#!/bin/sh
# نصب وابستگی‌های پایتون: اول PyPI اصلی، اگر نشد به ترتیب آینه‌ها.
# آینه‌ها از متغیر PIP_MIRRORS (جداشده با فاصله، آدرس .../simple) خوانده می‌شود.
set -u
REQ="${1:-requirements.txt}"

for idx in "https://pypi.org/simple" ${PIP_MIRRORS:-}; do
    echo ">>> pip: تلاش با: $idx"
    if pip install --no-cache-dir --retries 2 --timeout 25 --index-url "$idx" -r "$REQ"; then
        echo ">>> pip: نصب موفق از $idx"
        exit 0
    fi
    echo ">>> pip: $idx شکست خورد؛ منبع بعدی..."
done
echo ">>> خطا: نصب وابستگی‌ها از هیچ منبعی ممکن نشد." >&2
exit 1
