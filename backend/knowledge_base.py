# -*- coding: utf-8 -*-
"""
AI 守護助理的知識來源（RAG 的原文依據）

- knowledge_sources/sources.json：所有來源的清單（標題、機構、網址、授權、對應成分、查證紀錄）
- knowledge_sources/ 底下的 .txt／.md／.html／.pdf：來源原文。美國官方網頁、FDA 仿單與食藥署食品原料資料由 tools/fetch_sources.py 下載，
  其他查詢系統的結果頁與 NIH ODS 由使用者以瀏覽器存檔放入
- 原文切成段落（中文約 300–500 字；英文約 150–250 個單字），連同 source_title、authority、url、ingredient 存進資料庫，
  實際寫入由 database.sync_knowledge_base() 在啟動時依內容的雜湊值判斷要不要重做

只存原文段落與書目，不在這裡產生任何新的內容；有著作權或網站擋程式下載的來源只保留連結（content = link_only）。
"""
import hashlib
import json
import os
import re
from functools import lru_cache

SOURCES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge_sources")
MANIFEST_PATH = os.path.join(SOURCES_DIR, "sources.json")
CHUNKER_VERSION = "2"            # 切段規則改變時調高，讓啟動時重新匯入
FETCHED_MODES = ("fetch_html", "fetch_openfda_label", "fetch_tfda_material")   # 由 tools/fetch_sources.py 下載原文的來源
CONTENT_MODES = FETCHED_MODES + ("link_only", "manual")

ZH_MIN, ZH_MAX = 300, 500        # 中文：字數
EN_MIN, EN_MAX = 150, 250        # 英文：單字數（約 900–1,500 個字元）
TEXT_EXTS = (".txt", ".md")
HTML_EXTS = (".html", ".htm")


# -------------------------------------------------------------------------
# 來源清單
# -------------------------------------------------------------------------
def load_manifest(path: str = MANIFEST_PATH) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("sources", [])


@lru_cache(maxsize=1)
def _sources_by_id() -> dict:
    return {s["id"]: s for s in load_manifest()}


def source_refs(ids) -> list:
    """API 回傳用的來源摘要（只含清單裡查得到的來源；不認識的 id 直接略過，不會產生假的出處）"""
    refs, seen = [], set()
    by_id = _sources_by_id()
    for sid in ids or []:
        s = by_id.get(sid)
        if not s or sid in seen or not s.get("url"):
            continue
        if s.get("content") == "manual" and not source_files(s):
            continue                      # 待使用者存檔的來源：原文檔放進來之前不列為出處
        seen.add(sid)
        refs.append({"id": sid, "title": s["title"], "authority": s.get("authority", ""), "url": s["url"],
                     "type": s.get("type", ""), "citation": s.get("citation", "")})
    return refs


# -------------------------------------------------------------------------
# 原文擷取
# -------------------------------------------------------------------------
_NOISE_TAGS = ("script", "style", "noscript", "nav", "aside", "header", "footer", "form", "button", "svg", "figure", "iframe")
_BLOCK_TAGS = ("h1", "h2", "h3", "h4", "p", "li", "td", "th", "dd", "dt", "blockquote")
# 遇到這些小節標題就停止：之後是參考文獻、延伸資源、免責聲明與聯絡資訊，不是衛教內容
_STOP_HEADINGS = re.compile(r"^(key references|other references|selected references|references|for more information|additional resources|"
                            r"acknowledg(e)?ments?|about this pdq summary|changes to this summary|contact us|disclaimer)\b", re.I)


def html_to_text(html: str) -> str:
    """取出網頁主要內容的文字（去掉導覽列、選單、頁尾），每個段落一行"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one("main") or soup.select_one("article") or soup.select_one("[role=main]") or soup.body or soup
    for tag in root.find_all(_NOISE_TAGS):
        tag.decompose()
    for tag in root.select("[role=navigation], .breadcrumb, .breadcrumbs, .menu, .nav, .pager, .share, .social, .visually-hidden"):
        tag.decompose()
    lines = []
    for el in root.find_all(_BLOCK_TAGS):
        if el.find(_BLOCK_TAGS):          # 外層容器（例如 li 裡還有 p）交給內層處理
            continue
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if not text:
            continue
        links = "".join(a.get_text(" ", strip=True) for a in el.find_all("a"))
        if el.name == "li" and len(links) >= len(text) * 0.9:
            continue                      # 只有連結的清單項目多半是選單
        is_heading = el.name in ("h1", "h2", "h3", "h4")
        if is_heading and lines and _STOP_HEADINGS.match(text):
            break
        if not is_heading and len(text) < 25:
            continue
        lines.append(("## " if el.name in ("h2", "h3", "h4") else "") + text)
    out, prev = [], None
    for line in lines:
        if line != prev:
            out.append(line)
        prev = line
    return "\n\n".join(out)


def pdf_to_text(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("讀取 PDF 需要 pypdf（pip install pypdf）") from e
    reader = PdfReader(path)
    return "\n\n".join((page.extract_text() or "").strip() for page in reader.pages)


def read_source_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXTS:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        # 檔頭的「# key: value」是下載紀錄，不算原文
        return "\n".join(l for l in text.splitlines() if not re.match(r"^# (title|url|authority|fetched|license|source|set_id|note):", l)).strip()
    if ext in HTML_EXTS:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return html_to_text(f.read())
    if ext == ".pdf":
        return pdf_to_text(path)
    raise ValueError(f"不支援的檔案格式：{path}")


def source_files(source: dict) -> list:
    """來源對應的原文檔。file 可以是單一檔案，或以 / 結尾的資料夾（資料夾內檔名以來源 id 開頭的都算）"""
    f = source.get("file")
    if not f:
        return []
    full = os.path.join(SOURCES_DIR, f)
    if f.endswith("/"):
        if not os.path.isdir(full):
            return []
        return sorted(os.path.join(full, n) for n in os.listdir(full)
                      if n.startswith(source["id"]) and os.path.splitext(n)[1].lower() in TEXT_EXTS + HTML_EXTS + (".pdf",))
    return [full] if os.path.exists(full) else []


# -------------------------------------------------------------------------
# 切段
# -------------------------------------------------------------------------
_CJK = re.compile(r"[㐀-鿿豈-﫿]")


def text_units(text: str) -> int:
    """中文以字計、英文以單字計"""
    return len(_CJK.findall(text)) + len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’\-.]*", _CJK.sub(" ", text)))


def _sentences(paragraph: str) -> list:
    parts = re.split(r"(?<=[。！？；.!?;])\s+|(?<=[。！？；])", paragraph)
    return [p.strip() for p in parts if p and p.strip()]


def chunk_text(text: str, language: str = "en") -> list:
    """依段落與句子切成約 300–500 字（中文）或 150–250 個單字（英文）的段落；小節標題併入下一段"""
    lo, hi = (ZH_MIN, ZH_MAX) if language.startswith("zh") else (EN_MIN, EN_MAX)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces = []
    for p in paragraphs:
        if text_units(p) <= hi:
            pieces.append(p)
        else:
            buf = ""
            for s in _sentences(p):
                if buf and text_units(buf + " " + s) > hi:
                    pieces.append(buf)
                    buf = s
                else:
                    buf = (buf + " " + s).strip()
            if buf:
                pieces.append(buf)
    chunks, buf, heading = [], "", ""
    for piece in pieces:
        if piece.startswith("## "):
            if buf and text_units(buf) >= lo:
                chunks.append(buf)
                buf = ""
            heading = piece[3:].strip()
            buf = (buf + "\n" + heading).strip() if buf else heading
            continue
        candidate = (buf + "\n" + piece).strip()
        if buf and text_units(candidate) > hi:       # 一律不超過上限；寧可這段稍短
            if buf != heading:                       # 只有小節標題時不單獨成段
                chunks.append(buf)
            with_heading = (heading + "\n" + piece) if heading else piece
            buf = with_heading if text_units(with_heading) <= hi else piece
        else:
            buf = candidate
    if buf:
        if chunks and text_units(buf) < lo // 2 and text_units(chunks[-1] + "\n" + buf) <= hi:
            chunks[-1] = chunks[-1] + "\n" + buf      # 太短的結尾併入前一段（不超過上限時）
        else:
            chunks.append(buf)
    return chunks


# -------------------------------------------------------------------------
# 匯入資料
# -------------------------------------------------------------------------
def build_rows(manifest: list = None) -> tuple:
    """回傳 (sources, chunks, missing)：sources／chunks 是要寫進資料庫的資料，missing 是清單裡有、但還沒有原文檔的來源"""
    manifest = load_manifest() if manifest is None else manifest
    sources, chunks, missing = [], [], []
    for s in manifest:
        files = source_files(s)
        texts = []
        for path in files:
            try:
                t = read_source_file(path)
            except Exception as e:
                print(f"【知識庫】略過 {os.path.relpath(path, SOURCES_DIR)}：{e}")
                continue
            start = s.get("start_heading")
            if start and f"## {start}" in t:
                t = t[t.index(f"## {start}"):]     # 只收和保健品相關的小節（例如 NCI 營養照護的後半段）
            if t.strip():
                texts.append(t)
        if s.get("content") in FETCHED_MODES + ("manual",) and not texts:
            missing.append(s["id"])
        parts = []
        for t in texts:
            parts.extend(chunk_text(t, s.get("language", "en")))
        ingredient = ", ".join(s.get("ingredients") or [])
        for i, part in enumerate(parts):
            chunks.append({"id": f"{s['id']}#{i + 1:03d}", "source_id": s["id"], "chunk_index": i + 1,
                           "source_title": s["title"], "authority": s.get("authority", ""), "url": s.get("url", ""),
                           "ingredient": ingredient, "language": s.get("language", "en"), "chunk_text": part})
        sources.append({"id": s["id"], "title": s["title"], "authority": s.get("authority", ""), "url": s.get("url", ""),
                        "source_type": s.get("type", ""), "content_mode": s.get("content", ""), "language": s.get("language", "en"),
                        "license": s.get("license", ""), "citation": s.get("citation", ""),
                        "ingredients_json": json.dumps(s.get("ingredients") or [], ensure_ascii=False),
                        "topics_json": json.dumps(s.get("topics") or [], ensure_ascii=False),
                        "verified": s.get("verified", ""), "chunk_count": len(parts)})
    return sources, chunks, missing


def content_checksum(manifest_path: str = MANIFEST_PATH) -> str:
    """清單與所有原文檔的雜湊值：內容沒變就不用重新匯入"""
    h = hashlib.sha256(CHUNKER_VERSION.encode())
    if os.path.exists(manifest_path):
        with open(manifest_path, "rb") as f:
            h.update(f.read())
    for root, _, files in os.walk(SOURCES_DIR):
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() in TEXT_EXTS + HTML_EXTS + (".pdf",):
                path = os.path.join(root, name)
                h.update(os.path.relpath(path, SOURCES_DIR).replace("\\", "/").encode())
                with open(path, "rb") as f:
                    h.update(f.read())
    return h.hexdigest()
