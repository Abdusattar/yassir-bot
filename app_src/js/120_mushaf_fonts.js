  // Шрифт QPC V4 Tajweed - свой файл НА КАЖДУЮ страницу (604 разных
  // файла), значит на каждой навигации грузится заново. Раньше src
  // переписывался прямо в <style> - HTML с class="v4-word" уходил в DOM
  // СИНХРОННО, до того как шрифт реально скачался, браузер красил первый
  // кадр текста запасным шрифтом (тот не понимает PUA-глифы шрифта v4) -
  // видимый "голый текст, потом сворачивается" (реальный баг, пользователь
  // поймал на живой странице 28.08.2026). Фикс - FontFace API: явно ждём
  // .load() ПЕРЕД тем, как вставлять текст в DOM, никакого кадра с неверным
  // шрифтом просто не возникает физически. currentV4Face - чтобы не
  // копить в document.fonts все посещённые страницы разом (604 файла).
  // wantV4Url (02.10.2026) - шрифт последнего открытого листа. Листали
  // быстро, шрифт прошлого листа докачался позже нового - он не ставится,
  // иначе глифы листа нарисовались бы буквами соседнего (гонка, пойманная
  // в тренажёре слов, см. trainerV4Want).
  /* Зеркало шрифтов V4 (02.11.2026, Умар устаз: стр. 328 = стр. 327). У
     tarteel пропал p328.woff2 (404) - шрифт листа не грузился, на экране
     оставался шрифт прошлого листа, и коды стр. 328 рисовались словами
     стр. 327 (коды слов на всех листах одни и те же: U+FC41...). Те же
     файлы лежат на CDN quran.com - побайтно (сверено на p1/327/329/604,
     p328 сверен по кодам с sources/v4_fonts/p328.ttf). Основной адрес не
     ответил - пробуем зеркало. Проверка всех 604: scripts/check_v4_fonts.py. */
  var V4_CDN_MAIN = 'https://static-cdn.tarteel.ai/qul/fonts/quran_fonts/v4-tajweed/woff2/';
  var V4_CDN_MIRROR = 'https://verses.quran.foundation/fonts/quran/hafs/v4/colrv1/woff2/';
  function v4MirrorUrl(url) {
    return url && url.indexOf(V4_CDN_MAIN) === 0 ? V4_CDN_MIRROR + url.slice(V4_CDN_MAIN.length) : null;
  }
  function loadV4Face(family, url) {
    return new FontFace(family, "url('" + url + "')").load().catch(function (err) {
      var alt = v4MirrorUrl(url);
      if (!alt) throw err;
      return new FontFace(family, "url('" + alt + "')").load();
    });
  }

  // v4Req (02.11.2026) - номер запроса шрифта листа. Опоздавший ответ
  // сверяется по нему, а не по адресу: адрес может смениться на зеркало.
  var currentV4Face = null, wantV4Url = null, v4Req = 0;
  function loadV4Font(url) {
    wantV4Url = url;
    var req = ++v4Req;
    return loadV4Face('mushaf-v4', url).then(function (loaded) {
      if (req !== v4Req) return;
      if (currentV4Face) { try { document.fonts.delete(currentV4Face); } catch (e) {} }
      document.fonts.add(loaded);
      currentV4Face = loaded;
    }, function (err) {
      // Ни основной адрес, ни зеркало. Шрифт прошлого листа снимаем: с ним
      // коды этого листа нарисовались бы ЧУЖИМИ словами. Лист покажется
      // обычным текстом (reveal, plain).
      if (req === v4Req && currentV4Face) {
        try { document.fonts.delete(currentV4Face); } catch (e) {}
        currentV4Face = null;
      }
      throw err;
    });
  }

  // Второй шрифт листа - только у раскладки Дар аль-Маариф (23.09.2026),
  // см. .v4-b в стилях. fp - номер мединского листа, чьим шрифтом рисуется
  // слово; у мединской раскладки его нет никогда, и этот путь не работает.
  var currentV4FaceB = null, currentV4FaceBPage = null;
  function v4FontUrl(fp) {
    return 'https://static-cdn.tarteel.ai/qul/fonts/quran_fonts/v4-tajweed/woff2/p' + fp + '.woff2';
  }
  function pageExtraFontPage(data) {
    var fp = null;
    (data.lines || []).forEach(function (l) {
      (l.tokens || []).forEach(function (t) { if (t.fp && !fp) fp = t.fp; });
    });
    return fp;
  }
  function loadV4Fonts(data) {
    var main = loadV4Font(data.font_url);
    var req = v4Req;
    var fp = pageExtraFontPage(data);
    if (!fp || fp === currentV4FaceBPage) return main;
    var extra = loadV4Face('mushaf-v4-b', v4FontUrl(fp)).then(function (loaded) {
      if (req !== v4Req) return;
      if (currentV4FaceB) { try { document.fonts.delete(currentV4FaceB); } catch (e) {} }
      document.fonts.add(loaded);
      currentV4FaceB = loaded;
      currentV4FaceBPage = fp;
    }, function (err) {
      if (req === v4Req && currentV4FaceB) {
        try { document.fonts.delete(currentV4FaceB); } catch (e) {}
        currentV4FaceB = null; currentV4FaceBPage = null;
      }
      throw err;
    });
    return Promise.all([main, extra]);
  }
  // Класс слова V4: у слова с чужого мединского листа - второй шрифт.
  function v4Cls(t) { return t && t.fp ? 'v4-word v4-b' : 'v4-word'; }

