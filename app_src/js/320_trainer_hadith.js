  /* ── Тренажёр хадисов (23.09.2026, core/hadith_trainer.py) ────────────
     Один путь, как у остальных тренажёров: слово дня (показ, не проверка) →
     закрепление вариантами в обе стороны → итог. При первом входе человек
     сам ставит, с какого хадиса и слова продолжает. */
  var hadithState = null;
  var hadithAutoTimer = null;   // автолистание снято 11.10.2026; clearTimeout ниже — страховка

  function openHadith() {
    document.getElementById('trainers').style.display = 'none';
    document.getElementById('hadith').style.display = 'flex';
    document.getElementById('hadith-body').innerHTML = '<div class="trainer-msg">' + T('loading') + '</div>';
    withAuthCheck(apiCall('/hadith'), renderHadith);
  }

  function hadithPost(action, body) {
    clearTimeout(hadithAutoTimer);
    withAuthCheck(apiCall('/hadith/' + action, { method: 'POST', body: body || {} }), renderHadith);
  }

  function hadithPhrase(ctx) {
    return '<div class="hd-phrase">' + ctx.tokens.map(function (t) {
      return t.hl ? '<span class="hl">' + nahwEsc(t.t) + '</span>' : nahwEsc(t.t);
    }).join(' ') + '</div>';
  }

  /* Весь хадис: арабский, под ним смысловой перевод; фраза текущего слова
     подсвечена в обоих (24.09.2026). */
  function hadithFull(full, hideCur) {
    if (!full || !full.phrases || !full.phrases.length) return '';
    var n = full.n;
    var part = function (key) {
      return full.phrases.map(function (p, k) {
        var t = nahwEsc(p[key] || '');
        return k === full.cur ? '<span class="cur">' + t + '</span>' : t;
      }).join(' ');
    };
    // Крупно - только сам текст хадиса; кто передал и где записан - тихими
    // строками по-русски (24.09.2026, решение пользователя).
    return '<div class="hd-full' + (hideCur ? ' hide-cur' : '') + '">' +
      (n ? '<div class="hd-full-title">' + T('hadith_full_title', { N: n }) + '</div>' : '') +
      (full.isnad ? '<div class="hd-full-isnad">' + nahwEsc(full.isnad) + '</div>' : '') +
      '<div class="hd-full-ar">' + part('ar') + '</div>' +
      // tr - перевод целиком, когда пофразового нет (zh, HadeethEnc, 28.10.2026).
      '<div class="hd-full-ru">' + (full.tr ? nahwEsc(full.tr) : part('ru')) +
      (full.source ? '<div class="hd-full-src">' + nahwEsc(full.source) + '</div>' : '') +
      '</div></div>';
  }

  /* Вариант, которому тесно в половине ширины, - на всю ширину. Меряем
     после отрисовки: длину арабского слова в пикселях заранее не знаем. */
  function hadithWideOpts(buttons) {
    // Слово не рвём посреди («засвидетельствую/т» на 360px, 24.09.2026):
    // не влезло целым - кнопка на всю ширину. Пару тоже, чтобы сетка
    // не оставила дыру рядом.
    var list = Array.prototype.slice.call(buttons);
    list.forEach(function (b) {
      if (b.scrollWidth > b.clientWidth + 1) b.classList.add('wide');
    });
    list.forEach(function (b, k) {
      var mate = list[k % 2 ? k - 1 : k + 1];
      if (b.classList.contains('wide') && mate) mate.classList.add('wide');
    });
  }

  window.__hadithWideOpts = function () { hadithWideOpts(document.querySelectorAll('.hd-opt')); };   // для стенда снимков

  function hadithPill(d) {
    var pill = document.getElementById('hadith-daily');
    pill.textContent = T('daily_n', { N: d.daily_count || 0, M: d.daily_target || 0 });
    pill.classList.toggle('done', !!(d.task ? d.task.done : d.daily_count >= d.daily_target));
  }

  function hadithPickRender(d) {
    var body = document.getElementById('hadith-body');
    var html;
    {
      html = '<div class="trainer-msg"><b>' + T('hadith_pick_title') + '</b></div>' +
        '<div class="nh-hint">' + T('hadith_pick_hint') + '</div><div class="hd-pick">';
      d.pick.forEach(function (h) {
        html += '<button class="trainer-opt" data-n="' + h.n + '">' + h.n + '</button>';
      });
      html += '</div>';
      body.innerHTML = html;
      Array.prototype.forEach.call(body.querySelectorAll('.hd-pick button'), function (b) {
        b.addEventListener('click', function () {
          // Место записывается только после выбора слова: закрыл приложение
          // посреди выбора - старое место не потеряно.
          hadithWordsPick(+b.getAttribute('data-n'));
        });
      });
      return;
    }
  }

  function hadithWordsPick(n) {
    var body = document.getElementById('hadith-body');
    withAuthCheck(apiCall('/hadith/words?n=' + n), function (w) {
      if (!w || !w.words) { openHadith(); return; }
      var html = '<div class="nh-hint">' + T('hadith_pick_word', { N: n }) + '</div><div class="hd-words">';
      w.words.forEach(function (ar, i) {
        html += '<button data-i="' + i + '">' + nahwEsc(ar) + '</button> ';
      });
      html += '</div>';
      body.innerHTML = html;
      body.scrollTop = 0;
      Array.prototype.forEach.call(body.querySelectorAll('.hd-words button'), function (b) {
        b.addEventListener('click', function () {
          hadithPost('start', { hadith: n, pos: +b.getAttribute('data-i') });
        });
      });
    });
  }

  function renderHadith(d) {
    clearTimeout(hadithAutoTimer);
    hadithState = d;
    var body = document.getElementById('hadith-body');
    if (!d || d.error === 'closed') {
      body.innerHTML = '<div class="trainer-msg">' + T('hadith_closed') + '</div>';
      return;
    }
    hadithPill(d);
    if (d.pick) { hadithPickRender(d); return; }
    var html = '';
    var where = d.where;
    if (d.new_word) {
      var w = d.new_word;
      html += '<div class="hd-where">' + T('hadith_where', { N: w.hadith, P: w.pos, T: w.total }) + '</div>' +
        '<div class="hd-bar"><i style="width:' + Math.round(100 * (w.pos - 1) / w.total) + '%"></i></div>';
      html += '<div class="trainer-word-card">' + hadithPhrase(w.context) +
        '<div class="hd-gloss">' + nahwEsc(w.ru) + '</div></div>';
      html += '<div class="nh-hint">' + T('hadith_new_hint') + '</div>';
      html += '<button class="tj-go" id="hd-learn">' + T('hadith_learn') + '</button>';
      html += '<button class="hd-link" id="hd-change">' + T('hadith_change') + '</button>';
      html += hadithFull(w.full);
      body.innerHTML = html;
      body.scrollTop = 0;
      document.getElementById('hd-learn').addEventListener('click', function () { hadithPost('learn'); });
      document.getElementById('hd-change').addEventListener('click', function () {
        hadithPickRender({ pick: hadithPickList() });
      });
      return;
    }
    if (d.empty) {
      body.innerHTML = '<div class="trainer-msg">' + T('hadith_empty') + '</div>';
      return;
    }
    if (d.finished) {
      var f = d.finished;
      html = '<div class="trainer-msg">' + T('hadith_done_title') + '</div><div class="hd-list">';
      f.results.forEach(function (r) {
        html += '<div><span class="ar">' + nahwEsc(r.ar) + '</span><span>' + nahwEsc(r.ru) + '</span>' +
          '<span class="mk' + (r.ok ? '' : ' no') + '">' +
          (r.new ? T('hadith_new_mark') : r.ok ? T('hadith_ok_mark') : T('hadith_no_mark')) + '</span></div>';
      });
      html += '</div>';
      var left = Math.max(0, d.daily_target - d.daily_count);
      html += '<div class="trainer-info">' + (!d.task ? T('hadith_today', { N: d.daily_count, M: d.daily_target })
        : d.task.done ? T('hadith_task_done') : T('hadith_task_left', { N: left })) + '</div>';
      if (where) html += '<div class="hd-where">' + T('hadith_where', { N: where.hadith, P: Math.min(where.pos + 1, where.total), T: where.total }) + '</div>';
      if (f.more) html += '<button class="tj-go" id="hd-more">' + T('hadith_more_word') + '</button>';
      html += '<button class="tj-go" id="hd-round" style="background:var(--card-bg);color:var(--ink);border:1px solid var(--card-border)">' +
        T('hadith_more_round') + '</button>';
      body.innerHTML = html;
      body.scrollTop = 0;
      var mb = document.getElementById('hd-more');
      if (mb) mb.addEventListener('click', function () { hadithPost('more'); });
      document.getElementById('hd-round').addEventListener('click', function () { hadithPost('new'); });
      return;
    }
    var c = d.card;
    if (!c) { body.innerHTML = '<div class="trainer-msg">' + T('hadith_empty') + '</div>'; return; }
    var dots = '<span>' + c.pos + ' / ' + c.size + '</span>';
    if (c.retry) dots += '<span>' + T('nahw_retry') + '</span>';
    html += '<div class="hd-where">' + dots + '</div>';
    if (c.dir === 'ar2ru') {
      html += '<div class="trainer-word-card">' + hadithPhrase(c.context) + '</div>';
      html += '<div class="nh-q">' + T('hadith_ask_ar') + '</div>';
    } else {
      html += '<div class="trainer-word-card"><div class="hd-ask-ru">' + nahwEsc(c.ru) + '</div></div>';
      html += '<div class="nh-q">' + T('hadith_ask_ru') + '</div>';
    }
    html += '<div class="hd-opts">';
    c.options.forEach(function (o) {
      html += '<button class="trainer-opt hd-opt' + (c.dir === 'ru2ar' ? ' ar' : '') + '" data-key="' +
        nahwEsc(o.key) + '">' + nahwEsc(o.text) + '</button>';
    });
    html += '</div><div id="hd-after" style="display:contents"></div>';
    html += hadithFull(c.full, c.dir === 'ru2ar');
    body.innerHTML = html;
    body.scrollTop = 0;
    var buttons = body.querySelectorAll('.hd-opt');
    hadithWideOpts(buttons);
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener('click', function () {
        Array.prototype.forEach.call(buttons, function (b) { b.disabled = true; });
        withAuthCheck(apiCall('/hadith/answer', { method: 'POST',
          body: { card: c.id, choice: btn.getAttribute('data-key') } }), function (next) {
          var fb = next && next.feedback;
          if (!fb) { renderHadith(next); return; }
          Array.prototype.forEach.call(buttons, function (b) {
            if (b.getAttribute('data-key') === fb.answer) b.classList.add('ok');
          });
          if (!fb.correct) btn.classList.add('no');
          var fullBox = body.querySelector('.hd-full.hide-cur');
          if (fullBox) fullBox.classList.remove('hide-cur');
          var head = fb.correct ? T('hadith_right') : T('hadith_wrong', { A: fb.ar + ' — ' + fb.ru });
          /* «Дальше» — всегда кнопкой (11.10.2026, решение пользователя): кто-то
             читает и запоминает быстрее, кто-то медленнее; автолистание верного
             ответа (24.09–11.10) снято, как и в нахве. */
          document.getElementById('hd-after').innerHTML =
            '<div class="nh-fb"><div class="exp"><b>' + nahwArabic(head) + '</b></div></div>' +
            '<button class="tj-go" id="hd-next">' + T('hadith_next') + '</button>';
          var gone = false;
          var go = function () {
            if (gone) return;
            gone = true;
            clearTimeout(hadithAutoTimer);
            renderHadith(next);
          };
          document.getElementById('hd-next').addEventListener('click', go);
        });
      });
    });
  }

  // Список хадисов для «Сменить место» - номера 1..42, слова подтянет выбор.
  function hadithPickList() {
    var out = [];
    for (var n = 1; n <= 42; n++) out.push({ n: n });
    return out;
  }

  document.getElementById('hadith-back').addEventListener('click', function () {
    clearTimeout(hadithAutoTimer);
    document.getElementById('hadith').style.display = 'none';
    openTrainers();
  });

  document.getElementById('nahw-back').addEventListener('click', function () {
    document.getElementById('nahw').style.display = 'none';
    openTrainers();
  });

  document.getElementById('trainers-back').addEventListener('click', function () {
    document.getElementById('trainers').style.display = 'none';
    document.getElementById('dashboard').style.display = 'flex';
    if (typeof pulseIntroStart === 'function') pulseIntroStart();
  });
  document.getElementById('tajweed-back').addEventListener('click', function () {
    document.getElementById('tajweed').style.display = 'none';
    openTrainers();
  });

  /* Шапка тренажёра подписана по экрану (09.09.2026, общее правило
     навигации): на карточке - "← Дашборд" и заголовок "Тренажёр", в
     рейтинге - "← Тренажёр" и заголовок "Рейтинг" (иначе слева и в центре
     стояло бы одно и то же слово). Ставится в renderTrainer/endSession/
     showLeaderboard, поэтому шапка сама возвращается к прежней при любом
     уходе с рейтинга. */
  var trainerScreen = 'card';
  function setTrainerScreen(name) {
    trainerScreen = name;
    var rating = name === 'rating';
    document.getElementById('trainer-back').textContent =
      rating ? T('back_trainer') : T('back_trainers');
    document.getElementById('trainer-bookmark').textContent =
      rating ? T('trainer_rating_title') : T('trainers_words');
  }

  document.getElementById('trainer-back').addEventListener('click', function () {
    if (trainerScreen === 'rating') { renderTrainer(); return; }
    // С карточки «Слов» - в «Тренажёры», откуда и зашли (14.09.2026).
    document.getElementById('trainer').style.display = 'none';
    openTrainers();
  });

  // Название дивизиона приходит с сервера готовой РУССКОЙ строкой (она же
  // идёт в /muftop в чате). Для приложения бэкенд шлёт рядом division_no -
  // по нему берём перевод, а label оставляем запасным вариантом: старый
  // ответ сервера без номера не должен ломать экран.
  function divisionLabel(obj) {
    if (obj && obj.division_no && I18N[UI_LANG]['division_' + obj.division_no]) {
      return ICON.medal + ' ' + T('division_' + obj.division_no);
    }
    return (obj && obj.label) || '';
  }

  function renderFeedbackBanner(feedback) {
    if (!feedback) return '';
    // Одна и та же структура на оба исхода - "значок · арабское слово ·
    // перевод" (30.08.2026), меняются только иконка и цвет. Раньше при
    // верном ответе было сухое "✅ Верно!" без слова, а при неверном -
    // "правильно: <перевод>" тоже без слова, хотя на экране уже отрисован
    // СЛЕДУЮЩИЙ вопрос: понять, к чему относится перевод, было нельзя
    // (поймал пользователь). Показ пары "слово - смысл" ещё раз работает
    // на запоминание и в случае верного ответа, а одинаковое место и
    // формат избавляют от поиска информации заново.
    var cls = feedback.correct ? 'ok' : 'no';
    var icon = feedback.correct ? ICON['circle-check'].replace('class="ic"', 'class="ic ok"') : ICON['circle-x'].replace('class="ic"', 'class="ic no"');
    var ar = feedback.arabic
      ? '<span class="trainer-feedback-ar">' + feedback.arabic + '</span> — ' : '';
    var html = '<div class="trainer-feedback ' + cls + '">' + icon + ' ' + ar +
      feedback.target + '</div>';
    // Что осталось до зачёта «Слова» (15.09.2026, второй порог): пока не
    // хватает и слов, и верных - одна фраза про оба; 40 слов уже есть -
    // прямо говорим, что нужны верные, иначе привыкшие к «40 и всё» не
    // поймут, почему зачёт не пришёл.
    var leftW = feedback.remaining_for_task || 0, leftC = feedback.remaining_correct || 0;
    var hint = leftW > 0 && leftC > 0 ? T('daily_left_both', { N: leftW, C: leftC })
      : leftW > 0 ? T('daily_left', { N: leftW })
      : leftC > 0 ? T('daily_left_correct', { C: leftC, M: (trainerState && trainerState.daily_target) || '' })
      : '';
    if (hint) html += '<div class="trainer-hint">' + hint + '</div>';
    return html;
  }

  // «Выучено N% слов до стр. B» (11.11.2026): одна понятная цифра вместо
  // «Общий вес 9.81/10». Полоса - тоже по выученным словам, без частичного
  // зачёта ступенек: что на ней, то и в цифре. percent приходит с сервера
  // (вниз); у старого ответа без него считаем так же здесь.
  function renderOverallScore(s, page) {
    if (!s || !s.total) return '';
    var pct = s.percent != null ? s.percent : Math.floor(100 * s.mastered / s.total);
    var full = s.mastered >= s.total;
    var head = T('learned_line', { P: pct, N: page || '' }) + (full ? ' ✓' : '');
    var sub = full ? T('learned_of_all', { N: s.mastered, M: s.total })
      : T('learned_of', { N: s.mastered, M: s.total, R: s.total - s.mastered });
    var w = Math.max(0, Math.min(100, 100 * s.mastered / s.total));
    return '<div class="trainer-learned"><b>' + head + '</b>' +
      '<div class="trainer-score-bar"><div class="trainer-score-bar-fill" style="width:' + w + '%"></div></div>' +
      '<span>' + sub + '</span></div>';
  }

  function renderDailyBadge(d) {
    // Постоянный счётчик в шапке, не только в фидбеке после ответа - см.
    // комментарий у #trainer-daily в CSS. daily_target с бэкенда
    // (DAILY_WORDS_FOR_TASK_CREDIT), не захардкожен во фронтенде - единый
    // источник истины, значение меняли уже дважды (20 → 15 → 20 → 40).
    var el = document.getElementById('trainer-daily');
    if (!d || d.daily_target == null) { el.textContent = ''; el.classList.remove('done'); return; }
    // Зелёная - только по daily_done с бэкенда (оба порога, 15.09.2026).
    el.textContent = d.daily_correct_target != null
      ? T('daily_words_n', { N: d.daily_count, M: d.daily_target, C: d.daily_correct, K: d.daily_correct_target })
      : T('daily_n', { N: d.daily_count, M: d.daily_target });
    el.classList.toggle('done', !!d.daily_done);
  }

  function renderTrainer() {
    var d = trainerState;
    var body = document.getElementById('trainer-body');
    setTrainerScreen('card');
    renderDailyBadge(d);
    if (!d) { body.innerHTML = ''; return; }

    if (d.needs_page) {
      body.innerHTML =
        '<div class="trainer-msg">' + T('which_page_range', { A: d.first_page, B: d.last_page }) + '</div>' +
        '<div class="trainer-page-input">' +
        '<input id="tp-input" type="number" inputmode="numeric" min="' + d.first_page + '" max="' + d.last_page + '">' +
        '<button id="tp-submit">' + T('btn_start') + '</button></div>';
      document.getElementById('tp-submit').addEventListener('click', function () {
        var n = parseInt(document.getElementById('tp-input').value, 10);
        if (!n) return;
        withAuthCheck(apiCall('/page', { method: 'POST', body: { page: n } }), function (data) {
          if (data) trail('wpage', { p: data.bookmark_page, n: 'ввод' });
          trainerState = data; renderTrainer();
        });
      });
      return;
    }

    if (d.empty) {
      body.innerHTML = renderFeedbackBanner(d.feedback) +
        '<div class="trainer-msg">' + T('trainer_empty') + '</div>' +
        renderOverallScore(d.overall_score, d.bookmark_page) +
        '<div class="trainer-pagebar"><button id="tr-inc">➕</button></div>';
      document.getElementById('tr-inc').addEventListener('click', function () { stepPage(1); });
      return;
    }

    // Порядок блоков (30.08.2026): контекст -> задача -> действие -> прогресс.
    // Раньше между словом и вариантами вклинивались "Верно за сеанс" (с
    // 15.09.2026 - «верно сегодня», счёт за день, а не за сеанс) и
    // "Общий вес" с полосой - две строки статистики отодвигали кнопки от
    // вопроса, и взгляд метался между ними. Заодно контекст был разорван:
    // страница сверху, счёт за сеанс в середине. Теперь это одна мелкая
    // строка, а прогресс уехал под варианты - он важен, но не в момент
    // выбора ответа.
    /* Слово в своей строке мусхафа (22.09.2026, решение пользователя):
       вспоминают перевод по соседям - так крепче связь с аятом, и строка
       снимает двусмысленность (перевод дан для ЭТОГО места). Строка вынута
       отдельно и может лечь в два ряда - здесь важнее прочесть, чем узнать
       вид листа (в заучивании - наоборот). Пока строка грузится - слово
       одно, как раньше. Убрано: «стр. N · слово со стр. N · верно» (счёт
       и так в шапке, место видно по строке) и «Общий вес» (он на экране
       «Закончить»). */
    var html = renderFeedbackBanner(d.feedback);
    // Повтор выученного (19.10.2026): новых слов до закладки не осталось,
    // спрашиваются закреплённые - пусть человек знает, что это не сбой.
    if (d.review) html += '<div class="trainer-info">' + T('trainer_review', { N: d.bookmark_page }) + '</div>';
    html += '<div class="trainer-ctx" id="tr-ctx"><div class="trainer-word">' + d.arabic + '</div></div>';
    html += '<div class="trainer-options">';
    d.options.forEach(function (opt, i) {
      html += '<button class="trainer-opt" data-slot="' + i + '">' + opt + '</button>';
    });
    html += '</div>';
    // ➖ ➕ подписаны: без подписи посреди вопроса они читались загадкой.
    html += '<div class="trainer-pagebar"><button id="tr-dec">➖</button>' +
      '<span class="trainer-range">' + T('trainer_range_to', { N: d.bookmark_page }) + '</span>' +
      '<button id="tr-inc">➕</button></div>';
    html += trainerPlaceHint(d);
    html += '<div class="trainer-actions"><button id="tr-end">' + ICON['circle-check'] + ' ' + T('btn_finish') +
      '</button><button id="tr-top">' + ICON.trophy + ' ' + T('btn_rating') + '</button></div>';
    body.innerHTML = html;

    Array.prototype.forEach.call(body.querySelectorAll('.trainer-opt'), function (btn) {
      btn.addEventListener('click', function () {
        pickAnswer(d.word_id, parseInt(btn.getAttribute('data-slot'), 10));
      });
    });
    document.getElementById('tr-dec').addEventListener('click', function () { stepPage(-1); });
    document.getElementById('tr-inc').addEventListener('click', function () { stepPage(1); });
    document.getElementById('tr-end').addEventListener('click', endSession);
    document.getElementById('tr-top').addEventListener('click', showLeaderboard);
    var myPlace = document.getElementById('tr-myplace');
    if (myPlace) myPlace.addEventListener('click', function () {
      myPlace.disabled = true;
      withAuthCheck(apiCall('/page', { method: 'POST', body: { page: d.hifz_page } }), function (data) {
        if (data) trail('wpage', { p: data.bookmark_page, n: 'моё место' });
        trainerState = data; renderTrainer();
      });
    });
    trainerLineShow(d);
  }

  /* Закладка тренажёра и место заучивания (28.09.2026). ➖/➕ остались -
     тренировать слова наперёд можно, - но в рейтинг идёт меньшее из двух
     (core/mufradat.py: rating_depth). Отстала закладка - подсказка и кнопка
     «На моё место»; ушла вперёд - одна строка, без кнопки. */
  function trainerPlaceHint(d) {
    var h = d.hifz_page, b = d.bookmark_page;
    if (!h || !b || h === b) return '';
    if (b < h) {
      return '<div class="trainer-hint"><span>' + T('hint_behind', { H: h, B: b }) +
        '</span><button id="tr-myplace">' + T('btn_to_my_place') + '</button></div>';
    }
    return '<div class="trainer-hint"><span>' + T('hint_ahead', { H: h }) + '</span></div>';
  }

  // Строка рейтинга - одна и та же у лидеров и у себя (28.09.2026).
  // В строке - всё, что решает место (11.11.2026): точность, сколько разных
  // слов тренировал (attempted) и страница. Раньше было «83% (17081/20578)»,
  // и человек с 91% выше человека с 97% выглядел несправедливо.
  function lbResultText(e) {
    var words = e.attempted != null
      ? ' · ' + T(ruPluralKey('lb_words', e.attempted), { N: e.attempted }) : '';
    return e.accuracy.toFixed(0) + '%' + words + ' · ' + T('page_n', { N: e.page });
  }

  function lbRowText(place, e) {
    return place + '. ' + e.name + ' (' + e.group + ') — ' + lbResultText(e);
  }

  /* Строка мусхафа со словом вопроса. Лист берём тем же page*.json, что
     читает мусхаф (кэш на сеанс). Слово ищется по точному месту: аят может
     начаться на одном листе и кончиться на следующем, поэтому смотрим оба.
     Склеенное слово («مِن قَبْلِكُمْ» - одна голова с переводом на
     несколько слов) выделяем целиком: сколько слов в arabic, столько и
     красим подряд. */
  var trainerPages = {};
  function trainerPageLines(page) {
    if (trainerPages[page]) return trainerPages[page];
    trainerPages[page] = fetch('page' + page + '.json')
      .then(function (r) { if (!r.ok) throw new Error('page ' + page); return r.json(); })
      .then(function (data) {
        var lines = (data.lines || []).filter(function (l) { return l.type === 'text'; });
        lines.fontUrl = data.font_url;   // шрифт V4 листа - для строки глифами
        return lines;
      })
      .catch(function () { delete trainerPages[page]; return []; });
    return trainerPages[page];
  }
  function trainerFindLine(lines, d) {
    for (var i = 0; i < lines.length; i++) {
      var toks = lines[i].tokens || [];
      for (var j = 0; j < toks.length; j++) {
        var t = toks[j];
        if (t.type === 'word' && t.surah === d.word_surah && t.ayah === d.word_ayah && t.position === d.word_pos) {
          return { tokens: toks, at: j, fontUrl: lines.fontUrl };
        }
      }
    }
    return null;
  }
  function trainerLineShow(d) {
    if (!d || !d.word_pos || !d.word_page) return;
    var wordId = d.word_id;
    Promise.all([trainerPageLines(d.word_page), trainerPageLines(d.word_page + 1)]).then(function (res) {
      var box = document.getElementById('tr-ctx');
      // Пока грузилось, ответили и пришёл другой вопрос - не наш.
      if (!box || !trainerState || trainerState.word_id !== wordId) return;
      var hit = trainerFindLine(res[0], d) || trainerFindLine(res[1], d);
      if (!hit) return;
      trainerLineFont(hit.fontUrl).then(function (v4) {
        if (!trainerState || trainerState.word_id !== wordId) return;
        box.innerHTML = '<div class="trainer-line">' + trainerLineHtml(hit, d, v4) + '</div>';
        box.classList.add('has-line');
      });
    });
  }

  /* Строка глифами мусхафа (23.09.2026, Нур с айфона). Раньше строка шла
     обычным текстом с метками таджвида <tajweed>, а Safari на iOS не
     склеивает буквы через границу метки - слово рвалось на куски
     («ٱ|ل|دَّرْكِ», «ت|َجِدَ»). Глиф V4 - цельное слово, цвета внутри
     шрифта, рваться нечему. Шрифт свой у листа, семейство отдельное
     ('trainer-v4'), чтобы не сбить лист, открытый в мусхафе. Не загрузился
     шрифт - строка простым текстом БЕЗ меток: пусть без цвета, но цельная. */
  /* trainerV4Want - лист последней строки (02.10.2026, Нурсултан с айфона).
     Ответил быстро: шрифт прошлого листа ещё качался, новая строка взяла уже
     стоящий шрифт своего листа, а потом докачался старый и подменил его -
     глифы стр. 15 нарисовались буквами стр. 4, выделенное слово стало чужим,
     и среди вариантов «нет верного». Опоздавший шрифт теперь не ставится. */
  var trainerV4Face = null, trainerV4Url = null, trainerV4Want = null;
  function trainerLineFont(url) {
    trainerV4Want = url;
    if (!url || typeof FontFace === 'undefined') return Promise.resolve(false);
    if (url === trainerV4Url) return Promise.resolve(true);
    // loadV4Face - с зеркалом (02.11.2026, у tarteel пропал p328). Сверка
    // опоздания - по исходному адресу url, зеркало её не сбивает.
    return loadV4Face('trainer-v4', url).then(function (loaded) {
      if (trainerV4Want !== url) return false;
      if (trainerV4Face) { try { document.fonts.delete(trainerV4Face); } catch (e) {} }
      document.fonts.add(loaded);
      trainerV4Face = loaded; trainerV4Url = url;
      return true;
    }).catch(function () { return false; });
  }
  function trainerLineHtml(hit, d, v4) {
    var glued = String(d.arabic).trim().split(/\s+/).length;
    var html = '', lit = 0;
    hit.tokens.forEach(function (t, k) {
      if (t.type === 'word') {
        var on = k >= hit.at && lit < glued;
        if (on) lit++;
        var glyph = v4 && t.code_v4 && !t.fp;
        html += '<span class="tl-w' + (glyph ? ' tl-v4' : '') + (on ? ' on' : '') + '">' +
          (glyph ? t.code_v4 : String(t.html || '').replace(/<[^>]*>/g, '')) + '</span>';
      } else if (t.type === 'ayah_end') {
        html += '<span class="tl-ae">' + t.html + '</span>';
      }
    });
    return html;
  }

  function pickAnswer(wordId, slot) {
    withAuthCheck(apiCall('/answer', { method: 'POST', body: { word_id: wordId, slot: slot } }), function (data) {
      trainerState = data; renderTrainer();
    });
  }

  function stepPage(delta) {
    withAuthCheck(apiCall('/page', { method: 'POST', body: { delta: delta } }), function (data) {
      if (data) trail('wpage', { p: data.bookmark_page, n: delta > 0 ? '+' + delta : String(delta) });
      trainerState = data; renderTrainer();
    });
  }

  function endSession() {
    /* Экран итога рисуется здесь, а не через renderTrainer, - подпись
       возврата ставим явно, чтобы она не зависела от того, откуда пришли
       (09.09.2026). */
    setTrainerScreen('card');
    withAuthCheck(apiCall('/end', { method: 'POST' }), function (d) {
      var html = '<div class="trainer-msg">' + T('session_done') + '</div>';
      var sc = d.overall_score;
      html += renderOverallScore(sc, d.bookmark_page);
      if (sc) trail('wend', { p: d.bookmark_page, n: sc.mastered + '/' + sc.total });
      // Итог в словах (11.11.2026). Было «Вес за сеанс не изменился -
      // каждый верный ответ его двигает» даже у того, у кого всё выучено:
      // выше 10 расти некуда, и фраза говорила неправду (Толкун).
      var info = '';
      if (sc && sc.total && sc.mastered >= sc.total) {
        info = T('gained_all', { N: (d.bookmark_page || 0) + 1 });
      } else if (typeof d.gained === 'number' && d.gained > 0) {
        info = T(ruPluralKey('gained_up', d.gained), { N: d.gained });
      } else if (typeof d.gained === 'number' && d.gained < 0) {
        info = T(ruPluralKey('gained_down', -d.gained), { N: -d.gained });
      } else if (typeof d.gained === 'number') {
        info = T('gained_same');
      }
      if (info) html += '<div class="trainer-info">' + info + '</div>';
      // Точность за последние дни, а не за всё время: та почти не движется.
      // Нет 20 ответов за окно - строки нет (одна ошибка из трёх = «67%»).
      if (d.recent) {
        html += '<div class="trainer-info">' + T(ruPluralKey('recent_acc', d.recent.days), {
          D: d.recent.days, P: d.recent.accuracy, C: d.recent.correct, T: d.recent.n,
        }) + '</div>';
      }
      if (d.rank) {
        html += '<div class="trainer-info">' + ICON.trophy + ' ' + T('rank_line', {
          D: divisionLabel(d.rank),
          X: T('x_of_y', { P: d.rank.place, T: d.rank.total }),
        }) + '</div>';
      }
      html += '<div class="trainer-actions"><button id="tr-restart">' + ICON.repeat + ' ' + T('btn_new_card') + '</button></div>';
      document.getElementById('trainer-body').innerHTML = html;
      document.getElementById('tr-restart').addEventListener('click', openTrainer);
    });
  }

  function showLeaderboard() {
    setTrainerScreen('rating');
    withAuthCheck(apiCall('/leaderboard'), function (d) {
      var html = '<div class="trainer-msg">' + ICON.trophy + ' ' + T('top_title') + '</div>' +
        '<div class="trainer-lb-order">' + T('lb_order') + '</div>';
      if (!d.in_group) {
        html += d.personal
          ? '<div class="trainer-info">' + T('rank_among', {
              X: T('x_of_y', { P: d.personal.rank, T: d.total }),
            }) + '</div>' +
            '<div class="trainer-lb-row you">' + T('my_result', { R: lbResultText(d.personal.score) }) + '</div>'
          : '<div class="trainer-info">' + T('no_rank_yet') + '</div>';
      } else {
        var me = d.me;
        d.divisions.forEach(function (div) {
          if (!div.entries.length) return;
          html += '<div class="trainer-division">' + divisionLabel(div) + '</div>';
          div.entries.slice(0, 7).forEach(function (e, i) {
            html += '<div class="trainer-lb-row' + (e.you ? ' you' : '') + '">' + lbRowText(i + 1, e) + '</div>';
          });
          // Себя под семёркой - та же строка, что у лидеров (28.09.2026).
          if (me && me.division_no === div.division_no && me.place > 7) {
            html += '<div class="trainer-lb-gap">…</div>' +
              '<div class="trainer-lb-row you">' + lbRowText(me.place, me) +
              ' · ' + T('x_of_y', { P: me.place, T: me.total }) + '</div>';
          }
        });
        if (me && me.hidden) {
          html += '<div class="trainer-info">' + (me.idle_days
              ? T('lb_hidden', { D: me.idle_days }) : T('lb_hidden_long')) + '</div>' +
            '<div class="trainer-lb-row you">' + T('my_result', { R: lbResultText(me) }) + '</div>';
        }
      }
      document.getElementById('trainer-body').innerHTML = html;
    });
  }

