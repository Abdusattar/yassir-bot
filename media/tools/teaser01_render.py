"""Кадры с текстом для видео 1 (тизер): рисуем HTML в Chromium и снимаем PNG 1080x1920."""
import asyncio
import pathlib
from playwright.async_api import async_playwright

OUT = pathlib.Path(__file__).parent
FONT = "https://static-cdn.tarteel.ai/qul/fonts/quran_fonts/v4-tajweed/woff2/p252.woff2"
WORDS = ["ﳝ", "ﳞ", "ﳟ", "ﳠ", "ﳡ"]  # أَلَا بِذِكْرِ ٱللَّهِ تَطْمَئِنُّ ٱلْقُلُوبُ

HEAD = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&display=block" rel="stylesheet">
<style>
@font-face { font-family: 'v4'; src: url('%s'); font-display: block; }
@font-palette-values --Dark { font-family: 'v4'; base-palette: 1; }
html,body { margin:0; width:1080px; height:1920px; overflow:hidden; }
body { font-family: 'Cormorant Garamond', Georgia, serif; color:#f3ead8; }
.bg-dawn { background:
   radial-gradient(ellipse 900px 700px at 50%% 105%%, rgba(232,160,80,.55), rgba(232,160,80,0) 70%%),
   radial-gradient(ellipse 700px 500px at 50%% 40%%, rgba(90,70,120,.35), rgba(0,0,0,0) 70%%),
   linear-gradient(#070a14, #141226 55%%, #2a1c24); }
.center { position:absolute; left:65px; right:65px; text-align:center; }
.ru { font-size:84px; line-height:1.18; font-weight:600; letter-spacing:.5px;
      text-shadow: 0 2px 24px rgba(0,0,0,.65); }
.ar { direction:rtl; font-family:'v4'; font-palette:--Dark; font-size:118px; line-height:1.6;
      display:flex; flex-wrap:wrap; justify-content:center; gap:0 26px; }
.ar span { transition:none; }
.dim { opacity:.28; }
.tr { font-size:64px; line-height:1.25; font-weight:500; }
.src { font-size:38px; opacity:.6; letter-spacing:1px; }
</style></head><body class="%s">%s</body></html>"""


def page(body, cls=""):
    return HEAD % (FONT, cls, body)


def ayah(lit, with_tr):
    spans = "".join('<span class="%s">%s</span>' % ("" if i < lit else "dim", w) for i, w in enumerate(WORDS))
    tr = ('<div class="center tr" style="top:880px">Разве не поминанием Аллаха<br>утешаются сердца?</div>'
          '<div class="center src" style="top:1100px">Сура 13, аят 28 · перевод Кулиева</div>') if with_tr else ""
    return page('<div class="center ar" style="top:430px">%s</div>%s' % (spans, tr), "bg-dawn")


SHOTS = {
    "hook.png": (page('<div style="position:absolute;left:-200px;right:-200px;top:470px;height:520px;background:radial-gradient(ellipse at center, rgba(0,0,0,.72), rgba(0,0,0,.45) 45%%, rgba(0,0,0,0) 72%%)"></div><div class="center ru" style="top:620px">Сколько голосов<br>ты слышишь за день?</div>'), True),
    "q.png": (page('<div class="center ru" style="top:760px">А Его слово?</div>', ""), False),
    "soon.png": (page('<div class="center ru" style="top:760px;font-size:110px">Скоро.</div>', "bg-dawn"), False),
    "soon_y.png": (page('<div class="center ru" style="top:720px;font-size:110px">Скоро.</div><div class="center" style="top:900px;font-size:54px;letter-spacing:14px;opacity:.75;font-weight:500">YASSIR</div>', "bg-dawn"), False),
}
for k in range(len(WORDS) + 1):
    SHOTS["ayah_%d.png" % k] = (ayah(k, True), False)


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1080, "height": 1920})
        for name, (html, transparent) in SHOTS.items():
            if name != "soon_y.png": continue
            await pg.set_content(html, wait_until="networkidle")
            await pg.evaluate("document.fonts.ready")
            await pg.wait_for_timeout(300)
            if name == "q.png":
                await pg.evaluate("document.body.style.background='#000'")
            await pg.screenshot(path=str(OUT / name), omit_background=transparent)
            print("ok", name)
        await b.close()

asyncio.run(main())
