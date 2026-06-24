import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, ad, lark, scheduler

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

app = FastAPI(title="Bearhouse and Sunsu — ศูนย์รหัสผ่าน")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

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
    username: str
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
def login(body: LoginIn):
    if not config.AD_ENABLED:
        raise HTTPException(503, "ยังไม่ได้ตั้งค่าเชื่อม AD")
    if not ad.verify_password(body.username, body.password):
        raise HTTPException(401, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    return _status_or_500(body.username)


@app.get("/api/status")
def status(username: str):
    return _status_or_500(username)


@app.post("/api/change-password")
def change_password(body: ChangeIn):
    if not config.AD_ENABLED:
        raise HTTPException(503, "ยังไม่ได้ตั้งค่าเชื่อม AD")
    try:
        ad.change_password(body.username, body.current, body.new_password)
    except PermissionError as e:
        raise HTTPException(401, str(e))
    except Exception as e:  # noqa
        raise HTTPException(400, f"เปลี่ยนรหัสไม่สำเร็จ: {e}")
    return {"ok": True}


class TestNotifyIn(BaseModel):
    email: str


@app.post("/api/notify/test")
def notify_test(body: TestNotifyIn):
    if not config.LARK_ENABLED:
        raise HTTPException(503, "ยังไม่ได้ตั้งค่า Lark")
    oid = lark.open_id_by_email(body.email)
    if not oid:
        raise HTTPException(404, "ไม่พบผู้ใช้ใน Lark ตามอีเมลนี้")
    lark.send_expiry_card(oid, "ผู้ทดสอบ", 7, "ทดสอบระบบ")
    return {"ok": True}


@app.post("/api/notify/run")
def notify_run():
    """ทริกเกอร์งานแจ้งเตือนเดี๋ยวนั้น (เผื่ออยากใช้ cron ภายนอกเรียกแทน)"""
    return scheduler.scan_and_notify()
