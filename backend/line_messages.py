"""
GiftSense LINE 訊息卡片（Flex Message）

所有機器人回覆統一使用同一種卡片樣式，配色與圖文選單一致：
淡藍標頭 + GiftSense 品牌字 + 深藍大標題、內容區、底部操作按鈕。
警示類（緊急求助、綁定失敗）使用紅色版本。
"""
from typing import Any, Dict, List, Optional, Tuple

BRAND = "#2563EB"
TITLE = "#1E3A66"
TEXT = "#334155"
MUTED = "#64748B"
HEADER_BG = "#EFF6FF"
INFO_BG = "#EFF6FF"
INFO_TEXT = "#1D4ED8"
DANGER = "#C82D2D"
DANGER_BG = "#FEF2F2"
DANGER_BUTTON = "#DC2626"


def button(label: str, text: Optional[str] = None, uri: Optional[str] = None, primary: bool = False) -> Dict[str, Any]:
    action = {"type": "uri", "label": label, "uri": uri} if uri else {"type": "message", "label": label, "text": text or label}
    return {"type": "button", "style": "primary" if primary else "secondary", "height": "sm", "action": action, "_primary": primary}


def _text(text: str, size: str = "md", color: str = TEXT, weight: str = "regular", **extra) -> Dict[str, Any]:
    return {"type": "text", "text": text or " ", "size": size, "color": color, "weight": weight, "wrap": True, **extra}


def card(
    title: str,
    *,
    subtitle: Optional[str] = None,
    paragraphs: Optional[List[str]] = None,
    steps: Optional[List[str]] = None,
    info: Optional[str] = None,
    rows: Optional[List[Tuple[str, str]]] = None,
    note: Optional[str] = None,
    buttons: Optional[List[Dict[str, Any]]] = None,
    danger: bool = False,
    compact: bool = False,
    alt_text: Optional[str] = None,
) -> Dict[str, Any]:
    """組出一張 GiftSense 標準卡片，回傳可直接放進 messages 的 Flex Message"""
    header_contents = [
        _text("GiftSense", size="xs", color=DANGER if danger else BRAND, weight="bold"),
        _text(title, size="lg" if compact else "xl", color=DANGER if danger else TITLE, weight="bold", margin="sm"),
    ]
    if subtitle:
        header_contents.append(_text(subtitle, size="sm", color=MUTED, margin="sm"))

    body: List[Dict[str, Any]] = []
    for p in paragraphs or []:
        body.append(_text(p))
    if steps:
        body.append({
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                {
                    "type": "box", "layout": "horizontal", "spacing": "md",
                    "contents": [
                        _text(str(i), size="md", color=BRAND, weight="bold", flex=0),
                        _text(step, flex=1),
                    ],
                }
                for i, step in enumerate(steps, 1)
            ],
        })
    if rows:
        body.append({
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                {
                    "type": "box", "layout": "horizontal",
                    "contents": [
                        _text(k, size="sm", color=MUTED, flex=2),
                        _text(v, size="md", color=TEXT, weight="bold", flex=5),
                    ],
                }
                for k, v in rows
            ],
        })
    if info:
        body.append({
            "type": "box", "layout": "vertical", "cornerRadius": "12px", "paddingAll": "14px",
            "backgroundColor": DANGER_BG if danger else INFO_BG,
            "contents": [_text(info, size="md", color=DANGER if danger else INFO_TEXT, weight="bold", align="center")],
        })
    if note:
        body.append(_text(note, size="xs", color=MUTED))

    bubble: Dict[str, Any] = {
        "type": "bubble",
        "size": "kilo" if compact else "mega",
        "header": {
            "type": "box", "layout": "vertical", "paddingAll": "16px" if compact else "20px",
            "backgroundColor": DANGER_BG if danger else HEADER_BG,
            "contents": header_contents,
        },
    }
    if body:
        bubble["body"] = {"type": "box", "layout": "vertical", "spacing": "lg", "paddingAll": "20px", "contents": body}
    if buttons:
        footer_buttons = []
        for b in buttons:
            b = dict(b)
            if b.pop("_primary", False):
                b["color"] = DANGER_BUTTON if danger else BRAND
            footer_buttons.append(b)
        bubble["footer"] = {"type": "box", "layout": "vertical", "spacing": "sm", "paddingAll": "16px", "contents": footer_buttons}
        bubble["styles"] = {"footer": {"separator": True}}

    summary = alt_text or " ".join([title] + (paragraphs or [])[:1])
    return {"type": "flex", "altText": summary[:300], "contents": bubble}
