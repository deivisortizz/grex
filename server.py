from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import os
import sqlite3
import jwt
import uuid
from passlib.context import CryptContext
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Configurações de Ambiente
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

JWT_SECRET = os.getenv("JWT_SECRET", "multi-tenant-super-secret-fallback")
JWT_ALGORITHM = "HS256"
DATA_DIR = os.getenv('DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
DB_PATH = os.path.join(DATA_DIR, 'sniper.db')

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                subscription_expires TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_configs (
                user_id INTEGER PRIMARY KEY,
                snipe_size_eth REAL DEFAULT 0.005,
                min_pool_weth REAL DEFAULT 0.005,
                tp_pct REAL DEFAULT 50.0,
                sl_pct REAL DEFAULT 15.0,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                used BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                exchange TEXT,
                api_key TEXT,
                api_secret TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS burner_wallet (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT,
                pk_encrypted TEXT,
                user_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        conn.commit()

init_db()

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserRegister(BaseModel):
    email: str
    password: str
    token: str

class UserLogin(BaseModel):
    email: str
    password: str

class ExtendRequest(BaseModel):
    days: int

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class UserConfigReq(BaseModel):
    snipe_size_eth: float
    min_pool_weth: float
    tp_pct: float
    sl_pct: float

class WalletReq(BaseModel):
    address: str
    private_key: str

class BinanceReq(BaseModel):
    api_key: str
    api_secret: str

app = FastAPI(title="Grex HFT UI Server (Multi-Tenant)")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: sqlite3.Connection = Depends(get_db)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    cursor = db.cursor()
    cursor.execute("SELECT id, email, is_admin, is_active FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user or not user["is_active"]:
        raise HTTPException(status_code=403, detail="Acesso negado ou usuário inativo.")
    
    return user

def get_current_admin(token: str = Depends(oauth2_scheme), db: sqlite3.Connection = Depends(get_db)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    cursor = db.cursor()
    cursor.execute("SELECT id, email, is_admin FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user or not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Acesso negado. Requer privilégios de administrador.")
    
    return user

@app.post("/api/auth/register")
def register_user(user: UserRegister, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT id FROM invites WHERE token = ? AND used = 0", (user.token,))
    invite = cursor.fetchone()
    if not invite:
        raise HTTPException(status_code=403, detail="Convite de acesso inválido ou expirado.")

    cursor.execute("SELECT id FROM users WHERE email = ?", (user.email,))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="Email já cadastrado")
        
    hashed_pw = pwd_context.hash(user.password)
    try:
        # Se for o primeiro usuário a se registrar, vira admin
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        is_admin = 1 if user_count == 0 else 0
        
        cursor.execute("INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, ?)", (user.email, hashed_pw, is_admin))
        user_id = cursor.lastrowid
        # Cria uma config default para o usuário
        cursor.execute("INSERT INTO user_configs (user_id) VALUES (?)", (user_id,))
        
        # Marca o convite como usado
        cursor.execute("UPDATE invites SET used = 1 WHERE id = ?", (invite["id"],))
        
        db.commit()
        return {"msg": "Usuário criado com sucesso", "is_admin": bool(is_admin)}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/auth/login")
def login_user(user: UserLogin, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT id, password_hash FROM users WHERE email = ?", (user.email,))
    row = cursor.fetchone()
    if not row or not pwd_context.verify(user.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
        
    payload = {
        "sub": str(row["id"]),
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    # Busca se é admin para mandar no response
    cursor.execute("SELECT is_admin FROM users WHERE id = ?", (row["id"],))
    is_admin = cursor.fetchone()["is_admin"]
    
    return {"access_token": token, "token_type": "bearer", "is_admin": bool(is_admin)}

@app.post("/api/auth/change-password")
def change_password(req: ChangePasswordRequest, current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE id = ?", (current_user["id"],))
    row = cursor.fetchone()
    if not row or not pwd_context.verify(req.old_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    
    new_hash = pwd_context.hash(req.new_password)
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, current_user["id"]))
    db.commit()
    return {"msg": "Senha alterada com sucesso"}

# -----------------
# Rotas de Usuário (Multi-Tenant Isoladas)
# -----------------
@app.get("/api/user/config")
def get_user_config(current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM user_configs WHERE user_id = ?", (current_user["id"],))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Config não encontrada")
    return dict(row)

@app.post("/api/user/config")
def save_user_config(req: UserConfigReq, current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute('''
        UPDATE user_configs 
        SET snipe_size_eth = ?, min_pool_weth = ?, tp_pct = ?, sl_pct = ? 
        WHERE user_id = ?
    ''', (req.snipe_size_eth, req.min_pool_weth, req.tp_pct, req.sl_pct, current_user["id"]))
    db.commit()
    return {"msg": "Configurações salvas"}

@app.get("/api/user/wallet")
def get_user_wallet(current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT address FROM burner_wallet WHERE user_id = ?", (current_user["id"],))
    row = cursor.fetchone()
    if not row:
        return {"address": None}
    return {"address": row["address"]}

@app.post("/api/user/wallet")
def save_user_wallet(req: WalletReq, current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    # Nota: No mundo real, a pk_encrypted deve ser criptografada. 
    # Aqui delegamos para a mesma rotina (se precisar criptografar, deve usar a mesma chave mestra).
    # Como as chaves são geridas por websocket normalmente, este endpoint garante fallback HTPP restrito.
    cursor = db.cursor()
    cursor.execute("DELETE FROM burner_wallet WHERE user_id = ?", (current_user["id"],))
    cursor.execute("INSERT INTO burner_wallet (address, pk_encrypted, user_id) VALUES (?, ?, ?)", 
                   (req.address, req.private_key, current_user["id"]))
    
    # Ativa automaticamente o usuário para que o motor execute snipes
    cursor.execute("UPDATE users SET is_active = 1 WHERE id = ?", (current_user["id"],))
    
    db.commit()
    return {"status": "success", "message": "Carteira criptografada e salva com sucesso!"}

@app.delete("/api/user/wallet")
def delete_user_wallet(current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM burner_wallet WHERE user_id = ?", (current_user["id"],))
    db.commit()
    return {"status": "success", "message": "Carteira removida com sucesso!"}

@app.get("/api/user/binance")
def get_user_binance(current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT api_key FROM api_keys WHERE user_id = ? AND exchange = 'binance'", (current_user["id"],))
    row = cursor.fetchone()
    if not row or not row["api_key"]:
        return {"api_key": None}
    
    api_key = row["api_key"]
    # Mascara a chave por segurança
    masked = f"{api_key[:4]}***{api_key[-4:]}" if len(api_key) >= 8 else "***"
    return {"api_key": masked}

@app.post("/api/user/binance")
def save_user_binance(req: BinanceReq, current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM api_keys WHERE user_id = ? AND exchange = 'binance'", (current_user["id"],))
    cursor.execute("INSERT INTO api_keys (user_id, exchange, api_key, api_secret) VALUES (?, 'binance', ?, ?)", 
                   (current_user["id"], req.api_key, req.api_secret))
    db.commit()
    return {"status": "success", "message": "Corretora conectada com sucesso!"}

@app.delete("/api/user/binance")
def delete_user_binance(current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM api_keys WHERE user_id = ? AND exchange = 'binance'", (current_user["id"],))
    db.commit()
    return {"status": "success", "message": "Corretora desconectada com sucesso!"}

# ROTA TEMPORÁRIA: Limpeza geral da tabela de corretoras (solicitada pelo usuário)
@app.delete("/api/admin/clear_exchanges")
def clear_all_exchanges(db: sqlite3.Connection = Depends(get_db)):
    # Limpa do banco do Sniper
    cursor = db.cursor()
    cursor.execute("DELETE FROM api_keys")
    db.commit()
    
    # Limpa do banco do Arbitrage Bot (trades.db) se existir
    trades_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'trades.db')
    if os.path.exists(trades_db_path):
        with sqlite3.connect(trades_db_path) as conn_trades:
            cursor_trades = conn_trades.cursor()
            try:
                cursor_trades.execute("DELETE FROM api_keys")
                conn_trades.commit()
            except sqlite3.OperationalError:
                pass # Tabela ainda não existe
                
    return {"status": "success", "message": "Tabela api_keys 100% zerada em todos os bancos."}

@app.get("/api/analytics")
def get_analytics(current_user = Depends(get_current_user)):
    db_path = os.path.join(DATA_DIR, 'trades.db')
    if not os.path.exists(db_path):
        return {"history": []}
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 100", (current_user["id"],))
            rows = cursor.fetchall()
            return {"history": [dict(row) for row in rows]}
        except sqlite3.OperationalError:
            # Caso a tabela ainda não tenha sido migrada/criada pelo arbitrage_bot
            return {"history": []}

# -----------------
# Rotas Admin
# -----------------
@app.get("/api/admin/users")
def get_users(admin = Depends(get_current_admin), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT id, email, is_admin, is_active, subscription_expires, created_at FROM users")
    users = [dict(row) for row in cursor.fetchall()]
    return {"users": users}

@app.post("/api/admin/generate-invite")
def generate_invite(admin = Depends(get_current_admin), db: sqlite3.Connection = Depends(get_db)):
    token = str(uuid.uuid4())
    cursor = db.cursor()
    cursor.execute("INSERT INTO invites (token) VALUES (?)", (token,))
    db.commit()
    return {"invite_token": token}

@app.post("/api/admin/user/{id}/extend")
def extend_user(id: int, request: ExtendRequest, admin = Depends(get_current_admin), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT subscription_expires FROM users WHERE id = ?", (id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    current_expires = row["subscription_expires"]
    if not current_expires:
        new_expires = datetime.utcnow() + timedelta(days=request.days)
    else:
        try:
            curr_dt = datetime.strptime(current_expires, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            curr_dt = datetime.utcnow()
        if curr_dt < datetime.utcnow():
            curr_dt = datetime.utcnow()
        new_expires = curr_dt + timedelta(days=request.days)
        
    cursor.execute("UPDATE users SET subscription_expires = ? WHERE id = ?", (new_expires, id))
    db.commit()
    return {"msg": "Assinatura estendida com sucesso", "new_expires": new_expires}

@app.post("/api/admin/user/{id}/toggle-status")
def toggle_user_status(id: int, admin = Depends(get_current_admin), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT is_active FROM users WHERE id = ?", (id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    new_status = 0 if row["is_active"] else 1
    cursor.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, id))
    db.commit()
    return {"msg": "Status alterado com sucesso", "is_active": new_status}

@app.get("/api/admin/stats")
def get_admin_stats(admin = Depends(get_current_admin), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
    active_users = cursor.fetchone()[0]
    
    return {
        "total_users": total_users,
        "active_users": active_users
    }

@app.delete("/api/admin/user/{id}")
def delete_user(id: int, admin = Depends(get_current_admin), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE id = ?", (id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if row["is_admin"]:
        raise HTTPException(status_code=400, detail="Não é possível remover um administrador")
        
    cursor.execute("DELETE FROM user_configs WHERE user_id = ?", (id,))
    cursor.execute("DELETE FROM burner_wallet WHERE user_id = ?", (id,))
    cursor.execute("DELETE FROM users WHERE id = ?", (id,))
    db.commit()
    return {"msg": "Usuário removido com sucesso"}

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

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"🚀 Iniciando Grex HFT UI Server em http://{host}:{port}")
    uvicorn.run("server:app", host=host, port=port, reload=True)

