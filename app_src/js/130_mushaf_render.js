  var currentPageData = null;
  var currentSurahNameText = '';
  // Номера сур, представленных на текущей странице (обычно одна, но бывает
  // переход - напр. стр. 106: конец Ан-Нисы + начало Аль-Маиды). Нужны
  // только для подсветки текущего места в списке сур.
  var currentSurahNums = [];
  function renderPage(data) {
    currentPageData = data;
    currentSurahNameText = data.surah_names.join(', ');
    currentSurahNums = [];
    data.ayahs.forEach(function (a) {
      if (currentSurahNums.indexOf(a.surah) === -1) currentSurahNums.push(a.surah);
    });
    document.getElementById('surah-name').textContent = currentSurahNameText;
    var firstAyah = data.ayahs[0], lastAyah = data.ayahs[data.ayahs.length - 1];
    document.getElementById('ayah-range').textContent =
      lastAyah.ayah !== firstAyah.ayah
        ? T('ayah_range', { A: firstAyah.ayah, B: lastAyah.ayah })
        : T('ayah_n', { N: firstAyah.ayah });
    document.getElementById('page-indicator').textContent = T('page_n', { N: data.page });
    document.getElementById('tb-n').textContent = T('page_n', { N: data.page });

    // Настоящая построчная вёрстка (QUL/King Fahd Complex, 27.08.2026) -
    // каждая строка мусхафа - свой <div>, а не единый абзац с переносом
    // по ширине браузера. surah_name_ar - реальное арабское имя суры
    // (quran_transcript), не наша русская транслитерация из SURAH_NAMES.
    // plain (02.11.2026) - шрифт листа не загрузился ни с одного адреса:
    // слова обычным текстом из данных, без красок V4. Некрасиво, но слова
    // верные; глифы без своего шрифта - чужие слова или квадратики.
    var pairs = mushafPairs(data.lines || []);
    var pageHtml = function (plain) {
    var html = '';
    var textLineNo = 0;
    var lastMa = '';
    var bare = function (s) { return String(s || '').replace(/<[^>]*>/g, ''); };
    (data.lines || []).forEach(function (line) {
      if (line.type === 'header') {
        html += '<div class="surah-banner">سُورَةُ ' + line.surah_name_ar + '</div>';
      } else if (line.type === 'bismillah') {
        if (line.html) html += '<div class="bismillah">' + line.html + '</div>';
      } else if (line.type === 'text') {
        // fs - своя доля кегля у длинной строки раскладки Дар аль-Маариф
        // (scripts/build_dm_layout.py: squeeze_lines, не меньше 0.92): иначе
        // одна длинная строка уменьшала бы шрифт всего листа. У мединской
        // раскладки fs нет, строка как была.
        html += '<div class="mushaf-line" data-line="' + (textLineNo++) + '"' +
          (line.fs ? ' style="font-size:' + line.fs + 'em"' : '') + '>';
        line.tokens.forEach(function (t) {
          if (t.type === 'word') {
            // data-surah/data-ayah/data-pos/data-arabic - только вместе с
            // data-tr (29.08.2026, для "Мои слова" - двойной тап нужно
            // от чего-то отличать от одиночного, а слово без перевода и
            // так не кликабельно, см. showWordPopup/addToMyWords ниже).
            // Второе слово пары (28.09.2026) получает перевод головы и
            // data-head - см. mushafPairs.
            var wkey = t.surah + ':' + t.ayah + ':' + t.position;
            // data-ma - аят слова у КАЖДОГО токена (02.11.2026): по нему
            // удержание открывает смысловой перевод аята. Не data-ayah: тот
            // есть только у слов с переводом и читается заучиванием/пометками.
            lastMa = t.surah + ':' + t.ayah;
            var ma = ' data-ma="' + lastMa + '"';
            var head = !t.translation && pairs[wkey];
            // data-gl - подпись под словом лёжа в заучивании (19.10.2026):
            // только у головы пары (хвост делит её перевод) и без скобок -
            // в скобках пояснение переводчика, а подпись - дословно.
            var gl = t.translation ? glossText(t.translation) : '';
            var tr = (t.translation || head) ? ' data-tr="' + escapeAttr(t.translation || head.translation) + '"' +
              (gl ? ' data-gl="' + escapeAttr(gl) + '"' : '') +
              ' data-surah="' + t.surah + '" data-ayah="' + t.ayah + '" data-pos="' + t.position + '"' +
              ' data-arabic="' + escapeAttr(t.html) + '" data-w="' + wkey + '"' +
              (head ? ' data-head="' + head.surah + ':' + head.ayah + ':' + head.position + '"' : '') : '';
            if (t.code_v4 && !plain) {
              html += '<span class="' + v4Cls(t) + '"' + ma + tr + '>' + t.code_v4 + '</span>';
            } else {
              // Без меток <tajweed>: Safari на iOS рвёт слово на границе метки.
              html += '<span' + ma + tr + '>' + (plain ? bare(t.html) : t.html) + '</span>';
            }
          } else if (t.type === 'marker') {
            html += '<span class="marker">' + t.html + '</span>';
          } else if (t.type === 'ayah_end') {
            if (t.code_v4 && !plain) {
              html += '<span class="' + v4Cls(t) + '"' + (lastMa ? ' data-ma="' + lastMa + '"' : '') + '>' + t.code_v4 + '</span>';
            } else {
              html += '<span class="ayah-end"' + (lastMa ? ' data-ma="' + lastMa + '"' : '') + '>﴾' + bare(t.html) + '﴿</span>';
            }
          }
        });
        html += '</div>';
      }
    });
    return html;
    };
    var reveal = function (plain) {
      // Опоздавший лист (02.11.2026): листали быстро, шрифт прошлого листа
      // докачался позже - его текст не ложится поверх нового листа.
      if (currentPageData !== data) return;
      var html = pageHtml(plain);
      // Новый лист - с начала (21.09.2026). Стоя лист почти всегда влезает
      // целиком, и прокрутка не сбрасывалась никогда; лёжа дочитал до строки
      // страниц внизу, нажал «›» - и следующий лист открывался сразу в конце.
      // Тот же лист, нарисованный заново (пометки устаза), место не теряет.
      var shown = document.getElementById('ayah-text').getAttribute('data-page');
      if (shown !== String(data.page)) document.getElementById('page-wrap').scrollTop = 0;
      document.getElementById('ayah-text').innerHTML = html;
      // Номер листа на самом тексте - по нему mushafFitPredict берёт ширину.
      document.getElementById('ayah-text').setAttribute('data-page', data.page);
      // Обычный текст шире глифов V4 - кегль по таблице MUSHAF_FIT_W не
      // годится, mushafFitPredict его пропускает, и кегль меряется.
      if (plain) document.getElementById('ayah-text').setAttribute('data-plain', '1');
      else document.getElementById('ayah-text').removeAttribute('data-plain');
      if (typeof hifzApply === 'function') hifzApply();
      // Пометки слов рисуем ЗДЕСЬ, когда страница реально отрисована, а не
      // по таймеру после loadPage: страница приходит с сервера, и угадывать
      // задержку - тот же класс гонки, что уже ловили со шрифтом (27.08).
      if (typeof review !== 'undefined' && review.on) reviewAfterRender();
      else if (pendingErrorMarks) { applyErrorMarks(pendingErrorMarks); pendingErrorMarks = null; }
      // Не сразу clampFontToFit() - у loadV4Font() .load() резолвится, как
      // только байты шрифта скачаны и распаршены, но браузеру ещё нужно
      // применить его к УЖЕ ВСТАВЛЕННОМУ тексту (шейпинг/layout) - если
      // мерить scrollWidth/clientWidth синхронно сразу после innerHTML,
      // попадаешь в кадр с ещё не применённым шрифтом и подгонка считает по
      // чужим метрикам (тот самый класс бага 27.08). До 13.09.2026 здесь
      // ждали document.fonts.ready - в WebKit он приходит ДО раскладки, и на
      // айфонах замер всё равно шёл по тексту без шрифта (см.
      // MUSHAF_REFIT_DELAYS). Теперь - кадры и повторы по времени.
      mushafFitSchedule();
    };
    // Если шрифт не загрузился (сеть) - всё равно показываем текст, а не
    // висим бесконечно; PUA-глифы без своего шрифта покажутся "тофу"-
    // прямоугольниками в запасном шрифте - хуже, чем пустая страница, но
    // студент хотя бы поймёт, что что-то не так, а не решит, что бот завис.
    // Шрифт не пришёл - лист обычным текстом, но не навсегда (12.11.2026,
    // скрин пользователя materials/246.jpeg: стр. 246 текстом, низ экрана
    // пустой - обычный текст ниже глифов). Раньше шрифт больше не просили до
    // перезахода; теперь повторяем через 4, 15, 45 с и при возврате сети.
    // Получилось - лист перерисовывается глифами на месте. Сбой - в журнал.
    loadV4Fonts(data).then(function () { reveal(false); }, function () {
      reveal(true);
      trail('v4_font_fail', { p: data.page });
      var done = false;
      var retry = function () {
        if (done || currentPageData !== data) return;
        loadV4Fonts(data).then(function () {
          if (done || currentPageData !== data) return;
          done = true;
          window.removeEventListener('online', retry);
          trail('v4_font_retry_ok', { p: data.page });
          reveal(false);
        }, function () {});
      };
      [4000, 15000, 45000].forEach(function (ms) { setTimeout(retry, ms); });
      window.addEventListener('online', retry);
    });

    document.getElementById('btn-prev').disabled = data.page >= LAST_PAGE;
    document.getElementById('btn-next').disabled = data.page <= FIRST_PAGE;
    document.getElementById('tb-prev').disabled = data.page >= LAST_PAGE;
    document.getElementById('tb-next').disabled = data.page <= FIRST_PAGE;

    renderWordsList(data);
    renderMeaning(data);
  }

  // Тап по слову на странице чтения - быстрый перевод во всплывающей
  // подсказке (28.08.2026, добавлено ПОВЕРХ вкладки "Слова" ниже, не
  // вместо неё - вкладка остаётся для вдумчивого разбора, подсказка - для
  // мгновенного взгляда без переключения экрана). Один слушатель на
  // контейнер (делегирование) - работает и после innerHTML-замены при
  // смене страницы, не нужно перевешивать на каждое слово заново.
  var wordPopup = document.getElementById('word-popup');
  var popupHideTimer = null;
  /* Попап центрируется по слову (translate(-50%,-100%)), поэтому у края
     экрана половина его уезжала за границу и перевод обрезался - в арабском
     это происходит постоянно, ведь конец строки здесь ЛЕВЫЙ край
     (06.09.2026, поймано пользователем на скриншоте). Прижимаем к экрану:
     стрелки-указателя у попапа нет, так что сдвиг вбок ничего не ломает - он
     просто перестаёт быть ровно по центру слова.

     Сверху та же беда на первой строке: там показываем попап ПОД словом. */
  var POPUP_MARGIN = 8;

