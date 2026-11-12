# -*- coding: utf-8 -*-
"""Запись без звука на живом приложении (12.11.2026, Дилярам, женская prep, Android).

Её телефон в режиме «микрофон без обработки» отдавал цифровую тишину: три сдачи по
16-22 с с пиком -91 дБ; она слушала запись, ничего не слышала и не отправляла.
Проверяем оба заслона на стенде (Chrome с поддельным микрофоном):

  silent - микрофон отдаёт тишину (wav из нулей). Ждём: сразу после «Стоп» подсказка
           «В записи нет звука…», телефон запомнил обычный микрофон (hifz_mic_plain=1);
           «Отправить» - сервер отвечает error=silent, сдача не создаётся.
  tone   - обычный поддельный микрофон (гудок). Ждём: обычная подсказка, флага нет,
           отправка принята.

    python scripts/check_rec_silent.py
"""
import pathlib
import sys
import tempfile
import threading
import time
import wave

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_rec_redo as redo               # noqa: E402
import shoot_onboarding as stand            # noqa: E402
import core.db as db                        # noqa: E402
from aiohttp import web                     # noqa: E402

PORT = 8841

JS = """
<script>
(function () {
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var $ = function (id) { return document.getElementById(id); };
  var hint = function () { return ($('hifz-rec-hint') || {}).textContent || ''; };
  var flag = function () { try { return localStorage.getItem('hifz_mic_plain'); } catch (e) { return 'err'; } };
  window.__log = [];
  var realFetch = window.fetch;
  window.fetch = function (url, opts) {
    var p = realFetch.apply(window, arguments);
    if (String(url).indexOf('/submit') >= 0 && opts && opts.body && opts.body.forEach) {
      var sizes = [];
      opts.body.forEach(function (v, k) { if (k.indexOf('audio') === 0) sizes.push(k + ' ' + v.size + ' байт'); });
      p.then(function (r) { return r.clone().text(); }).then(function (txt) {
        window.__log.push('отправка: ' + sizes.join(', ') + ', ms=' + opts.body.get('ms') + ' -> ' + txt.slice(0, 120));
      });
    }
    return p;
  };
  window.addEventListener('load', function () {
    (async function () {
      await wait(1200);
      $('dash-mushaf').click(); await wait(1500);
      $('btn-revision').click(); await wait(1500);
      $('hifz-rec-go').click(); await wait(7000);
      $('hifz-rec-stop').click(); await wait(1500);
      window.__log.push('после «Стоп»: ' + hint() + ' | обычный микрофон: ' + flag());
      var send = $('hifz-rec-send');
      if (send) { send.click(); await wait(8000); } else window.__log.push('кнопки «Отправить» нет');
      window.__log.push('после «Отправить»: ' + hint() + ' | обычный микрофон: ' + flag());
      window.__done = true;
    })();
  });
})();
</script>
"""


def silence_wav():
    path = pathlib.Path(tempfile.mkdtemp(prefix="rec-silent-")) / "silence.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(b"\0\0" * 48000 * 10)
    return path


def run(sc, port):
    html = redo.page_html(False) + JS
    app = stand.build_app()

    async def page(request):
        stand.set_state("default")
        db.set_student_birth_year(stand.STUDENT, 2015)   # ребёнок: повторение записью
        return web.Response(text=html, content_type="text/html")

    app.router.add_get("/v", page)
    threading.Thread(target=lambda: web.run_app(app, host="127.0.0.1", port=port, print=None,
                                                handle_signals=False), daemon=True).start()
    time.sleep(3)
    args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
    if sc == "silent":
        args.append("--use-file-for-fake-audio-capture=%s" % silence_wav())
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=args)
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, permissions=["microphone"])
        pg = ctx.new_page()
        errors, answers = [], []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        def on_response(r):
            if r.request.method == "POST" and ("revision" in r.url or "hifz" in r.url):
                try:
                    answers.append("%s -> %s" % (r.url.rsplit("/api/", 1)[-1][:40], r.text()[:120]))
                except Exception:
                    pass
        pg.on("response", on_response)
        pg.goto("http://127.0.0.1:%d/v?bot=male" % port)
        pg.wait_for_function("window.__done", timeout=120000)
        log = pg.evaluate("window.__log")
        shot = ROOT / "logs" / "app_snap" / ("rec_%s.png" % sc)
        shot.parent.mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=str(shot))
        browser.close()
    print("== %s" % sc)
    for line in log:
        print("  ", line)
    for a in answers:
        print("   сервер:", a)
    if errors:
        print("   ОШИБКИ страницы:", "; ".join(errors[:3]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for i, sc in enumerate(("silent", "tone")):
        run(sc, PORT + i)


if __name__ == "__main__":
    main()
