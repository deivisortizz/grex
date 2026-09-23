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

DATA_DIR = os.getenv('DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
JWT_SECRET = os.getenv("JWT_SECRET", "multi-tenant-super-secret-fallback")
JWT_ALGORITHM = "HS256"

# [FIX] Backoff dedicado para HTTP 429 (rate limit) no handshake de WSS.
# Usado por solana_sniper.py, copy_sniper.py e raydium_migrator.py — todos os
# loops que abrem websockets.connect() para Helius/PumpPortal. Um 429 é o
# provedor pedindo EXPLICITAMENTE pra desacelerar; reconectar rápido (como no
# backoff normal de queda de conexão) só piora o rate limit. Por isso este
# schedule é bem mais conservador e não reaproveita o backoff "rápido".
RATE_LIMIT_BACKOFF_SCHEDULE = [5.0, 10.0, 30.0, 60.0]


def is_rate_limited_error(exc):
    """Detecta se uma exceção de handshake de WebSocket é um HTTP 429."""
    try:
        import websockets.exceptions as ws_exc
        if isinstance(exc, getattr(ws_exc, "InvalidStatus", ())):
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 429:
                return True
        if isinstance(exc, getattr(ws_exc, "InvalidStatusCode", ())):
            if getattr(exc, "status_code", None) == 429:
                return True
    except Exception:
        pass
    return "429" in str(exc)


def rate_limit_delay(streak):
    """Retorna o próximo intervalo de espera (em segundos) para uma sequência
    de 'streak' erros 429 consecutivos, seguindo RATE_LIMIT_BACKOFF_SCHEDULE."""
    idx = min(streak, len(RATE_LIMIT_BACKOFF_SCHEDULE) - 1)
    return RATE_LIMIT_BACKOFF_SCHEDULE[idx]


class SolanaCore:
    def __init__(self, history_table="solana_sniper_history", logger_name="SolanaCore"):
        self.history_table = history_table
        self.logger = logging.getLogger(logger_name)
        self.connected_clients = set()
        self.user_states = {}
        self.init_crypto()

    def init_crypto(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        key_path = os.path.join(DATA_DIR, '.master.key')
        if not os.path.exists(key_path):
            self.logger.info("⚠️ [COFRE] Chave Mestra (.master.key) não encontrada. Gerando nova chave...")
            master_key = Fernet.generate_key()
            with open(key_path, 'wb') as f:
                f.write(master_key)
        else:
            with open(key_path, 'rb') as f:
                master_key = f.read()
                
        self.cipher = Fernet(master_key)
        self.logger.info(f"🔑 [COFRE] Chave Mestra (Fernet) carregada com sucesso no Solana Core.")

    def _get_user_state(self, user_id):
        if user_id not in self.user_states:
            self.user_states[user_id] = {
                "config": {
                    "target_token": "",
                    "slippage": 15,
                    "jito_tip": 0.001,
                    "tp_pct": 20.0,
                    "sl_pct": 10.0,
                    "max_positions": 1,
                    "hardcore_mode": False,
                    "status": "idle"
                },
                "is_active": False,
                "wallet": None,
                "daily_pnl_usd": 0.0,
                "total_trades": 0,
                "win_trades": 0,
                "open_positions": {},
                "tracked_wallets": []
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
                cursor.execute("SELECT target_token, slippage, jito_tip, tp_pct, sl_pct, is_active, max_positions, hardcore_mode, trade_amount, anti_delay_filter, socials_filter, max_bonding_curve, min_trade_amount_sol FROM solana_sniper_configs WHERE user_id = ?", (user_id,))
                config_row = cursor.fetchone()
                if config_row:
                    new_token = config_row[0]
                    state["config"]["target_token"] = new_token if new_token else ""
                    state["config"]["slippage"] = config_row[1]
                    state["config"]["jito_tip"] = config_row[2]
                    state["config"]["tp_pct"] = config_row[3] if config_row[3] is not None else 20.0
                    state["config"]["sl_pct"] = config_row[4] if config_row[4] is not None else 10.0
                    
                    if len(config_row) > 6 and config_row[6] is not None:
                        state["config"]["max_positions"] = config_row[6]
                    if len(config_row) > 7 and config_row[7] is not None:
                        state["config"]["hardcore_mode"] = bool(config_row[7])
                    if len(config_row) > 8 and config_row[8] is not None:
                        state["config"]["trade_amount"] = config_row[8]
                    if len(config_row) > 9 and config_row[9] is not None:
                        state["config"]["anti_delay_filter"] = bool(config_row[9])
                    else:
                        state["config"]["anti_delay_filter"] = True
                        
                    if len(config_row) > 10 and config_row[10] is not None:
                        state["config"]["socials_filter"] = bool(config_row[10])
                    else:
                        state["config"]["socials_filter"] = True
                        
                    if len(config_row) > 11 and config_row[11] is not None:
                        state["config"]["max_bonding_curve"] = config_row[11]
                    else:
                        state["config"]["max_bonding_curve"] = 20.0
                        
                    if len(config_row) > 12 and config_row[12] is not None:
                        state["config"]["min_trade_amount_sol"] = config_row[12]
                    else:
                        state["config"]["min_trade_amount_sol"] = 0.02

                    if len(config_row) > 5 and config_row[5] is not None:
                        state["is_active"] = bool(config_row[5])
                        if state["is_active"]:
                            state["config"]["status"] = "watching"
                        else:
                            state["config"]["status"] = "idle"
                
                cursor.execute("SELECT pk_encrypted FROM solana_burner_wallet WHERE user_id = ?", (user_id,))
                wallet_row = cursor.fetchone()
                if wallet_row and wallet_row[0]:
                    try:
                        decrypted_pk = self.cipher.decrypt(wallet_row[0].encode()).decode() if self.cipher else wallet_row[0]
                        state["wallet"] = decrypted_pk
                    except Exception as dec_err:
                        self.logger.error(f"Erro ao descriptografar carteira Solana (User {user_id}): {dec_err}")
                        state["wallet"] = None
                else:
                    state["wallet"] = None
                    
            return True
        except Exception as e:
            self.logger.error(f"Erro ao ler banco de dados para user {user_id}: {e}")
            return False

    def _load_tracked_wallets_from_db(self, user_id):
        """Carrega as carteiras de Copy Trading rastreadas pelo usuário (tabela
        tracked_wallets, gerenciada via /api/solana/tracked-wallets em server.py)."""
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        state = self._get_user_state(user_id)
        state["tracked_wallets"] = []
        if not os.path.exists(db_path):
            return
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT wallet_address, label, is_active FROM tracked_wallets WHERE user_id = ?",
                    (user_id,)
                )
                state["tracked_wallets"] = [
                    {"wallet_address": row[0], "label": row[1], "is_active": bool(row[2])}
                    for row in cursor.fetchall()
                ]
        except Exception as e:
            self.logger.error(f"Erro ao carregar tracked_wallets para user {user_id}: {e}")

    def _is_blacklisted(self, creator_wallet):
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT 1 FROM creator_blacklist WHERE creator_wallet = ?', (creator_wallet,))
                if cursor.fetchone():
                    return True
        except Exception as e:
            self.logger.error(f"Erro ao consultar blacklist: {e}")
        return False

    def _add_to_blacklist(self, creator_wallet, reason=""):
        if not creator_wallet:
            return
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO creator_blacklist (creator_wallet, reason)
                    VALUES (?, ?)
                ''', (creator_wallet, reason))
                conn.commit()
                self.logger.info(f"🚫 [BLACKLIST] Criador {creator_wallet} inserido na lista negra. Motivo: {reason}")
        except Exception as e:
            self.logger.error(f"Erro ao adicionar na blacklist: {e}")

    def _save_user_is_active(self, user_id, is_active):
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO solana_sniper_configs (user_id, is_active)
                    VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET is_active = excluded.is_active
                """, (user_id, 1 if is_active else 0))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Erro ao salvar is_active da Solana no BD para user {user_id}: {e}")

    def _load_all_user_configs(self):
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        if not os.path.exists(db_path):
            return
            
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE solana_sniper_configs SET is_active = 0")
                conn.commit()
                
                cursor.execute("SELECT user_id FROM solana_sniper_configs")
                rows = cursor.fetchall()
                for row in rows:
                    user_id = row[0]
                    self._load_user_config_from_db(user_id)
            self.logger.info(f"🟢 [COFRE] Configurações de {len(rows)} usuários carregadas no Solana Core.")
        except Exception as e:
            self.logger.error(f"Erro ao carregar todas as configs no startup: {e}")

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

    async def _rpc_call_with_retry(self, session, url, payload, max_retries=5, base_delay=0.5, user_id=None):
        for attempt in range(max_retries):
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 429:
                        delay = base_delay * (2 ** attempt)
                        msg = f"⚠️ Helius Rate Limit (429) atingido. Retentando em {delay}s... (Tentativa {attempt+1}/{max_retries})"
                        if user_id:
                            await self.log_to_user(user_id, "WARN", msg)
                        else:
                            self.logger.warning(msg)
                        await asyncio.sleep(delay)
                        continue
                    
                    if resp.status != 200:
                        text = await resp.text()
                        msg = f"RPC Error {resp.status}: {text}"
                        if user_id:
                            await self.log_to_user(user_id, "ERROR", msg)
                        self.logger.error(msg)
                        return None
                        
                    return await resp.json()
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Attempt to decode JSON" in err_str or "Connection reset" in err_str:
                    delay = base_delay * (2 ** attempt)
                    msg = f"⚠️ Falha no RPC (Possível 429 ou erro de rede). Retentando em {delay}s... ({err_str})"
                    if user_id:
                        await self.log_to_user(user_id, "WARN", msg)
                    else:
                        self.logger.warning(msg)
                    await asyncio.sleep(delay)
                    continue
                else:
                    self.logger.error(f"Erro inesperado no RPC: {e}")
                    break
        return None

    async def _get_sol_balance(self, pubkey_str, session, rpc_url, user_id=None):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBalance",
            "params": [pubkey_str]
        }
        result = await self._rpc_call_with_retry(session, rpc_url, payload, user_id=user_id)
        if result and "result" in result and "value" in result["result"]:
            return result["result"]["value"] / 1_000_000_000
        return 0.0

    async def _get_token_balance(self, pubkey_str, mint, session, rpc_url, user_id=None):
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [pubkey_str, {"mint": mint}, {"encoding": "jsonParsed"}]
        }
        result = await self._rpc_call_with_retry(session, rpc_url, payload, user_id=user_id)
        if result and "result" in result and "value" in result["result"]:
            accounts = result["result"]["value"]
            if accounts:
                try:
                    amount = accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]
                    return float(amount)
                except (KeyError, IndexError, TypeError):
                    pass
        return 0.0

    async def _get_pump_token_price(self, mint, session, rpc_url=None):
        if not rpc_url:
            rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=eff46054-caa6-4e08-8731-e9abad96e5d2")
        
        try:
            from solders.pubkey import Pubkey
            import base64
            import struct
            mint_pk = Pubkey.from_string(mint)
            program_pk = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
            pda, _ = Pubkey.find_program_address([b"bonding-curve", bytes(mint_pk)], program_pk)
            
            payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getAccountInfo",
                "params": [str(pda), {"encoding": "base64"}]
            }
            async with session.post(rpc_url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "result" in data and data["result"]["value"]:
                        b64_data = data["result"]["value"]["data"][0]
                        raw_bytes = base64.b64decode(b64_data)
                        if len(raw_bytes) >= 40:
                            v_tokens = struct.unpack("<Q", raw_bytes[8:16])[0]
                            v_sol = struct.unpack("<Q", raw_bytes[16:24])[0]
                            if v_tokens > 0:
                                return (v_sol / 1e9) / (v_tokens / 1e6)
        except Exception as e:
            pass
            
        try:
            async with session.get(f"https://frontend-api.pump.fun/coins/{mint}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sol_reserves = data.get("virtual_sol_reserves", 0)
                    token_reserves = data.get("virtual_token_reserves", 0)
                    if token_reserves > 0:
                        return (sol_reserves / 1e9) / (token_reserves / 1e6)
        except Exception:
            pass
            
        return None

    async def _wait_for_tx_confirmation(self, signature, session, rpc_url, user_id):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignatureStatuses",
            "params": [
                [signature],
                {"searchTransactionHistory": True}
            ]
        }
        retries = 0
        while retries < 30:
            await asyncio.sleep(1)
            result = await self._rpc_call_with_retry(session, rpc_url, payload, user_id=user_id, max_retries=2, base_delay=0.5)
            if result:
                status = result.get("result", {}).get("value", [None])[0]
                if status is not None:
                    if status.get("err") is not None:
                        await self.log_to_user(user_id, "ERROR", f"❌ Transação falhou na rede: {status.get('err')}")
                        return False
                    confirmation_status = status.get("confirmationStatus")
                    if confirmation_status in ["confirmed", "finalized"]:
                        return True
            retries += 1
            
        await self.log_to_user(user_id, "WARN", "Tempo esgotado aguardando confirmação via signature status.")
        return False

    async def _wait_for_balance_change(self, pubkey_str, initial_balance, is_buy, session, rpc_url, user_id):
        retries = 0
        current_balance = initial_balance
        while retries < 30:
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
        
        for _ in range(10):
            try:
                async with session.post(rpc_url, json=payload) as resp:
                    data = await resp.json()
                    if "result" in data and data["result"]:
                        meta = data["result"].get("meta", {})
                        post_token_balances = meta.get("postTokenBalances", [])
                        if post_token_balances:
                            return post_token_balances[0].get("mint")
            except Exception:
                pass
            await asyncio.sleep(1)
            
        return None

    async def log_to_user(self, user_id, level, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        await self.broadcast_to_user(user_id, {
            "type": "log",
            "log": f"[{timestamp}] [{level}] {message}"
        })
        self.logger.info(f"[User {user_id}] [{level}] {message}")

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
                cursor.execute(f'''
                    SELECT 
                        SUM(net_pnl_usd) as daily_pnl_usd,
                        SUM(net_pnl_sol) as daily_pnl_sol,
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN is_win THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN NOT is_win THEN 1 ELSE 0 END) as losses
                    FROM {self.history_table}
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
            self.logger.error(f"Erro ao ler estatísticas do BD para user {user_id}: {e}")
            
        return stats

    def _save_trade_history(self, user_id, token_mint, sol_spent, sol_received, jito_tip_buy, jito_tip_sell, is_win, sol_price_usd=150.0):
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        net_pnl_sol = sol_received - sol_spent
        net_pnl_usd = net_pnl_sol * sol_price_usd
        
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f'''
                    INSERT INTO {self.history_table} (
                        user_id, token_mint, sol_spent, sol_received, 
                        jito_tip_buy, jito_tip_sell, net_pnl_sol, net_pnl_usd, is_win
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, token_mint, sol_spent, sol_received, jito_tip_buy, jito_tip_sell, net_pnl_sol, net_pnl_usd, is_win))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Erro ao salvar histórico do BD para user {user_id}: {e}")

    def _get_trade_history_from_db(self, user_id, limit=20):
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        history = []
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(f'''
                    SELECT token_mint, sol_spent, sol_received, net_pnl_sol, is_win, created_at 
                    FROM {self.history_table} 
                    WHERE user_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (user_id, limit))
                rows = cursor.fetchall()
                for row in rows:
                    history.append(dict(row))
        except Exception as e:
            self.logger.error(f"Erro ao ler historico para user {user_id}: {e}")
        return history

    async def broadcast_history(self, user_id):
        history = self._get_trade_history_from_db(user_id)
        await self.broadcast_to_user(user_id, {
            "type": "HISTORY_UPDATE",
            "history": history
        })

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
        self.logger.info("🔌 [WS] Nova conexão solicitada. Aguardando autenticação JWT...")
        
        try:
            try:
                auth_message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                auth_data = json.loads(auth_message)
                
                if auth_data.get("type") == "auth" and auth_data.get("token"):
                    token = auth_data.get("token")
                    try:
                        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                        websocket.user_id = int(payload.get("sub"))
                        self.logger.info(f"✅ [WS] Cliente autenticado (User ID: {websocket.user_id})")
                    except Exception as e:
                        self.logger.warning(f"❌ [WS] Erro JWT: {e}. Cliente desconectado.")
                        await websocket.close(code=4001, reason="JWT Error")
                        return
                else:
                    self.logger.warning("⚠️ [WS] Primeira mensagem não foi de autenticação. Desconectando.")
                    await websocket.close(code=4001, reason="Auth required")
                    return
            except asyncio.TimeoutError:
                self.logger.info("ℹ️ [WS] Tempo esgotado para autenticação. Desconectando.")
                await websocket.close(code=4001, reason="Timeout")
                return

            self.connected_clients.add(websocket)
            user_id = websocket.user_id
            
            self._load_user_config_from_db(user_id)
            state = self._get_user_state(user_id)
            
            await websocket.send(json.dumps({
                "type": "config",
                **state["config"],
                "is_active": state["is_active"]
            }))
            
            await self.broadcast_metrics(user_id)
            await self.broadcast_history(user_id)
            
            async for message in websocket:
                data = json.loads(message)
                
                if data.get("type") == "start":
                    self._load_user_config_from_db(user_id)
                    state = self._get_user_state(user_id)
                    
                    target_token = state["config"].get("target_token")
                        
                    if not state["wallet"]:
                        await self.log_to_user(user_id, "ERROR", "Nenhuma carteira Solana (Burner Wallet) cadastrada.")
                        continue
                        
                    state["config"]["status"] = "watching"
                    state["is_active"] = True
                    self._save_user_is_active(user_id, True)
                    
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
                    self._save_user_is_active(user_id, False)
                    await self.log_to_user(user_id, "WARN", "⏸️ Monitoramento pausado pelo usuário.")
                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                    
                elif data.get("type") == "reset_wallet":
                    state = self._get_user_state(user_id)
                    state["wallet"] = None
                    state["is_active"] = False
                    state["config"]["status"] = "idle"
                    self._save_user_is_active(user_id, False)
                    await self.log_to_user(user_id, "WARN", "🗑️ Carteira Solana apagada. Monitoramento interrompido.")
                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                    
                elif data.get("type") == "reset_config":
                    state = self._get_user_state(user_id)
                    state["config"]["target_token"] = ""
                    state["is_active"] = False
                    state["config"]["status"] = "idle"
                    self._save_user_is_active(user_id, False)
                    await self.log_to_user(user_id, "WARN", "🗑️ Token Alvo apagado. Monitoramento interrompido.")
                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})

                elif data.get("type") == "force_buy":
                    token_to_buy = data.get("token")
                    force_entry = data.get("force_entry", True)
                    if not token_to_buy:
                        await self.log_to_user(user_id, "ERROR", "Nenhum token fornecido para compra manual.")
                        continue
                    state = self._get_user_state(user_id)
                    if not state["wallet"]:
                        await self.log_to_user(user_id, "ERROR", "Nenhuma carteira Solana (Burner Wallet) cadastrada.")
                        continue
                    
                    await self.log_to_user(user_id, "WARN", f"⚡ Invocando COMPRA MANUAL para o token: {token_to_buy}")
                    if hasattr(self, 'handle_snipe_and_monitor'):
                        asyncio.create_task(self.handle_snipe_and_monitor(user_id, state, token_to_buy, force_entry=force_entry))

                elif data.get("type") == "force_sell":
                    token_to_sell = data.get("token")
                    is_panic = data.get("is_panic", False)
                    if not token_to_sell:
                        await self.log_to_user(user_id, "ERROR", "Nenhum token fornecido para venda manual.")
                        continue
                    state = self._get_user_state(user_id)
                    if not state["wallet"]:
                        await self.log_to_user(user_id, "ERROR", "Nenhuma carteira Solana (Burner Wallet) cadastrada.")
                        continue
                    
                    await self.log_to_user(user_id, "WARN", f"🔴 Invocando VENDA MANUAL (DUMP) para o token: {token_to_sell}")
                    asyncio.create_task(self.execute_real_sell(user_id, state, token_to_sell, is_panic=is_panic))

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            self.logger.error(f"WS Error: {e}")
        finally:
            if websocket in self.connected_clients:
                self.connected_clients.remove(websocket)

    async def execute_real_sell(self, user_id, state, token_mint, is_panic=False, sell_fraction=1.0):
        try:
            if state.get("open_positions", {}).get(token_mint, {}).get("sell_pending"):
                await self.log_to_user(user_id, "WARN", f"⚠️ Venda de {token_mint} já está em andamento. Ignorando tentativa duplicada.")
                return False
                
            wallet_pk_str = state.get("wallet")
            if not wallet_pk_str:
                return False

            if token_mint in state.get("open_positions", {}):
                state["open_positions"][token_mint]["sell_pending"] = True

            try:
                if wallet_pk_str.startswith("["):
                    key_bytes = bytes(json.loads(wallet_pk_str))
                    payer = Keypair.from_bytes(key_bytes)
                else:
                    payer = Keypair.from_bytes(base58.b58decode(wallet_pk_str))
            except Exception as e:
                await self.log_to_user(user_id, "ERROR", f"Erro ao decodificar chave privada: {e}")
                if token_mint in state.get("open_positions", {}):
                    state["open_positions"][token_mint]["sell_pending"] = False
                return False

            jito_tip_sol = float(state["config"]["jito_tip"])
            slippage = float(state["config"]["slippage"])

            if is_panic:
                slippage = min(slippage * 3.0, 50.0)
                jito_tip_sol *= 2.0
                await self.log_to_user(user_id, "WARN", f"⚡ [PANIC SELL] Slippage ajustada para {slippage}% e Jito Tip para {jito_tip_sol} SOL")


            await self.log_to_user(user_id, "WARN", f"🔴 Construindo transação de VENDA (PumpPortal) para {token_mint}...")
            
            payload = {
                "publicKey": str(payer.pubkey()),
                "action": "sell",
                "mint": token_mint.strip(),
                "amount": f"{int(sell_fraction * 100)}%",
                "denominatedInSol": "false",
                "slippage": int(slippage),
                "priorityFee": float(jito_tip_sol),
                "pool": "pump"
            }

            rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=eff46054-caa6-4e08-8731-e9abad96e5d2")
            async with aiohttp.ClientSession() as session:
                payer_pubkey_str = str(payer.pubkey())
                balance_before = await self._get_sol_balance(payer_pubkey_str, session, rpc_url, user_id=user_id)
                await self.log_to_user(user_id, "INFO", f"💳 Saldo inicial antes da venda: {balance_before:.5f} SOL")
                
                token_balance = await self._get_token_balance(payer_pubkey_str, token_mint, session, rpc_url, user_id=user_id)
                await self.log_to_user(user_id, "INFO", f"🪙 Saldo de tokens antes da venda: {token_balance:.2f} {token_mint[:4]}")
                if token_balance <= 0:
                    await self.log_to_user(user_id, "ERROR", f"❌ Saldo insuficiente do token {token_mint} na carteira. Venda cancelada.")
                    if token_mint in state.get("open_positions", {}):
                        state["open_positions"][token_mint]["sell_pending"] = False
                    return False
                
                async with session.post("https://pumpportal.fun/api/trade-local", json=payload) as response:
                    if response.status != 200:
                        err_text = await response.text()
                        await self.log_to_user(user_id, "ERROR", f"Falha na API PumpPortal (Venda): {err_text}")
                        if token_mint in state.get("open_positions", {}):
                            state["open_positions"][token_mint]["sell_pending"] = False
                        return False
                    tx_bytes = await response.read()

                transaction = VersionedTransaction.from_bytes(tx_bytes)
                signed_tx = VersionedTransaction(transaction.message, [payer])
                
                await self.log_to_user(user_id, "WARN", "🚀 Disparando transação de VENDA assinada para a rede (Helius/Jito)...")
                
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
                            "maxRetries": 0
                        }
                    ]
                }
                
                rpc_result = await self._rpc_call_with_retry(session, rpc_url, rpc_payload, user_id=user_id, max_retries=5)
                if rpc_result and "result" in rpc_result:
                    tx_sig = rpc_result["result"]
                    await self.log_to_user(user_id, "INFO", f"✅ Venda disparada! TX: {tx_sig}")
                    
                    await self.log_to_user(user_id, "INFO", "⏳ Aguardando confirmação na blockchain (Signature Status)...")
                    is_confirmed = await self._wait_for_tx_confirmation(tx_sig, session, rpc_url, user_id)
                    
                    if not is_confirmed:
                        await self.log_to_user(user_id, "WARN", "⚠️ [TIMEOUT] A rede demorou para confirmar o status da assinatura. Assumindo fechamento provisório para evitar spam infinito.")
                        
                    if sell_fraction < 1.0:
                        if token_mint in state.get("open_positions", {}):
                            state["open_positions"][token_mint]["sell_pending"] = False
                        return True

                    await asyncio.sleep(2)
                    balance_after = await self._get_sol_balance(payer_pubkey_str, session, rpc_url, user_id=user_id)
                    sol_received = balance_after - balance_before
                    
                    if sol_received <= 0:
                        await self.log_to_user(user_id, "WARN", "⚠️ Venda confirmada, mas o RPC ainda não atualizou o saldo final corretamente. Assumindo fechamento bem-sucedido.")
                        sol_received = 0.0
                        
                    await self.log_to_user(user_id, "INFO", f"💸 Saldo pós-venda: {balance_after:.5f} SOL | Receita calculada: {sol_received:.5f} SOL")
                    
                    pos_data = state["open_positions"].get(token_mint, {})
                    sol_spent = pos_data.get("sol_spent", 0.0)
                    jito_tip_buy = pos_data.get("jito_tip_buy", 0.0)
                    
                    pnl_pct = pos_data.get("pnl_pct", 0.0)
                    
                    if sol_spent == 0:
                        is_win = sol_received > (jito_tip_buy + jito_tip_sol) or pnl_pct > 0
                    else:
                        is_win = sol_received > sol_spent or pnl_pct > 0
                        
                    sol_price_usd = 150.0
                    try:
                        async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT") as price_resp:
                            if price_resp.status == 200:
                                price_data = await price_resp.json()
                                sol_price_usd = float(price_data.get("price", 150.0))
                    except Exception as e:
                        self.logger.error(f"Erro ao buscar preço do SOL na Binance: {e}")
                        
                    self._save_trade_history(
                        user_id=user_id,
                        token_mint=token_mint,
                        sol_spent=sol_spent,
                        sol_received=sol_received,
                        jito_tip_buy=jito_tip_buy,
                        jito_tip_sell=jito_tip_sol,
                        is_win=is_win,
                        sol_price_usd=sol_price_usd
                    )
                    
                    if is_win:
                        profit_sol = sol_received - sol_spent if sol_received > 0 else (sol_spent * (pnl_pct / 100.0))
                        await self.broadcast_to_user(user_id, {
                            "type": "trade_win",
                            "profit_sol": profit_sol,
                            "pnl_pct": pnl_pct,
                            "token_mint": token_mint
                        })
                    
                    if token_mint in state["open_positions"]:
                        del state["open_positions"][token_mint]
                        
                    state["config"]["status"] = "idle"
                    await self.broadcast_metrics(user_id)
                    await self.broadcast_history(user_id)
                    await self.broadcast_positions(user_id)
                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                    return True
                else:
                    err_msg = rpc_result.get("error", "Erro desconhecido")
                    await self.log_to_user(user_id, "ERROR", f"A rede recusou a transação de venda: {err_msg}")
                    return False

        except Exception as e:
            await self.log_to_user(user_id, "ERROR", f"Falha crítica ao executar venda real: {e}")
            self.logger.error(traceback.format_exc())
            return False

    async def _read_bonding_curve(self, mint: str, session: aiohttp.ClientSession, rpc_url: str,
                                   max_retries: int = 2, timeout: float = 0.6, retry_delay: float = 0.15) -> dict:
        """
        [FIX] Leitura ÚNICA e compartilhada da conta de Bonding Curve da Pump.fun.

        Antes, pre_buy_validation e _check_token_freshness faziam CADA UMA a sua
        própria chamada getAccountInfo pra essa MESMA conta, em sequência, dentro
        do caminho crítico de uma única compra — dobrando a latência e a pressão
        de rate-limit na Helius bem no momento em que velocidade importa mais.
        Agora execute_real_snipe lê a conta uma única vez (em paralelo com a
        busca de saldo) e reaproveita o resultado nas duas validações.

        Retorna: {"found": bool, "v_sol": float|None, "v_tokens": int|None,
                  "raw_len": int, "error": str|None}
        "found" = a conta existe e foi lida (mesmo que o payload esteja corrompido).
        "error" quando presente descreve o motivo de não ter dados utilizáveis
        ("not_found", "corrupted", "timeout", "http_<code>", "max_retries").
        """
        result = {"found": False, "v_sol": None, "v_tokens": None, "raw_len": 0, "error": None}
        try:
            from solders.pubkey import Pubkey
            import base64
            import struct

            mint_pk = Pubkey.from_string(mint)
            program_pk = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
            pda, _ = Pubkey.find_program_address([b"bonding-curve", bytes(mint_pk)], program_pk)

            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [str(pda), {"encoding": "base64"}]
            }

            for attempt in range(max_retries):
                try:
                    async with session.post(rpc_url, json=payload, timeout=timeout) as resp:
                        if resp.status != 200:
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay)
                                continue
                            result["error"] = f"http_{resp.status}"
                            return result

                        data = await resp.json()

                        if "result" not in data or not data["result"]["value"]:
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay)
                                continue
                            result["error"] = "not_found"
                            return result

                        b64_data = data["result"]["value"]["data"][0]
                        raw_bytes = base64.b64decode(b64_data)
                        result["raw_len"] = len(raw_bytes)

                        if len(raw_bytes) < 40:
                            result["found"] = True
                            result["error"] = "corrupted"
                            return result

                        result["found"] = True
                        result["v_tokens"] = struct.unpack("<Q", raw_bytes[8:16])[0]
                        result["v_sol"] = struct.unpack("<Q", raw_bytes[16:24])[0] / 1e9
                        return result
                except (asyncio.TimeoutError, aiohttp.ClientError):
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    result["error"] = "timeout"
                    return result

            result["error"] = "max_retries"
            return result
        except Exception as e:
            result["error"] = f"exception:{e}"
            return result

    def evaluate_pre_buy(self, curve: dict, min_liquidity_sol: float = 15.0) -> tuple[bool, str]:
        """
        [Validação Pré-Compra de Segurança]
        Avalia o resultado de _read_bonding_curve contra as regras de segurança
        pré-compra (payload íntegro, reservas não-zeradas, liquidez mínima).
        Não faz I/O — recebe a leitura já pronta, feita uma única vez por
        execute_real_snipe e reaproveitada também por evaluate_freshness.

        [FIX] "Conta ainda não propagou no RPC" (found=False) NÃO é mais tratado
        como falha fatal — é o sinal normal de bloco zero (o logsSubscribe da
        Helius avisa do InitializeMint2 antes de outro nó RPC conseguir responder
        getAccountInfo pra essa mesma conta). Isso já travava quase 100% das
        tentativas de snipe em modo Global antes desta correção. Só payload
        corrompido, reservas zeradas ou liquidez abaixo do mínimo (numa conta que
        EXISTE) continuam sendo abortamento real.
        """
        if curve.get("error") == "corrupted":
            return False, f"Payload corrompido: Estrutura de dados muito curta ({curve.get('raw_len', 0)} bytes)."

        if not curve.get("found"):
            return True, "Bloco zero: conta ainda não propagou no RPC (Modo Tolerante)."

        if curve.get("v_tokens") == 0:
            return False, "Reservas de tokens zeradas (Liquidez Drenada/Inválida)."

        v_sol = curve.get("v_sol")
        if v_sol is None:
            return True, "Dados de liquidez indisponíveis — Modo Tolerante."

        if v_sol < min_liquidity_sol:
            return False, f"Liquidez Insuficiente: {v_sol:.2f} SOL detectados (Mínimo exigido: {min_liquidity_sol:.2f} SOL)."

        return True, f"Token Saudável (Liquidez: {v_sol:.2f} SOL / Integridade: OK)."

    async def execute_real_snipe(self, user_id, state, token_mint):
        try:
            wallet_pk_str = state.get("wallet")
            if not wallet_pk_str:
                await self.log_to_user(user_id, "ERROR", "Carteira Burner não encontrada para assinatura.")
                return False

            try:
                if wallet_pk_str.startswith("["):
                    key_bytes = bytes(json.loads(wallet_pk_str))
                    payer = Keypair.from_bytes(key_bytes)
                else:
                    payer = Keypair.from_bytes(base58.b58decode(wallet_pk_str))
            except Exception as e:
                await self.log_to_user(user_id, "ERROR", f"Erro ao decodificar chave privada da Burner Wallet: {e}")
                return False

            await self.log_to_user(user_id, "INFO", f"🔑 Carteira carregada: {payer.pubkey()}")

            slippage = float(state["config"]["slippage"])
            buy_amount_sol = float(state["config"].get("trade_amount", 0.005))
            
            # --- GESTÃO DE RISCO: Aporte Mínimo e Proteção de Jito Tip ---
            min_trade_amount_sol = float(state["config"].get("min_trade_amount_sol", 0.02))
            if buy_amount_sol < min_trade_amount_sol:
                await self.log_to_user(user_id, "ERROR", f"🛑 COMPRA ABORTADA: Aporte ({buy_amount_sol} SOL) menor que o limite seguro. Mínimo: {min_trade_amount_sol} SOL.")
                return False

            jito_tip_sol = float(state["config"]["jito_tip"])
            max_jito_tip_pct = 0.10 # Max 10% do valor da compra
            max_allowed_tip = buy_amount_sol * max_jito_tip_pct
            if jito_tip_sol > max_allowed_tip:
                await self.log_to_user(user_id, "WARN", f"⚠️ Jito Tip ({jito_tip_sol} SOL) excede {max_jito_tip_pct*100}% do aporte de {buy_amount_sol} SOL. Ajustando para {max_allowed_tip:.4f} SOL para proteger capital.")
                jito_tip_sol = max_allowed_tip
            # -------------------------------------------------------------

            rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=eff46054-caa6-4e08-8731-e9abad96e5d2")
            async with aiohttp.ClientSession() as session:

                payer_pubkey_str = str(payer.pubkey())

                # --- LEITURA ÚNICA DA BONDING CURVE ---
                # [FIX] Antes, a validação pré-compra e o filtro de frescor faziam
                # CADA UM sua própria chamada getAccountInfo pra essa MESMA conta,
                # em sequência — dobrando a latência e a pressão de rate-limit no
                # caminho crítico de toda compra. Agora é uma leitura só, em
                # paralelo com a busca de saldo, reaproveitada pelas duas checagens.
                balance_task = asyncio.create_task(self._get_sol_balance(payer_pubkey_str, session, rpc_url))
                curve_task = asyncio.create_task(self._read_bonding_curve(token_mint, session, rpc_url))
                balance_before, curve = await asyncio.gather(balance_task, curve_task)

                # --- VALIDAÇÃO PRÉ-COMPRA ---
                min_liquidity = state.get("config", {}).get("min_liquidity_sol", 15.0)
                is_valid, validation_msg = self.evaluate_pre_buy(curve, min_liquidity_sol=min_liquidity)
                if not is_valid:
                    await self.log_to_user(user_id, "WARN", f"🛑 COMPRA ABORTADA (PRÉ-CHECK): {validation_msg}")
                    return False

                await self.log_to_user(user_id, "INFO", f"✅ [PRÉ-CHECK PASSOU] {validation_msg}")
                # ----------------------------

                anti_delay_filter = state.get("config", {}).get("anti_delay_filter", True)
                max_bonding_curve = state.get("config", {}).get("max_bonding_curve", 20.0)

                # Check se foi disparado por um sistema que possui freshness (global sniper)
                # Copy sniper tbm vai se beneficiar dessa checagem, mas vamos colocar um bypass para copy trading se quisermos
                is_fresh, fresh_msg = True, "Freshness ignorado para este bot"
                if hasattr(self, 'evaluate_freshness'):
                    is_fresh, fresh_msg = self.evaluate_freshness(curve, anti_delay_filter, max_bonding_curve)
                
                if not is_fresh:
                    await self.log_to_user(user_id, "WARN", f"🚫 [FILTRO ANTI-ATRASO] {fresh_msg} Compra abortada para evitar dump instantâneo.")
                    return False
                    
                await self.log_to_user(user_id, "INFO", f"💳 Saldo disponível: {balance_before:.5f} SOL | ✨ {fresh_msg}")
                
                required_balance = buy_amount_sol + jito_tip_sol + 0.002
                if balance_before < required_balance:
                    await self.log_to_user(user_id, "ERROR", f"❌ Saldo insuficiente! Requerido: ~{required_balance:.5f} SOL | Atual: {balance_before:.5f} SOL. Abortando compra para proteger a carteira.")
                    return False

                await self.log_to_user(user_id, "WARN", f"🔥 Construindo transação atômica (PumpPortal) para {token_mint} | Valor: {buy_amount_sol} SOL...")
                
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

                self.logger.debug(f"[User {user_id}] Solicitando transação à PumpPortal para {token_mint} com payload: {payload}")
                try:
                    async with session.post("https://pumpportal.fun/api/trade-local", json=payload, timeout=3.0) as response:
                        if response.status != 200:
                            err_text = await response.text()
                            await self.log_to_user(user_id, "ERROR", f"Falha na API PumpPortal (Status {response.status}): {err_text}")
                            return False
                        tx_bytes = await response.read()
                except asyncio.TimeoutError:
                    await self.log_to_user(user_id, "ERROR", "Falha Crítica: Timeout (3s) na API PumpPortal ao construir transação.")
                    return False
                except Exception as e:
                    await self.log_to_user(user_id, "ERROR", f"Falha Crítica: Erro ao contatar PumpPortal: {e}")
                    return False
                
                self.logger.debug(f"[User {user_id}] Transação recebida da PumpPortal. Decodificando...")

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
                            "maxRetries": 0
                        }
                    ]
                }
                
                self.logger.debug(f"[User {user_id}] Enviando transação assinada para {rpc_url}...")
                try:
                    async with session.post(rpc_url, json=rpc_payload, timeout=3.0) as rpc_resp:
                        rpc_result = await rpc_resp.json()
                        
                        if "result" in rpc_result:
                            tx_sig = rpc_result["result"]
                            await self.log_to_user(user_id, "INFO", f"✅ Transação de compra disparada! TX: {tx_sig}")
                            self.logger.debug(f"[User {user_id}] Transação enviada com sucesso. Assinatura: {tx_sig}")

                            await self.log_to_user(user_id, "INFO", "⏳ Aguardando confirmação (mudança de saldo)...")
                            balance_after = await self._wait_for_balance_change(payer_pubkey_str, balance_before, True, session, rpc_url, user_id)

                            sol_spent = balance_before - balance_after
                            if sol_spent <= 0:
                                await self.log_to_user(user_id, "ERROR", "❌ [FALHA] Saldo inalterado ou timeout da RPC. A transação falhou na rede Solana. Abortando trade fantasma.")
                                return False

                            await self.log_to_user(user_id, "INFO", f"💸 Saldo final: {balance_after:.5f} SOL | Custo Real: {sol_spent:.5f} SOL")

                            state["open_positions"][token_mint] = {
                                "sol_spent": sol_spent,
                                "buy_amount_sol": buy_amount_sol,
                                "jito_tip_buy": jito_tip_sol
                            }

                            return True
                        else:
                            err_msg = rpc_result.get("error", "Erro desconhecido")
                            await self.log_to_user(user_id, "ERROR", f"A rede retornou erro ao enviar a transação de compra: {err_msg}")
                            self.logger.debug(f"[User {user_id}] Erro da RPC ao enviar transação: {err_msg}")
                            return False
                except asyncio.TimeoutError:
                    await self.log_to_user(user_id, "ERROR", "Falha Crítica: Timeout (3s) na RPC da Helius ao enviar transação de compra.")
                    return False
                except Exception as e:
                    await self.log_to_user(user_id, "ERROR", f"Falha Crítica: Erro de conexão com RPC Helius: {e}")
                    return False

        except Exception as e:
            await self.log_to_user(user_id, "ERROR", f"Falha crítica ao executar snipe real: {e}")
            self.logger.error(f"[User {user_id}] Stack trace detalhada do erro em execute_real_snipe:")
            self.logger.error(traceback.format_exc())
            return False

    async def _get_dynamic_metrics(self, mint, session, rpc_url):
        try:
            from solders.pubkey import Pubkey
            import base64
            import struct
            mint_pk = Pubkey.from_string(mint)
            program_pk = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
            pda, _ = Pubkey.find_program_address([b"bonding-curve", bytes(mint_pk)], program_pk)
            
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo", "params": [str(pda), {"encoding": "base64"}]}
            async with session.post(rpc_url, json=payload, timeout=2.0) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "result" in data and data["result"]["value"]:
                        b64_data = data["result"]["value"]["data"][0]
                        raw_bytes = base64.b64decode(b64_data)
                        if len(raw_bytes) >= 40:
                            v_sol = struct.unpack("<Q", raw_bytes[16:24])[0]
                            v_sol_normalized = v_sol / 1e9
                            
                            sol_price = 150.0
                            try:
                                async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT", timeout=1.0) as price_resp:
                                    if price_resp.status == 200:
                                        p_data = await price_resp.json()
                                        sol_price = float(p_data.get("price", 150.0))
                            except: pass
                            
                            calculated_mcap = (v_sol_normalized / 1.073) * sol_price
                            estimated_vol = v_sol_normalized
                            return calculated_mcap, estimated_vol
        except Exception:
            pass
        return 0.0, 0.0

    async def monitor_position(self, user_id, entry_price_sol, token_mint="TOKEN_DEFAULT"):
        state = self._get_user_state(user_id)
        target_token = token_mint
        tp_pct = float(state["config"].get("tp_pct", 20.0))
        sl_pct = float(state["config"].get("sl_pct", 10.0))
        
        await self.log_to_user(user_id, "INFO", f"📈 Iniciando rastreamento de posição para {target_token}...")
        
        partial_tp_pct = tp_pct / 2.0
        await self.log_to_user(user_id, "WARN", f"🎯 Alvos definidos: Parcial (+{partial_tp_pct:.1f}%) | Final (+{tp_pct}%) | Stop-Loss (-{sl_pct}%)")
        
        current_price = entry_price_sol

        # [FIX] Suavização do Stop-Loss: antes, um único tick de preço abaixo do SL
        # disparava a venda de pânico na hora. Num token com dezenas de bots operando
        # no mesmo bloco, isso vende no primeiro flicker (ruído), não num dump real.
        SL_GRACE_PERIOD_SECONDS = 2.0   # nos primeiros segundos, só o corte catastrófico protege
        CATASTROPHIC_SL_PCT = 85.0      # corte de emergência: sempre ativo, mesmo durante a carência
        SL_CONFIRM_TICKS = 3            # fora da carência, exige N leituras seguidas abaixo do SL
        pnl_history = []
        entry_time = datetime.now()

        # Fetch metadata from Pump.fun
        metadata = {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://frontend-api.pump.fun/coins/{target_token}", timeout=2.0) as resp:
                    if resp.status == 200:
                        metadata = await resp.json()
        except:
            pass

        mcap = metadata.get("usd_market_cap", 0.0)
        volume = metadata.get("volume", 0.0)
        
        if not mcap or mcap == 0.0:
            try:
                async with aiohttp.ClientSession() as dyn_session:
                    dyn_mcap, dyn_vol = await self._get_dynamic_metrics(target_token, dyn_session, rpc_url)
                    if dyn_mcap > 0:
                        mcap = dyn_mcap
                    if not volume or volume == 0.0:
                        volume = dyn_vol
            except:
                pass

        name = metadata.get("name")
        symbol = metadata.get("symbol")
        
        if not name or name == "???":
            name = f"Pump-{target_token[:4]}"
        if not symbol or symbol == "???":
            symbol = f"PUMP"

        if target_token not in state["open_positions"]:
            state["open_positions"][target_token] = {}
            
        state["open_positions"][target_token].update({
            "token": target_token,
            "name": name,
            "symbol": symbol,
            "image_uri": metadata.get("image_uri", ""),
            "usd_market_cap": mcap,
            "volume": volume,
            "reply_count": metadata.get("reply_count", 0),
            "entry_price": entry_price_sol,
            "current_price": current_price,
            "pnl_pct": 0.0
        })
        await self.broadcast_positions(user_id)
        
        rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=eff46054-caa6-4e08-8731-e9abad96e5d2")
        
        wallet_pk_str = state.get("wallet")
        if wallet_pk_str:
            try:
                if wallet_pk_str.startswith("["):
                    key_bytes = bytes(json.loads(wallet_pk_str))
                    payer = Keypair.from_bytes(key_bytes)
                else:
                    payer = Keypair.from_bytes(base58.b58decode(wallet_pk_str))
                payer_pubkey_str = str(payer.pubkey())
            except:
                payer_pubkey_str = None
        else:
            payer_pubkey_str = None

        async with aiohttp.ClientSession() as session:
            token_balance = 0.0
            if payer_pubkey_str:
                token_balance = await self._get_token_balance(payer_pubkey_str, target_token, session, rpc_url)
                
            initial_price = await self._get_pump_token_price(target_token, session)
            if initial_price is not None and token_balance > 0:
                current_price = initial_price * token_balance

            # [FIX] Condição de corrida crítica em modo multi-posição (max_positions > 1):
            # "state['config']['status']" é UM campo global por usuário, compartilhado por
            # TODAS as posições simultâneas. Quando qualquer posição fechava (TP/SL), o
            # status virava "idle"/"watching" e esse while, usado por CADA task de
            # monitor_position (uma por posição aberta), saía do loop — matando o
            # rastreamento de SL/TP das OUTRAS posições ainda abertas, que ficavam sem
            # proteção nenhuma até o processo ser reiniciado. Agora cada task só encerra
            # quando a SUA própria posição sai de open_positions (por venda real).
            while state["is_active"] and target_token in state.get("open_positions", {}):
                try:
                    async with websockets.connect("wss://pumpportal.fun/api/data", ping_interval=30, ping_timeout=10) as ws:
                        subscribe_msg = {
                            "method": "subscribeTokenTrade",
                            "keys": [target_token]
                        }
                        await ws.send(json.dumps(subscribe_msg))

                        loops_since_last_poll = 0
                        while state["is_active"] and target_token in state.get("open_positions", {}):
                            if token_balance <= 0 and payer_pubkey_str:
                                new_balance = await self._get_token_balance(payer_pubkey_str, target_token, session, rpc_url)
                                if new_balance > 0:
                                    token_balance = new_balance
                                    fallback_price = await self._get_pump_token_price(target_token, session)
                                    if fallback_price is not None:
                                        current_price = fallback_price * token_balance
                                    
                            if state.get("open_positions", {}).get(target_token, {}).get("sell_pending"):
                                await asyncio.sleep(1)
                                continue

                            try:
                                message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                                data = json.loads(message)
                                
                                if data.get("mint") == target_token:
                                    v_sol = data.get("vSolInBondingCurve")
                                    v_tokens = data.get("vTokensInBondingCurve")
                                    if v_sol and v_tokens and v_tokens > 0:
                                        price_in_sol = float(v_sol) / float(v_tokens)
                                        if token_balance > 0:
                                            current_price = price_in_sol * token_balance
                                            loops_since_last_poll = 0
                            except asyncio.TimeoutError:
                                loops_since_last_poll += 1
                                if loops_since_last_poll >= 1:
                                    loops_since_last_poll = 0
                                    fallback_price = await self._get_pump_token_price(target_token, session)
                                    if fallback_price is not None and token_balance > 0:
                                        current_price = fallback_price * token_balance
                            except websockets.exceptions.ConnectionClosed:
                                self.logger.error("PumpPortal WS desconectado. Reconectando...")
                                break
                            except Exception as ws_err:
                                self.logger.error(f"Erro no Listener PumpPortal WS: {ws_err}")
                                await asyncio.sleep(1)
                                
                            if entry_price_sol > 0:
                                pnl_pct = ((current_price - entry_price_sol) / entry_price_sol) * 100
                            else:
                                pnl_pct = 0.0
                            
                            if target_token in state["open_positions"]:
                                state["open_positions"][target_token]["current_price"] = current_price
                                state["open_positions"][target_token]["pnl_pct"] = pnl_pct
                                await self.broadcast_positions(user_id)
                            
                            pos_state = state["open_positions"].get(target_token, {})
                            
                            if pnl_pct >= partial_tp_pct and not pos_state.get("partial_sold"):
                                await self.log_to_user(user_id, "INFO", f"💸 [TAKE PROFIT PARCIAL] Preço atingiu +{pnl_pct:.2f}%. Vendendo 50% da posição!")
                                state["open_positions"][target_token]["partial_sold"] = True
                                asyncio.create_task(self.execute_real_sell(user_id, state, target_token, is_panic=False, sell_fraction=0.5))
                                sl_pct = 0.0
                                await self.log_to_user(user_id, "WARN", f"🛡️ Stop-Loss movido para o preço de entrada (0%). Free roll ativado!")
                                pnl_history.clear()

                            elif pnl_pct >= tp_pct:
                                await self.log_to_user(user_id, "INFO", f"💰 [TAKE PROFIT FINAL] Preço atingiu +{pnl_pct:.2f}%. Disparando venda automática!")
                                asyncio.create_task(self.execute_real_sell(user_id, state, target_token, is_panic=False, sell_fraction=1.0))
                                pnl_history.clear()

                            elif pnl_pct <= -CATASTROPHIC_SL_PCT:
                                # [FIX] Corte catastrófico — dispara sempre, mesmo durante a carência (rug real)
                                await self.log_to_user(user_id, "ERROR", f"🛑 [STOP LOSS CATASTRÓFICO] Preço atingiu {pnl_pct:.2f}%. Disparando venda automática (emergência)!")
                                asyncio.create_task(self.execute_real_sell(user_id, state, target_token, is_panic=True))
                                
                                # Adicionar à Blacklist Automática
                                try:
                                    async with session.get(f"https://frontend-api.pump.fun/coins/{target_token}", timeout=2.0) as resp:
                                        if resp.status == 200:
                                            data = await resp.json()
                                            creator = data.get("creator")
                                            if creator:
                                                self._add_to_blacklist(creator, f"Stop-Loss Catastrófico ({pnl_pct:.2f}%)")
                                except Exception as e:
                                    self.logger.error(f"Erro ao buscar criador para blacklist: {e}")
                                    
                                pnl_history.clear()

                            elif pnl_pct <= -sl_pct:
                                # [FIX] Fora da carência inicial e só após N leituras seguidas confirmando
                                # a perda — evita vender no primeiro flicker de preço do bloco zero.
                                elapsed = (datetime.now() - entry_time).total_seconds()
                                if elapsed < SL_GRACE_PERIOD_SECONDS:
                                    pass  # ainda em carência: só o corte catastrófico acima protege a posição
                                else:
                                    pnl_history.append(pnl_pct)
                                    if len(pnl_history) > SL_CONFIRM_TICKS:
                                        pnl_history.pop(0)
                                    if len(pnl_history) >= SL_CONFIRM_TICKS and all(p <= -sl_pct for p in pnl_history):
                                        pos_state = state["open_positions"].get(target_token, {})
                                        
                                        if not pos_state.get("partial_sl_executed"):
                                            await self.log_to_user(user_id, "WARN", f"🛑 [STOP LOSS INTELIGENTE] Preço caiu para {pnl_pct:.2f}%. Despejando 50% da posição com baixo slippage para recuperar risco.")
                                            pos_state["partial_sl_executed"] = True
                                            pos_state["sl_relaxed_limit"] = sl_pct * 1.5
                                            asyncio.create_task(self.execute_real_sell(user_id, state, target_token, is_panic=False, sell_fraction=0.5))
                                            pnl_history.clear()
                                            
                                        elif pos_state.get("partial_sl_executed") and pnl_pct <= -pos_state.get("sl_relaxed_limit", sl_pct * 1.5):
                                            await self.log_to_user(user_id, "ERROR", f"🛑 [LIQUIDAÇÃO TOTAL] Sangria continuou ({pnl_pct:.2f}%). Despejando restante da posição a mercado!")
                                            asyncio.create_task(self.execute_real_sell(user_id, state, target_token, is_panic=True))
                                            pnl_history.clear()
                            else:
                                pnl_history.clear()
                                    
                except Exception as e:
                    self.logger.error(f"Falha ao conectar no PumpPortal WS para monitoramento: {e}")
                    await asyncio.sleep(2)
                    
        if target_token in state.get("open_positions", {}):
            del state["open_positions"][target_token]
            await self.broadcast_positions(user_id)
            
        await self.broadcast_metrics(user_id)
        await self.broadcast_positions(user_id)
                
        if state["is_active"]:
            state["config"]["status"] = "watching"
            await self.log_to_user(user_id, "INFO", "🔄 Retornando ao modo de observação (watching) para novos snipes.")
            await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})