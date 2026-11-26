import { api, esc, icon, lang, me, t } from "./core.js";
import { shell } from "./app.js";
import {
  GROUPS,
  SECTIONS,
  groupById,
  groupOf,
  sectionOf,
  sectionTitle,
} from "./sections.js";
/* v1.14 — the menu by purpose: HQ · Muster · Results · Club · Rules · Profile (+ Admin), drawn from the table
   in web/sections.js. On a computer the sections of the open group unfold under it in the sidebar; a phone
   shows the six items without scrolling and the sibling sections as tabs under the page title. The group
   pages show tiles with a short summary from GET /api/nav-summary; a dot marks a group that waits for the
   player. The summary is refreshed at most every 30 s and on new notifications. */
let summary = null,
  summaryAt = 0,
  loading = null;
const FRESH = 30000;
/* sections with a summary on their tile */
const SUMMARY = {
  rosters: 1,
  maps: 1,
  history: 1,
  stats: 1,
  friends: 1,
  nights: 1,
  tournaments: 1,
};
const n = (key, v) => t(key).replace("{n}", v);
function attention(s) {
  return {
    results: (s?.history?.to_confirm || 0) > 0,
    club:
      (s?.friends?.challenges || 0) +
        (s?.friends?.requests || 0) +
        (s?.nights?.unanswered || 0) >
      0,
  };
}
const dot = (id) =>
  attention(summary)[id]
    ? `<span class="nav-dot" aria-hidden="true"></span><span class="sr-only">${esc(t("navAttention"))}</span>`
    : "";
export function navHtml(current) {
  const g = groupOf(current),
    sec = sectionOf(current);
  return GROUPS.filter((x) => !x.admin || me?.is_admin)
    .map((x) => {
      const here = x.id === g,
        cur = here
          ? current === x.id
            ? 'aria-current="page"'
            : 'aria-current="true"'
          : "";
      const subs =
        here && x.items
          ? `<div class="nav-sub">${x.items
              .map(
                (k) =>
                  `<a class="nav-link nav-subitem" href="#${k}" ${k === current ? 'aria-current="page"' : k === sec ? 'aria-current="true"' : ""}>${icon(SECTIONS[k].icon)}<span class="nav-label">${esc(t(sectionTitle(k)))}</span></a>`,
              )
              .join("")}</div>`
          : "";
      return `<a class="nav-link${x.admin ? " nav-admin" : ""}" href="#${x.id}" data-group="${x.id}" ${cur}>${icon(x.icon)}<span class="nav-label">${esc(t(x.id))}</span>${dot(x.id)}</a>${subs}`;
    })
    .join("");
}
/* Title of a section page: «← Group», the heading and (on a phone) the sibling sections. */
export function groupTitle(k, section = k) {
  const gid = groupOf(section),
    g = groupById(gid);
  if (!g?.items)
    return `<header class="page-title"><h1>${esc(t(k))}</h1></header>`;
  const cur = sectionOf(section);
  return `<header class="page-title team-header"><a href="#${gid}" class="back">← ${esc(t(gid))}</a><h1>${esc(t(k))}</h1><nav class="group-tabs" aria-label="${esc(t(gid))}">${g.items.map((x) => `<a href="#${x}" ${x === cur ? 'aria-current="page"' : ""}>${esc(t(sectionTitle(x)))}</a>`).join("")}</nav></header>`;
}
function nextNight(v) {
  return new Date(v).toLocaleDateString(lang === "en" ? "en-GB" : "ru-RU", {
    day: "2-digit",
    month: "2-digit",
  });
}
/* The short summary of a tile: parts that wait for the player are marked. */
function sumHtml(k, s) {
  if (!s) return "";
  const out = [];
  const add = (text, cls = "") => out.push([text, cls]);
  if (k === "rosters") {
    add(n("sum_rosters", s.rosters.count));
    if (s.rosters.invalid)
      add(n("sum_rostersInvalid", s.rosters.invalid), "warn");
  } else if (k === "maps") add(n("sum_maps", s.maps.count));
  else if (k === "history") {
    add(n("sum_games", s.history.games));
    if (s.history.to_confirm)
      add(n("sum_toConfirm", s.history.to_confirm), "attn");
    if (s.history.live) add(n("sum_live", s.history.live));
  } else if (k === "stats") {
    add(n("sum_games", s.stats.games));
    if (s.stats.win_rate != null) add(n("sum_winRate", s.stats.win_rate));
  } else if (k === "friends") {
    add(n("sum_friends", s.friends.friends));
    if (s.friends.challenges)
      add(n("sum_challenges", s.friends.challenges), "attn");
    if (s.friends.requests) add(n("sum_requests", s.friends.requests), "attn");
  } else if (k === "nights") {
    add(
      s.nights.next
        ? t("sum_nextNight").replace("{d}", nextNight(s.nights.next))
        : t("sum_noNights"),
    );
    if (s.nights.unanswered)
      add(n("sum_unanswered", s.nights.unanswered), "attn");
  } else if (k === "tournaments")
    add(
      s.tournaments.active
        ? n("sum_tournaments", s.tournaments.active)
        : t("sum_noTournaments"),
    );
  return out
    .map(([x, cls]) => `<span${cls ? ` class="${cls}"` : ""}>${esc(x)}</span>`)
    .join(" · ");
}
/* Puts a fresh summary into the open page: the dots of the menu and the tiles of a group page. */
function applySummary() {
  document.querySelectorAll(".sidebar a.nav-link[data-group]").forEach((a) => {
    a.querySelectorAll(".nav-dot, .sr-only").forEach((x) => x.remove());
    a.insertAdjacentHTML("beforeend", dot(a.dataset.group));
  });
  document.querySelectorAll("[data-sum]").forEach((el) => {
    el.innerHTML = sumHtml(el.dataset.sum, summary);
  });
}
export function refreshSummary(force = false) {
  if (!me || (!force && Date.now() - summaryAt < FRESH) || loading)
    return loading || Promise.resolve(summary);
  loading = api("/nav-summary")
    .then((s) => {
      summary = s;
      summaryAt = Date.now();
      applySummary();
      return s;
    })
    .catch(() => summary)
    .finally(() => (loading = null));
  return loading;
}
export const resetSummary = () => {
  summary = null;
  summaryAt = 0;
};
export function groupPage(id) {
  const g = groupById(id);
  const tile = (k) => {
    const s = SECTIONS[k];
    return `<a class="rules-tile" href="#${k}">${icon(s.icon)}<strong>${esc(t(sectionTitle(k)))}</strong>${s.en && lang !== "en" ? `<span class="muted" lang="en">${esc(s.en)}</span>` : ""}${k in SUMMARY ? `<b class="tile-sum" data-sum="${k}">${sumHtml(k, summary)}</b>` : ""}<span>${esc(t(s.hint))}</span></a>`;
  };
  shell(
    `<header class="page-title"><h1>${esc(t(id))}</h1></header><p class="muted">${esc(t(g.hint))}</p><nav class="rules-hub" aria-label="${esc(t(id))}">${g.items.map(tile).join("")}</nav>`,
  );
}
