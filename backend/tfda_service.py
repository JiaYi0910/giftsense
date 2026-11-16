from typing import Dict, Any, Optional, List

try:
    import knowledge_base
except ImportError:
    from backend import knowledge_base

# =========================================================================
# 藥物、食物與保健品的交互作用規則（AI 守護助理的安全底線）
# 每條規則的 sources 對應 knowledge_sources/sources.json 中已查證的官方來源；
# 檢索結果與規則衝突時以規則的警示為準。尚無官方依據的規則在 official_citation 註明，並列入 docs/RAG_待查證清單.md
# （檔名沿用 tfda_service，內容並非食藥署的資料庫）
# =========================================================================

TFDA_COLLISION_RULES = [
    # 1. Statin 類降血脂藥 + 紅麴 (FATAL / TFDA 黑框警語)
    {
        "id": "tfda_statin_redyeast",
        "drug_keywords": ["statin", "降血脂", "膽固醇", "立普妥", "妥寧", "冠脂妥", "atorvastatin", "rosuvastatin", "simvastatin"],
        "supplement_keywords": ["紅麴", "monacolin", "red yeast"],
        "severity": "FATAL",
        "badge": "🔴 用藥安全警示：紅麴與 Statin 降血脂藥重複",
        "title": "重複降血脂成分！肌肉、肝腎損傷風險",
        "official_citation": "NIH NCCIH：Red Yeast Rice；EFSA Panel on Food Additives and Nutrient Sources added to Food. Scientific opinion on the safety of monacolins in red yeast rice. EFSA Journal. 2018;16(8):5368（doi:10.2903/j.efsa.2018.5368）",
        "sources": ["nccih_red_yeast_rice", "efsa_monacolins"],
        "mechanism": "紅麴的 Monacolin K 與降血脂藥 Lovastatin 結構相同；含量高的紅麴產品可能有和 Statin 相同的副作用（肌肉、腎臟與肝臟損傷）與藥物交互作用，與 Statin 併用等於重複用藥。",
        "clinical_action": "已在服用 Statin 降血脂藥者不可自行併用紅麴產品；有疑問請帶著藥袋詢問醫師或藥師。",
        "radar_scores": [20, 60, 10, 70, 10], # 用藥安全性: 10
        "alternative": None
    },
    # 2. Warfarin / 抗凝血藥 + 納豆激酶 (FATAL / 重大自發性出血)
    {
        "id": "tfda_warfarin_nattokinase",
        "drug_keywords": ["warfarin", "抗凝血", "可邁丁", "noac", "普栓達", "拜瑞妥", "dabigatran", "rivaroxaban", "apixaban"],
        "supplement_keywords": ["納豆", "納豆激酶", "nattokinase"],
        "severity": "FATAL",
        "badge": "🔴 用藥安全警示：抗凝血藥與溶栓成分",
        "title": "溶栓成分疊加抗凝血藥！出血風險升高",
        "official_citation": "Kurosawa Y, et al. A single-dose of oral nattokinase potentiates thrombolysis and anti-coagulation profiles. Sci Rep. 2015;5:11601.（PMID 26109079）；DailyMed：Warfarin Sodium Tablets — FDA Drug Label (Drug Interactions)；衛生福利部食品藥物管理署：食品原料整合查詢平臺－納豆激酶",
        "sources": ["pmid_26109079", "label_warfarin", "tfda_material_nattokinase"],
        "mechanism": "人體試驗中，單次口服納豆激酶即可增強溶栓與抗凝血指標；Warfarin 仿單也提醒，部分草藥產品本身可能引起出血、具抗凝血或溶栓作用。兩者併用可能疊加出血風險。",
        "clinical_action": "服用抗凝血藥者避免濃縮納豆激酶產品（食藥署將納豆激酶純化物列為未經確認食用安全性、不得供為食品原料）；有出血、黑便或大片瘀青時立即就醫。",
        "radar_scores": [30, 70, 15, 80, 15],
        "alternative": None
    },
    # 3. Warfarin / 抗凝血藥 + 銀杏 (MAJOR / 抑制血小板凝集)
    {
        "id": "tfda_warfarin_ginkgo",
        "drug_keywords": ["warfarin", "抗凝血", "可邁丁", "noac", "阿斯匹靈", "aspirin", "plavix", "保栓通"],
        "supplement_keywords": ["銀杏", "銀杏葉", "ginkgo", "egb"],
        "severity": "MAJOR",
        "badge": "⚠️ 用藥安全警示：抗凝血藥與銀杏",
        "title": "銀杏加上抗凝血藥，重大出血風險升高",
        "official_citation": "NIH NCCIH：Ginkgo；NIH NCCIH：Herb-Drug Interactions (Clinical Digest for Health Professionals)；DailyMed：Warfarin Sodium Tablets — FDA Drug Label (Drug Interactions)；WHO：WHO Monographs on Selected Medicinal Plants – Volume 1；衛生福利部食品藥物管理署：食品原料整合查詢平臺－銀杏葉",
        "sources": ["nccih_ginkgo", "nccih_herb_drug", "label_warfarin", "who_ginkgo_monograph", "tfda_material_ginkgo_leaf"],
        "mechanism": "NCCIH：銀杏與 Warfarin 併用，重大出血事件的風險比單用 Warfarin 高；Warfarin 仿單也列出銀杏可能單獨引起出血，並可能經由代謝酵素影響藥效。在台灣，銀杏葉不得供為食品原料，含銀杏葉萃取物的產品屬藥品。",
        "clinical_action": "服用抗凝血或抗血小板藥者避免自行使用銀杏；若醫師評估後仍需使用，須監測凝血指數（PT／INR）。",
        "radar_scores": [35, 75, 20, 80, 20],
        "alternative": None
    },
    # 4. Warfarin / 抗凝血藥 + 高劑量魚油 / 薑黃 (MAJOR)
    {
        "id": "tfda_warfarin_fishoil_curcumin",
        "drug_keywords": ["warfarin", "抗凝血", "可邁丁", "noac"],
        "supplement_keywords": ["魚油", "omega", "epa", "dha", "薑黃", "薑黃素", "curcumin"],
        "severity": "MAJOR",
        "badge": "⚠️ 用藥安全提醒：抗凝血藥與魚油、薑黃",
        "title": "抗凝血藥併用魚油或薑黃前，先詢問醫師",
        "official_citation": "DailyMed：Warfarin Sodium Tablets — FDA Drug Label (Drug Interactions)；NIH NCCIH：Turmeric",
        "sources": ["label_warfarin", "nccih_turmeric", "ods_omega3fattyacids"],
        "mechanism": "Warfarin 仿單提醒，併用其他可能影響凝血的藥物或草藥產品時需特別注意出血風險；魚油、薑黃是否影響 Warfarin 的完整依據，待補 NIH ODS 資料後更新。",
        "clinical_action": "服用抗凝血藥者使用魚油或薑黃前先詢問醫師或藥師，並留意牙齦出血、瘀青或黑便等出血徵兆。",
        "radar_scores": [40, 80, 25, 85, 25],
        "alternative": None
    },
    # 5. Warfarin / 抗凝血藥 + 蔓越莓萃取物 (MAJOR / 抑制 CYP2C9)
    {
        "id": "tfda_warfarin_cranberry",
        "drug_keywords": ["warfarin", "抗凝血", "可邁丁"],
        "supplement_keywords": ["蔓越莓", "cranberry", "前花青素"],
        "severity": "MAJOR",
        "badge": "⚠️ 用藥安全提醒：抗凝血藥與蔓越莓",
        "title": "蔓越莓與 Warfarin：交互作用證據不一致",
        "official_citation": "NIH NCCIH：Cranberry；NIH NCCIH：Herb-Drug Interactions (Clinical Digest for Health Professionals)",
        "sources": ["nccih_cranberry", "nccih_herb_drug"],
        "mechanism": "NCCIH：蔓越莓是否會和抗凝血藥 Warfarin 產生交互作用，目前研究證據不一致。",
        "clinical_action": "服用 Warfarin 者使用高濃縮蔓越莓產品前，先詢問醫師或藥師。",
        "radar_scores": [35, 70, 20, 75, 20],
        "alternative": None
    },
    # ---- 2026/11/16：依 NCCIH 官方資料補上的交互作用 ----
    {
        "id": "rule_warfarin_glucosamine",
        "drug_keywords": ["warfarin", "抗凝血", "可邁丁"],
        "supplement_keywords": ["葡萄糖胺", "glucosamine", "軟骨素", "chondroitin", "維骨力"],
        "severity": "MAJOR",
        "badge": "⚠️ 用藥安全警示：抗凝血藥與葡萄糖胺",
        "title": "葡萄糖胺、軟骨素與 Warfarin 併用，出血風險增加",
        "official_citation": "NIH NCCIH：Glucosamine and Chondroitin for Osteoarthritis: What You Need To Know",
        "sources": ["nccih_glucosamine"],
        "mechanism": "NCCIH：葡萄糖胺與軟骨素和服用抗凝血藥 Warfarin 者的出血風險增加有關；葡萄糖胺也可能使部分人的血糖上升。",
        "clinical_action": "服用 Warfarin 者使用葡萄糖胺或軟骨素前先詢問醫師或藥師，並留意出血徵兆。",
        "radar_scores": [40, 75, 25, 80, 25],
        "alternative": None
    },
    {
        "id": "rule_warfarin_coq10",
        "drug_keywords": ["warfarin", "抗凝血", "可邁丁"],
        "supplement_keywords": ["q10", "輔酶"],
        "severity": "MAJOR",
        "badge": "⚠️ 用藥安全提醒：抗凝血藥與輔酶 Q10",
        "title": "輔酶 Q10 可能影響 Warfarin 的作用",
        "official_citation": "NIH NCCIH：Coenzyme Q10；衛生福利部食品藥物管理署：食品原料輔酵素Q10 (Coenzyme Q10)之使用限制及標示規定（108年10月18日衛授食字第1081302650號公告）",
        "sources": ["nccih_coq10", "tfda_material_coq10"],
        "mechanism": "食藥署規定使用輔酶 Q10 作為原料的食品，應標示「服用抗凝血藥品(warfarin)之病患，不宜食用」；NCCIH 也指出輔酶 Q10 可能與抗凝血藥 Warfarin、糖尿病用藥胰島素產生交互作用。",
        "clinical_action": "服用 Warfarin 者不宜自行食用含輔酶 Q10 的產品；若醫師評估後仍要使用，開始或停用後依醫師指示追蹤凝血指數。",
        "radar_scores": [50, 75, 30, 80, 30],
        "alternative": None
    },
    # 6. 創傷 / 燙傷創面 + 活血化瘀成分 (MAJOR / 創面滲血)
    {
        "id": "tfda_wound_bleeding_risk",
        "drug_keywords": ["燙傷", "傷口", "皮膚", "創面", "褥瘡", "術後"],
        "supplement_keywords": ["薑黃", "納豆", "銀杏", "魚油", "活血", "一條根"],
        "severity": "MAJOR",
        "badge": "⚠️ 用藥安全提醒：傷口癒合期",
        "title": "傷口未癒合前，暫緩可能影響凝血的保健品",
        "official_citation": "（尚無官方依據，見 docs/RAG_待查證清單.md）",
        "sources": [],
        "mechanism": "傷口癒合需要正常的凝血功能；這類成分是否影響傷口癒合，目前知識庫尚無官方依據（見待查證清單），以保守原則提醒。",
        "clinical_action": "傷口未癒合前，使用這類保健品前先詢問醫師；不要在傷口上貼草本貼布。",
        "radar_scores": [35, 75, 25, 80, 25],
        "alternative": None
    },
    # 7. 降血壓藥 + 甘草萃取物 (MAJOR / 假性醛固酮症)
    {
        "id": "tfda_hypertension_licorice",
        "drug_keywords": ["血壓", "高血壓", "脈優", "amlodipine", "losartan", "valsartan"],
        "supplement_keywords": ["甘草", "licorice", "甘草酸"],
        "severity": "MAJOR",
        "badge": "⚠️ 用藥安全警示：高血壓與甘草",
        "title": "甘草酸可能造成嚴重不良反應，高血壓者需避免",
        "official_citation": "NIH NCCIH：Licorice Root",
        "sources": ["nccih_licorice"],
        "mechanism": "NCCIH：甘草所含的甘草酸（glycyrrhizin）可能造成心律不整等嚴重不良反應，大量或長期使用時更明顯；即使少量，也曾在高血壓、心臟或腎臟疾病、高鹽飲食者身上造成嚴重反應。",
        "clinical_action": "高血壓、心臟或腎臟疾病者避免含甘草酸的補品與喉糖；使用前先詢問醫師或藥師。",
        "radar_scores": [40, 70, 25, 75, 25],
        "alternative": None
    },
    # 8. 糖尿病親友 + 高糖滋補品 (MAJOR / 血糖劇烈波動)
    {
        "id": "tfda_diabetes_sugar",
        "drug_keywords": ["糖尿", "血糖", "滅醣敏", "metformin", "胰島素"],
        "supplement_keywords": ["含糖", "蜂蜜", "糖漿", "人參飲", "冬蟲夏草含糖", "黑糖", "冰糖"],
        "severity": "MAJOR",
        "badge": "⚠️ 用藥安全提醒：血糖控制",
        "title": "血糖劇烈波動警戒！干擾胰島素調控",
        "official_citation": "American Diabetes Association Professional Practice Committee, et al. Introduction and Methodology: Standards of Care in Diabetes-2024. Diabetes Care. 2024;47:S1-S4.（PMID 38078587）",
        "sources": ["pmid_38078587"],
        "mechanism": "高糖滋補品含大量游離果糖與蔗糖，進入人體後迅速被小腸上皮吸收，造成餐後血糖暴衝，抵消口服降血糖藥物療效，加速血管內皮病變。",
        "clinical_action": "糖尿病患應嚴格選擇無糖、低 GI (低升糖指數) 之認證配方。",
        "radar_scores": [45, 70, 30, 80, 30],
        "alternative": None
    },
    # ---- 2026/10/15 擴充：各病症常見的藥物、食物與保健品交互作用 ----
    {
        "id": "rule_grapefruit_ccb_statin",
        "drug_keywords": ["血壓", "鈣離子阻斷", "amlodipine", "nifedipine", "felodipine", "脈優", "statin", "降血脂", "膽固醇", "simvastatin", "atorvastatin", "立普妥"],
        "supplement_keywords": ["葡萄柚", "grapefruit", "文旦", "柚子"],
        "severity": "MAJOR",
        "badge": "用藥安全警示：食物與藥物交互作用",
        "title": "葡萄柚可能讓降血壓、降血脂藥濃度升高",
        "official_citation": "US FDA：Grapefruit Juice and Some Drugs Don't Mix；Bailey DG, et al. Grapefruit-medication interactions: forbidden fruit or avoidable consequences? CMAJ. 2013;185:309-16.（PMID 23184849）",
        "sources": ["fda_grapefruit", "pmid_23184849"],
        "mechanism": "葡萄柚會抑制腸道 CYP3A4 酵素，使鈣離子阻斷劑（如 felodipine、nifedipine）與部分 Statin（simvastatin、atorvastatin）的血中濃度升高，可能造成血壓過低、頭暈或肌肉病變，錯開時間吃也無法避免。",
        "clinical_action": "服用上述藥物期間避免葡萄柚與葡萄柚汁；不確定自己的藥是否受影響，請帶著藥袋詢問藥師。",
        "radar_scores": [55, 75, 35, 80, 30],
        "alternative": None
    },
    {
        "id": "rule_ckd_nsaid",
        "drug_keywords": ["腎", "洗腎", "透析", "ckd"],
        "supplement_keywords": ["止痛藥", "消炎藥", "布洛芬", "ibuprofen", "nsaid", "萘普生", "naproxen", "非類固醇"],
        "severity": "MAJOR",
        "badge": "用藥安全警示：腎臟病避免消炎止痛藥",
        "title": "消炎止痛藥可能使腎功能惡化",
        "official_citation": "KDIGO：KDIGO 2012 Clinical Practice Guideline for the Evaluation and Management of CKD",
        "sources": ["kdigo_ckd"],
        "mechanism": "非類固醇消炎止痛藥（NSAIDs）會減少腎臟血流，可能讓腎功能惡化並造成水腫與高血鉀；與降血壓藥或利尿劑一起使用時風險更高。",
        "clinical_action": "腎臟病親友不要自行購買消炎止痛藥；需要止痛時先詢問腎臟科醫師或藥師。",
        "radar_scores": [50, 70, 30, 80, 25],
        "alternative": None
    },
    {
        "id": "rule_anticoagulant_nsaid",
        "drug_keywords": ["warfarin", "抗凝血", "可邁丁", "noac", "普栓達", "拜瑞妥", "艾必克凝", "阿斯匹靈", "aspirin", "保栓通", "plavix"],
        "supplement_keywords": ["止痛藥", "消炎藥", "布洛芬", "ibuprofen", "nsaid", "萘普生", "naproxen", "非類固醇"],
        "severity": "MAJOR",
        "badge": "用藥安全警示：出血風險",
        "title": "抗凝血藥加上消炎止痛藥，出血風險增加",
        "official_citation": "DailyMed：Warfarin Sodium Tablets — FDA Drug Label (Drug Interactions)",
        "sources": ["label_warfarin"],
        "mechanism": "Warfarin 仿單列出抗血小板藥（如阿斯匹靈、保栓通）與非類固醇消炎止痛藥（NSAIDs）都會增加出血風險；與抗凝血藥一起使用時，出血的機會明顯增加。",
        "clinical_action": "服用抗凝血藥的親友不要自行吃消炎止痛藥；需要止痛退燒時先詢問醫師或藥師選擇較安全的藥。",
        "radar_scores": [45, 70, 30, 80, 20],
        "alternative": None
    },
    {
        "id": "rule_potassium_salt",
        "drug_keywords": ["腎", "洗腎", "透析", "保鉀", "spironolactone", "acei", "arb", "losartan", "valsartan"],
        "supplement_keywords": ["低鈉鹽", "代鹽", "鉀鹽", "鉀補充"],
        "severity": "MAJOR",
        "badge": "用藥安全警示：高血鉀風險",
        "title": "低鈉鹽的鉀可能造成高血鉀",
        "official_citation": "Ikizler TA, et al. KDOQI Clinical Practice Guideline for Nutrition in CKD: 2020 Update. Am J Kidney Dis. 2020;76:S1-S107.（PMID 32829751）",
        "sources": ["pmid_32829751"],
        "mechanism": "低鈉鹽多以氯化鉀取代氯化鈉；腎功能不好或服用保鉀利尿劑、ACEI／ARB 的人排鉀能力較差，可能使血鉀過高而引起心律不整。",
        "clinical_action": "腎臟病或服用上述藥物的親友，使用低鈉鹽前先詢問醫師；減鹽改用天然香料調味。",
        "radar_scores": [55, 75, 35, 80, 30],
        "alternative": None
    },
    {
        "id": "rule_cold_medicine_bp",
        "drug_keywords": ["血壓", "心臟", "青光眼", "攝護腺"],
        "supplement_keywords": ["感冒藥", "鼻塞", "pseudoephedrine", "偽麻黃", "phenylephrine"],
        "severity": "MAJOR",
        "badge": "用藥安全警示：感冒藥成分",
        "title": "部分綜合感冒藥可能讓血壓、心跳上升",
        "official_citation": "US FDA：OTC Monograph M012: Cough, Cold, Allergy, Bronchodilator, and Antiasthmatic Drug Products for OTC Human Use",
        "sources": ["fda_otc_m012"],
        "mechanism": "綜合感冒藥常含擬交感神經成分（如 pseudoephedrine、phenylephrine），可能使血壓與心跳上升，也可能加重青光眼與攝護腺肥大的症狀。",
        "clinical_action": "買感冒藥時主動告訴藥師親友的慢性病與用藥，請藥師挑選不含這類成分的藥品。",
        "radar_scores": [60, 80, 40, 85, 35],
        "alternative": None
    },
    {
        "id": "rule_gaba_bp_sedative_epilepsy",
        "drug_keywords": ["血壓", "降壓", "鎮靜", "安眠", "抗焦慮", "癲癇", "benzodiazepine", "zolpidem", "史蒂諾斯", "使蒂諾斯", "悠樂丁", "贊安諾"],
        "supplement_keywords": ["gaba", "胺基丁酸"],
        "severity": "MAJOR",
        "badge": "用藥安全警示：GABA 與降血壓、鎮靜、抗癲癇藥",
        "title": "GABA 產品依規定須標示：避免與降血壓、鎮靜及癲癇藥物併用",
        "official_citation": "衛生福利部食品藥物管理署：以微生物發酵製取之食品原料γ-胺基丁酸之使用限制及標示規定（114年2月13日衛授食字第1131303496號公告）",
        "sources": ["tfda_material_gaba"],
        "mechanism": "食藥署規定以微生物發酵製取的 GABA 原料每日食用限量為 100 毫克，且使用 GABA 作為原料的食品，應標示「使用本產品應避免同時飲酒或服用降血壓、鎮靜及癲癇等藥物；孕婦、授乳者、嬰幼兒，須諮詢醫師方可使用」。",
        "clinical_action": "正在服用降血壓藥、鎮靜安眠藥或抗癲癇藥的親友，不要自行使用含 GABA 的產品，也避免同時喝酒；請先帶著藥袋詢問醫師或藥師。",
        "radar_scores": [55, 75, 35, 80, 30],
        "alternative": None
    },
    {
        "id": "rule_sedative_sleep_aid",
        "drug_keywords": ["安眠", "鎮靜", "抗焦慮", "benzodiazepine", "zolpidem", "史蒂諾斯", "使蒂諾斯", "悠樂丁", "贊安諾"],
        "supplement_keywords": ["gaba", "褪黑", "melatonin", "纈草", "助眠", "酒"],
        "severity": "MAJOR",
        "badge": "用藥安全警示：中樞神經抑制",
        "title": "安眠藥加上助眠成分或酒精，可能加重嗜睡與跌倒風險",
        "official_citation": "Sateia MJ, et al. Clinical Practice Guideline for the Pharmacologic Treatment of Chronic Insomnia in Adults: An American Academy of Sleep Medicine Clinical Practice Guideline. J Clin Sleep Med. 2017;13:307-349.（PMID 27998379）",
        "sources": ["pmid_27998379"],
        "mechanism": "助眠成分與酒精和鎮靜安眠藥同樣作用在中樞神經，一起使用可能加重嗜睡、頭暈，增加長輩夜間跌倒的風險。",
        "clinical_action": "已在服用安眠藥的親友，不要自行加上助眠保健品，也不要喝酒；睡不好請回診與醫師討論調整。",
        "radar_scores": [55, 75, 35, 80, 30],
        "alternative": None
    },
    {
        "id": "rule_glucose_lowering_supplement",
        "drug_keywords": ["糖尿", "血糖", "降糖", "胰島素", "metformin", "滅醣敏"],
        "supplement_keywords": ["苦瓜", "肉桂", "鉻", "控糖保健"],
        "severity": "MODERATE",
        "badge": "用藥安全提醒：低血糖風險",
        "title": "控糖保健品可能加強降血糖藥的作用",
        "official_citation": "American Diabetes Association Professional Practice Committee, et al. Introduction and Methodology: Standards of Care in Diabetes-2024. Diabetes Care. 2024;47:S1-S4.（PMID 38078587）",
        "sources": ["pmid_38078587"],
        "mechanism": "苦瓜、肉桂、鉻等成分改善血糖的證據有限，但和降血糖藥或胰島素一起使用時，可能加強降血糖作用而增加低血糖風險。",
        "clinical_action": "使用前先和醫師討論，開始吃之後多量幾次血糖；不要用保健品取代藥物。",
        "radar_scores": [60, 80, 45, 85, 40],
        "alternative": None
    },
    {
        "id": "rule_cancer_therapy_herbal",
        "drug_keywords": ["化療", "放療", "標靶", "癌"],
        "supplement_keywords": ["聖約翰草", "中草藥", "中藥", "人參", "靈芝", "高劑量抗氧化", "益生菌"],
        "severity": "MAJOR",
        "badge": "用藥安全警示：可能影響癌症治療",
        "title": "治療期間的草藥與保健品可能干擾療效",
        "official_citation": "NCI：Nutrition in Cancer Care (PDQ®)–Health Professional Version",
        "sources": ["nci_nutrition_hp"],
        "mechanism": "部分草藥（如聖約翰草）會改變藥物代謝，高劑量抗氧化劑可能影響化療或放療效果；白血球低時，活菌產品也有感染風險。",
        "clinical_action": "治療期間使用任何保健品或中草藥前，先告知腫瘤科醫師或個管師。",
        "radar_scores": [50, 70, 30, 80, 25],
        "alternative": None
    },
    {
        "id": "rule_pregnancy_supplement",
        "drug_keywords": ["懷孕", "孕婦", "孕期", "哺乳"],
        "supplement_keywords": ["維生素a", "維他命a", "魚肝油", "視黃醇", "q10", "輔酶", "gaba", "胺基丁酸"],
        "severity": "MAJOR",
        "badge": "用藥安全警示：孕期與哺乳期",
        "title": "孕期避免高劑量維生素 A 與標示孕婦不宜的保健品",
        "official_citation": "WHO：WHO recommendations on antenatal care for a positive pregnancy experience；衛生福利部食品藥物管理署：食品原料輔酵素Q10 (Coenzyme Q10)之使用限制及標示規定（108年10月18日衛授食字第1081302650號公告）；衛生福利部食品藥物管理署：以微生物發酵製取之食品原料γ-胺基丁酸之使用限制及標示規定（114年2月13日衛授食字第1131303496號公告）",
        "sources": ["who_antenatal", "tfda_material_coq10", "tfda_material_gaba"],
        "mechanism": "WHO 產前照護建議不建議一般孕婦常規補充維生素 A，過量維生素 A（視黃醇）可能影響胎兒；食藥署規定含輔酶 Q10 的食品須標示懷孕或哺乳期間婦女不宜食用，含 GABA 的食品須標示孕婦、授乳者須諮詢醫師方可使用。",
        "clinical_action": "懷孕或哺乳期間使用保健品前先詢問婦產科醫師，以醫師建議的孕期綜合維生素為主。",
        "radar_scores": [55, 75, 35, 80, 30],
        "alternative": None
    },
    {
        "id": "rule_thyroid_mineral_spacing",
        "drug_keywords": ["甲狀腺", "levothyroxine", "昂特欣", "eltroxin"],
        "supplement_keywords": ["鈣", "鐵", "胃藥", "制酸", "鎂"],
        "severity": "MODERATE",
        "badge": "用藥安全提醒：服用時間要錯開",
        "title": "甲狀腺藥和鈣、鐵、胃藥至少間隔 4 小時",
        "official_citation": "DailyMed：Levothyroxine Sodium Tablets — FDA Drug Label (Drug Interactions)",
        "sources": ["label_levothyroxine", "ods_calcium"],
        "mechanism": "Levothyroxine 仿單：碳酸鈣、硫酸亞鐵等會和甲狀腺素結合，需至少間隔 4 小時；制酸劑與胃藥也會降低吸收，使藥效變差。",
        "clinical_action": "甲狀腺藥早上空腹吃，鈣片、鐵劑、胃藥移到午餐或晚餐後，至少間隔 4 小時。",
        "radar_scores": [70, 85, 55, 85, 50],
        "alternative": None
    }
]

class TFDAService:
    """Taiwan Food and Drug Administration (TFDA) Verification Service."""

    @staticmethod
    def check_interaction(elder_name: str, elder_condition: str, query: str, matched_ingredient: str = "") -> Dict[str, Any]:
        q = (query + " " + matched_ingredient).lower()
        cond = elder_condition.lower()

        for rule in TFDA_COLLISION_RULES:
            drug_hit = any(k in cond for k in rule["drug_keywords"])
            supp_hit = any(k in q for k in rule["supplement_keywords"])

            if drug_hit and supp_hit:
                return {
                    "is_collision": True,
                    "severity": rule["severity"],
                    "badge": rule["badge"],
                    "title": rule["title"],
                    "desc": f"【{elder_name}】患有【{elder_condition}】。依據 {rule['official_citation']}，{rule['mechanism']}",
                    "clinical_action": rule["clinical_action"],
                    "official_citation": rule["official_citation"],
                    "sources": knowledge_base.source_refs(rule.get("sources")),
                    "rule_id": rule["id"],
                    "mechanism": rule["mechanism"],
                    "radar_scores": rule["radar_scores"],
                    "alternative": rule["alternative"]
                }

        # 沒有命中任何規則：只代表不在本系統收錄的規則內，不代表確定沒有交互作用
        return {
            "is_collision": False,
            "severity": "SAFE",
            "badge": "✅ 未命中已收錄的交互作用規則",
            "title": "未命中已收錄的交互作用規則",
            "desc": f"已將【{matched_ingredient or query}】與【{elder_name}】（{elder_condition}）比對本系統收錄的 {len(TFDA_COLLISION_RULES)} 條交互作用規則，沒有命中。這不代表確定沒有交互作用，購買前仍請帶著藥袋詢問醫師或藥師。",
            "clinical_action": "請依產品標示或醫囑劑量使用；有慢性病或長期用藥者，使用前先詢問醫師或藥師。",
            "official_citation": "GiftSense 交互作用規則（每條規則附官方出處）",
            "sources": [],
            "rule_id": None,
            "mechanism": "未命中已收錄的交互作用規則。",
            "radar_scores": [95, 96, 94, 92, 98],
            "alternative": None
        }

global_tfda_service = TFDAService()
