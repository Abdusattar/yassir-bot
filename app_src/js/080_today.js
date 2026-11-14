  /* ══ «Сегодня» по макету (11.11.2026) ══════════════════════════════════
     Карточка дня, чек-лист и карточка устаза рисуются из тех же фактов
     heartbeat, что и прежний дашборд: day.tasks (k: m r t j n h, done),
     hifz {page, line, stage}, words/tajweed/nahw/hadith, subs. Строчка
     дня - текстом из page*.json (запасной шрифт, не глифы V4: шрифт
     листа живёт только в мусхафе). */
  var dashPageCache = {};
  function dashPage(n, cb) {
    if (!n) return;
    if (dashPageCache[n]) { cb(dashPageCache[n]); return; }
    fetchPageData(n).catch(function () { return null; })
      .then(function (d) { if (d) { dashPageCache[n] = d; cb(d); } }).catch(function () {});
  }
  function dashTextLines(d) {
    return (d.lines || []).filter(function (l) { return l.type === 'text'; });
  }
  function dashLineWords(line) {
    return (line.tokens || []).filter(function (t) { return t.type === 'word'; });
  }
  function dashBare(h) { return String(h || '').replace(/<[^>]*>/g, ''); }
  /* Имена сур по-русски для подписи карточки дня (11.11.2026, как в макете
     «Хифз»: «Аль-Бакара · 2:6–7»). Для ky/uz та же кириллица; для zh -
     арабское имя из SURAH_INDEX. */
  var SURAH_RU = [
    'Аль-Фатиха','Аль-Бакара','Аль Имран','Ан-Ниса','Аль-Маида','Аль-Анам',
    'Аль-Араф','Аль-Анфаль','Ат-Тауба','Юнус','Худ','Юсуф',
    'Ар-Рад','Ибрахим','Аль-Хиджр','Ан-Нахль','Аль-Исра','Аль-Кахф',
    'Марьям','Та Ха','Аль-Анбия','Аль-Хадж','Аль-Муминун','Ан-Нур',
    'Аль-Фуркан','Аш-Шуара','Ан-Намль','Аль-Касас','Аль-Анкабут','Ар-Рум',
    'Лукман','Ас-Саджда','Аль-Ахзаб','Саба','Фатыр','Ясин',
    'Ас-Саффат','Сад','Аз-Зумар','Гафир','Фуссилят','Аш-Шура',
    'Аз-Зухруф','Ад-Духан','Аль-Джасия','Аль-Ахкаф','Мухаммад','Аль-Фатх',
    'Аль-Худжурат','Каф','Аз-Зарият','Ат-Тур','Ан-Наджм','Аль-Камар',
    'Ар-Рахман','Аль-Вакиа','Аль-Хадид','Аль-Муджадаля','Аль-Хашр','Аль-Мумтахана',
    'Ас-Сафф','Аль-Джума','Аль-Мунафикун','Ат-Тагабун','Ат-Талак','Ат-Тахрим',
    'Аль-Мульк','Аль-Калям','Аль-Хакка','Аль-Мааридж','Нух','Аль-Джинн',
    'Аль-Муззаммиль','Аль-Муддассир','Аль-Кияма','Аль-Инсан','Аль-Мурсалят','Ан-Наба',
    'Ан-Назиат','Абаса','Ат-Таквир','Аль-Инфитар','Аль-Мутаффифин','Аль-Иншикак',
    'Аль-Бурудж','Ат-Тарик','Аль-Аля','Аль-Гашия','Аль-Фаджр','Аль-Баляд',
    'Аш-Шамс','Аль-Лейль','Ад-Духа','Аш-Шарх','Ат-Тин','Аль-Аляк',
    'Аль-Кадр','Аль-Баййина','Аз-Зальзаля','Аль-Адият','Аль-Кариа','Ат-Такасур',
    'Аль-Аср','Аль-Хумаза','Аль-Филь','Курайш','Аль-Маун','Аль-Каусар',
    'Аль-Кафирун','Ан-Наср','Аль-Масад','Аль-Ихлас','Аль-Фаляк','Ан-Нас'
  ];
  function dashSuraLabel(lines) {
    var sn = 0, a1 = 0, a2 = 0;
    lines.forEach(function (line) {
      (line.tokens || []).forEach(function (t) {
        if (t.type !== 'word' || !t.surah) return;
        if (!sn) { sn = t.surah; }
        if (t.surah !== sn) return;
        if (!a1 || t.ayah < a1) a1 = t.ayah;
        if (t.ayah > a2) a2 = t.ayah;
      });
    });
    if (!sn) return '';
    var name = UI_LANG === 'zh' ? (SURAH_INDEX[sn - 1] || [])[1] : SURAH_RU[sn - 1];
    return (name || '') + ' \u00b7 ' + sn + ':' + a1 + (a2 > a1 ? '\u2013' + a2 : '');
  }
  /* Связка (11.11.2026, правка пользователя): строка учится до начала
     следующей - те же токены, что берёт hifzTailTokens в мусхафе, то же
     правило длины слова и конца аята. С другого листа (foreign) - обычным
     текстом: глифы чужого листа в шрифте этого были бы чужими словами. */
  function dashTailCount(next) {
    if (!next || !next.tokens) return 0;
    var taken = 0, last = -1;
    for (var i = 0; i < next.tokens.length && taken < 3; i++) {
      var t = next.tokens[i];
      if (t.type !== 'word') continue;
      taken++; last = i;
      var after = next.tokens[i + 1];
      if (taken === 1 && hifzBaseLen(t.html) > 3) { if (!after || after.type !== 'ayah_end') break; }
      else if (taken >= 2) { if (!after || after.type !== 'ayah_end') break; }
    }
    return last + 1;
  }
  /* Строка дня глифами мусхафа (11.11.2026, правка пользователя: «как в
     мусхафе, а не арабская надпись»). Тот же приём, что trainerLineFont:
     шрифт листа своим семейством, опоздавший ответ не ставится, не
     загрузился - строка обычным текстом. */
  var dashV4Face = null, dashV4Url = null, dashV4Want = null;
  function dashLineFont(url) {
    dashV4Want = url;
    if (!url || typeof FontFace === 'undefined') return Promise.resolve(false);
    if (url === dashV4Url) return Promise.resolve(true);
    return loadV4Face('today-v4', url).then(function (loaded) {
      if (dashV4Want !== url) return false;
      if (dashV4Face) { try { document.fonts.delete(dashV4Face); } catch (e) {} }
      document.fonts.add(loaded);
      dashV4Face = loaded; dashV4Url = url;
      return true;
    }).catch(function () { return false; });
  }
  function dashLineHtml(line, v4, tail, foreign) {
    var html = '';
    var put = function (t, extra, plain) {
      var glyph = !plain && v4 && t.code_v4 && !t.fp;
      if (t.type === 'word') {
        html += '<span class="' + (glyph ? 'td-v4' : 'td-w') + extra + '">' + (glyph ? t.code_v4 : dashBare(t.html)) + '</span>';
      } else if (t.type === 'ayah_end') {
        html += '<span class="' + (glyph ? 'td-v4' : 'td-ae') + extra + '">' + (glyph ? t.code_v4 : '\uFD3E' + dashBare(t.html) + '\uFD3F') + '</span>';
      }
    };
    (line.tokens || []).forEach(function (t) { put(t, '', false); });
    var out = '<div class="h-line v4line">' + html + '</div>';
    // Связка отдельной строкой под основной, как на листе (там она - начало
    // следующей строки); кегль берёт у основной в dashFitLines.
    if (tail && tail.length) {
      html = '';
      tail.forEach(function (t) { put(t, ' td-tail', !!foreign); });
      out += '<div class="h-line v4line v4tail">' + html + '</div>';
    }
    return out;
  }
  // Одна строка, как на листе: кегль по ширине карточки. Ширина нулевая,
  // пока вкладка скрыта, - тогда повтор при показе вкладки (tabsGo).
  function dashFitLines() {
    var els = document.querySelectorAll('#dash-hero .h-line.v4line:not(.v4tail)');
    var tails = document.querySelectorAll('#dash-hero .v4tail');
    for (var j = 0; j < tails.length; j++) {
      var prev = tails[j].previousElementSibling;
      if (prev) tails[j].style.fontSize = (prev.style.fontSize || getComputedStyle(prev).fontSize);
    }
    for (var i = 0; i < els.length; i++) {
      var el = els[i]; el.style.fontSize = '';
      var cs = getComputedStyle(el);
      var room = el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      if (!(room > 0)) continue;
      var need = 0;
      for (var k = 0; k < el.children.length; k++) need += el.children[k].getBoundingClientRect().width;
      if (need > room) el.style.fontSize = Math.max(13, parseFloat(cs.fontSize) * room / need * 0.985).toFixed(1) + 'px';
      var tl = el.nextElementSibling;
      if (tl && tl.classList.contains('v4tail')) tl.style.fontSize = el.style.fontSize || getComputedStyle(el).fontSize;
    }
  }
  window.addEventListener('resize', dashFitLines);
  function dashTask(f, k) {
    var day = f && f.day, out = null;
    ((day && day.tasks) || []).forEach(function (t) { if (t.k === k) out = t; });
    return out;
  }
  function dashPlace(h) {
    if (!h || !h.page) return '';
    return h.stage === 3 ? T('ustaz_place_page', { P: h.page })
      : h.stage === 2 ? T('ustaz_place_half', { P: h.page })
      : T('ustaz_place', { P: h.page, L: (h.line || 0) + 1 });
  }
  var DASH_LOCALE = { ru: 'ru-RU', ky: 'ky-KG', uz: 'uz-UZ', zh: 'zh-CN' };
  function dashHead(f) {
    document.getElementById('dash-title-t').textContent = T('tab_today');
    var d = new Date(), loc = DASH_LOCALE[UI_LANG] || 'ru-RU', txt = '';
    try { txt = '· ' + d.toLocaleDateString(loc, { weekday: 'long', day: 'numeric', month: 'long' }); } catch (e) {}
    document.getElementById('dash-date').textContent = txt;
    var day = f && f.day;
    document.getElementById('dash-count').textContent = day && day.total
      ? (day.done >= day.total ? T('today_closed') : T('my_day_of', { N: day.done, M: day.total })) : '';
  }
  // Переходы из карточки и чек-листа - теми же дверями, что были.
  function dashGoHifz() {
    openMushaf('page');
    setTimeout(function () { var b = document.getElementById('btn-hifz'); if (b && !hifz.on) b.click(); }, 350);
  }
  function dashGoRevision() {
    openMushaf('page');
    setTimeout(function () { var b = document.getElementById('btn-revision'); if (b) b.click(); }, 350);
  }
  function dashGo(k) {
    if (k === 'm') dashGoHifz();
    else if (k === 'r') dashGoRevision();
    else if (k === 't') openTrainer();
    else if (k === 'j') openTajweed();
    else if (k === 'n') openNahw();
    else if (k === 'h') openHadith();
  }
  var dashHeroReq = 0;
  function dashHero(f) {
    var sura = document.getElementById('dash-hero-sura'), place = document.getElementById('dash-hero-place');
    var body = document.getElementById('dash-hero-body'), row = document.getElementById('dash-hero-row');
    var h = f.hifz || {}, m = dashTask(f, 'm'), r = dashTask(f, 'r'), t = dashTask(f, 't');
    var retake = f.subs && f.subs.retake > 0;
    var btn = function (k, label, primary, icon) {
      return '<button class="d-btn' + (primary ? ' primary' : '') + '" data-dash-go="' + k + '">' + (icon || '') + label + '</button>';
    };
    sura.textContent = ''; place.textContent = dashPlace(h); body.innerHTML = ''; row.innerHTML = '';
    var req = ++dashHeroReq;
    var showLine = function () {
      if (!h.page) return;
      dashPage(h.page, function (d) {
        if (req !== dashHeroReq) return;
        var lines = dashTextLines(d), n = lines.length;
        if (!n) return;
        dashLineFont(d.font_url).then(function (v4) {
          if (req !== dashHeroReq) return;
          paint(lines, n, v4);
          dashFitLines();
        });
      });
    };
    var paint = function (lines, n, v4) {
        if (!h.stage || h.stage === 1) {
          var idx = h.line || 0, line = lines[idx];
          if (!line) return;
          var done = function (next, foreign) {
            if (req !== dashHeroReq) return;
            var k = dashTailCount(next), tail = next ? next.tokens.slice(0, k) : [];
            sura.textContent = dashSuraLabel([line, { tokens: tail }]);
            body.innerHTML = dashLineHtml(line, v4, tail, foreign);
            dashFitLines();
          };
          if (idx + 1 < n) done(lines[idx + 1], false);
          else if (h.page < LAST_PAGE) { done(null); dashPage(h.page + 1, function (d2) { done(dashTextLines(d2)[0], true); }); }
          else done(null);
          return;
        }
        // Этап 2 - половина листа (первая floor(n/2) строк, как hifzHalf),
        // этап 3 - весь лист: карта, первая строка части и «до строчки N».
        var mid = Math.floor(n / 2), from = 0, to = n - 1;
        if (h.stage === 2) { if ((h.line || 0) < mid) { to = mid - 1; } else { from = mid; } }
        place.textContent = T('page_n', { N: h.page }) + ' · ' + T('hero_stage', { S: h.stage });
        sura.textContent = dashSuraLabel(lines.slice(from, to + 1));
        var map = '';
        for (var i = 0; i < n; i++) map += '<i class="' + (i >= from && i <= to ? 'on' : '') + '"></i>';
        // Строка во всю ширину карточки (как на этапе 1 - тем же кеглем,
        // что на листе), под ней миниатюра листа и «до строчки N».
        body.innerHTML = dashLineHtml(lines[from], v4) +
          '<div class="h-task"><div class="h-map">' + map + '</div>' +
          '<div class="h-to">' + T('hero_to_line', { N: to + 1 }) + '</div></div>';
    };
    if (retake) {
      place.textContent = dashPlace(h);
      body.innerHTML = '<p class="h-note">' + T('hero_redo_note', { N: f.subs.retake }) + '</p>';
      row.innerHTML = btn('subs', T('hero_redo'), true, ICON['rotate-ccw']);
    } else if (m && !m.done) {
      showLine();
      row.innerHTML = btn('m', T('hero_submit'), true, ICON.mic);
    } else if (r && !r.done) {
      sura.textContent = T('task_r'); place.textContent = T('hero_rep_s');
      body.innerHTML = '';
      row.innerHTML = btn('mushaf', T('hero_open'), false) + btn('r', T('hero_repeat'), true, ICON.repeat);
    } else if (t && !t.done) {
      sura.textContent = T('task_t');
      place.textContent = f.words ? T('daily_n', { N: f.words.done, M: f.words.target }) : '';
      row.innerHTML = btn('t', T('hero_words'), true);
    } else {
      sura.textContent = T('hero_all'); place.textContent = '';
      var left = ((f.day && f.day.tasks) || []).filter(function (x) { return !x.done; });
      if (left.length) {
        body.innerHTML = '<p class="h-note">' + T('hero_left', { N: left.map(function (x) { return dayTaskName(x.k); }).join(', ') }) + '</p>';
      } else if (m && m.done) {
        body.innerHTML = '<div class="h-lock">' + ICON.lock + '<span>' + T('hero_next_locked') + '</span></div>';
      }
      row.innerHTML = btn('mushaf', T('hero_open'), true, ICON['book-open']);
    }
  }
  function dashChecks(f) {
    var cap = document.getElementById('dash-checks-cap'), box = document.getElementById('dash-checks');
    var tasks = (f.day && f.day.tasks) || [];
    cap.textContent = T('today_checks');
    if (!tasks.length) { cap.style.display = 'none'; box.style.display = 'none'; return; }
    cap.style.display = ''; box.style.display = '';
    var sub = function (k) {
      if (k === 'm') return dashPlace(f.hifz) || T('task_m');
      if (k === 'r') return T('hero_rep_s');
      var x = k === 't' ? f.words : k === 'j' ? f.tajweed : k === 'n' ? f.nahw : k === 'h' ? f.hadith : null;
      return x && x.target != null ? T('daily_n', { N: x.done, M: x.target }) : '';
    };
    var act = function (k) { return k === 'm' ? T('check_rec') : k === 'r' ? T('check_mark') : T('check_go'); };
    box.innerHTML = tasks.map(function (t) {
      return '<div class="d-check' + (t.done ? ' done' : '') + '">' +
        '<span class="mk"><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7"/></svg></span>' +
        '<span class="bd"><span class="t">' + dayTaskName(t.k) + '</span><br><span class="s">' + sub(t.k) + '</span></span>' +
        (t.done ? '' : '<button class="d-btn sm" data-dash-go="' + t.k + '">' + act(t.k) + '</button>') + '</div>';
    }).join('');
  }
  function dashUstazCard(f) {
    var cap = document.getElementById('dash-ustaz-cap'), card = document.getElementById('dash-ustaz-card');
    cap.textContent = T('today_ustaz');
    var pill, t, sdesc, sb = f.subs || {};
    if (sb.retake > 0) { pill = ['redo', T('subs_verdict_retake')]; t = T('dash_subs_retake', { N: sb.retake }); sdesc = T('hero_redo_s'); }
    else if (sb.waiting > 0) { pill = ['wait', T('subs_verdict_wait')]; t = T('dash_subs_waiting', { N: sb.waiting }); sdesc = T('hero_wait_s'); }
    else { pill = ['', T('subs_verdict_ok')]; t = T('dash_subs'); sdesc = T('ustaz_card_sub'); }
    card.innerHTML = '<span class="d-pill ' + pill[0] + '">' + pill[1] + '</span>' +
      '<span class="bd"><span class="t">' + t + '</span><br><span class="s">' + sdesc + '</span></span>' +
      '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>';
  }
  function dashUstazRow() {
    var door = document.getElementById('dash-ustaz'), row = document.getElementById('dash-ustaz-row');
    var on = door && door.style.display !== 'none';
    row.style.display = on ? 'flex' : 'none';
    if (!on) return;
    document.querySelector('#dash-ustaz-row .d-ustaz-mk').innerHTML = ICON['user-check'];
    document.getElementById('dash-ustaz-row-t').textContent = T('ustaz_cab_row');
    var n = document.getElementById('dash-ustaz-count').textContent;
    document.getElementById('dash-ustaz-row-s').textContent = n ? T('ustaz_cab_sub', { N: n }) : T('dash_ustaz_sub');
    var pill = document.getElementById('dash-ustaz-row-n');
    pill.textContent = n; pill.style.display = n ? '' : 'none';
  }
  function dashToday(f) {
    dashHead(f); dashHero(f); dashChecks(f); dashUstazCard(f); dashUstazRow();
    // Устаз без своих заданий (не студент) - карточку дня и чек-лист не показываем.
    var hasTasks = !!(f.day && f.day.tasks && f.day.tasks.length);
    document.getElementById('dash-hero').style.display = hasTasks ? '' : 'none';
    var sum = document.getElementById('dash-jamaat-sum');
    if (sum && !sum.textContent) sum.textContent = T('jamaat_today');
  }
  document.getElementById('dashboard').addEventListener('click', function (e) {
    var b = e.target.closest('[data-dash-go]');
    if (b) {
      var k = b.getAttribute('data-dash-go');
      if (k === 'mushaf') openMushaf('page');
      else if (k === 'subs') openSubs();
      else dashGo(k);
      return;
    }
    if (e.target.closest('#dash-ustaz-card')) openSubs();
    else if (e.target.closest('#dash-ustaz-row')) document.getElementById('dash-ustaz').click();
  });
  // Счётчик джамаата в свёрнутой строке - зеркало #pulse-count.
  (function () {
    var cnt = document.getElementById('pulse-count'), sum = document.getElementById('dash-jamaat-sum');
    if (!cnt || !sum || !window.MutationObserver) return;
    new MutationObserver(function () {
      var n = cnt.textContent, online = (document.getElementById('dash-online') || {}).textContent || '';
      sum.textContent = T('jamaat_today') + (n ? ' · ' + n + ' ' + T('jamaat_acts') : '') + (online ? ' · ' + online : '');
    }).observe(cnt, { childList: true, characterData: true, subtree: true });
  })();

  function dashDay(day) {
    var box = document.getElementById('my-day');
    if (!day || !day.total) { box.classList.remove('on'); return; }
    document.getElementById('my-day-cap').innerHTML =
      '<span>' + T('my_day') + '</span><b>' +
      T('my_day_of', { N: day.done, M: day.total }) + '</b>';
    document.getElementById('my-day-bars').innerHTML = day.tasks.map(function (t) {
      return '<i class="' + (t.done ? 'on' : '') + '"></i>';
    }).join('');
    document.getElementById('my-day-names').innerHTML = day.tasks.map(function (t) {
      return '<span class="' + (t.done ? 'on' : '') + '">' + dayTaskName(t.k) + '</span>';
    }).join('');
    var night = document.getElementById('my-day-night');
    night.textContent = day.night ? T('my_day_night') : '';
    night.style.display = day.night ? '' : 'none';
    // Длинный набор (таджвид, нахв, хадис) - подписям нужен свой размер,
    // см. #dash-head #my-day.many.
    box.classList.toggle('many', day.tasks.length >= 5);
    box.classList.add('on');
  }

  function wordsCorrectSuffix(w) {
    if (!w || w.correct_target == null || w.complete || w.done < w.target) return '';
    return T('dash_words_correct', { C: w.correct, K: w.correct_target });
  }

  /* Выпуск из подготовительной (22.09.2026): карточку рисует факт из базы -
     prep_grad {ask, days} или {pending}; нет факта - нет карточки. */
  function dashGrad(g, moved) {
    var box = document.getElementById('dash-grad');
    if (moved) {
      document.getElementById('grad-h').textContent = T(lessonFemale() ? 'grad_title_f' : 'grad_title');
      document.getElementById('grad-t').textContent = T('grad_moved', { G: moved });
      // «Ты в группе» - итог, держим его полминуты, пульсы его не стирают.
      box.classList.add('on', 'wait', 'done');
      setTimeout(function () { box.classList.remove('on', 'wait', 'done'); }, 30000);
      return;
    }
    if (!g) { box.classList.remove('on', 'wait'); return; }
    document.getElementById('grad-h').textContent = T(lessonFemale() ? 'grad_title_f' : 'grad_title');
    document.getElementById('grad-t').textContent = g.pending ? T('grad_pending') : T('grad_ask', { N: g.days });
    document.getElementById('grad-yes').textContent = T('grad_yes');
    document.getElementById('grad-no').textContent = T('grad_no');
    box.classList.toggle('wait', !!g.pending);
    box.classList.remove('done');
    box.classList.add('on');
  }
  function gradAnswer(knows) {
    var btns = document.querySelectorAll('#grad-btns button');
    Array.prototype.forEach.call(btns, function (b) { b.disabled = true; });
    apiCall('/prep/juz', { method: 'POST', body: { knows: knows } }).then(function (res) {
      Array.prototype.forEach.call(btns, function (b) { b.disabled = false; });
      if (res.status === 401) return;
      var d = res.data || {};
      if (d.pending) dashGrad({ pending: true });
      else if (d.group) dashGrad(null, d.group);
      sendHeartbeat();
    }).catch(function () {
      Array.prototype.forEach.call(btns, function (b) { b.disabled = false; });
    });
  }
  document.getElementById('grad-yes').addEventListener('click', function () { gradAnswer(true); });
  document.getElementById('grad-no').addEventListener('click', function () { gradAnswer(false); });

  function dashFacts(f) {
    dashDay(f.day);
    mushafDoneMarks();
    if (!document.getElementById('dash-grad').classList.contains('done')) dashGrad(f.prep_grad);
    var mush = document.getElementById('dash-mushaf-sub');
    if (f.hifz && f.hifz.page) {
      var st = f.hifz.stage, page = f.hifz.page;
      mush.textContent = st === 3 ? T('ustaz_place_page', { P: page })
        : st === 2 ? T('ustaz_place_half', { P: page })
        : T('ustaz_place', { P: page, L: (f.hifz.line || 0) + 1 });
    }
    dashFactsLast = f;
    dashLearnSub(f);
    if (f.words) {
      // «✅ 14/20 верных» дописываем только в момент, когда 40 слов уже
      // есть, а зачёта нет (15.09.2026) - иначе на двери тесно, а полная
      // картина и так в пилюле тренажёра.
      var wc = wordsCorrectSuffix(f.words);
      var sub = f.tajweed
        ? T('dash_trainers_both', { N: f.words.done, M: f.words.target + (wc ? ' (' + wc + ')' : ''),
            A: f.tajweed.done, B: f.tajweed.target })
        : T('dash_words_today', { N: f.words.done, M: f.words.target }) + (wc ? ' · ' + wc : '');
      // Нахв (17.09.2026) дописывается третьим, если он есть у группы.
      if (f.nahw) sub += ' · ' + T('dash_trainers_nahw', { A: f.nahw.done, B: f.nahw.target });
      if (f.hadith) sub += ' · ' + T('dash_trainers_hadith', { A: f.hadith.done, B: f.hadith.target });
      document.getElementById('dash-trainer-sub').textContent = sub;
    }
    if (document.getElementById('trainers').style.display === 'flex') trainersRender();
    var subsSub = document.getElementById('dash-subs-sub');
    var subsCount = document.getElementById('dash-subs-count');
    if (f.subs) {
      // Пересдача - единственный настоящий долг студента, её и показываем
      // счётчиком. «На проверке» - очередь устаза, о ней спокойной строкой.
      if (f.subs.retake > 0) {
        subsSub.textContent = T('dash_subs_retake', { N: f.subs.retake });
        subsCount.textContent = f.subs.retake;
        subsCount.style.display = 'flex';
      } else {
        subsCount.style.display = 'none';
        subsSub.textContent = f.subs.waiting > 0
          ? T('dash_subs_waiting', { N: f.subs.waiting })
          : T('dash_subs_sub');
      }
    }
  }

  // «Сегодня» по макету перерисовывается теми же фактами (см. dashToday).
  var _dashFactsBase = dashFacts;
  dashFacts = function (f) { _dashFactsBase(f); try { dashToday(f); } catch (e) { console.error('dashToday', e); } };
  dashHead(null);

  setTimeout(sendHeartbeat, 0);
  setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS);

  // «Дыхание Яссира» (07.09.2026) — сердце из точек-людей и волна суток над
  // карточками. Числа настоящие (core/pulse.py, обе базы вместе), а вспышки —
  // не выдумка: раз в минуту сервер отдаёт новый счёт, разницу проигрываем
  // событиями по одному, распределив по следующей минуте. Поэтому каждая
  // вспышка — чьё-то реальное задание или разбор устаза, просто увиденное с
  // задержкой до минуты; когда в проекте тихо, экран честно молчит.
  var PULSE_REFRESH_MS = 60000;
  var pulse = {
    data: null, view: 0, today: 0, dots: [], ghost: [], shape: null,
    ripples: [], floats: [], queue: [], shown: 0, count: 0, tally: null,
    raf: 0, last: 0, slide: 1, from: 0, best: 0,
    // Разгон: день собирается на глазах, а не появляется готовым.
    intro: 0, introDur: 0, introAt: 0, introWord: 0,
    // Мерцание в тишине: сердце не должно замирать, когда никто не сдаёт.
    shimmer: 0, shimmerGap: 0
  };
  var PULSE_INTRO_GAP = 20000;    // не повторять разгон чаще раза в 20 секунд
  var PULSE_KINDS = ['m', 'r', 't', 'other', 'review'];

