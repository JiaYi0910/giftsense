import os
import threading
import time

import requests

# Automatically load .env file if present
def load_env():
    for base_dir in [os.path.dirname(os.path.abspath(__file__)), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]:
        env_path = os.path.join(base_dir, ".env")
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            except Exception:
                pass

load_env()

CWA_BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
CACHE_SECONDS = 600  # 同一縣市 10 分鐘內共用結果，避免每次開首頁都查氣象署

# 各縣市代表性的氣象站（優先使用氣象署局屬站，避免抓到山區測站，例如臺北市不用陽明山）
PREFERRED_STATIONS = {
    "臺北市": ["臺北"], "新北市": ["板橋", "新北"], "基隆市": ["基隆"], "桃園市": ["新屋", "桃園"],
    "新竹市": ["新竹"], "新竹縣": ["新竹", "竹北"], "苗栗縣": ["苗栗", "後龍"], "臺中市": ["臺中"],
    "彰化縣": ["彰化", "田中"], "南投縣": ["南投", "日月潭"], "雲林縣": ["斗六", "古坑"],
    "嘉義市": ["嘉義"], "嘉義縣": ["太保", "嘉義"], "臺南市": ["臺南"], "高雄市": ["高雄"],
    "屏東縣": ["屏東", "恆春"], "宜蘭縣": ["宜蘭"], "花蓮縣": ["花蓮"], "臺東縣": ["臺東"],
    "澎湖縣": ["澎湖"], "金門縣": ["金門"], "連江縣": ["馬祖"],
}

_cache = {}
_obs_cache = {"at": 0.0, "stations": []}
_lock = threading.Lock()


def _get_cwa_parameter(weather_elements, element_name, default=""):
    for elem in weather_elements:
        if elem.get("elementName") == element_name:
            times = elem.get("time", [])
            if times:
                return times[0].get("parameter", {}).get("parameterName", default)
    return default


def _valid(value):
    """氣象署以 -99 / -999 代表缺測"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if v <= -90 else v


def _fetch_forecast(key: str, cwa_city: str):
    """F-C0032-001 一般天氣預報（今明 36 小時）：天氣現象、溫度範圍、降雨機率、舒適度"""
    res = requests.get(
        f"{CWA_BASE}/F-C0032-001",
        params={"Authorization": key, "locationName": cwa_city},
        timeout=8,
    )
    res.raise_for_status()
    records = res.json().get("records", {}).get("location", [])
    if not records:
        return None
    els = records[0].get("weatherElement", [])
    return {
        "wx": _get_cwa_parameter(els, "Wx", ""),
        "min_t": int(float(_get_cwa_parameter(els, "MinT", "0"))),
        "max_t": int(float(_get_cwa_parameter(els, "MaxT", "0"))),
        "pop": int(float(_get_cwa_parameter(els, "PoP", "0") or 0)),
        "ci": _get_cwa_parameter(els, "CI", ""),
    }


def _fetch_observation(key: str, cwa_city: str):
    """O-A0003-001 現在天氣觀測：取得該縣市代表測站的即時氣溫與相對濕度（預報資料不含濕度）"""
    now = time.time()
    if now - _obs_cache["at"] > CACHE_SECONDS or not _obs_cache["stations"]:
        res = requests.get(f"{CWA_BASE}/O-A0003-001", params={"Authorization": key, "format": "JSON"}, timeout=12)
        res.raise_for_status()
        _obs_cache["stations"] = res.json().get("records", {}).get("Station", [])
        _obs_cache["at"] = now
    stations = _obs_cache["stations"]

    def usable(st):
        we = st.get("WeatherElement", {})
        return _valid(we.get("RelativeHumidity")) is not None and _valid(we.get("AirTemperature")) is not None

    by_name = {st.get("StationName"): st for st in stations}
    candidates = [by_name.get(n) for n in PREFERRED_STATIONS.get(cwa_city, [])]
    candidates += [st for st in stations if st.get("GeoInfo", {}).get("CountyName") == cwa_city]
    station = next((st for st in candidates if st and usable(st)), None)
    if not station:
        return None
    we = station["WeatherElement"]
    return {
        "station": station.get("StationName", ""),
        "observed_at": (station.get("ObsTime", {}).get("DateTime") or "")[11:16],
        "temp": round(_valid(we.get("AirTemperature")), 1),
        "humidity": int(round(_valid(we.get("RelativeHumidity")))),
        "weather": we.get("Weather") if we.get("Weather") not in (None, "-99") else "",
    }


def get_live_weather(city: str = "台北市", cwa_api_key: str = None):
    """
    中央氣象署 (CWA) 開放資料：
    - F-C0032-001 一般天氣預報（溫度範圍、天氣現象、降雨機率、舒適度）
    - O-A0003-001 現在天氣觀測（即時氣溫、相對濕度）
    需在環境變數設定 CWA_API_KEY（Render → Environment）。
    """
    key = (cwa_api_key or os.environ.get("CWA_API_KEY", "")).strip()
    # 氣象署官方地名使用正體字「臺」（如：臺北市、臺中市、臺南市、臺東縣）
    cwa_city = city.replace("台", "臺").strip()

    if key:
        with _lock:
            cached = _cache.get(cwa_city)
            if cached and time.time() - cached[0] < CACHE_SECONDS:
                return cached[1]
        try:
            forecast = _fetch_forecast(key, cwa_city)
            if forecast:
                obs = None
                try:
                    obs = _fetch_observation(key, cwa_city)
                except Exception as e:
                    print("CWA 觀測資料取得失敗（仍使用預報資料）:", e)
                humidity = obs["humidity"] if obs else None
                result = {
                    "source": "中央氣象署 (CWA)",
                    "is_fallback": False,
                    "city": city,
                    "cwa_city": cwa_city,
                    "temperature": f"{forecast['min_t']}°C ~ {forecast['max_t']}°C",
                    "condition": forecast["wx"],
                    "comfort": forecast["ci"],
                    "humidity": humidity,
                    "rain_prob": f"{forecast['pop']}%",
                    "current_temp": obs["temp"] if obs else None,
                    "station": obs["station"] if obs else "",
                    "observed_at": obs["observed_at"] if obs else "",
                    "alert": generate_weather_alert(forecast["min_t"], forecast["max_t"], forecast["pop"], humidity),
                }
                with _lock:
                    _cache[cwa_city] = (time.time(), result)
                return result
        except Exception as e:
            print("CWA API 連線異常，改用離線參考值:", e)
        reason = "目前無法連線中央氣象署"
    else:
        reason = "後端尚未設定中央氣象署 API 授權碼（CWA_API_KEY）"

    # 離線參考值：氣象署連不上或尚未設定授權碼時，讓畫面不中斷（前端會標示不是即時資料）
    return {
        "source": "離線參考值",
        "is_fallback": True,
        "fallback_reason": reason,
        "city": city,
        "cwa_city": cwa_city,
        "temperature": "24°C ~ 28°C",
        "condition": "多雲時晴",
        "comfort": "舒適",
        "humidity": 65,
        "rain_prob": "20%",
        "current_temp": None,
        "station": "",
        "observed_at": "",
        "alert": "早晚溫差適中，提醒親友早起散步適時加薄外套、多補充溫開水。"
    }


def generate_weather_alert(min_t, max_t, pop, humidity=None):
    """依據當日氣溫差、降雨機率、濕度與低溫，自動產生親友健康關懷叮嚀"""
    diff = max_t - min_t
    if diff >= 7:
        return f"今日早晚溫差高達 {diff:.1f}°C！高血壓親友晨間外出務必戴帽子保暖。"
    elif pop >= 60:
        return f"今日降雨機率 {pop}%，天雨路滑，請叮嚀親友居家防跌避免走濕滑磁磚。"
    elif humidity is not None and humidity >= 80:
        return f"今日濕度達 {humidity}% 偏高，提醒親友避免長時間悶熱與過度出汗，室內記得通風保持舒適。"
    elif min_t <= 16:
        return f"今日氣溫偏低 (最低 {min_t:.1f}°C)，提醒親友注意末梢血液循環與保暖。"
    else:
        return "今日氣候溫和舒適，適合叮嚀親友多喝溫開水、舒展關節。"
