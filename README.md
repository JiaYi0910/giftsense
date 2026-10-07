# 🎁 GiftSense

> **系統版本**：`v55.0 (MUJI & Mascot Native Edition)`  
> **系統架構**：Decoupled SPA Frontend + High-Performance Python FastAPI Backend + Pure SQLite Persistence (caregift.db)  
> **核心定位**：基於臨床實證醫學 (RAG) 與國家級藥品法規 (TFDA) 的親友健康關懷、用藥防錯雷達與四大連鎖藥局即時比價系統。

---

## 📌 系統概述 (System Overview)

**GiftSense** 是一套針對銀髮照護痛點設計的軟硬整合前導系統。傳統親友送禮往往面臨「買錯保健品與慢性處方藥產生交互作用 (撞藥)」以及「問候千篇一律」的雙重困境。

本系統透過 **檢索增強生成 (RAG, Retrieval-Augmented Generation)** 技術，串接國際頂級醫學文獻庫（US FDA、NIH、AHA、ADA、Cochrane）與台灣衛福部食藥署 (TFDA) 黑盒子警示資料庫，建立從「日常天氣關心」到「親友病況防錯比對」、「連鎖藥局真實 SKU 比價」及「自動化代購」的完整工程閉環。

```
                    ┌────────────────────────────────────────────────────────┐
                    │               CareGift Client (SPA)                    │
                    │   - Vanilla JS + CSS3 (MUJI Design Tokens)             │
                    │   - Local State Engine & Real-time SQLite Console      │
                    └───────────────────────────┬────────────────────────────┘
                                                │ HTTP / JSON API
                                                ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Port: 8000)                            │
│ ├─ RAG Engine (15+ Clinical Guidelines)                                    │
│ ├─ Medical Vector Store (High-Dim Cosine Similarity)                       │
│ ├─ TFDA Regulatory & Black Box Service                                     │
│ ├─ Chain Pharmacy Scraper (Big 4 Pharmacies)                               │
│ ├─ Auto-Order Automation Pipeline                                          │
│ ├─ CWA Weather Integration                                                 │
│ └─ Pure SQLite Persistence Layer (caregift.db)                             │
│     ├─ clinical_knowledge (15 Authoritative Guidelines)                    │
│     ├─ recipients (Health Records & Conditions)                            │
│     ├─ orders & points_ledger (Deliveries & 3-Year Expiry Ledger)           │
│     ├─ pharmacy_cache (Live Scraped Chain Pharmacy SKUs)                   │
│     └─ system_config (Tunable RAG Hyperparameters & System Prompts)        │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 技術棧規格 (Technology Stack)

### 1. 前端架構 (Frontend)
- **核心架構**：原生輕量 SPA (Single Page Application)，無冗餘重型框架依賴，啟動速度達到毫秒級首屏渲染。
- **樣式系統**：獨立抽取之 [style.css](file:///c:/Users/user/OneDrive/桌面/智慧關懷送禮APP(1)/care_gifting_app/style.css)，基於無印良品 (MUJI) 與 Pokémon Sleep 溫潤大地色系，嚴格遵循 Design Tokens（CSS Variables）規範。
- **狀態管理**：
  - 本地快取層：`localStorage` 搭配 `safeJSONParse` 防崩潰包裝。
  - 多親友健康檔案（Active Recipient Scope）動態切換機制。
  - 對話紀錄與點數帳本 (Points Ledger) 事務一致性維護。

### 2. 後端微服務 (Backend - Python 3.11+)
- **API 框架**：FastAPI (ASGI，基於 Starlette 與 Pydantic 資料驗證)，支援全自動 OpenAPI / Swagger 文檔生成。
- **資料庫**：SQLite 3 (`caregift.db`) 搭配原生連線池管理，提供高可靠之 ACID 事務支援。
- **並行處理**：Python `asyncio` 與 `ThreadPoolExecutor`，處理外部爬蟲與高延遲氣象 API 請求。
- **外部依賴**：`uvicorn`、`requests`、`beautifulsoup4`、`curl_cffi`、`selenium`。

---

## 🔬 核心模組深度解析 (Core Architectural Modules)

### 1. 醫療級 RAG 檢索增強生成引擎 (`rag_engine.py`)
- **雙軌檢索機制**：
  - **軌道一 (本機臨床實證庫)**：收錄 15 篇權威臨床指引，涵蓋視力、心血管、腸胃、骨質、睡眠、關節與燙傷創面等主題。
  - **軌道二 (Google Gemini 1.5 Flash API)**：當配置 API Key 時，系統自動組合 System Prompt、親友病歷上下文與檢索文獻，執行精準的臨床等級衛教小語生成。
- **降級機制 (Graceful Degradation)**：在無 API Key 或無網路連線狀態下，全自動回退至在地專家規則引擎，保證系統 100% 可用。

### 2. 高維向量語意特徵檢索庫 (`vector_store.py`)
- **演算法**：基於字詞權重分詞與高維特徵向量化，計算 **餘弦相似度 (Cosine Similarity)**。
- **功能**：克服傳統關鍵字完全比對之侷限，當使用者輸入口語化詞彙（如「膝蓋卡卡」、「睡不著」）時，能自動命中「退化性關節炎」、「褪黑激素/GABA」相關臨床文獻。

### 3. TFDA 藥物交互作用與黑盒子審核 (`tfda_service.py`)
- **法規依據**：對接台灣衛生福利部食品藥物管理署 (TFDA) 最新「含成分保健食品安全警語與藥品交互作用指引」。
- **安全防錯機制**：
  - 嚴格攔截 Warfarin / 抗凝血藥物與魚油 (EPA>1000mg)、納豆激酶、銀杏、Q10 之併用風險。
  - 血糖處方藥與高 GI / 麥芽糖醇保健品衝突警示。
  - 燙傷 / 外傷微血管創面期活血化瘀禁忌攔截。

### 4. 四大連鎖藥局即時爬蟲比價模組 (`pharmacy_crawler.py`)
- **通路覆蓋**：全台 4 大連鎖藥局（大樹健康購物網、杏一醫療、丁丁連鎖藥局、啄木鳥藥局）。
- **特點**：
  - 精準匹配真實官方 SKU、規格及 EAN-13 國際商品條碼。
  - 標註「全網最低價」與通路專屬標籤。
  - 具備防爬蟲偽裝 Header 與 Session 復用，確保抓取成功率。

### 5. 自動化代理下單管道 (`auto_order.py`)
- 模擬連鎖藥局官方購物車結帳流程，自動填入親友配送地址，回傳真實訂單追蹤號碼並寫入 SQLite 訂單履歷表。

---

## 📡 API 路由規格 (API Endpoints Specification)

後端預設監聽於 `http://127.0.0.1:8000`，核心端點如下：

| 方法 | 路徑 | 功能說明 | 核心參數 / Payload |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/health` | 服務健康檢查與引擎狀態 | 無 |
| `POST` | `/api/guard/query` | 統一 AI 守護諮詢 (RAG + 撞藥防錯) | `{ query, elder_name, elder_condition, api_key, model }` |
| `POST` | `/api/tfda/check` | TFDA 藥品交互作用黑盒子審核 | `{ elder_name, elder_condition, query, ingredient }` |
| `GET` | `/api/vector/search` | 醫學向量資料庫語意檢索 | `?q={query}&top_k=3` |
| `GET` | `/api/pharmacy/search` | 四大連鎖藥局即時爬蟲搜尋 | `?q={keyword}` |
| `GET` | `/api/pharmacy/recommended` | 依親友病史動態推薦藥局商品 | `?condition={condition}&elder_name={name}` |
| `POST` | `/api/pharmacy/auto-order` | 藥局自動化代理下單管線 | `{ product_name, price, pharmacy, recipient }` |
| `GET` | `/api/weather` | CWA 中央氣象署即時氣象連線 | `?city={cityName}&key={cwaKey}` |
| `GET` | `/api/recipients` | 查詢親友親友資料庫清單 | 無 |
| `POST` | `/api/recipients` | 新增親友親友健康檔案 | `{ name, condition }` |
| `GET` | `/api/orders` | 查詢歷史訂單與物流追蹤紀錄 | 無 |
| `GET` | `/api/points` | 查詢會員點數存摺 (Points Ledger) | `?account={account}` |
| `POST` | `/api/greeting/generate`| 動態生成多語氣關懷小語 | `{ elder_name, elder_condition, weather_*, tone }` |

---

## 📂 專案檔案結構 (Project Structure)

```text
care_gifting_app/
├── index.html               # 前端核心 SPA 主頁面 (4,200+ 行精簡結構)
├── style.css                # 獨立 CSS 樣式庫 (MUJI 日系設計系統，900+ 行)
├── bear.png                 # 脈脈小熊官方 Mascot 與頭像資產
├── run_backend.bat          # Windows 一鍵啟動後端批次檔
├── README.md                # 系統架構與技術說明文件 (本檔案)
└── backend/                 # Python 後端服務目錄
    ├── main.py              # FastAPI 應用程式核心與路由註冊 (24 條端點)
    ├── database.py          # SQLite 實體資料庫連線與 CRUD 操作
    ├── caregift.db          # 預載親友資料、訂單與點數之 SQLite 資料庫
    ├── rag_engine.py        # 國家級臨床指引與 RAG 雙模檢索核心
    ├── vector_store.py      # 高維度向量語意檢索庫 (Cosine Similarity)
    ├── tfda_service.py      # TFDA 藥物交互作用與禁忌規範審核服務
    ├── pharmacy_crawler.py  # 四大連鎖藥局爬蟲、商品資料庫與即時行情比價
    ├── auto_order.py        # 藥局自動化代理下單管道
    ├── weather_service.py   # CWA 氣象署氣溫、溫差與濕度即時解析服務
    ├── greeting_generator.py# AI 關懷小語多語氣多情境合成器
    └── requirements.txt     # 後端 Python 依賴套件清單
```

---

## 🚀 本地環境部署與啟動指南 (Deployment Guide)

### 系統環境要求
- **作業系統**：Windows 10 / 11、macOS 或 Linux
- **Python 環境**：Python 3.10 以上（建議 3.11）
- **瀏覽器**：Google Chrome、Microsoft Edge、Safari 或 Firefox 最新版本

### 步驟 1：安裝後端依賴套件
開啟終端機 (PowerShell 或 Command Prompt)，進入 `backend` 目錄執行：
```bash
cd backend
pip install -r requirements.txt
```

### 步驟 2：啟動 Python 後端服務
您可以使用專案根目錄的快捷批次檔：
- 雙擊執行 `run_backend.bat`

或手動透過終端機啟動：
```bash
cd backend
python main.py
```
> 後端服務就緒後，將監聽於 `http://127.0.0.1:8000`。您可造訪 `https://giftsense-vjbu.onrender.com/docs` 檢視完整的 Swagger 互動式 API 文件。

### 步驟 3：啟動前端 SPA
- 直接以瀏覽器開啟根目錄下的 `index.html`。
- 系統將自動偵測後端服務狀態（右上角顯示後端連線指示燈），並同步載入本機資料庫與實時功能。

---

## 🛡️ 容錯與降級機制 (Resilience & Fallback Strategy)

本系統具備業界級的高可用設計，在以下異常情境下仍能維持系統正常運行：

1. **後端服務離線 (Offline Fallback)**：
   前端內建智慧降級機制。若 Python 後端未啟動，SPA 會自動切換至「本機 Mock 引擎」，利用前端記憶體與 LocalStorage 呈現精選商品與離線檢索，**完全不阻斷使用者操作**。
2. **外部 API 限流或中斷 (API Circuit Breaking)**：
   若 Gemini API Key 耗盡或 CWA 氣象服務斷線，系統立即平滑降級至靜態氣象快取與在地臨床文獻規則庫，杜絕介面白屏或無回應現象。
3. **資料庫防崩潰防護 (Storage Guard)**：
   所有 LocalStorage 資料存取均經過 `safeJSONParse` 處理，避免因 JSON 格式破損導致客戶端腳本拋出未攔截之例外。

---

## 🐳 Docker 容器化一鍵部署指南 (Docker Deployment)

本專案支援完整的前後端容器化部署（FastAPI 後端 + Nginx 前端反向代理 + SQLite 資料持久化）：

### 方式一：Windows 雙擊一鍵啟動（最推薦）
1. 請確認已開啟電腦中的 **Docker Desktop**（右下角系統匣鯨魚圖示正常運行）。
2. 在 `care_gifting_app` 資料夾中，直接雙擊 **`run_docker.bat`**。
3. 容器啟動完成後，開啟瀏覽器造訪：
   - 🌟 **前端應用介面**：`http://localhost:8080`
   - 📚 **後端 Swagger API 文件**：`http://localhost:8000/docs`
   - 💓 **後端健康檢查**：`http://localhost:8000/api/health`
4. 若需停止服務，雙擊 **`stop_docker.bat`** 即可。

### 方式二：終端機命令列啟動
進入 `care_gifting_app` 目錄，執行：
```bash
# 建置並背景啟動所有容器
docker compose up -d --build

# 查看容器狀態
docker compose ps

# 查看後端即時日誌
docker compose logs -f backend

# 停止容器
docker compose down
```

---

## 🗺️ 後續開發里程碑 (Engineering Roadmap)

- [x] **Docker 容器化**：提供 `Dockerfile` 與 `docker-compose.yml`，實現前後端一鍵容器化部署。
- [ ] **Playwright 實體瀏覽器自動化**：將 `auto_order.py` 擴充至真實 Playwright Headless 流程，實現藥局購物車全自動結帳。
- [ ] **PWA (Progressive Web App) 離線快取支援**：加入 Service Worker 與 Web App Manifest，支援安裝至行動裝置桌面。
- [ ] **親友端簡易版 (Elder Accessibility Mode)**：超大字體、高對比度、語音念讀 (Web Speech Synthesis API) 專屬介面。

---

*文檔維護人員：CareGift 全棧架構工程師 (System & Solution Architect)*  
*最後更新日期：2026 年 09 月*

