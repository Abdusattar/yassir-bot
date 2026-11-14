# -*- coding: utf-8 -*-
"""Логика service worker на макете кэша (14.11.2026, wiki/architecture.md Р1, Р4).

tests/sw/data_files.js - файлы с отпечатком (?h=): из кэша навсегда, одна запись на файл,
без сети - прежняя версия; списки отпечатков - сеть вперёд с отсрочкой в секунду.
tests/sw/fonts.js - предел шрифтов листов: вытесняется давно не открывавшийся.
Каждая проверка печатает строку «OK …» или «FAIL …». Нет node - тест пропускается.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("script,at_least", [("data_files.js", 45), ("fonts.js", 8)])
def test_sw_harness(script, at_least):
    node = shutil.which("node")
    if not node:
        pytest.skip("нет node")
    out = subprocess.run([node, str(ROOT / "tests" / "sw" / script)], cwd=str(ROOT),
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    failed = [l for l in lines if not l.startswith("OK")]
    assert out.returncode == 0 and not failed, "\n".join(failed) + out.stderr
    assert len(lines) >= at_least
