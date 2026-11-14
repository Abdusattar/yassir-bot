  var currentPage = FIRST_PAGE;

  function loadPage(n) {
    if (n < FIRST_PAGE || n > LAST_PAGE) return;
    if (n !== currentPage) trail('page', { p: n });
    currentPage = n;
    recTrackPage(n);
    // Кэш - по паре "страница + язык" (30.08.2026): при переключении языка
    // та же страница должна перечитаться с другими переводами, а не отдаться
    // из памяти по-старому.
    var cacheKey = n + ':' + UI_LANG + ':' + pageLayout();
    if (cache[cacheKey]) {
      renderPage(cache[cacheKey]);
      try { localStorage.setItem('yassir_mushaf_page', String(n)); } catch (e) {}
      mushafPrefetch(n);
      return;
    }
    // Лист раскладки + переводы слов на языке интерфейса (14.11.2026,
    // fetchPageData в 034_wbw_words.js): слова без перевода на языке - по-русски,
    // занятие не прерывается там, где перевод ещё не готов. Раскладка (dm/)
    // сохраняется - египетский лист не подменяется мединским.
    fetchPageData(n)
      .then(function (data) {
        cache[cacheKey] = data;
        // Быстро листали: пока шла эта страница, открыли другую - опоздавший
        // ответ не перерисовывает экран (11.10.2026, жалоба устаза на листание).
        if (currentPage !== n || cacheKey !== n + ':' + UI_LANG + ':' + pageLayout()) return;
        renderPage(data);
        try { localStorage.setItem('yassir_mushaf_page', String(n)); } catch (e) {}
        mushafPrefetch(n);
      });
  }

  /* Соседние листы заранее (11.10.2026, устаз: «быстро листаю - ощутимая
     задержка»). У каждой страницы свой JSON (~47 КБ) и свой шрифт V4 (~85 КБ),
     и до этого оба качались только в момент перелистывания: 0,7-0,9 с на
     новый лист. Теперь после отрисовки тянем следующий, предыдущий и через
     один (с 11.10 - на три вперёд): JSON - в память (cache), шрифт - FontFace.load() без добавления в
     document.fonts (байты ложатся в кэш браузера и service worker), и
     loadV4Font на перелистывании берёт его оттуда. */
  /* 12.11.2026 (решение пользователя, скрин стр. 246 - шрифт не успел на 4G):
     окно шире - 10 листов вперёд и 2 назад (~130 КБ на лист: JSON + шрифт,
     всё окно ~1,5 МБ). Но не всё разом: на слабой сети десять параллельных
     загрузок задержали бы как раз следующий лист. Очередь по близости
     (n+1, n+2, n-1, n+3...), не больше двух загрузок одновременно; лист
     готов, когда пришли и JSON, и шрифт (шрифт V4 у tarteel кэшируется
     браузером на 4 ч, в браузере ещё и service worker). При перелистывании
     окно сдвигается - докачивается обычно один новый лист. Не пришло -
     метка снимается, лист попробуем снова при следующем сдвиге. */
  var MUSHAF_AHEAD = 10, MUSHAF_BEHIND = 2, MUSHAF_PREFETCH_PAR = 2;
  var mushafPrefetching = {}, mushafWarmFonts = {};
  var mushafPrefetchQueue = [], mushafPrefetchActive = 0;
  function mushafWarmFont(url) {
    if (!url || typeof FontFace === 'undefined') return Promise.resolve();
    if (mushafWarmFonts[url]) return mushafWarmFonts[url];
    // тот же порядок адресов, что при показе: свой сервер, tarteel, зеркало
    var p = loadV4Face('mushaf-warm', url)
      .catch(function () { delete mushafWarmFonts[url]; });
    mushafWarmFonts[url] = p;
    return p;
  }
  function mushafPrefetchOne(p) {
    var key = p + ':' + UI_LANG + ':' + pageLayout();
    var warm = function (data) {
      var fp = pageExtraFontPage(data);
      return Promise.all([mushafWarmFont(data.font_url), fp ? mushafWarmFont(v4FontUrl(fp)) : null]);
    };
    if (cache[key]) return warm(cache[key]);
    return fetchPageData(p)
      .then(function (data) { cache[key] = data; return warm(data); });
  }
  function mushafPrefetchPump() {
    while (mushafPrefetchActive < MUSHAF_PREFETCH_PAR && mushafPrefetchQueue.length) {
      var p = mushafPrefetchQueue.shift();
      var key = p + ':' + UI_LANG + ':' + pageLayout();
      if (mushafPrefetching[key]) continue;
      mushafPrefetching[key] = true;
      mushafPrefetchActive++;
      (function (key) {
        mushafPrefetchOne(p).catch(function () {}).then(function () {
          delete mushafPrefetching[key];
          mushafPrefetchActive--;
          mushafPrefetchPump();
        });
      })(key);
    }
  }
  function mushafPrefetch(n) {
    var order = [n + 1, n + 2, n - 1, n + 3];
    for (var i = 4; i <= MUSHAF_AHEAD; i++) order.push(n + i);
    for (var j = 2; j <= MUSHAF_BEHIND; j++) order.push(n - j);
    // Новая очередь вместо старой: листнули - ближние листы важнее дальних прошлого окна.
    mushafPrefetchQueue = order.filter(function (p) {
      if (p < FIRST_PAGE || p > LAST_PAGE) return false;
      var c = cache[p + ':' + UI_LANG + ':' + pageLayout()];
      return !(c && mushafWarmFonts[c.font_url]);   // уже готов - не трогаем
    });
    mushafPrefetchPump();
  }

