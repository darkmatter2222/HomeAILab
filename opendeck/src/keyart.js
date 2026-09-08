// keyart.js - pure 144x144 SVG key renderers with RAG state colors.
//
// RAG mapping (the user's requirement):
//   green  = working   #2fd06f
//   amber  = idle      #f5b13d
//   red    = waiting   #ff5a4e  (opencode is asking a question)
//   gray   = off       #5a5e6b  (no connected opencode env / no session)
//
// Each renderer returns a `data:image/svg+xml` URI, which the plugin pushes
// to the Stream Deck via setImage. No I/O, no side effects — unit-testable.

import { STATE_COLOR, STATE } from "./sessions.js";

const W = 144;
const H = 144;

const BG = "#101114";
const TEXT = "#eef1f6";
const MUTED = "#8b8f9a";

function toDataUri(svg) {
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
}

function frame(state) {
  const color = STATE_COLOR[state] || STATE_COLOR[STATE.OFF];
  return color;
}

// A project key: shows the short alias + a RAG state dot. `state` is one of
// the STATE values. Auto-fits the alias to the 144px key (shrinks long names).
export function projectKey({ alias = "project", state = STATE.OFF, color = null, phase = 0 } = {}) {
  const stateColor = color || frame(state);
  const isBreath = (state === STATE.RUNNING || state === STATE.WAITING) && phase > 0;
  // Shrink font if the alias is long so it auto-fits the key.
  let fontSize = 30;
  const label = alias.slice(0, 16);
  if (label.length > 8) fontSize = 24;
  if (label.length > 12) fontSize = 19;
  // Breathing: pulse the dot opacity across frames for active states.
  const dotOpacity = isBreath ? [1, 0.4, 0.7][phase % 3] : 1;
  const dotFill = state === STATE.OFF ? "none" : stateColor;
  const dotStroke = state === STATE.OFF ? stateColor : "none";
  const labelColor = state === STATE.OFF ? MUTED : TEXT;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">` +
    `<rect width="${W}" height="${H}" rx="20" fill="${BG}"/>` +
    // state ring (RAG color)
    `<rect x="4" y="4" width="${W - 8}" height="${H - 8}" rx="16" fill="none" stroke="${stateColor}" stroke-width="4" ${state === STATE.OFF ? `stroke-opacity="0.5"` : ""}/>` +
    // RAG state dot (top center)
    `<circle cx="${W / 2}" cy="44" r="12" fill="${dotFill}" stroke="${dotStroke}" stroke-width="3" fill-opacity="${dotOpacity}"/>` +
    // state word
    `<text x="${W / 2}" y="86" text-anchor="middle" font-family="Segoe UI, Arial" font-size="16" font-weight="700" fill="${stateColor}">${state.toUpperCase()}</text>` +
    // alias (auto-fit)
    `<text x="${W / 2}" y="118" text-anchor="middle" font-family="Segoe UI, Arial" font-size="${fontSize}" font-weight="600" fill="${labelColor}">${label}</text>` +
    `</svg>`;
  return toDataUri(svg);
}

// Placeholder key for empty slots / spare keys.
export function placeholderKey({ label = "" } = {}) {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">` +
    `<rect width="${W}" height="${H}" rx="20" fill="${BG}"/>` +
    `<rect x="4" y="4" width="${W - 8}" height="${H - 8}" rx="16" fill="none" stroke="#2a2d34" stroke-width="3" stroke-dasharray="6 5"/>` +
    (label
      ? `<text x="${W / 2}" y="${H / 2 + 6}" text-anchor="middle" font-family="Segoe UI, Arial" font-size="15" fill="${MUTED}">${label}</text>`
      : `<text x="${W / 2}" y="${H / 2 + 6}" text-anchor="middle" font-family="Segoe UI, Arial" font-size="40" fill="#3a3e47">+</text>`) +
    `</svg>`;
  return toDataUri(svg);
}

// The "Needs You" alert key: counts sessions blocked on input (red when > 0).
export function alertKey({ count = 0 } = {}) {
  const active = count > 0;
  const color = active ? STATE_COLOR[STATE.WAITING] : "#2a2d34";
  const label = active ? String(count) : "all clear";
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">` +
    `<rect width="${W}" height="${H}" rx="20" fill="${BG}"/>` +
    `<rect x="4" y="4" width="${W - 8}" height="${H - 8}" rx="16" fill="none" stroke="${color}" stroke-width="4"/>` +
    `<text x="${W / 2}" y="66" text-anchor="middle" font-family="Segoe UI, Arial" font-size="44" font-weight="800" fill="${active ? TEXT : MUTED}">${label}</text>` +
    `<text x="${W / 2}" y="104" text-anchor="middle" font-family="Segoe UI, Arial" font-size="14" fill="${MUTED}">needs you</text>` +
    `</svg>`;
  return toDataUri(svg);
}

// A "launch" key: opens a terminal running opencode in the project dir.
export function launchKey({} = {}) {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">` +
    `<rect width="${W}" height="${H}" rx="20" fill="${BG}"/>` +
    `<rect x="4" y="4" width="${W - 8}" height="${H - 8}" rx="16" fill="none" stroke="${STATE_COLOR[STATE.RUNNING]}" stroke-width="4"/>` +
    // play triangle
    `<polygon points="58,48 58,96 96,72" fill="${STATE_COLOR[STATE.RUNNING]}"/>` +
    `<text x="${W / 2}" y="120" text-anchor="middle" font-family="Segoe UI, Arial" font-size="15" font-weight="600" fill="${MUTED}">launch</text>` +
    `</svg>`;
  return toDataUri(svg);
}

// Nav key for paging through project menus ("Next" / "Back").
export function nextKey({ label = "Next" } = {}) {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">` +
    `<rect width="${W}" height="${H}" rx="20" fill="${BG}"/>` +
    `<rect x="4" y="4" width="${W - 8}" height="${H - 8}" rx="16" fill="none" stroke="#4a4e5a" stroke-width="3"/>` +
    (label === "Back"
      ? `<polygon points="96,52 96,92 64,72" fill="${TEXT}"/>`
      : `<polygon points="48,52 48,92 80,72" fill="${TEXT}"/>`) +
    `<text x="${W / 2}" y="118" text-anchor="middle" font-family="Segoe UI, Arial" font-size="15" font-weight="600" fill="${MUTED}">${label}</text>` +
    `</svg>`;
  return toDataUri(svg);
}

export default {
  projectKey,
  placeholderKey,
  alertKey,
  launchKey,
  nextKey,
  toDataUri,
};
