"""
منطق اصلی پردازش پیام‌ها و callback های کاربران عادی.
(بخش مدیریت در admin.py و منطق لیگ در league.py است.)
"""
import hmac
import logging
import time

from app import admin, auth, db, jdate, keyboards, league, texts, utils
from app.bale_api import answer_callback_query, edit_message_text, edit_or_send, send_long, send_message
from app.config import ADMIN_IDS, ADMIN_SETUP_CODE, MAX_MINUTES_PER_ENTRY
from app.keyboards import inline

log = logging.getLogger("handlers")

# مرحله‌های ثبت‌نام (قابل رد‌شدن با دکمه‌های منو نیستند؛ فقط با /start یا «انصراف» تمام می‌شوند)
REG_STATES = {"await_password", "await_name", "await_spouse", "await_children", "await_card"}
CANCEL_WORDS = {"انصراف", "❌ انصراف", "/cancel", "/لغو"}
MAX_PASSWORD_TRIES = 5
BLOCK_SECONDS = 600


def _menu(user_id):
    return keyboards.main_menu(auth.is_admin(user_id))


# ============================================================
#  ثبت‌نام و تکمیل مشخصات
# ============================================================

def _next_missing(u):
    """اولین مرحله‌ای از ثبت‌نام که برای این کاربر خالی مانده (برای کاربران نسخه ۰.۱ هم کار می‌کند)."""
    if not u["full_name"]:
        return "await_name"
    if not u["spouse_name"]:
        return "await_spouse"
    if u["has_children"] is None:
        return "await_children"
    if not u["card_number"]:
        return "await_card"
    return None


def _begin_state(chat_id, user_id, state, note=""):
    db.set_user_flow(user_id, state)
    if state == "await_password":
        send_message(chat_id, texts.WELCOME + "\n\n" + texts.ASK_PASSWORD)
    elif state == "await_name":
        send_message(chat_id, note + texts.ASK_NAME)
    elif state == "await_spouse":
        send_message(chat_id, note + texts.ASK_SPOUSE)
    elif state == "await_children":
        send_message(chat_id, note + texts.ASK_CHILDREN, reply_markup=keyboards.yes_no_children())
    elif state == "await_card":
        send_message(chat_id, note + texts.ASK_CARD)


def _advance_registration(chat_id, user_id):
    """بعد از هر مرحله: مرحله‌ی بعدیِ خالی را می‌پرسد، یا ثبت‌نام را تمام می‌کند."""
    u = db.get_user(user_id)
    nxt = _next_missing(u) if u else "await_name"
    if nxt:
        _begin_state(chat_id, user_id, nxt)
        return
    db.clear_user_flow(user_id)
    send_message(chat_id, texts.REGISTER_DONE, reply_markup=_menu(user_id))


def _pw_blocked(user_id) -> bool:
    until = db.get_state(f"pwblock:{user_id}")
    try:
        return bool(until) and float(until) > time.time()
    except ValueError:
        return False


def _handle_registration(chat_id, user_id, state, data, text, username):
    if state == "await_password":
        if _pw_blocked(user_id):
            send_message(chat_id, texts.TOO_MANY_ATTEMPTS)
            return
        password = db.get_registration_password()
        if not password:
            db.clear_user_flow(user_id)
            send_message(chat_id, texts.REGISTRATION_CLOSED)
            return
        given = utils.normalize_digits(text).strip().encode()
        wanted = utils.normalize_digits(password).strip().encode()
        if hmac.compare_digest(given, wanted):
            _begin_state(chat_id, user_id, "await_name")
            return
        fails = int(data or 0) + 1
        if fails >= MAX_PASSWORD_TRIES:
            db.set_state(f"pwblock:{user_id}", str(time.time() + BLOCK_SECONDS))
            db.clear_user_flow(user_id)
            send_message(chat_id, texts.TOO_MANY_ATTEMPTS)
        else:
            db.set_user_flow(user_id, "await_password", str(fails))
            send_message(chat_id, texts.WRONG_PASSWORD.format(left=MAX_PASSWORD_TRIES - fails))
        return

    if state in ("await_name", "await_spouse"):
        if not text or text.startswith("/") or len(text) > 80:
            send_message(chat_id, texts.INVALID_TEXT)
            return
        if state == "await_name":
            db.upsert_user(user_id, full_name=text, username=username)
        else:
            db.update_user(user_id, spouse_name=text)
        _advance_registration(chat_id, user_id)
        return

    if state == "await_children":
        send_message(chat_id, texts.USE_BUTTONS, reply_markup=keyboards.yes_no_children())
        return

    if state == "await_card":
        card = utils.parse_card(text)
        if not card:
            send_message(chat_id, texts.INVALID_CARD)
            return
        db.update_user(user_id, card_number=card)
        _advance_registration(chat_id, user_id)
        return


# ============================================================
#  اصلاح مطالعه و کتاب‌ها
# ============================================================

def _logs_menu(chat_id, user_id, season, message_id=None):
    logs = db.recent_logs(user_id, season["id"], 8)
    books = db.completed_books(user_id, season["id"])
    if not logs and not books:
        edit_or_send(chat_id, message_id, texts.NOTHING_TO_EDIT)
        return
    rows = [[(f"⏱ {l['minutes']} دقیقه — {jdate.fmt_datetime(l['created_at'])}", f"log:{l['id']}")] for l in logs]
    if books:
        rows.append([("📚 کتاب‌های ثبت‌شده‌ی من", "bk:list")])
    text = (f"✏️ اصلاح مطالعه — {season['name']}\n\n"
            "آخرین ثبت‌های شما را می‌بینید. روی هر مورد بزنید تا عدد آن را اصلاح یا حذف کنید.")
    edit_or_send(chat_id, message_id, text, inline(rows))


def _books_undo_menu(chat_id, user_id, season, message_id=None):
    books = db.completed_books(user_id, season["id"])
    if not books:
        edit_or_send(chat_id, message_id, "هنوز کتابی ثبت نکرده‌اید.", inline([[("↩️ بازگشت", "logs:list")]]))
        return
    rows = [[(f"↩️ لغو اتمام: {b['title']}", f"bkdel:{b['id']}")] for b in books]
    rows.append([("↩️ بازگشت", "logs:list")])
    edit_or_send(chat_id, message_id, "📚 کتاب‌هایی که اتمامشان را ثبت کرده‌اید.\nاگر اشتباهی ثبت شده، لغوش کنید:", inline(rows))


def _show_profile(chat_id, user_id):
    u = db.get_user(user_id)
    send_message(chat_id, texts.profile_text(u), reply_markup=inline([
        [("✏️ نام", "prof:name"), ("✏️ نام همسر", "prof:spouse")],
        [("✏️ شماره کارت", "prof:card"), ("👶 وضعیت فرزند", "prof:child")],
    ]))


# ============================================================
#  هندل پیام‌های متنی
# ============================================================

def handle_message(message: dict):
    chat_id = message.get("chat", {}).get("id")
    from_user = message.get("from", {})
    user_id = from_user.get("id")
    text = (message.get("text") or "").strip()

    if user_id is None or chat_id is None:
        return
    username = from_user.get("username")

    # ---------- گرفتن آیدی عددی (اطلاعاتی) — همیشه کار می‌کند، حتی قبل از ثبت‌نام ----------
    if text in ("/id", "/آیدی", "/شناسه", "آیدی من", "شناسه من"):
        log.info("درخواست آیدی: user_id=%s name=%s", user_id, auth.user_display_name(from_user))
        send_message(chat_id, f"آیدی عددی شما: {user_id}")
        return

    # ---------- ثبت ادمین با کد مخفی (ADMIN_SETUP_CODE در .env) ----------
    if ADMIN_SETUP_CODE and text == ADMIN_SETUP_CODE:
        if auth.is_admin(user_id):
            send_message(chat_id, "شما از قبل ادمین هستید.", reply_markup=keyboards.main_menu(True))
            return
        becomes_super = db.admins_count() == 0 and not ADMIN_IDS
        db.add_admin(user_id, full_name=auth.user_display_name(from_user), is_super=becomes_super)
        log.info("ادمین جدید اضافه شد: user_id=%s super=%s", user_id, becomes_super)
        if becomes_super:
            send_message(
                chat_id,
                "✅ شما به عنوان «مدیر اصلی» ربات ثبت شدید.\n"
                "برای امنیت بیشتر، الان بهتر است مقدار ADMIN_SETUP_CODE را در فایل .env "
                "عوض یا حذف کنید تا دیگران نتوانند با همین کد خودشان را ادمین کنند.\n\n"
                "از دکمه «⚙️ پنل مدیریت» همه‌ی تنظیمات را می‌توانید انجام دهید.",
                reply_markup=keyboards.main_menu(True),
            )
        else:
            send_message(chat_id, "✅ شما به عنوان ادمین ربات ثبت شدید.\nاز دکمه «⚙️ پنل مدیریت» استفاده کنید.",
                         reply_markup=keyboards.main_menu(True))
        return

    # ذخیره‌ی بی‌سروصدای آیدی (username) بله، برای هماهنگی مدیر با برندگان
    db.touch_username(user_id, username)

    is_admin = auth.is_admin(user_id)
    flow = db.get_user_flow(user_id)
    state = flow["state"] if flow else None
    flow_data = flow["data"] if flow else ""

    # ---------- انصراف ----------
    if text in CANCEL_WORDS:
        db.clear_user_flow(user_id)
        if state in REG_STATES:
            send_message(chat_id, "ثبت‌نام متوقف شد. هر وقت خواستید دوباره /start را بزنید.")
        else:
            send_message(chat_id, texts.CANCELED, reply_markup=_menu(user_id))
        return

    # ---------- اگر کاربر وسط یک کار، دکمه‌ی منو یا دستور زد، کار نیمه‌تمام لغو و دستور جدید اجرا می‌شود ----------
    if state and state not in REG_STATES and (text.startswith("/") or text in keyboards.ALL_BUTTONS):
        db.clear_user_flow(user_id)
        state, flow_data = None, ""

    # ---------- مدیر ----------
    if is_admin:
        if text == keyboards.BTN_ADMIN:
            admin.show_panel(chat_id)
            return
        if text.startswith("/") and admin.handle_command(chat_id, user_id, text):
            return
        if state and state.startswith("admin_"):
            if admin.handle_flow(chat_id, user_id, state, flow_data, text):
                return
    elif state and state.startswith("admin_"):
        db.clear_user_flow(user_id)
        state = None

    # ---------- /start و ثبت‌نام ----------
    if text == "/start":
        db.clear_user_flow(user_id)
        existing = db.get_user(user_id)
        if existing and existing["has_children"] is not None:      # قبلاً عضو شده
            nxt = _next_missing(existing)
            if nxt:
                _begin_state(chat_id, user_id, nxt, note=texts.PROFILE_INCOMPLETE_NOTE)
            else:
                send_message(chat_id, texts.ALREADY_REGISTERED, reply_markup=_menu(user_id))
            return
        if is_admin:                                                # مدیر برای ثبت‌نام رمز لازم ندارد
            _begin_state(chat_id, user_id, "await_name")
            return
        if not db.get_registration_password():
            send_message(chat_id, texts.REGISTRATION_CLOSED)
            return
        if _pw_blocked(user_id):
            send_message(chat_id, texts.TOO_MANY_ATTEMPTS)
            return
        _begin_state(chat_id, user_id, "await_password")
        return

    if state in REG_STATES:
        _handle_registration(chat_id, user_id, state, flow_data, text, username)
        return

    user_row = db.get_user(user_id)
    if not user_row or user_row["has_children"] is None:
        send_message(chat_id, texts.NOT_REGISTERED)
        return

    # کاربران نسخه ۰.۱: نام همسر و شماره کارت را باید یک‌بار تکمیل کنند
    missing = _next_missing(user_row)
    if missing:
        _begin_state(chat_id, user_id, missing, note=texts.PROFILE_INCOMPLETE_NOTE)
        return

    # ---------- مرحله‌های در جریان (پاسخ به سؤال ربات) ----------
    if state == "await_minutes":
        season = db.get_active_season()
        if not season:
            db.clear_user_flow(user_id)
            send_message(chat_id, texts.no_active_text(db.get_upcoming_season()))
            return
        minutes = utils.parse_int(text)
        if minutes is None or minutes <= 0:
            send_message(chat_id, texts.INVALID_MINUTES)
            return
        if minutes > MAX_MINUTES_PER_ENTRY:
            send_message(chat_id, texts.TOO_MANY_MINUTES.format(max=MAX_MINUTES_PER_ENTRY))
            return
        log_id = db.add_reading_log(user_id, season["id"], minutes)
        db.clear_user_flow(user_id)
        send_message(
            chat_id, texts.MINUTES_SAVED.format(minutes=minutes),
            reply_markup=inline([[("✏️ اصلاح یا حذف این ثبت", f"log:{log_id}")]]),
        )
        books = db.list_books(season["id"])
        done_ids = {b["id"] for b in db.completed_books(user_id, season["id"])}
        remaining = [b for b in books if b["id"] not in done_ids]
        if remaining:
            send_message(chat_id, texts.ASK_BOOK_DONE, reply_markup=keyboards.book_choice_keyboard(remaining))
        league.check_prize_increase(season["id"])
        return

    if state == "edit_minutes":
        log_row = db.get_log(int(flow_data)) if flow_data.isdigit() else None
        season = db.get_active_season()
        if not log_row or not season or log_row["user_id"] != user_id or log_row["season_id"] != season["id"]:
            db.clear_user_flow(user_id)
            send_message(chat_id, "این ثبت دیگر قابل اصلاح نیست.", reply_markup=_menu(user_id))
            return
        minutes = utils.parse_int(text)
        if minutes is None or minutes <= 0:
            send_message(chat_id, texts.INVALID_MINUTES)
            return
        if minutes > MAX_MINUTES_PER_ENTRY:
            send_message(chat_id, texts.TOO_MANY_MINUTES.format(max=MAX_MINUTES_PER_ENTRY))
            return
        db.update_log_minutes(log_row["id"], minutes)
        db.clear_user_flow(user_id)
        send_message(chat_id, texts.MINUTES_EDITED.format(old=log_row["minutes"], new=minutes), reply_markup=_menu(user_id))
        league.check_prize_increase(season["id"])
        return

    if state in ("edit_name", "edit_spouse"):
        if not text or len(text) > 80:
            send_message(chat_id, texts.INVALID_TEXT)
            return
        db.update_user(user_id, **{"full_name" if state == "edit_name" else "spouse_name": text})
        db.clear_user_flow(user_id)
        send_message(chat_id, "✅ ذخیره شد.", reply_markup=_menu(user_id))
        _show_profile(chat_id, user_id)
        return

    if state == "edit_card":
        card = utils.parse_card(text)
        if not card:
            send_message(chat_id, texts.INVALID_CARD)
            return
        db.update_user(user_id, card_number=card)
        db.clear_user_flow(user_id)
        send_message(chat_id, "✅ شماره کارت ذخیره شد.", reply_markup=_menu(user_id))
        _show_profile(chat_id, user_id)
        return

    # ---------- منوی اصلی ----------
    if text == keyboards.BTN_LOG:
        season = db.get_active_season()
        if not season:
            send_message(chat_id, texts.no_active_text(db.get_upcoming_season()), reply_markup=_menu(user_id))
            return
        db.set_user_flow(user_id, "await_minutes")
        send_message(chat_id, texts.ASK_MINUTES, reply_markup=_menu(user_id))
        return

    if text == keyboards.BTN_EDIT:
        season = db.get_active_season()
        if not season:
            send_message(chat_id, texts.no_active_text(db.get_upcoming_season()), reply_markup=_menu(user_id))
            return
        _logs_menu(chat_id, user_id, season)
        return

    if text == keyboards.BTN_REPORT:
        season = db.get_active_season()
        if not season:
            send_message(chat_id, texts.no_active_text(db.get_upcoming_season()), reply_markup=_menu(user_id))
            return
        send_message(chat_id, league.build_report(user_row, season), reply_markup=_menu(user_id))
        return

    if text == keyboards.BTN_STATUS:
        send_message(chat_id, league.build_status(user_id), reply_markup=_menu(user_id))
        return

    if text == keyboards.BTN_BOOKS:
        season = db.get_active_season()
        if not season:
            send_message(chat_id, texts.no_active_text(db.get_upcoming_season()), reply_markup=_menu(user_id))
            return
        send_message(chat_id, texts.books_list_text(db.list_books(season["id"])), reply_markup=_menu(user_id))
        return

    if text in (keyboards.BTN_RULES, "/قوانین"):
        send_long(chat_id, texts.rules_text(db.get_rules(), db.get_rules_text()), reply_markup=_menu(user_id))
        return

    if text == keyboards.BTN_PROFILE:
        _show_profile(chat_id, user_id)
        return

    if text in (keyboards.BTN_HELP, "/help", "/کمک"):
        msg = texts.HELP_USER
        if is_admin:
            msg += texts.HELP_ADMIN_EXTRA
        send_long(chat_id, msg, reply_markup=_menu(user_id))
        return

    # ---------- پیش‌فرض ----------
    send_message(chat_id, "از دکمه‌های منو استفاده کنید 👇", reply_markup=_menu(user_id))


# ============================================================
#  هندل callback query ها (دکمه‌های شیشه‌ای)
# ============================================================

def handle_callback_query(cb: dict):
    cb_id = cb.get("id")
    data = cb.get("data", "")
    from_user = cb.get("from", {})
    user_id = from_user.get("id")
    message = cb.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")

    if data.startswith("adm:"):
        admin.handle_callback(cb)
        return

    flow = db.get_user_flow(user_id)
    state = flow["state"] if flow else None

    # ---------- ثبت‌نام: فرزند ----------
    if data in ("children_yes", "children_no"):
        if state != "await_children":
            answer_callback_query(cb_id, texts.STALE_BUTTON, show_alert=True)
            return
        db.update_user(user_id, has_children=1 if data == "children_yes" else 0)
        answer_callback_query(cb_id)
        if message_id:
            edit_message_text(chat_id, message_id, texts.ASK_CHILDREN + "\n\n✅ ثبت شد.")
        _advance_registration(chat_id, user_id)
        return

    user_row = db.get_user(user_id)
    if not user_row or user_row["has_children"] is None:
        answer_callback_query(cb_id, texts.NOT_REGISTERED, show_alert=True)
        return

    # ---------- مشخصات ----------
    if data in ("pchild_yes", "pchild_no"):
        db.update_user(user_id, has_children=1 if data == "pchild_yes" else 0)
        answer_callback_query(cb_id)
        if message_id:
            edit_message_text(chat_id, message_id, "✅ وضعیت فرزند اصلاح شد.")
        _show_profile(chat_id, user_id)
        return

    if data.startswith("prof:"):
        answer_callback_query(cb_id)
        field = data.split(":", 1)[1]
        if field == "name":
            db.set_user_flow(user_id, "edit_name")
            send_message(chat_id, "نام و نام خانوادگی جدید را ارسال کنید:\n(برای انصراف: «❌ انصراف»)")
        elif field == "spouse":
            db.set_user_flow(user_id, "edit_spouse")
            send_message(chat_id, "نام و نام خانوادگی همسر را ارسال کنید:\n(برای انصراف: «❌ انصراف»)")
        elif field == "card":
            db.set_user_flow(user_id, "edit_card")
            send_message(chat_id, texts.ASK_CARD + "\n(برای انصراف: «❌ انصراف»)")
        elif field == "child":
            send_message(
                chat_id,
                "آیا فرزند دارید؟\n(توجه: این گزینه روی محاسبه‌ی امتیاز فصل جاری شما اثر می‌گذارد)",
                reply_markup=keyboards.yes_no_children("pchild"),
            )
        return

    season = db.get_active_season()

    # ---------- اتمام کتاب ----------
    if data.startswith("book_done:"):
        value = data.split(":", 1)[1]
        if not season:
            answer_callback_query(cb_id, "فصلی فعال نیست.", show_alert=True)
            return
        if value == "skip":
            answer_callback_query(cb_id)
            if message_id:
                edit_message_text(chat_id, message_id, texts.BOOK_SKIPPED)
            return
        book = db.get_book(int(value)) if value.isdigit() else None
        if not book or book["season_id"] != season["id"]:
            answer_callback_query(cb_id, "این کتاب دیگر موجود نیست.", show_alert=True)
            return
        ok = db.complete_book(user_id, season["id"], book["id"])
        answer_callback_query(cb_id)
        if message_id:
            edit_message_text(
                chat_id, message_id,
                texts.BOOK_DONE_SAVED.format(points=book["points"], title=book["title"]) if ok
                else texts.BOOK_ALREADY_DONE,
            )
        if ok:
            league.check_prize_increase(season["id"])
        return

    # ---------- اصلاح مطالعه ----------
    if data == "logs:list":
        answer_callback_query(cb_id)
        if season:
            _logs_menu(chat_id, user_id, season, message_id)
        return

    if data.startswith(("log:", "logedit:", "logdel:", "logdelyes:")):
        answer_callback_query(cb_id)
        action, _, raw_id = data.partition(":")
        log_row = db.get_log(int(raw_id)) if raw_id.isdigit() else None
        if (not season or not log_row or log_row["user_id"] != user_id
                or log_row["season_id"] != season["id"]):
            edit_or_send(chat_id, message_id, "این ثبت دیگر قابل اصلاح نیست.")
            return
        when = jdate.fmt_datetime(log_row["created_at"])
        if action == "log":
            edit_or_send(
                chat_id, message_id,
                f"⏱ {log_row['minutes']} دقیقه — {when}\nچه کاری انجام شود؟",
                inline([[("✏️ تغییر عدد", f"logedit:{log_row['id']}"), ("🗑 حذف", f"logdel:{log_row['id']}")],
                        [("↩️ بازگشت", "logs:list")]]),
            )
        elif action == "logedit":
            db.set_user_flow(user_id, "edit_minutes", str(log_row["id"]))
            send_message(chat_id, texts.ASK_EDIT_MINUTES.format(current=log_row["minutes"]))
        elif action == "logdel":
            edit_or_send(
                chat_id, message_id,
                f"ثبت «{log_row['minutes']} دقیقه — {when}» حذف شود؟",
                keyboards.confirm_keyboard(f"logdelyes:{log_row['id']}", "logs:list"),
            )
        else:  # logdelyes
            db.delete_log(log_row["id"])
            edit_or_send(chat_id, message_id, texts.LOG_DELETED, inline([[("↩️ بازگشت به لیست", "logs:list")]]))
        return

    if data == "bk:list":
        answer_callback_query(cb_id)
        if season:
            _books_undo_menu(chat_id, user_id, season, message_id)
        return

    if data.startswith(("bkdel:", "bkdelyes:")):
        answer_callback_query(cb_id)
        action, _, raw_id = data.partition(":")
        book = db.get_book(int(raw_id)) if raw_id.isdigit() else None
        done = {b["id"] for b in db.completed_books(user_id, season["id"])} if season else set()
        if not season or not book or book["id"] not in done:
            edit_or_send(chat_id, message_id, texts.STALE_BUTTON)
            return
        if action == "bkdel":
            edit_or_send(
                chat_id, message_id,
                f"ثبت اتمام کتاب «{book['title']}» ({book['points']} امتیاز) لغو شود؟",
                keyboards.confirm_keyboard(f"bkdelyes:{book['id']}", "bk:list"),
            )
        else:
            db.uncomplete_book(user_id, book["id"])
            edit_or_send(chat_id, message_id, texts.BOOK_UNDONE.format(title=book["title"]),
                         inline([[("↩️ بازگشت", "logs:list")]]))
        return

    answer_callback_query(cb_id)
