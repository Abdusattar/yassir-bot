"""Снимки панели повторов 40+40 после отправки (20.09.2026).

Зачем: панель переделана из вопроса («Сколько сделал сегодня?» + чипы
+10/+20/+40) в подтверждение — две строки методики тем же языком, что
счётчик внизу, полоса на все 80 с засечкой на сороковом, поправка на один
повтор и «вписать число». Проверяем глазами на НАСТОЯЩЕМ приложении, а не
по описанию (правило: сверять макеты с живым кодом).

    python scripts/shoot_hifz_progress.py            # снять всё
    python scripts/shoot_hifz_progress.py --serve    # покрутить руками
    python scripts/shoot_hifz_progress.py --only full

Стенд поднимает shoot_onboarding (своё приложение, своя база, подменённая
авторизация). Указатель ставим на первую половину стр. 3 (этап 2), счётчик
набиваем в базу под каждый вариант и открываем панель тем же вызовом, что
и живая отправка.
"""
import argparse
import pathlib
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import shoot_onboarding as stand            # noqa: E402  (поднимает стенд целиком)
from core import mushaf_words               # noqa: E402
from aiohttp import web                     # noqa: E402

OUT = ROOT / "logs" / "hifz_progress"
PORT = 8803
WIDTH, HEIGHT = 390, 844

PAGE = 3
HALF_LINE = 0        # первая половина листа: этап 2, строка 0

# вариант -> сколько повторов уже засчитано
VARIANTS = {
    "start":  0,     # ничего ещё не набрано
    "look20": 20,    # идут первые сорок, «по памяти» приглушено
    "look40": 40,    # сорок глядя закрыты, вторая строка ожила
    "mem12":  52,    # работа по памяти
    # 79 + один тап «+» в самой панели: так ловится и шаг поправки, и подпись
    # кнопки при 80. Держать 80 в базе нельзя - место тут же догонит себя
    # (_hifz_catch_up) и панель откроется уже на следующей единице.
    "full":   79,
    "own":    52,    # то же, но открыто поле «вписать число»
    "wall":   80,    # долг открыт: при 80 шаг упирается в стену пересдачи
}

OPEN_JS = """
<script>
(function () {
  var v = new URLSearchParams(location.search).get('v');
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var $ = function (id) { return document.getElementById(id); };

  /* Панель открывает САМО приложение после успешной отправки, а его функции
     лежат в IIFE и снаружи не видны. Поэтому подменяем ровно одно - ответ
     сервера на отправку записи: у стенда нет телеграм-токена, и настоящая
     отправка упала бы. Всё остальное (запись через фальшивый микрофон Chrome,
     чтение счётчика, отрисовка панели) идёт живым кодом, не макетом. */
  var realFetch = window.fetch;
  window.fetch = function (url, opts) {
    if (String(url).indexOf('/hifz/submit') >= 0) {
      return Promise.resolve(new Response(JSON.stringify({ ok: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return realFetch.apply(window, arguments);
  };

  window.addEventListener('load', function () {
    (async function () {
      // Дорога в режим та же, что у человека (как в shoot_retake_gate).
      await wait(1200);
      $('dash-mushaf').click(); await wait(1500);
      $('btn-go-baqara').click(); await wait(1400);   // стр. 2, начало Бакары
      $('btn-prev').click(); await wait(1300);        // стр. 3 - лист целиком
      $('btn-hifz').click(); await wait(1200);
      $('hifz-submit').click(); await wait(700);
      // Этап 2 требует не меньше 20 секунд записи (HIFZ_MIN_SEC), иначе
      // приложение само отбивает её как слишком короткую для объёма.
      $('hifz-rec-go').click(); await wait(22000);
      $('hifz-rec-stop').click(); await wait(1200);
      $('hifz-rec-send').click(); await wait(1600);   // отсюда панель открывает приложение
      if (v === 'own') { $('hifz-progress-own').click(); await wait(500); }
      if (v === 'full') { $('hifz-progress-plus').click(); await wait(900); }
    })();
  });
})();
</script>
"""


def build():
    app = stand.build_app()

    async def variant_page(request):
        v = request.query.get("v", "mem12")
        # stage2 закрывает долг стенда повторной записью: иначе при 80 шаг
        # упирается в стену пересдачи и вместо кнопки «Дальше» открывается
        # «Работа с устазом» (это отдельная сцена, wall).
        stand.set_state("stage2" if v != "wall" else "default")
        mushaf_words.set_hifz_pointer(stand.STUDENT, PAGE, HALF_LINE, 2)
        mushaf_words.set_hifz_progress(stand.STUDENT, PAGE, 2, 0, VARIANTS.get(v, 0))
        return web.Response(text=stand.dev_index() + OPEN_JS, content_type="text/html")

    async def variant_frame(request):
        v = request.query.get("v", "mem12")
        w = int(request.query.get("w", WIDTH))
        return web.Response(content_type="text/html", text=(
            "<style>html,body{margin:0;background:#fff}"
            "iframe{border:0;display:block;width:%dpx;height:%dpx}</style>"
            "<iframe src='/v?v=%s&bot=male'></iframe>" % (w, HEIGHT, v)))

    app.router.add_get("/v", variant_page)
    app.router.add_get("/vframe", variant_frame)
    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    app = build()
    if args.serve:
        print("стенд: http://127.0.0.1:%d/vframe?v=mem12" % PORT)
        web.run_app(app, host="127.0.0.1", port=PORT, print=None)
        return

    threading.Thread(
        target=lambda: web.run_app(app, host="127.0.0.1", port=PORT, print=None,
                                   handle_signals=False),
        daemon=True).start()
    time.sleep(3)

    OUT.mkdir(parents=True, exist_ok=True)
    only = [s.strip() for s in args.only.split(",") if s.strip()]
    # Playwright, а не headless-снимок с --virtual-time-budget: запись голоса
    # идёт в РЕАЛЬНОМ времени, а виртуальное его перематывает - MediaRecorder
    # отдавал пустышку, приложение отбивало её как слишком короткую, и панель
    # не открывалась вовсе (поймано на первой съёмке 20.09).
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=[
            "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
        ])
        for name in VARIANTS:
            if only and name not in only:
                continue
            ctx = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT},
                                      permissions=["microphone"])
            pg = ctx.new_page()
            pg.goto("http://127.0.0.1:%d/v?v=%s&bot=male" % (PORT, name))
            pg.wait_for_timeout(35000)
            png = OUT / ("prog_%s.png" % name)
            pg.screenshot(path=str(png))
            ctx.close()
            print("  %-8s %4d КБ" % (name, png.stat().st_size // 1024))
        browser.close()
    print("снимки в %s" % OUT)


if __name__ == "__main__":
    main()
