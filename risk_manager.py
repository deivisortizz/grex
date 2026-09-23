"""
Gestão de risco/exposição financeira por par.

O padrão central é "reservar antes de executar, liberar depois" (via
`reserved()`, um async context manager). Isso torna a checagem de limite
ATÔMICA em relação a outras oportunidades concorrentes do mesmo par: duas
tasks não podem, cada uma vendo o limite "livre", comprometer capital ao
mesmo tempo e estourar o exposure máximo — o lock por símbolo serializa
exatamente a seção crítica (checar + reservar), não a execução da ordem em si
(que continua rodando fora do lock, sem bloquear outras oportunidades).
"""
import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager

logger = logging.getLogger("RiskManager")


class RiskManager:
    def __init__(self, max_exposure_per_pair: dict[str, float] = None, default_max_exposure: float = 50.0):
        self.max_exposure_per_pair = max_exposure_per_pair or {}
        self.default_max_exposure = default_max_exposure
        self._committed = defaultdict(float)
        self._locks = defaultdict(asyncio.Lock)

    def limit_for(self, symbol: str) -> float:
        return self.max_exposure_per_pair.get(symbol, self.default_max_exposure)

    def committed_for(self, symbol: str) -> float:
        return self._committed[symbol]

    def set_limit(self, symbol: str, max_exposure_quote: float):
        self.max_exposure_per_pair[symbol] = max_exposure_quote

    async def try_reserve(self, symbol: str, amount_quote: float) -> bool:
        async with self._locks[symbol]:
            limit = self.limit_for(symbol)
            if self._committed[symbol] + amount_quote > limit:
                logger.warning(
                    f"[RISCO] Reserva negada para {symbol}: comprometido={self._committed[symbol]:.2f} + "
                    f"solicitado={amount_quote:.2f} > limite={limit:.2f}"
                )
                return False
            self._committed[symbol] += amount_quote
            return True

    async def release(self, symbol: str, amount_quote: float):
        async with self._locks[symbol]:
            self._committed[symbol] = max(0.0, self._committed[symbol] - amount_quote)

    @asynccontextmanager
    async def reserved(self, symbol: str, amount_quote: float):
        """Uso:
            async with risk_manager.reserved(symbol, amount) as ok:
                if not ok:
                    ... registra oportunidade descartada por limite de risco ...
                    return
                ... executa as duas pernas ...
        A liberação acontece automaticamente ao sair do bloco, mesmo em caso
        de exceção durante a execução — o capital nunca fica "preso" comprometido
        por um bug na perna de execução.
        """
        ok = await self.try_reserve(symbol, amount_quote)
        if not ok:
            yield False
            return
        try:
            yield True
        finally:
            await self.release(symbol, amount_quote)
