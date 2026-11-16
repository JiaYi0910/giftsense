"""
RAG 第二階段：混合檢索（TF-IDF＋Gemini 語意向量）、原文段落與多機構交叉驗證。

執行（在 backend 資料夾）：
    python -m pytest tests/test_retrieval.py -q

Gemini embedding 一律換成假的向量，不連線任何網站；測試使用 caregift.db 的暫存複本。
"""
import hashlib
import math
import os
import shutil
import sys
import tempfile

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP_DIR = tempfile.mkdtemp(prefix="giftsense_retrieval_test_")
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

import retrieval  # noqa: E402
import semantic_index as si  # noqa: E402
from rag_engine import query_rag_engine  # noqa: E402
from vector_store import global_vector_store  # noqa: E402

CARDS = database.get_all_clinical_knowledge()
CHUNKS = database.get_knowledge_chunks()
REAL_SEM_FLOOR = retrieval.SEM_FLOOR      # 依真實 Gemini 向量校正的值；假向量的分數範圍不同，多數測試先關掉


def fake_vector(text: str) -> list:
    """以字元雙字組雜湊成 768 維向量：字面越像，餘弦相似度越高（只用來測試流程）"""
    vec = [0.0] * si.EMBED_DIM
    t = text.lower()
    for i in range(len(t) - 1):
        h = int(hashlib.md5(t[i:i + 2].encode("utf-8")).hexdigest(), 16)
        vec[h % si.EMBED_DIM] += 1.0
    return si.normalize(vec)


class FakeEmbedder:
    def __init__(self, fail_query=False, rate_limit_once=False):
        self.calls, self.fail_query, self.rate_limit_once = [], fail_query, rate_limit_once

    def __call__(self, texts, task, timeout=None):
        self.calls.append((task, len(texts)))
        if self.rate_limit_once:
            self.rate_limit_once = False
            raise si.RateLimited("429")
        if task == "RETRIEVAL_QUERY" and self.fail_query:
            raise RuntimeError("timeout")
        return [fake_vector(t) for t in texts]


@pytest.fixture
def semantic(monkeypatch):
    """開啟語意檢索，以假向量建立索引"""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("SEMANTIC_SEARCH", "on")
    monkeypatch.setattr(si, "RATE_LIMIT_WAIT", 0)
    monkeypatch.setattr(retrieval, "SEM_FLOOR", 0.0)   # 假向量（字元雙字組）的分數普遍偏低，不套用真實向量的下限
    fake = FakeEmbedder()
    monkeypatch.setattr(si, "embed_texts", fake)
    index = si.SemanticIndex()
    monkeypatch.setattr(si, "semantic_index", index)
    monkeypatch.setattr(retrieval, "semantic_index", index)
    index.start(CARDS, CHUNKS, background=False)
    retrieval.load_chunks(CHUNKS)
    yield index, fake
    retrieval.load_chunks(CHUNKS)


@pytest.fixture(scope="module", autouse=True)
def _index_from_db():
    global_vector_store.reload(CARDS)
    retrieval.load_chunks(CHUNKS)


# -------------------------------------------------------------------------
# 向量索引的建立與快取
# -------------------------------------------------------------------------
def test_index_builds_once_and_then_uses_the_database_cache(semantic, monkeypatch):
    index, fake = semantic
    assert index.ready() and len(index.card_vecs) == len(CARDS) and len(index.chunk_vecs) == len(CHUNKS)
    assert all(abs(math.sqrt(sum(v * v for v in vec)) - 1) < 1e-4 for vec in index.card_vecs.values())   # 已正規化
    again = FakeEmbedder()
    monkeypatch.setattr(si, "embed_texts", again)
    fresh = si.SemanticIndex()
    fresh.start(CARDS, CHUNKS, background=False)
    assert fresh.ready() and again.calls == []                            # 全部來自資料庫快取
    info = fresh.info()
    assert info["mode"] == "hybrid" and info["cards"] == len(CARDS) and "key" not in str(info).lower()


def test_embedding_cache_writes_in_few_statements_and_skips_existing_keys():
    """Turso 的交易超過幾秒會被取消：向量要用多列 INSERT 批次寫入，不可逐筆 merge"""
    import uuid
    from sqlalchemy import event

    prefix = uuid.uuid4().hex[:8]
    items = {f"{prefix}-{i}": si.pack([0.0] * si.EMBED_DIM) for i in range(45)}
    statements = []

    def record(conn, cursor, statement, params, context, executemany):
        statements.append(statement.lstrip().upper())

    event.listen(database.engine, "before_cursor_execute", record)
    try:
        database.put_embeddings(items, si.EMBED_MODEL, si.EMBED_DIM)
        database.put_embeddings(items, si.EMBED_MODEL, si.EMBED_DIM)      # 第二次：全部已存在，只查詢
    finally:
        event.remove(database.engine, "before_cursor_execute", record)
    assert sum(s.startswith("INSERT") for s in statements) == 3          # 45 筆分 3 批（每批 20 筆）
    assert set(database.get_embeddings(list(items))) == set(items)


def test_rate_limit_is_retried(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("SEMANTIC_SEARCH", "on")
    monkeypatch.setattr(si, "RATE_LIMIT_WAIT", 0)
    fake = FakeEmbedder(rate_limit_once=True)
    monkeypatch.setattr(si, "embed_texts", fake)
    index = si.SemanticIndex()
    edited = [dict(CARDS[0], mechanism=CARDS[0]["mechanism"] + "（測試：限流後重試）")]
    index.start(edited, [], background=False)
    assert index.ready() and len(fake.calls) == 2


def test_disabled_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    index = si.SemanticIndex()
    index.start(CARDS, CHUNKS, background=False)
    assert index.status == "off" and index.query_vector("葉黃素") is None


# -------------------------------------------------------------------------
# 混合檢索
# -------------------------------------------------------------------------
def test_semantic_only_candidate_is_found_and_unrelated_is_rejected(semantic, monkeypatch):
    index, _ = semantic
    lutein = next(c for c in CARDS if c["id"] == "lit_lutein_01")
    # 字面完全不同的問題：TF-IDF 找不到，語意向量和葉黃素卡片很接近
    monkeypatch.setattr(index, "query_vector", lambda q: index.card_vecs["lit_lutein_01"] if q == "qqqq zzzz" else None)
    cards, info = retrieval.search_cards("qqqq zzzz")
    assert info["mode"] == "hybrid" and cards[0]["id"] == lutein["id"] and cards[0]["vector_score"] == 0
    # 和所有卡片都不像的問題：沒有候選
    monkeypatch.setattr(index, "query_vector", lambda q: si.normalize([1.0] + [0.0] * (si.EMBED_DIM - 1)))
    assert retrieval.search_cards("qqqq zzzz")[0] == []


def test_keyword_coincidence_is_rejected_by_semantic_floor(semantic, monkeypatch):
    index, _ = semantic
    query = "高鐵票怎麼訂"
    assert global_vector_store.search(query)                       # 只用 TF-IDF：字面巧合配到卡片
    monkeypatch.setattr(retrieval, "SEM_FLOOR", REAL_SEM_FLOOR)
    monkeypatch.setattr(index, "query_vector", lambda q: si.normalize([1.0] + [0.0] * (si.EMBED_DIM - 1)))
    assert retrieval.search_cards(query)[0] == []                  # 語意分數低於下限：排除


def test_query_embedding_failure_falls_back_to_tfidf(semantic, monkeypatch):
    monkeypatch.setattr(si, "embed_texts", FakeEmbedder(fail_query=True))
    cards, info = retrieval.search_cards("葉黃素可以保護眼睛嗎？")
    assert info["mode"] == "tfidf" and cards[0]["id"] == global_vector_store.search("葉黃素可以保護眼睛嗎？")[0]["id"]


def test_hybrid_keeps_strong_keyword_match_on_top(semantic):
    cards, info = retrieval.search_cards("膝蓋痛可以吃葡萄糖胺嗎？")
    assert info["mode"] == "hybrid" and cards[0]["id"] == "lit_glucosamine_07"
    assert cards[0]["semantic_score"] is not None and cards[0]["hybrid_score"] >= cards[-1]["hybrid_score"]


# -------------------------------------------------------------------------
# 原文段落與交叉驗證
# -------------------------------------------------------------------------
def test_passages_come_from_distinct_institutions(semantic):
    card = next(c for c in CARDS if c["id"] == "lit_glucosamine_07")
    cards, info = retrieval.search_cards("膝蓋痛可以吃葡萄糖胺嗎？")
    passages = retrieval.find_passages("膝蓋痛可以吃葡萄糖胺嗎？", card, info["qvec"])
    assert 1 <= len(passages) <= retrieval.MAX_PASSAGES
    orgs = [retrieval.institution(p["authority"]) for p in passages]
    assert len(set(orgs)) == len(orgs)
    known = {c["url"] for c in CHUNKS}
    assert all(p["url"] in known and p["excerpt"] for p in passages)


def test_tfidf_passages_and_excerpt_formatting():
    card = next(c for c in CARDS if c["id"] == "lit_coq10_06")
    passages = retrieval.find_passages("輔酶 Q10 每天可以吃多少？", card, None)
    tfda = next(p for p in passages if p["source_id"] == "tfda_material_coq10")
    assert "三十毫克" in tfda["excerpt"] and "；；" not in tfda["excerpt"] and "：；" not in tfda["excerpt"]


def test_institutions_merge_agencies_and_label_single_source():
    assert retrieval.institution("美國國家輔助與整合衛生中心（NIH NCCIH）") == retrieval.institution("美國國家衛生研究院膳食補充品辦公室（NIH ODS）")
    assert retrieval.institution("美國 FDA 藥品仿單（DailyMed）") == retrieval.institution("美國食品藥物管理局（US FDA）")
    assert retrieval.institution("衛生福利部食品藥物管理署") != retrieval.institution("美國食品藥物管理局（US FDA）")
    single = retrieval.evidence_check([{"authority": "Sci Rep（期刊）"}], [])
    assert single["status"] == "single" and single["label"] == "僅單一來源：Sci Rep 期刊"
    multi = retrieval.evidence_check([{"authority": "美國國家輔助與整合衛生中心（NIH NCCIH）"}],
                                     [{"authority": "衛生福利部食品藥物管理署"}])
    assert multi["status"] == "multi" and "2 個機構" in multi["label"]


def test_answer_includes_passages_evidence_and_mode(semantic):
    res = query_rag_engine("親友容易疲倦、體力差，補充輔酶 Q10 有幫助嗎？", "爸爸", "常熬夜加班")
    assert res["retrieval"]["mode"] == "hybrid"
    assert res["evidence_check"]["status"] == "multi" and res["passages"]
    assert "【交叉驗證】多機構來源" in res["gemini_synthesis"]
    assert res["passages"][0]["url"] in res["gemini_synthesis"]


def test_health_reports_retrieval_without_secrets():
    import main
    from fastapi.testclient import TestClient
    data = TestClient(main.app).get("/api/health").json()
    assert data["retrieval"]["mode"] in ("tfidf", "hybrid") and data["retrieval"]["passages_loaded"] > 0
    assert "test-key-not-real" not in str(data)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
