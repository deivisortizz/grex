import asyncio
import aiohttp
import argparse
import os
import sqlite3
import json
import logging
from dotenv import load_dotenv
from solders.pubkey import Pubkey

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger('WalletHunter')

# [FIX] Antes era um caminho relativo fixo ("data"), diferente de server.py/solana_core.py/
# base_meme_sniper.py (que resolvem um caminho absoluto e respeitam a env var DATA_DIR). Se
# DATA_DIR for customizada (ex.: volume persistente num deploy), o WalletHunter silenciosamente
# lia/gravava um sniper.db diferente do resto do sistema (tracked_wallets, blacklist etc).
DATA_DIR = os.getenv('DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))

class WalletHunter:
    def __init__(self, rpc_url):
        self.rpc_url = rpc_url
        self.db_path = os.path.join(DATA_DIR, 'sniper.db')

    async def _fetch_oldest_signatures(self, session, mint):
        """Pagina a API do RPC usando getSignaturesForAddress até o bloco 0"""
        logger.info(f"🔍 Iniciando máquina do tempo (Time Machine) para o token {mint}...")
        
        signatures = []
        before = None
        
        while True:
            params = [mint, {"limit": 1000}]
            if before:
                params[1]["before"] = before
                
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": params
            }
            
            try:
                async with session.post(self.rpc_url, json=payload, timeout=10.0) as resp:
                    if resp.status != 200:
                        logger.error(f"Erro na API: HTTP {resp.status}")
                        break
                        
                    data = await resp.json()
                    result = data.get("result", [])
                    
                    if not result:
                        break
                        
                    # Paginação
                    before = result[-1]["signature"]
                    
                    # Se retornou menos de 1000, significa que batemos no fundo do poço (bloco 0)
                    if len(result) < 1000:
                        # As últimas transações desta página são as mais antigas da história do token!
                        # Vamos pegar as 25 mais antigas (que estão no final da lista, pois a ordem é descrescente de tempo)
                        oldest_sigs = [tx["signature"] for tx in result[-25:]]
                        # Inverte para que a index 0 seja a criação, index 1 seja a primeira compra, etc.
                        oldest_sigs.reverse()
                        return oldest_sigs
                        
            except Exception as e:
                logger.error(f"Erro de conexão no Time Machine: {e}")
                break
                
        return []

    async def _extract_buyers_from_txs(self, session, signatures, mint):
        """Busca as transações brutas e extrai as carteiras que compraram no bloco zero"""
        logger.info(f"📜 Analisando {len(signatures)} transações iniciais...")
        buyers = set()
        dev_wallet = None
        
        for idx, sig in enumerate(signatures):
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [
                    sig,
                    {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
                ]
            }
            
            try:
                async with session.post(self.rpc_url, json=payload, timeout=8.0) as resp:
                    data = await resp.json()
                    result = data.get("result")
                    if not result:
                        continue
                        
                    meta = result.get("meta", {})
                    if meta.get("err"):
                        continue # Transação falhou
                        
                    pre_balances = meta.get("preTokenBalances", [])
                    post_balances = meta.get("postTokenBalances", [])
                    
                    # Identificar carteiras cujo saldo do token aumentou
                    for post_bal in post_balances:
                        if post_bal.get("mint") == mint:
                            owner = post_bal.get("owner")
                            
                            # Ignora contas de sistema / pool (bonding curve)
                            if owner == "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P":
                                continue
                                
                            post_amt = float(post_bal.get("uiTokenAmount", {}).get("uiAmount") or 0.0)
                            
                            pre_amt = 0.0
                            for pre_bal in pre_balances:
                                if pre_bal.get("owner") == owner and pre_bal.get("mint") == mint:
                                    pre_amt = float(pre_bal.get("uiTokenAmount", {}).get("uiAmount") or 0.0)
                                    break
                                    
                            if post_amt > pre_amt:
                                # Se é a primeira transação da história (idx == 0), este é o Dev/Criador!
                                if idx == 0 and not dev_wallet:
                                    dev_wallet = owner
                                    logger.info(f"👨‍💻 Dev identificado (ignorado do Copy Trade): {dev_wallet}")
                                else:
                                    # Se não é o dev, e comprou nas primeiras transações, é um sniper do bloco zero!
                                    if owner != dev_wallet:
                                        buyers.add(owner)
            except Exception as e:
                logger.error(f"Erro ao processar TX {sig}: {e}")
                
            # Rate limit básico (não metralhar o RPC)
            await asyncio.sleep(0.05)
            
        return list(buyers)

    async def _analyze_wallet_elite(self, session, wallet):
        """Elite Filter heurístico: verifica saldo e validação anti-burner."""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [wallet]
            }
            async with session.post(self.rpc_url, json=payload, timeout=8.0) as resp:
                data = await resp.json()
                lamports = data.get("result", {}).get("value", 0)
                sol_balance = lamports / 1e9
                
                # Regra Elite 1: Se a carteira tem menos de 0.2 SOL, provavelmente é um Burner Bot (One-Hit Wonder) 
                # que comprou, rugou e jogou a carteira fora. Não queremos seguir isso.
                if sol_balance < 0.2:
                    return False, f"Saldo muito baixo (Burner Bot): {sol_balance:.3f} SOL"
                    
                # Aqui poderíamos adicionar lógicas complexas de Win Rate puxando trades,
                # mas o saldo é uma heurística super poderosa. Se o cara tá no bloco 0 e tem
                # saldo relevante, é um insider/smart money ativo.
                return True, f"Smart Wallet c/ {sol_balance:.2f} SOL"
                
        except Exception:
            pass
        return False, "Falha ao checar a carteira"

    def _inject_into_db(self, user_id, wallet, label):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Checa se já existe
            cursor.execute("SELECT id FROM tracked_wallets WHERE wallet_address = ? AND user_id = ?", (wallet, user_id))
            if cursor.fetchone():
                logger.info(f"⚠️ Carteira {wallet} já está sendo rastreada.")
                conn.close()
                return False
                
            cursor.execute(
                "INSERT INTO tracked_wallets (user_id, wallet_address, label, is_active) VALUES (?, ?, ?, 1)",
                (user_id, wallet, label)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Erro ao injetar no banco de dados: {e}")
            return False

    async def run(self, mint, user_id):
        logger.info(f"🎯 Iniciando caçada aos insiders do token {mint}...")
        
        async with aiohttp.ClientSession() as session:
            oldest_sigs = await self._fetch_oldest_signatures(session, mint)
            if not oldest_sigs:
                logger.error("Nenhuma transação encontrada. O token existe?")
                return {
                    "status": "error",
                    "message": "Nenhuma transação encontrada para este contrato. Verifique se o Mint é válido.",
                    "approved_count": 0,
                    "total_buyers": 0,
                    "wallets": []
                }
                
            buyers = await self._extract_buyers_from_txs(session, oldest_sigs, mint)
            if not buyers:
                logger.warning("Nenhum comprador precoce identificado.")
                return {
                    "status": "warning",
                    "message": "Nenhum comprador precoce identificado no bloco zero.",
                    "approved_count": 0,
                    "total_buyers": 0,
                    "wallets": []
                }
                
            logger.info(f"👥 Encontrados {len(buyers)} snipers no bloco zero. Aplicando Elite Filter...")
            
            approved_count = 0
            approved_wallets = []
            for wallet in buyers:
                is_elite, reason = await self._analyze_wallet_elite(session, wallet)
                if is_elite:
                    logger.info(f"✅ APROVADO: {wallet} ({reason})")
                    label = f"Insider ({mint[:4]}..{mint[-4:]})"
                    inserted = self._inject_into_db(user_id, wallet, label)
                    if inserted:
                        approved_count += 1
                        approved_wallets.append({"address": wallet, "label": label, "reason": reason})
                else:
                    logger.info(f"🚫 REJEITADO: {wallet} ({reason})")
                    
            logger.info(f"🎉 Caçada finalizada! {approved_count} Smart Wallets foram injetadas no Copy Sniper.")
            return {
                "status": "success",
                "message": f"Caçada finalizada! {approved_count} Smart Wallets de Elite foram aprovadas e salvas para Copy Trading.",
                "approved_count": approved_count,
                "total_buyers": len(buyers),
                "wallets": approved_wallets
            }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Caçador de Baleias do Bloco Zero (Wallet Hunter)")
    parser.add_argument("--mint", type=str, required=True, help="Endereço de contrato (Mint) do token de sucesso")
    parser.add_argument("--user", type=int, default=1, help="ID do usuário para atrelar no Copy Sniper (default: 1)")
    
    args = parser.parse_args()
    
    rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=afef48e6-b88a-49e6-84c4-9b408156ee55")
    
    hunter = WalletHunter(rpc_url)
    asyncio.run(hunter.run(args.mint, args.user))
