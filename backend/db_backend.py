# -*- coding: utf-8 -*-
"""
Turso（libSQL）連線轉接層

libsql 的查詢結果是 tuple、錯誤類型是 ValueError，這裡包一層轉接，讓它的介面與 Python 內建的 sqlite3 相同，
SQLAlchemy 就能用 SQLite 方言透過它存取 Turso（見 db_engine.TursoDialect）。
設定環境變數 TURSO_DATABASE_URL（與 TURSO_AUTH_TOKEN）後啟用。
"""
import datetime
import os
import sqlite3
import time

TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "").strip()
USE_TURSO = bool(TURSO_DATABASE_URL)


class Row(tuple):
    """與 sqlite3.Row 相容：可用索引或欄位名稱取值，也可以 dict(row)"""

    def __new__(cls, values, columns):
        row = super().__new__(cls, values)
        row._columns = columns
        return row

    def keys(self):
        return list(self._columns)

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                return tuple.__getitem__(self, self._columns.index(key))
            except ValueError:
                lowered = [c.lower() for c in self._columns]
                if key.lower() in lowered:
                    return tuple.__getitem__(self, lowered.index(key.lower()))
                raise IndexError(f"No item with that key: {key}")
        return tuple.__getitem__(self, key)


def _translate_error(e: Exception) -> Exception:
    """libsql 的錯誤轉成 sqlite3 對應的例外，讓既有的 except 寫法照常運作"""
    msg = str(e)
    if "constraint" in msg.lower():
        return sqlite3.IntegrityError(msg)
    return sqlite3.OperationalError(msg)


def _adapt_param(v):
    # sqlite3 會自動把 bool / datetime 轉成 int / 字串，libsql 不會
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, datetime.datetime):
        return v.isoformat(" ")
    if isinstance(v, datetime.date):
        return v.isoformat()
    return v


def _adapt_params(params):
    if params is None:
        return ()
    if isinstance(params, dict):
        return {k: _adapt_param(v) for k, v in params.items()}
    return tuple(_adapt_param(v) for v in params)


class _Cursor:
    def __init__(self, cursor):
        self._cur = cursor

    def _columns(self):
        return tuple(d[0] for d in (self._cur.description or ()))

    def execute(self, sql, params=()):
        try:
            self._cur.execute(sql, _adapt_params(params))
        except ValueError as e:
            raise _translate_error(e) from e
        return self

    def executemany(self, sql, seq_of_params):
        try:
            self._cur.executemany(sql, [_adapt_params(p) for p in seq_of_params])
        except ValueError as e:
            raise _translate_error(e) from e
        return self

    def fetchone(self):
        r = self._cur.fetchone()
        return None if r is None else Row(r, self._columns())

    def fetchall(self):
        cols = self._columns()
        return [Row(r, cols) for r in self._cur.fetchall()]

    def fetchmany(self, size=1):
        cols = self._columns()
        return [Row(r, cols) for r in self._cur.fetchmany(size)]

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass


class _Connection:
    """與 sqlite3.Connection 相容的 Turso 連線"""

    row_factory = None  # 一律回傳 Row，設定值不影響

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return _Cursor(self._conn.cursor())

    def execute(self, sql, params=()):
        return self.cursor().execute(sql, params)

    def executemany(self, sql, seq_of_params):
        return self.cursor().executemany(sql, seq_of_params)

    def executescript(self, script):
        try:
            self._conn.executescript(script)
        except ValueError as e:
            raise _translate_error(e) from e
        return self.cursor()

    def commit(self):
        try:
            self._conn.commit()
        except ValueError as e:
            raise _translate_error(e) from e

    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            pass

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # 與 sqlite3 相同：成功時 commit、發生例外時 rollback（不關閉連線）
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False


def connect_turso():
    import libsql  # 只有啟用 Turso 時才需要安裝

    last_error = None
    for attempt in range(3):
        try:
            conn = libsql.connect(
                TURSO_DATABASE_URL,
                auth_token=TURSO_AUTH_TOKEN,
                _check_same_thread=False,
            )
            return _Connection(conn)
        except Exception as e:  # 網路瞬斷時重試
            last_error = e
            time.sleep(0.3 * (attempt + 1))
    raise sqlite3.OperationalError(f"無法連線 Turso 資料庫：{last_error}")
