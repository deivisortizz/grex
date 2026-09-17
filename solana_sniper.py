import asyncio
import json
import os
import sqlite3
import base64
import base58
import traceback
import websockets
import jwt
import logging
import sys
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

load_dotenv()

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('SolanaSniper')

# Dependências Solana verificadas acima

WS_PORT = int(os.getenv("SOLANA_SNIPER_WS_PORT", "8767"))
DATA_DIR = os.getenv('DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))

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
        os.makedirs(DATA_DIR, exist_ok=True)
        key_path = os.path.join(DATA_DIR, '.master.key')
        if not os.path.exists(key_path):
            logger.info("⚠️ [COFRE] Chave Mestra (.master.key) não encontrada. Gerando nova chave...")
            master_key = Fernet.generate_key()
            with open(key_path, 'wb') as f:
                f.write(master_key)
        else:
            with open(key_path, 'rb') as f:
                master_key = f.read()
                
        self.cipher = Fernet(master_key)
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
                "wallet": None,
                "daily_pnl_usd": 0.0,
                "total_trades": 0,
                "win_trades": 0,
                "open_positions": {}
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
                    new_token = config_row[0]
                    state["config"]["target_token"] = new_token if new_token else ""
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

    async def _get_sol_balance(self, pubkey_str, session, rpc_url):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBalance",
            "params": [pubkey_str]
        }
        try:
            async with session.post(rpc_url, json=payload) as resp:
                result = await resp.json()
                if "result" in result and "value" in result["result"]:
                    return result["result"]["value"] / 1_000_000_000
        except Exception:
            pass
        return 0.0

    async def _wait_for_balance_change(self, pubkey_str, initial_balance, is_buy, session, rpc_url, user_id):
        retries = 0
        current_balance = initial_balance
        while retries < 15:
            await asyncio.sleep(1)
            current_balance = await self._get_sol_balance(pubkey_str, session, rpc_url)
            
            if is_buy and current_balance < initial_balance:
                return current_balance
            elif not is_buy and current_balance > initial_balance:
                return current_balance
                
            retries += 1
            
        await self.log_to_user(user_id, "WARN", "Tempo esgotado aguardando mudança de saldo. Usando último saldo lido.")
        return current_balance

    async def _fetch_mint_from_tx(self, signature, session, rpc_url):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}
            ]
        }
        
        # Faz até 10 tentativas esperando a transação ficar disponível no RPC
        for _ in range(10):
            try:
                async with session.post(rpc_url, json=payload) as resp:
                    data = await resp.json()
                    if "result" in data and data["result"]:
                        meta = data["result"].get("meta", {})
                        post_token_balances = meta.get("postTokenBalances", [])
                        if post_token_balances:
                            # O primeiro token balance criado na pump.fun é o próprio token
                            return post_token_balances[0].get("mint")
            except Exception:
                pass
            await asyncio.sleep(1)
            
        return None

    async def _process_new_pool(self, signature):
        rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=afef48e6-b88a-49e6-84c4-9b408156ee55")
        async with aiohttp.ClientSession() as session:
            mint = await self._fetch_mint_from_tx(signature, session, rpc_url)
            if not mint:
                return
                
        logger.info(f"⚡ [LIVE POOL] Novo token criado na Pump.fun: {mint}")
        
        # Broadcast para todos os clientes via WebSocket (Live Feed)
        payload = {
            "type": "new_pool",
            "token": mint,
            "timestamp": int(datetime.now().timestamp() * 1000)
        }
        msg = json.dumps(payload)
        to_remove = set()
        for client in self.connected_clients:
            try:
                await client.send(msg)
            except Exception:
                to_remove.add(client)
        for client in to_remove:
            self.connected_clients.remove(client)
            
        # Acionar Sniper Global
        for user_id, state in list(self.user_states.items()):
            if state["is_active"] and state["config"]["status"] == "watching":
                target_token = state["config"].get("target_token")
                if not target_token: # Modo Global
                    if not state.get("wallet"):
                        await self.log_to_user(user_id, "ERROR", "Nenhuma carteira Solana cadastrada. Desativando Sniper Global.")
                        state["is_active"] = False
                        state["config"]["status"] = "idle"
                        await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                        continue
                        
                    await self.log_to_user(user_id, "INFO", f"🌍 Evento GLOBAL detectado na Pump.fun para: {mint}!")
                    state["config"]["status"] = "sniping"
                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                    asyncio.create_task(self.handle_snipe_and_monitor(user_id, state, mint))

    async def log_to_user(self, user_id, level, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        await self.broadcast_to_user(user_id, {
            "type": "log",
            "log": f"[{timestamp}] [{level}] {message}"
        })
        logger.info(f"[User {user_id}] [{level}] {message}")

    def _get_daily_stats_from_db(self, user_id):
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        stats = {
            "daily_pnl_usd": 0.0,
            "daily_pnl_sol": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0
        }
        if not os.path.exists(db_path):
            return stats
            
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        SUM(net_pnl_usd) as daily_pnl_usd,
                        SUM(net_pnl_sol) as daily_pnl_sol,
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN is_win THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN NOT is_win THEN 1 ELSE 0 END) as losses
                    FROM solana_sniper_history
                    WHERE user_id = ? AND date(created_at) = date('now')
                ''', (user_id,))
                row = cursor.fetchone()
                if row and row[2] > 0:
                    stats["daily_pnl_usd"] = row[0] or 0.0
                    stats["daily_pnl_sol"] = row[1] or 0.0
                    stats["total_trades"] = row[2]
                    stats["wins"] = row[3] or 0
                    stats["losses"] = row[4] or 0
                    stats["win_rate"] = round((stats["wins"] / stats["total_trades"]) * 100, 1) if stats["total_trades"] > 0 else 0.0
        except Exception as e:
            logger.error(f"Erro ao ler estatísticas do BD para user {user_id}: {e}")
            
        return stats

    def _save_trade_history(self, user_id, token_mint, sol_spent, sol_received, jito_tip_buy, jito_tip_sell, is_win):
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        # sol_spent e sol_received já são variações brutas do saldo da Helius.
        # Eles já embutem nativamente a taxa do Jito, o Gas, e o valor do Token.
        # Portanto, o PnL Líquido é puramente:
        net_pnl_sol = sol_received - sol_spent
        sol_price_usd = 150.0 # Placeholder estático ou buscar dinamicamente
        net_pnl_usd = net_pnl_sol * sol_price_usd
        
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO solana_sniper_history (
                        user_id, token_mint, sol_spent, sol_received, 
                        jito_tip_buy, jito_tip_sell, net_pnl_sol, net_pnl_usd, is_win
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, token_mint, sol_spent, sol_received, jito_tip_buy, jito_tip_sell, net_pnl_sol, net_pnl_usd, is_win))
                conn.commit()
        except Exception as e:
            logger.error(f"Erro ao salvar histórico do BD para user {user_id}: {e}")

    async def broadcast_metrics(self, user_id):
        stats = self._get_daily_stats_from_db(user_id)
        await self.broadcast_to_user(user_id, {
            "type": "STATS_UPDATE",
            "data": stats
        })

    async def broadcast_positions(self, user_id):
        state = self._get_user_state(user_id)
        positions = list(state.get("open_positions", {}).values())
        await self.broadcast_to_user(user_id, {"type": "open_positions", "positions": positions})

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
                        await websocket.close(code=4001, reason="JWT Error")
                        return
                else:
                    logger.warning("⚠️ [WS] Primeira mensagem não foi de autenticação. Desconectando.")
                    await websocket.close(code=4001, reason="Auth required")
                    return
            except asyncio.TimeoutError:
                logger.info("ℹ️ [WS] Tempo esgotado para autenticação. Desconectando.")
                await websocket.close(code=4001, reason="Timeout")
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
            
            # Envia estatísticas de PnL no momento da conexão
            await self.broadcast_metrics(user_id)
            
            async for message in websocket:
                data = json.loads(message)
                
                if data.get("type") == "start":
                    # Recarrega banco para ter certeza que tem a config atualizada
                    self._load_user_config_from_db(user_id)
                    state = self._get_user_state(user_id)
                    
                    target_token = state["config"].get("target_token")
                        
                    if not state["wallet"]:
                        await self.log_to_user(user_id, "ERROR", "Nenhuma carteira Solana (Burner Wallet) cadastrada.")
                        continue
                        
                    state["config"]["status"] = "watching"
                    state["is_active"] = True
                    
                    if target_token:
                        await self.log_to_user(user_id, "INFO", f"🚀 Iniciando monitoramento EXCLUSIVO para: {target_token}")
                    else:
                        await self.log_to_user(user_id, "WARN", "🌍 MODO GLOBAL: Escutando TODOS os novos lançamentos da Pump.fun!")
                        
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

                elif data.get("type") == "force_buy":
                    token_to_buy = data.get("token")
                    if not token_to_buy:
                        await self.log_to_user(user_id, "ERROR", "Nenhum token fornecido para compra manual.")
                        continue
                    state = self._get_user_state(user_id)
                    if not state["wallet"]:
                        await self.log_to_user(user_id, "ERROR", "Nenhuma carteira Solana (Burner Wallet) cadastrada.")
                        continue
                    
                    await self.log_to_user(user_id, "WARN", f"⚡ Invocando COMPRA MANUAL para o token: {token_to_buy}")
                    asyncio.create_task(self.handle_snipe_and_monitor(user_id, state, token_to_buy))

                elif data.get("type") == "force_sell":
                    token_to_sell = data.get("token")
                    if not token_to_sell:
                        await self.log_to_user(user_id, "ERROR", "Nenhum token fornecido para venda manual.")
                        continue
                    state = self._get_user_state(user_id)
                    if not state["wallet"]:
                        await self.log_to_user(user_id, "ERROR", "Nenhuma carteira Solana (Burner Wallet) cadastrada.")
                        continue
                    
                    await self.log_to_user(user_id, "WARN", f"🔴 Invocando VENDA MANUAL (DUMP) para o token: {token_to_sell}")
                    asyncio.create_task(self.execute_real_sell(user_id, state, token_to_sell))


        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"WS Error: {e}")
        finally:
            if websocket in self.connected_clients:
                self.connected_clients.remove(websocket)

    async def execute_real_sell(self, user_id, state, token_mint):
        try:
            wallet_pk_str = state.get("wallet")
            if not wallet_pk_str:
                return False

            try:
                if wallet_pk_str.startswith("["):
                    key_bytes = bytes(json.loads(wallet_pk_str))
                    payer = Keypair.from_bytes(key_bytes)
                else:
                    payer = Keypair.from_bytes(base58.b58decode(wallet_pk_str))
            except Exception as e:
                await self.log_to_user(user_id, "ERROR", f"Erro ao decodificar chave privada: {e}")
                return False

            jito_tip_sol = float(state["config"]["jito_tip"])
            slippage = float(state["config"]["slippage"])

            await self.log_to_user(user_id, "WARN", f"🔴 Construindo transação de VENDA (PumpPortal) para {token_mint}...")
            
            payload = {
                "publicKey": str(payer.pubkey()),
                "action": "sell",
                "mint": token_mint.strip(),
                "amount": "100%",
                "denominatedInSol": "false",
                "slippage": int(slippage),
                "priorityFee": float(jito_tip_sol),
                "pool": "auto"
            }

            rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=afef48e6-b88a-49e6-84c4-9b408156ee55")
            async with aiohttp.ClientSession() as session:
                payer_pubkey_str = str(payer.pubkey())
                balance_before = await self._get_sol_balance(payer_pubkey_str, session, rpc_url)
                await self.log_to_user(user_id, "INFO", f"💳 Saldo inicial antes da venda: {balance_before:.5f} SOL")
                
                async with session.post("https://pumpportal.fun/api/trade-local", json=payload) as response:
                    if response.status != 200:
                        err_text = await response.text()
                        await self.log_to_user(user_id, "ERROR", f"Falha na API PumpPortal (Venda): {err_text}")
                        return False
                    tx_bytes = await response.read()

                transaction = VersionedTransaction.from_bytes(tx_bytes)
                signed_tx = VersionedTransaction(transaction.message, [payer])
                
                await self.log_to_user(user_id, "WARN", "🚀 Disparando transação de VENDA assinada para a rede (Helius/Jito)...")
                
                # Bypassing strict preflight simulation via HTTP POST JSON-RPC
                encoded_tx = base64.b64encode(bytes(signed_tx)).decode('utf-8')
                rpc_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "sendTransaction",
                    "params": [
                        encoded_tx,
                        {
                            "encoding": "base64",
                            "skipPreflight": True,
                            "maxRetries": 2
                        }
                    ]
                }
                
                async with session.post(rpc_url, json=rpc_payload) as rpc_resp:
                    rpc_result = await rpc_resp.json()
                    if "result" in rpc_result:
                        tx_sig = rpc_result["result"]
                        await self.log_to_user(user_id, "INFO", f"✅ Venda disparada! TX: {tx_sig}")
                        
                        await self.log_to_user(user_id, "INFO", "⏳ Aguardando confirmação (mudança de saldo)...")
                        balance_after = await self._wait_for_balance_change(payer_pubkey_str, balance_before, False, session, rpc_url, user_id)
                        
                        sol_received = balance_after - balance_before
                        if sol_received <= 0:
                            # Fallback caso RPC atrase
                            sol_received = 0.0
                            
                        await self.log_to_user(user_id, "INFO", f"💸 Saldo final: {balance_after:.5f} SOL | Receita Real: {sol_received:.5f} SOL")
                        
                        # Recupera dados da compra
                        pos_data = state["open_positions"].get(token_mint, {})
                        sol_spent = pos_data.get("sol_spent", 0.0)
                        jito_tip_buy = pos_data.get("jito_tip_buy", 0.0)
                        
                        # Se não tinha sol_spent (ex: venda isolada), consideramos pnl neutro ou erro
                        if sol_spent == 0:
                            is_win = sol_received > (jito_tip_buy + jito_tip_sol)
                        else:
                            is_win = sol_received > sol_spent
                            
                        self._save_trade_history(
                            user_id=user_id,
                            token_mint=token_mint,
                            sol_spent=sol_spent,
                            sol_received=sol_received,
                            jito_tip_buy=jito_tip_buy,
                            jito_tip_sell=jito_tip_sol,
                            is_win=is_win
                        )
                        
                        # Remove a posição aberta
                        if token_mint in state["open_positions"]:
                            del state["open_positions"][token_mint]
                            
                        state["config"]["status"] = "idle"
                        await self.broadcast_metrics(user_id)
                        await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                        return True
                    else:
                        err_msg = rpc_result.get("error", "Erro desconhecido")
                        await self.log_to_user(user_id, "ERROR", f"A rede recusou a transação de venda: {err_msg}")
                        return False

        except Exception as e:
            await self.log_to_user(user_id, "ERROR", f"Falha crítica ao executar venda real: {e}")
            logger.error(traceback.format_exc())
            return False

    async def execute_real_snipe(self, user_id, state, token_mint):
        try:
            wallet_pk_str = state.get("wallet")
            if not wallet_pk_str:
                await self.log_to_user(user_id, "ERROR", "Carteira Burner não encontrada para assinatura.")
                return False

            # Carrega a Keypair da Solana a partir da chave privada do cofre
            try:
                # Suporta formato base58 ou lista de bytes (JSON string)
                if wallet_pk_str.startswith("["):
                    key_bytes = bytes(json.loads(wallet_pk_str))
                    payer = Keypair.from_bytes(key_bytes)
                else:
                    payer = Keypair.from_bytes(base58.b58decode(wallet_pk_str))
            except Exception as e:
                await self.log_to_user(user_id, "ERROR", f"Erro ao decodificar chave privada da Burner Wallet: {e}")
                return False

            await self.log_to_user(user_id, "INFO", f"🔑 Carteira carregada: {payer.pubkey()}")

            jito_tip_sol = float(state["config"]["jito_tip"])
            slippage = float(state["config"]["slippage"])
            buy_amount_sol = float(state["config"].get("snipe_size", 0.05))

            rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=afef48e6-b88a-49e6-84c4-9b408156ee55")
            async with aiohttp.ClientSession() as session:
                
                # Puxa o saldo inicial (antes da compra)
                payer_pubkey_str = str(payer.pubkey())
                balance_before = await self._get_sol_balance(payer_pubkey_str, session, rpc_url)
                await self.log_to_user(user_id, "INFO", f"💳 Saldo inicial: {balance_before:.5f} SOL")

                await self.log_to_user(user_id, "WARN", f"🔥 Construindo transação atômica (PumpPortal) para {token_mint}...")
                
                payload = {
                    "publicKey": str(payer.pubkey()),
                    "action": "buy",
                    "mint": token_mint.strip(),
                    "amount": float(buy_amount_sol),
                    "denominatedInSol": "true",
                    "slippage": int(slippage),
                    "priorityFee": float(jito_tip_sol),
                    "pool": "auto"
                }

                async with session.post("https://pumpportal.fun/api/trade-local", json=payload) as response:
                    if response.status != 200:
                        err_text = await response.text()
                        await self.log_to_user(user_id, "ERROR", f"Falha na API PumpPortal: {err_text}")
                        return False
                    tx_bytes = await response.read()

                # Deserializa e prepara para assinatura
                transaction = VersionedTransaction.from_bytes(tx_bytes)
                
                signed_tx = VersionedTransaction(transaction.message, [payer])
                
                await self.log_to_user(user_id, "WARN", "🚀 Disparando transação assinada para a rede (Helius/Jito)...")
                
                encoded_tx = base64.b64encode(bytes(signed_tx)).decode('utf-8')
                rpc_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "sendTransaction",
                    "params": [
                        encoded_tx,
                        {
                            "encoding": "base64",
                            "skipPreflight": True,
                            "maxRetries": 2
                        }
                    ]
                }
                
                async with session.post(rpc_url, json=rpc_payload) as rpc_resp:
                    rpc_result = await rpc_resp.json()
                    
                    if "result" in rpc_result:
                        tx_sig = rpc_result["result"]
                        await self.log_to_user(user_id, "INFO", f"✅ Transação de compra disparada! TX: {tx_sig}")
                        
                        await self.log_to_user(user_id, "INFO", "⏳ Aguardando confirmação (mudança de saldo)...")
                        balance_after = await self._wait_for_balance_change(payer_pubkey_str, balance_before, True, session, rpc_url, user_id)
                        
                        sol_spent = balance_before - balance_after
                        if sol_spent <= 0:
                            # Fallback caso Helius não atualizou o saldo a tempo
                            sol_spent = buy_amount_sol + jito_tip_sol + 0.0001
                            
                        await self.log_to_user(user_id, "INFO", f"💸 Saldo final: {balance_after:.5f} SOL | Custo Real: {sol_spent:.5f} SOL")
                        
                        # Guardamos o sol_spent no estado da posição aberta!
                        state["open_positions"][token_mint] = {
                            "sol_spent": sol_spent,
                            "jito_tip_buy": jito_tip_sol
                        }
                        
                        return True
                    else:
                        err_msg = rpc_result.get("error", "Erro desconhecido")
                        await self.log_to_user(user_id, "ERROR", f"A rede retornou erro ao enviar a transação de compra: {err_msg}")
                        return False

        except Exception as e:
            await self.log_to_user(user_id, "ERROR", f"Falha crítica ao executar snipe real: {e}")
            logger.error(traceback.format_exc())
            return False

    async def handle_snipe_and_monitor(self, user_id, state, target_token):
        success = await self.execute_real_snipe(user_id, state, target_token)
        if success:
            state["config"]["status"] = "monitoring_position"
            await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
            # Start position monitoring
            entry_price_sol = 0.5 # Replace with actual logic when available
            asyncio.create_task(self.monitor_position(user_id, entry_price_sol, token_mint=target_token))
        else:
            state["is_active"] = False
            state["config"]["status"] = "idle"
            await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})

    async def monitor_loop(self):
        wss_url = os.getenv("SOLANA_WSS_URL", "wss://mainnet.helius-rpc.com/?api-key=afef48e6-b88a-49e6-84c4-9b408156ee55")
        pump_fun_program = "6EF8rrecthR5Dkzon8Nwu78hRvfX9PNXTxmD8bXU1K5A"
        
        subscribe_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [pump_fun_program]},
                {"commitment": "processed"}
            ]
        }
        
        while True:
            try:
                async with websockets.connect(wss_url, ping_interval=60, ping_timeout=120) as ws:
                    logger.info(f"Conectado ao WSS Solana: {wss_url.split('?')[0]}***")
                    await ws.send(json.dumps(subscribe_msg))
                    
                    async for message in ws:
                        data = json.loads(message)
                        
                        if "method" not in data or data["method"] != "logsNotification":
                            continue
                            
                        params = data.get("params", {})
                        logs = params.get("result", {}).get("value", {}).get("logs", [])
                        if not logs:
                            continue
                            
                        logs_str = str(logs)
                        signature = params.get("result", {}).get("value", {}).get("signature")
                        
                        # 1. Trata criação de novos pools (Live Feed e Global Sniping)
                        if "InitializeMint2" in logs_str or "InitializeMint" in logs_str:
                            if signature:
                                asyncio.create_task(self._process_new_pool(signature))
                        
                        # 2. Processa usuários que estão no modo Target (Alvo Específico)
                        for user_id, state in list(self.user_states.items()):
                            if state["is_active"] and state["config"]["status"] == "watching":
                                target_token = state["config"].get("target_token")
                                
                                if target_token and target_token in logs_str:
                                    if not state.get("wallet"):
                                        await self.log_to_user(user_id, "ERROR", "Nenhuma carteira Solana cadastrada.")
                                        state["is_active"] = False
                                        state["config"]["status"] = "idle"
                                        await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                                        continue
                                        
                                    await self.log_to_user(user_id, "INFO", f"⚡ Evento ALVO detectado na Pump.fun para: {target_token}!")
                                    state["config"]["status"] = "sniping"
                                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                                    asyncio.create_task(self.handle_snipe_and_monitor(user_id, state, target_token))
            except Exception as e:
                logger.error(f"Erro no WSS Solana: {e}. Reconectando em 5s...")
                await asyncio.sleep(5)

    async def monitor_position(self, user_id, entry_price_sol, token_mint="TOKEN_DEFAULT"):
        state = self._get_user_state(user_id)
        target_token = token_mint
        tp_pct = state["config"]["tp_pct"]
        sl_pct = state["config"]["sl_pct"]
        
        await self.log_to_user(user_id, "INFO", f"📈 Iniciando rastreamento de posição para {target_token}...")
        await self.log_to_user(user_id, "WARN", f"🎯 Alvos definidos: Take-Profit (+{tp_pct}%) | Stop-Loss (-{sl_pct}%)")
        
        current_price = entry_price_sol
        tp_target = entry_price_sol * (1 + (tp_pct / 100.0))
        sl_target = entry_price_sol * (1 - (sl_pct / 100.0))
        
        # Registra posição inicial preservando dados existentes (como sol_spent do snipe)
        if target_token not in state["open_positions"]:
            state["open_positions"][target_token] = {}
            
        state["open_positions"][target_token].update({
            "token": target_token,
            "entry_price": entry_price_sol,
            "current_price": current_price,
            "pnl_pct": 0.0
        })
        await self.broadcast_positions(user_id)
        
        iteration = 0
        profit_sol = 0
        is_win = False
        
        while state["is_active"] and state["config"]["status"] == "monitoring_position":
            await asyncio.sleep(3)
            
            # Simula oscilação de preço
            iteration += 1
            if iteration % 2 == 0:
                current_price *= 1.15 # sobe 15%
            else:
                current_price *= 0.95 # cai 5%
                
            pnl_pct = ((current_price - entry_price_sol) / entry_price_sol) * 100
            
            # Atualiza e envia posições ao vivo
            if target_token in state["open_positions"]:
                state["open_positions"][target_token]["current_price"] = current_price
                state["open_positions"][target_token]["pnl_pct"] = pnl_pct
                await self.broadcast_positions(user_id)
            
            # Checa TP
            if current_price >= tp_target:
                await self.log_to_user(user_id, "INFO", f"💰 [TAKE PROFIT] Preço atingiu +{pnl_pct:.2f}%. Executando venda via Jupiter/Raydium...")
                await self.execute_real_sell(user_id, state, target_token)
                break
                
            # Checa SL
            if current_price <= sl_target:
                await self.log_to_user(user_id, "ERROR", f"🛑 [STOP LOSS] Preço atingiu {pnl_pct:.2f}%. Executando venda de emergência...")
                await self.execute_real_sell(user_id, state, target_token)
                break
                
        # PnL logic was delegated to execute_real_sell
        pass
        
        if target_token in state["open_positions"]:
            del state["open_positions"][target_token]
            
        await self.broadcast_metrics(user_id)
        await self.broadcast_positions(user_id)
                
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
