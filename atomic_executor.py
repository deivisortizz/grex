"""
Execução atômica (paralela) das duas pernas de uma oportunidade de arbitragem,
com tratamento explícito de leg risk.

[Contexto] No motor espacial já existente (arbitrage_bot.py::execute_real_trade),
as duas ordens são disparadas com `asyncio.gather(..., return_exceptions=False)`.
Isso paraleliza bem o caso feliz, mas se UMA perna falhar (rejeição da exchange,
saldo insuficiente, rate limit, etc.) enquanto a OUTRA já executou, o gather
levanta a exceção e o código simplesmente loga e retorna — a perna que executou
fica como uma posição nua, sem nenhuma tentativa de neutralização. Esse módulo
resolve exatamente isso: usa `return_exceptions=True` para nunca perder o
resultado de nenhuma perna, e dispara uma ordem de neutralização de emergência
na perna que executou quando a outra falha.
"""
import asyncio
import logging

logger = logging.getLogger("AtomicExecutor")


class LegExecutionError(Exception):
    def __init__(self, message, buy_result=None, sell_result=None, buy_error=None, sell_error=None, unwound=False):
        super().__init__(message)
        self.buy_result = buy_result
        self.sell_result = sell_result
        self.buy_error = buy_error
        self.sell_error = sell_error
        self.unwound = unwound  # True se a perna sobrevivente foi neutralizada com sucesso


class AtomicExecutor:
    async def execute_pair(self, buy_connector, sell_connector, symbol: str, base_amount: float):
        """Dispara compra e venda em paralelo. Em caso de sucesso total,
        retorna (buy_result, sell_result). Em caso de falha de UMA perna,
        tenta neutralizar a perna que executou e levanta LegExecutionError
        (o chamador decide o que fazer — ex: registrar no ledger, alertar)."""
        buy_task = asyncio.create_task(buy_connector.market_buy(symbol, base_amount))
        sell_task = asyncio.create_task(sell_connector.market_sell(symbol, base_amount))

        buy_result, sell_result = await asyncio.gather(buy_task, sell_task, return_exceptions=True)

        buy_ok = not isinstance(buy_result, Exception)
        sell_ok = not isinstance(sell_result, Exception)

        if buy_ok and sell_ok:
            return buy_result, sell_result

        if not buy_ok and not sell_ok:
            # Nenhuma perna executou — sem leg risk, só reporta a falha dupla.
            logger.error(f"[{symbol}] Ambas as pernas falharam. Compra: {buy_result} | Venda: {sell_result}")
            raise LegExecutionError(f"Ambas as pernas falharam em {symbol}", buy_error=buy_result, sell_error=sell_result)

        if buy_ok and not sell_ok:
            logger.error(f"⚠️ [LEG RISK] {symbol}: compra executada mas venda falhou ({sell_result}). "
                         f"Tentando neutralizar a posição comprada de emergência...")
            unwound = False
            try:
                bought_amount = float(buy_result.get("filled") or base_amount)
                emergency = await sell_connector.market_sell(symbol, bought_amount)
                unwound = True
                logger.warning(f"[LEG RISK] {symbol}: posição neutralizada via venda de emergência "
                                f"(ordem {emergency.get('id')}).")
            except Exception as unwind_err:
                logger.critical(
                    f"🔴 [LEG RISK CRÍTICO] {symbol}: falha ao neutralizar posição COMPRADA "
                    f"({buy_result.get('id') if isinstance(buy_result, dict) else '?'})! "
                    f"AÇÃO MANUAL NECESSÁRIA NA EXCHANGE DE COMPRA. "
                    f"Erro original da venda: {sell_result} | Erro no unwind: {unwind_err}"
                )
            raise LegExecutionError(
                f"Falha na perna de venda em {symbol}", buy_result=buy_result, sell_error=sell_result, unwound=unwound
            )

        # sell_ok and not buy_ok
        logger.error(f"⚠️ [LEG RISK] {symbol}: venda executada mas compra falhou ({buy_result}). "
                     f"Tentando recomprar de emergência para neutralizar a posição vendida...")
        unwound = False
        try:
            sold_amount = float(sell_result.get("filled") or base_amount)
            emergency = await buy_connector.market_buy(symbol, sold_amount)
            unwound = True
            logger.warning(f"[LEG RISK] {symbol}: posição neutralizada via recompra de emergência "
                            f"(ordem {emergency.get('id')}).")
        except Exception as unwind_err:
            logger.critical(
                f"🔴 [LEG RISK CRÍTICO] {symbol}: falha ao neutralizar posição VENDIDA "
                f"({sell_result.get('id') if isinstance(sell_result, dict) else '?'})! "
                f"AÇÃO MANUAL NECESSÁRIA NA EXCHANGE DE VENDA. "
                f"Erro original da compra: {buy_result} | Erro no unwind: {unwind_err}"
            )
        raise LegExecutionError(
            f"Falha na perna de compra em {symbol}", sell_result=sell_result, buy_error=buy_result, unwound=unwound
        )
