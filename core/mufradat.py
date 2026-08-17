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

# "Выучено" = верный ответ в 3 РАЗНЫХ дня, не N раз подряд за один присест -
# подряд за один сеанс проверяет кратковременную память, не долговременную
# (эффект беглости), см. разбор advisor 17.08.2026 и project_mufradat_trainer_engine.
MASTERY_DAYS = 3

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
    """progress_row - словарь с correct_streak/wrong_count или None (слово
    ещё не спрашивали). Новое слово получает вес как у слова с одной
    верной серией подряд - не перегружаем вопросами непройденные слова,
    но и не игнорируем их (согласовано с пользователем 17.08.2026)."""
    streak = progress_row["correct_streak"] if progress_row else 1
    return 1.0 / (1 + streak)


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


def generate_question(words, progress_by_id, n_options=6):
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
    календарный день - ошибка сбрасывает только серию, НЕ дни, чтобы одна
    случайная опечатка не стирала недели занятий (нет цели "гонять
    железно", решение пользователя 17.08.2026)."""
    today = _today()
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_PROGRESS_SCHEMA)
        row = conn.execute(
            "SELECT correct_streak, wrong_count, days_correct, last_correct_date "
            "FROM mufradat_progress WHERE user_id=? AND word_id=?",
            (user_id, word_id)
        ).fetchone()
        streak, wrong, days, last_date = row if row else (0, 0, 0, None)
        if correct:
            streak += 1
            if last_date != today:
                days += 1
                last_date = today
        else:
            streak = 0
            wrong += 1
        conn.execute(
            "INSERT OR REPLACE INTO mufradat_progress "
            "(user_id, word_id, correct_streak, wrong_count, days_correct, last_correct_date) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, word_id, streak, wrong, days, last_date)
        )


def is_mastered(progress_row):
    return bool(progress_row) and progress_row["days_correct"] >= MASTERY_DAYS


def get_current_page(user_id):
    """Возвращает (page_number, start_ayah, end_ayah) или None. page_number
    хранится отдельно от диапазона - нужен для заголовка карточки ("стр.
    23") и для будущей цветовой шкалы по страницам (агрегация по
    page_number, не по произвольному диапазону) - advisor 17.08.2026."""
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(_PAGE_SCHEMA)
        row = conn.execute(
            "SELECT page_number, start_ayah, end_ayah FROM mufradat_page WHERE user_id=?", (user_id,)
        ).fetchone()
    return (row["page_number"], row["start_ayah"], row["end_ayah"]) if row else None


def set_current_page(user_id, page_number, start_ayah, end_ayah):
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_PAGE_SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO mufradat_page (user_id, page_number, start_ayah, end_ayah) VALUES (?,?,?,?)",
            (user_id, page_number, start_ayah, end_ayah)
        )
