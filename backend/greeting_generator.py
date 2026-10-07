import os
import random
import requests
import json
from typing import Optional, Dict, Any

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
    model: str = "gemini-1.5-flash"
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
        tone=tone
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
    tone: str
) -> Dict[str, Any]:
    """
    Generates non-repetitive dynamic messages using combinatoric synthesis.
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

    msg = random.choice(openers) + random.choice(middles) + random.choice(closings)
    return {
        "success": True,
        "message": msg,
        "clinical_insight": insight,
        "source": "dynamic-combinatoric-synthesizer"
    }
