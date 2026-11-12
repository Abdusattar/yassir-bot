  function T(key, vars) {
    if (!I18N) I18N = i18nTable();   // экран входа - см. i18nTable
    var dict = I18N[UI_LANG] || I18N.ru;
    var s = (dict[key] != null ? dict[key] : I18N.ru[key]) || '';
    if (vars) {
      Object.keys(vars).forEach(function (k) {
        s = s.split('%' + k + '%').join(vars[k]);
      });
    }
    return s;
  }

  // Переключатель темы (30.08.2026, ответ на вопрос студента "можно
  // выбрать тему?"). Сам выбор уже применён к <html> отдельным скриптом
  // в <head> (до отрисовки) - здесь только: посчитать, что сейчас видно
  // человеку (для иконки кнопки), и обработать клик.
  var THEME_KEY = 'yassir_theme';
  var savedTheme = null;
  try { savedTheme = localStorage.getItem(THEME_KEY); } catch (e) {}
  function currentEffectiveTheme() {
    if (savedTheme === 'light' || savedTheme === 'dark') return savedTheme;
    return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
  }
  // С 10.09.2026 тема выбирается переключателем в настройках. Кнопка в
  // шапке показывала иконку ЦЕЛИ ("нажми, станет тёмной") - в переключателе
  // из двух положений это было бы враньём: там видно ВЫБРАННОЕ.
  function markTheme() {
    var now = currentEffectiveTheme();
    Array.prototype.forEach.call(
      document.querySelectorAll('#sett-theme button'),
      function (b) { b.classList.toggle('on', b.getAttribute('data-theme') === now); });
  }
  document.getElementById('sett-theme').addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) return;
    savedTheme = b.getAttribute('data-theme');
    try { localStorage.setItem(THEME_KEY, savedTheme); } catch (e2) {}
    document.documentElement.setAttribute('data-theme', savedTheme);
    markTheme();
  });
  markTheme();

  // Переключатель языка (30.08.2026). Хранится на сервере по Telegram ID
  // (mufradat_lang) - тот же источник, что и язык слов в тренажёре, поэтому
  // интерфейс и переводы никогда не разъезжаются. localStorage тут только
  // как мгновенный кэш, чтобы интерфейс не моргал по-русски, пока идёт
  // запрос к API (у мусхафа старт заметно раньше ответа сервера).
  var LANG_KEY = 'yassir_ui_lang';
  try {
    var cached = localStorage.getItem(LANG_KEY);
    if (cached && I18N[cached]) UI_LANG = cached;
  } catch (e) {}

  function applyLang() {
    if (typeof markLang === 'function') markLang();
    if (typeof mrMarkSeg === 'function') mrMarkSeg();
    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      el.textContent = T(el.getAttribute('data-i18n'));
    });
    // Отдельно - строки с разметкой внутри (иконка в своём span), им нужен
    // innerHTML, а не textContent.
    document.querySelectorAll('[data-i18n-html]').forEach(function (el) {
      el.innerHTML = T(el.getAttribute('data-i18n-html'));
    });
    // Подсказки в полях ввода - у них перевод ложится в placeholder
    // (10.09.2026, первым таким стало поле «сколько раз» в панели 40+40).
    document.querySelectorAll('[data-i18n-ph]').forEach(function (el) {
      el.placeholder = T(el.getAttribute('data-i18n-ph'));
    });
    // Подсказка кнопки-значка (16.10.2026): title, а у кого есть - и
    // aria-label, его читает экранный диктор.
    document.querySelectorAll('[data-i18n-title]').forEach(function (el) {
      var t = T(el.getAttribute('data-i18n-title'));
      el.title = t;
      if (el.hasAttribute('aria-label')) el.setAttribute('aria-label', t);
    });
    document.querySelectorAll('[data-i18n-aria]').forEach(function (el) {
      el.setAttribute('aria-label', T(el.getAttribute('data-i18n-aria')));
    });
    document.title = T('doc_title');
    // Экраны, собранные в JS, перерисовываем - иначе язык применится
    // только после следующего действия студента.
    if (document.getElementById('trainer').style.display !== 'none' && trainerState) renderTrainer();
    if (document.getElementById('trainers').style.display === 'flex') trainersRender();
    if (document.getElementById('tajweed').style.display === 'flex' && tajweedState) renderTajweed(tajweedState);
    if (document.getElementById('nahw').style.display === 'flex' && nahwState) renderNahw(nahwState);
    if (dashFactsLast) dashLearnSub(dashFactsLast);
    if (typeof loadMyWords === 'function' &&
        document.getElementById('view-mywords') &&
        document.getElementById('view-mywords').classList.contains('active')) loadMyWords();
  }

  // Язык выбирается переключателем в настройках (10.09.2026). Раньше это
  // была выезжающая панель под кнопкой в шапке; кнопки в шапке больше нет,
  // а поведение сохранилось: один тап - и выбор уходит на сервер тем же
  // эндпоинтом, что и язык слов (он один на интерфейс и на переводы).
  function markLang() {
    Array.prototype.forEach.call(
      document.querySelectorAll('#sett-lang button'),
      function (b) { b.classList.toggle('on', b.getAttribute('data-lang') === UI_LANG); });
  }
  document.getElementById('sett-lang').addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) return;
    var lang = b.getAttribute('data-lang');
    // Тап по уже выбранному - ничего: ни запроса, ни перерисовки.
    if (!I18N[lang] || lang === UI_LANG) return;
    UI_LANG = lang;
    try { localStorage.setItem(LANG_KEY, UI_LANG); } catch (e2) {}
    applyLang();
    apiCall('/lang', { method: 'POST', body: { language: UI_LANG } })
      .then(function () { if (typeof loadPage === 'function' && currentPage) loadPage(currentPage); })
      .catch(function () {});
  });

