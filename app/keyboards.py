"""
کیبوردهای شیشه‌ای (inline) و کیبورد متنی اصلی منو.
"""

BTN_LOG = "📖 ثبت مطالعه"
BTN_EDIT = "✏️ اصلاح مطالعه"
BTN_REPORT = "🏆 کارنامه من"
BTN_STATUS = "🏁 وضعیت لیگ"
BTN_BOOKS = "📚 کتاب‌های ویژه این فصل"
BTN_RULES = "📜 قوانین لیگ"
BTN_PROFILE = "👤 مشخصات من"
BTN_HELP = "❓ راهنما"
BTN_ADMIN = "⚙️ پنل مدیریت"

ALL_BUTTONS = {
    BTN_LOG, BTN_EDIT, BTN_REPORT, BTN_STATUS, BTN_BOOKS,
    BTN_RULES, BTN_PROFILE, BTN_HELP, BTN_ADMIN,
}


def main_menu(is_admin: bool = False) -> dict:
    rows = [
        [{"text": BTN_LOG}, {"text": BTN_EDIT}],
        [{"text": BTN_REPORT}, {"text": BTN_STATUS}],
        [{"text": BTN_BOOKS}, {"text": BTN_RULES}],
        [{"text": BTN_PROFILE}, {"text": BTN_HELP}],
    ]
    if is_admin:
        rows.append([{"text": BTN_ADMIN}])
    return {"keyboard": rows, "resize_keyboard": True}


def inline(rows) -> dict:
    """rows: لیستی از ردیف‌ها؛ هر ردیف لیستی از (متن, callback_data)."""
    return {
        "inline_keyboard": [
            [{"text": text, "callback_data": data} for text, data in row] for row in rows
        ]
    }


CANCEL_DATA = "cancel"


def cancel_kb() -> dict:
    """دکمه‌ی شیشه‌ای «انصراف» زیر هر پرسشی که ربات از کاربر/مدیر می‌پرسد."""
    return inline([[("❌ انصراف", CANCEL_DATA)]])


def yes_no_children(prefix: str = "children"):
    return inline([[("دارم", f"{prefix}_yes"), ("ندارم", f"{prefix}_no")],
                   [("❌ انصراف", CANCEL_DATA)]])


def book_choice_keyboard(books, prefix="book_done"):
    rows = [[{"text": b["title"], "callback_data": f"{prefix}:{b['id']}"}] for b in books]
    rows.append([{"text": "هیچ‌کدام / رد شدن", "callback_data": f"{prefix}:skip"}])
    return {"inline_keyboard": rows}


def confirm_keyboard(yes_data: str, no_data: str):
    return inline([[("✅ بله، مطمئنم", yes_data), ("❌ انصراف", no_data)]])
