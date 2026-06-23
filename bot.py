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

from config import TELEGRAM_TOKEN, PROFILE
from core.tg import tg_call, send_message
from core.db import init, get_all_groups, get_group_tasks, db, get_group, get_group_lang, set_pending_name, cache_username, cache_member_name, get_group_admins
from config import ADMIN_PHONES
from core.i18n import T
from core.handlers import process_message
from core.scheduler import scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

# ── Очередь сообщений по отправителю ──────────────────────────────────────────
# Один студент = одна очередь (Lock), разные студенты — параллельно.
_sender_locks: dict = {}


async def queued_process_message(chat_id, sender, text, sender_name, is_media=False, reply_to_id=None):
    key = (chat_id, sender)
    lock = _sender_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _sender_locks[key] = lock
    async with lock:
        try:
            await process_message(chat_id, sender, text, sender_name, is_media, reply_to_id)
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
    else:
        log.error("Не удалось подключиться к Telegram. Проверь токен.")
        return

    asyncio.create_task(scheduler())

    offset = 0
    while True:
        try:
            resp = await tg_call(
                "getUpdates",
                {"offset": offset, "timeout": 30, "allowed_updates": ["message", "chat_member"]},
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
                reply_to = msg.get("reply_to_message", {})
                reply_to_id = reply_to.get("from", {}).get("id") if reply_to else None

                if frm.get("is_bot"):
                    continue

                if frm.get("username") and sender:
                    cache_username(frm["username"], sender)
                if sender_name and sender and chat_id.startswith("-"):
                    cache_member_name(chat_id, sender_name, sender)

                log.info("chat=%s from=%s(%s) text=%r media=%s",
                         chat_id, sender_name, sender, text, is_media)

                # Новый участник
                for nm in msg.get("new_chat_members", []):
                    if not nm.get("is_bot"):
                        uid = str(nm.get("id", ""))
                        group_info = get_group(chat_id)
                        # Суперадмины и устазы группы — не регистрируем как студентов
                        is_super = uid in ADMIN_PHONES
                        is_grp_admin = group_info and uid in get_group_admins(group_info["id"])
                        is_tadabbur = group_info and (group_info.get("group_type") or "relaxed") == "tadabbur"
                        if is_super or is_grp_admin or is_tadabbur:
                            continue
                        with db() as c:
                            c.execute(
                                "INSERT OR IGNORE INTO unregistered_members(user_id,chat_id) VALUES(?,?)",
                                (uid, chat_id)
                            )
                        tg_name = (nm.get("first_name") or "").strip()
                        if nm.get("last_name"):
                            tg_name = (tg_name + " " + nm["last_name"]).strip()
                        if not tg_name and nm.get("username"):
                            tg_name = nm["username"]
                        glang = get_group_lang(group_info) if group_info else "ru"
                        if group_info:
                            set_pending_name(uid, group_info["id"], "")
                        greeting = ("Ассаляму алейкум, " + tg_name + "! 🌙\n") if tg_name else "Ассаляму алейкум! 🌙\n"
                        await send_message(chat_id, greeting + T("ask_name", glang))

                if (text or is_media) and chat_id:
                    asyncio.create_task(
                        queued_process_message(chat_id, sender, text, sender_name, is_media, reply_to_id)
                    )

        except Exception as e:
            log.error("Main loop error: %s", e)
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
