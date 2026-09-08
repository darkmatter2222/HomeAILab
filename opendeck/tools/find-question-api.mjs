import { readFileSync } from "node:fs";
const b = readFileSync("C:/Users/ryans/AppData/Roaming/npm/node_modules/opencode-ai/bin/opencode.exe");
const s = b.toString("latin1");

// client question methods
const re = /[a-zA-Z_$][\w$.]*\.question\.\w+/g;
const methods = new Set();
for (const m of s.match(re) || []) methods.add(m);
console.log("question client methods:\n" + [...methods].join("\n"));

// route strings that reference question
const re2 = /["'`](\/[a-z0-9_{}/.-]*question[a-z0-9_{}/.-]*)["'`]/g;
const routes = new Set();
for (const m of s.match(re2) || []) routes.add(m[0].slice(1, -1));
console.log("question routes:\n" + [...routes].join("\n"));

// Find reply/answer method names on the client
const re3 = /[a-zA-Z_$][\w$.]*\.(reply|answer|respond)\w*/g;
const rep = new Set();
for (const m of s.match(re3) || []) rep.add(m);
console.log("reply/answer methods:\n" + [...rep].join("\n"));
