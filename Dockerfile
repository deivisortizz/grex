# ==========================================
# STAGE 1: Build do Frontend (React/Vite)
# ==========================================
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend

# Copia os arquivos de dependência do frontend
COPY arb-desk/package*.json ./
RUN npm install

# Copia o código do frontend e executa o build
COPY arb-desk/ ./
RUN npm run build

# ==========================================
# STAGE 2: Build do Backend (Python/FastAPI)
# ==========================================
FROM python:3.10-slim

# Instalar dependências do sistema e utilitários
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia dependências do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todos os scripts Python e a shell de inicialização
COPY . .

# Copia a pasta 'dist' gerada no Stage 1 para a raiz do backend (/app/dist)
# É onde o FastAPI (server.py) espera encontrar o React compilado
COPY --from=frontend-builder /app/frontend/dist ./dist

# Garante permissões na pasta de banco de dados/chaves
RUN mkdir -p /app/data && chmod -R 777 /app/data
RUN chmod +x start.sh

# Exposição das portas (3000 = Frontend/FastAPI, 8765-8769 = WebSockets dos Snipers)
EXPOSE 3000 8765 8766 8767 8768 8769

# Executa o script central que sobe o FastAPI e os processos em background
CMD ["bash", "start.sh"]
