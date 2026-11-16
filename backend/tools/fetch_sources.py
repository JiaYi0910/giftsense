# -*- coding: utf-8 -*-
"""
下載 knowledge_sources/sources.json 中可公開取得的原文（美國聯邦政府網頁與 FDA 藥品仿單），存成 knowledge_sources/ 底下的文字檔

用法（在 backend 資料夾）：
    python tools/fetch_sources.py            # 下載全部 fetch_html／fetch_openfda_label 來源
    python tools/fetch_sources.py nccih_ginkgo label_warfarin   # 只下載指定來源

- fetch_html：取網頁主要內容；頁面標題必須包含清單上的標題關鍵字，否則視為網址失效、不寫檔
- fetch_openfda_label：以網址中的 setid 向 openFDA 查詢該份仿單，存「Drug Interactions」段落
- manual／link_only 的來源不會下載（有著作權、網站擋程式或需要在查詢系統操作）
"""
import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

import knowledge_base as kb  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _title_ok(html: str, expected: str) -> bool:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    page = re.sub(r"\s+", " ", m.group(1)).lower() if m else ""
    words = [w for w in re.findall(r"[a-z0-9]+", expected.lower()) if len(w) > 3][:3]
    return bool(words) and all(w in page for w in words)


def _write(source: dict, body: str, extra: str = ""):
    path = os.path.join(kb.SOURCES_DIR, source["file"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    header = [f"# title: {source['title']}", f"# url: {source['url']}", f"# authority: {source['authority']}",
              f"# fetched: {datetime.date.today().isoformat()}", f"# license: {source.get('license', '')}"]
    if extra:
        header.append(f"# note: {extra}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(header) + "\n\n" + body.strip() + "\n")
    return path


def fetch_html(source: dict) -> str:
    html = _get(source["url"]).decode("utf-8", errors="ignore")
    if not _title_ok(html, source["title"]):
        raise RuntimeError("頁面標題和清單不符（網址可能已改版或失效），未寫檔")
    text = kb.html_to_text(html)
    if kb.text_units(text) < 150:
        raise RuntimeError("擷取到的內容太少，未寫檔")
    return _write(source, text)


def fetch_openfda_label(source: dict) -> str:
    setid = urllib.parse.parse_qs(urllib.parse.urlparse(source["url"]).query)["setid"][0]
    data = json.loads(_get("https://api.fda.gov/drug/label.json?search=set_id:%22" + setid + "%22&limit=1"))
    label = data["results"][0]
    sections = [("Drug Interactions", label.get("drug_interactions") or [])]
    body = []
    for name, texts in sections:
        if texts:
            body.append("## " + name)
            body.extend(t.strip() for t in texts)
    if not body:
        raise RuntimeError("openFDA 仿單沒有 Drug Interactions 段落")
    brand = ", ".join((label.get("openfda") or {}).get("manufacturer_name") or [])
    return _write(source, "\n\n".join(body), extra=f"openFDA set_id {setid}；effective {label.get('effective_time', '')}；{brand}")


def main(only=None):
    ok, failed = 0, []
    for s in kb.load_manifest():
        if only and s["id"] not in only:
            continue
        mode = s.get("content")
        try:
            if mode == "fetch_html":
                path = fetch_html(s)
            elif mode == "fetch_openfda_label":
                path = fetch_openfda_label(s)
            else:
                continue
            ok += 1
            print(f"OK   {s['id']} → {os.path.relpath(path, kb.SOURCES_DIR)}")
        except Exception as e:
            failed.append(s["id"])
            print(f"FAIL {s['id']}：{e}")
    print(f"完成：{ok} 份下載成功，{len(failed)} 份失敗 {failed if failed else ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(set(sys.argv[1:]) or None))
