"""Telegram-обвязка тренажёра муфрадата (движок - core/mufradat.py).

Одна самообновляющаяся карточка на студента (editMessageText), не поток
сообщений - согласовано с пользователем 17.08.2026. Активный вопрос
студента живёт в памяти процесса (_active_question), не в БД - бот
деплоится сам на каждый push ([[feedback_auto_deploy]]), поэтому тап по
кнопке после рестарта не должен молчать: обработчик просто присылает
новую карточку без начисления балла за этот тап (advisor 17.08.2026,
пункт устойчивости к рестарту).

Студент называет НОМЕР СТРАНИЦЫ печатного мусхафа (core/quran_pages.py),
не диапазон аятов - так он реально ориентируется в Коране (17.08.2026,
второй заход после прямого вопроса пользователя об удобстве навигации).
"""
import logging
import re

from core.mufradat import (
    get_words_in_range, generate_question, get_progress_map, record_answer,
    get_current_page, set_current_page,
)
from core.quran_pages import resolve_page, BAQARA_FIRST_PAGE, BAQARA_LAST_PAGE, BAQARA_SURAH
from core.tg import send_message, send_message_with_button_rows, edit_message_with_button_rows

log = logging.getLogger(__name__)

_active_question = {}  # user_id -> {word_id, target, options, page, chat_id, message_id}
_awaiting_page = set()  # user_id, ждём текстовый ответ с номером страницы

_PAGE_NUM_RE = re.compile(r"^\s*(\d{1,3})\s*$")


def _page_prompt_text():
    return (
        "📖 Какая страница мусхафа? (сура Бакара — страницы "
        f"{BAQARA_FIRST_PAGE}-{BAQARA_LAST_PAGE})\n"
        "Напиши номер страницы, например: 23"
    )


async def start_trainer(user_id, chat_id):
    page = get_current_page(user_id)
    if page is None:
        _awaiting_page.add(user_id)
        await send_message(chat_id, _page_prompt_text())
        return
    await _send_new_card(user_id, chat_id, page)


async def handle_page_text(user_id, chat_id, text):
    """Возвращает True, если сообщение перехвачено (студент ждал вопрос
    про номер страницы) - вызывающий код тогда не должен обрабатывать
    text дальше."""
    if user_id not in _awaiting_page:
        return False

    m = _PAGE_NUM_RE.match(text)
    if not m:
        await send_message(chat_id, "Не понял номер страницы 🤔 Напиши просто число, например: 23")
        return True

    page_number = int(m.group(1))
    ayah_range = resolve_page(page_number)
    if ayah_range is None:
        await send_message(
            chat_id,
            f"Сура Бакара — это страницы {BAQARA_FIRST_PAGE}-{BAQARA_LAST_PAGE} мусхафа. "
            "Напиши номер в этом диапазоне, например: 23"
        )
        return True

    _awaiting_page.discard(user_id)
    set_current_page(user_id, page_number, *ayah_range)
    await _send_new_card(user_id, chat_id, (page_number, *ayah_range))
    return True


def _render_card(user_id, q, page, feedback=None):
    page_number = page[0]
    lines = []
    if feedback:
        lines.append(feedback)
        lines.append("")
    lines.append(f"📖 Бакара, стр. {page_number}")
    lines.append(f"Слово: {q['word']['arabic_text']}")
    text = "\n".join(lines)

    opts = q["options"]
    rows = []
    for i in range(0, len(opts), 2):
        row = [(opts[j], f"muf:{user_id}:{j}") for j in (i, i + 1) if j < len(opts)]
        rows.append(row)
    rows.append([("🔄 Сменить страницу", f"mufpg:{user_id}")])
    return text, rows


async def _send_new_card(user_id, chat_id, page):
    page_number, start_ayah, end_ayah = page
    words = get_words_in_range(BAQARA_SURAH, start_ayah, end_ayah)
    progress = get_progress_map(user_id, [w["id"] for w in words])
    q = generate_question(words, progress)
    if q is None:
        await send_message(chat_id, "На этой странице пока маловато слов для тренажёра 🤲 Попробуй другую страницу.")
        return

    text, rows = _render_card(user_id, q, page)
    resp = await send_message_with_button_rows(chat_id, text, rows)
    msg_id = ((resp or {}).get("result") or {}).get("message_id")
    if not msg_id:
        return
    _active_question[user_id] = {
        "word_id": q["word"]["id"], "target": q["word"]["translation"], "options": q["options"],
        "page": page, "chat_id": chat_id, "message_id": msg_id,
    }


async def handle_answer_tap(user_id, chat_id, message_id, slot):
    state = _active_question.get(user_id)
    if not state or state.get("message_id") != message_id:
        # Память потеряна (рестарт бота) или тап по устаревшей карточке -
        # не молчим, шлём свежую карточку, без начисления балла за этот тап.
        page = get_current_page(user_id)
        if not page:
            await send_message(chat_id, "Сессия тренажёра сброшена, набери /muf заново 🤲")
            return
        await _send_new_card(user_id, chat_id, page)
        return

    opts = state["options"]
    if not (0 <= slot < len(opts)):
        return
    chosen = opts[slot]
    correct = (chosen == state["target"])
    record_answer(user_id, state["word_id"], correct)

    page = state["page"]
    _, start_ayah, end_ayah = page
    words = get_words_in_range(BAQARA_SURAH, start_ayah, end_ayah)
    progress = get_progress_map(user_id, [w["id"] for w in words])
    q = generate_question(words, progress)
    feedback = "✅ Верно!" if correct else f"❌ Не то, правильно: {state['target']}"

    if q is None:
        _active_question.pop(user_id, None)
        await edit_message_with_button_rows(chat_id, message_id, feedback, [])
        return

    text, rows = _render_card(user_id, q, page, feedback)
    _active_question[user_id] = {
        "word_id": q["word"]["id"], "target": q["word"]["translation"], "options": q["options"],
        "page": page, "chat_id": chat_id, "message_id": message_id,
    }
    await edit_message_with_button_rows(chat_id, message_id, text, rows)


async def handle_change_page_tap(user_id, chat_id):
    _active_question.pop(user_id, None)
    _awaiting_page.add(user_id)
    await send_message(chat_id, _page_prompt_text())
