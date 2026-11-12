  /* ── «Тренажёры» и тренажёр таджвида (14.09.2026) ───────────────────────
     Хаб рисуется из фактов последнего heartbeat: счёт «Слов» и «Таджвида»
     за день уже едет туда для дверей, отдельный запрос не нужен. Нет
     facts.tajweed - у группы нет таджвида, строки нет. */
  var dashFactsLast = null;
  var tajweedState = null;
  var nahwState = null;

  // Подпись двери «Знания» - по предметам группы (14.09.2026): у кого нет
  // таджвида и нахва, про них и не пишем.
  function dashLearnSub(f) {
    var el = document.getElementById('dash-learn-sub');
    if (!el || !f || !f.learn) return;
    var j = f.learn.indexOf('j') >= 0, n = f.learn.indexOf('n') >= 0;
    var text = T(j && n ? 'dash_learn_sub' : j ? 'dash_learn_j' : n ? 'dash_learn_n' : 'dash_learn_how');
    // Первое слово - «Правила» - подсвечено (07.10.2026, просьба пользователя):
    // дверь должна выдавать, что правила методики внутри. Слово берём до
    // первой запятой или « и », остальное - как было.
    var m = /^([^,]+?)(,| и | жана | ва )(.*)$/.exec(text);
    el.innerHTML = m
      ? '<b class="dash-sub-hl">' + m[1] + '</b>' + m[2] + m[3]
      : text;
  }

  function openTrainers() {
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('trainer').style.display = 'none';
    document.getElementById('tajweed').style.display = 'none';
    document.getElementById('nahw').style.display = 'none';
    document.getElementById('hadith').style.display = 'none';
    document.getElementById('trainers').style.display = 'flex';
    trainersRender();
  }

  function trainersRow(id, mark, name, desc, fact) {
    var cnt = '';
    if (fact && fact.target != null) {
      var complete = fact.complete != null ? fact.complete : fact.done >= fact.target;
      var label = fact.correct_target != null
        ? T('daily_words_n', { N: fact.done, M: fact.target, C: fact.correct, K: fact.correct_target })
        : T('daily_n', { N: fact.done, M: fact.target });
      cnt = '<span class="cnt' + (complete ? ' done' : '') + '">' + label + '</span>';
    }
    return '<button class="tr-hub" id="' + id + '"><span class="mk">' + mark + '</span>' +
      '<span><span class="nm">' + name + '</span><span class="ds">' + desc + '</span></span>' +
      cnt + '</button>';
  }

  function trainersRender() {
    var f = dashFactsLast || {};
    var html = trainersRow('trh-words', 'ن', T('trainers_words'), T('trainers_words_sub'), f.words);
    if (f.tajweed) {
      html += trainersRow('trh-tajweed', 'ض', T('tajweed_title'), T('trainers_tajweed_sub'), f.tajweed);
    }
    if (f.nahw) {
      html += trainersRow('trh-nahw', 'ك', T('nahw_title'), T('trainers_nahw_sub'), f.nahw);
    }
    if (f.hadith) {
      html += trainersRow('trh-hadith', 'ح', T('hadith_title'), T('trainers_hadith_sub'), f.hadith);
    }
    // Слова из сегодняшней строки и «Мои слова» (11.11.2026, из макета).
    html += '<details class="tr-fold" id="tr-line-words"><summary>' +
      '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>' +
      T('line_words') + '<span class="cnt" id="tr-line-cnt"></span></summary><div class="tr-words" id="tr-line-list"></div></details>';
    html += trainersRow('trh-mywords', ICON.star, T('tab_mywords'), T('mywords_sub'), null);
    var body = document.getElementById('trainers-body');
    body.innerHTML = html;
    var myw = document.getElementById('trh-mywords');
    if (myw) { myw.querySelector('.mk').classList.add('gold'); myw.addEventListener('click', function () { openMushaf('mywords', 'trainer'); }); }
    trainersLineWords(f.hifz);
    document.getElementById('trh-words').addEventListener('click', openTrainer);
    var tj = document.getElementById('trh-tajweed');
    if (tj) tj.addEventListener('click', openTajweed);
    var nh = document.getElementById('trh-nahw');
    if (nh) nh.addEventListener('click', openNahw);
    var hd = document.getElementById('trh-hadith');
    if (hd) hd.addEventListener('click', openHadith);
  }

  function trainersLineWords(h) {
    var fold = document.getElementById('tr-line-words'), list = document.getElementById('tr-line-list');
    var cnt = document.getElementById('tr-line-cnt');
    if (!fold || !h || !h.page || (h.stage && h.stage !== 1)) { if (fold) fold.style.display = 'none'; return; }
    fold.style.display = '';
    cnt.textContent = dashPlace(h);
    dashPage(h.page, function (d) {
      var line = dashTextLines(d)[h.line || 0];
      if (!line) { fold.style.display = 'none'; return; }
      var words = dashLineWords(line);
      cnt.textContent = words.length + ' · ' + dashPlace(h);
      list.innerHTML = words.map(function (w, i) {
        return '<div class="tr-word"><span class="n">' + (i + 1) + '</span><span class="ar">' + dashBare(w.html) + '</span>' +
          '<span class="ru">' + feedEsc(w.translation || '') + '</span></div>';
      }).join('');
    });
  }

  function openTajweed() {
    document.getElementById('trainers').style.display = 'none';
    document.getElementById('tajweed').style.display = 'flex';
    document.getElementById('tajweed-body').innerHTML = '<div class="trainer-msg">' + T('loading') + '</div>';
    withAuthCheck(apiCall('/tajweed'), renderTajweed);
  }

  /* Центр буквы по её контуру, а не по строке (14.09.2026, поймал
     пользователь: «буква ниже, не по центру»). measureText даёт, насколько
     чернила уходят вверх и вниз от базовой линии, fontBoundingBox - где сама
     базовая линия внутри строки. Сдвигаем span так, чтобы середина чернил
     совпала с серединой строки. Шрифт ждём: до загрузки мерили бы запасной. */
  function tajweedCenterGlyph() {
    var box = document.querySelector('#tajweed-body .tj-glyph');
    if (!box) return;
    var glyph = box.textContent;
    box.innerHTML = '<span></span>';
    var span = box.firstChild;
    span.textContent = glyph;
    var place = function () {
      var cs = getComputedStyle(box);
      var ctx = document.createElement('canvas').getContext('2d');
      ctx.font = cs.fontSize + ' ' + cs.fontFamily;
      var m = ctx.measureText(glyph);
      if (!m || m.actualBoundingBoxAscent == null || m.fontBoundingBoxAscent == null) return;
      var lh = parseFloat(cs.lineHeight);
      var baseline = (lh - (m.fontBoundingBoxAscent + m.fontBoundingBoxDescent)) / 2 + m.fontBoundingBoxAscent;
      var inkMid = baseline - (m.actualBoundingBoxAscent - m.actualBoundingBoxDescent) / 2;
      span.style.transform = 'translateY(' + (lh / 2 - inkMid).toFixed(1) + 'px)';
    };
    if (document.fonts && document.fonts.load) {
      document.fonts.load(getComputedStyle(box).fontSize + " 'Scheherazade New'", glyph).then(place, place);
    } else {
      place();
    }
  }

  // Арабское слово в подписи крупнее - обёрткой только по размеру.
  function tajweedArabic(text) {
    return String(text || '').replace(/[\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)*/g, function (m) {
      return '<span class="tj-ar">' + m + '</span>';
    });
  }

  // Короткое имя свойства: «Взрыв — الشدة» → «Взрыв» (так же и в zh).
  function tajweedShort(oid, fallback) {
    return String(T('tjo_' + oid) || fallback || '').split(' — ')[0];
  }
  // Внутри фразы - со строчной: «значит «удержание»» (у zh регистра нет).
  function tajweedLower(t) { return t.charAt(0).toLowerCase() + t.slice(1); }

  // Фразы-ключи пары: где буква есть - подсвечено; нет нигде - противоположное.
  function tajweedWhy(fb) {
    var w = fb.why, L = '<span class="tj-ar">' + fb.glyph + '</span>‎';
    var html = '<div class="tj-why">';
    w.groups.forEach(function (g) {
      var lt = g.letters.split(' ').map(function (ch) {
        return '<b' + (ch === fb.glyph ? ' class="me"' : '') + '>' + ch + '</b>';
      }).join('');
      // Фраза «ص ض ط ظ» и есть сами буквы - второй строкой не повторяем.
      var same = g.phrase.replace(/\s/g, '') === g.letters.replace(/\s/g, '');
      html += '<div class="row' + (g.id === w.hit ? ' hit' : '') + '"><span class="lbl">' +
        tajweedShort(g.id, g.label) + '</span><span class="key">' +
        (same ? '' : '<span class="ph">' + g.phrase + '</span>') +
        '<span class="lt">' + lt + '</span></span></div>';
    });
    html += '<div class="say">' + (w.hit ? T('tj_why_in', { L: L })
      : T('tj_why_out', { L: L, A: tajweedLower(tajweedShort(w.rest, w.rest_label)) })) + '</div>';
    return html + '</div>';
  }

  function renderTajweed(d) {
    tajweedState = d;
    var body = document.getElementById('tajweed-body');
    var pill = document.getElementById('tajweed-daily');
    if (!d || d.error) {
      pill.textContent = '';
      body.innerHTML = '<div class="trainer-msg">' + T('tajweed_closed') + '</div>';
      return;
    }
    pill.textContent = T('daily_n', { N: d.daily_count, M: d.daily_target });
    pill.classList.toggle('done', d.daily_count >= d.daily_target);

    if (d.empty) {
      body.innerHTML = '<div class="trainer-msg">' + T('tajweed_empty') + '</div>';
      return;
    }

    /* Экрана «Заход окончен» здесь больше нет (20.09.2026, решение
       пользователя): каждые четыре буквы он вставал стеной и спрашивал
       разрешения продолжить. Норму дня человек видит счётчиком в шапке, а
       сверх неё занимается по своей воле - карточки идут лентой. */
    var c = d.card;
    // Точки — ход ДНЯ: сколько разных букв уже ответил верно из нормы.
    // Раньше они показывали место внутри захода, а захода больше нет.
    var dots = '';
    for (var i = 0; i < c.size; i++) {
      dots += '<i class="' + (c.day_done || i < c.pos - 1 ? 'on'
        : i === c.pos - 1 ? 'cur' : '') + '"></i>';
    }
    if (c.retry) dots += '<span>' + T('tajweed_retry') + '</span>';
    else if (c.day_done) dots += '<span class="tj-day-done">' + T('tajweed_day_done') + '</span>';
    var html = '<div class="tj-dots">' + dots + '</div>';
    // Подписи сервер шлёт по-русски и с id; на другом языке - из словаря
    // (28.10.2026, аудит zh), нет перевода - русская.
    var note = c.note && (T('tjn_' + c.note_id) || c.note);
    var question = c.question && (T('tjq_' + c.kind) || c.question);
    html += '<div class="trainer-word-card"><div class="tj-glyph">' + c.glyph + '</div>' +
      (note ? '<div class="tj-note">' + tajweedArabic(note) + '</div>' : '') + '</div>';
    // Сифаты (24.09.2026) спрашивают своё - вопрос приходит с карточкой.
    html += '<div class="tj-q">' + (question ? tajweedArabic(question) : T('tajweed_question')) + '</div>';
    html += '<div class="trainer-options">';
    d.options.forEach(function (opt, i) {
      var oid = (d.option_ids || [])[i] || '';
      html += '<button class="trainer-opt tj-opt" data-slot="' + i + '" data-oid="' + oid + '">'
        + (T('tjo_' + oid) || opt) + '</button>';
    });
    html += '</div><div id="tj-after"></div>';
    body.innerHTML = html;
    body.scrollTop = 0;
    tajweedCenterGlyph();
    var buttons = body.querySelectorAll('.tj-opt');
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener('click', function () {
        // Двойной тап не должен ответить за следующую карточку.
        Array.prototype.forEach.call(buttons, function (b) { b.disabled = true; });
        withAuthCheck(apiCall('/tajweed/answer', { method: 'POST',
          body: { card: c.id, slot: parseInt(btn.getAttribute('data-slot'), 10) } }), function (next) {
          var fb = next && next.feedback;
          if (!fb) { renderTajweed(next); return; }
          // Итог на тех же кнопках: верная - зелёная всегда, нажатая мимо - красная.
          Array.prototype.forEach.call(buttons, function (b) {
            if (fb.answer_id ? b.getAttribute('data-oid') === fb.answer_id
                             : b.textContent === fb.answer) b.classList.add('ok');
          });
          if (!fb.correct) btn.classList.add('no');
          // Места выхода: верно - сразу дальше. Сифаты (03.11.2026) - и при
          // верном ответе ждём «Дальше»: угаданный ответ без объяснения
          // ничему не учит, а строку «почему» надо успеть прочитать.
          if (fb.correct && !fb.why) { setTimeout(function () { renderTajweed(next); }, 900); return; }
          // Мимо - ждём «Дальше»: верный ответ надо успеть прочитать.
          var after = document.getElementById('tj-after');
          after.innerHTML = (fb.why ? tajweedWhy(fb) : '') +
            '<button class="tj-go" id="tj-next">' + T('tajweed_next') + '</button>';
          document.getElementById('tj-next').addEventListener('click', function () { renderTajweed(next); });
        });
      });
    });
  }

