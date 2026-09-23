from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import Optional, List
import os
import sqlite3
import jwt
import uuid
import logging
from passlib.context import CryptContext
from datetime import datetime, timedelta
from dotenv import load_dotenv
from cryptography.fernet import Fernet

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('GrexServer')

# Configurações de Ambiente
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

JWT_SECRET = os.getenv("JWT_SECRET", "multi-tenant-super-secret-fallback")
JWT_ALGORITHM = "HS256"
DATA_DIR = os.getenv('DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
DB_PATH = os.path.join(DATA_DIR, 'sniper.db')

# Setup Fernet Crypto
key_path = os.path.join(DATA_DIR, '.master.key')
if not os.path.exists(key_path):
    master_key = Fernet.generate_key()
    with open(key_path, 'wb') as f:
        f.write(master_key)
else:
    with open(key_path, 'rb') as f:
        master_key = f.read()
cipher = Fernet(master_key)

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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS solana_burner_wallet (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT,
                pk_encrypted TEXT,
                user_id INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS solana_sniper_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                target_token TEXT,
                slippage REAL,
                jito_tip REAL,
                tp_pct REAL DEFAULT 100.0,
                sl_pct REAL DEFAULT 20.0
            )
        ''')
        # Migrações seguras (adicionar colunas se não existirem)
        try:
            cursor.execute("ALTER TABLE solana_sniper_configs ADD COLUMN tp_pct REAL DEFAULT 100.0")
        except sqlite3.OperationalError:
            pass # Coluna já existe

        try:
            cursor.execute("ALTER TABLE solana_sniper_configs ADD COLUMN sl_pct REAL DEFAULT 20.0")
        except sqlite3.OperationalError:
            pass # Coluna já existe

        try:
            cursor.execute("ALTER TABLE solana_sniper_configs ADD COLUMN is_active BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass # Coluna já existe

        try:
            cursor.execute("ALTER TABLE solana_sniper_configs ADD COLUMN max_positions INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass # Coluna já existe

        try:
            cursor.execute("ALTER TABLE solana_sniper_configs ADD COLUMN hardcore_mode BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass # Coluna já existe
            
        try:
            cursor.execute("ALTER TABLE solana_sniper_configs ADD COLUMN anti_delay_filter BOOLEAN DEFAULT 1")
        except sqlite3.OperationalError:
            pass
            
        try:
            cursor.execute("ALTER TABLE solana_sniper_configs ADD COLUMN trade_amount REAL DEFAULT 0.05")
        except sqlite3.OperationalError:
            pass

            
        try:
            cursor.execute("ALTER TABLE solana_sniper_configs ADD COLUMN socials_filter BOOLEAN DEFAULT 1")
        except sqlite3.OperationalError:
            pass
            
        try:
            cursor.execute("ALTER TABLE solana_sniper_configs ADD COLUMN max_bonding_curve REAL DEFAULT 20.0")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE solana_sniper_configs ADD COLUMN raydium_migration_filter BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE solana_sniper_configs ADD COLUMN raydium_migrator_active BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE user_configs ADD COLUMN is_active BOOLEAN DEFAULT 1")
        except sqlite3.OperationalError:
            pass # Coluna já existe

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tracked_wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                wallet_address TEXT,
                label TEXT,
                is_active BOOLEAN DEFAULT 1
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS solana_sniper_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                token_mint TEXT,
                sol_spent REAL,
                sol_received REAL,
                jito_tip_buy REAL,
                jito_tip_sell REAL,
                net_pnl_sol REAL,
                net_pnl_usd REAL,
                is_win BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS copy_sniper_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                token_mint TEXT,
                sol_spent REAL,
                sol_received REAL,
                jito_tip_buy REAL,
                jito_tip_sell REAL,
                net_pnl_sol REAL,
                net_pnl_usd REAL,
                is_win BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # [FIX] Faltava esta tabela: _is_blacklisted/_add_to_blacklist (solana_core.py)
        # já fazem SELECT/INSERT nela, mas como nunca foi criada, toda chamada falhava
        # silenciosamente (capturada por um except genérico) e a blacklist automática
        # de criadores nunca bloqueava ninguém, mesmo após um Stop-Loss catastrófico.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS creator_blacklist (
                creator_wallet TEXT PRIMARY KEY,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()

    # Inicializar trades.db (Bot de Arbitragem CCXT) também, caso server.py inicie antes
    trades_db_path = os.path.join(DATA_DIR, 'trades.db')
    with sqlite3.connect(trades_db_path, check_same_thread=False) as conn_trades:
        cursor_trades = conn_trades.cursor()
        cursor_trades.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                timestamp TEXT,
                exchange_buy TEXT,
                exchange_sell TEXT,
                spread_bruto REAL,
                lucro_liquido REAL
            )
        ''')
        cursor_trades.execute('''
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                exchange TEXT,
                key_encrypted TEXT,
                secret_encrypted TEXT,
                password_encrypted TEXT
            )
        ''')
        conn_trades.commit()

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

class SolanaWalletReq(BaseModel):
    private_key: str

class SolanaConfigReq(BaseModel):
    target_token: Optional[str] = None
    slippage: float = Field(default=15.0, ge=0.0, le=100.0)
    jito_tip: float = Field(default=0.001, ge=0.0)
    tp_pct: float = Field(default=100.0, ge=0.0)
    sl_pct: float = Field(default=20.0, ge=0.0)
    trade_amount: float = Field(default=0.05, ge=0.0)
    max_positions: int = Field(default=1, ge=1)
    hardcore_mode: bool = Field(default=False)
    anti_delay_filter: bool = Field(default=True)
    socials_filter: bool = Field(default=True)
    max_bonding_curve: float = Field(default=20.0, ge=0.0)
    raydium_migration_filter: bool = Field(default=False)
    raydium_migrator_active: bool = Field(default=False)

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
    cursor = db.cursor()
    cursor.execute("DELETE FROM burner_wallet WHERE user_id = ?", (current_user["id"],))
    # Encrypt the base private key with Fernet
    encrypted_pk = cipher.encrypt(req.private_key.encode()).decode() if req.private_key else ""
    cursor.execute("INSERT INTO burner_wallet (address, pk_encrypted, user_id) VALUES (?, ?, ?)", 
                   (req.address, encrypted_pk, current_user["id"]))
    
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

@app.get("/api/user/solana_wallet")
def get_user_solana_wallet(current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT address FROM solana_burner_wallet WHERE user_id = ?", (current_user["id"],))
    row = cursor.fetchone()
    if not row:
        return {"address": None}
    return {"address": row["address"]}

@app.delete("/api/user/solana_wallet")
def delete_user_solana_wallet(current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM solana_burner_wallet WHERE user_id = ?", (current_user["id"],))
    db.commit()
    return {"status": "success", "message": "Carteira Solana removida com sucesso!"}

@app.post("/api/user/solana_wallet")
def save_user_solana_wallet(req: SolanaWalletReq, current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    if not req.private_key or len(req.private_key) < 60:
        raise HTTPException(status_code=400, detail="Chave privada Solana inválida. Use o formato Base58.")
    
    try:
        from solders.keypair import Keypair
        kp = Keypair.from_base58_string(req.private_key)
        derived_address = str(kp.pubkey())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao decodificar chave Solana: {e}")

    encrypted_pk = cipher.encrypt(req.private_key.encode()).decode()

    cursor = db.cursor()
    cursor.execute("DELETE FROM solana_burner_wallet WHERE user_id = ?", (current_user["id"],))
    cursor.execute("INSERT INTO solana_burner_wallet (address, pk_encrypted, user_id) VALUES (?, ?, ?)", 
                   (derived_address, encrypted_pk, current_user["id"]))
    
    # Ativa automaticamente o usuário
    cursor.execute("UPDATE users SET is_active = 1 WHERE id = ?", (current_user["id"],))
    db.commit()
    return {"status": "success", "message": f"Carteira Solana ({derived_address[:6]}...{derived_address[-4:]}) salva com sucesso!"}

@app.get("/api/user/solana_config")
def get_user_solana_config(current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    fallback_config = {
        "target_token": "", 
        "slippage": 15.0, 
        "jito_tip": 0.001, 
        "tp_pct": 100.0, 
        "sl_pct": 20.0, 
        "trade_amount": 0.005, 
        "max_positions": 1, 
        "hardcore_mode": False,
        "anti_delay_filter": True,
        "socials_filter": True,
        "max_bonding_curve": 20.0,
        "raydium_migration_filter": False,
        "raydium_migrator_active": False
    }

    try:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM solana_sniper_configs WHERE user_id = ?", (current_user["id"],))
        row = cursor.fetchone()
        
        if not row:
            return fallback_config
            
        row_keys = row.keys()
        return {
            "target_token": row["target_token"] if "target_token" in row_keys and row["target_token"] is not None else fallback_config["target_token"], 
            "slippage": row["slippage"] if "slippage" in row_keys and row["slippage"] is not None else fallback_config["slippage"], 
            "jito_tip": row["jito_tip"] if "jito_tip" in row_keys and row["jito_tip"] is not None else fallback_config["jito_tip"],
            "tp_pct": row["tp_pct"] if "tp_pct" in row_keys and row["tp_pct"] is not None else fallback_config["tp_pct"],
            "sl_pct": row["sl_pct"] if "sl_pct" in row_keys and row["sl_pct"] is not None else fallback_config["sl_pct"],
            "trade_amount": row["trade_amount"] if "trade_amount" in row_keys and row["trade_amount"] is not None else fallback_config["trade_amount"],
            "max_positions": row["max_positions"] if "max_positions" in row_keys and row["max_positions"] is not None else fallback_config["max_positions"],
            "hardcore_mode": bool(row["hardcore_mode"]) if "hardcore_mode" in row_keys and row["hardcore_mode"] is not None else fallback_config["hardcore_mode"],
            "anti_delay_filter": bool(row["anti_delay_filter"]) if "anti_delay_filter" in row_keys and row["anti_delay_filter"] is not None else fallback_config["anti_delay_filter"],
            "socials_filter": bool(row["socials_filter"]) if "socials_filter" in row_keys and row["socials_filter"] is not None else fallback_config["socials_filter"],
            "max_bonding_curve": row["max_bonding_curve"] if "max_bonding_curve" in row_keys and row["max_bonding_curve"] is not None else fallback_config["max_bonding_curve"],
            "raydium_migration_filter": bool(row["raydium_migration_filter"]) if "raydium_migration_filter" in row_keys and row["raydium_migration_filter"] is not None else fallback_config["raydium_migration_filter"],
            "raydium_migrator_active": bool(row["raydium_migrator_active"]) if "raydium_migrator_active" in row_keys and row["raydium_migrator_active"] is not None else fallback_config["raydium_migrator_active"]
        }
    except Exception as e:
        import traceback
        logger.error(f"Error fetching solana config for user {current_user['id']}: {str(e)}")
        traceback.print_exc()
        return fallback_config


@app.post("/api/user/solana_config")
def save_user_solana_config(req: SolanaConfigReq, current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    target = req.target_token or ""
    if target and len(target) < 32:
        raise HTTPException(status_code=400, detail="Token Mint inválido. A chave deve estar vazia para o Modo Global ou ter ao menos 32 caracteres.")
        
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO solana_sniper_configs (user_id, target_token, slippage, jito_tip, tp_pct, sl_pct, max_positions, hardcore_mode, trade_amount, anti_delay_filter, socials_filter, max_bonding_curve, raydium_migration_filter, raydium_migrator_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            target_token = excluded.target_token,
            slippage = excluded.slippage,
            jito_tip = excluded.jito_tip,
            tp_pct = excluded.tp_pct,
            sl_pct = excluded.sl_pct,
            max_positions = excluded.max_positions,
            hardcore_mode = excluded.hardcore_mode,
            trade_amount = excluded.trade_amount,
            anti_delay_filter = excluded.anti_delay_filter,
            socials_filter = excluded.socials_filter,
            max_bonding_curve = excluded.max_bonding_curve,
            raydium_migration_filter = excluded.raydium_migration_filter,
            raydium_migrator_active = excluded.raydium_migrator_active
    """, (current_user["id"], target, req.slippage, req.jito_tip, req.tp_pct, req.sl_pct, req.max_positions, 1 if req.hardcore_mode else 0, req.trade_amount, 1 if req.anti_delay_filter else 0, 1 if req.socials_filter else 0, req.max_bonding_curve, 1 if req.raydium_migration_filter else 0, 1 if req.raydium_migrator_active else 0))
    db.commit()
    return {"status": "success", "message": "Configuração do Token salva com sucesso!"}

@app.delete("/api/user/solana_config")
def delete_user_solana_config(current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM solana_sniper_configs WHERE user_id = ?", (current_user["id"],))
    db.commit()
    return {"status": "success", "message": "Configuração do Token apagada com sucesso!"}


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

@app.post("/api/admin/reset-system")
def reset_system(current_user = Depends(get_current_admin)):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Arquivos a serem apagados
        files_to_remove = [
            os.path.join(base_dir, "data", "trades.db"),
            os.path.join(base_dir, "data", ".master.key"),
            os.path.join(base_dir, "data", "base_meme_sniper.db"),
            os.path.join(base_dir, "data", "solana_sniper.db"),
            os.path.join(base_dir, "sniper.db")
        ]
        
        removed = []
        for file_path in files_to_remove:
            if os.path.exists(file_path):
                # Importante: Como o SQLite pode estar com o arquivo travado, tentamos remover
                try:
                    os.remove(file_path)
                    removed.append(file_path)
                except Exception as e:
                    print(f"Erro ao remover {file_path}: {e}")
                    
        return {"status": "success", "message": f"Sistema resetado. {len(removed)} arquivos apagados. Por favor, reinicie os containers."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trade-history")
def get_trade_history(current_user = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    try:
        cursor.execute('''
            SELECT token_mint, sol_spent, sol_received, jito_tip_buy, jito_tip_sell, net_pnl_sol, net_pnl_usd, is_win, created_at
            FROM solana_sniper_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 100
        ''', (current_user["id"],))
        rows = cursor.fetchall()
        return {"history": [dict(row) for row in rows]}
    except sqlite3.OperationalError:
        return {"history": []}

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
# ----------------------------------------------------------------------------
# TRACKED WALLETS (COPY TRADING) ENDPOINTS
# ----------------------------------------------------------------------------

class TrackedWalletPayload(BaseModel):
    wallet_address: str
    label: str = ""

@app.get("/api/solana/tracked-wallets")
async def get_tracked_wallets(user: dict = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    user_id = user["id"]
    cursor = db.cursor()
    cursor.execute("SELECT id, wallet_address, label, is_active FROM tracked_wallets WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    wallets = [{"id": r[0], "wallet_address": r[1], "label": r[2], "is_active": bool(r[3])} for r in rows]
    return {"status": "success", "wallets": wallets}

@app.post("/api/solana/tracked-wallets")
async def add_tracked_wallet(payload: TrackedWalletPayload, user: dict = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    user_id = user["id"]
    cursor = db.cursor()
    # Evitar duplicatas simples
    cursor.execute("SELECT id FROM tracked_wallets WHERE user_id = ? AND wallet_address = ?", (user_id, payload.wallet_address))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="Carteira já está sendo rastreada.")

    cursor.execute("INSERT INTO tracked_wallets (user_id, wallet_address, label, is_active) VALUES (?, ?, ?, 1)",
                   (user_id, payload.wallet_address, payload.label))
    db.commit()
    return {"status": "success", "message": "Carteira adicionada ao rastreamento."}

@app.delete("/api/solana/tracked-wallets/{wallet_id}")
async def remove_tracked_wallet(wallet_id: int, user: dict = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    user_id = user["id"]
    cursor = db.cursor()
    cursor.execute("DELETE FROM tracked_wallets WHERE id = ? AND user_id = ?", (wallet_id, user_id))
    db.commit()
    return {"status": "success"}

@app.put("/api/solana/tracked-wallets/{wallet_id}/toggle")
async def toggle_tracked_wallet(wallet_id: int, user: dict = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    user_id = user["id"]
    cursor = db.cursor()
    cursor.execute("UPDATE tracked_wallets SET is_active = NOT is_active WHERE id = ? AND user_id = ?", (wallet_id, user_id))
    db.commit()
    return {"status": "success"}

class WalletHunterRequest(BaseModel):
    mint: str

@app.post("/api/solana/hunt-wallets")
@app.post("/api/solana/hunter")
async def hunt_wallets_endpoint(payload: WalletHunterRequest, user: dict = Depends(get_current_user)):
    user_id = user["id"]
    mint = payload.mint.strip()
    if not mint:
        raise HTTPException(status_code=400, detail="Mint address do token é obrigatório.")
    
    try:
        from wallet_hunter import WalletHunter
        rpc_url = os.getenv("SOLANA_RPC_URL", "https://mainnet.helius-rpc.com/?api-key=eff46054-caa6-4e08-8731-e9abad96e5d2")
        hunter = WalletHunter(rpc_url)
        res = await hunter.run(mint, user_id)
        if not res or res.get("status") == "error":
            raise HTTPException(status_code=400, detail=res.get("message", "Nenhuma transação encontrada para este token."))
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao executar Wallet Hunter: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno no Wallet Hunter: {str(e)}")


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