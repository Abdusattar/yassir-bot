"""Кадры ролика 4 «Одно слово: هُدًى» (05.10.2026) -> PNG 1080x1920.

1:6 (лист 1) и 2:2 (лист 2) шрифтом V2 (quran.com; у V4-таджвид дефект глифа на стр. 2).
Тексты сверены: Кулиев (quran.com), ас-Саади на 1:6 дословно, корень ه د ي по QAC.
Сценарий и рецензия - media/videos/04_slovo_huda/README.md.

    python media/tools/video04_render.py   # PNG в media/videos/04_slovo_huda/frames/
"""
import asyncio
import json
import pathlib
import sys

from playwright.async_api import async_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from teaser01_render import HEAD  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "media" / "videos" / "04_slovo_huda" / "frames"
V2 = "https://static-cdn.tarteel.ai/qul/fonts/quran_fonts/v2/woff2/p%d.woff2"


def _glyphs(page, surah, ayah):
    d = json.load(open(ROOT / "mushaf_data" / ("page%d.json" % page), encoding="utf-8"))
    a = [x for x in d["ayahs"] if x["surah"] == surah and x["ayah"] == ayah][0]
    words = [t["code_v4"] for t in a["tokens"] if t["type"] == "word"]
    end = [t["code_v4"] for t in a["tokens"] if t["type"] == "ayah_end"][0]
    return words, end


W16, E16 = _glyphs(1, 1, 6)
W22, E22 = _glyphs(2, 2, 2)

EXTRA = """<style>
@font-face { font-family:'p1'; src:url('%s'); font-display:block; }
@font-face { font-family:'p2'; src:url('%s'); font-display:block; }
.a1 { font-family:'p1'; } .a2 { font-family:'p2'; }
.arw { position:absolute; left:65px; right:65px; direction:rtl; text-align:center;
       display:flex; flex-wrap:wrap; justify-content:center; gap:0 26px; line-height:1.6; }
.cap { font-size:70px; font-weight:600; line-height:1.18; }
.mean { font-size:66px; font-weight:600; color:#f6d9a0; line-height:1.5; }
.mean .off { opacity:0; }
.gold { color:#f3d9a4; }
</style>""" % (V2 % 1, V2 % 2)


def page(body):
    return (HEAD % (V2 % 1, "bg-dawn", body)).replace("</head>", EXTRA + "</head>")


def ayah16(lit, size, top):
    sp = "".join('<span class="%s">%s</span>' % ("" if i < lit else "dim", w) for i, w in enumerate(W16))
    return '<div class="arw a1" style="top:%dpx;font-size:%dpx">%s<span>%s</span></div>' % (top, size, sp, E16)


def ayah22(lit_from, lit):
    sp = "".join('<span class="%s">%s</span>' % ("" if lit_from <= i < lit else "dim", w)
                 for i, w in enumerate(W22))
    return '<div class="arw a2" style="top:470px;font-size:104px">%s<span>%s</span></div>' % (sp, E22)


SHOTS = {}
# 0-5,7: 1:6, крючок-вопрос Ибн Касира
for k in range(len(W16) + 1):
    for part, txt in (("h1", "Ты уже на прямом пути."),
                      ("h2", "Зачем же в каждом намазе звучит:<br>«Веди нас прямым путём»?")):
        SHOTS["%s_%d.png" % (part, k)] = page(
            '<div class="center cap" style="top:300px">%s</div>' % txt + ayah16(k, 150, 700))
# 5,7-10,2: три значения по ас-Саади
LINES = ["Покажи нам прямой путь", "Направь на него", "Помоги следовать им"]
for n in range(1, 4):
    body = "".join('<div%s>%s</div>' % ("" if i < n else ' class="off"', t) for i, t in enumerate(LINES))
    SHOTS["m_%d.png" % n] = page(
        ayah16(len(W16), 110, 300) +
        '<div class="center mean" style="top:720px">%s</div>' % body +
        '<div class="center src" style="top:1150px">ас-Саади, тафсир 1:6</div>')
# 10,2-14,4: 2:2, загораются هُدًى لِّلْمُتَّقِينَ (слова 6-7)
for k in (5, 6, 7):
    SHOTS["b_%d.png" % k] = page(
        ayah22(5, k) +
        '<div class="center tr" style="top:900px">…является верным руководством<br>для богобоязненных</div>'
        '<div class="center src" style="top:1120px">Сура 2, аят 2 · перевод Кулиева</div>')
# 14,4-16,6: один корень
SHOTS["root.png"] = page(
    '<div class="arw" style="top:430px;font-size:150px"><span class="a2 gold">%s</span>'
    '<span style="font-family:Cormorant Garamond,serif;font-size:90px;align-self:center">·</span>'
    '<span class="a1 gold">%s</span></div>' % (W22[5], W16[0]) +
    '<div class="center cap" style="top:820px">Один корень — <span dir="rtl" style="unicode-bidi:isolate">ه د ي</span>.<br>В Коране он встречается 316 раз.</div>')
SHOTS["end.png"] = page(
    '<div class="center ru" style="top:720px;font-size:96px">Одно слово</div>'
    '<div class="center" style="top:890px;font-size:54px;letter-spacing:14px;opacity:.75;font-weight:500">YASSIR</div>')


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1080, "height": 1920})
        for name, html in SHOTS.items():
            await pg.set_content(html, wait_until="networkidle")
            await pg.evaluate("document.fonts.ready")
            await pg.wait_for_timeout(300)
            await pg.screenshot(path=str(OUT / name))
        await b.close()
    print("ok", len(SHOTS))


if __name__ == "__main__":
    asyncio.run(main())
