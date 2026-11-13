# -*- coding: utf-8 -*-
"""Добавить правки пословного ru в logs/wbw_ru_juz1/changes.json (12.11.2026).
Вход - stdin, строки «2:3:5|новая подпись» (или «2:3:5|новая подпись|почему»). Проверяет, что позиция есть
и что «*» не трогаем. Собрать полный файл подписей: python scripts/wbw_ru_add.py --build"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
# Джуз - переменной WBW_JUZ (по умолчанию 1): папка logs/wbw_ru_juz<N>, аяты - JUZ_KEYS.
import os
JUZ = int(os.environ.get("WBW_JUZ", "1"))
JUZ_KEYS = {1: [f"1:{a}" for a in range(1, 8)] + [f"2:{a}" for a in range(1, 142)],
            2: [f"2:{a}" for a in range(142, 253)],
            3: [f"2:{a}" for a in range(253, 287)] + [f"3:{a}" for a in range(1, 93)],
            4: [f"3:{a}" for a in range(93, 201)] + [f"4:{a}" for a in range(1, 24)],
            5: [f"4:{a}" for a in range(24, 148)]}
D = ROOT / "logs" / f"wbw_ru_juz{JUZ}"; REFS = ROOT / "sources" / "wbw_ru_refs"
D.mkdir(parents=True, exist_ok=True)
CH = D / "changes.json"; NT = D / "notes.json"
ch = json.loads(CH.read_text(encoding="utf-8")) if CH.exists() else {}
nt = json.loads(NT.read_text(encoding="utf-8")) if NT.exists() else {}
def ref(key): return json.loads((REFS / f"{key.replace(':', '_')}.json").read_text(encoding="utf-8"))
if "--build" in sys.argv:
    keys = JUZ_KEYS[JUZ]
    full = {}
    for k in keys:
        full[k] = [ch.get(k, {}).get(str(w["pos"]), w["ru_now"]) for w in ref(k)["words"]]
    (D / "wbw_ru_new.json").write_text(json.dumps(full, ensure_ascii=False, indent=1), encoding="utf-8")
    print("аятов", len(full), "слов", sum(map(len, full.values())), "правок", sum(map(len, ch.values())))
else:
    n = 0
    for line in sys.stdin.read().splitlines():
        if not line.strip(): continue
        parts = line.split("|"); loc, g = parts[0].strip(), parts[1].strip()
        s, a, p = loc.split(":"); key = f"{s}:{a}"
        w = {x["pos"]: x for x in ref(key)["words"]}[int(p)]
        assert w["ru_now"].strip() != "*" and g != "*" and g, loc
        if g == w["ru_now"].strip():
            ch.get(key, {}).pop(p, None); continue
        ch.setdefault(key, {})[p] = g; n += 1
        if len(parts) > 2: nt[loc] = parts[2].strip()
    CH.write_text(json.dumps(ch, ensure_ascii=False, indent=1), encoding="utf-8")
    NT.write_text(json.dumps(nt, ensure_ascii=False, indent=1), encoding="utf-8")
    print("принято", n, "всего правок", sum(map(len, ch.values())))
