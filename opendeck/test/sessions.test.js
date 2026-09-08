import { test } from "node:test";
import assert from "node:assert/strict";
import {
  STATE,
  STATE_COLOR,
  stateFor,
  attributeToProject,
  mapSessions,
  agentStates,
  readDbSessions,
} from "../src/sessions.js";

const NOW = 1_700_000_000_000;

test("stateFor: explicit status wins", () => {
  assert.equal(stateFor({ status: "waiting", updatedMs: NOW - 5000, nowMs: NOW }), STATE.WAITING);
  assert.equal(stateFor({ status: "busy", updatedMs: null, nowMs: NOW }), STATE.RUNNING);
  assert.equal(stateFor({ status: "idle", updatedMs: NOW - 30_000, nowMs: NOW }), STATE.IDLE);
});

test("stateFor: infers from update recency when no status", () => {
  // updated < 20s -> running (green)
  assert.equal(stateFor({ status: null, updatedMs: NOW - 5_000, nowMs: NOW }), STATE.RUNNING);
  // 20s <= age < 60s -> waiting (red)
  assert.equal(stateFor({ status: null, updatedMs: NOW - 45_000, nowMs: NOW }), STATE.WAITING);
  // older -> idle (amber)
  assert.equal(stateFor({ status: null, updatedMs: NOW - 120_000, nowMs: NOW }), STATE.IDLE);
  // no updatedMs -> idle
  assert.equal(stateFor({ status: null, updatedMs: null, nowMs: NOW }), STATE.IDLE);
});

test("attributeToProject: longest path match wins, prefix only", () => {
  const projects = [
    { alias: "root", path: "C:/Users/ryans" },
    { alias: "homeai", path: "C:/Users/ryans/source/repos/HomeAILab" },
  ];
  const s = { directory: "C:/Users/ryans/source/repos/HomeAILab/somedir" };
  const p = attributeToProject(s, projects);
  assert.equal(p.alias, "homeai");
  // a path in a different tree matches nothing
  const s2 = { directory: "C:/other/place" };
  assert.equal(attributeToProject(s2, projects), null);
});

test("attributeToProject: normalizes backslashes and trailing slash", () => {
  const projects = [{ alias: "homeai", path: "C:\\Users\\ryans\\source\\repos\\HomeAILab" }];
  const s = { directory: "C:\\Users\\ryans\\source\\repos\\HomeAILab\\sub\\" };
  const p = attributeToProject(s, projects);
  assert.equal(p && p.alias, "homeai");
});

test("STATE enum exposes all four buckets", () => {
  assert.equal(STATE.RUNNING, "running");
  assert.equal(STATE.IDLE, "idle");
  assert.equal(STATE.WAITING, "waiting");
  assert.equal(STATE.OFF, "off");
  // RAG colors are present for every state
  for (const st of Object.values(STATE)) {
    assert.ok(STATE_COLOR[st], "color missing for " + st);
  }
});

test("mapSessions: surfaces id, directory, title, updatedAtMs, status, state", () => {
  const raw = [
    { id: "s1", directory: "C:/x", title: "hello", time: { updated: NOW - 5000 } },
    { id: "s2", directory: "C:/y", time: { updated: NOW - 120_000 } },
  ];
  const statusMap = { s1: "busy", s2: "idle" };
  const out = mapSessions(raw, statusMap, { nowMs: NOW });
  assert.equal(out.length, 2);
  assert.equal(out[0].state, STATE.RUNNING);
  assert.equal(out[1].state, STATE.IDLE);
  assert.equal(out[0].id, "s1");
  assert.equal(out[0].status, "busy");
});

test("mapSessions: busy status maps to running", () => {
  const out = mapSessions(
    [{ id: "s1", directory: "C:/x", time: { updated: NOW - 5000 } }],
    { s1: "busy" },
    { nowMs: NOW },
  );
  assert.equal(out[0].state, STATE.RUNNING);
});

test("mapSessions: no status → infer from recency", () => {
  const out = mapSessions(
    [{ id: "s1", directory: "C:/x", time: { updated: NOW - 120_000 } }],
    {},
    { nowMs: NOW },
  );
  assert.equal(out[0].state, STATE.IDLE);
});

test("mapSessions: drops entries without an id; tolerates null status map", () => {
  const out = mapSessions(
    [{ directory: "C:/x" }, { id: "s1", time: { updated: NOW - 120_000 } }, null, 42],
    null,
    { nowMs: NOW },
  );
  assert.equal(out.length, 1);
  assert.equal(out[0].id, "s1");
  assert.equal(out[0].state, STATE.IDLE);
});

test("mapSessions: non-array input → empty", () => {
  assert.deepEqual(mapSessions(null, null, { nowMs: NOW }), []);
  assert.deepEqual(mapSessions({ foo: 1 }, null, { nowMs: NOW }), []);
});

test("agentStates: 1:1 per agent (directory) using the most recent session", () => {
  const sessions = [
    // Two sessions in the same directory: only the most recent one (s2)
    // defines that agent's real-time state.
    { id: "s1", directory: "C:/Users/ryans/source/repos/HomeAILab", updatedAtMs: NOW - 300_000, status: "busy" },
    { id: "s2", directory: "C:/Users/ryans/source/repos/HomeAILab", updatedAtMs: NOW - 5_000, status: null },
    { id: "s3", directory: "C:/Users/ryans", updatedAtMs: NOW - 45_000, status: null },
    { id: "s4", directory: "C:/Users/ryans/source/repos/home_llm", updatedAtMs: NOW - 120_000, status: "idle" },
  ];
  const out = agentStates(sessions, { nowMs: NOW });
  // One entry per directory (agent).
  assert.equal(Object.keys(out).length, 3);
  const homeai = out["C:/Users/ryans/source/repos/HomeAILab"];
  assert.equal(homeai.state, STATE.RUNNING); // s2 updated 5s ago (<20s)
  assert.equal(homeai.sessionId, "s2");
  assert.equal(out["C:/Users/ryans"].state, STATE.WAITING); // 45s -> waiting (red)
  assert.equal(out["C:/Users/ryans/source/repos/home_llm"].state, STATE.IDLE); // explicit idle
});

test("agentStates: empty input yields no agents", () => {
  assert.deepEqual(agentStates([], { nowMs: NOW }), {});
  assert.deepEqual(agentStates(null, { nowMs: NOW }), {});
});

test("readDbSessions: missing sqlite3 or db yields empty (no throw)", () => {
  // No sqlite3 CLI or no DB file -> graceful empty result.
  assert.deepEqual(
    readDbSessions({ nowMs: NOW, sqlite3Exe: null, dbPath: "/nonexistent/opencode.db" }),
    [],
  );
});
