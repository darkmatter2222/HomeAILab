// probe-observe.mjs — Side Quest C: prove the DB-based detector distinguishes
// IDLE vs RUNNING vs NEEDS_USER on a real session, and measure transition latency.
//
// It starts the event-driven observation layer (src/observe.js) and drives a live
// `opencode serve`:
//   1. create a session  -> expect IDLE (amber)
//   2. POST a short prompt -> expect RUNNING (green) while it generates
//   3. POST a prompt that makes the model call the question tool -> expect
//      NEEDS_USER (red) while the question is pending
// Every state change from the observation layer is logged with a t+ms timestamp,
// which is the latency measurement the goal asks for.
//
// Usage: node tools/probe-observe.mjs [base]
import { startObservation } from "../src/observe.js";
import { STATE } from "../src/sessions.js";

const base = (process.argv[2] || "http://127.0.0.1:4096").replace(/\/+$/, "");
const t0 = Date.now();
const now = () => `t+${Date.now() - t0}`;

// Log every observation-layer state change (this is the latency trail).
const seen = new Map(); // sessionId -> last state
const changes = [];
function onState(records) {
  for (const r of records || []) {
    const prev = seen.get(r.id);
    if (prev === undefined || prev !== r.state) {
      const dt = Date.now() - t0;
      const label = { waiting: "NEEDS_USER(red)", running: "RUNNING(green)", idle: "IDLE(amber)", off: "OFF(gray)" }[r.state] || r.state;
      console.log(`[${now()}] ${r.id.slice(-8)} dir=${r.directory ? r.directory.split("/").pop() : "?"} ${prev === undefined ? "NEW" : prev} -> ${label}`);
      changes.push({ t: dt, id: r.id, from: prev, to: r.state });
      seen.set(r.id, r.state);
    }
  }
}

const obs = startObservation({ onState });
console.log(`[${now()}] observation layer started (watching ${"opencode.db" + " + WAL"})`);

// 1. Create a session -> IDLE
const cr = await fetch(base + "/session", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({}),
  signal: AbortSignal.timeout(5000),
});
const cj = await cr.json();
const sid = cj.id;
console.log(`[${now()}] created session ${sid} (expect IDLE)`);
await new Promise((r) => setTimeout(r, 1500));

// 2. Short prompt -> RUNNING
const b1 = JSON.stringify({ parts: [{ type: "text", text: "Reply with exactly one word: pong" }] });
try {
  await fetch(`${base}/session/${sid}/message`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: b1,
    signal: AbortSignal.timeout(20_000),
  });
  console.log(`[${now()}] posted short prompt (expect RUNNING while generating)`);
} catch (e) {
  console.log(`[${now()}] short prompt POST failed: ${e.message}`);
}
await new Promise((r) => setTimeout(r, 8000));

// 3. Question prompt -> NEEDS_USER
const b2 = JSON.stringify({
  parts: [
    {
      type: "text",
      text: "Use your question tool to ask me exactly one yes/no question: do you like pineapple on pizza? Wait for my answer before continuing.",
    },
  ],
});
try {
  const q = await fetch(`${base}/session/${sid}/message`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: b2,
    signal: AbortSignal.timeout(60_000),
  });
  console.log(`[${now()}] posted question prompt -> HTTP ${q.status} (expect NEEDS_USER while pending)`);
} catch (e) {
  console.log(`[${now()}] question prompt POST failed (timed out or aborted): ${e.message}`);
}
await new Promise((r) => setTimeout(r, 15000));

console.log(`[${now()}] === state-change trail (latency) ===`);
for (const c of changes) {
  console.log(`  t+${c.t}ms ${c.id.slice(-8)}: ${c.from ?? "NEW"} -> ${c.to}`);
}
obs.stop();
console.log(`[${now()}] probe complete`);
process.exit(0);
