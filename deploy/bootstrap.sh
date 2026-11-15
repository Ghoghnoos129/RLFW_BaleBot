#!/usr/bin/env bash
#
# اسکریپت یک‌بار-اجرا برای آماده‌سازی سرور جهت دیپلوی خودکار از طریق وبهوک گیت‌هاب.
# فقط روی سروری اجرا کنید که پروژه از قبل در /opt/reading-league-bot کلون شده باشد
# (به بخش «نصب روی سرور» در deploy/README.md نگاه کنید).
#
# اجرا:   sudo bash deploy/bootstrap.sh
#
set -euo pipefail

APP_DIR="/opt/reading-league-bot"
DEPLOY_USER="webhook"
LOG_DIR="/var/log/reading-league-bot"

if [ "$(id -u)" -ne 0 ]; then
    echo "خطا: این اسکریپت باید با روت اجرا شود (sudo bash deploy/bootstrap.sh)" >&2
    exit 1
fi

if [ ! -d "$APP_DIR/.git" ]; then
    echo "خطا: $APP_DIR یک ریپوی گیت نیست." >&2
    echo "اول طبق README پروژه را همان‌جا clone کنید، بعد این اسکریپت را اجرا کنید." >&2
    exit 1
fi

echo "== ۱) ساخت کاربر سیستمی بدون shell برای دریافت‌کننده وبهوک =="
if ! id "$DEPLOY_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$DEPLOY_USER"
    echo "کاربر $DEPLOY_USER ساخته شد."
else
    echo "کاربر $DEPLOY_USER از قبل وجود دارد."
fi

echo "== ۲) ساخت پوشه‌های لازم =="
mkdir -p "$LOG_DIR"
chown "$DEPLOY_USER:$DEPLOY_USER" "$LOG_DIR"
mkdir -p "$APP_DIR/.deploy"
mkdir -p "$(dirname /var/lock/reading-league-bot-deploy.lock)"

echo "== ۳) کلید SSH اختصاصی برای کلون/pull ریپوی پرایوت (در صورت نبود) =="
if [ ! -f "$APP_DIR/.deploy/id_ed25519" ]; then
    ssh-keygen -t ed25519 -C "reading-league-bot-deploy-$(hostname)" -f "$APP_DIR/.deploy/id_ed25519" -N ""
    echo
    echo ">>> این کلید عمومی را به عنوان Deploy Key (فقط خواندنی / Read-only) در گیت‌هاب اضافه کنید:"
    echo "    مخزن شما -> Settings -> Deploy keys -> Add deploy key"
    echo
    cat "$APP_DIR/.deploy/id_ed25519.pub"
    echo
    read -r -p "بعد از افزودن کلید بالا در گیت‌هاب، اینتر را بزنید تا ادامه یابد... " _
else
    echo "کلید deploy از قبل وجود دارد، رد شد."
fi
chmod 600 "$APP_DIR/.deploy/id_ed25519"
chmod 644 "$APP_DIR/.deploy/id_ed25519.pub"

echo "== ۴) دریافت کلید میزبان گیت‌هاب (برای جلوگیری از حمله مرد میانی روی SSH) =="
if [ ! -f "$APP_DIR/.deploy/known_hosts" ]; then
    ssh-keyscan -t ed25519 github.com > "$APP_DIR/.deploy/known_hosts" 2>/dev/null
    echo ">>> این فینگرپرینت را حتما با فینگرپرینت رسمی گیت‌هاب مقایسه کنید:"
    echo "    https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints"
    ssh-keygen -lf "$APP_DIR/.deploy/known_hosts"
    echo
else
    echo "known_hosts از قبل وجود دارد، رد شد."
fi

echo "== ۵) تولید رمز مشترک وبهوک و مسیر تصادفی (اگر هنوز نساخته‌اید) =="
WEBHOOK_ENV="$APP_DIR/deploy/webhook.env"
if [ ! -f "$WEBHOOK_ENV" ]; then
    SECRET="$(openssl rand -hex 32)"
    TOKEN="$(openssl rand -hex 16)"
    cat > "$WEBHOOK_ENV" <<EOF
WEBHOOK_SECRET=$SECRET
WEBHOOK_PATH=/hooks/$TOKEN
DEPLOY_BRANCH=main
LISTEN_HOST=127.0.0.1
LISTEN_PORT=9001
WEBHOOK_LOG_PATH=$LOG_DIR/webhook.log
EOF
    chmod 600 "$WEBHOOK_ENV"
    chown "$DEPLOY_USER:$DEPLOY_USER" "$WEBHOOK_ENV"
    echo
    echo ">>> این دو مقدار را هنگام ساخت وبهوک در تنظیمات ریپوی گیت‌هاب وارد کنید:"
    echo "    Payload URL : https://YOUR-DOMAIN/hooks/$TOKEN"
    echo "    Secret      : $SECRET"
    echo "    Content type: application/json"
    echo "    رویدادها    : فقط 'push'"
    echo
else
    echo "deploy/webhook.env از قبل وجود دارد، رد شد (برای تغییر رمز، دستی ویرایش کنید)."
fi

echo "== ۶) قفل کردن مالکیت و دسترسی deploy.sh (فقط روت بتواند تغییرش دهد) =="
chown root:root "$APP_DIR/deploy/deploy.sh"
chmod 700 "$APP_DIR/deploy/deploy.sh"

echo "== ۷) نصب قانون sudoers محدود =="
SUDOERS_DST="/etc/sudoers.d/reading-league-bot-deploy"
install -m 440 -o root -g root "$APP_DIR/deploy/sudoers-reading-league-bot-deploy" "$SUDOERS_DST"
if ! visudo -cf "$SUDOERS_DST"; then
    echo "خطا: فایل sudoers نامعتبر است، حذف شد." >&2
    rm -f "$SUDOERS_DST"
    exit 1
fi
echo "قانون sudoers نصب و تایید شد."

echo "== ۸) نصب و فعال‌سازی سرویس systemd =="
cp "$APP_DIR/deploy/webhook-listener.service" /etc/systemd/system/webhook-listener.service
systemctl daemon-reload
systemctl enable --now webhook-listener.service

echo
echo "✅ تمام شد. وضعیت سرویس:"
systemctl --no-pager status webhook-listener.service || true

cat <<'EOF'

مراحل باقی‌مانده (دستی):
  1) Nginx را طبق deploy/nginx-webhook.conf تنظیم کنید (دامنه و مسیر /hooks/... را جایگزین کنید)
     و با certbot گواهی TLS بگیرید.
  2) فایروال را فقط روی پورت‌های 22 (SSH)، 80 و 443 باز نگه دارید؛ پورت 9001 نباید از
     بیرون در دسترس باشد (پیش‌فرض همین‌طور است چون روی 127.0.0.1 گوش می‌دهد).
  3) در تنظیمات ریپوی گیت‌هاب، وبهوکی با Payload URL و Secret بالا بسازید (فقط رویداد push).
  4) یک commit آزمایشی push کنید و لاگ‌ها را ببینید:
       journalctl -u webhook-listener -f
       tail -f /var/log/reading-league-bot/deploy.log
EOF
