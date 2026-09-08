// observe.js — event-driven observation of OpenCode sessions from the global DB.
//
// The global OpenCode SQLite store (~/.local/share/opencode/opencode.db) is the
// shared source of truth: it records TUI sessions AND serve-hosted sessions.
// We do NOT rely on the serve /session/status endpoint, which returns {} for
// TUI sessions.
//
// Deterministic state signals (no timer-guessing beyond the RUNNING window):
//   - Session row present (not archived)  -> not OFF
//   - A pending `question` tool part (state.status != "completed") -> NEEDS_USER (red)
//   - MAX(part.time_updated) within RUN_WINDOW_MS -> RUNNING (green)
//   - otherwise -> IDLE (amber)
//   - No session row / archived -> OFF (gray)
//
// Observation is event-driven: `fs.watch` on the .db and .db-wal files. Any DB
// write fires a watcher, which debounces and runs ONE sqlite3 CLI query. A short
// eval tick (default 1s) re-runs the query to catch the two transitions that do
// NOT produce a DB write: RUNNING->IDLE (last part update ages past the window)
// and ACTIVE->OFF (session closed/archived).

import { watch, existsSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { opencodeDbPath, resolveSqlite3 } from "./config.js";
import { STATE } from "./sessions.js";

export const RUN_WINDOW_MS = 15_000; // last part update within 15s => still RUNNING

// Pure state derivation. Deterministic: pending question wins (NEEDS_USER),
// then recency of the last part update (RUNNING window), else IDLE.
export function deriveState({
  pendingQuestion = 0,
  lastPartUpdMs = null,
  nowMs = Date.now(),
  runWindowMs = RUN_WINDOW_MS,
} = {}) {
  if (pendingQuestion > 0) return STATE.WAITING;
  if (lastPartUpdMs != null && nowMs - lastPartUpdMs < runWindowMs) return STATE.RUNNING;
  return STATE.IDLE;
}

// Single CLI query: per-session signals in one round-trip.
const QUERY = `SELECT s.id, s.directory, s.title, s.time_updated AS upd,
  (SELECT MAX(p.time_updated) FROM part p WHERE p.session_id = s.id) AS last_part_upd,
  (SELECT COUNT(*) FROM part p WHERE p.session_id = s.id
     AND json_extract(p.data,'\$.type')='tool'
     AND json_extract(p.data,'\$.tool')='question'
     AND json_extract(p.data,'\$.state.status') != 'completed'
  ) AS pending_q
FROM session s
WHERE (s.time_archived IS NULL OR s.time_archived = 0)
ORDER BY s.time_updated DESC;`;

// Write the query to a temp file so the sqlite3 CLI reads it (`.read <file>`).
// This keeps the `$.json` paths intact (no shell `$` mangling).
function writeQueryFile() {
  const f = join(tmpdir(), "opendeck-observe.sql");
  writeFileSync(f, QUERY, "utf8");
  return f;
}

// Parse the CLI output (pipe-separated) into session records with derived state.
// `lines` are the raw CLI stdout lines.
export function parseRecords(lines, { nowMs = Date.now(), runWindowMs = RUN_WINDOW_MS } = {}) {
  const out = [];
  for (const raw of lines) {
    const line = String(raw || "").trim();
    if (!line) continue;
    const [id, directory, title, upd, lastPartUpd, pendingQ] = line.split("|");
    if (!id) continue;
    const rec = {
      id,
      directory: directory || null,
      title: title || null,
      updatedAtMs: upd ? Number(upd) : null,
      lastPartUpdMs: lastPartUpd ? Number(lastPartUpd) : null,
      pendingQuestion: pendingQ ? Number(pendingQ) : 0,
    };
    rec.state = deriveState({
      pendingQuestion: rec.pendingQuestion,
      lastPartUpdMs: rec.lastPartUpdMs,
      nowMs,
      runWindowMs,
    });
    out.push(rec);
  }
  return out;
}

// Start the event-driven observation. Returns { stop }.
//   onState(records) fires on every DB change (debounced) and on each eval tick.
//   records: [{ id, directory, title, updatedAtMs, lastPartUpdMs, pendingQuestion, state }]
//   - no records (no live sessions) => onState([]) => all keys OFF.
export function startObservation({
  onState,
  dbPath = null,
  sqlite3Exe = null,
  evalMs = 1000,
  debounceMs = 200,
  runWindowMs = RUN_WINDOW_MS,
} = {}) {
  const exe = sqlite3Exe || resolveSqlite3();
  const db = dbPath || opencodeDbPath();
  if (!exe || !existsSync(db)) {
    onState?.([]);
    return { stop() {} };
  }

  const sqlFile = writeQueryFile();
  const watchers = [];
  let debounceTimer = null;
  let evalTimer = null;

  function runQuery() {
    let out;
    try {
      // The sqlite3 CLI parses ".read <file>" as one argument.
      out = execFileSync(exe, ["-noheader", "-separator", "|", db, ".read " + sqlFile], {
        encoding: "utf8",
        timeout: 10_000,
      });
    } catch (e) {
      onState?.([]);
      return;
    }
    const nowMs = Date.now();
    const records = parseRecords(out.trim().split("\n"), { nowMs, runWindowMs });
    onState?.(records);
  }

  // Event-driven trigger: watch the main DB and the WAL. Coalesce bursts.
  for (const f of [db, db + "-wal"]) {
    if (!existsSync(f)) continue;
    const w = watch(f);
    w.on("change", () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(runQuery, debounceMs);
    });
    w.on("error", () => {});
    watchers.push(w);
  }
  // Safety-net tick: re-evaluate every evalMs (catches RUNNING->IDLE and ->OFF,
  // which are the transitions that don't themselves write to the DB).
  evalTimer = setInterval(runQuery, evalMs);

  runQuery();
  return {
    stop() {
      for (const w of watchers) w.close();
      if (debounceTimer) clearTimeout(debounceTimer);
      if (evalTimer) clearInterval(evalTimer);
    },
  };
}

export default { deriveState, parseRecords, startObservation, RUN_WINDOW_MS, QUERY };
