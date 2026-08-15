/* 모무꼬 서재 — 오프라인 읽기용 서비스워커
   교재는 한 번 열면 캐시에 남아 지하철에서도 읽힌다. */
const CACHE = 'mm-library-v1';
const CORE = [
  './',
  './index.html',
  './manifest.json',
  './books/blender-book.html',
  './books/gamedesign-book.html',
  './books/unity-book.html',
  './books/codequest.html'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(CORE).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

/* 네트워크 우선 — 새 버전이 있으면 받고, 실패하면 캐시로 */
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request)
      .then(res => {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(e.request).then(r => r || caches.match('./index.html')))
  );
});
