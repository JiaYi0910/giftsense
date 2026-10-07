import sqlite3
import json
import os
import time
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "caregift.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0) # 💡 增加逾時等待時間 (30秒)，避免瞬間搶鎖失敗
    conn.row_factory = sqlite3.Row
    try:
        # 💡 安全設定 WAL 模式，若當前被鎖定則自動略過，不讓程式崩潰
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError:
        pass
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. recipients 表格（💡 加上 user_account 實現多用戶隔離）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recipients (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        condition TEXT NOT NULL,
        phone TEXT,
        birthday TEXT,
        line_user_id TEXT,
        user_account TEXT DEFAULT 'test',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. orders 表格
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        items_json TEXT NOT NULL,
        total TEXT NOT NULL,
        recipient TEXT NOT NULL,
        pharmacy TEXT DEFAULT '連鎖藥局',
        status TEXT NOT NULL,
        user_account TEXT DEFAULT 'test',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 3. points_ledger 表格
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS points_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account TEXT NOT NULL,
        amount INTEGER NOT NULL,
        title TEXT NOT NULL,
        date_str TEXT NOT NULL,
        expire_str TEXT NOT NULL,
        type TEXT NOT NULL,
        user_account TEXT DEFAULT 'test',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 4. pharmacy_cache 表格
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pharmacy_cache (
        id TEXT PRIMARY KEY,
        pharmacy TEXT NOT NULL,
        product_name TEXT NOT NULL,
        price INTEGER NOT NULL,
        spec TEXT,
        url TEXT,
        image_url TEXT,
        in_stock INTEGER DEFAULT 1,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 5. clinical_knowledge 表格
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clinical_knowledge (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        authority TEXT NOT NULL,
        category TEXT NOT NULL,
        ingredient TEXT NOT NULL,
        evidence_level TEXT NOT NULL,
        recommended_dose TEXT NOT NULL,
        mechanism TEXT NOT NULL,
        contraindications TEXT NOT NULL,
        target_symptoms_json TEXT NOT NULL,
        citation TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 6. system_config 表格
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_config (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 7. users 表格
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        account TEXT UNIQUE,
        password_hash TEXT,
        name TEXT,
        role TEXT DEFAULT 'user',
        points INTEGER DEFAULT 100,
        email TEXT,
        phone TEXT DEFAULT '',
        birthday TEXT DEFAULT '',
        bio TEXT DEFAULT '',
        avatar TEXT DEFAULT 'default',
        auth_provider TEXT DEFAULT 'email',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 自動檢查舊資料庫並補上缺少的欄位（防呆機制）
    cursor = conn.execute("PRAGMA table_info(users)")
    existing_columns = [row["name"] for row in cursor.fetchall()]
    columns_to_add = [
        ("phone", "TEXT DEFAULT ''"),
        ("birthday", "TEXT DEFAULT ''"),
        ("bio", "TEXT DEFAULT ''"),
        ("avatar", "TEXT DEFAULT 'default'"),
        ("email", "TEXT DEFAULT ''"),
        ("auth_provider", "TEXT DEFAULT 'email'")
    ]
    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

    cursor.execute("SELECT COUNT(*) FROM users WHERE account = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO users (id, account, password_hash, name, role, points)
        VALUES (?, ?, ?, ?, ?, ?)
        """, ("usr_admin", "admin", "123", "系統管理員", "admin", 9999))

    conn.commit()
    conn.close()

def save_clinical_knowledge(item: dict):
    conn = get_db()
    symptoms = item.get("targetSymptoms") or item.get("target_symptoms", [])
    if isinstance(symptoms, str):
        try:
            symptoms = json.loads(symptoms)
        except Exception:
            symptoms = [symptoms]
    conn.execute("""
    INSERT OR REPLACE INTO clinical_knowledge (
        id, title, authority, category, ingredient,
        evidence_level, recommended_dose, mechanism,
        contraindications, target_symptoms_json, citation
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item["id"],
        item["title"],
        item.get("authority", ""),
        item.get("category", ""),
        item.get("ingredient", ""),
        item.get("evidenceLevel") or item.get("evidence_level", "Level 1"),
        item.get("recommendedDose") or item.get("recommended_dose", ""),
        item.get("mechanism", ""),
        item.get("contraindications", ""),
        json.dumps(symptoms, ensure_ascii=False),
        item.get("citation", "")
    ))
    conn.commit()
    conn.close()
    return item

def reset_clinical_knowledge_to_defaults():
    try:
        try:
            from backend.vector_store import FULL_CLINICAL_LITERATURES
        except ImportError:
            from vector_store import FULL_CLINICAL_LITERATURES
        defaults = FULL_CLINICAL_LITERATURES
    except Exception:
        defaults = []
    
    conn = get_db()
    conn.execute("DELETE FROM clinical_knowledge")
    conn.commit()
    conn.close()
    
    batch_save_clinical_knowledge(defaults)
    return get_all_clinical_knowledge()

def save_pharmacy_products(products: list):
    conn = get_db()
    cursor = conn.cursor()
    for p in products:
        cursor.execute("""
        INSERT OR REPLACE INTO pharmacy_cache (id, pharmacy, product_name, price, spec, url, image_url, in_stock, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            p.get("id") or f"{p['pharmacy']}_{hash(p['product_name'])}",
            p["pharmacy"],
            p["product_name"],
            p["price"],
            p.get("spec", ""),
            p.get("url", ""),
            p.get("image_url", ""),
            p.get("in_stock", 1)
        ))
    conn.commit()
    conn.close()

def search_cached_products(keyword: str):
    conn = get_db()
    cursor = conn.cursor()
    like_query = f"%{keyword}%"
    rows = cursor.execute("""
    SELECT * FROM pharmacy_cache 
    WHERE product_name LIKE ? OR pharmacy LIKE ? OR spec LIKE ?
    ORDER BY price ASC
    """, (like_query, like_query, like_query)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_clinical_knowledge(item_id: str):
    conn = get_db()
    conn.execute("DELETE FROM clinical_knowledge WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

def authenticate_user(account: str, password_raw: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE account = ? OR email = ?", (account, account)).fetchone()
    conn.close()
    if not row:
        return None
    user = dict(row)
    if user["password_hash"] == password_raw:
        return {
            "id": user["id"],
            "account": user["account"],
            "name": user["name"],
            "role": user["role"],
            "points": user["points"],
            "phone": user.get("phone", ""),
            "birthday": user.get("birthday", ""),
            "bio": user.get("bio", "")
        }
    return None

def register_user(account: str, password_raw: str, name: str = None, role: str = "user"):
    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE account = ? OR email = ?", (account, account)).fetchone()
    if existing:
        conn.close()
        return None
    
    user_id = f"usr_{int(datetime.now().timestamp() * 1000)}"
    display_name = name if name and name.strip() else account
    assigned_role = "admin" if "admin" in account.lower() else role
    initial_points = 9999 if assigned_role == "admin" else 100

    conn.execute("""
    INSERT INTO users (id, account, password_hash, name, role, points, email, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (user_id, account, password_raw, display_name, assigned_role, initial_points, account))
    conn.commit()
    conn.close()

    if initial_points > 0:
        add_points_transaction(account, initial_points, "新會員註冊獎勵")

    return {
        "id": user_id,
        "account": account,
        "name": display_name,
        "role": assigned_role,
        "points": initial_points
    }

def get_user_profile(account: str):
    conn = get_db()
    row = conn.execute("SELECT id, account, name, role, points, phone, birthday, bio, avatar, created_at, email, auth_provider FROM users WHERE account = ? OR email = ?", (account, account)).fetchone()
    conn.close()
    return dict(row) if row else None

# 💡 依據使用者帳號取得專屬親友清單
def get_all_recipients(user_account: str = "test"):
    conn = get_db()
    rows = conn.execute("SELECT * FROM recipients WHERE user_account = ? ORDER BY created_at ASC", (user_account,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# 💡 新增親友時綁定當前使用者帳號（具備自動重試防鎖定機制）
def add_recipient(name: str, condition: str, phone: str = "", birthday: str = "", user_account: str = "test"):
    rec_id = f"rec_{int(datetime.now().timestamp() * 1000)}"
    
    # 最多重試 5 次，每次間隔 0.2 秒
    for attempt in range(5):
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO recipients (id, name, condition, phone, birthday, user_account) VALUES (?, ?, ?, ?, ?, ?)",
                (rec_id, name, condition, phone, birthday, user_account)
            )
            conn.commit()
            break # 寫入成功，跳出迴圈
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < 4:
                try:
                    conn.close()
                except:
                    pass
                time.sleep(0.2) # 等待 0.2 秒後自動重試
                continue
            else:
                try:
                    conn.close()
                except:
                    pass
                raise e
        finally:
            try:
                conn.close()
            except:
                pass
                
    return {"id": rec_id, "name": name, "condition": condition, "phone": phone, "birthday": birthday, "user_account": user_account}

def update_recipient(rec_id: str, name: str, condition: str, phone: str = "", birthday: str = ""):
    conn = get_db()
    conn.execute(
        "UPDATE recipients SET name = ?, condition = ?, phone = ?, birthday = ? WHERE id = ?",
        (name, condition, phone, birthday, rec_id)
    )
    conn.commit()
    conn.close()
    return {"id": rec_id, "name": name, "condition": condition, "phone": phone, "birthday": birthday}

def delete_recipient(rec_id: str):
    conn = get_db()
    conn.execute("DELETE FROM recipients WHERE id = ?", (rec_id,))
    conn.commit()
    conn.close()

def get_all_orders(user_account: str = "test"):
    conn = get_db()
    rows = conn.execute("SELECT * FROM orders WHERE user_account = ? ORDER BY created_at DESC", (user_account,)).fetchall()
    conn.close()
    orders = []
    for r in rows:
        d = dict(r)
        d["items"] = json.loads(d["items_json"])
        orders.append(d)
    return orders

def create_order(order_id: str, items: list, total: str, recipient: str, pharmacy: str = "連鎖藥局", user_account: str = "test"):
    conn = get_db()
    status = f"系統已向【{pharmacy}】完成專人代購下單 (白手套配送中)"
    conn.execute(
        "INSERT INTO orders (id, items_json, total, recipient, pharmacy, status, user_account) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (order_id, json.dumps(items, ensure_ascii=False), total, recipient, pharmacy, status, user_account)
    )
    conn.commit()
    conn.close()
    return {"id": order_id, "status": status}

def cancel_order(order_id: str):
    conn = get_db()
    conn.execute("UPDATE orders SET status = '系統已連線藥局辦理撤單 (全額退款成功)' WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

def get_points_ledger(account: str = "test"):
    conn = get_db()
    rows = conn.execute("SELECT * FROM points_ledger WHERE account = ? OR user_account = ? ORDER BY id DESC", (account, account)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_points_transaction(account: str, amount: int, title: str):
    now = datetime.now()
    date_str = now.strftime("%Y/%m/%d")
    exp_year = now.year + 3
    expire_str = f"{exp_year}/{now.strftime('%m/%d')} (剩餘 3 年)" if amount > 0 else "已折抵使用"
    tx_type = "plus" if amount > 0 else "minus"

    conn = get_db()
    conn.execute(
        "INSERT INTO points_ledger (account, amount, title, date_str, expire_str, type, user_account) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (account, amount, title, date_str, expire_str, tx_type, account)
    )
    conn.execute(
        "UPDATE users SET points = points + ? WHERE account = ? OR email = ?",
        (amount, account, account)
    )
    conn.commit()
    conn.close()

def get_all_clinical_knowledge():
    conn = get_db()
    rows = conn.execute("SELECT * FROM clinical_knowledge ORDER BY id ASC").fetchall()
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        try:
            d["targetSymptoms"] = json.loads(d["target_symptoms_json"])
        except Exception:
            d["targetSymptoms"] = []
        d["evidenceLevel"] = d.get("evidence_level", "Level 1")
        d["recommendedDose"] = d.get("recommended_dose", "")
        items.append(d)
    return items

def batch_save_clinical_knowledge(items: list):
    conn = get_db()
    cursor = conn.cursor()
    for item in items:
        symptoms = item.get("targetSymptoms") or item.get("target_symptoms", [])
        if isinstance(symptoms, str):
            try:
                symptoms = json.loads(symptoms)
            except Exception:
                symptoms = [symptoms]
        cursor.execute("""
        INSERT OR REPLACE INTO clinical_knowledge (
            id, title, authority, category, ingredient,
            evidence_level, recommended_dose, mechanism,
            contraindications, target_symptoms_json, citation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item["id"],
            item["title"],
            item.get("authority", ""),
            item.get("category", ""),
            item.get("ingredient", ""),
            item.get("evidenceLevel") or item.get("evidence_level", "Level 1"),
            item.get("recommendedDose") or item.get("recommended_dose", ""),
            item.get("mechanism", ""),
            item.get("contraindications", ""),
            json.dumps(symptoms, ensure_ascii=False),
            item.get("citation", "")
        ))
    conn.commit()
    conn.close()
    return len(items)

def get_system_config(key: str, default=None):
    conn = get_db()
    row = conn.execute("SELECT value_json FROM system_config WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["value_json"])
        except Exception:
            return row["value_json"]
    return default

def set_system_config(key: str, value):
    val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    conn = get_db()
    conn.execute("""
    INSERT OR REPLACE INTO system_config (key, value_json, updated_at)
    VALUES (?, ?, CURRENT_TIMESTAMP)
    """, (key, val_str))
    conn.commit()
    conn.close()
    return value

def get_database_stats():
    conn = get_db()
    cursor = conn.cursor()
    tables = ["users", "recipients", "orders", "points_ledger", "pharmacy_cache", "clinical_knowledge", "system_config"]
    counts = {}
    for t in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            counts[t] = cursor.fetchone()[0]
        except Exception:
            counts[t] = 0
    conn.close()
    file_size_kb = round(os.path.getsize(DB_PATH) / 1024, 1) if os.path.exists(DB_PATH) else 0
    return {
        "db_name": "caregift.db",
        "db_path": DB_PATH,
        "db_size_kb": file_size_kb,
        "status": "connected",
        "counts": counts
    }

def update_user_profile_in_db(account: str, name: str, phone: str, birthday: str, bio: str, avatar: str = "default"):
    conn = get_db()
    try:
        conn.execute(
            """UPDATE users 
               SET name = ?, phone = ?, birthday = ?, bio = ?, avatar = ? 
               WHERE account = ? OR email = ?""", 
            (name, phone, birthday, bio, avatar, account, account)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("更新 SQLite 會員資料失敗:", e)
        conn.close()
        return False

def get_user_profile_by_account(account: str):
    conn = get_db()
    row = conn.execute(
        """
        SELECT account, name, role, points, phone, birthday, bio, avatar, created_at, email, auth_provider 
        FROM users 
        WHERE account = ? OR email = ?
        """, 
        (account, account)
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def export_full_database():
    return {
        "schema_version": "2.0",
        "database": "SQLite (caregift.db)",
        "exported_at": datetime.now().isoformat(),
        "tables": {
            "recipients": get_all_recipients(),
            "orders": get_all_orders(),
            "points_ledger": get_points_ledger("test"),
            "clinical_knowledge": get_all_clinical_knowledge()
        }
    }

def update_recipient_line_id(recipient_name: str, line_user_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE recipients SET line_user_id = ? WHERE name = ?",
        (line_user_id, recipient_name)
    )
    conn.commit()
    conn.close()
    return {"success": True, "name": recipient_name, "line_user_id": line_user_id}

init_db()