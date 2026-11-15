"""
منطق امتیازدهی، کدهای قرعه‌کشی و جوایز — دقیقاً بر اساس «طرح لیگ کتابخوانی».
"""
import random

from app.config import (
    MINUTES_PER_POINT_WITH_CHILD,
    MINUTES_PER_POINT_NO_CHILD,
    MAX_POINTS_PER_SEASON,
    POINTS_PER_CODE,
    BASE_PRIZE,
    BONUS_PER_10_CODES,
    MAX_PRIZE_PER_WINNER,
    NUMBER_OF_WINNERS,
)


def minutes_per_point(has_children: bool) -> int:
    return MINUTES_PER_POINT_WITH_CHILD if has_children else MINUTES_PER_POINT_NO_CHILD


def points_from_minutes(minutes: int, has_children: bool) -> int:
    return minutes // minutes_per_point(has_children)


def raw_points(minutes: int, has_children: bool, book_points: int) -> int:
    """امتیاز قبل از اعمال سقف ۱۵۰."""
    return points_from_minutes(minutes, has_children) + book_points


def capped_points(minutes: int, has_children: bool, book_points: int) -> int:
    return min(raw_points(minutes, has_children, book_points), MAX_POINTS_PER_SEASON)


def minutes_to_next_point(minutes: int, has_children: bool) -> int:
    interval = minutes_per_point(has_children)
    remainder = minutes % interval
    return interval - remainder


def codes_from_points(points: int) -> int:
    return points // POINTS_PER_CODE


def points_to_next_code(points: int) -> int:
    remainder = points % POINTS_PER_CODE
    return POINTS_PER_CODE - remainder


def prize_per_winner(total_codes_in_pool: int) -> int:
    bonus = (total_codes_in_pool // 10) * BONUS_PER_10_CODES
    return min(BASE_PRIZE + bonus, MAX_PRIZE_PER_WINNER)


def run_lottery(entries: list[tuple[int, int]]):
    """
    entries: لیستی از (user_id, تعداد کد) برای کاربرانی که حداقل ۱ کد دارند.
    برمی‌گرداند: (لیست برندگان [user_id, ...], مبلغ جایزه هر برنده, مجموع کدهای شرکت‌کننده در قرعه‌کشی)
    """
    total_codes = sum(codes for _, codes in entries)
    prize = prize_per_winner(total_codes)

    pool = []
    for user_id, codes in entries:
        pool.extend([user_id] * codes)

    winners = []
    n_winners = min(NUMBER_OF_WINNERS, len(set(pool)))
    remaining_pool = pool[:]
    while len(winners) < n_winners and remaining_pool:
        pick = random.choice(remaining_pool)
        winners.append(pick)
        remaining_pool = [u for u in remaining_pool if u != pick]

    return winners, prize, total_codes
