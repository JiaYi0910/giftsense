# -*- coding: utf-8 -*-
"""
RAG 第三階段：即時查詢美國官方開放資料（不需要金鑰）

- openFDA 藥品仿單 API（https://open.fda.gov/apis/drug/label/）：依藥品學名取最新一份有「Drug Interactions」段落的仿單，
  摘出提到該保健成分的原文句子，附 DailyMed 仿單網址
- RxNorm API（https://lhncbc.nlm.nih.gov/RxNav/）：藥品學名 → RxCUI
- MedlinePlus Connect（https://medlineplus.gov/medlineplus-connect/）：RxCUI → MedlinePlus 給一般民眾看的藥品衛教頁

原則：
- 交互作用規則仍是安全底線；即時資料只補充原文與連結，不會取消規則的警示
- 只查親友病況或問題中辨識出的「具體藥名」（例如 可邁丁 → warfarin）；「抗凝血藥」這類類別詞不查
- 查詢結果存在資料庫 live_source_cache（查到或確定查無：30 天；連線失敗：1 小時），每次問答最多等 LIVE_TIMEOUT 秒，逾時就略過
- 環境變數 LIVE_SOURCES=off 可整個關閉（測試預設關閉）；OPENFDA_API_KEY 可選，用來提高 openFDA 每日查詢上限
"""
import json
import os
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta

import requests

LIVE_TIMEOUT = 6            # 每次問答最多等幾秒（Render 免費方案，避免畫面卡住）
HTTP_TIMEOUT = 5
CACHE_DAYS = 30
FAIL_RETRY_HOURS = 1
MAX_DRUGS = 2
MAX_EXCERPTS = 3
EXCERPT_CHARS = 420

OPENFDA_URL = "https://api.fda.gov/drug/label.json"
RXNAV_URL = "https://rxnav.nlm.nih.gov/REST/rxcui.json"
MEDLINEPLUS_URL = "https://connect.medlineplus.gov/service"
DAILYMED_URL = "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid="
UA = "GiftSense/1.0 (care gifting app; RAG live lookup)"

# 具體藥名：台灣常見商品名、中文學名 → 美國仿單使用的學名
# fda_names：openFDA 的 generic_name（複方藥需要指定，否則以學名大寫比對）
DRUGS = [
    {"generic": "warfarin", "zh": "Warfarin（可邁丁）", "aliases": ["warfarin", "可邁丁", "coumadin", "華法林"]},
    {"generic": "apixaban", "zh": "Apixaban（艾必克凝）", "aliases": ["apixaban", "艾必克凝", "eliquis"]},
    {"generic": "rivaroxaban", "zh": "Rivaroxaban（拜瑞妥）", "aliases": ["rivaroxaban", "拜瑞妥", "xarelto"]},
    {"generic": "dabigatran", "zh": "Dabigatran（普栓達）", "aliases": ["dabigatran", "普栓達", "pradaxa"],
     "fda_names": ["DABIGATRAN ETEXILATE", "DABIGATRAN ETEXILATE MESYLATE"]},
    {"generic": "edoxaban", "zh": "Edoxaban（里先安）", "aliases": ["edoxaban", "里先安", "lixiana", "savaysa"]},
    {"generic": "clopidogrel", "zh": "Clopidogrel（保栓通）", "aliases": ["clopidogrel", "保栓通", "plavix"],
     "fda_names": ["CLOPIDOGREL", "CLOPIDOGREL BISULFATE"]},
    {"generic": "atorvastatin", "zh": "Atorvastatin（立普妥）", "aliases": ["atorvastatin", "立普妥", "lipitor"],
     "fda_names": ["ATORVASTATIN CALCIUM"]},
    {"generic": "rosuvastatin", "zh": "Rosuvastatin（冠脂妥）", "aliases": ["rosuvastatin", "冠脂妥", "crestor"],
     "fda_names": ["ROSUVASTATIN CALCIUM"]},
    {"generic": "simvastatin", "zh": "Simvastatin（素果）", "aliases": ["simvastatin", "素果", "zocor"]},
    {"generic": "amlodipine", "zh": "Amlodipine（脈優）", "aliases": ["amlodipine", "脈優", "norvasc"],
     "fda_names": ["AMLODIPINE BESYLATE"]},
    {"generic": "losartan", "zh": "Losartan（可悅您）", "aliases": ["losartan", "可悅您", "cozaar"],
     "fda_names": ["LOSARTAN POTASSIUM"]},
    {"generic": "valsartan", "zh": "Valsartan（得安穩）", "aliases": ["valsartan", "得安穩", "diovan"]},
    {"generic": "metformin", "zh": "Metformin（二甲雙胍）", "aliases": ["metformin", "二甲雙胍", "glucophage"],
     "fda_names": ["METFORMIN HYDROCHLORIDE"]},
    {"generic": "levothyroxine", "zh": "Levothyroxine（昂特欣）", "aliases": ["levothyroxine", "昂特欣", "eltroxin", "synthroid"],
     "fda_names": ["LEVOTHYROXINE SODIUM"]},
    {"generic": "zolpidem", "zh": "Zolpidem（使蒂諾斯）", "aliases": ["zolpidem", "使蒂諾斯", "史蒂諾斯", "stilnox"],
     "fda_names": ["ZOLPIDEM TARTRATE"]},
    {"generic": "alprazolam", "zh": "Alprazolam（贊安諾）", "aliases": ["alprazolam", "贊安諾", "xanax"]},
    {"generic": "estazolam", "zh": "Estazolam（悠樂丁）", "aliases": ["estazolam", "悠樂丁", "eurodin"]},
    {"generic": "lorazepam", "zh": "Lorazepam（安定文）", "aliases": ["lorazepam", "安定文", "ativan"]},
    {"generic": "digoxin", "zh": "Digoxin（地高辛）", "aliases": ["digoxin", "地高辛", "lanoxin"]},
    {"generic": "levodopa", "zh": "Levodopa（左旋多巴）", "aliases": ["levodopa", "左旋多巴", "sinemet", "心寧美"],
     "fda_names": ["CARBIDOPA AND LEVODOPA"]},
    {"generic": "ibuprofen", "zh": "Ibuprofen（布洛芬）", "aliases": ["ibuprofen", "布洛芬"]},
    {"generic": "acetaminophen", "zh": "Acetaminophen（乙醯胺酚／普拿疼）", "aliases": ["acetaminophen", "乙醯胺酚", "普拿疼", "panadol"]},
]

# 保健成分：問題中的中英文說法 → 仿單英文原文的比對字詞；herbal＝屬於草本產品，可一併摘錄仿單對草本產品的整體提醒
SUPPLEMENTS = [
    {"key": "ginkgo", "zh": "銀杏", "aliases": ["銀杏", "ginkgo", "egb"], "pattern": r"ginkgo", "herbal": True},
    {"key": "garlic", "zh": "大蒜", "aliases": ["大蒜", "蒜精", "garlic"], "pattern": r"garlic", "herbal": True},
    {"key": "fish_oil", "zh": "魚油（Omega-3）", "aliases": ["魚油", "omega-3", "omega3", "epa", "dha"],
     "pattern": r"fish oil|omega-3|omega 3", "herbal": False},
    {"key": "coq10", "zh": "輔酶 Q10", "aliases": ["q10", "輔酶", "輔酵素", "coenzyme"],
     "pattern": r"coenzyme q|ubidecarenone|coq10|co-q10", "herbal": False},
    {"key": "glucosamine", "zh": "葡萄糖胺", "aliases": ["葡萄糖胺", "glucosamine"], "pattern": r"glucosamine", "herbal": False},
    {"key": "cranberry", "zh": "蔓越莓", "aliases": ["蔓越莓", "cranberry"], "pattern": r"cranberr", "herbal": True},
    {"key": "red_yeast_rice", "zh": "紅麴", "aliases": ["紅麴", "red yeast", "monacolin"], "pattern": r"red yeast", "herbal": True},
    {"key": "turmeric", "zh": "薑黃", "aliases": ["薑黃", "turmeric", "curcumin"], "pattern": r"turmeric|curcumin", "herbal": True},
    {"key": "ginseng", "zh": "人參", "aliases": ["人參", "人蔘", "ginseng"], "pattern": r"ginseng", "herbal": True},
    {"key": "st_johns_wort", "zh": "聖約翰草", "aliases": ["聖約翰草", "st. john", "st john", "金絲桃"],
     "pattern": r"st\.? john'?s|hypericum", "herbal": True},
    {"key": "grapefruit", "zh": "葡萄柚", "aliases": ["葡萄柚", "grapefruit"], "pattern": r"grapefruit", "herbal": False},
    {"key": "licorice", "zh": "甘草", "aliases": ["甘草", "licorice"], "pattern": r"licorice|liquorice|glycyrrhiz", "herbal": True},
    {"key": "vitamin_k", "zh": "維生素 K", "aliases": ["維生素k", "維他命k", "vitamin k"], "pattern": r"vitamin k", "herbal": False},
    {"key": "calcium", "zh": "鈣", "aliases": ["鈣", "calcium"], "pattern": r"calcium", "herbal": False},
    {"key": "iron", "zh": "鐵劑", "aliases": ["鐵劑", "補鐵", "iron"], "pattern": r"\biron\b|ferrous", "herbal": False},
    {"key": "magnesium", "zh": "鎂", "aliases": ["鎂", "magnesium"], "pattern": r"magnesium", "herbal": False},
    {"key": "potassium", "zh": "鉀（低鈉鹽）", "aliases": ["鉀", "低鈉鹽", "potassium"], "pattern": r"potassium", "herbal": False},
    {"key": "melatonin", "zh": "褪黑激素", "aliases": ["褪黑", "melatonin"], "pattern": r"melatonin", "herbal": False},
    {"key": "valerian", "zh": "纈草", "aliases": ["纈草", "valerian"], "pattern": r"valerian", "herbal": True},
    {"key": "alcohol", "zh": "酒精", "aliases": ["酒", "alcohol"], "pattern": r"alcohol|ethanol", "herbal": False},
]
_HERBAL_PATTERN = r"botanical|herbal"


def enabled() -> bool:
    return os.getenv("LIVE_SOURCES", "on").strip().lower() not in ("off", "0", "false", "no")


def detect_drugs(*texts) -> list:
    text = " ".join(t or "" for t in texts).lower()
    return [d for d in DRUGS if any(a in text for a in d["aliases"])][:MAX_DRUGS]


def detect_supplement(*texts):
    for t in texts:
        low = (t or "").lower()
        for s in SUPPLEMENTS:
            if any(a in low for a in s["aliases"]):
                return s
    return None


# -------------------------------------------------------------------------
# 原文句子
# -------------------------------------------------------------------------
_ABBR = re.compile(r"(?:\be\.g|\bi\.e|\bSt|\bDr|\bvs|\betc|\bapprox|\bNo)\.$", re.I)


def split_sentences(text: str) -> list:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", re.sub(r"\s+", " ", text or "").strip())
    out = []
    for p in parts:
        if out and _ABBR.search(out[-1]):
            out[-1] += " " + p
        elif p:
            out.append(p)
    return out


def _clip(sentence: str) -> str:
    return sentence if len(sentence) <= EXCERPT_CHARS else sentence[:EXCERPT_CHARS].rsplit(" ", 1)[0] + " …"


def label_excerpts(interactions: str, supplement) -> tuple:
    """回傳 (摘錄句子, 是否直接提到該成分)；只有草本產品的整體提醒時，第二個值為 False"""
    if not supplement or not interactions:
        return [], False
    sentences = split_sentences(interactions)
    direct = [s for s in sentences if re.search(supplement["pattern"], s, re.I)]
    general = []
    if supplement.get("herbal"):
        general = [s for s in sentences if re.search(_HERBAL_PATTERN, s, re.I) and s not in direct]
    picked = (direct + general)[:MAX_EXCERPTS]
    return [_clip(s) for s in picked], bool(direct)


# -------------------------------------------------------------------------
# 外部查詢（在背景執行緒中執行，不碰資料庫）
# -------------------------------------------------------------------------
class NotFound(Exception):
    """確定查無資料（可以快取）；其他例外視為連線失敗"""


def _get_json(url: str, params: dict) -> dict:
    res = requests.get(url, params=params, timeout=HTTP_TIMEOUT, headers={"User-Agent": UA})
    if res.status_code == 404:
        raise NotFound(url)
    res.raise_for_status()
    return res.json()


def fetch_label(drug: dict) -> dict:
    params = {"search": f'openfda.generic_name:"{drug["generic"]}" AND _exists_:drug_interactions',
              "sort": "effective_time:desc", "limit": 10}
    key = os.getenv("OPENFDA_API_KEY", "").strip()
    if key:
        params["api_key"] = key
    results = _get_json(OPENFDA_URL, params).get("results") or []
    if not results:
        raise NotFound(drug["generic"])
    wanted = {n.upper() for n in drug.get("fda_names") or [drug["generic"].upper()]}
    label = next((r for r in results if wanted & {g.upper() for g in (r.get("openfda") or {}).get("generic_name") or []}), results[0])
    o = label.get("openfda") or {}
    eff = label.get("effective_time", "")
    return {
        "set_id": label.get("set_id", ""),
        "effective": f"{eff[:4]}-{eff[4:6]}-{eff[6:8]}" if len(eff) >= 8 else eff,
        "brand": ", ".join(o.get("brand_name") or [])[:120],
        "generic": ", ".join(o.get("generic_name") or [])[:120],
        "manufacturer": ", ".join(o.get("manufacturer_name") or [])[:200],
        "interactions": " ".join(label.get("drug_interactions") or []),
    }


def fetch_medlineplus(drug: dict) -> dict:
    ids = (_get_json(RXNAV_URL, {"name": drug["generic"], "search": 2}).get("idGroup") or {}).get("rxnormId") or []
    if not ids:
        raise NotFound(drug["generic"])
    data = _get_json(MEDLINEPLUS_URL, {
        "mainSearchCriteria.v.cs": "2.16.840.1.113883.6.88", "mainSearchCriteria.v.c": ids[0],
        "knowledgeResponseType": "application/json"})
    pages = []
    for e in (data.get("feed") or {}).get("entry") or []:
        links = e.get("link") or []
        href = links[0].get("href", "") if links else ""
        if href.startswith("https://medlineplus.gov/"):
            href = href.split("?")[0]        # 去掉追蹤參數
            summary = re.sub(r"<[^>]+>", " ", (e.get("summary") or {}).get("_value", ""))
            pages.append({"title": (e.get("title") or {}).get("_value", ""), "url": href,
                          "summary": _clip(re.sub(r"\s+", " ", summary).strip())})
    if not pages:
        raise NotFound(drug["generic"])
    return {"rxcui": ids[0], "pages": pages[:2]}


FETCHERS = {"label": fetch_label, "medlineplus": fetch_medlineplus}


# -------------------------------------------------------------------------
# 快取（資料庫）
# -------------------------------------------------------------------------
def _fresh(entry) -> bool:
    if not entry:
        return False
    try:
        age = datetime.now() - datetime.strptime(entry["fetched_at"][:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return False
    return age < (timedelta(days=CACHE_DAYS) if entry["ok"] else timedelta(hours=FAIL_RETRY_HOURS))


def _collect(drugs: list) -> dict:
    """回傳 {(kind, generic): payload 或 None}；先查快取，缺的才平行向外查詢，最多等 LIVE_TIMEOUT 秒"""
    import database

    results, todo = {}, {}
    for d in drugs:
        for kind in FETCHERS:
            entry = database.get_live_cache(f"{kind}:{d['generic']}")
            if _fresh(entry):
                results[(kind, d["generic"])] = entry["payload"]
            else:
                todo[(kind, d["generic"])] = d
    if not todo:
        return results
    pool = ThreadPoolExecutor(max_workers=min(4, len(todo)))
    futures = {pool.submit(FETCHERS[kind], d): (kind, gen) for (kind, gen), d in todo.items()}
    done, _ = wait(futures, timeout=LIVE_TIMEOUT)
    pool.shutdown(wait=False, cancel_futures=True)
    for fut in done:
        kind, gen = futures[fut]
        try:
            payload = fut.result()
            database.set_live_cache(f"{kind}:{gen}", payload, ok=True)
        except NotFound:
            payload = None
            database.set_live_cache(f"{kind}:{gen}", None, ok=True)       # 確定查無，也快取
        except Exception as e:
            payload = None
            print(f"【即時查詢】{kind}:{gen} 失敗：{e}")
            database.set_live_cache(f"{kind}:{gen}", None, ok=False)
        results[(kind, gen)] = payload
    return results


# -------------------------------------------------------------------------
# 對外介面
# -------------------------------------------------------------------------
def lookup(query: str, elder_condition: str, matched_ingredient: str = ""):
    """依親友的用藥即時查詢美國官方資料；沒有辨識到具體藥名或功能關閉時回傳 None"""
    if not enabled():
        return None
    drugs = detect_drugs(elder_condition, query)
    if not drugs:
        return None
    supplement = detect_supplement(query) or detect_supplement(matched_ingredient)
    try:
        data = _collect(drugs)
    except Exception as e:             # 快取或資料庫出錯也不能影響回答
        print("【即時查詢】略過：", e)
        return None

    out_drugs, sources, mentions = [], [], []
    for d in drugs:
        item = {"generic": d["generic"], "zh": d["zh"], "label": None, "medlineplus": []}
        label = data.get(("label", d["generic"]))
        if label:
            excerpts, direct = label_excerpts(label["interactions"], supplement)
            url = DAILYMED_URL + urllib.parse.quote(label["set_id"])
            title = f"{label['brand'] or label['generic']} — FDA Drug Label (Drug Interactions)"
            item["label"] = {"title": title, "url": url, "effective": label["effective"],
                             "manufacturer": label["manufacturer"], "excerpts": excerpts, "mentions": direct}
            sources.append({"id": f"openfda:{label['set_id']}", "title": title, "url": url,
                            "authority": "美國 FDA 藥品仿單（openFDA 即時查詢）"})
            if supplement and direct:
                mentions.append({"drug": d["zh"], "supplement": supplement["zh"], "excerpts": excerpts})
        med = data.get(("medlineplus", d["generic"]))
        if med:
            item["medlineplus"] = med["pages"]
            for p in med["pages"]:
                sources.append({"id": f"medlineplus:{p['url']}", "title": p["title"], "url": p["url"],
                                "authority": "美國國家醫學圖書館 MedlinePlus（即時查詢）"})
        if item["label"] or item["medlineplus"]:
            out_drugs.append(item)
    if not out_drugs:
        return None
    return {
        "drugs": out_drugs,
        "supplement": {"key": supplement["key"], "zh": supplement["zh"]} if supplement else None,
        "label_mentions": mentions,
        "sources": sources,
        "note": "以下為美國 FDA 仿單與 MedlinePlus 的英文原文，台灣上市的同成分藥品仿單內容可能不同；仿單沒有提到，也不代表確定沒有交互作用，請以醫師、藥師的說明為準。",
    }


def summary_text(live: dict) -> str:
    """離線回覆用：列出仿單原文摘錄（英文）與是否提到該成分"""
    if not live:
        return ""
    lines = ["【即時查詢】美國 FDA 藥品仿單與 MedlinePlus"]
    supp = (live.get("supplement") or {}).get("zh")
    for d in live["drugs"]:
        label = d.get("label")
        if label:
            if label["excerpts"]:
                head = f"・{d['zh']} 仿單（{label['effective']} 版）" + ("提到" + supp if label["mentions"] and supp else "對草本產品的提醒")
                lines.append(head + "：")
                lines.extend(f"  “{e}”" for e in label["excerpts"])
            elif supp:
                lines.append(f"・{d['zh']} 仿單（{label['effective']} 版）的交互作用段落沒有提到{supp}；沒有提到不代表確定沒有交互作用。")
            else:
                lines.append(f"・{d['zh']} 仿單（{label['effective']} 版）的交互作用段落可點下方連結查看。")
        for p in d.get("medlineplus") or []:
            lines.append(f"・MedlinePlus 衛教頁：{p['title']}")
    lines.append(live["note"])
    lines.append("即時查詢出處：")
    lines.extend(f"・{s['authority']}：{s['title']}（{s['url']}）" for s in live["sources"])
    return "\n".join(lines)
