"""Тренажёр муфрадата - генерация вопросов по загруженному пословному
словарю (core/sampler.py:save_mufradat_word, данные в sources/hadiths.db).

Фильтрация "плохих" слов - НЕ на этапе загрузки (там храним всё честно),
а здесь, на этапе генерации вопроса (см. project_mufradat_data_source_licensing
в памяти, разбор advisor 17.08.2026):
  - слова с вводными пояснениями в переводе, типа "(но) не (путём)" -
    не годятся ни целью вопроса, ни дистрактором: угадываются по виду
    текста, а не по знанию слова, и порождают вопрос с меньшим реальным
    числом вариантов, чем показано (разбор advisor 17.08.2026, второй заход).
  - дубли перевода (два разных арабских слова с одинаковым русским
    переводом, напр. "Путём" у ٱلصِّرَٰطَ И صِرَٰطَ) - дистрактор не должен
    совпадать с правильным ответом по нормализованному переводу.
  - слова, чей перевод повторяется в диапазоне 3+ раза (частицы вроде
    "не"/"в"/"из", но и контекстно устойчивые слова вроде "Аллах") - не
    годятся ЦЕЛЬЮ вопроса: прогресс привязан к конкретной строке
    (mufradat_words.id), а не к арабскому слову (см. ниже, почему), и у
    таких слов десятки независимых строк с одним и тем же переводом -
    "мастерство" по каждой строке отдельно никогда не сходится в одно
    целое. Дистрактором остаются (разбор advisor 17.08.2026, третий заход).
"""
import math
import random
import re
import sqlite3
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from core.sampler import HADITHS_DB
from core.quran_pages import resolve_page, last_ayah_on_page, SURAHS

_TZ = ZoneInfo("Asia/Bishkek")  # created_at в score_events хранится в UTC,
# а date - в этом поясе; здесь той же путаницы не будет, т.к. столбца даты
# в UTC вообще нет (см. project_score_events_timezone_gotcha в памяти).

_PROGRESS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS mufradat_progress(
        user_id TEXT NOT NULL,
        word_id INTEGER NOT NULL,
        correct_streak INTEGER NOT NULL DEFAULT 0,
        wrong_count INTEGER NOT NULL DEFAULT 0,
        days_correct INTEGER NOT NULL DEFAULT 0,
        last_correct_date TEXT,
        PRIMARY KEY (user_id, word_id)
    )
"""


def _ensure_progress_schema(conn):
    """CREATE TABLE + миграция ADD COLUMN correct_count (19.08.2026, для
    Wilson-рейтинга по точности - см. get_leaderboard). correct_count -
    НАКОПИТЕЛЬНЫЙ счётчик верных ответов, никогда не уменьшается и не
    ограничен потолком, в отличие от correct_streak (тот падает при ошибке,
    см. record_answer) - без него точность (correct/(correct+wrong)) по
    всей истории студента посчитать было нечем, только wrong_count был
    накопительным.

    Проверяем PRAGMA table_info ДО попытки ALTER (не try/except на каждый
    вызов) - эта функция дёргается на каждый тап карточки (get_progress_map,
    record_answer), try/except ловил бы исключение и писал попытку схемы в
    WAL при каждом тапе (поймал advisor 19.08.2026). Тот же трёхместный
    паттерн, что и у wrong_count (SELECT/increment/INSERT) - days_correct в
    этой же таблице молча обнуляется на каждый ответ уже давно именно
    потому, что не входит в список полей INSERT OR REPLACE в record_answer
    (найдено advisor как предупреждение о такой же ловушке для
    correct_count) - оставлено как есть, отдельное решение, не часть этой
    правки."""
    conn.execute(_PROGRESS_SCHEMA)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(mufradat_progress)")}
    if "correct_count" not in cols:
        conn.execute("ALTER TABLE mufradat_progress ADD COLUMN correct_count INTEGER NOT NULL DEFAULT 0")


_PAGE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS mufradat_page(
        user_id TEXT PRIMARY KEY,
        page_number INTEGER NOT NULL,
        start_ayah INTEGER NOT NULL,
        end_ayah INTEGER NOT NULL
    )
"""

# "Выучено" = 4 верных ответа (не обязательно подряд по времени - см.
# record_answer, ошибка НЕ обнуляет счётчик, только верные ответы двигают
# его вперёд, решение пользователя 17.08.2026, третий заход). Было 7,
# снижено до 4 решением пользователя 18.08.2026 - "пока 7 пройдут, время
# много понадобится". Естественный разброс по времени берётся не из
# календарных дней, а из самой механики выбора вопроса - слово с большим
# числом верных ответов получает меньший вес (word_weight) и реже
# выпадает, а слов на странице много, так что "домотать" одно и то же
# слово до MASTERY_STREAK за один присест почти невозможно.
MASTERY_STREAK = 4

# Даже "выученное" (correct_streak >= MASTERY_STREAK) слово освобождает
# место в пуле вопросов на RECHECK_AFTER_DAYS дней ("убирается" - не
# спрашивается вообще, см. pick_question_word), а не просто становится
# редким - без повторной проверки долговременная память не гарантирована
# (та же логика, что у Anki: "зрелая" карточка всё равно ревьюится, просто
# редко). Когда срок истёк - слово ОДИН раз возвращается в пул (вес 1.0,
# см. word_weight): верно - снова "убирается" на 60 дней (last_correct_date
# обновляется), неверно - счётчик снижается на 1 и слово уходит в общий
# режим проверки наравне с остальными (решение пользователя 17.08.2026,
# четвёртый заход - единственный случай, где ошибка ЧТО-ТО снижает,
# т.к. это настоящая проверка забывания, не случайная опечатка).
RECHECK_AFTER_DAYS = 60

_SCAFFOLD_RE = re.compile(r"[()]")
_HAS_LETTER_RE = re.compile(r"[a-zа-яё]", re.IGNORECASE)


def _normalize_gloss(text):
    return re.sub(r"[,.!;:\s]+$", "", text.strip().lower())


def _is_scaffold(translation):
    return bool(_SCAFFOLD_RE.search(translation))


def _is_junk(translation):
    """Перевод без единой буквы (напр. "*" - метка сноски в исходнике,
    17.08.2026, 116 из 6103 строк) - не перевод вообще, ни целью вопроса,
    ни дистрактором быть не может."""
    return not _HAS_LETTER_RE.search(translation)


def get_words_in_range(surah_number, start_ayah, end_ayah):
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, surah_number, ayah_number, position, arabic_text, translation "
            "FROM mufradat_words WHERE surah_number=? AND ayah_number BETWEEN ? AND ? "
            "ORDER BY ayah_number, position",
            (surah_number, start_ayah, end_ayah)
        ).fetchall()
    return [dict(r) for r in rows if not _is_junk(r["translation"])]


def word_weight(progress_row):
    """progress_row - словарь с correct_streak/wrong_count/last_correct_date
    или None (слово ещё не спрашивали). Новое слово получает вес как у
    слова с одной верной серией подряд - не перегружаем вопросами
    непройденные слова, но и не игнорируем их (согласовано с пользователем
    17.08.2026).

    Вызывается только для слов, прошедших фильтр в pick_question_word -
    т.е. либо не "выученных" совсем, либо "выученных", но просроченных
    (см. RECHECK_AFTER_DAYS) - те получают вес 1.0 (разовая перепроверка,
    не выше обычного нового слова).

    Условие - ПРОСТО _is_stale, без is_mastered: слово, ЧАСТИЧНО
    продемотированное после проваленной перепроверки (см. record_answer -
    streak снижается, но last_correct_date остаётся старым), тоже должно
    получать полный приоритет, а не средний по formula 1/(1+streak) -
    иначе частично сохранённый прогресс конфликтовал бы с "слабое слово в
    приоритете" (advisor 17.08.2026, шестой заход - поймал, что мой
    предыдущий фикс "streak=0" был избыточным overcorrection именно
    из-за этого условия)."""
    if not progress_row:
        return 1.0 / (1 + 1)
    if _is_stale(progress_row):
        return 1.0
    return 1.0 / (1 + progress_row["correct_streak"])


def _repeated_glosses(words, min_count=3):
    """Переводы, встречающиеся в диапазоне min_count+ раз - частицы и
    контекстно устойчивые слова, см. модульный docstring."""
    counts = Counter(
        _normalize_gloss(w["translation"]) for w in words if not _is_scaffold(w["translation"])
    )
    return {norm for norm, cnt in counts.items() if cnt >= min_count}


def _scaled_repeat_threshold(words):
    """Порог "часто повторяющийся перевод" (3 на одну страницу, см.
    модульный docstring) НЕ масштабируется с диапазоном напрямую -
    измерено эмпирически (advisor 17.08.2026, седьмой заход, после
    перехода на пул "вся закладка 2..N" вместо одной страницы): при
    фиксированном 3 доля годных целей падает с 83% (1 страница) до 49%
    (2-49 страницы) - настоящие содержательные слова, случайно встретившиеся
    3+ раза в большой выборке, начинают исключаться наравне с частицами.

    ПЕРЕКАЛИБРОВАНО 18.08.2026 при расширении на суры 3-10 (7 длинных сур):
    прежняя формула "3 + 1.5×(страниц-1)" росла ЛИНЕЙНО с числом страниц,
    а реальная частота частиц растёт линейно с числом СЛОВ в пуле, не
    страниц (на страницах разное число слов - от ~35 до ~140) - на полном
    диапазоне (стр. 221, 27609 слов) формула давала порог 332, при этом
    "в" (216 раз) и "из" (281 раз) уже НЕ попадали под исключение -
    доля "годных целей" показывала обманчиво хорошие 95.5% именно потому
    что фильтр перестал фильтровать (advisor поймал риск заранее, до
    прогона реальных данных). Проверено эмпирически на 5 разных глубинах
    пула (1042/5987/13195/18891/27609 слов, стр. 10/49/106/150/221) -
    частицы "не"/"в"/"из"/"Аллах" стабильно держат долю ~0.5-0.8% от
    РАЗМЕРА ПУЛА (не страниц), 0.6% исключает все известные частицы на
    всех проверенных глубинах и даёт долю годных целей ~83% (на самом
    большом пуле - меньше исходных 85-91%, но реальный сдвиг небольшой
    и предпочтительнее сломанного фильтра). max(3, ...) сохраняет
    поведение на маленьких пулах (1 страница, ~35 слов) - 0.6% от 35
    округляется в 0, порог остаётся 3, как и было изначально."""
    n = max(1, len(words))
    return max(3, round(n * 0.006))


def pick_question_word(words, progress_by_id, min_repeat_exclude=None):
    """words - результат get_words_in_range. Целью вопроса не может быть
    слово с пояснением в скобках (не проверяет знание слова, угадывается
    по форме ответа), слово с часто повторяющимся переводом (см. модульный
    docstring и _scaled_repeat_threshold), а также "выученное" слово,
    которое ещё не отдохнуло положенные RECHECK_AFTER_DAYS дней - убрано
    из пула совсем, не просто с низким весом (решение пользователя
    17.08.2026, четвёртый заход)."""
    if min_repeat_exclude is None:
        min_repeat_exclude = _scaled_repeat_threshold(words)
    repeated = _repeated_glosses(words, min_repeat_exclude)
    candidates = []
    for w in words:
        if _is_scaffold(w["translation"]) or _normalize_gloss(w["translation"]) in repeated:
            continue
        progress = progress_by_id.get(w["id"])
        if is_mastered(progress) and not _is_stale(progress):
            continue
        candidates.append(w)
    if not candidates:
        return None
    weights = [word_weight(progress_by_id.get(w["id"])) for w in candidates]
    return random.choices(candidates, weights=weights, k=1)[0]


def generate_question(words, progress_by_id, n_options=8):
    """Возвращает {word, options} или None, если в диапазоне недостаточно
    слов для вопроса. options - список переводов (включая верный),
    перемешанный."""
    target = pick_question_word(words, progress_by_id)
    if target is None:
        return None

    target_norm = _normalize_gloss(target["translation"])
    seen_norms = {target_norm}
    distractor_pool = []
    for w in random.sample(words, len(words)):
        if w["id"] == target["id"] or _is_scaffold(w["translation"]):
            continue
        norm = _normalize_gloss(w["translation"])
        if norm in seen_norms:
            continue
        seen_norms.add(norm)
        distractor_pool.append(w)
    if len(distractor_pool) < n_options - 1:
        return None

    distractors = distractor_pool[:n_options - 1]
    options = [target["translation"]] + [d["translation"] for d in distractors]
    random.shuffle(options)

    return {"word": target, "options": options}


def _today():
    return datetime.now(_TZ).strftime("%Y-%m-%d")


def _days_since(date_str):
    if not date_str:
        return None
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return (datetime.now(_TZ).date() - d).days


def _is_stale(progress_row):
    days_ago = _days_since(progress_row["last_correct_date"])
    return days_ago is not None and days_ago >= RECHECK_AFTER_DAYS


def get_progress_map(user_id, word_ids):
    if not word_ids:
        return {}
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_progress_schema(conn)
        placeholders = ",".join("?" * len(word_ids))
        rows = conn.execute(
            f"SELECT * FROM mufradat_progress WHERE user_id=? AND word_id IN ({placeholders})",
            (user_id, *word_ids)
        ).fetchall()
    return {r["word_id"]: dict(r) for r in rows}


def record_answer(user_id, word_id, correct):
    """Обновляет прогресс по одной строке mufradat_words. Симметрично:
    верный ответ двигает correct_streak на +1 (потолок MASTERY_STREAK),
    неверный - на -1 (пол 0), для ЛЮБОГО слова без исключений (решение
    пользователя 18.08.2026 - иначе балл только рос и не отражал реально
    забытые слова; отменяет более раннее решение 17.08.2026 "ошибка не
    снижает вес", включая специальный штраф -2 за провал перепроверки
    просроченного "выученного" слова - тот особый случай, введённый
    именно потому что обычная ошибка раньше ничего не снижала, теперь
    покрывается общим правилом, отдельная ветка стала не нужна).
    correct_streak никогда не уходит в минус (max(0, ...)) - поэтому и
    word_stimulus_credit (min(1.0, streak/MASTERY_STREAK)), и весь
    compute_overall_score (сумма неотрицательных долей) тоже не уходят
    в минус.

    last_correct_date выставляется ТОЛЬКО на верный ответ - на неверном
    остаётся прежним, поэтому просроченное "выученное" слово (see
    RECHECK_AFTER_DAYS) сохраняет вес 1.0 в word_weight (ветка _is_stale)
    до первого же верного ответа после провала, даже если провалило
    несколько перепроверок подряд.

    correct_count (19.08.2026) растёт вместе с correct_streak на верный
    ответ, но НИКОГДА не падает на ошибке (в отличие от correct_streak) -
    это единственный настоящий накопительный счётчик "сколько раз вообще
    ответил верно" по слову, нужен для Wilson-точности в get_leaderboard."""
    today = _today()
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_progress_schema(conn)
        row = conn.execute(
            "SELECT correct_streak, wrong_count, correct_count, last_correct_date "
            "FROM mufradat_progress WHERE user_id=? AND word_id=?",
            (user_id, word_id)
        ).fetchone()
        streak, wrong, right, last_date = tuple(row) if row else (0, 0, 0, None)
        if correct:
            streak = min(MASTERY_STREAK, streak + 1)
            right += 1
            last_date = today
        else:
            wrong += 1
            streak = max(0, streak - 1)
        conn.execute(
            "INSERT OR REPLACE INTO mufradat_progress "
            "(user_id, word_id, correct_streak, wrong_count, correct_count, last_correct_date) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, word_id, streak, wrong, right, last_date)
        )


def is_mastered(progress_row):
    return bool(progress_row) and progress_row["correct_streak"] >= MASTERY_STREAK


def word_stimulus_credit(progress_row):
    """Доля пути слова к полному вкладу в "Общий вес" - 0..1, растёт с
    каждым верным ответом. Тот же correct_streak, что и is_mastered -
    при достижении MASTERY_STREAK обе метрики совпадают (не два разных
    числа, как было в первой версии этой правки, а одно - решение
    пользователя 17.08.2026, третий заход: "такого в моей логике не было")."""
    if not progress_row:
        return 0.0
    return min(1.0, progress_row["correct_streak"] / MASTERY_STREAK)


def set_current_page(user_id, page_number):
    """Пишет ЗАКЛАДКУ студента - "дошёл до этой страницы" (не "добавь
    именно эту одну страницу"). ЯВЛЯЕТСЯ источником истины для пула
    тренажёра - get_words_for_bookmark берёт слова со ВСЕХ страниц (и
    сур, с 18.08.2026 - расширение за пределы Бакары) от начала до этой
    закладки разом (решение пользователя 17.08.2026, пятый заход:
    "рандомно должно идти... без ручного добавления каждой страницы").
    start_ayah/end_ayah в схеме таблицы - МЁРТВЫЕ колонки (пишутся, но
    нигде не читаются обратно - было так и до этой правки, просто раньше
    вызывающий код честно передавал их, создавая иллюзию, что они нужны).
    Пишем 0 - реальные диапазоны для пула всегда пересчитываются заново
    через core.quran_pages при каждом обращении, не хранятся здесь."""
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_PAGE_SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO mufradat_page (user_id, page_number, start_ayah, end_ayah) VALUES (?,?,0,0)",
            (user_id, page_number)
        )


def get_current_page(user_id):
    """Текущая закладка студента (номер страницы) или None, если ещё не
    установлена (студент ни разу не вводил страницу)."""
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_PAGE_SCHEMA)
        row = conn.execute(
            "SELECT page_number FROM mufradat_page WHERE user_id=?", (user_id,)
        ).fetchone()
    return row[0] if row else None


def get_words_up_to_page(page_number):
    """Пул слов от начала диапазона (FIRST_PAGE, сура 2) до заданной
    страницы РАЗОМ, вперемешку - решение пользователя 17.08.2026, пятый
    заход. С 18.08.2026 диапазон охватывает несколько сур (2-10, Бакара
    по Юнус - "семь длинных сур", решение пользователя), не только
    Бакару, поэтому простой BETWEEN по ayah_number внутри одной суры
    больше не работает (номера аятов начинаются заново с 1 в каждой
    суре) - берём ВСЕ слова каждой суры ПОЛНОСТЬЮ для сур строго до
    суры закладки, и только до нужного аята для суры самой закладки."""
    last = last_ayah_on_page(page_number)
    if last is None:
        return []
    bookmark_surah, bookmark_ayah = last

    words = []
    for surah in SURAHS:
        if surah < bookmark_surah:
            words.extend(get_words_in_range(surah, 1, 9999))
        elif surah == bookmark_surah:
            words.extend(get_words_in_range(surah, 1, bookmark_ayah))
            break
        else:
            break
    return words


def get_words_for_bookmark(user_id):
    """Пул слов тренажёра для ТЕКУЩЕЙ закладки студента (get_words_up_to_page,
    см. там) - не только последняя введённая страница, а всё от начала
    диапазона (решение пользователя 17.08.2026, пятый заход)."""
    page_number = get_current_page(user_id)
    if not page_number:
        return []
    return get_words_up_to_page(page_number)


def compute_overall_score(user_id, words=None, progress=None):
    """Общий вес студента среди ВСЕХ слов на закладке (get_words_for_bookmark,
    2..N, ТОТ ЖЕ пул, что и у тренажёра, не только реально тронутые
    страницы). Возвращает None, если закладка ещё не установлена. Личное
    отображаемое число на карточке/в статистике - НЕ критерий ранжирования
    в /muftop (там с 19.08.2026 Wilson-точность по всей истории, см.
    get_leaderboard), поэтому знаменатель "закладка" тут не проблема.

    Деноминатор - именно закладка (не число реально тронутых страниц) -
    иначе знаменатель рос НЕПРЕДСКАЗУЕМО посреди сеанса (каждый тап на
    новую страницу пула резко увеличивал total), из-за чего score10 мог
    УПАСТЬ после верного ответа - тот же "вес не растёт" эффект, который
    вся эта правка должна была устранить (баг найден advisor 17.08.2026,
    седьмой заход, до деплоя).

    "mastered"/"total" и "score10" - одна и та же метрика (correct_streak),
    просто по-разному агрегированная: "mastered" - целое число слов,
    достигших MASTERY_STREAK, "score10" - плавная доля пути к этому же
    порогу по ВСЕМ словам (word_stimulus_credit), двигается с каждым
    верным ответом, даже в первый день (решение пользователя 17.08.2026).

    words/progress - опционально, если вызывающий код уже их получил -
    не дублируем те же 2 запроса к БД (advisor, пятый заход)."""
    if words is None:
        words = get_words_for_bookmark(user_id)
    if not words:
        return None
    if progress is None:
        progress = get_progress_map(user_id, [w["id"] for w in words])

    word_ids = [w["id"] for w in words]
    mastered = sum(1 for wid in word_ids if is_mastered(progress.get(wid)))
    stimulus_sum = sum(word_stimulus_credit(progress.get(wid)) for wid in word_ids)
    total = len(word_ids)
    return {
        "total": total, "mastered": mastered, "remaining": total - mastered,
        "score10": round(10 * stimulus_sum / total, 2),
    }


def compute_page_score(user_id, page_number):
    """Вес ОДНОЙ страницы (не всей закладки, как compute_overall_score) -
    доля выученных слов именно на ней. Сейчас не используется в самом
    тренажёре (слова вперемешку со всей закладки, см.
    get_words_for_bookmark) - оставлен для будущего экрана цветовой шкалы
    по страницам (project_mufradat_trainer_engine, "не начато").

    entries - список (surah, start_ayah, end_ayah) от resolve_page, обычно
    один элемент, два - на единственной переходной странице (см.
    core/quran_pages.py) - суммируем слова по всем сурам страницы."""
    entries = resolve_page(page_number)
    if entries is None:
        return None
    words = []
    for surah, start_ayah, end_ayah in entries:
        words.extend(get_words_in_range(surah, start_ayah, end_ayah))
    if not words:
        return None
    progress = get_progress_map(user_id, [w["id"] for w in words])
    mastered = sum(1 for w in words if is_mastered(progress.get(w["id"])))
    total = len(words)
    return {"total": total, "mastered": mastered, "score10": round(10 * mastered / total, 2)}


# Wilson-рейтинг (19.08.2026) - заменил полки по глубине страниц. Прошлая
# метрика (mastered/score10 внутри полки по max тренированной странице)
# сломалась после расширения пула на 7 сур: знаменатель (весь пул закладки)
# вырос до ~28000 слов, доля стала неинформативной у всех ("вес слишком
# малые, есть у которых 0", пользователь 19.08.2026). Пользователь прямо
# попросил формулу из двух факторов - точность (верно/открыто) и стимул
# открывать больше карточек, не наказывая за возросший шанс ошибиться на
# объёме - консультация advisor 19.08.2026 указала на Wilson lower bound
# (тот же алгоритм, что использует Reddit для ранжирования комментариев по
# рейтингу) - см. _wilson_lower_bound.
_WILSON_Z = 1.96  # 95%-доверительный интервал, стандартный выбор для этого
# алгоритма - не тюнинг-константа, трогать не нужно.


def _wilson_lower_bound(correct, n):
    """Нижняя граница 95%-доверительного интервала для доли верных ответов
    (p = correct/n) - отвечает на вопрос "какая точность НАИХУДШАЯ, ещё
    согласующаяся с этим объёмом данных". Поэтому 190 верных из 200 обгоняет
    1 верный из 1: у первого высокая УВЕРЕННОСТЬ в оценке точности, у
    второго - почти никакой, хотя p=1.0 у обоих быть не может (сравнили на
    реальных данных студентов, SSH-превью на проде 19.08.2026 - Нурсултан,
    271 карточка / 39 ошибок, wilson~0.833, держится выше Ильяса, 15
    карточек / 1 ошибка, wilson~0.717, несмотря на более высокий % у
    второго - ровно то, что просил пользователь).

    Стимул от объёма ПЛАВНО ВЫДЫХАЕТСЯ после нескольких сотен карточек
    (предупредил advisor заранее) - при p=0.9 разница между n=200 и n=2000
    почти не заметна, чистый Wilson не даёт бесконечного стимула качать
    объём. Первая попытка (тай-брейк по attempted при точном совпадении
    Wilson) не сработала на реальных данных - Wilson-значения у разных
    студентов почти никогда не совпадают до 4 знака, тай-брейк не включался
    ни разу, кроме пары студентов с абсолютно одинаковыми correct/wrong
    (проверено на живых данных 19.08.2026, после прямого вопроса
    пользователя "у них то меньше слов для заучивания" - Бехзод с 46
    карточками (93.9%) обгонял Нурсултана с 271 карточкой (87.4%), хотя оба
    примерно на одной глубине страниц - не проблема глубины, проблема веса
    объёма в самой формуле). См. get_leaderboard для итоговой формулы
    сортировки (wilson * log10(1+attempted))."""
    if n == 0:
        return 0.0
    p = correct / n
    denom = 1 + _WILSON_Z ** 2 / n
    center = p + _WILSON_Z ** 2 / (2 * n)
    margin = _WILSON_Z * math.sqrt((p * (1 - p) + _WILSON_Z ** 2 / (4 * n)) / n)
    return (center - margin) / denom


def _accuracy_totals():
    """user_id -> {correct, wrong, n, attempted} - суммарно по ВСЕМ словам,
    что студент когда-либо открывал за всю историю (не только текущая
    закладка - строка в mufradat_progress появляется один раз на слово и
    остаётся навсегда, даже если закладка потом сдвинулась дальше).
    correct/wrong - SUM(correct_count)/SUM(wrong_count), оба честно
    накопительные (в отличие от correct_streak, который падает при ошибке).
    attempted - число РАЗНЫХ слов (не сумма попыток), нужен как тай-брейк
    при равном Wilson-счёте (решение пользователя 19.08.2026)."""
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_progress_schema(conn)
        rows = conn.execute(
            "SELECT user_id, SUM(correct_count), SUM(wrong_count), COUNT(*) "
            "FROM mufradat_progress GROUP BY user_id"
        ).fetchall()
    return {
        uid: {"correct": c or 0, "wrong": w or 0, "n": (c or 0) + (w or 0), "attempted": n}
        for uid, c, w, n in rows
    }


def get_leaderboard():
    """Единый общий список (user_id, score_dict), НЕ полки по глубине
    страниц (было так до 19.08.2026) - Wilson-точность сравнима на любой
    глубине пула напрямую (в отличие от score10/mastered, которые зависели
    от размера знаменателя закладки), деление на полки только прятало бы
    студентов на ранних страницах от тех, кто прошёл дальше.

    Сортировочный ключ - wilson * log10(1+attempted), НЕ чистый wilson
    (была первая версия 19.08.2026, тай-брейк по attempted при точном
    совпадении Wilson - см. docstring _wilson_lower_bound, почему не
    сработало на практике). log10(1+attempted) даёт объёму ПОСТОЯННЫЙ, но
    сублинейный вес - не позволяет маленькому объёму с чуть более высокой
    точностью обгонять большой объём (Нурсултан 271/87.4% поднимается
    выше Бехзода 46/93.9%, проверено на живых данных 19.08.2026), но и не
    даёт бесконечно растущему объёму задавить точность (log, не линейно).
    Итоговое число - НЕ вероятность, только внутренний ключ сортировки, не
    показывается студенту (на экране - accuracy% и n, см.
    core/mufradat_bot.py:_render_leaderboard_text).

    score_dict: wilson (промежуточный, для sort_key), accuracy (%, для
    показа), correct/wrong/n (сырые числа), attempted."""
    totals = _accuracy_totals()
    entries = []
    for uid, t in totals.items():
        wilson = _wilson_lower_bound(t["correct"], t["n"])
        accuracy = round(100 * t["correct"] / t["n"], 1) if t["n"] else 0.0
        sort_key = wilson * math.log10(1 + t["attempted"])
        entries.append((uid, {
            "wilson": wilson, "accuracy": accuracy,
            "correct": t["correct"], "wrong": t["wrong"], "n": t["n"],
            "attempted": t["attempted"], "_sort_key": sort_key,
        }))
    entries.sort(key=lambda item: -item[1]["_sort_key"])
    return entries


_DAILY_ANSWERED_SCHEMA = """
    CREATE TABLE IF NOT EXISTS mufradat_daily_answered_words(
        user_id TEXT NOT NULL,
        date TEXT NOT NULL,
        word_id INTEGER NOT NULL,
        PRIMARY KEY (user_id, date, word_id)
    )
"""

# Столько РАЗНЫХ слов за день - засчитывается как сдача задания "t"
# ("Слова (или Перевод)", core/handlers.py) - решение пользователя
# 17.08.2026. Разных, не любых ответов - иначе можно закрыть задание,
# тапая по одному и тому же лёгкому слову. Было 20, снижено до 15 в тот
# же день, возвращено обратно к 20 решением пользователя 18.08.2026 -
# 15 проходилось слишком быстро.
DAILY_WORDS_FOR_TASK_CREDIT = 20


def record_daily_answered_word(user_id, word_id):
    """Отмечает, что студент СЕГОДНЯ отвечал на это слово (не важно,
    верно или нет - "поработал", не "выучил"). Возвращает число РАЗНЫХ
    слов за сегодня после этой записи."""
    today = _today()
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_DAILY_ANSWERED_SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO mufradat_daily_answered_words (user_id, date, word_id) VALUES (?,?,?)",
            (user_id, today, word_id)
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM mufradat_daily_answered_words WHERE user_id=? AND date=?",
            (user_id, today)
        ).fetchone()[0]
    return count
