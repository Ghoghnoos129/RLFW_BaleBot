"""
منطق امتیازدهی، کدهای قرعه‌کشی و جوایز — بر اساس «طرح لیگ کتابخوانی».
از نسخه ۰.۲ همه‌ی اعداد از «قوانین» (rules) خوانده می‌شوند که مدیر از داخل بله تغییرشان می‌دهد
(db.get_rules()). هر تابع، دیکشنری قوانین را به عنوان آرگومان آخر می‌گیرد.
"""
import random


def minutes_per_point(has_children: bool, rules: dict) -> int:
    key = "minutes_per_point_child" if has_children else "minutes_per_point_nochild"
    return max(1, rules[key])


def points_from_minutes(minutes: int, has_children: bool, rules: dict) -> int:
    return minutes // minutes_per_point(has_children, rules)


def raw_points(minutes: int, has_children: bool, book_points: int, rules: dict) -> int:
    """امتیاز قبل از اعمال سقف فصل."""
    return points_from_minutes(minutes, has_children, rules) + book_points


def capped_points(minutes: int, has_children: bool, book_points: int, rules: dict) -> int:
    return min(raw_points(minutes, has_children, book_points, rules), rules["max_points"])


def minutes_to_next_point(minutes: int, has_children: bool, rules: dict) -> int:
    interval = minutes_per_point(has_children, rules)
    return interval - (minutes % interval)


def codes_from_points(points: int, rules: dict) -> int:
    return points // max(1, rules["points_per_code"])


def points_to_next_code(points: int, rules: dict) -> int:
    ppc = max(1, rules["points_per_code"])
    return ppc - (points % ppc)


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
    total_codes = sum(codes for _, codes in entries)
    prize = prize_per_winner(total_codes, rules)

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

    return winners, prize, total_codes
