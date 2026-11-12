  // Закладка страницы чтения (30.08.2026) - 🔖 сохраняет ТЕКУЩУЮ страницу
  // на сервере (по Telegram ID, core/mushaf_words.py), "«" переносит на
  // сохранённую. Не то же самое, что закладка тренажёра (mufradat_page) -
  // отдельная точка возврата, которую студент выставляет сам.
  /* С 22.09.2026 все три действия - в меню 🔖 (#bm-menu). Пункты - те же
     кнопки с теми же id, что стояли в полосе, поэтому и снимки онбординга,
     и стенды жмут их как раньше. Подсказки «сохранено / закладки нет»
     встают у 🔖: пункт меню к этому моменту уже скрыт. */
  var bmBtn = document.getElementById('btn-bookmark');
  var bmMenu = document.getElementById('bm-menu');
  // Откуда открыли меню - у той кнопки и всплывают подсказки (11.11.2026:
  // в шапке с панелью это номер страницы #tb-page, в строке страниц - 🔖).
  var bmAnchor = bmBtn;
  function bmClose() { bmMenu.classList.remove('on'); }
  function bmOpen(e, anchor) {
    e.stopPropagation();
    if (bmMenu.classList.contains('on')) { bmClose(); return; }
    bmAnchor = anchor;
    bmMenu.classList.add('on');
    // Под кнопкой, а если снизу не хватает места (полоса теперь внизу
    // экрана, а лёжа - в конце листа) - над ней. Прижато к экрану.
    var r = anchor.getBoundingClientRect(), m = bmMenu.getBoundingClientRect();
    var top = r.bottom + 6;
    if (top + m.height > window.innerHeight - 8) top = r.top - m.height - 6;
    bmMenu.style.top = Math.max(8, top) + 'px';
    bmMenu.style.left = Math.max(8, Math.min(r.left, window.innerWidth - m.width - 8)) + 'px';
    // Номер страницы закладки прямо в пункте: видно, куда уведёт.
    apiCall('/bookmark').then(function (res) {
      if (res.status !== 401 && res.data && res.data.page) {
        document.getElementById('bm-go-sub').textContent = T('page_n', { N: res.data.page });
      }
    });
  }
  // Листание кнопками под листом (перенесено из куска заучивания 12.11.2026).
  document.getElementById('btn-prev').addEventListener('click', function () {
    loadPage(currentPage + 1);
  });
  document.getElementById('btn-next').addEventListener('click', function () {
    loadPage(currentPage - 1);
  });

  // Начало суры Аль-Бакара - стр. 2 (проверено 17.08.2026, см. модульный
  // docstring core/quran_pages.py: "стр. 2 начинает Аль-Бакара с аята 1").
  var BAQARA_START_PAGE = 2;
  document.getElementById('btn-go-baqara').addEventListener('click', function () {
    loadPage(BAQARA_START_PAGE);
  });

  bmBtn.addEventListener('click', function (e) { bmOpen(e, bmBtn); });
  document.getElementById('tb-page').addEventListener('click', function (e) { bmOpen(e, document.getElementById('tb-page')); });
  document.getElementById('tb-next').addEventListener('click', function () { document.getElementById('btn-next').click(); });
  document.getElementById('tb-prev').addEventListener('click', function () { document.getElementById('btn-prev').click(); });
  document.getElementById('btn-bm-baqara').addEventListener('click', function () { loadPage(BAQARA_START_PAGE); });
  var bmJumpInput = document.getElementById('bm-jump-input');
  function bmJumpGo() {
    var n = parseInt(bmJumpInput.value, 10);
    if (n >= FIRST_PAGE && n <= LAST_PAGE) { loadPage(n); bmClose(); }
  }
  document.getElementById('bm-jump-go').addEventListener('click', bmJumpGo);
  bmJumpInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') bmJumpGo(); });
  bmJumpInput.addEventListener('click', function (e) { e.stopPropagation(); });
  // Поле ввода внутри меню: тап по нему меню не закрывает, по пунктам - закрывает.
  bmMenu.addEventListener('click', function (e) { if (e.target.closest('button') && !e.target.closest('#bm-jump')) bmClose(); });
  document.addEventListener('click', function (e) {
    if (bmMenu.classList.contains('on') && !bmMenu.contains(e.target)) bmClose();
  });
  document.getElementById('page-wrap').addEventListener('scroll', bmClose, { passive: true });
  document.getElementById('btn-bookmark-save').addEventListener('click', function () {
    apiCall('/bookmark', { method: 'POST', body: { page: currentPage } }).then(function (res) {
      if (res.status !== 401) showPopupMessage(bmAnchor, T('bookmark_saved', { N: currentPage }));
    });
  });
  document.getElementById('btn-bookmark-go').addEventListener('click', function () {
    var btn = bmAnchor;
    apiCall('/bookmark').then(function (res) {
      if (res.status === 401) return;
      if (res.data && res.data.page) {
        loadPage(res.data.page);
      } else {
        showPopupMessage(btn, T('bookmark_none'));
      }
    });
  });

