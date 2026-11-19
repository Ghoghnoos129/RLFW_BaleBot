"""
نظرسنجی: مدیر سؤال و دکمه‌های شیشه‌ای (گزینه‌ها) را طراحی می‌کند، می‌تواند مهلت بگذارد، برای همه ارسال
می‌شود؛ کاربران با زدن دکمه رأی می‌دهند (ناشناس، قابل‌تغییر تا پایان مهلت).
"""
import json
import logging
import time

from app import auth, bale_api, db, jdate, league
from app.bale_api import answer_callback_query, edit_or_send, send_message
from app.keyboards import cancel_kb, confirm_keyboard, inline

log = logging.getLogger("polls")

BACK_HOME = [("↩️ پنل مدیریت", "adm:home")]
BACK_PL = [("↩️ نظرسنجی‌ها", "adm:pl:home")]
MAX_OPTION_LEN = 40
MAX_OPTIONS = 10
BAR = 10


# ============================================================
#  ساخت پیام و کیبورد نظرسنجی
# ============================================================

def options_of(poll) -> list:
    return json.loads(poll["options"])


def poll_text(poll) -> str:
    deadline = (f"⏳ مهلت رأی: تا {jdate.fmt_datetime(poll['closes_at'])}" if poll["closes_at"]
                else "⏳ بدون محدودیت زمانی (تا وقتی مدیر ببندد)")
    return (f"🗳 نظرسنجی\n\n{poll['question']}\n\n{deadline}\n"
            "🔒 رأی‌ها ناشناس است و تا پایان مهلت می‌توانید رأی‌تان را عوض کنید.")


def poll_keyboard(pid, options, per_row, public) -> dict:
    per_row = min(max(per_row, 1), 3)
    buttons = [(opt, f"poll:{pid}:{i}") for i, opt in enumerate(options)]
    rows = [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]
    if public:
        rows.append([("📊 نتایج", f"pollres:{pid}")])
    return inline(rows)


def results_text(poll) -> str:
    opts = options_of(poll)
    counts = db.vote_counts(poll["id"])
    total = sum(counts.values())
    lines = [f"📊 {poll['question']}", ""]
    for i, opt in enumerate(opts):
        c = counts.get(i, 0)
        pct = round(c * 100 / total) if total else 0
        filled = round(BAR * c / total) if total else 0
        lines.append(f"{i + 1}) {opt}\n    {'█' * filled}{'░' * (BAR - filled)} {c} رأی ({pct}٪)")
    lines.append("")
    lines.append(f"👥 مجموع آرا: {total} از {db.count_users()} کاربر ثبت‌نام‌شده")
    lines.append("وضعیت: " + ("🟢 باز" if poll["status"] == "open" else "⚪ بسته"))
    return "\n".join(lines)


def publish(poll, ids=None) -> int:
    kb = poll_keyboard(poll["id"], options_of(poll), poll["per_row"], poll["public_results"])
    ids = {u["user_id"] for u in db.all_users()} if ids is None else ids
    return league.broadcast(poll_text(poll), ids=ids, reply_markup=kb)


# ============================================================
#  رأی‌دادن کاربران
# ============================================================

def handle_vote(cb: dict):
    cb_id, data = cb.get("id"), cb.get("data", "")
    user_id = cb.get("from", {}).get("id")
    try:
        _, pid_s, idx_s = data.split(":")
        pid, idx = int(pid_s), int(idx_s)
    except ValueError:
        answer_callback_query(cb_id)
        return
    if pid == 0:
        answer_callback_query(cb_id, "این فقط پیش‌نمایش است.", show_alert=True)
        return
    poll = db.get_poll(pid)
    u = db.get_user(user_id)
    if not poll:
        answer_callback_query(cb_id, "این نظرسنجی دیگر موجود نیست.", show_alert=True)
        return
    if not u or u["has_children"] is None:
        answer_callback_query(cb_id, "برای رأی‌دادن باید ثبت‌نام کنید.", show_alert=True)
        return
    expired = poll["closes_at"] and poll["closes_at"] <= jdate.now_iso()
    if poll["status"] != "open" or expired:
        answer_callback_query(cb_id, "مهلت این نظرسنجی تمام شده است.", show_alert=True)
        return
    opts = options_of(poll)
    if not (0 <= idx < len(opts)):
        answer_callback_query(cb_id)
        return
    prev = db.cast_vote(pid, user_id, idx)
    if prev == idx:
        answer_callback_query(cb_id, f"رأی شما از قبل همین بود: «{opts[idx]}»")
    elif prev is None:
        answer_callback_query(cb_id, f"✅ رأی شما ثبت شد: «{opts[idx]}»")
    else:
        answer_callback_query(cb_id, f"🔄 رأی شما عوض شد: «{opts[idx]}»")


def handle_results_button(cb: dict):
    cb_id, data = cb.get("id"), cb.get("data", "")
    user_id = cb.get("from", {}).get("id")
    chat_id = cb.get("message", {}).get("chat", {}).get("id")
    try:
        poll = db.get_poll(int(data.split(":")[1]))
    except (ValueError, IndexError):
        poll = None
    if not poll or not (poll["public_results"] or auth.is_admin(user_id)):
        answer_callback_query(cb_id, "نتایج این نظرسنجی عمومی نیست.", show_alert=True)
        return
    answer_callback_query(cb_id)
    send_message(chat_id, results_text(poll))


def show_open_polls(chat_id, user_id):
    """دکمه‌ی «🗳 نظرسنجی‌ها» برای کاربر: نظرسنجی‌های بازِ فعلی را دوباره نشان می‌دهد."""
    now = jdate.now_iso()
    polls = [p for p in db.open_polls() if not p["closes_at"] or p["closes_at"] > now]
    if not polls:
        send_message(chat_id, "در حال حاضر نظرسنجی بازی وجود ندارد.")
        return
    for p in polls:
        opts = options_of(p)
        mine = db.get_vote(p["id"], user_id)
        note = f"\n\n✅ رأی فعلی شما: «{opts[mine]}» (می‌توانید عوضش کنید)" if mine is not None else ""
        send_message(chat_id, poll_text(p) + note, reply_markup=poll_keyboard(p["id"], opts, p["per_row"], p["public_results"]))


# ============================================================
#  بستن نظرسنجی
# ============================================================

def close_poll(pid: int) -> bool:
    poll = db.get_poll(pid)
    if not poll or poll["status"] != "open":
        return False
    db.close_poll_row(pid)
    poll = db.get_poll(pid)
    res = results_text(poll)
    league.notify_admins("🗳 نظرسنجی بسته شد\n\n" + res)
    if poll["public_results"]:
        league.broadcast("🗳 نتیجه‌ی نظرسنجی\n\n" + res, ids={u["user_id"] for u in db.all_users()})
    return True


def close_due():
    for p in db.due_polls(jdate.now_iso()):
        close_poll(p["id"])


# ============================================================
#  پنل مدیر
# ============================================================

def home_screen(chat_id, message_id=None):
    polls = db.list_polls(10)
    lines = ["🗳 نظرسنجی‌ها", "", "سؤال و دکمه‌های شیشه‌ای (گزینه‌ها) را خودتان طراحی می‌کنید و برای همه ارسال می‌شود."]
    kb = [[("➕ نظرسنجی جدید", "adm:pl:new")]]
    for p in polls:
        mark = "🟢" if p["status"] == "open" else "⚪"
        votes = sum(db.vote_counts(p["id"]).values())
        q = p["question"].replace("\n", " ")
        kb.append([(f"{mark} #{p['id']} {q[:28]} ({votes} رأی)", f"adm:pl:v:{p['id']}")])
    if not polls:
        lines.append("\nهنوز نظرسنجی‌ای نساخته‌اید.")
    kb.append(BACK_HOME)
    edit_or_send(chat_id, message_id, "\n".join(lines), inline(kb))


def _detail(chat_id, message_id, pid):
    poll = db.get_poll(pid)
    if not poll:
        home_screen(chat_id, message_id)
        return
    created = jdate.fmt_datetime(poll["created_at"])
    closes = jdate.fmt_datetime(poll["closes_at"]) if poll["closes_at"] else "بدون محدودیت"
    text = (f"🗳 نظرسنجی #{pid} — ایجاد: {created}\n"
            f"⏳ مهلت: {closes} | 📊 نتایج برای کاربران: {'عمومی' if poll['public_results'] else 'فقط مدیر'} | "
            f"📨 ارسال‌شده به: {poll['sent_count']} نفر\n\n" + results_text(poll))
    kb = []
    if poll["status"] == "open":
        kb.append([("📣 یادآوری به رأی‌ندادگان", f"adm:pl:remind:{pid}")])
        kb.append([("⏹ بستن نظرسنجی", f"adm:pl:close:{pid}")])
    kb.append([("🗑 حذف نظرسنجی", f"adm:pl:del:{pid}")])
    kb.append(BACK_PL)
    edit_or_send(chat_id, message_id, text, inline(kb))


def _flow(user_id, *states):
    flow = db.get_user_flow(user_id)
    if not flow or flow["state"] not in states:
        return None
    try:
        return json.loads(flow["data"] or "{}")
    except ValueError:
        return None


def _save(user_id, state, d):
    db.set_user_flow(user_id, state, json.dumps(d, ensure_ascii=False))


def _ask_layout(chat_id, user_id, d):
    _save(user_id, "admin_pl_layout", d)
    send_message(chat_id, "🔘 چیدمان دکمه‌ها: در هر ردیف چند دکمه باشد؟\n(گزینه‌های کوتاه را می‌توان ۲ یا ۳تایی کنار هم گذاشت)",
                 inline([[("۱ دکمه", "adm:pl:lay:1"), ("۲ دکمه", "adm:pl:lay:2"), ("۳ دکمه", "adm:pl:lay:3")],
                         [("❌ انصراف", "cancel")]]))


def _ask_visibility(chat_id, user_id, d):
    _save(user_id, "admin_pl_vis", d)
    send_message(chat_id, "📊 نتایج برای کاربران چگونه باشد؟",
                 inline([[("🔒 فقط مدیر ببیند", "adm:pl:vis:0")],
                         [("📊 عمومی (دکمه‌ی نتایج + اعلام در پایان)", "adm:pl:vis:1")],
                         [("❌ انصراف", "cancel")]]))


def _preview(chat_id, user_id, d):
    _save(user_id, "admin_pl_confirm", d)
    fake = {"id": 0, "question": d["q"], "closes_at": d.get("closes_at")}
    send_message(chat_id, "👁 پیش‌نمایش نظرسنجی:")
    send_message(chat_id, poll_text(fake), reply_markup=poll_keyboard(0, d["opts"], d["per_row"], d["public"]))
    n = db.count_users()
    send_message(chat_id, f"برای {n} کاربر ارسال شود؟",
                 inline([[(f"📣 انتشار برای همه ({n} نفر)", "adm:pl:pub")], [("❌ انصراف", "cancel")]]))


def start_new(chat_id, user_id):
    db.set_user_flow(user_id, "admin_pl_q")
    send_message(chat_id, "🗳 متن سؤال نظرسنجی را بفرستید:", reply_markup=cancel_kb())


def handle_flow(chat_id, user_id, state, data, text) -> bool:
    if state == "admin_pl_q":
        if not text or len(text) > 500:
            send_message(chat_id, "سؤال باید متنی تا ۵۰۰ حرف باشد. دوباره بفرستید:", reply_markup=cancel_kb())
            return True
        _save(user_id, "admin_pl_opts", {"q": text})
        send_message(chat_id, f"گزینه‌ها (همان دکمه‌های شیشه‌ای) را بفرستید؛ هر گزینه در یک خط، بین ۲ تا {MAX_OPTIONS} گزینه.\n"
                              "مثال:\nبله\nخیر\nنظری ندارم", reply_markup=cancel_kb())
        return True

    if state == "admin_pl_opts":
        opts = [l.strip() for l in text.splitlines() if l.strip()]
        d = json.loads(data or "{}")
        if len(opts) < 2 or len(opts) > MAX_OPTIONS or any(len(o) > MAX_OPTION_LEN for o in opts) or len(set(opts)) != len(opts):
            send_message(chat_id, f"گزینه‌ها باید ۲ تا {MAX_OPTIONS} خط، غیرتکراری و هرکدام حداکثر {MAX_OPTION_LEN} حرف باشد. دوباره بفرستید:",
                         reply_markup=cancel_kb())
            return True
        d["opts"] = opts
        _ask_layout(chat_id, user_id, d)
        return True

    if state == "admin_pl_closeat":
        iso = jdate.parse_datetime(text)
        if not iso or iso <= jdate.now_iso():
            send_message(chat_id, "زمان نامعتبر یا گذشته است. مثال: 1405/09/10 18:30", reply_markup=cancel_kb())
            return True
        d = json.loads(data or "{}")
        d["closes_at"] = iso
        _ask_visibility(chat_id, user_id, d)
        return True

    if state in ("admin_pl_layout", "admin_pl_dur", "admin_pl_vis", "admin_pl_confirm"):
        send_message(chat_id, "از دکمه‌های بالا استفاده کنید یا انصراف دهید.", reply_markup=cancel_kb())
        return True
    return False


def admin_callback(chat_id, message_id, user_id, parts):
    action = parts[0] if parts else "home"
    arg = parts[1] if len(parts) > 1 else ""

    if action == "home":
        home_screen(chat_id, message_id)

    elif action == "new":
        start_new(chat_id, user_id)

    elif action == "lay":
        d = _flow(user_id, "admin_pl_layout")
        if d is None or arg not in ("1", "2", "3"):
            return
        d["per_row"] = int(arg)
        _save(user_id, "admin_pl_dur", d)
        send_message(chat_id, "⏳ مهلت نظرسنجی؟",
                     inline([[("♾ بدون محدودیت", "adm:pl:dur:none")],
                             [("۱ ساعت", "adm:pl:dur:1"), ("۶ ساعت", "adm:pl:dur:6"), ("۱ روز", "adm:pl:dur:24")],
                             [("۳ روز", "adm:pl:dur:72"), ("۷ روز", "adm:pl:dur:168")],
                             [("🕓 تاریخ و ساعت دلخواه", "adm:pl:dur:custom")],
                             [("❌ انصراف", "cancel")]]))

    elif action == "dur":
        d = _flow(user_id, "admin_pl_dur")
        if d is None:
            return
        if arg == "custom":
            _save(user_id, "admin_pl_closeat", d)
            send_message(chat_id, "🕓 زمان پایان نظرسنجی را بنویسید (شمسی، وقت تهران):\nمثال: 1405/09/10 18:30",
                         reply_markup=cancel_kb())
            return
        d["closes_at"] = None if arg == "none" else jdate.add_hours_iso(float(arg)) if arg.isdigit() else None
        _ask_visibility(chat_id, user_id, d)

    elif action == "vis":
        d = _flow(user_id, "admin_pl_vis")
        if d is None or arg not in ("0", "1"):
            return
        d["public"] = arg == "1"
        _preview(chat_id, user_id, d)

    elif action == "pub":
        d = _flow(user_id, "admin_pl_confirm")
        if d is None:
            edit_or_send(chat_id, message_id, "این پیش‌نمایش دیگر معتبر نیست.", inline([BACK_PL]))
            return
        pid = db.create_poll(d["q"], json.dumps(d["opts"], ensure_ascii=False), d["per_row"], d["public"],
                             d.get("closes_at"), user_id)
        db.clear_user_flow(user_id)
        edit_or_send(chat_id, message_id, "⏳ در حال ارسال نظرسنجی برای کاربران...", None)
        poll = db.get_poll(pid)
        sent = publish(poll)
        db.set_poll_sent(pid, sent)
        send_message(chat_id, f"✅ نظرسنجی #{pid} برای {sent} نفر ارسال شد.",
                     inline([[("📊 مشاهده‌ی نتایج", f"adm:pl:v:{pid}")], BACK_PL]))

    elif action == "v":
        _detail(chat_id, message_id, int(arg) if arg.isdigit() else 0)

    elif action == "remind":
        pid = int(arg) if arg.isdigit() else 0
        poll = db.get_poll(pid)
        if not poll or poll["status"] != "open":
            _detail(chat_id, message_id, pid)
            return
        voted = db.voter_ids(pid)
        todo = {u["user_id"] for u in db.all_users()} - voted
        send_message(chat_id, f"⏳ ارسال یادآوری به {len(todo)} نفر که هنوز رأی نداده‌اند...")
        sent = publish(poll, ids=todo)
        send_message(chat_id, f"✅ ارسال شد: {sent} نفر", inline([[("↩️ نظرسنجی", f"adm:pl:v:{pid}")]]))

    elif action == "close":
        pid = int(arg) if arg.isdigit() else 0
        edit_or_send(chat_id, message_id, f"نظرسنجی #{pid} بسته شود؟ (دیگر رأی پذیرفته نمی‌شود)"
                     + ("\nنتیجه برای همه‌ی کاربران هم ارسال می‌شود." if (db.get_poll(pid) and db.get_poll(pid)["public_results"]) else ""),
                     confirm_keyboard(f"adm:pl:closeyes:{pid}", f"adm:pl:v:{pid}"))

    elif action == "closeyes":
        pid = int(arg) if arg.isdigit() else 0
        close_poll(pid)
        _detail(chat_id, message_id, pid)

    elif action == "del":
        pid = int(arg) if arg.isdigit() else 0
        edit_or_send(chat_id, message_id, f"نظرسنجی #{pid} و همه‌ی آرای آن حذف شود؟ این کار برگشت‌پذیر نیست.",
                     confirm_keyboard(f"adm:pl:delyes:{pid}", f"adm:pl:v:{pid}"))

    elif action == "delyes":
        db.delete_poll(int(arg) if arg.isdigit() else 0)
        home_screen(chat_id, message_id)
