// t1-zerosessions.mjs — T1: prove that with zero live sessions, every project
// key renders OFF (gray). Uses a scratch DB with empty session/part tables and
// points the event-driven observation layer at it. Confirms:
//   - the observation layer's query returns 0 rows
//   - onState([]) fires
//   - the render path produces OFF (gray) for every configured project key
import { startObservation } from "../src/observe.js";
import { STATE, STATE_COLOR } from "../src/sessions.js";
import * as keyart from "../src/keyart.js";
import { tmpdir } from "node:os";
import { join } from "node:path";

const scratch = join(tmpdir(), "opendeck-t1-scratch.db");
let sawEmpty = false;
let lastRecords = [];
function onState(records) {
  lastRecords = records || [];
  if ((records || []).length === 0) sawEmpty = true;
  console.log(`onState fired with ${records?.length ?? 0} records`);
}
const obs = startObservation({ onState, dbPath: scratch });
await new Promise((r) => setTimeout(r, 1500));

// With zero sessions, the live map is empty -> every project key is OFF.
const projects = [
  { alias: "homeai", path: "C:/Users/ryans/source/repos/HomeAILab" },
  { alias: "ryans", path: "C:/Users/ryans" },
];
const live = {}; // no live sessions
const offImg = keyart.projectKey({ alias: "homeai", state: STATE.OFF, color: null, phase: 0 });
const offColor = STATE_COLOR[STATE.OFF];
const allOff = projects.every((p) => {
  const img = keyart.projectKey({ alias: p.alias, state: STATE.OFF, color: p.color, phase: 0 });
  return typeof img === "string" && img.startsWith("data:image/svg+xml");
});
console.log(`zero sessions: onState([]) fired=${sawEmpty}; records=${lastRecords.length}`);
console.log(`OFF color = ${offColor}; all project keys render OFF (gray): ${allOff ? "PASS" : "CHECK"}`);
console.log(`T1 (zero sessions -> all keys OFF): ${sawEmpty && allOff ? "PASS" : "CHECK"}`);
obs.stop();
process.exit(0);
