# -*- coding: utf-8 -*-
"""Поиск сдвигов отрицания в пословном ru (14.11.2026, wiki/wbw_ru_method.md правило 8).

Сверяет подписи i18n/wbw_ru/<файл>.json с английским пословным из sources/wbw_ru_refs:
  A - в английском есть not/no/never, в русской подписи отрицания нет (могло уехать к соседу);
  B - в русской подписи «не/нет/ни/без», в английском отрицания нет (могло приехать от соседа).
Это подсказка для глаз, не приговор: «ни» в «где бы ни», неверие (كفر) и т.п. - норма.

    python scripts/wbw_ru_shift_check.py i18n/wbw_ru/juz6.json
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEG_EN = re.compile(r"\b(not|no|never|nor|none|neither)\b", re.I)
NEG_RU = re.compile(r"(^|[^а-яё])(не|нет|ни|никогда|без|отнюдь|нельзя)([^а-яё]|$)", re.I)
SKIP_B = re.compile(r"disbeliev|reject|den(y|ied)|without|except|other than|unless|lest|nothing"
                    r"|until|any|nay|yes|ever|ignor|unjust|wrong|whatever|wherever|whoever", re.I)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    caps = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    hits = 0
    for key, glosses in caps.items():
        s, a = key.split(":")
        ref_path = ROOT / "sources" / "wbw_ru_refs" / f"{s}_{a}.json"
        if not ref_path.exists():
            print(f"нет опоры {key}")
            continue
        words = {w["pos"]: w for w in json.loads(ref_path.read_text(encoding="utf-8"))["words"]}
        for p, g in enumerate(glosses, 1):
            if g == "*" or p not in words:
                continue
            en = words[p].get("en_wbw") or ""
            en_neg, ru_neg = bool(NEG_EN.search(en)), bool(NEG_RU.search(g))
            if en_neg and not ru_neg:
                kind = "A"
            elif ru_neg and not en_neg and not SKIP_B.search(en):
                kind = "B"
            else:
                continue
            hits += 1
            print(f"{kind} {key}:{p} | {words[p].get('ar')} | en={en} | ru={g}")
    print(f"кандидатов: {hits}")


if __name__ == "__main__":
    main()
