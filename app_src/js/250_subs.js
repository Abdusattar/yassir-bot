  /* ─── Кабинет студента "Сдачи" (04.09.2026) ────────────────────────────
     Экран из макета 01.09: свои сдачи, ответ устаза, пересдача. Вердикта
     "принято / на пересдачу" в базе пока нет - есть только "устаз
     отреагировал", поэтому статуса ровно два. Вердикт - отдельный заход,
     он меняет контракт с устазами (пункт 11 макета: пока не принято,
     следующий этап закрыт). */
  var subsAudio = new Audio();
  var subsPlayingKey = null;

  function subsStopAudio() {
    try { subsAudio.pause(); } catch (e) {}
    if (subsAudio.src && subsAudio.src.indexOf('blob:') === 0) URL.revokeObjectURL(subsAudio.src);
    subsAudio.removeAttribute('src');
    subsPlayingKey = null;
  }

  // Звук тянем fetch'ем с заголовком авторизации и играем из blob, а НЕ
  // ставим ссылку прямо в <audio src>: заголовок initData туда не
  // приложить, а тащить его в query-строке - светить в логах и истории.
  function subsPlay(id, kind, btn) {
    var key = id + ':' + kind;
    if (subsPlayingKey === key) { subsStopAudio(); subsRenderButtons(); return; }
    subsStopAudio();
    var label = btn.textContent;
    btn.disabled = true;
    var path = '/submissions/audio?id=' + id + '&kind=' + kind;
    audioSource(path).then(function (url) {
      subsAudio.src = url;
      subsPlayingKey = key;
      btn.disabled = false;
      subsRenderButtons();
      return audioPlay(subsAudio, audioReload(subsAudio, path));
    }).catch(function () {
      btn.disabled = false;
      btn.textContent = T('subs_audio_failed');
      setTimeout(function () { btn.textContent = label; }, 2000);
    });
  }

  subsAudio.addEventListener('ended', function () { subsPlayingKey = null; subsRenderButtons(); });

  // Подписи кнопок воспроизведения зависят от того, что играет прямо сейчас -
  // перерисовываем только их, не весь список (иначе теряется прокрутка).
  function subsRenderButtons() {
    var body = document.getElementById('subs-body');
    Array.prototype.forEach.call(body.querySelectorAll('[data-play]'), function (b) {
      var key = b.getAttribute('data-play');
      var kind = key.split(':')[1];
      b.textContent = subsPlayingKey === key
        ? T('subs_playing')
        : T('subs_my_record');
    });
  }

  function subsPlace(item) {
    if (item.hifz_page == null) return T('ustaz_no_place');
    if (item.hifz_stage === 2) return T('ustaz_place_half', { P: item.hifz_page });
    if (item.hifz_stage === 3) return T('ustaz_place_page', { P: item.hifz_page });
    return T('ustaz_place', { P: item.hifz_page, L: (item.hifz_line || 0) + 1 });
  }

  function subsRow(item, today) {
    var done = !!item.reviewed_at;
    // Вердикт устаза важнее факта "отреагировал": принято - это закрытая
    // дорога, пересдача - работа, которая держит студента на месте.
    // Пересдача, на которую студент уже ответил новой записью, красной не
    // ходит: работа сделана, дальше ход устаза (08.09.2026).
    var pill = item.verdict === 'accepted'
      ? ['done', T('subs_verdict_ok')]
      : (item.verdict === 'retake'
        ? (item.redone
          ? ['wait', T('subs_verdict_redone')]
          // из прежней группы - без красного: это уже не долг
          : [item.left_group ? 'wait' : 'retake', T('subs_verdict_retake')])
        : [done ? 'done' : 'wait', T(done ? 'subs_done' : 'subs_wait')]);
    var marks = [];
    try { marks = JSON.parse(item.error_words || '[]'); } catch (e) { marks = []; }
    var html = '<div class="sub-row">' +
      '<div class="top"><span class="place">' + subsPlace(item) + '</span>' +
      '<span class="sub-pill ' + pill[0] + '">' + pill[1] + '</span></div>' +
      (marks.length ? '<div class="meta">' + T('subs_marked_words', { N: marks.length }) + '</div>' : '') +
      '<div class="meta">' + ustazWhen(item, today) +
      (item.series_count > 1
        ? '–' + ustazTimeOnly(item.sent_last) + ' · ' +
          T('subs_series_n', {
            N: item.series_count + ' ' +
               TP(item.series_count, 'n_rec')
          })
        : '') +
      (item.group_title ? ' · ' + ustazEsc(item.group_title) : '') + '</div>';
    if (item.review_type === 'text' && item.review_text) {
      html += '<div class="sub-review">' +
        (item.review_by_name ? '<b>' + ustazEsc(item.review_by_name) + ':</b> ' : '') +
        ustazEsc(item.review_text) + '</div>';
    } else if (item.review_type === 'voice' && item.has_review_audio) {
      html += '<div class="sub-review">' +
        (item.review_by_name
          ? T('subs_review_from', { N: ustazEsc(item.review_by_name) })
          : T('subs_review_voice')) + '</div>';
    }
    var hasReview = marks.length || item.has_review_audio;
    var fromApp = item.hifz_page != null;
    /* Сдача голосовым прямо в группу: в приложении она только отмечается, слушать
       нечего — ни свою запись, ни ответ устаза (07.09.2026, решение
       пользователя). Две причины. Первая: и запись, и реплай лежат в самой
       группе Telegram, там их и слушают — приложение не должно быть вторым
       плеером к тому же аудио. Вторая, важнее: бот записывает в сдачи ЛЮБОЕ
       голосовое студента в группе, поэтому «моя запись» здесь запросто
       окажется не сдачей, а просто сказанным вслух словом. Место сдачи
       известно только у сдач из приложения — их и разбираем на листе. */
    var acts = '';
    if (fromApp && item.has_audio) {
      acts += '<button data-play="' + item.id + ':own">' + T('subs_my_record') + '</button>';
    }
    /* «Перезаписать» - только пока сдачу не посмотрели (07.09.2026, решение
       пользователя: у проверенной перезаписывать незачем). И только там, где
       разбирать нечего: если разбор есть, дорога одна - через него, ниже. */
    if (fromApp && !item.reviewed_at && item.verdict !== 'accepted' && !hasReview) {
      acts += '<button data-retake="' + item.id + '">' + T('subs_redo') + '</button>';
    }
    // У групповой сдачи кнопок не остаётся вовсе - пустую полосу не рисуем.
    if (acts) html += '<div class="sub-actions">' + acts + '</div>';
    /* Одна дверь в разбор (07.09.2026). Раньше их было две и вели они в
       разные места: «Пересдать» включала запись, а посмотреть пометки при
       вердикте «принято» можно было только сделав вид, что идёшь
       пересдавать. Теперь дверь одна, а запись - шаг внутри неё. */
    /* Дверь одна - в разбор устаза: там его пометки на листе, его голос, и
       оттуда же пересдача (запись - шаг внутри разбора, а не мимо него).
       Менялось только слово: «Разобрать» не говорило, что за ним откроется
       (07.09.2026). При вердикте «на пересдачу» дверь выделена: это работа,
       которую от студента ждут. */
    if (fromApp && hasReview) {
      var retake = item.verdict === 'retake' && !item.redone && !item.left_group;
      html += '<div class="sub-actions" style="margin-top:6px">' +
        '<button style="flex:1" class="' + (retake ? 'primary' : 'sub-open') +
        '" data-look="' + item.id + '">' +
        T(retake ? 'subs_review_open' : 'subs_review_view') +
        '</button></div>';
    }
    return html + '</div>';
  }

  /* ЭКРАН РАЗБОРА (07.09.2026)

     Голос устаза и его пометки - две половины одного разбора, а лежали они
     на разных экранах: аудио играло в списке сдач, пометки рисовались на
     листе. Слушать замечание, глядя на свою строку, было нельзя.

     Здесь они сходятся: та же страница мусхафа, та же подсветка единицы,
     что видел устаз, его пометки поверх - и его голос в нижней полосе.
     Подсветку даёт hifzApply (свет на сданной единице, приглушение
     остального), поэтому режим заучивания включается, но КЛАСС look убирает
     его нижнюю полосу с «Крупно» и «Сдать»: разбор - это не заучивание.

     Указатель "где я" не двигается: смотреть разбор старой сдачи можно
     когда угодно, прогресс от этого не отматывается (та же осторожность,
     что в subsRetake). */
  var look = { on: false, item: null, saved: null, url: null, playing: false };
  var lookAudio = new Audio();

  /* Перемотка по дорожке тапом и перетаскиванием (10.11.2026): пальцем
     ведут ползунок, а не тыкают в точку. Pointer Events с захватом - палец
     может уйти с полосы, перемотка продолжается, пока не отпустят.
     fill - заливка, двигаем сразу, не дожидаясь timeupdate. */
  // Значки плеера (10.11.2026, решение пользователя: текстовые ▶ и ❚❚ «жирные»):
  // тонкий треугольник и две скруглённые полосы, цвет - currentColor.
  var ICON_PLAY = '<svg viewBox="0 0 24 24"><path d="M8.6 5.2v13.6c0 .9 1 1.4 1.7.9l10.3-6.8c.7-.4.7-1.4 0-1.8L10.3 4.3c-.7-.5-1.7 0-1.7.9z"/></svg>';
  var ICON_PAUSE = '<svg viewBox="0 0 24 24"><rect x="6" y="5" width="4" height="14" rx="1.6"/><rect x="14" y="5" width="4" height="14" rx="1.6"/></svg>';

  /* Волна громкости из пиков 0..1 (11.11.2026). Пики считает сервер при
     приёме записи (core/audio_compat.py), здесь только рисуем; пустой список -
     волны нет, остаётся полоса. */
  function waveRender(track, peaks) {
    var wave = track.querySelector('.wave');
    if (!wave) return;
    peaks = Array.isArray(peaks) ? peaks : [];
    track.classList.toggle('has-wave', peaks.length > 0);
    wave.innerHTML = peaks.map(function (v) {
      var h = Math.max(10, Math.min(100, Math.round((+v || 0) * 100)));
      return '<i style="height:' + h + '%"></i>';
    }).join('');
  }
  function waveProgress(track, ratio) {
    var wave = track.querySelector('.wave');
    if (!wave || !track.classList.contains('has-wave')) return;
    var bars = wave.children, n = Math.round(ratio * bars.length);
    for (var i = 0; i < bars.length; i++) bars[i].classList.toggle('on', i < n);
  }
  // Заливка полосы и волны разом - для timeupdate и перемотки.
  function trackProgress(track, fill, ratio) {
    if (fill) fill.style.width = (ratio * 100) + '%';
    waveProgress(track, ratio);
  }

  function audioSeekable(track, audio, fill) {
    var seeking = false;
    function seekTo(clientX) {
      var d = audio.duration;
      if (!isFinite(d) || d <= 0) return;
      var box = track.getBoundingClientRect();
      var ratio = Math.min(1, Math.max(0, (clientX - box.left) / box.width));
      audio.currentTime = ratio * d;
      trackProgress(track, fill, ratio);
    }
    track.addEventListener('pointerdown', function (e) {
      seeking = true;
      try { track.setPointerCapture(e.pointerId); } catch (err) {}
      seekTo(e.clientX);
      e.preventDefault();
    });
    track.addEventListener('pointermove', function (e) { if (seeking) seekTo(e.clientX); });
    function stop(e) {
      if (!seeking) return;
      seeking = false;
      try { track.releasePointerCapture(e.pointerId); } catch (err) {}
    }
    track.addEventListener('pointerup', stop);
    track.addEventListener('pointercancel', stop);
  }

  function lookFmt(sec) {
    if (!isFinite(sec) || sec < 0) sec = 0;
    var s = Math.floor(sec);
    return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);
  }

  function lookRenderActions() {
    var box = document.getElementById('look-actions');
    box.innerHTML = '';
    var defs = [['look-back10', 'look_back10', false]];
    // Пересдача - только там, где её просят. У принятой работы разбор
    // смотрят, чтобы знать на будущее, пересдавать нечего.
    if (look.item && look.item.verdict === 'retake') {
      defs.push(['look-retake', 'look_retake', true]);
    }
    defs.forEach(function (d) {
      var b = document.createElement('button');
      b.id = d[0];
      b.innerHTML = (d[1] === 'look_retake' ? ICON.mic + ' ' : d[1] === 'look_back10' ? ICON.rewind + ' ' : '') + T(d[1]);
      if (d[2]) b.className = 'primary';
      box.appendChild(b);
    });
    var back = document.getElementById('look-back10');
    if (back) back.addEventListener('click', function () {
      lookAudio.currentTime = Math.max(0, lookAudio.currentTime - 10);
    });
    var re = document.getElementById('look-retake');
    if (re) re.addEventListener('click', lookRetake);
  }

  function lookOpen(item) {
    subsStopAudio();
    try { pendingErrorMarks = JSON.parse(item.error_words || '[]'); }
    catch (e) { pendingErrorMarks = null; }
    /* Голос устаза держится в памяти на один разбор (lookLoadAudio), а
       закрытие экрана его не отпускало. Открыв вторую пересдачу, студент
       слышал замечание от ПЕРВОЙ: «уже загружено» - и старый blob играл
       под новыми пометками (14.09.2026, поймано пользователем на двух своих
       пересдачах). Отпускаем при смене сдачи; повторное открытие той же -
       из памяти, как и было. */
    if (!look.item || look.item.id !== item.id) lookFreeAudio();
    look.on = true;
    look.item = item;
    look.saved = { line: hifz.line, stage: hifz.stage, on: hifz.on, page: currentPage };
    hifz.on = true;
    hifz.picking = false;
    hifz.stage = item.hifz_stage || 1;
    hifz.line = item.hifz_line || 0;
    document.getElementById('subs').style.display = 'none';
    document.getElementById('app').classList.add('look');
    document.getElementById('look-who').textContent = item.review_by_name
      ? T('look_from', { N: item.review_by_name })
      : T('look_from_ustaz');
    document.getElementById('look-cur').textContent = '0:00';
    document.getElementById('look-total').textContent = '0:00';
    document.getElementById('look-fill').style.width = '0';
    document.getElementById('look-dur').textContent =
      item.has_review_audio ? '' : T('look_no_audio');
    document.getElementById('look-play').disabled = !item.has_review_audio;
    lookRenderActions();
    openMushaf('page');
    var relayout = useViewLayout(item.hifz_layout);
    if (relayout || currentPage !== item.hifz_page) {
      loadPage(item.hifz_page);   // renderPage сама позовёт hifzApply/hifzHead
    } else {
      hifzApply();
      if (pendingErrorMarks) { applyErrorMarks(pendingErrorMarks); pendingErrorMarks = null; }
    }
  }

  // Выход из разбора - обратно в «Сдачи», а не в чтение: студент пришёл
  // оттуда и туда же возвращается (та же дорога, что у проверки устаза).
  function lookClose() {
    lookStopAudio();
    look.on = false;
    look.item = null;
    document.getElementById('app').classList.remove('look');
    applyErrorMarks([]);
    if (look.saved) {
      hifz.line = look.saved.line;
      hifz.stage = look.saved.stage;
      hifz.on = look.saved.on;
      look.saved = null;
    }
    hifzApply();
    if (dropViewLayout()) loadPage(currentPage);
    document.getElementById('app').style.display = 'none';
    openSubs();
  }

  function lookStopAudio() {
    try { lookAudio.pause(); } catch (e) {}
    look.playing = false;
    var b = document.getElementById('look-play');
    if (b) b.innerHTML = ICON.play;
    var rb = document.getElementById('rec-review-play');
    if (rb) rb.innerHTML = ICON.play;
  }

  function lookFreeAudio() {
    lookStopAudio();
    if (look.url) { URL.revokeObjectURL(look.url); look.url = null; }
    lookAudio.removeAttribute('src');
  }

  /* Запись тянем один раз за разбор и держим blob: студент слушает её по
     кругу, а в пересдаче переслушивает из панели записи - второй заход в
     сеть там был бы не к месту. Заголовок initData нельзя поставить на
     <audio src>, поэтому fetch + blob, как и в списке сдач. */
  function lookLoadAudio() {
    if (look.url) return Promise.resolve();
    if (!look.item || !look.item.has_review_audio) return Promise.reject();
    return audioSource('/submissions/audio?id=' + look.item.id + '&kind=review').then(function (url) {
      look.url = url;
      lookAudio.src = look.url;
    });
  }

  function lookToggle(btn) {
    if (look.playing) { lookAudio.pause(); return; }
    btn.disabled = true;
    lookLoadAudio().then(function () {
      btn.disabled = false;
      return audioPlay(lookAudio, function () {
        if (look.url) { URL.revokeObjectURL(look.url); look.url = null; }
        return lookLoadAudio();
      });
    }).catch(function () {
      btn.disabled = false;
      document.getElementById('look-dur').textContent = T('look_failed');
    });
  }

  lookAudio.addEventListener('play', function () {
    look.playing = true;
    var b = document.getElementById('look-play');
    if (b) b.innerHTML = ICON.pause;
    var rb = document.getElementById('rec-review-play');
    if (rb) rb.innerHTML = ICON.pause;
  });
  lookAudio.addEventListener('pause', lookStopAudio);
  lookAudio.addEventListener('ended', lookStopAudio);
  lookAudio.addEventListener('timeupdate', function () {
    if (!look.on) return;
    var d = lookAudio.duration;
    document.getElementById('look-cur').textContent = lookFmt(lookAudio.currentTime);
    if (isFinite(d) && d > 0) {
      document.getElementById('look-total').textContent = lookFmt(d);
      document.getElementById('look-fill').style.width =
        (lookAudio.currentTime / d * 100) + '%';
    }
  });

  document.getElementById('look-play').addEventListener('click', function (e) {
    lookToggle(e.currentTarget);
  });
  // Перемотка тапом по полосе - разбор длиной в минуту переслушивают кусками.
  document.getElementById('rec-review-play').addEventListener('click', function (e) {
    lookToggle(e.currentTarget);
  });
  audioSeekable(document.getElementById('look-track'), lookAudio, document.getElementById('look-fill'));

  // Из разбора - прямо в запись, тем же местом. Пометки остаются на листе,
  // а сам разбор сворачивается в строку внутри панели записи.
  function lookRetake() {
    var item = look.item;
    lookStopAudio();
    look.on = false;
    document.getElementById('app').classList.remove('look');
    subsRetake(item, true);
    look.saved = null;      // место вернёт уже пересдача (hifzRetakeFinish)
  }

  // Пересдача: открываем заучивание РОВНО на том месте, что сдавали, и
  // помечаем сессию как пересдачу. Указатель "где я" при этом не двигается
  // ни локально, ни на сервере (см. hifzRetakeMode в hifzRecSend) - иначе
  // пересдача старой строчки отматывала бы прогресс назад.
  var hifzRetakeMode = false;
  var hifzRetakeSaved = null;

  /* fromLook - пересдача начата из разбора: лист уже открыт на нужной
     странице, пометки уже нарисованы, а разбор надо оставить под рукой
     свёрнутым (см. #rec-review). */
  function subsRetake(item, fromLook) {
    subsStopAudio();
    trail('retake', { p: item.hifz_page, l: item.hifz_line, s: item.hifz_stage });
    // Слова, отмеченные устазом, студент должен увидеть НА СТРАНИЦЕ - ради
    // этого пересдача и открывается прямо здесь, а не отдельным списком.
    if (!fromLook) {
      try { pendingErrorMarks = JSON.parse(item.error_words || '[]'); }
      catch (e) { pendingErrorMarks = null; }
    }
    // Лист запоминаем вместе с местом (13.09.2026): без него возврат чинил
    // только шапку, а currentPage оставался на странице долга - и следующая
    // сдача уходила с чужой страницей (она берёт currentPage, см. hifzRecSend).
    /* Из разбора - место берём из look.saved (13.09.2026, поймал
       пользователь): lookOpen уже поставил hifz.line/stage и лист на место
       долга, и здесь запоминалось бы оно само. После пересдачи первой строки
       студент, стоявший на третьей, оказывался снова на первой. */
    hifzRetakeSaved = (fromLook && look.saved) ? look.saved
      : { line: hifz.line, stage: hifz.stage, on: hifz.on, page: currentPage };
    hifzRetakeMode = true;
    hifz.on = true;
    hifz.picking = false;
    hifz.stage = item.hifz_stage || 1;
    hifz.line = item.hifz_line || 0;
    document.getElementById('subs').style.display = 'none';
    openMushaf('page');
    /* Долг читается на ЕГО листе (28.10.2026, Айкол): разобран в мадинской,
       а студентка перешла на Дар аль-Маариф - те же номера там другой текст,
       и пометки устаза легли бы на чужие слова. Семь её пересдач ушли
       египетскими номерами и долга не закрыли. Вид вернёт hifzRetakeFinish. */
    var relayout = useViewLayout(item.hifz_layout);
    if (relayout || currentPage !== item.hifz_page) {
      loadPage(item.hifz_page);   // renderPage сама вызовет hifzApply/hifzHead
    } else {
      hifzApply();
      hifzHead();
      /* Лист уже на месте - страница не перерисуется, и пометки устаза
         сами не лягут (14.09.2026, аудит после бага с кэшем замечания).
         Без этого «Пересдать» из блока долга на текущем листе открывал
         строку без единой пометки, а отложенные пометки всплывали на
         СЛЕДУЮЩЕМ отрисованном листе - чужом. */
      if (pendingErrorMarks) { applyErrorMarks(pendingErrorMarks); pendingErrorMarks = null; }
    }
    /* Свёрнутый разбор в панели записи - только когда есть что слушать.
       Пересдачу открывают двумя дорогами: из экрана разбора (там запись уже
       подгружена) и прямо из блока «нужно пересдать» - там её надо подцепить
       здесь, иначе студент остался бы наедине с пометками, без голоса устаза
       (07.09.2026). */
    if (!fromLook && look.item !== item) {
      lookFreeAudio();
      look.item = item;
    }
    var mini = document.getElementById('rec-review');
    mini.classList.toggle('on', !!item.has_review_audio);
    document.getElementById('rec-review-text').textContent = T('rec_review_text');
    /* «Пересдать» - это уже решение записать, а не заход в режим заучивания:
       лишний тап по «Сдать» внизу студент воспринимал как ещё один шаг
       («нажимаю на пересдать и открывается кнопка записать?», 07.09.2026).
       Шторка не модалка - лист с пометками устаза под ней виден и читается. */
    hifzRecOpen(subsPlace(item));
  }

  // Возврат к обычной сессии после пересдачи - место и этап, на которых
  // студент был до неё.
  function hifzRetakeFinish() {
    if (!hifzRetakeMode) return;
    hifzRetakeMode = false;
    // Пересдача отправлена - разбор отработан. Отпускаем и запись, и лист:
    // держать blob замечания в памяти дальше незачем.
    lookFreeAudio();
    look.item = null;
    applyErrorMarks([]);
    var relayout = dropViewLayout();   // лист долга был в его раскладке
    if (hifzRetakeSaved) {
      var back = hifzRetakeSaved;
      hifz.line = back.line;
      hifz.stage = back.stage;
      hifz.on = back.on;
      hifzRetakeSaved = null;
      // Долг закрыт самим фактом отправки - стена снимается сразу, ждать
      // приёма устаза не надо (см. get_open_retakes).
      hifzDebtRefresh();
      if (back.page && (relayout || back.page !== currentPage)) {
        loadPage(back.page);   // renderPage сама позовёт hifzApply/hifzHead
        return;
      }
    }
    if (relayout) { loadPage(currentPage); return; }
    hifzApply();
    hifzHead();
  }

  /* Мини-отчёт по дню (07.10.2026, решение пользователя): тап по неполному
     дню календаря показывает из базы, что сдано и во сколько, чего не
     хватило, узр, урок и короткий след действий в приложении. Полный день
     и пустой тапом не отвечают: там и так всё ясно. Одна функция рисует
     отчёт и студенту, и устазу в «Студентах» - картина одна у обоих. */
  function dayIsPause(d, key) {
    return (d.pauses || []).indexOf(key) >= 0;
  }

  function dayIsPartial(d, tasks, key) {
    if (d.miss && key && d.miss[key] != null) return tasks.length > 0 && d.miss[key] > 0;
    var total = d.tasks_total || 3;
    return tasks.length > 0 && tasks.length < total;
  }

  /* Цвет дня (11.11.2026, Розалина: 3 из 4 горело как полный день). Не по
     числу сданных, а по тому, сколько обязательных не хватило: всё - d3,
     не хватает одного - d2, больше - d1. Одинаково для 3, 4, 6 заданий и
     хафиза. miss приходит с сервера (core/db.py: day_missing); у старого
     ответа без него - прежнее правило. */
  function dayLevel(miss, key, n) {
    if (!n) return '';
    if (miss && miss[key] != null) return miss[key] <= 0 ? 'd3' : miss[key] === 1 ? 'd2' : 'd1';
    return 'd' + Math.min(3, n);
  }

  // Место сдачи из сырых полей - как _place в core/day_report.py.
  function dayPlace(page, line, stage) {
    var v = { P: page, L: (line || 0) + 1 };
    return T(stage === 3 ? 'day_place_sheet' : stage === 2 ? 'day_place_half' : 'day_place_line', v);
  }

  // Подробности задания и след на языке интерфейса. Сервер шлёт и готовую
  // русскую строку, и сырые поля (28.10.2026, zh); нет полей - строка как есть.
  function dayDetail(t) {
    if (t.subs) return t.subs.map(function (x) {
      var v = x.verdict === 'accepted' || x.verdict === 'retake' ? x.verdict : 'pending';
      return dayPlace(x.page, x.line, x.stage) + ' · ' + T('day_v_' + v);
    }).join('; ');
    if (t.rec_min) return t.rec_min.map(function (n) { return T('day_rec_min', { N: n }); }).join('; ');
    if (t.words) return T('day_words', { N: t.words[0], K: t.words[1] });
    return t.detail;
  }

  function dayTrailLine(e) {
    var bits = [e.at, T('dtr_' + e.ev) || e.ev];
    if (e.page != null) bits.push(dayPlace(e.page, e.line, e.stage));
    else if (e.note) bits.push(e.note);
    return bits.filter(Boolean).join(' · ');
  }

  function dayReportHTML(r) {
    var out = '<div class="stu-day-head">' + lessonDate(r.date) + '</div>';
    if (r.trail_ev) r.trail = r.trail_ev.map(dayTrailLine);
    // День паузы «Цикл» без сдач (03.11.2026): одно слово «пауза», без
    // красных «не сдано» - это не долг.
    var pauseOnly = r.pause && !(r.tasks || []).some(function (t) { return t.done; });
    (pauseOnly ? [] : (r.tasks || [])).forEach(function (t) {
      // Имя задания приходит по-русски (core/day_report.py); на другом
      // языке интерфейса - из словаря (28.10.2026, аудит zh).
      if (UI_LANG !== 'ru' && T('task_' + t.key)) t.name = T('task_' + t.key);
      t.detail = dayDetail(t);
      out += t.done
        ? '<div class="ok">✓ ' + t.name + (t.at ? ' ' + t.at : '') + (t.detail ? ' · ' + ustazEsc(t.detail) : '') + '</div>'
        : '<div class="no">' + ICON['circle-x'] + ' ' + t.name + ' — ' + T('day_not_done') + '</div>';
    });
    if (r.pause) out += '<div class="ok">' + T('day_pause') + '</div>';
    if (r.excuse != null) out += '<div class="ok">' + T('day_excuse') + (r.excuse ? ': ' + ustazEsc(r.excuse) : '') + '</div>';
    if (r.lesson) out += '<div class="ok">' + T('day_lesson') + '</div>';
    if (r.trail && r.trail.length) {
      out += '<div class="trail"><b>' + T('day_trail') + '</b><br>' + r.trail.map(ustazEsc).join('<br>') + '</div>';
    }
    return out;
  }

  // Рисует отчёт под календарём внутри host; повторный тап по тому же дню
  // сворачивает. path - свой день или день студента у устаза.
  function dayReportToggle(host, cell, path) {
    var box = host.querySelector('.stu-day');
    var date = cell.getAttribute('data-date');
    if (box && box.getAttribute('data-date') === date) { box.parentNode.removeChild(box); return; }
    if (!box) {
      box = document.createElement('div');
      box.className = 'stu-day';
      var cal = host.querySelector('.stu-cal');
      (cal && cal.nextSibling) ? cal.parentNode.insertBefore(box, cal.nextSibling) : host.appendChild(box);
    }
    box.setAttribute('data-date', date);
    box.innerHTML = '<div class="stu-day-head">' + lessonDate(date) + ' …</div>';
    apiCall(path + (path.indexOf('?') >= 0 ? '&' : '?') + 'date=' + date).then(function (res) {
      if (!res.data || res.status !== 200 || box.getAttribute('data-date') !== date) return;
      box.innerHTML = dayReportHTML(res.data);
    }).catch(function () { box.innerHTML = ''; });
  }

  /* Свой месяц в "Сдачах" (04.09.2026) - ТОТ ЖЕ календарь и тот же счёт
     пропусков, что видит устаз в зоне "Студенты". Условие макета: у обоих
     одна картина, иначе разговор "ты пропускал" снова становится спором.
     Порог назван прямо - он не должен жить только в голове у бота. */
  function subsCalendarHTML(d) {
    var info = stuMonthInfo(d.month, d.today);
    var first = new Date(info.year, info.month - 1, 1).getDay();
    var lead = (first + 6) % 7;
    var cells = '';
    for (var i = 0; i < lead; i++) cells += '<div class="c empty"></div>';
    for (var day = 1; day <= info.days; day++) {
      var tasks = (d.days || {})[stuDayKey(d.month, day)] || [];
      var cls = day > info.today ? 'future' : dayLevel(d.miss, stuDayKey(d.month, day), tasks.length);
      if ((d.lessons || []).indexOf(stuDayKey(d.month, day)) >= 0) cls += ' les';
      // Неполный день отвечает на тап мини-отчётом (07.10.2026) - помечаем
      // его, чтобы палец видел, куда нажимать.
      if (dayIsPartial(d, tasks, stuDayKey(d.month, day))) cls += ' part';
      else if (!tasks.length && dayIsPause(d, stuDayKey(d.month, day))) cls += ' pz';
      cells += '<div class="c ' + cls + '" data-date="' + stuDayKey(d.month, day) + '">' + day + '</div>';
    }
    var miss = d.threshold
      ? T('subs_month_misses', { N: d.missed, M: d.threshold })
      : T('subs_month_misses_no_limit', { N: d.missed });
    return '<div class="ustaz-group-title" style="margin-top:12px">' +
      T('subs_month_title') + (d.group_title ? ' · ' + ustazEsc(d.group_title) : '') +
      '</div><div class="stu-cal">' + cells + '</div>' +
      '<div class="stu-legend">' + miss + ' · ' + T('subs_month_legend') +
      ((d.lessons || []).length ? ' · ' + T('lesson_dot_legend') : '') +
      ((d.pauses || []).length ? ' · ' + T('pause_legend') : '') + '</div>';
  }

  /* Вариант В (06.09.2026, выбор пользователя): ДВЕ строки черточек.

     Верхняя - ритм по дням месяца, ровно тот же компонент, что видит устаз
     в "Студентах" (у обоих одна картина - условие макета). Читает массивы
     заданий из /month, а не счётчики: у устаза и студента разные источники
     (get_group_month_progress отдаёт число, get_student_month_days - список
     заданий за день), поэтому своя функция, а не переиспользование stuStrip.

     Нижняя - запас группы: черточек ровно столько, сколько пропусков даёт
     группа (10 pro / 20 relaxed), сгоревшие - слева. Это и есть тот
     "механизм", который просили показать: сколько пропустил из десяти.

     Обе от 1-го числа: пропуски и перевод в Тадаббур считаются от начала
     месяца (get_skip_count_month_detail, core/transfers.py). Скользящее
     окно "последние N дней" разошлось бы с числом в подписи - двойной счёт
     на этом экране запрещён. */
  function subsDaysStripHTML(d) {
    var info = stuMonthInfo(d.month, d.today);
    var out = '';
    for (var day = 1; day <= info.days; day++) {
      var n = ((d.days || {})[stuDayKey(d.month, day)] || []).length;
      var cls = day > info.today ? 'future' : dayLevel(d.miss, stuDayKey(d.month, day), n);
      if (!n && dayIsPause(d, stuDayKey(d.month, day))) cls = 'pz';
      out += '<i class="' + cls + '"></i>';
    }
    return '<div class="stu-strip">' + out + '</div>';
  }

  // Запас: сгоревшие слоты слева, свободные справа. Больше порога не рисуем -
  // у кого пропусков больше, чем даёт группа, полоска просто сгорела целиком,
  // а лишние черточки соврали бы про размер запаса.
  function subsBudgetStripHTML(used, total, cls) {
    var burned = Math.max(0, Math.min(used, total));
    var out = '';
    for (var i = 0; i < total; i++) out += '<i class="' + (i < burned ? cls : '') + '"></i>';
    return '<div class="stu-strip" style="margin-top:4px">' + out + '</div>';
  }

  function subsMonthSummaryHTML(d) {
    // Подготовительная (06.09.2026): там отчисляют не за пропуски, а за
    // недобор полных дней к сроку (core/prep.py). И запас там не сгорает, а
    // набирается - поэтому нижняя полоска заполняется акцентом, а не красным.
    var line, budget, note = '';
    if (d.prep) {
      line = T('subs_prep_days', { N: d.prep.days_done, M: d.prep.min_days }) +
        ' · ' + T('subs_prep_deadline', { D: subsShortDate(d.prep.deadline) });
      budget = subsBudgetStripHTML(d.prep.days_done, d.prep.min_days, 'd3');
      // Правило "полного дня" называем прямо (06.09.2026): иначе студент
      // видит "3 из 5" и думает, что засчитывается любое одно задание.
      var nt = d.prep.tasks_count || 3;
      note = '<div class="subs-note">' +
        T(ruPluralKey('subs_prep_full_day', nt), { N: nt }) + '</div>';
    } else if (d.threshold) {
      line = T('subs_month_misses', { N: d.missed, M: d.threshold }) +
        ' · ' + T('subs_month_left', { N: Math.max(0, d.threshold - d.missed) });
      budget = subsBudgetStripHTML(d.missed, d.threshold, 'burn');
    } else {
      line = T('subs_month_misses_no_limit', { N: d.missed });
      budget = '';
    }
    return subsDaysStripHTML(d) + budget +
      '<div class="stu-legend" style="margin-top:5px">' + line + '</div>' + note +
      '<div class="subs-month-tap">' + T('subs_month_open') + '</div>';
  }

  // "3 задания", но "5 заданий" - подставлять число в одну строку нельзя,
  // русский требует согласования. Ключи различаются суффиксом, а не текст
  // собирается в коде: перевод на ky/uz потом ляжет в те же ключи.
  function ruPluralKey(base, n) {
    var d10 = n % 10, d100 = n % 100;
    if (d10 === 1 && d100 !== 11) return base + '_one';
    if (d10 >= 2 && d10 <= 4 && (d100 < 12 || d100 > 14)) return base + '_few';
    return base + '_many';
  }

  function subsShortDate(iso) {
    return iso && iso.length >= 10 ? iso.slice(8, 10) + '.' + iso.slice(5, 7) : '';
  }

  /* Онлайн-урок (14.09.2026, решение пользователя): студент отмечает сам,
     без устаза. Правило на сервере - до двух отметок за неделю, сутки между
     ними (core/db.py credit_lesson_attendance), то же у «у» в Telegram. */
  function lessonFemale() { return apiBase().indexOf('/female') >= 0; }

  function subsRenderLesson(d) {
    var box = document.getElementById('subs-lesson');
    if (!box || !d.lesson) return;
    if (!d.lesson.can_mark) {
      box.innerHTML = (d.lesson.marked_today || d.lesson.week_count)
        ? '<div class="subs-quiet" style="margin:10px 0 12px">' +
          T(d.lesson.marked_today ? 'lesson_marked_today' : 'lesson_marked_recent') + '</div>'
        : '';
      return;
    }
    box.innerHTML = '<div class="lesson-row"><div class="t"><b>' + ICON.video + ' ' + T('lesson_title') +
      '</b><span>' + T('lesson_hint') + '</span></div><button id="subs-lesson-btn">' +
      T(lessonFemale() ? 'lesson_btn_f' : 'lesson_btn') + '</button></div>';
    document.getElementById('subs-lesson-btn').addEventListener('click', function () {
      showConfirm(T(lessonFemale() ? 'lesson_confirm_f' : 'lesson_confirm'), function () {
        apiCall('/lesson/mark', { method: 'POST' }).then(function (res) {
          var r = res && res.data;
          if (!r || !r.lesson) return;
          d.lesson = r.lesson;
          d.lessons = r.lessons || d.lessons;
          subsRenderLesson(d);
          // Точка в месяце - сразу, без перезагрузки экрана.
          var month = document.getElementById('subs-month');
          if (month) {
            var open = month.getAttribute('data-open') === '1';
            month.innerHTML = subsMonthSummaryHTML(d);
            if (open) month.insertAdjacentHTML('beforeend', subsCalendarHTML(d));
          }
        });
      });
    });
  }

  /* «Не могу сегодня» (03.11.2026, решение пользователя): узр кнопкой - всем,
     пауза «Цикл» - только сёстрам (cycle_allowed решает сервер). Карточка
     здесь, а не на главном экране: нажимают редко. Правила - core/absence.py. */
  function subsRenderAbsence(d) {
    var box = document.getElementById('subs-absence');
    var a = d && d.absence;
    if (!box || !a) return;
    if (a.pause) {
      box.innerHTML = '<div class="lesson-row"><div class="t"><b>' +
        T('abs_paused', { N: a.pause.day }) + '</b><span>' + T('abs_paused_hint') + '</span></div></div>';
      return;
    }
    var ex = a.excuse || {};
    var hint = ex.today ? T('abs_today')
      : ex.left > 0 ? T('abs_left', { N: ex.left, M: ex.limit }) : T('abs_none_left');
    var btns = '';
    if (!ex.today && ex.left > 0) btns += '<button id="abs-ex-btn">' + T('abs_btn_excuse') + '</button>';
    if (a.cycle_allowed) btns += '<button id="abs-cy-btn">' + T('abs_btn_cycle') + '</button>';
    box.innerHTML = '<div class="lesson-row"><div class="t"><b>' + T('abs_title') + '</b><span>' + hint +
      '</span></div>' + (btns ? '<div class="abs-btns">' + btns + '</div>' : '') + '</div>';
    var exBtn = document.getElementById('abs-ex-btn');
    if (exBtn) exBtn.addEventListener('click', function () { absOpenExcuse(d); });
    var cyBtn = document.getElementById('abs-cy-btn');
    if (cyBtn) cyBtn.addEventListener('click', function () { absOpenCycle(d); });
  }

  function absClose() {
    document.getElementById('abs-veil').classList.remove('on');
    document.getElementById('abs-sheet').classList.remove('on');
  }
  function absOpen(html) {
    var sheet = document.getElementById('abs-sheet');
    sheet.innerHTML = '<div class="grip"></div>' + html +
      '<button class="cancel" id="abs-cancel">' + T('abs_cancel') + '</button>';
    document.getElementById('abs-veil').classList.add('on');
    sheet.classList.add('on');
    document.getElementById('abs-cancel').addEventListener('click', absClose);
  }
  document.getElementById('abs-veil').addEventListener('click', absClose);

  // Ответ сервера - сразу в карточку и в месяц, без перезагрузки экрана.
  function absApply(d, r) {
    if (r.absence) d.absence = r.absence;
    if (r.pauses) d.pauses = r.pauses;
    subsRenderAbsence(d);
    var month = document.getElementById('subs-month');
    if (month) {
      var open = month.getAttribute('data-open') === '1';
      month.innerHTML = subsMonthSummaryHTML(d);
      if (open) month.insertAdjacentHTML('beforeend', subsCalendarHTML(d));
    }
  }

  function absSend(path, body, d) {
    var go = document.getElementById('abs-go');
    go.disabled = true;
    apiCall(path, { method: 'POST', body: body }).then(function (res) {
      go.disabled = false;
      absClose();
      absApply(d, (res && res.data) || {});
    }).catch(function () { go.disabled = false; });
  }

  function absOpenExcuse(d) {
    var ex = (d.absence && d.absence.excuse) || {};
    absOpen('<h3>' + T('abs_ex_title') + '</h3><div class="sub">' +
      T('abs_ex_sub', { N: ex.left, M: ex.limit }) + '</div>' +
      '<textarea id="abs-reason" maxlength="300" placeholder="' + ustazEsc(T('abs_ex_ph')) + '"></textarea>' +
      '<div class="note">' + T('abs_ex_note') + '</div>' +
      '<button class="go" id="abs-go">' + T('abs_ex_go') + '</button>');
    document.getElementById('abs-go').addEventListener('click', function () {
      absSend('/absence/excuse', { reason: document.getElementById('abs-reason').value || '' }, d);
    });
  }

  function absOpenCycle(d) {
    absOpen('<h3>' + T('abs_cy_title') + '</h3><div class="sub">' + T('abs_cy_sub') + '</div><ul>' +
      ['abs_cy_1', 'abs_cy_2', 'abs_cy_3', 'abs_cy_4'].map(function (k) {
        return '<li>' + T(k) + '</li>';
      }).join('') + '</ul><button class="go" id="abs-go">' + T('abs_cy_go') + '</button>');
    document.getElementById('abs-go').addEventListener('click', function () {
      absSend('/absence/cycle', {}, d);
    });
  }

  function subsLoadMonth() {
    var box = document.getElementById('subs-month');
    if (!box) return;
    apiCall('/month').then(function (res) {
      var d = res.data;
      // group_title есть только когда у студента вообще есть учебная группа
      // (см. handle_my_month) - без неё "days" приходит пустым {} и показывать
      // нечего, а не "пропусков undefined".
      if (!d || d.group_title == null) return;
      box.innerHTML = subsMonthSummaryHTML(d);
      subsRenderLesson(d);
      subsRenderAbsence(d);
      // Тап проваливает в месяц по дням - тот же жест и тот же календарь,
      // что у устаза в "Студентах". Полоски при этом никуда не деваются:
      // сворачивать их обратно незачем, они и так две строки.
      box.style.cursor = 'pointer';
      box.addEventListener('click', function (e) {
        if (box.getAttribute('data-open') === '1') {
          // Календарь открыт: тап по неполному дню - мини-отчёт (07.10.2026).
          var cell = e.target && e.target.closest ? e.target.closest('.stu-cal .c.part, .stu-cal .c.pz') : null;
          if (cell) dayReportToggle(box, cell, '/day');
          return;
        }
        box.setAttribute('data-open', '1');
        box.insertAdjacentHTML('beforeend', subsCalendarHTML(d));
      });
    }).catch(function () {});
  }

  // Окно + свёрнутый хвост (04.09.2026, жалоба: плоский список из 20 записей
  // плюс календарь довеском внизу читался "все дни скопом"). Тот же приём,
  // что уже принят у устаза в очереди - то же слово ("ещё N старше"), тот же
  // жест (тап разворачивает). Данные уже все на руках (SUBMISSIONS_LIMIT=20,
  // это не сотни строк устаза) - делим на клиенте, второй запрос не нужен.
  /* Неделя и всё (07.09.2026, решение пользователя): раньше показывались
     три дня плюс сворачиваемый хвост «ещё N старше». Хвост убран — студенту
     он не нужен: своя история за месяц и так видна календарём выше, а список
     существует ради вопроса «надо ли мне что-то сделать сейчас». */
  var SUBS_WINDOW_DAYS = 7;

  function subsDateAdd(iso, days) {
    var d = new Date(iso + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
  }

  function subsBindRows(container, items) {
    Array.prototype.forEach.call(container.querySelectorAll('[data-play]'), function (b) {
      b.addEventListener('click', function () {
        var parts = b.getAttribute('data-play').split(':');
        subsPlay(parts[0], parts[1], b);
      });
    });
    Array.prototype.forEach.call(container.querySelectorAll('[data-retake]'), function (b) {
      b.addEventListener('click', function () {
        var id = parseInt(b.getAttribute('data-retake'), 10);
        var item = items.filter(function (x) { return x.id === id; })[0];
        if (item) subsRetake(item);
      });
    });
    Array.prototype.forEach.call(container.querySelectorAll('[data-look]'), function (b) {
      b.addEventListener('click', function () {
        var id = parseInt(b.getAttribute('data-look'), 10);
        var item = items.filter(function (x) { return x.id === id; })[0];
        if (item) lookOpen(item);
      });
    });
  }

