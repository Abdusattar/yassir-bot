  /* ─── Прослушать Хусари (Muallim) — вкл/выкл (02.09.2026) ─────────────
     Играет ТЕКУЩУЮ единицу (строку/половину/страницу) по кругу с паузой
     между повторами, пока не выключат — тот же принцип, что и текстовые
     40 повторов, только на слух. Один <audio> на всё приложение и на оба
     места, где есть кнопка (страница и «Крупно») — они делят одно и то
     же состояние: открыл «Крупно» во время прослушки — звук не дёрнется,
     это та же единица.

     Имена файлов совпадают с scripts/generate_hifz_audio.py 1:1 - смена
     схемы там требует смены и здесь. Сгенерировано пока только для
     стр. 2-106 (пилот) - на прочих страницах play() получит 404 и кнопка
     сама молча выключится, ничего не обещая. */
  var HIFZ_LISTEN_PAUSE_MS = 1200;
  var HUSARY_AUDIO_VER = 2;
  var hifzListenAudio = new Audio();
  var hifzListenTimer = null;
  var hifzListening = false;

  function hifzAudioSlot() {
    // Порт group_slot() из generate_hifz_audio.py - должен давать то же
    // имя, что и генератор, иначе кнопка будет играть не ту единицу.
    if (hifz.stage === 3) return 'full';
    if (hifz.stage === 2) return hifzHalf(hifz.line) === 0 ? 'first_half' : 'second_half';
    var n = hifzTextLines().length, mid = Math.floor(n / 2);
    // Склеенная единица стр. 1-2 звучит файлом предпоследней строки: в нём
    // поглощённая строка уже есть как переход (05.11.2026).
    var ul = hifz.stage === 1 ? hifzUnitLine(hifz.line) : hifz.line;
    return ul < mid ? ('first_' + ul) : ('second_' + (ul - mid));
  }

  function hifzAudioUrl() {
    var page = ('000' + currentPage).slice(-3);
    // ?v - версия нарезки: 21.09.2026 файлы пересобраны без щелчков на
    // краях под теми же именами, а сервер не шлёт Cache-Control - без
    // метки телефон ещё дни играл бы старое из кэша. Пересобрали снова -
    // поднять число.
    // Египетская раскладка - своя нарезка (audio/husary_dm, 23.09.2026):
    // строки у неё другие, а совпавшие с мединскими единицы на сервере -
    // ссылки на те же файлы.
    return 'audio/' + (pageLayout() === 'dm' ? 'husary_dm' : 'husary') + '/page_' + page + '_' +
      hifzAudioSlot() + '.mp3?v=' + HUSARY_AUDIO_VER;
  }

  function hifzListenButtons() {
    var btns = document.querySelectorAll('.hifz-listen-btn');
    Array.prototype.forEach.call(btns, function (b) {
      b.classList.toggle('on', hifzListening);
      b.title = hifzListening ? T('hifz_listen_stop') : T('hifz_listen');
    });
  }

  function hifzListenStop() {
    if (hifzListenTimer) { clearTimeout(hifzListenTimer); hifzListenTimer = null; }
    hifzListening = false;
    hifzListenAudio.pause();
    hifzListenButtons();
  }

  function hifzListenPlayOnce() {
    hifzListenAudio.src = hifzAudioUrl();
    hifzListenAudio.play().catch(function () {
      // Файла нет (страница вне пилота) или автоплей запрещён - тихо
      // выключаем, без надписи об ошибке поверх мусхафа.
      hifzListenStop();
    });
  }
  hifzListenAudio.addEventListener('ended', function () {
    if (!hifzListening) return;
    hifzListenTimer = setTimeout(hifzListenPlayOnce, HIFZ_LISTEN_PAUSE_MS);
  });
  hifzListenAudio.addEventListener('error', function () {
    if (hifzListening) hifzListenStop();
  });

  function hifzListenToggle() {
    if (hifzListening) { hifzListenStop(); return; }
    hifzListening = true;
    hifzListenButtons();
    hifzListenPlayOnce();
  }
  document.getElementById('hifz-listen-btn').addEventListener('click', hifzListenToggle);
  document.getElementById('hifz-big-listen-btn').addEventListener('click', hifzListenToggle);

  // Перевод под словами лёжа (19.10.2026): по умолчанию включён - ради него
  // и сделан; выбор помнит телефон.
  var GLOSS_KEY = 'yassir_hifz_gloss';
  function glossApply(on) {
    document.getElementById('app').classList.toggle('gloss', on);
    ['hifz-gloss-btn', 'read-gloss-btn'].forEach(function (id) {
      document.getElementById(id).setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }
  (function () {
    var v = null;
    try { v = localStorage.getItem(GLOSS_KEY); } catch (e) {}
    glossApply(v !== '0');
  })();
  ['hifz-gloss-btn', 'read-gloss-btn'].forEach(function (id) {
    document.getElementById(id).addEventListener('click', function () {
      var on = !document.getElementById('app').classList.contains('gloss');
      glossApply(on);
      try { localStorage.setItem(GLOSS_KEY, on ? '1' : '0'); } catch (e) {}
      trail('gloss', { on: on ? 1 : 0, where: id === 'read-gloss-btn' ? 'read' : 'hifz' });
    });
  });

  // Подписи одним рядом (30.10.2026, пользователь: «переводы пошли вниз
  // строк» - лесенка 29.10 опускала наехавшую подпись ниже, читать было
  // трудно). Теперь каждая подпись остаётся под своим словом: рамка - по
  // ширине текста (не уже слова, не шире 8.5em); если соседям тесно, место
  // между ними делится - кому нужно меньше, берёт своё, другому остаток, -
  // и подпись сужается, переносясь (мягкие переносы - glossText) на
  // сколько нужно строк - без обрезки (пользователь: «обрезов не должно быть»). Подпись по центру слова; у края строки - прижата к краю.
  // Под строкой - столько места, сколько строк у самой высокой подписи.
  var GLOSS_GAP = 4;
  var glossCtx = null, glossQueued = false;
  function glossInk(text, cs, fs) {
    if (!glossCtx) glossCtx = document.createElement('canvas').getContext('2d');
    glossCtx.font = cs.fontWeight + ' ' + fs + 'px ' + cs.fontFamily;
    text = text.replace(/­/g, '');
    var ls = parseFloat(cs.letterSpacing) || 0;
    return glossCtx.measureText(text).width + ls * text.length;
  }
  function glossSet(el, name, v) {
    if (el.style.getPropertyValue(name) !== v) {
      if (v) el.style.setProperty(name, v); else el.style.removeProperty(name);
    }
  }
  function glossFitRow(row, on) {
    var spans = row.querySelectorAll(':scope > span[data-gl]');
    var rr = row.getBoundingClientRect(), g = [];
    for (var i = 0; i < spans.length; i++) {
      var sp = spans[i];
      var cs = on ? getComputedStyle(sp, '::after') : null;
      var r = cs && cs.content !== 'none' ? sp.getBoundingClientRect() : null;
      if (!(r && r.width)) { glossSet(sp, '--gl-w', ''); glossSet(sp, '--gl-x', ''); continue; }
      var fs = parseFloat(cs.fontSize), t = glossInk(sp.getAttribute('data-gl'), cs, fs);
      var want = Math.min(Math.max(t + 1, r.width), 8.5 * fs);
      var mid = r.left + r.width / 2;
      // У края строки рамка прижата к краю - считаем от её центра.
      var c = Math.max(rr.left + want / 2, Math.min(mid, rr.right - want / 2));
      g.push({ sp: sp, mid: mid, c: c, h: want / 2, lo: rr.left, hi: rr.right, fs: fs, cs: cs, t: t });
    }
    g.sort(function (x, y) { return x.c - y.c; });
    // Граница между соседями: тесно - кому нужно меньше, берёт своё.
    for (var j = 1; j < g.length; j++) {
      var a = g[j - 1], b = g[j], d = b.c - a.c - GLOSS_GAP;
      if (a.h + b.h <= d) continue;
      var pa = a.h <= d / 2 ? a.h : b.h <= d / 2 ? d - b.h : d / 2;
      a.hi = Math.min(a.hi, a.c + pa);
      b.lo = Math.max(b.lo, a.c + pa + GLOSS_GAP);
    }
    var lines = 0;
    for (var k = 0; k < g.length; k++) {
      var q = g[k], first = k === 0, last = k === g.length - 1;
      // По центру: ширина - вдвое меньшее из расстояний до границ. Крайней
      // подписи всё место до края строки - её: рамка сдвинется к краю.
      var w = first || last ? Math.min(2 * q.h, q.hi - q.lo) :
        Math.min(2 * q.h, 2 * (q.c - q.lo), 2 * (q.hi - q.c));
      w = Math.max(w, 2.4 * q.fs);
      var c2 = Math.max(q.lo + w / 2, Math.min(q.mid, q.hi - w / 2));
      c2 = Math.max(rr.left + w / 2, Math.min(c2, rr.right - w / 2));
      glossSet(q.sp, '--gl-w', w.toFixed(1) + 'px');
      glossSet(q.sp, '--gl-x', Math.abs(c2 - q.mid) > 0.5 ? (c2 - q.mid).toFixed(1) + 'px' : '');
      // Строк подписи: рамка уже такой ширины - высота от браузера (точно),
      // иначе прикидка; поменяли ширину - наблюдатель позовёт ещё раз.
      var lh = parseFloat(q.cs.lineHeight) || 1.18 * q.fs, H = parseFloat(q.cs.height);
      lines = Math.max(lines, Math.abs(parseFloat(q.cs.width) - w) < 1 && H > 0 ?
        Math.round(H / lh) : Math.ceil(q.t / (w * 0.9)));
    }
    glossSet(row, '--gl-extra', lines > 2 ? String(lines - 2) : '');
  }
  function glossStagger() {
    glossQueued = false;
    var app = document.getElementById('app');
    var on = app.classList.contains('gloss') && app.classList.contains('land');
    var rows = document.querySelectorAll('#ayah-text .mushaf-line, #ayah-text .hifz-xtail');
    for (var i = 0; i < rows.length; i++) glossFitRow(rows[i], on);
  }
  function glossStaggerSoon() {
    if (glossQueued) return;
    glossQueued = true;
    requestAnimationFrame(glossStagger);
  }
  // Перерисовка листа, смена строки заучивания, подгонка кегля (style),
  // поворот, кнопка «ب/а» - всё это видно как мутация или resize. Свои
  // правки (--gl-w, --gl-x, --gl-extra) тоже будят наблюдателя, но второй проход
  // ничего не меняет, и круг замыкается.
  if (window.MutationObserver) {
    var glossMo = new MutationObserver(glossStaggerSoon);
    glossMo.observe(document.getElementById('ayah-text'), { childList: true, subtree: true,
      attributes: true, attributeFilter: ['class', 'style'] });
    glossMo.observe(document.getElementById('app'), { attributes: true, attributeFilter: ['class'] });
  }
  window.addEventListener('resize', glossStaggerSoon);
  if (document.fonts && document.fonts.addEventListener) document.fonts.addEventListener('loadingdone', glossStaggerSoon);

  function hifzExit() {
    // Проверка сдачи закрывается своей дорогой - обратно в кабинет устаза,
    // а не в обычное чтение (04.09.2026).
    if (review.on) { reviewClose(); return; }
    // Разбор - тоже: студент пришёл из «Сдач» и возвращается туда же
    // (07.09.2026). Без этого ✕ высаживал бы его в чтение мусхафа, откуда
    // до своего списка сдач надо идти через дашборд.
    if (look.on) { lookClose(); return; }
    // Выход из режима во время пересдачи (см. subsRetake) обязан вернуть
    // указатель на место, где студент был до неё, и снять сам признак
    // пересдачи - иначе следующая ОБЫЧНАЯ сдача не сдвинула бы указатель.
    if (hifzRetakeMode) {
      hifzRetakeMode = false;
      var backPage = hifzRetakeSaved && hifzRetakeSaved.page;
      if (hifzRetakeSaved) {
        hifz.line = hifzRetakeSaved.line;
        hifz.stage = hifzRetakeSaved.stage;
        hifzRetakeSaved = null;
      }
      // Пересдача шла на листе долга в его раскладке (28.10.2026) - выйдя,
      // студент читает дальше в своей.
      if (dropViewLayout()) loadPage(backPage || currentPage);
    }
    // Вышел ✕ посреди выбора места - место осталось прежним, и об этом надо
    // сказать (13.09.2026, Муслим из Н-1): молчаливый выход читался как
    // «сохранилось», а 📖 потом вёл на старую страницу.
    var cancelled = hifz.picking && hifzPointerPage;
    trail('exit', { p: currentPage, n: cancelled ? 'cancel' : (hifz.picking ? 'pick' : '') });
    hifz.on = false; hifz.picking = false; hifz.unit = 'line';
    hifzListenStop();
    document.getElementById('hifz-big').classList.remove('visible');
    hifzApply();
    if (cancelled) hifzNote(T('hifz_pick_cancel'));
  }

  // Короткая плашка внизу листа, сама уходит. Одна на всё приложение.
  var hifzNoteTimer = null;
  function hifzNote(text, ms, small) {
    var el = document.getElementById('hifz-note');
    if (!el) {
      el = document.createElement('div');
      el.id = 'hifz-note';
      document.body.appendChild(el);
    }
    el.textContent = text;
    if (small) {
      var sm = document.createElement('small');
      sm.textContent = small;
      el.appendChild(sm);
    }
    el.classList.add('visible');
    if (hifzNoteTimer) clearTimeout(hifzNoteTimer);
    hifzNoteTimer = setTimeout(function () { el.classList.remove('visible'); }, ms || 2500);
  }

  /* Следующий шаг методики. Порядок жёсткий, отказа нет: метод 40+40 не
     предусматривает возврата (решение пользователя 01.09.2026). */
  /* Куда шагнём. Считаем ДО того, как двинуть указатель: от этого зависит,
     не упрётся ли шаг в стену пересдачи. Вынесено из hifzNext 20.09.2026 -
     то же место называет подпись кнопки «Дальше: …» в панели повторов. */
  function hifzNextPosition() {
    var to = { line: hifz.line, stage: hifz.stage, page: currentPage };
    if (hifz.stage === 1) {
      var half = hifzHalf(hifz.line), r = hifzHalfRange(half);
      // Поглощённая последняя строка - не своя единица (05.11.2026).
      var end = hifzAbsorbed() === r[1] ? r[1] - 1 : r[1];
      if (hifz.line < end) to.line = hifz.line + 1;
      else to.stage = 2;                           // строчки половины закончились
    } else if (hifz.stage === 2) {
      if (hifzHalf(hifz.line) === 0) {             // первая половина сдана
        to.line = hifzHalfRange(1)[0];
        to.stage = 1;
      } else {
        to.stage = 3;                              // обе половины сданы
      }
    } else if (currentPage < LAST_PAGE) {          // страница закрыта — дальше
      to.stage = 1; to.line = 0; to.page = currentPage + 1;
    }
    return to;
  }

  function hifzNext() {
    var to = hifzNextPosition();

    /* Стена пересдачи (13.09.2026, решение пользователя). Внутри этапа строки
       идут свободно - долг не мешает доделать то, что начал. Закрыта СМЕНА
       этапа (1->2, 2->3, 3->следующая страница): пока висит долг, вперёд хода
       нет. Проверяем ДО шага, потому что блок должен встречать человека до
       работы, а не после начитанных 40+40 (случай пользователя 12.09).

       Настоящую стену держит сервер (handle_hifz_set): локальное состояние
       можно перезагрузить. Здесь - чтобы не вести к заведомо мёртвому шагу. */
    if (hifzDebt.retakes.length &&
        (to.stage !== hifz.stage || to.page !== currentPage)) {
      hifzDebt.done = true;       // своё место доработано, дальше только долг
      hifzExit();
      openSubs(true);
      return;
    }

    hifzListenStop();  // единица меняется - старая запись больше не подходит
    hifz.line = to.line;
    hifz.stage = to.stage;
    if (to.page !== currentPage) {
      loadPage(to.page);
      hifzSave();
      return;
    }
    hifzApply();
    hifzSave();
  }
  document.getElementById('btn-hifz').addEventListener('click', function () {
    if (hifz.on) { hifzExit(); return; }
    trail('enter', { p: currentPage });
    // Указатель тянется с сервера асинхронно (см. apiCall('/hifz') ниже) -
    // если тапнуть по 📖 быстро после открытия приложения, ответ может ещё
    // не прийти: hifz.line всё ещё null, и режим решит, что указателя нет
    // вообще, хотя он есть. Реальный случай (02.09.2026, сын пользователя,
    // Залкар): один раз указал строку, в другой раз открыл — снова
    // спросило. Ждём ответ (с потолком на случай плохой связи), и только
    // потом решаем, спрашивать строку или нет.
    hifzPointerReady().then(function () {
      /* Ход закрыт - вести человека на его место незачем: работать там уже
         нечего, он намотает 40+40 на сданной единице и упрётся только в
         конце (случай пользователя 13.09: «а он уже поработал над новым»).
         Ведём сразу туда, где долги лежат по порядку и объяснены. */
      if (hifzWall()) { openSubs(true); return; }
      hifzEnter();
      // Место уже есть (не выбор) - подсказать про поворот. Чуть позже: лист
      // мог уехать на другую страницу, плашка не должна мелькнуть до него.
      setTimeout(function () { if (hifz.on && !hifz.picking) rotateHintMaybe(); }, 700);
    });
  });
  document.getElementById('hifz-close').addEventListener('click', hifzExit);
  document.getElementById('hifz-fix').addEventListener('click', function () {
    // «Поправить» — тот же экран выбора, значит и та же панель единиц:
    // менять можно не только строку, но и этап (02.09.2026).
    trail('fix', { p: currentPage, l: hifz.line, s: hifz.stage });
    hifz.picking = true; hifz.unit = 'line'; hifzApply(); hifzHead();
  });

  // Выбор строчки тапом прямо по странице — спрашивается один раз, дальше
  // режим ведёт сам; вернуться сюда можно всегда через «поправить».
  document.getElementById('ayah-text').addEventListener('click', function (e) {
    if (!hifz.on || !hifz.picking) return;
    var row = e.target.closest ? e.target.closest('.mushaf-line') : null;
    if (!row) return;
    e.stopPropagation();
    /* Тап по листу, которого уже нет (13.09.2026). Человек вводит номер
       страницы и убирает клавиатуру тапом по листу: blur → loadPage сразу
       ставит currentPage новым номером, а под пальцем ещё текст старой
       страницы - и строка старого листа сохранялась как место на новом
       («стр. 52, строка 1», которую никто не выбирал). Поймано пробой на
       стенде, пока разбирали случай Муслима из Н-1. Тап засчитываем только
       когда на экране уже тот лист, что в шапке (data-page ставит reveal). */
    if (parseInt(this.getAttribute('data-page'), 10) !== currentPage) return;
    var idx = parseInt(row.getAttribute('data-line'), 10);
    if (idx >= hifzTextLines().length) return;   // пустая заглушка стр. 1-2
    if (hifz.unit === 'half') {
      // Тапнул по любой строке половины — значит выбрал ЭТУ половину.
      // Указатель ставим на её первую строку: этап 2 определяет половину
      // через hifzHalf(line), поэтому строка обязана лежать внутри неё.
      hifz.line = hifzHalfRange(hifzHalf(idx))[0];
      hifz.stage = 2;
    } else {
      hifz.line = idx === hifzAbsorbed() ? idx - 1 : idx;   // склейка стр. 1-2
      hifz.stage = 1;
    }
    trail('pick', { p: currentPage, l: hifz.line, s: hifz.stage });
    hifzPickDone();
  }, true);

  /* Конец выбора: единица возвращается к строке (иначе следующий вход в
     «поправить» открылся бы в режиме половины, чего студент не просил). */
  function hifzPickDone() {
    hifz.picking = false;
    hifz.unit = 'line';
    hifzListenStop();
    hifzApply();
    hifzSave();
  }

  document.getElementById('hifz-units').addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('button[data-unit]') : null;
    if (!b || !hifz.picking) return;
    var unit = b.getAttribute('data-unit');
    trail('unit', { p: currentPage, n: unit });
    if (unit === 'page') {
      // Вся страница — выбирать больше нечего, место уже однозначно.
      hifz.line = 0;
      hifz.stage = 3;
      hifzPickDone();
      return;
    }
    hifz.unit = unit;
    hifzApply();
    hifzHead();
  });

  // «Крупно» — та же строчка и тот же переход, только крупнее.
  function hifzBigRender() {
    var lines = hifzTextLines(), line = lines[hifz.line];
    var src = hifzTailLine(hifz.line);
    var next = src && src.line;
    if (!line) return;
    var html = '';
    line.tokens.forEach(function (t) {
      html += hifzBigWord(t, false);
    });
    var tail = hifzTailTokens(hifz.line);
    for (var i = 0; i < tail && next && i < next.tokens.length; i++) {
      // Тот же капкан с чужим шрифтом, что и в подсказке ниже страницы.
      html += '<span class="hifz-tail">' + hifzBigWord(next.tokens[i], src.foreign) + '</span>';
    }
    var box = document.getElementById('hifz-big-words');
    box.innerHTML = html;
    document.getElementById('hifz-big-where').textContent =
      document.getElementById('hifz-where').textContent;
    // Кегль подбираем под область: строка может лечь в два-три ряда, это
    // нормально — цель «удобно читать глядя», а не «уместить в одну строку».
    var area = box.parentNode;
    var size = 46;
    box.style.width = (area.clientWidth - 20) + 'px';
    while (size > 18) {
      box.style.fontSize = size + 'px';
      if (box.scrollHeight <= area.clientHeight - 12) break;
      size -= 1;
    }
  }
  document.getElementById('hifz-big-words').addEventListener('click', function (e) {
    var el = e.target.closest ? e.target.closest('[data-tr]') : null;
    if (el) showWordPopup(el);
  });
  document.getElementById('hifz-big-close').addEventListener('click', function () {
    document.getElementById('hifz-big').classList.remove('visible');
  });

