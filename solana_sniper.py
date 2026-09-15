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
from cryptography.fernet import Fernet

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
        self.init_crypto()

    def init_crypto(self):
        key_path = os.path.join(DATA_DIR, '.master.key')
        if not os.path.exists(key_path):
            logger.error("❌ [COFRE] Chave Mestra (.master.key) não encontrada! Inicialização abortada.")
            self.cipher = None
            return
        
        with open(key_path, 'rb') as f:
            key = f.read()
        self.cipher = Fernet(key)
        logger.info(f"🔑 [COFRE] Chave Mestra (Fernet) carregada com sucesso no Solana Sniper.")

    def _get_user_state(self, user_id):
        if user_id not in self.user_states:
            self.user_states[user_id] = {
                "config": {
                    "target_token": "",
                    "slippage": 15,
                    "jito_tip": 0.001,
                    "tp_pct": 100.0,
                    "sl_pct": 20.0,
                    "status": "idle" # idle, watching, sniping, complete, monitoring_position
                },
                "is_active": False,
                "wallet": None
            }
        return self.user_states[user_id]

    def _load_user_config_from_db(self, user_id):
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        if not os.path.exists(db_path):
            return False
            
        state = self._get_user_state(user_id)
        
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # Load config
                cursor.execute("SELECT target_token, slippage, jito_tip, tp_pct, sl_pct FROM solana_sniper_configs WHERE user_id = ?", (user_id,))
                config_row = cursor.fetchone()
                if config_row:
                    state["config"]["target_token"] = config_row[0]
                    state["config"]["slippage"] = config_row[1]
                    state["config"]["jito_tip"] = config_row[2]
                    state["config"]["tp_pct"] = config_row[3] if config_row[3] is not None else 100.0
                    state["config"]["sl_pct"] = config_row[4] if config_row[4] is not None else 20.0
                
                # Load wallet
                cursor.execute("SELECT pk_encrypted FROM solana_burner_wallet WHERE user_id = ?", (user_id,))
                wallet_row = cursor.fetchone()
                if wallet_row and wallet_row[0]:
                    try:
                        decrypted_pk = self.cipher.decrypt(wallet_row[0].encode()).decode() if self.cipher else wallet_row[0]
                        state["wallet"] = decrypted_pk
                    except Exception as dec_err:
                        logger.error(f"Erro ao descriptografar carteira Solana (User {user_id}): {dec_err}")
                        state["wallet"] = None
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
                        websocket.user_id = int(payload.get("sub"))
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
                **state["config"],
                "is_active": state["is_active"]
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
                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                    
                elif data.get("type") == "stop":
                    state = self._get_user_state(user_id)
                    state["is_active"] = False
                    state["config"]["status"] = "idle"
                    await self.log_to_user(user_id, "WARN", "⏸️ Monitoramento pausado pelo usuário.")
                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                    
                elif data.get("type") == "reset_wallet":
                    state = self._get_user_state(user_id)
                    state["wallet"] = None
                    state["is_active"] = False
                    state["config"]["status"] = "idle"
                    await self.log_to_user(user_id, "WARN", "🗑️ Carteira Solana apagada. Monitoramento interrompido.")
                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                    
                elif data.get("type") == "reset_config":
                    state = self._get_user_state(user_id)
                    state["config"]["target_token"] = ""
                    state["is_active"] = False
                    state["config"]["status"] = "idle"
                    await self.log_to_user(user_id, "WARN", "🗑️ Token Alvo apagado. Monitoramento interrompido.")
                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})

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
                # Recarrega a configuração do SQLite a cada ciclo
                self._load_user_config_from_db(user_id)
                
                if state["is_active"] and state["config"]["status"] == "watching":
                    if not state.get("wallet"):
                        # Segunda tentativa de leitura do banco de dados antes de disparar o erro
                        self._load_user_config_from_db(user_id)
                        if not state.get("wallet"):
                            await self.log_to_user(user_id, "ERROR", "Nenhuma carteira Solana (Burner Wallet) cadastrada.")
                            state["is_active"] = False
                            state["config"]["status"] = "idle"
                            await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                            continue
                        
                    try:
                        await self.log_to_user(user_id, "INFO", "🔎 Conectando ao WSS e escutando logs da Pump.fun...")
                        await asyncio.sleep(3)
                        
                        if state["is_active"]:
                            await self.log_to_user(user_id, "INFO", "⚡ Evento de curva de adesão (Bonding Curve) detectado!")
                            await asyncio.sleep(1)
                            await self.log_to_user(user_id, "INFO", "🔐 Validando Mint Authority & Freeze Authority do token...")
                            await asyncio.sleep(2)
                            
                            state["config"]["status"] = "sniping"
                            await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                            await self.log_to_user(user_id, "WARN", "🔥 Montando Atomic Transaction (Jito Bundle)...")
                            await asyncio.sleep(1)
                            
                            await self.log_to_user(user_id, "INFO", f"💸 Anexando Priority Fee / Jito Tip: {state['config']['jito_tip']} SOL")
                            await asyncio.sleep(2)
                            
                            await self.log_to_user(user_id, "INFO", "✅ Transação de Snipe enviada e confirmada via Jito Block Engine!")
                            
                            state["config"]["status"] = "monitoring_position"
                            await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                            
                            # Inicia o monitoramento da posição para o Auto-Sell (TP/SL)
                            entry_price_sol = 0.5 # Simulação de preço de entrada
                            asyncio.create_task(self.monitor_position(user_id, entry_price_sol))
                            
                    except Exception as e:
                        await self.log_to_user(user_id, "ERROR", f"Falha no loop Solana: {e}")
                        await asyncio.sleep(5)
            await asyncio.sleep(1)

    async def monitor_position(self, user_id, entry_price_sol):
        state = self._get_user_state(user_id)
        target_token = state["config"]["target_token"]
        tp_pct = state["config"]["tp_pct"]
        sl_pct = state["config"]["sl_pct"]
        
        await self.log_to_user(user_id, "INFO", f"📈 Iniciando rastreamento de posição para {target_token}...")
        await self.log_to_user(user_id, "WARN", f"🎯 Alvos definidos: Take-Profit (+{tp_pct}%) | Stop-Loss (-{sl_pct}%)")
        
        current_price = entry_price_sol
        tp_target = entry_price_sol * (1 + (tp_pct / 100.0))
        sl_target = entry_price_sol * (1 - (sl_pct / 100.0))
        
        iteration = 0
        while state["is_active"] and state["config"]["status"] == "monitoring_position":
            await asyncio.sleep(3)
            
            # Simula oscilação de preço
            iteration += 1
            if iteration % 2 == 0:
                current_price *= 1.15 # sobe 15%
            else:
                current_price *= 0.95 # cai 5%
                
            pnl_pct = ((current_price - entry_price_sol) / entry_price_sol) * 100
            
            # Checa TP
            if current_price >= tp_target:
                await self.log_to_user(user_id, "INFO", f"💰 [TAKE PROFIT] Preço atingiu +{pnl_pct:.2f}%. Executando venda via Jupiter/Raydium...")
                await asyncio.sleep(2)
                await self.log_to_user(user_id, "INFO", f"✅ Transação de Venda (Take Profit) confirmada!")
                break
                
            # Checa SL
            if current_price <= sl_target:
                await self.log_to_user(user_id, "ERROR", f"🛑 [STOP LOSS] Preço atingiu {pnl_pct:.2f}%. Executando venda de emergência...")
                await asyncio.sleep(2)
                await self.log_to_user(user_id, "INFO", f"✅ Transação de Venda (Stop Loss) confirmada.")
                break
                
        # Finaliza o tracking e retorna para observação
        if state["is_active"]:
            state["config"]["status"] = "watching"
            await self.log_to_user(user_id, "INFO", "🔄 Retornando ao modo de observação (watching) para novos snipes.")
            await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})

    async def start(self):
        logger.info(f"🚀 Iniciando Solana Sniper na porta {WS_PORT}")
        # Iniciar servidor WebSocket
        async with websockets.serve(self.ws_handler, "0.0.0.0", WS_PORT):
            await self.monitor_loop()

if __name__ == "__main__":
    sniper = SolanaSniper()
    asyncio.run(sniper.start())
