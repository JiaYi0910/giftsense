# -*- coding: utf-8 -*-
"""
資料庫連線（SQLAlchemy Engine）

依環境變數決定連到哪一個資料庫，程式其他地方一律透過 ORM 存取，不需要知道是哪一種：
1. DATABASE_URL：任何 SQLAlchemy 連線網址，例如 Microsoft SQL Server
   - 本機（Windows 驗證）：mssql+pyodbc://@localhost/GiftSense?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes
   - 雲端（SQL 帳號）：mssql+pymssql://帳號:密碼@伺服器:1433/GiftSense
2. TURSO_DATABASE_URL（與 TURSO_AUTH_TOKEN）：Turso 雲端資料庫（libSQL，與 SQLite 相容）
3. 都沒有設定：本機 SQLite 檔案（CAREGIFT_DB_PATH，預設 backend/caregift.db）
"""
import os
import sqlite3
import warnings

from sqlalchemy import create_engine, event
from sqlalchemy.dialects import registry
from sqlalchemy.dialects.sqlite.pysqlite import SQLiteDialect_pysqlite
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from db_backend import TURSO_AUTH_TOKEN, TURSO_DATABASE_URL, connect_turso

DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "caregift.db")


class TursoDialect(SQLiteDialect_pysqlite):
    """透過 db_backend 的 Turso 連線（介面與 sqlite3 相同）使用 SQLAlchemy 的 SQLite 方言。
    libsql 連線不支援 create_function，因此不註冊 SQLite 方言預設的 REGEXP 函式"""
    supports_statement_cache = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 不使用 INSERT ... RETURNING，新增資料的 id 改由 cursor.lastrowid 取得（與原本的寫法相同）
        self.insert_returning = self.update_returning = self.delete_returning = False
        self.insert_executemany_returning = False
        self.use_insertmanyvalues = False

    def on_connect(self):
        return None

    def on_connect_url(self, url):
        return None


registry.register("sqlite.turso", __name__, "TursoDialect")

# SQLAlchemy 較舊的版本不認得 SQL Server 2025（17.x）的版本號，功能不受影響，不顯示警告
warnings.filterwarnings("ignore", message="Unrecognized server version info")


def _database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def describe(engine) -> dict:
    """給系統總覽顯示的資料庫名稱（不含帳號密碼）"""
    name = engine.dialect.name
    if name == "mssql":
        url = engine.url
        return {"kind": "sqlserver", "db_name": "Microsoft SQL Server", "db_path": f"{url.host or 'localhost'}/{url.database}",
                "persistent": True}
    if engine.url.drivername == "sqlite+turso":
        return {"kind": "turso", "db_name": "Turso 雲端資料庫", "db_path": "turso", "persistent": True}
    if name == "sqlite":
        return {"kind": "sqlite", "db_name": "SQLite（本機檔案）", "db_path": engine.url.database or "", "persistent": False}
    return {"kind": name, "db_name": name, "db_path": "", "persistent": True}


def build_engine(sqlite_path: str = None):
    url = _database_url()
    if url:
        return create_engine(url, pool_pre_ping=True)
    if TURSO_DATABASE_URL:
        # Turso 走 HTTP，每次查詢都開一條新連線（與原本的寫法相同），不放進連線池
        return create_engine("sqlite+turso://", creator=connect_turso, poolclass=NullPool)
    path = sqlite_path or os.getenv("CAREGIFT_DB_PATH") or DEFAULT_SQLITE_PATH
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"timeout": 30, "check_same_thread": False},  # 逾時等待 30 秒，避免瞬間搶鎖失敗
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        try:
            dbapi_conn.execute("PRAGMA journal_mode=WAL;")
        except sqlite3.OperationalError:  # 檔案被鎖定時略過，不讓程式崩潰
            pass

    return engine


def sqlite_file_engine(path: str):
    """唯讀用途的 SQLite 檔案連線（匯入初始資料時讀取 caregift.db）"""
    return create_engine(f"sqlite:///{path}", poolclass=NullPool)


def make_session_factory(engine):
    # expire_on_commit=False：commit 後仍可讀取物件的欄位（函式回傳 dict 前常會用到）
    return sessionmaker(bind=engine, expire_on_commit=False)


def is_turso_configured() -> bool:
    return bool(TURSO_DATABASE_URL) and not _database_url()


def turso_source_engine():
    """切換到 SQL Server 時，用來讀取 Turso 舊資料的連線；沒有設定 Turso 時回傳 None"""
    if not TURSO_DATABASE_URL:
        return None
    return create_engine("sqlite+turso://", creator=connect_turso, poolclass=NullPool)


__all__ = ["build_engine", "make_session_factory", "describe", "is_turso_configured", "turso_source_engine",
           "DEFAULT_SQLITE_PATH", "TURSO_AUTH_TOKEN"]
