  // ── Пословные переводы отдельно от страниц (14.11.2026, wiki/wbw_split_plan.md) ──
  // Раньше перевод слова был вшит в page{N}.json, а каждый язык был полной копией
  // страницы (page{N}_ky.json ...) - копии разъезжались (Фатиха в _ky со старой
  // разбивкой строк). Теперь: лист - всегда основа раскладки (page{N}.json или
  // dm/page{N}.json), переводы слов - из wbw/<язык>/<сура>.json, собранных из базы
  // (scripts/build_wbw_chunks.py). Ключ слова "аят:позиция" - один файл на обе
  // раскладки. Адрес с хэшем из wbw/manifest.json: исправили подпись - новый адрес.
  // Нет слова на языке интерфейса - русская подпись (решение 30.08.2026), нет
  // манифеста или нужного языка в нём - старый путь (вшитые переводы, _lang-файл).
  var wbwManifestP = null;
  var wbwChunkP = {};
  function wbwManifest() {
    if (!wbwManifestP) {
      wbwManifestP = fetch('wbw/manifest.json', { cache: 'no-cache' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; })
        .then(function (m) {
          if (!m) wbwManifestP = null;   // не пришёл - спросим снова на следующем листе
          return m;
        });
    }
    return wbwManifestP;
  }
  // {"аят:позиция": подпись} суры на языке или null (нет файла / не скачался).
  function wbwChunk(man, lang, s) {
    var h = man && man[lang] && man[lang][String(s)];
    if (!h) return Promise.resolve(null);
    var key = lang + ':' + s + ':' + h;
    if (!wbwChunkP[key]) {
      wbwChunkP[key] = fetch('wbw/' + lang + '/' + s + '.json?h=' + h)
        .then(function (r) { if (!r.ok) throw new Error('wbw ' + key); return r.json(); })
        .then(function (d) { return d.w || {}; })
        .catch(function () { delete wbwChunkP[key]; return null; });
    }
    return wbwChunkP[key];
  }
  function wbwPageSurahs(data) {
    var seen = {}, out = [];
    (data.ayahs || []).forEach(function (a) {
      if (!seen[a.surah]) { seen[a.surah] = true; out.push(a.surah); }
    });
    return out;
  }
  // Вписывает переводы в токены листа (и в lines, и в ayahs[].tokens). Сура, чей
  // ru-файл не скачался, остаётся со вшитым переводом - лист не теряет подсказки.
  function wbwApply(data, man, lang) {
    var surahs = wbwPageSurahs(data);
    var jobs = [];
    surahs.forEach(function (s) {
      jobs.push(wbwChunk(man, 'ru', s));
      jobs.push(lang !== 'ru' ? wbwChunk(man, lang, s) : Promise.resolve(null));
    });
    if (lang !== 'ru') {
      // смысл аята на языке интерфейса - из meaning/ (у ru-основы вшит Кулиев)
      surahs.forEach(function (s) {
        jobs.push(meaningSurah(meaningSrc(), s).catch(function () { return null; }));
      });
    }
    return Promise.all(jobs).then(function (res) {
      var ru = {}, loc = {}, mean = {};
      surahs.forEach(function (s, i) {
        ru[s] = res[2 * i];
        loc[s] = res[2 * i + 1];
        if (lang !== 'ru') mean[s] = res[2 * surahs.length + i];
      });
      function fill(t, s, a) {
        if (t.type !== 'word' || !ru[s]) return;
        var k = a + ':' + t.position;
        t.translation = (loc[s] && loc[s][k]) || ru[s][k] || '';
      }
      (data.lines || []).forEach(function (l) {
        (l.tokens || []).forEach(function (t) { fill(t, t.surah, t.ayah); });
      });
      (data.ayahs || []).forEach(function (a) {
        (a.tokens || []).forEach(function (t) { fill(t, a.surah, a.ayah); });
        var m = mean[a.surah];
        if (m && m[a.ayah - 1]) a.meaning = m[a.ayah - 1];
      });
      return data;
    });
  }
  // Лист не ждёт переводы дольше WBW_WAIT_MS (слабая сеть): не успели - показываем
  // со вшитым переводом (старый путь), а файлы докачиваются и лягут в кэш к
  // следующему листу. До чистки страниц (шаг 3 плана) вшитый перевод всегда есть.
  var WBW_WAIT_MS = 2500;
  function wbwSoon(p) {
    return new Promise(function (resolve) {
      var done = false;
      var timer = setTimeout(function () { if (!done) { done = true; resolve(null); } }, WBW_WAIT_MS);
      p.then(function (v) { if (!done) { done = true; clearTimeout(timer); resolve(v); } },
             function () { if (!done) { done = true; clearTimeout(timer); resolve(null); } });
    });
  }
  // Единый загрузчик листа для мусхафа, заучивания и «Сегодня».
  function fetchPageData(n) {
    var lang = UI_LANG;
    var base = fetch(pageJsonUrl(n)).then(function (r) {
      if (!r.ok) throw new Error('page ' + n);
      return r.json();
    });
    function oldWay(data) {
      if (lang === 'ru') return data;
      // языковая копия листа, нет её - русская основа
      return fetch(pageJsonUrl(n, lang))
        .then(function (r) { return r.ok ? r.json() : data; })
        .catch(function () { return data; });
    }
    return Promise.all([wbwSoon(wbwManifest()), base]).then(function (got) {
      var man = got[0], data = got[1];
      if (!(man && man.ru && (lang === 'ru' || man[lang]))) return oldWay(data);
      // переводы вписываются в копию: опоздавшая запись не тронет уже показанный лист
      var copy = JSON.parse(JSON.stringify(data));
      return wbwSoon(wbwApply(copy, man, lang)).then(function (filled) {
        return filled || oldWay(data);
      });
    });
  }
