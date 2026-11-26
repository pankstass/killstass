/* Local insignia sourced from Astartes; see docs/faction-icons-source.json. */
const assets = new Set([
  "angels-of-death",
  "tempestus-aquilons",
  "wrecka-krew",
  "celestian-insidiants",
  "canoptek-circle",
  "hierotek-circle",
  "pathfinders",
  "hunter-clade",
  "corsair-voidscarred",
  "elucidian-starstriders",
  "warpcoven",
  "chaos-cult",
  "void-dancer-troupe",
  "deathwatch",
  "death-korps",
  "phobos-strike-team",
  "exaction-squad",
  "scout-squad",
  "spectre-squad",
  "xv26-stealth-battlesuits",
  "vespid-stingwings",
  "brood-brothers",
  "nemesis-claw",
  "blooded",
  "kasrkin",
  "kommandos",
  "wyrmblade",
  "blades-of-khaine",
  "legionaries",
  "hand-of-the-archon",
  "mandrakes",
  "plague-marines",
  "murderwings",
  "goremongers",
  "novitiates",
  "farstalker-kinband",
  "ratlings",
  "fellgor-ravagers",
  "hearthkyn-salvagers",
  "raveners",
  "sanctifiers",
  "imperial-navy-breachers",
  "wolf-scouts",
  "inquisitorial-agents",
  "gellerpox-infected",
  "hernkyn-yaegirs",
]);
const fallback = {
  battleclade: "hunter-clade",
  "exodite-dragon-masters": "blades-of-khaine",
  "strike-force-variel": "angels-of-death",
};
export function factionIcon(slug) {
  if (assets.has(slug)) return { slug, placeholder: false };
  if (fallback[slug] && assets.has(fallback[slug]))
    return { slug: fallback[slug], placeholder: true };
  return null;
}
export function factionGroup(team) {
  if (team.slug === "strike-force-variel") return "imperium";
  if (["imperium", "chaos"].includes(team.faction)) return team.faction;
  if (
    ["aeldari", "tyranid", "gsc", "necron", "ork", "tau", "votann"].includes(
      team.faction,
    )
  )
    return "xenos";
  return "other";
}
