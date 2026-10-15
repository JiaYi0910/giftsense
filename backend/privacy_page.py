# -*- coding: utf-8 -*-
"""GiftSense 隱私權政策公開網頁（/privacy），可填在 Facebook 等開發者後台的「隱私政策網址」"""

PRIVACY_UPDATED = "2026 年 10 月 15 日"

PRIVACY_HTML = f"""<!DOCTYPE html>
<html lang="zh-Hant-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GiftSense 隱私權政策</title>
<style>
  :root {{ --blue:#2563EB; --ink:#0F172A; --slate:#475569; --line:#DBEAFE; }}
  body {{ margin:0; background:linear-gradient(180deg,#F4F8FF,#E9F0FF); color:var(--ink);
         font-family:-apple-system,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif; line-height:1.75; }}
  main {{ max-width:760px; margin:0 auto; padding:32px 20px 56px; }}
  .card {{ background:#fff; border:1px solid var(--line); border-radius:24px; padding:28px 26px;
          box-shadow:0 12px 32px rgba(37,99,235,.08); }}
  h1 {{ font-size:24px; margin:0 0 4px; }}
  .meta {{ color:var(--slate); font-size:13px; margin-bottom:20px; }}
  h2 {{ font-size:16px; color:#1E3A8A; margin:24px 0 6px; }}
  p, li {{ font-size:14.5px; color:var(--ink); }}
  ul {{ padding-left:20px; margin:6px 0; }}
  a {{ color:var(--blue); }}
  .back {{ display:inline-block; margin-top:24px; font-weight:700; text-decoration:none; }}
</style>
</head>
<body>
<main>
  <div class="card">
    <h1>GiftSense 隱私權政策</h1>
    <div class="meta">最後更新：{PRIVACY_UPDATED}</div>
    <p>GiftSense（智慧關懷送禮）重視你與親友的隱私。本政策說明我們蒐集哪些資料、如何使用與保護，以及你可以如何管理自己的資料。</p>

    <h2>一、我們蒐集的資料</h2>
    <ul>
      <li>會員資料：帳號、顯示名稱、Email、手機與生日（選填）、頭貼。</li>
      <li>第三方登入：使用 Google 或 Facebook 登入時，取得該服務提供的識別碼、名稱、Email 與大頭照。</li>
      <li>親友資料：你建立的親友姓名、健康狀況與用藥資訊，用於提供關懷提醒與用藥安全檢查。</li>
      <li>訊息資料：傳情小站的對話內容，以及親友綁定 LINE 時所需的 LINE 使用者識別碼。</li>
      <li>點數紀錄：暖幣點數、兌換與購物回饋紀錄。</li>
      <li>購物收據：申請購物回饋時上傳的收據、電子發票或訂單完成畫面。我們只保存辨識出的藥局名稱、訂單或發票號碼、購買時間與金額，以及用來防止重複登錄的圖片雜湊值，不保存收據圖片。</li>
    </ul>

    <h2>二、使用目的</h2>
    <ul>
      <li>提供每日關懷提醒、天氣叮嚀、AI 守護助理的用藥安全檢查與暖心選物推薦。</li>
      <li>在家人與親友之間傳遞關懷卡與訊息（包含推播至已綁定的 LINE）。</li>
      <li>計算暖幣點數與購物回饋，並核對收據避免重複或不實的回饋申請。</li>
    </ul>
    <p>我們不會販售你的個人資料，也不使用廣告或追蹤分析工具。</p>

    <h2>三、第三方服務</h2>
    <ul>
      <li>Google、Facebook：第三方登入。</li>
      <li>LINE：關懷卡與訊息推播。</li>
      <li>中央氣象署開放資料：天氣資訊（不傳送個人資料）。</li>
      <li>Google Gemini：你上傳的購物收據圖片會傳送給 Google 的 Gemini API 辨識藥局、訂單號碼、購買時間與金額。圖片僅用於這次辨識，GiftSense 不保存；Google 依其 Gemini API 條款處理傳送的資料（使用免費方案時，Google 可能將資料用於改善其服務）。</li>
      <li>Turso、Render：雲端資料庫與伺服器代管。</li>
    </ul>
    <p>我們只提供各服務運作所需的最少資料，各服務另依其隱私權政策處理資料。</p>

    <h2>四、Cookie 與瀏覽器儲存</h2>
    <ul>
      <li>必要項目：維持登入狀態、記住你選擇的親友與介面設定。</li>
      <li>第三方登入：使用 Google 或 Facebook 登入時，該服務會設定自己的 Cookie。</li>
    </ul>
    <p>網頁版第一次開啟時會詢問你的同意，你可以隨時在「隱私權與 Cookie 設定」中更改。</p>

    <h2>五、資料保存與安全</h2>
    <p>資料保存在加密傳輸的雲端資料庫，僅用於提供本服務。管理後台僅限授權的管理員使用。</p>

    <h2>六、你的權利</h2>
    <p>你可以在個人資料設定中查看或修改會員資料，也可以刪除建立的親友資料。若要查詢、更正或刪除帳號與所有相關資料，請透過 GiftSense LINE 官方帳號與我們聯繫，我們會在確認身分後處理。</p>

    <h2>七、政策更新</h2>
    <p>本政策若有重大變更，會在網站上公告。</p>

    <a class="back" href="/">← 回到 GiftSense</a>
  </div>
</main>
</body>
</html>
"""
