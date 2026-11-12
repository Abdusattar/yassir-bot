  // "Мои слова" - список (29.08.2026, см. модульный комментарий у
  // #view-mywords). Свой делегированный обработчик двойного тапа/клика -
  // тот же таймер-паттерн, что у слова на странице чтения выше, но здесь
  // одиночный клик НИЧЕГО не делает (простой список для чтения, решение
  // пользователя - строка не открывает тренажёр), только двойной убирает
  // слово из списка.
  var mywordsTapTimer = null, mywordsTapTarget = null;
  function myWordsRowHtml(w) {
    return '<div class="word-row mywords-row" data-surah="' + w.surah + '" data-ayah="' + w.ayah +
      '" data-pos="' + w.position + '"><span class="arabic">' + w.arabic +
      '</span><span class="translation">' + w.translation + '</span></div>';
  }
  function renderMyWords(words) {
    var html;
    if (!words.length) {
      html = '<div class="trainer-msg">' + T('mywords_empty') + '</div>';
    } else {
      // Секции показываем, только если есть хоть одно "Новое" (is_new) -
      // иначе список выглядит как раньше, без лишнего заголовка "Забытые"
      // над всем и так привычным списком (03.09.2026).
      var newWords = words.filter(function (w) { return w.is_new; });
      var oldWords = words.filter(function (w) { return !w.is_new; });
      if (newWords.length) {
        html = '<div class="mywords-section-title">' + T('mywords_new') + '</div>' +
          newWords.map(myWordsRowHtml).join('') +
          '<div class="mywords-section-title">' + T('mywords_old') + '</div>' +
          oldWords.map(myWordsRowHtml).join('');
      } else {
        html = words.map(myWordsRowHtml).join('');
      }
    }
    document.getElementById('mywords-list').innerHTML = html;
  }
  function loadMyWords() {
    document.getElementById('mywords-list').innerHTML = '<div class="trainer-msg">' + T('loading') + '</div>';
    apiCall('/words').then(function (res) {
      if (res.status === 401) {
        document.getElementById('mywords-list').innerHTML =
          '<div class="trainer-msg">' + T('session_expired') + '</div>';
        return;
      }
      renderMyWords(res.data.words);
    });
  }
  function removeFromMyWords(row) {
    apiCall('/words/remove', { method: 'POST', body: {
      surah: parseInt(row.getAttribute('data-surah'), 10),
      ayah: parseInt(row.getAttribute('data-ayah'), 10),
      position: parseInt(row.getAttribute('data-pos'), 10),
    } }).then(function (res) {
      if (res.status !== 401) renderMyWords(res.data.words);
    });
  }
  document.getElementById('mywords-list').addEventListener('click', function (e) {
    var row = e.target.closest('.mywords-row');
    if (!row) return;
    if (mywordsTapTimer && mywordsTapTarget === row) {
      clearTimeout(mywordsTapTimer);
      mywordsTapTimer = null; mywordsTapTarget = null;
      removeFromMyWords(row);
      return;
    }
    mywordsTapTarget = row;
    mywordsTapTimer = setTimeout(function () {
      mywordsTapTimer = null; mywordsTapTarget = null;
    }, DOUBLE_TAP_WINDOW_MS);
  });

