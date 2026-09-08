"""Копилка насых: всё, что бот сочинил, должно оседать в банке.

Смысл копилки — снять ежедневные вызовы ИИ на однотипные тексты (40 в сутки
на два бота только на «скучаем, вернись»). Выдача из банка делается отдельно,
здесь проверяется само накопление.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TELEGRAM_TOKEN", "test")

import pytest

from core import nasiha_bank


@pytest.fixture
def bank(tmp_path, monkeypatch):
    db = tmp_path / "hadiths.db"
    sqlite3.connect(db).close()          # save() пишет только в существующий файл
    monkeypatch.setattr(nasiha_bank, "HADITHS_DB", db)
    return db


def _rows(db):
    with sqlite3.connect(db) as conn:
        try:
            return conn.execute(
                "SELECT kind, profile, lang, gtype, bucket, text, seen_count FROM nasiha_bank"
            ).fetchall()
        except sqlite3.OperationalError:
            return []            # таблицы нет - значит и писать было нечего


def test_saved_text_keeps_meta_and_masks_the_name(bank):
    nasiha_bank.save("absent", "Ассаляму алейкум, брат Имран! Мы скучаем.",
                     lang="ru", bucket="3-5", name="Имран")
    (row,) = _rows(bank)
    assert row[0] == "absent"
    assert row[4] == "3-5"
    assert "{name}" in row[5] and "Имран" not in row[5]
    assert row[6] == 1


def test_same_text_counted_not_duplicated(bank):
    for name in ("Имран", "Хамза"):
        nasiha_bank.save("absent", "Ассаляму алейкум, брат " + name + "! Мы скучаем.",
                         lang="ru", bucket="3-5", name=name)
    rows = _rows(bank)
    assert len(rows) == 1, "текст с подставленным именем один и тот же"
    assert rows[0][6] == 2, "повтор считается, а не плодит строки"


def test_different_buckets_are_different_rows(bank):
    nasiha_bank.save("absent", "Текст {name}", lang="ru", bucket="3-5")
    nasiha_bank.save("absent", "Текст {name}", lang="ru", bucket="11+")
    assert len(_rows(bank)) == 2


def test_empty_text_is_ignored(bank):
    nasiha_bank.save("absent", None, lang="ru")
    nasiha_bank.save("absent", "", lang="ru")
    assert _rows(bank) == []


def test_broken_db_never_breaks_the_send(tmp_path, monkeypatch):
    # Копилка не должна мешать отправке насыхи: сломанный файл - молчим
    broken = tmp_path / "hadiths.db"
    broken.write_text("это не база данных", encoding="utf-8")
    monkeypatch.setattr(nasiha_bank, "HADITHS_DB", broken)
    nasiha_bank.save("absent", "Текст", lang="ru")   # не должно бросить


def test_buckets():
    assert nasiha_bank.days_bucket(3) == "3-5"
    assert nasiha_bank.days_bucket(9) == "6-10"
    assert nasiha_bank.days_bucket(40) == "11+"
    assert nasiha_bank.skips_bucket(8, 10) == "near_limit"
    assert nasiha_bank.skips_bucket(5, 10) == "warning"
