import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import base64
import hashlib
import hmac
import threading
import time
import random
import re
import requests

from database import (
    authenticate_user, register_user, get_user_profile,
    get_all_recipients, get_recipient_by_id, add_recipient, update_recipient,
    update_recipient_quick_tags, delete_recipient,
    get_all_orders, create_order, cancel_order,
    get_points_ledger, add_points_transaction,
    get_all_clinical_knowledge, save_clinical_knowledge, batch_save_clinical_knowledge,
    delete_clinical_knowledge, reset_clinical_knowledge_to_defaults,
    get_system_config, set_system_config, get_database_stats, export_full_database,
    get_db, update_user_profile_in_db, get_user_profile_by_account,
    get_ai_guard_quota, consume_ai_guard_quota, add_ai_guard_bonus,
    find_or_create_social_user, create_line_bind_code, bind_line_by_code,
    unbind_recipient_line, find_recipient_line_id, get_line_binding_info, claim_reward
)
from social_auth import verify_social_token, SocialAuthError
from rag_engine import query_rag_engine, CLINICAL_LITERATURES
from vector_store import global_vector_store
from tfda_service import global_tfda_service
from pharmacy_crawler import search_pharmacy_products, get_recommended_products_by_condition, warmup_pharmacy_cache
from auto_order import execute_auto_order
from weather_service import get_live_weather
from greeting_generator import generate_ai_greeting
from chips_generator import get_clinical_rule_chips, generate_ai_recipient_chips

# AI 守護助理每日免費詢問次數；可用關懷點數兌換額外次數
AI_GUARD_DAILY_LIMIT = 3
AI_GUARD_REDEEM_COST = 50
AI_GUARD_REDEEM_EXTRA = 3

from linebot import LineBotApi, WebhookHandler
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

@app.on_event("startup")
def startup_warmup_cache():
    # 💡 預熱藥局快取改在背景執行緒進行，避免爬蟲逾時拖慢伺服器啟動
    def _warmup():
        try:
            warmup_pharmacy_cache()
        except Exception as exc:
            print(f"Pharmacy cache warmup failed: {exc}")
    threading.Thread(target=_warmup, daemon=True).start()

# 💡 優先讀取環境變數（Render Environment / backend/.env），未設定時沿用原本的值
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") or "xKlKMiLS8T7bm2m4Are0ztmzeUxFPU41UIknxVmaQDK8NzJu6gpvGnjog5/7Cj+SjHAKFITOQt99ni5rQtQy/CMjJBFxyWL6Ioi48VN6up3EenRoMmEwaMrtoSQISvzxxRnEgGM7mzyZz6klFR0jqQdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET") or "98c83668779c7c870958d335b2b4de76"
ANDROID_PACKAGE_NAME = os.environ.get("ANDROID_PACKAGE_NAME", "com.example.giftsense")
_line_bot_basic_id_cache = {"value": os.environ.get("LINE_BOT_BASIC_ID", "")}

def _get_line_bot_basic_id() -> str:
    """取得 LINE 官方帳號 ID（如 @123abcde），用來產生加好友連結"""
    if _line_bot_basic_id_cache["value"]:
        return _line_bot_basic_id_cache["value"]
    try:
        res = requests.get(
            "https://api.line.me/v2/bot/info",
            headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
            timeout=6
        )
        if res.status_code == 200:
            _line_bot_basic_id_cache["value"] = res.json().get("basicId", "")
    except Exception as e:
        print("取得 LINE 官方帳號 ID 失敗:", e)
    return _line_bot_basic_id_cache["value"]

LINE_WELCOME_TEXT = (
    "💙 歡迎加入 GiftSense 智慧關懷 💙\n\n"
    "心意，醫觸即達。在這裡您會收到家人傳來的暖心問候、健康關懷卡與用藥叮嚀，"
    "也能直接留言或傳語音給家人 ✨"
)

LINE_HELP_TEXT = (
    "【 GiftSense 服務說明 】\n\n"
    "點下方選單就能使用：\n"
    "💌 今日關懷：查看家人最新送來的關懷卡\n"
    "💊 今日用藥：服藥與保健叮嚀\n"
    "🆘 緊急求助：立即通知守護您的家人\n"
    "🔗 綁定說明：如何綁定與改綁家人\n"
    "👤 我的綁定：查看目前綁定的家人\n\n"
    "💬 直接傳文字或語音，就會轉達給家人喔！"
)

LINE_UNBOUND_GUIDE = (
    "您好！您的 LINE 尚未完成綁定 🙏\n\n"
    "請向家人索取 GiftSense App 上顯示的 6 位數綁定碼，直接回傳：\n"
    "👉 【綁定 123456】\n"
    "（請把 123456 換成家人給您的綁定碼）"
)

def _verify_line_signature(body: bytes, signature: str) -> bool:
    digest = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode("utf-8"), signature or "")

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
    account: Optional[str] = None

class GuardRedeemRequest(BaseModel):
    account: str

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
    quick_tags: Optional[List[Dict[str, Any]]] = None

class GenerateChipsRequest(BaseModel):
    elder_name: Optional[str] = None
    elder_condition: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = "gemini-1.5-flash"

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
    weather_humidity: Optional[int] = 65
    elder_status: str = "normal"
    tone: str = "spoiled"
    api_key: Optional[str] = None
    model: Optional[str] = "gemini-1.5-flash"
    variant: Optional[int] = 0

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

# 傳情小站訊息（記憶體暫存）：owner_account = 守護家人的帳號，from_role = family（家人發送）/ elder（親友從 LINE 回覆）
family_messages_store: List[Dict[str, Any]] = []

@app.get("/api/health")
def health_check():
    db_stats = get_database_stats()
    return {
        "status": "ok",
        "service": "GiftSense 2.0 Real Python Backend",
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

def _guard_quota_key(account: Optional[str], request: Request) -> str:
    # 💡 有登入帳號時依帳號計算；未登入才退回以來源 IP 計算
    if account and account.strip():
        return account.strip()
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return f"ip:{client_ip}"

@app.post("/api/guard/query")
def guard_query(req: GuardQueryRequest, request: Request):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    allowed, quota = consume_ai_guard_quota(_guard_quota_key(req.account, request), AI_GUARD_DAILY_LIMIT)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"今日 AI 守護助理已達上限：{quota['limit']} 次/天，可使用 {AI_GUARD_REDEEM_COST} 點兌換 {AI_GUARD_REDEEM_EXTRA} 次，或明天再試。"
        )

    result = query_rag_engine(
        query=req.query, elder_name=req.elder_name,
        elder_condition=req.elder_condition, api_key=req.api_key, model=req.model or "gemini-1.5-flash"
    )
    if isinstance(result, dict):
        result["quota"] = quota
    return result

@app.get("/api/guard/quota")
def guard_quota(request: Request, account: Optional[str] = None):
    quota = get_ai_guard_quota(_guard_quota_key(account, request), AI_GUARD_DAILY_LIMIT)
    return {
        "success": True,
        "quota": quota,
        "redeem_cost": AI_GUARD_REDEEM_COST,
        "redeem_extra": AI_GUARD_REDEEM_EXTRA
    }

@app.post("/api/guard/redeem")
def guard_redeem(req: GuardRedeemRequest):
    profile = get_user_profile(req.account)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    if (profile.get("points") or 0) < AI_GUARD_REDEEM_COST:
        return {"success": False, "message": f"點數不足，兌換需要 {AI_GUARD_REDEEM_COST} 點"}

    add_points_transaction(account=req.account, amount=-AI_GUARD_REDEEM_COST, title=f"兌換 AI 守護助理詢問 {AI_GUARD_REDEEM_EXTRA} 次")
    quota = add_ai_guard_bonus(req.account, AI_GUARD_REDEEM_EXTRA, AI_GUARD_DAILY_LIMIT)
    return {
        "success": True,
        "message": f"已使用 {AI_GUARD_REDEEM_COST} 點兌換 {AI_GUARD_REDEEM_EXTRA} 次詢問！",
        "quota": quota,
        "new_points": profile["points"] - AI_GUARD_REDEEM_COST
    }

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
    return {"success": True, "recipients": get_all_recipients(user_account=account)}

@app.post("/api/recipients")
def create_new_recipient(request: Request, data: dict):
    try:
        # 💡 明確從前端 payload 提取對應欄位，並帶入當前登入的使用者帳號
        name = data.get("name")
        condition = data.get("condition")
        phone = data.get("phone", "")
        birthday = data.get("birthday", "")
        user_account = data.get("user_account", "test")
        quick_tags = data.get("quick_tags")

        rec = add_recipient(
            name=name,
            condition=condition,
            phone=phone,
            birthday=birthday,
            user_account=user_account,
            quick_tags=quick_tags
        )
        return {"success": True, "recipient": rec}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.put("/api/recipients/{rec_id}")
def edit_recipient(rec_id: str, req: RecipientUpdateRequest):
    row = get_recipient_by_id(rec_id)
    if not row:
        raise HTTPException(status_code=404, detail="Recipient not found")

    new_name = req.name if req.name is not None else row["name"]
    new_condition = req.condition if req.condition is not None else row["condition"]
    new_phone = req.phone if req.phone is not None else (row.get("phone") or "")
    new_birthday = req.birthday if req.birthday is not None else (row.get("birthday") or "")
    # 病況沒變且未指定晶片時保留原本的晶片（可能是 AI 產生的）
    new_tags = req.quick_tags
    if new_tags is None and new_condition == row["condition"]:
        new_tags = row.get("quick_tags") or None

    rec = update_recipient(rec_id=rec_id, name=new_name, condition=new_condition, phone=new_phone, birthday=new_birthday, quick_tags=new_tags)
    return {"success": True, "recipient": rec}

@app.delete("/api/recipients/{rec_id}")
def remove_recipient(rec_id: str):
    delete_recipient(rec_id=rec_id)
    return {"success": True, "deleted_id": rec_id}

# 親友專屬快速提問晶片（臨床規則 + AI 雙軌）
@app.get("/api/recipients/{rec_id}/chips")
def get_recipient_chips_endpoint(rec_id: str):
    rec = get_recipient_by_id(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recipient not found")
    chips = rec.get("quick_tags")
    if not chips:
        chips = get_clinical_rule_chips(rec["condition"], rec["name"])
        update_recipient_quick_tags(rec_id, chips)
    return {
        "success": True,
        "recipient_id": rec_id,
        "elder_name": rec["name"],
        "elder_condition": rec["condition"],
        "source": "sqlite_cache",
        "chips": chips
    }

@app.post("/api/recipients/{rec_id}/generate-chips")
def generate_recipient_chips_endpoint(rec_id: str, req: GenerateChipsRequest):
    rec = get_recipient_by_id(rec_id)
    elder_name = req.elder_name or (rec["name"] if rec else "親友")
    elder_condition = req.elder_condition or (rec["condition"] if rec else "日常養生")

    chips = generate_ai_recipient_chips(
        elder_name=elder_name,
        elder_condition=elder_condition,
        api_key=req.api_key,
        model=req.model or "gemini-1.5-flash"
    )
    if rec:
        update_recipient_quick_tags(rec_id, chips)
    return {
        "success": True,
        "recipient_id": rec_id,
        "elder_name": elder_name,
        "elder_condition": elder_condition,
        "source": "ai_generated",
        "chips": chips
    }

@app.get("/api/chips/suggested")
def get_suggested_chips_query(condition: str = "日常養生", name: str = "親友"):
    return {
        "success": True,
        "elder_name": name,
        "elder_condition": condition,
        "source": "clinical_rules",
        "chips": get_clinical_rule_chips(condition=condition, name=name)
    }

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
        "systemPrompt": "你是一位嚴謹客觀的臨床醫療與保健營養專家。請根據檢索到的國家級文獻 [1][2] 提供建議，嚴禁編造事實。若親友有服用處方藥，必須嚴格審核抗凝血與撞藥禁忌，並附上醫療免責聲明。"
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
        weather_humidity=req.weather_humidity if req.weather_humidity is not None else 65,
        elder_status=req.elder_status, tone=req.tone, api_key=req.api_key,
        model=req.model or "gemini-1.5-flash", variant=req.variant or 0
    )

@app.get("/api/messages")
def get_family_messages(elder: str = "", account: str = ""):
    # 💡 只回傳「這個帳號 × 這位親友」的一對一對話，避免不同使用者或不同親友的訊息混在一起
    if not account.strip():
        return {"success": True, "messages": []}
    filtered = [
        m for m in family_messages_store
        if m.get("owner_account") == account and (not elder.strip() or m.get("elder") == elder.strip())
    ]
    return {"success": True, "messages": filtered}

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
        "owner_account": req.sender,
        "from_role": "family",
    }
    family_messages_store.insert(0, new_msg)
    
    if req.sender != req.elder:
        # 💡 只推播給寄件者帳號底下的這位親友，避免不同使用者的同名親友收到別人的訊息
        target_line_id = find_recipient_line_id(req.elder, req.sender)
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

    # 💡 驗證請求確實來自 LINE 平台
    if not _verify_line_signature(body, signature):
        print("LINE webhook 簽章驗證失敗，已忽略此請求")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        import json
        data = json.loads(body.decode('utf-8'))
        for event in data.get("events", []):
            try:
                _handle_line_event(event)
            except Exception as e:
                print("LINE 事件處理異常:", e)
    except Exception as e:
        print("Webhook 處理異常:", e)

    return {"status": "success"}

# 圖文選單按鈕送出的文字（tools/setup_line_richmenu.py 建立的選單也使用這些字）
LINE_CMD_TODAY_CARE = ("今日關懷", "最新關懷", "關懷卡")
LINE_CMD_MEDICATION = ("今日用藥", "用藥提醒", "吃藥", "保健品")
LINE_CMD_SOS = ("緊急求助", "幫忙", "不舒服", "救命")
LINE_CMD_BIND_HELP = ("綁定說明", "如何綁定", "綁定")
LINE_CMD_HELP = ("服務說明", "功能說明", "說明", "幫助", "help", "選單", "menu")
LINE_CMD_MY_BINDING = ("我的綁定", "綁定狀態")

LINE_QUICK_REPLY = {
    "items": [
        {"type": "action", "action": {"type": "message", "label": label, "text": label}}
        for label in ("今日關懷", "今日用藥", "緊急求助", "服務說明")
    ]
}

def _line_text(text: str, quick_reply: bool = True) -> dict:
    msg = {"type": "text", "text": text}
    if quick_reply:
        msg["quickReply"] = LINE_QUICK_REPLY
    return msg

def _handle_line_event(event: dict):
    event_type = event.get("type")
    user_id = event.get("source", {}).get("userId")
    reply_token = event.get("replyToken")
    print(f"【解析事件】類型: {event_type}, 用戶 ID: {user_id}")
    if not user_id:
        return

    binding = get_line_binding_info(user_id)

    if event_type == "follow":
        if binding:
            _line_reply(reply_token, user_id, [_line_text(
                f"💙 歡迎回來，{binding['name']}！\n"
                f"您已綁定，{binding['owner_name']} 傳送的關懷卡會直接送到這裡。\n"
                "點下方選單就能查看今日關懷、用藥提醒或發送求助。"
            )])
        else:
            _line_reply(reply_token, user_id, [
                _line_text(LINE_WELCOME_TEXT, quick_reply=False),
                _line_text(LINE_UNBOUND_GUIDE, quick_reply=False),
            ])
        return

    if event_type != "message":
        return

    msg = event.get("message", {})
    msg_type = msg.get("type")
    text = msg.get("text", "").strip() if msg_type == "text" else ""

    # 1. 綁定碼：唯一的綁定方式
    bind_match = re.match(r"^【?\s*綁定\s*(\d{6})\s*】?$", text)
    if bind_match:
        rec = bind_line_by_code(bind_match.group(1), user_id)
        if rec:
            owner = rec.get("owner_name") or "家人"
            reply = _line_text(
                f"✅ 綁定成功！您好，{rec['name']}。\n"
                f"{owner} 傳送的健康關懷與用藥叮嚀會即時送到這裡，點下方選單就能使用各項功能。"
            )
        else:
            reply = _line_text(
                "綁定失敗：綁定碼錯誤或已過期（有效 24 小時）。\n請家人在 App 重新產生綁定碼後再試一次。",
                quick_reply=False,
            )
        _line_reply(reply_token, user_id, [reply])
        return

    # 2. 尚未綁定：只回覆綁定教學，訊息不存入系統
    if not binding:
        _line_reply(reply_token, user_id, [_line_text(LINE_UNBOUND_GUIDE, quick_reply=False)])
        return

    elder_name = binding["name"]
    owner_name = binding["owner_name"]
    owner_account = binding["user_account"]

    def _store(content: str, store_type: str = "text"):
        family_messages_store.insert(0, {
            "id": f"msg_line_{int(datetime.now().timestamp() * 1000)}",
            "sender": elder_name,
            "elder": elder_name,
            "content": content,
            "type": store_type,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "owner_account": owner_account,
            "from_role": "elder",
        })

    if msg_type == "text":
        cmd = text.lower()
        if cmd in LINE_CMD_TODAY_CARE:
            card = next((
                m for m in family_messages_store
                if m.get("elder") == elder_name and m.get("type") == "card"
                and m.get("owner_account") == owner_account
            ), None)
            if card:
                reply = f"💌 {owner_name} 最新送給您的關懷（{card.get('timestamp', '')[5:16]}）：\n\n{card['content']}"
            else:
                reply = f"💌 {owner_name} 今天還沒有送關懷卡喔！\n想念家人的話，可以直接在這裡留言，我會幫您轉達 ❤️"
            _line_reply(reply_token, user_id, [_line_text(reply)])
            return

        if cmd in LINE_CMD_MEDICATION:
            _line_reply(reply_token, user_id, [_line_text(_build_medication_reminder(binding))])
            return

        if cmd in LINE_CMD_SOS:
            _store("🚨【親友發出緊急求助訊號】", "text")
            _line_reply(reply_token, user_id, [_line_text(
                f"🆘 已收到您的求助！系統已通知 {owner_name}，請保持電話暢通。\n"
                "⚠️ 若情況緊急，請立即撥打 119。"
            )])
            return

        if cmd in LINE_CMD_BIND_HELP:
            _line_reply(reply_token, user_id, [_line_text(
                f"🔗 您目前綁定為【{elder_name}】，由 {owner_name} 守護。\n\n"
                "若要改綁其他家人：請向對方索取 GiftSense App 上的新綁定碼，回傳【綁定 123456】即可。"
            )])
            return

        if cmd in LINE_CMD_HELP:
            _line_reply(reply_token, user_id, [_line_text(LINE_HELP_TEXT)])
            return

        if cmd in LINE_CMD_MY_BINDING:
            _line_reply(reply_token, user_id, [_line_text(
                f"👤 綁定身分：{elder_name}\n💙 守護家人：{owner_name}\n🩺 健康狀況：{binding.get('condition') or '日常養生'}"
            )])
            return

        # 一般文字留言：轉達給家人
        _store(text, "text")
        _line_reply(reply_token, user_id, [_line_text(f"✅ 已轉達給 {owner_name}！")])
        return

    if msg_type == "audio":
        _store(_download_line_audio(msg.get("id")), "audio")
        _line_reply(reply_token, user_id, [_line_text(f"✅ 語音已轉達給 {owner_name}！")])
        return

    if msg_type == "sticker":
        _store("🎨 [LINE 貼圖]", "sticker")

def _build_medication_reminder(binding: dict) -> str:
    from greeting_generator import _match_condition_lines
    condition = binding.get("condition") or "日常養生"
    lines = [
        f"💊 【{binding['name']}的今日用藥與保健叮嚀】",
        "",
        "• 請依照醫師處方按時服藥，不要自行停藥或加量。",
    ]
    care = _match_condition_lines(condition)
    if care:
        lines.append(f"• {care['reserved'][0]}")
        lines.append("")
        lines.append(care["insight"])
    lines.append("")
    lines.append("• 想買市售保健品（如魚油、維他命）前，請先請家人用 GiftSense App 檢驗是否會撞藥喔！")
    return "\n".join(lines)

def _download_line_audio(msg_id: str) -> str:
    try:
        audio_res = requests.get(
            f"https://api-data.line.me/v2/bot/message/{msg_id}/content",
            headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"},
            timeout=15
        )
        if audio_res.status_code == 200:
            os.makedirs("static/uploads", exist_ok=True)
            file_name = f"voice_{msg_id}.m4a"
            with open(os.path.join("static/uploads", file_name), "wb") as f:
                f.write(audio_res.content)
            return f"/api/uploads/{file_name}"
        return "[語音訊息下載失敗]"
    except Exception:
        return "[語音訊息錯誤]"

def _line_reply(reply_token: Optional[str], user_id: str, messages: List[Dict[str, Any]]):
    """優先使用 Reply API（不佔官方帳號每月訊息額度），失敗時才改用 Push"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    messages = messages[:5]
    if reply_token:
        try:
            res = requests.post(
                "https://api.line.me/v2/bot/message/reply",
                headers=headers,
                json={"replyToken": reply_token, "messages": messages},
                timeout=8
            )
            if res.status_code == 200:
                return
            print("LINE Reply 失敗，改用 Push:", res.status_code, res.text[:200])
        except Exception as e:
            print("LINE Reply 例外，改用 Push:", e)
    try:
        requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers=headers,
            json={"to": user_id, "messages": messages},
            timeout=8
        )
    except Exception as e:
        print("LINE 推播失敗:", e)

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
    # Google: id_token（Android/iOS）或 access_token（Web）；Facebook: access_token；Apple: id_token (identityToken)
    id_token: Optional[str] = None
    access_token: Optional[str] = None
    # 以下僅作為顯示名稱參考，身分一律以平台驗證結果為準
    name: Optional[str] = None
    email: Optional[str] = None
    social_id: Optional[str] = None

class RewardClaimRequest(BaseModel):
    account: str
    action: str
    recipient: Optional[str] = ""

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

@app.post("/api/auth/social")
def api_social_login(req: SocialLoginRequest):
    # 💡 向 Google / Facebook / Apple 驗證 token 後才建立或登入會員，不再相信前端傳來的 email
    try:
        identity = verify_social_token(req.provider, req.id_token, req.access_token)
    except SocialAuthError as e:
        return {"success": False, "message": str(e)}

    user = find_or_create_social_user(
        provider=identity["provider"],
        social_id=identity["social_id"],
        email=identity.get("email", ""),
        email_verified=identity.get("email_verified", False),
        name=identity.get("name") or (req.name or "")
    )
    return {
        "success": True,
        "message": f"透過 {identity['provider'].capitalize()} 登入成功！",
        "user": user
    }

@app.post("/api/auth/apple/callback")
async def api_apple_android_callback(request: Request):
    # Android 版 Sign in with Apple 走網頁流程：Apple 把結果 POST 到這裡，再轉回 App
    body = (await request.body()).decode("utf-8")
    return RedirectResponse(
        f"intent://callback?{body}#Intent;package={ANDROID_PACKAGE_NAME};scheme=signinwithapple;end",
        status_code=307
    )

# LINE 個人帳號綁定：App 產生綁定碼，親友在 LINE 官方帳號傳「綁定 123456」
@app.post("/api/recipients/{rec_id}/line-bind")
def create_recipient_line_bind(rec_id: str):
    rec = get_recipient_by_id(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recipient not found")
    bind = create_line_bind_code(rec_id)
    basic_id = _get_line_bot_basic_id()
    add_friend_url = f"https://line.me/R/ti/p/{basic_id}" if basic_id else ""
    invite_text = (
        f"{rec['name']}您好！請先加入 GiftSense 的 LINE 好友"
        + (f"：{add_friend_url}" if add_friend_url else "")
        + f"\n加入後在聊天室傳送「綁定 {bind['code']}」，就能收到我的關懷卡與用藥叮嚀喔❤️（綁定碼 24 小時內有效）"
    )
    return {
        "success": True,
        "recipient_id": rec_id,
        "code": bind["code"],
        "expires_at": bind["expires_at"],
        "bot_basic_id": basic_id,
        "add_friend_url": add_friend_url,
        "invite_text": invite_text,
        "line_bound": rec.get("line_bound", False)
    }

@app.delete("/api/recipients/{rec_id}/line-bind")
def remove_recipient_line_bind(rec_id: str):
    if not get_recipient_by_id(rec_id):
        raise HTTPException(status_code=404, detail="Recipient not found")
    unbind_recipient_line(rec_id)
    return {"success": True, "recipient_id": rec_id, "line_bound": False}

# 回饋點數：由後端判斷每日／每週上限後才發點
@app.post("/api/rewards/claim")
def api_claim_reward(req: RewardClaimRequest):
    if not get_user_profile(req.account):
        raise HTTPException(status_code=404, detail="User not found")
    result = claim_reward(req.account, req.action, req.recipient or "")
    profile = get_user_profile(req.account)
    result["new_points"] = profile["points"] if profile else None
    return result

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