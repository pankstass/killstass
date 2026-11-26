import { api, esc, icon, notify, t } from "./core.js";
import { cachedTeam, datacard, ruleText } from "./teams.js";
import { teamEmblem } from "./emblem.js";
/* v1.9 — datacards of tracked/roster operatives, the players' rosters on the board and print views.
   Printing renders into #print-root; print CSS shows only that element while body.printing is set. */
const filled = (o) =>
  Object.fromEntries(
    Object.entries(o || {}).filter(([, v]) => v !== "" && v != null),
  );
/* v1.14 (Т2): roster operatives carry the rules of their selected options (api/tracker.py roster_build);
   only tracker rows without them (added from a datacard) fall back to the whole datacard. */
export function opCard(o, teamId) {
  const team = cachedTeam(teamId),
    key = (o.card || o.name || "").toLowerCase(),
    base = team?.data?.operatives?.find((c) => c.name.toLowerCase() === key),
    own = (k) => (Array.isArray(o[k]) ? o[k] : base?.[k] || []);
  return datacard({
    ...(base || {}),
    name: o.name,
    stats: { ...(base?.stats || {}), ...filled(o.stats) },
    weapons: o.weapons?.length ? o.weapons : base?.weapons || [],
    abilities: own("abilities"),
    actions: own("actions"),
    keywords: o.keywords?.length ? o.keywords : base?.keywords || [],
  });
}
export function rosterSheet(r, teamId) {
  if (!r.operatives?.length && !r.roster_text)
    return `<p class="empty">${t("rosterSheetEmpty")}</p>`;
  const extras = r.extras?.length
    ? `<div class="sheet-extras-rules">${r.extras.map((x) => `<div class="dc-rule" data-terms="text"><h4>${esc(x.name)}${x.type && x.type !== "Equipment" ? ` <small class="dc-type">${esc(x.type)}</small>` : ""}</h4>${ruleText(x.text)}</div>`).join("")}</div>`
    : "";
  return `<div class="roster-sheet">${r.operatives?.length ? `<div class="datacards">${r.operatives.map((o) => opCard(o, teamId ?? r.team_id)).join("")}</div>` : ""}${r.other?.length ? `<h4>${t("rosterExtras")}</h4>${extras || `<ul class="sheet-extras">${r.other.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`}` : ""}${!r.operatives?.length && r.roster_text ? `<p class="pre">${esc(r.roster_text)}</p>` : ""}</div>`;
}
export function printHtml(title, html) {
  let root = document.querySelector("#print-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "print-root";
    document.body.append(root);
  }
  root.innerHTML = `<header class="print-head"><b>KILLSTASS</b><h1>${esc(title)}</h1><small>${esc(new Date().toLocaleDateString())}</small></header>${html}`;
  document.body.classList.add("printing");
  const done = () => {
    document.body.classList.remove("printing");
    window.removeEventListener("afterprint", done);
  };
  window.addEventListener("afterprint", done);
  try {
    window.print();
  } catch {
    done();
  }
}
/* Board panel «Rosters»: both players' rosters as played (the opponent's opens after the start). */
const rosterCache = {};
export async function loadMatchRoster(m, slot) {
  const key = m.id + ":" + slot + ":" + m.status;
  if (!rosterCache[key])
    rosterCache[key] = api(`/matches/${m.id}/players/${slot}/roster`).catch(
      (e) => ({ error: e.message }),
    );
  return rosterCache[key];
}
export function rostersPanel(m, data) {
  return `<h2>${t("rostersPanel")}</h2><div class="roster-panels">${m.players
    .map((p) => {
      const r = data?.[p.slot];
      return `<section class="roster-panel slot-${p.slot}"><header class="row between"><h3>${teamEmblem(p.team_id, p.display_name)}<span>${esc(p.display_name)}</span>${r?.roster_name ? `<small class="muted">${esc(r.roster_name)}</small>` : ""}</h3>${r && !r.error && r.operatives?.length ? `<button type="button" class="secondary small" data-action="print-roster" data-slot="${p.slot}">${icon("print")}<span>${t("print")}</span></button>` : ""}</header>${
        !r
          ? `<p class="muted">${t("loading")}</p>`
          : r.error
            ? `<p class="muted">${esc(r.error)}</p>`
            : rosterSheet(r, p.team_id)
      }</section>`;
    })
    .join("")}</div>`;
}
export async function printMatchRoster(m, slot) {
  try {
    const r = await loadMatchRoster(m, slot),
      p = m.players.find((x) => x.slot === slot);
    if (r.error) throw new Error(r.error);
    printHtml(
      `${p.display_name}${r.roster_name ? " — " + r.roster_name : ""}${r.team_name ? " (" + r.team_name + ")" : ""}`,
      rosterSheet(r, p.team_id),
    );
  } catch (e) {
    notify(e.message);
  }
}
export async function printRoster(id) {
  try {
    const r = await api("/rosters/" + encodeURIComponent(id) + "/sheet");
    printHtml(
      `${r.roster_name}${r.team_name ? " — " + r.team_name : ""}`,
      rosterSheet(r, r.team_id),
    );
  } catch (e) {
    notify(e.message);
  }
}
export const printButton = (action, attrs = "") =>
  `<button type="button" class="secondary" data-action="${action}" ${attrs}>${icon("print")}<span>${esc(t("print"))}</span></button>`;
