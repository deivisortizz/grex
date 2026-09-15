## ---------- Multi‑Stage Build ----------
# ── 1️⃣ Frontend Builder (Node) ────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend

# Instalar dependências do React (npm ci usa lockfile, fallback to npm install)
COPY arb-desk/package*.json ./
RUN npm ci --silent || npm install --silent

# Copiar todo o código fonte do front-end
COPY arb-desk/ ./

# Build da aplicação React (Vite) → gera /frontend/dist
RUN npm run build

# ── 2️⃣ Backend Runtime (Python) ────────────────────────────────────────
FROM python:3.11-slim AS backend-runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Instalar dependências de compilação do Python e ferramentas essenciais
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar pacotes Python (incluindo solana e solders)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar todo o código do backend (inclui scripts, .env, start.sh, etc.)
COPY . .

# Incorporar assets estáticos gerados pelo frontend
COPY --from=frontend-builder /frontend/dist ./dist

# Garantir que o script de inicialização seja executável
RUN chmod +x start.sh

# Expor as portas usadas pelos WebSockets e HTTP (8767 para Solana)
EXPOSE 8765 8766 8767 3000

# Entrypoint único para gerenciar a stack completa via start.sh
CMD ["/bin/bash", "start.sh"]