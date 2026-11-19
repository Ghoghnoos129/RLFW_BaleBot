"""
لایه‌ی نازک ارتباط با Bot API بله (https://tapi.bale.ai).
فقط از متدهایی استفاده می‌کند که در مستندات رسمی بله مستند شده‌اند:
getUpdates / sendMessage / answerCallbackQuery / editMessageText
"""
import logging
import os
import requests

from app.config import API_BASE, BALE_TOKEN
from app.utils import split_text

log = logging.getLogger("bale_api")

_session = requests.Session()


def _call(method: str, payload: dict = None, timeout: int = 30):
    url = f"{API_BASE}/{method}"
    try:
        resp = _session.post(url, json=payload or {}, timeout=timeout)
        data = resp.json()
    except requests.RequestException as e:
        log.warning("network error calling %s: %s", method, e)
        return {"ok": False, "error": str(e)}
    except ValueError:
        log.warning("invalid json from %s: %s", method, resp.text[:300])
        return {"ok": False, "error": "invalid json"}

    if not data.get("ok"):
        log.warning("bale api error on %s: %s", method, data)
    return data


def get_updates(offset=None, limit=100, timeout=25):
    payload = {"limit": limit, "timeout": timeout}
    if offset is not None:
        payload["offset"] = offset
    # getUpdates از long-polling استفاده می‌کند؛ timeout سمت سرور کمی بیشتر در نظر گرفته می‌شود
    return _call("getUpdates", payload, timeout=timeout + 10)


def send_message(chat_id: int, text: str, reply_markup: dict = None, reply_to_message_id: int = None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id
    return _call("sendMessage", payload)


def answer_callback_query(callback_query_id: str, text: str = None, show_alert: bool = False):
    payload = {"callback_query_id": callback_query_id}
    if text is not None:
        payload["text"] = text
        payload["show_alert"] = show_alert
    return _call("answerCallbackQuery", payload)


def edit_message_text(chat_id: int, message_id: int, text: str, reply_markup: dict = None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return _call("editMessageText", payload)


def get_me():
    return _call("getMe", {})


def send_long(chat_id: int, text: str, reply_markup: dict = None):
    """پیام‌های بلند را به چند پیام تقسیم می‌کند؛ کیبورد (اگر باشد) روی آخرین پیام قرار می‌گیرد."""
    chunks = split_text(text)
    result = {"ok": False}
    for i, chunk in enumerate(chunks):
        markup = reply_markup if i == len(chunks) - 1 else None
        result = send_message(chat_id, chunk, reply_markup=markup)
    return result


def edit_or_send(chat_id: int, message_id, text: str, reply_markup: dict = None):
    """پیام موجود را ویرایش می‌کند (برای پنل‌های دکمه‌ای)؛ اگر نشد پیام تازه می‌فرستد."""
    if message_id:
        resp = edit_message_text(chat_id, message_id, text, reply_markup)
        if resp.get("ok"):
            return resp
        if "not modified" in str(resp.get("description", "")).lower():
            return resp
    return send_message(chat_id, text, reply_markup=reply_markup)


def send_document(chat_id: int, path: str, caption: str = None):
    """ارسال فایل (مثلاً فایل پشتیبان) با sendDocument."""
    url = f"{API_BASE}/sendDocument"
    try:
        with open(path, "rb") as f:
            resp = _session.post(
                url,
                data={"chat_id": chat_id, "caption": caption or ""},
                files={"document": (os.path.basename(path), f)},
                timeout=180,
            )
        data = resp.json()
    except (requests.RequestException, ValueError, OSError) as e:
        log.warning("sendDocument failed: %s", e)
        return {"ok": False, "error": str(e)}
    if not data.get("ok"):
        log.warning("bale api error on sendDocument: %s", data)
    return data


def get_file(file_id: str):
    return _call("getFile", {"file_id": file_id})


def download_file(file_path: str, dest: str, max_bytes: int = 50 * 1024 * 1024) -> bool:
    """فایل ارسال‌شده به ربات را از سرور بله دانلود می‌کند. True اگر موفق بود."""
    url = f"https://tapi.bale.ai/file/bot{BALE_TOKEN}/{file_path}"
    try:
        with _session.get(url, stream=True, timeout=120) as resp:
            if resp.status_code != 200:
                log.warning("download_file status %s", resp.status_code)
                return False
            size = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(65536):
                    size += len(chunk)
                    if size > max_bytes:
                        return False
                    f.write(chunk)
        return True
    except (requests.RequestException, OSError) as e:
        log.warning("download_file failed: %s", e)
        return False


_MEDIA_METHODS = {
    "photo": ("sendPhoto", "photo"),
    "video": ("sendVideo", "video"),
    "audio": ("sendAudio", "audio"),
    "voice": ("sendVoice", "voice"),
    "document": ("sendDocument", "document"),
}
CAPTION_LIMIT = 1000


def send_media(chat_id: int, kind: str, file_id: str, caption: str = None):
    """ارسال عکس/ویدیو/صوت/ویس/فایل با file_id (فایلی که قبلاً به ربات ارسال شده). کپشن بلند جدا ارسال می‌شود."""
    method, field = _MEDIA_METHODS[kind]
    payload = {"chat_id": chat_id, field: file_id}
    long_caption = bool(caption) and len(caption) > CAPTION_LIMIT
    if caption and not long_caption:
        payload["caption"] = caption
    resp = _call(method, payload, timeout=60)
    if long_caption and resp.get("ok"):
        send_long(chat_id, caption)
    return resp
