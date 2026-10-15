# -*- coding: utf-8 -*-
"""
購物回饋的收據辨識：把使用者上傳的收據／電子發票／訂單完成截圖交給 Google Gemini，
讀出藥局名稱、訂單或發票號碼、購買時間與總金額。

- 金鑰：環境變數 GEMINI_API_KEY（Render Environment）
- 模型：環境變數 GEMINI_RECEIPT_MODEL，未設定時用 DEFAULT_MODEL
- 影像只在這次請求中傳給 Gemini，伺服器不保存
"""
import base64
import json
import os
import re
from datetime import datetime, timedelta

import requests

DEFAULT_MODEL = "gemini-2.5-flash"
REQUEST_TIMEOUT = 40

# 藥局名稱比對：收據上常印公司全名或門市名稱，只要包含任一關鍵字就算同一家
PHARMACY_KEYWORDS = {
    "大樹藥局": ("大樹",),
    "杏一醫療": ("杏一",),
    "啄木鳥藥局": ("啄木鳥",),
    "丁丁藥局": ("丁丁",),
}

PROMPT = """你是收據辨識助手。這張圖片應該是台灣藥局的購物收據、電子發票證明聯，或網路商店的訂單完成畫面。
請只依照圖片上實際看得到的文字回答，看不到或不確定的欄位請填空字串或 0，不要猜測。

- is_receipt：圖片是否為購物收據、發票或訂單完成畫面
- document_type：receipt（紙本收據）、e_invoice（電子發票）、order_screenshot（訂單完成畫面）或 other
- store_name：印在圖片上的店家、公司或門市名稱
- order_number：訂單編號；沒有訂單編號時填發票號碼（例如 AB-12345678）
- purchase_time：購買或下單時間，格式 YYYY-MM-DD HH:MM；只看得到日期時填 YYYY-MM-DD；民國年請換算成西元年
- total_amount：實際付款總金額（新台幣整數，不含幣別符號與逗號）
- confidence：0 到 1，表示你對以上欄位都讀對的把握；圖片模糊、被裁切或反光時請給低分"""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "is_receipt": {"type": "BOOLEAN"},
        "document_type": {"type": "STRING"},
        "store_name": {"type": "STRING"},
        "order_number": {"type": "STRING"},
        "purchase_time": {"type": "STRING"},
        "total_amount": {"type": "INTEGER"},
        "confidence": {"type": "NUMBER"},
    },
    "required": ["is_receipt", "store_name", "order_number", "purchase_time", "total_amount", "confidence"],
}


class ReceiptScanError(Exception):
    """辨識服務無法使用（未設定金鑰、連線失敗、回應格式錯誤）"""


def call_gemini(image_bytes: bytes, mime_type: str) -> dict:
    """送出圖片給 Gemini，回傳模型輸出的 JSON 物件（未整理）"""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ReceiptScanError("尚未設定 GEMINI_API_KEY")
    model = os.environ.get("GEMINI_RECEIPT_MODEL", "").strip() or DEFAULT_MODEL
    payload = {
        "contents": [{
            "parts": [
                {"text": PROMPT},
                {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("ascii")}},
            ]
        }],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    try:
        res = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key},
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        raise ReceiptScanError(f"無法連線 Gemini：{e}") from e
    if res.status_code != 200:
        raise ReceiptScanError(f"Gemini 回應 HTTP {res.status_code}：{res.text[:300]}")
    try:
        parts = res.json()["candidates"][0]["content"]["parts"]
        # 2.5 系列模型可能附帶思考內容（thought），只取正式回答的文字
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        data = json.loads(text.replace("```json", "").replace("```", "").strip())
    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as e:
        raise ReceiptScanError(f"Gemini 回應格式無法解析：{e}") from e
    if not isinstance(data, dict):
        raise ReceiptScanError("Gemini 回應不是 JSON 物件")
    return data


def _parse_amount(value) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(round(value))
    digits = re.sub(r"[^\d.]", "", str(value or ""))
    try:
        return int(round(float(digits))) if digits else 0
    except ValueError:
        return 0


def _parse_confidence(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def parse_purchase_time(value):
    """回傳 (datetime, 是否有時間)；看不懂時回傳 (None, False)"""
    text = re.sub(r"\s+", " ", str(value or "").strip().replace("/", "-").replace("T", " "))
    for fmt, has_time in (("%Y-%m-%d %H:%M:%S", True), ("%Y-%m-%d %H:%M", True), ("%Y-%m-%d", False)):
        try:
            return datetime.strptime(text, fmt), has_time
        except ValueError:
            continue
    return None, False


def normalize_order_number(value) -> str:
    """去掉空白、連字號等符號並轉大寫，避免同一張發票換個寫法重複登錄"""
    return re.sub(r"[^0-9A-Za-z]", "", str(value or "")).upper()


def pharmacy_matches(expected: str, store_name: str) -> bool:
    store = re.sub(r"\s+", "", store_name or "")
    if not store:
        return False
    for name, keywords in PHARMACY_KEYWORDS.items():
        if name in (expected or "") or (expected or "") in name:
            return any(k in store for k in keywords)
    # 不在對照表裡的藥局：去掉常見字尾後比對
    core = re.sub(r"(藥局|藥妝|醫療用品|醫療|股份有限公司|有限公司|門市)", "", expected or "")
    return bool(core) and core in store


def validate_receipt(scan: dict, pharmacy: str, clicked_at: datetime, now: datetime,
                     max_amount: int, min_confidence: float):
    """檢查辨識結果能不能用在這筆購物追蹤；回傳 (錯誤訊息或 None, 是否請使用者重拍)"""
    if not scan["is_receipt"]:
        return "這張圖片看起來不是收據、發票或訂單完成畫面，請重新拍攝", True
    if scan["confidence"] < min_confidence:
        return "收據看不太清楚，請在光線充足的地方把整張收據拍進畫面後重新上傳", True
    missing = [label for label, ok in (
        ("店家名稱", scan["store_name"]),
        ("訂單或發票號碼", scan["order_number"]),
        ("購買時間", scan["purchase_time"]),
        ("付款金額", scan["total_amount"] > 0),
    ) if not ok]
    if missing:
        return f"收據上讀不到{'、'.join(missing)}，請重新拍攝完整收據", True
    if not pharmacy_matches(pharmacy, scan["store_name"]):
        return f"收據上的店家是「{scan['store_name']}」，和這筆追蹤的【{pharmacy}】不同，無法回饋", False
    bought = scan["purchase_time"]
    if not scan["has_time"] and bought.date() == clicked_at.date():
        return "收據上看不到購買時間，請改上傳有時間的收據或訂單完成畫面", True
    # 收據時間只到分鐘：和前往藥局的時間比較時也只看到分鐘
    if bought < clicked_at.replace(second=0, microsecond=0):
        return (f"收據的購買時間（{bought.strftime('%Y/%m/%d %H:%M')}）早於你從 GiftSense 前往藥局的時間"
                f"（{clicked_at.strftime('%Y/%m/%d %H:%M')}），無法回饋"), False
    if bought > now.replace(second=0, microsecond=0) + timedelta(minutes=10):
        return "收據的購買時間比現在還晚，請確認上傳的收據是否正確", True
    if scan["total_amount"] > max_amount:
        return f"付款金額 ${scan['total_amount']:,} 超過單筆回饋上限 ${max_amount:,}，無法自動回饋", False
    return None, False


def scan_receipt(image_bytes: bytes, mime_type: str) -> dict:
    """辨識收據並整理成固定欄位；辨識服務無法使用時拋出 ReceiptScanError"""
    raw = call_gemini(image_bytes, mime_type)
    purchase_time, has_time = parse_purchase_time(raw.get("purchase_time"))
    return {
        "is_receipt": bool(raw.get("is_receipt")),
        "document_type": str(raw.get("document_type") or "").strip()[:30],
        "store_name": str(raw.get("store_name") or "").strip()[:80],
        "order_number": normalize_order_number(raw.get("order_number"))[:40],
        "purchase_time": purchase_time,
        "has_time": has_time,
        "total_amount": _parse_amount(raw.get("total_amount")),
        "confidence": _parse_confidence(raw.get("confidence")),
    }
