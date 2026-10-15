"""
快速提問驗證：每一題點下去後，AI 守護助理檢索到的資料都要和題目相符。

執行：python tests/test_quick_questions.py（在 backend 資料夾）

檢索索引和正式環境一樣由資料庫重建：複製一份 repo 內附的 caregift.db（Turso 第一次啟動時匯入的就是它）
到暫存資料夾，import database 時跑完 init_db() 的所有遷移，再以資料庫中的文獻重建索引。
"""
import atexit
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")  # assert 失敗訊息才不會變亂碼
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

TEST_DIR = tempfile.mkdtemp(prefix="giftsense_test_")
atexit.register(shutil.rmtree, TEST_DIR, ignore_errors=True)
shutil.copy(os.path.join(BACKEND, "caregift.db"), os.path.join(TEST_DIR, "caregift.db"))
os.environ["CAREGIFT_DB_PATH"] = os.path.join(TEST_DIR, "caregift.db")
os.environ.pop("TURSO_DATABASE_URL", None)  # 測試一律用本機的暫存資料庫，不碰雲端資料庫

import database  # noqa: E402  （import 時執行 init_db）
import chips_generator as cg  # noqa: E402
from rag_engine import query_rag_engine  # noqa: E402
from vector_store import FULL_CLINICAL_LITERATURES, global_vector_store  # noqa: E402

# 程式碼中的內建文獻欄位 → 資料庫欄位
BUILTIN_FIELDS = {
    "title": "title", "authority": "authority", "category": "category", "ingredient": "ingredient",
    "evidenceLevel": "evidence_level", "recommendedDose": "recommended_dose", "mechanism": "mechanism",
    "contraindications": "contraindications", "targetSymptoms": "targetSymptoms", "citation": "citation",
}

# 與照護無關的問題不應該硬套文獻
UNRELATED_QUERIES = ["今天台北天氣如何？", "推薦一部好看的電影", "股票要怎麼買比較好？", "附近哪裡有好吃的拉麵？"]

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


def load_index_from_db():
    """與 main.py 的 _refresh_rag_index() 相同：以資料庫中的文獻重建檢索索引"""
    db_items = database.get_all_clinical_knowledge()
    count = global_vector_store.reload(db_items)
    assert count == len(db_items) > 0, "資料庫文獻沒有全部進入索引"
    by_id = {d["id"]: d for d in db_items}
    for lit in FULL_CLINICAL_LITERATURES:
        row = by_id.get(lit["id"])
        assert row, f"資料庫缺少內建文獻 {lit['id']}"
        for code_key, db_key in BUILTIN_FIELDS.items():
            assert row[db_key] == lit[code_key], f"資料庫的 {lit['id']}.{db_key} 和程式碼不同"
    print(f"已從測試資料庫重建索引：{count} 篇文獻\n")


def main():
    load_index_from_db()
    failures, extra_failures, total, collisions = [], [], 0, 0
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
            # 實際提問會把「親友」換成親友的稱呼，檢索結果不能只靠「親友」這兩個字
            named_src, _ = answer_source(chip["query"].replace("親友", "爺爺"), condition)
            if named_src not in chip["expect"]:
                print(f"FAIL [{cat}] {chip['label']}（爺爺）→ {named_src}")
                extra_failures.append((cat, chip["label"] + "（爺爺）", named_src, chip["expect"]))

    for q in UNRELATED_QUERIES:
        src, _ = answer_source(q, "日常養生")
        if src != "no_match":
            extra_failures.append(("無關問題", q, src, ["no_match"]))

    # 病況比對：否定說法不算、多種病況輪流取題
    assert cg.matched_categories("無糖尿病，高血壓") == ["高血壓"]
    assert "腎臟病" in cg.matched_categories("慢性腎臟病 未洗腎")
    assert cg.matched_categories("日常養生") == []
    mixed = cg._get_clinical_rule_chips("高血壓、糖尿病、腎臟病", "爺爺")
    assert len(mixed) == 8 and {c["label"] for c in mixed[:3]} == {"腎病能吃止痛藥嗎", "降糖藥能吃苦瓜胜肽嗎", "降壓藥能吃葡萄柚嗎"}
    assert all("expect" not in c for c in cg.get_clinical_rule_chips("高血壓", "爺爺"))
    assert "爺爺" in cg.get_clinical_rule_chips("高血壓", "爺爺")[0]["query"]

    print(f"\n共 {total} 題，{total - len(failures)} 題檢索正確，{collisions} 題觸發撞藥警示")
    print(f"代入稱呼（爺爺）與 {len(UNRELATED_QUERIES)} 題無關問題：{len(extra_failures)} 題不符")
    if failures or extra_failures:
        for f in failures + extra_failures:
            print("  不符：", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
