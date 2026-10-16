"""
購物回饋（模擬流程）：前往購買時由伺服器依商品查價鎖定金額，確認購買後待入帳 7 天，期滿自動入帳。
使用者無法輸入或修改金額；每天最多確認 3 筆，同一商品在同一藥局每天 1 筆。

執行（在 backend 資料夾）：
    python -m pytest tests/test_cashback_purchase.py -q
    或 python tests/test_cashback_purchase.py

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
_TMP_DIR = tempfile.mkdtemp(prefix="giftsense_cashback_purchase_test_")
TEST_DB = os.path.join(_TMP_DIR, "caregift.db")
shutil.copy(os.path.join(BACKEND, "caregift.db"), TEST_DB)

os.environ["CAREGIFT_DB_PATH"] = TEST_DB
os.environ["AUTH_TOKEN_SECRET"] = "test-only-auth-secret"
for _key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"):
    os.environ.pop(_key, None)
# 不碰開發用的資料庫（DATABASE_URL）；要在 SQL Server 上測試時另外設定 TEST_DATABASE_URL，指向空的測試資料庫
os.environ.pop("DATABASE_URL", None)
if os.getenv("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

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

# 商品資料庫（product_catalog.py）中的實際查價
LUTEIN = "【HAC 永信】晶亮葉黃膠囊 (120粒/瓶)"       # 大樹 $1,800、杏一 $1,760
FISH_OIL = "【歐3加福】精萃濃縮 EPA 魚油 (60顆/瓶)"  # 大樹 $1,680
VIT_C = "【善存】維他命 C 甜嚼錠 500mg (60錠/瓶)"    # 大樹 $279
Q10 = "【愛司盟】輔酵素 Q10 複方膠囊 (60粒/瓶)"       # 大樹 $748


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def new_member():
    account = f"cb_buy_{_RUN}_{next(_unique)}@example.test"
    data = client.post("/api/auth/register", json={
        "account": account, "password": f"pw-{account}", "name": account,
    }).json()
    assert data["success"] and data["user_token"]
    return account, data["user_token"]


def click(token, product=LUTEIN, pharmacy="大樹藥局", price=1, **extra):
    return client.post("/api/pharmacy/referral-click", headers=bearer(token), json={
        "product_name": product, "pharmacy": pharmacy, "price": price,
        "official_url": "https://example.test", **extra,
    }).json()


def track(token, product=LUTEIN, pharmacy="大樹藥局"):
    res = click(token, product, pharmacy)
    assert res["success"], res["message"]
    return res["cashback"]


def confirm(token, order_id, **body):
    res = client.post(f"/api/cashback/{order_id}/purchase", headers=bearer(token), json=body)
    assert res.status_code == 200
    return res.json()


def points_of(token):
    return client.get("/api/auth/profile", headers=bearer(token)).json()["profile"]["points"]


def db_row(order_id):
    conn = database.get_db()
    row = conn.execute("SELECT * FROM cashback_orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return dict(row)


# ---------------------------------------------------------------- 金額由伺服器決定

def test_amount_is_locked_to_catalog_price_not_client():
    _, token = new_member()
    res = click(token, price=1)  # 用戶端亂送的價格不採用
    assert res["success"]
    order = res["cashback"]
    assert order["status"] == "tracked" and order["est_price"] == 1800
    assert order["est_points"] == 90 and "$1,800" in res["message"]

    # 確認時送金額也一樣不採用
    done = confirm(token, order["id"], amount=1, order_amount=1, points=99999)
    assert done["success"], done["message"]
    o = done["order"]
    assert o["status"] == "pending" and o["order_amount"] == 1800 and o["points"] == 90
    row = db_row(order["id"])
    assert row["order_amount"] == 1800 and row["points"] == 90


def test_each_pharmacy_uses_its_own_price_and_rate():
    _, token = new_member()
    order = track(token, LUTEIN, "杏一醫療")  # 杏一 $1,760 × 4%
    assert order["pharmacy"] == "杏一醫療" and order["est_price"] == 1760
    assert confirm(token, order["id"])["order"]["points"] == round(1760 * 0.04)


def test_product_name_spacing_does_not_matter():
    _, token = new_member()
    order = track(token, "【HAC 永信】晶亮葉黃膠囊(120粒/瓶)")
    assert order["product_name"] == LUTEIN and order["est_price"] == 1800


def test_search_keyword_from_old_app_still_matches():
    # 舊版 App 的暖心選物送的是搜尋關鍵字（search_kw），不是完整品名
    _, token = new_member()
    order = track(token, "克補 B群 鐵", "大樹藥局")
    assert order["product_name"] == "【克補】B 群 + 鐵加強錠 (100錠/瓶)" and order["est_price"] == 720


def test_product_id_takes_priority_over_name():
    _, token = new_member()
    res = click(token, "隨便的名稱", "大樹藥局", product_id="rec_q10_01")
    assert res["success"] and res["cashback"]["product_name"] == Q10 and res["cashback"]["est_price"] == 748
    res = click(token, LUTEIN, "大樹藥局", product_id="rec_not_exist")
    assert not res["success"]  # ID 錯誤時不改用名稱，避免用別的商品價格


@pytest.mark.parametrize("product,pharmacy", [
    ("自己輸入的商品", "大樹藥局"),
    (Q10, "啄木鳥藥局"),  # 這家藥局沒有這項商品的查價
    ("", "大樹藥局"),
])
def test_no_catalog_price_means_no_cashback(product, pharmacy):
    account, token = new_member()
    res = click(token, product, pharmacy, price=5000)
    assert not res["success"] and "沒有查價資料" in res["message"]
    assert res["official_url"] == "https://example.test"  # 仍可前往藥局，只是不追蹤回饋
    assert client.get("/api/cashback", headers=bearer(token)).json()["orders"] == []


def test_receipt_upload_endpoint_is_gone():
    _, token = new_member()
    order = track(token)
    res = client.post(f"/api/cashback/{order['id']}/receipt", headers=bearer(token), json={"image": "data:image/png;base64,AAAA"})
    assert res.status_code in (404, 405)
    assert db_row(order["id"])["status"] == "tracked"


# ---------------------------------------------------------------- 待入帳與自動入帳

def test_pending_lasts_seven_days_then_credits_once():
    account, token = new_member()
    before = points_of(token)
    order = confirm(token, track(token, VIT_C)["id"])["order"]  # $279 × 5% = 13.95 → 14 點
    assert order["points"] == 14
    purchased = datetime.strptime(order["purchased_at"], TIME_FMT)
    credit_after = datetime.strptime(order["credit_after"], TIME_FMT)
    assert credit_after - purchased == timedelta(days=database.CASHBACK_PENDING_DAYS)

    assert database.settle_due_cashback(account, now=credit_after - timedelta(minutes=1)) == 0
    assert points_of(token) == pytest.approx(before)
    assert database.settle_due_cashback(account, now=credit_after) == 1
    assert database.settle_due_cashback(account, now=credit_after + timedelta(days=1)) == 0
    assert points_of(token) == pytest.approx(before + 14)
    assert db_row(order["id"])["status"] == "confirmed"
    ledger = client.get("/api/points", headers=bearer(token)).json()["ledger"]
    assert sum(1 for item in ledger if "購物回饋" in item["title"]) == 1


def test_reading_profile_credits_due_cashback():
    _, token = new_member()
    before = points_of(token)
    order = confirm(token, track(token, Q10)["id"])["order"]  # $748 × 5% = 37.4 → 37 點
    conn = database.get_db()
    conn.execute("UPDATE cashback_orders SET credit_after = ? WHERE id = ?",
                 ((datetime.now() - timedelta(minutes=1)).strftime(TIME_FMT), order["id"]))
    conn.commit()
    conn.close()
    assert points_of(token) == pytest.approx(before + 37)


# ---------------------------------------------------------------- 防止刷點數

def test_cannot_confirm_twice():
    _, token = new_member()
    order = track(token)
    assert confirm(token, order["id"])["success"]
    again = confirm(token, order["id"])
    assert not again["success"] and "待入帳" in again["message"]


def test_same_product_same_pharmacy_once_per_day():
    _, token = new_member()
    assert confirm(token, track(token, LUTEIN, "大樹藥局")["id"])["success"]
    second = track(token, LUTEIN, "大樹藥局")
    res = confirm(token, second["id"])
    assert not res["success"] and "每天只能回饋 1 次" in res["message"]
    assert db_row(second["id"])["status"] == "tracked"
    # 同一商品換一家藥局可以
    assert confirm(token, track(token, LUTEIN, "杏一醫療")["id"])["success"]


def test_daily_limit_of_three_purchases():
    account, token = new_member()
    limit = database.CASHBACK_DAILY_PURCHASE_LIMIT
    assert limit == 3
    for product in (LUTEIN, FISH_OIL, VIT_C):
        res = confirm(token, track(token, product)["id"])
        assert res["success"], res["message"]
    assert res["purchase_quota"] == {**res["purchase_quota"], "used": 3, "limit": 3, "remaining": 0}

    fourth = track(token, Q10)
    res = confirm(token, fourth["id"])
    assert not res["success"] and "3 筆上限" in res["message"]
    assert db_row(fourth["id"])["status"] == "tracked"
    listed = client.get("/api/cashback", headers=bearer(token)).json()
    assert listed["purchase_quota"]["remaining"] == 0

    # 隔天重新計算：這筆追蹤保留，可以再確認
    tomorrow = datetime.now() + timedelta(days=1)
    order, error = database.confirm_cashback_purchase(fourth["id"], account, now=tomorrow)
    assert error is None and order["status"] == "pending"

    # 其他會員不受影響
    _, other = new_member()
    assert confirm(other, track(other)["id"])["success"]


def test_cancelled_tracking_cannot_be_confirmed():
    _, token = new_member()
    order = track(token)
    assert client.post(f"/api/cashback/{order['id']}/cancel", headers=bearer(token), json={}).json()["success"]
    res = confirm(token, order["id"])
    assert not res["success"] and "已取消" in res["message"]


def test_cannot_cancel_after_confirming():
    _, token = new_member()
    order = track(token)
    assert confirm(token, order["id"])["success"]
    res = client.post(f"/api/cashback/{order['id']}/cancel", headers=bearer(token), json={}).json()
    assert not res["success"] and db_row(order["id"])["status"] == "pending"


def test_only_owner_can_confirm():
    _, alice = new_member()
    _, bob = new_member()
    order = track(alice)
    res = confirm(bob, order["id"])
    assert not res["success"] and "找不到" in res["message"]
    assert db_row(order["id"])["status"] == "tracked"


def test_legacy_tracked_orders_get_catalog_price_or_are_cancelled():
    account, token = new_member()
    now = datetime.now().strftime(TIME_FMT)
    conn = database.get_db()  # 舊版 App 建立的追蹤：價格是用戶端送來的
    conn.execute("""INSERT INTO cashback_orders (id, account, pharmacy, product_name, est_price, rate, status, created_at)
                    VALUES (?, ?, '大樹藥局', ?, 1, 0.05, 'tracked', ?)""", (f"LEGACY_A_{_RUN}", account, LUTEIN, now))
    conn.execute("""INSERT INTO cashback_orders (id, account, pharmacy, product_name, est_price, rate, status, created_at)
                    VALUES (?, ?, '大樹藥局', '魚油', 999, 0.05, 'tracked', ?)""", (f"LEGACY_B_{_RUN}", account, now))
    conn.execute("DELETE FROM system_config WHERE \"key\" = 'cashback_locked_price_20261015'")
    conn.commit()
    conn.close()

    database._lock_tracked_cashback_prices()
    assert db_row(f"LEGACY_A_{_RUN}")["est_price"] == 1800
    legacy_b = db_row(f"LEGACY_B_{_RUN}")
    assert legacy_b["status"] == "rejected" and legacy_b["settled_at"]
    assert confirm(token, f"LEGACY_A_{_RUN}")["order"]["order_amount"] == 1800

    # 只執行一次
    conn = database.get_db()
    conn.execute("UPDATE cashback_orders SET est_price = 5 WHERE id = ?", (f"LEGACY_B_{_RUN}",))
    conn.commit()
    conn.close()
    database._lock_tracked_cashback_prices()
    assert db_row(f"LEGACY_B_{_RUN}")["est_price"] == 5


def test_purchase_endpoints_require_member_token():
    for method, path, body in (
        ("POST", "/api/pharmacy/referral-click", {"product_name": LUTEIN, "pharmacy": "大樹藥局", "official_url": "x"}),
        ("POST", "/api/cashback/CB_X/purchase", {}),
        ("GET", "/api/cashback", None),
    ):
        assert client.request(method, path, json=body).status_code == 401


def test_privacy_policy_no_longer_mentions_receipt_scanning():
    html = client.get("/privacy").text
    assert "Gemini" not in html and "收據" not in html


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
