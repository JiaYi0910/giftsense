"""
購物回饋的管理：
- 管理員在 7 天待入帳期間可以檢視所有會員的待入帳回饋，並填寫原因駁回（不給點數）

執行（在 backend 資料夾）：
    python -m pytest tests/test_cashback_admin.py -q
    或 python tests/test_cashback_admin.py

測試使用 caregift.db 的暫存複本，不會改到 repo 內的資料庫。
"""
import itertools
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP_DIR = tempfile.mkdtemp(prefix="giftsense_cashback_admin_test_")
TEST_DB = os.path.join(_TMP_DIR, "caregift.db")
shutil.copy(os.path.join(BACKEND, "caregift.db"), TEST_DB)

ADMIN_PASSWORD = "admin-test-password"  # 與 test_member_auth.py 相同，同一個 pytest 行程裡才不會互相覆蓋
os.environ["CAREGIFT_DB_PATH"] = TEST_DB
os.environ["AUTH_TOKEN_SECRET"] = "test-only-auth-secret"
os.environ["ADMIN_PASSWORD"] = ADMIN_PASSWORD
for _key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "ADMIN_TOKEN_SECRET"):
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

client = TestClient(main.app)  # 不用 with：不跑 startup 的藥局爬蟲預熱與自動入帳排程

_unique = itertools.count(1)
_RUN = datetime.now().strftime("%H%M%S%f")
TIME_FMT = "%Y-%m-%d %H:%M:%S"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def new_member():
    """每次註冊新會員：每日確認購買的筆數各自從 0 開始，測試之間不互相影響"""
    account = f"cb_admin_{_RUN}_{next(_unique)}@example.test"
    data = client.post("/api/auth/register", json={
        "account": account, "password": f"pw-{account}", "name": account,
    }).json()
    assert data["success"] and data["user_token"]
    return account, data["user_token"]


@pytest.fixture(scope="module")
def admin():
    data = client.post("/api/auth/login", json={"account": "admin", "password": ADMIN_PASSWORD}).json()
    assert data["success"] and data["admin_token"]
    return {**bearer(data["user_token"]), "X-Admin-Token": data["admin_token"]}


PRODUCT = "【HAC 永信】晶亮葉黃膠囊 (120粒/瓶)"  # 大樹藥局查價 $1,800，回饋 5% = 90 點
PRICE, POINTS = 1800, 90


def track(token):
    res = client.post("/api/pharmacy/referral-click", headers=bearer(token), json={
        "product_name": PRODUCT, "pharmacy": "大樹藥局", "price": 1, "official_url": "https://example.test",
    }).json()
    assert res["success"], res["message"]
    return res["cashback"]


def confirm(token, order_id):
    res = client.post(f"/api/cashback/{order_id}/purchase", headers=bearer(token), json={})
    assert res.status_code == 200
    return res.json()


def pending_order(token):
    res = confirm(token, track(token)["id"])
    assert res["success"], res["message"]
    return res["order"]


def db_row(order_id):
    conn = database.get_db()
    row = conn.execute("SELECT * FROM cashback_orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return dict(row)


def set_credit_after(order_id, value):
    conn = database.get_db()
    conn.execute("UPDATE cashback_orders SET credit_after = ? WHERE id = ?", (value, order_id))
    conn.commit()
    conn.close()


def points_of(token):
    return client.get("/api/auth/profile", headers=bearer(token)).json()["profile"]["points"]


def admin_pending(admin):
    res = client.get("/api/admin/cashback/pending", headers=admin)
    assert res.status_code == 200
    return res.json()


def reject(admin, order_id, reason="會員已退貨"):
    res = client.post(f"/api/admin/cashback/{order_id}/reject", headers=admin, json={"reason": reason})
    assert res.status_code == 200
    return res.json()


# ---------------------------------------------------------------- 管理員：待入帳清單

def test_admin_sees_pending_cashback_of_all_members(admin):
    acc_a, tok_a = new_member()
    acc_b, tok_b = new_member()
    first = pending_order(tok_a)
    second = pending_order(tok_b)
    set_credit_after(first["id"], (datetime.now() + timedelta(days=2)).strftime(TIME_FMT))  # 比 second 早入帳
    tracked = track(tok_a)

    data = admin_pending(admin)
    assert data["success"] and data["pending_days"] == 7
    ids = [o["id"] for o in data["orders"]]
    assert first["id"] in ids and second["id"] in ids
    assert ids.index(first["id"]) < ids.index(second["id"])  # 最快入帳的排前面
    assert tracked["id"] not in ids  # 還沒確認購買的不在清單
    listed = next(o for o in data["orders"] if o["id"] == second["id"])
    assert listed["account"] == acc_b and listed["order_amount"] == PRICE and listed["points"] == POINTS
    assert listed["product_name"] == PRODUCT and listed["credit_after"]
    assert "receipt_hash" not in listed and "rejected_by" not in listed
    assert data["summary"]["count"] == len(data["orders"])
    assert data["summary"]["points"] == sum(o["points"] for o in data["orders"])


def test_pending_list_credits_due_cashback_first(admin):
    _, token = new_member()
    order = pending_order(token)
    set_credit_after(order["id"], (datetime.now() - timedelta(minutes=1)).strftime(TIME_FMT))

    ids = [o["id"] for o in admin_pending(admin)["orders"]]
    assert order["id"] not in ids
    assert db_row(order["id"])["status"] == "confirmed"


def test_legacy_pending_without_credit_time_listed_last_and_rejectable(admin):
    account, token = new_member()
    legacy = track(token)
    conn = database.get_db()  # 舊版模擬的待確認紀錄：沒有 credit_after，不會自動入帳
    conn.execute("UPDATE cashback_orders SET status = 'pending', order_amount = 800, points = 40 WHERE id = ?",
                 (legacy["id"],))
    conn.commit()
    conn.close()
    pending_order(token)

    ids = [o["id"] for o in admin_pending(admin)["orders"]]
    assert ids[-1] == legacy["id"]
    res = reject(admin, legacy["id"], "舊版模擬紀錄")
    assert res["success"], res["message"]
    assert db_row(legacy["id"])["status"] == "rejected"


# ---------------------------------------------------------------- 管理員：駁回

def test_reject_keeps_points_from_being_credited(admin):
    account, token = new_member()
    order = pending_order(token)
    before = points_of(token)

    res = reject(admin, order["id"], "  會員已在藥局辦理退貨  ")
    assert res["success"], res["message"]
    assert res["order"]["status"] == "rejected"
    row = db_row(order["id"])
    assert row["status"] == "rejected" and row["settled_at"]
    assert row["reject_reason"] == "會員已在藥局辦理退貨"
    assert row["rejected_by"] == "admin"

    # 原本的入帳時間到了也不會入帳
    credit_after = datetime.strptime(order["credit_after"], TIME_FMT)
    assert database.settle_due_cashback(account, now=credit_after + timedelta(days=1)) == 0
    assert points_of(token) == pytest.approx(before)
    ledger = client.get("/api/points", headers=bearer(token)).json()["ledger"]
    assert not any("購物回饋" in item["title"] for item in ledger)

    # 會員看得到結果與原因，看不到是哪位管理員
    mine = client.get("/api/cashback", headers=bearer(token)).json()
    listed = next(o for o in mine["orders"] if o["id"] == order["id"])
    assert listed["status_text"] == "未通過審核"
    assert listed["reject_reason"] == "會員已在藥局辦理退貨"
    assert "rejected_by" not in listed
    assert mine["summary"]["pending_points"] == 0

    assert order["id"] not in [o["id"] for o in admin_pending(admin)["orders"]]


def test_member_cancel_still_shows_cancelled():
    _, token = new_member()
    order = track(token)
    assert client.post(f"/api/cashback/{order['id']}/cancel", headers=bearer(token), json={}).json()["success"]
    listed = client.get("/api/cashback", headers=bearer(token)).json()["orders"][0]
    assert listed["status_text"] == "已取消"


@pytest.mark.parametrize("reason,expected", [
    ("", "請填寫駁回原因"),
    ("   ", "請填寫駁回原因"),
    ("退" * (database.REJECT_REASON_MAX_LENGTH + 1), "字以內"),
])
def test_reject_requires_short_reason(admin, reason, expected):
    _, token = new_member()
    order = pending_order(token)
    res = reject(admin, order["id"], reason)
    assert not res["success"] and expected in res["message"]
    assert db_row(order["id"])["status"] == "pending"


def test_reject_only_pending_orders(admin):
    _, token = new_member()
    tracked = track(token)
    res = reject(admin, tracked["id"])
    assert not res["success"] and "追蹤中" in res["message"]
    assert db_row(tracked["id"])["status"] == "tracked"

    order = pending_order(token)
    assert reject(admin, order["id"])["success"]
    again = reject(admin, order["id"], "再駁回一次")
    assert not again["success"] and "未通過審核" in again["message"]
    assert db_row(order["id"])["reject_reason"] == "會員已退貨"

    missing = reject(admin, "CB_NOT_EXIST")
    assert not missing["success"] and "找不到" in missing["message"]


def test_cannot_reject_after_pending_window(admin):
    _, token = new_member()
    order = pending_order(token)
    before = points_of(token)
    set_credit_after(order["id"], (datetime.now() - timedelta(minutes=1)).strftime(TIME_FMT))

    res = reject(admin, order["id"])
    assert not res["success"] and "已入帳" in res["message"]
    assert db_row(order["id"])["status"] == "confirmed"
    assert points_of(token) == pytest.approx(before + POINTS)


def test_rejected_purchase_cannot_be_confirmed_again_same_day(admin):
    _, token = new_member()
    first = pending_order(token)
    assert reject(admin, first["id"])["success"]

    # 被駁回的購買仍算今天的筆數：同一商品同一藥局不能馬上再確認一次換點數
    res = confirm(token, track(token)["id"])
    assert not res["success"] and "每天只能回饋 1 次" in res["message"]


def test_admin_cashback_endpoints_reject_members(admin):
    _, token = new_member()
    for method, path, body in (
        ("GET", "/api/admin/cashback/pending", None),
        ("POST", "/api/admin/cashback/CB_X/reject", {"reason": "x"}),
    ):
        assert client.request(method, path, json=body).status_code == 401
        assert client.request(method, path, json=body, headers=bearer(token)).status_code == 401
        assert client.request(method, path, json=body, headers={"X-Admin-Token": token}).status_code == 401
        # 管理員的「會員」通行證也不能當管理員通行證
        member_token = admin["Authorization"].split(" ", 1)[1]
        assert client.request(method, path, json=body, headers={"X-Admin-Token": member_token}).status_code == 401
