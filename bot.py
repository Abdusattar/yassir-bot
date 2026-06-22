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
from core.db import init, get_all_groups, get_group_tasks, db
from core.handlers import process_message
from core.scheduler import scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

# ── Очередь сообщений по отправителю ──────────────────────────────────────────
# Один студент = одна очередь (Lock), разные студенты — параллельно.
_sender_locks: dict = {}


async def queued_process_message(chat_id, sender, text, sender_name, is_media=False):
    key = (chat_id, sender)
    lock = _sender_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _sender_locks[key] = lock
    async with lock:
        try:
            await process_message(chat_id, sender, text, sender_name, is_media)
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
                await asyncio.sleep(2)
                continue

            for upd in resp.get("result", []):
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

                if frm.get("is_bot"):
                    continue

                log.info("chat=%s from=%s(%s) text=%r media=%s",
                         chat_id, sender_name, sender, text, is_media)

                # Новый участник
                for nm in msg.get("new_chat_members", []):
                    if not nm.get("is_bot"):
                        uid = str(nm.get("id", ""))
                        with db() as c:
                            c.execute(
                                "INSERT OR IGNORE INTO unregistered_members(user_id,chat_id) VALUES(?,?)",
                                (uid, chat_id)
                            )

                if (text or is_media) and chat_id:
                    asyncio.create_task(
                        queued_process_message(chat_id, sender, text, sender_name, is_media)
                    )

        except Exception as e:
            log.error("Main loop error: %s", e)
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
