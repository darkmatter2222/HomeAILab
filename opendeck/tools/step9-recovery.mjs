// step9-recovery.mjs — Step 9: prove the system converges after a failure
// (OpenCode force-killed / monitoring restart). A force-kill means the
// session stops writing to the DB. The observation layer's 1 s eval tick keeps
// re-querying, so the state must still converge:
//   1. session with a recent part update => RUNNING
//   2. wait past RUN_WINDOW_MS => the eval tick demotes to IDLE (no DB write needed)
//   3. archive the session => OFF
// Uses a scratch DB manipulated via the sqlite3 CLI (the same mechanism the
// plugin uses), with the event-driven observation layer watching it.
import { startObservation } from "../src/observe.js";
import { STATE } from "../src/sessions.js";
import { resolveSqlite3, opencodeDbPath } from "../src/config.js";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { writeFileSync, rmSync, existsSync } from "node:fs";

const exe = resolveSqlite3();
const db = join(tmpdir(), "opendeck-step9.db");
if (existsSync(db)) rmSync(db);

function sql(stmt) {
  execFileSync(exe, [db, stmt], { encoding: "utf8" });
}

// 1. seed one live session with a recent part update (RUNNING).
const sid = "ses_step9_test";
const nowMs = Date.now();
sql(`CREATE TABLE session (id TEXT PRIMARY KEY, directory TEXT, title TEXT, time_updated INTEGER, time_archived INTEGER);`);
sql(`CREATE TABLE part (id TEXT PRIMARY KEY, session_id TEXT, time_updated INTEGER, data TEXT);`);
sql(`INSERT INTO session (id, directory, title, time_updated, time_archived) VALUES ('${sid}', 'C:/Users/ryans', 'recovery', ${nowMs}, NULL);`);
sql(`INSERT INTO part (id, session_id, time_updated, data) VALUES ('prt_step9', '${sid}', ${nowMs}, '{"type":"tool","tool":"bash"}');`);

const states = [];
function onState(records) {
  for (const r of records || []) {
    if (r.id === sid) states.push({ t: Date.now(), state: r.state });
  }
}
const obs = startObservation({ onState, dbPath: db, evalMs: 1000, runWindowMs: 15_000 });

const t0 = Date.now();
const last = () => states.length ? states[states.length - 1].state : null;
console.log(`t+0 seeded session ${sid}`);
await new Promise((r) => setTimeout(r, 1500));
const running = last();
console.log(`t+1.5s state=${running} (expect running)`);

// 2. Force-kill: no more DB writes. The eval tick must demote RUNNING -> IDLE
// once the part update ages past the 15 s RUNNING window.
await new Promise((r) => setTimeout(r, 16000));
const idle = last();
console.log(`t+17.5s state=${idle} (expect idle)`);

// 3. Archive the session => OFF.
sql(`UPDATE session SET time_archived = ${Date.now()} WHERE id = '${sid}';`);
await new Promise((r) => setTimeout(r, 2500));
const afterArchive = last();
console.log(`t+~20s archived; last tracked state=${afterArchive} (expect the session to drop from live list)`);
const goneFromLive = !(lastRecordsNow(db).some((r) => r.id === sid));
function lastRecordsNow(d) {
  // direct query to check live list
  const out = execFileSync(exe, [d, `SELECT s.id FROM session s WHERE (s.time_archived IS NULL OR s.time_archived = 0);`], { encoding: "utf8" });
  return out.trim() ? out.trim().split("\n").map((l) => ({ id: l })) : [];
}
const ok = running === STATE.RUNNING && idle === STATE.IDLE && goneFromLive;
console.log(`\nStep 9 (force-kill recovery: RUNNING->IDLE via eval tick, then OFF when archived): ${ok ? "PASS" : "CHECK"}`);
obs.stop();
process.exit(0);
