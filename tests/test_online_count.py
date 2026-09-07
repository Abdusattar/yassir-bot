# -*- coding: utf-8 -*-
"""«Сейчас в онлайне» — одна цифра на оба бота (07.09.2026).

Джамаат один, поэтому мужской бот прибавляет к своим тем, кто сейчас держит
приложение в женском, и наоборот. Общей памяти у процессов нет: каждый
выкладывает своё число файлом в общий каталог.
"""
import json
import time

import pytest

from core import mufradat_api as api


@pytest.fixture
def share(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_ONLINE_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_online_written", 0.0)
    api._last_seen.clear()
    return tmp_path


def _pair(share, profile, n, age=0):
    (share / ("online_%s.json" % profile)).write_text(
        json.dumps({"n": n, "ts": time.time() - age}), encoding="utf-8")


def test_свои_и_соседние_складываются(share):
    api._last_seen.update({1: time.time(), 2: time.time()})
    _pair(share, "female", 3)
    assert api._online_count() == 5


def test_молчащий_сосед_это_ноль(share):
    api._last_seen[1] = time.time()
    _pair(share, "female", 4, age=api.ONLINE_SHARE_STALE + 5)
    assert api._online_count() == 1


def test_без_файла_соседа_считаем_только_своих(share):
    api._last_seen[1] = time.time()
    assert api._online_count() == 1


def test_своё_число_выкладывается_для_соседа(share):
    api._last_seen.update({1: time.time(), 2: time.time()})
    api._online_count()
    data = json.loads((share / "online_male.json").read_text(encoding="utf-8"))
    assert data["n"] == 2


def test_просроченные_свои_отваливаются(share):
    api._last_seen.update({1: time.time(), 2: time.time() - api.ONLINE_WINDOW_SECONDS - 5})
    assert api._online_count() == 1
