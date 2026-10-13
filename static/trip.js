// Trip viewer: polls the latest shared point every 10 seconds.
(function () {
  "use strict";
  var token = location.pathname.split("/").filter(Boolean)[1];
  var status = document.getElementById("status");
  var detail = document.getElementById("detail");
  var stale = document.getElementById("stale");
  var STALE_SECONDS = 120;
  var map = null, marker = null, updatedAt = null, poll = null;

  if (window.L) {
    map = L.map("map").setView([17.385, 78.4867], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);
  }

  function tick() {
    if (!updatedAt) return;
    var s = Math.max(0, Math.round((Date.now() - updatedAt) / 1000));
    status.textContent = "Last updated " + (s < 90 ? s + " seconds ago" : Math.round(s / 60) + " minutes ago");
    stale.hidden = s < STALE_SECONDS;
  }

  function ended(message) {
    clearInterval(poll);
    updatedAt = null;
    stale.hidden = true;
    status.textContent = "This trip link has ended";
    detail.textContent = message || "The rider stopped sharing, or the link expired.";
  }

  function load() {
    fetch("/trip/" + encodeURIComponent(token) + "/data", { cache: "no-store" })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, status: r.status, d: d }; }); })
      .then(function (res) {
        if (res.status === 404) { ended(res.d.error); return; }
        if (!res.ok) return;
        var d = res.d;
        detail.textContent = "Link expires at " + new Date(d.expires_at).toLocaleTimeString() +
          ". Refreshes every 10 seconds.";
        if (d.lat === null) return;
        updatedAt = Date.now() - d.seconds_ago * 1000;
        var ll = [d.lat, d.lng];
        if (map) {
          if (!marker) { marker = L.marker(ll).addTo(map); map.setView(ll, 15); }
          else { marker.setLatLng(ll); map.panTo(ll); }
        } else {
          detail.textContent += " Map unavailable. Position: " + d.lat.toFixed(5) + ", " + d.lng.toFixed(5);
        }
        tick();
      })
      .catch(function () { detail.textContent = "Connection lost. Retrying every 10 seconds."; });
  }

  load();
  poll = setInterval(load, 10000);
  setInterval(tick, 1000);
})();
