import { readDbSessions, agentStates, collectSessions } from "../src/sessions.js";
import { opencodeBase } from "../src/config.js";

const nowMs = Date.now();
const db = readDbSessions({ nowMs });
console.log("DB sessions (recent):", db.length);
const agents = agentStates(db, { nowMs });
for (const [dir, a] of Object.entries(agents)) {
  console.log("  agent", dir, "->", a.state, a.sessionId);
}
const base = opencodeBase("C:/Users/ryans/source/repos/HomeAILab/opendeck");
const { sessions, serverOk } = await collectSessions({ base });
console.log("collectSessions: serverOk=" + serverOk + " merged=" + sessions.length);
const mergedAgents = agentStates(sessions, { nowMs });
for (const [dir, a] of Object.entries(mergedAgents)) {
  console.log("  merged agent", dir, "->", a.state, a.sessionId);
}
