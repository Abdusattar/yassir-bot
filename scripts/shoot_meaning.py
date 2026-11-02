"""Смысловой перевод (02.11.2026): жесты, переводчик, своё место чтения.

Проверки на стенде (390x844):
  tap       - короткое касание: перевод слова, панели нет;
  dbl       - двойное: ровно один POST /words/add, панели нет;
  hold      - удержание 700 мс: панель смысла аята, без перевода слова и без POST;
  holdmove  - удержание со сдвигом пальца: ничего;
  swipe     - смахивание вбок листает лист;
  hifz      - выбор строки в заучивании + удержание: панель, строка НЕ выбрана;
  toggle    - Кулиев -> Абу Адель меняет текст и переживает перезагрузку;
  reader    - 📜: прокрутил, вышел, перезагрузил - открылось на том же аяте;
  ky        - кыргызский интерфейс: кыргызский текст, переключателя нет.
  close     - ✕ закрывает панель, перевод слова не открывается.
Плюс снимки панели и чтения в светлой и тёмной теме - смотреть глазами.

Жесты - настоящие касания через CDP (Chromium). В WebKit - те же сцены мышью:
Playwright WebKit не iOS, живой айфон всё равно нужен.

    python scripts/shoot_meaning.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import shoot_landscape as land              # noqa: E402

OUT = ROOT / "logs" / "meaning"
PAGE = 328

STATE = """() => {
  var sh = document.getElementById('ayah-sheet');
  var pop = document.getElementById('word-popup');
  return { sheet: !sh.hidden, text: document.getElementById('as-text').textContent,
           ref: document.getElementById('as-ref').textContent,
           popup: pop.classList.contains('visible'),
           page: document.getElementById('ayah-text').getAttribute('data-page'),
           seg: !document.getElementById('as-seg').hidden,
           hl: document.querySelectorAll('#ayah-text .ma-hl').length };
}"""


class Finger:
    """Касание: CDP touch в Chromium, мышь в WebKit."""

    def __init__(self, pg, engine):
        self.pg, self.engine = pg, engine
        self.cdp = pg.context.new_cdp_session(pg) if engine == "chromium" else None

    def _t(self, kind, x, y):
        pts = [] if kind == "touchEnd" else [{"x": x, "y": y}]
        self.cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": pts})

    def press(self, x, y, ms, move=None):
        if self.cdp:
            self._t("touchStart", x, y)
            if move:
                self.pg.wait_for_timeout(120)
                for k in range(1, 6):
                    self._t("touchMove", x + move[0] * k / 5, y + move[1] * k / 5)
            self.pg.wait_for_timeout(ms)
            self._t("touchEnd", x, y)
        else:
            m = self.pg.mouse
            m.move(x, y)
            m.down()
            if move:
                self.pg.wait_for_timeout(120)
                m.move(x + move[0], y + move[1], steps=5)
            self.pg.wait_for_timeout(ms)
            m.up()

    def tap(self, x, y):
        self.press(x, y, 40)


def word_xy(pg, sel="#ayah-text .mushaf-line:nth-child(3) [data-ma]"):
    b = pg.locator(sel).first.bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def open_app(b, engine, init="", theme="light", touch=True):
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                        has_touch=(touch and engine == "chromium"))
    ctx.add_init_script("try{localStorage.setItem('yassir_mushaf_page','%d');"
                        "localStorage.setItem('yassir_theme','%s');%s}catch(e){}" % (PAGE, theme, init))
    pg = ctx.new_page()
    errors, posts = [], []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/words/add" in r.url else None)
    pg.goto(f"http://127.0.0.1:{land.PORT}/new?bot=male")
    pg.wait_for_timeout(2500)
    pg.evaluate("document.getElementById('dash-mushaf').click()")
    pg.wait_for_function("document.querySelectorAll('#ayah-text [data-ma]').length > 0", timeout=20000)
    pg.wait_for_timeout(2200)
    return ctx, pg, errors, posts


def run(pw, engine, problems):
    b = getattr(pw, engine).launch()
    say = lambda msg: problems.append(f"{engine}: {msg}")   # noqa: E731

    ctx, pg, errors, posts = open_app(b, engine)
    f = Finger(pg, engine)
    x, y = word_xy(pg)

    f.tap(x, y); pg.wait_for_timeout(700)
    st = pg.evaluate(STATE)
    if not st["popup"] or st["sheet"]:
        say(f"tap: перевод слова {st['popup']}, панель {st['sheet']}")
    pg.wait_for_timeout(2500)

    f.tap(x, y); pg.wait_for_timeout(90); f.tap(x, y); pg.wait_for_timeout(900)
    st = pg.evaluate(STATE)
    if len(posts) != 1 or st["sheet"]:
        say(f"dbl: POST {len(posts)}, панель {st['sheet']}")
    pg.wait_for_timeout(2500)

    n0 = len(posts)
    f.press(x, y, 700); pg.wait_for_timeout(600)
    st = pg.evaluate(STATE)
    if not st["sheet"] or st["popup"] or len(posts) != n0 or not st["hl"]:
        say(f"hold: панель {st['sheet']}, перевод слова {st['popup']}, POST +{len(posts) - n0}, подсветка {st['hl']}")
    if "загружа" in st["text"].lower() or not st["text"].strip():
        say(f"hold: пустой текст {st['text']!r}")
    pg.screenshot(path=str(OUT / f"{engine}_hold_light.png"))
    print(f"  {engine} hold: {st['ref']} | {st['text'][:70]}")

    # Самая тесная шапка: длинное имя суры и 2:286 - строка не вылезает.
    over = pg.evaluate("""() => { var r=document.getElementById('as-ref'), keep=r.innerHTML;
        r.innerHTML='<bdi class="ar" dir="rtl">المنافقون</bdi> 2:286';
        var h=document.querySelector('#ayah-sheet .as-head'), d=h.scrollWidth-h.clientWidth;
        r.innerHTML=keep; return d; }""")
    if over > 0:
        say(f"шапка панели вылезает на {over}px")
    pg.click("#as-seg button[data-mtr=ru_abuadel]"); pg.wait_for_timeout(500)
    abu = pg.evaluate(STATE)["text"]
    if abu == st["text"] or not abu.strip():
        say("toggle: текст не сменился")
    pg.screenshot(path=str(OUT / f"{engine}_hold_abuadel.png"))
    pg.click("#as-close"); pg.wait_for_timeout(400)
    st = pg.evaluate(STATE)
    if st["sheet"] or st["popup"]:
        say(f"✕: панель {st['sheet']}, перевод слова {st['popup']}")
    pg.wait_for_timeout(2500)
    f.press(x, y, 700); pg.wait_for_timeout(700)
    pg.click("#ayah-sheet-dim", position={"x": 195, "y": 60}); pg.wait_for_timeout(400)
    if pg.evaluate(STATE)["sheet"]:
        say("тап по листу не закрыл панель")
    if pg.evaluate(STATE)["popup"]:
        say("тап по затемнению открыл перевод слова")
    pg.wait_for_timeout(2500)

    f.press(x, y, 700, move=(0, 40)); pg.wait_for_timeout(500)
    if pg.evaluate(STATE)["sheet"]:
        say("holdmove: панель открылась при сдвиге пальца")
    pg.wait_for_timeout(2500)

    if engine == "chromium":
        f.press(300, 400, 60, move=(-160, 0)); pg.wait_for_timeout(2500)
        if pg.evaluate(STATE)["page"] == str(PAGE):
            say("swipe: лист не перелистнулся")
    if errors:
        say(f"ошибки страницы {errors[:2]}")
    ctx.close()

    # Перезагрузка: выбор Абу Аделя остался.
    ctx, pg, errors, posts = open_app(b, engine, "localStorage.setItem('yassir_meaning_tr','ru_abuadel');")
    f = Finger(pg, engine)
    x, y = word_xy(pg)
    f.press(x, y, 700); pg.wait_for_timeout(700)
    st = pg.evaluate(STATE)
    if st["text"] != abu:
        say("toggle: после перезагрузки не Абу Адель")
    ctx.close()

    # Заучивание: выбор строки + удержание.
    ctx, pg, errors, posts = open_app(b, engine)
    f = Finger(pg, engine)
    pg.evaluate("document.getElementById('btn-hifz').click()"); pg.wait_for_timeout(1500)
    before = pg.evaluate("document.getElementById('hifz-where').textContent")
    x, y = word_xy(pg)
    f.press(x, y, 700); pg.wait_for_timeout(800)
    st = pg.evaluate(STATE)
    after = pg.evaluate("document.getElementById('hifz-where').textContent")
    if not st["sheet"] or before != after:
        say(f"hifz: панель {st['sheet']}, место {before!r} -> {after!r}")
    pg.screenshot(path=str(OUT / f"{engine}_hifz_hold.png"))
    ctx.close()

    # Чтение смысла: своё место.
    ctx, pg, errors, posts = open_app(b, engine, "localStorage.removeItem('yassir_meaning_pos');")
    pg.click("#btn-meaning"); pg.wait_for_timeout(2500)   # ответ сервера с местом прошлого прогона
    # С первой суры, независимо от места прошлых прогонов, - на 21-ю.
    pg.evaluate("var p=document.getElementById('mr-prev');for(var i=0;i<120;i++)p.click();"
                "var s=document.getElementById('mr-next');for(var i=0;i<20;i++)s.click();")
    pg.wait_for_timeout(1500)
    want = pg.evaluate("document.querySelector('#mr-text .mr-sura .num').textContent")
    pg.evaluate("var r=document.querySelector('#mr-text [data-a=\"12\"]');"
                "document.getElementById('mr-scroll').scrollTop=r.offsetTop-8;")
    pg.wait_for_timeout(2500)
    pg.click("#mr-back"); pg.wait_for_timeout(600)
    ctx.close()
    ctx, pg, errors, posts = open_app(b, engine)   # localStorage тот же? нет - новый контекст
    # Новый контекст = другое устройство: место должно прийти с сервера.
    pg.click("#btn-meaning"); pg.wait_for_timeout(3000)
    top = pg.evaluate("""() => { var box=document.getElementById('mr-scroll').getBoundingClientRect().top;
        var rows=document.querySelectorAll('#mr-text .mr-a');
        for (var i=0;i<rows.length;i++) if (rows[i].getBoundingClientRect().bottom>box+24) return rows[i].getAttribute('data-a');
        return null; }""")
    head = pg.evaluate("document.querySelector('#mr-text .mr-sura .num').textContent")
    pg.screenshot(path=str(OUT / f"{engine}_reader_light.png"))
    print(f"  {engine} reader: {head}, верхний аят {top}")
    if head != want or top not in ("11", "12"):
        say(f"reader: открылось {head} аят {top}, ждали {want} аят 12")
    pg.wait_for_timeout(3000)
    pg.screenshot(path=str(OUT / f"{engine}_reader_here_gone.png"))
    ctx.close()

    # Android: contextmenu раньше таймера (~400 мс) - панель сразу, не ждём 500 мс.
    ctx, pg, errors, posts = open_app(b, engine, touch=False)
    x, y = word_xy(pg)
    pg.mouse.move(x, y); pg.mouse.down(); pg.wait_for_timeout(150)
    pg.evaluate("(function(x,y){var el=document.elementFromPoint(x,y);"
                "el.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:x,clientY:y}));})"
                "(%d,%d)" % (x, y))
    pg.wait_for_timeout(120)
    early = pg.evaluate(STATE)["sheet"]
    pg.mouse.up(); pg.wait_for_timeout(700)
    st = pg.evaluate(STATE)
    if not early or not st["sheet"] or st["popup"]:
        say(f"android contextmenu: сразу {early}, потом {st['sheet']}, перевод слова {st['popup']}")
    ctx.close()

    # Лёжа (= «Крупно» в заучивании): панель.
    b2ctx = b.new_context(viewport={"width": 844, "height": 390}, device_scale_factor=2,
                          has_touch=(engine == "chromium"))
    b2ctx.add_init_script("try{localStorage.setItem('yassir_mushaf_page','%d')}catch(e){}" % PAGE)
    pg = b2ctx.new_page()
    pg.goto(f"http://127.0.0.1:{land.PORT}/new?bot=male"); pg.wait_for_timeout(2500)
    pg.evaluate("document.getElementById('dash-mushaf').click()")
    pg.wait_for_function("document.querySelectorAll('#ayah-text [data-ma]').length > 0", timeout=20000)
    pg.wait_for_timeout(2200)
    f = Finger(pg, engine)
    x, y = word_xy(pg, "#ayah-text .mushaf-line:nth-child(1) [data-ma]")
    f.press(x, y, 700); pg.wait_for_timeout(700)
    if not pg.evaluate(STATE)["sheet"]:
        say("лёжа: панель не открылась")
    pg.screenshot(path=str(OUT / f"{engine}_hold_land.png"))
    pg.click("#ayah-sheet-dim", position={"x": 420, "y": 30}); pg.wait_for_timeout(300)
    # «Крупно» с 22.09 - это сам лист лёжа (#hifz-big не открывается), проверено выше.
    b2ctx.close()

    # Тёмная тема и кыргызский.
    ctx, pg, errors, posts = open_app(b, engine, theme="dark")
    f = Finger(pg, engine)
    x, y = word_xy(pg)
    f.press(x, y, 700); pg.wait_for_timeout(700)
    pg.screenshot(path=str(OUT / f"{engine}_hold_dark.png"))
    pg.click("#ayah-sheet-dim", position={"x": 195, "y": 60}); pg.wait_for_timeout(300)
    pg.click("#btn-meaning"); pg.wait_for_timeout(2500)
    pg.screenshot(path=str(OUT / f"{engine}_reader_dark.png"))
    ctx.close()

    ctx, pg, errors, posts = open_app(b, engine)
    # Язык - как человек, через настройки: стенд берёт его с сервера.
    pg.evaluate("document.querySelector('#sett-lang button[data-lang=ky]').click()")
    pg.wait_for_timeout(1500)
    f = Finger(pg, engine)
    x, y = word_xy(pg)
    f.press(x, y, 700); pg.wait_for_timeout(800)
    st = pg.evaluate(STATE)
    print(f"  {engine} ky: {st['text'][:60]}")
    if st["seg"] or not st["sheet"] or not any(c in st["text"] for c in "өүң"):
        say(f"ky: переключатель {st['seg']}, текст {st['text'][:40]!r}")
    pg.screenshot(path=str(OUT / f"{engine}_hold_ky.png"))
    pg.evaluate("document.querySelector('#sett-lang button[data-lang=ru]').click()")
    pg.wait_for_timeout(1200)
    if errors:
        say(f"ошибки страницы {errors[:2]}")
    ctx.close()
    b.close()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    land.serve({"new": land.page_html(None)})
    from playwright.sync_api import sync_playwright
    problems = []
    with sync_playwright() as pw:
        for engine in ("chromium", "webkit"):
            run(pw, engine, problems)
    print("\nПРОБЛЕМЫ:\n  " + "\n  ".join(problems) if problems else "\nпроблем нет")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
