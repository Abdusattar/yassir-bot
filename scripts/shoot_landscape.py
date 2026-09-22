"""Чтение лёжа (21.09.2026): снимки и проверки, «ничего не съехало».

Просьба братьев: стоя экран узкий, читать мусхаф трудно. Лёжа колонка
идёт во всю ширину, хром ужат (см. «Чтение лёжа» в index.html). Скрипт
снимает одни и те же экраны в ТЕКУЩЕЙ версии и в HEAD (или --base) и
сравнивает попиксельно:

  - стоя всё должно совпасть до пикселя (режим лёжа стоя не включается);
  - лёжа меняется только лист мусхафа - дашборд, тренажёр и прочее тоже
    должны совпасть;
  - на листе меряет: кегль, вылезает ли строка за край (scrollWidth),
    где строка страниц, сохраняется ли место при повороте.

    python scripts/shoot_landscape.py               # всё, Chrome + WebKit
    python scripts/shoot_landscape.py --engines webkit
    python scripts/shoot_landscape.py --base HEAD~1

Снимки: logs/landscape/<движок>_<экран>_<размер>_{old,new}.png.
Playwright WebKit - не iOS: живой айфон всё равно нужен.
"""
import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import shoot_onboarding as stand            # noqa: E402
from aiohttp import web                     # noqa: E402

OUT = ROOT / "logs" / "landscape"
PORT = int(__import__("os").environ.get("LAND_PORT", "8810"))
PAGE = 50

PORTRAIT = [("stoya", 390, 844)]
LANDSCAPE = [("se", 667, 375), ("i14", 844, 390), ("promax", 932, 430), ("android", 915, 412)]

# Сцена = как дойти до экрана из дашборда. Каждый шаг - JS, пауза после.
SCENES = {
    "dash":     [],
    "mushaf":   [("document.getElementById('dash-mushaf').click()", 2500)],
    "mush_end": [("document.getElementById('dash-mushaf').click()", 2500),
                 ("var w=document.getElementById('page-wrap');w.scrollTop=w.scrollHeight", 600)],
    "meaning":  [("document.getElementById('dash-mushaf').click()", 2000),
                 # 📜 наверху с 22.09.2026; в прежней версии - вкладка внизу.
                 ("(document.getElementById('btn-meaning') || document.getElementById('tab-meaning')).click()", 1500)],
    "mywords":  [("document.getElementById('dash-mushaf').click()", 2000),
                 # «Мои слова» с 22.09.2026 - только из тренажёра слов.
                 ("document.getElementById('trainer-tab-mywords').click()", 1500)],
    "trainer":  [("document.getElementById('dash-trainer').click()", 2500)],
    "hifz":     [("document.getElementById('dash-mushaf').click()", 2000),
                 ("document.getElementById('btn-hifz').click()", 2000)],
    # Дочитал до конца, нажал «›» - следующий лист должен открыться с начала.
    "turn":     [("document.getElementById('dash-mushaf').click()", 2500),
                 ("var w=document.getElementById('page-wrap');w.scrollTop=w.scrollHeight", 600),
                 ("document.getElementById('btn-prev').click()", 2500)],
    "rev_rec":  [("document.getElementById('dash-mushaf').click()", 2000),
                 ("document.getElementById('btn-revision').click()", 2000)],
    # Лёжа только текст (22.09.2026): шапка уезжает сама, касание по пустому
    # месту возвращает, касание по слову - нет (там перевод).
    "bare":     [("document.getElementById('dash-mushaf').click()", 4500)],
    "tap":      [("document.getElementById('dash-mushaf').click()", 4500),
                 ("document.getElementById('page-wrap').click()", 700)],
    "tap_word": [("document.getElementById('dash-mushaf').click()", 4500),
                 ("document.querySelector('#ayah-text [data-tr]').click()", 700)],
}
# Что лёжа меняется намеренно - там сравнение с HEAD не требуется.
CHANGED_LAND = {"mushaf", "mush_end", "turn", "rev_rec", "bare", "tap", "tap_word", "hifz"}

MEASURE = """() => {
  var el = document.getElementById('ayah-text');
  var app = document.getElementById('app');
  if (!el || app.style.display === 'none') return null;
  var lines = el.querySelectorAll('.mushaf-line'), over = 0;
  for (var i = 0; i < lines.length; i++) {
    var d = lines[i].scrollWidth - lines[i].clientWidth;
    if (d > over) over = d;
  }
  var nav = document.getElementById('page-nav');
  var wrap = document.getElementById('page-wrap');
  var tab = document.getElementById('tabbar');
  var bar = document.getElementById('topbar').getBoundingClientRect();
  return {
    bar_bottom: Math.round(bar.bottom),
    font: getComputedStyle(el).fontSize, over_px: over, lines: lines.length,
    col: el.clientWidth, land: app.classList.contains('land'),
    nav_in_page: nav.parentNode === wrap,
    tabbar: tab ? tab.offsetHeight : 0, read_h: wrap.clientHeight, top: wrap.scrollTop,
    // Верх листа за краем: первый блок выше области чтения при прокрутке 0
    // (так лёжа срезало верх - «потолок», 21.09.2026).
    cut_top: wrap.scrollTop === 0 && el.firstElementChild ?
      Math.round(wrap.getBoundingClientRect().top - el.firstElementChild.getBoundingClientRect().top) : 0,
    page: el.getAttribute('data-page'),
    doc_overflow_x: document.documentElement.scrollWidth - document.documentElement.clientWidth
  };
}"""


def page_html(ref):
    """index.html в версии ref (None - рабочая копия), в обёртке стенда."""
    if ref is None:
        return stand.dev_index()
    src = subprocess.run(["git", "show", f"{ref}:mushaf_data/index.html"], cwd=ROOT,
                         capture_output=True, check=True).stdout.decode("utf-8")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="land-old-"))
    (tmp / "mushaf_data").mkdir()
    (tmp / "mushaf_data" / "index.html").write_text(src, encoding="utf-8", newline="")
    real, stand.ROOT = stand.ROOT, tmp
    try:
        return stand.dev_index()
    finally:
        stand.ROOT = real


def serve(pages):
    app = stand.build_app()

    def handler(html):
        async def h(request):
            stand.set_state("default")
            return web.Response(text=html, content_type="text/html")
        return h

    for name, html in pages.items():
        app.router.add_get("/" + name, handler(html))
    threading.Thread(target=lambda: web.run_app(app, host="127.0.0.1", port=PORT, print=None,
                                                handle_signals=False), daemon=True).start()
    time.sleep(3)


def shoot(pw, engine, which, scene, size):
    """Один снимок. Лист не загрузился за 15 с - одна повторная попытка
    (стенд на WebKit изредка теряет запрос листа); вторая неудача - ошибка."""
    try:
        return _shoot(pw, engine, which, scene, size)
    except Exception as e:
        print(f"    повтор {engine} {scene} {size[0]} {which}: {type(e).__name__}")
        return _shoot(pw, engine, which, scene, size)


def _shoot(pw, engine, which, scene, size):
    name, w, h = size
    b = getattr(pw, engine).launch()
    ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
    ctx.add_init_script("try{localStorage.setItem('yassir_mushaf_page','%d')}catch(e){}" % PAGE)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/{which}?bot=male")
    pg.wait_for_timeout(2500)
    for js, pause in SCENES[scene]:
        pg.evaluate(js)
        pg.wait_for_timeout(pause)
        # Лист грузится не мгновенно: снимок пустого листа (кегль 16px - это
        # ещё браузерный по умолчанию) ложная тревога, ждём строки и поздние
        # перемеры (MUSHAF_REFIT_DELAYS, 1.5 с).
        if "dash-mushaf" in js:
            pg.wait_for_function("document.querySelectorAll('#ayah-text .mushaf-line').length > 0",
                                 timeout=15000)
            pg.wait_for_timeout(1800)
    path = OUT / f"{engine}_{scene}_{name}_{which}.png"
    pg.screenshot(path=str(path))
    m = pg.evaluate(MEASURE)
    b.close()
    return path, m, errors


def same(a, b, dash=False):
    from PIL import Image, ImageChops
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if dash:
        # Карточка «пульса» - случайные точки при каждой загрузке, это шум
        # стенда, а не вёрстка: сравниваем то, что выше неё.
        ia, ib = ia.crop((0, 0, ia.width, 420)), ib.crop((0, 0, ib.width, 420))
    if ia.size != ib.size:
        return False
    return ImageChops.difference(ia, ib).getbbox() is None


def rotation_check(pw, engine):
    """Лёжа посреди листа: сменился размер (другой телефон, клавиатура,
    шапка Telegram) - текст там же; повернули стоя и обратно - не вылез.
    Стоя лист 50 влезает целиком, место там проверять нечем."""
    b = getattr(pw, engine).launch()
    ctx = b.new_context(viewport={"width": 844, "height": 390})
    ctx.add_init_script("try{localStorage.setItem('yassir_mushaf_page','%d')}catch(e){}" % PAGE)
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{PORT}/new?bot=male")
    pg.wait_for_timeout(2500)
    pg.evaluate("document.getElementById('dash-mushaf').click()")
    pg.wait_for_timeout(2500)
    share = """() => { var w=document.getElementById('page-wrap');
        var s=w.scrollHeight-w.clientHeight; return s>0 ? +(w.scrollTop/s).toFixed(2) : 0; }"""
    pg.evaluate("var w=document.getElementById('page-wrap');w.scrollTop=(w.scrollHeight-w.clientHeight)*0.5")
    pg.wait_for_timeout(400)
    before = pg.evaluate(share)
    out = []
    for w, h in ((932, 430), (390, 844), (844, 390)):
        pg.set_viewport_size({"width": w, "height": h})
        pg.wait_for_timeout(2200)
        m = pg.evaluate(MEASURE)
        out.append((f"{w}x{h}", pg.evaluate(share), m["font"], m["over_px"], m["nav_in_page"]))
    b.close()
    return before, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default="chromium,webkit")
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--scenes", default=",".join(SCENES))
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    serve({"new": page_html(None), "old": page_html(args.base)})
    from playwright.sync_api import sync_playwright
    problems = []
    with sync_playwright() as pw:
        for engine in args.engines.split(","):
            print(f"\n=== {engine} ===")
            for scene in args.scenes.split(","):
                for size in PORTRAIT + LANDSCAPE:
                    land = size[1] > size[2]
                    new, m, errs = shoot(pw, engine, "new", scene, size)
                    old, _, _ = shoot(pw, engine, "old", scene, size)
                    must_match = not (land and scene in CHANGED_LAND)
                    eq = same(new, old, dash=(scene == "dash" and not land))
                    tag = "=" if eq else ("изменено" if not must_match else "РАЗНИЦА!")
                    if must_match and not eq:
                        problems.append(f"{engine} {scene} {size[0]}: отличается от {args.base}")
                    if errs:
                        problems.append(f"{engine} {scene} {size[0]}: ошибки страницы {errs[:2]}")
                    extra = ""
                    if m and scene == "turn" and (m["page"] != str(PAGE + 1) or m["top"] > 0):
                        problems.append(f"{engine} turn {size[0]}: лист {m['page']}, прокрутка {m['top']}")
                    # Шапка лёжа: видна после «tap», спрятана после «bare» и «tap_word».
                    if m and land and scene in ("bare", "tap", "tap_word"):
                        shown = m["bar_bottom"] > 0
                        if shown != (scene == "tap"):
                            problems.append(f"{engine} {scene} {size[0]}: шапка {'видна' if shown else 'спрятана'}")
                        extra = f"  шапка низ {m['bar_bottom']}"
                    if m and scene in ("mushaf", "mush_end", "turn", "rev_rec"):
                        extra = (f"  лист {m['page']} сверху {m['top']} срез {m['cut_top']} кегль {m['font']} "
                                 f"колонка {m['col']} вылезло {m['over_px']}px "
                                 f"высота чтения {m['read_h']} меню {m['tabbar']} "
                                 f"стр.в конце {m['nav_in_page']} бок.скролл {m['doc_overflow_x']}")
                        if m["cut_top"] > 0:
                            problems.append(f"{engine} {scene} {size[0]}: верх листа срезан на {m['cut_top']}px")
                        if m["over_px"] > 1 or m["doc_overflow_x"] > 0:
                            problems.append(f"{engine} {scene} {size[0]}: вылезает {m}")
                    print(f"  {scene:<9} {size[0]:<8} {tag}{extra}")
            before, rot = rotation_check(pw, engine)
            print(f"  поворот: стоя место {before} ->", json.dumps(rot, ensure_ascii=False))
            for sz, share, font, over, nav in rot[:1]:
                if abs(share - before) > 0.12:
                    problems.append(f"{engine} поворот {sz}: место {before} -> {share}")
            for sz, share, font, over, nav in rot:
                if over > 1:
                    problems.append(f"{engine} поворот {sz}: вылезло {over}px")
    print("\nПРОБЛЕМЫ:" if problems else "\nпроблем нет")
    for p in problems:
        print("  -", p)
    print(f"снимки: {OUT}")


if __name__ == "__main__":
    main()
