#!/usr/bin/env bash
#
# ساخت ایمیج با «اول سرور اصلی، در صورت مشکل آینه‌ها» برای ایمیج پایه.
# (pip و apt داخل خود Dockerfile همین منطق را دارند.)
#
# استفاده (داخل پوشه‌ی پروژه):
#   ./deploy/build_with_fallback.sh            # فقط build
#   ./deploy/build_with_fallback.sh up         # build + docker compose up -d
#
# لیست ایمیج‌های پایه را می‌توان با متغیر BASE_IMAGE_CANDIDATES (جداشده با فاصله) عوض کرد.
set -uo pipefail
cd "$(dirname "$0")/.."

TAG="python:3.12-slim-bookworm"
CANDIDATES="${BASE_IMAGE_CANDIDATES:-\
$TAG \
mirror.gcr.io/library/$TAG \
public.ecr.aws/docker/library/$TAG \
docker.arvancloud.ir/library/$TAG \
docker.iranserver.com/library/$TAG \
docker.ththt.ir/library/$TAG}"

chosen=""
for img in $CANDIDATES; do
    echo ">>> تلاش برای دریافت ایمیج پایه: $img"
    # تا ۲ بار تلاش برای هر منبع (خطاهای گذرای شبکه)
    for attempt in 1 2; do
        if timeout 300 docker pull "$img"; then chosen="$img"; break 2; fi
        echo "    تلاش $attempt ناموفق بود"
        sleep 3
    done
    echo ">>> $img در دسترس نبود؛ منبع بعدی..."
done

if [ -z "$chosen" ]; then
    # شاید ایمیج از قبل روی سرور هست (کش محلی)
    if docker image inspect "$TAG" >/dev/null 2>&1; then
        echo ">>> هیچ منبعی جواب نداد؛ از ایمیج محلی موجود ($TAG) استفاده می‌شود."
        chosen="$TAG"
    else
        echo "خطا: ایمیج پایه از هیچ منبعی دریافت نشد." >&2
        exit 1
    fi
fi

echo ">>> ایمیج پایه‌ی انتخاب‌شده: $chosen"
export BASE_IMAGE="$chosen"
# ایمیج پایه همین الان دریافت شد؛ --pull لازم نیست (و در صورت قطع بودن منبع اصلی، خراب می‌کرد)
docker compose build || exit 1

if [ "${1:-}" = "up" ]; then
    docker compose up -d --remove-orphans
    docker compose ps
fi
