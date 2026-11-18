"""
پنل مدیریت داخل بله: قوانین و فرمول‌ها، فصل‌ها (با تاریخ شروع/پایان)، کتاب‌های ویژه، گزارش‌ها،
کاربران و رمز ثبت‌نام — به‌صورت دکمه‌ای (inline) و همچنین دستورهای میان‌بر.
"""
import json
import logging
import os

from app import auth, backup, bale_api, db, jdate, league, texts, utils
from app.bale_api import answer_callback_query, edit_or_send, send_long, send_message
from app.config import ADMIN_IDS
from app.keyboards import cancel_kb, confirm_keyboard, inline

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
PAGE_SIZE = 8
WIPE_WORD = "حذف همه"


def _ask(chat_id, text):
    """پرسشی که منتظر پاسخ متنی مدیر است؛ همراه دکمه‌ی شیشه‌ای «❌ انصراف»."""
    return send_message(chat_id, text, reply_markup=cancel_kb())


# ============================================================
#  پنل اصلی
# ============================================================

def show_panel(chat_id, message_id=None, user_id=None):
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
    rows = [
        [("📏 قوانین و فرمول‌ها", "adm:rules"), ("🗓 فصل‌ها", "adm:seasons")],
        [("📚 کتاب‌های ویژه", "adm:books:0"), ("📊 گزارش فصل جاری", "adm:report:0")],
        [("👥 کاربران", "adm:users:0"), ("🛡 مدیرها", "adm:admins")],
        [("🔑 رمز ثبت‌نام", "adm:pw")],
    ]
    if user_id is None or auth.can_wipe(user_id):
        rows[-1].append(("🗄 داده و پشتیبان", "adm:data"))
    kb = inline(rows)
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
        rows.append([("➕ افزودن کتاب (یک یا چند)", f"adm:bookadd:{season_id}")])
        if books:
            rows.append([("🗑 حذف چند کتاب", f"adm:bookdelmulti:{season_id}")])
    rows.append([("↩️ بازگشت به فصل", f"adm:s:{season_id}"), BACK_HOME[0]])
    edit_or_send(chat_id, message_id, "\n".join(lines), inline(rows))


BOOK_FORMAT = ("هر کتاب در یک خط: عنوان | امتیاز\n"
               "برای افزودن چند کتاب، چند خط بنویسید و یکجا بفرستید. مثال:\n"
               "طرح کلی اندیشه اسلامی در قرآن | 10\n"
               "کتاب دوم | 8")


def _add_books(chat_id, season_id, raw) -> bool:
    """یک یا چند کتاب (هر خط: عنوان | امتیاز). True اگر کار تمام شد؛ False اگر باید دوباره ارسال کند."""
    season = db.get_season(season_id)
    if not season or season["status"] == "ended":
        send_message(chat_id, "به این فصل نمی‌توان کتاب اضافه کرد.")
        return True
    items, failed = [], []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        title, sep, points_str = line.rpartition("|")
        title, points = title.strip(), utils.parse_int(points_str)
        if not sep or not title or points is None:
            failed.append(line)
        else:
            items.append((title, points))
    if len(items) + len(failed) > 100:
        _ask(chat_id, "حداکثر ۱۰۰ خط در هر بار. تعداد کمتری ارسال کنید.")
        return False
    if not items:
        _ask(chat_id, "هیچ کتاب معتبری پیدا نشد.\n" + BOOK_FORMAT + "\n(امتیاز باید عدد باشد)")
        return False
    db.add_books(season_id, items)
    lines = [f"✅ {len(items)} کتاب به «{season['name']}» اضافه شد:"]
    lines += [f"• {t} — {p} امتیاز" for t, p in items]
    if failed:
        lines.append(f"\n⚠️ {len(failed)} خط نامعتبر بود و اضافه نشد (فرمت: عنوان | امتیاز):")
        lines += [f"✗ {f}" for f in failed]
    send_long(chat_id, "\n".join(lines),
              inline([[("📚 لیست کتاب‌ها", f"adm:books:{season_id}")], BACK_HOME]))
    return True


def _delete_books(chat_id, text, season_id=None):
    """حذف یک یا چند کتاب با شناسه (فاصله/کاما/خط جدید؛ بازه مثل 3-6). True اگر شناسه‌ی معتبری خوانده شد."""
    ids, bad = utils.parse_id_list(text)
    if not ids:
        _ask(chat_id, "شناسه‌ای پیدا نشد. شناسه‌ها را با فاصله یا کاما بنویسید؛ مثال: 3 5 7 یا 3-6")
        return False
    removed, missing = [], []
    for bid in ids:
        book = db.get_book(bid)
        season = db.get_season(book["season_id"]) if book else None
        if (not book or not season or season["status"] == "ended"
                or (season_id is not None and book["season_id"] != season_id)):
            missing.append(bid)
            continue
        db.remove_book(bid)
        removed.append(f"#{bid} {book['title']}")
    lines = []
    if removed:
        lines.append(f"🗑 {len(removed)} کتاب حذف شد:")
        lines += [f"• {r}" for r in removed]
    if missing:
        lines.append("⚠️ پیدا نشد یا قابل حذف نیست (فصل پایان‌یافته): " + "، ".join(f"#{m}" for m in missing))
    if bad:
        lines.append("⚠️ نامعتبر: " + "، ".join(bad))
    send_long(chat_id, "\n".join(lines) or "چیزی حذف نشد.",
              inline([[("📚 لیست کتاب‌ها", f"adm:books:{season_id}")], BACK_HOME] if season_id else [BACK_HOME]))
    return True


# ============================================================
#  کاربران و رمز ثبت‌نام
# ============================================================

USER_DEL_WARNING = ("⚠️ همه‌ی مطالعه‌ها، امتیازها و نتایج ذخیره‌شده‌ی این کاربر در همه‌ی فصل‌ها (از جمله فصل‌های گذشته) "
                    "پاک می‌شود و برگشت‌پذیر نیست (مگر با فایل پشتیبان). کاربر می‌تواند دوباره با رمز ثبت‌نام کند.")


def _send_users(chat_id):
    """لیست کامل متنی کاربران."""
    users = db.all_users()
    if not users:
        send_message(chat_id, "هنوز کاربری ثبت‌نام نکرده.", inline([BACK_HOME]))
        return
    lines = [f"👥 تعداد کل: {len(users)} نفر", ""]
    for i, u in enumerate(users, start=1):
        username = f"@{u['username']}" if u["username"] else "بدون آیدی"
        lines.append(f"{i}. {u['full_name']} (همسر: {u['spouse_name'] or '—'}) — {username} — شناسه: {u['user_id']}")
    send_long(chat_id, "\n".join(lines), inline([BACK_HOME]))


def _users_screen(chat_id, message_id, page=0):
    users = db.all_users()
    total = len(users)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(page, 0), pages - 1)
    chunk = users[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    text = (f"👥 کاربران ({total} نفر) — صفحه {page + 1} از {pages}\n"
            "روی هر کاربر بزنید تا مشخصاتش و گزینه‌ی حذف را ببینید.\n"
            "حذف چند کاربر یکجا: /حذف_کاربر <شناسه‌ها>")
    rows = [[(u["full_name"] or str(u["user_id"]), f"adm:user:{u['user_id']}:{page}")] for u in chunk]
    nav = []
    if page > 0:
        nav.append(("◀️ قبلی", f"adm:users:{page - 1}"))
    if page < pages - 1:
        nav.append(("بعدی ▶️", f"adm:users:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([("📄 لیست کامل (متن)", "adm:userstext")])
    rows.append(BACK_HOME)
    edit_or_send(chat_id, message_id, text, inline(rows))


def _user_screen(chat_id, message_id, uid, page):
    u = db.get_user(uid)
    if not u:
        _users_screen(chat_id, message_id, page)
        return
    username = f"@{u['username']}" if u["username"] else "ندارد"
    text = (f"👤 {u['full_name']}\n"
            f"همسر: {u['spouse_name'] or '—'}\n"
            f"فرزند: {'دارد' if u['has_children'] else 'ندارد'}\n"
            f"آیدی بله: {username}\n"
            f"شناسه عددی: {u['user_id']}\n"
            f"شماره کارت: {utils.mask_card(u['card_number'])}\n"
            f"ثبت‌نام: {jdate.fmt_datetime(u['registered_at'])}")
    edit_or_send(chat_id, message_id, text, inline([
        [("🗑 حذف این کاربر", f"adm:userdel:{uid}:{page}")],
        [("↩️ لیست کاربران", f"adm:users:{page}")],
    ]))


def _delete_users(ids):
    active = db.get_active_season()
    for uid in ids:
        db.delete_user(uid)
        try:
            send_message(uid, "ثبت‌نام شما در لیگ کتابخوانی توسط مدیر حذف شد. برای ثبت‌نام دوباره با مدیر هماهنگ کنید.")
        except Exception:
            pass
    if active:
        league.check_prize_increase(active["id"], reset_lower=True)


def _admins_screen(chat_id, message_id, viewer_id):
    is_sup = auth.is_super_admin(viewer_id)
    lines = ["🛡 مدیرهای ربات", ""]
    rows = []
    for a in db.list_admins():
        name = a["full_name"] or str(a["user_id"])
        if a["is_super"]:
            lines.append(f"- {name} (آیدی: {a['user_id']}) — مدیر اصلی")
            continue
        lines.append(f"- {name} (آیدی: {a['user_id']}) — ادمین | اجازه‌ی حذف همه‌ی داده‌ها: "
                     f"{'✅' if a['can_wipe'] else '❌'}")
        if is_sup:
            rows.append([(f"🗑 حذف مدیر: {name}", f"adm:admdel:{a['user_id']}")])
            rows.append([(f"{'🔒 گرفتن' if a['can_wipe'] else '🔓 دادن'} اجازه‌ی حذف داده‌ها: {name}",
                          f"adm:admwipe:{a['user_id']}")])
    for static_id in ADMIN_IDS:
        lines.append(f"- {static_id} — مدیر اصلی (از .env)")
    lines.append("")
    lines.append("فقط مدیر اصلی می‌تواند مدیر حذف کند یا اجازه‌ی «حذف همه‌ی داده‌ها» بدهد. "
                 "مدیر اصلی و مدیرهای تعریف‌شده در .env از اینجا حذف‌شدنی نیستند.")
    rows.append(BACK_HOME)
    edit_or_send(chat_id, message_id, "\n".join(lines), inline(rows))


# ============================================================
#  داده‌ها: پشتیبان‌گیری، بازیابی، حذف همه‌ی داده‌ها
# ============================================================

def _data_screen(chat_id, message_id, user_id):
    backup.remove_quietly(backup.PENDING_ZIP, backup.PENDING_DB)  # فایل نیمه‌کاره‌ی بازیابی (حاوی اطلاعات حساس) نماند
    sup, wipe = auth.is_super_admin(user_id), auth.can_wipe(user_id)
    if not wipe:
        edit_or_send(chat_id, message_id, "دسترسی ندارید.", inline([BACK_HOME]))
        return
    lines = ["🗄 داده و پشتیبان", ""]
    rows = []
    if sup:
        lines += [
            "💾 پشتیبان‌گیری: یک فایل دریافت می‌کنید که همه‌ی اطلاعات (فصل‌ها، کاربران، مطالعه‌ها، قوانین، مدیرها) در آن است.",
            "♻️ بازیابی: همان فایل را برای ربات بفرستید تا همه‌چیز به همان وضعیت برگردد.",
            "",
        ]
        rows.append([("💾 دریافت فایل پشتیبان", "adm:backup")])
        rows.append([("♻️ بازیابی از فایل پشتیبان", "adm:restore")])
    lines.append("🗑 حذف داده‌ها: پاک‌کردن همه‌ی فصل‌ها و تاریخچه (و در صورت انتخاب، کاربران). با هشدار و تایید چندمرحله‌ای.")
    rows.append([("🗑 حذف داده‌ها", "adm:wipe")])
    rows.append(BACK_HOME)
    edit_or_send(chat_id, message_id, "\n".join(lines), inline(rows))


def _send_backup(chat_id, title="💾 فایل پشتیبان لیگ کتابخوانی") -> bool:
    path = None
    try:
        path = backup.create_backup()
        resp = bale_api.send_document(
            chat_id, path,
            caption=f"{title}\n{jdate.fmt_datetime(jdate.now_iso())}\n\n"
                    "⚠️ شامل شماره کارت و آیدی کاربران است؛ محرمانه نگه دارید.\n"
                    "بازیابی: پنل مدیریت ← داده و پشتیبان ← بازیابی، و همین فایل را بفرستید.",
        )
        return bool(resp.get("ok"))
    except Exception:
        log.exception("backup failed")
        return False
    finally:
        backup.remove_quietly(path)


def handle_restore_document(chat_id, user_id, doc: dict):
    """فایل zip پشتیبان که مدیر اصلی فرستاده را بررسی می‌کند و برای تایید نهایی خلاصه‌اش را نشان می‌دهد."""
    if not auth.is_super_admin(user_id):
        return
    if (doc.get("file_size") or 0) > 50 * 1024 * 1024:
        _ask(chat_id, "حجم فایل زیاد است (حداکثر ۵۰ مگابایت).")
        return
    info = bale_api.get_file(doc.get("file_id", ""))
    file_path = (info.get("result") or {}).get("file_path") if info.get("ok") else None
    if not file_path:
        _ask(chat_id, "نتوانستم فایل را از بله دریافت کنم. دوباره بفرستید.")
        return
    backup._ensure_tmp()
    if not bale_api.download_file(file_path, backup.PENDING_ZIP):
        _ask(chat_id, "دانلود فایل ناموفق بود. دوباره بفرستید.")
        return
    try:
        summary = backup.inspect_upload(backup.PENDING_ZIP)
    except ValueError as e:
        backup.remove_quietly(backup.PENDING_ZIP, backup.PENDING_DB)
        _ask(chat_id, f"❌ {e}\nفایل درست را بفرستید.")
        return
    db.clear_user_flow(user_id)
    seasons = summary["seasons"]
    shown = "، ".join(seasons[:10]) + (" …" if len(seasons) > 10 else "") if seasons else "—"
    send_message(
        chat_id,
        "📦 فایل پشتیبان معتبر است.\n"
        f"🕓 تاریخ ساخت: {jdate.fmt_datetime(summary['created_at'])}\n"
        f"🔖 نسخه ربات: {summary['version']}\n"
        f"👥 کاربران: {summary['users']}\n"
        f"🗓 فصل‌ها ({len(seasons)}): {shown}\n"
        f"⏱ ثبت‌های مطالعه: {summary['logs']}\n\n"
        "⚠️ با تایید، همه‌ی داده‌های فعلی با محتوای این فایل جایگزین می‌شود. "
        "پیش از جایگزینی یک فایل پشتیبان از وضعیت فعلی برایتان ارسال می‌شود.",
        confirm_keyboard("adm:restoreyes", "adm:data"),
    )


def _wipe_warning_screen(chat_id, message_id):
    edit_or_send(
        chat_id, message_id,
        "🚨 هشدار: حذف داده‌ها\n\n"
        "این کار غیرقابل برگشت است. یکی از دو سطح را انتخاب کنید:\n\n"
        "۱) حذف لیگ‌ها و تاریخچه — همه‌ی فصل‌ها، کتاب‌های ویژه، مطالعه‌ها، امتیازها و نتایج و برندگان پاک می‌شود. "
        "کاربران، مدیرها و تنظیمات (قوانین، رمز ثبت‌نام) می‌مانند.\n\n"
        "۲) حذف کامل — علاوه بر موارد بالا، همه‌ی کاربران ثبت‌نام‌شده هم حذف می‌شوند "
        "(باید دوباره با رمز ثبت‌نام کنند). مدیرها و تنظیمات می‌مانند.\n\n"
        "🛟 قبل از حذف، خودکار یک فایل پشتیبان برای مدیر اصلی ارسال می‌شود تا در صورت پشیمانی بتوان بازیابی کرد. "
        "در مرحله‌ی بعد باید عبارت تایید را هم بنویسید.",
        inline([
            [("🗑 حذف لیگ‌ها و تاریخچه", "adm:wipelvl:leagues")],
            [("☠️ حذف کامل (با کاربران)", "adm:wipelvl:full")],
            [("↩️ بازگشت", "adm:data")],
        ]),
    )


def _do_wipe(chat_id, user_id, level):
    if not auth.can_wipe(user_id):
        send_message(chat_id, "دسترسی ندارید.")
        return
    sent = 0
    for sid in sorted(auth.super_admin_ids()):
        if _send_backup(sid, "🛟 پشتیبان خودکار پیش از حذف داده‌ها"):
            sent += 1
    if not sent:
        send_message(chat_id, "❌ نتوانستم فایل پشتیبان ایمنی را برای مدیر اصلی بفرستم؛ به‌خاطر امنیت داده‌ها حذف انجام نشد.\n"
                              "(مدیر اصلی باید حداقل یک‌بار با ربات گفتگو کرده باشد.)")
        return
    db.wipe_all(full=(level == "full"))
    log.warning("DATA WIPED by %s level=%s", user_id, level)
    send_message(chat_id, "✅ داده‌ها حذف شد." + (" (همراه با کاربران)" if level == "full" else " (کاربران و تنظیمات باقی ماند)")
                 + "\nفایل پشتیبان پیش از حذف برای مدیر اصلی ارسال شده است.",
                 inline([BACK_HOME]))


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
        _ask(chat_id, f"تاریخ شروع فصل «{name}» را ارسال کنید — {DATE_HINT}:")
    else:
        db.set_user_flow(user_id, "admin_new_season_name")
        _ask(chat_id, "نام فصل جدید را ارسال کنید (مثلاً: پاییز ۱۴۰۵):\n(برای انصراف: «❌ انصراف»)")


# ============================================================
#  دستورهای متنی
# ============================================================

def handle_command(chat_id, user_id, text) -> bool:
    parts = text.split(maxsplit=1)
    cmd = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/پنل", "/panel"):
        show_panel(chat_id, user_id=user_id)
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
            _ask(chat_id, BOOK_FORMAT)
            return True
        _add_books(chat_id, target["id"], rest)
        return True

    if cmd == "/حذف_کتاب":
        if not rest:
            send_message(chat_id, "فرمت درست: /حذف_کتاب <شناسه‌ها>\nمثال: /حذف_کتاب 3 5 7 یا /حذف_کتاب 3-6")
            return True
        _delete_books(chat_id, rest)
        return True

    if cmd == "/حذف_کاربر":
        ids, bad = utils.parse_id_list(rest)
        found = [db.get_user(i) for i in ids]
        found = [u for u in found if u]
        if not found:
            send_message(chat_id, "فرمت درست: /حذف_کاربر <شناسه‌های عددی>\nمثال: /حذف_کاربر 111 222\n"
                                  "شناسه‌ها را از «👥 کاربران» ببینید. (کاربری با این شناسه‌ها پیدا نشد)")
            return True
        db.set_user_flow(user_id, "admin_user_del_confirm", json.dumps([u["user_id"] for u in found]))
        names = "\n".join(f"• {u['full_name']} ({u['user_id']})" for u in found[:40])
        send_message(chat_id, f"⚠️ {len(found)} کاربر حذف شوند؟\n{names}\n\n" + USER_DEL_WARNING,
                     confirm_keyboard("adm:udmyes", "cancel"))
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
            _ask(chat_id, "نام فصل باید متنی کوتاه (حداکثر ۶۰ حرف) باشد. دوباره ارسال کنید:")
            return True
        _start_new_season_wizard(chat_id, user_id, text)
        return True

    if state == "admin_new_season_start":
        iso = jdate.parse_date(text)
        if not iso:
            _ask(chat_id, f"تاریخ نامعتبر است. دوباره ارسال کنید — {DATE_HINT}:")
            return True
        d = json.loads(data)
        d["start"] = iso
        db.set_user_flow(user_id, "admin_new_season_end", json.dumps(d))
        _ask(chat_id, f"شروع: {jdate.to_jalali_str(iso)}\nتاریخ پایان فصل را ارسال کنید — {DATE_HINT}:")
        return True

    if state == "admin_new_season_end":
        iso = jdate.parse_date(text)
        d = json.loads(data)
        if not iso:
            _ask(chat_id, f"تاریخ نامعتبر است. دوباره ارسال کنید — {DATE_HINT}:")
            return True
        if iso < d["start"]:
            _ask(chat_id, "تاریخ پایان نمی‌تواند قبل از تاریخ شروع باشد. تاریخ پایان را دوباره ارسال کنید:")
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
                _ask(chat_id, "نام باید متنی کوتاه (حداکثر ۶۰ حرف) باشد. دوباره ارسال کنید:")
                return True
            db.update_season(s["id"], name=text)
        else:
            iso = jdate.parse_date(text)
            if not iso:
                _ask(chat_id, f"تاریخ نامعتبر است. دوباره ارسال کنید — {DATE_HINT}:")
                return True
            start = iso if field == "start" else s["start_date"]
            end = iso if field == "end" else s["end_date"]
            if start and end and end < start:
                _ask(chat_id, "تاریخ پایان نمی‌تواند قبل از تاریخ شروع باشد. تاریخ دیگری ارسال کنید:")
                return True
            if field == "end" and s["status"] == "active" and iso < jdate.today_iso():
                _ask(chat_id, "برای فصل فعال، تاریخ پایان نمی‌تواند در گذشته باشد. "
                                      "اگر می‌خواهید فصل همین حالا تمام شود از دکمه «پایان فصل» استفاده کنید.")
                return True
            db.update_season(s["id"], **({"start_date": iso} if field == "start" else {"end_date": iso}))
        db.clear_user_flow(user_id)
        send_message(chat_id, "✅ ذخیره شد.")
        league.tick()
        _season_screen(chat_id, None, s["id"])
        return True

    if state == "admin_book_del_multi":
        if _delete_books(chat_id, text, int(data)):
            db.clear_user_flow(user_id)
        return True

    if state == "admin_wipe_confirm":
        db.clear_user_flow(user_id)
        if text == WIPE_WORD:
            _do_wipe(chat_id, user_id, data)
        else:
            send_message(chat_id, "عبارت تایید درست نبود؛ حذف لغو شد و چیزی پاک نشد.", inline([BACK_HOME]))
        return True

    if state == "admin_restore_wait":
        _ask(chat_id, "منتظر فایل پشتیبان (zip) هستم؛ فایل را به‌صورت «ارسال فایل» بفرستید یا انصراف دهید.")
        return True

    if state == "admin_user_del_confirm":
        send_message(chat_id, "برای تایید از دکمه‌ها استفاده کنید یا «❌ انصراف» را بزنید.", confirm_keyboard("adm:udmyes", "cancel"))
        return True

    if state == "admin_book_add":
        if _add_books(chat_id, int(data), text):
            db.clear_user_flow(user_id)
        return True

    if state == "admin_set_rule":
        key, label, min_val = RULE_FIELDS[int(data)]
        val = utils.parse_int(text)
        if val is None or val < min_val or val > 10**9:
            _ask(chat_id, f"لطفاً یک عدد صحیح (حداقل {min_val}) ارسال کنید.\n(برای انصراف: «❌ انصراف»)")
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
            _ask(chat_id, "متن قوانین باید خالی نباشد و حداکثر ۳۵۰۰ حرف باشد. دوباره ارسال کنید:")
            return True
        db.set_rules_text(text)
        db.clear_user_flow(user_id)
        _rules_screen(chat_id, None, note="✅ متن نمایشی قوانین ذخیره شد و از این به بعد به کاربران نشان داده می‌شود.")
        return True

    if state == "admin_set_pw":
        if len(text) < 4 or len(text) > 40:
            _ask(chat_id, "رمز باید بین ۴ تا ۴۰ حرف باشد. دوباره ارسال کنید:")
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
        show_panel(chat_id, message_id, user_id)

    # ---- قوانین ----
    elif action == "rules":
        _rules_screen(chat_id, message_id)

    elif action == "rule":
        idx = _int(parts, 2)
        if idx is None or not (0 <= idx < len(RULE_FIELDS)):
            return
        key, label, min_val = RULE_FIELDS[idx]
        db.set_user_flow(user_id, "admin_set_rule", str(idx))
        _ask(
            chat_id,
            f"{label}\nمقدار فعلی: {db.get_rules()[key]}\n\nمقدار جدید را به صورت عدد ارسال کنید "
            f"(حداقل {min_val}).\n(برای انصراف: «❌ انصراف»)",
        )

    elif action == "ruletext":
        db.set_user_flow(user_id, "admin_set_rules_text")
        current = texts.rules_text(db.get_rules(), db.get_rules_text())
        _ask(
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
        _ask(chat_id, prompts[field] + "\n(برای انصراف: «❌ انصراف»)")

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
        _ask(chat_id, BOOK_FORMAT)

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

    elif action == "bookdelmulti":
        sid = _int(parts, 2)
        if not sid:
            return
        db.set_user_flow(user_id, "admin_book_del_multi", str(sid))
        _ask(chat_id, "شناسه‌ی کتاب‌هایی که می‌خواهید حذف شوند را بفرستید (با فاصله، کاما یا خط جدید؛ بازه هم مجاز است).\n"
                      "مثال: 3 5 7   یا   3-6\n(شناسه‌ها در لیست کتاب‌ها با # نشان داده شده)")

    # ---- کاربران ----
    elif action == "users":
        _users_screen(chat_id, message_id, _int(parts, 2, 0))

    elif action == "userstext":
        _send_users(chat_id)

    elif action == "user":
        _user_screen(chat_id, message_id, _int(parts, 2, 0), _int(parts, 3, 0))

    elif action == "userdel":
        uid, page = _int(parts, 2, 0), _int(parts, 3, 0)
        u = db.get_user(uid)
        if not u:
            _users_screen(chat_id, message_id, page)
            return
        edit_or_send(chat_id, message_id, f"❓ کاربر «{u['full_name']}» حذف شود؟\n\n" + USER_DEL_WARNING,
                     confirm_keyboard(f"adm:userdelyes:{uid}:{page}", f"adm:user:{uid}:{page}"))

    elif action == "userdelyes":
        uid, page = _int(parts, 2, 0), _int(parts, 3, 0)
        if db.get_user(uid):
            _delete_users([uid])
        _users_screen(chat_id, message_id, page)

    elif action == "udmyes":
        flow = db.get_user_flow(user_id)
        if not flow or flow["state"] != "admin_user_del_confirm":
            edit_or_send(chat_id, message_id, "این تایید دیگر معتبر نیست.")
            return
        ids = json.loads(flow["data"])
        db.clear_user_flow(user_id)
        _delete_users(ids)
        edit_or_send(chat_id, message_id, f"🗑 {len(ids)} کاربر حذف شد.", inline([BACK_HOME]))

    # ---- مدیرها ----
    elif action == "admins":
        _admins_screen(chat_id, message_id, user_id)

    elif action in ("admdel", "admdelyes", "admwipe"):
        if not auth.is_super_admin(user_id):
            send_message(chat_id, "فقط مدیر اصلی این کار را می‌تواند انجام دهد.")
            return
        target = _int(parts, 2, 0)
        row = db.get_admin(target)
        if not row or row["is_super"]:
            _admins_screen(chat_id, message_id, user_id)
            return
        name = row["full_name"] or target
        if action == "admdel":
            edit_or_send(chat_id, message_id, f"❓ دسترسی مدیریتی «{name}» لغو شود؟",
                         confirm_keyboard(f"adm:admdelyes:{target}", "adm:admins"))
            return
        if action == "admdelyes":
            db.remove_admin(target)
            try:
                send_message(target, "دسترسی مدیریتی شما در ربات لیگ کتابخوانی لغو شد.")
            except Exception:
                pass
        else:
            db.set_admin_can_wipe(target, not row["can_wipe"])
        _admins_screen(chat_id, message_id, user_id)

    # ---- داده و پشتیبان ----
    elif action == "data":
        _data_screen(chat_id, message_id, user_id)

    elif action == "backup":
        if not auth.is_super_admin(user_id):
            send_message(chat_id, "فقط مدیر اصلی می‌تواند پشتیبان بگیرد.")
            return
        send_message(chat_id, "⏳ در حال ساخت فایل پشتیبان...")
        if not _send_backup(chat_id):
            send_message(chat_id, "❌ ساخت یا ارسال فایل پشتیبان ناموفق بود (لاگ ربات را ببینید).")
        else:
            send_message(chat_id, "✅ فایل پشتیبان ارسال شد. آن را در جای امن نگه دارید.", inline([BACK_HOME]))

    elif action == "restore":
        if not auth.is_super_admin(user_id):
            send_message(chat_id, "فقط مدیر اصلی می‌تواند بازیابی کند.")
            return
        db.set_user_flow(user_id, "admin_restore_wait")
        _ask(chat_id, "♻️ بازیابی از فایل پشتیبان\n\n"
                      "فایل پشتیبان (همان zip که ربات قبلاً داده) را همین‌جا بفرستید.\n"
                      "⚠️ بعد از بررسی فایل، یک پیام تایید می‌بینید و تا تایید نکنید چیزی عوض نمی‌شود.")

    elif action == "restoreyes":
        if not auth.is_super_admin(user_id):
            return
        if not os.path.exists(backup.PENDING_DB):
            edit_or_send(chat_id, message_id, "فایل آماده‌ی بازیابی پیدا نشد؛ دوباره فایل را بفرستید.", inline([BACK_HOME]))
            return
        edit_or_send(chat_id, message_id, "⏳ در حال بازیابی...", None)
        if not _send_backup(chat_id, "🛟 پشتیبان ایمنی از وضعیت قبل از بازیابی"):
            send_message(chat_id, "❌ نتوانستم نسخه‌ی ایمنی از وضعیت فعلی بفرستم؛ برای حفظ امنیت داده‌ها بازیابی انجام نشد.")
            return
        try:
            row = db.get_admin(user_id)
            backup.restore_pending(user_id, row["full_name"] if row else None, True)
        except Exception as e:
            log.exception("restore failed")
            send_message(chat_id, f"❌ بازیابی ناموفق بود: {e}")
            return
        send_message(chat_id, "✅ بازیابی انجام شد؛ همه‌ی اطلاعات به وضعیت فایل پشتیبان برگشت. "
                              "(مرحله‌های نیمه‌تمام کاربران پاک شد.)", inline([BACK_HOME]))

    elif action == "wipe":
        if not auth.can_wipe(user_id):
            send_message(chat_id, "دسترسی ندارید.")
            return
        _wipe_warning_screen(chat_id, message_id)

    elif action == "wipelvl":
        level = parts[2] if len(parts) > 2 else ""
        if level not in ("leagues", "full") or not auth.can_wipe(user_id):
            return
        db.set_user_flow(user_id, "admin_wipe_confirm", level)
        what = "همه‌ی لیگ‌ها و تاریخچه" if level == "leagues" else "همه‌ی لیگ‌ها، تاریخچه و کاربران"
        _ask(chat_id, f"🚨 آخرین هشدار: {what} برای همیشه حذف می‌شود.\n\n"
                      f"اگر مطمئن هستید دقیقاً این عبارت را بنویسید:\n{WIPE_WORD}\n\n"
                      "هر چیز دیگر یا انصراف، حذف را لغو می‌کند.")

    # ---- رمز ----

    elif action == "pw":
        _pw_screen(chat_id, message_id)

    elif action == "pwset":
        db.set_user_flow(user_id, "admin_set_pw")
        _ask(chat_id, "رمز ثبت‌نام جدید را ارسال کنید (۴ تا ۴۰ حرف):\n(برای انصراف: «❌ انصراف»)")

    elif action == "pwclear":
        db.set_registration_password("")
        _pw_screen(chat_id, message_id)
