"""
Motor de cálculo de spread líquido (net spread).

O ponto central deste módulo é `vwap_fill`: em vez de calcular o spread a
partir do topo do livro (best bid/ask), ele "anda" pelos níveis reais do
orderbook para descobrir o preço médio de execução (VWAP) necessário para
preencher o tamanho de ordem pretendido. Isso é o que evita o falso positivo
clássico de par exótico/baixa liquidez: o topo do livro mostra um spread
ótimo, mas só tem profundidade pra uma fração do tamanho da ordem — o
restante "cai" em níveis piores e o spread real desaparece (ou vira prejuízo).
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("SpreadEngine")


@dataclass
class FillEstimate:
    avg_price: float | None
    base_filled: float
    book_exhausted: bool  # True = o livro visível não tinha profundidade suficiente


def vwap_fill_for_quote_amount(levels, target_quote_amount: float) -> FillEstimate:
    """Caminha os níveis (lista [preço, volume_base], ordenados do melhor pro
    pior) até preencher `target_quote_amount` em moeda de COTAÇÃO. Usado para
    a perna de COMPRA (anda o lado ASK)."""
    remaining_quote = target_quote_amount
    quote_spent = 0.0
    base_filled = 0.0

    for price, volume in levels:
        if price <= 0 or volume <= 0:
            continue
        level_quote_notional = price * volume
        if level_quote_notional >= remaining_quote:
            partial_base = remaining_quote / price
            quote_spent += remaining_quote
            base_filled += partial_base
            remaining_quote = 0.0
            break
        quote_spent += level_quote_notional
        base_filled += volume
        remaining_quote -= level_quote_notional

    book_exhausted = remaining_quote > 1e-12
    avg_price = (quote_spent / base_filled) if base_filled > 0 else None
    return FillEstimate(avg_price=avg_price, base_filled=base_filled, book_exhausted=book_exhausted)


def vwap_fill_for_base_amount(levels, target_base_amount: float) -> FillEstimate:
    """Caminha os níveis até vender `target_base_amount` em moeda BASE. Usado
    para a perna de VENDA (anda o lado BID) com a quantidade base realmente
    obtida na perna de compra."""
    remaining_base = target_base_amount
    quote_received = 0.0
    base_filled = 0.0

    for price, volume in levels:
        if price <= 0 or volume <= 0:
            continue
        if volume >= remaining_base:
            quote_received += remaining_base * price
            base_filled += remaining_base
            remaining_base = 0.0
            break
        quote_received += volume * price
        base_filled += volume
        remaining_base -= volume

    book_exhausted = remaining_base > 1e-12
    avg_price = (quote_received / base_filled) if base_filled > 0 else None
    return FillEstimate(avg_price=avg_price, base_filled=base_filled, book_exhausted=book_exhausted)


@dataclass
class SpreadEvaluation:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    amount_quote: float

    top_of_book_gross_pct: float = 0.0   # spread "ingênuo" (best ask vs best bid) — só informativo
    vwap_gross_pct: float = 0.0          # spread real considerando a profundidade necessária
    net_spread_pct: float = 0.0

    buy_avg_price: float | None = None
    sell_avg_price: float | None = None

    fee_buy_pct: float = 0.0
    fee_sell_pct: float = 0.0
    withdrawal_fee_quote: float = 0.0

    depth_ok: bool = False
    viable: bool = False
    reason: str = ""


class NetSpreadCalculator:
    def __init__(self, min_net_spread_pct: float, min_depth_multiplier: float = 1.5):
        """
        min_net_spread_pct: piso de spread líquido pra considerar a oportunidade
            executável (ex: 0.5 para 0.5%).
        min_depth_multiplier: exige que a profundidade TOTAL visível no livro
            (não só o necessário pra este trade) seja pelo menos essa quantas
            vezes o tamanho pretendido — margem de segurança extra contra um
            livro que está prestes a ser consumido por outro participante.
        """
        self.min_net_spread_pct = min_net_spread_pct
        self.min_depth_multiplier = min_depth_multiplier

    def evaluate(
        self,
        symbol: str,
        buy_exchange: str,
        sell_exchange: str,
        buy_asks: list,   # [[preço, volume_base], ...] ordenado do melhor (menor) pro pior
        sell_bids: list,  # [[preço, volume_base], ...] ordenado do melhor (maior) pro pior
        amount_quote: float,
        fee_buy_pct: float,
        fee_sell_pct: float,
        withdrawal_fee_base: float = 0.0,
    ) -> SpreadEvaluation:
        ev = SpreadEvaluation(
            symbol=symbol, buy_exchange=buy_exchange, sell_exchange=sell_exchange,
            amount_quote=amount_quote, fee_buy_pct=fee_buy_pct, fee_sell_pct=fee_sell_pct,
        )

        if not buy_asks or not sell_bids:
            ev.reason = "Livro de ordens vazio em uma das pontas."
            return ev

        best_ask = buy_asks[0][0]
        best_bid = sell_bids[0][0]
        ev.top_of_book_gross_pct = (best_bid / best_ask - 1) * 100 if best_ask > 0 else 0.0

        # 1. Checagem de profundidade total (antes de gastar tempo com VWAP):
        # soma o notional disponível nos níveis visíveis e exige uma folga
        # sobre o tamanho pretendido.
        total_ask_notional = sum(p * v for p, v in buy_asks)
        total_bid_base = sum(v for _, v in sell_bids)
        required_base_estimate = amount_quote / best_ask if best_ask > 0 else 0.0

        if total_ask_notional < amount_quote * self.min_depth_multiplier:
            ev.reason = (f"Profundidade insuficiente no lado da compra ({buy_exchange}): "
                         f"livro visível cobre {total_ask_notional:.2f} vs. mínimo exigido "
                         f"{amount_quote * self.min_depth_multiplier:.2f} ({self.min_depth_multiplier}x o trade).")
            return ev

        if total_bid_base < required_base_estimate * self.min_depth_multiplier:
            ev.reason = (f"Profundidade insuficiente no lado da venda ({sell_exchange}): "
                         f"livro visível cobre {total_bid_base:.6f} unidades vs. mínimo exigido "
                         f"{required_base_estimate * self.min_depth_multiplier:.6f}.")
            return ev

        # 2. VWAP real de cada perna — aqui é onde o falso positivo de livro
        # raso é pego: se o preço médio de execução for pior que o topo do
        # livro por causa da profundidade, o spread cai (ou vira negativo).
        buy_fill = vwap_fill_for_quote_amount(buy_asks, amount_quote)
        if buy_fill.avg_price is None or buy_fill.book_exhausted:
            ev.reason = f"Livro da compra ({buy_exchange}) esgotou antes de preencher {amount_quote} de notional."
            return ev

        sell_fill = vwap_fill_for_base_amount(sell_bids, buy_fill.base_filled)
        if sell_fill.avg_price is None or sell_fill.book_exhausted:
            ev.reason = f"Livro da venda ({sell_exchange}) esgotou antes de vender {buy_fill.base_filled:.6f} unidades."
            return ev

        ev.buy_avg_price = buy_fill.avg_price
        ev.sell_avg_price = sell_fill.avg_price
        ev.vwap_gross_pct = (sell_fill.avg_price / buy_fill.avg_price - 1) * 100

        # 3. Custos: taker fee de cada ponta + taxa de saque (se a estratégia
        # exigir transferência física do ativo entre exchanges — em arbitragem
        # com saldo pré-financiado nas duas pontas, withdrawal_fee_base=0).
        cost_quote = amount_quote * (1 + fee_buy_pct)
        revenue_quote = (buy_fill.base_filled * sell_fill.avg_price) * (1 - fee_sell_pct)

        withdrawal_fee_quote = withdrawal_fee_base * sell_fill.avg_price if withdrawal_fee_base else 0.0
        ev.withdrawal_fee_quote = withdrawal_fee_quote

        net_profit_quote = revenue_quote - cost_quote - withdrawal_fee_quote
        ev.net_spread_pct = (net_profit_quote / amount_quote) * 100
        ev.depth_ok = True

        if ev.net_spread_pct >= self.min_net_spread_pct:
            ev.viable = True
            ev.reason = "OK"
        else:
            ev.viable = False
            ev.reason = (f"Net spread {ev.net_spread_pct:.4f}% abaixo do piso "
                         f"{self.min_net_spread_pct:.4f}% após taxas "
                         f"(buy={fee_buy_pct:.4%}, sell={fee_sell_pct:.4%}, "
                         f"saque={withdrawal_fee_quote:.4f} na cotação).")

        return ev
