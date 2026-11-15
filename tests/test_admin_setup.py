"""
تست جریان «مدیر اصلی / ادمین با کد مخفی» — بدون تنظیم ADMIN_IDS، یعنی دقیقاً
همان سناریویی که یک ادمین واقعی روی سرور، بدون دانستن آیدی عددی کسی، طی می‌کند:
۱) اولین نفری که ADMIN_SETUP_CODE را بفرستد «مدیر اصلی» می‌شود.
۲) نفر دوم با همان کد فقط «ادمین» عادی می‌شود (نه مدیر اصلی).
۳) فقط مدیر اصلی می‌تواند ادمین عادی را حذف کند؛ خودِ مدیر اصلی حذف‌شدنی نیست.
۴) بعد از حذف، آن فرد دیگر به دستورات ادمین دسترسی ندارد.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["BALE_TOKEN"] = "TEST_TOKEN"
os.environ["ADMIN_IDS"] = ""  # عمدا خالی: هیچ ادمین از قبل تعیین‌شده‌ای نداریم
os.environ["ADMIN_SETUP_CODE"] = "sesame-open-123"
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")

from app import db, handlers  # noqa: E402
from app import bale_api  # noqa: E402

sent_messages = []


def fake_send_message(chat_id, text, reply_markup=None, reply_to_message_id=None):
    sent_messages.append((chat_id, text))
    print(f"--- SEND to {chat_id} ---\n{text}\n")
    return {"ok": True, "result": {"message_id": len(sent_messages)}}


bale_api.send_message = fake_send_message
handlers.send_message = fake_send_message


def msg(user_id, text):
    return {"chat": {"id": user_id}, "from": {"id": user_id, "first_name": "کاربر", "last_name": str(user_id)}, "text": text}


def main():
    db.init_db()

    SUPER = 10
    REGULAR = 20
    OUTSIDER = 30

    print("====== ۱. نفر اول کد مخفی را می‌فرستد -> باید مدیر اصلی شود ======")
    sent_messages.clear()
    handlers.handle_message(msg(SUPER, "sesame-open-123"))
    assert "مدیر اصلی" in sent_messages[-1][1], sent_messages[-1][1]
    assert handlers.is_super_admin(SUPER)
    assert handlers.is_admin(SUPER)
    print("OK: نفر اول مدیر اصلی شد ✅")

    print("====== ۲. نفر دوم همان کد را می‌فرستد -> باید فقط ادمین عادی شود ======")
    sent_messages.clear()
    handlers.handle_message(msg(REGULAR, "sesame-open-123"))
    assert "مدیر اصلی" not in sent_messages[-1][1]
    assert handlers.is_admin(REGULAR)
    assert not handlers.is_super_admin(REGULAR)
    print("OK: نفر دوم فقط ادمین عادی شد ✅")

    print("====== ۳. کسی که کد را نمی‌داند، ادمین نمی‌شود ======")
    sent_messages.clear()
    handlers.handle_message(msg(OUTSIDER, "یه کد الکی"))
    assert not handlers.is_admin(OUTSIDER)
    print("OK ✅")

    print("====== ۴. ادمین عادی اجازه حذف مدیر دیگر را ندارد ======")
    sent_messages.clear()
    handlers.handle_message(msg(REGULAR, f"/حذف_مدیر {SUPER}"))
    assert "فقط مدیر اصلی" in sent_messages[-1][1]
    assert handlers.is_admin(SUPER)
    print("OK ✅")

    print("====== ۵. مدیر اصلی لیست مدیرها را می‌بیند ======")
    sent_messages.clear()
    handlers.handle_message(msg(SUPER, "/لیست_مدیرها"))
    report = sent_messages[-1][1]
    print(report)
    assert str(SUPER) in report and str(REGULAR) in report

    print("====== ۶. مدیر اصلی نمی‌تواند خودش را حذف کند ======")
    sent_messages.clear()
    handlers.handle_message(msg(SUPER, f"/حذف_مدیر {SUPER}"))
    assert "نمی‌توانید خودتان" in sent_messages[-1][1]
    assert handlers.is_admin(SUPER)

    print("====== ۷. مدیر اصلی ادمین عادی را حذف می‌کند ======")
    sent_messages.clear()
    handlers.handle_message(msg(SUPER, f"/حذف_مدیر {REGULAR}"))
    assert "حذف شد" in sent_messages[0][1]
    assert not handlers.is_admin(REGULAR), "ادمین عادی باید بعد از حذف دیگر ادمین نباشد"
    print("OK: ادمین عادی حذف شد و دیگر دسترسی ندارد ✅")

    print("====== ۸. تلاش حذف مدیر اصلی توسط خودش با remove_admin مستقیم هم رد می‌شود (محافظت دیتابیسی) ======")
    removed = db.remove_admin(SUPER)
    assert removed is False, "تابع remove_admin نباید بتواند مدیر اصلی را حذف کند"
    assert handlers.is_super_admin(SUPER)
    print("OK ✅")

    print("\n✅✅✅ همه تست‌های جریان مدیر اصلی/ادمین پاس شدند ✅✅✅")


if __name__ == "__main__":
    main()
