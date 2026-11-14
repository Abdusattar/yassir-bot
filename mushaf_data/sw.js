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
 *   page*.json, meaning/<перевод>/<сура>.json — отдаём из кэша сразу и молча обновляем в фоне. Страница
 *                 мусхафа появляется мгновенно и работает без сети, а
 *                 исправление раскладки доезжает к следующему открытию.
 *   шрифты      — из кэша навсегда: у каждой страницы мусхафа свой файл
 *                 шрифта, и он неизменен (QPC V4, CDN).
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

// Смысловой перевод по сурам (02.11.2026, meaning/<перевод>/<сура>.json) -
// та же стратегия, что у листов: из кэша сразу, обновление в фоне. Иначе
// чтение смысла без сети было бы пустым.
function isPageJson(url) {
  return url.origin === self.location.origin &&
    (/^\/page\d+\.json$/.test(url.pathname) || /^\/meaning\/[a-z_]+\/\d+\.json$/.test(url.pathname));
}

// Пословные переводы по сурам (14.11.2026, wiki/wbw_split_plan.md):
// wbw/<язык>/<сура>.json?h=<хэш> - содержимое по адресу не меняется, берём из кэша
// навсегда; на (язык, сура) держим одну запись - новая версия вытесняет старую.
// wbw/manifest.json - сеть вперёд (там свежие хэши), без сети - последний виденный.
// Кэш не чистится при выходе: при слабом интернете дешевле не качать заново.
function isWbwChunk(url) {
  return url.origin === self.location.origin && /^\/wbw\/[a-z]+\/\d+\.json$/.test(url.pathname);
}
function isWbwManifest(url) {
  return url.origin === self.location.origin && url.pathname === '/wbw/manifest.json';
}

function isFont(url) {
  return /\.(woff2?|ttf|otf)$/i.test(url.pathname);
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

  if (isWbwManifest(url)) {
    e.respondWith(
      fetch(req).then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(PAGES).then((c) => c.put(url.pathname, copy)).catch(() => {});
        }
        return res;
      }).catch(() => caches.match(url.pathname))
    );
    return;
  }

  if (isWbwChunk(url)) {
    e.respondWith(
      caches.open(PAGES).then((cache) =>
        cache.match(req).then((hit) => hit || fetch(req).then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            // старые версии этой суры на этом языке больше не нужны
            cache.keys().then((keys) => Promise.all(keys
              .filter((k) => { const u = new URL(k.url); return u.pathname === url.pathname && u.search !== url.search; })
              .map((k) => cache.delete(k)))
            ).then(() => cache.put(req, copy)).catch(() => {});
          }
          return res;
        }))
      )
    );
    return;
  }

  if (isPageJson(url)) {
    e.respondWith(
      caches.open(PAGES).then((cache) =>
        cache.match(req).then((hit) => {
          const fresh = fetch(req).then((res) => {
            if (res && res.ok) cache.put(req, res.clone());
            return res;
          }).catch(() => hit);
          // Есть в кэше — отдаём мгновенно, обновление идёт своим ходом.
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
          if (hit && hit.ok) return hit;
          return fetch(req).then((res) => {
            if (res && res.ok) cache.put(req, res.clone());
            else if (hit) cache.delete(req);
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
