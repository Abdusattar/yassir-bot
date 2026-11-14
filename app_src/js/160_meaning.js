  // ── Смысловой перевод (02.11.2026, решения пользователя) ─────────────
  // 1) Удержание на аяте (полсекунды) - панель со смыслом ВСЕГО аята, в
  //    чтении, повторении и заучивании. Тап (перевод слова) и двойной тап
  //    («Мои слова») не задеты: после удержания следующий click гасится
  //    целиком, в фазе захвата - разом для всех обработчиков #ayah-text.
  //    У устаза в проверке удержания нет: там касание - пометка ошибки.
  // 2) 📜 - отдельное чтение смысла, «живёт своей жизнью»: своё место
  //    (сура:аят верхнего аята, не пиксели - Абу Адель вдвое длиннее
  //    Кулиева), на сервере по пользователю (/api/muf/meaning_pos) - у
  //    Telegram и иконки на экране «Домой» разный localStorage. С местом
  //    заучивания не связано никак.
  // Перевод: у русского - Кулиев или Абу Адель (переключатель прямо в окне
  // и в настройках, выбор общий), у ky/uz/zh - свой единственный.
  // Данные: mushaf_data/meaning/<перевод>/<сура>.json (scripts/build_meaning_reader.py).
  var MEANING_VER = '1';
  var MTR_KEY = 'yassir_meaning_tr';
  var MPOS_KEY = 'yassir_meaning_pos';
  var MEANING_HOLD_MS = 500;
  var mtrRu = 'ru_kuliev';
  try { if (localStorage.getItem(MTR_KEY) === 'ru_abuadel') mtrRu = 'ru_abuadel'; } catch (e) {}

  function meaningSrc() {
    return UI_LANG === 'ru' ? mtrRu : (UI_LANG === 'ky' || UI_LANG === 'uz' || UI_LANG === 'zh' ? UI_LANG : 'ru_kuliev');
  }
  var meaningCache = {};
  function meaningSurah(src, s) {
    var key = src + '/' + s;
    if (!meaningCache[key]) {
      // адрес с отпечатком из единого списка (030); списка нет - прежний ручной номер
      meaningCache[key] = dataManifestSoon().then(function (m) {
          var h = m && m.meaning && m.meaning[src] && m.meaning[src][String(s)];
          return fetch('meaning/' + key + '.json?' + (h ? 'h=' + h : 'v=' + MEANING_VER));
        })
        .then(function (r) { if (!r.ok) throw new Error('meaning ' + key); return r.json(); })
        .then(function (d) { return d.t || []; });
      meaningCache[key].catch(function () { delete meaningCache[key]; });
    }
    return meaningCache[key];
  }
  function surahRow(s) { return SURAH_INDEX[s - 1]; }

  // Переключатели переводчика: в панели, в чтении, в настройках - один выбор.
  function mrMarkSeg() {
    var ru = UI_LANG === 'ru';
    ['as-seg', 'mr-seg'].forEach(function (id) { document.getElementById(id).hidden = !ru; });
    document.getElementById('sett-mtr-card').hidden = !ru;
    Array.prototype.forEach.call(
      document.querySelectorAll('#as-seg button, #mr-seg button, #sett-mtr button'),
      function (b) { b.classList.toggle('on', b.getAttribute('data-mtr') === mtrRu); });
  }
  function setMtr(tr) {
    if (tr !== 'ru_abuadel') tr = 'ru_kuliev';
    if (tr === mtrRu) return;
    mtrRu = tr;
    try { localStorage.setItem(MTR_KEY, tr); } catch (e) {}
    trail('mtr', { tr: tr });
    mrMarkSeg();
    if (!document.getElementById('ayah-sheet').hidden) sheetShow();
    if (!document.getElementById('mreader').hidden) mrRender(mrTopAyah());
  }
  ['as-seg', 'mr-seg', 'sett-mtr'].forEach(function (id) {
    document.getElementById(id).addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (b) setMtr(b.getAttribute('data-mtr'));
    });
  });
  mrMarkSeg();

