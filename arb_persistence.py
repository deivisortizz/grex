"""
Persistência assíncrona em SQLite para o motor de arbitragem em pares
exóticos/Tier-2. Reaproveita o mesmo arquivo `trades.db` já usado por
arbitrage_bot.py (DATA_DIR configurável via env var, igual ao resto do
sistema) e a tabela `history` já existente para trades executados — só
adiciona a tabela `opportunities`, que é a peça que faltava: hoje só o que
vira trade é persistido, então nunca dá pra auditar quantas oportunidades
foram vistas e descartadas, nem por qual motivo.

Todas as operações de banco rodam em thread separada via `asyncio.to_thread`
(mesmo padrão de arbitrage_bot.py) para nunca bloquear o event loop principal
— importante aqui porque o volume de oportunidades detectadas (inclusive as
descartadas) pode ser MUITO maior que o de trades executados.
"""
import asyncio
import os
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger("ArbPersistence")


class ArbitragePersistence:
    def __init__(self, data_dir: str, db_filename: str = "trades.db"):
        self.db_path = os.path.join(data_dir, db_filename)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Tabela `history` já existe (criada por arbitrage_bot.py) — não a
            # recriamos aqui pra não duplicar definição, só garantimos que
            # exista (idempotente) para o caso deste módulo rodar sozinho.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    timestamp TEXT,
                    exchange_buy TEXT,
                    exchange_sell TEXT,
                    spread_bruto REAL,
                    lucro_liquido REAL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    exchange_buy TEXT NOT NULL,
                    exchange_sell TEXT NOT NULL,
                    amount_quote REAL,
                    buy_avg_price REAL,
                    sell_avg_price REAL,
                    gross_spread_pct REAL,
                    net_spread_pct REAL,
                    fee_buy_pct REAL,
                    fee_sell_pct REAL,
                    withdrawal_fee_quote REAL,
                    depth_ok BOOLEAN,
                    status TEXT NOT NULL,   -- 'executed' | 'discarded_low_net' | 'discarded_thin_book' |
                                            -- 'discarded_risk_limit' | 'discarded_cooldown' | 'leg_failure'
                    reason TEXT,
                    executed_trade_id INTEGER
                )
            ''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_symbol ON opportunities(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status)")
            conn.commit()
        logger.info(f"📂 Persistência de arbitragem pronta em {self.db_path}")

    # ------------------------------------------------------------------
    # Escrita síncrona (roda em thread via asyncio.to_thread pelos métodos
    # públicos abaixo) — nunca chamada diretamente do event loop.
    # ------------------------------------------------------------------
    def _sync_record_opportunity(self, evaluation, status: str, executed_trade_id=None, user_id=None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO opportunities (
                    user_id, created_at, symbol, exchange_buy, exchange_sell, amount_quote,
                    buy_avg_price, sell_avg_price, gross_spread_pct, net_spread_pct,
                    fee_buy_pct, fee_sell_pct, withdrawal_fee_quote, depth_ok,
                    status, reason, executed_trade_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, datetime.utcnow().isoformat(), evaluation.symbol,
                evaluation.buy_exchange, evaluation.sell_exchange, evaluation.amount_quote,
                evaluation.buy_avg_price, evaluation.sell_avg_price,
                evaluation.vwap_gross_pct, evaluation.net_spread_pct,
                evaluation.fee_buy_pct, evaluation.fee_sell_pct, evaluation.withdrawal_fee_quote,
                bool(evaluation.depth_ok), status, evaluation.reason, executed_trade_id
            ))
            conn.commit()
            return cursor.lastrowid

    def _sync_record_trade(self, timestamp, ex_buy, ex_sell, gross_pct, net_profit_quote, user_id=None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO history (timestamp, exchange_buy, exchange_sell, spread_bruto, lucro_liquido, user_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (timestamp, ex_buy, ex_sell, gross_pct, net_profit_quote, user_id))
            conn.commit()
            return cursor.lastrowid

    def _sync_get_opportunity_stats(self, symbol=None):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = "SELECT status, COUNT(*) as n FROM opportunities"
            params = ()
            if symbol:
                query += " WHERE symbol = ?"
                params = (symbol,)
            query += " GROUP BY status"
            cursor.execute(query, params)
            return {row["status"]: row["n"] for row in cursor.fetchall()}

    # ------------------------------------------------------------------
    # API pública assíncrona
    # ------------------------------------------------------------------
    async def record_opportunity(self, evaluation, status: str, executed_trade_id=None, user_id=None) -> int:
        try:
            return await asyncio.to_thread(
                self._sync_record_opportunity, evaluation, status, executed_trade_id, user_id
            )
        except Exception as e:
            logger.error(f"Falha ao registrar oportunidade ({evaluation.symbol}): {e}")
            return -1

    async def record_trade(self, ex_buy, ex_sell, gross_pct, net_profit_quote, user_id=None) -> int:
        ts = datetime.utcnow().isoformat()
        try:
            return await asyncio.to_thread(
                self._sync_record_trade, ts, ex_buy, ex_sell, gross_pct, net_profit_quote, user_id
            )
        except Exception as e:
            logger.error(f"Falha ao registrar trade executado ({ex_buy}->{ex_sell}): {e}")
            return -1

    async def get_opportunity_stats(self, symbol=None) -> dict:
        """Contagem de oportunidades por status — útil pra dashboard/auditoria
        de quão perto (ou longe) a estratégia está de gerar trades executáveis."""
        return await asyncio.to_thread(self._sync_get_opportunity_stats, symbol)
