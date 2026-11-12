"""МАКЕТ (12.11.2026): пояснение к слову по нажатию. Кода в приложении нет -
разметка и стили вставляются в стенд поверх настоящей страницы, чтобы показать
пользователю варианты на 390x844 до реализации.

Слово - رَٰعِنَا (2:104), самое длинное пояснение первого джуза
(logs/wbw_ru_juz1/explain.json): худший случай по объёму текста.

  a_inline  - вариант А: пояснение сразу в подсказке;
  b_tip     - вариант Б: подсказка с подписью и строкой «Подробнее»;
  b_sheet   - вариант Б: панель снизу по нажатию на подсказку (стиль #ayah-sheet);
  plain     - обычное слово без пояснения (как сейчас) - для сравнения.

    python scripts/shoot_word_note.py            # снимки
    python scripts/shoot_word_note.py --serve    # живой стенд: http://127.0.0.1:8812/new?bot=male&wn=b
                                                 # (wn=a - пояснение сразу; все 28 слов первого джуза)
"""
import os
if "--serve" in __import__("sys").argv:
    os.environ.setdefault("LAND_PORT", "8812")   # свой порт: стенд не мешает съёмке (8810)
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import shoot_landscape as land              # noqa: E402

OUT = ROOT / "logs" / "word_note"
PAGE = 16
LOC = "2:104:6"

CSS = """
#word-popup.wn { white-space: normal; text-align: left; max-width: 300px; padding: 10px 14px 11px;
  border-radius: 12px; background: color-mix(in srgb, var(--popup-bg) 94%, transparent); pointer-events: auto; }
#word-popup.wn .wn-gl { font-size: 15px; font-weight: 600; }
#word-popup.wn .wn-note { margin-top: 6px; font-size: 13.5px; line-height: 1.45; opacity: .92; }
#word-popup.wn .wn-src { margin-top: 6px; font-size: 11.5px; opacity: .6; }
#word-popup.wn-b { text-align: center; padding: 7px 14px 0; }
#word-popup.wn-b .wn-more { display: block; margin: 6px -14px 0; padding: 6px 14px 7px; font-size: 12.5px;
  color: var(--marker-color); border-top: 1px solid color-mix(in srgb, var(--popup-ink) 18%, transparent); }
#wn-sheet { position: fixed; left: 0; right: 0; bottom: 0; z-index: 89; max-width: 640px; margin: 0 auto;
  direction: ltr; text-align: left; background: var(--mushaf-bg-start); border-radius: 18px 18px 0 0;
  box-shadow: 0 -8px 30px rgba(30, 25, 10, 0.16); padding-bottom: 14px; }
#wn-sheet .wn-word { font-family: 'Scheherazade New', serif; font-size: 30px; line-height: 1.2; color: var(--ink); }
#wn-sheet .wn-gloss { padding: 0 18px; font-size: 18px; font-weight: 600; color: var(--ink); }
#wn-sheet .wn-text { padding: 8px 18px 0; font-size: 17px; line-height: 1.62; color: var(--ink); }
#wn-sheet .wn-from { padding: 10px 18px 0; font-size: 13px; color: var(--muted); }
"""

JS_FIND = """(loc) => {
  var el = document.querySelector('#ayah-text [data-w="' + loc + '"]');
  if (!el) { var p = loc.split(':'); el = Array.from(document.querySelectorAll('#ayah-text [data-ma]'))
      .find(function (e) { return (e.getAttribute('data-ma') || '').indexOf(p[0] + ':' + p[1]) === 0; }); }
  if (!el) return null;
  var r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2, top: r.top, bottom: r.bottom,
           attrs: Array.from(el.attributes).map(function (a) { return a.name + '=' + a.value; }).join(' ').slice(0, 200) };
}"""

JS_TIP = """(a) => {
  var p = document.getElementById('word-popup');
  p.className = 'visible wn ' + a.cls; p.innerHTML = a.html;
  p.style.left = '0px';
  var w = p.getBoundingClientRect().width, c = Math.min(Math.max(a.x, w / 2 + 8), innerWidth - w / 2 - 8);
  p.style.transform = 'translate(-50%, -100%)'; p.style.left = c + 'px'; p.style.top = (a.top - 8) + 'px';
  if (p.getBoundingClientRect().top < 60) { p.style.transform = 'translate(-50%, 0)'; p.style.top = (a.bottom + 8) + 'px'; }
}"""


LIVE_JS = r"""
(function () {
  var NOTES = __NOTES__, V = (new URLSearchParams(location.search).get('wn') || 'b');
  var pop, hold = null, pend = null, obs = null;
  // Штатная подсказка появляется позже нажатия (ждёт двойного касания) - подменяем её, когда она показалась.
  function apply() {
    if (!pend || !pop.classList.contains('visible') || pop.classList.contains('wn')) return;
    var n = pend.n, el = pend.el; pend = null; pop._n = n;
    if (V === 'a') { pop.className = 'visible wn wn-hold'; pop.innerHTML = '<div class="wn-gl">' + esc(n.g) + '</div><div class="wn-note">' + esc(n.note) + '</div><div class="wn-src">' + esc(n.src) + '</div>'; }
    else { pop.className = 'visible wn wn-b wn-hold'; pop.innerHTML = esc(n.g) + '<span class="wn-more">Подробнее</span>'; }
    place(el);
    hold = setTimeout(function () { pop.classList.remove('wn-hold', 'visible'); }, V === 'a' ? 9000 : 4000);
  }
  function esc(t) { return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
  function place(el) {
    var r = el.getBoundingClientRect(); pop.style.left = '0px';
    var w = pop.getBoundingClientRect().width, c = Math.min(Math.max(r.left + r.width / 2, w / 2 + 8), innerWidth - w / 2 - 8);
    pop.style.transform = 'translate(-50%, -100%)'; pop.style.left = c + 'px'; pop.style.top = (r.top - 8) + 'px';
    if (pop.getBoundingClientRect().top < 60) { pop.style.transform = 'translate(-50%, 0)'; pop.style.top = (r.bottom + 8) + 'px'; }
  }
  function closeSheet() { ['wn-sheet', 'wn-dim'].forEach(function (id) { var e = document.getElementById(id); if (e) e.remove(); }); }
  function openSheet(n) {
    closeSheet(); pop.classList.remove('wn-hold', 'visible');
    var d = document.createElement('div'); d.id = 'wn-dim'; document.body.appendChild(d);
    setTimeout(function () { d.onclick = closeSheet; }, 450);   // то же касание не должно закрыть панель
    var s = document.createElement('div'); s.id = 'wn-sheet';
    s.innerHTML = '<div class="as-head"><span class="wn-word" dir="rtl">' + n.ar + '</span><span class="as-tools">'
      + '<span class="as-ref">' + n.key.split(':').slice(0, 2).join(':') + '</span><button id="wn-x" type="button" '
      + 'style="width:40px;height:40px;background:none;border:0;font-size:17px;color:var(--muted)">✕</button></span></div>'
      + '<div class="wn-gloss">' + esc(n.g) + '</div><div class="wn-text mr-serif">' + esc(n.note) + '</div>'
      + '<div class="wn-from">' + esc(n.src) + '</div>';
    document.body.appendChild(s); document.getElementById('wn-x').onclick = closeSheet;
  }
  document.addEventListener('pointerup', function (ev) {
    pop = document.getElementById('word-popup');
    if (ev.target.closest && ev.target.closest('#word-popup') && pop._n && V !== 'a') { openSheet(pop._n); return; }
    var el = ev.target.closest && ev.target.closest('#ayah-text [data-w]');
    clearTimeout(hold); pend = null; if (pop) { pop.classList.remove('wn', 'wn-b', 'wn-hold'); pop._n = null; }
    if (!el) return;
    var n = NOTES[el.getAttribute('data-w')]; if (!n) return;
    pend = { el: el, n: n };
    if (!obs) { obs = new MutationObserver(apply); obs.observe(pop, { childList: true, attributes: true, attributeFilter: ['class'] }); }
  }, true);
  if (!sessionStorage.getItem('wn')) { try { localStorage.setItem('yassir_mushaf_page', '16'); } catch (e) {} sessionStorage.setItem('wn', '1'); }
  window.addEventListener('load', function () { setTimeout(function () { var b = document.getElementById('dash-mushaf'); if (b) b.click(); }, 2500); });
})();
"""


def live_page():
    """Страница стенда с живым макетом: нажатие на слово с пояснением."""
    notes = {}
    for e in json.loads((ROOT / "logs/wbw_ru_juz1/explain.json").read_text(encoding="utf-8")):
        notes[e["key"]] = {"key": e["key"], "ar": e["ar"], "g": e["gloss"].strip(" ,.–"), "note": e["note"],
                           "src": "Тафсир аль-Муяссар" if e["source"] == "Муяссар" else "Тафсир ас-Саади"}
    extra = ("<style>" + CSS + "#word-popup.wn-hold{opacity:1 !important}"
             "#wn-dim{position:fixed;inset:0;z-index:88;background:rgba(30,25,10,.14)}</style>"
             "<script>" + LIVE_JS.replace("__NOTES__", json.dumps(notes, ensure_ascii=False)) + "</script>")
    html = land.page_html(None)
    return html.replace("</head>", extra + "</head>", 1)


def main():
    if "--serve" in sys.argv:
        import time
        land.serve({"new": live_page()})
        print(f"стенд: http://127.0.0.1:{land.PORT}/new?bot=male&wn=b", flush=True)
        while True:
            time.sleep(3600)
    OUT.mkdir(parents=True, exist_ok=True)
    note = next(e for e in json.loads((ROOT / "logs/wbw_ru_juz1/explain.json").read_text(encoding="utf-8"))
                if e["key"] == LOC)
    src = "Тафсир аль-Муяссар" if note["source"] == "Муяссар" else "Тафсир ас-Саади"
    gloss = note["gloss"].strip(" ,.")
    land.serve({"new": land.page_html(None)})
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for theme in ("light", "dark"):
            ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True)
            ctx.add_init_script("try{localStorage.setItem('yassir_mushaf_page','%d');"
                                "localStorage.setItem('yassir_theme','%s');}catch(e){}" % (PAGE, theme))
            pg = ctx.new_page()
            pg.goto(f"http://127.0.0.1:{land.PORT}/new?bot=male")
            pg.wait_for_timeout(2500)
            pg.evaluate("document.getElementById('dash-mushaf').click()")
            pg.wait_for_function("document.querySelectorAll('#ayah-text [data-ma]').length > 0", timeout=20000)
            pg.wait_for_timeout(2200)
            pg.add_style_tag(content=CSS)
            w = pg.evaluate(JS_FIND, LOC)
            if not w:
                raise SystemExit("слово не найдено на странице")
            if theme == "light":
                print("слово:", w["attrs"])
            pg.touchscreen.tap(w["x"], w["y"]); pg.wait_for_timeout(500)   # настоящая подсветка слова
            base = {"x": w["x"], "top": w["top"], "bottom": w["bottom"]}
            if theme == "light":
                pg.evaluate(JS_TIP, dict(base, cls="", html=(
                    f'<div class="wn-gl">{gloss}</div><div class="wn-note">{note["note"]}</div>'
                    f'<div class="wn-src">{src}</div>')))
                pg.screenshot(path=str(OUT / "a_inline.png"))
            pg.evaluate(JS_TIP, dict(base, cls="wn-b", html=f'{gloss}<span class="wn-more">Подробнее</span>'))
            pg.screenshot(path=str(OUT / f"b_tip_{theme}.png"))
            pg.evaluate("""(a) => {
              var p = document.getElementById('word-popup'); p.className = ''; p.innerHTML = '';
              var d = document.createElement('div'); d.id = 'ayah-sheet-dim'; d.style.zIndex = 88; document.body.appendChild(d);
              var s = document.createElement('div'); s.id = 'wn-sheet';
              s.innerHTML = '<div class="as-head"><span class="wn-word" dir="rtl">' + a.ar + '</span>'
                + '<span class="as-tools"><span class="as-ref">2:104</span>'
                + '<button id="as-close" type="button">✕</button></span></div>'
                + '<div class="wn-gloss">' + a.gloss + '</div><div class="wn-text mr-serif">' + a.note + '</div>'
                + '<div class="wn-from">' + a.src + '</div>';
              document.body.appendChild(s);
            }""", {"ar": note["ar"], "gloss": gloss, "note": note["note"], "src": src})
            pg.wait_for_timeout(300)
            pg.screenshot(path=str(OUT / f"b_sheet_{theme}.png"))
            over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            print(theme, "горизонтальный вылет:", over)
            ctx.close()
        b.close()

    from PIL import Image, ImageDraw, ImageFont
    names = [("a_inline.png", "А: пояснение сразу"), ("b_tip_light.png", "Б: подпись + «Подробнее»"),
             ("b_sheet_light.png", "Б: по нажатию"), ("b_sheet_dark.png", "Б: тёмная тема")]
    ims = [Image.open(OUT / n).convert("RGB") for n, _ in names]
    w, h = ims[0].size
    pad, top = 30, 90
    sheet = Image.new("RGB", (len(ims) * (w + pad) + pad, h + top + pad), "#e9e6df")
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 44)
    except OSError:
        font = ImageFont.load_default()
    for i, (im, (_, title)) in enumerate(zip(ims, names)):
        x = pad + i * (w + pad)
        d.text((x, 24), title, fill="#222", font=font)
        sheet.paste(im, (x, top))
    sheet.thumbnail((2600, 2600))
    sheet.save(OUT / "compare.jpg", quality=88)
    print("готово:", OUT / "compare.jpg")


if __name__ == "__main__":
    main()
