# ایمیج پایه، با امکان جایگزینی در صورت مشکل شبکه هنگام pull از Docker Hub
# (مثلاً خطای "connection reset by peer" روی برخی سرورها). پیش‌فرض همان ایمیج رسمی
# Docker Hub است؛ در صورت نیاز می‌توانید موقع build مقدار دیگری بدهید، مثلا یک آینه:
#   docker compose build --build-arg BASE_IMAGE=docker.arvancloud.ir/library/python:3.12-slim-bookworm
# یا ساده‌تر، مقدار BASE_IMAGE را در فایل .env تنظیم کنید (به .env.example نگاه کنید).
ARG BASE_IMAGE=python:3.12-slim-bookworm

# ============================================================
#  مرحله ۱: نصب وابستگی‌ها در یک ایمیج موقت (build-time only)
# ============================================================
FROM ${BASE_IMAGE} AS builder

# به‌روزرسانی امنیتی پکیج‌های پایه + نصب فقط چیزی که برای build لازم است
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# فقط requirements کپی می‌شود تا کش داکر درست کار کند و تغییر کد باعث نصب مجدد نشود
COPY requirements.txt .

# نصب در --user تا بعدا فقط همین پوشه به ایمیج نهایی منتقل شود (بدون pip/setuptools اضافه در ایمیج نهایی)
# نکته امنیتی: برای سخت‌گیری بیشتر می‌توانید requirements.txt را با pip-compile --generate-hashes
# بازسازی کنید و این دستور را به «pip install --require-hashes» تغییر دهید.
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================================
#  مرحله ۲: ایمیج نهایی — حداقلی، بدون ابزار build، بدون root
# ============================================================
FROM ${BASE_IMAGE} AS runtime

LABEL org.opencontainers.image.title="RLFW_BaleBot" \
      org.opencontainers.image.description="ربات لیگ کتابخوانی برای پیام‌رسان بله" \
      org.opencontainers.image.licenses="MIT"

# به‌روزرسانی امنیتی پکیج‌های سیستمی + حذف هرچه ممکن است سطح حمله را افزایش دهد
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* \
    && find / -xdev \( -name '*.pyc' -o -name '__pycache__' \) -exec rm -rf {} + 2>/dev/null || true

# کاربر و گروه غیر-روت با UID/GID ثابت (برای هماهنگی مالکیت volume روی هاست)
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --home-dir /app --shell /usr/sbin/nologin --no-create-home appuser

WORKDIR /app

# انتقال فقط پکیج‌های نصب‌شده از مرحله builder (بدون pip/wheel/setuptools در ایمیج نهایی)
COPY --from=builder /root/.local /home/appuser/.local

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONPATH=/home/appuser/.local/lib/python3.12/site-packages \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/league.db \
    LOG_PATH=/app/data/bot.log \
    HEARTBEAT_PATH=/app/data/heartbeat

# فقط کد لازم کپی می‌شود (تست‌ها، .git، .env و ... با .dockerignore حذف شده‌اند)
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser run.py ./

# پوشه داده با مالکیت کاربر غیر-روت از قبل ساخته می‌شود (چون فایل‌سیستم runtime read-only خواهد بود)
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

USER appuser:appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,sys,time; p=os.environ['HEARTBEAT_PATH']; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p)<90 else 1)"

ENTRYPOINT ["python", "run.py"]
