#!/usr/bin/env python3
"""
دریافت‌کننده‌ی وبهوک گیت‌هاب برای دیپلوی خودکار ربات لیگ کتابخوانی.

عمداً فقط از کتابخانه استاندارد پایتون استفاده می‌کند (بدون Flask/هیچ وابستگی خارجی)
تا نیاز به نصب پکیج روی سرور و سطح حمله کمینه بماند.

این سرویس فقط باید روی 127.0.0.1 اجرا شود و فقط Nginx (با TLS) آن را از بیرون در دسترس
قرار دهد — هرگز مستقیم به اینترنت expose نشود.

لایه‌های امنیتی:
  1) هر درخواست باید امضای HMAC-SHA256 معتبر داشته باشد (هدر X-Hub-Signature-256)
     که گیت‌هاب با WEBHOOK_SECRET مشترک تولید می‌کند — با hmac.compare_digest مقایسه می‌شود
     تا در برابر timing attack هم مقاوم باشد.
  2) مسیر درخواست باید دقیقاً با WEBHOOK_PATH (شامل یک توکن تصادفی) برابر باشد — این فقط
     لایه مبهم‌سازی اضافه است، نه جایگزین HMAC.
  3) فقط رویداد push و فقط روی برنچ تنظیم‌شده (DEPLOY_BRANCH) پذیرفته می‌شود.
  4) دیپلوی واقعی هرگز مستقیم در این پردازش اجرا نمی‌شود؛ با «sudo -n» یک اسکریپت ثابت و
     مالکیت‌روت (deploy.sh) فراخوانی می‌شود. کاربری که این سرویس با آن اجرا می‌شود هیچ
     دسترسی مستقیم به docker یا روت ندارد؛ sudoers فقط اجازه‌ی همان یک دستور دقیق را می‌دهد.
  5) با یک Lock داخلی از اجرای هم‌زمان چند دیپلوی جلوگیری می‌شود (قفل سطح بالاتر هم در
     خود deploy.sh با flock وجود دارد).
"""
import hashlib
import hmac
import http.server
import ipaddress
import json
import logging
import os
import socketserver
import subprocess
import sys
import threading

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/hooks/change-me")
EXPECTED_BRANCH = os.environ.get("DEPLOY_BRANCH", "main")
DEPLOY_CMD = os.environ.get(
    "DEPLOY_CMD", "sudo -n /opt/RLFW_BaleBot/deploy/deploy.sh"
).split()
LISTEN_HOST = os.environ.get("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9001"))
LOG_PATH = os.environ.get("WEBHOOK_LOG_PATH", "/var/log/RLFW_BaleBot/webhook.log")
DEPLOY_TIMEOUT = int(os.environ.get("DEPLOY_TIMEOUT_SECONDS", "600"))

# اختیاری: محدودسازی اضافه بر اساس IP (defense-in-depth؛ HMAC همچنان اصل ماجراست چون
# رنج آی‌پی‌های گیت‌هاب تغییر می‌کند). مثال مقدار: "140.82.112.0/20,143.55.64.0/20"
_raw_allowlist = os.environ.get("GITHUB_IP_ALLOWLIST", "").strip()
IP_ALLOWLIST = []
if _raw_allowlist:
    for cidr in _raw_allowlist.split(","):
        cidr = cidr.strip()
        if cidr:
            try:
                IP_ALLOWLIST.append(ipaddress.ip_network(cidr))
            except ValueError:
                pass

os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
log = logging.getLogger("webhook")

deploy_lock = threading.Lock()

if not WEBHOOK_SECRET:
    log.error("WEBHOOK_SECRET تنظیم نشده؛ سرویس اجرا نمی‌شود (برای جلوگیری از پذیرش ناامن درخواست‌ها).")
    sys.exit(1)

if WEBHOOK_PATH in ("", "/", "/hooks/change-me"):
    log.error("WEBHOOK_PATH را به یک مقدار تصادفی و منحصربه‌فرد تغییر دهید (نه مقدار پیش‌فرض).")
    sys.exit(1)


def verify_signature(payload: bytes, signature_header: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


def ip_allowed(remote_ip: str) -> bool:
    if not IP_ALLOWLIST:
        return True  # محدودیت IP غیرفعال است؛ فقط به HMAC تکیه می‌کنیم
    try:
        addr = ipaddress.ip_address(remote_ip)
    except ValueError:
        return False
    return any(addr in net for net in IP_ALLOWLIST)


def run_deploy():
    if not deploy_lock.acquire(blocking=False):
        log.warning("دیپلویی از قبل در حال اجراست؛ این درخواست نادیده گرفته شد.")
        return
    try:
        log.info("شروع دیپلوی: %s", " ".join(DEPLOY_CMD))
        result = subprocess.run(
            DEPLOY_CMD,
            capture_output=True,
            text=True,
            timeout=DEPLOY_TIMEOUT,
        )
        log.info(
            "دیپلوی تمام شد (exit=%s)\n--- stdout ---\n%s\n--- stderr ---\n%s",
            result.returncode,
            result.stdout.strip(),
            result.stderr.strip(),
        )
    except subprocess.TimeoutExpired:
        log.error("دیپلوی بیش از %s ثانیه طول کشید و متوقف شد.", DEPLOY_TIMEOUT)
    except Exception:
        log.exception("خطای غیرمنتظره هنگام اجرای دیپلوی")
    finally:
        deploy_lock.release()


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "deploy-hook/1.0"

    def log_message(self, fmt, *args):  # noqa: A003 - امضای کلاس پایه است
        log.info("%s - %s", self.client_address[0], fmt % args)

    def _reject(self, code, msg="forbidden"):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(msg.encode())

    def do_POST(self):
        if not ip_allowed(self.client_address[0]):
            log.warning("درخواست از آی‌پی غیرمجاز رد شد: %s", self.client_address[0])
            self._reject(403, "forbidden")
            return

        if self.path != WEBHOOK_PATH:
            self._reject(404, "not found")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0 or content_length > 2_000_000:
            self._reject(400, "bad length")
            return
        body = self.rfile.read(content_length)

        signature = self.headers.get("X-Hub-Signature-256", "")
        if not verify_signature(body, signature):
            log.warning("امضای نامعتبر از %s", self.client_address[0])
            self._reject(403, "invalid signature")
            return

        event = self.headers.get("X-GitHub-Event", "")
        if event == "ping":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"pong")
            return
        if event != "push":
            self._reject(400, "unsupported event")
            return

        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError:
            self._reject(400, "invalid json")
            return

        ref = payload.get("ref", "")
        if ref != f"refs/heads/{EXPECTED_BRANCH}":
            log.info("push روی برنچ %s نادیده گرفته شد (فقط %s دیپلوی می‌شود)", ref, EXPECTED_BRANCH)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ignored: wrong branch")
            return

        log.info("push معتبر روی برنچ %s دریافت شد؛ دیپلوی در پس‌زمینه شروع می‌شود", EXPECTED_BRANCH)
        self.send_response(202)
        self.end_headers()
        self.wfile.write(b"accepted")

        threading.Thread(target=run_deploy, daemon=True).start()

    def do_GET(self):
        self._reject(404, "not found")


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    server = Server((LISTEN_HOST, LISTEN_PORT), Handler)
    log.info(
        "وبهوک دیپلوی روی %s:%s مسیر %s برای برنچ %s آماده است",
        LISTEN_HOST, LISTEN_PORT, WEBHOOK_PATH, EXPECTED_BRANCH,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
