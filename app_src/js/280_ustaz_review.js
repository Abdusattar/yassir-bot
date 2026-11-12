  /* ─── Проверка сдачи устазом (04.09.2026) ──────────────────────────────
     Экран ureview из макета 01.09. Устаз слушает сдачу, тапает по словам с
     ошибками и ставит вердикт. Страница мусхафа - ТА ЖЕ, что видит студент:
     подсветку единицы даёт та же машинерия заучивания (hifz.line/stage), а
     пометки слов рисуются одним и тем же классом .err у обоих. Это условие
     из макета: у устаза и студента должна быть буквально одна картинка.

     Слово адресуем как (номер строки на странице, позиция span в строке) -
     вёрстка построчная и детерминированная, адрес переживает перерисовку.

     Гейт "пока не принято - дальше хода нет" живёт на СЕРВЕРЕ (см.
     submit_hifz_recording): интерфейс можно перезагрузить, сдачу - нет. */
  var review = { on: false, sub: null, words: {}, saved: null };
  // Пометки, которые надо показать студенту, как только страница отрисуется
  // (см. reveal в renderPage).
  var pendingErrorMarks = null;
  var reviewAudio = new Audio();
  var reviewPlaying = false;

  function reviewKey(line, word) { return line + ':' + word; }

  function reviewMarkedList() {
    return Object.keys(review.words).filter(function (k) { return review.words[k]; })
      .map(function (k) {
        var p = k.split(':');
        return { line: parseInt(p[0], 10), word: parseInt(p[1], 10) };
      });
  }

  // Рисуем пометки на уже отрисованной странице. Одна функция и для устаза
  // (он их ставит), и для студента (он их смотрит) - расхождению взяться
  // неоткуда.
  function applyErrorMarks(marks) {
    var rows = document.querySelectorAll('#ayah-text .mushaf-line');
    Array.prototype.forEach.call(rows, function (row) {
      Array.prototype.forEach.call(row.children, function (sp) { sp.classList.remove('err'); });
    });
    (marks || []).forEach(function (m) {
      var row = document.querySelector('#ayah-text .mushaf-line[data-line="' + m.line + '"]');
      if (row && row.children[m.word]) row.children[m.word].classList.add('err');
    });
  }

  function reviewHint() {
    // Пересданную работу больше не переразбирают (07.09.2026, решение
    // пользователя): вердикт по ней заново закрыл бы гейт перед студентом,
    // который на замечание уже ответил, а новое замечание переписало бы то,
    // которое он послушал. Смотреть - можно, менять - нет; сервер это
    // правило держит сам (core/db.py:is_retake_answered).
    if (review.sub && review.sub.redone) {
      document.getElementById('review-hint').textContent = T('review_frozen');
      return;
    }
    var n = reviewMarkedList().length;
    document.getElementById('review-hint').textContent =
      n ? T('review_marked', { N: n }) : T('review_tap_words');
  }

  // Источник в плеере: 'own' - запись студента, 'review' - замечание устаза.
  // reviewPlaying - что загружено в <audio> (null - ещё ничего).
  var reviewSrc = 'own';

  function reviewStopAudio() {
    try { reviewAudio.pause(); } catch (e) {}
    if (reviewAudio.src && reviewAudio.src.indexOf('blob:') === 0) URL.revokeObjectURL(reviewAudio.src);
    reviewAudio.removeAttribute('src');
    reviewPlaying = null;
    reviewPlayerReset();
  }

  /* Плеер стоит в подвале всегда (11.11.2026): ▶, волна записи студента и
     её длина известны ещё до загрузки звука - из данных сдачи. Сброс - к
     записи студента, с начала. */
  function reviewPlayerReset() {
    var sub = review.sub || {};
    var track = document.getElementById('review-track');
    reviewSrc = 'own';
    waveRender(track, sub.peaks);
    trackProgress(track, document.getElementById('review-fill'), 0);
    document.getElementById('review-cur').textContent = '0:00';
    document.getElementById('review-total').textContent = reviewTotalLabel(sub.duration);
    document.getElementById('review-pp').innerHTML = ICON_PLAY;
    document.getElementById('review-pp').disabled = false;
    document.getElementById('review-src').textContent = T('review_src_own');
    var mine = document.getElementById('review-mine');
    mine.classList.remove('on');
    document.getElementById('review-mine-t').textContent = T('review_play_mine');
  }
  function reviewTotalLabel(sec) {
    var dur = ustazDur(sec);
    return dur ? dur.replace('⏱ ', '') : '0:00';
  }
  function reviewPlayerTime() {
    var d = reviewAudio.duration;
    document.getElementById('review-cur').textContent = lookFmt(reviewAudio.currentTime);
    if (isFinite(d) && d > 0) {
      document.getElementById('review-total').textContent = lookFmt(d);
      trackProgress(document.getElementById('review-track'), document.getElementById('review-fill'),
        reviewAudio.currentTime / d);
    }
  }
  reviewAudio.addEventListener('timeupdate', reviewPlayerTime);
  reviewAudio.addEventListener('loadedmetadata', reviewPlayerTime);
  reviewAudio.addEventListener('durationchange', reviewPlayerTime);
  reviewAudio.addEventListener('play', function () { document.getElementById('review-pp').innerHTML = ICON_PAUSE; });
  reviewAudio.addEventListener('pause', function () { document.getElementById('review-pp').innerHTML = ICON_PLAY; });
  // Доиграла - остаёмся на конце с ▶: тап играет заново с начала.
  reviewAudio.addEventListener('ended', function () { document.getElementById('review-pp').innerHTML = ICON_PLAY; });
  document.getElementById('review-pp').addEventListener('click', function () {
    if (!review.sub) return;
    if (!reviewPlaying) { reviewPlay(reviewSrc); return; }
    if (reviewAudio.ended) reviewAudio.currentTime = 0;
    if (reviewAudio.paused) reviewAudio.play().catch(function () {}); else reviewAudio.pause();
  });
  audioSeekable(document.getElementById('review-track'), reviewAudio, document.getElementById('review-fill'));

  /* Два звука на один плеер (07.09.2026): запись студента и собственное
     замечание устаза. Открыв уже разобранную сдачу, устаз должен слышать не
     только её, но и что сам тогда сказал, - иначе список пересдач читается
     как «кому-то что-то вернули», без содержания. Играет всегда один: тап по
     второй кнопке останавливает первую. */
  function reviewPlay(kind) {
    kind = kind === 'review' ? 'review' : 'own';
    if (reviewPlaying) reviewStopAudio();
    reviewSrc = kind;
    var pp = document.getElementById('review-pp'), track = document.getElementById('review-track');
    var mine = document.getElementById('review-mine');
    mine.classList.toggle('on', kind === 'review');
    document.getElementById('review-src').textContent = T(kind === 'own' ? 'review_src_own' : 'review_src_mine');
    // Волна - у записи студента; у замечания устаза пиков нет, полоса.
    waveRender(track, kind === 'own' ? review.sub.peaks : null);
    trackProgress(track, document.getElementById('review-fill'), 0);
    document.getElementById('review-total').textContent =
      kind === 'own' ? reviewTotalLabel(review.sub.duration) : '0:00';
    pp.disabled = true;
    var path = '/ustaz/audio?id=' + review.sub.id + '&kind=' + kind;
    // След «звук» (07.10.2026, Умар устаз: «не могу прослушать» 15-минутную
    // запись, а сервер отдал файл дважды целиком): пишем, что телефон получил,
    // заиграл ли и чем ответил - чтобы разбирать такое по следу, а не гадать.
    var tag = review.sub.id + ' ' + kind;
    var stage = 'fetch';
    audioSource(path).then(function (url) {
      trail('audio', { n: 'got ' + tag + ' ' + (url.indexOf('blob:') === 0 ? 'blob' : 'stream') });
      stage = 'play';
      reviewAudio.src = url;
      reviewPlaying = kind;
      pp.disabled = false;
      document.getElementById('review-back10').textContent = T('review_back10');
      return audioPlay(reviewAudio, audioReload(reviewAudio, path));
    }).catch(function (e) {
      trail('audio', { n: 'fail ' + stage + ' ' + tag + ' ' + ((e && (e.name + ' ' + e.message)) || '?') });
      // Запись не пошла - говорим в подписи плеера и возвращаем ▶.
      reviewStopAudio();
      document.getElementById('review-src').textContent = T('review_failed');
      setTimeout(function () {
        if (!reviewPlaying) document.getElementById('review-src').textContent = T('review_src_own');
      }, 2500);
    });
  }

  function reviewOpen(submissionId) {
    apiCall('/ustaz/submission?id=' + submissionId).then(function (res) {
      if (!res.data || res.status !== 200) return;
      var sub = res.data;
      if (sub.hifz_page == null) return;   // старая сдача без места - проверять нечего
      // Прежнее состояние заучивания устаза - он и сам студент, его место
      // не должно съехать от того, что он кого-то проверил. «Дальше»
      // (13.09.2026) открывает сдачу, уже стоя в проверке: hifz здесь -
      // место ПРОШЛОЙ сдачи, и запомнить его значило бы вернуть устазу
      // чужую строку (та же ловушка, что была у пересдачи из разбора).
      if (!review.on) {
        review.saved = { on: hifz.on, line: hifz.line, stage: hifz.stage, picking: hifz.picking };
      } else {
        reviewStopAudio();
      }
      review.on = true;
      review.sub = sub;
      reviewPlayerReset();
      review.words = {};
      (sub.error_words || []).forEach(function (m) { review.words[reviewKey(m.line, m.word)] = true; });
      hifz.on = true;
      hifz.picking = false;
      hifz.stage = sub.hifz_stage || 1;
      hifz.line = sub.hifz_line || 0;
      document.getElementById('ustaz').style.display = 'none';
      openMushaf('page');
      document.getElementById('app').classList.add('review');
      var relayout = useViewLayout(sub.hifz_layout);
      if (relayout || currentPage !== sub.hifz_page) {
        loadPage(sub.hifz_page);      // reveal() сама позовёт reviewAfterRender
      } else {
        hifzApply(); hifzHead(); reviewAfterRender();
      }
    });
  }

  function reviewAfterRender() {
    if (!review.on) return;
    reviewAfterShow(null);   // ряд «Дальше» - только после вердикта
    var frozen = !!(review.sub && review.sub.redone);
    ['review-accept', 'review-retake', 'review-comment'].forEach(function (id) {
      document.getElementById(id).style.display = frozen ? 'none' : '';
    });
    var mine = document.getElementById('review-mine');
    mine.style.display = review.sub && review.sub.has_review_audio ? '' : 'none';
    applyErrorMarks(reviewMarkedList());
    reviewHint();
    hifzHead();   // шапку проверки рисует она сама, см. hifzHead
  }

  function reviewClose() {
    reviewStopAudio();
    review.on = false;
    document.getElementById('app').classList.remove('review');
    applyErrorMarks([]);
    if (review.saved) {
      hifz.on = review.saved.on;
      hifz.line = review.saved.line;
      hifz.stage = review.saved.stage;
      hifz.picking = review.saved.picking;
      review.saved = null;
    }
    hifzApply();
    // Лист был в раскладке студента - возвращаем устазу его собственную.
    if (dropViewLayout()) loadPage(currentPage);
    document.getElementById('app').style.display = 'none';
    document.getElementById('ustaz').style.display = 'flex';
    // Обратно на ту вкладку, откуда сдачу открыли (13.09.2026): из
    // «Проверено» - в «Проверено», а не в «Ждут». Группа не меняется -
    // см. ustazGroupId.
    if (ustazZone === 'done') openReviewed();
    else openUstaz();
  }

  function reviewVerdict(verdict) {
    var hint = document.getElementById('review-hint');
    /* Пересдача без голосового разбора не уходит (правило пользователя
       07.09.2026): вернуть работу, не сказав почему, значит оставить
       студента в тупике. Но НЕ отказываем в последний момент - ведём
       записывать замечание, к которому устаз и так шёл, просто на шаг
       раньше. Сервер проверяет то же самое отдельно: страницу можно
       открыть старой версией. */
    if (verdict === 'retake' && !(review.sub && review.sub.has_review_audio)) {
      hint.textContent = T('review_need_comment');
      reviewComment();
      return;
    }
    hint.textContent = T('review_saving');
    apiCall('/ustaz/verdict', {
      method: 'POST',
      body: { id: review.sub.id, verdict: verdict, words: reviewMarkedList() }
    }).then(function (res) {
      if (res.data && res.data.ok) {
        var done = T(verdict === 'accepted' ? 'review_done_ok' : 'review_done_retake');
        hint.textContent = done;
        reviewAfterVerdict(done);
        return;
      }
      if (res.data && res.data.error === 'needs_comment') {
        hint.textContent = T('review_need_comment');
        reviewComment();
        return;
      }
      hint.textContent = T('review_failed');
    }).catch(function () { hint.textContent = T('review_failed'); });
  }

  /* «Дальше» после вердикта (13.09.2026, макет из разбора удобства). Раньше
     каждый вердикт выбрасывал в список: вернуться, дождаться загрузки,
     найти следующую строку, открыть. Теперь следующая сдача той же группы -
     одним тапом прямо из панели.

     Какая «следующая»: та, что в «Ждут» стояла НИЖЕ проверенной (тот же
     порядок, что видит устаз, см. ustazSortBySource), а если ниже ничего -
     первая из оставшихся. Список берём заново, а не из памяти: сдачу мог
     уже разобрать другой устаз или подхвативший супер-админ. Голосовые из
     группы пропускаем - открыть их нечем.

     Только для проверки из «Ждут»: из «Проверено» устаз пересматривает
     старое, у него свой возврат. Ждать больше нечего - как раньше, назад в
     список. */
  var ustazQueueData = null;   // последний отрисованный список «Ждут», см. ustazRenderList
  var reviewNextId = null;

  function ustazOpenable(items, groupId) {
    return ustazSortBySource((items || []).filter(function (it) {
      return it.hifz_page != null && (groupId == null || it.group_id === groupId);
    }));
  }

  // next - сдача для «Дальше» или null: тогда обычные ряды проверки.
  function reviewAfterShow(next) {
    var after = document.getElementById('review-after');
    Array.prototype.forEach.call(document.querySelectorAll('#review-foot > .row'), function (r) {
      r.style.display = (r === after) === !!next ? '' : 'none';
    });
    reviewNextId = next ? next.id : null;
    if (!next) return;
    document.getElementById('review-to-list').textContent = T('review_to_list');
    document.getElementById('review-next').textContent =
      T('review_next', { N: next.student_name || '', P: next.hifz_page });
  }

  function reviewAfterVerdict(doneText) {
    var cur = review.sub;
    var old = ustazQueueData;
    if (ustazZone !== 'queue' || !old || !cur) { setTimeout(reviewClose, 900); return; }
    var groupId = old.shown;
    var oldIds = ustazOpenable(old.items, groupId).map(function (it) { return it.id; });
    var pos = oldIds.indexOf(cur.id);
    apiCall('/ustaz/waiting' + (ustazShowAll ? '?all=1' : '')).then(function (res) {
      if (!review.on || review.sub !== cur) return;   // устаз уже ушёл сам
      var data = res.data;
      if (!data || !data.items) throw new Error('queue');
      data.shown = groupId;
      ustazQueueData = data;
      var fresh = ustazOpenable(data.items, groupId).filter(function (it) { return it.id !== cur.id; });
      if (!fresh.length) { setTimeout(reviewClose, 900); return; }
      var next = fresh.filter(function (it) { return oldIds.indexOf(it.id) > pos; })[0] || fresh[0];
      document.getElementById('review-hint').textContent =
        doneText + ' · ' + T('review_left', { N: fresh.length });
      reviewAfterShow(next);
    }).catch(function () { setTimeout(reviewClose, 900); });
  }

  // Замечание голосом пишем той же панелью, что и сдачу у студента - у устаза
  // нет отдельного "своего" рекордера, и учить его второму интерфейсу незачем.
  var reviewCommentMode = false;

  function reviewComment() {
    reviewStopAudio();
    reviewCommentMode = true;
    hifzRecReset();
    document.getElementById('hifz-rec-place').textContent = review.sub.student_name;
    document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_hint_idle');
    hifzRecButtons('idle');
    document.getElementById('hifz-rec').classList.add('visible');
    hifzRecPad();
  }

  function reviewCommentSend() {
    if (!rec.blob) return;
    hifzRecButtons('sending');
    document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_hint_sending');
    var fd = new FormData();
    fd.append('audio', rec.blob, 'rec');
    fd.append('id', String(review.sub.id));
    fetch(apiBase() + '/ustaz/comment', {
      method: 'POST',
      headers: authHeaders(),
      body: fd
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.ok) {
        document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_sent');
        if (typeof mushafDoneMarks === 'function') mushafDoneMarks('m');
        // Разбор записан - теперь «На пересдачу» пройдёт.
        if (review.sub) review.sub.has_review_audio = true;
        reviewCommentMode = false;
        setTimeout(hifzRecClose, 1000);
        return;
      }
      document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_failed');
      hifzRecButtons('done');
    }).catch(function () {
      document.getElementById('hifz-rec-hint').textContent = T('hifz_rec_failed');
      hifzRecButtons('done');
    });
  }

  // «Мой разбор» - переключатель источника: тап - замечание устаза, ещё тап - снова сдача.
  document.getElementById('review-mine').addEventListener('click', function () {
    reviewPlay(reviewSrc === 'review' ? 'own' : 'review');
  });
  /* Отмотка на 10 секунд (07.09.2026, просьба пользователя): устаз слушает
     чужую начитку и ловит ошибку на слух - нужное место переслушивают по
     нескольку раз, каждое нажатие отматывает ещё на 10 секунд. */
  document.getElementById('review-back10').addEventListener('click', function () {
    reviewAudio.currentTime = Math.max(0, reviewAudio.currentTime - 10);
  });
  document.getElementById('review-comment').addEventListener('click', reviewComment);
  document.getElementById('review-accept').addEventListener('click', function () { reviewVerdict('accepted'); });
  document.getElementById('review-retake').addEventListener('click', function () { reviewVerdict('retake'); });
  document.getElementById('review-to-list').addEventListener('click', function () { reviewClose(); });
  document.getElementById('review-next').addEventListener('click', function () {
    if (reviewNextId) reviewOpen(reviewNextId);
  });

  // Подпись времени сдачи: "сегодня 09:14" / "вчера 21:03" / "02.09 19:22".
  // Сегодняшнюю дату берём У СЕРВЕРА (поле today) - у телефона устаза может
  // быть свой часовой пояс, а sent_at записан в бишкекском времени.
  function ustazWhen(item, today) {
    var full = ustazFormatSince(item.sent_at);
    var hhmm = full.slice(-5);
    if (!item.date) return full;
    if (item.date === today) return T('ustaz_today') + ' ' + hhmm;
    var y = new Date(today + 'T00:00:00');
    y.setDate(y.getDate() - 1);
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    var yStr = y.getFullYear() + '-' + pad(y.getMonth() + 1) + '-' + pad(y.getDate());
    if (item.date === yStr) return T('ustaz_yesterday') + ' ' + hhmm;
    return full;
  }

  // Только время, без дня - для строки ПОД уже показанным заголовком дня
  // (ustazDaySections): "сегодня 14:32" на каждой из десятка строк одного
  // дня - шум, день уже назван один раз заголовком выше.
  function ustazTimeOnly(sentAt) {
    return (sentAt && sentAt.length >= 16) ? sentAt.slice(11, 16) : '';
  }

  var UD_WEEKDAY_KEYS = ['wd_sun', 'wd_mon', 'wd_tue', 'wd_wed', 'wd_thu', 'wd_fri', 'wd_sat'];

  // Заголовок дня для группировки списка (04.09.2026, жалоба: "дни идут
  // скролом"): "Сегодня (04.09)" / "Вчера (03.09)" / "Пятница (29.08)".
  // Без времени - это шапка дня, а не метка одной строки. UTC-якорь (как в
  // subsDateAdd) - иначе часовой пояс устройства сдвинул бы день недели.
  function ustazDayLabel(dateStr, today) {
    if (!dateStr) return '';
    var short = dateStr.slice(8, 10) + '.' + dateStr.slice(5, 7);
    var cap = function (s) { return s.charAt(0).toUpperCase() + s.slice(1); };
    if (dateStr === today) return cap(T('ustaz_today')) + ' (' + short + ')';
    var y = new Date(today + 'T00:00:00Z');
    y.setUTCDate(y.getUTCDate() - 1);
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    var yStr = y.getUTCFullYear() + '-' + pad(y.getUTCMonth() + 1) + '-' + pad(y.getUTCDate());
    if (dateStr === yStr) return cap(T('ustaz_yesterday')) + ' (' + short + ')';
    var d = new Date(dateStr + 'T00:00:00Z');
    return T(UD_WEEKDAY_KEYS[d.getUTCDay()]) + ' (' + short + ')';
  }

  // Список, разбитый на секции по дню - общее для очереди "Ждут" и
  // "Проверено". items уже отсортированы сервером так, что одна дата идёт
  // подряд (не вперемешку) - группировка просто склеивает соседние строки
  // с одинаковым dateOf(it), пересортировки не требуется.
  /* Внутри дня сначала сдачи из приложения, потом голосовые из группы
     (06.09.2026, просьба пользователя). Смысл ровно тот, что он назвал:
     у сдачи из приложения есть лист со строчками и место, её устаз
     открывает и разбирает по словам - это быстро. Голосовое из группы
     открывать нечего, это просто напоминание. Разложенные вперемешку, они
     заставляли устаза тыкать наугад.

     Сортируем ПО ДАТЕ первым ключом, иначе разъедется группировка по дням
     (ustazDaySections склеивает соседние строки одной даты). */
  function ustazSortBySource(items) {
    return items.slice().sort(function (a, b) {
      if (a.date !== b.date) return a.date < b.date ? 1 : -1;
      return (a.hifz_page != null ? 0 : 1) - (b.hifz_page != null ? 0 : 1);
    });
  }

  function ustazDaySections(items, today, dateOf, renderRow) {
    var days = [];
    items.forEach(function (it) {
      var d = dateOf(it);
      if (!days.length || days[days.length - 1].date !== d) days.push({ date: d, rows: [] });
      days[days.length - 1].rows.push(it);
    });
    return days.map(function (day) {
      return '<div class="ustaz-group-title">' + ustazDayLabel(day.date, today) + '</div>' +
        day.rows.map(renderRow).join('');
    }).join('');
  }

  // "ждёт 14 ч". Минуты считает СЕРВЕР (waited_min) - см. _minutes_since в
  // core/db.py, там же почему не в браузере.
  function ustazWaited(min) {
    if (min == null) return '';
    if (min < 60) return T('ustaz_waits', { N: T('ustaz_minutes', { N: min }) });
    if (min < 60 * 24) return T('ustaz_waits', { N: T('ustaz_hours', { N: Math.floor(min / 60) }) });
    return T('ustaz_waits', { N: T('ustaz_days', { N: Math.floor(min / (60 * 24)) }) });
  }

  // Что именно читал студент. Есть только у сдач ИЗ ПРИЛОЖЕНИЯ (место пишется
  // в voice_submissions с 04.09.2026) - у голосового, присланного прямо в
  // группу, места нет и не было.
  function ustazPlace(item) {
    if (item.hifz_page == null) return T('ustaz_no_place');
    if (item.hifz_stage === 2) return T('ustaz_place_half', { P: item.hifz_page });
    if (item.hifz_stage === 3) return T('ustaz_place_page', { P: item.hifz_page });
    return T('ustaz_place', { P: item.hifz_page, L: (item.hifz_line || 0) + 1 });
  }

  // Имя студента и название группы задаёт не наш код (Telegram-профиль,
  // название чата) - в отличие от остального текста в кабинете.
  // Длина записи «1:48» из секунд (14.09.2026). Пусто, если сервер её не
  // знает (старые сдачи, документ вместо голосового).
  function ustazDur(sec) {
    if (sec == null || !(sec >= 0)) return '';
    sec = Math.round(sec);
    var m = Math.floor(sec / 60), s2 = sec % 60;
    return '⏱ ' + m + ':' + (s2 < 10 ? '0' : '') + s2;
  }

  function ustazEsc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function ustazRow(item, today, withGroup) {
    var waited = ustazWaited(item.waited_min);
    var late = item.waited_min != null && item.waited_min >= 60 * 24;
    // Сдачу из приложения можно открыть на проверку (место известно). У
    // голосового, присланного прямо в группу, места нет - открывать нечего,
    // такая строка остаётся просто напоминанием.
    var fromApp = item.hifz_page != null;
    var open = item.id && fromApp ? ' data-review="' + item.id + '"' : '';
    // Метка источника - только у голосовых из группы (13.09.2026): сдачи из
    // приложения идут своим списком, и «через апп» на каждой строке ничего
    // не различало. Голосовые видны, лишь когда их строку развернули.
    var src = fromApp ? '' : '<span class="sub-pill audio">' + T('ustaz_src_audio') + '</span>';
    // Длина записи справа от имени (14.09.2026, вариант В макета): по ней
    // устаз видит, сколько займёт проверка, ещё до тапа. Карточка в две
    // строки - место, время и «ждёт» в одной, третья строка была лишней.
    var dur = ustazDur(item.duration);
    var right = (dur ? '<span class="sub-pill dur">' + dur + '</span>' : '') + src;
    var meta = [ustazPlace(item)];
    if (withGroup) meta.push(ustazEsc(item.group_title));
    var when = ustazTimeOnly(item.sent_at);
    if (when) meta.push(when);
    if (waited) meta.push('<b' + (late ? ' class="late"' : '') + '>' + waited + '</b>');
    return '<div class="ustaz-row"' + open + '><div class="name">' +
      '<span>' + ustazEsc(item.student_name) + '</span>' + right + '</div>' +
      '<div class="meta">' + meta.join(' · ') + '</div></div>';
  }

  /* Охват записи повторения словами (24.09.2026): «стр. 241–250», а если
     ребёнок не листал (читал по памяти) - «со стр. 241». Старые записи без
     page_from - от начала Аль-Бакары, как считалось тогда. */
  function revSpanText(it) {
    var a = it.page_from || 2, b = it.page_to || a;
    return b > a ? T('ustaz_rev_span', { A: a, B: b }) : T('ustaz_rev_from', { A: a });
  }

  function ustazRevRow(it) {
    var dur = ustazDur(it.duration);
    var right = (dur ? '<span class="sub-pill dur">' + dur + '</span>' : '') +
      (it.short ? '<span class="sub-pill short">' + ICON['triangle-alert'] + ' ' + T('ustaz_rev_short') + '</span>' : '');
    var meta = [revSpanText(it)];
    var when = ustazTimeOnly(it.sent_at);
    if (when) meta.push(when);
    if (!it.verdict) meta.push('<b class="rev-play">' + ICON.play + ' ' + T('ustaz_rev_play') + '</b>');
    /* Плеер и вердикт живут в самой карточке (16.09.2026): отдельный экран
       разбора здесь не нужен - устаз слушает выборочно и решает на месте.
       Уже разобранная запись показывает итог вместо кнопок. */
    var tail = it.verdict
      ? '<div class="rev-done">' + T(it.verdict === 'rejected' ? 'ustaz_rev_rejected' : 'ustaz_rev_accepted') + '</div>'
      : '<div class="rev-player" data-player="' + it.id + '">' +
          '<div class="line"><button class="pp">' + ICON_PLAY + '</button>' +
          '<div class="rev-track' + (it.peaks && it.peaks.length ? ' has-wave' : '') + '">' +
            '<div class="wave">' + (it.peaks || []).map(function (v) {
              return '<i style="height:' + Math.max(10, Math.min(100, Math.round((+v || 0) * 100))) + '%"></i>';
            }).join('') + '</div><div class="rev-fill"></div></div>' +
          '<span class="rev-time">0:00 / ' + (dur ? dur.replace('⏱ ', '') : '—') + '</span></div>' +
          '<div class="rev-skips">' +
            '<button data-skip="-300">' + ICON.rewind + ' ' + T('ustaz_rev_back5') + '</button>' +
            '<button data-skip="-30">' + ICON.rewind + ' ' + T('ustaz_rev_back') + '</button>' +
            '<button data-skip="30">' + T('ustaz_rev_fwd') + ' ' + ICON['fast-forward'] + '</button>' +
            '<button data-skip="300">' + T('ustaz_rev_fwd5') + ' ' + ICON['fast-forward'] + '</button>' +
          '</div>' +
          '<div class="rev-acts">' +
            '<button class="no" data-verdict="rejected">' + T('ustaz_rev_reject') + '</button>' +
            '<button class="ok" data-verdict="accepted">' + T('ustaz_rev_accept') + '</button>' +
          '</div></div>';
    return '<div class="ustaz-row rev" data-rev="' + it.id + '"><div class="name">' +
      '<span>' + ustazEsc(it.student_name) + '</span>' + right + '</div>' +
      '<div class="meta">' + meta.join(' · ') + '</div>' + tail + '</div>';
  }

  /* Один проигрыватель на весь кабинет: две записи одновременно слушать
     некому, а общий объект даёт «включил другую - первая остановилась». */
  var revAudio = new Audio();
  var revCardEl = null;          // карточка, чей звук сейчас загружен
  var revLoadedId = null;

  function revFmt(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    return Math.floor(sec / 60) + ':' + ('0' + (sec % 60)).slice(-2);
  }

  function revTick() {
    if (!revCardEl) return;
    var fill = revCardEl.querySelector('.rev-fill');
    var time = revCardEl.querySelector('.rev-time');
    var d = isFinite(revAudio.duration) && revAudio.duration > 0 ? revAudio.duration : 0;
    if (fill) fill.style.width = (d ? (revAudio.currentTime / d * 100) : 0) + '%';
    var tr = fill && fill.parentNode;
    if (tr) waveProgress(tr, d ? revAudio.currentTime / d : 0);
    if (time) time.textContent = revFmt(revAudio.currentTime) + ' / ' + (d ? revFmt(d) : '—');
  }
  revAudio.addEventListener('timeupdate', revTick);
  revAudio.addEventListener('loadedmetadata', revTick);
  revAudio.addEventListener('ended', function () {
    if (revCardEl) {
      var pp = revCardEl.querySelector('.pp');
      if (pp) pp.innerHTML = ICON_PLAY;
    }
  });

  function ustazRevStop() {
    try { revAudio.pause(); } catch (e) {}
    if (revCardEl) {
      var pp = revCardEl.querySelector('.pp');
      if (pp) pp.innerHTML = ICON_PLAY;
    }
  }

  // Звук отдаётся через наш сервер (file_id Telegram наружу не уходит), поэтому
  // грузим blob один раз на карточку и дальше перематываем локально.
  function ustazRevLoad(card, id) {
    if (revLoadedId === id) return Promise.resolve();
    ustazRevStop();
    revCardEl = card;
    var pp = card.querySelector('.pp');
    if (pp) pp.textContent = '…';
    return audioSource('/ustaz/revision_audio?id=' + id)
      .then(function (url) {
        revAudio.src = url;
        revLoadedId = id;
        if (pp) pp.innerHTML = ICON_PLAY;
      });
  }

  function ustazRevPlay(card, id) {
    if (revLoadedId === id && !revAudio.paused) { ustazRevStop(); return; }
    ustazRevLoad(card, id).then(function () {
      revCardEl = card;
      var pp = card.querySelector('.pp');
      if (pp) pp.innerHTML = ICON_PAUSE;
      return audioPlay(revAudio, function () {
        revLoadedId = null;
        return ustazRevLoad(card, id).then(function () {
          if (pp) pp.innerHTML = ICON_PAUSE;
        });
      });
    }).catch(function () { ustazRevStop(); });
  }

  function ustazRevSkip(card, id, sec) {
    ustazRevLoad(card, id).then(function () {
      revAudio.currentTime = Math.max(0, revAudio.currentTime + sec);
      revTick();
    }).catch(function () {});
  }

  function ustazRevSeek(card, id, ratio) {
    ustazRevLoad(card, id).then(function () {
      var d = isFinite(revAudio.duration) ? revAudio.duration : 0;
      if (d) { revAudio.currentTime = Math.min(d - 1, Math.max(0, d * ratio)); revTick(); }
    }).catch(function () {});
  }

  function ustazRevVerdict(card, id, verdict) {
    var box = card.querySelector('.rev-acts');
    if (box) box.innerHTML = '<div class="rev-done">' + T('ustaz_loading') + '</div>';
    apiCall('/ustaz/revision_verdict', { method: 'POST', body: { id: id, verdict: verdict } })
      .then(function (res) {
        if (!(res.data && res.data.ok)) throw new Error('verdict');
        ustazRevStop();
        var player = card.querySelector('.rev-player');
        if (player) {
          player.outerHTML = '<div class="rev-done">' +
            T(verdict === 'rejected' ? 'ustaz_rev_rejected' : 'ustaz_rev_accepted') + '</div>';
        }
        var play = card.querySelector('.rev-play');
        if (play) play.remove();
        if (ustazRevs) {
          ustazRevs.forEach(function (r) { if (r.id === id) r.verdict = verdict; });
        }
      }).catch(function () {
        if (box) box.innerHTML = '<div class="rev-done">' + T('hifz_rec_failed') + '</div>';
      });
  }

  // Один слушатель на карточку: кнопки внутри неё пересобираются.
  function ustazRevBind(card) {
    var id = parseInt(card.getAttribute('data-rev'), 10);
    /* Перемотка перетаскиванием по полосе (10.11.2026, решение пользователя):
       раньше только тап в точку и шаги 30 сек / 5 мин. Pointer Events с
       захватом, как в audioSeekable; первый тап ещё и грузит запись, поэтому
       движение до загрузки просто ждёт - перематывать нечего. */
    var seeking = false;
    function seekAt(track, clientX) {
      var box = track.getBoundingClientRect();
      var ratio = Math.min(1, Math.max(0, (clientX - box.left) / box.width));
      trackProgress(track, track.querySelector('.rev-fill'), ratio);
      if (revLoadedId === id) {
        var d = isFinite(revAudio.duration) ? revAudio.duration : 0;
        if (d) { revAudio.currentTime = Math.min(d - 1, Math.max(0, d * ratio)); revTick(); }
      } else {
        ustazRevSeek(card, id, ratio);
      }
    }
    card.addEventListener('pointerdown', function (e) {
      var track = e.target.closest('.rev-track');
      if (!track) return;
      seeking = true;
      try { track.setPointerCapture(e.pointerId); } catch (err) {}
      seekAt(track, e.clientX);
      e.preventDefault();
    });
    card.addEventListener('pointermove', function (e) {
      var track = seeking && e.target.closest('.rev-track');
      if (track) seekAt(track, e.clientX);
    });
    function stopSeek(e) {
      if (!seeking) return;
      seeking = false;
      var track = e.target.closest('.rev-track');
      if (track) { try { track.releasePointerCapture(e.pointerId); } catch (err) {} }
    }
    card.addEventListener('pointerup', stopSeek);
    card.addEventListener('pointercancel', stopSeek);
    card.addEventListener('click', function (e) {
      var t = e.target;
      if (t.closest('.pp')) { ustazRevPlay(card, id); return; }
      if (t.closest('[data-skip]')) {
        ustazRevSkip(card, id, parseInt(t.closest('[data-skip]').getAttribute('data-skip'), 10));
        return;
      }
      if (t.closest('[data-verdict]')) {
        ustazRevVerdict(card, id, t.closest('[data-verdict]').getAttribute('data-verdict'));
        return;
      }
      if (t.closest('.rev-track')) return;   // перемотка - на pointerdown выше
      if (t.closest('.rev-play')) ustazRevPlay(card, id);
    });
  }

  /* Выбранная группа - ОДНА на весь кабинет (13.09.2026, поймано на разборе
     удобства и повторено на стенде). Раньше их было две: своя у «Ждут» и
     своя у «Студентов» с «Проверено», а openUstaz обнулял первую при каждом
     открытии. Проверил сдачу в N-2a, вернулся - снова N-1; перешёл во
     вкладку - там опять N-1.

     Сбрасывает выбор только вход с дашборда (ustazEnter): там по-прежнему
     открывается группа, где ждут больше всего, - не прятать работу
     (решение 04.09.2026). Внутри кабинета выбор держится.

     Списки групп у вкладок разные: в «Ждут» только свои (у супер-админа -
     плюс развёрнутые чужие), в «Студентах» и «Проверено» - все. Если
     выбранной группы в списке вкладки нет, вкладка показывает свою группу
     по умолчанию, но сам выбор не затирает (ustazPickGroup). */
  var ustazGroupId = null;
  // Чужие группы супер-админа развёрнуты («показать остальные»). Держится
  // так же, как выбор группы: иначе после проверки сдачи в чужой группе
  // список сворачивался, и группа пропадала из выбора.
  var ustazShowAll = false;

  function ustazPickGroup(groups, fallback) {
    for (var i = 0; i < (groups || []).length; i++) {
      if (groups[i].id === ustazGroupId) return ustazGroupId;
    }
    return fallback;
  }

  // Полоса вкладок: своя группа первой, число ждущих красным (это долг).
  // Ноль не красим - красить нечего.
  /* Кнопка с текущей группой + список всех по тапу (07.09.2026).

     Порядок: СВОИ группы сверху (устаз отвечает за них), дальше остальные по
     числу ждущих - пустые тонут сами. Раньше порядок задавал сервер, а полоса
     показывала первые три-четыре; теперь виден весь список, и сортировка
     стала важнее: она отвечает на вопрос "куда идти в первую очередь".

     withCounts: в зонах "Студенты" и "Проверено" чисел нет - /ustaz/groups их
     не считает, а выдумывать нули значило бы соврать про долг. */
  function ustazGroupListHTML(groups, currentId, withCounts) {
    if (!groups || groups.length < 2) return '';
    var mine = groups.filter(function (g) { return g.mine !== false; });
    var rest = groups.filter(function (g) { return g.mine === false; });
    if (withCounts) {
      rest.sort(function (a, b) { return (b.waiting || 0) - (a.waiting || 0); });
    }
    var cur = groups.filter(function (g) { return g.id === currentId; })[0] || groups[0];

    function row(g) {
      var n = withCounts
        ? '<span class="n' + (g.waiting ? '' : ' zero') + '">' + g.waiting +
          (g.older ? ' <small>· ' + g.older + '</small>' : '') + '</span>'
        : '';
      return '<div class="g' + (g.id === currentId ? ' on' : '') + '" data-gid="' + g.id + '">' +
        '<div class="t"><span>' + ustazEsc(g.title) + '</span>' +
        (g.mine !== false ? '<span class="mine">' + T('ustaz_group_mine') + '</span>' : '') +
        '</div>' + n + '</div>';
    }

    var list = '';
    if (mine.length && rest.length) {
      list += '<div class="hd">' + T('ustaz_groups_mine') + '</div>' + mine.map(row).join('') +
        '<div class="hd">' + T(withCounts ? 'ustaz_groups_rest_by_debt' : 'ustaz_groups_rest') +
        '</div>' + rest.map(row).join('');
    } else {
      list += groups.map(row).join('');
    }

    var label = ustazEsc(cur.title) +
      (withCounts && cur.waiting ? ' · ' + T('ustaz_group_waiting', { N: cur.waiting }) : '');
    return '<div class="ustaz-picker" id="ustaz-picker"><span>' + label + '</span>' +
      '<span class="caret">' + ICON['chevron-down'] + '</span></div>' +
      '<div class="ustaz-groups" id="ustaz-group-list">' + list + '</div>';
  }

  function ustazGroupTabs(groups, shownId) {
    return ustazGroupListHTML(groups, shownId, true);
  }

  // Какая группа открыта по умолчанию: та, где ждут дольше всего дел, а из
  // равных - своя. Открывать пустую группу первой значило бы прятать работу.
  function ustazDefaultGroup(groups) {
    var best = null;
    groups.forEach(function (g) {
      if (!best) { best = g; return; }
      var better = g.waiting > best.waiting ||
        (g.waiting === best.waiting && g.mine !== false && best.mine === false);
      if (better) best = g;
    });
    return best ? best.id : null;
  }

  function ustazRenderList(data) {
    var body = document.getElementById('ustaz-body');
    var today = data.today || '';
    var groups = data.groups || [];
    var all = data.items || [];
    // Открыта ВСЕГДА одна группа - вертикальную простыню из всех групп
    // подряд листать некому (04.09.2026). Группу выбираем ДО фильтра
    // (08.09.2026): пока это шло наоборот, самый первый рендер отдавал
    // сдачи всех групп сразу, хотя вкладка сверху уже называла одну -
    // поймано на съёмке онбординга, у устаза с двумя группами.
    var byDefault = ustazDefaultGroup(groups);
    if (ustazGroupId === null) ustazGroupId = byDefault;
    var shown = ustazPickGroup(groups, byDefault);
    data.shown = shown;   // хвост «ещё N старше» фильтруется по ней же
    ustazQueueData = data;   // от него считается «Дальше», см. reviewAfterVerdict
    var inGroup = all.filter(function (it) {
      return shown === null || it.group_id === shown;
    });
    /* Голосовые, присланные прямо в группу, - одной строкой внизу (13.09.2026,
       решение пользователя, вариант А макета). Открыть их в кабинете нечем:
       места на листе нет, разбираются они реплаем в Telegram. Вперемешку со
       сдачами из приложения они занимали половину списка. Спрятать совсем
       нельзя - это всё ещё непроверенная работа, поэтому строка
       разворачивается тапом. */
    var items = inGroup.filter(function (it) { return it.hifz_page != null; });
    var voices = inGroup.filter(function (it) { return it.hifz_page == null; });
    var current = groups.filter(function (g) { return g.id === shown; })[0] || null;
    var html = '<div class="ustaz-head">' + ustazZones() + ustazGroupTabs(groups, shown) + '</div>';
    if (!items.length) {
      html += '<div class="ustaz-empty">' +
        T(voices.length ? 'ustaz_app_empty' : 'ustaz_window_empty') + '</div>';
    } else {
      html += ustazDaySections(items, today,
        function (it) { return it.date; },
        function (it) { return ustazRow(it, today, false); });
    }
    if (voices.length) {
      html += '<div class="ustaz-fold" id="ustaz-voices"><div class="t"><b>' +
        T('ustaz_voices_fold', { N: voices.length }) + '</b><span>' +
        T('ustaz_voices_hint') + '</span></div><span class="go">' +
        T('ustaz_voices_show') + '</span></div>';
    }
    /* Записи повторения живут в своей зоне (16.09.2026) - здесь только
       подгружаем их один раз, чтобы в полосе зон появилась вкладка со
       счётчиком. Заучивание в очереди от этого не сдвигается. */
    if (ustazRevs === null) {
      ustazRevs = [];
      apiCall('/ustaz/revisions' + (ustazShowAll ? '?all=1' : '')).then(function (res) {
        var items = (res.data && res.data.items) || [];
        if (items.length) { ustazRevs = items; ustazRenderList(data); }
      }).catch(function () {});
    }
    var olderCount = current ? current.older : data.older;
    if (olderCount) {
      html += '<div class="ustaz-older" id="ustaz-older">' +
        T('ustaz_older', { N: olderCount }) + '</div>';
    }
    /* Чужие группы у супер-устаза свёрнуты (08.09.2026): кабинет открывается
       на своих, остальные - одним тапом. В подписи сразу видно, есть ли там
       работа, иначе кнопка молчит о главном. */
    var hidden = data.hidden || {};
    if (hidden.groups) {
      html += '<div class="ustaz-older" id="ustaz-more-groups">' +
        T(hidden.waiting ? 'ustaz_more_groups' : 'ustaz_more_groups_calm',
          { N: hidden.groups, W: hidden.waiting }) + '</div>';
    }
    body.innerHTML = html;
    ustazBindZones(body);

    Array.prototype.forEach.call(body.querySelectorAll('.ustaz-groups .g'), function (el) {
      el.addEventListener('click', function () {
        ustazGroupId = parseInt(el.getAttribute('data-gid'), 10);
        document.getElementById('ustaz-body').scrollTop = 0;
        ustazRenderList(data);
      });
    });
    ustazBindReviews(body);
    var voicesEl = document.getElementById('ustaz-voices');
    if (voicesEl) voicesEl.addEventListener('click', function () {
      voicesEl.outerHTML = '<div class="ustaz-group-title">' + T('ustaz_voices_title') + '</div>' +
        ustazDaySections(voices, today,
          function (it) { return it.date; },
          function (it) { return ustazRow(it, today, false); });
      ustazBindReviews(body);
    });
    var olderEl = document.getElementById('ustaz-older');
    if (olderEl) olderEl.addEventListener('click', function () { ustazLoadOlder(data); });
    var moreEl = document.getElementById('ustaz-more-groups');
    if (moreEl) moreEl.addEventListener('click', function () { openUstaz(true); });
  }

  /* Тап по сдаче открывает проверку. Одна функция для первого рендера и для
     дописанных позже строк (10.11.2026, поймано на стенде): хвост «ещё N
     старше» и развёрнутые голосовые вставлялись через outerHTML, и у их строк
     обработчика не было - сдачу старше окна нельзя было открыть вовсе. Уже
     привязанные строки помечены, чтобы не вешать обработчик дважды. */
  function ustazBindReviews(root) {
    Array.prototype.forEach.call(root.querySelectorAll('[data-review]:not([data-bound])'), function (el) {
      el.setAttribute('data-bound', '1');
      el.style.cursor = 'pointer';
      el.addEventListener('click', function () {
        reviewOpen(parseInt(el.getAttribute('data-review'), 10));
      });
    });
  }

  // Хвост тянем ОТДЕЛЬНЫМ запросом и дописываем под окном, не заменяя его:
  // старое не должно вытеснять то, что ждёт прямо сейчас. И не тянем его
  // на каждое открытие кабинета - там могут быть сотни строк.
  function ustazLoadOlder(data) {
    var olderEl = document.getElementById('ustaz-older');
    if (olderEl) olderEl.textContent = T('ustaz_loading');
    apiCall('/ustaz/waiting?older=1').then(function (res) {
      var items = ((res.data && res.data.items) || []).filter(function (it) {
        return data.shown == null || it.group_id === data.shown;
      });
      var el = document.getElementById('ustaz-older');
      if (!el) return;
      // Заголовки дня сами делят хвост на понятные куски - отдельный
      // "Старше последних дней" сверху был бы лишней строкой над ними.
      el.outerHTML = ustazDaySections(ustazSortBySource(items), data.today || '',
        function (it) { return it.date; },
        function (it) { return ustazRow(it, data.today || '', true); });
      ustazBindReviews(document.getElementById('ustaz-body'));
    }).catch(function () {
      var el = document.getElementById('ustaz-older');
      if (el) el.textContent = T('ustaz_older', { N: data.older });
    });
  }

