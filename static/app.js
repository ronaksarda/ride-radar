// Ride Radar one-tap screen. Plain JS, no build step.
(function () {
  "use strict";

  // All UI strings live here. The server's one-line reason stays in English.
  var STRINGS = {
    en: {
      langButton: "हिंदी",
      check: "Check this ride",
      checking: "Finding your location…",
      scoring: "Checking reports…",
      hint: "Uses your location and the current time. Nothing is stored.",
      pickArea: "Choose an area instead",
      gpsOff: "Location is off or unavailable. Pick the area you are in.",
      gpsDenied: "Location permission was denied. Pick the area you are in.",
      area: "Area",
      time: "Time",
      now: "Now",
      myLocation: "My current location",
      checkArea: "Check this area",
      share: "Share my trip",
      sendLink: "Send link",
      stopShare: "Stop sharing",
      again: "Check again",
      footnote: "Based on reported incidents only. No reports does not guarantee safety.",
      advice: "Consider waiting for a busier stop or a different time.",
      helpTitle: "Need help now?",
      routeCta: "Going somewhere? Check the whole route",
      dayTitle: "Same spot, every hour",
      dayCell: function (h, w) { return pad(h) + ":00, " + w + ". Tap to check this hour."; },
      betterTime: function (b) { return "Lower after " + pad(b.hour) + ":00 (" + STRINGS.en.word[b.level] + ", in " + b.in_hours + " h)."; },
      betterSpot: function (b) { return b.area + ", " + b.km + " km away, is " + STRINGS.en.word[b.level] + " at this hour."; },
      checkThere: "Check there",
      word: { green: "Green", amber: "Amber", red: "Red", not_covered: "Not covered yet" },
      label: {
        green_none: "No reported incidents nearby",
        green_few: "Few reported incidents nearby",
        amber: "Some reported incidents nearby",
        red: "Many reported incidents nearby",
        not_covered: "No data for this place"
      },
      sourcesTitle: "Reported incidents within 1 km",
      sampleSource: "Sample entry, no source link yet",
      riderReport: "Rider report, not verified",
      readSource: "Read source",
      vague: "News often gives only the area, so incidents are placed by area, not exact spot.",
      meta: function (r) {
        return r.count + " incident" + (r.count === 1 ? "" : "s") + " · checked for " + pad(r.hour) + ":00";
      },
      offline: function (t) { return "You are offline. Showing the last result from " + t + "."; },
      sharing: "Sharing your live location every 15 seconds. Keep this page open.",
      shareWaiting: "Link ready. Waiting for your location…",
      shareNoGps: "Link created, but location is off, so it cannot show where you are.",
      shareEnded: "Sharing stopped. The link no longer works.",
      shareExpired: "This trip link has ended.",
      copied: "Link copied. Paste it to a trusted contact.",
      networkError: "Could not reach Ride Radar. Check your connection and try again.",
      tooMany: "Too many tries. Wait a minute and try again.",
      reportOpen: "Report something that happened",
      reportTitle: "Report something that happened",
      reportIntro: "Anonymous. We keep only the area (about 100 m), the hour and the type. No names, no text, no phone number.",
      reportWhat: "What happened?",
      reportWhere: "Where?",
      reportSend: "Send report",
      reportSending: "Sending…",
      reportThanks: function (area) { return "Thank you. Your report near " + area + " now counts for other riders."; },
      cancel: "Cancel",
      cat_harassment: "Harassment or lewd remarks",
      cat_stalking: "I was followed",
      cat_fare_dispute_threat: "Threatened over the fare",
      cat_assault: "Physical assault",
      cat_other: "Something else felt unsafe"
    },
    hi: {
      langButton: "English",
      check: "इस सवारी की जाँच करें",
      checking: "आपकी लोकेशन ढूँढ रहे हैं…",
      scoring: "रिपोर्ट देख रहे हैं…",
      hint: "आपकी लोकेशन और अभी का समय इस्तेमाल होता है। कुछ भी सेव नहीं होता।",
      pickArea: "इलाका चुनें",
      gpsOff: "लोकेशन बंद है या उपलब्ध नहीं। अपना इलाका चुनें।",
      gpsDenied: "लोकेशन की अनुमति नहीं मिली। अपना इलाका चुनें।",
      area: "इलाका",
      time: "समय",
      now: "अभी",
      myLocation: "मेरी अभी की लोकेशन",
      checkArea: "इस इलाके की जाँच करें",
      share: "मेरी यात्रा शेयर करें",
      sendLink: "लिंक भेजें",
      stopShare: "शेयर करना बंद करें",
      again: "फिर से जाँचें",
      footnote: "सिर्फ़ दर्ज घटनाओं पर आधारित। कोई रिपोर्ट न होने का मतलब सुरक्षा की गारंटी नहीं है।",
      advice: "किसी ज़्यादा भीड़ वाले स्टॉप या दूसरे समय का इंतज़ार करने पर विचार करें।",
      helpTitle: "अभी मदद चाहिए?",
      routeCta: "कहीं जा रहे हैं? पूरा रास्ता जाँचें",
      dayTitle: "यही जगह, हर घंटे",
      dayCell: function (h, w) { return pad(h) + ":00, " + w + "। यह घंटा जाँचने के लिए टैप करें।"; },
      betterTime: function (b) { return pad(b.hour) + ":00 के बाद कम (" + STRINGS.hi.word[b.level] + ", " + b.in_hours + " घंटे में)।"; },
      betterSpot: function (b) { return b.area + ", " + b.km + " किमी दूर, इस समय " + STRINGS.hi.word[b.level] + " है।"; },
      checkThere: "वहाँ जाँचें",
      word: { green: "हरा", amber: "पीला", red: "लाल", not_covered: "अभी कवर नहीं" },
      label: {
        green_none: "आसपास कोई दर्ज घटना नहीं",
        green_few: "आसपास बहुत कम दर्ज घटनाएँ",
        amber: "आसपास कुछ दर्ज घटनाएँ",
        red: "आसपास कई दर्ज घटनाएँ",
        not_covered: "इस जगह का डेटा नहीं है"
      },
      sourcesTitle: "1 किमी के अंदर दर्ज घटनाएँ",
      sampleSource: "सैंपल एंट्री, अभी कोई स्रोत लिंक नहीं",
      riderReport: "सवारी की रिपोर्ट, जाँची नहीं गई",
      readSource: "स्रोत पढ़ें",
      vague: "खबरों में अक्सर सिर्फ़ इलाका होता है, इसलिए घटनाएँ इलाके के हिसाब से दिखाई गई हैं।",
      meta: function (r) { return r.count + " घटनाएँ · " + pad(r.hour) + ":00 के लिए"; },
      offline: function (t) { return "आप ऑफ़लाइन हैं। " + t + " का आख़िरी नतीजा दिखा रहे हैं।"; },
      sharing: "हर 15 सेकंड में आपकी लोकेशन शेयर हो रही है। यह पेज खुला रखें।",
      shareWaiting: "लिंक तैयार है। आपकी लोकेशन का इंतज़ार है…",
      shareNoGps: "लिंक बन गया, पर लोकेशन बंद है, इसलिए आपकी जगह नहीं दिखेगी।",
      shareEnded: "शेयर करना बंद हुआ। लिंक अब काम नहीं करेगा।",
      shareExpired: "यह यात्रा लिंक ख़त्म हो गया है।",
      copied: "लिंक कॉपी हो गया। किसी भरोसेमंद व्यक्ति को भेजें।",
      networkError: "Ride Radar से जुड़ नहीं पाए। कनेक्शन देखकर फिर कोशिश करें।",
      tooMany: "बहुत ज़्यादा कोशिशें। एक मिनट रुककर फिर कोशिश करें।",
      reportOpen: "जो हुआ उसकी रिपोर्ट करें",
      reportTitle: "जो हुआ उसकी रिपोर्ट करें",
      reportIntro: "गुमनाम। हम सिर्फ़ इलाका (लगभग 100 मीटर), घंटा और घटना का प्रकार रखते हैं। कोई नाम, टेक्स्ट या फ़ोन नंबर नहीं।",
      reportWhat: "क्या हुआ?",
      reportWhere: "कहाँ?",
      reportSend: "रिपोर्ट भेजें",
      reportSending: "भेज रहे हैं…",
      reportThanks: function (area) { return "धन्यवाद। " + area + " के पास आपकी रिपोर्ट अब दूसरी सवारियों के काम आएगी।"; },
      cancel: "रद्द करें",
      cat_harassment: "छेड़छाड़ या भद्दी बातें",
      cat_stalking: "मेरा पीछा किया गया",
      cat_fare_dispute_threat: "किराए पर धमकी",
      cat_assault: "शारीरिक हमला",
      cat_other: "कुछ और असुरक्षित लगा"
    }
  };

  var lang = "en";
  try { lang = localStorage.getItem("rr-lang") === "hi" ? "hi" : "en"; } catch (e) { /* storage blocked */ }
  var lastResult = null;
  var gps = { lat: null, lng: null };  // last GPS fix, kept only in this page's memory
  var share = { token: null, key: null, timer: null, watch: null, posted: false };
  var city = { areas: [], helplines: [] };

  function $(id) { return document.getElementById(id); }
  function t(key) { return STRINGS[lang][key]; }
  function pad(n) { return (n < 10 ? "0" : "") + n; }

  function applyLang() {
    document.documentElement.lang = lang === "hi" ? "hi" : "en";
    $("lang-toggle").textContent = t("langButton");
    var nodes = document.querySelectorAll("[data-i18n]");
    for (var i = 0; i < nodes.length; i++) {
      var val = t(nodes[i].getAttribute("data-i18n"));
      if (typeof val === "string") nodes[i].textContent = val;
    }
    fillHours($("hour-select"));
    fillHours($("report-hour"));
    if (city.areas.length) fillReportWhere();
    if (lastResult) render(lastResult.data, lastResult.offlineTime);
  }

  // ---------- helpers ----------
  function fillHours(sel) {
    var keep = sel.value;
    sel.innerHTML = "";
    var now = document.createElement("option");
    now.value = ""; now.textContent = t("now");
    sel.appendChild(now);
    for (var h = 0; h < 24; h++) {
      var o = document.createElement("option");
      o.value = h; o.textContent = pad(h) + ":00";
      sel.appendChild(o);
    }
    sel.value = keep;
  }

  function postJSON(url, body, headers) {
    var h = { "Content-Type": "application/json" };
    for (var k in headers || {}) h[k] = headers[k];
    return fetch(url, { method: "POST", headers: h, body: JSON.stringify(body) });
  }

  function errorText(res) {
    return res.status === 429 ? t("tooMany") : t("networkError");
  }

  var cityLoaded = null;
  function loadCity() {
    if (cityLoaded) return cityLoaded;
    cityLoaded = fetch("/areas").then(function (r) { return r.json(); }).then(function (data) {
      city = data;
      $("city-name").textContent = data.city;
      var sel = $("area-select");
      sel.innerHTML = "";
      data.areas.forEach(function (a) {
        var o = document.createElement("option");
        o.value = a.lat + "," + a.lng; o.textContent = a.name;
        sel.appendChild(o);
      });
      fillReportWhere();
    }).catch(function (e) { cityLoaded = null; throw e; });
    return cityLoaded;
  }

  function fillReportWhere() {
    var sel = $("report-where");
    var keep = sel.value;
    sel.innerHTML = "";
    if (gps.lat !== null) {
      var me = document.createElement("option");
      me.value = "gps"; me.textContent = t("myLocation");
      sel.appendChild(me);
    }
    city.areas.forEach(function (a) {
      var o = document.createElement("option");
      o.value = a.lat + "," + a.lng; o.textContent = a.name;
      sel.appendChild(o);
    });
    if (keep) sel.value = keep;
  }

  function showOnly(id) {
    ["home", "result", "report"].forEach(function (s) { $(s).hidden = s !== id; });
    window.scrollTo(0, 0);
  }

  // ---------- area fallback ----------
  function showFallback(reasonKey) {
    $("fallback-reason").textContent = t(reasonKey || "gpsOff");
    $("fallback-reason").setAttribute("data-i18n", reasonKey || "gpsOff");
    $("fallback").hidden = false;
    loadCity().then(function () { $("area-select").focus(); })
      .catch(function () { showError(t("networkError")); });
  }

  // ---------- check ----------
  function setBusy(busy, textKey) {
    var btn = $("check-btn");
    btn.disabled = busy;
    btn.textContent = t(busy ? textKey : "check");
  }

  function showError(msg) {
    var el = $("home-error");
    el.textContent = msg;
    el.hidden = !msg;
  }

  var lastQuery = null;
  function runCheck(lat, lng, hour) {
    lastQuery = { lat: lat, lng: lng };
    setBusy(true, "scoring");
    showError("");
    var body = { lat: lat, lng: lng };
    if (hour !== null && hour !== undefined && hour !== "") body.hour = Number(hour);
    return postJSON("/check", body).then(function (res) {
      var cachedAt = res.headers.get("X-Ride-Radar-Cached-At");
      if (!res.ok) { showError(errorText(res)); return; }
      return res.json().then(function (data) {
        render(data, cachedAt ? new Date(cachedAt).toLocaleTimeString() : null);
      });
    }).catch(function () {
      showError(t("networkError"));
    }).then(function () { setBusy(false); });
  }

  function onCheckTap() {
    showError("");
    if (!("geolocation" in navigator)) { showFallback("gpsOff"); return; }
    setBusy(true, "checking");
    navigator.geolocation.getCurrentPosition(function (pos) {
      gps.lat = pos.coords.latitude; gps.lng = pos.coords.longitude;
      runCheck(gps.lat, gps.lng, null);
    }, function (err) {
      setBusy(false);
      showFallback(err.code === 1 ? "gpsDenied" : "gpsOff");
    }, { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 });
  }

  // ---------- result ----------
  function render(r, offlineTime) {
    lastResult = { data: r, offlineTime: offlineTime };
    var level = r.level;
    $("result").setAttribute("data-level", level);
    $("level-word").textContent = t("word")[level];
    var labelKey = level === "green" ? (r.count === 0 ? "green_none" : "green_few") : level;
    $("level-label").textContent = t("label")[labelKey];
    $("reason").textContent = r.reason;
    $("meta").textContent = level === "not_covered" ? "" : t("meta")(r);
    $("sample-badge").hidden = !r.sample;
    $("offline-note").hidden = !offlineTime;
    if (offlineTime) $("offline-note").textContent = t("offline")(offlineTime);

    var risky = level === "amber" || level === "red";
    $("advice").hidden = !risky;
    $("advice").textContent = t("advice");
    $("share-btn").hidden = level !== "red" || !!share.token;
    renderOptions(risky ? r : null);
    renderDay(r);
    renderHelplines(risky ? (r.helplines || []) : []);
    renderSources(r.sources || []);

    var wasHidden = $("result").hidden;
    showOnly("result");
    if (wasHidden) $("level-word").focus();
  }

  function renderOptions(r) {
    var box = $("options");
    box.innerHTML = "";
    if (r && r.better_time) {
      var li = document.createElement("li");
      li.textContent = t("betterTime")(r.better_time);
      box.appendChild(li);
    }
    if (r && r.better_spot) {
      var b = r.better_spot;
      var li2 = document.createElement("li");
      li2.appendChild(document.createTextNode(t("betterSpot")(b) + " "));
      var btn = document.createElement("button");
      btn.type = "button"; btn.className = "linkish";
      btn.textContent = t("checkThere");
      btn.addEventListener("click", function () { runCheck(b.lat, b.lng, r.hour); });
      li2.appendChild(btn);
      box.appendChild(li2);
    }
    box.hidden = !box.children.length;
  }

  function renderDay(r) {
    var strip = $("day-strip");
    strip.innerHTML = "";
    var hours = r.hours || [];
    $("day").hidden = !hours.length || !lastQuery;
    hours.forEach(function (h) {
      var c = document.createElement("button");
      c.type = "button";
      c.className = "day-cell";
      c.setAttribute("data-level", h.level);
      if (h.hour === r.hour) c.setAttribute("aria-current", "true");
      c.setAttribute("aria-label", t("dayCell")(h.hour, t("word")[h.level]));
      c.title = pad(h.hour) + ":00";
      c.addEventListener("click", function () {
        if (lastQuery) runCheck(lastQuery.lat, lastQuery.lng, h.hour);
      });
      strip.appendChild(c);
    });
  }

  function renderHelplines(list) {
    var box = $("helpline-list");
    box.innerHTML = "";
    list.forEach(function (h, i) {
      var a = document.createElement("a");
      a.className = "btn helpline" + (i === 0 ? " primary" : " secondary");
      a.href = h.href;
      if (/^https?:/.test(h.href)) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
      a.textContent = h.label + " · " + h.number;
      box.appendChild(a);
    });
    $("helplines").hidden = list.length === 0;
  }

  function renderSources(sources) {
    var list = $("sources");
    list.innerHTML = "";
    if (!sources.length) return;
    var h = document.createElement("h2");
    h.textContent = t("sourcesTitle");
    list.appendChild(h);
    sources.forEach(function (s) {
      var li = document.createElement("li");
      li.appendChild(document.createTextNode(s.snippet + " "));
      var meta = document.createElement("span");
      meta.className = "src-meta";
      meta.textContent = s.area + " · " + s.category.replace(/_/g, " ") + " · " + s.date + " · ~" + pad(s.hour) + ":00 · ";
      if (s.is_sample) {
        var b = document.createElement("span");
        b.className = "sample-badge";
        b.textContent = "SAMPLE DATA";
        meta.appendChild(b);
        meta.appendChild(document.createTextNode(" " + t("sampleSource")));
      } else if (!/^https?:\/\//.test(s.source_url || "")) {
        meta.appendChild(document.createTextNode(t("riderReport")));
      } else {
        var a = document.createElement("a");
        a.href = s.source_url; a.target = "_blank"; a.rel = "noopener noreferrer";
        a.textContent = t("readSource") + " (" + hostOf(s.source_url) + ")";
        meta.appendChild(a);
      }
      li.appendChild(meta);
      list.appendChild(li);
    });
    var note = document.createElement("li");
    note.className = "src-meta";
    note.textContent = t("vague");
    list.appendChild(note);
  }

  function hostOf(url) {
    try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return url; }
  }

  function backHome() {
    lastResult = null;
    showOnly("home");
    $("check-btn").focus();
  }

  // ---------- trip share ----------
  function postLocation() {
    if (!share.token || gps.lat === null) return;
    postJSON("/trip/" + share.token + "/update", { lat: gps.lat, lng: gps.lng }, { "X-Owner-Key": share.key })
      .then(function (res) {
        if (res.status === 404) { endShare(t("shareExpired")); return; }
        if (res.ok && !share.posted) { share.posted = true; $("share-status").textContent = t("sharing"); }
      }).catch(function () { /* retry next tick */ });
  }

  function startShare() {
    $("share-btn").disabled = true;
    fetch("/share", { method: "POST" }).then(function (res) {
      if (!res.ok) throw res;
      return res.json();
    }).then(function (data) {
      share.token = data.token;
      share.key = data.owner_key;
      share.posted = false;
      $("share-btn").hidden = true;
      $("share-box").hidden = false;
      $("share-send").hidden = false;
      $("share-stop").hidden = false;
      $("share-url").value = data.url;
      $("share-status").textContent = t("shareWaiting");
      if ("geolocation" in navigator) {
        share.watch = navigator.geolocation.watchPosition(function (pos) {
          var first = gps.lat === null || !share.posted;
          gps.lat = pos.coords.latitude; gps.lng = pos.coords.longitude;
          if (first) postLocation();
        }, function () {
          if (gps.lat === null) $("share-status").textContent = t("shareNoGps");
        }, { enableHighAccuracy: true, maximumAge: 10000 });
      }
      postLocation();
      share.timer = setInterval(postLocation, 15000);
      sendLink();
    }).catch(function (res) {
      $("share-btn").disabled = false;
      $("share-status").textContent = res && res.status ? errorText(res) : t("networkError");
      $("share-box").hidden = false;
    });
  }

  function sendLink() {
    var url = $("share-url").value;
    if (navigator.share) {
      navigator.share({ title: "Ride Radar trip", text: "Follow my ride live:", url: url }).catch(function () {});
    } else if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(function () {
        $("share-status").textContent = t("copied");
      }).catch(function () { $("share-url").select(); });
    } else {
      $("share-url").select();
    }
  }

  function endShare(message) {
    clearInterval(share.timer);
    if (share.watch !== null && navigator.geolocation) navigator.geolocation.clearWatch(share.watch);
    share.token = null; share.key = null; share.timer = null; share.watch = null;
    $("share-status").textContent = message;
    $("share-send").hidden = true;
    $("share-stop").hidden = true;
  }

  function stopShare() {
    var token = share.token, key = share.key;
    endShare(t("shareEnded"));
    if (token) {
      fetch("/trip/" + token, { method: "DELETE", headers: { "X-Owner-Key": key } }).catch(function () {});
    }
  }

  // ---------- rider report ----------
  function openReport() {
    $("report-status").textContent = "";
    showOnly("report");
    loadCity().then(function () { $("report-title").focus(); })
      .catch(function () { $("report-status").textContent = t("networkError"); });
  }

  function sendReport(e) {
    e.preventDefault();
    var form = $("report-form");
    var choice = form.querySelector("input[name=category]:checked");
    if (!choice) return;
    var where = $("report-where").value;
    var lat, lng;
    if (where === "gps") { lat = gps.lat; lng = gps.lng; }
    else { var p = where.split(","); lat = Number(p[0]); lng = Number(p[1]); }
    var body = { lat: lat, lng: lng, category: choice.value };
    if ($("report-hour").value !== "") body.hour = Number($("report-hour").value);
    var btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    $("report-status").textContent = t("reportSending");
    postJSON("/report", body).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) throw { status: res.status, message: data.error };
        $("report-status").textContent = t("reportThanks")(data.area);
        form.reset();
      });
    }).catch(function (err) {
      $("report-status").textContent = err && err.status === 429 ? t("tooMany")
        : (err && err.message) || t("networkError");
    }).then(function () { btn.disabled = false; });
  }

  // ---------- wiring ----------
  $("check-btn").addEventListener("click", onCheckTap);
  $("pick-area").addEventListener("click", function () { showFallback("gpsOff"); });
  $("open-report").addEventListener("click", openReport);
  $("report-cancel").addEventListener("click", backHome);
  $("report-form").addEventListener("submit", sendReport);
  $("fallback").addEventListener("submit", function (e) {
    e.preventDefault();
    var parts = $("area-select").value.split(",");
    runCheck(Number(parts[0]), Number(parts[1]), $("hour-select").value);
  });
  $("again-btn").addEventListener("click", backHome);
  $("share-btn").addEventListener("click", startShare);
  $("share-send").addEventListener("click", sendLink);
  $("share-stop").addEventListener("click", stopShare);
  $("lang-toggle").addEventListener("click", function () {
    lang = lang === "en" ? "hi" : "en";
    try { localStorage.setItem("rr-lang", lang); } catch (e) { /* storage blocked */ }
    applyLang();
  });

  applyLang();

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () { /* offline shell is optional */ });
  }
})();
