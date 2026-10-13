import sqlite3
import json
import os
import time
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "caregift.db")

# 💡 關懷推薦商品預設資料（首次啟動時寫入 recommendation_products 表）
DEFAULT_RECOMMENDATION_PRODUCTS = [
    {
        "id": "rec_quaker_01",
        "product_name": "【桂格完膳】營養素無糖低 GI 高鈣配方 (24罐/箱)",
        "sku": "GT-Q109",
        "ean_13": "4710043022131",
        "category": "親友滋補 / 零撞藥首選",
        "spec": "250ml x 24罐/箱",
        "search_kw": "桂格完膳",
        "match_conditions": ["warfarin", "抗凝血", "血壓", "心血管", "糖", "日常"],
        "match_reason": "經臨床 RAG 審核：零抗凝血活血成分，無糖低 GI，高血壓與 Warfarin 患者首選滋補配方！",
        "recommended_pharmacy": "大樹藥局",
        "best_price": 1480,
        "official_url": "https://shop.greattree.com.tw/searchlist?keyword=%E6%A1%82%E6%A0%BC%E5%AE%8C%E8%86%B3",
        "pharmacy_comparison": [
            {"pharmacy": "大樹藥局", "price": 1480, "is_lowest": True, "badge": "官方最低價", "url": "https://shop.greattree.com.tw/searchlist?keyword=%E6%A1%82%E6%A0%BC%E5%AE%8C%E8%86%B3"},
            {"pharmacy": "杏一醫療", "price": 1499, "is_lowest": False, "badge": "門市正品", "url": "https://www.medfirst.com.tw/v2/Search?q=%E6%A1%82%E6%A0%BC%E5%AE%8C%E8%86%B3"},
            {"pharmacy": "啄木鳥藥局", "price": 1520, "is_lowest": False, "badge": "原廠箱裝", "url": "https://www.woodpecker.com.tw/products_search/all/1?PdSearch=%E6%A1%82%E6%A0%BC%E5%AE%8C%E8%86%B3"},
            {"pharmacy": "丁丁藥局", "price": 1550, "is_lowest": False, "badge": "快速出貨", "url": "https://www.norbelbaby.com.tw/nec/search?keyword=%E6%A1%82%E6%A0%BC%E5%AE%8C%E8%86%B3"}
        ]
    },
    {
        "id": "rec_glucosamine_01",
        "product_name": "【挺立】關鍵 UC-II 葡萄糖胺加強配方 (30錠/盒)",
        "sku": "MF-V180",
        "ean_13": "4710018151026",
        "category": "骨骼關節 / ESCEO 臨床首選",
        "spec": "30錠/盒 (非變性二型膠原蛋白+葡萄糖胺)",
        "search_kw": "葡萄糖胺",
        "match_conditions": ["膝蓋", "關節", "骨折", "骨質", "痛", "跌倒", "日常", "warfarin", "抗凝血", "血壓"],
        "match_reason": "符合 ESCEO 骨關節醫學會指引：非變性二型膠原蛋白協同葡萄糖胺，無心血管與抗凝血衝突。",
        "recommended_pharmacy": "大樹藥局",
        "best_price": 1550,
        "official_url": "https://shop.greattree.com.tw/searchlist?keyword=%E8%91%A3%E8%90%84%E9%85%B6%E8%83%B6",
        "pharmacy_comparison": [
            {"pharmacy": "大樹藥局", "price": 1550, "is_lowest": True, "badge": "限時特惠", "url": "https://shop.greattree.com.tw/searchlist?keyword=%E8%91%A3%E8%90%84%E9%85%B6%E8%83%B6"},
            {"pharmacy": "杏一醫療", "price": 1580, "is_lowest": False, "badge": "醫學中心合約", "url": "https://www.medfirst.com.tw/v2/Search?q=%E8%91%A3%E8%90%84%E9%85%B6%E8%83%B6"},
            {"pharmacy": "啄木鳥藥局", "price": 1590, "is_lowest": False, "badge": "門市現貨", "url": "https://www.woodpecker.com.tw/products_search/all/1?PdSearch=%E8%91%A3%E8%90%84%E9%85%B6%E8%83%B6"},
            {"pharmacy": "丁丁藥局", "price": 1620, "is_lowest": False, "badge": "官方直售", "url": "https://www.norbelbaby.com.tw/nec/search?keyword=%E8%91%A3%E8%90%84%E9%85%B6%E8%83%B6"}
        ]
    },
    {
        "id": "rec_calcium_01",
        "product_name": "【挺立】鈣強力錠 + 活性維生素 D3 (60錠/盒)",
        "sku": "GT-C060",
        "ean_13": "4710018151019",
        "category": "骨密維護 / NOF 臨床指引",
        "spec": "60錠/盒 (高吸收檸檬酸鈣)",
        "search_kw": "挺立",
        "match_conditions": ["骨質", "骨折", "抽筋", "關節", "膝蓋", "日常", "warfarin", "抗凝血", "血壓"],
        "match_reason": "美國骨質疏鬆學會 (NOF) 建議：鈣+D3 協同吸收，有效維持骨質密度，無藥物衝突。",
        "recommended_pharmacy": "大樹藥局",
        "best_price": 499,
        "official_url": "https://shop.greattree.com.tw/searchlist?keyword=%E6%8C%BA%E7%AB%8B",
        "pharmacy_comparison": [
            {"pharmacy": "大樹藥局", "price": 499, "is_lowest": True, "badge": "會員破盤價", "url": "https://shop.greattree.com.tw/searchlist?keyword=%E6%8C%BA%E7%AB%8B"},
            {"pharmacy": "杏一醫療", "price": 520, "is_lowest": False, "badge": "官方正品", "url": "https://www.medfirst.com.tw/v2/Search?q=%E6%8C%BA%E7%AB%8B"},
            {"pharmacy": "丁丁藥局", "price": 535, "is_lowest": False, "badge": "連鎖直營", "url": "https://www.norbelbaby.com.tw/nec/search?keyword=%E6%8C%BA%E7%AB%8B"},
            {"pharmacy": "啄木鳥藥局", "price": 550, "is_lowest": False, "badge": "門市供應", "url": "https://www.woodpecker.com.tw/products_search/all/1?PdSearch=%E6%8C%BA%E7%AB%8B"}
        ]
    },
    {
        "id": "rec_lutein_01",
        "product_name": "【永信藥品】活泉游離型葉黃素 30mg + 玉米黃素 (60粒/瓶)",
        "sku": "NB-L060",
        "ean_13": "4711928001221",
        "category": "視力保養 / AREDS 2 指引",
        "spec": "60粒/瓶 (黃金比例 10:2)",
        "search_kw": "葉黃素",
        "match_conditions": ["眼", "視力", "白內障", "黃斑", "日常", "糖", "糖尿病"],
        "match_reason": "符合美國國家衛生院 (NIH) AREDS 2 臨床指引：游離型高吸收率，保養黃斑部與視網膜微血管。",
        "recommended_pharmacy": "丁丁藥局",
        "best_price": 980,
        "official_url": "https://www.norbelbaby.com.tw/nec/search?keyword=%E8%91%89%E9%BB%83%E7%B4%A0",
        "pharmacy_comparison": [
            {"pharmacy": "丁丁藥局", "price": 980, "is_lowest": True, "badge": "最低優惠價", "url": "https://www.norbelbaby.com.tw/nec/search?keyword=%E8%91%89%E9%BB%83%E7%B4%A0"},
            {"pharmacy": "杏一醫療", "price": 1050, "is_lowest": False, "badge": "門市正品", "url": "https://www.medfirst.com.tw/v2/Search?q=%E8%91%89%E9%BB%83%E7%B4%A0"},
            {"pharmacy": "大樹藥局", "price": 1080, "is_lowest": False, "badge": "官方直銷", "url": "https://shop.greattree.com.tw/searchlist?keyword=%E8%91%89%E9%BB%83%E7%B4%A0"},
            {"pharmacy": "啄木鳥藥局", "price": 1100, "is_lowest": False, "badge": "常態供應", "url": "https://www.woodpecker.com.tw/products_search/all/1?PdSearch=%E8%91%89%E9%BB%83%E7%B4%A0"}
        ]
    },
    {
        "id": "rec_probiotics_01",
        "product_name": "【日本味王】消化專利複合益生菌 (60包/盒)",
        "sku": "GT-P060",
        "ean_13": "4712857002013",
        "category": "腸道健康 / WGO 益生菌指引",
        "spec": "60包/盒 (200億活菌)",
        "search_kw": "益生菌",
        "match_conditions": ["腸", "便秘", "排便", "胃", "消化", "日常", "糖", "糖尿病"],
        "match_reason": "符合世界胃腸病學組織 (WGO) 指引：調節腸道菌相、幫助消化，親友無腸胃負擔。",
        "recommended_pharmacy": "大樹藥局",
        "best_price": 790,
        "official_url": "https://shop.greattree.com.tw/searchlist?keyword=%E7%9B%8A%E7%94%9F%E8%8F%80",
        "pharmacy_comparison": [
            {"pharmacy": "大樹藥局", "price": 790, "is_lowest": True, "badge": "獨家最低價", "url": "https://shop.greattree.com.tw/searchlist?keyword=%E7%9B%8A%E7%94%9F%E8%8F%80"},
            {"pharmacy": "啄木鳥藥局", "price": 820, "is_lowest": False, "badge": "現貨提供", "url": "https://www.woodpecker.com.tw/products_search/all/1?PdSearch=%E7%9B%8A%E7%94%9F%E8%8F%80"},
            {"pharmacy": "丁丁藥局", "price": 850, "is_lowest": False, "badge": "門市正品", "url": "https://www.norbelbaby.com.tw/nec/search?keyword=%E7%9B%8A%E7%94%9F%E8%8F%80"},
            {"pharmacy": "杏一醫療", "price": 880, "is_lowest": False, "badge": "醫材門市", "url": "https://www.medfirst.com.tw/v2/Search?q=%E7%9B%8A%E7%94%9F%E8%8F%80"}
        ]
    },
    {
        "id": "rec_gaba_01",
        "product_name": "【三得利】芝麻明 EX + GABA (90錠/瓶)",
        "sku": "MF-S090",
        "ean_13": "4901777252011",
        "category": "睡眠調節 / AASM 指引",
        "spec": "90錠/瓶 (日本原裝進口)",
        "search_kw": "芝麻明",
        "match_conditions": ["睡", "失眠", "焦慮", "放鬆", "熬夜", "疲勞", "精神", "日常"],
        "match_reason": "結合 GABA 與高濃度芝麻素，幫助中樞神經放鬆，改善親友淺眠，無安眠藥成癮性。",
        "recommended_pharmacy": "杏一醫療",
        "best_price": 1600,
        "official_url": "https://www.medfirst.com.tw/v2/Search?q=%E8%8A%9D%E9%BA%BB%E6%98%8E",
        "pharmacy_comparison": [
            {"pharmacy": "杏一醫療", "price": 1600, "is_lowest": True, "badge": "官方直銷最優", "url": "https://www.medfirst.com.tw/v2/Search?q=%E8%8A%9D%E9%BA%BB%E6%98%8E"},
            {"pharmacy": "大樹藥局", "price": 1650, "is_lowest": False, "badge": "官方正品", "url": "https://shop.greattree.com.tw/searchlist?keyword=%E8%8A%9D%E9%BA%BB%E6%98%8E"},
            {"pharmacy": "啄木鳥藥局", "price": 1680, "is_lowest": False, "badge": "門市代購", "url": "https://www.woodpecker.com.tw/products_search/all/1?PdSearch=%E8%8A%9D%E9%BA%BB%E6%98%8E"},
            {"pharmacy": "丁丁藥局", "price": 1700, "is_lowest": False, "badge": "現貨速配", "url": "https://www.norbelbaby.com.tw/nec/search?keyword=%E8%8A%9D%E9%BA%BB%E6%98%8E"}
        ]
    }
]

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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

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
        ("social_id", "TEXT")
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
            best_price, official_url, pharmacy_comparison_json, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            1
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
        products.append(d)
    return products

def match_recommendation_products(condition: str = ""):
    """依病況比對推薦商品；沒有對應商品時回傳一般日常保養商品並標記 is_fallback"""
    cond = (condition or "").lower().strip()
    items = get_all_recommendation_products()
    matched = []
    if cond:
        for item in items:
            terms = [t for t in (item.get("match_conditions") or []) if t and t != "日常"]
            if any(t.lower() in cond or cond in t.lower() for t in terms):
                matched.append(item)
    if matched:
        return {"products": matched, "is_fallback": False}
    # 「日常養生」本來就是一般保養，不算找不到對應商品
    return {"products": items[:3], "is_fallback": "日常" not in cond}

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
    # 💡 一律註冊為一般會員，避免帳號含 admin 或前端傳 role 就取得管理員權限
    assigned_role = "user"
    initial_points = 100

    # 點數先寫 0，再由下方的點數交易加上註冊獎勵（避免重複計算成 200 點）
    conn.execute("""
    INSERT INTO users (id, account, password_hash, name, role, points, email, created_at)
    VALUES (?, ?, ?, ?, ?, 0, ?, CURRENT_TIMESTAMP)
    """, (user_id, account, password_raw, display_name, assigned_role, account))
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

def _public_user(row):
    user = dict(row)
    user.pop("password_hash", None)
    return user

def find_or_create_social_user(provider: str, social_id: str, email: str = "", email_verified: bool = False, name: str = ""):
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
            """INSERT INTO users (id, account, name, email, auth_provider, social_id, role, points, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'user', 0, CURRENT_TIMESTAMP)""",
            (user_id, account, display_name, email if not email_taken else "", provider, social_id)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        created = True

    conn.close()
    if created:
        add_points_transaction(row["account"], 100, "新會員註冊獎勵")
        return {**get_user_profile(row["account"]), "is_new_user": True}
    return _public_user(row)

def get_user_profile(account: str):
    conn = get_db()
    row = conn.execute("SELECT id, account, name, role, points, phone, birthday, bio, avatar, created_at, email, auth_provider FROM users WHERE account = ? OR email = ?", (account, account)).fetchone()
    conn.close()
    return dict(row) if row else None

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
    rec_id = f"rec_{int(datetime.now().timestamp() * 1000)}"
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

def get_database_stats():
    conn = get_db()
    cursor = conn.cursor()
    tables = ["users", "recipients", "orders", "points_ledger", "pharmacy_cache", "recommendation_products", "clinical_knowledge", "system_config"]
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
           WHERE r.line_user_id = ?""",
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
# =========================================================================
REWARD_RULES = {
    # 發送關懷卡：每位親友每天 +10，每天最多 5 張
    "care_card": {"amount": 10, "title": "發送關懷卡：給【{recipient}】", "daily_cap": 5},
    # 與小熊互動：每週 +50
    "mascot_weekly": {"amount": 50, "title": "小熊每週關懷加碼"},
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
    return {"success": True, "awarded": rule["amount"], "message": f"獲得 {rule['amount']} 點關懷回饋！"}

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
