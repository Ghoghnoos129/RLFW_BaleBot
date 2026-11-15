# ============================================================
#  ایمیج پایه — انتخاب آینه پایدارتر برای شبکه ایران
# ============================================================
# نکته: اگر آینه پیش‌فرض در دسترس نبود، می‌توانید مقدار BASE_IMAGE را
# از طریق Build Variable در Coolify یا در فایل .env تغییر دهید.
# گزینه‌های جایگزین:
#   python:3.12-slim-bookworm                              (Docker Hub رسمی)
#   docker.ththt.ir/library/python:3.12-slim-bookworm       (پیش‌فرض فعلی)
#   docker.iranserver.com/library/python:3.12-slim-bookworm (آینه جایگزین)
ARG BASE_IMAGE=docker.ththt.ir/library/python:3.12-slim-bookworm

# نسخه پایتون به‌صورت متغیر — برای هماهنگی مسیر PYTHONPATH
ARG PYTHON_VERSION=3.12

# ============================================================
#  مرحله ۱: نصب وابستگی‌ها در یک ایمیج موقت (build-time only)
# ============================================================
FROM ${BASE_IMAGE} AS builder

# به‌روزرسانی امنیتی پکیج‌های پایه
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# فقط requirements کپی می‌شود تا کش داکر درست کار کند
COPY requirements.txt .

# نصب در --user تا بعداً فقط همین پوشه به ایمیج نهایی منتقل شود
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================================
#  مرحله ۲: ایمیج نهایی — حداقلی، بدون ابزار build، بدون root
# ============================================================
FROM ${BASE_IMAGE} AS runtime

LABEL org.opencontainers.image.title="RLFW_BaleBot" \
      org.opencontainers.image.description="ربات لیگ کتابخوانی برای پیام‌رسان بله" \
      org.opencontainers.image.licenses="MIT"

# به‌روزرسانی امنیتی + نصب ca-certificates + حذف فایل‌های اضافی
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* \
    && find / -xdev -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find / -xdev -type f -name '*.pyc' -delete \
    && true

# کاربر و گروه غیر-روت با UID/GID ثابت
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --home-dir /app --shell /usr/sbin/nologin --no-create-home appuser

WORKDIR /app

# انتقال فقط پکیج‌های نصب‌شده از مرحله builder (بدون pip/wheel/setuptools)
COPY --from=builder /root/.local /home/appuser/.local

# حذف باقی‌مانده pip/setuptools از ایمیج نهایی (برای کاهش سطح حمله)
RUN rm -rf /home/appuser/.local/lib/python${PYTHON_VERSION}/site-packages/pip* \
    /home/appuser/.local/lib/python${PYTHON_VERSION}/site-packages/setuptools* \
    /home/appuser/.local/lib/python${PYTHON_VERSION}/site-packages/wheel* \
    /home/appuser/.local/bin/pip* \
    /home/appuser/.local/bin/wheel* 2>/dev/null || true

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONPATH=/home/appuser/.local/lib/python${PYTHON_VERSION}/site-packages \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/league.db \
    LOG_PATH=/app/data/bot.log \
    HEARTBEAT_PATH=/app/data/heartbeat

# فقط کد لازم کپی می‌شود
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser run.py ./

# پوشه داده با مالکیت کاربر غیر-روت
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

USER appuser:appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,sys,time; p=os.environ['HEARTBEAT_PATH']; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p)<90 else 1)"

ENTRYPOINT ["python", "run.py"]
