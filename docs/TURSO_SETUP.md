# Turso 雲端資料庫設定（讓資料不再消失）

## 為什麼需要

Render 免費方案的硬碟不會保存資料：服務閒置約 15 分鐘會休眠，重新喚醒或重新部署時，
`backend/caregift.db` 會回到 git 裡的版本，使用者新增的帳號、親友、LINE 綁定都會消失。

改用 [Turso](https://turso.tech)（免費方案、不需信用卡）後，資料存在雲端，Render 怎麼重啟都不會遺失。
Turso 使用 libSQL，語法和 SQLite 相同；後端以 SQLAlchemy ORM 存取資料庫，同一套程式也能連線 SQL Server（見 [SQLSERVER_SETUP.md](SQLSERVER_SETUP.md)）。

## 設定步驟

1. **註冊 Turso**：到 <https://turso.tech> 註冊（可用 GitHub 帳號登入），選免費方案。
2. **建立資料庫**：在 Dashboard 建立一個資料庫，名稱例如 `giftsense`。
   地區（Location）建議選離 Render 服務最近的地區（Render 服務的 Settings 頁面可以看到 Region），延遲比較低。
3. **取得資料庫網址**：資料庫頁面會顯示 `libsql://giftsense-你的帳號.turso.io` 這樣的網址。
4. **建立存取 Token**：在資料庫頁面建立 Token（可讀寫、不設到期日），複製產生的字串。
   Token 等同資料庫密碼，**不要**貼到 GitHub、群組或程式碼裡。
5. **設定 Render 環境變數**：Render → GiftSense 服務 → Environment，新增兩個變數後儲存：

   | Key | Value |
   |---|---|
   | `TURSO_DATABASE_URL` | 第 3 步的 `libsql://...` 網址 |
   | `TURSO_AUTH_TOKEN` | 第 4 步的 Token |

   儲存後 Render 會自動重新部署。
6. **確認**：打開 <https://giftsense-vjbu.onrender.com/api/health>，`database` 顯示
   `Turso 雲端資料庫 Connected`、`sqlite_stats.persistent` 為 `true` 就完成了。

## 運作方式

- 沒有設定 `TURSO_DATABASE_URL` 時，後端使用本機 `backend/caregift.db`；有設定 `DATABASE_URL` 時則優先使用該資料庫（本機的 SQL Server）。
- 第一次連上**空的** Turso 資料庫時，會把 repo 內附的 `caregift.db`（示範帳號、實證文獻、商品快取）整份匯入；
  之後 Turso 已有資料就不會再匯入，不會覆蓋使用者新增的資料。
- 啟動時的資料表遷移（新增欄位）、暖心選物商品同步都會直接作用在 Turso 上。
- 程式位置：`backend/db_backend.py`（libSQL 轉接層）、`backend/db_engine.py`（建立連線）、`backend/database.py`（資料存取）。

## 備份（選用）

安裝 [Turso CLI](https://docs.turso.tech/cli/installation) 後可匯出整份資料：

```bash
turso db shell giftsense .dump > giftsense_backup.sql
```
