import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import time
import random
import requests

from database import (
    authenticate_user, register_user, get_user_profile,
    get_all_recipients, add_recipient, update_recipient, delete_recipient,
    get_all_orders, create_order, cancel_order,
    get_points_ledger, add_points_transaction,
    get_all_clinical_knowledge, save_clinical_knowledge, batch_save_clinical_knowledge,
    delete_clinical_knowledge, reset_clinical_knowledge_to_defaults,
    get_system_config, set_system_config, get_database_stats, export_full_database,
    get_db, update_recipient_line_id, update_user_profile_in_db, get_user_profile_by_account
)
from rag_engine import query_rag_engine, CLINICAL_LITERATURES
from vector_store import global_vector_store
from tfda_service import global_tfda_service
from pharmacy_crawler import search_pharmacy_products, get_recommended_products_by_condition
from auto_order import execute_auto_order
from weather_service import get_live_weather
from greeting_generator import generate_ai_greeting

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, AudioMessage

# 1. 💡 必須最先建立 FastAPI 實例 (app)
app = FastAPI(
    title="GiftSense Real Python Backend",
    description="Python 後端服務（國家級 RAG + 4 大連鎖藥局即時爬蟲 + SQLite 資料庫 + 即時天氣連線 + LINE 雙向真人互動）",
    version="2.0.0"
)

# 2. 💡 接著設定上傳檔案與 CORS
os.makedirs("static/uploads", exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory="static/uploads"), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LINE_CHANNEL_ACCESS_TOKEN = "xKlKMiLS8T7bm2m4Are0ztmzeUxFPU41UIknxVmaQDK8NzJu6gpvGnjog5/7Cj+SjHAKFITOQt99ni5rQtQy/CMjJBFxyWL6Ioi48VN6up3EenRoMmEwaMrtoSQISvzxxRnEgGM7mzyZz6klFR0jqQdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = "98c83668779c7c870958d335b2b4de76"

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

class LoginRequest(BaseModel):
    account: str
    password: str

class RegisterRequest(BaseModel):
    account: str
    password: str
    name: Optional[str] = None
    role: Optional[str] = "user"

class GuardQueryRequest(BaseModel):
    query: str
    elder_name: str = "親友"
    elder_condition: str = "日常養生"
    api_key: Optional[str] = None
    model: Optional[str] = "gemini-1.5-flash"

class AutoOrderRequest(BaseModel):
    product_name: str
    price: int
    pharmacy: str = "連鎖藥局"
    recipient: str = "親友家"

class RecipientCreateRequest(BaseModel):
    name: str
    condition: str = "日常養生"
    phone: Optional[str] = ""
    birthday: Optional[str] = ""

class RecipientUpdateRequest(BaseModel):
    name: Optional[str] = None
    condition: Optional[str] = None
    phone: Optional[str] = None
    birthday: Optional[str] = None

class OrderCreateRequest(BaseModel):
    order_id: str
    items: List[Dict[str, Any]]
    total: str
    recipient: str
    pharmacy: Optional[str] = "連鎖藥局"

class PointsTxRequest(BaseModel):
    account: str = "test"
    amount: int
    title: str

class GreetingGenerateRequest(BaseModel):
    elder_name: str = "親友"
    elder_condition: str = "日常養生"
    weather_city: str = "臺北市"
    weather_temp: str = "26 ~ 36°C"
    weather_temp_diff: int = 10
    weather_condition: str = "晴朗"
    weather_humidity: int = 65
    elder_status: str = "normal"
    tone: str = "spoiled"
    api_key: Optional[str] = None
    model: Optional[str] = "gemini-1.5-flash"

class FamilyMessageRequest(BaseModel):
    sender: str = "我"
    elder: str = "親友"
    content: str
    type: Optional[str] = "card"
    timestamp: Optional[str] = None

class ReferralClickRequest(BaseModel):
    product_name: str
    pharmacy: str
    price: int
    recipient: str = "親友"
    official_url: str

class TFDACheckRequest(BaseModel):
    elder_name: str = "親友"
    elder_condition: str = "日常養生"
    query: str
    ingredient: Optional[str] = ""

class RAGConfigRequest(BaseModel):
    topK: Optional[int] = 3
    simThreshold: Optional[float] = 0.25
    temperature: Optional[float] = 0.3
    model: Optional[str] = "builtin"
    apiKey: Optional[str] = ""
    systemPrompt: Optional[str] = ""

class KnowledgeItemRequest(BaseModel):
    id: str
    title: str
    authority: Optional[str] = ""
    category: Optional[str] = ""
    ingredient: Optional[str] = ""
    evidenceLevel: Optional[str] = "Level 1"
    recommendedDose: Optional[str] = ""
    mechanism: Optional[str] = ""
    contraindications: Optional[str] = ""
    targetSymptoms: Optional[List[str]] = []
    citation: Optional[str] = ""

class KnowledgeSyncRequest(BaseModel):
    literatures: List[Dict[str, Any]]

family_messages_store: List[Dict[str, Any]] = [
    {
        "id": "msg_sample_1",
        "sender": "我",
        "elder": "媽媽",
        "content": "媽媽早安！今天臺北市氣溫舒適，記得多喝溫開水，按時更換無菌敷料喔❤️",
        "type": "card",
        "timestamp": "2026-10-05 08:30:00"
    }
]

@app.get("/api/health")
def health_check():
    db_stats = get_database_stats()
    return {
        "status": "ok",
        "service": "CareGift 2.0 Real Python Backend",
        "version": "2.0.0",
        "database": "SQLite (caregift.db) Connected",
        "sqlite_stats": db_stats,
        "literatures_count": db_stats["counts"].get("clinical_knowledge", len(CLINICAL_LITERATURES)),
        "vector_engine": "MedicalVectorStore (High-Dimensional Cosine)",
        "tfda_engine": "TFDAService (Official Black Box Registry)"
    }

@app.post("/api/auth/login")
def api_login(req: LoginRequest):
    user = authenticate_user(req.account, req.password)
    if not user:
        return {"success": False, "message": "帳號或密碼錯誤，請重新確認！"}
    return {"success": True, "message": f"歡迎回來，{user['name']}！", "user": user}

@app.post("/api/auth/register")
def api_register(req: RegisterRequest):
    user = register_user(req.account, req.password, req.name, req.role or "user")
    if not user:
        return {"success": False, "message": "此帳號已存在，請直接登入！"}
    return {"success": True, "message": "註冊成功！已自動發放新會員 100 點獎勵！", "user": user}

@app.get("/api/auth/profile")
def api_user_profile(account: str = "test"):
    profile = get_user_profile(account)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "profile": profile}

@app.post("/api/guard/query")
def guard_query(req: GuardQueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    return query_rag_engine(
        query=req.query, elder_name=req.elder_name,
        elder_condition=req.elder_condition, api_key=req.api_key, model=req.model or "gemini-1.5-flash"
    )

@app.post("/api/tfda/check")
def tfda_check(req: TFDACheckRequest):
    return global_tfda_service.check_interaction(
        elder_name=req.elder_name, elder_condition=req.elder_condition,
        query=req.query, matched_ingredient=req.ingredient or ""
    )

@app.get("/api/vector/search")
def vector_search(q: str = "", top_k: int = 3):
    return {"success": True, "query": q, "results": global_vector_store.search(q, top_k=top_k)}

@app.get("/api/pharmacy/search")
def pharmacy_search(q: str = ""):
    products = search_pharmacy_products(keyword=q)
    return {"success": True, "query": q, "total": len(products), "products": products}

@app.get("/api/pharmacy/recommended")
def pharmacy_recommended(elder_name: str = "親友", condition: str = "日常養生"):
    return get_recommended_products_by_condition(elder_name=elder_name, condition=condition)

@app.post("/api/pharmacy/auto-order")
def pharmacy_auto_order(req: AutoOrderRequest):
    return execute_auto_order(
        product_name=req.product_name, price=req.price,
        pharmacy=req.pharmacy, recipient=req.recipient
    )

@app.post("/api/pharmacy/referral-click")
def pharmacy_referral_click(req: ReferralClickRequest):
    order_id = f"REF-{time.strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
    create_order(
        order_id=order_id,
        items=[{"name": f"{req.product_name} [{req.pharmacy} 官方直營]", "price": req.price, "qty": 1}],
        total=f"${req.price:,}", recipient=req.recipient, pharmacy=req.pharmacy
    )
    add_points_transaction(account="test", amount=100, title=f"導購送禮加贈：{req.pharmacy} - {req.product_name}")
    return {"success": True, "order_id": order_id, "pharmacy": req.pharmacy, "points_awarded": 100, "official_url": req.official_url}

@app.get("/api/weather")
def weather_forecast(city: str = "台北市", key: Optional[str] = None):
    weather = get_live_weather(city=city, cwa_api_key=key)
    return {"success": True, "weather": weather}

@app.get("/api/recipients")
def list_recipients(account: str = "test"):
    conn = get_db()
    rows = conn.execute("SELECT * FROM recipients WHERE user_account = ?", (account,)).fetchall()
    conn.close()
    return {"success": True, "recipients": [dict(r) for r in rows]}

@app.post("/api/recipients")
def create_new_recipient(request: Request, data: dict):
    try:
        # 💡 明確從前端 payload 提取對應欄位，並帶入當前登入的使用者帳號
        name = data.get("name")
        condition = data.get("condition")
        phone = data.get("phone", "")
        birthday = data.get("birthday", "")
        user_account = data.get("user_account", "test")

        rec = add_recipient(
            name=name,
            condition=condition,
            phone=phone,
            birthday=birthday,
            user_account=user_account
        )
        return {"success": True, "recipient": rec}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.put("/api/recipients/{rec_id}")
def edit_recipient(rec_id: str, req: RecipientUpdateRequest):
    conn = get_db()
    row = conn.execute("SELECT * FROM recipients WHERE id = ?", (rec_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Recipient not found")
    
    new_name = req.name if req.name is not None else row["name"]
    new_condition = req.condition if req.condition is not None else row["condition"]
    new_phone = req.phone if req.phone is not None else (row["phone"] if "phone" in row.keys() else "")
    new_birthday = req.birthday if req.birthday is not None else (row["birthday"] if "birthday" in row.keys() else "")
    
    rec = update_recipient(rec_id=rec_id, name=new_name, condition=new_condition, phone=new_phone, birthday=new_birthday)
    return {"success": True, "recipient": rec}

@app.delete("/api/recipients/{rec_id}")
def remove_recipient(rec_id: str):
    delete_recipient(rec_id=rec_id)
    return {"success": True, "deleted_id": rec_id}

@app.get("/api/orders")
def list_orders():
    return {"success": True, "orders": get_all_orders()}

@app.post("/api/orders")
def save_new_order(req: OrderCreateRequest):
    ord_res = create_order(
        order_id=req.order_id, items=req.items, total=req.total,
        recipient=req.recipient, pharmacy=req.pharmacy or "連鎖藥局"
    )
    return {"success": True, "order": ord_res}

@app.post("/api/orders/{order_id}/cancel")
def cancel_existing_order(order_id: str):
    cancel_order(order_id=order_id)
    return {"success": True, "canceled_id": order_id}

@app.get("/api/points")
def list_points(account: str = "test"):
    return {"success": True, "ledger": get_points_ledger(account=account)}

@app.post("/api/points")
def add_points_tx(req: PointsTxRequest):
    add_points_transaction(account=req.account, amount=req.amount, title=req.title)
    return {"success": True, "account": req.account, "amount": req.amount}

@app.get("/api/knowledge")
def list_clinical_knowledge():
    items = get_all_clinical_knowledge()
    if not items:
        items = CLINICAL_LITERATURES
    return {"success": True, "total": len(items), "source": "SQLite (caregift.db)", "literatures": items}

@app.post("/api/knowledge")
def add_or_update_clinical_knowledge(req: KnowledgeItemRequest):
    item = save_clinical_knowledge(req.dict())
    return {"success": True, "item": item}

@app.post("/api/knowledge/sync")
def sync_clinical_knowledge(req: KnowledgeSyncRequest):
    saved_count = batch_save_clinical_knowledge(req.literatures)
    return {"success": True, "saved_count": saved_count}

@app.post("/api/knowledge/reset")
def reset_clinical_knowledge():
    res = reset_clinical_knowledge_to_defaults()
    return {"success": True, "total": len(res), "literatures": res}

@app.delete("/api/knowledge/{item_id}")
def remove_clinical_knowledge(item_id: str):
    delete_clinical_knowledge(item_id)
    return {"success": True, "deleted_id": item_id}

@app.get("/api/config/rag")
def get_rag_configuration():
    cfg = get_system_config("rag_config", default={
        "topK": 3, "simThreshold": 0.25, "temperature": 0.3, "model": "builtin", "apiKey": "",
        "systemPrompt": "你是一位嚴謹客觀的臨床醫療與保健營養專家。"
    })
    return {"success": True, "config": cfg}

@app.post("/api/config/rag")
def save_rag_configuration(req: RAGConfigRequest):
    set_system_config("rag_config", req.dict())
    return {"success": True, "config": req.dict()}

@app.get("/api/db/stats")
def database_statistics():
    return {"success": True, "stats": get_database_stats()}

@app.get("/api/db/export")
def database_export():
    return export_full_database()

@app.post("/api/greeting/generate")
def greeting_generate(req: GreetingGenerateRequest):
    return generate_ai_greeting(
        elder_name=req.elder_name, elder_condition=req.elder_condition,
        weather_city=req.weather_city, weather_temp=req.weather_temp,
        weather_temp_diff=req.weather_temp_diff, weather_condition=req.weather_condition,
        weather_humidity=req.weather_humidity, elder_status=req.elder_status,
        tone=req.tone, api_key=req.api_key, model=req.model or "gemini-1.5-flash"
    )

@app.get("/api/messages")
def get_family_messages(elder: str = ""):
    if elder.strip():
        filtered = [m for m in family_messages_store if elder in m.get("elder", "")]
        return {"success": True, "messages": filtered}
    return {"success": True, "messages": family_messages_store}

@app.post("/api/messages")
def post_family_message(req: FamilyMessageRequest):
    timestamp_str = req.timestamp or time.strftime("%Y-%m-%d %H:%M:%S")
    content_text = req.content
    
    sender_display = req.sender if req.sender and req.sender.strip() else "家人"
    conn = get_db()
    user_row = conn.execute("SELECT name FROM users WHERE account = ?", (req.sender,)).fetchone()
    conn.close()
    
    if user_row and user_row["name"]:
        sender_display = user_row["name"]

    card_prefix = f"【來自 {sender_display} 的健康關懷】"
    
    if req.type == "card":
        for old_prefix in ["【來自家人的健康關懷】", "【來自 test 的健康關懷】", "【來自 測試員 的健康關懷】", "【來自 家宜 的健康關懷】"]:
            if content_text.startswith(old_prefix):
                content_text = content_text[len(old_prefix):].strip()
        content_text = f"{card_prefix}\n{content_text}"

    new_msg = {
        "id": f"msg_{int(time.time() * 1000)}",
        "sender": sender_display,
        "elder": req.elder,
        "content": content_text,
        "type": req.type or "card",
        "timestamp": timestamp_str,
    }
    family_messages_store.insert(0, new_msg)
    
    if req.sender != req.elder:
        conn = get_db()
        row = conn.execute("SELECT line_user_id FROM recipients WHERE name = ?", (req.elder,)).fetchone()
        conn.close()
        
        target_line_id = row["line_user_id"] if row and row["line_user_id"] else None
        if target_line_id:
            url = "https://api.line.me/v2/bot/message/push"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
            }
            payload = {
                "to": target_line_id,
                "messages": [{"type": "text", "text": content_text}]
            }
            try:
                requests.post(url, headers=headers, json=payload)
            except Exception as e:
                print("LINE 推播失敗:", e)
        
    return {"success": True, "message": new_msg}

@app.post("/api/line/webhook")
async def line_webhook(request: Request):
    signature = request.headers.get('X-Line-Signature', '')
    body = await request.body()
    body_str = body.decode('utf-8')
    
    try:
        import json
        data = json.loads(body_str)
        for event in data.get("events", []):
            event_type = event.get("type")
            user_id = event.get("source", {}).get("userId")
            print(f"【解析事件】類型: {event_type}, 用戶 ID: {user_id}")
            
            if event_type == "follow":
                if user_id:
                    welcome_msg_1 = (
                        "💙 【 歡迎加入 GiftSense 智慧健康守護 】 💙\n"
                        "-------------------------------------\n"
                        "心意，醫觸即達。我們是您專屬的溫馨健康管家。\n\n"
                        "在這裡，您可以隨時收到家人傳遞的暖心問候、健康守護小卡與用藥叮嚀，讓愛與關懷零距離！✨"
                    )
                    welcome_msg_2 = (
                        "📌 【 快速開通綁定步驟 】\n"
                        "為了讓系統能準時同步您的專屬對話，請直接回傳您的名字進行身份綁定：\n\n"
                        "👉 請回傳：【我是 您的名字】\n"
                        "（例如：【我是 媽媽】 或 🌱 【我是 王小明】）\n\n"
                        "💡 綁定成功後，您就能直接在此聊天室與家人雙向對話、接收語音或查看用藥提醒喔！"
                    )
                    _send_line_reply(user_id, welcome_msg_1)
                    import time
                    time.sleep(0.4)
                    _send_line_reply(user_id, welcome_msg_2)
                continue

            if event_type == "message":
                msg = event.get("message", {})
                content = ""
                msg_type = "text"
                
                if msg.get("type") == "text":
                    content = msg.get("text", "").strip()
                    
                    if content.startswith("我是"):
                        target_name = content.replace("我是", "").strip()
                        conn = get_db()
                        rows = conn.execute("SELECT id, name FROM recipients").fetchall()
                        conn.close()
                        
                        matched_id = None
                        matched_real_name = ""
                        for r in rows:
                            db_name = r["name"].strip()
                            if target_name in db_name or db_name in target_name:
                                matched_id = r["id"]
                                matched_real_name = db_name
                                break
                        
                        if matched_id:
                            update_recipient_line_id(matched_real_name, user_id)
                            reply_text = f"綁定成功！您好，{matched_real_name}。家人傳送的健康關懷與用藥叮嚀將會即時同步給您！"
                        else:
                            reply_text = f"綁定失敗：系統的親友健康資料庫中找不到「{target_name}」，請確認家人的 App 中是否已新增您的名字。"
                        
                        _send_line_reply(user_id, reply_text)
                        continue

                    elif content in ["功能說明", "說明", "幫助", "Help", "選單", "menu"]:
                        help_text = (
                            "【 GiftSense 服務說明 】\n\n"
                            "1. 接收家人問候\n"
                            "   家人每天發送的關懷卡會直接推播到這裡。\n\n"
                            "2. 隨時語音與文字留言\n"
                            "   直接傳送訊息，系統會自動同步至家人的控制台。\n\n"
                            "3. 常用指令快捷：\n"
                            "   - 輸入「我是 您的名字」重新綁定身份\n"
                            "   - 點擊下方選單查看用藥提醒或發送求助"
                        )
                        _send_line_reply(user_id, help_text)
                        content = "【系統指令】查看功能說明"

                    elif content in ["用藥提醒", "吃藥", "保健品"]:
                        med_text = (
                            "【 今日用藥與保健叮嚀 】\n\n"
                            "• 請依照醫師處方按時服藥。\n"
                            "• 若有額外購買市售保健品（如魚油、維他命），請先透過家人的 App 進行安全交互作用檢驗喔！"
                        )
                        _send_line_reply(user_id, med_text)
                        content = "【系統指令】查詢用藥提醒"

                    elif content in ["緊急求助", "幫忙", "不舒服"]:
                        sos_text = "【安全通報】已收到您的身體不適訊息！系統已同步發送通知給您的守護家人，請保持電話暢通或稍候片刻。"
                        _send_line_reply(user_id, sos_text)
                        content = "🚨 【親友發出緊急求助訊號】"

                elif msg.get("type") == "audio":
                    msg_type = "audio"
                    msg_id = msg.get("id")
                    audio_url = f"https://api-data.line.me/v2/bot/message/{msg_id}/content"
                    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
                    try:
                        audio_res = requests.get(audio_url, headers=headers)
                        if audio_res.status_code == 200:
                            os.makedirs("static/uploads", exist_ok=True)
                            file_name = f"voice_{msg_id}.m4a"
                            file_path = os.path.join("static/uploads", file_name)
                            with open(file_path, "wb") as f:
                                f.write(audio_res.content)
                            content = f"/api/uploads/{file_name}"
                        else:
                            content = "[語音訊息下載失敗]"
                    except Exception as e:
                        content = "[語音訊息錯誤]"

                elif msg.get("type") == "sticker":
                    msg_type = "sticker"
                    content = "🎨 [LINE 貼圖]"
                
                conn = get_db()
                row = conn.execute("SELECT name FROM recipients WHERE line_user_id = ?", (user_id,)).fetchone()
                conn.close()
                
                elder_name = row["name"] if row else "未綁定親友"
                new_msg = {
                    "id": f"msg_line_{int(datetime.now().timestamp() * 1000)}",
                    "sender": elder_name,
                    "elder": elder_name,
                    "content": content,
                    "type": msg_type,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                family_messages_store.insert(0, new_msg)
                
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print("Webhook 處理異常:", e)
        
    return {"status": "success"}

def _send_line_reply(user_id: str, text: str):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}]
    }
    try:
        requests.post(url, headers=headers, json=payload)
    except Exception as e:
        print("LINE 回覆失敗:", e)

@app.post("/api/points/add")
def api_add_points_alias(req: PointsTxRequest):
    target_account = req.account if req.account else "test"
    add_points_transaction(account=target_account, amount=req.amount, title=req.title)
    profile = get_user_profile(target_account)
    updated_points = profile["points"] if profile else req.amount
    return {"success": True, "message": f"成功新增 {req.amount} 點！", "new_points": updated_points}

@app.get("/api/user/profile")
def api_get_user_profile(account: str = None):
    if not account or not account.strip():
        raise HTTPException(status_code=400, detail="必須提供有效的會員帳號 (account)")
        
    profile = get_user_profile_by_account(account)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "profile": profile}

@app.put("/api/user/profile")
def api_update_user_profile(req: dict):
    account = req.get("account")
    name = req.get("name")
    phone = req.get("phone", "")
    birthday = req.get("birthday", "")
    bio = req.get("bio", "")
    avatar = req.get("avatar", "default")
    
    if not account or not name:
        return {"success": False, "message": "帳號與顯示名稱不能為空"}
        
    success = update_user_profile_in_db(account, name, phone, birthday, bio, avatar)
    if success:
        return {"success": True, "message": "個人資料與 SQLite 資料庫更新成功"}
    return {"success": False, "message": "更新失敗"}

class SocialLoginRequest(BaseModel):
    provider: str
    email: str
    name: str
    social_id: str

class ForgotPasswordRequest(BaseModel):
    email: str

@app.post("/api/auth/forgot-password")
def api_forgot_password(req: ForgotPasswordRequest):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ? OR account = ?", (req.email, req.email)).fetchone()
    conn.close()
    
    if not user:
        return {"success": False, "message": "找不到與此信箱相符的會員帳號"}
        
    return {"success": True, "message": f"重設密碼信件已發送至 {req.email}，請至信箱查收！"}

@app.api_route("/api/auth/social", methods=["GET", "POST"])
def api_social_login(req: Optional[SocialLoginRequest] = None):
    if req is None or not req.email:
        return {"success": False, "message": "請透過 POST 傳遞社群驗證資料"}
    
    conn = get_db()
    # 💡 修正：嚴格使用當前 Google 傳過來的真實 email 作為獨立帳號辨識，避免不同帳號互抓資料
    account = req.email.strip()
    user = conn.execute("SELECT * FROM users WHERE email = ? OR account = ?", (account, account)).fetchone()
    
    if not user:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO users (account, name, email, auth_provider, points, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (account, req.name, req.email, req.provider, 2500, now_str)
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE email = ? OR account = ?", (account, account)).fetchone()
    
    conn.close()
    return {
        "success": True, 
        "message": f"透過 {req.provider.capitalize()} 登入成功！", 
        "user": dict(user)
    }

# 💡 統一使用絕對路徑確保 FastAPI 絕對找得到靜態資料夾，且只掛載一次
web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "web")
if os.path.exists(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web_ui")
    print(f"【成功掛載前端網頁】路徑: {web_dir}")
else:
    print(f"【警告】找不到前端靜態路徑: {web_dir}")

if __name__ == "__main__":
    import uvicorn
    print("啟動 GiftSense 後端服務 (http://127.0.0.1:8000)...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)