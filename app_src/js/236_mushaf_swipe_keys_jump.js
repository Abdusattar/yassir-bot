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

