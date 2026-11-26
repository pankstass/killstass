import {
  api,
  app,
  BASE,
  catName,
  catalogs,
  date,
  esc,
  icon,
  locale,
  t,
} from "./core.js";
import { page, rulesTitle, shell } from "./app.js";
import { factionGroup, factionIcon } from "./faction-icons.js";
/* v1.7: read-only team & operative reference. Texts stay in English as published by the sources;
   data is imported by the operator (./scripts/import-teams.sh), nothing is fetched from the internet here. */
let teamIndex = null;
const teamCache = {};
const TEAM_TABS = ["operatives", "rules", "ploys", "equipment", "selection"];
export async function loadTeamIndex(force = false) {
  if (teamIndex && !force) return teamIndex;
  try {
    teamIndex = await api("/teams");
  } catch {
    teamIndex = { teams: [], import: null };
  }
  return teamIndex;
}
export const teamTitle = (x) => (x.catalog_id ? catName(x.catalog_id) : x.name);
/* v1.9: index row of a catalog team (slug, faction, archetypes) and its cached datacards. */
export const teamOf = (catalogId) =>
  teamIndex?.teams?.find((r) => r.catalog_id === catalogId) || null;
export async function teamData(slug) {
  return (
    teamCache[slug] ||
    (teamCache[slug] = await api("/teams/" + encodeURIComponent(slug)))
  );
}
export const cachedTeam = (catalogId) => {
  const x = teamOf(catalogId);
  return x ? teamCache[x.slug] || null : null;
};
/* Team name on match/stats pages: links to datacards when the team exists in the imported reference. */
export function teamLabel(catalogId) {
  const x = teamIndex?.teams?.find((r) => r.catalog_id === catalogId);
  const name = esc(catName(catalogId));
  return x
    ? `<a class="team-link" href="#teams/${esc(x.slug)}" title="${esc(t("datacards"))}">${name} ${icon("book")}</a>`
    : name;
}
/* Keywords are printed in capitals in the source; highlight them like on the cards.
   v1.8: BSData marks emphasis as **bold** (escaped first, so only that markup becomes HTML). */
const kw = (s) =>
  esc(s)
    .replace(/\*\*([^*]+?)\*\*/g, "<b>$1</b>")
    .replace(/\b([A-Z][A-Z0-9'’-]+(?: [A-Z][A-Z0-9'’-]+)*)\b/g, (m) =>
      m.length > 2 && !/^\d/.test(m) ? `<b class="kw">${m}</b>` : m,
    );
export function ruleText(text) {
  return String(text || "")
    .split("\n")
    .filter((l) => l.trim())
    .map((l) =>
      /^[•\-–]\s*/.test(l)
        ? `<p class="li">${kw(l.replace(/^[•\-–]\s*/, ""))}</p>`
        : `<p>${kw(l)}</p>`,
    )
    .join("");
}
/* v1.14: «Deploy Nuncio-aquila (0AP)» → ["Deploy Nuncio-aquila", "0AP"] — the AP cost of a unique action as a badge. */
const AP_RX = /\s*\(\s*(?:(\d+(?:\/\d+)?)\s*AP|AP\s*(\d+))\s*\)\s*$/i;
export function apSplit(name) {
  const s = String(name || ""),
    m = AP_RX.exec(s);
  return m ? [s.slice(0, m.index), (m[1] || m[2]) + "AP"] : [s, ""];
}
export const apBadge = (ap) =>
  ap ? ` <span class="ap" title="${esc(t("apCost"))}">${esc(ap)}</span>` : "";
export function ruleBlocks(body) {
  return (body || [])
    .map((b) =>
      b.k === "h"
        ? `<h4>${esc(b.t)}</h4>`
        : `<p class="${b.k === "p" ? "" : esc(b.k)}">${b.k === "lore" ? esc(b.t).replace(/\*\*([^*]+?)\*\*/g, "<b>$1</b>") : kw(b.t)}</p>`,
    )
    .join("");
}
export function datacard(o, id = "") {
  const st = o.stats || {};
  const conflicts = Object.entries(o.conflicts || {});
  const search = [
    o.name,
    ...(o.keywords || []),
    ...(o.weapons || []).map((w) => w.name),
  ]
    .join(" ")
    .toLowerCase();
  return `<article class="datacard" ${id ? `id="ref-${esc(id)}" tabindex="-1"` : ""} data-search="${esc(search)}"><header><h3>${esc(o.name)}</h3>${o.base ? `<span class="dc-base" title="${esc(t("baseSize"))}">⌀${esc(o.base)}mm</span>` : ""}</header><div class="dc-stats">${[
    ["APL", st.apl, "apl"],
    [t("statMove"), st.move, "move"],
    [t("statSave"), st.save, "save"],
    [t("statWounds"), st.wounds, "wounds"],
  ]
    .map(
      ([l, v, k]) =>
        `<div class="${o.conflicts?.[k] ? "conflict" : ""}"><span>${esc(l)}</span><b>${esc(v || "—")}</b></div>`,
    )
    .join("")}</div>${
    conflicts.length
      ? `<p class="dc-conflict">${esc(t("bsdataDiffers"))}: ${conflicts.map(([k, v]) => `${esc(k.toUpperCase())} ${esc(v)}`).join(", ")}</p>`
      : ""
  }${
    o.weapons?.length
      ? `<div class="table-wrap" tabindex="0"><table class="dc-weapons"><thead><tr><th>${t("weapon")}</th><th>ATK</th><th>HIT</th><th>DMG</th></tr></thead><tbody>${o.weapons
          .map(
            (w) =>
              `<tr><td><span class="wt ${esc(w.type)}" title="${esc(t(w.type === "melee" ? "melee" : "ranged"))}">${icon(w.type === "melee" ? "melee" : "crosshair")}</span>${esc(w.name)}${w.wr && w.wr !== "-" ? `<small data-terms="wr">${esc(w.wr)}</small>` : ""}</td><td>${esc(w.atk)}</td><td>${esc(w.hit)}</td><td>${esc(w.dmg)}</td></tr>`,
          )
          .join("")}</tbody></table></div>`
      : ""
  }${(o.abilities || [])
    .map(
      (a) =>
        `<div class="dc-rule" data-terms="text"><h4>${esc(a.name)}${a.type ? ` <small class="dc-type">${esc(a.type)}</small>` : ""}</h4>${ruleText(a.text)}</div>`,
    )
    .join("")}${(o.actions || [])
    .map((a) => {
      const [name, ap] = apSplit(a.name);
      return `<div class="dc-rule dc-action" data-terms="text"><h4>${esc(name)}${apBadge(ap)}</h4>${ruleText(a.text)}</div>`;
    })
    .join(
      "",
    )}<footer><span class="dc-keywords">${esc((o.keywords || []).join(", "))}</span>${
    /^https:\/\//.test(o.card || "")
      ? `<a href="${esc(o.card)}" target="_blank" rel="noopener noreferrer">${t("originalCard")} ↗</a>`
      : ""
  }</footer></article>`;
}
function sourcesLine(s, importedAt) {
  const k = s?.kt_datacards,
    b = s?.bsdata;
  return `<p class="muted sources">${t("sourcesLabel")}: ${[
    k &&
      `<a href="https://github.com/${esc(k.repo)}/tree/${esc(k.commit)}" target="_blank" rel="noopener noreferrer">${esc(k.repo)}</a> <span class="mono">@${esc(String(k.commit).slice(0, 7))}</span>${k.generated_at ? ` (${esc(date(k.generated_at))})` : ""}`,
    b &&
      `<a href="https://github.com/${esc(b.repo)}/tree/${esc(b.commit)}" target="_blank" rel="noopener noreferrer">${esc(b.repo)}</a> <span class="mono">@${esc(String(b.commit).slice(0, 7))}</span>${b.revision ? ` rev ${esc(b.revision)}` : ""}${b.comment ? ` · ${esc(b.comment)}` : ""}`,
  ]
    .filter(Boolean)
    .join(
      " · ",
    )}${importedAt ? ` · ${t("importedAt")} ${esc(date(importedAt))}` : ""}</p><p class="muted">${t("teamsDisclaimer")}</p>`;
}
async function teamsPage() {
  const ix = await loadTeamIndex(true);
  if (page !== "teams") return;
  if (!ix.teams.length) {
    shell(
      `${rulesTitle("rules_faction")}<section class="panel"><h2>${t("teamsEmptyTitle")}</h2><p>${t("teamsEmpty")}</p><pre class="mono">./scripts/import-teams.sh</pre><p class="muted">${t("teamsEmptyHint")}</p></section>`,
    );
    return;
  }
  const badge = (x) => {
    const asset = factionIcon(x.slug);
    return asset
      ? `<span class="team-insignia" ${asset.placeholder ? `title="${esc(t("factionPlaceholder"))}"` : ""}><img src="${BASE}factions/${esc(asset.slug)}.png" alt="" loading="lazy"></span>${asset.placeholder ? `<span class="muted">${t("factionPlaceholder")}</span>` : ""}`
      : `<span class="team-insignia" aria-hidden="true">${icon("book")}</span>`;
  };
  const groups = ["imperium", "chaos", "xenos", "other"]
    .map((group) => {
      const rows = ix.teams
        .filter((x) => factionGroup(x) === group)
        .sort((a, b) => teamTitle(a).localeCompare(teamTitle(b), locale()));
      if (!rows.length) return "";
      return `<section class="team-group"><h2 class="section-label">${t("faction_" + group)}</h2><div class="team-grid">${rows
        .map((x) => {
          const name = teamTitle(x);
          const arch = x.archetypes?.length
            ? x.archetypes
            : catalogs.find((c) => c.id === x.catalog_id)?.config?.archetypes ||
              [];
          return `<a class="team-tile" href="#teams/${esc(x.slug)}" data-search="${esc((name + " " + x.name + " " + arch.join(" ")).toLowerCase())}">${badge(x)}<strong>${esc(name)}</strong>${name !== x.name ? `<span class="muted">${esc(x.name)}</span>` : ""}<span class="row">${arch.map((a) => `<span class="badge">${esc(a)}</span>`).join("")}</span><span class="muted">${t("operativesCount")}: ${x.operatives}</span></a>`;
        })
        .join("")}</div></section>`;
    })
    .join("");
  shell(
    `${rulesTitle("rules_faction")}<div class="filters one"><label>${t("searchLabel")}<input id="team-search" type="search" autocomplete="off" placeholder="${esc(t("teamSearchHint"))}"></label></div>${groups}<p class="empty" id="team-none" hidden>${t("nothingFound")}</p><p class="muted">${t("factionIconSource")}: <a href="https://astartes.space/factions-kill-team-2024/" target="_blank" rel="noopener noreferrer">Astartes</a></p>${ix.import ? sourcesLine(ix.import.sources, ix.import.imported_at) : ""}`,
  );
}
async function teamPage(slug, tab, anchor = "") {
  if (!TEAM_TABS.includes(tab)) tab = "operatives";
  const x =
    teamCache[slug] ||
    (teamCache[slug] = await api("/teams/" + encodeURIComponent(slug)));
  if (page !== "teams" || location.hash.split("/")[1] !== slug) return;
  if (!teamIndex) loadTeamIndex();
  const d = x.data || {};
  const name = teamTitle(x);
  const archetypes = d.archetypes?.length
    ? d.archetypes
    : catalogs.find((c) => c.id === x.catalog_id)?.config?.archetypes || [];
  const counts = {
    operatives: d.operatives?.length || 0,
    rules: d.faction_rules?.length || 0,
    ploys: (d.strategy_ploys?.length || 0) + (d.firefight_ploys?.length || 0),
    equipment: d.equipment?.length || 0,
    selection: d.selection?.length || 0,
  };
  /* v1.8: every rule with all of its options (Chapter Tactics, Boons…); BSData-sourced text is labelled. */
  const src = (x) =>
    x.src === "bsdata"
      ? `<span class="src-note" title="${esc(t("bsdataTextHint"))}">BSData</span>`
      : "";
  const options = (r) =>
    r.options?.length
      ? `<div class="rule-options" role="list" aria-label="${esc(t("ruleOptions"))}">${r.options.map((o) => `<div class="rule-option" role="listitem"><h4>${esc(o.name)}${r.src === "bsdata" ? "" : src(o)}</h4>${ruleBlocks(o.body)}</div>`).join("")}</div>`
      : "";
  /* v1.11: every card has an anchor (ref-op-3, ref-sp-0…) for links from the reference search (#reference). */
  const rules = (items, prefix) =>
    items?.length
      ? `<div class="rule-list">${items.map((r, i) => `<section class="panel rule" id="ref-${prefix}-${i}" tabindex="-1" data-terms="text"><h3>${esc(r.name)}${src(r)}</h3>${ruleBlocks(r.body)}${options(r)}</section>`).join("")}</div>`
      : `<p class="empty">${t("noData")}</p>`;
  const body =
    tab === "operatives"
      ? `<div class="filters one"><label>${t("searchLabel")}<input id="op-filter" type="search" autocomplete="off" placeholder="${esc(t("operativeSearchHint"))}"></label></div><div class="datacards">${(d.operatives || []).map((o, i) => datacard(o, "op-" + i)).join("")}</div><p class="empty" id="op-none" hidden>${t("nothingFound")}</p>`
      : tab === "rules"
        ? rules(d.faction_rules, "fr")
        : tab === "ploys"
          ? `<h2 class="section-label">${t("strategyPloys")}</h2>${rules(d.strategy_ploys, "sp")}<h2 class="section-label">${t("firefightPloys")}</h2>${rules(d.firefight_ploys, "fp")}`
          : tab === "equipment"
            ? rules(d.equipment, "eq")
            : rules(d.selection, "sel");
  shell(
    `<header class="team-header"><a href="#teams" class="back">← ${t("rules_faction")}</a><h1>${esc(name)}</h1><div class="row">${name !== x.name ? `<span class="muted">${esc(x.name)}</span>` : ""}${archetypes.map((a) => `<span class="badge">${esc(a)}</span>`).join("")}${x.has_roster ? `<a class="button secondary small" href="#rosters/new/${esc(slug)}">${icon("list")}${t("rosterBuild")}</a>` : ""}</div></header><nav class="tabs" aria-label="${esc(t("sections"))}">${TEAM_TABS.map((k) => `<a href="#teams/${esc(slug)}/${k}" ${k === tab ? 'aria-current="page"' : ""}>${t("tab_" + k)}${counts[k] ? ` <span class="count">${counts[k]}</span>` : ""}</a>`).join("")}</nav>${body}${sourcesLine(x.sources, x.imported_at)}`,
  );
  const target = /^(op|fr|sp|fp|eq|sel)-\d{1,3}$/.test(anchor)
    ? document.getElementById("ref-" + anchor)
    : null;
  if (target) {
    target.classList.add("ref-target");
    target.scrollIntoView({ block: "center" });
    target.focus({ preventScroll: true });
  }
}
export async function teamsRoute(parts) {
  if (parts[0])
    return teamPage(decodeURIComponent(parts[0]), parts[1], parts[2] || "");
  return teamsPage();
}
function filterCards(inputSel, itemSel, noneSel) {
  const q = document.querySelector(inputSel).value.trim().toLowerCase();
  let shown = 0;
  document.querySelectorAll(itemSel).forEach((el) => {
    const ok = !q || el.dataset.search.includes(q);
    el.hidden = !ok;
    shown += ok;
  });
  if (inputSel === "#team-search")
    document.querySelectorAll(".team-group").forEach((group) => {
      group.hidden = !group.querySelector(".team-tile:not([hidden])");
    });
  const none = document.querySelector(noneSel);
  if (none) none.hidden = shown > 0;
}

/* v1.9: listeners are registered from main.js in a fixed order (the former <script> order). */
export function init() {
  app.addEventListener("input", (e) => {
    if (e.target.id === "team-search")
      filterCards("#team-search", ".team-tile", "#team-none");
    if (e.target.id === "op-filter")
      filterCards("#op-filter", ".datacard", "#op-none");
  });
}
