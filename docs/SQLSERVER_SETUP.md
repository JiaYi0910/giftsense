# SQL Server 與 ORM 設定

## 為什麼改用 SQL Server

SQLite 是單一檔案的資料庫，寫入時會鎖住整個檔案，多人同時使用時容易互相等待。
SQL Server 以資料列為單位鎖定、支援連線池，適合多人同時存取。

後端改用 **SQLAlchemy ORM** 存取資料庫：12 張資料表以 Python 類別定義（`backend/models.py`），
程式透過物件新增、查詢與更新資料，不寫只適用某一種資料庫的 SQL。同一套程式可以連線
SQL Server、Turso 或本機 SQLite，144 項後端測試在三種資料庫上都通過。

## 後端使用哪個資料庫

啟動時依環境變數決定（`backend/db_engine.py`）：

| 設定 | 使用的資料庫 | 用途 |
|---|---|---|
| `DATABASE_URL` | 網址指定的資料庫（SQL Server） | 本機開發與展示 |
| `TURSO_DATABASE_URL`（沒有 `DATABASE_URL`） | Turso 雲端資料庫 | 正式站（Render），設定見 [TURSO_SETUP.md](TURSO_SETUP.md) |
| 都沒有設定 | `backend/caregift.db`（SQLite） | 不想安裝 SQL Server 時 |

正式站目前仍使用 Turso，本機才使用 SQL Server。

## 本機設定步驟（Windows）

1. **安裝 SQL Server**：安裝免費的 SQL Server Developer Edition，以及
   [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)。
2. **安裝 Python 套件**：`pip install -r backend/requirements.txt` 之外，再安裝連線驅動：

   ```bash
   pip install pyodbc
   ```

3. **建立資料庫**：

   ```bash
   sqlcmd -S localhost -E -C -Q "CREATE DATABASE GiftSense"
   ```

4. **設定 `DATABASE_URL` 並啟動後端**（PowerShell，使用 Windows 帳號登入，不需要密碼）：

   ```powershell
   $env:DATABASE_URL = "mssql+pyodbc://@localhost/GiftSense?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes"
   cd backend
   python main.py
   ```

5. **確認**：打開 <http://127.0.0.1:8000/api/health>，`database` 顯示 `Microsoft SQL Server Connected`、
   `orm` 顯示 `SQLAlchemy ORM` 就完成了。管理後台的「資料庫指標」頁也會顯示目前連線的資料庫。

## 第一次啟動會自動匯入資料

連上**空的**資料庫時，後端會先建立所有資料表，再把原本的資料整份匯入：

- 有設定 `TURSO_DATABASE_URL`（與 `TURSO_AUTH_TOKEN`）時，從 Turso 匯入正式站的資料；
- 沒有設定時，從 repo 內附的 `caregift.db` 匯入示範資料。

資料庫已經有資料就不會再匯入，不會覆蓋任何資料。匯入失敗時後端會停止啟動，避免在空的資料庫上運作。
舊資料中主鍵為空的會員會補上新的 id，聊天訊息依原本的時間順序排列。

也可以手動複製（目標必須是空的資料庫）：

```bash
cd backend
python tools/copy_database.py --source sqlite:///caregift.db --target "<SQL Server 連線網址>"
python tools/copy_database.py --source turso --target "<SQL Server 連線網址>"
```

## 在 SQL Server 上跑測試

測試預設使用暫存的 SQLite 檔案，**不會**讀取 `DATABASE_URL`，所以不會動到開發用的 GiftSense。
要在 SQL Server 上測試，先建立一個空的測試資料庫，再用 `TEST_DATABASE_URL` 指定：

```bash
sqlcmd -S localhost -E -C -Q "DROP DATABASE IF EXISTS GiftSense_Test; CREATE DATABASE GiftSense_Test"
```

```powershell
$env:TEST_DATABASE_URL = "mssql+pyodbc://@localhost/GiftSense_Test?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes"
cd backend
python -m pytest tests -q
```

快速提問驗證（`python tests/test_quick_questions.py`）也一樣，執行前先重建空的 GiftSense_Test。

## 之後若正式站要改用 SQL Server

正式站跑在 Render（Linux），系統沒有 ODBC 驅動，因此改用不需要額外安裝的 `pymssql`：

1. 準備一個雲端 SQL Server（例如 Azure SQL Database），建立空的資料庫 `GiftSense`，並確認費用方案。
2. 在 `backend/requirements.txt` 加上 `pymssql`。
3. 在 Render → Environment 新增 `DATABASE_URL`：`mssql+pymssql://帳號:密碼@主機:1433/GiftSense`。
   密碼只放在 Render 環境變數，不要寫進程式碼或 GitHub。
4. **保留** `TURSO_DATABASE_URL` 與 `TURSO_AUTH_TOKEN`，第一次啟動時才能從 Turso 匯入全部資料。
5. 部署後確認 `/api/health` 顯示 `Microsoft SQL Server Connected`，並抽查會員、親友與回饋資料；
   確認無誤後再移除 Turso 的兩個環境變數。

## 程式位置

| 檔案 | 內容 |
|---|---|
| `backend/models.py` | ORM 模型（12 張資料表的欄位、型別與主鍵） |
| `backend/db_engine.py` | 依環境變數建立資料庫連線；Turso 透過 `db_backend.py` 轉接 |
| `backend/database.py` | 所有資料存取函式（會員、親友、點數、購物回饋等）與啟動時的資料遷移 |
| `backend/db_transfer.py` | 資料庫之間的整份複製（自動匯入與 `tools/copy_database.py` 共用） |
