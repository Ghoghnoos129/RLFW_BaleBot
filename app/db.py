"""
لایه دیتابیس (SQLite). همه‌ی جدول‌ها و توابع خواندن/نوشتن داده اینجاست.
"""
import os
import sqlite3
import datetime as dt
from contextlib import contextmanager

from app.config import DB_PATH

os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


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
                is_active INTEGER DEFAULT 1
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
                status TEXT NOT NULL DEFAULT 'active', -- active | ended
                started_at TEXT,
                ended_at TEXT
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
            """
        )


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


# ---------- users ----------

def get_user(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def upsert_user(user_id: int, full_name: str = None, has_children: int = None):
    with get_conn() as conn:
        existing = conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if existing:
            if full_name is not None:
                conn.execute("UPDATE users SET full_name=? WHERE user_id=?", (full_name, user_id))
            if has_children is not None:
                conn.execute("UPDATE users SET has_children=? WHERE user_id=?", (has_children, user_id))
        else:
            conn.execute(
                "INSERT INTO users(user_id, full_name, has_children, registered_at, is_active) "
                "VALUES (?, ?, ?, ?, 1)",
                (user_id, full_name, has_children, now()),
            )


def all_users():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE is_active=1 ORDER BY registered_at").fetchall()


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

def get_active_season():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM seasons WHERE status='active' ORDER BY id DESC LIMIT 1"
        ).fetchone()


def get_season(season_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()


def create_season(name: str) -> int:
    with get_conn() as conn:
        conn.execute(
            "UPDATE seasons SET status='ended', ended_at=? WHERE status='active'", (now(),)
        )
        cur = conn.execute(
            "INSERT INTO seasons(name, status, started_at) VALUES (?, 'active', ?)",
            (name, now()),
        )
        return cur.lastrowid


def end_season(season_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE seasons SET status='ended', ended_at=? WHERE id=?", (now(), season_id)
        )


# ---------- special books ----------

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
        conn.execute("DELETE FROM special_books WHERE id=?", (book_id,))


def get_book(book_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM special_books WHERE id=?", (book_id,)).fetchone()


# ---------- reading logs ----------

def add_reading_log(user_id: int, season_id: int, minutes: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO reading_logs(user_id, season_id, minutes, created_at) VALUES (?, ?, ?, ?)",
            (user_id, season_id, minutes, now()),
        )


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
            SELECT u.user_id, u.full_name, u.has_children
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
