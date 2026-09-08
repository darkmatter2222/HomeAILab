// probe-event.mjs — side-quest C/D diagnostic: stream the OpenCode /event SSE
// endpoint and log every event with a timestamp. Usage:
//   node tools/probe-event.mjs [base] [seconds]
// Proves what event signals OpenCode actually exposes (deterministic state
// sources), and measures time-to-first-event and per-event latency.
const base = (process.argv[2] || "http://127.0.0.1:4096").replace(/\/+$/, "");
const seconds = Number(process.argv[3] || 10);
const t0 = Date.now();

const res = await fetch(base + "/event", { signal: AbortSignal.timeout(seconds * 1000 + 2000) });
console.log("open: HTTP", res.status, res.headers.get("content-type"));
const reader = res.body.getReader();
const dec = new TextDecoder();
let buf = "";
let events = 0;
const loop = (async () => {
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line.startsWith("data:")) {
        events++;
        const payload = line.slice(5);
        let evType = "?";
        try { evType = JSON.parse(payload).type; } catch {}
        console.log(
          `[t+${Date.now() - t0}ms] event #${events} type=${evType} raw=${payload.slice(0, 160)}`
        );
      }
    }
  }
})().catch((e) => console.log("stream ended:", e.message));
await new Promise((r) => setTimeout(r, seconds * 1000));
await loop;
console.log(`total events in ${seconds}s: ${events} (mean interval ${events ? Math.round(seconds * 1000 / events) : -1}ms)`);
process.exit(0);
