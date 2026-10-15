"""
購物回饋收據掃描：金額由伺服器辨識收據取得，通過檢查後待入帳 7 天，期滿自動入帳。

執行（在 backend 資料夾）：
    python -m pytest tests/test_cashback_receipt.py -q
    或 python tests/test_cashback_receipt.py

測試使用 caregift.db 的暫存複本，不會改到 repo 內的資料庫；Gemini 一律以假的回應取代，不連線 Google。
"""
import base64
import hashlib
import itertools
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP_DIR = tempfile.mkdtemp(prefix="giftsense_receipt_test_")
TEST_DB = os.path.join(_TMP_DIR, "caregift.db")
shutil.copy(os.path.join(BACKEND, "caregift.db"), TEST_DB)

os.environ["CAREGIFT_DB_PATH"] = TEST_DB
os.environ["AUTH_TOKEN_SECRET"] = "test-only-auth-secret"
for _key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "GEMINI_API_KEY", "GEMINI_RECEIPT_MODEL"):
    os.environ.pop(_key, None)

os.chdir(BACKEND)  # main.py 以相對路徑掛載 static/uploads
sys.path.insert(0, BACKEND)

import database  # noqa: E402

if database.DB_PATH != TEST_DB:  # 同一個 pytest 行程裡已有其他測試先載入 database
    database.DB_PATH = TEST_DB
    database.init_db()
assert not database.USE_TURSO, "測試不可連線 Turso"

import main  # noqa: E402
import receipt_scanner  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app)  # 不用 with：不跑 startup 的藥局爬蟲預熱與自動入帳排程

ALICE = "receipt_alice@example.test"
BOB = "receipt_bob@example.test"
CAROL = "receipt_carol@example.test"  # 只用在入帳時間的測試，避免結算到其他測試的待入帳紀錄
_unique = itertools.count(1)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _register(account):
    res = client.post("/api/auth/register", json={"account": account, "password": f"pw-{account}", "name": account})
    data = res.json()
    if not data.get("success"):  # 已存在就改用登入
        data = client.post("/api/auth/login", json={"account": account, "password": f"pw-{account}"}).json()
    assert data["success"] and data["user_token"]
    return data["user_token"]


@pytest.fixture(scope="module")
def alice():
    return _register(ALICE)


@pytest.fixture(scope="module")
def bob():
    return _register(BOB)


@pytest.fixture(scope="module")
def carol():
    return _register(CAROL)


class FakeGemini:
    """取代 receipt_scanner.call_gemini：回傳設定好的辨識結果，並記錄收到的圖片"""

    def __init__(self):
        self.calls = []
        self.result = None
        self.error = None

    def __call__(self, image_bytes, mime_type):
        self.calls.append((image_bytes, mime_type))
        if self.error:
            raise self.error
        return dict(self.result)


@pytest.fixture
def gemini(monkeypatch):
    fake = FakeGemini()
    monkeypatch.setattr(receipt_scanner, "call_gemini", fake)
    return fake


def gemini_receipt(**overrides):
    """Gemini 會回傳的 JSON：預設是一張剛剛在大樹藥局買的電子發票"""
    n = next(_unique)
    data = {
        "is_receipt": True,
        "document_type": "e_invoice",
        "store_name": "大樹醫藥股份有限公司 新莊中正門市",
        "order_number": f"RC-{n:08d}",
        "purchase_time": (datetime.now() + timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M"),
        "total_amount": 1280,
        "confidence": 0.95,
    }
    data.update(overrides)
    return data


def image_data_url(tag=None):
    """每次產生不同內容的假圖片（雜湊值才不會重複）"""
    payload = b"\x89PNG\r\n\x1a\n" + f"receipt-{tag or next(_unique)}-{datetime.now().timestamp()}".encode()
    return "data:image/png;base64," + base64.b64encode(payload).decode()


def track(token, pharmacy="大樹藥局", price=1390):
    res = client.post("/api/pharmacy/referral-click", headers=bearer(token), json={
        "product_name": "魚油", "pharmacy": pharmacy, "price": price, "official_url": "https://example.test",
    }).json()
    assert res["success"]
    return res["cashback"]


def upload(token, order_id, image=None, **extra):
    body = {"image": image_data_url() if image is None else image, **extra}
    res = client.post(f"/api/cashback/{order_id}/receipt", headers=bearer(token), json=body)
    assert res.status_code == 200
    return res.json()


def points_of(token):
    return client.get("/api/auth/profile", headers=bearer(token)).json()["profile"]["points"]


def db_row(order_id):
    conn = database.get_db()
    row = conn.execute("SELECT * FROM cashback_orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return dict(row)


# ---------------------------------------------------------------- 正常流程

def test_receipt_amount_comes_from_gemini_not_client(alice, gemini):
    gemini.result = gemini_receipt(total_amount=1280)
    order = track(alice)
    before = points_of(alice)

    res = upload(alice, order["id"], amount=99999, order_amount=99999, points=99999)
    assert res["success"], res["message"]
    saved = res["order"]
    assert saved["status"] == "pending"
    assert saved["order_amount"] == 1280
    assert saved["points"] == 64  # 大樹藥局 5%
    assert "receipt_hash" not in saved
    assert len(gemini.calls) == 1 and gemini.calls[0][1] == "image/png"
    # 尚未入帳
    assert points_of(alice) == before


def test_pending_lasts_seven_days_then_credits_once(carol, gemini):
    gemini.result = gemini_receipt(total_amount=2000)
    order = upload(carol, track(carol)["id"])["order"]
    credit_after = datetime.strptime(order["credit_after"], "%Y-%m-%d %H:%M:%S")
    assert timedelta(days=6, hours=23) < credit_after - datetime.now() <= timedelta(days=7)

    before = points_of(carol)
    assert database.settle_due_cashback(CAROL, now=credit_after - timedelta(minutes=1)) == 0
    assert db_row(order["id"])["status"] == "pending"

    assert database.settle_due_cashback(CAROL, now=credit_after) == 1
    assert database.settle_due_cashback(CAROL, now=credit_after + timedelta(days=1)) == 0  # 不重複入帳
    assert db_row(order["id"])["status"] == "confirmed"
    assert points_of(carol) == pytest.approx(before + 100)  # $2,000 × 5%
    ledger = client.get("/api/points", headers=bearer(carol)).json()["ledger"]
    assert any("購物回饋" in item["title"] and item["amount"] == 100 for item in ledger)


def test_reading_profile_credits_due_cashback(alice, gemini):
    gemini.result = gemini_receipt(total_amount=500)
    order = upload(alice, track(alice)["id"])["order"]
    conn = database.get_db()
    conn.execute("UPDATE cashback_orders SET credit_after = ? WHERE id = ?",
                 ((datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"), order["id"]))
    conn.commit()
    conn.close()

    before = database.get_user_profile(ALICE)["points"]
    after = points_of(alice)  # /api/auth/profile 會先結算期滿的回饋
    assert after == pytest.approx(before + 25)
    listed = client.get("/api/cashback", headers=bearer(alice)).json()
    assert listed["pending_days"] == 7
    assert next(o for o in listed["orders"] if o["id"] == order["id"])["status"] == "confirmed"


def test_users_can_no_longer_confirm_or_set_amount(alice):
    order = track(alice)
    for action in ("simulate-purchase", "simulate-confirm", "simulate-cancel"):
        res = client.post(f"/api/cashback/{order['id']}/{action}", headers=bearer(alice), json={"amount": 500})
        assert res.status_code in (404, 405), action
    assert db_row(order["id"])["status"] == "tracked"


def test_receipt_image_is_not_stored(alice, gemini):
    gemini.result = gemini_receipt()
    image = image_data_url()
    order = upload(alice, track(alice)["id"], image=image)["order"]
    row = db_row(order["id"])
    raw = base64.b64decode(image.split(",", 1)[1])
    assert row["receipt_hash"] == hashlib.sha256(raw).hexdigest()
    encoded = image.split(",", 1)[1]
    assert not any(isinstance(v, (str, bytes)) and encoded in str(v) for v in row.values())


# ---------------------------------------------------------------- 伺服器端檢查

def test_pharmacy_must_match_tracked_click(alice, gemini):
    gemini.result = gemini_receipt(store_name="杏一醫療用品股份有限公司")
    order = track(alice, pharmacy="大樹藥局")
    res = upload(alice, order["id"])
    assert not res["success"] and not res["retake"]
    assert "杏一" in res["message"]
    assert db_row(order["id"])["status"] == "tracked"


def test_purchase_must_be_after_click(alice, gemini):
    gemini.result = gemini_receipt(purchase_time=(datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M"))
    order = track(alice)
    res = upload(alice, order["id"])
    assert not res["success"] and "早於" in res["message"]
    assert db_row(order["id"])["status"] == "tracked"


def test_same_day_receipt_without_time_asks_retake(alice, gemini):
    gemini.result = gemini_receipt(purchase_time=datetime.now().strftime("%Y-%m-%d"))
    res = upload(alice, track(alice)["id"])
    assert not res["success"] and res["retake"]
    assert "時間" in res["message"]


def test_future_purchase_time_rejected(alice, gemini):
    gemini.result = gemini_receipt(purchase_time=(datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M"))
    res = upload(alice, track(alice)["id"])
    assert not res["success"]


def test_same_image_cannot_be_used_twice(alice, gemini):
    image = image_data_url()
    gemini.result = gemini_receipt()
    assert upload(alice, track(alice)["id"], image=image)["success"]

    gemini.result = gemini_receipt()  # 換一個訂單號碼也一樣擋下
    second = track(alice)
    res = upload(alice, second["id"], image=image)
    assert not res["success"] and "已經登錄過" in res["message"]
    assert len(gemini.calls) == 1  # 重複的圖片不送 Gemini
    assert db_row(second["id"])["status"] == "tracked"


def test_same_order_number_cannot_be_used_twice(alice, gemini):
    gemini.result = gemini_receipt(order_number="ZX-2026 1015")
    assert upload(alice, track(alice)["id"])["success"]

    gemini.result = gemini_receipt(order_number="zx20261015")  # 同一張發票，寫法不同
    second = track(alice)
    res = upload(alice, second["id"])
    assert not res["success"] and "已經登錄過" in res["message"]
    assert db_row(second["id"])["status"] == "tracked"


def test_order_number_unique_across_members(alice, bob, gemini):
    gemini.result = gemini_receipt(order_number="SHARED-0001")
    assert upload(alice, track(alice)["id"])["success"]
    gemini.result = gemini_receipt(order_number="SHARED-0001")
    res = upload(bob, track(bob)["id"])
    assert not res["success"] and "已經登錄過" in res["message"]


def test_amount_over_cap_rejected(alice, gemini):
    gemini.result = gemini_receipt(total_amount=database.CASHBACK_MAX_AMOUNT + 1)
    order = track(alice)
    res = upload(alice, order["id"])
    assert not res["success"] and "上限" in res["message"]
    assert db_row(order["id"])["status"] == "tracked"


def test_low_confidence_asks_retake_then_retry_succeeds(alice, gemini):
    order = track(alice)
    gemini.result = gemini_receipt(confidence=0.4)
    res = upload(alice, order["id"])
    assert not res["success"] and res["retake"]
    assert db_row(order["id"])["status"] == "tracked"

    gemini.result = gemini_receipt(confidence=0.92)
    assert upload(alice, order["id"])["success"]


@pytest.mark.parametrize("overrides", [
    {"is_receipt": False},
    {"total_amount": 0},
    {"order_number": ""},
    {"purchase_time": "看不清楚"},
    {"store_name": ""},
])
def test_unreadable_receipt_asks_retake(alice, gemini, overrides):
    gemini.result = gemini_receipt(**overrides)
    order = track(alice)
    res = upload(alice, order["id"])
    assert not res["success"] and res["retake"]
    assert db_row(order["id"])["status"] == "tracked"


def test_gemini_failure_keeps_order_tracked(alice, gemini):
    gemini.error = receipt_scanner.ReceiptScanError("boom")
    order = track(alice)
    res = upload(alice, order["id"])
    assert not res["success"] and "暫時無法使用" in res["message"]
    assert db_row(order["id"])["status"] == "tracked"
    assert db_row(order["id"])["receipt_hash"] is None  # 同一張圖之後還能再上傳


def test_missing_gemini_key_is_reported_as_unavailable(alice):
    res = upload(alice, track(alice)["id"])  # 未替換 call_gemini，也沒有 GEMINI_API_KEY
    assert not res["success"] and "暫時無法使用" in res["message"]


@pytest.mark.parametrize("image", [
    "",
    "not-a-data-url",
    "data:text/plain;base64,aGVsbG8=",
    "data:image/png;base64,***",
])
def test_invalid_image_rejected_before_gemini(alice, gemini, image):
    res = upload(alice, track(alice)["id"], image=image or "")
    assert not res["success"] and res["retake"]
    assert gemini.calls == []


def test_receipt_upload_only_for_own_tracked_click(alice, bob, gemini):
    gemini.result = gemini_receipt()
    order = track(alice)
    res = upload(bob, order["id"])
    assert not res["success"] and "找不到" in res["message"]
    assert gemini.calls == []

    assert upload(alice, order["id"])["success"]
    again = upload(alice, order["id"])
    assert not again["success"] and "待入帳" in again["message"]


def test_cancel_only_before_receipt(alice, bob, gemini):
    order = track(alice)
    assert not client.post(f"/api/cashback/{order['id']}/cancel", headers=bearer(bob), json={}).json()["success"]
    assert client.post(f"/api/cashback/{order['id']}/cancel", headers=bearer(alice), json={}).json()["success"]
    assert db_row(order["id"])["status"] == "rejected"

    gemini.result = gemini_receipt()
    pending = upload(alice, track(alice)["id"])["order"]
    res = client.post(f"/api/cashback/{pending['id']}/cancel", headers=bearer(alice), json={}).json()
    assert not res["success"]
    assert db_row(pending["id"])["status"] == "pending"


def test_receipt_endpoints_require_member_token():
    assert client.post("/api/cashback/cb_x/receipt", json={"image": image_data_url()}).status_code == 401
    assert client.post("/api/cashback/cb_x/cancel", json={}).status_code == 401


# ---------------------------------------------------------------- 辨識模組

def test_gemini_request_and_response_parsing(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            receipt = {"is_receipt": True, "document_type": "receipt", "store_name": "丁丁藥局 板橋店",
                       "order_number": "No. 0012-3456", "purchase_time": "2026/10/15 14:05",
                       "total_amount": "1,368", "confidence": 0.88}
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(receipt, ensure_ascii=False)}]}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json)
        return FakeResponse()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(receipt_scanner.requests, "post", fake_post)
    scan = receipt_scanner.scan_receipt(b"jpeg-bytes", "image/jpeg")

    assert receipt_scanner.DEFAULT_MODEL in captured["url"]
    assert "test-key" not in captured["url"]  # 金鑰放在標頭，不放網址
    assert captured["headers"]["x-goog-api-key"] == "test-key"
    image_part = captured["json"]["contents"][0]["parts"][1]["inline_data"]
    assert image_part == {"mime_type": "image/jpeg", "data": base64.b64encode(b"jpeg-bytes").decode()}
    assert captured["json"]["generationConfig"]["responseMimeType"] == "application/json"

    assert scan["order_number"] == "NO00123456"
    assert scan["total_amount"] == 1368
    assert scan["purchase_time"] == datetime(2026, 10, 15, 14, 5) and scan["has_time"]
    assert scan["confidence"] == pytest.approx(0.88)


def test_gemini_http_error_raises(monkeypatch):
    class Bad:
        status_code = 429
        text = "quota"

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(receipt_scanner.requests, "post", lambda *a, **k: Bad())
    with pytest.raises(receipt_scanner.ReceiptScanError):
        receipt_scanner.scan_receipt(b"x", "image/png")


@pytest.mark.parametrize("expected,store,ok", [
    ("大樹藥局", "大樹醫藥股份有限公司 新莊中正門市", True),
    ("大樹藥局", "杏一醫療用品", False),
    ("杏一醫療", "杏一醫療用品股份有限公司", True),
    ("啄木鳥藥局", "啄木鳥藥局 線上商城", True),
    ("丁丁藥局", "丁丁連鎖藥妝", True),
    ("丁丁藥局", "", False),
])
def test_pharmacy_matching(expected, store, ok):
    assert receipt_scanner.pharmacy_matches(expected, store) is ok


def test_privacy_policy_mentions_gemini():
    html = client.get("/privacy").text
    assert "Gemini" in html and "收據" in html


def test_health_reports_gemini_key_without_revealing_it(monkeypatch):
    assert client.get("/api/health").json()["gemini_api_key"] == "missing"
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-gemini-key")
    res = client.get("/api/health")
    assert res.json()["gemini_api_key"] == "configured"
    assert "test-only-gemini-key" not in res.text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
