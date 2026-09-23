"""
CEX Listing Sniper — microsserviço independente.

Processo próprio (mesmo padrão de copy_sniper.py/solana_sniper.py): cofre
Fernet reaproveitando a MESMA chave mestra dos outros bots (DATA_DIR/.master.key
— uma chave decripta tudo no ecossistema, nenhum bot fica "surdo" às
credenciais de outro), WebSocket de controle autenticado por JWT, SQLite
dedicado (listing_sniper.db). Compõe os módulos menores:

  listing_sources.py          -> ingestão de anúncios (item 1)
  ticker_extractor.py         -> extração/filtro de ticker (item 2)
  listing_execution_engine.py -> compra a mercado + TP/SL (itens 3 e 4)
  listing_persistence.py      -> histórico de anúncios e trades (item 5)
"""
import asyncio
import json
import logging
import os
import sqlite3
import sys
import time

import aiohttp
import jwt
import websockets
from dotenv import load_dotenv
from cryptography.fernet import Fernet

from listing_sources import create_source, SOURCE_REGISTRY
from ticker_extractor import extract_ticker
from listing_persistence import ListingPersistence
from listing_execution_engine import ListingExecutionEngine, ListingTradeConfig

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('ListingSniper')

DATA_DIR = os.getenv('DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
JWT_SECRET = os.getenv("JWT_SECRET", "multi-tenant-super-secret-fallback")
JWT_ALGORITHM = "HS256"
WS_PORT = int(os.getenv("LISTING_SNIPER_WS_PORT", "8769"))


class ListingSniperService:
    def __init__(self):
        self.connected_clients = set()
        self.init_crypto()
        self.persistence = ListingPersistence(DATA_DIR)
        self.execution_engine = ListingExecutionEngine(self.persistence, self.cipher)
        self.execution_engine.on_trade_event = self._broadcast_trade_event
        self.init_db()

    # ------------------------------------------------------------------
    # Cofre — reaproveita a MESMA chave mestra dos outros bots
    # ------------------------------------------------------------------
    def init_crypto(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        key_path = os.path.join(DATA_DIR, '.master.key')
        # [IMPORTANTE] Não gera uma chave própria: reaproveita
        # DATA_DIR/.master.key, a MESMA usada por solana_core.py,
        # arbitrage_bot.py e base_meme_sniper.py. Uma chave mestra decripta
        # tudo no ecossistema — gerar uma nova aqui deixaria as credenciais
        # cadastradas neste serviço ilegíveis por qualquer outro processo.
        if not os.path.exists(key_path):
            master_key = Fernet.generate_key()
            with open(key_path, 'wb') as f:
                f.write(master_key)
            logger.info("⚠️ [COFRE] Chave Mestra não encontrada. Gerando nova (primeira vez do ecossistema).")
        else:
            with open(key_path, 'rb') as f:
                master_key = f.read()
        self.cipher = Fernet(master_key)
        logger.info("🔑 [COFRE] Chave Mestra carregada com sucesso no Listing Sniper.")

    def encrypt_val(self, val: str) -> str:
        if not val:
            return ""
        return self.cipher.encrypt(val.encode()).decode()

    def decrypt_val(self, val: str) -> str:
        if not val:
            return ""
        try:
            return self.cipher.decrypt(val.encode()).decode()
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # SQLite dedicado — credenciais + configuração de armamento por usuário
    # ------------------------------------------------------------------
    def init_db(self):
        db_path = os.path.join(DATA_DIR, 'listing_sniper.db')
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    exchange TEXT NOT NULL,
                    key_encrypted TEXT NOT NULL,
                    secret_encrypted TEXT NOT NULL,
                    password_encrypted TEXT,
                    trade_amount_quote REAL DEFAULT 20.0,
                    tp_pct REAL DEFAULT 50.0,
                    sl_pct REAL DEFAULT 15.0,
                    max_hold_seconds REAL DEFAULT 300.0,
                    is_armed BOOLEAN DEFAULT 0,
                    UNIQUE(user_id, exchange)
                )
            ''')
            conn.commit()
        self.db_path = db_path

    def _sync_save_credentials(self, user_id, exchange, apikey, secret, password,
                                trade_amount_quote, tp_pct, sl_pct, max_hold_seconds):
        enc_key = self.encrypt_val(apikey)
        enc_secret = self.encrypt_val(secret)
        enc_password = self.encrypt_val(password) if password else None
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO credentials (user_id, exchange, key_encrypted, secret_encrypted, password_encrypted,
                                          trade_amount_quote, tp_pct, sl_pct, max_hold_seconds, is_armed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(user_id, exchange) DO UPDATE SET
                    key_encrypted = excluded.key_encrypted,
                    secret_encrypted = excluded.secret_encrypted,
                    password_encrypted = excluded.password_encrypted,
                    trade_amount_quote = excluded.trade_amount_quote,
                    tp_pct = excluded.tp_pct,
                    sl_pct = excluded.sl_pct,
                    max_hold_seconds = excluded.max_hold_seconds
            ''', (user_id, exchange, enc_key, enc_secret, enc_password, trade_amount_quote, tp_pct, sl_pct, max_hold_seconds))
            conn.commit()

    def _sync_set_armed(self, user_id, exchange, armed: bool):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE credentials SET is_armed = ? WHERE user_id = ? AND exchange = ?",
                           (1 if armed else 0, user_id, exchange))
            conn.commit()

    def _sync_get_all_armed(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM credentials WHERE is_armed = 1")
            return [dict(row) for row in cursor.fetchall()]

    def _sync_get_user_exchanges(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT exchange, is_armed, trade_amount_quote, tp_pct, sl_pct, max_hold_seconds "
                           "FROM credentials WHERE user_id = ?", (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    async def boot_armed_users(self):
        """Re-arma no execution_engine todo usuário que estava armado antes
        do processo reiniciar (persistência sobrevive a restart/deploy)."""
        rows = await asyncio.to_thread(self._sync_get_all_armed)
        for row in rows:
            try:
                config = ListingTradeConfig(
                    trade_amount_quote=row["trade_amount_quote"], tp_pct=row["tp_pct"],
                    sl_pct=row["sl_pct"], max_hold_seconds=row["max_hold_seconds"],
                )
                self.execution_engine.arm_user(row["user_id"], row["exchange"], row, config)
            except Exception as e:
                logger.error(f"Erro ao rearmar usuário {row['user_id']} em {row['exchange']} no boot: {e}")
        if rows:
            logger.info(f"🟢 [COFRE] {len(rows)} usuário(s) rearmado(s) a partir do banco.")

    # ------------------------------------------------------------------
    # Ingestão + extração — o coração da latência da estratégia
    # ------------------------------------------------------------------
    async def poll_source_loop(self, exchange_key: str):
        """Um loop de polling dedicado por exchange, só ativo (faz requisições
        de verdade) enquanto houver ao menos um usuário armado nela — evita
        gastar o rate limit da API de anúncios à toa quando ninguém vai agir
        sobre o resultado."""
        source = create_source(exchange_key)
        seen = set()

        async with aiohttp.ClientSession() as session:
            while True:
                if not self.execution_engine.has_armed_users(exchange_key):
                    await asyncio.sleep(5)
                    continue

                announcements = await source.fetch_latest(session)

                # Processa do mais antigo pro mais novo (preserva a ordem
                # cronológica real de detecção nos logs/broadcast).
                for ann in reversed(announcements):
                    dedup_key = ann.url or ann.title
                    if not dedup_key or dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    if len(seen) > 3000:
                        seen = set(list(seen)[-1500:])
                    asyncio.create_task(self._process_announcement(ann))

                await asyncio.sleep(source.poll_interval_seconds)

    async def _process_announcement(self, ann):
        # [FIX-pattern] Protegida em try/except: fire-and-forget via
        # create_task no loop de polling.
        try:
            detected_at_ms = int(time.time() * 1000)
            result = extract_ticker(ann.title)

            if not result.matched:
                status = "excluded" if (result.excluded_reason and result.excluded_reason != "no_pattern_matched") else "no_match"
                await self.persistence.record_announcement(
                    ann.exchange, ann.title, ann.url, None, None, status,
                    result.excluded_reason, ann.published_at_ms, detected_at_ms,
                )
                return

            has_users = self.execution_engine.has_armed_users(ann.exchange)
            status = "matched_traded" if has_users else "matched_no_users"
            announcement_id = await self.persistence.record_announcement(
                ann.exchange, ann.title, ann.url, result.ticker, result.confidence, status,
                None, ann.published_at_ms, detected_at_ms,
            )

            latency_ms = (detected_at_ms - ann.published_at_ms) if ann.published_at_ms else None
            logger.warning(
                f"🚨 [{ann.exchange}] LISTAGEM DETECTADA: {result.ticker} "
                f"(confiança={result.confidence}, latência de detecção={latency_ms}ms) — {ann.title}"
            )
            await self.broadcast_raw({
                "type": "announcement_detected",
                "data": {
                    "exchange": ann.exchange, "ticker": result.ticker, "title": ann.title,
                    "confidence": result.confidence, "latency_ms": latency_ms, "has_armed_users": has_users,
                }
            })

            if has_users:
                await self.execution_engine.handle_qualified_announcement(
                    ann.exchange, result.ticker, announcement_id, detected_at_ms
                )
        except Exception as e:
            logger.error(f"Erro ao processar anúncio ({ann.exchange}): {e}")

    # ------------------------------------------------------------------
    # WebSocket de controle
    # ------------------------------------------------------------------
    async def broadcast_raw(self, payload):
        if not self.connected_clients:
            return
        message = json.dumps(payload)
        for client in set(self.connected_clients):
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                pass

    async def _broadcast_trade_event(self, event_type, data):
        await self.broadcast_raw({"type": event_type, "data": data})

    async def ws_handler(self, websocket):
        logger.info("🔌 [WS] Nova conexão solicitada. Aguardando autenticação JWT...")
        try:
            auth_message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            auth_data = json.loads(auth_message)
            if auth_data.get("type") != "auth" or not auth_data.get("token"):
                await websocket.close(code=4001, reason="Auth required")
                return
            payload = jwt.decode(auth_data["token"], JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = int(payload.get("sub"))
            websocket.user_id = user_id
            logger.info(f"✅ [WS] Cliente autenticado (User ID: {user_id})")
        except asyncio.TimeoutError:
            await websocket.close(code=4001, reason="Timeout")
            return
        except Exception as e:
            logger.warning(f"❌ [WS] Erro de autenticação: {e}")
            await websocket.close(code=4001, reason="JWT Error")
            return

        self.connected_clients.add(websocket)
        try:
            exchanges = await asyncio.to_thread(self._sync_get_user_exchanges, user_id)
            recent_trades = await self.persistence.get_recent_trades(user_id=user_id)
            avg_latency = await self.persistence.get_avg_detection_latency_ms()
            await websocket.send(json.dumps({
                "type": "state", "exchanges": exchanges, "trades": recent_trades,
                "avg_detection_latency_ms": avg_latency,
            }))
        except websockets.exceptions.ConnectionClosed:
            self.connected_clients.discard(websocket)
            return

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    mtype = data.get("type")
                    if mtype != "command":
                        continue
                    cmd = data.get("command")

                    if cmd == "save_and_arm":
                        exchange = data.get("exchange", "").upper()
                        creds = data.get("credentials", {})
                        cfg = data.get("config", {})
                        trade_amount = float(cfg.get("trade_amount_quote", 20.0))
                        tp_pct = float(cfg.get("tp_pct", 50.0))
                        sl_pct = float(cfg.get("sl_pct", 15.0))
                        max_hold = float(cfg.get("max_hold_seconds", 300.0))

                        await asyncio.to_thread(
                            self._sync_save_credentials, user_id, exchange,
                            creds.get("apiKey", ""), creds.get("secret", ""), creds.get("password", ""),
                            trade_amount, tp_pct, sl_pct, max_hold,
                        )
                        await asyncio.to_thread(self._sync_set_armed, user_id, exchange, True)

                        encrypted_row = {
                            "key_encrypted": self.encrypt_val(creds.get("apiKey", "")),
                            "secret_encrypted": self.encrypt_val(creds.get("secret", "")),
                            "password_encrypted": self.encrypt_val(creds.get("password", "")) if creds.get("password") else None,
                        }
                        try:
                            self.execution_engine.arm_user(
                                user_id, exchange, encrypted_row,
                                ListingTradeConfig(trade_amount_quote=trade_amount, tp_pct=tp_pct, sl_pct=sl_pct, max_hold_seconds=max_hold),
                            )
                        except Exception as e:
                            logger.error(f"Erro ao armar usuário {user_id} em {exchange}: {e}")

                        exchanges = await asyncio.to_thread(self._sync_get_user_exchanges, user_id)
                        await websocket.send(json.dumps({"type": "state", "exchanges": exchanges}))

                    elif cmd == "disarm":
                        exchange = data.get("exchange", "").upper()
                        await asyncio.to_thread(self._sync_set_armed, user_id, exchange, False)
                        await self.execution_engine.disarm_user(user_id, exchange)
                        exchanges = await asyncio.to_thread(self._sync_get_user_exchanges, user_id)
                        await websocket.send(json.dumps({"type": "state", "exchanges": exchanges}))

                    elif cmd == "get_history":
                        trades = await self.persistence.get_recent_trades(user_id=user_id)
                        await websocket.send(json.dumps({"type": "history", "data": trades}))

                except Exception as e:
                    logger.error(f"WS Error: {e}")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.connected_clients.discard(websocket)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def run(self):
        logger.info(f"🚀 Iniciando CEX Listing Sniper na porta {WS_PORT}")
        await self.boot_armed_users()

        source_tasks = [self.poll_source_loop(ex) for ex in SOURCE_REGISTRY.keys()]
        async with websockets.serve(self.ws_handler, "0.0.0.0", WS_PORT):
            try:
                await asyncio.gather(*source_tasks)
            finally:
                await self.execution_engine.shutdown()


async def main():
    service = ListingSniperService()
    await service.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Sistema interrompido pelo usuário.")
