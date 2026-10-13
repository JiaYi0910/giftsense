"""
社群登入 token 驗證（Google / Facebook / Apple）

後端不再相信前端送來的 email，而是向各平台驗證 token 後才取得使用者身分。
所需環境變數（設定於 Render 的 Environment 或 backend/.env）：
- GOOGLE_CLIENT_IDS    : 允許的 Google OAuth Client ID，逗號分隔（預設為目前 App 使用的 Web Client ID）
- FACEBOOK_APP_ID      : Facebook App ID
- FACEBOOK_APP_SECRET  : Facebook App Secret（只放後端，不可放進 App）
- APPLE_CLIENT_IDS     : 允許的 Apple audience，逗號分隔（iOS Bundle ID 與 Android/Web 用的 Services ID）
"""
import os
from typing import Optional, Dict, Any

import requests

GOOGLE_DEFAULT_CLIENT_IDS = ["348160522222-d1ltoloj7gtcid9cd1fq6toe803djhor.apps.googleusercontent.com"]
APPLE_DEFAULT_CLIENT_IDS = ["com.example.giftsense"]
APPLE_ISSUER = "https://appleid.apple.com"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"

_apple_jwk_client = None


class SocialAuthError(Exception):
    pass


def _env_list(name: str, default=None):
    values = [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]
    return values or list(default or [])


def verify_google(id_token: Optional[str] = None, access_token: Optional[str] = None) -> Dict[str, Any]:
    allowed = _env_list("GOOGLE_CLIENT_IDS", GOOGLE_DEFAULT_CLIENT_IDS)
    if id_token:
        params = {"id_token": id_token}
    elif access_token:
        # Flutter Web 版 google_sign_in 只拿得到 access token
        params = {"access_token": access_token}
    else:
        raise SocialAuthError("缺少 Google 驗證憑證")

    try:
        res = requests.get("https://oauth2.googleapis.com/tokeninfo", params=params, timeout=8)
    except requests.RequestException:
        raise SocialAuthError("無法連線至 Google 驗證伺服器，請稍後再試")
    if res.status_code != 200:
        raise SocialAuthError("Google 登入驗證失敗，請重新登入")

    info = res.json()
    if info.get("aud") not in allowed and info.get("azp") not in allowed:
        raise SocialAuthError("Google 登入憑證不屬於本服務")
    if id_token and info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise SocialAuthError("Google 登入憑證發行者不正確")
    if not info.get("sub"):
        raise SocialAuthError("Google 登入憑證缺少使用者識別碼")

    picture = info.get("picture", "")
    name = info.get("name", "")
    if access_token and not picture:
        # Web 版只有 access token：tokeninfo 不含大頭照，改向 userinfo 取得
        try:
            profile = requests.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=8,
            ).json()
            picture = profile.get("picture", "") or ""
            name = name or profile.get("name", "")
        except Exception:
            pass

    return {
        "provider": "google",
        "social_id": info["sub"],
        "email": info.get("email", ""),
        "email_verified": str(info.get("email_verified", "")).lower() == "true",
        "name": name,
        "picture": picture,
    }


def verify_facebook(access_token: Optional[str]) -> Dict[str, Any]:
    app_id = os.environ.get("FACEBOOK_APP_ID", "").strip()
    app_secret = os.environ.get("FACEBOOK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise SocialAuthError("Facebook 登入尚未設定（後端缺少 FACEBOOK_APP_ID / FACEBOOK_APP_SECRET）")
    if not access_token:
        raise SocialAuthError("缺少 Facebook 驗證憑證")

    try:
        debug = requests.get(
            "https://graph.facebook.com/debug_token",
            params={"input_token": access_token, "access_token": f"{app_id}|{app_secret}"},
            timeout=8,
        ).json().get("data", {})
        if not debug.get("is_valid") or str(debug.get("app_id")) != app_id:
            raise SocialAuthError("Facebook 登入驗證失敗，請重新登入")

        me = requests.get(
            "https://graph.facebook.com/me",
            params={"fields": "id,name,email,picture.width(256).height(256)", "access_token": access_token},
            timeout=8,
        ).json()
    except requests.RequestException:
        raise SocialAuthError("無法連線至 Facebook 驗證伺服器，請稍後再試")

    if not me.get("id") or str(me.get("id")) != str(debug.get("user_id")):
        raise SocialAuthError("Facebook 使用者資料不一致")
    picture_data = (me.get("picture") or {}).get("data") or {}

    return {
        "provider": "facebook",
        "social_id": str(me["id"]),
        "email": me.get("email", ""),
        # Facebook 不保證 email 已驗證，因此不用來合併既有帳號
        "email_verified": False,
        "name": me.get("name", ""),
        # 預設剪影頭像不使用，改顯示系統預設圖示
        "picture": "" if picture_data.get("is_silhouette") else picture_data.get("url", ""),
    }


def verify_apple(identity_token: Optional[str]) -> Dict[str, Any]:
    global _apple_jwk_client
    if not identity_token:
        raise SocialAuthError("缺少 Apple 驗證憑證")
    try:
        import jwt
    except ImportError:
        raise SocialAuthError("後端尚未安裝 PyJWT，無法驗證 Apple 登入")

    allowed = _env_list("APPLE_CLIENT_IDS", APPLE_DEFAULT_CLIENT_IDS)
    try:
        if _apple_jwk_client is None:
            _apple_jwk_client = jwt.PyJWKClient(APPLE_KEYS_URL)
        signing_key = _apple_jwk_client.get_signing_key_from_jwt(identity_token)
        claims = jwt.decode(
            identity_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=allowed,
            issuer=APPLE_ISSUER,
        )
    except jwt.PyJWTError:
        raise SocialAuthError("Apple 登入驗證失敗，請重新登入")

    return {
        "provider": "apple",
        "social_id": claims["sub"],
        # Apple 只有第一次登入會給 email，之後以 sub 辨識
        "email": claims.get("email", ""),
        "email_verified": claims.get("email_verified") in (True, "true"),
        "name": "",
        "picture": "",  # Apple 不提供大頭照
    }


def verify_social_token(provider: str, id_token: Optional[str], access_token: Optional[str]) -> Dict[str, Any]:
    provider = (provider or "").lower().strip()
    if provider == "google":
        return verify_google(id_token=id_token, access_token=access_token)
    if provider == "facebook":
        return verify_facebook(access_token)
    if provider == "apple":
        return verify_apple(id_token)
    raise SocialAuthError("不支援的登入方式")
