"""Выбор цели вопроса в тренажёре муфрадата.

Главное, что здесь проверяется (04.09.2026, жалоба студента на 15-й
странице): "звёздная квота" - каждый STARRED_QUESTION_QUOTA-й вопрос,
который обязан брать цель из "Моих слов", - НЕ имеет права объявить
исчерпанной всю закладку. Раньше при пустой (после фильтров) звёздной
выборке generate_question возвращал None, и оба транспорта показывали
"Слова на твоей закладке пока закончились. Сдвинь страницу дальше." при
полном основном пуле из 1000+ слов.

Функция чистая (в БД не ходит), поэтому фикстуры баз здесь не нужны.
"""

import core.mufradat as mufradat
from core.mufradat import (
    COVERAGE_WAVE_SHARE, MASTERY_STREAK, generate_question, pick_question_word,
)


def _word(i, arabic, translation):
    """Форма строки из get_words_in_range: прогресс всегда по progress_key,
    не по id конкретной строки (см. pick_question_word)."""
    return {
        "id": i,
        "progress_key": i,
        "arabic_text": arabic,
        "translation": translation,
    }


def _pool(n=12):
    return [_word(i, "كلمة%d" % i, "перевод%d" % i) for i in range(1, n + 1)]


def _mastered(progress_key, today="2026-09-04"):
    """Слово "выучено" и ещё не ушло на перепроверку (RECHECK_AFTER_DAYS) -
    pick_question_word выбрасывает такое из кандидатов совсем."""
    return {progress_key: {
        "correct_streak": MASTERY_STREAK,
        "wrong_count": 0,
        "correct_count": MASTERY_STREAK,
        "last_correct_date": today,
    }}


def test_starred_pool_without_target_falls_back_to_main_pool():
    """Всё, что есть в "Моих словах", уже выучено - вопрос всё равно должен
    задаться, из обычного пула."""
    words = _pool()
    starred = [_word(99, "مرصود", "звёздный")]
    progress = _mastered(99)

    q = generate_question(words, progress, starred_words=starred)

    assert q is not None
    assert q["word"]["id"] != 99
    assert q["word"]["translation"] in q["options"]


def test_starred_target_still_wins_when_available():
    """Откат не должен обесценить саму квоту: пока в "Моих словах" есть
    годная цель, вопрос берётся именно оттуда."""
    words = _pool()
    starred = [_word(99, "مرصود", "звёздный")]

    for _ in range(20):
        q = generate_question(words, {}, starred_words=starred)
        assert q is not None
        assert q["word"]["id"] == 99


def test_all_mastered_asks_oldest_learned_instead_of_dead_end():
    """19.10.2026, Динара (стр. 12): закреплены все годные слова до её
    страницы - раньше None и «сдвинь страницу дальше». Теперь вопрос из
    отдыхающих слов, только из самых давно спрошенных, с пометкой review."""
    words = _pool(40)
    progress = {}
    for w in words:
        k = w["progress_key"]
        progress.update(_mastered(k, "2026-10-%02d" % (19 - k % 10)))
    starred = [_word(99, "مرصود", "звёздный")]
    progress.update(_mastered(99))

    oldest = {k for k, row in progress.items() if row["last_correct_date"] <= "2026-10-12"}
    for _ in range(50):
        q = generate_question(words, progress, starred_words=starred)
        assert q is not None and q["review"] is True
        assert q["word"]["progress_key"] in oldest or len(oldest) < mufradat.REVIEW_OLDEST


def test_review_takes_oldest_first():
    words = _pool(mufradat.REVIEW_OLDEST + 10)
    progress = {}
    for w in words:
        k = w["progress_key"]
        # 10 самых свежих - сентябрь→октябрь по номеру, старшие - меньшие номера
        progress.update(_mastered(k, "2026-09-%02d" % min(28, k) if k <= 28 else "2026-10-%02d" % (k - 28)))
    picked = {k["progress_key"] for k in mufradat._review_candidates(words, progress, None, mufradat._stale_cutoff())}
    assert picked == set(range(1, mufradat.REVIEW_OLDEST + 1))


def test_not_review_when_new_words_left():
    words = _pool()
    progress = _mastered(1)
    q = generate_question(words, progress)
    assert q["review"] is False


def test_none_only_when_pool_is_empty():
    assert generate_question([], {}) is None


# ── Три корзины выбора цели (04.09.2026, см. CONSOLIDATION_SHARE) ──────────


def _started(progress_key, streak=1, shown=1):
    """Слово начато и не доведено - корзина закрепления."""
    return {progress_key: {
        "correct_streak": streak,
        "wrong_count": 0,
        "correct_count": shown,
        "last_correct_date": "2026-09-04",
    }}


def _fixed_roll(monkeypatch, value):
    """random.random() решает, из какой корзины берём цель."""
    monkeypatch.setattr(mufradat.random, "random", lambda: value)


def test_consolidation_bucket_picks_started_word(monkeypatch):
    """В своей доле вопрос идёт по НЕДОВЕДЁННОМУ слову, а не по новому -
    иначе "закреплено" стоит на месте (жалоба студента)."""
    words = _pool()
    progress = _started(words[0]["progress_key"])
    _fixed_roll(monkeypatch, COVERAGE_WAVE_SHARE + 0.01)

    for _ in range(20):
        assert pick_question_word(words, progress)["progress_key"] == words[0]["progress_key"]


def test_consolidation_bucket_empty_falls_back_to_wave(monkeypatch):
    """У новичка недоведённых слов нет - доля закрепления должна уходить
    волне, а не ронять выбор."""
    words = _pool()
    _fixed_roll(monkeypatch, COVERAGE_WAVE_SHARE + 0.01)

    assert pick_question_word(words, {}) is not None


def test_wave_share_still_picks_least_shown(monkeypatch):
    """Волна на месте: в своей доле берётся ни разу не показанное слово."""
    words = _pool()
    progress = {}
    for w in words[:-1]:
        progress.update(_started(w["progress_key"], streak=1, shown=3))
    _fixed_roll(monkeypatch, 0.0)

    for _ in range(20):
        assert pick_question_word(words, progress)["progress_key"] == words[-1]["progress_key"]


def test_другой_перевод_того_же_слова_не_идёт_в_варианты():
    """Пословный источник идёт за связным переводом, поэтому у служебных слов
    десятки контекстных значений (у «من» - 501). Если такое значение попадёт
    в варианты рядом с верным, оба будут правильными для показанного слова, а
    засчитан будет один (07.09.2026, разбор со скриншотами пользователя).

    Цель и порядок вариантов выбираются случайно, поэтому проверяем инвариант
    на серии вопросов: ОБА перевода одного слова не встречаются никогда."""
    pair = ["и он", "в то время как оно"]
    pool = [
        {"id": 1, "progress_key": 1, "arabic_text": "وَهُوَ", "translation": pair[0]},
        {"id": 2, "progress_key": 2, "arabic_text": "وَهُوَ", "translation": pair[1]},
    ] + [
        {"id": i, "progress_key": i, "arabic_text": "كلمة%d" % i, "translation": "перевод%d" % i}
        for i in range(3, 9)
    ]

    asked = 0
    for _ in range(60):
        q = generate_question(pool, {}, n_options=4)
        assert q is not None
        # Проверять есть что только когда спросили само «وَهُوَ»: два его
        # перевода среди вариантов к ДРУГОМУ слову - обычные дистракторы,
        # ни один из них к показанному слову не подходит.
        if q["word"]["arabic_text"] == "وَهُوَ":
            asked += 1
            assert len(set(pair) & set(q["options"])) == 1
    assert asked, "цель ни разу не выпала - проверять было нечего"


def test_варианты_различаются_по_смыслу():
    """Старое правило (одинаковый перевод не дублируется) продолжает
    действовать - проверка на «то же слово» его не заменяет."""
    pool = _pool(10)
    pool[1] = {**pool[1], "translation": pool[0]["translation"]}
    q = generate_question(pool, {}, n_options=4)

    assert q is not None
    assert len(set(q["options"])) == len(q["options"])


def test_вопрос_несёт_точное_место_слова(monkeypatch):
    """22.09.2026: тренажёр показывает строку мусхафа со словом - для этого
    вопрос отдаёт суру, аят и позицию слова. Старый вопрос из памяти (до
    выкладки, без позиции) не падает: позиция просто None."""
    import core.mufradat_api as api
    monkeypatch.setattr(api, "get_current_page", lambda uid: 3)
    monkeypatch.setattr(api, "page_for_ayah", lambda s, a: 3)
    monkeypatch.setattr(api, "_daily_fields", lambda uid, st=None: {})
    state = {"arabic": "أَلِيمٌ", "options": ["a", "b"], "word_id": 7,
             "surah": 2, "ayah": 10, "position": 3}
    p = api._question_payload(1, state, None)
    assert (p["word_surah"], p["word_ayah"], p["word_pos"], p["word_page"]) == (2, 10, 3, 3)
    del state["position"]
    assert api._question_payload(1, state, None)["word_pos"] is None


def test_review_reaches_forty_distinct_words_in_a_day():
    """Задание «Слова» - 40 разных за день: повтор не должен крутиться на 30."""
    words = _pool(100)
    progress = {}
    for w in words:
        progress.update(_mastered(w["progress_key"], "2026-10-%02d" % (1 + w["progress_key"] % 18)))
    today = set()
    for _ in range(40):
        q = generate_question(words, progress, exclude_keys=today)
        assert q["review"] is True
        today.add(q["word"]["progress_key"])
    assert len(today) == 40


def test_review_all_done_today_still_asks():
    words = _pool(12)
    progress = {}
    for w in words:
        progress.update(_mastered(w["progress_key"], "2026-10-10"))
    q = generate_question(words, progress, exclude_keys={w["progress_key"] for w in words})
    assert q is not None and q["review"] is True
