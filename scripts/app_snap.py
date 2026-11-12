# -*- coding: utf-8 -*-
"""Сверка приложения «до и после» попиксельно (12.11.2026).

Зачем. Исходники приложения разрезаны на app_src/ (scripts/build_app.py), и дальше код
переставляется между кусками. Такая правка не должна менять НИЧЕГО на экране, а глазами
это не проверить. Скрипт поднимает стенд (настоящее приложение, как shoot_onboarding),
снимает одни и те же экраны в версии из git (--base, по умолчанию HEAD) и в рабочей копии
и сравнивает снимки пиксель в пиксель.

    python scripts/app_snap.py                    # рабочая копия против HEAD, Chromium
    python scripts/app_snap.py --base HEAD~3
    python scripts/app_snap.py --engines chromium,webkit
    python scripts/app_snap.py --only mushaf      # сцены, в имени которых есть слово

Код возврата 0 - все снимки равны; 1 - есть отличия (снимки и картинка разницы в
logs/app_snap/). Правка, которая и ДОЛЖНА менять экран, этим скриптом показывает, что
изменилось только задуманное: смотреть *_diff.png.

Чтобы снимок был повторяемым: анимации и переходы выключены, холсты (пульс на «Сегодня»
рисуется по времени) скрыты, шрифты листов отдаются с диска (sources/v4_fonts/woff2,
scripts/mirror_v4_fonts.py), а не из сети. Playwright WebKit - не iOS: живой айфон этим
не заменить.
"""
import argparse
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("LAND_PORT", "8830")
import shoot_landscape as land              # noqa: E402

OUT = ROOT / "logs" / "app_snap"
FONTS = ROOT / "sources" / "v4_fonts" / "woff2"
STILL = ("*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}"
         "canvas{visibility:hidden!important}")
MUSHAF = "document.getElementById('dash-mushaf').click()"
SHEET = "document.querySelectorAll('#ayah-text .mushaf-line').length > 0"


def tab(name):
    return "document.querySelector('.tabs-btn[data-tab=\"%s\"]').click()" % name


# Сцена: (имя, ширина, высота, лист, раскладка, [шаги]); шаг - JS или ('wait', условие) или число мс.
SCENES = [
    ("today",        390, 844, 246, "madani", [1500]),
    ("mushaf_246",   390, 844, 246, "madani", [MUSHAF, ("wait", SHEET), 2500]),
    ("mushaf_1",     390, 844, 1,   "madani", [MUSHAF, ("wait", SHEET), 2500]),
    ("mushaf_604",   390, 844, 604, "madani", [MUSHAF, ("wait", SHEET), 2500]),
    ("mushaf_dm_50", 390, 844, 50,  "dm",     [MUSHAF, ("wait", SHEET), 2500]),
    ("mushaf_turn",  390, 844, 246, "madani", [MUSHAF, ("wait", SHEET), 2500,
                                               "document.getElementById('btn-next').click()", 2500]),
    ("word_tap",     390, 844, 246, "madani", [MUSHAF, ("wait", SHEET), 2500,
                                               "document.querySelectorAll('#ayah-text [data-tr]')[5].click()", 500]),
    ("word_note",    390, 844, 16,  "madani", [MUSHAF, ("wait", SHEET), 2500,
                                               "document.querySelector('#ayah-text [data-w=\"2:104:6\"]').click()", 500,
                                               "document.querySelector('#word-popup .wn-more').click()", 500]),
    ("meaning",      390, 844, 246, "madani", [MUSHAF, ("wait", SHEET), 2000,
                                               "document.getElementById('btn-meaning').click()", 1500]),
    ("hifz",         390, 844, 246, "madani", [MUSHAF, ("wait", SHEET), 2000,
                                               "document.getElementById('btn-hifz').click()", 2000]),
    ("mushaf_land",  844, 390, 246, "madani", [MUSHAF, ("wait", SHEET), 4500]),
    ("trainers",     390, 844, 246, "madani", [1000, tab("train"), 1500]),
    ("ustaz",        390, 844, 246, "madani", [1000, tab("ustaz"), 1500]),
    ("more",         390, 844, 246, "madani", [1000, tab("more"), 1500]),
]


def fonts_from_disk(route):
    f = FONTS / route.request.url.rsplit("/", 1)[1]
    if f.exists():
        route.fulfill(status=200, content_type="font/woff2", body=f.read_bytes())
    else:
        route.continue_()


def shoot(browser, which, scene, theme):
    name, w, h, page, layout, steps = scene
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, color_scheme=theme)
    ctx.add_init_script(
        "try{localStorage.setItem('yassir_mushaf_page','%d');localStorage.setItem('yassir_theme','%s');"
        "localStorage.setItem('yassir_mushaf_layout','%s');}catch(e){}" % (page, theme, layout))
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    if FONTS.exists():
        pg.route("**/*.woff2", fonts_from_disk)
    pg.goto("http://127.0.0.1:%d/%s?bot=male" % (land.PORT, which))
    pg.add_style_tag(content=STILL)
    pg.wait_for_timeout(2000)
    for step in steps:
        if isinstance(step, int):
            pg.wait_for_timeout(step)
        elif isinstance(step, tuple):
            pg.wait_for_function(step[1], timeout=20000)
        else:
            pg.evaluate(step)
    path = OUT / ("%s_%s_%s.png" % (name, theme, which))
    pg.screenshot(path=str(path))
    ctx.close()
    return path, errors


def differ(a, b, out):
    from PIL import Image, ImageChops
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if ia.size != ib.size:
        return -1
    diff = ImageChops.difference(ia, ib)
    box = diff.getbbox()
    if not box:
        return 0
    mask = diff.convert("L").point(lambda v: 255 if v else 0)
    n = mask.histogram()[255]
    red = Image.new("RGB", ia.size, (255, 0, 60))
    Image.composite(red, ib.point(lambda v: 128 + v // 2), mask).save(out)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--engines", default="chromium")
    ap.add_argument("--only", default="")
    ap.add_argument("--themes", default="light,dark")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.png"):
        f.unlink()
    if not FONTS.exists():
        print("нет sources/v4_fonts/woff2 - шрифты пойдут из сети, снимки могут гулять "
              "(python scripts/mirror_v4_fonts.py)")
    land.serve({"old": land.page_html(a.base), "new": land.page_html(None)})
    scenes = [s for s in SCENES if a.only in s[0]]
    from playwright.sync_api import sync_playwright
    bad = total = 0
    with sync_playwright() as pw:
        for engine in a.engines.split(","):
            browser = getattr(pw, engine).launch()
            for scene in scenes:
                for theme in a.themes.split(","):
                    total += 1
                    try:
                        old, e1 = shoot(browser, "old", scene, theme)
                        new, e2 = shoot(browser, "new", scene, theme)
                    except Exception as e:
                        bad += 1
                        print("  ОШИБКА  %-8s %-13s %-5s %s" % (engine, scene[0], theme, str(e).splitlines()[0][:90]))
                        continue
                    n = differ(old, new, OUT / ("%s_%s_diff.png" % (scene[0], theme)))
                    if n:
                        # Один повтор: экран с поздней подгрузкой (плитки уроков) изредка
                        # снимается на кадр раньше. Настоящее отличие повторится.
                        old, e1 = shoot(browser, "old", scene, theme)
                        new, e2 = shoot(browser, "new", scene, theme)
                        n = differ(old, new, OUT / ("%s_%s_diff.png" % (scene[0], theme)))
                    js = (" | ошибки JS: %s" % (e1 + e2)[:2]) if (e1 or e2) else ""
                    if n or js:
                        bad += 1
                    print("  %s  %-8s %-13s %-5s%s%s" % (
                        "равны " if not n else "РАЗНЫЕ", engine, scene[0], theme,
                        "" if not n else (" размер другой" if n < 0 else " %d пикс." % n), js))
            browser.close()
    print("%s: снимков %d, с отличиями %d (%s против рабочей копии); папка logs/app_snap/"
          % ("ВСЁ РАВНО" if not bad else "ЕСТЬ ОТЛИЧИЯ", total, bad, a.base))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
