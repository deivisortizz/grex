#!/bin/bash
set -e

echo "🚀 Iniciando stack Grex..."

# Motor de arbitragem em background (não bloqueia o processo principal)
python arbitrage_bot.py &
ARB_PID=$!
echo "✅ arbitrage_bot.py iniciado (PID: $ARB_PID)"

# Base Meme Sniper em foreground (mantém o container ativo)
# Se falhar, o container reporta o erro e o Coolify pode reagendar
python base_meme_sniper.py