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
  - слова, за которыми стоит 3+ РАЗНЫХ арабских слова с одним и тем же
    переводом (частицы вроде "не"/"в"/"из", но и контекстно устойчивые
    слова вроде "Аллах") - не годятся ЦЕЛЬЮ вопроса: перевод не отличает их
    друг от друга, вопрос угадывается по виду перевода, а не по знанию
    конкретного слова (разбор advisor 17.08.2026, третий заход). Дистрактором
    остаются. ДО 26.08.2026 порог считался по числу СТРОК (позиций), а не
    разных арабских слов - причиной была фрагментация прогресса по позициям
    (mufradat_words.id); с переходом прогресса на progress_key
    (core/sampler.py, одно и то же слово с одним и тем же переводом на
    разных страницах теперь делит один прогресс) эта причина отпала, и
    порог считается по сути вопроса - неоднозначности перевода, см.
    _repeated_glosses.
"""
import math
import random
import re
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from core.sampler import HADITHS_DB, normalize_gloss as _normalize_gloss, ensure_mufradat_schema
from core.quran_pages import resolve_page, last_ayah_on_page, SURAHS
from core.mushaf_words import (
    get_starred_progress_keys, remove_starred_by_progress_key, add_starred_word_by_progress_key,
)

# Языки перевода, доступные в тренажёре (26.08.2026) - код -> подпись кнопки.
# API Quran Academy реально поддерживает ru/en/uz/tr (проверено эмпирически
# по живому /languages, 53 языка всего) - НО узбекский там реально заполнен
# только на первых ~9 аятах всего Корана (проверено эмпирически по HTTP 500
# на подавляющем большинстве аятов сур 1-10) - непригоден как источник,
# отложен. Кыргызского в этом API вообще нет (UNKNOWN_LANGUAGE), как и
# готового пословного перевода на кыргызский в принципе нигде не нашлось
# (проверены QuranWBW, api.quran.com, fawazahmed0/quran-api, QuranEnc -
# ни у кого нет ни кыргызского, ни пословной гранулярности одновременно).
# Кыргызский поэтому генерируется через Gemini (google/gemini-3.1-pro-preview
# via OpenRouter, scripts/generate_kyrgyz_translation.py) - осознанное
# исключение из общего правила "никогда не выдумывать переводы Корана"
# (решение пользователя 26.08.2026, при отсутствии готового источника),
# со сверкой пользователем (носитель кыргызского + пословный русский)
# первой и второй страниц перед массовой генерацией. uz/kk НЕ в этом
# словаре - не путать со списком языков UI бота (groups.lang, wiki/i18n.md).
SUPPORTED_LANGUAGES = {"ru": "Русский", "ky": "Кыргызча"}
DEFAULT_LANGUAGE = "ru"

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
    """CREATE TABLE + миграция ADD COLUMN correct_count (18.08.2026, для
    Wilson-рейтинга по точности - см. get_leaderboard). correct_count -
    НАКОПИТЕЛЬНЫЙ счётчик верных ответов, никогда не уменьшается и не
    ограничен потолком, в отличие от correct_streak (тот падает при ошибке,
    см. record_answer) - без него точность (correct/(correct+wrong)) по
    всей истории студента посчитать было нечем, только wrong_count был
    накопительным.

    Проверяем PRAGMA table_info ДО попытки ALTER (не try/except на каждый
    вызов) - эта функция дёргается на каждый тап карточки (get_progress_map,
    record_answer), try/except ловил бы исключение и писал попытку схемы в
    WAL при каждом тапе (поймал advisor 18.08.2026). Тот же трёхместный
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
# много понадобится", поднято обратно до 5 решением пользователя
# 29.08.2026 (заодно с фичей "Мои слова" - см. mushaf_words.py, слово
# уходит из личного списка по достижении именно этого порога). Естественный
# разброс по времени берётся не из календарных дней, а из самой механики
# выбора вопроса - слово с большим числом верных ответов получает меньший
# вес (word_weight) и реже выпадает, а слов на странице много, так что
# "домотать" одно и то же слово до MASTERY_STREAK за один присест почти
# невозможно.
MASTERY_STREAK = 5

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
# a-zа-яё - обычный рус./лат. алфавит. + ў/қ/ғ/ҳ (26.08.2026) - специфичные
# буквы узбекской кириллицы, отсутствующие в русском алфавите (например
# "ҳам" = "также") - без них короткое валидное узбекское слово могло ложно
# попасть под _is_junk, если все его "настоящие" буквы - именно из этого
# набора. re.IGNORECASE распространяется на них так же, как и на а-яё
# (Python 3 str-паттерны Unicode-aware по умолчанию).
_HAS_LETTER_RE = re.compile(r"[a-zа-яёқғўҳ]", re.IGNORECASE)


def _is_scaffold(translation):
    return bool(_SCAFFOLD_RE.search(translation))


def _is_junk(translation):
    """Перевод без единой буквы - не перевод вообще, ни целью вопроса, ни
    дистрактором быть не может. Раньше "*" считался меткой сноски в
    исходнике (17.08.2026) - неверно (19.08.2026, разбор по жалобе
    студента на вопрос без верного варианта): у API Quran Academy "*" -
    это признак слова, чей перевод целиком склеен с ПРЕДЫДУЩИМ словом
    (устойчивые сочетания вроде "مِن بَعْدِ" = "после", "عَلَى عَبْدِنَا" =
    "Нашему рабу,"), проверено на всех 114 строках с "*" в момент правки -
    паттерн стабильный. Такие строки поглощаются в get_words_in_range
    (арабский текст головного слова дополняется ими) и сюда никогда не
    доходят - если "*" всё же попал в _is_junk, это баг склейки, не
    ожидаемый путь. Оставшиеся "" и ":" (по 1 строке) - не склейка, у них
    перевод предыдущего слова реально не покрывает соседа - фильтруются
    здесь как раньше."""
    return not _HAS_LETTER_RE.search(translation)


def _merge_glued_translations(rows):
    """API Quran Academy для устойчивых сочетаний (предлог+сущ.,
    предлог+предлог, числительное+числительное) не даёт отдельный перевод
    каждому слову - весь перевод связки приклеен к ПЕРВОМУ слову, а
    следующие помечены переводом "*" (см. _is_junk). Без этой склейки
    первое слово остаётся в пуле вопросов с переводом фразы из 2-3 слов,
    у которого нет честного соответствия в вариантах ответа (баг, из-за
    которого студент получил вопрос без верного варианта - 19.08.2026).
    Склеиваем арабский текст головного слова с текстом всех идущих подряд
    "*"-хвостов (цепочки бывают длиннее одного слова, напр. "أَلَمْ تَرَ
    إِلَىٰ" - 2 хвоста), перевод и id оставляем от головного слова - хвосты
    в пул не попадают вообще (как и раньше)."""
    by_position = {}
    for r in rows:
        by_position.setdefault(r["ayah_number"], {})[r["position"]] = r

    merged = []
    for r in rows:
        if r["translation"].strip() == "*":
            continue
        ayah_words = by_position[r["ayah_number"]]
        arabic_parts = [r["arabic_text"]]
        pos = r["position"] + 1
        while ayah_words.get(pos) and ayah_words[pos]["translation"].strip() == "*":
            arabic_parts.append(ayah_words[pos]["arabic_text"])
            pos += 1
        merged.append({**r, "arabic_text": " ".join(arabic_parts)})
    return merged


def get_words_in_range(surah_number, start_ayah, end_ayah, language=DEFAULT_LANGUAGE):
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.row_factory = sqlite3.Row
        ensure_mufradat_schema(conn)
        rows = conn.execute(
            "SELECT id, surah_number, ayah_number, position, arabic_text, translation, progress_key "
            "FROM mufradat_words WHERE surah_number=? AND ayah_number BETWEEN ? AND ? AND language=? "
            "ORDER BY ayah_number, position",
            (surah_number, start_ayah, end_ayah, language)
        ).fetchall()
    words = _merge_glued_translations([dict(r) for r in rows])
    return [w for w in words if not _is_junk(w["translation"])]


def get_words_by_progress_keys(progress_keys, language=DEFAULT_LANGUAGE):
    """Слова по прогресс-ключам напрямую (НЕ по диапазону страниц) - для
    "Мои слова" (core/mushaf_words.py): звёздное слово может быть отмечено
    на странице, до которой закладка студента в тренажёре ещё не дошла
    (решение пользователя 29.08.2026, "подтягивать сразу, вне закладки").
    Одна строка на progress_key (MIN(id) - представитель, arabic_text и
    translation у всех вхождений одного progress_key совпадают по
    построению, см. core/sampler.py) - _merge_glued_translations тут не
    нужен, "*"-хвосты просто не имеют своего progress_key и не попадут в
    выборку по WHERE IN (эти progress_keys уже разрешены на реальных
    словах, см. core/mushaf_words.py:_resolve_progress_key)."""
    progress_keys = list({*progress_keys})
    if not progress_keys:
        return []
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.row_factory = sqlite3.Row
        ensure_mufradat_schema(conn)
        placeholders = ",".join("?" * len(progress_keys))
        rows = conn.execute(
            f"SELECT id, surah_number, ayah_number, position, arabic_text, translation, progress_key "
            f"FROM mufradat_words WHERE progress_key IN ({placeholders}) AND language=? "
            f"GROUP BY progress_key",
            (*progress_keys, language)
        ).fetchall()
    words = [dict(r) for r in rows]
    return [w for w in words if not _is_junk(w["translation"])]


# Каждый STARRED_QUESTION_QUOTA-й вопрос в тренажёре - гарантированно из
# "Мои слова" (core/mushaf_words.py), если там есть хоть одно слово с
# разрешённым progress_key. Решение пользователя 29.08.2026 -
# множитель к весу не работал бы на реальных объёмах пула (сотни-тысячи
# слов делают буст в 2-3 раза незаметным на глаз, разбор advisor того же
# дня) - только гарантированная квота даёт то самое "обязательно",
# которое просил пользователь.
STARRED_QUESTION_QUOTA = 3

_QUESTION_COUNTER_SCHEMA = """
    CREATE TABLE IF NOT EXISTS mufradat_question_counter(
        user_id TEXT PRIMARY KEY,
        count INTEGER NOT NULL DEFAULT 0
    )
"""


def _bump_question_counter(user_id):
    """Персистентный (в БД, не в _active/_active_question) счётчик вопросов
    пользователя - у обоих транспортов (чат core/mufradat_bot.py, веб
    core/mufradat_api.py) НЕСКОЛЬКО разных мест генерируют вопрос (новая
    карточка, ответ, обновление после смены страницы...) - единая функция,
    вызываемая перед КАЖДЫМ generate_question, надёжнее, чем тащить
    счётчик через параметры/сессионные словари в каждое из этих мест."""
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_QUESTION_COUNTER_SCHEMA)
        conn.execute(
            "INSERT INTO mufradat_question_counter (user_id, count) VALUES (?, 1) "
            "ON CONFLICT(user_id) DO UPDATE SET count = count + 1",
            (user_id,)
        )
        return conn.execute(
            "SELECT count FROM mufradat_question_counter WHERE user_id=?", (user_id,)
        ).fetchone()[0]


def get_starred_question_pool(user_id, language=DEFAULT_LANGUAGE):
    """Вызывать ПЕРЕД КАЖДЫМ generate_question, и в чат-версии, и в веб -
    результат передаётся как generate_question(..., starred_words=...).
    None - обычный вопрос как раньше (не подошла очередь квоты, либо в
    "Моих словах" нет ни одного слова с разрешённым progress_key)."""
    if _bump_question_counter(user_id) % STARRED_QUESTION_QUOTA != 0:
        return None
    starred_keys = get_starred_progress_keys(user_id)
    if not starred_keys:
        return None
    return get_words_by_progress_keys(starred_keys, language) or None


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
    """Переводы, за которыми стоит min_count+ РАЗНЫХ арабских слов - см.
    модульный docstring. Считаем по числу уникальных arabic_text, а не по
    числу строк (было так до 26.08.2026) - с введением progress_key
    (core/sampler.py) прогресс одного и того же арабского слова, повторённого
    на нескольких страницах, сходится в одну запись сам по себе, и первая
    причина этого фильтра ("мастерство по каждой строке отдельно не
    сходится") больше не действует. Вторая причина остаётся в силе - если
    ОДИН И ТОТ ЖЕ перевод стоит за несколькими РАЗНЫМИ арабскими словами,
    вопрос по любому из них угадывается по переводу, а не по знанию слова -
    именно эту неоднозначность фильтр и ловит теперь."""
    counts = {}
    for w in words:
        if _is_scaffold(w["translation"]):
            continue
        norm = _normalize_gloss(w["translation"])
        counts.setdefault(norm, set()).add(w["arabic_text"])
    return {norm for norm, arabic_texts in counts.items() if len(arabic_texts) >= min_count}


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
    округляется в 0, порог остаётся 3, как и было изначально.

    НЕ ПЕРЕКАЛИБРОВАНО заново после перехода _repeated_glosses на подсчёт
    РАЗНЫХ арабских слов вместо строк (26.08.2026, см. её docstring) - число
    "n" здесь по-прежнему размер ПУЛА (строк), а порог теперь сравнивается со
    счётом уникальных arabic_text на перевод, который систематически МЕНЬШЕ
    (или равен) числу строк. Значит фильтр стал ЭФФЕКТИВНО МЯГЧЕ, чем
    предполагали замеры 18.08.2026 (тот же порог реже достигается) - это и
    есть желаемый эффект (больше содержательных слов разблокируется как цель
    вопроса), но долю "годных целей" по прежней методике никто заново не
    мерил - если после деплоя она заметно съедет, порог нужно перемерить
    заново по той же методике (см. выше), а не подгонять на глаз."""
    n = max(1, len(words))
    return max(3, round(n * 0.006))


def pick_question_word(words, progress_by_id, min_repeat_exclude=None):
    """words - результат get_words_in_range. Целью вопроса не может быть
    слово с пояснением в скобках (не проверяет знание слова, угадывается
    по форме ответа), слово с часто повторяющимся переводом (см. модульный
    docstring и _scaled_repeat_threshold), а также "выученное" слово,
    которое ещё не отдохнуло положенные RECHECK_AFTER_DAYS дней - убрано
    из пула совсем, не просто с низким весом (решение пользователя
    17.08.2026, четвёртый заход).

    progress_by_id - словарь по progress_key (core/sampler.py), НЕ по id
    конкретной строки (26.08.2026) - если то же арабское слово с тем же
    переводом встречается на нескольких страницах, все его строки делят
    ОДИН прогресс, "выученность" на одной странице сразу видна и на другой."""
    if min_repeat_exclude is None:
        min_repeat_exclude = _scaled_repeat_threshold(words)
    repeated = _repeated_glosses(words, min_repeat_exclude)
    candidates = []
    for w in words:
        if _is_scaffold(w["translation"]) or _normalize_gloss(w["translation"]) in repeated:
            continue
        progress = progress_by_id.get(w["progress_key"])
        if is_mastered(progress) and not _is_stale(progress):
            continue
        candidates.append(w)
    if not candidates:
        return None
    weights = [word_weight(progress_by_id.get(w["progress_key"])) for w in candidates]
    return random.choices(candidates, weights=weights, k=1)[0]


def generate_question(words, progress_by_id, n_options=8, starred_words=None):
    """Возвращает {word, options} или None, если в диапазоне недостаточно
    слов для вопроса. options - список переводов (включая верный),
    перемешанный.

    starred_words - результат get_starred_question_pool (29.08.2026),
    когда передан и не пуст, ЦЕЛЬ вопроса берётся из него, а не из words -
    "Мои слова" должны доставаться вопросом, даже если слово со страницы,
    где его отметили, ещё вне текущей закладки студента в тренажёре
    (решение пользователя, "подтягивать сразу, вне закладки"). Дистракторы
    (неверные варианты) всё равно строятся из words - они не обязаны быть
    с той же страницы, что и цель, это просто похожие по форме вопроса
    вложения."""
    target = pick_question_word(starred_words, progress_by_id) if starred_words \
        else pick_question_word(words, progress_by_id)
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
    """word_ids - progress_key'и (core/sampler.py), не id конкретных строк
    (26.08.2026) - дедуп через set() чисто для размера IN(...) (пул может
    содержать десятки тысяч строк с сильно меньшим числом уникальных
    progress_key), на корректность не влияет."""
    word_ids = list({*word_ids})
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
    """word_id - здесь и во всех вызывающих местах (core/mufradat_bot.py) на
    самом деле progress_key (core/sampler.py), не id конкретной строки
    mufradat_words (26.08.2026) - имя колонки в схеме mufradat_progress
    осталось word_id по историческим причинам, менять не стали (лишняя
    миграция без функциональной пользы), но значения в ней теперь означают
    id "представителя" пары (arabic_text, перевод, язык), общий для всех
    страниц, где эта пара встречается.

    Обновляет прогресс по ОДНОЙ такой паре. Симметрично:
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

    correct_count (18.08.2026) растёт вместе с correct_streak на верный
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
    if correct and streak >= MASTERY_STREAK:
        # "Мои слова" (core/mushaf_words.py, 29.08.2026) - слово выходит из
        # личного списка ровно в момент, когда становится "выученным" по
        # той же мере, что и весь остальной тренажёр (is_mastered), не по
        # отдельному параллельному счётчику. word_id тут - progress_key
        # (см. докстрочку функции выше), remove_starred_by_progress_key
        # сама решает, что делать, если он не в списке (ничего). Она же
        # обнуляет correct_streak обратно в 0 (core/mushaf_words.py:
        # _reset_progress_streak) - выход из "Мои слова" НЕ должен совпадать
        # с уходом на 60-дневный отдых, слово должно заново пройти путь "как
        # обычное" (решение пользователя 29.08.2026, третий заход).
        remove_starred_by_progress_key(user_id, word_id)
    elif not correct:
        # Симметрично: неверный ответ ЛЮБОГО слова (не только уже звёздного)
        # закидывает его в "Мои слова" (решение пользователя 29.08.2026,
        # третий заход - "должно уходить автоматом"). Без предела размера
        # списка - два канала слива (ручное удаление + 5 верных подряд)
        # признаны достаточными. Идемпотентно - уже там, ничего не меняется.
        add_starred_word_by_progress_key(user_id, word_id)


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


_LANG_SCHEMA = """
    CREATE TABLE IF NOT EXISTS mufradat_lang(
        user_id TEXT PRIMARY KEY,
        language TEXT NOT NULL DEFAULT 'ru'
    )
"""


def get_current_lang(user_id):
    """Язык перевода в тренажёре у студента (переключатель на карточке,
    core/mufradat_bot.py, 26.08.2026) - по умолчанию ru, пока студент ни разу
    не переключал (та же схема, что у закладки страницы, но раздельная
    таблица - страница НЕ завязана на язык, один и тот же прогресс по
    странице виден в любом языке)."""
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_LANG_SCHEMA)
        row = conn.execute(
            "SELECT language FROM mufradat_lang WHERE user_id=?", (user_id,)
        ).fetchone()
    return row[0] if row else DEFAULT_LANGUAGE


def set_current_lang(user_id, language):
    if language not in SUPPORTED_LANGUAGES:
        return
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_LANG_SCHEMA)
        conn.execute(
            "INSERT INTO mufradat_lang (user_id, language) VALUES (?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET language=excluded.language",
            (user_id, language)
        )


def get_words_up_to_page(page_number, language=DEFAULT_LANGUAGE):
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
            words.extend(get_words_in_range(surah, 1, 9999, language))
        elif surah == bookmark_surah:
            words.extend(get_words_in_range(surah, 1, bookmark_ayah, language))
            break
        else:
            break
    return words


def get_words_for_bookmark(user_id):
    """Пул слов тренажёра для ТЕКУЩЕЙ закладки студента (get_words_up_to_page,
    см. там) - не только последняя введённая страница, а всё от начала
    диапазона (решение пользователя 17.08.2026, пятый заход). Язык - текущий
    выбор студента (get_current_lang, 26.08.2026), закладка (страница) от
    языка не зависит - переключение языка не сбрасывает прогресс по глубине."""
    page_number = get_current_page(user_id)
    if not page_number:
        return []
    return get_words_up_to_page(page_number, get_current_lang(user_id))


def compute_overall_score(user_id, words=None, progress=None):
    """Общий вес студента среди ВСЕХ слов на закладке (get_words_for_bookmark,
    2..N, ТОТ ЖЕ пул, что и у тренажёра, не только реально тронутые
    страницы). Возвращает None, если закладка ещё не установлена. Личное
    отображаемое число на карточке/в статистике - НЕ критерий ранжирования
    в /muftop (там с 18.08.2026 Wilson-точность по всей истории, см.
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
    не дублируем те же 2 запроса к БД (advisor, пятый заход).

    Считаем по УНИКАЛЬНЫМ progress_key, не по строкам пула (26.08.2026,
    вместе с переходом прогресса на progress_key - core/sampler.py) - иначе
    числитель (мастерство, привязанное к progress_key) и знаменатель (число
    строк) считались бы в разных единицах. Знаменатель поэтому меньше, чем
    раньше (число строк > число уникальных пар) - "Общий вес" на карточке
    заметно ПОДРОС у всех студентов сразу после этой правки (не баг, честный
    побочный эффект дедупа - обсуждено и принято пользователем 26.08.2026)."""
    if words is None:
        words = get_words_for_bookmark(user_id)
    if not words:
        return None
    if progress is None:
        progress = get_progress_map(user_id, [w["progress_key"] for w in words])

    pair_keys = {w["progress_key"] for w in words}
    mastered = sum(1 for pk in pair_keys if is_mastered(progress.get(pk)))
    stimulus_sum = sum(word_stimulus_credit(progress.get(pk)) for pk in pair_keys)
    total = len(pair_keys)
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
    core/quran_pages.py) - суммируем слова по всем сурам страницы. Язык -
    текущий выбор студента (get_current_lang, 26.08.2026), как и в
    get_words_for_bookmark. Считаем по progress_key, не по строкам - см.
    docstring compute_overall_score."""
    entries = resolve_page(page_number)
    if entries is None:
        return None
    language = get_current_lang(user_id)
    words = []
    for surah, start_ayah, end_ayah in entries:
        words.extend(get_words_in_range(surah, start_ayah, end_ayah, language))
    if not words:
        return None
    progress = get_progress_map(user_id, [w["progress_key"] for w in words])
    pair_keys = {w["progress_key"] for w in words}
    mastered = sum(1 for pk in pair_keys if is_mastered(progress.get(pk)))
    total = len(pair_keys)
    return {"total": total, "mastered": mastered, "score10": round(10 * mastered / total, 2)}


# Wilson-рейтинг (18.08.2026) - заменил полки по глубине страниц. Прошлая
# метрика (mastered/score10 внутри полки по max тренированной странице)
# сломалась после расширения пула на 7 сур: знаменатель (весь пул закладки)
# вырос до ~28000 слов, доля стала неинформативной у всех ("вес слишком
# малые, есть у которых 0", пользователь 18.08.2026). Пользователь прямо
# попросил формулу из двух факторов - точность (верно/открыто) и стимул
# открывать больше карточек, не наказывая за возросший шанс ошибиться на
# объёме - консультация advisor 18.08.2026 указала на Wilson lower bound
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
    реальных данных студентов, SSH-превью на проде 18.08.2026 - Нурсултан,
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
    (проверено на живых данных 18.08.2026, после прямого вопроса
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
    """user_id -> {language: {correct, wrong, n, attempted, page}} - суммарно
    по ВСЕМ словам, что студент когда-либо открывал за всю историю (не только
    текущая закладка - строка в mufradat_progress появляется один раз на
    слово и остаётся навсегда, даже если закладка потом сдвинулась дальше),
    РАЗБИТО ПО ЯЗЫКУ (26.08.2026) - смешивать точность по ru и uz в одну
    сумму нечестно (студент, ответивший на одно и то же слово на обоих
    языках, получил бы вдвое больше "attempted" просто за переключение языка,
    без реального нового знания - поймано до деплоя, см. project-заметку).
    Язык каждой progress-строки берём через JOIN на mufradat_words.language
    ПО progress_key (= mufradat_words.id представителя пары, core/sampler.py)
    - mufradat_progress.word_id хранит именно его.

    correct/wrong - SUM(correct_count)/SUM(wrong_count), оба честно
    накопительные (в отличие от correct_streak, который падает при ошибке).
    attempted - число РАЗНЫХ слов (не сумма попыток), нужен как тай-брейк
    при равном Wilson-счёте (решение пользователя 18.08.2026). page - НЕ
    завязана на язык (закладка одна на студента, get_current_page), берётся
    из отдельного запроса и подставляется в обе языковые ветки одинаково."""
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_progress_schema(conn)
        rows = conn.execute(
            "SELECT p.user_id, w.language, SUM(p.correct_count), SUM(p.wrong_count), COUNT(*) "
            "FROM mufradat_progress p JOIN mufradat_words w ON w.id = p.word_id "
            "GROUP BY p.user_id, w.language"
        ).fetchall()
        conn.execute(_PAGE_SCHEMA)
        pages = dict(conn.execute("SELECT user_id, page_number FROM mufradat_page").fetchall())

    totals = {}
    for uid, lang, c, w, n in rows:
        totals.setdefault(uid, {})[lang] = {
            "correct": c or 0, "wrong": w or 0, "n": (c or 0) + (w or 0), "attempted": n,
            "page": pages.get(uid, 0),
        }
    return totals


def get_leaderboard():
    """Единый общий список (user_id, score_dict), НЕ полки по глубине
    страниц (было так до 18.08.2026) - Wilson-точность сравнима на любой
    глубине пула напрямую (в отличие от score10/mastered, которые зависели
    от размера знаменателя закладки), деление на полки только прятало бы
    студентов на ранних страницах от тех, кто прошёл дальше.

    Сортировочный ключ - wilson * log10(1+attempted) * log10(1+page), НЕ
    чистый wilson (была первая версия 18.08.2026, тай-брейк по attempted
    при точном совпадении Wilson - см. docstring _wilson_lower_bound,
    почему не сработало на практике), и не двучленная версия без страницы
    (была вторая версия в тот же день). Три множителя решают три РАЗНЫЕ
    проблемы, найденные на живых данных по очереди:
      - wilson - точность НЕ равна голому %, малый объём не даёт вздутую
        точность обогнать честную (1/1 не бьёт 190/200).
      - log10(1+attempted) - объём (число открытых карточек) тянет
        сортировку постоянно, но сублинейно - без него high-accuracy при
        низком объёме обгоняла large-accuracy при высоком (Бехзод
        46/93.9% выше Нурсултана 271/87.4% в версии без этого множителя).
      - log10(1+page) - глубина продвижения по Корану (закладка) тоже
        весит - без неё студент на маленьком пуле (стр.3, ~160 слов)
        обгонял студента на большом пуле (стр.14, ~1500 слов) просто
        потому что на маленьком пуле физически легче быстро набрать много
        карточек (Муслим 72 карт/стр.3 выше Сатара 53 карт/стр.14 в
        версии без этого множителя - прямой вопрос пользователя
        "у них поменьше слов для заучивания", 18.08.2026, третий заход).
    Все три - log10, не линейно и не деление на пул (та же ошибка, что
    убила score10 на глубоких страницах, см. compute_overall_score) - ни
    один фактор не может задавить остальные два бесконечно.

    page=2 (FIRST_PAGE, минимум для реального студента) даёт наименьший
    возможный множитель глубины (log10(3)=0.48) - это НЕ баг/перекос
    против новичков, это по определению нижняя граница "как далеко можно
    продвинуться меньше некуда" (проверено эмпирически, что log10(page)
    без +1 сделал бы её ЕЩЁ ниже, не выше - альтернатива не годится).

    Итоговое число - НЕ вероятность, только внутренний ключ сортировки, не
    показывается студенту (на экране - accuracy% и n, см.
    core/mufradat_bot.py:_render_leaderboard_text).

    score_dict: wilson (промежуточный, для sort_key), accuracy (%, для
    показа), correct/wrong/n (сырые числа), attempted, page, language (какой
    из языковых треков студента дал этот результат).

    С 26.08.2026 (много языков) - у студента может быть прогресс на
    НЕСКОЛЬКИХ языках (_accuracy_totals разбивает по языку отдельно, именно
    чтобы их не смешивать). Здесь считаем sort_key ОТДЕЛЬНО по каждому языку
    студента и берём ЛУЧШИЙ (максимальный sort_key) как его запись в общем
    рейтинге - решение пользователя 26.08.2026 ("берём его рейтинг выше
    который по конкретному языку"): переключение языка само по себе не может
    поднять место (объём/точность одного языка никогда не приплюсовывается к
    другому), а слабая проба на новом языке никогда не может ПОНИЗИТЬ
    результат (просто не выигрывает max())."""
    totals = _accuracy_totals()
    entries = []
    for uid, by_lang in totals.items():
        best = None
        for lang, t in by_lang.items():
            wilson = _wilson_lower_bound(t["correct"], t["n"])
            accuracy = round(100 * t["correct"] / t["n"], 1) if t["n"] else 0.0
            sort_key = wilson * math.log10(1 + t["attempted"]) * math.log10(1 + t["page"])
            candidate = {
                "wilson": wilson, "accuracy": accuracy,
                "correct": t["correct"], "wrong": t["wrong"], "n": t["n"],
                "attempted": t["attempted"], "page": t["page"], "_sort_key": sort_key,
                "language": lang,
            }
            if best is None or candidate["_sort_key"] > best["_sort_key"]:
                best = candidate
        entries.append((uid, best))
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
# 15 проходилось слишком быстро. Поднято до 40 решением пользователя
# 28.08.2026.
DAILY_WORDS_FOR_TASK_CREDIT = 40


def record_daily_answered_word(user_id, word_id):
    """Отмечает, что студент СЕГОДНЯ отвечал на это слово (не важно,
    верно или нет - "поработал", не "выучил"). Возвращает число РАЗНЫХ
    слов за сегодня после этой записи.

    word_id - progress_key (см. record_answer) - если студент сегодня уже
    отвечал на ту же пару (arabic_text, перевод) на ДРУГОЙ странице, это тот
    же "разный" счётчик не увеличивает (PRIMARY KEY не пускает дубль) - и это
    ожидаемо: технически другая позиция, но по факту то же самое слово."""
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


def get_daily_answered_count(user_id):
    """Только чтение - сколько РАЗНЫХ слов сегодня уже отработано, без
    записи нового ответа (в отличие от record_daily_answered_word). Нужно
    для счётчика "X/40 сегодня" в шапке тренажёра (28.08.2026) - его нужно
    показывать сразу при открытии, до первого ответа в этой сессии."""
    today = _today()
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_DAILY_ANSWERED_SCHEMA)
        count = conn.execute(
            "SELECT COUNT(*) FROM mufradat_daily_answered_words WHERE user_id=? AND date=?",
            (user_id, today)
        ).fetchone()[0]
    return count
