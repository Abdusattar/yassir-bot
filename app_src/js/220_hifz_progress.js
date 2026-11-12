  /* ─── Захват прогресса 40+40 (03.09.2026) ──────────────────────────────
     Единица — (страница, этап, половина); половина имеет смысл только на
     этапе 2 (hifzHalf(line)), на этапе 3 всегда 0. Кэш по ключу - чтобы
     не дёргать сервер повторно, пока студент не ушёл на другую единицу. */
  var hifzProgressCache = {};
  function hifzProgressHalf() { return hifz.stage === 2 ? hifzHalf(hifz.line) : 0; }
  function hifzProgressKey(page, stage, half) { return page + ':' + stage + ':' + half; }

  // Число одно (0-80), фаза выводится из него - методика строго
  // последовательна (40 глядя, потом 40 не глядя), не два счётчика.
  function hifzProgressPhaseText(count) {
    if (count <= 0) return null;
    if (count >= HIFZ_PROGRESS_TARGET) return T('hifz_progress_done');
    if (count > 40) return T('hifz_progress_both', { N: count - 40 });
    return T('hifz_progress_looking_only', { N: count });
  }

  function hifzProgressEnsureLoaded(page, stage, half) {
    var key = hifzProgressKey(page, stage, half);
    if (hifzProgressCache[key]) return;
    hifzProgressCache[key] = { count: 0, target: HIFZ_PROGRESS_TARGET };
    apiCall('/hifz/progress?page=' + page + '&stage=' + stage + '&half=' + half).then(function (res) {
      if (res.status === 401 || !res.data) return;
      hifzProgressCache[key] = { count: res.data.count || 0, target: res.data.target || HIFZ_PROGRESS_TARGET };
      // Число могло уже стоять на шапке, пока грузилось - перерисовать,
      // только если студент всё ещё на этой же единице.
      if (hifz.on && !hifz.picking && hifzProgressKey(currentPage, hifz.stage, hifzProgressHalf()) === key) {
        hifzHead();
      }
      // Цифра у кнопки Хусари и в «Крупно» (14.09.2026, поймал пользователь:
      // стояла на нуле, пока не тапнешь). Перерисовка своя проверяет, что
      // счётчик виден и стоит на этой же единице.
      if (typeof hifzCountRender === 'function' && hifzCountKey === key) hifzCountRender();
    }).catch(function () {});
  }

  // Текст для #hifz-sub на этапах 2/3 - пока по единице ничего не
  // сдавалось (count === 0), показываем прежнюю общую подпись этапа.
  function hifzProgressSubText(stage, half) {
    hifzProgressEnsureLoaded(currentPage, stage, half);
    var p = hifzProgressCache[hifzProgressKey(currentPage, stage, half)];
    return (p && hifzProgressPhaseText(p.count)) || T('hifz_stage' + stage);
  }

  /* ── Счётчик повторов у кнопки Хусари (11.09.2026) ──────────────────
     Тап = один повтор. Число то же, что копила панель «сколько сделал
     сегодня»: 0-80 на место, первые сорок — глядя, вторые — по памяти.
     Поэтому цифры и переживают выход из режима: они лежат на сервере,
     а не в этом браузере.

     На сервер шлём не каждый тап, а накопленное: сорок тапов подряд — это
     сорок запросов на слабом интернете, и половина из них разошлась бы с
     тем, что человек видит. Копим и отправляем через полторы секунды после
     последнего тапа, а также при выходе с экрана. */
  var hifzCountPending = 0, hifzCountTimer = null, hifzCountKey = null;

  function hifzCountUnit() {
    // На этапе 1 «половина» — это номер строки: иначе счёт всех строк одной
    // половины слился бы в одно число (см. handle_hifz_progress_add).
    if (hifz.stage === 1) return { stage: 1, half: hifz.line };
    return { stage: hifz.stage, half: hifzProgressHalf() };
  }

  function hifzCountFlush() {
    if (!hifzCountPending || !hifzCountKey) return;
    var parts = hifzCountKey.split(':');
    var delta = hifzCountPending;
    hifzCountPending = 0;
    apiCall('/hifz/progress', { method: 'POST', body: {
      page: parseInt(parts[0], 10), stage: parseInt(parts[1], 10),
      half: parseInt(parts[2], 10), delta: delta
    } }).then(function (res) {
      // Неуспех - это не только оборванная сеть: 400/401 тоже, и молча
      // терять набитые тапы нельзя, человек их уже сделал (поймано на
      // стенде 11.09.2026).
      if (!res || !res.data || typeof res.data.count !== 'number') {
        hifzCountPending += delta;
        return;
      }
      var p = hifzProgressCache[hifzCountKey];
      // Сервер знает лучше: он же видит сдачи с другого телефона.
      if (p) p.count = res.data.count;
      hifzCountRender();
    }).catch(function () {
      // Не дошло — вернём в копилку, следующий тап или выход попробуют снова.
      hifzCountPending += delta;
    });
  }

  function hifzCountRender() {
    var page = document.getElementById('hifz-count');
    var big = document.getElementById('big-count');
    if (!page || !big) return;
    var show = hifz.on && !hifz.picking
      && !(typeof review !== 'undefined' && review.on)
      && !(typeof look !== 'undefined' && look.on);
    page.classList.toggle('on', !!show);
    big.classList.toggle('on', !!show);
    if (!show) return;

    var u = hifzCountUnit();
    hifzCountKey = hifzProgressKey(currentPage, u.stage, u.half);
    hifzProgressEnsureLoaded(currentPage, u.stage, u.half);
    var p = hifzProgressCache[hifzCountKey] || { count: 0 };
    var count = p.count + hifzCountPending;
    var second = count >= 40, full = count >= HIFZ_PROGRESS_TARGET;
    var shown = full ? 40 : (second ? count - 40 : count);
    [page, big].forEach(function (el) {
      el.classList.toggle('second', second);
      el.classList.toggle('full', full);
      el.querySelector('.c-cap').textContent =
        T(second ? 'hifz_count_memory' : 'hifz_count_looking');
      el.querySelector('.c-n b').textContent = shown;
      var bar = el.querySelector('.c-bar i');
      if (bar) bar.style.width = Math.min(100, count / HIFZ_PROGRESS_TARGET * 100) + '%';
    });
  }

  function hifzCountTap(el) {
    var p = hifzProgressCache[hifzCountKey] || { count: 0 };
    if (p.count + hifzCountPending >= HIFZ_PROGRESS_TARGET) return;
    hifzCountPending += 1;
    hifzCountRender();
    el.classList.remove('hit');
    void el.offsetWidth;              // перезапуск анимации на частых тапах
    el.classList.add('hit');
    clearTimeout(hifzCountTimer);
    hifzCountTimer = setTimeout(hifzCountFlush, 1500);
    hifzBackToStart();
  }

  /* Тап по счётчику = «прочитал до конца», следующий повтор - с первой
     строки (24.09.2026, предложение пользователя: лёжа на этапах 2-3 видно
     2-3 строки, и наверх листали руками). Едем, только если первая строка
     ушла с экрана: тап, пока она видна, лист не трогает. */
  function hifzBackToStart() {
    var wrap = document.getElementById('page-wrap');
    var first = document.querySelector('#ayah-text .mushaf-line.hifz-lit');
    if (!first) return;
    if (document.getElementById('app').classList.contains('land')) {
      // Лёжа единица стоит с начала листа (hifzApply), её начало - верх.
      if (wrap.scrollTop > 0) wrap.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    var gap = first.getBoundingClientRect().top - wrap.getBoundingClientRect().top;
    if (gap < 0) wrap.scrollBy({ top: gap - 8, behavior: 'smooth' });
  }

  ['hifz-count', 'big-count'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('click', function () { hifzCountTap(el); });
  });
  // Ушёл со страницы, свернул, закрыл - досылаем накопленное.
  window.addEventListener('pagehide', hifzCountFlush);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') hifzCountFlush();
  });

  function hifzProgressRenderPanel(count) {
    var look = Math.min(40, count), mem = Math.max(0, count - 40);
    document.getElementById('hp-look-n').textContent = look;
    document.getElementById('hp-mem-n').textContent = mem;
    var rowLook = document.getElementById('hp-row-look');
    var rowMem = document.getElementById('hp-row-mem');
    rowLook.classList.toggle('done', look >= 40);
    // Пока сорок «глядя» не набраны, вторая строка приглушена: по методике
    // до неё ещё не дошли, и яркий ноль рядом читался бы как долг.
    rowMem.classList.toggle('idle', look < 40);
    rowMem.classList.toggle('done', mem >= 40);
    document.getElementById('hifz-progress-bar').style.width =
      Math.min(100, count / HIFZ_PROGRESS_TARGET * 100) + '%';
    document.getElementById('hifz-progress-count').textContent = count;
    document.getElementById('hifz-progress-minus').disabled = count <= 0;
    document.getElementById('hifz-progress-plus').disabled = count >= HIFZ_PROGRESS_TARGET;
    var btn = document.getElementById('hifz-progress-save');
    var closed = count >= HIFZ_PROGRESS_TARGET;
    // Кнопка называет ровно то, что произойдёт. Раньше «Сохранить и
    // продолжить» обещала переход и при 40, хотя панель просто закрывалась.
    btn.textContent = closed
      ? T('hifz_progress_close', { P: hifzNextPlaceText() })
      : T('hifz_progress_save');
    btn.classList.toggle('closing', closed);
  }

  /* Куда поведёт «Дальше»: то же место и теми же словами, что покажет шапка
     после шага. Чужая страница называется одним номером: сколько на ней
     строк, мы узнаем только когда загрузим её. */
  function hifzPlaceText(page, line, stage) {
    if (page !== currentPage) return T('page_n', { N: page });
    if (stage === 1) {
      return T('page_n', { N: page }) + ' · ' + hifzLineOf(line);
    }
    if (stage === 2) {
      var rr = hifzHalfRange(hifzHalf(line));
      return T('page_n', { N: page }) + ' · ' + T('hifz_lines_range', { A: rr[0] + 1, B: rr[1] + 1 });
    }
    return T('page_n', { N: page }) + ' · ' + T('hifz_whole');
  }
  function hifzNextPlaceText() {
    var n = hifzNextPosition();
    return n ? hifzPlaceText(n.page, n.line, n.stage) : '';
  }

  // Открывается вместо мгновенного hifzNext() после успешной сдачи на
  // этапах 2/3 - запись прячем (панель занимает её место), число тянем
  // из кэша сразу, а следом перепроверяем с сервера (могли сдать с
  // другого устройства с тех пор).
  function hifzProgressOpen() {
    var page = currentPage, stage = hifz.stage, half = hifzProgressHalf();
    document.getElementById('hifz-rec-actions').style.display = 'none';
    // Таймер и плеер своё отработали: запись ушла устазу, переслушивать её
    // здесь незачем, а место они занимают и уводят взгляд с подтверждения
    // (аудит 20.09). Обратно их вернёт hifzRecReset при следующей записи.
    document.getElementById('hifz-rec-timer').style.display = 'none';
    hifzRecPlayerShow(false);
    document.getElementById('hifz-progress').style.display = 'block';
    document.getElementById('hifz-rec').classList.add('prog');
    var key = hifzProgressKey(page, stage, half);
    var cached = hifzProgressCache[key];
    hifzProgressRenderPanel(cached ? cached.count : 0);
    apiCall('/hifz/progress?page=' + page + '&stage=' + stage + '&half=' + half).then(function (res) {
      if (res.status === 401 || !res.data) return;
      hifzProgressCache[key] = { count: res.data.count || 0, target: res.data.target || HIFZ_PROGRESS_TARGET };
      hifzProgressRenderPanel(hifzProgressCache[key].count);
    }).catch(function () {});
  }

  /* Чипы «+10/+20/+40» и тапы по счётчику шлют ДЕЛЬТУ и сохраняются сразу
     же на сервере, а не копятся локально до отдельного «сохранить»: так тап
     не потеряется, если студент уйдёт со страницы раньше. Поле «вписать
     число» шлёт ТОЧНОЕ число (20.09.2026): оно читается как итог, а
     складывалось - человек, натапавший 20 и вписавший «20», получал 40
     (случай пользователя 19.09). Точное число ещё и единственный способ
     исправить промах: уменьшить дельтой нельзя. */
  function hifzProgressSubmit(body) {
    var page = currentPage, stage = hifz.stage, half = hifzProgressHalf();
    body.page = page; body.stage = stage; body.half = half;
    return apiCall('/hifz/progress', {
      method: 'POST', body: body
    }).then(function (res) {
      if (!(res.data && typeof res.data.count === 'number')) return;
      hifzProgressCache[hifzProgressKey(page, stage, half)] =
        { count: res.data.count, target: res.data.target || HIFZ_PROGRESS_TARGET };
      hifzProgressRenderPanel(res.data.count);
    }).catch(function () {});
  }
  function hifzProgressSubmitCount(count) { return hifzProgressSubmit({ count: count }); }

  /* Шаг ровно один повтор - как тап по счётчику у 🔊. Чипов «+10/+20/+40»
     больше нет: они появились, когда счётчика не было, и с ним стали вторым
     способом ввести то же число (аудит 20.09). Крупное число вписывается. */
  function hifzProgressStep(delta) {
    var key = hifzProgressKey(currentPage, hifz.stage, hifzProgressHalf());
    var p = hifzProgressCache[key] || { count: 0 };
    var next = Math.max(0, Math.min(HIFZ_PROGRESS_TARGET, p.count + delta));
    if (next === p.count) return;
    hifzProgressRenderPanel(next);          // рисуем сразу, ответ придёт следом
    hifzProgressSubmitCount(next);
  }
  document.getElementById('hifz-progress-minus').addEventListener('click', function () { hifzProgressStep(-1); });
  document.getElementById('hifz-progress-plus').addEventListener('click', function () { hifzProgressStep(1); });

  document.getElementById('hifz-progress-chips').addEventListener('click', function (e) {
    if (e.target.id === 'hifz-progress-own') {
      document.getElementById('hifz-progress-chips').style.display = 'none';
      document.getElementById('hifz-progress-own-row').style.display = 'flex';
      var inp = document.getElementById('hifz-progress-own-input');
      // Показываем накопленное прямо в поле: человек правит ИТОГ, а не
      // вводит добавку в пустоту - сразу видно, от чего он пляшет.
      var cur = hifzProgressCache[hifzProgressKey(currentPage, hifz.stage, hifzProgressHalf())];
      inp.value = cur ? cur.count : 0;
      inp.focus();
      inp.select();
    }
  });
  // Возвращает промис отправки (или null, если вводить было нечего) - нижняя
  // кнопка панели ждёт его, прежде чем закрыться.
  function hifzProgressCommitOwn() {
    var input = document.getElementById('hifz-progress-own-input');
    var n = parseInt(input.value, 10);
    document.getElementById('hifz-progress-chips').style.display = 'flex';
    document.getElementById('hifz-progress-own-row').style.display = 'none';
    input.value = '';
    if (isFinite(n) && n >= 0) {
      return hifzProgressSubmitCount(Math.max(0, Math.min(n, HIFZ_PROGRESS_TARGET)));
    }
    return null;
  }
  document.getElementById('hifz-progress-own-input').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') hifzProgressCommitOwn();
  });

  /* Кнопка внизу панели: сохраняет недосохранённое и закрывает, а после 80
     ещё и двигает указатель (частичная сдача его никогда не трогает).

     Число, набранное в поле «своё», раньше пропадало молча: кнопка «ок»
     рядом с полем маленькая, а внизу стоит большая «Сохранить и продолжить»
     - и она только закрывала панель, в поле не заглядывая. Поймано
     08.09.2026 на живых логах: два вечера подряд студент вводил повторы по
     этапу 3, POST /hifz/progress не ушёл НИ РАЗУ, счётчик так и остался
     0/80. Теперь кнопка сперва досохраняет введённое и лишь потом
     закрывает - иначе она обманывает своим же названием. */
  document.getElementById('hifz-progress-save').addEventListener('click', function () {
    var typing = document.getElementById('hifz-progress-own-row').style.display !== 'none';
    var pending = typing ? hifzProgressCommitOwn() : null;
    function finish() {
      var p = hifzProgressCache[hifzProgressKey(currentPage, hifz.stage, hifzProgressHalf())];
      var closed = p && p.count >= HIFZ_PROGRESS_TARGET;
      hifzRecClose();
      if (closed) {
        hifzNext();
        if (document.getElementById('hifz-big').classList.contains('visible')) hifzBigRender();
      }
    }
    // Ждём ответ сервера: только по нему видно, дошло ли до 80 - а от этого
    // зависит, сдвинется указатель или нет.
    if (pending) pending.then(finish); else finish();
  });

  /* «Сдать» прямо с «Крупно»: именно там студент делает свои 40 повторов,
     и закончив, не должен искать кнопку на другом экране. Крупный экран
     НЕ закрываем — окно записи и так рисуется поверх него, и после
     отправки студент остаётся там же, где повторял, уже на следующей
     строчке (02.09.2026). */
  document.getElementById('hifz-big-submit').addEventListener('click', function () {
    document.getElementById('hifz-submit').click();
  });

  // Указатель с сервера: он двигается ОБОИМИ каналами сдачи, поэтому живёт
  // не в localStorage. Если студент ещё не заходил в режим — null, тогда
  // при первом входе спросим строчку.
  /* apiCall отдаёт {status, data} — раньше здесь читали d.pointer напрямую,
     и указатель не восстанавливался НИ РАЗУ: каждый вход в режим заново
     спрашивал строчку (поймал пользователь 02.09.2026).

     Строка имеет смысл только вместе со СТРАНИЦЕЙ: «строка 7» на стр. 5 и
     на стр. 200 — разные места. Поэтому храним и страницу указателя, а
     подставляем сохранённую строку, только если студент на этой же
     странице; на любой другой — честно спрашиваем, где он (и подсказываем
     в подзаголовке, где осталось его место). */
  /* ─── Долг пересдачи (13.09.2026) ──────────────────────────────────────
     Решение пользователя. Долг больше НЕ запирает всё подряд: этап, в котором
     студент стоит, он доделывает и сдаёт («внутри первого этапа 7 или 8
     строк сдаёшь, даже если долги не закрыты»). Закрыт вход в СЛЕДУЮЩИЙ этап.

     Главное - блок ДО действия, а не после. Раньше стена стояла на отправке,
     и человек узнавал о ней, уже начитав 40+40 (случай пользователя 12.09).
     Теперь до записи дело не доходит: при закрытом ходе вход в заучивание
     ведёт в «Работу с устазом», к блоку «ПЕРЕСДАТЬ».

     Держит стену сервер (handle_hifz_set): локальное состояние можно
     перезагрузить, поэтому здесь только то, что видно на экране. */
  var hifzDebt = { retakes: [], done: false };

  function hifzSetDebt(data) {
    hifzDebt = {
      retakes: (data && data.retakes) || [],
      done: !!(data && data.done)
    };
  }

  function hifzDebtRefresh() {
    return apiCall('/hifz').then(function (res) {
      if (res.data) hifzSetDebt(res.data);
    }).catch(function () {});
  }

  // Ход закрыт: долги есть и на своём месте работать уже нечего (единицу
  // указателя студент закрыл, а шаг вперёд не состоялся). Считает сервер -
  // ему видно и сдачи, и счётчик 40+40.
  function hifzWall() {
    return !!(hifzDebt.retakes.length && hifzDebt.done);
  }

  // Плашки «пересдать» в шапке заучивания больше нет (17.09.2026, решение
  // пользователя: не загромождать мусхаф). О долге на дашборде, на
  // двери «Работа с устазом» говорят красная цифра и текст; при закрытом
  // ходе вход в заучивание по-прежнему ведёт туда сам (hifzWall).

  var hifzPointerPage = null;
  // setTimeout(...,0) оставлен как есть (безвредно) - причина ("var
  // API_BASE присваивается ниже по файлу") закрыта отдельно: apiBase()
  // теперь функция (см. её комментарий ниже), порядок строк файла
  // больше ни на что не влияет. Живой случай, который это вскрыл
  // (03.09.2026) - "GET /undefined/hifz" в логе 9 раз за утро, указатель
  // НИ РАЗУ не долетал до сервера, хотя там он был.
  var hifzPointerLoaded = new Promise(function (resolve) {
    setTimeout(function () {
      apiCall('/hifz').then(function (res) {
        if (res.status === 401 || !res.data) return;
        hifzSetDebt(res.data);
        if (!res.data.pointer) return;
        if (res.data.pointer.layout) applyLayout(res.data.pointer.layout);
        hifz.line = res.data.pointer.line;
        hifz.stage = res.data.pointer.stage;
        hifzPointerPage = res.data.pointer.page;
      }).catch(function (err) { console.error('hifz pointer', err); }).then(resolve);
    }, 0);
  });
  // Потолок на случай плохой связи (02.09.2026) - тап по 📖 не должен
  // зависнуть навсегда, если ответ так и не пришёл; после 2.5 сек режим
  // открывается с тем, что успело подгрузиться (в худшем случае - как
  // раньше, спросит строку).
  function hifzPointerReady() {
    return Promise.race([
      hifzPointerLoaded,
      new Promise(function (resolve) { setTimeout(resolve, 2500); })
    ]);
  }

  document.getElementById('btn-prev').addEventListener('click', function () {
    loadPage(currentPage + 1);
  });
  document.getElementById('btn-next').addEventListener('click', function () {
    loadPage(currentPage - 1);
  });

  // Начало суры Аль-Бакара - стр. 2 (проверено 17.08.2026, см. модульный
  // docstring core/quran_pages.py: "стр. 2 начинает Аль-Бакара с аята 1").
  var BAQARA_START_PAGE = 2;
  document.getElementById('btn-go-baqara').addEventListener('click', function () {
    loadPage(BAQARA_START_PAGE);
  });

