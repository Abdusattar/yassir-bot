"""Выдача из банка насых (15.09.2026): типовой текст берётся готовым, ИИ не
зовётся; пока шаблонов мало - сочиняется как раньше.

Живые тексты несут числа конкретного студента, поэтому выдаются шаблоны с
подстановками, а числа приходят уже отформатированными («5 дней», «31 балл»).
"""
import asyncio
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TELEGRAM_TOKEN", "test")

import pytest

from core import nasiha_bank
import core.ai as ai


@pytest.fixture
def bank(tmp_path, monkeypatch):
    db = tmp_path / "hadiths.db"
    sqlite3.connect(db).close()
    monkeypatch.setattr(nasiha_bank, "HADITHS_DB", db)
    return db


def _fill(kind, bucket, n, text="Ассаляму алейкум, {name}! Уже {days} без тебя. Возвращайся №%d"):
    for i in range(n):
        nasiha_bank.save(kind, text % i, lang="ru", bucket=bucket, template=True)


def test_pick_ротация_наименее_выданных(bank):
    _fill("absent", "3-5", nasiha_bank.MIN_TEMPLATES)

    got = [nasiha_bank.pick("absent", "ru", bucket="3-5") for _ in range(nasiha_bank.MIN_TEMPLATES)]

    assert len(set(got)) == nasiha_bank.MIN_TEMPLATES, "пока все не выданы по разу, повторов нет"


def test_pick_молчит_пока_шаблонов_мало(bank):
    _fill("absent", "3-5", nasiha_bank.MIN_TEMPLATES - 1)
    assert nasiha_bank.pick("absent", "ru", bucket="3-5") is None


def test_pick_не_путает_корзины_и_живые_тексты(bank):
    _fill("absent", "6-10", nasiha_bank.MIN_TEMPLATES)
    for i in range(nasiha_bank.MIN_TEMPLATES):
        nasiha_bank.save("absent", "живой текст %d" % i, lang="ru", bucket="3-5", name=None)

    assert nasiha_bank.pick("absent", "ru", bucket="3-5") is None, "живые тексты не шаблоны"
    assert nasiha_bank.pick("absent", "ru", bucket="6-10") is not None


def test_render_и_склонения():
    assert nasiha_bank.render("Привет, {name}! {days}, {x}", name="Имран", days="5 дней") == \
        "Привет, Имран! 5 дней, {x}"
    assert nasiha_bank.days_text(1) == "1 день"
    assert nasiha_bank.days_text(3) == "3 дня"
    assert nasiha_bank.days_text(11) == "11 дней"
    assert nasiha_bank.days_text(21) == "21 день"
    assert nasiha_bank.points_text(31) == "31 балл"
    assert nasiha_bank.skips_text(8) == "8 пропусков"


def test_absent_из_банка_без_вызова_ии(bank, monkeypatch):
    _fill("absent", "3-5", nasiha_bank.MIN_TEMPLATES)

    async def boom(*a, **k):
        raise AssertionError("ИИ звать не должны")
    monkeypatch.setattr(ai, "ask_ai", boom)

    text = asyncio.run(ai.absent_motivation("Имран", 4, "ru"))

    assert text.startswith("Ассаляму алейкум, Имран! Уже 4 дня без тебя.")


def test_absent_сочиняет_когда_банк_пуст(bank, monkeypatch):
    calls = []

    async def fake(prompt, **k):
        calls.append(prompt)
        return "Ассаляму алейкум, Имран! Скучаем."
    monkeypatch.setattr(ai, "ask_ai", fake)

    text = asyncio.run(ai.absent_motivation("Имран", 4, "ru"))

    assert calls and text.startswith("Ассаляму алейкум, Имран!")


def test_validate_template():
    assert ai.validate_template("absent", "{name}, уже {days}.")
    assert not ai.validate_template("absent", "{name}, уже 5 дней."), "нет {days}"
    assert not ai.validate_template("absent", "{name}, {days}, {points}"), "чужой плейсхолдер"


def test_generate_template_бракует_и_сохраняет(bank, monkeypatch):
    answers = iter(["Брат {name}, уже 5 дней тишины.", "Брат {name}, уже {days} тишины."])

    async def fake(prompt, **k):
        return next(answers)
    monkeypatch.setattr(ai, "ask_ai", fake)

    assert asyncio.run(ai.generate_template("absent", "3-5", "ru")) is None
    assert asyncio.run(ai.generate_template("absent", "3-5", "ru")) == "Брат {name}, уже {days} тишины."
    assert nasiha_bank.count_templates("absent", "ru", "3-5") == 1


def test_pick_не_отдаёт_тексты_другого_профиля(bank, monkeypatch):
    """Мужской бот не должен получить «сестра»: строки другого профиля для него
    не существуют, даже если их много."""
    monkeypatch.setattr(nasiha_bank, "IS_FEMALE", True)
    _fill("absent", "3-5", nasiha_bank.MIN_TEMPLATES, text="Сестра {name}, уже {days} №%d")
    monkeypatch.setattr(nasiha_bank, "IS_FEMALE", False)

    assert nasiha_bank.pick("absent", "ru", bucket="3-5") is None
    monkeypatch.setattr(nasiha_bank, "IS_FEMALE", True)
    assert nasiha_bank.pick("absent", "ru", bucket="3-5").startswith("Сестра")

