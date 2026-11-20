# ایمیج پایه.
#
# استراتژی «اول سرور اصلی، در صورت مشکل آینه»:
#  • وابستگی‌های پایتون (pip) و پکیج‌های سیستمی (apt): داخل همین Dockerfile خودکار —
#    اول PyPI/Debian اصلی، و اگر جواب نداد به ترتیب آینه‌های PIP_MIRRORS / APT_MIRRORS.
#  • ایمیج پایه (دستور FROM): Docker اجازه‌ی «تلاش چندباره» داخل Dockerfile نمی‌دهد؛
#    برای همین اسکریپت deploy/build_with_fallback.sh (و deploy.sh) به ترتیب
#    BASE_IMAGE_CANDIDATES را pull می‌کند و اولین ایمیجِ سالم را به‌عنوان BASE_IMAGE می‌دهد.
#    اگر از Coolify می‌سازید، فقط یک مقدار BASE_IMAGE قابل‌تنظیم است (Build Variable)،
#    یا روی سرور در /etc/docker/daemon.json گزینه‌ی registry-mirrors را بگذارید (README).
#
# پیش‌فرض: ایمیج رسمی Docker Hub (سرور اصلی).
ARG BASE_IMAGE=python:3.12-slim-bookworm

# ============================================================
#  مرحله ۱: نصب وابستگی‌ها در یک ایمیج موقت (build-time only)
# ============================================================
FROM ${BASE_IMAGE} AS builder

# آینه‌ها (جداشده با فاصله). مقدار پیش‌فرض را می‌توان با Build Arg / .env عوض کرد.
ARG PIP_MIRRORS="https://mirror-pypi.runflare.com/simple https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple https://pypi.mirrors.ustc.edu.cn/simple"

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
COPY docker/pip_retry.sh /usr/local/bin/pip_retry.sh
RUN PIP_MIRRORS="${PIP_MIRRORS}" sh /usr/local/bin/pip_retry.sh requirements.txt \
    && pip uninstall -y pip setuptools wheel

# ============================================================
#  مرحله ۲: ایمیج نهایی — حداقلی، بدون ابزار build، بدون root
# ============================================================
FROM ${BASE_IMAGE} AS runtime

LABEL org.opencontainers.image.title="RLFW_BaleBot" \
      org.opencontainers.image.description="ربات لیگ کتابخوانی برای پیام‌رسان بله" \
      org.opencontainers.image.licenses="MIT"

# به‌روزرسانی امنیتی پکیج‌های سیستمی (اول Debian اصلی، بعد آینه‌ها؛ بهترین تلاش)
ARG APT_MIRRORS="http://mirror.arvancloud.ir/debian http://ftp.de.debian.org/debian http://mirrors.kernel.org/debian http://ftp.us.debian.org/debian"
COPY docker/apt_retry.sh /usr/local/bin/apt_retry.sh
RUN APT_MIRRORS="${APT_MIRRORS}" sh /usr/local/bin/apt_retry.sh ca-certificates \
    && rm -f /usr/local/bin/apt_retry.sh \
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
