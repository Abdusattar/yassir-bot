"""Китайский пословный перевод (20.10.2026, scripts/load_wbw_zh.py)."""
import json
import os

from core.mufradat import _is_junk

WBW = os.path.join(os.path.dirname(__file__), "..", "i18n", "wbw_zh.json")


def test_chinese_gloss_is_not_junk():
    # Фильтр «перевод без букв» знал только кириллицу и латиницу - тренажёр
    # на zh выходил пустым.
    assert not _is_junk("安拉")
    assert not _is_junk("至仁的")
    assert _is_junk("：")


def test_wbw_file_has_no_empty_glosses():
    with open(WBW, encoding="utf-8") as f:
        data = json.load(f)
    bad = [k for k, gl in data.items() for g in gl if not g.strip()]
    assert bad == []
    # «*» - только хвост склейки, не первое слово аята
    assert [k for k, gl in data.items() if gl[0] == "*"] == []
