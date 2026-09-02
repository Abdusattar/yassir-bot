import os
import pytest
import core.db as db_module
import core.sampler as sampler_module
import core.mushaf_words as mushaf_words_module


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Временная SQLite для каждого теста — изолирована, не трогает prod."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB", db_path)
    db_module.init()
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
