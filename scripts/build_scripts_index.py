# -*- coding: utf-8 -*-
"""Указатель скриптов: wiki/scripts_index.md из описаний в самих файлах (14.11.2026, architecture.md С4).

В scripts/ больше сотни файлов, и не было видно, что живое, а что разовое. Указатель
собирается из первой строки описания каждого скрипта и даты последней правки в git -
руками его не ведут. Тест tests/test_scripts_index.py не даст запушить скрипт без
описания или с устаревшим указателем.

    python scripts/build_scripts_index.py           # пересобрать
    python scripts/build_scripts_index.py --check   # устарел - код 1
"""
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "wiki" / "scripts_index.md"

# Раздел по началу имени (первое совпадение). Слои - wiki/architecture.md.
GROUPS = [
    ("Сервер и выкатка (слой 3)", ("backup_", "pull_backup", "monitor", "server_config", "team_sync",
                                    "patch_nginx", "check_v4_fonts", "user_trail", "restore_after_hack")),
    ("Сборка приложения и данных мусхафа (слой 2)", ("build_", "export_mushaf", "patch_mushaf", "fix_",
                                                      "audit_mushaf", "add_ayah_meaning", "restore_missing",
                                                      "check_wbw", "generate_hifz")),
    ("Пословный перевод (слои 1–2)", ("wbw_", "load_wbw")),
    ("Загрузка содержания в базу (слой 1)", ("load_", "import_", "seed_", "sync_", "fetch_")),
    ("Снимки и стенд (слой 5)", ("shoot_", "stand", "dev_")),
    ("Приложение: вход, запись, замеры (слои 4–5)", ("app_", "login_", "link_email", "make_app_icons",
                                                      "mark_sketches", "check_rec", "rec_", "find_glued",
                                                      "backfill_voice", "measure_", "mirror_v4", "i18n_")),
    ("Люди, группы, баллы (слой 1, данные людей)", ("appeal_", "announce", "send_", "membership", "curriculum",
                                                     "attendance", "score", "leaderboard", "group", "ustaz",
                                                     "prep_", "enter_prep", "finish_prep", "rotate_prep",
                                                     "hafiz", "lesson_", "retake_", "set_", "task_since",
                                                     "written_off", "migrate_", "scan_group", "fill_invite",
                                                     "user_timezones", "subject_readiness", "nahw_start",
                                                     "prune_", "dedup_", "restore_mastery", "pulse_")),
    ("Насыхи, тадаббур, классификация содержания", ("apply_nasiha", "export_nasiha", "batch_classify",
                                                    "classify_", "tadabbur_", "test_", "simulate_",
                                                    "generate_kyrgyz", "ingest_")),
]
OTHER = "Остальное"


def first_line(path):
    doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
    line = doc.strip().splitlines()[0].strip() if doc.strip() else ""
    return line.replace("|", "/")


def group_of(name):
    for title, prefixes in GROUPS:
        if name.startswith(prefixes):
            return title
    return OTHER


def last_dates():
    """{имя файла: дата последнего коммита} одним вызовом git."""
    out = subprocess.run(["git", "-C", str(ROOT), "log", "--format=@%ad", "--date=short", "--name-only",
                          "--", "scripts"], capture_output=True, text=True, encoding="utf-8").stdout
    dates, cur = {}, ""
    for line in out.splitlines():
        if line.startswith("@"):
            cur = line[1:]
        elif line.startswith("scripts/") and line.endswith(".py"):
            dates.setdefault(line[len("scripts/"):], cur)
    return dates


def render():
    dates = last_dates()
    groups = {}
    for f in sorted((ROOT / "scripts").glob("*.py")):
        groups.setdefault(group_of(f.name), []).append(f)
    lines = ["# Указатель скриптов", "",
             "Собирается сам: `python scripts/build_scripts_index.py` (описание - первая строка в файле,",
             "дата - последняя правка в git). Руками не править. Слои - `wiki/architecture.md`.", ""]
    for title in [g[0] for g in GROUPS] + [OTHER]:
        files = groups.get(title)
        if not files:
            continue
        lines += ["## %s" % title, "", "| Скрипт | Что делает | Правка |", "|---|---|---|"]
        for f in files:
            lines.append("| `%s` | %s | %s |" % (f.name, first_line(f), dates.get(f.name, "новый")))
        lines.append("")
    return "\n".join(lines)


def main():
    text = render()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("wiki/scripts_index.md устарел: python scripts/build_scripts_index.py")
            sys.exit(1)
        return
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("скриптов %d -> %s" % (len(list((ROOT / "scripts").glob("*.py"))), OUT.relative_to(ROOT)))


if __name__ == "__main__":
    main()
