# -*- coding: utf-8 -*-
"""Загрузка пересмотренного пословного ru в mufradat_words (12.11.2026).

Методика перевода - wiki/wbw_ru_method.md. Данные - i18n/wbw_ru/<имя>.json:
{"2:2": ["Это", ...]} - подписи по позициям ru-строк, «*» на тех же местах.

Почему не scripts/load_wbw_zh.py-подобный UPDATE на месте: тренажёр считает одним
словом все строки с общим progress_key и полагается на то, что арабский текст и
подпись внутри ключа одинаковы (core/mufradat.py:get_words_by_progress_keys берёт
одного представителя). Ключ = id строки-представителя пары (арабское, подпись), и
в него входят вхождения по всему Корану. Правка подписи в одном джузе оставила бы в
ключе две разные подписи (на копии базы 12.11: 169 таких ключей, у 173 затронутых
ключей 3155 слов вне 1 джуза). Поэтому после правки затронутые строки делятся на
группы заново, по фактической паре (арабское, normalize_gloss(подпись)):

- в группе есть строка-представитель (id == её ключ), чья подпись не менялась, -
  группа берёт этот ключ (изменённое слово примкнуло к уже существующей паре);
- иначе, если есть строка с id == её ключ (представитель ушёл с новой подписью), -
  группа сохраняет этот номер;
- иначе ключ = наименьший id группы.

Прогресс студентов (mufradat_progress, та же база, word_id = progress_key) -
решение пользователя 12.11: ПЕРЕНОСИТЬ и переспросить. Для каждого ключа, из
которого строки перешли в другой, прогресс копируется на новый ключ (если своего
там нет; при слиянии - лучший по correct_streak). Счётчики correct_count /
wrong_count в копию не идут: рейтинг суммирует их по строкам, копия удвоила бы объём.
Там, где подпись у слова стала другой, выученному слову (correct_streak >=
MASTERY_STREAK) ставится last_correct_date старше RECHECK_AFTER_DAYS: оно остаётся
выученным, но тренажёр один раз переспросит его штатной перепроверкой.

По умолчанию НИЧЕГО не пишет - печатает план. Запись - с --apply (перед ней копия
базы рядом: hadiths.db.bak-wbw-<имя>). Идемпотентно: повторный запуск без правок
подписей ничего не делает.

    python scripts/load_wbw_ru.py i18n/wbw_ru/juz1.json            # план
    python scripts/load_wbw_ru.py i18n/wbw_ru/juz1.json --apply    # записать
    ... --db <путь>                                                # другая база (проверка на копии)
"""
import argparse
import collections
import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.sampler import HADITHS_DB, normalize_gloss, ensure_mufradat_schema  # noqa: E402
from core.mufradat import MASTERY_STREAK, RECHECK_AFTER_DAYS  # noqa: E402

LANG = "ru"


def plan(conn, data):
    rows = {r["id"]: dict(r) for r in conn.execute(
        "SELECT id, surah_number s, ayah_number a, position p, arabic_text ar, translation t, "
        "progress_key k FROM mufradat_words WHERE language=?", (LANG,))}
    by_pos = {(r["s"], r["a"], r["p"]): r for r in rows.values()}

    new_t = {}                                   # id -> новая подпись
    for key, glosses in data.items():
        s, a = map(int, key.split(":"))
        have = sorted(p for (s2, a2, p) in by_pos if (s2, a2) == (s, a))
        if have != list(range(1, len(glosses) + 1)):
            raise SystemExit(f"{key}: подписей {len(glosses)}, в базе позиции {have[:3]}..{have[-3:]}")
        for p, g in enumerate(glosses, 1):
            r = by_pos[(s, a, p)]
            g = g.strip()
            if (r["t"].strip() == "*") != (g == "*"):
                raise SystemExit(f"{key}:{p}: «*» не на том месте")
            if not g:
                raise SystemExit(f"{key}:{p}: пустая подпись")
            if g != r["t"]:
                new_t[r["id"]] = g

    def pair(r):
        return (r["ar"], normalize_gloss(new_t.get(r["id"], r["t"])))

    # строки, у которых изменилась нормализованная подпись (только знак - ключ не трогаем)
    moved = {i for i in new_t if normalize_gloss(new_t[i]) != normalize_gloss(rows[i]["t"])}
    touched_keys = {rows[i]["k"] for i in moved}
    target_pairs = {pair(rows[i]) for i in moved}
    scope = [r for r in rows.values() if r["k"] in touched_keys or pair(r) in target_pairs]

    groups = collections.defaultdict(list)
    for r in scope:
        groups[pair(r)].append(r)

    new_key = {}                                 # id -> новый ключ
    for members in groups.values():
        seated = [r for r in members if r["id"] == r["k"]]
        stable = [r for r in seated if r["id"] not in moved]
        if stable:
            k = min(r["id"] for r in stable)
        elif seated:
            k = min(r["id"] for r in seated)
        else:
            k = min(r["id"] for r in members)
        for r in members:
            new_key[r["id"]] = k

    # перенос прогресса: (старый ключ -> новый ключ), stale = подпись у слова стала другой
    moves = {}
    for r in scope:
        ok, nk = r["k"], new_key[r["id"]]
        changed = r["id"] in moved
        if ok != nk:
            moves[(ok, nk)] = moves.get((ok, nk), False) or changed
    # ключ сохранил номер, но все его строки сменили подпись - тоже переспросить
    restale = set()
    for members in groups.values():
        k = new_key[members[0]["id"]]
        if all(r["id"] in moved for r in members) and any(r["k"] == k for r in members):
            restale.add(k)
    rekey = {i: k for i, k in new_key.items() if rows[i]["k"] != k}
    return rows, new_t, rekey, moves, restale, groups


def check_invariant(conn):
    """Внутри одного ключа - одна пара (арабское, нормализованная подпись)."""
    bad = collections.defaultdict(set)
    for ar, t, k in conn.execute(
            "SELECT arabic_text, translation, progress_key FROM mufradat_words WHERE language=?", (LANG,)):
        bad[k].add((ar, normalize_gloss(t)))
    mixed = sum(1 for v in bad.values() if len(v) > 1)
    orphan = conn.execute(
        "SELECT COUNT(*) FROM mufradat_words w WHERE language=? AND NOT EXISTS "
        "(SELECT 1 FROM mufradat_words x WHERE x.id = w.progress_key AND x.language = w.language "
        " AND x.progress_key = w.progress_key)", (LANG,)).fetchone()[0]
    return mixed, orphan


def invariant_after(rows, new_t, rekey):
    """То же правило, что check_invariant, но посчитанное в памяти для состояния ПОСЛЕ правки -
    чтобы план (без --apply) ничего не писал в рабочую базу и не запирал её."""
    pairs = collections.defaultdict(set)
    key_of = {}
    for i, r in rows.items():
        k = rekey.get(i, r["k"])
        key_of[i] = k
        pairs[k].add((r["ar"], normalize_gloss(new_t.get(i, r["t"]))))
    mixed = sum(1 for v in pairs.values() if len(v) > 1)
    orphan = sum(1 for i, k in key_of.items() if key_of.get(k) != k)
    return mixed, orphan


def plan_progress(conn, moves, restale):
    """Что сделать с прогрессом студентов: (строки к вставке, строки к пометке «переспросить»,
    счётчики). Только читает, и читает таблицу ОДНИМ проходом: до 14.11.2026 здесь было по
    запросу на каждый ключ без индекса по word_id - на сервере это минуты, и всё это время
    база была заперта (14.11 приложение у студентов не открывалось 17 минут)."""
    stale_date = (date.today() - timedelta(days=RECHECK_AFTER_DAYS + 1)).isoformat()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(mufradat_progress)")}
    if not cols:
        return [], [], {"copied": 0, "users": 0, "staled": 0, "kept": 0, "has_cc": False, "none": True}
    by_new = collections.defaultdict(list)
    for (ok, nk), changed in moves.items():
        by_new[nk].append((ok, changed))
    need = set(by_new) | {ok for srcs in by_new.values() for ok, _ in srcs} | set(restale)
    prog = collections.defaultdict(list)         # word_id -> [(user, streak, days, last)]
    for u, w, streak, days, last in conn.execute(
            "SELECT user_id, word_id, correct_streak, days_correct, last_correct_date FROM mufradat_progress"):
        if w in need:
            prog[w].append((u, streak, days, last))
    inserts, seen_users, staled = [], set(), 0
    for nk, sources in by_new.items():
        have = {u for u, *_ in prog.get(nk, ())}
        best = {}                                # user -> (streak, days_correct, last, changed)
        for ok, changed in sources:
            for u, streak, days, last in prog.get(ok, ()):
                if u in have:
                    continue
                if u not in best or streak > best[u][0]:
                    best[u] = (streak, days, last, changed)
        for u, (streak, days, last, changed) in best.items():
            if streak <= 0:
                continue                         # нечего сохранять: слово и так «не начато»
            if changed and streak >= MASTERY_STREAK:
                last = stale_date; staled += 1
            seen_users.add(u)
            inserts.append((u, nk, streak, 0, days, last))
    restale_rows = [(stale_date, u, k) for k in restale for u, streak, days, last in prog.get(k, ())
                    if streak >= MASTERY_STREAK and (last is None or last > stale_date)]
    stats = {"copied": len(inserts), "users": len(seen_users), "staled": staled,
             "kept": len(restale_rows), "has_cc": "correct_count" in cols, "none": False}
    return inserts, restale_rows, stats


def write_progress(conn, inserts, restale_rows, has_cc):
    if has_cc:
        conn.executemany(
            "INSERT OR IGNORE INTO mufradat_progress(user_id, word_id, correct_streak, wrong_count, "
            "days_correct, last_correct_date, correct_count) VALUES (?,?,?,?,?,?,0)", inserts)
    else:
        conn.executemany(
            "INSERT OR IGNORE INTO mufradat_progress(user_id, word_id, correct_streak, wrong_count, "
            "days_correct, last_correct_date) VALUES (?,?,?,?,?,?)", inserts)
    conn.executemany("UPDATE mufradat_progress SET last_correct_date=? WHERE user_id=? AND word_id=?",
                     restale_rows)


def _print_progress(st):
    if st["none"]:
        print("  таблицы mufradat_progress нет - переносить нечего")
        return
    print(f"  прогресс: скопировано строк {st['copied']} (студентов {st['users']}), из них выученных на "
          f"переспрос {st['staled']}; на прежнем ключе помечено к переспросу {st['kept']}")


def _rebuild_chunks(db):
    """Файлы переводов для мусхафа (wbw/<язык>/<сура>.json) - сразу из обновлённой базы.
    Только для рабочей базы: прогон на копии (--db) файлы приложения не трогает."""
    if Path(db).resolve() != Path(HADITHS_DB).resolve():
        return
    from scripts.build_wbw_chunks import build
    _, written = build(db, languages={"ru"})
    print("файлы переводов мусхафа: переписано %d" % written)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--db", default=str(HADITHS_DB))
    args = ap.parse_args()
    data = json.loads(Path(args.src).read_text(encoding="utf-8"))
    db = Path(args.db)

    if args.apply:
        bak = db.with_name(db.name + ".bak-wbw-" + Path(args.src).stem)
        if not bak.exists():
            src_c = sqlite3.connect(db); dst_c = sqlite3.connect(bak)
            src_c.backup(dst_c); dst_c.close(); src_c.close()
            print("копия базы:", bak)

    # Рабочую базу запираем только на саму запись (секунды). Всё чтение и расчёт - до неё и
    # без запирающей транзакции; план без --apply не пишет в базу ничего (14.11.2026: и план, и
    # запись держали базу запертой минутами - приложение у студентов не открывалось).
    conn = sqlite3.connect(db, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None          # транзакцией управляем сами
    if args.apply:
        ensure_mufradat_schema(conn)
    before = check_invariant(conn)
    rows, new_t, rekey, moves, restale, groups = plan(conn, data)
    print(f"аятов {len(data)}; подписей к замене {len(new_t)}; строк со сменой ключа {len(rekey)} "
          f"(из них вне файла: {sum(1 for i in rekey if i not in new_t)}); "
          f"переносов прогресса {len(moves)}; ключей на переспрос без смены номера {len(restale)}")
    print(f"  до: ключей с разными подписями {before[0]}, строк без представителя {before[1]}")
    if not new_t:
        print("нечего менять")
        return
    after = invariant_after(rows, new_t, rekey)
    print(f"  после: ключей с разными подписями {after[0]}, строк без представителя {after[1]}")
    if after[0] > before[0] or after[1] > before[1]:
        raise SystemExit("нарушено правило ключей - ничего не записано")

    if not args.apply:
        _print_progress(plan_progress(conn, moves, restale)[2])
        print("это был план (база не тронута). Записать: --apply")
        return

    import time
    t0 = time.time()
    conn.execute("BEGIN IMMEDIATE")
    try:
        # прогресс читаем уже под замком: ответ студента секунду назад не потеряется
        inserts, restale_rows, st = plan_progress(conn, moves, restale)
        conn.executemany("UPDATE mufradat_words SET translation=? WHERE id=?", [(g, i) for i, g in new_t.items()])
        conn.executemany("UPDATE mufradat_words SET progress_key=? WHERE id=?", [(k, i) for i, k in rekey.items()])
        if not st["none"]:
            write_progress(conn, inserts, restale_rows, st["has_cc"])
        real = check_invariant(conn)
        if real[0] > before[0] or real[1] > before[1]:
            raise SystemExit("нарушено правило ключей - откат, ничего не записано")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    _print_progress(st)
    print("записано; база была заперта %.1f с" % (time.time() - t0))
    _rebuild_chunks(args.db)
    if Path(args.db).resolve() == Path(HADITHS_DB).resolve():
        from scripts.check_wbw_ru_loaded import update_mark
        left = [k for k, v in update_mark().items() if v]
        print("отметка загруженных джузов обновлена" + (
            "; ещё не загружены: " + ", ".join(left) if left else ""))


if __name__ == "__main__":
    main()
