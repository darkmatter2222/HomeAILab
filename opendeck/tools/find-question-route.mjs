import { readFileSync } from "node:fs";
const b = readFileSync("C:/Users/ryans/AppData/Roaming/npm/node_modules/opencode-ai/bin/opencode.exe");
const s = b.toString("latin1");

// Find the C0 base prefix near the question reply route registration
let i = s.indexOf("question.reply");
while (i >= 0) {
  const ctx = s.slice(Math.max(0, i - 500), i + 250);
  console.log("--- context around a question.reply occurrence ---");
  console.log(ctx);
  i = s.indexOf("question.reply", i + 1);
}
