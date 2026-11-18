"""
تشخیص نقش مدیر و نام نمایشی کاربر.
"""
from app import db
from app.config import ADMIN_IDS


def is_super_admin(user_id: int) -> bool:
    """مدیر اصلی: کسی که در ADMIN_IDS (.env) است، یا اولین نفری که با کد مخفی ثبت‌نام کرده."""
    return user_id in ADMIN_IDS or db.is_db_super_admin(user_id)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS or db.is_db_admin(user_id)


def admin_ids() -> set:
    ids = set(ADMIN_IDS)
    ids.update(a["user_id"] for a in db.list_admins())
    return ids


def user_display_name(tg_user: dict) -> str:
    first = tg_user.get("first_name", "") or ""
    last = tg_user.get("last_name", "") or ""
    full = f"{first} {last}".strip()
    return full or str(tg_user.get("id"))
