#!/usr/bin/env python3
"""
نقطه ورود اصلی ربات. اجرا با: python run.py
ربات به صورت long-polling با Bot API بله ارتباط می‌گیرد، نیازی به دامنه یا SSL ندارد.
"""
import logging
import os
import time

from app import db
from app.bale_api import get_updates, get_me
from app.config import LOG_PATH, HEARTBEAT_PATH
from app.handlers import handle_message, handle_callback_query

os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("run")

OFFSET_KEY = "update_offset"


def _write_heartbeat():
    """هر دور از حلقه‌ی اصلی این فایل را به‌روز می‌کند تا healthcheck داکر بفهمد ربات زنده است."""
    try:
        os.makedirs(os.path.dirname(HEARTBEAT_PATH) or ".", exist_ok=True)
        with open(HEARTBEAT_PATH, "w") as f:
            f.write(str(time.time()))
    except OSError:
        log.warning("نتوانستم فایل heartbeat را بنویسم: %s", HEARTBEAT_PATH)


def process_update(update: dict):
    try:
        if "message" in update:
            handle_message(update["message"])
        elif "callback_query" in update:
            handle_callback_query(update["callback_query"])
    except Exception:
        log.exception("error while processing update: %s", update)


def main():
    db.init_db()

    me = get_me()
    if me.get("ok"):
        bot_info = me.get("result", {})
        log.info("ربات با موفقیت متصل شد: %s", bot_info.get("username") or bot_info.get("id"))
    else:
        log.error("اتصال به بله ناموفق بود، توکن را بررسی کنید: %s", me)

    offset = db.get_state(OFFSET_KEY)
    offset = int(offset) if offset else None

    log.info("ربات لیگ کتابخوانی اجرا شد و منتظر پیام‌هاست...")

    backoff = 1
    while True:
        try:
            _write_heartbeat()
            result = get_updates(offset=offset)
            if not result.get("ok"):
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
            backoff = 1

            updates = result.get("result", [])
            for update in updates:
                process_update(update)
                offset = update["update_id"] + 1
                db.set_state(OFFSET_KEY, str(offset))

        except KeyboardInterrupt:
            log.info("ربات متوقف شد.")
            break
        except Exception:
            log.exception("خطای غیرمنتظره در حلقه اصلی، ۵ ثانیه بعد تلاش مجدد می‌شود")
            time.sleep(5)


if __name__ == "__main__":
    main()
