import { app, esc, icon, me, notify, num, t } from "./core.js";
import { currentMatch } from "./app.js";
import { isHotseat } from "./quickstart.js";
import { cachedTeam } from "./teams.js";
import { injured, opsOf, tap, trackerCommand } from "./tracker.js";
import { equipmentWeapons } from "./equipment.js";
import {
  GRENADES,
  RULE_CHIPS,
  cryptoD6,
  parseRules,
  resolve,
  simulate,
  stat,
  toggleRule,
  weaponProfile,
} from "./attackcalc.js";
/* v1.9 — attack calculator on the board (Features → Attack calculator). The attacker's weapon and the
   target come from tracked operatives or the team's datacards, or are typed in; the odds are a Monte
   Carlo estimate (web/attackcalc.js). «Roll» throws real dice (crypto) and, when this phone controls the
   tracked target, the damage can be applied to it. Nothing here is saved on the server by itself.
   v1.13: the weapon rules are toggle chips (the rules the model does not use are shown as they are), and the
   universal grenades can be picked for any attacker or a typed-in profile.
   v1.14: with the player's equipment on record — only the weapons of that equipment. */
const DEFAULTS = {
  attacker: "",
  weapon: "0",
  target: "",
  type: "ranged",
  atk: "4",
  hit: "3+",
  dmg: "3/4",
  wr: "",
  save: "3+",
  wounds: "8",
  cover: false,
  obscured: false,
  injured: false,
};
let S = { ...DEFAULTS, roll: null, matchId: null };
const filled = (o) =>
  Object.fromEntries(
    Object.entries(o || {}).filter(([, v]) => v !== "" && v != null),
  );
/* Both players' operatives: tracked ones (current wounds) or else the team's datacards. */
export function units(m) {
  return m.players.map((p) => {
    const cards = cachedTeam(p.team_id)?.data?.operatives || [],
      base = (o) =>
        cards.find(
          (c) =>
            c.name.toLowerCase() ===
            String(o.card || o.name || "").toLowerCase(),
        ),
      ops = opsOf(m, p.slot);
    const list = ops.length
      ? ops.map((o) => {
          const b = base(o);
          return {
            key: "op:" + o.id,
            name: o.name,
            stats: { ...(b?.stats || {}), ...filled(o.stats) },
            weapons: o.weapons?.length ? o.weapons : b?.weapons || [],
            wounds: o.wounds,
            max: o.wounds_max,
            opId: o.id,
            hurt: injured(o),
            down: o.wounds === 0,
          };
        })
      : cards.map((c, i) => ({
          key: `card:${p.slot}:${i}`,
          name: c.name,
          stats: c.stats || {},
          weapons: c.weapons || [],
          wounds: stat(c.stats?.wounds, 0) || null,
          max: stat(c.stats?.wounds, 0) || null,
        }));
    return { p, list };
  });
}
function find(m, key) {
  if (!key) return null;
  for (const u of units(m)) {
    const x = u.list.find((o) => o.key === key);
    if (x) return { ...x, slot: u.p.slot };
  }
  return null;
}
/* v1.14: the attacker's player with equipment on record gets the weapons of that equipment (Explosive
   Grenades → frag and krak, faction equipment with a profile); without a record — the universal grenades. */
function extraWeapons(m) {
  const a = find(m, S.attacker),
    p = a && m.players.find((x) => x.slot === a.slot);
  if (p && (p.equipment_count || p.equipment?.length))
    return { label: t("equipment"), list: equipmentWeapons(p) };
  return {
    label: t("atkGrenades"),
    list: Object.entries(GRENADES).map(([k, g]) => ({
      ...g,
      name: t("atkGrenade_" + k),
      value: "g:" + k,
    })),
  };
}
function fillWeapon(m) {
  const w = S.weapon.startsWith("g:")
    ? GRENADES[S.weapon.slice(2)]
    : S.weapon.startsWith("e:")
      ? extraWeapons(m).list.find((x) => x.value === S.weapon)
      : find(m, S.attacker)?.weapons?.[+S.weapon];
  if (!w) return;
  Object.assign(S, {
    type: w.type === "melee" ? "melee" : "ranged",
    atk: String(stat(w.atk, 0) || ""),
    hit: w.hit || "",
    dmg: w.dmg || "",
    wr: w.wr || "",
  });
}
function fillAttacker(m) {
  const a = find(m, S.attacker);
  S.weapon = "0";
  S.injured = !!a?.hurt;
  fillWeapon(m);
}
function fillTarget(m) {
  const x = find(m, S.target);
  if (!x) return;
  S.save = x.stats?.save || S.save;
  S.wounds = String(x.wounds ?? (stat(x.stats?.wounds, 0) || S.wounds));
}
const profile = () =>
  weaponProfile({
    type: S.type,
    atk: S.atk,
    hit: S.hit,
    dmg: S.dmg,
    wr: S.wr,
  });
const targetOf = () => ({ save: S.save, wounds: S.wounds });
const modsOf = () => ({
  cover: S.cover && S.type === "ranged",
  obscured: S.obscured && S.type === "ranged",
  injured: S.injured,
});
const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const opt = (v, label, selected) =>
  `<option value="${esc(v)}" ${selected ? "selected" : ""}>${esc(label)}</option>`;
function unitSelect(m, name, label, value) {
  /* Own operatives first for the attacker, the opponent's first for the target (hot-seat: slot order). */
  const mine = (u) => (!isHotseat(m) && !!me && u.p.user_id === me.id ? 1 : 0),
    groups = units(m)
      .filter((u) => u.list.length)
      .sort((x, y) =>
        name === "attacker" ? mine(y) - mine(x) : mine(x) - mine(y),
      );
  return `<label>${t(label)}<select name="${name}">${opt("", t("atkManual"), !value)}${groups
    .map(
      (u) =>
        `<optgroup label="${esc(u.p.display_name)}">${u.list
          .map((o) =>
            opt(
              o.key,
              `${o.name}${o.max ? ` · ${o.wounds ?? o.max}/${o.max}` : ""}${o.down ? " ✝" : ""}`,
              o.key === value,
            ),
          )
          .join("")}</optgroup>`,
    )
    .join("")}</select></label>`;
}
const weaponLabel = (w, name = w.name) =>
  `${w.type === "melee" ? "⚔" : "⌖"} ${name} · A${w.atk} ${w.hit} D${w.dmg}`;
function weaponSelect(m) {
  const ws = find(m, S.attacker)?.weapons || [],
    extra = extraWeapons(m);
  return `<label>${t("atkWeapon")}<select name="weapon">${
    ws.length
      ? ws
          .map((w, i) => opt(String(i), weaponLabel(w), String(i) === S.weapon))
          .join("")
      : opt("", t("atkManual"), !/^[ge]:/.test(S.weapon))
  }${
    extra.list.length
      ? `<optgroup label="${esc(extra.label)}">${extra.list
          .map((g) => opt(g.value, weaponLabel(g), S.weapon === g.value))
          .join("")}</optgroup>`
      : ""
  }</select></label>`;
}
/* The weapon rules: toggle chips for the rules the model uses (a valued one shows its values while it is
   on; the ranged-only ones are disabled for melee) and plain chips for the others. */
function rulesHtml() {
  const r = parseRules(S.wr),
    melee = S.type === "melee",
    chip = (c, v, label, on, off) =>
      `<button type="button" class="chip" data-action="atk-wr" data-rule="${c.k}" ${v == null ? "" : `data-v="${v}"`} aria-pressed="${on}" ${off ? "disabled" : ""}>${esc(label)}</button>`,
    chips = RULE_CHIPS.map((c) => {
      const v = r[c.k],
        off = melee && !!c.ranged,
        name =
          c.k === "devastating" && r.devastatingRange
            ? `${r.devastatingRange}" ${c.name}`
            : c.name,
        vals =
          c.vals && v
            ? `<span class="atk-vals" role="group" aria-label="${esc(name)}">${[
                ...new Set([...c.vals, v]),
              ]
                .sort((a, b) => (c.plus ? b - a : a - b))
                .map((x) => chip(c, x, x + (c.plus ? "+" : ""), x === v, off))
                .join("")}</span>`
            : "";
      return `<span class="atk-chip">${chip(c, null, name, !!v, off)}${vals}</span>`;
    }).join(""),
    other = [
      r.range != null ? `Range ${r.range}"` : "",
      r.brutal ? "Brutal" : "",
      ...r.other,
    ].filter(Boolean);
  return `<fieldset class="atk-wr"><legend>${t("atkRules")}</legend><div class="atk-chips" lang="en">${chips}</div>${
    other.length
      ? `<p class="atk-wr-other" data-terms="wr"><span>${t("atkIgnored")}:</span> ${other.map((x) => `<span class="chip info" lang="en">${esc(x)}</span>`).join(" ")}</p>`
      : ""
  }</fieldset>`;
}
const field = (name, label, attrs = "") =>
  `<label class="atk-field">${t(label)}<input name="${name}" value="${esc(S[name])}" ${attrs}></label>`;
const check = (name, label, disabled = false) =>
  `<label class="check"><input type="checkbox" name="${name}" ${S[name] ? "checked" : ""} ${disabled ? "disabled" : ""}>${t(label)}</label>`;
function formHtml(m) {
  const melee = S.type === "melee";
  return `<form id="attack-form" class="attack-form" novalidate><fieldset><legend>${t("atkAttacker")}</legend>${unitSelect(m, "attacker", "atkOperative", S.attacker)}${weaponSelect(m)}<div class="atk-profile"><label class="atk-field">${t("atkType")}<select name="type">${opt("ranged", t("atkRanged"), !melee)}${opt("melee", t("atkMelee"), melee)}</select></label>${field("atk", "atkDice", 'type="number" min="1" max="20" inputmode="numeric"')}${field("hit", "atkHit", 'maxlength="3" inputmode="numeric"')}${field("dmg", "atkDmg", 'maxlength="7"')}</div>${rulesHtml()}${check("injured", "atkInjured")}</fieldset><fieldset><legend>${t("atkTarget")}</legend>${unitSelect(m, "target", "atkOperative", S.target)}<div class="atk-profile">${field("save", "atkSave", 'maxlength="3" inputmode="numeric"')}${field("wounds", "atkWounds", 'type="number" min="1" max="99" inputmode="numeric"')}</div>${check("cover", "atkCover", melee)}${check("obscured", "atkObscured", melee)}</fieldset></form>`;
}
function distSvg(dist, wounds) {
  let last = dist.length - 1;
  while (last > 0 && dist[last] < 0.002) last--;
  const shown = dist.slice(0, last + 1),
    max = Math.max(...shown, 0.001),
    bw = Math.max(8, Math.min(28, Math.floor(300 / shown.length))),
    w = bw * shown.length,
    label = shown
      .map((p, i) => `${i}: ${pct(p)}`)
      .filter((_, i) => shown[i] >= 0.01)
      .join(", ");
  return `<svg class="atk-dist" viewBox="0 0 ${w} 96" role="img" aria-label="${esc(t("atkDistribution") + " — " + label)}">${shown
    .map((p, i) => {
      const h = Math.round((p / max) * 70);
      return `<rect class="${i >= wounds ? "kill" : ""}" x="${i * bw + 1}" y="${76 - h}" width="${bw - 2}" height="${Math.max(h, p > 0 ? 1 : 0)}"><title>${i}: ${pct(p)}</title></rect>${shown.length <= 16 || i % 2 === 0 ? `<text x="${i * bw + bw / 2}" y="90" text-anchor="middle">${i}</text>` : ""}`;
    })
    .join("")}</svg>`;
}
function resultHtml() {
  const p = profile();
  if (!p.atk) return `<p class="muted">${t("atkNeedProfile")}</p>`;
  const wounds = stat(S.wounds, 0) || Infinity,
    r = simulate(p, targetOf(), modsOf(), 20000, 7);
  return `<dl class="atk-stats"><div><dt>${t("atkMean")}</dt><dd>${num(r.mean.toFixed(2))}</dd></div><div><dt>${t("atkAny")}</dt><dd>${pct(r.pDamage)}</dd></div><div><dt>${t("atkKill")}</dt><dd>${Number.isFinite(wounds) ? pct(r.pIncapacitate) : "—"}</dd></div><div><dt>${t("atkHits")}</dt><dd>${num(r.avgCrits.toFixed(1))} / ${num(r.avgNormals.toFixed(1))}</dd></div>${p.type === "ranged" ? `<div><dt>${t("atkSaves")}</dt><dd>${num(r.avgSaves.toFixed(1))}</dd></div>` : ""}</dl>${distSvg(r.dist, wounds)}<p class="muted small">${t(p.type === "melee" ? "atkMeleeNote" : "atkNote")}</p>`;
}
const canEditSlot = (m, slot) => {
  const p = m.players.find((x) => x.slot === slot);
  return (
    m.status === "active" &&
    !!p &&
    (isHotseat(m) || (!!me && p.user_id === me.id))
  );
};
function dieHtml(d) {
  return `<span class="die ${d.kind}" ${d.first ? `title="${esc(t("atkRerolled"))}: ${d.first}"` : ""}>${d.first ? `<s>${d.first}</s>` : ""}${d.v}</span>`;
}
function rollHtml(m) {
  const r = S.roll;
  if (!r) return "";
  const a = r.attack,
    x = find(m, S.target),
    apply =
      !r.applied && r.damage > 0 && x?.opId && !x.down && canEditSlot(m, x.slot)
        ? `<button type="button" data-action="attack-apply" data-op="${x.opId}" data-dmg="${Math.min(r.damage, x.wounds)}">${icon("heart")}<span>${esc(t("atkApply").replace("{n}", Math.min(r.damage, x.wounds)).replace("{name}", x.name))}</span></button>`
        : "";
  const notes = [
    a.accurate ? `${t("atkAccurate")} ×${a.accurate}` : "",
    a.severe ? "Severe" : "",
    a.punishing ? "Punishing" : "",
    a.rending ? "Rending" : "",
    a.obscured ? t("atkObscured") + (a.discarded ? " −1" : "") : "",
    r.devastating ? `Devastating +${r.devastating}` : "",
  ].filter(Boolean);
  return `<div class="atk-roll" aria-live="polite"><p><b>${t("atkAttackDice")}</b> <span class="dice-row">${Array.from({ length: a.accurate }, () => '<span class="die normal acc">✓</span>').join("")}${a.dice.map(dieHtml).join("")}</span> → ${a.crits} ${t("atkCrit")} · ${a.normals} ${t("atkNormal")}</p>${
    r.defence
      ? `<p><b>${t("atkDefenceDice")}</b> <span class="dice-row">${Array.from({ length: r.defence.cover }, () => `<span class="die normal acc" title="${esc(t("atkCover"))}">▣</span>`).join("")}${r.defence.dice.map(dieHtml).join("")}</span> → ${r.defence.crits} ${t("atkCrit")} · ${r.defence.normals} ${t("atkNormal")}${r.defence.pierce ? ` · Piercing ${r.defence.pierce}` : ""}</p>`
      : ""
  }${notes.length ? `<p class="muted small">${esc(notes.join(" · "))}</p>` : ""}<p class="atk-damage"><b>${t("atkDamage")}: ${r.damage}</b>${r.incapacitates ? ` · <span class="badge down">${icon("skull")}${t("opDown")}</span>` : ""}</p>${apply}${r.applied ? `<p class="muted">${t("atkApplied")}</p>` : ""}</div>`;
}
export function attackPanel(m) {
  if (S.matchId !== m.id) S = { ...DEFAULTS, roll: null, matchId: m.id };
  return `<h2>${icon("target")} ${t("attackCalc")}</h2><p class="muted">${t("atkHint")}</p><div id="attack-panel">${formHtml(m)}</div><div id="attack-result" aria-live="polite">${resultHtml()}</div><div class="row"><button type="button" data-action="attack-roll">${icon("dice")}<span>${t("atkRoll")}</span></button></div><div id="attack-roll-out">${rollHtml(m)}</div>`;
}
function redrawForm(m, focusName) {
  const host = document.querySelector("#attack-panel");
  if (!host) return;
  host.innerHTML = formHtml(m);
  if (focusName) host.querySelector(`[name="${focusName}"]`)?.focus();
}
function redrawRules(rule, v) {
  const host = document.querySelector("#attack-form .atk-wr");
  if (!host) return;
  host.outerHTML = rulesHtml();
  document
    .querySelector(
      `#attack-form .atk-wr [data-rule="${rule}"]${v ? `[data-v="${v}"]` : ":not([data-v])"}`,
    )
    ?.focus();
}
function redrawResult(m) {
  const res = document.querySelector("#attack-result"),
    out = document.querySelector("#attack-roll-out");
  if (res) res.innerHTML = resultHtml();
  if (out) out.innerHTML = rollHtml(m);
}
let timer = null;
export function init() {
  app.addEventListener("input", (e) => {
    const f = e.target.closest("#attack-form");
    if (
      !f ||
      !currentMatch ||
      e.target.tagName !== "INPUT" ||
      e.target.type === "checkbox"
    )
      return;
    S[e.target.name] = e.target.value;
    S.roll = null;
    clearTimeout(timer);
    timer = setTimeout(() => redrawResult(currentMatch), 150);
  });
  app.addEventListener("change", (e) => {
    const f = e.target.closest("#attack-form");
    if (!f || !currentMatch) return;
    const m = currentMatch,
      n = e.target.name;
    if (e.target.type === "checkbox") S[n] = e.target.checked;
    else S[n] = e.target.value;
    if (["attacker", "weapon", "target", "type"].includes(n)) {
      if (n === "attacker") fillAttacker(m);
      else if (n === "weapon") fillWeapon(m);
      else if (n === "target") fillTarget(m);
      S.roll = null;
      redrawForm(m, n);
    }
    redrawResult(m);
  });
  app.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b || !currentMatch || b.disabled) return;
    const m = currentMatch;
    if (b.dataset.action === "atk-wr") {
      S.wr = toggleRule(S.wr, b.dataset.rule, b.dataset.v ?? null);
      S.roll = null;
      redrawRules(b.dataset.rule, b.dataset.v);
      redrawResult(m);
    } else if (b.dataset.action === "attack-roll") {
      const p = profile();
      if (!p.atk) return notify(t("atkNeedProfile"));
      tap();
      S.roll = resolve(p, targetOf(), modsOf(), cryptoD6);
      redrawResult(m);
    } else if (b.dataset.action === "attack-apply") {
      b.disabled = true;
      try {
        S.roll.applied = true;
        await trackerCommand({
          action: "wounds",
          operative_id: +b.dataset.op,
          delta: -+b.dataset.dmg,
        });
        fillTarget(currentMatch);
        redrawForm(currentMatch);
        redrawResult(currentMatch);
      } catch (err) {
        S.roll.applied = false;
        notify(err.message);
      } finally {
        b.disabled = false;
      }
    }
  });
}
