// Simulated phone for the SMS demo. Uses /sms/simulate, which never sends a real message.
(function () {
  "use strict";
  var thread = document.getElementById("thread");

  function bubble(text, dir, note) {
    var b = document.createElement("div");
    b.className = "bubble " + dir;
    b.textContent = text;
    if (note) { var s = document.createElement("small"); s.textContent = note; b.appendChild(s); }
    thread.appendChild(b);
    thread.scrollTop = thread.scrollHeight;
  }

  document.getElementById("composer").addEventListener("submit", function (e) {
    e.preventDefault();
    var input = document.getElementById("msg");
    var text = input.value.trim();
    if (!text) return;
    bubble(text, "out");
    input.value = "";
    fetch("/sms/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: text })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, status: r.status, d: d }; }); })
      .then(function (res) {
        if (!res.ok) {
          bubble(res.status === 429 ? "Too many messages. Wait a minute." : "Not delivered: " + res.d.error, "in");
          return;
        }
        bubble(res.d.reply, "in", res.d.reply.length + "/160 characters");
      })
      .catch(function () { bubble("Not delivered. Check the server is running.", "in"); });
  });
})();
