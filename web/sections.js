/* v1.14 (Т1): the table of the app's sections — one place for the menu, the groups, icons, titles and the
   «← group» links. Pure data without the DOM: web/groups.js draws the menu and the group pages from it, and
   tests/e2e/unit.test.mjs checks that every section has a group, an icon, a route and both translations.
   The addresses of the sections stay as they were (#history, #friends…), so links from notifications, push,
   the calendar and bookmarks keep working; the groups get their own pages (#muster, #results, #club, #rules). */
export const GROUPS = [
  { id: "overview", icon: "grid" },
  {
    id: "muster",
    icon: "list",
    hint: "grp_musterHint",
    items: ["rosters", "maps"],
  },
  {
    id: "results",
    icon: "chart",
    hint: "grp_resultsHint",
    items: ["history", "stats"],
  },
  {
    id: "club",
    icon: "people",
    hint: "grp_clubHint",
    items: ["friends", "nights", "tournaments"],
  },
  {
    id: "rules",
    icon: "book",
    hint: "rules_hint",
    items: ["reference", "core", "teams"],
  },
  { id: "profile", icon: "user" },
  /* administrators only; on a phone it is opened from the profile */
  { id: "admin", icon: "gear", admin: true },
];
/* A section: icon, title key (default — its id), hint on the group page tile, the English name under the
   title in the Russian interface (the rules books keep their published names) and the pages opened from it
   that belong to its group (#player/… from «Comms», #map/… from «Maps»). */
export const SECTIONS = {
  rosters: { icon: "list", hint: "sec_rostersHint" },
  maps: { icon: "target", hint: "sec_mapsHint", pages: ["map"] },
  history: { icon: "history", hint: "sec_historyHint" },
  stats: { icon: "chart", hint: "sec_statsHint" },
  friends: { icon: "people", hint: "sec_friendsHint", pages: ["player"] },
  nights: { icon: "table", hint: "sec_nightsHint" },
  tournaments: { icon: "trophy", hint: "sec_tournamentsHint" },
  reference: {
    icon: "search",
    title: "rules_quick",
    en: "Quick Reference",
    hint: "rules_quickHint",
  },
  core: {
    icon: "book",
    title: "rules_core",
    en: "Core Rules",
    hint: "rules_coreHint",
  },
  teams: {
    icon: "shield",
    title: "rules_faction",
    en: "Faction Rules",
    hint: "rules_factionHint",
  },
};
/* Pages outside the menu: the board and the match flows, pages without a session. */
export const LOOSE = [
  "match",
  "quick",
  "new",
  "join",
  "demo",
  "styleguide",
  "shared",
  "tv",
];
export const groupById = (id) => GROUPS.find((g) => g.id === id) || null;
/* The section a page belongs to: itself or the section it is opened from. */
export function sectionOf(page) {
  if (SECTIONS[page]) return page;
  return (
    Object.keys(SECTIONS).find((k) => SECTIONS[k].pages?.includes(page)) || null
  );
}
/* The menu item of a page: a group (or a top-level item like «HQ») — null for pages outside the menu. */
export function groupOf(page) {
  if (groupById(page)) return page;
  const sec = sectionOf(page);
  return sec ? GROUPS.find((g) => g.items?.includes(sec))?.id || null : null;
}
export const sectionTitle = (k) => SECTIONS[k]?.title || k;
