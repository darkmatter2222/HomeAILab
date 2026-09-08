// sessions.js — discover live OpenCode sessions and compute their RAG state.
//
// We poll a running `opencode serve` HTTP server (the headless backend the
// launchers start on 127.0.0.1:4096). Two endpoints feed the deck:
//   GET /session         — every session (id, directory, title, time.updated)
//   GET /session/status  — per-session status map { id: "idle"|"busy"|"waiting"|... }
//
// RAG state (the user's requirement):
//   green  = working   (opencode is actively generating / running a tool)
//   amber  = idle      (alive but quiet)
//   red    = waiting   (opencode is asking a question / needs input)
//   gray   = off       (no live session for this project / no connected env)
//
// State is derived from the explicit /session/status value when present;
// otherwise inferred from the recency of `time.updated`:
//   updated < 20s  -> working (green)
//   < 60s           -> waiting (red)
//   older           -> idle   (amber)
// Sessions are gathered from two read-only sources and merged:
//   1. The global SQLite store (~/.local/share/opencode/opencode.db) — the
//      source of truth for TUI sessions launched from a terminal, which the
//      serve HTTP API does not list.
//   2. The live `opencode serve` HTTP API — provides explicit per-session
//      status (busy/waiting/idle); if the configured URL is unreachable we
//      fall back to the known serve ports (4096, 4202).
// A session is "live" simply by being present; state comes from the explicit
// status when present, otherwise from update recency. No process-table
// cross-check is needed: OpenCode owns session lifetime.

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { opencodeDbPath, resolveSqlite3 } from "./config.js";

const RUN_MS = 20_000; // updated < 20s ago -> working
const WAIT_MS = 60_000; // < 60s but not working -> likely waiting on input

export const STATE = {
  WAITING: "waiting", // red - opencode is asking a question / needs input
  RUNNING: "running", // green - actively generating / tool-running
  IDLE: "idle",      // amber - alive but quiet
  OFF: "off",        // gray - no live session for this project
};

// RAG color per state (used by the key renderers). Keys are the STATE values.
export const STATE_COLOR = {
  "running": "#2fd06f", // green = working
  "idle": "#f5b13d", // amber = idle
  "waiting": "#ff5a4e", // red = asking a question
  "off": "#5a5e6b", // gray = no connected opencode env
};

// Map a raw OpenCode status string (or null) + last-updated recency to a STATE.
// `status` is the value from /session/status for this session id, or null.
// `updatedMs` is the session's time.updated (epoch ms) or null.
export function stateFor({ status = null, updatedMs = null, nowMs = Date.now() } = {}) {
  if (status === "waiting") return STATE.WAITING;
  if (status === "busy" || status === "shell") return STATE.RUNNING;
  if (status === "idle") return STATE.IDLE;
  // No explicit status: infer from how recently the session was updated.
  if (updatedMs == null) return STATE.IDLE;
  const age = nowMs - updatedMs;
  if (age < RUN_MS) return STATE.RUNNING;
  if (age < WAIT_MS) return STATE.WAITING;
  return STATE.IDLE;
}

// Attribute a session to a project config entry by its working-directory
// prefix. Returns the matching project, or null (auto-detected project).
export function attributeToProject(session, projects) {
  const raw = session.directory || session.cwd;
  if (!raw) return null;
  const norm = String(raw).replace(/\\/g, "/").replace(/\/+$/, "");
  let best = null;
  let bestLen = -1;
  for (const p of projects) {
    const np = String(p.path).replace(/\\/g, "/").replace(/\/+$/, "");
    if (norm === np || norm.startsWith(np + "/")) {
      if (np.length > bestLen) {
        best = p;
        bestLen = np.length;
      }
    }
  }
  return best;
}

// Normalize the /session list into the deck's session records. Pure: takes the
// raw array, returns [{ id, directory, title, updatedAtMs, status, state }].
// `statusMap` is the /session/status object ({ id: status }) or null.
export function mapSessions(rawSessions, statusMap = null, { nowMs = Date.now() } = {}) {
  if (!Array.isArray(rawSessions)) return [];
  const out = [];
  for (const s of rawSessions) {
    if (!s || typeof s !== "object") continue;
    const id = s.id || null;
    if (!id) continue;
    const dir = s.directory || s.cwd || null;
    const updatedMs =
      s.time && typeof s.time.updated === "number" ? s.time.updated : null;
    const status = statusMap && statusMap[id] != null ? String(statusMap[id]) : null;
    out.push({
      id,
      directory: dir,
      title: s.title || s.slug || null,
      updatedAtMs: updatedMs,
      status,
      state: stateFor({ status, updatedMs, nowMs }),
    });
  }
  return out;
}

// Read recent sessions from OpenCode's global SQLite store. This is the
// source of truth for TUI sessions (e.g. a terminal `opencode` launch),
// which the serve HTTP API does not list. Shells out to the sqlite3 CLI
// (the Stream Deck's bundled Node 20 has no node:sqlite).
export function readDbSessions({
  nowMs = Date.now(),
  dbPath = null,
  sqlite3Exe = null,
  windowMs = 90_000,
} = {}) {
  const exe = sqlite3Exe || resolveSqlite3();
  const db = dbPath || opencodeDbPath();
  if (!exe || !existsSync(db)) return [];
  const cutoff = nowMs - windowMs;
  const q = `SELECT id, directory, title, time_updated FROM session WHERE (time_archived IS NULL OR time_archived = 0) AND time_updated >= ${cutoff} ORDER BY time_updated DESC LIMIT 50;`;
  let out;
  try {
    out = execFileSync(exe, ["-noheader", "-separator", "|", db, q], { encoding: "utf8" });
  } catch {
    return [];
  }
  return out
    .trim()
    .split("\n")
    .map((line) => {
      const [id, directory, title, updated] = line.split("|");
      if (!id || !updated) return null;
      const updatedAtMs = Number(updated);
      return {
        id,
        directory: directory || null,
        title: title || null,
        updatedAtMs,
        status: null,
        state: stateFor({ status: null, updatedMs: updatedAtMs, nowMs }),
      };
    })
    .filter(Boolean);
}

// Merge DB sessions (TUI + all) with the live serve server's sessions.
// Server records carry explicit /session/status values and win over DB
// recency inference for the same session id. If the configured server is
// unreachable, fall back to the known serve ports so the deck tracks
// whichever `opencode serve` instance is actually live.
export async function collectSessions({ base, nowMs = Date.now() } = {}) {
  const dbSessions = readDbSessions({ nowMs });
  let serverSessions = [];
  let serverOk = false;
  if (base) {
    const r = await fetchSessions(base, {});
    if (r.ok) {
      serverSessions = r.sessions;
      serverOk = true;
    }
  }
  if (!serverOk) {
    for (const port of SERVE_PORT_FALLBACKS) {
      const alt = `http://127.0.0.1:${port}`;
      const r = await fetchSessions(alt, { timeoutMs: 2_000 });
      if (r.ok) {
        serverSessions = r.sessions;
        serverOk = true;
        break;
      }
    }
  }
  const byId = new Map();
  for (const s of dbSessions) byId.set(s.id, s);
  for (const s of serverSessions) byId.set(s.id, s);
  return { sessions: [...byId.values()], serverOk };
}

// 1:1 per agent: one button per working directory. For each directory show
// the state of its most recently active session — that is the agent's
// real-time state, not a rotation of states.
export function agentStates(sessions, { nowMs = Date.now() } = {}) {
  const byDir = new Map();
  for (const s of sessions || []) {
    const dir = s.directory || "";
    const cur = byDir.get(dir);
    if (!cur || (s.updatedAtMs || 0) > (cur.updatedAtMs || 0)) byDir.set(dir, s);
  }
  const out = {};
  for (const dir of byDir.keys()) {
    const s = byDir.get(dir);
    out[dir] = {
      // Prefer the observation layer's deterministic state when present;
      // fall back to recency inference for legacy records without `state`.
      state: s.state ?? stateFor({ status: s.status || null, updatedMs: s.updatedAtMs, nowMs }),
      sessionId: s.id,
      title: s.title,
      directory: dir,
    };
  }
  return out;
}

// Poll a running `opencode serve` instance. Tries the configured URL and,
// if unreachable, falls back to the known serve ports, so the deck tracks
// whichever instance is actually live (e.g. the launcher's 4096 or a manual
// 4202).
const SERVE_PORT_FALLBACKS = [4096, 4202];

// HTTP adapter. `base` is the OpenCode server root (e.g. http://127.0.0.1:4096).
// Returns { sessions, ok } — ok is false when the server is unreachable (the
// deck then shows everything as gray/OFF). Never throws across the boundary.
export async function fetchSessions(base, { timeoutMs = 4_000 } = {}) {
  const root = String(base || "").replace(/\/+$/, "");
  if (!root) return { sessions: [], ok: false };
  const get = async (path) => {
    const res = await fetch(root + path, { signal: AbortSignal.timeout(timeoutMs) });
    if (!res.ok) throw new Error(`${path} → HTTP ${res.status}`);
    return res.json();
  };
  try {
    const [raw, statusMap] = await Promise.all([
      get("/session"),
      get("/session/status").catch(() => ({})),
    ]);
    const sessions = mapSessions(raw, statusMap || {});
    return { sessions, ok: true };
  } catch (e) {
    return { sessions: [], ok: false, error: e.message };
  }
}

export default {
  STATE,
  STATE_COLOR,
  stateFor,
  attributeToProject,
  mapSessions,
  fetchSessions,
  readDbSessions,
  collectSessions,
  agentStates,
};
