"""ส่งการ์ดแจ้งเตือนเข้า Lark ผ่าน Custom App (tenant_access_token)"""
import json
import time
import logging

import httpx

from . import config

log = logging.getLogger("lark")

# ─────────────────────────────────────────────────────────────────────────────
# ▶ ตั้งค่า 3 จุดนี้ (แก้แค่ตรงนี้พอ)
# ─────────────────────────────────────────────────────────────────────────────
# 1) รูปแบบการ์ด:
#    True  = การ์ดแบบกล่องสวย (Card JSON 2.0) — หน้าตาตรงตาม preview
#    False = การ์ดแบบเรียบ (เส้นคั่น) — การันตีว่ารันได้ทุกเวอร์ชัน Lark
#    ▶ ถ้าตั้ง True แล้วส่งแล้วการ์ดขึ้น error ให้เปลี่ยนเป็น False
USE_BOXES = True

# 2) img_key รูปปุ่ม Ctrl+Alt+Delete  (ได้จาก: python -m app.lark upload keys keys.png)
KEYS_IMG_KEY = ""

# 3) img_key รูปหน้าจอ Windows         (ได้จาก: python -m app.lark upload win win_change.png)
WIN_IMG_KEY = ""
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
_INTRO = ("เรียน คุณ{name}\n\n"
          "รหัสผ่าน **Active Directory** จะหมดอายุใน **{days} วัน** (วันที่ {date})\n"
          "รหัสนี้ใช้เข้า 💻 คอมพิวเตอร์ · 📶 WiFi ออฟฟิศ · 🔐 VPN — กรุณาเปลี่ยนก่อนหมดอายุ\n\n"
          "**เปลี่ยนได้ 2 วิธี เลือกอันที่สะดวก** 👇")

_M1_TITLE = "**1️⃣  กดลิงก์ เปลี่ยนได้เลย**　⭐ ง่ายสุด"
_M1_DESC = "กดปุ่มข้างล่าง เปิดหน้าเว็บแล้วตั้งรหัสใหม่ในนั้น — ใช้ได้ทุกที่ ทุกเครื่อง แม้อยู่นอกออฟฟิศ"

_M2_TITLE = "**2️⃣  กด Ctrl + Alt + Delete ที่เครื่อง**"
_M2_NOTE = "📍 ใช้ได้เฉพาะตอนนั่งหน้าคอมที่อยู่ใน **เครือข่ายออฟฟิศ** (LAN, WiFi บริษัท หรือเปิด VPN)"
_M2_STEPS = ("1. กดสามปุ่มพร้อมกัน แล้วเลือก **Change a password**\n"
             "2. ใส่รหัสเดิม → รหัสใหม่ → ยืนยันรหัสใหม่\n"
             "3. กด Enter เสร็จเลย ใช้รหัสใหม่กับทุกระบบได้ทันที")
_M2_SCREEN_CAP = "หน้าจอที่จะเจอหลังเลือก *Change a password*:"


def _img(img_key: str, alt: str) -> dict:
    return {"tag": "img", "img_key": img_key,
            "alt": {"tag": "plain_text", "content": alt}}


def _card_boxes(name, days, expiry_date, portal, guide) -> dict:
    """Card JSON 2.0 — แบบกล่องสวย"""
    m2 = [
        {"tag": "markdown", "content": _M2_TITLE},
        {"tag": "markdown", "content": _M2_NOTE},
    ]
    if KEYS_IMG_KEY:
        m2.append(_img(KEYS_IMG_KEY, "Ctrl + Alt + Delete"))
    else:
        m2.append({"tag": "markdown", "content": "**Ctrl + Alt + Delete**"})
    m2.append({"tag": "markdown", "content": _M2_STEPS})
    if WIN_IMG_KEY:
        m2.append({"tag": "markdown", "content": _M2_SCREEN_CAP})
        m2.append(_img(WIN_IMG_KEY, "หน้าจอเปลี่ยนรหัสผ่านของ Windows"))
    m2.append({"tag": "button", "type": "default", "width": "default",
               "text": {"tag": "plain_text", "content": "เปิดคู่มือบนเว็บ"},
               "behaviors": [{"type": "open_url", "default_url": guide}]})

    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "รหัสผ่านใกล้หมดอายุ"},
        },
        "body": {"elements": [
            {"tag": "markdown", "content": _INTRO.format(name=name, days=days, date=expiry_date)},
            # กล่องวิธีที่ 1 (ขอบน้ำเงิน)
            {"tag": "interactive_container",
             "corner_radius": "10px",
             "padding": "12px 14px 12px 14px",
             "border": {"color": "blue", "corner_radius": "10px"},
             "elements": [
                {"tag": "markdown", "content": _M1_TITLE},
                {"tag": "markdown", "content": _M1_DESC},
                {"tag": "button", "type": "primary", "width": "fill",
                 "text": {"tag": "plain_text", "content": "เปลี่ยนรหัสผ่าน"},
                 "behaviors": [{"type": "open_url", "default_url": portal}]},
             ]},
            # กล่องวิธีที่ 2 (พื้นเทา)
            {"tag": "interactive_container",
             "corner_radius": "10px",
             "padding": "12px 14px 12px 14px",
             "background_style": "grey",
             "elements": m2},
        ]},
    }


def _card_simple(name, days, expiry_date, portal, guide) -> dict:
    """Card JSON 1.0 — แบบเรียบ เส้นคั่น (การันตีรันได้ทุกเวอร์ชัน)"""
    elements = [
        {"tag": "div", "text": {"tag": "lark_md",
         "content": _INTRO.format(name=name, days=days, date=expiry_date)}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": _M1_TITLE + "\n" + _M1_DESC}},
        {"tag": "action", "actions": [
            {"tag": "button", "type": "primary",
             "text": {"tag": "plain_text", "content": "เปลี่ยนรหัสผ่าน"},
             "url": portal}]},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": _M2_TITLE + "\n" + _M2_NOTE}},
    ]
    if KEYS_IMG_KEY:
        elements.append(_img(KEYS_IMG_KEY, "Ctrl + Alt + Delete"))
    else:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**Ctrl + Alt + Delete**"}})
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": _M2_STEPS}})
    if WIN_IMG_KEY:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": _M2_SCREEN_CAP}})
        elements.append(_img(WIN_IMG_KEY, "หน้าจอเปลี่ยนรหัสผ่านของ Windows"))
    elements.append({"tag": "action", "actions": [
        {"tag": "button", "type": "default",
         "text": {"tag": "plain_text", "content": "เปิดคู่มือบนเว็บ"},
         "url": guide}]})

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "รหัสผ่านใกล้หมดอายุ"},
        },
        "elements": elements,
    }


def _card(name: str, days: int, expiry_date: str) -> dict:
    portal = config.PORTAL_URL
    guide = config.PORTAL_URL.rstrip("/") + "/#change-win"
    if USE_BOXES:
        return _card_boxes(name, days, expiry_date, portal, guide)
    return _card_simple(name, days, expiry_date, portal, guide)


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
        var = {"keys": "KEYS_IMG_KEY", "win": "WIN_IMG_KEY"}.get(which, "IMG_KEY")
        print(f"\nเอา key นี้ไปวางที่หัวไฟล์ lark.py:\n\n    {var} = \"{k}\"\n")
    else:
        print("วิธีใช้:  python -m app.lark upload <keys|win> <path ของรูป>")
        print("ตัวอย่าง: python -m app.lark upload keys keys.png")
        print("         python -m app.lark upload win win_change.png")
