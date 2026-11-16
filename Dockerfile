# ایمیج پایه — انتخاب آینه پایدارتر برای شبکه ایران.
#
# نکته مهم: Docker هیچ راهی برای «اول رجیستری اصلی را امتحان کن، اگر نشد خودکار برو سراغ
# آینه» ندارد مگر با تنظیم registry-mirror در خودِ Docker daemon روی سرور (که نیاز به
# دسترسی سرور/SSH دارد). چون هدف این است که بدون دست‌زدن به سرور یا پنل Coolify هم کار
# کند، این مقدار مستقیم به یک آینه اشاره می‌کند. اگر آینه فعلی در دسترس نبود، مقدار زیر
# را عوض کنید (مستقیم همین‌جا، یا با BASE_IMAGE در .env / Build Variable در Coolify):
#   python:3.12-slim-bookworm                               (رسمی Docker Hub)
#   docker.ththt.ir/library/python:3.12-slim-bookworm        (پیش‌فرض فعلی)
#   docker.arvancloud.ir/library/python:3.12-slim-bookworm   (آینه جایگزین)
#   docker.iranserver.com/library/python:3.12-slim-bookworm  (آینه جایگزین)
ARG BASE_IMAGE=docker.ththt.ir/library/python:3.12-slim-bookworm

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

# نصب در یک virtualenv مجزا (نه --user): مسیر site-packages در venv همیشه از طریق
# pyvenv.cfg مشخص و خودکار است و به حدس‌زدن نسخه دقیق پایتون/مسیر site-packages
# (که قبلا همین‌جا باعث ModuleNotFoundError می‌شد) وابسته نیست — فارغ از اینکه ایمیج
# پایه را از Docker Hub بگیرید یا از یک آینه.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# نکته امنیتی: برای سخت‌گیری بیشتر می‌توانید requirements.txt را با pip-compile --generate-hashes
# بازسازی کنید و این دستور را به «pip install --require-hashes» تغییر دهید.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y pip setuptools wheel

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

# انتقال کل virtualenv ساخته‌شده در مرحله builder (شامل پایتون و پکیج‌های نصب‌شده)
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
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
