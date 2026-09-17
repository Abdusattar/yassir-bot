"""Макеты кабинета устаза (13.09.2026) — по разбору удобства.

Зачем: разбор показал, что половина устазов проверяет сдачи из приложения
реплаем в группе, мимо кабинета, а сам кабинет требует лишних шагов. Прежде
чем писать код — посмотреть предложения глазами.

Как у shoot_retake_gate: поднимается тот же стенд (настоящее приложение,
подменённая авторизация), вход под устазом, а поверх НАСТОЯЩИХ экранов
накладывается только предлагаемая разметка. Варианты *_now — честный ноль,
без единой инъекции (см. feedback «Сверять мокапы с реальным кодом»).

    python scripts/shoot_ustaz_cabinet.py           # снять всё + сравнения
    python scripts/shoot_ustaz_cabinet.py --serve   # покрутить руками

База своя (yassir_ustaz_stand), а не общая со стендом онбординга: здесь в
очередь досеяны голосовые из группы и вторая попытка той же строки, и снимки
раздела «Знания» (стенд онбординга) не должны их унаследовать.
"""
import argparse
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from datetime import timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import shoot_onboarding as stand            # noqa: E402  (поднимает стенд целиком)
from aiohttp import web                     # noqa: E402

TMP = pathlib.Path(tempfile.gettempdir()) / "yassir_ustaz_stand"
TMP.mkdir(exist_ok=True)
stand.db.DB = str(TMP / "dev.db")            # db() читает путь при каждом вызове

OUT = ROOT / "logs" / "ustaz_cabinet"
PORT = 8803
WIDTH, HEIGHT = 390, 844


# ─── данные ───────────────────────────────────────────────────────────────

def seed_extra():
    """Очередь, похожая на живую N-1: сдач из приложения меньше, чем
    голосовых прямо в группу (13.09 на проде — 9 против 76)."""
    db = stand.db
    group = db.get_group(stand.CHAT)
    now = db.get_now()
    today = db.get_date()
    yday = (now.date() - timedelta(days=1)).isoformat()
    # msg, телефон, дата, часов назад, стр., строка, этап
    rows = [
        # Абдулла пересдаёт стр. 3, строчку 3 (line=2): её вернули (msg 102),
        # это вторая попытка той же строки.
        (104, stand.STUDENT, today, 2, 3, 2, 1),
        (113, "777003", yday, 20, 2, 5, 1),
        # Голосовые прямо в группу — места на листе у них нет.
        (301, "777002", today, 1, None, None, None),
        (302, "777003", today, 3, None, None, None),
        (303, stand.STUDENT, today, 5, None, None, None),
        (304, "777002", today, 6, None, None, None),
        (305, "777003", today, 8, None, None, None),
        (306, stand.STUDENT, yday, 18, None, None, None),
        (307, "777002", yday, 22, None, None, None),
        (308, "777003", yday, 26, None, None, None),
    ]
    with sqlite3.connect(db.DB) as conn:
        have = {r[0] for r in conn.execute(
            "SELECT message_id FROM voice_submissions WHERE chat_id=?", (stand.CHAT,))}
    for msg, phone, date, _h, page, line, stage in rows:
        if msg in have:
            continue
        db.save_voice_submission(db.find_user_by_phone(phone)["id"], group["id"],
                                 stand.CHAT, msg, date, file_id="dev%d" % msg,
                                 hifz_page=page, hifz_line=line, hifz_stage=stage)
    # Возраст ожидания: на свежей базе всё «ждёт 0 мин», так очередь не читается.
    ages = {103: 4, 111: 7}
    ages.update({r[0]: r[3] for r in rows})
    with sqlite3.connect(db.DB) as conn:
        for msg, hours in ages.items():
            conn.execute("UPDATE voice_submissions SET sent_at=? WHERE chat_id=? AND message_id=?",
                         ((now - timedelta(hours=hours)).isoformat(), stand.CHAT, msg))
        # Длина записи (14.09.2026) - у сдач из приложения, чтобы *_now
        # показывали её так, как рисует настоящий код.
        for msg, sec in {104: 108, 103: 52, 111: 135, 113: 63}.items():
            conn.execute("UPDATE voice_submissions SET duration=? WHERE chat_id=? AND message_id=?",
                         (sec, stand.CHAT, msg))
    # Отметки онлайн-урока (14.09.2026) - точки в полосе и в месяце настоящим
    # кодом. Время записи сдвинуто на 30 часов назад: иначе правило «сутки
    # между отметками» спрячет кнопку «Я был» и снимок покажет не то.
    # Тренажёр таджвида (14.09.2026) виден только группе с заданием «j».
    db.update_group_tasks(stand.CHAT, "m,r,t,j,n")
    # Тренажёр нахва (17.09.2026): урок «Виды слова» опубликован, у 777002 -
    # 40 верных ответов первой ступени, чтобы снять слитное слово (ступень 2).
    with sqlite3.connect(db.DB) as conn:
        if not conn.execute("SELECT 1 FROM curriculum_parts WHERE topic LIKE 'أنواع الكلمة%'").fetchone():
            conn.execute(
                "INSERT INTO curriculum_parts(subject, chapter, topic, part_number, part_total,"
                " order_index, content, published_at) VALUES('n','الكلمة',"
                "'أنواع الكلمة (Виды слова)',1,1,-1,'Текст','2026-07-09')")
    stand.db.init()
    with sqlite3.connect(db.DB) as conn:
        if not conn.execute("SELECT 1 FROM nahw_answers WHERE user_id='777002'").fetchone():
            conn.executemany(
                "INSERT INTO nahw_answers(user_id, date, skill, ctype, stage, item, correct, retry)"
                " VALUES('777002','2026-09-10','kinds','ism_al',1,'1:2:1:1',1,0)", [()] * 40)
        conn.execute("DELETE FROM nahw_sessions")
        conn.execute("DELETE FROM nahw_answers WHERE user_id=?", (stand.STUDENT,))
    for phone, days_ago in ((stand.STUDENT, 1), (stand.STUDENT, 7), ("777002", 1)):
        user = db.find_user_by_phone(phone)
        if not user:
            continue
        day = (now.date() - timedelta(days=days_ago)).isoformat()
        if day[:7] == today[:7]:
            db.add_bonus(user["id"], group["id"], day, 5, "attendance", "online")
    with sqlite3.connect(db.DB) as conn:
        conn.execute("UPDATE score_events SET created_at=datetime('now','-30 hours')"
                     " WHERE category='attendance'")


# ─── предлагаемая разметка ────────────────────────────────────────────────

MOCK_CSS = """
<style>
/* Свёрнутые голосовые из группы: одна строка вместо простыни. Пунктир и
   серый — это не долг и не работа кабинета, а напоминание. */
.mk-fold {
  display: flex; align-items: center; gap: 10px; direction: ltr;
  border: 1px dashed var(--card-border); border-radius: 12px;
  padding: 11px 14px; color: var(--muted);
}
.mk-fold .t { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.mk-fold b { font-size: 13.5px; color: var(--ink); font-weight: 600; }
.mk-fold span { font-size: 12px; }
.mk-fold .go { flex: 0 0 auto; color: var(--accent); font-size: 13px; font-weight: 600; }

/* Полоса записи в проверке — тот же плеер, что у студента в разборе
   (#look-foot .player), только со своей отмоткой справа. */
#review-foot .mk-player { display: flex; align-items: center; gap: 10px; }
#review-foot .mk-player .pp {
  flex: 0 0 auto; width: 38px; height: 38px; border-radius: 50%; padding: 0;
  background: var(--accent); border: none; color: #fff; font-size: 14px;
}
#review-foot .mk-player .bar { flex: 1 1 auto; }
#review-foot .mk-player .tr {
  height: 4px; border-radius: 999px; background: var(--card-border); position: relative;
}
#review-foot .mk-player .tr i {
  position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px; background: var(--accent);
}
#review-foot .mk-player .t {
  display: flex; justify-content: space-between; font-size: 10.5px;
  color: var(--muted); margin-top: 5px; font-variant-numeric: tabular-nums;
}
#review-foot .mk-player .b10 { flex: 0 0 auto; padding: 8px 10px; }

/* После вердикта — не выход в список, а следующая сдача. */
#review-foot .mk-list { flex: 0 0 auto; }
#review-foot .mk-ok { color: var(--accent); font-weight: 700; }
#review-foot .mk-left { font-size: 11.5px; color: var(--muted); text-align: center; }

/* Замечание записано — вердикт ещё нет: без этого сдача молча остаётся в
   «Ждут», хотя устаз уверен, что закончил. */
#review-foot .mk-done { color: var(--accent); font-weight: 600; }
#review-foot .row.mk-glow button { box-shadow: 0 0 0 3px var(--accent-soft); }

/* Прошлые попытки той же строки. */
#review-foot .mk-hist {
  display: flex; flex-direction: column; gap: 6px;
  background: var(--no-soft); border-radius: 10px; padding: 8px 10px;
}
#review-foot .mk-hist .h { display: flex; gap: 8px; align-items: baseline; font-size: 12px; color: var(--muted); }
#review-foot .mk-hist .h b { color: var(--no); font-size: 12.5px; }
#review-foot .mk-hist .chips { display: flex; gap: 6px; }
#review-foot .mk-hist .chips button { flex: 1 1 0; padding: 7px 4px; font-size: 11.5px; }
.mk-prev { outline: 1.5px dashed var(--no); outline-offset: 1px; border-radius: 4px; }

/* Длина записи (14.09.2026): А - в строке времени, Б - плашкой у имени. */
.mk-dur { font-variant-numeric: tabular-nums; white-space: nowrap; }
.sub-pill.mk-durpill { font-variant-numeric: tabular-nums; }

/* Отметка онлайн-урока (14.09.2026). У студента - строка под полосой
   пропусков: название слева, действие справа, как у свёрнутых голосовых. */
.mk-lesson {
  display: flex; align-items: center; gap: 10px; direction: ltr;
  background: var(--card-bg); border: 1px solid var(--card-border);
  border-radius: 12px; padding: 10px 12px; margin: 10px 0 12px;
}
.mk-lesson .t { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.mk-lesson b { font-size: 13.5px; color: var(--ink); font-weight: 600; }
.mk-lesson span { font-size: 12px; color: var(--muted); }
.mk-lesson button {
  flex: 0 0 auto; border: 0; border-radius: 10px; padding: 9px 14px;
  background: var(--accent); color: #fff; font-size: 13px; font-weight: 600;
}
.mk-lesson .ok { flex: 0 0 auto; color: var(--accent); font-size: 13px; font-weight: 600; }
.mk-lesson button.ghost {
  background: transparent; color: var(--accent); border: 1px solid var(--accent);
}
/* У устаза - строка дат под календарём студента, дата снимается тапом. */
.mk-les-u { direction: ltr; margin-top: 12px; text-align: center; }
.mk-les-u .h { font-size: 11.5px; color: var(--muted); margin-bottom: 6px; }
.mk-les-u .chips { display: flex; gap: 6px; justify-content: center; flex-wrap: wrap; }
.mk-les-u .chip {
  font-size: 12.5px; font-weight: 600; padding: 5px 10px; border-radius: 999px;
  background: var(--accent-soft); color: var(--accent);
}
.mk-les-u .chip i { font-style: normal; opacity: .55; margin-left: 5px; }
.mk-les-u .none { font-size: 12.5px; color: var(--muted); }

/* Точка онлайн-урока (14.09.2026, мысль пользователя): под отрезком дня в
   полосе списка и под числом в календаре месяца. Одна и та же у устаза и у
   студента. */
.stu-strip.mk-has { padding-bottom: 10px; }
.stu-strip i.mk-les { position: relative; }
.stu-strip i.mk-les::after {
  content: ''; position: absolute; left: 50%; bottom: -9px;
  width: 5px; height: 5px; margin-left: -2.5px; border-radius: 50%;
  background: var(--accent);
}
.stu-cal .c.mk-les { position: relative; }
.stu-cal .c.mk-les::after {
  content: ''; position: absolute; left: 50%; bottom: 5px;
  width: 5px; height: 5px; margin-left: -2.5px; border-radius: 50%;
  background: var(--accent);
}
.stu-cal .c.d3.mk-les::after { background: #fff; }

/* Сдачи студента под его календарём. */
.mk-subs { display: flex; flex-direction: column; gap: 8px; margin-top: 16px; direction: ltr; }
.mk-subs .ustaz-group-title { margin: 0 2px 0; }
</style>
"""

MOCK_JS = """
<script>
(function () {
  var v = new URLSearchParams(location.search).get('v');
  if (!v) return;
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var $ = function (id) { return document.getElementById(id); };
  var all = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  async function openQueue() { $('dash-ustaz').click(); await wait(2200); }

  async function openReview(name, place) {
    await openQueue();
    var row = all('[data-review]').filter(function (el) {
      return el.textContent.indexOf(name) >= 0 && el.textContent.indexOf(place) >= 0;
    })[0];
    if (!row) throw new Error('нет сдачи ' + name + ' ' + place);
    row.click(); await wait(2800);
  }

  function mark(ln, idx) {
    var row = document.querySelector('#ayah-text .mushaf-line[data-line="' + ln + '"]');
    if (row && row.children[idx]) row.children[idx].click();
  }

  // Голосовые из группы уходят из списка. mode: 'fold' - одной строкой внизу,
  // 'tabs' - отдельным срезом рядом со сдачами из приложения.
  function foldGroupVoices(mode) {
    var body = $('ustaz-body');
    var voice = all('.ustaz-row', body).filter(function (el) { return !el.hasAttribute('data-review'); });
    var n = voice.length;
    voice.forEach(function (el) { el.remove(); });
    all('.ustaz-group-title', body).forEach(function (t) {
      var nx = t.nextElementSibling;
      if (!nx || !nx.classList.contains('ustaz-row')) t.remove();
    });
    var rows = all('[data-review]', body);
    // Метка «через апп» больше ничего не различает - в списке только они.
    all('.sub-pill.app', body).forEach(function (p) { p.remove(); });
    var lab = body.querySelector('#ustaz-picker span');
    if (lab) lab.textContent = lab.textContent.replace(/ждут \\d+/, 'ждут ' + rows.length);
    if (mode === 'fold') {
      var box = document.createElement('div');
      box.className = 'mk-fold';
      box.innerHTML = '<div class="t"><b>Ещё ' + n + ' голосовых в группе</b>'
        + '<span>без места на листе — ответить реплаем в Telegram</span></div>'
        + '<span class="go">Открыть ›</span>';
      var last = rows[rows.length - 1];
      last.parentNode.insertBefore(box, last.nextSibling);
    } else {
      var f = document.createElement('div');
      f.className = 'ustaz-filter';
      f.innerHTML = '<button class="on">из приложения · ' + rows.length + '</button>'
        + '<button>голосовые в группе · ' + n + '</button>';
      body.querySelector('.ustaz-head').appendChild(f);
    }
    // Вторая попытка той же строки - видно ещё в очереди.
    rows.forEach(function (el) {
      if (el.textContent.indexOf('Абдулла') >= 0 && el.textContent.indexOf('строчка 3') >= 0) {
        el.querySelector('.name').insertAdjacentHTML('beforeend',
          '<span class="sub-pill retake">2-я попытка</span>');
      }
    });
  }

  // Длина записи у каждой сдачи из приложения. mode: 'meta' - в строке
  // времени после «ждёт», 'pill' - плашкой справа от имени.
  var DUR = ['1:48', '0:52', '2:15', '1:03', '0:37', '1:21'];
  function durations(mode) {
    all('[data-review]', $('ustaz-body')).forEach(function (el, i) {
      var d = DUR[i % DUR.length];
      if (mode === 'meta') {
        var metas = all('.meta', el);
        metas[metas.length - 1].insertAdjacentHTML('beforeend',
          ' · <span class="mk-dur">⏱ ' + d + '</span>');
      } else {
        el.querySelector('.name').insertAdjacentHTML('beforeend',
          '<span class="sub-pill mk-durpill">⏱ ' + d + '</span>');
      }
    });
  }

  // Карточка в две строки: имя + длина, под ними место · время · ждёт.
  function twoLines() {
    all('[data-review]', $('ustaz-body')).forEach(function (el) {
      var metas = all('.meta', el);
      if (metas.length < 2) return;
      metas[0].innerHTML = metas[0].innerHTML + ' · ' + metas[1].innerHTML;
      metas[1].remove();
    });
  }

  // Экран «Работа с устазом» у студента: ждём, пока догрузится полоса месяца.
  async function openSubsStudent() {
    $('dash-subs').click();
    for (var i = 0; i < 30; i++) {
      var m = $('subs-month');
      if (m && m.children.length) break;
      await wait(200);
    }
    await wait(400);
  }

  function lessonCard(state) {
    var box = document.createElement('div');
    if (state === 'done') {
      box.className = 'subs-quiet';
      box.style.margin = '10px 0 12px';
      box.textContent = '✓ онлайн-урок отмечен сегодня';
    } else {
      box.className = 'mk-lesson';
      box.innerHTML = '<div class="t"><b>🕌 Онлайн-урок</b><span>отметь после урока</span></div>'
        + '<button class="ghost">Я был</button>';
    }
    var m = $('subs-month');
    m.parentNode.insertBefore(box, m.nextSibling);
  }

  // Общее окно подтверждения приложения; showConfirm живёт в замыкании
  // приложения, поэтому открываем его разметкой - вид тот же.
  function openConfirm(text) {
    $('confirm-text').textContent = text;
    $('confirm-overlay').classList.add('visible');
  }

  function lessonUstaz() {
    var legends = all('#ustaz-body .stu-legend');
    var last = legends[legends.length - 1];
    var box = document.createElement('div');
    box.className = 'mk-les-u';
    box.innerHTML = '<div class="h">онлайн-уроки за месяц · тап по дате — снять</div>'
      + '<div class="chips"><span class="chip">пн 07.09<i>✕</i></span>'
      + '<span class="chip">вс 13.09<i>✕</i></span></div>';
    last.parentNode.insertBefore(box, last.nextSibling);
  }

  // Точки урока: в полосе строки студента (i по порядку дней) и в календаре.
  function dotStrip(row, days) {
    var strip = row.querySelector('.stu-strip');
    if (!strip) return;
    strip.classList.add('mk-has');
    var cells = strip.querySelectorAll('i');
    days.forEach(function (d) { if (cells[d - 1]) cells[d - 1].classList.add('mk-les'); });
  }

  function dotCal(root, days, legend) {
    var cal = root.querySelector('.stu-cal');
    if (!cal) return;
    all('.c', cal).forEach(function (c) {
      if (days.indexOf(parseInt(c.textContent, 10)) >= 0) c.classList.add('mk-les');
    });
    var legends = all('.stu-legend', root);
    var last = legends[legends.length - 1];
    if (last && legend) last.insertAdjacentHTML('beforeend', ' · ' + legend);
  }

  async function openStudentsList() {
    await openQueue();
    document.querySelector('.ustaz-zones [data-zone="students"]').click();
    await wait(2200);
  }

  function playerBar() {
    var foot = $('review-foot');
    var p = document.createElement('div');
    p.className = 'mk-player';
    p.innerHTML = '<button class="pp">❚❚</button>'
      + '<div class="bar"><div class="tr"><i style="width:38%"></i></div>'
      + '<div class="t"><span>0:41</span><span>1:48</span></div></div>'
      + '<button class="b10">↺ 10</button>';
    foot.insertBefore(p, foot.querySelector('.row'));
    $('review-play').style.display = 'none';
    $('review-back10').style.display = 'none';
  }

  var scenes = {
    queue_now: openQueue,
    queue_fold: async function () { await openQueue(); foldGroupVoices('fold'); },
    queue_tabs: async function () { await openQueue(); foldGroupVoices('tabs'); },

    dur_meta: async function () { await openQueue(); durations('meta'); },
    dur_pill: async function () { await openQueue(); durations('pill'); },
    dur_two: async function () { await openQueue(); durations('pill'); twoLines(); },
    review_dur: async function () {
      await openReview('Абдулла', 'строчка 4'); mark(3, 2);
      // Подсказка перерисовывается после каждой пометки - длину кладём на кнопку.
      var b = $('review-play');
      b.innerHTML = b.textContent.trim() + ' <span class="mk-dur">· 1:48</span>';
    },

    review_now: async function () { await openReview('Абдулла', 'строчка 4'); mark(3, 2); },
    review_bar: async function () {
      await openReview('Абдулла', 'строчка 4'); mark(3, 2); await wait(300); playerBar();
    },
    comment_then: async function () {
      await openReview('Абдулла', 'строчка 4'); mark(3, 2); await wait(300); playerBar();
      $('review-hint').innerHTML = '<span class="mk-done">Замечание записано ✓</span> Теперь вердикт — сдача ещё в «Ждут»';
      var rows = all('#review-foot .row');
      rows[rows.length - 1].classList.add('mk-glow');
    },
    review_next: async function () {
      await openReview('Абдулла', 'строчка 4'); mark(3, 2); await wait(300);
      $('review-hint').innerHTML = '<span class="mk-ok">Принято ✅</span> Абдулла · стр. 3, строчка 4';
      var rows = all('#review-foot .row');
      rows[0].style.display = 'none';
      rows[1].innerHTML = '<button class="mk-list">К списку</button>'
        + '<button class="ok">Дальше: Хамза · стр. 4 ›</button>';
      $('review-foot').insertAdjacentHTML('beforeend',
        '<div class="mk-left">в N-1 ждут ещё 2 · группа не меняется</div>');
    },

    history_now: async function () { await openReview('Абдулла', 'строчка 3'); },
    history: async function () {
      await openReview('Абдулла', 'строчка 3');
      // Пометка с прошлой попытки (seed_submissions: строка 2, слово 4).
      var ln = document.querySelector('#ayah-text .mushaf-line[data-line="2"]');
      if (ln && ln.children[4]) ln.children[4].classList.add('mk-prev');
      var s = document.createElement('div');
      s.className = 'mk-hist';
      s.innerHTML = '<div class="h"><b>2-я попытка</b><span>пунктир — отмечено в прошлый раз</span></div>'
        + '<div class="chips"><button>▶ Прошлая запись</button><button>▶ Мой разбор тогда</button></div>';
      var foot = $('review-foot');
      foot.insertBefore(s, foot.firstChild);
    },

    les_stu_now: openSubsStudent,
    les_stu_card: async function () { await openSubsStudent(); lessonCard('todo'); },
    les_stu_confirm: async function () {
      await openSubsStudent(); lessonCard('todo');
      openConfirm('Отметить, что ты был на онлайн-уроке?');
    },
    les_stu_done: async function () { await openSubsStudent(); lessonCard('done'); },
    les_list_now: openStudentsList,
    // Тренажёры (14.09.2026) - настоящий код, без инъекций.
    tj_door: async function () { await wait(2500); },
    // «Знания» по заданиям (14.09.2026): kn_* - Юсуф из группы без таджвида
    // и нахва, tj_learn - Абдулла из группы с таджвидом.
    kn_door: async function () { await wait(2500); },
    kn_learn: async function () {
      await wait(2500); $('dash-learn').click(); await wait(1800);
    },
    tj_learn: async function () {
      await wait(2500); $('dash-learn').click(); await wait(1800);
    },
    tj_hub: async function () {
      await wait(2500); $('dash-trainer').click(); await wait(700);
    },
    tj_card: async function () {
      await scenes.tj_hub(); $('trh-tajweed').click(); await wait(1500);
    },
    // Тап по первому варианту: чаще всего мимо - красная нажатая, зелёная
    // верная и «Дальше».
    tj_answer: async function () {
      await scenes.tj_card();
      document.querySelector('.tj-opt').click(); await wait(700);
    },
    // Итог захода: тапаем по кругу, «Дальше» после ошибки, пока не кончится.
    tj_done: async function () {
      await scenes.tj_card();
      for (var i = 0; i < 90 && !$('tj-more'); i++) {
        if ($('tj-next')) { $('tj-next').click(); await wait(250); continue; }
        var opts = document.querySelectorAll('.tj-opt:not(:disabled)');
        if (opts.length) opts[i % opts.length].click();
        await wait(1000);
      }
    },
    // Тренажёр нахва (17.09.2026) - настоящий код, без инъекций.
    nh_hub: async function () {
      await wait(2500); $('dash-trainer').click(); await wait(700);
    },
    nh_card: async function () {
      await scenes.nh_hub(); $('trh-nahw').click(); await wait(1800);
    },
    // Мимо нарочно: верный ответ берём из разбора после первого тапа не
    // можем, поэтому жмём «Харф» - на первой ступени он верен реже всего.
    nh_answer: async function () {
      await scenes.nh_card();
      document.querySelector('.nh-opt[data-key="harf"]').click(); await wait(900);
    },
    nh_right: async function () {
      await scenes.nh_card();
      document.querySelector('.nh-opt[data-key="ism"]').click(); await wait(500);
    },
    // Ступень 2: листаем, пока не выпадет слитное слово.
    nh2_part: async function () {
      await scenes.nh_card();
      var part = function () { var q = document.querySelector('.nh-q'); return q && /выделенная/.test(q.textContent); };
      for (var i = 0; i < 20 && !part(); i++) {
        if ($('nh-next')) { $('nh-next').click(); await wait(600); continue; }
        var o = document.querySelector('.nh-opt:not(:disabled)');
        if (o) o.click();
        await wait(700);
      }
    },
    nh2_answer: async function () {
      await scenes.nh2_part();
      document.querySelector('.nh-opt[data-key="fil"]').click(); await wait(900);
    },
    nh_done: async function () {
      await scenes.nh_card();
      for (var i = 0; i < 120 && !$('nh-more'); i++) {
        if ($('nh-next')) { $('nh-next').click(); await wait(300); continue; }
        var opts = document.querySelectorAll('.nh-opt:not(:disabled)');
        if (opts.length) opts[i % opts.length].click();
        await wait(700);
      }
    },
    tj_words: async function () {
      await scenes.tj_hub(); $('trh-words').click(); await wait(1500);
    },
    // Настоящие экраны после выкладки - без единой инъекции.
    les_stu_real_month: async function () {
      await openSubsStudent(); $('subs-month').click(); await wait(600);
    },
    real_lesson: async function () {
      $('dash-learn').click(); await wait(1500);
      var tile = document.querySelector('[data-subj="j"]');
      if (tile) { tile.click(); await wait(1500); }
      var item = document.querySelector('[data-lesson]');
      if (item) { item.click(); await wait(1800); }
    },
    // «Было»: прежние размеры поверх того же урока - для сравнения.
    real_lesson_old: async function () {
      await scenes.real_lesson();
      var st = document.createElement('style');
      st.textContent = '#learn-body .k-text{font-size:14px;line-height:1.55;padding:14px 16px 18px}'
        + '#learn-body .k-text .k-chapter{font-size:11.5px}#learn-body .k-text .k-ar{font-size:1em}';
      document.head.appendChild(st);
    },
    les_list: async function () {
      await openStudentsList();
      var plan = [[7, 13], [7], [], [13]];
      all('#ustaz-body .stu-row').forEach(function (row, i) { dotStrip(row, plan[i % plan.length]); });
      var legends = all('#ustaz-body > .stu-legend');
      var last = legends[legends.length - 1];
      if (last) last.insertAdjacentHTML('beforeend', '<br>• под днём — был на онлайн-уроке');
    },
    les_cal: async function () {
      await scenes.student_now();
      dotCal($('ustaz-body'), [7, 13], '• онлайн-урок, тап по дню — снять');
    },
    les_cal_confirm: async function () {
      await scenes.student_now();
      dotCal($('ustaz-body'), [7, 13], '• онлайн-урок, тап по дню — снять');
      openConfirm('Снять отметку урока за вс 13.09 у Абдуллы?');
    },
    les_stu_month: async function () {
      await openSubsStudent(); lessonCard('done');
      $('subs-month').click(); await wait(500);
      dotCal($('subs-month'), [7, 13], '• онлайн-урок');
    },
    les_u: async function () { await scenes.student_now(); lessonUstaz(); },
    les_u_confirm: async function () {
      await scenes.student_now(); lessonUstaz();
      openConfirm('Снять отметку урока за вс 13.09 у Абдуллы?');
    },

    student_now: async function () {
      await openQueue();
      document.querySelector('.ustaz-zones [data-zone="students"]').click(); await wait(2200);
      var r = all('.stu-row').filter(function (el) { return el.textContent.indexOf('Абдулла') >= 0; })[0];
      if (r) { r.click(); await wait(2000); }
    },
    student_subs: async function () {
      await scenes.student_now();
      var row = function (place, pill, meta, note) {
        return '<div class="sub-row open"><div class="top"><span class="place">' + place + '</span>'
          + '<span class="sub-pill ' + pill[0] + '">' + pill[1] + '</span></div>'
          + (meta ? '<div class="meta">' + meta + '</div>' : '')
          + (note || '') + '</div>';
      };
      $('ustaz-body').insertAdjacentHTML('beforeend',
        '<div class="mk-subs"><div class="ustaz-group-title">Сдачи за 7 дней</div>'
        + row('стр. 3, строчка 3', ['wait', 'ждёт'], 'сегодня · 2-я попытка')
        + row('стр. 3, строчка 4', ['wait', 'ждёт'], 'сегодня')
        + row('стр. 3, строчка 3', ['retake', 'на пересдачу'], 'Отмечено слов: 1 · разбор голосом',
              '<div class="note answered">пересдал — новая запись в «Ждут»</div>')
        + row('стр. 3, строчка 2', ['done', 'принято'], 'Отмечено слов: 2 · разбор голосом')
        + '</div>');
    }
  };

  window.addEventListener('load', function () {
    setTimeout(function () {
      var fn = scenes[v];
      if (!fn) throw new Error('нет такого варианта: ' + v);
      fn();
    }, 1200);
  });
})();
</script>
"""

VARIANTS = ["nh_hub", "nh_card", "nh_answer", "nh_right", "nh2_part", "nh2_answer", "nh_done",
            "kn_door", "kn_learn", "tj_learn", "tj_door", "tj_hub", "tj_card", "tj_answer", "tj_done", "tj_words",
            "les_stu_real_month", "real_lesson", "real_lesson_old",
            "les_stu_now", "les_stu_card", "les_stu_confirm", "les_stu_done", "les_stu_month",
            "les_list_now", "les_list", "les_cal", "les_cal_confirm",
            "queue_now", "queue_fold", "queue_tabs", "dur_meta", "dur_pill", "dur_two", "review_dur",
            "review_now", "review_bar", "comment_then", "review_next",
            "history_now", "history",
            "student_now", "student_subs"]

# Сравнения: первым всегда «как сейчас».
COMPARE = {
    "knowledge": [("kn_door", "Без предметов · дашборд"), ("kn_learn", "Без предметов · Знания"),
                  ("tj_door", "С таджвидом · дашборд"), ("tj_learn", "С таджвидом · Знания")],
    "nahw": [("tj_door", "Дашборд"), ("nh_hub", "Тренажёры"), ("nh_card", "Карточка"),
             ("nh_answer", "Мимо"), ("nh2_part", "Слитное слово"), ("nh2_answer", "Разбор частей"),
             ("nh_done", "Итог захода")],
    "tajweed": [("tj_door", "Дашборд"), ("tj_hub", "Тренажёры"),
                ("tj_card", "Карточка"), ("tj_answer", "После ответа"), ("tj_done", "Итог захода")],
    "lesson_real": [("les_stu_now", "Студент"), ("les_stu_real_month", "Свой месяц"),
                    ("les_list_now", "Устаз · список"), ("student_now", "Устаз · месяц")],
    "lesson_font": [("real_lesson_old", "Было · 14px"), ("real_lesson", "Стало · 17px")],
    "lesson_student": [("les_stu_now", "Сейчас"), ("les_stu_card", "Строка урока"),
                       ("les_stu_confirm", "Тап · переспрос"), ("les_stu_done", "Отмечено"),
                       ("les_stu_month", "Свой месяц · точки")],
    # Точка ПОД полосой, а не в самих черточках (14.09.2026, уточнение
    # пользователя): черточки - сдачи по заданиям, урок рядом, но отдельно.
    "lesson_ustaz": [("les_list_now", "Сейчас · студенты"), ("les_list", "Точка под полосой"),
                     ("les_cal", "Месяц · точка"), ("les_cal_confirm", "Тап по дню · снять")],
    "duration": [("queue_now", "Сейчас"), ("dur_meta", "А · в строке времени"),
                 ("dur_pill", "Б · плашкой у имени"), ("dur_two", "В · две строки")],
    "review_dur": [("review_now", "Сейчас"), ("review_dur", "Длина в шапке разбора")],
    "queue": [("queue_now", "Сейчас"), ("queue_fold", "А · голосовые одной строкой"),
              ("queue_tabs", "Б · голосовые отдельным срезом")],
    "review": [("review_now", "Сейчас"), ("review_bar", "Полоса записи"),
               ("comment_then", "Замечание есть — ждём вердикт"),
               ("review_next", "После вердикта — дальше")],
    "history": [("history_now", "Сейчас · 2-я попытка"), ("history", "Прошлая попытка рядом")],
    "student": [("student_now", "Сейчас"), ("student_subs", "Календарь + его сдачи")],
}


def page(variant):
    # Стили макета безвредны и для *_now: их классы появляются только из
    # сцен-предложений, «как сейчас» ничего не дорисовывает.
    if variant.startswith("kn_"):
        return stand.dev_index("777004", "Юсуф") + MOCK_CSS + MOCK_JS
    if variant.startswith("nh2_"):
        return stand.dev_index("777002", "Хамза") + MOCK_CSS + MOCK_JS
    if variant.startswith(("les_stu", "tj_", "nh_")):
        return stand.dev_index(stand.STUDENT, "Абдулла") + MOCK_CSS + MOCK_JS
    return stand.dev_index(stand.USTAZ, "Устаз") + MOCK_CSS + MOCK_JS


def build():
    app = stand.build_app()
    seed_extra()

    async def variant_page(request):
        return web.Response(text=page(request.query.get("v", "queue_now")),
                            content_type="text/html")

    async def variant_frame(request):
        v = request.query.get("v", "queue_now")
        w = int(request.query.get("w", WIDTH))
        return web.Response(content_type="text/html", text=(
            "<style>html,body{margin:0;background:#fff}"
            "iframe{border:0;display:block;width:%dpx;height:%dpx}</style>"
            "<iframe src='/v?v=%s&bot=male'></iframe>" % (w, HEIGHT, v)))

    app.router.add_get("/v", variant_page)
    app.router.add_get("/vframe", variant_frame)
    return app


def compose():
    from PIL import Image, ImageDraw, ImageFont
    font = None
    for path in (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"):
        if pathlib.Path(path).exists():
            font = ImageFont.truetype(path, 17)
            break
    font = font or ImageFont.load_default()
    band, gap = 40, 14
    for name, items in COMPARE.items():
        shots = [Image.open(OUT / ("u_%s.png" % v)).convert("RGB") for v, _ in items]
        w = sum(s.width for s in shots) + gap * (len(shots) - 1)
        h = band + max(s.height for s in shots)
        canvas = Image.new("RGB", (w, h), (236, 232, 222))
        draw = ImageDraw.Draw(canvas)
        x = 0
        for shot, (_v, label) in zip(shots, items):
            draw.text((x + 12, 10), label, fill=(40, 40, 40), font=font)
            canvas.paste(shot, (x, band))
            x += shot.width + gap
        jpg = OUT / ("cmp_%s.jpg" % name)
        canvas.save(jpg, "JPEG", quality=82, optimize=True)
        print("  cmp_%-8s %4d КБ" % (name, jpg.stat().st_size // 1024))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    app = build()
    if args.serve:
        print("стенд: http://127.0.0.1:%d/vframe?v=queue_fold" % PORT)
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
        png = OUT / ("u_%s.png" % name)
        subprocess.run([
            chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--window-size=%d,%d" % (WIDTH, HEIGHT),
            "--virtual-time-budget=%d" % (90000 if name in ("tj_done", "nh_done", "nh2_part", "nh2_answer")
                                          else 17000),
            "--screenshot=%s" % png,
            "http://127.0.0.1:%d/vframe?v=%s" % (PORT, name),
        ], check=True, capture_output=True)
        if not png.exists():
            raise SystemExit("вариант %s не снялся" % name)
        print("  %-13s %4d КБ" % (name, png.stat().st_size // 1024))
    compose()
    print("снимки в %s" % OUT)


if __name__ == "__main__":
    main()
