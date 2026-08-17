"""
Точка входа нового структурированного бота.

Запуск:
  BOT_PROFILE=male   python bot.py   # мужские группы
  BOT_PROFILE=female python bot.py   # женские группы

Пока bot_tg.py обслуживает действующие группы устаза,
этот бот тестируется на новых группах.
"""
import asyncio
import logging

from config import TELEGRAM_TOKEN, PROFILE, REQUIRE_PREP_FOR_NEW_STUDENTS
from core.tg import tg_call, send_message, answer_callback_query, remove_message_keyboard
from core.db import init, get_all_groups, get_group_tasks, db, get_group, get_group_lang, set_pending_name, cache_username, cache_member_name, get_group_admins, find_user_by_phone
from config import SUPER_ADMIN_IDS
from core.i18n import T
from core.handlers import process_message, handle_reaction
from core.scheduler import scheduler
from core.prep import handle_juz_answer, handle_prep_onboarding_next
from core.transfers import (
    handle_known_user_group_join, handle_upgrade_answer, handle_member_left,
    send_new_student_prep_redirect,
)
from core.attendance_confirm import handle_attendance_confirm_answer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

# ── Очередь сообщений по отправителю ──────────────────────────────────────────
# Один студент = одна очередь (Lock), разные студенты — параллельно.
_sender_locks: dict = {}


async def queued_process_message(chat_id, sender, text, sender_name, is_media=False, reply_to_id=None, message_id=None, reply_to_text="", is_voice=False, reply_to_message_id=None, voice_file_id=None):
    key = (chat_id, sender)
    lock = _sender_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _sender_locks[key] = lock
    async with lock:
        try:
            await process_message(chat_id, sender, text, sender_name, is_media, reply_to_id, message_id, reply_to_text, is_voice, reply_to_message_id, voice_file_id)
        except Exception as e:
            log.error("process_message error chat=%s sender=%s: %s", chat_id, sender, e)
        await asyncio.sleep(0.3)


async def main():
    init()
    if not TELEGRAM_TOKEN:
        log.error("TELEGRAM_TOKEN не задан! Задай переменную окружения.")
        return

    me = await tg_call("getMe")
    if me and me.get("ok"):
        username = me["result"].get("username", "?")
        log.info("Бот запущен: @%s  [profile=%s]", username, PROFILE)
        # Меню команд Telegram (кнопка "/" рядом с полем ввода) - имя
        # команды технически латиницей (ограничение Telegram), но описание
        # в меню на русском, чтобы находили не зная английского (17.08.2026).
        await tg_call("setMyCommands", {
            "commands": [
                {"command": "invite", "description": "Ссылка для друга — позвать к Корану"},
                {"command": "muf", "description": "Муфрадат"},
                {"command": "muftop", "description": "Рейтинг по муфрадату"},
            ],
            "scope": {"type": "all_private_chats"},
            "language_code": "ru",
        })
    else:
        log.error("Не удалось подключиться к Telegram. Проверь токен.")
        return

    asyncio.create_task(scheduler())

    offset = 0
    while True:
        try:
            resp = await tg_call(
                "getUpdates",
                {"offset": offset, "timeout": 30, "allowed_updates": ["message", "chat_member", "message_reaction", "callback_query"]},
                timeout=40
            )
            if not resp or not resp.get("ok"):
                log.warning("getUpdates failed: %s", resp)
                await asyncio.sleep(2)
                continue

            updates = resp.get("result", [])
            if updates:
                log.debug("getUpdates: %d updates", len(updates))
            for upd in updates:
                offset = upd["update_id"] + 1

                # Нажатие инлайн-кнопки (сейчас единственный сценарий — вопрос
                # "знаешь ли хотя бы 1 джуз" при выпуске из подготовительной)
                cq = upd.get("callback_query")
                if cq:
                    cq_data = cq.get("data", "")
                    cq_from = cq.get("from", {})
                    cq_uid = str(cq_from.get("id", ""))
                    cq_msg = cq.get("message", {}) or {}
                    cq_chat_id = str(cq_msg.get("chat", {}).get("id", ""))
                    cq_message_id = cq_msg.get("message_id")
                    await answer_callback_query(cq.get("id"))
                    # "pjz:yes:<uid>" / "pjz:no:<uid>" - вопрос про джуз при выпуске
                    # из подготовительной. uid закодирован в callback_data, потому
                    # что кнопка может быть показана в ГРУППЕ (если личка студенту
                    # ещё недоступна) - там её видят и могут нажать все участники,
                    # поэтому обрабатываем только тап именно адресата (24.07.2026).
                    if cq_data.startswith("pjz:"):
                        parts = cq_data.split(":", 2)
                        if len(parts) == 3 and parts[2] == cq_uid:
                            if cq_chat_id and cq_message_id:
                                await remove_message_keyboard(cq_chat_id, cq_message_id)
                            asyncio.create_task(handle_juz_answer(cq_uid, parts[1] == "yes"))
                    # "upg:stay:<uid>:<offer_id>" / "upg:pro:<uid>:<offer_id>" -
                    # предложение перейти из relaxed в pro-группу (25.07.2026).
                    # offer_id в data - чтобы тап по устаревшему сообщению не
                    # резолвил случайно текущее предложение того же студента.
                    elif cq_data.startswith("upg:"):
                        parts = cq_data.split(":", 3)
                        if len(parts) == 4 and parts[2] == cq_uid:
                            if cq_chat_id and cq_message_id:
                                await remove_message_keyboard(cq_chat_id, cq_message_id)
                            asyncio.create_task(handle_upgrade_answer(cq_uid, parts[1], int(parts[3])))
                    # "att:yes:<uid>:<confirm_id>" / "att:no:<uid>:<confirm_id>" -
                    # подтверждение устазом, что урок реально прошёл, перед
                    # начислением баллов за "у" (31.07.2026, пересмотрено 12.08.2026 -
                    # молчание больше не эскалируется супер-админам, см. attendance_confirm.py).
                    elif cq_data.startswith("att:"):
                        parts = cq_data.split(":", 3)
                        if len(parts) == 4 and parts[2] == cq_uid:
                            if cq_chat_id and cq_message_id:
                                await remove_message_keyboard(cq_chat_id, cq_message_id)
                            asyncio.create_task(handle_attendance_confirm_answer(cq_uid, parts[1], int(parts[3])))
                    # "ponb:<next_screen_idx>:<uid>" - кнопка "Далее" в онбординге
                    # подготовительной (13.08.2026, 6 экранов вместо потока из 9
                    # сообщений). Только личка - но uid всё равно сверяем, для
                    # единообразия с остальными callback-веткам.
                    elif cq_data.startswith("ponb:"):
                        parts = cq_data.split(":", 2)
                        if len(parts) == 3 and parts[2] == cq_uid:
                            if cq_chat_id and cq_message_id:
                                await remove_message_keyboard(cq_chat_id, cq_message_id)
                            asyncio.create_task(handle_prep_onboarding_next(cq_uid, int(parts[1])))
                    # "muf:<uid>:<slot>" - тап по варианту ответа в тренажёре
                    # муфрадата (17.08.2026). Не убираем клавиатуру заранее -
                    # обработчик сам правит то же сообщение новым вопросом.
                    elif cq_data.startswith("muf:"):
                        parts = cq_data.split(":", 2)
                        if len(parts) == 3 and parts[1] == cq_uid and cq_chat_id and cq_message_id:
                            from core.mufradat_bot import handle_answer_tap
                            asyncio.create_task(handle_answer_tap(cq_uid, cq_chat_id, cq_message_id, int(parts[2])))
                    # "mufpg:<uid>" - кнопка "Новая страница" в тренажёре муфрадата
                    elif cq_data.startswith("mufpg:"):
                        parts = cq_data.split(":", 1)
                        if len(parts) == 2 and parts[1] == cq_uid and cq_chat_id:
                            from core.mufradat_bot import handle_change_page_tap
                            asyncio.create_task(handle_change_page_tap(cq_uid, cq_chat_id))
                    # "mufend:<uid>" - кнопка "Закончить" в тренажёре муфрадата
                    elif cq_data.startswith("mufend:"):
                        parts = cq_data.split(":", 1)
                        if len(parts) == 2 and parts[1] == cq_uid and cq_chat_id and cq_message_id:
                            from core.mufradat_bot import handle_end_session_tap
                            asyncio.create_task(handle_end_session_tap(cq_uid, cq_chat_id, cq_message_id))
                    # "muftop:<uid>" - кнопка "Рейтинг" в тренажёре муфрадата -
                    # шлёт рейтинг ОТДЕЛЬНЫМ сообщением, не трогает активную карточку
                    elif cq_data.startswith("muftop:"):
                        parts = cq_data.split(":", 1)
                        if len(parts) == 2 and parts[1] == cq_uid and cq_chat_id:
                            from core.mufradat_bot import show_leaderboard
                            asyncio.create_task(show_leaderboard(cq_uid, cq_chat_id))
                    continue

                # Вступление по ссылке-приглашению (chat_member update)
                cm = upd.get("chat_member")
                if cm:
                    new_m = cm.get("new_chat_member", {})
                    old_m = cm.get("old_chat_member", {})
                    user = new_m.get("user", {})
                    log.info("chat_member: chat=%s user=%s(%s) %s→%s",
                             cm.get("chat", {}).get("id"), user.get("first_name"), user.get("id"),
                             old_m.get("status"), new_m.get("status"))
                    joined = (
                        new_m.get("status") == "member"
                        and old_m.get("status") in ("left", "kicked")
                        and not user.get("is_bot")
                    )
                    left = (
                        old_m.get("status") == "member"
                        and new_m.get("status") in ("left", "kicked")
                        and not user.get("is_bot")
                    )
                    if left:
                        uid = str(user.get("id", ""))
                        chat_id = str(cm.get("chat", {}).get("id", ""))
                        await handle_member_left(chat_id, uid)
                        continue
                    if joined:
                        uid = str(user.get("id", ""))
                        chat_id = str(cm.get("chat", {}).get("id", ""))
                        group_info = get_group(chat_id)
                        is_super = uid in SUPER_ADMIN_IDS
                        is_grp_admin = group_info and uid in get_group_admins(group_info["id"])
                        is_tadabbur = group_info and (group_info["group_type"] or "relaxed") == "tadabbur"
                        log.info("chat_member join: uid=%s group=%s super=%s grp_admin=%s tadabbur=%s",
                                 uid, group_info and group_info["id"], is_super, is_grp_admin, is_tadabbur)
                        if group_info and not is_super and not is_grp_admin and not is_tadabbur:
                            tg_name = (user.get("first_name") or "").strip()
                            if user.get("last_name"):
                                tg_name = (tg_name + " " + user["last_name"]).strip()
                            if not tg_name and user.get("username"):
                                tg_name = user["username"]
                            if user.get("username"):
                                cache_username(user["username"], uid)
                            glang = get_group_lang(group_info)
                            existing_user = find_user_by_phone(uid)
                            if existing_user:
                                await handle_known_user_group_join(chat_id, group_info, uid, existing_user)
                            else:
                                with db() as c:
                                    c.execute(
                                        "INSERT OR IGNORE INTO unregistered_members(user_id,chat_id) VALUES(?,?)",
                                        (uid, chat_id)
                                    )
                                gtype_join = group_info["group_type"] or "relaxed"
                                if REQUIRE_PREP_FOR_NEW_STUDENTS and gtype_join in ("pro", "relaxed"):
                                    # Сразу шлём в личку ссылку на подготовительную, не
                                    # ждём первого сообщения/кика через сутки (02.08.2026,
                                    # см. send_new_student_prep_redirect в transfers.py).
                                    # pending_name не ставим - тут регистрация не начинается.
                                    log.info("chat_member: new user %s in prep-bypass group %s - redirecting to prep", uid, chat_id)
                                    await send_new_student_prep_redirect(uid, chat_id, tg_name, glang)
                                else:
                                    set_pending_name(uid, group_info["id"], "")
                                    greeting = ("Ассаляму алейкум, " + tg_name + "! 🌙\n") if tg_name else "Ассаляму алейкум! 🌙\n"
                                    log.info("chat_member: greeting new user %s in chat %s", uid, chat_id)
                                    await send_message(chat_id, greeting + T("ask_name", glang))
                    continue

                mr = upd.get("message_reaction")
                if mr:
                    r_chat_id = str(mr.get("chat", {}).get("id", ""))
                    r_user = mr.get("user") or {}
                    r_user_id = str(r_user.get("id", "")) if r_user else ""
                    r_message_id = mr.get("message_id")
                    if r_chat_id and r_user_id and r_message_id:
                        asyncio.create_task(handle_reaction(r_chat_id, r_user_id, r_message_id))
                    continue

                msg = upd.get("message")
                if not msg:
                    continue

                chat = msg.get("chat", {})
                frm = msg.get("from", {})

                chat_id = str(chat.get("id", ""))
                sender = str(frm.get("id", ""))

                sender_name = (frm.get("first_name", "") or "").strip()
                if frm.get("last_name"):
                    sender_name = (sender_name + " " + frm["last_name"]).strip()
                if not sender_name and frm.get("username"):
                    sender_name = frm["username"]

                text = msg.get("text", "") or msg.get("caption", "")
                is_media = any(k in msg for k in
                               ("photo", "video", "document", "audio", "voice", "video_note"))
                is_voice = "voice" in msg or "audio" in msg
                voice_file_id = (msg.get("voice") or msg.get("audio") or {}).get("file_id")
                reply_to = msg.get("reply_to_message", {})
                reply_to_id = reply_to.get("from", {}).get("id") if reply_to else None
                reply_to_text = reply_to.get("text", "") if reply_to else ""
                reply_to_message_id = reply_to.get("message_id") if reply_to else None

                if frm.get("is_bot"):
                    continue

                if frm.get("username") and sender:
                    cache_username(frm["username"], sender)
                if sender_name and sender and chat_id.startswith("-"):
                    cache_member_name(chat_id, sender_name, sender)

                log.info("chat=%s from=%s(%s) text=%r media=%s",
                         chat_id, sender_name, sender, text, is_media)

                # Новый участник (new_chat_members — добавлен кем-то или в старых группах)
                for nm in msg.get("new_chat_members", []):
                    if not nm.get("is_bot"):
                        uid = str(nm.get("id", ""))
                        log.info("new_chat_members: uid=%s name=%s in chat=%s", uid, nm.get("first_name"), chat_id)
                        group_info = get_group(chat_id)
                        # Суперадмины и устазы группы — не регистрируем как студентов
                        is_super = uid in SUPER_ADMIN_IDS
                        is_grp_admin = group_info and uid in get_group_admins(group_info["id"])
                        is_tadabbur = group_info and (group_info["group_type"] or "relaxed") == "tadabbur"
                        if is_super or is_grp_admin or is_tadabbur:
                            continue
                        tg_name = (nm.get("first_name") or "").strip()
                        if nm.get("last_name"):
                            tg_name = (tg_name + " " + nm["last_name"]).strip()
                        if not tg_name and nm.get("username"):
                            tg_name = nm["username"]
                        glang = get_group_lang(group_info) if group_info else "ru"
                        if group_info:
                            existing_user = find_user_by_phone(uid)
                            if existing_user:
                                await handle_known_user_group_join(chat_id, group_info, uid, existing_user)
                            else:
                                with db() as c:
                                    c.execute(
                                        "INSERT OR IGNORE INTO unregistered_members(user_id,chat_id) VALUES(?,?)",
                                        (uid, chat_id)
                                    )
                                gtype_nm = group_info["group_type"] or "relaxed"
                                if REQUIRE_PREP_FOR_NEW_STUDENTS and gtype_nm in ("pro", "relaxed"):
                                    log.info("new_chat_members: new user %s in prep-bypass group %s - redirecting to prep", uid, chat_id)
                                    await send_new_student_prep_redirect(uid, chat_id, tg_name, glang)
                                else:
                                    set_pending_name(uid, group_info["id"], "")
                                    greeting = ("Ассаляму алейкум, " + tg_name + "! 🌙\n") if tg_name else "Ассаляму алейкум! 🌙\n"
                                    await send_message(chat_id, greeting + T("ask_name", glang))

                if (text or is_media) and chat_id:
                    message_id = msg.get("message_id")
                    asyncio.create_task(
                        queued_process_message(chat_id, sender, text, sender_name, is_media, reply_to_id, message_id, reply_to_text, is_voice, reply_to_message_id, voice_file_id)
                    )

        except Exception as e:
            log.error("Main loop error: %s", e)
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
