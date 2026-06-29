"""ส่งการ์ดแจ้งเตือนเข้า Lark ผ่าน Custom App (tenant_access_token)"""
import json
import time
import logging

import httpx

from . import config

log = logging.getLogger("lark")

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


def _card(name: str, days: int, expiry_date: str) -> dict:
    portal = config.PORTAL_URL
    guide = config.PORTAL_URL.rstrip("/") + "/#change-win"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "รหัสผ่านใกล้หมดอายุ"},
        },
        "elements": [
            # หัวข้อ + สรุปวันหมดอายุ
            {"tag": "div", "text": {"tag": "lark_md",
             "content": f"เรียน คุณ{name}\n\n"
                        f"รหัสผ่าน **Active Directory** จะหมดอายุใน **{days} วัน** (วันที่ {expiry_date})\n"
                        f"รหัสนี้ใช้เข้า 💻 คอมพิวเตอร์ · 📶 WiFi ออฟฟิศ · 🔐 VPN — กรุณาเปลี่ยนก่อนหมดอายุ\n\n"
                        f"**เปลี่ยนได้ 2 วิธี เลือกอันที่สะดวก** 👇"}},
            {"tag": "hr"},
            # วิธีที่ 1 — กดลิงก์เปลี่ยนเลย
            {"tag": "div", "text": {"tag": "lark_md",
             "content": "**1️⃣  กดลิงก์ เปลี่ยนได้เลย**  ⭐ ง่ายสุด\n"
                        "กดปุ่มข้างล่าง เปิดหน้าเว็บแล้วตั้งรหัสใหม่ในนั้น — "
                        "ใช้ได้ทุกที่ ทุกเครื่อง แม้อยู่นอกออฟฟิศ"}},
            {"tag": "action", "actions": [
                {"tag": "button", "type": "primary",
                 "text": {"tag": "plain_text", "content": "เปลี่ยนรหัสผ่าน"},
                 "url": portal},
            ]},
            {"tag": "hr"},
            # วิธีที่ 2 — Ctrl+Alt+Delete ที่เครื่อง
            {"tag": "div", "text": {"tag": "lark_md",
             "content": "**2️⃣  กด Ctrl + Alt + Delete ที่เครื่อง**\n"
                        "📍 ใช้ได้เฉพาะตอนนั่งหน้าคอมที่อยู่ใน **เครือข่ายออฟฟิศ** "
                        "(LAN, WiFi บริษัท หรือเปิด VPN)\n\n"
                        "`[ Ctrl ]` + `[ Alt ]` + `[ Delete ]`\n\n"
                        "1. กดสามปุ่มพร้อมกัน แล้วเลือก **Change a password**\n"
                        "2. ใส่รหัสเดิม → รหัสใหม่ → ยืนยันรหัสใหม่\n"
                        "3. กด Enter เสร็จเลย ใช้รหัสใหม่กับทุกระบบได้ทันที"}},
            {"tag": "action", "actions": [
                {"tag": "button", "type": "default",
                 "text": {"tag": "plain_text", "content": "ดูวิธีแบบมีรูป"},
                 "url": guide},
            ]},
        ],
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
