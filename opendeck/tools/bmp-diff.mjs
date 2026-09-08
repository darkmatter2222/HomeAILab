// bmp-diff.mjs — compare two full-screen BMP captures, restricted to the
// Stream Deck app window (device mirror) region, and report how many pixels
// changed. Usage: node tools/bmp-diff.mjs <prev.bmp> <cur.bmp> [x y w h]
import { readFileSync } from "node:fs";

function parseBmp(buf) {
  if (buf.toString("latin1", 0, 2) !== "BM") throw new Error("not a BMP");
  const dataOffset = buf.readUInt32LE(10);
  const ihdr = buf.readUInt32LE(14); // BITMAPINFOHEADER size
  const w = buf.readInt32LE(18);
  const h = buf.readInt32LE(22);
  const planes = buf.readUInt16LE(26);
  const bpp = buf.readUInt16LE(28);
  return { w, h: Math.abs(h), bpp, dataOffset, buf };
}

function pixelAt(img, x, y) {
  // BMP rows are bottom-up; y=0 is the top row in screen coords.
  const { w, h, bpp, dataOffset, buf } = img;
  const bytesPerPx = bpp / 8;
  const rowStartY = (h - 1 - y); // bottom-up index for top-origin row y
  const rowBytes = ((w * bytesPerPx + 3) & ~3);
  const off = dataOffset + rowStartY * rowBytes + x * bytesPerPx;
  if (bpp === 32) {
    const b = buf.readUInt8(off), g = buf.readUInt8(off + 1), r = buf.readUInt8(off + 2);
    return { r, g, b };
  }
  if (bpp === 24) {
    const b = buf.readUInt8(off), g = buf.readUInt8(off + 1), r = buf.readUInt8(off + 2);
    return { r, g, b };
  }
  if (bpp === 8) {
    const paletteOffset = 54; // after 14+40 header
    const idx = buf.readUInt8(off);
    const p = paletteOffset + idx * 4;
    const b = buf.readUInt8(p), g = buf.readUInt8(p + 1), r = buf.readUInt8(p + 2);
    return { r, g, b };
  }
  throw new Error("unsupported bpp " + bpp);
}

const [, , prevPath, curPath, rx, ry, rw, rh] = process.argv;
const prev = parseBmp(readFileSync(prevPath));
const cur = parseBmp(readFileSync(curPath));
if (prev.w !== cur.w || prev.h !== cur.h) {
  console.log(`size mismatch: prev ${prev.w}x${prev.h} vs cur ${cur.w}x${cur.h}`);
}

const x0 = rx != null ? Number(rx) : 0;
const y0 = ry != null ? Number(ry) : 0;
const cw = rw != null ? Number(rw) : prev.w - x0;
const ch = rh != null ? Number(rh) : prev.h - y0;

let changed = 0, total = 0;
// Sample every 2nd pixel in both dims for speed; scale factor applied to report.
for (let y = y0; y < y0 + ch; y += 2) {
  for (let x = x0; x < x0 + cw; x += 2) {
    const a = pixelAt(prev, x, y);
    const b = pixelAt(cur, x, y);
    total++;
    if (a.r !== b.r || a.g !== b.g || a.b !== b.b) changed++;
  }
}
const sampleScale = 4; // 2x2 stride => each sampled pixel represents 4 real pixels
console.log(`region: x=${x0} y=${y0} w=${cw} h=${ch}`);
console.log(`sampled ${total} pixels (2x stride); differing samples: ${changed}`);
console.log(`approx differing real pixels (x4): ${changed * sampleScale}`);
console.log(changed === 0 ? "REGION UNCHANGED (device screen identical between the two captures)" : `REGION CHANGED: ~${changed * sampleScale} pixels differ`);
