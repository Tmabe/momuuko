const CACHE = 'momuuko-v1';
const SHELL = [
  '/momuuko/studio-BETA.html',
  '/momuuko/d_i75EXu4XuLRneN3r-BETA.html',
  '/momuuko/deadline-BETA.html',
  '/momuuko/practice-BETA.html',
  '/momuuko/manifest.json',
  '/momuuko/icons/icon-192.png',
  '/momuuko/icons/icon-512.png'
];

self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE).then(function(c) { return c.addAll(SHELL); })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(keys.filter(function(k){ return k !== CACHE; }).map(function(k){ return caches.delete(k); }));
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(e) {
  // 외부 리소스(CDN, API)는 네트워크 우선
  if (!e.request.url.includes('tmabe.github.io') && !e.request.url.includes('localhost')) {
    return;
  }
  e.respondWith(
    caches.match(e.request).then(function(cached) {
      var net = fetch(e.request).then(function(res) {
        caches.open(CACHE).then(function(c) { c.put(e.request, res.clone()); });
        return res;
      });
      return cached || net;
    })
  );
});
