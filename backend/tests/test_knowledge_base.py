"""
AI 守護助理的知識來源：每張知識卡片與交互作用規則都要有可查證的出處，原文切段後存進資料庫。

執行（在 backend 資料夾）：
    python -m pytest tests/test_knowledge_base.py -q

測試使用 caregift.db 的暫存複本，不會改到 repo 內的資料庫；不連線任何外部網站。
"""
import json
import os
import re
import shutil
import sys
import tempfile

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP_DIR = tempfile.mkdtemp(prefix="giftsense_knowledge_test_")
TEST_DB = os.path.join(_TMP_DIR, "caregift.db")
shutil.copy(os.path.join(BACKEND, "caregift.db"), TEST_DB)

os.environ["CAREGIFT_DB_PATH"] = TEST_DB
for _key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "GEMINI_API_KEY"):
    os.environ.pop(_key, None)
# 不碰開發用的資料庫（DATABASE_URL）；要在 SQL Server 上測試時另外設定 TEST_DATABASE_URL，指向空的測試資料庫
os.environ.pop("DATABASE_URL", None)
if os.getenv("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

os.chdir(BACKEND)
sys.path.insert(0, BACKEND)

import database  # noqa: E402

if database.DB_PATH != TEST_DB:  # 同一個 pytest 行程裡已有其他測試先載入 database
    database.DB_PATH = TEST_DB
    database.init_db()

import knowledge_base as kb  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from rag_engine import query_rag_engine  # noqa: E402
from tfda_service import TFDA_COLLISION_RULES  # noqa: E402
from vector_store import FULL_CLINICAL_LITERATURES, global_vector_store  # noqa: E402

client = TestClient(main.app)
MANIFEST = {s["id"]: s for s in kb.load_manifest()}

# 查無出處、已確認要移除的引用（見 docs/RAG_待查證清單.md）
REMOVED_CITATIONS = ["0950400854", "0960408532", "1456-1463", "018245", "藥品安全通訊第 48 期", "J Clin Hypertens", "相容度"]


# -------------------------------------------------------------------------
# 來源清單
# -------------------------------------------------------------------------
def test_manifest_ids_unique_and_complete():
    ids = [s["id"] for s in kb.load_manifest()]
    assert len(ids) == len(set(ids))
    for s in MANIFEST.values():
        assert s["title"] and s["authority"] and s["url"].startswith("https://"), s["id"]
        assert s["content"] in ("fetch_html", "fetch_openfda_label", "link_only", "manual"), s["id"]
        assert s.get("verified"), f"{s['id']} 沒有查證紀錄"
        if s["type"] == "journal" and s.get("pmid"):
            assert s["url"] == f"https://pubmed.ncbi.nlm.nih.gov/{s['pmid']}/"


def test_every_card_has_verified_sources():
    for lit in FULL_CLINICAL_LITERATURES:
        ids = lit.get("sourceIds") or []
        assert ids, f"{lit['id']} 沒有依據來源"
        assert all(i in MANIFEST for i in ids), f"{lit['id']} 的來源不在清單：{ids}"
        published = [i for i in ids if MANIFEST[i]["content"] != "manual"]
        assert published, f"{lit['id']} 只有尚未存檔的來源"
        assert lit["url"] == MANIFEST[published[0]]["url"]


def test_every_rule_lists_sources_and_no_unverified_alternatives():
    for rule in TFDA_COLLISION_RULES:
        assert "sources" in rule, rule["id"]
        assert all(i in MANIFEST for i in rule["sources"]), rule["id"]
        if not rule["sources"]:
            assert "尚無官方依據" in rule["official_citation"], rule["id"]
        # 替代商品的理由都沒有官方依據，命中規則時一律不推薦商品
        assert rule["alternative"] is None, rule["id"]
        assert "TFDA" not in rule["badge"] and "食藥署" not in rule["badge"], rule["id"]


def test_removed_citations_are_gone():
    texts = json.dumps(FULL_CLINICAL_LITERATURES, ensure_ascii=False) + json.dumps(TFDA_COLLISION_RULES, ensure_ascii=False)
    for bad in REMOVED_CITATIONS:
        assert bad not in texts, f"仍有查無出處的引用：{bad}"
    # 後端程式也不能再宣稱比對過食藥署的資料庫
    for name in ("rag_engine.py", "tfda_service.py"):
        src = open(os.path.join(BACKEND, name), encoding="utf-8").read()
        assert "相容度" not in src and "TFDA 官方資料庫" not in src, name


def test_source_refs_skip_unknown_and_unsaved_manual_sources():
    refs = kb.source_refs(["nccih_ginkgo", "not_a_real_source", "nccih_ginkgo"])
    assert [r["id"] for r in refs] == ["nccih_ginkgo"]
    assert refs[0]["url"] == "https://www.nccih.nih.gov/health/ginkgo"
    pending = [s["id"] for s in MANIFEST.values() if s["content"] == "manual" and not kb.source_files(s)]
    if pending:
        assert kb.source_refs(pending[:1]) == []


# -------------------------------------------------------------------------
# 原文擷取與切段
# -------------------------------------------------------------------------
def test_html_to_text_keeps_content_and_drops_navigation_and_references():
    html = """<html><head><title>Ginkgo | NCCIH</title></head><body>
      <nav><ul><li><a href="/">Home</a></li><li><a href="/health">Health Topics A-Z</a></li></ul></nav>
      <main><h1>Ginkgo</h1>
        <p>Ginkgo may increase the risk of bleeding in people who are taking anticoagulant drugs, such as warfarin.</p>
        <ul><li><a href="/a">Related link only</a></li></ul>
        <h2>Safety</h2><p>Talk with your health care provider before using ginkgo if you take any medicines.</p>
        <h2>Key References</h2><p>Smith J, et al. A reference that should not be stored. J Test. 2020;1:1-2.</p>
      </main><footer><p>Contact us at the clearinghouse for more information today.</p></footer></body></html>"""
    text = kb.html_to_text(html)
    assert "increase the risk of bleeding" in text and "## Safety" in text
    assert "Home" not in text and "Related link only" not in text
    assert "should not be stored" not in text and "Contact us" not in text


def test_chunk_sizes_follow_language_rules():
    zh = "\n\n".join("服用抗凝血藥的長輩在使用保健品前，應先詢問醫師或藥師，確認是否會增加出血風險。" * 4 for _ in range(12))
    zh_chunks = kb.chunk_text(zh, "zh")
    assert len(zh_chunks) > 1
    assert all(kb.text_units(c) <= kb.ZH_MAX for c in zh_chunks)
    assert all(kb.text_units(c) >= kb.ZH_MIN for c in zh_chunks[:-1])
    en = "\n\n".join(" ".join(["Ginkgo may increase the risk of bleeding in people taking warfarin."] * 6) for _ in range(10))
    en_chunks = kb.chunk_text(en, "en")
    assert len(en_chunks) > 1 and all(kb.text_units(c) <= kb.EN_MAX for c in en_chunks)


def test_build_rows_only_chunks_sources_with_files():
    sources, chunks, missing = kb.build_rows()
    assert len(sources) == len(MANIFEST)
    by_source = {}
    for c in chunks:
        assert {"source_title", "authority", "url", "ingredient", "chunk_text"} <= set(c)
        assert c["chunk_text"].strip() and c["url"] == MANIFEST[c["source_id"]]["url"]
        by_source.setdefault(c["source_id"], 0)
        by_source[c["source_id"]] += 1
    for sid, s in MANIFEST.items():
        if s["content"] == "link_only":
            assert sid not in by_source, f"{sid} 只能放連結，不能存全文"
    assert {"nccih_ginkgo", "nccih_glucosamine", "label_warfarin"} <= set(by_source)
    assert all(MANIFEST[m]["content"] in ("manual", "fetch_html", "fetch_openfda_label") for m in missing)


# -------------------------------------------------------------------------
# 資料庫同步與 API
# -------------------------------------------------------------------------
def test_sync_is_skipped_when_sources_unchanged_and_forced_reload_works():
    assert database.sync_knowledge_base()["updated"] is False      # init_db 已匯入過
    forced = database.sync_knowledge_base(force=True)
    assert forced["updated"] is True and forced["chunks"] > 0
    stored = database.get_knowledge_chunks(source_id="nccih_ginkgo")
    assert stored and all(c["url"] == "https://www.nccih.nih.gov/health/ginkgo" for c in stored)
    assert [c["chunk_index"] for c in stored] == list(range(1, len(stored) + 1))


def test_knowledge_api_returns_sources_and_chunks():
    data = client.get("/api/knowledge").json()
    lit = next(l for l in data["literatures"] if l["id"] == "lit_glucosamine_07")
    assert lit["url"] and lit["sources"] and lit["sources"][0]["url"].startswith("https://")
    assert "出血" in lit["contraindications"]                       # 依 NCCIH 更正後的內容
    src = client.get("/api/knowledge/sources").json()
    assert src["total"] == len(MANIFEST) and src["chunks"] > 0
    chunks = client.get("/api/knowledge/chunks", params={"ingredient": "warfarin"}).json()
    assert chunks["total"] > 0 and all("warfarin" in c["ingredient"] for c in chunks["chunks"])
    assert client.post("/api/knowledge/sources/reload").status_code in (401, 403)   # 需要管理員通行證


def test_editing_a_card_without_source_fields_keeps_its_sources():
    before = next(l for l in database.get_all_clinical_knowledge() if l["id"] == "lit_ginkgo_11")
    edited = {k: before[k] for k in ("id", "title", "authority", "category", "ingredient", "citation")}
    edited.update(targetSymptoms=before["targetSymptoms"], mechanism=before["mechanism"] + "（測試編輯）")
    database.save_clinical_knowledge(edited)
    after = next(l for l in database.get_all_clinical_knowledge() if l["id"] == "lit_ginkgo_11")
    assert after["url"] == before["url"] and after["sourceIds"] == before["sourceIds"]
    database.save_clinical_knowledge({**edited, "mechanism": before["mechanism"]})


# -------------------------------------------------------------------------
# 回答：附出處、命中規則時不推薦商品
# -------------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def _index_from_db():
    global_vector_store.reload(database.get_all_clinical_knowledge())


def test_warfarin_and_glucosamine_is_flagged_without_product():
    res = query_rag_engine("親友在吃抗凝血藥又膝蓋痛，葡萄糖胺或 UC-II 比較安全嗎？", "爸爸", "心房顫動，服用 Warfarin")
    safety = res["safety"]
    assert safety["is_collision"] is True
    assert safety["action_card"]["type"] == "notice" and safety["action_card"]["price"] is None
    assert [s["id"] for s in res["tfda_verification"]["sources"]] == ["nccih_glucosamine"]
    assert "https://www.nccih.nih.gov/health/glucosamine" in res["gemini_synthesis"]


def test_answers_cite_only_listed_urls():
    known = {s["url"] for s in MANIFEST.values()}
    for q, cond in [("親友容易疲倦、體力差，補充輔酶 Q10 有幫助嗎？", "常熬夜加班"),
                    ("膽固醇偏高可以吃紅麴嗎？", "膽固醇偏高，服用 Statin"),
                    ("腎功能不好的親友，可以自己吃布洛芬這類消炎止痛藥嗎？", "慢性腎臟病 未洗腎")]:
        res = query_rag_engine(q, "爸爸", cond)
        for lit in res["matched_literatures"]:
            assert lit["sources"], lit["id"]
            assert all(s["url"] in known for s in lit["sources"])
        cited = set(re.findall(r"https://[^\s）)]+", res["gemini_synthesis"]))
        assert cited and cited <= known, cited - known


def test_no_match_rule_result_does_not_claim_tfda_database():
    res = query_rag_engine("親友容易疲倦、體力差，補充輔酶 Q10 有幫助嗎？", "爸爸", "常熬夜加班")
    tfda = res["tfda_verification"]
    assert tfda["is_collision"] is False
    assert "食藥署" not in tfda["desc"] and "98%" not in tfda["desc"]
    assert "不代表確定沒有交互作用" in tfda["desc"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
