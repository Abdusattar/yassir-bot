"""Фразы бота на китайском (28.10.2026, core/i18n_zh.json)."""
import re
import string

import core.i18n as I

_F = string.Formatter()


def _fields(text):
    return {f for _, f, _, _ in _F.parse(text) if f}


def test_every_phrase_has_chinese_without_extra_placeholders():
    for key, table in I.TR.items():
        zh, ru = table.get("zh"), table.get("ru")
        assert zh, key
        ru = ru if isinstance(ru, str) else ru[0]
        zh = zh if isinstance(zh, str) else zh[0]
        # Лишнее поле сломало бы format() - и бот ушёл бы с сырым {x}.
        assert _fields(zh) <= _fields(ru), key
        assert not re.search("[А-Яа-яЁё]", zh), key


def test_help_and_task_names_in_chinese():
    text = I.help_student(["m", "r", "t", "h"], "prep", "zh", app_only=True)
    assert "圣训" in text and not re.search("[А-Яа-я]", text)
    assert "请假" in text
    assert not re.search("[А-Яа-я]", I.help_admin("zh"))
