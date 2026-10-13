// Authority SOS console: lists sent alerts with brief, location and links.
(function () {
  "use strict";
  var token = "";
  try { token = sessionStorage.getItem("rr-admin") || ""; } catch (e) { /* storage blocked */ }
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text) n.textContent = text; return n; }

  function load() {
    fetch("/sos/alerts", { headers: token ? { Authorization: "Bearer " + token } : {}, cache: "no-store" })
      .then(function (r) {
        if (r.status === 401) { $("token-form").hidden = false; throw new Error("Enter the officer token."); }
        return r.json();
      })
      .then(function (d) {
        $("error").hidden = true;
        var box = $("alerts");
        box.innerHTML = "";
        if (!d.alerts.length) { box.appendChild(el("p", "notice", "No SOS alerts in the last 7 days.")); return; }
        d.alerts.forEach(function (a) {
          var card = el("article", "alert-card" + (a.severity === "high" || a.duress ? " urgent" : ""));
          card.appendChild(el("h2", null, new Date(a.sent_at).toLocaleString() + (a.area ? " · " + a.area : "") +
            (a.duress ? " · DURESS PIN" : "") + (a.severity ? " · severity " + a.severity : "")));
          card.appendChild(el("p", null, a.summary || ""));
          var links = el("p", "src-meta");
          var open = el("a", null, "Open alert (live location, video)");
          open.href = "/alert/" + encodeURIComponent(a.id); open.target = "_blank"; open.rel = "noopener noreferrer";
          links.appendChild(open);
          if (a.lat !== null) {
            var map = el("a", null, " · Map");
            map.href = "https://www.openstreetmap.org/?mlat=" + a.lat + "&mlon=" + a.lng + "#map=17/" + a.lat + "/" + a.lng;
            map.target = "_blank"; map.rel = "noopener noreferrer";
            links.appendChild(map);
          }
          card.appendChild(links);
          if (a.video_sha256) card.appendChild(el("p", "src-meta", "SHA-256 " + a.video_sha256));
          box.appendChild(card);
        });
      })
      .catch(function (e) { $("error").textContent = e.message || "Could not load alerts."; $("error").hidden = false; });
  }
  $("token-form").addEventListener("submit", function (e) {
    e.preventDefault();
    token = $("token").value.trim();
    try { sessionStorage.setItem("rr-admin", token); } catch (x) { /* storage blocked */ }
    $("token-form").hidden = true;
    load();
  });
  load();
  setInterval(load, 10000);
})();
