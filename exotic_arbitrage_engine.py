"""
Motor de arbitragem espacial para pares exóticos / exchanges regionais
Tier-2 (Mercado Bitcoin, Gate.io, etc.), pensado pra capturar spreads de
0.5%-1.5% onde grandes fundos HFT não competem tão agressivamente.

Este módulo é o orquestrador: ele compõe as peças menores já implementadas
(exchange_connectors, spread_engine, risk_manager, atomic_executor,
arb_persistence) e implementa o fluxo assíncrono de monitoramento contínuo
dos livros de ordens + a decisão de executar ou descartar cada oportunidade.

Integração com o cofre Fernet: este motor NUNCA lê nem guarda chaves em texto
plano. Ele recebe o objeto `cipher` (o mesmo Fernet já inicializado em
MarketDataEngine.init_crypto()) e as credenciais já encriptadas exatamente
como saem de `_sync_save_api_key`/`_sync_get_all_keys` — a decriptação só
acontece na borda, dentro de `add_exchange()`, no momento de instanciar o
conector ccxt. As chaves decriptadas vivem apenas dentro da instância ccxt em
memória, nunca são logadas nem persistidas de volta.
"""
import asyncio
import logging
import time
from collections import defaultdict

from exchange_connectors import create_connector
from spread_engine import NetSpreadCalculator
from risk_manager import RiskManager
from atomic_executor import AtomicExecutor, LegExecutionError
from arb_persistence import ArbitragePersistence

logger = logging.getLogger("ExoticArbitrageEngine")


class ExoticArbitrageEngine:
    def __init__(
        self,
        cipher,
        data_dir: str,
        symbols: list[str],
        min_net_spread_pct: float = 0.5,
        trade_amount_quote: float = 50.0,
        max_concurrent_positions_per_symbol: int = 2,
        cooldown_seconds: float = 5.0,
        min_depth_multiplier: float = 1.5,
    ):
        self.cipher = cipher
        self.symbols = symbols
        self.trade_amount_quote = trade_amount_quote
        self.cooldown_seconds = cooldown_seconds

        self.persistence = ArbitragePersistence(data_dir)
        self.spread_calc = NetSpreadCalculator(
            min_net_spread_pct=min_net_spread_pct, min_depth_multiplier=min_depth_multiplier
        )
        self.risk = RiskManager(default_max_exposure=trade_amount_quote * max_concurrent_positions_per_symbol)
        self.executor = AtomicExecutor()

        self.connectors = {}          # {exchange_key: ExchangeConnector}
        self.orderbooks = {}          # {(exchange_key, symbol): {'bids': [...], 'asks': [...]}}
        self.cooldown_until = defaultdict(float)
        self.is_active = False

    # ------------------------------------------------------------------
    # Conectividade
    # ------------------------------------------------------------------
    def _decrypt(self, encrypted_val: str) -> str:
        if not encrypted_val:
            return ""
        try:
            return self.cipher.decrypt(encrypted_val.encode()).decode()
        except Exception as e:
            logger.error(f"Falha ao decriptar credencial do cofre: {e}")
            return ""

    def add_exchange(self, exchange_key: str, encrypted_row: dict = None, fee_overrides: dict = None):
        """`encrypted_row` é o dict cru vindo de `_sync_get_all_keys()` /
        `api_keys` (com key_encrypted/secret_encrypted/password_encrypted já
        no formato Fernet salvo pelo cofre). Passe None pra exchanges públicas
        (sem autenticação — só leitura de orderbook, sem poder executar ordens)."""
        creds = None
        if encrypted_row:
            apikey = self._decrypt(encrypted_row.get("key_encrypted", ""))
            secret = self._decrypt(encrypted_row.get("secret_encrypted", ""))
            password = self._decrypt(encrypted_row.get("password_encrypted", ""))
            if apikey and secret:
                creds = {"apiKey": apikey, "secret": secret}
                if password:
                    creds["password"] = password

        connector = create_connector(exchange_key, credentials=creds, fee_overrides=fee_overrides)
        self.connectors[exchange_key] = connector
        logger.info(f"🟢 [COFRE] Conector '{connector.display_name}' registrado "
                    f"({'autenticado' if creds else 'somente leitura pública'}).")
        return connector

    async def remove_exchange(self, exchange_key: str):
        connector = self.connectors.pop(exchange_key, None)
        if connector:
            await connector.close()
        for key in list(self.orderbooks.keys()):
            if key[0] == exchange_key:
                del self.orderbooks[key]

    # ------------------------------------------------------------------
    # Fluxo assíncrono de monitoramento de livros de ordens
    # ------------------------------------------------------------------
    async def _watch_orderbook(self, exchange_key: str, symbol: str):
        connector = self.connectors[exchange_key]
        key = (exchange_key, symbol)
        logger.info(f"[{connector.display_name}] Iniciando stream de {symbol} "
                    f"({'WebSocket' if connector.supports_ws_orderbook else 'polling REST'})...")

        # Melhor esforço: tenta corrigir a taxa default pela taxa real da conta
        # autenticada antes de começar a operar com este par.
        await connector.refresh_fees(symbol)

        async for ob in connector.stream_order_book(symbol):
            bids = ob.get("bids") or []
            asks = ob.get("asks") or []
            if bids and asks:
                self.orderbooks[key] = {"bids": bids, "asks": asks}

    def watch_tasks(self):
        """Uma task de monitoramento por (exchange, símbolo) registrado —
        mesma filosofia de watch_symbol() já usada em arbitrage_bot.py, só
        generalizada pra N exchanges plugáveis em vez de fixo Binance/Bitget."""
        tasks = []
        for exchange_key in self.connectors:
            for symbol in self.symbols:
                tasks.append(self._watch_orderbook(exchange_key, symbol))
        return tasks

    # ------------------------------------------------------------------
    # Análise de spread + decisão de execução
    # ------------------------------------------------------------------
    async def analyze_loop(self, poll_interval: float = 0.05):
        logger.info(f"Iniciando análise de spread para pares exóticos: {self.symbols}")
        while True:
            await asyncio.sleep(poll_interval)
            for symbol in self.symbols:
                try:
                    await self._analyze_symbol(symbol)
                except Exception as e:
                    logger.error(f"Erro ao analisar {symbol}: {e}")

    async def _analyze_symbol(self, symbol: str):
        candidates = {
            ex_key: ob for (ex_key, sym), ob in self.orderbooks.items()
            if sym == symbol and ob.get("bids") and ob.get("asks")
        }
        if len(candidates) < 2:
            return

        for buy_ex, buy_ob in candidates.items():
            for sell_ex, sell_ob in candidates.items():
                if buy_ex == sell_ex:
                    continue

                buy_conn = self.connectors[buy_ex]
                sell_conn = self.connectors[sell_ex]

                evaluation = self.spread_calc.evaluate(
                    symbol=symbol,
                    buy_exchange=buy_ex,
                    sell_exchange=sell_ex,
                    buy_asks=buy_ob["asks"],
                    sell_bids=sell_ob["bids"],
                    amount_quote=self.trade_amount_quote,
                    fee_buy_pct=buy_conn.taker_fee,
                    fee_sell_pct=sell_conn.taker_fee,
                    # withdrawal_fee_base=0.0 assume saldo pré-financiado nas duas
                    # pontas (modelo já usado no motor espacial existente). Se a
                    # estratégia para um par específico exigir transferência
                    # física do ativo, passe buy_conn.get_withdrawal_fee(<ativo base>).
                    withdrawal_fee_base=0.0,
                )

                if not evaluation.viable:
                    status = "discarded_thin_book" if not evaluation.depth_ok else "discarded_low_net"
                    asyncio.create_task(self.persistence.record_opportunity(evaluation, status))
                    continue

                if time.time() < self.cooldown_until[symbol]:
                    asyncio.create_task(self.persistence.record_opportunity(evaluation, "discarded_cooldown"))
                    continue

                if not self.is_active:
                    # Continua registrando oportunidades viáveis mesmo pausado,
                    # pra dar visibilidade do que teria sido executado.
                    asyncio.create_task(self.persistence.record_opportunity(evaluation, "discarded_paused"))
                    continue

                await self._try_execute(evaluation, buy_conn, sell_conn)

    async def _try_execute(self, evaluation, buy_conn, sell_conn):
        async with self.risk.reserved(evaluation.symbol, evaluation.amount_quote) as reserved_ok:
            if not reserved_ok:
                await self.persistence.record_opportunity(evaluation, "discarded_risk_limit")
                return

            self.cooldown_until[evaluation.symbol] = time.time() + self.cooldown_seconds
            base_amount = evaluation.amount_quote / evaluation.buy_avg_price

            try:
                buy_result, sell_result = await self.executor.execute_pair(
                    buy_conn, sell_conn, evaluation.symbol, base_amount
                )
            except LegExecutionError as leg_err:
                logger.error(f"[{evaluation.symbol}] Execução com risco de perna falhou: {leg_err} "
                             f"(neutralizado={leg_err.unwound})")
                await self.persistence.record_opportunity(
                    evaluation, "leg_failure",
                )
                return
            except Exception as e:
                logger.error(f"[{evaluation.symbol}] Erro inesperado na execução: {e}")
                await self.persistence.record_opportunity(evaluation, "leg_failure")
                return

            net_profit_quote = evaluation.amount_quote * (evaluation.net_spread_pct / 100.0)
            trade_id = await self.persistence.record_trade(
                evaluation.buy_exchange, evaluation.sell_exchange,
                evaluation.vwap_gross_pct, net_profit_quote,
            )
            await self.persistence.record_opportunity(evaluation, "executed", executed_trade_id=trade_id)

            logger.info(
                f"[✅ EXECUTADO] {evaluation.symbol} {evaluation.buy_exchange}->{evaluation.sell_exchange} | "
                f"net={evaluation.net_spread_pct:.3f}% | lucro≈{net_profit_quote:.4f} | "
                f"buy_id={buy_result.get('id')} sell_id={sell_result.get('id')}"
            )

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def run(self):
        tasks = self.watch_tasks()
        tasks.append(self.analyze_loop())
        await asyncio.gather(*tasks)

    async def shutdown(self):
        for connector in self.connectors.values():
            await connector.close()
