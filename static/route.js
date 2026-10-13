// Route page: type or pin a pickup and a drop, then score every stretch of the ride.
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  var WORD = { green: "Green", amber: "Amber", red: "Red", not_covered: "Not covered yet" };
  var MY_LOCATION = "My location";
  var NAME = { from: "pickup", to: "drop" };

  if (!window.L) {
    $("error").textContent = "The map library did not load. Check your connection and reload.";
    $("error").hidden = false;
    return;
  }
  var css = getComputedStyle(document.documentElement);
  function color(level) { return css.getPropertyValue("--" + (level === "not_covered" ? "muted" : level)).trim(); }

  var map = L.map("map").setView([17.385, 78.4867], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: "&copy; OpenStreetMap contributors"
  }).addTo(map);
  var line = L.layerGroup().addTo(map);
  var pins = { from: null, to: null };
  var points = { from: null, to: null };   // chosen {lat, lng}, null until picked
  var areas = [];
  var pinTarget = "to";                     // which field a map tap fills

  var hourSel = $("hour"), now = new Date().getHours();
  for (var h = 0; h < 24; h++) {
    var o = document.createElement("option");
    o.value = h; o.textContent = pad(h) + ":00" + (h === now ? " (now)" : "");
    if (h === now) o.selected = true;
    hourSel.appendChild(o);
  }
  $("from").value = MY_LOCATION;

  fetch("/areas").then(function (r) { return r.json(); }).then(function (data) {
    areas = data.areas;
    $("city-name").textContent = data.city;
    map.setView(data.center, 11);
  }).catch(function () { showError("Could not load areas. Check your connection."); });

  function showError(msg) { $("error").textContent = msg; $("error").hidden = !msg; }

  function setPin(which, lat, lng, label) {
    points[which] = { lat: lat, lng: lng };
    if (pins[which]) map.removeLayer(pins[which]);
    pins[which] = L.circleMarker([lat, lng], {
      radius: 9, weight: 3, color: "#1d1f22", fillColor: which === "from" ? "#ffffff" : "#1d1f22", fillOpacity: 1
    }).bindTooltip(label || (which === "from" ? "Pickup" : "Drop")).addTo(map);
  }

  // ---------- type-ahead ----------
  var timers = {}, seq = {}, items = { from: [], to: [] }, active = { from: -1, to: -1 };

  function areaMatches(q) {
    q = q.toLowerCase();
    return areas.filter(function (a) { return a.name.toLowerCase().indexOf(q) !== -1; })
      .slice(0, 4).map(function (a) { return { label: a.name, lat: a.lat, lng: a.lng, kind: "Area" }; });
  }

  function geocode(q, final) {
    return fetch("/geocode?q=" + encodeURIComponent(q) + (final ? "&final=true" : "")).then(function (r) {
      return r.ok ? r.json() : { results: [] };
    }).then(function (d) {
      return d.results.map(function (x) { return { label: x.label, lat: x.lat, lng: x.lng, kind: "Address" }; });
    }).catch(function () { return []; });
  }

  function renderList(which) {
    var ul = $(which + "-list"), input = $(which);
    ul.innerHTML = "";
    items[which].forEach(function (it, i) {
      var li = document.createElement("li");
      li.id = which + "-opt-" + i;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", i === active[which] ? "true" : "false");
      var main = document.createElement("span");
      main.textContent = it.label;
      var kind = document.createElement("small");
      kind.textContent = it.kind;
      li.appendChild(main); li.appendChild(kind);
      li.addEventListener("mousedown", function (e) { e.preventDefault(); choose(which, i); });
      ul.appendChild(li);
    });
    var open = items[which].length > 0;
    ul.hidden = !open;
    input.setAttribute("aria-expanded", open ? "true" : "false");
    if (active[which] >= 0) input.setAttribute("aria-activedescendant", which + "-opt-" + active[which]);
    else input.removeAttribute("aria-activedescendant");
  }

  function close(which) { items[which] = []; active[which] = -1; renderList(which); }

  function suggest(which) {
    var q = $(which).value.trim();
    var base = which === "from" ? [{ label: MY_LOCATION, kind: "GPS", gps: true }] : [];
    if (q === MY_LOCATION) q = "";
    items[which] = base.concat(q ? areaMatches(q) : []);
    active[which] = -1;
    renderList(which);
    clearTimeout(timers[which]);
    if (q.length < 3) return;
    var mine = seq[which] = (seq[which] || 0) + 1;
    timers[which] = setTimeout(function () {
      geocode(q).then(function (found) {
        if (mine !== seq[which] || document.activeElement !== $(which)) return;
        var have = {};
        items[which].forEach(function (it) { have[it.label] = true; });
        items[which] = items[which].concat(found.filter(function (f) { return !have[f.label]; }));
        renderList(which);
      });
    }, 250);
  }

  function choose(which, i) {
    var it = items[which][i];
    close(which);
    if (!it) return;
    $(which).value = it.label;
    if (it.gps) { points.from = null; if (pins.from) { map.removeLayer(pins.from); pins.from = null; } return; }
    setPin(which, it.lat, it.lng, it.label);
    map.setView([it.lat, it.lng], Math.max(map.getZoom(), 13));
  }

  ["from", "to"].forEach(function (which) {
    var input = $(which);
    input.addEventListener("focus", function () {
      pinTarget = which;
      $("pin-hint").textContent = "Type an address, or tap the map to set your " + NAME[which] + ".";
      if (which === "from" && input.value === MY_LOCATION) input.select();
      suggest(which);
    });
    input.addEventListener("input", function () { points[which] = null; suggest(which); });
    input.addEventListener("blur", function () { close(which); });
    input.addEventListener("keydown", function (e) {
      var n = items[which].length;
      if (e.key === "ArrowDown" && n) { e.preventDefault(); active[which] = (active[which] + 1) % n; renderList(which); }
      else if (e.key === "ArrowUp" && n) { e.preventDefault(); active[which] = (active[which] - 1 + n) % n; renderList(which); }
      else if (e.key === "Enter" && active[which] >= 0) { e.preventDefault(); choose(which, active[which]); }
      else if (e.key === "Escape") close(which);
    });
  });

  map.on("click", function (e) {
    var which = pinTarget;
    setPin(which, e.latlng.lat, e.latlng.lng);
    $(which).value = "Pinned on map";
    close(which);
    $("pin-hint").textContent = (which === "from" ? "Pickup" : "Drop") + " pinned. Tap again to move it.";
  });

  // A typed address nobody picked from the list: take the best match.
  function resolve(which) {
    if (points[which]) return Promise.resolve();
    var q = $(which).value.trim();
    if (which === "from" && (q === "" || q === MY_LOCATION)) return locate();
    if (!q) return Promise.reject(new Error("Type where you are going, or tap the map."));
    var area = areaMatches(q.replace(/,?\s*hyderabad\s*$/i, ""))[0];
    if (area) { setPin(which, area.lat, area.lng, area.label); $(which).value = area.label; return Promise.resolve(); }
    return geocode(q, true).then(function (found) {
      if (!found.length) throw new Error("Could not find “" + q + "” in " + $("city-name").textContent + ". Try a nearby landmark or tap the map.");
      setPin(which, found[0].lat, found[0].lng, found[0].label);
      $(which).value = found[0].label;
    });
  }

  function locate() {
    return new Promise(function (resolve, reject) {
      var fail = function () { reject(new Error("Location is off. Type your pickup address in From.")); };
      if (!navigator.geolocation) return fail();
      navigator.geolocation.getCurrentPosition(function (pos) {
        setPin("from", pos.coords.latitude, pos.coords.longitude, "You");
        resolve();
      }, fail, { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 });
    });
  }

  $("route-form").addEventListener("submit", function (e) {
    e.preventDefault();
    showError("");
    close("from"); close("to");
    $("go").disabled = true; $("go").textContent = "Checking the route…";
    resolve("to").then(function () { return resolve("from"); }).then(function () {
      return fetch("/route", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start: points.from, end: points.to, hour: Number(hourSel.value) })
      });
    }).then(function (res) {
      if (res.status === 429) throw new Error("Too many tries. Wait a minute and try again.");
      if (!res.ok) throw new Error("Could not check this route. Try again.");
      return res.json();
    }).then(render).catch(function (err) {
      showError(err.message || "Could not reach Ride Radar. Check your connection.");
    }).then(function () {
      $("go").disabled = false; $("go").textContent = "Check this route";
    });
  });

  function render(r) {
    var box = $("result");
    box.hidden = false;
    box.setAttribute("data-level", r.level);
    $("level-word").textContent = WORD[r.level];
    $("reason").textContent = r.reason;
    $("sample-badge").hidden = !r.sample;
    line.clearLayers();
    $("hotspots").innerHTML = "";
    $("better").hidden = true;
    $("routing-note").hidden = r.routing !== "straight";
    if (r.level === "not_covered") { $("meta").textContent = ""; return; }

    $("meta").textContent = r.distance_km + " km · about " + r.minutes + " min · leaving " + pad(r.hour) + ":00";
    var bounds = [];
    r.segments.forEach(function (s) {
      L.polyline(s.coords, { color: color(s.level), weight: s.level === "green" ? 5 : 8, opacity: 0.9 }).addTo(line);
      bounds = bounds.concat(s.coords);
    });
    if (bounds.length) map.fitBounds(bounds, { padding: [24, 24] });

    r.hotspots.forEach(function (h) {
      var li = document.createElement("li");
      li.setAttribute("data-level", h.level);
      var b = document.createElement("strong");
      b.textContent = h.area + ": " + WORD[h.level];
      li.appendChild(b);
      li.appendChild(document.createTextNode(
        " · " + (h.km === 0 ? "at pickup" : "km " + h.km) + " · around " + pad(h.hour) + ":00 · " +
        h.count + " reported incident" + (h.count === 1 ? "" : "s")));
      $("hotspots").appendChild(li);
    });
    if (r.better_time) {
      var bt = r.better_time;
      $("better").textContent = "Leaving at " + pad(bt.hour) + ":00 instead (in " + bt.in_hours +
        " h) lowers this route to " + WORD[bt.level] + ".";
      $("better").hidden = false;
    }
    $("level-word").focus();
  }
})();
