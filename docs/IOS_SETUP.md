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

### 在 Mac 上編譯

```bash
cd giftsense
flutter pub get
cd ios && pod install && cd ..
flutter build ios --release
```

或用 Xcode 開啟 `ios/Runner.xcworkspace`，選擇自己的 iPhone 直接執行。

- **免費 Apple ID**：可以裝到自己的 iPhone 測試（約 7 天要重新安裝一次），但**不能使用 Apple 登入**。
- **Apple Developer Program（每年 US$99）**：才能使用 Apple 登入、TestFlight 給別人測試、上架 App Store。

### 正式發佈前要做的設定

1. **Bundle ID**：目前是 `com.example.giftsense`，建議在 Xcode → Runner → General 改成正式名稱（例如 `tw.giftsense.app`），之後 Apple、Google、Facebook 都用這個名稱申請。
2. **Google 登入（iOS）**：到 Google Cloud Console 建立「iOS」類型的 OAuth 用戶端（填 Bundle ID），把 `GIDClientID` 和反轉的 Client ID URL Scheme 加進 `ios/Runner/Info.plist`。
3. **Facebook 登入（iOS）**：到 Facebook 開發者後台新增 iOS 平台，填入 Bundle ID。
4. **Apple 登入**：依 [SOCIAL_LOGIN_SETUP.md](SOCIAL_LOGIN_SETUP.md) 第 3 節操作，並在 Xcode 的 Signing & Capabilities 加入 **Sign in with Apple**。

## Apple 登入（網頁版與 Android 也適用）

程式已經寫好（前端 `sign_in_with_apple`、後端以 Apple 公開金鑰驗證身分），只差 Apple 的帳號設定：

1. 加入 Apple Developer Program。
2. 建立 App ID（勾選 Sign in with Apple）與 **Services ID**（網頁、Android 走 Apple 網頁流程時使用）。
   - Domains：`giftsense-vjbu.onrender.com`
   - Return URL：`https://giftsense-vjbu.onrender.com/api/auth/apple/callback`
3. 把 Services ID 填進 `giftsense/lib/config/social_login_config.dart` 的 `appleServiceId`，重新編譯網頁與 APK。
4. Render 環境變數新增 `APPLE_CLIENT_IDS` = `你的BundleID,你的ServicesID`（逗號分隔）。

只驗證 Apple 回傳的身分憑證，不需要 `.p8` 私鑰。
