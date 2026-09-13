from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

app = FastAPI(title="Grex HFT UI Server")

# Monta o diretório de assets se ele existir (gerado pelo Vite)
assets_path = "dist/assets"
if os.path.exists(assets_path):
    app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    # Primeiro verifica se está tentando acessar um arquivo real na pasta dist (ex: favicon.ico, logo.png)
    file_path = os.path.join("dist", full_path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # Fallback de SPA para o React Router (retorna index.html SEM CACHE)
    index_path = "dist/index.html"
    if os.path.exists(index_path):
        response = FileResponse(index_path)
        # Força o navegador a sempre buscar o index.html atualizado
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    
    # Retorno de erro caso o build ainda não exista (debug)
    return {"error": "Frontend build (dist) not found. Check if npm run build executed successfully."}

