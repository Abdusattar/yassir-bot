  // ── Тренажёр муфрадата в вебе (29.08.2026) ────────────────────────────
  // API - в ТОМ ЖЕ процессе бота (core/mufradat_api.py), свой порт на
  // мужского/женского бота (два процесса на сервере, см. config.py:
  // MUFRADAT_API_PORT) - nginx разводит по префиксу пути /api/muf/<bot>/,
  // поэтому фронтенду нужно знать профиль (?bot=male|female в ссылке,
  // подставляется ботом - core/handlers.py:/mushaf,/yassirapp).
  // Функция, не var (03.09.2026) - объявления функций хойстятся ЦЕЛИКОМ,
  // с телом, в отличие от var (только имя, не присваивание). Раньше
  // apiCall() читал var API_BASE, присвоенный на этой же строке файла -
  // любой код ВЫШЕ неё (hifzPointerLoaded, синхронизация языка при
  // старте) на самом деле вызывался раньше присваивания и получал
  // "undefined" вместо базы: живой случай - "GET /undefined/hifz" и
  // "GET /undefined/lang" в логе nginx, оба чинены точечно через
  // setTimeout(fn, 0) (см. комментарии у обоих мест) - те правки не
  // тронуты, они безвредны, здесь закрывается сам КЛАСС ошибки, чтобы
  // следующий такой вызов, где бы он в файле ни стоял, просто работал.
  // Профиль (какой из двух процессов бота отвечает) внутри Telegram
  // приходит параметром ?bot= из кнопки меню, а на сайте берётся из
  // сессии: там адрес чистый, и подставить чужой профиль рукой в строке
  // браузера нельзя - сервер всё равно ищет токен в СВОЕЙ базе и чужого
  // не найдёт (10.09.2026).
  function apiBase() {
    var profile = (new URLSearchParams(window.location.search)).get('bot')
      || (webAuth && webAuth.profile) || 'male';
    return '/api/muf/' + profile;
  }

  /* Звук старым iPhone (28.09.2026). Голосовые у нас ogg/opus, Safari играет
     их только с iOS 18.4. Сервер сам отдаёт mp3 по версии iOS
     (core/audio_compat.py) - это страховка на случай, когда версия не
     угадалась: телефон ответил на play() NotSupportedError - один раз
     берём тот же звук в mp3 и запоминаем, что этому телефону нужен mp3.
     Другие отказы (NotAllowedError - запрет автозапуска) флаг не трогают. */
  var AUDIO_MP3_KEY = 'yassir_audio_mp3';
  var audioMp3 = false;
  try { audioMp3 = localStorage.getItem(AUDIO_MP3_KEY) === '1'; } catch (e) {}

  function audioFetch(path) {
    return fetch(apiBase() + path + (audioMp3 ? '&fmt=mp3' : ''), {
      headers: authHeaders()
    }).then(function (r) {
      if (!r.ok) throw new Error('audio');
      return r.blob();
    });
  }

  /* Звук потоком (10.10.2026: устазы ждали длинные 40+40 - запись качалась
     целиком перед каждым прослушиванием). Сервер на ?link=1 даёт подписанный
     адрес недельной копии, <audio> играет его, пока докачивается, и
     перематывает кусками. Копии нет или поток однажды не заиграл
     (audioStreamOff) - прежний путь: fetch целиком и blob.
     Отдаёт строку для el.src; revokeObjectURL на ней безвреден. */
  var audioStreamOff = false;
  function audioSource(path) {
    var blob = function () {
      return audioFetch(path).then(function (b) { return URL.createObjectURL(b); });
    };
    if (audioStreamOff) return blob();
    return fetch(apiBase() + path + '&link=1', { headers: authHeaders() })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; })
      .then(function (d) { return d && d.url ? apiBase() + d.url : blob(); });
  }

  // play() с одной попыткой в mp3; reload заново кладёт звук в el
  // (там, где blob держится на карточке, - сбросив его).
  function audioPlay(el, reload) {
    return el.play().catch(function (e) {
      // Не заиграл поток - не mp3 виноват: дальше качаем целиком.
      if (el.src && el.src.indexOf('blob:') !== 0 && !audioStreamOff) {
        audioStreamOff = true;
        trail('audio', { n: 'stream off ' + ((e && e.name) || '?') });
        return reload().then(function () { return el.play(); });
      }
      if (!e || e.name !== 'NotSupportedError' || audioMp3) throw e;
      audioMp3 = true;
      try { localStorage.setItem(AUDIO_MP3_KEY, '1'); } catch (e2) {}
      return reload().then(function () { return el.play(); });
    });
  }

  function audioReload(el, path) {
    return function () {
      return audioSource(path).then(function (url) {
        if (el.src && el.src.indexOf('blob:') === 0) URL.revokeObjectURL(el.src);
        el.src = url;
      });
    };
  }

  function apiCall(path, opts) {
    opts = opts || {};
    var headers = authHeaders();
    var init = { method: opts.method || 'GET', headers: headers };
    if (opts.body) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.body);
    }
    return fetch(apiBase() + path, init).then(function (r) {
      return r.json().then(function (data) {
        // Ответ дошёл - связь есть. Гасим баннер, если он висел: иначе он
        // оставался на экране навсегда после одного сбоя, хотя всё давно
        // работает (06.09.2026, жалоба: "часто выходит").
        apiFailStreak = 0;
        apiEverOk = true;
        hideOffline();
        // Сессия сайта кончилась (истекла, отозвана, база бота
        // переехала) - возвращаем человека ко входу, а не оставляем
        // на экране, где ничего не работает. Внутри Telegram этого
        // пути нет: там 401 значит "протухла initData", и её починит
        // сам Telegram при следующем открытии (10.09.2026).
        if (r.status === 401 && !(tg && tg.initData) && webAuth) {
          saveAuth(null);
          location.reload();
        }
        // Открыто через бот другой половины (18.09.2026) - один экран с
        // кнопкой в свой бот, см. showWrongBot.
        if (r.status === 403 && data && data.error === 'wrong_bot') showWrongBot(data);
        return { status: r.status, data: data };
      });
    }).catch(function () {
      /* Связь оборвалась ЛИБО сервер отдал не-JSON (502 во время
         перезапуска бота - реальный случай 06.09.2026: женский бот
         поднимался пару секунд, и кто открыл приложение в эту секунду,
         остался с вечной "Загрузкой").

         Раньше промис здесь просто умирал: .catch не было ни тут, ни в
         вызывающих местах, колбэк не вызывался, экран замирал навсегда и
         не оживал даже когда сеть возвращалась - человеку приходилось
         закрывать приложение и открывать заново, не понимая почему.

         Теперь любой сбой - это ВИДИМОЕ состояние с кнопкой, а не тишина.
         Не бросаем исключение дальше: вызывающий код получит offline:true
         и пустые данные.

         Но кричать на КАЖДЫЙ сбой нельзя (06.09.2026, жалоба: "часто
         выходит", при том что сервер отдаёт 1777 из 2000 ответов
         двухсотыми). Одиночный обрыв - это норма мобильной жизни: телефон
         переключился с Wi-Fi на LTE, экран погас, приложение свернули - и
         висящий fetch отваливается. Пугать этим человека посреди чтения
         незачем.

         Показываем, только когда сбой действительно означает "не
         работает":
           - приложение ещё ни разу ничего не получило (тот самый случай
             "открывается и висит" - здесь молчать нельзя);
           - либо сбой повторился подряд.
         Пока вкладка скрыта, не считаем вовсе: там обрывы ожидаемы.
         quiet (13.09.2026) - служебные отчёты (mushafFitReport): их сбой
         человека не касается и в счёт баннера не идёт. */
      if (!document.hidden && !opts.quiet) {
        apiFailStreak++;
        if (!apiEverOk || apiFailStreak >= 2) showOffline();
      }
      return { status: 0, data: null, offline: true };
    });
  }

  // Сколько запросов подряд не прошло и получали ли мы вообще хоть один
  // ответ за этот запуск - по ним решаем, показывать баннер или промолчать
  // (см. apiCall).
  var apiFailStreak = 0;
  var apiEverOk = false;

  // Один баннер на всё приложение: пять упавших запросов не должны дать
  // пять полосок. Кнопка перезагружает Mini App - то же, что человек делает
  // руками, закрывая и открывая приложение, только в один тап.
  function showOffline() {
    if (document.getElementById('offline-bar')) return;
    var bar = document.createElement('div');
    bar.id = 'offline-bar';
    bar.innerHTML = '<span>' + T('offline_text') + '</span>' +
      '<button type="button">' + T('offline_retry') + '</button>';
    bar.querySelector('button').addEventListener('click', function () {
      location.reload();
    });
    document.body.appendChild(bar);
  }

  // Связь вернулась - убираем баннер сами, не заставляя человека жать
  // "Попробовать снова" ради того, что уже работает.
  function hideOffline() {
    var bar = document.getElementById('offline-bar');
    if (bar) bar.remove();
  }

  // Проверка 401 в одном месте - initData может протухнуть (сутки, см.
  // core/mufradat_api.py:_INIT_DATA_MAX_AGE) прямо посреди открытого
  // тренажёра, каждый вызов эндпоинта должен на это отреагировать одинаково.
  function withAuthCheck(promise, cb) {
    promise.then(function (res) {
      // Связи нет - баннер с кнопкой уже показан в apiCall. Тянуть колбэк
      // с пустыми данными нельзя: тренажёр отрисуется сломанным поверх
      // честного "нет связи".
      if (res.offline) return;
      if (res.status === 401) {
        document.getElementById('trainer-body').innerHTML =
          '<div class="trainer-msg">' + T('session_expired') + '</div>';
        return;
      }
      cb(res.data);
    });
  }

  var trainerState = null;

  // Кабинет устаза (03.09.2026) - только чтение списка "Ждут проверки",
  // без действий: приём/отклонение сдачи всё ещё идёт реплаем в группе
  // Telegram, как и раньше. Дата/время из sent_at читаем СРОКОВЫМИ
  // СИМВОЛАМИ строки, а не через new Date().toLocaleString() - сервер
  // (core/db.py:get_now()) уже пишет её в бишкекском времени со своим
  // смещением, пересчитывать через часовой пояс браузера не нужно и
  // опасно (та же грабля, что и с score_events - см. память проекта).
  function ustazFormatSince(iso) {
    if (!iso || iso.length < 16) return '';
    return iso.slice(8, 10) + '.' + iso.slice(5, 7) + ' ' + iso.slice(11, 16);
  }

