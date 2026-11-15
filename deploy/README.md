# دیپلوی خودکار با وبهوک گیت‌هاب (پرایوت)

این راهنما مرحله‌به‌مرحله می‌گوید چطور ربات را به‌صورت Docker روی سرور خودتان بالا بیاورید
طوری که با هر `push` به برنچ `main` در ریپوی **پرایوت** گیت‌هاب، خودش به‌صورت امن روی سرور
دیپلوی (build + up) شود — بدون نیاز به GitHub Actions، بدون باز کردن پورت اضافه، و بدون
دادن دسترسی روت به فرآیندی که مستقیم از اینترنت درخواست می‌گیرد.

## معماری امنیتی، خلاصه

```
GitHub (push) ──HTTPS + HMAC──▶ Nginx (TLS, rate-limit) ──127.0.0.1──▶ webhook_listener.py
                                                                         (کاربر بدون‌دسترسی «webhook»)
                                                                                 │
                                                                     sudo -n (فقط همین یک دستور)
                                                                                 ▼
                                                                    deploy.sh (مالکیت روت، 700)
                                                                                 │
                                                                 git pull (با deploy key فقط-خواندنی)
                                                                        +
                                                                 docker compose build/up
```

نکات کلیدی طراحی:
- **فرآیندی که مستقیم درخواست اینترنتی می‌گیرد (`webhook_listener.py`) هیچ‌وقت روت یا
  دسترسی به docker ندارد.** حتی اگر این فرآیند به هر نحوی compromise شود، تنها کاری که
  می‌تواند بکند اجرای همان یک اسکریپت ثابت (`deploy.sh`) از طریق یک قانون `sudoers`
  محدود است — نه هر دستور دلخواه با روت.
- `deploy.sh` مالکیت `root:root` و دسترسی `700` دارد؛ کاربر `webhook` فقط می‌تواند آن را
  **اجرا** کند، نه بخواند یا تغییر دهد.
- گیت‌هاب هر درخواست را با **HMAC-SHA256** (هدر `X-Hub-Signature-256`) امضا می‌کند و
  `webhook_listener.py` این امضا را با `hmac.compare_digest` (مقاوم در برابر timing attack)
  اعتبارسنجی می‌کند؛ بدون امضای معتبر هیچ دیپلویی شروع نمی‌شود.
- کلون پروژه پرایوت روی سرور از طریق یک **Deploy Key** اختصاصی و **فقط-خواندنی** انجام
  می‌شود (نه توکن شخصی شما؛ اگر سرور هک شود این کلید فقط اجازه خواندن همین یک ریپو را
  می‌دهد، نه نوشتن و نه دسترسی به حساب گیت‌هاب شما).
- کانتینر ربات با کاربر غیر-روت، فایل‌سیستم read-only، و بدون هیچ Linux capability اجرا
  می‌شود (جزئیات در `Dockerfile` و `docker-compose.yml`).
- وبهوک روی `127.0.0.1` گوش می‌دهد و فقط Nginx (با TLS و rate-limit) آن را از بیرون قابل
  دسترس می‌کند.

---

## مرحله ۱: آماده‌سازی اولیه سرور (یک‌بار)

روی یک سرور لینوکسی (Ubuntu/Debian فرض شده) با دسترسی روت:

```bash
apt-get update
apt-get install -y git openssh-client curl ca-certificates gnupg

# نصب Docker (روش رسمی)
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# نصب Nginx و certbot برای TLS
apt-get install -y nginx certbot python3-certbot-nginx
```

فایروال را فقط روی پورت‌های لازم باز بگذارید (مثال با `ufw`):
```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```
(پورت ۹۰۰۱ که `webhook_listener.py` روی آن گوش می‌دهد نباید هیچ‌جا باز شود — چون فقط
روی `127.0.0.1` گوش می‌دهد، حتی بدون فایروال هم از بیرون قابل دسترس نیست.)

## مرحله ۲: کلون اولیه پروژه (دستی، یک‌بار)

چون ریپو پرایوت است، اول باید یک کلید deploy بسازید و قبل از هر `pull` خودکار، یک‌بار
دستی کلون کنید:

```bash
mkdir -p /opt/RLFW_BaleBot
cd /opt/RLFW_BaleBot
git init
mkdir -p .deploy
ssh-keygen -t ed25519 -C "RLFW_BaleBot-deploy" -f .deploy/id_ed25519 -N ""
cat .deploy/id_ed25519.pub
```

کلید عمومی چاپ‌شده را در گیت‌هاب اضافه کنید:
**ریپو شما → Settings → Deploy keys → Add deploy key** (تیک "Allow write access" را
**نزنید** — این کلید فقط باید خواندنی باشد).

سپس فینگرپرینت واقعی گیت‌هاب را بگیرید و با
[صفحه رسمی فینگرپرینت‌های SSH گیت‌هاب](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)
مقایسه کنید تا مطمئن شوید به سرور واقعی گیت‌هاب وصل می‌شوید، نه یک حمله مرد-میانی:

```bash
ssh-keyscan -t ed25519 github.com > .deploy/known_hosts
ssh-keygen -lf .deploy/known_hosts
```

حالا کلون واقعی را انجام دهید (مسیر ریپوی خودتان را جایگزین کنید):

```bash
export GIT_SSH_COMMAND="ssh -i /opt/RLFW_BaleBot/.deploy/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/opt/RLFW_BaleBot/.deploy/known_hosts"
cd /opt
rm -rf RLFW_BaleBot_tmp
git clone git@github.com:YOUR_USERNAME/YOUR_REPO.git RLFW_BaleBot_tmp
# محتوای کلون‌شده را جایگزین پوشه‌ای کنید که .deploy را در آن ساختید:
rsync -a --exclude='.deploy' RLFW_BaleBot_tmp/ /opt/RLFW_BaleBot/
rm -rf RLFW_BaleBot_tmp
```

(اگر پروژه را به ریپوی گیت‌هاب خودتان push نکرده‌اید، اول این پوشه `RLFW_BaleBot`
که از من گرفته‌اید را به یک ریپوی پرایوت جدید push کنید.)

فایل `.env` واقعی را بسازید (این فایل هرگز نباید وارد گیت شود؛ در `.gitignore`/`.dockerignore`
هم هست):
```bash
cd /opt/RLFW_BaleBot
cp .env.example .env
nano .env   # BALE_TOKEN را وارد کنید و یک ADMIN_SETUP_CODE دلخواه بگذارید
# (بعد از بالا آمدن ربات، همین کد را به ربات پیام بدهید تا مدیر اصلی شوید — به README اصلی پروژه نگاه کنید)
```

## مرحله ۳: اجرای bootstrap (یک‌بار)

```bash
cd /opt/RLFW_BaleBot
sudo bash deploy/bootstrap.sh
```

این اسکریپت:
1. کاربر سیستمی بدون shell به نام `webhook` می‌سازد (اگر کلید SSH را در مرحله ۲ نساخته
   باشید، همین‌جا هم می‌سازد و از شما می‌خواهد کلید عمومی را در گیت‌هاب اضافه کنید).
2. یک **Secret** تصادفی ۶۴ کاراکتری و یک **مسیر تصادفی** (`/hooks/...`) برای وبهوک تولید
   و در `deploy/webhook.env` ذخیره می‌کند — این دو مقدار را در خروجی می‌بینید.
3. مالکیت `deploy.sh` را `root:root` و دسترسی `700` می‌کند.
4. قانون محدود `sudoers` را نصب و با `visudo -cf` اعتبارسنجی می‌کند.
5. سرویس `systemd` به نام `RLFW_BaleBot-webhook` را نصب و فعال می‌کند.

خروجی را نگه دارید — مقدار **Payload URL** و **Secret** را در مرحله بعد لازم دارید.

## مرحله ۴: تنظیم Nginx + TLS

فایل `deploy/nginx-webhook.conf` را کپی و ویرایش کنید:
```bash
cp /opt/RLFW_BaleBot/deploy/nginx-webhook.conf /etc/nginx/sites-available/RLFW_BaleBot-webhook.conf
nano /etc/nginx/sites-available/RLFW_BaleBot-webhook.conf
# deploy.yourdomain.com -> دامنه واقعی خودتان
# /hooks/REPLACE_WITH_RANDOM_TOKEN -> همان مسیری که bootstrap.sh ساخت (WEBHOOK_PATH)

ln -s /etc/nginx/sites-available/RLFW_BaleBot-webhook.conf /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# گرفتن گواهی TLS (دامنه باید از قبل به IP این سرور اشاره کند)
certbot --nginx -d deploy.yourdomain.com
```

## مرحله ۵: ساخت وبهوک در گیت‌هاب

در گیت‌هاب: **ریپو → Settings → Webhooks → Add webhook**
- **Payload URL:** همان مقداری که `bootstrap.sh` چاپ کرد (مثلاً `https://deploy.yourdomain.com/hooks/XXXX`)
- **Content type:** `application/json`
- **Secret:** همان مقداری که `bootstrap.sh` چاپ کرد
- **Which events:** فقط «Just the push event»
- SSL verification: فعال بماند (Enable SSL verification)

## مرحله ۶: اولین دیپلوی دستی (برای اطمینان قبل از اتکا به وبهوک)

```bash
cd /opt/RLFW_BaleBot
sudo ./deploy/deploy.sh
docker compose ps
```
اگر این دستی کار کرد، یعنی مسیر گیت + داکر سالم است و فقط کافی‌ست وبهوک را تست کنید.

## مرحله ۷: تست وبهوک

یک تغییر کوچک commit و push کنید، سپس:
```bash
journalctl -u RLFW_BaleBot-webhook -f      # لاگ دریافت‌کننده وبهوک
tail -f /var/log/RLFW_BaleBot/deploy.log   # لاگ خود دیپلوی
```
در گیت‌هاب هم زیر **Settings → Webhooks → (وبهوک شما) → Recent Deliveries** می‌توانید
ببینید درخواست با چه کد وضعیتی جواب داده شده (باید ۲۰۲ باشد).

---

## عیب‌یابی سریع

| علامت | احتمالاً یعنی |
|---|---|
| در Recent Deliveries کد ۴۰۳ می‌بینید | Secret در گیت‌هاب با `WEBHOOK_SECRET` در `deploy/webhook.env` یکی نیست |
| کد ۴۰۴ می‌بینید | مسیر در Payload URL گیت‌هاب با `WEBHOOK_PATH` یکی نیست، یا Nginx هنوز location درست را ندارد |
| کد ۲۰۲ می‌گیرید ولی تغییری اعمال نمی‌شود | `journalctl -u RLFW_BaleBot-webhook -f` و `deploy.log` را ببینید؛ احتمالا خطای `sudo` یا git |
| `sudo: a password is required` در deploy.log | قانون sudoers نصب نشده یا کاربر اجراکننده webhook_listener برابر `webhook` نیست |
| خطای SSH در `git fetch` | `known_hosts` یا کلید deploy درست تنظیم نشده؛ با همان کاربر root دستی تست کنید:<br>`sudo -u root ssh -i /opt/RLFW_BaleBot/.deploy/id_ed25519 -T git@github.com` |

## چرخش (Rotate) Secret یا کلید در صورت نیاز

- **رمز وبهوک:** مقدار جدید را در `deploy/webhook.env` بگذارید، سرویس را ری‌استارت کنید
  (`systemctl restart RLFW_BaleBot-webhook`)، و همان مقدار را در تنظیمات وبهوک گیت‌هاب هم
  به‌روز کنید.
- **Deploy key:** یک کلید جدید بسازید، در گیت‌هاب جایگزین کنید، کلید قدیمی را از گیت‌هاب
  حذف کنید، فایل‌های `.deploy/id_ed25519*` را عوض کنید.
