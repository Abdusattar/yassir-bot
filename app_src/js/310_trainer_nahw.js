  /* ── Тренажёр нахва (17.09.2026, core/nahw_trainer.py) ─────────────────
     Слово в аяте, три кнопки: исм / фиаль / харф. После ответа - объяснение
     словами урока и разбор слова по частям, дальше - по «Дальше». */
  function openNahw() {
    document.getElementById('trainers').style.display = 'none';
    document.getElementById('nahw').style.display = 'flex';
    document.getElementById('nahw-body').innerHTML = '<div class="trainer-msg">' + T('loading') + '</div>';
    withAuthCheck(apiCall('/nahw'), renderNahw);
  }

  function nahwEsc(t) {
    return String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  }

  // Окно вокруг слова: длинный аят (2:282) не должен вытеснять вопрос.
  var NAHW_AROUND = 4;
  function nahwAyah(words) {
    var at = 0;
    words.forEach(function (w, i) { if (w.hl || w.parts) at = i; });
    var from = Math.max(0, at - NAHW_AROUND), to = Math.min(words.length, at + NAHW_AROUND + 1);
    var out = [];
    if (from > 0) out.push('<span class="gap">…</span>');
    for (var i = from; i < to; i++) {
      var w = words[i];
      if (w.parts) {
        out.push('<span>' + w.parts.map(function (p) {
          return p.hl ? '<span class="hl">' + nahwEsc(p.t) + '</span>' : nahwEsc(p.t);
        }).join('') + '</span>');
      } else {
        out.push(w.hl ? '<span class="hl">' + nahwEsc(w.t) + '</span>' : nahwEsc(w.t));
      }
    }
    if (to < words.length) out.push('<span class="gap">…</span>');
    return out.join(' ');
  }

  // Арабские вставки в русском тексте («есть артикль الـ») - крупнее, только размером.
  function nahwArabic(text) {
    return nahwEsc(text).replace(/[\u0600-\u06FF]+(?:[\s\/]+[\u0600-\u06FF]+)*/g, function (m) {
      // Знак «слева направо» после вставки (17.09.2026): иначе тире между
      // двумя арабскими словами склеивает их в один кусок справа налево, и
      // «نون التوكيد — معرب» читается задом наперёд.
      return '<span class="ar">' + m + '</span>\u200E';
    });
  }

  function nahwFeedback(fb) {
    var head = fb.correct ? T('nahw_right') : T('nahw_wrong', { A: fb.answer_ar + ' · ' + fb.answer_ru });
    var html = '<div class="nh-fb"><div class="exp"><b style="color:var(' + (fb.correct ? '--ok' : '--no') + ')">' +
      nahwArabic(head) + '.</b> ' + nahwArabic(fb.explain) + '</div>';
    var parts = (fb.breakdown || []).filter(function (b) { return b.t; });
    if (parts.length > 1) {
      html += '<div class="nh-bd">' + parts.map(function (b) {
        return '<span class="' + (b.asked ? 'asked' : '') + '"><b>' + nahwEsc(b.t) + '</b><i>' + nahwEsc(b.label) + '</i></span>';
      }).join('') + '</div>';
    }
    if (fb.meaning) html += '<div class="mean">' + nahwArabic(fb.word) + ' — ' + nahwEsc(fb.meaning) + '</div>';
    return html + '</div>';
  }

  var nahwAutoTimer = null;   // автолистание снято 11.10.2026, таймер остался только как страховка в renderNahw

  function renderNahw(d) {
    clearTimeout(nahwAutoTimer);
    nahwState = d;
    window.__nahwCard = function () { return nahwState && nahwState.card; };   // для стенда снимков
    var body = document.getElementById('nahw-body');
    var pill = document.getElementById('nahw-daily');
    if (!d || d.error) {
      pill.textContent = '';
      body.innerHTML = '<div class="trainer-msg">' + T('nahw_closed') + '</div>';
      return;
    }
    pill.textContent = T('daily_n', { N: d.daily_count, M: d.daily_target });
    pill.classList.toggle('done', d.daily_count >= d.daily_target);

    if (d.empty) {
      body.innerHTML = '<div class="trainer-msg">' + T('nahw_empty') + '</div>';
      return;
    }

    var html;
    if (d.finished) {
      var f = d.finished;
      html = '<div class="trainer-msg">' + T('nahw_done_title') + '</div>';
      if (f.stage_up) html += '<div class="nh-sum"><b>' + T('nahw_stage_up') + '</b></div>';
      if (f.new_skill) html += '<div class="nh-sum"><b>' + nahwArabic(T('nahw_new_skill', { S: f.new_skill })) + '</b></div>';
      if (f.good.length) html += '<div class="nh-sum">' + nahwArabic(T('nahw_good', { L: f.good.join(', ') })) + '</div>';
      if (f.weak.length) html += '<div class="nh-sum">' + nahwArabic(T('nahw_weak', { L: f.weak.join(', ') })) + '</div>';
      var left = Math.max(0, d.daily_target - d.daily_count);
      html += '<div class="trainer-info">' + (!d.task ? T('nahw_today', { N: d.daily_count, M: d.daily_target })
        : d.task.done ? T('nahw_task_done') : T('nahw_task_left', { N: left })) + '</div>';
      html += '<button class="tj-go" id="nh-more">' + T('nahw_more') + '</button>';
      html += '<div class="nh-src">' + T('nahw_source') + '</div>';
      body.innerHTML = html;
      body.scrollTop = 0;
      document.getElementById('nh-more').addEventListener('click', function () {
        this.disabled = true;
        withAuthCheck(apiCall('/nahw/new', { method: 'POST' }), renderNahw);
      });
      return;
    }

    var c = d.card;
    var dots = '';
    for (var i = 0; i < c.size; i++) {
      dots += '<i class="' + (c.retry || i < c.pos - 1 ? 'on' : i === c.pos - 1 ? 'cur' : '') + '"></i>';
    }
    if (c.retry) dots += '<span>' + T('nahw_retry') + '</span>';
    html = '<div class="tj-dots">' + dots + '</div>';
    // Первая карточка дня - одна строка, что это и зачем.
    if (!d.daily_count && c.pos === 1 && !c.retry) html += '<div class="nh-hint">' + T('nahw_hint') + '</div>';
    html += '<div class="trainer-word-card"><div class="nh-ayah">' + nahwAyah(c.words) + '</div>' +
      '<div class="nh-ref">' + nahwEsc(c.ref) + '</div></div>';
    // Вопрос и кнопки - от навыка (17.09.2026): виды слова, признаки исма,
    // число, время, معرب/مبني... Приходят с сервера готовыми.
    html += '<div class="nh-q">' + nahwArabic(c.question || T('nahw_question')) + '</div>';
    html += '<div class="nh-opts n' + d.options.length + '">';
    d.options.forEach(function (o) {
      html += '<button class="trainer-opt nh-opt" data-key="' + o.key + '"><span class="ar">' + o.ar +
        '</span><span class="ru">' + o.ru + '</span></button>';
    });
    html += '</div><div id="nh-after" style="display:contents"></div>';
    html += '<div class="nh-src">' + T('nahw_source') + '</div>';
    body.innerHTML = html;
    body.scrollTop = 0;
    var buttons = body.querySelectorAll('.nh-opt');
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener('click', function () {
        // Двойной тап не должен ответить за следующую карточку.
        Array.prototype.forEach.call(buttons, function (b) { b.disabled = true; });
        withAuthCheck(apiCall('/nahw/answer', { method: 'POST',
          body: { card: c.id, choice: btn.getAttribute('data-key') } }), function (next) {
          var fb = next && next.feedback;
          if (!fb) { renderNahw(next); return; }
          Array.prototype.forEach.call(buttons, function (b) {
            if (b.getAttribute('data-key') === fb.answer) b.classList.add('ok');
          });
          if (!fb.correct) btn.classList.add('no');
          // Дальше — только по кнопке (11.10.2026, решение пользователя: студенты
          // не успевали дочитать разбор внизу; автолистание 17.09–11.10 снято).
          document.getElementById('nh-after').innerHTML = nahwFeedback(fb) +
            '<button class="tj-go" id="nh-next">' + T('nahw_next') + '</button>';
          var gone = false;
          var go = function () {
            if (gone) return;
            gone = true;
            clearTimeout(nahwAutoTimer);
            renderNahw(next);
          };
          document.getElementById('nh-next').addEventListener('click', go);
        });
      });
    });
  }

