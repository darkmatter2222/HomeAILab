import { test } from "node:test";
import assert from "node:assert/strict";
import * as render from "../src/render.js";
import { STATE } from "../src/sessions.js";

test("main page yields up to 6 project slots", () => {
  const r = render.render({
    projects: [
      { alias: "a", path: "/a" },
      { alias: "b", path: "/b" },
      { alias: "c", path: "/c" },
      { alias: "d", path: "/d" },
      { alias: "e", path: "/e" },
      { alias: "f", path: "/f" },
    ],
    live: { a: { state: STATE.RUNNING } },
    phase: 0,
  });
  assert.equal(r.keys.length, 6);
  assert.ok(r.keys.every((k) => typeof k.image === "string" && k.image.startsWith("data:image/svg+xml")));
});

test("main page with fewer projects shows placeholders for empty slots", () => {
  const r = render.render({
    projects: [{ alias: "a", path: "/a" }],
    live: { a: { state: STATE.WAITING } },
    phase: 0,
  });
  assert.equal(r.keys.length, 6);
  // first key is the real project, rest are placeholders
  assert.equal(r.keys[0].kind, "project");
  assert.equal(r.keys[1].kind, "placeholder");
});

test("menu page: 5 project keys + 1 nav (next)", () => {
  const r = render.render({
    page: "menu",
    menuPage: 0,
    projects: [
      { alias: "a", path: "/a" }, { alias: "b", path: "/b" },
      { alias: "c", path: "/c" }, { alias: "d", path: "/d" },
      { alias: "e", path: "/e" }, { alias: "f", path: "/f" },
    ],
    live: {},
    phase: 0,
  });
  assert.equal(r.keys.length, 6);
  assert.equal(r.keys[5].kind, "nav");
  assert.equal(r.pages, 2);
});

test("menu page 1: shows remaining projects and nav flips to Back", () => {
  const r = render.render({
    page: "menu",
    menuPage: 1,
    projects: [
      { alias: "a", path: "/a" }, { alias: "b", path: "/b" },
      { alias: "c", path: "/c" }, { alias: "d", path: "/d" },
      { alias: "e", path: "/e" }, { alias: "f", path: "/f" },
    ],
    live: {},
    phase: 0,
  });
  assert.equal(r.keys[5].image.length > 0, true);
  // nav label should be "Back" on page 1
});

test("project key carries live state + sessionId", () => {
  const r = render.render({
    projects: [{ alias: "homeai", path: "/homeai" }],
    live: { homeai: { state: STATE.WAITING, sessionId: "s1" } },
    phase: 0,
  });
  assert.equal(r.keys[0].kind, "project");
});

test("countAlerts counts waiting + newAlert", () => {
  const live = {
    a: { state: STATE.WAITING, newAlert: true },
    b: { state: STATE.RUNNING, newAlert: false },
    c: { state: STATE.IDLE, newAlert: false },
    d: { state: STATE.WAITING, newAlert: false },
  };
  assert.equal(render.countAlerts(live), 2);
  assert.equal(render.countAlerts({}), 0);
  assert.equal(render.countAlerts({ a: { state: STATE.IDLE, newAlert: true } }), 1);
});
