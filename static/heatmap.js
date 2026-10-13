// Heatmap page: heat layer plus clickable dots, filtered by hour and sample data.
(function () {
  "use strict";
  var summary = document.getElementById("summary");
  if (!window.L || !L.heatLayer) {
    summary.textContent = "The map library did not load. Check your connection and reload.";
    return;
  }
  var map = L.map("map").setView([17.385, 78.4867], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: "&copy; OpenStreetMap contributors"
  }).addTo(map);
  var heat = L.heatLayer([], { radius: 28, blur: 22, maxZoom: 14 }).addTo(map);
  var dots = L.layerGroup().addTo(map);
  var slider = document.getElementById("hour");
  var all = document.getElementById("all-hours");
  var withSample = document.getElementById("show-sample");
  var centred = false;
  var pending = 0;

  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function esc(s) { var d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

  function popup(p) {
    var src;
    if (p.is_sample) src = '<span class="sample-badge">SAMPLE DATA</span> no source link yet';
    else if (p.source_type === "report") src = "Rider report, not verified";
    else src = '<a href="' + esc(p.source_url) + '" target="_blank" rel="noopener noreferrer">Read source</a>';
    return "<strong>" + esc(p.area) + "</strong><br>" + esc(p.category.replace(/_/g, " ")) +
      " · " + esc(p.date) + " · ~" + pad(p.hour) + ":00<br>" + esc(p.snippet) + "<br>" + src;
  }

  function load() {
    var hour = all.checked ? null : Number(slider.value);
    document.getElementById("hour-readout").textContent = hour === null ? "All hours" : pad(hour) + ":00";
    var qs = [];
    if (hour !== null) qs.push("hour=" + hour);
    if (!withSample.checked) qs.push("include_sample=false");
    var mine = ++pending;  // ignore answers to older slider positions
    fetch("/heatmap" + (qs.length ? "?" + qs.join("&") : ""), {
      headers: { Accept: "application/json" }, cache: "no-store"
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (mine !== pending) return;
        document.getElementById("city-name").textContent = data.city;
        if (!centred) { map.setView(data.center, 11); centred = true; }
        heat.setLatLngs(data.points.map(function (p) { return [p.lat, p.lng, Math.max(0.3, p.weight)]; }));
        dots.clearLayers();
        data.points.forEach(function (p) {
          var report = p.source_type === "report";
          L.circleMarker([p.lat, p.lng], {
            radius: 6, weight: report ? 2 : 1, color: "#1d1f22",
            fillColor: report ? "#ffffff" : "#1d1f22", fillOpacity: report ? 0.6 : 0.85
          }).bindPopup(popup(p)).addTo(dots);
        });
        document.getElementById("sample-badge").hidden = !data.points.some(function (p) { return p.is_sample; });
        summary.textContent = data.points.length === 0
          ? "No reported incidents for this filter. Try another hour."
          : data.points.length + " reported incident" + (data.points.length === 1 ? "" : "s") +
            (hour === null ? " across all hours." : " around " + pad(hour) + ":00.");
      })
      .catch(function () {
        summary.textContent = "Could not load reports. Check your connection and reload.";
      });
  }

  slider.addEventListener("input", load);
  all.addEventListener("change", function () { slider.disabled = all.checked; load(); });
  withSample.addEventListener("change", load);
  load();
})();
