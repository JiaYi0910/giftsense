# RAG 知識庫：待人工查證清單

> 更新：2026/11/16（RAG 第一階段：知識庫改為可查證的官方出處）
>
> 原則：**無法確認真實存在的來源一律不寫入知識庫**。查證方式記錄在 `backend/knowledge_sources/sources.json` 每個來源的 `verified` 欄位：
> 期刊以 PubMed ECitMatch（比對期刊、年份、卷號、頁碼）或 Crossref DOI 確認；網站以 HTTP 200 且頁面標題相符確認。

## 一、已移除：查無出處的引用

| 原本的引用 | 出現在 | 查證結果 | 處理 |
|---|---|---|---|
| J Am Coll Cardiol. 2014;64(14):1456-1463 | 輔酶 Q10 卡片 | PubMed ECitMatch 查無此期刊頁碼 | 移除，改用 NIH NCCIH Coenzyme Q10 |
| 衛署食字第 0950400854 號 | 輔酶 Q10 卡片 | 無法查證公告內容 | 移除；待你補食藥署原料頁（`tfda_food_material`） |
| 衛署食字第 0960408532 號 | 紅麴卡片、紅麴＋Statin 規則 | 無法查證公告內容 | 移除，改用 NIH NCCIH Red Yeast Rice 與 EFSA 2018 |
| 衛署藥輸字第 018245 號仿單禁忌 | 抗凝血藥＋納豆激酶規則 | 無法查證 | 移除，改用 FDA Warfarin 仿單（DailyMed）與 Sci Rep 2015 |
| TFDA 藥品安全通訊第 48 期 | 抗凝血藥＋銀杏規則 | 無法查證 | 移除，改用 NIH NCCIH Ginkgo、Herb-Drug Interactions 與 Warfarin 仿單 |
| J Clin Hypertens 2017 | 高血壓＋甘草規則 | 引用不完整，無法查證 | 移除，改用 NIH NCCIH Licorice Root |
| 「TFDA 衛署食字公告」「TFDA 藥品安全通報」「TFDA 傷口照護衛教規範」「TFDA 衛教資訊」「衛福部食藥署 用藥安全衛教」 | 多條規則 | 沒有具體出處 | 移除；有官方依據的改用該來源，沒有的標示「尚無官方依據」 |
| 日本納豆激酶協會（JNKA）、日本機能性表示食品（CAA）、國際神經學聯盟（WFN）、OARSI、EAU、ASPEN、台灣失智症協會 等機構名稱 | 卡片的「權威機構」 | 引用的文獻並非這些機構發表 | 權威機構改為實際引用來源的機構 |

另外更正了兩篇真實存在、但**標題寫錯**的期刊引用：ESCEO 2019（實際標題 An updated algorithm recommendation for the management of knee osteoarthritis…）、Yamatsu 2016（實際標題 Effect of oral γ-aminobutyric acid (GABA) administration on sleep and its absorption in humans）。

## 二、已更正：與官方原文矛盾的內容

| 項目 | 原本寫法 | 官方原文 | 出處 |
|---|---|---|---|
| 葡萄糖胺卡片 | 「一般不具抗凝血交互作用，心血管患者可安心替代」 | 葡萄糖胺／軟骨素與服用 Warfarin 者的出血風險增加有關，也可能使血糖上升 | NIH NCCIH：Glucosamine and Chondroitin |
| 抗凝血藥＋納豆激酶、抗凝血藥＋魚油／薑黃規則 | 替代商品推薦葡萄糖胺，「臨床證實不干擾凝血」「完全零 Warfarin 撞藥風險」 | 同上（葡萄糖胺會增加出血風險） | 同上；替代商品已移除，並新增「Warfarin＋葡萄糖胺」規則 |
| 紅麴＋Statin 規則 | 替代商品推薦輔酶 Q10，「衛福部與 ACC 認可……舒緩肌肉酸痛」 | 整體證據不支持輔酶 Q10 能減輕 Statin 造成的肌肉痠痛 | NIH NCCIH：Coenzyme Q10；替代商品已移除 |
| 輔酶 Q10 卡片 | 標題「Statin 肌肉酸痛緩解之臨床回顧」 | 同上；另可能與 Warfarin、胰島素交互作用 | NIH NCCIH；並新增「Warfarin＋輔酶 Q10」規則 |
| 薑黃卡片 | 「搭配 Piperine 可提高 2,000% 生物利用率」 | 高生物利用率的薑黃素配方曾有肝損傷案例 | NIH NCCIH：Turmeric |
| 蔓越莓卡片與規則 | 「重大交互作用……嚴禁」 | 蔓越莓是否與 Warfarin 交互作用，證據不一致 | NIH NCCIH：Cranberry、Herb-Drug Interactions |
| 葉黃素卡片 | 「有效過濾藍光……延緩視力退化」 | AREDS2 主要分析：加入葉黃素＋玉米黃素沒有進一步降低惡化成晚期黃斑部病變的風險 | AREDS2，JAMA 2013（PMID 23644932） |
| 紅麴卡片 | 「每日 Monacolin K 4.8–10 mg（TFDA 上限 15 mg）」 | 產品含量差異大且多未標示；EFSA 2018 認為 Monacolin K 可能造成嚴重副作用 | NIH NCCIH：Red Yeast Rice |
| 未命中規則時的說明（後端與 App） | 「經比對衛福部食藥署藥品交互作用資料庫……相容度高達 98%」 | 系統並沒有查詢食藥署的資料庫，98% 也沒有根據 | 改為「未命中本系統收錄的 20 條規則，不代表確定沒有交互作用」 |
| App 連不上後端時 | 顯示固定的「鈣片＋TFDA 相容 98%」示範答案 | — | 移除示範答案，只顯示無法連線的提示 |

其餘 5 條規則（抗凝血＋銀杏推薦 B 群、抗凝血＋蔓越莓推薦益生菌、傷口與糖尿病推薦完膳、高血壓甘草推薦芝麻明）的替代商品理由也沒有官方依據，一併移除；命中規則時一律不推薦商品，請使用者先詢問醫師或藥師。

## 三、保留但尚無已存原文佐證的內容（待補來源）

| 內容 | 位置 | 待補來源 |
|---|---|---|
| 魚油與抗凝血藥併用的出血風險 | 魚油卡片、抗凝血藥＋魚油／薑黃規則 | NIH ODS Omega-3 Fatty Acids（`ods_omega3fattyacids`）；NCCIH 的 Omega-3 頁沒有提到這點 |
| 食藥署的劑量上限與警語（輔酶 Q10、紅麴、葉黃素的每日上限；Q10「孕婦、哺乳、15 歲以下不宜」標示） | 輔酶 Q10、紅麴、葉黃素卡片、孕期規則 | 食品原料整合查詢平臺（`tfda_food_material`） |
| 鈣、維生素 D 的建議量與上限 | 鈣與維生素 D 卡片 | 國人膳食營養素參考攝取量（`hpa_dri`）、NIH ODS Calcium／Vitamin D |
| 維生素 B 群劑量與 B6 長期過量的神經病變 | 維生素 B 群卡片 | NIH ODS B12／B6／Thiamin |
| 鋅與蛋白質幫助傷口癒合 | 鋅卡片 | 目前引用的 ESPEN 2019 是**加護病房**營養指引，與「銀髮族傷口癒合」不完全相符；建議改找傷口照護或壓瘡營養指引，並補 NIH ODS Zinc |
| 芝麻素的助眠效果 | GABA＋芝麻素卡片 | 引用的 Yamatsu 2016 只研究 GABA，沒有芝麻素 |
| D-甘露糖預防泌尿道感染 | 蔓越莓卡片 | 引用的 Cochrane 2023 只回顧蔓越莓 |
| 綜合感冒藥（擬交感神經成分）使血壓上升 | 感冒藥規則 | FDA OTC Monograph M012（已確認網址，PDF 內文尚未擷取比對） |
| 傷口癒合期避免活血類保健品 | 傷口規則 | 尚無官方依據 |
| 高糖滋補品影響血糖 | 糖尿病規則 | 目前只連到 ADA Standards of Care 2024 的導論，需補具體段落 |
| 國健署中風口訣「微笑、舉手、說你好」 | 心臟病與中風警訊卡片 | 國健署中風衛教頁（目前以 NIH NHLBI 與 CDC 為出處） |
| 各卡片的作用機轉、劑量數字 | 15 張保健成分卡片 | 第二階段會改為直接引用原文段落，每項主張附對應段落的來源與網址 |

## 四、網址存在但程式無法確認、需你用瀏覽器確認的來源

- **NIH ODS Fact Sheets**（8 份）：網站有機器人驗證，程式與內建瀏覽器都被擋下，未破解驗證。請用你的瀏覽器開啟並存檔。
- **AHA Warning Signs of a Heart Attack**、**ADA Standards of Care 2024 完整版**：同上；目前改用已確認的 NIH NHLBI、CDC 與 PubMed 條目。
- **NIH LiverTox**：個別成分頁有 reCAPTCHA，無法確認頁碼；目前未列入知識庫。
- **adr.fda.gov.tw**（藥物不良反應通報）：2026/11/16 查詢時網站維護中（HTTP 503）。

## 五、即時 API（第三階段）可用性

| API | 結果（2026/11/16） |
|---|---|
| openFDA 藥品仿單 | 可用，免金鑰；Warfarin 仿單的交互作用段落有提到草藥、銀杏、大蒜 |
| MedlinePlus Connect | 可用，免金鑰；以 RxCUI 查 Warfarin 回傳 MedlinePlus 藥品頁與抗凝血藥衛教頁 |
| PubMed E-utilities | 可用，免金鑰 |
| DailyMed | 可用，免金鑰 |
| NIH ODS API | 被機器人驗證擋下 |
