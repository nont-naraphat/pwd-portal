import os
import time
import hmac
import base64
import hashlib
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, Cookie
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, ad, lark, scheduler

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

app = FastAPI(title="Bearhouse and Sunsu — ศูนย์รหัสผ่าน")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# ----- Session (cookie ลงนามด้วย HMAC + มี timeout) -----
SESSION_SECRET = os.getenv("SESSION_SECRET") or base64.b64encode(os.urandom(32)).decode()
SESSION_TTL = int(os.getenv("SESSION_TIMEOUT_MIN", "30")) * 60
COOKIE = "pwdsession"


def _sign(payload: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _make_token(username: str) -> str:
    payload = f"{username}|{int(time.time()) + SESSION_TTL}"
    b = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"{b}.{_sign(payload)}"


def _parse_token(token: str):
    try:
        b, sig = token.split(".", 1)
        payload = base64.urlsafe_b64decode(b.encode()).decode()
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        username, exp = payload.split("|", 1)
        if int(exp) < int(time.time()):
            return None
        return username
    except Exception:
        return None


def _set_session(resp: Response, username: str):
    resp.set_cookie(COOKIE, _make_token(username), max_age=SESSION_TTL,
                    httponly=True, samesite="lax", path="/")


def _require_user(session: str):
    user = _parse_token(session) if session else None
    if not user:
        raise HTTPException(401, "เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่")
    return user


_sch = None


@app.on_event("startup")
def _startup():
    global _sch
    try:
        _sch = scheduler.start()
    except Exception as e:  # noqa
        log.error("เริ่มตัวตั้งเวลาไม่ได้: %s", e)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "ad": config.AD_ENABLED, "lark": config.LARK_ENABLED}


class LoginIn(BaseModel):
    username: str
    password: str


class ChangeIn(BaseModel):
    current: str
    new_password: str


def _status_or_500(username: str):
    try:
        return ad.get_status(username)
    except LookupError:
        raise HTTPException(404, "ไม่พบบัญชีผู้ใช้")
    except Exception as e:  # noqa
        raise HTTPException(500, f"อ่านสถานะจาก AD ไม่ได้: {e}")


@app.post("/api/login")
def login(body: LoginIn, response: Response):
    if not config.AD_ENABLED:
        raise HTTPException(503, "ยังไม่ได้ตั้งค่าเชื่อม AD")
    if not ad.verify_password(body.username, body.password):
        raise HTTPException(401, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    data = _status_or_500(body.username)
    _set_session(response, body.username)
    return data


@app.get("/api/me")
def me(response: Response, pwdsession: str = Cookie(None)):
    user = _require_user(pwdsession)
    data = _status_or_500(user)
    _set_session(response, user)   # sliding: ต่ออายุทุกครั้งที่ใช้งาน
    return data


@app.get("/api/status")
def status(response: Response, pwdsession: str = Cookie(None)):
    user = _require_user(pwdsession)
    data = _status_or_500(user)
    _set_session(response, user)
    return data


@app.post("/api/change-password")
def change_password(body: ChangeIn, response: Response, pwdsession: str = Cookie(None)):
    user = _require_user(pwdsession)
    if not config.AD_ENABLED:
        raise HTTPException(503, "ยังไม่ได้ตั้งค่าเชื่อม AD")
    try:
        ad.change_password(user, body.current, body.new_password)
    except PermissionError as e:
        raise HTTPException(401, str(e))
    except Exception as e:  # noqa
        raise HTTPException(400, f"เปลี่ยนรหัสไม่สำเร็จ: {e}")
    _set_session(response, user)
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


class TestNotifyIn(BaseModel):
    email: str


@app.post("/api/notify/test")
def notify_test(body: TestNotifyIn, pwdsession: str = Cookie(None)):
    _require_user(pwdsession)
    if not config.LARK_ENABLED:
        raise HTTPException(503, "ยังไม่ได้ตั้งค่า Lark")
    oid = lark.open_id_by_email(body.email)
    if not oid:
        raise HTTPException(404, "ไม่พบผู้ใช้ใน Lark ตามอีเมลนี้")
    lark.send_expiry_card(oid, "ผู้ทดสอบ", 7, "ทดสอบระบบ")
    return {"ok": True}


@app.post("/api/notify/run")
def notify_run():
    return scheduler.scan_and_notify()
