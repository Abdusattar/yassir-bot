  function renderWordsList(data) {
    // "Слова" - отдельный чистый список слово+перевод для этой же
    // страницы (решение пользователя 27.08.2026, "нравится их вариант" -
    // ссылаясь на quran-stroka.vercel.app) - остаётся для вдумчивого
    // разбора аята целиком, подсказка по тапу выше - для быстрого взгляда
    // прямо на странице чтения (добавлена 28.08.2026, обе формы теперь
    // сосуществуют, не заменяют друг друга).
    var html = '';
    data.ayahs.forEach(function (a) {
      html += '<div class="words-ayah-sep">' + T('ayah_n', { N: a.ayah }) + '</div>';
      a.tokens.forEach(function (t) {
        if (t.type !== 'word') return;
        html += '<div class="word-row">' +
          '<span class="arabic">' + t.html + '</span>' +
          '<span class="translation">' + (t.translation || '') + '</span>' +
          '</div>';
      });
    });
    document.getElementById('words-list').innerHTML = html;
  }

  function renderMeaning(data) {
    // "Смысл" - целостный перевод аятов страницы (Кулиев, 28.08.2026),
    // не пословный список (тот - #word-popup на самой странице чтения).
    // meaning может отсутствовать (страница ещё не догнана скриптом
    // scripts/add_ayah_meaning.py) - тогда просто не показываем блок для
    // этого аята, не выдумываем текст.
    var html = '';
    data.ayahs.forEach(function (a) {
      if (!a.meaning) return;
      html += '<div class="meaning-row">' +
        '<span class="ayah-num">' + T('ayah_n', { N: a.ayah }) + '</span>' +
        '<div class="meaning-text">' + a.meaning + '</div>' +
        '</div>';
    });
    document.getElementById('meaning-list').innerHTML = html ||
      '<div class="meaning-row"><span class="ayah-num">' + T('meaning_missing') + '</span></div>';
  }

  // "Мои слова" достижимы и со Страницы, и из Тренажёра (см. openMushaf) -
  // "стрелка назад" на "Мои словах" должна вести туда, откуда реально
  // пришли, а не всегда на Страницу (решение пользователя 30.08.2026).
  var mywordsOrigin = 'page'; // 'page' | 'trainer'

  function switchTab(name) {
    // tab-words/#view-words больше не в UI (см. комментарий у #tabbar
    // выше), но код оставлен на будущее.
    document.getElementById('view-page').classList.toggle('active', name === 'page');
    document.getElementById('view-words').classList.toggle('active', name === 'words');
    document.getElementById('view-meaning').classList.toggle('active', name === 'meaning');
    document.getElementById('view-mywords').classList.toggle('active', name === 'mywords');

    // Контекстная нижняя панель (30.08.2026, решение пользователя) -
    // всегда показывает "куда ещё пойти", никогда кнопку на текущее
    // место:
    //   Страница - Смысл, Мои слова, Тренажёр (3, текст+иконка)
    //   Смысл - пусто (идти отсюда некуда, назад ведёт шапка)
    //   Мои слова - Тренажёр - НО если
    //     зашли ИЗ Тренажёра, "Тренажёр" не показываем вовсе (30.08.2026,
    //     поймано пользователем: обе кнопки вели бы в одно и то же место -
    //     дублирование, как и с "текущим местом" в остальных случаях).
    var onPage = name === 'page', onMeaning = name === 'meaning', onMywords = name === 'mywords';
    var mywordsFromTrainer = onMywords && mywordsOrigin === 'trainer';
    /* Возврат слева вверху подписан тем, КУДА уводит (09.09.2026): со
       Страницы - на дашборд, с сабвью - назад по стеку. "Мои слова"
       достижимы из двух мест, поэтому смотрим mywordsOrigin - тот же
       признак, по которому раньше решала кнопка 🔙 в таббаре. */
    document.getElementById('mushaf-back').textContent = onPage
      ? T('back_dashboard')
      : (mywordsFromTrainer ? T('back_trainer') : T('back_mushaf'));

    // "Мои слова" - список ПО ВСЕЙ книге, не привязан к текущей странице
    // (29.08.2026, поймано пользователем живьём - "стр. 4" в шапке над
    // списком выглядела так, будто список тоже про эту страницу). Номер
    // страницы/навигация ‹›/аят-диапазон - убираем, они относятся только
    // к "Странице"/"Смыслу". Имя суры в шапке слева раньше оставляли как
    // ambient-контекст, но с телефона было неочевидно, что это за вкладка
    // (пользователь, 29.08.2026) - теперь явный заголовок "Мои слова",
    // имя суры возвращается при уходе с вкладки.
    document.getElementById('page-nav').style.display = name === 'mywords' ? 'none' : 'flex';
    document.getElementById('ayah-range').style.display = name === 'mywords' ? 'none' : '';
    document.getElementById('surah-name').textContent =
      name === 'mywords' ? T('tab_mywords') : currentSurahNameText;
    // На "Моих словах" в шапке стоит заголовок вкладки, а не имя суры -
    // открывать оттуда список сур бессмысленно, гасим вместе с шевроном.
    document.getElementById('btn-surah-pick').disabled = name === 'mywords';
    // 🔁 "повторение" (30.08.2026) - только на "Странице" (решение
    // пользователя), не на "Смысле"/"Мои слова".
    document.getElementById('btn-revision').style.display = name === 'page' ? '' : 'none';
    /* 📖 «Заучивание» прячется вместе с 🔁 (10.09.2026, решение
       пользователя). Кнопка, уводящая ИЗ раздела, не должна стоять в шапке
       этого раздела: из «Смысла» и «Слов» тап по ней — почти всегда промах,
       а не намерение. Сам hifzEnter() всё равно возвращает на страницу
       (защита с другой стороны): в режим заучивания попадают не только
       отсюда — есть ещё разбор устаза и пересдача. */
    document.getElementById('btn-hifz').style.display = name === 'page' ? '' : 'none';
    document.getElementById('btn-meaning').style.display = name === 'page' ? '' : 'none';
    document.getElementById('read-gloss-btn').style.visibility = name === 'page' ? '' : 'hidden';
    if (name === 'page') mushafFitSchedule();
    if (name === 'mywords') loadMyWords();
  }
  switchTab('page');

