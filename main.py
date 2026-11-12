from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import pymysql

app = FastAPI(title="Ví Uni Full API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='567890', # Điền mật khẩu MySQL của bạn vào đây nếu có
        database='chitieu_sv',
        cursorclass=pymysql.cursors.DictCursor
    )

# --- SCHEMAS ---
class LoginReq(BaseModel):
    email: str
    password: str

class TxReq(BaseModel):
    user_id: int
    wallet_id: int
    category_id: int
    amount: float
    type: str
    note: str
    priority_level: Optional[str] = "Essential"

# --- APIs ---
@app.post("/api/login")
def login(data: LoginReq):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, email, avatar FROM users WHERE email = %s AND password = %s", (data.email, data.password))
            user = cur.fetchone()
            if user:
                return {"success": True, "user": user}
            raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không chính xác!")
    finally:
        conn.close()

@app.get("/api/dashboard/{user_id}")
def get_dashboard(user_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Wallets
            cur.execute("SELECT * FROM wallets WHERE user_id = %s", (user_id,))
            wallets = cur.fetchall()
            
            # Recent transactions
            cur.execute("""
                SELECT t.*, c.name as category_name, c.icon as category_icon 
                FROM transactions t 
                LEFT JOIN categories c ON t.category_id = c.id 
                WHERE t.user_id = %s ORDER BY t.transaction_date DESC LIMIT 10
            """, (user_id,))
            transactions = cur.fetchall()
            
            # Savings
            cur.execute("SELECT * FROM savings_goals WHERE user_id = %s", (user_id,))
            savings = cur.fetchall()

            # Groups
            cur.execute("SELECT * FROM groups WHERE created_by = %s", (user_id,))
            groups = cur.fetchall()
            
            return {
                "success": True,
                "wallets": wallets,
                "transactions": transactions,
                "savings": savings,
                "groups": groups
            }
    finally:
        conn.close()

@app.get("/api/categories/{user_id}")
def get_categories(user_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM categories WHERE user_id = %s", (user_id,))
            return {"success": True, "data": cur.fetchall()}
    finally:
        conn.close()

@app.post("/api/transactions")
def create_transaction(tx: TxReq):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Thêm giao dịch
            cur.execute(
                "INSERT INTO transactions (user_id, wallet_id, category_id, amount, type, note, priority_level) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (tx.user_id, tx.wallet_id, tx.category_id, tx.amount, tx.type, tx.note, tx.priority_level)
            )
            # Cập nhật số dư ví
            op = '-' if tx.type == 'expense' else '+'
            cur.execute(f"UPDATE wallets SET balance = balance {op} %s WHERE id = %s", (tx.amount, tx.wallet_id))
            conn.commit()
            return {"success": True, "message": "Thêm giao dịch thành công!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/groups/{group_id}")
def get_group_details(group_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM groups WHERE id = %s", (group_id,))
            group = cur.fetchone()
            cur.execute("SELECT * FROM group_members WHERE group_id = %s", (group_id,))
            members = cur.fetchall()
            return {"success": True, "group": group, "members": members}
    finally:
        conn.close()