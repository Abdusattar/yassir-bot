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

