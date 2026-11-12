  // "Мои слова" (29.08.2026) - двойной тап/клик по слову на странице
  // чтения добавляет его в личный список (см. #tab-mywords ниже), не
  // открывает подсказку перевода.
  // До 12.11.2026 одиночный тап ЖДАЛ это окно (не придёт ли второй) и только
  // потом показывал перевод: 300 мс ожидания + 250 мс проявления = полсекунды
  // от нажатия до подсказки (замер; жалоба пользователя: «в других
  // приложениях гораздо быстрее»). Теперь перевод показывается сразу, а
  // второй тап по ТОМУ ЖЕ слову в пределах окна заменяет подсказку на
  // «добавлено в Мои слова». В проверке устаза двойного тапа нет: там каждый
  // тап ставит или снимает пометку ошибки.
  var DOUBLE_TAP_WINDOW_MS = 300;
  var wordTapTimer = null, wordTapTarget = null;
  function addToMyWords(el) {
    // Хвост пары - в «Мои слова» идёт её голова (своего перевода у хвоста
    // нет, запись по нему тренажёр не показал бы никогда).
    var headKey = el.getAttribute('data-head');
    if (headKey) {
      var headEl = document.querySelector('#ayah-text [data-w="' + headKey + '"]');
      if (!headEl) return;
      var shownOn = el;
      el = headEl;
      var surahH = el.getAttribute('data-surah');
      apiCall('/words/add', { method: 'POST', body: {
        surah: parseInt(surahH, 10),
        ayah: parseInt(el.getAttribute('data-ayah'), 10),
        position: parseInt(el.getAttribute('data-pos'), 10),
        arabic: el.getAttribute('data-arabic') || '',
        translation: el.getAttribute('data-tr') || '',
      } }).then(function (res) {
        if (res.status !== 401) showPopupMessage(shownOn, T('added_mywords'));
      });
      return;
    }
    var surah = el.getAttribute('data-surah');
    if (!surah) return;
    apiCall('/words/add', { method: 'POST', body: {
      surah: parseInt(surah, 10),
      ayah: parseInt(el.getAttribute('data-ayah'), 10),
      position: parseInt(el.getAttribute('data-pos'), 10),
      arabic: el.getAttribute('data-arabic') || '',
      translation: el.getAttribute('data-tr') || '',
    } }).then(function (res) {
      if (res.status !== 401) showPopupMessage(el, T('added_mywords'));
    });
  }
  document.getElementById('ayah-text').addEventListener('click', function (e) {
    if (justSwiped) { justSwiped = false; return; }
    var el = e.target.closest('[data-tr]');
    if (!el) return;
    if (wordTapTimer && wordTapTarget === el && !review.on) {
      clearTimeout(wordTapTimer);
      wordTapTimer = null; wordTapTarget = null;
      addToMyWords(el);
      return;
    }
    clearTimeout(wordTapTimer);
    wordTapTarget = el;
    showWordPopup(el);
    // Таймер теперь только закрывает окно двойного тапа.
    wordTapTimer = setTimeout(function () {
      wordTapTimer = null; wordTapTarget = null;
    }, DOUBLE_TAP_WINDOW_MS);
  });

