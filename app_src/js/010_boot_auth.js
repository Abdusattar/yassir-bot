  var tg = window.Telegram && window.Telegram.WebApp;
  if (tg) { tg.ready(); tg.expand(); }

  // Открыто кнопкой в чате @YassirAppBot (?bot=app, 01.10.2026). Бот один
  // на обе половины, а API у половин свои - спрашиваем, чья половина
  // (/whoami смотрит обе базы), и открываемся заново уже с ней. Хэш с
  // initData сохраняем: из него Telegram и узнаёт человека. Не ответил -
  // мужская: сестре сервер ответит wrong_bot, и она увидит кнопку в своё.
  var openedAs = new URLSearchParams(window.location.search);
  if (openedAs.get('bot') === 'app' && tg && tg.initData) {
    fetch('/api/muf/male/whoami', { headers: { 'X-Telegram-Init-Data': tg.initData } })
      .then(function (r) { return r.json(); })
      .catch(function () { return {}; })
      .then(function (d) {
        openedAs.set('bot', (d && d.profile) || 'male');
        window.location.replace(window.location.pathname + '?' + openedAs.toString() + window.location.hash);
      });
    return;
  }

  // ── Кто мы такие (10.09.2026) ─────────────────────────────────────────
  // Внутри Telegram нас узнаёт initData - подписанная строка, живёт сутки,
  // приходит от самого Telegram. Открытое как сайт (yassirilm.com) то же
  // приложение никакой initData не получает вообще, поэтому там свой
  // токен сессии: его выдают после того, как вход подтвердил бот
  // (core/web_auth.py). Всё остальное в приложении одинаково для обоих.
  //
  // localStorage, а не sessionStorage: сессия обязана пережить закрытие
  // браузера, иначе долгий срок на сервере не имеет смысла.
  var AUTH_KEY = 'yassir_auth';
  var webAuth = null;
  try { webAuth = JSON.parse(localStorage.getItem(AUTH_KEY) || 'null'); } catch (e) {}

  function saveAuth(v) {
    try {
      if (v) localStorage.setItem(AUTH_KEY, JSON.stringify(v));
      else localStorage.removeItem(AUTH_KEY);
    } catch (e) {}
    webAuth = v;
  }

  // Один заголовок на все запросы приложения. До 10.09.2026 эта строчка
  // была скопирована в шести местах - добавить второй способ входа значило
  // бы поправить все шесть и не забыть ни одного.
  function authHeaders() {
    if (tg && tg.initData) return { 'X-Telegram-Init-Data': tg.initData };
    if (webAuth && webAuth.token) return { 'Authorization': 'Bearer ' + webAuth.token };
    return {};
  }

  // Офлайн и значок на экране (10.09.2026) - только для сайта, НЕ внутри
  // Telegram. Причина в истории, а не в технике: index.html и page*.json
  // обновляются на месте, и мы уже ловили телефон, на котором висела старая
  // версия при правильном файле на сервере (29.08.2026). Внутри Telegram
  // сейчас всё работает через nginx no-cache - трогать этот путь незачем,
  // а класс ошибки у service worker'а ровно тот же, только живучее.
  // Подробности стратегии по файлам - в самом sw.js.
  if (!(tg && tg.initData) && 'serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js').catch(function () {});
    });
  }

  // Ни того, ни другого - значит приложение открыто как сайт и человек ещё
  // не входил. Дальше идти незачем: показываем вход и выходим из всего
  // скрипта. Объявления функций хойстятся целиком, поэтому showLogin()
  // ниже по файлу здесь уже доступна (та же особенность, на которой
  // однажды погорел apiBase - см. комментарий у него).
  // Ссылка для входа от супер-админа (20.10.2026, scripts/login_link.py):
  // yassirilm.com/#login=<секрет>. Хэш, а не ?параметр: хэш не уходит на
  // сервер и не оседает в журналах nginx. Сначала спрашиваем мужской
  // процесс (как вход по почте); ссылка сестры не тратится, он отвечает её
  // профилем - спрашиваем женский. Секрет из адреса убираем сразу.
  var linkCode = (window.location.hash.match(/(?:^#|&)login=([\w-]+)/) || [])[1];
  if (linkCode && !(tg && tg.initData)) {
    history.replaceState(null, '', window.location.pathname + window.location.search);
    var useLink = function (profile, hop) {
      fetch('/api/muf/' + profile + '/auth/link', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: linkCode })
      }).then(function (r) { return r.json(); }).catch(function () { return {}; })
        .then(function (d) {
          d = d || {};
          if (d.profile && d.profile !== profile && !hop) { useLink(d.profile, true); return; }
          if (d.token) saveAuth({ token: d.token, profile: profile, name: d.name || '' });
          else {
            try { sessionStorage.setItem('yassir_link_bad', '1'); } catch (e) {}
          }
          location.reload();
        });
    };
    useLink('male', false);
    return;
  }

  if (!(tg && tg.initData) && !(webAuth && webAuth.token)) {
    showLogin();
    return;
  }

  // Открыто через бот другой половины (18.09.2026): первый же 403 wrong_bot
  // из apiCall поднимает этот экран, дальше приложение не работает.
  var wrongBotShown = false;
  function showWrongBot(d) {
    if (wrongBotShown) return;
    wrongBotShown = true;
    document.getElementById('wrongbot-text').textContent =
      T(d.side === 'female' ? 'wrongbot_female' : d.side === 'male' ? 'wrongbot_male' : 'wrongbot_other');
    var a = document.getElementById('wrongbot-link');
    if (d.app_link) {
      a.href = d.app_link;
      a.addEventListener('click', function (e) {
        // Внутри Telegram ссылку t.me открывает сам Telegram: Mini App
        // соседа поднимается на месте этого.
        if (tg && tg.openTelegramLink) { e.preventDefault(); tg.openTelegramLink(d.app_link); }
      });
    } else {
      a.hidden = true;
    }
    document.getElementById('wrongbot').hidden = false;
  }

  function showLogin() {
    var box = document.getElementById('login');
    var stepSide = document.getElementById('login-step-side');
    var stepGo = document.getElementById('login-step-go');
    var link = document.getElementById('login-link');
    var status = document.getElementById('login-status');
    var poll = null;
    box.hidden = false;

    // Вход мог случиться в СОСЕДНЕЙ вкладке (10.09.2026, поймано живьём:
    // человек открыл сайт дважды, вошёл в одной вкладке, а смотрел на
    // другую — та осталась на экране выбора и про вход не знала, потому что
    // токен читается один раз при загрузке). Событие storage приходит всем
    // вкладкам того же сайта, кроме той, что писала: как только вход
    // появился где-то ещё, эта вкладка просто перезагружается и открывает
    // приложение.
    window.addEventListener('storage', function (e) {
      if (e.key === AUTH_KEY && e.newValue) location.reload();
    });

    // navigator.standalone есть только у Safari и равно true, когда
    // приложение уже запущено со значка — тогда подсказка не нужна.
    if (/iPad|iPhone|iPod/.test(navigator.userAgent) && !navigator.standalone) {
      document.getElementById('login-ios').hidden = false;
    }

    // Всегда мужской бот: он ищет человека по обеим базам (18.09.2026).
    document.getElementById('login-start').addEventListener('click', function () { start('male'); });
    document.getElementById('login-back').addEventListener('click', function () {
      if (poll) { clearInterval(poll); poll = null; }
      stepGo.hidden = true;
      stepSide.hidden = false;
    });

    function say(text, bad) {
      status.textContent = text;
      status.className = 'login-status' + (bad ? ' bad' : '');
    }

    // Ссылка для входа не сработала (см. #login= выше) - говорим, почему
    // человек снова на экране входа.
    var linkBad = false;
    try { linkBad = sessionStorage.getItem('yassir_link_bad') === '1'; sessionStorage.removeItem('yassir_link_bad'); } catch (e) {}
    if (linkBad) say(T('login_link_bad'), true);

    // ── Вход по почте (07.10.2026, core/email_login.py) ──
    // Письмо шлёт мужской процесс (как и ссылка в Telegram ведёт в мужской
    // бот), верный код он превращает в обычный код входа для половины
    // человека - дальше тот же waitFor, что и после Telegram.
    var stepMail = document.getElementById('login-step-mail');
    var mailIn = document.getElementById('login-mail');
    var codeBox = document.getElementById('login-mail-code-box');
    var codeIn = document.getElementById('login-mail-code');
    var mailGo = document.getElementById('login-mail-go');
    var mailAgain = document.getElementById('login-mail-again');
    var mailStatus = document.getElementById('login-mail-status');
    var mailBusy = false;
    var MAIL_ERR = {
      email_bad: 'login_err_email_bad',
      not_linked: 'login_err_not_linked',
      too_many: 'login_err_too_many',
      mail_off: 'login_err_mail_off',
      send_failed: 'login_err_send_failed',
      wrong: 'login_err_wrong',
      expired: 'login_err_expired'
    };
    function sayMail(text, bad) {
      mailStatus.textContent = text;
      mailStatus.className = 'login-status' + (bad ? ' bad' : '');
    }
    function postJson(path, body) {
      return fetch('/api/muf/male' + path, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
      }).then(function (r) { return r.json().catch(function () { return {}; }); });
    }
    function sendMailCode() {
      if (mailBusy) return;
      var email = mailIn.value.trim();
      if (!email) { mailIn.focus(); return; }
      mailBusy = true;
      sayMail(T('login_mail_sending'));
      postJson('/auth/email/start', { email: email }).then(function (d) {
        mailBusy = false;
        if (!d.sent) { sayMail(T(MAIL_ERR[d.error] || MAIL_ERR.send_failed), true); return; }
        codeBox.hidden = false;
        mailAgain.hidden = false;
        mailGo.textContent = T('login_enter');
        sayMail(T('login_mail_sent', { E: email }));
        codeIn.value = '';
        codeIn.focus();
      }, function () { mailBusy = false; sayMail(T('login_no_net'), true); });
    }
    function checkMailCode() {
      if (mailBusy) return;
      var code = codeIn.value.replace(/\D/g, '');
      if (code.length !== 6) { sayMail(T('login_code_6'), true); codeIn.focus(); return; }
      mailBusy = true;
      sayMail(T('login_checking'));
      postJson('/auth/email/verify', { email: mailIn.value.trim(), code: code }).then(function (d) {
        mailBusy = false;
        if (!d.code) { sayMail(T(MAIL_ERR[d.error] || MAIL_ERR.wrong), true); return; }
        // Дальше как после Telegram: опрос заберёт сессию у нужной половины.
        status = mailStatus;
        waitFor(d.code, d.profile || 'male');
      }, function () { mailBusy = false; sayMail(T('login_no_net'), true); });
    }
    document.getElementById('login-mail-open').addEventListener('click', function () {
      stepSide.hidden = true;
      stepMail.hidden = false;
      mailIn.focus();
    });
    document.getElementById('login-mail-back').addEventListener('click', function () {
      if (poll) { clearInterval(poll); poll = null; }
      status = document.getElementById('login-status');
      stepMail.hidden = true;
      codeBox.hidden = true;
      mailAgain.hidden = true;
      mailGo.textContent = T('login_mail_send');
      sayMail('');
      stepSide.hidden = false;
    });
    mailGo.addEventListener('click', function () {
      if (codeBox.hidden) sendMailCode(); else checkMailCode();
    });
    mailAgain.addEventListener('click', sendMailCode);
    mailIn.addEventListener('keydown', function (e) { if (e.key === 'Enter') mailGo.click(); });
    codeIn.addEventListener('keydown', function (e) { if (e.key === 'Enter') mailGo.click(); });
    codeIn.addEventListener('input', function () {
      if (codeIn.value.replace(/\D/g, '').length === 6) checkMailCode();
    });

    // profile - чей процесс просим о коде. Ссылка ведёт в этот бот, а вот
    // сессию выдаст тот, где человек учится: сестре мужской бот подтвердит
    // код для женского профиля, и опрос ниже переедет к нему сам
    // (18.09.2026, см. core/web_auth.py).
    function start(profile) {
      stepSide.hidden = true;
      stepGo.hidden = false;
      link.removeAttribute('href');
      say(T('login_preparing'));
      fetch('/api/muf/' + profile + '/auth/start', { method: 'POST' })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d || {} }; }); })
        .then(function (res) {
          if (!res.ok || !res.d.link) {
            say(res.d.error === 'too_many'
              ? T('login_err_tries')
              : T('login_err_start'), true);
            return;
          }
          link.href = res.d.link;
          say(T('login_press'));
          waitFor(res.d.code, profile);
        })
        .catch(function () { say(T('login_no_net'), true); });
    }

    // Опрос раз в две секунды. Держать соединение открытым (long-poll) не
    // стали: вкладку на телефоне усыпляют, а короткий запрос переживает сон
    // спокойно - вернулся в браузер, и следующий тик всё забрал.
    function waitFor(code, profile) {
      var until = Date.now() + 15 * 60 * 1000;   // столько же живёт код на сервере
      if (poll) clearInterval(poll);
      poll = setInterval(function () {
        if (Date.now() > until) {
          clearInterval(poll);
          poll = null;
          say(T('login_expired'), true);
          return;
        }
        fetch('/api/muf/' + profile + '/auth/poll?code=' + encodeURIComponent(code))
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (!d) return;
            // Бот не нашёл человека ни у себя, ни у соседа. Он сказал об
            // этом в Telegram, но человек смотрит сюда: говорим и здесь.
            if (d.refused) {
              clearInterval(poll);
              poll = null;
              stepGo.hidden = true;
              stepSide.hidden = false;
              document.getElementById('login-wrong-side').hidden = false;
              return;
            }
            // Код подтверждён для другого бота (сестра вошла через ссылку
            // в мужской): дальше спрашиваем его процесс - сессия там.
            if (d.profile && d.profile !== profile) {
              profile = d.profile;
              return;
            }
            if (!d.token) return;
            clearInterval(poll);
            poll = null;
            saveAuth({ token: d.token, profile: profile, name: d.name || '' });
            say(T('login_done', { N: d.name ? ', ' + d.name : '' }));
            // Перезагрузка, а не ручной запуск приложения: оно поднимается
            // не одной функцией, а десятками мест по всему файлу (загрузка
            // страницы мусхафа, синхронизация языка, указатель 40+40,
            // пульс). Повторить этот порядок вручную - надёжный способ
            // получить полурабочий экран; перезагрузка проходит ровно тот
            // же путь, что и обычное открытие.
            location.reload();
          })
          .catch(function () {});
      }, 2000);
    }
  }

  // Выход - только для сессии сайта (см. #dash-logout в разметке). Гасим
  // токен и на сервере: иначе на чужом устройстве он остался бы рабочим
  // ещё три месяца. Ответа не ждём молча - экран входа показываем в любом
  // случае, даже если запрос не дошёл.
  if (webAuth && webAuth.token) {
    var logoutBtn = document.getElementById('dash-logout');
    logoutBtn.hidden = false;
    // Выход - со второго нажатия (30.10.2026): Муслим случайно вышел с
    // иконки на экране, а войти заново тогда не мог (см. i18nTable).
    // Первое нажатие спрашивает, через 4 с кнопка возвращается сама.
    var logoutSure = null;
    logoutBtn.addEventListener('click', function () {
      if (!logoutSure) {
        logoutBtn.textContent = T('sett_logout_sure');
        logoutBtn.classList.add('sure');
        logoutSure = setTimeout(function () {
          logoutSure = null;
          logoutBtn.textContent = T('sett_logout');
          logoutBtn.classList.remove('sure');
        }, 4000);
        return;
      }
      clearTimeout(logoutSure);
      logoutBtn.disabled = true;
      var done = function () { saveAuth(null); location.reload(); };
      fetch(apiBase() + '/auth/logout', { method: 'POST', headers: authHeaders() })
        .then(done, done);
    });
  }

