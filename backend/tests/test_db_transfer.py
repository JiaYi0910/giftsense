"""
資料庫搬移（db_transfer）：切換到 SQL Server 時，從 Turso 或 SQLite 匯入全部資料。

執行（在 backend 資料夾）：
    python -m pytest tests/test_db_transfer.py -q

以兩個暫存的 SQLite 檔案模擬來源與目標，不連線任何雲端資料庫。
"""
import os
import sqlite3
import sys
import tempfile

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from sqlalchemy import create_engine, inspect, select  # noqa: E402

import db_transfer  # noqa: E402
from models import Base, ChatMessage, PointsLedger, User  # noqa: E402


def _engine(path):
    return create_engine(f"sqlite:///{path}")


@pytest.fixture
def old_source(tmp_path):
    """模擬舊版資料庫：欄位比現在少、有 id 為 NULL 的會員、多一個已移除功能的欄位、沒有 seq"""
    path = tmp_path / "old.db"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE users (id TEXT PRIMARY KEY, account TEXT UNIQUE, password_hash TEXT, name TEXT, role TEXT, points INTEGER);
        INSERT INTO users VALUES ('usr_1', 'alice@example.test', 'x', 'Alice', 'user', 7.5);
        INSERT INTO users VALUES (NULL, 'legacy@example.test', NULL, '舊會員', 'user', 3);
        CREATE TABLE points_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT, amount INTEGER, title TEXT,
                                    date_str TEXT, expire_str TEXT, type TEXT, receipt_hash TEXT);
        INSERT INTO points_ledger (account, amount, title, date_str, expire_str, type, receipt_hash)
            VALUES ('alice@example.test', 0.1, '發送關懷卡：給【奶奶】', '2026/10/15', '2029/10/15', 'plus', 'h');
        CREATE TABLE chat_messages (id TEXT PRIMARY KEY, owner_account TEXT, elder TEXT, sender TEXT, content TEXT,
                                    type TEXT, timestamp TEXT, from_role TEXT);
        INSERT INTO chat_messages VALUES ('msg_1792000000000_aaaaaa', 'alice@example.test', '奶奶', 'Alice', '早安', 'card', '2026-10-15 08:00:00', 'family');
        INSERT INTO chat_messages VALUES ('msg_line_1792000000500_bbbbbb', 'alice@example.test', '奶奶', '奶奶', '收到', 'text', '2026-10-15 08:00:00', 'elder');
    """)
    c.commit()
    c.close()
    return _engine(path)


def test_copy_fills_target_and_fixes_legacy_rows(old_source, tmp_path):
    target = _engine(tmp_path / "new.db")
    assert db_transfer.target_is_empty(target)
    copied = db_transfer.copy_database(old_source, target, log=lambda *_: None)
    assert copied == {"users": 2, "points_ledger": 1, "chat_messages": 2}
    assert not db_transfer.target_is_empty(target)

    with target.connect() as conn:
        users = {r.account: r for r in conn.execute(select(User.__table__)).all()}
        assert users["alice@example.test"].points == pytest.approx(7.5)
        legacy_id = users["legacy@example.test"].id
        assert legacy_id and legacy_id.startswith("use_import_")  # NULL 主鍵補上新 id

        ledger = conn.execute(select(PointsLedger.__table__)).one()
        assert ledger.amount == pytest.approx(0.1)
        assert ledger.created_at  # 來源沒有的欄位套用模型預設值（與舊版補欄位時的 DEFAULT 相同）

        msgs = conn.execute(select(ChatMessage.__table__).order_by(ChatMessage.seq.desc())).all()
        assert [m.content for m in msgs] == ["收到", "早安"]  # 同一秒的訊息依 id 的毫秒排序

    # 目標包含所有資料表，舊欄位（receipt_hash）不會帶過去
    names = set(inspect(target).get_table_names())
    assert {t.name for t in Base.metadata.sorted_tables} <= names
    assert "receipt_hash" not in {c["name"] for c in inspect(target).get_columns("points_ledger")}


def test_copy_refuses_non_empty_target(old_source, tmp_path):
    target = _engine(tmp_path / "busy.db")
    db_transfer.copy_database(old_source, target, log=lambda *_: None)
    with pytest.raises(RuntimeError, match="已有資料"):
        db_transfer.copy_database(old_source, target, log=lambda *_: None)


def test_table_columns_survives_incomplete_reflection(old_source, tmp_path, monkeypatch):
    """Turso 遠端連線曾回傳缺少欄位的清單（system_config 少了 key）：實際查詢到的欄位仍要算進去，複製時也不能漏"""
    real_inspect = db_transfer.inspect

    class PartialInspector:
        def __init__(self, engine):
            self._insp = real_inspect(engine)

        def __getattr__(self, name):
            return getattr(self._insp, name)

        def get_columns(self, name):
            return [c for c in self._insp.get_columns(name) if c["name"] != "account"]

    monkeypatch.setattr(db_transfer, "inspect", PartialInspector)
    assert "account" in db_transfer.table_columns(old_source, User.__table__)

    target = _engine(tmp_path / "new.db")
    db_transfer.copy_database(old_source, target, log=lambda *_: None)
    with target.connect() as conn:
        accounts = {r.account for r in conn.execute(select(User.__table__)).all()}
    assert accounts == {"alice@example.test", "legacy@example.test"}


@pytest.mark.parametrize("msg_id,timestamp,expected", [
    ("msg_1792000000000_abcdef", "", 1792000000000 * 1000),
    ("msg_line_1792000000500_abcdef", "", 1792000000500 * 1000),
    ("custom-id", "2026-10-15 08:00:00", None),
    ("custom-id", "", 0),
])
def test_chat_seq_from(msg_id, timestamp, expected):
    seq = db_transfer.chat_seq_from(msg_id, timestamp)
    if expected is None:
        assert seq > 0
    else:
        assert seq == expected


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
