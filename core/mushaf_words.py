"""Личный список "Мои слова" - слова со страницы чтения мусхафа, отмеченные
студентом двойным тапом/кликом для повторения (29.08.2026, "встретил
забытое слово по ходу чтения, хочу вернуться к нему потом"), а с того же
дня (второй заход) - ТАКЖЕ слова, отвеченные неверно в тренажёре
(add_starred_word_by_progress_key, см. core/mufradat.py:record_answer) -
список растёт без предела, ограничений на размер намеренно нет (решение
пользователя: два канала слива - ручное удаление и 5 верных подряд -
достаточны). Простой список арабский+перевод для чтения - клик по строке
никуда не ведёт, не квиз (решение пользователя 29.08.2026, первый заход).
Арабский текст всегда БЕЗ цветной таджвид-разметки (даже если добавлено
со страницы чтения, где разметка есть) - решение пользователя, список
для повторения, не для чтения с таджвидом.

Идентификатор слова - (surah, ayah, position) из данных страницы чтения
(mushaf_data/page*.json, scripts/export_mushaf_page.py), НЕ progress_key
mufradat_words напрямую - резолвится отдельным JOIN при добавлении (см.
ниже), т.к. это разные системы идентификации одного и того же слова.

Интеграция с тренажёром (29.08.2026, второй заход - решение пользователя
"их надо обязательно прогонять в тренажёре"): при добавлении слова сразу
пытаемся разрешить его progress_key (совпадение по surah/ayah/position с
mufradat_words, язык 'ru' - тот же язык, каким страница чтения
экспортирует переводы, см. scripts/export_mushaf_page.py:get_ayah_words).
mufradat_words покрывает весь Коран (1-114, синк на прод 29.08.2026 - см.
память project_mufradat_local_full_quran_data), так что резолвится
практически всегда; не нашли - progress_key остаётся NULL, слово просто
списком для чтения, как и было изначально."""
import json
import os
import re
import sqlite3
from datetime import datetime, timezone

from core.sampler import HADITHS_DB

# Со страницы чтения арабский текст приходит с цветной таджвид-разметкой
# (<tajweed class=...>...</tajweed>, см. scripts/export_mushaf_page.py) -
# "Мои слова" её не показывает (решение пользователя 29.08.2026, список для
# повторения, не для чтения с таджвидом) - снимаем теги, оставляя только
# буквы. Слова, приходящие из тренажёра (add_starred_word_by_progress_key),
# и так без тегов (arabic_text из mufradat_words - обычный текст).
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tajweed_tags(html):
    return _TAG_RE.sub("", html)

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS mushaf_starred_words(
        user_id TEXT NOT NULL,
        surah INTEGER NOT NULL,
        ayah INTEGER NOT NULL,
        position INTEGER NOT NULL,
        arabic_html TEXT NOT NULL,
        translation TEXT NOT NULL,
        added_at TEXT NOT NULL,
        progress_key INTEGER,
        PRIMARY KEY (user_id, surah, ayah, position)
    )
"""

# Тот же язык, каким страница чтения экспортирует переводы (SOURCE_LANGUAGE
# в scripts/export_mushaf_page.py) - иначе progress_key просто не найдётся
# (mufradat_words хранит несколько языков в одной таблице).
_LANGUAGE = "ru"


def _ensure_schema(conn):
    conn.execute(_SCHEMA)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(mushaf_starred_words)")}
    if "progress_key" not in cols:
        conn.execute("ALTER TABLE mushaf_starred_words ADD COLUMN progress_key INTEGER")


def _resolve_progress_key(conn, surah, ayah, position):
    row = conn.execute(
        "SELECT progress_key FROM mufradat_words WHERE surah_number=? AND ayah_number=? "
        "AND position=? AND language=?",
        (surah, ayah, position, _LANGUAGE)
    ).fetchone()
    return row[0] if row else None


def _merge_tail_arabic(conn, surah, ayah, position, arabic_text, language=_LANGUAGE):
    """Устойчивые сочетания (30.08.2026, тот же баг класс, что в
    add_starred_word_by_progress_key, найден по вопросу пользователя "а мы
    ничего не потеряли?") - следующие позиции того же аята с
    translation="*" приклеиваются арабским текстом (см.
    core/mufradat.py:_merge_glued_translations - тот же алгоритм, здесь
    нет предзагруженного списка строк аята, поэтому запрашиваем по одной).
    Перевод головы (translation, передан отдельно вызывающим кодом) уже
    покрывает всю связку - его не трогаем."""
    parts = [arabic_text]
    pos = position + 1
    while True:
        tail = conn.execute(
            "SELECT arabic_text, translation FROM mufradat_words "
            "WHERE surah_number=? AND ayah_number=? AND position=? AND language=?",
            (surah, ayah, pos, language)
        ).fetchone()
        if not tail or tail[1].strip() != "*":
            break
        parts.append(tail[0])
        pos += 1
    return " ".join(parts)


def add_starred_word(user_id, surah, ayah, position, arabic_html, translation):
    """Идемпотентно (INSERT OR IGNORE) - двойной тап на уже добавленном
    слове на странице чтения молча ничего не меняет, не убирает его. На
    странице чтения нет визуальной пометки "уже в списке" - слепой toggle
    там рисковал бы тихо удалить слово случайным повторным тапом. Убрать
    можно только явно, из самого списка "Мои слова" (remove_starred_word),
    либо автоматически по достижении MASTERY_STREAK верных подряд в
    тренажёре (см. core/mufradat.py:record_answer)."""
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        progress_key = _resolve_progress_key(conn, surah, ayah, position)
        # Голова устойчивого сочетания (30.08.2026) - страница чтения не
        # склеивает арабский текст head+"*"-хвоста для показа (каждое
        # слово - свой глиф в построчной вёрстке), но перевод головы уже
        # покрывает ВСЮ связку - без склейки арабский в "Мои слова" не
        # соответствовал бы переводу (тот же баг, что был в
        # add_starred_word_by_progress_key, найден по вопросу пользователя
        # "а мы точно ничего не потеряли?").
        arabic_html = _merge_tail_arabic(conn, surah, ayah, position, arabic_html)
        conn.execute(
            "INSERT OR IGNORE INTO mushaf_starred_words "
            "(user_id, surah, ayah, position, arabic_html, translation, added_at, progress_key) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (user_id, surah, ayah, position, _strip_tajweed_tags(arabic_html), translation,
             datetime.now(timezone.utc).isoformat(), progress_key)
        )


def add_starred_word_by_progress_key(user_id, progress_key, language=_LANGUAGE):
    """Авто-добавление при неверном ответе в тренажёре (core/mufradat.py:
    record_answer, 29.08.2026, решение пользователя "должно уходить в мои
    слова"). В отличие от add_starred_word (тап на странице чтения, есть
    surah/ayah/position/arabic/translation готовыми), тут есть только
    progress_key - берём представительную строку из mufradat_words (тот же
    подход, что get_words_by_progress_keys в core/mufradat.py: arabic_text/
    translation одинаковы у всех вхождений одного progress_key по
    построению, конкретные surah/ayah/position роли не играют, просто нужен
    один реальный идентификатор для PRIMARY KEY таблицы). Идемпотентно, как
    и add_starred_word - если это же вхождение уже в списке, ничего не
    меняет."""
    if progress_key is None:
        return
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT surah_number, ayah_number, position, arabic_text, translation "
            "FROM mufradat_words WHERE progress_key=? AND language=? LIMIT 1",
            (progress_key, language)
        ).fetchone()
        if row is None:
            return
        surah, ayah, position, arabic_text, translation = row
        # Склейка устойчивых сочетаний (30.08.2026, живой баг - пользователь
        # увидел на карточке "مِّنۢ بَعْدِ" ("после"), а в "Мои слова" попало
        # только "مِّنۢ" без хвоста "بَعْدِ") - представительная строка тут
        # берётся напрямую по progress_key, БЕЗ прохода через
        # _merge_glued_translations (та работает на предзагруженном списке
        # строк ayah'а, здесь его нет) - см. _merge_tail_arabic.
        arabic_text = _merge_tail_arabic(conn, surah, ayah, position, arabic_text, language)
        # Импорт внутри функции - не наверху файла (30.08.2026): core.mufradat
        # уже импортирует ИЗ core.mushaf_words на верхнем уровне (см. модульный
        # docstring выше), обратный импорт там же создал бы цикл. К моменту
        # реального вызова этой функции core.mufradat уже полностью
        # загружен, поэтому отложенный импорт здесь безопасен.
        from core.mufradat import _clean_translation
        translation = _clean_translation(translation)
        conn.execute(
            "INSERT OR IGNORE INTO mushaf_starred_words "
            "(user_id, surah, ayah, position, arabic_html, translation, added_at, progress_key) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (user_id, surah, ayah, position, arabic_text, translation,
             datetime.now(timezone.utc).isoformat(), progress_key)
        )


def _reset_progress_streak(conn, user_id, progress_key):
    """Слово покинуло "Мои слова" (любым путём - вручную или 5 верных
    подряд) - обнуляет correct_streak в mufradat_progress (core/mufradat.py),
    чтобы путь к MASTERY_STREAK начинался заново, "как у обычного слова",
    а не мгновенно засчитывался на уже накопленном streak=5 (решение
    пользователя 29.08.2026 - без сброса выход из "Мои слова" совпадал бы
    с уходом слова на 60-дневный отдых, минуя повторное подтверждение).
    Не трогает wrong_count/correct_count/last_correct_date - только текущую
    серию. Нет строки прогресса (слово ни разу не отвечали в тренажёре) -
    UPDATE просто не находит строк, безопасный no-op."""
    if progress_key is None:
        return
    conn.execute(
        "UPDATE mufradat_progress SET correct_streak=0 WHERE user_id=? AND word_id=?",
        (user_id, progress_key)
    )


def remove_starred_word(user_id, surah, ayah, position):
    """Двойной тап/клик по строке В САМОМ списке (см. модульный docstring).
    Сбрасывает correct_streak (см. _reset_progress_streak) - решение
    пользователя 29.08.2026: ручное удаление тоже "как все", не льгота."""
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT progress_key FROM mushaf_starred_words "
            "WHERE user_id=? AND surah=? AND ayah=? AND position=?",
            (user_id, surah, ayah, position)
        ).fetchone()
        conn.execute(
            "DELETE FROM mushaf_starred_words WHERE user_id=? AND surah=? AND ayah=? AND position=?",
            (user_id, surah, ayah, position)
        )
        if row is not None:
            _reset_progress_streak(conn, user_id, row[0])


def remove_starred_by_progress_key(user_id, progress_key):
    """Авто-удаление по достижении MASTERY_STREAK в тренажёре (вызывается
    из core/mufradat.py:record_answer). По progress_key, НЕ по конкретной
    (surah,ayah,position) - одно и то же слово может быть отмечено на
    НЕСКОЛЬКИХ страницах одновременно (progress_key общий для всех
    вхождений одной пары arabic_text/перевод, см. core/sampler.py), и
    "выучено" оно тоже одно на всех - вопрос в тренажёре мог попасться по
    ЛЮБОМУ из этих вхождений, не обязательно по тому, что отмечал студент.
    Сбрасывает correct_streak (см. _reset_progress_streak) - это и есть
    развязка "вышло из Моих слов" от "ушло на 60-дневный отдых": вызывающий
    код (record_answer) уже записал streak=5 ДО этого вызова, тут же
    перезаписываем его в 0, чтобы is_mastered() перестал быть true и слово
    вернулось в обычный пул вопросов."""
    if progress_key is None:
        return
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        conn.execute(
            "DELETE FROM mushaf_starred_words WHERE user_id=? AND progress_key=?",
            (user_id, progress_key)
        )
        _reset_progress_streak(conn, user_id, progress_key)


def get_starred_progress_keys(user_id):
    """Только слова с уже разрешённым progress_key - это то, что тренажёр
    вообще способен задать вопросом. Вызывается перед КАЖДЫМ
    generate_question (core/mufradat.py) - см. get_starred_question_pool."""
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT DISTINCT progress_key FROM mushaf_starred_words "
            "WHERE user_id=? AND progress_key IS NOT NULL",
            (user_id,)
        ).fetchall()
    return {r[0] for r in rows}


def _translations_for(conn, triples, language):
    """(surah, ayah, position) -> перевод на нужном языке, одним запросом.
    Кусками по 200 троек: список "Моих слов" не ограничен по размеру (см.
    модульный docstring), а у SQLite есть предел на число параметров."""
    found = {}
    triples = list(triples)
    for i in range(0, len(triples), 200):
        chunk = triples[i:i + 200]
        where = " OR ".join(
            ["(surah_number=? AND ayah_number=? AND position=?)"] * len(chunk)
        )
        params = [language]
        for t in chunk:
            params.extend(t)
        rows = conn.execute(
            "SELECT surah_number, ayah_number, position, translation FROM mufradat_words "
            "WHERE language=? AND (" + where + ")",
            params
        ).fetchall()
        for surah, ayah, position, translation in rows:
            found[(surah, ayah, position)] = translation
    return found


def list_starred_words(user_id, language=_LANGUAGE):
    """Новые сверху - только что встреченное забытое слово должно быть
    первым в списке, не погребено под старыми.

    Перевод берётся НА ЯЗЫКЕ СТУДЕНТА в момент чтения списка, а не тот,
    что лежит в таблице (30.08.2026, живой баг: студент переключился на
    кыргызский, а "Мои слова" остались русскими). В mushaf_starred_words
    перевод - снимок момента добавления, всегда русский: и страница чтения,
    и add_starred_word_by_progress_key работают с _LANGUAGE="ru". Хранить
    по копии на каждый язык незачем - mufradat_words и так покрывает все
    языки, ключ (surah, ayah, position) общий.

    Нет перевода на целевом языке (кыргызский и узбекский готовы пока на
    джуз 1) - остаётся русский из таблицы: пустая строка в списке для
    повторения бесполезнее, чем перевод на другом языке."""
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT surah, ayah, position, arabic_html, translation FROM mushaf_starred_words "
            "WHERE user_id=? ORDER BY added_at DESC",
            (user_id,)
        ).fetchall()
        localized = {}
        if language != _LANGUAGE and rows:
            localized = _translations_for(
                conn, [(r[0], r[1], r[2]) for r in rows], language
            )
    from core.mufradat import _clean_translation
    out = []
    for surah, ayah, position, arabic, translation in rows:
        t = localized.get((surah, ayah, position))
        # "*" - хвост устойчивого сочетания, его перевод целиком лежит на
        # головном слове (см. _merge_tail_arabic): как самостоятельный
        # перевод он бессмыслен, откатываемся на сохранённый.
        if t and t.strip() and t.strip() != "*":
            translation = _clean_translation(t)
        out.append({
            "surah": surah, "ayah": ayah, "position": position,
            "arabic": arabic, "translation": translation,
        })
    return out


# Закладка страницы чтения (30.08.2026, кнопка 🔖 в #page-nav) - НЕ то же
# самое, что закладка тренажёра (mufradat_page/set_current_page, "дошёл до
# страницы N", пул вопросов). Эта - произвольная точка возврата, которую
# студент сам выставляет тапом на любой странице ("сохранить") и подтягивает
# обратно тапом на "«" (решение пользователя 30.08.2026: тап на иконку -
# сохранить, отдельная кнопка "«" в навигаторе - перейти). На сервере по
# Telegram ID (решение пользователя - переживает смену устройства/браузера),
# отдельная маленькая таблица, одна строка на студента.
_BOOKMARK_SCHEMA = """
    CREATE TABLE IF NOT EXISTS mushaf_reading_bookmark(
        user_id TEXT PRIMARY KEY,
        page_number INTEGER NOT NULL,
        updated_at TEXT NOT NULL
    )
"""


def set_reading_bookmark(user_id, page_number):
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_BOOKMARK_SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO mushaf_reading_bookmark (user_id, page_number, updated_at) "
            "VALUES (?,?,?)",
            (user_id, page_number, datetime.now(timezone.utc).isoformat())
        )


# Указатель режима заучивания 40+40 (01.09.2026) - "где студент сейчас":
# страница, номер СТРОКИ на ней и этап (1 - по строчкам, 2 - половина
# страницы, 3 - страница целиком). Третья по счёту "закладка" в проекте, и
# все три - разные вещи, путать нельзя:
#   mufradat_page          - "дошёл до страницы N", задаёт пул вопросов тренажёра
#   mushaf_reading_bookmark - произвольная точка возврата, кнопка 🔖
#   mushaf_hifz_pointer    - место в методике заучивания, двигается сдачами
# На сервере по Telegram ID, а не в localStorage: указатель двигают ОБА
# канала сдачи (режим в мусхафе и старая сдача в группе), и он обязан
# переживать смену устройства.
_HIFZ_SCHEMA = """
    CREATE TABLE IF NOT EXISTS mushaf_hifz_pointer(
        user_id TEXT PRIMARY KEY,
        page_number INTEGER NOT NULL,
        line_index INTEGER NOT NULL,
        stage INTEGER NOT NULL,
        updated_at TEXT NOT NULL
    )
"""


def set_hifz_pointer(user_id, page_number, line_index, stage):
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_HIFZ_SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO mushaf_hifz_pointer "
            "(user_id, page_number, line_index, stage, updated_at) VALUES (?,?,?,?,?)",
            (user_id, page_number, line_index, stage,
             datetime.now(timezone.utc).isoformat())
        )


def get_hifz_pointer(user_id):
    """None, если студент ещё ни разу не входил в режим заучивания."""
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_HIFZ_SCHEMA)
        row = conn.execute(
            "SELECT page_number, line_index, stage FROM mushaf_hifz_pointer "
            "WHERE user_id=?",
            (user_id,)
        ).fetchone()
    if not row:
        return None
    return {"page": row[0], "line": row[1], "stage": row[2]}


def get_reading_bookmark(user_id):
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_BOOKMARK_SCHEMA)
        row = conn.execute(
            "SELECT page_number FROM mushaf_reading_bookmark WHERE user_id=?",
            (user_id,)
        ).fetchone()
    return row[0] if row else None


# ── Движение указателя 40+40 ────────────────────────────────────────────
# Тот же автомат, что на фронтенде (hifzNext в mushaf_data/index.html):
# этап 1 идёт по строчкам внутри половины листа, дойдя до конца - этап 2
# (половина целиком); сдав первую половину, возвращаемся на этап 1 уже во
# второй; сдав вторую - этап 3 (страница целиком); сдав страницу - на
# следующую, снова с первой строки.
#
# Дублирование автомата осознанное: в приложении переход должен случиться
# МГНОВЕННО, без ожидания ответа сервера, а сдача голосом в группе идёт
# вообще мимо приложения. Формулу половины ("line < n//2") держать
# одинаковой в обоих местах - расхождение будет означать, что после сдачи
# в группе студент увидит в приложении не ту строку.

_MUSHAF_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "mushaf_data")
_page_line_counts = {}
_HIFZ_LAST_PAGE = 604


def page_text_line_count(page_number, default=15):
    """Сколько ТЕКСТОВЫХ строк на листе: строка с названием суры и басмала
    в счёт не идут, иначе половина листа съедет. Читаем из тех же
    page*.json, что отдаёт приложение; результат кэшируем."""
    if page_number in _page_line_counts:
        return _page_line_counts[page_number]
    path = os.path.join(_MUSHAF_DATA_DIR, f"page{page_number}.json")
    count = default
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        found = sum(1 for l in data.get("lines", []) if l.get("type") == "text")
        if found:
            count = found
    except (OSError, ValueError):
        pass
    _page_line_counts[page_number] = count
    return count


def next_hifz_position(page, line, stage, page_lines=None):
    """Чистая функция: (страница, строка, этап) -> следующая позиция.
    Возвращает то же самое, если дальше идти некуда (последняя страница)."""
    n = page_lines or page_text_line_count(page)
    mid = n // 2
    if stage == 1:
        half_end = (mid - 1) if line < mid else (n - 1)
        if line < half_end:
            return page, line + 1, 1
        return page, line, 2
    if stage == 2:
        if line < mid:
            return page, mid, 1          # первая половина сдана - идём во вторую
        return page, line, 3
    if page < _HIFZ_LAST_PAGE:
        return page + 1, 0, 1
    return page, line, stage


def advance_hifz_pointer(user_id):
    """Сдвигает указатель студента на одну единицу вперёд. Ничего не делает,
    если студент ещё ни разу не заходил в режим заучивания - тогда у него
    нет места, которое можно двигать, и выдумывать его нельзя."""
    pointer = get_hifz_pointer(user_id)
    if not pointer:
        return None
    page, line, stage = next_hifz_position(pointer["page"], pointer["line"], pointer["stage"])
    if (page, line, stage) == (pointer["page"], pointer["line"], pointer["stage"]):
        return pointer
    set_hifz_pointer(user_id, page, line, stage)
    return {"page": page, "line": line, "stage": stage}
