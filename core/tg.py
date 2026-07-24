import asyncio
import logging
import aiohttp
from config import TG_API, SHADOW_CHAT_IDS

log = logging.getLogger(__name__)


async def tg_call(method, payload=None, timeout=35):
    url = TG_API + "/" + method
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                url, json=(payload or {}),
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as r:
                data = await r.json()
                if data and not data.get("ok"):
                    log.error("tg_call %s failed: %s", method, data.get("description", data))
                return data
    except Exception as e:
        log.error("tg_call %s error: %s: %s", method, type(e).__name__, e)
        return None


async def _raw_send(cid, text, reply_to_message_id=None):
    parts = []
    t = text or ""
    while len(t) > 4096:
        cut = t.rfind("\n", 0, 4096)
        if cut <= 0:
            cut = 4096
        parts.append(t[:cut])
        t = t[cut:]
    parts.append(t)
    last = None
    for p in parts:
        if not p:
            continue
        params = {"chat_id": cid, "text": p}
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id
            params["allow_sending_without_reply"] = True
        last = await tg_call("sendMessage", params)
        await asyncio.sleep(0.05)
    return last


async def send_message(chat_id, text, reply_to_message_id=None):
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id

    # Shadow mode: для ГРУПП — пересылаем наблюдателям вместо отправки в группу
    if SHADOW_CHAT_IDS and str(chat_id).startswith("-"):
        header = "👁 [shadow → " + str(chat_id) + "]:\n"
        shadow_text = header + (text or "")
        for observer in SHADOW_CHAT_IDS:
            try:
                obs_id = int(observer)
            except (ValueError, TypeError):
                obs_id = observer
            await _raw_send(obs_id, shadow_text)
        return None  # в группу НЕ отправляем

    return await _raw_send(cid, text or "", reply_to_message_id=reply_to_message_id)


async def send_message_with_buttons(chat_id, text, buttons):
    """buttons: список (label, callback_data) - одна кнопка на строку."""
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id
    keyboard = {"inline_keyboard": [[{"text": label, "callback_data": data}] for label, data in buttons]}
    return await tg_call("sendMessage", {"chat_id": cid, "text": text, "reply_markup": keyboard})


async def answer_callback_query(callback_query_id, text=None):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    await tg_call("answerCallbackQuery", payload)


async def remove_message_keyboard(chat_id, message_id):
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id
    await tg_call("editMessageReplyMarkup", {
        "chat_id": cid, "message_id": message_id, "reply_markup": {"inline_keyboard": []}
    })


async def get_dm_start_link():
    """Ссылка-приглашение в личку с ботом (https://t.me/<username>?start=go).
    Юзернейм берётся через getMe каждый раз — на случай разных ботов (муж/жен)."""
    me = await tg_call("getMe")
    username = (me or {}).get("result", {}).get("username") if me else None
    if not username:
        log.error("get_dm_start_link: getMe failed")
        return None
    return "https://t.me/" + username + "?start=go"


async def ban_member(chat_id, user_id):
    return await tg_call("banChatMember", {"chat_id": int(str(chat_id)), "user_id": int(str(user_id))})


async def unban_member(chat_id, user_id):
    return await tg_call("unbanChatMember", {
        "chat_id": int(str(chat_id)), "user_id": int(str(user_id)), "only_if_banned": True
    })
