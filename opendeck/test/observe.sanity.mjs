import m from "../src/observe.js";

const a = { pendingQuestion: 1, nowMs: 1000 };
console.log("pendingQ=1 ->", m.deriveState(a));

const b = { pendingQuestion: 0, lastPartUpdMs: -5000, nowMs: 1000 };
console.log("recent part (5s old) ->", m.deriveState(b));

const c = { pendingQuestion: 0, lastPartUpdMs: -20000, nowMs: 1000 };
console.log("old part (20s old) ->", m.deriveState(c));

// Real query emits 6 columns: id|directory|title|upd|last_part_upd|pending_q
const lines = [
  "s1|C:/x|t|1788556293534|1788556299150|0",
  "s2|C:/y|t2|1788532961020||0",
];
const opts = { nowMs: 1788556293534 + 5000 };
const recs = m.parseRecords(lines, opts);
console.log("parseRecords ->", JSON.stringify(recs));
