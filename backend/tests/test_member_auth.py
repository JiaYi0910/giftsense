"""
會員通行證驗證：會員 API 一律以登入通行證判斷身分，前端送來的 account 只用來核對。

執行（在 backend 資料夾）：
    python -m pytest tests/test_member_auth.py -q
    或 python tests/test_member_auth.py

測試使用 caregift.db 的暫存複本，不會改到 repo 內的資料庫，也不連線 Turso / LINE / Gemini。
"""
import base64
import hashlib
import hmac
import json
import os
import shutil
import sys
import tempfile

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP_DIR = tempfile.mkdtemp(prefix="giftsense_auth_test_")
TEST_DB = os.path.join(_TMP_DIR, "caregift.db")
shutil.copy(os.path.join(BACKEND, "caregift.db"), TEST_DB)

ADMIN_PASSWORD = "admin-test-password"
os.environ["CAREGIFT_DB_PATH"] = TEST_DB
os.environ["AUTH_TOKEN_SECRET"] = "test-only-auth-secret"
os.environ["ADMIN_PASSWORD"] = ADMIN_PASSWORD
for _key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "GEMINI_API_KEY", "ADMIN_TOKEN_SECRET"):
    os.environ.pop(_key, None)

os.chdir(BACKEND)  # main.py 以相對路徑掛載 static/uploads
sys.path.insert(0, BACKEND)

import database  # noqa: E402

if database.DB_PATH != TEST_DB:  # 同一個 pytest 行程裡已有其他測試先載入 database
    database.DB_PATH = TEST_DB
    database.init_db()
assert not database.USE_TURSO, "測試不可連線 Turso"

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app)  # 不用 with：不跑 startup 的藥局爬蟲預熱

ALICE = "alice@example.test"
BOB = "bob@example.test"


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
def admin():
    data = client.post("/api/auth/login", json={"account": "admin", "password": ADMIN_PASSWORD}).json()
    assert data["success"]
    return {"user_token": data["user_token"], "admin_token": data["admin_token"]}


# ---------------------------------------------------------------- 核發通行證

def test_password_login_issues_member_token(alice):
    data = client.post("/api/auth/login", json={"account": ALICE, "password": f"pw-{ALICE}"}).json()
    assert data["success"]
    assert "admin_token" not in data
    profile = client.get("/api/auth/profile", headers=bearer(data["user_token"])).json()["profile"]
    assert profile["account"] == ALICE


def test_x_user_token_header_also_accepted(alice):
    res = client.get("/api/auth/profile", headers={"X-User-Token": alice})
    assert res.status_code == 200 and res.json()["profile"]["account"] == ALICE


def test_admin_login_issues_member_and_admin_tokens(admin):
    res = client.get("/api/auth/profile", headers=bearer(admin["user_token"]))
    assert res.status_code == 200 and res.json()["profile"]["role"] == "admin"


def test_social_login_issues_member_token(monkeypatch):
    monkeypatch.setattr(main, "verify_social_token", lambda provider, id_token, access_token: {
        "provider": "google", "social_id": "g-auth-test", "email": "carol@example.test",
        "email_verified": True, "name": "Carol",
    })
    data = client.post("/api/auth/social", json={"provider": "google", "id_token": "fake"}).json()
    assert data["success"] and data["user_token"]
    profile = client.get("/api/auth/profile", headers=bearer(data["user_token"])).json()["profile"]
    assert profile["account"] == data["user"]["account"]


def test_failed_login_issues_no_token():
    data = client.post("/api/auth/login", json={"account": ALICE, "password": "wrong"}).json()
    assert not data["success"] and "user_token" not in data


# ---------------------------------------------------------------- 沒有／無效的通行證

MEMBER_ENDPOINTS = [
    ("GET", "/api/auth/profile?account=" + ALICE, None),
    ("GET", "/api/recipients?account=" + ALICE, None),
    ("POST", "/api/recipients", {"name": "奶奶", "condition": "高血壓", "user_account": ALICE}),
    ("PUT", "/api/recipients/rec_x", {"name": "改名"}),
    ("DELETE", "/api/recipients/rec_x", None),
    ("GET", "/api/recipients/rec_x/chips", None),
    ("POST", "/api/recipients/rec_x/generate-chips", {}),
    ("POST", "/api/recipients/rec_x/line-bind", None),
    ("DELETE", "/api/recipients/rec_x/line-bind", None),
    ("POST", "/api/guard/query", {"query": "魚油", "account": ALICE}),
    ("GET", "/api/guard/quota?account=" + ALICE, None),
    ("POST", "/api/guard/redeem", {"account": ALICE}),
    ("POST", "/api/pharmacy/referral-click", {"product_name": "魚油", "pharmacy": "大樹藥局", "price": 500, "official_url": "https://example.test", "account": ALICE}),
    ("GET", "/api/cashback?account=" + ALICE, None),
    ("POST", "/api/cashback/cb_x/simulate-purchase", {"account": ALICE, "amount": 100}),
    ("POST", "/api/cashback/cb_x/simulate-confirm", {"account": ALICE}),
    ("POST", "/api/cashback/cb_x/simulate-cancel", {"account": ALICE}),
    ("GET", "/api/orders", None),
    ("POST", "/api/orders", {"order_id": "o1", "items": [], "total": "$1", "recipient": "奶奶"}),
    ("POST", "/api/orders/o1/cancel", None),
    ("GET", "/api/points?account=" + ALICE, None),
    ("GET", "/api/messages?elder=奶奶&account=" + ALICE, None),
    ("POST", "/api/messages", {"sender": ALICE, "elder": "奶奶", "content": "hi"}),
    ("GET", "/api/user/profile?account=" + ALICE, None),
    ("PUT", "/api/user/profile", {"account": ALICE, "name": "駭客"}),
    ("POST", "/api/user/checkin", {"account": ALICE}),
    ("POST", "/api/user/avatar", {"account": ALICE, "image": ""}),
    ("POST", "/api/rewards/claim", {"account": ALICE, "action": "care_card"}),
]


def _call(method, path, body=None, headers=None):
    return client.request(method, path, json=body, headers=headers or {})


@pytest.mark.parametrize("method,path,body", MEMBER_ENDPOINTS)
def test_member_endpoint_rejects_missing_token(method, path, body):
    assert _call(method, path, body).status_code == 401


@pytest.mark.parametrize("method,path,body", MEMBER_ENDPOINTS)
def test_member_endpoint_rejects_garbage_token(method, path, body):
    assert _call(method, path, body, bearer("not-a-token")).status_code == 401


def test_expired_token_rejected():
    expired = main._sign_token("member", ALICE, -60)
    assert client.get("/api/recipients", headers=bearer(expired)).status_code == 401


def test_tampered_token_rejected(alice):
    # 把通行證上的帳號換成 Bob，但沿用 Alice 的簽章
    encoded, sig = alice.split(".", 1)
    payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    forged_payload = BOB + "|" + payload.rsplit("|", 1)[1]
    forged = base64.urlsafe_b64encode(forged_payload.encode()).decode().rstrip("=") + "." + sig
    assert client.get("/api/recipients", headers=bearer(forged)).status_code == 401


def test_token_signed_with_other_secret_rejected():
    payload = f"{ALICE}|9999999999"
    key = hashlib.sha256(b"giftsense-member-token|some-other-secret").digest()
    sig = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=") + "." + sig
    assert client.get("/api/recipients", headers=bearer(token)).status_code == 401


def test_admin_token_cannot_be_used_as_member_token(admin):
    assert client.get("/api/recipients", headers=bearer(admin["admin_token"])).status_code == 401


# ---------------------------------------------------------------- 冒用別人的帳號

@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/auth/profile?account=" + BOB, None),
    ("GET", "/api/recipients?account=" + BOB, None),
    ("POST", "/api/recipients", {"name": "奶奶", "condition": "高血壓", "user_account": BOB}),
    ("GET", "/api/guard/quota?account=" + BOB, None),
    ("POST", "/api/guard/query", {"query": "魚油", "account": BOB}),
    ("POST", "/api/guard/redeem", {"account": BOB}),
    ("GET", "/api/cashback?account=" + BOB, None),
    ("GET", "/api/points?account=" + BOB, None),
    ("GET", "/api/messages?elder=奶奶&account=" + BOB, None),
    ("POST", "/api/messages", {"sender": BOB, "elder": "奶奶", "content": "冒名"}),
    ("PUT", "/api/user/profile", {"account": BOB, "name": "被改名"}),
    ("POST", "/api/user/checkin", {"account": BOB}),
    ("POST", "/api/user/avatar", {"account": BOB, "image": ""}),
    ("POST", "/api/rewards/claim", {"account": BOB, "action": "care_card"}),
])
def test_token_for_different_account_forbidden(alice, bob, method, path, body):
    assert _call(method, path, body, bearer(alice)).status_code == 403


def test_bob_profile_untouched_after_alice_attempts(bob):
    assert client.get("/api/auth/profile", headers=bearer(bob)).json()["profile"]["name"] == BOB


# ---------------------------------------------------------------- 資料隔離

def test_recipients_are_isolated(alice, bob):
    created = client.post("/api/recipients", headers=bearer(alice), json={
        "name": "阿嬤", "condition": "心房顫動，服用 Warfarin", "phone": "0912000000",
    }).json()
    assert created["success"]
    rec = created["recipient"]
    assert rec["user_account"] == ALICE
    rec_id = rec["id"]

    alice_list = client.get("/api/recipients", headers=bearer(alice)).json()["recipients"]
    assert rec_id in [r["id"] for r in alice_list]
    bob_list = client.get("/api/recipients", headers=bearer(bob)).json()["recipients"]
    assert rec_id not in [r["id"] for r in bob_list]

    for method, path, body in [
        ("PUT", f"/api/recipients/{rec_id}", {"name": "被改名"}),
        ("GET", f"/api/recipients/{rec_id}/chips", None),
        ("POST", f"/api/recipients/{rec_id}/generate-chips", {}),
        ("POST", f"/api/recipients/{rec_id}/line-bind", None),
        ("DELETE", f"/api/recipients/{rec_id}/line-bind", None),
        ("DELETE", f"/api/recipients/{rec_id}", None),
    ]:
        assert _call(method, path, body, bearer(bob)).status_code == 404, (method, path)

    still_there = database.get_recipient_by_id(rec_id)
    assert still_there and still_there["name"] == "阿嬤"

    assert client.get(f"/api/recipients/{rec_id}/chips", headers=bearer(alice)).status_code == 200
    edited = client.put(f"/api/recipients/{rec_id}", headers=bearer(alice), json={"name": "外婆"})
    assert edited.status_code == 200 and edited.json()["recipient"]["name"] == "外婆"
    assert client.delete(f"/api/recipients/{rec_id}", headers=bearer(alice)).status_code == 200
    assert database.get_recipient_by_id(rec_id) is None


def test_messages_are_isolated(alice, bob):
    sent = client.post("/api/messages", headers=bearer(alice), json={"elder": "外公", "content": "記得吃藥"})
    assert sent.status_code == 200
    msg = sent.json()["message"]
    assert msg["owner_account"] == ALICE

    alice_msgs = client.get("/api/messages", headers=bearer(alice), params={"elder": "外公"}).json()["messages"]
    assert msg["id"] in [m["id"] for m in alice_msgs]
    bob_msgs = client.get("/api/messages", headers=bearer(bob), params={"elder": "外公"}).json()["messages"]
    assert msg["id"] not in [m["id"] for m in bob_msgs]


def test_points_and_profile_follow_token(alice, bob):
    ledger = client.get("/api/points", headers=bearer(alice)).json()["ledger"]
    assert ledger and all(ALICE in (row.get("account"), row.get("user_account")) for row in ledger)

    res = client.put("/api/user/profile", headers=bearer(alice), json={"name": "Alice 新名字"})
    assert res.json()["success"]
    assert client.get("/api/user/profile", headers=bearer(alice)).json()["profile"]["name"] == "Alice 新名字"
    assert client.get("/api/user/profile", headers=bearer(bob)).json()["profile"]["name"] == BOB


def test_cashback_orders_are_isolated(alice, bob):
    click = client.post("/api/pharmacy/referral-click", headers=bearer(alice), json={
        "product_name": "魚油", "pharmacy": "大樹藥局", "price": 500, "official_url": "https://example.test",
    }).json()
    assert click["success"]
    order_id = click["cashback"]["id"]

    hijack = client.post(f"/api/cashback/{order_id}/simulate-purchase", headers=bearer(bob), json={"amount": 9999}).json()
    assert not hijack["success"]
    bob_orders = client.get("/api/cashback", headers=bearer(bob)).json()["orders"]
    assert order_id not in [o["id"] for o in bob_orders]
    alice_orders = client.get("/api/cashback", headers=bearer(alice)).json()["orders"]
    assert order_id in [o["id"] for o in alice_orders]


def test_orders_cancel_requires_owner(alice, bob):
    assert client.post("/api/orders", headers=bearer(alice), json={
        "order_id": "ord_auth_test", "items": [{"name": "魚油", "price": 500, "qty": 1}], "total": "$500", "recipient": "阿嬤",
    }).status_code == 200
    assert "ord_auth_test" not in [o["id"] for o in client.get("/api/orders", headers=bearer(bob)).json()["orders"]]
    assert client.post("/api/orders/ord_auth_test/cancel", headers=bearer(bob)).status_code == 404
    assert client.post("/api/orders/ord_auth_test/cancel", headers=bearer(alice)).status_code == 200


def test_guard_quota_counts_token_account(alice, admin):
    before = client.get("/api/guard/quota", headers=bearer(alice)).json()["quota"]
    assert before["limit"] == main.AI_GUARD_DAILY_LIMIT
    res = client.post("/api/guard/query", headers=bearer(alice), json={"query": "魚油", "elder_condition": "高血壓"})
    assert res.status_code == 200
    after = client.get("/api/guard/quota", headers=bearer(alice)).json()["quota"]
    assert after["remaining"] == before["remaining"] - 1

    admin_quota = client.get("/api/guard/quota", headers={
        **bearer(admin["user_token"]), "X-Admin-Token": admin["admin_token"],
    }).json()["quota"]
    assert admin_quota["unlimited"] is True


# ---------------------------------------------------------------- 管理後台

ADMIN_ENDPOINTS = [
    ("GET", "/api/db/export", None),
    ("GET", "/api/db/stats", None),
    ("GET", "/api/config/rag", None),
    ("POST", "/api/config/rag", {"topK": 3}),
    ("POST", "/api/knowledge", {"id": "lit_x", "title": "x"}),
    ("POST", "/api/knowledge/sync", {"literatures": []}),
    ("POST", "/api/knowledge/reset", None),
    ("DELETE", "/api/knowledge/lit_x", None),
    ("POST", "/api/points", {"account": BOB, "amount": 999, "title": "自己加點"}),
    ("POST", "/api/points/add", {"account": BOB, "amount": 999, "title": "自己加點"}),
    ("POST", "/api/pharmacy/auto-order", {"product_name": "魚油", "price": 500}),
]


@pytest.mark.parametrize("method,path,body", ADMIN_ENDPOINTS)
def test_admin_endpoint_rejects_members(bob, admin, method, path, body):
    assert _call(method, path, body).status_code == 401
    assert _call(method, path, body, bearer(bob)).status_code == 401
    assert _call(method, path, body, {"X-Admin-Token": bob}).status_code == 401
    # 管理員的「會員」通行證也不能當管理員通行證
    assert _call(method, path, body, {"X-Admin-Token": admin["user_token"]}).status_code == 401


def test_admin_endpoints_work_with_admin_token(admin):
    headers = {**bearer(admin["user_token"]), "X-Admin-Token": admin["admin_token"]}
    for path in ("/api/db/stats", "/api/config/rag", "/api/db/export"):
        res = client.get(path, headers=headers)
        assert res.status_code == 200, path


def test_admin_token_of_demoted_account_rejected(admin):
    # 通行證簽章正確，但帳號已不是管理員 → 拒絕
    token = main._sign_token("admin", ALICE, 3600)
    assert client.get("/api/db/stats", headers={"X-Admin-Token": token}).status_code == 401


# ---------------------------------------------------------------- 公開端點維持不用登入

def test_public_endpoints_stay_open(monkeypatch):
    monkeypatch.setattr(main, "get_live_weather", lambda city, cwa_api_key=None: {"city": city})
    health = client.get("/api/health")
    assert health.status_code == 200 and health.json()["auth_token_secret"] == "configured"
    for path in ("/privacy", "/guide", "/api/weather?city=臺北市", "/api/knowledge",
                 "/api/pharmacy/recommended?condition=高血壓", "/api/chips/suggested?condition=高血壓"):
        assert client.get(path).status_code == 200, path


def test_line_webhook_uses_signature_not_member_token():
    body = json.dumps({"events": []}).encode()
    assert client.post("/api/line/webhook", content=body, headers={"X-Line-Signature": "bad"}).status_code == 400
    sig = base64.b64encode(hmac.new(main.LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()).decode()
    res = client.post("/api/line/webhook", content=body, headers={"X-Line-Signature": sig})
    assert res.status_code == 200


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
