# -*- coding: utf-8 -*-
"""Применить список правок к готовым файлам пословного ru (14.11.2026, wiki/wbw_ru_method.md).

Строка списка: `s:a:p | арабское | было -> стало`. Правка вносится, только если «было»
совпало с файлом; «стало» со скобками, «->» или двойным пробелом отвергается (14.11 комментарий
из такой строки уехал в подпись на прод). Любое несовпадение - ничего не записывается.

    python scripts/wbw_ru_apply.py logs/wbw_ru_juz9/verify.txt [--apply]
"""
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINE = re.compile(r"^(\d+):(\d+):(\d+) \| (.*?) \| (.*?) -> (.*)$")
BAD = re.compile(r"[()\[\]]|  |->")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    files = {f: json.loads(Path(f).read_text(encoding="utf-8"))
             for f in sorted(glob.glob(str(ROOT / "i18n" / "wbw_ru" / "juz*.json")))}
    problems, touched, n = [], set(), 0
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        m = LINE.match(line.rstrip())
        if not m:
            if line.strip() and not line.startswith("#"):
                problems.append("не разобрано: " + line)
            continue
        s, a, p, _, old, new = m.groups()
        key, p, new = "%s:%s" % (s, a), int(p), new.strip()
        f = next((f for f, d in files.items() if key in d), None)
        if f is None or p > len(files[f][key]):
            problems.append("нет слова: " + line)
        elif files[f][key][p - 1] != old.strip():
            problems.append("«было» не совпало (%r в файле): %s" % (files[f][key][p - 1], line))
        elif not new or new == "*" or BAD.search(new) or len(new) > 40:
            problems.append("плохое «стало»: " + line)
        else:
            files[f][key][p - 1] = new
            touched.add(f)
            n += 1
    if problems:
        print("\n".join(problems))
        sys.exit("ничего не записано")
    print("правок: %d, файлов: %d" % (n, len(touched)))
    if "--apply" in sys.argv:
        for f in touched:
            raw = Path(f).read_bytes()
            nl = "\r\n" if b"\r\n" in raw else "\n"
            Path(f).write_text(json.dumps(files[f], ensure_ascii=False, indent=1), encoding="utf-8", newline=nl)
        print("записано")


if __name__ == "__main__":
    main()
