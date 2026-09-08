// current-state.mjs — show what the opendeck plugin is currently displaying:
// for each project (homeai, ryans), compute the RAG state the plugin pushes
// (waiting=RED, running=GREEN, idle=AMBER, off=GRAY), so we can compare it
// against what is actually on the physical Stream Deck.
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { writeFileSync, readFileSync, existsSync } from "node:fs";
import { opencodeDbPath, resolveSqlite3, loadProjects } from "../src/config.js";
import { RUN_WINDOW_MS, deriveState } from "../src/observe.js";
import { STATE, STATE_COLOR } from "../src/sessions.js";

const exe = resolveSqlite3();
const db = opencodeDbPath();
const nowMs = Date.now();

const QUERY = `SELECT s.id, s.directory, s.title, s.time_updated AS upd,
  (SELECT MAX(p.time_updated) FROM part p WHERE p.session_id = s.id) AS last_part_upd,
  (SELECT COUNT(*) FROM part p WHERE p.session_id = s.id
     AND json_extract(p.data, '$.type') = 'tool'
     AND json_extract(p.data, '$.tool') = 'question'
     AND json_extract(p.data, '$.state.status') <> 'completed'
  ) AS pending_q
FROM session s
WHERE (s.time_archived IS NULL OR s.time_archived = 0)
ORDER BY s.time_updated DESC;`;

const f = join(tmpdir(), "opendeck-current-state.sql");
writeFileSync(f, QUERY, "utf8");

let out;
try {
  out = execFileSync(exe, ["-noheader", "-separator", "|", db, ".read " + f], { encoding: "utf8" });
} catch (e) {
  console.error("sqlite3 query failed:", e.message);
  process.exit(1);
}

// Fold to per-directory most-recent session (what plugin.js/agentStates does).
const byDir = new Map();
for (const line of out.trim().split("\n")) {
  const [id, directory, title, upd, lastPartUpd, pendingQ] = line.split("|");
  if (!id || !directory) continue;
  const cur = byDir.get(directory);
  const updMs = Number(upd) || 0;
  if (!cur || updMs > (Number(cur.upd) || 0)) {
    byDir.set(directory, { id, directory, title, upd: updMs, lastPartUpdMs: Number(lastPartUpd) || null, pendingQuestion: Number(pendingQ) || 0 });
  }
}

const { projects } = loadProjects({ repoRoot: process.cwd() });
console.log(`now=${new Date(nowMs).toISOString()}`);
console.log("");
for (const p of projects) {
  const norm = p.path.replace(/\\/g, "/").replace(/\/+$/, "");
  const rec = [...byDir.values()].find((r) => {
    const d = (r.directory || "").replace(/\\/g, "/").replace(/\/+$/, "");
    return d === norm || d.startsWith(norm + "/");
  });
  if (!rec) {
    console.log(`[${p.alias}] OFF (gray #5a5e6b) — no live session for ${norm}`);
    continue;
  }
  const state = deriveState({
    pendingQuestion: rec.pendingQuestion,
    lastPartUpdMs: rec.lastPartUpdMs,
    nowMs,
    runWindowMs: RUN_WINDOW_MS,
  });
  const color = STATE_COLOR[state];
  const ageMs = rec.lastPartUpdMs ? nowMs - rec.lastPartUpdMs : null;
  console.log(
    `[${p.alias}] ${state.toUpperCase()} (${color}) — session ${rec.id}, dir ${rec.directory}, last part update ${ageMs == null ? "n/a" : ageMs + "ms ago"}, pending questions: ${rec.pendingQuestion}`
  );
}
console.log("");
console.log("Expected device screen: the two project keys above; alert key RED only if any project is WAITING.");
