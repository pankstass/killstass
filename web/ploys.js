import { app, button, esc, icon, me, notify, t } from "./core.js";
import { currentMatch, drawMatch, updateMatch } from "./app.js";
import { setBoardPanel } from "./board.js";
import { cachedTeam, ruleBlocks, teamData, teamOf } from "./teams.js";
import { cpState } from "./turns.js";
import { isHotseat } from "./quickstart.js";
/* v1.14 — ploys on the board (Kill Team 2024 core rules, «Ploys»): spending CP on a strategy or firefight ploy
   of the player's team or on Command Re-roll records it in the match protocol (POST /ploys, «Undo last»
   reverts it). Other than Command Re-roll, a ploy is used once per turning point: a repeat asks first and is
   sent as an explicit repeat (some team rules allow it). */
export const COMMAND_REROLL = "Command Re-roll";
let ploySlot = null;
const shown = new Set(); // ploy texts open: `${slot}:${kind}:${name}`
const slotsOf = (m) =>
  isHotseat(m)
    ? [1, 2]
    : m.players.filter((p) => p.user_id === me?.id).map((p) => p.slot);
export const ploysOn = (m) =>
  m.status === "active" && !m.demo && m.kind !== "guest" && slotsOf(m).length;
const usedNow = (m, p, name) =>
  (m.ploys || []).some(
    (y) =>
      y.player_id === p.id &&
      y.turning_point === m.current_turn &&
      y.name === name,
  );
function ployRow(m, p, kind, x, cp, i) {
  const k = `${p.slot}:${kind}:${x.name}`,
    id = `ploy-${p.slot}-${kind}-${i}`,
    used = usedNow(m, p, x.name),
    repeatable = x.name === COMMAND_REROLL;
  return `<li class="ploy ${used ? "used" : ""}"><div class="ploy-head"><button type="button" class="ploy-name" data-action="ploy-text" data-key="${esc(k)}" aria-expanded="${shown.has(k)}" aria-controls="${id}"><span>${esc(x.name)}</span>${used ? `<small class="ploy-used">${esc(t("ployUsedNow"))}</small>` : ""}</button><button type="button" class="${used && !repeatable ? "secondary small" : "small"}" data-action="ploy-use" data-slot="${p.slot}" data-kind="${kind}" data-name="${esc(x.name)}" data-used="${used && !repeatable ? 1 : ""}" aria-label="${esc(t("ployUse") + ": " + x.name + ", 1CP")}" ${cp < 1 ? `disabled title="${esc(t("cpNotEnough"))}"` : ""}>${icon("bolt")}<span>1CP</span></button></div><div class="ploy-text" id="${id}" data-terms="text" ${shown.has(k) ? "" : "hidden"}>${x.body ? ruleBlocks(x.body) : `<p>${esc(x.text || "")}</p>`}</div></li>`;
}
function playerPloys(m, p) {
  const team = cachedTeam(p.team_id),
    d = team?.data || {};
  if (!team && teamOf(p.team_id))
    teamData(teamOf(p.team_id).slug).then(() => {
      if (currentMatch?.id === m.id) drawMatch(currentMatch);
    });
  const cp = cpState(m, p, m.current_turn).cp,
    reroll = { name: COMMAND_REROLL, text: t("commandRerollText") },
    group = (kind, title, list) =>
      `<h3 class="section-label">${t(title)}</h3><ul class="ploy-list">${list.map((x, i) => ployRow(m, p, kind, x, cp, i)).join("")}</ul>`;
  return `<p class="ploy-cp"><b>CP ${cp}</b> · ${t("turn")} ${m.current_turn}</p>${d.strategy_ploys?.length ? group("strategy", "strategyPloys", d.strategy_ploys) : ""}${group("firefight", "firefightPloys", [reroll, ...(d.firefight_ploys || [])])}${team ? "" : `<p class="muted">${t("ployTeamUnknown")}</p>`}`;
}
/* The match protocol of ploys, newest first (both players; it is public once used). */
export function ployLog(m) {
  const rows = [...(m.ploys || [])].reverse();
  if (!rows.length) return `<p class="muted">${t("ployLogEmpty")}</p>`;
  const who = (slot) =>
    m.players.find((p) => p.slot === slot)?.display_name || "";
  return `<ol class="ploy-log">${rows.map((y) => `<li><span class="muted">TP${y.turning_point}</span> <b>${esc(who(y.slot))}</b> · ${esc(y.name)} <small class="muted">${t(y.kind === "strategy" ? "ployStrategy" : "ployFirefight")} · ${y.cost}CP</small></li>`).join("")}</ol>`;
}
export function ploysPanel(m) {
  const slots = slotsOf(m);
  if (!slots.includes(ploySlot)) ploySlot = slots[0];
  const p = m.players.find((x) => x.slot === ploySlot);
  if (!p) return "";
  const tabs =
    slots.length > 1
      ? `<div class="row ploy-tabs" role="group" aria-label="${esc(t("player"))}">${slots.map((s) => button(m.players.find((x) => x.slot === s).display_name, "ploys-open", s === ploySlot ? "selected small" : "secondary small", `data-slot="${s}" aria-pressed="${s === ploySlot}"`)).join("")}</div>`
      : "";
  return `<h2>${t("ploys")}: ${esc(p.display_name)}</h2>${tabs}<p class="muted small">${t("ployHint")}</p>${playerPloys(m, p)}<details class="ploy-protocol"><summary>${t("ployLog")} (${(m.ploys || []).length})</summary>${ployLog(m)}</details>`;
}
/* The ploys of a turning point for the score table: «Name (1CP)». */
export const ploysAt = (m, p, tp) =>
  (m.ploys || [])
    .filter((y) => y.player_id === p.id && y.turning_point === tp)
    .map((y) => `${y.name} (${y.cost}CP)`);

async function use(b, repeat = false) {
  await updateMatch("/ploys", {
    slot: +b.dataset.slot,
    kind: b.dataset.kind,
    name: b.dataset.name,
    cost: 1,
    repeat,
  });
}
export function init() {
  app.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b || b.disabled || !currentMatch) return;
    const a = b.dataset.action;
    if (a === "ploys-open") {
      ploySlot = +b.dataset.slot || null;
      setBoardPanel("ploys");
      drawMatch(currentMatch);
      document
        .querySelector("#board-sheet")
        ?.scrollIntoView({ block: "nearest" });
    } else if (a === "ploy-text") {
      const k = b.dataset.key,
        panel = document.getElementById(b.getAttribute("aria-controls"));
      if (shown.has(k)) shown.delete(k);
      else shown.add(k);
      b.setAttribute("aria-expanded", String(shown.has(k)));
      if (panel) panel.hidden = !shown.has(k);
    } else if (a === "ploy-use") {
      const repeat = !!b.dataset.used;
      if (repeat && !confirm(t("ployRepeatConfirm"))) return;
      b.disabled = true;
      try {
        await use(b, repeat);
      } catch (err) {
        if (err.code === "ploy_repeat" && confirm(t("ployRepeatConfirm")))
          await use(b, true).catch((x) => notify(x.message));
        else notify(err.message);
      } finally {
        b.disabled = false;
      }
    }
  });
}
