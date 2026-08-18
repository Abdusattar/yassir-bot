"""Telegram-обвязка тренажёра муфрадата (движок - core/mufradat.py).

Одна самообновляющаяся карточка на студента, не поток сообщений -
согласовано с пользователем 17.08.2026. С 18.08.2026 карточка - ФОТО
(editMessageMedia/editMessageCaption), не текст: арабское слово рендерится
крупным шрифтом в PNG через core/mufradat_render.py (Telegram Bot API HTML
не умеет font-size - жирного было мало, пользователь пожаловался "мелко
читать"). Первая карточка ОБЯЗАНА быть фото-сообщением - editMessageMedia
падает на текстовом сообщении и наоборот, поэтому переход от единственного
текстового состояния ("слов мало на старте") к фото-карточке всегда идёт
через НОВОЕ сообщение, не правку (см. handle_page_step_tap). Активный вопрос
студента живёт в памяти процесса (_active_question), не в БД - бот
деплоится сам на каждый push ([[feedback_auto_deploy]]), поэтому тап по
кнопке после рестарта не должен молчать: обработчик просто присылает
новую карточку без начисления балла за этот тап (advisor 17.08.2026,
пункт устойчивости к рестарту).

Номер страницы - это ЗАКЛАДКА студента ("дошёл до этой страницы"), не
"добавь именно эту одну страницу" (решение пользователя 17.08.2026,
пятый заход, после прямой жалобы "почему у меня страница не меняется,
слова должны идти рандомно автоматом"). Слова вопросов идут вперемешку
со ВСЕХ страниц от начала суры до закладки разом (get_words_for_bookmark,
core/mufradat.py) - студенту не нужно вручную добавлять каждую страницу.
Первый ввод страницы - текстом (студент явно не ориентируется, пока
закладки нет), дальше - кнопки ➕/➖ (на 1 страницу), без повторного
набора текста - именно так описал пользователь: "рядом кнопка плюс,
кнопка минус тоже".
"""
import logging
import re

from core.db import find_user_by_phone, get_learning_group, get_group_tasks, save_report, get_date, get_today_report
from core.mufradat import (
    generate_question, get_progress_map, record_answer,
    set_current_page, get_current_page, get_words_for_bookmark, mark_page_trained, get_leaderboard,
    record_daily_answered_word, DAILY_WORDS_FOR_TASK_CREDIT, compute_overall_score,
)
from core.quran_pages import resolve_page, page_for_ayah, BAQARA_FIRST_PAGE, BAQARA_LAST_PAGE
from core.tg import (
    send_message, send_message_with_button_rows, edit_message_with_button_rows,
    send_photo_bytes_with_button_rows, edit_message_media_with_button_rows,
    edit_message_caption_with_button_rows,
)
from core.mufradat_render import render_word_png_bytes

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
    if get_current_page(user_id) is None:
        _awaiting_page.add(user_id)
        await send_message(chat_id, _page_prompt_text())
        return
    await _send_new_card(user_id, chat_id, get_words_for_bookmark(user_id))


async def handle_page_text(user_id, chat_id, text):
    """Возвращает True, если сообщение перехвачено (студент ждал вопрос
    про номер страницы - только ПЕРВЫЙ ввод, пока закладки ещё нет,
    дальше закладка двигается кнопками ➕/➖) - вызывающий код тогда не
    должен обрабатывать text дальше."""
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
    await _send_new_card(user_id, chat_id, get_words_for_bookmark(user_id))
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
    word_page = page_for_ayah(q["word"]["ayah_number"])
    bookmark_page = get_current_page(user_id)
    lines = []
    if feedback:
        lines.append(feedback)
        lines.append("")
    lines.append(f"📖 Твоя страница: {bookmark_page}  (слово со стр. {word_page})")
    # Само арабское слово - в картинке (core/mufradat_render.py), не в тексте:
    # Telegram HTML не умеет font-size, крупный текст можно получить только
    # рендером в PNG (решение пользователя 18.08.2026 - "мелко читать").
    lines.append(f"\n✅ Верно за сеанс: {session_correct}")
    if overall_score:
        lines.append(_format_overall_score(overall_score))
    text = "\n".join(lines)

    opts = q["options"]
    rows = []
    for i in range(0, len(opts), 2):
        row = [(opts[j], f"muf:{user_id}:{j}") for j in (i, i + 1) if j < len(opts)]
        rows.append(row)
    # ➕/➖ двигают ЗАКЛАДКУ на 1 страницу (не текстовый ввод - решение
    # пользователя 17.08.2026, пятый заход) - "-" неактивна на BAQARA_FIRST_PAGE,
    # "+" на BAQARA_LAST_PAGE, но Telegram не умеет отключать кнопки без
    # изменения callback_data - тап на границе просто no-op в обработчике.
    rows.append([("➖", f"mufdec:{user_id}"), ("➕", f"mufinc:{user_id}")])
    rows.append([("✅ Закончить", f"mufend:{user_id}")])
    rows.append([("🏆 Рейтинг", f"muftop:{user_id}")])
    return text, rows


async def _send_new_card(user_id, chat_id, words_pool):
    progress = get_progress_map(user_id, [w["id"] for w in words_pool])
    q = generate_question(words_pool, progress)
    if q is None:
        await send_message_with_button_rows(
            chat_id, "Пока маловато слов для тренажёра 🤲 Сдвинь страницу дальше.",
            [[("➖", f"mufdec:{user_id}"), ("➕", f"mufinc:{user_id}")]]
        )
        return

    overall_score = compute_overall_score(user_id)
    text, rows = _render_card(user_id, q, 0, overall_score)
    photo = render_word_png_bytes(q["word"]["arabic_text"])
    resp = await send_photo_bytes_with_button_rows(chat_id, photo, "word.png", text, rows)
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
    await send_message(
        chat_id,
        f"🎉 Задание «Слова» на сегодня засчитано — {DAILY_WORDS_FOR_TASK_CREDIT} разных слов проработано!"
    )

    if group["chat_id"]:
        score = compute_overall_score(user_id)
        score_part = f" (вес {score['score10']:.2f}/10)" if score else ""
        # Короткая расшифровка "что такое муфрадат" - в группе это видят
        # ВСЕ, не только сам студент, а тренажёр живёт в личке с ботом
        # (пользователь 18.08.2026: непонятно со стороны, что за муфрадат).
        await send_message(
            group["chat_id"],
            f"📖 {user['name']} отработал(а) дневной сет {DAILY_WORDS_FOR_TASK_CREDIT} слов на тренажёре "
            f"муфрадат (карточки арабских слов Корана с переводом){score_part}."
        )


async def handle_answer_tap(user_id, chat_id, message_id, slot):
    state = _active_question.get(user_id)
    if not state or state.get("message_id") != message_id:
        # Память потеряна (рестарт бота) или тап по устаревшей карточке -
        # не молчим, шлём свежую карточку, без начисления балла за этот тап.
        pool = get_words_for_bookmark(user_id)
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
    # Отмечаем ЗАКЛАДКУ, не страницу слова (state["word_page"]) - вопрос
    # взят из пула 2..закладка равномерно, страница СЛУЧАЙНОГО слова почти
    # всегда НИЖЕ закладки (1 из N шанс совпасть с ней) - если отмечать её,
    # MAX(page_number) в mufradat_trained_pages (глубина для /muftop) годами
    # отставал бы от реальной закладки студента (advisor 17.08.2026, восьмой
    # заход). Закладка - и есть честное свидетельство "дошёл досюда и хотя
    # бы раз ответил", подделать её нельзя не отвечая (mark_page_trained
    # вызывается только здесь, после реального ответа).
    mark_page_trained(user_id, get_current_page(user_id))

    session_correct = state.get("session_correct", 0) + (1 if correct else 0)

    count_today = record_daily_answered_word(user_id, state["word_id"])
    if count_today >= DAILY_WORDS_FOR_TASK_CREDIT:
        await _credit_task_if_applicable(user_id, chat_id)

    pool = get_words_for_bookmark(user_id)
    progress = get_progress_map(user_id, [w["id"] for w in pool])
    q = generate_question(pool, progress)
    feedback = "✅ Верно!" if correct else f"❌ Не то, правильно: {state['target']}"
    # Короткая подсказка до порога зачёта задания "Слова" - решение
    # пользователя 17.08.2026 (тот же день, что и снижение порога 20->15).
    # Первая формулировка ("и «Слова» засчитается") была неясной - непонятно,
    # ЧТО именно засчитается (пользователь: "не совсем понятно до чего
    # осталось") - расписано явно.
    if count_today < DAILY_WORDS_FOR_TASK_CREDIT:
        remaining = DAILY_WORDS_FOR_TASK_CREDIT - count_today
        feedback += f"\n📝 Ещё {remaining} разных слов сегодня — и дневное задание «Слова» будет засчитано"

    if q is None:
        _active_question.pop(user_id, None)
        # Раньше это было недостижимо (слова только теряли вес, не
        # исключались) - с жёстким исключением "отдыхающих" выученных слов
        # (RECHECK_AFTER_DAYS) пул реально может опустеть, если студент
        # прошёл всю закладку - тупик без объяснения и кнопок был багом
        # (advisor 17.08.2026, пятый заход).
        text = feedback + "\n\nСлова на твоей закладке пока закончились 🤲 Сдвинь страницу дальше."
        # Картинка (последнее показанное слово) остаётся - меняем только
        # подпись/клавиатуру, editMessageMedia тут не нужен.
        await edit_message_caption_with_button_rows(
            chat_id, message_id, text, [[("➕", f"mufinc:{user_id}")]]
        )
        return

    # pool/progress уже те же, что читает compute_overall_score по умолчанию
    # (закладка), не дублируем поход в БД (advisor 17.08.2026, пятый заход).
    overall_score = compute_overall_score(user_id, words=pool, progress=progress)
    text, rows = _render_card(user_id, q, session_correct, overall_score, feedback)
    _active_question[user_id] = {
        "word_id": q["word"]["id"], "target": q["word"]["translation"], "options": q["options"],
        "word_page": page_for_ayah(q["word"]["ayah_number"]),
        "chat_id": chat_id, "message_id": message_id, "session_correct": session_correct,
        "start_score10": state.get("start_score10"),
    }
    photo = render_word_png_bytes(q["word"]["arabic_text"])
    await edit_message_media_with_button_rows(chat_id, message_id, photo, "word.png", text, rows)


async def handle_page_step_tap(user_id, chat_id, message_id, delta):
    """Кнопки ➕/➖ - двигают закладку на 1 страницу без текстового ввода
    (решение пользователя 17.08.2026, пятый заход). Если закладки ещё нет
    вообще (не должно случиться - кнопка появляется только на карточке,
    а карточка требует закладку - но на случай гонки/старой карточки)
    откатываемся на текстовый первый ввод."""
    current = get_current_page(user_id)
    if current is None:
        _active_question.pop(user_id, None)
        _awaiting_page.add(user_id)
        await send_message(chat_id, _page_prompt_text())
        return

    new_page = max(BAQARA_FIRST_PAGE, min(BAQARA_LAST_PAGE, current + delta))
    if new_page == current:
        return  # уже на границе диапазона - no-op, Telegram не отключает кнопки

    set_current_page(user_id, new_page, *resolve_page(new_page))

    pool = get_words_for_bookmark(user_id)
    progress = get_progress_map(user_id, [w["id"] for w in pool])
    q = generate_question(pool, progress)
    overall_score = compute_overall_score(user_id, words=pool, progress=progress)

    # Карточка - ФОТО только если для message_id есть активное состояние
    # (создаётся _send_new_card/предыдущим тапом). Самое первое сообщение
    # при нехватке слов на старте - ТЕКСТОВОЕ (слова для картинки ещё нет,
    # см. _send_new_card) - если теперь слов хватило, editMessageMedia
    # упадёт на текстовом сообщении ("there is no media to edit"), нужна
    # НОВАЯ фото-карточка, а не правка (advisor 18.08.2026).
    state = _active_question.get(user_id)
    is_photo_card = bool(state and state.get("message_id") == message_id)

    if q is None:
        _active_question.pop(user_id, None)
        rows = [[("➖", f"mufdec:{user_id}"), ("➕", f"mufinc:{user_id}")]]
        if is_photo_card:
            await edit_message_caption_with_button_rows(chat_id, message_id, "Пока маловато слов для тренажёра 🤲", rows)
        else:
            await edit_message_with_button_rows(chat_id, message_id, "Пока маловато слов для тренажёра 🤲", rows)
        return

    # Тап по устаревшей карточке (другой message_id) не наследует её
    # session_correct - та же защита, что в handle_answer_tap.
    session_correct = state.get("session_correct", 0) if is_photo_card else 0

    # start_score10 ВСЕГДА пересчитывается заново, не наследуется - шаг
    # закладки меняет знаменатель (total слов), сравнение со старым
    # start_score10 сравнивало бы разные знаменатели и могло показать
    # ложное падение веса на "Закончить" без единой ошибки студента
    # (advisor 17.08.2026, восьмой заход).
    text, rows = _render_card(user_id, q, session_correct, overall_score)
    photo = render_word_png_bytes(q["word"]["arabic_text"])
    if is_photo_card:
        await edit_message_media_with_button_rows(chat_id, message_id, photo, "word.png", text, rows)
    else:
        # Старое текстовое сообщение остаётся как есть (мёртвые кнопки) -
        # шлём новую фото-карточку, редактировать текст->фото нельзя.
        resp = await send_photo_bytes_with_button_rows(chat_id, photo, "word.png", text, rows)
        message_id = ((resp or {}).get("result") or {}).get("message_id") or message_id

    _active_question[user_id] = {
        "word_id": q["word"]["id"], "target": q["word"]["translation"], "options": q["options"],
        "word_page": page_for_ayah(q["word"]["ayah_number"]),
        "chat_id": chat_id, "message_id": message_id, "session_correct": session_correct,
        "start_score10": overall_score["score10"] if overall_score else None,
    }


def _leaderboard_for_this_bot():
    """core/mufradat.py:get_leaderboard читает ОБЩУЮ sources/hadiths.db -
    мужской и женский бот пишут в один файл, движок намеренно не знает о
    поле (разделение полов - забота Telegram-обвязки, не движка). Рейтинг
    ВСЕГДА раздельный по полу, никогда не смешивается (жёсткое правило
    пользователя 17.08.2026, найдено advisor'ом как утечка "Студент XXXX
    (—)" из другого бота). Фильтруем по тому, существует ли студент в БД
    ИМЕННО ЭТОГО бота (users - per-profile, quran_male.db/quran_female.db,
    см. config.DB) - явного поля "пол" в mufradat_* таблицах нет и не
    нужно, разделение уже есть на уровне БД пользователей."""
    filtered = []
    for label, entries in get_leaderboard():
        own = [(uid, score) for uid, score in entries if find_user_by_phone(uid)]
        filtered.append((label, own))
    return filtered


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

        rank_info = _find_rank(_leaderboard_for_this_bot(), user_id)
        if rank_info:
            label, rank, total_in_bracket, _score = rank_info
            lines.append(f"🏆 Место среди изучающих стр. {label}: {rank} из {total_in_bracket}")

    # "Закончить" - кнопка только на фото-карточке (_render_card), картинка
    # (последнее слово) остаётся видна - меняем только подпись.
    await edit_message_caption_with_button_rows(chat_id, message_id, "\n".join(lines), [])


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
                # Раньше показывали mastered (выученные) - при MASTERY_STREAK=4
                # это почти у всех 0 первые дни, рейтинг выглядел "сломанным"
                # (пользователь 18.08.2026: "рейтинг не информативен - 0 слов").
                # Показываем вес (плавный, двигается с первого правильного
                # ответа) и общее число слов, прогнанных за всё время.
                lines.append(
                    f"  {marker}{i}. {_display_name(uid)} ({_group_name(uid)}) — "
                    f"вес {score['score10']:.2f}/10 ({score['attempted']} слов)"
                )
        lines.append("")

    if my_bracket and my_rank > 3:
        lines.append(
            f"Ты среди изучающих стр. {my_bracket}: место {my_rank}, "
            f"вес {my_score['score10']:.2f}/10 ({my_score['attempted']} слов проработано)."
        )
    elif my_bracket is None:
        lines.append("Ты ещё не тренировал ни одной страницы — набери /muf 🤲")

    return "\n".join(lines).rstrip()


async def show_leaderboard(user_id, chat_id):
    leaderboard = _leaderboard_for_this_bot()
    await send_message(chat_id, _render_leaderboard_text(user_id, leaderboard))
