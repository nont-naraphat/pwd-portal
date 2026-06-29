"""ส่งการ์ดแจ้งเตือนเข้า Lark ผ่าน Custom App (tenant_access_token)"""
import json
import time
import logging

import httpx

from . import config

log = logging.getLogger("lark")

# ─────────────────────────────────────────────────────────────────────────────
# ▶ ใส่ img_key ของรูปกล่อง 2 อันตรงนี้ (อัปรูปขึ้น Lark แล้วเอา key มาวาง)
#   วิธีอัป: ใช้ API Explorer บนเว็บ Lark  หรือสั่ง python -m app.lark upload m1 m1.png
# ─────────────────────────────────────────────────────────────────────────────
M1_IMG_KEY = "img_v3_02134_eb54e4ac-2ef3-4981-bd52-1e82e6a883hu"   # รูปกล่องวิธีที่ 1 (m1.png)
M2_IMG_KEY = "img_v3_02134_7c490a60-012a-48bd-a322-b3156a0f6ahu"   # รูปกล่องวิธีที่ 2 (m2.png)
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
# สร้างการ์ด
# ─────────────────────────────────────────────────────────────────────────────
def _intro(name, days, expiry_date):
    return (f"เรียน คุณ{name}\n\n"
            f"รหัสผ่าน **Active Directory** จะหมดอายุใน **{days} วัน** (วันที่ {expiry_date})\n"
            f"รหัสนี้ใช้เข้า 💻 คอมพิวเตอร์ · 📶 WiFi ออฟฟิศ · 🔐 VPN — กรุณาเปลี่ยนก่อนหมดอายุ\n\n"
            f"**เปลี่ยนได้ 2 วิธี เลือกอันที่สะดวก** 👇")


def _card_images(name, days, expiry_date, portal) -> dict:
    """Card 2.0 — กล่องเป็นรูปภาพ (หน้าตาตรงตามดีไซน์เป๊ะ)"""
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "รหัสผ่านใกล้หมดอายุ"},
        },
        "body": {"direction": "vertical", "padding": "12px 12px 12px 12px", "elements": [
            {"tag": "markdown", "content": _intro(name, days, expiry_date)},
            # กล่องวิธีที่ 1 (รูป) + ปุ่มจริง
            {"tag": "img", "img_key": M1_IMG_KEY, "scale_type": "fit_horizontal",
             "alt": {"tag": "plain_text", "content": "วิธีที่ 1: กดลิงก์เปลี่ยนรหัสผ่าน"}},
            {"tag": "button", "type": "primary", "width": "fill", "size": "medium",
             "text": {"tag": "plain_text", "content": "เปลี่ยนรหัสผ่าน"},
             "behaviors": [{"type": "open_url", "default_url": portal}]},
            # กล่องวิธีที่ 2 (รูป)
            {"tag": "img", "img_key": M2_IMG_KEY, "scale_type": "fit_horizontal",
             "alt": {"tag": "plain_text", "content": "วิธีที่ 2: กด Ctrl Alt Delete"}},
        ]},
    }


def _card_text(name, days, expiry_date, portal) -> dict:
    """Fallback — ยังไม่ได้ใส่ img_key จะใช้ข้อความล้วน (การ์ดไม่พัง)"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "รหัสผ่านใกล้หมดอายุ"},
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": _intro(name, days, expiry_date)}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md",
             "content": "**1️⃣ กดลิงก์ เปลี่ยนได้เลย** ⭐ ง่ายสุด\nเปิดหน้าเว็บแล้วตั้งรหัสใหม่ ใช้ได้ทุกที่ทุกเครื่อง"}},
            {"tag": "action", "actions": [
                {"tag": "button", "type": "primary",
                 "text": {"tag": "plain_text", "content": "เปลี่ยนรหัสผ่าน"}, "url": portal}]},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md",
             "content": "**2️⃣ กด Ctrl + Alt + Delete ที่เครื่อง**\n"
                        "📍 ใช้ได้เฉพาะคอมในเครือข่ายออฟฟิศ (LAN, WiFi บริษัท หรือ VPN)\n\n"
                        "**Ctrl + Alt + Delete**\n"
                        "1. กดสามปุ่มพร้อมกัน แล้วเลือก **Change a password**\n"
                        "2. ใส่รหัสเดิม → รหัสใหม่ → ยืนยันรหัสใหม่\n"
                        "3. กด Enter เสร็จเลย ใช้รหัสใหม่กับทุกระบบได้ทันที"}},
        ],
    }


def _card(name: str, days: int, expiry_date: str) -> dict:
    portal = config.PORTAL_URL
    if M1_IMG_KEY and M2_IMG_KEY:
        return _card_images(name, days, expiry_date, portal)
    return _card_text(name, days, expiry_date, portal)


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
    key = d["data"]["image_key"]
    log.info("อัปโหลดรูปสำเร็จ image_key=%s", key)
    return key


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 4 and sys.argv[1] == "upload":
        which, path = sys.argv[2], sys.argv[3]
        k = upload_key_image(path)
        var = {"m1": "M1_IMG_KEY", "m2": "M2_IMG_KEY"}.get(which, "IMG_KEY")
        print(f"\nเอา key นี้ไปวางที่หัวไฟล์ lark.py:\n\n    {var} = \"{k}\"\n")
    else:
        print("วิธีใช้:  python -m app.lark upload <m1|m2> <path ของรูป>")
        print("ตัวอย่าง: python -m app.lark upload m1 m1.png")
        print("         python -m app.lark upload m2 m2.png")
