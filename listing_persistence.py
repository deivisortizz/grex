"""
Persistência dedicada do CEX Listing Sniper (item 5).

Banco próprio (`DATA_DIR/listing_sniper.db`), separado dos outros bots —
mesma filosofia de isolamento já usada pelo Copy Sniper (copy_sniper_history)
e pelo motor de arbitragem exótica (opportunities). Duas tabelas:

- `announcements`: TODO anúncio processado pela fonte, mesmo os descartados
  pelo extrator (delisting, futures, promoção etc.) — com o motivo do
  descarte e, quando aplicável, a latência entre a publicação do anúncio e o
  instante em que o sniper terminou de processá-lo. Essa métrica de latência
  é o KPI central da estratégia: se estiver alta, o "efeito eufórico dos
  primeiros 1-3s" já passou antes da gente sequer decidir comprar.

- `listing_trades`: cada compra disparada e seu ciclo de vida (TP/SL/saída
  manual/timeout), com preço de entrada/saída e PnL.
"""
import asyncio
import os
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger("ListingPersistence")


class ListingPersistence:
    def __init__(self, data_dir: str, db_filename: str = "listing_sniper.db"):
        self.db_path = os.path.join(data_dir, db_filename)
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT,
                    ticker TEXT,
                    confidence TEXT,
                    status TEXT NOT NULL,        -- 'excluded' | 'no_match' | 'matched_no_users' |
                                                  -- 'matched_traded' | 'matched_trade_failed'
                    excluded_reason TEXT,
                    published_at_ms INTEGER,
                    detected_at_ms INTEGER NOT NULL,
                    detection_latency_ms INTEGER,  -- detected_at_ms - published_at_ms (KPI central)
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS listing_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    announcement_id INTEGER,
                    user_id INTEGER,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    buy_order_id TEXT,
                    buy_price REAL,
                    amount_quote REAL,
                    amount_base REAL,
                    tp_pct REAL,
                    sl_pct REAL,
                    status TEXT NOT NULL,       -- 'open' | 'closed_tp' | 'closed_sl' | 'closed_timeout' |
                                                 -- 'closed_manual' | 'failed'
                    exit_order_id TEXT,
                    exit_price REAL,
                    pnl_quote REAL,
                    pnl_pct REAL,
                    entry_latency_ms INTEGER,   -- tempo entre detecção do anúncio e ordem de compra disparada
                    entry_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    exit_at TEXT,
                    error_reason TEXT,
                    FOREIGN KEY(announcement_id) REFERENCES announcements(id)
                )
            ''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_announcements_exchange ON announcements(exchange)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON listing_trades(status)")
            conn.commit()
        logger.info(f"📂 Persistência do Listing Sniper pronta em {self.db_path}")

    # ------------------------------------------------------------------
    # Escrita síncrona (chamada via asyncio.to_thread pelos métodos públicos)
    # ------------------------------------------------------------------
    def _sync_record_announcement(self, exchange, title, url, ticker, confidence, status,
                                   excluded_reason, published_at_ms, detected_at_ms) -> int:
        latency_ms = (detected_at_ms - published_at_ms) if published_at_ms else None
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO announcements (
                    exchange, title, url, ticker, confidence, status, excluded_reason,
                    published_at_ms, detected_at_ms, detection_latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (exchange, title, url, ticker, confidence, status, excluded_reason,
                  published_at_ms, detected_at_ms, latency_ms))
            conn.commit()
            return cursor.lastrowid

    def _sync_record_trade_open(self, announcement_id, user_id, exchange, symbol, buy_order_id,
                                 buy_price, amount_quote, amount_base, tp_pct, sl_pct, entry_latency_ms) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO listing_trades (
                    announcement_id, user_id, exchange, symbol, buy_order_id, buy_price,
                    amount_quote, amount_base, tp_pct, sl_pct, status, entry_latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            ''', (announcement_id, user_id, exchange, symbol, buy_order_id, buy_price,
                  amount_quote, amount_base, tp_pct, sl_pct, entry_latency_ms))
            conn.commit()
            return cursor.lastrowid

    def _sync_record_trade_failed(self, announcement_id, user_id, exchange, symbol, error_reason) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO listing_trades (announcement_id, user_id, exchange, symbol, status, error_reason)
                VALUES (?, ?, ?, ?, 'failed', ?)
            ''', (announcement_id, user_id, exchange, symbol, error_reason))
            conn.commit()
            return cursor.lastrowid

    def _sync_close_trade(self, trade_id, status, exit_order_id, exit_price, pnl_quote, pnl_pct):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE listing_trades
                SET status = ?, exit_order_id = ?, exit_price = ?, pnl_quote = ?, pnl_pct = ?,
                    exit_at = ?
                WHERE id = ?
            ''', (status, exit_order_id, exit_price, pnl_quote, pnl_pct, datetime.utcnow().isoformat(), trade_id))
            conn.commit()

    def _sync_get_open_trades(self, user_id=None):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT * FROM listing_trades WHERE status = 'open' AND user_id = ?", (user_id,))
            else:
                cursor.execute("SELECT * FROM listing_trades WHERE status = 'open'")
            return [dict(row) for row in cursor.fetchall()]

    def _sync_get_recent_trades(self, user_id=None, limit=50):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT * FROM listing_trades WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
            else:
                cursor.execute("SELECT * FROM listing_trades ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def _sync_get_avg_detection_latency_ms(self, exchange=None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if exchange:
                cursor.execute(
                    "SELECT AVG(detection_latency_ms) FROM announcements WHERE detection_latency_ms IS NOT NULL AND exchange = ?",
                    (exchange,)
                )
            else:
                cursor.execute("SELECT AVG(detection_latency_ms) FROM announcements WHERE detection_latency_ms IS NOT NULL")
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else None

    # ------------------------------------------------------------------
    # API pública assíncrona
    # ------------------------------------------------------------------
    async def record_announcement(self, exchange, title, url, ticker, confidence, status,
                                   excluded_reason, published_at_ms, detected_at_ms) -> int:
        try:
            return await asyncio.to_thread(
                self._sync_record_announcement, exchange, title, url, ticker, confidence,
                status, excluded_reason, published_at_ms, detected_at_ms
            )
        except Exception as e:
            logger.error(f"Falha ao registrar anúncio ({exchange}): {e}")
            return -1

    async def record_trade_open(self, announcement_id, user_id, exchange, symbol, buy_order_id,
                                 buy_price, amount_quote, amount_base, tp_pct, sl_pct, entry_latency_ms) -> int:
        try:
            return await asyncio.to_thread(
                self._sync_record_trade_open, announcement_id, user_id, exchange, symbol, buy_order_id,
                buy_price, amount_quote, amount_base, tp_pct, sl_pct, entry_latency_ms
            )
        except Exception as e:
            logger.error(f"Falha ao registrar trade aberto ({exchange}/{symbol}): {e}")
            return -1

    async def record_trade_failed(self, announcement_id, user_id, exchange, symbol, error_reason) -> int:
        try:
            return await asyncio.to_thread(
                self._sync_record_trade_failed, announcement_id, user_id, exchange, symbol, error_reason
            )
        except Exception as e:
            logger.error(f"Falha ao registrar trade falho ({exchange}/{symbol}): {e}")
            return -1

    async def close_trade(self, trade_id, status, exit_order_id, exit_price, pnl_quote, pnl_pct):
        try:
            await asyncio.to_thread(self._sync_close_trade, trade_id, status, exit_order_id, exit_price, pnl_quote, pnl_pct)
        except Exception as e:
            logger.error(f"Falha ao fechar trade {trade_id}: {e}")

    async def get_open_trades(self, user_id=None) -> list:
        return await asyncio.to_thread(self._sync_get_open_trades, user_id)

    async def get_recent_trades(self, user_id=None, limit=50) -> list:
        return await asyncio.to_thread(self._sync_get_recent_trades, user_id, limit)

    async def get_avg_detection_latency_ms(self, exchange=None):
        return await asyncio.to_thread(self._sync_get_avg_detection_latency_ms, exchange)
