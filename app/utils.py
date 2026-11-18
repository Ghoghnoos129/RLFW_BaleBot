"""
ابزارهای کمکی: تبدیل ارقام فارسی، خواندن عدد، شماره کارت، تکه‌کردن پیام‌های بلند.
"""
import re

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


def parse_id_list(text: str, max_range: int = 500):
    """
    فهرست شناسه‌ها را از متن می‌خواند: جداکننده فاصله/کاما/خط جدید، و بازه مثل 3-6.
    برمی‌گرداند: (لیست شناسه‌های یکتا به ترتیب ورود، لیست توکن‌های نامعتبر)
    """
    s = normalize_digits(text or "")
    for ch in ("،", "؛", ";", ","):
        s = s.replace(ch, " ")
    ids, bad = [], []
    for tok in s.split():
        tok = tok.lstrip("#")
        m = re.fullmatch(r"(\d+)[-–—](\d+)", tok)
        if m and tok.isascii():
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b and b - a <= max_range:
                ids.extend(range(a, b + 1))
            else:
                bad.append(tok)
        elif tok.isascii() and tok.isdigit():
            ids.append(int(tok))
        else:
            bad.append(tok)
    return list(dict.fromkeys(ids)), bad
