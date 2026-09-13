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

# Iniciar servidor web FastAPI em foreground (mantém o container ativo)
echo "✅ Servidor web (FastAPI) iniciado na porta 8000"
exec uvicorn server:app --host 0.0.0.0 --port 8000