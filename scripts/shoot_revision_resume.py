"""Снимки прерванного чтения повторения (20.09.2026).

Зачем: у Бекхана (G-10, ребёнок) запись рвалась — Telegram перезапускал
вкладку, и восемь минут чтения пропадали. Теперь куски ложатся на телефон, и
приложение предлагает продолжить. Проверяем это на ЖИВОМ приложении, а не по
описанию: пишем, роняем страницу посреди записи, открываем заново.

    python scripts/shoot_revision_resume.py           # снять всё
    python scripts/shoot_revision_resume.py --serve   # покрутить руками

Сцены:
  rec       — идёт запись (после неё страница «падает»)
  broken    — вернулись: «Запись прервалась. Ты прочитал 0:12»
  resumed   — нажали «Продолжить чтение», запись идёт дальше
  sent      — «Стоп» и отправка (ответ сервера подменён: токена у стенда нет)
"""
import argparse
import pathlib
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import shoot_onboarding as stand            # noqa: E402
import core.db as db                        # noqa: E402
from aiohttp import web                     # noqa: E402

OUT = ROOT / "logs" / "revision_resume"
PORT = 8807
WIDTH, HEIGHT = 390, 844

SCENES = ("rec", "broken", "resumed", "sent")

JS = """
<script>
(function () {
  var v = new URLSearchParams(location.search).get('v');
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var $ = function (id) { return document.getElementById(id); };

  /* Подменяем только ответ на отправку: у стенда нет телеграм-токена, а всё
     остальное - запись через фальшивый микрофон Chrome, хранение кусков,
     экран продолжения - идёт живым кодом. */
  var realFetch = window.fetch;
  window.fetch = function (url) {
    if (String(url).indexOf('/revision/submit') >= 0) {
      return Promise.resolve(new Response(JSON.stringify({ ok: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return realFetch.apply(window, arguments);
  };

  window.addEventListener('load', function () {
    (async function () {
      await wait(1200);
      var back = sessionStorage.getItem('shot-phase') === 'back';
      $('dash-mushaf').click(); await wait(1500);

      if (!back) {
        // Первый заход: начинаем читать и «роняем» вкладку посреди записи -
        // ровно то, что делает Telegram при нехватке памяти.
        $('btn-revision').click(); await wait(1200);
        $('hifz-rec-go').click(); await wait(12000);
        if (v === 'rec') return;                 // снимок идущей записи
        sessionStorage.setItem('shot-phase', 'back');
        location.reload();
        return;
      }

      sessionStorage.removeItem('shot-phase');
      $('btn-revision').click(); await wait(1500);
      if (v === 'broken') return;                // «Запись прервалась»
      $('hifz-rec-continue').click(); await wait(9000);
      if (v === 'resumed') return;               // читает дальше
      $('hifz-rec-stop').click(); await wait(1200);
      $('hifz-rec-send').click(); await wait(2000);
    })();
  });
})();
</script>
"""


def build():
    app = stand.build_app()

    async def page(request):
        stand.set_state("default")
        # Ребёнок: повторение засчитывается только записью, и 🔁 открывает
        # панель сразу, без вопроса «вы сделали повторение?».
        db.set_student_birth_year(stand.STUDENT, 2015)
        return web.Response(text=stand.dev_index() + JS, content_type="text/html")

    app.router.add_get("/v", page)
    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    app = build()
    if args.serve:
        print("стенд: http://127.0.0.1:%d/v?v=broken&bot=male" % PORT)
        web.run_app(app, host="127.0.0.1", port=PORT, print=None)
        return

    threading.Thread(
        target=lambda: web.run_app(app, host="127.0.0.1", port=PORT, print=None,
                                   handle_signals=False),
        daemon=True).start()
    time.sleep(3)

    OUT.mkdir(parents=True, exist_ok=True)
    only = [s.strip() for s in args.only.split(",") if s.strip()]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=[
            "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
        ])
        for name in SCENES:
            if only and name not in only:
                continue
            ctx = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT},
                                      permissions=["microphone"])
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto("http://127.0.0.1:%d/v?v=%s&bot=male" % (PORT, name))
            pg.wait_for_timeout(45000)
            png = OUT / ("rev_%s.png" % name)
            pg.screenshot(path=str(png))
            print("  %-8s %4d КБ%s" % (name, png.stat().st_size // 1024,
                                       ("  ОШИБКИ: " + "; ".join(errors[:2])) if errors else ""))
            ctx.close()
        browser.close()
    print("снимки в %s" % OUT)


if __name__ == "__main__":
    main()
