#!/usr/bin/env python3
"""Чинит построчную разметку страниц мусхафа по печатной раскладке
KFGQPC V4 (1441H) из QUL.

Зачем: источник наших данных (zonetecde/mushaf-layout) на 49 страницах из 604
нумерует строки с нуля и раскладывает слова по 16 строкам вместо 15. В печатном
мадани-мусхафе на странице всегда 15 строк. Прямая сверка с KFGQPC V4 показала:
на страницах, где у нас 15 строк, расхождений с печатной раскладкой НОЛЬ
(проверено на стр. 5, 7, 300, 500 — 129/125/132/127 слов, ни одного переезда),
а на 16-строчных не на своём месте 56-74 слова. То есть чинить нужно только их.

Метод стоит ровно на границах строк (40+40, правило перехода), поэтому это не
косметика: на битых страницах студент учил бы не те отрезки, а устаз проверял бы
по бумаге, где строки другие.

Источник истины: https://qul.tarteel.ai/resources/mushaf-layout/19?page=N —
превью печатной раскладки того самого издания, под которое нарезан наш шрифт V4.
В нём у каждого слова стоит data-location="сура:аят:позиция". ВАЖНО: у QUL знак
конца аята считается словом и получает позицию N+1 — у нас это отдельный токен
типа ayah_end. Пустые строки у QUL (без слов) — это строка с названием суры и
строка басмалы, у нас типы header/bismillah.

Скрипт НЕ трогает сами токены: слова, глифы code_v4, переводы и разметку таджвида
переносит как есть, меняется только распределение по строкам и их нумерация
(становится 1..15, как на остальных 555 страницах).

Использование:
    python scripts/fix_mushaf_lines.py --check
        показать, какие страницы битые, ничего не менять

    python scripts/fix_mushaf_lines.py --dir mushaf_data
        починить page{N}.json в указанной папке

    python scripts/fix_mushaf_lines.py --dir <папка> --suffix _ky
        то же для page{N}_ky.json (языковые версии живут на сервере)

Кэш скачанных страниц QUL — в --cache (по умолчанию рядом, qul_cache/),
чтобы повторный прогон не ходил в сеть.
"""

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, ".")
import quran_transcript as qt

QUL_URL = "https://qul.tarteel.ai/resources/mushaf-layout/19?page={page}"
LINE_RE = re.compile(r'<div class="line-container" data-line="(\d+)">')
LOC_RE = re.compile(r'data-location="(\d+:\d+:\d+)"')
# Пустые строки печатной раскладки размечены явно: строка с названием суры
# несёт класс line--surah-name и номер суры (surah085), строка басмалы —
# класс line--bismillah.
SURAH_LINE_RE = re.compile(r'line--surah-name')
SURAH_NUM_RE = re.compile(r'surah(\d{3})')
BISMILLAH_LINE_RE = re.compile(r'line--bismillah')


def fetch_qul(page, cache_dir):
    """HTML превью печатной раскладки страницы. Кэшируется на диск."""
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "%d.html" % page)
    if os.path.exists(path) and os.path.getsize(path) > 50000:
        return io.open(path, encoding="utf-8").read()
    req = urllib.request.Request(
        QUL_URL.format(page=page), headers={"User-Agent": "yassir-bot/1.0"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    io.open(path, "w", encoding="utf-8").write(html)
    time.sleep(0.3)
    return html


def qul_layout(html):
    """Строки печатной страницы: [{line, kind, locs, surah}].

    kind — "text" (слова), "header" (название суры) или "bismillah".
    Раньше возвращались только слова, а чем заполнить пустую строку —
    брали из нашего же файла; на страницах с разъехавшейся границей таких
    строк у нас нет вовсе, и сборка падала."""
    parts = LINE_RE.split(html)
    out = []
    for i in range(1, len(parts), 2):
        n, body = int(parts[i]), parts[i + 1]
        locs = LOC_RE.findall(body)
        if locs:
            out.append({"line": n, "kind": "text", "locs": locs, "surah": None})
        elif SURAH_LINE_RE.search(body):
            m = SURAH_NUM_RE.search(body)
            out.append({
                "line": n, "kind": "header", "locs": [],
                "surah": int(m.group(1)) if m else None,
            })
        elif BISMILLAH_LINE_RE.search(body):
            out.append({"line": n, "kind": "bismillah", "locs": [], "surah": None})
        else:
            out.append({"line": n, "kind": "empty", "locs": [], "surah": None})
    return out


def ayah_stream(data):
    """Все токены страницы подряд, как они идут в аятах: слова, знаки конца
    аята и маркеры (۞ руку'). Именно этот поток мы и раскладываем по строкам —
    так маркер сам оказывается перед своим словом, его не надо привязывать
    отдельно (у QUL знака руку' в данных нет вовсе)."""
    out = []
    for ayah in data["ayahs"]:
        key = "%d:%d" % (ayah["surah"], ayah["ayah"])
        words = [t for t in ayah["tokens"] if t["type"] == "word"]
        for t in ayah["tokens"]:
            if t["type"] == "word":
                # В lines у слова есть surah/ayah, в ayahs их нет — они лежат
                # на самом аяте. Дополняем, иначе на странице чтения отвалятся
                # data-surah/data-ayah, а на них висят перевод по тапу и
                # добавление в «Мои слова».
                w = dict(t)
                w["surah"] = ayah["surah"]
                w["ayah"] = ayah["ayah"]
                out.append(((key, t["position"]), w))
            elif t["type"] == "ayah_end":
                # У QUL знак конца аята считается словом с позицией N+1.
                out.append(((key, len(words) + 1), dict(t)))
            else:
                out.append((None, dict(t)))  # маркер: своей локации не имеет
    return out


def flat_tokens(data):
    """Все токены строк подряд, в порядке чтения — для сверки до/после."""
    out = []
    for line in data["lines"]:
        for t in line.get("tokens", []):
            out.append(t)
    return out


def token_id(t):
    """Устойчивый отпечаток токена: по нему сверяем, что ничего не потеряли."""
    if t["type"] == "word":
        return ("w", t.get("surah"), t.get("ayah"), t.get("position"), t.get("code_v4"))
    return (t["type"], t.get("code_v4"), t.get("html"))


def rebuild(data, layout):
    """Новый массив lines по печатной раскладке. Токены переносятся как есть,
    меняется только то, где проходят границы строк.

    Строки с названием суры и басмалой строятся ПО ПЕЧАТНОЙ РАСКЛАДКЕ, а не
    берутся из нашего файла: на страницах, где наша граница разошлась с
    печатью, их у нас может не быть вовсе. Название суры и текст басмалы —
    из quran_transcript, тот же источник, что и у экспортёра."""
    stream = ayah_stream(data)
    pos = 0
    lines = []

    for item in layout:
        line_no, kind, locs = item["line"], item["kind"], item["locs"]
        if kind == "header":
            surah = item["surah"]
            lines.append({
                "line": line_no, "type": "header", "surah": surah,
                "surah_name_ar": qt.Aya(surah, 1).get().sura_name,
            })
            continue
        if kind == "bismillah":
            # Какая сура начинается на этой странице — берём из ближайшей
            # строки-заголовка выше.
            surah = None
            for prev in reversed(lines):
                if prev.get("type") == "header":
                    surah = prev["surah"]
                    break
            html = qt.Aya(surah, 1).get().bismillah_uthmani if surah else None
            lines.append({"line": line_no, "type": "bismillah", "html": html})
            continue
        if kind != "text":
            raise ValueError("строка %d непонятного типа" % line_no)
        tokens = []
        for loc in locs:
            surah, ayah, p = loc.split(":")
            want = ("%s:%s" % (surah, ayah), int(p))
            # Съедаем поток до нужного токена включительно; маркеры по дороге
            # попадают на ту же строку, что и слово, перед которым они стоят.
            while pos < len(stream) and stream[pos][0] != want:
                if stream[pos][0] is not None:
                    raise ValueError(
                        "поток разошёлся: ждали %s, в потоке %s"
                        % (loc, "%s:%d" % stream[pos][0])
                    )
                tokens.append(stream[pos][1])
                pos += 1
            if pos >= len(stream):
                raise ValueError(
                    "на странице нет токена %s — расходится ГРАНИЦА СТРАНИЦЫ, "
                    "не строки; такую страницу трогать нельзя (code_v4 привязан "
                    "к шрифту страницы)" % loc
                )
            tokens.append(stream[pos][1])
            pos += 1
        lines.append({"line": line_no, "type": "text", "tokens": tokens})

    # Хвост потока (маркеры в самом конце) — на последнюю текстовую строку.
    while pos < len(stream):
        if stream[pos][0] is not None:
            raise ValueError("в потоке остались слова после последней строки QUL")
        for line in reversed(lines):
            if line.get("type") == "text":
                line["tokens"].append(stream[pos][1])
                break
        pos += 1
    return lines


def verify(before, after):
    """Ни одного слова не потеряно, не задвоено и не переставлено."""
    a = [token_id(t) for t in before]
    b = [token_id(t) for t in after]
    if a != b:
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return "порядок токенов изменился на позиции %d: было %s, стало %s" % (i, x, y)
        return "число токенов изменилось: было %d, стало %d" % (len(a), len(b))
    return None


def is_broken(data):
    nums = [l["line"] for l in data["lines"] if l.get("line") is not None]
    return bool(nums) and min(nums) == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="mushaf_data", help="папка с page{N}.json")
    ap.add_argument("--suffix", default="", help="суффикс языка, напр. _ky")
    ap.add_argument("--cache", default="qul_cache", help="кэш HTML QUL")
    ap.add_argument("--check", action="store_true", help="только показать битые")
    ap.add_argument("--pages", default="", help="список страниц через запятую")
    args = ap.parse_args()

    if args.pages:
        pages = [int(x) for x in args.pages.split(",")]
    else:
        pages = range(1, 605)

    broken = []
    for p in pages:
        path = os.path.join(args.dir, "page%d%s.json" % (p, args.suffix))
        if not os.path.exists(path):
            continue
        data = json.loads(io.open(path, encoding="utf-8").read())
        if is_broken(data):
            broken.append(p)

    print("битых страниц: %d" % len(broken))
    if args.check:
        print(broken)
        return 0
    if not broken:
        return 0

    fixed = failed = 0
    for p in broken:
        path = os.path.join(args.dir, "page%d%s.json" % (p, args.suffix))
        data = json.loads(io.open(path, encoding="utf-8").read())
        before = flat_tokens(data)
        try:
            layout = qul_layout(fetch_qul(p, args.cache))
            new_lines = rebuild(data, layout)
        except Exception as e:
            print("  стр.%-4d ОШИБКА: %s" % (p, e))
            failed += 1
            continue
        data["lines"] = new_lines
        err = verify(before, flat_tokens(data))
        if err:
            print("  стр.%-4d СВЕРКА НЕ ПРОШЛА: %s" % (p, err))
            failed += 1
            continue
        io.open(path, "w", encoding="utf-8").write(
            json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        )
        n_text = len([l for l in new_lines if l["type"] == "text"])
        print("  стр.%-4d ок: %d строк (текстовых %d)" % (p, len(new_lines), n_text))
        fixed += 1

    print("починено: %d, с ошибкой: %d" % (fixed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
