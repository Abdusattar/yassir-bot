  // ── Режим заучивания 40+40 (01.09.2026) ───────────────────────────────
  // Порядок и вид повторяют то, к чему студенты привыкли в стороннем
  // приложении (materials/7f.jpeg): один тап — строчка выделена, переход
  // подсвечен на следующей строке, дальше повторы. Счётчиков 40 нет
  // намеренно — студент считает сам, руками (решение пользователя).
  // unit — что выбирается ПРЯМО СЕЙЧАС на экране выбора места: строка,
  // половина листа или вся страница (02.09.2026). Это не то же, что stage:
  // stage — где студент по методике, unit живёт только на время выбора и
  // по умолчанию всегда 'line' (кто не вникает — тапает строку, как
  // раньше).
  var hifz = { on: false, line: null, stage: 1, picking: false, unit: 'line' };
  var HIFZ_PROGRESS_TARGET = 80;

  // Правило переходного слова (решение пользователя 01.09.2026): строка
  // читается не до своего конца, а ДО НАЧАЛА СЛЕДУЮЩЕЙ. Сколько слов
  // захватить — считается, а не берётся всегда по одному:
  //   • первое слово следующей строки;
  //   • если в нём 3 буквы или меньше без огласовок (предлог, местоимение,
  //     частица) — добавляем второе;
  //   • если на нём заканчивается аят — добавляем ещё одно;
  //   • потолок три слова, чтобы «переход» не стал полстрокой.
  var HIFZ_HARAKAT = /[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]/g;
  function hifzBaseLen(html) {
    return String(html).replace(/<[^>]+>/g, '').replace(HIFZ_HARAKAT, '').length;
  }

  function hifzTextLines() {
    if (!currentPageData) return [];
    // Пустые строки-заглушки в конце стр. 1 и 2 не в счёт (23.09.2026), как
    // и в page_text_line_count на сервере: иначе половины листа съезжают.
    return (currentPageData.lines || []).filter(function (l) {
      return l.type === 'text' && l.tokens && l.tokens.length;
    });
  }

  /* Сколько ПЕРВЫХ ТОКЕНОВ следующей строки составляют переход. Считаем в
     токенах, а не в словах: между словами может стоять знак конца аята, и
     подсветить надо всё подряд, без дырки. */
  /* Строки СЛЕДУЮЩЕЙ страницы — переход с последней строчки уходит туда.
     Правило перехода границ страницы не знает: строка всё равно читается до
     начала следующей, а следующая может быть уже на другом листе (поймано
     пользователем 01.09.2026 на 15-й строчке 15-й страницы). */
  // layout - раскладка, в которой взят следующий лист (23.09.2026): после
  // смены раскладки переход должен браться из её листа, а не из старого.
  var hifzNextPage = { page: null, lines: null, layout: null };

  function hifzFetchNextPage() {
    var want = currentPage + 1;
    var lay = pageLayout();
    if (want > LAST_PAGE || (hifzNextPage.page === want && hifzNextPage.layout === lay)) return;
    hifzNextPage.page = want;
    hifzNextPage.layout = lay;
    hifzNextPage.lines = null;
    // Тот же загрузчик, что у loadPage (переводы слов - 034_wbw_words.js).
    fetchPageData(want)
      .then(function (data) {
        if (hifzNextPage.page !== want || hifzNextPage.layout !== lay) return;
        hifzNextPage.lines = (data.lines || []).filter(function (l) { return l.type === 'text'; });
        // Данные пришли позже отрисовки — обновляем то, что уже на экране.
        if (hifz.on) hifzApply();
        if (document.getElementById('hifz-big').classList.contains('visible')) hifzBigRender();
      })
      .catch(function () {});
  }

  /* Откуда брать переход для строки lineIdx: следующая строка этой же
     страницы или первая строка следующей. null — если данных ещё нет.

     foreign=true означает «строка с ДРУГОГО листа». Это важно при
     отрисовке: code_v4 — не юникод, а номера глифов ВНУТРИ шрифта своей
     страницы, а шрифт у каждой страницы свой. Нарисовать коды 16-й
     страницы шрифтом 15-й = показать чужие буквы (поймано пользователем
     02.09.2026; ровно тот же класс бага, что чинили 01.09 — «305 слов
     чужим шрифтом»). Поэтому чужую строку рисуем из t.html — настоящий
     арабский юникод — обычным Scheherazade. */
  function hifzTailLine(lineIdx) {
    var lines = hifzTextLines();
    if (lineIdx + 1 < lines.length) return { line: lines[lineIdx + 1], foreign: false };
    if (hifzNextPage.page === currentPage + 1 && hifzNextPage.layout === pageLayout() &&
        hifzNextPage.lines && hifzNextPage.lines.length) {
      return { line: hifzNextPage.lines[0], foreign: true };
    }
    hifzFetchNextPage();
    return null;
  }

  /* Слово для крупного экрана: тот же выбор шрифта, что у перехода, плюс
     перевод в data-tr — на «Крупно» тап по слову показывает подсказку, как
     и на самой странице (просьба пользователя 02.09.2026: «повторяешь и
     иногда забыл — хочется глянуть перевод, не выходя»). */
  function hifzBigWord(token, foreign) {
    var tr = token.translation ? ' data-tr="' + escapeAttr(token.translation) + '"' : '';
    // data-ma - удержание открывает смысл аята и в «Крупно» (02.11.2026).
    var ma = token.surah ? ' data-ma="' + token.surah + ':' + token.ayah + '"' : '';
    // Шрифт листа не загрузился (data-plain) - глифы V4 здесь были бы чужими
    // словами, как на самом листе: обычный текст.
    var plain = foreign || document.getElementById('ayah-text').hasAttribute('data-plain');
    var glyph = plain ? String(token.html || '').replace(/<[^>]*>/g, '') : (token.code_v4 || token.html);
    var cls = foreign ? 'tail-plain' : (plain ? '' : v4Cls(token));
    return '<span class="' + cls + '"' + ma + tr + '>' + glyph + '</span>';
  }

  function hifzTailTokens(lineIdx) {
    var src = hifzTailLine(lineIdx);
    var next = src && src.line;
    if (!next || !next.tokens) return 0;
    var taken = 0, lastTokenIdx = -1;
    for (var i = 0; i < next.tokens.length && taken < 3; i++) {
      var t = next.tokens[i];
      if (t.type !== 'word') continue;
      taken++;
      lastTokenIdx = i;
      if (taken === 1 && hifzBaseLen(t.html) > 3) {
        // Слово нормальной длины — хватит одного, но проверим конец аята.
        var after = next.tokens[i + 1];
        if (!after || after.type !== 'ayah_end') break;
      } else if (taken >= 2) {
        var after2 = next.tokens[i + 1];
        if (!after2 || after2.type !== 'ayah_end') break;
      }
    }
    return lastTokenIdx + 1;
  }

  /* Поглощённая последняя строка (05.11.2026, Умар устаз): её ЦЕЛИКОМ
     съедает переход предпоследней - стр. 1 «وَلَا ٱلضَّآلِّينَ», стр. 2
     «هُمُ ٱلْمُفْلِحُونَ». Отдельной единицей этапа 1 она была бы теми же
     двумя словами по 40+40, поэтому входит в предыдущую строку. Индекс или
     -1. То же правило - hifz_absorbed_line на сервере. */
  function hifzAbsorbed() {
    var lines = hifzTextLines(), n = lines.length;
    if (n < 2) return -1;
    var words = 0, toks = lines[n - 1].tokens;
    for (var i = 0; i < toks.length; i++) if (toks[i].type === 'word') words++;
    var tail = hifzTailTokens(n - 2), taken = 0;
    for (var j = 0; j < tail && j < toks.length; j++) if (toks[j].type === 'word') taken++;
    return words && taken >= words ? n - 1 : -1;
  }
  // Строка-единица этапа 1: на поглощённой - предыдущая.
  function hifzUnitLine(line) {
    return line !== null && line === hifzAbsorbed() ? line - 1 : line;
  }
  // «строчка N из M» с учётом склейки: поглощённая строка не считается.
  function hifzLineOf(line) {
    var r = hifzHalfRange(hifzHalf(line)), ab = hifzAbsorbed();
    var m = r[1] - r[0] + 1 - (ab >= r[0] && ab <= r[1] ? 1 : 0);
    return T('hifz_line_of', { N: hifzUnitLine(line) - r[0] + 1, M: m });
  }

  /* Половины страницы: первая — floor(n/2) строк, вторая — остальные.
     На 15 строках это 7+8, ровно как в печатной раскладке. */
  function hifzHalf(lineIdx) {
    var n = hifzTextLines().length;
    return lineIdx < Math.floor(n / 2) ? 0 : 1;
  }
  function hifzHalfRange(half) {
    var n = hifzTextLines().length, mid = Math.floor(n / 2);
    return half === 0 ? [0, mid - 1] : [mid, n - 1];
  }

  var hifzShownUnit = null;
  function hifzApply() {
    var app = document.getElementById('app');
    app.classList.toggle('hifz', hifz.on);
    app.classList.toggle('hifz-pick', hifz.on && hifz.picking);
    app.classList.toggle('pick-line', hifz.picking && hifz.unit !== 'half');
    app.classList.toggle('pick-half', hifz.picking && hifz.unit === 'half');
    app.classList.toggle('hifz-s2', hifz.on && !hifz.picking && hifz.stage === 2);
    app.classList.remove('hifz-xt');
    var box = document.getElementById('ayah-text');
    Array.prototype.forEach.call(box.children, function (el) { el.classList.remove('hifz-off'); });
    var oldX = box.querySelector('.hifz-xtail');
    if (oldX) oldX.parentNode.removeChild(oldX);
    var allRows = document.querySelectorAll('#ayah-text .mushaf-line');
    // Пустые строки-заглушки (стр. 1 и 2 обеих раскладок, после текста) - не
    // строки заучивания (05.11.2026, Умар устаз): с ними последняя строка
    // стр. 2 «имела следующую» пустую на том же листе, и переход со стр. 3
    // не вставал; половина при выборе считалась по 13 строкам вместо 6.
    // Счёт тот же, что hifzTextLines и page_text_line_count на сервере.
    var rows = Array.prototype.filter.call(allRows, function (row) {
      return row.children.length > 0;
    });
    Array.prototype.forEach.call(allRows, function (row) {
      row.classList.remove('hifz-lit', 'hifz-dim', 'hifz-has-tail',
        'pick-half-a', 'pick-half-b', 'pick-half-first-b', 'pick-half-last-a');
      Array.prototype.forEach.call(row.children, function (sp) {
        sp.classList.remove('hifz-tail');
      });
    });
    // Выбор половины: красим строки двумя группами, чтобы лист сам показал,
    // где граница и куда тапать. Без этого студент видит обычную страницу и
    // не понимает, чего от него ждут.
    if (hifz.picking && hifz.unit === 'half') {
      var mid = Math.floor(rows.length / 2);
      Array.prototype.forEach.call(rows, function (row, idx) {
        row.classList.add(idx < mid ? 'pick-half-a' : 'pick-half-b');
        if (idx === mid - 1) row.classList.add('pick-half-last-a');
        if (idx === mid) row.classList.add('pick-half-first-b');
      });
    }
    if (!hifz.on || hifz.picking || hifz.line === null) return;

    var lit = [];
    if (hifz.stage === 1) {
      // Склейка (05.11.2026): единица предпоследней строки - вместе с
      // поглощённой последней, переход уже со следующего листа.
      var ul = hifzUnitLine(hifz.line);
      lit = ul !== hifz.line || hifzAbsorbed() === ul + 1 ? [ul, ul + 1] : [ul];
    }
    else if (hifz.stage === 2) {
      var r = hifzHalfRange(hifzHalf(hifz.line));
      for (var i = r[0]; i <= r[1]; i++) lit.push(i);
    } else {
      for (var j = 0; j < rows.length; j++) lit.push(j);
    }
    Array.prototype.forEach.call(rows, function (row, idx) {
      row.classList.add(lit.indexOf(idx) !== -1 ? 'hifz-lit' : 'hifz-dim');
    });
    // Переход — на строке, следующей за последней подсвеченной.
    var tailLine = lit[lit.length - 1] + 1;
    var tailCount = hifzTailTokens(lit[lit.length - 1]);
    if (tailCount && rows[tailLine]) {
      rows[tailLine].classList.remove('hifz-dim');
      rows[tailLine].classList.add('hifz-has-tail');
      for (var k = 0; k < tailCount && k < rows[tailLine].children.length; k++) {
        rows[tailLine].children[k].classList.add('hifz-tail');
      }
    }
    // На последней строчке листа переход физически на следующей странице —
    // подсветить на этом листе нечего. Отдельной полосы внизу больше нет
    // (02.09.2026): она отъедала место у самого мусхафа. С 22.09.2026
    // «Крупно» убрано, и переход с чужого листа встаёт отдельной строкой
    // под листом (.hifz-xtail) - на любом этапе, стоя и лёжа.
    var lastShown = tailCount && rows[tailLine] ? rows[tailLine] : rows[lit[lit.length - 1]];
    var xtail = false;
    if (tailCount && !rows[tailLine]) {
      var src = hifzTailLine(lit[lit.length - 1]);
      if (src && src.foreign) {
        var x = document.createElement('div');
        x.className = 'hifz-xtail';
        var xh = '';
        for (var q = 0; q < tailCount && q < src.line.tokens.length; q++) {
          var tk = src.line.tokens[q];
          if (tk.type !== 'word') continue;
          // Те же атрибуты, что у слова на листе: тап - перевод, двойной -
          // «Мои слова» (обработчик #ayah-text их и ждёт).
          var tr = tk.translation ? ' data-tr="' + escapeAttr(tk.translation) + '"' +
            ' data-surah="' + tk.surah + '" data-ayah="' + tk.ayah + '" data-pos="' + tk.position + '"' +
            ' data-arabic="' + escapeAttr(tk.html) + '"' +
            ' data-gl="' + escapeAttr(glossText(tk.translation)) + '"' : '';
          xh += '<span class="tail-plain"' + tr + '>' + tk.html + '</span>';
        }
        x.innerHTML = xh;
        // Сразу под последней строкой единицы, а не в конец листа: на стр. 1-2
        // за текстом идут пустые заглушки, и переход отъехал бы под них.
        var anchor = rows[lit[lit.length - 1]];
        box.insertBefore(x, anchor ? anchor.nextSibling : null);
        lastShown = x;
        xtail = true;
      }
    }
    // Всё вне своей единицы и перехода - .hifz-off: лёжа прячется, на
    // этапе 2 стоя становится пустым местом (CSS решает, что с ним делать).
    var firstLit = rows[lit[0]], inside = false;
    Array.prototype.forEach.call(box.children, function (el) {
      if (el === firstLit) inside = true;
      if (!inside) el.classList.add('hifz-off');
      if (el === lastShown) inside = false;
      else if (!inside && el !== firstLit) el.classList.add('hifz-off');
    });
    app.classList.toggle('hifz-xt', xtail);
    // Лёжа сменилась единица - показываем её с начала.
    var unitKey = currentPage + ':' + hifz.stage + ':' + lit[0];
    if (app.classList.contains('land') && unitKey !== hifzShownUnit) {
      document.getElementById('page-wrap').scrollTop = 0;
    }
    hifzShownUnit = unitKey;
    hifzHead();
  }

  function hifzHead() {
    // Счётчик живёт по тем же правилам, что шапка: место сменилось - число
    // тоже (11.09.2026).
    if (typeof hifzCountRender === 'function') setTimeout(hifzCountRender, 0);
    var n = hifzTextLines().length;
    var where = document.getElementById('hifz-where');
    var sub = document.getElementById('hifz-sub');
    var fix = document.getElementById('hifz-fix');
    /* Выход подписывается по режиму (07.09.2026, жалоба: «с разбора должна
       быть кнопочка назад, а то внизу другие кнопки»). Голый ✕ читается как
       «закрыть мусхаф», а не «вернуться в свои сдачи», - внизу же стоят
       «10 сек назад» и «Пересдать», и дороги обратно человек не видел.
       Ставим здесь, а не в lookOpen: hifzHead зовётся при каждой
       перерисовке и на всех выходах из разбора (в том числе через
       пересдачу), значит подпись сама возвращается к ✕. */
    var close = document.getElementById('hifz-close');
    /* Крестик и подписанный возврат - один элемент в двух ролях, поэтому
       сторону задаём здесь же (09.09.2026): возврат слева, закрытие
       справа. Класс висит на шапке - CSS переставляет её содержимое. */
    function hifzClose(label, isBack) {
      close.textContent = label;
      close.classList.toggle('back', isBack);
      document.getElementById('hifz-head').classList.toggle('closing', !isBack);
    }
    /* Шапка принадлежит РОЛИ, а не режиму (07.09.2026). У проверки своя:
       имя студента и группа. Раньше их вписывал reviewAfterRender поверх
       студенческой строки - и любой следующий hifzHead() (а его зовёт
       hifzApply при каждой перерисовке) возвращал туда "стр. 15 · строка 3
       из 8". Заодно здесь же снимается "поправить": у устаза она меняет
       ЕГО СОБСТВЕННОЕ место заучивания, а следующий тап по строке чужой
       сдачи сохранял бы его себе (hifzPickDone -> hifzSave -> POST /hifz). */
    if (typeof review !== 'undefined' && review.on && review.sub) {
      /* Выход из проверки - это ВОЗВРАТ в кабинет (hifzExit -> reviewClose),
         а не закрытие мусхафа, значит и подписан он должен быть так же, как
         разбор у студента (09.09.2026, общее правило навигации). Голый ✕
         тут читался как "закрыть", хотя уводит на прежнюю вкладку кабинета. */
      hifzClose(T('review_back'), true);
      where.textContent = review.sub.student_name || '';
      sub.textContent = review.sub.group_title || '';
      fix.style.display = 'none';
      return;
    }
    // Разбор: место называем так же, как в списке сдач, - студент должен
    // видеть, ЧТО он сдавал, а не только где на листе горит подсветка.
    if (typeof look !== 'undefined' && look.on && look.item) {
      hifzClose(T('look_back'), true);
      where.textContent = subsPlace(look.item);
      sub.textContent = T('look_sub');
      fix.style.display = 'none';
      return;
    }
    hifzClose('✕', false);
    if (hifz.picking) {
      // Шапка спрашивает ровно про ту единицу, что выбрана внизу — «укажи
      // этап» нигде не пишем, вопрос всегда конкретный (02.09.2026).
      var half = hifz.unit === 'half';
      where.textContent = half ? T('hifz_pick_half') : T('hifz_pick');
      // Место осталось на другом листе — без этой строки студент не поймёт,
      // куда делся его прогресс, и решит, что приложение забыло (02.09.2026).
      // Но НЕ вместо «тапни по…» (13.09.2026, Муслим из Н-1): на стр. 51 он
      // нажал «Половина», увидел только «место осталось на стр. 6», по листу
      // не тапнул и вышел через ✕ — ничего не сохранилось. Обе строки.
      var tapHint = half ? T('hifz_pick_half_sub') : T('hifz_pick_sub');
      sub.textContent = (hifzPointerPage && hifzPointerPage !== currentPage)
        ? tapHint + ' · ' + T('hifz_pick_sub_elsewhere', { N: hifzPointerPage })
        : tapHint;
    } else if (hifz.stage === 1) {
      where.textContent = T('page_n', { N: currentPage }) + ' · ' + hifzLineOf(hifz.line);
      sub.textContent = T('hifz_stage1');
    } else if (hifz.stage === 2) {
      var rr = hifzHalfRange(hifzHalf(hifz.line));
      where.textContent = T('page_n', { N: currentPage }) + ' · ' +
        T('hifz_lines_range', { A: rr[0] + 1, B: rr[1] + 1 });
      // Прогресс 40+40 (03.09.2026) - в ту же строку, что и раньше стоял
      // статичный "этап 2 — половина страницы, 40+40": она уже вне потока
      // мусхафа (chrome-бар), место текста Корана не трогает.
      sub.textContent = hifzProgressSubText(2, hifzHalf(hifz.line));
    } else {
      where.textContent = T('page_n', { N: currentPage }) + ' · ' + T('hifz_whole');
      sub.textContent = hifzProgressSubText(3, 0);
    }
    document.getElementById('hifz-submit-t').textContent = T('hifz_submit');
    document.getElementById('hifz-submit').disabled = hifz.picking;
    fix.textContent = T('hifz_fix');
    /* В пересдаче место не меняют: пересдаётся ровно то, что сдавал (так и
       написано студенту в подсказке, и того же требует сервер - гейт ищет
       сдачу той же единицы, иначе retake_pending). Со сменой места запись
       уходила бы не туда, а указатель на сервере успевал сдвинуться
       (hifzSave), и возврат hifzRetakeFinish чинил бы только экран. */
    fix.style.display = (hifz.picking || hifzRetakeMode) ? 'none' : '';
    var units = document.querySelectorAll('#hifz-units button');
    Array.prototype.forEach.call(units, function (b) {
      b.textContent = T('hifz_unit_' + b.getAttribute('data-unit'));
      b.classList.toggle('on', b.getAttribute('data-unit') === hifz.unit);
    });
  }

  function hifzSave() {
    if (hifz.line === null) return;
    hifzPointerPage = currentPage;
    apiCall('/hifz', { method: 'POST', body: {
      page: currentPage, line: hifz.line, stage: hifz.stage, layout: MUSHAF_LAYOUT
    } }).then(function (res) {
      trail('save', { p: currentPage, l: hifz.line, s: hifz.stage,
                      n: String(res.status) + (res.data && res.data.error ? ' ' + res.data.error : '') });
      // Шаг упёрся в стену пересдачи на сервере (устаревшая страница, или
      // долг прилетел прямо сейчас). Указатель там не сдвинулся - и здесь
      // ему двигаться незачем: ведём человека к долгам.
      if (res.data && res.data.error === 'retake_pending') {
        hifzDebt = { retakes: res.data.retakes || [], done: true };
        hifzExit();
        openSubs(true);
      }
    }).catch(function () {});
  }

  function hifzEnter() {
    /* Заучивание всегда начинается со СТРАНИЦЫ (10.09.2026, поймал
       пользователь). Тапнув 📖, стоя в «Смысле» или «Моих словах», человек
       оставался в сабвью: верхняя навигация никуда не девается, и содержимое
       сабвью показывалось внутри режима 40+40, где ему делать нечего.
       Нарочно так зайти или случайно - разницы нет, экран получался
       бессмысленный. */
    if (!document.getElementById('view-page').classList.contains('active')) {
      switchTab('page');
    }
    hifz.on = true;
    hifz.unit = 'line';   // выбор всегда открывается на строке
    // Указатель на другой странице — сами переходим туда и продолжаем с
    // сохранённого места. Раньше здесь просто переспрашивали строку с
    // подсказкой мелким текстом «твоё место осталось на стр. N» — этого
    // оказалось мало: студент подсказку не замечал и решал, что прогресс
    // пропал (поймано 02-03.09.2026 на живом студенте, Сатар из G2b).
    // loadPage → renderPage сама вызовет hifzApply()/hifzHead() после
    // отрисовки новой страницы (тот же путь, что при автопереходе на
    // следующую страницу в hifzNext()).
    if (hifzPointerPage && hifzPointerPage !== currentPage) {
      loadPage(hifzPointerPage);
      return;
    }
    if (hifz.line === null) hifz.picking = true;
    hifzApply();
    hifzHead();
  }
