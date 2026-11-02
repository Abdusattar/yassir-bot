"""Шрифт листа не загрузился - не рисовать чужие слова (02.11.2026).

Повод: у tarteel пропал p328.woff2 (404), и лист 328 рисовался шрифтом
листа 327 - словами стр. 327 (Умар устаз). Скрипт на стенде листает
327 -> 328 и проверяет:
  - normal: основной CDN как есть (p328 там 404) - шрифт берётся с зеркала,
            лист рисуется глифами (data-plain нет);
  - blocked: оба CDN для p328 закрыты - лист обычным текстом (data-plain=1),
            первое слово «وَجَعَلْنَـٰهُمْ», не глифы чужого листа;
  - old: версия HEAD (или --base) в normal - для снимка «было».
Обе раскладки (madani, dm), 390x844, Chromium + WebKit.

    python scripts/shoot_v4_font_fallback.py
    python scripts/shoot_v4_font_fallback.py --engines chromium

Снимки: logs/v4_fallback/<движок>_<раскладка>_<сцена>.png - смотреть глазами
(первая строка стр. 328: «وَجَعَلْنَـٰهُمْ أَئِمَّةً يَهْدُونَ ...»).
"""
import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import shoot_landscape as land              # noqa: E402

OUT = ROOT / "logs" / "v4_fallback"
FIRST_WORD = "وَجَعَلْنَـٰهُمْ"

STATE = """() => {
  var el = document.getElementById('ayah-text');
  var first = el.querySelector('[data-arabic]');
  var fonts = performance.getEntriesByType('resource')
    .map(function (e) { return e.name; })
    .filter(function (n) { return /p32[78]\\.woff2/.test(n); });
  return { page: el.getAttribute('data-page'), plain: el.hasAttribute('data-plain'),
           v4: el.querySelectorAll('.v4-word').length,
           first: first ? first.textContent.trim() : null,
           first_arabic: first ? first.getAttribute('data-arabic').replace(/<[^>]*>/g, '') : null,
           header: document.getElementById('ayah-range').textContent,
           font: getComputedStyle(el).fontSize, fonts: fonts };
}"""


def run(pw, engine, which, layout, scene):
    b = getattr(pw, engine).launch()
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    ctx.add_init_script(
        "try{localStorage.setItem('yassir_mushaf_page','327');"
        "localStorage.setItem('yassir_mushaf_layout','%s')}catch(e){}" % layout)
    if scene == "blocked":
        ctx.route("**/p328.woff2", lambda route: route.abort())
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"http://127.0.0.1:{land.PORT}/{which}?bot=male")
    pg.wait_for_timeout(2500)
    pg.evaluate("document.getElementById('dash-mushaf').click()")
    pg.wait_for_function("document.getElementById('ayah-text').getAttribute('data-page') === '327'",
                         timeout=20000)
    pg.wait_for_timeout(1500)
    pg.evaluate("document.getElementById('btn-prev').click()")   # rtl: «‹» - следующий лист
    pg.wait_for_function("document.getElementById('ayah-text').getAttribute('data-page') === '328'",
                         timeout=20000)
    pg.wait_for_timeout(2500)
    path = OUT / f"{engine}_{layout}_{scene}_{which}.png"
    pg.screenshot(path=str(path))
    st = pg.evaluate(STATE)
    b.close()
    return path, st, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default="chromium,webkit")
    ap.add_argument("--base", default="HEAD")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    land.serve({"new": land.page_html(None), "old": land.page_html(args.base)})
    from playwright.sync_api import sync_playwright
    problems = []
    with sync_playwright() as pw:
        for engine in args.engines.split(","):
            for layout in ("madani", "dm"):
                for which, scene in (("old", "normal"), ("new", "normal"), ("new", "blocked")):
                    path, st, errs = run(pw, engine, which, layout, scene)
                    print(f"{engine:<9}{layout:<7}{which}/{scene:<8} лист {st['page']} plain={st['plain']} "
                          f"v4={st['v4']} шапка «{st['header']}» кегль {st['font']} "
                          f"первое={st['first_arabic']!r} шрифты={[f.split('/')[2] for f in st['fonts']]}")
                    if errs:
                        problems.append(f"{engine} {layout} {which}/{scene}: ошибки {errs[:2]}")
                    if which != "new":
                        continue
                    if st["first_arabic"] != FIRST_WORD:
                        problems.append(f"{engine} {layout} {scene}: первое слово {st['first_arabic']!r}")
                    if scene == "normal" and (st["plain"] or not st["v4"]):
                        problems.append(f"{engine} {layout} normal: нет глифов (зеркало не сработало?)")
                    if scene == "blocked" and (not st["plain"] or st["v4"]):
                        problems.append(f"{engine} {layout} blocked: глифы без своего шрифта")
                    if scene == "blocked" and st["first"] != FIRST_WORD:
                        problems.append(f"{engine} {layout} blocked: на экране {st['first']!r}")
    print("\nПРОБЛЕМЫ:\n  " + "\n  ".join(problems) if problems else "\nпроблем нет")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
