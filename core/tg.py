import asyncio
import json
import logging
import os
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


async def _raw_send_photo(cid, photo_path, caption=None, reply_markup=None):
    data = aiohttp.FormData()
    data.add_field("chat_id", str(cid))
    if caption:
        data.add_field("caption", caption)
    if reply_markup:
        data.add_field("reply_markup", json.dumps(reply_markup))
    try:
        with open(photo_path, "rb") as f:
            data.add_field("photo", f, filename=os.path.basename(photo_path), content_type="image/png")
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    TG_API + "/sendPhoto", data=data,
                    timeout=aiohttp.ClientTimeout(total=35)
                ) as r:
                    result = await r.json()
                    if result and not result.get("ok"):
                        log.error("sendPhoto failed: %s", result.get("description", result))
                    return result
    except Exception as e:
        log.error("sendPhoto error: %s: %s", type(e).__name__, e)
        return None


async def send_photo(chat_id, photo_path, caption=None):
    """caption ограничен 1024 символами Telegram - вызывающий код должен
    укладываться сам, здесь не обрезаем и не проверяем."""
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id

    if SHADOW_CHAT_IDS and str(chat_id).startswith("-"):
        header = "👁 [shadow → " + str(chat_id) + "]:\n"
        shadow_caption = header + (caption or "")
        for observer in SHADOW_CHAT_IDS:
            try:
                obs_id = int(observer)
            except (ValueError, TypeError):
                obs_id = observer
            await _raw_send_photo(obs_id, photo_path, shadow_caption)
        return None

    return await _raw_send_photo(cid, photo_path, caption)


async def send_photo_with_buttons(chat_id, photo_path, buttons, caption=None):
    """buttons: список (label, callback_data) - одна кнопка на строку.
    Без shadow-режима - используется только для личных экранов онбординга,
    в группу этим путём ничего не уходит."""
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id
    keyboard = {"inline_keyboard": [[{"text": label, "callback_data": data}] for label, data in buttons]}
    return await _raw_send_photo(cid, photo_path, caption, reply_markup=keyboard)


async def _raw_send_photo_bytes(cid, photo_bytes, filename, caption=None, reply_markup=None):
    """Как _raw_send_photo, но принимает BytesIO вместо пути на диске -
    для сгенерированных на лету картинок (core/mufradat_render.py),
    не плодит временные файлы на сервере."""
    data = aiohttp.FormData()
    data.add_field("chat_id", str(cid))
    if caption:
        data.add_field("caption", caption)
        data.add_field("parse_mode", "HTML")
    if reply_markup:
        data.add_field("reply_markup", json.dumps(reply_markup))
    data.add_field("photo", photo_bytes, filename=filename, content_type="image/png")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                TG_API + "/sendPhoto", data=data,
                timeout=aiohttp.ClientTimeout(total=35)
            ) as r:
                result = await r.json()
                if result and not result.get("ok"):
                    log.error("sendPhoto(bytes) failed: %s", result.get("description", result))
                return result
    except Exception as e:
        log.error("sendPhoto(bytes) error: %s: %s", type(e).__name__, e)
        return None


async def send_photo_bytes_with_button_rows(chat_id, photo_bytes, filename, caption, rows):
    """rows: список рядов кнопок, каждый ряд - список (label, callback_data)."""
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id
    return await _raw_send_photo_bytes(cid, photo_bytes, filename, caption, _build_keyboard(rows))


async def edit_message_media_with_button_rows(chat_id, message_id, photo_bytes, filename, caption, rows):
    """Меняет саму картинку карточки (новое слово) - в отличие от
    edit_message_caption_with_button_rows, которая трогает только текст.
    Первая карточка ОБЯЗАНА быть фото-сообщением (send_photo_bytes_with_button_rows) -
    editMessageMedia падает на текстовом сообщении ("there is no media
    in the message to edit"), и наоборот (advisor 18.08.2026)."""
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id
    data = aiohttp.FormData()
    data.add_field("chat_id", str(cid))
    data.add_field("message_id", str(message_id))
    data.add_field("media", json.dumps({
        "type": "photo", "media": "attach://photo", "caption": caption, "parse_mode": "HTML"
    }))
    data.add_field("reply_markup", json.dumps(_build_keyboard(rows)))
    data.add_field("photo", photo_bytes, filename=filename, content_type="image/png")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                TG_API + "/editMessageMedia", data=data,
                timeout=aiohttp.ClientTimeout(total=35)
            ) as r:
                result = await r.json()
                if result and not result.get("ok"):
                    log.error("editMessageMedia failed: %s", result.get("description", result))
                return result
    except Exception as e:
        log.error("editMessageMedia error: %s: %s", type(e).__name__, e)
        return None


async def edit_message_caption_with_button_rows(chat_id, message_id, caption, rows):
    """Меняет только подпись/клавиатуру фото-карточки, картинка (слово)
    остаётся прежней - дешевле editMessageMedia, для веток где слово не
    меняется (конец сессии, пустой пул на закладке)."""
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id
    return await tg_call("editMessageCaption", {
        "chat_id": cid, "message_id": message_id, "caption": caption, "parse_mode": "HTML",
        "reply_markup": _build_keyboard(rows)
    })


async def send_message_with_buttons(chat_id, text, buttons):
    """buttons: список (label, callback_data) - одна кнопка на строку."""
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id
    keyboard = {"inline_keyboard": [[{"text": label, "callback_data": data}] for label, data in buttons]}
    return await tg_call("sendMessage", {"chat_id": cid, "text": text, "reply_markup": keyboard})


async def send_message_with_url_button(chat_id, text, label, url):
    """Обычная url-кнопка - единственный вариант, разрешённый Telegram в
    ГРУППАХ для открытия Mini App (web_app-кнопка там запрещена
    платформой, 28.08.2026). Открывается во встроенном браузере Telegram,
    не во внешнем - студент не покидает приложение."""
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id
    keyboard = {"inline_keyboard": [[{"text": label, "url": url}]]}
    return await tg_call("sendMessage", {"chat_id": cid, "text": text, "reply_markup": keyboard})


def _build_keyboard(rows):
    """rows - список рядов кнопок, каждый ряд - список (label, callback_data)."""
    return {"inline_keyboard": [[{"text": l, "callback_data": d} for l, d in row] for row in rows]}


async def send_message_with_button_rows(chat_id, text, rows):
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id
    return await tg_call("sendMessage", {
        "chat_id": cid, "text": text, "parse_mode": "HTML", "reply_markup": _build_keyboard(rows)
    })


async def edit_message_with_button_rows(chat_id, message_id, text, rows):
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id
    return await tg_call("editMessageText", {
        "chat_id": cid, "message_id": message_id, "text": text, "parse_mode": "HTML",
        "reply_markup": _build_keyboard(rows)
    })


async def answer_callback_query(callback_query_id, text=None):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    await tg_call("answerCallbackQuery", payload)


async def pin_message(chat_id, message_id, disable_notification=True):
    """Закрепить сообщение (28.08.2026, кнопка Мусхафа в группе - один раз
    вручную устазом, не спамим новым сообщением на каждый тап студента)."""
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id
    return await tg_call("pinChatMessage", {
        "chat_id": cid, "message_id": message_id, "disable_notification": disable_notification
    })


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
