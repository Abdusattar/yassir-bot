# -*- coding: utf-8 -*-
"""Подмена русских подписей слов в готовых страницах мусхафа (12.11.2026).

Подписи для тапа по слову вшиты в mushaf_data/page{N}.json и mushaf_data/dm/page{N}.json
(обе раскладки). Полный scripts/export_mushaf_page.py ходит в api.quran.com за таджвидом
на каждую страницу - ради смены подписей это лишний риск для выверенных данных
(тот же довод, что в scripts/export_mushaf_lang.py). Здесь меняется ТОЛЬКО поле
translation у слов из файла подписей; правило то же, что у экспорта: «*» и подписи без
букв - пустая строка, хвостовая пунктуация срезается (_clean_translation).

Источник - файл подписей (i18n/wbw_ru/<имя>.json), а не база: страницы лежат в git и
собираются локально, а база на проде своя (scripts/load_wbw_ru.py грузит тот же файл).

    python scripts/patch_mushaf_ru.py i18n/wbw_ru/juz1.json          # записать
    python scripts/patch_mushaf_ru.py i18n/wbw_ru/juz1.json --check  # только посчитать
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.mufradat import _is_junk  # noqa: E402
from scripts.export_mushaf_page import _clean_translation  # noqa: E402

DIRS = [ROOT / "mushaf_data", ROOT / "mushaf_data" / "dm"]
_BASE_PAGE = re.compile(r"^page\d+\.json$")      # без _ky/_uz/_zh: там свой язык


def main():
    src = Path(sys.argv[1])
    check = "--check" in sys.argv
    want = {}
    for key, glosses in json.loads(src.read_text(encoding="utf-8")).items():
        s, a = map(int, key.split(":"))
        for p, g in enumerate(glosses, 1):
            want[(s, a, p)] = "" if _is_junk(g) else _clean_translation(g)

    files = changed_files = changed_tokens = 0
    seen = set()
    for d in DIRS:
        for f in sorted(d.glob("page*.json")):
            if not _BASE_PAGE.match(f.name):
                continue
            raw = f.read_text(encoding="utf-8")
            data = json.loads(raw)
            n = 0

            def patch(tok, s=None, a=None):
                nonlocal n
                if tok.get("type") != "word":
                    return
                key = (tok.get("surah", s), tok.get("ayah", a), tok.get("position"))
                if key in want:
                    seen.add(key)
                    if tok.get("translation") != want[key]:
                        tok["translation"] = want[key]
                        n += 1

            for ay in data.get("ayahs", []):
                for tok in ay.get("tokens", []):
                    patch(tok, ay["surah"], ay["ayah"])
            for line in data.get("lines", []):
                for tok in line.get("tokens", []):
                    patch(tok)
            files += 1
            if n:
                changed_files += 1; changed_tokens += n
                if not check:
                    # вид файла сохраняем: у Мадины json.dump по умолчанию, у Дар аль-Маариф -
                    # без пробелов (scripts/build_dm_layout.py), иначе дифф был бы на весь файл
                    compact = raw == json.dumps(json.loads(raw), ensure_ascii=False, separators=(",", ":"))
                    out = json.dumps(data, ensure_ascii=False, **({"separators": (",", ":")} if compact else {}))
                    f.write_text(out, encoding="utf-8", newline="")
    missing = [k for k in want if k not in seen and want[k]]
    print(f"файлов просмотрено {files}, изменено {changed_files}, подписей заменено {changed_tokens}"
          + (" (проверка, без записи)" if check else ""))
    if missing:
        print(f"ВНИМАНИЕ: {len(missing)} слов из файла не найдены в страницах, первые: {missing[:5]}")


if __name__ == "__main__":
    main()
