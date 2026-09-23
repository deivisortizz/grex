"""
Motor de execução relâmpago (item 3) + gestão de saída automatizada (item 4).

[Sobre "ordens OCO"] Pesquisei antes de implementar: suporte a OCO
(One-Cancels-Other) via ccxt não é uniforme entre exchanges Tier-2/3 — cada
uma expõe (ou não) de um jeito diferente, e nem toda posição criada por
ordem a mercado tem um par OCO nativo disponível no par recém-listado (às
vezes o par nem tem profundidade de order book suficiente pra aceitar ordens
limite logo na abertura). Por isso o TP/SL aqui é **gerido por software**
(polling de altíssima frequência do último preço via `stream_ticker`,
disparando uma ordem de mercado no instante em que um dos limiares é
cruzado) — o MESMO padrão já usado e validado no monitor de posição do
Solana Sniper (solana_core.py::monitor_position). É mais portável entre
exchanges com suporte a OCO inconsistente, ao custo de depender da conexão
ficar viva durante a janela de saída (por isso o watch_ticker/fetch_ticker
já tem sua própria resiliência de reconexão em exchange_connectors.py).
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field

from exchange_connectors import create_connector, ExchangeConnector

logger = logging.getLogger("ListingExecutionEngine")


@dataclass
class ListingTradeConfig:
    trade_amount_quote: float = 20.0
    tp_pct: float = 50.0
    sl_pct: float = 15.0
    max_hold_seconds: float = 300.0     # saída forçada de segurança, mesmo sem bater TP/SL
    poll_interval_seconds: float = 0.3  # frequência de checagem via fallback REST (WS é preferido quando disponível)
    quote_currencies: tuple = ("USDT", "USDC")


@dataclass
class _ArmedUser:
    connector: ExchangeConnector
    config: ListingTradeConfig


class ListingExecutionEngine:
    def __init__(self, persistence, cipher):
        self.persistence = persistence
        self.cipher = cipher
        # {exchange: {user_id: _ArmedUser}}
        self.armed_users: dict[str, dict[int, _ArmedUser]] = {}
        # Callback opcional: async def on_trade_event(event_type, data) — pro
        # processo que compõe este motor (ver listing_sniper_service.py)
        # repassar eventos ao front-end em tempo real, sem este módulo saber
        # nada sobre WebSocket/broadcast.
        self.on_trade_event = None

    async def _notify(self, event_type: str, data: dict):
        if self.on_trade_event:
            try:
                await self.on_trade_event(event_type, data)
            except Exception as e:
                logger.error(f"Erro no callback on_trade_event: {e}")

    # ------------------------------------------------------------------
    # Cofre / armamento de usuários
    # ------------------------------------------------------------------
    def _decrypt(self, encrypted_val: str) -> str:
        if not encrypted_val:
            return ""
        try:
            return self.cipher.decrypt(encrypted_val.encode()).decode()
        except Exception as e:
            logger.error(f"Falha ao decriptar credencial do cofre: {e}")
            return ""

    def arm_user(self, user_id: int, exchange: str, encrypted_row: dict, config: ListingTradeConfig):
        """Registra um usuário como 'armado': assim que uma listagem
        qualificada aparecer nessa exchange, uma compra é disparada
        automaticamente pra ele. `encrypted_row` é o dict cru vindo do cofre
        (key_encrypted/secret_encrypted/password_encrypted)."""
        apikey = self._decrypt(encrypted_row.get("key_encrypted", ""))
        secret = self._decrypt(encrypted_row.get("secret_encrypted", ""))
        password = self._decrypt(encrypted_row.get("password_encrypted", ""))
        if not apikey or not secret:
            raise ValueError("Credenciais inválidas/incompletas no cofre — não é possível armar o usuário.")

        creds = {"apiKey": apikey, "secret": secret}
        if password:
            creds["password"] = password

        connector = create_connector(exchange, credentials=creds)
        self.armed_users.setdefault(exchange.upper(), {})[user_id] = _ArmedUser(connector=connector, config=config)
        logger.info(f"🔫 [ARMADO] Usuário {user_id} pronto pra disparar em {exchange} "
                    f"(aporte={config.trade_amount_quote}, TP=+{config.tp_pct}%, SL=-{config.sl_pct}%).")

    async def disarm_user(self, user_id: int, exchange: str):
        bucket = self.armed_users.get(exchange.upper(), {})
        entry = bucket.pop(user_id, None)
        if entry:
            await entry.connector.close()
            logger.info(f"🔒 [DESARMADO] Usuário {user_id} não dispara mais em {exchange}.")

    def has_armed_users(self, exchange: str) -> bool:
        return bool(self.armed_users.get(exchange.upper()))

    # ------------------------------------------------------------------
    # Disparo — chamado pelo serviço principal quando o extrator confirma
    # uma listagem acionável.
    # ------------------------------------------------------------------
    async def handle_qualified_announcement(self, exchange: str, ticker: str, announcement_id: int, detected_at_ms: int):
        armed = dict(self.armed_users.get(exchange.upper(), {}))
        if not armed:
            return
        tasks = [
            self._execute_for_user(user_id, entry, exchange.upper(), ticker, announcement_id, detected_at_ms)
            for user_id, entry in armed.items()
        ]
        # [FIX-pattern] return_exceptions=True: um usuário falhando (saldo
        # insuficiente, símbolo inexistente, etc.) não pode derrubar o
        # disparo dos outros usuários armados na mesma listagem.
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _resolve_symbol(self, connector: ExchangeConnector, ticker: str, quote_currencies: tuple) -> str | None:
        """Acha o par de negociação certo pro ticker recém-listado. O mercado
        pode não estar carregado/atualizado no instante exato do anúncio —
        tenta o cache primeiro (rápido) e só recarrega se preciso (o par pode
        ter acabado de ser criado no exchange há segundos)."""
        try:
            markets = getattr(connector.ccxt, "markets", None) or {}
            for quote in quote_currencies:
                symbol = f"{ticker}/{quote}"
                if symbol in markets:
                    return symbol
        except Exception:
            pass

        try:
            await connector.ccxt.load_markets(reload=True)
        except Exception as e:
            logger.warning(f"[{connector.display_name}] Falha ao recarregar mercados: {e}")
            return None

        markets = getattr(connector.ccxt, "markets", None) or {}
        for quote in quote_currencies:
            symbol = f"{ticker}/{quote}"
            if symbol in markets:
                return symbol
        return None

    async def _execute_for_user(self, user_id: int, entry: _ArmedUser, exchange: str, ticker: str,
                                 announcement_id: int, detected_at_ms: int):
        connector = entry.connector
        config = entry.config

        symbol = await self._resolve_symbol(connector, ticker, config.quote_currencies)
        if not symbol:
            logger.warning(f"[{exchange}] Símbolo pra '{ticker}' não encontrado (usuário {user_id}).")
            await self.persistence.record_trade_failed(announcement_id, user_id, exchange, ticker, "symbol_not_found")
            await self._notify("trade_failed", {"user_id": user_id, "exchange": exchange, "ticker": ticker, "reason": "symbol_not_found"})
            return

        entry_latency_ms = int(time.time() * 1000) - detected_at_ms
        logger.warning(f"⚡ [{exchange}] Disparando compra de {symbol} pro usuário {user_id} "
                        f"(latência desde a detecção: {entry_latency_ms}ms)...")

        try:
            order = await connector.market_buy_with_cost(symbol, config.trade_amount_quote)
        except Exception as e:
            logger.error(f"[{exchange}] Falha ao comprar {symbol} pro usuário {user_id}: {e}")
            await self.persistence.record_trade_failed(announcement_id, user_id, exchange, ticker, str(e))
            await self._notify("trade_failed", {"user_id": user_id, "exchange": exchange, "ticker": ticker, "reason": str(e)})
            return

        filled_base = float(order.get("filled") or order.get("amount") or 0.0)
        avg_price = order.get("average") or order.get("price")
        if not avg_price:
            cost = order.get("cost")
            avg_price = (cost / filled_base) if (cost and filled_base) else None

        if filled_base <= 0 or not avg_price:
            logger.error(f"[{exchange}] Ordem de compra de {symbol} sem preenchimento utilizável "
                         f"(usuário {user_id}) — não é possível gerir TP/SL sem saber quanto foi comprado.")
            await self.persistence.record_trade_failed(announcement_id, user_id, exchange, ticker, "unfilled_or_unpriced_order")
            await self._notify("trade_failed", {"user_id": user_id, "exchange": exchange, "ticker": ticker, "reason": "unfilled_or_unpriced_order"})
            return

        trade_id = await self.persistence.record_trade_open(
            announcement_id=announcement_id, user_id=user_id, exchange=exchange, symbol=symbol,
            buy_order_id=order.get("id"), buy_price=avg_price, amount_quote=config.trade_amount_quote,
            amount_base=filled_base, tp_pct=config.tp_pct, sl_pct=config.sl_pct, entry_latency_ms=entry_latency_ms,
        )
        logger.info(f"✅ [{exchange}] Compra de {symbol} confirmada pro usuário {user_id}: "
                    f"{filled_base:.6f} @ {avg_price:.8f} (trade #{trade_id}).")
        await self._notify("trade_opened", {
            "trade_id": trade_id, "user_id": user_id, "exchange": exchange, "symbol": symbol,
            "buy_price": avg_price, "amount_base": filled_base, "entry_latency_ms": entry_latency_ms,
        })

        asyncio.create_task(self._monitor_exit(trade_id, user_id, connector, symbol, avg_price, filled_base, config))

    # ------------------------------------------------------------------
    # Saída automatizada (TP / SL / timeout)
    # ------------------------------------------------------------------
    async def _monitor_exit(self, trade_id: int, user_id: int, connector: ExchangeConnector, symbol: str,
                             entry_price: float, base_amount: float, config: ListingTradeConfig):
        # [FIX-pattern] Protegido em try/except: como é disparada via
        # asyncio.create_task (fire-and-forget), uma exceção não tratada aqui
        # deixaria a posição aberta pra sempre sem monitoramento nenhum —
        # exatamente o tipo de "trade órfão" que já corrigimos no Solana Sniper.
        try:
            start_time = time.monotonic()
            tp_price = entry_price * (1 + config.tp_pct / 100.0)
            sl_price = entry_price * (1 - config.sl_pct / 100.0)

            async for ticker in connector.stream_ticker(symbol, fallback_poll_seconds=config.poll_interval_seconds):
                last_price = ticker.get("last") or ticker.get("close")
                elapsed = time.monotonic() - start_time

                if elapsed >= config.max_hold_seconds:
                    await self._close_position(trade_id, user_id, connector, symbol, entry_price, base_amount, "closed_timeout")
                    return

                if not last_price:
                    continue

                if last_price >= tp_price:
                    await self._close_position(trade_id, user_id, connector, symbol, entry_price, base_amount, "closed_tp", last_price)
                    return

                if last_price <= sl_price:
                    await self._close_position(trade_id, user_id, connector, symbol, entry_price, base_amount, "closed_sl", last_price)
                    return
        except Exception as e:
            logger.critical(f"🔴 [{symbol}] Falha crítica no monitor de saída do trade #{trade_id} "
                             f"(usuário {user_id})! Posição pode ficar sem TP/SL ativo. Erro: {e}")
            await self._notify("monitor_crashed", {"trade_id": trade_id, "user_id": user_id, "symbol": symbol, "error": str(e)})

    async def _close_position(self, trade_id: int, user_id: int, connector: ExchangeConnector, symbol: str,
                               entry_price: float, base_amount: float, status: str, last_known_price: float = None):
        try:
            order = await connector.market_sell(symbol, base_amount)
        except Exception as e:
            logger.critical(f"🔴 [{symbol}] Falha ao ENVIAR ordem de saída ({status}) do trade #{trade_id} "
                             f"(usuário {user_id})! AÇÃO MANUAL PODE SER NECESSÁRIA. Erro: {e}")
            await self._notify("exit_failed", {"trade_id": trade_id, "user_id": user_id, "symbol": symbol, "status": status, "error": str(e)})
            return

        exit_price = order.get("average") or order.get("price") or last_known_price or entry_price
        pnl_quote = (exit_price - entry_price) * base_amount
        pnl_pct = ((exit_price / entry_price) - 1) * 100 if entry_price else 0.0

        await self.persistence.close_trade(trade_id, status, order.get("id"), exit_price, pnl_quote, pnl_pct)

        icon = "💰" if pnl_quote >= 0 else "🛑"
        logger.info(f"{icon} [{symbol}] Posição encerrada ({status}) — trade #{trade_id}, usuário {user_id}: "
                    f"PnL {pnl_pct:+.2f}% ({pnl_quote:+.6f} na cotação).")
        await self._notify("trade_closed", {
            "trade_id": trade_id, "user_id": user_id, "symbol": symbol, "status": status,
            "exit_price": exit_price, "pnl_quote": pnl_quote, "pnl_pct": pnl_pct,
        })

    async def shutdown(self):
        for bucket in self.armed_users.values():
            for entry in bucket.values():
                await entry.connector.close()
