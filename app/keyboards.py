"""
کیبوردهای شیشه‌ای (inline) و کیبورد متنی اصلی منو.
"""

MAIN_MENU = {
    "keyboard": [
        [{"text": "📖 ثبت مطالعه"}, {"text": "🏆 کارنامه من"}],
        [{"text": "📚 کتاب‌های ویژه این فصل"}, {"text": "❓ راهنما"}],
    ],
    "resize_keyboard": True,
}


def yes_no_children():
    return {
        "inline_keyboard": [
            [
                {"text": "دارم", "callback_data": "children_yes"},
                {"text": "ندارم", "callback_data": "children_no"},
            ]
        ]
    }


def book_choice_keyboard(books, prefix="book_done"):
    rows = [[{"text": b["title"], "callback_data": f"{prefix}:{b['id']}"}] for b in books]
    rows.append([{"text": "هیچ‌کدام / رد شدن", "callback_data": f"{prefix}:skip"}])
    return {"inline_keyboard": rows}


def confirm_keyboard(yes_data: str, no_data: str):
    return {
        "inline_keyboard": [
            [
                {"text": "✅ بله، مطمئنم", "callback_data": yes_data},
                {"text": "❌ انصراف", "callback_data": no_data},
            ]
        ]
    }
