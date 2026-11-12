  /* ─── Зона "Студенты" (04.09.2026, макет 01.09) ────────────────────────
     Не рейтинг, а "кому нужна помощь": месяц полосками по дням и пропуски
     против ПОРОГА ГРУППЫ, названного прямо. Порог берём с сервера, где он
     совпадает с тем, по которому студента реально переводят в Тадаббур
     (core/transfers.py) - два разных числа тут были бы обманом.

     Успеваемость видит ЛЮБОЙ устаз по ЛЮБОЙ группе (решение пользователя):
     проверять он по-прежнему может только у себя, а знать - про всех. */
  var ustazZone = 'queue';          // 'queue' | 'students' | 'done' | 'revisions'
  /* Записи повторения младших (16.09.2026) - СВОЯ зона, не хвост очереди.
     Причина (вопрос пользователя): в «Ждут» лежит заучивание всей группы, в
     G-12 это уже десять карточек, и записи детей внизу пришлось бы каждый раз
     прокручивать. Вкладка появляется только у того, кому есть что слушать. */
  var ustazRevs = null;             // null - ещё не грузили, [] - грузили, пусто
  var doneFilter = 'all';           // срез зоны "Проверено": 'all' | 'retake'
  var stuGroups = null;             // все группы, грузим один раз за сессию
  var stuShown = null;              // группа на экране «Студентов»/«Проверено», см. ustazGroupId
  var stuData = null;

  function ustazZones() {
    var four = !!(ustazRevs && ustazRevs.length);
    return '<div class="ustaz-zones' + (four ? ' four' : '') + '">' +
      '<button data-zone="queue"' + (ustazZone === 'queue' ? ' class="on"' : '') + '>' +
      T('ustaz_zone_queue') + '</button>' +
      '<button data-zone="students"' + (ustazZone === 'students' ? ' class="on"' : '') + '>' +
      T('ustaz_zone_students') + '</button>' +
      '<button data-zone="done"' + (ustazZone === 'done' ? ' class="on"' : '') + '>' +
      T('ustaz_zone_done') + '</button>' +
      ((ustazRevs && ustazRevs.length)
        ? '<button data-zone="revisions"' + (ustazZone === 'revisions' ? ' class="on"' : '') + '>' +
          T('ustaz_zone_revisions') + ' · ' + ustazRevs.length + '</button>'
        : '') +
      '</div>';
  }

  // Раскрытие списка групп. Вешаем здесь, а не в каждом месте отрисовки:
  // ustazBindZones зовётся из всех трёх зон, и список одинаков во всех.
  function ustazBindPicker(body) {
    var btn = body.querySelector('#ustaz-picker');
    var list = body.querySelector('#ustaz-group-list');
    if (!btn || !list) return;
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      list.classList.toggle('open');
    });
    // Тап мимо списка закрывает его - привычное поведение выпадающих меню,
    // как у выбора языка на дашборде.
    document.addEventListener('click', function (e) {
      if (list.classList.contains('open') && !list.contains(e.target)) {
        list.classList.remove('open');
      }
    });
  }

  function ustazBindZones(body) {
    ustazBindPicker(body);
    Array.prototype.forEach.call(body.querySelectorAll('.ustaz-zones button'), function (b) {
      b.addEventListener('click', function () {
        ustazZone = b.getAttribute('data-zone');
        body.scrollTop = 0;
        if (ustazZone === 'queue') openUstaz();
        else if (ustazZone === 'done') openReviewed();
        else if (ustazZone === 'revisions') openRevisions();
        else openStudents();
      });
    });
  }

  function stuGroupTabs() {
    return ustazGroupListHTML(stuGroups, stuShown, false);
  }

  // Сколько дней в месяце и какой день сегодня - чтобы будущие дни не
  // выглядели пропусками (студент их ещё не мог сдать).
  function stuMonthInfo(month, today) {
    var y = parseInt(month.slice(0, 4), 10), m = parseInt(month.slice(5, 7), 10);
    var days = new Date(y, m, 0).getDate();
    var isCurrent = today.slice(0, 7) === month;
    return { year: y, month: m, days: days, today: isCurrent ? parseInt(today.slice(8, 10), 10) : days };
  }

  function stuDayKey(month, day) {
    return month + '-' + (day < 10 ? '0' : '') + day;
  }

  function stuStrip(days, month, today, lessons, pauses, miss) {
    var info = stuMonthInfo(month, today), out = '', has = false;
    for (var d = 1; d <= info.days; d++) {
      var n = days[stuDayKey(month, d)] || 0;
      var cls = d > info.today ? 'future' : dayLevel(miss, stuDayKey(month, d), n);
      // Пауза «Цикл» (03.11.2026) - не розовым пропуском, а тихой чертой.
      if (!n && (pauses || []).indexOf(stuDayKey(month, d)) >= 0) cls = 'pz';
      if ((lessons || []).indexOf(stuDayKey(month, d)) >= 0) { cls += ' les'; has = true; }
      out += '<i class="' + cls + '"></i>';
    }
    return '<div class="stu-strip' + (has ? ' has-les' : '') + '">' + out + '</div>';
  }

  function stuMissLine(st, threshold) {
    if (!threshold) return T('ustaz_misses_no_limit', { N: st.missed });
    return T('ustaz_misses', { N: st.missed, M: threshold });
  }

  /* Зона "Проверено" (04.09.2026, макет 01.09) - что уже разобрано, свежее
     сверху, с вердиктом и с тем, КТО его поставил: в группе проверяет и её
     устаз, и подхвативший супер-админ, и это ровно тот вопрос, ради которого
     зона нужна. Группа берётся та же, что выбрана в "Студентах" - один
     выбор на весь кабинет, а не три разных. */
  /* Зона «Повторения» (16.09.2026): записи чтения младших по выбранной
     группе, свежие сверху, неделя. Вердиктов здесь нет - это не долг устаза,
     он слушает выборочно, «⚠ коротко» подсказывает кого. */
  function openRevisions() {
    ustazZone = 'revisions';
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('ustaz').style.display = 'flex';
    var body = document.getElementById('ustaz-body');
    body.innerHTML = '<div class="ustaz-empty">' + T('ustaz_loading') + '</div>';
    var groupsReady = stuGroups
      ? Promise.resolve({ data: { groups: stuGroups } })
      : apiCall('/ustaz/groups');
    groupsReady.then(function (res) {
      stuGroups = (res.data && res.data.groups) || [];
      stuShown = ustazPickGroup(stuGroups, stuGroups.length ? stuGroups[0].id : null);
      return apiCall('/ustaz/revisions' + (ustazShowAll ? '?all=1' : ''));
    }).then(function (res) {
      ustazRevs = (res.data && res.data.items) || [];
      var today = (res.data && res.data.today) || '';
      var items = ustazRevs.filter(function (it) {
        return stuShown === null || it.group_id === stuShown;
      });
      var html = '<div class="ustaz-head">' + ustazZones() + stuGroupTabs() + '</div>';
      html += items.length
        ? ustazDaySections(items, today,
            function (it) { return it.date; },
            function (it) { return ustazRevRow(it); })
        : '<div class="ustaz-empty">' + T('ustaz_rev_empty') + '</div>';
      body.innerHTML = html;
      ustazBindZones(body);
      Array.prototype.forEach.call(body.querySelectorAll('[data-rev]'), ustazRevBind);
      Array.prototype.forEach.call(body.querySelectorAll('.ustaz-groups .g'), function (el) {
        el.addEventListener('click', function () {
          ustazGroupId = parseInt(el.getAttribute('data-gid'), 10);
          body.scrollTop = 0;
          openRevisions();
        });
      });
    }).catch(function () {
      body.innerHTML = '<div class="ustaz-empty">' + T('ustaz_rev_empty') + '</div>';
    });
  }

  function openReviewed() {
    ustazZone = 'done';
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('ustaz').style.display = 'flex';
    var body = document.getElementById('ustaz-body');
    body.innerHTML = '<div class="ustaz-empty">' + T('ustaz_loading') + '</div>';
    var groupsReady = stuGroups
      ? Promise.resolve({ data: { groups: stuGroups } })
      : apiCall('/ustaz/groups');
    groupsReady.then(function (res) {
      stuGroups = (res.data && res.data.groups) || [];
      stuShown = ustazPickGroup(stuGroups, stuGroups.length ? stuGroups[0].id : null);
      return apiCall('/ustaz/reviewed?group=' + stuShown);
    }).then(function (res) {
      var all = (res.data && res.data.items) || [];
      var today = (res.data && res.data.today) || '';
      var retakes = all.filter(function (it) { return it.verdict === 'retake'; });
      var items = doneFilter === 'retake' ? retakes : all;
      var html = '<div class="ustaz-head">' + ustazZones() + stuGroupTabs() +
        '<div class="ustaz-filter">' +
        '<button data-done="all"' + (doneFilter === 'all' ? ' class="on"' : '') + '>' +
        T('ustaz_done_all') + '</button>' +
        '<button data-done="retake"' + (doneFilter === 'retake' ? ' class="on"' : '') + '>' +
        T('ustaz_done_retakes', { N: retakes.length }) + '</button>' +
        '</div></div>';
      if (!items.length) {
        html += '<div class="ustaz-empty">' + T('ustaz_done_empty') + '</div>';
      } else {
        // Группируем по дате РАЗБОРА (reviewed_at), не сдачи (date) - список
        // отсортирован по reviewed_at, и группировка по другому полю рвала
        // бы соседние строки одного дня в два разных, повторяющихся
        // заголовка (04.09.2026, поймано на ревью).
        html += ustazDaySections(items, today,
          function (it) { return it.reviewed_at ? it.reviewed_at.slice(0, 10) : it.date; },
          function (it) {
            var pill = it.verdict === 'accepted'
              ? ['done', T('subs_verdict_ok')]
              : (it.verdict === 'retake' ? ['retake', T('subs_verdict_retake')]
                // Разобрано реплаем в группе, без явного вердикта. Слово
                // студента («сдано») здесь не годится: устаз смотрит на
                // СВОЮ работу, а не на факт сдачи.
                : ['wait', T('ustaz_pill_done')]);
            /* Строку можно открыть - тот же лист, что видит студент: его
               пометки, запись студента и голос разбора. Открывается только
               сдача из приложения: у голосового, присланного в группу, места
               на листе нет и показывать нечего. */
            var open = it.hifz_page != null;
            // Что внутри: без этого «принято» с разбором на пять слов и
            // «принято» молчком выглядят в списке одинаково.
            var what = [];
            var dur = ustazDur(it.duration);
            if (dur) what.push(dur);
            if (it.marks) what.push(T('subs_marked_words', { N: it.marks }));
            if (it.has_review_audio) what.push(T('ustaz_has_voice'));
            var note = '';
            if (it.verdict === 'retake') {
              // Пересдал - долг закрыт самим фактом записи (то же правило, что
              // у гейта). Без этой строки пометка «на пересдачу» висела бы
              // вечно, хотя ответ студента уже лежит в «Ждут».
              note = it.redone
                ? '<div class="note answered">' + T('ustaz_retake_answered') + '</div>'
                : '<div class="note wait">' + T('ustaz_retake_waiting') + '</div>';
            }
            return '<div class="sub-row' + (open ? ' open' : '') + '"' +
              (open ? ' data-review="' + it.id + '"' : '') + '><div class="top">' +
              '<span class="place">' + ustazEsc(it.student_name) + '</span>' +
              '<span class="sub-pill ' + pill[0] + '">' + pill[1] + '</span></div>' +
              '<div class="meta">' + ustazPlace(it) +
              (it.verdict_by_name ? ' · ' + T('ustaz_by', { N: ustazEsc(it.verdict_by_name) }) : '') +
              (what.length ? ' · ' + what.join(' · ') : '') + '</div>' + note + '</div>';
          });
      }
      body.innerHTML = html;
      ustazBindZones(body);
      Array.prototype.forEach.call(body.querySelectorAll('[data-review]'), function (el) {
        el.addEventListener('click', function () {
          reviewOpen(parseInt(el.getAttribute('data-review'), 10));
        });
      });
      Array.prototype.forEach.call(body.querySelectorAll('.ustaz-filter button'), function (b) {
        b.addEventListener('click', function () {
          doneFilter = b.getAttribute('data-done');
          body.scrollTop = 0;
          openReviewed();
        });
      });
      Array.prototype.forEach.call(body.querySelectorAll('.ustaz-groups .g'), function (el) {
        el.addEventListener('click', function () {
          ustazGroupId = parseInt(el.getAttribute('data-gid'), 10);
          body.scrollTop = 0;
          openReviewed();
        });
      });
    }).catch(function () {
      body.innerHTML = '<div class="ustaz-empty">' + T('ustaz_done_empty') + '</div>';
    });
  }

  function openStudents() {
    ustazZone = 'students';
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('ustaz').style.display = 'flex';
    var body = document.getElementById('ustaz-body');
    body.innerHTML = '<div class="ustaz-empty">' + T('ustaz_loading') + '</div>';
    var load = stuGroups
      ? Promise.resolve({ data: { groups: stuGroups } })
      : apiCall('/ustaz/groups');
    load.then(function (res) {
      stuGroups = (res.data && res.data.groups) || [];
      if (!stuGroups.length) {
        body.innerHTML = '<div class="ustaz-head">' + ustazZones() + '</div>' +
          '<div class="ustaz-empty">' + T('ustaz_students_empty') + '</div>';
        ustazBindZones(body);
        return;
      }
      // Своя группа первая, см. сортировку на сервере.
      stuShown = ustazPickGroup(stuGroups, stuGroups[0].id);
      return apiCall('/ustaz/students?group=' + stuShown).then(function (r) {
        stuData = r.data || {};
        stuRenderList();
      });
    }).catch(function () {
      body.innerHTML = '<div class="ustaz-empty">' + T('ustaz_empty') + '</div>';
    });
  }

  function stuRenderList() {
    var body = document.getElementById('ustaz-body');
    var data = stuData || {};
    var students = data.students || [];
    var html = '<div class="ustaz-head">' + ustazZones() + stuGroupTabs() + '</div>';
    if (!students.length) {
      html += '<div class="ustaz-empty">' + T('ustaz_students_empty') + '</div>';
    } else {
      html += students.map(function (st) {
        // Красным - когда до порога осталось меньше четверти запаса: это
        // ещё не перевод, но уже разговор.
        var near = data.threshold && st.missed >= data.threshold * 0.75;
        return '<div class="stu-row" data-sid="' + st.id + '">' +
          '<div class="top"><span class="name">' + ustazEsc(st.name) + '</span>' +
          '<span class="miss' + (near ? ' near' : '') + '">' +
          stuMissLine(st, data.threshold) + '</span></div>' +
          stuStrip(st.days || {}, data.month, data.today, st.lesson_days, st.pause_days, st.miss) +
          '</div>';
      }).join('') + '<div class="stu-legend">' + T('ustaz_strip_legend') +
        (students.some(function (st) { return (st.lesson_days || []).length; })
          ? '<br>' + T('ustaz_lesson_legend') : '') + '</div>';
    }
    body.innerHTML = html;
    ustazBindZones(body);
    Array.prototype.forEach.call(body.querySelectorAll('.ustaz-groups .g'), function (el) {
      el.addEventListener('click', function () {
        ustazGroupId = parseInt(el.getAttribute('data-gid'), 10);
        body.scrollTop = 0;
        openStudents();
      });
    });
    Array.prototype.forEach.call(body.querySelectorAll('.stu-row'), function (el) {
      el.addEventListener('click', function () {
        stuOpenStudent(parseInt(el.getAttribute('data-sid'), 10));
      });
    });
  }

  // Календарь одного студента - ровно тот же, что потом увидит он сам:
  // разговор "ты пропускал" перестаёт быть спором, оба смотрят в один экран.
  function stuOpenStudent(studentId) {
    var body = document.getElementById('ustaz-body');
    body.innerHTML = '<div class="ustaz-empty">' + T('ustaz_loading') + '</div>';
    apiCall('/ustaz/student?id=' + studentId + '&group=' + stuShown).then(function (res) {
      var d = res.data || {};
      var info = stuMonthInfo(d.month, d.today);
      // Пустые клетки до первого дня месяца - чтобы столбцы попали на свои
      // дни недели (понедельник первый).
      var first = new Date(info.year, info.month - 1, 1).getDay();
      var lead = (first + 6) % 7;
      var cells = '';
      for (var i = 0; i < lead; i++) cells += '<div class="c empty"></div>';
      for (var day = 1; day <= info.days; day++) {
        var tasks = (d.days || {})[stuDayKey(d.month, day)] || [];
        var key = stuDayKey(d.month, day);
        var cls = day > info.today ? 'future' : dayLevel(d.miss, key, tasks.length);
        if ((d.lessons || []).indexOf(key) >= 0) cls += ' les' + (d.can_edit_lessons ? ' tap' : '');
        if (dayIsPartial(d, tasks, key)) cls += ' part';
        else if (!tasks.length && dayIsPause(d, key)) cls += ' pz';
        cells += '<div class="c ' + cls + '" data-date="' + key + '">' + day + '</div>';
      }
      var missed = 0;
      for (var dd = 1; dd <= info.today; dd++) {
        // День паузы «Цикл» - не пропуск (03.11.2026).
        if (!((d.days || {})[stuDayKey(d.month, dd)] || []).length &&
            !dayIsPause(d, stuDayKey(d.month, dd))) missed++;
      }
      body.innerHTML = '<div class="ustaz-head">' +
        '<button class="nav-back" id="stu-back">' + T('ustaz_student_back') + '</button>' +
        '</div>' +
        '<div class="ustaz-group-title">' + ustazEsc(d.name) + '</div>' +
        '<div class="stu-cal">' + cells + '</div>' +
        '<div class="stu-legend">' +
        (d.threshold ? T('ustaz_misses', { N: missed, M: d.threshold })
                     : T('ustaz_misses_no_limit', { N: missed })) +
        ((d.lessons || []).length
          ? ' · ' + T(d.can_edit_lessons ? 'ustaz_lesson_cal_legend' : 'lesson_dot_legend') : '') +
        ((d.pauses || []).length ? ' · ' + T('pause_legend') : '') +
        '</div>';
      document.getElementById('stu-back').addEventListener('click', openStudents);
      // Ошибочная отметка урока снимается тапом по дню с точкой, с
      // подтверждением (14.09.2026). Ставить за студента устаз не может.
      Array.prototype.forEach.call(body.querySelectorAll('.stu-cal .c.les.tap'), function (c) {
        c.addEventListener('click', function () {
          var date = c.getAttribute('data-date');
          showConfirm(T('ustaz_lesson_remove', { D: subsShortDate(date), N: d.name }), function () {
            apiCall('/ustaz/lesson/remove', {
              method: 'POST', body: { student_id: studentId, group_id: stuShown, date: date }
            }).then(function () { stuOpenStudent(studentId); });
          });
        });
      });
      // Неполный день - мини-отчёт по студенту (07.10.2026), тот же, что
      // видит он сам. День с точкой урока и правом снимать её остаётся за
      // снятием отметки - у него свой тап выше.
      Array.prototype.forEach.call(body.querySelectorAll('.stu-cal .c.part:not(.tap), .stu-cal .c.pz:not(.tap)'), function (c) {
        c.addEventListener('click', function () {
          dayReportToggle(body, c, '/ustaz/day?id=' + studentId + '&group=' + stuShown);
        });
      });
    }).catch(function () {
      openStudents();
    });
  }

  // Вход с дашборда - единственное место, где выбор группы и развёрнутые
  // чужие группы сбрасываются (см. ustazGroupId).
  function ustazEnter() {
    ustazGroupId = null;
    ustazShowAll = false;
    openUstaz();
  }

  // withAll - развернуть чужие группы (только у супер-устаза, см.
  // core/mufradat_api.py:_visible_ustaz_groups). Развёрнутыми они остаются
  // до выхода на дашборд.
  function openUstaz(withAll) {
    if (withAll) ustazShowAll = true;
    ustazZone = 'queue';
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('ustaz').style.display = 'flex';
    var body = document.getElementById('ustaz-body');
    body.innerHTML = '<div class="ustaz-empty">' + T('ustaz_loading') + '</div>';
    apiCall('/ustaz/waiting' + (ustazShowAll ? '?all=1' : '')).then(function (res) {
      if (res.status === 401 || res.status === 403 || !res.data) {
        body.innerHTML = '<div class="ustaz-empty">' + T('ustaz_empty') + '</div>';
        return;
      }
      ustazRenderList(res.data);
    }).catch(function () {
      body.innerHTML = '<div class="ustaz-empty">' + T('ustaz_empty') + '</div>';
    });
  }

  function openTrainer() {
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('trainers').style.display = 'none';
    document.getElementById('app').style.display = 'none';
    document.getElementById('trainer').style.display = 'flex';
    document.getElementById('trainer-body').innerHTML = '<div class="trainer-msg">' + T('loading') + '</div>';
    withAuthCheck(apiCall('/state'), function (data) { trainerState = data; renderTrainer(); });
  }

