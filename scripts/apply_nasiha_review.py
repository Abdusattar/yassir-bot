"""Применить решения ручной сверки к банку насых (16.09.2026).

decisions.json: {"<id>": "ok" | "delete" | {"edit": [[old, new], ...]}}.
ok -> approved=1; delete -> строка удаляется; edit -> подстрочные замены
(каждая старая строка обязана встретиться ровно один раз), затем approved=1.
Заодно снимает латиницу приветствий в любых шаблонах (Assalamu alaykum,
MashaAllah, Tadabbur). Идемпотентен: повторный запуск ничего не ломает.

    sudo -u stursunkul python3 scripts/apply_nasiha_review.py decisions.json [--db sources/hadiths.db]
"""
import argparse
import json
import re
import sqlite3
import sys

LATIN = [
    (re.compile(r"Assalamu[ ']?alaykum", re.I), "Ассаляму алейкум"),
    (re.compile(r"Masha ?Allah", re.I), "МашаАллах"),
    (re.compile(r"Tadabbur"), "Тадаббур"),
    (re.compile(r"Barak ?Allahu? fiik[ia]?", re.I), "БаракАллаху фийк"),
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("decisions")
    p.add_argument("--db", default="sources/hadiths.db")
    a = p.parse_args()
    dec = json.load(open(a.decisions, encoding="utf-8"))
    c = sqlite3.connect(a.db)
    n_ok = n_del = n_edit = n_latin = 0
    for sid, d in dec.items():
        row = c.execute("SELECT text FROM nasiha_bank WHERE id=?", (int(sid),)).fetchone()
        if not row:
            print(f"#{sid}: нет в банке (уже удалён?)")
            continue
        text = row[0]
        if d == "delete":
            c.execute("DELETE FROM nasiha_bank WHERE id=?", (int(sid),))
            n_del += 1
            continue
        if isinstance(d, dict):
            for old, new in d["edit"]:
                if text.count(old) != 1:
                    if new in text and old not in text:
                        continue  # уже применено
                    sys.exit(f"#{sid}: старый фрагмент встречается {text.count(old)} раз: {old[:60]}")
                text = text.replace(old, new)
            n_edit += 1
        c.execute("UPDATE nasiha_bank SET text=?, approved=1 WHERE id=?", (text, int(sid)))
        n_ok += 1
    for rid, text in c.execute("SELECT id, text FROM nasiha_bank WHERE template=1").fetchall():
        new = text
        for rx, rep in LATIN:
            new = rx.sub(rep, new)
        if new != text:
            c.execute("UPDATE nasiha_bank SET text=? WHERE id=?", (new, rid))
            n_latin += 1
    c.commit()
    print(f"одобрено {n_ok} (из них с правкой {n_edit}), удалено {n_del}, латиница снята у {n_latin}")
    print(c.execute("SELECT kind, COUNT(*), SUM(approved) FROM nasiha_bank WHERE template=1 GROUP BY kind").fetchall())


if __name__ == "__main__":
    main()
