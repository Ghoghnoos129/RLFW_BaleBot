"""
تاریخ شمسی (جلالی) و زمان تهران — بدون وابستگی خارجی.
همه تاریخ‌ها در دیتابیس به صورت میلادی (YYYY-MM-DD) ذخیره می‌شوند و به کاربر شمسی نمایش داده می‌شوند.
مدیر تاریخ را شمسی وارد می‌کند (مثال: 1405/08/01) یا کلمه «امروز».
"""
import datetime as dt
import re

from app.utils import normalize_digits

# ایران ساعت تابستانی ندارد؛ ثابت UTC+03:30
TEHRAN = dt.timezone(dt.timedelta(hours=3, minutes=30))


def now_tehran() -> dt.datetime:
    return dt.datetime.now(TEHRAN)


def now_iso() -> str:
    return now_tehran().replace(tzinfo=None).isoformat(timespec="seconds")


def today_iso() -> str:
    return now_tehran().date().isoformat()


def gregorian_to_jalali(gy: int, gm: int, gd: int):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
            - 80 + gd + g_d_m[gm - 1])
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int):
    if jy > 979:
        gy = 1600
        jy -= 979
    else:
        gy = 621
    days = (365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + 78 + jd
            + ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186))
    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    months = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > months[gm]:
        gd -= months[gm]
        gm += 1
    return gy, gm, gd


def to_jalali_str(value) -> str:
    """'2026-11-18' یا '2026-11-18T08:55:00' → '1405/08/27'. برای مقدار خالی «—»."""
    if not value:
        return "—"
    try:
        d = dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"


def fmt_datetime(value) -> str:
    """'2026-11-18T08:55:00' → '1405/08/27 08:55'."""
    if not value:
        return "—"
    s = str(value)
    time_part = s[11:16] if len(s) >= 16 else ""
    return f"{to_jalali_str(s)} {time_part}".strip()


def parse_date(text: str):
    """
    تاریخ ورودی مدیر را به ISO میلادی برمی‌گرداند؛ اگر نامعتبر بود None.
    پذیرفته: 1405/08/01 ، ۱۴۰۵-۸-۱ ، «امروز» ، و تاریخ میلادی مثل 2026/11/22
    """
    t = normalize_digits(text or "").strip()
    if t in ("امروز", "today"):
        return today_iso()
    parts = re.split(r"[/\-\.]", t)
    if len(parts) != 3 or not all(p.strip().isdigit() for p in parts):
        return None
    y, m, d = (int(p) for p in parts)
    try:
        if y >= 1700:
            return dt.date(y, m, d).isoformat()
        if not (1300 <= y <= 1600 and 1 <= m <= 12 and 1 <= d <= 31):
            return None
        gy, gm, gd = jalali_to_gregorian(y, m, d)
        if gregorian_to_jalali(gy, gm, gd) != (y, m, d):
            return None  # مثلاً ۳۱ در ماه‌های ۳۰ روزه
        return dt.date(gy, gm, gd).isoformat()
    except ValueError:
        return None


def add_hours_iso(hours: float) -> str:
    """زمان (به وقت تهران) چند ساعت بعد، به‌صورت ISO بدون منطقه‌ی زمانی."""
    t = now_tehran() + dt.timedelta(hours=hours)
    return t.replace(tzinfo=None).isoformat(timespec="seconds")


def parse_datetime(text: str):
    """
    «1405/09/10 18:30» (تاریخ شمسی + ساعت) → '2026-12-01T18:30:00' (وقت تهران)؛ نامعتبر → None.
    ساعت می‌تواند با «:» یا «.» نوشته شود؛ اگر ساعت نیامد، ۰۰:۰۰ در نظر گرفته می‌شود.
    """
    t = normalize_digits(text or "").strip()
    parts = t.split()
    if not parts or len(parts) > 2:
        return None
    date_iso = parse_date(parts[0])
    if not date_iso:
        return None
    hh, mm = 0, 0
    if len(parts) == 2:
        m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", parts[1])
        if not m:
            return None
        hh, mm = int(m.group(1)), int(m.group(2))
        if hh > 23 or mm > 59:
            return None
    return f"{date_iso}T{hh:02d}:{mm:02d}:00"


def parse_hhmm(text: str):
    """'18:30' یا '۱۸.۳۰' یا '7' → '18:30' / '07:00'؛ نامعتبر → None."""
    t = normalize_digits(text or "").strip()
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?", t)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2) or 0)
    if hh > 23 or mm > 59:
        return None
    return f"{hh:02d}:{mm:02d}"
