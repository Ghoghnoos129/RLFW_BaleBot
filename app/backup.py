"""
پشتیبان‌گیری و بازیابی کل دیتابیس لیگ.
فایل پشتیبان یک zip است شامل league.db (کپی سازگار SQLite) و backup_info.json.
⚠️ فایل پشتیبان شامل شماره کارت و آیدی کاربران است؛ فقط برای مدیر اصلی ارسال می‌شود.
"""
import json
import logging
import os
import sqlite3
import zipfile

from app import __version__, db, jdate
from app.config import DB_PATH

log = logging.getLogger("backup")

DATA_DIR = os.path.dirname(os.path.abspath(DB_PATH)) or "."
TMP_DIR = os.path.join(DATA_DIR, "tmp")
PENDING_ZIP = os.path.join(TMP_DIR, "restore_upload.zip")
PENDING_DB = os.path.join(TMP_DIR, "restore_pending.db")
MAX_DB_BYTES = 200 * 1024 * 1024
REQUIRED_TABLES = {
    "users", "admins", "seasons", "special_books", "reading_logs",
    "book_completions", "season_results",
}


def _ensure_tmp():
    os.makedirs(TMP_DIR, exist_ok=True)


def create_backup() -> str:
    """فایل پشتیبان می‌سازد و مسیر zip را برمی‌گرداند (فراخوان بعد از ارسال، آن را پاک می‌کند)."""
    _ensure_tmp()
    stamp = jdate.now_tehran().strftime("%Y%m%d_%H%M%S")
    snap = os.path.join(TMP_DIR, f"snapshot_{stamp}.db")
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(snap)
    try:
        src.backup(dst)   # کپی سازگار حتی وقتی ربات در حال کار است
    finally:
        dst.close()
        src.close()
    info = {
        "app": "RLFW_BaleBot",
        "version": __version__,
        "created_at_tehran": jdate.now_iso(),
    }
    out = os.path.join(TMP_DIR, f"RLFW_backup_{stamp}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(snap, "league.db")
        z.writestr("backup_info.json", json.dumps(info, ensure_ascii=False, indent=2))
    os.remove(snap)
    return out


def remove_quietly(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def inspect_upload(zip_path: str) -> dict:
    """
    zip آپلودشده را بررسی می‌کند و league.db را در PENDING_DB می‌گذارد (هنوز جایگزین نمی‌شود).
    خلاصه‌ی محتوای پشتیبان را برمی‌گرداند؛ اگر معتبر نبود ValueError با پیام فارسی می‌دهد.
    """
    _ensure_tmp()
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            if "league.db" not in names:
                raise ValueError("این فایل، پشتیبان ربات لیگ نیست (league.db داخلش نیست).")
            if z.getinfo("league.db").file_size > MAX_DB_BYTES:
                raise ValueError("حجم فایل پشتیبان بیش از حد مجاز است.")
            with z.open("league.db") as src, open(PENDING_DB, "wb") as dst:
                dst.write(src.read(MAX_DB_BYTES + 1))
            info = {}
            if "backup_info.json" in names:
                try:
                    info = json.loads(z.read("backup_info.json").decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    info = {}
    except zipfile.BadZipFile:
        raise ValueError("فایل ارسالی zip معتبر نیست. همان فایل پشتیبانی را بفرستید که ربات به شما داده بود.")

    try:
        conn = sqlite3.connect(f"file:{PENDING_DB}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("دیتابیس داخل فایل پشتیبان سالم نیست.")
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not REQUIRED_TABLES <= tables:
                raise ValueError("ساختار دیتابیس داخل فایل پشتیبان با این ربات سازگار نیست.")
            count = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            seasons = [r[0] for r in conn.execute("SELECT name FROM seasons ORDER BY id")]
            return {
                "created_at": info.get("created_at_tehran"),
                "version": info.get("version", "؟"),
                "users": count("users"),
                "seasons": seasons,
                "logs": count("reading_logs"),
            }
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        remove_quietly(PENDING_DB)
        raise ValueError("فایل پشتیبان قابل خواندن نیست.")


def restore_pending(actor_id: int, actor_name: str = None, actor_was_super: bool = False):
    """
    محتوای PENDING_DB را به‌جای دیتابیس فعلی می‌گذارد.
    - شمارنده‌ی آپدیت‌های بله حفظ می‌شود (تا پیام‌های قدیمی دوباره پردازش نشوند)
    - مرحله‌های نیمه‌تمام همه‌ی کاربران پاک می‌شود
    - مدیر اصلیِ بازیابی‌کننده حتماً مدیر اصلی می‌ماند (حتی اگر در فایل پشتیبان نبوده)
    """
    if not os.path.exists(PENDING_DB):
        raise ValueError("فایل پشتیبان آماده‌ی بازیابی پیدا نشد؛ دوباره فایل را بفرستید.")
    offset = db.get_state("update_offset")
    src = sqlite3.connect(PENDING_DB)
    dst = sqlite3.connect(DB_PATH)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    db.init_db()   # اگر پشتیبان از نسخه‌ی قدیمی‌تر است، ستون‌های جدید اضافه می‌شود
    with db.get_conn() as conn:
        conn.execute("DELETE FROM user_state")
    if offset:
        db.set_state("update_offset", offset)
    if actor_was_super and not db.is_db_super_admin(actor_id):
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO admins(user_id, full_name, is_super, added_at) VALUES (?, ?, 1, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET is_super=1",
                (actor_id, actor_name, db.now()),
            )
    remove_quietly(PENDING_DB, PENDING_ZIP)
