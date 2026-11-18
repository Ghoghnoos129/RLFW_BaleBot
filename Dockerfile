# ============================================================
#  تصویر پایه — استفاده از آینه داخلی ایران (جلوگیری از 403 Docker Hub)
# ============================================================
# گزینه‌های جایگزین (در صورت عدم دسترسی می‌توانید به صورت دستی تعویض کنید):
#   python:3.12-slim-bookworm                                (Docker Hub رسمی — در ایران 403 می‌دهد)
#   docker.abrha.net/library/python:3.12-slim-bookworm       (آینه پارس‌پک — پیش‌فرض فعلی)
#   docker-mirror.liara.ir/library/python:3.12-slim-bookworm (آینه Liara)
#   docker.arvancloud.ir/library/python:3.12-slim-bookworm   (آینه ابرآروان)
ARG BASE_IMAGE=docker.abrha.net/library/python:3.12-slim-bookworm

# ============================================================
#  مرحله ۱: نصب وابستگی‌ها در تصویر موقت (فقط زمان ساخت)
# ============================================================
FROM ${BASE_IMAGE} AS builder

# به‌روزرسانی امنیتی بسته‌های پایه
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# فقط requirements را کپی کنید تا کش Docker به درستی کار کند
COPY requirements.txt .

# استفاده از virtualenv مستقل: مسیر site-packages همیشه از طریق pyvenv.cfg مشخص می‌شود
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# نصب وابستگی‌ها (در نهایت pip/setuptools/wheel حذف می‌شوند)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y pip setuptools wheel

# ============================================================
#  مرحله ۲: تصویر نهایی — حداقلی، بدون ابزار ساخت، بدون root
# ============================================================
FROM ${BASE_IMAGE} AS runtime

LABEL org.opencontainers.image.title="RLFW_BaleBot" \
      org.opencontainers.image.description="ربات لیگ کتاب‌خوانی برای پیام‌رسان بله" \
      org.opencontainers.image.licenses="MIT"

# به‌روزرسانی امنیتی + نصب ca-certificates + حذف فایل‌های اضافی
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* \
    && find / -xdev -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find / -xdev -type f -name '*.pyc' -delete \
    && true

# کاربر و گروه غیر root با UID/GID ثابت
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --home-dir /app --shell /usr/sbin/nologin --no-create-home appuser

WORKDIR /app

# انتقال virtualenv کامل از مرحله builder
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/league.db \
    LOG_PATH=/app/data/bot.log \
    HEARTBEAT_PATH=/app/data/heartbeat

# فقط کد لازم را کپی کنید
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser run.py ./

# پوشه داده با مالکیت کاربر غیر root
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

USER appuser:appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,sys,time; p=os.environ['HEARTBEAT_PATH']; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p)<90 else 1)"

ENTRYPOINT ["python", "run.py"]
