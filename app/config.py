"""
تنظیمات ربات: همه مقادیر از فایل .env خوانده می‌شوند.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _parse_admin_ids(raw: str) -> set[int]:
    ids = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


BALE_TOKEN = os.getenv("BALE_TOKEN", "").strip()

# روش قدیمی/پیشرفته: اگر از قبل آیدی عددی ادمین را می‌دانید می‌توانید اینجا هم بگذارید.
# روش ساده و پیشنهادی: ADMIN_SETUP_CODE را پایین‌تر ببینید — نیازی به دانستن آیدی عددی نیست.
ADMIN_IDS = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))

# کد مخفی ادمین: هر کس این رشته را عیناً به ربات پیام بدهد، به‌صورت خودکار ادمین می‌شود.
# بعد از اینکه مدیر(ها) را اضافه کردید، برای امنیت بیشتر پیشنهاد می‌شود این مقدار را از
# .env پاک یا عوض کنید تا دیگران نتوانند با همان کد خودشان را ادمین کنند.
ADMIN_SETUP_CODE = os.getenv("ADMIN_SETUP_CODE", "").strip()

DB_PATH = os.getenv("DB_PATH", "./data/league.db")
LOG_PATH = os.getenv("LOG_PATH", "./data/bot.log")
HEARTBEAT_PATH = os.getenv("HEARTBEAT_PATH", "./data/heartbeat")
SEASON_PREFIX = os.getenv("DEFAULT_SEASON_PREFIX", "فصل")

VERSION = "0.3"

API_BASE = f"https://tapi.bale.ai/bot{BALE_TOKEN}"

# رمز ثبت‌نام کاربران (مقدار اولیه). مدیر بعداً می‌تواند آن را از «پنل مدیریت ← رمز ثبت‌نام» در بله
# تغییر دهد؛ مقدار تعیین‌شده در بله بر این مقدار اولویت دارد. اگر رمزی تعیین نشده باشد ثبت‌نام بسته است.
REGISTRATION_PASSWORD = os.getenv("REGISTRATION_PASSWORD", "").strip()

# حداکثر دقیقه مجاز در هر بار ثبت مطالعه (برای جلوگیری از اشتباه تایپی؛ ۲۴ ساعت)
MAX_MINUTES_PER_ENTRY = 1440

# --- مقادیر پیش‌فرض قوانین لیگ (طبق طرح) ---
# از نسخه ۰.۲ مدیر می‌تواند همه این مقادیر را از داخل بله (پنل مدیریت ← قوانین و فرمول‌ها) تغییر دهد.
# مقدار تغییرداده‌شده در دیتابیس ذخیره می‌شود و بر این پیش‌فرض‌ها اولویت دارد.
DEFAULT_RULES = {
    "minutes_per_point_child": 20,     # دقیقه مطالعه برای هر امتیاز (دارای فرزند)
    "minutes_per_point_nochild": 25,   # دقیقه مطالعه برای هر امتیاز (بدون فرزند)
    "max_points": 150,                 # سقف امتیاز هر فصل
    "points_per_code": 5,              # امتیاز لازم برای هر کد قرعه‌کشی
    "base_prize": 500_000,             # جایزه پایه هر برنده (تومان)
    "bonus_per_step": 100_000,         # افزایش جایزه هر برنده به ازای هر پله (تومان)
    "codes_per_step": 10,              # هر چند کد (مجموع شرکت‌کنندگان) یک پله افزایش جایزه است
    "max_prize": 1_500_000,            # سقف جایزه هر برنده (تومان)
    "winners": 2,                      # تعداد برندگان قرعه‌کشی
}

if not BALE_TOKEN:
    raise SystemExit(
        "خطا: BALE_TOKEN تنظیم نشده است. فایل .env را بر اساس .env.example بسازید و توکن ربات را در آن قرار دهید."
    )
