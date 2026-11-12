  /* ─── Сдача 40+40: запись, прослушивание себя, отправка ────────────────
     Устаз получает в группе картинку прочитанного места и голосовое —
     принимает привычным реплаем, как обычную голосовую сдачу.

     Картинку рисуем ЗДЕСЬ, на canvas: настоящий шрифт V4 (свой на каждую
     страницу) есть только у клиента, на сервере рендер пословный и другим
     шрифтом — устаз увидел бы не то, что видел студент. */
  /* Предел записи. Было 10 минут - и в него РЕАЛЬНО упирались: замер сдач
     06.09.2026 показал пять записей ровно по 599.8-600.3 сек, один студент
     (Рауф) налетел трижды. Читает дольше десяти минут - запись обрывалась на
     полуслове, а устазу приходила неполная сдача.

     30 минут упираются в 7 МБ при нашем битрейте (замерено: 4.05 КБ/сек), а
     предел загрузки на сервере - 20 МБ (HIFZ_MAX_UPLOAD_BYTES), так что
     техническое ограничение тут не десять минут и никогда им не было.

     Совсем без предела нельзя: забытая включённой запись копит чанки в
     памяти телефона, пока он не начнёт задыхаться. */
  /* 16.09.2026: два часа вместо тридцати минут. Повторение у младших идёт от
     начала Аль-Бакары до их места, и оно растёт с каждой страницей: на стр. 30
     это уже около часа чтения, и 30 минут обрывали работу на середине.
     Решение пользователя - читать всё, прерываясь «Паузой». Цепочка расшита
     под этот предел: 120 мин ≈ 29 МБ при 4,05 КБ/сек, загрузка 40 МБ
     (HIFZ_MAX_UPLOAD_BYTES), nginx 45 МБ, перекодировка 600 сек. */
  var HIFZ_REC_MAX_MS = 120 * 60 * 1000;
  // За сколько до предела предупредить. Молчаливый обрыв - это потерянная
  // работа: студент дочитывает, не зная, что его уже не пишут.
  var HIFZ_REC_WARN_MS = 2 * 60 * 1000;
  /* Короче двух секунд - это не сдача, а промах по кнопке (13.09.2026).
     Устазу такие обрывки уходили как полноценная работа. */
  var HIFZ_REC_MIN_MS = 2000;
  // Минимум по объёму (17.09.2026) - тот же, что на сервере (HIFZ_MIN_SEC в
  // core/mufradat_bot.py): треть самого быстрого настоящего чтения.
  var HIFZ_MIN_SEC = { 1: 3, 2: 20, 3: 40 };
  // Запись на телефоне короче таймера - на столько секунд и такую долю.
  function recLostTail(sec, ms) {
    if (!sec || !isFinite(sec) || !ms) return false;
    var exp = ms / 1000;
    return exp - sec >= 5 && sec < 0.8 * exp;
  }
  // В плеере лежит только текущий поток, а таймер после продолжения
  // прерванного чтения идёт с начитанного раньше (23.09.2026, Азиля из
  // группы Мохидиль: 548 с на таймере, 267 с в плеере - полная запись ни разу
  // не ушла). Сравниваем плеер только с тем, что записано в этом потоке.
  function recSegMs(ms, baseMs) {
    return Math.max(0, (ms || 0) - (baseMs || 0));
  }
  var rec = { mr: null, chunks: [], blob: null, url: null, t0: 0, tick: null, stream: null,
              mode: null,     // mode: null - сдача 40+40, 'revision' - запись повторения
              // Сегмент - один поток MediaRecorder. Продолжение после обрыва
              // начинает новый, поэтому куски нумеруются (20.09.2026).
              seg: 0, saved: [],
              // Охват записи повторения (24.09.2026): страница, где нажали
              // «Записать», самая дальняя за время записи и раскладка книги.
              pageFrom: null, pageMax: null, pageLayout: null };

  function hifzSubmitLines() {
    var lines = hifzTextLines();
    if (hifz.stage === 1) return [hifz.line];
    if (hifz.stage === 2) {
      var r = hifzHalfRange(hifzHalf(hifz.line)), out = [];
      for (var i = r[0]; i <= r[1]; i++) out.push(i);
      return out;
    }
    var all = [];
    for (var j = 0; j < lines.length; j++) all.push(j);
    return all;
  }

  /* t.html — разметка ДЛЯ innerHTML (теги <tajweed class=...>, красит цвет
     прямо в браузере), не голый текст. Везде она и уходит через innerHTML —
     кроме canvas: там fillText рисует теги буквально как символы, а не
     парсит их (поймано пользователем 02.09.2026 на картинке сдачи, где
     переход берётся с чужой страницы через t.html). */
  function hifzPlainText(html) {
    return (html || '').replace(/<[^>]+>/g, '');
  }

  function hifzLinesToPng(lineIdxs) {
    var lines = hifzTextLines();
    var scale = 2, size = 42, lh = size * 1.9, pad = 20;
    var rows = lineIdxs.map(function (idx) {
      var l = lines[idx];
      return {
        text: (l && l.tokens) ? l.tokens.map(function (t) { return t.code_v4 || ''; }).join(' ') : '',
        font: 'mushaf-v4',
        // Слова со вторым шрифтом листа (раскладка Дар аль-Маариф, t.fp):
        // одной строкой fillText их не нарисовать - строка идёт кусками.
        parts: (l && l.tokens && l.tokens.some(function (t) { return t.fp; })) ? l.tokens.map(function (t) {
          return { text: t.code_v4 || '', font: t.fp ? 'mushaf-v4-b' : 'mushaf-v4' };
        }) : null
      };
    });
    // Переходное слово студент читает следом за единицей — тем же тапом,
    // что подсвечивает его на самой странице и в «Крупно». Картинка сдачи
    // была единственным местом, где его забыли: устаз получал скрин, где
    // текст обрывался ровно на последней строке единицы, хотя в записи
    // переход уже прозвучал (поймал пользователь 02.09.2026).
    var lastIdx = lineIdxs[lineIdxs.length - 1];
    var tailCount = hifzTailTokens(lastIdx);
    if (tailCount) {
      var src = hifzTailLine(lastIdx);
      if (src && src.line && src.line.tokens) {
        var toks = src.line.tokens.slice(0, tailCount);
        rows.push({
          // Тот же капкан с чужим шрифтом, что и везде: чужая страница —
          // t.html обычным Scheherazade, не глифы V4 текущей страницы. И
          // html — это разметка тегами, canvas её не парсит, нужен голый
          // текст (hifzPlainText).
          text: toks.map(function (t) {
            return src.foreign ? hifzPlainText(t.html) : (t.code_v4 || '');
          }).join(' '),
          font: src.foreign ? "'Scheherazade New'" : 'mushaf-v4',
          parts: (!src.foreign && toks.some(function (t) { return t.fp; })) ? toks.map(function (t) {
            return { text: t.code_v4 || '', font: t.fp ? 'mushaf-v4-b' : 'mushaf-v4' };
          }) : null,
          tail: true
        });
      }
    }
    var canvas = document.createElement('canvas');
    var ctx = canvas.getContext('2d');
    var maxW = 0;
    function rowWidth(r) {
      if (!r.parts) { ctx.font = size + 'px ' + r.font; return ctx.measureText(r.text).width; }
      var w = 0;
      r.parts.forEach(function (p, i) {
        ctx.font = size + 'px ' + p.font;
        w += ctx.measureText(p.text).width + (i ? ctx.measureText(' ').width : 0);
      });
      return w;
    }
    rows.forEach(function (r) { maxW = Math.max(maxW, rowWidth(r)); });
    canvas.width = Math.ceil((maxW + pad * 2) * scale);
    canvas.height = Math.ceil((rows.length * lh + pad * 2) * scale);
    ctx.scale(scale, scale);
    ctx.fillStyle = '#fbf8f0';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.direction = 'rtl';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'alphabetic';
    rows.forEach(function (r, i) {
      // Палитру таджвида canvas не поддерживает (font-palette только в
      // CSS) — глифы рисуются базовым цветом, для сверки «что читал»
      // этого достаточно. Переходное слово чуть светлее — та же логика
      // приглушения, что и на самой странице, чтобы устазу было видно,
      // где кончается единица и начинается переход.
      ctx.fillStyle = r.tail ? '#8a8370' : '#1c1710';
      if (r.parts) {
        var x = maxW + pad;
        r.parts.forEach(function (p) {
          ctx.font = size + 'px ' + p.font;
          ctx.fillText(p.text, x, pad + lh * (i + 0.75));
          x -= ctx.measureText(p.text).width + ctx.measureText(' ').width;
        });
        return;
      }
      ctx.font = size + 'px ' + r.font;
      ctx.fillText(r.text, (maxW + pad), pad + lh * (i + 0.75));
    });
    return new Promise(function (resolve) {
      canvas.toBlob(function (b) { resolve(b); }, 'image/png');
    });
  }

  /* ─── Начитанное живёт на телефоне (20.09.2026) ───────────────────────
     Запись раньше копилась только в памяти вкладки и становилась файлом
     по «Стоп». Telegram перезапускает вкладку - при сворачивании, повороте,
     нехватке памяти - и восемь минут чтения исчезали (живой случай Бекхана
     из G-10, у него же «⚠ коротко» на половине записей).

     Теперь MediaRecorder отдаёт кусок каждые пять секунд, и каждый кусок
     сразу ложится в IndexedDB. Куски ОДНОГО потока вместе дают исправный
     файл; продолжение после обрыва - это новый поток, поэтому у него свой
     номер сегмента, а сшивает их сервер (ffmpeg concat).

     Всё это только для повторения: у сдачи 40+40 записи короткие, а место
     (страница, строка, этап) после перезапуска пришлось бы ещё и угадывать. */
  var REC_DB_NAME = 'yassir-rec', REC_STORE = 'parts';
  var REC_KEEP_MS = 18 * 3600 * 1000;   // старше - это вчерашнее чтение
  var REC_SLICE_MS = 5000;

  function recDb() {
    return new Promise(function (resolve, reject) {
      if (!window.indexedDB) { reject(); return; }
      var req = indexedDB.open(REC_DB_NAME, 1);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(REC_STORE)) {
          db.createObjectStore(REC_STORE, { keyPath: 'id', autoIncrement: true });
        }
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  function recStoreDo(mode, fn) {
    return recDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(REC_STORE, mode);
        var out = fn(tx.objectStore(REC_STORE));
        tx.oncomplete = function () { db.close(); resolve(out && out.result !== undefined ? out.result : out); };
        tx.onerror = function () { db.close(); reject(tx.error); };
      });
    });
  }

  /* Место записи: у повторения оно одно на всех («с начала Аль-Бакары»), у
     сдачи 40+40 - страница, строка и этап. Продолжать можно только там же,
     иначе чтение одной страницы допишется к другой. */
  function recPlace() {
    // Разбор устаза - короткая реплика поверх чужой сдачи, продолжать в ней
    // нечего, и путать её с чтением студента нельзя.
    if (typeof reviewCommentMode !== 'undefined' && reviewCommentMode) return null;
    if (rec.mode === 'revision') return 'revision';
    // Первый этап - одна строчка, секунды чтения: оборвалось - проще
    // перечитать, чем продолжать (21.09.2026, решение пользователя).
    if (hifz.stage === 1) return null;
    return 'hifz:' + currentPage + ':' + hifz.line + ':' + hifz.stage +
           (hifzRetakeMode ? ':retake' : '');
  }

  function recPartSave(seg, blob, ms) {
    var place = recPlace();
    if (!place) return Promise.resolve();
    return recStoreDo('readwrite', function (st) {
      st.add({ seg: seg, at: Date.now(), ms: ms, blob: blob, place: place,
               pf: rec.pageFrom, pm: rec.pageMax, lay: rec.pageLayout });
    }).catch(function () { /* нет места или приватный режим - живём как раньше */ });
  }

  /* Самая дальняя страница за время записи повторения (24.09.2026) - конец
     охвата в подписи устазу. Считаем только пока диктофон идёт: листание до
     «Записать» и после «Стоп» к чтению не относится. */
  function recTrackPage(n) {
    if (rec.mode !== 'revision' || !rec.pageFrom) return;
    if (!rec.mr || rec.mr.state === 'inactive') return;
    if (n > rec.pageMax) rec.pageMax = n;
  }
  window.__recSpan = function () { return [rec.pageFrom, rec.pageMax]; };   // для стенда проверок

  function recPartsLoad() {
    var place = recPlace();
    if (!place) return Promise.resolve([]);
    return recStoreDo('readonly', function (st) { return st.getAll(); })
      .then(function (rows) {
        var all = rows || [];
        // Вчерашнее и чужое место не предлагаем и не храним: начитанное
        // относится к одному чтению, а не к телефону вообще.
        var stale = all.some(function (r) {
          return Date.now() - r.at >= REC_KEEP_MS || (r.place || 'revision') !== place;
        });
        if (stale) recPartsWipe();
        var mine = all.filter(function (r) {
          return Date.now() - r.at < REC_KEEP_MS && (r.place || 'revision') === place;
        });
        mine.sort(function (a, b) { return a.seg - b.seg || a.id - b.id; });
        return stale ? [] : mine;
      }).catch(function () { return []; });
  }

  function recPartsWipe() {
    return recStoreDo('readwrite', function (st) { st.clear(); })
      .catch(function () { /* нечего чистить */ });
  }

  /* Куски одного сегмента - один файл. Сервер получит их как audio, audio1,
     audio2 и сошьёт (core/mufradat_bot.py: transcode_parts_to_ogg). */
  function recSegments(rows) {
    var out = [], cur = null, seg = null;
    rows.forEach(function (r) {
      if (r.seg !== seg) { cur = []; out.push(cur); seg = r.seg; }
      cur.push(r.blob);
    });
    return out.map(function (blobs) {
      return new Blob(blobs, { type: blobs[0] ? blobs[0].type : 'audio/webm' });
    });
  }

  function recSavedMs(rows) {
    // В каждом куске лежит время на момент записи - после обрыва это
    // единственный след того, сколько человек начитал. Время НАКОПЛЕННОЕ
    // (hifzRecElapsed идёт через все сегменты), поэтому берём наибольшее, а
    // не сумму по сегментам (30.09.2026, Азиля из группы Мохидил: сумма
    // удваивала таймер после продолжения - 1227 с стали 2291, и сервер
    // отверг 18 минут настоящего чтения как «короче таймера»).
    return rows.reduce(function (m, r) { return Math.max(m, r.ms || 0); }, 0);
  }

  function hifzRecRelease() {
    if (rec.stream) { rec.stream.getTracks().forEach(function (t) { t.stop(); }); rec.stream = null; }
  }

  /* Экран не должен гаснуть, пока человек читает (20.09.2026). Запись живёт
     в памяти вкладки и становится файлом только по «Стоп»: уснул экран,
     Telegram перезапустил вкладку - и восьми минут чтения нет. Живой случай
     Бекхана из G-10, и те же обрывки у других детей.

     Замок теряется, когда вкладка уходит в фон, поэтому берём его заново при
     возвращении (см. слушателя ниже). Поддерживается не везде - там, где
     API нет, молча живём как раньше. */
  function hifzWakeOn() {
    if (rec.wake || !navigator.wakeLock) return;
    try {
      navigator.wakeLock.request('screen').then(function (lock) {
        rec.wake = lock;
        lock.addEventListener('release', function () { rec.wake = null; });
      }).catch(function () { rec.wake = null; });
    } catch (e) { rec.wake = null; }
  }

  function hifzWakeOff() {
    if (!rec.wake) return;
    try { rec.wake.release(); } catch (e) { /* уже отпущен */ }
    rec.wake = null;
  }

  function hifzRecActive() {
    return !!(rec.mr && (rec.mr.state === 'recording' || rec.mr.state === 'paused'));
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && hifzRecActive()) hifzWakeOn();
  });

