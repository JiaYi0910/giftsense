"""
用藥安全與照護指引（2026/10/15 擴充）

原本 15 篇文獻都是「保健成分」，快速提問裡常見的腎臟病止痛藥、痛風飲食、失智照護等問題
找不到對應資料，AI 守護助理只能拿最接近的保健品文獻回答。這裡補上各病症的用藥安全、
飲食與照護指引，內容整理自各機構公開的臨床指引與衛教資料。

這三類（GUIDANCE_CATEGORIES）不是保健品，回答時以「指引重點」呈現，不推薦商品。
"""
from typing import Any, Dict, List

GUIDANCE_CATEGORIES = {"用藥安全", "飲食照護", "照護指引"}

GUIDANCE_LITERATURES: List[Dict[str, Any]] = [
    {
        "id": "lit_nsaid_ckd_16",
        "title": "慢性腎臟病與非類固醇消炎止痛藥（NSAIDs）用藥安全",
        "authority": "KDIGO 慢性腎臟病臨床指引",
        "category": "用藥安全",
        "ingredient": "非類固醇消炎止痛藥 NSAIDs（布洛芬 Ibuprofen、萘普生 Naproxen 等）",
        "evidenceLevel": "臨床指引建議",
        "recommendedDose": "腎功能不全者避免自行長期服用 NSAIDs；需要止痛時先詢問醫師，乙醯胺酚（普拿疼）在建議劑量內相對安全",
        "mechanism": "NSAIDs 會抑制腎臟的前列腺素，減少腎臟血流，可能使腎功能惡化、造成水腫與高血鉀；與降血壓藥（ACEI／ARB）或利尿劑一起使用時風險更高。",
        "contraindications": "慢性腎臟病、洗腎、心衰竭，以及正在服用 ACEI／ARB、利尿劑者，避免自行購買消炎止痛藥；有胃潰瘍病史者也應避免。",
        "targetSymptoms": ["腎臟病止痛藥", "腎功能不好吃止痛藥", "洗腎", "慢性腎臟病", "消炎止痛藥", "布洛芬", "關節痛止痛"],
        "citation": "KDIGO 2012 Clinical Practice Guideline for the Evaluation and Management of Chronic Kidney Disease. Kidney Int Suppl. 2013;3(1):1-150."
    },
    {
        "id": "lit_ckd_diet_17",
        "title": "慢性腎臟病飲食：蛋白質、電解質與營養品選擇",
        "authority": "美國國家腎臟基金會 KDOQI 營養指引",
        "category": "飲食照護",
        "ingredient": "腎臟病飲食（蛋白質、電解質與磷的控制）",
        "evidenceLevel": "臨床指引建議",
        "recommendedDose": "未洗腎者通常需要限制蛋白質，洗腎後反而需要增加，實際份量依醫師或營養師評估；營養品請選腎臟病專用配方",
        "mechanism": "腎功能下降時，鉀、磷與蛋白質代謝產物不容易排出。血鉀太高可能引起心律不整，磷太高會造成皮膚癢與骨骼病變。楊桃含有對腎友有神經毒性的物質，腎臟病患者應完全避免。",
        "contraindications": "腎友不要吃楊桃；以鉀取代鈉的低鈉鹽不適合腎友；來路不明的中草藥與補品可能傷腎；一般高蛋白營養品不一定適合未洗腎的腎友。",
        "targetSymptoms": ["腎臟病飲食", "高鉀食物", "高磷食物", "腎友營養品", "低蛋白飲食", "洗腎飲食", "楊桃", "腎友補品"],
        "citation": "Ikizler TA, et al. KDOQI Clinical Practice Guideline for Nutrition in CKD: 2020 Update. Am J Kidney Dis. 2020;76(3 Suppl 1):S1-S107."
    },
    {
        "id": "lit_gout_18",
        "title": "痛風與高尿酸：飲食、生活與保健品",
        "authority": "美國風濕病學會（ACR）痛風管理指引",
        "category": "飲食照護",
        "ingredient": "高尿酸飲食控制（低普林飲食）",
        "evidenceLevel": "臨床指引建議",
        "recommendedDose": "沒有限水的疾病時多喝水；限制酒精（尤其啤酒）、含糖飲料與高果糖、內臟與帶殼海鮮；體重過重者逐步減重",
        "mechanism": "尿酸是普林代謝後的產物，尿酸過高會在關節形成結晶而引發痛風。酒精與果糖會增加尿酸生成並減少排出。降尿酸藥物需要長期規律服用，不要因為不痛就自行停藥。",
        "contraindications": "ACR 指引不建議以補充維生素 C 來降尿酸；酸櫻桃、芹菜籽等保健品證據有限，不能取代藥物；痛風發作時不要自行大量服用止痛藥，腎功能不好者尤其要先問醫師。",
        "targetSymptoms": ["痛風", "尿酸過高", "高尿酸", "普林", "痛風飲食", "關節紅腫熱痛", "酸櫻桃", "痛風喝酒"],
        "citation": "FitzGerald JD, et al. 2020 American College of Rheumatology Guideline for the Management of Gout. Arthritis Care Res. 2020;72(6):744-760."
    },
    {
        "id": "lit_grapefruit_19",
        "title": "葡萄柚與降血壓藥、降血脂藥的交互作用",
        "authority": "美國 FDA 消費者衛教 & 加拿大醫學會期刊（CMAJ）回顧",
        "category": "用藥安全",
        "ingredient": "葡萄柚與葡萄柚汁（呋喃香豆素）",
        "evidenceLevel": "藥物動力學研究與臨床回顧",
        "recommendedDose": "服用部分降血壓藥（鈣離子阻斷劑如 felodipine、nifedipine）、部分降血脂藥（simvastatin、atorvastatin）時，避免吃葡萄柚與喝葡萄柚汁",
        "mechanism": "葡萄柚中的呋喃香豆素會抑制腸道的 CYP3A4 酵素，讓部分藥物吸收變多、血中濃度升高，可能造成血壓過低、頭暈或肌肉病變；作用可持續一天以上，錯開時間吃也無法避免。",
        "contraindications": "柳丁、橘子通常沒有相同作用；文旦等柚類也可能含有呋喃香豆素，服用上述藥物者先詢問藥師。",
        "targetSymptoms": ["葡萄柚", "葡萄柚汁", "降血壓藥", "降血脂藥", "柚子", "文旦", "藥物交互作用"],
        "citation": "U.S. FDA Consumer Update: Grapefruit Juice and Some Drugs Don't Mix; Bailey DG, et al. Grapefruit-medication interactions. CMAJ. 2013;185(4):309-316."
    },
    {
        "id": "lit_med_spacing_20",
        "title": "鈣片、鐵劑、胃藥與藥物的服用間隔",
        "authority": "美國 NIH 膳食補充品辦公室（ODS）& 藥品仿單",
        "category": "用藥安全",
        "ingredient": "鈣、鐵、鎂、制酸劑（胃藥）與藥物間隔",
        "evidenceLevel": "藥品仿單與官方衛教",
        "recommendedDose": "甲狀腺素（Levothyroxine）與鈣片、鐵劑、胃藥至少間隔 4 小時；四環黴素、氟喹諾酮類抗生素與鈣、鐵、鎂、鋅依仿單間隔 2–6 小時；鈣和鐵分開吃",
        "mechanism": "鈣、鐵、鎂、鋁等金屬離子會在腸道和部分藥物結合，降低藥物吸收，讓甲狀腺藥或抗生素的效果變差。骨質疏鬆藥（雙磷酸鹽類）需要空腹服用，服藥後要等一段時間才能吃東西或鈣片。",
        "contraindications": "正在吃甲狀腺藥、抗生素或骨質疏鬆藥時，補充鈣、鐵前先問藥師要怎麼錯開時間。",
        "targetSymptoms": ["胃藥", "制酸劑", "鈣片間隔", "鐵劑", "甲狀腺藥", "抗生素", "吃藥間隔", "骨質疏鬆藥"],
        "citation": "NIH Office of Dietary Supplements. Calcium – Fact Sheet for Health Professionals; Levothyroxine Sodium Prescribing Information."
    },
    {
        "id": "lit_sleep_meds_21",
        "title": "安眠藥、抗焦慮藥與助眠保健品的併用安全",
        "authority": "美國睡眠醫學會（AASM）臨床指引",
        "category": "用藥安全",
        "ingredient": "鎮靜安眠藥的併用安全",
        "evidenceLevel": "臨床指引建議",
        "recommendedDose": "已經在吃鎮靜安眠藥（如 zolpidem、benzodiazepines）的人，不要自行再加助眠保健品；褪黑激素在台灣屬於藥品，需要由醫師開立",
        "mechanism": "多種助眠成分和鎮靜安眠藥同樣作用在中樞神經，一起使用可能加重嗜睡與頭暈，增加長輩夜間起床跌倒的風險；酒精也會加重這些作用。",
        "contraindications": "褪黑激素在台灣屬於藥品，需要醫師處方，不要自行購買來路不明的產品；服用安眠藥後不要喝酒；長輩夜間起床要開小夜燈、慢慢起身；停藥要依醫師指示逐步減量，不要自行突然停藥。",
        "targetSymptoms": ["安眠藥", "抗焦慮藥", "褪黑激素", "助眠保健品", "鎮靜劑", "夜間跌倒", "吃安眠藥"],
        "citation": "Sateia MJ, et al. Clinical Practice Guideline for the Pharmacologic Treatment of Chronic Insomnia in Adults: An AASM Clinical Practice Guideline. J Clin Sleep Med. 2017;13(2):307-349."
    },
    {
        "id": "lit_glucose_supp_22",
        "title": "降血糖藥與控糖保健品：低血糖風險",
        "authority": "美國糖尿病學會（ADA）糖尿病照護標準",
        "category": "用藥安全",
        "ingredient": "血糖調節保健品與低血糖預防",
        "evidenceLevel": "臨床指引建議",
        "recommendedDose": "正在使用降血糖藥或胰島素者，新增任何控糖保健品前先和醫師討論，並增加血糖監測",
        "mechanism": "ADA 照護標準指出，沒有缺乏的人補充維生素、礦物質（如鉻）或草本香料（如肉桂），目前沒有明確證據能改善血糖控制；部分成分和降血糖藥一起使用，可能加強降血糖作用而增加低血糖風險。",
        "contraindications": "出現冒冷汗、手抖、心悸、意識混亂等低血糖症狀時，先補充 15 克糖（如半杯果汁），15 分鐘後再測血糖；不要用保健品取代藥物；含糖滋補飲品與蜂蜜會讓血糖上升。",
        "targetSymptoms": ["降血糖藥", "控糖保健品", "苦瓜胜肽", "肉桂", "鉻", "低血糖", "胰島素", "血糖偏高", "蜂蜜"],
        "citation": "American Diabetes Association. Standards of Care in Diabetes—2024. Diabetes Care. 2024;47(Suppl 1)."
    },
    {
        "id": "lit_diabetes_foot_23",
        "title": "糖尿病足部照護與末梢神經病變",
        "authority": "國際糖尿病足工作小組（IWGDF）",
        "category": "照護指引",
        "ingredient": "糖尿病足部自我照護",
        "evidenceLevel": "臨床指引建議",
        "recommendedDose": "每天檢查雙腳有沒有傷口、水泡或顏色改變；穿合腳的鞋襪，不要赤腳走路；泡腳前先用手肘測水溫",
        "mechanism": "糖尿病神經病變會讓腳的感覺變遲鈍，小傷口不容易發現，加上循環較差，傷口容易感染、不易癒合。長期服用 metformin 可能使維生素 B12 下降而加重手腳麻，可請醫師檢查。",
        "contraindications": "腳上傷口紅腫、流膿或發黑時立即就醫；不要自行修剪雞眼或厚繭；使用電熱毯、熱敷墊要小心低溫燙傷。",
        "targetSymptoms": ["糖尿病足", "腳有傷口", "末梢神經", "手腳麻木", "傷口不易癒合", "metformin", "糖尿病腳"],
        "citation": "Schaper NC, et al. Practical guidelines on the prevention and management of diabetes-related foot disease (IWGDF 2023 update). Diabetes Metab Res Rev. 2024;40(3):e3657."
    },
    {
        "id": "lit_heart_warning_24",
        "title": "心臟病與中風的緊急警訊：何時要立刻就醫",
        "authority": "美國心臟學會（AHA）& 衛福部國民健康署",
        "category": "照護指引",
        "ingredient": "心肌梗塞與中風警訊",
        "evidenceLevel": "官方衛教",
        "recommendedDose": "胸痛或胸悶超過 5 分鐘、冒冷汗、喘、噁心，或痛感延伸到手臂、下巴；或突然臉歪、單側手腳無力、說話不清楚，立即撥打 119",
        "mechanism": "心肌梗塞與中風的治療有黃金時間，越早送醫越能保住心肌和腦部功能。長輩與糖尿病患者的症狀可能不典型，有時只有喘或異常疲倦。中風可用「微笑、舉手、說你好」快速辨識。",
        "contraindications": "不要等症狀自己緩解，也不要自行開車去醫院；醫師開過舌下含片者依指示使用。",
        "targetSymptoms": ["胸悶", "胸痛", "心臟病何時就醫", "喘不過氣", "中風徵兆", "心肌梗塞", "臉歪手無力"],
        "citation": "American Heart Association. Warning Signs of a Heart Attack; 衛福部國民健康署 中風衛教（微笑、舉手、說你好，打 119）。"
    },
    {
        "id": "lit_exercise_25",
        "title": "高血壓與心血管疾病的運動建議",
        "authority": "世界衛生組織（WHO）身體活動指引 & 美國心臟學會（AHA）",
        "category": "照護指引",
        "ingredient": "中等強度有氧運動與肌力訓練",
        "evidenceLevel": "臨床指引建議",
        "recommendedDose": "每週累積 150 分鐘中等強度有氧運動（快走、騎腳踏車），每週 2 天肌力訓練；強度以「可以說話但不能唱歌」為參考；長輩加入平衡訓練",
        "mechanism": "規律運動可以降低血壓、改善血脂與血糖，增加心肺功能；長輩做平衡與肌力訓練可以預防跌倒。",
        "contraindications": "心臟病、裝過支架或心衰竭的人，運動強度先和心臟科醫師討論，必要時參加心臟復健；運動中出現胸痛、頭暈或異常喘要立即停止。",
        "targetSymptoms": ["心臟病運動", "高血壓運動", "運動強度", "心臟復健", "支架後運動", "長輩運動", "防跌"],
        "citation": "WHO Guidelines on Physical Activity and Sedentary Behaviour. Geneva: World Health Organization; 2020."
    },
    {
        "id": "lit_bp_diet_26",
        "title": "高血壓飲食：減鈉與得舒飲食（DASH）",
        "authority": "美國心臟學會（AHA）& 世界衛生組織（WHO）減鈉建議",
        "category": "飲食照護",
        "ingredient": "得舒飲食與減鈉",
        "evidenceLevel": "大型隨機對照試驗（DASH）",
        "recommendedDose": "每日鈉攝取少於 2000 毫克（約 5 克鹽）；多吃蔬果、全穀與低脂乳品；少吃醃漬、加工食品與湯汁",
        "mechanism": "鈉攝取過多會讓血壓上升；得舒飲食富含鉀、鎂、鈣與纖維，臨床試驗證實可以降低收縮壓。",
        "contraindications": "低鈉鹽多以鉀取代鈉，腎臟病或服用保鉀利尿劑、ACEI／ARB 的人使用前先問醫師；甘草可能使血壓上升、血鉀下降。",
        "targetSymptoms": ["高血壓飲食", "減鈉", "低鈉鹽", "得舒飲食", "DASH", "鹽分", "血壓偏高", "甘草"],
        "citation": "Appel LJ, et al. A clinical trial of the effects of dietary patterns on blood pressure. N Engl J Med. 1997;336(16):1117-1124."
    },
    {
        "id": "lit_lipid_lifestyle_27",
        "title": "高膽固醇與三酸甘油脂的飲食與生活調整",
        "authority": "美國心臟學會／美國心臟病學院（AHA/ACC）血脂指引",
        "category": "飲食照護",
        "ingredient": "降血脂飲食與生活型態",
        "evidenceLevel": "臨床指引建議",
        "recommendedDose": "減少飽和脂肪與反式脂肪，以植物油、堅果、魚取代肥肉與油炸；三酸甘油脂高者特別要少吃精緻糖、少喝含糖飲料與酒；規律運動、控制體重",
        "mechanism": "飽和脂肪會提高低密度膽固醇；精緻糖和酒精會讓肝臟製造更多三酸甘油脂。生活調整是所有血脂治療的基礎，但不能取代醫師開立的降血脂藥。",
        "contraindications": "已經在吃 Statin 的人不要再自行吃紅麴；高劑量魚油要由醫師評估，服用抗凝血藥者尤其注意出血風險。",
        "targetSymptoms": ["膽固醇偏高", "三酸甘油脂", "高血脂飲食", "血脂偏高", "低密度膽固醇", "植物固醇"],
        "citation": "Grundy SM, et al. 2018 AHA/ACC Guideline on the Management of Blood Cholesterol. Circulation. 2019;139(25):e1082-e1143."
    },
    {
        "id": "lit_liver_28",
        "title": "脂肪肝與保健品造成肝損傷的風險",
        "authority": "美國肝病研究學會（AASLD）& 美國 NIH LiverTox 資料庫",
        "category": "飲食照護",
        "ingredient": "脂肪肝生活調整與保健品肝毒性",
        "evidenceLevel": "臨床指引建議",
        "recommendedDose": "體重過重者減重 7–10% 可以改善脂肪肝；少喝含糖飲料、少喝酒；保健品只吃必要、成分單純、有合法標示的產品",
        "mechanism": "脂肪肝和肥胖、糖尿病、高血脂密切相關。NIH LiverTox 資料庫記錄了多種草藥與保健品可能造成肝損傷，例如高劑量綠茶萃取物、紅麴與部分減重產品。",
        "contraindications": "肝指數異常的人避免同時吃多種保健品或來路不明的草藥；出現茶色尿、眼白變黃或極度疲倦要就醫；肝病患者使用乙醯胺酚（普拿疼）要依醫師建議降低劑量。",
        "targetSymptoms": ["脂肪肝", "肝指數偏高", "護肝", "保健品傷肝", "肝功能不好", "熬夜傷肝"],
        "citation": "Rinella ME, et al. AASLD Practice Guidance on the clinical assessment and management of nonalcoholic fatty liver disease. Hepatology. 2023;77(5):1797-1835; NIH LiverTox."
    },
    {
        "id": "lit_dementia_29",
        "title": "降低失智風險與失智長輩居家照護",
        "authority": "世界衛生組織（WHO）認知衰退與失智風險降低指引 & 台灣失智症協會",
        "category": "照護指引",
        "ingredient": "失智預防與居家照護",
        "evidenceLevel": "臨床指引建議",
        "recommendedDose": "規律運動、控制血壓與血糖、戒菸、多社交與動腦；居家移除跌倒風險，為長輩準備寫有聯絡資訊的手鍊（如愛心手鍊）以防走失",
        "mechanism": "WHO 指引建議以運動、戒菸、健康飲食與控制三高來降低認知衰退風險，並不建議以維生素 B、E、魚油或銀杏等補充品來預防失智。",
        "contraindications": "銀杏和抗凝血藥、阿斯匹靈一起使用會增加出血風險；記憶力突然明顯變差或伴隨走路不穩，要就醫排除其他原因。",
        "targetSymptoms": ["失智", "記憶力變差", "預防失智", "防走失", "銀杏記憶力", "阿茲海默", "認知退化"],
        "citation": "World Health Organization. Risk Reduction of Cognitive Decline and Dementia: WHO Guidelines. Geneva: WHO; 2019."
    },
    {
        "id": "lit_parkinson_30",
        "title": "帕金森氏症用藥與蛋白質、鐵劑的時間安排",
        "authority": "美國帕金森基金會（Parkinson's Foundation）營養衛教",
        "category": "用藥安全",
        "ingredient": "左多巴（Levodopa）與蛋白質、鐵劑",
        "evidenceLevel": "官方衛教",
        "recommendedDose": "左多巴通常建議飯前 30–60 分鐘服用；藥效不穩時可和醫師討論把蛋白質集中在晚餐；鐵劑和左多巴間隔約 2 小時",
        "mechanism": "食物中的蛋白質（胺基酸）會和左多巴競爭吸收與進入大腦，飯後馬上吃藥可能讓藥效變差；鐵也會降低左多巴的吸收。",
        "contraindications": "不要自行大幅減少蛋白質，以免營養不良；便秘很常見，可增加水分與纖維。",
        "targetSymptoms": ["帕金森氏症", "左多巴", "帕金森飲食", "帕金森蛋白質", "手抖", "帕金森用藥", "帕金森便秘"],
        "citation": "Parkinson's Foundation. Nutrition and Parkinson's: Protein and Levodopa."
    },
    {
        "id": "lit_gerd_31",
        "title": "胃食道逆流的生活調整與胃藥使用",
        "authority": "美國胃腸醫學會（ACG）胃食道逆流臨床指引",
        "category": "飲食照護",
        "ingredient": "胃食道逆流生活調整與制酸劑",
        "evidenceLevel": "臨床指引建議",
        "recommendedDose": "睡前 2–3 小時不要進食、床頭墊高、體重過重者減重；依個人反應減少誘發食物（如油炸、巧克力、咖啡、酒）",
        "mechanism": "下食道括約肌鬆弛會讓胃酸逆流。長期服用氫離子幫浦阻斷劑（PPI）可能影響維生素 B12 與鎂的吸收，需要依醫師指示使用。",
        "contraindications": "吞嚥困難、體重不明原因下降、解黑便或吐血要立即就醫；胃藥（制酸劑）和鈣片、鐵劑、甲狀腺藥要錯開時間。",
        "targetSymptoms": ["胃食道逆流", "火燒心", "胃藥", "制酸劑", "胃酸逆流", "PPI", "長期吃胃藥"],
        "citation": "Katz PO, et al. ACG Clinical Guideline for the Diagnosis and Management of Gastroesophageal Reflux Disease. Am J Gastroenterol. 2022;117(1):27-56."
    },
    {
        "id": "lit_cold_meds_32",
        "title": "慢性病患者使用綜合感冒藥與止痛退燒藥的注意事項",
        "authority": "衛福部食藥署 用藥安全衛教 & 美國 FDA",
        "category": "用藥安全",
        "ingredient": "綜合感冒藥（擬交感神經成分、乙醯胺酚、抗組織胺）",
        "evidenceLevel": "官方衛教",
        "recommendedDose": "高血壓、心臟病、青光眼、攝護腺肥大的人，買感冒藥前先告訴藥師；同時吃多種感冒藥時注意乙醯胺酚總量（成人一般每日不超過 4000 毫克，長輩與肝病患者更低）",
        "mechanism": "許多綜合感冒藥含有擬交感神經成分（如 pseudoephedrine、phenylephrine），可能讓血壓和心跳上升；第一代抗組織胺可能造成嗜睡、口乾與排尿困難，長輩較容易跌倒或意識混亂。",
        "contraindications": "不要同時吃兩種以上含乙醯胺酚的藥；服用抗凝血藥的人自行吃消炎止痛藥前先問藥師。",
        "targetSymptoms": ["感冒藥", "慢性病吃感冒藥", "高血壓感冒藥", "綜合感冒藥", "鼻塞藥", "普拿疼", "退燒止痛"],
        "citation": "衛福部食藥署 用藥安全資訊；U.S. FDA. Use Caution with Pain Relievers (acetaminophen)."
    },
    {
        "id": "lit_immunity_33",
        "title": "維生素 C、維生素 D 與鋅：預防感冒的實證",
        "authority": "考科藍實證回顧（Cochrane）& 美國 NIH 膳食補充品辦公室",
        "category": "照護指引",
        "ingredient": "維生素 C、維生素 D、鋅",
        "evidenceLevel": "系統性回顧與統合分析",
        "recommendedDose": "以均衡飲食攝取為主；維生素 D 缺乏者依醫師建議補充；鋅每日不超過 40 毫克",
        "mechanism": "考科藍回顧顯示，一般人規律補充維生素 C 無法預防感冒，但可能略為縮短病程；統合分析顯示維生素 D 對缺乏的人預防呼吸道感染可能有幫助。",
        "contraindications": "鋅長期過量可能造成銅缺乏；有腎結石病史的人避免高劑量維生素 C；發燒超過 3 天、呼吸困難要就醫。",
        "targetSymptoms": ["提升免疫力", "容易感冒", "維生素C", "維生素D", "鋅", "感冒保健品"],
        "citation": "Hemilä H, Chalker E. Vitamin C for preventing and treating the common cold. Cochrane Database Syst Rev. 2013;(1):CD000980; Martineau AR, et al. BMJ. 2017;356:i6583."
    },
    {
        "id": "lit_pregnancy_34",
        "title": "孕期與哺乳期的營養補充與保健品安全",
        "authority": "世界衛生組織（WHO）產前照護建議",
        "category": "照護指引",
        "ingredient": "葉酸、鐵、鈣與孕期保健品",
        "evidenceLevel": "臨床指引建議",
        "recommendedDose": "準備懷孕到懷孕初期每天補充葉酸 400 微克；鐵依產檢結果補充；避免高劑量維生素 A（視黃醇、魚肝油）",
        "mechanism": "葉酸可降低胎兒神經管缺損的風險；孕期血量增加需要較多鐵；過量的維生素 A 可能造成胎兒畸形。",
        "contraindications": "懷孕與哺乳期間，多數草本保健品缺乏安全資料，使用前先問婦產科醫師；標示「孕婦不宜」的產品（如輔酶 Q10）應避免。",
        "targetSymptoms": ["懷孕保健品", "葉酸", "孕婦營養", "哺乳期用藥", "產後調養", "孕期鐵劑"],
        "citation": "WHO recommendations on antenatal care for a positive pregnancy experience. Geneva: World Health Organization; 2016."
    },
    {
        "id": "lit_cancer_care_35",
        "title": "癌症治療期間的保健品與營養照護",
        "authority": "美國國家癌症研究院（NCI）",
        "category": "用藥安全",
        "ingredient": "化療、放療期間的草藥與抗氧化補充品",
        "evidenceLevel": "官方臨床資訊（PDQ）",
        "recommendedDose": "治療期間使用任何保健品、中草藥前先告知腫瘤科團隊；食慾差時少量多餐，選擇高熱量、高蛋白的營養補充品",
        "mechanism": "部分高劑量抗氧化劑與草藥（如聖約翰草）可能影響化療或放療效果，或改變藥物代謝；營養不良會降低治療耐受度，因此維持體重與蛋白質攝取很重要。",
        "contraindications": "化療期間白血球低時，避免生食與未經殺菌的食品；益生菌等活菌產品先詢問醫師。",
        "targetSymptoms": ["化療保健品", "化療營養", "放療", "癌症飲食", "化療食慾差", "癌症術後調養", "化療中藥"],
        "citation": "National Cancer Institute. Nutrition in Cancer Care (PDQ®) – Health Professional Version."
    },
    {
        "id": "lit_skin_care_36",
        "title": "濕疹與皮膚乾癢的居家照護",
        "authority": "美國皮膚科醫學會（AAD）異位性皮膚炎照護指引",
        "category": "照護指引",
        "ingredient": "保濕與皮膚屏障照護",
        "evidenceLevel": "臨床指引建議",
        "recommendedDose": "洗澡後 3 分鐘內擦保濕乳；用溫水、縮短洗澡時間；選擇無香料的清潔用品",
        "mechanism": "長輩皮脂分泌減少，冬天容易皮膚乾癢；規律使用保濕劑可以修復皮膚屏障、減少發炎與抓癢。",
        "contraindications": "癢到影響睡眠、皮膚破皮流湯或大範圍紅疹要就醫；保健品對濕疹的實證有限，對特定食物過敏者要避開過敏原。",
        "targetSymptoms": ["濕疹", "皮膚乾癢", "異位性皮膚炎", "皮膚保濕", "過敏體質", "冬季癢"],
        "citation": "Sidbury R, et al. Guidelines of care for the management of atopic dermatitis in adults with topical therapies. J Am Acad Dermatol. 2023;89(1):e1-e20."
    },
]
