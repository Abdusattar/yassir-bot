"""Деление студентов на 5 частей для фильтра этапа 3 (11.11.2026).

Почему так. Пометки Умар устаза есть у 40 студентов, а пятеро держат 54%
всех пометок. Один отложенный кусок шаток: попал крупный студент в проверку
или нет - число прыгает. Поэтому проверяем по кругу: каждая часть по очереди
служит проверкой, фильтр учится на остальных четырёх. Студент целиком в
одной части - модель не видит его голос до проверки.

Раскладка жадная: студенты по числу пометок (больше - раньше) кладутся в
часть, где пометок пока меньше всего; при равенстве - где меньше сдач.
Детерминирована: тот же набор сдач - те же части.

В файл идут только student_id (внутренний номер в базе), не имена:
репозиторий публичный.

    python scripts/make_folds.py              # data/stage3_folds.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "umar_corpus"
RESULTS = ROOT / "data" / "hifz_eval_results_stage2_dedup.jsonl"
OUT = ROOT / "data" / "stage3_folds.json"
K = 5


def main():
    by_student = {}
    for line in RESULTS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        meta = json.loads((CORPUS / str(r["id"]) / "meta.json").read_text(encoding="utf-8"))
        s = by_student.setdefault(meta["student_id"], {"subs": 0, "marks": 0})
        s["subs"] += 1
        s["marks"] += len(r["marks"])

    folds = [{"students": [], "subs": 0, "marks": 0} for _ in range(K)]
    for sid, s in sorted(by_student.items(), key=lambda kv: (-kv[1]["marks"], -kv[1]["subs"], kv[0])):
        f = min(folds, key=lambda f: (f["marks"], f["subs"]))
        f["students"].append(sid)
        f["subs"] += s["subs"]
        f["marks"] += s["marks"]

    OUT.write_text(json.dumps({
        "made": "2026-11-11",
        "source": RESULTS.name,
        "k": K,
        "folds": [{"students": sorted(f["students"]), "subs": f["subs"], "marks": f["marks"]} for f in folds],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    for i, f in enumerate(folds):
        print(f"часть {i}: студентов {len(f['students'])}, сдач {f['subs']}, пометок {f['marks']}")


if __name__ == "__main__":
    main()
