import os

def _bool(v: str, default: bool = True) -> bool:
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

# --- Active Directory ---
AD_HOST       = os.getenv("AD_HOST", "dc01.bearhouse.sunsu.local")
AD_PORT       = int(os.getenv("AD_PORT", "636"))
AD_USE_SSL    = _bool(os.getenv("AD_USE_SSL"), True)
AD_BASE_DN    = os.getenv("AD_BASE_DN", "DC=bearhouse,DC=sunsu,DC=local")
AD_USER_OU    = os.getenv("AD_USER_OU", AD_BASE_DN)          # ขอบเขตค้นหา user สำหรับแจ้งเตือน
AD_UPN_SUFFIX = os.getenv("AD_UPN_SUFFIX", "bearhouse.sunsu.local")
AD_BIND_USER  = os.getenv("AD_BIND_USER", "svc-pwdportal@bearhouse.sunsu.local")
AD_BIND_PASSWORD = os.getenv("AD_BIND_PASSWORD", "")
AD_CA_CERT    = os.getenv("AD_CA_CERT", "/certs/bearhouse-ca.crt")
# "required" = ตรวจใบรับรอง LDAPS (แนะนำ), "none" = ข้ามการตรวจ (ใช้ทดสอบเท่านั้น)
AD_TLS_VALIDATE = os.getenv("AD_TLS_VALIDATE", "required").lower()

# --- Lark ---
LARK_DOMAIN     = os.getenv("LARK_DOMAIN", "https://open.larksuite.com")
LARK_APP_ID     = os.getenv("LARK_APP_ID", "")
LARK_APP_SECRET = os.getenv("LARK_APP_SECRET", "")

# --- การแจ้งเตือน ---
NOTIFY_DAYS = [int(x) for x in os.getenv("NOTIFY_DAYS", "14,7,3,1").split(",") if x.strip()]
NOTIFY_HOUR = int(os.getenv("NOTIFY_HOUR", "9"))
PORTAL_URL  = os.getenv("PORTAL_URL", "https://pwd.bearhouse.sunsu.local")

LARK_ENABLED = bool(LARK_APP_ID and LARK_APP_SECRET)
AD_ENABLED   = bool(AD_BIND_PASSWORD)
