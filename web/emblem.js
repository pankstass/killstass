import { catalogs, esc } from "./core.js";
import { teamOf } from "./teams.js";
/* v1.9 — generated team emblems: a hexagon in the faction family's colours with a glyph for the
   team's first archetype. Plain geometry drawn for KILLSTASS; no faction iconography is reproduced. */
export const FACTION_COLORS = {
  imperium: ["#1f3a68", "#e2bd55"],
  chaos: ["#5c1a1a", "#e6a75a"],
  aeldari: ["#0f4c5c", "#8fe3d6"],
  tyranid: ["#3d1f4f", "#dcb0f7"],
  gsc: ["#2d2448", "#bfaaff"],
  necron: ["#14261c", "#62e690"],
  ork: ["#2f3d16", "#bde464"],
  tau: ["#5a3b12", "#f4cd80"],
  votann: ["#4a2a14", "#ffa566"],
  unaligned: ["#2b2f36", "#cdd2da"],
};
const GLYPHS = {
  "Seek & Destroy": () => '<path d="M20 8.5 30 27l-10-5.2L10 27z"/>',
  Security: (bg) =>
    `<path d="M20 8.5l9.5 3.4v6.6c0 6.1-4 10.6-9.5 12.9-5.5-2.3-9.5-6.8-9.5-12.9v-6.6z"/><path d="M14.5 19.5h11" fill="none" stroke="${bg}" stroke-width="2.4"/>`,
  Infiltration: (bg) =>
    `<path d="M8.5 20Q20 9 31.5 20 20 31 8.5 20z"/><circle cx="20" cy="20" r="3.6" fill="${bg}"/>`,
  Recon: () =>
    '<path d="M20 7.5l3.2 9.3 9.3 3.2-9.3 3.2L20 32.5l-3.2-9.3L7.5 20l9.3-3.2z"/>',
};
export const ARCHETYPES = Object.keys(GLYPHS);
export function emblemSvg({
  faction = "unaligned",
  archetype = "",
  initial = "?",
  label = "",
} = {}) {
  const [bg, fg] = FACTION_COLORS[faction] || FACTION_COLORS.unaligned,
    glyph = GLYPHS[archetype];
  return `<svg class="emblem-svg" viewBox="0 0 40 40" ${label ? `role="img" aria-label="${esc(label)}"` : 'aria-hidden="true"'} data-faction="${esc(faction)}"><path d="M20 1.5 36 10.75v18.5L20 38.5 4 29.25v-18.5z" fill="${bg}"/><path d="M20 4.6 33.3 12.3v15.4L20 35.4 6.7 27.7V12.3z" fill="none" stroke="${fg}" stroke-opacity=".45" stroke-width="1.2"/><g fill="${fg}" stroke="${bg}" stroke-width="1.6" stroke-linejoin="round">${glyph ? glyph(bg) : `<text x="20" y="25.5" text-anchor="middle" font-size="15" font-weight="700" stroke="none">${esc(String(initial).slice(0, 1).toUpperCase())}</text>`}</g></svg>`;
}
/* Emblem of a catalog team (falls back to the player's initial). */
export function teamEmblem(teamId, fallbackName = "?", label = "") {
  const team = catalogs.find((c) => c.id === teamId),
    row = teamOf(teamId),
    arch = row?.archetypes?.[0] || team?.config?.archetypes?.[0] || "";
  return emblemSvg({
    faction: row?.faction || "unaligned",
    archetype: arch,
    initial: (team?.label || fallbackName || "?").trim(),
    label,
  });
}
