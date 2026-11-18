"""
ابزارهای کمکی: تبدیل ارقام فارسی، خواندن عدد، شماره کارت، تکه‌کردن پیام‌های بلند.
"""

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits(s) -> str:
    """ارقام فارسی و عربی را به انگلیسی تبدیل می‌کند."""
    return (s or "").translate(_DIGITS)


def parse_int(s):
    """عدد صحیح نامنفی را از متن کاربر می‌خواند (ارقام فارسی و جداکننده هزارگان مجاز است)؛ وگرنه None."""
    s = normalize_digits(s).strip()
    for ch in (",", "،", "٬", " ", "_", "‌"):
        s = s.replace(ch, "")
    if s and s.isascii() and s.isdigit():
        return int(s)
    return None


def parse_card(s):
    """شماره کارت ۱۶ رقمی را برمی‌گرداند (فقط ارقام)؛ اگر معتبر نبود None."""
    s = normalize_digits(s)
    for ch in (" ", "-", "_", ".", "‌", "‏", "‎"):
        s = s.replace(ch, "")
    if len(s) == 16 and s.isascii() and s.isdigit():
        return s
    return None


def format_card(card: str) -> str:
    card = card or ""
    return " ".join(card[i:i + 4] for i in range(0, len(card), 4))


def mask_card(card: str) -> str:
    if not card:
        return "—"
    return "•••• •••• •••• " + card[-4:]


def fmt_money(n) -> str:
    return f"{int(n or 0):,}"


def split_text(text: str, limit: int = 3500):
    """متن بلند را روی مرز خط‌ها به تکه‌های کوچک‌تر از limit تقسیم می‌کند (محدودیت پیام بله)."""
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) + 1 > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return chunks
