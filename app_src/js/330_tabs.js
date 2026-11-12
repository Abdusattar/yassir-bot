  /* ─── Нижняя панель разделов (04.11.2026) ─────────────────────────────
     Перенос из прототипа «Хифз · Сегодня». Экраны приложения открываются
     каждый своей функцией и сами прячут соседей - общего переключателя нет.
     Поэтому панель не встраивается в каждую из них, а СМОТРИТ на экраны:
     tabsSync() по видимости решает, корневой ли это экран раздела, и
     показывает панель только там. Мусхаф и глубокие экраны (заучивание,
     разбор, кабинет устаза) панель прячут сами собой: там лист во всю
     высоту или внизу стоят действия. Экраны тренажёров (карточка «Слов»,
     таджвид, нахв, хадис) - с панелью (10.11.2026, решение пользователя):
     их низ скроллится вместе с телом, действий, прибитых к низу, нет. */
  var TABS_SCREENS = ['dashboard', 'app', 'trainers', 'subs', 'more', 'learn',
    'trainer', 'tajweed', 'nahw', 'hadith', 'ustaz'];
  var tabsBox = document.getElementById('tabs');

  function tabsVisible(id) {
    var el = document.getElementById(id);
    return !!el && !el.hidden && getComputedStyle(el).display !== 'none';
  }
  function tabsSettOn() { return settBox.classList.contains('on'); }

  // Мусхаф в режиме «Страница» (11.11.2026, перенос из прототипа): панель
  // есть, строка страниц переехала в шапку, кегль ограничен и по высоте -
  // лист не скроллится. Заучивание, разбор, проверка, «Смысл» - без панели.
  function mushafTabsMode() {
    var app = document.getElementById('app'), page = document.getElementById('view-page');
    return !!(page && page.classList.contains('active')) &&
      !app.classList.contains('hifz') && !app.classList.contains('look') && !app.classList.contains('review');
  }

  // Какая вкладка подсвечена, или null - панель не нужна.
  function tabsCurrent() {
    if (tabsVisible('login') || tabsVisible('wrongbot')) return null;
    // Настройки - шторка поверх любого экрана, живут во вкладке «Ещё».
    if (tabsSettOn()) return 'more';
    if (tabsVisible('dashboard')) return 'today';
    if (tabsVisible('app') && mushafTabsMode()) return 'mushaf';
    // Внутри тренажёров панель тоже есть (10.11.2026, решение пользователя):
    // карточка «Слов», таджвид, нахв и хадис - те же «Тренажёры».
    if (tabsVisible('trainers') || tabsVisible('trainer') || tabsVisible('tajweed') ||
        tabsVisible('nahw') || tabsVisible('hadith')) return 'train';
    if (tabsVisible('subs')) return 'ustaz';
    if (tabsVisible('more') || tabsVisible('learn')) return 'more';
    return null;
  }

  function tabsSync() {
    var cur = tabsCurrent();
    var wasMushaf = document.body.classList.contains('tabs-mushaf');
    document.body.classList.toggle('tabs-on', !!cur);
    document.body.classList.toggle('tabs-mushaf', cur === 'mushaf');
    // Панель появилась или ушла - высота листа другая, кегль перемеряем.
    if (wasMushaf !== (cur === 'mushaf') && typeof mushafFitSchedule === 'function') mushafFitSchedule();
    Array.prototype.forEach.call(tabsBox.querySelectorAll('.tabs-btn'), function (b) {
      var on = b.getAttribute('data-tab') === cur;
      b.classList.toggle('on', on);
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
  }

  var tabsQueued = false;
  function tabsQueue() {
    if (tabsQueued) return;
    tabsQueued = true;
    requestAnimationFrame(function () { tabsQueued = false; tabsSync(); });
  }
  var tabsObs = new MutationObserver(tabsQueue);
  TABS_SCREENS.concat(['sett', 'login', 'wrongbot', 'view-page']).forEach(function (id) {
    var el = document.getElementById(id);
    if (el) tabsObs.observe(el, { attributes: true, attributeFilter: ['style', 'class', 'hidden'] });
  });

  function tabsGo(tab) {
    var cur = tabsCurrent();
    var onLearn = tabsVisible('learn');
    var inTrainer = tabsVisible('trainer') || tabsVisible('tajweed') ||
      tabsVisible('nahw') || tabsVisible('hadith');
    // Тап по своей вкладке на её же экране - ничего. Из настроек и «Знаний»
    // «Ещё» ведёт в само «Ещё», из карточки тренажёра «Тренажёры» - в хаб.
    if (cur === tab && !tabsSettOn() && !onLearn) {
      if (tab === 'train' && inTrainer) openTrainers();
      return;
    }
    if (tab === 'today') setTimeout(dashFitLines, 50);
    // Уборка уходящего экрана - то же, что делают их кнопки возврата.
    if (tabsSettOn()) settClose();
    if (onLearn) {
      // Очищаем тело «Знаний»: иначе ролик из «Как работать» играл бы и со
      // скрытого экрана. При следующем входе openLearn рисует оглавление.
      document.getElementById('learn-body').innerHTML = '';
      document.getElementById('learn').style.display = 'none';
      learnFromMore = false;
    }
    if (cur === 'ustaz') subsStopAudio();
    ['dashboard', 'app', 'trainers', 'trainer', 'tajweed', 'nahw', 'hadith', 'subs', 'more'].forEach(function (id) {
      document.getElementById(id).style.display = 'none';
    });
    if (tab === 'today') {
      document.getElementById('dashboard').style.display = 'flex';
      if (typeof pulseIntroStart === 'function') pulseIntroStart();
    } else if (tab === 'mushaf') {
      openMushaf('page');
    } else if (tab === 'train') {
      openTrainers();
    } else if (tab === 'ustaz') {
      openSubs();
    } else if (tab === 'more') {
      document.getElementById('more').style.display = 'flex';
    }
  }

  Array.prototype.forEach.call(tabsBox.querySelectorAll('.tabs-btn'), function (b) {
    b.addEventListener('click', function () { tabsGo(b.getAttribute('data-tab')); });
  });
  document.getElementById('more-learn').addEventListener('click', function () { openLearn(true); });
  document.getElementById('more-sett').addEventListener('click', function () { settOpen(true); });
  tabsSync();
