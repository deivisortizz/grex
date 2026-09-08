import asyncio
import ccxt.pro as ccxt
import logging
import sys
import time
import json
import os
import sqlite3
import websockets
from datetime import datetime
from dotenv import load_dotenv
from cryptography.fernet import Fernet

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

# Pasta de dados com suporte a Docker Volume
DATA_DIR = os.getenv('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('HFT_Engine')

class MarketDataEngine:
    def __init__(self):
        self.symbol_spatial = 'USDT/BRL'
        self.triangular_symbols = ['USDT/BRL', 'ETH/BRL', 'ETH/USDT']
        
        self.FEE_TAKER = 0.001
        self.TARGET_SPREAD = 0.30
        self.TRADE_AMOUNT_USDT = 11.0
        self.COOLDOWN_SECONDS = 5.0
        
        self.cooldown_until = 0.0
        self.connected_clients = set()
        
        # Flags independentes para cada estratégia
        self.is_spatial_active = False
        self.is_triangular_active = False
        
        self.orderbook_state = {}
        
        self.init_crypto()
        self.init_db()

    def init_crypto(self):
        key_path = os.path.join(DATA_DIR, '.master.key')
        if not os.path.exists(key_path):
            key = Fernet.generate_key()
            with open(key_path, 'wb') as f:
                f.write(key)
            logger.info(f"🔑 Chave Mestra (.master.key) gerada e salva com sucesso em {key_path}")
        else:
            with open(key_path, 'rb') as f:
                key = f.read()
            logger.info(f"🔑 Chave Mestra carregada de {key_path}")
        self.cipher = Fernet(key)

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

    def init_db(self):
        db_path = os.path.join(DATA_DIR, 'trades.db')
        logger.info(f"📂 Conectando ao banco SQLite em {db_path}")
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    exchange_buy TEXT,
                    exchange_sell TEXT,
                    spread_bruto REAL,
                    lucro_liquido REAL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS api_keys (
                    exchange TEXT PRIMARY KEY,
                    key_encrypted TEXT,
                    secret_encrypted TEXT,
                    password_encrypted TEXT
                )
            ''')
            conn.commit()

    def _sync_get_trade_history(self):
        db_path = os.path.join(DATA_DIR, 'trades.db')
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM history ORDER BY id DESC LIMIT 100")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_trade_history(self):
        try:
            return await asyncio.to_thread(self._sync_get_trade_history)
        except Exception as e:
            logger.error(f"Erro ao ler histórico SQLite: {e}")
            return []

    def _sync_insert_trade(self, timestamp, ex_buy, ex_sell, gross, net):
        db_path = os.path.join(DATA_DIR, 'trades.db')
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO history (timestamp, exchange_buy, exchange_sell, spread_bruto, lucro_liquido)
                VALUES (?, ?, ?, ?, ?)
            ''', (timestamp, ex_buy, ex_sell, gross, net))
            conn.commit()
            return cursor.lastrowid

    def _sync_save_api_key(self, exchange, apikey, secret, password):
        enc_key = self.encrypt_val(apikey)
        enc_sec = self.encrypt_val(secret)
        enc_pass = self.encrypt_val(password)
        db_path = os.path.join(DATA_DIR, 'trades.db')
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO api_keys (exchange, key_encrypted, secret_encrypted, password_encrypted)
                VALUES (?, ?, ?, ?)
            ''', (exchange, enc_key, enc_sec, enc_pass))
            conn.commit()

    def _sync_get_all_keys(self):
        db_path = os.path.join(DATA_DIR, 'trades.db')
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM api_keys")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    async def boot_exchanges_from_db(self):
        logger.info("Carregando Cofre de API Keys do SQLite...")
        rows = await asyncio.to_thread(self._sync_get_all_keys)
        tasks = []
        for row in rows:
            ex_name = row['exchange']
            apikey = self.decrypt_val(row['key_encrypted'])
            secret = self.decrypt_val(row['secret_encrypted'])
            password = self.decrypt_val(row['password_encrypted'])
            
            if not apikey or not secret:
                continue
                
            creds = {
                'apiKey': apikey,
                'secret': secret,
                'enableRateLimit': True
            }
            if password:
                creds['password'] = password
                
            try:
                ExchangeClass = getattr(ccxt, ex_name.lower())
                new_inst = ExchangeClass(creds)
                
                self.orderbook_state[ex_name] = {
                    'instance': new_inst,
                    'symbols': {sym: {'bid': None, 'ask': None} for sym in self.triangular_symbols}
                }
                
                for sym in self.triangular_symbols:
                    tasks.append(self.watch_symbol(ex_name, sym))
                
                logger.info(f"🟢 [COFRE] Instância da {ex_name} carregada e adicionada.")
            except Exception as e:
                logger.error(f"Erro ao instanciar corretora {ex_name} do banco: {e}")
                
        return tasks

    async def ws_handler(self, websocket):
        self.connected_clients.add(websocket)
        logger.info(f"Frontend conectado. Total de clientes: {len(self.connected_clients)}")
        
        # Handshake protegido
        try:
            history = await self.get_trade_history()
            await websocket.send(json.dumps({"type": "history", "data": history}))
            await websocket.send(json.dumps({
                "type": "config", 
                "target_spread": self.TARGET_SPREAD, 
                "trade_amount": self.TRADE_AMOUNT_USDT,
                "is_spatial_active": self.is_spatial_active,
                "is_triangular_active": self.is_triangular_active,
                "exchanges": list(self.orderbook_state.keys())
            }))
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Cliente desconectou antes do handshake. Ignorando.")
            self.connected_clients.discard(websocket)
            return

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    mtype = data.get("type")
                    
                    if mtype == "ping":
                        await websocket.send(json.dumps({"type": "pong", "timestamp": data.get("timestamp")}))
                        
                    elif mtype == "config_update":
                        if "target_spread" in data:
                            self.TARGET_SPREAD = float(data["target_spread"])
                        if "trade_amount" in data:
                            self.TRADE_AMOUNT_USDT = float(data["trade_amount"])
                        await self.broadcast_raw({
                            "type": "config", 
                            "target_spread": self.TARGET_SPREAD, 
                            "trade_amount": self.TRADE_AMOUNT_USDT,
                            "is_spatial_active": self.is_spatial_active,
                            "is_triangular_active": self.is_triangular_active,
                            "exchanges": list(self.orderbook_state.keys())
                        })
                        
                    elif mtype == "command":
                        cmd = data.get("command")
                        if cmd == "start_spatial":
                            self.is_spatial_active = True
                        elif cmd == "pause_spatial":
                            self.is_spatial_active = False
                        elif cmd == "start_triangular":
                            self.is_triangular_active = True
                        elif cmd == "pause_triangular":
                            self.is_triangular_active = False
                        elif cmd == "get_history":
                            hist = await self.get_trade_history()
                            await websocket.send(json.dumps({"type": "history", "data": hist}))
                            continue
                        elif cmd == "add_exchange":
                            ex_name = data.get("exchange", "").upper()
                            creds = data.get("credentials", {})
                            if ex_name and ex_name not in self.orderbook_state:
                                try:
                                    apikey = creds.get("apiKey", "")
                                    secret = creds.get("secret", "")
                                    password = creds.get("password", "")
                                    
                                    await asyncio.to_thread(self._sync_save_api_key, ex_name, apikey, secret, password)
                                    
                                    creds['enableRateLimit'] = True
                                    ExchangeClass = getattr(ccxt, ex_name.lower())
                                    new_inst = ExchangeClass(creds)
                                    
                                    self.orderbook_state[ex_name] = {
                                        'instance': new_inst,
                                        'symbols': {sym: {'bid': None, 'ask': None} for sym in self.triangular_symbols}
                                    }
                                    
                                    for sym in self.triangular_symbols:
                                        asyncio.create_task(self.watch_symbol(ex_name, sym))
                                        
                                except Exception as e:
                                    logger.error(f"Erro ao instanciar corretora {ex_name}: {e}")
                            
                            await self.broadcast_raw({
                                "type": "config", 
                                "target_spread": self.TARGET_SPREAD, 
                                "trade_amount": self.TRADE_AMOUNT_USDT,
                                "is_spatial_active": self.is_spatial_active,
                                "is_triangular_active": self.is_triangular_active,
                                "exchanges": list(self.orderbook_state.keys())
                            })
                            continue

                        await self.broadcast_raw({
                            "type": "config", 
                            "target_spread": self.TARGET_SPREAD, 
                            "trade_amount": self.TRADE_AMOUNT_USDT,
                            "is_spatial_active": self.is_spatial_active,
                            "is_triangular_active": self.is_triangular_active,
                            "exchanges": list(self.orderbook_state.keys())
                        })
                except Exception as e:
                    logger.error(f"WS Error: {e}")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.connected_clients.remove(websocket)

    async def start_ws_server(self):
        logger.info("📡 Iniciando servidor WebSocket em ws://localhost:8765")
        async with websockets.serve(self.ws_handler, "0.0.0.0", 8765):
            await asyncio.Future()

    async def broadcast_raw(self, payload):
        if not self.connected_clients:
            return
        message = json.dumps(payload)
        clients = set(self.connected_clients)
        for client in clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                pass

    async def watch_symbol(self, exchange_name: str, symbol: str):
        exchange_instance = self.orderbook_state[exchange_name]['instance']
        logger.info(f"[{exchange_name}] Iniciando stream para {symbol}...")
        while True:
            try:
                orderbook = await exchange_instance.watch_order_book(symbol)
                best_bid = orderbook['bids'][0][0] if len(orderbook['bids']) > 0 else None
                best_ask = orderbook['asks'][0][0] if len(orderbook['asks']) > 0 else None
                self.orderbook_state[exchange_name]['symbols'][symbol]['bid'] = best_bid
                self.orderbook_state[exchange_name]['symbols'][symbol]['ask'] = best_ask
            except ccxt.NetworkError:
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"[{exchange_name} - {symbol}] Erro: {e}")
                await asyncio.sleep(5)

    async def execute_real_trade(self, buy_exchange_name, sell_exchange_name, buy_price, sell_price, amount_usdt, gross_spread_pct, net_spread_pct):
        sys.stdout.write("\r" + " " * 100 + "\r")
        logger.info(f"[⚡ EXECUTANDO ESPACIAL] Compra {buy_exchange_name} | Venda {sell_exchange_name} | Qtd: {amount_usdt}")
        
        buy_inst = self.orderbook_state[buy_exchange_name]['instance']
        sell_inst = self.orderbook_state[sell_exchange_name]['instance']
        
        try:
            results = await asyncio.gather(
                buy_inst.create_market_buy_order(self.symbol_spatial, amount_usdt),
                sell_inst.create_market_sell_order(self.symbol_spatial, amount_usdt),
                return_exceptions=False
            )
            logger.info(f"[✅ ORDENS EXECUTADAS] Buy ID: {results[0].get('id')} | Sell ID: {results[1].get('id')}")
        except Exception as e:
            logger.error(f"[❌ FALHA NA EXECUÇÃO ESPACIAL] {e}")

        estimated_profit_brl = (amount_usdt * sell_price * (1 - self.FEE_TAKER)) - (amount_usdt * buy_price * (1 + self.FEE_TAKER))
        ts = datetime.now().isoformat()
        
        try:
            inserted_id = await asyncio.to_thread(
                self._sync_insert_trade, ts, buy_exchange_name, sell_exchange_name, gross_spread_pct, estimated_profit_brl
            )
            
            trade_record = {
                "id": inserted_id,
                "timestamp": ts,
                "exchange_buy": buy_exchange_name,
                "exchange_sell": sell_exchange_name,
                "spread_bruto": round(gross_spread_pct, 4),
                "lucro_liquido": round(estimated_profit_brl, 4)
            }
            
            await self.broadcast_raw({"type": "new_trade", "data": trade_record})
        except Exception as e:
            logger.error(f"Falha ao salvar no banco: {e}")

    async def analyze_spread_loop(self):
        logger.info("Iniciando Módulo de Arbitragem Espacial (Monitorando USDT/BRL)...")
        while True:
            await asyncio.sleep(0.005)
                
            exchanges = list(self.orderbook_state.keys())
            valid_exchanges = {}
            for ex in exchanges:
                state = self.orderbook_state[ex]['symbols'][self.symbol_spatial]
                if state['bid'] and state['ask']:
                    valid_exchanges[ex] = state

            if len(valid_exchanges) < 2:
                continue
                
            best_spread = -999
            best_pair = None
            
            for buy_ex, buy_state in valid_exchanges.items():
                for sell_ex, sell_state in valid_exchanges.items():
                    if buy_ex == sell_ex:
                        continue
                    
                    buy_price = buy_state['ask']
                    sell_price = sell_state['bid']
                    
                    gross = (sell_price / buy_price - 1) * 100
                    custo = buy_price * (1 + self.FEE_TAKER)
                    receita = sell_price * (1 - self.FEE_TAKER)
                    net = ((receita / custo) - 1) * 100
                    
                    if net > best_spread:
                        best_spread = net
                        best_pair = {
                            'buy_ex': buy_ex, 'sell_ex': sell_ex,
                            'buy_price': buy_price, 'sell_price': sell_price,
                            'gross': gross, 'net': net
                        }
            
            # Sempre despacha os dados para visualização, independente de estar ativo
            payload = {"type": "market_data"}
            for ex, data in valid_exchanges.items():
                payload[ex.lower()] = {"bid": data['bid'], "ask": data['ask']}
                
            if best_pair:
                payload['gross_spread'] = round(best_pair['gross'], 4)
                payload['net_spread'] = round(best_pair['net'], 4)
                payload['best_route'] = f"{best_pair['buy_ex']} -> {best_pair['sell_ex']}"
            else:
                payload['gross_spread'] = 0
                payload['net_spread'] = 0
                payload['best_route'] = "N/A"

            asyncio.create_task(self.broadcast_raw(payload))
            
            if time.time() < self.cooldown_until:
                continue

            # Só executa a ordem se o motor Espacial estiver LIGADO
            if best_pair and best_pair['net'] >= self.TARGET_SPREAD:
                if self.is_spatial_active:
                    await self.execute_real_trade(
                        best_pair['buy_ex'], 
                        best_pair['sell_ex'], 
                        best_pair['buy_price'], 
                        best_pair['sell_price'], 
                        self.TRADE_AMOUNT_USDT, 
                        best_pair['gross'],
                        best_pair['net']
                    )
                    self.cooldown_until = time.time() + self.COOLDOWN_SECONDS

    async def analyze_triangular_loop(self):
        logger.info("Iniciando Módulo de Arbitragem Triangular (Oceano Azul)...")
        while True:
            await asyncio.sleep(0.005)
            
            exchanges = list(self.orderbook_state.keys())
            triangular_results = []
            
            for ex in exchanges:
                syms = self.orderbook_state[ex]['symbols']
                
                eth_brl = syms.get('ETH/BRL', {})
                eth_usdt = syms.get('ETH/USDT', {})
                usdt_brl = syms.get('USDT/BRL', {})
                
                if not (eth_brl.get('ask') and eth_brl.get('bid') and 
                        eth_usdt.get('ask') and eth_usdt.get('bid') and 
                        usdt_brl.get('ask') and usdt_brl.get('bid')):
                    continue
                
                # Preços Reais
                ask_eth_brl = eth_brl['ask']
                bid_eth_brl = eth_brl['bid']
                
                ask_eth_usdt = eth_usdt['ask']
                bid_eth_usdt = eth_usdt['bid']
                
                ask_usdt_brl = usdt_brl['ask']
                bid_usdt_brl = usdt_brl['bid']
                
                F = 1 - self.FEE_TAKER
                F_gross = 1
                
                # Ciclo Direto: BRL -> ETH -> USDT -> BRL
                eth_direct_gross = (1 / ask_eth_brl) * F_gross
                eth_direct_net = (1 / ask_eth_brl) * F
                
                usdt_direct_gross = eth_direct_gross * bid_eth_usdt * F_gross
                usdt_direct_net = eth_direct_net * bid_eth_usdt * F
                
                brl_direct_gross = usdt_direct_gross * bid_usdt_brl * F_gross
                brl_direct_net = usdt_direct_net * bid_usdt_brl * F
                
                direct_gross_pct = (brl_direct_gross - 1) * 100
                direct_net_pct = (brl_direct_net - 1) * 100
                
                # Ciclo Reverso: BRL -> USDT -> ETH -> BRL
                usdt_rev_gross = (1 / ask_usdt_brl) * F_gross
                usdt_rev_net = (1 / ask_usdt_brl) * F
                
                eth_rev_gross = (usdt_rev_gross / ask_eth_usdt) * F_gross
                eth_rev_net = (usdt_rev_net / ask_eth_usdt) * F
                
                brl_rev_gross = eth_rev_gross * bid_eth_brl * F_gross
                brl_rev_net = eth_rev_net * bid_eth_brl * F
                
                rev_gross_pct = (brl_rev_gross - 1) * 100
                rev_net_pct = (brl_rev_net - 1) * 100
                
                triangular_results.append({
                    "exchange": ex,
                    "prices": {
                        "ETH/BRL": {"ask": ask_eth_brl, "bid": bid_eth_brl},
                        "ETH/USDT": {"ask": ask_eth_usdt, "bid": bid_eth_usdt},
                        "USDT/BRL": {"ask": ask_usdt_brl, "bid": bid_usdt_brl},
                    },
                    "direct_route": {
                        "gross": round(direct_gross_pct, 4),
                        "net": round(direct_net_pct, 4)
                    },
                    "reverse_route": {
                        "gross": round(rev_gross_pct, 4),
                        "net": round(rev_net_pct, 4)
                    }
                })
                
                # Só executa a ordem se o motor Triangular estiver LIGADO
                if direct_net_pct >= self.TARGET_SPREAD and self.is_triangular_active and time.time() > self.cooldown_until:
                    logger.info(f"[OCEANO AZUL] Executando Ciclo Direto na {ex} - Lucro Est: {direct_net_pct}%")
                    ts = datetime.now().isoformat()
                    est_profit_brl = self.TRADE_AMOUNT_USDT * ask_usdt_brl * (direct_net_pct/100)
                    try:
                        inserted_id = await asyncio.to_thread(
                            self._sync_insert_trade, ts, f"{ex}_TRI_DIRECT", f"{ex}_TRI_DIRECT", direct_gross_pct, est_profit_brl
                        )
                        trade_record = {
                            "id": inserted_id, "timestamp": ts,
                            "exchange_buy": f"{ex}_TRI_DIRECT", "exchange_sell": f"{ex}_TRI_DIRECT",
                            "spread_bruto": round(direct_gross_pct, 4), "lucro_liquido": round(est_profit_brl, 4)
                        }
                        await self.broadcast_raw({"type": "new_trade", "data": trade_record})
                    except Exception as e:
                        pass
                    self.cooldown_until = time.time() + self.COOLDOWN_SECONDS
                    
            if triangular_results:
                await self.broadcast_raw({
                    "type": "triangular_data",
                    "timestamp": datetime.now().isoformat(),
                    "exchanges": triangular_results
                })

    async def run(self):
        logger.info(f"Iniciando Motor HFT - Suporte Dual (Espacial + Triangular)")
        exchange_tasks = await self.boot_exchanges_from_db()
        
        try:
            tasks = exchange_tasks
            tasks.append(self.start_ws_server())
            tasks.append(self.analyze_spread_loop())
            tasks.append(self.analyze_triangular_loop())
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            for ex_name, state in self.orderbook_state.items():
                inst = state.get('instance')
                if inst:
                    await inst.close()

async def main():
    engine = MarketDataEngine()
    await engine.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Sistema interrompido pelo usuário.")
