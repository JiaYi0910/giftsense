# -*- coding: utf-8 -*-
"""
暖心選物商品資料庫（init_db 每次啟動都會同步到 recommendation_products）

- 價格：2026/10/13 逐一到四家藥局官方網路商店查詢的實際售價（非會員價、非 App 價）。
- 比價：只有「同品項、同包裝」的報價才列入全網最低評比；
  包裝不同（例如只賣 2 箱組、90 錠裝）或缺貨的報價標 comparable=False，仍會顯示但不參與比價。
- 比對：match_conditions 命中親友病況才推薦；primary_conditions 是主要對應病況（加權）；
  exclude_conditions 命中時一律不推薦（例如服用抗凝血劑者不推薦魚油、Q10）。
- match_conditions 含「日常」代表一般保養品，親友沒有特定病況時可作為一般推薦。
"""

PRICE_CHECKED_AT = "2026/10/13"

GREATTREE = "大樹藥局"
MEDFIRST = "杏一醫療"
WOODPECKER = "啄木鳥藥局"
TINTIN = "丁丁藥局"


def _greattree(sale_id: str) -> str:
    return f"https://shop.greattree.com.tw/product?SaleID={sale_id}"


def _medfirst(page_id: str) -> str:
    return f"https://www.medfirst.com.tw/SalePage/Index/{page_id}"


def _woodpecker(product_id: str) -> str:
    return f"https://www.woodpecker.com.tw/products_detail/{product_id}"


def _tintin(product_id: str) -> str:
    return f"https://www.norbelbaby.com.tw/nec/product/{product_id}/view"


def _price(pharmacy: str, price: int, url: str, note: str = "", comparable: bool = True) -> dict:
    return {
        "pharmacy": pharmacy,
        "price": price,
        "url": url,
        "note": note,
        "comparable": comparable,
        "badge": "",
    }


def _product(**p) -> dict:
    """補上全網最低價、推薦藥局與 is_lowest（只在可比較的報價中評比）。"""
    prices = sorted(p["pharmacy_comparison"], key=lambda x: (not x["comparable"], x["price"]))
    comparable = [x for x in prices if x["comparable"]]
    lowest = min(x["price"] for x in comparable) if comparable else 0
    for x in prices:
        # 至少兩家同規格報價才標「同規格最低」
        x["is_lowest"] = len(comparable) >= 2 and x["comparable"] and x["price"] == lowest
        if x["is_lowest"]:
            x["badge"] = "同規格最低"
    best = next((x for x in prices if x["is_lowest"]), prices[0])
    return {
        "sku": "",
        "ean_13": "",
        "primary_conditions": [],
        "exclude_conditions": [],
        **p,
        "pharmacy_comparison": prices,
        "best_price": best["price"],
        "recommended_pharmacy": best["pharmacy"],
        "official_url": best["url"],
        "price_checked_at": PRICE_CHECKED_AT,
    }


DEFAULT_RECOMMENDATION_PRODUCTS = [
    # ── 一般保養（親友沒有特定病況時也可推薦） ──
    _product(
        id="rec_quaker_01",
        product_name="【桂格】完膳營養素 原味無糖 (250ml×24罐/箱)",
        category="均衡營養 / 無糖低 GI",
        spec="250ml × 24罐/箱",
        search_kw="桂格完膳 原味無糖",
        match_conditions=["糖尿病", "血糖", "糖", "營養", "食慾", "體重", "咀嚼", "吞嚥", "術後", "日常"],
        primary_conditions=["糖尿病", "血糖"],
        exclude_conditions=["腎", "透析", "warfarin", "抗凝血"],
        match_reason="無糖、低 GI 的均衡營養配方，適合需要留意血糖、食慾較差或想補充營養的親友。腎臟病或需限制蛋白質、水分者請改用醫師或營養師建議的專用配方；含維生素 K，服用抗凝血劑者請先詢問醫師。",
        pharmacy_comparison=[
            _price(TINTIN, 1368, _tintin("2022030059")),
            _price(GREATTREE, 1390, _greattree("2108300556"), "原價 $1,680"),
            _price(MEDFIRST, 1390, _medfirst("7497037"), "送 2 罐"),
            _price(WOODPECKER, 1390, _woodpecker("819")),
        ],
    ),
    _product(
        id="rec_lutein_01",
        product_name="【HAC 永信】晶亮葉黃膠囊 (120粒/瓶)",
        category="視力保養",
        spec="120粒/瓶",
        search_kw="HAC 晶亮葉黃",
        match_conditions=["眼", "視力", "白內障", "黃斑", "乾眼", "用眼", "3c", "日常"],
        primary_conditions=["眼", "視力", "黃斑"],
        match_reason="葉黃素是常見的視力保養補充品，適合長時間用眼或想保養眼睛的親友。已有眼疾者請持續回診，補充品不能取代治療。",
        pharmacy_comparison=[
            _price(MEDFIRST, 1760, _medfirst("7498415"), "原價 $2,000"),
            _price(GREATTREE, 1800, _greattree("2107220228"), "原價 $1,900"),
            _price(TINTIN, 3200, _tintin("2440213"), "2 入禮盒，約 $1,600／瓶", comparable=False),
        ],
    ),
    _product(
        id="rec_probiotics_01",
        product_name="【日本味王】暢快人生 奇異果精華版 (30包/盒)",
        category="腸道保養",
        spec="5g × 30包/盒",
        search_kw="味王 暢快人生",
        match_conditions=["便秘", "排便", "腸胃", "腸道", "消化", "脹氣", "日常"],
        primary_conditions=["便秘", "排便"],
        exclude_conditions=["化療", "放療"],
        match_reason="含益生菌與奇異果精華，幫助維持消化道機能、讓排便順暢。長期便秘或排便習慣突然改變，請先就醫檢查；化療、放療期間請先詢問主治醫師。",
        pharmacy_comparison=[
            _price(GREATTREE, 420, _greattree("2107220336"), "原價 $680"),
            _price(MEDFIRST, 499, _medfirst("7505961"), "原價 $680"),
        ],
    ),
    _product(
        id="rec_vitc_01",
        product_name="【善存】維他命 C 甜嚼錠 500mg (60錠/瓶)",
        category="免疫保養",
        spec="500mg × 60錠/瓶",
        search_kw="善存 維他命C 甜嚼錠",
        match_conditions=["感冒", "免疫", "流感", "咳", "呼吸", "鼻炎", "抵抗力", "日常"],
        primary_conditions=["感冒", "免疫", "流感"],
        exclude_conditions=["腎結石", "洗腎", "透析", "化療", "放療"],
        match_reason="補充維生素 C，幫助維持免疫力，換季時的日常保養。甜嚼錠含糖，需控制血糖者請留意；有腎結石或洗腎者請先詢問醫師。",
        pharmacy_comparison=[
            _price(MEDFIRST, 251, _medfirst("7498192")),
            _price(GREATTREE, 279, _greattree("2107220515")),
            _price(TINTIN, 279, _tintin("2341850")),
        ],
    ),

    # ── 骨骼關節 ──
    _product(
        id="rec_glucosamine_01",
        product_name="【挺立】UC-II 關鍵迷你錠 (30錠/盒)",
        category="關節保養",
        spec="30錠/盒",
        search_kw="挺立 UC-II",
        match_conditions=["膝蓋", "關節", "退化", "骨關節", "爬樓梯"],
        primary_conditions=["膝蓋", "關節", "退化"],
        match_reason="UC-II 非變性第二型膠原蛋白，一天一顆的關節保養補充品，適合膝蓋、關節不適的親友。關節紅腫熱痛或疼痛加劇請先就醫。",
        pharmacy_comparison=[
            _price(GREATTREE, 849, _greattree("2107220506")),
            _price(MEDFIRST, 949, _medfirst("7508573"), "原價 $999"),
            _price(TINTIN, 999, _tintin("2360612")),
        ],
    ),
    _product(
        id="rec_calcium_01",
        product_name="【挺立】鈣強力錠 (88錠/盒)",
        category="骨骼保養",
        spec="88錠/盒",
        search_kw="挺立 鈣強力錠",
        match_conditions=["骨質", "骨鬆", "骨折", "抽筋", "跌倒"],
        primary_conditions=["骨質", "骨鬆", "骨折"],
        exclude_conditions=["腎結石", "洗腎", "透析"],
        match_reason="補充鈣質與維生素 D，幫助維持骨骼健康。與甲狀腺素、部分抗生素需間隔服用；有腎結石或洗腎者請先詢問醫師。",
        pharmacy_comparison=[
            _price(MEDFIRST, 656, _medfirst("7508574"), "原價 $759"),
            _price(GREATTREE, 729, _greattree("2608070008")),
        ],
    ),

    # ── 腎臟病營養（洗腎／未洗腎配方不同，不可互換） ──
    _product(
        id="rec_suplena_01",
        product_name="【亞培】勝補納 未洗腎病患專用營養品 (237ml×24罐/箱)",
        category="腎臟病營養 / 未洗腎",
        spec="237ml × 24罐/箱",
        search_kw="亞培 勝補納",
        match_conditions=["腎", "腎臟", "慢性腎", "未洗腎", "腎功能", "ckd"],
        primary_conditions=["慢性腎", "未洗腎", "腎臟", "腎功能"],
        exclude_conditions=["洗腎", "透析"],
        match_reason="低蛋白、低磷鉀的腎臟病專用配方，適合尚未洗腎的慢性腎臟病親友。已在洗腎者請改用洗腎專用配方；使用量請依腎臟科醫師或營養師指示。",
        pharmacy_comparison=[
            _price(MEDFIRST, 2790, _medfirst("7490055"), "送 2 罐"),
            _price(TINTIN, 2880, _tintin("2022030035")),
            _price(GREATTREE, 5520, _greattree("2110280279"), "2 箱組，約 $2,760／箱", comparable=False),
        ],
    ),
    _product(
        id="rec_nepro_01",
        product_name="【亞培】普寧勝 洗腎病患專用營養品 (237ml×24罐/箱)",
        category="腎臟病營養 / 洗腎中",
        spec="237ml × 24罐/箱",
        search_kw="亞培 普寧勝",
        match_conditions=["洗腎", "透析", "血液透析", "腹膜透析"],
        primary_conditions=["洗腎", "透析", "血液透析", "腹膜透析"],
        match_reason="高蛋白、低磷鉀的洗腎專用配方，補充透析時流失的蛋白質。尚未洗腎者不適用；使用量請依腎臟科醫師或營養師指示。",
        pharmacy_comparison=[
            _price(MEDFIRST, 2790, _medfirst("7490054"), "送 2 罐"),
            _price(TINTIN, 2880, _tintin("2022030033")),
            _price(GREATTREE, 5520, _greattree("2507170031"), "2 箱組，約 $2,760／箱", comparable=False),
        ],
    ),

    # ── 癌症治療期間營養 ──
    _product(
        id="rec_prosure_01",
        product_name="【亞培】倍力素 癌症專用營養品 (220ml×24罐/箱)",
        category="癌症營養",
        spec="220ml × 24罐/箱",
        search_kw="亞培 倍力素",
        match_conditions=["癌", "化療", "放療", "腫瘤", "標靶"],
        primary_conditions=["癌", "化療", "放療", "腫瘤"],
        exclude_conditions=["腎", "透析", "warfarin", "抗凝血"],
        match_reason="含 EPA 的高蛋白營養配方，適合癌症治療期間體重下降、食慾差的親友。請先和主治醫師或營養師確認是否適用與每日用量。",
        pharmacy_comparison=[
            _price(TINTIN, 5424, _tintin("2022030001"), "送 2 罐"),
            _price(MEDFIRST, 5475, _medfirst("7490044"), "送 2 罐"),
            _price(WOODPECKER, 5699, _woodpecker("3243"), "送 2 罐"),
            _price(GREATTREE, 10380, _greattree("2108300536"), "2 箱組，約 $5,190／箱", comparable=False),
        ],
    ),

    # ── 日常活力 ──
    _product(
        id="rec_bcomplex_01",
        product_name="【克補】B 群 + 鐵加強錠 (100錠/瓶)",
        category="日常活力",
        spec="100錠/瓶",
        search_kw="克補 B群 鐵",
        match_conditions=["疲勞", "熬夜", "加班", "累", "上班族", "壓力", "精神", "元氣"],
        primary_conditions=["疲勞", "熬夜", "加班"],
        match_reason="補充維生素 B 群與鐵，適合作息忙碌、容易疲倦的親友。含鐵，與甲狀腺素、部分抗生素需間隔服用；持續疲倦請就醫檢查原因。",
        pharmacy_comparison=[
            _price(GREATTREE, 720, _greattree("2107220504")),
            _price(TINTIN, 805, _tintin("2330702")),
            _price(WOODPECKER, 719, _woodpecker("1371"), "目前缺貨", comparable=False),
            _price(MEDFIRST, 705, _medfirst("7508520"), "90 錠裝", comparable=False),
        ],
    ),

    # ── 心血管 ──
    _product(
        id="rec_fishoil_01",
        product_name="【歐3加福】精萃濃縮 EPA 魚油 (60顆/瓶)",
        category="血脂保養",
        spec="60顆/瓶",
        search_kw="歐3加福 魚油",
        match_conditions=["血脂", "膽固醇", "三酸甘油", "高血脂", "心血管"],
        primary_conditions=["血脂", "膽固醇", "三酸甘油"],
        exclude_conditions=["warfarin", "抗凝血", "阿斯匹靈", "抗血小板", "保栓通", "出血"],
        match_reason="高濃度 EPA 魚油，幫助維持血脂健康。魚油可能增加出血風險，服用抗凝血劑或抗血小板藥物者不建議自行補充，請先詢問醫師。",
        pharmacy_comparison=[
            _price(MEDFIRST, 1512, _medfirst("7504843"), "原價 $1,680"),
            _price(GREATTREE, 1680, _greattree("2107220678"), "任 3 件 $3,360"),
            _price(TINTIN, 1680, _tintin("1490808")),
        ],
    ),
    _product(
        id="rec_q10_01",
        product_name="【愛司盟】輔酵素 Q10 複方膠囊 (60粒/瓶)",
        category="心臟保養",
        spec="60粒/瓶",
        search_kw="愛司盟 Q10",
        match_conditions=["心臟", "心律", "心衰", "冠心", "支架", "心血管"],
        primary_conditions=["心臟", "心衰", "冠心", "支架"],
        exclude_conditions=["warfarin", "抗凝血"],
        match_reason="輔酵素 Q10 是常見的心血管保養補充品。Q10 可能影響抗凝血劑（如 Warfarin）的效果，服用者請勿自行補充；心臟病親友請先詢問醫師。",
        pharmacy_comparison=[
            _price(GREATTREE, 748, _greattree("2206300034")),
            _price(MEDFIRST, 880, _medfirst("10721424"), "買 1 送 1（2 瓶），約 $440／瓶", comparable=False),
        ],
    ),
]
