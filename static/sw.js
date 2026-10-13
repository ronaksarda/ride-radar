// Caches the app shell and the last /check result so the app opens offline.
var SHELL = "rr-shell-v7";
var LAST = "rr-last-check";
var SHELL_FILES = ["/", "/static/style.css", "/static/app.js", "/static/icon.svg", "/manifest.json", "/areas", "/privacy", "/sos", "/static/sos.js"];

self.addEventListener("install", function (event) {
  event.waitUntil(caches.open(SHELL).then(function (c) { return c.addAll(SHELL_FILES); }));
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== SHELL && k !== LAST; })
      .map(function (k) { return caches.delete(k); }));
  }));
  self.clients.claim();
});

self.addEventListener("fetch", function (event) {
  var url = new URL(event.request.url);
  if (url.origin !== location.origin) return;

  // POST /check: network first; keep a copy of the latest result for offline use.
  if (event.request.method === "POST" && url.pathname === "/check") {
    event.respondWith(fetch(event.request.clone()).then(function (res) {
      if (res.ok) {
        var copy = res.clone();
        copy.text().then(function (body) {
          caches.open(LAST).then(function (c) {
            c.put("/last-check", new Response(body, {
              headers: { "Content-Type": "application/json", "X-Ride-Radar-Cached-At": new Date().toISOString() }
            }));
          });
        });
      }
      return res;
    }).catch(function () {
      return caches.open(LAST).then(function (c) { return c.match("/last-check"); }).then(function (hit) {
        return hit || Response.error();
      });
    }));
    return;
  }

  if (event.request.method !== "GET") return;
  if (SHELL_FILES.indexOf(url.pathname) === -1) return;
  // App shell: network first so updates show, cache when offline.
  event.respondWith(fetch(event.request).then(function (res) {
    var copy = res.clone();
    caches.open(SHELL).then(function (c) { c.put(event.request, copy); });
    return res;
  }).catch(function () { return caches.match(event.request); }));
});
