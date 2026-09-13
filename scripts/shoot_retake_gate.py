"""Макеты стены пересдачи в режиме заучивания (13.09.2026).

Зачем: гейт пересдачи сейчас отбивает сдачу ПОСЛЕ записи и запирает всё,
кроме самого долга. Договорились переносить стену на смену этапа и показывать
её ДО записи. Прежде чем писать код — посмотреть глазами.

Как и у shoot_dash_variants: поднимается тот же стенд (настоящее приложение,
своя база, подменённая авторизация), а поверх НАСТОЯЩЕГО экрана заучивания
накладывается только предлагаемая разметка. Это не отдельный мокап, который
завтра разойдётся с кодом (см. feedback «Сверять мокапы с реальным кодом»).

    python scripts/shoot_retake_gate.py           # снять все варианты
    python scripts/shoot_retake_gate.py --serve   # покрутить руками

Долг на стенде — сдача стр. 3, строка 3, этап 1 (seed_submissions), её устаз
вернул на пересдачу.
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

OUT = ROOT / "logs" / "retake_gate"
PORT = 8802
WIDTH, HEIGHT = 390, 844

# Половина листа стр. 3 — строки 0..6 (15 строк, hifzHalf: line < 15//2).
# Для «хода нет» ставим указатель на ПОСЛЕДНЮЮ строку половины: следующий шаг
# сменил бы этап, а он и есть то, что закрывает долг.
LAST_LINE_OF_HALF = 6
MID_LINE_OF_HALF = 3

DEBT_PLACE = "стр. 3, строка 3"

# ─── предлагаемая разметка ────────────────────────────────────────────────
#
# Пилюля встаёт в ПУСТУЮ середину шапки: #hifz-head это space-between, ✕
# слева, место справа, между ними ничего. Вторую строку в шапку не
# возвращаем — её свели в одну 11.09 по просьбе пользователя.
GATE_CSS = """
#hifz-debt {
  flex: 0 0 auto; display: inline-flex; align-items: center; gap: 5px;
  border: 1px solid var(--no); background: var(--no-soft); color: var(--no);
  border-radius: 999px; padding: 3px 10px;
  font-size: 11.5px; font-weight: 700; line-height: 1.35;
  direction: ltr; cursor: pointer; -webkit-tap-highlight-color: transparent;
}
#hifz-debt.low { padding: 7px 11px; font-size: 12px; border-radius: 9px; }
/* Три заливки на выбор: мягкая (как .sub-pill в «Сдачах»), сплошная и
   точка-маячок. Мягкая на 11 пикселях читается почти белой — ровно то, что
   поймал пользователь. */
#hifz-debt.solid {
  background: var(--no); border-color: var(--no); color: #fff;
}
#hifz-debt.dot::before {
  content: ''; width: 7px; height: 7px; border-radius: 50%;
  background: var(--no); flex: 0 0 auto;
}
#hifz-debt.dot {
  background: var(--card-bg); border-color: var(--card-border); color: var(--ink);
  font-weight: 600;
}
#hifz-submit.wall {
  background: var(--no-soft) !important; border-color: var(--no) !important;
  color: var(--no) !important; font-weight: 700;
}
"""

GATE_JS = """
<script>
(function () {
  var v = new URLSearchParams(location.search).get('v');
  if (!v || v === 'now') return;
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var $ = function (id) { return document.getElementById(id); };

  var PILL = { free: '\\u21ba пересдать', free_low: '\\u21ba пересдать',
               free_solid: '\\u21ba пересдать', free_dot: '\\u21ba пересдать',
               free_text: 'есть пересдача',
               wall_a: '\\u21ba пересдать',
               wall_b: '\\u21ba %P%', wall_c: '\\u21ba пересдать',
               wall_d: '\\u21ba пересдать' };
  var BTN  = { wall_a: '\\u21ba Пересдать: %P%', wall_b: '\\u21ba Пересдать',
               wall_c: '\\u21ba Пересдать', wall_d: '\\u21ba Разбор устаза',
               wall_e: '\\u21ba Разбор устаза' };
  var SUB  = { wall_b: 'дальше \\u2014 после пересдачи',
               debt_sub: 'дальше \u2014 после пересдачи' };
  var RETBTN = { debt_btn: '🎙 Пересдать и идти дальше' };

  window.addEventListener('load', function () {
    (async function () {
      await wait(7400);   // после входа в режим (см. ENTER_JS: ~6.3 сек)
      var head = $('hifz-head');
      if (!head || getComputedStyle(head).display === 'none') return;
      if (PILL[v]) {
        var pill = document.createElement('button');
        pill.id = 'hifz-debt';
        pill.textContent = PILL[v].replace('%P%', window.__PLACE);
        // Низ (free_low) против шапки (free): низ ближе к руке и к моменту
        // «хочу сдать», но там уже четыре элемента. Смотрим, влезает ли.
        if (v === 'free_solid') pill.classList.add('solid');
        if (v === 'free_dot') pill.classList.add('dot');
        if (v === 'free_low') {
          pill.classList.add('low');
          $('hifz-foot').insertBefore(pill, $('hifz-submit'));
        } else {
          head.insertBefore(pill, head.querySelector('.where'));
        }
      }

      if (BTN[v]) {
        var b = $('hifz-submit');
        b.classList.remove('primary');
        b.classList.add('wall');
        b.textContent = BTN[v].replace('%P%', window.__PLACE);
      }
      if (SUB[v]) $('hifz-sub').textContent = SUB[v];
      if (RETBTN[v]) {
        var r = $('look-retake');
        if (r) r.textContent = RETBTN[v];
      }
    })();
  });
})();
</script>
"""

# Панель записи в трёх состояниях. Микрофона в headless нет, поэтому ряд
# кнопок и плеер собираем той же разметкой, что рисует hifzRecButtons, - это
# проверка КОМПОНОВКИ, а не работы записи.
REC_JS = """
<script>
(function () {
  var v = new URLSearchParams(location.search).get('v');
  if (['rec_live', 'rec_done', 'flow_ask', 'flow_go', 'flow_slim'].indexOf(v) < 0) return;
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var $ = function (id) { return document.getElementById(id); };
  var row = function (defs) {
    var box = $('hifz-rec-actions');
    box.innerHTML = '';
    defs.forEach(function (d) {
      var b = document.createElement('button');
      b.id = d[0]; b.textContent = d[1];
      if (d[2]) b.className = d[2];
      box.appendChild(b);
    });
  };
  window.addEventListener('load', function () {
    (async function () {
      await wait(7400);
      $('hifz-submit').click();
      await wait(900);
      // flow_ask — что человек видит СЕЙЧАС сразу после тапа по «Сдать»:
      // настоящая шторка, ничего не подставляем.
      if (v === 'flow_ask') return;
      /* flow_slim — предложение: шаг «Записать» остаётся, но с него убран
         мёртвый таймер. Ноль на нём не значит ничего: время появляется только
         когда запись пошла. Шторка становится ниже, листа видно больше. */
      if (v === 'flow_slim') {
        $('hifz-rec-timer').style.display = 'none';
        return;
      }
      // flow_go — предложение: шторка открывается уже пишущей. Три секунды на
      // таймере, потому что ноль в этом варианте человек не увидит никогда.
      if (v === 'flow_go') {
        $('hifz-rec-timer').style.display = '';
        $('hifz-rec-timer').textContent = '0:03';
        $('hifz-rec-timer').classList.add('rec');
        $('hifz-rec-hint').textContent = 'Идёт запись — нажми «Стоп», когда закончишь';
        row([['hifz-rec-pause', 'Пауза', ''], ['hifz-rec-stop', 'Стоп', 'stop']]);
        return;
      }
      if (v === 'rec_live') {
        $('hifz-rec-timer').style.display = '';
        $('hifz-rec-timer').textContent = '1:12';
        $('hifz-rec-timer').classList.add('rec');
        $('hifz-rec-hint').textContent = 'Идёт запись — нажми «Стоп», когда закончишь';
        row([['hifz-rec-pause', 'Пауза', ''], ['hifz-rec-stop', 'Стоп', 'stop']]);
      } else {
        $('hifz-rec-timer').style.display = '';
        $('hifz-rec-timer').textContent = '1:12';
        $('hifz-rec-hint').textContent = 'Послушай себя. Всё хорошо — отправляй устазу';
        // Свой плеер (13.09) вместо системной полосы: показываем его и
        // подставляем длительность, звука в headless всё равно нет.
        $('hifz-rec-player').style.display = 'flex';
        $('hifz-rec-total').textContent = '1:12';
        $('hifz-rec-fill').style.width = '38%';
        $('hifz-rec-cur').textContent = '0:27';
        row([['hifz-rec-again', 'Перезаписать', ''],
             ['hifz-rec-send', 'Отправить', 'primary']]);
      }
    })();
  });
})();
</script>
"""

# «Как сейчас»: отказ приходит ответом сервера уже ПОСЛЕ записи, в подсказку
# шторки. Кнопки в этот момент в состоянии «готово» (переслушать/записать
# заново/отправить) — их рисует hifzRecButtons, снаружи не позвать, поэтому
# панель снимаем открытой, а текст отказа ставим настоящий.
NOW_BLOCK_JS = """
<script>
(function () {
  if (new URLSearchParams(location.search).get('v') !== 'now_block') return;
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  window.addEventListener('load', function () {
    (async function () {
      await wait(7400);   // после входа в режим (см. ENTER_JS)
      document.getElementById('hifz-submit').click();
      await wait(900);
      document.getElementById('hifz-rec-hint').textContent =
        'Сначала пересдай: ' + window.__PLACE;
      document.getElementById('hifz-rec-hint').style.color = 'var(--no)';
    })();
  });
})();
</script>
"""

# Починка «Моего дня» при длинных наборах - две ветки на выбор.
DAY_FIX = """
<style>
/* Счёт «0 из 6» не должен переноситься: он ломается на «0 из» и «6», и от
   этого растёт вся полоса. */
#dash-head #my-day .cap b { white-space: nowrap; }
</style>
<script>
(function () {
  var v = new URLSearchParams(location.search).get('v');
  if (v !== 'day6_a' && v !== 'day6_b') return;
  var st = document.createElement('style');
  st.textContent = v === 'day6_a'
    ? '#dash-head #my-day .names span { font-size: 9px; letter-spacing: -.02em; }'
    : '#dash-head #my-day .names { display: none; }';
  document.head.appendChild(st);
})();
</script>
"""

# Вход в режим заучивания: тот же путь, что у человека — дашборд, мусхаф,
# полный лист Аль-Бакары (стр. 3), 📖.
ENTER_JS = """
<script>
(function () {
  var v = new URLSearchParams(location.search).get('v');
  if (!v) return;
  window.__PLACE = '%PLACE%';
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var $ = function (id) { return document.getElementById(id); };
  window.addEventListener('load', function () {
    (async function () {
      await wait(1200);
      // day* — сам дашборд, никуда не уходим: смотрим «Мой день».
      if (v.indexOf('day') === 0) return;
      // Экраны разбора (debt_*) — куда человека бросает при закрытом ходе.
      // Дорога та же, что у него: «Сдачи» → карточка с вердиктом «на
      // пересдачу» (её дверь единственная акцентная, .primary).
      if (v.indexOf('debt') === 0) {
        $('dash-subs').click(); await wait(2200);
        // debt_subs — сам кабинет: блок «ПЕРЕСДАТЬ — N» сверху, дальше не идём.
        if (v === 'debt_subs') return;
        var d = document.querySelector('[data-look].primary')
             || document.querySelector('[data-look]');
        if (d) { d.click(); await wait(2400); }
        return;
      }
      $('dash-mushaf').click(); await wait(1500);
      $('btn-go-baqara').click(); await wait(1400);   // стр. 2, начало Бакары
      $('btn-prev').click(); await wait(1300);        // стр. 3 — лист целиком
      $('btn-hifz').click(); await wait(900);
    })();
  });
})();
</script>
"""

VARIANTS = {
    # Честный ноль: настоящий экран без единой инъекции. Долг висит, а в
    # заучивании о нём не сказано ничего.
    "now": MID_LINE_OF_HALF,
    # Он же в момент отказа — то, что человек видит сегодня после записи.
    "now_block": LAST_LINE_OF_HALF,
    # Предложение, ход открыт: долг есть, этап не кончился — сдаём свободно.
    "free": MID_LINE_OF_HALF,
    # То же, но пилюля внизу, у «Сдать»: ближе к руке и к моменту сдачи.
    "free_low": MID_LINE_OF_HALF,
    # Заливки пилюли: сплошная красная и нейтральная с красной точкой.
    "free_solid": MID_LINE_OF_HALF,
    "free_dot": MID_LINE_OF_HALF,
    # Другой текст: «есть пересдача» — сообщение факта, а не требование.
    "free_text": MID_LINE_OF_HALF,
    # Предложение, ход закрыт: место на кнопке.
    "wall_a": LAST_LINE_OF_HALF,
    # Предложение, ход закрыт: место в пилюле, кнопка короткая, подстрока
    # объясняет почему.
    "wall_b": LAST_LINE_OF_HALF,
    # Предложение, ход закрыт, самый скупой: и пилюля, и кнопка короткие,
    # места не называем нигде — его покажет сам разбор, который откроется.
    "wall_c": LAST_LINE_OF_HALF,
    # То же, но верным словом: тап ведёт в РАЗБОР, а не сразу в запись
    # (решение пользователя 07.09, wiki/mushaf_yassirapp.md:820). Пилюля
    # говорит о состоянии, кнопка — о действии, как в списке сдач.
    "wall_d": LAST_LINE_OF_HALF,
    # Без пилюли: когда ход закрыт, дверь одна — нижняя кнопка. Пилюля нужна
    # ровно до этого момента (вариант free), двух дверей разом не бывает.
    "wall_e": LAST_LINE_OF_HALF,
    # Экран разбора — то, куда бросает при закрытом ходе. Вопрос
    # пользователя: чем ему объяснить, что это долг и он держит, не отнимая
    # места на экране.
    "debt_now": LAST_LINE_OF_HALF,   # как есть: перекинуло и ничего не сказало
    "debt_sub": LAST_LINE_OF_HALF,   # подстрока шапки уже есть — меняем текст
    "debt_btn": LAST_LINE_OF_HALF,   # объяснение уезжает на саму кнопку
    # Кабинет студента: туда предлагает бросать пользователь. Блок
    # «ПЕРЕСДАТЬ — N» там уже есть (index.html:8263), дорисовывать нечего.
    "debt_subs": LAST_LINE_OF_HALF,
    # Проверка живого кода. На стенде сдан лист 3: строка 2 принята, строка 3
    # ждёт устаза, строка 3 (line=2) возвращена на пересдачу.
    "real_free": 4,   # своё место без сдачи — ход открыт, ждём пилюлю
    "real_wall": 3,   # стоим на сданной строке — ход закрыт, ждём «Сдачи»
    # Панель записи: как она выглядит в каждом состоянии (юзабилити).
    "rec_idle": 4,
    "rec_live": 4,
    "rec_done": 4,
    # Сколько шагов до записи: как сейчас (спрашиваем «Записать») против
    # «шторка открывается уже пишущей».
    "flow_ask": 4,
    "flow_go": 4,
    "flow_slim": 4,
    # Навигация в режиме выбора места.
    "pick_nav": 4,
    # «Мой день» при длинных наборах заданий - жалоба пользователя 13.09:
    # «цифры 5 или 6 кажется не помещаются».
    "day3": 4,
    "day5": 4,
    "day6": 4,
    # Починка: A - счётчик не переносится, подписи мельче; B - при пяти и
    # более заданиях подписи уходят, остаются полоски и счёт.
    "day6_a": 4,
    "day6_b": 4,
}


def page(variant):
    html = stand.dev_index()
    html += ENTER_JS.replace("%PLACE%", DEBT_PLACE)
    # real_* — НАСТОЯЩЕЕ приложение после правки, без единой инъекции: проверка,
    # а не макет. Дорога в режим та же, что у человека.
    if variant.startswith("real_"):
        return html
    if variant.startswith("day6_"):
        return html + DAY_FIX
    if (variant.startswith("rec_") or variant.startswith("flow_")
            or variant == "pick_nav"):
        return html + REC_JS
    if variant == "now_block":
        html += NOW_BLOCK_JS
    elif variant != "now":
        html += "<style>%s</style>" % GATE_CSS + GATE_JS
    return html


def build():
    app = stand.build_app()

    async def variant_page(request):
        v = request.query.get("v", "now")
        # Указатель ставим под вариант: «ход открыт» — середина половины,
        # «хода нет» — её последняя строка.
        if v.startswith("day"):
            # Настоящие наборы с прода (13.09): у мужчин есть группа с шестью
            # заданиями (m,r,t,j,n,h) и с пятью, у женщин - с пятью.
            import sqlite3 as _sq
            tasks = "m,r,t"
            if v.startswith("day6"):
                tasks = "m,r,t,j,n,h"
            elif v.startswith("day5"):
                tasks = "m,r,t,j,n"
            with _sq.connect(stand.db.DB) as conn:
                conn.execute("UPDATE groups SET tasks=? WHERE chat_id=?",
                             (tasks, stand.CHAT))
        elif v == "pick_nav":
            # «Поправить»: указателя нет, приложение само спрашивает место —
            # ровно тот экран, где нужен перескок по страницам.
            stand.set_state("fresh")
        else:
            mushaf_words.set_hifz_pointer(stand.STUDENT, 3,
                                          VARIANTS.get(v, MID_LINE_OF_HALF), 1)
        return web.Response(text=page(v), content_type="text/html")

    async def variant_frame(request):
        v = request.query.get("v", "now")
        # Ширину можно задать: пилюля внизу добавляет пятый элемент в ряд, и
        # проверять её надо не только на 390, но и на узких 360.
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
        print("стенд: http://127.0.0.1:%d/vframe?v=wall_a" % PORT)
        web.run_app(app, host="127.0.0.1", port=PORT, print=None)
        return

    chrome = stand.find_chrome()
    threading.Thread(
        target=lambda: web.run_app(app, host="127.0.0.1", port=PORT, print=None,
                                   handle_signals=False),
        daemon=True).start()
    time.sleep(3)

    OUT.mkdir(parents=True, exist_ok=True)
    only = [s.strip() for s in args.only.split(",") if s.strip()]
    for name in VARIANTS:
        if only and name not in only:
            continue
        png = OUT / ("gate_%s.png" % name)
        subprocess.run([
            chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--window-size=%d,%d" % (WIDTH, HEIGHT),
            "--virtual-time-budget=17000", "--screenshot=%s" % png,
            "http://127.0.0.1:%d/vframe?v=%s" % (PORT, name),
        ], check=True, capture_output=True)
        if not png.exists():
            raise SystemExit("вариант %s не снялся" % name)
        print("  %-10s %4d КБ" % (name, png.stat().st_size // 1024))
    print("снимки в %s" % OUT)


if __name__ == "__main__":
    main()
