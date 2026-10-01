import asyncio
import json
import logging
import os
import aiohttp
from config import TG_API, SHADOW_CHAT_IDS
from core import app_route
from core.feed import record_outgoing

log = logging.getLogger(__name__)

# Имя бота (@username) — узнаётся один раз при старте из getMe (bot.py) и
# нужно веб-входу, чтобы собрать ссылку t.me/<бот>?start=login_<код>
# (10.09.2026). В конфиге его нет и не должно быть: у мужского и женского
# процессов имена разные, а токен и так у каждого свой.
_bot_username = ""


def set_bot_username(name):
    global _bot_username
    _bot_username = (name or "").lstrip("@")


def get_bot_username():
    return _bot_username


# Личка через @YassirAppBot (01.10.2026, core/app_route.py): эти методы в
# личный чат студента, чей канал - YassirApp, уходят его токеном. Решение и
# запасной путь - здесь, в нижней точке, как и лента: выше десятки send_*.
_ROUTED = {"sendMessage", "sendPhoto", "sendVoice", "sendDocument", "sendAudio", "sendVideo",
           "sendChatAction", "editMessageText", "editMessageReplyMarkup", "editMessageCaption",
           "editMessageMedia", "deleteMessage"}


async def _routed(method, chat_id, attempt):
    """attempt(base) -> ответ Telegram. Канал YassirApp - сначала им; явный
    отказ - старым путём (свой бот). Отказ «заблокировал / не начинал» ещё и
    снимает человека с YassirApp. Сеть молчит (None) - не повторяем: сообщение
    могло уйти, дубль человек заметит."""
    if method in _ROUTED and app_route.via_app(chat_id):
        data = await attempt(app_route.api_base(), "app ")
        if data is None or data.get("ok"):
            return data
        if app_route.unreachable(data):
            app_route.mark_blocked(chat_id)
        log.info("%s %s через YassirApp не прошёл - старым путём", method, chat_id)
    return await attempt(TG_API, "")


async def tg_call(method, payload=None, timeout=35):
    payload = payload or {}

    async def attempt(base, label):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    base + "/" + method, json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as r:
                    data = await r.json()
                    if data and not data.get("ok"):
                        log.error("tg_call %s%s failed: %s", label, method, data.get("description", data))
                    return data
        except Exception as e:
            log.error("tg_call %s%s error: %s: %s", label, method, type(e).__name__, e)
            return None

    data = await _routed(method, payload.get("chat_id"), attempt)
    # Лента (11.09.2026): свои сообщения бот через getUpdates не получает -
    # пишем их здесь, в общей точке. Выше tg_call десяток send_*, и
    # перехватывать каждую значило бы забыть следующую. Метод фильтруем:
    # через tg_call ходят и getUpdates, и getMe, и баны.
    if method == "sendMessage" and data and data.get("ok"):
        record_outgoing(payload.get("chat_id"), result=data, text=payload.get("text"))
    return data


async def _post_form(method, cid, build, timeout=35):
    """Multipart-отправка (фото, голос) с тем же выбором канала. build() -
    свежий FormData на каждую попытку: использованный второй раз не уходит."""
    async def attempt(base, label):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    base + "/" + method, data=build(),
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as r:
                    result = await r.json()
                    if result and not result.get("ok"):
                        log.error("%s%s failed: %s", label, method, result.get("description", result))
                    return result
        except Exception as e:
            log.error("%s%s error: %s: %s", label, method, type(e).__name__, e)
            return None
    return await _routed(method, cid, attempt)


def _as_bytes(body):
    """BytesIO читается один раз - запасной попытке нужны сами байты."""
    return body.getvalue() if hasattr(body, "getvalue") else body


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
        await pace(0.05)
    return last


# Пауза между обращениями к Telegram: у Bot API есть лимиты, и рассылка без
# передышки ловит 429. Отдельная функция, а не голый asyncio.sleep, потому что
# тесты её отключают (tests/conftest.py): полный прогон честно ждал этих пауз
# и шёл десять минут вместо полутора (20.09.2026).
PACING = True


async def pace(seconds):
    if PACING:
        await asyncio.sleep(seconds)


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
    try:
        with open(photo_path, "rb") as f:
            body = f.read()
    except OSError as e:
        log.error("sendPhoto error: %s: %s", type(e).__name__, e)
        return None

    def build():
        data = aiohttp.FormData()
        data.add_field("chat_id", str(cid))
        if caption:
            data.add_field("caption", caption)
        if reply_markup:
            data.add_field("reply_markup", json.dumps(reply_markup))
        data.add_field("photo", body, filename=os.path.basename(photo_path), content_type="image/png")
        return data

    result = await _post_form("sendPhoto", cid, build)
    if result and result.get("ok"):
        record_outgoing(cid, result=result, text=caption, kind="photo")
    return result


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


async def _raw_send_photo_bytes(cid, photo_bytes, filename, caption=None, reply_markup=None,
                                reply_to_message_id=None):
    """Как _raw_send_photo, но принимает BytesIO вместо пути на диске -
    для сгенерированных на лету картинок (снимок строки при сдаче хифза),
    не плодит временные файлы на сервере."""
    body = _as_bytes(photo_bytes)

    def build():
        data = aiohttp.FormData()
        data.add_field("chat_id", str(cid))
        if caption:
            data.add_field("caption", caption)
            data.add_field("parse_mode", "HTML")
        if reply_markup:
            data.add_field("reply_markup", json.dumps(reply_markup))
        if reply_to_message_id:
            data.add_field("reply_to_message_id", str(reply_to_message_id))
        data.add_field("photo", body, filename=filename, content_type="image/png")
        return data

    result = await _post_form("sendPhoto", cid, build)
    if result and result.get("ok"):
        record_outgoing(cid, result=result, text=caption, kind="photo")
    return result


async def send_photo_bytes(chat_id, photo_bytes, filename, caption=None, reply_to_message_id=None):
    """Картинка из памяти в группу, с поддержкой shadow-режима (как
    send_photo) - в отличие от send_photo_bytes_with_button_rows, та
    только для личных карточек тренажёра."""
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id
    if SHADOW_CHAT_IDS and str(chat_id).startswith("-"):
        header = "👁 [shadow → " + str(chat_id) + "]:\n"
        for observer in SHADOW_CHAT_IDS:
            try:
                obs_id = int(observer)
            except (ValueError, TypeError):
                obs_id = observer
            await _raw_send_photo_bytes(obs_id, photo_bytes, filename, header + (caption or ""))
        return None
    return await _raw_send_photo_bytes(cid, photo_bytes, filename, caption,
                                       reply_to_message_id=reply_to_message_id)


async def send_voice_bytes(chat_id, voice_bytes, caption=None, reply_to_message_id=None):
    """Голосовое сообщение из памяти (сдача 40+40, записанная в YassirApp).
    Telegram принимает в sendVoice ТОЛЬКО ogg/opus - конвертация лежит на
    вызывающем коде (core/mufradat_bot.transcode_to_ogg), здесь байты
    уходят как есть."""
    try:
        cid = int(str(chat_id))
    except (ValueError, TypeError):
        cid = chat_id
    body = _as_bytes(voice_bytes)

    def build():
        data = aiohttp.FormData()
        data.add_field("chat_id", str(cid))
        if caption:
            data.add_field("caption", caption)
        if reply_to_message_id:
            data.add_field("reply_to_message_id", str(reply_to_message_id))
        data.add_field("voice", body, filename="hifz.ogg", content_type="audio/ogg")
        return data

    result = await _post_form("sendVoice", cid, build, timeout=120)
    if result and result.get("ok"):
        record_outgoing(cid, result=result, text=caption, kind="voice")
    return result


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
    body = _as_bytes(photo_bytes)

    def build():
        data = aiohttp.FormData()
        data.add_field("chat_id", str(cid))
        data.add_field("message_id", str(message_id))
        data.add_field("media", json.dumps({
            "type": "photo", "media": "attach://photo", "caption": caption, "parse_mode": "HTML"
        }))
        data.add_field("reply_markup", json.dumps(_build_keyboard(rows)))
        data.add_field("photo", body, filename=filename, content_type="image/png")
        return data

    return await _post_form("editMessageMedia", cid, build)


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


async def approve_join_request(chat_id, user_id):
    return await tg_call("approveChatJoinRequest", {"chat_id": int(str(chat_id)), "user_id": int(str(user_id))})


async def decline_join_request(chat_id, user_id):
    return await tg_call("declineChatJoinRequest", {"chat_id": int(str(chat_id)), "user_id": int(str(user_id))})


async def unban_member(chat_id, user_id):
    return await tg_call("unbanChatMember", {
        "chat_id": int(str(chat_id)), "user_id": int(str(user_id)), "only_if_banned": True
    })
