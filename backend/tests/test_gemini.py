"""
Gemini 文字生成：模型名稱、金鑰位置、AI 快速提問的篩選與問候語的衛教叮嚀。

執行（在 backend 資料夾）：
    python -m pytest tests/test_gemini.py -q

不連線 Gemini：HTTP 呼叫與生成結果一律換成假的。
"""
import json
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

import chips_generator as cg  # noqa: E402
import gemini_client  # noqa: E402
import greeting_generator as gg  # noqa: E402

FAKE_KEY = "test-key-not-real"


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


# -------------------------------------------------------------------------
# 共用呼叫
# -------------------------------------------------------------------------
def test_retired_models_map_to_the_default(monkeypatch):
    monkeypatch.delenv("GEMINI_TEXT_MODEL", raising=False)
    default = gemini_client.DEFAULT_MODEL
    assert default == "gemini-3.1-flash-lite"
    for retired in ("gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.5-flash", None):   # 已下架或不開放給新使用者
        assert gemini_client.text_model(retired) == default
    monkeypatch.setenv("GEMINI_TEXT_MODEL", "gemini-3.8-flash")
    assert gemini_client.text_model("gemini-1.5-flash") == "gemini-3.8-flash"
    assert gemini_client.thinking_config("gemini-3.1-flash-lite") == {"thinkingLevel": "minimal"}
    assert gemini_client.thinking_config("gemini-2.5-flash") == {"thinkingBudget": 0}
    assert gemini_client.thinking_config("gemini-3.8-flash") is None      # 不支援 minimal，用預設


def test_key_goes_in_header_and_thinking_is_off(monkeypatch):
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.update(url=url, headers=headers, body=json)
        return FakeResponse(200, {"candidates": [{"content": {"parts": [
            {"text": "思考過程", "thought": True}, {"text": "問候"}, {"text": "內容"}]}}]})

    monkeypatch.setattr(gemini_client.requests, "post", fake_post)
    out = gemini_client.generate("提示", FAKE_KEY, model="gemini-1.5-flash", max_tokens=100, json_mode=True)
    assert out == "問候內容"
    assert FAKE_KEY not in sent["url"] and sent["headers"]["x-goog-api-key"] == FAKE_KEY
    assert "/models/gemini-3.1-flash-lite:generateContent" in sent["url"]
    config = sent["body"]["generationConfig"]
    assert config["thinkingConfig"] == {"thinkingLevel": "minimal"} and config["maxOutputTokens"] == 100
    assert config["responseMimeType"] == "application/json"


def test_failures_return_empty_text_without_leaking_the_key(monkeypatch, capsys):
    monkeypatch.setattr(gemini_client.requests, "post", lambda *a, **k: FakeResponse(404, {"error": {}}))
    assert gemini_client.generate("提示", FAKE_KEY) == ""

    def boom(*a, **k):
        raise RuntimeError(f"connection failed for key={FAKE_KEY}")

    monkeypatch.setattr(gemini_client.requests, "post", boom)
    assert gemini_client.generate("提示", FAKE_KEY) == ""
    assert gemini_client.generate("提示", "") == ""
    assert FAKE_KEY not in capsys.readouterr().out
    assert gemini_client.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert gemini_client.parse_json("不是 JSON") is None


# -------------------------------------------------------------------------
# AI 快速提問
# -------------------------------------------------------------------------
AI_CHIPS = [
    {"label": "⚠️ 抗凝血藥能吃納豆嗎", "query": "爺爺在吃抗凝血藥，可以吃納豆激酶嗎？", "badge": "撞藥防錯"},
    {"label": "魚油會增加出血嗎", "query": "爺爺在吃抗凝血藥，可以吃魚油嗎？", "badge": "TFDA警示"},
    {"label": "這個標籤實在是太長了超過十四個字", "query": "爺爺可以吃銀杏嗎？", "badge": "撞藥防錯"},
    {"label": "推薦哪支股票", "query": "爺爺想買股票，推薦哪一支？", "badge": "實證保健"},
    {"label": "銀杏能一起吃嗎", "query": "爺爺在吃抗凝血藥，可以吃銀杏嗎？", "badge": "撞藥防錯"},
    {"label": "流鼻血要就醫嗎", "query": "爺爺在吃抗凝血藥，流鼻血止不住要就醫嗎？", "badge": "就醫警訊"},
]


def answerable(query):
    return "股票" not in query


def test_ai_chips_are_cleaned_and_must_be_answerable(monkeypatch):
    monkeypatch.setattr(gemini_client, "generate", lambda *a, **k: json.dumps(AI_CHIPS, ensure_ascii=False))
    chips = cg.generate_ai_recipient_chips("爺爺", "服用 Warfarin", api_key=FAKE_KEY, answerable=answerable)
    labels = [c["label"] for c in chips]
    assert labels == ["抗凝血藥能吃納豆嗎", "魚油會增加出血嗎", "銀杏能一起吃嗎", "流鼻血要就醫嗎"]
    assert all(c["badge"] in cg.BADGES for c in chips)
    assert chips[1]["badge"] == cg.EVID                       # 「TFDA警示」不是允許的分類
    assert [c["warning"] for c in chips] == [True, False, True, True]


def test_ai_chips_fall_back_to_verified_rule_chips(monkeypatch):
    rule = cg.get_clinical_rule_chips("服用 Warfarin", "爺爺")
    monkeypatch.setattr(gemini_client, "generate", lambda *a, **k: json.dumps(AI_CHIPS[:3], ensure_ascii=False))
    assert cg.generate_ai_recipient_chips("爺爺", "服用 Warfarin", api_key=FAKE_KEY, answerable=answerable) == rule
    monkeypatch.setattr(gemini_client, "generate", lambda *a, **k: "")
    assert cg.generate_ai_recipient_chips("爺爺", "服用 Warfarin", api_key=FAKE_KEY) == rule


# -------------------------------------------------------------------------
# 問候語
# -------------------------------------------------------------------------
GREETING_ARGS = dict(elder_name="奶奶", elder_condition="高血壓", weather_city="臺北市", weather_temp="18°C",
                     weather_temp_diff=8, weather_condition="多雲", weather_humidity=70, elder_status="normal",
                     tone="reserved", variant=0)


def test_greeting_uses_gemini_text_but_keeps_the_builtin_insight(monkeypatch):
    gg._AI_GREETING_CACHE.clear()
    calls = []

    def fake_generate(prompt, key, **kw):
        calls.append(prompt)
        return '{"message": "「奶奶早安，今天臺北多雲，出門記得加件外套。」"}'

    monkeypatch.setattr(gemini_client, "generate", fake_generate)
    local = gg.generate_local_dynamic_greeting(**GREETING_ARGS)
    out = gg.generate_ai_greeting(**GREETING_ARGS, api_key=FAKE_KEY)
    assert out["message"] == "「奶奶早安，今天臺北多雲，出門記得加件外套。」" and out["source"] == "gemini"
    assert out["clinical_insight"] == local["clinical_insight"]
    assert "指引、期刊、機構名稱" in calls[0]
    gg.generate_ai_greeting(**GREETING_ARGS, api_key=FAKE_KEY)     # 同一天同條件：用快取，不再呼叫
    assert len(calls) == 1


def test_greeting_falls_back_to_builtin_text(monkeypatch):
    gg._AI_GREETING_CACHE.clear()
    monkeypatch.setattr(gemini_client, "generate", lambda *a, **k: "")
    assert gg.generate_ai_greeting(**GREETING_ARGS, api_key=FAKE_KEY) == gg.generate_local_dynamic_greeting(**GREETING_ARGS)
