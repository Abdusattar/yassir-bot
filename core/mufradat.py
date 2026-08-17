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
import random
import re
import sqlite3
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from core.sampler import HADITHS_DB
from core.quran_pages import resolve_page, page_for_ayah, BAQARA_SURAH, BAQARA_FIRST_PAGE

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

_PAGE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS mufradat_page(
        user_id TEXT PRIMARY KEY,
        page_number INTEGER NOT NULL,
        start_ayah INTEGER NOT NULL,
        end_ayah INTEGER NOT NULL
    )
"""

# Страницы, которые студент РЕАЛЬНО тренировал (хотя бы раз ответил) -
# отдельно от mufradat_page (там только ТЕКУЩАЯ страница, одна строка,
# перезаписывается). Общий вес считается по объединению этих страниц, а
# не по "текущей" или "до текущей" - иначе рейтинг ломается в обе стороны:
# студент, который прыгнул сразу на стр.30, получил бы в знаменатель ~4000
# слов, которые никогда не видел, а переписав номер на маленький - искусственно
# поднял бы вес. Так вес растёт только от реальной работы (advisor 17.08.2026).
_TRAINED_PAGES_SCHEMA = """
    CREATE TABLE IF NOT EXISTS mufradat_trained_pages(
        user_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        PRIMARY KEY (user_id, page_number)
    )
"""

# "Выучено" = 7 верных ответов (не обязательно подряд по времени - см.
# record_answer, ошибка НЕ обнуляет счётчик, только верные ответы двигают
# его вперёд, решение пользователя 17.08.2026, третий заход). Естественный
# разброс по времени берётся не из календарных дней, а из самой механики
# выбора вопроса - слово с большим числом верных ответов получает меньший
# вес (word_weight) и реже выпадает, а слов на странице много, так что
# "домотать" одно и то же слово до 7 за один присест почти невозможно.
MASTERY_STREAK = 7

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
    Формула 3 + 1.5×(страниц-1) держит долю в районе 85-91% на любом
    диапазоне (проверено на страницах 1, 13, 24, 48)."""
    pages = {page_for_ayah(w["ayah_number"]) for w in words}
    n = max(1, len(pages))
    return max(3, round(3 + 1.5 * (n - 1)))


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
        conn.execute(_PROGRESS_SCHEMA)
        placeholders = ",".join("?" * len(word_ids))
        rows = conn.execute(
            f"SELECT * FROM mufradat_progress WHERE user_id=? AND word_id IN ({placeholders})",
            (user_id, *word_ids)
        ).fetchall()
    return {r["word_id"]: dict(r) for r in rows}


def record_answer(user_id, word_id, correct):
    """Обновляет прогресс по одной строке mufradat_words. Обычная ошибка
    НИЧЕГО не снижает (только считается в wrong_count для статистики) -
    вес растёт исключительно от верных ответов, по чуть-чуть (решение
    пользователя 17.08.2026, третий заход - "неверные не должны снижать
    вес, только верные добавляют").

    ЕДИНСТВЕННОЕ исключение - провал разовой перепроверки просроченного
    "выученного" слова (см. RECHECK_AFTER_DAYS, pick_question_word): это
    не случайная опечатка, а прямое доказательство забывания, поэтому
    correct_streak снижается на 4 (7→3, нужно ещё 4 верных для повторного
    "выучено", не все 7 заново - полный сброс в 0 был избыточным
    наказанием, замечание пользователя 17.08.2026, шестой заход).
    last_correct_date НЕ трогается (остаётся старым) - поэтому слово
    сохраняет вес 1.0 в word_weight (см. там, ветка _is_stale) до первого
    же верного ответа - частичный прогресс сохранён И приоритет
    максимальный одновременно, никакого противоречия (advisor, тот же
    заход)."""
    today = _today()
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(_PROGRESS_SCHEMA)
        row = conn.execute(
            "SELECT correct_streak, wrong_count, last_correct_date "
            "FROM mufradat_progress WHERE user_id=? AND word_id=?",
            (user_id, word_id)
        ).fetchone()
        streak, wrong, last_date = tuple(row) if row else (0, 0, None)
        if correct:
            streak = min(MASTERY_STREAK, streak + 1)
            last_date = today
        else:
            was_due_recheck = row and is_mastered(row) and _is_stale(row)
            wrong += 1
            if was_due_recheck:
                streak = max(0, streak - 4)
        conn.execute(
            "INSERT OR REPLACE INTO mufradat_progress "
            "(user_id, word_id, correct_streak, wrong_count, last_correct_date) "
            "VALUES (?,?,?,?,?)",
            (user_id, word_id, streak, wrong, last_date)
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


def set_current_page(user_id, page_number, start_ayah, end_ayah):
    """Пишет ЗАКЛАДКУ студента - "дошёл до этой страницы" (не "добавь
    именно эту одну страницу"). ЯВЛЯЕТСЯ источником истины для пула
    тренажёра - get_words_for_bookmark берёт слова со ВСЕХ страниц от
    начала суры до этой закладки разом (решение пользователя 17.08.2026,
    пятый заход: "рандомно должно идти... без ручного добавления каждой
    страницы"). Раньше эта таблица была почти мёртвой (пул строился по
    mufradat_trained_pages) - теперь наоборот, mufradat_trained_pages
    осталась только как ДОКАЗАТЕЛЬСТВО глубины для рейтинга (см.
    get_leaderboard), а не источник пула."""
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_PAGE_SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO mufradat_page (user_id, page_number, start_ayah, end_ayah) VALUES (?,?,?,?)",
            (user_id, page_number, start_ayah, end_ayah)
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


def get_words_for_bookmark(user_id):
    """Пул слов тренажёра - ВСЕ страницы от начала суры (BAQARA_FIRST_PAGE)
    до закладки студента разом, вперемешку (не только последняя введённая
    страница) - решение пользователя 17.08.2026, пятый заход. Страницы не
    разрывают аяты (проверено в core/quran_pages.py), поэтому диапазон
    2..N - это просто один непрерывный отрезок аятов, не нужно объединять
    по одной странице за раз."""
    page_number = get_current_page(user_id)
    if not page_number:
        return []
    start_ayah = resolve_page(BAQARA_FIRST_PAGE)[0]
    end_ayah = resolve_page(page_number)[1]
    return get_words_in_range(BAQARA_SURAH, start_ayah, end_ayah)


def mark_page_trained(user_id, page_number):
    """Вызывается при КАЖДОМ ответе (не при открытии карточки). Вызывающий
    код (core/mufradat_bot.py) обязан передавать ЗАКЛАДКУ студента
    (get_current_page), НЕ страницу конкретного заданного слова - вопросы
    берутся равномерно из всего диапазона 2..закладка, поэтому страница
    случайного слова почти всегда НИЖЕ закладки (шанс совпасть ~1/N) -
    если бы отмечали её, MAX(page_number) в mufradat_trained_pages (полка
    рейтинга, см. get_leaderboard) годами отставал бы от реальной глубины
    студента (баг найден advisor 17.08.2026, восьмой заход, до деплоя).

    НЕ источник пула тренажёра (см. get_words_for_bookmark) - только
    доказательство глубины для полок рейтинга: "дошёл до этой страницы
    И хотя бы раз ответил" - подделать нельзя не отвечая (защита от
    "вписал 49 и сразу попал в верхнюю полку", advisor, седьмой заход)."""
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_TRAINED_PAGES_SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO mufradat_trained_pages (user_id, page_number) VALUES (?,?)",
            (user_id, page_number)
        )


def compute_overall_score(user_id, words=None, progress=None):
    """Общий вес студента среди ВСЕХ слов на закладке (get_words_for_bookmark,
    2..N, ТОТ ЖЕ пул, что и у тренажёра, не только реально тронутые
    страницы). Возвращает None, если закладка ещё не установлена.

    Деноминатор - именно закладка, не mufradat_trained_pages (было так в
    первой версии этой правки) - иначе знаменатель рос НЕПРЕДСКАЗУЕМО
    посреди сеанса (каждый тап на новую страницу пула резко увеличивал
    total), из-за чего score10 мог УПАСТЬ после верного ответа - тот же
    "вес не растёт" эффект, который вся эта правка должна была устранить
    (баг найден advisor 17.08.2026, седьмой заход, до деплоя). Защита от
    "вписал 49 и получил дутый вес" здесь не нужна - score10 личное
    отображаемое число, не критерий ранжирования в /muftop (там сортировка
    по mastered ВНУТРИ полки, а полка - по mufradat_trained_pages, которая
    осталась честной).

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
    по страницам (project_mufradat_trainer_engine, "не начато")."""
    ayah_range = resolve_page(page_number)
    if ayah_range is None:
        return None
    words = get_words_in_range(BAQARA_SURAH, *ayah_range)
    if not words:
        return None
    progress = get_progress_map(user_id, [w["id"] for w in words])
    mastered = sum(1 for w in words if is_mastered(progress.get(w["id"])))
    total = len(words)
    return {"total": total, "mastered": mastered, "score10": round(10 * mastered / total, 2)}


# Полки рейтинга по ГЛУБИНЕ прохождения (max тренированная страница),
# границы включительно, без пересечений.
PAGE_BRACKETS = [
    ("2-5", 2, 5),
    ("6-10", 6, 10),
    ("11-15", 11, 15),
    ("16-25", 16, 25),
    ("26-49", 26, 49),
]


def _bracket_for_page(max_page):
    for label, lo, hi in PAGE_BRACKETS:
        if lo <= max_page <= hi:
            return label
    return None


def get_leaderboard():
    """Список (bracket_label, [(user_id, score_dict), ...]) - полки по
    глубине прохождения (max пройденная страница), не единый общий
    список: студент, прошедший 20 страниц, и студент, допрыгнувший сразу
    на 30-ю и тренировавший только её, иначе оказались бы в одном ряду.

    Внутри полки сортировка по ЧИСЛУ выученных слов (mastered), НЕ по
    доле (score10) - доля не защищена от того же самого трюка (у
    "прыгнувшего" знаменатель маленький, доля может быть выше при
    меньшей реальной работе). score10 остаётся личным числом на
    карточке/в статистике, не рейтинговым критерием (разбор advisor
    17.08.2026, четвёртый заход)."""
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_TRAINED_PAGES_SCHEMA)
        rows = conn.execute(
            "SELECT user_id, MAX(page_number) FROM mufradat_trained_pages GROUP BY user_id"
        ).fetchall()

    buckets = {label: [] for label, _, _ in PAGE_BRACKETS}
    for uid, max_page in rows:
        label = _bracket_for_page(max_page)
        if label is None:
            continue
        score = compute_overall_score(uid)
        if score:
            buckets[label].append((uid, score))

    for label in buckets:
        buckets[label].sort(key=lambda item: (-item[1]["mastered"], -item[1]["score10"]))

    return [(label, buckets[label]) for label, _, _ in PAGE_BRACKETS]


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
# же день по решению пользователя.
DAILY_WORDS_FOR_TASK_CREDIT = 15


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
