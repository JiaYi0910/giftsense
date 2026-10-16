# -*- coding: utf-8 -*-
"""
在兩個資料庫之間複製 GiftSense 的資料（例如 Turso → SQL Server、SQLite 檔案 → SQL Server）

- 只複製 ORM 模型定義的資料表與欄位；來源缺少的資料表或欄位會略過，交給 init_db 補齊
- 目標資料表必須是空的（避免覆蓋已經在使用的資料）
- chat_messages 的 seq（排序用）若來源沒有，依訊息 id 中的毫秒時間推算
- 早期 SQLite 允許文字主鍵是 NULL（SQL Server 不允許），這類資料列會補上新的 id
"""
import re
import uuid
from datetime import datetime

from sqlalchemy import Column, MetaData, Table, func, insert, inspect, select, text

from models import ALL_MODELS, Base, ChatMessage, TIME_FMT

CHUNK = 200
_ID_MS = re.compile(r"_(\d{12,14})_")


def chat_seq_from(msg_id: str, timestamp: str = "") -> int:
    """訊息排序值（微秒）：優先用 id 裡的毫秒時間，其次用 timestamp 欄位"""
    m = _ID_MS.search(msg_id or "")
    if m:
        return int(m.group(1)) * 1000
    try:
        return int(datetime.strptime(timestamp or "", TIME_FMT).timestamp() * 1_000_000)
    except ValueError:
        return 0


def table_columns(engine, table) -> set:
    """資料表目前的欄位名稱（小寫）。合併資料庫的欄位清單（reflection）與實際查詢結果的欄位：
    Turso 遠端連線曾回傳缺少欄位的清單（system_config 少了 key），只靠一種來源會漏掉欄位"""
    names = {c["name"].lower() for c in inspect(engine).get_columns(table.name)}
    with engine.connect() as conn:
        names |= {k.lower() for k in conn.execute(select(text("*")).select_from(table).limit(1)).keys()}
    return names


def target_is_empty(engine) -> bool:
    insp = inspect(engine)
    if not insp.has_table("users"):
        return True
    with engine.connect() as conn:
        for model in ALL_MODELS:
            if insp.has_table(model.__tablename__):
                if conn.execute(select(func.count()).select_from(model.__table__)).scalar():
                    return False
    return True


def copy_database(source_engine, target_engine, log=print) -> dict:
    """把 source 的資料複製到 target（target 的資料表會先建立）；回傳各資料表複製的筆數"""
    Base.metadata.create_all(target_engine)
    src_insp = inspect(source_engine)
    copied = {}
    with source_engine.connect() as src, target_engine.begin() as dst:
        for model in ALL_MODELS:
            table = model.__table__
            name = table.name
            if not src_insp.has_table(name):
                continue
            src_cols = table_columns(source_engine, table)
            cols = [c for c in table.columns if c.name.lower() in src_cols]
            if dst.execute(select(func.count()).select_from(table)).scalar():
                raise RuntimeError(f"目標資料庫的 {name} 已有資料，為避免覆蓋，停止複製")
            src_table = Table(name, MetaData(), *[Column(c.name, c.type) for c in cols])
            rows = src.execute(select(*src_table.columns)).mappings().all()
            pk_text_cols = [c.name for c in table.primary_key.columns
                            if c.name.lower() in src_cols and getattr(c.type, "length", None) is not None]
            batch = []
            for r in rows:
                row = {c.name: r[c.name] for c in cols}
                for pk in pk_text_cols:
                    if row.get(pk) in (None, ""):
                        row[pk] = f"{name[:3]}_import_{uuid.uuid4().hex[:12]}"
                if model is ChatMessage and row.get("seq") is None:
                    row["seq"] = chat_seq_from(row.get("id"), row.get("timestamp"))
                batch.append(row)
                if len(batch) >= CHUNK:
                    dst.execute(insert(table), batch)
                    batch = []
            if batch:
                dst.execute(insert(table), batch)
            copied[name] = len(rows)
            log(f"  {name}: {len(rows)} 筆")
    return copied
