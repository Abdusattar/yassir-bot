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
    set_current_page, get_current_page, get_words_for_bookmark, get_leaderboard,
    record_daily_answered_word, DAILY_WORDS_FOR_TASK_CREDIT, compute_overall_score,
    get_current_lang, set_current_lang, SUPPORTED_LANGUAGES,
)
from core.quran_pages import resolve_page, page_for_ayah, FIRST_PAGE, LAST_PAGE
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
        "📖 Какая страница мусхафа? (суры Аль-Бакара — Юнус, страницы "
        f"{FIRST_PAGE}-{LAST_PAGE})\n"
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
    if resolve_page(page_number) is None:
        await send_message(
            chat_id,
            f"Страницы {FIRST_PAGE}-{LAST_PAGE} мусхафа (суры Аль-Бакара — Юнус). "
            "Напиши номер в этом диапазоне, например: 23"
        )
        return True

    _awaiting_page.discard(user_id)
    set_current_page(user_id, page_number)
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
    word_page = page_for_ayah(q["word"]["surah_number"], q["word"]["ayah_number"])
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
    # word_id здесь и во всех callback_data/_active_question ниже - на самом
    # деле progress_key (core/sampler.py, 26.08.2026): id "представителя"
    # пары арабский-перевод, общий для всех страниц, где она встречается -
    # не id конкретной строки q["word"]["id"] (та тоже существует, но здесь
    # не нужна).
    word_id = q["word"]["progress_key"]
    rows = []
    for i in range(0, len(opts), 2):
        # word_id в callback_data (18.08.2026) - защита от гонки при
        # двойном тапе на слабом интернете (реальный кейс - Руслан N-2a):
        # карточка правится НА МЕСТЕ (тот же message_id), так что если
        # первый тап уже успел полностью обработаться и подвинуть вопрос
        # дальше, второй (повторный клик) раньше проходил проверку "тот
        # же message_id" и применял свою позицию кнопки к УЖЕ ДРУГОМУ
        # вопросу - слот совпадал случайно, чаще всего с неверным
        # вариантом. handle_answer_tap теперь сверяет word_id с текущим
        # активным вопросом и молча игнорирует несовпадение (advisor
        # 18.08.2026).
        row = [(opts[j], f"muf:{user_id}:{word_id}:{j}") for j in (i, i + 1) if j < len(opts)]
        rows.append(row)
    # Переключатель языка перевода (26.08.2026) - отдельной строкой над
    # ➖/➕ (место выбрано пользователем по мокапу), открывает список языков
    # (show_language_menu). Подпись показывает ТЕКУЩИЙ язык этой карточки.
    current_lang = get_current_lang(user_id)
    lang_label = SUPPORTED_LANGUAGES.get(current_lang, current_lang)
    rows.append([(f"🌐 {lang_label} ▾", f"muflang:{user_id}")])
    # ➕/➖ двигают ЗАКЛАДКУ на 1 страницу (не текстовый ввод - решение
    # пользователя 17.08.2026, пятый заход) - "-" неактивна на FIRST_PAGE,
    # "+" на LAST_PAGE, но Telegram не умеет отключать кнопки без
    # изменения callback_data - тап на границе просто no-op в обработчике.
    rows.append([("➖", f"mufdec:{user_id}"), ("➕", f"mufinc:{user_id}")])
    rows.append([("✅ Закончить", f"mufend:{user_id}")])
    rows.append([("🏆 Рейтинг", f"muftop:{user_id}")])
    return text, rows


async def _send_new_card(user_id, chat_id, words_pool):
    progress = get_progress_map(user_id, [w["progress_key"] for w in words_pool])
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
        "word_id": q["word"]["progress_key"], "target": q["word"]["translation"], "options": q["options"],
        "word_page": page_for_ayah(q["word"]["surah_number"], q["word"]["ayah_number"]),
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
        score_part = f", вес {score['score10']:.2f}/10" if score else ""
        # Тот же короткий формат "Имя, Слова +.", что и у обычной сдачи
        # текстом в группе (core/handlers.py, SHORT_TASKS) - раньше здесь
        # было длинное отдельное предложение, из которого не считывалось
        # "сдал дневное задание" (пользователь 18.08.2026). "через тренажёр"
        # поясняет, откуда взялось выполнение - обычно сдача идёт текстом
        # прямо в группе, здесь источник другой (личка с ботом).
        await send_message(
            group["chat_id"],
            f"{user['name']}, Слова + (через тренажёр{score_part})."
        )


async def handle_stale_answer_tap(user_id, chat_id):
    """Тап по СТАРОЙ карточке (callback_data без word_id - формат до
    18.08.2026), ещё висящей у студента в момент этого деплоя. Тот же
    путь, что "память потеряна" в handle_answer_tap - свежая карточка,
    без начисления балла за этот тап (сам вопрос на старой карточке уже
    не восстановить, слот не с чем сверить)."""
    pool = get_words_for_bookmark(user_id)
    if not pool:
        await send_message(chat_id, "Сессия тренажёра сброшена, набери /muf заново 🤲")
        return
    await _send_new_card(user_id, chat_id, pool)


async def handle_answer_tap(user_id, chat_id, message_id, word_id, slot):
    """word_id - какой именно вопрос отвечал студент (из callback_data,
    18.08.2026) - НЕ то же самое, что message_id (карточка правится на
    месте, message_id не меняется между вопросами). Защита от гонки при
    двойном тапе на слабом интернете: если первый тап уже успел полностью
    обработаться (синхронно, без await) и подвинуть _active_question на
    СЛЕДУЮЩИЙ вопрос до того, как второй тап дошёл до обработки - второй
    тап проходил проверку "тот же message_id" (она не меняется) и
    применял свою позицию кнопки к УЖЕ ДРУГОМУ вопросу, слот совпадал
    почти всегда с неверным вариантом (реальный кейс - Руслан N-2a,
    репорт пользователя 18.08.2026, разбор advisor). word_id ловит именно
    это - несовпадение молча игнорируем, карточка уже честно показывает
    актуальный вопрос, повторно отвечать не нужно."""
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

    if state.get("word_id") != word_id:
        # Тап на уже сменившийся вопрос (см. docstring выше) - молча игнор.
        return

    opts = state["options"]
    if not (0 <= slot < len(opts)):
        return
    chosen = opts[slot]
    correct = (chosen == state["target"])
    # Удаляем состояние СРАЗУ после проверки word_id, до record_answer -
    # закрывает более редкое окно гонки на await внутри
    # _credit_task_if_applicable ниже (если бы состояние осталось, второй
    # тап с ТЕМ ЖЕ word_id мог проскочить туда же, пока первый ещё не
    # дошёл до переприсвоения state в конце функции). Любой конкурентный
    # тап после этой строки просто попадёт в ветку "state потерян" выше
    # (advisor 18.08.2026).
    _active_question.pop(user_id, None)
    record_answer(user_id, state["word_id"], correct)

    session_correct = state.get("session_correct", 0) + (1 if correct else 0)

    count_today = record_daily_answered_word(user_id, state["word_id"])
    if count_today >= DAILY_WORDS_FOR_TASK_CREDIT:
        await _credit_task_if_applicable(user_id, chat_id)

    pool = get_words_for_bookmark(user_id)
    progress = get_progress_map(user_id, [w["progress_key"] for w in pool])
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
        "word_id": q["word"]["progress_key"], "target": q["word"]["translation"], "options": q["options"],
        "word_page": page_for_ayah(q["word"]["surah_number"], q["word"]["ayah_number"]),
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

    new_page = max(FIRST_PAGE, min(LAST_PAGE, current + delta))
    if new_page == current:
        return  # уже на границе диапазона - no-op, Telegram не отключает кнопки

    set_current_page(user_id, new_page)

    pool = get_words_for_bookmark(user_id)
    progress = get_progress_map(user_id, [w["progress_key"] for w in pool])
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
        "word_id": q["word"]["progress_key"], "target": q["word"]["translation"], "options": q["options"],
        "word_page": page_for_ayah(q["word"]["surah_number"], q["word"]["ayah_number"]),
        "chat_id": chat_id, "message_id": message_id, "session_correct": session_correct,
        "start_score10": overall_score["score10"] if overall_score else None,
    }


def _lang_menu_rows(user_id):
    rows = [[(label, f"muflangset:{user_id}:{code}")] for code, label in SUPPORTED_LANGUAGES.items()]
    rows.append([("⬅️ Назад", f"muflangback:{user_id}")])
    return rows


async def show_language_menu(user_id, chat_id, message_id):
    """Тап по кнопке "🌐 <Язык> ▾" на карточке (26.08.2026) - правит ТУ ЖЕ
    карточку (фото не трогаем, editMessageCaption), заменяя подпись/клавиатуру
    списком языков. "⬅️ Назад" без изменений возвращает карточку с вопросом
    (handle_language_back_tap), тап по языку - переключает и тоже возвращает
    карточку, уже на новом языке (handle_language_set_tap)."""
    current = get_current_lang(user_id)
    text = f"🌐 Выбери язык перевода (сейчас: {SUPPORTED_LANGUAGES.get(current, current)})"
    await edit_message_caption_with_button_rows(chat_id, message_id, text, _lang_menu_rows(user_id))


async def _refresh_card(user_id, chat_id, message_id, session_correct, start_score10):
    """Перегенерирует карточку (новый вопрос из ТЕКУЩЕГО пула/языка
    студента) и правит уже существующее фото-сообщение на месте - общий путь
    для "⬅️ Назад" из меню языка и для применения нового языка (26.08.2026).
    session_correct/start_score10 - что показывать на новой карточке (см.
    вызывающий код: "Назад" сохраняет то, что было в сеансе, смена языка
    начинает сеанс заново - другой пул слов, другой прогресс)."""
    pool = get_words_for_bookmark(user_id)
    progress = get_progress_map(user_id, [w["progress_key"] for w in pool])
    q = generate_question(pool, progress)
    overall_score = compute_overall_score(user_id, words=pool, progress=progress)

    if q is None:
        _active_question.pop(user_id, None)
        await edit_message_caption_with_button_rows(
            chat_id, message_id,
            "Слова на твоей закладке пока закончились 🤲 Сдвинь страницу дальше.",
            [[("➕", f"mufinc:{user_id}")]]
        )
        return

    text, rows = _render_card(user_id, q, session_correct, overall_score)
    photo = render_word_png_bytes(q["word"]["arabic_text"])
    await edit_message_media_with_button_rows(chat_id, message_id, photo, "word.png", text, rows)
    _active_question[user_id] = {
        "word_id": q["word"]["progress_key"], "target": q["word"]["translation"], "options": q["options"],
        "word_page": page_for_ayah(q["word"]["surah_number"], q["word"]["ayah_number"]),
        "chat_id": chat_id, "message_id": message_id, "session_correct": session_correct,
        "start_score10": start_score10 if start_score10 is not None else (
            overall_score["score10"] if overall_score else None
        ),
    }


async def handle_language_back_tap(user_id, chat_id, message_id):
    state = _active_question.get(user_id)
    same_card = bool(state and state.get("message_id") == message_id)
    session_correct = state.get("session_correct", 0) if same_card else 0
    start_score10 = state.get("start_score10") if same_card else None
    await _refresh_card(user_id, chat_id, message_id, session_correct, start_score10)


async def handle_language_set_tap(user_id, chat_id, message_id, language):
    """language уже проверен вызывающим кодом (bot.py) на принадлежность
    SUPPORTED_LANGUAGES перед вызовом - set_current_lang сам по себе тоже
    молча игнорирует неизвестный код (core/mufradat.py), двойная защита.
    Сеанс визуально начинается заново (session_correct=0, start_score10
    пересчитывается) - другой язык означает другой пул progress_key, старые
    числа сеанса были бы не про то же самое (тот же паттерн, что при
    смене страницы, см. handle_page_step_tap)."""
    set_current_lang(user_id, language)
    await _refresh_card(user_id, chat_id, message_id, 0, None)


def _leaderboard_for_this_bot():
    """core/mufradat.py:get_leaderboard читает ОБЩУЮ sources/hadiths.db -
    мужской и женский бот пишут в один файл, движок намеренно не знает о
    поле (разделение полов - забота Telegram-обвязки, не движка). Рейтинг
    ВСЕГДА раздельный по полу, никогда не смешивается (жёсткое правило
    пользователя 17.08.2026, найдено advisor'ом как утечка "Студент XXXX
    (—)" из другого бота). Фильтруем по тому, существует ли студент в БД
    ИМЕННО ЭТОГО бота (users - per-profile, quran_male.db/quran_female.db,
    см. config.DB) - явного поля "пол" в mufradat_* таблицах нет и не
    нужно, разделение уже есть на уровне БД пользователей.

    Плоский, отсортированный, БЕЗ разбивки на дивизионы (см. _split_by_division
    ниже) - движок (core/mufradat.py) остаётся дивизион-слепым, разбивка
    только в этой Telegram-обвязке. Порядок важен: гендерный фильтр здесь
    выполняется ДО разбивки на дивизионы - если бы разбивали раньше,
    фильтр пришлось бы дублировать в обоих дивизионах (advisor 18.08.2026,
    четвёртый заход).

    ВКЛЮЧАЕТ студентов без группы (find_user_by_phone требует только
    запись в users, не членство в группе) - это НЕ то же самое, что
    ПУБЛИЧНЫЙ групповой рейтинг (см. _group_leaderboard_for_this_bot) -
    /muf вообще не проверяет группу (start_trainer работает по голому
    user_id), кто-то тренируется, ни разу не вступив в группу. Список
    нужен как есть (гендер-фильтр, группа не важна) для личной статистики
    таких студентов (_render_personal_stats_text) - решение пользователя
    18.08.2026, пятый заход: "пусть тренируется, нет ничего плохого... в
    рейтинг не включать, но ему лично рейтинг отправлять... и показывать
    его место" - место среди ВСЕХ тренирующихся этого бота, не только
    группы."""
    return [(uid, score) for uid, score in get_leaderboard() if find_user_by_phone(uid)]


def _group_leaderboard_for_this_bot():
    """ПУБЛИЧНЫЙ групповой рейтинг (то, что видят все в /muftop) - сужает
    _leaderboard_for_this_bot до студентов, состоящих хоть в какой-то
    группе (get_learning_group). Студент без группы тренируется наравне
    со всеми (см. _leaderboard_for_this_bot), но сравнивать его с группой
    в общем топе не имеет смысла - решение пользователя 18.08.2026."""
    return [(uid, score) for uid, score in _leaderboard_for_this_bot() if get_learning_group(uid)]


# Порог дивизиона - решение пользователя 18.08.2026, четвёртый заход про
# рейтинг за один день: "они на той странице где учат Коран, кто-то раньше
# начал, поэтому больше страниц" - группировка по РЕАЛЬНОМУ прогрессу
# заучивания, не про честность вычислений (та уже решена depth-множителем
# в самой формуле сортировки, см. core/mufradat.py:get_leaderboard).
# Порог 10 - предложение пользователя, проверено на живых данных: 8
# студентов на <=10, 7 на >10 - почти ровный сплит (не пирамида "3-10
# большинство", как предполагал пользователь, но для двух дивизионов
# ровный сплит даже лучше).
_DIVISION_THRESHOLD = 10
_DIVISION_LABELS = ("🥇 Дивизион 1 (стр. 11+)", "🥈 Дивизион 2 (стр. 2-10)")


def _split_by_division(leaderboard):
    """leaderboard - уже отсортированный ПЛОСКИЙ список (_leaderboard_for_this_bot).
    Разбивка чисто на уровне отображения - каждый дивизион сохраняет
    относительный порядок (уже отсортирован по единой формуле, глубина
    внутри дивизиона ПРОДОЛЖАЕТ работать - Дивизион 1 охватывает стр.11-221,
    это 20-кратный разброс размера пула, без depth-множителя внутри самого
    дивизиона повторилась бы та же проблема Муслим/Сатар, только на его
    масштабе, advisor 18.08.2026). Возвращает [(label, entries), ...]."""
    div1 = [(uid, score) for uid, score in leaderboard if score["page"] > _DIVISION_THRESHOLD]
    div2 = [(uid, score) for uid, score in leaderboard if score["page"] <= _DIVISION_THRESHOLD]
    return list(zip(_DIVISION_LABELS, (div1, div2)))


def _find_rank(divisions, user_id):
    for label, entries in divisions:
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

        # _group_leaderboard_for_this_bot (не _leaderboard_for_this_bot) -
        # студент без группы тут просто не найдётся (rank_info=None, строка
        # молча не показывается) - его личное место показывает /muftop
        # (_render_personal_stats_text), не это сообщение о конце сеанса.
        rank_info = _find_rank(_split_by_division(_group_leaderboard_for_this_bot()), user_id)
        if rank_info:
            label, rank, total, _score = rank_info
            lines.append(f"🏆 Место в {label}: {rank} из {total}")

    # "Закончить" - кнопка только на фото-карточке (_render_card), картинка
    # (последнее слово) остаётся видна - меняем только подпись.
    await edit_message_caption_with_button_rows(chat_id, message_id, "\n".join(lines), [])


def _display_name(user_id):
    user = find_user_by_phone(user_id)
    return user["name"] if user else f"Студент {user_id[-4:]}"


def _group_name(user_id):
    group = get_learning_group(user_id)
    return group["title"] if group and group["title"] else "—"


_DIVISION_TOP_N = 7  # решение пользователя 18.08.2026, пятый заход - запас
# на рост группы (сейчас 7-8 студентов на дивизион, при большем числе топ-7
# не растянет сообщение до бесконечности).


def _render_leaderboard_text(user_id, leaderboard):
    """leaderboard - результат _leaderboard_for_this_bot(): [(uid,
    score_dict), ...], плоский отсортированный список по
    wilson*log10(1+attempted)*log10(1+page) - см. модульный docstring
    core/mufradat.py:get_leaderboard. Разбивается на два дивизиона по
    РЕАЛЬНОМУ прогрессу заучивания Корана (_split_by_division) - решение
    пользователя 18.08.2026, четвёртый заход: "они на той странице где
    учат Коран, кто-то раньше начал, поэтому больше страниц" - сравнивать
    напрямую тех, кто в разных точках пути, не совсем справедливо, даже
    при depth-множителе в самой формуле (тот уже не даёт мелким страницам
    ПРОБИТЬСЯ наверх - проверено математически, идеальный студент стр.3
    упирается в потолок ниже скромного студента стр.20 - но не решает
    вопрос мотивации/сравнимости для тех, кто просто позже начал).

    Топ-7 внутри каждого дивизиона; если сам студент не попал - отдельной
    строкой под дивизионом (тот же паттерн, что был в плоской версии до
    дивизионов, решение пользователя 18.08.2026, пятый заход)."""
    if not leaderboard:
        return "Пока никто не тренировал муфрадат достаточно, чтобы попасть в рейтинг 🤲 Начни первым: /muf"

    lines = ["🏆 Топ по муфрадату — точность, объём и глубина закладки\n"]

    for label, entries in _split_by_division(leaderboard):
        if not entries:
            continue
        lines.append(f"{label}:")
        my_rank = my_score = None
        for i, (uid, score) in enumerate(entries, start=1):
            if uid == user_id:
                my_rank, my_score = i, score
            if i <= _DIVISION_TOP_N:
                marker = "👉 " if uid == user_id else ""
                lines.append(
                    f"{marker}{i}. {_display_name(uid)} ({_group_name(uid)}) — "
                    f"{score['accuracy']:.0f}% ({score['correct']}/{score['n']} карточек), стр. {score['page']}"
                )
        if my_rank is not None and my_rank > _DIVISION_TOP_N:
            lines.append(
                f"👉 Ты: место {my_rank} из {len(entries)}, "
                f"{my_score['accuracy']:.0f}% ({my_score['correct']}/{my_score['n']} карточек)."
            )
        lines.append("")

    lines.append(
        "ℹ️ Место — внутри своего дивизиона (по глубине закладки), "
        "зависит от точности и объёма карточек."
    )

    return "\n".join(lines).rstrip()


def _render_personal_stats_text(user_id):
    """Для студента БЕЗ группы (get_learning_group(user_id) пусто) -
    решение пользователя 18.08.2026, пятый заход: "пусть тренируется, нет
    ничего плохого... в рейтинг не включать, но ему лично рейтинг
    отправлять... и показывать его место". Место - среди ВСЕХ
    тренирующихся этого бота (_leaderboard_for_this_bot, БЕЗ фильтра по
    группе - в отличие от публичного _group_leaderboard_for_this_bot),
    личный ориентир, не появляется в /muftop у других."""
    full = _leaderboard_for_this_bot()
    own = next(
        ((i, score) for i, (uid, score) in enumerate(full, start=1) if uid == user_id),
        None
    )
    if not own:
        return (
            "Ты пока не в учебной группе, поэтому общий рейтинг тебе не "
            "показываем — но тренироваться можно свободно 🤲 Набери /muf"
        )
    rank, score = own
    return (
        f"📊 Твой результат: {score['accuracy']:.0f}% ({score['correct']}/{score['n']} карточек), "
        f"стр. {score['page']}\n"
        f"Место среди всех тренирующихся: {rank} из {len(full)}\n\n"
        "Ты пока не в учебной группе, поэтому не участвуешь в общем групповом "
        "рейтинге — но тренироваться можно свободно, продолжай в том же духе 🤲"
    )


async def show_leaderboard(user_id, chat_id):
    if not get_learning_group(user_id):
        await send_message(chat_id, _render_personal_stats_text(user_id))
        return
    leaderboard = _group_leaderboard_for_this_bot()
    await send_message(chat_id, _render_leaderboard_text(user_id, leaderboard))
