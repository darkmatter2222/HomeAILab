// deck-render-test.mjs — Side Quest A: prove the physical Stream Deck renders
// exactly what we request, and that updates appear immediately.
//
// What it does:
//   1. Finds Stream Deck's loopback port(s) (listening ports of the StreamDeck
//      process).
//   2. Connects and registers as a throwaway plugin (uuid dev.ryans.opendeck.render-test).
//   3. Collects willAppear contexts for every key on the active page.
//   4. Pushes: key1 RED, key2 GREEN, key3 BLUE, key4 animated rainbow,
//      key5 gray OFF, key6 amber IDLE — then cycles colors every 1s to prove
//      live updates.
//   5. Logs every setImage push with a timestamp so latency to the physical
//      deck can be measured against a human watch on the device.
//
// Usage: node tools/deck-render-test.mjs [seconds]
import { WebSocket } from "ws";
import { execSync } from "node:child_process";

// Register with the plugin's manifest UUID so the host sends willAppear for
// the deck keys that use dev.ryans.opendeck actions. The live plugin is
// stopped for the duration of the test (run-render-test.ps1), so there is no
// "already connected" conflict.
const DEFAULT_UUID = "dev.ryans.opendeck";
const SECONDS = Number(process.argv[2] || 20);
// Optional 3rd arg: the SDK server port (captured by the orchestrator
// before stopping the live plugin).
const FORCED_PORT = Number(process.argv[3] || 0);
// Optional 4th arg: the live plugin's per-launch -pluginUUID hash. The
// Stream Deck host identifies a plugin by that per-launch hash (the live
// plugin registers with its own hash); registering with the manifest UUID
// alone did not trigger willAppear.
const REG_UUID = process.argv[4] || DEFAULT_UUID;

function sdPorts() {
  const ps = "$sdPid = (Get-Process StreamDeck -ErrorAction SilentlyContinue).Id; if ($sdPid) { Get-NetTCPConnection -OwningProcess $sdPid -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalPort }";
  try {
    const out = execSync('powershell -NoLogo -NoProfile -Command "' + ps + '"', { encoding: "utf8" });
    return out.split(/\r?\n/).map((l) => parseInt(l, 10)).filter((n) => !isNaN(n) && n > 0);
  } catch {
    return [];
  }
}

const t0 = Date.now();
const ts = () => `t+${Date.now() - t0}`;

// 144x144 SVG key images.
const BG = "#101114";
const TEXT = "#eef1f6";
function keySvg(color, label) {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="144" height="144" viewBox="0 0 144 144">` +
    `<rect width="144" height="144" rx="20" fill="${BG}"/>` +
    `<rect x="4" y="4" width="136" height="136" rx="16" fill="none" stroke="${color}" stroke-width="4"/>` +
    `<circle cx="72" cy="52" r="14" fill="${color}"/>` +
    `<text x="72" y="100" text-anchor="middle" font-family="Segoe UI, Arial" font-size="18" font-weight="700" fill="${TEXT}">${label}</text>` +
    `</svg>`;
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
}

// The SDK server port is the one the live opendeck plugin is connected to.
// The host restarts a killed plugin within ~2s and takes the port back, so
// query the live plugin's socket to find the SDK port and try it first.
function livePluginSdkPort() {
  const ps = "$p = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -like '*opendeck*' } | Select-Object -First 1; if ($p) { Get-NetTCPConnection -OwningProcess $p.ProcessId -State Establish -ErrorAction SilentlyContinue | Where-Object { $_.RemotePort -ne 4096 -and $_.RemotePort -ne 4202 -and $_.RemotePort -ne 4203 } | Select-Object -First 1 -ExpandProperty RemotePort }";
  try {
    const out = execSync('powershell -NoLogo -NoProfile -Command "' + ps + '"', { encoding: "utf8" });
    const port = parseInt(out.split(/\r?\n/).find((l) => /^\d+$/.test(l.trim())) || "", 10);
    return Number.isFinite(port) ? port : null;
  } catch {
    return null;
  }
}

const sdkPort = FORCED_PORT || livePluginSdkPort();
const ports = sdPorts();
console.log(`[${ts()}] Stream Deck listening ports: ${ports.join(", ")}; target SDK port: ${sdkPort || "(none)"}`);
if (sdkPort) {
  const idx = ports.indexOf(sdkPort);
  if (idx >= 0) ports.splice(idx, 1);
  ports.unshift(sdkPort);
}
if (!ports.length) {
  console.log("no Stream Deck port found — is the app running?");
  process.exit(1);
}

// Try each port until one accepts the registration handshake.
const keys = [];
let ws = null;
let confirmedPort = null;
let confirmed = false;
for (const port of ports) {
  const w = new WebSocket(`ws://127.0.0.1:${port}`);
  ws = w;
  await new Promise((resolve) => {
    let done = false;
    const finish = (ok) => {
      if (done) return;
      done = true;
      if (ok) {
        confirmedPort = port;
        confirmed = true;
      }
      setTimeout(resolve, 1000);
    };
    w.on("open", () => {
      w.send(JSON.stringify({ event: "registerPlugin", uuid: REG_UUID }));
      w.send(JSON.stringify({ event: "getGlobalSettings", context: REG_UUID }));
    });
    w.on("message", (buf) => {
      let m;
      try { m = JSON.parse(buf.toString()); } catch { return; }
      if (m.event === "willAppear") {
        keys.push(m.context);
        console.log(`[${ts()}] willAppear context=${m.context}`);
        finish(true);
      } else {
        console.log(`[${ts()}] host event: ${m.event} ${JSON.stringify(m).slice(0, 160)}`);
        if (m.event === "didReceiveGlobalSettings") finish(true);
      }
    });
    w.on("close", (code, reason) => {
      const r = String(reason || "").toLowerCase();
      if (r.includes("already connected")) finish(true);
      else if (code !== 1000) console.log(`[${ts()}] closed (code ${code} ${reason})`);
      finish(confirmed || r.includes("already connected"));
    });
    w.on("error", (e) => console.log(`[${ts()}] ws error: ${e.message}`));
  });
  if (confirmedPort) break;
  try { ws.close(); } catch {}
}
if (!confirmedPort) {
  console.log("could not register on any port");
  process.exit(1);
}
console.log(`[${ts()}] registered on port ${confirmedPort}`);

// willAppear only fires on page navigation / app startup, so it may not
// arrive for a mid-session registration. The active page's profile file
// carries the stable per-key contexts (ActionID) — use those.
await new Promise((r) => setTimeout(r, 1500));
console.log(`[${ts()}] willAppear contexts collected: ${keys.length}`);

// Stable key contexts from the active page profile
// (%APPDATA%\Elgato\StreamDeck\ProfilesV3\...\Profiles\0ee1ded4...\manifest.json).
const KNOWN_CONTEXTS = [
  "70958b8c-360a-40b0-b0bd-9178ad0b96fa", // (0,0) project key "Agent State"
  "ac88487a-8534-4f00-a2a0-6bc63e5a3a94", // (0,1) alert key "Needs You"
  "91fa8858-fd63-4125-bf58-3e44c033d0e1", // (1,0) project key
  "d6222dfc-edba-4c54-8775-3bb970f7138b", // (2,0) project key
  "5e97e195-9b48-46aa-89f9-f19c0f40f73e", // (2,1) claude-fleet spare key
];

const RED = "#ff5a4e";
const GREEN = "#2fd06f";
const BLUE = "#3d9bf5";
const AMBER = "#f5b13d";
const GRAY = "#5a5e6b";
const STATIC_PLAN = [
  { color: RED, label: "RED" },      // (0,0)
  { color: GREEN, label: "GREEN" },  // (0,1)
  { color: BLUE, label: "BLUE" },    // (1,0)
  null,                              // (2,0) = animated rainbow
  { color: GRAY, label: "OFF" },     // (2,1)
  { color: AMBER, label: "IDLE" },   // (1,1) — empty key; only if willAppear gave its context
];

function hueColor(hue) {
  return `hsl(${hue}, 90%, 55%)`;
}

let hue = 0;
let lastPushAt = Date.now();
function pushKey(index, uri, note) {
  // Prefer the stable profile contexts (ActionID); fall back to willAppear
  // contexts if available.
  const context = KNOWN_CONTEXTS[index] || keys[index];
  if (!context) return;
  // v1 format (what the live plugin uses and what Stream Deck 7.5 accepts).
  const msg = { event: "setImage", context, image: { uri } };
  ws.send(JSON.stringify(msg));
  const elapsed = Date.now() - lastPushAt;
  lastPushAt = Date.now();
  console.log(`[${ts()}] setImage key${index + 1} (${note}) context=${context.slice(0, 8)}… sent in ${elapsed}ms since last push`);
}

// Phase 1: static colors.
for (let i = 0; i < Math.min(KNOWN_CONTEXTS.length, STATIC_PLAN.length); i++) {
  const p = STATIC_PLAN[i];
  if (p) pushKey(i, keySvg(p.color, p.label), p.label);
}

// Ask the host for each key's current state (independent read-back of the
// device display). Any host response is logged by the message handler.
for (let i = 0; i < keys.length; i++) {
  const q = { event: "getKeyState", context: keys[i] };
  ws.send(JSON.stringify(q));
}
console.log(`[${ts()}] getKeyState queries sent for ${keys.length} keys`);

// Phase 2: live changes — rainbow key animates, others cycle.
const CYCLE = [RED, GREEN, BLUE, AMBER, GRAY];
let cycleIdx = 0;
const stopAt = t0 + SECONDS * 1000;
const timer = setInterval(() => {
  const rainbowHue = (Date.now() / 15) % 360;
  if (KNOWN_CONTEXTS[3]) pushKey(3, keySvg(hueColor(rainbowHue), "RAINBOW"), "rainbow frame");
  cycleIdx = (cycleIdx + 1) % CYCLE.length;
  const c = CYCLE[cycleIdx];
  for (let i = 0; i < 3; i++) pushKey(i, keySvg(c, ["RED", "GREEN", "BLUE"][i]), `cycle ${c}`);
  if (KNOWN_CONTEXTS[4]) pushKey(4, keySvg(GRAY, "OFF"), "OFF steady");
  if (KNOWN_CONTEXTS[5]) pushKey(5, keySvg(AMBER, "IDLE"), "IDLE steady");
  if (Date.now() >= stopAt) {
    clearInterval(timer);
    try { ws.close(); } catch {}
    console.log(`[${ts()}] done — close. The live opendeck plugin will repaint within its 5s poll; compare the physical deck against this log (timestamps above) to confirm what the device actually showed.`);
    process.exit(0);
  }
}, 1000);
