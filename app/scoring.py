"""
منطق کدهای قرعه‌کشی و جوایز — بر اساس «طرح لیگ کتابخوانی».
از نسخه ۱.۰ «امتیاز» حذف شده است: دقایق مطالعه مستقیم به کد قرعه‌کشی تبدیل می‌شود و هر کتابِ
تمام‌شده هم تعدادی کد (پیش‌فرض ۱) دارد. همه‌ی اعداد از «قوانین» (rules) خوانده می‌شود که مدیر از داخل بله
تغییرشان می‌دهد (db.get_rules()).
"""
import random


def minutes_per_code(has_children: bool, rules: dict) -> int:
    key = "minutes_per_code_child" if has_children else "minutes_per_code_nochild"
    return max(1, rules[key])


def codes_from_minutes(minutes: int, has_children: bool, rules: dict) -> int:
    """کدِ حاصل از مطالعه (رند به پایین؛ باقیمانده به فصل بعد منتقل نمی‌شود)."""
    return minutes // minutes_per_code(has_children, rules)


def codes_from_books(books_count: int, rules: dict) -> int:
    return books_count * max(0, rules["codes_per_book"])


def total_codes(minutes: int, has_children: bool, books_count: int, rules: dict):
    """(کدِ مطالعه, کدِ کتاب‌ها, مجموع پس از اعمال سقف فصل, آیا به سقف رسیده)"""
    from_minutes = codes_from_minutes(minutes, has_children, rules)
    from_books = codes_from_books(books_count, rules)
    raw = from_minutes + from_books
    cap = max(0, rules["max_codes"])
    return from_minutes, from_books, min(raw, cap), raw >= cap


def minutes_to_next_code(minutes: int, has_children: bool, rules: dict) -> int:
    interval = minutes_per_code(has_children, rules)
    return interval - (minutes % interval)


def prize_per_winner(total_codes_in_pool: int, rules: dict) -> int:
    step = max(1, rules["codes_per_step"])
    bonus = (total_codes_in_pool // step) * rules["bonus_per_step"]
    return min(rules["base_prize"] + bonus, rules["max_prize"])


def codes_to_next_prize_step(total_codes_in_pool: int, rules: dict) -> int:
    step = max(1, rules["codes_per_step"])
    return step - (total_codes_in_pool % step)


def run_lottery(entries: list, rules: dict):
    """
    entries: لیستی از (user_id, تعداد کد) برای کاربرانی که حداقل ۱ کد دارند.
    برمی‌گرداند: (لیست برندگان [user_id, ...], مبلغ جایزه هر برنده, مجموع کدهای شرکت‌کننده در قرعه‌کشی)
    هر کد یک بلیط است؛ هر نفر حداکثر یک‌بار برنده می‌شود.
    """
    total = sum(codes for _, codes in entries)
    prize = prize_per_winner(total, rules)

    pool = []
    for user_id, codes in entries:
        pool.extend([user_id] * codes)

    winners = []
    n_winners = min(max(0, rules["winners"]), len(set(pool)))
    remaining_pool = pool[:]
    while len(winners) < n_winners and remaining_pool:
        pick = random.choice(remaining_pool)
        winners.append(pick)
        remaining_pool = [u for u in remaining_pool if u != pick]

    return winners, prize, total
