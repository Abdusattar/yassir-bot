  /* ── Лента (11.09.2026) ───────────────────────────────────────────────
     Только чтение. Строка на дашборде живёт от heartbeat (каждые 20 секунд),
     сам экран грузится по открытию - держать ленту в памяти незачем, она
     нужна ровно в тот момент, когда её открыли.

     Тексты пока по-русски: правило «сначала ru, локализация одним проходом,
     когда отшлифуется». */
  var feedBox = document.getElementById('feed');
  var feedScroll = document.getElementById('feed-scroll');
  var feedTop = 0;          // самый свежий показанный id - его и шлём как прочитанное
  var feedPhotoObserver = null;
  var feedItems = [];       // вся лента, разложить по чипам - дело клиента
  var feedChats = [];       // чаты в порядке от сервера: личное, общая, учебная, свои
  var feedChat = null;      // какой чат открыт сейчас

  function feedEsc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /* Сообщения бота в Telegram уходят с HTML-разметкой (<b>, <i>, ссылки), и
     лента хранит их ровно так (core/feed.py record_outgoing). Показывать их
     экранированными - значит видеть «<b>» прямо в тексте (12.11.2026, объявление
     о пословном переводе). Рисуем только то, что умеет сам Telegram: теги из
     белого списка, ссылки http(s)/tg; всё прочее и текст между тегами -
     экранируем. Сообщения людей хранятся простым текстом - им feedEsc, как было. */
  var FEED_TAG = /<(\/?)(b|strong|i|em|u|ins|s|strike|del|code|pre|blockquote)(?:\s[^>]*)?>|<a\s+href="([^"]*)"[^>]*>|<\/a>/gi;
  function feedUnent(t) {
    return t.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
  }
  function feedRich(html) {
    html = String(html == null ? '' : html);
    var out = '', last = 0, m, open = [];
    FEED_TAG.lastIndex = 0;
    while ((m = FEED_TAG.exec(html))) {
      out += feedEsc(feedUnent(html.slice(last, m.index)));
      last = FEED_TAG.lastIndex;
      if (m[2]) {
        var tag = m[2].toLowerCase();
        tag = { strong: 'b', em: 'i', ins: 'u', strike: 's', del: 's' }[tag] || tag;
        if (m[1]) {
          var at = open.lastIndexOf(tag);
          if (at < 0) continue;
          while (open.length > at) out += '</' + open.pop() + '>';
        } else { out += '<' + tag + '>'; open.push(tag); }
      } else if (m[3] !== undefined) {
        var href = feedUnent(m[3]);
        out += /^(https?:|tg:)/i.test(href)
          ? '<a href="' + feedEsc(href) + '" target="_blank" rel="noopener">' : '<a>';
        open.push('a');
      } else {
        var ai = open.lastIndexOf('a');
        if (ai >= 0) while (open.length > ai) out += '</' + open.pop() + '>';
      }
    }
    out += feedEsc(feedUnent(html.slice(last)));
    while (open.length) out += '</' + open.pop() + '>';
    return out;
  }

  function feedInitial(name) {
    return (name || '—').trim().charAt(0).toUpperCase();
  }

  // «14:00» для сегодняшних, «вчера», дальше - число и месяц. created_at
  // приходит из SQLite как UTC без зоны - отдаём его в Date явным UTC,
  // иначе браузер прочитает его как местное и собьёт время на часовой пояс
  // (та же ловушка, что записана в памяти про score_events).
  function feedWhen(at) {
    if (!at) return '';
    var d = new Date(at.replace(' ', 'T') + 'Z');
    if (isNaN(d.getTime())) return '';
    var now = new Date();
    var sameDay = d.toDateString() === now.toDateString();
    if (sameDay) {
      return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
    }
    var y = new Date(now.getTime() - 86400000);
    if (d.toDateString() === y.toDateString()) return T('ustaz_yesterday');
    return d.getDate() + '.' + ('0' + (d.getMonth() + 1)).slice(-2);
  }

  function feedDayLabel(at) {
    var d = new Date((at || '').replace(' ', 'T') + 'Z');
    if (isNaN(d.getTime())) return '';
    var now = new Date();
    if (d.toDateString() === now.toDateString()) return T('feed_today');
    var y = new Date(now.getTime() - 86400000);
    if (d.toDateString() === y.toDateString()) return T('feed_yesterday');
    return d.getDate() + '.' + ('0' + (d.getMonth() + 1)).slice(-2);
  }

  // Строка дашборда. item выбирает сервер (важнейшее непрочитанное, а не
  // последнее по времени) - здесь только рисуем.
  // Линейные значки в один цвет - тем же языком, что у дверей (эмодзи на
  // доске читались вставкой из другого приложения).
  var NOTICE_ICON = {
    lesson: '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v15H5.5A1.5 1.5 0 0 0 4 20.5zM20 5.5A1.5 1.5 0 0 0 18.5 4H13v15h5.5a1.5 1.5 0 0 1 1.5 1.5z"/>',
    kick: '<path d="M12 4 3 19.5h18zM12 10v4.5M12 17.2v.3"/>',
    announce: '<path d="M4 10v4h3l7 4V6l-7 4zM17.5 9.5a4 4 0 0 1 0 5M7 14l1.5 5h2.5"/>',
    transfer: '<path d="M4 12h15M13.5 6.5 19 12l-5.5 5.5"/>',
    task: '<path d="M12 5v14M5 12h14"/><circle cx="12" cy="12" r="9"/>',
    name: '<circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/>'
  };
  // Имя не похоже на имя (07.10.2026): карточка на доске важного, пока не
  // поправит в настройках. Не из ленты - из heartbeat, поэтому без id.
  var nameFix = false;
  // Доска важного (17.09.2026) - отдельно от строки чата: строка показывает
  // последнее, а важное висит, пока не открыл (объявление - до своей даты).
  // Название группы в шапке карточки убрано (05.10.2026, решение
  // пользователя): только тип. Откуда - видно по тапу, он ведёт в ленту группы.
  function boardRender(list) {
    var box = document.getElementById('dash-board');
    list = (list || []).slice();
    if (nameFix) list.unshift({ type: 'name', text: T('notice_name_text'), read: false });
    box.innerHTML = list.map(function (n, i) {
      return '<div class="bd-row' + (n.read ? ' read' : '') + '" data-i="' + i + '" tabindex="0" role="button">' +
        '<span class="bd-ic"><svg viewBox="0 0 24 24" aria-hidden="true">' + (NOTICE_ICON[n.type] || NOTICE_ICON.announce) + '</svg></span>' +
        '<span class="bd-body"><span class="bd-h"><span>' + feedEsc(T('notice_' + n.type)) + '</span></span>' +
        '<span class="bd-t">' + feedEsc(n.text) + '</span></span><span class="bd-go">›</span></div>';
    }).join('');
    box.classList.toggle('on', !!list.length);
    box.classList.toggle('hot', list.some(function (n) { return !n.read; }));
    Array.prototype.forEach.call(box.querySelectorAll('.bd-row'), function (row) {
      var go = function () { boardGo(list[+row.getAttribute('data-i')], row); };
      row.addEventListener('click', go);
      row.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); }
      });
    });
  }
  // Тап: отмечаем открытым и ведём к делу - урок в урок, остальное - в
  // чат, прямо на само сообщение.
  function boardGo(n, row) {
    if (n.type === 'name') { settOpen(); return; }
    apiCall('/feed/notice', { method: 'POST', body: { id: n.id } }).then(function () {
      sendHeartbeat();
    }).catch(function () {});
    row.classList.add('read');
    document.getElementById('dash-board').classList.toggle('hot',
      !!document.querySelector('#dash-board .bd-row:not(.read)'));
    var m = /^lesson:([a-z]):(\d+)$/.exec(n.link || '');
    if (m) {
      openLearn();
      document.getElementById('learn-foot').style.display = 'none';
      lessonsRenderOne(m[1], m[2]);
    } else {
      feedOpen(n.chat_id, n.id);
    }
  }
  function feedBrief(f) {
    var box = document.getElementById('dash-brief');
    boardRender(f && f.notices);
    if (!f || !f.item) { box.classList.remove('on'); return; }
    var it = f.item;
    briefChat = it.chat_id;
    document.getElementById('brief-ava').textContent = feedInitial(it.who);
    document.getElementById('brief-who').textContent = it.who;
    document.getElementById('brief-src').textContent = feedTitle(it.source);
    var txt = it.text;
    if (!txt) txt = it.kind === 'voice' ? T('feed_voice') : it.kind === 'photo' ? T('feed_photo') : T('feed_attach');
    document.getElementById('brief-txt').textContent = txt;
    var n = document.getElementById('brief-n');
    n.textContent = f.unread || '';
    n.classList.toggle('on', !!f.unread);
    document.getElementById('brief-dot').classList.toggle('on', !!f.more);
    box.classList.add('on');
  }

  // Фото грузится, когда до него долистали: в ленте их может быть много, и
  // тянуть все сразу значит жечь чужой трафик ради того, что не увидят.
  function feedWatchPhoto(el) {
    if (!feedPhotoObserver) {
      feedPhotoObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return;
          feedPhotoObserver.unobserve(e.target);
          feedLoadPhoto(e.target);
        });
      }, { rootMargin: '200px' });
    }
    feedPhotoObserver.observe(el);
  }

  function feedLoadPhoto(box) {
    fetch(apiBase() + '/feed/media?id=' + box.getAttribute('data-id'), {
      headers: authHeaders()
    }).then(function (r) {
      if (!r.ok) throw new Error('media');
      return r.blob();
    }).then(function (blob) {
      var img = document.createElement('img');
      img.src = URL.createObjectURL(blob);
      img.alt = '';
      box.appendChild(img);
    }).catch(function () {
      box.textContent = '';
    });
  }

  var feedAudio = new Audio();
  var feedPlayingId = null;
  function feedPlay(id, btn) {
    if (feedPlayingId === id) {
      feedAudio.pause(); feedPlayingId = null; btn.textContent = '▶ ' + T('feed_voice');
      return;
    }
    feedAudio.pause();
    btn.disabled = true;
    var path = '/feed/media?id=' + id;
    audioSource(path)
      .then(function (url) {
        feedAudio.src = url;
        feedPlayingId = id;
        btn.disabled = false;
        btn.textContent = '⏸ ' + T('feed_voice');
        return audioPlay(feedAudio, audioReload(feedAudio, path));
      }).catch(function () {
        btn.disabled = false;
        btn.textContent = T('feed_failed_short');
      });
  }
  feedAudio.addEventListener('ended', function () {
    feedPlayingId = null;
    feedRenderVoiceLabels();
  });
  function feedRenderVoiceLabels() {
    Array.prototype.forEach.call(feedScroll.querySelectorAll('.m-voice'), function (b) {
      b.textContent = '▶ ' + T('feed_voice');
    });
  }

  // Тадаббур сервер подписывает «Общая» (core/feed.py) - на языке
  // интерфейса это слово из словаря (28.10.2026, аудит zh).
  function feedTitle(t) { return t === 'Общая' ? T('feed_common') : (t || ''); }

  function feedRenderChips() {
    var box = document.getElementById('feed-chips');
    if (feedChats.length < 2) { box.innerHTML = ''; return; }
    box.innerHTML = feedChats.map(function (c) {
      return '<button data-chat="' + feedEsc(c.id) + '"'
        + (c.id === feedChat ? ' class="on"' : '') + '>'
        + '<span class="t">' + feedEsc(feedTitle(c.title)) + '</span>'
        + (c.unread ? '<i>' + c.unread + '</i>' : '')
        + '</button>';
    }).join('');
    Array.prototype.forEach.call(box.querySelectorAll('[data-chat]'), function (b) {
      b.addEventListener('click', function () {
        feedChat = b.getAttribute('data-chat');
        feedRenderChips();
        feedRender();
        b.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      });
    });
  }

  function feedRender() {
    var items = feedItems.filter(function (it) {
      return !feedChat || it.chat_id === feedChat;
    });
    if (!items.length) {
      feedScroll.innerHTML = '<div class="l-empty">' + T('feed_empty_html') + '</div>';
        return;
    }
    // Свежие сверху приходят с сервера; на экране читаем как в чате -
    // сверху вниз по дням, самое свежее внизу, и туда же сразу прокручиваем.
    var rows = items.slice().reverse();
    var html = '';
    var day = '';
    rows.forEach(function (it) {
      var d = feedDayLabel(it.at);
      if (d !== day) { day = d; html += '<div class="l-day">' + feedEsc(d) + '</div>'; }
      var media = '';
      if (it.has_media && it.kind === 'photo') {
        media = '<div class="m-photo" data-photo="' + it.id + '" data-id="' + it.id + '"></div>';
      } else if (it.has_media) {
        media = '<button class="m-voice" data-voice="' + it.id + '">▶ ' + T('feed_voice') + '</button>';
      }
      // Источник у строки не подписываем: чат выбран чипом выше, и рамка
      // «N-1» у каждого сообщения внутри N-1 - чистый шум.
      html += '<div class="l-row' + (it.is_bot ? ' bot' : '') + '" data-mid="' + it.id + '">'
        + '<span class="l-ava">' + feedEsc(feedInitial(it.who)) + '</span>'
        + '<span class="l-body">'
        +   '<span class="l-top"><b>' + feedEsc(it.who) + '</b>'
        +     '<u>' + feedEsc(feedWhen(it.at)) + '</u></span>'
        +   (it.text ? '<span class="l-txt">' + (it.is_bot ? feedRich(it.text) : feedEsc(it.text)) + '</span>' : '')
        +   media
        + '</span></div>';
    });
    feedScroll.innerHTML = html;

    Array.prototype.forEach.call(feedScroll.querySelectorAll('[data-photo]'), feedWatchPhoto);
    Array.prototype.forEach.call(feedScroll.querySelectorAll('[data-voice]'), function (b) {
      b.addEventListener('click', function () { feedPlay(b.getAttribute('data-voice'), b); });
    });
    feedScroll.scrollTop = feedScroll.scrollHeight;
    // Пришли с доски важного (17.09.2026): открываем на самом сообщении и
    // подсвечиваем его - иначе вчерашнее объявление пришлось бы искать под
    // полусотней «м р т». Не нашлось (старше выдачи) - остаёмся внизу.
    if (feedFocus) {
      var hit = feedScroll.querySelector('[data-mid="' + feedFocus + '"]');
      feedFocus = null;
      if (hit) {
        feedScroll.scrollTop += hit.getBoundingClientRect().top - feedScroll.getBoundingClientRect().top - 60;
        hit.classList.add('hit');
      }
    }
  }

  // wantChat - чат, на котором открыть ленту. Приходит из строки дашборда:
  // тапнул по разбору устаза - попал в свою учебную, а не в общий список,
  // где его ещё надо найти.
  var feedFocus = null;
  function feedOpen(wantChat, focusId) {
    feedFocus = focusId || null;
    feedBox.classList.add('on');
    feedScroll.innerHTML = '<div class="l-empty">' + T('feed_loading') + '</div>';
    document.getElementById('feed-chips').innerHTML = '';
    apiCall('/feed').then(function (res) {
      var d = res && res.data;
      if (!d || !d.items) { feedScroll.innerHTML = '<div class="l-empty">' + T('feed_failed') + '</div>'; return; }
      feedItems = d.items;
      feedChats = d.chats || [];
      var ids = feedChats.map(function (c) { return c.id; });
      // Чат из строки дашборда, иначе тот, где есть непрочитанное, иначе
      // первый по порядку сервера (личное).
      feedChat = (wantChat && ids.indexOf(wantChat) >= 0) ? wantChat : null;
      if (!feedChat) {
        var hot = feedChats.filter(function (c) { return c.unread; })[0];
        feedChat = hot ? hot.id : (feedChats[0] ? feedChats[0].id : null);
      }
      feedRenderChips();
      feedRender();
      // Прочитано до самого свежего, что показали. Сервер двигает отметку
      // только вперёд, так что повторное открытие ничего не портит.
      if (d.items.length) {
        feedTop = d.items[0].id;
        apiCall('/feed/read', { method: 'POST', body: { last_id: feedTop } })
          .then(function () { sendHeartbeat(); }).catch(function () {});
      }
    }).catch(function () {
      feedScroll.innerHTML = '<div class="l-empty">' + T('feed_failed') + '</div>';
    });
  }
  function feedClose() {
    feedBox.classList.remove('on');
    feedAudio.pause();
    feedPlayingId = null;
  }

  // Чат из строки запоминаем при отрисовке - по нему лента и откроется.
  var briefChat = null;
  document.getElementById('dash-brief').addEventListener('click', function () {
    feedOpen(briefChat);
  });
  document.getElementById('dash-brief').addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); feedOpen(briefChat); }
  });
  document.getElementById('feed-back').addEventListener('click', feedClose);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && feedBox.classList.contains('on')) feedClose();
  });

  // fromMore - открыто из вкладки «Ещё» (04.11.2026): настройки лежат поверх
  // неё, и возврат подписан «← Ещё». Ключ меняем в data-i18n, а не только в
  // тексте - иначе смена языка тут же, в настройках, вернула бы «← Дашборд».
  function settOpen(fromMore) {
    var back = document.getElementById('sett-back');
    back.setAttribute('data-i18n', fromMore === true ? 'back_more' : 'back_dashboard');
    back.textContent = T(back.getAttribute('data-i18n'));
    settBox.classList.add('on');
    markLang();
    markTheme();
    if (!profileLoaded) settLoadProfile();
    // Ссылки для «позвать друга» тянем здесь, а не на дашборде: на главном
    // экране этого действия больше нет (20.09.2026).
    inviteLoad();
  }
  function settClose() { settBox.classList.remove('on'); }

  document.getElementById('btn-profile').addEventListener('click', function () { settOpen(false); });
  document.getElementById('sett-back').addEventListener('click', settClose);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && settBox.classList.contains('on')) settClose();
  });

  settName.addEventListener('change', function () {
    var v = settName.value.trim();
    if (!v) {
      // Пустым имя не остаётся: возвращаем прежнее, чтобы человек не ушёл
      // с экрана, стерев себя.
      settName.value = savedProfile.name || '';
      settSay(nameHint, T(SAVE_ERRORS.name_empty), 'bad', T('sett_name_hint'));
      return;
    }
    if (v === savedProfile.name) return;
    settSave({ name: v }, nameHint, T('sett_name_hint'));
  });

  settYear.addEventListener('change', function () {
    var v = settYear.value.trim();
    if (String(savedProfile.birth_year || '') === v) return;
    settSave({ birth_year: v }, placeHint, '');
  });

  settPlace.addEventListener('change', function () {
    if (settPlace.value === '__other') {
      settCountry.hidden = false;
      settCountry.focus();
      return;                       // ждём саму страну, сохранять нечего
    }
    settCountry.hidden = true;
    settSave({ location: settPlace.value }, placeHint, '');
  });

  settCountry.addEventListener('change', function () {
    var v = settCountry.value.trim();
    if (!v || v === savedProfile.location) return;
    settSave({ location: v }, placeHint, '');
  });

  // Узнаём язык с сервера при старте - он главнее локального кэша
  // (студент мог переключиться с другого устройства).
  // setTimeout(...,0) оставлен как есть (безвредно), хотя сама причина -
  // apiBase() теперь функция, порядок строк файла её больше не касается
  // (03.09.2026, комментарий у apiBase() ниже - там же "undefined/lang"
  // и "undefined/hifz" из лога nginx, повод для этой правки).
  setTimeout(function () {
    apiCall('/lang').then(function (res) {
      // apiCall отдаёт {status, data} - здесь читали language прямо с
      // верхнего уровня, а сервер кладёт его в data (см. handle_lang_get,
      // core/mufradat_api.py:290) - синхронизация языка с другого
      // устройства при старте молчаливо не срабатывала НИКОГДА, отдельно
      // от ловушки undefined/lang выше (найдено 03.09.2026).
      var d = res && res.data;
      if (d && d.language && I18N[d.language] && d.language !== UI_LANG) {
        UI_LANG = d.language;
        try { localStorage.setItem(LANG_KEY, UI_LANG); } catch (e) {}
        applyLang();
        if (typeof loadPage === 'function' && currentPage) loadPage(currentPage);
      }
    }).catch(function (err) { console.error('lang sync', err); });
  }, 0);

  applyLang();

