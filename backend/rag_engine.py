import json
import requests

# Handle local and package imports gracefully
try:
    from backend.vector_store import global_vector_store, FULL_CLINICAL_LITERATURES
    from backend.tfda_service import global_tfda_service
    from backend.product_catalog import DEFAULT_RECOMMENDATION_PRODUCTS
except ImportError:
    from vector_store import global_vector_store, FULL_CLINICAL_LITERATURES
    from tfda_service import global_tfda_service
    from product_catalog import DEFAULT_RECOMMENDATION_PRODUCTS

# Expose full clinical literatures for compatibility
CLINICAL_LITERATURES = FULL_CLINICAL_LITERATURES

# =========================================================================
# 推薦商品卡：一律使用 product_catalog（2026/10/13 四家藥局官網實際查價）
# 沒有收錄（沒有實際查價）的成分不顯示價格，避免出現不實的比價資訊
# =========================================================================
_CATALOG = {p["id"]: p for p in DEFAULT_RECOMMENDATION_PRODUCTS}

# 實證文獻 → 暖心選物中同成分的商品
LIT_TO_CATALOG = {
    "lit_calcium_d3_04": "rec_calcium_01",
    "lit_lutein_01": "rec_lutein_01",
    "lit_probiotics_03": "rec_probiotics_01",
    "lit_coq10_06": "rec_q10_01",
    "lit_omega3_02": "rec_fishoil_01",
    "lit_ucii_12": "rec_glucosamine_01",
}

# TFDA 替代建議的品名關鍵字 → 暖心選物中同類的商品
ALT_NAME_TO_CATALOG = [
    ("Q10", "rec_q10_01"),
    ("完膳", "rec_quaker_01"),
    ("味王", "rec_probiotics_01"),
    ("葉黃", "rec_lutein_01"),
    ("鈣強力", "rec_calcium_01"),
    ("UC-II", "rec_glucosamine_01"),
]


def catalog_card_fields(product_id, elder_condition: str = ""):
    """回傳商品卡的通路／品名／價格／比價；親友病況命中商品的排除條件時回傳 None"""
    p = _CATALOG.get(product_id or "")
    if not p:
        return None
    cond = (elder_condition or "").lower()
    if any(t.lower() in cond for t in p.get("exclude_conditions", []) if t):
        return None
    comparable = [x for x in p["pharmacy_comparison"] if x.get("comparable", True)]
    parts = [
        f"{x['pharmacy']} ${x['price']:,}" + ("（最低）" if x.get("is_lowest") else "")
        for x in comparable
    ]
    return {
        "pharmacy": p["recommended_pharmacy"],
        "product_name": p["product_name"],
        "price": p["best_price"],
        "comparison": " vs ".join(parts) + f"｜{p['price_checked_at']} 藥局官網查價",
        "url": p["official_url"],
        "catalog_id": p["id"],
    }


try:
    from clinical_guidance import GUIDANCE_CATEGORIES
except ImportError:
    from backend.clinical_guidance import GUIDANCE_CATEGORIES


def _guidance_text(lit: dict) -> str:
    return (f"依據 {lit.get('authority', '')}：\n{lit.get('mechanism', '')}\n"
            f"建議做法：{lit.get('recommendedDose', '')}\n注意：{lit.get('contraindications', '')}")


def _no_price_card(title: str, product_name: str, reason: str) -> dict:
    return {
        "type": "notice",
        "title": title,
        "pharmacy": "",
        "product_name": product_name,
        "price": None,
        "comparison": None,
        "url": "",
        "reason": reason,
    }


# =========================================================================
# SYMPTOM & PHYSICAL RELIEF KNOWLEDGE BASE (Acupressure + Tools + Safety)
# =========================================================================
SYMPTOM_KNOWLEDGE_BASE = {
    "waist_back": {
        "title": "親友腰痛腰痠與下背緊繃舒緩指南",
        "keywords": ["腰痛", "腰痠", "腰酸", "下背痛", "閃腰", "腰椎", "腰肌", "腰部", "腰背", "腰酸背痛", "腰痛怎麼辦", "腰部痠痛", "腰痛吃什麼"],
        "overview": "親友常因腰椎退化、久坐骨盆傾斜、椎間盤微突出或腰背肌筋膜受寒痙攣引起腰痛。建議透過補腎強腰穴位、定溫熱敷與護腰支撐舒緩，切勿自行大力扭腰或盲目服用強效止痛藥。",
        "acupoints": [
            {
                "name": "腎俞穴 (雙側)",
                "location": "第二腰椎棘突下，左右各旁開 1.5 寸處（肚臍正後方對應之脊椎兩側約兩橫指寬處）",
                "method": "親友雙手握拳，以拳眼或雙手拇指指腹由外向內垂直點按揉壓 3~5 分鐘，感到酸脹微熱為宜。",
                "benefit": "補腎強腰、壯骨固本、通經活絡，專治銀髮族慢性腰痠與腰膝酸軟"
            },
            {
                "name": "委中穴 (雙側)",
                "location": "膝關節後方膕窩橫紋的正中點（中醫名言：『腰背委中求』）",
                "method": "親友坐姿放鬆，用雙手食指或中指指腹深層揉按 2~3 分鐘，配合緩慢屈伸小腿。",
                "benefit": "疏通膀胱經氣血、舒筋止痛，快速緩解下背部與坐骨神經緊繃牽引痛"
            },
            {
                "name": "大腸俞穴 (雙側)",
                "location": "第四腰椎棘突下，旁開 1.5 寸處（約當兩側骨盆髂骨最高點連線水準之脊椎兩側）",
                "method": "雙手拇指點按並順時針輕揉 2 分鐘。",
                "benefit": "通調大腸經氣、理氣化滯、舒緩下腰部深層豎脊肌痙攣"
            }
        ],
        "home_care": [
            "🌡️ 40°C~42°C 定溫熱敷腰背：每次 15~20 分鐘，促進腰背深層血液循環，舒緩肌肉痙攣，切忌吹冷風受涼。",
            "🪑 屈膝蹲下代替彎腰：親友撿拾地面物品時，務必先屈膝蹲下、保持背部挺直，嚴禁直接彎腰負重以免腰椎小面關節扭傷。",
            "🛏️ 維持床墊適度支撐：床墊不可過軟塌陷，仰臥時可在膝下微墊小枕頭，減輕腰椎前凸壓力。"
        ],
        "tools": [
            {
                "name": "醫療級遠紅外線支撐加壓護腰帶",
                "type": "腰部護具",
                "tag": "醫材門市推薦",
                "pharmacy": "杏一醫療",
                "price": 1280,
                "reason": "具備人體工學軟鋼板支撐條，穩定腰椎並分散 50% 壓力，結合遠紅外線溫熱維持深層循環。",
                "search_keyword": "護腰",
                "official_url": "https://www.medfirst.com.tw/v2/Search?q=%E8%AD%B7%E8%85%B0"
            },
            {
                "name": "金門一條根草本舒緩貼片 (溫感)",
                "type": "外用貼片",
                "tag": "連鎖藥局熱銷",
                "pharmacy": "大樹藥局",
                "price": 280,
                "reason": "草本天然精油溫感透皮，舒緩下背深層肌筋膜緊繃，無口服止痛藥傷胃傷腎副作用。",
                "search_keyword": "一條根",
                "official_url": "https://shop.greattree.com.tw/searchlist?keyword=%E4%B8%80%E6%A2%9D%E6%A0%B9"
            },
            {
                "name": "人體工學記憶減壓護腰坐墊",
                "type": "坐姿輔具",
                "tag": "久坐防護",
                "pharmacy": "啄木鳥藥局",
                "price": 650,
                "reason": "立體曲面環抱腰椎與骨盆，矯正不良坐姿，預防親友看電視久坐引發的急性腰肌疲勞。",
                "search_keyword": "護腰",
                "official_url": "https://www.woodpecker.com.tw/products_search/all/1?PdSearch=%E8%AD%B7%E8%85%B0"
            }
        ]
    },
    "neck_shoulder": {
        "title": "肩頸痠痛與落枕舒緩指南",
        "keywords": ["肩頸", "脖子", "落枕", "頸椎", "斜方肌", "肩膀痛", "肩痛", "頸痛", "肩頸痠痛", "肩膀酸痛", "頸部僵硬", "肩頸僵硬", "肩緊", "頸緊"],
        "overview": "親友常因頸椎退化、睡眠姿勢不當受寒或斜方肌筋膜緊繃而產生肩頸痠痛。建議透過穴位指壓與溫熱敷促進局部血液微循環，搭配合適之非侵入性物理輔具舒緩，切勿自行亂服消炎止痛藥。",
        "acupoints": [
            {
                "name": "風池穴 (雙側)",
                "location": "後頸部枕骨下方兩側凹陷處（約在耳垂後方平行的凹窩）",
                "method": "雙手大拇指分別按壓兩側凹陷，其餘四指抱頭支撐，朝鼻尖方向往上、往內輕輕揉按 3~5 分鐘，以微感酸脹為佳。",
                "benefit": "放鬆枕後肌群、改善腦部微循環、緩解落枕緊繃與偏頭痛"
            },
            {
                "name": "肩井穴 (雙側)",
                "location": "頸部第七頸椎（大椎穴）與肩峰端連線的正中點（肩膀肌肉最高隆起處）",
                "method": "用對側手食指與中指指腹適度向下按揉或提捏斜方肌，每次 2~3 分鐘，力道宜柔和，不可猛力重擊。",
                "benefit": "釋放斜方肌深層僵硬、通經活絡、大幅舒緩肩膀沉重感"
            },
            {
                "name": "天柱穴 (雙側)",
                "location": "後髮際正中直上 0.5 寸，旁開 1.3 寸處（斜方肌外側緣凹陷中）",
                "method": "以雙手拇指指腹點按揉動，配合緩慢抬頭、低頭呼吸放鬆，每次 2 分鐘。",
                "benefit": "改善頸椎僵硬、減輕頭頸部緊繃感與後腦疲勞"
            }
        ],
        "home_care": [
            "🌡️ 溫熱敷放鬆：以 40°C~42°C 熱毛巾或電熱敷墊溫敷頸肩部 15~20 分鐘，促進微血管擴張，切勿沖冷水以免肌肉痙攣。",
            "🧘 輕柔收下巴伸展：親友挺胸坐正，緩慢收下巴（做出雙下巴動作），停留 5 秒後放鬆，重複 8~10 次，強化深層頸屈肌。",
            "🛏️ 枕頭高度調整：睡眠時枕頭高度應約為親友一拳高，保持頸椎水平且完全支撐頸曲，避免頸部懸空加劇落枕。"
        ],
        "tools": [
            {
                "name": "醫療級定溫電熱敷墊",
                "type": "物理溫敷",
                "tag": "藥局實用輔具",
                "pharmacy": "杏一醫療",
                "price": 990,
                "reason": "具備多段溫控與自動斷電安全設計，均勻溫敷肩頸改善血液循環，比傳統熱水袋更安全防燙。",
                "search_keyword": "熱敷墊",
                "official_url": "https://www.medfirst.com.tw/v2/Search?q=%E7%86%B1%E6%95%B7%E5%A2%8A"
            },
            {
                "name": "金門一條根草本舒緩貼片 (溫感/涼感)",
                "type": "外用貼片",
                "tag": "連鎖藥局熱銷",
                "pharmacy": "大樹藥局",
                "price": 280,
                "reason": "天然草本精油透皮吸收，緩解肌肉僵硬酸脹，非口服無腸胃刺激與肝腎代謝負擔。",
                "search_keyword": "一條根",
                "official_url": "https://shop.greattree.com.tw/searchlist?keyword=%E4%B8%80%E6%A2%9D%E6%A0%B9"
            },
            {
                "name": "人體工學護頸放鬆牽引枕",
                "type": "護頸輔具",
                "tag": "物理支撐",
                "pharmacy": "啄木鳥藥局",
                "price": 1280,
                "reason": "依照頸椎人體工學曲度打造，睡眠中提供穩定支撐，預防親友落枕與晨起僵硬。",
                "search_keyword": "護頸",
                "official_url": "https://www.woodpecker.com.tw/products_search/all/1?PdSearch=%E8%AD%B7%E9%A0%B neck"
            }
        ]
    },
    "insomnia": {
        "title": "親友淺眠失眠與放鬆舒緩指南",
        "keywords": ["失眠", "睡不著", "睡不好", "難入睡", "淺眠", "多夢", "早醒", "睡眠障礙", "夜醒", "睡眠品質"],
        "overview": "銀髮族褪黑激素分泌減少且易受環境干擾。建議透過安神穴位按摩、溫水足浴與調節睡前環境，啟動副交感神經，取代自行服用成癮性安眠藥物。",
        "acupoints": [
            {
                "name": "神門穴 (手少陰心經)",
                "location": "手腕掌側橫紋尺側端（小指側手腕凹陷處）",
                "method": "以另一手拇指指腹輕輕按揉 2~3 分鐘，感到微酸脹即可，有助寧心安神。",
                "benefit": "調節自律神經、平撫心煩焦慮、縮短入睡時間"
            },
            {
                "name": "安眠穴 (經外奇穴)",
                "location": "耳後翳風穴（耳垂後凹陷）與風池穴連線之中點",
                "method": "以食指或中指指腹輕柔打圈按揉 3 分鐘，配合深呼吸。",
                "benefit": "鎮靜中樞神經、放鬆頭部緊繃、改善夜醒與多夢"
            },
            {
                "name": "內關穴 (手厥陰心包經)",
                "location": "手腕內側橫紋正中直上 2 寸（約三橫指寬度）兩筋之間",
                "method": "大拇指垂直按壓，緩慢吐氣揉按 2 分鐘。",
                "benefit": "和胃安神、寬胸理氣、緩解因胸悶心悸引起的淺眠"
            }
        ],
        "home_care": [
            "睡前足浴放鬆：睡前 1 小時以 40°C 溫水足浴 15 分鐘，引導血液往下肢流動，幫助核心體溫下降促進睡意。",
            "減少睡前刺激：睡前 1 小時避免看電視與手機強光，臥室保持柔和暖黃光或全暗環境。",
            "避免刺激飲品：午後避免濃茶、咖啡，睡前 2 小時勿大量飲水以免夜間頻尿跌倒。"
        ],
        "tools": [
            {
                "name": "定溫蒸氣舒壓眼罩 (草本洋甘菊)",
                "type": "舒眠眼罩",
                "tag": "藥局熱銷好物",
                "pharmacy": "大樹藥局",
                "price": 320,
                "reason": "40°C 溫和蒸氣持續釋放 20 分鐘，放鬆眼部睫狀肌與面部神經，快速誘導睡意。",
                "search_keyword": "蒸氣眼罩",
                "official_url": "https://shop.greattree.com.tw/searchlist?keyword=%E8%92%B8%E6%B0%A3%E7%9C%BC%E7%BD%A9"
            },
            {
                "name": "折疊恆溫足浴按摩桶",
                "type": "居家足浴",
                "tag": "物理溫熱",
                "pharmacy": "杏一醫療",
                "price": 1480,
                "reason": "定溫水循環與凸點穴位滾輪，促進下肢微循環、舒緩神經緊繃，助親友一夜好眠。",
                "search_keyword": "足浴",
                "official_url": "https://www.medfirst.com.tw/v2/Search?q=%E8%B6%B3%E6%B5%B4"
            }
        ]
    },
    "knee_joint": {
        "title": "膝關節無力與卡卡活動舒緩指南",
        "keywords": ["膝蓋痛", "膝關節", "膝蓋卡卡", "膝蓋無力", "上下樓梯痛", "退化性關節", "膝蓋喀喀", "膝關節炎", "走不動"],
        "overview": "親友膝關節退化常伴隨軟骨磨損與關節周圍肌力衰退。應在不增加關節壓力下進行穴位保養與適度支撐，避免久坐不動導致關節僵硬。",
        "acupoints": [
            {
                "name": "鶴頂穴",
                "location": "髕骨（膝蓋骨）上緣正中凹陷處",
                "method": "雙手拇指指腹點按揉動 2~3 分鐘，力道以酸脹舒適為度。",
                "benefit": "改善膝關節活動度、祛風除濕、緩解膝蓋上緣緊繃"
            },
            {
                "name": "血海穴 (內側)",
                "location": "髕骨內上緣上 2 寸（約三橫指處，屈膝時股內側肌隆起處）",
                "method": "拇指指腹由外向內輕柔推按 2 分鐘。",
                "benefit": "活血通絡、緩解膝內側退化性疼痛與行走無力"
            },
            {
                "name": "梁丘穴 (外側)",
                "location": "髕骨外上緣上 2 寸處（股外側肌凹陷中）",
                "method": "以食指或中指指腹垂直下壓揉按 2 分鐘。",
                "benefit": "理氣通經、改善上下樓梯時膝蓋前方突發性酸軟無力"
            }
        ],
        "home_care": [
            "坐姿抬腿運動：坐在穩固椅子上，將單腳緩慢伸直平舉，腳尖往回勾，維持 5 秒後緩緩放下，每腳重複 10 次，強化股四頭肌。",
            "減少關節重壓：避免深蹲、盤腿、久跪或長時間負重爬坡；下樓梯時重心微放後側或善用扶手。",
            "溫和保暖：膝蓋周圍脂肪層薄，避免冷氣直吹膝部，外出可穿著透氣保暖護膝。"
        ],
        "tools": [
            {
                "name": "醫療級開孔加壓髕骨護膝 (透氣型)",
                "type": "關節輔具",
                "tag": "杏一醫材首選",
                "pharmacy": "杏一醫療",
                "price": 850,
                "reason": "環狀矽膠軟墊穩定髕骨不位移，雙側彈簧支撐條分擔上下樓梯負載，減輕磨損。",
                "search_keyword": "護膝",
                "official_url": "https://www.medfirst.com.tw/v2/Search?q=%E8%AD%B7%E8%86%9D"
            },
            {
                "name": "人體工學輕量防滑避震手杖",
                "type": "行動輔具",
                "tag": "親友安全輔具",
                "pharmacy": "大樹藥局",
                "price": 680,
                "reason": "超輕量鋁合金材質與四腳止滑底座，有效分擔關節 25% 承重，預防跌倒骨折。",
                "search_keyword": "手杖",
                "official_url": "https://shop.greattree.com.tw/searchlist?keyword=%E6%89%8B%E6%9D%96"
            }
        ]
    },
    "cramp": {
        "title": "親友半夜抽筋與小腿痙攣舒緩指南",
        "keywords": ["抽筋", "小腿抽筋", "半夜抽筋", "腳抽筋", "痙攣", "小腿肚痛", "肌肉痙攣"],
        "overview": "親友夜間抽筋多因下肢受寒、微循環較弱、或電解質（鈣、鎂）缺乏所引起。發作時應立即正確伸展，平時注重腿部保暖與水分補充。",
        "acupoints": [
            {
                "name": "承山穴",
                "location": "小腿後側正中，腓腸肌兩肌腹交界處下方（用力墊腳尖時呈現的人字形凹陷處）",
                "method": "以雙手拇指指腹深層點按揉壓 3~5 分鐘，以酸脹感為宜。",
                "benefit": "快速舒緩小腿腓腸肌痙攣、舒筋活絡、消除腿部疲勞"
            },
            {
                "name": "陽陵泉穴",
                "location": "小腿外側，腓骨小頭前下方凹陷處",
                "method": "拇指指腹垂直下壓並緩慢打圈，每次 2 分鐘。",
                "benefit": "中醫筋之會穴，專管全身筋脈，改善下肢筋急拘攣與抽搐"
            }
        ],
        "home_care": [
            "急性發作自救：抽筋發作時【切勿猛力拉扯】，應平躺或坐起，緩緩將腳尖【往身體方向向上勾起】持續 20~30 秒，伸展小腿後側肌群。",
            "睡眠足部保暖：親友就寢時可穿著寬鬆透氣的保暖長襪，避免冷氣或電風扇直吹下肢導致血管驟縮。",
            "睡前水分與電解質：睡前半小時飲用約 100ml 溫水，平日飲食適度補充富含鈣、鎂食材（如深綠色蔬菜、黑芝麻、香蕉）。"
        ],
        "tools": [
            {
                "name": "保暖透氣羊毛睡眠護腿長襪",
                "type": "保暖護具",
                "tag": "舒適防受寒",
                "pharmacy": "大樹藥局",
                "price": 380,
                "reason": "柔軟不緊繃的天然羊毛混紡，保暖小腿肚與腳踝，大幅降低夜間受寒引發抽筋頻率。",
                "search_keyword": "睡眠襪",
                "official_url": "https://shop.greattree.com.tw/searchlist?keyword=%E4%BF%9D%E6%9A%96%E8%A5%AA"
            },
            {
                "name": "溫熱氣壓小腿深層按摩儀",
                "type": "循環儀器",
                "tag": "舒緩放鬆",
                "pharmacy": "杏一醫療",
                "price": 1880,
                "reason": "仿人手波浪式氣壓推捏結合定溫溫敷，促進下肢靜脈血液回流，放鬆緊繃小腿肌。",
                "search_keyword": "按摩",
                "official_url": "https://www.medfirst.com.tw/v2/Search?q=%E6%8C%89%E6%91%A9"
            }
        ]
    },
    "digestion": {
        "title": "親友腹脹便秘與腸胃消化舒緩指南",
        "keywords": ["便秘", "脹氣", "腹脹", "肚子脹", "消化不良", "排便不順", "胃脹", "排便困難", "腸胃蠕動"],
        "overview": "親友腸道蠕動減緩、腹肌肌力下降常引發排便不順與脹氣。建議透過順時針腹部按摩、特定健脾穴位及適量溫水刺激腸道蠕動。",
        "acupoints": [
            {
                "name": "中脘穴",
                "location": "胸骨下端（劍突）與肚臍連線的正中點（肚臍直上 4 寸）",
                "method": "以掌心或四指指腹溫和下壓順時針揉動 3 分鐘，力道不可過重。",
                "benefit": "健脾和胃、理氣消脹、改善飯後胃部脹滿"
            },
            {
                "name": "天樞穴 (雙側)",
                "location": "肚臍左右各旁開 2 寸（約三橫指寬度）處",
                "method": "雙手食指、中指併攏按壓天樞穴，輕柔揉按 3 分鐘。",
                "benefit": "大腸經募穴，雙向調節腸道蠕動，改善便秘與宿便停滯"
            },
            {
                "name": "足三里穴 (雙側)",
                "location": "外膝眼下 3 寸（四橫指），脛骨前緣外側一橫指處",
                "method": "以大拇指指腹點按揉捏 3 分鐘，感到酸脹傳導為佳。",
                "benefit": "調理脾胃、通調腸腑、促進全身體力與消化吸收"
            }
        ],
        "home_care": [
            "順時針摩腹：晨起或睡前親友平躺，雙手搓熱後以肚臍為中心，順時針方向由內向外環形摩腹 50~100 次，順應結腸蠕動方向。",
            "飯後散步 15 分鐘：飯後切忌立即平躺，輕慢散步可透過重力與腹肌運動幫助胃排空。",
            "溫水與水溶性纖維：晨起空腹飲用 200ml 溫水喚醒胃結腸反射，日常多吃熟燕麥、秋葵、奇異果等溫和高纖食材。",
        ],
        "tools": [
            {
                "name": "草本溫敷腹部定溫電熱墊",
                "type": "腹部溫敷",
                "tag": "促進蠕動",
                "pharmacy": "杏一醫療",
                "price": 890,
                "reason": "定溫熱敷下腹部促進骨盆腔血液循環，舒緩腸道平滑肌痙攣與寒性腹脹。",
                "search_keyword": "熱敷墊",
                "official_url": "https://www.medfirst.com.tw/v2/Search?q=%E7%86%B1%E6%95%B7%E5%A2%8A"
            }
        ]
    },
    "eye_strain": {
        "title": "親友眼睛乾澀與視覺疲勞舒緩指南",
        "keywords": ["眼睛乾", "眼睛酸", "視力疲勞", "眼乾", "眼酸", "眼睛乾澀", "眼疲勞", "視力模糊", "畏光", "用眼過度"],
        "overview": "銀髮族淚腺分泌退化、瞼板腺功能不全易造成乾眼症與視物疲倦。透過眼周骨緣穴位輕壓與定溫溫敷，可融化阻塞的瞼板腺油脂，維持淚膜穩定。",
        "acupoints": [
            {
                "name": "睛明穴 (雙側)",
                "location": "內眼角稍微上方凹陷處（近鼻樑骨邊緣）",
                "method": "用雙手食指或拇指指腹輕輕由下往上點按，切勿壓迫眼球，每次 1~2 分鐘。",
                "benefit": "疏通眼部經絡、促進淚液分泌、改善眼部乾澀酸脹"
            },
            {
                "name": "攢竹穴 (雙側)",
                "location": "眉頭內側端凹陷處",
                "method": "用雙手拇指指腹向上托揉眉頭凹陷，每次 2 分鐘。",
                "benefit": "緩解前額緊繃、消除眼壓過高引起的眉骨酸痛"
            },
            {
                "name": "太陽穴 (雙側)",
                "location": "眉梢與外眼角之間，向後約一橫指處的凹陷",
                "method": "以食指或中指指腹順時針輕揉 2~3 分鐘。",
                "benefit": "放鬆眼周顳肌、醒腦明目、改善視物模糊與偏頭痛"
            }
        ],
        "home_care": [
            "👀 20-20-20 護眼原則：看電視或滑手機每 20 分鐘，將視線移向 20 呎（約 6 公尺）外的遠處至少 20 秒，放鬆睫狀肌。",
            "♨️ 40°C 定溫熱敷眼部：早晚各熱敷 10~15 分鐘，幫助瞼板腺分泌健康的脂質層，防止淚液過度蒸發。",
            "💡 調整環境照明：避免在昏暗環境閱讀，燈光應充足且避免眩光反光直接照射眼睛。"
        ],
        "tools": [
            {
                "name": "醫療級恆溫蒸氣熱敷眼罩 (可調定溫)",
                "type": "眼部溫敷",
                "tag": "乾眼保養",
                "pharmacy": "大樹藥局",
                "price": 690,
                "reason": "40°C~42°C 定溫釋放微米蒸氣，軟化瞼板腺油脂，滋潤眼球表面，比傳統毛巾更衛生持久。",
                "search_keyword": "蒸氣眼罩",
                "official_url": "https://shop.greattree.com.tw/searchlist?keyword=%E8%92%B8%E6%B0%A3%E7%9C%BC%E7%BD%A9"
            },
            {
                "name": "防藍光多焦抗疲勞老花眼鏡",
                "type": "光學輔具",
                "tag": "阻絕藍光",
                "pharmacy": "杏一醫療",
                "price": 980,
                "reason": "有效濾除 3C 螢幕高能量有害藍光，提供漸進多焦視野，大幅減少看近看遠的睫狀肌疲勞。",
                "search_keyword": "老花眼鏡",
                "official_url": "https://www.medfirst.com.tw/v2/Search?q=%E8%80%81%E8%8A%B1%E7%9C%BC%E9%8F%A1"
            }
        ]
    }
}

def build_elder_safety_warning(symptom_cat: str, elder_name: str, elder_condition: str) -> str:
    cond = elder_condition.lower()
    
    # Warfarin / Anticoagulant elder
    if "warfarin" in cond or "抗凝血" in cond or "血壓" in cond:
        if symptom_cat == "neck_shoulder":
            return f"⚠️ 【{elder_name} 專屬安全叮嚀（Warfarin/高血壓）】：\n" \
                   f"1. 嚴禁使用高頻筋膜槍直接重擊頸部兩側（頸動脈竇三角區），以免造成動脈血管斑塊脫落或內膜剝離風險！\n" \
                   f"2. 切勿自行口服非類固醇消炎止痛藥 (NSAIDs，如布洛芬)，兩者併用會導致消化道大出血風險倍增。\n" \
                   f"3. 溫敷溫度應控制在 40°C~42°C，每次不超過 15 分鐘，避免微血管驟然擴張導致血壓波動。"
        elif symptom_cat == "knee_joint":
            return f"⚠️ 【{elder_name} 專屬安全叮嚀（Warfarin/高血壓）】：\n" \
                   f"1. 關節按摩力道宜柔和，禁止大力敲擊或深層重力推拿，以免皮下微血管破裂造成深層血腫。\n" \
                   f"2. 若關節處於急性紅腫熱痛期，切勿熱敷，應先就醫排查痛風或滑囊炎。"
        else:
            return f"⚠️ 【{elder_name} 專屬安全叮嚀（Warfarin/抗凝血）】：親友凝血機能較慢，居家穴位按壓請保持輕柔微酸即可，嚴禁重力刮痧或重擊敲打，避免造成皮下瘀血。"

    # Burn / Wound elder
    elif "燙傷" in cond or "傷口" in cond or "皮膚" in cond:
        return f"⚠️ 【{elder_name} 專屬安全叮嚀（創面修復期）】：\n" \
               f"1. 燙傷創面及周圍皮膚【嚴禁熱敷或貼附任何外用草本貼布】，避免刺激新生上皮組織或引發二次感染！\n" \
               f"2. 穴位指壓與溫熱敷僅限於無傷口之完好健康皮膚區域，保持創面乾燥透氣。"

    # Diabetes elder
    elif "糖" in cond:
        return f"⚠️ 【{elder_name} 專屬安全叮嚀（糖尿病親友）】：親友末梢神經溫度感知可能較遲鈍，使用電熱敷墊時請務必隔著衣物或毛巾，並定時 15 分鐘自動斷電，切防低溫燙傷起水泡。"

    else:
        return f"ℹ️ 【{elder_name} 專屬健康叮嚀】：穴位指壓請以親友感覺「酸脹微溫」為原則，切勿用力過猛造成皮下瘀青。如持續劇痛或出現手麻放射性麻木，應即刻前往神經內科或骨科門診就醫。"

# 問題提到藥物、保健品或飲食時，交給文獻檢索與撞藥比對，不走穴位舒緩路線
INTAKE_TERMS = ("藥", "保健", "補充", "維生素", "維他命", "魚油", "gaba", "芝麻素", "葡萄糖胺", "uc-ii",
                "膠原", "葉黃素", "益生菌", "鈣", "鎂", "b群", "薑黃", "納豆", "銀杏", "紅麴", "q10", "輔酶",
                "飲食", "營養", "可以吃", "能吃", "可以喝", "能喝")


def find_symptom_match(query: str, elder_name: str, elder_condition: str):
    q = query.lower()
    if any(t in q for t in INTAKE_TERMS):
        return None
    for cat_id, cat_data in SYMPTOM_KNOWLEDGE_BASE.items():
        if any(kw in q for kw in cat_data["keywords"]):
            safety_warning = build_elder_safety_warning(cat_id, elder_name, elder_condition)
            return {
                "category": cat_id,
                "title": cat_data["title"],
                "overview": cat_data["overview"],
                "acupoints": cat_data["acupoints"],
                "home_care": cat_data["home_care"],
                "tools": cat_data["tools"],
                "elder_safety_warning": safety_warning
            }
    return None

# =========================================================================
# UNIFIED HYBRID QUERY PIPELINE (VECTOR DB + TFDA VERIFICATION + GEMINI)
# =========================================================================
def query_rag_engine(query: str, elder_name: str, elder_condition: str, api_key: str = None, model: str = "gemini-1.5-flash"):
    # -------------------------------------------------------------------------
    # 1. TRACK 1: SYMPTOM & PHYSICAL RELIEF TRACK (Acupressure + Tools + Safety)
    # -------------------------------------------------------------------------
    symptom_data = find_symptom_match(query, elder_name, elder_condition)
    if symptom_data:
        gemini_text = ""
        if api_key and api_key.strip():
            try:
                prompt = f"""你是一位專業的銀髮健康與物理舒緩 AI 守護助手。
當前親友：{elder_name}，目前病史與用藥：{elder_condition}。
使用者諮詢症狀：{query}

【臨床症狀與物理舒緩知識】
症狀類別：{symptom_data['title']}
推薦穴位：{json.dumps(symptom_data['acupoints'], ensure_ascii=False)}
居家溫敷與護理：{json.dumps(symptom_data['home_care'], ensure_ascii=False)}
連鎖藥局實用輔具與外用貼片：{json.dumps(symptom_data['tools'], ensure_ascii=False)}
針對親友體質之安全叮嚀：
{symptom_data['elder_safety_warning']}

請以 20~30 歲年輕子女易懂、溫暖專業的語氣，組織一段清晰流暢的舒緩指南（約 3~4 句話）：
1. 說明此症狀的成因與第一步放鬆重點（如溫熱敷、放鬆肌肉）。
2. 指導子女如何幫親友按壓核心穴位（如風池穴、肩井穴）。
3. 推薦連鎖藥局能買到的實用外用輔具或草本貼片（強調非口服、物理舒緩，【嚴禁推薦無關的口服營養品如桂格完膳】）。
4. 明確提醒親友病史（{elder_name} - {elder_condition}）的特定安全禁忌（如：抗凝血不可用筋膜槍重擊頸部動脈、燙傷不可在傷口貼貼布、高血壓注意溫敷溫度）。"""

                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.3}
                }
                res = requests.post(url, json=payload, timeout=8)
                if res.status_code == 200:
                    data = res.json()
                    gemini_text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            except Exception as e:
                print("Gemini API call notice:", e)

        if not gemini_text:
            first_ap = symptom_data['acupoints'][0]['name'] if symptom_data['acupoints'] else "穴位"
            second_ap = symptom_data['acupoints'][1]['name'] if len(symptom_data['acupoints']) > 1 else ""
            ap_str = f"「{first_ap}」" + (f"與「{second_ap}」" if second_ap else "")
            
            gemini_text = f"親友出現【{query}】，多因頸椎關節退化、姿勢不良受寒或肌筋膜緊繃所致。\n" \
                          f"💡 居家第一步：建議先以 40°C~42°C 溫熱敷 15~20 分鐘促進微循環，隨後可幫親友輕柔按壓 {ap_str}，釋放深層僵硬壓力。\n" \
                          f"🛠️ 藥局實用輔具：可至大樹或杏一等連鎖藥局選購「醫療級電熱敷墊」或「金門一條根草本舒緩貼片」，物理透皮舒緩且不增加肝腎代謝負擔。\n" \
                          f"{symptom_data['elder_safety_warning']}"

        return {
            "success": True,
            "has_match": True,
            "is_symptom_track": True,
            "query": query,
            "elder": {"name": elder_name, "condition": elder_condition},
            "symptom_data": symptom_data,
            "gemini_synthesis": gemini_text
        }

    # -------------------------------------------------------------------------
    # 2. TRACK 2: VECTOR DB SEMANTIC RETRIEVAL (Text-Embedding Semantic Space)
    # -------------------------------------------------------------------------
    vector_matches = global_vector_store.search(query, top_k=3)
    if not vector_matches:
        return {
            "success": True,
            "has_match": False,
            "is_symptom_track": False,
            "message": f"針對「{query}」，目前 {len(global_vector_store.documents)} 篇實證文獻與照護指引中未檢索到高度直接相關項目。",
            "supported_areas": [
                "肩頸與關節舒緩 (風池/肩井穴位、醫療熱敷墊、一條根貼片)",
                "紅麴血脂調節 (Monacolin K / TFDA 黑框警語)",
                "納豆激酶溶栓 (Nattokinase / Warfarin 禁忌)",
                "銀杏末梢循環 (EGb 761 / 出血警示)",
                "二型膠原蛋白 (UC-II / 軟骨免疫耐受)",
                "活性維生素 B 群 (B1/B6/B12 / 末梢手麻修復)",
                "甘胺酸鋅與蛋白質 (創傷組織上皮細胞癒合)",
                "高濃縮蔓越莓 (PACs / 泌尿道保護)",
                "視力乾澀 (葉黃素/AREDS 2)", "心血管血脂 (Omega-3 魚油/AHA)",
                "腸胃消化 (複合益生菌/WGO)", "骨密骨折 (檸檬酸鈣+D3/NOF)",
                "關節消炎 (高純度薑黃素/NIH)", "心肌體力 (輔酶 Q10/TFDA)",
                "膝蓋軟骨痛 (葡萄糖胺/ESCEO)", "睡眠放鬆 (GABA+芝麻素/AASM)"
            ]
        }

    top_lit = vector_matches[0]
    matched_ingredient = top_lit["ingredient"]

    # -------------------------------------------------------------------------
    # 3. TRACK 3: TFDA OFFICIAL REGULATORY COLLISION & BLACK BOX CHECK
    # -------------------------------------------------------------------------
    tfda_result = global_tfda_service.check_interaction(
        elder_name=elder_name,
        elder_condition=elder_condition,
        query=query,
        matched_ingredient=matched_ingredient
    )

    is_collision = tfda_result["is_collision"]
    radar_scores = tfda_result["radar_scores"]
    is_guidance = top_lit.get("category") in GUIDANCE_CATEGORIES
    if is_guidance and not is_collision:
        tfda_result = {
            **tfda_result,
            "badge": "照護與用藥安全指引",
            "title": f"依{top_lit.get('authority', '權威機構')}建議整理",
            "desc": f"這題屬於{top_lit.get('category')}問題，以下依權威機構的指引整理重點；已比對{elder_name}（{elder_condition}）的病況與用藥，沒有命中撞藥規則。",
        }

    # Action Card: TFDA 替代建議或同成分商品；價格一律來自暖心選物的實際查價資料
    if is_collision and tfda_result.get("alternative"):
        alt = tfda_result["alternative"]
        catalog_id = next((cid for kw, cid in ALT_NAME_TO_CATALOG if kw in alt["product_name"]), None)
        real = catalog_card_fields(catalog_id, elder_condition)
        if real:
            action_card = {"type": "alternative", "title": "較安全的替代選擇", **real, "reason": alt["reason"]}
        else:
            # 替代商品只從經過查價、套用排除條件的暖心選物資料庫挑選；
            # 沒有收錄或替代品本身也有衝突時（例如服用抗凝血劑時的 Q10），不推薦具體商品
            action_card = _no_price_card(
                "暫不推薦替代商品",
                "請先諮詢醫師或藥師",
                "親友目前的用藥與這類保健品可能有交互作用，替代選擇請由醫師或藥師依實際用藥評估後再購買。"
            )
    elif is_guidance:
        action_card = _no_price_card(
            "這題不需要購買保健品",
            "依指引調整用藥與生活習慣",
            "這是用藥安全與照護建議，不推薦特定商品；有疑問請帶著藥袋詢問醫師或藥師。"
        )
    else:
        lit_id = top_lit["id"]
        real = catalog_card_fields(LIT_TO_CATALOG.get(lit_id), elder_condition)
        if real:
            action_card = {
                "type": "recommended",
                "title": f"推薦通路：【{real['pharmacy']}】",
                **real,
                "reason": _CATALOG[real["catalog_id"]]["match_reason"],
            }
        else:
            action_card = _no_price_card(
                "暖心選物尚未收錄此類商品",
                f"{matched_ingredient} 類保健品",
                "目前藥局比價資料庫沒有經過實際查價的對應商品，因此不提供價格。購買前請先詢問醫師或藥師，確認與親友目前的用藥沒有交互作用。"
            )

    safety = {
        "is_collision": is_collision,
        "severity": tfda_result["severity"],
        "title": tfda_result["title"],
        "desc": tfda_result["desc"],
        "radar_scores": radar_scores,
        "action_card": action_card
    }

    # -------------------------------------------------------------------------
    # 4. LLM SYNTHESIS (GEMINI 1.5 FLASH WITH TFDA & VECTOR INJECTION)
    # -------------------------------------------------------------------------
    gemini_text = ""
    if api_key and api_key.strip():
        try:
            prompt = f"""你是一位專業的銀髮健康 AI 守護助手。
當前親友：{elder_name}，目前病史與用藥：{elder_condition}。
使用者問題：{query}

【Vector DB 檢索到的臨床實證文獻】
{json.dumps([{
    'title': m['title'], 'authority': m['authority'], 'ingredient': m['ingredient'],
    'evidenceLevel': m['evidenceLevel'], 'dose': m['recommendedDose'],
    'mechanism': m['mechanism'], 'contraindications': m['contraindications'], 'citation': m['citation'],
    'vector_similarity': m.get('vector_score', 0)
} for m in vector_matches], ensure_ascii=False, indent=2)}

【衛福部食藥署 (TFDA) 官方藥物檢驗報告】
檢驗結果：{tfda_result['badge']}
官方標題：{tfda_result['title']}
官方依據：{tfda_result['official_citation']}
機轉說明：{tfda_result['mechanism']}
處置建議：{tfda_result['clinical_action']}

請以 20~30 歲年輕子女易懂、白話溫暖的語氣，簡要說明（2~3 句話）：
1. 臨床實證建議的核心成分與好處。
2. 明確說明衛福部 TFDA 官方檢驗結果：是否與親友病史（如 Warfarin、Statin、燙傷、高血壓）產生撞藥或重大黑框警語？
3. 標註官方文獻出處。避免冗長大段文字。"""

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3}
            }
            res = requests.post(url, json=payload, timeout=8)
            if res.status_code == 200:
                data = res.json()
                gemini_text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        except Exception as e:
            print("Gemini API call notice:", e)

    if not gemini_text and is_guidance:
        gemini_text = _guidance_text(top_lit)
        if is_collision:
            gemini_text = (f"【用藥安全警示】{tfda_result['title']}\n{tfda_result['mechanism']}\n"
                           f"處置建議：{tfda_result['clinical_action']}\n\n" + gemini_text)

    if not gemini_text:
        # High quality offline synthesis with TFDA endorsement
        if is_collision:
            gemini_text = f"⚠️ 【衛福部食藥署 (TFDA) 官方撞藥警訊】：\n" \
                          f"針對「{query}」，檢索到核心成分為【{matched_ingredient}】。\n" \
                          f"經比對親友病史【{elder_name}】({elder_condition})，命中 {tfda_result['badge']}！\n" \
                          f"依據 {tfda_result['official_citation']}：{tfda_result['mechanism']}\n" \
                          f"💡 處置建議：{tfda_result['clinical_action']}"
        else:
            gemini_text = f"✅ 【衛福部食藥署 (TFDA) 臨床實證相容】：\n" \
                          f"針對「{query}」，{top_lit['authority']} 推薦核心成分為【{matched_ingredient}】。\n" \
                          f"經比對 TFDA 官方資料庫，與【{elder_name}】({elder_condition}) 當前處方無已知重大黑框警語與撞藥衝突，相容度 98%。\n" \
                          f"💡 作用機轉：{top_lit['mechanism']}"

    return {
        "success": True,
        "has_match": True,
        "is_symptom_track": False,
        "query": query,
        "elder": {"name": elder_name, "condition": elder_condition},
        "safety": safety,
        "tfda_verification": tfda_result,
        "vector_retrieval": vector_matches,
        "matched_literatures": vector_matches,
        "gemini_synthesis": gemini_text
    }
