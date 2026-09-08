// config.js — load + merge projects.json (hand-written) and projects.auto.json
// (auto-detected sessions), validate, and expose the opencode server URL.
//
// Shape of projects.json:
// {
//   "opencode": { "url": "http://127.0.0.1:4096" },
//   "projects": [
//     { "alias": "homeai", "path": "C:\\...\\HomeAILab", "bat": "C:\\Users\\ryans\\bin\\opencode-3090-serve.bat" }
//   ]
// }
//
// The plugin bundle lives next to its own projects.json (installed) or the
// repo root (dev). We prefer the repo root when present so a dev checkout
// wins.

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import os from "node:os";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// The installed plugin resolves its config dir to the plugin root (resolve(bin, "..")).
// In dev, the repo root (resolve(src, "..") = opendeck/) holds the live config.
const PLUGIN_ROOT = resolve(__dirname, "..");

const OPENSERV_DEFAULT = "http://127.0.0.1:4096";

// Slugify a path into a short alias (last path segment, lowercased, capped).
export function slugify(pathLike) {
  const raw = String(pathLike || "").replace(/\\/g, "/").replace(/\/+$/, "");
  const seg = raw.split("/").filter(Boolean).pop() || "session";
  return seg.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-+$/g, "").slice(0, 12);
}

// Normalize a list of project entries into a deduped, sorted project array.
// Each entry: { alias?, path, bat?, color? }. Missing alias -> slugify(path).
// `auto` entries sort alphabetically after manual entries.
export function normalizeProjects(raw, { repoRoot = PLUGIN_ROOT, auto = false } = {}) {
  const list = Array.isArray(raw) ? raw : (raw && raw.projects) || [];
  const seen = new Set();
  const out = [];
  for (const e of list) {
    if (!e || typeof e !== "object") continue;
    const path = String(e.path || "").trim();
    if (!path) continue;
    let alias = String(e.alias || "").trim() || slugify(path);
    const key = alias.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      alias,
      path,
      bat: e.bat ? resolve(repoRoot, String(e.bat)) : null,
      color: e.color != null ? String(e.color) : null,
      auto: auto || !!e.auto,
    });
  }
  const manual = out.filter((p) => !p.auto).sort((a, b) => a.alias.localeCompare(b.alias));
  const autos = out.filter((p) => p.auto).sort((a, b) => a.alias.localeCompare(b.alias));
  return manual.concat(autos);
}

// Load the hand-written + auto projects files from a root dir.
// Returns { projects, opencodeUrl }.
export function loadProjects({ repoRoot = PLUGIN_ROOT } = {}) {
  const manualPath = resolve(repoRoot, "projects.json");
  const autoPath = resolve(repoRoot, "projects.auto.json");
  let manual = [];
  let opencodeUrl = OPENSERV_DEFAULT;
  if (existsSync(manualPath)) {
    try {
      const cfg = JSON.parse(readFileSync(manualPath, "utf8"));
      opencodeUrl = (cfg.opencode && cfg.opencode.url) || OPENSERV_DEFAULT;
      manual = normalizeProjects(cfg, { repoRoot });
    } catch {}
  }
  let autos = [];
  if (existsSync(autoPath)) {
    try {
      const cfg = JSON.parse(readFileSync(autoPath, "utf8"));
      autos = normalizeProjects(cfg, { repoRoot, auto: true });
    } catch {}
  }
  const byAlias = new Map();
  for (const p of manual.concat(autos)) byAlias.set(p.alias.toLowerCase(), p);
  const projects = [...byAlias.values()];
  return { projects, opencodeUrl };
}

// Persist auto-detected projects (never clobbers the hand-written file).
export function writeAutoProjects(repoRoot, autos) {
  const autoPath = resolve(repoRoot, "projects.auto.json");
  try {
    writeFileSync(autoPath, JSON.stringify({ projects: autos }, null, 2));
  } catch {}
}

// Resolve the opencode server base URL.
export function opencodeBase(repoRoot = PLUGIN_ROOT) {
  const cfg = loadProjects({ repoRoot });
  return cfg.opencodeUrl;
}

// OpenCode keeps all sessions (TUI + serve) in one global SQLite store.
// The standard location on this machine.
export function opencodeDbPath() {
  return join(os.homedir(), ".local", "share", "opencode", "opencode.db");
}

// Find the sqlite3 CLI (needed to read the DB from the Stream Deck's
// bundled Node 20, which has no node:sqlite).
export function resolveSqlite3() {
  const candidates = [
    "O:/platform-tools/sqlite3.exe",
    join(os.homedir(), "AppData", "Local", "Android", "Sdk", "platform-tools", "sqlite3.exe"),
  ];
  // PATH lookup first (where.exe), then known locations.
  try {
    const out = execFileSync("where.exe", ["sqlite3"], { encoding: "utf8" });
    const hit = out.split(/\r?\n/).map((l) => l.trim()).find(Boolean);
    if (hit) return hit;
  } catch {}
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  return null;
}

export default {
  slugify,
  normalizeProjects,
  loadProjects,
  writeAutoProjects,
  opencodeBase,
  opencodeDbPath,
  resolveSqlite3,
};
