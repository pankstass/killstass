/* v1.9 — QR Code Model 2 encoder (byte mode, versions 1–40, ECC L/M/Q/H), written for KILLSTASS.
   ISO/IEC 18004 structure: data bits → Reed–Solomon blocks → interleave → zigzag placement → best of 8 masks.
   No network, no dependencies; output is an SVG string (dark modules on a white plate with a quiet zone). */
const ECC = { L: 0, M: 1, Q: 2, H: 3 };
const FORMAT_BITS = [1, 0, 3, 2]; // L, M, Q, H as written into the format information
// prettier-ignore
const ECC_PER_BLOCK = [
  [-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
  [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28],
  [-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
  [-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
];
// prettier-ignore
const BLOCKS = [
  [-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25],
  [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49],
  [-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68],
  [-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81],
];
const bit = (x, i) => ((x >>> i) & 1) !== 0;

function rawModules(ver) {
  let n = (16 * ver + 128) * ver + 64;
  if (ver >= 2) {
    const align = Math.floor(ver / 7) + 2;
    n -= (25 * align - 10) * align - 55;
    if (ver >= 7) n -= 36;
  }
  return n;
}
const dataCodewords = (ver, e) =>
  Math.floor(rawModules(ver) / 8) - ECC_PER_BLOCK[e][ver] * BLOCKS[e][ver];

function alignmentPositions(ver) {
  if (ver === 1) return [];
  const count = Math.floor(ver / 7) + 2,
    size = ver * 4 + 17,
    step = Math.floor((ver * 8 + count * 3 + 5) / (count * 4 - 4)) * 2,
    out = [];
  for (let pos = size - 7; out.length < count - 1; pos -= step)
    out.unshift(pos);
  out.unshift(6);
  return out;
}

/* GF(2^8) with the QR polynomial x^8 + x^4 + x^3 + x^2 + 1. */
function gfMul(x, y) {
  let z = 0;
  for (let i = 7; i >= 0; i--) {
    z = (z << 1) ^ ((z >>> 7) * 0x11d);
    z ^= ((y >>> i) & 1) * x;
  }
  return z & 0xff;
}
function rsDivisor(degree) {
  const out = new Array(degree).fill(0);
  out[degree - 1] = 1;
  let root = 1;
  for (let i = 0; i < degree; i++) {
    for (let j = 0; j < degree; j++) {
      out[j] = gfMul(out[j], root);
      if (j + 1 < degree) out[j] ^= out[j + 1];
    }
    root = gfMul(root, 2);
  }
  return out;
}
function rsRemainder(data, divisor) {
  const out = divisor.map(() => 0);
  for (const b of data) {
    const factor = b ^ out.shift();
    out.push(0);
    divisor.forEach((c, i) => (out[i] ^= gfMul(c, factor)));
  }
  return out;
}

function encodeData(bytes, ver, e) {
  const bits = [],
    push = (value, len) => {
      for (let i = len - 1; i >= 0; i--) bits.push((value >>> i) & 1);
    };
  push(0b0100, 4);
  push(bytes.length, ver <= 9 ? 8 : 16);
  for (const b of bytes) push(b, 8);
  const capacity = dataCodewords(ver, e) * 8;
  push(0, Math.min(4, capacity - bits.length));
  push(0, (8 - (bits.length % 8)) % 8);
  for (let pad = 0xec; bits.length < capacity; pad ^= 0xec ^ 0x11) push(pad, 8);
  const out = [];
  for (let i = 0; i < bits.length; i += 8)
    out.push(bits.slice(i, i + 8).reduce((a, b) => (a << 1) | b, 0));
  return out;
}

function interleave(data, ver, e) {
  const count = BLOCKS[e][ver],
    eccLen = ECC_PER_BLOCK[e][ver],
    raw = Math.floor(rawModules(ver) / 8),
    short = count - (raw % count),
    shortLen = Math.floor(raw / count),
    divisor = rsDivisor(eccLen),
    blocks = [];
  for (let i = 0, k = 0; i < count; i++) {
    const part = data.slice(k, k + shortLen - eccLen + (i < short ? 0 : 1));
    k += part.length;
    const ecc = rsRemainder(part, divisor);
    if (i < short) part.push(0);
    blocks.push(part.concat(ecc));
  }
  const out = [];
  for (let i = 0; i < blocks[0].length; i++)
    blocks.forEach((b, j) => {
      if (i !== shortLen - eccLen || j >= short) out.push(b[i]);
    });
  return out;
}

class Grid {
  constructor(ver) {
    this.size = ver * 4 + 17;
    this.dark = Array.from({ length: this.size }, () =>
      new Array(this.size).fill(false),
    );
    this.fixed = Array.from({ length: this.size }, () =>
      new Array(this.size).fill(false),
    );
  }
  set(x, y, dark) {
    this.dark[y][x] = dark;
    this.fixed[y][x] = true;
  }
}

function drawFunctions(g, ver) {
  const n = g.size;
  for (let i = 0; i < n; i++) {
    g.set(6, i, i % 2 === 0);
    g.set(i, 6, i % 2 === 0);
  }
  for (const [cx, cy] of [
    [3, 3],
    [n - 4, 3],
    [3, n - 4],
  ])
    for (let dy = -4; dy <= 4; dy++)
      for (let dx = -4; dx <= 4; dx++) {
        const x = cx + dx,
          y = cy + dy,
          d = Math.max(Math.abs(dx), Math.abs(dy));
        if (x >= 0 && x < n && y >= 0 && y < n) g.set(x, y, d !== 2 && d !== 4);
      }
  const pos = alignmentPositions(ver),
    last = pos.length - 1;
  pos.forEach((x, i) =>
    pos.forEach((y, j) => {
      if (
        (i === 0 && j === 0) ||
        (i === 0 && j === last) ||
        (i === last && j === 0)
      )
        return;
      for (let dy = -2; dy <= 2; dy++)
        for (let dx = -2; dx <= 2; dx++)
          g.set(x + dx, y + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
    }),
  );
  drawFormat(g, 0, 0); // reserve; rewritten after masking
  if (ver >= 7) {
    let rem = ver;
    for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
    const bits = (ver << 12) | rem;
    for (let i = 0; i < 18; i++) {
      const a = n - 11 + (i % 3),
        b = Math.floor(i / 3);
      g.set(a, b, bit(bits, i));
      g.set(b, a, bit(bits, i));
    }
  }
}

function drawFormat(g, e, mask) {
  const data = (FORMAT_BITS[e] << 3) | mask;
  let rem = data;
  for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
  const bits = ((data << 10) | rem) ^ 0x5412,
    n = g.size;
  for (let i = 0; i <= 5; i++) g.set(8, i, bit(bits, i));
  g.set(8, 7, bit(bits, 6));
  g.set(8, 8, bit(bits, 7));
  g.set(7, 8, bit(bits, 8));
  for (let i = 9; i < 15; i++) g.set(14 - i, 8, bit(bits, i));
  for (let i = 0; i < 8; i++) g.set(n - 1 - i, 8, bit(bits, i));
  for (let i = 8; i < 15; i++) g.set(8, n - 15 + i, bit(bits, i));
  g.set(8, n - 8, true); // the dark module
}

function drawCodewords(g, codewords) {
  const n = g.size;
  let i = 0;
  for (let right = n - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let vert = 0; vert < n; vert++)
      for (let j = 0; j < 2; j++) {
        const x = right - j,
          up = ((right + 1) & 2) === 0,
          y = up ? n - 1 - vert : vert;
        if (!g.fixed[y][x] && i < codewords.length * 8) {
          g.dark[y][x] = bit(codewords[i >>> 3], 7 - (i & 7));
          i++;
        }
      }
  }
}

const MASKS = [
  (x, y) => (x + y) % 2 === 0,
  (x, y) => y % 2 === 0,
  (x) => x % 3 === 0,
  (x, y) => (x + y) % 3 === 0,
  (x, y) => (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0,
  (x, y) => ((x * y) % 2) + ((x * y) % 3) === 0,
  (x, y) => (((x * y) % 2) + ((x * y) % 3)) % 2 === 0,
  (x, y) => (((x + y) % 2) + ((x * y) % 3)) % 2 === 0,
];
function applyMask(g, m) {
  for (let y = 0; y < g.size; y++)
    for (let x = 0; x < g.size; x++)
      if (!g.fixed[y][x] && MASKS[m](x, y)) g.dark[y][x] = !g.dark[y][x];
}

/* Penalty rules N1–N4 (runs, 2×2 blocks, finder-like patterns, dark balance). */
function penalty(g) {
  const n = g.size,
    d = g.dark;
  let score = 0,
    darkCount = 0;
  const lines = [];
  for (let i = 0; i < n; i++) {
    lines.push(d[i]);
    lines.push(d.map((row) => row[i]));
  }
  const pattern = [true, false, true, true, true, false, true];
  for (const line of lines) {
    let run = 1;
    for (let i = 1; i <= n; i++) {
      if (i < n && line[i] === line[i - 1]) run++;
      else {
        if (run >= 5) score += 3 + run - 5;
        run = 1;
      }
    }
    for (let i = 0; i + 7 <= n; i++) {
      if (!pattern.every((v, k) => line[i + k] === v)) continue;
      const before = i >= 4 && [1, 2, 3, 4].every((k) => !line[i - k]),
        after = i + 11 <= n && [7, 8, 9, 10].every((k) => !line[i + k]);
      if (before || after) score += 40;
    }
  }
  for (let y = 0; y < n; y++)
    for (let x = 0; x < n; x++) {
      if (d[y][x]) darkCount++;
      if (
        x + 1 < n &&
        y + 1 < n &&
        d[y][x] === d[y][x + 1] &&
        d[y][x] === d[y + 1][x] &&
        d[y][x] === d[y + 1][x + 1]
      )
        score += 3;
    }
  score += Math.floor(Math.abs((darkCount * 100) / (n * n) - 50) / 5) * 10;
  return score;
}

/* Returns { version, size, mask, modules } with modules[y][x] === true for dark. */
export function qrMatrix(
  text,
  level = "M",
  { minVersion = 1, mask = -1 } = {},
) {
  const e = ECC[level] ?? ECC.M,
    bytes = [...new TextEncoder().encode(String(text))];
  let ver = minVersion;
  while (ver <= 40 && bytes.length + (ver <= 9 ? 2 : 3) > dataCodewords(ver, e))
    ver++;
  if (ver > 40) throw new Error("qr_too_long");
  const codewords = interleave(encodeData(bytes, ver, e), ver, e);
  let best = null;
  for (let m = 0; m < 8; m++) {
    if (mask >= 0 && m !== mask) continue;
    const g = new Grid(ver);
    drawFunctions(g, ver);
    drawCodewords(g, codewords);
    applyMask(g, m);
    drawFormat(g, e, m);
    const p = penalty(g);
    if (!best || p < best.p) best = { p, g, m };
  }
  return {
    version: ver,
    size: best.g.size,
    mask: best.m,
    modules: best.g.dark,
  };
}

export function qrSvg(text, { level = "M", label = "", quiet = 4 } = {}) {
  const q = qrMatrix(text, level),
    total = q.size + quiet * 2;
  let path = "";
  q.modules.forEach((row, y) => {
    let x = 0;
    while (x < q.size) {
      if (!row[x]) {
        x++;
        continue;
      }
      let w = 1;
      while (x + w < q.size && row[x + w]) w++;
      path += `M${x + quiet} ${y + quiet}h${w}v1h-${w}z`;
      x += w;
    }
  });
  const esc = (v) =>
    String(v).replace(
      /[&<>"]/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c],
    );
  return `<svg class="qr" viewBox="0 0 ${total} ${total}" role="img" aria-label="${esc(label)}" shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg"><rect width="${total}" height="${total}" fill="#fff"/><path fill="#000" d="${path}"/></svg>`;
}
