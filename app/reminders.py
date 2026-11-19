"""
یادآور مطالعه‌ی روزانه: کاربر ساعت دلخواهش را انتخاب می‌کند و هر روز همان ساعت (به وقت تهران)
یک پیام یادآوری می‌گیرد؛ می‌تواند هر زمان تغییر دهد یا خاموش کند.
"""
import logging
import time

from app import db, jdate
from app.bale_api import edit_or_send, send_message
from app.keyboards import cancel_kb, inline

log = logging.getLogger("reminders")

LATE_LIMIT_MINUTES = 180   # اگر ربات خاموش بود، یادآور بیش از ۳ ساعت دیرتر فرستاده نمی‌شود
MESSAGES = [
    "⏰ وقت مطالعه‌ی امروزتان است! چند دقیقه کتاب بخوانید و ثبتش کنید 📖",
    "📚 یادآوری: امروز هم کمی مطالعه، یک امتیاز دیگر در لیگ 🌱",
    "⏰ سلام! ساعت مطالعه‌ی شما رسید. یک فنجان چای و یک کتاب خوب ☕📖",
    "📖 مطالعه‌ی منظم، کلید برد در لیگ است. امروز چقدر خواندید؟",
    "⏰ هنوز فرصت دارید امروز را با مطالعه بسازید. موفق باشید 🌟",
]


def _status_text(r) -> str:
    if r and r["enabled"]:
        return (f"⏰ یادآور مطالعه: روشن ✅\nهر روز ساعت {r['remind_time']} (به وقت تهران) برایتان پیام یادآوری می‌فرستم.")
    return "⏰ یادآور مطالعه: خاموش\nاگر می‌خواهید مطالعه‌ی روزانه‌ی منظم داشته باشید، یادآور را فعال کنید و ساعت دلخواهتان را بدهید."


def show(chat_id, user_id, message_id=None):
    r = db.get_reminder(user_id)
    if r and r["enabled"]:
        kb = [[("🕒 تغییر ساعت", "rem:on"), ("🔕 خاموش کردن", "rem:off")]]
    else:
        kb = [[("🔔 فعال‌سازی یادآور", "rem:on")]]
    edit_or_send(chat_id, message_id, _status_text(r), inline(kb))


def _hours_grid():
    rows, row = [], []
    for h in range(5, 24):
        row.append((f"{h:02d}:00", f"rem:t:{h:02d}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([("⌨️ ساعت دلخواه (مثلاً 20:45)", "rem:custom")])
    rows.append([("❌ انصراف", "cancel")])
    return inline(rows)


def handle_callback(cb: dict):
    """callback های «rem:...» — فراخوان قبلاً answer_callback_query زده است."""
    data = cb.get("data", "")
    user_id = cb.get("from", {}).get("id")
    msg = cb.get("message", {})
    chat_id, message_id = msg.get("chat", {}).get("id"), msg.get("message_id")
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "on":
        edit_or_send(chat_id, message_id, "🕒 هر روز چه ساعتی (به وقت تهران) یادآوری کنم؟", _hours_grid())

    elif action == "t" and len(parts) > 2:
        t = jdate.parse_hhmm(parts[2])
        if not t:
            return
        db.set_reminder(user_id, t, True)
        edit_or_send(chat_id, message_id, f"✅ یادآور فعال شد: هر روز ساعت {t}.\nهر وقت خواستید از «⏰ یادآور مطالعه» تغییرش دهید.")

    elif action == "custom":
        db.set_user_flow(user_id, "edit_reminder")
        send_message(chat_id, "ساعت یادآوری را بنویسید؛ مثال: 20:45 یا ۷:۳۰", reply_markup=cancel_kb())

    elif action == "off":
        db.disable_reminder(user_id)
        edit_or_send(chat_id, message_id, "🔕 یادآور خاموش شد. هر وقت خواستید دوباره فعالش کنید.")


def handle_time_text(chat_id, user_id, text) -> bool:
    """پاسخ متنی کاربر برای ساعت دلخواه. True اگر کار تمام شد."""
    t = jdate.parse_hhmm(text)
    if not t:
        send_message(chat_id, "ساعت نامعتبر است. مثال: 20:45", reply_markup=cancel_kb())
        return False
    db.set_reminder(user_id, t, True)
    db.clear_user_flow(user_id)
    send_message(chat_id, f"✅ یادآور فعال شد: هر روز ساعت {t}.")
    return True


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def run_due():
    """از حلقه‌ی اصلی صدا زده می‌شود؛ یادآورهای رسیده را می‌فرستد (فقط وقتی فصل فعال هست)."""
    now = jdate.now_tehran()
    today, hhmm = now.date().isoformat(), now.strftime("%H:%M")
    rows = db.due_reminders(today, hhmm)
    if not rows:
        return
    season = db.get_active_season()
    text = MESSAGES[now.timetuple().tm_yday % len(MESSAGES)]
    kb = inline([[("📖 ثبت مطالعه‌ی امروز", "rem:log")]])
    for r in rows:
        db.mark_reminder_sent(r["user_id"], today)   # اول علامت می‌خورد تا دوبار نرود
        if not season or _to_minutes(hhmm) - _to_minutes(r["remind_time"]) > LATE_LIMIT_MINUTES:
            continue
        try:
            send_message(r["user_id"], text, reply_markup=kb)
        except Exception:
            log.warning("reminder failed for %s", r["user_id"])
        time.sleep(0.05)
