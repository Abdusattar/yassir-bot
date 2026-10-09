"""Карусель 4:5 (style §3 «4:5», §9; concept §4) из листа карусели рядом с роликом.

    python media/tools/gen/carousel.py media/videos/04_slovo_huda/carousel.json

Слайд — колонка элементов по центру живого поля 4:5 (x 100–980, y 110–1230). Слайды статичны: аят
стоит «сказанным» (--ink), ключевое слово --gold (единственное золотое), синий — только слово
обложки, знак и YASSIR. Свет страницы сдвигается по слайдам 0 → 100 % ширины — листание одной лентой.
Выход: carousel/01.png … NN.png 1080×1350, contact.jpg (лента в ширину телефона), cover_3x4_180.png
(слайд 1 в сетке профиля: обрез 3:4, 180 px).
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compile import ROOT, ayah_tokens  # noqa: E402
from page import GLYPH, TEX, V2  # noqa: E402

W, H = 1080, 1350
FIELD = 880  # 1080 − 2×100

CSS = """
:root{--paper-top:#f7efdf;--paper-mid:#fbf6ea;--paper-low:#f3e8d3;--paper-glow:#fffaf0;
--ink:#1d1a16;--ink-2:#2b2620;--blue:#2456b8;--gold:#8a6015;--muted:#6f6557}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1350px;overflow:hidden;background:#fbf6ea}
body{position:relative;font-variant-numeric:lining-nums;-webkit-font-smoothing:antialiased}
.bg{position:absolute;inset:0}
.tex{position:absolute;left:0;top:0;width:1080px;height:1920px;opacity:.05;mix-blend-mode:multiply}
.slide{position:absolute;left:100px;top:110px;width:880px;height:1120px;display:flex;flex-direction:column;
 align-items:center;justify-content:center;text-align:center}
.cg{font-family:'Cormorant Garamond',serif;font-weight:600;text-wrap:balance}
.in{font-family:Inter,sans-serif;font-weight:500}
.row{display:flex;direction:rtl;justify-content:center;gap:0 26px;white-space:nowrap}
.col{display:flex;flex-direction:column;align-items:center}
.mn{color:var(--ink-2);white-space:nowrap;direction:ltr}
.roots{display:flex;direction:rtl;justify-content:center;gap:28px}
.plate{width:140px;height:140px;border:2px solid var(--gold);border-radius:22px;display:flex;align-items:center;
 justify-content:center;font-family:Amiri,serif;font-size:104px;color:var(--ink);line-height:1}
.plate span{transform:translateY(-6px)}
"""

JS = r"""
const S = __DATA__;
const FIELD = 880;
const STEPS = [118, 111, 104, 98, 96];  // кегль аята 4:5 (style §3): 96–118
const MF = ["600 46px/1.1 'Cormorant Garamond'", '500 40px/1.1 Inter'];
function el(tag, cls, parent, html) { const e = document.createElement(tag); if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html; parent.appendChild(e); return e; }
function measure(text, font) { const s = el('span', '', document.body); s.style.cssText =
  `position:absolute;white-space:nowrap;visibility:hidden;font:${font}`; s.textContent = text;
  const w = s.getBoundingClientRect().width; s.remove(); return w; }
function nb(s) { s = s.replace(/ —/g, ' —');
  for (let i = 0; i < 2; i++) s = s.replace(/(^|[\s ])([А-Яа-яЁё]{1,3}) /g, '$1$2 '); return s; }
const C = c => `var(--${c})`;
// аят: столбцы (глиф | значение), балансный перенос ≤25 % (style §2), ширина строки ≤880
function ayah(x, parent) {
  const fam = 'v2p' + x.page, n = x.words.length;
  const g = x.words.map((w, i) => w.glyph + (i === n - 1 ? x.end : ''));
  const warn = [];
  // короткий аят (≤4 слов) одной строкой на любой ступени лучше переноса 2+1
  const steps = n <= 4 ? STEPS.concat(STEPS) : STEPS;
  for (let si = 0; si < steps.length; si++) { const k = steps[si], oneRow = n <= 4 && si < STEPS.length;
    const cols = g.map((c, i) => { const gw = measure(c, `${k}px ${fam}`);
      if (!x.values) return {w: gw, f: 0};
      const m = x.words[i].meaning, a = measure(m, MF[0]);
      if (a <= gw + 60) return {w: Math.max(gw, a), f: 0};
      return {w: Math.max(gw, measure(m, MF[1])), f: 1}; });
    const w = cols.map(c => c.w), sum = (a, z) => w.slice(a, z).reduce((s, v) => s + v, 0) + 26 * (z - a - 1);
    let rows = null;
    if (sum(0, n) <= FIELD) rows = [[0, n]];
    else if (!oneRow) { let best = null;
      for (let i = 1; i < n; i++) { const A = sum(0, i), B = sum(i, n), r = Math.abs(A - B) / Math.max(A, B);
        if (A <= FIELD && B <= FIELD && r <= .25 && (!best || r < best[1])) best = [i, r]; }
      if (best) rows = [[0, best[0]], [best[0], n]]; }
    if (!rows && (oneRow || si !== steps.length - 1)) continue;
    if (!rows) { rows = [[0, n]]; warn.push(`аят ${x.ref} не влез в 2 строки на ${k} px`); }
    const blk = el('div', '', parent);
    for (const [a, z] of rows) { const row = el('div', 'row', blk);
      for (let i = a; i < z; i++) { const col = el('div', 'col', row); col.style.width = cols[i].w + 'px';
        const s = el('span', '', col); s.style.font = `${k}px/1.6 ${fam}`;
        s.innerHTML = `<span style="color:${x.key.includes(x.words[i].pos) ? C('gold') : C('ink')}">${x.words[i].glyph}</span>`
          + (i === n - 1 ? `<span style="color:${C('ink')}">${x.end}</span>` : '');
        if (x.values) { const m = el('div', 'mn', col, x.words[i].meaning); m.style.font = MF[cols[i].f];
          m.style.marginTop = '-14px'; } } }
    return {el: blk, k, rows: rows.map(r => r[1] - r[0]), warn};
  }
}
window.build = async function (i) {
  const sl = S.slides[i], n = S.slides.length;
  const gx = n > 1 ? Math.round(100 * i / (n - 1)) : 50;  // свет страницы идёт лентой по слайдам
  document.querySelector('.bg').style.background =
    `radial-gradient(ellipse 820px 640px at ${gx}% 45%,var(--paper-glow),transparent 70%),` +
    'linear-gradient(var(--paper-top),var(--paper-mid) 50%,var(--paper-low))';
  const box = el('div', 'slide', document.body), info = [];
  for (const x of sl.items) {
    let d;
    switch (x.type) {
      case 'label': d = el('div', 'cg', box, x.text); d.style.cssText += ';font-size:48px;line-height:1.2;color:var(--muted)'; break;
      case 'text': d = el('div', 'cg', box, nb(x.text)); d.style.cssText +=
        `;font-size:${x.size || 60}px;line-height:${x.size >= 80 ? 1.18 : 1.25};font-weight:${x.weight || 600};color:${C(x.color || 'ink-2')};max-width:880px;width:max-content`; break;
      case 'source': d = el('div', 'in', box, x.text); d.style.cssText += ';font-size:40px;line-height:1.2;color:var(--muted);white-space:nowrap'; break;
      case 'word': d = el('div', '', box, x.glyph); d.style.cssText += `;font:${x.size}px/1.3 v2p${x.page};color:${C(x.color)}`; break;
      case 'ayah': { const r = ayah(x, box); d = r.el; info.push({ref: x.ref, k: r.k, rows: r.rows, warn: r.warn}); break; }
      case 'root': d = el('div', 'roots', box); for (const ch of x.letters) el('div', 'plate', d, `<span>${ch}</span>`); break;
      case 'glyph': d = el('div', '', box, S.glyph); d.firstElementChild.setAttribute('width', x.w);
        d.firstElementChild.setAttribute('height', Math.round(x.w * 602 / 752)); break;
      case 'yassir': d = el('div', 'in', box, 'YASSIR'); d.style.cssText +=
        `;font-size:${x.size || 40}px;line-height:1;letter-spacing:${(x.size || 40) / 5}px;text-indent:${(x.size || 40) / 5}px;color:var(--blue)`; break;
    }
    if (x.mt) d.style.marginTop = x.mt + 'px';
  }
  const r = box.getBoundingClientRect(), kids = [...box.children].map(c => c.getBoundingClientRect());
  const top = Math.min(...kids.map(k => k.top)), bot = Math.max(...kids.map(k => k.bottom));
  const left = Math.min(...kids.map(k => k.left)), right = Math.max(...kids.map(k => k.right));
  return {ayah: info, box: [Math.round(left), Math.round(top), Math.round(right), Math.round(bot)]};
};
"""


def resolve(spec):
    """Глифы V2 со страницы мусхафа; значения — из базы страницы (листом можно переопределить)."""
    pages = set()
    for sl in spec["slides"]:
        for x in sl["items"]:
            if x["type"] in ("word", "ayah"):
                words, end = ayah_tokens(x["page"], x["surah"], x["ayah"])
                pages.add(x["page"])
                for w in words:
                    w["meaning"] = x.get("meanings", {}).get(str(w["pos"]), w["meaning"])
                if x["type"] == "word":
                    x["glyph"] = [w for w in words if w["pos"] == x["pos"]][0]["glyph"]
                else:
                    x.update(words=words, end=end, ref="%d:%d" % (x["surah"], x["ayah"]),
                             key=x.get("key", []), values=x.get("values", False))
    return pages


def html(spec, pages):
    faces = "".join("@font-face{font-family:v2p%d;src:url(%s) format('woff2');font-display:block}" % (n, V2 % n)
                    for n in sorted(pages))
    data = dict(spec, glyph=GLYPH.read_text("utf-8"))
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<link href='https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700"
            "&family=Inter:wght@500&family=Amiri&display=block' rel='stylesheet'>"
            "<style>" + faces + CSS + "</style></head><body><div class='bg'></div>"
            "<img class='tex' src='" + TEX.as_uri() + "'>"
            "<script>" + JS.replace("__DATA__", json.dumps(data, ensure_ascii=False)) + "</script></body></html>")


async def shoot(page_path, out_dir, n):
    from playwright.async_api import async_playwright
    fams = ["118px v2p%d" % p for p in PAGES] + ["104px Amiri", "600 60px 'Cormorant Garamond'",
                                                "700 60px 'Cormorant Garamond'", "500 40px Inter"]
    report = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for i in range(n):
            pg = await b.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
            await pg.goto(Path(page_path).as_uri(), wait_until="networkidle")
            for f in fams:
                await pg.evaluate("f => document.fonts.load(f, 'ابجد Аб')", f)
            await pg.evaluate("document.fonts.ready")
            report.append(await pg.evaluate("i => build(i)", i))
            await pg.screenshot(path=str(out_dir / ("%02d@2x.png" % (i + 1))))
            await pg.close()
        await b.close()
    return report


def main(sheet_path):
    global PAGES
    from PIL import Image
    sheet_path = Path(sheet_path).resolve()
    spec = json.loads(sheet_path.read_text("utf-8"))
    PAGES = resolve(spec)
    out = sheet_path.parent / "carousel"
    out.mkdir(exist_ok=True)
    page = out / "carousel.html"
    page.write_text(html(spec, PAGES), "utf-8")
    n = len(spec["slides"])
    report = asyncio.run(shoot(page, out, n))
    ims = []
    for i in range(n):
        big = out / ("%02d@2x.png" % (i + 1))
        im = Image.open(big).convert("RGB").resize((W, H), Image.LANCZOS)  # dsf 2 → Lanczos: резкие харакаты
        im.save(out / ("%02d.png" % (i + 1)))
        big.unlink()
        ims.append(im)
    # проверки: живое поле 4:5 (x 100–980, y 110–1230) и предупреждения раскладки
    ok = True
    for i, r in enumerate(report, 1):
        l, t, rr, bt = r["box"]
        inside = l >= 100 and rr <= 980 and t >= 110 and bt <= 1230
        ok &= inside
        lay = "; ".join("%s %d px, строки %s%s" % (a["ref"], a["k"], "+".join(map(str, a["rows"])),
                                                    (" ⚠ " + ", ".join(a["warn"])) if a["warn"] else "")
                        for a in r["ayah"])
        print("слайд %d: поле x %d–%d, y %d–%d %s%s" % (i, l, rr, t, bt, "✓" if inside else "✗ ВНЕ ПОЛЯ",
                                                     ("  | " + lay) if lay else ""))
    # лента в ширину телефона (390 pt ≈ 1080 px → слайд 360 px) — смотреть глазами
    tw = 360
    th = round(H * tw / W)
    sheet = Image.new("RGB", (tw * n + 12 * (n - 1), th), "#d9d4cc")
    for i, im in enumerate(ims):
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (i * (tw + 12), 0))
    sheet.save(out / "contact.jpg", quality=90)
    # слайд 1 в сетке профиля: обрез 3:4 по центру (1012×1350) → 180 px
    c = ims[0].crop(((W - 1012) // 2, 0, (W + 1012) // 2, H))
    c.resize((180, 240), Image.LANCZOS).save(out / "cover_3x4_180.png")
    page.unlink()
    print("готово:", out, "" if ok else "— есть элементы вне поля")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1]) else 1)
