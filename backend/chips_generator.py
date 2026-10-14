import os
import json
import re
import requests
from typing import List, Dict, Any, Optional

_LEADING_EMOJI = re.compile(r"^[\s☀-➿⬀-⯿️\U0001F000-\U0001FAFF]+")

def normalize_chip(chip: Dict[str, Any]) -> Dict[str, Any]:
    """標籤不使用 emoji：去掉開頭的 emoji，原本以 ⚠️ 標示的撞藥警示改用 warning 欄位"""
    label = str(chip.get("label", ""))
    warning = bool(chip.get("warning")) or "⚠" in label
    return {**chip, "label": _LEADING_EMOJI.sub("", label).strip(), "warning": warning}

def normalize_chips(chips) -> List[Dict[str, Any]]:
    return [normalize_chip(c) for c in (chips or []) if isinstance(c, dict)]


# =========================================================================
# Track 1：依親友病況產生快速提問（規則式，零延遲）
#
# 每一類病況各有一組提問，順序是「撞藥防錯 → 就醫警訊 → 飲食／照護 → 實證保健」。
# 每題的 expect 是預期會由 AI 守護助理檢索到的文獻 id（或 symptom:穴位舒緩類別），
# 由 tests/test_quick_questions.py 逐題驗證，確保點下去的回答和病況真的有關。
# =========================================================================
DRUG, ALERT, DIET, CARE, EVID = "撞藥防錯", "就醫警訊", "飲食指引", "照護指引", "實證保健"


def _c(label, query, badge, expect):
    return {"label": label, "query": query, "badge": badge,
            "warning": badge in (DRUG, ALERT), "expect": expect}


CONDITION_CATEGORIES = [
    ("抗凝血", ["warfarin", "抗凝血", "可邁丁", "普栓達", "拜瑞妥", "艾必克凝", "阿斯匹靈", "aspirin", "保栓通", "plavix", "noac", "心房顫動"], [
        _c("抗凝血藥能吃納豆激酶嗎", "親友在吃抗凝血藥，可以吃納豆激酶嗎？會不會增加出血風險？", DRUG, ["lit_nattokinase_10"]),
        _c("抗凝血藥能吃魚油嗎", "親友在吃抗凝血藥，可以吃高濃度魚油或薑黃嗎？", DRUG, ["lit_omega3_02", "lit_curcumin_05"]),
        _c("抗凝血藥能吃銀杏嗎", "親友在吃抗凝血藥，可以吃銀杏改善循環嗎？", DRUG, ["lit_ginkgo_11"]),
        _c("抗凝血藥能喝蔓越莓嗎", "親友在吃抗凝血藥，可以喝高濃縮蔓越莓汁嗎？", DRUG, ["lit_cranberry_mannose_15"]),
        _c("頭痛能自己買止痛藥嗎", "親友在吃抗凝血藥，感冒頭痛可以自己買消炎止痛藥嗎？", DRUG, ["lit_cold_meds_32", "lit_nsaid_ckd_16"]),
        _c("膝蓋痛選哪種較安全", "親友在吃抗凝血藥又膝蓋痛，葡萄糖胺或 UC-II 比較安全嗎？", EVID, ["lit_glucosamine_07", "lit_ucii_12"]),
    ]),
    ("腎臟病", ["腎", "洗腎", "透析", "ckd"], [
        _c("腎病能吃止痛藥嗎", "腎功能不好的親友，可以自己吃布洛芬這類消炎止痛藥嗎？", DRUG, ["lit_nsaid_ckd_16"]),
        _c("腎友能用低鈉鹽嗎", "腎臟病親友想減鹽，可以改用低鈉鹽嗎？", DRUG, ["lit_ckd_diet_17", "lit_bp_diet_26"]),
        _c("高鉀高磷食物怎麼避", "腎臟病親友飲食要避開哪些高鉀、高磷的食物？", DIET, ["lit_ckd_diet_17"]),
        _c("腎友能吃楊桃嗎", "腎臟病親友可以吃楊桃或喝楊桃汁嗎？", DIET, ["lit_ckd_diet_17"]),
        _c("腎友營養品怎麼挑", "腎臟病親友還沒洗腎，一般高蛋白營養品可以喝嗎？", DIET, ["lit_ckd_diet_17"]),
        _c("腎友能吃中藥補品嗎", "腎臟病親友可以吃中草藥或親戚送的補品嗎？", DRUG, ["lit_ckd_diet_17"]),
    ]),
    ("糖尿病", ["糖尿", "血糖", "胰島素", "降糖", "metformin", "滅醣敏"], [
        _c("降糖藥能吃苦瓜胜肽嗎", "親友在吃降血糖藥，可以吃苦瓜胜肽或肉桂來控糖嗎？", DRUG, ["lit_glucose_supp_22"]),
        _c("低血糖要怎麼處理", "親友有糖尿病，低血糖會有哪些症狀？發生時要怎麼處理？", ALERT, ["lit_glucose_supp_22"]),
        _c("能喝含糖滋補飲嗎", "糖尿病親友可以喝蜂蜜水或含糖的滋補飲品嗎？", DIET, ["lit_glucose_supp_22"]),
        _c("腳有傷口怎麼照顧", "糖尿病親友腳有小傷口、手腳麻，平常要怎麼照顧？", CARE, ["lit_diabetes_foot_23"]),
        _c("手腳麻補B群有用嗎", "親友手腳末梢刺痛麻木，補充活性維生素 B 群（B1、B6、B12）有幫助嗎？", EVID, ["lit_vitamin_b_13"]),
        _c("眼睛保養葉黃素", "糖尿病親友想保養眼睛黃斑部，葉黃素怎麼挑？", EVID, ["lit_lutein_01"]),
    ]),
    ("高血壓", ["血壓", "脈優", "amlodipine", "losartan", "valsartan", "降壓"], [
        _c("降壓藥能吃葡萄柚嗎", "親友在吃降血壓藥，可以吃葡萄柚或喝葡萄柚汁嗎？", DRUG, ["lit_grapefruit_19"]),
        _c("高血壓能吃甘草嗎", "高血壓親友可以吃甘草、甘草喉糖或含甘草的中藥嗎？", DRUG, ["lit_bp_diet_26"]),
        _c("鼻塞能吃感冒藥嗎", "高血壓親友感冒鼻塞，可以吃綜合感冒藥嗎？", DRUG, ["lit_cold_meds_32"]),
        _c("高血壓飲食怎麼減鹽", "高血壓親友飲食要怎麼減鹽？得舒飲食怎麼吃？", DIET, ["lit_bp_diet_26"]),
        _c("高血壓適合什麼運動", "高血壓親友適合做什麼運動？強度要怎麼拿捏？", CARE, ["lit_exercise_25"]),
        _c("高血壓吃魚油有用嗎", "高血壓親友補充魚油對心血管有幫助嗎？", EVID, ["lit_omega3_02"]),
    ]),
    ("高血脂", ["血脂", "膽固醇", "三酸甘油", "statin", "立普妥", "冠脂妥", "降血脂"], [
        _c("降血脂藥能吃紅麴嗎", "親友在吃 Statin 降血脂藥，可以再吃紅麴保健品（Monacolin K）嗎？", DRUG, ["lit_red_yeast_09"]),
        _c("降血脂藥能吃葡萄柚嗎", "親友在吃降血脂藥，可以喝葡萄柚汁嗎？", DRUG, ["lit_grapefruit_19"]),
        _c("降脂藥肌肉痠補Q10", "親友吃降血脂藥後肌肉痠痛，補充輔酶 Q10 有幫助嗎？", EVID, ["lit_coq10_06"]),
        _c("膽固醇高怎麼吃", "親友膽固醇偏高，飲食和生活要怎麼調整？", DIET, ["lit_lipid_lifestyle_27"]),
        _c("三酸甘油脂高怎麼辦", "親友三酸甘油脂偏高，除了吃藥還能怎麼改善？", DIET, ["lit_lipid_lifestyle_27"]),
        _c("高血脂吃魚油有用嗎", "高血脂的親友適合補充 Omega-3 魚油（EPA／DHA）嗎？", EVID, ["lit_omega3_02"]),
    ]),
    ("心臟病", ["心臟", "心律", "心衰", "支架", "冠心", "心肌", "心絞痛"], [
        _c("哪些症狀要立刻就醫", "親友有心臟病，出現哪些症狀要立刻打 119？", ALERT, ["lit_heart_warning_24"]),
        _c("心臟病能吃感冒藥嗎", "心臟病親友感冒了，可以吃綜合感冒藥嗎？", DRUG, ["lit_cold_meds_32"]),
        _c("裝支架能做什麼運動", "心臟病或裝過支架的親友，適合做什麼運動？", CARE, ["lit_exercise_25"]),
        _c("心臟病飲食怎麼吃", "心臟病親友要怎麼減鹽？得舒飲食適合嗎？", DIET, ["lit_bp_diet_26", "lit_lipid_lifestyle_27"]),
        _c("心臟保養Q10有用嗎", "心臟病親友補充輔酶 Q10 有實證幫助嗎？", EVID, ["lit_coq10_06"]),
    ]),
    ("肝病", ["肝"], [
        _c("保健品會傷肝嗎", "肝功能不好的親友，吃保健品會不會增加肝臟負擔？", DRUG, ["lit_liver_28"]),
        _c("肝不好能吃普拿疼嗎", "肝功能不好的親友，感冒可以吃普拿疼嗎？劑量要注意什麼？", DRUG, ["lit_cold_meds_32", "lit_liver_28"]),
        _c("肝指數高能吃紅麴嗎", "肝指數偏高的親友可以吃紅麴保健品嗎？", DRUG, ["lit_red_yeast_09", "lit_liver_28"]),
        _c("脂肪肝怎麼改善", "親友有脂肪肝，飲食和生活要怎麼調整？", DIET, ["lit_liver_28"]),
    ]),
    ("癌症", ["癌", "化療", "放療", "腫瘤", "標靶"], [
        _c("化療能吃中藥補品嗎", "親友正在化療，可以吃保健品或中藥補身體嗎？", DRUG, ["lit_cancer_care_35"]),
        _c("化療能吃益生菌嗎", "親友正在化療，可以吃益生菌嗎？", DRUG, ["lit_cancer_care_35", "lit_probiotics_03"]),
        _c("化療沒食慾怎麼補", "化療期間食慾很差的親友，營養要怎麼補充？", DIET, ["lit_cancer_care_35"]),
        _c("治療後怎麼調養", "癌症術後或放療後的親友，日常調養要注意什麼？", CARE, ["lit_cancer_care_35"]),
    ]),
    ("懷孕哺乳", ["懷孕", "孕婦", "孕期", "產後", "哺乳", "坐月子"], [
        _c("孕期能吃Q10嗎", "懷孕的親友可以吃輔酶 Q10 或維生素 A 嗎？", DRUG, ["lit_pregnancy_34", "lit_coq10_06"]),
        _c("哺乳期吃藥要注意", "哺乳中的親友吃藥或保健品要注意什麼？", DRUG, ["lit_pregnancy_34"]),
        _c("懷孕怎麼補葉酸鐵", "懷孕的親友要怎麼補充葉酸和鐵？", EVID, ["lit_pregnancy_34"]),
        _c("產後怎麼補營養", "產後坐月子的親友，鐵和葉酸等營養要怎麼補充？", DIET, ["lit_pregnancy_34"]),
    ]),
    ("甲狀腺", ["甲狀腺", "levothyroxine", "昂特欣", "eltroxin"], [
        _c("甲狀腺藥和鈣片間隔", "親友吃甲狀腺藥，跟鈣片、鐵劑要間隔多久？", DRUG, ["lit_med_spacing_20"]),
        _c("甲狀腺藥能配胃藥嗎", "親友吃甲狀腺藥，同時有吃胃藥要注意什麼？", DRUG, ["lit_med_spacing_20"]),
    ]),
    ("痛風", ["痛風", "尿酸"], [
        _c("發作能自己吃止痛藥嗎", "痛風發作時，親友可以自己吃止痛藥嗎？", DRUG, ["lit_gout_18", "lit_nsaid_ckd_16"]),
        _c("痛風要避開哪些食物", "親友有痛風，飲食要避開哪些食物？", DIET, ["lit_gout_18"]),
        _c("痛風能喝酒或飲料嗎", "痛風的親友可以喝啤酒或含糖飲料嗎？", DIET, ["lit_gout_18"]),
        _c("酸櫻桃能降尿酸嗎", "酸櫻桃或芹菜籽保健品真的能降尿酸嗎？", EVID, ["lit_gout_18"]),
        _c("補維生素C能降尿酸嗎", "痛風親友補充維生素 C 可以降尿酸嗎？", EVID, ["lit_gout_18", "lit_immunity_33"]),
    ]),
    ("失智", ["失智", "記憶", "阿茲海默", "認知"], [
        _c("怎麼降低失智風險", "親友記憶力變差，生活上怎麼做能降低失智風險？", CARE, ["lit_dementia_29"]),
        _c("失智長輩防走失", "家中長輩有失智症狀，居家安全和防走失要注意什麼？", CARE, ["lit_dementia_29"]),
        _c("銀杏魚油能防失智嗎", "銀杏或魚油可以預防失智嗎？", EVID, ["lit_dementia_29"]),
    ]),
    ("帕金森", ["帕金森"], [
        _c("左多巴要怎麼吃", "帕金森氏症親友吃左多巴，跟吃飯的時間要怎麼安排？", DRUG, ["lit_parkinson_30"]),
        _c("帕金森能吃鐵劑嗎", "帕金森氏症親友需要補鐵，跟左多巴要間隔多久？", DRUG, ["lit_parkinson_30"]),
        _c("帕金森蛋白質怎麼吃", "帕金森氏症親友的飲食，蛋白質要怎麼吃？", DIET, ["lit_parkinson_30"]),
    ]),
    ("失眠", ["失眠", "睡", "安眠", "焦慮"], [
        _c("安眠藥能加助眠品嗎", "親友有吃安眠藥，可以再吃 GABA 或褪黑激素嗎？", DRUG, ["lit_sleep_meds_21", "lit_gaba_sesamin_08"]),
        _c("吃安眠藥夜間防跌", "親友吃安眠藥後半夜起床，要注意什麼？", CARE, ["lit_sleep_meds_21"]),
        _c("褪黑激素能自己買嗎", "在台灣褪黑激素可以自己買來吃嗎？", EVID, ["lit_sleep_meds_21"]),
        _c("淺眠能吃GABA嗎", "親友淺眠多夢，GABA 或芝麻素保健品有幫助嗎？", EVID, ["lit_gaba_sesamin_08"]),
        _c("睡不好穴位按摩", "親友失眠睡不好，有哪些穴位按摩和睡前放鬆方法？", CARE, ["symptom:insomnia"]),
    ]),
    ("腸胃", ["胃", "腸", "便秘", "消化", "逆流", "腹瀉"], [
        _c("胃藥和鈣片間隔多久", "親友有吃胃藥，跟鈣片、鐵劑要間隔多久？", DRUG, ["lit_med_spacing_20"]),
        _c("抗生素能配益生菌嗎", "親友在吃抗生素，可以同時吃益生菌嗎？", DRUG, ["lit_probiotics_03"]),
        _c("長期吃胃藥的影響", "親友長期吃胃藥，會影響營養吸收嗎？", DRUG, ["lit_gerd_31"]),
        _c("胃食道逆流怎麼吃", "胃食道逆流的親友，飲食和睡前要注意什麼？", DIET, ["lit_gerd_31"]),
        _c("便秘吃益生菌有用嗎", "親友常便秘，吃益生菌有幫助嗎？", EVID, ["lit_probiotics_03"]),
    ]),
    ("感冒免疫", ["感冒", "咳", "氣喘", "肺", "鼻炎", "流感", "免疫"], [
        _c("慢性病能吃感冒藥嗎", "有慢性病在吃藥的親友，可以自己買綜合感冒藥嗎？", DRUG, ["lit_cold_meds_32"]),
        _c("普拿疼一天能吃多少", "親友感冒發燒吃普拿疼，一天最多能吃多少？", DRUG, ["lit_cold_meds_32"]),
        _c("維生素C能防感冒嗎", "親友容易感冒，補充維生素 C 可以預防嗎？", EVID, ["lit_immunity_33"]),
        _c("要補維生素D或鋅嗎", "容易感冒的親友，需要補充維生素 D 或鋅嗎？", EVID, ["lit_immunity_33"]),
    ]),
    ("骨骼關節", ["關節", "膝", "退化", "骨", "肌少", "抽筋"], [
        _c("骨鬆藥和鈣片怎麼錯開", "親友吃骨質疏鬆藥，跟鈣片要怎麼錯開時間？", DRUG, ["lit_med_spacing_20"]),
        _c("關節痛能常吃止痛藥嗎", "親友關節痛，可以長期吃消炎止痛藥嗎？", DRUG, ["lit_nsaid_ckd_16"]),
        _c("膝蓋退化吃葡萄糖胺", "親友膝關節退化，吃葡萄糖胺有用嗎？", EVID, ["lit_glucosamine_07"]),
        _c("UC-II和葡萄糖胺差別", "UC-II 非變性二型膠原蛋白跟葡萄糖胺有什麼差別？", EVID, ["lit_ucii_12", "lit_glucosamine_07"]),
        _c("關節痛吃薑黃素有用嗎", "親友關節痛，吃薑黃素保健品有幫助嗎？", EVID, ["lit_curcumin_05"]),
        _c("骨鬆怎麼補鈣和D", "親友骨質疏鬆，檸檬酸鈣和維生素 D3 要怎麼補充？", EVID, ["lit_calcium_d3_04"]),
        _c("膝蓋痛熱敷與按摩", "親友膝蓋痛，居家可以怎麼熱敷和按摩舒緩？", CARE, ["symptom:knee_joint"]),
    ]),
    ("眼睛", ["眼", "視力", "黃斑", "白內障", "青光眼"], [
        _c("青光眼能吃感冒藥嗎", "有青光眼的親友，可以吃綜合感冒藥嗎？", DRUG, ["lit_cold_meds_32"]),
        _c("黃斑部葉黃素怎麼挑", "親友黃斑部退化，葉黃素和玉米黃素怎麼挑？", EVID, ["lit_lutein_01"]),
        _c("葉黃素一天吃多少", "葉黃素一天吃多少才適合？", EVID, ["lit_lutein_01"]),
        _c("眼睛乾澀怎麼舒緩", "親友眼睛乾澀、容易疲勞，居家可以怎麼舒緩？", CARE, ["symptom:eye_strain"]),
    ]),
    ("傷口", ["燙傷", "燒傷", "傷口", "創面", "術後", "褥瘡", "開刀"], [
        _c("有傷口能吃魚油嗎", "親友還在術後恢復期，可以吃 Omega-3 魚油或薑黃素嗎？會影響凝血嗎？", DRUG, ["lit_omega3_02", "lit_curcumin_05", "lit_zinc_wound_14"]),
        _c("術後能吃銀杏納豆嗎", "親友剛開完刀，可以吃銀杏或納豆激酶嗎？", DRUG, ["lit_ginkgo_11", "lit_nattokinase_10"]),
        _c("傷口癒合吃什麼", "親友有褥瘡或術後傷口癒合慢，要補充哪些營養？", EVID, ["lit_zinc_wound_14"]),
        _c("燙傷補鋅和蛋白質", "親友燙傷，補充鋅和蛋白質能幫助傷口癒合嗎？", EVID, ["lit_zinc_wound_14"]),
    ]),
    ("泌尿道", ["泌尿", "尿道", "頻尿", "膀胱"], [
        _c("吃蔓越莓要注意什麼", "親友有在吃藥，吃高濃縮蔓越莓要注意什麼？", DRUG, ["lit_cranberry_mannose_15"]),
        _c("蔓越莓能防尿道炎嗎", "親友常泌尿道感染，吃蔓越莓有幫助嗎？", EVID, ["lit_cranberry_mannose_15"]),
    ]),
    ("皮膚", ["皮膚", "濕疹", "異位性", "乾癢", "過敏"], [
        _c("過敏體質吃保健品", "過敏體質的親友吃保健品要注意什麼？", DRUG, ["lit_skin_care_36"]),
        _c("皮膚乾癢怎麼保濕", "親友皮膚乾癢、濕疹，日常要怎麼保濕？", CARE, ["lit_skin_care_36"]),
        _c("冬天皮膚癢怎麼辦", "長輩冬天皮膚很癢，洗澡和保養要注意什麼？", CARE, ["lit_skin_care_36"]),
    ]),
    ("疲勞", ["熬夜", "疲勞", "加班", "壓力", "上班族", "疲倦"], [
        _c("熬夜會傷肝嗎", "親友常熬夜，會傷肝嗎？需要吃護肝保健品嗎？", DIET, ["lit_liver_28"]),
        _c("常熬夜補B群有用嗎", "親友常熬夜容易疲勞，補充 B 群有幫助嗎？", EVID, ["lit_vitamin_b_13"]),
        _c("容易累補Q10有用嗎", "親友容易疲倦、體力差，補充輔酶 Q10 有幫助嗎？", EVID, ["lit_coq10_06"]),
        _c("肩頸痠痛怎麼舒緩", "親友久坐肩頸痠痛，有哪些伸展和熱敷方法？", CARE, ["symptom:neck_shoulder"]),
    ]),
]

# 沒有對應病況（例如「日常養生」）時的日常保養提問
DEFAULT_CHIPS = [
    _c("吃藥和保健品怎麼錯開", "長輩有吃藥也有吃保健品，要怎麼錯開時間？", DRUG, ["lit_med_spacing_20"]),
    _c("保健品吃太多會傷肝嗎", "長輩同時吃很多種保健品，會不會傷肝？", DRUG, ["lit_liver_28"]),
    _c("長輩骨質怎麼保養", "長輩想保養骨質，鈣和維生素 D 要怎麼補？", EVID, ["lit_calcium_d3_04"]),
    _c("長輩適合什麼運動", "長輩適合做什麼運動？一週要做多少？", CARE, ["lit_exercise_25"]),
    _c("眼睛保養葉黃素", "長輩想保養眼睛，葉黃素怎麼挑？", EVID, ["lit_lutein_01"]),
    _c("維生素C能防感冒嗎", "長輩容易感冒，補充維生素 C 可以預防嗎？", EVID, ["lit_immunity_33"]),
]

MAX_CHIPS = 8
_NEGATIONS = ("未", "無", "非", "沒有", "不是", "否認")


def _mentions(text: str, keyword: str) -> bool:
    """病況有提到關鍵字，且不是「無糖尿病」「沒有高血壓」這類否定說法"""
    start = text.find(keyword)
    while start != -1:
        before = text[max(0, start - 3):start]
        if not any(n in before for n in _NEGATIONS):
            return True
        start = text.find(keyword, start + 1)
    return False


def matched_categories(condition: str) -> List[str]:
    cond = (condition or "").lower()
    return [name for name, keywords, _ in CONDITION_CATEGORIES if any(_mentions(cond, k) for k in keywords)]


def get_clinical_rule_chips(condition: str = "日常養生", name: str = "親友") -> List[Dict[str, Any]]:
    return normalize_chips(_get_clinical_rule_chips(condition, name))


def _get_clinical_rule_chips(condition: str = "日常養生", name: str = "親友", keep_expect: bool = False) -> List[Dict[str, Any]]:
    """
    依病況挑出相關的快速提問：有多種病況時輪流各取一題（每類先放撞藥防錯題），
    讓每個病況都有代表題；病況對應不到時用日常保養題，題數不足時也以日常保養題補滿。
    """
    names = set(matched_categories(condition))
    groups = [chips for cat, _, chips in CONDITION_CATEGORIES if cat in names]

    picked: List[Dict[str, Any]] = []
    seen = set()
    depth = max((len(g) for g in groups), default=0)
    for i in range(depth):
        for g in groups:
            if i < len(g) and g[i]["label"] not in seen and len(picked) < MAX_CHIPS:
                seen.add(g[i]["label"])
                picked.append(g[i])
    for chip in DEFAULT_CHIPS:
        if len(picked) >= 6:
            break
        if chip["label"] not in seen:
            seen.add(chip["label"])
            picked.append(chip)

    result = []
    for chip in picked[:MAX_CHIPS]:
        c = dict(chip)
        if name and name != "親友":
            c["query"] = c["query"].replace("親友", name)
        if not keep_expect:
            c.pop("expect", None)
        result.append(c)
    return result


def generate_ai_recipient_chips(
    elder_name: str,
    elder_condition: str,
    api_key: Optional[str] = None,
    model: str = "gemini-1.5-flash"
) -> List[Dict[str, Any]]:
    """
    Track 2: AI-Powered Deep Profiling.
    Uses Gemini LLM to generate 6-8 tailored medical question & supplement check chips.
    Falls back gracefully to rich Track 1 clinical engine if API fails or key is missing.
    """
    gemini_key = api_key or os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            prompt = f"""你是一位臨床藥師與銀髮醫療營養照護專家。
請針對守護對象的稱呼與健康病況，為年輕子女生成 6 到 8 個「高實用度、具備臨床撞藥防錯與對症調理」的快速諮詢提問標籤。

【守護對象資訊】
- 稱呼：{elder_name}
- 健康狀況 / 慢性病史 / 傷病：{elder_condition}

【要求】
1. 嚴格輸出合法 JSON Array，格式為：
[
  {{
    "label": "短標籤名稱（不超過14字，如：⚠️ 抗凝血+納豆禁忌 或 💡 血糖偏高喝什麼？）",
    "query": "點擊後發送給 AI 諮詢的完整詳細問題（約20~40字）",
    "badge": "類別小標籤（例如：TFDA警示 / 臨床指引 / 對症舒緩 / 藥局首選 / 撞藥防錯）"
  }}
]
2. 必須精準針對【{elder_condition}】的禁忌、常見併發症、以及臺灣連鎖藥局常見合格補品進行提問。
3. 若含有心血管、降血壓、抗凝血、糖尿病、痛風等，必須包含至少 2 題 TFDA 藥物交互作用撞藥防錯題！
4. 嚴格僅輸出 JSON Array，勿輸出任何其他 Markdown 或解釋文字。
"""
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.4,
                    "maxOutputTokens": 600
                }
            }
            res = requests.post(url, json=payload, timeout=8)
            if res.status_code == 200:
                res_data = res.json()
                raw_text = res_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                clean_json_str = raw_text.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(clean_json_str)
                if isinstance(parsed, list) and len(parsed) >= 4:
                    formatted = []
                    for item in parsed:
                        if "label" in item and "query" in item:
                            formatted.append({
                                "label": str(item["label"]).strip(),
                                "query": str(item["query"]).strip(),
                                "badge": str(item.get("badge", "AI推薦")).strip()
                            })
                    if len(formatted) >= 4:
                        return normalize_chips(formatted[:8])
        except Exception as e:
            print("Notice: AI chips generation fallback to clinical rules:", e)

    # Fallback to Track 1 deterministic clinical engine
    return get_clinical_rule_chips(condition=elder_condition, name=elder_name)
