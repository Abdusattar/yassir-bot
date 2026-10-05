"""Кадры ролика 3 «Путь» (05.10.2026): аят 54:17 + экраны приложения -> PNG 1080x1920.

Аят 54:17 «وَلَقَدْ يَسَّرْنَا ٱلْقُرْءَانَ لِلذِّكْرِ فَهَلْ مِن مُّدَّكِرٍ» - лист 529,
глифы V4 из mushaf_data/page529.json; Кулиев сверен с quran.com 05.10.2026.
Экраны - media/tools/video03_screens.py (стенд, без обучающей подсветки).

    python media/tools/video03_render.py   # PNG в media/videos/03_put/frames/
"""
import asyncio
import base64
import json
import pathlib
import sys

from playwright.async_api import async_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from teaser01_render import HEAD  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
VID = ROOT / "media" / "videos" / "03_put"
OUT = VID / "frames"

_page = json.load(open(ROOT / "mushaf_data" / "page529.json", encoding="utf-8"))
FONT = _page["font_url"]
_ayah = [a for a in _page["ayahs"] if a["surah"] == 54 and a["ayah"] == 17][0]
WORDS = [t["code_v4"] for t in _ayah["tokens"] if t["type"] == "word"]
END = [t["code_v4"] for t in _ayah["tokens"] if t["type"] == "ayah_end"][0]

# (файл экрана, подпись, откуда резать: top|bottom)
SCREENS = [
    ("pointer", "Заучиваешь — строка за строкой", "top"),
    ("word_tap", "Понимаешь каждое слово", "top"),
    ("trainer_q", "Закрепляешь слова", "top"),
    ("rec", "Читаешь устазу — голосом", "bottom"),
    ("dash", "Всё — в одном приложении", "top"),
]

EXTRA = """<style>
.cap { position:absolute; left:65px; right:65px; top:290px; text-align:center;
       font-size:66px; font-weight:600; line-height:1.15; }
.card { position:absolute; left:90px; width:900px; top:430px; height:1240px; overflow:hidden;
        border-radius:42px; box-shadow:0 18px 60px rgba(0,0,0,.55), 0 0 0 2px rgba(243,217,164,.25); }
.card img { width:900px; display:block; position:absolute; left:0; }
</style>"""


def page(body, cls="bg-dawn"):
    return (HEAD % (FONT, cls, body)).replace("</head>", EXTRA + "</head>")


def ayah(lit):
    spans = "".join('<span class="%s">%s</span>' % ("" if i < lit else "dim", w)
                    for i, w in enumerate(WORDS))
    spans += '<span>%s</span>' % END
    return page('<div class="center ar" style="top:420px">%s</div>'
                '<div class="center tr" style="top:960px">Мы облегчили Коран для поминания.<br>'
                'Но есть ли среди вас вспоминающие?</div>'
                '<div class="center src" style="top:1330px">Сура 54, аят 17 · перевод Кулиева</div>' % spans)


def card(name, cap, anchor):
    data = base64.b64encode((VID / "screens" / ("%s.png" % name)).read_bytes()).decode()
    pos = "top:0" if anchor == "top" else "bottom:0"
    return page('<div class="cap ru">%s</div><div class="card"><img style="%s" '
                'src="data:image/png;base64,%s"></div>' % (cap, pos, data))


SHOTS = {
    "how.png": page('<div class="center ru" style="top:780px">Как это выглядит<br>каждый день</div>'),
    "end.png": page('<div class="center ru" style="top:720px;font-size:104px">Коран отвечает</div>'
                    '<div class="center" style="top:900px;font-size:54px;letter-spacing:14px;'
                    'opacity:.75;font-weight:500">YASSIR</div>'),
}
for k in range(len(WORDS) + 1):
    SHOTS["ay_%d.png" % k] = ayah(k)
for name, cap, anchor in SCREENS:
    SHOTS["s_%s.png" % name] = card(name, cap, anchor)


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
            print("ok", name)
        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
