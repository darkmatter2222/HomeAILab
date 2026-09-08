import { test } from "node:test";
import assert from "node:assert/strict";
import { deriveState, parseRecords, RUN_WINDOW_MS } from "../src/observe.js";
import { STATE } from "../src/sessions.js";

const NOW = 1_788_556_293_534;

test("deriveState: pending question => NEEDS_USER (waiting/red)", () => {
  const a = { pendingQuestion: 1, lastPartUpdMs: NOW - 5000, nowMs: NOW };
  assert.equal(deriveState(a), STATE.WAITING);
  // pending question wins even if a part update is recent
  const b = { pendingQuestion: 2, lastPartUpdMs: NOW - 1000, nowMs: NOW };
  assert.equal(deriveState(b), STATE.WAITING);
});

test("deriveState: recent part update within window => RUNNING", () => {
  const a = { pendingQuestion: 0, lastPartUpdMs: NOW - 5000, nowMs: NOW };
  assert.equal(deriveState(a), STATE.RUNNING);
  const edge = { pendingQuestion: 0, lastPartUpdMs: NOW - (RUN_WINDOW_MS - 1), nowMs: NOW };
  assert.equal(deriveState(edge), STATE.RUNNING);
});

test("deriveState: part update older than window => IDLE", () => {
  const a = { pendingQuestion: 0, lastPartUpdMs: NOW - (RUN_WINDOW_MS + 1), nowMs: NOW };
  assert.equal(deriveState(a), STATE.IDLE);
  const b = { pendingQuestion: 0, lastPartUpdMs: null, nowMs: NOW };
  assert.equal(deriveState(b), STATE.IDLE);
});

test("parseRecords: parses 6-column CLI rows into state records", () => {
  const lines = [
    "s1|C:/x|t|1788556293534|1788556299150|0",
    "s2|C:/y|t2|1788532961020||0",
    "s3|C:/z|t3|1788556293534|1788556293534|1",
  ];
  const opts = { nowMs: NOW };
  const recs = parseRecords(lines, opts);
  assert.equal(recs.length, 3);
  // s1: part updated 5.6s ago (within window) => running
  assert.equal(recs[0].id, "s1");
  assert.equal(recs[0].state, STATE.RUNNING);
  assert.equal(recs[0].directory, "C:/x");
  // s2: no parts (last_part_upd empty) => idle
  assert.equal(recs[1].lastPartUpdMs, null);
  assert.equal(recs[1].state, STATE.IDLE);
  // s3: pending question => waiting (NEEDS_USER)
  assert.equal(recs[2].pendingQuestion, 1);
  assert.equal(recs[2].state, STATE.WAITING);
});

test("parseRecords: skips blank lines and empty input", () => {
  const opts = { nowMs: NOW };
  assert.deepEqual(parseRecords([], opts), []);
  assert.deepEqual(parseRecords(["", "   "], opts), []);
  const mixed = parseRecords(["", "s9|C:/w|t|1788556293534||0", ""], opts);
  assert.equal(mixed.length, 1);
  assert.equal(mixed[0].state, STATE.IDLE);
});

test("RUN_WINDOW_MS is a positive number (the RUNNING recency window)", () => {
  assert.ok(RUN_WINDOW_MS > 0);
});
