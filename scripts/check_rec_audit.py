"""Запись и отправка на живом приложении - случаи из аудита 23.09.2026.

Фальшивый микрофон Chrome, отправка перехвачена - смотрим, что ушло бы на
сервер: сколько полей audio*, сколько в них потоков (заголовков), сколько
секунд звука, и что прочёл студент в подсказке.

  double  - «Записать» нажато дважды подряд (микрофон выдаётся не сразу).
            Раньше второй диктофон дописывал куски во все следующие записи:
            склейка двух потоков / bad_audio. Ждём: 1 поток в обеих записях.
  pause   - пауза, потом «Стоп». Раньше «Стоп» на паузе молчал.
  resume  - запись оборвалась (панель закрыли посреди чтения), открыли
            снова, «Продолжить», дочитали. Раньше «не целиком» (Азиля).

    python scripts/check_rec_audit.py            # рабочая копия
    python scripts/check_rec_audit.py --old      # HEAD - для сравнения
"""
import argparse
import base64
import json
import pathlib
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_rec_redo as redo               # noqa: E402
import shoot_onboarding as stand            # noqa: E402
import core.db as db                        # noqa: E402
import core.mufradat_bot as mb              # noqa: E402
from aiohttp import web                     # noqa: E402

PORT = 8809

JS = """
<script>
(function () {
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var $ = function (id) { return document.getElementById(id); };
  var hint = function () { return ($('hifz-rec-hint') || {}).textContent || ''; };
  window.__sent = []; window.__log = [];
  var realFetch = window.fetch;
  window.fetch = function (url, opts) {
    if (String(url).indexOf('/revision/submit') >= 0) {
      var out = [], jobs = [];
      opts.body.forEach(function (v, k) {
        if (k.indexOf('audio') !== 0) return;
        jobs.push(v.arrayBuffer().then(function (buf) {
          var b = new Uint8Array(buf), s = '';
          for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
          out.push({ name: k, b64: btoa(s) });
        }));
      });
      Promise.all(jobs).then(function () { window.__sent.push(out); });
      return Promise.resolve(new Response(JSON.stringify({ ok: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return realFetch.apply(window, arguments);
  };
  var send = async function (label) {
    var n = window.__sent.length;
    $('hifz-rec-send') ? $('hifz-rec-send').click() : null;
    await wait(2500);
    window.__log.push(label + ': ' + (window.__sent.length > n ? 'ушло' : 'НЕ ушло') + ' | ' + hint());
  };
  var sc = new URLSearchParams(location.search).get('sc');
  window.addEventListener('load', function () {
    (async function () {
      await wait(1200);
      $('dash-mushaf').click(); await wait(1500);
      $('btn-revision').click(); await wait(1500);
      if (sc === 'double') {
        $('hifz-rec-go').click(); $('hifz-rec-go').click();
        await wait(6000);
        $('hifz-rec-stop').click(); await wait(1500);
        await send('первая (6 с)');
        $('btn-revision').click(); await wait(1500);
        $('hifz-rec-go').click(); await wait(5000);
        $('hifz-rec-stop').click(); await wait(1500);
        await send('вторая (5 с)');
      } else if (sc === 'pause') {
        $('hifz-rec-go').click(); await wait(4000);
        $('hifz-rec-pause').click(); await wait(1000);
        $('hifz-rec-stop').click(); await wait(1500);
        await send('4 с, пауза, стоп');
      } else if (sc === 'resume') {
        $('hifz-rec-go').click(); await wait(12000);
        $('hifz-rec-close').click(); await wait(1500);        // оборвалось
        $('btn-revision').click(); await wait(2000);
        window.__log.push('после обрыва: ' + hint());
        $('hifz-rec-continue').click(); await wait(6000);
        $('hifz-rec-stop').click(); await wait(1500);
        await send('продолжение (~10 + 6 с)');
      }
      window.__done = true;
    })();
  });
})();
</script>
"""


def run(sc, old):
    html = redo.page_html(old) + JS
    app = stand.build_app()

    async def page(request):
        stand.set_state("default")
        db.set_student_birth_year(stand.STUDENT, 2015)   # ребёнок: повторение записью
        return web.Response(text=html, content_type="text/html")

    app.router.add_get("/v", page)
    port = PORT + ["double", "pause", "resume"].index(sc)
    threading.Thread(target=lambda: web.run_app(app, host="127.0.0.1", port=port, print=None,
                                                handle_signals=False), daemon=True).start()
    time.sleep(3)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--use-fake-device-for-media-stream",
                                           "--use-fake-ui-for-media-stream"])
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, permissions=["microphone"])
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("http://127.0.0.1:%d/v?bot=male&sc=%s" % (port, sc))
        pg.wait_for_function("window.__done", timeout=120000)
        sent, log = pg.evaluate("[window.__sent, window.__log]")
        browser.close()

    print("== %s" % sc)
    for line in log:
        print("  ", line)
    for i, parts in enumerate(sent):
        desc = []
        for part in sorted(parts, key=lambda p: p["name"]):
            data = base64.b64decode(part["b64"])
            desc.append("%s: потоков %d, %.1f с" % (part["name"], mb.stream_heads(data),
                                                     redo.decoded_seconds(data)))
        print("   отправка %d: %s" % (i + 1, "; ".join(desc)))
    if errors:
        print("   ОШИБКИ страницы:", "; ".join(errors[:3]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", action="store_true")
    ap.add_argument("--sc", choices=["double", "pause", "resume"])
    a = ap.parse_args()
    print("версия:", "HEAD (до правки)" if a.old else "рабочая копия")
    for sc in ([a.sc] if a.sc else ["double", "pause", "resume"]):
        run(sc, a.old)


if __name__ == "__main__":
    main()
