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
  // Лист ждёт переводы не дольше WBW_WAIT_MS (0,7 с: обычно они уже в кэше, а перерисовка на глазах хуже короткой паузы). Не успели - лист отдаётся
  // сразу старым путём (вшитый перевод / _lang-копия; после чистки страниц, шаг 3
  // wiki/wbw_split_plan.md, - без подписей), а когда переводы всё-таки пришли,
  // зовётся onLate(лист с переводами): показывающий экран подменяет данные и
  // дорисовывает подписи. Так лист виден сразу, подписи дописываются по приходу
  // (wiki/architecture.md, слой 4, правило 5).
  var WBW_WAIT_MS = 700;
  function wbwSoon(p) {
    return new Promise(function (resolve) {
      var done = false;
      var timer = setTimeout(function () { if (!done) { done = true; resolve(null); } }, WBW_WAIT_MS);
      p.then(function (v) { if (!done) { done = true; clearTimeout(timer); resolve(v); } },
             function () { if (!done) { done = true; clearTimeout(timer); resolve(null); } });
    });
  }
  // Единый загрузчик листа для мусхафа, заучивания и «Сегодня».
  // onLate (необязательно) - см. выше; зовётся не больше одного раза.
  function fetchPageData(n, onLate) {
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
    // лист с переводами из wbw/ или null (нет манифеста / языка / файл не пришёл)
    var filledP = Promise.all([wbwManifest(), base]).then(function (got) {
      var man = got[0], data = got[1];
      if (!(man && man.ru && (lang === 'ru' || man[lang]))) return null;
      // переводы вписываются в копию: опоздавшая запись не тронет уже показанный лист
      return wbwApply(JSON.parse(JSON.stringify(data)), man, lang);
    }).catch(function () { return null; });
    return wbwSoon(filledP).then(function (filled) {
      if (filled) return filled;
      if (onLate) filledP.then(function (late) { if (late) onLate(late); });
      return base.then(oldWay);
    });
  }
