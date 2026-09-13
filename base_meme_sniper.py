import asyncio
import logging
import sys
import os
import sqlite3
import json
import time
import websockets
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from web3 import AsyncWeb3, WebSocketProvider, AsyncHTTPProvider

# ---------------------------------------------------------
# Configuração de Ambiente e Logging
# ---------------------------------------------------------
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

DATA_DIR = os.getenv('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))

# Suporte a dois padrões de nomenclatura de env vars:
# Legado: BASE_WSS_RPC / BASE_HTTP_RPC
# Novo (Docker/Coolify): BASE_RPC_WS / BASE_RPC_HTTP
BASE_WSS_RPC   = os.getenv('BASE_RPC_WS')   or os.getenv('BASE_WSS_RPC')
BASE_HTTP_RPC  = os.getenv('BASE_RPC_HTTP')  or os.getenv('BASE_HTTP_RPC')
ROUTER_ADDRESS = os.getenv('ROUTER_ADDRESS')
SNIPER_WS_PORT = int(os.getenv('SNIPER_WS_PORT', 8766))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('BaseMemeSniper')

class WSLogHandler(logging.Handler):
    def __init__(self, sniper_instance):
        super().__init__()
        self.sniper = sniper_instance

    def emit(self, record):
        try:
            loop = asyncio.get_running_loop()
            log_entry = self.format(record)
            payload = {
                "type": "log",
                "level": record.levelname,
                "message": log_entry,
                "timestamp": int(time.time() * 1000)
            }
            loop.create_task(self.sniper.broadcast_ws(payload))
        except RuntimeError:
            pass

# ---------------------------------------------------------
# ABIs Mínimas (Minimal ABIs)
# ---------------------------------------------------------

def safe_topic_to_address(topic) -> str:
    """
    Converte um tópico de log (pode ser string hex ou objeto bytes)
    para um endereço EVM válido de 40 caracteres.
    """
    if isinstance(topic, str):
        # Garante que veio como '0x000...abcd', pega os últimos 40 chars
        return "0x" + topic.lstrip("0x").lstrip("0")[-40:].zfill(40)
    if hasattr(topic, 'hex'):
        return "0x" + topic.hex()[-40:]
    return "0x" + str(topic)[-40:]
# Evento genérico PairCreated (Usado por forks do UniswapV2 como BaseSwap, etc)
FACTORY_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "token0", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "token1", "type": "address"},
            {"indexed": False, "internalType": "address", "name": "pair", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "name": "PairCreated",
        "type": "event"
    }
]

# Funções estritamente necessárias do Router para compra
ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactETHForTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForETH",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# ABI mínima ERC-20 para approve e balanceOf
ERC20_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

class BaseMemeSniper:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # Validação de variáveis de ambiente (sem sys.exit para não crashar o container)
        missing = []
        if not BASE_WSS_RPC:
            missing.append('BASE_RPC_WS (ou BASE_WSS_RPC)')
        if not BASE_HTTP_RPC:
            missing.append('BASE_RPC_HTTP (ou BASE_HTTP_RPC)')
            
        self.rpc_ok = len(missing) == 0
        if not self.rpc_ok:
            logger.critical(
                f"❌ [CONFIG] Variáveis de ambiente ausentes: {', '.join(missing)}. "
                f"O Sniper permanecerá em modo STANDBY até as variáveis serem configuradas."
            )
            # Web3 não será inicializado – métodos que dependem dele retornam cedo
            self.w3_ws   = None
            self.w3_http = None
        else:
            # Conexões Web3 Assíncronas
            self.w3_ws   = AsyncWeb3(WebSocketProvider(BASE_WSS_RPC))
            self.w3_http = AsyncWeb3(AsyncHTTPProvider(BASE_HTTP_RPC))
        
        self.cipher = None
        self.wallet_address = None
        self.private_key = None
        self.is_active = True
        self.daily_pnl_usd = 0.0
        self.max_daily_loss_usd = float(os.getenv('MAX_DAILY_LOSS_USD', 10.00))
        self.eth_usd_price = float(os.getenv('ETH_PRICE_USD', 3500.0))
        
        # Gestão Dinâmica (Controlado pelo React HFT)
        self.config = {
            'snipe_size_eth': 0.0005,
            'min_pool_weth': 0.05,
            'tp_pct': 100,
            'sl_pct': 20
        }
        self.open_positions = {}
        self.total_trades = 0
        self.win_trades = 0
        
        self.connected_clients = set()
        
        # Conecta os logs do backend ao WebSocket do frontend
        ws_logger = WSLogHandler(self)
        ws_logger.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
        logger.addHandler(ws_logger)
        
        self.init_crypto()
        self.init_db()

    # ---------------------------------------------------------
    # Cofre (Fernet Vault) e DB Assíncrono
    # ---------------------------------------------------------
    def init_crypto(self):
        key_path = os.path.join(DATA_DIR, '.master.key')
        if not os.path.exists(key_path):
            key = Fernet.generate_key()
            with open(key_path, 'wb') as f:
                f.write(key)
            logger.info(f"🔑 [COFRE] Chave Mestra gerada em {key_path}")
        else:
            with open(key_path, 'rb') as f:
                key = f.read()
            logger.info(f"🔑 [COFRE] Chave Mestra (Fernet) carregada com sucesso.")
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
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        logger.info(f"📂 Conectando ao SQLite Sniper em {db_path}")
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            # Tabela de segurança isolada para Burner Wallet
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS burner_wallet (
                    id INTEGER PRIMARY KEY,
                    address TEXT,
                    pk_encrypted TEXT
                )
            ''')
            conn.commit()

    def _sync_get_wallet(self):
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM burner_wallet LIMIT 1")
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def _sync_save_wallet(self, address, private_key):
        enc_pk = self.encrypt_val(private_key)
        db_path = os.path.join(DATA_DIR, 'sniper.db')
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM burner_wallet") # Mantém apenas 1 burner
            cursor.execute('''
                INSERT INTO burner_wallet (address, pk_encrypted)
                VALUES (?, ?)
            ''', (address, enc_pk))
            conn.commit()

    async def load_wallet(self):
        """
        Isolamento de operações bloqueantes de I/O via to_thread.
        """
        row = await asyncio.to_thread(self._sync_get_wallet)
        if row:
            self.wallet_address = row['address']
            self.private_key = self.decrypt_val(row['pk_encrypted'])
            logger.info(f"🟢 [COFRE] Burner Wallet carregada pronta para Snipe: {self.wallet_address}")
        else:
            logger.warning("⚠️ Nenhuma wallet configurada no banco de dados. Modo leitura ativo.")

    # ---------------------------------------------------------
    # Motor HFT Assíncrono Web3
    # ---------------------------------------------------------
    async def listen_new_pairs(self):
        logger.info("📡 Iniciando escuta de logs de criação de pares na Base (WSS)...")
        
        event_signature_hash = self.w3_http.keccak(text="PairCreated(address,address,address,uint256)").hex()
        
        subscribe_payload = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "eth_subscribe",
            "params": ["logs", {"topics": [event_signature_hash]}]
        }
        
        while True:
            try:
                # Conexão WSS direta, evitando as instabilidades de filtros do AsyncWeb3 
                async with websockets.connect(BASE_WSS_RPC, ping_interval=20, ping_timeout=20) as ws:
                    await ws.send(json.dumps(subscribe_payload))
                    response = await ws.recv()
                    logger.info(f"🟢 [SNIPER] Subscrição de Logs ativa! Resposta do Node: {response}")

                    async for message in ws:
                        data = json.loads(message)
                        if "params" in data and "result" in data["params"]:
                            log = data["params"]["result"]
                            # Delega o processamento sem travar o listener
                            asyncio.create_task(self.process_new_pair(log))
                        
            except Exception as e:
                logger.error("❌ Conexão WSS com a rede Base perdida. Tentando reconectar...")
                logger.error(f"Erro detalhado no WSS: {e}")
                await asyncio.sleep(5)

    async def process_new_pair(self, log):
        """
        Decodifica o log da chain e prepara o snipe em background.
        Os topics chegam como strings hex '0x...' quando vindos do WS puro.
        """
        try:
            topics = log.get("topics", [])
            if len(topics) < 3:
                return

            # Usar helper seguro para extrair endereços dos topics indexados
            raw_token0 = safe_topic_to_address(topics[1])
            raw_token1 = safe_topic_to_address(topics[2])

            token0 = self.w3_http.to_checksum_address(raw_token0)
            token1 = self.w3_http.to_checksum_address(raw_token1)
            
            # WETH na Base (0x4200000000000000000000000000000000000006)
            WETH_BASE = self.w3_http.to_checksum_address("0x4200000000000000000000000000000000000006")
            
            meme_token = token0 if token1 == WETH_BASE else (token1 if token0 == WETH_BASE else None)
            
            # Extrair endereço do par do data do log
            data = log.get("data", "")
            pair_address = None
            if len(data) >= 66:
                pair_address_raw = "0x" + data[26:66]
                pair_address = self.w3_http.to_checksum_address(pair_address_raw)
            
            if meme_token:
                logger.info(f"⚡ [NOVO MEME DETECTADO] Liquidez Criada | Token: {meme_token}")
                
                # Broadcast para a UI do React (informa se a execução foi pulada por estar pausado)
                await self.broadcast_ws({
                    "type": "new_pool",
                    "token": meme_token,
                    "paired_with": "WETH",
                    "timestamp": int(time.time() * 1000),
                    "skipped": not self.is_active
                })
                
                if not self.is_active:
                    logger.info(f"⏸️ [SNIPER PAUSADO] Compra ignorada para {meme_token} (robô está desligado/pausado).")
                    return
                
                await self.execute_swap(meme_token, pair_address=pair_address)
            else:
                logger.info(f"⚪ Par ignorado (Não envelopa WETH). Tokens: {token0} / {token1}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao decodificar novo contrato: {e}")

    async def get_amounts_out(self, amount_in_wei, path):
        router = self.w3_http.eth.contract(address=self.w3_http.to_checksum_address(ROUTER_ADDRESS), abi=ROUTER_ABI)
        try:
            amounts = await router.functions.getAmountsOut(amount_in_wei, path).call()
            return amounts[-1]
        except Exception as e:
            logger.error(f"❌ [SIMULAÇÃO] Falha ao estimar retorno de tokens: {e}")
            return 0

    async def anti_honeypot_check(self, target_token, amount_in_wei, expected_tokens_out) -> bool:
        """
        Simula estaticamente uma VENDA de 100% dos tokens via eth_call.
        Se o contrato reverter, bloqueia o Snipe antes de gastar qualquer gwei.
        Retorna True se PASSAR na verificação, False se for Honeypot.
        """
        WETH_BASE = self.w3_http.to_checksum_address("0x4200000000000000000000000000000000000006")
        target_token_checksum = self.w3_http.to_checksum_address(target_token)
        router_addr = self.w3_http.to_checksum_address(ROUTER_ADDRESS)
        router = self.w3_http.eth.contract(address=router_addr, abi=ROUTER_ABI)
        account = self.w3_http.eth.account.from_key(self.private_key)
        
        sell_path = [target_token_checksum, WETH_BASE]
        deadline = int(time.time()) + 60
        
        logger.info(f"🔍 [ANTI-HONEYPOT] Simulando venda de {expected_tokens_out} tokens...")
        
        try:
            # eth.call é puro (não gasta gas, não submete TX)
            await router.functions.swapExactTokensForETH(
                expected_tokens_out,
                0,  # amountOutMin = 0 pois é apenas simulação
                sell_path,
                account.address,
                deadline
            ).call({'from': account.address})
            
            logger.info("✅ [ANTI-HONEYPOT] Simulação de venda passou. Token não é Honeypot.")
            return True
            
        except Exception as e:
            err_str = str(e).lower()
            # Detectar padrões comuns de Honeypot/tokens bloqueados
            honeypot_signals = [
                'transfer_failed', 'paused', 'revert', 'execution reverted',
                'transferfailed', 'blacklist', 'not allowed', 'trading not open'
            ]
            is_honeypot = any(sig in err_str for sig in honeypot_signals)
            
            if is_honeypot:
                logger.warning(
                    f"⚠️ [ANTI-HONEYPOT] Token identificado como Honeypot/Bloqueado para venda. "
                    f"Snipe cancelado. | Token: {target_token} | Razão: {str(e)[:80]}"
                )
            else:
                # Pode ser falta de liquidez para venda, ou approve não dado ainda
                logger.warning(
                    f"⚠️ [ANTI-HONEYPOT] Simulação de venda falhou (motivo inesperado). "
                    f"Snipe cancelado por precaução. | Detalhe: {str(e)[:120]}"
                )
            return False

    async def auto_approve_router(self, target_token):
        """
        Envia um Approve de limite infinito para o Router após a compra
        para permitir futuras vendas sem precisar de uma transação extra.
        """
        INFINITE_APPROVE = 2**256 - 1
        router_addr = self.w3_http.to_checksum_address(ROUTER_ADDRESS)
        token_contract = self.w3_http.eth.contract(
            address=self.w3_http.to_checksum_address(target_token),
            abi=ERC20_ABI
        )
        account = self.w3_http.eth.account.from_key(self.private_key)
        
        try:
            # Verifica se já tem allowance infinita para evitar TX desnecessária
            current_allowance = await token_contract.functions.allowance(
                account.address, router_addr
            ).call()
            
            if current_allowance >= INFINITE_APPROVE // 2:
                logger.info("🔓 [APPROVE] Allowance já configurada. Pulando approve.")
                return

            nonce = await self.w3_http.eth.get_transaction_count(account.address)
            latest_block = await self.w3_http.eth.get_block('latest')
            base_fee = latest_block['baseFeePerGas']
            max_priority_fee = self.w3_http.to_wei(0.1, 'gwei')
            max_fee_per_gas = (base_fee * 2) + max_priority_fee

            approve_tx = await token_contract.functions.approve(
                router_addr, INFINITE_APPROVE
            ).build_transaction({
                'from': account.address,
                'nonce': nonce,
                'maxFeePerGas': max_fee_per_gas,
                'maxPriorityFeePerGas': max_priority_fee,
                'chainId': 8453
            })

            signed = self.w3_http.eth.account.sign_transaction(approve_tx, private_key=self.private_key)
            tx_hash = await self.w3_http.eth.send_raw_transaction(signed.rawTransaction)
            logger.info(f"✅ [APPROVE] Allowance infinita enviada para o Router | TX: {tx_hash.hex()}")
            
        except Exception as e:
            logger.error(f"❌ [APPROVE] Falha ao enviar approve: {e}")

    async def execute_sell(self, target_token, sell_percentage=100):
        """
        Executa a venda de uma porcentagem do saldo do token alvo.
        """
        if not self.private_key:
            return
            
        logger.info(f"🔄 [VENDA] Iniciando venda de {sell_percentage}% de {target_token}...")
        
        try:
            WETH_BASE = self.w3_http.to_checksum_address("0x4200000000000000000000000000000000000006")
            target_token_checksum = self.w3_http.to_checksum_address(target_token)
            
            token_contract = self.w3_http.eth.contract(address=target_token_checksum, abi=ERC20_ABI)
            account = self.w3_http.eth.account.from_key(self.private_key)
            
            # Checar saldo
            balance = await token_contract.functions.balanceOf(account.address).call()
            if balance == 0:
                logger.warning(f"⚠️ [VENDA] Saldo zero para {target_token}. Cancelando venda.")
                return
                
            amount_to_sell = int(balance * (sell_percentage / 100))
            if amount_to_sell == 0:
                return
                
            path = [target_token_checksum, WETH_BASE]
            
            # Estimativa de retorno (apenas para log e amountOutMin)
            expected_out = await self.get_amounts_out(amount_to_sell, path)
            slippage_tolerance = 0.50  # 50% slippage agressivo para saídas de emergência
            amount_out_min = int(expected_out * slippage_tolerance)
            
            router = self.w3_http.eth.contract(address=self.w3_http.to_checksum_address(ROUTER_ADDRESS), abi=ROUTER_ABI)
            nonce = await self.w3_http.eth.get_transaction_count(account.address)
            
            latest_block = await self.w3_http.eth.get_block('latest')
            base_fee = latest_block['baseFeePerGas']
            max_priority_fee = self.w3_http.to_wei(0.5, 'gwei')
            max_fee_per_gas = (base_fee * 2) + max_priority_fee
            
            deadline = int(time.time()) + 60
            
            # Usar SupportingFeeOnTransferTokens para evitar falhas com tokens de taxa
            tx = await router.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(
                amount_to_sell,
                amount_out_min,
                path,
                account.address,
                deadline
            ).build_transaction({
                'from': account.address,
                'nonce': nonce,
                'maxFeePerGas': max_fee_per_gas,
                'maxPriorityFeePerGas': max_priority_fee,
                'chainId': 8453
            })
            
            signed_tx = self.w3_http.eth.account.sign_transaction(tx, private_key=self.private_key)
            tx_hash = await self.w3_http.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"✅ [VENDA ENVIADA] {sell_percentage}% liquidado | TX Hash: {tx_hash.hex()}")
            
        except Exception as e:
            logger.error(f"❌ [FALHA NA VENDA] Erro ao tentar vender {target_token}: {e}")

    async def monitor_position(self, target_token, entry_price_wei, initial_expected_out):
        """
        Monitora a posição a cada segundo para realizar lucros (TP), aplicar Trailing Stop (TS) ou Stop Loss (SL).
        """
        logger.info(f"📈 [MONITOR] Iniciando acompanhamento de preço para {target_token}...")
        
        # Espera para garantir que a TX de compra foi minerada e os tokens estão no saldo
        await asyncio.sleep(5)
        
        highest_eth_value = entry_price_wei
        tp_triggered = False
        
        WETH_BASE = self.w3_http.to_checksum_address("0x4200000000000000000000000000000000000006")
        target_token_checksum = self.w3_http.to_checksum_address(target_token)
        path = [target_token_checksum, WETH_BASE]
        
        token_contract = self.w3_http.eth.contract(address=target_token_checksum, abi=ERC20_ABI)
        account = self.w3_http.eth.account.from_key(self.private_key)
        
        balance = await token_contract.functions.balanceOf(account.address).call()
        if balance == 0:
            await asyncio.sleep(5)
            balance = await token_contract.functions.balanceOf(account.address).call()
            if balance == 0:
                logger.warning(f"⚠️ [MONITOR] Saldo zerado para {target_token}. Monitoramento encerrado.")
                return

        logger.info(f"📊 [MONITOR] Saldo inicial: {balance} tokens. Valor entrada: {entry_price_wei} wei")

        self.open_positions[target_token] = {
            "token": target_token,
            "entry_price": entry_price_wei,
            "highest_price": entry_price_wei,
            "current_price": entry_price_wei,
            "pnl_pct": 0.0
        }

        while self.is_active:
            if target_token not in self.open_positions:
                break # Vendida via panic sell ou outra task
                
            try:
                current_eth_value = await self.get_amounts_out(balance, path)
                
                if current_eth_value == 0:
                    await asyncio.sleep(2)
                    continue
                    
                highest_eth_value = max(highest_eth_value, current_eth_value)
                
                # Atualiza state da posição e propaga via WS
                pnl_pct = ((current_eth_value - entry_price_wei) / entry_price_wei) * 100
                self.open_positions[target_token].update({
                    "current_price": current_eth_value,
                    "highest_price": highest_eth_value,
                    "pnl_pct": round(pnl_pct, 2)
                })
                await self.broadcast_ws({"type": "open_positions", "positions": list(self.open_positions.values())})
                
                tp_target = entry_price_wei * (1 + (float(self.config.get('tp_pct', 100)) / 100.0))
                sl_target = entry_price_wei * (1 - (float(self.config.get('sl_pct', 20)) / 100.0))
                
                # Take-Profit
                if current_eth_value >= tp_target and not tp_triggered:
                    logger.info(f"💰 [TAKE PROFIT] Alvo de {self.config.get('tp_pct')}% atingido! Liquidando 50% de {target_token}...")
                    tp_triggered = True
                    await self.execute_sell(target_token, sell_percentage=50)
                    
                    realized_pnl_wei = (current_eth_value / 2) - (entry_price_wei / 2)
                    realized_pnl_usd = (realized_pnl_wei / 1e18) * self.eth_usd_price
                    self.daily_pnl_usd += realized_pnl_usd
                    if realized_pnl_usd > 0: self.win_trades += 1
                    logger.info(f"💸 PnL parcial (TP): +${realized_pnl_usd:.2f} USD")
                    await self.broadcast_ws({"type": "metrics_updated", "metrics": {"total_trades": self.total_trades, "win_trades": self.win_trades, "daily_pnl_usd": self.daily_pnl_usd}})
                    
                    await asyncio.sleep(5)
                    balance = await token_contract.functions.balanceOf(account.address).call()
                    if balance == 0:
                        break
                        
                    entry_price_wei = int(entry_price_wei / 2)
                    highest_eth_value = entry_price_wei
                    continue

                # Trailing Stop: -15%
                if current_eth_value <= highest_eth_value * 0.85:
                    logger.warning(f"📉 [TRAILING STOP] Preço caiu 15% do topo. Liquidando 100% de {target_token}...")
                    await self.execute_sell(target_token, sell_percentage=100)
                    
                    realized_pnl_wei = current_eth_value - entry_price_wei
                    realized_pnl_usd = (realized_pnl_wei / 1e18) * self.eth_usd_price
                    self.daily_pnl_usd += realized_pnl_usd
                    if realized_pnl_usd > 0: self.win_trades += 1
                    logger.info(f"💸 PnL da operação (TS): ${realized_pnl_usd:.2f} USD")
                    await self.broadcast_ws({"type": "metrics_updated", "metrics": {"total_trades": self.total_trades, "win_trades": self.win_trades, "daily_pnl_usd": self.daily_pnl_usd}})
                    
                    del self.open_positions[target_token]
                    await self.broadcast_ws({"type": "open_positions", "positions": list(self.open_positions.values())})
                    
                    if self.daily_pnl_usd <= -self.max_daily_loss_usd:
                        self.is_active = False
                        logger.error(f"🛑 [CIRCUIT BREAKER] Limite de perda diária atingido. Compras automáticas suspensas.")
                        asyncio.create_task(self.broadcast_ws({"type": "sniper_status", "is_active": self.is_active}))
                    break

                # Stop-Loss: dinâmico
                if current_eth_value <= sl_target:
                    logger.error(f"🛑 [STOP LOSS] Preço caiu para Stop Loss. Cortando perdas em {target_token}...")
                    await self.execute_sell(target_token, sell_percentage=100)
                    
                    realized_pnl_wei = current_eth_value - entry_price_wei
                    realized_pnl_usd = (realized_pnl_wei / 1e18) * self.eth_usd_price
                    self.daily_pnl_usd += realized_pnl_usd
                    if realized_pnl_usd > 0: self.win_trades += 1
                    logger.info(f"💸 PnL da operação (SL): ${realized_pnl_usd:.2f} USD")
                    await self.broadcast_ws({"type": "metrics_updated", "metrics": {"total_trades": self.total_trades, "win_trades": self.win_trades, "daily_pnl_usd": self.daily_pnl_usd}})
                    
                    del self.open_positions[target_token]
                    await self.broadcast_ws({"type": "open_positions", "positions": list(self.open_positions.values())})
                    
                    if self.daily_pnl_usd <= -self.max_daily_loss_usd:
                        self.is_active = False
                        logger.error(f"🛑 [CIRCUIT BREAKER] Limite de perda diária atingido. Compras automáticas suspensas.")
                        asyncio.create_task(self.broadcast_ws({"type": "sniper_status", "is_active": self.is_active}))
                    break
                    
            except Exception as e:
                logger.error(f"❌ [MONITOR] Erro durante monitoramento de preço: {e}")
                
            await asyncio.sleep(2)


    async def execute_swap(self, target_token, force=False, pair_address=None):
        """
        Gera e assina a transação de compra (Snipe) com:
        - Anti-Honeypot check via eth.call antes do disparo
        - EIP-1559, slippage e roteamento V2
        - Auto-Approve do Router após compra confirmada
        """
        if not self.is_active and not force:
            logger.warning(f"⏸️ [SNIPER PAUSADO] Snipe abortado para {target_token}. O robô está pausado.")
            return

        if not self.private_key:
            logger.warning(f"⚠️ Ignorando snipe no token {target_token}. Burner wallet inexistente.")
            return
            
        logger.info(f"⚡ [EXECUÇÃO] Preparando roteamento e compra de {target_token} na Base...")
        
        try:
            # 1. Configuração da Operação
            WETH_BASE = self.w3_http.to_checksum_address("0x4200000000000000000000000000000000000006")
            target_token_checksum = self.w3_http.to_checksum_address(target_token)
            path = [WETH_BASE, target_token_checksum]
            
            amount_in_eth = float(self.config.get('snipe_size_eth', 0.0005))
            amount_in_wei = self.w3_http.to_wei(amount_in_eth, 'ether')
            
            # 1.5 Validação Rápida de Liquidez (WETH) no Par
            if pair_address:
                try:
                    PAIR_MIN_ABI = [
                        {"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"stateMutability":"view","type":"function"},
                        {"inputs":[],"name":"token0","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}
                    ]
                    pair_contract = self.w3_http.eth.contract(address=pair_address, abi=PAIR_MIN_ABI)
                    reserves = await pair_contract.functions.getReserves().call()
                    token0_addr = await pair_contract.functions.token0().call()
                    
                    if token0_addr == WETH_BASE:
                        weth_reserve = reserves[0]
                    else:
                        weth_reserve = reserves[1]
                        
                    min_pool_weth_eth = float(self.config.get('min_pool_weth', 0.05))
                    if weth_reserve < self.w3_http.to_wei(min_pool_weth_eth, 'ether'):
                        logger.info(f"⚪ [FILTRO] Liquidez insuficiente no pool (< {min_pool_weth_eth} WETH). Snipe ignorado.")
                        return
                        
                    # 1.6 Validação de Queima/Trava de LP (LP Burn/Lock Check)
                    ERC20_MIN_ABI = [{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]
                    lp_contract = self.w3_http.eth.contract(address=pair_address, abi=ERC20_MIN_ABI)
                    
                    dead_addr = self.w3_http.to_checksum_address("0x000000000000000000000000000000000000dEaD")
                    zero_addr = self.w3_http.to_checksum_address("0x0000000000000000000000000000000000000000")
                    
                    # Lockers comuns na Base (PinkSale, Unicrypt, Team Finance etc) - Endereços simplificados para proxy
                    known_lockers = [
                        self.w3_http.to_checksum_address("0x71B5759d73262FBb223956913ecF4ecC51057641"), # Ex: PinkSale Base
                        self.w3_http.to_checksum_address("0x231278eDd38B00B07fBd52120CEf685B9BaEBCC1")  # Ex: Unicrypt Base
                    ]
                    
                    is_lp_safe = False
                    for addr in [dead_addr, zero_addr] + known_lockers:
                        locked_bal = await lp_contract.functions.balanceOf(addr).call()
                        if locked_bal > 0:
                            is_lp_safe = True
                            break
                            
                    if not is_lp_safe:
                        logger.warning("⚠️ [RISCO LP] Liquidez não travada/queimada. Snipe cancelado.")
                        return
                        
                except Exception as e:
                    logger.debug(f"Aviso: Não foi possível checar a reserva/LP do par {pair_address}: {e}")
            
            # 2. Estimativa de retorno via getAmountsOut
            expected_out = await self.get_amounts_out(amount_in_wei, path)
            if expected_out == 0:
                logger.error("❌ Abortando: Simulação retornou 0 tokens (Sem liquidez ou token scam/tax).")
                return

            slippage_tolerance = 0.80  # Slippage de 20% para snipes agressivos
            amount_out_min = int(expected_out * slippage_tolerance)
            logger.info(f"📊 Estimativa: {expected_out} | Mínimo aceitável: {amount_out_min}")

            # 3. ⛔ ANTI-HONEYPOT: Simula venda via eth.call antes de qualquer TX real
            is_safe = await self.anti_honeypot_check(target_token, amount_in_wei, expected_out)
            if not is_safe:
                return  # Abortado pelo Anti-Honeypot

            # 4. Preparação do Contrato e Conta
            logger.info("🟢 [SIMULAÇÃO APROVADA] Disparando ordem de compra real...")
            router = self.w3_http.eth.contract(address=self.w3_http.to_checksum_address(ROUTER_ADDRESS), abi=ROUTER_ABI)
            account = self.w3_http.eth.account.from_key(self.private_key)
            nonce = await self.w3_http.eth.get_transaction_count(account.address)
            
            # 5. Cálculo Dinâmico de Gás EIP-1559
            latest_block = await self.w3_http.eth.get_block('latest')
            base_fee = latest_block['baseFeePerGas']
            max_priority_fee = self.w3_http.to_wei(0.5, 'gwei')
            max_fee_per_gas = (base_fee * 2) + max_priority_fee
            
            # 5.5 Trava Dinâmica de Gás (Max Fee Cap)
            estimated_gas_limit = 250000 # Custo médio de um swap na V2
            estimated_gas_cost_wei = max_fee_per_gas * estimated_gas_limit
            estimated_gas_cost_usd = (estimated_gas_cost_wei / 1e18) * self.eth_usd_price
            
            max_gas_fee_usd = float(os.getenv('MAX_GAS_FEE_USD', 0.30))
            if estimated_gas_cost_usd > max_gas_fee_usd:
                logger.warning(f"⛽ [GÁS ELEVADO] Taxa de gás superior ao limite estipulado (${estimated_gas_cost_usd:.2f} > ${max_gas_fee_usd:.2f}). Operação abortada.")
                return
            
            deadline = int(time.time()) + 60
            
            # 6. Construção da Transação
            tx = await router.functions.swapExactETHForTokens(
                amount_out_min,
                path,
                account.address,
                deadline
            ).build_transaction({
                'from': account.address,
                'value': amount_in_wei,
                'nonce': nonce,
                'maxFeePerGas': max_fee_per_gas,
                'maxPriorityFeePerGas': max_priority_fee,
                'chainId': 8453
            })
            
            start_time = time.time()
            
            # 7. Assinatura Offline na RAM
            signed_tx = self.w3_http.eth.account.sign_transaction(tx, private_key=self.private_key)
            
            # 8. Disparo
            tx_hash = await self.w3_http.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            latency = (time.time() - start_time) * 1000
            logger.info(f"✅ [SNIPE ENVIADO] TX Hash: {tx_hash.hex()} | Latência: {latency:.2f}ms")
            
            self.total_trades += 1
            await self.broadcast_ws({"type": "metrics_updated", "metrics": {"total_trades": self.total_trades, "win_trades": self.win_trades, "daily_pnl_usd": self.daily_pnl_usd}})

            # 9. Auto-Approve do Router em background (não trava o loop)
            asyncio.create_task(self.auto_approve_router(target_token))
            
            # 10. Inicia Monitoramento de Posição (TP/SL) em background
            asyncio.create_task(self.monitor_position(target_token, amount_in_wei, expected_out))
            
        except Exception as e:
            logger.error(f"❌ [FALHA DE EXECUÇÃO] Erro crítico no Sniper: {e}")

    # ---------------------------------------------------------
    # WebSocket Server (Comunicação com React)
    # ---------------------------------------------------------
    async def ws_handler(self, websocket):
        self.connected_clients.add(websocket)
        logger.info(f"🔌 [WS] Cliente conectado no painel Sniper. Total: {len(self.connected_clients)}")
        
        try:
            # Enviar status inicial da carteira e do robô
            status_payload = {
                "type": "wallet_status",
                "wallet_address": self.wallet_address if self.wallet_address else None,
                "is_active": self.is_active
            }
            await websocket.send(json.dumps(status_payload))
            await websocket.send(json.dumps({
                "type": "sniper_status",
                "is_active": self.is_active
            }))
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")

                    if msg_type == "add_wallet":
                        address = data.get("address")
                        pk = data.get("private_key")
                        
                        if address and pk:
                            logger.info(f"🔐 [WS] Recebida nova Burner Wallet: {address}")
                            await asyncio.to_thread(self._sync_save_wallet, address, pk)
                            await self.load_wallet()
                            
                            # Broadcast status atualizado para todos clientes
                            update_payload = {
                                "type": "wallet_status",
                                "wallet_address": self.wallet_address,
                                "is_active": self.is_active
                            }
                            await self.broadcast_ws(update_payload)

                    elif msg_type == "toggle_sniper":
                        new_state = data.get("is_active")
                        if new_state is None:
                            self.is_active = not self.is_active
                        else:
                            self.is_active = bool(new_state)
                        
                        if self.is_active:
                            logger.info("🟢 [STATUS] Base Meme Sniper ATIVADO pelo operador via painel!")
                        else:
                            logger.warning("⏸️ [STATUS] Base Meme Sniper PAUSADO pelo operador via painel! Novas ordens automáticas bloqueadas.")
                        
                        await self.broadcast_ws({
                            "type": "sniper_status",
                            "is_active": self.is_active
                        })

                    elif msg_type == "manual_snipe":
                        token = data.get("token")
                        if token:
                            logger.info(f"🎯 [MANUAL] Disparo manual de Snipe solicitado para: {token}")
                            asyncio.create_task(self.execute_swap(token, force=True))
                            
                    elif msg_type == "update_config":
                        new_config = data.get("config", {})
                        if new_config:
                            self.config.update(new_config)
                            logger.info(f"⚙️ [CONFIG] Parâmetros de risco atualizados via WS: {self.config}")
                            await self.broadcast_ws({"type": "config_updated", "config": self.config})
                            
                    elif msg_type == "force_sell":
                        token = data.get("token")
                        if token and token in self.open_positions:
                            logger.warning(f"🚨 [PANIC SELL] Venda de emergência solicitada pelo operador para {token}!")
                            asyncio.create_task(self.execute_sell(token, sell_percentage=100))
                            del self.open_positions[token]
                            await self.broadcast_ws({"type": "open_positions", "positions": list(self.open_positions.values())})
                except Exception as e:
                    logger.error(f"❌ [WS] Erro ao processar mensagem: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.connected_clients.remove(websocket)
            logger.info(f"🔌 [WS] Cliente desconectado.")

    async def broadcast_ws(self, payload):
        if not self.connected_clients:
            return
        msg = json.dumps(payload)
        for client in set(self.connected_clients):
            try:
                await client.send(msg)
            except websockets.exceptions.ConnectionClosed:
                pass

    async def start_ws_server(self):
        logger.info(f"📡 [WS] Iniciando WebSocket Sniper em ws://0.0.0.0:{SNIPER_WS_PORT}")
        async with websockets.serve(self.ws_handler, "0.0.0.0", SNIPER_WS_PORT):
            await asyncio.Future()

    # ---------------------------------------------------------
    # Injeção de Dependências e Orquestração
    # ---------------------------------------------------------
    async def run(self):
        logger.info("Iniciando Microsserviço Assíncrono: Base Meme Sniper 🚀")
        
        # O servidor WebSocket SEMPRE sobe para manter o container vivo
        # e permitir que o painel React mostre erros de configuração
        if not self.rpc_ok:
            logger.critical(
                "⛔ [STANDBY] RPCs não configurados. O servidor WebSocket subirá na porta "
                f"{SNIPER_WS_PORT} para diagnóstico, mas nenhum snipe será executado. "
                "Configure BASE_RPC_WS e BASE_RPC_HTTP no painel de variáveis de ambiente."
            )
            # Sobe apenas o WS para manter container ativo e aceitando conexões do React
            await self.start_ws_server()
            return
        
        # Carregamento do estado persistido sem travar o Event Loop
        await self.load_wallet()
        
        # Tasks concorrentes plenas (RPC disponível)
        tasks = [
            self.start_ws_server(),
            self.listen_new_pairs(),
        ]
        
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"❌ Falha no Event Loop principal: {e}")

async def main():
    sniper = BaseMemeSniper()
    await sniper.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Meme Sniper interrompido pelo operador.")
