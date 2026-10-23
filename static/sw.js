// Bump this whenever the caching rules change. Bumping it also wipes every
// older cache on activate, which is how a device holding stale assets from a
// previous version gets cleaned out.
const CACHE_NAME = 'smartworker-v21';

// Only the app shell is pre-cached. Every /static/ URL now carries a ?v=
// content stamp (see _stamp_static_url in app.py), so the bare paths that used
// to be listed here are never requested by any page — pre-caching them
// downloaded a second, unused copy of each asset and, worse, made it look as
// though the assets were covered. They are cached at runtime instead, on the
// first page that asks for them.
const STATIC_ASSETS = [
  '/login'
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

// The cache key for a page is its URL, but the language comes from the
// session, so after a language switch every cached page is in the old
// language. They would each be served stale once before the background
// revalidate landed. app.js tells us the moment it sees the language change;
// dropping the page entries costs one network load per screen and nothing else
// (static assets and photos are keyed by content and stay).
async function purgeCachedPages() {
  const cache = await caches.open(CACHE_NAME);
  const keys = await cache.keys();
  await Promise.all(keys.map(async (request) => {
    const url = new URL(request.url);
    if (url.origin !== self.location.origin) return;
    if (url.pathname.startsWith('/static/')) return;
    await cache.delete(request);
  }));
  // /login is the offline fallback every miss falls back to, so put the shell
  // back rather than leaving the app with nothing to show while offline.
  await cache.addAll(STATIC_ASSETS).catch(() => {});
}

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'purge-pages') {
    event.waitUntil(purgeCachedPages());
  }
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
            // Only cache successful image responses — never a 403/404 (e.g.
            // before Storage is configured), which would otherwise be served
            // as a permanently broken image even after the bucket is fixed.
            if (res && res.ok) {
              const clone = res.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
            }
            return res;
          })
        )
      );
    }
    return; // other cross-origin requests (fonts) go straight to the network
  }

  // Static assets. Never cache errors — a 404 for an uploaded image (e.g.
  // wiped by a redeploy) must not be pinned in the cache, or the image stays
  // broken forever even after a successful re-upload.
  if (url.pathname.startsWith('/static/')) {
    const store = (res) => {
      if (res && res.ok) {
        const clone = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
      }
      return res;
    };

    // A stamped URL (?v=<content hash>) can only ever name one version of one
    // file, so serving it from cache forever is both safe and the fastest
    // thing we can do.
    if (url.searchParams.has('v')) {
      event.respondWith(
        caches.match(request).then((cached) => cached || fetch(request).then(store))
      );
      return;
    }

    // An unstamped URL is a path that could change under us — anything
    // referenced from inside a stylesheet or script rather than through
    // url_for. Serve the cached copy for speed but always refresh it in the
    // background, so a stale asset survives at most one load. Pure
    // cache-first here is what pinned a months-old custom.css on real
    // devices, leaving the calendar with no grid rules at all.
    event.respondWith(
      caches.match(request).then((cached) => {
        const fresh = fetch(request).then(store).catch(() => cached);
        return cached || fresh;
      })
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
