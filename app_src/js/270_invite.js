  /* ─── «Позвать друга» (20.09.2026) ────────────────────────────────────
     Команда /invite в личке осталась, но кнопка меню в чате занята самим
     приложением, и списка команд там не видно - пользователь не нашёл её у
     своего же бота. Здесь она на виду.

     Отправляет не бот, а сам человек: открываем телеграмное окно «кому
     отправить» с готовым текстом (openTelegramLink + t.me/share). Вне
     Telegram - кладём ссылку в буфер. Ссылка ведёт в ЛИЧКУ бота нужной
     половины: там новичка спросят, брат он или сестра, и отправят в свою
     подготовительную (core/side.py), поэтому пересылать её безопасно. */
  var inviteLinks = null;

  function inviteSay(text) {
    var el = document.getElementById('invite-say');
    if (el) el.textContent = text;
  }

  function inviteApply() {
    var one = !!(inviteLinks && inviteLinks.app);
    document.getElementById('invite-pick').hidden = one;
    document.getElementById('invite-one').hidden = !one;
    inviteSay(T(one ? 'invite_one_hint' : 'invite_who'));
  }

  function inviteLoad() {
    if (inviteLinks) { inviteApply(); return; }
    withAuthCheck(apiCall('/invite'), function (d) {
      inviteLinks = d || {};
      inviteApply();
    });
  }

  function inviteCopy(side) {
    var link = inviteLinks && inviteLinks[side || 'app'];
    if (!link) { inviteSay(T('invite_none')); return; }
    var full = T('invite_text', { L: link });
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(full).then(function () { inviteSay(T('invite_ready')); },
                                               function () { inviteSay(full); });
      return;
    }
    // Старый iOS без clipboard API: временное поле и execCommand. Не вышло -
    // показываем текст целиком, его можно выделить пальцем.
    try {
      var ta = document.createElement('textarea');
      ta.value = full;
      ta.setAttribute('readonly', '');
      ta.style.cssText = 'position:absolute;left:-9999px;top:0';
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand('copy');
      document.body.removeChild(ta);
      inviteSay(ok ? T('invite_ready') : full);
    } catch (e) {
      inviteSay(full);
    }
  }

  function inviteShare(side) {
    var link = inviteLinks && inviteLinks[side];
    if (!link) { inviteSay(T('invite_none')); return; }
    var text = T('invite_text', { L: '' }).replace(/\s*$/, '');
    var tgApi = window.Telegram && window.Telegram.WebApp;
    if (tgApi && tgApi.openTelegramLink) {
      tgApi.openTelegramLink('https://t.me/share/url?url=' + encodeURIComponent(link) +
                             '&text=' + encodeURIComponent(text));
      return;
    }
    inviteCopy(side);
  }

  document.getElementById('invite-app').addEventListener('click', function () { inviteShare('app'); });
  document.getElementById('invite-copy').addEventListener('click', function () { inviteCopy('app'); });
  document.getElementById('invite-male').addEventListener('click', function () { inviteShare('male'); });
  document.getElementById('invite-female').addEventListener('click', function () { inviteShare('female'); });
  document.getElementById('learn-zoom').addEventListener('click', function () {
    this.classList.remove('visible');
  });

  /* Свайп по шагам (08.09.2026, просьба пользователя: «в телефонах часто так
     двигаемся»). Влево - дальше, вправо - назад, ровно как кнопки внизу.
     Порог 45 px и требование горизонтальности: иначе обычная прокрутка
     длинного объяснения пальцем вверх будет через раз перелистывать шаг.
     На странице мусхафа свайп уже живёт (см. justSwiped) - здесь свой,
     отдельный: у #learn-body другое содержимое и другой смысл жеста. */
  (function () {
    var body = document.getElementById('learn-body');
    var x0 = null, y0 = null;
    body.addEventListener('touchstart', function (e) {
      if (e.touches.length !== 1) { x0 = null; return; }
      x0 = e.touches[0].clientX;
      y0 = e.touches[0].clientY;
    }, { passive: true });
    body.addEventListener('touchend', function (e) {
      if (x0 === null || !learnAt) return;
      var t = e.changedTouches[0];
      var dx = t.clientX - x0, dy = t.clientY - y0;
      x0 = null;
      if (Math.abs(dx) < 45 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
      learnStepBy(dx < 0 ? 1 : -1);
    }, { passive: true });
  })();
  document.getElementById('learn-prev').addEventListener('click', function () { learnStepBy(-1); });
  document.getElementById('learn-next').addEventListener('click', function () { learnStepBy(1); });
  document.getElementById('learn-back').addEventListener('click', function () {
    // Из шага «назад» ведёт в оглавление, из оглавления - на дашборд: одним
    // тапом из середины рассказа студента не выкидываем. У уроков уровней на
    // один больше: из текста урока - в список тем, из списка - в оглавление.
    if (learnAt && learnAt.lesson) return lessonsRenderList(learnAt.lesson);
    if (learnAt) return learnRenderToc();
    document.getElementById('learn').style.display = 'none';
    if (learnFromMore) {
      learnFromMore = false;
      document.getElementById('more').style.display = 'flex';
      return;
    }
    document.getElementById('dashboard').style.display = 'flex';
    if (typeof pulseIntroStart === 'function') pulseIntroStart();
  });

  /* Стена пересдачи привела человека сюда (20.09.2026). Раньше экран просто
     подменялся молча: студент жал «дальше» и оказывался в другом месте без
     единого слова - приходилось догадываться. Теперь короткая строка в шапке
     экрана говорит, что произошло, а подробности он читает в блоке
     «ПЕРЕСДАТЬ». Гасим её при обычном заходе с дашборда. */
  function subsWallNote(on) {
    var el = document.getElementById('subs-wall-note');
    if (el) el.style.display = on ? 'block' : 'none';
  }

  /* Плитки уроков наверху «Работы с устазом» (11.11.2026, п. 4 правок):
     у групп с таджвидом и нахвом - те же плитки, что в «Знаниях». */
  var subsLessonsHtml = '';
  function subsLessonsTiles() {
    // По списку предметов /lessons, как в «Знаниях» (12.11.2026): раньше
    // плитки ждали f.learn, и у того, кому уроки открыты, их тут не было.
    var paint = function (subjects) {
      if (!subjects.length) { subsLessonsHtml = ''; return; }
      subsLessonsHtml = '<div class="subs-lessons"><p class="subs-cap">' + T('learn_cap_lessons') +
        '<i>' + T('learn_lessons_note') + '</i></p><div class="subs-grid">' + subjects.map(function (sj) {
        return '<button class="k-tile" data-subs-subj="' + sj.id + '">' +
          subjMark(sj.id) +
          '<span class="t-nm">' + (T(SUBJ_TITLE_KEY[sj.id]) || sj.title) + '</span>' +
          '<span class="t-ds">' + (T('subj_' + sj.id + '_sub') || sj.sub) + '</span>' +
          '<span class="t-cnt">' + T('learn_open_of', { N: sj.open, M: sj.total }) + '</span></button>';
      }).join('') + '</div></div>';
      var body = document.getElementById('subs-body');
      // Вставляем и при пустом списке сдач (12.11.2026): раньше .subs-empty
      // блокировал вставку, и плиток на вкладке не было почти ни у кого.
      if (body && !body.querySelector('.subs-lessons')) {
        body.insertAdjacentHTML('afterbegin', subsLessonsHtml);
      }
    };
    if (lessonsCache) { paint(lessonsCache); return; }
    apiCall('/lessons').then(function (res) {
      var d = res && res.data;
      lessonsCache = (d && d.subjects) || [];
      paint(lessonsCache);
    }).catch(function () {});
  }
  document.getElementById('subs-body').addEventListener('click', function (e) {
    var b = e.target.closest('[data-subs-subj]');
    if (!b) return;
    // openLearn гасит дашборд и «Ещё», а «Устаз» лежал поверх «Знаний» -
    // плитка выглядела некликабельной (12.11.2026, прод).
    document.getElementById('subs').style.display = 'none';
    openLearn(false);
    lessonsRenderList(b.getAttribute('data-subs-subj'));
  });

  function openSubs(fromWall) {
    subsWallNote(!!fromWall);
    subsLessonsTiles();
    document.getElementById('dashboard').style.display = 'none';
    // Раньше сюда приходили только с дашборда, и мусхаф гасить было не нужно.
    // С 13.09.2026 сюда же ведёт закрытый ход пересдачи - прямо из заучивания,
    // а #app лежит поверх и оставил бы человека на листе (поймано на стенде).
    document.getElementById('app').style.display = 'none';
    document.getElementById('trainer').style.display = 'none';
    document.getElementById('subs').style.display = 'flex';
    var body = document.getElementById('subs-body');
    body.innerHTML = '<div class="subs-empty">' + T('subs_loading') + '</div>';
    apiCall('/submissions').then(function (res) {
      var items = (res.data && res.data.items) || [];
      var rejectedRevs = (res.data && res.data.revisions_rejected) || [];
      if (!items.length && !rejectedRevs.length) {
        body.innerHTML = subsLessonsHtml + '<div class="subs-empty">' + T('subs_empty') + '</div>';
        return;
      }
      var today = (res.data && res.data.today) || '';
      // Календарь - наверх, сразу под рукой, а не довеском после всего
      // списка (была ровно эта жалоба).
      var cutoff = subsDateAdd(today, -(SUBS_WINDOW_DAYS - 1));
      // Сдачи из блока «нужно пересдать» в ленте не повторяем - одна и та же
      // строка дважды на экране читается как две разные работы. Отвеченная
      // пересдача (redone) в блоке не висит, значит её место здесь.
      // left_group - долг из группы, откуда студент ушёл (05.11.2026): не
      // задача, а история; в блок «ПЕРЕСДАТЬ» не идёт.
      var feed = items.filter(function (it) {
        return it.verdict !== 'retake' || it.redone || it.left_group;
      });
      var recent = feed.filter(function (it) { return it.date >= cutoff; });
      /* Сверху - только то, что просит устаз (07.09.2026). У активного
         студента сдач больше сотни, из них половина «ждёт проверки» - но это
         очередь УСТАЗА, а не задача студента: он своё сдал. Экран должен
         отвечать на один вопрос - надо ли мне что-то сделать сейчас.

         Блок, а не вкладка: пусто - и его нет вовсе, ноль места. Вкладка же
         существует всегда и заставляет в неё заглядывать, чтобы убедиться,
         что там пусто. */
      /* На этапах 2/3 студент добивает 40+40 частями за 2-3 дня, и каждая
         часть - сдача той же половины/страницы. Такая запись и есть ответ на
         замечание устаза (08.09.2026, решение пользователя): долг гаснет сам,
         карточка уходит в ленту, отдельной «пересдачи» никто не ждёт. Признак
         redone считает сервер тем же правилом, что снимает гейт. */
      var todo = items.filter(function (it) {
        return it.verdict === 'retake' && !it.redone && !it.left_group;
      });
      /* Сверху - самый ранний по МУСХАФУ, а не по дате разбора (13.09.2026,
         решение пользователя). Устаз мог разобрать стр. 7 в понедельник, а
         стр. 6 во вторник: по дате «старше» стр. 7, хотя по Корану она позже,
         и закрывать вразнобой со своим же движением по листам человеку
         незачем. Тем же порядком список отвечает «которую первой» - верхнюю.
         Порядок, а не запрет: стена стоит, пока не закрыты все. */
      todo.sort(function (a, b) {
        return (a.hifz_page - b.hifz_page)
          || ((a.hifz_line || 0) - (b.hifz_line || 0))
          || ((a.hifz_stage || 1) - (b.hifz_stage || 1));
      });
      var waiting = items.filter(function (it) { return !it.reviewed_at; }).length;
      var html = '';
      /* Отвергнутая запись повторения (16.09.2026) - своим блоком сверху, как
         «ПЕРЕСДАТЬ» у заучивания: это единственное на экране, что требует
         действия прямо сейчас. Успеет до полуночи - зачёт вернётся. */
      // «Ваша активность» (12.11.2026, правка пользователя): над всем, что про
      // свои сдачи - пересдачи, «на проверке», полоса месяца, - не только над полосой.
      html += '<p class="subs-cap">' + T('subs_cap_activity') + '</p>';

      (rejectedRevs || []).forEach(function (rv) {
        html += '<div class="subs-todo"><div class="hd">' + T('subs_rev_title') + '</div>' +
          '<div class="body"><div class="sub-row"><div class="top">' +
          '<span class="place">' + T('subs_rev_meta', {
            D: ustazDayLabel(rv.date, today), S: revSpanText(rv),
            T: revFmt(rv.duration) }) + '</span></div></div>' +
          '<div class="subs-todo-hint">' + T('subs_rev_hint') + '</div>' +
          '<div class="subs-rev-go"><button id="subs-rev-go">' + ICON.repeat + ' ' + T('subs_rev_go') + '</button></div>' +
          '</div></div>';
      });
      if (todo.length) {
        // «Почему» стоит НАД строками (20.09.2026): человека сюда приводит
        // стена, и правило он должен прочитать раньше списка, а не после
        // него. Прежняя подпись «Пересдай — путь открыт» осталась внизу как
        // короткий итог.
        html += '<div class="subs-todo"><div class="hd">' +
          T('subs_todo_title', { N: todo.length }) + '</div><div class="body" id="subs-todo-rows">' +
          '<div class="subs-todo-why">' + T('subs_todo_why') + '</div>' +
          todo.map(function (it) { return subsRow(it, today); }).join('') +
          '<div class="subs-todo-hint">' + T('subs_todo_hint') + '</div></div></div>';
      }
      // «На проверке» - тихой строкой, без красного: у студента их бывает по
      // сотне, и счётчик долга здесь читался бы как «у меня что-то не так».
      if (waiting) {
        html += '<div class="subs-quiet">' + T('subs_waiting_quiet', { N: waiting }) + '</div>';
      }
      html += '<div id="subs-month"></div><div id="subs-lesson"></div><div id="subs-absence"></div>' +
        '<div id="subs-recent-rows">' +
        recent.map(function (it) { return subsRow(it, today); }).join('') +
        '</div>';
      html += '<div class="subs-empty" style="margin-top:6px;font-size:12.5px">' +
        T('subs_retake_hint') + '</div>';
      body.innerHTML = subsLessonsHtml + html;   // плитки уроков первым блоком
      subsLoadMonth();
      subsBindRows(document.getElementById('subs-recent-rows'), items);
      var todoBox = document.getElementById('subs-todo-rows');
      if (todoBox) subsBindRows(todoBox, items);
    }).catch(function () {
      body.innerHTML = '<div class="subs-empty">' + T('subs_empty') + '</div>';
    });
  }

