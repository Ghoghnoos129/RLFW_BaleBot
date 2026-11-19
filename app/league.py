"""
منطق لیگ: رتبه‌بندی، کارنامه، شروع/پایان فصل، قرعه‌کشی، اعلان‌های همگانی و افزایش جایزه.
"""
import logging
import time

from app import auth, bale_api, db, jdate, scoring, texts
from app.utils import split_text

log = logging.getLogger("league")


# ============================================================
#  رتبه‌بندی
# ============================================================

def compute_standings(season_id: int, rules: dict = None) -> list:
    """لیست شرکت‌کنندگان فصل، مرتب بر اساس امتیاز (و در تساوی: دقیقه مطالعه بیشتر)."""
    rules = rules or db.get_rules()
    rows = []
    for p in db.season_participants(season_id):
        minutes = db.total_minutes(p["user_id"], season_id)
        book_pts = db.book_points_sum(p["user_id"], season_id)
        has_children = bool(p["has_children"])
        raw = scoring.raw_points(minutes, has_children, book_pts, rules)
        points = min(raw, rules["max_points"])
        rows.append({
            "user_id": p["user_id"],
            "full_name": p["full_name"] or str(p["user_id"]),
            "spouse_name": p["spouse_name"],
            "has_children": has_children,
            "minutes": minutes,
            "book_points": book_pts,
            "points": points,
            "codes": scoring.codes_from_points(points, rules),
            "capped": raw >= rules["max_points"],
        })
    rows.sort(key=lambda r: (-r["points"], -r["minutes"], r["user_id"]))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows


def current_prize(season_id: int, rules: dict = None):
    """(جایزه فعلی هر برنده، مجموع کدها، رتبه‌بندی)"""
    rules = rules or db.get_rules()
    standings = compute_standings(season_id, rules)
    total_codes = sum(r["codes"] for r in standings)
    return scoring.prize_per_winner(total_codes, rules), total_codes, standings


# ============================================================
#  کارنامه و وضعیت لیگ برای کاربر
# ============================================================

def build_report(user_row, season_row) -> str:
    user_id = user_row["user_id"]
    season_id = season_row["id"]
    rules = db.get_rules()
    has_children = bool(user_row["has_children"])

    minutes = db.total_minutes(user_id, season_id)
    book_pts = db.book_points_sum(user_id, season_id)
    books = db.completed_books(user_id, season_id)

    raw = scoring.raw_points(minutes, has_children, book_pts, rules)
    points = min(raw, rules["max_points"])
    standings = compute_standings(season_id, rules)
    me = next((r for r in standings if r["user_id"] == user_id), None)

    return texts.report_text(
        full_name=user_row["full_name"] or str(user_id),
        spouse_name=user_row["spouse_name"],
        has_children=has_children,
        season_name=season_row["name"],
        minutes=minutes,
        completed_books=books,
        points=points,
        minutes_to_next=scoring.minutes_to_next_point(minutes, has_children, rules),
        codes=scoring.codes_from_points(points, rules),
        points_to_next_code=scoring.points_to_next_code(points, rules),
        rank=me["rank"] if me else None,
        total_participants=len(standings) or 1,
        total_prize_so_far=db.total_prize_won(user_id),
        capped=raw >= rules["max_points"],
    )


def build_status(user_id: int) -> str:
    season = db.get_active_season()
    if not season:
        return texts.no_active_text(db.get_upcoming_season())
    rules = db.get_rules()
    prize, total_codes, standings = current_prize(season["id"], rules)
    me = next((r for r in standings if r["user_id"] == user_id), None)
    return texts.status_text(
        season, standings[:3], me, len(standings), db.count_users(), prize, total_codes, rules
    )


# ============================================================
#  ارسال پیام همگانی
# ============================================================

def recipient_ids() -> set:
    ids = {u["user_id"] for u in db.all_users()}
    ids |= auth.admin_ids()
    return ids


def broadcast(text: str, ids=None, reply_markup=None) -> int:
    """پیام را برای همه‌ی کاربران ثبت‌نام‌شده و مدیرها (یا ids) می‌فرستد. تعداد ارسال موفق را برمی‌گرداند."""
    ids = recipient_ids() if ids is None else ids
    sent = 0
    for uid in sorted(ids):
        try:
            ok = True
            chunks = split_text(text)
            for i, chunk in enumerate(chunks):
                markup = reply_markup if i == len(chunks) - 1 else None
                ok = bale_api.send_message(uid, chunk, reply_markup=markup).get("ok", False) and ok
            sent += 1 if ok else 0
        except Exception:
            log.warning("broadcast failed for %s", uid)
        time.sleep(0.05)  # فاصله کوتاه برای رعایت محدودیت نرخ ارسال
    log.info("broadcast sent to %s/%s users", sent, len(ids))
    return sent


def notify_admins(text: str):
    broadcast(text, ids=auth.admin_ids())


# ============================================================
#  افزایش جایزه
# ============================================================

def check_prize_increase(season_id: int, reset_lower: bool = False):
    """
    اگر جایزه‌ی فعلی هر برنده از آخرین مقدار اعلام‌شده بیشتر شده باشد، به همه پیام می‌دهد.
    reset_lower: وقتی مدیر قوانین را تغییر داده، مقدار اعلام‌شده بدون پیام به جایزه‌ی کمتر هم به‌روز می‌شود.
    """
    season = db.get_season(season_id)
    if not season or season["status"] != "active":
        return
    prize, total_codes, _ = current_prize(season_id)
    announced = season["announced_prize"]
    if announced is None:
        db.update_season(season_id, announced_prize=prize)
    elif prize > announced:
        db.update_season(season_id, announced_prize=prize)
        broadcast(texts.prize_increase_broadcast(season, announced, prize, total_codes))
    elif prize < announced and reset_lower:
        db.update_season(season_id, announced_prize=prize)


# ============================================================
#  شروع و پایان فصل
# ============================================================

def activate_season(season):
    rules = db.get_rules()
    db.set_season_status(season["id"], "active")
    season = db.get_season(season["id"])
    prize = scoring.prize_per_winner(0, rules)
    db.update_season(season["id"], announced_prize=prize)
    log.info("season started: %s", season["name"])
    broadcast(texts.season_start_broadcast(season, prize, rules))


def finish_season(season_id: int, auto: bool = False):
    """
    فصل را می‌بندد، نتایج را ذخیره می‌کند، قرعه‌کشی انجام می‌دهد و به همه (شامل نام برندگان) اطلاع می‌دهد.
    مشخصات کامل برندگان (آیدی، شماره کارت) فقط برای مدیرها فرستاده می‌شود.
    برمی‌گرداند: True اگر انجام شد، False اگر فصل فعال نبود.
    """
    season = db.get_season(season_id)
    if not season or season["status"] != "active":
        return False

    rules = db.get_rules()
    standings = compute_standings(season_id, rules)
    entries = [(r["user_id"], r["codes"]) for r in standings if r["codes"] > 0]
    if entries:
        winners, prize, total_codes = scoring.run_lottery(entries, rules)
    else:
        winners, prize, total_codes = [], 0, 0

    db.end_season(season_id)  # اول بسته می‌شود تا اجرای دوباره/همزمان ممکن نباشد
    for r in standings:
        db.save_season_result(
            season_id, r["user_id"], r["minutes"], r["points"], r["codes"], r["rank"],
            prize if r["user_id"] in winners else 0,
        )
    log.info("season ended: %s winners=%s prize=%s auto=%s", season["name"], winners, prize, auto)

    winner_rows = [db.get_user(w) for w in winners]
    winner_rows = [u for u in winner_rows if u]
    winner_names = [u["full_name"] or str(u["user_id"]) for u in winner_rows]

    season = db.get_season(season_id)
    broadcast(texts.season_end_broadcast(season, winner_names, prize, len(standings)))
    for u in winner_rows:
        try:
            bale_api.send_message(u["user_id"], texts.winner_private(season, prize))
        except Exception:
            log.warning("could not notify winner %s", u["user_id"])
    notify_admins(texts.season_end_admin(season, winner_rows, prize, total_codes, len(standings)))
    return True


def tick():
    """
    کارهای زمان‌بندی‌شده؛ در هر دور حلقه‌ی اصلی صدا زده می‌شود:
      ۱) پایان خودکار فصلی که تاریخ پایانش گذشته (اگر «پایان خودکار» روشن باشد)
      ۲) شروع خودکار فصلی که تاریخ شروعش رسیده (اگر فصل فعالی نباشد)
    """
    today = jdate.today_iso()

    active = db.get_active_season()
    if active and active["end_date"] and today > active["end_date"]:
        if db.auto_end_enabled():
            finish_season(active["id"], auto=True)
        else:
            key = f"end_reminded:{active['id']}"
            if not db.get_state(key):
                db.set_state(key, "1")
                notify_admins(
                    f"⏰ تاریخ پایان «{active['name']}» گذشته است ولی پایان خودکار خاموش است.\n"
                    "برای بستن فصل و قرعه‌کشی از «پنل مدیریت ← فصل‌ها» اقدام کنید."
                )
        active = db.get_active_season()

    if not active:
        due = db.next_due_scheduled(today)
        while due:
            if due["end_date"] and today > due["end_date"]:
                # فصلی که پیش از شروع، تاریخ پایانش هم گذشته؛ بدون قرعه‌کشی بسته می‌شود
                db.set_season_status(due["id"], "ended")
                notify_admins(f"⚠️ «{due['name']}» هیچ‌گاه شروع نشد و چون تاریخ پایانش گذشته بود بسته شد.")
                due = db.next_due_scheduled(today)
                continue
            activate_season(due)
            break
