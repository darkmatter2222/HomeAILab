// scan the opencode binary for the session status enum values and event names
import { readFileSync } from "node:fs";
const buf = readFileSync("C:/Users/ryans/AppData/Roaming/npm/node_modules/opencode-ai/bin/opencode.exe");
const s = buf.toString("latin1");
const needles = ['"busy"', '"waiting"', '"idle"', "session.status", "session.idle", "message.part.delta", "session.updated"];
for (const n of needles) {
  let i = -1, c = 0;
  while ((i = s.indexOf(n, i + 1)) >= 0) c++;
  console.log(n, c);
}
