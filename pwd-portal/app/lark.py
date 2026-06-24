"""ส่งการ์ดแจ้งเตือนเข้า Lark ผ่าน Custom App (tenant_access_token)"""
import json
import time

import httpx

from . import config

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
        raise RuntimeError(f"ขอ token ไม่สำเร็จ: {d}")
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
    users = r.json().get("data", {}).get("user_list", [])
    return users[0].get("user_id") if users and users[0].get("user_id") else None


def _card(name: str, days: int, expiry_date: str) -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "รหัสผ่านใกล้หมดอายุ"},
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md",
             "content": f"เรียน คุณ{name}\nรหัสผ่านบัญชี AD ของคุณจะหมดอายุใน **{days} วัน** "
                        f"กรุณาเปลี่ยนก่อนวันหมดอายุเพื่อไม่ให้กระทบการใช้งานและ WiFi"}},
            {"tag": "div", "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**วันหมดอายุ**\n{expiry_date}"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**เหลือเวลา**\n{days} วัน"}},
            ]},
            {"tag": "action", "actions": [
                {"tag": "button", "type": "primary",
                 "text": {"tag": "plain_text", "content": "เปลี่ยนรหัสผ่าน"},
                 "url": config.PORTAL_URL},
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
        raise RuntimeError(f"ส่งข้อความไม่สำเร็จ: {d}")
    return True
