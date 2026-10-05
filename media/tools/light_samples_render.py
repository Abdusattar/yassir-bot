import asyncio, base64, json, sys
from pathlib import Path
from playwright.async_api import async_playwright
ROOT = Path(r"D:\aispace\yassir_Bot")
OUT = ROOT / "media" / "brand"
SCR = Path(__file__).parent
d = json.loads((ROOT / "mushaf_data/page1.json").read_text(encoding="utf-8"))
a = [x for x in d["ayahs"] if x["ayah"] == 6][0]
words = [t for t in a["tokens"] if t["type"] == "word"]
end = [t for t in a["tokens"] if t["type"] == "ayah_end"][0]["code_v4"]
tex = base64.b64encode((OUT / "paper_texture.png").read_bytes()).decode()
glyph = (OUT / "glyph_book.svg").read_text(encoding="utf-8").replace('width="752" height="602"', 'width="240" height="192"')

def head(glowy, texture=True):
    return """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&family=Inter:wght@500&display=block" rel="stylesheet">
<style>
@font-face{font-family:v2p1;src:url(https://static-cdn.tarteel.ai/qul/fonts/quran_fonts/v2/woff2/p1.woff2) format('woff2');font-display:block}
:root{--paper-top:#f7efdf;--paper-mid:#fbf6ea;--paper-low:#f3e8d3;--paper-glow:#fffaf0;
--ink:#1d1a16;--ink-2:#2b2620;--dim:rgba(29,26,22,.40);--blue:#2456b8;--gold:#8a6015;--muted:#6f6557}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;overflow:hidden}
body{position:relative;font-variant-numeric:lining-nums}
.bg{position:absolute;inset:0;background:radial-gradient(ellipse 900px 700px at 50% GLOWY, var(--paper-glow), transparent 70%),
linear-gradient(var(--paper-top), var(--paper-mid) 50%, var(--paper-low))}
.tex{position:absolute;left:0;top:0;width:1080px;height:1920px;opacity:TOP;mix-blend-mode:multiply}
.abs{position:absolute;left:0;right:0;text-align:center}
</style></head><body><div class="bg"></div><img class="tex" src="data:image/png;base64,TEX">""".replace("GLOWY", glowy).replace("TOP", ".05" if texture else "0").replace("TEX", tex)

def ayah_html(texture=True):
    states = ["gold", "blue", "dim"]; mon = [True, True, False]
    cols = []
    for i, w in enumerate(words):
        g = w["code_v4"] + (end if i == len(words) - 1 else "")
        cols.append(f'<div class="col"><div class="ar" style="color:var(--{states[i]})">{g}</div>'
                    f'<div class="mn" style="opacity:{1 if mon[i] else 0}">{w["translation"]}</div></div>')
    return head("40%", texture) + """<style>
.hook{top:290px;font:600 84px/1.18 'Cormorant Garamond',serif;color:var(--ink);padding:0 130px}
.blk{position:absolute;left:65px;right:65px;top:520px;height:480px;display:flex;flex-direction:column;justify-content:center}
.row{display:flex;flex-direction:row;direction:rtl;justify-content:center;gap:26px}
.col{display:flex;flex-direction:column;align-items:center}
.ar{font-family:v2p1;font-size:118px;line-height:1.6;white-space:nowrap}
.mn{font:600 46px/1.1 'Cormorant Garamond',serif;color:var(--ink-2)}
.src{top:1160px;font:500 40px/1.2 Inter,sans-serif;color:var(--muted)}
</style>
<div class="abs hook">Куда ведёт твой путь?</div>
<div class="blk"><div class="row">""" + "".join(cols[:2]) + """</div><div class="row">""" + cols[2] + """</div></div>
<div class="abs src">Сура 1, аят 6</div></body></html>"""

def end_html(texture=True):
    return head("37.5%", texture) + f"""<style>
.lbl{{top:500px;font:600 48px/1.2 'Cormorant Garamond',serif;color:var(--muted)}}
.gl{{position:absolute;left:420px;top:624px;width:240px;height:192px}}
.ys{{top:880px;font:500 70px/1 Inter,sans-serif;letter-spacing:14px;padding-left:14px;color:var(--blue)}}
.cta{{top:990px;font:600 46px/1.2 'Cormorant Garamond',serif;color:var(--ink-2)}}
</style>
<div class="abs lbl">Путь</div>
<div class="gl">{glyph}</div>
<div class="abs ys">YASSIR</div>
<div class="abs cta">Учиться понимать — ссылка в профиле</div></body></html>"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1080, "height": 1920})
        jobs = [(ayah_html(), OUT / "light_sample_ayah.png"), (end_html(), OUT / "light_sample_end.png"),
                (ayah_html(False), SCR / "ayah_notex.png"), (end_html(False), SCR / "end_notex.png")]
        for html, path in jobs:
            await pg.set_content(html, wait_until="networkidle")
            await pg.evaluate("document.fonts.ready")
            await pg.wait_for_timeout(500)
            await pg.screenshot(path=str(path))
        await b.close()
asyncio.run(main())
print("ok")
