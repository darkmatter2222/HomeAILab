// pack.mjs — produce the installable dev.ryans.opendeck.streamDeckPlugin bundle
// as a zip (a .streamDeckPlugin is just a zipped .sdPlugin folder). Stream Deck
// can import a plugin straight from such a file / a GitHub Release asset.
import { zip, unzip } from "node:zlib";
import { readdir, readFile, writeFile, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const pluginDir = resolve(__dirname, "..", "dev.ryans.opendeck.streamDeckPlugin");
const out = resolve(__dirname, "..", "dev.ryans.opendeck.streamDeckPlugin.streamDeckPlugin");

// Minimal zip writer (store, no compression) so the bundle has no extra deps.
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0);
  }
  return (c ^ 0xffffffff) >>> 0;
}
function u16(n) { const b = Buffer.alloc(2); b.writeUInt16LE(n & 0xffff); return b; }
function u32(n) { const b = Buffer.alloc(4); b.writeUInt32LE(n >>> 0); return b; }

async function buildZip(root) {
  const files = [];
  async function walk(d, prefix) {
    const entries = await readdir(d);
    for (const name of entries) {
      const p = resolve(d, name);
      const st = await stat(p);
      const rel = prefix + name;
      if (st.isDirectory()) await walk(p, rel + "/");
      else if (st.isFile()) files.push({ rel, path: p, size: st.size, mtime: st.mtimeMs });
    }
  }
  await walk(root, "");

  const chunks = [];
  const central = [];
  let offset = 0;
  for (const f of files) {
    const data = await readFile(f.path);
    const nameBuf = Buffer.from(f.rel, "utf8");
    const dosTime = ((new Date(f.mtime).getHours() << 11) | (new Date(f.mtime).getMinutes() << 5) | (new Date(f.mtime).getSeconds() >> 1);
    const dosDate = (((new Date(f.mtime).getFullYear() - 1980) << 9) | ((new Date(f.mtime).getMonth() + 1) << 5) | new Date(f.mtime).getDate();
    const crc = crc32(data);
    const local = Buffer.concat([
      u32(0x04034b50), u16(20), u16(0), u16(0), u16(dosTime), u16(dosDate),
      u32(crc), u32(data.length), u32(data.length), u16(nameBuf.length), u16(0),
      nameBuf, data,
    ]);
    chunks.push(local);
    central.push({ rel: f.rel, crc, size: data.length, offset, mtime: f.mtime });
    offset += local.length;
  }
  let centralBuf = Buffer.alloc(0);
  for (const c of central) {
    const nameBuf = Buffer.from(c.rel, "utf8");
    const dosTime = ((new Date(c.mtime).getHours() << 11) | (new Date(c.mtime).getMinutes() << 5) | (new Date(c.mtime).getSeconds() >> 1);
    const dosDate = (((new Date(c.mtime).getFullYear() - 1980) << 9) | ((new Date(c.mtime).getMonth() + 1) << 5) | new Date(c.mtime).getDate();
    const entry = Buffer.concat([
      u32(0x02014b50), u16(20), u16(20), u16(0), u16(0),
      u16(dosTime), u16(dosDate), u32(c.crc), u32(c.size), u32(c.size),
      u16(nameBuf.length), u16(0), u16(0), u16(0), u32(0), u32(c.offset),
      nameBuf,
    ]);
    centralBuf = Buffer.concat([centralBuf, entry]);
  }
  const centralOffset = offset;
  const eocd = Buffer.concat([
    u32(0x06054b50), u16(0), u16(0), u16(central.length), u16(central.length),
    u32(centralBuf.length), u32(centralOffset), u16(0),
  ]);
  const zipData = Buffer.concat([...chunks, centralBuf, eocd]);
  await writeFile(out, zipData);
  console.log("packed", out, `(${zipData.length} bytes, ${files.length} files)`);
}

if (existsSync(pluginDir)) await buildZip(pluginDir);
else {
  console.error("plugin dir not found:", pluginDir);
  process.exit(1);
}
