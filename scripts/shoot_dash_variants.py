"""Варианты компоновки дашборда — снимки для выбора глазами (10.09.2026).

Зачем отдельный скрипт: спорить о вёрстке словами дорого и неточно. Здесь
поднимается тот же стенд, что и у shoot_onboarding (настоящее приложение,
пустая база, подменённая авторизация), а поверх настоящего дашборда
накладывается только CSS варианта. Это важно: варианты — это НАСТОЯЩИЙ
дашборд в другой раскладке, а не отдельный мокап, который завтра разойдётся
с кодом (см. feedback «Сверять мокапы с реальным кодом»).

    python scripts/shoot_dash_variants.py           # снять все варианты
    python scripts/shoot_dash_variants.py --serve   # покрутить руками

Дверь «Лента» дорисовывается скриптом: выбирать компоновку под сегодняшний
набор дверей бессмысленно, если завтра их станет на одну больше.
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
from aiohttp import web                     # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "logs" / "dash_variants"
PORT = 8801
WIDTH, HEIGHT = 390, 844

# Дверь «Лента» — пока её нет в index.html, но компоновку выбираем под неё.
ADD_FEED = """
<script>
window.__feedSkip = SKIP;
window.__mydayTop = MYDAY_TOP;
window.addEventListener('load', function () {
  setTimeout(function () {
    var doors = document.getElementById('dash-doors');
    if (!doors || document.getElementById('dash-feed')) return;

    // Шестерёнка вместо RU и луны: настройки живут в углу, как принято.
    var head = document.getElementById('dash-settings');
    if (head) head.innerHTML =
      '<button id="btn-profile" title="Настройки">\u2699</button>';

    // Полуоткрытая лента. Тексты - образец, чтобы видеть настоящую длину
    // строк, а не пустые прямоугольники.
    var items = [
      ['\u0422', 'Тадаббур', 'Он видит тебя прямо сейчас - посреди долгов и усталости\u2026', '14:00'],
      ['\u0410', 'Абдулла', 'м р т', '13:12'],
      ['\u0423', 'Умар устаз', 'МашаАллах, приняли. Дальше 40+40 с 7 страницы.', '12:48']
    ];
    var box = document.createElement('div');
    box.id = 'dash-feed';
    box.innerHTML = '<div class="f-head"><span class="f-cap">ЛЕНТА</span>'
      + '<span class="f-more">вся лента \u203a</span></div>'
      + items.slice(window.__feedSkip || 0).map(function (it) {
          return '<div class="f-row"><span class="f-ava">' + it[0] + '</span>'
            + '<span class="f-body"><span class="f-who">' + it[1] + '</span>'
            + '<span class="f-txt">' + it[2] + '</span></span>'
            + '<span class="f-at">' + it[3] + '</span></div>';
        }).join('');
    doors.parentNode.insertBefore(box, doors.nextSibling);

    // Строка-лента в одной грядке с шестерёнкой: эта строка сейчас пустая
    // на девять десятых, а самое свежее событие в неё помещается целиком.
    // «Мой день» — в грядку с шестерёнкой (просьба пользователя 10.09):
    // строка шапки пустует, а прогресс по заданиям в неё помещается.
    var head = document.getElementById('dash-head');
    var md = document.getElementById('my-day');
    if (head && md && window.__mydayTop) head.insertBefore(md, head.firstChild);

    var t = document.createElement('div');
    t.id = 'dash-ticker';
    t.innerHTML = '<span class="t-ava">' + items[0][0] + '</span>'
      + '<span class="t-txt"><b>' + items[0][1] + '</b> ' + items[0][2] + '</span>';
    if (head) head.insertBefore(t, head.firstChild);
  }, 1200);
});
</script>
"""

# Стиль полуоткрытой ленты - общий для всех вариантов, где она есть.
FEED_CSS = """
  /* direction: ltr обязателен: страница целиком в RTL (нужен арабскому
     тексту мусхафа), и без этого шестерёнка уезжает влево, а прогресс
     вправо - зеркалится сам порядок. Та же ловушка, что записана в
     wiki/mushaf_yassirapp.md. */
  #dash-head { display: flex; align-items: center; gap: 10px; direction: ltr; }
  #dash-online { display: none; }
  #dash-ticker {
    flex: 1; min-width: 0; display: flex; align-items: center; gap: 9px;
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 19px; padding: 5px 12px 5px 5px; height: 38px;
    box-sizing: border-box; cursor: pointer;
  }
  #dash-ticker .t-ava {
    flex: 0 0 auto; width: 26px; height: 26px; border-radius: 8px;
    background: var(--accent-soft); color: var(--accent);
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 600;
  }
  #dash-ticker .t-txt {
    flex: 1; min-width: 0; font-size: 12px; color: var(--muted);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  #dash-ticker .t-txt b { color: var(--ink); font-weight: 600; }

  #dash-feed {
    direction: ltr; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 20px; box-shadow: var(--shadow-sm);
    padding: 12px 14px 8px; margin-bottom: 12px;
    display: flex; flex-direction: column; gap: 2px;
  }
  #dash-feed .f-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 6px; }
  #dash-feed .f-cap { font-size: 11px; font-weight: 700; letter-spacing: .08em; color: var(--muted); }
  #dash-feed .f-more { font-size: 12px; color: var(--accent); }
  #dash-feed .f-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; }
  #dash-feed .f-row + .f-row { border-top: 1px solid var(--card-border); }
  #dash-feed .f-ava {
    flex: 0 0 auto; width: 28px; height: 28px; border-radius: 9px;
    background: var(--accent-soft); color: var(--accent);
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 600;
  }
  #dash-feed .f-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  #dash-feed .f-who { font-size: 12.5px; font-weight: 600; color: var(--ink); }
  #dash-feed .f-txt {
    font-size: 12px; color: var(--muted);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  #dash-feed .f-at { flex: 0 0 auto; font-size: 10.5px; color: var(--muted); }
"""

# ── общее для всех новых вариантов ────────────────────────────────────────
# Порядок экрана: сначала что должен я, потом чем это сделать, потом что у
# своих, и в самом низу дыхание джамаата.
#
# Пульс НЕ перестраиваем и сердце НЕ уменьшаем (решение пользователя
# 10.09.2026): холст рисуется в 330x168 и сжатие средствами CSS делает точки
# мелкими и редкими - сердце начинает читаться хуже. Вместо этого блок просто
# уезжает вниз, за первый экран: на него смотрят между делом, а не ради него
# открывают приложение.
COMMON = """
  #dashboard { display: flex; flex-direction: column; }
  #dash-head { order: 0; }
  #lang-menu { order: 0; }
  #my-day { order: 1; margin-bottom: 12px; }
  #dash-doors { order: 2; margin-bottom: 12px; }
  #dash-settings #btn-profile {
    border: 1px solid var(--card-border); background: var(--card-bg);
    border-radius: 50%; width: 38px; height: 38px; font-size: 17px;
    color: var(--muted); cursor: pointer;
  }
"""

# Четыре двери ровным квадратом: лента больше не дверь, она полуоткрыта
# отдельным блоком, и пятая плитка не нужна.
DOORS4 = """
  #dash-doors { grid-template-columns: 1fr 1fr; gap: 10px; }
  .dash-row {
    aspect-ratio: auto; min-height: 116px;
    padding: 13px 13px 14px; gap: 10px; border-radius: 18px;
  }
  .dash-row .mark { width: 38px; height: 38px; border-radius: 12px; font-size: 19px; }
  .dash-row .label { font-size: 15px; }
  .dash-row .sub { font-size: 11.5px; line-height: 1.25; }
  .dash-row .badge { top: 10px; right: 10px; }
  /* Базовое правило #dash-doors.three #dash-trainer сильнее по
     специфичности - перебиваем той же силой, иначе Тренажёр остаётся
     строкой во всю ширину. */
  #dash-doors.three #dash-trainer {
    grid-column: auto; aspect-ratio: auto; min-height: 116px;
    flex-direction: column; align-items: stretch; gap: 10px;
  }
"""

PULSE_SIDE = """
  #dash-feed { order: 3; }
  #dash-pulse { order: 4; }
  /* !important: pulseInit() ставит блоку инлайновый display:flex, а инлайн
     бьёт таблицу стилей. */
  #dash-pulse {
    display: grid !important;
    grid-template-columns: %s 1fr;
    grid-template-areas: "heart count" "heart split" "days days";
    column-gap: 12px; row-gap: 2px; align-items: center;
  }
  #dash-pulse #pulse-heart { grid-area: heart; height: auto; }
  #dash-pulse .p-count { grid-area: count; align-self: end; }
  #dash-pulse .p-split { grid-area: split; align-self: start; }
  #dash-pulse .p-days { grid-area: days; }
"""

# Пульс живёт ниже сгиба - для его вариантов снимаем кадр повыше.
SHOT_H = {"brief1": 980, "brief_smart": 980, "brief2": 1020,
          "brief_bare": 980, "feed_open": 844,
          "pulse58": 1180, "pulse66": 1180, "feed_low": 1180,
          "ticker": 1180, "ticker_both": 1180, "ticker_smart": 1180,
          "myday_top": 1180, "myday_lab": 1180,
          "feed_live": 844, "feed_ustaz": 844, "feed_dark": 844, "settings": 900, "sett_live": 900, "dark": 900, "online": 900, "sett_dark": 900}


MYDAY_CSS = """
  /* direction: ltr обязателен: страница целиком в RTL (нужен арабскому
     тексту мусхафа), и без этого шестерёнка уезжает влево, а прогресс
     вправо - зеркалится сам порядок. Та же ловушка, что записана в
     wiki/mushaf_yassirapp.md. */
  #dash-head { display: flex; align-items: center; gap: 10px; direction: ltr; }
  #dash-online { display: none; }
  #dash-ticker { display: none; }
  #my-day.on {
    /* order: -1 обязателен - общий блок дал #my-day order:1 для колонки
       дашборда, и в шапке это отправляло его ЗА шестерёнку.
       flex-direction: row - базовый #my-day это колонка, иначе полоски
       сжимаются в 10px и пропадают. */
    order: -1; flex-direction: row;
    flex: 1; min-width: 0; margin: 0;
    padding: 0 13px; height: 38px; border-radius: 19px;
    align-items: center; gap: 12px;
  }
  #my-day .cap { order: 2; flex: 0 0 auto; }
  #my-day .cap span { display: none; }
  #my-day .cap b { font-size: 13px; }
  #my-day .bars { order: 1; flex: 1; min-width: 0; }
  #my-day .names { display: none; }
"""

# То же, но с подписями заданий: строка выше, зато видно, ЧТО осталось.
MYDAY_LAB = """
  /* direction: ltr обязателен: страница целиком в RTL (нужен арабскому
     тексту мусхафа), и без этого шестерёнка уезжает влево, а прогресс
     вправо - зеркалится сам порядок. Та же ловушка, что записана в
     wiki/mushaf_yassirapp.md. */
  #dash-head { display: flex; align-items: center; gap: 10px; direction: ltr; }
  #dash-online { display: none; }
  #dash-ticker { display: none; }
  #my-day.on {
    order: -1;
    flex: 1; min-width: 0; margin: 0;
    padding: 7px 13px 6px; border-radius: 16px;
    display: grid !important;
    grid-template-columns: 1fr auto;
    grid-template-areas: "bars num" "names num";
    column-gap: 12px; row-gap: 4px; align-items: center;
  }
  #my-day .cap { grid-area: num; }
  #my-day .cap span { display: none; }
  #my-day .cap b { font-size: 14px; }
  #my-day .bars { grid-area: bars; }
  #my-day .names { grid-area: names; }
  #my-day .names span { font-size: 9.5px; }
"""


# ── экран настроек (макет, 10.09.2026) ────────────────────────────────────
# Показывается поверх дашборда, чтобы увидеть его в настоящем окружении:
# те же карточки, та же палитра, тот же возврат «← Дашборд» слева вверху.
SETTINGS_HTML = """
<script>
window.addEventListener('load', function () {
  setTimeout(function () {
    var d = document.createElement('div');
    d.id = 'sett';
    d.innerHTML =
      '<div class="s-head">'
      +   '<button class="s-back">\u2190 \u0414\u0430\u0448\u0431\u043e\u0440\u0434</button>'
      +   '<span class="s-title">Настройки</span>'
      + '</div>'
      + '<div class="s-card">'
      +   '<label class="s-lab">Имя</label>'
      +   '<input class="s-inp" value="Абдулла">'
      +   '<p class="s-hint">Это имя видят устаз в отчётах и вся группа в рейтинге.</p>'
      + '</div>'
      + '<div class="s-card">'
      +   '<label class="s-lab">Год рождения <i>по желанию</i></label>'
      +   '<input class="s-inp" placeholder="например, 1994" inputmode="numeric">'
      +   '<label class="s-lab s-lab2">Откуда сдаёшь задания <i>по желанию</i></label>'
      +   '<select class="s-inp"><option>Не указано</option><option selected>Чуйская область</option>'
      +   '<option>Бишкек</option><option>Ош</option><option>Ошская область</option>'
      +   '<option>Джалал-Абадская область</option><option>Иссык-Кульская область</option>'
      +   '<option>Нарынская область</option><option>Таласская область</option>'
      +   '<option>Баткенская область</option><option>Другая страна</option></select>'
      + '</div>'
      + '<div class="s-card">'
      +   '<label class="s-lab">Язык</label>'
      +   '<div class="s-seg"><button>Русский</button><button class="on">Кыргызча</button><button>Ўзбекча</button></div>'
      +   '<label class="s-lab s-lab2">Тема</label>'
      +   '<div class="s-seg"><button class="on">☀️ День</button><button>🌙 Ночь</button></div>'
      + '</div>'
      + '<button class="s-out">Выйти из приложения</button>';
    document.body.appendChild(d);
  }, 1200);
});
</script>
"""

SETTINGS_CSS = """
  #sett {
    position: fixed; inset: 0; z-index: 90; overflow-y: auto;
    direction: ltr; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: linear-gradient(160deg, var(--dash-bg-start), var(--dash-bg-end));
    padding: 14px 16px 24px;
  }
  #sett .s-head { display: flex; align-items: center; gap: 10px; min-height: 38px; margin-bottom: 14px; }
  #sett .s-back {
    border: none; background: none; padding: 0; cursor: pointer;
    font: inherit; font-size: 14px; color: var(--accent);
  }
  #sett .s-title { margin-left: auto; margin-right: auto; font-size: 15px; font-weight: 600; color: var(--ink); }
  #sett .s-card {
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 20px; box-shadow: var(--shadow-sm);
    padding: 14px 15px 16px; margin-bottom: 12px;
  }
  #sett .s-lab {
    display: block; font-size: 12px; font-weight: 600; color: var(--ink);
    margin-bottom: 7px;
  }
  #sett .s-lab2 { margin-top: 16px; }
  #sett .s-lab i { font-style: normal; font-weight: 400; color: var(--muted); }
  #sett .s-inp {
    width: 100%; box-sizing: border-box; font: inherit; font-size: 15px;
    padding: 11px 12px; border-radius: 13px;
    border: 1px solid var(--card-border); background: var(--card-bg); color: var(--ink);
  }
  #sett .s-hint { margin: 8px 2px 0; font-size: 11.5px; color: var(--muted); line-height: 1.35; }
  #sett .s-seg { display: flex; gap: 6px; }
  #sett .s-seg button {
    flex: 1; font: inherit; font-size: 13px; padding: 10px 4px;
    border-radius: 12px; cursor: pointer;
    border: 1px solid var(--card-border); background: var(--card-bg); color: var(--muted);
  }
  #sett .s-seg button.on {
    border-color: var(--accent); color: var(--accent-ink);
    background: var(--accent); font-weight: 600;
  }
  #sett .s-out {
    display: block; margin: 18px auto 0; font: inherit; font-size: 12.5px;
    color: var(--muted); background: none; border: none; cursor: pointer; padding: 6px 10px;
  }
"""

# -- подбриф ленты под прогрессом + экран ленты (11.09.2026) ---------------
# Предложение пользователя: не блок в три строки под дверями, а СТРОКА сразу
# под "Моим днём" - свежее сообщение и счётчик непрочитанных, тап открывает
# ленту.
#
# Лента открывается полноэкранным слоем, как #sett и #learn, а НЕ попапом:
# попап здесь - это #word-popup и #confirm-overlay, мелочь на пару строк.
# Лента - длинный список с прокруткой, медиа и неделей истории.
#
# Два варианта наполнения строки:
#   brief1 - самое свежее по времени и счётчик ВСЕХ непрочитанных;
#   brief_smart - самое важное непрочитанное (устаз тебе > Тадаббур >
#     остальное) и счётчик только АДРЕСОВАННОГО тебе, остальное - точкой.
FEED_ITEMS = """
window.__FEED = [
  {a:'\u0419', who:'\u042f\u0441\u0441\u0438\u0440', src:'\u0422\u0430\u0434\u0430\u0431\u0431\u0443\u0440', at:'14:00', bot:1,
   txt:'\u041e\u043d \u0432\u0438\u0434\u0438\u0442 \u0442\u0435\u0431\u044f \u043f\u0440\u044f\u043c\u043e \u0441\u0435\u0439\u0447\u0430\u0441 \u2014 \u043f\u043e\u0441\u0440\u0435\u0434\u0438 \u0434\u043e\u043b\u0433\u043e\u0432 \u0438 \u0443\u0441\u0442\u0430\u043b\u043e\u0441\u0442\u0438. \u0418 \u0437\u043d\u0430\u0435\u0442, \u0447\u0442\u043e \u0442\u044b \u0432\u0441\u0451 \u0440\u0430\u0432\u043d\u043e \u043e\u0442\u043a\u0440\u044b\u043b \u043c\u0443\u0441\u0445\u0430\u0444.'},
  {a:'\u0410', who:'\u0410\u0431\u0434\u0443\u043b\u043b\u0430', src:'N-2\u0430', at:'13:12', txt:'\u043c \u0440 \u0442'},
  {a:'\u0423', who:'\u0423\u043c\u0430\u0440 \u0443\u0441\u0442\u0430\u0437', src:'N-2\u0430', at:'12:48', mine:1,
   txt:'\u041c\u0430\u0448\u0430\u0410\u043b\u043b\u0430\u0445, \u043f\u0440\u0438\u043d\u044f\u043b\u0438. \u0414\u0430\u043b\u044c\u0448\u0435 40+40 \u0441 7 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u044b.'},
  {a:'\u0422', who:'\u0422\u0430\u043b\u0430\u0441', src:'N-2\u0430', at:'11:30', voice:'0:42'},
  {a:'\u0419', who:'\u042f\u0441\u0441\u0438\u0440', src:'\u043b\u0438\u0447\u043d\u043e\u0435', at:'09:00', bot:1,
   txt:'\u0417\u0430\u0434\u0430\u043d\u0438\u044f \u043d\u0430 \u0441\u0435\u0433\u043e\u0434\u043d\u044f: \u043f\u043e\u0432\u0442\u043e\u0440\u0435\u043d\u0438\u0435, \u043c\u0443\u0444\u0440\u0430\u0434\u0430\u0442, \u0437\u0430\u0443\u0447\u0438\u0432\u0430\u043d\u0438\u0435.'},
  {a:'\u0421', who:'\u0421\u0443\u043b\u0435\u0439\u043c\u0430\u043d', src:'N-2\u0430', at:'\u0432\u0447\u0435\u0440\u0430', photo:1}
];
"""

BRIEF_JS = """
<script>
%s
window.addEventListener('load', function () {
  setTimeout(function () {
    var doors = document.getElementById('dash-doors');
    if (!doors) return;
    // brief1 - первое по времени; brief_smart - разбор устаза (mine).
    var f = window.__SMART ? window.__FEED[2] : window.__FEED[0];

    var tail = window.__SMART
      ? '<span class="b-n one">1</span>'
      : '<span class="b-n">47</span>';
    if (window.__SMART) tail += '<span class="b-dot"></span>';

    var box = document.createElement('div');
    box.id = 'dash-brief';
    box.setAttribute('role', 'button');
    box.innerHTML =
      '<span class="b-ava">' + f.a + '</span>'
      + '<span class="b-body"><span class="b-who">' + f.who
      +   '<i>' + f.src + '</i></span>'
      + '<span class="b-txt">' + (f.txt || '') + '</span></span>'
      + tail;
    doors.parentNode.insertBefore(box, doors);

    if (window.__BRIEF2) {
      var g = window.__FEED[0];
      var row = document.createElement('div');
      row.id = 'dash-brief2';
      row.innerHTML =
        '<span class="b-ava">' + g.a + '</span>'
        + '<span class="b-body"><span class="b-who">' + g.who
        +   '<i>' + g.src + '</i></span>'
        + '<span class="b-txt">' + (g.txt || '') + '</span></span>';
      box.parentNode.insertBefore(row, box.nextSibling);
    }
  }, 1200);
});
</script>
""" % FEED_ITEMS

BRIEF_CSS = """
  /* direction: ltr - страница целиком RTL ради арабского текста мусхафа,
     без него аватар уезжает вправо, а счётчик влево. Та же ловушка, что
     записана в wiki/mushaf_yassirapp.md. */
  #dash-brief, #dash-brief2 {
    direction: ltr; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    display: flex; align-items: center; gap: 10px;
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 16px; box-shadow: var(--shadow-sm);
    padding: 8px 12px 8px 8px; margin-bottom: 10px; cursor: pointer;
  }
  #dash-brief .b-ava, #dash-brief2 .b-ava {
    flex: 0 0 auto; width: 30px; height: 30px; border-radius: 10px;
    background: var(--accent-soft); color: var(--accent);
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 600;
  }
  #dash-brief .b-body, #dash-brief2 .b-body {
    flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px;
  }
  #dash-brief .b-who, #dash-brief2 .b-who {
    font-size: 12.5px; font-weight: 600; color: var(--ink);
    display: flex; align-items: baseline; gap: 6px;
  }
  #dash-brief .b-who i, #dash-brief2 .b-who i {
    font-style: normal; font-size: 10.5px; font-weight: 400; color: var(--muted);
  }
  #dash-brief .b-txt, #dash-brief2 .b-txt {
    font-size: 12px; color: var(--muted);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  /* Счётчик спокойный (var(--accent), не var(--no)): непрочитанное в ленте -
     не долг. Красным в приложении помечены только сдачи. */
  #dash-brief .b-n {
    flex: 0 0 auto; background: var(--accent); color: var(--accent-ink);
    border-radius: 11px; min-width: 22px; height: 22px; padding: 0 6px;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums;
  }
  /* Точка "есть и другое новое" - без числа, чтобы групповой шум не
     превращался в несбрасываемую цифру. */
  #dash-brief .b-dot {
    flex: 0 0 auto; width: 7px; height: 7px; border-radius: 50%;
    background: var(--card-border); margin-left: -4px;
  }
  #dash-brief2 { margin-top: -4px; }
"""

BRIEF_BARE = BRIEF_CSS + """
  #dash-brief {
    background: none; border: none; box-shadow: none;
    border-bottom: 1px solid var(--card-border);
    border-radius: 0; padding: 6px 2px 10px;
  }
"""

# -- экран ленты (макет) --------------------------------------------------
FEED_SCREEN_HTML = """
<script>
%s
window.addEventListener('load', function () {
  setTimeout(function () {
    function row(f) {
      var media = '';
      if (f.voice) media = '<span class="m-voice">\u25b6 \u0433\u043e\u043b\u043e\u0441\u043e\u0432\u043e\u0435 &middot; ' + f.voice + '</span>';
      if (f.photo) media = '<span class="m-photo">\u0444\u043e\u0442\u043e \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u044b</span>';
      return '<div class="l-row' + (f.bot ? ' bot' : '') + '">'
        + '<span class="l-ava">' + f.a + '</span>'
        + '<span class="l-body">'
        +   '<span class="l-top"><b>' + f.who + '</b><i>' + f.src + '</i>'
        +     '<u>' + f.at + '</u></span>'
        +   (f.txt ? '<span class="l-txt">' + f.txt + '</span>' : '')
        +   media
        + '</span></div>';
    }
    var F = window.__FEED;
    var d = document.createElement('div');
    d.id = 'feed';
    d.innerHTML =
      '<div class="l-head">'
      +   '<button class="l-back">\u2190 \u0414\u0430\u0448\u0431\u043e\u0440\u0434</button>'
      +   '<span class="l-title">\u041b\u0435\u043d\u0442\u0430</span>'
      + '</div>'
      + '<div class="l-scroll">'
      +   '<div class="l-day">\u0421\u0435\u0433\u043e\u0434\u043d\u044f</div>'
      +   F.slice(0, 5).map(function (f) { return row(f); }).join('')
      +   '<div class="l-day">\u0412\u0447\u0435\u0440\u0430</div>'
      +   row(F[5])
      +   '<div class="l-end">\u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u0445\u0440\u0430\u043d\u044f\u0442\u0441\u044f \u0441\u0435\u043c\u044c \u0434\u043d\u0435\u0439</div>'
      + '</div>'
      + '<div class="l-foot">\u0427\u0438\u0442\u0430\u0442\u044c \u043c\u043e\u0436\u043d\u043e \u0437\u0434\u0435\u0441\u044c, \u043e\u0442\u0432\u0435\u0447\u0430\u0442\u044c \u2014 \u0432 Telegram'
      +   '<button class="l-tg">\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443</button></div>';
    document.body.appendChild(d);
  }, 1200);
});
</script>
""" % FEED_ITEMS

FEED_SCREEN_CSS = BRIEF_CSS + """
  #feed {
    position: fixed; inset: 0; z-index: 90;
    direction: ltr; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: linear-gradient(160deg, var(--dash-bg-start), var(--dash-bg-end));
    display: flex; flex-direction: column;
  }
  #feed .l-head {
    flex: 0 0 auto; display: flex; align-items: center; gap: 10px;
    min-height: 38px; padding: 14px 16px 10px;
  }
  #feed .l-back {
    border: none; background: none; padding: 0; cursor: pointer;
    font: inherit; font-size: 14px; color: var(--accent);
  }
  #feed .l-title {
    margin-left: auto; margin-right: auto;
    font-size: 15px; font-weight: 600; color: var(--ink);
  }
  #feed .l-scroll { flex: 1; overflow-y: auto; padding: 0 14px 12px; }
  #feed .l-day {
    text-align: center; font-size: 11px; color: var(--muted);
    margin: 10px 0 8px; letter-spacing: .04em;
  }
  #feed .l-row {
    display: flex; gap: 10px; align-items: flex-start;
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 16px; box-shadow: var(--shadow-sm);
    padding: 10px 12px; margin-bottom: 8px;
  }
  /* Бот отличается фоном, а не подписью "бот": имя у него своё, как в
     Telegram, и лишнее слово в каждой строке только шумит. */
  #feed .l-row.bot { background: var(--accent-soft); border-color: transparent; }
  #feed .l-ava {
    flex: 0 0 auto; width: 32px; height: 32px; border-radius: 10px;
    background: var(--accent-soft); color: var(--accent);
    display: flex; align-items: center; justify-content: center;
    font-size: 13.5px; font-weight: 600;
  }
  #feed .l-row.bot .l-ava { background: var(--card-bg); }
  #feed .l-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  #feed .l-top { display: flex; align-items: baseline; gap: 7px; }
  #feed .l-top b { font-size: 13px; font-weight: 600; color: var(--ink); }
  #feed .l-top i {
    font-style: normal; font-size: 10.5px; color: var(--muted);
    border: 1px solid var(--card-border); border-radius: 6px; padding: 1px 5px;
  }
  #feed .l-top u { margin-left: auto; text-decoration: none; font-size: 10.5px; color: var(--muted); }
  #feed .l-txt { font-size: 13px; line-height: 1.42; color: var(--ink); }
  #feed .m-voice, #feed .m-photo {
    display: inline-flex; align-items: center; gap: 6px; align-self: flex-start;
    font-size: 12px; color: var(--accent);
    background: var(--accent-soft); border-radius: 9px; padding: 6px 10px;
  }
  #feed .m-photo { color: var(--muted); background: var(--card-bg); border: 1px dashed var(--card-border); }
  #feed .l-end { text-align: center; font-size: 11px; color: var(--muted); padding: 14px 0 4px; }
  #feed .l-foot {
    flex: 0 0 auto; display: flex; align-items: center; gap: 10px;
    padding: 10px 16px 16px; font-size: 11.5px; color: var(--muted);
    border-top: 1px solid var(--card-border);
  }
  #feed .l-tg {
    margin-left: auto; font: inherit; font-size: 12px; cursor: pointer;
    border: 1px solid var(--card-border); background: var(--card-bg);
    color: var(--accent); border-radius: 11px; padding: 7px 12px;
  }
"""


VARIANTS = {
    "feed_ustaz": "",
    "feed_dark": "",
    "feed_live": "",
    # Подбриф ленты под прогрессом (11.09.2026).
    "brief1": BRIEF_CSS,
    "brief_smart": BRIEF_CSS,
    "brief2": BRIEF_CSS,
    "brief_bare": BRIEF_BARE,
    "feed_open": FEED_SCREEN_CSS,
    "now": "",
    "sett_live": "",
    "dark": "",
    "online": "",
    "sett_dark": "",

    # Макет экрана настроек - что откроется под шестерёнкой.
    "settings": SETTINGS_CSS,

    # Лента под дверями.
    "feed_low": COMMON + FEED_CSS + DOORS4 + """
  #dash-feed { order: 3; }
  #dash-pulse { order: 4; }
""",

    # Лента сразу под «Моим днём» - её видно первой, двери уезжают ниже.
    "feed_high": COMMON + FEED_CSS + DOORS4 + """
  #dash-feed { order: 2; }
  #dash-doors { order: 3; }
  #dash-pulse { order: 4; }
""",

    # Строка-лента в шапке ВМЕСТО блока: всё уезжает вверх, пульс попадает
    # на первый экран целиком.
    "ticker": COMMON + FEED_CSS + DOORS4 + PULSE_SIDE % "58%" + """
  #dash-feed { display: none; }
""",

    # Строка в шапке И блок: самое свежее всегда перед глазами, а под
    # дверями - ещё три.
    "ticker_both": COMMON + FEED_CSS + DOORS4 + PULSE_SIDE % "58%",

    # Строка в шапке - самое свежее, блок под дверями - те, что до него.
    "ticker_smart": COMMON + FEED_CSS + DOORS4 + PULSE_SIDE % "58%",

    # «Мой день» в шапке, без подписей заданий.
    "myday_top": COMMON + FEED_CSS + MYDAY_CSS + DOORS4 + PULSE_SIDE % "58%",

    # «Мой день» в шапке, с подписями — видно, что именно осталось.
    "myday_lab": COMMON + FEED_CSS + MYDAY_LAB + DOORS4 + PULSE_SIDE % "58%",

    # Пульс: сердце сдвинуто в левую часть, число и разбивка - сбоку справа.
    # Волна остаётся во всю ширину под ними. Доля сердца - 58%: «чуть-чуть
    # сдвинуть», а не ужать вдвое.
    "pulse58": COMMON + FEED_CSS + DOORS4 + PULSE_SIDE % "58%",

    # То же, но сердцу отдано больше - 66%.
    "pulse66": COMMON + FEED_CSS + DOORS4 + PULSE_SIDE % "66%",
}


def page(variant):
    html = stand.dev_index()
    css = VARIANTS.get(variant, "")
    # В "умном" варианте самое свежее живёт в строке шапки, поэтому блок
    # начинает со второго - иначе оно двоится.
    skip = "1" if variant == "ticker_smart" else "0"
    top = "true" if variant.startswith("myday") else "false"
    # "now" - честный ноль: настоящий index.html без единой инъекции, иначе
    # сравнивать не с чем.
    if variant == "now":
        return html
    if variant == "online":
        # На стенде онлайн пуст (нужно >=3 человека) - подставляем строку
        # руками, иначе кашу в шапке не увидеть.
        return html + ("<script>window.addEventListener('load',function(){"
                       "setTimeout(function(){var e=document.getElementById('dash-online');"
                       "if(e)e.innerHTML='<span class=\"dot\"></span>сейчас в онлайне учатся 7';},2500);"
                       "});</script>")
    if variant in ("dark", "sett_dark"):
        # Тёмная тема ставится до отрисовки, как это делает скрипт в <head>.
        js = "<script>document.documentElement.setAttribute('data-theme','dark');"
        if variant == "sett_dark":
            js += ("window.addEventListener('load',function(){setTimeout(function(){"
                   "document.getElementById('btn-profile').click();},1500);});")
        return html + js + "</script>"
    if variant == "feed_dark":
        return html + ("<script>document.documentElement.setAttribute('data-theme','dark');"
                       "window.addEventListener('load',function(){"
                       "setTimeout(function(){var b=document.getElementById('dash-brief');"
                       "if(b)b.click();},2500);});</script>")
    if variant == "feed_ustaz":
        return html + ("<script>window.addEventListener('load',function(){"
                       "setTimeout(function(){var b=document.getElementById('dash-brief');"
                       "if(b)b.click();},2500);});</script>")
    if variant == "feed_live":
        # Настоящий экран ленты из index.html - открываем тапом по строке
        # дашборда. Ждём дольше настроек: строка появляется после первого
        # ответа heartbeat, а не сразу при отрисовке.
        return html + ("<script>window.addEventListener('load',function(){"
                       "setTimeout(function(){var b=document.getElementById('dash-brief');"
                       "if(b)b.click();},2500);});</script>")
    if variant == "sett_live":
        # Настоящий экран настроек из index.html: открываем его тем же
        # тапом по шестерёнке, что и человек.
        return html + ("<script>window.addEventListener('load',function(){"
                       "setTimeout(function(){document.getElementById('btn-profile').click();},1500);});"
                       "</script>")
    if variant == "settings":
        return html + SETTINGS_HTML + "<style>%s</style>" % SETTINGS_CSS
    if variant.startswith("brief"):
        pre = ""
        if variant == "brief_smart":
            pre = "<script>window.__SMART=1;</script>"
        if variant == "brief2":
            pre = "<script>window.__BRIEF2=1;</script>"
        return html + pre + BRIEF_JS + "<style>%s</style>" % css
    if variant == "feed_open":
        return html + FEED_SCREEN_HTML + "<style>%s</style>" % css
    body = ADD_FEED.replace("SKIP", skip).replace("MYDAY_TOP", top)
    return html + body + ("<style>%s</style>" % css if css else "")


def build():
    app = stand.build_app()

    async def variant_page(request):
        html = page(request.query.get("v", "now"))
        if request.query.get("as") == "ustaz":
            # У устаза дверей пять - проверяем, что последняя ложится во всю
            # строку, а не оставляет пустую половину.
            html = html.replace(stand.STUDENT, stand.USTAZ)
        return web.Response(text=html, content_type="text/html")

    async def variant_frame(request):
        v = request.query.get("v", "now")
        h = int(request.query.get("h", HEIGHT))
        who = "&as=ustaz" if request.query.get("as") == "ustaz" else ""
        return web.Response(content_type="text/html", text=(
            "<style>html,body{margin:0;background:#fff}"
            "iframe{border:0;display:block;width:%dpx;height:%dpx}</style>"
            "<iframe src='/v?v=%s&bot=male%s'></iframe>" % (WIDTH, h, v, who)))

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
        print("стенд: http://127.0.0.1:%d/vframe?v=three" % PORT)
        web.run_app(app, host="127.0.0.1", port=PORT, print=None)
        return

    chrome = stand.find_chrome()
    threading.Thread(
        target=lambda: web.run_app(app, host="127.0.0.1", port=PORT, print=None,
                                   handle_signals=False),
        daemon=True).start()
    time.sleep(2.5)

    OUT.mkdir(parents=True, exist_ok=True)
    only = [s for s in args.only.split(",") if s]
    for name in VARIANTS:
        if only and name not in only:
            continue
        png = OUT / ("dash_%s.png" % name)
        subprocess.run([
            chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--window-size=%d,%d" % (WIDTH, SHOT_H.get(name, HEIGHT)),
            "--virtual-time-budget=16000",
            "--screenshot=%s" % png,
            "http://127.0.0.1:%d/vframe?v=%s&h=%d%s" % (PORT, name, SHOT_H.get(name, HEIGHT),
                                        "&as=ustaz" if name.endswith("_ustaz") else ""),
        ], check=True, capture_output=True)
        if not png.exists():
            raise SystemExit("вариант %s не снялся" % name)
        print("  %-6s %4d КБ  %s" % (name, png.stat().st_size // 1024, png))


if __name__ == "__main__":
    main()
