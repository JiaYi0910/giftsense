# 社群登入與 LINE 綁定設定指南

程式碼已經完成。下面列出要到各平台申請的項目，以及申請到的值要填在哪裡。

> ⚠️ **先決定正式的 App 套件名稱**
>
> 目前 Android `applicationId` 和 iOS Bundle ID 都還是 Flutter 範本的預設值 `com.example.giftsense`。
> Facebook、Apple、Google 的設定都會綁定套件名稱，建議**先改成正式名稱**（例如 `tw.giftsense.app`）再去申請，之後就不用重新設定。
> 要改的地方：`giftsense/android/app/build.gradle.kts`（namespace、applicationId），以及 iOS 的 Bundle ID。

## 0. 後端環境變數（Render → Environment）

後端只信任**平台驗證過的 token**，所以要在 Render 設定以下環境變數。完整範例見 `backend/.env.example`。

| 變數 | 用途 | 沒設定時 |
|---|---|---|
| `GOOGLE_CLIENT_IDS` | 允許的 Google Client ID（逗號分隔） | 使用目前 App 內的 Web Client ID |
| `FACEBOOK_APP_ID` / `FACEBOOK_APP_SECRET` | 驗證 Facebook token | Facebook 登入會回「尚未設定」 |
| `APPLE_CLIENT_IDS` | iOS Bundle ID 與 Services ID（逗號分隔） | 只接受 `com.example.giftsense` |
| `ANDROID_PACKAGE_NAME` | Apple 網頁流程轉回 App 用 | `com.example.giftsense` |
| `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_CHANNEL_SECRET` | LINE 官方帳號 | 沿用程式內的舊值 |
| `LINE_BOT_BASIC_ID` | 官方帳號 ID（例如 `@123abcde`），產生加好友連結用 | 後端自動向 LINE 查詢 |

## 1. Google（已可使用，Android 上架前要補設定）

- Web 版已可使用。
- Android 版要在 [Google Cloud Console](https://console.cloud.google.com/apis/credentials) 再建一個 **Android** 類型的 OAuth Client：
  - 套件名稱填 `applicationId`。
  - SHA-1 填簽章金鑰的指紋。
  - 目前 release 是用 debug key 簽章；正式上架前請建立 release keystore，並用它的 SHA-1 再登記一次。
- App 會把 idToken（Android）或 accessToken（Web）送到後端驗證，後端會確認 token 屬於 `GOOGLE_CLIENT_IDS` 裡的 Client ID。

## 2. Facebook

1. 到 [Meta for Developers](https://developers.facebook.com/apps) 建立 App，類型選「消費者」，並加入「Facebook 登入」產品。
2. 「設定 → 基本資料」：
   - 記下 **App ID**、**App Secret**。
   - 到「設定 → 進階」取得 **Client Token**。
3. 新增 **Android** 平台：
   - 套件名稱填 `applicationId`。
   - 類別名稱填 `<applicationId>.MainActivity`。
   - 金鑰雜湊用下面的指令產生（release 金鑰也要加）：
     ```bash
     keytool -exportcert -alias androiddebugkey -keystore %USERPROFILE%\.android\debug.keystore | openssl sha1 -binary | openssl base64
     ```
4. 新增**網站**平台：網址填 `https://giftsense-vjbu.onrender.com/`。
5. 把值填進專案：
   - `giftsense/lib/config/social_login_config.dart` → `facebookAppId`
   - `giftsense/android/app/src/main/res/values/strings.xml` → `facebook_app_id`、`facebook_client_token`
   - `giftsense/android/app/src/main/AndroidManifest.xml` → 移除 Facebook `meta-data` 外面的註解
   - Render 環境變數 → `FACEBOOK_APP_ID`、`FACEBOOK_APP_SECRET`（**App Secret 只能放後端**）
6. App 還在「開發模式」時，只有被加為測試人員的 Facebook 帳號可以登入。

## 3. Apple（需要 Apple Developer Program，每年 US$99）

1. 到 [Apple Developer → Identifiers](https://developer.apple.com/account/resources/identifiers/list)，為 App ID（Bundle ID）勾選 **Sign in with Apple**。
2. 建立 **Services ID**（例如 `com.example.giftsense.signin`）。Android 與 Web 都走 Apple 的網頁流程，所以需要它。設定 Sign in with Apple：
   - Domains：`giftsense-vjbu.onrender.com`
   - Return URLs：`https://giftsense-vjbu.onrender.com/api/auth/apple/callback`
3. 把值填進專案：
   - `giftsense/lib/config/social_login_config.dart` → `appleServiceId`
   - Render 環境變數 → `APPLE_CLIENT_IDS=<Bundle ID>,<Services ID>`
4. iOS：在 Xcode 的 Signing & Capabilities 加入 **Sign in with Apple**。
5. Android：`AndroidManifest.xml` 已加入 `SignInWithAppleCallback`，不用再設定。
6. Apple 只有**第一次**授權時會提供姓名與 email，之後一律以 Apple 的使用者 ID 辨識同一個會員。

## 4. LINE 個人帳號綁定（親友接收關懷卡）

1. [LINE Developers](https://developers.line.biz/console/) 的 Messaging API channel：
   - Webhook URL：`https://giftsense-vjbu.onrender.com/api/line/webhook`
   - 開啟「Use webhook」
2. 後端現在會**驗證 `X-Line-Signature`**，所以 `LINE_CHANNEL_SECRET` 必須正確，否則 webhook 會回 400。
3. 綁定流程：
   1. App →「親友健康資料庫」→ 點親友旁邊的綠色 🔗 按鈕，產生 6 位數綁定碼（24 小時有效、用一次就失效）。
   2. 按「複製邀請訊息」，貼給親友。
   3. 親友加入官方帳號後，在聊天室傳 `綁定 123456`，就完成綁定。
4. 綁定一律使用綁定碼；尚未綁定的 LINE 使用者傳任何訊息，機器人都只會回覆綁定教學，訊息不會存入系統。
5. 關懷卡只會推播給**寄件者帳號底下**已綁定的親友。
6. 機器人回覆一律使用 Reply API（不佔官方帳號每月免費訊息額度），只有 App 主動推送的關懷卡才使用 Push。

### 圖文選單（Rich Menu）

選單圖片與設定都在 `backend/tools/`：

| 檔案 | 用途 |
|---|---|
| `make_line_richmenu_image.py` | 產生選單圖片 `line_richmenu.png`（需要 `pip install pillow`） |
| `setup_line_richmenu.py` | 把選單套用到 LINE 官方帳號 |

在 `backend` 資料夾執行：

```bash
python tools/setup_line_richmenu.py
```

不加參數只會預覽。確認沒問題後加上 `--apply`，會先刪除舊的「GiftSense 主選單」，再建立新選單並設為所有使用者的預設選單：

```bash
python tools/setup_line_richmenu.py --apply
```

選單 6 個按鈕送出的文字（今日關懷、今日用藥、緊急求助、綁定說明、服務說明、我的綁定）由 `main.py` 的 `LINE_CMD_*` 處理。修改按鈕時，兩邊要一起改。

## 5. 密鑰安全

- `backend/main.py` 裡的 LINE Channel access token 和 secret，之前已經以明碼推上 GitHub。建議：
  1. 到 LINE Developers **重新發行**這兩個值。
  2. 把新的值設在 Render 環境變數。
  3. 移除程式碼裡的預設值。
