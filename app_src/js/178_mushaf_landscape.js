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

