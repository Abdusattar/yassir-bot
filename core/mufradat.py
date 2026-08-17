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
from core.quran_pages import resolve_page, BAQARA_SURAH

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

# "Выучено" = верный ответ в 3 РАЗНЫХ дня, не N раз подряд за один присест -
# подряд за один сеанс проверяет кратковременную память, не долговременную
# (эффект беглости), см. разбор advisor 17.08.2026 и project_mufradat_trainer_engine.
MASTERY_DAYS = 3

# Даже "выученное" (days_correct >= MASTERY_DAYS) слово залёживается - без
# повторной проверки долговременная память не гарантирована (та же логика,
# что и у Anki: "зрелая" карточка всё равно ревьюится, просто редко). Если
# с последнего верного ответа прошло RECHECK_AFTER_DAYS+ дней - слово
# получает вес как у только что ошибочного (не выше!), чтобы не спрашиваться
# ЧАЩЕ слов, которые студент реально сейчас учит (решение пользователя
# 17.08.2026, второй заход после моей правки "по-научному" MASTERY_DAYS).
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
    """progress_row - словарь с correct_streak/wrong_count/days_correct/
    last_correct_date или None (слово ещё не спрашивали). Новое слово
    получает вес как у слова с одной верной серией подряд - не
    перегружаем вопросами непройденные слова, но и не игнорируем их
    (согласовано с пользователем 17.08.2026).

    Залежавшееся "выученное" слово (см. RECHECK_AFTER_DAYS) получает вес
    как у только что ошибочного (1.0), НЕ выше - иначе оно бы спрашивалось
    ЧАЩЕ слов, которые студент реально сейчас учит, что неправильно."""
    if not progress_row:
        return 1.0 / (1 + 1)
    if is_mastered(progress_row) and _is_stale(progress_row):
        return 1.0
    return 1.0 / (1 + progress_row["correct_streak"])


def _repeated_glosses(words, min_count=3):
    """Переводы, встречающиеся в диапазоне min_count+ раз - частицы и
    контекстно устойчивые слова, см. модульный docstring."""
    counts = Counter(
        _normalize_gloss(w["translation"]) for w in words if not _is_scaffold(w["translation"])
    )
    return {norm for norm, cnt in counts.items() if cnt >= min_count}


def pick_question_word(words, progress_by_id, min_repeat_exclude=3):
    """words - результат get_words_in_range. Целью вопроса не может быть
    слово с пояснением в скобках (не проверяет знание слова, угадывается
    по форме ответа), а также слово с часто повторяющимся переводом
    (см. модульный docstring)."""
    repeated = _repeated_glosses(words, min_repeat_exclude)
    candidates = [
        w for w in words
        if not _is_scaffold(w["translation"]) and _normalize_gloss(w["translation"]) not in repeated
    ]
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
    """Обновляет прогресс по одной строке mufradat_words. correct_streak
    двигает вес вопроса В РАМКАХ сеанса (может расти хоть за одну сессию).
    days_correct двигает "выучено" (MASTERY_DAYS) и растёт максимум раз в
    календарный день - обычная ошибка сбрасывает только серию, НЕ дни,
    чтобы одна случайная опечатка не стирала недели занятий (нет цели
    "гонять железно", решение пользователя 17.08.2026).

    ИСКЛЮЧЕНИЕ: если слово было "выученным", но залежалось (см.
    RECHECK_AFTER_DAYS) - это настоящая повторная проверка, и провал на
    ней действительно означает "уже не выучено" - days_correct снижается
    на 1 (решение пользователя 17.08.2026, второй заход)."""
    today = _today()
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(_PROGRESS_SCHEMA)
        row = conn.execute(
            "SELECT correct_streak, wrong_count, days_correct, last_correct_date "
            "FROM mufradat_progress WHERE user_id=? AND word_id=?",
            (user_id, word_id)
        ).fetchone()
        streak, wrong, days, last_date = tuple(row) if row else (0, 0, 0, None)
        if correct:
            streak += 1
            if last_date != today:
                days += 1
                last_date = today
        else:
            was_stale_mastered = row and is_mastered(row) and _is_stale(row)
            streak = 0
            wrong += 1
            if was_stale_mastered:
                days = max(0, days - 1)
        conn.execute(
            "INSERT OR REPLACE INTO mufradat_progress "
            "(user_id, word_id, correct_streak, wrong_count, days_correct, last_correct_date) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, word_id, streak, wrong, days, last_date)
        )


def is_mastered(progress_row):
    return bool(progress_row) and progress_row["days_correct"] >= MASTERY_DAYS


def set_current_page(user_id, page_number, start_ayah, end_ayah):
    """Пишет последнюю явно введённую студентом страницу - НЕ читается
    нигде для выбора пула тренажёра (слова идут вперемешку со всех
    тренированных страниц, см. get_words_for_trained_pages). Оставлено
    как побочный, потенциально полезный след истории на будущее -
    удаление читателя (get_current_page) не создаёт гонки с активной
    карточкой, т.к. она хранит page_number вопроса отдельно
    (advisor 17.08.2026, финальный заход)."""
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_PAGE_SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO mufradat_page (user_id, page_number, start_ayah, end_ayah) VALUES (?,?,?,?)",
            (user_id, page_number, start_ayah, end_ayah)
        )


def mark_page_trained(user_id, page_number):
    """Вызывается при КАЖДОМ ответе (не при открытии карточки) - "трогал"
    страницу значит реально на ней отвечал, не просто зашёл посмотреть."""
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_TRAINED_PAGES_SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO mufradat_trained_pages (user_id, page_number) VALUES (?,?)",
            (user_id, page_number)
        )


def get_trained_pages(user_id):
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_TRAINED_PAGES_SCHEMA)
        return [r[0] for r in conn.execute(
            "SELECT page_number FROM mufradat_trained_pages WHERE user_id=?", (user_id,)
        ).fetchall()]


def get_words_for_trained_pages(user_id):
    """Пул слов со ВСЕХ тренированных страниц студента разом, вперемешку -
    не одна страница за раз, чтобы старые страницы естественно повторялись
    вместе с новой работой (решение пользователя 17.08.2026, второй заход
    после жалобы на залипание на одной странице)."""
    words = []
    for page_number in get_trained_pages(user_id):
        ayah_range = resolve_page(page_number)
        if ayah_range:
            words.extend(get_words_in_range(BAQARA_SURAH, *ayah_range))
    return words


def compute_overall_score(user_id):
    """Общий вес студента - доля ВЫУЧЕННЫХ слов (is_mastered, days_correct
    >= MASTERY_DAYS) среди ВСЕХ слов на страницах, которые он реально
    тренировал (не "текущая страница", см. mufradat_trained_pages выше).
    Возвращает None, если студент ещё не тренировал ни одной страницы."""
    words = get_words_for_trained_pages(user_id)
    if not words:
        return None

    word_ids = [w["id"] for w in words]
    progress = get_progress_map(user_id, word_ids)
    mastered = sum(1 for wid in word_ids if is_mastered(progress.get(wid)))
    total = len(word_ids)
    return {
        "total": total, "mastered": mastered, "remaining": total - mastered,
        "score10": round(10 * mastered / total, 2),
    }


def compute_page_score(user_id, page_number):
    """Вес ОДНОЙ страницы (не всех тренированных, как compute_overall_score) -
    доля выученных слов именно на ней. Сейчас не используется в самом
    тренажёре (слова вперемешку со всех страниц, см.
    get_words_for_trained_pages) - оставлен для будущего экрана
    цветовой шкалы по страницам (project_mufradat_trainer_engine,
    "не начато")."""
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
# тапая по одному и тому же лёгкому слову 20 раз.
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
