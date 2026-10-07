"""Просьба написать имя (07.10.2026): в подготовительной сдавал «Неизвестный»."""
import pytest

import core.db as db
from core.db import name_needs_fix


@pytest.mark.parametrize("name", ["", None, "Неизвестный", "unknown", "User", "🙂", "123", "@abc_12", "-", "ok"])
def test_not_a_name(name):
    assert name_needs_fix(name) is True


@pytest.mark.parametrize("name", ["Амин", "Абу Самийя", "Rayana Myrzakadyrova .", "Умм Ахмад", "Салия. М.", "زُبَيْر", "Абади Хабиби"])
def test_real_names_pass(name):
    assert name_needs_fix(name) is False


def test_profile_rejects_non_name(test_db):
    g_chat = "-100901"
    db.save_group(g_chat, "N-1", tasks="m,r,t")
    sid = db.add_student("Неизвестный", db.get_group(g_chat)["id"], phone="777")
    with pytest.raises(ValueError, match="name_not_name"):
        db.update_profile("777", name="unknown")
    db.update_profile("777", name="Мухаммад")
    assert db.find_user_by_phone("777")["name"] == "Мухаммад"
