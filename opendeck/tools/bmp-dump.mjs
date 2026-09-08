// bmp-dump.mjs — parse a BMP file and print a high-res ASCII + color histogram.
// Usage: node tools/bmp-dump.mjs <file.bmp>
import { readFileSync } from "node:fs";

const file = process.argv[2];
const cx = process.argv[3] ? Number(process.argv[3]) : 0;
const cy = process.argv[4] ? Number(process.argv[4]) : 0;
const cw = process.argv[5] ? Number(process.argv[5]) : 0;
const ch_ = process.argv[6] ? Number(process.argv[6]) : 0;
const buf = readFileSync(file);
// BMP: 14-byte header, then pixel data (bottom-up, BGR, 24-bit assumed)
const fullW = buf.readUInt16LE(18);
const fullH = buf.readUInt16LE(22);
const bits = buf.readUInt16LE(28);
const off = buf.readUInt32LE(10);
let w = fullW, h = fullH;
let ox = 0, oy = 0;
if (cw > 0 && ch_ > 0) {
  w = Math.min(cw, fullW - cx);
  h = Math.min(ch_, fullH - cy);
  ox = cx; oy = cy;
}
// Row stride is based on the FULL image width (BMP rows span the full width).
const rowBytes = bits === 32 ? fullW * 4 : (Math.ceil(fullW * 3 / 4) * 4);
const stride = bits === 32 ? 4 : 3;
console.log(`BMP full ${fullW}x${fullH} ${bits}bpp; crop ${w}x${h} at (${ox},${oy})`);
// build a downsampled ASCII grid (e.g. 120x40)
const GW = 120, GH = 40;
const out = [];
for (let gy = 0; gy < GH; gy++) {
  const pyFull = oy + (h - 1 - Math.floor((gy * h) / GH));
  let line = "";
  for (let gx = 0; gx < GW; gx++) {
    const px = ox + Math.floor((gx * w) / GW);
    const rowOff = off + (fullH - 1 - pyFull) * rowBytes;
    const b = buf[rowOff + px * stride + 0];
    const g = buf[rowOff + px * stride + 1];
    const r = buf[rowOff + px * stride + 2];
    let ch = " ";
    if (r > 200 && g < 150 && b < 150) ch = "R";
    else if (g > 150 && r < 150 && b < 150) ch = "G";
    else if (b > 200 && r < 150) ch = "B";
    else {
      const bright = (r + g + b) / 3;
      if (bright > 180) ch = "#";
      else if (bright > 90) ch = "+";
    }
    line += ch;
  }
  out.push(line);
}
console.log("---- ASCII " + GW + "x" + GH + " (R/G/B colored, # bright, + mid) ----");
for (const l of out) console.log(l);

// color histogram of saturated pixels
const hist = { red: 0, green: 0, blue: 0, amber: 0, gray: 0, other: 0 };
for (let y = 0; y < h; y += 3) {
  const pyFull = oy + (h - 1 - y);
  for (let x = 0; x < w; x += 3) {
    const px = ox + x;
    const rowOff = off + (fullH - 1 - pyFull) * rowBytes;
    const b = buf[rowOff + px * stride + 0];
    const g = buf[rowOff + px * stride + 1];
    const r = buf[rowOff + px * stride + 2];
    if (r > 200 && g < 150 && b < 150) hist.red++;
    else if (g > 150 && r < 150 && b < 150) hist.green++;
    else if (b > 200 && r < 150) hist.blue++;
    else if (r > 200 && g > 150 && b < 120) hist.amber++;
    else if (Math.abs(r - 90) < 40 && Math.abs(g - 94) < 40 && Math.abs(b - 107) < 40) hist.gray++;
    else hist.other++;
  }
}
console.log("color histogram (sampled /3): " + JSON.stringify(hist));
process.exit(0);
