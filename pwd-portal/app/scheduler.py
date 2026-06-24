"""งานตั้งเวลา: สแกน AD รายวัน หาคนใกล้หมดอายุ แล้วยิงการ์ด Lark"""
import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler

from . import config, ad, lark

log = logging.getLogger("scheduler")


def scan_and_notify():
    if not config.AD_ENABLED:
        log.warning("ข้าม: ยังไม่ได้ตั้งค่า AD")
        return {"sent": 0, "skipped": "no-ad"}
    sent = 0
    try:
        users = ad.list_expiring(set(config.NOTIFY_DAYS))
    except Exception as e:  # noqa
        log.error("สแกน AD ล้มเหลว: %s", e)
        return {"error": str(e)}
    for u in users:
        try:
            if not config.LARK_ENABLED:
                continue
            oid = lark.open_id_by_email(u["mail"])
            if not oid:
                log.info("ไม่พบ Lark user สำหรับ %s", u["mail"])
                continue
            lark.send_expiry_card(oid, u["display_name"], u["days_left"], u["expiry_date"])
            sent += 1
            time.sleep(0.25)  # กัน rate limit (~5/วินาที)
        except Exception as e:  # noqa
            log.error("แจ้งเตือน %s ล้มเหลว: %s", u.get("username"), e)
    log.info("แจ้งเตือนสำเร็จ %d ราย", sent)
    return {"candidates": len(users), "sent": sent}


def start():
    sch = BackgroundScheduler(timezone="Asia/Bangkok")
    sch.add_job(scan_and_notify, "cron", hour=config.NOTIFY_HOUR, minute=0, id="daily_notify")
    sch.start()
    log.info("ตั้งเวลาแจ้งเตือนทุกวันเวลา %02d:00 น.", config.NOTIFY_HOUR)
    return sch
