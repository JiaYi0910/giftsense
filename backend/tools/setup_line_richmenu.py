"""
建立（或更新）GiftSense LINE 官方帳號的圖文選單

用法（在 backend 資料夾執行）：
  python tools/setup_line_richmenu.py           # 預覽，不會改動 LINE
  python tools/setup_line_richmenu.py --apply   # 刪除舊的 GiftSense 選單、建立新選單並設為預設

Channel access token 讀取順序：環境變數 LINE_CHANNEL_ACCESS_TOKEN → backend/.env → main.py 內的預設值
按鈕送出的文字由 main.py 的 LINE webhook 處理（LINE_CMD_*）。
"""
import argparse
import json
import os
import re
import sys

import requests

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_PATH = os.path.join(BACKEND_DIR, "tools", "line_richmenu.png")
MENU_NAME = "GiftSense 主選單"
API = "https://api.line.me/v2/bot"
API_DATA = "https://api-data.line.me/v2/bot"

# 與 make_line_richmenu_image.py 的 BUTTONS 順序一致：3 x 2 按鈕（左上 → 右下）
MENU_ACTIONS = ["今日關懷", "今日用藥", "緊急求助", "綁定說明", "服務說明", "我的綁定"]
COLUMNS = [0, 833, 1667, 2500]
ROWS = [0, 843, 1686]


def load_token() -> str:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if token:
        return token
    env_path = os.path.join(BACKEND_DIR, ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            if line.strip().startswith("LINE_CHANNEL_ACCESS_TOKEN="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    main_src = open(os.path.join(BACKEND_DIR, "main.py"), encoding="utf-8").read()
    match = re.search(r'LINE_CHANNEL_ACCESS_TOKEN = os\.environ\.get\("LINE_CHANNEL_ACCESS_TOKEN"\) or "([^"]+)"', main_src)
    if match:
        return match.group(1)
    raise SystemExit("找不到 LINE_CHANNEL_ACCESS_TOKEN")


def build_menu() -> dict:
    areas = []
    for i, text in enumerate(MENU_ACTIONS):
        col, row = i % 3, i // 3
        areas.append({
            "bounds": {
                "x": COLUMNS[col],
                "y": ROWS[row],
                "width": COLUMNS[col + 1] - COLUMNS[col],
                "height": ROWS[row + 1] - ROWS[row],
            },
            "action": {"type": "message", "label": text, "text": text},
        })
    return {
        "size": {"width": 2500, "height": 1686},
        "selected": True,
        "name": MENU_NAME,
        "chatBarText": "選單",
        "areas": areas,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="實際套用到 LINE 官方帳號")
    args = parser.parse_args()

    menu = build_menu()
    if not os.path.exists(IMAGE_PATH):
        raise SystemExit(f"找不到選單圖片 {IMAGE_PATH}，請先執行 tools/make_line_richmenu_image.py")
    if not args.apply:
        print(json.dumps(menu, ensure_ascii=False, indent=2))
        print(f"\n圖片：{IMAGE_PATH}（{os.path.getsize(IMAGE_PATH) // 1024} KB）")
        print("以上為預覽；加上 --apply 才會套用到 LINE。")
        return

    headers = {"Authorization": f"Bearer {load_token()}"}

    # 1. 刪除舊的 GiftSense 選單，避免重複
    res = requests.get(f"{API}/richmenu/list", headers=headers, timeout=15)
    res.raise_for_status()
    for old in res.json().get("richmenus", []):
        if old.get("name") == MENU_NAME:
            requests.delete(f"{API}/richmenu/{old['richMenuId']}", headers=headers, timeout=15).raise_for_status()
            print(f"已刪除舊選單 {old['richMenuId']}")

    # 2. 建立選單、上傳圖片、設為所有使用者的預設選單
    res = requests.post(f"{API}/richmenu", headers=headers, json=menu, timeout=15)
    res.raise_for_status()
    menu_id = res.json()["richMenuId"]
    with open(IMAGE_PATH, "rb") as f:
        requests.post(
            f"{API_DATA}/richmenu/{menu_id}/content",
            headers={**headers, "Content-Type": "image/png"},
            data=f.read(),
            timeout=30,
        ).raise_for_status()
    requests.post(f"{API}/user/all/richmenu/{menu_id}", headers=headers, timeout=15).raise_for_status()
    print(f"✅ 已建立並套用圖文選單 {menu_id}")


if __name__ == "__main__":
    main()
