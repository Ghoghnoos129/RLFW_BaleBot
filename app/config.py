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

API_BASE = f"https://tapi.bale.ai/bot{BALE_TOKEN}"

# --- قوانین امتیازدهی لیگ کتابخوانی (طبق طرح) ---
MINUTES_PER_POINT_WITH_CHILD = 20
MINUTES_PER_POINT_NO_CHILD = 25
MAX_POINTS_PER_SEASON = 150
POINTS_PER_CODE = 5

# --- قوانین جایزه ---
BASE_PRIZE = 500_000
BONUS_PER_10_CODES = 100_000
MAX_PRIZE_PER_WINNER = 1_500_000
NUMBER_OF_WINNERS = 2

if not BALE_TOKEN:
    raise SystemExit(
        "خطا: BALE_TOKEN تنظیم نشده است. فایل .env را بر اساس .env.example بسازید و توکن ربات را در آن قرار دهید."
    )
