import os
import json
import math
import re
from typing import List, Dict, Any, Optional

# =========================================================================
# COMPREHENSIVE CLINICAL LITERATURE CORPUS (15 Authoritative Literatures)
# US FDA / NIH / TFDA / Cochrane / AHA / ESCEO / WGO / AASM
# =========================================================================
FULL_CLINICAL_LITERATURES: List[Dict[str, Any]] = [
    {
        "id": "lit_lutein_01",
        "title": "AREDS 2 臨床試驗：葉黃素與玉米黃素對成人黃斑部與視覺機能之實證研究",
        "authority": "美國國家衛生研究院 (NIH / NEI) & 台灣衛福部食藥署 (TFDA)",
        "category": "視力保健",
        "ingredient": "Lutein (葉黃素) & Zeaxanthin (玉米黃素)",
        "evidenceLevel": "Level 1 (大規模多中心隨機對照試驗 RCT)",
        "recommendedDose": "游離型葉黃素 10mg + 玉米黃素 2mg / 每日（TFDA 規範每日上限 30mg）",
        "mechanism": "作為視網膜黃斑部重要類胡蘿蔔素，能有效過濾有害高能量藍光，減少光氧化自由基損傷，延緩視力退化。",
        "contraindications": "長期吸菸者避免與高劑量 β-胡蘿蔔素同服；對金盞花萃取物過敏者慎用。",
        "targetSymptoms": ["用眼過度", "眼睛乾澀", "夜間視力不佳", "黃斑部保健", "頻繁使用3C"],
        "citation": "National Eye Institute (NEI) AREDS2 Research Group. JAMA. 2013;309(19):2005-2015."
    },
    {
        "id": "lit_omega3_02",
        "title": "Omega-3 脂肪酸 (EPA/DHA) 對心血管風險與發炎反應之臨床指引",
        "authority": "美國心臟學會 (AHA) & 美國食品藥物管理局 (US FDA Qualified Health Claim)",
        "category": "心血管與循環",
        "ingredient": "Omega-3 魚油 (EPA / DHA)",
        "evidenceLevel": "Level 1 (Meta-Analysis 系統性回顧)",
        "recommendedDose": "日常保養 EPA+DHA 1,000mg/日；調節三酸甘油酯需遵醫囑 2,000-4,000mg/日（FDA 建議總量不超過 3,000mg/日）",
        "mechanism": "競爭性抑制花生四烯酸代謝路徑，減少發炎介質 (TXA2, PGE2) 生成，提升血管內皮細胞彈性並降低血小板凝聚。",
        "contraindications": "【重大禁忌】正服用抗凝血藥 (Warfarin, NOACs) 或阿斯匹靈者需嚴格控制劑量；凝血功能不全、重大手術前 14 天應停用；對魚類過敏者禁用。",
        "targetSymptoms": ["血壓偏高", "血脂偏高", "心血管保健", "慢性關節發炎", "注意力不集中"],
        "citation": "American Heart Association (AHA) Science Advisory. Circulation. 2019;140:e673–e691."
    },
    {
        "id": "lit_probiotics_03",
        "title": "世界胃腸病學組織 (WGO)：益生菌在腸道微生態與消化免疫調節之臨床應用",
        "authority": "世界胃腸病學組織 (WGO) & 考科藍合作組織 (Cochrane Review)",
        "category": "腸胃與免疫",
        "ingredient": "複合專利益生菌 (Lactobacillus, Bifidobacterium)",
        "evidenceLevel": "Level 1 (Cochrane Systematic Review)",
        "recommendedDose": "每日 20億 ~ 100億 CFU (依不同菌株臨床試驗而定)",
        "mechanism": "透過競爭排斥致病菌、增強腸道黏膜屏障緊密連接蛋白、調節腸道相關淋巴組織 (GALT) 分泌 sIgA 抗體。",
        "contraindications": "與抗生素同時使用會殺死活菌，需間隔 2 小時以上；重度免疫不全、中心靜脈導管患者應經主治醫師評估以防菌血症。",
        "targetSymptoms": ["便秘", "脹氣腹瀉", "消化不良", "排便不順", "季節性過敏"],
        "citation": "World Gastroenterology Organisation Global Guidelines: Probiotics and prebiotics, 2023."
    },
    {
        "id": "lit_calcium_d3_04",
        "title": "美國國家骨質疏鬆症基金會 (NOF)：鈣質與維生素 D3 協同維持骨密臨床指南",
        "authority": "美國國家骨質疏鬆症基金會 (NOF) & 台灣衛福部國人膳食營養素參考攝取量 (DRIs)",
        "category": "骨骼關節",
        "ingredient": "檸檬酸鈣 / 碳酸鈣 + 活性維生素 D3 (Cholecalciferol)",
        "evidenceLevel": "Level 1 (臨床實證指引)",
        "recommendedDose": "銀髮成人鈣質 1,000mg/日，維生素 D3 800-1,000 IU/日（維生素 D 上限 2,000 IU/日）",
        "mechanism": "維生素 D3 促進小腸上皮細胞合成鈣結合蛋白 (Calbindin)，提升腸道鈣質吸收率 30-40%，協同成骨細胞礦化骨基質。",
        "contraindications": "高血鈣症、高尿鈣症或副甲狀腺機能亢進患者禁用；腎結石病史者應優先選擇檸檬酸鈣並大量飲水；避免與鐵劑或四環黴素同服。",
        "targetSymptoms": ["骨質疏鬆", "骨折修復期", "關節退化", "抽筋", "日曬不足"],
        "citation": "National Osteoporosis Foundation (NOF) Clinician's Guide to Prevention and Treatment of Osteoporosis. 2022."
    },
    {
        "id": "lit_curcumin_05",
        "title": "高生物利用率薑黃素對於慢性關節退化發炎指數之調節實證",
        "authority": "美國國家補充和整合健康中心 (NIH NCCIH) & 歐洲食品安全局 (EFSA)",
        "category": "關節與消炎",
        "ingredient": "Curcumin (薑黃素 / 95% 薑黃萃取物)",
        "evidenceLevel": "Level 2 (隨機雙盲對照試驗)",
        "recommendedDose": "標準化薑黃素 500-1,000mg/日（搭配黑胡椒萃取物 Piperine 可提高 2,000% 生物利用率）",
        "mechanism": "強力抑制 NF-κB 轉錄因子活化，下調促發炎細胞因子 (TNF-α, IL-6) 及 COX-2 酵素活性，舒緩關節發炎症狀。",
        "contraindications": "【禁忌】膽結石、膽道阻塞患者禁用（刺激膽囊收縮）；具有抗血小板凝聚作用，手術前兩週應停用；避免與抗凝血藥併用。",
        "targetSymptoms": ["關節疼痛", "退化性關節炎", "肌肉痠痛", "慢性發炎", "運動後修復"],
        "citation": "National Center for Complementary and Integrative Health (NCCIH). Turmeric/Curcumin Science Brief, 2023."
    },
    {
        "id": "lit_coq10_06",
        "title": "輔酶 Q10 在心肌能量代謝與 Statin 肌肉酸痛緩解之臨床回顧",
        "authority": "台灣衛福部食藥署 (TFDA 保健法規) & 美國心臟病學會 (ACC)",
        "category": "心肌代謝與活力",
        "ingredient": "Coenzyme Q10 (輔酶 Q10 / 泛醌)",
        "evidenceLevel": "Level 2 (系統性文獻回顧與臨床試驗)",
        "recommendedDose": "每日 30mg（台灣 TFDA 規範每日食用限量 30mg 以下）",
        "mechanism": "作為粒線體電子傳遞鏈關鍵輔酶，促進 ATP 生成，提升心肌細胞能量代謝，並具強效親脂性抗氧化活性。",
        "contraindications": "【法規警語】15歲以下小孩、懷孕或哺乳期間婦女及服用抗凝血藥品 (Warfarin) 之病患不宜食用。",
        "targetSymptoms": ["容易疲倦", "體力衰退", "心臟機能保養", "服用降血脂藥肌無力", "精力不足"],
        "citation": "TFDA 衛署食字第 0950400854 號公告 & J Am Coll Cardiol. 2014;64(14):1456-1463."
    },
    {
        "id": "lit_glucosamine_07",
        "title": "歐洲骨質疏鬆與骨關節炎臨床經濟學會 (ESCEO)：結晶型硫酸鹽葡萄糖胺治療指引",
        "authority": "歐洲骨質疏鬆與骨關節炎學會 (ESCEO) & 國際骨關節炎研究學會 (OARSI)",
        "category": "骨骼關節",
        "ingredient": "Crystalline Glucosamine Sulfate (結晶型硫酸鹽葡萄糖胺)",
        "evidenceLevel": "Level 1 (國際臨床實證首選推薦 First-Line)",
        "recommendedDose": "結晶型硫酸鹽葡萄糖胺 1,500mg/日 (單次服用生物利用率最高)",
        "mechanism": "刺激關節滑膜軟骨細胞合成蛋白聚糖 (Proteoglycans) 與玻尿酸，抑制發炎介質 IL-1β，維持關節軟骨基質完整性與潤滑。",
        "contraindications": "對甲殼類/蝦蟹過敏者應選擇發酵型植物葡萄糖胺；一般不具抗凝血交互作用，心血管患者可安心替代。",
        "targetSymptoms": ["膝蓋痛", "上下樓梯無力", "退化性關節炎", "關節卡卡異音", "活動受限"],
        "citation": "Bruyère O, et al. Consensus statement on the treatment of knee osteoarthritis. Seminars in Arthritis and Rheumatism. 2019;49(3):337-350."
    },
    {
        "id": "lit_gaba_sesamin_08",
        "title": "GABA 協同芝麻素對銀髮族睡眠障礙與自律神經放鬆之臨床實證",
        "authority": "美國睡眠醫學會 (AASM 臨床指引) & 日本機能性表示食品 (CAA)",
        "category": "睡眠與神經放鬆",
        "ingredient": "GABA (γ-胺基丁酸) & Sesamin (芝麻素)",
        "evidenceLevel": "Level 2 (隨機雙盲安慰劑對照臨床試驗)",
        "recommendedDose": "GABA 100-250mg + 芝麻素 10-15mg / 睡前 30-60 分鐘食用",
        "mechanism": "GABA 作為中樞神經系統主要抑制性神經傳導物質，能活化 GABA-A 受體，提升副交感神經活性，誘導深層慢波睡眠。",
        "contraindications": "避免與抗焦慮處方鎮靜劑 (Benzodiazepines) 同時大量服用；嚴重低血壓患者應監測血壓變化。",
        "targetSymptoms": ["失眠睡不好", "入睡困難", "淺眠多夢", "自律神經失調", "焦慮緊繃"],
        "citation": "Yamatsu A, et al. Effect of oral GABA on sleep and autonomic nervous system. Food Sci Biotechnol. 2016;25(2):547-551."
    },
    # --- EXPANDED ELDER INGREDIENTS & CLINICAL GUIDELINES ---
    {
        "id": "lit_red_yeast_09",
        "title": "紅麴萃取物 (Monacolin K) 調節膽固醇之臨床療效與 Statin 交互作用警示",
        "authority": "台灣衛福部食藥署 (TFDA 警示) & 歐洲食品安全局 (EFSA)",
        "category": "心血管與血脂",
        "ingredient": "Red Yeast Rice (紅麴 / Monacolin K)",
        "evidenceLevel": "Level 1 (臨床隨機對照試驗與安全性警示)",
        "recommendedDose": "每日 Monacolin K 4.8mg ~ 10mg（TFDA 規範每日上限 15mg）",
        "mechanism": "Monacolin K 結構與降血脂處方藥 Lovastatin 相同，競爭性抑制肝臟 HMG-CoA 還原酶，阻斷內生性膽固醇生合成。",
        "contraindications": "【TFDA 重大黑框警語】嚴禁與 Statin 類處方降血脂藥 (Atorvastatin, Rosuvastatin) 併用，否則血中濃度疊加，引發『橫紋肌溶解症』、肌肉壞死與急性腎衰竭！肝腎功能不全者禁用。",
        "targetSymptoms": ["總膽固醇偏高", "低密度膽固醇 (LDL) 偏高", "心血管保健", "血脂代謝異常"],
        "citation": "TFDA 衛署食字第 0960408532 號公告 & EFSA Journal 2018;16(8):5368."
    },
    {
        "id": "lit_nattokinase_10",
        "title": "納豆激酶 (Nattokinase) 纖維蛋白溶解與抗血栓作用之臨床實證",
        "authority": "日本納豆激酶協會 (JNKA) & 台灣衛福部食藥署 (TFDA)",
        "category": "循環與血栓預防",
        "ingredient": "Nattokinase (納豆激酶 / 納豆菌發酵物)",
        "evidenceLevel": "Level 2 (人體臨床血栓指標試驗)",
        "recommendedDose": "每日 2,000 FU (Fibrin Units) / 晚餐後或睡前食用",
        "mechanism": "具直接水解血栓纖維蛋白活性，並刺激血管內皮細胞釋放組織型纖維蛋白溶酶原活化劑 (t-PA)，預防夜間微血栓形成。",
        "contraindications": "【重大禁忌】嚴禁與處方抗凝血藥 (Warfarin, NOAC) 或抗血小板藥 (Aspirin, Plavix) 併用，會引發嚴重自發性內出血、腦出血或消化道潰瘍出血！手術前兩週停用。",
        "targetSymptoms": ["血液循環不良", "手腳冰冷", "血栓預防", "高黏稠血症", "心腦血管保養"],
        "citation": "Kurosawa Y, et al. A single dose of oral nattokinase potentiates thrombolysis and anticoagulation. Sci Rep. 2015;5:11601."
    },
    {
        "id": "lit_ginkgo_11",
        "title": "銀杏葉標準萃取物 (EGb 761) 對末梢循環障礙與認知機能之實證研究",
        "authority": "世界衛生組織 (WHO Monographs) & 歐洲藥品管理局 (EMA)",
        "category": "腦部與末梢循環",
        "ingredient": "Ginkgo Biloba Leaf Extract (銀杏葉萃取物 EGb 761)",
        "evidenceLevel": "Level 1 (系統性回顧與 Cochrane 臨床分析)",
        "recommendedDose": "每日 120mg ~ 240mg 標準化萃取物 (含 24% 銀杏黃酮配醣體、6% 萜類內酯)",
        "mechanism": "清除自由基並強力抑制血小板活化因子 (PAF)，改善血液流變學，增加腦部微血管及末梢動脈血流灌注。",
        "contraindications": "【重大出血警示】具強效抗血小板凝集活性，嚴禁與抗凝血藥 (Warfarin) 或阿斯匹靈併用；易導致顱內出血或創面大量滲血；手術前 14 天必須停用。",
        "targetSymptoms": ["末梢血液循環不良", "手腳冰冷麻木", "注意力記憶力減退", "間歇性跛行", "耳鳴眩暈"],
        "citation": "World Health Organization. WHO Monographs on Selected Medicinal Plants - Volume 1, Ginkgo folium. 1999."
    },
    {
        "id": "lit_ucii_12",
        "title": "非變性二型膠原蛋白 (UC-II) 透過口服免疫耐受調節關節炎之多中心 RCT",
        "authority": "美國國家衛生研究院 (NIH PubMed) & 國際骨關節研究學會 (OARSI)",
        "category": "骨骼關節",
        "ingredient": "UC-II (Undenatured Type II Collagen / 非變性第二型膠原蛋白)",
        "evidenceLevel": "Level 1 (隨機雙盲對照臨床試驗)",
        "recommendedDose": "每日 40mg (含非變性二型膠原蛋白 10mg) / 空腹食用",
        "mechanism": "於腸道派氏結 (Peyer's Patches) 誘發口服免疫耐受 (Oral Tolerance)，刺激調節型 T 細胞 (Treg) 遷移至關節軟骨，抑制發炎並促進軟骨基質修復。",
        "contraindications": "對禽肉類蛋白質嚴重過敏者慎用；與抗凝血藥無已知重大交互作用，心血管親友可安心食用。",
        "targetSymptoms": ["膝蓋卡卡不順", "上下樓梯膝蓋痠軟", "關節僵硬", "活動受限", "退化性關節炎保養"],
        "citation": "Lugo JP, et al. Efficacy and tolerability of an undenatured type II collagen supplement in modulating knee osteoarthritis symptoms. Nutr J. 2016;15:14."
    },
    {
        "id": "lit_vitamin_b_13",
        "title": "高單位活性維生素 B 群 (B1, B6, B12) 對親友末梢神經修復之實證指南",
        "authority": "台灣衛福部食藥署 (TFDA 臨床指引) & 國際神經學聯盟 (WFN)",
        "category": "神經與活力代謝",
        "ingredient": "Active Vitamin B Complex (活性 B1 / 活化 B6 / 甲鈷胺 Methyl-B12)",
        "evidenceLevel": "Level 1 (隨機對照試驗與神經傳導檢查實證)",
        "recommendedDose": "B1 50mg + B6 50mg + 活性 B12 (甲鈷胺) 500-1,000μg / 每日",
        "mechanism": "甲鈷胺 (Methylcobalamin) 作為輔酶參與髓鞘磷脂合成，促進受損周圍神經纖維再生與軸突傳導，改善糖尿病或退化引起的四肢發麻。",
        "contraindications": "高劑量 B6 長期超過 200mg/日可能引發感覺神經病變；請依包裝建議劑量服用，尿液變深黃屬正常核黃素代謝現象。",
        "targetSymptoms": ["手麻腳麻", "四肢末梢刺痛感", "慢性疲勞", "神經痛", "貧血頭暈"],
        "citation": "Head KA. Peripheral neuropathy: pathogenic mechanisms and alternative therapies. Altern Med Rev. 2006;11(4):294-329."
    },
    {
        "id": "lit_zinc_wound_14",
        "title": "甘胺酸鋅與高優質蛋白質對銀髮族皮膚創面與燙傷組織癒合之臨床指引",
        "authority": "美國腸道與靜脈營養學會 (ASPEN) & 歐洲臨床營養學會 (ESPEN)",
        "category": "創傷組織修復",
        "ingredient": "Zinc Glycinate (螯合鋅) + Whey Protein (乳清蛋白質)",
        "evidenceLevel": "Level 1 (ESPEN 臨床創傷照護指南)",
        "recommendedDose": "元素鋅 15mg ~ 30mg / 每日 + 高生物價蛋白質 1.2~1.5g/kg 體重",
        "mechanism": "鋅是人體 DNA 聚合酶、基質金屬蛋白酶 (MMP) 及上皮細胞生長之關鍵輔因子，能加速纖維母細胞合成膠原蛋白，加快創面結痂與肉芽組織生長。",
        "contraindications": "避免與四環黴素、氟喹諾酮抗生素或鐵劑同服（間隔 2 小時）；過量（>40mg/日）可能干擾銅吸收。",
        "targetSymptoms": ["燙傷創面修復", "壓瘡褥瘡", "術後傷口癒合慢", "皮膚脆弱破皮", "指甲毛髮生長不良"],
        "citation": "ESPEN guideline on clinical nutrition in the intensive care unit. Clin Nutr. 2019;38(1):48-79."
    },
    {
        "id": "lit_cranberry_mannose_15",
        "title": "高濃縮蔓越莓 PACs 與 D-甘露糖對高齡者復發性泌尿道感染之考科藍回顧",
        "authority": "考科藍合作組織 (Cochrane Database) & 歐洲泌尿科醫學會 (EAU)",
        "category": "泌尿道健康",
        "ingredient": "Cranberry PACs (原花青素 A 型 36mg) + D-Mannose (D-甘露糖)",
        "evidenceLevel": "Level 1 (Cochrane Systematic Review 2023)",
        "recommendedDose": "前花青素 (PACs) 每日至少 36mg，D-甘露糖 1,000mg ~ 2,000mg / 每日",
        "mechanism": "A 型原花青素與 D-甘露糖可競爭性結合致病性大腸桿菌 (UPEC) 表面的 I 型纖毛與 P 纖毛，阻斷細菌附著於尿路上皮，隨尿液排出。",
        "contraindications": "【重大交互作用】高濃縮蔓越莓會抑制肝臟 CYP2C9 酵素，使抗凝血藥 (Warfarin) 代謝減慢，造成血中濃度劇增與大出血風險；Warfarin 患者嚴禁高劑量飲用！",
        "targetSymptoms": ["頻尿尿急", "排尿灼熱不適", "復發性泌尿道感染", "銀髮女性私密保養", "憋尿發炎"],
        "citation": "Williams G, et al. Cranberries for preventing urinary tract infections. Cochrane Database of Systematic Reviews. 2023;Issue 11."
    }
]

# =========================================================================
# MEDICAL VECTOR STORE IMPLEMENTATION
# (High-Dimensional Semantic Embeddings + Persistent In-Memory Index)
# =========================================================================
class MedicalVectorStore:
    def __init__(self, index_file: str = "backend/vector_store.json"):
        self.index_file = os.path.abspath(index_file) if not os.path.isabs(index_file) else index_file
        self.documents: List[Dict[str, Any]] = FULL_CLINICAL_LITERATURES
        self.vocabulary: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_vectors: List[Dict[str, float]] = []
        self._build_index()

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into Chinese characters, 2-grams, and English words."""
        cleaned = re.sub(r'[^\w\s\u4e00-\u9fa5]', ' ', text.lower())
        tokens = []
        # English words & numbers
        words = re.findall(r'[a-zA-Z0-9]+', cleaned)
        tokens.extend(words)
        # Chinese characters and 2-grams
        chinese_chars = re.findall(r'[\u4e00-\u9fa5]', cleaned)
        tokens.extend(chinese_chars)
        for i in range(len(chinese_chars) - 1):
            tokens.append(chinese_chars[i] + chinese_chars[i+1])
        return tokens

    def _build_index(self):
        """Construct TF-IDF semantic vector space for all 15 clinical documents."""
        doc_count = len(self.documents)
        doc_tokens_list = []
        df: Dict[str, int] = {}

        for doc in self.documents:
            full_text = f"{doc['title']} {doc['ingredient']} {doc['category']} {' '.join(doc['targetSymptoms'])} {doc['mechanism']} {doc['contraindications']}"
            tokens = self._tokenize(full_text)
            doc_tokens_list.append(tokens)
            unique_tokens = set(tokens)
            for t in unique_tokens:
                df[t] = df.get(t, 0) + 1

        # Calculate IDF
        for t, count in df.items():
            self.idf[t] = math.log((doc_count + 1) / (count + 1)) + 1.0

        # Calculate Normalized TF-IDF Vectors
        self.doc_vectors = []
        for tokens in doc_tokens_list:
            vec: Dict[str, float] = {}
            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            length = 0.0
            for t, count in tf.items():
                w = count * self.idf.get(t, 1.0)
                vec[t] = w
                length += w * w
            length = math.sqrt(length) if length > 0 else 1.0
            for t in vec:
                vec[t] /= length
            self.doc_vectors.append(vec)

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Semantic vector retrieval via Cosine Similarity in high-dimensional space."""
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return []

        # Build Query Vector
        q_vec: Dict[str, float] = {}
        tf: Dict[str, int] = {}
        for t in q_tokens:
            tf[t] = tf.get(t, 0) + 1
        q_len = 0.0
        for t, count in tf.items():
            w = count * self.idf.get(t, 1.0)
            q_vec[t] = w
            q_len += w * w
        q_len = math.sqrt(q_len) if q_len > 0 else 1.0
        for t in q_vec:
            q_vec[t] /= q_len

        # Compute Cosine Similarity against all documents
        scores: List[tuple] = []
        for idx, doc_vec in enumerate(self.doc_vectors):
            dot_product = 0.0
            for t, val in q_vec.items():
                if t in doc_vec:
                    dot_product += val * doc_vec[t]
            scores.append((dot_product, self.documents[idx]))

        scores.sort(key=lambda x: x[0], reverse=True)
        # Return matched documents with score >= 0.12 (normalized threshold)
        results = []
        for score, doc in scores:
            if score >= 0.10:
                doc_copy = dict(doc)
                doc_copy["vector_score"] = round(float(score), 4)
                results.append(doc_copy)
            if len(results) >= top_k:
                break
        return results

# Singleton instance for quick access
global_vector_store = MedicalVectorStore()
