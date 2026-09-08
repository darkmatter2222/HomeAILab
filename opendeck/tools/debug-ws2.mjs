// Debug 2 (fixed): focus the Stream Deck app window via .BringToFront(),
// then register fresh and watch for willAppear events.
import { WebSocket } from "ws";
import { execSync } from "node:child_process";

function sh(cmd) {
  return execSync('powershell -NoProfile -Command "' + cmd + '"', { encoding: "utf8" });
}

const psFocus =
  "$sd = Get-Process StreamDeck -ErrorAction SilentlyContinue | Select-Object -First 1; " +
  "if ($sd) { $sd.BringToFront() }";
try { sh(psFocus); } catch (e) { console.log("focus failed:", e.message); }

setTimeout(() => {
  const ps = "(Get-Process StreamDeck -ErrorAction SilentlyContinue).Id | ForEach-Object { Get-NetTCPConnection -OwningProcess $_ -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalPort }";
  const ports = sh(ps).split(/\r?\n/).map((l) => parseInt(l.trim(), 10)).filter((n) => !isNaN(n) && n > 0);
  const ps2 = "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -like '*opendeck*' } | Select-Object -First 1 -ExpandProperty CommandLine";
  const out2 = sh(ps2);
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
  }, 10000);
}, 1500);
