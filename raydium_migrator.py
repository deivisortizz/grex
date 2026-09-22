import asyncio
import json
import logging
import base64
import os
import traceback
from datetime import datetime
import aiohttp
import websockets
from solders.transaction import VersionedTransaction
from solders.keypair import Keypair
import base58

from solana_core import is_rate_limited_error, rate_limit_delay

logger = logging.getLogger("RaydiumMigrator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

class RaydiumMigrator:
    def __init__(self, main_sniper):
        self.main = main_sniper
        self.migration_ws_url = "wss://pumpportal.fun/api/data"
        # [FIX] Sem isso, uma mensagem de migração duplicada/reenviada pelo PumpPortal
        # (reconexão do WS, retry, etc.) podia disparar handle_raydium_snipe duas vezes
        # para o mesmo mint antes da primeira compra terminar e popular open_positions
        # (a checagem de max_positions só vê a posição DEPOIS da compra confirmar).
        self.migrated_seen = set()

    async def _execute_raydium_buy(self, user_id, state, token_mint):
        """Dispara a compra diretamente para o pool Raydium usando PumpPortal Trade API"""
        try:
            wallet_pk_str = state.get("wallet")
            if not wallet_pk_str:
                return False

            if wallet_pk_str.startswith("["):
                key_bytes = bytes(json.loads(wallet_pk_str))
                payer = Keypair.from_bytes(key_bytes)
            else:
                payer = Keypair.from_bytes(base58.b58decode(wallet_pk_str))
                
            jito_tip_sol = float(state["config"]["jito_tip"])
            slippage = float(state["config"]["slippage"])
            buy_amount_sol = float(state["config"].get("trade_amount", 0.005))
            
            rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=afef48e6-b88a-49e6-84c4-9b408156ee55")

            async with aiohttp.ClientSession() as session:
                payer_pubkey_str = str(payer.pubkey())
                balance_before = await self.main._get_sol_balance(payer_pubkey_str, session, rpc_url)
                
                required_balance = buy_amount_sol + jito_tip_sol + 0.002
                if balance_before < required_balance:
                    await self.main.log_to_user(user_id, "ERROR", f"❌ Saldo insuficiente para Raydium Snipe! Requerido: ~{required_balance:.5f} SOL")
                    return False

                await self.main.log_to_user(user_id, "WARN", f"🔥 Construindo transação atômica (Raydium) para {token_mint} | Valor: {buy_amount_sol} SOL...")
                
                payload = {
                    "publicKey": str(payer.pubkey()),
                    "action": "buy",
                    "mint": token_mint.strip(),
                    "amount": float(buy_amount_sol),
                    "denominatedInSol": "true",
                    "slippage": int(slippage),
                    "priorityFee": float(jito_tip_sol),
                    "pool": "raydium" # CRÍTICO: Roteia via Raydium
                }

                async with session.post("https://pumpportal.fun/api/trade-local", json=payload) as response:
                    if response.status != 200:
                        err_text = await response.text()
                        await self.main.log_to_user(user_id, "ERROR", f"Falha na API PumpPortal (Raydium Buy): {err_text}")
                        return False
                    tx_bytes = await response.read()

                transaction = VersionedTransaction.from_bytes(tx_bytes)
                signed_tx = VersionedTransaction(transaction.message, [payer])
                
                await self.main.log_to_user(user_id, "WARN", "🚀 Disparando transação assinada para a rede (Jito/Raydium)...")
                
                encoded_tx = base64.b64encode(bytes(signed_tx)).decode('utf-8')
                rpc_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "sendTransaction",
                    "params": [
                        encoded_tx,
                        {
                            "encoding": "base64",
                            "skipPreflight": True,
                            "maxRetries": 0
                        }
                    ]
                }
                
                async with session.post(rpc_url, json=rpc_payload) as rpc_resp:
                    rpc_result = await rpc_resp.json()
                    
                    if "result" in rpc_result:
                        tx_sig = rpc_result["result"]
                        await self.main.log_to_user(user_id, "INFO", f"✅ Transação Raydium disparada! TX: {tx_sig}")
                        
                        await self.main.log_to_user(user_id, "INFO", "⏳ Aguardando confirmação (mudança de saldo)...")
                        balance_after = await self.main._wait_for_balance_change(payer_pubkey_str, balance_before, True, session, rpc_url, user_id)
                        
                        sol_spent = balance_before - balance_after
                        if sol_spent <= 0:
                            await self.main.log_to_user(user_id, "ERROR", "❌ [FALHA] Saldo inalterado ou timeout da RPC. A transação falhou na Raydium.")
                            return False
                            
                        await self.main.log_to_user(user_id, "INFO", f"💸 Saldo final: {balance_after:.5f} SOL | Custo Real: {sol_spent:.5f} SOL")
                        
                        state["open_positions"][token_mint] = {
                            "sol_spent": sol_spent,
                            # [FIX] Faltava registrar "buy_amount_sol" (valor real que virou
                            # posição). handle_raydium_snipe usa isso como base do SL/TP;
                            # sem essa chave, ele sempre caía no fallback "sol_spent" (débito
                            # total incluindo tip Jito + rent de conta nova), fazendo o trade
                            # parecer instantaneamente no vermelho sem o preço ter se mexido.
                            "buy_amount_sol": buy_amount_sol,
                            "jito_tip_buy": jito_tip_sol
                        }
                        return True
                    else:
                        err_msg = rpc_result.get("error", "Erro desconhecido")
                        await self.main.log_to_user(user_id, "ERROR", f"A rede retornou erro ao enviar a transação (Raydium): {err_msg}")
                        return False
        except Exception as e:
            await self.main.log_to_user(user_id, "ERROR", f"Falha crítica ao executar Raydium snipe: {e}")
            logger.error(traceback.format_exc())
            return False

    async def handle_raydium_snipe(self, user_id, state, token_mint):
        # [FIX] Protege a task fire-and-forget: sem isto, uma exceção não tratada aqui
        # travaria o "status" do usuário em "sniping" permanentemente.
        try:
            success = await self._execute_raydium_buy(user_id, state, token_mint)
            if success:
                state["config"]["status"] = "monitoring_position"
                await self.main.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                # [FIX] Usar "buy_amount_sol" (valor real que virou posição) como referência
                # de entrada do SL/TP, não "sol_spent" (débito total: compra + tip + rent).
                pos_data = state.get("open_positions", {}).get(token_mint, {})
                sol_spent = pos_data.get("sol_spent", 0.0)
                entry_reference = pos_data.get("buy_amount_sol", sol_spent)
                asyncio.create_task(self.main.monitor_position(user_id, entry_reference, token_mint=token_mint))
            else:
                if state["is_active"]:
                    await self.main.log_to_user(user_id, "WARN", "⚠️ A compra falhou ou foi abortada na Raydium. Recuperando fôlego (3s)...")
                    await asyncio.sleep(3)
                    if state["is_active"]:
                        state["config"]["status"] = "watching"
                        await self.main.log_to_user(user_id, "INFO", "🔄 Retornando ao modo de escuta para migrações Raydium.")
                        await self.main.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
        except Exception as e:
            logger.error(f"Falha crítica não tratada em handle_raydium_snipe ({token_mint}): {e}")
            logger.error(traceback.format_exc())
            if state.get("is_active") and token_mint not in state.get("open_positions", {}):
                state["config"]["status"] = "watching"
                await self.main.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})

    async def migration_listener_loop(self):
        """Escuta eventos de migração para a Raydium em tempo real via PumpPortal WS"""
        # [FIX] Reconexão quase instantânea com backoff exponencial (em vez de 5s fixos)
        # para minimizar migrações perdidas durante quedas de conexão do WS.
        min_delay = 0.25
        max_delay = 10.0
        reconnect_delay = min_delay
        rate_limit_streak = 0
        consecutive_errors = 0
        while True:
            has_active_users = any(state.get("config", {}).get("raydium_migrator_active") for state in self.main.user_states.values() if state["is_active"])
            if not has_active_users:
                await asyncio.sleep(5)
                continue

            try:
                async with websockets.connect(self.migration_ws_url, ping_interval=30, ping_timeout=10) as ws:
                    logger.info("📡 Iniciando rastreador oficial de Migração Raydium (Pool Creation)...")
                    await ws.send(json.dumps({"method": "subscribeMigration"}))
                    reconnect_delay = min_delay
                    rate_limit_streak = 0
                    consecutive_errors = 0

                    async for message in ws:
                        has_active_users = any(state.get("config", {}).get("raydium_migrator_active") for state in self.main.user_states.values() if state["is_active"])
                        if not has_active_users:
                            break 

                        data = json.loads(message)
                        mint = data.get("mint")
                        signature = data.get("signature")

                        # [FIX] Deduplicação por mint: evita disparar handle_raydium_snipe
                        # duas vezes para o mesmo token caso o PumpPortal reenvie o evento
                        # de migração (reconexão do WS, retry de rede, etc.).
                        if mint and mint in self.migrated_seen:
                            continue

                        if mint and signature:
                            self.migrated_seen.add(mint)
                            # 1. Extração Dinâmica ou Simulação Realista para Migrações Raydium
                            vol = data.get("v_sol", data.get("volume", data.get("initialBuy", 85.0))) # Geralmente migrações Raydium têm liquidez de ~85 SOL na pool
                            mcap = data.get("usd_market_cap", data.get("market_cap", data.get("mcap", 69000.0))) # Market cap de formatura na Pump.fun costuma ser ~$69k
                            name = data.get("name", data.get("token_name"))
                            symbol = data.get("symbol", data.get("token_symbol"))
                            
                            if not name or name == "???":
                                name = f"Raydium-{mint[:4]}"
                            if not symbol or symbol == "???":
                                symbol = "RAY"
                                
                            pool_payload = {
                                "type": "new_pool",
                                "token": mint,
                                "timestamp": int(datetime.now().timestamp() * 1000),
                                "name": name,
                                "symbol": symbol,
                                "image_uri": data.get("image_uri", ""),
                                "usd_market_cap": mcap,
                                "volume": vol,
                                "reply_count": data.get("reply_count", 0)
                            }
                            
                            for user_id, state in list(self.main.user_states.items()):
                                if state["is_active"]:
                                    await self.main.broadcast_to_user(user_id, pool_payload)
                                    
                                if state["is_active"] and state["config"].get("raydium_migrator_active"):
                                    target_token = state["config"].get("target_token")
                                    if target_token and target_token != mint:
                                        continue 
                                        
                                    max_pos = int(state["config"].get("max_positions", 1))
                                    if len(state.get("open_positions", {})) < max_pos:
                                        await self.main.log_to_user(user_id, "WARN", f"🦄 [RAYDIUM POOL] Token acabou de migrar com LP Burned! Atirando na abertura da Pool!")
                                        state["config"]["status"] = "sniping"
                                        await self.main.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                                        asyncio.create_task(self.handle_raydium_snipe(user_id, state, mint))
                                        
            except Exception as e:
                consecutive_errors += 1
                if is_rate_limited_error(e):
                    delay = rate_limit_delay(rate_limit_streak)
                    rate_limit_streak += 1
                    if consecutive_errors <= 3 or consecutive_errors % 5 == 0:
                        logger.error(f"⛔ PumpPortal retornou 429 (rate limit) no Raydium Migrator. Aguardando {delay:.0f}s (ocorrência #{consecutive_errors})...")
                    await asyncio.sleep(delay)
                else:
                    rate_limit_streak = 0
                    if consecutive_errors <= 3 or consecutive_errors % 5 == 0:
                        logger.error(f"Erro no WSS Raydium Migrator: {e}. Reconectando em {reconnect_delay:.2f}s...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_delay)
