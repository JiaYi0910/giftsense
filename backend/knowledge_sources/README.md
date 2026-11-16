# AI 守護助理的知識來源

AI 守護助理（RAG）回答時引用的原文都放在這個資料夾，清單在 `sources.json`。
每個來源都記錄標題、機構、網址、授權與查證紀錄；**沒有經過查證的來源不放進清單**。

## 資料夾

| 位置 | 內容 | 怎麼來的 |
|---|---|---|
| `us_gov/` | NIH NCCIH、FDA、NEI、NHLBI、NCI 的衛教網頁原文 | `python tools/fetch_sources.py` 下載（美國聯邦政府著作，屬公有領域） |
| `drug_labels/` | FDA 核准仿單的「Drug Interactions」段落（Warfarin、Levothyroxine） | 同上，經 openFDA API 取得 |
| `tw/` | 食藥署、國健署查詢系統的結果頁 | **由你用瀏覽器存檔**（見下方） |
| `manual/` | NIH ODS Fact Sheets 等網站擋程式下載的頁面 | **由你用瀏覽器存檔**（見下方） |

`content` 欄位的意思：

- `fetch_html`／`fetch_openfda_label`：由 `tools/fetch_sources.py` 下載原文
- `manual`：需要你存檔；檔案放進來之前，這個來源**不會**出現在回答的出處裡
- `link_only`：只放連結與書目，不存全文（期刊論文、WHO、學會指引等有著作權的內容，或網站擋程式下載）

## 你需要存檔的檔案

存成「網頁，完整」（.html）或 PDF 都可以，檔名開頭要和來源 id 相同。

| 來源 id | 要存的頁面 | 存到 |
|---|---|---|
| `tfda_food_material` | [食品原料整合查詢平臺](https://consumer.fda.gov.tw/Food/Material.aspx?nodeID=160)：分別查「輔酶 Q10」「紅麴」「納豆」並存結果頁 | `tw/tfda_food_material_q10.html`、`tw/tfda_food_material_red_yeast.html`、`tw/tfda_food_material_natto.html` |
| `tfda_health_food` | [健康食品許可證查詢](https://consumer.fda.gov.tw/Food/InfoHealthFood.aspx?nodeID=162)：常見成分（魚油、葉黃素、益生菌、紅麴）的許可資料頁 | `tw/tfda_health_food_<成分>.html` |
| `tfda_drug_safety` | [藥品安全資訊](https://www.fda.gov.tw/TC/siteList.aspx?sid=1571)：與保健品交互作用相關的公告頁 | `tw/tfda_drug_safety_<主題>.html` |
| `hpa_dri` | [國人膳食營養素參考攝取量 第八版](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4248&pid=12285)：鈣、維生素 D、B 群、鋅的建議量與上限 | `tw/hpa_dri.pdf` |
| `ods_omega3fattyacids` 等 8 個 | NIH ODS 專業版 Fact Sheets（網址在 `sources.json`） | `manual/ods_<名稱>.html`，例如 `manual/ods_calcium.html` |

存好後：

1. 在 `sources.json` 該來源的 `url` 填入實際頁面網址（查詢系統的結果頁網址），`verified` 改成存檔日期與「瀏覽器開啟，內容相符」。
2. 重新啟動後端，或在管理後台呼叫 `POST /api/knowledge/sources/reload`，系統會重新切段落並寫入資料庫。

## 指令（在 backend 資料夾）

```bash
python tools/fetch_sources.py              # 重新下載公開網頁與仿單（網頁改版時頁面標題對不上會停止，不會寫入錯誤內容）
python tools/fetch_sources.py nccih_ginkgo # 只下載指定來源
python -m pytest tests/test_knowledge_base.py -q
```

## 切段方式

- 中文約 300–500 字一段；英文約 150–250 個單字一段（英文單字資訊量較大，同樣長度的段落不會過長）
- 以段落、句子為界，小節標題併入下一段；網頁的參考文獻、延伸資源、免責聲明與聯絡資訊不收
- 每段存成 `knowledge_chunks` 資料表的一列：`source_title`、`authority`、`url`、`ingredient`、`chunk_text`
- 啟動時比對清單與所有原文檔的雜湊值，內容有變才重新匯入
