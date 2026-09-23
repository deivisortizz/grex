#!/bin/bash
# [FIX] set -e removido do escopo global: com múltiplos bots em background e
# supervisão própria, um `set -e` global era um risco desnecessário — bastava
# qualquer comando não-backgrounded falhar (ex: o preflight abaixo) para matar
# o script inteiro, incluindo o Uvicorn que ainda nem tinha subido.
set -u

echo "🚀 Iniciando stack Grex..."

echo "⚙️ Inicializando Banco de Dados e Chave Mestra (Pre-flight)..."
# O import do server garante que o init_db() e a geração do .master.key
# ocorram de forma totalmente síncrona antes dos outros processos.
# [FIX] Retry: um volume persistente recém-montado pelo Coolify pode não
# estar 100% pronto no primeiro instante do boot do container. Antes, uma
# falha aqui (ex: FileNotFoundError ao escrever .master.key) matava o script
# inteiro via set -e e a porta 3000 nunca chegava a abrir. Agora tentamos
# algumas vezes antes de desistir, e se falhar de verdade, o erro completo
# (com traceback) fica visível nos logs do Coolify.
PREFLIGHT_OK=0
for attempt in 1 2 3; do
    if python -c "import server"; then
        PREFLIGHT_OK=1
        break
    fi
    echo "⚠️ Pre-flight falhou (tentativa $attempt/3). Tentando novamente em 3s..."
    sleep 3
done

if [ "$PREFLIGHT_OK" -ne 1 ]; then
    echo "❌ Pre-flight falhou após 3 tentativas. Verifique permissões/volume de ${DATA_DIR:-/app/data} e o traceback acima."
    exit 1
fi
echo "✅ Pre-flight concluído."

# [FIX] Isolamento de falhas: cada bot em background roda dentro de um loop
# de auto-restart próprio. Antes, se um sniper morresse (WebSocket, DB, RPC),
# ele simplesmente desaparecia para sempre até o container inteiro reiniciar
# — sem afetar o FastAPI, mas também sem nenhuma tentativa de recuperação.
# Agora cada serviço se reinicia sozinho, com backoff, e o Uvicorn nunca é
# tocado por essa lógica.
run_supervised() {
    local name="$1"
    local script="$2"
    (
        while true; do
            python "$script"
            code=$?
            echo "⚠️ [$name] encerrou (exit code $code). Reiniciando em 5s..."
            sleep 5
        done
    ) &
    echo "✅ $name iniciado sob supervisão (PID grupo: $!)"
}

# Motor de arbitragem em background (não bloqueia o processo principal)
run_supervised "arbitrage_bot.py" "arbitrage_bot.py"

# Base Meme Sniper em background
run_supervised "base_meme_sniper.py" "base_meme_sniper.py"

# Solana Sniper em background
run_supervised "solana_sniper.py" "solana_sniper.py"

# Copy Sniper (motor de copy trading, porta 8768) em background
run_supervised "copy_sniper.py" "copy_sniper.py"

# CEX Listing Sniper (anúncios de listagem Tier-2/3, porta 8769) em background
run_supervised "listing_sniper_service.py" "listing_sniper_service.py"

# [FIX] Encaminha SIGTERM para os processos filhos em background, evitando
# que um redeploy/restart do Coolify precise esperar o timeout de kill -9.
trap 'echo "🛑 Encerrando stack Grex..."; kill $(jobs -p) 2>/dev/null; exit 0' TERM INT

# Iniciar servidor web FastAPI em foreground (mantém o container ativo)
echo "✅ Servidor web (FastAPI) iniciado na porta 3000"
exec uvicorn server:app --host 0.0.0.0 --port 3000
