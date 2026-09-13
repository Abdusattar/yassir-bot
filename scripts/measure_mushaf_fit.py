"""Замер подгонки шрифта мусхафа по страницам (13.09.2026).

Зачем: пользователь на айфонах видит, что шрифт листа то мельче, то крупнее
при листании, а на крупном текст вылезает за горизонтальные края. Эмулятора
Safari с машины нет, но САМА подгонка (clampFontToFit) — обычный JS, один и
тот же на любом движке. Значит вопрос решается замером, а не эмуляцией:
прогоняем страницы на телефонных ширинах и печатаем, какой размер вышел и
осталось ли вылезание после самопроверки.

Скрипт постоянный. Ширины по умолчанию — настоящие CSS-ширины айфонов:
320 (SE), 375 (mini/8), 390 (13/14), 414 (Plus).

    python scripts/measure_mushaf_fit.py                    # стр. 2-20
    python scripts/measure_mushaf_fit.py --pages 2-60 --widths 375,390
"""
import argparse
import json
import pathlib
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import shoot_onboarding as stand            # noqa: E402
from aiohttp import web                     # noqa: E402

PORT = 8803
RESULTS = []

# Меряем ТЕМ ЖЕ правилом, что и самопроверка в clampFontToFit: строка как она
# отрисована, с боевым justify, без .measuring. Нас интересует не натуральная
# ширина слов, а факт «вылезло за край или нет».
MEASURE_JS = """
<script>
(function () {
  var q = new URLSearchParams(location.search);
  if (!q.get('measure')) return;
  var pages = q.get('measure').split(',').map(Number);
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var read = function (page) {
    var el = document.getElementById('ayah-text');
    var lines = el.querySelectorAll('.mushaf-line');
    var worst = 1, over = 0;
    for (var i = 0; i < lines.length; i++) {
      var w = lines[i].clientWidth;
      if (!w) continue;
      var r = lines[i].scrollWidth / w;
      if (r > 1.005) { over++; if (r > worst) worst = r; }
    }
    return {
      page: page, lines: lines.length,
      avail: el.clientWidth,
      font: parseFloat(getComputedStyle(el).fontSize.replace('px', '')),
      worst: Math.round(worst * 1000) / 1000, over: over
    };
  };
  window.addEventListener('load', function () {
    (async function () {
      document.title = 'step:load';
      await wait(1500);
      var d = document.getElementById('dash-mushaf');
      document.title = 'step:dash=' + !!d;
      d.click();
      await wait(1800);
      var out = [];
      for (var i = 0; i < pages.length; i++) {
        document.title = 'step:go' + pages[i];
        window.__goPage(pages[i]);
        await wait(900);
        await document.fonts.ready;
        await wait(250);
        out.push(read(pages[i]));
      }
      await fetch('/dev/measure', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ width: window.innerWidth, rows: out })
      });
      document.title = 'done';
    })();
  });
})();
</script>
"""

# Переход по номеру страницы: у приложения он спрятан в замыкании, поэтому
# пользуемся его же полем ввода - той дорогой, что и человек.
GO_JS = """
<script>
window.__goPage = function (n) {
  var ind = document.getElementById('page-indicator');
  var inp = document.getElementById('page-jump-input');
  ind.click();
  inp.value = String(n);
  inp.blur();
};
</script>
"""


def build():
    app = stand.build_app()

    async def index(request):
        return web.Response(text=stand.dev_index() + GO_JS + MEASURE_JS,
                            content_type="text/html")

    async def measure(request):
        RESULTS.append(await request.json())
        return web.json_response({"ok": True})

    async def frame(request):
        w = request.query.get("w", "390")
        return web.Response(content_type="text/html", text=(
            "<style>html,body{margin:0}iframe{border:0;display:block;"
            "width:%spx;height:844px}</style>"
            "<iframe src='/m?bot=male&measure=%s'></iframe>"
            % (w, request.query.get("measure", ""))))

    app.router.add_post("/dev/measure", measure)
    app.router.add_get("/mframe", frame)
    # Свой путь, а не "/": маршрут "/" стенд уже занял, и второй такой же
    # просто никогда не сработает (полчаса на это ушло 13.09.2026).
    app.router.add_get("/m", index)
    return app


# Чтение той же меркой, что самопроверка clampFontToFit, но снаружи —
# через Playwright. Возвращает размер шрифта и худшее вылезание.
READ_JS = """() => {
  const el = document.getElementById('ayah-text');
  const lines = el.querySelectorAll('.mushaf-line');
  let worst = 1, over = 0;
  for (const l of lines) {
    const w = l.clientWidth;
    if (!w) continue;
    const r = l.scrollWidth / w;
    if (r > 1.005) { over++; if (r > worst) worst = r; }
  }
  return { lines: lines.length, avail: el.clientWidth,
           font: parseFloat(getComputedStyle(el).fontSize),
           worst: Math.round(worst * 1000) / 1000, over };
}"""


def run_engine(engine, device, width, pages, slow_font):
    """Прогон в настоящем браузере Playwright. webkit — движок Safari; это не
    iOS целиком (системные шрифты там свои), но метрики текста считает WebKit,
    а не Blink, и ради них всё и затевается.

    slow_font — задержка на файлы шрифта. Подозрение 13.09.2026: на телефоне
    шрифт V4 приезжает позже замера, подгонка считает по запасному, и размер
    скачет от страницы к странице. Здесь это можно вызвать нарочно."""
    from playwright.sync_api import sync_playwright

    rows = []
    with sync_playwright() as pw:
        browser = getattr(pw, engine).launch()
        if device:
            ctx = browser.new_context(**pw.devices[device])
        else:
            ctx = browser.new_context(viewport={"width": width, "height": 844})
        page = ctx.new_page()
        if slow_font:
            def hold(route):
                time.sleep(slow_font / 1000.0)
                route.continue_()
            page.route("**/*.ttf", hold)
            page.route("**/*.woff*", hold)
        page.goto("http://127.0.0.1:%d/m?bot=male" % PORT)
        page.wait_for_selector("#dash-mushaf", timeout=15000)
        page.click("#dash-mushaf")
        page.wait_for_timeout(1800)
        for n in pages:
            page.click("#page-indicator")
            page.fill("#page-jump-input", str(n))
            page.press("#page-jump-input", "Enter")
            page.wait_for_timeout(1100 + (slow_font or 0))
            row = page.evaluate(READ_JS)
            row["page"] = n
            rows.append(row)
        browser.close()
    return rows


def report(title, rows):
    if not rows:
        print(title + ": пусто")
        return
    fonts = [r["font"] for r in rows]
    bad = [r for r in rows if r["over"]]
    print("\n=== %s (лист %d px) ===" % (title, rows[0]["avail"]))
    print("  шрифт: %.1f–%.1f px, разброс %.1f px"
          % (min(fonts), max(fonts), max(fonts) - min(fonts)))
    print("  страниц с вылезанием: %d из %d" % (len(bad), len(rows)))
    for r in bad[:8]:
        print("    стр. %d — %d строк(и) за краем, худшая %.1f%%, шрифт %.1f"
              % (r["page"], r["over"], (r["worst"] - 1) * 100, r["font"]))


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
    ap.add_argument("--pages", default="2-20")
    ap.add_argument("--widths", default="320,375,390,414")
    ap.add_argument("--engine", default="", help="webkit | chromium (Playwright)")
    ap.add_argument("--device", default="", help="профиль Playwright, напр. «iPhone 13»")
    ap.add_argument("--slow-font", type=int, default=0,
                    help="задержать файлы шрифта, мс — проверка гонки замера")
    args = ap.parse_args()

    pages = parse_pages(args.pages)
    widths = [int(w) for w in args.widths.split(",")]

    app = build()
    threading.Thread(
        target=lambda: web.run_app(app, host="127.0.0.1", port=PORT, print=None,
                                   handle_signals=False),
        daemon=True).start()
    time.sleep(3)

    if args.engine:
        for w in widths:
            rows = run_engine(args.engine, args.device, w, pages, args.slow_font)
            name = "%s %s" % (args.engine, args.device or ("ширина %d" % w))
            if args.slow_font:
                name += ", шрифт с задержкой %d мс" % args.slow_font
            report(name, rows)
            if args.device:
                break
        return

    chrome = stand.find_chrome()

    for w in widths:
        RESULTS.clear()
        budget = 4000 + 1400 * len(pages)
        subprocess.run([
            chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--window-size=%d,844" % w, "--virtual-time-budget=%d" % budget,
            "--dump-dom",
            "http://127.0.0.1:%d/mframe?w=%d&measure=%s"
            % (PORT, w, ",".join(map(str, pages))),
        ], capture_output=True)
        if not RESULTS:
            print("ширина %d: ответа не пришло" % w)
            continue
        rows = RESULTS[0]["rows"]
        fonts = [r["font"] for r in rows]
        bad = [r for r in rows if r["over"]]
        print("\n=== ширина %d (лист %d px) ===" % (w, rows[0]["avail"]))
        print("  шрифт: %.1f–%.1f px, разброс %.1f px"
              % (min(fonts), max(fonts), max(fonts) - min(fonts)))
        print("  страниц с вылезанием: %d из %d" % (len(bad), len(rows)))
        for r in bad:
            print("    стр. %d — %d строк(и) за краем, худшая %.1f%%, шрифт %.1f"
                  % (r["page"], r["over"], (r["worst"] - 1) * 100, r["font"]))
        order = sorted(rows, key=lambda r: r["font"])
        print("  мельче всех: " + ", ".join("стр.%d %.1f" % (r["page"], r["font"])
                                            for r in order[:3]))
        print("  крупнее всех: " + ", ".join("стр.%d %.1f" % (r["page"], r["font"])
                                             for r in order[-3:]))


if __name__ == "__main__":
    main()
