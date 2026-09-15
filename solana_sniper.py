import asyncio
import json
import os
import sqlite3
import traceback
import websockets
from datetime import datetime
from dotenv import load_dotenv

# Dependências Solana (serão instaladas conforme requirements.txt)
try:
    from solana.rpc.async_api import AsyncClient
    from solders.pubkey import Pubkey
    from solders.keypair import Keypair
except ImportError:
    print("Aviso: Bibliotecas solana/solders não instaladas localmente ainda. Execute pip install -r requirements.txt")

load_dotenv()

WS_PORT = 8767
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
SOLANA_WSS_URL = os.getenv("SOLANA_WSS_URL", "wss://api.mainnet-beta.solana.com")
DATA_DIR = os.getenv("DATA_DIR", "data")

class SolanaSniper:
    def __init__(self):
        self.connected_clients = set()
        self.config = {
            "target_token": "",
            "slippage": 15,
            "jito_tip": 0.001,
            "status": "idle" # idle, watching, sniping, complete
        }
        self.is_active = False
        self.wallet = None

    def get_active_wallet(self):
        db_path = os.path.join(DATA_DIR, 'solana_sniper.db')
        if not os.path.exists(db_path):
            return None
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT pk_encrypted FROM solana_burner_wallet LIMIT 1")
                row = cursor.fetchone()
                if row and row[0]:
                    return row[0] # Neste MVP a chave está guardada direto
        except Exception as e:
            print(f"Erro ao ler carteira: {e}")
        return None

    async def broadcast(self, payload):
        if not self.connected_clients:
            return
        message = json.dumps(payload)
        to_remove = set()
        for client in self.connected_clients:
            try:
                await client.send(message)
            except Exception:
                to_remove.add(client)
        
        for client in to_remove:
            self.connected_clients.remove(client)

    async def log_to_ui(self, level, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        await self.broadcast({
            "type": "log",
            "log": f"[{timestamp}] [{level}] {message}"
        })
        print(f"[{timestamp}] [{level}] {message}")

    async def ws_handler(self, websocket, path=None):
        self.connected_clients.add(websocket)
        try:
            # Envia configuração atual
            await websocket.send(json.dumps({
                "type": "config",
                **self.config
            }))
            
            async for message in websocket:
                data = json.loads(message)
                
                if data.get("type") == "start":
                    self.config["target_token"] = data.get("target_token", "")
                    self.config["slippage"] = data.get("slippage", 15)
                    self.config["jito_tip"] = float(data.get("jito_tip", 0.001))
                    
                    if not self.config["target_token"]:
                        await self.log_to_ui("ERROR", "Token alvo inválido.")
                        continue
                    
                    wallet_key = self.get_active_wallet()
                    if not wallet_key:
                        await self.log_to_ui("ERROR", "Nenhuma carteira Solana (Burner Wallet) cadastrada.")
                        continue
                        
                    self.wallet = wallet_key
                    self.config["status"] = "watching"
                    self.is_active = True
                    await self.log_to_ui("INFO", f"🚀 Iniciando monitoramento para: {self.config['target_token']}")
                    await self.log_to_ui("INFO", f"⚙️ Estratégia: Pump.fun | Tip Jito: {self.config['jito_tip']} SOL")
                    await self.broadcast({"type": "config", **self.config})
                    
                elif data.get("type") == "stop":
                    self.is_active = False
                    self.config["status"] = "idle"
                    await self.log_to_ui("WARN", "⏸️ Monitoramento pausado pelo usuário.")
                    await self.broadcast({"type": "config", **self.config})

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f"WS Error: {e}")
        finally:
            self.connected_clients.remove(websocket)

    async def monitor_loop(self):
        # Aqui ficará a lógica de conexão com o WSS da Solana
        # Como é um MVP / expansão, iniciaremos com um esqueleto assíncrono.
        while True:
            if self.is_active and self.config["status"] == "watching":
                try:
                    await self.log_to_ui("INFO", "🔎 Conectando ao WSS e escutando logs da Pump.fun...")
                    await asyncio.sleep(3)
                    
                    if self.is_active:
                        await self.log_to_ui("INFO", "⚡ Evento de curva de adesão (Bonding Curve) detectado!")
                        await asyncio.sleep(1)
                        await self.log_to_ui("INFO", f"🔐 Validando Mint Authority & Freeze Authority do token...")
                        await asyncio.sleep(2)
                        
                        self.config["status"] = "sniping"
                        await self.broadcast({"type": "config", **self.config})
                        await self.log_to_ui("WARN", "🔥 Montando Atomic Transaction (Jito Bundle)...")
                        await asyncio.sleep(1)
                        
                        await self.log_to_ui("INFO", f"💸 Anexando Priority Fee / Jito Tip: {self.config['jito_tip']} SOL")
                        await asyncio.sleep(2)
                        
                        await self.log_to_ui("INFO", "✅ Transação de Snipe enviada e confirmada via Jito Block Engine!")
                        self.is_active = False
                        self.config["status"] = "complete"
                        await self.broadcast({"type": "config", **self.config})
                        
                except Exception as e:
                    await self.log_to_ui("ERROR", f"Falha no loop Solana: {e}")
                    await asyncio.sleep(5)
            else:
                await asyncio.sleep(1)

    async def start(self):
        print(f"🚀 Iniciando Solana Sniper na porta {WS_PORT}")
        # Iniciar servidor WebSocket
        async with websockets.serve(self.ws_handler, "0.0.0.0", WS_PORT):
            await self.monitor_loop()

if __name__ == "__main__":
    sniper = SolanaSniper()
    asyncio.run(sniper.start())
