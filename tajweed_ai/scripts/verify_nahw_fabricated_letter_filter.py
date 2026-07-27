# -*- coding: utf-8 -*-
"""
Тест детерминированного пост-фильтра _strip_nahw_fabricated_letters
(core/handlers.py) на всех 22 nahw-записях за 2 недели (см.
tajweed_ai/data/nahw_2weeks.json).

27.07.2026: проверка git-истории (см. project memory) показала, что
"لям джарр" (eba052e) и точное само-противоречие "X — вместо X" (185ca91)
уже почищены раньше. Единственная подтверждённая живая дыра - id=39:
модель заявляет "не должно быть X" про букву X, которой в слове студента
физически нет (عَيْнًا - никакого ح там нет, مَشْرَبَهُمْ - никакой ة там
нет). Требование: новый фильтр должен убрать именно эти 2 строки в id=39
и не тронуть НИ ОДНОЙ строки в остальных 21 записях, включая id=85, где
претензия "قالوأ — لишняя буква ا" - настоящая (ا реально есть в слове,
просто заявлена как лишняя) и должна выжить.
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from core.handlers import _strip_nahw_exact_phantoms, _strip_nahw_fabricated_letters

ROOT = Path(__file__).resolve().parent.parent
with open(ROOT / "data" / "nahw_2weeks.json", encoding="utf-8") as f:
    records = json.load(f)

# id -> ожидаемые строки, которые новый фильтр должен убрать (по подстроке)
EXPECTED_DROPS = {
    39: [
        "не должно быть на конце ح",
        "не должно быть на конце ة",
    ],
}

ok = True
for rec in records:
    rid = rec["id"]
    verdict = rec["verdict"]
    after_exact = _strip_nahw_exact_phantoms(verdict)
    after_fab = _strip_nahw_fabricated_letters(after_exact) or "ВЕРНО"

    before_lines = set(after_exact.split("\n"))
    after_lines = set(after_fab.split("\n"))
    dropped = before_lines - after_lines

    expected_substrings = EXPECTED_DROPS.get(rid, [])
    dropped_text = "\n".join(dropped)

    if rid in EXPECTED_DROPS:
        missing = [s for s in expected_substrings if s not in dropped_text]
        extra_drop = len(dropped) != len(expected_substrings)
        status = "OK" if not missing and not extra_drop else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"=== id={rid} {rec['name']} EXPECTED DROP status={status} ===")
        print("dropped:", dropped)
        if missing:
            print("MISSING:", missing)
    else:
        if dropped:
            ok = False
            print(f"=== id={rid} {rec['name']} UNEXPECTED DROP - FAIL ===")
            print("dropped:", dropped)

print("\n" + "=" * 60)
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
