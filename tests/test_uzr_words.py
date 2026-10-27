"""Узр первым словом: кириллица, латиница, китайский 请假 (27.10.2026)."""
from core.handlers import UZR_RE


def _reason(text):
    m = UZR_RE.match(text)
    return m.group(1).strip() if m else None


def test_cyrillic_and_latin():
    assert _reason("Узр, болею") == "болею"
    assert _reason("uzr: kasal") == "kasal"
    assert _reason("узр") == ""


def test_chinese():
    assert _reason("请假，生病了") == "生病了"
    assert _reason("请假生病了") == "生病了"
    assert _reason("请假") == ""


def test_not_an_excuse():
    assert _reason("узрум бар") is None          # отдельное слово, не узр-команда
    assert _reason("1. Заучивание ✔️") is None
