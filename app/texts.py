"""
متن پیام‌های ربات.
"""
from app import jdate
from app.utils import fmt_money, format_card, mask_card

# ---------- ثبت‌نام ----------

WELCOME = (
    "سلام 🌱\n"
    "به «لیگ کتابخوانی» خوش آمدید.\n\n"
    "این ربات برای ثبت زمان مطالعه و پیگیری کدهای قرعه‌کشی شماست."
)

ASK_PASSWORD = (
    "🔐 برای ثبت‌نام، «رمز ثبت‌نام» را که مدیر لیگ در اختیارتان گذاشته ارسال کنید:"
)
WRONG_PASSWORD = "❌ رمز اشتباه است. ({left} فرصت باقی مانده)\nرمز را از مدیر لیگ بپرسید و دوباره ارسال کنید."
TOO_MANY_ATTEMPTS = "⛔ تعداد تلاش‌های ناموفق زیاد بود. ده دقیقه بعد با /start دوباره تلاش کنید یا با مدیر تماس بگیرید."
REGISTRATION_CLOSED = (
    "ثبت‌نام در حال حاضر باز نیست.\n"
    "برای ثبت‌نام با مدیر لیگ هماهنگ کنید تا رمز ثبت‌نام را به شما بدهد 🙏"
)

ASK_NAME = "نام و نام خانوادگی خودتان را ارسال کنید:"
ASK_SPOUSE = "نام و نام خانوادگی همسرتان را ارسال کنید:"
ASK_CHILDREN = "آیا فرزند دارید؟ (این موضوع در محاسبه کد قرعه‌کشی شما مؤثر است)"
ASK_CARD = (
    "💳 شماره کارت (۱۶ رقمی) خود را برای واریز جایزه (در صورت برنده‌شدن) ارسال کنید.\n\n"
    "⚠️ توجه: شماره کارت باید به نام خودِ شرکت‌کننده یا همسر او باشد."
)
INVALID_CARD = "شماره کارت باید دقیقاً ۱۶ رقم باشد. لطفاً دوباره و فقط با ارقام ارسال کنید."
INVALID_TEXT = "لطفاً پاسخ را به صورت متن (و حداکثر ۸۰ حرف) ارسال کنید."
PROFILE_INCOMPLETE_NOTE = "📝 برای ادامه، چند اطلاعات تکمیلی لازم است (نسخه جدید ربات).\n"
USE_BUTTONS = "لطفاً با دکمه‌های بالا پاسخ دهید 🙏"

REGISTER_DONE = (
    "ثبت‌نام شما با موفقیت انجام شد ✅\n"
    "از منوی پایین می‌توانید مطالعه‌تان را ثبت کنید یا کارنامه‌تان را ببینید."
)
ALREADY_REGISTERED = "شما قبلاً ثبت‌نام کرده‌اید 🙌"
NOT_REGISTERED = "ابتدا باید ثبت‌نام کنید. لطفاً دستور /start را بزنید."
CANCELED = "لغو شد. از منو ادامه دهید 👇"
STALE_BUTTON = "این دکمه دیگر فعال نیست."

# ---------- فصل و مطالعه ----------

NO_ACTIVE_SEASON = (
    "در حال حاضر فصلی از لیگ کتابخوانی فعال نیست.\n"
    "منتظر اعلام مدیر برای شروع فصل جدید بمانید 🙏"
)


def no_active_text(upcoming=None) -> str:
    if upcoming and upcoming["start_date"]:
        return (
            f"در حال حاضر فصلی فعال نیست.\n"
            f"فصل بعدی: «{upcoming['name']}» — شروع از {jdate.to_jalali_str(upcoming['start_date'])} 🌱"
        )
    return NO_ACTIVE_SEASON


ASK_MINUTES = (
    "چند دقیقه مطالعه کردید؟ 📖\n"
    "فقط عدد را ارسال کنید (مثلاً: 30)\n"
    "اگر اشتباهی وارد این بخش شدید، «❌ انصراف» را بنویسید یا یکی از دکمه‌های منو را بزنید."
)
INVALID_MINUTES = (
    "لطفاً فقط یک عدد صحیح و مثبت برای دقیقه مطالعه ارسال کنید.\n"
    "(برای انصراف: «❌ انصراف» یا یکی از دکمه‌های منو)"
)
TOO_MANY_MINUTES = "عدد وارد‌شده بیشتر از {max} دقیقه (۲۴ ساعت) است و در یک ثبت پذیرفته نمی‌شود. لطفاً دوباره بررسی کنید."
MINUTES_SAVED = "✅ {minutes} دقیقه مطالعه برای شما ثبت شد."
ASK_EDIT_MINUTES = "عدد فعلی: {current} دقیقه.\nعدد درست را (به دقیقه) ارسال کنید:\n(برای انصراف: «❌ انصراف»)"
MINUTES_EDITED = "✅ ثبت اصلاح شد: {old} ← {new} دقیقه."
LOG_DELETED = "🗑 این ثبت حذف شد."
NOTHING_TO_EDIT = "در این فصل هنوز مطالعه یا کتابی ثبت نکرده‌اید."

ASK_BOOK_DONE = (
    "آیا یکی از کتاب‌های ویژه‌ی این فصل را به پایان رساندید؟\n"
    "(یادآوری: کد قرعه‌کشی کتاب فقط با مطالعه‌ی کامل آن تعلق می‌گیرد)"
)
NO_BOOKS_THIS_SEASON = "در این فصل هنوز کتاب ویژه‌ای توسط مدیر معرفی نشده است."
BOOK_ALREADY_DONE = "شما قبلاً کد این کتاب را دریافت کرده‌اید."
BOOK_DONE_SAVED = "🎉 آفرین! {codes} کد قرعه‌کشی برای اتمام کتاب «{title}» به شما تعلق گرفت."
BOOK_SKIPPED = "باشد، هر وقت کتابی را تمام کردید از همین‌جا اعلام کنید."
BOOK_UNDONE = "↩️ ثبت اتمام کتاب «{title}» لغو شد."

# ---------- راهنما ----------

HELP_USER = (
    "📘 راهنمای لیگ کتابخوانی\n\n"
    "دکمه‌های منو:\n"
    "📖 ثبت مطالعه — ثبت دقایق مطالعه\n"
    "✏️ اصلاح مطالعه — اصلاح یا حذف عددی که اشتباه وارد کرده‌اید\n"
    "🏆 کارنامه من — میزان مطالعه، کدها و رتبه شما در فصل جاری\n"
    "🏁 وضعیت لیگ — سه نفر اول، جایگاه شما، جایزه لیگ و تعداد شرکت‌کنندگان\n"
    "📚 کتاب‌های ویژه این فصل — لیست کتاب‌های معرفی‌شده (هر کتاب یک کد قرعه‌کشی)\n"
    "📜 قوانین لیگ — نحوه محاسبه کد قرعه‌کشی و جایزه\n"
    "👤 مشخصات من — مشاهده و اصلاح نام، همسر، فرزند و شماره کارت\n"
    "⏰ یادآور مطالعه — ساعتی را انتخاب کنید تا هر روز همان ساعت یادآوری بگیرید\n"
    "🗳 نظرسنجی‌ها — نظرسنجی‌های بازِ لیگ را ببینید و رأی دهید\n\n"
    "دستور /id — نمایش آیدی عددی خودتان در بله\n"
    "اگر در میانه‌ی یک کار پشیمان شدید، «❌ انصراف» را بنویسید."
)

HELP_ADMIN_EXTRA = (
    "\n\n⚙️ مدیریت (فقط ادمین‌ها):\n"
    "دکمه «⚙️ پنل مدیریت» (یا دستور /پنل) همه‌ی کارها را با دکمه انجام می‌دهد: "
    "قوانین و فرمول‌ها، فصل‌ها (با تاریخ شروع و پایان)، کتاب‌های ویژه، گزارش‌ها، کاربران، مدیرها، رمز ثبت‌نام "
    "و (برای مدیر اصلی یا ادمین دارای اجازه) داده و پشتیبان.\n\n"
    "📢 «پیام به کاربران»: ارسال متن، عکس، ویدیو، صوت، ویس یا فایل برای همه (فوری یا زمان‌بندی‌شده)\n"
    "🗳 «نظرسنجی‌ها»: ساخت نظرسنجی با دکمه‌های شیشه‌ای و مهلت دلخواه\n\n"
    "دستورهای میان‌بر:\n"
    "/فصل_جدید <نام> | <تاریخ شروع> | <تاریخ پایان> — مثال: /فصل_جدید پاییز | 1405/08/01 | 1405/10/30\n"
    "/افزودن_کتاب <عنوان> — به فصل فعال (یا نزدیک‌ترین فصل در انتظار). برای چند کتاب، هر کتاب را در یک خط بنویسید\n"
    "/حذف_کتاب <شناسه‌ها> — چند شناسه با فاصله/کاما یا بازه؛ مثال: 3 5 7-9\n"
    "/حذف_کاربر <شناسه‌ها> — حذف یک یا چند کاربر (با تایید)\n"
    "/لیست_کتاب‌ها\n"
    "/گزارش_فصل\n"
    "/پایان_فصل\n"
    "/لیست_کاربران\n"
    "/رمز_ثبت_نام <رمز> — تعیین رمز ثبت‌نام\n"
    "/لیست_مدیرها\n"
    "/حذف_مدیر <آیدی عددی> — فقط مدیر اصلی"
)


def rules_text(rules: dict, custom=None) -> str:
    """متن قوانین لیگ: اگر مدیر متن سفارشی گذاشته همان، وگرنه متن خودکار از روی اعداد قوانین."""
    if custom:
        return "📜 قوانین لیگ کتابخوانی\n\n" + custom
    return (
        "📜 قوانین لیگ کتابخوانی\n\n"
        f"• هر {rules['minutes_per_code_child']} دقیقه مطالعه (برای خانواده‌های دارای فرزند) یا "
        f"{rules['minutes_per_code_nochild']} دقیقه (برای خانواده‌های بدون فرزند) = ۱ کد قرعه‌کشی "
        "(باقیمانده کمتر از آن در پایان فصل حذف می‌شود)\n"
        f"• اتمام کامل هر کتاب ویژه = {rules['codes_per_book']} کد قرعه‌کشی\n"
        f"• سقف کد هر نفر در هر فصل: {rules['max_codes']} کد\n"
        f"• در پایان هر فصل بین دارندگان کد، قرعه‌کشی {rules['winners']} جایزه نقدی انجام می‌شود\n"
        f"• جایزه هر برنده: {fmt_money(rules['base_prize'])} تومان پایه، به‌علاوه "
        f"{fmt_money(rules['bonus_per_step'])} تومان به ازای هر {rules['codes_per_step']} کدِ مجموع "
        f"شرکت‌کنندگان (حداکثر {fmt_money(rules['max_prize'])} تومان)\n"
        "• شماره کارت ثبت‌شده باید به نام شرکت‌کننده یا همسر او باشد\n"
        "• مسابقه فقط مخصوص همسران طلاب و اساتید مدرسه است و مطالعه کتب درسی در آن ثبت نمی‌شود\n"
        "• این مسابقه بر پایه اعتماد و صداقت طراحی شده است"
    )


def books_list_text(books):
    if not books:
        return NO_BOOKS_THIS_SEASON
    lines = ["📚 کتاب‌های ویژه این فصل (اتمام هر کتاب = یک کد قرعه‌کشی):\n"]
    for b in books:
        lines.append(f"• {b['title']}")
    return "\n".join(lines)


def period_text(season) -> str:
    start = season["start_date"] or (season["started_at"] or "")[:10]
    return f"🗓 از {jdate.to_jalali_str(start)} تا {jdate.to_jalali_str(season['end_date'])}"


# ---------- کارنامه ----------

def report_text(*, full_name, spouse_name, has_children, season_name, minutes, completed_books,
                codes_from_minutes, codes_from_books, codes, max_codes, minutes_to_next, rank,
                total_participants, total_prize_so_far, capped):
    children_text = "دارد" if has_children else "بدون فرزند"
    books_txt = "، ".join(b["title"] for b in completed_books) if completed_books else "—"

    if capped:
        next_txt = f"به سقف کد فصل ({max_codes} کد) رسیده‌اید 🎉"
    else:
        next_txt = f"{minutes_to_next} دقیقه"

    rank_txt = f"{rank} از {total_participants}" if rank else "هنوز مطالعه‌ای ثبت نکرده‌اید"

    return (
        f"🏆 کارنامه لیگ کتابخوانی — {season_name}\n\n"
        f"👤 نام و نام خانوادگی: {full_name}\n"
        f"👫 نام همسر: {spouse_name or '—'}\n"
        f"👶 فرزندان: {children_text}\n"
        f"⏱ میزان مطالعه این فصل: {minutes} دقیقه\n"
        f"📚 کتاب‌های تمام‌شده: {books_txt}\n"
        f"🎟 کد از مطالعه: {codes_from_minutes} | کد از کتاب‌ها: {codes_from_books}\n"
        f"🎟 مجموع کدهای قرعه‌کشی: {codes} کد\n"
        f"➕ مطالعه لازم برای کد بعدی: {next_txt}\n"
        f"📊 رتبه در لیگ کتابخوانی ({season_name}): {rank_txt}\n"
        f"💰 جایزه لیگ برای شما تا به الان: {fmt_money(total_prize_so_far)} تومان"
    )


# ---------- وضعیت لیگ ----------

MEDALS = ["🥇", "🥈", "🥉"]


def status_text(season, top3, me, participants_count, registered_count, prize, total_codes, rules):
    lines = [
        f"🏁 وضعیت لیگ — {season['name']}",
        period_text(season),
        "",
        f"👥 شرکت‌کنندگان فصل: {participants_count} نفر (از {registered_count} نفر ثبت‌نام‌شده)",
        "",
        "🏆 سه نفر اول:",
    ]
    if top3:
        for i, r in enumerate(top3):
            lines.append(f"{MEDALS[i]} {r['full_name']} — {r['codes']} کد")
    else:
        lines.append("هنوز کسی مطالعه‌ای ثبت نکرده است.")
    lines.append("")
    if me:
        lines.append(f"📍 جایگاه شما: {me['rank']} از {participants_count} — {me['minutes']} دقیقه، {me['codes']} کد")
    else:
        lines.append("📍 جایگاه شما: هنوز مطالعه‌ای در این فصل ثبت نکرده‌اید.")
    lines.append("")
    lines.append(f"🎁 جایزه لیگ: {fmt_money(prize)} تومان برای هر برنده ({rules['winners']} برنده)")
    lines.append(f"🎟 مجموع کدهای شرکت‌کنندگان: {total_codes}")
    if prize < rules["max_prize"]:
        from app import scoring
        need = scoring.codes_to_next_prize_step(total_codes, rules)
        lines.append(
            f"📈 با {need} کد دیگر، جایزه هر برنده {fmt_money(rules['bonus_per_step'])} تومان افزایش می‌یابد."
        )
    return "\n".join(lines)


# ---------- مشخصات ----------

def profile_text(u) -> str:
    username = f"@{u['username']}" if u["username"] else "—"
    return (
        "👤 مشخصات شما\n\n"
        f"نام و نام خانوادگی: {u['full_name'] or '—'}\n"
        f"نام همسر: {u['spouse_name'] or '—'}\n"
        f"فرزند: {'دارم' if u['has_children'] else 'ندارم'}\n"
        f"شماره کارت: {mask_card(u['card_number'])}\n"
        f"آیدی بله: {username}\n\n"
        "برای اصلاح هر مورد، دکمه‌ی آن را بزنید."
    )


# ---------- اعلان‌های همگانی ----------

def season_start_broadcast(season, prize, rules) -> str:
    return (
        f"🚀 «{season['name']}» لیگ کتابخوانی شروع شد!\n"
        f"{period_text(season)}\n\n"
        f"🎁 جایزه فعلی هر برنده: {fmt_money(prize)} تومان ({rules['winners']} برنده)\n"
        "از دکمه «📖 ثبت مطالعه» مطالعه‌تان را ثبت کنید و از «📜 قوانین لیگ» جزئیات را ببینید.\n"
        "موفق باشید 🌱"
    )


def season_end_broadcast(season, winner_names, prize, participants_count) -> str:
    lines = [
        f"🏁 «{season['name']}» لیگ کتابخوانی به پایان رسید!",
        f"👥 تعداد شرکت‌کنندگان: {participants_count} نفر",
    ]
    if winner_names:
        lines.append(f"\n🎉 برندگان قرعه‌کشی (جایزه هر نفر: {fmt_money(prize)} تومان):")
        for n in winner_names:
            lines.append(f"🏆 {n}")
        lines.append("\nبه برندگان تبریک می‌گوییم! مدیر برای واریز جایزه با آن‌ها هماهنگ می‌کند.")
    else:
        lines.append("\nدر این فصل کسی کد قرعه‌کشی کسب نکرد و قرعه‌کشی انجام نشد.")
    lines.append("\nمنتظر اعلام فصل بعد باشید 🌱")
    return "\n".join(lines)


def prize_increase_broadcast(season, old, new, total_codes) -> str:
    return (
        "🎁 خبر خوب! جایزه لیگ افزایش یافت!\n\n"
        f"جایزه هر برنده در «{season['name']}»: {fmt_money(old)} ← {fmt_money(new)} تومان\n"
        f"🎟 مجموع کدهای شرکت‌کنندگان: {total_codes}\n"
        "مطالعه‌تان را ادامه دهید 📖"
    )


def winner_private(season, prize) -> str:
    return (
        f"🎉 تبریک! شما در قرعه‌کشی لیگ کتابخوانی «{season['name']}» برنده "
        f"{fmt_money(prize)} تومان جایزه شدید. مدیر به زودی با شما هماهنگ می‌کند."
    )


def winner_detail_lines(i, u) -> list:
    """مشخصات برنده برای مدیر (برای هماهنگی و واریز جایزه)."""
    username = f"@{u['username']}" if u["username"] else "ندارد"
    return [
        f"{i}) {u['full_name'] or '—'} (همسر: {u['spouse_name'] or '—'})",
        f"   🆔 آیدی بله: {username} | شناسه عددی: {u['user_id']}",
        f"   💳 شماره کارت: {format_card(u['card_number']) if u['card_number'] else 'ثبت نشده'}",
    ]


def season_end_admin(season, winner_rows, prize, total_codes, participants_count) -> str:
    lines = [
        f"🔔 نتیجه پایان «{season['name']}»",
        f"👥 شرکت‌کنندگان: {participants_count} نفر | 🎟 مجموع کدها: {total_codes}",
    ]
    if not winner_rows:
        lines.append("هیچ‌کس کد قرعه‌کشی نداشت؛ قرعه‌کشی انجام نشد.")
        return "\n".join(lines)
    lines.append(f"💰 جایزه هر برنده: {fmt_money(prize)} تومان\n")
    lines.append("🏆 برندگان (مشخصات برای هماهنگی و واریز):")
    for i, u in enumerate(winner_rows, start=1):
        lines.extend(winner_detail_lines(i, u))
    return "\n".join(lines)
