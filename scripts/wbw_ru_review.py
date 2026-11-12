# -*- coding: utf-8 -*-
"""Сверка пословного ru «было / стало / почему» для человека (12.11.2026).

Вход (папка, по умолчанию logs/wbw_ru_sample):
  wbw_ru_new.json  - {"2:2": ["Это", ...]} подписи Claude, позиции = mufradat_words ru;
  notes.json       - {"2:2:7": "почему"} основания главных правок (необязательно);
  gemini.json      - {"2:2": [{"pos": 7, "problem": ..., "suggestion": ..., "source": ...}]}
                     замечания Gemini (scripts/wbw_ru_gemini.py), необязательно.
Опоры - sources/wbw_ru_refs/ (scripts/wbw_ru_refs.py).
Выход: review.md там же. Методика - wiki/wbw_ru_method.md.

    python scripts/wbw_ru_review.py [папка]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "sources" / "wbw_ru_refs"


def _norm(x):
    return re.sub(r"[^\wё]", "", x.lower())


def main():
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "logs" / "wbw_ru_sample"
    new = json.loads((d / "wbw_ru_new.json").read_text(encoding="utf-8"))
    notes = json.loads((d / "notes.json").read_text(encoding="utf-8")) if (d / "notes.json").exists() else {}
    gem = json.loads((d / "gemini.json").read_text(encoding="utf-8")) if (d / "gemini.json").exists() else {}

    body, big, small, words = [], 0, 0, 0
    for key, glosses in new.items():
        ref = json.loads((REFS / f"{key.replace(':', '_')}.json").read_text(encoding="utf-8"))
        ws = ref["words"]
        if len(ws) != len(glosses):
            raise SystemExit(f"{key}: подписей {len(glosses)}, слов {len(ws)}")
        for w, g in zip(ws, glosses):
            if (w["ru_now"].strip() == "*") != (g.strip() == "*"):
                raise SystemExit(f"{key}:{w['pos']}: «*» не на том месте")
        words += len(ws)
        old_line = " ".join(w["ru_now"] for w in ws if w["ru_now"] != "*")
        new_line = " ".join(g for g in glosses if g != "*")
        body += [f"## {key}", "", f"**Кулиев:** {ref['translations'].get('kuliev', '')}", "",
                 f"**Saheeh:** {ref['translations'].get('saheeh', '')}", "",
                 f"**Было:** {old_line}", "", f"**Стало:** {new_line}", ""]
        rows = []
        for w, g in zip(ws, glosses):
            old = w["ru_now"].strip()
            if old == g.strip():
                continue
            why = notes.get(f"{key}:{w['pos']}")
            if why:
                big += 1
            elif re.search(r"[\[\(]", old):
                why = "убраны скобки"; big += 1
            elif _norm(old) == _norm(g):
                why = "мелкое: знак препинания"; small += 1
            else:
                why = "мелкое: чтобы подписи подряд читались фразой"; small += 1
            rows.append(f"| {w['pos']} | {w['ar']} | {old} | {g} | {why} |")
        if rows:
            body += ["| № | Слово | Было | Стало | Почему |", "|---|---|---|---|---|"] + rows + [""]
        if key in gem:
            body += ["**Gemini:**", ""]
            for it in gem[key] or []:
                body.append(f"- {it.get('pos')}: {it.get('problem')} → «{it.get('suggestion')}» ({it.get('source', '')})")
            if not gem[key]:
                body.append("- замечаний нет")
            body.append("")

    head = ["# Пословный русский: проба (" + ", ".join(new) + ")", "",
            "**Черновик. Перевёл Claude по опорам (wiki/wbw_ru_method.md). В приложение не загружен.**", "",
            f"Аятов {len(new)}, слов {words}. Изменено {big + small}: **по смыслу {big}**, мелких {small} "
            "(знаки препинания, падеж и порядок слов — чтобы подписи подряд читались фразой).", "",
            "Опоры на каждый аят: тафсир аль-Муяссар (арбитр), ас-Саади (рус.), корпус QAC, "
            "английский пословный quran.com, Saheeh International, Абдель Халим, Кулиев, Абу Адель, Минвакф Египта.", ""]
    (d / "review.md").write_text("\n".join(head + body) + "\n", encoding="utf-8")
    print(f"review.md: аятов {len(new)}, слов {words}, по смыслу {big}, мелких {small}")


if __name__ == "__main__":
    main()
