const CACHE_NAME = 'bd-cache-v2';
const urlsToCache = [
  './',
  './index.html',
  './data.json',
  './manifest.json'
];

self.addEventListener('install', event => {
  self.skipWaiting(); // Force new service worker to take over immediately
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName); // Delete old caches
          }
        })
      );
    }).then(() => self.clients.claim()) // Take control of all clients immediately
  );
});

self.addEventListener('fetch', event => {
  // Try network first, then fallback to cache for HTML, to always get the latest version if online.
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
