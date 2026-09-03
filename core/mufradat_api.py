"""HTTP API тренажёра муфрадата для веб-версии внутри YassirApp Mini App
(29.08.2026) - тонкая обвязка НАД тем же движком core/mufradat.py, что и
Telegram-версия (core/mufradat_bot.py). Вся игровая логика (подбор слова,
дистракторы, прогресс, рейтинг, зачёт дневного задания) НЕ дублируется -
импортируется напрямую, включая "приватные" (_-префикс) хелперы рейтинга
из mufradat_bot - они уже транспорт-независимы, дублировать их означало бы
рассинхрон дивизионов/формулы между ботом и вебом.

Сессия активного вопроса (_active) - СВОЙ словарь, отдельный от
mufradat_bot._active_question: тот привязан к message_id (Telegram
редактирует карточку на месте), здесь это не нужно - веб-клиент просто
шлёт word_id вопроса, на который отвечает, и сервер сверяет его с
активным состоянием (та же защита от гонки двойного тапа, что и в
mufradat_bot.handle_answer_tap, но без message_id - HTTP запрос/ответ уже
атомарен на уровне одного вызова).

Аутентификация - Telegram initData (HMAC-SHA256 подписанная строка,
Telegram.WebApp.initData на фронтенде) - см. validate_init_data. user_id
везде дальше - str(telegram_user_id), тот же формат, что использует вся
остальная кодовая база (users.phone это Telegram ID, см. память проекта) -
маппинга на отдельный внутренний id не нужно.
"""
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from aiohttp import web

from config import TELEGRAM_TOKEN
from core.db import get_learning_group
from core.mufradat import (
    generate_question, get_progress_map, record_answer,
    set_current_page, get_current_page, get_words_for_bookmark, compute_overall_score,
    get_current_lang, set_current_lang, SUPPORTED_LANGUAGES,
    record_daily_answered_word, get_daily_answered_count, DAILY_WORDS_FOR_TASK_CREDIT,
    get_starred_question_pool, _is_junk,
)
from core.mufradat_bot import (
    _credit_task_if_applicable, _leaderboard_for_this_bot, _group_leaderboard_for_this_bot,
    _split_by_division, _display_name, _group_name, _find_rank, credit_revision_task,
    submit_hifz_recording, HIFZ_MAX_UPLOAD_BYTES,
)
from core.mushaf_words import (
    add_starred_word, remove_starred_word, list_starred_words,
    get_reading_bookmark, set_reading_bookmark,
    get_hifz_pointer, set_hifz_pointer,
    get_hifz_progress, add_hifz_progress, HIFZ_PROGRESS_TARGET,
)
from core.quran_pages import resolve_page, page_for_ayah, FIRST_PAGE, LAST_PAGE

log = logging.getLogger(__name__)

_active = {}  # user_id -> {word_id, target, options, arabic, surah, ayah, session_correct, start_score10}

_INIT_DATA_MAX_AGE = 86400  # сутки - initData протухает по auth_date, не только по подписи


def validate_init_data(raw, bot_token, max_age_seconds=_INIT_DATA_MAX_AGE):
    """https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app -
    секрет = HMAC_SHA256("WebAppData", bot_token), хэш - HMAC_SHA256(секрет,
    отсортированные "key=value" через \\n, без самого hash). Возвращает dict
    user (id, first_name, ...) или None при любой проблеме (нет исключений
    наружу - вызывающий код просто трактует None как unauthorized)."""
    if not raw or not bot_token:
        return None
    try:
        pairs = dict(parse_qsl(raw, strict_parsing=True))
    except ValueError:
        return None
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        return None
    auth_date = pairs.get("auth_date")
    if not auth_date or time.time() - int(auth_date) > max_age_seconds:
        return None
    user_json = pairs.get("user")
    if not user_json:
        return None
    try:
        return json.loads(user_json)
    except ValueError:
        return None


def with_auth(handler):
    async def wrapped(request):
        raw = request.headers.get("X-Telegram-Init-Data", "")
        user = validate_init_data(raw, TELEGRAM_TOKEN)
        if user is None or not user.get("id"):
            return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request, str(user["id"]))
    return wrapped


def _daily_fields(user_id):
    """X/40 сегодня для шапки тренажёра (28.08.2026) - нужно в КАЖДОМ ответе
    API (не только после ответа на вопрос), иначе счётчик в шапке пропадает
    на экранах needs_page/empty."""
    return {"daily_count": get_daily_answered_count(user_id), "daily_target": DAILY_WORDS_FOR_TASK_CREDIT}


def _question_payload(user_id, state, overall_score, feedback=None):
    payload = {
        "arabic": state["arabic"], "options": state["options"], "word_id": state["word_id"],
        "session_correct": state["session_correct"], "overall_score": overall_score,
        "bookmark_page": get_current_page(user_id),
        "word_page": page_for_ayah(state["surah"], state["ayah"]),
        **_daily_fields(user_id),
    }
    if feedback is not None:
        payload["feedback"] = feedback
    return payload


def _new_question(user_id, session_correct, start_score10):
    """Генерирует вопрос из ТЕКУЩЕГО пула закладки, кладёт в _active,
    возвращает (state, overall_score) или (None, overall_score) если пул
    пуст - вызывающий код решает, что показать в этом случае (см.
    handle_state/handle_answer/handle_page)."""
    pool = get_words_for_bookmark(user_id)
    progress = get_progress_map(user_id, [w["progress_key"] for w in pool])
    overall_score = compute_overall_score(user_id, words=pool, progress=progress)
    # "Мои слова" (29.08.2026) - каждый STARRED_QUESTION_QUOTA-й вопрос
    # гарантированно из личного списка (core/mushaf_words.py), см. докстрочку
    # get_starred_question_pool. Вызывается перед КАЖДЫМ generate_question -
    # эта функция единственная точка генерации вопроса на веб-стороне.
    starred_words = get_starred_question_pool(user_id, get_current_lang(user_id))
    q = generate_question(pool, progress, starred_words=starred_words)
    if q is None:
        _active.pop(user_id, None)
        return None, overall_score
    state = {
        "word_id": q["word"]["progress_key"], "target": q["word"]["translation"], "options": q["options"],
        "arabic": q["word"]["arabic_text"], "surah": q["word"]["surah_number"], "ayah": q["word"]["ayah_number"],
        "session_correct": session_correct,
        "start_score10": start_score10 if start_score10 is not None else (
            overall_score["score10"] if overall_score else None
        ),
    }
    _active[user_id] = state
    return state, overall_score


@with_auth
async def handle_state(request, user_id):
    """GET - текущее состояние тренажёра: активный вопрос (переиспользует
    уже сгенерированный, не крутит новый на каждый рефреш страницы), либо
    needs_page (закладка ещё не установлена), либо empty (пул закончился)."""
    page = get_current_page(user_id)
    if page is None:
        return web.json_response({
            "needs_page": True, "first_page": FIRST_PAGE, "last_page": LAST_PAGE, **_daily_fields(user_id)
        })

    state = _active.get(user_id)
    if state:
        pool_keys = {w["progress_key"] for w in get_words_for_bookmark(user_id)}
        if state["word_id"] not in pool_keys:
            state = None  # закладка сдвинулась в другом клиенте, вопрос больше не из пула
    if not state:
        state, overall_score = _new_question(user_id, 0, None)
        if state is None:
            return web.json_response({
                "empty": True, "bookmark_page": page, "overall_score": overall_score, **_daily_fields(user_id)
            })
    else:
        pool = get_words_for_bookmark(user_id)
        progress = get_progress_map(user_id, [w["progress_key"] for w in pool])
        overall_score = compute_overall_score(user_id, words=pool, progress=progress)

    return web.json_response(_question_payload(user_id, state, overall_score))


@with_auth
async def handle_page(request, user_id):
    """POST {page: N} - первичная установка закладки (студент ни разу не
    открывал тренажёр). POST {delta: 1|-1} - шаг ➕/➖, как в Telegram-версии.
    В обоих случаях активный вопрос сбрасывается - следующий GET /state
    сгенерирует новый из уже сдвинутого пула."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        body = {}

    if "page" in body:
        try:
            page_number = int(body["page"])
        except (TypeError, ValueError):
            return web.json_response({"error": "bad_page"}, status=400)
        if resolve_page(page_number) is None:
            return web.json_response(
                {"error": "out_of_range", "first_page": FIRST_PAGE, "last_page": LAST_PAGE}, status=400
            )
        set_current_page(user_id, page_number)
    elif "delta" in body:
        current = get_current_page(user_id)
        if current is None:
            return web.json_response({"error": "no_page"}, status=400)
        try:
            delta = int(body["delta"])
        except (TypeError, ValueError):
            return web.json_response({"error": "bad_delta"}, status=400)
        set_current_page(user_id, max(FIRST_PAGE, min(LAST_PAGE, current + delta)))
    else:
        return web.json_response({"error": "missing_page_or_delta"}, status=400)

    _active.pop(user_id, None)
    return await _state_body(user_id)


async def _state_body(user_id):
    """Общий хвост handle_state без повторной аутентификации - переиспользуется
    из handle_page/handle_lang/handle_end после того, как user_id уже известен."""
    page = get_current_page(user_id)
    if page is None:
        return web.json_response({
            "needs_page": True, "first_page": FIRST_PAGE, "last_page": LAST_PAGE, **_daily_fields(user_id)
        })
    state, overall_score = _new_question(user_id, 0, None)
    if state is None:
        return web.json_response({
            "empty": True, "bookmark_page": page, "overall_score": overall_score, **_daily_fields(user_id)
        })
    return web.json_response(_question_payload(user_id, state, overall_score))


@with_auth
async def handle_answer(request, user_id):
    """POST {word_id, slot} - ответ на активный вопрос. word_id сверяется с
    _active[user_id] (защита от устаревшего/повторного ответа - тот же
    паттерн, что handle_answer_tap в mufradat_bot.py, без message_id, он тут
    не нужен). Начисление дневного задания "Слова" и уведомление в группу -
    через ТОТ ЖЕ _credit_task_if_applicable, что и Telegram-путь (шлёт
    сообщение в личку/группу как обычно, транспорт ответа API это не меняет)."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "bad_json"}, status=400)

    word_id = body.get("word_id")
    slot = body.get("slot")
    state = _active.get(user_id)

    if not state or state["word_id"] != word_id:
        # Устаревший/повторный ответ - молча не засчитываем, отдаём актуальное состояние.
        return await _state_body(user_id)

    opts = state["options"]
    if not isinstance(slot, int) or not (0 <= slot < len(opts)):
        return web.json_response({"error": "bad_slot"}, status=400)

    chosen = opts[slot]
    correct = chosen == state["target"]
    target = state["target"]
    session_correct = state["session_correct"] + (1 if correct else 0)
    start_score10 = state.get("start_score10")
    _active.pop(user_id, None)

    record_answer(user_id, state["word_id"], correct)
    count_today = record_daily_answered_word(user_id, state["word_id"])
    if count_today >= DAILY_WORDS_FOR_TASK_CREDIT:
        await _credit_task_if_applicable(user_id, user_id)  # chat_id личного чата == user_id

    # "arabic" - слово, на которое студент ТОЛЬКО ЧТО отвечал (30.08.2026).
    # Без него плашка фидбека говорила "правильно: <перевод>", а самого слова
    # на экране уже не было - там отрисован следующий вопрос, и к чему
    # относится верный перевод, понять было нельзя (поймал пользователь).
    feedback = {
        "correct": correct, "target": target, "arabic": state["arabic"],
        "remaining_for_task": max(0, DAILY_WORDS_FOR_TASK_CREDIT - count_today),
    }

    new_state, overall_score = _new_question(user_id, session_correct, start_score10)
    if new_state is None:
        return web.json_response({
            "empty": True, "feedback": feedback, "overall_score": overall_score,
            "bookmark_page": get_current_page(user_id), **_daily_fields(user_id),
        })
    return web.json_response(_question_payload(user_id, new_state, overall_score, feedback))


@with_auth
async def handle_lang_get(request, user_id):
    """GET - текущий язык студента (30.08.2026, для локализации ВСЕГО
    интерфейса, не только слов). Отдельный от POST-обработчика: мусхаф и
    дашборд стартуют раньше тренажёра и /state не дёргают, а язык нужен им
    сразу - иначе интерфейс успевал моргнуть по-русски."""
    return web.json_response({
        "language": get_current_lang(user_id),
        "supported": SUPPORTED_LANGUAGES,
    })


@with_auth
async def handle_lang(request, user_id):
    """POST {language} - переключатель языка перевода (сеанс визуально
    начинается заново, как и в Telegram-версии - другой язык означает
    другой пул progress_key, см. handle_language_set_tap)."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        body = {}
    language = body.get("language")
    if language not in SUPPORTED_LANGUAGES:
        return web.json_response({"error": "bad_language", "supported": SUPPORTED_LANGUAGES}, status=400)
    set_current_lang(user_id, language)
    _active.pop(user_id, None)
    return await _state_body(user_id)


@with_auth
async def handle_end(request, user_id):
    """POST - явное завершение сеанса (аналог кнопки "Закончить"). Возвращает
    итоговый вес, прирост за сеанс и место в дивизионе, если студент в группе."""
    state = _active.pop(user_id, None)
    end_score = compute_overall_score(user_id)
    result = {"overall_score": end_score}
    if end_score and state and state.get("start_score10") is not None:
        result["delta"] = round(end_score["score10"] - state["start_score10"], 2)
    if end_score:
        divisions = _split_by_division(_group_leaderboard_for_this_bot())
        rank_info = _find_rank(divisions, user_id)
        if rank_info:
            label, rank, total, _score = rank_info
            result["rank"] = {
                "division": label,
                # Порядковый номер дивизиона - чтобы приложение подставило
                # НАЗВАНИЕ на языке студента (label - всегда русский, он
                # общий с /muftop в чате, где язык один).
                "division_no": next(
                    (i for i, (lbl, _e) in enumerate(divisions, start=1) if lbl == label), None
                ),
                "place": rank,
                "total": total,
            }
    return web.json_response(result)


@with_auth
async def handle_leaderboard(request, user_id):
    """GET - рейтинг. Тот же гендер-фильтр/дивизионы/Wilson-формула, что и
    /muftop в Telegram (переиспользует приватные хелперы mufradat_bot.py
    напрямую - см. модульный docstring, почему это не дублирование)."""
    if not get_learning_group(user_id):
        full = _leaderboard_for_this_bot()
        own = next(((i, s) for i, (uid, s) in enumerate(full, start=1) if uid == user_id), None)
        return web.json_response({
            "in_group": False, "total": len(full),
            "personal": {"rank": own[0], "score": own[1]} if own else None,
        })

    divisions = []
    for i, (label, entries) in enumerate(_split_by_division(_group_leaderboard_for_this_bot()), start=1):
        divisions.append({
            "label": label,
            "division_no": i,
            "entries": [
                {**score, "name": _display_name(uid), "group": _group_name(uid), "you": uid == user_id}
                for uid, score in entries
            ],
        })
    return web.json_response({"in_group": True, "divisions": divisions})


@with_auth
async def handle_words_list(request, user_id):
    """GET - список "Мои слова" (core/mushaf_words.py - НЕ прогресс
    тренажёра муфрадата, отдельная функция страницы чтения)."""
    return web.json_response({"words": list_starred_words(user_id, get_current_lang(user_id))})


def _parse_word_key(body):
    """(surah, ayah, position) или None при некорректном теле запроса -
    общий разбор для handle_words_add/handle_words_remove."""
    try:
        return int(body["surah"]), int(body["ayah"]), int(body["position"])
    except (KeyError, TypeError, ValueError):
        return None


@with_auth
async def handle_words_add(request, user_id):
    """POST {surah, ayah, position, arabic, translation} - двойной
    тап/клик по слову на странице чтения. arabic/translation приходят от
    клиента (уже отрисованы на странице, см. data-arabic/data-tr в
    mushaf_data/index.html), не пересчитываются заново по mufradat_words -
    только _is_junk-проверка (см. ниже, "*" от старого закэшированного
    клиента)."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "bad_json"}, status=400)
    key = _parse_word_key(body)
    if key is None:
        return web.json_response({"error": "bad_word"}, status=400)
    arabic = (body.get("arabic") or "").strip()
    translation = (body.get("translation") or "").strip()
    if not arabic or not translation or _is_junk(translation):
        # _is_junk ловит "*" (метка склейки API Quran Academy, см.
        # core/mufradat.py:_is_junk) - у клиента со старым закэшированным
        # page*.json тап по хвосту склейки ещё может слать "*" как
        # translation до обновления кэша, серверная сторона не должна
        # пускать её в mushaf_starred_words (29.08.2026).
        return web.json_response({"error": "missing_text"}, status=400)
    add_starred_word(user_id, *key, arabic, translation)
    return web.json_response({"words": list_starred_words(user_id, get_current_lang(user_id))})


@with_auth
async def handle_words_remove(request, user_id):
    """POST {surah, ayah, position} - двойной тап/клик по строке уже
    В САМОМ списке "Мои слова" (не на странице чтения - см. модульный
    docstring core/mushaf_words.py, почему на странице чтения только add)."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "bad_json"}, status=400)
    key = _parse_word_key(body)
    if key is None:
        return web.json_response({"error": "bad_word"}, status=400)
    remove_starred_word(user_id, *key)
    return web.json_response({"words": list_starred_words(user_id, get_current_lang(user_id))})


# Полный диапазон страниц чтения (mushaf_data/page1.json..page604.json) -
# НЕ core.quran_pages.FIRST_PAGE/LAST_PAGE (те 2-221, только диапазон
# тренажёра муфрадата, см. модульный docstring quran_pages.py). Закладка
# страницы чтения (core/mushaf_words.py) - отдельная от тренажёрной,
# охватывает весь мусхаф.
_READING_FIRST_PAGE, _READING_LAST_PAGE = 1, 604


@with_auth
async def handle_bookmark_get(request, user_id):
    """GET - текущая закладка страницы чтения (кнопка "«" в #page-nav,
    30.08.2026). null, если студент ещё ни разу не сохранял."""
    return web.json_response({"page": get_reading_bookmark(user_id)})


@with_auth
async def handle_bookmark_set(request, user_id):
    """POST {page} - тап на 🔖 в #page-nav сохраняет текущую страницу как
    закладку (перезаписывает предыдущую, если была)."""
    try:
        body = await request.json()
        page = int(body["page"])
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        return web.json_response({"error": "bad_page"}, status=400)
    if not (_READING_FIRST_PAGE <= page <= _READING_LAST_PAGE):
        return web.json_response({"error": "bad_page"}, status=400)
    set_reading_bookmark(user_id, page)
    return web.json_response({"page": page})


@with_auth
async def handle_hifz_get(request, user_id):
    """GET - указатель режима заучивания 40+40: где студент сейчас.
    null, если он ещё ни разу не входил в режим (тогда фронтенд один раз
    спрашивает строчку)."""
    return web.json_response({"pointer": get_hifz_pointer(user_id)})


@with_auth
async def handle_hifz_set(request, user_id):
    """POST {page, line, stage} - студент выбрал строчку, перешёл на
    следующую или сменил этап. Строка - индекс ТЕКСТОВОЙ строки страницы
    (0..15: в мадани-мусхафе их 15, плюс запас), этап 1..3."""
    try:
        body = await request.json()
        page = int(body["page"])
        line = int(body["line"])
        stage = int(body["stage"])
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        return web.json_response({"error": "bad_pointer"}, status=400)
    if not (_READING_FIRST_PAGE <= page <= _READING_LAST_PAGE):
        return web.json_response({"error": "bad_page"}, status=400)
    if not (0 <= line <= 15) or stage not in (1, 2, 3):
        return web.json_response({"error": "bad_pointer"}, status=400)
    set_hifz_pointer(user_id, page, line, stage)
    return web.json_response({"pointer": {"page": page, "line": line, "stage": stage}})


@with_auth
async def handle_hifz_progress_get(request, user_id):
    """GET ?page=&stage=&half= - сколько повторов (0-80) уже накоплено по
    ТЕКУЩЕЙ единице этапа 2/3 (03.09.2026). У этапа 1 (строка) счётчика
    нет - там одна сдача и так закрывает единицу, спрашивать нечего."""
    try:
        page = int(request.query["page"])
        stage = int(request.query["stage"])
        half = int(request.query["half"])
    except (KeyError, ValueError, TypeError):
        return web.json_response({"error": "bad_pointer"}, status=400)
    if not (_READING_FIRST_PAGE <= page <= _READING_LAST_PAGE):
        return web.json_response({"error": "bad_page"}, status=400)
    if stage not in (2, 3) or half not in (0, 1):
        return web.json_response({"error": "bad_pointer"}, status=400)
    return web.json_response({
        "count": get_hifz_progress(user_id, page, stage, half),
        "target": HIFZ_PROGRESS_TARGET,
    })


@with_auth
async def handle_hifz_progress_add(request, user_id):
    """POST {page, stage, half, delta} - "сколько добавил сегодня" к
    единице этапа 2/3 (03.09.2026). Дельта, не абсолютное число - так
    нельзя случайно занизить уже сохранённый счёт. `closed` в ответе
    говорит фронтенду, дошло ли до 80 - только тогда указатель должен
    сдвинуться дальше, частичная сдача его не трогает."""
    try:
        body = await request.json()
        page = int(body["page"])
        stage = int(body["stage"])
        half = int(body["half"])
        delta = int(body["delta"])
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        return web.json_response({"error": "bad_pointer"}, status=400)
    if not (_READING_FIRST_PAGE <= page <= _READING_LAST_PAGE):
        return web.json_response({"error": "bad_page"}, status=400)
    if stage not in (2, 3) or half not in (0, 1) or not (1 <= delta <= HIFZ_PROGRESS_TARGET):
        return web.json_response({"error": "bad_pointer"}, status=400)
    count = add_hifz_progress(user_id, page, stage, half, delta)
    return web.json_response({
        "count": count, "target": HIFZ_PROGRESS_TARGET,
        "closed": count >= HIFZ_PROGRESS_TARGET,
    })


@with_auth
async def handle_hifz_submit(request, user_id):
    """POST multipart - сдача 40+40, записанная в приложении (02.09.2026).
    Поля: audio (запись), image (картинка прочитанной строчки, рисует сам
    фронтенд на canvas настоящим шрифтом V4 - на сервере такого рендера
    нет, там только пословный Scheherazade), page/line/stage - что читал.

    Размер режем на входе: mp3/opus-минута весит сотни килобайт, 20 МБ -
    это уже не сдача, а сбой записи или чужой файл."""
    try:
        reader = await request.multipart()
    except Exception:
        return web.json_response({"error": "bad_form"}, status=400)

    audio, image, fields = None, None, {}
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name in ("audio", "image"):
            data = await part.read(decode=False)
            if len(data) > HIFZ_MAX_UPLOAD_BYTES:
                return web.json_response({"error": "too_big"}, status=413)
            if part.name == "audio":
                audio = data
            else:
                image = data
        else:
            fields[part.name] = (await part.read(decode=False)).decode("utf-8", "replace")

    if not audio:
        return web.json_response({"error": "no_audio"}, status=400)
    try:
        page = int(fields["page"])
        line = int(fields["line"])
        stage = int(fields["stage"])
    except (KeyError, ValueError, TypeError):
        return web.json_response({"error": "bad_pointer"}, status=400)
    if not (_READING_FIRST_PAGE <= page <= _READING_LAST_PAGE):
        return web.json_response({"error": "bad_page"}, status=400)
    if not (0 <= line <= 15) or stage not in (1, 2, 3):
        return web.json_response({"error": "bad_pointer"}, status=400)
    try:
        page_lines = int(fields.get("lines", 15))
    except (ValueError, TypeError):
        page_lines = 15
    if not (1 <= page_lines <= 16):
        page_lines = 15

    result = await submit_hifz_recording(user_id, audio, image, page, line, stage, page_lines)
    return web.json_response(result, status=200 if result.get("ok") else 400)


@with_auth
async def handle_revision_credit(request, user_id):
    """POST - кнопка "🔁" в #topbar на странице чтения (30.08.2026).
    Подтверждение ("вы сделали повторение...?") уже показано на фронтенде
    ДО этого запроса - сюда приходит только финальное "да". Логика зачёта
    и сообщения в группу - в credit_revision_task (core/mufradat_bot.py),
    та же, что у обычной текстовой сдачи "повторение" в группе."""
    credited = await credit_revision_task(user_id)
    return web.json_response({"credited": credited})


# "Сейчас онлайн" на дашборде (30.08.2026) - в Mini App нет постоянного
# соединения (не WebSocket), поэтому "онлайн" приближённо = кто прислал
# отметку присутствия за последние ONLINE_WINDOW_SECONDS. Фронтенд шлёт
# heartbeat каждые ~20 сек, пока приложение открыто (см. mushaf_data/
# index.html). В памяти процесса, НЕ в БД - раздельно по мужскому/женскому
# боту само собой (свой процесс/порт на каждого, см. модульный docstring
# в wiki/mushaf_yassirapp.md), потеря счётчика при рестарте бота не
# страшна (не критичная метрика, просто набирается заново за минуту).
ONLINE_WINDOW_SECONDS = 60
_last_seen = {}  # user_id -> unix-время последнего heartbeat


def _online_count():
    cutoff = time.time() - ONLINE_WINDOW_SECONDS
    stale = [uid for uid, ts in _last_seen.items() if ts < cutoff]
    for uid in stale:
        del _last_seen[uid]
    return len(_last_seen)


@with_auth
async def handle_heartbeat(request, user_id):
    """POST - "я сейчас держу YassirApp открытым", шлётся с фронтенда
    периодически. Возвращает текущее число "онлайн" сразу же, отдельного
    GET не нужно."""
    _last_seen[user_id] = time.time()
    return web.json_response({"online": _online_count()})


def build_app():
    # client_max_size по умолчанию 1 МБ - голосовая сдача 40+40 (несколько
    # минут записи из браузера) в него не влезает, aiohttp обрывал бы её
    # до нашего обработчика. Свой предел проверяем уже в handle_hifz_submit.
    app = web.Application(client_max_size=HIFZ_MAX_UPLOAD_BYTES + 1024 * 1024)
    app.router.add_get("/api/muf/state", handle_state)
    app.router.add_post("/api/muf/page", handle_page)
    app.router.add_post("/api/muf/answer", handle_answer)
    app.router.add_get("/api/muf/lang", handle_lang_get)
    app.router.add_post("/api/muf/lang", handle_lang)
    app.router.add_post("/api/muf/end", handle_end)
    app.router.add_get("/api/muf/leaderboard", handle_leaderboard)
    app.router.add_get("/api/muf/words", handle_words_list)
    app.router.add_post("/api/muf/words/add", handle_words_add)
    app.router.add_post("/api/muf/words/remove", handle_words_remove)
    app.router.add_get("/api/muf/bookmark", handle_bookmark_get)
    app.router.add_post("/api/muf/bookmark", handle_bookmark_set)
    app.router.add_get("/api/muf/hifz", handle_hifz_get)
    app.router.add_post("/api/muf/hifz", handle_hifz_set)
    app.router.add_get("/api/muf/hifz/progress", handle_hifz_progress_get)
    app.router.add_post("/api/muf/hifz/progress", handle_hifz_progress_add)
    app.router.add_post("/api/muf/hifz/submit", handle_hifz_submit)
    app.router.add_post("/api/muf/revision", handle_revision_credit)
    app.router.add_post("/api/muf/heartbeat", handle_heartbeat)
    return app


async def run_server(port=8081):
    """Запускается как фоновая asyncio-задача из bot.py (тот же процесс,
    что и getUpdates-цикл - не отдельный сервис, чтобы не плодить второй
    systemd-юнит и не дублировать доступ к БД/токену). Слушает только
    127.0.0.1 - наружу смотрит nginx, проксирующий /api/muf/ (см.
    wiki/infrastructure.md после этой правки)."""
    app = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    log.info("mufradat API listening on 127.0.0.1:%d", port)
