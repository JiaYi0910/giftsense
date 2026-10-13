"""
產生 LINE 圖文選單圖片（2500 x 1686，上下兩排共 6 個按鈕）

沿用原本 GiftSense 圖文選單的風格：淡藍漸層背景、細分隔線、
藍色線條圖示（外圍細圓框與裝飾點）、深藍粗體標題與灰藍說明文字。
圖示全部用線條繪製，不使用 emoji。

需要 Pillow：pip install pillow
用法：python tools/make_line_richmenu_image.py [--font 中文字型]
預設使用 Windows 內建的思源黑體 (Noto Sans TC)；輸出 tools/line_richmenu.png
"""
import argparse
import math
import os

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 2500, 1686
SCALE = 2  # 先放大繪製再縮小，讓線條平滑
COLUMNS = [0, 833, 1667, 2500]
ROWS = [0, 843, 1686]

BG_TOP = (248, 251, 255)
BG_BOTTOM = (226, 236, 248)
DIVIDER = (196, 212, 232)
RING = (170, 192, 220)
ICON = (43, 92, 158)
ICON_DANGER = (200, 45, 45)
TITLE = (30, 58, 102)
TITLE_DANGER = (200, 38, 38)
SUBTITLE = (84, 104, 130)

# (按鈕文字＝送出的指令, 說明, 圖示, 是否為警示樣式) — 順序需與 setup_line_richmenu.py 的 MENU_ACTIONS 一致
BUTTONS = [
    ("今日關懷", "查看家人送的關懷卡", "envelope", False),
    ("今日用藥", "查看服藥與保健叮嚀", "medicine", False),
    ("緊急求助", "即時通知守護家人", "bell", True),
    ("綁定說明", "如何綁定與改綁家人", "link", False),
    ("服務說明", "點擊查看使用指南", "book", False),
    ("我的綁定", "查看守護我的家人", "person", False),
]

DEFAULT_FONTS = [r"C:\Windows\Fonts\NotoSansTC-VF.ttf", r"C:\Windows\Fonts\msjhbd.ttc", "/System/Library/Fonts/PingFang.ttc"]


def S(v):
    return int(round(v * SCALE))


def load_font(path, size, weight):
    font = ImageFont.truetype(path, S(size))
    try:
        font.set_variation_by_name(weight)
    except Exception:
        pass
    return font


def rotate(points, cx, cy, angle_deg):
    a = math.radians(angle_deg)
    return [(cx + (x - cx) * math.cos(a) - (y - cy) * math.sin(a),
             cy + (x - cx) * math.sin(a) + (y - cy) * math.cos(a)) for x, y in points]


def rounded_rect_points(cx, cy, w, h, r, steps=10):
    pts = []
    for qx, qy, start in [(w / 2 - r, -h / 2 + r, -90), (w / 2 - r, h / 2 - r, 0),
                          (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180)]:
        for i in range(steps + 1):
            t = math.radians(start + 90 * i / steps)
            pts.append((cx + qx + r * math.cos(t), cy + qy + r * math.sin(t)))
    return pts


def outline(draw, pts, color, width):
    draw.line([(S(x), S(y)) for x, y in pts] + [(S(pts[0][0]), S(pts[0][1]))], fill=color, width=S(width), joint="curve")


def line(draw, pts, color, width):
    draw.line([(S(x), S(y)) for x, y in pts], fill=color, width=S(width), joint="curve")


def arc(draw, cx, cy, r, start, end, color, width):
    draw.arc((S(cx - r), S(cy - r), S(cx + r), S(cy + r)), start, end, fill=color, width=S(width))


def dot(draw, x, y, r, color):
    draw.ellipse((S(x - r), S(y - r), S(x + r), S(y + r)), fill=color)


def draw_ring(draw, cx, cy, r):
    # 細圓框：左半實線、右半虛線，四個方位各一個裝飾點
    arc(draw, cx, cy, r, 90, 270, RING, 3)
    for start in range(-90, 90, 12):
        arc(draw, cx, cy, r, start, start + 6, RING, 3)
    for ang in (0, 90, 180, 270):
        t = math.radians(ang)
        dot(draw, cx + r * math.cos(t), cy + r * math.sin(t), 7, ICON)


def icon_envelope(draw, cx, cy, c):
    w, h = 190, 130
    outline(draw, rounded_rect_points(cx, cy, w, h, 14), c, 9)
    line(draw, [(cx - w / 2 + 10, cy - h / 2 + 12), (cx, cy + 10), (cx + w / 2 - 10, cy - h / 2 + 12)], c, 9)
    pts = []
    for i in range(60):
        t = 2 * math.pi * i / 60
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + 62 + x * 2.6, cy + 52 + y * 2.6))
    draw.polygon([(S(x), S(y)) for x, y in pts], fill=(255, 255, 255))
    outline(draw, pts, c, 8)


def icon_medicine(draw, cx, cy, c):
    bx, by = cx - 35, cy + 5
    outline(draw, rounded_rect_points(bx, by, 150, 120, 10), c, 9)
    outline(draw, rounded_rect_points(bx, by - 78, 164, 36, 8), c, 9)
    line(draw, [(bx, by - 32), (bx, by + 32)], c, 10)
    line(draw, [(bx - 32, by), (bx + 32, by)], c, 10)
    capsule = rotate(rounded_rect_points(cx + 70, cy + 62, 120, 50, 25), cx + 70, cy + 62, -40)
    draw.polygon([(S(x), S(y)) for x, y in capsule], fill=(255, 255, 255))
    outline(draw, capsule, c, 8)
    line(draw, rotate([(cx + 70, cy + 37), (cx + 70, cy + 87)], cx + 70, cy + 62, -40), c, 8)


def icon_bell(draw, cx, cy, c):
    # 圓頂鈴鐺：上方半圓 → 兩側直線往下微張 → 底部外擴裙邊
    dome_cy, dome_r, bottom = cy - 30, 58, cy + 55
    pts = []
    for i in range(31):
        t = math.radians(180 + 180 * i / 30)
        pts.append((cx + dome_r * math.cos(t), dome_cy + dome_r * math.sin(t)))
    pts += [(cx + dome_r + 8, bottom - 22), (cx + 92, bottom), (cx - 92, bottom), (cx - dome_r - 8, bottom - 22)]
    outline(draw, pts, c, 9)
    arc(draw, cx, dome_cy - dome_r - 10, 13, 0, 360, c, 8)
    arc(draw, cx, bottom + 4, 24, 0, 180, c, 9)
    line(draw, [(cx, cy - 36), (cx, cy + 6)], c, 11)
    dot(draw, cx, cy + 28, 8, c)
    for side in (-1, 1):
        for rr in (125, 155):
            start = -30 if side == 1 else 150
            arc(draw, cx, cy - 15, rr, start, start + 60, c, 8)


def icon_link(draw, cx, cy, c):
    for dx, dy in ((-50, 36), (50, -36)):
        pts = rotate(rounded_rect_points(cx + dx, cy + dy, 140, 64, 32), cx + dx, cy + dy, -35)
        outline(draw, pts, c, 10)


def icon_book(draw, cx, cy, c):
    left = [(cx - 8, cy - 70), (cx - 130, cy - 82), (cx - 130, cy + 70), (cx - 8, cy + 82)]
    right = [(cx + 8, cy - 70), (cx + 130, cy - 90), (cx + 130, cy + 62), (cx + 8, cy + 82)]
    outline(draw, left, c, 9)
    outline(draw, right, c, 9)
    outline(draw, [(cx - 110, cy - 55), (cx - 62, cy - 51), (cx - 62, cy - 10), (cx - 110, cy - 14)], c, 6)
    for i in range(4):
        y = cy - 38 + i * 28
        line(draw, [(cx + 30, y + 2), (cx + 110, y - 10)], c, 6)
    for i in range(2):
        y = cy + 18 + i * 26
        line(draw, [(cx - 110, y), (cx - 30, y + 6)], c, 6)


def icon_person(draw, cx, cy, c):
    arc(draw, cx, cy - 38, 42, 0, 360, c, 9)
    arc(draw, cx, cy + 105, 92, 200, 340, c, 9)
    line(draw, [(cx - 86, cy + 73), (cx - 86, cy + 78)], c, 9)
    line(draw, [(cx + 86, cy + 73), (cx + 86, cy + 78)], c, 9)


ICONS = {
    "envelope": icon_envelope, "medicine": icon_medicine, "bell": icon_bell,
    "link": icon_link, "book": icon_book, "person": icon_person,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", default=next((f for f in DEFAULT_FONTS if os.path.exists(f)), None))
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "line_richmenu.png"))
    args = parser.parse_args()
    if not args.font:
        raise SystemExit("找不到中文字型，請用 --font 指定")

    title_font = load_font(args.font, 132, "Black")
    sub_font = load_font(args.font, 64, "Medium")

    img = Image.new("RGB", (S(WIDTH), S(HEIGHT)))
    draw = ImageDraw.Draw(img)

    # 淡藍漸層背景
    for y in range(S(HEIGHT)):
        t = y / S(HEIGHT)
        color = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3))
        draw.line([(0, y), (S(WIDTH), y)], fill=color)

    # 細分隔線
    for x in COLUMNS[1:-1]:
        for y0, y1 in zip(ROWS[:-1], ROWS[1:]):
            line(draw, [(x, y0 + 70), (x, y1 - 70)], DIVIDER, 3)
    line(draw, [(90, ROWS[1]), (WIDTH - 90, ROWS[1])], DIVIDER, 3)

    for i, (title, sub, icon, danger) in enumerate(BUTTONS):
        col, row = i % 3, i // 3
        cx = (COLUMNS[col] + COLUMNS[col + 1]) / 2
        y0 = ROWS[row]
        icy = y0 + 255
        draw_ring(draw, cx, icy, 175)
        ICONS[icon](draw, cx, icy, ICON_DANGER if danger else ICON)
        draw.text((S(cx), S(y0 + 560)), title, font=title_font, fill=TITLE_DANGER if danger else TITLE, anchor="mm")
        draw.text((S(cx), S(y0 + 690)), sub, font=sub_font, fill=SUBTITLE, anchor="mm")

    img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)
    img.save(args.out, optimize=True)
    print(f"已輸出 {args.out}（{os.path.getsize(args.out) // 1024} KB）")


if __name__ == "__main__":
    main()
