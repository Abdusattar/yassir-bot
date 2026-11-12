  // ── Жест удержания: лист и «Крупно» в заучивании ──
  // Pointer events: на тачскрине прокрутка листа сама шлёт pointercancel
  // (touch-action: pan-y), сдвиг пальца больше 10px отменяет удержание.
  // Android (Chrome, WebView Telegram) ловит долгое нажатие сам, около
  // 400 мс - раньше нашего таймера - и шлёт contextmenu, часто вместе с
  // pointercancel. Поэтому contextmenu над аятом срабатывает сразу, тем же
  // путём, что таймер, а повтор (таймер после contextmenu) ничего не делает.
  var hold = { timer: null, x: 0, y: 0, id: null, fired: false, ma: null }, swallowClick = false;
  function holdCancel() {
    if (hold.timer) { clearTimeout(hold.timer); hold.timer = null; }
  }
  function holdFire() {
    if (hold.fired || !hold.ma) return;
    holdCancel();
    hold.fired = true;
    swallowClick = true;
    // Устаревший тап-таймер перевода слова не должен сработать поверх.
    if (typeof wordTapTimer !== 'undefined' && wordTapTimer) {
      clearTimeout(wordTapTimer); wordTapTimer = null; wordTapTarget = null;
    }
    if (navigator.vibrate) { try { navigator.vibrate(8); } catch (e2) {} }
    sheetOpen(hold.ma[0], hold.ma[1]);
  }
  function holdRelease() {
    holdCancel();
    // Click после удержания приходит не всегда (iOS его иногда не шлёт) -
    // флаг не должен «съесть» следующий настоящий тап.
    if (hold.fired) setTimeout(function () { swallowClick = false; }, 450);
  }
  function holdAttach(el) {
    el.addEventListener('pointerdown', function (e) {
      holdCancel();
      hold.fired = false; hold.ma = null;
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      if (!e.isPrimary || review.on) return;
      var w = e.target.closest ? e.target.closest('[data-ma]') : null;
      if (!w) return;
      var ma = w.getAttribute('data-ma').split(':');
      hold.ma = [parseInt(ma[0], 10), parseInt(ma[1], 10)];
      hold.x = e.clientX; hold.y = e.clientY; hold.id = e.pointerId;
      hold.timer = setTimeout(holdFire, MEANING_HOLD_MS);
    });
    el.addEventListener('pointermove', function (e) {
      if (!hold.timer || e.pointerId !== hold.id) return;
      if (Math.abs(e.clientX - hold.x) > 10 || Math.abs(e.clientY - hold.y) > 10) holdCancel();
    });
    el.addEventListener('pointerup', holdRelease);
    el.addEventListener('pointercancel', holdRelease);
    el.addEventListener('pointerleave', holdCancel);
    el.addEventListener('touchstart', function (e) {
      if (e.touches.length > 1) holdCancel();     // второй палец - масштаб, не удержание
    }, { passive: true });
    el.addEventListener('contextmenu', function (e) {
      e.preventDefault();
      if (hold.timer) holdFire();                 // Android: долгое нажатие раньше таймера
    });
  }
  var ayahTextEl = document.getElementById('ayah-text');
  holdAttach(ayahTextEl);
  holdAttach(document.getElementById('hifz-big-words'));
  document.getElementById('page-wrap').addEventListener('scroll', holdCancel, { passive: true });
  // Гасим click после удержания - в фазе захвата, раньше всех обработчиков
  // (перевод слова, двойной тап, выбор строки в заучивании). На документе,
  // а не на листе: отпущенный палец бьёт кликом уже по затемнению панели,
  // и та закрывалась сразу после открытия (поймано на стенде).
  window.addEventListener('click', function (e) {
    if (!swallowClick) return;
    swallowClick = false;
    e.stopImmediatePropagation();
    e.preventDefault();
  }, true);

