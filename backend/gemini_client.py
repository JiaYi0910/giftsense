# -*- coding: utf-8 -*-
"""
Gemini 文字生成的共用呼叫：首頁問候語、親友快速提問、AI 守護助理的生成式模式

- 模型：預設 gemini-3.1-flash-lite（可用環境變數 GEMINI_TEXT_MODEL 改）。2026/11/17 實測：
  gemini-1.5 系列已下架（404）；gemini-2.5-flash 不再開放給新使用者（404）；gemini-3.8-flash、3.5-flash 超過 45 秒沒有回應；
  gemini-3.1-flash-lite 約 1～2 秒。舊版 App 或管理後台存的舊模型名稱一律改用預設模型
- 金鑰放在 x-goog-api-key 標頭，不放網址，錯誤訊息與伺服器記錄才不會出現金鑰
- 關閉「思考」：思考會用掉輸出字數上限、拖慢回應，問候語與提問這類短文不需要
- 介面不使用 emoji：回傳的文字一律濾掉 emoji
- 任何失敗都回傳空字串，由呼叫端改用內建內容
"""
import os
import re

import requests

DEFAULT_MODEL = "gemini-3.1-flash-lite"
SUPPORTED_MODELS = ("gemini-3.1-flash-lite",)
GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_EMOJI = re.compile(r"[\u2600-\u27bf\u2b00-\u2bff\U0001F000-\U0001FAFF]\ufe0f?")   # emoji 與變體選擇符


def strip_emoji(text: str) -> str:
    return _EMOJI.sub("", text or "")


def text_model(requested: str = None) -> str:
    """要使用的模型：請求指定且仍可用的模型，否則用預設模型"""
    if requested in SUPPORTED_MODELS:
        return requested
    return (os.getenv("GEMINI_TEXT_MODEL") or "").strip() or DEFAULT_MODEL


def thinking_config(name: str):
    """關閉思考的設定：Gemini 2.5 Flash 用 thinkingBudget，Gemini 3 Flash-Lite 用 thinkingLevel"""
    if name.startswith("gemini-2.5-flash"):
        return {"thinkingBudget": 0}
    if name.startswith("gemini-3") and "flash-lite" in name:
        return {"thinkingLevel": "minimal"}
    return None


def generate(prompt: str, api_key: str, model: str = None, temperature: float = 0.4,
             max_tokens: int = None, json_mode: bool = False, timeout: float = 8) -> str:
    """回傳 Gemini 生成的文字；沒有金鑰或呼叫失敗時回傳空字串"""
    if not (api_key or "").strip():
        return ""
    name = text_model(model)
    config = {"temperature": temperature}
    thinking = thinking_config(name)
    if thinking:
        config["thinkingConfig"] = thinking
    if max_tokens:
        config["maxOutputTokens"] = max_tokens
    if json_mode:
        config["responseMimeType"] = "application/json"
    try:
        res = requests.post(GENERATE_URL.format(model=name), headers={"x-goog-api-key": api_key.strip()},
                            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config},
                            timeout=timeout)
        if res.status_code != 200:
            print(f"【Gemini】{name} 回應 HTTP {res.status_code}，改用內建內容")
            return ""
        parts = (res.json().get("candidates") or [{}])[0].get("content", {}).get("parts") or []
        return strip_emoji("".join(p.get("text", "") for p in parts if not p.get("thought"))).strip()
    except Exception as e:  # 只印例外類型，不印內容
        print(f"【Gemini】{name} 呼叫失敗（{type(e).__name__}），改用內建內容")
        return ""


def parse_json(text: str):
    """解析 Gemini 回傳的 JSON（容許外面包著 ```json）；失敗回傳 None"""
    import json

    clean = (text or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(clean)
    except (ValueError, TypeError):
        return None
