"""
پنل مدیریت داخل بله: قوانین و فرمول‌ها، فصل‌ها (با تاریخ شروع/پایان)، کتاب‌های ویژه، گزارش‌ها،
کاربران و رمز ثبت‌نام — به‌صورت دکمه‌ای (inline) و همچنین دستورهای میان‌بر.
"""
import json
import logging

from app import auth, db, jdate, league, texts, utils
from app.bale_api import answer_callback_query, edit_or_send, send_long, send_message
from app.config import ADMIN_IDS
from app.keyboards import confirm_keyboard, inline

log = logging.getLogger("admin")

# (کلید در قوانین، عنوان دکمه/پیام، حداقل مقدار مجاز)
RULE_FIELDS = [
    ("minutes_per_point_child", "⏱ دقیقه برای هر امتیاز (دارای فرزند)", 1),
    ("minutes_per_point_nochild", "⏱ دقیقه برای هر امتیاز (بدون فرزند)", 1),
    ("max_points", "🔝 سقف امتیاز هر فصل", 1),
    ("points_per_code", "🎟 امتیاز لازم برای هر کد", 1),
    ("base_prize", "💰 جایزه پایه هر برنده (تومان)", 0),
    ("bonus_per_step", "➕ افزایش جایزه در هر پله (تومان)", 0),
    ("codes_per_step", "📈 تعداد کد هر پله‌ی افزایش جایزه", 1),
    ("max_prize", "🔒 سقف جایزه هر برنده (تومان)", 0),
    ("winners", "🏆 تعداد برندگان", 1),
]

STATUS_LABEL = {"active": "🟢 فعال", "scheduled": "🕓 در انتظار شروع", "ended": "⚪ پایان‌یافته"}
BACK_HOME = [("↩️ پنل مدیریت", "adm:home")]


# ============================================================
#  پنل اصلی
# ============================================================

def show_panel(chat_id, message_id=None):
    active = db.get_active_season()
    upcoming = db.get_upcoming_season()
    pw = db.get_registration_password()
    lines = ["⚙️ پنل مدیریت لیگ کتابخوانی", ""]
    if active:
        lines.append(f"🟢 فصل فعال: {active['name']}")
        lines.append(texts.period_text(active))
    elif upcoming:
        lines.append(f"🕓 فصل بعدی: {upcoming['name']} — شروع از {jdate.to_jalali_str(upcoming['start_date'])}")
    else:
        lines.append("هیچ فصلی تعریف نشده؛ از «🗓 فصل‌ها» یک فصل بسازید.")
    lines.append(f"👥 کاربران ثبت‌نام‌شده: {db.count_users()} نفر")
    if not pw:
        lines.append("\n⚠️ رمز ثبت‌نام تعیین نشده؛ تا آن را تعیین نکنید هیچ کاربر جدیدی نمی‌تواند ثبت‌نام کند.")
    kb = inline([
        [("📏 قوانین و فرمول‌ها", "adm:rules"), ("🗓 فصل‌ها", "adm:seasons")],
        [("📚 کتاب‌های ویژه", "adm:books:0"), ("📊 گزارش فصل جاری", "adm:report:0")],
        [("👥 کاربران", "adm:users"), ("🔑 رمز ثبت‌نام", "adm:pw")],
    ])
    edit_or_send(chat_id, message_id, "\n".join(lines), kb)


# ============================================================
#  قوانین و فرمول‌ها
# ============================================================

def _rules_screen(chat_id, message_id=None, note=""):
    rules = db.get_rules()
    custom = db.get_rules_text()
    lines = []
    if note:
        lines += [note, ""]
    lines.append("📏 قوانین و فرمول‌ها")
    lines.append("")
    for i, (key, label, _) in enumerate(RULE_FIELDS, start=1):
        value = rules[key]
        shown = utils.fmt_money(value) if "prize" in key or key == "bonus_per_step" else value
        lines.append(f"{i}. {label}: {shown}")
    lines.append("")
    lines.append(f"📝 متن نمایشی قوانین برای کاربران: {'سفارشی' if custom else 'خودکار (از روی اعداد بالا)'}")
    lines.append(f"⏹ پایان خودکار فصل در تاریخ پایان: {'روشن' if db.auto_end_enabled() else 'خاموش'}")
    lines.append("")
    lines.append("برای تغییر هر مورد روی دکمه‌اش بزنید. ⚠️ تغییر اعداد روی محاسبه‌ی امتیاز و کد فصل جاری هم اثر می‌گذارد.")
    rows = []
    for i, (_, label, _) in enumerate(RULE_FIELDS):
        rows.append([(label, f"adm:rule:{i}")])
    rows.append([("📝 ویرایش متن نمایشی قوانین", "adm:ruletext")])
    rows.append([("🔄 متن قوانین ← حالت خودکار", "adm:ruletext_reset"), ("👁 پیش‌نمایش", "adm:rulepreview")])
    rows.append([(f"⏹ پایان خودکار فصل: {'روشن ✅' if db.auto_end_enabled() else 'خاموش ❌'} (تغییر)", "adm:autoend")])
    rows.append(BACK_HOME)
    edit_or_send(chat_id, message_id, "\n".join(lines), inline(rows))


# ============================================================
#  فصل‌ها
# ============================================================

def _seasons_screen(chat_id, message_id=None):
    seasons = db.list_seasons()
    lines = ["🗓 فصل‌های لیگ", ""]
    rows = []
    if not seasons:
        lines.append("هنوز فصلی تعریف نشده است.")
    for s in seasons:
        start = s["start_date"] or (s["started_at"] or "")[:10]
        label = f"{STATUS_LABEL[s['status']].split()[0]} {s['name']} ({jdate.to_jalali_str(start)} تا {jdate.to_jalali_str(s['end_date'])})"
        rows.append([(label, f"adm:s:{s['id']}")])
    rows.append([("➕ فصل جدید", "adm:snew")])
    rows.append(BACK_HOME)
    lines.append("برای دیدن جزئیات، نتایج و کتاب‌های هر فصل (حتی فصل‌های گذشته) روی آن بزنید.")
    edit_or_send(chat_id, message_id, "\n".join(lines), inline(rows))


def _season_screen(chat_id, message_id, season_id):
    s = db.get_season(season_id)
    if not s:
        edit_or_send(chat_id, message_id, "فصل پیدا نشد.", inline([BACK_HOME]))
        return
    start = s["start_date"] or (s["started_at"] or "")[:10]
    lines = [
        f"🗓 {s['name']}",
        f"وضعیت: {STATUS_LABEL[s['status']]}",
        f"شروع: {jdate.to_jalali_str(start)}",
        f"پایان: {jdate.to_jalali_str(s['end_date'])}",
        f"📚 کتاب‌های ویژه: {len(db.list_books(season_id))} عدد",
    ]
    if s["status"] == "active":
        prize, total_codes, standings = league.current_prize(season_id)
        lines.append(f"👥 شرکت‌کنندگان: {len(standings)} نفر | 🎟 کدها: {total_codes}")
        lines.append(f"🎁 جایزه فعلی هر برنده: {utils.fmt_money(prize)} تومان")
    elif s["status"] == "ended":
        results = db.season_results(season_id)
        lines.append(f"👥 شرکت‌کنندگان: {len(results)} نفر")
        winners = [r for r in results if (r["prize"] or 0) > 0]
        if winners:
            lines.append("🏆 برندگان: " + "، ".join(r["full_name"] or str(r["user_id"]) for r in winners))
            lines.append(f"💰 جایزه هر برنده: {utils.fmt_money(winners[0]['prize'])} تومان")
        else:
            lines.append("🏆 برنده‌ای ثبت نشده (قرعه‌کشی انجام نشد).")
    rows = []
    if s["status"] != "ended":
        rows.append([("✏️ نام", f"adm:sedit:{season_id}:name"),
                     ("✏️ تاریخ شروع", f"adm:sedit:{season_id}:start"),
                     ("✏️ تاریخ پایان", f"adm:sedit:{season_id}:end")])
    rows.append([("📚 کتاب‌ها", f"adm:books:{season_id}"),
                 ("📊 گزارش و نتایج", f"adm:report:{season_id}")])
    if s["status"] == "active":
        rows.append([("⏹ پایان فصل و قرعه‌کشی", f"adm:send:{season_id}")])
    rows.append([("↩️ فصل‌ها", "adm:seasons"), BACK_HOME[0]])
    edit_or_send(chat_id, message_id, "\n".join(lines), inline(rows))


def _confirm_end(chat_id, message_id, season_id):
    s = db.get_season(season_id)
    if not s or s["status"] != "active":
        edit_or_send(chat_id, message_id, texts.NO_ACTIVE_SEASON, inline([BACK_HOME]))
        return
    edit_or_send(
        chat_id, message_id,
        f"آیا مطمئن هستید می‌خواهید «{s['name']}» را پایان دهید؟\n"
        "امتیازها ثبت و آرشیو می‌شود، قرعه‌کشی انجام می‌شود و نتیجه (نام برندگان) برای همه ارسال می‌شود.",
        confirm_keyboard(f"adm:sendyes:{season_id}", f"adm:s:{season_id}"),
    )


def _season_report_text(s) -> str:
    sid = s["id"]
    if s["status"] == "scheduled":
        return f"«{s['name']}» هنوز شروع نشده است."
    if s["status"] == "active":
        prize, total_codes, standings = league.current_prize(sid)
        if not standings:
            return f"📊 گزارش «{s['name']}»\n\nهنوز هیچ‌کس مطالعه‌ای ثبت نکرده است."
        lines = [f"📊 گزارش «{s['name']}» (در جریان)\n"]
        for r in standings:
            lines.append(f"{r['rank']}. {r['full_name']} — {r['minutes']} دقیقه — {r['points']} امتیاز — {r['codes']} کد")
        lines.append(f"\n🎟 مجموع کدها: {total_codes}")
        lines.append(f"🎁 جایزه فعلی هر برنده: {utils.fmt_money(prize)} تومان")
        return "\n".join(lines)
    # پایان‌یافته: از نتایج ذخیره‌شده
    results = db.season_results(sid)
    if not results:
        return f"برای «{s['name']}» نتیجه‌ای ذخیره نشده است (شرکت‌کننده‌ای نداشت)."
    lines = [f"📊 نتایج نهایی «{s['name']}»\n"]
    for i, r in enumerate(results, start=1):
        mark = " 🏆" if (r["prize"] or 0) > 0 else ""
        lines.append(f"{i}. {r['full_name'] or r['user_id']} — {r['minutes']} دقیقه — {r['points']} امتیاز — {r['codes']} کد{mark}")
    winners = [r for r in results if (r["prize"] or 0) > 0]
    lines.append("")
    if winners:
        lines.append(f"💰 جایزه هر برنده: {utils.fmt_money(winners[0]['prize'])} تومان")
        lines.append("🏆 برندگان (مشخصات برای هماهنگی):")
        for i, r in enumerate(winners, start=1):
            lines.extend(texts.winner_detail_lines(i, r))
    else:
        lines.append("برنده‌ای ثبت نشده (قرعه‌کشی انجام نشد).")
    return "\n".join(lines)


def _send_report(chat_id, season_id):
    s = db.get_season(season_id)
    if not s:
        send_message(chat_id, "فصل پیدا نشد.")
        return
    send_long(chat_id, _season_report_text(s), inline([[("↩️ بازگشت به فصل", f"adm:s:{season_id}")], BACK_HOME]))


# ============================================================
#  کتاب‌های ویژه
# ============================================================

def _target_season():
    return db.get_active_season() or db.get_upcoming_season()


def _books_screen(chat_id, message_id, season_id):
    s = db.get_season(season_id)
    if not s:
        edit_or_send(chat_id, message_id, "فصلی برای افزودن کتاب وجود ندارد؛ ابتدا یک فصل بسازید.", inline([BACK_HOME]))
        return
    books = db.list_books(season_id)
    lines = [f"📚 کتاب‌های ویژه «{s['name']}» ({STATUS_LABEL[s['status']]})", ""]
    rows = []
    if not books:
        lines.append("هنوز کتابی اضافه نشده.")
    for b in books:
        lines.append(f"#{b['id']} — {b['title']} ({b['points']} امتیاز)")
        if s["status"] != "ended":
            rows.append([(f"🗑 حذف: {b['title']}", f"adm:bookdel:{b['id']}:{season_id}")])
    if s["status"] != "ended":
        rows.append([("➕ افزودن کتاب", f"adm:bookadd:{season_id}")])
    rows.append([("↩️ بازگشت به فصل", f"adm:s:{season_id}"), BACK_HOME[0]])
    edit_or_send(chat_id, message_id, "\n".join(lines), inline(rows))


def _add_book(chat_id, season_id, raw) -> bool:
    season = db.get_season(season_id)
    if not season or season["status"] == "ended":
        send_message(chat_id, "به این فصل نمی‌توان کتاب اضافه کرد.")
        return True
    title, _, points_str = raw.partition("|")
    title, points = title.strip(), utils.parse_int(points_str)
    if not title or points is None:
        send_message(chat_id, "فرمت درست: عنوان | امتیاز (امتیاز باید عدد باشد)\nمثال: طرح کلی اندیشه اسلامی در قرآن | 10")
        return False
    book_id = db.add_book(season_id, title, points)
    send_message(
        chat_id, f"✅ کتاب «{title}» با {points} امتیاز به «{season['name']}» اضافه شد (شناسه #{book_id}).",
        inline([[("📚 لیست کتاب‌ها", f"adm:books:{season_id}")], BACK_HOME]),
    )
    return True


# ============================================================
#  کاربران و رمز ثبت‌نام
# ============================================================

def _send_users(chat_id):
    users = db.all_users()
    if not users:
        send_message(chat_id, "هنوز کاربری ثبت‌نام نکرده.", inline([BACK_HOME]))
        return
    lines = [f"👥 تعداد کل: {len(users)} نفر", ""]
    for i, u in enumerate(users, start=1):
        username = f"@{u['username']}" if u["username"] else "بدون آیدی"
        lines.append(f"{i}. {u['full_name']} (همسر: {u['spouse_name'] or '—'}) — {username} — شناسه: {u['user_id']}")
    send_long(chat_id, "\n".join(lines), inline([BACK_HOME]))


def _pw_screen(chat_id, message_id=None):
    pw = db.get_registration_password()
    if pw:
        text = (f"🔑 رمز ثبت‌نام فعلی: {pw}\n\n"
                "کاربران جدید فقط با این رمز می‌توانند ثبت‌نام کنند. رمز را فقط به شرکت‌کنندگان بدهید.")
    else:
        text = "🔑 رمز ثبت‌نام تعیین نشده است؛ ثبت‌نام کاربران جدید فعلاً بسته است."
    edit_or_send(chat_id, message_id, text, inline([
        [("🔑 تعیین / تغییر رمز", "adm:pwset")],
        [("🚫 بستن ثبت‌نام (حذف رمز)", "adm:pwclear")],
        BACK_HOME,
    ]))


# ============================================================
#  ساخت فصل
# ============================================================

DATE_HINT = "به صورت شمسی، مثل 1405/08/01 (یا کلمه «امروز»)"


def _create_season(chat_id, name, start_iso, end_iso):
    if end_iso < start_iso:
        send_message(chat_id, "❌ تاریخ پایان نمی‌تواند قبل از تاریخ شروع باشد.")
        return False
    active_before = db.get_active_season()
    season_id = db.create_season(name, start_iso, end_iso)
    s = db.get_season(season_id)
    msg = [f"✅ فصل «{name}» ساخته شد.", texts.period_text(s)]
    if start_iso <= jdate.today_iso():
        if active_before:
            msg.append(f"⏳ فصل «{active_before['name']}» هنوز فعال است؛ این فصل بعد از پایان آن شروع می‌شود.")
        else:
            msg.append("🟢 فصل همین حالا شروع شد و به همه‌ی کاربران اطلاع داده می‌شود.")
    else:
        msg.append("🕓 در تاریخ شروع، خودکار فعال می‌شود و به همه‌ی کاربران اطلاع داده می‌شود.")
    msg.append("📚 از بخش «کتاب‌ها»ی همین فصل می‌توانید کتاب‌های ویژه را از همین حالا اضافه کنید.")
    send_message(chat_id, "\n".join(msg), inline([[("📖 جزئیات فصل", f"adm:s:{season_id}")], BACK_HOME]))
    league.tick()
    return True


def _start_new_season_wizard(chat_id, user_id, name=None):
    if name:
        db.set_user_flow(user_id, "admin_new_season_start", json.dumps({"name": name}))
        send_message(chat_id, f"تاریخ شروع فصل «{name}» را ارسال کنید — {DATE_HINT}:")
    else:
        db.set_user_flow(user_id, "admin_new_season_name")
        send_message(chat_id, "نام فصل جدید را ارسال کنید (مثلاً: پاییز ۱۴۰۵):\n(برای انصراف: «❌ انصراف»)")


# ============================================================
#  دستورهای متنی
# ============================================================

def handle_command(chat_id, user_id, text) -> bool:
    parts = text.split(maxsplit=1)
    cmd = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/پنل", "/panel"):
        show_panel(chat_id)
        return True

    if cmd == "/فصل_جدید":
        if rest.count("|") >= 2:
            name, start_raw, end_raw = (x.strip() for x in rest.split("|", 2))
            start_iso, end_iso = jdate.parse_date(start_raw), jdate.parse_date(end_raw)
            if not name or not start_iso or not end_iso:
                send_message(chat_id, "فرمت درست: /فصل_جدید نام | تاریخ شروع | تاریخ پایان\n"
                                      "مثال: /فصل_جدید پاییز | 1405/08/01 | 1405/10/30")
                return True
            _create_season(chat_id, name, start_iso, end_iso)
            return True
        _start_new_season_wizard(chat_id, user_id, rest or None)
        return True

    if cmd == "/افزودن_کتاب":
        target = _target_season()
        if not target:
            send_message(chat_id, "ابتدا یک فصل بسازید (/فصل_جدید).")
            return True
        if "|" not in rest:
            db.set_user_flow(user_id, "admin_book_add", str(target["id"]))
            send_message(chat_id, "عنوان کتاب و امتیاز را با | از هم جدا و ارسال کنید.\nمثال: طرح کلی اندیشه اسلامی در قرآن | 10")
            return True
        _add_book(chat_id, target["id"], rest)
        return True

    if cmd == "/حذف_کتاب":
        book_id = utils.parse_int(rest)
        if book_id is None:
            send_message(chat_id, "فرمت درست: /حذف_کتاب <شناسه کتاب>")
            return True
        book = db.get_book(book_id)
        if not book:
            send_message(chat_id, "کتابی با این شناسه پیدا نشد.")
            return True
        db.remove_book(book_id)
        send_message(chat_id, f"کتاب «{book['title']}» حذف شد.")
        return True

    if cmd in ("/لیست_کتاب‌ها", "/لیست_کتابها"):
        target = _target_season()
        if not target:
            send_message(chat_id, texts.NO_ACTIVE_SEASON)
            return True
        _books_screen(chat_id, None, target["id"])
        return True

    if cmd == "/گزارش_فصل":
        active = db.get_active_season()
        if not active:
            send_message(chat_id, texts.NO_ACTIVE_SEASON)
            return True
        _send_report(chat_id, active["id"])
        return True

    if cmd == "/پایان_فصل":
        active = db.get_active_season()
        if not active:
            send_message(chat_id, texts.NO_ACTIVE_SEASON)
            return True
        _confirm_end(chat_id, None, active["id"])
        return True

    if cmd == "/لیست_کاربران":
        _send_users(chat_id)
        return True

    if cmd == "/رمز_ثبت_نام":
        if len(rest) < 4:
            send_message(chat_id, "فرمت درست: /رمز_ثبت_نام <رمز>  (حداقل ۴ حرف)")
            return True
        db.set_registration_password(rest)
        send_message(chat_id, f"✅ رمز ثبت‌نام تعیین شد: {rest}")
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
        if not auth.is_super_admin(user_id):
            send_message(chat_id, "فقط مدیر اصلی می‌تواند مدیرهای دیگر را حذف کند.")
            return True
        target_id = utils.parse_int(rest)
        if target_id is None:
            send_message(chat_id, "فرمت درست: /حذف_مدیر <آیدی عددی>\nآیدی‌ها را از /لیست_مدیرها ببینید.")
            return True
        if target_id == user_id:
            send_message(chat_id, "نمی‌توانید خودتان را حذف کنید.")
            return True
        if db.remove_admin(target_id):
            send_message(chat_id, f"✅ ادمین با آیدی {target_id} حذف شد.")
            try:
                send_message(target_id, "دسترسی مدیریتی شما در ربات لیگ کتابخوانی لغو شد.")
            except Exception:
                pass
        else:
            send_message(chat_id, "پیدا نشد یا قابل حذف نیست (مدیر اصلی را نمی‌توان با این دستور حذف کرد).")
        return True

    return False


# ============================================================
#  مراحل گفتگوی مدیر (پاسخ متنی به سؤال‌های ربات)
# ============================================================

def handle_flow(chat_id, user_id, state, data, text) -> bool:
    text = text.strip()

    if state == "admin_new_season_name":
        if not text or len(text) > 60:
            send_message(chat_id, "نام فصل باید متنی کوتاه (حداکثر ۶۰ حرف) باشد. دوباره ارسال کنید:")
            return True
        _start_new_season_wizard(chat_id, user_id, text)
        return True

    if state == "admin_new_season_start":
        iso = jdate.parse_date(text)
        if not iso:
            send_message(chat_id, f"تاریخ نامعتبر است. دوباره ارسال کنید — {DATE_HINT}:")
            return True
        d = json.loads(data)
        d["start"] = iso
        db.set_user_flow(user_id, "admin_new_season_end", json.dumps(d))
        send_message(chat_id, f"شروع: {jdate.to_jalali_str(iso)}\nتاریخ پایان فصل را ارسال کنید — {DATE_HINT}:")
        return True

    if state == "admin_new_season_end":
        iso = jdate.parse_date(text)
        d = json.loads(data)
        if not iso:
            send_message(chat_id, f"تاریخ نامعتبر است. دوباره ارسال کنید — {DATE_HINT}:")
            return True
        if iso < d["start"]:
            send_message(chat_id, "تاریخ پایان نمی‌تواند قبل از تاریخ شروع باشد. تاریخ پایان را دوباره ارسال کنید:")
            return True
        db.clear_user_flow(user_id)
        _create_season(chat_id, d["name"], d["start"], iso)
        return True

    if state == "admin_season_edit":
        d = json.loads(data)
        s = db.get_season(d["id"])
        field = d["field"]
        if not s or s["status"] == "ended":
            db.clear_user_flow(user_id)
            send_message(chat_id, "این فصل قابل ویرایش نیست.")
            return True
        if field == "name":
            if not text or len(text) > 60:
                send_message(chat_id, "نام باید متنی کوتاه (حداکثر ۶۰ حرف) باشد. دوباره ارسال کنید:")
                return True
            db.update_season(s["id"], name=text)
        else:
            iso = jdate.parse_date(text)
            if not iso:
                send_message(chat_id, f"تاریخ نامعتبر است. دوباره ارسال کنید — {DATE_HINT}:")
                return True
            start = iso if field == "start" else s["start_date"]
            end = iso if field == "end" else s["end_date"]
            if start and end and end < start:
                send_message(chat_id, "تاریخ پایان نمی‌تواند قبل از تاریخ شروع باشد. تاریخ دیگری ارسال کنید:")
                return True
            if field == "end" and s["status"] == "active" and iso < jdate.today_iso():
                send_message(chat_id, "برای فصل فعال، تاریخ پایان نمی‌تواند در گذشته باشد. "
                                      "اگر می‌خواهید فصل همین حالا تمام شود از دکمه «پایان فصل» استفاده کنید.")
                return True
            db.update_season(s["id"], **({"start_date": iso} if field == "start" else {"end_date": iso}))
        db.clear_user_flow(user_id)
        send_message(chat_id, "✅ ذخیره شد.")
        league.tick()
        _season_screen(chat_id, None, s["id"])
        return True

    if state == "admin_book_add":
        if _add_book(chat_id, int(data), text):
            db.clear_user_flow(user_id)
        return True

    if state == "admin_set_rule":
        key, label, min_val = RULE_FIELDS[int(data)]
        val = utils.parse_int(text)
        if val is None or val < min_val or val > 10**9:
            send_message(chat_id, f"لطفاً یک عدد صحیح (حداقل {min_val}) ارسال کنید.\n(برای انصراف: «❌ انصراف»)")
            return True
        old = db.get_rules()[key]
        db.set_rule(key, val)
        db.clear_user_flow(user_id)
        active = db.get_active_season()
        if active:
            league.check_prize_increase(active["id"], reset_lower=True)
        _rules_screen(chat_id, None, note=f"✅ «{label}» تغییر کرد: {old} ← {val}")
        return True

    if state == "admin_set_rules_text":
        if not text or len(text) > 3500:
            send_message(chat_id, "متن قوانین باید خالی نباشد و حداکثر ۳۵۰۰ حرف باشد. دوباره ارسال کنید:")
            return True
        db.set_rules_text(text)
        db.clear_user_flow(user_id)
        _rules_screen(chat_id, None, note="✅ متن نمایشی قوانین ذخیره شد و از این به بعد به کاربران نشان داده می‌شود.")
        return True

    if state == "admin_set_pw":
        if len(text) < 4 or len(text) > 40:
            send_message(chat_id, "رمز باید بین ۴ تا ۴۰ حرف باشد. دوباره ارسال کنید:")
            return True
        db.set_registration_password(text)
        db.clear_user_flow(user_id)
        send_message(chat_id, f"✅ رمز ثبت‌نام تعیین شد: {text}", inline([BACK_HOME]))
        return True

    return False


# ============================================================
#  دکمه‌های پنل (callback)
# ============================================================

def _int(parts, i, default=None):
    try:
        return int(parts[i])
    except (IndexError, ValueError):
        return default


def handle_callback(cb: dict):
    cb_id = cb.get("id")
    data = cb.get("data", "")
    user_id = cb.get("from", {}).get("id")
    message = cb.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")

    if not auth.is_admin(user_id):
        answer_callback_query(cb_id, "دسترسی ندارید.", show_alert=True)
        return
    answer_callback_query(cb_id)

    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "home":
        show_panel(chat_id, message_id)

    # ---- قوانین ----
    elif action == "rules":
        _rules_screen(chat_id, message_id)

    elif action == "rule":
        idx = _int(parts, 2)
        if idx is None or not (0 <= idx < len(RULE_FIELDS)):
            return
        key, label, min_val = RULE_FIELDS[idx]
        db.set_user_flow(user_id, "admin_set_rule", str(idx))
        send_message(
            chat_id,
            f"{label}\nمقدار فعلی: {db.get_rules()[key]}\n\nمقدار جدید را به صورت عدد ارسال کنید "
            f"(حداقل {min_val}).\n(برای انصراف: «❌ انصراف»)",
        )

    elif action == "ruletext":
        db.set_user_flow(user_id, "admin_set_rules_text")
        current = texts.rules_text(db.get_rules(), db.get_rules_text())
        send_message(
            chat_id,
            "متن کامل قوانین را ارسال کنید؛ همان‌طور که می‌فرستید (با همین خط‌بندی) به کاربران نشان داده می‌شود.\n"
            "(برای انصراف: «❌ انصراف»)\n\n"
            "متن فعلی برای کپی و ویرایش:\n\n" + current,
        )

    elif action == "ruletext_reset":
        db.set_rules_text(None)
        _rules_screen(chat_id, message_id, note="✅ متن قوانین به حالت خودکار برگشت (از روی اعداد ساخته می‌شود).")

    elif action == "rulepreview":
        send_long(chat_id, texts.rules_text(db.get_rules(), db.get_rules_text()), inline([[("↩️ قوانین و فرمول‌ها", "adm:rules")]]))

    elif action == "autoend":
        db.set_auto_end(not db.auto_end_enabled())
        _rules_screen(chat_id, message_id)

    # ---- فصل‌ها ----
    elif action == "seasons":
        _seasons_screen(chat_id, message_id)

    elif action == "snew":
        _start_new_season_wizard(chat_id, user_id)

    elif action == "s":
        _season_screen(chat_id, message_id, _int(parts, 2, 0))

    elif action == "sedit":
        sid, field = _int(parts, 2), (parts[3] if len(parts) > 3 else "")
        s = db.get_season(sid) if sid else None
        if not s or s["status"] == "ended" or field not in ("name", "start", "end"):
            return
        db.set_user_flow(user_id, "admin_season_edit", json.dumps({"id": sid, "field": field}))
        prompts = {
            "name": f"نام جدید فصل را ارسال کنید (فعلی: {s['name']}):",
            "start": f"تاریخ شروع جدید را ارسال کنید (فعلی: {jdate.to_jalali_str(s['start_date'])}) — {DATE_HINT}:",
            "end": f"تاریخ پایان جدید را ارسال کنید (فعلی: {jdate.to_jalali_str(s['end_date'])}) — {DATE_HINT}:",
        }
        send_message(chat_id, prompts[field] + "\n(برای انصراف: «❌ انصراف»)")

    elif action == "send":
        _confirm_end(chat_id, message_id, _int(parts, 2, 0))

    elif action == "sendyes":
        sid = _int(parts, 2, 0)
        edit_or_send(chat_id, message_id, "⏳ در حال پایان فصل، قرعه‌کشی و ارسال نتیجه به کاربران...", None)
        if league.finish_season(sid):
            league.tick()
            send_message(chat_id, "✅ فصل پایان یافت؛ نتیجه برای همه ارسال شد و مشخصات برندگان در پیام جداگانه برای مدیرها آمد.",
                         inline([[("📊 نتایج فصل", f"adm:report:{sid}")], BACK_HOME]))
        else:
            send_message(chat_id, "این فصل فعال نیست (شاید قبلاً پایان یافته).", inline([BACK_HOME]))

    # ---- گزارش ----
    elif action == "report":
        sid = _int(parts, 2, 0)
        if not sid:
            active = db.get_active_season()
            if not active:
                edit_or_send(chat_id, message_id, texts.no_active_text(db.get_upcoming_season()), inline([BACK_HOME]))
                return
            sid = active["id"]
        _send_report(chat_id, sid)

    # ---- کتاب‌ها ----
    elif action == "books":
        sid = _int(parts, 2, 0)
        if not sid:
            target = _target_season()
            if not target:
                edit_or_send(chat_id, message_id, "ابتدا یک فصل بسازید (🗓 فصل‌ها ← ➕ فصل جدید).", inline([BACK_HOME]))
                return
            sid = target["id"]
        _books_screen(chat_id, message_id, sid)

    elif action == "bookadd":
        sid = _int(parts, 2)
        if not sid:
            return
        db.set_user_flow(user_id, "admin_book_add", str(sid))
        send_message(chat_id, "عنوان کتاب و امتیاز را با | از هم جدا و ارسال کنید.\n"
                              "مثال: طرح کلی اندیشه اسلامی در قرآن | 10\n(برای انصراف: «❌ انصراف»)")

    elif action == "bookdel":
        bid, sid = _int(parts, 2), _int(parts, 3)
        book = db.get_book(bid) if bid else None
        if not book:
            _books_screen(chat_id, message_id, sid)
            return
        edit_or_send(
            chat_id, message_id,
            f"کتاب «{book['title']}» حذف شود؟ (امتیاز اتمام این کتاب هم از کاربرانی که ثبت کرده‌اند کم می‌شود)",
            confirm_keyboard(f"adm:bookdelyes:{bid}:{sid}", f"adm:books:{sid}"),
        )

    elif action == "bookdelyes":
        bid, sid = _int(parts, 2), _int(parts, 3)
        if bid:
            db.remove_book(bid)
        _books_screen(chat_id, message_id, sid)

    # ---- کاربران / رمز ----
    elif action == "users":
        _send_users(chat_id)

    elif action == "pw":
        _pw_screen(chat_id, message_id)

    elif action == "pwset":
        db.set_user_flow(user_id, "admin_set_pw")
        send_message(chat_id, "رمز ثبت‌نام جدید را ارسال کنید (۴ تا ۴۰ حرف):\n(برای انصراف: «❌ انصراف»)")

    elif action == "pwclear":
        db.set_registration_password("")
        _pw_screen(chat_id, message_id)
