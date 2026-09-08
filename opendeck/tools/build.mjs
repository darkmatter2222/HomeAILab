// build.mjs — bundle src/plugin.js -> dev.ryans.opendeck.streamDeckPlugin/bin/plugin.mjs
// with esbuild, target node, ESM. Same approach as agent-vitals.
import { build } from "esbuild";
import { mkdir, copyFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(__dirname, "..", "dev.ryans.opendeck.streamDeckPlugin", "bin");
await mkdir(outDir, { recursive: true });

const result = await build({
  entryPoints: [resolve(__dirname, "..", "src", "plugin.js")],
  bundle: true,
  platform: "node",
  format: "esm",
  target: "node18",
  outfile: resolve(outDir, "plugin.mjs"),
  // ws's optional native deps aren't needed on the Stream Deck host.
  external: ["bufferutil", "utf-8-validate"],
  banner: {
    js: [
      "import { createRequire as __ccr } from 'node:module';",
      "const require = __ccr(import.meta.url);",
    ].join("\n"),
  },
  logLevel: "silent",
});

if (result.errors.length) {
  console.error(result.errors);
  process.exit(1);
}

// The installed plugin resolves its config dir to the plugin root (resolve(bin,
// "..")). Ship the user's projects.json there so a fresh install works without
// the repo present.
const pluginRoot = resolve(__dirname, "..", "dev.ryans.opendeck.streamDeckPlugin");
const src = resolve(__dirname, "..", "projects.json");
if (existsSync(src)) {
  await copyFile(src, resolve(pluginRoot, "projects.json"));
}
console.log("built dev.ryans.opendeck.streamDeckPlugin/bin/plugin.mjs");
