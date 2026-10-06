"""Одна HTML-страница ролика: render(t) выставляет каждое свойство как функцию t (style §4).
Playwright Chromium 1080×1920 снимает кадр i при t = i/fps; переходы CSS выключены.
"""
import asyncio
import json
from pathlib import Path

from compile import ROOT

V2 = "https://static-cdn.tarteel.ai/qul/fonts/quran_fonts/v2/woff2/p%d.woff2"
TEX = ROOT / "media" / "brand" / "paper_texture.png"
GLYPH = ROOT / "media" / "brand" / "glyph_book.svg"

CSS = """
:root{--paper-top:#f7efdf;--paper-mid:#fbf6ea;--paper-low:#f3e8d3;--paper-glow:#fffaf0;
--ink:#1d1a16;--ink-2:#2b2620;--dim:rgba(29,26,22,.40);--blue:#2456b8;--gold:#8a6015;--muted:#6f6557}
*{margin:0;padding:0;box-sizing:border-box;transition:none!important;animation:none!important}
html,body{width:1080px;height:1920px;overflow:hidden;background:#fbf6ea}
body{position:relative;font-variant-numeric:lining-nums;-webkit-font-smoothing:antialiased}
.bg{position:absolute;inset:0;background:radial-gradient(ellipse 900px 700px at 50% 45%,var(--paper-glow),transparent 70%),
 linear-gradient(var(--paper-top),var(--paper-mid) 50%,var(--paper-low))}
.tex{position:absolute;left:0;top:0;width:1080px;height:1920px;opacity:.05;mix-blend-mode:multiply}
.plan,.cam{position:absolute;left:0;top:0;width:1080px;height:1920px}
.cam{transform-origin:540px 760px}
.blk{position:absolute;left:0;top:0;width:1080px;transform-origin:540px 0}
.row{display:flex;direction:rtl;justify-content:center;gap:0 26px;white-space:nowrap}
.col{display:flex;flex-direction:column;align-items:center}
.w{line-height:1.6;white-space:nowrap}
.mn{color:var(--ink-2);text-align:center;white-space:nowrap;direction:ltr}
.live{position:absolute;left:0;top:0;width:1080px;height:1920px}
.paper{position:absolute;inset:0;background:radial-gradient(ellipse 900px 700px at 50% 45%,var(--paper-glow),transparent 70%),
 linear-gradient(var(--paper-top),var(--paper-mid) 50%,var(--paper-low))}
.card{background:rgba(251,246,234,.90);border-radius:32px;padding:40px 56px}
.tx{position:absolute;text-align:center;text-wrap:balance}
.cg{font-family:'Cormorant Garamond',serif;font-weight:600}
.in{font-family:Inter,sans-serif;font-weight:500}
.roots{position:absolute;left:0;width:1080px;top:300px;display:flex;direction:rtl;justify-content:center;gap:32px}
.plate{width:160px;height:160px;border:2px solid var(--gold);border-radius:24px;display:flex;align-items:center;
 justify-content:center;font-family:Amiri,serif;font-size:120px;color:var(--ink);line-height:1}
.plate span{transform:translateY(-6px)}
.glyph{position:absolute;left:420px;top:624px;width:240px;height:192px}
body.solo,html:has(body.solo){background:transparent} body.solo>.bg,body.solo>.tex{visibility:hidden}
"""

JS = r"""
const D = __DATA__;
const STEPS = [118, 111, 104, 98, 92, 88]; // ступени кегля (style §2)
const ZMAX = 1.04;                         // наибольший наезд: ширины делим на него (безопасные поля)
const W_FIELD = 950 / ZMAX, W_LOW = 820 / ZMAX;
const MODES = ['A', 'B', 'C'];
const lerp = (a, b, u) => a + (b - a) * u;
const ease = u => u < .5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
const mix = (a, b, u) => Array.isArray(a) ? a.map((x, i) => lerp(x, b[i], u)) : lerp(a, b, u);
// значение по ключевым точкам [t, v, длит., ease] — чистая функция t
function ev(o, t) {
  let v = o.c0; const k = o.kfs;
  for (let i = 0; i < k.length; i++) {
    const [t0, val, d, e] = k[i]; if (t < t0) break;
    const te = i + 1 < k.length ? Math.min(t, k[i + 1][0]) : t;
    let u = d > 0 ? Math.min(1, (te - t0) / d) : 1; if (e) u = ease(u);
    v = mix(v, val, u);
  }
  return v;
}
const rgba = c => `rgba(${c[0].toFixed(2)},${c[1].toFixed(2)},${c[2].toFixed(2)},${c[3].toFixed(4)})`;
function el(tag, cls, parent, html) { const e = document.createElement(tag); if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html; parent.appendChild(e); return e; }
function measure(text, font) { const s = el('span', '', document.body); s.style.cssText =
  `position:absolute;white-space:nowrap;visibility:hidden;font:${font}`; s.textContent = text;
  const w = s.getBoundingClientRect().width; s.remove(); return w; }
// неразрывные пробелы: тире не начинает строку, короткие слова (≤3 букв) не висят в конце строки
function nb(s) { s = s.replace(/ —/g, ' —');
  for (let i = 0; i < 2; i++) s = s.replace(/(^|[\s ])([А-Яа-яЁё]{1,3}) /g, '$1$2 '); return s; }

// Столбец слова (style §2 п. 2): w = max(глиф, значение); значение Cormorant 46 -> Inter 40 -> 2 строки
const MF = ["600 46px/1.1 'Cormorant Garamond'", '500 40px/1.1 Inter'];
function column(gw, m) {
  if (m === null) return {w: gw, f: 0, two: false};
  const c = measure(m, MF[0]); if (c <= gw + 60) return {w: Math.max(gw, c), f: 0, two: false};
  const i = measure(m, MF[1]); if (i <= gw + 60) return {w: Math.max(gw, i), f: 1, two: false};
  return {w: gw + 60, f: 1, two: true};
}
// Раскладка аята (style §2): ступени кегля, балансный перенос ≤25 %, перенос по вакфу
function layout(b) {
  const fam = 'v2p' + b.page;
  const glyphs = b.words.map((w, i) => w.glyph + (i === b.words.length - 1 && b.end ? b.end : ''));
  const g118 = glyphs.map(c => measure(c, `118px ${fam}`));
  const PRI = {'ۘ': 4, 'ۗ': 3, 'ۖ': 2, 'ۚ': 1};
  for (const k of STEPS) {
    const cols = g118.map((x, i) => column(x * k / 118, b.values ? b.words[i].meaning : null));
    const w = cols.map(c => c.w), n = w.length;
    const sum = (a, z) => w.slice(a, z).reduce((s, x) => s + x, 0) + 26 * (z - a - 1);
    const two = cols.some(c => c.two);
    const res = (rows, ratio) => ({k, cols, glyphs, rows, ratio, two, warn: null});
    if (sum(0, n) <= W_FIELD) return res([[0, n]], 0);
    // значения в 2 строки: нижняя строка блока уходит ниже y 1050 — она ≤820 (style §3)
    const W2max = two ? W_LOW : W_FIELD;
    let best = null, cand = [];
    for (let i = 1; i < n; i++) {
      const W1 = sum(0, i), W2 = sum(i, n), r = Math.abs(W1 - W2) / Math.max(W1, W2);
      if (W1 > W_FIELD || W2 > W2max || r > .25 || b.words[i - 1].waqf.includes('ۙ')) continue;
      cand.push([i, r]); if (!best || r < best[1]) best = [i, r];
    }
    if (!best) continue;
    let br = best[0], pr = 0;
    for (const [i] of cand) {
      const p = Math.max(0, ...[...b.words[i - 1].waqf].map(ch => PRI[ch] || 0));
      if (Math.abs(i - best[0]) <= 2 && p > pr) { pr = p; br = i; }
    }
    return res([[0, br], [br, n]], best[1]);
  }
  const waqf = b.words.filter(w => w.waqf && !w.waqf.includes('ۙ')).map(w => w.pos);
  const cols = g118.map((x, i) => column(x * 88 / 118, b.values ? b.words[i].meaning : null));
  return {k: 88, cols, glyphs, rows: [[0, b.words.length]], ratio: 0, two: false,
          warn: `аят ${b.ref} не влез в 2 строки на 88 px — делить на части (план на часть, "words") после слов со знаком вакфа: ${waqf}`};
}
// Геометрия блока в режиме (style §3): верх и масштаб; зона по L_0 / L_m, короткий блок — по центру зоны
function geom(o, mode) {
  const m = o.p.block.values, H = o.H;
  if (mode === 'C') { const s = 88 / o.L.k, zh = m ? 384 : 282;
    return {top: 290 + Math.max(0, (zh - H * s) / 2), s}; }
  const [zt, zh] = m ? [520, 480] : [560, 378];
  return {top: zt + Math.max(0, (zh - H) / 2), s: 1};
}

const P = [];  // построенные планы
window.LAYOUT = [];
function build() {
  for (const p of D.plans) {
    const pd = el('div', 'plan', document.body), cam = el('div', 'cam', pd);
    const o = {p, pd, cam, glyphs: [], means: [], texts: []};
    if (p.live) {  // живой кадр — картинка из нарезанных ffmpeg PNG; поверх слой бумаги для светления
      o.img = el('img', 'live', cam); o.cover = el('div', 'paper', cam);
      el('img', 'tex', o.cover).src = D.tex;
    }
    if (p.block) {
      const L = layout(p.block); o.L = L;
      const blk = el('div', 'blk', cam); o.blk = blk;
      const mh = p.block.values ? (L.two ? 84 : 51) : 0;
      for (const [a, z] of L.rows) {
        const row = el('div', 'row', blk);
        for (let i = a; i < z; i++) {
          const col = el('div', 'col', row); col.style.width = L.cols[i].w + 'px';
          const last = i === p.block.words.length - 1 && p.block.end;
          const w = el('span', 'w', col); w.style.font = `${L.k}px/1.6 v2p${p.block.page}`;
          o.glyphs.push(el('span', '', w, p.block.words[i].glyph));
          if (last) o.endEl = el('span', '', w, p.block.end);  // знак аята — свой цвет, синим не бывает
          if (p.block.values) {
            const m = el('div', 'mn', col, p.block.words[i].meaning); m.style.font = MF[L.cols[i].f];
            m.style.height = mh + 'px';
            if (L.cols[i].two) { m.style.whiteSpace = 'normal'; m.style.lineHeight = '1.05'; }
            o.means.push(m);
          }
        }
      }
      o.H = L.rows.length * (L.k * 1.6 + mh);
      blk.style.height = o.H + 'px';
      o.G = {A: geom(o, 'A'), B: geom(o, 'B'), C: geom(o, 'C')};
      o.botC = o.G.C.top + o.H * o.G.C.s;
      window.LAYOUT.push({ref: p.block.ref, k: L.k, rows: L.rows.map(r => r[1] - r[0]), warn: L.warn,
                          ratio: L.ratio, values: p.block.values, two: L.two});
    }
    for (const x of p.texts) o.texts.push([x, text(x, cam, o)]);
    P.push(o);
  }
}
function box(parent, cls, top, width, html) {
  const d = el('div', 'tx ' + cls, parent, html);
  d.style.top = top + 'px'; d.style.left = (1080 - width) / 2 + 'px'; d.style.width = width + 'px'; return d; }
function card(d) {  // светлая карточка по ширине строки (текст на живом кадре, style §1)
  d.classList.add('card'); d.style.width = 'fit-content'; d.style.maxWidth = W_FIELD + 'px';
  d.style.left = Math.round((1080 - d.getBoundingClientRect().width) / 2) + 'px'; return d; }
function text(x, cam, o) {
  const C = x.mode === 'C', m = o.p.block && o.p.block.values;
  const tC = m ? Math.round(o.botC + 36) : 640;            // перевод в C: под фактическим низом блока
  const tB = m ? 1010 : 980;                                // перевод в B
  const t = x.text ? nb(x.text) : '';
  switch (x.role) {
    case 'hook': { const d = box(cam, 'cg', 290, W_FIELD, t);
      d.style.cssText += ';font-size:84px;line-height:1.18;color:var(--ink)'; return o.p.live ? card(d) : d; }
    case 'translation': { const d = box(cam, 'cg', C ? tC : tB, C ? 820 : W_LOW, t);  // выше y 1050 — 820 по style
      d.style.cssText += ';font-size:60px;line-height:1.25;color:var(--ink-2)';
      const bt = d.getBoundingClientRect().bottom;
      if (C) o.lowC = Math.max(o.lowC || 0, bt); else o.lowB = bt; return d; }
    case 'line': { const d = box(cam, 'cg', tC + 75 * x.slot, 820, t);
      d.style.cssText += `;font-size:60px;line-height:1.25;white-space:nowrap;color:var(${x.key_line ? '--ink' : '--ink-2'});font-weight:${x.key_line ? 700 : 600}`;
      o.lowC = Math.max(o.lowC || 0, d.getBoundingClientRect().bottom); return d; }
    case 'source': { // одна строка Inter 40 («1:6 · смысловой перевод: Кулиев», style §2); в C — на 40 px
      // под последним занятым слотом перевода; не влезает — страховка: перенос по « · » с предупреждением
      const bot = C ? (o.lowC ? Math.round(o.lowC) + 40 + 48 : (m ? tC + 300 + 40 + 48 : 1028))
                    : x.mode === 'A' ? 1208 : (m ? 1218 : 1208);
      const W = bot > 1050 ? W_LOW : W_FIELD;  // строка уходит ниже y 1050 — ширина ≤820 (с наездом)
      const d = box(cam, 'in', bot - 48, W, x.text);
      d.style.cssText += ';font-size:40px;line-height:1.2;color:var(--muted);white-space:nowrap';
      if (d.scrollWidth > W + 1) { d.innerHTML = x.text.replace(' · ', '<br>');
        // две строки: низ на низе зоны, но не выше низа перевода режима B (+10 px)
        const top = Math.max(bot - d.getBoundingClientRect().height, !C && o.lowB ? o.lowB + 10 : 0);
        d.style.top = top + 'px';
        const zb = 760 + (top + d.getBoundingClientRect().height - 760) * ZMAX;
        if (zb > 1250) window.LAYOUT.push({warn: `источник «${x.text}» с наездом уходит до y ${Math.round(zb)} > 1250 — сцену в режим C`});
        window.LAYOUT.push({warn: `источник «${x.text}» шире ${Math.round(W)} px — в две строки`}); }
      return d; }
    case 'root': { const d = el('div', 'roots', cam);
      for (const ch of x.letters) el('div', 'plate', d, `<span>${ch}</span>`); return d; }
    case 'root_line': { const d = box(cam, 'cg', tB, W_LOW, t);
      d.style.cssText += ';font-size:60px;line-height:1.25;color:var(--ink)'; return d; }
    case 'question': { // 84 px; не влезает в 2 строки — 60 px; по центру живого поля (y 760)
      const d = box(cam, 'cg', 0, W_FIELD, t);
      d.style.cssText += ';font-size:84px;line-height:1.18;color:var(--ink)';
      if (d.getBoundingClientRect().height > 2 * 84 * 1.18 + 1) { d.style.fontSize = '60px'; d.style.lineHeight = '1.25'; }
      if (o.p.live) card(d);
      d.style.top = Math.round(760 - d.getBoundingClientRect().height / 2) + 'px'; return d; }
    case 'label': { const d = box(cam, 'cg', 500, W_FIELD, t);
      d.style.cssText += ';font-size:48px;line-height:1.2;color:var(--muted)'; return d; }
    case 'glyph': return el('div', 'glyph', cam, D.glyph);
    case 'yassir': { const d = box(cam, 'in', 880, W_FIELD, x.text);
      d.style.cssText += ';font-size:70px;line-height:1;letter-spacing:14px;text-indent:14px;color:var(--blue)'; return d; }
  }
}
window.render = function (t) {
  for (const o of P) {
    const p = o.p;
    o.pd.style.opacity = ev(p.op, t).toFixed(4);
    const u = Math.min(1, Math.max(0, (t - p.t0) / (p.t1 - p.t0)));
    o.scale = 1 + p.zoom * u;  // наезд на план (style §4)
    o.cam.style.transform = window.NO_CAM ? 'none' : `scale(${o.scale.toFixed(6)})`;
    if (o.img) {
      const L = p.live, i = Math.max(0, Math.min(L.n - 1, Math.floor((t - L.at) * 30 + 1e-6)));
      const src = L.base + String(i).padStart(5, '0') + '.png';
      if (o.img.getAttribute('src') !== src) o.img.src = src;
      const b = ev(L.bright, t);  // светление в бумагу (style §1 п. 3)
      o.img.style.filter = `brightness(${(1 + .35 * b).toFixed(4)}) saturate(${(1 - .3 * b).toFixed(4)})`;
      o.cover.style.opacity = (.55 * b).toFixed(4);
    }
    if (o.blk) {
      const w = ev(p.block.move, t);  // веса режимов A/B/C (переезд — ease-in-out в ключевых точках)
      let top = 0, s = 0; MODES.forEach((md, i) => { top += w[i] * o.G[md].top; s += w[i] * o.G[md].s; });
      o.blk.style.transform = `translate(0px,${top.toFixed(3)}px) scale(${s.toFixed(6)})`;
      o.glyphs.forEach((g, i) => g.style.color = rgba(ev(p.block.colors[i], t)));
      if (o.endEl) o.endEl.style.color = rgba(ev(p.block.end_color, t));
      o.means.forEach((m, i) => m.style.opacity = ev(p.block.means[i], t).toFixed(4));
    }
    for (const [x, d] of o.texts) d.style.opacity = ev(x.op, t).toFixed(4);
  }
};
// Снимок по слоям: Chromium под scale() привязывает базовую линию текста к пикселю (дрожь до 0,4 px),
// поэтому наезд накладывает Python точным ресэмплом. layers(t) — видимые планы и их масштаб.
window.layers = async function (t) {
  window.NO_CAM = true; render(t);
  await Promise.all([...document.images].map(i => i.complete ? 0 : new Promise(r => { i.onload = i.onerror = r; })));
  return P.filter(o => parseFloat(o.pd.style.opacity) > 0).map(o => [o.p.id, o.scale]);
};
window.solo = function (id) {  // только один план, без бумаги — фон прозрачный
  document.body.classList.toggle('solo', id !== null);
  for (const o of P) o.pd.style.visibility = (id === null || o.p.id === id) ? 'visible' : 'hidden';
};
window.boot = async function () {
  const fams = D.pages.map(n => `118px v2p${n}`).concat(['120px Amiri', "600 60px 'Cormorant Garamond'",
                "700 60px 'Cormorant Garamond'", '500 40px Inter', "600 46px 'Cormorant Garamond'"]);
  for (const f of fams) await document.fonts.load(f, 'ابجد Аб');
  await document.fonts.ready;
  build(); render(0);
  return window.LAYOUT;
};
"""


def html(data, pages):
    faces = "".join("@font-face{font-family:v2p%d;src:url(%s) format('woff2');font-display:block}" % (n, V2 % n)
                    for n in pages)
    data = dict(data, pages=list(pages), tex=TEX.as_uri(), glyph=GLYPH.read_text("utf-8").replace('width="752" height="602"', 'width="240" height="192"'))
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<link href='https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700"
            "&family=Inter:wght@500&family=Amiri&display=block' rel='stylesheet'>"
            "<style>" + faces + CSS + "</style></head><body><div class='bg'></div>"
            "<img class='tex' src='" + TEX.as_uri() + "'>"
            "<script>" + JS.replace("__DATA__", json.dumps(data, ensure_ascii=False)) + "</script></body></html>")


async def _open(pw, path, dsf):
    b = await pw.chromium.launch()
    pg = await b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=dsf)
    await pg.goto(Path(path).as_uri(), wait_until="networkidle")
    layout = await pg.evaluate("boot()")
    return b, pg, layout


def _compose(bg, layers, dsf):
    """Слои планов (RGBA, без бумаги, масштаб 1) -> наезд точным ресэмплом Lanczos вокруг (540, 760),
    наложение на неподвижную бумагу (фон вне камеры, style §4)."""
    from PIL import Image
    out = bg.copy()
    for im, s in layers:
        box = (dsf * (540 - 540 / s), dsf * (760 - 760 / s), dsf * (540 + 540 / s), dsf * (760 + 1160 / s))
        lay = im.convert("RGBa").resize((1080, 1920), Image.LANCZOS, box=box).convert("RGBA")
        out.alpha_composite(lay)
    return out.convert("RGB")


async def _chunk(page_html, out_dir, items, dsf):
    import io
    from PIL import Image
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b, pg, layout = await _open(pw, page_html, dsf)
        await pg.evaluate("layers(0); solo(-1); document.body.classList.remove('solo')")
        bg = Image.open(io.BytesIO(await pg.screenshot())).convert("RGBA").resize((1080, 1920), Image.LANCZOS)
        for t, name in items:
            vis = await pg.evaluate("layers(%r)" % t)
            lays = []
            for pid, s in vis:
                await pg.evaluate("solo(%d)" % pid)
                png = await pg.screenshot(omit_background=True)
                lays.append((Image.open(io.BytesIO(png)), s))
            _compose(bg, lays, dsf).save(Path(out_dir) / name)
        await b.close()
        return layout


def _run_chunk(args):
    return asyncio.run(_chunk(*args))


def frames(page_html, out_dir, times, dsf=2, names=None, workers=3):
    """Снять кадры: render(t) по слоям планов -> наезд -> PNG 1080×1920. names — имена (по умолчанию %05d.png)."""
    from concurrent.futures import ProcessPoolExecutor
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    items = list(zip(times, names or ["%05d.png" % i for i in range(len(times))]))
    parts = [(str(page_html), str(out_dir), items[k::workers], dsf) for k in range(workers) if items[k::workers]]
    with ProcessPoolExecutor(len(parts)) as ex:
        return list(ex.map(_run_chunk, parts))[0]


def cover(sheet, work, out):
    """Обложка (style §10): бумага, метка рубрики 48 px --muted, ключевое слово 260 px --blue
    в зоне y 560–1100; плюс копия 180 px по ширине — проверка читаемости в сетке."""
    from PIL import Image
    from playwright.async_api import async_playwright
    from compile import ayah_tokens
    c, w = sheet["cover"], sheet["cover"].get("word") or {"page": 1}
    if c.get("text"):  # «Коран отвечает», «Путь»: ≤3 русских слова 120 px --ink (style §10)
        body = ("<div class='tx cg' style='top:600px;left:65px;width:950px;font-size:48px;line-height:1.2;"
                "color:var(--muted)'>%s</div><div class='tx cg' style='top:700px;left:65px;width:950px;"
                "font-size:120px;line-height:1.1;color:var(--ink)'>%s</div>" % (c["label"], c["text"]))
    else:
        words, _ = ayah_tokens(w["page"], w["surah"], w["ayah"])
        glyph = [x for x in words if x["pos"] == w["pos"]][0]["glyph"]
        body = ("<div class='tx cg' style='top:600px;left:65px;width:950px;font-size:48px;line-height:1.2;"
                "color:var(--muted)'>%s</div><div class='tx' style='top:660px;left:0;width:1080px;"
                "font:260px/1.6 v2p%d;color:var(--blue)'>%s</div>" % (c["label"], w["page"], glyph))
    doc = ("<!doctype html><html><head><meta charset='utf-8'><link href='https://fonts.googleapis.com/css2?"
           "family=Cormorant+Garamond:wght@600&display=block' rel='stylesheet'><style>@font-face{font-family:v2p%d;"
           "src:url(%s) format('woff2');font-display:block}" % (w["page"], V2 % w["page"]) + CSS +
           "</style></head><body><div class='bg'></div><img class='tex' src='" + TEX.as_uri() + "'>" + body +
           "</body></html>")
    p = Path(work) / "cover.html"
    p.write_text(doc, "utf-8")

    async def run():
        async with async_playwright() as pw:
            b = await pw.chromium.launch()
            pg = await b.new_page(viewport={"width": 1080, "height": 1920})
            await pg.goto(p.as_uri(), wait_until="networkidle")
            await pg.evaluate("Promise.all([document.fonts.load('260px v2p%d'), "
                              "document.fonts.load(\"600 48px 'Cormorant Garamond'\")])" % w["page"])
            await pg.evaluate("document.fonts.ready")
            await pg.screenshot(path=str(out), type="png")
            await b.close()
    asyncio.run(run())
    Image.open(out).resize((180, 320), Image.LANCZOS).save(Path(work) / "cover_180.png")
