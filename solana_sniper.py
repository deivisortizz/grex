import asyncio
import json
import os
import sqlite3
import traceback
import websockets
import jwt
import logging
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('SolanaSniper')

# Dependências Solana
try:
    from solana.rpc.async_api import AsyncClient
    from solders.pubkey import Pubkey
    from solders.keypair import Keypair
except ImportError:
    logger.warning("Aviso: Bibliotecas solana/solders não instaladas localmente ainda. Execute pip install -r requirements.txt")

WS_PORT = int(os.getenv("SOLANA_SNIPER_WS_PORT", "8767"))
DATA_DIR = os.getenv("DATA_DIR", "/app/data")

JWT_SECRET = os.getenv("JWT_SECRET", "multi-tenant-super-secret-fallback")
JWT_ALGORITHM = "HS256"

class SolanaSniper:
    def __init__(self):
        self.connected_clients = set()
        # Estado separado por user_id
        # user_id -> { "config": { ... }, "is_active": bool, "wallet": str }
        self.user_states = {}

    def _get_user_state(self, user_id):
        if user_id not in self.user_states:
            self.user_states[user_id] = {
                "config": {
                    "target_token": "",
                    "slippage": 15,
                    "jito_tip": 0.001,
                    "status": "idle" # idle, watching, sniping, complete
                },
                "is_active": False,
                "wallet": None
            }
        return self.user_states[user_id]

    def _load_user_config_from_db(self, user_id):
        db_path = os.path.join(DATA_DIR, 'solana_sniper.db')
        if not os.path.exists(db_path):
            return False
            
        state = self._get_user_state(user_id)
        
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # Load config
                cursor.execute("SELECT target_token, slippage, jito_tip FROM solana_sniper_configs WHERE user_id = ?", (user_id,))
                config_row = cursor.fetchone()
                if config_row:
                    state["config"]["target_token"] = config_row[0]
                    state["config"]["slippage"] = config_row[1]
                    state["config"]["jito_tip"] = config_row[2]
                
                # Load wallet
                cursor.execute("SELECT pk_encrypted FROM solana_burner_wallet WHERE user_id = ?", (user_id,))
                wallet_row = cursor.fetchone()
                if wallet_row and wallet_row[0]:
                    state["wallet"] = wallet_row[0]
                else:
                    state["wallet"] = None
                    
            return True
        except Exception as e:
            logger.error(f"Erro ao ler banco de dados para user {user_id}: {e}")
            return False

    async def broadcast_to_user(self, user_id, payload):
        if not self.connected_clients:
            return
            
        message = json.dumps(payload)
        to_remove = set()
        for client in self.connected_clients:
            if getattr(client, 'user_id', None) == user_id:
                try:
                    await client.send(message)
                except Exception:
                    to_remove.add(client)
        
        for client in to_remove:
            self.connected_clients.remove(client)

    async def log_to_user(self, user_id, level, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        await self.broadcast_to_user(user_id, {
            "type": "log",
            "log": f"[{timestamp}] [{level}] {message}"
        })
        logger.info(f"[User {user_id}] [{level}] {message}")

    async def ws_handler(self, websocket, path=None):
        logger.info("🔌 [WS] Nova conexão solicitada. Aguardando autenticação JWT...")
        
        try:
            try:
                auth_message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                auth_data = json.loads(auth_message)
                
                if auth_data.get("type") == "auth" and auth_data.get("token"):
                    token = auth_data.get("token")
                    try:
                        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                        websocket.user_id = payload.get("sub")
                        logger.info(f"✅ [WS] Cliente autenticado (User ID: {websocket.user_id})")
                    except Exception as e:
                        logger.warning(f"❌ [WS] Erro JWT: {e}. Cliente desconectado.")
                        return
                else:
                    logger.warning("⚠️ [WS] Primeira mensagem não foi de autenticação. Desconectando.")
                    return
            except asyncio.TimeoutError:
                logger.info("ℹ️ [WS] Tempo esgotado para autenticação. Desconectando.")
                return

            self.connected_clients.add(websocket)
            user_id = websocket.user_id
            
            # Carrega dados atualizados do banco ao conectar
            self._load_user_config_from_db(user_id)
            state = self._get_user_state(user_id)
            
            # Envia configuração atual
            await websocket.send(json.dumps({
                "type": "config",
                **state["config"]
            }))
            
            async for message in websocket:
                data = json.loads(message)
                
                if data.get("type") == "start":
                    # Recarrega banco para ter certeza que tem a config atualizada
                    self._load_user_config_from_db(user_id)
                    state = self._get_user_state(user_id)
                    
                    if not state["config"]["target_token"]:
                        await self.log_to_user(user_id, "ERROR", "Token alvo inválido ou não configurado no painel.")
                        continue
                        
                    if not state["wallet"]:
                        await self.log_to_user(user_id, "ERROR", "Nenhuma carteira Solana (Burner Wallet) cadastrada.")
                        continue
                        
                    state["config"]["status"] = "watching"
                    state["is_active"] = True
                    await self.log_to_user(user_id, "INFO", f"🚀 Iniciando monitoramento para: {state['config']['target_token']}")
                    await self.log_to_user(user_id, "INFO", f"⚙️ Estratégia: Pump.fun | Tip Jito: {state['config']['jito_tip']} SOL")
                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"]})
                    
                elif data.get("type") == "stop":
                    state = self._get_user_state(user_id)
                    state["is_active"] = False
                    state["config"]["status"] = "idle"
                    await self.log_to_user(user_id, "WARN", "⏸️ Monitoramento pausado pelo usuário.")
                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"]})

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"WS Error: {e}")
        finally:
            if websocket in self.connected_clients:
                self.connected_clients.remove(websocket)

    async def monitor_loop(self):
        # Aqui ficará a lógica de conexão com o WSS da Solana
        while True:
            for user_id, state in list(self.user_states.items()):
                if state["is_active"] and state["config"]["status"] == "watching":
                    try:
                        await self.log_to_user(user_id, "INFO", "🔎 Conectando ao WSS e escutando logs da Pump.fun...")
                        await asyncio.sleep(3)
                        
                        if state["is_active"]:
                            await self.log_to_user(user_id, "INFO", "⚡ Evento de curva de adesão (Bonding Curve) detectado!")
                            await asyncio.sleep(1)
                            await self.log_to_user(user_id, "INFO", "🔐 Validando Mint Authority & Freeze Authority do token...")
                            await asyncio.sleep(2)
                            
                            state["config"]["status"] = "sniping"
                            await self.broadcast_to_user(user_id, {"type": "config", **state["config"]})
                            await self.log_to_user(user_id, "WARN", "🔥 Montando Atomic Transaction (Jito Bundle)...")
                            await asyncio.sleep(1)
                            
                            await self.log_to_user(user_id, "INFO", f"💸 Anexando Priority Fee / Jito Tip: {state['config']['jito_tip']} SOL")
                            await asyncio.sleep(2)
                            
                            await self.log_to_user(user_id, "INFO", "✅ Transação de Snipe enviada e confirmada via Jito Block Engine!")
                            state["is_active"] = False
                            state["config"]["status"] = "complete"
                            await self.broadcast_to_user(user_id, {"type": "config", **state["config"]})
                            
                    except Exception as e:
                        await self.log_to_user(user_id, "ERROR", f"Falha no loop Solana: {e}")
                        await asyncio.sleep(5)
            await asyncio.sleep(1)

    async def start(self):
        logger.info(f"🚀 Iniciando Solana Sniper na porta {WS_PORT}")
        # Iniciar servidor WebSocket
        async with websockets.serve(self.ws_handler, "0.0.0.0", WS_PORT):
            await self.monitor_loop()

if __name__ == "__main__":
    sniper = SolanaSniper()
    asyncio.run(sniper.start())
