import asyncio
import json
import os
import sqlite3
import base64
import base58
import traceback
import websockets
import jwt
import logging
import sys
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

from solana_core import SolanaCore
from raydium_migrator import RaydiumMigrator

load_dotenv()

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('SolanaSniper')

# Dependências Solana verificadas acima

WS_PORT = int(os.getenv("SOLANA_SNIPER_WS_PORT", "8767"))

class SolanaSniper(SolanaCore):
    def __init__(self):
        super().__init__(logger_name="SolanaSniper")
        self.migration_triggered = set()
        self.raydium_migrator = RaydiumMigrator(self)

    async def _check_token_freshness(self, mint, session, rpc_url, anti_delay_filter=True, max_bonding_curve=20.0):
        # Retorna (is_fresh, message)
        if not anti_delay_filter:
            return True, "Filtro Anti-Atraso desativado (bypass)."
        try:
            from solders.pubkey import Pubkey
            import base64
            import struct
            mint_pk = Pubkey.from_string(mint)
            program_pk = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
            pda, _ = Pubkey.find_program_address([b"bonding-curve", bytes(mint_pk)], program_pk)
            
            payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getAccountInfo",
                "params": [str(pda), {"encoding": "base64"}]
            }
            # [FIX] Antes: até 10 tentativas com timeout de 4s + backoff progressivo,
            # o que podia levar ~50s no pior caso antes de liberar o "Modo Tolerante" —
            # exatamente quando a RPC costuma travar (muitos bots batendo no mesmo token
            # no bloco zero). Reduzido para falhar rápido e não perder a janela de entrada.
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    async with session.post(rpc_url, json=payload, timeout=1.5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if "result" in data and data["result"]["value"]:
                                b64_data = data["result"]["value"]["data"][0]
                                raw_bytes = base64.b64decode(b64_data)
                                if len(raw_bytes) >= 40:
                                    v_sol = struct.unpack("<Q", raw_bytes[16:24])[0]
                                    v_sol_normalized = v_sol / 1e9
                                    # Tokens da Pump.fun começam com exatos 30 SOL de reservas virtuais.
                                    if v_sol_normalized > (30.0 + max_bonding_curve):
                                        return False, f"Bonding curve avançada ({v_sol_normalized:.2f} SOL)."
                                    return True, "Token recém-criado (topo do bloco)."
                        elif resp.status == 429: # Rate Limit
                            await asyncio.sleep(0.3)
                            continue
                except (asyncio.TimeoutError, aiohttp.ClientError):
                    # Se houver erro de rede/timeout, tolera e tenta de novo
                    pass
                    
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.2) # [FIX] Backoff curto e fixo — aqui velocidade > tolerância
            
            # Se não encontrou a conta no RPC após o loop ou deu muito timeout, retorna como Bloco Zero (Modo Tolerante)
            return True, "Token no bloco zero ou RPC inacessível (Modo Tolerante)."
        except Exception:
            pass
        return True, "Bypass de filtro (erro inesperado)"

    async def _check_token_quality_for_global(self, mint, session, rpc_url, config):
        hardcore = config.get("hardcore_mode", False)

        # 0. Blacklist Automática de Criadores & 1. Filtro de Redes Sociais
        try:
            async with session.get(f"https://frontend-api.pump.fun/coins/{mint}", timeout=2.0) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Checagem de Blacklist (sempre ocorre)
                    creator = data.get("creator")
                    if creator and hasattr(self, '_is_blacklisted') and self._is_blacklisted(creator):
                        return False, f"[BLACKLIST] Criador reincidente bloqueado ({creator})"
                    
                    # Checagem de Redes Sociais (se hardcore = False)
                    if not hardcore and config.get("socials_filter", True):
                        has_socials = data.get("twitter") or data.get("telegram") or data.get("website")
                        if not has_socials:
                            return False, "Sem redes sociais válidas detectadas."
        except Exception:
            pass # Soft-fail: API indisponível, ignorar filtro para não perder o snipe

        # 2. Filtro de Fluxo Inicial (Volume)
        # [FIX] Antes esse sleep de 1.5s + checagem RPC rodava MESMO com hardcore_mode
        # ativado — o hardcore só pulava o filtro de redes sociais. Isso fazia o modo
        # "Global" comprar sistematicamente 1.5s+ depois da criação do token mesmo no
        # modo supostamente mais rápido, perdendo a janela de bloco zero pra outros bots.
        if hardcore:
            return True, "Hardcore Mode: filtro de fluxo inicial pulado (velocidade máxima)."

        # Espera 1.5s para ver se entram compras além do próprio Dev.
        await asyncio.sleep(1.5)
        try:
            from solders.pubkey import Pubkey
            import base64
            import struct
            mint_pk = Pubkey.from_string(mint)
            program_pk = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
            pda, _ = Pubkey.find_program_address([b"bonding-curve", bytes(mint_pk)], program_pk)
            
            payload = {
                "jsonrpc": "2.0", "id": 1,
                "method": "getAccountInfo",
                "params": [str(pda), {"encoding": "base64"}]
            }
            async with session.post(rpc_url, json=payload, timeout=2.0) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "result" in data and data["result"]["value"]:
                        b64_data = data["result"]["value"]["data"][0]
                        raw_bytes = base64.b64decode(b64_data)
                        if len(raw_bytes) >= 40:
                            v_sol = struct.unpack("<Q", raw_bytes[16:24])[0]
                            v_sol_normalized = v_sol / 1e9
                            
                            # Pump.fun começa com exatos 30 SOL virtuais. 
                            # Se tiver menos de 30.5 SOL (meio SOL injetado), o fluxo é praticamente nulo.
                            if v_sol_normalized < 30.5:
                                return False, f"Volume inicial insuficiente (Reservas SOL: {v_sol_normalized:.2f})."
                            return True, "Aprovado nos filtros de qualidade."
        except Exception:
            pass
            
        return True, "RPC indisponível/Timeout, ignorando filtro de fluxo inicial (Bypass)."

    async def _get_dynamic_metrics(self, mint, session, rpc_url):
        try:
            from solders.pubkey import Pubkey
            import base64
            import struct
            mint_pk = Pubkey.from_string(mint)
            program_pk = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
            pda, _ = Pubkey.find_program_address([b"bonding-curve", bytes(mint_pk)], program_pk)
            
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo", "params": [str(pda), {"encoding": "base64"}]}
            async with session.post(rpc_url, json=payload, timeout=2.0) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "result" in data and data["result"]["value"]:
                        b64_data = data["result"]["value"]["data"][0]
                        raw_bytes = base64.b64decode(b64_data)
                        if len(raw_bytes) >= 40:
                            v_sol = struct.unpack("<Q", raw_bytes[16:24])[0]
                            v_sol_normalized = v_sol / 1e9
                            
                            sol_price = 150.0
                            try:
                                async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT", timeout=1.0) as price_resp:
                                    if price_resp.status == 200:
                                        p_data = await price_resp.json()
                                        sol_price = float(p_data.get("price", 150.0))
                            except: pass
                            
                            calculated_mcap = (v_sol_normalized / 1.073) * sol_price
                            estimated_vol = v_sol_normalized # Usar a reserva de SOL inteira como Volume/Reserva inicial
                            return calculated_mcap, estimated_vol
        except Exception:
            pass
        return 0.0, 0.0

    async def _process_new_pool(self, signature):
        rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=afef48e6-b88a-49e6-84c4-9b408156ee55")
        async with aiohttp.ClientSession() as session:
            mint = await self._fetch_mint_from_tx(signature, session, rpc_url)
            if not mint:
                return
                
            # Filtro estrito de tokens do sistema (WSOL)
            if mint == "So11111111111111111111111111111111111111112" or mint.endswith("11111111111111111111111111111111"):
                logger.info(f"Token de sistema ignorado: WSOL ({mint})")
                return
                
            # Buscar metadados da Pump.fun para o Mayhem Screener (com retry para tokens muito novos)
            metadata = {}
            for attempt in range(3):
                try:
                    async with session.get(f"https://frontend-api.pump.fun/coins/{mint}", timeout=2.0) as resp:
                        if resp.status == 200:
                            metadata = await resp.json()
                            if metadata.get("name"):
                                break # Sucesso, sai do loop
                except Exception as e:
                    pass
                await asyncio.sleep(0.5) # Aguarda meio segundo antes de tentar novamente

            mcap = metadata.get("usd_market_cap", 0.0)
            volume = metadata.get("volume", 0.0)

            # [FIX] Antes esta chamada rodava DEPOIS do "async with aiohttp.ClientSession()"
            # ter sido fechado (o bloco terminava logo acima, no fim do for de retry). A
            # "session" já estava fechada aqui, então _get_dynamic_metrics sempre falhava
            # (RuntimeError "Session is closed", engolido pelo próprio except genérico dela)
            # e retornava (0.0, 0.0) — SEMPRE. Resultado: mcap/volume chegavam zerados no
            # front-end pra TODO token recém-criado (a API da Pump.fun quase nunca indexa a
            # tempo), que então caía no fallback fixo da UI ($4.5k / 0.01 SOL para 100% dos
            # tokens, tornando a ordenação por MCap/Volume e o Smart Alert inúteis).
            if not mcap or mcap == 0.0:
                dyn_mcap, dyn_vol = await self._get_dynamic_metrics(mint, session, rpc_url)
                if dyn_mcap > 0:
                    mcap = dyn_mcap
                if not volume or volume == 0.0:
                    volume = dyn_vol

        name = metadata.get("name") or metadata.get("tokenName")
        symbol = metadata.get("symbol") or metadata.get("tokenSymbol")

        if not name or name == "???":
            name = f"Pump-{mint[:4]}"
        if not symbol or symbol == "???":
            symbol = f"PUMP"

        logger.info(f"⚡ [LIVE POOL] Novo token criado na Pump.fun: {mint} | Name: {name}")

        # Broadcast para todos os clientes via WebSocket (Live Feed)
        payload = {
            "type": "new_pool",
            "token": mint,
            "timestamp": int(datetime.now().timestamp() * 1000),
            "name": name,
            "symbol": symbol,
            "image_uri": metadata.get("image_uri", ""),
            "usd_market_cap": mcap,
            "volume": volume,
            "reply_count": metadata.get("reply_count", 0)
        }
        msg = json.dumps(payload)
        to_remove = set()
        for client in self.connected_clients:
            try:
                await client.send(msg)
            except Exception:
                to_remove.add(client)
        for client in to_remove:
            self.connected_clients.remove(client)
            
        # Acionar Sniper Global
        for user_id, state in list(self.user_states.items()):
            if state["is_active"] and state["config"]["status"] == "watching":
                target_token = state["config"].get("target_token")
                if not target_token: # Modo Global
                    if not state.get("wallet"):
                        await self.log_to_user(user_id, "ERROR", "Nenhuma carteira Solana cadastrada. Desativando Sniper Global.")
                        state["is_active"] = False
                        state["config"]["status"] = "idle"
                        await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                        continue
                        
                    if state["config"].get("raydium_migration_filter"):
                        # [FIX] Usuário focado em Migração Raydium: ignora eventos de Bloco Zero
                        continue
                        
                    max_pos = state["config"].get("max_positions", 1)

                    # [FIX] Hardcore Mode só deve pular filtros que ADICIONAM ESPERA
                    # (qualidade/momentum). max_positions é gestão de risco de capital,
                    # não um filtro de velocidade — bypassar isso permitia abrir posições
                    # ilimitadas simultâneas mesmo com o limite configurado pelo usuário.
                    if len(state["open_positions"]) >= max_pos:
                        await self.log_to_user(user_id, "WARN", f"⏳ Limite de {max_pos} posições atingido. Ignorando novo pool: {mint}")
                        continue
                        
                    await self.log_to_user(user_id, "INFO", f"🌍 Evento GLOBAL detectado na Pump.fun para: {mint}!")
                    state["config"]["status"] = "sniping"
                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                    asyncio.create_task(self.handle_snipe_and_monitor(user_id, state, mint))

    async def _check_momentum_growth(self, user_id, target_token, duration=5.0):
        """
        Escuta o token no PumpPortal WS por 'duration' segundos.
        Exige pelo menos 2 ticks de preço, preço final >= inicial, e sem quedas > 2% entre ticks.
        """
        prices = []
        try:
            start_time = datetime.now().timestamp()
            async with websockets.connect("wss://pumpportal.fun/api/data", ping_interval=30, ping_timeout=10) as ws:
                subscribe_msg = {
                    "method": "subscribeTokenTrade",
                    "keys": [target_token]
                }
                await ws.send(json.dumps(subscribe_msg))
                
                while True:
                    now = datetime.now().timestamp()
                    if now - start_time >= duration:
                        break
                        
                    try:
                        # Timeout calculando tempo restante até o fim da janela de 5s
                        remaining = duration - (now - start_time)
                        if remaining <= 0:
                            break
                        message = await asyncio.wait_for(ws.recv(), timeout=min(1.0, remaining))
                        data = json.loads(message)
                        if data.get("mint") == target_token:
                            v_sol = data.get("vSolInBondingCurve")
                            v_tokens = data.get("vTokensInBondingCurve")
                            if v_sol and v_tokens and v_tokens > 0:
                                price_in_sol = float(v_sol) / float(v_tokens)
                                prices.append(price_in_sol)
                    except asyncio.TimeoutError:
                        continue
                        
        except Exception as e:
            logger.error(f"Erro no Momentum WS: {e}")
            return False, "Erro ao rastrear momentum na Pump.fun."

        if len(prices) < 2:
            return False, "Dados insuficientes (menos de 2 ticks no período)."
            
        if prices[-1] < prices[0]:
            return False, f"Tendência de queda (Início maior que o Fim)."
            
        for i in range(1, len(prices)):
            if prices[i] < prices[i-1] * 0.98: # Queda > 2%
                return False, f"Alta volatilidade (queda brusca >2% detectada)."
                
        return True, "Crescimento estável validado."

    async def handle_snipe_and_monitor(self, user_id, state, target_token):
        # [FIX] Toda a função roda dentro de um try/except: como é sempre disparada via
        # asyncio.create_task (fire-and-forget), uma exceção não tratada aqui travaria o
        # "status" do usuário em "sniping" para sempre (sniper órfão, sem crash visível e
        # sem log de erro), sem qualquer chance de auto-recuperação.
        try:
            # Filtro de Anti-Golpe/Qualidade Apenas no Modo Global (quando target_token na config é vazio)
            if not state["config"].get("target_token"):
                rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=afef48e6-b88a-49e6-84c4-9b408156ee55")
                async with aiohttp.ClientSession() as session:
                    is_quality, msg = await self._check_token_quality_for_global(target_token, session, rpc_url, state.get("config", {}))
                    if not is_quality:
                        await self.log_to_user(user_id, "WARN", f"🚫 [FILTRO] Token descartado: {msg}")
                        # Retorna para estado watching
                        if state["is_active"]:
                            state["config"]["status"] = "watching"
                            await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                        return False
                    await self.log_to_user(user_id, "INFO", f"✅ [FILTRO APROVADO] {msg}")

            # [FIX] Consistência com o Hardcore Mode: hardcore = velocidade máxima, então também
            # pula o filtro de Momentum (5s) — antes ele rodava os 5s completos mesmo com hardcore
            # ativado, o que contradizia a própria proposta do modo (zero espera / zero filtro pesado).
            hardcore_mode = state["config"].get("hardcore_mode", False)
            if state["config"].get("momentum_filter", False):
                if hardcore_mode:
                    await self.log_to_user(user_id, "INFO", "⚡ Hardcore Mode ativo: filtro de Momentum (5s) pulado para velocidade máxima.")
                else:
                    await self.log_to_user(user_id, "INFO", "📈 Iniciando análise de Momentum (5s)...")
                    is_momentum, msg = await self._check_momentum_growth(user_id, target_token)
                    if not is_momentum:
                        await self.log_to_user(user_id, "WARN", f"🚫 [FILTRO MOMENTUM] Token descartado: {msg}")
                        if state["is_active"]:
                            state["config"]["status"] = "watching"
                            await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                        return False
                    await self.log_to_user(user_id, "INFO", f"✅ [MOMENTUM APROVADO] {msg}")

            success = await self.execute_real_snipe(user_id, state, target_token)
            if success:
                state["config"]["status"] = "monitoring_position"
                await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                # Start position monitoring
                # [FIX] Antes usávamos "sol_spent" (débito total da carteira: compra + tip + rent
                # de conta nova) como referência de entrada pro monitor de SL/TP. Isso fazia
                # qualquer trade pequeno parecer instantaneamente -50% a -75% no primeiro tick,
                # mesmo sem o preço do token ter se mexido — porque tip e rent não compram token,
                # só o "buy_amount_sol" vira posição de fato. sol_spent continua sendo usado (correto)
                # no _save_trade_history pro P&L real em SOL no final do trade.
                pos_data = state.get("open_positions", {}).get(target_token, {})
                sol_spent = pos_data.get("sol_spent", 0.0)
                entry_reference = pos_data.get("buy_amount_sol", sol_spent)
                asyncio.create_task(self.monitor_position(user_id, entry_reference, token_mint=target_token))
            else:
                if state["is_active"]:
                    await self.log_to_user(user_id, "WARN", "⚠️ A compra falhou ou foi abortada. Recuperando fôlego (3s)...")
                    await asyncio.sleep(3)
                    if state["is_active"]:
                        state["config"]["status"] = "watching"
                        await self.log_to_user(user_id, "INFO", "🔄 Sistema recuperado: Retornando ao modo de escuta para novos lançamentos.")
                        await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
        except Exception as e:
            logger.error(f"Falha crítica não tratada em handle_snipe_and_monitor ({target_token}): {e}")
            self.logger.error(traceback.format_exc())
            if state.get("is_active") and target_token not in state.get("open_positions", {}):
                state["config"]["status"] = "watching"
                await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})

    async def monitor_loop(self):
        wss_url = os.getenv("SOLANA_WSS_URL", "wss://mainnet.helius-rpc.com/?api-key=afef48e6-b88a-49e6-84c4-9b408156ee55")
        pump_fun_program = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
        
        subscribe_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [pump_fun_program]},
                {"commitment": "processed"}
            ]
        }

        # [FIX] A Helius derruba a conexão periodicamente (plano com limite de duração;
        # "1011 keepalive ping timeout" nos logs a cada ~3min). Antes esperávamos 5s FIXOS
        # antes de tentar reconectar — nesses 5s, qualquer token lançado na Pump.fun era
        # perdido pelo Sniper Global (sem buffer/retry). Agora a primeira tentativa é quase
        # instantânea (250ms) e só cresce exponencialmente se as reconexões continuarem
        # falhando (rede realmente fora), até um teto de 10s.
        min_delay = 0.25
        max_delay = 10.0
        reconnect_delay = min_delay

        while True:
            try:
                async with websockets.connect(wss_url, ping_interval=60, ping_timeout=120) as ws:
                    logger.info(f"Conectado ao WSS Solana: {wss_url.split('?')[0]}***")
                    await ws.send(json.dumps(subscribe_msg))
                    reconnect_delay = min_delay  # conexão OK: zera o backoff

                    async for message in ws:
                        data = json.loads(message)
                        
                        if "method" not in data or data["method"] != "logsNotification":
                            continue
                            
                        params = data.get("params", {})
                        logs = params.get("result", {}).get("value", {}).get("logs", [])
                        if not logs:
                            continue
                            
                        logs_str = str(logs)
                        signature = params.get("result", {}).get("value", {}).get("signature")
                        
                        # 1. Trata criação de novos pools (Live Feed e Global Sniping)
                        if "InitializeMint2" in logs_str or "InitializeMint" in logs_str:
                            if signature:
                                asyncio.create_task(self._process_new_pool(signature))
                        
                        # 2. Processa usuários que estão no modo Target (Alvo Específico)
                        for user_id, state in list(self.user_states.items()):
                            if state["is_active"] and state["config"]["status"] == "watching":
                                target_token = state["config"].get("target_token")
                                
                                if target_token and target_token in logs_str:
                                    if not state.get("wallet"):
                                        await self.log_to_user(user_id, "ERROR", "Nenhuma carteira Solana cadastrada.")
                                        state["is_active"] = False
                                        state["config"]["status"] = "idle"
                                        await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                                        continue
                                        
                                    await self.log_to_user(user_id, "INFO", f"⚡ Evento ALVO detectado na Pump.fun para: {target_token}!")
                                    state["config"]["status"] = "sniping"
                                    await self.broadcast_to_user(user_id, {"type": "config", **state["config"], "is_active": state["is_active"]})
                                    asyncio.create_task(self.handle_snipe_and_monitor(user_id, state, target_token))
            except Exception as e:
                logger.error(f"Erro no WSS Solana: {e}. Reconectando em {reconnect_delay:.2f}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_delay)

    async def pumpportal_migration_loop(self):
        min_delay = 0.25
        max_delay = 10.0
        reconnect_delay = min_delay
        while True:
            has_migration_users = any(state.get("config", {}).get("raydium_migration_filter") for state in self.user_states.values() if state["is_active"] and not state["config"].get("target_token"))
            if not has_migration_users:
                await asyncio.sleep(5)
                continue

            try:
                async with websockets.connect("wss://pumpportal.fun/api/data", ping_interval=30, ping_timeout=10) as ws:
                    logger.info("📡 Iniciando rastreador global de pré-migração Raydium...")
                    await ws.send(json.dumps({"method": "subscribeTokenTrade"}))
                    reconnect_delay = min_delay

                    async for message in ws:
                        has_migration_users = any(state.get("config", {}).get("raydium_migration_filter") for state in self.user_states.values() if state["is_active"] and not state["config"].get("target_token"))
                        if not has_migration_users:
                            break # Desconecta e volta a checar a cada 5s

                        data = json.loads(message)
                        v_sol = data.get("vSolInBondingCurve", 0)
                        if v_sol:
                            v_sol_normalized = float(v_sol) / 1e9
                            # Virtual SOL starts at 30. Migration happens at ~115 SOL. Pre-migration is ~113.5 to 114.9 SOL.
                            if 113.0 <= v_sol_normalized < 115.0:
                                mint = data.get("mint")
                                if mint and mint not in self.migration_triggered:
                                    self.migration_triggered.add(mint)
                                    # Dispara o snipe para usuários com raydium_migration_filter
                                    for user_id, state in list(self.user_states.items()):
                                        if state["is_active"] and not state["config"].get("target_token") and state["config"].get("raydium_migration_filter"):
                                            # Evita disparar se já atingiu max_positions
                                            max_pos = int(state["config"].get("max_positions", 1))
                                            open_pos_count = len(state.get("open_positions", {}))
                                            if open_pos_count < max_pos:
                                                await self.log_to_user(user_id, "WARN", f"🚀 [RAYDIUM MIGRATION] Token pré-migração detectado! ({v_sol_normalized:.1f} SOL Virtuais)")
                                                asyncio.create_task(self.handle_snipe_and_monitor(user_id, state, mint))
            except Exception as e:
                logger.error(f"Erro no WSS PumpPortal (Migration Mode): {e}. Reconectando em {reconnect_delay:.2f}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_delay)

    async def start(self):
        logger.info(f"🚀 Iniciando Solana Sniper na porta {WS_PORT}")
        self._load_all_user_configs()
        # Iniciar servidor WebSocket
        async with websockets.serve(self.ws_handler, "0.0.0.0", WS_PORT):
            await asyncio.gather(
                self.monitor_loop(),
                self.pumpportal_migration_loop(),
                self.raydium_migrator.migration_listener_loop()
            )

if __name__ == "__main__":
    sniper = SolanaSniper()
    asyncio.run(sniper.start())