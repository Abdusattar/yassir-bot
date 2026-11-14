# -*- coding: utf-8 -*-
"""sw.js должен разбираться браузером (14.11.2026).

С 02.11 по 14.11 на проде стоял sw.js с «meaning/*/*.json» в /* комментарии: «*/»
закрывал комментарий, файл не разбирался, новый service worker не ставился ни у кого.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

SW = Path(__file__).resolve().parent.parent / "mushaf_data" / "sw.js"


@pytest.mark.skipif(not shutil.which("node"), reason="нет node")
def test_sw_parses():
    r = subprocess.run(["node", "--check", str(SW)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
