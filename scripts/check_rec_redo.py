"""«Перезаписать» не должен тащить прежние попытки в отправку (21.09.2026).

Живой случай: пользователь дважды начал сдачу, дважды нажал «Перезаписать»,
третий раз прочитал целиком - и устаз услышал начало трижды. Куски прежних
попыток лежали на телефоне (IndexedDB) и уходили вместе с новой одним файлом.

Проверка на ЖИВОМ приложении (фальшивый микрофон Chrome): три записи с
«Перезаписать» между ними, отправка перехвачена - смотрим, что ушло: сколько
полей audio*, сколько в них потоков (заголовков), сколько секунд звука.

    python scripts/check_rec_redo.py          # текущий index.html
    python scripts/check_rec_redo.py --old    # версия из HEAD - для сравнения
"""
import argparse
import base64
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import shoot_onboarding as stand            # noqa: E402
import core.db as db                        # noqa: E402
import core.mufradat_bot as mb              # noqa: E402
from aiohttp import web                     # noqa: E402

PORT = 8808

# Три попытки: две короткие (как «начал и передумал») и последняя.
ATTEMPTS_MS = (6000, 6000, 9000)

JS = """
<script>
(function () {
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var $ = function (id) { return document.getElementById(id); };
  var realFetch = window.fetch;
  window.fetch = function (url, opts) {
    if (String(url).indexOf('/revision/submit') >= 0) {
      var out = [];
      var jobs = [];
      opts.body.forEach(function (v, k) {
        if (k.indexOf('audio') !== 0) return;
        jobs.push(v.arrayBuffer().then(function (buf) {
          var b = new Uint8Array(buf), s = '';
          for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
          out.push({ name: k, b64: btoa(s) });
        }));
      });
      Promise.all(jobs).then(function () { window.__sent = out; });
      return Promise.resolve(new Response(JSON.stringify({ ok: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return realFetch.apply(window, arguments);
  };
  window.addEventListener('load', function () {
    (async function () {
      await wait(1200);
      $('dash-mushaf').click(); await wait(1500);
      $('btn-revision').click(); await wait(1500);
      var tries = %s;
      for (var i = 0; i < tries.length; i++) {
        if (i) { $('hifz-rec-again').click(); await wait(800); }
        $('hifz-rec-go').click(); await wait(tries[i]);
        $('hifz-rec-stop').click(); await wait(1500);
      }
      $('hifz-rec-send').click();
    })();
  });
})();
</script>
""" % json.dumps(list(ATTEMPTS_MS))


def page_html(old):
    if not old:
        return stand.dev_index()
    src = subprocess.run(["git", "show", "HEAD:mushaf_data/index.html"], cwd=ROOT,
                         capture_output=True, check=True).stdout.decode("utf-8")
    # dev_index читает ROOT/mushaf_data/index.html - даём ему временный ROOT,
    # настоящий файл не трогаем (в репо может работать другая сессия).
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="rec-old-"))
    (tmp / "mushaf_data").mkdir()
    (tmp / "mushaf_data" / "index.html").write_text(src, encoding="utf-8", newline="")
    real_root, stand.ROOT = stand.ROOT, tmp
    try:
        return stand.dev_index()
    finally:
        stand.ROOT = real_root


def decoded_seconds(data):
    with tempfile.NamedTemporaryFile(suffix=".rec", delete=False) as f:
        f.write(data)
    out = subprocess.run(["ffmpeg", "-v", "quiet", "-i", f.name, "-ac", "1", "-ar", "8000",
                          "-f", "s16le", "pipe:1"], capture_output=True).stdout
    pathlib.Path(f.name).unlink()
    return len(out) / 16000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", action="store_true")
    args = ap.parse_args()

    html = page_html(args.old) + JS
    app = stand.build_app()

    async def page(request):
        stand.set_state("default")
        db.set_student_birth_year(stand.STUDENT, 2015)   # ребёнок: повторение записью
        return web.Response(text=html, content_type="text/html")

    app.router.add_get("/v", page)
    threading.Thread(target=lambda: web.run_app(app, host="127.0.0.1", port=PORT, print=None,
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
        pg.goto("http://127.0.0.1:%d/v?bot=male" % PORT)
        pg.wait_for_function("window.__sent", timeout=90000)
        sent = pg.evaluate("window.__sent")
        browser.close()

    print("версия:", "HEAD (до правки)" if args.old else "рабочая копия")
    print("попытки:", ", ".join("%d с" % (m // 1000) for m in ATTEMPTS_MS))
    total = 0.0
    for part in sorted(sent, key=lambda p: p["name"]):
        data = base64.b64decode(part["b64"])
        sec = decoded_seconds(data)
        total += sec
        print("  %-7s %7d байт  потоков %d  звука %.1f с"
              % (part["name"], len(data), mb.stream_heads(data), sec))
    print("итого звука: %.1f с (последняя попытка %.1f с)" % (total, ATTEMPTS_MS[-1] / 1000))
    if errors:
        print("ОШИБКИ страницы:", "; ".join(errors[:3]))


if __name__ == "__main__":
    main()
