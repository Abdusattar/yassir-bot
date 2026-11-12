  // "Сейчас онлайн" (30.08.2026) - heartbeat каждые 20 сек, пока YassirApp
  // открыт (независимо от того, какой экран сейчас - дашборд/мусхаф/
  // тренажёр), бейдж обновляется только на дашборде. setTimeout(..., 0)
  // вместо прямого вызова - функция apiCall объявлена НИЖЕ по файлу
  // (function-декларация хойстится целиком и вызвать её можно откуда
  // угодно, но здесь важнее сам сдвиг за пределы синхронного старта:
  // setInterval-колбэки и так асинхронны, а вот этот, самый первый,
  // синхронно выполнился бы слишком рано без отложенного старта).
  /* ── Новая версия приложения (11.09.2026) ────────────────────────────
     Приложение с домашнего экрана при запуске НЕ перезагружается: система
     возвращает ту же страницу вместе со старым кодом. Человек жмёт иконку и
     видит вчерашнюю версию, хотя в браузере всё свежее. Service worker тут
     не помогает — он берёт index.html из сети, но запроса просто нет.

     Поэтому спрашиваем сами: метку версии при старте запоминаем, а при
     каждом возвращении в приложение сверяем. Отличается — перезагружаемся.

     Перезагрузка не должна случиться посреди работы: если идёт запись сдачи
     или играет звук, откладываем до следующего возвращения. Потерять
     недописанную сдачу ради свежего кода — плохой обмен. */
  var appVersion = null;

  function appVersionBusy() {
    var rec = document.getElementById('hifz-rec');
    if (rec && rec.classList.contains('visible')) return true;   // идёт сдача
    var audios = document.getElementsByTagName('audio');
    for (var i = 0; i < audios.length; i++) {
      if (!audios[i].paused && !audios[i].ended) return true;    // играет звук
    }
    return false;
  }

  function appVersionCheck(first) {
    fetch(apiBase() + '/version', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.v) return;
        if (first || !appVersion) { appVersion = d.v; return; }
        if (d.v !== appVersion && !appVersionBusy()) location.reload();
      })
      .catch(function () { /* нет сети - просто в другой раз */ });
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') appVersionCheck(false);
  });
  window.addEventListener('pageshow', function (e) {
    // persisted - страница вернулась из «заморозки», ровно наш случай.
    if (e.persisted) appVersionCheck(false);
  });
  setTimeout(function () { appVersionCheck(true); }, 1500);

  // «След» (13.09.2026, идея пользователя): действия на экране копятся здесь
  // и уезжают пачкой вместе с heartbeat - отдельного запроса нет. Только то,
  // чего сервер иначе не видит (тапы, выбор единицы, ✕, попытки сохранить
  // место с ответом); сдачи и текущее место у него и так есть. Разбирать -
  // scripts/user_trail.py. Хранится 3 дня.
  var trailBuf = [];
  function trail(e, d) {
    d = d || {};
    trailBuf.push({ t: Date.now(), e: e, p: d.p, l: d.l, s: d.s, n: d.n });
    if (trailBuf.length > 200) trailBuf.splice(0, trailBuf.length - 200);
  }

  var HEARTBEAT_INTERVAL_MS = 20000;
  // Роль из heartbeat: по ней же показывается раздел онбординга
  // «Проверка сдач» (см. LEARN).
  var meIsUstaz = false;
  // Повторение только записью (16.09.2026, несовершеннолетние) - едет тем
  // же heartbeat, что и роль устаза.
  var meRevisionRecord = false;
  var meRecAac = false;   // писать сдачу в AAC/mp4 (проба, config.REC_AAC_IDS)
  // Хафиз (26.09.2026): повторяет свою норму, а не от начала Аль-Бакары.
  var meHafiz = false;
  var ONLINE_BADGE_MIN = 3; // меньше - не показываем совсем (решение
  // пользователя 30.08.2026 - 1-2 "онлайн" выглядит бедно, не украшает)
  function phoneTz() {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; }
    catch (e) { return ''; }
  }

  function sendHeartbeat() {
    var opts = { method: 'POST' };
    var batch = null;
    if (trailBuf.length) { batch = trailBuf; trailBuf = []; opts.body = { trail: batch }; }
    // Пояс телефона (21.09.2026): учебный день кончается в три ночи, а у
    // студента за границей три ночи наступают не по Бишкеку. Telegram пояс
    // боту не сообщает - знает только сам телефон. Пишется на сервере лишь
    // при смене.
    var tz = phoneTz();
    if (tz) { opts.body = opts.body || {}; opts.body.tz = tz; }
    apiCall('/heartbeat', opts).then(function (res) {
      // Не дошло - вернём пачку в буфер, следующий heartbeat заберёт.
      if (batch && res.status === 0) trailBuf = batch.concat(trailBuf).slice(-200);
      if (res.status === 401) return;
      var el = document.getElementById('dash-online');
      if (res.data && typeof res.data.online === 'number' && res.data.online >= ONLINE_BADGE_MIN) {
        el.innerHTML = '<span class="dot"></span>' + T('online_now_n', { N: res.data.online });
      } else {
        el.innerHTML = '';
      }
      // 4-я дверь "Устаз" (03.09.2026, пункт 13 старого макета) - тем же
      // ответом, что и "онлайн": дешёвая точка узнать роль, без отдельного
      // запроса на каждое открытие дашборда.
      var door = document.getElementById('dash-ustaz');
      var count = document.getElementById('dash-ustaz-count');
      var isUstaz = !!(res.data && res.data.is_ustaz);
      meRevisionRecord = !!(res.data && res.data.revision_record);
      meHafiz = !!(res.data && res.data.hafiz);
      meRecAac = !!(res.data && res.data.rec_aac);
      // Раздел «Проверка сдач» рисуется по этому же признаку. Если человек
      // стоял в оглавлении, когда ответ пришёл, - перерисуем, иначе раздел
      // появился бы только со второго захода.
      if (meIsUstaz !== isUstaz) {
        meIsUstaz = isUstaz;
        if (document.getElementById('learn').style.display === 'flex' && learnAt === null) {
          learnRenderToc();
        }
      }
      if (isUstaz) {
        door.style.display = 'flex';
        var n = res.data.waiting_count || 0;
        setTimeout(function () { if (typeof dashUstazRow === 'function') dashUstazRow(); }, 0);
        if (n > 0) { count.textContent = n; count.style.display = 'flex'; }
        else { count.style.display = 'none'; }
      } else {
        door.style.display = 'none';
      }
      // Дверей три - тренажёр тянется на всю строку (см. #dash-doors.three).
      document.getElementById('dash-doors').classList.toggle('three', !isUstaz);
      // Факты на дверях (07.09.2026): раздел сам говорит, что у него внутри.
      if (res.data && res.data.facts) dashFacts(res.data.facts);
      // Строка ленты (11.09.2026) - тем же ответом, чтобы она оживала без
      // перезагрузки экрана. null значит «писать пока нечего» - тогда
      // строки просто нет, пустой карточки не показываем.
      if (res.data) nameFix = !!res.data.name_fix;
      if (res.data) feedBrief(res.data.feed);
    });
  }
  /* Подписи дверей: вместо вечного описания раздела - его сегодняшнее
     состояние. «Чтение с таджвидом и переводом» человек прочитал один раз в
     первый день; «стр. 15, половина листа» отвечает на вопрос, где он стоит,
     каждый раз. Пока факта нет (новичок ещё не заходил в заучивание), остаётся
     прежнее описание - пустая строка была бы хуже. */
  // Названия заданий - те же короткие слова, что в группе (core/content.py:
  // SHORT_TASKS). Незнакомый код показываем как есть: лучше буква, чем
  // пропавшая отметка.
  function dayTaskName(k) {
    return T('task_' + k) || k;
  }

  // Подсветка «сдано сегодня» на кнопках мусхафа (11.11.2026): 'm' -
  // заучивание, 'r' - повторение, по тем же фактам, что и полоска «Мой день».
  function mushafDoneMarks(force) {
    var day = dashFactsLast && dashFactsLast.day, m = false, r = false;
    ((day && day.tasks) || []).forEach(function (t) {
      if (t.k === 'm' && t.done) m = true;
      if (t.k === 'r' && t.done) r = true;
    });
    if (force === 'm') m = true;
    if (force === 'r') r = true;
    var h = document.getElementById('btn-hifz'), rv = document.getElementById('btn-revision');
    if (h) h.classList.toggle('done', m);
    if (rv) rv.classList.toggle('done', r);
  }

