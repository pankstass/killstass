import { api, app, esc, icon, me, notify, t, uuid } from "./core.js";
import { currentMatch, drawMatch, setCurrentMatch } from "./app.js";
import { apBadge, apSplit, ruleText } from "./teams.js";
import { isHotseat } from "./quickstart.js";
/* v1.14 — equipment (Game Sequence, step 2). Each player secretly selects up to four options before the
   battle (universal or of their faction, each once); the server reveals them when the match starts and gives
   each player 2CP. Setup: the options of the player's team (GET /equipment) with their rules; the board: the
   revealed equipment as chips with the text; the attack calculator offers the weapons of the equipment. */
export const EQUIP_MAX = 4;
const loaded = new Map(); // `${match}:${slot}` → the GET /equipment answer
const opened = new Set(); // texts shown: board chips `${match}:${slot}:${key}`, setup options by element id
export const equipmentOn = (m) =>
  m.edition === "2024" && m.kind !== "guest" && !m.demo;
function ownSlots(m) {
  if (isHotseat(m)) return [1, 2];
  const own = m.players.find((p) => p.user_id === me?.id);
  return own ? [own.slot] : [];
}
/* The rules of one option: unique actions with the AP badge, other profiles under their name when it says
   more than the option's name (e.g. «2x Light Barricades»), weapon profiles in one line each. */
export function itemText(item) {
  const plain = (n) =>
    n.toLowerCase().replace(/^1x\s+/, "") === item.name.toLowerCase();
  return `${(item.rules || [])
    .map((r) => {
      const [name, ap] = r.type === "action" ? apSplit(r.name) : [r.name, ""];
      return `${r.name && !plain(r.name) ? `<h4>${r.type === "action" ? icon("bolt") : ""}${esc(name)}${apBadge(ap)}</h4>` : ""}${ruleText(r.text)}`;
    })
    .join("")}${(item.weapons || [])
    .map(
      (w) =>
        `<p class="equip-weapon">${w.type === "melee" ? "⚔" : "⌖"} <b>${esc(w.name)}</b> · A${esc(w.atk)} ${esc(w.hit)} D${esc(w.dmg)}${w.wr ? ` · <span data-terms="wr">${esc(w.wr)}</span>` : ""}</p>`,
    )
    .join("")}`;
}
function option(item, checked, full, slot) {
  const id = `eq-${slot}-${item.key.replace(/[^a-z0-9-]/gi, "-")}`,
    open = opened.has(id);
  return `<div class="equip-opt"><label><input type="checkbox" name="equipment" value="${esc(item.key)}" ${checked ? "checked" : ""} ${!checked && full ? "disabled" : ""}><span>${esc(item.name)}</span>${item.weapons?.length ? `<small class="muted">${item.weapons.map((w) => esc(w.name)).join(", ")}</small>` : ""}</label><button type="button" class="text equip-more" data-action="equip-more" aria-expanded="${open}" aria-controls="${id}" aria-label="${esc(t("equipRules") + ": " + item.name)}">${t("equipRules")}</button><div class="equip-text" id="${id}" data-terms="text" ${open ? "" : "hidden"}>${itemText(item)}</div></div>`;
}
const countText = (n) =>
  t("equipCount").replace("{n}", n).replace("{max}", EQUIP_MAX);
function formHtml(m, p) {
  if (!p.team_id) return `<p class="muted">${t("equipTeamFirst")}</p>`;
  const d = loaded.get(m.id + ":" + p.slot);
  if (!d || d.team_id !== p.team_id) {
    queueMicrotask(() => load(m, p.slot));
    return `<p class="muted" role="status">${t("loading")}</p>`;
  }
  if (!d.options.length) return `<p class="muted">${t("equipNone")}</p>`;
  const chosen = new Set(d.selected),
    full = chosen.size >= EQUIP_MAX,
    group = (g, title) => {
      const items = d.options.filter((o) => o.group === g);
      return items.length
        ? `<fieldset class="equip-group"><legend>${t(title)}</legend>${items.map((o) => option(o, chosen.has(o.key), full, p.slot)).join("")}</fieldset>`
        : "";
    },
    suggest =
      !d.selected.length && d.suggested.length
        ? `<button type="button" class="secondary" data-action="equip-suggest" data-slot="${p.slot}">${icon("list")}<span>${esc(t("equipFromRoster").replace("{n}", d.suggested.length))}</span></button>`
        : "";
  return `<form class="equip-form" id="equip-form-${p.slot}" data-slot="${p.slot}"><p class="muted">${t("equipHint")}</p>${group("universal", "equipUniversal")}${group("faction", "equipFaction")}<p class="equip-count" aria-live="polite">${countText(chosen.size)}</p><div class="row"><button>${t("equipSave")}</button>${suggest}</div></form>`;
}
async function load(m, slot) {
  const key = m.id + ":" + slot;
  try {
    const d = await api(`/matches/${m.id}/equipment?slot=${slot}`);
    loaded.set(key, d);
  } catch (err) {
    notify(err.message);
    return;
  }
  const box = document.getElementById("equip-" + slot),
    p =
      currentMatch?.id === m.id &&
      currentMatch.players.find((x) => x.slot === slot);
  if (box && p) box.innerHTML = formHtml(currentMatch, p);
}
/* Setup page: the own selection (a hot-seat guest's behind «pass the device»), the opponent's progress only. */
export function equipmentSetup(m) {
  if (m.status !== "setup" || !equipmentOn(m)) return "";
  const slots = ownSlots(m),
    others = m.players.filter((p) => !slots.includes(p.slot));
  return slots
    .map((slot) => {
      const p = m.players.find((x) => x.slot === slot),
        body = `<div class="equip-setup" id="equip-${slot}">${formHtml(m, p)}</div>`,
        state = `<p class="equip-state">${p.equipment_count ? `✓ ${esc(countText(p.equipment_count))}` : esc(t("equipNotChosen"))}</p>`;
      return slot === 2 && isHotseat(m)
        ? `<section class="panel equip-panel"><h2>${t("equipment")}: ${esc(p.display_name)}</h2><p class="warning">${t("passDevice")} ${esc(p.display_name)}.</p>${state}<details><summary>${t("equipOpenGuest")}</summary>${body}</details></section>`
        : `<section class="panel equip-panel"><h2>${t("equipment")}${isHotseat(m) ? ": " + esc(p.display_name) : ""}</h2>${body}${others.map((o) => `<p class="muted">${esc(o.display_name)}: ${o.equipment_count ? esc(countText(o.equipment_count)) : esc(t("equipNotChosen"))}</p>`).join("")}</section>`;
    })
    .join("");
}
/* Board: the revealed equipment of a player as chips; a chip shows the option's text below the chips. */
export function equipmentBox(m, p) {
  const items = p.equipment || [];
  if (!items.length || m.status === "setup") return "";
  const id = (i) => `eqb-${p.slot}-${i}`,
    key = (x) => `${m.id}:${p.slot}:${x.key}`;
  return `<div class="box equip-box"><span class="box-label">${t("equipment")}</span><div class="rchips">${items
    .map(
      (x, i) =>
        `<button type="button" class="rchip" data-action="equip-chip" data-key="${esc(key(x))}" aria-expanded="${opened.has(key(x))}" aria-controls="${id(i)}">${icon(x.weapons?.length ? "target" : "pack")}<span>${esc(x.name)}</span></button>`,
    )
    .join("")}</div>${items
    .map(
      (x, i) =>
        `<div class="rrule equip-rule" id="${id(i)}" ${opened.has(key(x)) ? "" : "hidden"}><h4>${esc(x.name)} <small class="dc-type">${t(x.group === "faction" ? "equipFactionShort" : "equipUniversalShort")}</small></h4><div data-terms="text">${itemText(x)}</div></div>`,
    )
    .join("")}</div>`;
}
/* Weapons the attack calculator offers for a player's operatives (grenades and the like). */
export const equipmentWeapons = (p) =>
  (p?.equipment || []).flatMap((x, i) =>
    (x.weapons || []).map((w, j) => ({
      ...w,
      value: `e:${i}:${j}`,
      from: x.name,
    })),
  );

function refreshCount(f) {
  const boxes = [...f.querySelectorAll("input[name=equipment]")],
    n = boxes.filter((x) => x.checked).length;
  for (const x of boxes) x.disabled = !x.checked && n >= EQUIP_MAX;
  const out = f.querySelector(".equip-count");
  if (out) out.textContent = countText(n);
}
export function init() {
  app.addEventListener("change", (e) => {
    const f = e.target.closest(".equip-form");
    if (f && e.target.name === "equipment") refreshCount(f);
  });
  app.addEventListener("submit", async (e) => {
    const f = e.target;
    if (!f.classList.contains("equip-form") || !currentMatch) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const b = f.querySelector("button:not([type])"),
      slot = +f.dataset.slot,
      keys = [...f.querySelectorAll("input[name=equipment]:checked")].map(
        (x) => x.value,
      );
    if (b) b.disabled = true;
    try {
      await api(`/matches/${currentMatch.id}/equipment`, "PUT", {
        request_id: uuid(),
        version: currentMatch.version,
        slot,
        keys,
      });
      loaded.delete(currentMatch.id + ":" + slot);
      setCurrentMatch(await api("/matches/" + currentMatch.id));
      drawMatch(currentMatch);
      notify(t("equipSaved"));
    } catch (err) {
      notify(err.message);
    } finally {
      if (b) b.disabled = false;
    }
  });
  app.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b || !currentMatch) return;
    if (
      b.dataset.action === "equip-chip" ||
      b.dataset.action === "equip-more"
    ) {
      const k = b.dataset.key || b.getAttribute("aria-controls"),
        panel = document.getElementById(b.getAttribute("aria-controls"));
      if (opened.has(k)) opened.delete(k);
      else opened.add(k);
      b.setAttribute("aria-expanded", String(opened.has(k)));
      if (panel) panel.hidden = !opened.has(k);
    } else if (b.dataset.action === "equip-suggest") {
      const d = loaded.get(currentMatch.id + ":" + b.dataset.slot),
        f = b.closest("form");
      if (!d || !f) return;
      for (const x of f.querySelectorAll("input[name=equipment]"))
        x.checked = d.suggested.includes(x.value);
      refreshCount(f);
      f.querySelector("input[name=equipment]:checked")?.focus();
    }
  });
}
