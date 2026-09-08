// plugin.js — the I/O shell for the OpenCode Stream Deck plugin.
//
// Stream Deck runs this as a Node process and talks to it over a WebSocket on
// 127.0.0.1:<port>. We connect back, register, then render. Everything heavy
// (session discovery, state, key art) lives in the sibling modules; this file
// only does I/O: the socket, the keyDown router, the pollers, and page state.
//
// Args (passed by the Stream Deck host):
//   -port N          the loopback port to connect to
//   -pluginUUID X    a per-launch hashed UUID (register with it as-is)
//   -registerEvent E the event name to fire on registration (e.g. "registerPlugin")
//   -info <json>     host info; `plugin.uuid` is the stable manifest UUID
//   --selftest        smoke-run the render path and exit 0/1

import { WebSocket } from "ws";
import { spawn } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { writeFileSync, mkdirSync } from "node:fs";

import { loadProjects, normalizeProjects, writeAutoProjects } from "./config.js";
import { agentStates, attributeToProject, STATE } from "./sessions.js";
import { startObservation } from "./observe.js";
import { focusSession, launchProject } from "./focus.js";
import * as render from "./render.js";
import * as keyart from "./keyart.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
// The config lives next to the installed plugin bundle, or in the repo root
// (opendeck/) in dev. Prefer the repo root when present.
const REPO_ROOT = resolve(__dirname, "..");

const MENU_IDLE_MS = 5_000; // auto-return to main when on a menu page
const BREATH_MS = 700; // 3-frame breathing for active keys
const BREATH_FRAMES = 3;

const log = (m) => {
  if (process.env.DFDECK_DEBUG) console.error("[opendeck]", m);
};

// Crash guards: an uncaught exception would kill the Node process and the
// Stream Deck runtime would mark the plugin "unstable" and disable it.
process.on("uncaughtException", (e) => {
  console.error("[opendeck] uncaughtException:", e && e.message, e && e.stack);
});
process.on("unhandledRejection", (r) => {
  console.error("[opendeck] unhandledRejection:", String(r));
});

// Graceful shutdown: when Stream Deck exits cleanly it signals the plugin
// process. Close the WebSocket with code 1000 so the SDK server can write
// a session-end report, then exit.
function gracefulShutdown() {
  try {
    if (state.ws && state.ws.readyState === 1) state.ws.close(1000, "shutdown");
  } catch (e) {
    log("shutdown close failed:", e.message);
  }
  setTimeout(() => process.exit(0), 300);
}
process.on("SIGINT", gracefulShutdown);
process.on("SIGTERM", gracefulShutdown);

// ---- state --------------------------------------------------------------
const state = {
  ws: null,
  pluginUUID: null,
  page: "main",
  menuPage: 0,
  // live session data: alias -> { state, sessionId, directory, title, newAlert }
  live: {},
  projects: [],
  lastKeyAt: {},
  lastFocusAt: {},
  menuIdleTimer: null,
  breathPhase: 0,
  serverOk: true,
};

function argOf(flag) {
  const i = process.argv.indexOf(flag);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : null;
}

// ---- render + push ------------------------------------------------------

// Send a key image to a context. `context` is the Stream Deck context string;
// plugin.js maps its own stable contexts to physical keys.
function setKeyImage(context, image) {
  if (state.ws && image) {
    state.ws.send(
      JSON.stringify({ event: "setImage", context, image: { uri: image } })
    );
  }
}

// Render every key we know about, by its real Stream Deck context.
function renderAll() {
  for (const [context, info] of contextMap) {
    const image = imageForContext(context, info);
    if (image) setKeyImage(context, image);
  }
}

// What should a given key show, given its (action, slot) and current state.
function imageForContext(context, info) {
  const phase = state.breathPhase;
  if (state.page === "menu") {
    // menu page: keys 0..4 = projects, key 5 = nav
    if (info.action === "project" && info.slot < render.MENU_PER_PAGE) {
      const p = state.projects[state.menuPage * render.MENU_PER_PAGE + info.slot];
      if (p) {
        const l = state.live[p.alias] || { state: STATE.OFF };
        return keyart.projectKey({ alias: p.alias, state: l.state, color: p.color, phase });
      }
      return keyart.placeholderKey({ label: "empty", phase });
    }
    if (info.action === "nav") {
      const pages = Math.max(1, Math.ceil(state.projects.length / render.MENU_PER_PAGE));
      const label =
        state.menuPage > 0 ? "Back" : state.menuPage + 1 < pages ? "Next" : "Back";
      return keyart.nextKey({ label });
    }
  }
  // main page (or non-project action): each key = project at its slot
  if (info.action === "project" || info.action === "launch" || info.action === "spare") {
    const p = state.projects[info.slot];
    if (p) {
      const l = state.live[p.alias] || { state: STATE.OFF };
      return keyart.projectKey({ alias: p.alias, state: l.state, color: p.color, phase });
    }
    return keyart.placeholderKey({ label: "add project", phase });
  }
  if (info.action === "alert") {
    return keyart.alertKey({ count: render.countAlerts(state.live) });
  }
  return null;
}

// ---- event-driven session observation -----------------------------------
// The observation layer (src/observe.js) watches the global OpenCode DB and
// fires onState(records) on every DB change (debounced) plus a 1s eval tick
// (catches RUNNING->IDLE and ACTIVE->OFF, which don't themselves write to the
// DB). We fold the per-session records to per-working-directory agents and
// push the RAG state to the deck. Replaces the old 5s poller.
function applyObservation(records) {
  // 1:1 per agent: one button per working directory, showing that agent's
  // real-time state (the most recently active session for that directory).
  const agents = agentStates(records || [], { nowMs: Date.now() });

  const next = {};
  // Track which aliases were already "waiting" so we can flag a *new* alert.
  const prevWaiting = new Set(
    Object.keys(state.live).filter((a) => state.live[a].state === STATE.WAITING),
  );
  // Auto projects minted this observation (directory matches no configured project).
  const minted = [];
  for (const agent of Object.values(agents)) {
    // attribute to a configured project; else mint an auto project
    let project = attributeToProject({ directory: agent.directory }, state.projects);
    if (!project) {
      const alias = normalizeProjects(
        [{ path: agent.directory || "", alias: (agent.directory ? agent.directory.replace(/[\\/]+$/, "").split(/[\\/]/).pop() : "session") }],
        { auto: true },
      )[0].alias;
      project = { alias, path: agent.directory, bat: null, auto: true };
      minted.push(project);
    }
    next[project.alias] = {
      state: agent.state,
      sessionId: agent.sessionId,
      directory: agent.directory,
      title: agent.title,
      newAlert: agent.state === STATE.WAITING && !prevWaiting.has(project.alias),
    };
  }
  // Remember which projects are auto-detected so we can persist them.
  const autos = state.projects.filter((p) => p.auto).concat(minted);
  state.live = next;
  if (autos.length) writeAutoProjects(REPO_ROOT, autos);
  renderAll();
}

// ---- key handling -------------------------------------------------------
// Stream Deck identifies each key by an opaque context hash. When a key of ours
// appears, "willAppear" carries its per-key settings — including the action id
// (our manifest UUID, e.g. "...project") and the slot we ask for via settings.
// We build a map: context -> { action, slot } and use it for both keyDown
// routing and setImage.
const contextMap = new Map(); // context -> { action, slot }
const contextSettings = new Map(); // context -> raw settings object from the PI

function registerContext(context, settings) {
  const rawAction = (settings && settings.action) || "";
  const action = rawAction.split(".").pop() || "project";
  const known = contextMap.get(context);
  const slot =
    settings && settings.slot != null
      ? Number(settings.slot)
      : known
        ? known.slot
        : contextMap.size; // appearance order = slot
  contextMap.set(context, { action, slot });
  if (settings && typeof settings === "object") contextSettings.set(context, settings);
  dumpContexts();
}

// The acceptance harness (streamdeck/acceptance.py) reads this dump to map
// key index -> context for simulating button presses.
const CONTEXT_DUMP = join(
  process.env.USERPROFILE || process.env.HOME || "C:\\Users\\ryans",
  ".local", "share", "opencode", "opendeck-contexts.json",
);

function dumpContexts() {
  try {
    const out = {};
    for (const [ctx, info] of contextMap) out[ctx] = info;
    mkdirSync(dirname(CONTEXT_DUMP), { recursive: true });
    writeFileSync(CONTEXT_DUMP, JSON.stringify(out, null, 2));
  } catch (e) {
    log("context dump failed:", e.message);
  }
}

function onKeyDown(context) {
  const info = contextMap.get(context);
  if (!info) return;
  const { action, slot } = info;
  if (action === "launch") {
    // On the main page: if the launch key's slot has no live session, launch
    // the project at that slot (or the first project if the slot is empty).
    // On a menu page: open the full project menu.
    if (state.page === "main") {
      const p = state.projects[slot] || state.projects[0];
      if (p) {
        const l = state.live[p.alias] || {};
        if (l.sessionId) {
          focusSession({ marker: `opencode:${p.alias}` });
        } else {
          launchProject(p);
        }
        armMenuIdle();
        return;
      }
    }
    goMenu(0);
    return;
  }
  if (action === "nav") {
    if (state.page !== "menu") return;
    const pages = Math.max(1, Math.ceil(state.projects.length / render.MENU_PER_PAGE));
    if (state.menuPage > 0) state.menuPage--;
    else if (state.menuPage + 1 < pages) state.menuPage++;
    renderAll();
    armMenuIdle();
    return;
  }
  if (action === "project") {
    // main page: this key shows project `slot`. menu page: key `slot` on page `menuPage`.
    let project =
      state.page === "menu"
        ? state.projects[state.menuPage * render.MENU_PER_PAGE + slot]
        : state.projects[slot];
    // A per-key settings override (path/bat/label) wins over the positional
    // project at this slot.
    const settings = contextSettings.get(context);
    if (settings && (settings.path || settings.bat || settings.label)) {
      const override = {
        alias: settings.label || (project ? project.alias : `key-${slot}`),
        path: settings.path || (project ? project.path : null),
        bat: settings.bat || (project ? project.bat : null),
      };
      if (override.path || override.bat || project) project = override;
    }
    if (project) handleProjectPress(project, context);
    return;
  }
}

async function handleProjectPress(project, context) {
  const now = Date.now();
  const last = state.lastKeyAt[context] || 0;
  const DOUBLE = 350;
  const isDouble = now - last < DOUBLE;
  state.lastKeyAt[context] = now;

  const alias = project.alias;
  const l = state.live[alias] || {};

  if (isDouble) {
    // double-tap: quick-launch a second session (parallel agents). This is a
    // genuine OpenCode state change (a new session is born -> OFF -> IDLE).
    launchProject(project);
    return;
  }
  // single press: navigate only — focus the associated session's terminal.
  // OFF (no live session): the press does nothing. No launch, no state
  // change, no fake session.
  if (l.sessionId) {
    await focusSession({ marker: `opencode:${alias}` });
  }
  if (state.page === "menu") armMenuIdle();
}

// ---- page management ----------------------------------------------------
function goMenu(page) {
  state.page = "menu";
  state.menuPage = page || 0;
  renderAll();
  armMenuIdle();
}
function goMain() {
  state.page = "main";
  state.menuPage = 0;
  renderAll();
}
function armMenuIdle() {
  if (state.menuIdleTimer) clearTimeout(state.menuIdleTimer);
  if (state.page === "menu") {
    state.menuIdleTimer = setTimeout(() => {
      if (state.page === "menu") goMain();
    }, MENU_IDLE_MS);
  }
}

// ---- bootstrap ----------------------------------------------------------
function start() {
  // Stream Deck 7.x launches the plugin with single-dash flags:
  //   -port N  -pluginUUID <per-launch hash>  -registerEvent <event name>  -info <json>
  // (confirmed against the live 7.5 process command line and the reference
  // agent-vitals plugin, which parses the same single-dash flags).
  const port = Number(argOf("-port") || argOf("--port") || 0);
  let pluginUUID = argOf("-pluginUUID") || argOf("--pluginUUID");
  const registerEvent = argOf("-registerEvent") || argOf("--registerEvent") || "SDDidRegisterPlugin";
  // Manual runs (selftest) have no -pluginUUID: fall back to the stable
  // manifest UUID from -info.
  if (!pluginUUID) {
    const infoRaw = argOf("-info");
    if (infoRaw) {
      try {
        const info = JSON.parse(infoRaw);
        if (info.plugin && info.plugin.uuid) pluginUUID = info.plugin.uuid;
      } catch {}
    }
  }
  state.pluginUUID = pluginUUID;

  // Load projects (hand-written + auto).
  const cfg = loadProjects({ repoRoot: REPO_ROOT });
  state.projects = cfg.projects;

  const ws = new WebSocket(`ws://127.0.0.1:${port}`);
  state.ws = ws;
  wire(ws, port, registerEvent, pluginUUID);
  attachResilience(ws, port, registerEvent, pluginUUID);

  // Event-driven session observation (replaces the 5s poller). Lives in
  // start() (not wire()) so it isn't re-created on every socket reconnect.
  // The watcher fires on every global-DB change; the 1s eval tick catches the
  // RUNNING->IDLE and ACTIVE->OFF transitions that don't themselves write to the DB.
  startObservation({ onState: applyObservation, evalMs: 1000 });
  setInterval(() => {
    state.breathPhase = (state.breathPhase + 1) % BREATH_FRAMES;
    const anyActive = Object.keys(state.live).some(
      (a) => state.live[a].state === STATE.RUNNING || state.live[a].state === STATE.WAITING,
    );
    if (anyActive) renderAll();
  }, BREATH_MS);
}

// A brand-new socket must carry its own error/close handlers, or an
// ECONNREFUSED (Stream Deck port not up yet) is an unhandled 'error' that
// kills the process. The reconnect path creates a fresh socket, so it reuses
// this too.
const RECONNECT_BASE_MS = 1000;
const ALREADY_CONNECTED_WAIT_MS = 5_000;
let reconnectTimer = null;

function attachResilience(ws, port, registerEvent, pluginUUID) {
  ws.on("error", (e) => log("ws error (will retry):", e.message));
  ws.on("close", (code, reason) => {
    if (state.ws !== ws) return; // a newer socket already took over
    const r = String(reason || "");
    const contested = r.toLowerCase().includes("already connected");
    const delay = contested ? ALREADY_CONNECTED_WAIT_MS : RECONNECT_BASE_MS;
    log(`ws closed (code ${code} ${r} - reconnecting in ${delay}ms`);
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
      try {
        const next = new WebSocket(`ws://127.0.0.1:${port}`);
        state.ws = next;
        wire(next, port, registerEvent, pluginUUID);
        attachResilience(next, port, registerEvent, pluginUUID);
      } catch (e) {
        log("reconnect failed:", e.message);
      }
    }, delay);
  });
}

function wire(ws, port, registerEvent, pluginUUID) {
  ws.on("open", () => {
    log("registered with Stream Deck");
    // Stream Deck 7.5 passes its OWN register event name on the command line
    // (currently "registerPlugin"; older builds used "SDDidRegisterPlugin") —
    // we echo exactly that.
    ws.send(JSON.stringify({ event: registerEvent, uuid: pluginUUID }));
    ws.send(JSON.stringify({ event: "getGlobalSettings", context: pluginUUID }));
    // A connection that stays open for a full poll interval is stable. If the
    // socket is stuck in CLOSING, force a clean 1000 close, then force a
    // reconnect if the close event still hasn't fired 3s later.
    setTimeout(() => {
      if (ws.readyState === ws.OPEN) return;
      try { ws.close(1000, "reap-session"); } catch {}
      setTimeout(() => {
        if (ws.readyState !== ws.OPEN && state.ws === ws) {
          const next = new WebSocket(`ws://127.0.0.1:${port}`);
          state.ws = next;
          wire(next, port, registerEvent, pluginUUID);
          attachResilience(next, port, registerEvent, pluginUUID);
        }
      }, 3000);
    }, 6000);
    // Initial state comes from the observation layer's first read (done in
    // startObservation). No need to poll here.
  });

  ws.on("message", (buf) => {
    let m;
    try {
      m = JSON.parse(buf.toString());
    } catch {
      return;
    }
    handleMessage(m);
  });
}

function handleMessage(m) {
  switch (m.event) {
    case "willAppear": {
      registerContext(m.context, m.settings);
      renderAll();
      break;
    }
    case "keyDown":
      onKeyDown(m.context);
      break;
    case "didReceiveSettings":
      registerContext(m.context, m.settings);
      renderAll();
      break;
    case "didReceiveGlobalSettings": {
      if (m.settings && Array.isArray(m.settings.projects)) {
        state.projects = normalizeProjects(m.settings.projects, { repoRoot: REPO_ROOT });
        renderAll();
      }
      break;
    }
    case "didChangeSettings":
      renderAll();
      break;
    default:
      break;
  }
}

// ---- self-test ----------------------------------------------------------
function selftest() {
  const ok = (() => {
    try {
      const r = render.render({
        projects: [
          { alias: "homeai", path: "/tmp/homeai" },
          { alias: "router", path: "/tmp/router" },
        ],
        live: { homeai: { state: STATE.RUNNING } },
        phase: 1,
      });
      const imgs = r.keys.map((k) => k.image);
      if (!imgs.length) return false;
      if (!imgs.every((i) => typeof i === "string" && i.startsWith("data:image/svg+xml"))) return false;
      const menu = render.render({
        page: "menu",
        menuPage: 0,
        projects: [
          { alias: "a", path: "/a" }, { alias: "b", path: "/b" },
          { alias: "c", path: "/c" }, { alias: "d", path: "/d" },
          { alias: "e", path: "/e" }, { alias: "f", path: "/f" },
        ],
        live: {},
        phase: 0,
      });
      if (menu.keys.length < 5) return false;
      return true;
    } catch (e) {
      console.error("selftest error", e);
      return false;
    }
  })();
  console.log(ok ? "selftest OK" : "selftest FAILED");
  process.exit(ok ? 0 : 1);
}

if (process.argv.includes("--selftest")) {
  selftest();
} else {
  start();
}

export { state, start, renderAll, goMenu, goMain, onKeyDown, applyObservation };
export default start;
