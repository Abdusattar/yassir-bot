# -*- coding: utf-8 -*-
"""
Тест find_unconfirmed_words (core/quran_ref.py) - обратная проверка:
находит слова студента, которых НЕТ в тексте Корана, но которые
однозначно близки (1 буква) к ровно одному реальному слову.

История (27.07.2026):
- Advisor: порог длины >=4 буквы, однозначность кандидата, мягкая
  формулировка вместо "исправления".
- Первый прогон precision-теста (0 срабатываний на 16 flagged=0 записях)
  нашёл 3 "срабатывания". Ручная проверка по реальному тексту Корана
  показала: 2 из 3 - НЕ ложные тревоги, а ещё два реальных пропуска ИИ
  (id=126 Юсуф, id=150 Сатар), плюс баг нормализации (ٱ vs ا, исправлен).
- Пользователь (Сатар - это его собственная запись id=150) объяснил: на
  телефоне нет клавиши "алиф с хамзой". Проверено поиском - подтверждено
  (arabictyping101.com/en/guide/arabic-101-keyboard): именно أ/إ/آ
  (хамза НА алифе) требуют Shift/долгое нажатие, в отличие от ة/ى/ؤ/ئ/ء
  (те на основном слое клавиатуры). Три из четырёх изначальных находок
  (id=162, id=126, id=150) - все ровно эта замена. Добавлено исключение
  _is_alif_hamza_only_diff - теперь эти три НЕ флагаются.

Критерии этого теста:
1. Recall: должна сработать на реальной ошибке, НЕ связанной с
   алиф-хамзой (Бекхан id=140 هلفهم -> خلفهم, разные буквы).
2. Клавиатурное исключение: id=162, id=126, id=150 (все три - алиф вместо
   алифа-с-хамзой) НЕ должны флагироваться.
3. Precision: ноль ЛЮБЫХ других срабатываний на 16 flagged=0 записях.
4. Слова, которые уже вычищает strip_quran_confirmed_words (точное
   совпадение с Кораном), не должны попадать в unconfirmed.
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from core.quran_ref import find_unconfirmed_words, _QURAN_INDEX, _normalize, _ARABIC_TOKEN_RE

ROOT = Path(__file__).resolve().parent.parent
rows = json.loads((ROOT / "data" / "all_mufradat_36.json").read_text(encoding="utf-8"))

MUST_FIND = {
    140: "هلفهم",  # Бекхан - должно найти خلфهم (разные буквы, не про клавиатуру)
}

MUST_NOT_FIND = {
    162: "اخيه",  # Абдульвахид - алиф-хамза, теперь клавиатурное исключение
    126: "فاخذتكم",  # Юсуф - тоже алиф-хамза
    150: "اقررتم",  # Сатар - тоже алиф-хамза
}

ok = True

print("=== 1. RECALL: реальная ошибка (не алиф-хамза) должна найтись ===")
for rid, expect_tok in MUST_FIND.items():
    row = next(r for r in rows if r["id"] == rid)
    findings = find_unconfirmed_words(row["submitted_text"])
    found_toks = [f[0] for f in findings]
    hit = expect_tok in found_toks
    print(f"id={rid} {row['name']}: findings={findings} -> {'OK' if hit else 'MISS'}")
    if not hit:
        ok = False

print("\n=== 2. Клавиатурное исключение: алиф-хамза случаи НЕ должны флагироваться ===")
for rid, tok in MUST_NOT_FIND.items():
    row = next(r for r in rows if r["id"] == rid)
    findings = find_unconfirmed_words(row["submitted_text"])
    found_toks = [f[0] for f in findings]
    still_found = tok in found_toks
    print(f"id={rid} {row['name']}: findings={findings} -> {'FAIL (всё ещё флагает)' if still_found else 'OK (исключено)'}")
    if still_found:
        ok = False

print("\n=== 3. PRECISION: ноль срабатываний на 16 flagged=0 записях ===")
false_alarms = 0
for r in rows:
    if r["flagged"]:
        continue
    findings = find_unconfirmed_words(r["submitted_text"])
    if findings:
        false_alarms += len(findings)
        print(f"  !! ЛОЖНАЯ ТРЕВОГА id={r['id']} {r['name']}: {findings}")
        print(f"     текст: {r['submitted_text']!r}")
if false_alarms == 0:
    print("OK - ноль срабатываний на 16 flagged=0 записях")
else:
    print(f"FAIL - {false_alarms} срабатываний")
    ok = False

print("\n=== 4. Слова, подтверждённые strip_quran_confirmed_words, не должны попадать в unconfirmed ===")
overlap_errors = 0
for r in rows:
    tokens = _ARABIC_TOKEN_RE.findall(r["submitted_text"])
    exact_hits = {_normalize(t) for t in tokens if _normalize(t) in _QURAN_INDEX}
    findings = find_unconfirmed_words(r["submitted_text"])
    for tok, _ in findings:
        if _normalize(tok) in exact_hits:
            print(f"  !! ПЕРЕСЕЧЕНИЕ id={r['id']}: {tok} одновременно и точное совпадение, и unconfirmed")
            overlap_errors += 1
if overlap_errors == 0:
    print("OK - пересечений нет")
else:
    ok = False

print("\n" + "=" * 60)
print("PASS" if ok else "FAIL")
