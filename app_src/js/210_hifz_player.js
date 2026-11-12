  /* ─── Плеер своей записи (13.09.2026) ──────────────────────────────────
     Тот же, что слушает разбор устаза (#look-play и соседи - стили общие).
     До этого тут стоял системный <audio controls>: серая полоса, которая на
     каждом телефоне своя и ни на что в приложении не похожа. Тег остался
     мотором, наружу торчит наш круг с дорожкой. */
  var recAudio = document.getElementById('hifz-rec-audio');

  function hifzRecPlayerShow(on) {
    document.getElementById('hifz-rec-player').style.display = on ? 'flex' : 'none';
    document.getElementById('hifz-rec-play').innerHTML = ICON.play;
    document.getElementById('hifz-rec-fill').style.width = '0';
    document.getElementById('hifz-rec-cur').textContent = '0:00';
    document.getElementById('hifz-rec-total').textContent =
      on && rec.ms ? lookFmt(rec.ms / 1000) : '0:00';
  }

  /* Слушать себя на iPhone (24.10.2026, Александра из группы Муслима: «не
     могу прослушать, очень тихо», а после отправки - громко). Пока микрофон
     открыт (держим его всю панель, см. hifzRecStream), iOS ведёт звук в
     разговорный динамик, тот, что у уха. На ▶ отпускаем микрофон - звук идёт
     в обычный; дослушал или поставил паузу - сразу берём обратно в фоне,
     чтобы «Перезаписать» стартовало без задержки. Запись и так начинается
     только когда микрофон реально выдан (красный таймер, hifzRecStart). */
  var REC_IOS = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

  function hifzRecPanelOpen() {
    return document.getElementById('hifz-rec').classList.contains('visible');
  }

  document.getElementById('hifz-rec-play').addEventListener('click', function () {
    if (recAudio.paused) {
      if (REC_IOS && rec.stream) {
        hifzRecRelease();
        rec.micBack = true;
        trail('rec', { n: 'mic off for play' });
      }
      recAudio.play().catch(function () {});
    }
    else { recAudio.pause(); }
  });
  recAudio.addEventListener('play', function () {
    document.getElementById('hifz-rec-play').innerHTML = ICON.pause;
  });
  ['pause', 'ended'].forEach(function (ev) {
    recAudio.addEventListener(ev, function () {
      document.getElementById('hifz-rec-play').innerHTML = ICON.play;
      if (!rec.micBack || !hifzRecPanelOpen()) return;
      rec.micBack = false;
      hifzRecStream().then(function () {
        if (!hifzRecPanelOpen()) hifzRecRelease();   // закрыли, пока ждали
      }).catch(function () {});
    });
  });
  recAudio.addEventListener('timeupdate', function () {
    /* Длительность только что записанного blob браузер часто отдаёт как
       Infinity (webm без длины в заголовке) - тогда считаем по своему
       замеру rec.ms, он у нас точнее и всё равно уже есть. */
    var d = isFinite(recAudio.duration) && recAudio.duration > 0
      ? recAudio.duration : (rec.ms ? rec.ms / 1000 : 0);
    document.getElementById('hifz-rec-cur').textContent = lookFmt(recAudio.currentTime);
    if (d > 0) {
      document.getElementById('hifz-rec-total').textContent = lookFmt(d);
      document.getElementById('hifz-rec-fill').style.width =
        Math.min(100, recAudio.currentTime / d * 100) + '%';
    }
  });
  document.getElementById('hifz-rec-track').addEventListener('click', function (e) {
    var d = isFinite(recAudio.duration) && recAudio.duration > 0
      ? recAudio.duration : (rec.ms ? rec.ms / 1000 : 0);
    if (d <= 0) return;
    var box = e.currentTarget.getBoundingClientRect();
    recAudio.currentTime = Math.min(d, Math.max(0, (e.clientX - box.left) / box.width * d));
  });

  function hifzRecReset() {
    if (rec.tick) { clearInterval(rec.tick); rec.tick = null; }
    hifzWakeOff();
    // Микрофон здесь НЕ отпускаем: hifzRecReset зовётся и при "перезаписать",
    // а повторный захват - это повторный вопрос студенту.
    if (rec.url) { URL.revokeObjectURL(rec.url); rec.url = null; }
    // Идущий диктофон останавливаем и бросаем: его onstop увидит, что он уже
    // не текущий, и ничего не тронет (см. hifzRecStart).
    var old = rec.mr;
    rec.mr = null; rec.chunks = []; rec.blob = null;
    rec.gen = (rec.gen || 0) + 1; rec.starting = false;
    if (old && old.state !== 'inactive') { try { old.stop(); } catch (e) { /* уже стоит */ } }
    rec.accMs = 0; rec.segBaseMs = 0; rec.paused = false; rec.resent = false;
    rec.seg = 0; rec.saved = []; rec.micLost = false;
    rec.pageFrom = null; rec.pageMax = null; rec.pageLayout = null;
    var a = document.getElementById('hifz-rec-audio');
    a.pause(); a.removeAttribute('src');
    hifzRecPlayerShow(false);
    // Таймер прячем до старта (13.09.2026): «0:00» на экране ничего не
    // значит и просит взгляд впустую. Время появляется вместе с записью,
    // и тогда же становится крупным и красным.
    document.getElementById('hifz-rec-timer').classList.remove('rec');
    document.getElementById('hifz-rec-timer').textContent = '0:00';
    document.getElementById('hifz-rec-timer').style.display = 'none';
    // Захват прогресса (см. hifzProgressOpen) прячет запись на время
    // выбора чипов - при новом открытии панели или закрытии обе стороны
    // возвращаем в исходное состояние.
    document.getElementById('hifz-rec-actions').style.display = '';
    document.getElementById('hifz-progress').style.display = 'none';
    document.getElementById('hifz-rec').classList.remove('prog');
    document.getElementById('hifz-progress-chips').style.display = 'flex';
    document.getElementById('hifz-progress-own-row').style.display = 'none';
  }

  function hifzRecClose() {
    rec.micBack = false;   // закрываем - микрофон после прослушивания не возвращать
    hifzRecReset();
    rec.mode = null;
    hifzRecRelease();   // панель закрыта - микрофон отпущен, индикатор гаснет
    document.getElementById('hifz-rec').classList.remove('visible', 'rev');
    // Свёрнутый разбор живёт только внутри этой панели: закрылась - и слушать
    // его здесь больше негде, кнопка не должна остаться висеть.
    lookStopAudio();
    document.getElementById('rec-review').classList.remove('on');
    hifzRecPad();
  }

  /* Шторка перекрывает низ страницы, поэтому отдаём мусхафу ровно столько
     места снизу, сколько она занимает - тогда последние строки можно
     доскроллить и прочитать (06.09.2026). Высоту берём измерением, а не
     константой: карточка меняет рост по состоянию (в "готово" в ней
     появляется плеер), и любое зашитое число разъехалось бы. */
  function hifzRecPad() {
    var wrap = document.getElementById('page-wrap');
    if (!wrap) return;
    var panel = document.getElementById('hifz-rec');
    var card = panel.querySelector('.card');
    var open = panel.classList.contains('visible');
    wrap.style.paddingBottom = open ? (card.offsetHeight + 12) + 'px' : '';
  }

  function hifzRecButtons(state) {
    var box = document.getElementById('hifz-rec-actions');
    box.innerHTML = '';
    // Пауза - для длинных сдач: минуту читать без единой заминки трудно, а
    // раньше выбор был "терпи или начинай заново" (06.09.2026, просьба
    // пользователя). MediaRecorder умеет pause/resume не везде - там, где
    // не умеет, кнопки просто нет, вместо неработающей.
    var canPause = rec.mr && typeof rec.mr.pause === 'function';
    var recRow = [];
    if (canPause) {
      recRow.push(['hifz-rec-pause', rec.paused ? 'hifz_rec_resume' : 'hifz_rec_pause', '']);
    }
    recRow.push(['hifz-rec-stop', 'hifz_rec_stop', 'stop']);
    var defs = {
      // В режиме повторения кнопка называет ОБЪЁМ работы (16.09.2026, вопрос
      // пользователя «ребёнок понимает, что надо записать всё?»): у сдачи
      // 40+40 объём виден из места в шапке, у повторения - нет.
      idle:   [['hifz-rec-go', rec.mode === 'revision' ? 'revision_rec_start' : 'hifz_rec_start', 'primary']],
      rec:    recRow,
      done:   [['hifz-rec-again', 'hifz_rec_again', ''],
               ['hifz-rec-send', 'hifz_rec_send', 'primary']],
      // Чтение оборвалось и ждёт человека (20.09.2026): послушать конец,
      // продолжить (главное действие) и начать заново - последним.
      broken: [['hifz-rec-tail', 'rec_listen_tail', ''],
               ['hifz-rec-continue', 'rec_continue', 'primary'],
               ['hifz-rec-fresh', 'rec_fresh', '']],
      sending: []
    };
    (defs[state] || []).forEach(function (d) {
      var b = document.createElement('button');
      b.id = d[0];
      b.textContent = T(d[1]);
      if (d[2]) b.className = d[2];
      box.appendChild(b);
    });
    /* Защита от тапа, летящего в только что появившуюся кнопку (13.09.2026).
       Ряд подменяется мгновенно, и второй тап по «Стоп» попадал уже в
       «Отправить». Цвет кнопки развели выше, но место осталось тем же, а
       палец быстрее глаза. Полсекунды тишины - и промах уходит в пустоту. */
    if (state === 'done') rec.guardUntil = Date.now() + 600;
    hifzRecPad();   // высота карточки поменялась вместе с кнопками
  }

  // Длительность СЧИТАЕТСЯ БЕЗ пауз: на таймере должно стоять столько,
  // сколько реально записано, иначе он врёт и студенту, и лимиту записи.
  function hifzRecElapsed() {
    return rec.accMs + (rec.paused ? 0 : Date.now() - rec.t0);
  }

  function hifzRecTimer() {
    var el = document.getElementById('hifz-rec-timer');
    var s = Math.floor(hifzRecElapsed() / 1000);
    el.textContent = Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);
  }

  /* Микрофон заглох посреди записи (30.09.2026). Живой случай - Азиля из
     группы Мохидил, iPhone: 28.09 после 20-минутной паузы и после перезапуска
     вкладки звук больше не шёл, а таймер шёл дальше. Узнавала она об этом
     только по «Стоп» - после 10-20 минут чтения в пустоту, три раза за день.
     Теперь следим сами: с телефона куски идут каждые REC_SLICE_MS, и если
     их нет дольше REC_SILENT_MS (или дорожка мертва на снятии паузы) -
     останавливаем, начитанное остаётся на телефоне, человек сразу видит
     «Продолжить чтение», и продолжение возьмёт микрофон заново. */
  var REC_SILENT_MS = 20000;

  function recMicAlive() {
    return !!(rec.stream && rec.stream.getAudioTracks().some(function (t) {
      return t.readyState === 'live' && !t.muted;
    }));
  }

  function hifzRecMicLost(why) {
    if (!rec.mr || rec.mr.state === 'inactive' || rec.micLost) return;
    rec.micLost = true;
    trail('rec', { n: 'mic lost ' + why + ' ' + Math.round(hifzRecElapsed() / 1000) + 's' });
    if (rec.tick) { clearInterval(rec.tick); rec.tick = null; }
    try { rec.mr.stop(); } catch (e) { rec.micLost = false; }
  }

  function recAfterMicLost() {
    rec.micLost = false;
    rec.mr = null; rec.paused = false;
    hifzRecRelease();            // «Продолжить» возьмёт микрофон заново
    document.getElementById('hifz-rec-timer').classList.remove('rec');
    (rec.saving || Promise.resolve()).then(recOfferResume).then(function (had) {
      if (had) {
        document.getElementById('hifz-rec-hint').textContent =
          T('rec_mic_lost', { T: hifzRecMmss(rec.accMs) });
        hifzRecPad();
        return;
      }
      // Первый этап (куски не хранятся) или совсем мало - просто заново.
      rec.accMs = 0; rec.seg = 0; rec.saved = [];
      document.getElementById('hifz-rec-timer').style.display = 'none';
      document.getElementById('hifz-rec-hint').textContent = T('rec_mic_lost_again');
      hifzRecButtons('idle');
    });
  }

  function hifzRecPause() {
    if (!rec.mr || typeof rec.mr.pause !== 'function') return;
    if (rec.paused) {
      // После долгой паузы айфон мог забрать микрофон - «продолжать» мёртвую
      // запись нельзя, берём микрофон заново новым куском (30.09.2026).
      if (!recMicAlive()) { hifzRecMicLost('resume'); return; }
      rec.t0 = Date.now();
      rec.heardAt = Date.now();
      rec.paused = false;
      rec.mr.resume();
      trail('rec', { n: 'resume' });
      document.getElementById('hifz-rec-timer').style.display = '';
      document.getElementById('hifz-rec-timer').classList.add('rec');
      document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_hint_rec');
    } else {
      rec.accMs = hifzRecElapsed();
      rec.paused = true;
      rec.mr.pause();
      trail('rec', { n: 'pause ' + Math.round(rec.accMs / 1000) + 's' });
      // Красный на таймере означает "идёт запись" - на паузе он гаснет,
      // иначе непонятно, пишется сейчас или нет.
      document.getElementById('hifz-rec-timer').classList.remove('rec');
      document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_hint_paused');
    }
    hifzRecButtons('rec');   // перерисовать надпись на кнопке
  }

  /* Разрешение на микрофон спрашивается ОДИН раз за открытие панели
     записи (04.09.2026, жалоба студента: "каждый раз спрашивает").
     Причина была в том, что после каждой записи мы глушили дорожку
     (track.stop()), и следующий getUserMedia заводил захват заново - а
     WebView Telegram на это заново переспрашивает. Теперь поток живёт,
     пока панель открыта: "перезаписать" больше не вызывает вопроса.
     Закрыли панель - отпускаем микрофон совсем (держать его открытым в
     фоне нельзя: телефон покажет, что приложение слушает, и это будет
     выглядеть ровно так, как не должно выглядеть приложение о Коране).

     Между ЗАПУСКАМИ приложения вопрос всё равно будет: разрешение
     принадлежит WebView Telegram, у Mini Apps нет API, чтобы его
     запомнить. На Android Telegram спрашивает системное разрешение
     один раз на себя, дальше вопрос внутри WebView; на iOS WKWebView
     переспрашивает при каждом новом запуске приложения. */
  function hifzMicPlain() {
    try { localStorage.setItem('hifz_mic_plain', '1'); } catch (e) {}
    if (rec.stream) rec.stream.getTracks().forEach(function (t) { t.stop(); });
    rec.stream = null;
    trail('rec', { n: 'mic plain' });
  }

  function hifzRecStream() {
    // Заглохший микрофон (muted) формально жив, но звука не даёт: на iPhone
    // из такого выходил файл в 0 байт (23.09.2026) - берём микрофон заново.
    if (rec.stream && rec.stream.getTracks().some(function (t) { return t.readyState === 'live' && !t.muted; })) {
      return Promise.resolve(rec.stream);
    }
    // Микрофон «как у диктофона», без обработки браузера (11.10.2026, Залкар
    // G-10: «часть слышно, часть совсем тихо», а в WhatsApp ровно). При
    // audio: true Chrome включает шумоподавление, и через 9-12 с оно
    // принимает ровное распевное чтение за шум: замер его сдач по секундам -
    // первые ~10 с около -25 дБ, дальше провал на 20-25 дБ до конца записи.
    // Эхоподавление не нужно: Хусари глушится в начале записи
    // при открытии шторки записи (hifzRecOpen). Где отключить нельзя (iOS),
    // браузер просто проигнорирует и запишет как раньше.
    // Откат на обычный микрофон (11.10.2026, Бехзод, Android 10): на части
    // телефонов запись без обработки доходит пустой (сервер слышит 0,1 с из
    // 130). Две такие подряд - телефон запоминает и пишет как раньше.
    // Samsung Internet - сразу как раньше: Азиз на той же версии (30) сдавал
    // до правки, Бехзод после неё - ни разу, телефон сам мерил файл в 0 с.
    var plain = /SamsungBrowser/.test(navigator.userAgent);
    try { plain = plain || localStorage.getItem('hifz_mic_plain') === '1'; } catch (e) {}
    // Одна выдача за раз (24.10.2026): прогрев после прослушивания (см.
    // recAudio ниже) и «Перезаписать» могут попросить микрофон одновременно -
    // второй поток никто бы не закрыл, и телефон показывал бы, что мы слушаем.
    if (rec.streamWait) return rec.streamWait;
    rec.streamWait = navigator.mediaDevices.getUserMedia({ audio: plain ? true : {
      noiseSuppression: false, echoCancellation: false, autoGainControl: false
    } }).then(function (stream) {
      rec.streamWait = null;
      rec.stream = stream;
      return stream;
    }, function (e) { rec.streamWait = null; throw e; });
    return rec.streamWait;
  }

  function hifzRecStart() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_no_mic');
      return;
    }
    // Запись с нуля (не продолжение обрыва - у того seg > 0) начинается с
    // чистого хранилища: что бы там ни осталось, к этой записи оно не
    // относится. Ждём очистки, иначе она сотрёт и первый новый кусок.
    // Один диктофон за раз (23.09.2026). Микрофон выдаётся не сразу, и второе
    // нажатие «Записать» за это время заводило второй MediaRecorder; первый
    // никто не останавливал, и он дописывал свои куски во все следующие
    // записи до перезапуска приложения - сдача уходила склейкой двух потоков
    // или битым файлом (bad_audio), вес вдвое больше обычного.
    if (rec.starting || (rec.mr && rec.mr.state !== 'inactive')) return;
    rec.starting = true;
    // Запись повторения с нуля: откуда читают - та страница, что на экране
    // сейчас (24.09.2026). Продолжение обрыва (seg > 0) начало уже знает.
    if (rec.mode === 'revision' && !rec.seg) {
      rec.pageFrom = currentPage; rec.pageMax = currentPage; rec.pageLayout = MUSHAF_LAYOUT;
    }
    var gen = rec.gen;   // панель сбросили, пока ждали микрофон - не стартуем
    var clean = (!rec.seg && recPlace()) ? recPartsWipe() : Promise.resolve();
    hifzRecStream().then(function (stream) {
      return clean.then(function () { return stream; });
    }).then(function (stream) {
      rec.starting = false;
      if (rec.gen !== gen) return;
      // Куски - у каждого диктофона свои: чужой в эту запись не допишет.
      var chunks = rec.chunks = [];
      var mr;
      // Формат не навязываем: Chrome/Android даёт webm/opus, Safari/iOS —
      // mp4/aac. Оба приводит к ogg сервер (ffmpeg), Telegram принимает
      // в голосовые только ogg/opus.
      // 64 кбит/с (12.10.2026, Лилия, Android 10): на 32 кбит/с opus Chrome
      // делил биты на всю полосу до 24 кГц, и чтение звучало «компьютерно» -
      // все её сдачи из приложения с 16.09, а голосовые Telegram 03-04.09 с
      // того же телефона чистые. Минута ~480 КБ, до предела загрузки далеко.
      // AAC/mp4 (12.10.2026, проба на одном телефоне): оригинал, который
      // играют все телефоны. Формат задаём явно - isTypeSupported сам по
      // себе ничего не меняет; не умеет телефон - пишем как раньше.
      var recOpts = { audioBitsPerSecond: 64000 };
      try {
        if (meRecAac && MediaRecorder.isTypeSupported('audio/mp4;codecs=mp4a.40.2')) recOpts.mimeType = 'audio/mp4;codecs=mp4a.40.2';
      } catch (e) {}
      try {
        mr = new MediaRecorder(stream, recOpts);
      } catch (e) {
        mr = new MediaRecorder(stream);
      }
      rec.mr = mr;
      mr.ondataavailable = function (e) {
        if (rec.mr !== mr || !e.data || !e.data.size) return;
        // Формат пишем по первому куску (13.10.2026): до start() Chrome
        // отдаёт пустой mimeType, и в след шло «fmt ?» у всех.
        if (!chunks.length) trail('rec', { n: 'fmt ' + (mr.mimeType || e.data.type || '?') });
        rec.heardAt = Date.now();
        chunks.push(e.data);
        // Держим последнее сохранение: «Стоп» приходит сразу за куском, и
        // отправлять надо уже после того, как он лёг на телефон.
        rec.saving = recPartSave(rec.seg, e.data, hifzRecElapsed());
      };
      mr.onstop = function () {
        if (rec.mr !== mr) return;   // брошенный диктофон (см. hifzRecReset)
        hifzWakeOff();
        if (rec.micLost) { recAfterMicLost(); return; }
        // Звука нет совсем (23.09.2026, только iPhone: 17-22 с на таймере и
        // файл в 0 байт, одна сестра нажала «Отправить» 13 раз). Отправлять
        // нечего - просим записать ещё раз, микрофон при этом берём заново.
        if (!chunks.length) {
          trail('rec', { n: 'empty ' + Math.round(hifzRecElapsed() / 1000) + 's' });
          if (rec.tick) { clearInterval(rec.tick); rec.tick = null; }
          rec.mr = null;
          rec.accMs = rec.segBaseMs || 0;
          hifzRecRelease();
          document.getElementById('hifz-rec-timer').classList.remove('rec');
          document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_empty');
          hifzRecButtons('idle');
          return;
        }
        // Перечитываем то, что лежит на телефоне: там и прежние сегменты, и
        // только что дописанный - из них и собирается отправка.
        (rec.saving || Promise.resolve()).then(recPartsLoad).then(function (rows) {
          rec.saved = rows;
        });
        rec.blob = new Blob(chunks, { type: chunks[0].type || 'audio/webm' });
        // Дорожку здесь НЕ глушим (см. hifzRecStream): иначе "перезаписать"
        // снова вызовет вопрос про микрофон. Микрофон отпускается при
        // закрытии панели.
        // Длину берём ДО того, как погасим тик: она нужна порогу в hifzRecSend.
        rec.ms = hifzRecElapsed();
        if (rec.tick) { clearInterval(rec.tick); rec.tick = null; }
        rec.url = URL.createObjectURL(rec.blob);
        var a = document.getElementById('hifz-rec-audio');
        a.src = rec.url;
        hifzRecPlayerShow(true);
        document.getElementById('hifz-rec-timer').classList.remove('rec');
        // Если запись остановил предел, а не студент - сказать прямо. Иначе
        // он видит "всё хорошо, отправляй" и не догадывается, что его
        // оборвали на полуслове.
        document.getElementById('hifz-rec-hint').textContent =
          T(rec.hitLimit ? 'hifz_rec_hint_limit' : 'hifz_rec_hint_done');
        // Тишина вместо звука (12.11.2026, Дилярам, Android): микрофон «без
        // обработки» на её телефоне отдаёт нули - 23 с записи весили 1,7 КБ
        // (обычно ~8 КБ в секунду; тишина - заголовок ~1,2 КБ и десятки байт
        // в секунду, стенд: 7 с = 1,8 КБ). Она слушала, не слышала ничего и не
        // отправляла - сервер об этом так и не узнавал. Ловим по весу сразу
        // после «Стоп»: говорим прямо и запоминаем обычный микрофон, со
        // следующей записи телефон пишет через него. Порог с большим запасом;
        // где тишина весит много (AAC на iPhone) - поймает сервер («silent»).
        var segSec = recSegMs(rec.ms, rec.segBaseMs) / 1000;
        if (segSec >= 3 && rec.blob.size < 1500 + 400 * segSec) {
          trail('rec', { n: 'silent local ' + rec.blob.size + 'b ' + Math.round(segSec) + 's' });
          hifzMicPlain();
          document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_silent');
        }
        hifzRecButtons('done');
      };
      // Кусками, а не одним куском в памяти (20.09.2026): оборвалась вкладка -
      // начитанное уже лежит на телефоне. Так пишутся обе записи: сдача
      // второго и третьего этапа не короче повторения.
      mr.start(REC_SLICE_MS);
      rec.heardAt = Date.now();
      hifzWakeOn();             // читает долго - экран гасить нельзя
      rec.t0 = Date.now();
      // accMs мог прийти из прерванной записи - тогда таймер идёт дальше, а
      // не с нуля (см. revisionRecResume).
      rec.accMs = rec.accMs || 0;
      rec.segBaseMs = rec.accMs;   // с этого места пишет новый поток (см. recSegMs)
      rec.paused = false;
      rec.hitLimit = false;
      rec.tick = setInterval(function () {
        hifzRecTimer();
        // Звук перестал приходить - микрофон заглох (см. hifzRecMicLost).
        if (!rec.paused && Date.now() - rec.heardAt > REC_SILENT_MS) { hifzRecMicLost('silent'); return; }
        // Лимит - по реально записанному, без учёта пауз.
        var left = HIFZ_REC_MAX_MS - hifzRecElapsed();
        if (left <= 0) {
          rec.hitLimit = true;   // onstop скажет об этом прямо, а не "готово"
          hifzRecStop();
        } else if (left <= HIFZ_REC_WARN_MS && !rec.paused) {
          document.getElementById('hifz-rec-hint').textContent =
            T('hifz_rec_hint_left', { N: Math.ceil(left / 60000) });
        }
      }, 500);
      // Таймер спрятан со сброса панели (13.09.2026) - показать его надо
      // здесь, а не только после паузы (16.09.2026: три дня запись шла без
      // видимого времени, поймано на съёмке шагов повторения).
      document.getElementById('hifz-rec-timer').style.display = '';
      document.getElementById('hifz-rec-timer').classList.add('rec');
      document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_hint_rec');
      hifzRecButtons('rec');
    }).catch(function () {
      rec.starting = false;
      document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_no_mic');
    });
  }

  function hifzRecStop() {
    // И с паузы тоже (23.09.2026): раньше «Стоп» на паузе молчал, и запись
    // оставалась неоконченной - человек уходил, так и не отправив.
    if (rec.mr && rec.mr.state !== 'inactive') rec.mr.stop();
  }

  function hifzRecSend() {
    if (!rec.blob) return;
    // Почему телефон не пустил запись - в след (23.09.2026): раньше это
    // восстанавливали по цифрам, а студент видел одну и ту же фразу 60 раз.
    if (!rec.blob.size) {
      trail('rec', { n: 'block empty' });
      document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_empty');
      return;
    }
    if (rec.ms && rec.ms < HIFZ_REC_MIN_MS) {
      trail('rec', { n: 'block short' });
      document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_too_short');
      return;
    }
    // Запись на самом телефоне короче таймера (17.09.2026): отправлять нечего,
    // полной записи нет нигде. Длину файла знает плеер; у webm из Chrome её
    // бывает не видно (Infinity) - тогда проверит сервер.
    var played = document.getElementById('hifz-rec-audio').duration;
    trail('rec', { n: 'send ' + Math.round((rec.ms || 0) / 1000) + 's file ' +
                      (isFinite(played) ? Math.round(played) + 's' : '?') + ' ' + rec.blob.size + 'b' +
                      (rec.segBaseMs ? ' from ' + Math.round(rec.segBaseMs / 1000) + 's' : '') });
    if (recLostTail(played, recSegMs(rec.ms, rec.segBaseMs))) {
      trail('rec', { n: 'block lost' });
      document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_lost');
      return;
    }
    if (rec.mode !== 'revision' && rec.ms && rec.ms / 1000 < (HIFZ_MIN_SEC[hifz.stage] || 0)) {
      trail('rec', { n: 'block unit' });
      document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_short_unit');
      return;
    }
    if (rec.mode === 'revision') { revisionRecSend(); return; }
    hifzRecButtons('sending');
    document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_hint_sending');
    hifzLinesToPng(hifzSubmitLines()).then(function (png) {
      var fd = new FormData();
      // Куски прерванного чтения (20.09.2026) - сервер сошьёт их в одну
      // запись; одиночная сдача уходит как раньше.
      // Один сегмент - это ровно запись в плеере, её и шлём: так на сервер
      // не попадёт ничего, кроме того, что студент сейчас слышал.
      var segs = rec.saved.length ? recSegments(rec.saved) : [];
      if (segs.length > 1) {
        segs.forEach(function (b, i) { fd.append(i ? 'audio' + i : 'audio', b, 'rec' + i); });
      } else {
        fd.append('audio', rec.blob, 'rec');
      }
      if (png) fd.append('image', png, 'lines.png');
      fd.append('page', String(currentPage));
      fd.append('line', String(hifz.line));
      fd.append('stage', String(hifz.stage));
      // Строк на листе не всегда 15 — сервер по этому же числу считает,
      // какая половина (та же формула, что hifzHalf выше).
      fd.append('lines', String(hifzTextLines().length));
      // Раскладка, в которой считаны страница и строка (23.09.2026). Та,
      // что на экране: пересдача долга из прежней раскладки идёт на его
      // листе (28.10.2026, Айкол - см. subsRetake).
      fd.append('layout', pageLayout());
      // Свой замер длины: Telegram для части файлов отдаёт 0 (16.09.2026).
      fd.append('ms', String(rec.ms || 0));
      return fetch(apiBase() + '/hifz/submit', {
        method: 'POST',
        headers: authHeaders(),
        body: fd
      });
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, data: d }; });
    }).then(function (res) {
      trail('submit', { p: currentPage, l: hifz.line, s: hifz.stage,
                        n: (res.ok && res.data.ok) ? 'ok' : String(res.data && res.data.error) });
      if (res.ok && res.data.ok) {
        document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_sent');
        if (typeof mushafDoneMarks === 'function') mushafDoneMarks('m');
        recPartsWipe();     // дошло до устаза - держать на телефоне незачем
        // Пересдача (см. subsRetake): та же единица уходит устазу заново, но
        // указатель "где я" не двигается и повторы не спрашиваются - студент
        // не проходит место второй раз, он его переcдаёт.
        if (hifzRetakeMode) {
          setTimeout(function () { hifzRecClose(); hifzRetakeFinish(); }, 1200);
          return;
        }
        if (hifz.stage === 1) {
          // Строка закрывается ОДНОЙ сдачей - указатель сам идёт дальше,
          // как и раньше. Стрелок для этого нет - методика без возврата.
          hifzNext();
          if (document.getElementById('hifz-big').classList.contains('visible')) hifzBigRender();
          setTimeout(hifzRecClose, 1200);
          return;
        }
        // Этапы 2/3 (половина/страница, 40+40) студенты обычно сдают по
        // частям за 2-3 дня (поймано пользователем 03.09.2026) - одна
        // запись больше НЕ закрывает единицу сама по себе. Вместо
        // немедленного hifzNext() спрашиваем, сколько повторов добавилось
        // сегодня; указатель сдвинется только когда счётчик дойдёт до 80.
        hifzProgressOpen();
        return;
      }
      // Гейт пересдачи (04.09.2026): сервер не принял сдачу другой единицы,
      // пока не принята пересдача. Называем место прямо - иначе отказ
      // читается как поломка.
      var err = res.data && res.data.error;
      // Дошла не целиком (17.09.2026): та же запись ещё лежит на телефоне -
      // один раз отправляем её сами, студенту ничего нажимать не нужно.
      if (err === 'incomplete' && !rec.resent) {
        rec.resent = true;
        hifzRecSend();
        return;
      }
      if (err === 'incomplete') hifzMicPlain();
      // В записи нет звука (12.11.2026, Дилярам): телефон в режиме «без обработки»
      // отдал тишину. Сервер такую сдачу не принимает; телефон запоминает обычный
      // микрофон, следующая запись пойдёт уже через него.
      if (err === 'silent') { hifzMicPlain(); trail('rec', { n: 'silent' }); }
      rec.resent = false;
      document.getElementById('hifz-rec-hint').textContent =
        err === 'retake_pending' ? T('hifz_retake_pending', { P: res.data.place || '' })
        : err === 'incomplete' ? T('hifz_rec_incomplete')
        : err === 'silent' ? T('hifz_rec_silent')
        : err === 'too_short' ? T('hifz_rec_short_unit')
        : err === 'wrong_bot' ? T('wrong_bot')
        : (err === 'no_group' ? T('hifz_rec_no_group') : T('hifz_rec_failed'));
      hifzRecButtons('done');
    }).catch(function () {
      trail('submit', { n: 'net' });
      document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_failed');
      hifzRecButtons('done');
    });
  }

  /* ─── Повторение записью (16.09.2026) ─────────────────────────────────
     Несовершеннолетним «повторение» засчитывается только записью чтения
     (задача пользователя: дети жали 🔁, не читая). Та же шторка записи, что у
     сдачи 40+40, но: открывается на обычной странице чтения, листать можно
     (pageTurnBlocked не держит - режим заучивания выключен), отправка идёт
     в /revision/submit. Охват (24.09.2026): страница, где нажали «Записать»,
     и самая дальняя за время записи - recTrackPage. */
  function revisionRecOpen() {
    hifzListenStop();
    hifzRecReset();
    rec.mode = 'revision';
    document.getElementById('hifz-rec').classList.add('rev');
    // Лист не трогаем (24.09.2026, решение пользователя): раньше панель сама
    // листала на начало Аль-Бакары, но дети, ушедшие далеко вперёд, повторяют
    // своё место. Кому нужна Бакара - «⤒ Бакара» в строке страниц. Откуда
    // читали, приложение запомнит само по нажатию «Записать».
    document.getElementById('hifz-rec-place').textContent = T('revision_rec_place');
    document.getElementById('hifz-rec-hint').textContent = T('revision_rec_hint');
    hifzRecButtons('idle');
    document.getElementById('hifz-rec').classList.add('visible');
    hifzRecPad();
    trail('rev_open', { p: currentPage });
    // Осталось начитанное с прошлого раза - предложим продолжить.
    recOfferResume().then(function (had) { if (had) hifzRecPad(); });
  }

  /* ─── Прерванное чтение (20.09.2026) ─────────────────────────────────
     Открыли запись повторения, а на телефоне лежит начитанное - значит в
     прошлый раз вкладку оборвали. Предлагаем послушать конец и продолжить;
     «начать заново» стоит последним, чтобы не смахнуть работу случайно. */
  function recOfferResume() {
    return recPartsLoad().then(function (rows) {
      if (!rows.length) return false;
      var ms = recSavedMs(rows);
      if (ms < 10000) { recPartsWipe(); return false; }   // пара секунд - не жалко
      rec.saved = rows;
      rec.accMs = ms;
      rec.seg = rows[rows.length - 1].seg + 1;            // продолжение - новый поток
      // Откуда читали в прошлый раз - из кусков; докуда - самое дальнее из них.
      rec.pageFrom = rows[0].pf || null;
      rec.pageLayout = rows[0].lay || null;
      rec.pageMax = rows.reduce(function (m, r) { return Math.max(m, r.pm || 0); }, rec.pageFrom || 0) || null;
      document.getElementById('hifz-rec-hint').textContent =
        T('rec_broken', { T: hifzRecMmss(ms) });
      document.getElementById('hifz-rec-timer').style.display = '';
      document.getElementById('hifz-rec-timer').textContent = hifzRecMmss(ms);
      hifzRecButtons('broken');
      trail('rev_broken', { n: Math.round(ms / 1000) + 's' });   // след хранит только n
      return true;
    }).catch(function () { return false; });
  }

  function hifzRecMmss(ms) {
    var s = Math.floor((ms || 0) / 1000);
    return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);
  }

  /* Последние пятнадцать секунд - чтобы вспомнить место в мусхафе. Играем
     ПОСЛЕДНИЙ сегмент: он и есть конец чтения. */
  function recPlayTail() {
    var segs = recSegments(rec.saved);
    if (!segs.length) return;
    var blob = segs[segs.length - 1];
    if (rec.url) URL.revokeObjectURL(rec.url);
    rec.url = URL.createObjectURL(blob);
    var a = document.getElementById('hifz-rec-audio');
    a.src = rec.url;
    hifzRecPlayerShow(true);
    a.addEventListener('loadedmetadata', function once() {
      a.removeEventListener('loadedmetadata', once);
      var d = a.duration;
      if (isFinite(d) && d > 15) a.currentTime = d - 15;
      a.play();
    });
    // У webm из Chrome длительность бывает неизвестна до конца файла -
    // тогда просто играем с начала последнего куска, он и так короткий.
    a.play().catch(function () { /* ждём loadedmetadata */ });
  }

  function recResume() {
    hifzRecPlayerShow(false);
    document.getElementById('hifz-rec-hint').textContent = T('rec_continue_hint');
    hifzRecStart();              // accMs и seg уже выставлены, таймер пойдёт дальше
  }

  function recFresh() {
    recPartsWipe();
    rec.saved = []; rec.accMs = 0; rec.seg = 0;
    hifzRecPlayerShow(false);
    document.getElementById('hifz-rec-timer').style.display = 'none';
    document.getElementById('hifz-rec-hint').textContent =
      T(rec.mode === 'revision' ? 'revision_rec_hint' : 'hifz_rec_hint_idle');
    hifzRecButtons('idle');
  }

  function revisionRecSend() {
    hifzRecButtons('sending');
    document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_hint_sending');
    var fd = new FormData();
    // Сегментов бывает несколько - чтение прерывалось и продолжалось. Сервер
    // сошьёт их в одно голосовое (20.09.2026).
    var segs = rec.saved.length ? recSegments(rec.saved) : [];
    if (segs.length > 1 && rec.blob) {
      // Последний сегмент уже лежит в хранилище целиком - берём оттуда,
      // чтобы не отправить его дважды.
      segs.forEach(function (b, i) { fd.append(i ? 'audio' + i : 'audio', b, 'rec' + i); });
    } else {
      fd.append('audio', rec.blob, 'rec');
    }
    fd.append('ms', String(rec.ms || 0));
    // Охват: откуда начал и докуда долистал, в нумерации своей книги -
    // сервер переведёт в мединскую (24.09.2026).
    fd.append('page_from', String(rec.pageFrom || currentPage));
    fd.append('page_to', String(Math.max(rec.pageMax || 0, rec.pageFrom || currentPage)));
    fd.append('layout', rec.pageLayout || MUSHAF_LAYOUT);
    fetch(apiBase() + '/revision/submit', { method: 'POST', headers: authHeaders(), body: fd })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (res) {
        trail('rev_submit', { n: ((res.ok && res.data.ok) ? 'ok' : String(res.data && res.data.error)) + ' ' + Math.round((rec.ms || 0) / 1000) + 's' });
        if (res.ok && res.data.ok) {
          document.getElementById('hifz-rec-hint').textContent = T('revision_rec_sent');
          recPartsWipe();       // дошло до устаза - на телефоне держать незачем
          setTimeout(hifzRecClose, 1500);
          return;
        }
        var err = res.data && res.data.error;
        if (err === 'incomplete' && !rec.resent) {
          rec.resent = true;
          revisionRecSend();
          return;
        }
        if (err === 'incomplete') hifzMicPlain();
        if (err === 'silent') { hifzMicPlain(); trail('rec', { n: 'silent' }); }
        rec.resent = false;
        document.getElementById('hifz-rec-hint').textContent =
          err === 'incomplete' ? T('hifz_rec_incomplete')
          : err === 'silent' ? T('hifz_rec_silent')
          : err === 'wrong_bot' ? T('wrong_bot')
          : err === 'no_group' ? T('hifz_rec_no_group') : T('hifz_rec_failed');
        hifzRecButtons('done');
      }).catch(function () {
        trail('rev_submit', { n: 'net' });
        document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_failed');
        hifzRecButtons('done');
      });
  }

  /* Шторка записи. Место берём параметром, а не из шапки: при пересдаче
     панель открывается сразу, ещё до того как лист догрузится и hifzHead
     впишет туда строку (07.09.2026). */
  function hifzRecOpen(place) {
    hifzListenStop();  // запись голоса и прослушка Хусари одновременно мешают друг другу
    hifzRecReset();
    rec.mode = null;
    document.getElementById('hifz-rec-place').textContent =
      place || document.getElementById('hifz-where').textContent;
    document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_hint_idle');
    hifzRecButtons('idle');
    document.getElementById('hifz-rec').classList.add('visible');
    hifzRecPad();
    // Оборвалось на этом же месте - предложим дочитать, а не начинать заново
    // (20.09.2026: на втором и третьем этапе запись идёт минутами).
    recOfferResume().then(function (had) { if (had) hifzRecPad(); });
  }

  document.getElementById('hifz-submit').addEventListener('click', function () {
    if (hifz.line === null || hifz.picking) return;
    hifzRecOpen();
  });

  // Один слушатель на всю панель: кнопки пересобираются под состояние.
  document.getElementById('hifz-rec-actions').addEventListener('click', function (e) {
    // см. hifzRecButtons: кнопки только что перерисовались, тап по ним сейчас
    // почти наверняка не их, а предыдущих.
    if (rec.guardUntil && Date.now() < rec.guardUntil) return;
    var id = e.target && e.target.id;
    if (id === 'hifz-rec-go') hifzRecStart();
    else if (id === 'hifz-rec-pause') hifzRecPause();
    else if (id === 'hifz-rec-stop') hifzRecStop();
    else if (id === 'hifz-rec-tail') recPlayTail();
    else if (id === 'hifz-rec-continue') recResume();
    else if (id === 'hifz-rec-fresh') recFresh();
    else if (id === 'hifz-rec-again') { hifzRecReset();
      // Прежняя попытка лежит на телефоне кусками - её надо стереть, иначе
      // она уйдёт вместе с новой (21.09.2026: у пользователя начало сдачи
      // прозвучало трижды - два «Перезаписать» и третья попытка).
      if (recPlace()) recPartsWipe();
      document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_hint_idle');
      hifzRecButtons('idle'); }
    else if (id === 'hifz-rec-send') { if (reviewCommentMode) reviewCommentSend(); else hifzRecSend(); }
  });
  document.getElementById('hifz-rec-close').addEventListener('click', hifzRecClose);

