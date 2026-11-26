/* v1.9 — Kill Team (2024) shooting resolution as pure functions: no DOM, so node:test covers them.
   One attack: attack dice (Accurate, re-rolls, Lethal, Severe/Rending/Punishing, Obscured) → defence dice
   (3 dice, Piercing / Piercing Crits, cover save unless Saturate) → the defender's best allocation of saves
   → damage (+ Devastating for every retained critical success). Melee weapons: successes and damage
   without parries (the fight is interactive). Choices are made the way a careful player would:
   re-roll fails, Ceaseless on the most frequent failed value, Punishing before Rending. */
export const DEFENCE_DICE = 3;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export const stat = (v, fallback = 0) => {
  const m = String(v ?? "").match(/\d+/);
  return m ? +m[0] : fallback;
};
export function parseDamage(v) {
  const m = String(v ?? "").match(/(\d+)\s*\/\s*(\d+)/);
  if (m) return [+m[1], +m[2]];
  const n = stat(v, 0);
  return [n, n];
}
const FLAGS = [
  "balanced",
  "ceaseless",
  "relentless",
  "rending",
  "punishing",
  "severe",
  "saturate",
  "brutal",
];
export function parseRules(wr) {
  const r = {
    range: null,
    lethal: null,
    accurate: 0,
    piercing: 0,
    piercingCrits: 0,
    devastating: 0,
    devastatingRange: null,
    other: [],
  };
  for (const f of FLAGS) r[f] = false;
  for (const raw of String(wr ?? "").split(/[,;]/)) {
    const s = raw.trim().replace(/\s+/g, " ");
    if (!s) continue;
    let m;
    if ((m = s.match(/^range (\d+)/i))) r.range = +m[1];
    else if ((m = s.match(/^lethal (\d)\+?$/i))) r.lethal = clamp(+m[1], 2, 6);
    else if ((m = s.match(/^accurate (\d+)$/i))) r.accurate = +m[1];
    else if ((m = s.match(/^piercing crits? (\d+)$/i))) r.piercingCrits = +m[1];
    else if ((m = s.match(/^piercing (\d+)$/i))) r.piercing = +m[1];
    else if (
      (m = s.match(
        /^(?:(\d+) ?(?:"|”|″|''|in(?:ch(?:es)?)?\.?) ?)?devastating (\d+)$/i,
      ))
    ) {
      r.devastating = +m[2];
      r.devastatingRange = m[1] ? +m[1] : null;
    } else if (FLAGS.includes(s.toLowerCase())) r[s.toLowerCase()] = true;
    else r.other.push(s);
  }
  return r;
}
/* v1.13 — the weapon rules the model uses, as toggle chips on the calculator: a flag or a value to pick
   (the first value is the default; `ranged`: no effect on the melee estimate). */
export const RULE_CHIPS = [
  { k: "accurate", name: "Accurate", vals: [1, 2] },
  { k: "balanced", name: "Balanced" },
  { k: "ceaseless", name: "Ceaseless" },
  { k: "relentless", name: "Relentless" },
  { k: "lethal", name: "Lethal", vals: [5, 4, 3], plus: true },
  { k: "rending", name: "Rending" },
  { k: "punishing", name: "Punishing" },
  { k: "severe", name: "Severe" },
  { k: "devastating", name: "Devastating", vals: [1, 2, 3, 4], ranged: true },
  { k: "piercing", name: "Piercing", vals: [1, 2], ranged: true },
  { k: "piercingCrits", name: "Piercing Crits", vals: [1, 2], ranged: true },
  { k: "saturate", name: "Saturate", ranged: true },
];
/* The inverse of parseRules: parseRules(formatRules(r)) equals r; the rules the model does not use
   (r.other) are kept as they were. */
export function formatRules(r = {}) {
  const out = [];
  if (r.range != null) out.push(`Range ${r.range}"`);
  if (r.accurate) out.push(`Accurate ${r.accurate}`);
  if (r.balanced) out.push("Balanced");
  if (r.brutal) out.push("Brutal");
  if (r.ceaseless) out.push("Ceaseless");
  if (r.devastating)
    out.push(
      `${r.devastatingRange ? `${r.devastatingRange}" ` : ""}Devastating ${r.devastating}`,
    );
  if (r.lethal) out.push(`Lethal ${r.lethal}+`);
  if (r.piercing) out.push(`Piercing ${r.piercing}`);
  if (r.piercingCrits) out.push(`Piercing Crits ${r.piercingCrits}`);
  if (r.punishing) out.push("Punishing");
  if (r.relentless) out.push("Relentless");
  if (r.rending) out.push("Rending");
  if (r.saturate) out.push("Saturate");
  if (r.severe) out.push("Severe");
  return [...out, ...(r.other || [])].join(", ");
}
/* Switch one rule of a weapon-rules string: a flag on/off, a valued rule on (its first value) or off,
   or — with `value` — set to that value. */
export function toggleRule(wr, key, value = null) {
  const r = parseRules(wr),
    chip = RULE_CHIPS.find((c) => c.k === key);
  if (!chip) return formatRules(r);
  if (value != null && chip.vals) r[key] = +value;
  else if (r[key]) r[key] = parseRules("")[key];
  else r[key] = chip.vals ? chip.vals[0] : true;
  if (key === "devastating" && !r.devastating) r.devastatingRange = null;
  return formatRules(r);
}
/* Universal grenades (Kill Team universal equipment, official profiles of 28.10.2026). */
export const GRENADES = {
  frag: {
    name: "Frag grenade",
    type: "ranged",
    atk: "4",
    hit: "4+",
    dmg: "2/4",
    wr: 'Range 6", Blast 2", Saturate',
  },
  krak: {
    name: "Krak grenade",
    type: "ranged",
    atk: "4",
    hit: "4+",
    dmg: "4/5",
    wr: 'Range 6", Piercing 1, Saturate',
  },
};
/* A datacard weapon {name,type,atk,hit,dmg,wr} → numbers the calculator uses. */
export function weaponProfile(w = {}) {
  return {
    name: w.name || "",
    type: w.type === "melee" ? "melee" : "ranged",
    atk: clamp(stat(w.atk, 0), 0, 20),
    hit: clamp(stat(w.hit, 6), 2, 6),
    dmg: parseDamage(w.dmg),
    rules: parseRules(w.wr),
  };
}
/* Deterministic PRNG for Monte Carlo (mulberry32) and a d6 from any [0,1) source. */
export function seeded(seed = 1) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export const d6From = (random) => () => 1 + Math.floor(random() * 6);
export function cryptoD6() {
  const buf = new Uint8Array(1);
  for (;;) {
    crypto.getRandomValues(buf);
    if (buf[0] < 252) return 1 + (buf[0] % 6); // no modulo bias
  }
}

/* Attack dice of one weapon; `roll` returns 1..6. */
export function rollAttack(p, mods = {}, roll = cryptoD6) {
  const R = p.rules,
    hit = clamp(p.hit + (mods.injured ? 1 : 0), 2, 6),
    critOn = R.lethal ? Math.min(R.lethal, 6) : 6,
    kind = (v) =>
      v === 1 || v < hit ? "fail" : v >= critOn ? "crit" : "normal",
    accurate = Math.min(R.accurate || 0, p.atk),
    dice = Array.from({ length: p.atk - accurate }, () => ({
      v: roll(),
      first: null,
    }));
  const reroll = (d) => {
    d.first = d.v;
    d.v = roll();
  };
  if (R.relentless) dice.filter((d) => kind(d.v) === "fail").forEach(reroll);
  else {
    if (R.ceaseless) {
      const counts = {};
      for (const d of dice)
        if (kind(d.v) === "fail") counts[d.v] = (counts[d.v] || 0) + 1;
      const best = Object.entries(counts).sort(
        (a, b) => b[1] - a[1] || a[0] - b[0],
      )[0];
      if (best) dice.filter((d) => d.v === +best[0]).forEach(reroll);
    }
    if (R.balanced) {
      const d = dice.find((x) => x.first === null && kind(x.v) === "fail");
      if (d) reroll(d);
    }
  }
  let crits = 0,
    normals = accurate,
    fails = 0;
  for (const d of dice) {
    d.kind = kind(d.v);
    if (d.kind === "crit") crits++;
    else if (d.kind === "normal") normals++;
    else fails++;
  }
  const out = {
    hit,
    critOn,
    accurate,
    dice,
    severe: false,
    rending: false,
    punishing: false,
    obscured: false,
    discarded: 0,
  };
  if (mods.obscured && p.type === "ranged") {
    // Obscured: critical successes are retained as normal successes and can't become critical; discard one success.
    normals += crits;
    crits = 0;
    out.obscured = true;
    if (normals) {
      normals--;
      out.discarded = 1;
    }
  } else if (R.severe && !crits && normals) {
    normals--;
    crits++;
    out.severe = true;
  } else if (crits) {
    if (R.punishing && fails) {
      fails--;
      normals++;
      out.punishing = true;
    }
    if (R.rending && normals) {
      normals--;
      crits++;
      out.rending = true;
    }
  }
  return Object.assign(out, { crits, normals, fails });
}

export function rollDefence(
  p,
  attack,
  target = {},
  mods = {},
  roll = cryptoD6,
) {
  const R = p.rules,
    pierce = Math.max(R.piercing || 0, attack.crits ? R.piercingCrits || 0 : 0),
    count = Math.max(0, DEFENCE_DICE - pierce),
    cover = mods.cover && !R.saturate && count > 0 ? 1 : 0,
    save = clamp(stat(target.save, 6), 2, 6),
    dice = Array.from({ length: count - cover }, () => {
      const v = roll();
      return {
        v,
        kind: v === 6 ? "crit" : v !== 1 && v >= save ? "normal" : "fail",
      };
    });
  return {
    pierce,
    count,
    cover,
    save,
    dice,
    crits: dice.filter((d) => d.kind === "crit").length,
    normals: cover + dice.filter((d) => d.kind === "normal").length,
  };
}

/* The defender allocates saves to minimise damage: a critical save blocks any success,
   two normal saves block a critical success, one normal save blocks a normal success. */
export function allocate(hits, saves, dmg) {
  const [dn, dc] = dmg;
  let best = { damage: Infinity };
  for (let a = 0; a <= Math.min(saves.crits, hits.crits); a++)
    for (
      let b = 0;
      b <= Math.min(Math.floor(saves.normals / 2), hits.crits - a);
      b++
    ) {
      const critsLeft = hits.crits - a - b,
        blockN = Math.min(
          hits.normals,
          saves.crits - a + saves.normals - 2 * b,
        ),
        damage = critsLeft * dc + (hits.normals - blockN) * dn;
      if (damage < best.damage)
        best = {
          damage,
          critsBlocked: a + b,
          normalsBlocked: blockN,
          critsThrough: critsLeft,
          normalsThrough: hits.normals - blockN,
        };
    }
  return best;
}

/* One full attack. Returns every intermediate step for the «actual roll» view. */
export function resolve(p, target = {}, mods = {}, roll = cryptoD6) {
  const attack = rollAttack(p, mods, roll),
    devastating = attack.crits * (p.rules.devastating || 0);
  if (p.type === "melee") {
    const damage = attack.crits * p.dmg[1] + attack.normals * p.dmg[0];
    return {
      attack,
      defence: null,
      allocation: null,
      devastating: 0,
      damage,
      incapacitates: damage >= stat(target.wounds, Infinity),
    };
  }
  const defence = rollDefence(p, attack, target, mods, roll),
    allocation = allocate(attack, defence, p.dmg),
    damage = devastating + allocation.damage;
  return {
    attack,
    defence,
    allocation,
    devastating,
    damage,
    incapacitates: damage >= stat(target.wounds, Infinity),
  };
}

/* Monte Carlo summary of n attacks. */
export function simulate(p, target = {}, mods = {}, n = 20000, seed = 1) {
  const roll = d6From(seeded(seed)),
    wounds = stat(target.wounds, Infinity),
    hist = [];
  let sum = 0,
    kills = 0,
    any = 0,
    crits = 0,
    normals = 0,
    saves = 0;
  for (let i = 0; i < n; i++) {
    const r = resolve(p, target, mods, roll);
    sum += r.damage;
    hist[r.damage] = (hist[r.damage] || 0) + 1;
    if (r.damage >= wounds) kills++;
    if (r.damage > 0) any++;
    crits += r.attack.crits;
    normals += r.attack.normals;
    if (r.defence) saves += r.defence.crits + r.defence.normals;
  }
  const dist = Array.from(hist, (c) => (c || 0) / n);
  return {
    n,
    mean: sum / n,
    pIncapacitate: Number.isFinite(wounds) ? kills / n : null,
    pDamage: any / n,
    avgCrits: crits / n,
    avgNormals: normals / n,
    avgSaves: saves / n,
    dist,
  };
}
