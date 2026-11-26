// v1.9: pure-function tests for the attack calculator (web/attackcalc.js) and the QR encoder (web/qr.js);
// v1.12: the ready-made killzone terrain (web/killzones.js); v1.13: weapon rules chips and universal grenades;
// v1.14: the table of the app's sections (web/sections.js).
// No browser and no server: `node --test tests/e2e/unit.test.mjs`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import * as A from "../../web/attackcalc.js";
import { qrMatrix, qrSvg } from "../../web/qr.js";

/* Scripted dice: returns the given values in order and fails loudly if the code rolls more. */
const dice = (values) => {
  let i = 0;
  const roll = () => {
    if (i >= values.length) throw new Error("rolled more dice than scripted");
    return values[i++];
  };
  roll.used = () => i;
  return roll;
};
const gun = (wr = "", extra = {}) =>
  A.weaponProfile({
    type: "ranged",
    atk: "4",
    hit: "3+",
    dmg: "3/4",
    wr,
    ...extra,
  });

test("parsing of datacard values", () => {
  assert.equal(A.stat("3+"), 3);
  assert.equal(A.stat("—", 7), 7);
  assert.deepEqual(A.parseDamage("3/4"), [3, 4]);
  assert.deepEqual(A.parseDamage("5"), [5, 5]);
  const p = A.weaponProfile({
    type: "melee",
    atk: "25",
    hit: "1+",
    dmg: "4/5",
  });
  assert.equal(p.type, "melee");
  assert.equal(p.atk, 20, "attack dice are capped");
  assert.equal(p.hit, 2, "hit is clamped to 2+…6+");
  assert.equal(A.weaponProfile({}).hit, 6);
});

test("weapon rules", () => {
  const r = A.parseRules(
    'Range 8", Piercing 1, Lethal 5+, 3" Devastating 2, Balanced, Saturate, Hot',
  );
  assert.equal(r.range, 8);
  assert.equal(r.piercing, 1);
  assert.equal(r.lethal, 5);
  assert.equal(r.devastating, 2);
  assert.equal(r.devastatingRange, 3);
  assert.ok(r.balanced && r.saturate);
  assert.deepEqual(r.other, ["Hot"]);
  const s = A.parseRules(
    "Accurate 1; Piercing Crits 1; Ceaseless; Relentless; Rending; Punishing; Severe; Brutal",
  );
  assert.equal(s.accurate, 1);
  assert.equal(s.piercingCrits, 1);
  for (const f of [
    "ceaseless",
    "relentless",
    "rending",
    "punishing",
    "severe",
    "brutal",
  ])
    assert.ok(s[f], f);
  assert.deepEqual(s.other, []);
});

test("v1.13: weapon rules chips — formatRules is the inverse of parseRules, toggleRule, grenades", () => {
  for (const wr of [
    "",
    'Range 8", Piercing 1, Lethal 5+, 3" Devastating 2, Balanced, Saturate, Hot',
    "Accurate 1; Piercing Crits 1; Ceaseless; Relentless; Rending; Punishing; Severe; Brutal",
    'Blast 2", Torrent 1", Heavy (Dash only), Limited 1, Silent, Stun, Seek Light',
  ]) {
    const r = A.parseRules(wr);
    assert.deepEqual(A.parseRules(A.formatRules(r)), r, wr);
  }
  assert.equal(
    A.formatRules(A.parseRules('hot, lethal 4, range 6", 1" devastating 3')),
    'Range 6", 1" Devastating 3, Lethal 4+, hot',
    "a canonical order; the unmodelled rules are kept as written",
  );
  let wr = A.toggleRule('Range 6", Hot', "lethal");
  assert.equal(wr, 'Range 6", Lethal 5+, Hot', "on: the first value");
  wr = A.toggleRule(wr, "lethal", "3");
  assert.equal(A.parseRules(wr).lethal, 3);
  wr = A.toggleRule(wr, "lethal");
  assert.equal(wr, 'Range 6", Hot', "off");
  wr = A.toggleRule(A.toggleRule("", "saturate"), "accurate");
  assert.equal(wr, "Accurate 1, Saturate");
  assert.equal(A.toggleRule(wr, "saturate"), "Accurate 1");
  assert.equal(
    A.toggleRule('2" Devastating 3', "devastating"),
    "",
    "the distance goes with the rule",
  );
  assert.equal(A.toggleRule("Hot", "nonsense"), "Hot");
  assert.deepEqual(
    A.RULE_CHIPS.map((c) => c.k),
    [
      "accurate",
      "balanced",
      "ceaseless",
      "relentless",
      "lethal",
      "rending",
      "punishing",
      "severe",
      "devastating",
      "piercing",
      "piercingCrits",
      "saturate",
    ],
  );
  for (const c of A.RULE_CHIPS) {
    const on = A.parseRules(A.toggleRule("", c.k))[c.k];
    assert.equal(on, c.vals ? c.vals[0] : true, c.k);
  }
  const frag = A.weaponProfile(A.GRENADES.frag),
    krak = A.weaponProfile(A.GRENADES.krak);
  assert.deepEqual(
    [frag.type, frag.atk, frag.hit, frag.dmg, frag.rules.range],
    ["ranged", 4, 4, [2, 4], 6],
  );
  assert.ok(frag.rules.saturate);
  assert.deepEqual(frag.rules.other, ['Blast 2"']);
  assert.deepEqual(
    [krak.atk, krak.hit, krak.dmg, krak.rules.piercing, krak.rules.saturate],
    [4, 4, [4, 5], 1, true],
  );
  assert.deepEqual(krak.rules.other, []);
});

test("attack dice: hits, crits, Lethal, injured, Accurate", () => {
  let a = A.rollAttack(gun(), {}, dice([6, 5, 2, 1]));
  assert.deepEqual([a.crits, a.normals, a.fails], [1, 1, 2]);
  a = A.rollAttack(gun("Lethal 5+"), {}, dice([5, 6, 4, 1]));
  assert.deepEqual([a.crits, a.normals, a.fails], [2, 1, 1]);
  a = A.rollAttack(gun(), { injured: true }, dice([3, 4, 5, 6]));
  assert.equal(a.hit, 4);
  assert.deepEqual([a.crits, a.normals, a.fails], [1, 2, 1]);
  const roll = dice([2, 2, 6]);
  a = A.rollAttack(gun("Accurate 1"), {}, roll);
  assert.equal(roll.used(), 3, "one die is retained without rolling");
  assert.deepEqual([a.crits, a.normals, a.fails], [1, 1, 2]);
});

test("attack dice: re-rolls (Balanced, Ceaseless, Relentless)", () => {
  let a = A.rollAttack(gun("Balanced"), {}, dice([1, 2, 6, 6, 5]));
  assert.deepEqual([a.crits, a.normals, a.fails], [2, 1, 1]);
  assert.equal(a.dice[0].first, 1);
  a = A.rollAttack(gun("Ceaseless"), {}, dice([2, 2, 1, 6, 6, 3]));
  assert.deepEqual(
    [a.crits, a.normals, a.fails],
    [2, 1, 1],
    "both 2s are re-rolled, the 1 stays",
  );
  a = A.rollAttack(gun("Relentless"), {}, dice([1, 2, 5, 6, 3, 1]));
  assert.deepEqual([a.crits, a.normals, a.fails], [1, 2, 1]);
});

test("attack dice: Severe, Rending, Punishing, Obscured", () => {
  let a = A.rollAttack(gun("Severe"), {}, dice([5, 4, 2, 2]));
  assert.ok(a.severe);
  assert.deepEqual([a.crits, a.normals], [1, 1]);
  a = A.rollAttack(gun("Rending"), {}, dice([6, 4, 2, 1]));
  assert.ok(a.rending);
  assert.deepEqual([a.crits, a.normals], [2, 0]);
  a = A.rollAttack(gun("Punishing"), {}, dice([6, 2, 1, 1]));
  assert.ok(a.punishing);
  assert.deepEqual(
    [a.crits, a.normals, a.fails],
    [1, 1, 2],
    "one fail becomes a normal success",
  );
  a = A.rollAttack(gun("Rending"), { obscured: true }, dice([6, 5, 4, 1]));
  assert.ok(a.obscured);
  assert.deepEqual(
    [a.crits, a.normals, a.discarded],
    [0, 2, 1],
    "crits become normals, one success is discarded",
  );
  a = A.rollAttack(
    A.weaponProfile({ type: "melee", atk: 4, hit: "3+" }),
    { obscured: true },
    dice([6, 5, 4, 1]),
  );
  assert.equal(a.obscured, false, "obscured does not apply to melee");
});

test("defence dice: Piercing, Piercing Crits, cover, Saturate", () => {
  const hit = { crits: 1 },
    miss = { crits: 0 };
  let d = A.rollDefence(gun(), miss, { save: "3+" }, {}, dice([6, 3, 2]));
  assert.deepEqual([d.count, d.crits, d.normals], [3, 1, 1]);
  d = A.rollDefence(gun("Piercing 1"), miss, { save: "3+" }, {}, dice([6, 6]));
  assert.deepEqual([d.count, d.crits], [2, 2]);
  d = A.rollDefence(
    gun("Piercing Crits 1"),
    miss,
    { save: "3+" },
    {},
    dice([1, 1, 1]),
  );
  assert.equal(d.count, 3, "Piercing Crits needs a critical success");
  d = A.rollDefence(
    gun("Piercing Crits 1"),
    hit,
    { save: "3+" },
    {},
    dice([1, 1]),
  );
  assert.equal(d.count, 2);
  d = A.rollDefence(gun(), miss, { save: "4+" }, { cover: true }, dice([1, 1]));
  assert.deepEqual([d.cover, d.normals, d.dice.length], [1, 1, 2]);
  d = A.rollDefence(
    gun("Saturate"),
    miss,
    { save: "4+" },
    { cover: true },
    dice([1, 1, 1]),
  );
  assert.equal(d.cover, 0);
});

test("the defender allocates saves to take the least damage", () => {
  assert.equal(
    A.allocate({ crits: 1, normals: 1 }, { crits: 0, normals: 2 }, [3, 4])
      .damage,
    3,
  );
  assert.equal(
    A.allocate({ crits: 2, normals: 0 }, { crits: 1, normals: 1 }, [3, 4])
      .damage,
    4,
  );
  assert.equal(
    A.allocate({ crits: 0, normals: 3 }, { crits: 1, normals: 1 }, [3, 4])
      .damage,
    3,
  );
  assert.equal(
    A.allocate({ crits: 1, normals: 2 }, { crits: 0, normals: 2 }, [2, 6])
      .damage,
    4,
  );
  assert.equal(
    A.allocate({ crits: 0, normals: 0 }, { crits: 3, normals: 0 }, [3, 4])
      .damage,
    0,
  );
});

/* Independent reference: brute force over every way to spend each save die. */
function bestDamage(hc, hn, sc, sn, [dn, dc]) {
  let best = Infinity;
  const go = (c, n, half, sc, sn) => {
    if (!sc && !sn) {
      best = Math.min(best, (c + half) * dc + n * dn);
      return;
    }
    if (sc) {
      go(c, n, half, sc - 1, sn);
      if (c) go(c - 1, n, half, sc - 1, sn);
      if (n) go(c, n - 1, half, sc - 1, sn);
      if (half) go(c, n, half - 1, sc - 1, sn);
    } else {
      go(c, n, half, 0, sn - 1);
      if (n) go(c, n - 1, half, 0, sn - 1);
      if (c) go(c - 1, n, half + 1, 0, sn - 1);
      if (half) go(c, n, half - 1, 0, sn - 1);
    }
  };
  go(hc, hn, 0, sc, sn);
  return best;
}
function* sequences(n) {
  const v = Array(n).fill(1);
  for (;;) {
    yield [...v];
    let i = n - 1;
    while (i >= 0 && v[i] === 6) v[i--] = 1;
    if (i < 0) return;
    v[i]++;
  }
}

test("resolve() is exact against an independent enumeration; simulate() converges to it", () => {
  const p = A.weaponProfile({
      type: "ranged",
      atk: 2,
      hit: "4+",
      dmg: "3/4",
      wr: "Devastating 1",
    }),
    target = { save: "4+", wounds: 7 };
  let total = 0,
    hits = 0,
    kills = 0,
    count = 0;
  for (const s of sequences(5)) {
    const r = A.resolve(p, target, {}, dice(s));
    const att = s.slice(0, 2),
      def = s.slice(2),
      hc = att.filter((v) => v === 6).length,
      hn = att.filter((v) => v >= 4 && v < 6).length,
      sc = def.filter((v) => v === 6).length,
      sn = def.filter((v) => v >= 4 && v < 6).length,
      expect = hc * 1 + bestDamage(hc, hn, sc, sn, [3, 4]);
    assert.equal(r.damage, expect, `dice ${s.join(",")}`);
    total += expect;
    hits += expect > 0 ? 1 : 0;
    kills += expect >= 7 ? 1 : 0;
    count++;
  }
  assert.equal(count, 6 ** 5);
  const mean = total / count,
    sim = A.simulate(p, target, {}, 40000, 3);
  assert.ok(
    Math.abs(sim.mean - mean) < 0.06,
    `mean ${sim.mean} vs exact ${mean}`,
  );
  assert.ok(Math.abs(sim.pDamage - hits / count) < 0.015);
  assert.ok(Math.abs(sim.pIncapacitate - kills / count) < 0.01);
  assert.ok(Math.abs(sim.dist.reduce((a, b) => a + b, 0) - 1) < 1e-9);
});

test("melee resolves without defence dice", () => {
  const p = A.weaponProfile({ type: "melee", atk: 3, hit: "3+", dmg: "4/5" });
  const r = A.resolve(p, { wounds: 9 }, {}, dice([6, 3, 1]));
  assert.equal(r.defence, null);
  assert.equal(r.damage, 9);
  assert.ok(r.incapacitates);
});

test("simulation is deterministic for a seed; the crypto die is fair-looking", () => {
  const p = gun("Lethal 5+, Piercing 1");
  assert.deepEqual(
    A.simulate(p, { save: "3+" }, {}, 2000, 11),
    A.simulate(p, { save: "3+" }, {}, 2000, 11),
  );
  const seen = new Set();
  for (let i = 0; i < 600; i++) {
    const v = A.cryptoD6();
    assert.ok(Number.isInteger(v) && v >= 1 && v <= 6);
    seen.add(v);
  }
  assert.equal(seen.size, 6);
});

/* ---------------------------------------------------------------- QR */
const at = (q, x, y) => q.modules[y][x];
function formatBits(q) {
  const n = q.size,
    a = [],
    b = [];
  for (let i = 0; i <= 5; i++) a.push(at(q, 8, i));
  a.push(at(q, 8, 7), at(q, 8, 8), at(q, 7, 8));
  for (let i = 9; i < 15; i++) a.push(at(q, 14 - i, 8));
  for (let i = 0; i < 8; i++) b.push(at(q, n - 1 - i, 8));
  for (let i = 8; i < 15; i++) b.push(at(q, 8, n - 15 + i));
  const num = (bits) => bits.reduce((v, d, i) => v | ((d ? 1 : 0) << i), 0);
  return [num(a), num(b)];
}
const bchOk = (value, bitsLen, poly, polyDeg) => {
  let v = value;
  for (let i = bitsLen - 1; i >= polyDeg; i--)
    if ((v >>> i) & 1) v ^= poly << (i - polyDeg);
  return v === 0;
};
const GOLDEN = [
  [
    "https://192.168.1.250/#join/ABC234",
    "M",
    3,
    "5c86b315fd110b432e270b392779afc5fba10d71815a6bdf610e68e0ece2a7ec",
  ],
  [
    "KILLSTASS",
    "H",
    2,
    "34545b7cd24783f5d631800926d99f9f2e00a4b02c6803db19e7283621f98aee",
  ],
  [
    "Привет, мир — QR",
    "Q",
    3,
    "81b45cb1399dbc96d8b461e046a5b9c6b2dc5367d9f90fdee52c85eb0f22c1bd",
  ],
  [
    "x".repeat(300),
    "M",
    13,
    "a6c4c99a50e77d18b6ddfdcbd85fffbd3b4da81e4eabc96b030a3f559d2b7fbb",
  ],
];

test("QR symbols: finder and timing patterns, dark module, format and version information", () => {
  for (const [text, level] of GOLDEN) {
    const q = qrMatrix(text, level),
      n = q.size;
    assert.equal(n, 17 + 4 * q.version);
    for (const [cx, cy] of [
      [3, 3],
      [n - 4, 3],
      [3, n - 4],
    ])
      for (let dy = -3; dy <= 3; dy++)
        for (let dx = -3; dx <= 3; dx++) {
          const d = Math.max(Math.abs(dx), Math.abs(dy));
          assert.equal(
            at(q, cx + dx, cy + dy),
            d !== 2,
            `finder at ${cx},${cy}`,
          );
        }
    for (let i = 8; i < n - 8; i++) {
      assert.equal(at(q, i, 6), i % 2 === 0, "horizontal timing");
      assert.equal(at(q, 6, i), i % 2 === 0, "vertical timing");
    }
    assert.ok(at(q, 8, n - 8), "dark module");
    const [f1, f2] = formatBits(q);
    assert.equal(f1, f2, "both format copies agree");
    const f = f1 ^ 0x5412;
    assert.ok(bchOk(f, 15, 0x537, 10), "format BCH");
    assert.equal(
      f >>> 13,
      { L: 1, M: 0, Q: 3, H: 2 }[level],
      "error correction level",
    );
    assert.equal((f >>> 10) & 7, q.mask);
    if (q.version >= 7) {
      let v1 = 0,
        v2 = 0;
      for (let i = 0; i < 18; i++) {
        const a = n - 11 + (i % 3),
          b = Math.floor(i / 3);
        v1 |= (at(q, a, b) ? 1 : 0) << i;
        v2 |= (at(q, b, a) ? 1 : 0) << i;
      }
      assert.equal(v1, v2);
      assert.equal(v1 >>> 12, q.version);
      assert.ok(bchOk(v1, 18, 0x1f25, 12), "version BCH");
    }
  }
});

test("QR output is stable (golden symbols, decoded with OpenCV during development)", () => {
  for (const [text, level, version, sha] of GOLDEN) {
    const q = qrMatrix(text, level),
      h = createHash("sha256")
        .update(
          q.modules.map((r) => r.map((d) => (d ? 1 : 0)).join("")).join("\n"),
        )
        .digest("hex");
    assert.equal(q.version, version, text.slice(0, 20));
    assert.equal(h, sha, `${text.slice(0, 20)} ${level}`);
  }
});

test("QR capacity, masks and SVG", () => {
  let last = 0;
  for (const len of [10, 50, 100, 200, 400, 800]) {
    const v = qrMatrix("a".repeat(len), "Q").version;
    assert.ok(v >= last);
    last = v;
  }
  assert.throws(() => qrMatrix("a".repeat(3000), "H"), /qr_too_long/);
  for (let m = 0; m < 8; m++)
    assert.equal(qrMatrix("mask test", "L", { mask: m }).mask, m);
  const svg = qrSvg("https://x/#join/ABC", { label: 'QR "invite" <link>' });
  const q = qrMatrix("https://x/#join/ABC", "M");
  assert.match(svg, new RegExp(`viewBox="0 0 ${q.size + 8} ${q.size + 8}"`));
  assert.match(svg, /aria-label="QR &quot;invite&quot; &lt;link&gt;"/);
  assert.match(svg, /role="img"/);
  assert.match(svg, /<path fill="#000" d="M\d/);
});

/* v1.12: web/killzones.js imports web/core.js, which looks up a couple of elements when loaded. */
globalThis.document ??= { querySelector: () => null, documentElement: {} };
const K = await import("../../web/killzones.js");
const inside = ([x, y, w, h], px, py) =>
  px >= x && px <= x + w && py >= y && py <= y + h;
/* Every point of an SVG path of absolute M/L/H/V/Z commands. */
function points(d) {
  const out = [];
  let x = 0,
    y = 0;
  for (const [, c, args] of d.matchAll(/([MLHVZ])([^MLHVZ]*)/g)) {
    const n = args.trim() ? args.trim().split(/[ ,]+/).map(Number) : [];
    if (c === "H") x = n[0];
    else if (c === "V") y = n[0];
    else if (c !== "Z") [x, y] = n;
    if (c !== "Z") out.push([x, y]);
  }
  return out;
}

test("killzone layouts: ids, letters, objectives and geometry inside the board", () => {
  const ids = K.LAYOUTS.map((l) => l.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.deepEqual(
    ids.filter((id) => id.startsWith("volkus-2025-")),
    [1, 2, 3, 4, 5, 6].map((n) => `volkus-2025-${n}`),
  );
  for (const l of K.LAYOUTS) {
    assert.deepEqual(
      l.labels.map((x) => x[0]).sort(),
      [..."ABCDEFGHIJKLMN"],
      `${l.id}: every letter of the key once`,
    );
    const pts = [
      ...[l.fill, l.dark, l.walls, l.doors].filter(Boolean).flatMap(points),
      ...l.labels.map(([, x, y]) => [x, y]),
      ...l.obj.map(([x, y]) => [x, y]),
      ...l.dashed.flatMap(([x, y, w, h]) => [
        [x, y],
        [x + w, y + h],
      ]),
    ];
    assert.ok(pts.length > 50, l.id);
    for (const [x, y] of pts)
      assert.ok(
        x >= 0 && x <= 30 && y >= 0 && y <= 22 && !isNaN(x + y),
        `${l.id}: ${x},${y} outside the 30×22 board`,
      );
    assert.deepEqual(l.obj.map((o) => o[2]).sort(), [0, 1, 2]);
    for (const swap of [false, true]) {
      const zs = K.zones(l, swap);
      assert.deepEqual(
        zs.map((z) => z.side),
        [1, 2],
      );
      assert.notEqual(zs[0].edge, zs[1].edge);
      for (const [x, y, s] of l.obj) {
        // objective markers are never in a drop zone; a player's own one is in that player's territory
        assert.ok(!zs.some((z) => inside(z.drop, x, y)), `${l.id}: ${x},${y}`);
        if (s)
          assert.ok(
            inside(zs[(swap ? 3 - s : s) - 1].half, x, y),
            `${l.id}: objective ${s}`,
          );
      }
    }
    assert.equal(K.zones(l, true)[0].edge, K.zones(l)[1].edge, "swap");
    assert.equal(
      K.zones(l)[0].drop[l.s1 === "left" || l.s1 === "right" ? 2 : 3],
      l.depth,
    );
  }
});

test("killzone layouts: SVG layer, select and key", () => {
  assert.equal(K.layoutSvg("nope"), "");
  assert.equal(K.layoutLegend(""), "");
  assert.equal(K.layoutById("volkus-2025-9"), null);
  for (const l of K.LAYOUTS) {
    const svg = K.layoutSvg(l.id);
    assert.match(svg, /^<g class="kz" pointer-events="none"/);
    assert.equal(
      (svg.match(/<g[ >]/g) || []).length,
      (svg.match(/<\/g>/g) || []).length,
    );
    assert.equal((svg.match(/class="kz-obj"/g) || []).length, 3);
    assert.equal((svg.match(/<text /g) || []).length, 14);
    // swapping the drop zones repaints the zones and the players' objectives, not the terrain
    const swapped = K.layoutSvg(l.id, true);
    assert.notEqual(swapped, svg);
    assert.equal(
      swapped.match(/<path d="[^"]*" fill="#66766d"/)[0],
      svg.match(/<path d="[^"]*" fill="#66766d"/)[0],
    );
    assert.match(K.layoutLegend(l.id), /href="#core\/volkus"/);
  }
  const sel = K.layoutSelect("volkus-2025-3");
  assert.match(sel, /<select name="layout" data-layout><option value="">/);
  assert.equal(
    (sel.match(/<option value="volkus-/g) || []).length,
    K.LAYOUTS.length,
  );
  assert.match(sel, /value="volkus-2025-3" selected/);
  assert.equal((sel.match(/ selected/g) || []).length, 1);
  assert.equal((K.layoutSelect("").match(/ selected/g) || []).length, 0);
});

/* v1.14 (Т1): the table of the app's sections (web/sections.js) — every section has exactly one group, a route,
   an icon and both translations; pages opened from a section belong to its group; loose pages have none. */
const S = await import("../../web/sections.js");
const read = async (p) =>
  (await import("node:fs/promises")).readFile(
    new URL(`../../web/${p}`, import.meta.url),
    "utf8",
  );

test("v1.14: menu groups — the table of sections is complete and consistent", async () => {
  const appJs = await read("app.js");
  const block = appJs.slice(appJs.indexOf("const ROUTES = {"));
  const routes = new Set(
    [...block.slice(0, block.indexOf("};")).matchAll(/^\s+(\w+):/gm)].map(
      (m) => m[1],
    ),
  );
  const icons = new Set(
    [...(await read("icons.svg")).matchAll(/<symbol id="([^"]+)"/g)].map(
      (m) => m[1],
    ),
  );
  const ru = JSON.parse(await read("i18n/ru.json"));
  const en = JSON.parse(await read("i18n/en.json"));
  const translated = (k) => {
    assert.ok(ru[k], `ru: ${k}`);
    assert.ok(en[k], `en: ${k}`);
  };
  const ids = S.GROUPS.map((g) => g.id);
  assert.equal(new Set(ids).size, ids.length, "group ids are unique");
  assert.deepEqual(ids, [
    "overview",
    "muster",
    "results",
    "club",
    "rules",
    "profile",
    "admin",
  ]);
  for (const g of S.GROUPS) {
    assert.ok(routes.has(g.id), `route for the group ${g.id}`);
    assert.ok(icons.has(g.icon), `icon ${g.icon} of the group ${g.id}`);
    translated(g.id);
    if (g.hint) translated(g.hint);
  }
  assert.ok(S.groupById("admin").admin, "admin is for administrators only");
  for (const [k, s] of Object.entries(S.SECTIONS)) {
    const owners = S.GROUPS.filter((g) => g.items?.includes(k));
    assert.equal(owners.length, 1, `${k} belongs to exactly one group`);
    assert.ok(routes.has(k), `route for the section ${k}`);
    assert.ok(icons.has(s.icon), `icon ${s.icon} of the section ${k}`);
    translated(S.sectionTitle(k));
    translated(s.hint);
    for (const p of s.pages || []) {
      assert.ok(routes.has(p), `route for the page ${p}`);
      assert.equal(S.sectionOf(p), k);
      assert.equal(S.groupOf(p), owners[0].id);
    }
    assert.equal(S.groupOf(k), owners[0].id);
  }
  for (const g of S.GROUPS)
    for (const k of g.items || [])
      assert.ok(S.SECTIONS[k], `${g.id} lists a known section ${k}`);
  /* the published names of the rules books stay in English under the Russian titles */
  assert.equal(S.SECTIONS.core.en, "Core Rules");
  assert.equal(S.sectionTitle("history"), "history");
  assert.equal(S.groupOf("player"), "club");
  assert.equal(S.groupOf("map"), "muster");
  assert.equal(S.groupOf("muster"), "muster");
  assert.equal(S.groupOf("overview"), "overview");
  assert.equal(S.sectionOf("player"), "friends");
  for (const p of S.LOOSE) {
    assert.equal(S.groupOf(p), null, `${p} is outside the menu`);
    assert.equal(S.sectionOf(p), null);
  }
  assert.equal(S.groupOf("nonsense"), null);
});
