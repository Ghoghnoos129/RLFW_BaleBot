"""
ارسال پیام/اعلان مدیر به کاربران: متن، عکس، ویدیو، صوت، ویس و فایل — فوری یا زمان‌بندی‌شده.
(مثلاً ارسال دوره‌ای بخش‌هایی از یک کتاب.)
"""
import json
import logging
import time

from app import auth, bale_api, db, jdate, texts
from app.bale_api import edit_or_send, send_long, send_message
from app.keyboards import cancel_kb, confirm_keyboard, inline

log = logging.getLogger("content")

BACK_HOME = [("↩️ پنل مدیریت", "adm:home")]
BACK_BC = [("↩️ پیام‌ها", "adm:bc:home")]
KIND_LABEL = {"text": "متن", "photo": "تصویر", "video": "ویدیو", "audio": "صوت", "voice": "ویس", "document": "فایل"}
MAX_TEXT = 4000


# ============================================================
#  استخراج محتوا از پیام مدیر و ارسال به کاربران
# ============================================================

def extract(message: dict):
    """پیام مدیر را به یک «پیش‌نویس» تبدیل می‌کند: {"kind","text","file_id","caption"}؛ پشتیبانی‌نشده → None."""
    caption = (message.get("caption") or "").strip() or None
    text = (message.get("text") or "").strip()
    if message.get("photo"):
        return {"kind": "photo", "file_id": message["photo"][-1]["file_id"], "caption": caption}
    for kind in ("video", "audio", "voice", "document", "animation"):
        obj = message.get(kind)
        if obj and obj.get("file_id"):
            return {"kind": "document" if kind == "animation" else kind, "file_id": obj["file_id"], "caption": caption}
    if text and not text.startswith("/"):
        return {"kind": "text", "text": text}
    return None


def send_content(chat_id: int, d: dict, reply_markup=None) -> bool:
    """یک پیش‌نویس را برای یک چت می‌فرستد؛ True اگر موفق بود."""
    if d["kind"] == "text":
        return bool(send_long(chat_id, d["text"], reply_markup).get("ok"))
    return bool(bale_api.send_media(chat_id, d["kind"], d["file_id"], d.get("caption")).get("ok"))


def deliver(d: dict, ids=None):
    """پیام را برای همه‌ی کاربران ثبت‌نام‌شده می‌فرستد. (ارسال‌موفق, ناموفق) را برمی‌گرداند."""
    ids = {u["user_id"] for u in db.all_users()} if ids is None else ids
    ok = fail = 0
    for uid in sorted(ids):
        try:
            good = send_content(uid, d)
        except Exception:
            log.warning("content delivery failed for %s", uid)
            good = False
        ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
        time.sleep(0.05)
    return ok, fail


def _describe(d) -> str:
    if d["kind"] == "text":
        body = d["text"]
    else:
        body = d.get("caption") or ""
    body = body.replace("\n", " ")
    return f"{KIND_LABEL[d['kind']]}" + (f" — {body[:40]}…" if len(body) > 40 else (f" — {body}" if body else ""))


def _row_to_draft(r) -> dict:
    return {"kind": r["kind"], "text": r["text"], "file_id": r["file_id"], "caption": r["caption"]}


# ============================================================
#  پنل مدیر
# ============================================================

def home_screen(chat_id, message_id=None):
    sched = db.list_broadcasts("scheduled", 50)
    text = ("📢 پیام به کاربران\n\n"
            "هر محتوایی را (متن، عکس، ویدیو، صوت، ویس یا فایل — با کپشن) برای همه‌ی کاربران ثبت‌نام‌شده بفرستید؛ "
            "همین حالا یا در زمان دلخواه.\n"
            f"🕓 زمان‌بندی‌شده‌های در انتظار: {len(sched)}")
    edit_or_send(chat_id, message_id, text, inline([
        [("➕ پیام جدید", "adm:bc:new")],
        [("🕓 زمان‌بندی‌شده‌ها", "adm:bc:sched"), ("🧾 تاریخچه", "adm:bc:hist")],
        BACK_HOME,
    ]))


def start_new(chat_id, user_id):
    db.set_user_flow(user_id, "admin_bc_wait")
    send_message(
        chat_id,
        "📢 پیام خود را همین‌جا بفرستید:\n"
        "• متن • عکس • ویدیو • صوت • ویس • فایل (عکس/ویدیو/صوت را می‌توانید با کپشن بفرستید)\n\n"
        "هر بار یک پیام؛ برای چند بخش، چند بار این کار را تکرار کنید. بعد از ارسال، پیش‌نمایش و دکمه‌ی تایید می‌بینید.",
        reply_markup=cancel_kb(),
    )


def handle_input(chat_id, user_id, message: dict):
    """پیام مدیر (متن/رسانه) در حالت انتظار؛ پیش‌نویس را می‌سازد و پیش‌نمایش نشان می‌دهد."""
    d = extract(message)
    if not d:
        send_message(chat_id, "این نوع پیام پشتیبانی نمی‌شود. متن، عکس، ویدیو، صوت، ویس یا فایل بفرستید.",
                     reply_markup=cancel_kb())
        return
    body = d.get("text") if d["kind"] == "text" else d.get("caption")
    if body and len(body) > MAX_TEXT:
        send_message(chat_id, f"متن بیش از {MAX_TEXT} حرف است؛ آن را به چند پیام تقسیم کنید.", reply_markup=cancel_kb())
        return
    db.set_user_flow(user_id, "admin_bc_confirm", json.dumps(d))
    n = db.count_users()
    send_message(chat_id, "👁 پیش‌نمایش (کاربران دقیقاً همین را می‌بینند):")
    if not send_content(chat_id, d):
        send_message(chat_id, "❌ نتوانستم این پیام را پیش‌نمایش/ارسال کنم (شاید فایل پشتیبانی نمی‌شود). پیام دیگری بفرستید.",
                     reply_markup=cancel_kb())
        db.set_user_flow(user_id, "admin_bc_wait")
        return
    send_message(
        chat_id, f"این پیام برای {n} کاربر ارسال شود؟\n(برای تغییر، پیام دیگری بفرستید تا جایگزین شود.)",
        inline([[(f"✅ ارسال همین حالا ({n} نفر)", "adm:bc:go")],
                [("🕓 زمان‌بندی ارسال", "adm:bc:sch")],
                [("❌ انصراف", "cancel")]]),
    )


def _flow_draft(user_id, expected=("admin_bc_confirm", "admin_bc_time")):
    flow = db.get_user_flow(user_id)
    if not flow or flow["state"] not in expected:
        return None
    try:
        return json.loads(flow["data"])
    except ValueError:
        return None


def _send_now(chat_id, user_id, d):
    bid = db.add_broadcast(d["kind"], d.get("text"), d.get("file_id"), d.get("caption"), None, "scheduled", user_id)
    db.clear_user_flow(user_id)
    send_message(chat_id, "⏳ در حال ارسال برای کاربران...")
    ok, fail = deliver(d)
    db.finish_broadcast(bid, "sent", ok, fail)
    send_message(chat_id, f"✅ ارسال شد: {ok} نفر" + (f" — ناموفق: {fail}" if fail else ""), inline([BACK_BC, BACK_HOME]))


def handle_flow(chat_id, user_id, state, data, text) -> bool:
    if state == "admin_bc_wait":
        send_message(chat_id, "پیام (متن/تصویر/ویدیو/صوت/فایل) را بفرستید یا انصراف دهید.", reply_markup=cancel_kb())
        return True
    if state == "admin_bc_confirm":
        send_message(chat_id, "برای ارسال از دکمه‌های زیر پیش‌نمایش استفاده کنید، یا پیام جدیدی بفرستید.", reply_markup=cancel_kb())
        return True
    if state == "admin_bc_time":
        iso = jdate.parse_datetime(text)
        d = _flow_draft(user_id, ("admin_bc_time",))
        if not iso or not d:
            send_message(chat_id, "زمان نامعتبر است. مثال: 1405/09/10 18:30", reply_markup=cancel_kb())
            return True
        if iso <= jdate.now_iso():
            send_message(chat_id, "این زمان گذشته است. زمان آینده بفرستید (مثال: 1405/09/10 18:30)", reply_markup=cancel_kb())
            return True
        bid = db.add_broadcast(d["kind"], d.get("text"), d.get("file_id"), d.get("caption"), iso, "scheduled", user_id)
        db.clear_user_flow(user_id)
        send_message(chat_id, f"🕓 پیام #{bid} برای {jdate.fmt_datetime(iso)} زمان‌بندی شد.",
                     inline([[("🕓 زمان‌بندی‌شده‌ها", "adm:bc:sched")], BACK_HOME]))
        return True
    return False


def admin_callback(chat_id, message_id, user_id, parts):
    """parts: بخش‌های بعد از «adm:bc»"""
    action = parts[0] if parts else "home"

    if action == "home":
        home_screen(chat_id, message_id)

    elif action == "new":
        start_new(chat_id, user_id)

    elif action == "go":
        d = _flow_draft(user_id, ("admin_bc_confirm",))
        if not d:
            edit_or_send(chat_id, message_id, "این پیش‌نمایش دیگر معتبر نیست؛ پیام را دوباره بفرستید.", inline([BACK_BC]))
            return
        edit_or_send(chat_id, message_id, "⏳ ارسال شروع شد...", None)
        _send_now(chat_id, user_id, d)

    elif action == "sch":
        d = _flow_draft(user_id, ("admin_bc_confirm",))
        if not d:
            return
        db.set_user_flow(user_id, "admin_bc_time", json.dumps(d))
        send_message(chat_id, "🕓 زمان ارسال را بنویسید (شمسی، وقت تهران):\nمثال: 1405/09/10 18:30",
                     reply_markup=cancel_kb())

    elif action == "sched":
        rows = db.list_broadcasts("scheduled", 20)
        if not rows:
            edit_or_send(chat_id, message_id, "پیام زمان‌بندی‌شده‌ای نیست.", inline([BACK_BC]))
            return
        lines = ["🕓 زمان‌بندی‌شده‌ها", ""]
        kb = []
        for r in rows:
            lines.append(f"#{r['id']} — {jdate.fmt_datetime(r['send_at'])} — {_describe(_row_to_draft(r))}")
            kb.append([(f"👁 #{r['id']}", f"adm:bc:view:{r['id']}"), (f"❌ لغو #{r['id']}", f"adm:bc:cancel:{r['id']}")])
        kb.append(BACK_BC)
        edit_or_send(chat_id, message_id, "\n".join(lines), inline(kb))

    elif action == "view":
        r = db.get_broadcast(int(parts[1])) if len(parts) > 1 and parts[1].isdigit() else None
        if r:
            send_content(chat_id, _row_to_draft(r))

    elif action == "cancel":
        bid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        r = db.get_broadcast(bid)
        if r and r["status"] == "scheduled":
            db.finish_broadcast(bid, "canceled")
        admin_callback(chat_id, message_id, user_id, ["sched"])

    elif action == "hist":
        rows = db.list_broadcasts(None, 10)
        lines = ["🧾 آخرین پیام‌ها", ""]
        for r in rows:
            st = {"sent": "✅ ارسال‌شده", "scheduled": "🕓 در انتظار", "canceled": "🚫 لغو"}.get(r["status"], r["status"])
            extra = f" ({r['sent_count']} موفق، {r['fail_count']} ناموفق)" if r["status"] == "sent" else ""
            when = jdate.fmt_datetime(r["sent_at"] or r["send_at"] or r["created_at"])
            lines.append(f"#{r['id']} {st} — {when} — {_describe(_row_to_draft(r))}{extra}")
        if not rows:
            lines.append("هنوز پیامی ارسال نشده است.")
        edit_or_send(chat_id, message_id, "\n".join(lines), inline([BACK_BC]))


# ============================================================
#  زمان‌بندی (از حلقه‌ی اصلی صدا زده می‌شود)
# ============================================================

def run_due():
    for r in db.due_broadcasts(jdate.now_iso()):
        d = _row_to_draft(r)
        db.finish_broadcast(r["id"], "sent")   # اول علامت می‌خورد تا دوبار ارسال نشود
        ok, fail = deliver(d)
        db.finish_broadcast(r["id"], "sent", ok, fail)
        log.info("scheduled broadcast #%s sent ok=%s fail=%s", r["id"], ok, fail)
        if r["created_by"]:
            try:
                send_message(r["created_by"], f"✅ پیام زمان‌بندی‌شده‌ی #{r['id']} ارسال شد: {ok} نفر" + (f" — ناموفق: {fail}" if fail else ""))
            except Exception:
                pass
