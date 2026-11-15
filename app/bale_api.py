"""
لایه‌ی نازک ارتباط با Bot API بله (https://tapi.bale.ai).
فقط از متدهایی استفاده می‌کند که در مستندات رسمی بله مستند شده‌اند:
getUpdates / sendMessage / answerCallbackQuery / editMessageText
"""
import logging
import requests

from app.config import API_BASE

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
