import os
import pytest
import core.db as db_module


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Временная SQLite для каждого теста — изолирована, не трогает prod."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB", db_path)
    db_module.init()
    yield db_path
