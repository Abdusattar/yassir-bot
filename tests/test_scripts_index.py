# -*- coding: utf-8 -*-
"""Указатель скриптов не отстаёт от scripts/ (scripts/build_scripts_index.py, architecture.md С4)."""
from scripts.build_scripts_index import OUT, ROOT, first_line


def test_every_script_is_described_and_listed():
    text = OUT.read_text(encoding="utf-8")
    for f in sorted((ROOT / "scripts").glob("*.py")):
        assert first_line(f), "%s: нет описания в начале файла" % f.name
        assert "| `%s` |" % f.name in text, \
            "%s нет в указателе: python scripts/build_scripts_index.py" % f.name
