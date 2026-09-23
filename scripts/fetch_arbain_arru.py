"""«Сорок хадисов» ан-Навави по фразам - из веб-архива ar-ru.ru (23.09.2026).

Источник для тренажёра хадисов: на ar-ru.ru каждый из 42 хадисов был
разбит на фразы (арабский с огласовками, русский перевод по Нирше с
правками сайта, тайминг фразы в озвучке). Сайт умер (домен истёк), страницы
и звук целиком лежат в Wayback Machine, снимки 2013-2016.

Пословного перевода тут нет - только по фразам. Заготовка по словам
делается отдельно и ВНУТРИ фразы, а сверяет её человек.

    python scripts/fetch_arbain_arru.py            # страницы -> sources/arbain/arbain.json
    python scripts/fetch_arbain_arru.py --audio    # плюс озвучка hadisN.ogg

Только читает архив. Разовый, но повторяемый: перезапуск ничего не ломает.
"""
import argparse
import html
import json
import pathlib
import re
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "sources" / "arbain"
CDX = ("http://web.archive.org/cdx/search/cdx?url=ar-ru.ru/40h/*&output=txt"
       "&fl=timestamp,original,statuscode&filter=statuscode:200&collapse=urlkey&limit=300")
AUDIO_CDX = ("http://web.archive.org/cdx/search/cdx?url=ar-ru.ru/my/40h/*&output=txt"
             "&fl=timestamp,original,mimetype,statuscode&filter=statuscode:200&collapse=urlkey&limit=300")
PHRASE_RE = re.compile(r'<div class="il"(?:\s+tm="([^"]*)")?>\s*<div class="ph-ar">(.*?)</div>\s*'
                       r'<div class="ru-tr">(.*?)</div>', re.S)
TITLE_RE = re.compile(r'<h2[^>]*>\s*(?:<a[^>]*>)?\s*(.*?)\s*(?:</a>)?\s*</h2>', re.S)


def get(url, binary=False, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (yassir-bot arbain fetch)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            return data if binary else data.decode("utf-8", "replace")
        except Exception as e:                       # noqa: BLE001 - архив капризный, просто ждём
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def clean(s):
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    rows = [l.split() for l in get(CDX).splitlines() if "-hadith-" in l]
    pages = {}
    for ts, url, _ in rows:
        m = re.search(r"/40h/(\d+)-hadith-(\d+)", url)
        if not m:
            continue
        pages.setdefault(int(m.group(2)), []).append((ts, url))
    print("страниц в архиве:", len(pages), "хадисы", min(pages), "-", max(pages))

    out = []
    for n in sorted(pages):
        # Один хадис - несколько снимков/адресов. Поздний снимок бывает уже
        # заглушкой истёкшего домена (41-й) - идём назад, пока не найдём фразы.
        phrases, src, ts, url = [], "", None, None
        for ts, url in sorted(pages[n], reverse=True):
            src = get("http://web.archive.org/web/%s/%s" % (ts, url))
            phrases = [{"ar": clean(ar), "ru": clean(ru), "tm": tm or None}
                       for tm, ar, ru in PHRASE_RE.findall(src)]
            if phrases:
                break
            time.sleep(0.5)
        if not phrases:
            # Общий запрос к архиву отдаёт не все адреса страницы (у 41-го
            # два адреса, живой - длинный): спрашиваем по этому хадису.
            q = ("http://web.archive.org/cdx/search/cdx?url=ar-ru.ru/40h/*-hadith-%d-*&output=txt"
                 "&fl=timestamp,original,statuscode&filter=statuscode:200&limit=50" % n)
            for row in sorted((l.split() for l in get(q).splitlines() if l.strip()), reverse=True):
                ts, url = row[0], row[1]
                if not re.search(r"-hadith-%d-" % n, url):
                    continue
                src = get("http://web.archive.org/web/%s/%s" % (ts, url))
                phrases = [{"ar": clean(ar), "ru": clean(ru), "tm": tm or None}
                           for tm, ar, ru in PHRASE_RE.findall(src)]
                if phrases:
                    break
                time.sleep(0.5)
        t = TITLE_RE.search(src)
        title = clean(t.group(1)) if t else ""
        if not phrases:
            print("  %2d: фраз нет! %s" % (n, url))
        out.append({"n": n, "title": title, "source": url, "snapshot": ts, "phrases": phrases})
        print("  %2d: %2d фраз  %s" % (n, len(phrases), title[:60]))
        time.sleep(0.5)
    (OUT / "arbain.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("->", OUT / "arbain.json")

    if a.audio:
        arows = [l.split() for l in get(AUDIO_CDX).splitlines() if ".ogg" in l]
        for ts, url, *_ in arows:
            name = url.rsplit("/", 1)[-1]
            path = OUT / name
            if path.exists():
                continue
            data = get("http://web.archive.org/web/%sid_/%s" % (ts, url), binary=True)
            path.write_bytes(data)
            print("  audio", name, len(data))
            time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())
