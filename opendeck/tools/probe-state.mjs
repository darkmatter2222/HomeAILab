// probe-state.mjs — side-quest C: prove what signals OpenCode exposes for
// IDLE vs RUNNING vs NEEDS_USER.
//
// Runs a full experiment against a live `opencode serve`:
//   1. opens the /event SSE stream and logs every event (type + t+ms)
//   2. polls /session/status at 250ms to capture the status string transitions
//   3. POSTs a short prompt to a fresh session and records status around it
// Usage: node tools/probe-state.mjs [base] [sessionId?]
// If no sessionId is given, creates one (in the server's default directory).
const base = (process.argv[2] || "http://127.0.0.1:4096").replace(/\/+$/, "");
const givenId = process.argv[3] || null;
const t0 = Date.now();
const now = () => `t+${Date.now() - t0}`;

// 1. event stream
const res = await fetch(base + "/event");
console.log(`[${now()}] /event opened: HTTP ${res.status} ${res.headers.get("content-type")}`);
const reader = res.body.getReader();
const dec = new TextDecoder();
let buf = "";
const stream = (async () => {
  for (;;) {
    let value, done;
    try {
      ({ value, done } = await reader.read());
    } catch (e) {
      console.log(`[${now()}] event stream error: ${e.message}`);
      return;
    }
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line.startsWith("data:")) {
        let type = "?";
        let raw = line.slice(5);
        try {
          const p = JSON.parse(raw);
          type = p.type;
          if (type === "session.status" || type === "session.idle") {
            console.log(`[${now()}] ${type} ${raw.slice(0, 220)}`);
          } else {
            console.log(`[${now()}] EVENT ${type}`);
          }
        } catch {
          console.log(`[${now()}] EVENT ${type} raw=${raw.slice(0, 120)}`);
        }
      }
    }
  }
  console.log(`[${now()}] event stream closed`);
})();

// 2. status poller (short interval — diagnostic only; production uses events)
const statusTimer = setInterval(() => {
  (async () => {
    try {
      const r = await fetch(base + "/session/status", { signal: AbortSignal.timeout(3000) });
      const j = await r.json();
      const ids = Object.keys(j);
      const changed = ids.length ? ids.map((id) => `${id.slice(-6)}=${JSON.stringify(j[id])}`).join(" ") : "(empty)";
      console.log(`[${now()}] STATUS ${changed}`);
    } catch (e) {
      console.log(`[${now()}] status poll failed: ${e.message}`);
    }
  })();
}, 250);

// 3. session: reuse given or create
let sid = givenId;
if (!sid) {
  const r = await fetch(base + "/session", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({}),
    signal: AbortSignal.timeout(5000),
  });
  const j = await r.json();
  sid = j.id;
  console.log(`[${now()}] created session ${sid}`);
}
console.log(`[${now()}] sending prompt to ${sid}`);
const body = JSON.stringify({ parts: [{ type: "text", text: "Reply with exactly one word: pong" }] });
const mr = await fetch(`${base}/session/${sid}/message`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body,
  signal: AbortSignal.timeout(90_000),
});
console.log(`[${now()}] prompt POST -> HTTP ${mr.status}`);
await mr.text();
console.log(`[${now()}] prompt response received`);
await new Promise((r) => setTimeout(r, 3000));
clearInterval(statusTimer);
try { await reader.cancel(); } catch {}
await stream;
console.log(`[${now()}] probe complete`);
process.exit(0);
