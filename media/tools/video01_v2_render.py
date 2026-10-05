"""Кадры с текстом для ролика 1, версия 2 (05.10.2026): HTML в Chromium -> PNG 1080x1920.

Отличия от версии 1 (teaser01_render.py): крючок «Тебе тоже шумно внутри?»,
вопрос «А Его слово ты слышишь?», в конце «Коран отвечает» + YASSIR вместо
«Скоро». Кадр с аятом тот же. Текст - в безопасных зонах (270/670/65).

    python media/tools/video01_v2_render.py    # PNG в media/videos/01_skolko_golosov/v2/
"""
import asyncio
import pathlib
import sys

from playwright.async_api import async_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from teaser01_render import page, ayah, WORDS  # noqa: E402  (тот же шрифт V4, лист 252)

OUT = pathlib.Path(__file__).resolve().parent.parent / "videos" / "01_skolko_golosov" / "v2"

SHADE = ('<div style="position:absolute;left:-200px;right:-200px;top:560px;height:560px;'
         'background:radial-gradient(ellipse at center, rgba(0,0,0,.72), rgba(0,0,0,.45) 45%,'
         ' rgba(0,0,0,0) 72%)"></div>')

SHOTS = {
    # (html, прозрачный фон - кладётся поверх видео)
    "hook.png": (page(SHADE + '<div class="center ru" style="top:720px;font-size:96px">'
                      'Тебе тоже<br>шумно внутри?</div>'), True),
    "q.png": (page('<div class="center ru" style="top:760px">А Его слово<br>ты слышишь?</div>'), False),
    "end.png": (page('<div class="center ru" style="top:720px;font-size:104px">Коран отвечает</div>'
                     '<div class="center" style="top:900px;font-size:54px;letter-spacing:14px;'
                     'opacity:.75;font-weight:500">YASSIR</div>', "bg-dawn"), False),
}
for k in range(len(WORDS) + 1):
    SHOTS["ayah_%d.png" % k] = (ayah(k, True), False)


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1080, "height": 1920})
        for name, (html, transparent) in SHOTS.items():
            await pg.set_content(html, wait_until="networkidle")
            await pg.evaluate("document.fonts.ready")
            await pg.wait_for_timeout(300)
            if name == "q.png":
                await pg.evaluate("document.body.style.background='#000'")
            await pg.screenshot(path=str(OUT / name), omit_background=transparent)
            print("ok", name)
        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
