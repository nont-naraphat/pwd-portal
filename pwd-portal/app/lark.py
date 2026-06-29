"""ส่งการ์ดแจ้งเตือนเข้า Lark ผ่าน Custom App (tenant_access_token)"""
import json
import time
import logging

import httpx

from . import config

log = logging.getLogger("lark")

# ─────────────────────────────────────────────────────────────────────────────
# img_key ของรูปกล่อง 2 อัน (ใส่ให้แล้ว)
# ─────────────────────────────────────────────────────────────────────────────
M1_IMG_KEY = "img_v3_02134_175bb743-731d-4c70-aa4c-afd33268bdhu"   # รูปกล่องวิธีที่ 1
M2_IMG_KEY = "img_v3_02134_146db6b0-e6d0-46fb-b09e-6105894b3ehu"   # รูปกล่องวิธีที่ 2
# ─────────────────────────────────────────────────────────────────────────────

_token = {"value": None, "exp": 0}


def _get_token() -> str:
    if not config.LARK_ENABLED:
        raise RuntimeError("ยังไม่ได้ตั้งค่า LARK_APP_ID / LARK_APP_SECRET")
    if _token["value"] and time.time() < _token["exp"] - 60:
        return _token["value"]
    r = httpx.post(
        f"{config.LARK_DOMAIN}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": config.LARK_APP_ID, "app_secret": config.LARK_APP_SECRET},
        timeout=10,
    )
    d = r.json()
    if d.get("code") != 0:
        log.error("ขอ tenant_access_token ไม่สำเร็จ: %s", d)
        raise RuntimeError(f"ขอ token ไม่สำเร็จ: {d}")
    log.info("ได้ tenant_access_token แล้ว")
    _token["value"] = d["tenant_access_token"]
    _token["exp"] = time.time() + d.get("expire", 7200)
    return _token["value"]


def open_id_by_email(email: str):
    token = _get_token()
    r = httpx.post(
        f"{config.LARK_DOMAIN}/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id",
        headers={"Authorization": f"Bearer {token}"},
        json={"emails": [email]},
        timeout=10,
    )
    resp = r.json()
    if resp.get("code") != 0:
        log.error("หา user จากอีเมลไม่ได้ (อาจขาด scope/contact): email=%s resp=%s", email, resp)
        return None
    users = resp.get("data", {}).get("user_list", [])
    oid = users[0].get("user_id") if users and users[0].get("user_id") else None
    if not oid:
        log.warning("ไม่พบ Lark user ตามอีเมลนี้ (อีเมล AD อาจไม่ตรงกับ Lark): email=%s resp=%s", email, resp)
    else:
        log.info("พบ Lark user: email=%s open_id=%s", email, oid)
    return oid


# ─────────────────────────────────────────────────────────────────────────────
# สร้างการ์ด (โครงสร้าง 1.0 — รองรับทุกเวอร์ชัน Lark)
# ─────────────────────────────────────────────────────────────────────────────
def _intro(name, days, expiry_date):
    return (f"เรียน คุณ{name}\n\n"
            f"รหัสผ่าน **Active Directory** จะหมดอายุใน **{days} วัน** (วันที่ {expiry_date})\n"
            f"รหัสนี้ใช้เข้า 💻 คอมพิวเตอร์ · 📶 WiFi ออฟฟิศ · 🔐 VPN — กรุณาเปลี่ยนก่อนหมดอายุ\n\n"
            f"**เปลี่ยนได้ 2 วิธี เลือกอันที่สะดวก** 👇")


def _card(name: str, days: int, expiry_date: str) -> dict:
    portal = config.PORTAL_URL
    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": _intro(name, days, expiry_date)}},
    ]
    # กล่องวิธีที่ 1 (รูป) + ปุ่มจริง
    if M1_IMG_KEY:
        elements.append({"tag": "img", "img_key": M1_IMG_KEY, "mode": "fit_horizontal",
                         "alt": {"tag": "plain_text", "content": "วิธีที่ 1: กดลิงก์เปลี่ยนรหัสผ่าน"}})
    elements.append({"tag": "action", "actions": [
        {"tag": "button", "type": "primary",
         "text": {"tag": "plain_text", "content": "เปลี่ยนรหัสผ่าน"}, "url": portal}]})
    # กล่องวิธีที่ 2 (รูป)
    if M2_IMG_KEY:
        elements.append({"tag": "img", "img_key": M2_IMG_KEY, "mode": "fit_horizontal",
                         "alt": {"tag": "plain_text", "content": "วิธีที่ 2: กด Ctrl Alt Delete"}})
    else:
        elements.append({"tag": "div", "text": {"tag": "lark_md",
            "content": "**2️⃣ กด Ctrl + Alt + Delete ที่เครื่อง**\n📍 ใช้ได้เฉพาะคอมในเครือข่ายออฟฟิศ\n"
                       "1. กดสามปุ่มพร้อมกัน เลือก Change a password\n2. ใส่รหัสเดิม → ใหม่ → ยืนยัน\n3. กด Enter"}})

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "รหัสผ่านใกล้หมดอายุ"},
        },
        "elements": elements,
    }


def send_expiry_card(open_id: str, name: str, days: int, expiry_date: str):
    token = _get_token()
    r = httpx.post(
        f"{config.LARK_DOMAIN}/open-apis/im/v1/messages?receive_id_type=open_id",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"receive_id": open_id, "msg_type": "interactive",
              "content": json.dumps(_card(name, days, expiry_date))},
        timeout=10,
    )
    d = r.json()
    if d.get("code") != 0:
        log.error("ส่งการ์ดเข้า Lark ไม่สำเร็จ: open_id=%s resp=%s", open_id, d)
        raise RuntimeError(f"ส่งข้อความไม่สำเร็จ: {d}")
    log.info("ส่งการ์ดเข้า Lark สำเร็จ: open_id=%s", open_id)
    return True


def upload_key_image(path: str) -> str:
    """อัปโหลดรูปขึ้น Lark แล้วคืนค่า image_key (img_v3_xxx)"""
    token = _get_token()
    with open(path, "rb") as f:
        r = httpx.post(
            f"{config.LARK_DOMAIN}/open-apis/im/v1/images",
            headers={"Authorization": f"Bearer {token}"},
            data={"image_type": "message"},
            files={"image": f},
            timeout=30,
        )
    d = r.json()
    if d.get("code") != 0:
        raise RuntimeError(f"อัปโหลดรูปไม่สำเร็จ: {d}")
    return d["data"]["image_key"]
