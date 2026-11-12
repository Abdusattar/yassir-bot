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

  /* Пояснения к словам (12.11.2026): {"2:104:6": [текст, источник]}, только русские.
     Файл маленький, берём один раз при старте; нет сети - подсказка работает как раньше. */
  var wordNotes = null;
  fetch('notes/ru.json').then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) { wordNotes = d; }).catch(function () {});
  var wnOpenedAt = 0;
  function wordNoteClose() {
    document.getElementById('wn-dim').hidden = true;
    document.getElementById('wn-sheet').hidden = true;
  }
  function wordNoteOpen(n) {
    wordPopup.classList.remove('visible');
    document.getElementById('wn-word').textContent = n.ar;
    document.getElementById('wn-ref').textContent = n.key.split(':').slice(0, 2).join(':');
    document.getElementById('wn-gloss').textContent = n.gloss;
    document.getElementById('wn-text').textContent = n.note;
    document.getElementById('wn-from').textContent = n.src;
    document.getElementById('wn-dim').hidden = false;
    document.getElementById('wn-sheet').hidden = false;
    wnOpenedAt = Date.now();
    trail('word_note', { w: n.key });
  }
  wordPopup.addEventListener('click', function () {
    if (wordPopup._note) wordNoteOpen(wordPopup._note);
  });
  document.getElementById('wn-close').addEventListener('click', wordNoteClose);
  document.getElementById('wn-dim').addEventListener('click', function () {
    // То же касание, что открыло панель, на телефоне доходит сюда кликом - не закрываемся им.
    if (Date.now() - wnOpenedAt > 450) wordNoteClose();
  });

  function showPopupMessage(el, text, note) {
    wordPopup._note = note || null;
    wordPopup.classList.toggle('wn', !!note);
    wordPopup.textContent = text;
    if (note) {
      var more = document.createElement('span');
      more.className = 'wn-more';
      more.textContent = 'Подробнее';   // пояснения есть только на русском - строка не в словаре
      wordPopup.appendChild(more);
    }
    wordPopup.style.transform = 'translate(-50%, -100%)';
    wordPopup.classList.add('visible');

    // Мерить ОБЯЗАТЕЛЬНО на нулевой позиции: ширина у position:fixed
    // считается "сколько влезет от left до края экрана", и на прошлой
    // позиции у самого края попап меряется узким (текст переносится). По
    // такой ширине клампинг промахивается - ровно так первая версия этого
    // фикса всё ещё выпускала попап за экран на первой строке.
    wordPopup.style.left = '0px';
    var rect = el.getBoundingClientRect();
    var pop = wordPopup.getBoundingClientRect();
    var half = pop.width / 2;
    var center = rect.left + rect.width / 2;
    var maxCenter = window.innerWidth - half - POPUP_MARGIN;
    var minCenter = half + POPUP_MARGIN;
    // Если попап шире экрана, minCenter окажется больше maxCenter - тогда
    // важнее не обрезать начало текста, поэтому побеждает левый край.
    center = Math.min(Math.max(center, minCenter), Math.max(maxCenter, minCenter));

    var top = rect.top - POPUP_MARGIN;
    if (top - pop.height < POPUP_MARGIN) {
      top = rect.bottom + POPUP_MARGIN;
      wordPopup.style.transform = 'translate(-50%, 0)';
    }

    wordPopup.style.left = center + 'px';
    wordPopup.style.top = top + 'px';
    clearTimeout(popupHideTimer);
    popupHideTimer = setTimeout(function () {
      wordPopup.classList.remove('visible');
    }, note ? 4000 : 1800);   // со строкой «Подробнее» - дольше: её ещё надо успеть нажать
  }
  /* Пары слов с одним переводом (28.09.2026, Имран устаз: «أَنصَحَ - тап,
     перевод не выходит»). Источник переводит устойчивое сочетание целиком и
     кладёт перевод на первое слово («أَنْ» - «посоветовать»), следующее
     остаётся пустым (раньше там была «*»). Пустое слово сразу за головой в
     том же аяте - её хвост: тап по любому из них подсвечивает всю пару и
     показывает общий перевод, двойной тап кладёт в «Мои слова» голову
     (сервер сам приклеит арабский хвоста - _merge_tail_arabic). Хвост на
     следующем листе остаётся без перевода, как раньше. */
  function glossText(s) {
    s = s.replace(/\s*\([^)]*\)\s*/g, ' ').replace(/[«»"]/g, '').replace(/\s+/g, ' ').trim();
    return s.replace(/[A-Za-zА-Яа-яЁёӨөҮүҢң]{5,}/g, glossHyph);
  }
  // Мягкие переносы в подписи (30.10.2026): в тесном ряду подпись сужается,
  // и длинное слово переносится через дефис. Свои, а не hyphens:auto - тому
  // нужен lang (у листа он ar) и словарь, которого для ky/uz нет. Правило
  // простое: разрыв перед согласной, за которой гласная (ми-ло-сер-дный
  // примерно так), слева и справа не меньше двух букв и есть гласная.
  var GL_VOW = /[аеёиоуыэюяөүaeiouАЕЁИОУЫЭЮЯӨҮAEIOU]/;
  function glossHyph(w) {
    var out = w.charAt(0), vow = GL_VOW.test(w.charAt(0));
    for (var i = 1; i < w.length; i++) {
      var ch = w.charAt(i);
      if (vow && i >= 2 && i <= w.length - 2 && !GL_VOW.test(ch) && !/[ьъйЬЪЙ]/.test(ch) &&
          GL_VOW.test(w.charAt(i + 1))) out += '­';
      out += ch;
      if (GL_VOW.test(ch)) vow = true;
    }
    return out;
  }

  function mushafPairs(lines) {
    var tails = {}, head = null, lastPos = null;
    lines.forEach(function (line) {
      (line.tokens || []).forEach(function (t) {
        if (t.type !== 'word') return;
        if (t.translation) {
          head = t;
        } else if (head && head.surah === t.surah && head.ayah === t.ayah && lastPos !== null &&
                   t.position === lastPos + 1) {
          tails[t.surah + ':' + t.ayah + ':' + t.position] = head;
        } else {
          head = null;
        }
        lastPos = t.position;
      });
    });
    return tails;
  }

  var wordHlTimer = null;
  function highlightWordGroup(el) {
    var box = document.getElementById('ayah-text');
    Array.prototype.forEach.call(box.querySelectorAll('.w-hl'), function (x) { x.classList.remove('w-hl'); });
    var key = el.getAttribute('data-head') || el.getAttribute('data-w');
    if (!key) return;
    var group = box.querySelectorAll('[data-w="' + key + '"], [data-head="' + key + '"]');
    Array.prototype.forEach.call(group, function (x) { x.classList.add('w-hl'); });
    clearTimeout(wordHlTimer);
    wordHlTimer = setTimeout(function () {
      Array.prototype.forEach.call(group, function (x) { x.classList.remove('w-hl'); });
    }, 1800);
  }

  function showWordPopup(el) {
    // В режиме проверки тап по слову - это ПОМЕТКА ОШИБКИ, а не перевод:
    // устаз здесь не читает, а отмечает (04.09.2026).
    if (review.on) {
      var row = el.parentNode;
      var line = parseInt(row.getAttribute('data-line'), 10);
      var idx = Array.prototype.indexOf.call(row.children, el);
      if (isNaN(line) || idx < 0) return;
      var key = reviewKey(line, idx);
      review.words[key] = !review.words[key];
      el.classList.toggle('err', !!review.words[key]);
      reviewHint();
      return;
    }
    var text = el.getAttribute('data-tr');
    if (text) {
      var note = null;
      var wkey = el.getAttribute('data-w') || el.getAttribute('data-head');
      if (UI_LANG === 'ru' && wordNotes && wkey && wordNotes[wkey] && el.closest('#ayah-text')) {
        // Арабское слово - обычным текстом: в самом листе оно набрано глифами шрифта страницы.
        var tmp = document.createElement('div');
        tmp.innerHTML = el.getAttribute('data-arabic') || '';
        note = { key: wkey, ar: tmp.textContent, gloss: text, note: wordNotes[wkey][0], src: wordNotes[wkey][1] };
      }
      showPopupMessage(el, text, note);
      if (el.closest('#ayah-text')) highlightWordGroup(el);
    }
  }

