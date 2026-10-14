"""
快速提問驗證：每一題點下去後，AI 守護助理檢索到的資料都要和題目相符。

執行：python tests/test_quick_questions.py（在 backend 資料夾）
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

import chips_generator as cg  # noqa: E402
from rag_engine import query_rag_engine  # noqa: E402

# 每類病況用一個代表性的病況描述來測試
SAMPLE_CONDITION = {
    "抗凝血": "心房顫動，服用 Warfarin",
    "腎臟病": "慢性腎臟病 未洗腎",
    "糖尿病": "第二型糖尿病，服用 Metformin",
    "高血壓": "高血壓，服用脈優",
    "高血脂": "膽固醇偏高，服用 Statin",
    "心臟病": "冠心病，裝過支架",
    "肝病": "脂肪肝，肝指數偏高",
    "癌症": "乳癌化療中",
    "懷孕哺乳": "懷孕 20 週",
    "甲狀腺": "甲狀腺功能低下，服用昂特欣",
    "痛風": "痛風，尿酸偏高",
    "失智": "輕度失智，記憶力變差",
    "帕金森": "帕金森氏症",
    "失眠": "失眠，服用安眠藥",
    "腸胃": "胃食道逆流，常便秘",
    "感冒免疫": "容易感冒",
    "骨骼關節": "膝關節退化，骨質疏鬆",
    "眼睛": "黃斑部退化",
    "傷口": "手部燙傷，傷口未癒合",
    "泌尿道": "反覆泌尿道感染",
    "皮膚": "皮膚乾癢濕疹",
    "疲勞": "常熬夜加班",
}


def answer_source(query: str, condition: str):
    res = query_rag_engine(query, "親友", condition)
    if res.get("is_symptom_track"):
        return f"symptom:{res['symptom_data']['category']}", res
    if not res.get("has_match"):
        return "no_match", res
    return res["matched_literatures"][0]["id"], res


def main():
    failures, total, collisions = [], 0, 0
    cases = [(cat, SAMPLE_CONDITION[cat], chips) for cat, _, chips in cg.CONDITION_CATEGORIES]
    cases.append(("日常保養", "日常養生", cg.DEFAULT_CHIPS))
    for cat, condition, chips in cases:
        assert cat == "日常保養" or cat in cg.matched_categories(condition), f"{cat} 的代表病況沒有對應到分類"
        for chip in chips:
            total += 1
            src, res = answer_source(chip["query"], condition)
            hit = src in chip["expect"]
            is_collision = bool(res.get("safety", {}).get("is_collision"))
            collisions += is_collision
            mark = "OK  " if hit else "FAIL"
            print(f"{mark} [{cat}] {chip['label']} → {src}{'（撞藥警示）' if is_collision else ''}")
            if not hit:
                failures.append((cat, chip["label"], src, chip["expect"]))
            assert len(chip["label"]) <= 14, f"標籤太長：{chip['label']}"

    # 病況比對：否定說法不算、多種病況輪流取題
    assert cg.matched_categories("無糖尿病，高血壓") == ["高血壓"]
    assert "腎臟病" in cg.matched_categories("慢性腎臟病 未洗腎")
    assert cg.matched_categories("日常養生") == []
    mixed = cg._get_clinical_rule_chips("高血壓、糖尿病、腎臟病", "爺爺")
    assert len(mixed) == 8 and {c["label"] for c in mixed[:3]} == {"腎病能吃止痛藥嗎", "降糖藥能吃苦瓜胜肽嗎", "降壓藥能吃葡萄柚嗎"}
    assert all("expect" not in c for c in cg.get_clinical_rule_chips("高血壓", "爺爺"))
    assert "爺爺" in cg.get_clinical_rule_chips("高血壓", "爺爺")[0]["query"]

    print(f"\n共 {total} 題，{total - len(failures)} 題檢索正確，{collisions} 題觸發撞藥警示")
    if failures:
        for f in failures:
            print("  不符：", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
