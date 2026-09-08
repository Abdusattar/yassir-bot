"""Снимки экранов для раздела «Как учимся» (mushaf_data/onboarding/*.jpg).

Зачем скрипт, а не папка с картинками: снимки должны стареть вместе с
интерфейсом. Здесь поднимается ЛОКАЛЬНАЯ копия приложения (своя пустая база,
свой hadiths.db, подменённая авторизация) и сцены кликают по НАСТОЯЩИМ
кнопкам — переименуют кнопку, съёмка упадёт, а не соврёт молча.

    python scripts/shoot_onboarding.py            # снять всё и обновить jpg
    python scripts/shoot_onboarding.py --serve    # только поднять стенд

Живой аккаунт для этого не годится: часть шагов доходит до отправки записи,
а она ушла бы устазу в группу. Здесь всё уходит в пустоту временной базы.

Телефонная ширина берётся через iframe (/frame): headless Chrome сам держит
layout-viewport шире окна (см. wiki/hifz_audio_husary.md, «визуальное — только
скриншотом»), и без рамки снимок получается обрезанным по правому краю.
"""
import argparse
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("TELEGRAM_TOKEN", "dev")
os.environ.setdefault("SUPER_ADMIN_IDS", "")

import core.db as db                      # noqa: E402
import core.sampler as sampler            # noqa: E402
import core.mushaf_words as mushaf_words  # noqa: E402

TMP = pathlib.Path(tempfile.gettempdir()) / "yassir_onboarding_stand"
TMP.mkdir(exist_ok=True)
db.DB = str(TMP / "dev.db")
sampler.HADITHS_DB = str(TMP / "hadiths.db")
mushaf_words.HADITHS_DB = str(TMP / "hadiths.db")

import core.mufradat_api as api           # noqa: E402
api.validate_init_data = lambda raw, token: {"id": raw}
api.SUPER_ADMIN_IDS = []

from aiohttp import web                   # noqa: E402

PORT = 8799
STUDENT = "777001"
CHAT = "-100999001"
SHOTS = ROOT / "mushaf_data" / "onboarding"
SHOT_WIDTH = 520          # ширина итогового jpg; на экране он ~300 CSS-пикселей
# 72 давало ~800 КБ на набор: лист Аль-Бакары плотнее Фатихи, и вес вырос
# вдвое. Студенты сидят на мобильном интернете - держим набор в ~500 КБ.
SHOT_QUALITY = 65

# Сцена -> имя файла. Порядок тот же, что в LEARN (mushaf_data/index.html).
SCENES = ["dash", "mushaf", "pick", "pointer", "big", "rec", "progress", "subs", "look",
          "read", "bookmark", "revision", "revision_ask"]

CHROME_CANDIDATES = [
    os.environ.get("CHROME"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]


def find_chrome():
    for path in CHROME_CANDIDATES:
        if path and pathlib.Path(path).exists():
            return path
    found = shutil.which("google-chrome") or shutil.which("chromium")
    if found:
        return found
    raise SystemExit("Chrome не найден — укажи путь в переменной CHROME")


# ─── данные стенда ────────────────────────────────────────────────────────

def seed():
    db.init()
    if not db.get_group(CHAT):
        db.save_group(CHAT, "N-1", tasks="m,r,t")
    group = db.get_group(CHAT)
    if not db.find_user_by_phone(STUDENT):
        db.add_student("Абдулла", group["id"], phone=STUDENT)
    return group


def seed_submissions():
    """Одна сдача принята с пометками, одна ждёт устаза, одна возвращена на
    пересдачу — три состояния, которые студент видит в «Работе с устазом»."""
    group = db.get_group(CHAT)
    user = db.find_user_by_phone(STUDENT)
    if db.get_student_submissions(user["id"]):
        return
    today = db.get_date()
    rows = [
        (101, 3, 1, 1, db.VERDICT_ACCEPTED, [{"line": 1, "word": 3}, {"line": 1, "word": 7}]),
        (102, 3, 2, 1, db.VERDICT_RETAKE, [{"line": 2, "word": 4}]),
        (103, 3, 3, 1, None, None),
    ]
    for msg_id, page, line, stage, verdict, words in rows:
        db.save_voice_submission(user["id"], group["id"], CHAT, msg_id, today,
                                 file_id="dev%d" % msg_id,
                                 hifz_page=page, hifz_line=line, hifz_stage=stage)
        if verdict:
            db.save_submission_review(CHAT, msg_id, "voice",
                                      review_file_id="rev%d" % msg_id,
                                      review_by="888002")
            sub = [r for r in db.get_student_submissions(user["id"])
                   if r["hifz_line"] == line][0]
            db.set_submission_verdict(sub["id"], verdict, "888002", words)


def set_state(mode):
    """Сцены конфликтуют по состоянию: «первый вход» требует пустого
    указателя, панель повторов — этапа 2 с накопленными повторами. Поэтому
    состояние ставится явно перед каждой сценой, а не копится от прошлой."""
    with sqlite3.connect(str(TMP / "hadiths.db")) as conn:
        conn.execute(mushaf_words._HIFZ_SCHEMA)
        conn.execute("DELETE FROM mushaf_hifz_pointer WHERE user_id=?", (STUDENT,))
    if mode == "stage2":
        mushaf_words.set_hifz_pointer(STUDENT, 3, 0, 2)
        if mushaf_words.get_hifz_progress(STUDENT, 3, 2, 0) == 0:
            mushaf_words.add_hifz_progress(STUDENT, 3, 2, 0, 24)


# ─── страница стенда ──────────────────────────────────────────────────────

TELEGRAM_STUB = (
    "<script>window.Telegram={WebApp:{initData:'%s',"
    "initDataUnsafe:{user:{id:%s,first_name:'Абдулла'}},"
    "colorScheme:'light',themeParams:{},"
    "ready:function(){},expand:function(){},close:function(){},"
    "onEvent:function(){},offEvent:function(){},"
    "HapticFeedback:{impactOccurred:function(){},notificationOccurred:function(){},"
    "selectionChanged:function(){}},"
    "MainButton:{show:function(){},hide:function(){},setText:function(){},"
    "onClick:function(){},offClick:function(){}},"
    "BackButton:{show:function(){},hide:function(){},onClick:function(){},"
    "offClick:function(){}}}};</script>" % (STUDENT, STUDENT)
)

SCENE_SCRIPT = """
<style>
  /* Подсветка: обводка плюс затемнение всего остального — «нажимать сюда»
     должно читаться без стрелок и подписей. */
  .onb-spot {
    outline: 3px solid #e8863a !important;
    outline-offset: 3px;
    border-radius: 12px;
    box-shadow: 0 0 0 9999px rgba(20, 16, 8, .34) !important;
    position: relative; z-index: 9999;
  }
</style>
<script>
(function () {
  var scene = new URLSearchParams(location.search).get('scene');
  if (!scene) return;
  var $ = function (id) { return document.getElementById(id); };
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var spot = function (sel) {
    var el = document.querySelector(sel);
    if (el) el.classList.add('onb-spot');
  };
  var state = function (mode) { return fetch('/dev/state?mode=' + mode).then(function (r) { return r.json(); }); };
  var line = function (i) { return document.querySelectorAll('#ayah-text .mushaf-line')[i]; };

  // Мусхаф открывается на Фатихе, а её лист короткий - половина снимка
  // выходит пустой, и всё важное на нём мелкое. Уходим на полный лист
  // Аль-Бакары: там страница заполнена, как у настоящего студента.
  var goFullPage = async function () {
    $('btn-go-baqara').click(); await wait(1400);      // стр. 2, начало Бакары
    $('btn-prev').click(); await wait(1300);           // стр. 3 - лист целиком
  };

  var scenes = {
    dash: async function () { spot('#dash-mushaf'); },

    mushaf: async function () {
      await state('fresh');
      $('dash-mushaf').click(); await wait(1500);
      await goFullPage(); spot('#btn-hifz');
    },

    pick: async function () {
      await state('fresh');
      $('dash-mushaf').click(); await wait(1500);
      await goFullPage();
      $('btn-hifz').click(); await wait(900);
    },

    pointer: async function () {
      await state('fresh');
      $('dash-mushaf').click(); await wait(1500);
      await goFullPage();
      $('btn-hifz').click(); await wait(900);
      line(1).click(); await wait(900);
      spot('#hifz-foot');
    },

    big: async function () {
      await state('fresh');
      $('dash-mushaf').click(); await wait(1500);
      await goFullPage();
      $('btn-hifz').click(); await wait(900);
      line(1).click(); await wait(700);
      $('hifz-big-btn').click(); await wait(900);
    },

    rec: async function () {
      await state('fresh');
      $('dash-mushaf').click(); await wait(1500);
      await goFullPage();
      $('btn-hifz').click(); await wait(900);
      line(1).click(); await wait(700);
      $('hifz-submit').click(); await wait(900);
    },

    // Панель повторов открывается после отправки записи, а записать в
    // headless нечем — открываем ту же панель на подготовленном этапе 2.
    progress: async function () {
      await state('stage2');
      $('dash-mushaf').click(); await wait(1500);
      await goFullPage();
      $('btn-hifz').click(); await wait(1000);
      $('hifz-submit').click(); await wait(700);
      $('hifz-rec-actions').style.display = 'none';
      $('hifz-progress').style.display = 'block';
      var r = await fetch('/api/muf/hifz/progress?page=3&stage=2&half=0',
                          { headers: { 'X-Telegram-Init-Data': '%s' } }).then(function (x) { return x.json(); });
      $('hifz-progress-count').textContent = r.count || 0;
      spot('#hifz-progress-chips');
    },

    subs: async function () { $('dash-subs').click(); await wait(1800); },

    // --- повторение ---
    // Повторение идёт с начала Аль-Бакары - показываем её начало, а не
    // Фатиху, на которой мусхаф открывается по умолчанию.
    read: async function () {
      $('dash-mushaf').click(); await wait(1600);
      $('btn-go-baqara').click(); await wait(1400);
    },

    bookmark: async function () {
      $('dash-mushaf').click(); await wait(1600);
      await goFullPage();
      spot('#btn-bookmark-save');
    },

    revision: async function () {
      $('dash-mushaf').click(); await wait(1600);
      await goFullPage();
      spot('#btn-revision');
    },

    revision_ask: async function () {
      $('dash-mushaf').click(); await wait(1600);
      await goFullPage();
      $('btn-revision').click(); await wait(800);
    },

    look: async function () {
      $('dash-subs').click(); await wait(1800);
      var b = document.querySelector('[data-look]');
      if (b) { b.click(); await wait(1600); }
    },

    learn: async function () { $('dash-learn').click(); await wait(800); },

    learn_step1: async function () {
      $('dash-learn').click(); await wait(800);
      document.querySelector('[data-sec="0"]').click(); await wait(1200);
    },

    learn_revision: async function () {
      $('dash-learn').click(); await wait(800);
      document.querySelector('[data-sec="2"]').click(); await wait(1200);
    },

    learn_step: async function () {
      $('dash-learn').click(); await wait(800);
      document.querySelector('[data-sec="0"]').click(); await wait(900);
      $('learn-next').click(); await wait(500);
      $('learn-next').click(); await wait(700);
    }
  };

  var run = function () {
    var fn = scenes[scene];
    if (!fn) throw new Error('нет такой сцены: ' + scene);
    fn();
  };
  if (document.readyState === 'complete') setTimeout(run, 900);
  else window.addEventListener('load', function () { setTimeout(run, 900); });
})();
</script>
""" % STUDENT


def dev_index():
    html = (ROOT / "mushaf_data" / "index.html").read_text(encoding="utf-8")
    tag = '<script src="https://telegram.org/js/telegram-web-app.js"></script>'
    assert tag in html, "SDK Telegram больше не подключается так — поправь заглушку"
    html = html.replace(tag, TELEGRAM_STUB, 1)
    api_base = "return '/api/muf/' + profile;"
    assert api_base in html, "apiBase() изменился — стенду нужен путь без профиля"
    html = html.replace(api_base, "return '/api/muf';", 1)
    return html + SCENE_SCRIPT


def build_app():
    seed()
    seed_submissions()
    app = api.build_app()
    index_html = dev_index()

    async def index(request):
        return web.Response(text=index_html, content_type="text/html")

    async def state(request):
        set_state(request.query.get("mode", "fresh"))
        return web.json_response({"ok": True})

    async def frame(request):
        w = request.query.get("w", "390")
        h = request.query.get("h", "844")
        src = "/?bot=male"
        if request.query.get("scene"):
            src += "&scene=" + request.query["scene"]
        return web.Response(content_type="text/html", text=(
            "<style>html,body{margin:0;background:#fff}"
            "iframe{border:0;display:block;width:%spx;height:%spx}</style>"
            "<iframe src='%s'></iframe>" % (w, h, src)))

    app.router.add_get("/dev/state", state)
    app.router.add_get("/frame", frame)
    app.router.add_get("/", index)
    app.router.add_static("/", str(ROOT / "mushaf_data"), show_index=False)
    return app


# ─── съёмка ───────────────────────────────────────────────────────────────

def shoot(chrome, out_dir):
    from PIL import Image

    SHOTS.mkdir(exist_ok=True)
    total = 0
    for scene in SCENES:
        png = out_dir / ("%s.png" % scene)
        subprocess.run([
            chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--window-size=390,844", "--virtual-time-budget=17000",
            "--screenshot=%s" % png,
            "http://127.0.0.1:%d/frame?w=390&h=844&scene=%s" % (PORT, scene),
        ], check=True, capture_output=True)
        if not png.exists():
            raise SystemExit("сцена %s не снялась" % scene)
        im = Image.open(png).convert("RGB")
        im = im.resize((SHOT_WIDTH, int(im.height * SHOT_WIDTH / im.width)), Image.LANCZOS)
        jpg = SHOTS / ("%s.jpg" % scene)
        im.save(jpg, "JPEG", quality=SHOT_QUALITY, optimize=True, progressive=True)
        total += jpg.stat().st_size
        print("  %-9s %4d КБ" % (scene, jpg.stat().st_size // 1024))
    print("итого %d КБ в %s" % (total // 1024, SHOTS))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true",
                        help="только поднять стенд (открывать /frame?scene=...)")
    args = parser.parse_args()

    app = build_app()
    if args.serve:
        print("стенд: http://127.0.0.1:%d/frame?w=390&h=844&scene=dash" % PORT)
        web.run_app(app, host="127.0.0.1", port=PORT, print=None)
        return

    chrome = find_chrome()
    runner = threading.Thread(
        target=lambda: web.run_app(app, host="127.0.0.1", port=PORT, print=None,
                                   handle_signals=False),
        daemon=True)
    runner.start()
    time.sleep(3)
    with tempfile.TemporaryDirectory() as tmp:
        shoot(chrome, pathlib.Path(tmp))


if __name__ == "__main__":
    main()
