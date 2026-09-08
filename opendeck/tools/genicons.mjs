// genicons.mjs — rasterize the key art into the static PNGs the manifest's
// Icons/States reference, plus the action-list (list/) thumbnails. Run after
// install (needs @resvg/resvg-js). Output goes into the .sdPlugin imgs/ tree.
import { Resvg } from "@resvg/resvg-js";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import * as keyart from "../src/keyart.js";
import { STATE } from "../src/sessions.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const imgs = resolve(__dirname, "..", "dev.ryans.opendeck.streamDeckPlugin", "imgs");
await mkdir(resolve(imgs, "list"), { recursive: true });

const W = 324; // list icons a bit bigger for crispness
async function png(name, dataUri, fit) {
  const svg = decodeURIComponent(dataUri.split(",", 2)[1]);
  const resvg = new Resvg(svg, { fitTo: { mode: "width", value: fit || W } });
  const buf = resvg.render().asPng();
  await writeFile(resolve(imgs, name), buf);
  console.log("icon:", name);
}

// Action thumbnails (list/) — small, monochrome-ish.
await png("list/project.png", keyart.projectKey({ alias: "proj", state: STATE.OFF }), 128);
await png("list/alert.png", keyart.alertKey({ count: 1 }), 128);
await png("list/plugin.png", keyart.placeholderKey({ label: "OP" }), 128);

// Default action icons (full 144) — one per RAG state.
await png("project-off.png", keyart.projectKey({ alias: "off", state: STATE.OFF }), W);
await png("project-running.png", keyart.projectKey({ alias: "run", state: STATE.RUNNING }), W);
await png("project-waiting.png", keyart.projectKey({ alias: "wait", state: STATE.WAITING }), W);
await png("project-idle.png", keyart.projectKey({ alias: "idle", state: STATE.IDLE }), W);
await png("project.png", keyart.projectKey({ alias: "project", state: STATE.OFF }), W);
await png("alert.png", keyart.alertKey({ count: 1 }), W);

// The plugin's own category icon.
{
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="144" height="144" viewBox="0 0 144 144">` +
    `<rect width="144" height="144" rx="24" fill="#0c0d10"/>` +
    `<circle cx="44" cy="72" r="13" fill="#2fd06f"/>` +
    `<circle cx="72" cy="72" r="13" fill="#f5b13d"/>` +
    `<circle cx="100" cy="72" r="13" fill="#ff5a4e"/>` +
    `<text x="72" y="122" text-anchor="middle" font-family="Arial" font-size="13" fill="#8b8f9a" font-weight="600">OPENCODE</text>` +
    `</svg>`;
  await png("plugin.png", "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg), 288);
}
console.log("icons written to", imgs);
