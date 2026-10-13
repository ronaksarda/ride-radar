// Alert page for emergency contacts: live location, AI brief, video, hash. Refreshes every 10 s.
(function () {
  "use strict";
  var id = location.pathname.split("/").filter(Boolean)[1];
  var map = null, marker = null, videoSet = false;
  if (window.L) {
    map = L.map("map").setView([17.385, 78.4867], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);
  }
  function $(x) { return document.getElementById(x); }

  function load() {
    fetch("/alert/" + encodeURIComponent(id) + "/data", { cache: "no-store" })
      .then(function (r) { return r.json().then(function (d) { return { status: r.status, d: d }; }); })
      .then(function (res) {
        var d = res.d;
        if (res.status === 404) { $("title").textContent = "This alert does not exist."; return; }
        if (d.state === "cancelled") { $("title").textContent = "The rider cancelled this alert (false alarm)."; return; }
        if (d.state !== "sent") { $("title").textContent = "Alert is being prepared…"; return; }
        var sent = new Date(d.sent_at);
        $("title").textContent = "SOS sent at " + sent.toLocaleTimeString() + (d.area ? " near " + d.area : "");
        $("duress").hidden = !d.duress;
        if (d.lat !== null) {
          var ago = Math.round((Date.now() - new Date(d.location_updated)) / 1000);
          $("where").textContent = "Last location " + d.lat.toFixed(5) + ", " + d.lng.toFixed(5) +
            " · updated " + (ago < 90 ? ago + " s" : Math.round(ago / 60) + " min") + " ago";
          if (map) {
            var ll = [d.lat, d.lng];
            if (!marker) { marker = L.marker(ll).addTo(map); map.setView(ll, 16); } else marker.setLatLng(ll);
          }
        }
        $("summary").textContent = (d.summary || "") + (d.ai_status === "pending" ? " (AI brief on its way…)" : "");
        if (d.transcript) { $("transcript").textContent = d.transcript; $("transcript-box").hidden = false; }
        if (d.video_url && !videoSet) {
          $("video").src = d.video_url; $("video").hidden = false; videoSet = true;
          $("video-note").textContent = "Recorded on the rider's phone.";
        }
        if (d.video_sha256) $("hash").textContent = "Video SHA-256 (proves the file was not changed): " + d.video_sha256;
      })
      .catch(function () { $("where").textContent = "Connection lost. Retrying…"; });
  }
  load();
  setInterval(load, 10000);
})();
