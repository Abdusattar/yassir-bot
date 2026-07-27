# -*- coding: utf-8 -*-
"""
Тест детерминированного пост-фильтра strip_quran_confirmed_words
(core/quran_ref.py) на 20 flagged муфрадат-записях за 25-26.07.2026.

Аудит того же дня (см. wiki/ai_verification.md) сверил эти записи вручную
с реальным текстом Корана и нашёл 2 подтверждённых случая, где ИИ
"исправил" студента на несуществующее в Коране слово (id=128 Эмир,
id=137 Абдулатиф). Требование: фильтр должен вычистить именно эти два
случая и не тронуть остальные ~15 настоящих ошибок.
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from core.quran_ref import strip_quran_confirmed_words

ROOT = Path(__file__).resolve().parent.parent

# id -> ожидаемый результат по ручному аудиту 27.07.2026:
#   "fp"  - подтверждённая галлюцинация, фильтр ДОЛЖЕН вычистить строку(и)
#   "tp"  - настоящая ошибка, фильтр НЕ должен ничего убирать
EXPECTED = {
    121: "tp",  # реальная ошибка (والانثى), но verdict эхом даёт 4 верных слова - фильтр может убрать их (бонус)
    124: "tp",
    125: "tp",
    128: "fp",  # وَارْكَعُوا - подтверждено 2:43, بот придумал وَرَكَعُоа
    129: "tp",
    130: "tp",
    131: "fp",  # تقدموا подтверждено (2:110) - Арабский верен, бот там правил только русский
                # перевод (вне области муфрадата) - фильтр корректно сводит к ВЕРНО, бонус-эффект
    133: "tp",
    137: "fp",  # شَيْءٍ/الْكِتَابَ/عَنْهَا - все три подтверждены точным текстом Корана
    138: "tp",
    139: "tp",
    140: "tp",  # هلفهم - реальная ошибка, бот её не поймал (false negative, вне области этого фильтра)
    142: "tp",
    151: "tp",
    152: "tp",
    155: "tp",
    159: "tp",
    162: "tp",  # реальная ошибка (اخيه), но не зона этого фильтра
    163: "tp",
    167: "tp",
}

rows = json.loads((ROOT / "data" / "flagged_mufradat.json").read_text(encoding="utf-8"))

ok = True
for r in rows:
    rid = r["id"]
    new_verdict = strip_quran_confirmed_words(r["verdict"], r["submitted_text"])
    changed = new_verdict.strip() != r["verdict"].strip()
    clean = new_verdict.strip().rstrip(" ·.").upper()
    became_empty = clean in ("", "ВЕРНО")

    exp = EXPECTED.get(rid, "?")
    print(f"=== id={rid} {r['name']} expected={exp} changed={changed} became_empty={became_empty} ===")
    if changed:
        print("ORIGINAL:", repr(r["verdict"]))
        print("FILTERED:", repr(new_verdict))
    if exp == "fp" and not became_empty:
        print(f"  !! ОШИБКА: ожидали, что id={rid} станет пустым/ВЕРНО (ложное срабатывание), но осталось: {new_verdict!r}")
        ok = False
    if exp == "tp" and became_empty:
        print(f"  !! ОШИБКА: id={rid} - настоящая ошибка, а фильтр убрал ВСЁ (стало пусто) - регрессия!")
        ok = False
    print()

print("=" * 60)
print("PASS" if ok else "FAIL")
