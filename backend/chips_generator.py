import os
import json
import requests
from typing import List, Dict, Any, Optional

# Track 1: Fast Clinical Knowledge Base Mapping (0-delay deterministic clinical tags)
CLINICAL_DISEASE_TAGS_MAP = {
    "warfarin": [
        {"label": "⚠️ 抗凝血+納豆禁忌(TFDA)", "query": "吃抗凝血藥Warfarin可以吃納豆激酶嗎？有什麼出血風險？", "badge": "TFDA禁忌"},
        {"label": "⚠️ 魚油/銀杏出血風險", "query": "吃Warfarin可以吃高濃度魚油或銀杏嗎？需要停用嗎？", "badge": "撞藥警示"},
        {"label": "膝關節無力卡卡(ESCEO)", "query": "親友膝蓋關節痛，吃硫酸鹽葡萄糖胺會影響血壓或抗凝血藥嗎？", "badge": "臨床指引"},
        {"label": "半夜小腿抽筋補鈣(NOF)", "query": "親友半夜小腿容易抽筋，高血壓與服用抗凝血藥物補鈣推薦哪種？", "badge": "對症舒緩"},
        {"label": "失眠睡不好吃什麼？", "query": "親友高血壓失眠睡不好，吃GABA或芝麻素安全嗎？會撞藥嗎？", "badge": "安全評估"},
        {"label": "桂格完膳零撞藥滋補", "query": "桂格完膳無糖高鈣配方適合高血壓且吃抗凝血藥的親友嗎？", "badge": "藥局推薦"},
        {"label": "挺立關鍵UC-II安全檢驗", "query": "挺立關鍵UC-II非變性二型膠原蛋白，心血管患者能安心吃嗎？", "badge": "實證檢驗"}
    ],
    "血壓": [
        {"label": "⚠️ 降壓藥與紅麴交互作用", "query": "吃降血壓藥或降血脂藥可以吃紅麴嗎？TFDA有沒有警示？", "badge": "TFDA警示"},
        {"label": "輔酶Q10心血管保養", "query": "高血壓親友補充輔酶Q10有幫助嗎？會不會影響降血壓藥？", "badge": "心血管"},
        {"label": "半夜小腿抽筋補鈣鎂", "query": "高血壓親友夜間腳抽筋，補充檸檬酸鈣與鎂安全嗎？", "badge": "對症舒緩"},
        {"label": "深海魚油EPA/DHA挑選", "query": "高血壓親友吃深海魚油，EPA與DHA該怎麼選？", "badge": "實證檢驗"},
        {"label": "親友失眠睡不好吃什麼？", "query": "高血壓親友失眠淺眠，吃什麼保健品溫和放鬆不傷心血管？", "badge": "安全評估"},
        {"label": "低鈉低鉀營養飲推薦", "query": "高血壓患者平時滋補，有推薦哪些低鈉無負擔的營養素嗎？", "badge": "營養指引"}
    ],
    "糖": [
        {"label": "💡 高血糖吃什麼保健品安全？", "query": "親友血糖偏高，吃什麼保健品安全？有哪些成分不能碰？", "badge": "對症指南"},
        {"label": "⚠️ 苦瓜胜肽+降糖藥(TFDA)", "query": "吃降血糖藥可以吃苦瓜胜肽嗎？會不會造成低血糖危險？", "badge": "TFDA警示"},
        {"label": "⚠️ 糖尿病可以吃紅麴嗎？", "query": "糖尿病患者可以吃紅麴降血脂嗎？有撞藥或肝腎風險嗎？", "badge": "撞藥防錯"},
        {"label": "桂格完膳無糖低GI(藥局)", "query": "桂格完膳無糖低GI高鈣配方適合糖尿病親友當早餐或點心嗎？", "badge": "藥局首選"},
        {"label": "手腳末梢麻木保養", "query": "糖尿病親友手腳末梢神經麻木、血液循環差，補充B群或硫辛酸有用嗎？", "badge": "症狀舒緩"},
        {"label": "視網膜與葉黃素AREDS 2", "query": "糖尿病親友眼睛視網膜與黃斑部保養，AREDS 2指引葉黃素怎麼挑？", "badge": "視力保健"},
        {"label": "鉻酵母與胰島素敏感度", "query": "糖尿病親友補充微量元素鉻酵母，對維持醣類正常代謝有幫助嗎？", "badge": "實證檢驗"}
    ],
    "燙傷": [
        {"label": "🩹 燙傷創面組織修復指南", "query": "手部燙傷創面吃什麼加速皮膚組織修復與長肉？", "badge": "創面修復"},
        {"label": "膠原蛋白胜肽傷口癒合", "query": "燙傷傷口癒合期吃水解膠原蛋白胜肽有效嗎？", "badge": "組織再生"},
        {"label": "維生素C + 鋅加速癒合", "query": "燙傷創面需要補充高劑量維生素C和鋅嗎？臨床指引建議？", "badge": "臨床指引"},
        {"label": "除疤凝膠與外用敷料推薦", "query": "燙傷創面表皮癒合後的除疤凝膠與矽膠貼片怎麼挑選？", "badge": "藥局衛教"},
        {"label": "高蛋白滋補飲品挑選", "query": "傷口創面組織修復期，有哪些低刺激高蛋白飲品推薦？", "badge": "營養補充"},
        {"label": "創面飲食抗發炎與禁忌", "query": "皮膚燙傷創面飲食有哪些發物禁忌？咖啡或辣的能吃嗎？", "badge": "飲食禁忌"}
    ],
    "傷": [
        {"label": "🩹 傷口組織修復營養", "query": "外傷創面加速癒合修復，吃什麼營養品最有效？", "badge": "創傷修復"},
        {"label": "膠原蛋白+維生素C", "query": "傷口癒合期間補充膠原蛋白與維生素C能加速長肉嗎？", "badge": "組織再生"},
        {"label": "避免色素沉澱抗痕指南", "query": "受傷創面如何避免色素沉澱與留疤？保健品與外用藥膏建議？", "badge": "對症指南"},
        {"label": "高純度左旋麩醯胺酸", "query": "傷口組織修復吃左旋麩醯胺酸(Glutamine)有幫助嗎？", "badge": "臨床指引"}
    ],
    "關節": [
        {"label": "膝關節卡卡無力(ESCEO)", "query": "親友膝關節退化卡卡無力，ESCEO骨關節醫學會指引首選吃什麼？", "badge": "臨床首選"},
        {"label": "挺立UC-II與葡萄糖胺", "query": "挺立關鍵UC-II非變性二型膠原蛋白跟葡萄糖胺有何差別？哪個有效？", "badge": "實證比較"},
        {"label": "硫酸鹽葡萄糖胺(藥品級)", "query": "結晶型硫酸鹽葡萄糖胺跟一般食品級鹽酸鹽葡萄糖胺吸收率差別？", "badge": "藥局推薦"},
        {"label": "檸檬酸鈣+維生素D3(NOF)", "query": "美國骨質疏鬆學會NOF建議：檸檬酸鈣加D3如何幫助骨質密度？", "badge": "骨密指引"},
        {"label": "肌少症乳清蛋白補充", "query": "親友走路無力容易跌倒，肌少症補充哪種蛋白質最容易吸收？", "badge": "肌力維護"},
        {"label": "半夜小腿抽筋補鈣鎂", "query": "親友半夜常因關節或小腿抽筋痛醒，如何補充鈣鎂？", "badge": "對症舒緩"}
    ],
    "骨": [
        {"label": "骨質疏鬆補鈣防跌指引", "query": "親友骨質密度低、容易骨折，補鈣與維生素D3臨床最新指引？", "badge": "骨密指引"},
        {"label": "骨折術後加速骨痂生長", "query": "親友骨折術後調養，吃什麼能加速骨痂形成與骨骼癒合？", "badge": "術後調養"},
        {"label": "挺立高鈣錠+活性D3", "query": "挺立高鈣強力錠配合活性D3對親友吸收率好嗎？會引起便秘嗎？", "badge": "實證檢驗"},
        {"label": "非變性二型膠原蛋白UC-II", "query": "保護骨關節與軟骨韌性，UC-II每天建議劑量是多少？", "badge": "臨床推薦"}
    ],
    "失眠": [
        {"label": "親友失眠睡不好吃什麼？", "query": "親友長期失眠、淺眠多夢，吃什麼保健品溫和安全不依賴？", "badge": "好眠推薦"},
        {"label": "三得利芝麻明EX+GABA", "query": "三得利芝麻明EX結合GABA，對改善中老年人淺眠睡眠品質有效嗎？", "badge": "實證檢驗"},
        {"label": "鈣鎂黃金比例幫助入睡", "query": "睡前補充檸檬酸鈣加鎂，有助於中樞神經放鬆與肌肉舒緩嗎？", "badge": "神經放鬆"},
        {"label": "⚠️ 安眠藥與保健品撞藥", "query": "親友如果有吃西藥安眠藥或抗焦慮藥，可以吃GABA或褪黑激素嗎？", "badge": "撞藥防錯"}
    ],
    "眼": [
        {"label": "游離型葉黃素AREDS 2", "query": "親友眼睛老化、黃斑部模糊，符合NIH AREDS 2指引葉黃素怎麼挑？", "badge": "AREDS 2"},
        {"label": "玉米黃素黃金比例10:2", "query": "葉黃素跟玉米黃素黃金比例10:2對抗藍光與水晶體抗氧化有何實證？", "badge": "實證檢驗"},
        {"label": "白內障保養與抗氧化營養", "query": "親友有輕微白內障，補充蝦紅素或花青素對眼睛微血管循環有用嗎？", "badge": "對症指引"}
    ],
    "痛風": [
        {"label": "⚠️ 痛風高尿酸飲食禁忌", "query": "親友尿酸過高容易痛風發作，有哪些保健食品和補品絕對不能吃？", "badge": "飲食禁忌"},
        {"label": "酸櫻桃萃取與尿酸代謝", "query": "酸櫻桃萃取物或芹菜籽對輔助尿酸代謝有醫學實證嗎？", "badge": "實證檢驗"},
        {"label": "痛風親友降發炎保健推薦", "query": "痛風發作期關節紅腫熱痛，日常有哪些溫和抗發炎營養素？", "badge": "發炎舒緩"}
    ],
    "血脂": [
        {"label": "⚠️ 降血脂藥+紅麴重複成分", "query": "親友有吃降血脂藥（Statin），可以再吃紅麴嗎？會不會重複劑量傷肝或肌肉？", "badge": "撞藥防錯"},
        {"label": "高膽固醇飲食怎麼吃？", "query": "親友膽固醇偏高，日常飲食與烹調方式要注意什麼？", "badge": "飲食指引"},
        {"label": "魚油與植物固醇挑選", "query": "高血脂的親友適合吃魚油或植物固醇嗎？怎麼挑比較安全？", "badge": "實證檢驗"},
        {"label": "三酸甘油脂偏高怎麼辦", "query": "親友三酸甘油脂偏高，除了吃藥以外生活上可以怎麼改善？", "badge": "對症指南"}
    ],
    "腎": [
        {"label": "⚠️ 腎臟病止痛藥禁忌", "query": "腎功能不好的親友可以吃市售止痛藥（NSAID）嗎？有什麼風險？", "badge": "撞藥防錯"},
        {"label": "⚠️ 腎友保健品要避開什麼", "query": "慢性腎臟病親友吃保健品要特別避開哪些成分？", "badge": "TFDA警示"},
        {"label": "低蛋白飲食與營養補充", "query": "慢性腎臟病親友需要控制蛋白質，營養品要怎麼挑選？", "badge": "營養指引"},
        {"label": "高鉀高磷食物怎麼避", "query": "腎臟病親友飲食要注意哪些高鉀、高磷的食物？", "badge": "飲食禁忌"}
    ],
    "心臟": [
        {"label": "⚠️ 心臟病用藥與保健品", "query": "親友有心臟病在服藥，吃保健品前要注意哪些交互作用？", "badge": "撞藥防錯"},
        {"label": "輔酶Q10對心臟有幫助嗎", "query": "心臟病或裝支架的親友補充輔酶Q10有實證幫助嗎？", "badge": "實證檢驗"},
        {"label": "心臟病適合的運動強度", "query": "心臟病親友適合做什麼運動？強度要怎麼拿捏？", "badge": "臨床指引"},
        {"label": "胸悶喘不過氣何時就醫", "query": "親友有心臟病，出現哪些症狀需要立刻就醫？", "badge": "安全評估"}
    ],
    "肝": [
        {"label": "⚠️ 保健品會不會傷肝？", "query": "肝功能不好的親友吃保健品，有哪些成分可能加重肝臟負擔？", "badge": "撞藥防錯"},
        {"label": "脂肪肝飲食與生活調整", "query": "親友有脂肪肝，飲食和生活習慣要怎麼調整？", "badge": "對症指南"},
        {"label": "B群與護肝產品挑選", "query": "常熬夜或肝指數偏高的親友，B群或護肝產品怎麼挑？", "badge": "實證檢驗"}
    ],
    "失智": [
        {"label": "預防失智的生活習慣", "query": "親友記憶力變差，有哪些生活習慣有助於延緩失智？", "badge": "臨床指引"},
        {"label": "銀杏與魚油對記憶力", "query": "銀杏或魚油對親友記憶力有實證幫助嗎？會跟其他藥物衝突嗎？", "badge": "實證檢驗"},
        {"label": "居家防走失與安全", "query": "家中親友有失智症狀，居家安全與防走失要注意什麼？", "badge": "照護指引"},
        {"label": "帕金森氏症營養照護", "query": "帕金森氏症親友吃藥期間，飲食與蛋白質攝取要注意什麼？", "badge": "營養指引"}
    ],
    "腸胃": [
        {"label": "便秘吃什麼比較好？", "query": "親友長期便秘，飲食、益生菌或纖維補充品怎麼選比較溫和？", "badge": "腸道健康"},
        {"label": "⚠️ 胃藥與保健品間隔", "query": "親友有吃胃藥（制酸劑），跟鈣片、鐵劑等保健品要間隔多久？", "badge": "撞藥防錯"},
        {"label": "胃食道逆流飲食禁忌", "query": "胃食道逆流的親友平常飲食要避開哪些東西？", "badge": "飲食禁忌"},
        {"label": "腸胃敏感益生菌挑選", "query": "腸胃敏感、容易拉肚子的親友，益生菌要怎麼挑？", "badge": "實證檢驗"}
    ],
    "呼吸": [
        {"label": "感冒期間吃什麼恢復快", "query": "親友感冒中，飲食與營養補充有什麼建議？", "badge": "對症舒緩"},
        {"label": "⚠️ 感冒藥與慢性病用藥", "query": "有慢性病在吃藥的親友，可以自行吃市售感冒藥嗎？", "badge": "撞藥防錯"},
        {"label": "提升免疫力保健品", "query": "親友容易感冒，維生素C、D或鋅等保健品有實證幫助嗎？", "badge": "實證檢驗"},
        {"label": "氣喘或過敏性鼻炎保養", "query": "有氣喘或過敏性鼻炎的親友，換季時居家要怎麼保養？", "badge": "照護指引"}
    ],
    "疲勞": [
        {"label": "常熬夜要補什麼？", "query": "親友工作常熬夜加班，B群、魚油或其他保健品該怎麼補？", "badge": "元氣補充"},
        {"label": "⚠️ 提神飲料與咖啡因", "query": "親友每天喝很多提神飲料或咖啡，對身體有什麼影響？", "badge": "安全評估"},
        {"label": "壓力大睡不好怎麼調整", "query": "親友壓力大、睡眠品質差，生活上可以怎麼調整？", "badge": "對症指南"},
        {"label": "久坐肩頸痠痛舒緩", "query": "上班族親友久坐肩頸痠痛，有哪些伸展或保健方式？", "badge": "症狀舒緩"}
    ],
    "癌症": [
        {"label": "⚠️ 化療期間保健品禁忌", "query": "親友正在化療，哪些保健品或中藥可能影響治療效果？", "badge": "撞藥防錯"},
        {"label": "化療期間營養補充", "query": "化療期間食慾差的親友，營養品與飲食要怎麼安排？", "badge": "營養指引"},
        {"label": "術後與放療後調養", "query": "癌症術後或放療後的親友，日常調養與營養補充有什麼建議？", "badge": "術後調養"}
    ],
    "孕產": [
        {"label": "⚠️ 孕期保健品要避開什麼", "query": "懷孕的親友吃保健品，有哪些成分要避免？葉酸要怎麼補？", "badge": "安全評估"},
        {"label": "孕期營養補充重點", "query": "懷孕期間鐵、鈣、DHA 要怎麼補充比較適合？", "badge": "營養指引"},
        {"label": "產後坐月子調養", "query": "產後的親友坐月子期間，飲食與營養補充有什麼建議？", "badge": "照護指引"},
        {"label": "哺乳期用藥與保健品", "query": "哺乳中的親友吃藥或保健品要注意什麼？", "badge": "撞藥防錯"}
    ],
    "皮膚": [
        {"label": "濕疹乾癢保濕照護", "query": "親友有濕疹或皮膚乾癢，日常保濕與飲食要注意什麼？", "badge": "對症舒緩"},
        {"label": "⚠️ 過敏體質保健品挑選", "query": "過敏體質的親友吃保健品，要注意哪些可能的過敏原？", "badge": "安全評估"},
        {"label": "膠原蛋白對皮膚有用嗎", "query": "膠原蛋白或維生素C對親友皮膚健康有實證幫助嗎？", "badge": "實證檢驗"}
    ],
    "default": [
        {"label": "銀髮綜合維他命挑選", "query": "銀髮親友日常保養，綜合維他命該怎麼挑選最均衡安全？", "badge": "日常保養"},
        {"label": "Costco 深海魚油 (EPA/DHA)", "query": "親友保養心血管與大腦，Costco深海魚油好嗎？rTG型態差別？", "badge": "外購檢驗"},
        {"label": "肩頸痠痛肌肉僵硬舒緩", "query": "親友肩頸經常痠痛僵硬，補充高單位B群還是外用貼布有效？", "badge": "症狀舒緩"},
        {"label": "提升元氣消除疲勞首選", "query": "親友容易疲勞、體力變差，適合補充什麼滋補營養品？", "badge": "元氣補充"},
        {"label": "益生菌調節腸道與免疫(WGO)", "query": "世界胃腸病學組織WGO指引：親友日常補充益生菌能改善消化嗎？", "badge": "腸道健康"},
        {"label": "半夜小腿抽筋補鈣鎂", "query": "親友半夜睡覺小腿容易抽筋，該補充鈣還是鎂？", "badge": "對症舒緩"}
    ]
}

def get_clinical_rule_chips(condition: str = "日常養生", name: str = "親友") -> List[Dict[str, Any]]:
    """
    Track 1: Instantly matches the condition string to high-relevance clinical question chips.
    Returns 6 to 8 tailored chips with zero latency.
    """
    cond_clean = (condition or "").lower().strip()
    matched_chips: List[Dict[str, Any]] = []

    # Priority matching
    if "warfarin" in cond_clean or "抗凝血" in cond_clean:
        matched_chips.extend(CLINICAL_DISEASE_TAGS_MAP["warfarin"])
    elif "血壓" in cond_clean or "心血管" in cond_clean:
        matched_chips.extend(CLINICAL_DISEASE_TAGS_MAP["血壓"])
    
    if "糖" in cond_clean or "低gi" in cond_clean or "胰島素" in cond_clean:
        matched_chips.extend(CLINICAL_DISEASE_TAGS_MAP["糖"])

    if "燙傷" in cond_clean or "燒傷" in cond_clean:
        matched_chips.extend(CLINICAL_DISEASE_TAGS_MAP["燙傷"])
    elif "傷" in cond_clean or "創面" in cond_clean or "術後" in cond_clean:
        matched_chips.extend(CLINICAL_DISEASE_TAGS_MAP["傷"])

    if "膝" in cond_clean or "關節" in cond_clean or "退化" in cond_clean or "軟骨" in cond_clean:
        matched_chips.extend(CLINICAL_DISEASE_TAGS_MAP["關節"])
    
    if "骨" in cond_clean or "骨折" in cond_clean or "肌少" in cond_clean or "抽筋" in cond_clean:
        matched_chips.extend(CLINICAL_DISEASE_TAGS_MAP["骨"])

    if "眠" in cond_clean or "睡" in cond_clean or "焦慮" in cond_clean:
        matched_chips.extend(CLINICAL_DISEASE_TAGS_MAP["失眠"])

    if "眼" in cond_clean or "視力" in cond_clean or "黃斑" in cond_clean or "白內障" in cond_clean:
        matched_chips.extend(CLINICAL_DISEASE_TAGS_MAP["眼"])

    if "痛風" in cond_clean or "尿酸" in cond_clean:
        matched_chips.extend(CLINICAL_DISEASE_TAGS_MAP["痛風"])

    # 擴充疾病類型（關鍵字 → 晶片分類）
    for keywords, map_key in [
        (("血脂", "膽固醇", "三酸甘油", "statin"), "血脂"),
        (("腎", "洗腎", "透析", "ckd"), "腎"),
        (("心臟", "心律", "心衰", "支架", "冠心"), "心臟"),
        (("肝",), "肝"),
        (("失智", "記憶", "帕金森", "阿茲海默"), "失智"),
        (("胃", "腸", "便秘", "消化", "逆流", "腹瀉"), "腸胃"),
        (("感冒", "咳", "氣喘", "肺", "鼻炎", "免疫", "流感"), "呼吸"),
        (("熬夜", "疲勞", "加班", "壓力", "上班族", "累"), "疲勞"),
        (("癌", "化療", "放療", "腫瘤"), "癌症"),
        (("懷孕", "孕", "產後", "哺乳", "坐月子"), "孕產"),
        (("皮膚", "濕疹", "異位性", "過敏", "乾癢"), "皮膚"),
    ]:
        if any(k in cond_clean for k in keywords):
            matched_chips.extend(CLINICAL_DISEASE_TAGS_MAP[map_key])

    # Remove duplicate labels
    seen_labels = set()
    unique_chips = []
    for chip in matched_chips:
        if chip["label"] not in seen_labels:
            seen_labels.add(chip["label"])
            # Personalize query with recipient name
            c = dict(chip)
            if "親友" in c["query"] and name and name != "親友":
                c["query"] = c["query"].replace("親友", name)
            unique_chips.append(c)

    # If too few chips, top up with default general care chips
    if len(unique_chips) < 6:
        for chip in CLINICAL_DISEASE_TAGS_MAP["default"]:
            if chip["label"] not in seen_labels:
                seen_labels.add(chip["label"])
                c = dict(chip)
                if "親友" in c["query"] and name and name != "親友":
                    c["query"] = c["query"].replace("親友", name)
                unique_chips.append(c)
            if len(unique_chips) >= 7:
                break

    return unique_chips[:8]

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
                        return formatted[:8]
        except Exception as e:
            print("Notice: AI chips generation fallback to clinical rules:", e)

    # Fallback to Track 1 deterministic clinical engine
    return get_clinical_rule_chips(condition=elder_condition, name=elder_name)
