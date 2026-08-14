# -*- coding: utf-8 -*-
"""
Тест детерминированного пост-фильтра для _verify_and_reply (core/handlers.py).

Ловит "фантомные" ошибки муфрадат/хадис-проверки: когда Gemini заявляет
"неверно" / "правильно X", а X после снятия огласовок (харакат/танвин/
шадда/сукун) побуквенно совпадает с исходным словом студента. Хамзу,
алиф/алиф-максуру, та-марбуту НЕ трогаем — это реальные различия, которые
промпт требует проверять по-настоящему (см. discussion 24.07.2026).

Применяется ТОЛЬКО к записям, где checks включает mufradat/hadith (для
нахва огласовка на конце слова — это и есть иъраб-ошибка, снимать нельзя).
"""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Харакат/танвин/шадда/сукун/тatwil/верхний алиф — снимаем.
# Хамзу (ء أ إ ؤ ئ), алиф (ا/آ), та-марбуту (ة/ه), алиф-максуру (ى/ي) НЕ трогаем.
HARAKAT_RE = re.compile(r"[ً-ْـٰ]")
ARABIC_TOKEN_RE = re.compile(r"[؀-ۿ]+")
TRIGGER_WORDS = ["неверно", "неправильно", "правильно", "туура эмес", "туура", "туура эмес"]

# Узкий паттерн "слово - не БУКВА, а БУКВА (слово2)" (id=1, 24.07.2026 discussion).
# НЕ добавляем "не" в общий TRIGGER_WORDS - оно слишком частое в легитимных
# пояснениях ("не к рту", "не фعل المضارع"). Здесь структура жёстко узкая:
# начало строки = слово, потом повтор "не БУКВА, а БУКВА", в конце скобки со
# словом - сравниваем только первое слово и слово в скобках, буквы посередине
# игнорируем (это claim модели, который мы не валидируем).
NE_A_PATTERN = re.compile(
    r"^([؀-ۿ]+)\s*[-–—]\s*"
    r"(?:не\s+[؀-ۿ]+,?\s*а\s+[؀-ۿ]+,?\s*)+"
    r"\(([؀-ۿ]+)\)"
)


def normalize(word):
    # NFC сначала - иначе составная хамза (ؤ, U+0624) и разложенная форма
    # (و + отдельный диакритик хамзы, U+0648 U+0654) считаются разными.
    word = unicodedata.normalize("NFC", word)
    return HARAKAT_RE.sub("", word).strip()


def has_trigger(line):
    low = line.lower()
    return any(t in low for t in TRIGGER_WORDS)


def filter_verdict(verdict):
    """Возвращает (новый_вердикт, список_убранных_блоков_для_ревью)."""
    lines = verdict.split("\n")
    n = len(lines)
    drop = [False] * n
    dropped = []
    i = 0
    while i < n:
        line = lines[i]
        m = NE_A_PATTERN.match(line.strip())
        if m and normalize(m.group(1)) == normalize(m.group(2)):
            drop[i] = True
            dropped.append((line,))
            i += 1
            continue
        toks = ARABIC_TOKEN_RE.findall(line)
        if len(toks) >= 2 and has_trigger(line):
            first, last = toks[0], toks[-1]
            if normalize(first) == normalize(last):
                drop[i] = True
                dropped.append((line,))
            i += 1
            continue
        if len(toks) == 1 and has_trigger(line) and i + 1 < n:
            next_line = lines[i + 1]
            next_toks = ARABIC_TOKEN_RE.findall(next_line)
            if len(next_toks) == 1:
                first, last = toks[0], next_toks[0]
                if normalize(first) == normalize(last):
                    drop[i] = True
                    drop[i + 1] = True
                    dropped.append((line, next_line))
                    i += 2
                    continue
        i += 1
    kept = [l for idx, l in enumerate(lines) if not drop[idx]]
    new_verdict = "\n".join(kept).strip()
    return new_verdict, dropped


def main():
    rows = json.loads((ROOT / "data" / "verify_log_all.json").read_text(encoding="utf-8"))
    total_dropped_claims = 0
    affected_records = 0
    would_become_verno = 0

    for r in rows:
        checks = r["checks"]
        if "mufradat" not in checks and "hadith" not in checks:
            continue
        new_verdict, dropped = filter_verdict(r["verdict"])
        if not dropped:
            continue
        affected_records += 1
        total_dropped_claims += len(dropped)
        clean = new_verdict.strip().rstrip(" ·.").upper()
        becomes_verno = clean == "" or clean == "ВЕРНО"
        if becomes_verno:
            would_become_verno += 1
        print(f"=== id={r['id']} student_id={r['student_id']} date={r['date']} flagged={r['flagged']} ===")
        print("ORIGINAL:")
        print(r["verdict"])
        print("УБРАНО:")
        for block in dropped:
            for l in block:
                print("  - " + l)
        print("НОВЫЙ ВЕРДИКТ:")
        print(new_verdict if new_verdict else "(пусто -> ВЕРНО)")
        print()

    print(f"\nИтого: {len(rows)} записей всего, из них с mufradat/hadith проверено.")
    print(f"Записей с хотя бы одним убранным фантомным пунктом: {affected_records}")
    print(f"Всего убранных фантомных пунктов: {total_dropped_claims}")
    print(f"Из них записей, где после фильтра не осталось ни одной реальной ошибки (стало бы ВЕРНО): {would_become_verno}")


if __name__ == "__main__":
    main()
