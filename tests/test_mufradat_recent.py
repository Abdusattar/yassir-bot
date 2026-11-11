"""Цифры тренажёра слов для студента (11.11.2026).

Повод - Толкун: «вес снизился, а теперь не двигается». Вес 10/10 стоял
рядом с точностью «за всё время» 83%, которая у неё почти не движется
(20 578 ответов). Теперь студент видит «выучено N%» (только полностью
выученные слова, вниз) и точность за последние дни, которая копится с
выкладки и честно называет число дней.
"""

from datetime import date, timedelta

import pytest

import core.mufradat as mufradat


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "hadiths.db")
    monkeypatch.setattr(mufradat, "HADITHS_DB", path)
    # «Мои слова» живут в другой базе - в этих тестах они не нужны.
    monkeypatch.setattr(mufradat, "add_starred_word_by_progress_key", lambda *a: None)
    monkeypatch.setattr(mufradat, "remove_starred_by_progress_key", lambda *a: None)
    return path


def _set_today(monkeypatch, iso):
    monkeypatch.setattr(mufradat, "_today", lambda: iso)


def test_меньше_порога_ответов_точности_нет(db):
    for i in range(mufradat.RECENT_ACCURACY_MIN_ANSWERS - 1):
        mufradat.record_answer("u1", i, True)
    assert mufradat.recent_accuracy("u1") is None


def test_каждый_ответ_считается_и_ошибки_тоже(db):
    for i in range(15):
        mufradat.record_answer("u1", i, True)
    for i in range(5):
        mufradat.record_answer("u1", 100, False)   # одно и то же слово - пять ошибок
    r = mufradat.recent_accuracy("u1")
    assert r == {"accuracy": 75, "correct": 15, "n": 20, "days": 1}


def test_точность_округляется_вниз(db):
    for i in range(199):
        mufradat.record_answer("u1", i, True)
    mufradat.record_answer("u1", 999, False)
    assert mufradat.recent_accuracy("u1")["accuracy"] == 99, "99.5% - не 100%"


def test_окно_честно_называет_дни_и_забывает_старое(db, monkeypatch):
    today = date.fromisoformat(mufradat._today())
    _set_today(monkeypatch, (today - timedelta(days=40)).isoformat())
    for i in range(30):
        mufradat.record_answer("u1", i, False)           # старые ошибки, вне окна
    _set_today(monkeypatch, (today - timedelta(days=4)).isoformat())
    for i in range(20):
        mufradat.record_answer("u1", i, True)
    _set_today(monkeypatch, today.isoformat())
    for i in range(5):
        mufradat.record_answer("u1", i, True)

    r = mufradat.recent_accuracy("u1")
    assert r["n"] == 25 and r["accuracy"] == 100, "ошибки 40-дневной давности не тянут вниз"
    assert r["days"] == 5, "окно с первого дня внутри 30, а не «30 дней»"


def test_окно_не_больше_тридцати_дней(db, monkeypatch):
    today = date.fromisoformat(mufradat._today())
    _set_today(monkeypatch, (today - timedelta(days=29)).isoformat())
    for i in range(20):
        mufradat.record_answer("u1", i, True)
    _set_today(monkeypatch, today.isoformat())
    assert mufradat.recent_accuracy("u1")["days"] == 30


def test_ответы_разных_студентов_не_смешиваются(db):
    for i in range(20):
        mufradat.record_answer("u1", i, True)
        mufradat.record_answer("u2", i, False)
    assert mufradat.recent_accuracy("u1")["accuracy"] == 100
    assert mufradat.recent_accuracy("u2")["accuracy"] == 0


def test_процент_выученного_только_по_полностью_выученным(db, monkeypatch):
    words = [{"progress_key": k} for k in range(3)]
    monkeypatch.setattr(mufradat, "_slice_info", lambda ws: {"static": ws})
    progress = {
        0: {"correct_streak": mufradat.MASTERY_STREAK},
        1: {"correct_streak": mufradat.MASTERY_STREAK},
        2: {"correct_streak": mufradat.MASTERY_STREAK - 1},  # почти, но не выучено
    }
    s = mufradat.compute_overall_score("u1", words=words, progress=progress)
    assert s["mastered"] == 2 and s["percent"] == 66, "2 из 3 - 66%, не 67% и не 89%"

    progress[2] = {"correct_streak": mufradat.MASTERY_STREAK}
    s = mufradat.compute_overall_score("u1", words=words, progress=progress)
    assert s["percent"] == 100
