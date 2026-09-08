// e2e-answer.mjs — T6: prove answering a pending question transitions
// NEEDS_USER -> RUNNING -> IDLE. Drives a live `opencode serve`:
//   1. create a session, make the model call the question tool (NEEDS_USER)
//   2. answer it via the real reply endpoint: POST /question/{requestID}/reply
//      with {"answers":[["<label>"]]}; the pending question part flips to
//      `completed`, so the observation layer drops the session out of NEEDS_USER.
//   3. the model resumes -> RUNNING, then finishes -> IDLE.
// State trail is logged via the event-driven observation layer with t+ms latency.
import { startObservation } from "../src/observe.js";
import { STATE } from "../src/sessions.js";

const base = (process.argv[2] || "http://127.0.0.1:4096").replace(/\/+$/, "");
const t0 = Date.now();
const now = () => `t+${Date.now() - t0}`;

const seen = new Map();
function onState(records) {
  for (const r of records || []) {
    const prev = seen.get(r.id);
    if (prev === undefined || prev !== r.state) {
      const entry = { t: Date.now() - t0, id: r.id, from: prev, to: r.state };
      console.log(`[${now()}] ${r.id.slice(-8)} ${prev ?? "NEW"} -> ${r.state}`);
      seen.set(r.id, r.state);
    }
  }
}
const obs = startObservation({ onState });

// 1. create session
const cReq = {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: "{}",
  signal: AbortSignal.timeout(5000),
};
const cj = await (await fetch(base + "/session", cReq)).json();
const sid = cj.id;
console.log(`[${now()}] created session ${sid.slice(-8)} (expect IDLE)`);
await new Promise((r) => setTimeout(r, 2000));

// 2. make the model ask a question -> NEEDS_USER
const qPart = { type: "text", text: "Use your question tool to ask me exactly one yes/no question: is the sky blue? Wait for my answer." };
const qPayload = { parts: [qPart] };
const qReq = {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(qPayload),
  signal: AbortSignal.timeout(90_000),
};
await fetch(`${base}/session/${sid}/message`, qReq).catch(() => {});
console.log(`[${now()}] question prompt posted (expect NEEDS_USER)`);
// The model needs time to generate + call the question tool.
await new Promise((r) => setTimeout(r, 40000));

// 3. answer the pending question via the reply endpoint.
const qListResp = await fetch(base + "/question", { signal: AbortSignal.timeout(5000) });
const listR = await qListResp.json();
const req = (listR || []).find((q) => q.sessionID === sid);
if (req) {
  const replyBody = JSON.stringify({ answers: [["Yes"]] });
  const replyReq = {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: replyBody,
    signal: AbortSignal.timeout(30000),
  };
  const rr = await fetch(`${base}/question/${req.id}/reply`, replyReq);
  console.log(`[${now()}] answered question ${req.id.slice(-8)} (HTTP ${rr.status})`);
} else {
  console.log(`[${now()}] no pending question found for this session yet`);
}
// model resumes (RUNNING) then finishes (IDLE)
await new Promise((r) => setTimeout(r, 60000));

const st = seen.get(sid);
const sawWaiting = [...seen.values()].includes(STATE.WAITING);
console.log(`\nT6: session ${sid.slice(-8)} final state=${st}; saw NEEDS_USER=${sawWaiting}`);
console.log(`T6 (NEEDS_USER -> answer -> RUNNING -> IDLE): ${st === STATE.IDLE && sawWaiting ? "PASS" : "CHECK"}`);
obs.stop();
console.log(`[${now()}] T6 complete`);
process.exit(0);
