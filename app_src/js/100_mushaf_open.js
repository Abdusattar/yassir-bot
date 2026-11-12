  // Дашборд YassirApp (28.08.2026/29.08.2026) - первый экран. "Мусхаф" и
  // "Тренажёр" оба теперь переключают вид ВНУТРИ этого же приложения (до
  // 29.08.2026 Тренажёр уводил обратно в чат с ботом deep-link'ом - решение
  // пользователя "ты странный мы же ее ложим вместе с мусхафом в один
  // апп" - движок тренажёра (core/mufradat.py) был уже транспорт-независим,
  // core/mufradat_api.py просто открывает его по HTTP, core/mufradat_bot.py
  // (чат-версия) не тронут, оба используют один и тот же движок/БД).
  // openMushaf(tab) - общая точка входа в #app, вызывается и с дашборда
  // (tab='page'), и напрямую из Тренажёра (30.08.2026, решение пользователя
  // "удобный переход без дашборда") - оттуда может понадобиться сразу
  // открыть "Мои слова", а не только "Страницу". Прячет #trainer тоже
  // (не только #dashboard) - иначе повторный вызов из Тренажёра оставлял
  // бы его видимым под #app.
  function openMushaf(tab, mywordsFrom) {
    if (typeof mushafDoneMarks === 'function') mushafDoneMarks();
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('trainer').style.display = 'none';
    document.getElementById('app').style.display = 'flex';
    // mywordsFrom - куда должна вести "стрелка назад" на "Мои словах"
    // (см. mywordsOrigin у switchTab) - только когда открываем именно
    // "Мои слова" этим вызовом (из Тренажёра, 30.08.2026).
    if (tab === 'mywords') mywordsOrigin = mywordsFrom || 'page';
    switchTab(tab || 'page');
    // clampFontToFit() при самом рендере страницы (reveal(), см. выше)
    // считает по нулевой ширине - #app в этот момент ещё display:none
    // (дашборд - первый экран, см. комментарий выше), контейнер без
    // ширины, подгонка молча не срабатывает. Пересчёт здесь - сразу как
    // #app стал видимым (28.08.2026, тот самый баг с обрезкой текста на
    // телефоне: у уже открывавших мусхаф раньше страница подгружается
    // ИЗ localStorage ещё до клика по карточке).
    mushafFitSchedule();
  }
  // Дашборд YassirApp (28.08.2026/29.08.2026) - первый экран. "Мусхаф" и
  // "Тренажёр" оба теперь переключают вид ВНУТРИ этого же приложения (до
  // 29.08.2026 Тренажёр уводил обратно в чат с ботом deep-link'ом - решение
  // пользователя "ты странный мы же ее ложим вместе с мусхафом в один
  // апп" - движок тренажёра (core/mufradat.py) был уже транспорт-независим,
  // core/mufradat_api.py просто открывает его по HTTP, core/mufradat_bot.py
  // (чат-версия) не тронут, оба используют один и тот же движок/БД).
  // Вход с дашборда - всегда вкладка "Страница" (30.08.2026, решение
  // пользователя), даже если в прошлый раз ушли со "Смысла"/"Мои слова".
  document.getElementById('dash-mushaf').addEventListener('click', function () { openMushaf('page'); });
  document.getElementById('dash-trainer').addEventListener('click', function () { openTrainers(); });
  // Не голый openSubs (05.11.2026, Толкун): клик передал бы событие в
  // fromWall - и «Сначала пересдай, потом дальше» висело у всех без долгов.
  document.getElementById('dash-subs').addEventListener('click', function () { openSubs(); });
  document.getElementById('subs-back').addEventListener('click', function () {
    subsStopAudio();
    document.getElementById('subs').style.display = 'none';
    document.getElementById('dashboard').style.display = 'flex';
    if (typeof pulseIntroStart === 'function') pulseIntroStart();
  });
  // Через обёртку, не напрямую: слушатель передал бы объект события
  // первым аргументом, и openUstaz принял бы его за withAll.
  document.getElementById('dash-ustaz').addEventListener('click', function () { ustazEnter(); });
  document.getElementById('ustaz-back').addEventListener('click', function () {
    document.getElementById('ustaz').style.display = 'none';
    document.getElementById('dashboard').style.display = 'flex';
    if (typeof pulseIntroStart === 'function') pulseIntroStart();
  });
  document.getElementById('trainer-tab-mywords').addEventListener('click', function () { openMushaf('mywords', 'trainer'); });
  document.getElementById('trainer-tab-mushaf').addEventListener('click', function () { openMushaf('page'); });
  // role="button" на <div> не даёт Enter/Space нативно, в отличие от <button> -
  // нужен явный keydown (30.08.2026, клавиатурная навигация Telegram Desktop).
  Array.prototype.forEach.call(document.querySelectorAll('.dash-card, .dash-row'), function (card) {
    card.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); card.click(); }
    });
  });
  document.getElementById('mushaf-back').addEventListener('click', function () {
    /* Возврат по стеку (09.09.2026): с "Смысла"/"Моих слов" - на шаг
       назад (страница или тренажёр, откуда пришли), и только со самой
       Страницы - из мусхафа на дашборд. Подпись ставит switchTab. */
    if (!document.getElementById('view-page').classList.contains('active')) {
      var onMywords = document.getElementById('view-mywords').classList.contains('active');
      if (onMywords && mywordsOrigin === 'trainer') openTrainer();
      else switchTab('page');
      return;
    }
    document.getElementById('app').style.display = 'none';
    document.getElementById('dashboard').style.display = 'flex';
    if (typeof pulseIntroStart === 'function') pulseIntroStart();
  });

  function escapeAttr(s) {
    return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  }

  var FIRST_PAGE = 1, LAST_PAGE = 604;
  var cache = {};

