# -*- coding: utf-8 -*-
"""
RAG 第二階段：語意向量（Gemini embedding）

- 模型：gemini-embedding-001（文字專用，可指定 RETRIEVAL_DOCUMENT／RETRIEVAL_QUERY 任務類型），向量取 768 維；
  官方說明縮減維度後的向量需要自行正規化，這裡一律正規化成長度 1，餘弦相似度＝內積
- 知識卡片與原文段落的向量在背景計算，存進資料庫 embedding_cache（key＝模型、維度、任務、文字的雜湊），重新啟動不必重算
- 只把「問題文字」送去計算向量，不送親友的病況、姓名或帳號
- 沒有 GEMINI_API_KEY、SEMANTIC_SEARCH=off、向量還沒算好或連線失敗時，檢索自動退回 TF-IDF（vector_store.py）
"""
import base64
import hashlib
import os
import struct
import threading
import time

import requests

EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001").strip() or "gemini-embedding-001"
EMBED_DIM = 768
EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
BATCH_SIZE = 40
QUERY_TIMEOUT = 4           # 問題向量最多等幾秒，逾時就只用 TF-IDF
BUILD_TIMEOUT = 60
RATE_LIMIT_WAIT = 65        # 免費額度被限流（HTTP 429）時，等一分鐘再試
MAX_RETRIES = 6
MAX_CHARS = 3000            # gemini-embedding-001 單筆輸入上限 2,048 tokens，超過的部分截掉
QUERY_CACHE_SIZE = 500


class RateLimited(Exception):
    pass


def api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def enabled() -> bool:
    return bool(api_key()) and os.getenv("SEMANTIC_SEARCH", "on").strip().lower() not in ("off", "0", "false", "no")


def cache_key(task: str, text: str) -> str:
    return hashlib.sha1(f"{EMBED_MODEL}|{EMBED_DIM}|{task}|{text}".encode("utf-8")).hexdigest()


def normalize(vec) -> list:
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def pack(vec) -> str:
    return base64.b64encode(struct.pack(f"<{len(vec)}f", *vec)).decode("ascii")


def unpack(b64: str) -> list:
    raw = base64.b64decode(b64)
    return list(struct.unpack(f"<{len(raw) // 4}f", raw))


def dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def embed_texts(texts: list, task: str, timeout: float = BUILD_TIMEOUT) -> list:
    """呼叫 Gemini batchEmbedContents；回傳正規化後的向量。金鑰放在標頭，不放網址"""
    body = {"requests": [{"model": f"models/{EMBED_MODEL}", "content": {"parts": [{"text": t[:MAX_CHARS]}]},
                          "taskType": task, "outputDimensionality": EMBED_DIM} for t in texts]}
    res = requests.post(EMBED_URL.format(model=EMBED_MODEL), json=body, timeout=timeout,
                        headers={"x-goog-api-key": api_key(), "Content-Type": "application/json"})
    if res.status_code == 429:
        raise RateLimited(res.text[:200])
    if res.status_code != 200:
        raise RuntimeError(f"HTTP {res.status_code}：{res.text[:200]}")
    vectors = [e.get("values") or [] for e in res.json().get("embeddings") or []]
    if len(vectors) != len(texts) or any(len(v) != EMBED_DIM for v in vectors):
        raise RuntimeError("回傳的向量數量或維度不符")
    return [normalize(v) for v in vectors]


class SemanticIndex:
    """知識卡片與原文段落的語意向量；在背景執行緒建立，查詢時只讀"""

    def __init__(self):
        self.card_vecs = {}         # 卡片 id → 向量
        self.chunk_vecs = {}        # 段落 id → 向量
        self.status = "off"
        self.message = ""
        self._generation = 0
        self._lock = threading.Lock()
        self._query_cache = {}

    # ---------- 建立 ----------
    def start(self, cards: list, chunks: list, background: bool = True):
        """卡片或原文段落有變動時呼叫；只計算快取裡沒有的向量"""
        if not enabled():
            self.status, self.message = "off", "未設定 GEMINI_API_KEY 或 SEMANTIC_SEARCH=off，使用 TF-IDF 檢索"
            return
        with self._lock:
            self._generation += 1
            generation = self._generation
        items = [("card", c["id"], card_text(c)) for c in cards if c.get("id")]
        items += [("chunk", c["id"], chunk_text(c)) for c in chunks if c.get("id")]
        self.status = "building"
        self.message = f"計算 {len(items)} 筆向量中"
        if background:
            threading.Thread(target=self._build, args=(items, generation), daemon=True).start()
        else:
            self._build(items, generation)

    def _build(self, items: list, generation: int):
        import database

        try:
            keys = {(kind, item_id): cache_key("RETRIEVAL_DOCUMENT", text) for kind, item_id, text in items}
            cached = database.get_embeddings(list(keys.values()))
            vecs = {k: unpack(cached[key]) for k, key in keys.items() if key in cached}
            missing = [(kind, item_id, text) for kind, item_id, text in items if (kind, item_id) not in vecs]
            for i in range(0, len(missing), BATCH_SIZE):
                if generation != self._generation:
                    return                                   # 已有更新的建立工作
                batch = missing[i:i + BATCH_SIZE]
                for attempt in range(MAX_RETRIES):
                    try:
                        out = embed_texts([t for _, _, t in batch], "RETRIEVAL_DOCUMENT")
                        break
                    except RateLimited:
                        self.message = f"免費額度限流，{RATE_LIMIT_WAIT} 秒後重試（已完成 {len(vecs)}／{len(items)}）"
                        time.sleep(RATE_LIMIT_WAIT)
                else:
                    raise RuntimeError("多次限流，稍後重新啟動時會從快取接續")
                database.put_embeddings({keys[(k, i_)]: pack(v) for (k, i_, _), v in zip(batch, out)}, EMBED_MODEL, EMBED_DIM)
                for (k, i_, _), v in zip(batch, out):
                    vecs[(k, i_)] = v
                self.message = f"已完成 {len(vecs)}／{len(items)} 筆向量"
            if generation != self._generation:
                return
            self.card_vecs = {i_: v for (k, i_), v in vecs.items() if k == "card"}
            self.chunk_vecs = {i_: v for (k, i_), v in vecs.items() if k == "chunk"}
            self.status = "ready"
            self.message = f"語意檢索就緒：{len(self.card_vecs)} 張卡片、{len(self.chunk_vecs)} 段原文"
            print("【語意檢索】" + self.message)
        except Exception as e:
            if generation == self._generation:
                self.status, self.message = "error", f"向量建立失敗，使用 TF-IDF 檢索：{e}"
                print("【語意檢索】" + self.message)

    # ---------- 查詢 ----------
    def ready(self) -> bool:
        return self.status == "ready" and bool(self.card_vecs)

    def query_vector(self, query: str):
        """問題的向量；失敗或逾時回傳 None（呼叫端改用 TF-IDF）"""
        if not self.ready() or not query.strip():
            return None
        key = cache_key("RETRIEVAL_QUERY", query)
        if key in self._query_cache:
            return self._query_cache[key]
        try:
            vec = embed_texts([query], "RETRIEVAL_QUERY", timeout=QUERY_TIMEOUT)[0]
        except Exception as e:
            print("【語意檢索】問題向量失敗，改用 TF-IDF：", str(e)[:120])
            return None
        if len(self._query_cache) >= QUERY_CACHE_SIZE:
            self._query_cache.pop(next(iter(self._query_cache)))
        self._query_cache[key] = vec
        return vec

    def card_scores(self, qvec) -> dict:
        return {i: dot(qvec, v) for i, v in self.card_vecs.items()}

    def chunk_scores(self, qvec, ids) -> dict:
        return {i: dot(qvec, self.chunk_vecs[i]) for i in ids if i in self.chunk_vecs}

    def info(self) -> dict:
        return {"mode": "hybrid" if self.ready() else "tfidf", "status": self.status, "model": EMBED_MODEL,
                "dim": EMBED_DIM, "cards": len(self.card_vecs), "chunks": len(self.chunk_vecs), "message": self.message}


def card_text(card: dict) -> str:
    symptoms = card.get("targetSymptoms") or []
    return "\n".join(x for x in [
        card.get("title", ""), f"成分：{card.get('ingredient', '')}", f"分類：{card.get('category', '')}",
        "適用：" + "、".join(str(s) for s in symptoms), card.get("mechanism", ""), card.get("contraindications", ""),
    ] if x)


def chunk_text(chunk: dict) -> str:
    return f"{chunk.get('source_title', '')}\n{chunk.get('chunk_text', '')}"


semantic_index = SemanticIndex()
