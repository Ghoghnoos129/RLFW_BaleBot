"""
لایه دیتابیس (SQLite). همه‌ی جدول‌ها و توابع خواندن/نوشتن داده اینجاست.
"""
import os
import sqlite3
from contextlib import contextmanager

from app.config import DB_PATH, DEFAULT_RULES, REGISTRATION_PASSWORD
from app import jdate

os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)


def now() -> str:
    """زمان فعلی به وقت تهران (مستقل از ساعت سرور)."""
    return jdate.now_iso()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                has_children INTEGER,
                registered_at TEXT,
                is_active INTEGER DEFAULT 1,
                spouse_name TEXT,
                card_number TEXT,
                username TEXT
            );

            CREATE TABLE IF NOT EXISTS user_state (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                data TEXT
            );

            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                is_super INTEGER NOT NULL DEFAULT 0,
                added_at TEXT
            );

            CREATE TABLE IF NOT EXISTS seasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled', -- scheduled | active | ended
                started_at TEXT,
                ended_at TEXT,
                start_date TEXT,      -- تاریخ شروع (میلادی ISO، نمایش شمسی)
                end_date TEXT,        -- تاریخ پایان (میلادی ISO، نمایش شمسی)
                announced_prize INTEGER  -- آخرین جایزه‌ای که به کاربران اعلام شده
            );

            CREATE TABLE IF NOT EXISTS special_books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER NOT NULL REFERENCES seasons(id),
                title TEXT NOT NULL,
                points INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reading_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(user_id),
                season_id INTEGER NOT NULL REFERENCES seasons(id),
                minutes INTEGER NOT NULL,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS book_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(user_id),
                season_id INTEGER NOT NULL REFERENCES seasons(id),
                book_id INTEGER NOT NULL REFERENCES special_books(id),
                created_at TEXT,
                UNIQUE(user_id, book_id)
            );

            CREATE TABLE IF NOT EXISTS season_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER NOT NULL REFERENCES seasons(id),
                user_id INTEGER NOT NULL REFERENCES users(user_id),
                minutes INTEGER,
                points INTEGER,
                codes INTEGER,
                rank INTEGER,
                prize INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS reminders (
                user_id INTEGER PRIMARY KEY,
                remind_time TEXT NOT NULL,        -- HH:MM به وقت تهران
                enabled INTEGER NOT NULL DEFAULT 1,
                last_sent_date TEXT
            );

            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,               -- text | photo | video | audio | voice | document
                text TEXT,
                file_id TEXT,
                caption TEXT,
                send_at TEXT,                     -- زمان‌بندی (وقت تهران)؛ خالی = همین حالا
                status TEXT NOT NULL DEFAULT 'scheduled',  -- scheduled | sent | canceled
                created_by INTEGER,
                created_at TEXT,
                sent_at TEXT,
                sent_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                options TEXT NOT NULL,            -- JSON: لیست متن دکمه‌ها
                per_row INTEGER NOT NULL DEFAULT 1,
                public_results INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'open',       -- open | closed
                created_by INTEGER,
                created_at TEXT,
                closes_at TEXT,
                closed_at TEXT,
                sent_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS poll_votes (
                poll_id INTEGER NOT NULL REFERENCES polls(id),
                user_id INTEGER NOT NULL,
                option_idx INTEGER NOT NULL,
                voted_at TEXT,
                PRIMARY KEY (poll_id, user_id)
            );
            """
        )
        # مهاجرت دیتابیس نسخه ۰.۱ به ۰.۲ (ستون‌های جدید؛ داده‌های قبلی دست‌نخورده می‌مانند)
        _ensure_column(conn, "users", "spouse_name", "TEXT")
        _ensure_column(conn, "users", "card_number", "TEXT")
        _ensure_column(conn, "users", "username", "TEXT")
        _ensure_column(conn, "seasons", "start_date", "TEXT")
        _ensure_column(conn, "seasons", "end_date", "TEXT")
        _ensure_column(conn, "seasons", "announced_prize", "INTEGER")
        _ensure_column(conn, "admins", "can_wipe", "INTEGER NOT NULL DEFAULT 0")


def _ensure_column(conn, table: str, column: str, ddl: str):
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


# ---------- bot_state (برای offset گرفتن آپدیت‌های بله) ----------

def get_state(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM bot_state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_state(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO bot_state(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


# ---------- settings (قوانین و تنظیمات قابل‌تغییر توسط مدیر) ----------

def get_setting(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def delete_setting(key: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM settings WHERE key=?", (key,))


def get_rules() -> dict:
    """قوانین فعلی لیگ: پیش‌فرض‌های config.py که با مقدارهای تنظیم‌شده توسط مدیر جایگزین می‌شوند."""
    rules = dict(DEFAULT_RULES)
    with get_conn() as conn:
        for row in conn.execute("SELECT key, value FROM settings WHERE key LIKE 'rule:%'"):
            k = row["key"][5:]
            if k in rules:
                try:
                    rules[k] = int(row["value"])
                except (TypeError, ValueError):
                    pass
    return rules


def set_rule(key: str, value: int):
    if key not in DEFAULT_RULES:
        raise KeyError(key)
    set_setting(f"rule:{key}", str(int(value)))


def get_rules_text():
    """متن سفارشی قوانین (اگر مدیر تعیین کرده باشد)؛ وگرنه None و متن خودکار ساخته می‌شود."""
    v = get_setting("rules_text")
    return v if v else None


def set_rules_text(text):
    if text:
        set_setting("rules_text", text)
    else:
        delete_setting("rules_text")


def get_registration_password() -> str:
    """رمز ثبت‌نام. مقدار ذخیره‌شده در بله (حتی خالی) بر مقدار .env اولویت دارد. خالی = ثبت‌نام بسته."""
    v = get_setting("registration_password")
    if v is None:
        return REGISTRATION_PASSWORD
    return v


def set_registration_password(pw: str):
    set_setting("registration_password", pw or "")


def auto_end_enabled() -> bool:
    return get_setting("auto_end", "1") == "1"


def set_auto_end(enabled: bool):
    set_setting("auto_end", "1" if enabled else "0")


# ---------- users ----------

_USER_FIELDS = {"full_name", "spouse_name", "has_children", "card_number", "username"}


def get_user(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def upsert_user(user_id: int, full_name: str = None, username: str = None):
    """اگر کاربر نبود می‌سازد؛ در غیر این صورت فقط مقدارهای داده‌شده را به‌روز می‌کند."""
    with get_conn() as conn:
        existing = conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if existing:
            if full_name is not None:
                conn.execute("UPDATE users SET full_name=? WHERE user_id=?", (full_name, user_id))
            if username is not None:
                conn.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
        else:
            conn.execute(
                "INSERT INTO users(user_id, full_name, registered_at, is_active, username) "
                "VALUES (?, ?, ?, 1, ?)",
                (user_id, full_name, now(), username),
            )


def update_user(user_id: int, **fields):
    fields = {k: v for k, v in fields.items() if k in _USER_FIELDS}
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE users SET {sets} WHERE user_id=?", (*fields.values(), user_id))


def touch_username(user_id: int, username: str):
    """آیدی (username) بله کاربر را بی‌سروصدا ذخیره/به‌روز می‌کند (فقط برای کاربر ثبت‌نام‌شده)."""
    if not username:
        return
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET username=? WHERE user_id=? AND COALESCE(username,'')<>?",
            (username, user_id, username),
        )


def all_users():
    """کاربران فعالی که ثبت‌نامشان به مرحله‌ی انتخاب فرزند رسیده (اعضای لیگ)."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE is_active=1 AND has_children IS NOT NULL ORDER BY registered_at"
        ).fetchall()


def delete_user(user_id: int):
    """کاربر را همراه با همه‌ی مطالعه‌ها، کتاب‌ها و نتایج ذخیره‌شده‌اش (در همه‌ی فصل‌ها) پاک می‌کند."""
    with get_conn() as conn:
        for table in ("season_results", "book_completions", "reading_logs", "user_state",
                      "reminders", "poll_votes"):
            conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))


def wipe_all(full: bool = False):
    """
    حذف داده‌ها. full=False: همه‌ی فصل‌ها و تاریخچه (مطالعه‌ها، کتاب‌ها، نتایج).
    full=True: علاوه بر آن، همه‌ی کاربران هم حذف می‌شوند.
    مدیرها و قوانین/تنظیمات (رمز ثبت‌نام، اعداد قوانین، متن قوانین) هرگز پاک نمی‌شوند.
    """
    with get_conn() as conn:
        for table in ("season_results", "book_completions", "reading_logs", "special_books", "seasons"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM bot_state WHERE key LIKE 'end_reminded:%'")
        for table in ("poll_votes", "polls", "broadcasts"):   # نظرسنجی‌ها و تاریخچه‌ی پیام‌ها هم تاریخچه‌اند
            conn.execute(f"DELETE FROM {table}")
        if full:
            conn.execute("DELETE FROM reminders")
            conn.execute("DELETE FROM users")
            conn.execute("DELETE FROM user_state")
            conn.execute("DELETE FROM bot_state WHERE key LIKE 'pwblock:%'")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN "
                     "('seasons','special_books','reading_logs','book_completions','season_results','polls','broadcasts')")


def count_users() -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE is_active=1 AND has_children IS NOT NULL"
        ).fetchone()["c"]


# ---------- admins (ادمین‌هایی که با کد مخفی ADMIN_SETUP_CODE اضافه شده‌اند) ----------

def is_db_admin(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone()
        return row is not None


def is_db_super_admin(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM admins WHERE user_id=? AND is_super=1", (user_id,)
        ).fetchone()
        return row is not None


def admins_count() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM admins").fetchone()
        return row["c"]


def add_admin(user_id: int, full_name: str = None, is_super: bool = False):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO admins(user_id, full_name, is_super, added_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET full_name=excluded.full_name",
            (user_id, full_name, 1 if is_super else 0, now()),
        )


def remove_admin(user_id: int) -> bool:
    """فقط ادمین‌های غیر-اصلی حذف می‌شوند؛ مدیر اصلی هرگز از این تابع حذف نمی‌شود."""
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM admins WHERE user_id=? AND is_super=0", (user_id,)
        )
        return cur.rowcount > 0


def set_admin_can_wipe(user_id: int, allowed: bool):
    """اجازه‌ی «حذف همه‌ی داده‌ها» برای یک ادمین (فقط مدیر اصلی این اجازه را می‌دهد)."""
    with get_conn() as conn:
        conn.execute("UPDATE admins SET can_wipe=? WHERE user_id=?", (1 if allowed else 0, user_id))


def db_admin_can_wipe(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT can_wipe FROM admins WHERE user_id=?", (user_id,)).fetchone()
        return bool(row and row["can_wipe"])


def get_admin(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM admins WHERE user_id=?", (user_id,)).fetchone()


def list_admins():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM admins ORDER BY is_super DESC, added_at").fetchall()


# ---------- user_state (برای مکالمه چند مرحله‌ای) ----------

def set_user_flow(user_id: int, state: str, data: str = ""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO user_state(user_id, state, data) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET state=excluded.state, data=excluded.data",
            (user_id, state, data),
        )


def get_user_flow(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM user_state WHERE user_id=?", (user_id,)).fetchone()


def clear_user_flow(user_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM user_state WHERE user_id=?", (user_id,))


# ---------- seasons ----------

_SEASON_FIELDS = {"name", "start_date", "end_date", "announced_prize"}


def get_active_season():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM seasons WHERE status='active' ORDER BY id DESC LIMIT 1"
        ).fetchone()


def get_season(season_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()


def get_upcoming_season():
    """نزدیک‌ترین فصل در انتظار شروع (اگر باشد)."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM seasons WHERE status='scheduled' "
            "ORDER BY COALESCE(start_date, '9999'), id LIMIT 1"
        ).fetchone()


def next_due_scheduled(today_iso: str):
    """فصل در انتظاری که تاریخ شروعش رسیده است."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM seasons WHERE status='scheduled' AND start_date IS NOT NULL "
            "AND start_date<=? ORDER BY start_date, id LIMIT 1",
            (today_iso,),
        ).fetchone()


def list_seasons(limit: int = 12):
    """فعال‌ها اول، بعد در انتظار، بعد پایان‌یافته‌ها (جدیدترین اول)."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM seasons
            ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'scheduled' THEN 1 ELSE 2 END,
                     COALESCE(start_date, substr(started_at, 1, 10), '') DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def create_season(name: str, start_date: str, end_date: str) -> int:
    """فصل جدید را در حالت «در انتظار» می‌سازد؛ با رسیدن تاریخ شروع، خودکار فعال می‌شود."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO seasons(name, status, start_date, end_date) VALUES (?, 'scheduled', ?, ?)",
            (name, start_date, end_date),
        )
        return cur.lastrowid


def update_season(season_id: int, **fields):
    fields = {k: v for k, v in fields.items() if k in _SEASON_FIELDS}
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE seasons SET {sets} WHERE id=?", (*fields.values(), season_id))


def set_season_status(season_id: int, status: str):
    with get_conn() as conn:
        if status == "active":
            conn.execute(
                "UPDATE seasons SET status='active', started_at=? WHERE id=?", (now(), season_id)
            )
        elif status == "ended":
            conn.execute(
                "UPDATE seasons SET status='ended', ended_at=? WHERE id=?", (now(), season_id)
            )
        else:
            conn.execute("UPDATE seasons SET status=? WHERE id=?", (status, season_id))


def end_season(season_id: int):
    set_season_status(season_id, "ended")


# ---------- special books ----------

def add_books(season_id: int, items) -> int:
    """items: لیستی از (عنوان, امتیاز)؛ همه در یک تراکنش اضافه می‌شوند. تعداد افزوده‌شده را برمی‌گرداند."""
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO special_books(season_id, title, points) VALUES (?, ?, ?)",
            [(season_id, t, p) for t, p in items],
        )
        return len(items)


def add_book(season_id: int, title: str, points: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO special_books(season_id, title, points) VALUES (?, ?, ?)",
            (season_id, title, points),
        )
        return cur.lastrowid


def list_books(season_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM special_books WHERE season_id=? ORDER BY id", (season_id,)
        ).fetchall()


def remove_book(book_id: int):
    with get_conn() as conn:
        # اول ثبت‌های اتمام این کتاب پاک می‌شود (در نسخه ۰.۱ به دلیل کلید خارجی حذف کتابِ ثبت‌شده خطا می‌داد)
        conn.execute("DELETE FROM book_completions WHERE book_id=?", (book_id,))
        conn.execute("DELETE FROM special_books WHERE id=?", (book_id,))


def get_book(book_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM special_books WHERE id=?", (book_id,)).fetchone()


# ---------- reading logs ----------

def add_reading_log(user_id: int, season_id: int, minutes: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO reading_logs(user_id, season_id, minutes, created_at) VALUES (?, ?, ?, ?)",
            (user_id, season_id, minutes, now()),
        )
        return cur.lastrowid


def get_log(log_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM reading_logs WHERE id=?", (log_id,)).fetchone()


def update_log_minutes(log_id: int, minutes: int):
    with get_conn() as conn:
        conn.execute("UPDATE reading_logs SET minutes=? WHERE id=?", (minutes, log_id))


def delete_log(log_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM reading_logs WHERE id=?", (log_id,))


def recent_logs(user_id: int, season_id: int, limit: int = 5, offset: int = 0):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM reading_logs WHERE user_id=? AND season_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, season_id, limit, offset),
        ).fetchall()


def count_logs(user_id: int, season_id: int) -> int:
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM reading_logs WHERE user_id=? AND season_id=?",
            (user_id, season_id),
        ).fetchone()["c"]


def total_minutes(user_id: int, season_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(minutes),0) AS s FROM reading_logs WHERE user_id=? AND season_id=?",
            (user_id, season_id),
        ).fetchone()
        return row["s"] or 0


# ---------- book completions ----------

def complete_book(user_id: int, season_id: int, book_id: int) -> bool:
    """برمی‌گرداند True اگر با موفقیت ثبت شد، False اگر قبلا ثبت شده بود."""
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO book_completions(user_id, season_id, book_id, created_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, season_id, book_id, now()),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def uncomplete_book(user_id: int, book_id: int):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM book_completions WHERE user_id=? AND book_id=?", (user_id, book_id)
        )


def completed_books(user_id: int, season_id: int):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT sb.id, sb.title, sb.points
            FROM book_completions bc
            JOIN special_books sb ON sb.id = bc.book_id
            WHERE bc.user_id=? AND bc.season_id=?
            ORDER BY bc.created_at
            """,
            (user_id, season_id),
        ).fetchall()


def book_points_sum(user_id: int, season_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(sb.points),0) AS s
            FROM book_completions bc
            JOIN special_books sb ON sb.id = bc.book_id
            WHERE bc.user_id=? AND bc.season_id=?
            """,
            (user_id, season_id),
        ).fetchone()
        return row["s"] or 0


# ---------- leaderboard / season results ----------

def season_participants(season_id: int):
    """همه کاربرانی که در این فصل حداقل یک دقیقه مطالعه یا یک کتاب ثبت کرده‌اند."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT u.*
            FROM users u
            WHERE u.user_id IN (
                SELECT DISTINCT user_id FROM reading_logs WHERE season_id=?
                UNION
                SELECT DISTINCT user_id FROM book_completions WHERE season_id=?
            )
            """,
            (season_id, season_id),
        ).fetchall()


def save_season_result(season_id, user_id, minutes, points, codes, rank, prize=0):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO season_results(season_id, user_id, minutes, points, codes, rank, prize) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (season_id, user_id, minutes, points, codes, rank, prize),
        )


def season_results(season_id: int):
    """نتایج ذخیره‌شده‌ی یک فصل پایان‌یافته (همراه مشخصات کاربر برای هماهنگی با برندگان)."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT sr.*, u.full_name, u.spouse_name, u.username, u.card_number
            FROM season_results sr
            LEFT JOIN users u ON u.user_id = sr.user_id
            WHERE sr.season_id=?
            ORDER BY CASE WHEN sr.rank > 0 THEN 0 ELSE 1 END, sr.rank, sr.points DESC
            """,
            (season_id,),
        ).fetchall()


def total_prize_won(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(prize),0) AS s FROM season_results WHERE user_id=?",
            (user_id,),
        ).fetchone()
        return row["s"] or 0


def set_result_prize(season_id: int, user_id: int, prize: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE season_results SET prize=? WHERE season_id=? AND user_id=?",
            (prize, season_id, user_id),
        )


# ---------- reminders (یادآور مطالعه روزانه) ----------

def get_reminder(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM reminders WHERE user_id=?", (user_id,)).fetchone()


def set_reminder(user_id: int, remind_time: str, enabled: bool = True):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO reminders(user_id, remind_time, enabled) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET remind_time=excluded.remind_time, "
            "enabled=excluded.enabled, last_sent_date=NULL",
            (user_id, remind_time, 1 if enabled else 0),
        )


def disable_reminder(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE reminders SET enabled=0 WHERE user_id=?", (user_id,))


def due_reminders(today_iso: str, hhmm: str):
    """یادآورهای فعالی که ساعتشان رسیده/گذشته و امروز هنوز فرستاده نشده."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM reminders WHERE enabled=1 AND remind_time<=? "
            "AND COALESCE(last_sent_date,'')<>?",
            (hhmm, today_iso),
        ).fetchall()


def mark_reminder_sent(user_id: int, today_iso: str):
    with get_conn() as conn:
        conn.execute("UPDATE reminders SET last_sent_date=? WHERE user_id=?", (today_iso, user_id))


def count_reminders() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) AS c FROM reminders WHERE enabled=1").fetchone()["c"]


# ---------- broadcasts (پیام‌های مدیر به کاربران) ----------

def add_broadcast(kind, text, file_id, caption, send_at, status, created_by) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO broadcasts(kind, text, file_id, caption, send_at, status, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, text, file_id, caption, send_at, status, created_by, now()),
        )
        return cur.lastrowid


def get_broadcast(bid: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM broadcasts WHERE id=?", (bid,)).fetchone()


def due_broadcasts(now_iso: str):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM broadcasts WHERE status='scheduled' AND send_at IS NOT NULL AND send_at<=? ORDER BY send_at",
            (now_iso,),
        ).fetchall()


def list_broadcasts(status=None, limit: int = 10):
    with get_conn() as conn:
        if status:
            return conn.execute(
                "SELECT * FROM broadcasts WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)
            ).fetchall()
        return conn.execute("SELECT * FROM broadcasts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def finish_broadcast(bid: int, status: str, sent: int = 0, failed: int = 0):
    with get_conn() as conn:
        conn.execute(
            "UPDATE broadcasts SET status=?, sent_at=?, sent_count=?, fail_count=? WHERE id=?",
            (status, now(), sent, failed, bid),
        )


# ---------- polls (نظرسنجی) ----------

def create_poll(question, options_json, per_row, public_results, closes_at, created_by) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO polls(question, options, per_row, public_results, status, created_by, created_at, closes_at) "
            "VALUES (?, ?, ?, ?, 'open', ?, ?, ?)",
            (question, options_json, per_row, 1 if public_results else 0, created_by, now(), closes_at),
        )
        return cur.lastrowid


def get_poll(poll_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM polls WHERE id=?", (poll_id,)).fetchone()


def list_polls(limit: int = 10):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM polls ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def open_polls():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM polls WHERE status='open' ORDER BY id").fetchall()


def due_polls(now_iso: str):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM polls WHERE status='open' AND closes_at IS NOT NULL AND closes_at<=?", (now_iso,)
        ).fetchall()


def close_poll_row(poll_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE polls SET status='closed', closed_at=? WHERE id=? AND status='open'", (now(), poll_id))


def set_poll_sent(poll_id: int, n: int):
    with get_conn() as conn:
        conn.execute("UPDATE polls SET sent_count=? WHERE id=?", (n, poll_id))


def delete_poll(poll_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM poll_votes WHERE poll_id=?", (poll_id,))
        conn.execute("DELETE FROM polls WHERE id=?", (poll_id,))


def get_vote(poll_id: int, user_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT option_idx FROM poll_votes WHERE poll_id=? AND user_id=?", (poll_id, user_id)
        ).fetchone()
        return row["option_idx"] if row else None


def cast_vote(poll_id: int, user_id: int, option_idx: int):
    """رأی را ثبت/عوض می‌کند. رأی قبلی (یا None) را برمی‌گرداند."""
    prev = get_vote(poll_id, user_id)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO poll_votes(poll_id, user_id, option_idx, voted_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(poll_id, user_id) DO UPDATE SET option_idx=excluded.option_idx, voted_at=excluded.voted_at",
            (poll_id, user_id, option_idx, now()),
        )
    return prev


def vote_counts(poll_id: int) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT option_idx, COUNT(*) AS c FROM poll_votes WHERE poll_id=? GROUP BY option_idx", (poll_id,)
        ).fetchall()
        return {r["option_idx"]: r["c"] for r in rows}


def voter_ids(poll_id: int) -> set:
    with get_conn() as conn:
        return {r["user_id"] for r in conn.execute("SELECT user_id FROM poll_votes WHERE poll_id=?", (poll_id,))}
