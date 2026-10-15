import sqlite3
import json
import hmac
import os
import time
import uuid

import bcrypt
from datetime import datetime, timedelta, timezone

# 💡 伺服器一律使用台灣時間（Render 預設是 UTC，會讓 LINE 訊息時間慢 8 小時、聊天排序錯亂）
#    使用 POSIX 時區字串 CST-8（UTC+8、台灣無日光節約），不依賴系統是否安裝時區資料
os.environ["TZ"] = "CST-8"
if hasattr(time, "tzset"):
    time.tzset()

# 測試可用 GIFTSENSE_DB_PATH 指向暫存複本，避免改到 repo 內的 caregift.db
DB_PATH = os.getenv("GIFTSENSE_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "caregift.db")

# 💡 暖心選物商品資料（藥局官網實際查價）統一放在 product_catalog.py，init_db 啟動時同步寫入
from product_catalog import DEFAULT_RECOMMENDATION_PRODUCTS
# 💡 設定 TURSO_DATABASE_URL 後改用 Turso 雲端資料庫（Render 免費方案重啟時資料才不會消失）
from db_backend import USE_TURSO, connect_turso, bootstrap_turso_from_sqlite

# =========================================================================
# 密碼：以 bcrypt 雜湊儲存（2026/10/15 起）
# 舊資料的明文密碼在啟動時一次轉成雜湊；登入時若仍遇到明文，驗證成功後立即改存雜湊
# =========================================================================
def _password_bytes(raw: str) -> bytes:
    # bcrypt 只使用前 72 個位元組；新版 bcrypt 對超過的長度會報錯，因此先截斷
    return (raw or "").encode("utf-8")[:72]


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(_password_bytes(raw), bcrypt.gensalt()).decode("ascii")


def is_password_hash(stored) -> bool:
    return isinstance(stored, str) and stored.startswith(("$2a$", "$2b$", "$2y$"))


def verify_password(raw: str, stored) -> bool:
    if not stored or raw is None:
        return False
    if is_password_hash(stored):
        try:
            return bcrypt.checkpw(_password_bytes(raw), stored.encode("ascii"))
        except ValueError:
            return False
    return hmac.compare_digest(str(stored).encode("utf-8"), raw.encode("utf-8"))  # 尚未轉換的舊明文


# 點數規則（2026/10/15 起改為小額回饋，1 點折抵 $1）
SIGNUP_BONUS_POINTS = 5        # 新會員註冊禮
AI_GUARD_REDEEM_COST = 1       # 兌換 AI 守護助理 3 次詢問所需點數


def round_points(value) -> float:
    """點數保留到小數第 2 位，避免浮點數累加出現 0.30000000000000004"""
    return round(float(value or 0), 2)


def format_points(value) -> str:
    v = round_points(value)
    return str(int(v)) if v == int(v) else f"{v:g}"


def get_db():
    if USE_TURSO:
        return connect_turso()
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
    if USE_TURSO:
        # 第一次連上空的 Turso 資料庫：匯入 repo 內附的 caregift.db（示範帳號、文獻、商品快取）
        try:
            if bootstrap_turso_from_sqlite(conn, DB_PATH):
                print("【Turso】已從 caregift.db 匯入初始資料")
        except Exception as e:
            print("【Turso】初始資料匯入失敗，改用預設資料建立：", e)
            conn.rollback()
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
        quick_tags_json TEXT DEFAULT '[]',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 舊資料庫自動補上 recipients 缺少的欄位
    cursor.execute("PRAGMA table_info(recipients)")
    existing_rec_cols = [c[1] for c in cursor.fetchall()]
    for col_name, col_type in [
        ("phone", "TEXT"),
        ("birthday", "TEXT"),
        ("line_user_id", "TEXT"),
        ("user_account", "TEXT DEFAULT 'test'"),
        ("quick_tags_json", "TEXT DEFAULT '[]'"),
        ("line_bind_code", "TEXT"),
        ("line_bind_expires", "TEXT")
    ]:
        if col_name not in existing_rec_cols:
            cursor.execute(f"ALTER TABLE recipients ADD COLUMN {col_name} {col_type}")

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

    # 4.5 recommendation_products 表格（關懷推薦商品資料庫）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recommendation_products (
        id TEXT PRIMARY KEY,
        product_name TEXT NOT NULL,
        sku TEXT,
        ean_13 TEXT,
        category TEXT,
        spec TEXT,
        search_kw TEXT,
        match_conditions_json TEXT NOT NULL,
        match_reason TEXT,
        recommended_pharmacy TEXT,
        best_price INTEGER NOT NULL,
        official_url TEXT,
        pharmacy_comparison_json TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        price_checked_at TEXT,
        primary_conditions_json TEXT DEFAULT '[]',
        exclude_conditions_json TEXT DEFAULT '[]',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("PRAGMA table_info(recommendation_products)")
    rp_cols = [c[1] for c in cursor.fetchall()]
    if "price_checked_at" not in rp_cols:
        cursor.execute("ALTER TABLE recommendation_products ADD COLUMN price_checked_at TEXT")
    if "primary_conditions_json" not in rp_cols:
        cursor.execute("ALTER TABLE recommendation_products ADD COLUMN primary_conditions_json TEXT DEFAULT '[]'")
    if "exclude_conditions_json" not in rp_cols:
        cursor.execute("ALTER TABLE recommendation_products ADD COLUMN exclude_conditions_json TEXT DEFAULT '[]'")

    # 4.6 ai_guard_usage 表格（AI 守護助理每日詢問次數，依帳號計算）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_guard_usage (
        account TEXT NOT NULL,
        date_str TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        bonus INTEGER DEFAULT 0,
        PRIMARY KEY (account, date_str)
    )
    """)

    # 4.7 reward_claims 表格（回饋點數領取紀錄，用來限制每日／每週次數）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reward_claims (
        account TEXT NOT NULL,
        claim_key TEXT NOT NULL,
        amount INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (account, claim_key)
    )
    """)

    # 4.7.5 chat_messages 表格（傳情小站聊天紀錄；原本只放記憶體，服務重啟就會消失）
    #      註：舊版遺留的 family_messages 表欄位不同且已不使用，所以另開新表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        owner_account TEXT NOT NULL,
        elder TEXT NOT NULL,
        sender TEXT,
        content TEXT,
        type TEXT DEFAULT 'text',
        timestamp TEXT,
        from_role TEXT DEFAULT 'family'
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_owner ON chat_messages (owner_account, elder)")

    # 4.8 cashback_orders 表格（ShopBack 模式購物回饋：點擊追蹤 → 完成購物 → 藥局確認後入帳）
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cashback_orders (
        id TEXT PRIMARY KEY,
        account TEXT NOT NULL,
        recipient TEXT,
        pharmacy TEXT NOT NULL,
        product_name TEXT NOT NULL,
        est_price INTEGER DEFAULT 0,
        rate REAL NOT NULL,
        status TEXT NOT NULL,
        order_amount INTEGER DEFAULT 0,
        points INTEGER DEFAULT 0,
        official_url TEXT,
        created_at TEXT NOT NULL,
        purchased_at TEXT,
        settled_at TEXT
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
        ("auth_provider", "TEXT DEFAULT 'email'"),
        ("social_id", "TEXT"),
        ("social_avatar_url", "TEXT DEFAULT ''"),
        ("last_active_date", "TEXT DEFAULT ''"),
        ("login_streak", "INTEGER DEFAULT 0")
    ]
    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

    cursor.execute(
        "UPDATE recipients SET line_user_id = NULL "
        "WHERE COALESCE(user_account, '') = '' AND line_user_id IS NOT NULL"
    )

    # 一次性：清除舊的暖幣紀錄與傳情小站聊天紀錄（2026/10/13 使用者要求，避免和新的測試紀錄混在一起）
    # 舊資料移到 *_archive 表保留備查，不直接刪除；會員保留「新會員註冊獎勵 +100」（以新版格式重新記錄），
    # 其餘紀錄歸零後重新累計（管理員帳號的點數不動）
    if not cursor.execute("SELECT 1 FROM system_config WHERE key = 'points_reset_20261013'").fetchone():
        cursor.execute("CREATE TABLE IF NOT EXISTS chat_messages_archive AS SELECT * FROM chat_messages WHERE 0")
        cursor.execute("INSERT INTO chat_messages_archive SELECT * FROM chat_messages")
        cursor.execute("DELETE FROM chat_messages")
        cursor.execute("CREATE TABLE IF NOT EXISTS points_ledger_archive AS SELECT * FROM points_ledger WHERE 0")
        cursor.execute("INSERT INTO points_ledger_archive SELECT * FROM points_ledger")
        cursor.execute("DELETE FROM points_ledger")
        cursor.execute("CREATE TABLE IF NOT EXISTS cashback_orders_archive AS SELECT * FROM cashback_orders WHERE 0")
        cursor.execute("INSERT INTO cashback_orders_archive SELECT * FROM cashback_orders")
        cursor.execute("DELETE FROM cashback_orders")
        cursor.execute("DELETE FROM reward_claims")
        reset_now = datetime.now()
        bonus_date = reset_now.strftime("%Y/%m/%d")
        bonus_expire = f"{reset_now.year + 3}/{reset_now.strftime('%m/%d')} (剩餘 3 年)"
        members = cursor.execute(
            "SELECT account FROM users WHERE COALESCE(role, 'user') != 'admin'"
        ).fetchall()
        for m in members:
            cursor.execute(
                "INSERT INTO points_ledger (account, amount, title, date_str, expire_str, type, user_account) "
                "VALUES (?, 100, '新會員註冊獎勵', ?, ?, 'plus', ?)",
                (m["account"], bonus_date, bonus_expire, m["account"])
            )
        cursor.execute("UPDATE users SET points = 100 WHERE COALESCE(role, 'user') != 'admin'")
        cursor.execute(
            "INSERT OR REPLACE INTO system_config (key, value_json) VALUES ('points_reset_20261013', ?)",
            (json.dumps({"done_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}),)
        )

    # 一次性：先前 LINE 回覆的時間是以 UTC 記錄（慢 8 小時），補回台灣時間
    if not cursor.execute("SELECT 1 FROM system_config WHERE key = 'chat_tz_fix_20261013'").fetchone():
        cursor.execute(
            "UPDATE chat_messages SET timestamp = datetime(timestamp, '+8 hours') "
            "WHERE from_role = 'elder' AND timestamp LIKE '____-__-__ __:__:__'"
        )
        cursor.execute(
            "INSERT OR REPLACE INTO system_config (key, value_json) VALUES ('chat_tz_fix_20261013', ?)",
            (json.dumps({"done_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}),)
        )

    # 一次性：點數改為小額回饋（2026/10/15）。舊紀錄依新規則換算，並把差額反映到會員點數
    if not cursor.execute("SELECT 1 FROM system_config WHERE key = 'points_rescale_20261015'").fetchone():
        rescale = [
            ("title = '新會員註冊獎勵' AND amount = 100", 100, SIGNUP_BONUS_POINTS),
            ("title LIKE '發送關懷卡：%' AND amount = 10", 10, REWARD_RULES["care_card"]["amount"]),
            ("title = '小熊每週關懷加碼' AND amount = 50", 50, REWARD_RULES["mascot_weekly"]["amount"]),
            ("title LIKE '兌換 AI 守護助理詢問%' AND amount = -50", -50, -AI_GUARD_REDEEM_COST),
        ]
        for where, old_amount, new_amount in rescale:
            for r in cursor.execute(f"SELECT account FROM points_ledger WHERE {where}").fetchall():
                cursor.execute(
                    "UPDATE users SET points = ROUND(points + ?, 2) WHERE account = ? OR email = ?",
                    (new_amount - old_amount, r["account"], r["account"])
                )
            cursor.execute(f"UPDATE points_ledger SET amount = ? WHERE {where}", (new_amount,))
        cursor.execute("UPDATE reward_claims SET amount = ? WHERE claim_key LIKE 'care_card:%' AND amount = 10",
                       (REWARD_RULES["care_card"]["amount"],))
        cursor.execute("UPDATE reward_claims SET amount = ? WHERE claim_key LIKE 'mascot_weekly:%' AND amount = 50",
                       (REWARD_RULES["mascot_weekly"]["amount"],))
        cursor.execute(
            "INSERT OR REPLACE INTO system_config (key, value_json) VALUES ('points_rescale_20261015', ?)",
            (json.dumps({"done_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}),)
        )

    # 一次性：補上用藥安全與照護指引文獻（已存在的文獻不覆蓋，保留管理員的編輯）
    if not cursor.execute("SELECT 1 FROM system_config WHERE key = 'knowledge_guidance_20261015'").fetchone():
        try:
            from clinical_guidance import GUIDANCE_LITERATURES
        except ImportError:
            GUIDANCE_LITERATURES = []
        for lit in GUIDANCE_LITERATURES:
            if cursor.execute("SELECT 1 FROM clinical_knowledge WHERE id = ?", (lit["id"],)).fetchone():
                continue
            cursor.execute("""
            INSERT INTO clinical_knowledge (
                id, title, authority, category, ingredient,
                evidence_level, recommended_dose, mechanism,
                contraindications, target_symptoms_json, citation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lit["id"], lit["title"], lit.get("authority", ""), lit.get("category", ""), lit.get("ingredient", ""),
                lit.get("evidenceLevel", ""), lit.get("recommendedDose", ""), lit.get("mechanism", ""),
                lit.get("contraindications", ""), json.dumps(lit.get("targetSymptoms", []), ensure_ascii=False),
                lit.get("citation", "")
            ))
        cursor.execute(
            "INSERT OR REPLACE INTO system_config (key, value_json) VALUES ('knowledge_guidance_20261015', ?)",
            (json.dumps({"done_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}),)
        )

    # 一次性：快速提問改為依病況分類的新題庫，重新產生每位親友的提問
    if not cursor.execute("SELECT 1 FROM system_config WHERE key = 'quick_chips_v2_20261015'").fetchone():
        try:
            from chips_generator import get_clinical_rule_chips as _rule_chips
            for rec in cursor.execute("SELECT id, name, condition FROM recipients").fetchall():
                cursor.execute(
                    "UPDATE recipients SET quick_tags_json = ? WHERE id = ?",
                    (json.dumps(_rule_chips(rec["condition"], rec["name"]), ensure_ascii=False), rec["id"])
                )
            cursor.execute(
                "INSERT OR REPLACE INTO system_config (key, value_json) VALUES ('quick_chips_v2_20261015', ?)",
                (json.dumps({"done_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}),)
            )
        except Exception as e:
            print("Notice: quick chips refresh deferred:", e)

    cursor.execute("SELECT COUNT(*) FROM users WHERE account = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO users (id, account, password_hash, name, role, points)
        VALUES (?, ?, ?, ?, ?, ?)
        """, ("usr_admin", "admin", hash_password("123"), "系統管理員", "admin", 9999))

    # 舊資料的明文密碼一律轉成 bcrypt 雜湊（已是雜湊的不動，可重複執行）
    for r in cursor.execute(
        "SELECT id, password_hash FROM users WHERE password_hash IS NOT NULL AND password_hash != ''"
    ).fetchall():
        if not is_password_hash(r["password_hash"]):
            cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(r["password_hash"]), r["id"]))

    # 💡 線上環境請在 Render 設定 ADMIN_PASSWORD：啟動時以它覆蓋 admin 密碼（存成雜湊），
    #    避免任何人用 repo 裡公開的預設密碼登入管理後台
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    if admin_password:
        current = cursor.execute("SELECT password_hash FROM users WHERE account = 'admin'").fetchone()
        if not current or not verify_password(admin_password, current["password_hash"]):
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE account = 'admin'",
                (hash_password(admin_password),)
            )

    # 為尚未有快速提問晶片的親友自動補上臨床規則晶片
    try:
        from chips_generator import get_clinical_rule_chips
    except Exception:
        get_clinical_rule_chips = lambda c, n: []

    cursor.execute("SELECT id, name, condition, quick_tags_json FROM recipients")
    for rec in cursor.fetchall():
        if not rec["quick_tags_json"] or rec["quick_tags_json"] == "[]":
            auto_tags = get_clinical_rule_chips(rec["condition"], rec["name"])
            cursor.execute(
                "UPDATE recipients SET quick_tags_json = ? WHERE id = ?",
                (json.dumps(auto_tags, ensure_ascii=False), rec["id"])
            )

    # 全新資料庫時預先寫入國家級臨床文獻
    cursor.execute("SELECT COUNT(*) FROM clinical_knowledge")
    if cursor.fetchone()[0] == 0:
        try:
            from vector_store import FULL_CLINICAL_LITERATURES
            for lit in FULL_CLINICAL_LITERATURES:
                cursor.execute("""
                INSERT OR REPLACE INTO clinical_knowledge (
                    id, title, authority, category, ingredient,
                    evidence_level, recommended_dose, mechanism,
                    contraindications, target_symptoms_json, citation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    lit["id"],
                    lit["title"],
                    lit.get("authority", ""),
                    lit.get("category", ""),
                    lit.get("ingredient", ""),
                    lit.get("evidenceLevel", "Level 1"),
                    lit.get("recommendedDose", ""),
                    lit.get("mechanism", ""),
                    lit.get("contraindications", ""),
                    json.dumps(lit.get("targetSymptoms", []), ensure_ascii=False),
                    lit.get("citation", "")
                ))
        except Exception as e:
            print("Notice: Clinical knowledge auto-seed deferred:", e)

    # 推薦商品：每次啟動都以預設資料為準（移除不在預設清單的商品，並更新內容）
    default_ids = [p["id"] for p in DEFAULT_RECOMMENDATION_PRODUCTS]
    cursor.execute(
        f"DELETE FROM recommendation_products WHERE id NOT IN ({','.join('?' * len(default_ids))})",
        default_ids
    )
    conn.commit()
    conn.close()
    save_recommendation_products(DEFAULT_RECOMMENDATION_PRODUCTS)

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

def save_recommendation_products(products: list):
    conn = get_db()
    cursor = conn.cursor()
    for p in products:
        if not isinstance(p, dict):
            continue
        cursor.execute("""
        INSERT OR REPLACE INTO recommendation_products (
            id, product_name, sku, ean_13, category, spec, search_kw,
            match_conditions_json, match_reason, recommended_pharmacy,
            best_price, official_url, pharmacy_comparison_json, is_active, price_checked_at,
            primary_conditions_json, exclude_conditions_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p.get("id") or f"rec_{hash(str(p))}",
            p.get("product_name", ""),
            p.get("sku", ""),
            p.get("ean_13", ""),
            p.get("category", ""),
            p.get("spec", ""),
            p.get("search_kw", ""),
            json.dumps(p.get("match_conditions") or [], ensure_ascii=False),
            p.get("match_reason", ""),
            p.get("recommended_pharmacy", ""),
            int(p.get("best_price") or 0),
            p.get("official_url", ""),
            json.dumps(p.get("pharmacy_comparison") or [], ensure_ascii=False),
            1,
            p.get("price_checked_at", ""),
            json.dumps(p.get("primary_conditions") or [], ensure_ascii=False),
            json.dumps(p.get("exclude_conditions") or [], ensure_ascii=False)
        ))
    conn.commit()
    conn.close()
    return len(products)

def get_all_recommendation_products():
    conn = get_db()
    rows = conn.execute("SELECT * FROM recommendation_products WHERE is_active = 1 ORDER BY best_price ASC").fetchall()
    conn.close()
    products = []
    for r in rows:
        d = dict(r)
        d["match_conditions"] = json.loads(d.get("match_conditions_json") or "[]")
        d["pharmacy_comparison"] = json.loads(d.get("pharmacy_comparison_json") or "[]")
        d["primary_conditions"] = json.loads(d.get("primary_conditions_json") or "[]")
        d["exclude_conditions"] = json.loads(d.get("exclude_conditions_json") or "[]")
        products.append(d)
    return products

_NEGATION_PREFIXES = ("未", "無", "非", "沒有", "不是")

def _mentions(cond: str, term: str) -> bool:
    """病況文字是否提到 term；「未洗腎」「沒有糖尿病」這類否定敘述不算"""
    start = cond.find(term)
    while start != -1:
        if not any(cond[max(0, start - len(n)):start] == n for n in _NEGATION_PREFIXES):
            return True
        start = cond.find(term, start + 1)
    return False

def _is_excluded(item: dict, cond: str) -> bool:
    return any(_mentions(cond, (t or "").lower()) for t in (item.get("exclude_conditions") or []) if t)

def _match_score(item: dict, cond: str) -> int:
    """比對分數：關鍵字越具體（越長）分數越高；命中該商品的主要對應病況再加權。
    命中 exclude_conditions（例如服用抗凝血劑時的魚油、Q10）一律不推薦"""
    if _is_excluded(item, cond):
        return 0
    primary = [t.lower() for t in (item.get("primary_conditions") or [])]
    score = 0
    for term in item.get("match_conditions") or []:
        t = (term or "").lower()
        if not t or t == "日常":
            continue
        if _mentions(cond, t) or (len(cond) >= 2 and cond in t):
            score += len(t) * (3 if t in primary else 1)
    return score

RECOMMEND_LIMIT = 3

def match_recommendation_products(condition: str = "", limit: int = RECOMMEND_LIMIT):
    """暖心選物固定推薦 limit（3）項：
    - 先放與病況相關的商品（分數高 → 價格低），第一名標記 is_top_pick
    - 相關商品不足時，用一般日常保養品補滿，標記 is_related=False（前端以「日常保養推薦」另外呈現）
    - 補位商品同樣套用排除條件（例如服用抗凝血劑者不會出現魚油、Q10）
    - 完全沒有相關商品時標記 is_fallback（「日常養生」本來就是一般保養，不算）"""
    cond = (condition or "").lower().strip()
    items = get_all_recommendation_products()
    scored = []
    if cond:
        for item in items:
            score = _match_score(item, cond)
            if score > 0:
                scored.append((score, item))
    scored.sort(key=lambda x: (-x[0], x[1].get("best_price") or 0))
    related = [
        {**item, "match_score": score, "is_related": True, "is_top_pick": rank == 0}
        for rank, (score, item) in enumerate(scored[:limit])
    ]
    used = {p["id"] for p in related}
    general = [
        i for i in items
        if "日常" in (i.get("match_conditions") or []) and i["id"] not in used and not _is_excluded(i, cond)
    ]
    is_daily = not cond or "日常" in cond
    if is_daily and not related:
        # 日常養生：一般保養品就是對應的推薦（沒有特定病況，不標最推薦）
        related = [{**i, "match_score": 0, "is_related": True, "is_top_pick": False} for i in general[:limit]]
        general = general[limit:]
    fillers = [
        {**i, "match_score": 0, "is_related": False, "is_top_pick": False}
        for i in general[:max(0, limit - len(related))]
    ]
    return {
        "products": related + fillers,
        "related_count": len(related),
        "is_fallback": not related,
    }

def get_recommendation_products_by_condition(condition: str = ""):
    return match_recommendation_products(condition)["products"]

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
    if verify_password(password_raw, user["password_hash"]):
        if not is_password_hash(user["password_hash"]):
            conn = get_db()
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password_raw), user["id"]))
            conn.commit()
            conn.close()
        return {
            "id": user["id"],
            "account": user["account"],
            "name": user["name"],
            "role": user["role"],
            "points": round_points(user["points"]),
            "phone": user.get("phone", ""),
            "birthday": user.get("birthday", ""),
            "bio": user.get("bio", ""),
            "avatar_url": resolve_avatar_url(user),
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
    # 💡 一律註冊為一般會員，避免帳號含 admin 或前端傳 role 就取得管理員權限
    assigned_role = "user"
    initial_points = SIGNUP_BONUS_POINTS

    # 點數先寫 0，再由下方的點數交易加上註冊獎勵（避免重複計算成 200 點）
    conn.execute("""
    INSERT INTO users (id, account, password_hash, name, role, points, email, created_at)
    VALUES (?, ?, ?, ?, ?, 0, ?, CURRENT_TIMESTAMP)
    """, (user_id, account, hash_password(password_raw), display_name, assigned_role, account))
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

def resolve_avatar_url(user: dict) -> str:
    """頭貼優先順序：自行上傳 > 第三方登入的大頭照 > 空字串（前端顯示預設人像圖示）"""
    avatar = (user.get("avatar") or "").strip()
    if avatar.startswith("data:image/") or avatar.startswith("http"):
        return avatar
    return (user.get("social_avatar_url") or "").strip()

def _public_user(row):
    user = dict(row)
    user.pop("password_hash", None)
    user["avatar_url"] = resolve_avatar_url(user)
    if "points" in user:
        user["points"] = round_points(user["points"])
    return user

AVATAR_MAX_LENGTH = 450_000  # 約 330KB 圖片（base64）；前端上傳前會先縮到 512px

def set_user_avatar(account: str, image_data_url: str = ""):
    """自行上傳頭貼（data URL）；傳空字串則移除，改回第三方大頭照或預設圖示"""
    value = (image_data_url or "").strip() or "default"
    conn = get_db()
    conn.execute("UPDATE users SET avatar = ? WHERE account = ? OR email = ?", (value, account, account))
    conn.commit()
    row = conn.execute(
        "SELECT avatar, social_avatar_url FROM users WHERE account = ? OR email = ?", (account, account)
    ).fetchone()
    conn.close()
    return resolve_avatar_url(dict(row)) if row else None

def find_or_create_social_user(provider: str, social_id: str, email: str = "", email_verified: bool = False, name: str = "", picture: str = ""):
    """
    依平台驗證過的身分找出或建立會員：
    1. 先以 (auth_provider, social_id) 比對
    2. 再以「平台已驗證」的 email 比對既有一般會員（不比對 account、不合併管理員）
    3. 都沒有就建立新會員並發放註冊獎勵
    """
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE auth_provider = ? AND social_id = ?", (provider, social_id)).fetchone()

    if not row and email and email_verified:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? AND COALESCE(role, 'user') != 'admin'", (email,)
        ).fetchone()
        if row and not row["social_id"] and row["auth_provider"] == provider:
            conn.execute("UPDATE users SET social_id = ? WHERE id = ?", (social_id, row["id"]))
            conn.commit()

    created = False
    if not row:
        email_taken = bool(email) and conn.execute(
            "SELECT 1 FROM users WHERE account = ? OR email = ?", (email, email)
        ).fetchone() is not None
        account = email if email and not email_taken else f"{provider}_{social_id}"
        display_name = (name or "").strip() or (email.split("@")[0] if email else f"{provider.capitalize()} 會員")
        user_id = f"usr_{int(datetime.now().timestamp() * 1000)}"
        conn.execute(
            """INSERT INTO users (id, account, name, email, auth_provider, social_id, role, points, created_at, social_avatar_url)
               VALUES (?, ?, ?, ?, ?, ?, 'user', 0, CURRENT_TIMESTAMP, ?)""",
            (user_id, account, display_name, email if not email_taken else "", provider, social_id, picture or "")
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        created = True

    elif picture and picture != (row["social_avatar_url"] or ""):
        # 每次登入都同步第三方的最新大頭照
        conn.execute("UPDATE users SET social_avatar_url = ? WHERE id = ?", (picture, row["id"]))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()

    conn.close()
    if created:
        add_points_transaction(row["account"], SIGNUP_BONUS_POINTS, "新會員註冊獎勵")
        return {**get_user_profile(row["account"]), "is_new_user": True}
    return _public_user(row)

def get_user_profile(account: str):
    conn = get_db()
    row = conn.execute(
        "SELECT id, account, name, role, points, phone, birthday, bio, avatar, social_avatar_url, created_at, email, auth_provider "
        "FROM users WHERE account = ? OR email = ?",
        (account, account)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["avatar_url"] = resolve_avatar_url(d)
    d["points"] = round_points(d.get("points"))
    return d

def _recipient_row_to_dict(row):
    d = dict(row)
    try:
        from chips_generator import normalize_chips
        d["quick_tags"] = normalize_chips(json.loads(d.get("quick_tags_json") or "[]"))
    except Exception:
        d["quick_tags"] = []
    d["line_bound"] = bool(d.get("line_user_id"))
    d.pop("line_bind_code", None)
    d.pop("line_bind_expires", None)
    return d

def _resolve_quick_tags(quick_tags, condition: str, name: str):
    if quick_tags is None:
        try:
            from chips_generator import get_clinical_rule_chips
            quick_tags = get_clinical_rule_chips(condition, name)
        except Exception:
            quick_tags = []
    return quick_tags, json.dumps(quick_tags, ensure_ascii=False)

# 💡 依據使用者帳號取得專屬親友清單
def get_all_recipients(user_account: str = "test"):
    conn = get_db()
    rows = conn.execute("SELECT * FROM recipients WHERE user_account = ? ORDER BY created_at ASC", (user_account,)).fetchall()
    conn.close()
    return [_recipient_row_to_dict(r) for r in rows]

def get_recipient_by_id(rec_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM recipients WHERE id = ?", (rec_id,)).fetchone()
    conn.close()
    return _recipient_row_to_dict(row) if row else None

# 💡 新增親友時綁定當前使用者帳號（具備自動重試防鎖定機制），未指定晶片時依病況自動產生
def add_recipient(name: str, condition: str, phone: str = "", birthday: str = "", user_account: str = "test", quick_tags: list = None):
    rec_id = f"rec_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:6]}"  # 加隨機碼，避免同一毫秒建立時撞號
    quick_tags, tags_json = _resolve_quick_tags(quick_tags, condition, name)

    # 最多重試 5 次，每次間隔 0.2 秒
    for attempt in range(5):
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO recipients (id, name, condition, phone, birthday, user_account, quick_tags_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rec_id, name, condition, phone, birthday, user_account, tags_json)
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
                
    return {"id": rec_id, "name": name, "condition": condition, "phone": phone, "birthday": birthday, "user_account": user_account, "quick_tags": quick_tags}

def update_recipient(rec_id: str, name: str, condition: str, phone: str = "", birthday: str = "", quick_tags: list = None):
    quick_tags, tags_json = _resolve_quick_tags(quick_tags, condition, name)
    conn = get_db()
    conn.execute(
        "UPDATE recipients SET name = ?, condition = ?, phone = ?, birthday = ?, quick_tags_json = ? WHERE id = ?",
        (name, condition, phone, birthday, tags_json, rec_id)
    )
    conn.commit()
    conn.close()
    return {"id": rec_id, "name": name, "condition": condition, "phone": phone, "birthday": birthday, "quick_tags": quick_tags}

def update_recipient_quick_tags(rec_id: str, quick_tags: list):
    conn = get_db()
    conn.execute("UPDATE recipients SET quick_tags_json = ? WHERE id = ?", (json.dumps(quick_tags, ensure_ascii=False), rec_id))
    conn.commit()
    conn.close()
    return {"id": rec_id, "quick_tags": quick_tags}

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

def cancel_order(order_id: str, user_account: str) -> bool:
    """只能取消自己帳號的訂單；找不到（或不是自己的）回傳 False"""
    conn = get_db()
    cur = conn.execute(
        "UPDATE orders SET status = '系統已連線藥局辦理撤單 (全額退款成功)' WHERE id = ? AND user_account = ?",
        (order_id, user_account)
    )
    conn.commit()
    conn.close()
    return (cur.rowcount or 0) > 0

TAIWAN_TZ = timezone(timedelta(hours=8))

def check_in_user(account: str):
    """每天第一次開啟 App 時打卡：昨天有上線就連續天數 +1，中間斷掉就從第 1 天重新計算（以台灣日期為準）"""
    today = datetime.now(TAIWAN_TZ).date()
    conn = get_db()
    row = conn.execute(
        "SELECT account, last_active_date, login_streak FROM users WHERE account = ? OR email = ?",
        (account, account)
    ).fetchone()
    if not row:
        conn.close()
        return None
    last = row["last_active_date"] or ""
    streak = int(row["login_streak"] or 0)
    if last == today.isoformat():
        new_streak = max(streak, 1)
    elif last == (today - timedelta(days=1)).isoformat():
        new_streak = streak + 1
    else:
        new_streak = 1
    if last != today.isoformat():
        conn.execute(
            "UPDATE users SET last_active_date = ?, login_streak = ? WHERE account = ?",
            (today.isoformat(), new_streak, row["account"])
        )
        conn.commit()
    conn.close()
    return {"streak": new_streak, "date": today.isoformat(), "is_new_day": last != today.isoformat()}

def get_points_ledger(account: str = "test"):
    conn = get_db()
    rows = conn.execute("SELECT * FROM points_ledger WHERE account = ? OR user_account = ? ORDER BY id DESC", (account, account)).fetchall()
    conn.close()
    return [{**dict(r), "amount": round_points(r["amount"])} for r in rows]

def add_points_transaction(account: str, amount: float, title: str):
    amount = round_points(amount)
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
        "UPDATE users SET points = ROUND(points + ?, 2) WHERE account = ? OR email = ?",
        (amount, account, account)
    )
    conn.commit()
    conn.close()

def get_ai_guard_quota(account: str, daily_limit: int):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    row = conn.execute("SELECT used, bonus FROM ai_guard_usage WHERE account = ? AND date_str = ?", (account, today)).fetchone()
    conn.close()
    used = row["used"] if row else 0
    bonus = row["bonus"] if row else 0
    limit = daily_limit + bonus
    return {"date": today, "used": used, "bonus": bonus, "limit": limit, "remaining": max(0, limit - used)}

def consume_ai_guard_quota(account: str, daily_limit: int):
    """扣除一次詢問次數；已達上限時回傳 (False, quota)"""
    quota = get_ai_guard_quota(account, daily_limit)
    if quota["remaining"] <= 0:
        return False, quota
    conn = get_db()
    conn.execute("""
    INSERT INTO ai_guard_usage (account, date_str, used, bonus) VALUES (?, ?, 1, 0)
    ON CONFLICT(account, date_str) DO UPDATE SET used = used + 1
    """, (account, quota["date"]))
    conn.commit()
    conn.close()
    return True, get_ai_guard_quota(account, daily_limit)

def add_ai_guard_bonus(account: str, extra: int, daily_limit: int):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    conn.execute("""
    INSERT INTO ai_guard_usage (account, date_str, used, bonus) VALUES (?, ?, 0, ?)
    ON CONFLICT(account, date_str) DO UPDATE SET bonus = bonus + excluded.bonus
    """, (account, today, extra))
    conn.commit()
    conn.close()
    return get_ai_guard_quota(account, daily_limit)

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

# =========================================================================
# 傳情小站聊天紀錄
# =========================================================================
def add_family_message(msg: dict):
    conn = get_db()
    conn.execute(
        """INSERT INTO chat_messages (id, owner_account, elder, sender, content, type, timestamp, from_role)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (msg["id"], msg.get("owner_account") or "", msg.get("elder") or "", msg.get("sender") or "",
         msg.get("content") or "", msg.get("type") or "text", msg.get("timestamp") or "", msg.get("from_role") or "family")
    )
    conn.commit()
    conn.close()
    return msg

def list_family_messages(owner_account: str, elder: str = "", limit: int = 300):
    """只回傳「這個帳號 × 這位親友」的對話，新訊息在前"""
    conn = get_db()
    sql = "SELECT * FROM chat_messages WHERE owner_account = ?"
    params = [owner_account]
    if elder:
        sql += " AND elder = ?"
        params.append(elder)
    sql += " ORDER BY timestamp DESC, rowid DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def latest_family_card(owner_account: str, elder: str):
    conn = get_db()
    row = conn.execute(
        """SELECT * FROM chat_messages WHERE owner_account = ? AND elder = ? AND type = 'card'
           ORDER BY timestamp DESC, rowid DESC LIMIT 1""",
        (owner_account, elder)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_database_stats():
    conn = get_db()
    cursor = conn.cursor()
    tables = ["users", "recipients", "orders", "points_ledger", "pharmacy_cache", "recommendation_products", "clinical_knowledge", "system_config", "cashback_orders", "ai_guard_usage", "chat_messages"]
    counts = {}
    for t in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            counts[t] = cursor.fetchone()[0]
        except Exception:
            counts[t] = 0
    conn.close()
    if USE_TURSO:
        return {
            "db_name": "Turso 雲端資料庫",
            "db_path": "turso",
            "db_size_kb": "-",
            "status": "connected",
            "persistent": True,
            "counts": counts
        }
    file_size_kb = round(os.path.getsize(DB_PATH) / 1024, 1) if os.path.exists(DB_PATH) else 0
    return {
        "db_name": "caregift.db",
        "db_path": DB_PATH,
        "db_size_kb": file_size_kb,
        "persistent": False,
        "status": "connected",
        "counts": counts
    }

def update_user_profile_in_db(account: str, name: str, phone: str, birthday: str, bio: str, avatar: str = None):
    conn = get_db()
    try:
        if avatar is None:
            conn.execute(
                "UPDATE users SET name = ?, phone = ?, birthday = ?, bio = ? WHERE account = ? OR email = ?",
                (name, phone, birthday, bio, account, account)
            )
        else:
            conn.execute(
                "UPDATE users SET name = ?, phone = ?, birthday = ?, bio = ?, avatar = ? WHERE account = ? OR email = ?",
                (name, phone, birthday, bio, avatar, account, account)
            )
        conn.commit()
        return True
    except Exception as e:
        print("更新會員資料失敗:", e)
        return False
    finally:
        conn.close()

def get_user_profile_by_account(account: str):
    return get_user_profile(account)

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

# =========================================================================
# LINE 個人帳號綁定（綁定碼）
# =========================================================================
LINE_BIND_CODE_TTL_HOURS = 24

def create_line_bind_code(rec_id: str):
    """為指定親友產生 6 位數綁定碼（24 小時內有效），親友在 LINE 傳「綁定 123456」即可綁定"""
    import random as _random
    rng = _random.SystemRandom()
    now = datetime.now()
    expires = (now + timedelta(hours=LINE_BIND_CODE_TTL_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    for _ in range(20):
        code = f"{rng.randint(0, 999999):06d}"
        clash = conn.execute(
            "SELECT 1 FROM recipients WHERE line_bind_code = ? AND line_bind_expires > ?",
            (code, now.strftime("%Y-%m-%d %H:%M:%S"))
        ).fetchone()
        if not clash:
            break
    conn.execute("UPDATE recipients SET line_bind_code = ?, line_bind_expires = ? WHERE id = ?", (code, expires, rec_id))
    conn.commit()
    conn.close()
    return {"code": code, "expires_at": expires}

def bind_line_by_code(code: str, line_user_id: str):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM recipients WHERE line_bind_code = ? AND line_bind_expires > ?", (code, now_str)
    ).fetchone()
    if not row:
        conn.close()
        return None
    # 同一個 LINE 帳號只對應一位親友：先解除其他親友身上的舊綁定，避免訊息存到錯的對話
    conn.execute(
        "UPDATE recipients SET line_user_id = NULL WHERE line_user_id = ? AND id != ?",
        (line_user_id, row["id"])
    )
    conn.execute(
        "UPDATE recipients SET line_user_id = ?, line_bind_code = NULL, line_bind_expires = NULL WHERE id = ?",
        (line_user_id, row["id"])
    )
    conn.commit()
    owner = conn.execute("SELECT name FROM users WHERE account = ?", (row["user_account"],)).fetchone()
    conn.close()
    rec = _recipient_row_to_dict(row)
    rec["owner_name"] = owner["name"] if owner and owner["name"] else ""
    return rec

def unbind_recipient_line(rec_id: str):
    conn = get_db()
    conn.execute("UPDATE recipients SET line_user_id = NULL, line_bind_code = NULL, line_bind_expires = NULL WHERE id = ?", (rec_id,))
    conn.commit()
    conn.close()

def find_recipient_line_id(elder_name: str, owner_account: str = ""):
    """找出要推播的 LINE ID：只比對寄件者帳號底下的親友，避免推給其他使用者的同名親友"""
    if not owner_account:
        return None
    conn = get_db()
    row = conn.execute(
        "SELECT line_user_id FROM recipients WHERE name = ? AND user_account = ? AND line_user_id IS NOT NULL",
        (elder_name, owner_account)
    ).fetchone()
    conn.close()
    return row["line_user_id"] if row else None

def get_line_binding_info(line_user_id: str):
    """依 LINE ID 取得綁定的親友資料與守護家人的顯示名稱；未綁定回傳 None"""
    conn = get_db()
    row = conn.execute(
        """SELECT r.id, r.name, r.condition, r.user_account, u.name AS owner_name
           FROM recipients r LEFT JOIN users u ON u.account = r.user_account
           WHERE r.line_user_id = ?
           ORDER BY CASE WHEN COALESCE(r.user_account, '') = '' THEN 1 ELSE 0 END, r.rowid DESC""",
        (line_user_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    info = dict(row)
    info["owner_name"] = info.get("owner_name") or "家人"
    return info

def find_recipient_name_by_line_id(line_user_id: str):
    conn = get_db()
    row = conn.execute("SELECT name FROM recipients WHERE line_user_id = ?", (line_user_id,)).fetchone()
    conn.close()
    return row["name"] if row else None

# =========================================================================
# 回饋點數規則（由後端控管次數上限）
# 參考蝦皮蝦幣與 ShopBack：1 點折抵 $1，點數主要來自購物回饋；
# 註冊與日常互動只給小額點數，避免一開始就能折抵太多
# =========================================================================
REWARD_RULES = {
    # 發送關懷卡：每位親友每天 +0.1，每天最多 5 張（每天最多 0.5 點）
    "care_card": {"amount": 0.1, "title": "發送關懷卡：給【{recipient}】", "daily_cap": 5},
    # 與小熊互動：每週 +0.5
    "mascot_weekly": {"amount": 0.5, "title": "小熊每週關懷加碼"},
}

def claim_reward(account: str, action: str, recipient: str = ""):
    rule = REWARD_RULES.get(action)
    if not rule:
        return {"success": False, "awarded": 0, "message": "未知的回饋項目"}

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    if action == "care_card":
        claim_key = f"care_card:{today}:{recipient}"
    else:
        iso_year, iso_week, _ = now.isocalendar()
        claim_key = f"mascot_weekly:{iso_year}-W{iso_week:02d}"

    conn = get_db()
    if conn.execute("SELECT 1 FROM reward_claims WHERE account = ? AND claim_key = ?", (account, claim_key)).fetchone():
        conn.close()
        msg = "今天已經送過這位親友的關懷卡點數囉！" if action == "care_card" else "本週的小熊加碼已經領過囉！"
        return {"success": True, "awarded": 0, "message": msg}

    daily_cap = rule.get("daily_cap")
    if daily_cap:
        used = conn.execute(
            "SELECT COUNT(*) FROM reward_claims WHERE account = ? AND claim_key LIKE ?", (account, f"{action}:{today}:%")
        ).fetchone()[0]
        if used >= daily_cap:
            conn.close()
            return {"success": True, "awarded": 0, "message": f"今天的關懷卡點數已達上限（{daily_cap} 張）"}

    conn.execute("INSERT INTO reward_claims (account, claim_key, amount) VALUES (?, ?, ?)", (account, claim_key, rule["amount"]))
    conn.commit()
    conn.close()

    add_points_transaction(account, rule["amount"], rule["title"].format(recipient=recipient or "親友"))
    return {"success": True, "awarded": rule["amount"], "message": f"獲得 {format_points(rule['amount'])} 點關懷回饋！"}

# =========================================================================
# 購物回饋（ShopBack 模式）：透過 GiftSense 前往藥局購物，確認購物後依金額回饋點數
# 目前尚未與藥局正式合作，「完成購物」與「藥局確認」由模擬操作觸發
# =========================================================================
CASHBACK_RATES = {"大樹藥局": 0.05, "杏一醫療": 0.04, "啄木鳥藥局": 0.03, "丁丁藥局": 0.03}
CASHBACK_DEFAULT_RATE = 0.03
POINTS_PER_CASHBACK_DOLLAR = 1  # 回饋金額每 1 元換算的點數
CASHBACK_STATUS_TEXT = {
    "tracked": "追蹤中",
    "pending": "回饋待確認",
    "confirmed": "已入帳",
    "rejected": "訂單取消",
}

def cashback_rate_for(pharmacy: str) -> float:
    for name, rate in CASHBACK_RATES.items():
        if name in (pharmacy or "") or (pharmacy or "") in name:
            return rate
    return CASHBACK_DEFAULT_RATE

def calc_cashback_points(amount: int, rate: float) -> int:
    return int(round(max(0, amount) * rate * POINTS_PER_CASHBACK_DOLLAR))

def _cashback_row(row):
    d = dict(row)
    d["status_text"] = CASHBACK_STATUS_TEXT.get(d["status"], d["status"])
    d["rate_percent"] = round(d["rate"] * 100, 1)
    d["est_points"] = calc_cashback_points(d.get("order_amount") or d.get("est_price") or 0, d["rate"])
    return d

def create_cashback_click(account: str, pharmacy: str, product_name: str, est_price: int = 0, recipient: str = "", official_url: str = ""):
    now = datetime.now()
    click_id = f"CB{now.strftime('%Y%m%d%H%M%S')}{int(now.microsecond / 1000):03d}"
    rate = cashback_rate_for(pharmacy)
    conn = get_db()
    conn.execute(
        """INSERT INTO cashback_orders (id, account, recipient, pharmacy, product_name, est_price, rate, status, official_url, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'tracked', ?, ?)""",
        (click_id, account, recipient, pharmacy, product_name, int(est_price or 0), rate, official_url, now.strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    row = conn.execute("SELECT * FROM cashback_orders WHERE id = ?", (click_id,)).fetchone()
    conn.close()
    return _cashback_row(row)

def list_cashback_orders(account: str):
    conn = get_db()
    rows = conn.execute("SELECT * FROM cashback_orders WHERE account = ? ORDER BY created_at DESC", (account,)).fetchall()
    conn.close()
    orders = [_cashback_row(r) for r in rows]
    return {
        "orders": orders,
        "summary": {
            "tracked": sum(1 for o in orders if o["status"] == "tracked"),
            "pending_points": sum(o["points"] for o in orders if o["status"] == "pending"),
            "confirmed_points": sum(o["points"] for o in orders if o["status"] == "confirmed"),
        },
    }

def _get_cashback_for_account(order_id: str, account: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM cashback_orders WHERE id = ? AND account = ?", (order_id, account)).fetchone()
    conn.close()
    return row

def simulate_cashback_purchase(order_id: str, account: str, amount: int = 0):
    """模擬藥局回傳「已完成購物」：記錄訂單金額，回饋進入待確認"""
    row = _get_cashback_for_account(order_id, account)
    if not row:
        return None, "找不到這筆購物追蹤紀錄"
    if row["status"] != "tracked":
        return _cashback_row(row), f"這筆紀錄目前是「{CASHBACK_STATUS_TEXT[row['status']]}」，無法再次回報購物"
    amount = int(amount or row["est_price"] or 0)
    if amount <= 0:
        return _cashback_row(row), "請輸入購物金額"
    points = calc_cashback_points(amount, row["rate"])
    conn = get_db()
    conn.execute(
        "UPDATE cashback_orders SET status = 'pending', order_amount = ?, points = ?, purchased_at = ? WHERE id = ?",
        (amount, points, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), order_id)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM cashback_orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return _cashback_row(row), None

def settle_cashback(order_id: str, account: str, approve: bool = True):
    """模擬藥局確認訂單：approve=True 回饋點數入帳；False 視為訂單取消、不給點"""
    row = _get_cashback_for_account(order_id, account)
    if not row:
        return None, "找不到這筆購物追蹤紀錄"
    allowed = ("pending",) if approve else ("tracked", "pending")
    if row["status"] not in allowed:
        return _cashback_row(row), f"這筆紀錄目前是「{CASHBACK_STATUS_TEXT[row['status']]}」，無法執行此操作"
    new_status = "confirmed" if approve else "rejected"
    conn = get_db()
    # 以狀態做條件更新，避免重複入帳
    cur = conn.execute(
        "UPDATE cashback_orders SET status = ?, settled_at = ? WHERE id = ? AND status = ?",
        (new_status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), order_id, row["status"])
    )
    conn.commit()
    updated = cur.rowcount == 1
    row = conn.execute("SELECT * FROM cashback_orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    if approve and updated and row["points"] > 0:
        add_points_transaction(
            account, row["points"],
            f"購物回饋：{row['pharmacy']}（訂單 ${row['order_amount']:,} × {round(row['rate'] * 100, 1)}%）"
        )
    return _cashback_row(row), None

init_db()
