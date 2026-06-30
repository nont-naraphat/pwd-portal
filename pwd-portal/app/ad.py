"""เชื่อม Active Directory ผ่าน LDAPS: ตรวจรหัส / อ่านวันหมดอายุ / เปลี่ยนรหัส"""
import ssl
from datetime import datetime, timezone, timedelta

from ldap3 import Server, Connection, Tls, ALL, SUBTREE
from ldap3.core.exceptions import LDAPException

from . import config

import logging
log = logging.getLogger("ad")

EPOCH_AS_FILETIME = 116444736000000000  # 1601->1970 ใน FILETIME (100ns ticks)
NEVER = (0, 9223372036854775807)
BKK = timezone(timedelta(hours=7))  # เวลาไทย


def _tls():
    validate = ssl.CERT_REQUIRED if config.AD_TLS_VALIDATE == "required" else ssl.CERT_NONE
    ca = config.AD_CA_CERT if config.AD_TLS_VALIDATE == "required" else None
    return Tls(validate=validate, ca_certs_file=ca, version=ssl.PROTOCOL_TLS_CLIENT)


def _server():
    return Server(config.AD_HOST, port=config.AD_PORT, use_ssl=config.AD_USE_SSL,
                  tls=_tls(), get_info=ALL)


def _service_conn():
    return Connection(_server(), user=config.AD_BIND_USER,
                      password=config.AD_BIND_PASSWORD, auto_bind=True)


def _filetime_to_dt(ft):
    if ft is None:
        return None
    if isinstance(ft, datetime):
        return ft if ft.tzinfo else ft.replace(tzinfo=timezone.utc)
    try:
        ft = int(ft)
    except (TypeError, ValueError):
        return None
    if ft in NEVER:
        return None
    secs = (ft - EPOCH_AS_FILETIME) / 10_000_000
    return datetime.fromtimestamp(secs, tz=timezone.utc)


def verify_password(username: str, password: str) -> bool:
    """ลอง bind ด้วยรหัสของผู้ใช้เอง"""
    if not password:
        return False
    if "@" in username or "\\" in username:
        upn = username
    else:
        upn = f"{username}@{config.AD_UPN_SUFFIX}"
    try:
        conn = Connection(_server(), user=upn, password=password)
        ok = conn.bind()
        if not ok:
            log.warning("bind ล้มเหลว user=%s result=%s", upn, conn.result)
        else:
            conn.unbind()
        return bool(ok)
    except LDAPException as e:
        log.error("bind error user=%s: %s", upn, e)
        return False


def _find_user(conn, username: str):
    conn.search(config.AD_BASE_DN, f"(sAMAccountName={username})", SUBTREE,
                attributes=["distinguishedName", "displayName", "mail",
                            "department", "title",
                            "msDS-UserPasswordExpiryTimeComputed",
                            "pwdLastSet", "lastLogonTimestamp",
                            "userAccountControl"])
    return conn.entries[0] if conn.entries else None


def get_status(username: str) -> dict:
    """อ่านสถานะรหัสผ่านของผู้ใช้คนหนึ่ง"""
    conn = _service_conn()
    e = _find_user(conn, username)
    conn.unbind()
    if e is None:
        raise LookupError("user not found")
    now = datetime.now(timezone.utc)
    exp = _filetime_to_dt(e["msDS-UserPasswordExpiryTimeComputed"].value)
    changed = _filetime_to_dt(e["pwdLastSet"].value)
    logon = _filetime_to_dt(e["lastLogonTimestamp"].value)
    days = (exp - now).days if exp else None
    age = (now - changed).days if changed else None
    cycle = (exp - changed).days if (exp and changed) else None
    try:
        enabled = not (int(e["userAccountControl"].value) & 0x2)
    except Exception:
        enabled = True
    return {
        "username": username,
        "display_name": str(e["displayName"].value or username),
        "mail": str(e["mail"].value or ""),
        "department": str(e["department"].value or ""),
        "title": str(e["title"].value or ""),
        "expiry": exp.isoformat() if exp else None,
        "expiry_date": exp.strftime("%-d/%-m/%Y") if exp else "ไม่หมดอายุ",
        "days_left": days if days is not None else 9999,
        "changed_date": changed.astimezone(BKK).strftime("%-d/%-m/%Y") if changed else "-",
        "password_age_days": age,
        "cycle_days": cycle,
        "last_logon": logon.astimezone(BKK).strftime("%-d/%-m/%Y %H:%M") if logon else "-",
        "account_enabled": enabled,
    }


def change_password(username: str, current: str, new_password: str):
    """เปลี่ยนรหัสผ่านผ่าน LDAPS (ต้องรู้รหัสเดิม)"""
    if not verify_password(username, current):
        raise PermissionError("รหัสผ่านปัจจุบันไม่ถูกต้อง")
    conn = _service_conn()
    try:
        e = _find_user(conn, username)
        if e is None:
            raise LookupError("user not found")
        dn = str(e["distinguishedName"].value)
        ok = conn.extend.microsoft.modify_password(dn, new_password, current)
        if not ok:
            raise RuntimeError(conn.result.get("description", "เปลี่ยนรหัสไม่สำเร็จ"))
    finally:
        conn.unbind()


def list_expiring(days_set):
    """คืนรายชื่อผู้ใช้ที่วันเหลือตรงกับ days_set (สำหรับงานแจ้งเตือน)"""
    conn = _service_conn()
    out = []
    try:
        conn.search(config.AD_USER_OU,
                    "(&(objectClass=user)(objectCategory=person)(mail=*))",
                    SUBTREE,
                    attributes=["sAMAccountName", "displayName", "mail",
                                "msDS-UserPasswordExpiryTimeComputed"])
        now = datetime.now(timezone.utc)
        for e in conn.entries:
            exp = _filetime_to_dt(e["msDS-UserPasswordExpiryTimeComputed"].value)
            if exp is None:
                continue
            days = (exp - now).days
            if days in days_set:
                out.append({
                    "username": str(e["sAMAccountName"].value),
                    "display_name": str(e["displayName"].value or ""),
                    "mail": str(e["mail"].value or ""),
                    "days_left": days,
                    "expiry_date": exp.strftime("%-d/%-m/%Y"),
                })
    finally:
        conn.unbind()
    return out
