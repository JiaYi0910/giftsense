import requests
import re
import urllib3
import urllib.parse
import json
import os
import time
from database import save_pharmacy_products, save_recommendation_products, match_recommendation_products
from product_catalog import DEFAULT_RECOMMENDATION_PRODUCTS

urllib3.disable_warnings()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

CACHE_TTL_SECONDS = 24 * 60 * 60
CACHE_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pharmacy_cache.json')

def _normalize_cache_key(keyword: str) -> str:
    text = (keyword or '').strip().lower()
    return text or '__all__'

def _read_cache_store():
    if not os.path.exists(CACHE_FILE_PATH):
        return {}
    try:
        with open(CACHE_FILE_PATH, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}

def _write_cache_store(store):
    with open(CACHE_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(store, f, ensure_ascii=False, indent=2)

def get_cache_status(keyword: str = ""):
    key = _normalize_cache_key(keyword)
    store = _read_cache_store()
    entry = store.get(key)

    if not isinstance(entry, dict):
        return {
            'key': key,
            'exists': False,
            'is_expired': True,
            'cached_at': None,
            'expires_at': None,
            'ttl_seconds': CACHE_TTL_SECONDS,
            'remaining_seconds': 0
        }

    cached_at = float(entry.get('cached_at', 0) or 0)
    expires_at = float(entry.get('expires_at', 0) or 0)
    now = time.time()
    is_expired = now >= expires_at or now - cached_at > CACHE_TTL_SECONDS

    return {
        'key': key,
        'exists': True,
        'is_expired': is_expired,
        'cached_at': cached_at,
        'expires_at': expires_at,
        'ttl_seconds': CACHE_TTL_SECONDS,
        'remaining_seconds': max(0, int(expires_at - now))
    }


def get_cached_pharmacy_products(keyword: str = ""):
    status = get_cache_status(keyword)
    if not status['exists'] or status['is_expired']:
        return None

    store = _read_cache_store()
    entry = store.get(status['key'])
    if not isinstance(entry, dict):
        return None

    products = entry.get('products')
    if isinstance(products, list):
        return products
    return None


def set_cached_pharmacy_products(keyword: str, products):
    key = _normalize_cache_key(keyword)
    store = _read_cache_store()
    now = time.time()
    store[key] = {
        'cached_at': now,
        'expires_at': now + CACHE_TTL_SECONDS,
        'products': products
    }
    _write_cache_store(store)

def get_pharmacy_search_url(pharmacy: str, keyword: str) -> str:
    clean_kw = re.sub(r'【.*?】', '', keyword).strip()
    clean_kw = re.sub(r'\(.*?\)', '', clean_kw).strip()
    clean_kw = clean_kw.split()[0] if clean_kw.split() else "保健"
    encoded_kw = urllib.parse.quote(clean_kw)
    
    if "大樹" in pharmacy:
        return f"https://shop.greattree.com.tw/searchlist?keyword={encoded_kw}"
    elif "杏一" in pharmacy:
        return f"https://www.medfirst.com.tw/v2/Search?q={encoded_kw}"
    elif "啄木鳥" in pharmacy:
        return f"https://www.woodpecker.com.tw/products_search/all/1?PdSearch={encoded_kw}"
    elif "丁丁" in pharmacy:
        return f"https://www.norbelbaby.com.tw/nec/search?keyword={encoded_kw}"
    else:
        return f"https://shop.greattree.com.tw/searchlist?keyword={encoded_kw}"


def warmup_pharmacy_cache():
    keywords = [
        "保健品",
        "骨骼關節",
        "葡萄糖胺",
        "葉黃素",
        "益生菌",
        "魚油",
        "睡眠",
        "高血壓",
        "親友保健"
    ]
    warmed = []
    for keyword in keywords:
        try:
            items = search_pharmacy_products(keyword)
            if items:
                warmed.append({"keyword": keyword, "count": len(items)})
        except Exception as exc:
            print(f"Warmup cache failed for '{keyword}': {exc}")
    return warmed

# Curated & Verified Real Chain Pharmacy Product SKUs (Taiwan Big 4 Pharmacies)
VERIFIED_PHARMACY_CATALOG = [
    {
        "id": "sku_quaker_01",
        "pharmacy": "大樹藥局",
        "product_name": "【桂格完膳】營養素無糖低 GI 高鈣配方 (24罐/箱)",
        "price": 1480,
        "spec": "250ml x 24罐/箱",
        "category": "親友滋補",
        "tags": ["低GI", "無糖", "高鈣", "糖尿病適用", "零撞藥替代"],
        "url": get_pharmacy_search_url("大樹藥局", "桂格完膳"),
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_quaker_02",
        "pharmacy": "杏一醫療",
        "product_name": "【桂格完膳】營養素無糖低 GI 高鈣配方 (24罐/箱)",
        "price": 1499,
        "spec": "250ml x 24罐/箱",
        "category": "親友滋補",
        "tags": ["低GI", "無糖", "高鈣", "糖尿病適用"],
        "url": get_pharmacy_search_url("杏一醫療", "桂格完膳"),
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_quaker_03",
        "pharmacy": "啄木鳥藥局",
        "product_name": "【桂格完膳】營養素無糖低 GI 高鈣配方 (24罐/箱)",
        "price": 1520,
        "spec": "250ml x 24罐/箱",
        "category": "親友滋補",
        "tags": ["低GI", "無糖", "高鈣"],
        "url": get_pharmacy_search_url("啄木鳥藥局", "桂格完膳"),
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_glucosamine_01",
        "pharmacy": "杏一醫療",
        "product_name": "【維骨力】加強型結晶型硫酸鹽葡萄糖胺膠囊 (500mg x 180粒)",
        "price": 1580,
        "spec": "180粒/盒 (義大利原裝進口)",
        "category": "骨骼關節",
        "tags": ["葡萄糖胺", "膝蓋痛", "ESCEO首選", "無抗凝血衝突"],
        "url": get_pharmacy_search_url("杏一醫療", "維骨力"),
        "image_url": "https://images.unsplash.com/photo-1577401239170-897942555fb3?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_glucosamine_02",
        "pharmacy": "大樹藥局",
        "product_name": "【維骨力】加強型結晶型硫酸鹽葡萄糖胺膠囊 (500mg x 180粒)",
        "price": 1550,
        "spec": "180粒/盒 (義大利原裝進口)",
        "category": "骨骼關節",
        "tags": ["葡萄糖胺", "膝蓋痛", "ESCEO首選", "大樹正品"],
        "url": get_pharmacy_search_url("大樹藥局", "維骨力"),
        "image_url": "https://images.unsplash.com/photo-1577401239170-897942555fb3?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_fishoil_01",
        "pharmacy": "大樹藥局",
        "product_name": "【白蘭氏】深海魚油 + 蝦紅素軟膠囊 (120粒/瓶)",
        "price": 1280,
        "spec": "120粒/瓶 (EPA+DHA 80%高純度)",
        "category": "心血管與循環",
        "tags": ["魚油", "EPA", "DHA", "心血管", "注意Warfarin禁忌"],
        "url": get_pharmacy_search_url("大樹藥局", "魚油"),
        "image_url": "https://images.unsplash.com/photo-1550572017-edd951aa8f72?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_fishoil_02",
        "pharmacy": "丁丁藥局",
        "product_name": "【白蘭氏】深海魚油 + 蝦紅素軟膠囊 (120粒/瓶)",
        "price": 1320,
        "spec": "120粒/瓶 (EPA+DHA 80%高純度)",
        "category": "心血管與循環",
        "tags": ["魚油", "EPA", "DHA", "丁丁正品"],
        "url": get_pharmacy_search_url("丁丁藥局", "魚油"),
        "image_url": "https://images.unsplash.com/photo-1550572017-edd951aa8f72?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_lutein_01",
        "pharmacy": "丁丁藥局",
        "product_name": "【永信藥品】活泉游離型葉黃素 30mg + 玉米黃素 (60粒/瓶)",
        "price": 980,
        "spec": "60粒/瓶 (AREDS 2 黃金比例 10:2)",
        "category": "視力保健",
        "tags": ["葉黃素", "玉米黃素", "視力", "眼睛乾澀"],
        "url": get_pharmacy_search_url("丁丁藥局", "葉黃素"),
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_lutein_02",
        "pharmacy": "杏一醫療",
        "product_name": "【三多】專利亮晶菁游離型葉黃素軟膠囊 (100粒/盒)",
        "price": 850,
        "spec": "100粒/盒 (FloraGLO 專利)",
        "category": "視力保健",
        "tags": ["葉黃素", "FloraGLO", "視力保養"],
        "url": get_pharmacy_search_url("杏一醫療", "葉黃素"),
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_probiotics_01",
        "pharmacy": "大樹藥局",
        "product_name": "【日本味王】消化專利複合益生菌 (60包/盒)",
        "price": 790,
        "spec": "60包/盒 (200億活菌)",
        "category": "腸胃消化",
        "tags": ["益生菌", "腸胃", "排便順暢", "脹氣消化"],
        "url": get_pharmacy_search_url("大樹藥局", "益生菌"),
        "image_url": "https://images.unsplash.com/photo-1577401239170-897942555fb3?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_probiotics_02",
        "pharmacy": "杏一醫療",
        "product_name": "【娘家】益生菌 (60包/盒)",
        "price": 1680,
        "spec": "60包/盒 (NTU 101 單一專利菌株)",
        "category": "腸胃消化",
        "tags": ["娘家益生菌", "NTU101", "調節體質"],
        "url": get_pharmacy_search_url("杏一醫療", "娘家益生菌"),
        "image_url": "https://images.unsplash.com/photo-1577401239170-897942555fb3?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_calcium_01",
        "pharmacy": "大樹藥局",
        "product_name": "【挺立】鈣強力錠 + 活性維生素 D3 (60錠/盒)",
        "price": 499,
        "spec": "60錠/盒 (高吸收檸檬酸鈣)",
        "category": "骨骼關節",
        "tags": ["補鈣", "維生素D3", "骨質疏鬆", "防抽筋"],
        "url": get_pharmacy_search_url("大樹藥局", "挺立"),
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_curcumin_01",
        "pharmacy": "啄木鳥藥局",
        "product_name": "【三得利】極之薑黃薑黃素膠囊 (60粒/瓶)",
        "price": 1150,
        "spec": "60粒/瓶 (高吸收薑黃素)",
        "category": "關節消炎",
        "tags": ["薑黃素", "消炎", "注意活血禁忌"],
        "url": get_pharmacy_search_url("啄木鳥藥局", "薑黃"),
        "image_url": "https://images.unsplash.com/photo-1550572017-edd951aa8f72?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_coq10_01",
        "pharmacy": "大樹藥局",
        "product_name": "【DHC】輔酶 Q10 軟膠囊 (60粒/包)",
        "price": 520,
        "spec": "60粒/包 (每日 30mg 符合TFDA法規)",
        "category": "心肌代謝與活力",
        "tags": ["Q10", "心臟活力", "疲勞", "注意Warfarin禁忌"],
        "url": get_pharmacy_search_url("大樹藥局", "Q10"),
        "image_url": "https://images.unsplash.com/photo-1550572017-edd951aa8f72?w=300",
        "in_stock": 1
    },
    {
        "id": "sku_gaba_01",
        "pharmacy": "杏一醫療",
        "product_name": "【三得利】芝麻明 EX + GABA (90錠/瓶)",
        "price": 1600,
        "spec": "90錠/瓶 (日本原裝睡眠調理)",
        "category": "睡眠與神經放鬆",
        "tags": ["GABA", "芝麻素", "好眠", "放鬆"],
        "url": get_pharmacy_search_url("杏一醫療", "芝麻明"),
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=300",
        "in_stock": 1
    }
]

def scrape_medfirst_live(keyword: str):
    results = []
    try:
        url = f"https://www.medfirst.com.tw/v2/Search?q={keyword}"
        res = requests.get(url, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            titles = re.findall(r'"Title":\s*"([^"]+)"', res.text)
            prices = re.findall(r'"Price":\s*([0-9.]+)', res.text)
            for i in range(min(len(titles), len(prices), 6)):
                t = titles[i]
                p = int(float(prices[i]))
                if p > 0:
                    results.append({
                        "id": f"medfirst_live_{i}_{hash(t)}",
                        "pharmacy": "杏一醫療",
                        "product_name": t,
                        "price": p,
                        "spec": "杏一門市/官網直售",
                        "category": "醫療保健",
                        "tags": ["杏一正品", "即時爬取"],
                        "url": f"https://www.medfirst.com.tw/v2/Search?q={keyword}",
                        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=300",
                        "in_stock": 1
                    })
    except Exception as e:
        print("Live scrape error (graceful fallback):", e)
    return results

def search_pharmacy_products(keyword: str = ""):
    k = keyword.strip().lower()

    cache_status = get_cache_status(k)
    if cache_status['exists'] and not cache_status['is_expired']:
        cached = get_cached_pharmacy_products(k)
        if cached is not None:
            return cached

    # 1. Search verified catalog
    matched = []
    for item in VERIFIED_PHARMACY_CATALOG:
        if not k:
            matched.append(item)
            continue
        text_to_search = f"{item['product_name']} {item['pharmacy']} {item['category']} {' '.join(item['tags'])}".lower()
        if k in text_to_search:
            matched.append(item)

    # 2. If keyword is specific, also try live scrape
    if k and len(matched) < 5:
        live_items = scrape_medfirst_live(keyword)
        matched.extend(live_items)

    # 3. Sort by price
    matched.sort(key=lambda x: x["price"])

    # 4. Cache into JSON with 24h TTL
    if matched:
        set_cached_pharmacy_products(k, matched)
        try:
            save_pharmacy_products(matched)
        except Exception as e:
            print("DB cache error:", e)

    return matched

def get_recommended_products_by_condition(elder_name: str = "親友", condition: str = "日常養生"):
    cond = condition.lower()

    db_result = match_recommendation_products(cond)
    matched = db_result["products"]
    is_fallback = db_result["is_fallback"]
    related_count = db_result["related_count"]
    if not matched:
        # 資料庫尚未建立時，改用 product_catalog 的一般保養商品當作日常保養推薦
        matched = [
            {**p, "is_related": False, "is_top_pick": False}
            for p in DEFAULT_RECOMMENDATION_PRODUCTS if "日常" in p.get("match_conditions", [])
        ][:3]
        is_fallback = True
        related_count = 0

    return {
        "success": True,
        "elder_name": elder_name,
        "elder_condition": condition,
        "total": len(matched),
        "related_count": related_count,
        "is_fallback": is_fallback,
        "products": matched
    }
