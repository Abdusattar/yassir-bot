/* Service worker YassirApp (10.09.2026).
 *
 * Ставится ТОЛЬКО когда приложение открыто как сайт, не внутри Telegram
 * (см. регистрацию в index.html). Причина не в технике, а в истории: файлы
 * index.html и page*.json обновляются НА МЕСТЕ, имена не меняются, и мы уже
 * ловили случай, когда правильный файл лежал на сервере, а на телефоне
 * висела старая версия (29.08.2026, см. wiki/mushaf_yassirapp.md). Кэш
 * service worker'а — та же ловушка, только он умеет держать старое неделями.
 * Поэтому внутри Telegram, где всё и так работает через nginx no-cache,
 * ничего не меняем, а здесь стратегия выбирается ПОФАЙЛОВО, а не одна на всё.
 *
 * Что где:
 *   index.html  — сеть вперёд, кэш только если сети нет. Правки приложения
 *                 доходят в тот же момент, что и раньше; офлайн открывается
 *                 последняя виденная версия.
 *   листы, смысл, переводы слов с отпечатком в адресе (...json?h=<отпечаток>,
 *                 с 14.11.2026) — из кэша навсегда: содержимое по такому адресу
 *                 не меняется. Исправили файл - приложение попросит новый адрес
 *                 (data_manifest.json), старая запись заменится.
 *   data_manifest.json — сеть вперёд; сеть молчит дольше секунды - последний
 *                 виденный список.
 *   page*.json, meaning/ без отпечатка (старая оболочка или список не пришёл) —
 *                 из кэша сразу, обновление в фоне.
 *   шрифты      — из кэша: у каждой страницы мусхафа свой файл шрифта, и он
 *                 неизменен (QPC V4). Держим 150 последних открывавшихся
 *                 листов, давние вытесняются (14.11.2026).
 *   /api/muf/*  — НИКОГДА не кэшируем. Это живые данные: прогресс, сдачи,
 *                 пульс. Отданный из кэша ответ здесь означал бы враньё.
 *   аудио       — мимо кэша: разборы устаза и чтение Хусари весят много,
 *                 забивать ими хранилище телефона незачем.
 */
const VERSION = 'v1';
const SHELL = 'yassir-shell-' + VERSION;   // index.html и иконки
const PAGES = 'yassir-pages-' + VERSION;   // page*.json
const FONTS = 'yassir-fonts-' + VERSION;   // шрифты страниц мусхафа

const SHELL_URLS = ['/', '/index.html', '/manifest.json', '/icon-192.png'];

self.addEventListener('install', (e) => {
  // Не ждём, пока закроются старые вкладки: обновление приложения не должно
  // зависеть от того, помнит ли человек, что оно где-то ещё открыто.
  e.waitUntil(
    caches.open(SHELL).then((c) => c.addAll(SHELL_URLS)).catch(() => {})
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  const keep = [SHELL, PAGES, FONTS];
  e.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names.filter((n) => n.startsWith('yassir-') && !keep.includes(n))
             .map((n) => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

// Данные мусхафа готовыми файлами: листы обеих раскладок, смысл по сурам, переводы слов.
function isDataFile(url) {
  return url.origin === self.location.origin &&
    (/^\/(dm\/)?page\d+\.json$/.test(url.pathname) ||
     /^\/meaning\/[a-z_]+\/\d+\.json$/.test(url.pathname) ||
     /^\/wbw\/[a-z]+\/\d+\.json$/.test(url.pathname));
}
// Адрес с отпечатком содержимого (?h=...): по нему файл не меняется никогда.
function isHashed(url) {
  return /^\?h=[0-9a-f]+$/.test(url.search);
}
// Списки отпечатков: единый data_manifest.json (14.11.2026, wiki/architecture.md Р1)
// и прежний wbw/manifest.json (его просит оболочка, открытая до обновления).
function isManifest(url) {
  return url.origin === self.location.origin &&
    (url.pathname === '/data_manifest.json' || url.pathname === '/wbw/manifest.json');
}
const MANIFEST_WAIT_MS = 1000;

function isFont(url) {
  return /\.(woff2?|ttf|otf)$/i.test(url.pathname);
}

// Шрифты листов мусхафа (p<N>.woff2): у каждого листа свой, ~87 КБ, все 604 - около
// 53 МБ. Весь мусхаф разом никто не читает (решение пользователя 14.11.2026): держим
// FONT_LIMIT последних открывавшихся листов (~7 джузов, ~13 МБ), остальные вытесняем -
// давно не открывавшийся лист при сети просто скачает шрифт заново.
// Когда лист открывали, помнит запись FONT_LRU в том же кэше: {адрес: время}.
const FONT_LIMIT = 150;
const FONT_LRU = '/__font_lru';
function isPageFont(url) {
  return /\/p\d+\.(woff2?|ttf)$/i.test(url.pathname);
}
let fontLru = null;          // в памяти, пока service worker жив
let fontLruQueue = Promise.resolve();
const fontSeen = {};         // отметки, ещё не записанные: ставятся сразу, до очереди
function fontTouch(cache, href, added) {
  // Время ставим немедленно: при подгрузке десятка листов разом только что скачанный
  // шрифт без отметки иначе выглядел бы самым давним и вытеснялся первым.
  fontSeen[href] = Date.now();
  // по очереди: два листа, открытые разом, не затирают отметки друг друга
  fontLruQueue = fontLruQueue.then(() => fontTouchNow(cache, href, added)).catch(() => {});
  return fontLruQueue;
}
function fontTouchNow(cache, href, added) {
  const load = fontLru ? Promise.resolve(fontLru)
    : cache.match(FONT_LRU).then((r) => (r ? r.json() : {})).catch(() => ({})).then((m) => (fontLru = m));
  return load.then((lru) => {
    Object.keys(fontSeen).forEach((u) => { lru[u] = fontSeen[u]; delete fontSeen[u]; });
    if (!added) return lru;
    return cache.keys().then((keys) => {
      const fonts = keys.map((k) => k.url).filter((u) => isPageFont(new URL(u)));
      const have = {};
      fonts.forEach((u) => { have[u] = true; });
      Object.keys(lru).forEach((u) => { if (!have[u]) delete lru[u]; });   // отметки без файла
      if (fonts.length <= FONT_LIMIT) return lru;
      fonts.sort((x, y) => (lru[x] || 0) - (lru[y] || 0));                  // давние - первыми
      const drop = fonts.slice(0, fonts.length - FONT_LIMIT);
      drop.forEach((u) => { delete lru[u]; });
      return Promise.all(drop.map((u) => cache.delete(u))).then(() => lru);
    });
  }).then((lru) => cache.put(FONT_LRU, new Response(JSON.stringify(lru), {
    headers: { 'Content-Type': 'application/json' } })));
}

function isIndex(url) {
  return url.origin === self.location.origin
    && (url.pathname === '/' || url.pathname === '/index.html');
}

function isAudio(url) {
  return /\.(mp3|ogg|m4a|opus)$/i.test(url.pathname) || url.pathname.indexOf('/audio/') !== -1;
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Живые данные и звук — всегда напрямую, без нашего участия.
  if (url.pathname.startsWith('/api/muf/') || isAudio(url)) return;

  if (isIndex(url)) {
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put('/index.html', copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match('/index.html').then((r) => r || caches.match('/')))
    );
    return;
  }

  if (isManifest(url)) {
    // Сеть вперёд: в списке свежие отпечатки. Но лист не должен ждать слабую сеть:
    // молчит дольше секунды - отдаём последний виденный список, новый доедет в кэш
    // и сработает при следующем открытии. Без сети - тоже последний виденный.
    e.respondWith(
      caches.open(PAGES).then((cache) =>
        cache.match(url.pathname).then((hit) => {
          const fresh = fetch(req).then((res) => {
            if (res && res.ok) cache.put(url.pathname, res.clone()).catch(() => {});
            return res;
          });
          if (!hit) return fresh;
          const late = new Promise((resolve) => setTimeout(() => resolve(hit), MANIFEST_WAIT_MS));
          return Promise.race([fresh.catch(() => hit), late]);
        })
      )
    );
    return;
  }

  if (isDataFile(url) && isHashed(url)) {
    // Из кэша навсегда. На файл держим одну запись: новая версия вытесняет и старые
    // отпечатки, и запись без отпечатка, оставшуюся от прежней оболочки.
    e.respondWith(
      caches.open(PAGES).then((cache) =>
        cache.match(req).then((hit) => hit || fetch(req).then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            cache.keys().then((keys) => Promise.all(keys
              .filter((k) => { const u = new URL(k.url); return u.pathname === url.pathname && u.search !== url.search; })
              .map((k) => cache.delete(k)))
            ).then(() => cache.put(req, copy)).catch(() => {});
          }
          return res;
        }).catch((err) =>
          // сети нет, а нужной версии в кэше нет - лучше прежняя версия файла, чем пустой лист
          cache.match(req, { ignoreSearch: true }).then((old) => old || Promise.reject(err))
        ))
      )
    );
    return;
  }

  if (isDataFile(url)) {
    // Без отпечатка: из кэша сразу (годится и запись с отпечатком), обновление в фоне.
    e.respondWith(
      caches.open(PAGES).then((cache) =>
        cache.match(req).then((exact) =>
          exact ? { hit: exact, own: true }
                : cache.match(req, { ignoreSearch: true }).then((any) => ({ hit: any, own: !any }))
        ).then((found) => {
          const hit = found.hit;
          const fresh = fetch(req).then((res) => {
            // запись с отпечатком уже есть - вторую копию того же файла не кладём
            if (res && res.ok && found.own) cache.put(req, res.clone());
            return res;
          }).catch((err) => hit || Promise.reject(err));
          return hit || fresh;
        })
      )
    );
    return;
  }

  if (isFont(url)) {
    e.respondWith(
      caches.open(FONTS).then((cache) =>
        cache.match(req).then((hit) => {
          // Только удачный ответ (02.11.2026): раньше в кэш ложилось всё,
          // и 404 пропавшего у CDN p328.woff2 застревал на телефоне
          // навсегда. Шрифт грузит FontFace - это CORS-запрос, у ответа
          // виден статус. Уже застрявшая ошибка не отдаётся, а качается
          // заново - без смены VERSION и перекачки всех 604 шрифтов.
          if (hit && hit.ok) {
            if (isPageFont(url)) e.waitUntil(fontTouch(cache, req.url, false));
            return hit;
          }
          return fetch(req).then((res) => {
            if (res && res.ok) {
              const stored = cache.put(req, res.clone());
              if (isPageFont(url)) {
                fontSeen[req.url] = Date.now();
                e.waitUntil(stored.then(() => fontTouch(cache, req.url, true)));
              }
            } else if (hit) cache.delete(req);
            return res;
          });
        })
      )
    );
    return;
  }

  // Всё прочее (иконки, manifest) — сеть, а если её нет, то что есть.
  e.respondWith(fetch(req).catch(() => caches.match(req)));
});
