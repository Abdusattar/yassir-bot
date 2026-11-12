  // ── Список сур (31.08.2026) ───────────────────────────────────────────
  // Студенты, закончившие Аль-Бакару, уходят дальше по мусхафу, и держать
  // в голове номер страницы каждой суры им незачем. Точка входа - само
  // название суры в шапке (#btn-surah-pick), список всплывает оверлеем:
  // постоянного места в хроме не занимает, текст мусхафа не теснит.
  //
  // Таблица [номер, арабское имя, первая страница] выведена программно из
  // наших же 604 page*.json (первое вхождение аята суры + surah_name_ar из
  // строки-заголовка; у 17 сур заголовочной строки в данных нет - имя взято
  // из surah_names той же страницы). Сверена с печатным мадани-мусхафом на
  // независимо известных началах: Аль-Кахф 293, Ясин 440, Ар-Рахман 531,
  // Аль-Мульк 562, Ан-Наба 582, Аль-Ихлас 604 - все совпали.
  var SURAH_INDEX = [
    [1,"الفاتحة",1],[2,"البقرة",2],[3,"آل عمران",50],[4,"النساء",77],[5,"المائدة",106],
    [6,"الأنعام",128],[7,"الأعراف",151],[8,"الأنفال",177],[9,"التوبة",187],[10,"يونس",208],
    [11,"هود",221],[12,"يوسف",235],[13,"الرعد",249],[14,"ابراهيم",255],[15,"الحجر",262],
    [16,"النحل",267],[17,"الإسراء",282],[18,"الكهف",293],[19,"مريم",305],[20,"طه",312],
    [21,"الأنبياء",322],[22,"الحج",332],[23,"المؤمنون",342],[24,"النور",350],[25,"الفرقان",359],
    [26,"الشعراء",367],[27,"النمل",377],[28,"القصص",385],[29,"العنكبوت",396],[30,"الروم",404],
    [31,"لقمان",411],[32,"السجدة",415],[33,"الأحزاب",418],[34,"سبإ",428],[35,"فاطر",434],
    [36,"يس",440],[37,"الصافات",446],[38,"ص",453],[39,"الزمر",458],[40,"غافر",467],
    [41,"فصلت",477],[42,"الشورى",483],[43,"الزخرف",489],[44,"الدخان",496],[45,"الجاثية",499],
    [46,"الأحقاف",502],[47,"محمد",507],[48,"الفتح",511],[49,"الحجرات",515],[50,"ق",518],
    [51,"الذاريات",520],[52,"الطور",523],[53,"النجم",526],[54,"القمر",528],[55,"الرحمن",531],
    [56,"الواقعة",534],[57,"الحديد",537],[58,"المجادلة",542],[59,"الحشر",545],[60,"الممتحنة",549],
    [61,"الصف",551],[62,"الجمعة",553],[63,"المنافقون",554],[64,"التغابن",556],[65,"الطلاق",558],
    [66,"التحريم",560],[67,"الملك",562],[68,"القلم",564],[69,"الحاقة",566],[70,"المعارج",568],
    [71,"نوح",570],[72,"الجن",572],[73,"المزمل",574],[74,"المدثر",575],[75,"القيامة",577],
    [76,"الانسان",578],[77,"المرسلات",580],[78,"النبإ",582],[79,"النازعات",583],[80,"عبس",585],
    [81,"التكوير",586],[82,"الإنفطار",587],[83,"المطففين",587],[84,"الإنشقاق",589],[85,"البروج",590],
    [86,"الطارق",591],[87,"الأعلى",591],[88,"الغاشية",592],[89,"الفجر",593],[90,"البلد",594],
    [91,"الشمس",595],[92,"الليل",595],[93,"الضحى",596],[94,"الشرح",596],[95,"التين",597],
    [96,"العلق",597],[97,"القدر",598],[98,"البينة",598],[99,"الزلزلة",599],[100,"العاديات",599],
    [101,"القارعة",600],[102,"التكاثر",600],[103,"العصر",601],[104,"الهمزة",601],[105,"الفيل",601],
    [106,"قريش",602],[107,"الماعون",602],[108,"الكوثر",602],[109,"الكافرون",603],[110,"النصر",603],
    [111,"المسد",603],[112,"الإخلاص",604],[113,"الفلق",604],[114,"الناس",604]
  ];

  var surahOverlay = document.getElementById('surah-overlay');
  var surahListEl = document.getElementById('surah-list');

  function renderSurahList() {
    var html = '';
    SURAH_INDEX.forEach(function (row) {
      var cur = currentSurahNums.indexOf(row[0]) !== -1;
      html += '<div class="surah-row' + (cur ? ' current' : '') + '" data-page="' + row[2] +
              '" data-num="' + row[0] + '">' +
              '<span class="s-num">' + row[0] + '</span>' +
              '<span class="s-ar">' + row[1] + '</span>' +
              '<span class="s-page">' + T('page_n', { N: row[2] }) + '</span>' +
              '</div>';
    });
    surahListEl.innerHTML = html;
  }

  function openSurahList() {
    renderSurahList();
    surahOverlay.classList.add('visible');
    // Прокрутка к текущей суре - студент открывает список там, где читает,
    // а не с Аль-Фатихи (иначе с 60-й суры пришлось бы листать вручную).
    var cur = surahListEl.querySelector('.surah-row.current');
    if (cur) cur.scrollIntoView({ block: 'center' });
  }
  function closeSurahList() { surahOverlay.classList.remove('visible'); }

  document.getElementById('btn-surah-pick').addEventListener('click', openSurahList);
  document.getElementById('surah-close').addEventListener('click', closeSurahList);
  // Тап по затемнению - тоже закрытие (привычный жест листа снизу).
  surahOverlay.addEventListener('click', function (e) {
    if (e.target === surahOverlay) closeSurahList();
  });
  surahListEl.addEventListener('click', function (e) {
    var row = e.target.closest ? e.target.closest('.surah-row') : null;
    if (!row) return;
    closeSurahList();
    // Со "Смысла"/"Моих слов" переход по суре возвращает на саму страницу
    // мусхафа - выбор суры это про чтение, а не про текущую вкладку.
    switchTab('page');
    loadPage(parseInt(row.getAttribute('data-page'), 10));
  });

  // Закладка страницы чтения (30.08.2026) - 🔖 сохраняет ТЕКУЩУЮ страницу
  // на сервере (по Telegram ID, core/mushaf_words.py), "«" переносит на
  // сохранённую. Не то же самое, что закладка тренажёра (mufradat_page) -
  // отдельная точка возврата, которую студент выставляет сам.
  /* С 22.09.2026 все три действия - в меню 🔖 (#bm-menu). Пункты - те же
     кнопки с теми же id, что стояли в полосе, поэтому и снимки онбординга,
     и стенды жмут их как раньше. Подсказки «сохранено / закладки нет»
     встают у 🔖: пункт меню к этому моменту уже скрыт. */
  var bmBtn = document.getElementById('btn-bookmark');
  var bmMenu = document.getElementById('bm-menu');
  // Откуда открыли меню - у той кнопки и всплывают подсказки (11.11.2026:
  // в шапке с панелью это номер страницы #tb-page, в строке страниц - 🔖).
  var bmAnchor = bmBtn;
  function bmClose() { bmMenu.classList.remove('on'); }
  function bmOpen(e, anchor) {
    e.stopPropagation();
    if (bmMenu.classList.contains('on')) { bmClose(); return; }
    bmAnchor = anchor;
    bmMenu.classList.add('on');
    // Под кнопкой, а если снизу не хватает места (полоса теперь внизу
    // экрана, а лёжа - в конце листа) - над ней. Прижато к экрану.
    var r = anchor.getBoundingClientRect(), m = bmMenu.getBoundingClientRect();
    var top = r.bottom + 6;
    if (top + m.height > window.innerHeight - 8) top = r.top - m.height - 6;
    bmMenu.style.top = Math.max(8, top) + 'px';
    bmMenu.style.left = Math.max(8, Math.min(r.left, window.innerWidth - m.width - 8)) + 'px';
    // Номер страницы закладки прямо в пункте: видно, куда уведёт.
    apiCall('/bookmark').then(function (res) {
      if (res.status !== 401 && res.data && res.data.page) {
        document.getElementById('bm-go-sub').textContent = T('page_n', { N: res.data.page });
      }
    });
  }
  bmBtn.addEventListener('click', function (e) { bmOpen(e, bmBtn); });
  document.getElementById('tb-page').addEventListener('click', function (e) { bmOpen(e, document.getElementById('tb-page')); });
  document.getElementById('tb-next').addEventListener('click', function () { document.getElementById('btn-next').click(); });
  document.getElementById('tb-prev').addEventListener('click', function () { document.getElementById('btn-prev').click(); });
  document.getElementById('btn-bm-baqara').addEventListener('click', function () { loadPage(BAQARA_START_PAGE); });
  var bmJumpInput = document.getElementById('bm-jump-input');
  function bmJumpGo() {
    var n = parseInt(bmJumpInput.value, 10);
    if (n >= FIRST_PAGE && n <= LAST_PAGE) { loadPage(n); bmClose(); }
  }
  document.getElementById('bm-jump-go').addEventListener('click', bmJumpGo);
  bmJumpInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') bmJumpGo(); });
  bmJumpInput.addEventListener('click', function (e) { e.stopPropagation(); });
  // Поле ввода внутри меню: тап по нему меню не закрывает, по пунктам - закрывает.
  bmMenu.addEventListener('click', function (e) { if (e.target.closest('button') && !e.target.closest('#bm-jump')) bmClose(); });
  document.addEventListener('click', function (e) {
    if (bmMenu.classList.contains('on') && !bmMenu.contains(e.target)) bmClose();
  });
  document.getElementById('page-wrap').addEventListener('scroll', bmClose, { passive: true });
  document.getElementById('btn-bookmark-save').addEventListener('click', function () {
    apiCall('/bookmark', { method: 'POST', body: { page: currentPage } }).then(function (res) {
      if (res.status !== 401) showPopupMessage(bmAnchor, T('bookmark_saved', { N: currentPage }));
    });
  });
  document.getElementById('btn-bookmark-go').addEventListener('click', function () {
    var btn = bmAnchor;
    apiCall('/bookmark').then(function (res) {
      if (res.status === 401) return;
      if (res.data && res.data.page) {
        loadPage(res.data.page);
      } else {
        showPopupMessage(btn, T('bookmark_none'));
      }
    });
  });

  // Отметка "повторение" (30.08.2026) - решение пользователя: подтверждение
  // ПЕРЕД зачётом (студент мог случайно задеть кнопку), засчитывает
  // дневное задание "r" и шлёт сообщение в группу (core/mufradat_bot.py:
  // credit_revision_task) только после явного "Да".
  document.getElementById('btn-revision').addEventListener('click', function (e) {
    var btn = e.currentTarget;
    // Несовершеннолетним (16.09.2026) - не вопрос, а панель записи: читает
    // повторение под запись, запись уходит устазу, зачёт ставит сервер.
    if (meRevisionRecord) { revisionRecOpen(); return; }
    showConfirm(T(meHafiz ? 'revision_ask_hafiz' : 'revision_ask'), function () {
      apiCall('/revision', { method: 'POST' }).then(function (res) {
        if (res.status === 401) return;
        if (res.data && res.data.error === 'record_required') { meRevisionRecord = true; revisionRecOpen(); return; }
        showPopupMessage(btn, res.data && res.data.credited ?
          T('revision_done') : T('revision_already'));
        mushafDoneMarks('r');   // засчитано (сейчас или раньше) - кнопка зелёная
      });
    });
  });

  // Свайп по странице (28.08.2026, направление развёрнуто 30.08.2026 по
  // просьбе пользователя - "интуитивно понятнее наоборот"): палец влево
  // (dx < 0) - назад по мусхафу (currentPage - 1), палец вправо - вперёд
  // (currentPage + 1). #page-wrap уже скроллится вертикально
  // (плотные страницы, 15-16 строк) - жест засчитывается только когда
  // горизонтальная составляющая явно больше вертикальной, иначе обычный
  // вертикальный скролл принимался бы за свайп. justSwiped - клик на
  // ayah-text (попап перевода слова, см. выше) на тачскрине приходит ПОСЛЕ
  // touchend от того же жеста - без флага смахивание страницы попутно
  // открывало бы всплывающую подсказку слова, на котором палец оторвался.
  var pageWrap = document.getElementById('page-wrap');
  var touchStartX = 0, touchStartY = 0, justSwiped = false;
  pageWrap.addEventListener('touchstart', function (e) {
    var t = e.touches[0];
    touchStartX = t.clientX;
    touchStartY = t.clientY;
  }, { passive: true });
  pageWrap.addEventListener('touchend', function (e) {
    var t = e.changedTouches[0];
    var dx = t.clientX - touchStartX;
    var dy = t.clientY - touchStartY;
    /* Проверка и пересдача привязаны к одной странице (07.09.2026).
       У устаза это прямая порча данных: пометка адресуется парой
       (строка, слово) без номера страницы, и на соседней она ляжет на
       ДРУГИЕ слова - а вердикт уйдёт с этими координатами. У студента
       пересдаётся ровно то место, что сдавал, уходить с него некуда. */
    if (pageTurnBlocked()) return;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      justSwiped = true;
      loadPage(dx < 0 ? currentPage - 1 : currentPage + 1);
    }
  }, { passive: true });

  /* Колесо мыши и клавиши листают страницы (10.09.2026, поймал пользователь:
     «зашёл через браузер, мусхаф не скролится»).

     Страница мусхафа всегда помещается в экран целиком - clampFontToFit
     подгоняет шрифт под него, - поэтому прокручивать там нечего, и это
     задумано. Но на компьютере нет свайпа, и человек упирался в тупик:
     колесо крутится, ничего не происходит, а кнопки ‹ › он мог и не
     заметить. Теперь колесо вниз - дальше по номерам, вверх - назад, как в
     любой книге на экране.

     Порог и пауза нужны из-за трекпада: один мах даёт десятки событий, и без
     них пролистывало бы сразу пачку страниц. */
  var wheelAcc = 0, wheelTurned = 0, wheelLast = 0;
  var WHEEL_STEP = 110, WHEEL_PAUSE = 420, WHEEL_IDLE = 350;

  function pageTurnBlocked() {
    // Проверка и пересдача привязаны к одной странице, уходить с неё нельзя.
    //
    // Заучивание — тоже (13.09.2026). Свайп уводил лист, а место НЕ уезжало:
    // hifzApply подсвечивал ту же строку уже на новой странице, шапка писала
    // новый номер, и сдача уходила с чужой страницей — она берёт currentPage
    // (см. hifzRecSend). Выглядело всё при этом совершенно нормально.
    // В режиме выбора места (hifz.picking) листать, наоборот, НУЖНО.
    return (typeof review !== 'undefined' && review.on) || hifzRetakeMode
      || (hifz.on && !hifz.picking);
  }

  pageWrap.addEventListener('wheel', function (e) {
    if (pageTurnBlocked()) return;
    // Если страница всё же выше экрана (узкое окно, крупный шрифт) - сперва
    // обычная прокрутка, листаем только на краю.
    if (pageWrap.scrollHeight > pageWrap.clientHeight + 1) {
      var atTop = pageWrap.scrollTop <= 0;
      var atBottom = pageWrap.scrollTop + pageWrap.clientHeight >= pageWrap.scrollHeight - 1;
      if (!(e.deltaY > 0 ? atBottom : atTop)) return;
    }
    var now = Date.now();
    if (now - wheelLast > WHEEL_IDLE) wheelAcc = 0;   // новый мах, а не тот же
    wheelLast = now;
    if (now - wheelTurned < WHEEL_PAUSE) return;      // страница только что перевернулась
    wheelAcc += e.deltaY;
    if (Math.abs(wheelAcc) < WHEEL_STEP) return;
    wheelTurned = now;
    var dir = wheelAcc > 0 ? 1 : -1;
    wheelAcc = 0;
    loadPage(currentPage + dir);
  }, { passive: true });

  // Клавиши - вторая половина того же: на компьютере ими листают привычнее,
  // чем мышью. Вертикальные, а не ← →: страница арабская, и в RTL «вправо»
  // читается неоднозначно, а «вниз» значит одно и то же везде.
  document.addEventListener('keydown', function (e) {
    if (document.getElementById('app').style.display === 'none') return;
    if (pageTurnBlocked()) return;
    var t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    var dir = (e.key === 'ArrowDown' || e.key === 'PageDown') ? 1
            : (e.key === 'ArrowUp' || e.key === 'PageUp') ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    loadPage(currentPage + dir);
  });

  // Тап по номеру страницы - прямой переход (220 страниц, недостаточно
  // одних ◀▶ - решение пользователя 27.08.2026, после расширения с 9 до
  // всего диапазона сур 2-10).
  var pageIndicator = document.getElementById('page-indicator');
  var pageJumpInput = document.getElementById('page-jump-input');
  pageIndicator.addEventListener('click', function () {
    pageJumpInput.value = currentPage;
    pageIndicator.style.display = 'none';
    pageJumpInput.style.display = 'inline-block';
    pageJumpInput.focus();
    pageJumpInput.select();
  });
  function commitJump() {
    var n = parseInt(pageJumpInput.value, 10);
    pageJumpInput.style.display = 'none';
    pageIndicator.style.display = 'inline-block';
    if (n >= FIRST_PAGE && n <= LAST_PAGE) loadPage(n);
  }
  pageJumpInput.addEventListener('blur', commitJump);
  pageJumpInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') pageJumpInput.blur();
  });

  /* Чтение лёжа (21.09.2026). Стоя строка страниц (« ‹ стр. N › 🔖) висит
     над текстом, лёжа по высоте каждая строка на счету - она уезжает в конец
     листа: дочитал и тут же листаешь или ставишь закладку. Узел переносится
     целиком, обработчики остаются с ним. */
  var mushafWasLand = null;
  var mushafWasHifzLand = false;
  // Метка родного места строки страниц: между ней и листом стоит шапка
  // заучивания, «перед листом» - уже не то место (поймано сравнением снимков).
  var pageNavHome = document.createComment('page-nav');
  document.getElementById('page-nav').parentNode.insertBefore(
    pageNavHome, document.getElementById('page-nav'));
  var mushafScrollShare = 0;   // где в листе был читающий, долей высоты
  // Прокрутку, которую сделал не человек, а перестройка экрана, в «место
  // чтения» не берём: WebKit шлёт её ДО события resize, при уже новом
  // размере (поймано сравнением: 0.50 -> 0.33 на WebKit, в Chrome нет), и
  // после поворота - пока идут перемеры кегля.
  var mushafViewSize = window.innerWidth + 'x' + window.innerHeight;
  var mushafRestoreUntil = 0;
  pageWrap.addEventListener('scroll', function () {
    if (window.innerWidth + 'x' + window.innerHeight !== mushafViewSize) return;
    if (Date.now() < mushafRestoreUntil) return;
    var span = pageWrap.scrollHeight - pageWrap.clientHeight;
    mushafScrollShare = span > 0 ? pageWrap.scrollTop / span : 0;
  }, { passive: true });

  /* Лёжа - только текст (22.09.2026, решение пользователя). Повернул
     телефон - шапка видна несколько секунд и уезжает; касание по пустому
     месту листа (между строками, поля) - вернуть её, ещё касание - убрать.
     Двойное касание не годится: одно касание по слову уже открывает
     перевод, двойное - добавляет в «Мои слова». Поэтому слова, строка
     страниц и кнопки здесь не считаются. Выход из режима - повернуть
     телефон обратно, отдельного жеста нет. */
  var LAND_CHROME_MS = 3500;
  var landChromeTimer = null;
  function landChromeShow() {
    var app = document.getElementById('app');
    app.classList.remove('bare');
    clearTimeout(landChromeTimer);
    landChromeTimer = setTimeout(function () {
      if (app.classList.contains('land') && !app.classList.contains('hifz-pick')) app.classList.add('bare');
    }, LAND_CHROME_MS);
  }
  function landChromeHide() {
    clearTimeout(landChromeTimer);
    document.getElementById('app').classList.add('bare');
  }
  function landChromeReset() {
    clearTimeout(landChromeTimer);
    document.getElementById('app').classList.remove('bare');
  }
  // Касание, после которого палец ехал (прокрутка, свайп страницы), - не
  // касание: иначе каждое перелистывание дёргало бы шапку.
  var landTouchX = 0, landTouchY = 0, landTouchMovedAt = 0;
  pageWrap.addEventListener('touchstart', function (e) {
    landTouchX = e.touches[0].clientX; landTouchY = e.touches[0].clientY;
  }, { passive: true });
  pageWrap.addEventListener('touchmove', function (e) {
    var t = e.touches[0];
    if (Math.abs(t.clientX - landTouchX) + Math.abs(t.clientY - landTouchY) > 10) landTouchMovedAt = Date.now();
  }, { passive: true });
  pageWrap.addEventListener('click', function (e) {
    var app = document.getElementById('app');
    if (!app.classList.contains('land')) return;
    if (Date.now() - landTouchMovedAt < 600) return;
    // Выбор места: касание по строке - ответ на вопрос, а не шапка.
    if (app.classList.contains('hifz-pick')) return;
    if (e.target.closest('[data-tr], #page-nav, button, a, input')) return;
    if (app.classList.contains('bare')) landChromeShow(); else landChromeHide();
  });
  // Пока человек что-то нажимает в шапке, она не уезжает из-под пальца.
  ['topbar', 'hifz-head'].forEach(function (id) {
    document.getElementById(id).addEventListener('click', function () {
      if (document.getElementById('app').classList.contains('land')) landChromeShow();
    });
  });

  /* Подсказка про поворот вместо кнопки «Крупно» (22.09.2026, решение
     пользователя). Показываем при входе в заучивание стоя до 5 раз и
     перестаём, как только человек дважды заучивал лёжа - значит, знает.
     Счёт в браузере: это удобство одного телефона, а не данные. */
  var ROTATE_HINT_KEY = 'yassir_rotate_hint';
  var ROTATE_HINT_MAX = 5, ROTATE_HINT_LEARNED = 2;
  function rotateHintState() {
    try { return JSON.parse(localStorage.getItem(ROTATE_HINT_KEY) || 'null') || { shown: 0, land: 0 }; }
    catch (e) { return { shown: 0, land: 0 }; }
  }
  function rotateHintSave(st) {
    try { localStorage.setItem(ROTATE_HINT_KEY, JSON.stringify(st)); } catch (e) {}
  }
  function rotateHintLearned() {
    var st = rotateHintState();
    st.land = (st.land || 0) + 1;
    rotateHintSave(st);
  }
  function rotateHintMaybe() {
    // Только телефон стоя: на компьютере и планшете лёжа ничего не даёт.
    if (!window.matchMedia || !window.matchMedia('(orientation: portrait) and (max-width: 500px)').matches) return;
    var st = rotateHintState();
    if (st.shown >= ROTATE_HINT_MAX || st.land >= ROTATE_HINT_LEARNED) return;
    st.shown++;
    rotateHintSave(st);
    hifzNote(T('hifz_rotate_hint'), 5000, T('hifz_rotate_hint_lock'));
  }

  /* Полный экран Telegram лёжа (22.09.2026): убирает и шапку самого
     Telegram - по высоте лёжа это ещё почти строка. Только в Telegram 8.0+
     (на сайте и в старом Telegram - как было). Снимаем только то, что
     включили сами: человек мог держать полный экран и без нас. */
  var tgFull = window.Telegram && window.Telegram.WebApp;
  var tgFullOk = !!(tgFull && tgFull.initData && tgFull.isVersionAtLeast &&
                    tgFull.isVersionAtLeast('8.0') && tgFull.requestFullscreen);
  if (tgFullOk) {
    tgFull.onEvent('fullscreenChanged', function () {
      // Вышел сам кнопкой Telegram - больше не наш, не возвращаем силой.
      if (!tgFull.isFullscreen) mushafTgFullOurs = false;
    });
    tgFull.onEvent('fullscreenFailed', function () { mushafTgFullOurs = false; });
  }
  function landFullscreen(on) {
    if (!tgFullOk) return;
    try {
      if (on && !tgFull.isFullscreen) {
        mushafTgFullOurs = true;
        tgFull.requestFullscreen();
      } else if (!on && mushafTgFullOurs) {
        mushafTgFullOurs = false;
        if (tgFull.isFullscreen) tgFull.exitFullscreen();
      }
    } catch (e) {}
  }

  // Режим лёжа - только на листе чтения и вне заучивания (21.09.2026):
  // «Смысл» листается той же строкой страниц, и уносить её в лист нельзя, а
  // заучивание лёжа - отдельный следующий шаг. Вкладки и вход в заучивание
  // меняют классы - за ними следит наблюдатель ниже, их код не тронут.
  function mushafOrientationApply() {
    var app = document.getElementById('app');
    var view = document.getElementById('view-page');
    // Мусхаф закрыт (вернулись на дашборд) - тоже не «лёжа»: иначе полный
    // экран Telegram остался бы на дашборде под его кнопками.
    // Заучивание лёжа с 22.09.2026 тоже «лёжа» (там оно и есть «Крупно»).
    // Проверка сдачи устазом и разбор у студента - как было, стоя-вёрстка:
    // там низ занят вердиктом и плеером, колонке счётчика места нет.
    var land = mushafLandscape() && view.classList.contains('active') &&
               !app.classList.contains('review') && !app.classList.contains('look') &&
               app.style.display !== 'none';
    var nav = document.getElementById('page-nav');
    if (land && nav.parentNode !== pageWrap) pageWrap.appendChild(nav);
    if (!land && nav.parentNode === pageWrap) pageNavHome.parentNode.insertBefore(nav, pageNavHome.nextSibling);
    app.classList.toggle('land', land);
    // Выбор места - вопрос человеку, шапка с ним не уезжает.
    if (land && app.classList.contains('hifz-pick') && app.classList.contains('bare')) landChromeShow();
    // Вход в заучивание лёжа и выход из него - тоже смена режима: колонка
    // счётчика отнимает ширину, кегль надо перемерить (иначе строка вылезала
    // на 55-70px - поймано снимком).
    var hifzLand = land && app.classList.contains('hifz');
    var hifzLandChanged = hifzLand !== mushafWasHifzLand;
    if (hifzLand && !mushafWasHifzLand) rotateHintLearned();
    mushafWasHifzLand = hifzLand;
    if (land === mushafWasLand) {
      if (hifzLandChanged) mushafFitTrusted = null;
      return hifzLandChanged;
    }
    mushafWasLand = land;
    if (land) landChromeShow(); else landChromeReset();
    landFullscreen(land);
    // Доверенный кегль полного листа из другой ориентации здесь чужой.
    mushafFitTrusted = null;
    return true;
  }

  window.addEventListener('resize', function () {
    var turned = mushafOrientationApply();
    var share = mushafScrollShare;
    var resized = mushafViewSize !== window.innerWidth + 'x' + window.innerHeight;
    mushafViewSize = window.innerWidth + 'x' + window.innerHeight;
    var keys = Object.keys(cache);
    if (keys.length) mushafFitSchedule();
    if (typeof hifzRecPad === 'function') hifzRecPad();
    // После поворота (и любой смены размера лёжа) кегль и высота листа
    // другие - возвращаем читающего на ту же долю листа, а не в начало.
    // Повторно - после поздних перемеров.
    if (turned || (resized && mushafWasLand)) {
      var restores = [0].concat(MUSHAF_REFIT_DELAYS.map(function (ms) { return ms + 50; }));
      mushafRestoreUntil = Date.now() + restores[restores.length - 1] + 100;
      restores.forEach(function (ms) {
        setTimeout(function () {
          var span = pageWrap.scrollHeight - pageWrap.clientHeight;
          if (span > 0) pageWrap.scrollTop = share * span;
        }, ms);
      });
    }
  });
  mushafOrientationApply();
  if (window.MutationObserver) {
    var landWatch = new MutationObserver(function () {
      // Режим сменился не поворотом (вкладка, заучивание) - потолок кегля
      // другой, лист надо перемерить.
      // Закрытый мусхаф не меряем: скрытый лист дал бы ложный кегль, при
      // открытии режим сменится ещё раз и перемер будет уже на виду.
      if (mushafOrientationApply() && Object.keys(cache).length &&
          document.getElementById('app').style.display !== 'none') mushafFitSchedule();
    });
    // style - закрытие/открытие мусхафа (display), см. mushafOrientationApply.
    landWatch.observe(document.getElementById('app'), { attributes: true, attributeFilter: ['class', 'style'] });
    landWatch.observe(document.getElementById('view-page'), { attributes: true, attributeFilter: ['class'] });
  }

  var startPage = FIRST_PAGE;
  try {
    var saved = parseInt(localStorage.getItem('yassir_mushaf_page'), 10);
    if (saved >= FIRST_PAGE && saved <= LAST_PAGE) startPage = saved;
  } catch (e) {}
  loadPage(startPage);
  // «rec aac» - телефон умеет писать сдачу сразу в AAC/mp4, который играют
  // все телефоны без перекодировки (12.10.2026, разведка: стоит ли уходить
  // с opus на Android). chNNN - версия Chrome, от неё это и зависит.
  var recCaps = '';
  try {
    var mrT = window.MediaRecorder && MediaRecorder.isTypeSupported;
    recCaps = ' rec ' + (!mrT ? '-' : MediaRecorder.isTypeSupported('audio/mp4;codecs=mp4a.40.2') ? 'aac'
      : MediaRecorder.isTypeSupported('audio/mp4') ? 'mp4' : 'opus');
    var chV = /Chrome\/(\d+)/.exec(navigator.userAgent);
    if (chV) recCaps += ' ch' + chV[1];
  } catch (e) {}
  trail('open', { p: startPage,
                  n: ((tg && tg.initData) ? 'tg' : 'web') + ' ' + window.innerWidth + 'x' + window.innerHeight + recCaps });

