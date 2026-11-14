# -*- coding: utf-8 -*-
"""Файлы пословного ru (i18n/wbw_ru) - только подписи, без рабочих пометок (14.11.2026).

14.11 в подпись 2:93:23 уехала пометка из списка правок («этому  (подпись выдумана…)») и
дошла до прода. Скобки, двойные пробелы, «->» и подписи длиннее 40 знаков в файл не проходят.
"""
import json
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "i18n" / "wbw_ru"
BAD = re.compile(r"[()\[\]]|  |->|досл\.")


def test_captions_are_clean():
    bad = []
    for f in sorted(DIR.glob("juz*.json")):
        for key, caps in json.loads(f.read_text(encoding="utf-8")).items():
            for p, c in enumerate(caps, 1):
                if BAD.search(c) or len(c) > 40 or c != c.strip():
                    bad.append("%s %s:%d %r" % (f.name, key, p, c))
    assert not bad, bad[:10]
