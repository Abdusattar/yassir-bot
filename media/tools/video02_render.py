"""Кадры ролика 2 «Ты учишь — а понимаешь?» (05.10.2026): HTML в Chromium -> PNG 1080x1920.

Аят 2:2 - лист 2 мусхафа, шрифт V4 (глифы из mushaf_data/page2.json), пословные
значения - те же, что в тренажёре (mufradat_words, Quran Academy), полный перевод -
Кулиев (quran.com, сверено 05.10.2026).

    python media/tools/video02_render.py    # PNG в media/videos/02_ty_uchish/frames/
"""
import asyncio
import json
import pathlib
import sys

from playwright.async_api import async_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from teaser01_render import HEAD  # noqa: E402  (тот же фон, шрифты и классы)

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "media" / "videos" / "02_ty_uchish" / "frames"

_page = json.load(open(ROOT / "mushaf_data" / "page2.json", encoding="utf-8"))
FONT = _page["font_url"]
_ayah = [a for a in _page["ayahs"] if a["ayah"] == 2][0]
WORDS = [(t["code_v4"], t["translation"]) for t in _ayah["tokens"] if t["type"] == "word"]
END = [t["code_v4"] for t in _ayah["tokens"] if t["type"] == "ayah_end"][0]
KULIEV = "Это Писание, в котором нет сомнения, является верным руководством для богобоязненных…"

EXTRA = """<style>
.hook { top:300px; font-size:80px; }
.ar2 { position:absolute; left:50px; right:50px; top:640px; direction:rtl; font-family:'v4';
       font-palette:--Dark; display:flex; flex-wrap:wrap; justify-content:center; gap:34px 30px; }
.w { display:flex; flex-direction:column; align-items:center; }
.w b { font-weight:normal; font-size:112px; line-height:1.35; }
.w i { direction:ltr; font-style:normal; font-family:'Cormorant Garamond', Georgia, serif;
       font-size:54px; font-weight:600; color:#f6d9a0; min-height:64px; margin-top:-6px; }
.e { font-size:112px; line-height:1.35; align-self:flex-start; }
</style>"""


def page(body, cls=""):
    return (HEAD % (FONT, cls, body)).replace("</head>", EXTRA + "</head>")


def ayah(lit, meanings, hook):
    """lit - сколько слов горит; meanings - показывать ли значения под горящими."""
    cells = []
    for i, (glyph, tr) in enumerate(WORDS):
        on = i < lit
        cells.append('<span class="w%s"><b>%s</b><i>%s</i></span>' % (
            "" if on else " dim", glyph, tr.rstrip(" –,") if (meanings and on) else ""))
    cells.append('<span class="e">%s</span>' % END)
    head = '<div class="center ru hook">Ты знаешь это<br>наизусть.</div>' if hook else ""
    return page(head + '<div class="ar2">%s</div>' % "".join(cells), "bg-dawn")


SHOTS = {
    "q.png": page('<div class="center ru" style="top:760px">А что ты сейчас<br>услышал?</div>'),
    "kuliev.png": page('<div class="center tr" style="top:640px;font-size:68px">%s</div>'
                       '<div class="center src" style="top:1180px">Сура 2, аят 2 · перевод Кулиева</div>'
                       % KULIEV, "bg-dawn"),
    "end.png": page('<div class="center ru" style="top:720px;font-size:104px">Коран отвечает</div>'
                    '<div class="center" style="top:900px;font-size:54px;letter-spacing:14px;'
                    'opacity:.75;font-weight:500">YASSIR</div>', "bg-dawn"),
}
for k in range(len(WORDS) + 1):
    SHOTS["a_%d.png" % k] = ayah(k, False, True)     # первый проход - звук
    SHOTS["b_%d.png" % k] = ayah(k, True, False)     # второй проход - смысл


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1080, "height": 1920})
        for name, html in SHOTS.items():
            await pg.set_content(html, wait_until="networkidle")
            await pg.evaluate("document.fonts.ready")
            await pg.wait_for_timeout(300)
            if name == "q.png":
                await pg.evaluate("document.body.style.background='#000'")
            await pg.screenshot(path=str(OUT / name))
            print("ok", name)
        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
