"""
GiftSense 資料存取層（SQLAlchemy ORM）

資料表定義在 models.py，連線設定在 db_engine.py：
- 設定 DATABASE_URL：Microsoft SQL Server（或其他 SQLAlchemy 支援的資料庫）
- 設定 TURSO_DATABASE_URL：Turso 雲端資料庫
- 都沒有：本機 SQLite 檔案（CAREGIFT_DB_PATH，預設 backend/caregift.db）
這裡的函式名稱與回傳格式和改用 ORM 之前相同，main.py 等呼叫端不需要知道是哪一種資料庫。
"""
import json
import hmac
import os
import re
import time
import uuid
from contextlib import contextmanager

import bcrypt
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, MetaData, Table, case, delete, func, insert, inspect, literal, or_, select, text, update
from sqlalchemy.exc import IntegrityError

# 💡 伺服器一律使用台灣時間（Render 預設是 UTC，會讓 LINE 訊息時間慢 8 小時、聊天排序錯亂）
#    使用 POSIX 時區字串 CST-8（UTC+8、台灣無日光節約），不依賴系統是否安裝時區資料
os.environ["TZ"] = "CST-8"
if hasattr(time, "tzset"):
    time.tzset()

import db_engine
from db_transfer import chat_seq_from, copy_database, target_is_empty
from models import (
    TIME_FMT, AiGuardUsage, Base, CashbackOrder, ChatMessage, ClinicalKnowledge, Order, PharmacyCache,
    PointsLedger, RecommendationProduct, Recipient, RewardClaim, SystemConfig, User, now_str,
)
# 💡 暖心選物商品資料（藥局官網實際查價）統一放在 product_catalog.py，init_db 啟動時同步寫入
from product_catalog import DEFAULT_RECOMMENDATION_PRODUCTS

# CAREGIFT_DB_PATH：測試時指向一份暫存的資料庫副本，不動到 repo 內附的 caregift.db
DB_PATH = os.getenv("CAREGIFT_DB_PATH") or db_engine.DEFAULT_SQLITE_PATH
USE_TURSO = db_engine.is_turso_configured()

engine = None
SessionLocal = None
_engine_key = None


def _setup_engine():
    """建立（或在測試改了 DB_PATH 後重建）資料庫連線"""
    global engine, SessionLocal, _engine_key
    key = (os.getenv("DATABASE_URL", "").strip(), USE_TURSO, DB_PATH)
    if engine is not None and key == _engine_key:
        return
    if engine is not None:
        engine.dispose()
    engine = db_engine.build_engine(DB_PATH)
    SessionLocal = db_engine.make_session_factory(engine)
    _engine_key = key


@contextmanager
def _session():
    """一次資料庫工作：成功時 commit，發生例外時 rollback"""
    _setup_engine()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _as_dict(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}


# =========================================================================
# 給測試與維護腳本使用的簡易 SQL 介面（介面與 sqlite3 相同：? 參數、row["欄位"]、commit/close）
# 正式功能一律使用上方的 ORM，不要在這裡加商業邏輯
# =========================================================================
class _CompatRow:
    """與 sqlite3.Row 相同：row[0]、row["欄位"]、dict(row) 都可以"""

    def __init__(self, row):
        self._row = row
        self._map = row._mapping

    def __getitem__(self, key):
        return self._row[key] if isinstance(key, int) else self._map[key]

    def keys(self):
        return list(self._map.keys())

    def __iter__(self):
        return iter(self._row)

    def __len__(self):
        return len(self._row)


class _CompatResult:
    def __init__(self, result):
        self._result = result

    def fetchone(self):
        if not self._result.returns_rows:
            return None
        row = self._result.fetchone()
        return _CompatRow(row) if row is not None else None

    def fetchall(self):
        if not self._result.returns_rows:
            return []
        return [_CompatRow(r) for r in self._result.fetchall()]

    @property
    def rowcount(self):
        return self._result.rowcount


class _CompatConnection:
    def __init__(self):
        _setup_engine()
        self._conn = engine.connect()
        self._tx = self._conn.begin()

    @staticmethod
    def _named(sql: str, params):
        if isinstance(params, dict):
            return sql, params
        names = {}
        parts = sql.split("?")
        out = parts[0]
        for i, part in enumerate(parts[1:]):
            names[f"p{i}"] = params[i]
            out += f":p{i}" + part
        return out, names

    def execute(self, sql, params=()):
        sql, named = self._named(sql, params or ())
        return _CompatResult(self._conn.execute(text(sql), named))

    def cursor(self):
        return self

    def commit(self):
        self._tx.commit()
        self._tx = self._conn.begin()

    def rollback(self):
        self._tx.rollback()
        self._tx = self._conn.begin()

    def close(self):
        if self._tx.is_active:
            self._tx.rollback()  # 與 sqlite3 相同：沒有 commit 就關閉，變更不會保留
        self._conn.close()


def get_db():
    return _CompatConnection()


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


def _account_match(model, account: str):
    """會員可用帳號或 email 識別"""
    return or_(model.account == account, model.email == account)


# =========================================================================
# 初始化：建立資料表、補齊舊資料庫的欄位、一次性資料遷移、內建資料同步
# =========================================================================
def _bootstrap_empty_database():
    """第一次連上空的 SQL Server／Turso 時匯入初始資料：
    改用 SQL Server 時若仍設定 Turso，就把 Turso 上的全部資料搬過來；否則匯入 repo 內附的 caregift.db"""
    if engine.dialect.name == "sqlite" and engine.url.drivername != "sqlite+turso":
        return  # 本機 SQLite 檔案本身就是資料
    if not target_is_empty(engine):
        return
    source = db_engine.turso_source_engine() if engine.dialect.name != "sqlite" else None
    label = "Turso"
    if source is None:
        if not os.path.exists(DB_PATH):
            return
        source = db_engine.sqlite_file_engine(DB_PATH)
        label = os.path.basename(DB_PATH)
    try:
        print(f"【資料庫】目標資料庫是空的，從 {label} 匯入初始資料：")
        copy_database(source, engine)
    except Exception as e:
        # 匯入失敗時停止啟動：若繼續以空資料庫運作，下次啟動就不會再匯入，舊資料等於遺失
        raise RuntimeError(f"從 {label} 匯入初始資料失敗，請修正後重新啟動（目標資料庫維持空白）：{e}") from e
    finally:
        source.dispose()


def _ensure_columns():
    """舊版資料庫（例如早期的 caregift.db、Turso）缺少的欄位自動補上，既有資料不變"""
    insp = inspect(engine)
    dialect = engine.dialect
    preparer = dialect.identifier_preparer
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                ddl = f"ALTER TABLE {preparer.quote(table.name)} ADD "
                if dialect.name == "sqlite":
                    ddl += "COLUMN "
                ddl += f"{preparer.quote(col.name)} {col.type.compile(dialect=dialect)}"
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                if isinstance(default, str):
                    ddl += " DEFAULT '" + default.replace("'", "''") + "'"
                elif isinstance(default, (int, float)):
                    ddl += f" DEFAULT {default}"
                if default is not None and dialect.name == "mssql":
                    ddl += " WITH VALUES"
                conn.execute(text(ddl))


def _migration_done(session, key: str) -> bool:
    return session.get(SystemConfig, key) is not None


def _mark_migration(session, key: str, **extra):
    session.merge(SystemConfig(key=key, value_json=json.dumps({"done_at": now_str(), **extra}), updated_at=now_str()))


def _archive_and_clear(session, model):
    """把資料表內容複製到 <資料表>_archive 保留備查，再清空原資料表"""
    src = model.__table__
    archive = Table(f"{src.name}_archive", MetaData(), *[Column(c.name, c.type) for c in src.columns])
    conn = session.connection()
    archive.create(conn, checkfirst=True)
    archived_cols = {c["name"] for c in inspect(conn).get_columns(archive.name)}
    cols = [c for c in src.columns if c.name in archived_cols]
    conn.execute(insert(archive).from_select([c.name for c in cols], select(*cols)))
    conn.execute(delete(src))


def _run_data_migrations(session):
    # LINE 綁定只對應有家人帳號的親友
    session.execute(
        update(Recipient.__table__)
        .where(func.coalesce(Recipient.user_account, "") == "", Recipient.line_user_id.is_not(None))
        .values(line_user_id=None)
    )

    # 一次性：清除舊的暖幣紀錄與傳情小站聊天紀錄（2026/10/13 使用者要求，避免和新的測試紀錄混在一起）
    # 舊資料移到 *_archive 表保留備查，不直接刪除；會員保留「新會員註冊獎勵 +100」（以新版格式重新記錄），
    # 其餘紀錄歸零後重新累計（管理員帳號的點數不動）
    if not _migration_done(session, "points_reset_20261013"):
        _archive_and_clear(session, ChatMessage)
        _archive_and_clear(session, PointsLedger)
        _archive_and_clear(session, CashbackOrder)
        session.execute(delete(RewardClaim.__table__))
        reset_now = datetime.now()
        bonus_date = reset_now.strftime("%Y/%m/%d")
        bonus_expire = f"{reset_now.year + 3}/{reset_now.strftime('%m/%d')} (剩餘 3 年)"
        not_admin = func.coalesce(User.role, "user") != "admin"
        for (account,) in session.execute(select(User.account).where(not_admin)).all():
            session.add(PointsLedger(account=account, amount=100, title="新會員註冊獎勵", date_str=bonus_date,
                                     expire_str=bonus_expire, type="plus", user_account=account))
        session.execute(update(User.__table__).where(not_admin).values(points=100))
        _mark_migration(session, "points_reset_20261013")

    # 一次性：先前 LINE 回覆的時間是以 UTC 記錄（慢 8 小時），補回台灣時間
    if not _migration_done(session, "chat_tz_fix_20261013"):
        pattern = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        for msg in session.scalars(select(ChatMessage).where(ChatMessage.from_role == "elder")).all():
            if msg.timestamp and pattern.match(msg.timestamp):
                msg.timestamp = (datetime.strptime(msg.timestamp, TIME_FMT) + timedelta(hours=8)).strftime(TIME_FMT)
        _mark_migration(session, "chat_tz_fix_20261013")

    # 一次性：點數改為小額回饋（2026/10/15）。舊紀錄依新規則換算，並把差額反映到會員點數
    if not _migration_done(session, "points_rescale_20261015"):
        rescale = [
            ((PointsLedger.title == "新會員註冊獎勵") & (PointsLedger.amount == 100), 100, SIGNUP_BONUS_POINTS),
            (PointsLedger.title.like("發送關懷卡：%") & (PointsLedger.amount == 10), 10, REWARD_RULES["care_card"]["amount"]),
            ((PointsLedger.title == "小熊每週關懷加碼") & (PointsLedger.amount == 50), 50, REWARD_RULES["mascot_weekly"]["amount"]),
            (PointsLedger.title.like("兌換 AI 守護助理詢問%") & (PointsLedger.amount == -50), -50, -AI_GUARD_REDEEM_COST),
        ]
        for where, old_amount, new_amount in rescale:
            for (account,) in session.execute(select(PointsLedger.account).where(where)).all():
                session.execute(
                    update(User.__table__).where(_account_match(User, account))
                    .values(points=func.round(User.points + (new_amount - old_amount), 2))
                )
            session.execute(update(PointsLedger.__table__).where(where).values(amount=new_amount))
        session.execute(update(RewardClaim.__table__)
                        .where(RewardClaim.claim_key.like("care_card:%"), RewardClaim.amount == 10)
                        .values(amount=REWARD_RULES["care_card"]["amount"]))
        session.execute(update(RewardClaim.__table__)
                        .where(RewardClaim.claim_key.like("mascot_weekly:%"), RewardClaim.amount == 50)
                        .values(amount=REWARD_RULES["mascot_weekly"]["amount"]))
        _mark_migration(session, "points_rescale_20261015")

    # 一次性：補上用藥安全與照護指引文獻（已存在的文獻不覆蓋，保留管理員的編輯）
    if not _migration_done(session, "knowledge_guidance_20261015"):
        try:
            from clinical_guidance import GUIDANCE_LITERATURES
        except ImportError:
            GUIDANCE_LITERATURES = []
        for lit in GUIDANCE_LITERATURES:
            if session.get(ClinicalKnowledge, lit["id"]) is None:
                session.add(_knowledge_from_literature(lit, default_level=""))
        _mark_migration(session, "knowledge_guidance_20261015")

    # 一次性：內建文獻的內容以程式碼為準重新同步（2026/10/15）
    # 資料庫裡的內建文獻是早期匯入的版本（例如標題寫「長輩」），啟動時又以資料庫重建檢索索引，
    # 造成線上檢索結果和程式碼不同。只更新內建文獻 id 的既有資料列，管理員新增的文獻與已刪除的內建文獻都不動
    if not _migration_done(session, "knowledge_sync_20261015"):
        try:
            from vector_store import FULL_CLINICAL_LITERATURES as _builtin_lits
        except Exception as e:
            _builtin_lits = None
            print("Notice: clinical knowledge sync deferred:", e)
        if _builtin_lits:
            for lit in _builtin_lits:
                row = session.get(ClinicalKnowledge, lit["id"])
                if row is not None:
                    fresh = _knowledge_from_literature(lit, default_level="")
                    for col in ("title", "authority", "category", "ingredient", "evidence_level", "recommended_dose",
                                "mechanism", "contraindications", "target_symptoms_json", "citation"):
                        setattr(row, col, getattr(fresh, col))
            _mark_migration(session, "knowledge_sync_20261015")

    # 一次性：快速提問改為依病況分類的新題庫，重新產生每位親友的提問
    if not _migration_done(session, "quick_chips_v2_20261015"):
        try:
            from chips_generator import get_clinical_rule_chips as _rule_chips
            for rec in session.scalars(select(Recipient)).all():
                rec.quick_tags_json = json.dumps(_rule_chips(rec.condition, rec.name), ensure_ascii=False)
            _mark_migration(session, "quick_chips_v2_20261015")
        except Exception as e:
            print("Notice: quick chips refresh deferred:", e)

    # 一次性：傳情小站訊息補上排序值（改用 ORM、支援 SQL Server 後取代 SQLite 專屬的 rowid）
    for msg in session.scalars(select(ChatMessage).where(ChatMessage.seq.is_(None))).all():
        msg.seq = chat_seq_from(msg.id, msg.timestamp)


def _knowledge_from_literature(lit: dict, default_level: str = "Level 1") -> ClinicalKnowledge:
    symptoms = lit.get("targetSymptoms") or lit.get("target_symptoms", [])
    if isinstance(symptoms, str):
        try:
            symptoms = json.loads(symptoms)
        except Exception:
            symptoms = [symptoms]
    return ClinicalKnowledge(
        id=lit["id"],
        title=lit["title"],
        authority=lit.get("authority", ""),
        category=lit.get("category", ""),
        ingredient=lit.get("ingredient", ""),
        evidence_level=lit.get("evidenceLevel") or lit.get("evidence_level") or default_level,
        recommended_dose=lit.get("recommendedDose") or lit.get("recommended_dose", ""),
        mechanism=lit.get("mechanism", ""),
        contraindications=lit.get("contraindications", ""),
        target_symptoms_json=json.dumps(symptoms, ensure_ascii=False),
        citation=lit.get("citation", ""),
    )


def init_db():
    _setup_engine()
    _bootstrap_empty_database()
    Base.metadata.create_all(engine)
    _ensure_columns()

    with _session() as session:
        # 須在下方一次性補入指引文獻之前判斷，否則全新資料庫會只剩指引文獻、略過原本的國家級臨床文獻
        knowledge_was_empty = session.scalar(select(func.count()).select_from(ClinicalKnowledge)) == 0

        _run_data_migrations(session)

        if session.scalar(select(func.count()).select_from(User).where(User.account == "admin")) == 0:
            session.add(User(id="usr_admin", account="admin", password_hash=hash_password("123"),
                             name="系統管理員", role="admin", points=9999))

        # 舊資料的明文密碼一律轉成 bcrypt 雜湊（已是雜湊的不動，可重複執行）
        for user in session.scalars(select(User).where(User.password_hash.is_not(None), User.password_hash != "")).all():
            if not is_password_hash(user.password_hash):
                user.password_hash = hash_password(user.password_hash)

        # 💡 線上環境請在 Render 設定 ADMIN_PASSWORD：啟動時以它覆蓋 admin 密碼（存成雜湊），
        #    避免任何人用 repo 裡公開的預設密碼登入管理後台
        admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
        if admin_password:
            session.flush()
            admin = session.scalar(select(User).where(User.account == "admin"))
            if admin and not verify_password(admin_password, admin.password_hash):
                admin.password_hash = hash_password(admin_password)

        # 為尚未有快速提問晶片的親友自動補上臨床規則晶片
        try:
            from chips_generator import get_clinical_rule_chips
        except Exception:
            get_clinical_rule_chips = lambda c, n: []
        for rec in session.scalars(select(Recipient)).all():
            if not rec.quick_tags_json or rec.quick_tags_json == "[]":
                rec.quick_tags_json = json.dumps(get_clinical_rule_chips(rec.condition, rec.name), ensure_ascii=False)

        # 全新資料庫時預先寫入國家級臨床文獻
        if knowledge_was_empty:
            try:
                from vector_store import FULL_CLINICAL_LITERATURES
                for lit in FULL_CLINICAL_LITERATURES:
                    session.merge(_knowledge_from_literature(lit))
            except Exception as e:
                print("Notice: Clinical knowledge auto-seed deferred:", e)

        # 推薦商品：每次啟動都以預設資料為準（移除不在預設清單的商品，並更新內容）
        default_ids = [p["id"] for p in DEFAULT_RECOMMENDATION_PRODUCTS]
        session.execute(delete(RecommendationProduct.__table__).where(RecommendationProduct.id.not_in(default_ids)))

    save_recommendation_products(DEFAULT_RECOMMENDATION_PRODUCTS)
    _lock_tracked_cashback_prices()


def _lock_tracked_cashback_prices():
    """一次性：舊版「追蹤中」的購物回饋金額是 App 送來的價格，改成商品資料庫的查價；
    查不到查價的商品不提供回饋，直接取消追蹤（需在商品資料同步後執行）"""
    with _session() as session:
        if _migration_done(session, "cashback_locked_price_20261015"):
            return
        orders = session.scalars(select(CashbackOrder).where(CashbackOrder.status == "tracked")).all()
        now = now_str()
        for order in orders:
            offer = find_catalog_price(order.product_name, order.pharmacy)
            if offer:
                order.est_price, order.product_name, order.pharmacy = offer["price"], offer["product_name"], offer["pharmacy"]
            else:
                order.status, order.settled_at = "rejected", now
        _mark_migration(session, "cashback_locked_price_20261015", tracked=len(orders))


# =========================================================================
# 實證文獻（AI 守護助理的檢索來源）
# =========================================================================
def save_clinical_knowledge(item: dict):
    with _session() as session:
        session.merge(_knowledge_from_literature(item))
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
    with _session() as session:
        session.execute(delete(ClinicalKnowledge.__table__))
    batch_save_clinical_knowledge(defaults)
    return get_all_clinical_knowledge()


def get_all_clinical_knowledge():
    with _session() as session:
        rows = session.scalars(select(ClinicalKnowledge).order_by(ClinicalKnowledge.id)).all()
    items = []
    for r in rows:
        d = _as_dict(r)
        try:
            d["targetSymptoms"] = json.loads(d["target_symptoms_json"])
        except Exception:
            d["targetSymptoms"] = []
        d["evidenceLevel"] = d.get("evidence_level", "Level 1")
        d["recommendedDose"] = d.get("recommended_dose", "")
        items.append(d)
    return items


def batch_save_clinical_knowledge(items: list):
    with _session() as session:
        for item in items:
            session.merge(_knowledge_from_literature(item))
    return len(items)


def delete_clinical_knowledge(item_id: str):
    with _session() as session:
        session.execute(delete(ClinicalKnowledge.__table__).where(ClinicalKnowledge.id == item_id))


# =========================================================================
# 藥局商品
# =========================================================================
def save_pharmacy_products(products: list):
    with _session() as session:
        for p in products:
            session.merge(PharmacyCache(
                id=p.get("id") or f"{p['pharmacy']}_{hash(p['product_name'])}",
                pharmacy=p["pharmacy"],
                product_name=p["product_name"],
                price=p["price"],
                spec=p.get("spec", ""),
                url=p.get("url", ""),
                image_url=p.get("image_url", ""),
                in_stock=p.get("in_stock", 1),
                updated_at=now_str(),
            ))


def save_recommendation_products(products: list):
    with _session() as session:
        for p in products:
            if not isinstance(p, dict):
                continue
            session.merge(RecommendationProduct(
                id=p.get("id") or f"rec_{hash(str(p))}",
                product_name=p.get("product_name", ""),
                sku=p.get("sku", ""),
                ean_13=p.get("ean_13", ""),
                category=p.get("category", ""),
                spec=p.get("spec", ""),
                search_kw=p.get("search_kw", ""),
                match_conditions_json=json.dumps(p.get("match_conditions") or [], ensure_ascii=False),
                match_reason=p.get("match_reason", ""),
                recommended_pharmacy=p.get("recommended_pharmacy", ""),
                best_price=int(p.get("best_price") or 0),
                official_url=p.get("official_url", ""),
                pharmacy_comparison_json=json.dumps(p.get("pharmacy_comparison") or [], ensure_ascii=False),
                is_active=1,
                price_checked_at=p.get("price_checked_at", ""),
                primary_conditions_json=json.dumps(p.get("primary_conditions") or [], ensure_ascii=False),
                exclude_conditions_json=json.dumps(p.get("exclude_conditions") or [], ensure_ascii=False),
            ))
    return len(products)


def get_all_recommendation_products():
    with _session() as session:
        rows = session.scalars(
            select(RecommendationProduct).where(RecommendationProduct.is_active == 1)
            .order_by(RecommendationProduct.best_price, RecommendationProduct.id)
        ).all()
    products = []
    for r in rows:
        d = _as_dict(r)
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
    like = f"%{keyword}%"
    with _session() as session:
        rows = session.scalars(
            select(PharmacyCache)
            .where(or_(PharmacyCache.product_name.like(like), PharmacyCache.pharmacy.like(like), PharmacyCache.spec.like(like)))
            .order_by(PharmacyCache.price)
        ).all()
    return [_as_dict(r) for r in rows]


# =========================================================================
# 會員
# =========================================================================
def authenticate_user(account: str, password_raw: str):
    with _session() as session:
        user = session.scalar(select(User).where(_account_match(User, account)))
        if not user or not verify_password(password_raw, user.password_hash):
            return None
        if not is_password_hash(user.password_hash):
            user.password_hash = hash_password(password_raw)
        return {
            "id": user.id,
            "account": user.account,
            "name": user.name,
            "role": user.role,
            "points": round_points(user.points),
            "phone": user.phone,
            "birthday": user.birthday,
            "bio": user.bio,
            "avatar_url": resolve_avatar_url(_as_dict(user)),
        }


def register_user(account: str, password_raw: str, name: str = None, role: str = "user"):
    user_id = f"usr_{int(datetime.now().timestamp() * 1000)}"
    display_name = name if name and name.strip() else account
    # 💡 一律註冊為一般會員，避免帳號含 admin 或前端傳 role 就取得管理員權限
    assigned_role = "user"
    initial_points = SIGNUP_BONUS_POINTS
    try:
        with _session() as session:
            if session.scalar(select(User.id).where(_account_match(User, account))):
                return None
            # 點數先寫 0，再由下方的點數交易加上註冊獎勵（避免重複計算）
            session.add(User(id=user_id, account=account, password_hash=hash_password(password_raw), name=display_name,
                             role=assigned_role, points=0, email=account))
    except IntegrityError:
        return None  # 同時送出兩次註冊：唯一鍵擋下第二筆

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


def _public_user(user: dict):
    user = dict(user)
    user.pop("password_hash", None)
    user["avatar_url"] = resolve_avatar_url(user)
    if "points" in user:
        user["points"] = round_points(user["points"])
    return user


AVATAR_MAX_LENGTH = 450_000  # 約 330KB 圖片（base64）；前端上傳前會先縮到 512px


def set_user_avatar(account: str, image_data_url: str = ""):
    """自行上傳頭貼（data URL）；傳空字串則移除，改回第三方大頭照或預設圖示"""
    value = (image_data_url or "").strip() or "default"
    with _session() as session:
        session.execute(update(User.__table__).where(_account_match(User, account)).values(avatar=value))
        user = session.scalar(select(User).where(_account_match(User, account)))
        return resolve_avatar_url(_as_dict(user)) if user else None


def find_or_create_social_user(provider: str, social_id: str, email: str = "", email_verified: bool = False, name: str = "", picture: str = ""):
    """
    依平台驗證過的身分找出或建立會員：
    1. 先以 (auth_provider, social_id) 比對
    2. 再以「平台已驗證」的 email 比對既有一般會員（不比對 account、不合併管理員）
    3. 都沒有就建立新會員並發放註冊獎勵
    """
    created = False
    with _session() as session:
        user = session.scalar(select(User).where(User.auth_provider == provider, User.social_id == social_id))

        if not user and email and email_verified:
            user = session.scalar(select(User).where(User.email == email, func.coalesce(User.role, "user") != "admin"))
            if user and not user.social_id and user.auth_provider == provider:
                user.social_id = social_id

        if not user:
            email_taken = bool(email) and session.scalar(select(User.id).where(_account_match(User, email))) is not None
            account = email if email and not email_taken else f"{provider}_{social_id}"
            display_name = (name or "").strip() or (email.split("@")[0] if email else f"{provider.capitalize()} 會員")
            user = User(id=f"usr_{int(datetime.now().timestamp() * 1000)}", account=account, name=display_name,
                        email=email if not email_taken else "", auth_provider=provider, social_id=social_id,
                        role="user", points=0, social_avatar_url=picture or "")
            session.add(user)
            created = True
        elif picture and picture != (user.social_avatar_url or ""):
            # 每次登入都同步第三方的最新大頭照
            user.social_avatar_url = picture
        session.flush()
        data = _as_dict(user)

    if created:
        add_points_transaction(data["account"], SIGNUP_BONUS_POINTS, "新會員註冊獎勵")
        return {**get_user_profile(data["account"]), "is_new_user": True}
    return _public_user(data)


_PROFILE_FIELDS = ("id", "account", "name", "role", "points", "phone", "birthday", "bio", "avatar",
                   "social_avatar_url", "created_at", "email", "auth_provider")


def get_user_profile(account: str):
    with _session() as session:
        user = session.scalar(select(User).where(_account_match(User, account)))
        if not user:
            return None
        d = {k: getattr(user, k) for k in _PROFILE_FIELDS}
    d["avatar_url"] = resolve_avatar_url(d)
    d["points"] = round_points(d.get("points"))
    return d


def get_user_profile_by_account(account: str):
    return get_user_profile(account)


def get_user_display_name(account: str) -> str:
    with _session() as session:
        return session.scalar(select(User.name).where(User.account == account)) or ""


def find_user_by_account_or_email(value: str):
    """忘記密碼等流程用：以帳號或 email 找會員（不含密碼雜湊）"""
    with _session() as session:
        user = session.scalar(select(User).where(_account_match(User, value)))
        return _public_user(_as_dict(user)) if user else None


def update_user_profile_in_db(account: str, name: str, phone: str, birthday: str, bio: str, avatar: str = None):
    values = {"name": name, "phone": phone, "birthday": birthday, "bio": bio}
    if avatar is not None:
        values["avatar"] = avatar
    try:
        with _session() as session:
            session.execute(update(User.__table__).where(_account_match(User, account)).values(**values))
        return True
    except Exception as e:
        print("更新會員資料失敗:", e)
        return False


TAIWAN_TZ = timezone(timedelta(hours=8))


def check_in_user(account: str):
    """每天第一次開啟 App 時打卡：昨天有上線就連續天數 +1，中間斷掉就從第 1 天重新計算（以台灣日期為準）"""
    today = datetime.now(TAIWAN_TZ).date()
    with _session() as session:
        user = session.scalar(select(User).where(_account_match(User, account)))
        if not user:
            return None
        last = user.last_active_date or ""
        streak = int(user.login_streak or 0)
        if last == today.isoformat():
            new_streak = max(streak, 1)
        elif last == (today - timedelta(days=1)).isoformat():
            new_streak = streak + 1
        else:
            new_streak = 1
        if last != today.isoformat():
            user.last_active_date = today.isoformat()
            user.login_streak = new_streak
    return {"streak": new_streak, "date": today.isoformat(), "is_new_day": last != today.isoformat()}


# =========================================================================
# 親友
# =========================================================================
def _recipient_row_to_dict(rec):
    d = _as_dict(rec) if not isinstance(rec, dict) else dict(rec)
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
    with _session() as session:
        rows = session.scalars(
            select(Recipient).where(Recipient.user_account == user_account).order_by(Recipient.created_at, Recipient.id)
        ).all()
    return [_recipient_row_to_dict(r) for r in rows]


def get_recipient_by_id(rec_id: str):
    with _session() as session:
        rec = session.get(Recipient, rec_id)
    return _recipient_row_to_dict(rec) if rec else None


# 💡 新增親友時綁定當前使用者帳號，未指定晶片時依病況自動產生
def add_recipient(name: str, condition: str, phone: str = "", birthday: str = "", user_account: str = "test", quick_tags: list = None):
    rec_id = f"rec_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:6]}"  # 加隨機碼，避免同一毫秒建立時撞號
    quick_tags, tags_json = _resolve_quick_tags(quick_tags, condition, name)
    with _session() as session:
        session.add(Recipient(id=rec_id, name=name, condition=condition, phone=phone, birthday=birthday,
                              user_account=user_account, quick_tags_json=tags_json))
    return {"id": rec_id, "name": name, "condition": condition, "phone": phone, "birthday": birthday, "user_account": user_account, "quick_tags": quick_tags}


def update_recipient(rec_id: str, name: str, condition: str, phone: str = "", birthday: str = "", quick_tags: list = None):
    quick_tags, tags_json = _resolve_quick_tags(quick_tags, condition, name)
    with _session() as session:
        session.execute(update(Recipient.__table__).where(Recipient.id == rec_id).values(
            name=name, condition=condition, phone=phone, birthday=birthday, quick_tags_json=tags_json))
    return {"id": rec_id, "name": name, "condition": condition, "phone": phone, "birthday": birthday, "quick_tags": quick_tags}


def update_recipient_quick_tags(rec_id: str, quick_tags: list):
    with _session() as session:
        session.execute(update(Recipient.__table__).where(Recipient.id == rec_id)
                        .values(quick_tags_json=json.dumps(quick_tags, ensure_ascii=False)))
    return {"id": rec_id, "quick_tags": quick_tags}


def delete_recipient(rec_id: str):
    with _session() as session:
        session.execute(delete(Recipient.__table__).where(Recipient.id == rec_id))


# =========================================================================
# 代購訂單（舊版示範功能）
# =========================================================================
def get_all_orders(user_account: str = "test"):
    with _session() as session:
        rows = session.scalars(select(Order).where(Order.user_account == user_account).order_by(Order.created_at.desc())).all()
    orders = []
    for r in rows:
        d = _as_dict(r)
        d["items"] = json.loads(d["items_json"])
        orders.append(d)
    return orders


def create_order(order_id: str, items: list, total: str, recipient: str, pharmacy: str = "連鎖藥局", user_account: str = "test"):
    status = f"系統已向【{pharmacy}】完成專人代購下單 (白手套配送中)"
    with _session() as session:
        session.add(Order(id=order_id, items_json=json.dumps(items, ensure_ascii=False), total=total, recipient=recipient,
                          pharmacy=pharmacy, status=status, user_account=user_account))
    return {"id": order_id, "status": status}


def cancel_order(order_id: str, user_account: str) -> bool:
    """只能取消自己帳號的訂單；找不到（或不是自己的）回傳 False"""
    with _session() as session:
        result = session.execute(
            update(Order.__table__).where(Order.id == order_id, Order.user_account == user_account)
            .values(status="系統已連線藥局辦理撤單 (全額退款成功)")
        )
        return (result.rowcount or 0) > 0


# =========================================================================
# 暖幣點數與 AI 守護助理次數
# =========================================================================
def get_points_ledger(account: str = "test"):
    with _session() as session:
        rows = session.scalars(
            select(PointsLedger).where(or_(PointsLedger.account == account, PointsLedger.user_account == account))
            .order_by(PointsLedger.id.desc())
        ).all()
    return [{**_as_dict(r), "amount": round_points(r.amount)} for r in rows]


def add_points_transaction(account: str, amount: float, title: str):
    amount = round_points(amount)
    now = datetime.now()
    date_str = now.strftime("%Y/%m/%d")
    expire_str = f"{now.year + 3}/{now.strftime('%m/%d')} (剩餘 3 年)" if amount > 0 else "已折抵使用"
    with _session() as session:
        session.add(PointsLedger(account=account, amount=amount, title=title, date_str=date_str, expire_str=expire_str,
                                 type="plus" if amount > 0 else "minus", user_account=account))
        session.execute(update(User.__table__).where(_account_match(User, account))
                        .values(points=func.round(User.points + amount, 2)))


def get_ai_guard_quota(account: str, daily_limit: int):
    today = datetime.now().strftime("%Y-%m-%d")
    with _session() as session:
        row = session.get(AiGuardUsage, (account, today))
        used = (row.used or 0) if row else 0
        bonus = (row.bonus or 0) if row else 0
    limit = daily_limit + bonus
    return {"date": today, "used": used, "bonus": bonus, "limit": limit, "remaining": max(0, limit - used)}


def _bump_ai_guard_usage(account: str, date_str: str, used: int = 0, bonus: int = 0):
    """詢問次數或兌換加碼 +N（先更新，沒有當天紀錄才新增；同時新增時改為更新）"""
    table = AiGuardUsage.__table__
    stmt = (update(table).where(table.c.account == account, table.c.date_str == date_str)
            .values(used=func.coalesce(table.c.used, 0) + used, bonus=func.coalesce(table.c.bonus, 0) + bonus))
    with _session() as session:
        if session.execute(stmt).rowcount:
            return
        try:
            with session.begin_nested():
                session.execute(insert(table).values(account=account, date_str=date_str, used=used, bonus=bonus))
        except IntegrityError:
            session.execute(stmt)


def consume_ai_guard_quota(account: str, daily_limit: int):
    """扣除一次詢問次數；已達上限時回傳 (False, quota)"""
    quota = get_ai_guard_quota(account, daily_limit)
    if quota["remaining"] <= 0:
        return False, quota
    _bump_ai_guard_usage(account, quota["date"], used=1)
    return True, get_ai_guard_quota(account, daily_limit)


def add_ai_guard_bonus(account: str, extra: int, daily_limit: int):
    _bump_ai_guard_usage(account, datetime.now().strftime("%Y-%m-%d"), bonus=extra)
    return get_ai_guard_quota(account, daily_limit)


# =========================================================================
# 系統設定
# =========================================================================
def get_system_config(key: str, default=None):
    with _session() as session:
        row = session.get(SystemConfig, key)
        value = row.value_json if row else None
    if value is None:
        return default
    try:
        return json.loads(value)
    except Exception:
        return value


def set_system_config(key: str, value):
    val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    with _session() as session:
        session.merge(SystemConfig(key=key, value_json=val_str, updated_at=now_str()))
    return value


# =========================================================================
# 傳情小站聊天紀錄
# =========================================================================
def _message_dict(msg) -> dict:
    d = _as_dict(msg)
    d.pop("seq", None)
    return d


def add_family_message(msg: dict):
    with _session() as session:
        session.add(ChatMessage(
            id=msg["id"], owner_account=msg.get("owner_account") or "", elder=msg.get("elder") or "",
            sender=msg.get("sender") or "", content=msg.get("content") or "", type=msg.get("type") or "text",
            timestamp=msg.get("timestamp") or "", from_role=msg.get("from_role") or "family",
            seq=time.time_ns() // 1000,
        ))
    return msg


def list_family_messages(owner_account: str, elder: str = "", limit: int = 300):
    """只回傳「這個帳號 × 這位親友」的對話，新訊息在前"""
    stmt = select(ChatMessage).where(ChatMessage.owner_account == owner_account)
    if elder:
        stmt = stmt.where(ChatMessage.elder == elder)
    stmt = stmt.order_by(ChatMessage.timestamp.desc(), ChatMessage.seq.desc()).limit(limit)
    with _session() as session:
        rows = session.scalars(stmt).all()
    return [_message_dict(r) for r in rows]


def latest_family_card(owner_account: str, elder: str):
    with _session() as session:
        msg = session.scalar(
            select(ChatMessage)
            .where(ChatMessage.owner_account == owner_account, ChatMessage.elder == elder, ChatMessage.type == "card")
            .order_by(ChatMessage.timestamp.desc(), ChatMessage.seq.desc()).limit(1)
        )
    return _message_dict(msg) if msg else None


# =========================================================================
# 系統總覽與匯出
# =========================================================================
_STATS_MODELS = {
    "users": User, "recipients": Recipient, "orders": Order, "points_ledger": PointsLedger,
    "pharmacy_cache": PharmacyCache, "recommendation_products": RecommendationProduct,
    "clinical_knowledge": ClinicalKnowledge, "system_config": SystemConfig, "cashback_orders": CashbackOrder,
    "ai_guard_usage": AiGuardUsage, "chat_messages": ChatMessage,
}


def get_database_stats():
    counts = {}
    with _session() as session:
        for name, model in _STATS_MODELS.items():
            try:
                counts[name] = session.scalar(select(func.count()).select_from(model))
            except Exception:
                counts[name] = 0
    info = db_engine.describe(engine)
    size = "-"
    if info["kind"] == "sqlite" and os.path.exists(DB_PATH):
        size = round(os.path.getsize(DB_PATH) / 1024, 1)
    return {
        "db_name": info["db_name"],
        "db_kind": info["kind"],
        "db_path": info["db_path"],
        "db_size_kb": size,
        "orm": "SQLAlchemy ORM",
        "status": "connected",
        "persistent": info["persistent"],
        "counts": counts,
    }


def export_full_database():
    return {
        "schema_version": "2.1",
        "database": f"{db_engine.describe(engine)['db_name']}（SQLAlchemy ORM）",
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
    now_s = now.strftime(TIME_FMT)
    expires = (now + timedelta(hours=LINE_BIND_CODE_TTL_HOURS)).strftime(TIME_FMT)
    with _session() as session:
        for _ in range(20):
            code = f"{rng.randint(0, 999999):06d}"
            clash = session.scalar(select(Recipient.id).where(Recipient.line_bind_code == code, Recipient.line_bind_expires > now_s))
            if not clash:
                break
        session.execute(update(Recipient.__table__).where(Recipient.id == rec_id)
                        .values(line_bind_code=code, line_bind_expires=expires))
    return {"code": code, "expires_at": expires}


def bind_line_by_code(code: str, line_user_id: str):
    now_s = now_str()
    with _session() as session:
        rec = session.scalar(select(Recipient).where(Recipient.line_bind_code == code, Recipient.line_bind_expires > now_s))
        if not rec:
            return None
        before = _as_dict(rec)
        # 同一個 LINE 帳號只對應一位親友：先解除其他親友身上的舊綁定，避免訊息存到錯的對話
        session.execute(update(Recipient.__table__)
                        .where(Recipient.line_user_id == line_user_id, Recipient.id != rec.id).values(line_user_id=None))
        session.execute(update(Recipient.__table__).where(Recipient.id == rec.id)
                        .values(line_user_id=line_user_id, line_bind_code=None, line_bind_expires=None))
        owner_name = session.scalar(select(User.name).where(User.account == before["user_account"]))
    result = _recipient_row_to_dict(before)
    result["owner_name"] = owner_name or ""
    return result


def unbind_recipient_line(rec_id: str):
    with _session() as session:
        session.execute(update(Recipient.__table__).where(Recipient.id == rec_id)
                        .values(line_user_id=None, line_bind_code=None, line_bind_expires=None))


def find_recipient_line_id(elder_name: str, owner_account: str = ""):
    """找出要推播的 LINE ID：只比對寄件者帳號底下的親友，避免推給其他使用者的同名親友"""
    if not owner_account:
        return None
    with _session() as session:
        return session.scalar(
            select(Recipient.line_user_id)
            .where(Recipient.name == elder_name, Recipient.user_account == owner_account, Recipient.line_user_id.is_not(None))
            .limit(1)
        )


def get_line_binding_info(line_user_id: str):
    """依 LINE ID 取得綁定的親友資料與守護家人的顯示名稱；未綁定回傳 None"""
    with _session() as session:
        row = session.execute(
            select(Recipient.id, Recipient.name, Recipient.condition, Recipient.user_account, User.name.label("owner_name"))
            .outerjoin(User, User.account == Recipient.user_account)
            .where(Recipient.line_user_id == line_user_id)
            .order_by(case((func.coalesce(Recipient.user_account, "") == "", 1), else_=0),
                      Recipient.created_at.desc(), Recipient.id.desc())
            .limit(1)
        ).mappings().first()
    if not row:
        return None
    info = dict(row)
    info["owner_name"] = info.get("owner_name") or "家人"
    return info


def find_recipient_name_by_line_id(line_user_id: str):
    with _session() as session:
        return session.scalar(select(Recipient.name).where(Recipient.line_user_id == line_user_id).limit(1))


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

    already = "今天已經送過這位親友的關懷卡點數囉！" if action == "care_card" else "本週的小熊加碼已經領過囉！"
    try:
        with _session() as session:
            if session.get(RewardClaim, (account, claim_key)) is not None:
                return {"success": True, "awarded": 0, "message": already}
            daily_cap = rule.get("daily_cap")
            if daily_cap:
                used = session.scalar(select(func.count()).select_from(RewardClaim).where(
                    RewardClaim.account == account, RewardClaim.claim_key.like(f"{action}:{today}:%")))
                if used >= daily_cap:
                    return {"success": True, "awarded": 0, "message": f"今天的關懷卡點數已達上限（{daily_cap} 張）"}
            session.add(RewardClaim(account=account, claim_key=claim_key, amount=rule["amount"]))
    except IntegrityError:
        return {"success": True, "awarded": 0, "message": already}  # 同時送出兩次：主鍵擋下第二筆

    add_points_transaction(account, rule["amount"], rule["title"].format(recipient=recipient or "親友"))
    return {"success": True, "awarded": rule["amount"], "message": f"獲得 {format_points(rule['amount'])} 點關懷回饋！"}


# =========================================================================
# 購物回饋（ShopBack 模式，目前為模擬流程）：透過 GiftSense 前往藥局購物，確認購買後依金額回饋點數
# 金額在點擊「前往購買」時由伺服器依商品資料庫的查價鎖定（不採用用戶端送來的價格），待入帳 7 天後自動入帳
# =========================================================================
CASHBACK_RATES = {"大樹藥局": 0.05, "杏一醫療": 0.04, "啄木鳥藥局": 0.03, "丁丁藥局": 0.03}
CASHBACK_DEFAULT_RATE = 0.03
POINTS_PER_CASHBACK_DOLLAR = 1  # 回饋金額每 1 元換算的點數
CASHBACK_PENDING_DAYS = 7       # 確認購買後的待入帳天數（期間可處理退貨），期滿自動入帳
CASHBACK_DAILY_PURCHASE_LIMIT = 3  # 每位會員每天最多確認幾筆購買（同商品同藥局每天另限 1 筆）
REJECT_REASON_MAX_LENGTH = 200
CASHBACK_STATUS_TEXT = {
    "tracked": "追蹤中",
    "pending": "待入帳",
    "confirmed": "已入帳",
    "rejected": "已取消",
}
_TIME_FMT = TIME_FMT


def cashback_rate_for(pharmacy: str) -> float:
    for name, rate in CASHBACK_RATES.items():
        if name in (pharmacy or "") or (pharmacy or "") in name:
            return rate
    return CASHBACK_DEFAULT_RATE


def calc_cashback_points(amount: int, rate: float) -> int:
    return int(round(max(0, amount) * rate * POINTS_PER_CASHBACK_DOLLAR))


def _cashback_row(order):
    d = _as_dict(order) if not isinstance(order, dict) else dict(order)
    d.pop("rejected_by", None)  # 不回傳是哪位管理員駁回
    d["status_text"] = CASHBACK_STATUS_TEXT.get(d["status"], d["status"])
    if d["status"] == "rejected" and d.get("reject_reason"):
        d["status_text"] = "未通過審核"  # 管理員在待入帳期間駁回（會員自己取消的追蹤沒有原因）
    d["rate_percent"] = round(d["rate"] * 100, 1)
    d["est_points"] = calc_cashback_points(d.get("order_amount") or d.get("est_price") or 0, d["rate"])
    return d


def _load_cashback(order_id: str, account: str = None):
    with _session() as session:
        stmt = select(CashbackOrder).where(CashbackOrder.id == order_id)
        if account is not None:
            stmt = stmt.where(CashbackOrder.account == account)
        return session.scalar(stmt)


def create_cashback_click(account: str, pharmacy: str, product_name: str, est_price: int = 0, recipient: str = "", official_url: str = ""):
    now = datetime.now()
    click_id = f"CB{now.strftime('%Y%m%d%H%M%S')}{int(now.microsecond / 1000):03d}"
    order = CashbackOrder(id=click_id, account=account, recipient=recipient, pharmacy=pharmacy, product_name=product_name,
                          est_price=int(est_price or 0), rate=cashback_rate_for(pharmacy), status="tracked",
                          official_url=official_url, created_at=now.strftime(TIME_FMT))
    with _session() as session:
        session.add(order)
        session.flush()
        data = _as_dict(order)
    return _cashback_row(data)


def list_cashback_orders(account: str):
    with _session() as session:
        rows = session.scalars(select(CashbackOrder).where(CashbackOrder.account == account)
                               .order_by(CashbackOrder.created_at.desc(), CashbackOrder.id.desc())).all()
    orders = [_cashback_row(r) for r in rows]
    return {
        "orders": orders,
        "summary": {
            "tracked": sum(1 for o in orders if o["status"] == "tracked"),
            "pending_points": sum(o["points"] or 0 for o in orders if o["status"] == "pending"),
            "confirmed_points": sum(o["points"] or 0 for o in orders if o["status"] == "confirmed"),
        },
    }


def _norm_product_name(name: str) -> str:
    return re.sub(r"\s+", "", name or "")


def find_catalog_price(product_name: str, pharmacy: str, product_id: str = ""):
    """依商品（ID，或完整品名／搜尋關鍵字）與藥局，從暖心選物商品資料庫找出查價金額；找不到回傳 None。
    舊版 App 的暖心選物送的是搜尋關鍵字，所以兩種名稱都比對"""
    target = _norm_product_name(product_name)
    if (not target and not product_id) or not pharmacy:
        return None
    for product in get_all_recommendation_products():
        if product_id:
            if product["id"] != product_id:
                continue
        elif target not in (_norm_product_name(product.get("product_name")), _norm_product_name(product.get("search_kw"))):
            continue
        for offer in product.get("pharmacy_comparison") or []:
            name = offer.get("pharmacy") or ""
            price = int(offer.get("price") or 0)
            if price > 0 and (name == pharmacy or name in pharmacy or pharmacy in name):
                return {"product_id": product["id"], "product_name": product["product_name"],
                        "pharmacy": name, "price": price}
    return None


def cashback_purchase_quota(account: str, now: datetime = None):
    """今天已確認的購買筆數（不論之後是否入帳或被駁回都算）"""
    today = (now or datetime.now()).strftime("%Y-%m-%d")
    with _session() as session:
        used = session.scalar(select(func.count()).select_from(CashbackOrder).where(
            CashbackOrder.account == account, CashbackOrder.purchased_at.like(today + "%")))
    limit = CASHBACK_DAILY_PURCHASE_LIMIT
    return {"date": today, "used": used, "limit": limit, "remaining": max(0, limit - used)}


def confirm_cashback_purchase(order_id: str, account: str, now: datetime = None):
    """使用者確認已完成購買：金額直接採用點擊時鎖定的查價金額（使用者無法輸入或修改），
    進入待入帳，CASHBACK_PENDING_DAYS 天後自動入帳。
    每天最多 CASHBACK_DAILY_PURCHASE_LIMIT 筆，同一商品在同一藥局每天 1 筆。
    回傳 (紀錄, 錯誤訊息)"""
    order = _load_cashback(order_id, account)
    if not order:
        return None, "找不到這筆購物追蹤紀錄"
    if order.status != "tracked":
        return _cashback_row(order), f"這筆紀錄目前是「{CASHBACK_STATUS_TEXT[order.status]}」，無法再確認購買"
    amount = int(order.est_price or 0)
    if amount <= 0:
        return _cashback_row(order), "這筆追蹤沒有查價金額，無法提供購物回饋"

    now = now or datetime.now()
    today_like = now.strftime("%Y-%m-%d") + "%"
    table = CashbackOrder.__table__
    other = table.alias("other")
    confirmed_today = (select(func.count()).select_from(other)
                       .where(other.c.account == account, other.c.purchased_at.like(today_like)).scalar_subquery())
    same_item_today = (select(literal(1)).select_from(other)
                       .where(other.c.account == account, other.c.pharmacy == order.pharmacy,
                              other.c.product_name == order.product_name, other.c.purchased_at.like(today_like))
                       .exists())
    # 上限檢查與更新寫在同一個條件更新裡，同時送出多筆確認也不會超過上限
    stmt = (update(table)
            .where(table.c.id == order_id, table.c.account == account, table.c.status == "tracked",
                   confirmed_today < CASHBACK_DAILY_PURCHASE_LIMIT, ~same_item_today)
            .values(status="pending", order_amount=table.c.est_price, points=calc_cashback_points(amount, order.rate),
                    purchased_at=now.strftime(TIME_FMT),
                    credit_after=(now + timedelta(days=CASHBACK_PENDING_DAYS)).strftime(TIME_FMT)))
    with _session() as session:
        updated = session.execute(stmt).rowcount == 1
    order = _load_cashback(order_id)
    if updated:
        return _cashback_row(order), None
    if order.status != "tracked":
        return _cashback_row(order), "這筆紀錄已經確認過購買"
    if cashback_purchase_quota(account, now)["remaining"] <= 0:
        return _cashback_row(order), f"今天的購物回饋已達 {CASHBACK_DAILY_PURCHASE_LIMIT} 筆上限，請明天再確認"
    return _cashback_row(order), "同一商品在同一藥局每天只能回饋 1 次，請明天再確認"


def settle_due_cashback(account: str = None, now: datetime = None) -> int:
    """待入帳期滿的回饋自動入帳；account 為 None 時處理所有會員。回傳入帳筆數"""
    now_s = (now or datetime.now()).strftime(TIME_FMT)
    stmt = select(CashbackOrder).where(CashbackOrder.status == "pending", CashbackOrder.credit_after.is_not(None),
                                       CashbackOrder.credit_after <= now_s)
    if account:
        stmt = stmt.where(CashbackOrder.account == account)
    table = CashbackOrder.__table__
    credited = []
    with _session() as session:
        due = [_as_dict(o) for o in session.scalars(stmt).all()]
    for row in due:
        # 以狀態做條件更新，同時有多個請求在結算也只會入帳一次
        with _session() as session:
            result = session.execute(update(table).where(table.c.id == row["id"], table.c.status == "pending")
                                     .values(status="confirmed", settled_at=now_s))
            if result.rowcount == 1:
                credited.append(row)
    for row in credited:
        if (row["points"] or 0) > 0:
            add_points_transaction(
                row["account"], row["points"],
                f"購物回饋：{row['pharmacy']}（訂單 ${row['order_amount']:,} × {round(row['rate'] * 100, 1)}%）"
            )
    return len(credited)


def cancel_tracked_cashback(order_id: str, account: str):
    """使用者取消還沒確認購買的追蹤（已確認的回饋不能由使用者變更）"""
    order = _load_cashback(order_id, account)
    if not order:
        return None, "找不到這筆購物追蹤紀錄"
    if order.status != "tracked":
        return _cashback_row(order), f"這筆紀錄目前是「{CASHBACK_STATUS_TEXT[order.status]}」，無法取消"
    table = CashbackOrder.__table__
    with _session() as session:
        session.execute(update(table).where(table.c.id == order_id, table.c.status == "tracked")
                        .values(status="rejected", settled_at=now_str()))
    return _cashback_row(_load_cashback(order_id)), None


def list_pending_cashback():
    """管理員檢視所有會員的待入帳回饋：最快入帳的排前面，舊版模擬紀錄（沒有入帳時間、不會自動入帳）排最後"""
    settle_due_cashback()  # 期滿的先入帳，清單只留還能處理的
    with _session() as session:
        rows = session.scalars(
            select(CashbackOrder).where(CashbackOrder.status == "pending")
            .order_by(case((CashbackOrder.credit_after.is_(None), 1), else_=0),
                      CashbackOrder.credit_after, CashbackOrder.created_at)
        ).all()
    orders = [_cashback_row(r) for r in rows]
    return {
        "orders": orders,
        "summary": {"count": len(orders), "points": sum(o["points"] or 0 for o in orders)},
    }


def reject_pending_cashback(order_id: str, admin_account: str, reason: str):
    """管理員在待入帳期間駁回回饋（退貨、異常購買等）：不給點數"""
    reason = (reason or "").strip()
    if not reason:
        return None, "請填寫駁回原因"
    if len(reason) > REJECT_REASON_MAX_LENGTH:
        return None, f"駁回原因請在 {REJECT_REASON_MAX_LENGTH} 字以內"
    order = _load_cashback(order_id)
    if not order:
        return None, "找不到這筆購物回饋紀錄"
    settle_due_cashback(account=order.account)  # 待入帳期已滿的會先入帳，下面的條件更新就不會成立

    now_s = now_str()
    table = CashbackOrder.__table__
    with _session() as session:
        rejected = session.execute(
            update(table)
            .where(table.c.id == order_id, table.c.status == "pending",
                   or_(table.c.credit_after.is_(None), table.c.credit_after > now_s))
            .values(status="rejected", settled_at=now_s, reject_reason=reason, rejected_by=admin_account)
        ).rowcount == 1
    order = _load_cashback(order_id)
    if rejected:
        return _cashback_row(order), None
    if order.status == "pending":
        return _cashback_row(order), "待入帳期已滿，這筆回饋會自動入帳，無法駁回"
    return _cashback_row(order), f"這筆紀錄目前是「{_cashback_row(order)['status_text']}」，只能駁回待入帳的回饋"


init_db()
