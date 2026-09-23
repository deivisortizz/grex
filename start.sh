#!/bin/bash
set -e

echo "🚀 Iniciando stack Grex..."

# Motor de arbitragem em background (não bloqueia o processo principal)
python arbitrage_bot.py &
ARB_PID=$!
echo "✅ arbitrage_bot.py iniciado (PID: $ARB_PID)"

# Base Meme Sniper em background
python base_meme_sniper.py &
MEME_PID=$!
echo "✅ base_meme_sniper.py iniciado (PID: $MEME_PID)"

# Solana Sniper em background
python solana_sniper.py &
SOL_PID=$!
echo "✅ solana_sniper.py iniciado (PID: $SOL_PID)"

# Copy Sniper (motor de copy trading, porta 8768) em background
# [FIX] Este processo nunca era iniciado — o módulo existia no código mas
# jamais rodava no container, por isso o WebSocket da porta 8768 nunca
# respondia (não havia sequer um processo escutando nela).
python copy_sniper.py &
COPY_PID=$!
echo "✅ copy_sniper.py iniciado (PID: $COPY_PID)"

# CEX Listing Sniper (anúncios de listagem Tier-2/3, porta 8769) em background
python listing_sniper_service.py &
LISTING_PID=$!
echo "✅ listing_sniper_service.py iniciado (PID: $LISTING_PID)"

# Iniciar servidor web FastAPI em foreground (mantém o container ativoo)
echo "✅ Servidor web (FastAPI) iniciado na porta 3000"
exec uvicorn server:app --host 0.0.0.0 --port 3000