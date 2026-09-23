"""
Extrator ultra-rápido de ticker a partir do texto de anúncios de listagem.

[Base empírica] Os padrões abaixo foram validados contra uma amostra real de
~50 anúncios ao vivo da API pública da MEXC (`/api/v3/announcements`), não
inventados. Essa amostra mostrou algo importante: **a maioria dos anúncios
NÃO é uma listagem spot nova** — é deslistagem, ajuste de funding rate,
futures, pré-IPO, upgrade de rede, copy trade, promoção etc. Um extrator que
só soubesse "puxar o ticker" sem excluir esse ruído dispararia compras em
cima de deslistagens e produtos de futures que o motor nem sabe operar. Por
isso a exclusão (`EXCLUDE_PATTERNS`) roda ANTES da extração e é tão
importante quanto os padrões de inclusão.

Puramente regex — sem dependência de NLP pesada — porque o objetivo é
processar um payload de texto em microssegundos, antes que humanos leiam o
comunicado. É "leve" de propósito: mais robustez viria de um parser mais
esperto, mas custaria a latência que é o único edge desta estratégia.
"""
import re
from dataclasses import dataclass

# Frases que indicam que o anúncio NÃO é uma listagem spot nova acionável.
# Checadas primeiro (case-insensitive) — qualquer match aqui descarta o
# anúncio sem gastar tempo tentando extrair um ticker dele.
EXCLUDE_PATTERNS = [
    r"\bdelisting\b",
    r"\bsuspension of\b",
    r"\bdeposits and withdrawals\b",
    r"\bfunding rate\b",
    r"\bmaximum leverage\b",
    r"\bcontract swap\b",
    r"\bnetwork upgrade\b",
    r"\bcopy trade\b",
    r"\bpre-ipo\b",
    r"\bstock futures?\b",
    r"\busdt-m futures?\b",
    r"\busdc-m futures?\b",
    r"\bperpetual futures?\b",
    r"\badjustment to\b",
    r"\bsystem upgrade\b",
    r"\btoken swap into\b",
    r"\brebase\b.*\bfutures\b",
    # [FIX] Validado contra amostra real: "Airdrop+:Celebrate Bitcoin (BTC)
    # Party with $50,000 in BTC..." batia no fallback de parênteses e virava
    # um falso positivo de "listagem de BTC" — conteúdo puramente
    # promocional. Excluído explicitamente, defesa em profundidade além de
    # já ter removido o padrão de fallback que causava isso (ver abaixo).
    r"\bairdrop\b", r"\bcashback\b", r"\bgiveaway\b", r"\bcarnival\b",
    r"\bcompete for\b", r"\bwin a\b", r"\bunlock \$", r"\brewards?\b",
    r"\bbonus\b", r"\bspin to win\b",
]

# Padrões de inclusão, em ORDEM DE PRIORIDADE (o primeiro que bater vence).
# Cada um tem um grupo nomeado "ticker". Testados contra títulos reais da MEXC.
INCLUDE_PATTERNS = [
    # "First in Market: MONITOR Now Live on MEXC Meme+" / "SCHIFFY Now Live on MEXC"
    (re.compile(r"(?:First in Market:\s*)?(?P<ticker>[A-Z][A-Z0-9]{1,14})\s+(?:Is\s+)?Now Live on\b", re.IGNORECASE), "now_live"),
    # "X (TICKER) is now available" / "Listing of TICKER" / genérico com parênteses
    (re.compile(r"\bwill list\b.*?\(\s*(?P<ticker>[A-Z0-9]{2,15})\s*\)", re.IGNORECASE), "will_list_paren"),
    (re.compile(r"\bwill list\s+(?P<ticker>[A-Z0-9]{2,15})\b", re.IGNORECASE), "will_list_bare"),
    (re.compile(r"\bnew listing[:\-]?\s*(?P<ticker>[A-Z0-9]{2,15})\b", re.IGNORECASE), "new_listing"),
    (re.compile(r"\blists?\s+(?P<ticker>[A-Z0-9]{2,15})\s*/\s*(?:USDT|USDC|USD|BTC)\b", re.IGNORECASE), "pair_notation"),
    # [FIX] Removido o fallback genérico "qualquer coisa entre parênteses"
    # (ex: "(TICKER)"). Validado contra amostra real: ele capturou "BTC" de
    # um post promocional de airdrop ("Celebrate Bitcoin (BTC) Party...").
    # Preferimos DEIXAR PASSAR uma listagem real ocasional a arriscar comprar
    # o token errado com dinheiro real por causa de um padrão frouxo demais —
    # cada match aqui vira uma ordem de mercado de verdade.
    (re.compile(r"\btoken\s*\(\s*(?P<ticker>[A-Z0-9]{2,15})\s*\)\s+(?:launches?|listed|now available)\b", re.IGNORECASE), "token_paren_launch"),
]

# Sufixos comuns de par de negociação, removidos se vierem colados ao ticker
# (ex: "PEPEUSDT" -> "PEPE") — comum em títulos de exchanges chinesas/Tier-2.
_TRADING_SUFFIXES = ("USDT", "USDC", "USD", "BTC", "ETH")


@dataclass
class ExtractionResult:
    matched: bool
    ticker: str | None = None
    confidence: str = "none"   # "high" (now_live/will_list) | "medium" (new_listing/pair) | "low" (fallback)
    pattern_name: str | None = None
    excluded_reason: str | None = None


_CONFIDENCE_BY_PATTERN = {
    "now_live": "high",
    "will_list_paren": "high",
    "will_list_bare": "high",
    "new_listing": "medium",
    "pair_notation": "medium",
    "token_paren_launch": "medium",
}


def _strip_trading_suffix(ticker: str) -> str:
    upper = ticker.upper()
    for suffix in _TRADING_SUFFIXES:
        if upper.endswith(suffix) and len(upper) > len(suffix) + 1:
            return upper[: -len(suffix)]
    return upper


def extract_ticker(text: str) -> ExtractionResult:
    """Extrai o ticker de um título/corpo de anúncio. Não faz I/O — puro CPU,
    pensado para rodar em microssegundos por chamada."""
    if not text:
        return ExtractionResult(matched=False, excluded_reason="empty_text")

    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return ExtractionResult(matched=False, excluded_reason=pattern)

    for regex, name in INCLUDE_PATTERNS:
        m = regex.search(text)
        if m:
            raw_ticker = m.group("ticker")
            ticker = _strip_trading_suffix(raw_ticker)
            if len(ticker) < 2:
                continue  # ticker degenerado demais (ex: sobrou 1 letra), tenta o próximo padrão
            return ExtractionResult(
                matched=True, ticker=ticker,
                confidence=_CONFIDENCE_BY_PATTERN.get(name, "low"),
                pattern_name=name,
            )

    return ExtractionResult(matched=False, excluded_reason="no_pattern_matched")
