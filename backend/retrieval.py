# -*- coding: utf-8 -*-
"""
RAG 第二階段：混合檢索、原文段落與多機構交叉驗證

1. 卡片檢索：TF-IDF（字面）＋ Gemini 語意向量；語意向量不可用時只用 TF-IDF，結果與第一階段相同
2. 原文段落：從知識庫 141 段原文中，找出和問題最相關、且屬於同一成分的段落（最多 2 段，盡量來自不同來源），直接引用原文
3. 交叉驗證：統計卡片出處與引用段落涵蓋幾個機構；2 個以上標示「多機構來源」，只有 1 個標示「僅單一來源」
   （NIH 底下的 NCCIH、NEI、ODS、MedlinePlus 等算同一個機構；FDA 網頁與 FDA 仿單算同一個機構；每本期刊各算一個機構）
"""
import re

import knowledge_base as kb
import live_sources
from semantic_index import semantic_index
from vector_store import global_vector_store

# 門檻與權重：依 gemini-embedding-001 實測分數校正（2026-11-17，見 docs/RAG_待查證清單.md 第八節）
#   快速提問 208 題（含「爺爺」版本）正確卡片的語意分數 ≥ 0.618；無關問題 20 題最高 0.579；
#   送禮、App 操作等邊界問題最高 0.653（且會配錯卡片）
SEM_MIN = 0.68            # TF-IDF 未達門檻時，語意相似度要達此值才算候選
SEM_FLOOR = 0.60          # TF-IDF 達門檻但語意相似度低於此值：視為字面巧合，排除（例如「高鐵票怎麼訂」）
SEM_WEIGHT = 1.0
TFIDF_WEIGHT = 0.5
PASSAGE_SEM_MIN = 0.60    # 卡片以外的同成分原文段落，語意相似度要達此值才引用
MAX_PASSAGES = 2
EXCERPT_ZH = 180
EXCERPT_EN = 360

_chunks = []              # 啟動時由資料庫載入的原文段落


def load_chunks(chunks: list):
    global _chunks
    _chunks = [dict(c) for c in chunks or []]
    return len(_chunks)


def chunk_count() -> int:
    return len(_chunks)


# -------------------------------------------------------------------------
# 1. 卡片檢索
# -------------------------------------------------------------------------
def search_cards(query: str, top_k: int = 3) -> tuple:
    """回傳 (卡片清單, 檢索資訊)；卡片附 vector_score（TF-IDF）與 semantic_score"""
    tf = global_vector_store.scores(query)
    qvec = semantic_index.query_vector(query)
    info = {"mode": "tfidf", "qvec": None}
    if qvec is None:
        return global_vector_store.search(query, top_k=top_k), info
    sem = semantic_index.card_scores(qvec)
    info = {"mode": "hybrid", "qvec": qvec}
    ranked = []
    for tf_score, doc in tf:
        s = sem.get(doc.get("id"))
        if s is None:                        # 管理員剛新增、向量還沒算好的卡片：只用 TF-IDF
            if tf_score >= global_vector_store.TFIDF_MIN_SCORE:
                ranked.append((tf_score, tf_score, None, doc))
            continue
        if s >= SEM_FLOOR and (tf_score >= global_vector_store.TFIDF_MIN_SCORE or s >= SEM_MIN):
            ranked.append((SEM_WEIGHT * s + TFIDF_WEIGHT * tf_score, tf_score, s, doc))
    ranked.sort(key=lambda x: x[0], reverse=True)
    out = []
    for hybrid, tf_score, s, doc in ranked[:top_k]:
        d = dict(doc)
        d["vector_score"] = round(float(tf_score), 4)
        d["semantic_score"] = round(float(s), 4) if s is not None else None
        d["hybrid_score"] = round(float(hybrid), 4)
        out.append(d)
    return out, info


# -------------------------------------------------------------------------
# 2. 原文段落
# -------------------------------------------------------------------------
_EN_WORD = re.compile(r"[a-z][a-z0-9\-]{3,}")
# 挑句子時優先選安全資訊（限量、警語、交互作用、出血風險）
_SAFETY = ("限量", "警語", "不宜", "不得", "避免", "標示", "交互作用", "出血", "interact", "bleeding", "risk", "avoid",
           "warning", "side effect", "liver", "not recommend", "safe")
_ZH = re.compile(r"[一-鿿]")


def _terms(query: str, card: dict) -> list:
    """段落內挑句子用的關鍵字：卡片成分的英文字、問題中的英文字與中文雙字詞"""
    text = f"{card.get('ingredient', '')} {query}".lower()
    terms = set(_EN_WORD.findall(text))
    zh = _ZH.findall(query)
    terms |= {zh[i] + zh[i + 1] for i in range(len(zh) - 1)}
    return [t for t in terms if t not in ("with", "from", "that", "this")]


def _sentences(text: str, language: str) -> list:
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if language == "zh":
            out.extend(s for s in re.split(r"(?<=[。！？；])", line) if s.strip())
        else:
            out.extend(live_sources.split_sentences(line))
    return out


def excerpt(text: str, language: str, terms: list) -> str:
    sentences = _sentences(text, language)
    if not sentences:
        return ""
    limit = EXCERPT_ZH if language == "zh" else EXCERPT_EN
    scores = [sum(1 for t in terms if t in s.lower()) + 0.6 * any(w in s.lower() for w in _SAFETY) for s in sentences]
    start = max(range(len(sentences)), key=lambda i: (scores[i], len(sentences[i]) > 20))
    picked = ""
    for s in sentences[start:]:
        if not picked:
            joiner = ""
        elif language == "zh":
            joiner = "" if picked[-1] in "。！？；：" else "；"    # 不同行（例如食藥署的欄位）之間加分號
        else:
            joiner = " "
        if picked and len(picked) + len(s) > limit:
            break
        picked += joiner + s
    if len(picked) > limit:
        picked = picked[:limit].rstrip() + "…"
    return picked


def _card_source_ids(card: dict) -> list:
    return [r["id"] for r in card.get("sources") or kb.source_refs(card.get("sourceIds") or [])]


def find_passages(query: str, card: dict, qvec=None) -> list:
    """和卡片同一成分的原文段落中，挑出最相關的段落（盡量來自不同來源）"""
    if not _chunks or not card:
        return []
    manifest = {s["id"]: s for s in kb.load_manifest()}
    own = _card_source_ids(card)
    keys = set()
    for sid in own:
        keys |= {k for k in manifest.get(sid, {}).get("ingredients") or [] if k != "interactions"}
    candidates = [c for c in _chunks if c["source_id"] in own
                  or keys & {k.strip() for k in (c.get("ingredient") or "").split(",") if k.strip()}]
    if not candidates:
        return []
    terms = _terms(query, card)
    scored = []
    if qvec is not None:
        # 卡片本身引用的出處一律可選、依語意排序；同成分的其他來源要達門檻才選
        sem = semantic_index.chunk_scores(qvec, [c["id"] for c in candidates])
        for c in candidates:
            s = sem.get(c["id"])
            if s is not None and (c["source_id"] in own or s >= PASSAGE_SEM_MIN):
                scored.append((s, c))
    if not scored:
        # 沒有語意向量：以關鍵字命中數排序，卡片本身的出處優先
        for c in candidates:
            low = c["chunk_text"].lower()
            hits = sum(1 for t in terms if t in low)
            if hits:
                scored.append((hits + (0.5 if c["source_id"] in own else 0), c))
        if not scored:                       # 沒有關鍵字命中：取卡片第一個出處的第一段
            first = next((c for sid in own for c in candidates if c["source_id"] == sid), None)
            scored = [(0.0, first)] if first else []
    scored.sort(key=lambda x: x[0], reverse=True)
    # 先挑不同機構的段落（交叉驗證），不夠再補同機構的其他來源
    chosen, sources, orgs = [], set(), set()
    for distinct_org in (True, False):
        for score, c in scored:
            org = institution(c["authority"])
            if len(chosen) >= MAX_PASSAGES or c["source_id"] in sources or (distinct_org and org in orgs):
                continue
            chosen.append((score, c))
            sources.add(c["source_id"])
            orgs.add(org)
    picked = [{"id": c["id"], "source_id": c["source_id"], "title": c["source_title"], "authority": c["authority"],
               "url": c["url"], "language": c.get("language", "en"), "score": round(float(score), 4),
               "excerpt": excerpt(c["chunk_text"], c.get("language", "en"), terms)} for score, c in chosen]
    return [p for p in picked if p["excerpt"]]


# -------------------------------------------------------------------------
# 3. 交叉驗證
# -------------------------------------------------------------------------
_ORG_RULES = [
    (r"衛生福利部食品藥物管理署|食藥署", "衛福部食藥署"),
    (r"國民健康署", "衛福部國健署"),
    (r"NIH|美國國家衛生研究院|美國國家癌症研究院|NCI|MedlinePlus|美國國家醫學圖書館", "美國國家衛生研究院（NIH）"),
    (r"FDA|DailyMed|美國食品藥物管理局", "美國 FDA"),
    (r"CDC|疾病管制", "美國 CDC"),
    (r"WHO|世界衛生組織", "世界衛生組織（WHO）"),
    (r"Cochrane", "Cochrane 實證回顧"),
]


def institution(authority: str) -> str:
    for pattern, name in _ORG_RULES:
        if re.search(pattern, authority or ""):
            return name
    return re.sub(r"（期刊）$", " 期刊", authority or "").strip()


def evidence_check(*source_lists) -> dict:
    orgs = []
    for refs in source_lists:
        for r in refs or []:
            org = institution(r.get("authority", ""))
            if org and org not in orgs:
                orgs.append(org)
    if len(orgs) >= 2:
        return {"status": "multi", "institutions": orgs,
                "label": f"多機構來源：{'、'.join(orgs)}（{len(orgs)} 個機構）"}
    if orgs:
        return {"status": "single", "institutions": orgs, "label": f"僅單一來源：{orgs[0]}"}
    return {"status": "none", "institutions": [], "label": "尚無已存原文的出處"}


def passages_text(passages: list, evidence: dict) -> str:
    """離線回覆用：引用的原文段落與交叉驗證結果"""
    lines = [f"【交叉驗證】{evidence['label']}"]
    if passages:
        lines.append("知識庫原文段落：")
        for p in passages:
            lines.append(f"・{p['authority']}：{p['title']}（{p['url']}）")
            lines.append(f"  「{p['excerpt']}」")
    return "\n".join(lines)
