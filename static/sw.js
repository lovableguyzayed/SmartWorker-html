const CACHE_NAME = 'smartworker-v12';
const STATIC_ASSETS = [
  '/login',
  '/static/css/custom.css',
  '/static/js/app.js',
  '/static/js/offline-sync.js',
  '/static/images/logo.png',
  '/static/manifest.json',
  '/static/vendor/tailwind.min.css',
  '/static/vendor/fontawesome/css/all.min.css',
  '/static/vendor/fontawesome/webfonts/fa-solid-900.woff2',
  '/static/vendor/fontawesome/webfonts/fa-regular-400.woff2',
  '/static/vendor/html5-qrcode.min.js',
  '/static/vendor/jspdf.umd.min.js',
  '/static/vendor/html2canvas.min.js'
];

// After a form submit (attendance, payroll, settings…) the next page loads
// must come from the network so the user sees their change. Outside that
// window, navigations are served cache-first for an instant native feel and
// silently revalidated in the background.
const MUTATION_WINDOW_MS = 15000;
let lastMutationAt = 0;

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

function cachePage(request, response) {
  // Never cache auth redirects (e.g. /dashboard answered by /login) or errors
  if (!response || !response.ok || response.redirected) return response;
  const clone = response.clone();
  caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
  return response;
}

self.addEventListener('fetch', (event) => {
  const { request } = event;

  if (request.method !== 'GET') {
    lastMutationAt = Date.now();
    return; // POST/PUT/DELETE go straight to the network (offline-sync.js queues them)
  }

  const url = new URL(request.url);

  // Supabase Storage images (worker photos, company logo): cache-first so
  // they render instantly and remain visible offline. Filenames are unique
  // per upload, so stale cache entries are never wrong.
  if (url.origin !== self.location.origin) {
    if (url.hostname.endsWith('.supabase.co')) {
      event.respondWith(
        caches.match(request).then((cached) =>
          cached || fetch(request).then((res) => {
            const clone = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
            return res;
          })
        )
      );
    }
    return; // other cross-origin requests (fonts) go straight to the network
  }

  // Static assets: cache-first, populate on miss
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cached) =>
        cached || fetch(request).then((res) => {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return res;
        })
      )
    );
    return;
  }

  // SPA screen changes arrive as fetch() with Accept: text/html rather than
  // real navigations — treat both as page requests for instant cache serving.
  const isPageRequest = request.mode === 'navigate'
    || (request.headers.get('accept') || '').includes('text/html');
  const recentlyMutated = Date.now() - lastMutationAt < MUTATION_WINDOW_MS;

  if (isPageRequest && !recentlyMutated) {
    // Instant open: serve cached page immediately, refresh cache in background
    event.respondWith(
      caches.match(request).then((cached) => {
        const network = fetch(request)
          .then((res) => cachePage(request, res))
          .catch(() => cached || caches.match('/login'));
        if (cached) {
          event.waitUntil(network.catch(() => {}));
          return cached;
        }
        return network;
      })
    );
    return;
  }

  // Fresh-data path: network-first with cache fallback for offline
  event.respondWith(
    fetch(request)
      .then((res) => cachePage(request, res))
      .catch(() =>
        caches.match(request).then((cached) =>
          cached || caches.match('/login')
        )
      )
  );
});
