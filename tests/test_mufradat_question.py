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

from core.mufradat import MASTERY_STREAK, generate_question


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


def test_none_only_when_main_pool_is_exhausted():
    """None остаётся сигналом "двигай страницу" - но ровно тогда, когда
    выучен сам основной пул, а не звёздная выборка."""
    words = _pool()
    progress = {}
    for w in words:
        progress.update(_mastered(w["progress_key"]))
    starred = [_word(99, "مرصود", "звёздный")]
    progress.update(_mastered(99))

    assert generate_question(words, progress, starred_words=starred) is None
