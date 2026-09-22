"""@YassirAppBot - одна дверь для обеих половин (22.09.2026).

Зачем. До сих пор у проекта было две двери в Telegram - мужской и женский
боты, - и всё, что смотрит наружу, приходилось делить надвое: кнопка входа
на сайте вела в мужской бот (сестёр он пересылал к соседу), в настройках
было два приглашения - «брату» и «сестре». Решение пользователя: «теперь
истина - база», двойственность убираем. Наружу смотрит один бот, а кто
брат, кто сестра - он узнаёт по базам и по ответу человека.

Что он делает. Только встречает и показывает дорогу - никого не учит,
групп не ведёт, в базы половин не пишет:
  - вход на сайт: ссылка t.me/YassirAppBot?start=login_<код>; бот ищет
    человека в обеих базах и подтверждает код ДЛЯ ЕГО половины - сессию
    выдаст процесс этой половины из своей базы (core/web_auth.py), как и
    раньше, когда код подтверждал мужской бот;
  - знакомому - «твой бот - @...» (задания сдаются там);
  - незнакомцу - «брат или сестра?», ответ пишется в общую user_side, и
    ссылка на бот его половины. Туда, а не сразу в подготовительную:
    половине нужна открытая личка (онбординг, вопрос про джуз), а свой бот
    уже знает ответ и сразу даст ссылку на группу (core/side.py).

Где живёт. В мужском процессе, отдельной задачей со своим getUpdates и
своим токеном (config.APP_BOT_TOKEN). Женский процесс его не слушает -
Telegram не даёт двум слушателям один токен. Нет токена - бот молчит, а
вход и приглашения идут через свои боты, как до 22.09.
"""
import asyncio
import logging

import aiohttp

import config
from core.bots import other_bot, other_profile, JAMAAT_IN, register_app
from core.db import is_app_member, other_bot_member
from core.i18n import T
from core.side import known_side, remember_side, _leave_own_prep, side_buttons, SIDES
from core.tg import get_bot_username
from core.web_auth import claim_login_code, refuse_login_code, LOGIN_START_PREFIX

log = logging.getLogger(__name__)

# Тексты входа - те же, что у ботов половин (core/handlers.py): человек не
# должен замечать, через какую дверь вошёл.
LOGIN_CONFIRMED = (
    "✅ Вход подтверждён.\n\n"
    "Возвращайся в приложение — оно уже открылось. Заходить заново не "
    "придётся: это устройство я запомнил."
)
LOGIN_CODE_EXPIRED = (
    "Эта ссылка на вход уже не годится — она живёт 15 минут 🤲\n\n"
    "Открой приложение и нажми «Войти» ещё раз, я подтвержу."
)

DESCRIPTION = (
    "Ясир — заучивание и чтение Корана с устазом: заучивание, повторение, "
    "слова и живой разбор. Братья и сёстры учатся раздельно — нажми "
    "«Начать», и я направлю тебя в твою группу."
)
SHORT_DESCRIPTION = "Заучивание и чтение Корана с устазом. Нажми «Начать»."


def _api():
    return "https://api.telegram.org/bot" + config.APP_BOT_TOKEN


async def call(method, payload=None, timeout=35):
    """Как core.tg.tg_call, но токеном общего бота. В ленту группы не пишет:
    общий бот в группах не бывает."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(_api() + "/" + method, json=(payload or {}),
                              timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                data = await r.json()
                if data and not data.get("ok"):
                    log.error("app_bot %s failed: %s", method, data.get("description", data))
                return data
    except Exception as e:
        log.error("app_bot %s error: %s: %s", method, type(e).__name__, e)
        return None


async def send(chat_id, text, buttons=None):
    """buttons: список (label, callback_data), одна кнопка на строку."""
    payload = {"chat_id": int(str(chat_id)), "text": text}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": [[{"text": l, "callback_data": d}] for l, d in buttons]}
    return await call("sendMessage", payload)


# ── Кто это ──────────────────────────────────────────────────────────────────

def studies_in(uid):
    """Половина, где человек сейчас учится (или устаз), либо None. Та же
    мерка, что у дверей ботов: своя база первой (is_app_member), потом
    соседская (other_bot_member). Процесс - мужской, но код от этого не
    зависит: «своя» - это config.PROFILE."""
    if is_app_member(uid):
        return config.PROFILE
    if other_bot_member(uid):
        return other_profile()
    return None


def _bot_links(profile):
    """(ссылка на чат, ссылка с «Начать») бота половины, или (None, None)."""
    if profile == config.PROFILE:
        name = get_bot_username()
        if not name:
            return None, None
        return "https://t.me/" + name, "https://t.me/" + name + "?start=go"
    other = other_bot()
    if not other:
        return None, None
    return other["chat_link"], other["start_link"]


# ── Разговор ─────────────────────────────────────────────────────────────────

async def handle_text(uid, text):
    text = (text or "").strip()
    if text.startswith("/start " + LOGIN_START_PREFIX):
        code = text.split(" ", 1)[1][len(LOGIN_START_PREFIX):].strip()
        side = studies_in(uid)
        if side:
            # Код подтверждается для половины человека: сессию выдаст её
            # процесс, вкладка узнает профиль из /auth/poll.
            ok = claim_login_code(code, uid, profile=side)
            await send(uid, LOGIN_CONFIRMED if ok else LOGIN_CODE_EXPIRED)
            return
        # Не учится нигде - вкладка сразу говорит об этом сама, а здесь
        # вместо тупика дорога внутрь.
        refuse_login_code(code)
        await send(uid, T("app_login_not_yet"))
    await way_in(uid)


async def way_in(uid):
    side = studies_in(uid)
    if side:
        chat_link, _ = _bot_links(side)
        await send(uid, T("app_member", jamaat=JAMAAT_IN[side], link=chat_link or "—"))
        return
    # Не учится сейчас, но половина известна: ответил раньше или проходил
    # через устаза (штрафник) - его бот знает, куда вести дальше.
    side = known_side(uid)
    if side:
        await send_to_side(uid, side)
        return
    await send(uid, T("side_question"), side_buttons(uid))


async def send_to_side(uid, side):
    _, start_link = _bot_links(side)
    if start_link:
        await send(uid, T("app_side_link", jamaat=JAMAAT_IN[side], link=start_link))
    else:
        await send(uid, T("app_side_nolink", jamaat=JAMAAT_IN[side]))


async def handle_side_answer(uid, side):
    if side not in SIDES:
        return
    remember_side(uid, side)
    if side != config.PROFILE:
        # Сестра, по ошибке уже записанная в мужскую подготовительную: иначе
        # женский бот увидит её активной здесь и развернёт назад.
        await _leave_own_prep(uid)
    await send_to_side(uid, side)


async def handle_update(upd):
    cq = upd.get("callback_query")
    if cq:
        await call("answerCallbackQuery", {"callback_query_id": cq.get("id")})
        uid = str((cq.get("from") or {}).get("id", ""))
        parts = (cq.get("data") or "").split(":", 2)
        msg = cq.get("message") or {}
        # «side:<половина>:<uid>» - те же кнопки, что у ботов половин;
        # принимаем тап только адресата.
        if len(parts) == 3 and parts[0] == "side" and parts[2] == uid:
            if msg.get("message_id"):
                await call("editMessageReplyMarkup", {
                    "chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                    "reply_markup": {"inline_keyboard": []},
                })
            await handle_side_answer(uid, parts[1])
        return
    msg = upd.get("message") or {}
    chat = msg.get("chat") or {}
    # Только личка: в группы общего бота не зовут, а если добавят - молчит.
    if chat.get("type") != "private":
        return
    uid = str((msg.get("from") or {}).get("id", ""))
    if not uid or (msg.get("from") or {}).get("is_bot"):
        return
    await handle_text(uid, msg.get("text") or "")


# ── Цикл ─────────────────────────────────────────────────────────────────────

async def run():
    if not config.APP_BOT_TOKEN:
        return
    me = await call("getMe")
    if not (me and me.get("ok")):
        log.error("app_bot: getMe не прошёл - общий бот не запущен")
        return
    username = me["result"].get("username", "")
    register_app(username)
    log.info("Общий бот запущен: @%s", username)
    await call("setMyDescription", {"description": DESCRIPTION})
    await call("setMyShortDescription", {"short_description": SHORT_DESCRIPTION})
    offset = 0
    while True:
        try:
            resp = await call("getUpdates", {
                "offset": offset, "timeout": 30,
                "allowed_updates": ["message", "callback_query"],
            }, timeout=40)
            if not resp or not resp.get("ok"):
                await asyncio.sleep(3)
                continue
            for upd in resp.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    await handle_update(upd)
                except Exception as e:
                    log.error("app_bot: update %s: %s", upd.get("update_id"), e)
        except Exception as e:
            log.error("app_bot loop: %s", e)
            await asyncio.sleep(3)
