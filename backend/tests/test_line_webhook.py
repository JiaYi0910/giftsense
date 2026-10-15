"""
LINE webhook 金鑰：Channel secret / access token 只能來自環境變數，未設定時 webhook 一律拒絕。

執行（在 backend 資料夾）：
    python -m pytest tests/test_line_webhook.py -q
    或 python tests/test_line_webhook.py

測試使用 caregift.db 的暫存複本，不會改到 repo 內的資料庫，也不連線 Turso / LINE / Gemini。
"""
import ast
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
_TMP_DIR = tempfile.mkdtemp(prefix="giftsense_line_test_")
TEST_DB = os.path.join(_TMP_DIR, "caregift.db")
shutil.copy(os.path.join(BACKEND, "caregift.db"), TEST_DB)

os.environ["CAREGIFT_DB_PATH"] = TEST_DB
for _key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "GEMINI_API_KEY"):
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

TEST_SECRET = "test-only-line-channel-secret"
LINE_USER = "U_line_webhook_test_user"


def sign(body: bytes, secret: str) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def text_event_body(text: str) -> bytes:
    event = {
        "type": "message",
        "replyToken": "reply-token-test",
        "source": {"type": "user", "userId": LINE_USER},
        "message": {"type": "text", "id": "1", "text": text},
    }
    return json.dumps({"events": [event]}, ensure_ascii=False).encode()


@pytest.fixture
def line_calls(monkeypatch):
    """記錄送進 _handle_line_event 的事件，以及所有對外 HTTP 呼叫（不會真的連線）"""
    calls = {"events": [], "http": []}
    real_handle = main._handle_line_event

    def spy(event):
        calls["events"].append(event)
        real_handle(event)

    def no_network(*args, **kwargs):
        calls["http"].append(args[0] if args else kwargs.get("url"))
        raise AssertionError("測試不可呼叫 LINE API")

    monkeypatch.setattr(main, "_handle_line_event", spy)
    monkeypatch.setattr(main.requests, "post", no_network)
    monkeypatch.setattr(main.requests, "get", no_network)
    return calls


def test_no_hardcoded_line_credentials():
    """main.py 裡 LINE 金鑰的賦值不可帶任何字串預設值（只允許空字串）"""
    tree = ast.parse(open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read())
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        for name in names & {"LINE_CHANNEL_SECRET", "LINE_CHANNEL_ACCESS_TOKEN"}:
            found.add(name)
            literals = [c.value for c in ast.walk(node.value) if isinstance(c, ast.Constant) and isinstance(c.value, str)]
            assert all(value in ("", name) for value in literals), f"{name} 不可寫死預設值"
    assert found == {"LINE_CHANNEL_SECRET", "LINE_CHANNEL_ACCESS_TOKEN"}


def test_webhook_rejects_everything_without_secret(monkeypatch, line_calls):
    monkeypatch.setattr(main, "LINE_CHANNEL_SECRET", "")
    body = text_event_body("綁定 123456")
    # 空字串也能算出 HMAC，若沒擋下，任何人都能用空金鑰偽造簽章
    for signature in ("", "bad", sign(body, ""), sign(body, TEST_SECRET)):
        res = client.post("/api/line/webhook", content=body, headers={"X-Line-Signature": signature})
        assert res.status_code == 503, signature
    assert line_calls["events"] == []
    assert line_calls["http"] == []


def test_webhook_accepts_correct_signature_when_secret_set(monkeypatch, line_calls):
    monkeypatch.setattr(main, "LINE_CHANNEL_SECRET", TEST_SECRET)
    monkeypatch.setattr(main, "LINE_CHANNEL_ACCESS_TOKEN", "")  # 沒有 token：回覆要安靜略過，不打 LINE API
    body = text_event_body("服務說明")

    bad = client.post("/api/line/webhook", content=body, headers={"X-Line-Signature": sign(body, "wrong-secret")})
    assert bad.status_code == 400
    assert line_calls["events"] == []

    res = client.post("/api/line/webhook", content=body, headers={"X-Line-Signature": sign(body, TEST_SECRET)})
    assert res.status_code == 200 and res.json() == {"status": "success"}
    assert [e["message"]["text"] for e in line_calls["events"]] == ["服務說明"]
    assert line_calls["http"] == []


def test_line_helpers_skip_without_access_token(monkeypatch, line_calls):
    monkeypatch.setattr(main, "LINE_CHANNEL_ACCESS_TOKEN", "")
    monkeypatch.setitem(main._line_bot_basic_id_cache, "value", "")
    main._line_reply("reply-token-test", LINE_USER, [{"type": "text", "text": "hi"}])
    assert main._download_line_audio("1") == "[語音訊息下載失敗]"
    assert main._get_line_bot_basic_id() == ""
    assert line_calls["http"] == []


def test_health_reports_line_config(monkeypatch):
    monkeypatch.setattr(main, "LINE_CHANNEL_SECRET", "")
    monkeypatch.setattr(main, "LINE_CHANNEL_ACCESS_TOKEN", TEST_SECRET)
    data = client.get("/api/health").json()
    assert data["line_channel_secret"] == "missing"
    assert data["line_channel_access_token"] == "configured"
    assert TEST_SECRET not in json.dumps(data)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
