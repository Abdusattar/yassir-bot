import os
import shutil

import pytest
import core.db as db_module
import core.sampler as sampler_module
import core.mushaf_words as mushaf_words_module


@pytest.fixture(scope="session")
def _db_template(tmp_path_factory):
    """Схема, построенная ОДИН раз за прогон.

    `db.init()` идёт 0,79 секунды: это весь executescript плюс миграции. На
    497 тестах выходило шесть с половиной минут чистого ожидания, притом что
    схема у всех одна и та же (замер 20.09.2026). Дальше каждый тест просто
    копирует файл."""
    path = str(tmp_path_factory.mktemp("db-template") / "template.db")
    was = db_module.DB
    db_module.DB = path
    try:
        db_module.init()
    finally:
        db_module.DB = was
    return path


@pytest.fixture
def fresh_db(_db_template):
    """Готовая схема в любой файл — для тестов, которые заводят свою базу
    руками (второй бот, пульс, отправка сдач). Тот же шаблон, та же копия
    вместо db.init()."""
    def make(path):
        shutil.copyfile(_db_template, str(path))
        return str(path)
    return make


@pytest.fixture
def test_db(tmp_path, monkeypatch, _db_template):
    """Временная SQLite для каждого теста — изолирована, не трогает prod."""
    db_path = str(tmp_path / "test.db")
    shutil.copyfile(_db_template, db_path)
    monkeypatch.setattr(db_module, "DB", db_path)
    yield db_path


@pytest.fixture
def test_hadiths_db(tmp_path, monkeypatch):
    """Вторая база проекта (sources/hadiths.db): в ней живут тренажёр
    муфрадата, «Мои слова» и указатель 40+40 (core/mushaf_words.py).

    Нужна отдельным фикстурой, потому что на машине разработчика этот файл
    ЕСТЬ, а в раннере GitHub Actions его нет вовсе — тест, трогающий её без
    подмены, проходит локально и роняет деплой (поймано 02.09.2026).
    Модули берут путь через `from core.sampler import HADITHS_DB`, то есть
    держат свою ссылку — патчим и источник, и потребителя."""
    path = str(tmp_path / "hadiths.db")
    monkeypatch.setattr(sampler_module, "HADITHS_DB", path)
    monkeypatch.setattr(mushaf_words_module, "HADITHS_DB", path)
    yield path


@pytest.fixture(autouse=True)
def _no_audio_probe(monkeypatch):
    """Тесты подают ненастоящий звук (b"OGG:...") - длину не меряем, иначе
    проверка «запись дошла не целиком» (17.09.2026) сочтёт его пустым.
    Тесты самой проверки подменяют audio_seconds поверх."""
    import core.mufradat_bot as mb

    async def no_seconds(data):
        return None
    monkeypatch.setattr(mb, "audio_seconds", no_seconds)
    monkeypatch.setattr(mb, "_probe_ok", False)


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch):
    """Паузы между обращениями к Telegram (core/tg.py: pace) в тестах не
    ждём. В бою они берегут лимиты Bot API - рассылка без передышки ловит
    429; в прогоне это были минуты пустого ожидания, а у kick_unregistered -
    десять секунд на каждого."""
    import core.tg as tg_module
    monkeypatch.setattr(tg_module, "PACING", False)
