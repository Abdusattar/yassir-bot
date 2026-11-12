# -*- coding: utf-8 -*-
"""Снимок пояснения к слову в настоящем приложении (12.11.2026), 390x844, обе темы.

Нажатие по слову с пояснением -> подсказка с «Подробнее» -> нажатие -> панель.
Плюс контроль: слово без пояснения - подсказка как раньше, без второй строки.

    python scripts/shoot_word_note_live.py     # -> logs/word_note/live_*.png, live_compare.jpg
"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("LAND_PORT", "8813")
import shoot_landscape as land              # noqa: E402

OUT = ROOT / "logs" / "word_note"
PAGE, LOC, PLAIN = 16, "2:104:6", "2:104:9"

FIND = """(loc) => { var el = document.querySelector('#ayah-text [data-w="' + loc + '"]');
  if (!el) return null; var r = el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; }"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    land.serve({"new": land.page_html(None)})
    from playwright.sync_api import sync_playwright
    shots = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for theme in ("light", "dark"):
            ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True,
                                color_scheme=theme)
            ctx.add_init_script("try{localStorage.setItem('yassir_mushaf_page','%d');"
                                "localStorage.setItem('yassir_theme','%s');}catch(e){}" % (PAGE, theme))
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{land.PORT}/new?bot=male")
            pg.wait_for_timeout(2500)
            pg.evaluate("document.getElementById('dash-mushaf').click()")
            pg.wait_for_function("document.querySelectorAll('#ayah-text [data-w]').length > 0", timeout=20000)
            pg.wait_for_timeout(2000)
            if theme == "light":
                w = pg.evaluate(FIND, PLAIN)
                pg.touchscreen.tap(w["x"], w["y"]); pg.wait_for_timeout(700)
                plain = pg.evaluate("document.getElementById('word-popup').innerHTML")
                print("слово без пояснения:", plain)
                pg.wait_for_timeout(2200)
            w = pg.evaluate(FIND, LOC)
            if not w:
                raise SystemExit("слово не найдено")
            pg.touchscreen.tap(w["x"], w["y"]); pg.wait_for_timeout(700)
            pop = pg.evaluate("(() => { var p = document.getElementById('word-popup'); "
                              "return [p.className, p.innerHTML, getComputedStyle(p).pointerEvents]; })()")
            print(theme, "подсказка:", pop)
            f1 = OUT / f"live_tip_{theme}.png"; pg.screenshot(path=str(f1))
            box = pg.evaluate("(() => { var r = document.querySelector('#word-popup .wn-more').getBoundingClientRect();"
                              " return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()")
            pg.touchscreen.tap(box["x"], box["y"]); pg.wait_for_timeout(600)
            opened = pg.evaluate("!document.getElementById('wn-sheet').hidden")
            f2 = OUT / f"live_sheet_{theme}.png"; pg.screenshot(path=str(f2))
            # то же касание не закрывает; касание по фону через полсекунды - закрывает
            pg.mouse.click(195, 120); pg.wait_for_timeout(300)
            closed = pg.evaluate("document.getElementById('wn-sheet').hidden")
            over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            print(theme, "панель открылась:", opened, "закрылась по фону:", closed, "вылет:", over, "ошибки JS:", errs)
            shots += [(f1, f"Подсказка, {theme}"), (f2, f"Панель, {theme}")]
            ctx.close()
        b.close()

    from PIL import Image, ImageDraw, ImageFont
    ims = [Image.open(p).convert("RGB") for p, _ in shots]
    w, h = ims[0].size
    pad, top = 30, 90
    sheet = Image.new("RGB", (len(ims) * (w + pad) + pad, h + top + pad), "#e9e6df")
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 44)
    except OSError:
        font = ImageFont.load_default()
    for i, (im, (_, title)) in enumerate(zip(ims, shots)):
        x = pad + i * (w + pad)
        d.text((x, 24), title, fill="#222", font=font)
        sheet.paste(im, (x, top))
    sheet.thumbnail((2600, 2600))
    sheet.save(OUT / "live_compare.jpg", quality=88)
    print("готово:", OUT / "live_compare.jpg")


if __name__ == "__main__":
    main()
