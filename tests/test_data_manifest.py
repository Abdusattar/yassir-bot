# -*- coding: utf-8 -*-
"""Единый список отпечатков данных мусхафа (scripts/build_data_manifest.py, architecture.md Р1)."""
import hashlib
import json
import os
import time

from scripts.build_data_manifest import NAME, build, stale
from scripts.monitor import refresh_data_manifest


def _tree(tmp_path):
    d = tmp_path / "mushaf_data"
    (d / "dm").mkdir(parents=True)
    (d / "meaning" / "ru_kuliev").mkdir(parents=True)
    (d / "wbw" / "ru").mkdir(parents=True)
    (d / "page1.json").write_text('{"p":1}', encoding="utf-8")
    (d / "page10.json").write_text('{"p":10}', encoding="utf-8")
    (d / "page2.json").write_text('{"p":2}', encoding="utf-8")
    (d / "page1_ky.json").write_text('{"p":"ky"}', encoding="utf-8")     # языковая копия - мимо
    (d / "manifest.json").write_text('{}', encoding="utf-8")              # значок приложения - мимо
    (d / "dm" / "page1.json").write_text('{"dm":1}', encoding="utf-8")
    (d / "meaning" / "ru_kuliev" / "2.json").write_text('{"t":[]}', encoding="utf-8")
    (d / "wbw" / "ru" / "2.json").write_text('{"w":{}}', encoding="utf-8")
    (d / "wbw" / "manifest.json").write_text('{}', encoding="utf-8")      # старый список - мимо
    return d


def test_sections_and_hashes(tmp_path):
    d = _tree(tmp_path)
    man, changed = build(d)
    assert changed
    assert list(man["page"]) == ["1", "2", "10"]           # по номеру, без _ky и manifest.json
    assert man["page"]["1"] == hashlib.sha1(b'{"p":1}').hexdigest()[:8]
    assert man["dm"] == {"1": hashlib.sha1(b'{"dm":1}').hexdigest()[:8]}
    assert set(man["meaning"]) == {"ru_kuliev"} and set(man["meaning"]["ru_kuliev"]) == {"2"}
    assert man["wbw"] == {"ru": {"2": hashlib.sha1(b'{"w":{}}').hexdigest()[:8]}}
    assert json.loads((d / NAME).read_text(encoding="utf-8")) == man


def test_rebuild_only_on_change(tmp_path):
    d = _tree(tmp_path)
    build(d)
    assert build(d)[1] is False and not stale(d)
    (d / "dm" / "page1.json").write_text('{"dm":"new"}', encoding="utf-8")
    assert stale(d)
    man, changed = build(d)
    assert changed and man["dm"]["1"] == hashlib.sha1(b'{"dm":"new"}').hexdigest()[:8]


def test_monitor_refreshes_stale_manifest(tmp_path):
    d = _tree(tmp_path)
    build(d)
    old = time.time() - 3600
    os.utime(str(d / NAME), (old, old))
    (d / "page2.json").write_text('{"p":"fixed"}', encoding="utf-8")       # лист поправили, список забыли
    assert refresh_data_manifest(d) is None
    man = json.loads((d / NAME).read_text(encoding="utf-8"))
    assert man["page"]["2"] == hashlib.sha1(b'{"p":"fixed"}').hexdigest()[:8]
    # тот же файл переписан без изменений: список не меняется, но отмечается сверенным
    os.utime(str(d / NAME), (old, old))
    assert refresh_data_manifest(d) is None
    assert (d / NAME).stat().st_mtime > old + 1800 and not stale(d)
