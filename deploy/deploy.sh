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

echo "-- git fetch --"
git fetch --prune origin "$BRANCH"

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

echo "-- docker compose build --"
docker compose build --pull

echo "-- docker compose up -d --"
docker compose up -d --remove-orphans

echo "-- پاکسازی ایمیج‌های بلااستفاده --"
docker image prune -f > /dev/null

echo "-- وضعیت نهایی کانتینر --"
docker compose ps

echo "===== دیپلوی با موفقیت تمام شد: $(date -Is) ====="
