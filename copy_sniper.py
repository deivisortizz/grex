import asyncio
import json
import os
import sqlite3
import traceback
import websockets
import logging
import sys
import aiohttp
from dotenv import load_dotenv

from solana_core import SolanaCore, DATA_DIR, is_rate_limited_error, rate_limit_delay

load_dotenv()

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('CopySniper')

WS_PORT = int(os.getenv("COPY_SNIPER_WS_PORT", "8768"))
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


class CopySniper(SolanaCore):
    """
    Motor de Copy Trading real.

    Diferente do solana_sniper.py (que escuta TODO lançamento novo da Pump.fun),
    este processo assina logsSubscribe especificamente das carteiras cadastradas
    pelo usuário em `tracked_wallets` (aba "Copy Trading" do front-end) e, ao
    detectar uma compra Pump.fun feita por uma delas, replica a mesma compra
    para o usuário que a está seguindo, usando o wallet/trade_amount/jito_tip/
    slippage/TP/SL já configurados na aba "Sniper" (mesma linha de
    solana_sniper_configs, compartilhada entre os dois motores).
    """

    def __init__(self):
        # [FIX] Tabela de histórico dedicada: antes o copy_sniper.py nem existia
        # como motor de copy trading de verdade, e quando chegou a rodar (como
        # cópia do sniper global) gravava tudo em "solana_sniper_history",
        # misturando estatísticas de estratégias diferentes.
        super().__init__(history_table="copy_sniper_history", logger_name="CopySniper")
        # Dedup de assinaturas já processadas (evita reagir duas vezes à mesma
        # transação se o WS da Helius reenviar a notificação após reconectar).
        self.processed_signatures = set()

    # ------------------------------------------------------------------
    # Descoberta e carregamento de estado (config compartilhada + wallets rastreadas)
    # ------------------------------------------------------------------
    def _discover_copy_trading_user_ids(self):
        """Retorna todo user_id que tenha carteira burner OU carteiras rastreadas
        cadastradas — não dá pra usar só solana_sniper_configs (como o sniper
        global faz), porque um usuário pode usar só a aba Copy Trading e nunca
        ter tocado na aba Sniper."""
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        if not os.path.exists(db_path):
            return []
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT user_id FROM tracked_wallets
                    UNION
                    SELECT DISTINCT user_id FROM solana_burner_wallet
                ''')
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erro ao listar usuários do Copy Sniper: {e}")
            return []

    def _refresh_copy_trading_state(self):
        """Recarrega wallet/config/tracked_wallets de todos os usuários a partir
        do SQLite. Propositalmente NÃO usa _load_all_user_configs() herdado:
        aquele método faz "UPDATE solana_sniper_configs SET is_active = 0" no
        startup, e como essa tabela é COMPARTILHADA com o solana_sniper.py,
        isso desligaria o sniper global de todo mundo sempre que o processo
        de Copy Trading reiniciasse. Aqui só LEMOS o banco, nunca escrevemos."""
        for user_id in self._discover_copy_trading_user_ids():
            self._load_user_config_from_db(user_id)
            self._load_tracked_wallets_from_db(user_id)

    def _build_wallet_watch_map(self):
        """{wallet_address: [user_id, ...]} para todo usuário com carteira burner
        configurada e ao menos uma tracked_wallet marcada como ativa."""
        wallet_map = {}
        for user_id, state in self.user_states.items():
            if not state.get("wallet"):
                continue
            for tracked in state.get("tracked_wallets", []):
                if not tracked.get("is_active", True):
                    continue
                addr = tracked.get("wallet_address")
                if addr:
                    wallet_map.setdefault(addr, []).append(user_id)
        return wallet_map

    # ------------------------------------------------------------------
    # Detecção de compra: inspeciona a transação da carteira rastreada
    # ------------------------------------------------------------------
    async def _fetch_wallet_buy_mint(self, signature, wallet_address, session, rpc_url):
        """Confirma que 'wallet_address' comprou um token via Pump.fun nesta tx
        (saldo do mint aumentou) e retorna o mint, ou None caso contrário."""
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
            "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}]
        }
        for _ in range(5):
            try:
                async with session.post(rpc_url, json=payload, timeout=3.0) as resp:
                    data = await resp.json()
                    result = data.get("result")
                    if result:
                        meta = result.get("meta") or {}
                        if meta.get("err") is not None:
                            return None  # a transação da carteira falhou na rede

                        account_keys_raw = result.get("transaction", {}).get("message", {}).get("accountKeys", [])
                        account_keys = [
                            (k.get("pubkey") if isinstance(k, dict) else k) for k in account_keys_raw
                        ]
                        if PUMP_PROGRAM not in account_keys:
                            return None  # atividade da carteira não envolveu o programa da Pump.fun

                        pre_by_mint = {}
                        for b in (meta.get("preTokenBalances") or []):
                            if b.get("owner") == wallet_address:
                                pre_by_mint[b.get("mint")] = float((b.get("uiTokenAmount") or {}).get("uiAmount") or 0.0)

                        for b in (meta.get("postTokenBalances") or []):
                            if b.get("owner") != wallet_address:
                                continue
                            mint = b.get("mint")
                            post_amount = float((b.get("uiTokenAmount") or {}).get("uiAmount") or 0.0)
                            pre_amount = pre_by_mint.get(mint, 0.0)
                            if post_amount > pre_amount:
                                return mint
                        return None
            except Exception:
                pass
            await asyncio.sleep(0.3)
        return None

    # ------------------------------------------------------------------
    # Replicação da compra para cada usuário que segue a carteira
    # ------------------------------------------------------------------
    async def handle_copy_snipe(self, user_id, state, target_token, source_wallet):
        # [FIX] Roda inteira dentro de um try/except: como é disparada via
        # asyncio.create_task (fire-and-forget), uma exceção não tratada travaria
        # o "status" do usuário em "sniping" pra sempre, sem log e sem recuperação.
        try:
            if target_token in state.get("open_positions", {}):
                return  # já temos posição aberta nesse token, evita compra duplicada

            max_pos = int(state["config"].get("max_positions", 1))
            if len(state.get("open_positions", {})) >= max_pos:
                await self.log_to_user(
                    user_id, "WARN",
                    f"⏳ Limite de {max_pos} posições atingido. Copy-trade de "
                    f"{source_wallet[:4]}...{source_wallet[-4:]} ignorado."
                )
                return

            rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=afef48e6-b88a-49e6-84c4-9b408156ee55")

            # Blacklist automática de criadores continua valendo como rede de
            # segurança mesmo em copy trading (soft-fail: não perder o trade se
            # a API da Pump.fun estiver fora do ar).
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"https://frontend-api.pump.fun/coins/{target_token}", timeout=2.0) as resp:
                        if resp.status == 200:
                            coin_data = await resp.json()
                            creator = coin_data.get("creator")
                            if creator and self._is_blacklisted(creator):
                                await self.log_to_user(
                                    user_id, "WARN",
                                    f"🚫 [BLACKLIST] Copy-trade de {source_wallet[:4]}...{source_wallet[-4:]} "
                                    f"ignorado: criador do token está na lista negra."
                                )
                                return
            except Exception:
                pass

            await self.log_to_user(
                user_id, "WARN",
                f"🐳 [COPY TRADE] {source_wallet[:4]}...{source_wallet[-4:]} comprou "
                f"{target_token[:4]}...{target_token[-4:]}! Replicando compra..."
            )
            state["config"]["status"] = "sniping"
            await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})

            success = await self.execute_real_snipe(user_id, state, target_token)
            if success:
                state["config"]["status"] = "monitoring_position"
                await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                # Base do SL/TP é o valor real investido (buy_amount_sol), não o débito
                # total da carteira (sol_spent inclui tip Jito + rent de conta nova).
                pos_data = state.get("open_positions", {}).get(target_token, {})
                sol_spent = pos_data.get("sol_spent", 0.0)
                entry_reference = pos_data.get("buy_amount_sol", sol_spent)
                asyncio.create_task(self.monitor_position(user_id, entry_reference, token_mint=target_token))
            else:
                state["config"]["status"] = "watching"
                await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
        except Exception as e:
            logger.error(f"Falha crítica não tratada em handle_copy_snipe ({target_token} via {source_wallet}): {e}")
            logger.error(traceback.format_exc())
            if target_token not in state.get("open_positions", {}):
                state["config"]["status"] = "watching"
                await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})

    # ------------------------------------------------------------------
    # Loop principal: assina logsSubscribe de cada carteira rastreada
    # ------------------------------------------------------------------
    async def wallet_watch_loop(self):
        wss_url = os.getenv("SOLANA_WSS_URL", "wss://mainnet.helius-rpc.com/?api-key=afef48e6-b88a-49e6-84c4-9b408156ee55")
        rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=afef48e6-b88a-49e6-84c4-9b408156ee55")

        min_delay = 0.25
        max_delay = 10.0
        reconnect_delay = min_delay

        # [FIX] Backoff separado e bem mais conservador para HTTP 429 (rate limit) —
        # reconectar em 250ms contra uma Helius que já está nos rejeitando só piora.
        rate_limit_streak = 0
        consecutive_errors = 0

        while True:
            self._refresh_copy_trading_state()
            wallet_map = self._build_wallet_watch_map()

            if not wallet_map:
                await asyncio.sleep(10)
                continue

            try:
                async with websockets.connect(wss_url, ping_interval=60, ping_timeout=120) as ws:
                    # A Solana só aceita 1 endereço por assinatura "mentions" — uma
                    # logsSubscribe por carteira, todas na mesma conexão WS. Espaçadas
                    # em 50ms entre si pra não disparar uma rajada de requisições no
                    # handshake quando há muitas carteiras rastreadas (contribuía pro 429).
                    id_to_wallet = {}
                    wallet_list = list(wallet_map.keys())
                    for idx, wallet in enumerate(wallet_list):
                        req_id = idx + 1
                        id_to_wallet[req_id] = wallet
                        await ws.send(json.dumps({
                            "jsonrpc": "2.0", "id": req_id, "method": "logsSubscribe",
                            "params": [{"mentions": [wallet]}, {"commitment": "processed"}]
                        }))
                        if idx < len(wallet_list) - 1:
                            await asyncio.sleep(0.05)

                    logger.info(f"📡 Copy Sniper monitorando {len(wallet_map)} carteira(s) rastreada(s) via Helius WSS...")
                    reconnect_delay = min_delay
                    rate_limit_streak = 0
                    consecutive_errors = 0
                    sub_to_wallet = {}

                    async with aiohttp.ClientSession() as session:
                        loop = asyncio.get_event_loop()
                        last_refresh = loop.time()

                        async for message in ws:
                            now = loop.time()
                            if now - last_refresh > 20.0:
                                self._refresh_copy_trading_state()
                                new_map = self._build_wallet_watch_map()
                                if set(new_map.keys()) != set(wallet_map.keys()):
                                    logger.info("🔄 Lista de carteiras rastreadas mudou. Reconectando com o novo conjunto...")
                                    break
                                last_refresh = now

                            data = json.loads(message)

                            # Confirmação de subscrição: {"result": <subscription_id>, "id": <req_id>}
                            if "result" in data and isinstance(data.get("id"), int) and data["id"] in id_to_wallet:
                                sub_to_wallet[data["result"]] = id_to_wallet[data["id"]]
                                continue

                            if data.get("method") != "logsNotification":
                                continue

                            params = data.get("params", {})
                            subscription = params.get("subscription")
                            wallet = sub_to_wallet.get(subscription)
                            if not wallet:
                                continue

                            value = params.get("result", {}).get("value", {})
                            if value.get("err") is not None:
                                continue  # transação da carteira falhou na rede

                            logs = value.get("logs", [])
                            signature = value.get("signature")
                            if not logs or not signature:
                                continue

                            if PUMP_PROGRAM not in str(logs):
                                continue  # atividade da carteira não foi na Pump.fun

                            if signature in self.processed_signatures:
                                continue
                            self.processed_signatures.add(signature)
                            if len(self.processed_signatures) > 5000:
                                self.processed_signatures.clear()

                            mint = await self._fetch_wallet_buy_mint(signature, wallet, session, rpc_url)
                            if not mint:
                                continue

                            for user_id in wallet_map.get(wallet, []):
                                state = self._get_user_state(user_id)
                                if not state.get("wallet"):
                                    continue
                                asyncio.create_task(self.handle_copy_snipe(user_id, state, mint, wallet))

            except Exception as e:
                consecutive_errors += 1
                if is_rate_limited_error(e):
                    delay = rate_limit_delay(rate_limit_streak)
                    rate_limit_streak += 1
                    if consecutive_errors <= 3 or consecutive_errors % 5 == 0:
                        logger.error(f"⛔ Helius retornou 429 (rate limit) no Copy Sniper. Aguardando {delay:.0f}s (ocorrência #{consecutive_errors})...")
                    await asyncio.sleep(delay)
                else:
                    rate_limit_streak = 0
                    if consecutive_errors <= 3 or consecutive_errors % 5 == 0:
                        logger.error(f"Erro no WSS Copy Sniper: {e}. Reconectando em {reconnect_delay:.2f}s...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_delay)

    async def start(self):
        logger.info(f"🚀 Iniciando Copy Sniper na porta {WS_PORT}")
        self._refresh_copy_trading_state()
        async with websockets.serve(self.ws_handler, "0.0.0.0", WS_PORT):
            await self.wallet_watch_loop()


if __name__ == "__main__":
    sniper = CopySniper()
    asyncio.run(sniper.start())
