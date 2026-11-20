#!/usr/bin/env bash
#
# این اسکریپت فقط باید توسط root اجرا شود — از طریق «sudo -n» محدود شده در
# /etc/sudoers.d/RLFW_BaleBot-deploy که آن را به کاربر webhook می‌دهد.
#
# مالکیت این فایل باید root:root و دسترسی 700 باشد (بوسیله bootstrap.sh تنظیم می‌شود)
# تا کاربر webhook نتواند محتوای آن را تغییر دهد؛ در غیر این صورت sudo بی‌معنی می‌شود.
#
set -euo pipefail

REPO_DIR="/opt/RLFW_BaleBot"
BRANCH="main"
LOCK_FILE="/var/lock/RLFW_BaleBot-deploy.lock"
LOG_FILE="/var/log/RLFW_BaleBot/deploy.log"
SSH_KEY="$REPO_DIR/.deploy/id_ed25519"
KNOWN_HOSTS="$REPO_DIR/.deploy/known_hosts"

mkdir -p "$(dirname "$LOG_FILE")"
exec >> "$LOG_FILE" 2>&1

echo "===== دیپلوی شروع شد: $(date -Is) ====="

# جلوگیری از اجرای هم‌زمان چند دیپلوی (مثلاً اگر چند push پشت‌سرهم بیاید)
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "دیپلوی دیگری همین الان در حال اجراست؛ این اجرا نادیده گرفته شد."
    exit 1
fi

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "خطا: $REPO_DIR یک ریپوی گیت نیست. اول باید طبق README یک‌بار دستی clone کنید."
    exit 1
fi

cd "$REPO_DIR"

# --- اتصال امن به گیت‌هاب: فقط با کلید deploy مخصوص این سرور، با بررسی دقیق هاست ---
export GIT_SSH_COMMAND="ssh -i $SSH_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$KNOWN_HOSTS"

# --- دریافت کد: اول مسیر اصلی (SSH روی پورت ۲۲)، اگر نشد SSH روی پورت ۴۴۳ گیت‌هاب،
#     و در آخر (اختیاری) یک آینه‌ی گیت: GIT_MIRROR_URL در فایل $REPO_DIR/.deploy/mirror.env
#     (مثلاً ریپوی آینه روی GitLab/Gitea/Codeberg). مثال محتوای فایل:
#         GIT_MIRROR_URL=ssh://git@gitlab.com/USER/RLFW_BaleBot.git
#         GIT_MIRROR_SSH_KEY=/opt/RLFW_BaleBot/.deploy/mirror_ed25519   (اختیاری)
[ -f "$REPO_DIR/.deploy/mirror.env" ] && . "$REPO_DIR/.deploy/mirror.env"
echo "-- git fetch --"
ORIGIN_URL="$(git remote get-url origin)"
fetched=0

try_fetch() {   # $1=آدرس ریموت   $2=توضیح
    echo "   تلاش: $2"
    if timeout 90 git fetch --prune "$1" "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"; then
        fetched=1; return 0
    fi
    echo "   ناموفق: $2"; return 1
}

try_fetch "$ORIGIN_URL" "سرور اصلی (origin)" || true

if [ "$fetched" -eq 0 ]; then
    # تبدیل git@github.com:owner/repo.git  →  ssh://git@ssh.github.com:443/owner/repo.git
    ALT_URL="$(printf '%s' "$ORIGIN_URL" | sed -E 's#^git@github\.com:#ssh://git@ssh.github.com:443/#; s#^ssh://git@github\.com/#ssh://git@ssh.github.com:443/#')"
    if [ "$ALT_URL" != "$ORIGIN_URL" ]; then
        try_fetch "$ALT_URL" "گیت‌هاب از طریق پورت ۴۴۳" || true
    fi
fi

if [ "$fetched" -eq 0 ] && [ -n "${GIT_MIRROR_URL:-}" ]; then
    # آینه معمولاً با کلید/توکن دیگری است؛ اگر لازم است GIT_MIRROR_SSH_KEY را هم بگذارید
    if [ -n "${GIT_MIRROR_SSH_KEY:-}" ]; then
        export GIT_SSH_COMMAND="ssh -i $GIT_MIRROR_SSH_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
    fi
    try_fetch "$GIT_MIRROR_URL" "آینه‌ی گیت (GIT_MIRROR_URL)" || true
fi

if [ "$fetched" -eq 0 ]; then
    echo "خطا: دریافت کد از هیچ‌کدام از منبع‌ها ممکن نبود."
    exit 1
fi

BEFORE_COMMIT="$(git rev-parse HEAD)"
AFTER_COMMIT="$(git rev-parse "origin/$BRANCH")"

if [ "$BEFORE_COMMIT" = "$AFTER_COMMIT" ]; then
    echo "تغییری نسبت به کامیت فعلی ($BEFORE_COMMIT) وجود ندارد؛ دیپلوی لازم نیست."
    exit 0
fi

echo "-- git reset --hard origin/$BRANCH (از $BEFORE_COMMIT به $AFTER_COMMIT) --"
git reset --hard "origin/$BRANCH"

echo "-- بررسی اینکه .env دست‌نخورده مانده (هرگز نباید از گیت بیاید) --"
if git show "origin/$BRANCH" --stat | grep -q '^\.env$'; then
    echo "هشدار: فایل .env داخل ریپو دیده شد! این فایل هرگز نباید commit شود."
fi

echo "-- build (با فال‌بک آینه برای ایمیج پایه / pip / apt) و up --"
"$REPO_DIR/deploy/build_with_fallback.sh" up

echo "-- پاکسازی ایمیج‌های بلااستفاده --"
docker image prune -f > /dev/null

echo "-- وضعیت نهایی کانتینر --"
docker compose ps

echo "===== دیپلوی با موفقیت تمام شد: $(date -Is) ====="
