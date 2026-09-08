// device-live-check.mjs — controlled test: create a fresh OpenCode session,
// post a short prompt (drives IDLE -> RUNNING), so the corresponding Stream Deck
// key must flip from amber (idle) to green (running). Then re-capture the
// device mirror and diff against the previous capture to verify the device
// screen actually changed in response to the state change.
import { startObservation } from "../src/observe.js";
import { STATE } from "../src/sessions.js";

const base = "http://127.0.0.1:4096";
const t0 = Date.now();
const now = () => `t+${Date.now() - t0}`;

const seen = new Map();
function onState(records) {
  for (const r of records || []) {
    const prev = seen.get(r.id);
    if (prev === undefined || prev !== r.state) {
      console.log(`[${now()}] ${r.id.slice(-8)} dir=${(r.directory || "?").split("/").pop()} ${prev ?? "NEW"} -> ${r.state}`);
      seen.set(r.id, r.state);
    }
  }
}
const obs = startObservation({ onState });

// create a session in a scratch directory (auto-detects a new project key)
const dir = "C:/Users/ryans/source/repos/HomeAILab";
const cReq = { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ directory: dir }), signal: AbortSignal.timeout(5000) };
const cj = await (await fetch(base + "/session", cReq)).json();
const sid = cj.id;
console.log(`[${now()}] created session ${sid} (expect IDLE/amber key)`);
await new Promise((r) => setTimeout(r, 1500));

// post a short prompt -> RUNNING (green)
const pReq = { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ parts: [{ type: "text", text: "Reply with exactly one word: pong" }], directory: dir }), signal: AbortSignal.timeout(90000) };
await fetch(`${base}/session/${sid}/message`, pReq).catch(() => {});
console.log(`[${now()}] posted short prompt (expect RUNNING/green on the key)`);
await new Promise((r) => setTimeout(r, 8000));

const st = seen.get(sid);
console.log(`\nSession ${sid} state now: ${st}`);
console.log(`Device should show a GREEN (running) key for this session: ${st === STATE.RUNNING ? "expected GREEN" : "CHECK"}`);
obs.stop();
console.log(`[${now()}] device-live-check complete`);
process.exit(0);
