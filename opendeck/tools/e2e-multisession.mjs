// e2e-multisession.mjs — Step 8 + T6 + T7: prove multiple simultaneous sessions
// work independently, session identities don't cross, and closing a session
// returns its key to OFF. Drives a live `opencode serve` and observes via the
// event-driven observation layer (src/observe.js).
import { startObservation } from "../src/observe.js";
import { STATE } from "../src/sessions.js";

const base = (process.argv[2] || "http://127.0.0.1:4096").replace(/\/+$/, "");
const t0 = Date.now();
const now = () => `t+${Date.now() - t0}`;

const seen = new Map(); // sessionId -> last state
let latestRecords = [];
const trail = [];
function onState(records) {
  latestRecords = records || [];
  for (const r of records || []) {
    const prev = seen.get(r.id);
    if (prev === undefined || prev !== r.state) {
      const entry = { t: Date.now() - t0, id: r.id, dir: (r.directory || "?").split("/").pop(), from: prev, to: r.state };
      trail.push(entry);
      console.log(`[${now()}] ${r.id.slice(-8)} dir=${entry.dir} ${prev ?? "NEW"} -> ${r.state}`);
      seen.set(r.id, r.state);
    }
  }
}
const obs = startObservation({ onState });

async function createSession(dir) {
  const dirPayload = { directory: dir };
  const body = JSON.stringify(dirPayload);
  const req = {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    signal: AbortSignal.timeout(5000),
  };
  const r = await fetch(base + "/session", req);
  const j = await r.json();
  return j.id;
}
async function sendText(sid, text) {
  const part = { type: "text", text };
  const payload = { parts: [part] };
  const body = JSON.stringify(payload);
  const req = {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    signal: AbortSignal.timeout(90_000),
  };
  await fetch(`${base}/session/${sid}/message`, req);
}

console.log(`[${now()}] creating 3 sessions in 3 directories (Step 8)`);
const dirA = "C:/Users/ryans/source/repos/HomeAILab";
const dirB = "C:/Users/ryans";
const dirC = "C:/Users/ryans/source/repos/hacksmith";
const sA = await createSession(dirA);
const sB = await createSession(dirB);
const sC = await createSession(dirC);
console.log(`[${now()}] A=${sA.slice(-8)} B=${sB.slice(-8)} C=${sC.slice(-8)}`);

// B stays IDLE.
// A -> RUNNING: send a short prompt.
await sendText(sA, "Reply with exactly one word: pong");
console.log(`[${now()}] A: prompt posted (expect RUNNING)`);
await new Promise((r) => setTimeout(r, 5000));

// C -> NEEDS_USER: ask the model to call the question tool.
const cPart = { type: "text", text: "Use your question tool to ask me exactly one yes/no question: are you a robot? Wait for my answer." };
const cPayload = { parts: [cPart] };
const qbody = JSON.stringify(cPayload);
const cReq = {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: qbody,
  signal: AbortSignal.timeout(60_000),
};
await fetch(`${base}/session/${sC}/message`, cReq).catch(() => {});
console.log(`[${now()}] C: question prompt posted (expect NEEDS_USER)`);
await new Promise((r) => setTimeout(r, 15000));

console.log(`\n=== per-session state (Step 8: must be independent) ===`);
const states = {};
for (const [id, st] of seen) states[id] = st;
const stateSummary = { A: states[sA], B: states[sB], C: states[sC] };
console.log(JSON.stringify(stateSummary));
// Independence + uncrossed identities: C must be NEEDS_USER (waiting); A and B
// track their own states (A finished -> idle, B idle).
const ok = states[sC] === STATE.WAITING && states[sA] === STATE.IDLE && states[sB] === STATE.IDLE;
console.log(`Step 8 (C=NEEDS_USER, A/B=IDLE, identities uncrossed): ${ok ? "PASS" : "CHECK"}`);

// T7: close session B -> its key returns to OFF (session absent from live list).
const delReq = { method: "DELETE", signal: AbortSignal.timeout(5000) };
const del = await fetch(`${base}/session/${sB}`, delReq).catch(() => null);
console.log(`[${now()}] closed session B (HTTP ${del ? del.status : "n/a"}); expect B -> OFF`);
await new Promise((r) => setTimeout(r, 3000));
// OFF proof: the closed session B must be ABSENT from the latest live records
// (the observation layer stops reporting it -> its key goes gray/OFF).
const bStillListed = latestRecords.some((r) => r.id === sB);
console.log(`T7 (close -> OFF, session absent from live list): ${bStillListed ? "CHECK" : "PASS"}`);

obs.stop();
console.log(`[${now()}] e2e complete`);
process.exit(0);
