"""
تست دستی کل منطق (دیتابیس + امتیازدهی + هندلرها) بدون نیاز به اتصال واقعی به بله.
sendMessage و توابع شبکه‌ای mock می‌شوند تا فقط منطق تست شود.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["BALE_TOKEN"] = "TEST_TOKEN"
os.environ["ADMIN_IDS"] = "1"
tmp_db = tempfile.mktemp(suffix=".db")
os.environ["DB_PATH"] = tmp_db

from app import db, scoring, handlers  # noqa: E402
from app import bale_api  # noqa: E402

sent_messages = []


def fake_send_message(chat_id, text, reply_markup=None, reply_to_message_id=None):
    sent_messages.append((chat_id, text))
    print(f"--- SEND to {chat_id} ---\n{text}\n")
    return {"ok": True, "result": {"message_id": len(sent_messages)}}


def fake_answer_cb(*a, **k):
    return {"ok": True}


def fake_edit(*a, **k):
    print(f"--- EDIT ---\n{a[2] if len(a) > 2 else k.get('text')}\n")
    return {"ok": True}


bale_api.send_message = fake_send_message
bale_api.answer_callback_query = fake_answer_cb
bale_api.edit_message_text = fake_edit
handlers.send_message = fake_send_message
handlers.answer_callback_query = fake_answer_cb
handlers.edit_message_text = fake_edit


def msg(user_id, text, chat_id=None):
    chat_id = chat_id or user_id
    return {
        "chat": {"id": chat_id},
        "from": {"id": user_id, "first_name": "تست", "last_name": "کاربر"},
        "text": text,
    }


def cb(user_id, data, chat_id=None, message_id=1):
    chat_id = chat_id or user_id
    return {
        "id": "cbid1",
        "data": data,
        "from": {"id": user_id},
        "message": {"chat": {"id": chat_id}, "message_id": message_id},
    }


def main():
    db.init_db()

    ADMIN = 1
    SOGHRA = 2  # دارای فرزند
    MARYAM = 3  # بدون فرزند

    print("====== ۱. ثبت‌نام ادمین به عنوان مدیر (و کاربر عادی) ======")
    handlers.handle_message(msg(ADMIN, "/start"))
    handlers.handle_message(msg(ADMIN, "مدیر سیستم"))
    handlers.handle_callback_query(cb(ADMIN, "children_no"))

    print("====== ۲. شروع فصل جدید توسط ادمین ======")
    handlers.handle_message(msg(ADMIN, "/فصل_جدید پاییز ۱۴۰۴"))
    season = db.get_active_season()
    assert season is not None, "فصل فعال ساخته نشد!"
    print("فصل فعال:", dict(season))

    print("====== ۳. افزودن کتاب ویژه ======")
    handlers.handle_message(msg(ADMIN, "/افزودن_کتاب طرح کلی اندیشه اسلامی در قرآن | 10"))
    books = db.list_books(season["id"])
    assert len(books) == 1
    print("کتاب‌ها:", [dict(b) for b in books])

    print("====== ۴. ثبت‌نام صغری (دارای فرزند) ======")
    handlers.handle_message(msg(SOGHRA, "/start"))
    handlers.handle_message(msg(SOGHRA, "صغری کبرایان‌پور"))
    handlers.handle_callback_query(cb(SOGHRA, "children_yes"))
    u = db.get_user(SOGHRA)
    assert u["has_children"] == 1
    print("کاربر صغری:", dict(u))

    print("====== ۵. ثبت‌نام مریم (بدون فرزند) ======")
    handlers.handle_message(msg(MARYAM, "/start"))
    handlers.handle_message(msg(MARYAM, "مریم احمدی"))
    handlers.handle_callback_query(cb(MARYAM, "children_no"))

    print("====== ۶. ثبت مطالعه صغری: ۶۰ دقیقه ======")
    handlers.handle_message(msg(SOGHRA, "📖 ثبت مطالعه"))
    handlers.handle_message(msg(SOGHRA, "60"))
    # باید پیشنهاد کتاب داده شود چون کتاب ویژه موجود است
    handlers.handle_callback_query(cb(SOGHRA, f"book_done:{books[0]['id']}"))

    minutes = db.total_minutes(SOGHRA, season["id"])
    assert minutes == 60, f"دقیقه اشتباه: {minutes}"
    book_pts = db.book_points_sum(SOGHRA, season["id"])
    assert book_pts == 10, f"امتیاز کتاب اشتباه: {book_pts}"
    points = scoring.capped_points(minutes, True, book_pts)
    # ۶۰ دقیقه / ۲۰ = ۳ امتیاز + ۱۰ امتیاز کتاب = ۱۳
    assert points == 13, f"امتیاز اشتباه: {points} (باید ۱۳ باشد)"
    print(f"امتیاز صغری: {points} (درست است ✅)")

    print("====== ۷. ثبت مطالعه مریم: ۱۲۵ دقیقه (بدون فرزند -> هر ۲۵ دقیقه ۱ امتیاز) ======")
    handlers.handle_message(msg(MARYAM, "📖 ثبت مطالعه"))
    handlers.handle_message(msg(MARYAM, "125"))
    handlers.handle_callback_query(cb(MARYAM, "book_done:skip"))
    m_minutes = db.total_minutes(MARYAM, season["id"])
    m_points = scoring.capped_points(m_minutes, False, 0)
    assert m_points == 5, f"امتیاز مریم اشتباه: {m_points}"
    print(f"امتیاز مریم: {m_points} (درست است ✅)")

    print("====== ۸. کارنامه صغری ======")
    sent_messages.clear()
    handlers.handle_message(msg(SOGHRA, "🏆 کارنامه من"))
    report = sent_messages[-1][1]
    print(report)
    assert "۱۳" in report or "13" in report

    print("====== ۹. تست سقف ۱۵۰ امتیاز: ثبت ۵۰۰۰ دقیقه برای صغری ======")
    db.add_reading_log(SOGHRA, season["id"], 5000)
    minutes2 = db.total_minutes(SOGHRA, season["id"])
    points2 = scoring.capped_points(minutes2, True, 10)
    assert points2 == 150, f"سقف امتیاز رعایت نشد: {points2}"
    print(f"امتیاز بعد از مطالعه زیاد: {points2} (سقف رعایت شد ✅)")

    print("====== ۱۰. گزارش فصل (ادمین) ======")
    sent_messages.clear()
    handlers.handle_message(msg(ADMIN, "/گزارش_فصل"))
    print(sent_messages[-1][1])

    print("====== ۱۱. پایان فصل و قرعه‌کشی ======")
    handlers.handle_message(msg(ADMIN, "/پایان_فصل"))
    handlers.handle_message(msg(ADMIN, "بله پایان فصل"))
    ended = db.get_season(season["id"])
    assert ended["status"] == "ended"
    print("وضعیت فصل بعد از پایان:", dict(ended))

    print("====== ۱۲. بعد از پایان فصل، فصل فعالی نباید وجود داشته باشد ======")
    assert db.get_active_season() is None
    sent_messages.clear()
    handlers.handle_message(msg(SOGHRA, "📖 ثبت مطالعه"))
    assert "فصلی" in sent_messages[-1][1]
    print("پیام مناسب نبود فصل فعال نمایش داده شد ✅")

    print("\n✅✅✅ همه تست‌ها با موفقیت پاس شدند ✅✅✅")


if __name__ == "__main__":
    main()
