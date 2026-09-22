"""Заучивание лёжа и половина листа стоя (22.09.2026): снимки глазами.

Решение пользователя: лёжа и есть «Крупно» - на всех этапах, строкой как в
мусхафе; слева колонка счётчика; стоя на этапе 2 видна только своя
половина на своём месте; переход с чужого листа - строкой под листом.
Кнопки «Крупно» больше нет. Скрипт ставит указатель на нужную единицу и
входит в режим теми же кнопками, что человек, стоя и лёжа.

    python scripts/shoot_hifz_land.py               # всё
    python scripts/shoot_hifz_land.py --only s2b,s3
    python scripts/shoot_hifz_land.py --engine webkit

Снимки: logs/hifz_land/<сцена>_<размер>.png. Playwright WebKit - не iOS.
"""
import argparse
import pathlib
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import shoot_onboarding as stand            # noqa: E402
from core import mushaf_words               # noqa: E402
from aiohttp import web                     # noqa: E402

OUT = ROOT / "logs" / "hifz_land"
PORT = int(__import__("os").environ.get("HIFZ_PORT", "8811"))
PAGE = 3
SIZES = [("stoya", 390, 844), ("se", 667, 375), ("i14", 844, 390)]

# сцена -> (строка, этап) указателя; None - указателя нет, режим спросит место.
SCENES = {
    "s1":    (2, 1),      # строка в середине листа, переход на этом же листе
    "s1end": (14, 1),     # последняя строка - переход с чужого листа
    "s2a":   (0, 2),      # первая половина
    "s2b":   (7, 2),      # вторая половина - переход с чужого листа
    "s3":    (0, 3),      # весь лист
    "pick":  None,        # выбор места
    "rec":   (0, 2),      # открыта запись сдачи
    "bare":  (0, 2),      # лёжа шапка уехала сама
}

MEASURE = """() => {
  var app = document.getElementById('app'), wrap = document.getElementById('page-wrap');
  var el = document.getElementById('ayah-text');
  var shown = Array.prototype.filter.call(el.children, function (c) {
    return getComputedStyle(c).display !== 'none' && getComputedStyle(c).visibility !== 'hidden';
  }).length;
  var head = document.getElementById('hifz-head').getBoundingClientRect();
  var foot = document.getElementById('hifz-foot').getBoundingClientRect();
  var lines = el.querySelectorAll('.mushaf-line'), over = 0;
  for (var i = 0; i < lines.length; i++) over = Math.max(over, lines[i].scrollWidth - lines[i].clientWidth);
  var xt = el.querySelector('.hifz-xtail'), wr = wrap.getBoundingClientRect();
  var first = Array.prototype.filter.call(el.children, function (c) {
    return getComputedStyle(c).display !== 'none'; })[0];
  return { xt_cut: xt ? Math.round(xt.getBoundingClientRect().bottom - wr.bottom) : null,
           first_under_head: first ? Math.round(head.bottom - first.getBoundingClientRect().top) : null,
           land: app.classList.contains('land'), bare: app.classList.contains('bare'),
           font: getComputedStyle(el).fontSize, shown: shown, xtail: !!el.querySelector('.hifz-xtail'),
           head_bottom: Math.round(head.bottom), foot: [Math.round(foot.left), Math.round(foot.width), Math.round(foot.height)],
           over: over, big_btn: !!document.getElementById('hifz-big-btn'),
           doc_x: document.documentElement.scrollWidth - document.documentElement.clientWidth };
}"""


def build():
    app = stand.build_app()

    async def page(request):
        scene = request.query.get("s", "s1")
        stand.set_state("stage2")
        at = SCENES[scene]
        if at is None:
            import sqlite3
            with sqlite3.connect(str(stand.TMP / "hadiths.db")) as conn:
                conn.execute("DELETE FROM mushaf_hifz_pointer WHERE user_id=?", (stand.STUDENT,))
        else:
            mushaf_words.set_hifz_pointer(stand.STUDENT, PAGE, at[0], at[1])
        return web.Response(text=stand.dev_index(), content_type="text/html")

    app.router.add_get("/h", page)
    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--engine", default="chromium")
    args = ap.parse_args()
    only = [s for s in args.only.split(",") if s]

    threading.Thread(target=lambda: web.run_app(build(), host="127.0.0.1", port=PORT, print=None,
                                                handle_signals=False), daemon=True).start()
    time.sleep(3)
    OUT.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    problems = []
    with sync_playwright() as pw:
        b = getattr(pw, args.engine).launch()
        for scene in SCENES:
            if only and scene not in only:
                continue
            for name, w, h in SIZES:
                ctx = b.new_context(viewport={"width": w, "height": h})
                ctx.add_init_script("try{localStorage.setItem('yassir_mushaf_page','%d')}catch(e){}" % PAGE)
                pg = ctx.new_page()
                errors = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.goto(f"http://127.0.0.1:{PORT}/h?s={scene}&bot=male")
                pg.wait_for_timeout(2500)
                pg.evaluate("document.getElementById('dash-mushaf').click()")
                pg.wait_for_function("document.querySelectorAll('#ayah-text .mushaf-line').length > 0",
                                     timeout=15000)
                pg.wait_for_timeout(1500)
                pg.evaluate("document.getElementById('btn-hifz').click()")
                pg.wait_for_timeout(2500)
                if scene == "rec":
                    pg.evaluate("document.getElementById('hifz-submit').click()")
                    pg.wait_for_timeout(900)
                if scene == "bare":
                    pg.wait_for_timeout(4000)
                path = OUT / f"{scene}_{name}.png"
                pg.screenshot(path=str(path))
                m = pg.evaluate(MEASURE)
                ctx.close()
                print(f"  {scene:<6} {name:<6} {m}")
                if errors:
                    problems.append(f"{scene} {name}: ошибки {errors[:2]}")
                if m["over"] > 1 or m["doc_x"] > 0:
                    problems.append(f"{scene} {name}: вылезает {m['over']} / {m['doc_x']}")
                if m["big_btn"]:
                    problems.append(f"{scene} {name}: кнопка «Крупно» на месте")
                land = w > h
                if land != m["land"]:
                    problems.append(f"{scene} {name}: land={m['land']}")
                if scene in ("s1end", "s2b") and not m["xtail"]:
                    problems.append(f"{scene} {name}: нет перехода с чужого листа")
                # Только стоя: лёжа этапы 2-3 длиннее экрана и прокручиваются,
                # переход там и должен быть ниже края.
                if not land and m["xt_cut"] is not None and m["xt_cut"] > 0 and scene != "rec":
                    problems.append(f"{scene} {name}: переход обрезан снизу на {m['xt_cut']}px")
                if land and scene not in ("bare", "pick") and m["first_under_head"] and m["first_under_head"] > 2:
                    problems.append(f"{scene} {name}: первая строка под шапкой на {m['first_under_head']}px")
                if scene == "bare" and land and m["head_bottom"] > 0:
                    problems.append(f"{scene} {name}: шапка не уехала")
                if scene == "pick" and land and m["head_bottom"] <= 0:
                    problems.append(f"{scene} {name}: шапка уехала посреди выбора")
        b.close()
    print("\nПРОБЛЕМЫ:" if problems else "\nпроблем нет")
    for p in problems:
        print("  " + p)


if __name__ == "__main__":
    main()
