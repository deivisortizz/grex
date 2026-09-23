"""
Camada de conectividade multi-exchange plugável para o motor HFT.

Cada exchange é um `ExchangeConnector` que encapsula a instância ccxt (pro
quando há suporte a WebSocket, clássico com polling REST quando não há) e
declara sua própria taxa de taker/maker e tabela de taxas de saque — para que
o motor de spread líquido (spread_engine.py) não precise saber nada sobre
particularidades de cada corretora.

Para adicionar uma exchange nova "de forma limpa" (item 1 do pedido): basta
criar uma subclasse de ExchangeConnector declarando `exchange_id`,
`display_name`, as taxas default e (se aplicável) a tabela de saque, e
registrá-la em CONNECTOR_REGISTRY no fim do arquivo. Nenhum outro módulo
precisa ser tocado.
"""
import asyncio
import logging

import ccxt as ccxt_rest
import ccxt.pro as ccxt_pro

logger = logging.getLogger("ExchangeConnectors")


class ExchangeConnector:
    """Classe base. Nunca é instanciada diretamente — sempre via subclasse
    concreta ou via `create_connector()` do registro."""

    exchange_id: str = None          # id ccxt (ex: 'binance', 'gate', 'mercado')
    display_name: str = None
    default_taker_fee: float = 0.001
    default_maker_fee: float = 0.001
    supports_ws_orderbook: bool = True   # False -> usa polling REST (ex: Mercado Bitcoin)
    poll_interval_seconds: float = 1.0   # só usado quando supports_ws_orderbook=False

    # Taxas de saque por ativo, em unidades do próprio ativo. Nem toda exchange
    # expõe isso de forma confiável via API (cobertura no ccxt é inconsistente,
    # especialmente em exchanges regionais/Tier-2) — por isso é uma tabela
    # estática, de melhor esforço, pensada para ser ajustada manualmente pelo
    # operador. Usada apenas quando a estratégia exige TRANSFERÊNCIA física do
    # ativo entre exchanges (ver `requires_transfer` em spread_engine.py); no
    # modelo "saldo pré-financiado em ambas as pontas" (como o espacial atual
    # USDT/BRL Binance<->Bitget) ela não entra na conta.
    withdrawal_fees: dict = {}

    def __init__(self, credentials=None, fee_overrides=None):
        if not self.exchange_id:
            raise NotImplementedError("Subclasse de ExchangeConnector precisa definir exchange_id")

        creds = dict(credentials or {})
        creds.setdefault("enableRateLimit", True)

        ccxt_module = ccxt_pro if self.supports_ws_orderbook else ccxt_rest
        try:
            ExchangeClass = getattr(ccxt_module, self.exchange_id)
        except AttributeError:
            # Fallback defensivo: se por algum motivo o id não existir no módulo
            # esperado (ex: uma versão de ccxt sem suporte WS pra essa exchange
            # ainda), cai pro ccxt clássico com polling em vez de quebrar.
            ExchangeClass = getattr(ccxt_rest, self.exchange_id)
            self.supports_ws_orderbook = False

        self.ccxt = ExchangeClass(creds)

        overrides = fee_overrides or {}
        self.taker_fee = overrides.get("taker", self.default_taker_fee)
        self.maker_fee = overrides.get("maker", self.default_maker_fee)

    def get_withdrawal_fee(self, asset: str) -> float:
        return self.withdrawal_fees.get(asset.upper(), 0.0)

    async def refresh_fees(self, symbol: str):
        """Melhor esforço: tenta puxar a taxa real da conta autenticada (nem
        toda exchange/ccxt suporta `fetchTradingFee`). Falha em silêncio e
        mantém o default declarado na classe — nunca deixa taker_fee/maker_fee
        indefinidos, o que corromperia o cálculo de net spread."""
        if not getattr(self.ccxt, "has", {}).get("fetchTradingFee"):
            return
        try:
            info = await self.ccxt.fetch_trading_fee(symbol)
            if info.get("taker") is not None:
                self.taker_fee = float(info["taker"])
            if info.get("maker") is not None:
                self.maker_fee = float(info["maker"])
            logger.info(f"[{self.display_name}] Taxas reais carregadas para {symbol}: "
                        f"taker={self.taker_fee:.4%} maker={self.maker_fee:.4%}")
        except Exception as e:
            logger.debug(f"[{self.display_name}] Não foi possível obter taxa real para {symbol} ({e}); "
                         f"mantendo default taker={self.taker_fee:.4%}.")

    async def stream_order_book(self, symbol: str, depth: int = 20):
        """Async generator unificado: usa WebSocket quando a exchange suporta
        (`watch_order_book`), ou faz polling REST no intervalo declarado quando
        não suporta (ex: Mercado Bitcoin, que não tem WS em nenhuma exchange
        ccxt/ccxt.pro atual). O chamador (watch loop do motor) não precisa
        saber qual dos dois caminhos está sendo usado."""
        if self.supports_ws_orderbook:
            while True:
                try:
                    ob = await self.ccxt.watch_order_book(symbol, limit=depth)
                    yield ob
                except ccxt_pro.NetworkError:
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"[{self.display_name} - {symbol}] Erro no watch_order_book: {e}")
                    await asyncio.sleep(2)
        else:
            while True:
                try:
                    ob = await self.ccxt.fetch_order_book(symbol, limit=depth)
                    yield ob
                except Exception as e:
                    logger.error(f"[{self.display_name} - {symbol}] Erro no fetch_order_book (polling): {e}")
                await asyncio.sleep(self.poll_interval_seconds)

    async def stream_ticker(self, symbol: str, fallback_poll_seconds: float = 0.5):
        """Análogo a stream_order_book, mas pra ticker (último preço) — usado
        pelo monitor de TP/SL do Listing Sniper, que precisa da menor latência
        possível pra reagir a um spike-and-dump logo após uma listagem nova."""
        if getattr(self.ccxt, "has", {}).get("watchTicker") and self.supports_ws_orderbook:
            while True:
                try:
                    ticker = await self.ccxt.watch_ticker(symbol)
                    yield ticker
                except ccxt_pro.NetworkError:
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"[{self.display_name} - {symbol}] Erro no watch_ticker: {e}")
                    await asyncio.sleep(1)
        else:
            while True:
                try:
                    ticker = await self.ccxt.fetch_ticker(symbol)
                    yield ticker
                except Exception as e:
                    logger.error(f"[{self.display_name} - {symbol}] Erro no fetch_ticker (polling): {e}")
                await asyncio.sleep(fallback_poll_seconds)

    async def market_buy(self, symbol: str, base_amount: float):
        """`base_amount` é sempre a quantidade da moeda BASE do par (ex: em
        USDT/BRL, base=USDT) — mesma convenção já usada em arbitrage_bot.py."""
        return await self.ccxt.create_market_buy_order(symbol, base_amount)

    async def market_buy_with_cost(self, symbol: str, cost_quote: float):
        """Compra `cost_quote` unidades da moeda de COTAÇÃO via ordem a
        mercado, sem precisar converter pra quantidade de moeda base a partir
        de um preço que já pode estar obsoleto no instante do disparo — crítico
        logo após um anúncio de listagem, quando o preço se move violentamente
        em segundos (uso principal: listing_execution_engine.py).

        Usa o método unificado do ccxt (`createMarketBuyOrderWithCost`) quando
        a exchange suporta [confirmado via introspecção que MEXC suporta].
        Só cai pro fallback de estimar a quantidade base pelo último preço se
        a exchange genuinamente não tiver o método — e nesse caso loga um
        aviso claro, porque a imprecisão é real."""
        if self.ccxt.has.get("createMarketBuyOrderWithCost"):
            return await self.ccxt.create_market_buy_order_with_cost(symbol, cost_quote)

        logger.warning(
            f"[{self.display_name}] Sem suporte nativo a compra por custo — estimando quantidade "
            f"base pelo último preço (menos preciso, o preço pode já ter se movido)."
        )
        ticker = await self.ccxt.fetch_ticker(symbol)
        last_price = ticker.get("last") or ticker.get("close")
        if not last_price or last_price <= 0:
            raise ValueError(f"Não foi possível obter preço de {symbol} pra estimar a quantidade base.")
        base_amount = cost_quote / last_price
        return await self.ccxt.create_market_buy_order(symbol, base_amount)

    async def market_sell(self, symbol: str, base_amount: float):
        return await self.ccxt.create_market_sell_order(symbol, base_amount)

    async def close(self):
        try:
            await self.ccxt.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# Conectores concretos
# ----------------------------------------------------------------------

class BinanceConnector(ExchangeConnector):
    exchange_id = "binance"
    display_name = "Binance"
    default_taker_fee = 0.001
    default_maker_fee = 0.001
    supports_ws_orderbook = True
    withdrawal_fees = {"USDT": 1.0, "BTC": 0.0002, "ETH": 0.003, "BRL": 0.0}


class BitgetConnector(ExchangeConnector):
    exchange_id = "bitget"
    display_name = "Bitget"
    # ccxt não expõe taxa estática pra Bitget (varia por conta/VIP tier);
    # 0.1%/0.1% é a taxa pública padrão documentada. refresh_fees() tenta
    # corrigir com o valor real da conta assim que autenticado.
    default_taker_fee = 0.001
    default_maker_fee = 0.001
    supports_ws_orderbook = True
    withdrawal_fees = {"USDT": 1.0, "BTC": 0.0002, "ETH": 0.003}


class GateIOConnector(ExchangeConnector):
    exchange_id = "gate"   # NÃO é 'gateio' — esse é o id real no ccxt/ccxt.pro
    display_name = "Gate.io"
    # Confirmado via introspecção do ccxt.pro: taker/maker tier-0 = 0.2%,
    # com tiers decrescentes por volume (não modelados aqui — refresh_fees()
    # busca o valor real quando autenticado).
    default_taker_fee = 0.002
    default_maker_fee = 0.002
    supports_ws_orderbook = True
    withdrawal_fees = {"USDT": 1.0, "BTC": 0.0005, "ETH": 0.003}


class MexcConnector(ExchangeConnector):
    # Confirmado via introspecção do ccxt.pro (id='mexc'): suporta WS
    # orderbook/ticker e ordens de mercado. Taxa pública taker/maker 0.2%.
    # Usada também pelo CEX Listing Sniper (listing_execution_engine.py) —
    # MEXC tem API pública de anúncios (/api/v3/announcements) verificada
    # ao vivo, útil tanto pra arbitragem quanto pra sniping de listagem.
    exchange_id = "mexc"
    display_name = "MEXC"
    default_taker_fee = 0.002
    default_maker_fee = 0.002
    supports_ws_orderbook = True
    withdrawal_fees = {"USDT": 1.0, "BTC": 0.0002, "ETH": 0.003}


class MercadoBitcoinConnector(ExchangeConnector):
    # [IMPORTANTE] O id ccxt é 'mercado' (não 'mercadobitcoin'). Confirmado
    # também que esta exchange NÃO tem suporte a WebSocket em nenhuma versão
    # do ccxt/ccxt.pro atual — supports_ws_orderbook=False força o fallback
    # de polling REST automaticamente via stream_order_book().
    exchange_id = "mercado"
    display_name = "Mercado Bitcoin"
    # Taxas públicas reais confirmadas via ccxt: taker 0.7%, maker 0.3% — bem
    # mais altas que Binance/Bitget/Gate.io. Um spread bruto de 0.5%-1.5% pode
    # ser INTEIRAMENTE consumido só pela taker fee desta ponta; é exatamente
    # o tipo de falso positivo que o motor de net spread existe pra pegar.
    default_taker_fee = 0.007
    default_maker_fee = 0.003
    supports_ws_orderbook = False
    poll_interval_seconds = 1.5
    withdrawal_fees = {"BTC": 0.0005, "BRL": 0.0}


# ----------------------------------------------------------------------
# Registro / Factory — ponto único de extensão para novas exchanges
# ----------------------------------------------------------------------

CONNECTOR_REGISTRY = {
    "BINANCE": BinanceConnector,
    "BITGET": BitgetConnector,
    "GATEIO": GateIOConnector,
    "MERCADOBITCOIN": MercadoBitcoinConnector,
    "MEXC": MexcConnector,
}


def create_connector(exchange_key: str, credentials=None, fee_overrides=None) -> ExchangeConnector:
    """Fábrica principal. `exchange_key` é o nome amigável usado no resto do
    sistema (ex: 'BINANCE', 'GATEIO'), não o id interno do ccxt."""
    key = exchange_key.upper()
    ConnectorClass = CONNECTOR_REGISTRY.get(key)
    if ConnectorClass is None:
        raise ValueError(
            f"Exchange '{exchange_key}' não está registrada em CONNECTOR_REGISTRY. "
            f"Disponíveis: {list(CONNECTOR_REGISTRY.keys())}"
        )
    return ConnectorClass(credentials=credentials, fee_overrides=fee_overrides)
