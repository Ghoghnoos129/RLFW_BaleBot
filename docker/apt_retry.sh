#!/bin/sh
# به‌روزرسانی/نصب پکیج‌های apt با «اول سرور اصلی، بعد آینه‌ها».
# استفاده:  apt_retry.sh <پکیج‌ها...>   (بدون آرگومان فقط upgrade انجام می‌شود)
# آینه‌ها از متغیر APT_MIRRORS (جداشده با فاصله) خوانده می‌شود.
# این مرحله «بهترین تلاش» است: اگر همه‌ی منبع‌ها شکست خورند، ساخت ایمیج متوقف نمی‌شود
# (ایمیج پایه از قبل ca-certificates دارد) و فقط هشدار چاپ می‌شود.
SRC=/etc/apt/sources.list.d/debian.sources
[ -f "$SRC" ] || SRC=/etc/apt/sources.list
cp "$SRC" /tmp/sources.orig

run_apt() {
    apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 update \
      && apt-get -y -o Acquire::Retries=2 upgrade \
      && { [ "$#" -eq 0 ] || apt-get install -y --no-install-recommends -o Acquire::Retries=2 "$@"; }
}

ok=1
if run_apt "$@"; then ok=0; else
    for m in $APT_MIRRORS; do
        m="${m%/}"
        cp /tmp/sources.orig "$SRC"
        sed -i "s|http://deb.debian.org/debian-security|${m}-security|g; s|http://deb.debian.org/debian|${m}|g; \
                s|https://deb.debian.org/debian-security|${m}-security|g; s|https://deb.debian.org/debian|${m}|g" "$SRC"
        rm -rf /var/lib/apt/lists/*
        echo ">>> apt: سرور اصلی جواب نداد؛ تلاش با آینه: $m"
        if run_apt "$@"; then ok=0; break; fi
    done
fi
cp /tmp/sources.orig "$SRC"
rm -rf /var/lib/apt/lists/* /var/cache/apt/* /tmp/sources.orig
if [ "$ok" -ne 0 ]; then
    echo ">>> هشدار: هیچ‌کدام از منبع‌های apt در دسترس نبود؛ بدون به‌روزرسانی سیستمی ادامه می‌دهیم."
fi
exit 0
