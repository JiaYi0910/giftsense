# -*- coding: utf-8 -*-
"""
把 GiftSense 的資料從一個資料庫複製到另一個（目標必須是空的）

用法（在 backend 資料夾）：
    python tools/copy_database.py --source sqlite:///caregift.db --target "mssql+pyodbc://@localhost/GiftSense?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes"
    python tools/copy_database.py --source turso --target "<SQL Server 連線網址>"

--source turso 會使用環境變數 TURSO_DATABASE_URL 與 TURSO_AUTH_TOKEN。
平常不需要手動執行：正式站設定 DATABASE_URL 指向空的 SQL Server 後，第一次啟動會自動從 Turso 匯入。
"""
import argparse
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from sqlalchemy import create_engine  # noqa: E402

import db_engine  # noqa: E402
from db_transfer import copy_database, target_is_empty  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="複製 GiftSense 資料庫")
    parser.add_argument("--source", required=True, help="來源：SQLAlchemy 連線網址，或 turso")
    parser.add_argument("--target", required=True, help="目標：SQLAlchemy 連線網址（必須是空的資料庫）")
    args = parser.parse_args()

    source = db_engine.turso_source_engine() if args.source == "turso" else create_engine(args.source)
    if source is None:
        sys.exit("沒有設定 TURSO_DATABASE_URL")
    target = create_engine(args.target)
    if not target_is_empty(target):
        sys.exit("目標資料庫已有資料，為避免覆蓋，不執行複製")
    print(f"來源：{db_engine.describe(source)['db_name']} → 目標：{db_engine.describe(target)['db_name']}")
    copied = copy_database(source, target)
    print(f"完成，共複製 {sum(copied.values())} 筆資料。下一次啟動後端時會自動補齊欄位與資料遷移。")


if __name__ == "__main__":
    main()
