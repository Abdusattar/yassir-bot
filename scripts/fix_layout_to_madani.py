#!/usr/bin/env python3
"""Приводит построчную раскладку `mushaf_data/page*.json` к ПЕЧАТНОЙ
мединской (KFGQPC V4, 1441H print) - источник QUL `mushaf-layout/19`.

**Зачем**: студент учит параллельно по бумажному мединскому мусхафу (в
мечетях - зелёные), а метод 40+40 стоит на строках. Разбивка по строкам
в приложении обязана совпадать с печатью, иначе рушится сама привязка
заучивания (решение пользователя 02.09.2026).

**Что нашёл аудит** (`scripts/audit_mushaf_layout.py`): 46 страниц из 604
расходились с печатью, 2140 слов из 77 432 (2.76%) стояли не на своей
строке. Главная причина (35 страниц, всегда ПАРАМИ): когда сура
начинается ровно с новой страницы, ряд заголовка суры оказывался в КОНЦЕ
предыдущей страницы, а басмала - в начале новой. В печати оба ряда стоят
на странице новой суры. Из-за этого на первой странице пары под текст
оставалось 14 рядов вместо 15, на второй - 14 вместо 13, и слова
расползались по всей странице (40-60% не на своём месте). Побочно у такой
страницы басмала выходила с `html: null` - текст не подтягивался, потому
что заголовок был на другом листе.

**ХИРУРГИЧЕСКИ**: страница НЕ перегенерируется с нуля. Переводы,
глиф-коды `code_v4`, привязка аятов, сам состав слов остаются ровно теми
же - меняется только то, на какой строке лежит каждый токен. Тот же
подход, что у `fix_mushaf_lines.py` и `fix_page_boundaries.py`.

**Проверки перед записью** (страница не пишется, если хоть одна не прошла):
  - состав слов до и после совпадает ПОЛНОСТЬЮ (ни одно не потеряно и не
    появилось лишнего);
  - все нетекстовые токены (знаки конца аята) на месте;
  - коды глифов идут неубывающим рядом от U+FC41 - инвариант, ловящий
    "чужой шрифт" (см. wiki/mushaf_yassirapp.md);
  - раскладка после правки совпадает с QUL пословно.

Идемпотентно: на уже верной странице ничего не меняет.

Использование:
    python scripts/fix_layout_to_madani.py --dry-run          # только отчёт
    python scripts/fix_layout_to_madani.py --pages 76,77
    python scripts/fix_layout_to_madani.py                    # все 604
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "mushaf_data")
CACHE_DIR = os.path.join(SCRIPT_DIR, "..", "sources", "qul_layout_cache")
BACKUP_DIR = os.path.join(SCRIPT_DIR, "..", "sources", "layout_backup")

QUL_URL = "https://qul.tarteel.ai/resources/mushaf-layout/19?page={page}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; yassir-bot/1.0)"}

_BLOCK_RE = re.compile(r'<div class="line-container" data-line="(\d+)">(.*?)(?=<div class="line-container"|\Z)', re.S)
_WORD_RE = re.compile(r'<span class="char\s+(char-word|char-end)\s*"[^>]*?data-location="([^"]*)"', re.S)

V4_FIRST_GLYPH = "ﱁ"


def fetch_qul(page):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"page{page}.html")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(QUL_URL.format(page=page), headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read().decode("utf-8", "replace")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            return html
        except (urllib.error.URLError, OSError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def qul_rows(page):
    """[(тип_ряда, [локация...]), ...] - ровно как в печати.

    Тип ряда берём из класса: `line--surah-name` - заголовок суры,
    `line--bismillah` - басмала, иначе текст. Знак конца аята (класс
    `char-end`) словом НЕ считаем - у QUL он размечен тем же тегом и
    получает позицию N+1, без этой поправки счёт врёт в каждом аяте."""
    html = fetch_qul(page)
    rows = []
    for m in _BLOCK_RE.finditer(html):
        block = m.group(2)
        if "line--surah-name" in block:
            kind = "header"
        elif "line--bismillah" in block:
            kind = "bismillah"
        else:
            kind = "text"
        locs = [w.group(2) for w in _WORD_RE.finditer(block) if w.group(1) == "char-word"]
        rows.append((kind, locs))
    return rows


def _loc(token):
    return f"{token['surah']}:{token['ayah']}:{token['position']}"


def _header_meta(surah_num, existing=None):
    """Метаданные ряда заголовка. Если ряд уже есть в наших данных (пусть
    и на соседней странице) - берём как есть, чтобы ничего не выдумывать."""
    if existing:
        return dict(existing)
    import quran_transcript as qt
    return {"type": "header", "surah": surah_num,
            "surah_name_ar": qt.Aya(surah_num, 1).get().sura_name}


def _bismillah_meta(surah_num, existing=None):
    if existing and existing.get("html"):
        return dict(existing)
    import quran_transcript as qt
    return {"type": "bismillah", "html": qt.Aya(surah_num, 1).get().bismillah_uthmani}


def rebuild_page(page, rows, data, neighbour_header=None):
    """Новый lines[] по печатным рядам. Токены только перекладываются."""
    tokens = [t for l in data["lines"] if l.get("type") == "text" for t in (l.get("tokens") or [])]
    loc_index = {}
    for i, t in enumerate(tokens):
        if t.get("type") == "word":
            loc_index[_loc(t)] = i

    text_rows = [i for i, (kind, _) in enumerate(rows) if kind == "text"]
    assign = [None] * len(tokens)
    for ri, (kind, locs) in enumerate(rows):
        if kind != "text":
            continue
        for loc in locs:
            idx = loc_index.get(loc)
            if idx is None:
                raise ValueError(f"стр {page}: слова {loc} нет в наших данных")
            assign[idx] = ri

    # Нетекстовые токены (знак конца аята, маркер руку' ۞) сами по себе
    # строки не имеют - у QUL их нет в разметке слов. Наследуют строку
    # соседа, НО с какой стороны - берём из НАШИХ исходных данных: знак
    # конца аята идёт в хвосте строки за словом, а маркер руку' может
    # СТОЯТЬ В НАЧАЛЕ строки (реальный случай - стр. 11, поймано при
    # сухом прогоне 02.09.2026: правило "всегда за предыдущим" тащило
    # маркер на строку выше и меняло 25 страниц, которые и так верны).
    orig_line = {}
    li = 0
    for l in data["lines"]:
        if l.get("type") != "text":
            continue
        for t in l.get("tokens") or []:
            orig_line[id(t)] = li
        li += 1
    attach_next = set()
    for i, t in enumerate(tokens):
        if t.get("type") == "word":
            continue
        prev_w = next((j for j in range(i - 1, -1, -1) if tokens[j].get("type") == "word"), None)
        next_w = next((j for j in range(i + 1, len(tokens)) if tokens[j].get("type") == "word"), None)
        mine = orig_line.get(id(t))
        if next_w is not None and orig_line.get(id(tokens[next_w])) == mine and (
                prev_w is None or orig_line.get(id(tokens[prev_w])) != mine):
            attach_next.add(i)

    last = text_rows[0] if text_rows else None
    for i in range(len(assign)):
        if assign[i] is None and i in attach_next:
            nxt = next((j for j in range(i + 1, len(assign)) if assign[j] is not None), None)
            assign[i] = assign[nxt] if nxt is not None else last
        elif assign[i] is None:
            assign[i] = last
        else:
            last = assign[i]

    # Какую суру объявляет ряд заголовка - берём из ПЕРВОГО СЛОВА, идущего
    # за ним в печатных рядах, а не из старых данных: на странице может
    # быть ДВА заголовка (стр. 595: Аш-Шамс и Аль-Лейл), и брать сурру у
    # первого для обоих - ошибка (поймано сухим прогоном 02.09.2026).
    def surah_after(ri):
        for kind, locs in rows[ri + 1:]:
            if kind == "text" and locs:
                return int(locs[0].split(":")[0])
        for t in tokens:
            if t.get("type") == "word":
                return t["surah"]
        return None

    old_headers = {l.get("surah"): l for l in data["lines"] if l.get("type") == "header"}
    if neighbour_header:
        old_headers.setdefault(neighbour_header.get("surah"), neighbour_header)
    old_bisms = [l for l in data["lines"] if l.get("type") == "bismillah"]

    out = []
    bism_i = 0
    for ri, (kind, _) in enumerate(rows):
        line_no = ri + 1
        if kind == "header":
            sn = surah_after(ri)
            meta = _header_meta(sn, old_headers.get(sn))
            meta["line"] = line_no
            meta["type"] = "header"
            meta["surah"] = sn
            out.append(meta)
        elif kind == "bismillah":
            sn = surah_after(ri)
            existing = old_bisms[bism_i] if bism_i < len(old_bisms) else None
            bism_i += 1
            meta = _bismillah_meta(sn, existing)
            meta["line"] = line_no
            meta["type"] = "bismillah"
            out.append(meta)
        else:
            out.append({"line": line_no, "type": "text",
                        "tokens": [t for i, t in enumerate(tokens) if assign[i] == ri]})
    return out


def check(page, before_lines, after_lines, rows):
    """Возвращает список проблем; пустой - можно писать."""
    problems = []

    def toks(lines):
        return [t for l in lines if l.get("type") == "text" for t in (l.get("tokens") or [])]

    b, a = toks(before_lines), toks(after_lines)
    if len(b) != len(a):
        problems.append(f"число токенов изменилось: {len(b)} -> {len(a)}")
    bw = sorted(_loc(t) for t in b if t.get("type") == "word")
    aw = sorted(_loc(t) for t in a if t.get("type") == "word")
    if bw != aw:
        lost = set(bw) - set(aw)
        extra = set(aw) - set(bw)
        problems.append(f"состав слов изменился (потеряно {len(lost)}, лишних {len(extra)})")
    bn = sum(1 for t in b if t.get("type") != "word")
    an = sum(1 for t in a if t.get("type") != "word")
    if bn != an:
        problems.append(f"нетекстовых токенов было {bn}, стало {an}")

    # Инвариант "коды глифов страницы идут неубывающим рядом от U+FC41" -
    # ловит слова, отрисованные шрифтом ЧУЖОЙ страницы.
    codes = [t.get("code_v4") for t in a if t.get("code_v4")]
    flat = [c for c in codes if c]
    if flat and flat[0] and flat[0][0] != V4_FIRST_GLYPH:
        problems.append(f"первый глиф не U+FC41, а U+{ord(flat[0][0]):04X}")
    prev = None
    for c in flat:
        cur = ord(c[0])
        if prev is not None and cur < prev:
            problems.append("коды глифов идут не по возрастанию")
            break
        prev = cur

    # Совпадение с печатью пословно.
    qmap = {}
    ri_text = 0
    for ri, (kind, locs) in enumerate(rows):
        if kind != "text":
            continue
        for loc in locs:
            qmap[loc] = ri_text
        ri_text += 1
    omap = {}
    ti = 0
    for l in after_lines:
        if l.get("type") != "text":
            continue
        for t in l.get("tokens") or []:
            if t.get("type") == "word":
                omap[_loc(t)] = ti
        ti += 1
    wrong = [w for w in qmap if omap.get(w) != qmap[w]]
    if wrong:
        problems.append(f"после правки всё ещё не совпадает с печатью: {len(wrong)} слов")
    return problems


def process(page, dry_run=False, neighbour_header=None):
    path = os.path.join(DATA_DIR, f"page{page}.json")
    if not os.path.exists(path):
        return {"page": page, "skip": "нет данных"}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    rows = qul_rows(page)
    before = data["lines"]
    try:
        after = rebuild_page(page, rows, data, neighbour_header)
    except ValueError as e:
        return {"page": page, "error": str(e)}

    if before == after:
        return {"page": page, "unchanged": True}

    problems = check(page, before, after, rows)
    if problems:
        return {"page": page, "error": "; ".join(problems)}

    if not dry_run:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        backup = os.path.join(BACKUP_DIR, f"page{page}.json")
        if not os.path.exists(backup):
            shutil.copy(path, backup)
        tmp = path + ".tmp"
        data["lines"] = after
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)

    def kinds(lines):
        return [l.get("type") for l in lines]
    return {"page": page, "fixed": True,
            "before_rows": len(before), "after_rows": len(after),
            "before_kinds": kinds(before)[:3], "after_kinds": kinds(after)[:3]}


def parse_pages(spec):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default="1-604")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pages = parse_pages(args.pages)
    # Заголовок суры, ошибочно лежащий в конце предыдущей страницы,
    # переезжает на следующую - подхватываем его метаданные оттуда.
    neighbour_headers = {}
    for p in pages:
        path = os.path.join(DATA_DIR, f"page{p}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        last = d["lines"][-1] if d["lines"] else None
        if last and last.get("type") == "header":
            neighbour_headers[p + 1] = last

    fixed, errors, unchanged = [], [], 0
    for p in pages:
        r = process(p, args.dry_run, neighbour_headers.get(p))
        if r.get("fixed"):
            fixed.append(r)
            print(f"стр {p}: рядов {r['before_rows']} -> {r['after_rows']}, "
                  f"начало {r['before_kinds']} -> {r['after_kinds']}", flush=True)
        elif r.get("error"):
            errors.append(r)
            print(f"стр {p}: ОШИБКА - {r['error']}", flush=True)
        elif r.get("unchanged"):
            unchanged += 1

    print(f"\nИТОГО: исправлено {len(fixed)}, без изменений {unchanged}, ошибок {len(errors)}")
    if errors:
        print("Страницы с ошибками:", [e["page"] for e in errors])
    if args.dry_run:
        print("(dry-run: на диск ничего не писалось)")


if __name__ == "__main__":
    main()
