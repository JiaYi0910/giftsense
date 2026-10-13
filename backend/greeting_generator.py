import os
import random
import requests
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

WEEKDAY_NAMES = ["一", "二", "三", "四", "五", "六", "日"]

def _season_of(month: int) -> str:
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "autumn"
    return "winter"

SEASON_TEXT = {
    "spring": {"spoiled": "春天到了，花都開了", "taiwanese": "春天來矣，四界花攏開", "reserved": "時值春暖花開"},
    "summer": {"spoiled": "夏天太陽好大", "taiwanese": "熱天日頭赤焱焱", "reserved": "時序入夏，暑氣漸盛"},
    "autumn": {"spoiled": "秋天來了，早晚涼涼的", "taiwanese": "秋天到矣，早暗有較冷", "reserved": "時序入秋，早晚微涼"},
    "winter": {"spoiled": "冬天冷颼颼", "taiwanese": "寒天冷吱吱", "reserved": "時值隆冬，寒意漸濃"},
}

# 依病況挑選的專屬叮嚀（每種語氣各數句，讓不同親友收到不同內容）
CONDITION_CARE_LINES = [
    (("warfarin", "抗凝血", "血壓", "心血管"), {
        "spoiled": [
            "早上起床先在床邊坐 3 分鐘再站起來，血壓藥也要準時吃喔！",
            "今天記得量一下血壓，不要吃太鹹，醬料沾一點點就好～",
            "銀杏、高劑量魚油這些先不要亂吃，有想吃的補品先問我喔！",
        ],
        "taiwanese": [
            "透早起床先坐佇床邊三分鐘才徛起來，血壓藥仔愛準時食喔！",
            "今仔日愛記得量血壓，食物莫食傷鹹，醬料沾淡薄仔就好。",
        ],
        "reserved": [
            "晨起請先於床緣靜坐三分鐘再起身，並請按時服用降壓藥物。",
            "飲食宜清淡少鹽，若欲服用任何補品，請先與醫師確認。",
        ],
        "insight": "【AHA 美國心臟學會臨床指引】清晨為血壓高峰期，起床前先靜坐 3 分鐘可降低姿勢性低血壓與心血管事件風險。",
    }),
    (("糖",), {
        "spoiled": [
            "甜點和含糖飲料要忍住喔，飯後去散步 15 分鐘血糖會更穩～",
            "洗澡水不要太燙，睡前看看腳有沒有小傷口，要好好保護喔！",
            "三餐要定時定量，餓了可以吃一點無糖優格或堅果喔～",
        ],
        "taiwanese": [
            "甜粿、甜飲料愛忍一下，食飽去行行咧十五分鐘，血糖較穩。",
            "洗身軀水莫傷燒，睏前看跤有破空無，愛顧予好喔！",
        ],
        "reserved": [
            "三餐請定時定量，少食甜品，飯後緩步慢行有助血糖平穩。",
            "沐浴水溫請勿過燙，睡前請留意足部有無破皮傷口。",
        ],
        "insight": "【ADA 美國糖尿病學會照護標準】飯後輕度步行 10~15 分鐘可有效降低餐後血糖峰值，並建議每日檢查足部。",
    }),
    (("關節", "膝", "骨", "退化", "肌少"), {
        "spoiled": [
            "走路慢慢來，樓梯能少爬就少爬，膝蓋要好好疼惜喔！",
            "坐久了記得起來動一動，晚上可以熱敷膝蓋 15 分鐘～",
            "多曬一點太陽補維生素 D，骨頭才會勇勇的喔！",
        ],
        "taiwanese": [
            "行路寬寬仔行，樓梯會使莫爬就莫爬，跤頭趺愛顧予好！",
            "坐久愛徛起來振動一下，暗時用燒毛巾敷跤頭趺十五分。",
        ],
        "reserved": [
            "行走請放緩步伐，盡量減少上下樓梯，以養護膝關節。",
            "久坐後宜起身舒展，夜間可溫敷關節十五分鐘以舒緩不適。",
        ],
        "insight": "【ESCEO 歐洲骨關節醫學會指引】規律低衝擊運動（如散步、水中運動）搭配溫敷，有助維持關節活動度並減緩疼痛。",
    }),
    (("眠", "睡", "熬夜", "焦慮"), {
        "spoiled": [
            "晚上早點放下手機，睡前泡個腳，今晚一定能睡得香香的～",
            "下午咖啡和濃茶先不要喝喔，白天曬曬太陽晚上比較好睡！",
            "睡不著也不要煩惱，聽點輕音樂慢慢放鬆就好喔～",
        ],
        "taiwanese": [
            "暗時早點放落手機仔，睏前燒水泡跤，今暗一定好睏！",
            "下晡咖啡、濃茶先莫啉，日時曬日頭，暗時較好睏。",
        ],
        "reserved": [
            "夜間請早些歇息，睡前溫水泡腳，有助安神入眠。",
            "午後宜避免咖啡與濃茶，日間適度日照有助調整作息。",
        ],
        "insight": "【AASM 美國睡眠醫學會指引】固定起床時間、白天接受日照、睡前 1 小時遠離螢幕藍光，是改善失眠的第一線非藥物策略。",
    }),
    (("傷", "燙", "術後", "創面"), {
        "spoiled": [
            "傷口要保持乾淨乾燥，換藥時有紅腫熱痛要馬上跟我說喔！",
            "多吃蛋、魚、豆腐補充蛋白質，傷口才會好得快快的～",
        ],
        "taiwanese": [
            "傷口愛保持清氣焦燥，換藥若有紅腫疼愛隨講予我知！",
            "加食卵、魚仔、豆腐補蛋白質，傷口才會較緊好。",
        ],
        "reserved": [
            "傷口請保持清潔乾燥，換藥時若見紅腫熱痛，請即告知。",
            "飲食宜多攝取優質蛋白質，以助傷口組織修復。",
        ],
        "insight": "【WHO / 傷口照護臨床指引】充足蛋白質、維生素 C 與鋅的攝取可促進膠原蛋白合成，加速傷口癒合。",
    }),
    (("眼", "視力", "黃斑", "白內障"), {
        "spoiled": [
            "看電視或手機 30 分鐘就讓眼睛休息一下，望望遠方喔～",
            "出門戴個太陽眼鏡擋紫外線，多吃深綠色蔬菜顧眼睛！",
        ],
        "taiwanese": [
            "看電視、手機三十分鐘就愛予目睭歇睏，看遠遠的所在。",
            "出門戴烏仔鏡，加食青菜，目睭才會金金。",
        ],
        "reserved": [
            "用眼三十分鐘請稍事歇息，遠眺片刻以舒緩眼部疲勞。",
            "外出請配戴太陽眼鏡，並多攝取深綠色蔬菜以護視力。",
        ],
        "insight": "【NIH AREDS 2 研究】葉黃素與玉米黃素的攝取，搭配外出配戴抗 UV 眼鏡，有助延緩黃斑部退化。",
    }),
    (("懷孕", "孕", "產後", "哺乳", "坐月子"), {
        "spoiled": [
            "要多休息不要太累，想吃什麼跟我說，我買給您～",
            "記得補充水分、慢慢走路，身體有不舒服要馬上說喔！",
        ],
        "taiwanese": [
            "愛加歇睏莫傷忝，想欲食啥物共我講，我買予您。",
            "水愛加啉，行路寬寬仔行，身體若無爽快愛隨講喔！",
        ],
        "reserved": [
            "請多加歇息，切勿過度操勞，飲食起居皆以安穩為要。",
            "請適量補充水分，起身行走放緩步伐，如有不適請即告知。",
        ],
        "insight": "【WHO 孕產期照護建議】孕期與產後應均衡攝取鐵、鈣與葉酸，保健品使用前請先與醫師或藥師確認。",
    }),
    (("胃", "腸", "便秘", "消化", "逆流"), {
        "spoiled": [
            "吃飯要細嚼慢嚥，七分飽就好，飯後不要馬上躺下喔～",
            "多吃蔬菜水果、多喝溫開水，肚子會比較舒服喔！",
        ],
        "taiwanese": [
            "食飯愛慢慢仔哺，七分飽就好，食飽莫隨倒落去喔。",
            "加食菜佮果子、加啉燒水，腹肚會較爽快！",
        ],
        "reserved": [
            "用餐請細嚼慢嚥，以七分飽為宜，飯後請勿立即躺臥。",
            "日常宜多攝取蔬果與溫開水，以助腸胃順暢。",
        ],
        "insight": "【WGO 世界胃腸病學組織指引】規律作息、足量膳食纖維與水分，是維持腸道健康的基礎。",
    }),
    (("感冒", "咳", "氣喘", "肺", "鼻炎", "流感"), {
        "spoiled": [
            "最近換季要注意保暖，出門記得戴口罩，多喝溫水喔！",
            "咳嗽不舒服就早點休息，症狀沒好要去看醫生喔～",
        ],
        "taiwanese": [
            "這站仔換季愛注意燒暖，出門愛掛喙罨，加啉燒水喔！",
            "嗽甲無爽快就早點歇睏，若無好愛去予醫生看喔。",
        ],
        "reserved": [
            "時值換季，請留意保暖，外出時配戴口罩以防感染。",
            "若有咳嗽不適，請早些歇息，症狀未改善請盡早就醫。",
        ],
        "insight": "【CDC 呼吸道疾病預防建議】勤洗手、配戴口罩、充足睡眠與接種疫苗，可降低呼吸道感染風險。",
    }),
]

def _match_condition_lines(condition: str):
    cond = (condition or "").lower()
    for keywords, lines in CONDITION_CARE_LINES:
        if any(k in cond for k in keywords):
            return lines
    return None

def _daily_rng(*parts) -> random.Random:
    """同一天、同一位親友、同一語氣產生固定結果；換天或換人就會不同"""
    seed = "|".join(str(p) for p in parts)
    return random.Random(seed)

def generate_ai_greeting(
    elder_name: str,
    elder_condition: str,
    weather_city: str,
    weather_temp: str,
    weather_temp_diff: int,
    weather_condition: str,
    weather_humidity: int,
    elder_status: str,
    tone: str,
    api_key: Optional[str] = None,
    model: str = "gemini-1.5-flash",
    variant: int = 0
) -> Dict[str, Any]:
    """
    Generates real-time personalized elder care messages:
    1. Prepares clinical safety constraints & weather context
    2. If Gemini API key is available, calls Gemini API
    3. If no key or API fails, uses dynamic multi-permutation generative synthesis
    """
    # 1. Clinical Constraints based on Elder's Medical History
    cond = elder_condition.lower()
    clinical_rules = []
    
    if "warfarin" in cond or "抗凝血" in cond or "血壓" in cond:
        clinical_rules.append("親友患有高血壓或正服用 Warfarin 抗凝血劑，嚴禁建議任何活血食材（如高劑量銀杏、維生素K、人參），提醒溫差大清晨下床先在床邊靜坐3分鐘，定時量血壓。")
    if "糖" in cond:
        clinical_rules.append("親友患有糖尿病，嚴禁推薦甜品或高糖補品，提醒早晚溫差注意足部保暖避免乾裂，洗澡水溫切勿超過40度。")
    if "骨" in cond or "關節" in cond or "膝蓋" in cond:
        clinical_rules.append("親友關節退化，提醒避免搬重物爬樓梯，天氣潮濕時可溫敷關節。")

    status_desc_map = {
        "normal": "狀況良好穩定，心情不錯",
        "joint_pain": "膝蓋酸痛、關節卡卡的、活動不便",
        "insomnia": "昨晚失眠、沒睡好、精神較差",
        "high_bp": "頭暈、血壓偏高、有些不舒服"
    }
    status_text = status_desc_map.get(elder_status, "日常保養")

    tone_map = {
        "spoiled": "撒嬌溫馨（20~30歲子女貼心小棉襖風格，活潑親暱，多用暖心語氣與「❤️、喔、啦、最愛您了」）",
        "taiwanese": "道地親切台語（例如使用：今仔日、莫行太遠、食藥仔、下晡曬日頭、穿暖和）",
        "reserved": "端莊敬重（典雅有禮的晚輩語氣，謙恭溫柔，尊重關懷）"
    }
    tone_desc = tone_map.get(tone, "撒嬌溫馨")

    # 2. Try Gemini API if key is present
    gemini_key = api_key or os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            prompt = f"""你是一位專門為年輕子女代筆發送「親友專屬每日健康問候」的 AI 暖心助理。
請依據以下即時數據，為子女撰寫一段傳送給親友的問候短文，並提供 1 句專業醫學指南。

【今天】
- {datetime.now().strftime('%Y-%m-%d')} 星期{WEEKDAY_NAMES[datetime.now().weekday()]}（請自然融入季節或星期的話題，每天內容都要不一樣，避免制式重複的句子）

【親友資訊】
- 稱呼：{elder_name}
- 慢性病史：{elder_condition}
- 今日回報狀況：{status_text}

【即時天氣】
- 城市：{weather_city}
- 氣溫：{weather_temp} (溫差 {weather_temp_diff}°C)
- 天氣狀況：{weather_condition}，濕度 {weather_humidity}%

【指定語氣風格】
- {tone_desc}

【醫學與照護安全限制】
{chr(10).join(['- ' + r for r in clinical_rules])}

請務必嚴格輸出合法的 JSON 物件，格式如下（勿輸出其他文字）：
{{
  "message": "「問候內容，約60~90字，自然結合天氣與親友當前狀況，語氣道地，句首以親友稱呼開頭，以『「』開頭並以『」』結尾」",
  "clinical_insight": "【權威醫學指引出處】1句簡明扼要的臨床衛教叮嚀（例如 AHA 心血管指引或 ESCEO 關節指引）"
}}
"""
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 350
                }
            }
            res = requests.post(url, json=payload, timeout=8)
            if res.status_code == 200:
                res_data = res.json()
                raw_text = res_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                # Clean markdown backticks if any
                clean_json_str = raw_text.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(clean_json_str)
                if "message" in parsed and "clinical_insight" in parsed:
                    return {
                        "success": True,
                        "message": parsed["message"],
                        "clinical_insight": parsed["clinical_insight"],
                        "source": "gemini-1.5-flash",
                        "model": model
                    }
        except Exception as e:
            print("Gemini API generation fallback:", e)

    # 3. Dynamic Local Generative Synthesis (Rich Multi-Permutation Engine)
    # Even without API key, it generates varied, non-repetitive greetings based on live variables!
    return generate_local_dynamic_greeting(
        elder_name=elder_name,
        elder_condition=elder_condition,
        weather_city=weather_city,
        weather_temp=weather_temp,
        weather_temp_diff=weather_temp_diff,
        weather_condition=weather_condition,
        weather_humidity=weather_humidity,
        elder_status=elder_status,
        tone=tone,
        variant=variant
    )

def generate_local_dynamic_greeting(
    elder_name: str,
    elder_condition: str,
    weather_city: str,
    weather_temp: str,
    weather_temp_diff: int,
    weather_condition: str,
    weather_humidity: int,
    elder_status: str,
    tone: str,
    variant: int = 0
) -> Dict[str, Any]:
    """
    Generates non-repetitive dynamic messages using combinatoric synthesis.
    同一天同一位親友結果固定（重新整理不會跳動），換天、換人、換病況或 variant 就會不同。
    """
    is_big_temp_diff = weather_temp_diff >= 7
    is_humid = weather_humidity >= 70

    # A. Taiwanese Tone
    if tone == "taiwanese":
        if elder_status == "joint_pain":
            openers = [
                f"「{elder_name}早安！今仔日【{weather_city}】濕度有 {weather_humidity}%，天公生風又起霧。",
                f"「{elder_name}食飽未？聽講今仔日【{weather_city}】偏冷偏濕，氣溫 {weather_temp}。",
            ]
            middles = [
                "風若透，骨頭關節卡容易酸軟，聽著您膝頭卡卡我真掛心！",
                "濕氣重關節卡卡，今天莫搬粗重物件，行路寬寬仔行。",
            ]
            closings = [
                "暗時早淡薄仔用溫熱水泡腳、熱敷膝蓋，乖乖聽話喔！」",
                "下晡若有日頭出來，再去門口曬曬日頭，多啉溫開水喔！」"
            ]
            insight = "【ESCEO 歐洲骨關節醫學指引】濕度高於 70% 時關節內滑液黏稠度增加，晨起活動關節 5 分鐘，睡前熱敷 15 分鐘可有效緩解酸脹。"
        elif elder_status == "insomnia":
            openers = [
                f"「{elder_name}早安！聽講昨暗無睏好，今仔日精神甘有卡差？",
                f"「{elder_name}平安！昨暗是不是操煩代誌翻來覆去無入眠？",
            ]
            middles = [
                f"今仔日【{weather_city}】天氣 {weather_condition}，中晝若愛睏就小歇睏一下，莫免勉強。",
                f"今日氣溫 {weather_temp} 算舒服，下晡去向陽處曬曬日頭、散散步，對自律神經上好。",
            ]
            closings = [
                "暗時我買好茶包給您泡杯熱舒壓茶，早點休息，別太操勞喔❤️」",
                "暗時睡前啉淡薄仔溫水，聽聽收音機放鬆心情，祝您今晚好眠！」"
            ]
            insight = "【AASM 美國睡眠醫學會指引】親友睡眠片段化時，白天午後照光 20 分鐘可促進晚間褪黑激素自然分泌，睡前 1 小時請遠離電視藍光。"
        elif elder_status == "high_bp":
            openers = [
                f"「{elder_name}早安！今仔日【{weather_city}】溫差高達 {weather_temp_diff}°C，天時變化真大！",
                f"「{elder_name}！聽講您今仔日頭有淡薄仔暈、血壓偏高，我聽著心頭真驚！",
            ]
            middles = [
                "血壓愛照三頓定時量，降血壓藥仔愛準時食，若頭暈就坐好歇睏，千萬莫猛猛站起來！",
                "氣溫急急變，血管收縮卡利害，今日莫急著出門，室內窗戶留個縫透氣就好。",
            ]
            closings = [
                "答應我今日好好坐著休息，多喝溫水，最要緊是身體平安喔❤️」",
                "藥仔照時間食，有任何不爽快愛即刻跟我講，最愛您了！」"
            ]
            insight = "【AHA 美國心臟學會臨床指引】日夜溫差達 7°C 以上清晨血壓易驟升 15~25mmHg。若服用抗凝血劑請注意床邊靜坐 3 分鐘再起身。"
        else:
            openers = [
                f"「{elder_name}早安！今仔日【{weather_city}】天氣 {weather_condition}，氣溫 {weather_temp}。",
                f"「{elder_name}平安！看著手機報講今仔日【{weather_city}】溫差有 {weather_temp_diff}°C 呢。",
            ]
            middles = [
                "聽著您今仔日身體勇健、精神足好，做晚輩的我就上安心啦！",
                "今天心情放輕鬆，去公園慢慢散步透透氣，看花看草身心好。",
            ]
            closings = [
                "出門還是記得加件薄外套防風，多啉溫開水喔！」",
                "您康健就是咱全家人的福氣，祝您今仔日順心平安❤️」"
            ]
            insight = "【NIH 國家衛生研究院】銀髮親友維持每日適度散步 20 分鐘與足量水分 (1500ml)，有助提升免疫力與心血管循環穩定。"

    # B. Reserved Tone (端莊敬重)
    elif tone == "reserved":
        if elder_status == "joint_pain":
            openers = [f"「{elder_name}晨安，今日【{weather_city}】濕度達 {weather_humidity}%，氣候濕涼。"]
            middles = ["獲悉您膝關節偶有酸脹不適，晚輩甚為惦念。已依臨床指引為您彙整護理要點，今日切勿負重走動。"]
            closings = ["夜間請備溫熱敷巾舒緩膝關節，祈願您起居安適，身心康泰。」"]
            insight = "【ESCEO 骨關節醫學指引】天冷潮濕時關節僵硬屬常見生理反應，晨起可在被窩活動腳踝，避免久坐不動。"
        elif elder_status == "insomnia":
            openers = [f"「{elder_name}晨安，聞知親友昨夜睡眠欠佳，精神難免疲頓。"]
            middles = [f"今日【{weather_city}】氣溫 {weather_temp}，日間請多加歇息養神，午後可於向陽明處漫步片刻以和暢氣血。"]
            closings = ["晚間請保持居室通風靜謐，睡前少飲濃茶，敬祝親友今宵得享安眠。」"]
            insight = "【AASM 睡眠醫學指引】親友睡眠片段化或入睡困難，午後適度散步曬太陽有助褪黑激素自然分泌。"
        elif elder_status == "high_bp":
            openers = [f"「{elder_name}晨安，今日【{weather_city}】溫差高達 {weather_temp_diff}°C，氣溫急遽變化。"]
            middles = ["親友血壓易受氣候溫差波動影響，請務必遵從醫囑定時監測數據並按時服藥，若感暈眩請立即坐下歇息。"]
            closings = ["晨起起臥動作請放緩節奏，添衣保暖為要，晚輩敬候親友安好。」"]
            insight = "【AHA 心血管指引】溫差大時清晨血壓易驟升。每日晨起請先於床邊靜坐 3 分鐘再下床，防範姿勢性低血壓。"
        else:
            openers = [f"「{elder_name}晨安，【{weather_city}】今日氣溫 {weather_temp}，天氣 {weather_condition}。"]
            middles = [f"欣聞親友今日身體康泰、精神健朗，實乃晚輩全家之福。早晚溫差 {weather_temp_diff}°C 仍存。"]
            closings = ["外出之際敬請留意適時添衣保暖，時常補充溫開水，恭祝親友福壽康寧。」"]
            insight = "【NIH / FDA 銀髮照護指引】銀髮親友每日應攝取足量水分 (1500~2000ml) 與優質蛋白質，搭配適度日照促進鈣質吸收。"

    # C. Spoiled Tone (撒嬌溫馨)
    else:
        if elder_status == "joint_pain":
            openers = [
                f"「{elder_name}早安！今天【{weather_city}】濕度有 {weather_humidity}% 呢，整座城市濕漉漉的。",
                f"「{elder_name}早安呀！一看手機【{weather_city}】氣溫 {weather_temp}，濕度偏高。",
            ]
            middles = [
                "聽說您膝蓋酸酸卡卡的，我好心疼喔！今天千萬不要逞強去爬樓梯或提重物喔！",
                "濕氣重關節最敏感了，走路要慢慢走，不要走太遠，膝蓋要好好保護喔！",
            ]
            closings = [
                "晚上用熱毛巾幫膝蓋好好敷一敷，要乖乖聽我的話喔❤️ 最愛您了！」",
                "等我放假回去幫您按摩膝蓋！今天在家好好休息，多喝溫水喔❤️」"
            ]
            insight = "【ESCEO 骨關節醫學指引】潮濕陰冷易引發關節痛覺神經敏感，適度熱敷能促進微循環，減緩滑膜發炎。"
        elif elder_status == "insomnia":
            openers = [
                f"「{elder_name}早安！昨晚沒睡好是不是太想我了呀？",
                f"「{elder_name}早安安！聽說昨晚失眠翻來覆去，精神好一點了嗎？",
            ]
            middles = [
                f"今天【{weather_city}】天氣 {weather_condition}，午後到陽台或公園曬曬暖洋洋的太陽散散步，心情會變超好喔！",
                f"白天中午一定要小睡個 20 分鐘補補眠，今天別讓自己太忙太累喔！",
            ]
            closings = [
                "晚上我幫您泡杯助眠熱茶，今晚一定能做個香甜的美夢，最愛您了❤️」",
                "睡前聽聽輕音樂放鬆心情，今天就放空好好休息，愛您喔❤️」"
            ]
            insight = "【AASM 睡眠醫學指引】親友日間小睡以 20~30 分鐘為宜，午後日照能重整生理時鐘，幫助夜間深層睡眠。"
        elif elder_status == "high_bp":
            openers = [
                f"「{elder_name}早安！今天【{weather_city}】溫差居然有 {weather_temp_diff}°C 這麼大！",
                f"「{elder_name}！看到您說今天頭暈、血壓偏高，我整個人都緊張起來了！",
            ]
            middles = [
                "天氣溫差大血管收縮超劇烈的，請您現在馬上坐好深呼吸，血壓藥一定要按時吃喔！",
                "千萬不要突然猛烈站起來，出門一定要戴圍巾披外套，不可以著涼喔！",
            ]
            closings = [
                "答應我今天一定要乖乖定時量血壓、多喝溫水好好休息，最愛您了❤️」",
                "有任何不舒服馬上打電話給我，今天別亂跑，在家好好休息喔❤️」"
            ]
            insight = "【AHA 美國心臟學會臨床指引】溫差超過 7°C 易引發血壓劇烈震盪。服用抗凝血劑者晨起請在床邊靜坐 3 分鐘再落地。"
        else:
            openers = [
                f"「{elder_name}早安！今天【{weather_city}】氣溫 {weather_temp} (溫差有 {weather_temp_diff}°C 呢)！",
                f"「{elder_name}早安安！今天【{weather_city}】天氣 {weather_condition}，陽光很舒服喔！",
            ]
            middles = [
                "聽說您今天狀況超級棒、精神很好，我就整天都安心放心啦～",
                "看到親友身體健健康康，是我每天最幸福開心的事了！",
            ]
            closings = [
                "出門散步還是要披件薄外套、多喝溫開水喔，最愛您了❤️」",
                "今天也要保持好心情，隨時記得喝水，最喜歡您開心的笑容了❤️」"
            ]
            insight = "【NIH 國家衛生研究院】銀髮親友每日攝取 1500~2000ml 水分能降低血液黏稠度，維持心肌與腦部供血充足。"

    tone_key = tone if tone in ("taiwanese", "reserved") else "spoiled"
    now = datetime.now()
    weekday = WEEKDAY_NAMES[now.weekday()]
    season = SEASON_TEXT[_season_of(now.month)][tone_key]

    # 日常狀況時加入季節／星期開場與病況專屬叮嚀，讓每天、每位親友的語錄都不同
    if elder_status not in ("joint_pain", "insomnia", "high_bp"):
        if tone_key == "taiwanese":
            openers = openers + [
                f"「{elder_name}早安！{season}，今仔日【{weather_city}】{weather_temp}。",
                f"「{elder_name}拜{weekday}好！今仔日【{weather_city}】{weather_condition}。",
            ]
            middles = middles + [
                "有閒佮厝邊開講、行公園，心情好身體就勇。",
                "日頭若好就去外口行行咧，莫歸工坐佇厝內喔。",
            ]
            closings = closings + [
                "我有閒就轉去看您，愛好好照顧家己喔❤️」",
                "三頓愛照時食，水愛加啉，愛您喔！」",
            ]
        elif tone_key == "reserved":
            openers = openers + [
                f"「{elder_name}晨安，{season}，【{weather_city}】今日 {weather_temp}。",
                f"「{elder_name}晨安，今日星期{weekday}，【{weather_city}】天氣 {weather_condition}。",
            ]
            middles = middles + [
                "願您今日起居有常，閒暇時可至戶外散步，舒展筋骨。",
                "日常飲食宜均衡清淡，適量飲水，保持心情愉悅。",
            ]
            closings = closings + [
                "晚輩雖不在身旁，心中時時掛念，敬祝您安康順遂。」",
                "敬請保重身體，晚輩改日再向您問安。」",
            ]
        else:
            openers = openers + [
                f"「{elder_name}早安！{season}，【{weather_city}】今天 {weather_temp}喔！",
                f"「{elder_name}星期{weekday}快樂！今天【{weather_city}】{weather_condition}～",
                f"「{elder_name}早安呀！今天【{weather_city}】濕度 {weather_humidity}%，溫差 {weather_temp_diff}°C 喔！",
            ]
            middles = middles + [
                "今天有沒有出去走走呀？跟朋友聊聊天心情會更好喔！",
                "記得三餐要好好吃，不可以隨便吃吃就算了喔～",
                "想到您我就覺得好幸福，今天也要開開心心的！",
            ]
            closings = closings + [
                "我有空就回去陪您吃飯，要想我喔❤️」",
                "有什麼需要隨時打給我，愛您喔❤️」",
                "今天也要記得多喝水、多笑笑，最愛您了❤️」",
            ]

        condition_lines = _match_condition_lines(elder_condition)
        if condition_lines:
            middles = condition_lines[tone_key]
            insight = condition_lines["insight"]

    rng = _daily_rng(now.strftime("%Y-%m-%d"), elder_name, elder_condition, tone_key, elder_status, variant)
    msg = rng.choice(openers) + rng.choice(middles) + rng.choice(closings)
    return {
        "success": True,
        "message": msg,
        "clinical_insight": insight,
        "source": "dynamic-combinatoric-synthesizer"
    }
