# -*- coding: utf-8 -*-
"""
GiftSense 資料表的 ORM 模型（SQLAlchemy 2.0）

同一套模型可用於 Microsoft SQL Server、Turso（libSQL）與本機 SQLite：
- 中文欄位一律用 Unicode／UnicodeText，在 SQL Server 對應 NVARCHAR，避免中文變成問號
- 主鍵與需要建索引的欄位指定長度（SQL Server 的 NVARCHAR(MAX) 不能當主鍵或索引）
- 點數可能有小數（例如關懷卡 0.1 點），一律用 Float
- 時間沿用既有的文字格式（2026-10-16 09:30:00），比較與排序規則和舊資料一致；
  預設值在 Python 端產生，各資料庫存進去的格式才會相同
"""
from datetime import datetime

from sqlalchemy import BigInteger, Float, Index, Integer, Unicode, UnicodeText
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TIME_FMT = "%Y-%m-%d %H:%M:%S"

# 欄位長度
ID_LEN = 64
ACCOUNT_LEN = 200   # 帳號（email 或 google_xxx）；組合主鍵在 SQL Server 有 900 bytes 上限
TIME_LEN = 32


def now_str() -> str:
    return datetime.now().strftime(TIME_FMT)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Unicode(ID_LEN), primary_key=True)
    account: Mapped[str] = mapped_column(Unicode(ACCOUNT_LEN), unique=True)
    password_hash: Mapped[str | None] = mapped_column(Unicode(255))
    name: Mapped[str | None] = mapped_column(Unicode(200))
    role: Mapped[str | None] = mapped_column(Unicode(20), default="user")
    points: Mapped[float | None] = mapped_column(Float, default=0)
    email: Mapped[str | None] = mapped_column(Unicode(255), default="")
    phone: Mapped[str | None] = mapped_column(Unicode(50), default="")
    birthday: Mapped[str | None] = mapped_column(Unicode(20), default="")
    bio: Mapped[str | None] = mapped_column(UnicodeText, default="")
    avatar: Mapped[str | None] = mapped_column(UnicodeText, default="default")  # 自行上傳的頭貼（data URL）
    auth_provider: Mapped[str | None] = mapped_column(Unicode(20), default="email")
    social_id: Mapped[str | None] = mapped_column(Unicode(255))
    social_avatar_url: Mapped[str | None] = mapped_column(UnicodeText, default="")
    last_active_date: Mapped[str | None] = mapped_column(Unicode(20), default="")
    login_streak: Mapped[int | None] = mapped_column(Integer, default=0)
    created_at: Mapped[str | None] = mapped_column(Unicode(TIME_LEN), default=now_str)


class Recipient(Base):
    """受照顧的親友（依 user_account 區分是哪位會員的親友）"""
    __tablename__ = "recipients"

    id: Mapped[str] = mapped_column(Unicode(ID_LEN), primary_key=True)
    name: Mapped[str] = mapped_column(Unicode(200))
    condition: Mapped[str] = mapped_column(UnicodeText)
    phone: Mapped[str | None] = mapped_column(Unicode(50))
    birthday: Mapped[str | None] = mapped_column(Unicode(20))
    line_user_id: Mapped[str | None] = mapped_column(Unicode(ID_LEN))
    user_account: Mapped[str | None] = mapped_column(Unicode(ACCOUNT_LEN), default="test")
    quick_tags_json: Mapped[str | None] = mapped_column(UnicodeText, default="[]")
    line_bind_code: Mapped[str | None] = mapped_column(Unicode(10))
    line_bind_expires: Mapped[str | None] = mapped_column(Unicode(TIME_LEN))
    created_at: Mapped[str | None] = mapped_column(Unicode(TIME_LEN), default=now_str)


class Order(Base):
    """代購訂單（舊版示範功能）"""
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(Unicode(ID_LEN), primary_key=True)
    items_json: Mapped[str] = mapped_column(UnicodeText)
    total: Mapped[str] = mapped_column(Unicode(50))
    recipient: Mapped[str] = mapped_column(Unicode(200))
    pharmacy: Mapped[str | None] = mapped_column(Unicode(100), default="連鎖藥局")
    status: Mapped[str] = mapped_column(Unicode(255))
    user_account: Mapped[str | None] = mapped_column(Unicode(ACCOUNT_LEN), default="test")
    created_at: Mapped[str | None] = mapped_column(Unicode(TIME_LEN), default=now_str)


class PointsLedger(Base):
    """暖幣收支明細"""
    __tablename__ = "points_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account: Mapped[str] = mapped_column(Unicode(ACCOUNT_LEN))
    amount: Mapped[float] = mapped_column(Float)
    title: Mapped[str] = mapped_column(Unicode(500))
    date_str: Mapped[str] = mapped_column(Unicode(20))
    expire_str: Mapped[str] = mapped_column(Unicode(50))
    type: Mapped[str] = mapped_column(Unicode(10))
    user_account: Mapped[str | None] = mapped_column(Unicode(ACCOUNT_LEN), default="test")
    created_at: Mapped[str | None] = mapped_column(Unicode(TIME_LEN), default=now_str)


class PharmacyCache(Base):
    """藥局爬蟲結果快取"""
    __tablename__ = "pharmacy_cache"

    id: Mapped[str] = mapped_column(Unicode(255), primary_key=True)
    pharmacy: Mapped[str] = mapped_column(Unicode(100))
    product_name: Mapped[str] = mapped_column(Unicode(500))
    price: Mapped[int] = mapped_column(Integer)
    spec: Mapped[str | None] = mapped_column(Unicode(500))
    url: Mapped[str | None] = mapped_column(UnicodeText)
    image_url: Mapped[str | None] = mapped_column(UnicodeText)
    in_stock: Mapped[int | None] = mapped_column(Integer, default=1)
    updated_at: Mapped[str | None] = mapped_column(Unicode(TIME_LEN), default=now_str)


class RecommendationProduct(Base):
    """暖心選物商品（藥局官網實際查價）"""
    __tablename__ = "recommendation_products"

    id: Mapped[str] = mapped_column(Unicode(100), primary_key=True)
    product_name: Mapped[str] = mapped_column(Unicode(500))
    sku: Mapped[str | None] = mapped_column(Unicode(100))
    ean_13: Mapped[str | None] = mapped_column(Unicode(50))
    category: Mapped[str | None] = mapped_column(Unicode(100))
    spec: Mapped[str | None] = mapped_column(Unicode(500))
    search_kw: Mapped[str | None] = mapped_column(Unicode(255))
    match_conditions_json: Mapped[str] = mapped_column(UnicodeText)
    match_reason: Mapped[str | None] = mapped_column(UnicodeText)
    recommended_pharmacy: Mapped[str | None] = mapped_column(Unicode(100))
    best_price: Mapped[int] = mapped_column(Integer)
    official_url: Mapped[str | None] = mapped_column(UnicodeText)
    pharmacy_comparison_json: Mapped[str] = mapped_column(UnicodeText)
    is_active: Mapped[int | None] = mapped_column(Integer, default=1)
    price_checked_at: Mapped[str | None] = mapped_column(Unicode(TIME_LEN))
    primary_conditions_json: Mapped[str | None] = mapped_column(UnicodeText, default="[]")
    exclude_conditions_json: Mapped[str | None] = mapped_column(UnicodeText, default="[]")
    created_at: Mapped[str | None] = mapped_column(Unicode(TIME_LEN), default=now_str)


class AiGuardUsage(Base):
    """AI 守護助理每日詢問次數"""
    __tablename__ = "ai_guard_usage"

    account: Mapped[str] = mapped_column(Unicode(ACCOUNT_LEN), primary_key=True)
    date_str: Mapped[str] = mapped_column(Unicode(10), primary_key=True)
    used: Mapped[int | None] = mapped_column(Integer, default=0)
    bonus: Mapped[int | None] = mapped_column(Integer, default=0)


class RewardClaim(Base):
    """關懷卡、小熊回饋的領取紀錄（主鍵防止重複領取）"""
    __tablename__ = "reward_claims"

    account: Mapped[str] = mapped_column(Unicode(ACCOUNT_LEN), primary_key=True)
    claim_key: Mapped[str] = mapped_column(Unicode(200), primary_key=True)
    amount: Mapped[float] = mapped_column(Float)
    created_at: Mapped[str | None] = mapped_column(Unicode(TIME_LEN), default=now_str)


class ChatMessage(Base):
    """傳情小站訊息（會員 × 單一親友）"""
    __tablename__ = "chat_messages"
    __table_args__ = (Index("idx_chat_messages_owner", "owner_account", "elder"),)

    id: Mapped[str] = mapped_column(Unicode(ID_LEN), primary_key=True)
    owner_account: Mapped[str] = mapped_column(Unicode(ACCOUNT_LEN))
    elder: Mapped[str] = mapped_column(Unicode(200))
    sender: Mapped[str | None] = mapped_column(Unicode(200))
    content: Mapped[str | None] = mapped_column(UnicodeText)
    type: Mapped[str | None] = mapped_column(Unicode(20), default="text")
    timestamp: Mapped[str | None] = mapped_column(Unicode(TIME_LEN))
    from_role: Mapped[str | None] = mapped_column(Unicode(20), default="family")
    # 同一秒內的訊息依寫入順序排序（取代 SQLite 專屬的 rowid）
    seq: Mapped[int | None] = mapped_column(BigInteger)


class CashbackOrder(Base):
    """購物回饋：追蹤中 → 待入帳（7 天）→ 已入帳／已取消"""
    __tablename__ = "cashback_orders"
    __table_args__ = (Index("idx_cashback_status", "status", "credit_after"),)

    id: Mapped[str] = mapped_column(Unicode(ID_LEN), primary_key=True)
    account: Mapped[str] = mapped_column(Unicode(ACCOUNT_LEN))
    recipient: Mapped[str | None] = mapped_column(Unicode(200))
    pharmacy: Mapped[str] = mapped_column(Unicode(100))
    product_name: Mapped[str] = mapped_column(Unicode(500))
    est_price: Mapped[int | None] = mapped_column(Integer, default=0)   # 前往購買時鎖定的查價金額
    rate: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(Unicode(20))
    order_amount: Mapped[int | None] = mapped_column(Integer, default=0)
    points: Mapped[int | None] = mapped_column(Integer, default=0)
    official_url: Mapped[str | None] = mapped_column(UnicodeText)
    created_at: Mapped[str] = mapped_column(Unicode(TIME_LEN), default=now_str)
    purchased_at: Mapped[str | None] = mapped_column(Unicode(TIME_LEN))
    settled_at: Mapped[str | None] = mapped_column(Unicode(TIME_LEN))
    credit_after: Mapped[str | None] = mapped_column(Unicode(TIME_LEN))   # 待入帳期滿、自動入帳的時間
    reject_reason: Mapped[str | None] = mapped_column(Unicode(255))
    rejected_by: Mapped[str | None] = mapped_column(Unicode(ACCOUNT_LEN))


class ClinicalKnowledge(Base):
    """實證文獻與照護指引（AI 守護助理的檢索來源，管理員可維護）"""
    __tablename__ = "clinical_knowledge"

    id: Mapped[str] = mapped_column(Unicode(100), primary_key=True)
    title: Mapped[str] = mapped_column(Unicode(500))
    authority: Mapped[str] = mapped_column(UnicodeText)
    category: Mapped[str] = mapped_column(Unicode(200))
    ingredient: Mapped[str] = mapped_column(UnicodeText)
    evidence_level: Mapped[str] = mapped_column(Unicode(255))
    recommended_dose: Mapped[str] = mapped_column(UnicodeText)
    mechanism: Mapped[str] = mapped_column(UnicodeText)
    contraindications: Mapped[str] = mapped_column(UnicodeText)
    target_symptoms_json: Mapped[str] = mapped_column(UnicodeText)
    citation: Mapped[str] = mapped_column(UnicodeText)
    created_at: Mapped[str | None] = mapped_column(Unicode(TIME_LEN), default=now_str)


class SystemConfig(Base):
    """系統設定與一次性資料遷移的完成標記"""
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(Unicode(100), primary_key=True)
    value_json: Mapped[str] = mapped_column(UnicodeText)
    updated_at: Mapped[str | None] = mapped_column(Unicode(TIME_LEN), default=now_str)


# 匯入資料時的順序（沒有外鍵，順序只影響閱讀）
ALL_MODELS = [
    SystemConfig, User, Recipient, Order, PointsLedger, PharmacyCache, RecommendationProduct,
    AiGuardUsage, RewardClaim, ChatMessage, CashbackOrder, ClinicalKnowledge,
]
