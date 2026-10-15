import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import base64
import hashlib
import hmac
import threading
import time
import platform
import uuid
import random
import re
import requests

# 💡 伺服器一律使用台灣時間（Render 預設是 UTC，會讓 LINE 訊息時間慢 8 小時、聊天排序錯亂）
#    使用 POSIX 時區字串 CST-8（UTC+8、台灣無日光節約），不依賴系統是否安裝時區資料
os.environ["TZ"] = "CST-8"
if hasattr(time, "tzset"):
    time.tzset()

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
    unbind_recipient_line, find_recipient_line_id, get_line_binding_info, claim_reward,
    create_cashback_click, list_cashback_orders, check_cashback_receipt_upload, record_cashback_receipt,
    settle_due_cashback, cancel_tracked_cashback, CASHBACK_RATES, CASHBACK_PENDING_DAYS,
    add_family_message, list_family_messages, latest_family_card,
    set_user_avatar, AVATAR_MAX_LENGTH, check_in_user
)
from social_auth import verify_social_token, SocialAuthError
from line_messages import card as line_card, button as line_button
from rag_engine import query_rag_engine, CLINICAL_LITERATURES
from vector_store import global_vector_store
from tfda_service import global_tfda_service
from pharmacy_crawler import search_pharmacy_products, get_recommended_products_by_condition, warmup_pharmacy_cache
from auto_order import execute_auto_order
from weather_service import get_live_weather
from greeting_generator import generate_ai_greeting
from chips_generator import get_clinical_rule_chips, generate_ai_recipient_chips
from receipt_scanner import scan_receipt, ReceiptScanError

# AI 守護助理每日免費詢問次數；可用關懷點數兌換額外次數
AI_GUARD_DAILY_LIMIT = 3
from database import AI_GUARD_REDEEM_COST, SIGNUP_BONUS_POINTS, round_points, format_points  # 1 點兌換 3 次
AI_GUARD_REDEEM_EXTRA = 3

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

@app.middleware("http")
async def no_cache_web_app(request: Request, call_next):
    # 💡 網頁版（Flutter Web）每次都向伺服器確認是否有新版，部署後一般重新整理就能看到更新；
    #    檔案沒變時伺服器回 304，不會重新下載
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response

@app.on_event("startup")
def startup_warmup_cache():
    # 💡 預熱藥局快取改在背景執行緒進行，避免爬蟲逾時拖慢伺服器啟動
    def _warmup():
        try:
            warmup_pharmacy_cache()
        except Exception as exc:
            print(f"Pharmacy cache warmup failed: {exc}")
    threading.Thread(target=_warmup, daemon=True).start()

# 💡 LINE 金鑰只從環境變數讀取（Render → Environment / backend/.env），不寫在程式碼裡。
#   缺 LINE_CHANNEL_SECRET：/api/line/webhook 拒絕所有請求（無法驗證簽章，避免被偽造）
#   缺 LINE_CHANNEL_ACCESS_TOKEN：LINE 推播、回覆直接略過，其他功能照常
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "").strip()
if not LINE_CHANNEL_SECRET:
    print("【警告】未設定 LINE_CHANNEL_SECRET：LINE webhook 會拒絕所有請求，長輩在 LINE 的訊息與綁定都收不到")
if not LINE_CHANNEL_ACCESS_TOKEN:
    print("【警告】未設定 LINE_CHANNEL_ACCESS_TOKEN：LINE 推播與回覆會略過，關懷卡不會送到長輩的 LINE")
ANDROID_PACKAGE_NAME = os.environ.get("ANDROID_PACKAGE_NAME", "com.example.giftsense")
_line_bot_basic_id_cache = {"value": os.environ.get("LINE_BOT_BASIC_ID", "")}

def _get_line_bot_basic_id() -> str:
    """取得 LINE 官方帳號 ID（如 @123abcde），用來產生加好友連結"""
    if _line_bot_basic_id_cache["value"] or not LINE_CHANNEL_ACCESS_TOKEN:
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

def _verify_line_signature(body: bytes, signature: str) -> bool:
    if not LINE_CHANNEL_SECRET:
        return False
    digest = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode("utf-8"), signature or "")

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
    account: Optional[str] = None

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
    amount: float
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
    sender: Optional[str] = None  # 寄件者帳號（僅用來核對，身分以會員通行證為準）
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
    account: Optional[str] = None

class CashbackActionRequest(BaseModel):
    account: Optional[str] = None

class CashbackReceiptRequest(BaseModel):
    # 只收圖片；購物金額一律由伺服器辨識收據取得，用戶端送來的 amount 等欄位會被忽略
    image: str = ""  # data:image/...;base64,...

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

# 傳情小站訊息存在資料庫 family_messages 表：owner_account = 守護家人的帳號，
# from_role = family（家人發送）/ elder（親友從 LINE 回覆）
def _new_message_id(prefix: str = "msg") -> str:
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"

# 隱私權政策公開網頁（Facebook 等開發者後台的「隱私政策網址」：https://giftsense-vjbu.onrender.com/privacy）
@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy_page():
    from privacy_page import PRIVACY_HTML
    return HTMLResponse(PRIVACY_HTML)

# 系統說明文件：架構圖、流程圖、ER Model、點數回饋、Demo 腳本（https://giftsense-vjbu.onrender.com/guide）
GUIDE_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "guide.html")

@app.get("/guide", response_class=HTMLResponse)
def system_guide_page():
    if not os.path.exists(GUIDE_HTML_PATH):
        raise HTTPException(status_code=404, detail="Guide not found")
    with open(GUIDE_HTML_PATH, encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/health")
def health_check():
    db_stats = get_database_stats()
    return {
        "status": "ok",
        "service": "GiftSense 2.0 Real Python Backend",
        "version": "2.0.0",
        "database": "Turso (libSQL) Connected" if db_stats.get("persistent") else "SQLite (caregift.db) Connected",
        "sqlite_stats": db_stats,
        "python": platform.python_version(),
        "literatures_count": db_stats["counts"].get("clinical_knowledge", len(CLINICAL_LITERATURES)),
        "vector_engine": "MedicalVectorStore (High-Dimensional Cosine)",
        "tfda_engine": "TFDAService (Official Black Box Registry)",
        # 只回報是否已設定，不回傳金鑰本身
        "auth_token_secret": "configured" if _token_secret_base("member") else "missing",
        "line_channel_secret": "configured" if LINE_CHANNEL_SECRET else "missing",
        "line_channel_access_token": "configured" if LINE_CHANNEL_ACCESS_TOKEN else "missing",
        "gemini_api_key": "configured" if os.environ.get("GEMINI_API_KEY", "").strip() else "missing"  # 收據辨識
    }

# =========================================================================
# 登入通行證（HMAC 簽章 + 到期時間）
# - 會員通行證：任何方式登入成功都會核發（30 天有效）。會員 API 一律以它判斷身分，
#   前端送來的 account 只用來核對，不再採信；改 localStorage 的帳號也冒充不了別人。
# - 管理員通行證：只有用帳號密碼登入的管理員才拿得到（7 天有效），用於管理後台與
#   RAG 測試台不限次數。只送 account=admin 不會被當成管理員。
# 簽章金鑰來自環境變數 AUTH_TOKEN_SECRET（Render → Environment），不寫在程式碼裡；
# 兩種通行證用不同的衍生金鑰，會員通行證不能拿來當管理員通行證。
# =========================================================================
MEMBER_TOKEN_TTL = 30 * 24 * 3600
ADMIN_TOKEN_TTL = 7 * 24 * 3600
_TOKEN_PROCESS_SECRET = os.urandom(32)


def _token_secret_base(kind: str) -> str:
    base = os.getenv("AUTH_TOKEN_SECRET") or os.getenv("ADMIN_TOKEN_SECRET") or ""
    if not base and kind == "admin":
        base = os.getenv("ADMIN_PASSWORD") or ""  # 相容舊設定：管理員通行證原本以管理員密碼衍生
    return base


def _token_key(kind: str) -> bytes:
    base = _token_secret_base(kind)
    if not base:
        # 未設定時每次重啟都會失效，需重新登入
        return hashlib.sha256(_TOKEN_PROCESS_SECRET + kind.encode()).digest()
    return hashlib.sha256(f"giftsense-{kind}-token|{base}".encode()).digest()


def _sign_token(kind: str, account: str, ttl: int) -> str:
    payload = f"{account}|{int(time.time()) + ttl}"
    sig = hmac.new(_token_key(kind), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=") + "." + sig


def _token_account(kind: str, token: Optional[str]) -> Optional[str]:
    """簽章正確且未過期時回傳通行證上的帳號，否則回傳 None"""
    try:
        encoded, sig = (token or "").split(".", 1)
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        expected = hmac.new(_token_key(kind), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        account, exp = payload.rsplit("|", 1)
        if not account or int(exp) < time.time():
            return None
        return account
    except Exception:
        return None


def issue_member_token(account: str) -> str:
    return _sign_token("member", account, MEMBER_TOKEN_TTL)


def issue_admin_token(account: str) -> str:
    return _sign_token("admin", account, ADMIN_TOKEN_TTL)


def verify_admin_token(token: Optional[str], account: Optional[str]) -> bool:
    token_account = _token_account("admin", token)
    if not token_account or token_account != (account or ""):
        return False
    profile = get_user_profile(token_account)
    return bool(profile) and profile.get("role") == "admin"


if not _token_secret_base("member"):
    print("【警告】未設定 AUTH_TOKEN_SECRET：會員登入通行證在伺服器重啟後會失效，所有人都要重新登入")


def _request_member_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return request.headers.get("x-user-token", "").strip()


def current_member(request: Request) -> str:
    """會員 API 的身分來源：Authorization: Bearer <會員通行證>（或 X-User-Token）"""
    account = _token_account("member", _request_member_token(request))
    if not account:
        raise HTTPException(status_code=401, detail="請先登入（登入已過期或無效）")
    return account


def current_admin(request: Request) -> str:
    """管理後台 API：需要有效的管理員通行證（X-Admin-Token）"""
    account = _token_account("admin", request.headers.get("x-admin-token"))
    profile = get_user_profile(account) if account else None
    if not profile or profile.get("role") != "admin":
        raise HTTPException(status_code=401, detail="需要管理員登入")
    return account


def _ensure_same_account(member: str, claimed: Any):
    # 舊版前端仍會送 account；若和通行證上的帳號不同，代表想讀寫別人的資料
    claimed = str(claimed or "").strip()
    if claimed and claimed != member:
        raise HTTPException(status_code=403, detail="無權存取其他會員的資料")


def _owned_recipient(rec_id: str, member: str) -> dict:
    # 不是自己的親友一律回 404，不透露這筆資料是否存在
    rec = get_recipient_by_id(rec_id)
    if not rec or rec.get("user_account") != member:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return rec


def _login_result(user: dict, message: str) -> dict:
    return {"success": True, "message": message, "user": user, "user_token": issue_member_token(user["account"])}


@app.post("/api/auth/login")
def api_login(req: LoginRequest):
    user = authenticate_user(req.account, req.password)
    if not user:
        return {"success": False, "message": "帳號或密碼錯誤，請重新確認！"}
    result = _login_result(user, f"歡迎回來，{user['name']}！")
    if user.get("role") == "admin":
        result["admin_token"] = issue_admin_token(user["account"])
    return result

@app.post("/api/auth/register")
def api_register(req: RegisterRequest):
    user = register_user(req.account, req.password, req.name, req.role or "user")
    if not user:
        return {"success": False, "message": "此帳號已存在，請直接登入！"}
    return _login_result(user, f"註冊成功！已發放新會員 {format_points(SIGNUP_BONUS_POINTS)} 點獎勵！")

@app.get("/api/auth/profile")
def api_user_profile(account: Optional[str] = None, member: str = Depends(current_member)):
    _ensure_same_account(member, account)
    _settle_cashback_quietly(member)
    profile = get_user_profile(member)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "profile": profile}

@app.post("/api/guard/query")
def guard_query(req: GuardQueryRequest, request: Request, member: str = Depends(current_member)):
    _ensure_same_account(member, req.account)
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # 管理員（持有效通行證）在 RAG 測試台不限次數
    if verify_admin_token(request.headers.get("x-admin-token"), member):
        allowed, quota = True, {"unlimited": True, "remaining": None, "limit": None}
    else:
        allowed, quota = consume_ai_guard_quota(member, AI_GUARD_DAILY_LIMIT)
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
def guard_quota(request: Request, account: Optional[str] = None, member: str = Depends(current_member)):
    _ensure_same_account(member, account)
    if verify_admin_token(request.headers.get("x-admin-token"), member):
        quota = {"unlimited": True, "remaining": None, "limit": None}
    else:
        quota = get_ai_guard_quota(member, AI_GUARD_DAILY_LIMIT)
    return {
        "success": True,
        "quota": quota,
        "redeem_cost": AI_GUARD_REDEEM_COST,
        "redeem_extra": AI_GUARD_REDEEM_EXTRA
    }

@app.post("/api/guard/redeem")
def guard_redeem(req: GuardRedeemRequest, member: str = Depends(current_member)):
    _ensure_same_account(member, req.account)
    profile = get_user_profile(member)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    if (profile.get("points") or 0) < AI_GUARD_REDEEM_COST:
        return {"success": False, "message": f"點數不足，兌換需要 {AI_GUARD_REDEEM_COST} 點"}

    add_points_transaction(account=member, amount=-AI_GUARD_REDEEM_COST, title=f"兌換 AI 守護助理詢問 {AI_GUARD_REDEEM_EXTRA} 次")
    quota = add_ai_guard_bonus(member, AI_GUARD_REDEEM_EXTRA, AI_GUARD_DAILY_LIMIT)
    return {
        "success": True,
        "message": f"已使用 {AI_GUARD_REDEEM_COST} 點兌換 {AI_GUARD_REDEEM_EXTRA} 次詢問！",
        "quota": quota,
        "new_points": round_points(profile["points"] - AI_GUARD_REDEEM_COST)
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

# 舊版代購示範（App 已不使用）：會寫入訂單並發點數，限管理員
@app.post("/api/pharmacy/auto-order")
def pharmacy_auto_order(req: AutoOrderRequest, admin: str = Depends(current_admin)):
    return execute_auto_order(
        product_name=req.product_name, price=req.price,
        pharmacy=req.pharmacy, recipient=req.recipient
    )

@app.post("/api/pharmacy/referral-click")
def pharmacy_referral_click(req: ReferralClickRequest, member: str = Depends(current_member)):
    # 💡 ShopBack 模式：點擊只建立「購物追蹤」，上傳收據後才回饋點數（不再點擊就送點）
    _ensure_same_account(member, req.account)
    if not get_user_profile(member):
        return {"success": False, "message": "請先登入，才能追蹤購物回饋", "official_url": req.official_url}
    order = create_cashback_click(
        account=member, pharmacy=req.pharmacy, product_name=req.product_name,
        est_price=req.price, recipient=req.recipient, official_url=req.official_url
    )
    return {
        "success": True,
        "cashback": order,
        "message": f"已開始追蹤購物回饋：在【{req.pharmacy}】完成購物後上傳收據，可獲得約 {order['rate_percent']}% 點數回饋",
        "official_url": req.official_url
    }

# 購物回饋（ShopBack 模式）：上傳收據 → Gemini 辨識金額 → 待入帳 7 天 → 自動入帳
RECEIPT_IMAGE_MAX_BYTES = 8 * 1024 * 1024
_RECEIPT_DATA_URL = re.compile(r"^data:(image/(?:png|jpe?g|webp|heic|heif));base64,([A-Za-z0-9+/=\s]+)$")

def _settle_cashback_quietly(account: Optional[str] = None):
    # 待入帳期滿的回饋在會員讀取資料時順便入帳；失敗不影響原本的請求
    try:
        settle_due_cashback(account=account)
    except Exception as e:
        print("購物回饋自動入帳失敗:", e)

@app.on_event("startup")
def startup_cashback_settler():
    # Render 免費方案會休眠，這裡只是補強；會員讀取點數時也會結算
    def _loop():
        while True:
            _settle_cashback_quietly()
            time.sleep(3600)
    threading.Thread(target=_loop, daemon=True).start()

@app.get("/api/cashback")
def api_list_cashback(account: Optional[str] = None, member: str = Depends(current_member)):
    _ensure_same_account(member, account)
    _settle_cashback_quietly(member)
    return {
        "success": True, "rates": CASHBACK_RATES, "pending_days": CASHBACK_PENDING_DAYS,
        **list_cashback_orders(member)
    }

@app.post("/api/cashback/{order_id}/receipt")
def api_upload_cashback_receipt(order_id: str, req: CashbackReceiptRequest, member: str = Depends(current_member)):
    match = _RECEIPT_DATA_URL.match((req.image or "").strip())
    if not match:
        return {"success": False, "retake": True, "message": "請上傳 JPG、PNG、WebP 或 HEIC 格式的收據照片"}
    mime_type = "image/jpeg" if match.group(1) == "image/jpg" else match.group(1)
    try:
        image_bytes = base64.b64decode(re.sub(r"\s", "", match.group(2)), validate=True)
    except ValueError:
        return {"success": False, "retake": True, "message": "收據圖片無法讀取，請重新選擇"}
    if not image_bytes or len(image_bytes) > RECEIPT_IMAGE_MAX_BYTES:
        return {"success": False, "retake": True, "message": "收據圖片太大，請重新拍攝或選擇較小的圖片"}
    receipt_hash = hashlib.sha256(image_bytes).hexdigest()

    # 先做不需要辨識的檢查，重複或不能上傳的紀錄就不必送 Gemini
    order, error = check_cashback_receipt_upload(order_id, member, receipt_hash)
    if error:
        return {"success": False, "retake": False, "message": error, "order": order}
    try:
        scan = scan_receipt(image_bytes, mime_type)
    except ReceiptScanError as e:
        print("收據辨識失敗:", e)
        return {"success": False, "retake": False, "message": "收據辨識服務暫時無法使用，請稍後再試", "order": order}
    order, error, retake = record_cashback_receipt(order_id, member, scan, receipt_hash)
    if error:
        return {"success": False, "retake": retake, "message": error, "order": order}
    return {
        "success": True,
        "message": (f"已登錄 {order['pharmacy']} 收據 ${order['order_amount']:,}，"
                    f"{order['points']} 點回饋將在 {CASHBACK_PENDING_DAYS} 天後自動入帳"),
        "order": order,
    }

@app.post("/api/cashback/{order_id}/cancel")
def api_cancel_cashback(order_id: str, req: CashbackActionRequest, member: str = Depends(current_member)):
    _ensure_same_account(member, req.account)
    order, error = cancel_tracked_cashback(order_id, member)
    if error:
        return {"success": False, "message": error, "order": order}
    return {"success": True, "message": "已取消這筆購物追蹤", "order": order}

@app.get("/api/weather")
def weather_forecast(city: str = "台北市", key: Optional[str] = None):
    weather = get_live_weather(city=city, cwa_api_key=key)
    return {"success": True, "weather": weather}

@app.get("/api/recipients")
def list_recipients(account: Optional[str] = None, member: str = Depends(current_member)):
    _ensure_same_account(member, account)
    return {"success": True, "recipients": get_all_recipients(user_account=member)}

@app.post("/api/recipients")
def create_new_recipient(data: dict, member: str = Depends(current_member)):
    _ensure_same_account(member, data.get("user_account"))
    try:
        # 💡 明確從前端 payload 提取對應欄位，親友一律掛在通行證上的帳號底下
        name = data.get("name")
        condition = data.get("condition")
        phone = data.get("phone", "")
        birthday = data.get("birthday", "")
        quick_tags = data.get("quick_tags")

        rec = add_recipient(
            name=name,
            condition=condition,
            phone=phone,
            birthday=birthday,
            user_account=member,
            quick_tags=quick_tags
        )
        return {"success": True, "recipient": rec}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.put("/api/recipients/{rec_id}")
def edit_recipient(rec_id: str, req: RecipientUpdateRequest, member: str = Depends(current_member)):
    row = _owned_recipient(rec_id, member)

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
def remove_recipient(rec_id: str, member: str = Depends(current_member)):
    _owned_recipient(rec_id, member)
    delete_recipient(rec_id=rec_id)
    return {"success": True, "deleted_id": rec_id}

# 親友專屬快速提問晶片（臨床規則 + AI 雙軌）
@app.get("/api/recipients/{rec_id}/chips")
def get_recipient_chips_endpoint(rec_id: str, member: str = Depends(current_member)):
    rec = _owned_recipient(rec_id, member)
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
def generate_recipient_chips_endpoint(rec_id: str, req: GenerateChipsRequest, member: str = Depends(current_member)):
    rec = get_recipient_by_id(rec_id)
    if rec and rec.get("user_account") != member:
        raise HTTPException(status_code=404, detail="Recipient not found")
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
def list_orders(member: str = Depends(current_member)):
    return {"success": True, "orders": get_all_orders(user_account=member)}

@app.post("/api/orders")
def save_new_order(req: OrderCreateRequest, member: str = Depends(current_member)):
    ord_res = create_order(
        order_id=req.order_id, items=req.items, total=req.total,
        recipient=req.recipient, pharmacy=req.pharmacy or "連鎖藥局", user_account=member
    )
    return {"success": True, "order": ord_res}

@app.post("/api/orders/{order_id}/cancel")
def cancel_existing_order(order_id: str, member: str = Depends(current_member)):
    if not cancel_order(order_id=order_id, user_account=member):
        raise HTTPException(status_code=404, detail="Order not found")
    return {"success": True, "canceled_id": order_id}

@app.get("/api/points")
def list_points(account: Optional[str] = None, member: str = Depends(current_member)):
    _ensure_same_account(member, account)
    return {"success": True, "ledger": get_points_ledger(account=member)}

# 手動加減點數（App 不使用；一般會員的點數只能由後端規則發放），限管理員
@app.post("/api/points")
def add_points_tx(req: PointsTxRequest, admin: str = Depends(current_admin)):
    add_points_transaction(account=req.account, amount=req.amount, title=req.title)
    return {"success": True, "account": req.account, "amount": req.amount}

def _refresh_rag_index():
    """實證文獻有變動時重建 AI 守護助理的檢索索引（資料庫是唯一來源）"""
    try:
        return global_vector_store.reload(get_all_clinical_knowledge())
    except Exception as e:
        print("RAG 索引重建失敗：", e)
        return None

# 啟動時改用資料庫中的文獻建立索引（管理員編輯過的內容在重啟後仍然有效）
_refresh_rag_index()

@app.get("/api/knowledge")
def list_clinical_knowledge():
    items = get_all_clinical_knowledge()
    if not items:
        items = CLINICAL_LITERATURES
    return {"success": True, "total": len(items), "source": "SQLite (caregift.db)", "literatures": items}

# 以下為管理後台（實證文獻庫、RAG 設定、資料庫主控台）的寫入與匯出，需管理員通行證
@app.post("/api/knowledge")
def add_or_update_clinical_knowledge(req: KnowledgeItemRequest, admin: str = Depends(current_admin)):
    item = save_clinical_knowledge(req.dict())
    _refresh_rag_index()
    return {"success": True, "item": item}

@app.post("/api/knowledge/sync")
def sync_clinical_knowledge(req: KnowledgeSyncRequest, admin: str = Depends(current_admin)):
    saved_count = batch_save_clinical_knowledge(req.literatures)
    _refresh_rag_index()
    return {"success": True, "saved_count": saved_count}

@app.post("/api/knowledge/reset")
def reset_clinical_knowledge(admin: str = Depends(current_admin)):
    res = reset_clinical_knowledge_to_defaults()
    _refresh_rag_index()
    return {"success": True, "total": len(res), "literatures": res}

@app.delete("/api/knowledge/{item_id}")
def remove_clinical_knowledge(item_id: str, admin: str = Depends(current_admin)):
    delete_clinical_knowledge(item_id)
    _refresh_rag_index()
    return {"success": True, "deleted_id": item_id}

@app.get("/api/config/rag")
def get_rag_configuration(admin: str = Depends(current_admin)):
    cfg = get_system_config("rag_config", default={
        "topK": 3, "simThreshold": 0.25, "temperature": 0.3, "model": "builtin", "apiKey": "",
        "systemPrompt": "你是一位嚴謹客觀的臨床醫療與保健營養專家。請根據檢索到的國家級文獻 [1][2] 提供建議，嚴禁編造事實。若親友有服用處方藥，必須嚴格審核抗凝血與撞藥禁忌，並附上醫療免責聲明。"
    })
    return {"success": True, "config": cfg}

@app.post("/api/config/rag")
def save_rag_configuration(req: RAGConfigRequest, admin: str = Depends(current_admin)):
    set_system_config("rag_config", req.dict())
    return {"success": True, "config": req.dict()}

@app.get("/api/db/stats")
def database_statistics(admin: str = Depends(current_admin)):
    return {"success": True, "stats": get_database_stats()}

@app.get("/api/db/export")
def database_export(admin: str = Depends(current_admin)):
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
def get_family_messages(elder: str = "", account: Optional[str] = None, member: str = Depends(current_member)):
    # 💡 只回傳「這個帳號 × 這位親友」的一對一對話，避免不同使用者或不同親友的訊息混在一起
    _ensure_same_account(member, account)
    return {"success": True, "messages": list_family_messages(member, elder.strip())}

@app.post("/api/messages")
def post_family_message(req: FamilyMessageRequest, member: str = Depends(current_member)):
    # sender 是寄件者帳號：一律以通行證上的帳號為準
    _ensure_same_account(member, req.sender)
    timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")  # 一律以伺服器的台灣時間為準
    content_text = req.content

    sender_display = member
    conn = get_db()
    user_row = conn.execute("SELECT name FROM users WHERE account = ?", (member,)).fetchone()
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
        "id": _new_message_id(),
        "sender": sender_display,
        "elder": req.elder,
        "content": content_text,
        "type": req.type or "card",
        "timestamp": timestamp_str,
        "owner_account": member,
        "from_role": "family",
    }
    add_family_message(new_msg)

    if member != req.elder:
        # 💡 只推播給寄件者帳號底下的這位親友，避免不同使用者的同名親友收到別人的訊息
        target_line_id = find_recipient_line_id(req.elder, member)
        if target_line_id and LINE_CHANNEL_ACCESS_TOKEN:
            url = "https://api.line.me/v2/bot/message/push"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
            }
            if req.type == "card":
                push_message = _with_quick_reply(_care_card(sender_display, content_text, timestamp_str))
            else:
                push_message = _with_quick_reply(line_card(
                    f"{sender_display} 傳來訊息", paragraphs=[content_text], compact=True
                ))
            payload = {
                "to": target_line_id,
                "messages": [push_message]
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

    # 💡 沒有 Channel secret 就無法驗證簽章，一律拒絕，避免有人偽造綁定或長輩訊息
    if not LINE_CHANNEL_SECRET:
        print("LINE webhook 未設定 LINE_CHANNEL_SECRET，已拒絕此請求")
        raise HTTPException(status_code=503, detail="LINE webhook is not configured")

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

def _with_quick_reply(message: dict) -> dict:
    return {**message, "quickReply": LINE_QUICK_REPLY}

# ---------- 機器人訊息卡片（統一使用 line_messages.card 樣式）----------

def _welcome_cards() -> List[Dict[str, Any]]:
    return [
        line_card(
            "歡迎加入 GiftSense",
            subtitle="心意，醫觸即達",
            paragraphs=["在這裡，您會收到家人傳來的暖心問候、健康關懷卡與用藥叮嚀，也能直接留言或傳語音給家人。"],
            alt_text="歡迎加入 GiftSense！完成綁定後就能收到家人的關懷卡。",
        ),
        _unbound_card(),
    ]

def _unbound_card() -> Dict[str, Any]:
    return line_card(
        "完成綁定，開始接收關懷",
        steps=[
            "請家人在 GiftSense App 的「親友健康資料庫」產生綁定碼",
            "在這個聊天室傳送下方訊息（數字換成家人給您的綁定碼）",
        ],
        info="綁定 123456",
        note="綁定碼 24 小時內有效，使用一次後即失效。",
        alt_text="尚未綁定：請向家人索取綁定碼，傳送「綁定 123456」。",
    )

def _help_card() -> Dict[str, Any]:
    return line_card(
        "服務說明",
        subtitle="點下方選單就能使用以下功能",
        rows=[
            ("今日關懷", "查看家人最新送來的關懷卡"),
            ("今日用藥", "服藥與保健叮嚀"),
            ("緊急求助", "立即通知守護您的家人"),
            ("綁定說明", "如何綁定與改綁家人"),
            ("我的綁定", "查看目前綁定的家人"),
        ],
        note="直接傳文字或語音，就會轉達給家人。",
        buttons=[line_button("今日關懷", primary=True)],
    )

def _care_card(sender: str, content: str, timestamp: str = "") -> Dict[str, Any]:
    body = content
    prefix = f"【來自 {sender} 的健康關懷】"
    if body.startswith(prefix):
        body = body[len(prefix):].strip()
    return line_card(
        f"來自 {sender} 的關懷",
        subtitle=timestamp[5:16].replace("-", "/") if timestamp else None,
        paragraphs=[body],
        buttons=[line_button("今日用藥"), line_button("服務說明")],
        alt_text=f"{sender} 送來一張關懷卡：{body}",
    )

def _medication_card(binding: dict) -> Dict[str, Any]:
    from greeting_generator import _match_condition_lines
    condition = binding.get("condition") or "日常養生"
    steps = ["請依照醫師處方按時服藥，不要自行停藥或加量。"]
    care = _match_condition_lines(condition)
    if care:
        steps.append(care["reserved"][0])
    steps.append("想買市售保健品（如魚油、維他命）前，請先請家人用 GiftSense App 檢驗是否會撞藥。")
    return line_card(
        "今日用藥叮嚀",
        subtitle=f"{binding['name']} · {condition}",
        steps=steps,
        info=care["insight"] if care else None,
        buttons=[line_button("今日關懷")],
    )

def _handle_line_event(event: dict):
    event_type = event.get("type")
    user_id = event.get("source", {}).get("userId")
    reply_token = event.get("replyToken")
    print(f"【解析事件】類型: {event_type}, 用戶 ID: {user_id}")
    if not user_id:
        return

    binding = get_line_binding_info(user_id)

    def reply(*messages):
        msgs = list(messages)
        msgs[-1] = _with_quick_reply(msgs[-1]) if binding else msgs[-1]
        _line_reply(reply_token, user_id, msgs)

    if event_type == "follow":
        if binding:
            reply(line_card(
                f"歡迎回來，{binding['name']}",
                paragraphs=[f"您已完成綁定，{binding['owner_name']} 傳送的關懷卡會直接送到這裡。"],
                buttons=[line_button("今日關懷", primary=True), line_button("今日用藥")],
            ))
        else:
            reply(*_welcome_cards())
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
            binding = get_line_binding_info(user_id)
            owner = rec.get("owner_name") or "家人"
            reply(line_card(
                "綁定成功",
                subtitle=f"您好，{rec['name']}",
                paragraphs=[f"{owner} 傳送的健康關懷與用藥叮嚀，會即時送到這個聊天室。"],
                note="點下方選單就能使用各項功能。",
                buttons=[line_button("今日關懷", primary=True), line_button("服務說明")],
            ))
        else:
            reply(line_card(
                "綁定失敗",
                paragraphs=["綁定碼錯誤或已過期（有效 24 小時）。"],
                info="請家人在 App 重新產生綁定碼後再試一次",
                danger=True,
            ))
        return

    # 2. 尚未綁定：只回覆綁定教學，訊息不存入系統
    if not binding:
        reply(_unbound_card())
        return

    elder_name = binding["name"]
    owner_name = binding["owner_name"]
    owner_account = binding["user_account"]

    def _store(content: str, store_type: str = "text"):
        add_family_message({
            "id": _new_message_id("msg_line"),
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
            card_msg = latest_family_card(owner_account, elder_name)
            if card_msg:
                reply(_care_card(card_msg.get("sender") or owner_name, card_msg["content"], card_msg.get("timestamp", "")))
            else:
                reply(line_card(
                    "今日關懷",
                    paragraphs=[f"{owner_name} 今天還沒有送關懷卡喔！"],
                    note="想念家人的話，可以直接在這裡留言，我會幫您轉達。",
                ))
            return

        if cmd in LINE_CMD_MEDICATION:
            reply(_medication_card(binding))
            return

        if cmd in LINE_CMD_SOS:
            _store("🚨【親友發出緊急求助訊號】", "text")
            reply(line_card(
                "已通知守護家人",
                subtitle="緊急求助",
                paragraphs=[f"系統已通知 {owner_name}，請保持電話暢通，家人會盡快與您聯絡。"],
                info="若情況緊急，請立即撥打 119",
                buttons=[line_button("撥打 119", uri="tel:119", primary=True)],
                danger=True,
            ))
            return

        if cmd in LINE_CMD_BIND_HELP:
            reply(line_card(
                "綁定說明",
                rows=[("目前綁定", elder_name), ("守護家人", owner_name)],
                paragraphs=["若要改綁其他家人，請向對方索取 GiftSense App 上的新綁定碼，並傳送："],
                info="綁定 123456",
            ))
            return

        if cmd in LINE_CMD_HELP:
            reply(_help_card())
            return

        if cmd in LINE_CMD_MY_BINDING:
            reply(line_card(
                "我的綁定",
                rows=[
                    ("綁定身分", elder_name),
                    ("守護家人", owner_name),
                    ("健康狀況", binding.get("condition") or "日常養生"),
                ],
                buttons=[line_button("綁定說明")],
            ))
            return

        # 一般文字留言：轉達給家人
        _store(text, "text")
        reply(line_card(f"已轉達給 {owner_name}", paragraphs=[text], compact=True))
        return

    if msg_type == "audio":
        _store(_download_line_audio(msg.get("id")), "audio")
        reply(line_card(f"語音已轉達給 {owner_name}", compact=True))
        return

    if msg_type == "sticker":
        _store("🎨 [LINE 貼圖]", "sticker")

def _download_line_audio(msg_id: str) -> str:
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return "[語音訊息下載失敗]"
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
    if not LINE_CHANNEL_ACCESS_TOKEN:
        return
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
def api_add_points_alias(req: PointsTxRequest, admin: str = Depends(current_admin)):
    target_account = req.account if req.account else "test"
    add_points_transaction(account=target_account, amount=req.amount, title=req.title)
    profile = get_user_profile(target_account)
    updated_points = profile["points"] if profile else req.amount
    return {"success": True, "message": f"成功新增 {format_points(req.amount)} 點！", "new_points": updated_points}

@app.get("/api/user/profile")
def api_get_user_profile(account: Optional[str] = None, member: str = Depends(current_member)):
    _ensure_same_account(member, account)
    profile = get_user_profile_by_account(member)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "profile": profile}

@app.put("/api/user/profile")
def api_update_user_profile(req: dict, member: str = Depends(current_member)):
    _ensure_same_account(member, req.get("account"))
    name = req.get("name")
    phone = req.get("phone", "")
    birthday = req.get("birthday", "")
    bio = req.get("bio", "")
    avatar = req.get("avatar")  # 沒帶就維持原本的頭貼（上傳頭貼改用 /api/user/avatar）

    if not name:
        return {"success": False, "message": "帳號與顯示名稱不能為空"}

    success = update_user_profile_in_db(member, name, phone, birthday, bio, avatar)
    if success:
        return {"success": True, "message": "個人資料與 SQLite 資料庫更新成功"}
    return {"success": False, "message": "更新失敗"}

class CheckInRequest(BaseModel):
    account: Optional[str] = None

@app.post("/api/user/checkin")
def api_user_checkin(req: CheckInRequest, member: str = Depends(current_member)):
    """連續登入天數：每天第一次開啟時打卡，中斷就從第 1 天重新計算"""
    _ensure_same_account(member, req.account)
    result = check_in_user(member)
    if result is None:
        return {"success": False, "streak": 1}
    return {"success": True, **result}

class AvatarUploadRequest(BaseModel):
    account: Optional[str] = None
    image: str = ""  # data:image/...;base64,...；空字串 = 移除自訂頭貼

@app.post("/api/user/avatar")
def api_upload_avatar(req: AvatarUploadRequest, member: str = Depends(current_member)):
    _ensure_same_account(member, req.account)
    image = (req.image or "").strip()
    if image:
        if not re.match(r"^data:image/(png|jpe?g|webp|gif);base64,[A-Za-z0-9+/=]+$", image):
            return {"success": False, "message": "頭貼格式不支援，請上傳 JPG、PNG 或 WebP 圖片"}
        if len(image) > AVATAR_MAX_LENGTH:
            return {"success": False, "message": "圖片太大，請選擇較小的照片"}
    avatar_url = set_user_avatar(member, image)
    if avatar_url is None:
        return {"success": False, "message": "找不到這個會員帳號"}
    return {"success": True, "avatar_url": avatar_url}

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
    account: Optional[str] = None
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
        name=identity.get("name") or (req.name or ""),
        picture=identity.get("picture", "")
    )
    return _login_result(user, f"透過 {identity['provider'].capitalize()} 登入成功！")

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
def create_recipient_line_bind(rec_id: str, member: str = Depends(current_member)):
    rec = _owned_recipient(rec_id, member)
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
def remove_recipient_line_bind(rec_id: str, member: str = Depends(current_member)):
    _owned_recipient(rec_id, member)
    unbind_recipient_line(rec_id)
    return {"success": True, "recipient_id": rec_id, "line_bound": False}

# 回饋點數：由後端判斷每日／每週上限後才發點
@app.post("/api/rewards/claim")
def api_claim_reward(req: RewardClaimRequest, member: str = Depends(current_member)):
    _ensure_same_account(member, req.account)
    if not get_user_profile(member):
        raise HTTPException(status_code=404, detail="User not found")
    result = claim_reward(member, req.action, req.recipient or "")
    profile = get_user_profile(member)
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