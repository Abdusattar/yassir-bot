# -*- coding: utf-8 -*-
"""Свои копии шрифтов мусхафа V4 (12.11.2026): 604 файла p{N}.woff2 для yassirilm.com/v4/.

Зачем: шрифт листа (86 КБ) - главный вес страницы, а лежал только на чужом CDN
(tarteel: кэш 4 часа, внутри Telegram service worker'а нет - шрифты качались
заново каждый день; оттуда же сбои стр. 328 02.11 и стр. 246 12.11). Теперь
основной адрес - свой сервер с бессрочным кэшем, tarteel и quran.foundation -
запасные (loadV4Face в index.html).

Качает с tarteel (не ответил - с зеркала), проверяет, что в файле есть все коды
слов своего листа по обеим раскладкам (та же сверка, что scripts/check_v4_fonts.py),
и кладёт в sources/v4_fonts/woff2/ (не в git: 52 МБ). На сервер - архивом:

    python scripts/mirror_v4_fonts.py             # скачать недостающие и проверить все
    tar -C sources/v4_fonts/woff2 -cf v4.tar .  &&  scp v4.tar ...  &&  распаковать в /var/www/yassir-app/v4/
"""
import io
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor

from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from check_v4_fonts import MAIN, MIRROR, fetch, needed_codes  # noqa: E402

OUT = ROOT / "sources" / "v4_fonts" / "woff2"


def one(page, codes):
    f = OUT / f"p{page}.woff2"
    src = "есть"
    if not f.exists():
        for src, tpl in (("tarteel", MAIN), ("зеркало", MIRROR)):
            status, body = fetch(tpl.format(page))
            if status == 200 and body:
                f.write_bytes(body)
                break
        else:
            return page, src, "не скачался"
    try:
        cmap = TTFont(io.BytesIO(f.read_bytes())).getBestCmap()
    except Exception as e:
        f.unlink()
        return page, src, f"не читается ({e})"
    miss = [c for c in codes if c not in cmap]
    if miss:
        f.unlink()
        return page, src, f"нет {len(miss)} из {len(codes)} кодов"
    return page, src, None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    need = needed_codes()
    bad, from_mirror = 0, []
    with ThreadPoolExecutor(4) as ex:
        for page, src, problem in ex.map(lambda p: one(p, need[p]), sorted(need)):
            if problem:
                bad += 1
                print(f"p{page}: {problem}")
            elif src == "зеркало":
                from_mirror.append(page)
    files = list(OUT.glob("p*.woff2"))
    print(f"листов {len(need)}, файлов {len(files)}, {sum(f.stat().st_size for f in files) // 1048576} МБ, "
          f"с проблемами {bad}, с зеркала: {from_mirror or 'нет'}")
    sys.exit(1 if bad or len(files) != 604 else 0)


if __name__ == "__main__":
    main()
