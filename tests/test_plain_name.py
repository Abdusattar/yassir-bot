"""Имя, которое видно без ИИ.

Регистрация в группе спрашивает имя и раньше всегда шла за ответом к ИИ.
08.09.2026 у OpenRouter кончились кредиты - и регистрация встала совсем:
студентка написала «Салия» девять раз подряд, каждый раз получая «Напиши
только своё имя». Теперь простое имя распознаётся локально, а ИИ остаётся
для сложных случаев.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TELEGRAM_TOKEN", "test")

from core.db import looks_like_plain_name


def test_simple_names_pass_without_ai():
    for name in ("Салия", "Зульфия", "Имран", "Абдусаттар", "Aisha", "Салия. М."):
        assert looks_like_plain_name(name), name


def test_reports_are_not_names():
    # Ровно то, что студенты пишут в группу каждый день - именем стать не должно
    for text in ("Заучивание 40+40", "Повторил", "1 этап 40/40",
                 "Заучивание Повторение Слова", "Новые слова"):
        assert not looks_like_plain_name(text), text


def test_greeting_is_not_a_name():
    assert not looks_like_plain_name("Ассаляму алейкум")
    assert not looks_like_plain_name("Салам")


def test_too_long_or_too_short_goes_to_ai():
    assert not looks_like_plain_name("")
    assert not looks_like_plain_name("Я")
    assert not looks_like_plain_name("Меня зовут Салия, я из Оша, учусь второй месяц")


def test_digits_never_pass():
    assert not looks_like_plain_name("40 40")
    assert not looks_like_plain_name("Салия 2")
