  // ── Смысловой перевод (02.11.2026, решения пользователя) ─────────────
  // 1) Удержание на аяте (полсекунды) - панель со смыслом ВСЕГО аята, в
  //    чтении, повторении и заучивании. Тап (перевод слова) и двойной тап
  //    («Мои слова») не задеты: после удержания следующий click гасится
  //    целиком, в фазе захвата - разом для всех обработчиков #ayah-text.
  //    У устаза в проверке удержания нет: там касание - пометка ошибки.
  // 2) 📜 - отдельное чтение смысла, «живёт своей жизнью»: своё место
  //    (сура:аят верхнего аята, не пиксели - Абу Адель вдвое длиннее
  //    Кулиева), на сервере по пользователю (/api/muf/meaning_pos) - у
  //    Telegram и иконки на экране «Домой» разный localStorage. С местом
  //    заучивания не связано никак.
  // Перевод: у русского - Кулиев или Абу Адель (переключатель прямо в окне
  // и в настройках, выбор общий), у ky/uz/zh - свой единственный.
  // Данные: mushaf_data/meaning/<перевод>/<сура>.json (scripts/build_meaning_reader.py).
  var MEANING_VER = '1';
  var MTR_KEY = 'yassir_meaning_tr';
  var MPOS_KEY = 'yassir_meaning_pos';
  var MEANING_HOLD_MS = 500;
  var mtrRu = 'ru_kuliev';
  try { if (localStorage.getItem(MTR_KEY) === 'ru_abuadel') mtrRu = 'ru_abuadel'; } catch (e) {}

  function meaningSrc() {
    return UI_LANG === 'ru' ? mtrRu : (UI_LANG === 'ky' || UI_LANG === 'uz' || UI_LANG === 'zh' ? UI_LANG : 'ru_kuliev');
  }
  var meaningCache = {};
  function meaningSurah(src, s) {
    var key = src + '/' + s;
    if (!meaningCache[key]) {
      meaningCache[key] = fetch('meaning/' + key + '.json?v=' + MEANING_VER)
        .then(function (r) { if (!r.ok) throw new Error('meaning ' + key); return r.json(); })
        .then(function (d) { return d.t || []; });
      meaningCache[key].catch(function () { delete meaningCache[key]; });
    }
    return meaningCache[key];
  }
  function surahRow(s) { return SURAH_INDEX[s - 1]; }

  // Переключатели переводчика: в панели, в чтении, в настройках - один выбор.
  function mrMarkSeg() {
    var ru = UI_LANG === 'ru';
    ['as-seg', 'mr-seg'].forEach(function (id) { document.getElementById(id).hidden = !ru; });
    document.getElementById('sett-mtr-card').hidden = !ru;
    Array.prototype.forEach.call(
      document.querySelectorAll('#as-seg button, #mr-seg button, #sett-mtr button'),
      function (b) { b.classList.toggle('on', b.getAttribute('data-mtr') === mtrRu); });
  }
  function setMtr(tr) {
    if (tr !== 'ru_abuadel') tr = 'ru_kuliev';
    if (tr === mtrRu) return;
    mtrRu = tr;
    try { localStorage.setItem(MTR_KEY, tr); } catch (e) {}
    trail('mtr', { tr: tr });
    mrMarkSeg();
    if (!document.getElementById('ayah-sheet').hidden) sheetShow();
    if (!document.getElementById('mreader').hidden) mrRender(mrTopAyah());
  }
  ['as-seg', 'mr-seg', 'sett-mtr'].forEach(function (id) {
    document.getElementById(id).addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (b) setMtr(b.getAttribute('data-mtr'));
    });
  });
  mrMarkSeg();

  // ── Панель аята ──
  var sheetAt = null;   // {s, a}
  function sheetHighlight() {
    Array.prototype.forEach.call(document.querySelectorAll('#ayah-text .ma-hl, #hifz-big-words .ma-hl'),
      function (el) { el.classList.remove('ma-hl'); });
    if (!sheetAt) return;
    Array.prototype.forEach.call(
      document.querySelectorAll('#ayah-text [data-ma="' + sheetAt.s + ':' + sheetAt.a + '"], ' +
        '#hifz-big-words [data-ma="' + sheetAt.s + ':' + sheetAt.a + '"]'),
      function (el) { el.classList.add('ma-hl'); });
  }
  function sheetShow() {
    if (!sheetAt) return;
    var at = sheetAt, src = meaningSrc();
    var row = surahRow(at.s);
    document.getElementById('as-ref').innerHTML =
      '<bdi class="ar" dir="rtl">' + row[1] + '</bdi> ' + at.s + ':' + at.a;
    var text = document.getElementById('as-text');
    text.textContent = T('mr_loading');
    meaningSurah(src, at.s).then(function (t) {
      if (sheetAt !== at || meaningSrc() !== src) return;
      var n = t.length;
      text.textContent = t[at.a - 1] || '';
      text.scrollTop = 0;
      var prev = document.getElementById('as-prev'), next = document.getElementById('as-next');
      prev.disabled = at.s === 1 && at.a === 1;
      next.disabled = at.s === 114 && at.a === n;
      prev.textContent = '‹ ' + (at.a > 1 ? T('ayah_n', { N: at.a - 1 }) : T('mr_surah', { N: at.s - 1 }));
      next.textContent = (at.a < n ? T('ayah_n', { N: at.a + 1 }) : T('mr_surah', { N: at.s + 1 })) + ' ›';
    }, function () {
      if (sheetAt === at) text.textContent = T('mr_offline');
    });
    sheetHighlight();
  }
  function sheetOpen(s, a) {
    sheetAt = { s: s, a: a };
    document.getElementById('ayah-sheet-dim').hidden = false;
    document.getElementById('ayah-sheet').hidden = false;
    sheetShow();
    trail('mhold', { k: s + ':' + a });
  }
  function sheetClose() {
    sheetAt = null;
    document.getElementById('ayah-sheet-dim').hidden = true;
    document.getElementById('ayah-sheet').hidden = true;
    sheetHighlight();
  }
  function sheetStep(d) {
    if (!sheetAt) return;
    var at = sheetAt;
    meaningSurah(meaningSrc(), at.s).then(function (t) {
      if (sheetAt !== at) return;
      if (d > 0) {
        if (at.a < t.length) sheetAt = { s: at.s, a: at.a + 1 };
        else if (at.s < 114) sheetAt = { s: at.s + 1, a: 1 };
        sheetShow();
      } else if (at.a > 1) {
        sheetAt = { s: at.s, a: at.a - 1 }; sheetShow();
      } else if (at.s > 1) {
        meaningSurah(meaningSrc(), at.s - 1).then(function (p) {
          if (sheetAt !== at) return;
          sheetAt = { s: at.s - 1, a: p.length }; sheetShow();
        });
      }
    });
  }
  document.getElementById('ayah-sheet-dim').addEventListener('click', sheetClose);
  document.getElementById('as-close').addEventListener('click', sheetClose);
  document.getElementById('as-prev').addEventListener('click', function () { sheetStep(-1); });
  document.getElementById('as-next').addEventListener('click', function () { sheetStep(1); });

  // ── Жест удержания: лист и «Крупно» в заучивании ──
  // Pointer events: на тачскрине прокрутка листа сама шлёт pointercancel
  // (touch-action: pan-y), сдвиг пальца больше 10px отменяет удержание.
  // Android (Chrome, WebView Telegram) ловит долгое нажатие сам, около
  // 400 мс - раньше нашего таймера - и шлёт contextmenu, часто вместе с
  // pointercancel. Поэтому contextmenu над аятом срабатывает сразу, тем же
  // путём, что таймер, а повтор (таймер после contextmenu) ничего не делает.
  var hold = { timer: null, x: 0, y: 0, id: null, fired: false, ma: null }, swallowClick = false;
  function holdCancel() {
    if (hold.timer) { clearTimeout(hold.timer); hold.timer = null; }
  }
  function holdFire() {
    if (hold.fired || !hold.ma) return;
    holdCancel();
    hold.fired = true;
    swallowClick = true;
    // Устаревший тап-таймер перевода слова не должен сработать поверх.
    if (typeof wordTapTimer !== 'undefined' && wordTapTimer) {
      clearTimeout(wordTapTimer); wordTapTimer = null; wordTapTarget = null;
    }
    if (navigator.vibrate) { try { navigator.vibrate(8); } catch (e2) {} }
    sheetOpen(hold.ma[0], hold.ma[1]);
  }
  function holdRelease() {
    holdCancel();
    // Click после удержания приходит не всегда (iOS его иногда не шлёт) -
    // флаг не должен «съесть» следующий настоящий тап.
    if (hold.fired) setTimeout(function () { swallowClick = false; }, 450);
  }
  function holdAttach(el) {
    el.addEventListener('pointerdown', function (e) {
      holdCancel();
      hold.fired = false; hold.ma = null;
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      if (!e.isPrimary || review.on) return;
      var w = e.target.closest ? e.target.closest('[data-ma]') : null;
      if (!w) return;
      var ma = w.getAttribute('data-ma').split(':');
      hold.ma = [parseInt(ma[0], 10), parseInt(ma[1], 10)];
      hold.x = e.clientX; hold.y = e.clientY; hold.id = e.pointerId;
      hold.timer = setTimeout(holdFire, MEANING_HOLD_MS);
    });
    el.addEventListener('pointermove', function (e) {
      if (!hold.timer || e.pointerId !== hold.id) return;
      if (Math.abs(e.clientX - hold.x) > 10 || Math.abs(e.clientY - hold.y) > 10) holdCancel();
    });
    el.addEventListener('pointerup', holdRelease);
    el.addEventListener('pointercancel', holdRelease);
    el.addEventListener('pointerleave', holdCancel);
    el.addEventListener('touchstart', function (e) {
      if (e.touches.length > 1) holdCancel();     // второй палец - масштаб, не удержание
    }, { passive: true });
    el.addEventListener('contextmenu', function (e) {
      e.preventDefault();
      if (hold.timer) holdFire();                 // Android: долгое нажатие раньше таймера
    });
  }
  var ayahTextEl = document.getElementById('ayah-text');
  holdAttach(ayahTextEl);
  holdAttach(document.getElementById('hifz-big-words'));
  document.getElementById('page-wrap').addEventListener('scroll', holdCancel, { passive: true });
  // Гасим click после удержания - в фазе захвата, раньше всех обработчиков
  // (перевод слова, двойной тап, выбор строки в заучивании). На документе,
  // а не на листе: отпущенный палец бьёт кликом уже по затемнению панели,
  // и та закрывалась сразу после открытия (поймано на стенде).
  window.addEventListener('click', function (e) {
    if (!swallowClick) return;
    swallowClick = false;
    e.stopImmediatePropagation();
    e.preventDefault();
  }, true);

  // ── Отдельное чтение смысла ──
  var mr = { s: 1, here: null, saveTimer: null, sentKey: '' };
  function mrLocalPos() {
    try {
      var p = JSON.parse(localStorage.getItem(MPOS_KEY) || 'null');
      if (p && p.s >= 1 && p.s <= 114 && p.a >= 1) return p;
    } catch (e) {}
    return null;
  }
  function mrTopAyah() {
    var box = document.getElementById('mr-scroll');
    var top = box.getBoundingClientRect().top;
    var rows = document.querySelectorAll('#mr-text .mr-a');
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].getBoundingClientRect().bottom > top + 24) {
        return { s: mr.s, a: parseInt(rows[i].getAttribute('data-a'), 10) };
      }
    }
    return { s: mr.s, a: 1 };
  }
  function mrSave() {
    var p = mrTopAyah(), now = Date.now();
    p.t = now;
    try { localStorage.setItem(MPOS_KEY, JSON.stringify(p)); } catch (e) {}
    var key = p.s + ':' + p.a;
    if (key === mr.sentKey) return;
    mr.sentKey = key;
    apiCall('/meaning_pos', { method: 'POST', quiet: true, body: { surah: p.s, ayah: p.a } })
      .catch(function () { mr.sentKey = ''; });
  }
  function mrRender(at, here) {
    mr.s = at.s;
    var box = document.getElementById('mr-text'), scroll = document.getElementById('mr-scroll');
    var row = surahRow(at.s), src = meaningSrc();
    box.innerHTML = '<div class="mr-msg">' + T('mr_loading') + '</div>';
    var prev = document.getElementById('mr-prev'), next = document.getElementById('mr-next');
    prev.disabled = at.s <= 1; next.disabled = at.s >= 114;
    // <bdi> - арабское имя изолировано от номера: без этого WebKit
    // переставлял «20. طه» в «طه .20» (снимок 02.11.2026).
    prev.innerHTML = at.s > 1 ? '‹ ' + (at.s - 1) + '. <bdi class="ar" dir="rtl">' + surahRow(at.s - 1)[1] + '</bdi>' : '';
    next.innerHTML = at.s < 114 ? (at.s + 1) + '. <bdi class="ar" dir="rtl">' + surahRow(at.s + 1)[1] + '</bdi> ›' : '';
    meaningSurah(src, at.s).then(function (t) {
      if (mr.s !== at.s || meaningSrc() !== src) return;
      var html = '<div class="mr-sura"><div class="ar">سُورَةُ ' + row[1] + '</div>' +
        '<div class="num">' + T('mr_surah', { N: at.s }) + '</div></div>';
      t.forEach(function (txt, i) {
        if (here && here === i + 1) html += '<div class="mr-here" id="mr-here">' + T('mr_here') + '</div>';
        html += '<div class="mr-a" data-a="' + (i + 1) + '"><span class="n">' + (i + 1) + '</span><span></span></div>';
      });
      if (at.s < 114) {
        html += '<button type="button" class="mr-next" id="mr-next-surah">' + T('mr_next') + ': ' +
          (at.s + 1) + '. <bdi dir="rtl">' + surahRow(at.s + 1)[1] + '</bdi></button>';
      }
      box.innerHTML = html;
      // Текст перевода - через textContent: это данные, не разметка.
      var spans = box.querySelectorAll('.mr-a span:last-child');
      t.forEach(function (txt, i) { spans[i].textContent = txt; });
      var target = at.a > 1 ? box.querySelector('[data-a="' + (here ? here : at.a) + '"]') : null;
      var mark = document.getElementById('mr-here');
      scroll.scrollTop = target ? (mark || target).offsetTop - 8 : 0;
      if (mark) setTimeout(function () { mark.classList.add('gone'); }, 2500);
      var ns = document.getElementById('mr-next-surah');
      if (ns) ns.addEventListener('click', function () { mrRender({ s: at.s + 1, a: 1 }); mrSave(); });
    }, function () {
      if (mr.s !== at.s) return;
      box.innerHTML = '<div class="mr-msg"></div>';
      var msg = box.firstChild;
      msg.textContent = T('mr_offline');
      msg.addEventListener('click', function () { mrRender(at, here); });
    });
  }
  function mrOpen() {
    sheetClose();
    document.getElementById('mreader').hidden = false;
    mrMarkSeg();
    var local = mrLocalPos();
    var start = local || { s: 1, a: 1 };
    mrRender(start, local && (local.s > 1 || local.a > 1) ? local.a : null);
    trail('mread', { k: start.s + ':' + start.a });
    // Сервер - место с другого устройства (Telegram/иконка). Новее - прыгаем.
    apiCall('/meaning_pos', { quiet: true }).then(function (res) {
      var d = res && res.status === 200 ? res.data : null;
      if (!d || !d.surah || document.getElementById('mreader').hidden) return;
      var st = Date.parse(d.updated_at || '') || 0;
      if (local && local.t && local.t >= st) return;
      if (local && local.s === d.surah && local.a === d.ayah) return;
      mr.sentKey = d.surah + ':' + d.ayah;
      mrRender({ s: d.surah, a: d.ayah }, d.surah > 1 || d.ayah > 1 ? d.ayah : null);
    }).catch(function () {});
  }
  function mrClose() {
    if (document.getElementById('mreader').hidden) return;
    if (document.querySelector('#mr-text .mr-a')) mrSave();
    document.getElementById('mreader').hidden = true;
  }
  document.getElementById('mr-scroll').addEventListener('scroll', function () {
    clearTimeout(mr.saveTimer);
    mr.saveTimer = setTimeout(mrSave, 1500);
  }, { passive: true });
  document.getElementById('mr-back').addEventListener('click', mrClose);
  document.getElementById('mr-prev').addEventListener('click', function () {
    if (mr.s > 1) { mrRender({ s: mr.s - 1, a: 1 }); mrSave(); }
  });
  document.getElementById('mr-next').addEventListener('click', function () {
    if (mr.s < 114) { mrRender({ s: mr.s + 1, a: 1 }); mrSave(); }
  });
  document.addEventListener('visibilitychange', function () {
    if (document.hidden && !document.getElementById('mreader').hidden) mrSave();
  });
  document.getElementById('btn-meaning').addEventListener('click', mrOpen);

  // "Мои слова" - список (29.08.2026, см. модульный комментарий у
  // #view-mywords). Свой делегированный обработчик двойного тапа/клика -
  // тот же таймер-паттерн, что у слова на странице чтения выше, но здесь
  // одиночный клик НИЧЕГО не делает (простой список для чтения, решение
  // пользователя - строка не открывает тренажёр), только двойной убирает
  // слово из списка.
  var mywordsTapTimer = null, mywordsTapTarget = null;
  function myWordsRowHtml(w) {
    return '<div class="word-row mywords-row" data-surah="' + w.surah + '" data-ayah="' + w.ayah +
      '" data-pos="' + w.position + '"><span class="arabic">' + w.arabic +
      '</span><span class="translation">' + w.translation + '</span></div>';
  }
  function renderMyWords(words) {
    var html;
    if (!words.length) {
      html = '<div class="trainer-msg">' + T('mywords_empty') + '</div>';
    } else {
      // Секции показываем, только если есть хоть одно "Новое" (is_new) -
      // иначе список выглядит как раньше, без лишнего заголовка "Забытые"
      // над всем и так привычным списком (03.09.2026).
      var newWords = words.filter(function (w) { return w.is_new; });
      var oldWords = words.filter(function (w) { return !w.is_new; });
      if (newWords.length) {
        html = '<div class="mywords-section-title">' + T('mywords_new') + '</div>' +
          newWords.map(myWordsRowHtml).join('') +
          '<div class="mywords-section-title">' + T('mywords_old') + '</div>' +
          oldWords.map(myWordsRowHtml).join('');
      } else {
        html = words.map(myWordsRowHtml).join('');
      }
    }
    document.getElementById('mywords-list').innerHTML = html;
  }
  function loadMyWords() {
    document.getElementById('mywords-list').innerHTML = '<div class="trainer-msg">' + T('loading') + '</div>';
    apiCall('/words').then(function (res) {
      if (res.status === 401) {
        document.getElementById('mywords-list').innerHTML =
          '<div class="trainer-msg">' + T('session_expired') + '</div>';
        return;
      }
      renderMyWords(res.data.words);
    });
  }
  function removeFromMyWords(row) {
    apiCall('/words/remove', { method: 'POST', body: {
      surah: parseInt(row.getAttribute('data-surah'), 10),
      ayah: parseInt(row.getAttribute('data-ayah'), 10),
      position: parseInt(row.getAttribute('data-pos'), 10),
    } }).then(function (res) {
      if (res.status !== 401) renderMyWords(res.data.words);
    });
  }
  document.getElementById('mywords-list').addEventListener('click', function (e) {
    var row = e.target.closest('.mywords-row');
    if (!row) return;
    if (mywordsTapTimer && mywordsTapTarget === row) {
      clearTimeout(mywordsTapTimer);
      mywordsTapTimer = null; mywordsTapTarget = null;
      removeFromMyWords(row);
      return;
    }
    mywordsTapTarget = row;
    mywordsTapTimer = setTimeout(function () {
      mywordsTapTimer = null; mywordsTapTarget = null;
    }, DOUBLE_TAP_WINDOW_MS);
  });

