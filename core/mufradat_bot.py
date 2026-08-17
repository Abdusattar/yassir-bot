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

Слова вопросов идут ВПЕРЕМЕШКУ со ВСЕХ страниц, которые студент уже
тренировал (get_words_for_trained_pages), не с одной "текущей" страницы -
решение пользователя 17.08.2026 (третий заход): раньше сессия держалась
одной страницы (взвешенный случайный выбор среди тренированных), но это
всё ещё позволяло старым страницам "простаивать" весь сеанс. Теперь у
каждого вопроса своя страница (page_for_ayah), заголовок карточки её
показывает, а "вес" на карточке - ОБЩИЙ (compute_overall_score), не
одной страницы. mufradat_page (set_current_page) больше не читается для
выбора пула - только пишется, как побочный след явного выбора номера.
"""
import logging
import re

from core.db import find_user_by_phone, get_learning_group, get_group_tasks, save_report, get_date, get_today_report
from core.mufradat import (
    get_words_in_range, generate_question, get_progress_map, record_answer,
    set_current_page, mark_page_trained, get_leaderboard, get_words_for_trained_pages,
    record_daily_answered_word, DAILY_WORDS_FOR_TASK_CREDIT, compute_overall_score,
)
from core.quran_pages import resolve_page, page_for_ayah, BAQARA_SURAH, BAQARA_FIRST_PAGE, BAQARA_LAST_PAGE
from core.tg import send_message, send_message_with_button_rows, edit_message_with_button_rows

log = logging.getLogger(__name__)

_active_question = {}  # user_id -> {word_id, target, options, word_page, chat_id, message_id, session_correct, start_score10}
_awaiting_page = set()  # user_id, ждём текстовый ответ с номером страницы

_PAGE_NUM_RE = re.compile(r"^\s*(\d{1,3})\s*$")


def _page_prompt_text():
    return (
        "📖 Какая страница мусхафа? (сура Бакара — страницы "
        f"{BAQARA_FIRST_PAGE}-{BAQARA_LAST_PAGE})\n"
        "Напиши номер страницы, например: 23"
    )


async def start_trainer(user_id, chat_id):
    pool = get_words_for_trained_pages(user_id)
    if not pool:
        _awaiting_page.add(user_id)
        await send_message(chat_id, _page_prompt_text())
        return
    await _send_new_card(user_id, chat_id, pool)


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
    # Сразу открываем карточку именно с ЭТОЙ новой страницы (не общий пул) -
    # иначе только что добавленная страница потеряется среди старых слов.
    words = get_words_in_range(BAQARA_SURAH, *ayah_range)
    await _send_new_card(user_id, chat_id, words)
    return True


def _format_overall_score(score):
    """"0.0/10 (0/117)" читалось как загадка (фидбек пользователя 17.08.2026,
    второй заход) - расписываем словами. score10 (плавная доля пути к
    MASTERY_STREAK по всем словам) и "закреплено" (целое число слов,
    реально достигших MASTERY_STREAK) - одна и та же метрика, просто
    агрегированная по-разному (core/mufradat.py:compute_overall_score),
    поэтому разные слова в тексте, не "выучено" для обеих."""
    return f"📊 Общий вес: {score['score10']:.2f}/10 (закреплено {score['mastered']} из {score['total']} слов)"


def _render_card(user_id, q, session_correct, overall_score=None, feedback=None):
    """session_correct - счётчик верных ответов ЭТОГО сеанса (живёт в
    _active_question, монотонно растёт, никогда не падает от ошибки) -
    показывается на КАЖДОЙ карточке, для мгновенной обратной связи.
    overall_score ("общий вес") теперь тоже двигается с каждым верным
    ответом (correct_streak, не завязан на календарный день) - поэтому,
    в отличие от первой версии, тоже показывается на каждом тапе, не
    только в начале/конце сеанса (решение пользователя 17.08.2026,
    третий заход - старая причина прятать её была в том, что дневная
    метрика не успевала сдвинуться за один сеанс, это больше не так)."""
    page_number = page_for_ayah(q["word"]["ayah_number"])
    lines = []
    if feedback:
        lines.append(feedback)
        lines.append("")
    lines.append(f"📖 Бакара, стр. {page_number}")
    lines.append(f"Слово: <b>{q['word']['arabic_text']}</b>")
    lines.append(f"\n✅ Верно за сеанс: {session_correct}")
    if overall_score:
        lines.append(_format_overall_score(overall_score))
    text = "\n".join(lines)

    opts = q["options"]
    rows = []
    for i in range(0, len(opts), 2):
        row = [(opts[j], f"muf:{user_id}:{j}") for j in (i, i + 1) if j < len(opts)]
        rows.append(row)
    rows.append([("➕ Новая страница", f"mufpg:{user_id}"), ("✅ Закончить", f"mufend:{user_id}")])
    rows.append([("🏆 Рейтинг", f"muftop:{user_id}")])
    return text, rows


async def _send_new_card(user_id, chat_id, words_pool):
    progress = get_progress_map(user_id, [w["id"] for w in words_pool])
    q = generate_question(words_pool, progress)
    if q is None:
        await send_message(chat_id, "Пока маловато слов для тренажёра 🤲 Попробуй добавить ещё страницу.")
        return

    overall_score = compute_overall_score(user_id)
    text, rows = _render_card(user_id, q, 0, overall_score)
    resp = await send_message_with_button_rows(chat_id, text, rows)
    msg_id = ((resp or {}).get("result") or {}).get("message_id")
    if not msg_id:
        return
    _active_question[user_id] = {
        "word_id": q["word"]["id"], "target": q["word"]["translation"], "options": q["options"],
        "word_page": page_for_ayah(q["word"]["ayah_number"]),
        "chat_id": chat_id, "message_id": msg_id, "session_correct": 0,
        "start_score10": overall_score["score10"] if overall_score else None,
    }


async def _credit_task_if_applicable(user_id, chat_id):
    """20+ разных слов за день - засчитываем задание 't' ("Слова (или
    Перевод)", core/handlers.py), если оно вообще есть в группе студента.
    Порог в вызывающем коде - "count_today >= ...", не "==": два тапа
    почти одновременно (без лока, в отличие от queued_process_message)
    могут оба увидеть count=19→20 или проскочить ровно 20 - save_report
    идемпотентен (INSERT OR IGNORE), поэтому лишний вызов не страшен.
    Но чтобы не слать поздравление на КАЖДЫЙ следующий тап после 20-го,
    сверяемся с get_today_report - шлём текст только при первой отметке
    (advisor 17.08.2026, поймал и гонку, и повторный спам).

    Обычные задания студент сдаёт ТЕКСТОМ прямо в группе - там же и видно
    подтверждение (core/handlers.py). Здесь сдача происходит в личке с
    ботом (тренажёр), поэтому группа иначе не узнала бы - дублируем
    короткое уведомление в group["chat_id"] с текущим весом (решение
    пользователя 17.08.2026)."""
    group = get_learning_group(user_id)
    if not group or "t" not in get_group_tasks(group):
        return
    user = find_user_by_phone(user_id)
    if not user:
        return
    already = get_today_report(user["id"], group["id"]) or {}
    if already.get("t"):
        return
    save_report(user["id"], group["id"], get_date(), {"t": True})
    await send_message(chat_id, "🎉 Задание «Слова» на сегодня засчитано — 20 разных слов проработано!")

    if group["chat_id"]:
        score = compute_overall_score(user_id)
        score_part = f" (вес {score['score10']:.2f}/10)" if score else ""
        await send_message(
            group["chat_id"],
            f"📖 {user['name']} отработал(а) дневной сет 20 слов на тренажёре муфрадат{score_part}."
        )


async def handle_answer_tap(user_id, chat_id, message_id, slot):
    state = _active_question.get(user_id)
    if not state or state.get("message_id") != message_id:
        # Память потеряна (рестарт бота) или тап по устаревшей карточке -
        # не молчим, шлём свежую карточку, без начисления балла за этот тап.
        pool = get_words_for_trained_pages(user_id)
        if not pool:
            await send_message(chat_id, "Сессия тренажёра сброшена, набери /muf заново 🤲")
            return
        await _send_new_card(user_id, chat_id, pool)
        return

    opts = state["options"]
    if not (0 <= slot < len(opts)):
        return
    chosen = opts[slot]
    correct = (chosen == state["target"])
    record_answer(user_id, state["word_id"], correct)
    mark_page_trained(user_id, state["word_page"])

    session_correct = state.get("session_correct", 0) + (1 if correct else 0)

    count_today = record_daily_answered_word(user_id, state["word_id"])
    if count_today >= DAILY_WORDS_FOR_TASK_CREDIT:
        await _credit_task_if_applicable(user_id, chat_id)

    pool = get_words_for_trained_pages(user_id)
    progress = get_progress_map(user_id, [w["id"] for w in pool])
    q = generate_question(pool, progress)
    feedback = "✅ Верно!" if correct else f"❌ Не то, правильно: {state['target']}"

    if q is None:
        _active_question.pop(user_id, None)
        # Раньше это было недостижимо (слова только теряли вес, не
        # исключались) - с жёстким исключением "отдыхающих" выученных слов
        # (RECHECK_AFTER_DAYS) пул реально может опустеть, если студент
        # прошёл всю страницу - тупик без объяснения и кнопок был багом
        # (advisor 17.08.2026, пятый заход).
        text = feedback + "\n\nСлова на этой странице пока закончились 🤲 Добавь ещё одну."
        await edit_message_with_button_rows(
            chat_id, message_id, text, [[("➕ Новая страница", f"mufpg:{user_id}")]]
        )
        return

    overall_score = compute_overall_score(user_id, words=pool, progress=progress)
    text, rows = _render_card(user_id, q, session_correct, overall_score, feedback)
    _active_question[user_id] = {
        "word_id": q["word"]["id"], "target": q["word"]["translation"], "options": q["options"],
        "word_page": page_for_ayah(q["word"]["ayah_number"]),
        "chat_id": chat_id, "message_id": message_id, "session_correct": session_correct,
        "start_score10": state.get("start_score10"),
    }
    await edit_message_with_button_rows(chat_id, message_id, text, rows)


async def handle_change_page_tap(user_id, chat_id):
    _active_question.pop(user_id, None)
    _awaiting_page.add(user_id)
    await send_message(chat_id, _page_prompt_text())


def _find_rank(leaderboard, user_id):
    for label, entries in leaderboard:
        for i, (uid, score) in enumerate(entries, start=1):
            if uid == user_id:
                return label, i, len(entries), score
    return None


async def handle_end_session_tap(user_id, chat_id, message_id):
    """Кнопка "Закончить" - студент явно завершает сеанс (пользователь
    спросил "как закрывается тренажёр", 17.08.2026 - карточка до этого
    висела активной бесконечно, без явного конца). Показывает итоговый
    вес, насколько он вырос за сеанс (от start_score10), и место в
    рейтинге (пользователь: "покажи его бал, топов, насколько улучшил")."""
    state = _active_question.pop(user_id, None)
    lines = ["Сессия завершена 🤲"]

    end_score = compute_overall_score(user_id)
    if end_score:
        lines.append(_format_overall_score(end_score))
        start10 = state.get("start_score10") if state else None
        if start10 is not None:
            delta = round(end_score["score10"] - start10, 2)
            if delta > 0:
                lines.append(f"📈 Вырос за сеанс на +{delta:.2f}")
            elif delta < 0:
                lines.append(f"📉 Снизился за сеанс на {delta:.2f}")
            else:
                lines.append("Вес за сеанс не изменился — попробуй ещё раз, каждый верный ответ его двигает 🤲")

        rank_info = _find_rank(get_leaderboard(), user_id)
        if rank_info:
            label, rank, total_in_bracket, _score = rank_info
            lines.append(f"🏆 Место среди изучающих стр. {label}: {rank} из {total_in_bracket}")

    await edit_message_with_button_rows(chat_id, message_id, "\n".join(lines), [])


def _display_name(user_id):
    user = find_user_by_phone(user_id)
    return user["name"] if user else f"Студент {user_id[-4:]}"


def _group_name(user_id):
    group = get_learning_group(user_id)
    return group["title"] if group and group["title"] else "—"


def _render_leaderboard_text(user_id, leaderboard):
    """leaderboard - результат get_leaderboard():
    [(bracket_label, [(uid, score_dict), ...]), ...], уже отсортировано
    внутри каждой полки по числу выученных слов (см. модульный docstring
    core/mufradat.py:get_leaderboard)."""
    if not any(entries for _, entries in leaderboard):
        return "Пока никто не тренировал муфрадат достаточно, чтобы попасть в рейтинг 🤲 Начни первым: /muf"

    lines = ["🏆 Топ по муфрадату (Бакара) — по глубине прохождения\n"]
    my_bracket = my_rank = my_score = None

    for label, entries in leaderboard:
        if not entries:
            continue
        lines.append(f"📄 Стр. {label}:")
        for i, (uid, score) in enumerate(entries, start=1):
            if uid == user_id:
                my_bracket, my_rank, my_score = label, i, score
            if i <= 3:
                marker = "👉 " if uid == user_id else ""
                lines.append(f"  {marker}{i}. {_display_name(uid)} ({_group_name(uid)}) — {score['mastered']} слов")
        lines.append("")

    if my_bracket and my_rank > 3:
        lines.append(
            f"Ты среди изучающих стр. {my_bracket}: место {my_rank}, "
            f"{my_score['mastered']} слов выучено (вес {my_score['score10']:.2f}/10)."
        )
    elif my_bracket is None:
        lines.append("Ты ещё не тренировал ни одной страницы — набери /muf 🤲")

    return "\n".join(lines).rstrip()


async def show_leaderboard(user_id, chat_id):
    leaderboard = get_leaderboard()
    await send_message(chat_id, _render_leaderboard_text(user_id, leaderboard))
