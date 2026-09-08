// render.js — map the current page/state to the set of key images to push.
//
// Layout (Mini: 6 keys):
//   main page  -> up to 6 project keys, one per configured project
//   menu page  -> 5 project keys + 1 nav key, for when there are >6 projects
//
// Each project key shows its RAG state color (green/amber/red) via keyart.

import * as keyart from "./keyart.js";
import { STATE } from "./sessions.js";

// How many project keys fit on the Mini main page.
const MAIN_PER_PAGE = 6;
// How many project keys fit on a menu page (the 6th key is the nav key).
const MENU_PER_PAGE = 5;

// Count how many live sessions are waiting (red = asking a question).
export function countAlerts(live) {
  let n = 0;
  for (const a of Object.keys(live || {})) {
    const l = live[a];
    if (l && (l.state === STATE.WAITING || l.newAlert)) n++;
  }
  return n;
}

// Produce the ordered list of key images for the current view.
// `live` maps alias -> { state, sessionId, ... }; a project with no live
// session renders as OFF (gray).
export function render({
  page = "main",
  menuPage = 0,
  projects = [],
  live = {},
  phase = 0,
  serverOk = true,
} = {}) {
  const keys = [];
  if (page === "menu") {
    const start = menuPage * MENU_PER_PAGE;
    for (let i = 0; i < MENU_PER_PAGE; i++) {
      const p = projects[start + i];
      if (p) {
        const l = live[p.alias] || { state: STATE.OFF };
        keys.push({
          kind: "project",
          slot: i,
          image: keyart.projectKey({ alias: p.alias, state: l.state, color: p.color, phase }),
        });
      } else {
        keys.push({ kind: "placeholder", slot: i, image: keyart.placeholderKey({ label: "add project", phase }) });
      }
    }
    // 6th key on the menu page = nav (Back/Next).
    const pages = Math.max(1, Math.ceil(projects.length / MENU_PER_PAGE));
    const label = menuPage > 0 ? "Back" : (menuPage + 1 < pages ? "Next" : "Back");
    keys.push({ kind: "nav", slot: MENU_PER_PAGE, image: keyart.nextKey({ label }) });
    return { keys, pages, menuPage };
  }
  // main page: one key per project (up to 6 on the Mini).
  for (let i = 0; i < MAIN_PER_PAGE; i++) {
    const p = projects[i];
    if (p) {
      const l = live[p.alias] || { state: STATE.OFF };
      keys.push({
        kind: "project",
        slot: i,
        image: keyart.projectKey({ alias: p.alias, state: l.state, color: p.color, phase }),
      });
    } else {
      keys.push({ kind: "placeholder", slot: i, image: keyart.placeholderKey({ label: "add project", phase }) });
    }
  }
  return { keys, pages: 1, menuPage: 0 };
}

export default { render, countAlerts, MAIN_PER_PAGE, MENU_PER_PAGE };
