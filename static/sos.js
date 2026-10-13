// SOS: hold to record, release to lock, countdown, PIN cancels, duress PIN sends silently.
(function () {
  "use strict";
  var STORE = "rr-sos-setup";
  var setup = null;
  try { setup = JSON.parse(localStorage.getItem(STORE) || "null"); } catch (e) { setup = null; }
  var alert = null;      // { id, key, url }
  var recorder = null, stream = null, queue = [], uploading = false, chunkIndex = 0;
  var geoWatch = null, lastPos = null, locTimer = null, countTimer = null, wakeLock = null;
  var pinEntry = "", sending = false;

  function $(id) { return document.getElementById(id); }
  function show(id) {
    ["setup", "ready", "locked", "done"].forEach(function (s) { $(s).hidden = s !== id; });
  }

  // ---------- PIN hashing (PBKDF2, WebCrypto) ----------
  function b64(buf) { return btoa(String.fromCharCode.apply(null, new Uint8Array(buf))); }
  function hashPin(pin, saltB64) {
    var salt = Uint8Array.from(atob(saltB64), function (c) { return c.charCodeAt(0); });
    return crypto.subtle.importKey("raw", new TextEncoder().encode(pin), "PBKDF2", false, ["deriveBits"])
      .then(function (k) {
        return crypto.subtle.deriveBits({ name: "PBKDF2", salt: salt, iterations: 150000, hash: "SHA-256" }, k, 256);
      }).then(b64);
  }

  // ---------- setup ----------
  function contactRow(c) {
    var wrap = document.createElement("div");
    wrap.className = "contact-row";
    wrap.innerHTML = '<input class="c-name" placeholder="Name" maxlength="40" aria-label="Contact name">' +
      '<input class="c-phone" placeholder="+91 98xxxxxxxx" inputmode="tel" aria-label="WhatsApp number">';
    wrap.querySelector(".c-name").value = (c && c.name) || "";
    wrap.querySelector(".c-phone").value = (c && c.phone) || "";
    $("contacts").appendChild(wrap);
  }

  function openSetup() {
    $("contacts").querySelectorAll(".contact-row").forEach(function (r) { r.remove(); });
    var list = (setup && setup.contacts) || [];
    (list.length ? list : [null]).forEach(contactRow);
    $("pin").value = ""; $("duress").value = "";
    show("setup");
  }

  $("add-contact").addEventListener("click", function () {
    if ($("contacts").querySelectorAll(".contact-row").length < 5) contactRow(null);
  });

  $("test-camera").addEventListener("click", function () {
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: true })
      .then(function (s) {
        s.getTracks().forEach(function (t) { t.stop(); });
        $("camera-status").textContent = "Camera and microphone allowed.";
      })
      .catch(function () { $("camera-status").textContent = "Camera blocked. Allow it in your browser settings."; });
    if (navigator.geolocation) navigator.geolocation.getCurrentPosition(function () {}, function () {});
  });

  $("setup-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var err = $("setup-error");
    var pin = $("pin").value, duress = $("duress").value;
    var contacts = [];
    $("contacts").querySelectorAll(".contact-row").forEach(function (r) {
      var name = r.querySelector(".c-name").value.trim();
      var phone = r.querySelector(".c-phone").value.replace(/[\s()-]/g, "");
      if (name || phone) contacts.push({ name: name, phone: phone });
    });
    var bad = contacts.filter(function (c) { return !c.name || !/^\+?[1-9]\d{7,14}$/.test(c.phone); });
    if (!contacts.length || bad.length) {
      err.textContent = "Add at least one contact with a name and full number, e.g. +919812345678.";
      err.hidden = false; return;
    }
    if (!/^\d{4,6}$/.test(pin) || !/^\d{4,6}$/.test(duress) || pin === duress) {
      err.textContent = "PINs must be 4 to 6 digits, and the two PINs must be different.";
      err.hidden = false; return;
    }
    var salt = b64(crypto.getRandomValues(new Uint8Array(16)));
    Promise.all([hashPin(pin, salt), hashPin(duress, salt)]).then(function (h) {
      setup = { contacts: contacts, salt: salt, pin: h[0], duress: h[1] };
      try { localStorage.setItem(STORE, JSON.stringify(setup)); } catch (x) { /* storage blocked */ }
      err.hidden = true;
      show("ready");
    });
  });

  // ---------- recording ----------
  function pickMime() {
    var options = ["video/webm;codecs=vp8,opus", "video/webm", "video/mp4"];
    for (var i = 0; i < options.length; i++) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported(options[i])) return options[i];
    }
    return "";
  }

  function pump() {
    if (uploading || !queue.length || !alert) return;
    uploading = true;
    var blob = queue[0];
    fetch("/sos/" + alert.id + "/chunk", {
      method: "POST", body: blob,
      headers: { "X-Owner-Key": alert.key, "X-Chunk-Index": String(chunkIndex),
                 "Content-Type": (blob.type || "video/webm").split(";")[0] }
    }).then(function (r) {
      if (r.ok) { queue.shift(); chunkIndex++; }
      else if (r.status === 409) { return r.json().then(function (d) { if (d.expected !== undefined) chunkIndex = d.expected; }); }
    }).catch(function () { /* offline: keep it queued and retry */ })
      .then(function () { uploading = false; setTimeout(pump, queue.length ? 0 : 500); });
  }

  function postLocation() {
    if (!alert || !lastPos) return;
    fetch("/sos/" + alert.id + "/location", {
      method: "POST", headers: { "Content-Type": "application/json", "X-Owner-Key": alert.key },
      body: JSON.stringify(lastPos)
    }).catch(function () {});
  }

  function startRecording() {
    if (alert) return;
    $("ready-error").hidden = true;
    $("hold").classList.add("recording");
    $("hold").textContent = "Recording… let go to lock";
    if (navigator.wakeLock) navigator.wakeLock.request("screen").then(function (w) { wakeLock = w; }).catch(function () {});
    if (navigator.geolocation) {
      geoWatch = navigator.geolocation.watchPosition(function (p) {
        lastPos = { lat: p.coords.latitude, lng: p.coords.longitude };
      }, function () {}, { enableHighAccuracy: true, maximumAge: 5000 });
    }
    var created = fetch("/sos", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ contacts: setup.contacts }, lastPos || {}))
    }).then(function (r) { if (!r.ok) throw r; return r.json(); })
      .then(function (d) {
        alert = { id: d.id, key: d.owner_key, url: d.alert_url };
        postLocation();
        locTimer = setInterval(postLocation, 10000);
        pump();
      });
    created.catch(function () {
      $("ready-error").textContent = "Could not reach the server. Call 112 now.";
      $("ready-error").hidden = false;
    });
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: true })
      .then(function (s) {
        stream = s;
        var mime = pickMime();
        recorder = new MediaRecorder(s, mime ? { mimeType: mime } : undefined);
        recorder.ondataavailable = function (ev) { if (ev.data && ev.data.size) { queue.push(ev.data); pump(); } };
        recorder.start(1000);  // a chunk every second, so little is lost if the phone is taken
      })
      .catch(function () {
        $("ready-error").textContent = "Camera unavailable. The alert still sends with your location.";
        $("ready-error").hidden = false;
      });
  }

  function release() {
    if (!$("hold").classList.contains("recording")) return;
    $("hold").classList.remove("recording");
    $("hold").textContent = "Hold to record";
    if (recorder && recorder.state !== "inactive") recorder.stop();
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    var waitForAlert = setInterval(function () {
      if (!alert) return;
      clearInterval(waitForAlert);
      fetch("/sos/" + alert.id + "/release", { method: "POST", headers: { "X-Owner-Key": alert.key } }).catch(function () {});
    }, 200);
    startCountdown();
  }

  // ---------- locked: countdown + PIN ----------
  function startCountdown() {
    var left = 10;
    pinEntry = ""; drawDots();
    $("pin-msg").textContent = "Enter your PIN to cancel a false alarm.";
    $("count").textContent = left;
    show("locked");
    countTimer = setInterval(function () {
      left--;
      $("count").textContent = Math.max(0, left);
      if (left <= 0) { clearInterval(countTimer); send(false); }
    }, 1000);
  }

  function drawDots() { $("pin-dots").textContent = pinEntry.replace(/./g, "●") || " "; }

  function buildKeypad() {
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "OK"].forEach(function (k) {
      var b = document.createElement("button");
      b.type = "button"; b.textContent = k; b.className = "key";
      if (k === "⌫") b.setAttribute("aria-label", "Delete");
      b.addEventListener("click", function () { onKey(k); });
      $("keypad").appendChild(b);
    });
  }

  function onKey(k) {
    if (sending) return;
    if (k === "⌫") pinEntry = pinEntry.slice(0, -1);
    else if (k === "OK") { checkPin(); return; }
    else if (pinEntry.length < 6) pinEntry += k;
    drawDots();
  }

  function checkPin() {
    var entered = pinEntry;
    pinEntry = ""; drawDots();
    hashPin(entered, setup.salt).then(function (h) {
      if (h === setup.pin) cancel();
      else if (h === setup.duress) send(true);
      else $("pin-msg").textContent = "Wrong PIN. The alert still sends when the timer ends.";
    });
  }

  function whenAlert(fn) {
    if (alert) { fn(); return; }
    var tries = 0;
    var t = setInterval(function () { if (alert || ++tries > 50) { clearInterval(t); if (alert) fn(); } }, 200);
  }

  function cleanup(keepLocation) {
    clearInterval(countTimer);
    if (!keepLocation) {
      clearInterval(locTimer);
      if (geoWatch !== null) navigator.geolocation.clearWatch(geoWatch);
    }
    if (wakeLock) { wakeLock.release().catch(function () {}); wakeLock = null; }
  }

  function cancel() {
    sending = true;
    cleanup(false);
    whenAlert(function () {
      fetch("/sos/" + alert.id + "/cancel", { method: "POST", headers: { "X-Owner-Key": alert.key } }).catch(function () {});
    });
    showCancelled();
  }

  function showCancelled() {
    $("done-title").textContent = "Cancelled";
    $("done-msg").textContent = "False alarm cancelled. The recording was deleted.";
    $("sent-actions").hidden = true;
    show("done");
    $("done-title").focus();
  }

  function send(duress) {
    if (sending) return;
    sending = true;
    cleanup(true);  // keep sharing location after a real alert
    if (duress) showCancelled();  // looks exactly like a cancel
    whenAlert(function () {
      var flush = setInterval(function () {
        if (queue.length && Date.now() - started < 8000) return;  // let the last chunks upload
        clearInterval(flush);
        var loc = lastPos ? fetch("/sos/" + alert.id + "/location", {
          method: "POST", headers: { "Content-Type": "application/json", "X-Owner-Key": alert.key },
          body: JSON.stringify(lastPos)
        }).catch(function () {}) : Promise.resolve();
        loc.then(function () { return fetch("/sos/" + alert.id + "/send", {
          method: "POST", headers: { "Content-Type": "application/json", "X-Owner-Key": alert.key },
          body: JSON.stringify({ duress: duress })
        }); }).then(function (r) { return r.json(); }).then(function (d) {
          if (!duress) showSent(d.whatsapp);
        }).catch(function () { if (!duress) showSent("offline"); });
      }, 300);
      var started = Date.now();
    });
  }

  function showSent(status) {
    $("done-title").textContent = "Alert sent";
    var auto = status === "sent";
    $("done-msg").textContent = auto
      ? "Your contacts were messaged on WhatsApp with your live location and the video."
      : status === "offline"
        ? "The server will still send it as soon as the recording reaches it. Call 112 if you can."
        : "Tap each contact below to send them the alert on WhatsApp.";
    $("wa-title").textContent = auto ? "Message them again on WhatsApp" : "Tell your contacts on WhatsApp";
    var box = $("wa-links");
    box.innerHTML = "";
    setup.contacts.forEach(function (c) {
      var a = document.createElement("a");
      a.className = "btn helpline secondary";
      a.target = "_blank"; a.rel = "noopener noreferrer";
      a.href = "https://wa.me/" + c.phone.replace(/\D/g, "") + "?text=" +
        encodeURIComponent(c.name + ", I need help. Live location and video from Ride Radar: " + alert.url);
      a.textContent = "WhatsApp " + c.name;
      box.appendChild(a);
    });
    $("sent-actions").hidden = false;
    show("done");
    $("done-title").focus();
  }

  // ---------- wiring ----------
  var hold = $("hold");
  hold.addEventListener("pointerdown", function (e) { e.preventDefault(); hold.setPointerCapture(e.pointerId); startRecording(); });
  hold.addEventListener("pointerup", release);
  hold.addEventListener("pointercancel", release);
  hold.addEventListener("contextmenu", function (e) { e.preventDefault(); });
  hold.addEventListener("keydown", function (e) { if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); startRecording(); } });
  hold.addEventListener("keyup", function (e) { if (e.key === " " || e.key === "Enter") release(); });
  $("send-now").addEventListener("click", function () { clearInterval(countTimer); send(false); });
  $("edit-setup").addEventListener("click", openSetup);
  $("done-back").addEventListener("click", function () { location.reload(); });
  buildKeypad();

  if (!window.MediaRecorder || !navigator.mediaDevices || !window.crypto || !crypto.subtle) {
    $("ready-error").textContent = "This browser cannot record video. The alert still sends with your location. Use HTTPS.";
    $("ready-error").hidden = false;
  }
  if (setup) show("ready"); else openSetup();
})();
