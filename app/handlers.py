"""
منطق اصلی پردازش پیام‌ها و callback ها.
"""
import logging

from app import db, texts, keyboards, scoring
from app.bale_api import send_message, answer_callback_query, edit_message_text
from app.config import (
    ADMIN_IDS,
    ADMIN_SETUP_CODE,
    MINUTES_PER_POINT_WITH_CHILD,
    MINUTES_PER_POINT_NO_CHILD,
    MAX_POINTS_PER_SEASON,
)

log = logging.getLogger("handlers")


def is_super_admin(user_id: int) -> bool:
    """مدیر اصلی: کسی که در ADMIN_IDS (.env) است، یا اولین نفری که با کد مخفی ثبت‌نام کرده.
    فقط مدیر اصلی می‌تواند مدیرهای دیگر را حذف کند."""
    return user_id in ADMIN_IDS or db.is_db_super_admin(user_id)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS or db.is_db_admin(user_id)


def user_display_name(tg_user: dict) -> str:
    first = tg_user.get("first_name", "") or ""
    last = tg_user.get("last_name", "") or ""
    full = f"{first} {last}".strip()
    return full or str(tg_user.get("id"))


# ============================================================
#  محاسبه خلاصه وضعیت یک کاربر در فصل جاری (برای کارنامه)
# ============================================================

def build_report(user_row, season_row):
    user_id = user_row["user_id"]
    season_id = season_row["id"]
    has_children = bool(user_row["has_children"])

    minutes = db.total_minutes(user_id, season_id)
    book_pts = db.book_points_sum(user_id, season_id)
    books = db.completed_books(user_id, season_id)

    raw = scoring.raw_points(minutes, has_children, book_pts)
    points = scoring.capped_points(minutes, has_children, book_pts)
    capped = raw >= MAX_POINTS_PER_SEASON

    minutes_to_next = scoring.minutes_to_next_point(minutes, has_children)
    codes = scoring.codes_from_points(points)
    pts_to_next_code = scoring.points_to_next_code(points)

    # رتبه‌بندی بین همه شرکت‌کنندگان فصل
    participants = db.season_participants(season_id)
    scored = []
    for p in participants:
        p_minutes = db.total_minutes(p["user_id"], season_id)
        p_book_pts = db.book_points_sum(p["user_id"], season_id)
        p_points = scoring.capped_points(p_minutes, bool(p["has_children"]), p_book_pts)
        scored.append((p["user_id"], p_points))
    scored.sort(key=lambda x: -x[1])
    rank = next((i + 1 for i, (uid, _) in enumerate(scored) if uid == user_id), len(scored))

    total_prize = db.total_prize_won(user_id)

    return texts.report_text(
        full_name=user_row["full_name"] or user_display_name({"id": user_id}),
        has_children=has_children,
        season_name=season_row["name"],
        minutes=minutes,
        completed_books=books,
        points=points,
        minutes_to_next=minutes_to_next,
        codes=codes,
        points_to_next_code=pts_to_next_code,
        rank=rank,
        total_participants=len(scored) or 1,
        total_prize_so_far=total_prize,
        capped=capped,
    )


# ============================================================
#  هندل پیام‌های متنی
# ============================================================

def handle_message(message: dict):
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    from_user = message.get("from", {})
    user_id = from_user.get("id")
    text = (message.get("text") or "").strip()

    if user_id is None or chat_id is None:
        return

    # ---------- گرفتن آیدی عددی (اختیاری/اطلاعاتی) — همیشه کار می‌کند، حتی قبل از ثبت‌نام ----------
    if text in ("/id", "/آیدی", "/شناسه", "آیدی من", "شناسه من"):
        log.info("درخواست آیدی: user_id=%s name=%s", user_id, user_display_name(from_user))
        send_message(chat_id, f"آیدی عددی شما: {user_id}")
        return

    # ---------- ثبت ادمین با کد مخفی (ADMIN_SETUP_CODE در .env) ----------
    # اولین کسی که این کد را بفرستد «مدیر اصلی» می‌شود و تنها او می‌تواند مدیرهای بعدی را حذف کند.
    if ADMIN_SETUP_CODE and text == ADMIN_SETUP_CODE:
        if is_admin(user_id):
            send_message(chat_id, "شما از قبل ادمین هستید.")
            return
        becomes_super = db.admins_count() == 0 and not ADMIN_IDS
        db.add_admin(user_id, full_name=user_display_name(from_user), is_super=becomes_super)
        log.info("ادمین جدید اضافه شد: user_id=%s super=%s", user_id, becomes_super)
        if becomes_super:
            send_message(
                chat_id,
                "✅ شما به عنوان «مدیر اصلی» ربات ثبت شدید.\n"
                "برای امنیت بیشتر، الان بهتر است مقدار ADMIN_SETUP_CODE را در فایل .env "
                "عوض یا حذف کنید تا دیگران نتوانند با همین کد خودشان را ادمین کنند.",
            )
        else:
            send_message(chat_id, "✅ شما به عنوان ادمین ربات ثبت شدید.")
        return

    flow = db.get_user_flow(user_id)
    flow_state = flow["state"] if flow else None

    # ---------- دستورات ادمین ----------
    # عمدا قبل از گیت «باید ثبت‌نام کنید» بررسی می‌شود: کسی که فقط با کد مخفی ادمین شده،
    # لازم نیست حتما به‌عنوان یک «شرکت‌کننده در لیگ» هم ثبت‌نام کند تا بتواند مدیریت کند.
    if text.startswith("/") and is_admin(user_id):
        handled = handle_admin_command(chat_id, user_id, text)
        if handled:
            return

    if flow_state and flow_state.startswith("admin_") and is_admin(user_id):
        handled = handle_admin_flow(chat_id, user_id, flow_state, flow["data"], text)
        if handled:
            return

    # ---------- /start و ثبت‌نام ----------
    if text == "/start":
        db.clear_user_flow(user_id)
        existing = db.get_user(user_id)
        if existing and existing["full_name"] and existing["has_children"] is not None:
            send_message(chat_id, "شما قبلاً ثبت‌نام کرده‌اید 🙌", reply_markup=keyboards.MAIN_MENU)
            return
        db.upsert_user(user_id, full_name=user_display_name(from_user))
        db.set_user_flow(user_id, "await_name")
        send_message(chat_id, texts.WELCOME)
        return

    if flow_state == "await_name":
        if not text:
            send_message(chat_id, "لطفاً نام و نام خانوادگی را به صورت متن ارسال کنید.")
            return
        db.upsert_user(user_id, full_name=text)
        db.set_user_flow(user_id, "await_children")
        send_message(chat_id, texts.ASK_CHILDREN, reply_markup=keyboards.yes_no_children())
        return

    if flow_state == "await_children":
        send_message(chat_id, "لطفاً با دکمه‌های بالا پاسخ دهید 🙏", reply_markup=keyboards.yes_no_children())
        return

    user_row = db.get_user(user_id)
    if not user_row or not user_row["full_name"] or user_row["has_children"] is None:
        send_message(chat_id, texts.NOT_REGISTERED)
        return

    # ---------- منوی اصلی ----------
    if text == "📖 ثبت مطالعه":
        season = db.get_active_season()
        if not season:
            send_message(chat_id, texts.NO_ACTIVE_SEASON)
            return
        db.set_user_flow(user_id, "await_minutes")
        send_message(chat_id, texts.ASK_MINUTES)
        return

    if flow_state == "await_minutes":
        season = db.get_active_season()
        if not season:
            db.clear_user_flow(user_id)
            send_message(chat_id, texts.NO_ACTIVE_SEASON)
            return
        if not text.isdigit() or int(text) <= 0:
            send_message(chat_id, texts.INVALID_MINUTES)
            return
        minutes = int(text)
        db.add_reading_log(user_id, season["id"], minutes)
        send_message(chat_id, texts.MINUTES_SAVED.format(minutes=minutes))

        books = db.list_books(season["id"])
        done_ids = {b["id"] for b in db.completed_books(user_id, season["id"])}
        remaining_books = [b for b in books if b["id"] not in done_ids]
        db.clear_user_flow(user_id)
        if remaining_books:
            send_message(
                chat_id,
                texts.ASK_BOOK_DONE,
                reply_markup=keyboards.book_choice_keyboard(remaining_books),
            )
        return

    if text == "🏆 کارنامه من":
        season = db.get_active_season()
        if not season:
            send_message(chat_id, texts.NO_ACTIVE_SEASON)
            return
        report = build_report(user_row, season)
        send_message(chat_id, report, reply_markup=keyboards.MAIN_MENU)
        return

    if text == "📚 کتاب‌های ویژه این فصل":
        season = db.get_active_season()
        if not season:
            send_message(chat_id, texts.NO_ACTIVE_SEASON)
            return
        books = db.list_books(season["id"])
        send_message(chat_id, texts.books_list_text(books), reply_markup=keyboards.MAIN_MENU)
        return

    if text == "❓ راهنما" or text == "/help" or text == "/کمک":
        msg = texts.HELP_USER.format(
            interval_child=MINUTES_PER_POINT_WITH_CHILD,
            interval_nochild=MINUTES_PER_POINT_NO_CHILD,
        )
        if is_admin(user_id):
            msg += texts.HELP_ADMIN_EXTRA
        send_message(chat_id, msg, reply_markup=keyboards.MAIN_MENU)
        return

    # ---------- پیش‌فرض ----------
    send_message(chat_id, "از دکمه‌های منو استفاده کنید 👇", reply_markup=keyboards.MAIN_MENU)


# ============================================================
#  دستورات ادمین
# ============================================================

def handle_admin_command(chat_id, user_id, text) -> bool:
    parts = text.split(maxsplit=1)
    cmd = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/فصل_جدید":
        if not rest:
            db.set_user_flow(user_id, "admin_await_season_name")
            send_message(chat_id, "نام فصل جدید را ارسال کنید (مثلاً: پاییز ۱۴۰۴):")
            return True
        _create_season(chat_id, rest)
        return True

    if cmd == "/افزودن_کتاب":
        if "|" not in rest:
            db.set_user_flow(user_id, "admin_await_book_input")
            send_message(chat_id, "عنوان کتاب و امتیاز را با | از هم جدا و ارسال کنید.\nمثال: طرح کلی اندیشه اسلامی در قرآن | 10")
            return True
        _add_book(chat_id, rest)
        return True

    if cmd == "/حذف_کتاب":
        if not rest.isdigit():
            send_message(chat_id, "فرمت درست: /حذف_کتاب <شناسه کتاب>")
            return True
        book = db.get_book(int(rest))
        if not book:
            send_message(chat_id, "کتابی با این شناسه پیدا نشد.")
            return True
        db.remove_book(int(rest))
        send_message(chat_id, f"کتاب «{book['title']}» حذف شد.")
        return True

    if cmd in ("/لیست_کتاب‌ها", "/لیست_کتابها"):
        season = db.get_active_season()
        if not season:
            send_message(chat_id, texts.NO_ACTIVE_SEASON)
            return True
        books = db.list_books(season["id"])
        if not books:
            send_message(chat_id, "هنوز کتابی اضافه نشده.")
            return True
        lines = [f"#{b['id']} — {b['title']} ({b['points']} امتیاز)" for b in books]
        send_message(chat_id, "\n".join(lines))
        return True

    if cmd == "/گزارش_فصل":
        _season_report(chat_id)
        return True

    if cmd == "/پایان_فصل":
        season = db.get_active_season()
        if not season:
            send_message(chat_id, texts.NO_ACTIVE_SEASON)
            return True
        db.set_user_flow(
            user_id, "admin_confirm_end_season", data=str(season["id"])
        )
        send_message(
            chat_id,
            f"آیا مطمئن هستید می‌خواهید «{season['name']}» را پایان دهید؟ "
            f"امتیازها آرشیو و قرعه‌کشی انجام و این فصل بسته می‌شود.\n"
            f"برای تایید دقیقاً بنویسید: بله پایان فصل",
        )
        return True

    if cmd == "/لیست_کاربران":
        users = db.all_users()
        if not users:
            send_message(chat_id, "هنوز کاربری ثبت‌نام نکرده.")
            return True
        lines = [f"تعداد کل: {len(users)} نفر", ""]
        for u in users:
            lines.append(f"- {u['full_name']} (آیدی: {u['user_id']})")
        send_message(chat_id, "\n".join(lines))
        return True

    if cmd == "/لیست_مدیرها":
        admins = db.list_admins()
        lines = ["👤 مدیرهای ربات:\n"]
        for a in admins:
            role = "مدیر اصلی" if a["is_super"] else "ادمین"
            lines.append(f"- {a['full_name'] or a['user_id']} (آیدی: {a['user_id']}) — {role}")
        for static_id in ADMIN_IDS:
            lines.append(f"- {static_id} — مدیر اصلی (از .env)")
        if len(lines) == 1:
            lines.append("هنوز هیچ مدیری با کد مخفی ثبت نشده.")
        send_message(chat_id, "\n".join(lines))
        return True

    if cmd == "/حذف_مدیر":
        if not is_super_admin(user_id):
            send_message(chat_id, "فقط مدیر اصلی می‌تواند مدیرهای دیگر را حذف کند.")
            return True
        if not rest.isdigit():
            send_message(chat_id, "فرمت درست: /حذف_مدیر <آیدی عددی>\nآیدی‌ها را از /لیست_مدیرها ببینید.")
            return True
        target_id = int(rest)
        if target_id == user_id:
            send_message(chat_id, "نمی‌توانید خودتان را حذف کنید.")
            return True
        removed = db.remove_admin(target_id)
        if removed:
            send_message(chat_id, f"✅ ادمین با آیدی {target_id} حذف شد.")
            try:
                send_message(target_id, "دسترسی مدیریتی شما در ربات لیگ کتابخوانی لغو شد.")
            except Exception:
                pass
        else:
            send_message(
                chat_id,
                "پیدا نشد یا قابل حذف نیست (مدیر اصلی را نمی‌توان با این دستور حذف کرد).",
            )
        return True

    return False


def handle_admin_flow(chat_id, user_id, flow_state, data, text) -> bool:
    if flow_state == "admin_await_season_name":
        db.clear_user_flow(user_id)
        _create_season(chat_id, text.strip())
        return True

    if flow_state == "admin_await_book_input":
        db.clear_user_flow(user_id)
        if "|" not in text:
            send_message(chat_id, "فرمت درست نیست. دوباره تلاش کنید: عنوان | امتیاز")
            return True
        _add_book(chat_id, text)
        return True

    if flow_state == "admin_confirm_end_season":
        if text.strip() == "بله پایان فصل":
            db.clear_user_flow(user_id)
            _end_season(chat_id, int(data))
        else:
            db.clear_user_flow(user_id)
            send_message(chat_id, "لغو شد.")
        return True

    return False


def _create_season(chat_id, name):
    if not name:
        send_message(chat_id, "نام فصل نمی‌تواند خالی باشد.")
        return
    season_id = db.create_season(name)
    send_message(chat_id, f"✅ فصل «{name}» شروع شد و برای همه کاربران فعال است.")


def _add_book(chat_id, raw):
    season = db.get_active_season()
    if not season:
        send_message(chat_id, texts.NO_ACTIVE_SEASON)
        return
    title, _, points_str = raw.partition("|")
    title = title.strip()
    points_str = points_str.strip()
    if not title or not points_str.isdigit():
        send_message(chat_id, "فرمت درست: عنوان | امتیاز (امتیاز باید عدد باشد)")
        return
    book_id = db.add_book(season["id"], title, int(points_str))
    send_message(chat_id, f"✅ کتاب «{title}» با {points_str} امتیاز به فصل «{season['name']}» اضافه شد (شناسه #{book_id}).")


def _season_report(chat_id):
    season = db.get_active_season()
    if not season:
        send_message(chat_id, texts.NO_ACTIVE_SEASON)
        return
    participants = db.season_participants(season["id"])
    if not participants:
        send_message(chat_id, "هنوز هیچ‌کس در این فصل مطالعه‌ای ثبت نکرده.")
        return

    rows = []
    for p in participants:
        minutes = db.total_minutes(p["user_id"], season["id"])
        book_pts = db.book_points_sum(p["user_id"], season["id"])
        points = scoring.capped_points(minutes, bool(p["has_children"]), book_pts)
        codes = scoring.codes_from_points(points)
        rows.append((p["full_name"], minutes, points, codes))

    rows.sort(key=lambda r: -r[2])
    lines = [f"📊 گزارش فصل «{season['name']}»\n"]
    for i, (name, minutes, points, codes) in enumerate(rows, start=1):
        lines.append(f"{i}. {name} — {minutes} دقیقه — {points} امتیاز — {codes} کد")
    total_codes = sum(r[3] for r in rows)
    lines.append(f"\nمجموع کدهای شرکت‌کننده در قرعه‌کشی فعلی: {total_codes}")
    send_message(chat_id, "\n".join(lines))


def _end_season(chat_id, season_id):
    season = db.get_season(season_id)
    participants = db.season_participants(season_id)

    entries = []
    for p in participants:
        minutes = db.total_minutes(p["user_id"], season_id)
        book_pts = db.book_points_sum(p["user_id"], season_id)
        points = scoring.capped_points(minutes, bool(p["has_children"]), book_pts)
        codes = scoring.codes_from_points(points)
        rank_key = points
        db.save_season_result(season_id, p["user_id"], minutes, points, codes, rank=0)
        if codes > 0:
            entries.append((p["user_id"], codes))

    # رتبه‌بندی نهایی را روی رکوردهای ذخیره‌شده اصلاح می‌کنیم
    scored = []
    for p in participants:
        minutes = db.total_minutes(p["user_id"], season_id)
        book_pts = db.book_points_sum(p["user_id"], season_id)
        points = scoring.capped_points(minutes, bool(p["has_children"]), book_pts)
        scored.append((p["user_id"], points))
    scored.sort(key=lambda x: -x[1])

    db.end_season(season_id)

    if not entries:
        send_message(
            chat_id,
            f"فصل «{season['name']}» بسته شد. از آنجا که هیچ‌کس کد قرعه‌کشی کسب نکرده بود، قرعه‌کشی انجام نشد.",
        )
        return

    winners, prize, total_codes = scoring.run_lottery(entries)

    for winner_id in winners:
        db.set_result_prize(season_id, winner_id, prize)

    lines = [
        f"🎉 فصل «{season['name']}» به پایان رسید!",
        f"مجموع کد قرعه‌کشی شرکت‌کنندگان: {total_codes}",
        f"مبلغ هر جایزه: {prize:,} تومان\n",
        "🏆 برندگان قرعه‌کشی:",
    ]
    for winner_id in winners:
        u = db.get_user(winner_id)
        name = u["full_name"] if u else str(winner_id)
        lines.append(f"• {name}")
    announcement = "\n".join(lines)

    # اعلام عمومی برای ادمین و پیام خصوصی به هر برنده
    send_message(chat_id, announcement)
    for winner_id in winners:
        try:
            send_message(
                winner_id,
                f"🎉 تبریک! شما در قرعه‌کشی لیگ کتابخوانی فصل «{season['name']}» برنده "
                f"{prize:,} تومان جایزه شدید. مدیر به زودی با شما هماهنگ می‌کند.",
            )
        except Exception:
            log.warning("could not notify winner %s", winner_id)


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

    if data in ("children_yes", "children_no"):
        has_children = 1 if data == "children_yes" else 0
        db.upsert_user(user_id, has_children=has_children)
        db.clear_user_flow(user_id)
        answer_callback_query(cb_id)
        if message_id:
            edit_message_text(chat_id, message_id, texts.ASK_CHILDREN + "\n\n✅ ثبت شد.")
        send_message(chat_id, texts.REGISTER_DONE, reply_markup=keyboards.MAIN_MENU)
        return

    if data.startswith("book_done:"):
        _, value = data.split(":", 1)
        season = db.get_active_season()
        if not season:
            answer_callback_query(cb_id, "فصلی فعال نیست.", show_alert=True)
            return
        if value == "skip":
            answer_callback_query(cb_id)
            if message_id:
                edit_message_text(chat_id, message_id, texts.BOOK_SKIPPED)
            return
        if not value.isdigit():
            answer_callback_query(cb_id)
            return
        book_id = int(value)
        book = db.get_book(book_id)
        if not book:
            answer_callback_query(cb_id, "این کتاب دیگر موجود نیست.", show_alert=True)
            return
        ok = db.complete_book(user_id, season["id"], book_id)
        answer_callback_query(cb_id)
        if ok:
            if message_id:
                edit_message_text(
                    chat_id,
                    message_id,
                    texts.BOOK_DONE_SAVED.format(points=book["points"], title=book["title"]),
                )
        else:
            if message_id:
                edit_message_text(chat_id, message_id, texts.BOOK_ALREADY_DONE)
        return

    answer_callback_query(cb_id)
