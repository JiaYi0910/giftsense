# iOS 使用與 Apple 登入設定

## 方式一：iPhone 加入主畫面（免費，現在就能用）

GiftSense 的網頁版已針對 iPhone 調整，加入主畫面後會以全螢幕、GiftSense 圖示的 App 方式開啟。

1. 用 iPhone 的 **Safari** 開啟 <https://giftsense-vjbu.onrender.com>
2. 點下方「分享」按鈕 → **加入主畫面** → 新增
3. 之後從主畫面的 GiftSense 圖示開啟即可

| 功能 | 加入主畫面版 |
|---|---|
| 帳號密碼登入、Google 登入 | 可以使用 |
| Facebook 登入 | 完成 Facebook 開發者後台的網域設定後可以使用 |
| Apple 登入 | 需要 Apple Developer Program（見下方） |
| 換頭貼（相簿／拍照）、傳情小站、AI 守護助理、暖心選物 | 可以使用 |

## 方式二：原生 iOS App（需要 Mac）

iOS App 只能在 **macOS + Xcode** 上編譯，Windows 無法產出 iPhone 安裝檔。專案已預先設定好：

- App 名稱 GiftSense、各尺寸 App 圖示（`ios/Runner/Assets.xcassets/AppIcon.appiconset`）
- 相簿／相機使用說明（換頭貼用，沒有的話 iOS 會直接關閉 App）
- Facebook 登入的 App ID、Client Token、URL Scheme

### 用免費 Apple ID 裝到自己的 iPhone（Mac 上操作）

**一、準備（只需做一次）**

1. 從 App Store 安裝 **Xcode**，打開一次並同意授權；終端機執行 `xcode-select --install`。
2. 安裝 Flutter（macOS 版）與 CocoaPods：`brew install cocoapods`（沒有 Homebrew 可用 `sudo gem install cocoapods`）。
3. 把 Windows 上的 `giftsense` 資料夾整個複製到 Mac（`build`、`.dart_tool` 資料夾不用複製）。

**二、第一次編譯**

```bash
cd giftsense
flutter pub get
cd ios && pod install && cd ..
open ios/Runner.xcworkspace
```

在 Xcode 左側點 **Runner** → **Signing & Capabilities**：

- **Team**：選「Add an Account…」登入你的 Apple ID，選擇「(Personal Team)」。
- **Bundle Identifier**：免費帳號需要獨一無二的名稱，把 `com.example.giftsense` 改成例如 `com.你的英文名.giftsense`。

**三、裝到 iPhone**

1. iPhone 用傳輸線接上 Mac，在 iPhone 上點「信任這部電腦」。
2. iPhone：設定 → 隱私權與安全性 → **開發者模式** → 開啟（會要求重新開機）。
3. Xcode 上方選擇你的 iPhone，按 ▶ 執行。
4. 第一次開啟若顯示「不受信任的開發者」：iPhone 設定 → 一般 → **VPN 與裝置管理** → 信任你的 Apple ID。

免費 Apple ID 安裝的 App 約 **7 天**後會失效，接上 Mac 再按一次 ▶ 就能重新安裝。

| 功能 | 免費 Apple ID 版 |
|---|---|
| 帳號密碼登入、傳情小站、AI 守護助理、換頭貼 | 可以使用 |
| Google 登入 | 需另外建立 iOS 用的 Google OAuth 用戶端（免費，見下方） |
| Facebook 登入 | 需在 Facebook 開發者後台新增 iOS 平台（免費，見下方） |
| Apple 登入 | 無法使用（按鈕會顯示「尚未開放」） |
| 給別人安裝、上架 App Store | 需要 Apple Developer Program（每年 US$99） |

### 正式發佈前要做的設定

1. **Bundle ID**：目前是 `com.example.giftsense`，建議在 Xcode → Runner → General 改成正式名稱（例如 `tw.giftsense.app`），之後 Apple、Google、Facebook 都用這個名稱申請。
2. **Google 登入（iOS）**：到 Google Cloud Console 建立「iOS」類型的 OAuth 用戶端（填 Bundle ID），把 `GIDClientID` 和反轉的 Client ID URL Scheme 加進 `ios/Runner/Info.plist`。
3. **Facebook 登入（iOS）**：到 Facebook 開發者後台新增 iOS 平台，填入 Bundle ID。
4. **Apple 登入**：依 [SOCIAL_LOGIN_SETUP.md](SOCIAL_LOGIN_SETUP.md) 第 3 節操作，並在 Xcode 的 Signing & Capabilities 加入 **Sign in with Apple**。

## Apple 登入（網頁版與 Android 也適用）

目前採免費方案：Apple 按鈕會顯示「Apple 登入尚未開放」，引導改用其他登入方式。之後若加入 Apple Developer Program，程式已經寫好（前端 `sign_in_with_apple`、後端以 Apple 公開金鑰驗證身分），只差 Apple 的帳號設定：

1. 加入 Apple Developer Program。
2. 建立 App ID（勾選 Sign in with Apple）與 **Services ID**（網頁、Android 走 Apple 網頁流程時使用）。
   - Domains：`giftsense-vjbu.onrender.com`
   - Return URL：`https://giftsense-vjbu.onrender.com/api/auth/apple/callback`
3. 把 Services ID 填進 `giftsense/lib/config/social_login_config.dart` 的 `appleServiceId`，重新編譯網頁與 APK。
4. Render 環境變數新增 `APPLE_CLIENT_IDS` = `你的BundleID,你的ServicesID`（逗號分隔）。

只驗證 Apple 回傳的身分憑證，不需要 `.p8` 私鑰。
