  // Раскладка мусхафа (23.09.2026): 'madani' - наш мединский (page{N}.json),
  // 'dm' - Дар аль-Маариф, египетский таджвидный по раскладке 1405H
  // (dm/page{N}.json, scripts/build_dm_layout.py). Главный источник -
  // сервер (/layout, по нему считается указатель 40+40), localStorage -
  // мгновенный кэш до ответа. reviewLayout - лист чужой сдачи у устаза
  // открывается в раскладке студента, пока идёт разбор.
  var LAYOUT_KEY = 'yassir_mushaf_layout';
  var MUSHAF_LAYOUT = 'madani';
  try {
    if (localStorage.getItem(LAYOUT_KEY) === 'dm') MUSHAF_LAYOUT = 'dm';
  } catch (e) {}
  var reviewLayout = null;
  function pageLayout() { return reviewLayout || MUSHAF_LAYOUT; }
  // Лист чужой (или своей старой) сдачи - в раскладке, в которой она
  // записана. true - раскладка на экране сменилась, лист надо перечитать.
  function useViewLayout(lay) {
    var before = pageLayout();
    lay = lay || 'madani';
    reviewLayout = lay === MUSHAF_LAYOUT ? null : lay;
    return pageLayout() !== before;
  }
  function dropViewLayout() {
    var was = !!reviewLayout;
    reviewLayout = null;
    return was;
  }
  // ?v у египетских листов: nginx держит no-cache только для /pageN.json в
  // корне, а dm/ идёт общим правилом, и телефон мог бы днями показывать
  // старую сборку (ловушка 29.08.2026). Пересобрали dm/ - поднять число.
  var DM_DATA_VER = 2;
  function pageJsonUrl(n, lang) {
    var file = 'page' + n + (lang && lang !== 'ru' ? '_' + lang : '') + '.json';
    return pageLayout() === 'dm' ? 'dm/' + file + '?v=' + DM_DATA_VER : file;
  }

  // ── Единый список отпечатков данных (14.11.2026, wiki/architecture.md Р1) ──
  // data_manifest.json: отпечаток содержимого каждого листа (обе раскладки), файла
  // смысла и файла переводов слов (scripts/build_data_manifest.py, собирается на
  // сервере сам). Файл просим по адресу ...json?h=<отпечаток>: изменился файл -
  // изменился адрес, ручные номера (DM_DATA_VER, MEANING_VER) больше поднимать не
  // надо; не изменился - service worker отдаёт из кэша, не заходя в сеть.
  // Списка нет или он не успел (слабая сеть) - старые адреса, всё работает как раньше.
  var DATA_MAN_WAIT_MS = 1500;
  var dataManP = null;
  var dataManVal = null;      // пришедший список
  var dataManSlow = false;    // один раз не дождались - больше лист из-за него не держим
  function dataManifest() {
    if (!dataManP) {
      dataManP = fetch('data_manifest.json', { cache: 'no-cache' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; })
        .then(function (m) {
          if (m && m.page) { dataManVal = m; return m; }
          dataManP = null;      // не пришёл - спросим снова на следующем листе
          return null;
        });
    }
    return dataManP;
  }
  dataManifest();   // сразу при запуске: к первому листу список обычно уже пришёл
  // Список или null, если он не пришёл за DATA_MAN_WAIT_MS.
  function dataManifestSoon() {
    if (dataManVal) return Promise.resolve(dataManVal);
    var p = dataManifest();
    if (dataManSlow) return Promise.resolve(null);
    return new Promise(function (resolve) {
      var timer = setTimeout(function () { dataManSlow = true; resolve(null); }, DATA_MAN_WAIT_MS);
      p.then(function (m) { clearTimeout(timer); resolve(m); });
    });
  }
  // Адрес основы листа текущей раскладки: с отпечатком, если список есть.
  function pageUrlP(n) {
    var dm = pageLayout() === 'dm';
    return dataManifestSoon().then(function (m) {
      var h = m && m[dm ? 'dm' : 'page'] && m[dm ? 'dm' : 'page'][String(n)];
      return h ? (dm ? 'dm/' : '') + 'page' + n + '.json?h=' + h : pageJsonUrl(n);
    });
  }

