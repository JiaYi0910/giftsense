import os
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


def _get_cwa_parameter(weather_elements, element_name, default=""):
    for elem in weather_elements:
        if elem.get("elementName") == element_name:
            times = elem.get("time", [])
            if times:
                return times[0].get("parameter", {}).get("parameterName", default)
    return default


def get_live_weather(city: str = "台北市", cwa_api_key: str = None):
    """
    中央氣象署 (CWA) 官方即時天氣觀測與預報 API
    資料集代碼：F-C0032-001 (一般天氣預報-今明 36 小時天氣預報)
    """
    # 1. 優先由參數或 .env 取得 CWA API 授權碼
    key = (cwa_api_key or os.environ.get("CWA_API_KEY", "")).strip()
    if key:
        try:
            # 氣象署官方資料庫地名強制使用正體字「臺」（如：臺北市、臺中市、臺南市、臺東縣）
            cwa_city = city.replace("台", "臺").strip()
            cwa_url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization={key}&locationName={cwa_city}"
            res = requests.get(cwa_url, timeout=6)
            if res.status_code == 200:
                data = res.json()
                records = data.get("records", {}).get("location", [])
                if records:
                    weather_elements = records[0].get("weatherElement", [])
                    wx = _get_cwa_parameter(weather_elements, "Wx", "晴時多雲")
                    min_t = _get_cwa_parameter(weather_elements, "MinT", "22")
                    max_t = _get_cwa_parameter(weather_elements, "MaxT", "28")
                    pop = _get_cwa_parameter(weather_elements, "PoP", "20")
                    rh = _get_cwa_parameter(weather_elements, "RH", "60")
                    ci = _get_cwa_parameter(weather_elements, "CI", "舒適")

                    try:
                        humidity_value = int(float(rh))
                    except (TypeError, ValueError):
                        humidity_value = 60

                    return {
                        "source": "中央氣象署 (CWA) 官方即時觀測",
                        "city": city,
                        "cwa_city": cwa_city,
                        "temperature": f"{min_t}°C ~ {max_t}°C",
                        "condition": wx,
                        "comfort": ci,
                        "humidity": humidity_value,
                        "rain_prob": f"{pop}%",
                        "alert": generate_weather_alert(int(min_t), int(max_t), int(pop), humidity_value)
                    }
        except Exception as e:
            print("CWA API 連線異常，啟用本地安全備援:", e)

    # 2. 本地安全離線備援（若遇斷網或氣象局伺服器維護時，確保系統不中斷）
    return {
        "source": "中央氣象署 (本地安全離線備援)",
        "city": city,
        "cwa_city": city.replace("台", "臺"),
        "temperature": "24°C ~ 28°C",
        "condition": "多雲時晴 🌤️",
        "comfort": "舒適",
        "humidity": 65,
        "rain_prob": "20%",
        "alert": "早晚溫差適中，提醒親友早起散步適時加薄外套、多補充溫開水。"
    }

def generate_weather_alert(min_t, max_t, pop, humidity=None):
    """依據當日氣溫差、降雨機率、濕度與低溫，自動產生親友健康關懷叮嚀"""
    diff = max_t - min_t
    if diff >= 7:
        return f"⚠️ 今日早晚溫差高達 {diff:.1f}°C！高血壓親友晨間外出務必戴帽子保暖。"
    elif pop >= 60:
        return f"🌧️ 今日降雨機率 {pop}%，天雨路滑，請叮嚀親友居家防跌避免走濕滑磁磚。"
    elif humidity is not None and humidity >= 80:
        return f"💧 今日濕度達 {humidity}% 偏高，提醒親友避免長時間悶熱與過度出汗，室內記得通風保持舒適。"
    elif min_t <= 16:
        return f"❄️ 今日氣溫偏低 (最低 {min_t:.1f}°C)，提醒親友注意末梢血液循環與保暖。"
    else:
        return "☀️ 今日氣候溫和舒適，適合叮嚀親友多喝溫開水、舒展關節。"
