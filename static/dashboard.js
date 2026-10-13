// Authority dashboard: ranked areas, "Mark addressed" behind an optional officer token.
(function () {
  "use strict";
  var token = "";
  try { token = sessionStorage.getItem("rr-admin") || ""; } catch (e) { /* storage blocked */ }
  var authRequired = false;

  function $(id) { return document.getElementById(id); }

  function cell(row, text, cls) {
    var td = document.createElement("td");
    if (cls) td.className = cls;
    td.textContent = text;
    row.appendChild(td);
    return td;
  }

  function showError(msg) {
    $("error").textContent = msg;
    $("error").hidden = !msg;
  }

  function load() {
    fetch("/dashboard", { headers: { Accept: "application/json" }, cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        authRequired = data.auth_required;
        $("token-form").hidden = !authRequired || !!token;
        $("city-name").textContent = data.city;
        $("today").textContent = "As of " + data.today;
        var body = $("rows");
        body.innerHTML = "";
        if (!data.areas.length) {
          var tr = document.createElement("tr");
          cell(tr, "No incidents loaded yet. Run python scripts/seed.py to add them.").colSpan = 7;
          body.appendChild(tr);
        }
        var anySample = false;
        data.areas.forEach(function (a, i) {
          anySample = anySample || a.sample;
          var tr = document.createElement("tr");
          cell(tr, i + 1, "num");
          var name = cell(tr, a.area + " ");
          if (a.sample) {
            var b = document.createElement("span");
            b.className = "sample-badge"; b.textContent = "SAMPLE";
            name.appendChild(b);
          }
          var addressed = a.resolved_at && a.weeks_unresolved === 0;
          if (addressed) cell(tr, "Addressed " + a.resolved_at.slice(0, 10), "num resolved");
          else if (!a.flagged) cell(tr, "No recent reports", "num");
          else cell(tr, a.weeks_unresolved, "num" + (a.weeks_unresolved >= 12 ? " weeks-high" : ""));
          cell(tr, a.incidents, "num");
          cell(tr, a.weighted.toFixed(1), "num");
          cell(tr, a.last_incident);
          var act = cell(tr, "");
          var btn = document.createElement("button");
          btn.className = "btn secondary"; btn.type = "button"; btn.textContent = "Review";
          btn.setAttribute("aria-label", "Review " + a.area);
          btn.addEventListener("click", function () { openArea(a.area_id, true); });
          act.appendChild(btn);
          tr.className = "row-pick";
          if (a.area_id === current) tr.setAttribute("aria-current", "true");
          tr.addEventListener("click", function (e) { if (e.target.tagName === "TD") openArea(a.area_id, true); });
          body.appendChild(tr);
        });
        $("sample-badge").hidden = !anySample;
      })
      .catch(function () { showError("Could not load the dashboard. Reload the page."); });
  }

  // ---------- area review panel ----------
  var current = null, pmap = null, players = null;
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function nice(c) { c = c.replace(/_/g, " "); return c.charAt(0).toUpperCase() + c.slice(1); }

  function openArea(id, scroll) {
    current = id;
    fetch("/dashboard/area/" + id, { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (d) {
        renderArea(d);
        load();
        if (scroll) {
          $("panel").focus({ preventScroll: true });
          if (window.innerWidth < 1180) $("panel").scrollIntoView({ behavior: "smooth" });
        }
      })
      .catch(function () { showError("Could not load this area. Try again."); });
  }

  function renderArea(d) {
    $("panel-empty").hidden = true;
    $("panel-body").hidden = false;
    $("p-name").textContent = d.area;
    var f = d.flag, status;
    if (f && f.resolved_at) {
      status = "Addressed " + f.resolved_at.slice(0, 10) + (f.resolution_label ? ": " + f.resolution_label : "") +
        (f.resolution_note ? ". “" + f.resolution_note + "”" : "");
    } else if (f) {
      var weeks = Math.max(0, Math.floor((Date.now() - Date.parse(f.first_flagged_date)) / 6048e5));
      status = "Unresolved for " + weeks + " week" + (weeks === 1 ? "" : "s") + ", since " + f.first_flagged_date + ".";
    } else {
      status = "No reports in the last 12 months.";
    }
    $("p-status").textContent = status;
    $("p-status").className = "panel-status" + (f && !f.resolved_at ? " open" : "");
    $("p-gmaps").href = d.directions.google;
    $("p-osm").href = d.directions.osm;

    if (window.L) {
      if (!pmap) {
        pmap = L.map("p-map", { scrollWheelZoom: false });
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 18, attribution: "&copy; OpenStreetMap contributors"
        }).addTo(pmap);
        players = L.layerGroup().addTo(pmap);
      }
      players.clearLayers();
      pmap.setView([d.lat, d.lng], 14);
      L.circle([d.lat, d.lng], { radius: d.radius_km * 1000, color: "#1f2a44", weight: 1, fillOpacity: 0.06 }).addTo(players);
      d.incidents.forEach(function (i) {
        L.circleMarker([i.lat, i.lng], {
          radius: 6, weight: 1.5, color: "#1d1f22",
          fillColor: i.source_type === "report" ? "#ffffff" : "#a3161c", fillOpacity: 0.85
        }).bindTooltip(i.date + " · ~" + pad(i.hour) + ":00 · " + nice(i.category)).addTo(players);
      });
      setTimeout(function () { pmap.invalidateSize(); pmap.fitBounds(L.latLng(d.lat, d.lng).toBounds(d.radius_km * 2000), { padding: [8, 8] }); }, 0);
    }

    var max = Math.max.apply(null, d.by_hour.concat([1]));
    var bars = $("p-hours");
    bars.innerHTML = "";
    d.by_hour.forEach(function (n, h) {
      var b = document.createElement("span");
      b.style.height = (n ? 8 + 52 * n / max : 2) + "px";
      if (d.peak && ((h - d.peak.start + 24) % 24) < 3) b.className = "peak";
      b.title = pad(h) + ":00 · " + n;
      bars.appendChild(b);
    });
    $("p-peak").textContent = d.peak
      ? "Most reports between " + pad(d.peak.start) + ":00 and " + pad(d.peak.end) + ":00 (" + d.peak.count +
        " of " + d.count + "). Patrols and checks count most then."
      : "No incidents on record.";

    var cats = $("p-cats");
    cats.innerHTML = "";
    d.by_category.forEach(function (kv) {
      var li = document.createElement("li");
      var name = document.createElement("span"); name.textContent = nice(kv[0]);
      var n = document.createElement("strong"); n.textContent = kv[1];
      li.appendChild(name); li.appendChild(n);
      cats.appendChild(li);
    });
    $("p-trend").textContent = "Last 90 days: " + d.last_90_days + ". The 90 days before: " + d.previous_90_days + ".";
    var mix = [];
    if (d.news) mix.push(d.news + " news report" + (d.news === 1 ? "" : "s"));
    if (d.reports) mix.push(d.reports + " rider report" + (d.reports === 1 ? "" : "s") + " (not verified)");
    if (d.samples) mix.push(d.samples + " sample entr" + (d.samples === 1 ? "y" : "ies"));
    $("p-mix").textContent = mix.length ? "Sources: " + mix.join(", ") + "." : "";

    var canAct = f && !f.resolved_at && (!authRequired || token);
    $("p-resolve").hidden = !canAct;
    var sel = $("p-action");
    if (!sel.options.length) {
      var ph = document.createElement("option"); ph.value = ""; ph.textContent = "Choose an action";
      sel.appendChild(ph);
      Object.keys(d.actions).forEach(function (k) {
        var o = document.createElement("option"); o.value = k; o.textContent = d.actions[k]; sel.appendChild(o);
      });
    }

    var list = $("p-incidents");
    list.innerHTML = "";
    $("p-inc-title").textContent = "Reported incidents (" + d.count + ")";
    d.incidents.forEach(function (i) {
      var li = document.createElement("li");
      li.appendChild(document.createTextNode(i.snippet + " "));
      var meta = document.createElement("span");
      meta.className = "src-meta";
      meta.textContent = i.date + " · ~" + pad(i.hour) + ":00 · " + nice(i.category) + " · ";
      if (i.is_sample) {
        var b = document.createElement("span"); b.className = "sample-badge"; b.textContent = "SAMPLE";
        meta.appendChild(b);
      } else if (i.source_type === "report") {
        meta.appendChild(document.createTextNode("Rider report, not verified"));
      } else {
        var a = document.createElement("a");
        a.href = i.source_url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = "Read source";
        meta.appendChild(a);
      }
      li.appendChild(meta);
      list.appendChild(li);
    });
  }

  $("p-resolve").addEventListener("submit", function (e) {
    e.preventDefault();
    resolve(current, $("p-resolve").querySelector("button"), { action: $("p-action").value, note: $("p-note").value });
  });

  function resolve(id, btn, payload) {
    btn.disabled = true;
    showError("");
    var headers = { "Content-Type": "application/json" };
    if (token) headers.Authorization = "Bearer " + token;
    fetch("/dashboard/resolve/" + id, { method: "POST", headers: headers, body: JSON.stringify(payload) })
      .then(function (r) {
        if (r.status === 401) {
          token = "";
          try { sessionStorage.removeItem("rr-admin"); } catch (e) { /* storage blocked */ }
          throw new Error("That access token was not accepted.");
        }
        if (r.status === 429) throw new Error("Too many requests. Wait a minute and try again.");
        if (!r.ok) throw new Error("Could not mark the area addressed. Try again.");
        btn.disabled = false;
        $("p-note").value = ""; $("p-action").value = "";
        openArea(id, false);
      })
      .catch(function (e) { btn.disabled = false; showError(e.message); load(); });
  }

  $("token-form").addEventListener("submit", function (e) {
    e.preventDefault();
    token = $("token").value.trim();
    try { sessionStorage.setItem("rr-admin", token); } catch (err) { /* storage blocked */ }
    $("token").value = "";
    load();
  });

  load();
})();
