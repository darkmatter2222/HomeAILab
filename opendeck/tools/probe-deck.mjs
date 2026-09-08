// probe-deck.mjs — confirm the plugin is actually running on the device.
// Stream Deck assigns the plugin a fresh loopback port on every launch; we
// enumerate Stream Deck's listening ports and try each until one accepts the
// plugin registration handshake.
//
// Stream Deck 7.5 launches the plugin with a per-launch hashed
// -pluginUUID and -registerEvent "registerPlugin", so the probe mirrors that
// exactly: it reads the live plugin process command line for the current hash
// (falling back to the manifest UUID) and registers with "registerPlugin".
import { WebSocket } from "ws";
import { execSync } from "node:child_process";

const MANIFEST_UUID = "dev.ryans.opendeck";

function sdPorts() {
  const ps = '$sdPid = (Get-Process StreamDeck -ErrorAction SilentlyContinue).Id; if ($sdPid) { Get-NetTCPConnection -OwningProcess $sdPid -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalPort }';
  try {
    const out = execSync('powershell -NoLogo -NoProfile -Command "' + ps + '"', { encoding: "utf8" });
    return out.split(/\r?\n/).map((l) => parseInt(l, 10)).filter((n) => !isNaN(n) && n > 0);
  } catch {
    return [];
  }
}

// The live plugin process (spawned by Stream Deck) carries the per-launch
// -pluginUUID hash; reuse it so the probe registers exactly like the plugin.
function livePluginUUID() {
  // No -Filter (WQL quoting is fragile through a double-quoted -Command):
  // filter in JS instead. No inner double quotes anywhere.
  const ps = `Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -like '*opendeck*' } | Select-Object -First 1 -ExpandProperty CommandLine`;
  try {
    const out = execSync('powershell -NoLogo -NoProfile -Command "' + ps + '"', { encoding: "utf8" });
    const m = out.match(/-pluginUUID\s+(\S+)/);
    if (m) return m[1];
  } catch {}
  return MANIFEST_UUID;
}

const ports = sdPorts();
const uuid = livePluginUUID();
console.log("Stream Deck listening ports:", ports.join(", ") || "(none found)");
console.log("registering with uuid:", uuid);

let confirmed = false;
for (const port of ports) {
  const ws = new WebSocket("ws://127.0.0.1:" + port);
  try {
    ws.on("open", () => {
      // Stream Deck 7.5 passes "registerPlugin" as the register event name;
      // older builds used "SDDidRegisterPlugin".
      ws.send(JSON.stringify({ event: "registerPlugin", uuid: uuid }));
      ws.send(JSON.stringify({ event: "getGlobalSettings", context: uuid }));
    });
    ws.on("message", (buf) => {
      let m;
      try { m = JSON.parse(buf.toString()); } catch { return; }
      console.log("port " + port + " event: " + m.event + " " + JSON.stringify(m).slice(0, 150));
      if (m.event === "didReceiveGlobalSettings" || m.event === "registerPlugin" || m.event === "didRegisterPlugin") {
        confirmed = true;
        try { ws.close(); } catch {}
      }
    });
    ws.on("error", (e) => console.log("port " + port + " error: " + e.message));
    ws.on("close", (code, reason) => {
      const r = String(reason || "");
      // The plugin's own session is registered on this port: a second
      // registration with the same uuid gets closed with "Already connected"
      // — that IS confirmation the plugin is live on the device.
      if (r.toLowerCase().includes("already connected")) {
        confirmed = true;
        console.log("port " + port + " closed: code " + code + " " + r + " (plugin session already registered)");
        return;
      }
      if (!confirmed) console.log("port " + port + " closed without confirmation (code " + code + " " + r + ")");
    });
    await new Promise((r) => setTimeout(r, 4000));
    try { ws.close(); } catch {}
  } catch (e) {
    console.log("port " + port + " failed: " + e.message);
  }
}

console.log(confirmed ? "CONFIRMED: plugin is live on the device" : "NOT confirmed on this pass");
process.exit(confirmed ? 0 : 1);
