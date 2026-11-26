import { VERSION, button, esc, icon, t } from "./core.js";
import { standalone } from "./share.js";
import { datacard } from "./teams.js";
import { ARCHETYPES, FACTION_COLORS, emblemSvg } from "./emblem.js";
import { trackerBlock } from "./tracker.js";
import { qrSvg } from "./qr.js";
import { printHtml } from "./sheets.js";
/* v1.9 — #styleguide: the interface building blocks on one page (works without an account), rendered by
   the same functions the app uses, plus print previews of datacards. Sample data is invented. */
const ICONS = [
  "crosshair",
  "grid",
  "history",
  "people",
  "chart",
  "user",
  "book",
  "melee",
  "skull",
  "shield",
  "play",
  "pause",
  "pass",
  "menu",
  "dice",
  "list",
  "clock",
  "swap",
  "flag",
  "share",
  "lock",
  "check",
  "plus",
  "star",
  "copy",
  "undo",
  "print",
  "qr",
  "target",
  "trophy",
  "gear",
  "heart",
  "eye",
  "bolt",
  "upload",
  "table",
  "palette",
];
const SWATCHES = [
  "bg",
  "panel",
  "raised",
  "ink",
  "muted",
  "line",
  "accent",
  "accent-soft",
  "danger",
  "p1",
  "p2",
  "bar",
];
const SAMPLE = {
  name: "Vanguard Sergeant",
  base: 32,
  keywords: ["SAMPLE", "LEADER"],
  stats: { apl: "3", move: '6"', save: "3+", wounds: "13" },
  weapons: [
    {
      name: "Marksman carbine",
      type: "ranged",
      atk: "4",
      hit: "3+",
      dmg: "3/4",
      wr: "Piercing Crits 1",
    },
    {
      name: "Combat blade",
      type: "melee",
      atk: "4",
      hit: "3+",
      dmg: "4/5",
      wr: "Lethal 5+",
    },
  ],
  abilities: [
    {
      name: "Steady Hand",
      text: "Once per turning point, re-roll one of your attack dice.",
    },
  ],
};
const SAMPLE2 = {
  name: "Vanguard Gunner",
  base: 32,
  stats: { apl: "2", move: '6"', save: "4+", wounds: "10" },
  weapons: [
    {
      name: "Heavy rifle",
      type: "ranged",
      atk: "5",
      hit: "4+",
      dmg: "4/5",
      wr: "Heavy (Dash only), Piercing 1",
    },
  ],
};
function sampleMatch() {
  const op = (id, name, wounds, max, extra = {}) => ({
    id,
    slot: 1,
    position: id,
    name,
    card: name,
    wounds,
    wounds_max: max,
    order_token: "engage",
    activated_tp: null,
    incapacitated_tp: null,
    stats: {},
    weapons: [],
    ...extra,
  });
  return {
    id: "styleguide",
    status: "active",
    current_turn: 2,
    kind: "friend",
    operatives: [
      op(1, "Vanguard Sergeant", 13, 13, { activated_tp: 2 }),
      op(2, "Vanguard Gunner", 4, 10, { order_token: "conceal" }),
      op(3, "Vanguard Scout", 0, 8, { incapacitated_tp: 1 }),
    ],
  };
}
const section = (id, h, body) =>
  `<section class="panel sg-section" id="sg-${id}"><h2>${esc(h)}</h2>${body}</section>`;
export function styleguidePage() {
  const m = sampleMatch(),
    p = { slot: 1, roster_id: null, team_id: null };
  standalone(
    `<header class="match-header"><span class="eyebrow">KILLSTASS ${esc(VERSION)}</span><h1>${icon("palette")} ${t("styleguide")}</h1><p class="muted">${t("styleguideHint")}</p><nav class="row sg-nav" aria-label="${esc(t("styleguide"))}">${["colors", "type", "buttons", "badges", "forms", "icons", "emblems", "board", "cards", "print"].map((x) => `<a class="button secondary small" href="#styleguide" data-sg="${x}">${t("sg_" + x)}</a>`).join("")}</nav></header>${section(
      "colors",
      t("sg_colors"),
      `<div class="sg-swatches">${SWATCHES.map((s) => `<div class="sg-swatch"><span class="swatch sw-${s}"></span><code>--${s}</code></div>`).join("")}</div><p class="muted small">${t("sg_colorsHint")}</p>`,
    )}${section(
      "type",
      t("sg_type"),
      `<p class="eyebrow">EYEBROW / OPERATION</p><h1>${t("sg_h1")}</h1><h2>${t("sg_h2")}</h2><h3>${t("sg_h3")}</h3><p>${t("sg_body")}</p><p class="muted">${t("sg_muted")}</p><p class="mono accent">ABCD2345 · 12:34</p>`,
    )}${section(
      "buttons",
      t("sg_buttons"),
      `<div class="row"><button type="button">${t("save")}</button>${button(t("cancel"), "sg-noop", "secondary")}${button(t("sg_selected"), "sg-noop", "selected")}${button(t("sg_text"), "sg-noop", "text")}<button type="button" class="danger">${t("deleteAccount")}</button><button type="button" disabled>${t("sg_disabled")}</button></div><div class="row">${button("−", "sg-noop", "mini")}${button("+", "sg-noop", "mini")}<button type="button" class="secondary">${icon("dice")}<span>${t("diceRoller")}</span></button><button type="button" class="secondary undo">${icon("undo")}<span>${t("undoShort")}</span></button></div>`,
    )}${section(
      "badges",
      t("sg_badges"),
      `<div class="row"><span class="badge active">${t("active")}</span><span class="badge">${t("confirmed")}</span><span class="badge down">${icon("skull")}${t("opDown")}</span><span class="badge injured">${t("opInjured")}</span><span class="chip">${icon("flag")}<span>Chip</span></span><span class="chip secret">${icon("lock")}<span>${t("tacHidden")}</span></span><span class="chip primary">${icon("shield")}<span>${t("op_crit")} +2</span></span></div><p class="warning">${t("sg_warning")}</p>`,
    )}${section(
      "forms",
      t("sg_forms"),
      `<form class="grid sg-form"><label>${t("name")}<input value="Kill Team"></label><label>${t("tFormat")}<select><option>${t("tFormatSwiss")}</option><option>${t("tFormatLeague")}</option></select></label><label>${t("notes")}<textarea rows="2">…</textarea></label><fieldset><legend>${t("sg_choices")}</legend><label class="check"><input type="checkbox" checked>${t("atkCover")}</label><label class="check"><input type="radio" name="sg-r" checked>A</label><label class="check"><input type="radio" name="sg-r">B</label></fieldset></form>`,
    )}${section(
      "icons",
      t("sg_icons"),
      `<ul class="sg-icons">${ICONS.map((i) => `<li>${icon(i)}<code>${i}</code></li>`).join("")}</ul>`,
    )}${section(
      "emblems",
      t("sg_emblems"),
      `<div class="sg-emblems">${Object.keys(FACTION_COLORS)
        .map(
          (f) =>
            `<div class="sg-emblem-row"><code>${f}</code>${["", ...ARCHETYPES].map((a) => `<span class="emblem" title="${esc(a || "initial")}">${emblemSvg({ faction: f, archetype: a, initial: f, label: `${f} ${a}`.trim() })}</span>`).join("")}</div>`,
        )
        .join("")}</div><p class="muted small">${t("sg_emblemsHint")}</p>`,
    )}${section(
      "board",
      t("sg_board"),
      `<div class="sg-board"><table class="tp-grid"><tbody><tr><th scope="row">Crit</th><td class="cell"><span class="tokens"><span class="token on">${icon("skull")}</span><span class="token">${icon("skull")}</span></span></td><td class="cell now step">${button("−", "sg-noop", "mini")}<output>2</output>${button("+", "sg-noop", "mini")}</td><td class="cell na"></td></tr></tbody></table><div class="half slot-1 readonly sg-half">${trackerBlock(m, p, false)}</div><div class="half-vp sg-vp"><b class="bump">12</b><small>VP</small></div></div>`,
    )}${section(
      "cards",
      t("sg_cards"),
      `<div class="datacards">${datacard(SAMPLE)}${datacard(SAMPLE2)}</div><figure class="invite-qr sg-qr">${qrSvg("https://killstass.lan/#join/ABCD2345", { label: "QR" })}<figcaption class="muted">${t("inviteQrHint")}</figcaption></figure>`,
    )}${section(
      "print",
      t("sg_print"),
      `<p class="muted">${t("sg_printHint")}</p><div class="row"><button type="button" class="secondary" data-action="sg-print">${icon("print")}<span>${t("print")}</span></button></div>`,
    )}`,
  );
}
export function init() {
  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-sg]");
    if (a) {
      e.preventDefault();
      document
        .querySelector("#sg-" + a.dataset.sg)
        ?.scrollIntoView({ block: "start" });
      return;
    }
    const b = e.target.closest('button[data-action="sg-print"]');
    if (b)
      printHtml(
        t("sg_printTitle"),
        `<div class="roster-sheet"><div class="datacards">${datacard(SAMPLE)}${datacard(SAMPLE2)}${datacard({ ...SAMPLE2, name: "Vanguard Scout", stats: { apl: "2", move: '7"', save: "4+", wounds: "8" } })}</div></div>`,
      );
  });
}
