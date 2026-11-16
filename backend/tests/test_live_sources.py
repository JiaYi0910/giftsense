"""
RAG 第三階段：即時查詢 openFDA 仿單與 MedlinePlus。

執行（在 backend 資料夾）：
    python -m pytest tests/test_live_sources.py -q

外部 API 一律換成假的回應，不連線任何網站；測試使用 caregift.db 的暫存複本。
"""
import os
import shutil
import sys
import tempfile

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP_DIR = tempfile.mkdtemp(prefix="giftsense_live_test_")
TEST_DB = os.path.join(_TMP_DIR, "caregift.db")
shutil.copy(os.path.join(BACKEND, "caregift.db"), TEST_DB)

os.environ["CAREGIFT_DB_PATH"] = TEST_DB
for _key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "GEMINI_API_KEY"):
    os.environ.pop(_key, None)
os.environ.pop("DATABASE_URL", None)
if os.getenv("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

import database  # noqa: E402

if database.DB_PATH != TEST_DB:  # 同一個 pytest 行程裡已有其他測試先載入 database
    database.DB_PATH = TEST_DB
    database.init_db()

import live_sources  # noqa: E402
from rag_engine import query_rag_engine  # noqa: E402
from vector_store import global_vector_store  # noqa: E402

# 仿單原文的寫法（openFDA 回傳的 drug_interactions 段落，節錄改寫成測試用）
WARFARIN_TEXT = (
    "7 DRUG INTERACTIONS Concomitant use of drugs that increase bleeding risk, antibiotics, antifungals, "
    "botanical (herbal) products, and inhibitors and inducers of CYP2C9, 1A2, or 3A4. "
    "7.5 Botanical (Herbal) Products and Foods More frequent INR monitoring should be performed when starting or stopping botanicals. "
    "Some botanicals may cause bleeding events when taken alone (e.g., garlic and Ginkgo biloba) and may have anticoagulant, "
    "antiplatelet, and/or fibrinolytic properties. Some botanicals and foods can interact with warfarin through CYP450 "
    "interactions (e.g., echinacea, grapefruit juice, ginkgo, goldenseal, St. John's wort)."
)
APIXABAN_TEXT = (
    "7 DRUG INTERACTIONS Combined P-gp and strong CYP3A4 inducers (e.g., rifampin, carbamazepine, phenytoin, St. John's wort) "
    "decrease exposure to apixaban. Coadministration of antiplatelet agents, fibrinolytics, heparin, aspirin, and chronic NSAID use "
    "increases the risk of bleeding."
)


class FakeApis:
    """依網址回傳假的 openFDA／RxNav／MedlinePlus 資料，並記錄呼叫次數"""

    def __init__(self, fail=False, extra=None):
        self.calls = []
        self.fail = fail
        self.extra = extra or {}      # {學名: 加在仿單後面的句子}

    def __call__(self, url, params):
        self.calls.append(url)
        if self.fail:
            raise ConnectionError("network down")
        if url == live_sources.OPENFDA_URL:
            generic = params["search"].split('"')[1]
            text = {"warfarin": WARFARIN_TEXT, "apixaban": APIXABAN_TEXT}.get(generic)
            if not text:
                raise live_sources.NotFound(generic)
            text += self.extra.get(generic, "")
            return {"results": [{"set_id": f"set-{generic}", "effective_time": "20261028", "drug_interactions": [text],
                                 "openfda": {"generic_name": [generic.upper()], "brand_name": [generic.title()],
                                             "manufacturer_name": ["Example Pharma"]}}]}
        if url == live_sources.RXNAV_URL:
            return {"idGroup": {"rxnormId": ["11289"]}}
        if url == live_sources.MEDLINEPLUS_URL:
            return {"feed": {"entry": [{"title": {"_value": "Warfarin"},
                                        "link": [{"href": "https://medlineplus.gov/druginfo/meds/a682277.html?utm_source=mplusconnect"}],
                                        "summary": {"_value": "<p>Warfarin is used to prevent blood clots.</p>"}}]}}
        raise AssertionError(url)


@pytest.fixture
def fake_apis(monkeypatch):
    monkeypatch.setenv("LIVE_SOURCES", "on")
    database.clear_live_cache()
    fake = FakeApis()
    monkeypatch.setattr(live_sources, "_get_json", fake)
    yield fake
    database.clear_live_cache()


@pytest.fixture(scope="module", autouse=True)
def _index_from_db():
    global_vector_store.reload(database.get_all_clinical_knowledge())


# -------------------------------------------------------------------------
# 辨識藥名與摘錄原文
# -------------------------------------------------------------------------
def test_detects_specific_drugs_but_not_drug_classes():
    assert [d["generic"] for d in live_sources.detect_drugs("心房顫動，服用可邁丁")] == ["warfarin"]
    assert [d["generic"] for d in live_sources.detect_drugs("服用 Eliquis", "")] == ["apixaban"]
    assert live_sources.detect_drugs("高血壓，服用抗凝血藥") == []          # 類別詞交給規則處理，不查仿單
    assert live_sources.detect_supplement("可以吃銀杏嗎？")["key"] == "ginkgo"


def test_sentences_keep_abbreviations_together():
    sentences = live_sources.split_sentences(WARFARIN_TEXT)
    assert any("(e.g., garlic and Ginkgo biloba)" in s for s in sentences)
    assert any("St. John's wort)." in s for s in sentences)


def test_label_excerpts_prefer_direct_mentions():
    ginkgo = live_sources.detect_supplement("銀杏")
    excerpts, direct = live_sources.label_excerpts(WARFARIN_TEXT, ginkgo)
    assert direct and "Ginkgo biloba" in excerpts[0] and len(excerpts) <= live_sources.MAX_EXCERPTS
    calcium = live_sources.detect_supplement("鈣片")
    assert live_sources.label_excerpts(WARFARIN_TEXT, calcium) == ([], False)


# -------------------------------------------------------------------------
# 查詢、快取與失敗處理
# -------------------------------------------------------------------------
def test_lookup_returns_label_and_medlineplus_and_uses_cache(fake_apis):
    live = live_sources.lookup("可以吃銀杏嗎？", "心房顫動，服用可邁丁")
    drug = live["drugs"][0]
    assert drug["label"]["url"] == live_sources.DAILYMED_URL + "set-warfarin"
    assert drug["label"]["mentions"] and drug["label"]["effective"] == "2026-10-28"
    assert drug["medlineplus"][0]["url"] == "https://medlineplus.gov/druginfo/meds/a682277.html"   # 去掉追蹤參數
    assert live["label_mentions"] and {s["url"] for s in live["sources"]} == {
        live_sources.DAILYMED_URL + "set-warfarin", "https://medlineplus.gov/druginfo/meds/a682277.html"}
    calls = len(fake_apis.calls)
    again = live_sources.lookup("那大蒜呢？", "心房顫動，服用可邁丁")
    assert len(fake_apis.calls) == calls                                  # 第二次直接用快取
    assert again["supplement"]["key"] == "garlic" and again["label_mentions"]


def test_lookup_is_skipped_when_disabled_or_no_specific_drug(fake_apis, monkeypatch):
    assert live_sources.lookup("可以吃銀杏嗎？", "高血壓") is None
    monkeypatch.setenv("LIVE_SOURCES", "off")
    assert live_sources.lookup("可以吃銀杏嗎？", "服用可邁丁") is None
    assert fake_apis.calls == []


def test_network_failure_is_cached_briefly_and_answer_still_works(monkeypatch):
    monkeypatch.setenv("LIVE_SOURCES", "on")
    database.clear_live_cache()
    failing = FakeApis(fail=True)
    monkeypatch.setattr(live_sources, "_get_json", failing)
    res = query_rag_engine("親友容易疲倦，可以吃輔酶 Q10 嗎？", "爸爸", "服用 Eliquis")
    assert res["has_match"] is True and res["live_sources"] is None
    entry = database.get_live_cache("label:apixaban")
    assert entry and entry["ok"] is False                                 # 失敗只快取 1 小時
    database.clear_live_cache()


# -------------------------------------------------------------------------
# 與回答整合
# -------------------------------------------------------------------------
def test_rule_hit_keeps_rule_warning_and_adds_label_excerpt(fake_apis):
    res = query_rag_engine("爸爸想吃銀杏改善循環，可以嗎？", "爸爸", "心房顫動，服用可邁丁（Warfarin）")
    assert res["safety"]["is_collision"] is True                          # 規則仍是安全底線
    assert res["safety"]["action_card"]["price"] is None
    text = res["gemini_synthesis"]
    assert "Ginkgo biloba" in text and live_sources.DAILYMED_URL + "set-warfarin" in text
    assert res["live_sources"]["drugs"][0]["generic"] == "warfarin"


def test_label_without_mention_says_so(fake_apis):
    res = query_rag_engine("親友想吃魚油保養心血管，可以嗎？", "媽媽", "服用 Eliquis 艾必克凝")
    label = res["live_sources"]["drugs"][0]["label"]
    assert label["mentions"] is False and label["excerpts"] == []
    assert res["safety"]["label_caution"] is False
    assert "交互作用段落沒有提到魚油" in res["gemini_synthesis"]


def test_label_mention_without_rule_blocks_product(monkeypatch):
    # 艾必克凝（apixaban）不在輔酶 Q10 規則的藥名裡；仿單若直接提到這項成分，雖然沒有命中規則也不推薦商品
    monkeypatch.setenv("LIVE_SOURCES", "on")
    database.clear_live_cache()
    monkeypatch.setattr(live_sources, "_get_json", FakeApis(extra={"apixaban": " Coenzyme Q10 may alter the anticoagulant effect."}))
    res = query_rag_engine("親友容易疲倦，可以吃輔酶 Q10 嗎？", "爸爸", "服用 Eliquis 艾必克凝")
    database.clear_live_cache()
    assert res["safety"]["is_collision"] is False and res["safety"]["label_caution"] is True
    assert res["safety"]["action_card"]["price"] is None
    assert res["gemini_synthesis"].startswith("⚠️ 【仿單提醒】")
    assert "Coenzyme Q10 may alter" in res["gemini_synthesis"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
