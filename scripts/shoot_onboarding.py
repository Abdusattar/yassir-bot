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

# Тренажёру нужен словарь (mufradat_words) - на пустой базе вопрос не
# соберётся. Берём КОПИЮ рабочей sources/hadiths.db: прогресс тестового
# студента пишется в копию и живой базы не касается.
_REAL_WORDS = ROOT / "sources" / "hadiths.db"
_STAND_WORDS = TMP / "hadiths.db"
if _REAL_WORDS.exists() and not _STAND_WORDS.exists():
    shutil.copy2(_REAL_WORDS, _STAND_WORDS)
db.DB = str(TMP / "dev.db")
sampler.HADITHS_DB = str(TMP / "hadiths.db")
mushaf_words.HADITHS_DB = str(TMP / "hadiths.db")

import core.mufradat_api as api           # noqa: E402
api.validate_init_data = lambda raw, token: {"id": raw}
api.SUPER_ADMIN_IDS = []

from aiohttp import web                   # noqa: E402

PORT = 8799
STUDENT = "777001"
# Тот же id, которым проставлены вердикты в seed_submissions: устаз должен
# видеть в «Проверено» СВОЙ разбор, а не чужой.
USTAZ = "888002"
CHAT = "-100999001"
# Вторая группа того же устаза: в кабинете должны быть видны вкладки групп -
# у Умара устаза их четыре, и «где переключить группу» это первый вопрос.
CHAT2 = "-100999002"
SHOTS = ROOT / "mushaf_data" / "onboarding"
SHOT_WIDTH = 520          # ширина итогового jpg; на экране он ~300 CSS-пикселей
# 72 давало ~800 КБ на набор: лист Аль-Бакары плотнее Фатихи, и вес вырос
# вдвое. Студенты сидят на мобильном интернете - держим набор в ~500 КБ.
SHOT_QUALITY = 65

# Сцена -> имя файла. Порядок тот же, что в LEARN (mushaf_data/index.html).
# Сцены на "u_" снимаются под аккаунтом устаза (см. USTAZ и /frame?as=ustaz):
# у студента этих экранов нет вообще.
SCENES = ["dash", "mushaf", "pick", "pointer", "big", "rec", "progress", "subs", "look",
          "read", "bookmark", "revision", "revision_ask",
          "trainer_start", "trainer_q", "trainer_daily", "trainer_range", "trainer_answer",
          "word_tap", "word_add", "mywords",
          "u_door", "u_queue", "u_open", "u_marks", "u_comment", "u_verdict",
          "u_done", "u_students"]

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
    if not db.get_group(CHAT2):
        db.save_group(CHAT2, "N-2a", tasks="m,r,t")
    group2 = db.get_group(CHAT2)
    for name, phone, grp in (("Хамза", "777002", group), ("Ибрахим", "777003", group),
                             ("Юсуф", "777004", group2), ("Билял", "777005", group2)):
        if not db.find_user_by_phone(phone):
            db.add_student(name, grp["id"], phone=phone)
    # Устаз этих групп - под ним снимаются сцены "u_*". Имя нужно:
    # в зоне «Проверено» стоит подпись «разобрал ...».
    if not db.find_user_by_phone(USTAZ):
        db.add_group_admin(group["id"], USTAZ)
        db.add_group_admin(group2["id"], USTAZ)
        with sqlite3.connect(db.DB) as conn:
            conn.execute("UPDATE users SET name='Устаз' WHERE phone=?", (USTAZ,))
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
                                      review_by=USTAZ)
            sub = [r for r in db.get_student_submissions(user["id"])
                   if r["hifz_line"] == line][0]
            db.set_submission_verdict(sub["id"], verdict, USTAZ, words)
    # Ещё две сдачи в очередь - у устаза она никогда не из одной строки, а
    # своя группа должна открываться первой (ustazDefaultGroup: где больше ждут).
    for phone, chat, msg_id, page, line, stage in (
            ("777002", CHAT, 111, 4, 0, 1),
            ("777004", CHAT2, 112, 5, 0, 2)):
        other = db.find_user_by_phone(phone)
        if other and not db.get_student_submissions(other["id"]):
            db.save_voice_submission(other["id"], db.get_group(chat)["id"], chat,
                                     msg_id, today, file_id="dev%d" % msg_id,
                                     hifz_page=page, hifz_line=line, hifz_stage=stage)


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
    if mode == "trainer_fresh":
        # Первый вход в тренажёр: закладки нет, приложение спрашивает
        # страницу. Без сброса сцена сняла бы обычный вопрос.
        with sqlite3.connect(str(TMP / "hadiths.db")) as conn:
            conn.execute("DELETE FROM mufradat_page WHERE user_id=?", (STUDENT,))
    if mode == "words":
        # Тренажёр без закладки просит выбрать страницу - для сцены с
        # вопросом её надо поставить заранее.
        from core.mufradat import set_current_page
        set_current_page(STUDENT, 3)


# ─── страница стенда ──────────────────────────────────────────────────────

TELEGRAM_STUB = (
    "<script>window.Telegram={WebApp:{initData:'%s',"
    "initDataUnsafe:{user:{id:%s,first_name:'%s'}},"
    "colorScheme:'light',themeParams:{},"
    "ready:function(){},expand:function(){},close:function(){},"
    "onEvent:function(){},offEvent:function(){},"
    "HapticFeedback:{impactOccurred:function(){},notificationOccurred:function(){},"
    "selectionChanged:function(){}},"
    "MainButton:{show:function(){},hide:function(){},setText:function(){},"
    "onClick:function(){},offClick:function(){}},"
    "BackButton:{show:function(){},hide:function(){},onClick:function(){},"
    "offClick:function(){}}}};</script>"
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

  // Единственная ждущая сдача стенда (стр. 3, строчка 3) - через неё
  // снимается весь разбор.
  var openWaiting = async function () {
    $('dash-ustaz').click(); await wait(1900);
    // Именно сдача Абдуллы (стр. 3, строчка 4): пометки ниже ставятся в его
    // строку, а не в соседнюю - устаз отмечает то место, что слушает.
    var row = Array.prototype.filter.call(
      document.querySelectorAll('[data-review]'),
      function (el) { return el.textContent.indexOf('Абдулла') >= 0; })[0];
    if (!row) throw new Error('сдача Абдуллы не в очереди - проверь seed_submissions');
    row.click(); await wait(2200);
  };

  // Тап по слову в режиме проверки = пометка ошибки (см. showWordPopup).
  var markWord = function (ln, idx) {
    var row = document.querySelector('#ayah-text .mushaf-line[data-line="' + ln + '"]');
    if (!row || !row.children[idx]) throw new Error('нет слова ' + ln + ':' + idx);
    row.children[idx].click();
  };

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

    // --- слова и тренажёр ---
    trainer_start: async function () {
      await state('trainer_fresh');
      $('dash-trainer').click(); await wait(1800);
    },

    trainer_q: async function () {
      await state('words');
      $('dash-trainer').click(); await wait(2200);
    },

    trainer_daily: async function () {
      await state('words');
      $('dash-trainer').click(); await wait(2200);
      spot('#trainer-daily');
    },

    trainer_range: async function () {
      await state('words');
      $('dash-trainer').click(); await wait(2200);
      spot('.trainer-pagebar');       // ➖ ➕ - шаг закладки на страницу
    },

    trainer_answer: async function () {
      await state('words');
      $('dash-trainer').click(); await wait(2200);
      var opt = document.querySelector('#trainer-body button');
      if (opt) { opt.click(); await wait(1400); }
    },

    mywords: async function () {
      $('dash-trainer').click(); await wait(1600);
      $('trainer-tab-mywords').click(); await wait(1600);
    },

    // Попап перевода живёт 1800 мс, а headless прокручивает таймеры
    // (--virtual-time-budget) - к моменту снимка он уже спрятан. Держим его
    // видимым принудительно: сам попап настоящий, гасится только таймер.
    word_tap: async function () {
      $('dash-mushaf').click(); await wait(1600);
      await goFullPage();
      var w = document.querySelectorAll('#ayah-text [data-tr]')[5];
      w.click();
      setInterval(function () { $('word-popup').classList.add('visible'); }, 30);
      await wait(900);
    },

    word_add: async function () {
      $('dash-mushaf').click(); await wait(1600);
      await goFullPage();
      var w = document.querySelectorAll('#ayah-text [data-tr]')[5];
      w.click(); await wait(80); w.click();
      setInterval(function () { $('word-popup').classList.add('visible'); }, 30);
      await wait(1200);
    },

    // --- кабинет устаза (снимается под другим аккаунтом) ---
    u_door: async function () { spot('#dash-ustaz'); },

    u_queue: async function () { $('dash-ustaz').click(); await wait(1900); },

    u_open: async function () { await openWaiting(); spot('#review-play'); },

    u_marks: async function () {
      await openWaiting();
      markWord(3, 2); markWord(3, 6);
      await wait(500);
    },

    u_comment: async function () { await openWaiting(); spot('#review-comment'); },

    u_verdict: async function () {
      await openWaiting();
      markWord(3, 2);
      spot('#review-foot .row:last-child');
      await wait(400);
    },

    u_done: async function () {
      $('dash-ustaz').click(); await wait(1900);
      document.querySelector('.ustaz-zones [data-zone="done"]').click(); await wait(1700);
    },

    u_students: async function () {
      $('dash-ustaz').click(); await wait(1900);
      document.querySelector('.ustaz-zones [data-zone="students"]').click(); await wait(2000);
    },

    learn: async function () { $('dash-learn').click(); await wait(800); },

    learn_step1: async function () {
      $('dash-learn').click(); await wait(800);
      document.querySelector('[data-sec="0"]').click(); await wait(1200);
    },

    learn_revision: async function () {
      $('dash-learn').click(); await wait(800);
      document.querySelector('[data-sec="1"]').click(); await wait(1200);
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


def dev_index(user_id=STUDENT, name="Абдулла"):
    html = (ROOT / "mushaf_data" / "index.html").read_text(encoding="utf-8")
    tag = '<script src="https://telegram.org/js/telegram-web-app.js"></script>'
    assert tag in html, "SDK Telegram больше не подключается так — поправь заглушку"
    html = html.replace(tag, TELEGRAM_STUB % (user_id, user_id, name), 1)
    api_base = "return '/api/muf/' + profile;"
    assert api_base in html, "apiBase() изменился — стенду нужен путь без профиля"
    html = html.replace(api_base, "return '/api/muf';", 1)
    return html + SCENE_SCRIPT


def build_app():
    seed()
    seed_submissions()
    app = api.build_app()
    pages = {"student": dev_index(), "ustaz": dev_index(USTAZ, "Устаз")}

    async def index(request):
        who = "ustaz" if request.query.get("as") == "ustaz" else "student"
        return web.Response(text=pages[who], content_type="text/html")

    async def state(request):
        set_state(request.query.get("mode", "fresh"))
        return web.json_response({"ok": True})

    async def frame(request):
        w = request.query.get("w", "390")
        h = request.query.get("h", "844")
        src = "/?bot=male"
        if request.query.get("scene"):
            src += "&scene=" + request.query["scene"]
        if request.query.get("as"):
            src += "&as=" + request.query["as"]
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

def shoot(chrome, out_dir, only=None):
    from PIL import Image

    SHOTS.mkdir(exist_ok=True)
    total = 0
    for scene in SCENES:
        if only and scene not in only:
            continue
        png = out_dir / ("%s.png" % scene)
        who = "&as=ustaz" if scene.startswith("u_") else ""
        subprocess.run([
            chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--window-size=390,844", "--virtual-time-budget=17000",
            "--screenshot=%s" % png,
            "http://127.0.0.1:%d/frame?w=390&h=844&scene=%s%s" % (PORT, scene, who),
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
    parser.add_argument("--only", default="",
                        help="снять только эти сцены через запятую")
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
    only = [s.strip() for s in args.only.split(",") if s.strip()]
    unknown = [s for s in only if s not in SCENES]
    if unknown:
        raise SystemExit("нет таких сцен: %s" % ", ".join(unknown))
    with tempfile.TemporaryDirectory() as tmp:
        shoot(chrome, pathlib.Path(tmp), only)


if __name__ == "__main__":
    main()
