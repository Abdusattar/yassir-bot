"""Продолжение прерванной записи не принимается за потерянный хвост (23.09.2026).

Азиля (группа Мохидиль) начитала утром 4:46, вечером продолжила и дочитала:
на таймере 548 с, в плеере - только вечерний поток, 267 с. Проверка перед
отправкой (recLostTail в mushaf_data/index.html) сравнивала плеер со всем
таймером и 60 раз подряд говорила «запись не целиком». Правильно - сравнивать
плеер с тем, что записано в текущем потоке (recSegMs).

Функции берутся прямо из index.html и гоняются в node - без node пропускаем.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="нужен node")

HTML = os.path.join(os.path.dirname(__file__), "..", "mushaf_data", "index.html")


def _fn(src, name):
    m = re.search(r"function %s\(.*?\n  \}\n" % name, src, re.S)
    assert m, name
    return m.group(0)


def _run(expr):
    with open(HTML, encoding="utf-8") as f:
        src = f.read()
    js = _fn(src, "recLostTail") + _fn(src, "recSegMs") + \
        "console.log(JSON.stringify(%s));" % expr
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_resumed_record_of_azila_goes_through():
    # Утром начитано ~256 с, вечерний поток 267 с по плееру, таймер 548 с.
    assert _run("recLostTail(267, recSegMs(548000, 256000))") is False


def test_old_comparison_was_the_bug():
    assert _run("recLostTail(267, recSegMs(548000, 0))") is True


def test_real_lost_tail_in_resumed_stream_still_caught():
    # Вечерний поток должен быть 290 с, а в плеере 100 - хвост потерян.
    assert _run("recLostTail(100, recSegMs(546000, 256000))") is True


def test_fresh_record_unchanged():
    assert _run("recLostTail(446, recSegMs(446000, undefined))") is False
    assert _run("recLostTail(200, recSegMs(446000, 0))") is True
