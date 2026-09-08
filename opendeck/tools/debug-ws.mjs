// Debug: see what the Stream Deck app sends to a fresh plugin registration.
import { WebSocket } from "ws";
import { execSync } from "node:child_process";

const ps = "(Get-Process StreamDeck -ErrorAction SilentlyContinue).Id | ForEach-Object { Get-NetTCPConnection -OwningProcess $_ -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalPort }";
const out = execSync('powershell -NoProfile -Command "' + ps + '"', { encoding: "utf8" });
const ports = out.split(/\r?\n/).map((l) => parseInt(l.trim(), 10)).filter((n) => !isNaN(n) && n > 0);
console.log("SD listening ports:", ports);
// Use the plugin's port (the port the live opendeck plugin connects to).
const ps2 = "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -like '*opendeck*' } | Select-Object -First 1 -ExpandProperty CommandLine";
const out2 = execSync('powershell -NoProfile -Command "' + ps2 + '"', { encoding: "utf8" });
const m = out2.match(/-port\s+(\d+)/);
const port = m ? Number(m[1]) : ports[0];
const uuid = "acceptance-debug-" + Date.now();
const ws = new WebSocket("ws://127.0.0.1:" + port);
ws.on("open", () => {
  console.log("open on port", port);
  ws.send(JSON.stringify({ event: "registerPlugin", uuid }));
  ws.send(JSON.stringify({ event: "getGlobalSettings", context: uuid }));
});
ws.on("message", (buf) => {
  const t = buf.toString();
  console.log("MSG:", t.slice(0, 300));
});
ws.on("close", (code, reason) => console.log("CLOSED:", code, String(reason)));
setTimeout(() => {
  try { ws.close(); } catch {}
  process.exit(0);
}, 8000);
