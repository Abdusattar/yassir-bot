"""Таблица естественных ширин листов мусхафа для подгонки кегля (13.09.2026).

Зачем: на айфонах кегль листа подбирался замером, а замер в WebKit идёт до
раскладки шрифта (document.fonts.ready приходит раньше, bugs.webkit.org
174030/225790/217047). Отсюда неверный первый кадр и поправка через
полсекунды — заметное дёргание при листании. Решение пользователя: знать
размер заранее, а замер оставить проверкой.

Кегль листа = БАЗА × доступная ширина / естественная ширина самой длинной
строки × запас. Естественная ширина — свойство текста и шрифта, а не
телефона: один и тот же шрифт на любом Blink даёт те же ширины (HarfBuzz
везде). Поэтому её можно один раз снять здесь для всех 604 листов и
положить в index.html. Разницу движков (Safari против Chrome, ~1–2%)
приложение ловит само одним коэффициентом и помнит его на телефоне.

Замер — той же меркой, что clampFontToFit: класс .measuring (снимает
растягивание), кегль 40px, max(scrollWidth) по .mushaf-line.

    python scripts/measure_mushaf_widths.py            # снять все 604 → JSON
    python scripts/measure_mushaf_widths.py --pages 1-20
    python scripts/measure_mushaf_widths.py --apply    # JSON → index.html

Перезапускать, когда меняется раскладка page*.json, шрифт листа или CSS,
влияющий на ширину слов (.marker, .v4-word). Если забыть — не страшно:
проверка в приложении поправит кегль и пришлёт /fitlog, по нему и видно.
"""
import argparse
import json
import pathlib
import re
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import measure_mushaf_fit as fit           # noqa: E402  (стенд и порт)
from aiohttp import web                    # noqa: E402

OUT = ROOT / "scripts" / "mushaf_fit_widths.json"
INDEX = ROOT / "mushaf_data" / "index.html"
BEGIN, END = "/* FIT_WIDTHS:BEGIN */", "/* FIT_WIDTHS:END */"
BASE = 40

MEASURE = """() => {
  const el = document.getElementById('ayah-text');
  const lines = el.querySelectorAll('.mushaf-line');
  const prev = el.style.fontSize;
  el.classList.add('measuring');
  el.style.fontSize = '%dpx';
  let w = 0;
  for (const l of lines) if (l.scrollWidth > w) w = l.scrollWidth;
  el.classList.remove('measuring');
  el.style.fontSize = prev;
  return { w, lines: lines.length };
}""" % BASE

# Метка внутри #ayah-text: reveal() заменяет innerHTML целиком, значит метка
# пропала — на экране уже текст новой страницы, а не старой с новым номером.
MARK = """() => {
  const i = document.createElement('i');
  i.id = 'probe-old';
  document.getElementById('ayah-text').appendChild(i);
}"""


def measure(pages):
    from playwright.sync_api import sync_playwright

    app = fit.build()
    threading.Thread(
        target=lambda: web.run_app(app, host="127.0.0.1", port=fit.PORT,
                                   print=None, handle_signals=False),
        daemon=True).start()
    time.sleep(3)

    rows = {}
    if OUT.exists():
        rows = {int(k): v for k, v in json.loads(OUT.read_text("utf-8"))["pages"].items()}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
        page.goto("http://127.0.0.1:%d/m?bot=male" % fit.PORT)
        page.wait_for_selector("#dash-mushaf", timeout=15000)
        page.click("#dash-mushaf")
        page.wait_for_timeout(1500)
        started = time.time()
        for i, n in enumerate(pages):
            page.evaluate(MARK)
            page.click("#page-indicator")
            page.fill("#page-jump-input", str(n))
            page.press("#page-jump-input", "Enter")
            page.wait_for_function(
                "() => !document.getElementById('probe-old')"
                " && document.querySelectorAll('#ayah-text .mushaf-line').length"
                " && document.fonts.status === 'loaded'", timeout=30000)
            page.wait_for_timeout(300)
            r = page.evaluate(MEASURE)
            # Второй замер через паузу: если шрифт ещё ложился, числа разойдутся.
            page.wait_for_timeout(300)
            r2 = page.evaluate(MEASURE)
            if r2["w"] != r["w"]:
                page.wait_for_timeout(1200)
                r2 = page.evaluate(MEASURE)
            rows[n] = {"w": r2["w"], "lines": r2["lines"]}
            if (i + 1) % 50 == 0:
                print("  %d/%d, %.0f с" % (i + 1, len(pages), time.time() - started), flush=True)
                save(rows)
        browser.close()
    save(rows)
    return rows


def save(rows):
    OUT.write_text(json.dumps({"base": BASE, "pages": {str(k): rows[k] for k in sorted(rows)}},
                              ensure_ascii=False, indent=0), "utf-8")


def apply():
    data = json.loads(OUT.read_text("utf-8"))
    pages = {int(k): v["w"] for k, v in data["pages"].items()}
    missing = [n for n in range(1, 605) if not pages.get(n)]
    if missing:
        raise SystemExit("в таблице нет листов: %s" % missing[:20])
    arr = "[0," + ",".join(str(pages[n]) for n in range(1, 605)) + "]"
    block = "%s\n  var MUSHAF_FIT_W = %s;\n  %s" % (BEGIN, arr, END)
    html = INDEX.read_text("utf-8")
    if BEGIN not in html:
        raise SystemExit("в index.html нет метки %s" % BEGIN)
    html = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block, html, flags=re.S)
    INDEX.write_text(html, "utf-8")
    ws = sorted(pages.values())
    print("вписано 604 листа; ширина при %dpx: %d–%d, медиана %d"
          % (data["base"], ws[0], ws[-1], ws[len(ws) // 2]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default="1-604")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.apply:
        apply()
        return
    rows = measure(fit.parse_pages(args.pages))
    ws = sorted(r["w"] for r in rows.values())
    print("снято %d листов; ширина %d–%d → %s" % (len(ws), ws[0], ws[-1], OUT))


if __name__ == "__main__":
    main()
