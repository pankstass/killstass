import {
  app,
  badge,
  button,
  catName,
  catalogs,
  esc,
  icon,
  me,
  notify,
  t,
} from "./core.js";
import { currentMatch, drawMatch, updateMatch } from "./app.js";
import { isDown } from "./offline.js";
import { attackPanel } from "./attack.js";
import { teamEmblem } from "./emblem.js";
import {
  loadMatchRoster,
  opCard,
  printMatchRoster,
  rostersPanel,
} from "./sheets.js";
import { tap, tracked, trackerBlock } from "./tracker.js";
import { cachedTeam, teamData, teamOf } from "./teams.js";
import { clockData, clockForm, clockTime, setClock } from "./clock.js";
import { dice, diceBody } from "./dice.js";
import { catalogDetail, matchSources, primaryOptions } from "./ops.js";
import { isHotseat, slotAttr } from "./quickstart.js";
import { ENDED, sharePanel } from "./share.js";
import { teamLabel } from "./teams.js";
import {
  cpPending,
  cpState,
  finishPanel,
  initiativeBlock,
  initiativeOf,
  isSwapped,
  ordered,
  turnButtons,
} from "./turns.js";
import { equipmentBox } from "./equipment.js";
import { ploysAt, ploysOn, ploysPanel } from "./ploys.js";
/* v1.8 — match scoreboard in the style of BattleKit: a turning point bar with a Features menu, two coloured
   halves (slot 1 red, slot 2 navy) with Crit/Tac tokens per turning point and the Kill grade, CP, ops and kills.
   Nothing is computed for the record here: every click sends the same API calls as before, the server validates. */
export let boardPanel = null;
export const setBoardPanel = (v) => (boardPanel = v);
/* v1.9 — tabletop mode (phone lying between the players: the first half is turned to the opponent),
   tap feedback (changed numbers pulse once), team datacards for the tracker and the attack calculator. */
const TABLETOP_KEY = "killstass-tabletop";
export const isTabletop = () => {
  try {
    return localStorage.getItem(TABLETOP_KEY) === "1";
  } catch {
    return false;
  }
};
const seen = {};
function changed(m, kind, slot, value) {
  const key = `${m.id}:${kind}:${slot}`,
    before = seen[key];
  seen[key] = value;
  return before !== undefined && before !== value ? "bump" : "";
}
const loading = new Set();
/* Load the players' team datacards once (names for «add operative», stats for cards and the calculator). */
function ensureCards(m) {
  for (const p of m.players) {
    const row = teamOf(p.team_id);
    if (!row || cachedTeam(p.team_id) || loading.has(row.slug)) continue;
    loading.add(row.slug);
    teamData(row.slug)
      .then(() => {
        const f = document.activeElement;
        if (
          currentMatch?.id === m.id &&
          !(f && ["INPUT", "TEXTAREA", "SELECT"].includes(f.tagName))
        )
          drawMatch(currentMatch);
      })
      .catch(() => {});
  }
}
let rosterData = { id: null, slots: {} };
function rosterOf(m, slot, panel) {
  if (rosterData.id !== m.id + m.status)
    rosterData = { id: m.id + m.status, slots: {} };
  if (!(slot in rosterData.slots)) {
    rosterData.slots[slot] = null;
    loadMatchRoster(m, slot).then((r) => {
      rosterData.slots[slot] = r;
      if (boardPanel === panel && currentMatch?.id === m.id)
        drawMatch(currentMatch);
    });
  }
  return rosterData.slots[slot];
}
function rosterSheetBody(m) {
  for (const p of m.players) rosterOf(m, p.slot, "roster");
  return rostersPanel(m, rosterData.slots);
}
/* v1.14: a tracked operative from a roster shows the rules of its selected options (same name in the roster). */
function cardSheet(m, id) {
  const o = (m.operatives || []).find((x) => String(x.id) === id);
  if (!o) return "";
  const p = m.players.find((x) => x.slot === o.slot),
    r = m.demo ? null : rosterOf(m, o.slot, "card:" + id),
    ro = r?.operatives?.find((x) => x.name === o.name),
    card = ro
      ? {
          ...o,
          abilities: ro.abilities,
          actions: ro.actions,
          keywords: ro.keywords,
        }
      : o;
  return `<p class="eyebrow">${esc(p.display_name)} · ${o.wounds}/${o.wounds_max} ${esc(t("woundsShort"))}</p>${opCard(card, p.team_id)}${canEdit(m, p) ? `<div class="row">${button(t("opRemove"), "op-remove", "secondary small", `data-op="${o.id}" data-confirm="${esc(t("opRemoveConfirm"))}"`)}</div>` : ""}`;
}
/* «Undo last»: the server says what it would revert for this viewer (m.undo). */
function undoText(m, u) {
  const who = u.slot
      ? m.players.find((p) => p.slot === u.slot)?.display_name
      : "",
    tail = who ? " · " + who : "",
    comp = m.rules_snapshot?.sources?.[u.source_id];
  if (u.action === "score") {
    if (u.vp)
      return `${comp ? (comp === "crit" ? "Crit" : "Tac") : catName(u.source_id)} TP${u.turning_point}: ${u.vp[0] ?? 0}→${u.vp[1]} VP${tail}`;
    if (u.cp)
      return `CP TP${u.turning_point}: ${u.cp[0] ?? 0}→${u.cp[1]}${tail}`;
    return t("scoreChange") + tail;
  }
  if (u.action === "kills")
    return `${t("miniaturesKilled")} TP${u.turning_point}: ${u.delta?.[0] ?? 0}→${u.delta?.[1] ?? 0}${tail}`;
  if (u.action === "initiative")
    return `${t("initiativeLabel")} TP${u.turning_point}${tail}`;
  if (u.action === "cp_grant")
    return `${t("cpReady")} TP${u.turning_point}: ${m.players.map((p) => `${p.display_name} +${u.gains?.[p.slot] ?? 0}CP`).join(", ")}`;
  if (u.action === "ploy")
    return `${u.name} TP${u.turning_point} (${u.cost}CP)${tail}`;
  if (u.action === "turn") return `${t("turn")} ${u.turn?.[0]}→${u.turn?.[1]}`;
  if (u.action === "operative")
    return `${u.name || t("tracker")}: ${t("opChange_" + (u.change || "wounds"))}${u.wounds && u.wounds[0] != null && u.wounds[1] != null ? ` ${u.wounds[0]}→${u.wounds[1]}` : ""}`;
  return t(u.action);
}
function undoButton(m) {
  const u = m.undo;
  if (!u || m.status !== "active") return "";
  const text = undoText(m, u);
  return `<button type="button" class="secondary undo" data-action="undo" data-audit="${esc(u.id)}" title="${esc(t("undoLast") + ": " + text)}" aria-label="${esc(t("undoLast") + ": " + text)}">${icon("undo")}<span>${t("undoShort")}</span></button>`;
}
const ibutton = (ic, text, action, cls = "secondary", attrs = "") =>
  `<button type="button" class="${cls}" data-action="${action}" ${attrs}>${icon(ic)}<span>${esc(text)}</span></button>`;
const sourceOf = (m, comp) => {
  const hit = Object.entries(m.rules_snapshot?.sources || {}).find(
    ([, c]) => c === comp,
  );
  return hit ? +hit[0] : null;
};
const scoreAt = (m, p, sid, tp) =>
  m.scores.find(
    (s) =>
      s.player_id === p.id && s.turning_point === tp && s.source_id === sid,
  )?.vp || 0;
const canEdit = (m, p) =>
  m.status === "active" && (isHotseat(m) || p.user_id === me.id);
/* Per-TP caps: Crit from the frozen mission, Tac from the player's own card. A secret card on a shared screen
   (hot-seat) gives no hints: those cells use a plain counter instead of tokens. */
function capsOf(m, p, comp) {
  if (comp === "crit") return m.rules_snapshot?.mission?.per_turn_caps || null;
  if (isHotseat(m) && !p.tac_revealed && !ENDED.includes(m.status)) return null;
  return (
    catalogs.find((c) => c.id === p.tac_op_id)?.config.per_turn_caps || null
  );
}
function tokenCell(m, p, comp, tp, editable) {
  const sid = sourceOf(m, comp),
    caps = capsOf(m, p, comp),
    v = scoreAt(m, p, sid, tp),
    sa = slotAttr(m, p),
    total = Array.from({ length: m.turns }, (_, i) =>
      scoreAt(m, p, sid, i + 1),
    ).reduce((a, b) => a + b, 0),
    open = editable && tp <= m.current_turn,
    label = `${comp === "crit" ? "Crit" : "Tac"} · ${t("turn")} ${tp}`,
    cls = `cell ${tp === m.current_turn && m.status === "active" ? "now" : ""} ${tp > m.current_turn && m.status === "active" ? "later" : ""}`;
  if (caps && !caps[tp - 1] && !v)
    return `<td class="${cls} na" title="${esc(t("cellClosed"))}"><span class="sr-only">${label}: —</span></td>`;
  if (!caps) {
    if (!open)
      return `<td class="${cls}"><span class="cell-num" aria-hidden="true">${v || ""}</span><span class="sr-only">${label}: ${v}</span></td>`;
    return `<td class="${cls} step">${button("−", "score", "mini", `data-source="${sid}" data-tp="${tp}" data-delta="-1" ${sa} aria-label="${label}: −1" ${v ? "" : "disabled"}`)}<output>${v}</output>${button("+", "score", "mini", `data-source="${sid}" data-tp="${tp}" data-delta="1" ${sa} aria-label="${label}: +1" ${total >= 6 ? "disabled" : ""}`)}</td>`;
  }
  const n = Math.max(caps[tp - 1] || 0, v);
  const tokens = Array.from({ length: n }, (_, i) => {
    const k = i + 1,
      on = k <= v,
      target = v >= k ? k - 1 : k,
      delta = target - v;
    if (!open)
      return `<span class="token ${on ? "on" : ""}">${icon("skull")}</span>`;
    return `<button type="button" class="token ${on ? "on" : ""}" data-action="score" data-source="${sid}" data-tp="${tp}" data-delta="${delta}" ${sa} aria-pressed="${on}" aria-label="${label}: ${target} VP" ${delta > 0 && total + delta > 6 ? "disabled" : ""}>${icon("skull")}</button>`;
  }).join("");
  return `<td class="${cls}"><span class="tokens" ${open ? "" : `role="img" aria-label="${label}: ${v}"`}>${tokens}</span></td>`;
}
function killRow(m, p) {
  const other = m.players.find((x) => x.slot !== p.slot),
    g = p.grade || 0,
    bonus = g > (other.grade || 0),
    n = m.turns;
  return `<tr class="kill-row"><th scope="row">Kill</th><td colspan="${Math.max(1, n - 1)}" class="skulls"><span class="tokens" role="img" aria-label="${t("killGrade")}: ${g}">${Array.from({ length: 5 }, (_, i) => `<span class="token ${i < g ? "on" : ""}">${icon("skull")}</span>`).join("")}</span></td>${n > 1 ? `<td class="skulls bonus" title="${esc(t("killBonusHint"))}"><span class="tokens" role="img" aria-label="${esc(t("killBonusHint"))}: ${bonus ? 1 : 0}"><span class="token ${bonus ? "on" : ""} ${ENDED.includes(m.status) ? "" : "pending"}">${icon("skull")}</span></span></td>` : ""}</tr>`;
}
function tpHead(m, n) {
  return `<thead><tr><th></th>${Array.from({ length: n }, (_, i) => `<th scope="col" class="${i + 1 === m.current_turn && m.status === "active" ? "now" : ""}">TP${i + 1}</th>`).join("")}</tr></thead>`;
}
function tpGrid(m, p, editable) {
  if (m.scoring_mode !== "approved2025") return legacyGrid(m, p, editable);
  const n = m.turns;
  return `<div class="tp-wrap" ${editable ? "" : 'tabindex="0"'}><table class="tp-grid">${tpHead(m, n)}<tbody>${[
    "crit",
    "tac",
  ]
    .map(
      (comp) =>
        `<tr><th scope="row">${comp === "crit" ? "Crit" : "Tac"}</th>${Array.from({ length: n }, (_, i) => tokenCell(m, p, comp, i + 1, editable)).join("")}</tr>`,
    )
    .join("")}${killRow(m, p)}</tbody></table></div>`;
}
/* Legacy/guest scoring: one row per VP source, ± in the current turning point. */
function legacyGrid(m, p, editable) {
  const n = m.kind === "guest" ? 1 : m.turns,
    sa = slotAttr(m, p);
  return `<div class="tp-wrap" ${editable ? "" : 'tabindex="0"'}><table class="tp-grid legacy">${tpHead(m, n)}<tbody>${matchSources(
    m,
  )
    .map(
      (s) =>
        `<tr><th scope="row">${esc(s.label)}</th>${Array.from(
          { length: n },
          (_, i) => {
            const tp = i + 1,
              v = scoreAt(m, p, s.id, tp);
            return editable && tp === m.current_turn
              ? `<td class="cell now step">${button("−", "score", "mini", `data-source="${s.id}" data-tp="${tp}" data-delta="-1" ${sa} aria-label="−1 VP: ${esc(s.label)}" ${v ? "" : "disabled"}`)}<output>${v}</output>${button("+", "score", "mini", `data-source="${s.id}" data-tp="${tp}" data-delta="1" ${sa} aria-label="+1 VP: ${esc(s.label)}"`)}</td>`
              : `<td class="cell"><span class="cell-num">${v || ""}</span></td>`;
          },
        ).join("")}</tr>`,
    )
    .join("")}</tbody></table></div>`;
}
function cpBox(m, p, editable) {
  const st = cpState(m, p, m.current_turn),
    sa = slotAttr(m, p);
  /* v1.14: «Ploy» — spend CP on a ploy of the team or Command Re-roll (recorded in the protocol). */
  const ploy =
    editable && m.status === "active" && !m.demo
      ? `<button type="button" class="mini ploy-open" data-action="ploys-open" data-slot="${p.slot}" aria-label="${esc(t("ploys") + ": " + p.display_name)}">${icon("bolt")}<span>${t("ploys")}</span></button>`
      : "";
  return `<div class="box cp-box"><span class="box-label">CP</span><div class="cp-body"><output class="big ${changed(m, "cp", p.slot, st.cp)}" aria-label="CP">${st.cp}</output>${
    editable
      ? `<div class="pm">${button("+", "cp", "mini", `data-value="${st.cp + 1}" ${sa} aria-label="+1 CP" ${st.cp >= 99 ? "disabled" : ""}`)}${button("−", "cp", "mini", `data-value="${st.cp - 1}" ${sa} aria-label="−1 CP" ${st.cp ? "" : "disabled"}`)}</div>`
      : ""
  }</div>${ploy}${st.carried ? `<small class="muted">${t("cpCarried")}</small>` : ""}</div>`;
}
function tacChip(m, p, editable) {
  const tac = catalogs.find((c) => c.id === p.tac_op_id),
    hs = isHotseat(m),
    ended = ENDED.includes(m.status),
    sa = slotAttr(m, p);
  let chip;
  if (tac && (p.tac_revealed || ended))
    chip = `<details class="chip"><summary>${icon("flag")}<span>${esc(tac.label)}</span></summary><p class="muted">${esc(tac.config.reveal || "")}</p><p>${esc(tac.config.summary || "")}</p></details>`;
  else if (tac)
    chip = `<details class="chip secret"><summary>${icon("lock")}<span>${hs ? t("tacHidden") : esc(tac.label)}</span></summary>${hs ? `<p><b>${esc(tac.label)}</b></p>` : ""}<p class="muted">${esc(tac.config.reveal || "")}</p><p>${esc(tac.config.summary || "")}</p></details>`;
  else
    chip = `<span class="chip secret">${icon("lock")}<span>${p.secret_set ? t("tacHidden") : "—"}</span></span>`;
  const reveal =
    editable && !p.tac_revealed && p.secret_set
      ? button(
          t("revealShort"),
          "reveal-tac",
          "mini text",
          `${sa} aria-label="${esc(t("revealTac"))}"`,
        )
      : "";
  return `<div class="chip-row">${chip}${reveal}</div>`;
}
function primaryChip(m, p, editable) {
  const hs = isHotseat(m),
    ended = ENDED.includes(m.status),
    mine = p.user_id === me?.id;
  if (ended && p.primary_op)
    return `<span class="chip primary">${icon("shield")}<span>${esc(t("op_" + p.primary_op))} +${p.primary_bonus}</span></span>`;
  if (p.primary_committed)
    return `<span class="chip primary fixed">${icon("shield")}<span>${!hs && mine && p.primary_op ? esc(t("op_" + p.primary_op)) + " · " : ""}${t("primaryFixedShort")}</span></span>`;
  if (!editable)
    return `<span class="chip primary">${icon("shield")}<span>${t("primaryOpen")}</span></span>`;
  const id = hs ? "primary-active-" + p.slot : "primary-active",
    tp1 = m.current_turn === 1;
  return `<div class="primary-pick ${tp1 ? "" : "late"}"><label class="sr-only" for="${id}">${t("primaryOp")}</label><select id="${id}" aria-label="${esc(t("primaryOp"))}">${primaryOptions()
    .map(
      (o) =>
        `<option value="${o.id}" ${o.id === p.primary_op ? "selected" : ""}>${esc(o.label)}</option>`,
    )
    .join(
      "",
    )}</select>${ibutton("shield", t("primaryShort"), "primary-commit", "mini", `${slotAttr(m, p)} title="${esc(t("commitPrimary"))}" aria-label="${esc(t("primaryShort"))}: ${esc(t("commitPrimary"))}" ${tp1 ? "" : "disabled"}`)}${tp1 ? "" : `<small class="warning-text">${t("primaryLate")}</small>`}</div>`;
}
function killsBox(m, p, editable) {
  const other = m.players.find((x) => x.slot !== p.slot),
    sa = slotAttr(m, p),
    max = other.operative_count ?? 40,
    // v1.9: the opponent tracks their operatives — kills follow from incapacitated operatives.
    auto = tracked(m, other.slot),
    step = editable && !auto;
  return `<div class="box kill-box"><span class="box-label">${t("enemyOperativesShort")}: <b>${other.operative_count ?? "—"}</b></span><div class="kill-step">${step ? button("−", "kills", "mini", `data-delta="-1" ${sa} aria-label="${esc(t("killMinus"))}" ${p.incapacitated > 0 ? "" : "disabled"}`) : ""}<span class="kill-num"><output class="${changed(m, "kills", p.slot, p.incapacitated)}" aria-label="${esc(t("miniaturesKilled"))}">${p.incapacitated}</output><small>${t("miniaturesKilled")}</small></span>${step ? button("+", "kills", "mini", `data-delta="1" ${sa} aria-label="${esc(t("killPlus"))}" ${p.incapacitated < max ? "" : "disabled"}`) : ""}</div>${auto ? `<small class="auto-note">${icon("heart")}${t("killsAuto")}</small>` : ""}</div>`;
}
function notesBox(m, p, editable) {
  if (!editable) return "";
  const st = cpState(m, p, m.current_turn);
  return `<details class="tp-notes" ${st.notes ? "open" : ""}><summary>${t("notes")} · TP${m.current_turn}</summary><form class="turn-notes-form" id="turn-notes-form-${p.slot}" ${slotAttr(m, p)}><textarea name="notes" maxlength="2000" aria-label="${esc(t("notes"))}">${esc(st.notes)}</textarea><button class="secondary">${t("save")}</button></form></details>`;
}
function boardHalf(m, p, leader, bump) {
  const editable = canEdit(m, p),
    ops = m.scoring_mode === "approved2025",
    who = isHotseat(m)
      ? t("player") + " " + p.slot
      : p.user_id === me?.id
        ? t("yours")
        : t("opponent");
  return `<section class="half slot-${p.slot} ${leader ? "leader" : ""} ${editable ? "editable" : "readonly"}" aria-label="${esc(p.display_name)}"><header class="half-banner"><span class="emblem">${teamEmblem(p.team_id, p.display_name)}</span><div class="half-id"><span class="eyebrow">${esc(who)}${m.status === "active" && initiativeOf(m, m.current_turn) === p.slot ? ` · ★ ${t("initiativeLabel")}` : ""}</span><b class="player-name">${esc(p.display_name)}</b><small>${m.demo ? "" : teamLabel(p.team_id)}</small></div><span class="half-vp"><b class="${bump}">${p.vp}</b><small>VP</small></span></header>${!editable && m.status === "active" && !isHotseat(m) ? `<p class="half-note">${icon("lock")}${t("opponentReadOnly")}</p>` : ""}${m.kind === "guest" ? "" : `${tpGrid(m, p, editable)}<div class="half-bottom ${ops ? "" : "simple"}">${cpBox(m, p, editable)}${ops ? `<div class="box ops-box">${m.demo ? "" : tacChip(m, p, editable)}${primaryChip(m, p, editable)}</div>${killsBox(m, p, editable)}` : ""}</div>${equipmentBox(m, p)}${trackerBlock(m, p, editable)}`}${ops ? `<p class="ops-line muted">Crit ${p.crit} · Tac ${p.tac} · Kill ${p.kill} · ${t("primaryShort")} +${p.primary_bonus}</p>` : ""}${notesBox(m, p, editable)}${leader && ENDED.includes(m.status) ? badge(m.status === "confirmed" ? "winner" : "leader") : ""}</section>`;
}
/* Clock between the halves: each side has its time and a hexagonal play button. */
export function clockBoard(m) {
  setClock(m.id, m.clock);
  if (!clockData || clockData.id !== m.id) return "";
  const s = clockData.state,
    live = m.status === "active",
    players = ordered(m);
  if (!s.mode && !live) return "";
  if (!s.mode)
    return `<div class="clock-board off" id="clock-panel">${ibutton("clock", t("clockSetup"), "board-panel", "secondary small", 'data-panel="clock"')}</div>`;
  const hex = (p) => {
    const on = s.running && s.active_slot === p.slot,
      name = esc(p.display_name);
    if (!live)
      return `<span class="hex slot-${p.slot}" aria-hidden="true">${icon("play")}</span>`;
    if (on)
      return `<button type="button" class="hex slot-${p.slot} on" data-action="clock" data-cmd="switch" data-slot="${p.slot}" aria-label="${name}: ${esc(t("clockPass"))}">${icon("pass")}</button>`;
    if (s.running)
      return `<button type="button" class="hex slot-${p.slot}" disabled aria-label="${name}: ${esc(t("clockWaiting"))}">${icon("play")}</button>`;
    return `<button type="button" class="hex slot-${p.slot}" data-action="clock" data-cmd="start" data-slot="${p.slot}" aria-label="${esc(t("clockStart"))}: ${name}">${icon("play")}</button>`;
  };
  const middle = `<div class="clock-mid">${s.mode === "stopwatch" ? `<span class="clock-big">${clockTime("total")}</span>` : `<small>${t("clockTotal")} ${clockTime("total")}</small>`}<span class="clock-mode">${esc(t("clockMode_" + s.mode))}${live && !s.running ? " · " + esc(t("clockPaused")) : ""}</span>${live && s.running ? ibutton("pause", t("clockPause"), "clock", "mini", 'data-cmd="pause"') : ""}</div>`;
  if (s.mode === "stopwatch")
    return `<div class="clock-board stopwatch ${s.running ? "running" : ""}" id="clock-panel">${middle}${live && !s.running ? `<button type="button" class="hex" data-action="clock" data-cmd="start" aria-label="${esc(t(s.started ? "clockResume" : "clockStart"))}">${icon("play")}</button>` : ""}</div>`;
  const side = (p) =>
    `<div class="clock-side slot-${p.slot} clock-tile ${s.running && s.active_slot === p.slot ? "on" : ""} ${s.mode === "countdown" ? "countdown" : ""}">${hex(p)}<span class="clock-num">${clockTime("slot", p.slot)}<small class="clock-over">${t("clockOvertime")}</small></span></div>`;
  return `<div class="clock-board ${s.running ? "running" : ""}" id="clock-panel">${side(players[0])}${middle}${side(players[1])}</div>`;
}
function clockSheet(m) {
  const s = clockData?.id === m.id ? clockData.state : m.clock || {};
  return `<h2>${t("clockSettings")}</h2><p class="muted">${t("clockHint")}</p>${s.running ? `<p class="muted">${t("clockPauseFirst")}</p>` : clockForm(s)}${!s.running && s.started ? `<div class="row">${button(t("clockReset"), "clock-reset", "secondary")}</div>` : ""}`;
}
/* v1.13: conceding — the player who concedes gets 0, the opponent 10 (view player_totals); a friend confirms
   it like a finished match, a hot-seat match ends at once. Online only (the result is not queued offline). */
function concedePanel(m) {
  const off = isDown(),
    own = m.players.find((p) => !!me && p.user_id === me.id),
    btn = (p, label) =>
      button(
        label,
        "match-action",
        "danger",
        `data-kind="concede" data-slot="${p.slot}" ${off ? "disabled" : ""}`,
      ),
    buttons = isHotseat(m)
      ? m.players
          .map((p) => btn(p, t("concedeAs").replace("{name}", p.display_name)))
          .join("")
      : own
        ? btn(own, t("concede"))
        : "";
  return `<h2>${icon("surrender")} ${t("concede")}</h2><p>${t(isHotseat(m) ? "concedeHotseatHint" : "concedeHint")}</p>${off ? `<p class="warning">${t("concedeOffline")}</p>` : ""}<div class="row">${buttons}</div>`;
}
function concededNote(m) {
  const loser = m.players.find((p) => p.slot === m.conceded_slot),
    winner = m.players.find((p) => p.slot !== m.conceded_slot);
  return loser && winner
    ? `<p class="concede-note">${icon("surrender")}<span>${esc(t("concededText").replace("{name}", loser.display_name).replace("{other}", winner.display_name))}</span></p>`
    : "";
}
function resultPanel(m) {
  if (m.status === "active") return "";
  return `<section class="panel result-panel">${m.conceded_slot ? concededNote(m) : ""}${
    m.status === "awaiting_confirmation"
      ? m.submitted_by === me.id
        ? `<p>${t("waiting")}</p>${m.recorded_result ? button(t("cancelMatch"), "cancel-match", "secondary") : ""}`
        : `<div class="row">${button(t("confirm"), "match-action", "", `data-kind="confirm"`)}${button(t("dispute"), "match-action", "secondary", `data-kind="dispute"`)}</div>`
      : m.status === "disputed"
        ? m.recorded_result
          ? `<p>${t("recordedDisputed")}</p>${m.created_by === me.id ? button(t("cancelMatch"), "cancel-match", "secondary") : ""}`
          : `<p>${t("disputedText")}</p>${button(t("reopen"), "match-action", "", `data-kind="reopen"`)}`
        : `<p>${t(m.status === "cancelled" ? "cancelledText" : m.kind === "guest" ? "guestText" : m.kind === "hotseat" ? "hotseatText" : "confirmedText")}</p>`
  }</section>`;
}
function scoreTable(m) {
  return `<section class="panel"><details class="score-table"><summary>${t("scoreTable")}</summary><div class="table-wrap" tabindex="0"><table><thead><tr><th>${t("turn")}</th><th>${t("name")}</th><th>${t("score")}</th><th>CP / ${t("notes")}</th><th>${t("initiativeLabel")}</th></tr></thead><tbody>${Array.from(
    { length: m.kind === "guest" ? 1 : m.turns },
    (_, i) =>
      ordered(m).map((p) => {
        const state = m.turn_states.find(
          (x) => x.player_id === p.id && x.turning_point === i + 1,
        );
        return `<tr><td>${i + 1}</td><td>${esc(p.display_name)}</td><td>${
          m.scores
            .filter((s) => s.player_id === p.id && s.turning_point === i + 1)
            .map((s) => esc(catName(s.source_id)) + ": " + s.vp)
            .join("<br>") || "0"
        }</td><td>${i + 1 <= m.current_turn ? cpState(m, p, i + 1).cp : state?.cp || 0}<br>${esc(state?.notes || "")}${ploysAt(m, p, i + 1).length ? `<br><small class="muted">${esc(ploysAt(m, p, i + 1).join(", "))}</small>` : ""}</td><td>${initiativeOf(m, i + 1) === p.slot ? `<span aria-label="${t("initiativeLabel")}">★</span>` : ""}</td></tr>`;
      }),
  )
    .flat()
    .join(
      "",
    )}</tbody></table></div>${m.notes ? `<p>${esc(m.notes)}</p>` : ""}${m.setup.rule_notes ? `<p class="muted">${esc(m.setup.rule_notes)}</p>` : ""}<h3>${t("roster")}</h3>${m.players.map((p) => `<h4>${esc(p.display_name)} · ${p.operative_count || "—"}</h4><p class="pre">${esc(p.roster) || "—"}</p>`).join("")}</details></section>`;
}
function featuresMenu(m) {
  const live = m.status === "active",
    ended = ENDED.includes(m.status),
    demo = !!m.demo,
    item = (ic, k, panel, extra = "") =>
      ibutton(
        ic,
        t(k),
        "board-panel",
        "menu-item",
        `data-panel="${panel}" role="menuitem" ${extra}`,
      );
  return `<details class="menu" id="board-menu"><summary class="button secondary">${icon("menu")}<span>${t("features")}</span></summary><div class="menu-list" role="menu">${[
    demo
      ? ""
      : `<a class="menu-item" href="#demo" role="menuitem">${icon("play")}<span>${t("featureDemo")}</span></a>`,
    ibutton(
      "swap",
      t("swapSides"),
      "swap",
      "menu-item",
      `role="menuitem" aria-pressed="${isSwapped(m)}"`,
    ),
    ibutton(
      "table",
      t("tabletop"),
      "tabletop",
      "menu-item",
      `role="menuitemcheckbox" aria-checked="${isTabletop()}" title="${esc(t("tabletopHint"))}"`,
    ),
    !demo && (live || m.clock?.mode)
      ? item("clock", "clockSettings", "clock")
      : "",
    item("dice", "diceRoller", "dice"),
    item("target", "attackCalc", "attack"),
    demo ? "" : item("list", "rostersPanel", "roster"),
    catalogDetail(m.mission_id) ? item("book", "missionRules", "rules") : "",
    live ? item("star", "initiativeLabel", "initiative") : "",
    ploysOn(m) ? item("bolt", "ploys", "ploys") : "",
    ended && !demo
      ? ibutton(
          "share",
          t("shareResult"),
          "board-scroll",
          "menu-item",
          'data-target="#share-panel" role="menuitem"',
        )
      : "",
    live ? item("flag", "finishGame", "finish") : "",
    live && !demo ? item("surrender", "concede", "concede") : "",
  ].join("")}</div></details>`;
}
function boardSheet(m) {
  const live = m.status === "active",
    p = boardPanel;
  if (!p) return "";
  let body = "";
  if (p === "dice")
    body = `<h2>${t("diceRoller")}</h2><div id="dice-panel" class="dice"><div id="dice-body">${diceBody()}</div></div>`;
  else if (p === "clock" && (live || m.clock?.mode)) body = clockSheet(m);
  else if (p === "rules")
    body = catalogDetail(m.mission_id).replace("<details>", "<details open>");
  else if (p === "initiative" && live)
    body = initiativeBlock(m) || `<p class="muted">${t("initiativeHint")}</p>`;
  else if (p === "attack") body = attackPanel(m);
  else if (p === "ploys" && ploysOn(m)) body = ploysPanel(m);
  else if (p === "roster" && !m.demo) body = rosterSheetBody(m);
  else if (p === "concede" && live && !m.demo) body = concedePanel(m);
  else if (p.startsWith("card:")) body = cardSheet(m, p.slice(5));
  else if (p === "finish" && live)
    return `<div class="board-sheet" id="board-sheet">${button("×", "board-panel", "sheet-close", `data-panel="" aria-label="${esc(t("closePanel"))}"`)}${finishPanel(m, m.demo ? "demoFinishHint" : isHotseat(m) ? "hotseatFinishHint" : "finishHint")}</div>`;
  else return "";
  if (!body) return "";
  return `<div class="board-sheet panel" id="board-sheet">${button("×", "board-panel", "sheet-close", `data-panel="" aria-label="${esc(t("closePanel"))}"`)}${body}</div>`;
}
export function drawBoard(m) {
  const players = ordered(m),
    live = m.status === "active",
    leader =
      m.players[0].vp === m.players[1].vp
        ? null
        : m.players.reduce((a, b) => (a.vp > b.vp ? a : b)),
    undecided = live && !initiativeOf(m, m.current_turn),
    bump = Object.fromEntries(
      m.players.map((p) => [p.slot, changed(m, "vp", p.slot, p.vp)]),
    );
  if (m.recorded_result)
    return `<section class="panel recorded-score"><h2>${t("total")}</h2><div class="row">${players.map((p) => `<div><strong>${esc(p.display_name)}</strong> <b class="accent">${p.vp}</b><br><span class="muted">${teamLabel(p.team_id)}</span></div>`).join("<span>—</span>")}</div>${m.notes ? `<p>${esc(m.notes)}</p>` : ""}</section>${resultPanel(m)}${sharePanel(m)}`;
  if (!m.demo) ensureCards(m);
  return `<section class="board ${isTabletop() ? "tabletop" : ""}" aria-label="${esc(t("scoreboard"))}"><div class="board-bar"><div class="bar-top"><span class="tp-title">${t(m.kind === "guest" ? "total" : "turningPoint")}</span><span class="board-score" aria-label="${esc(t("score"))}">${players.map((p) => `<b class="slot-${p.slot} ${bump[p.slot]}">${p.vp}</b>`).join("<i>–</i>")}</span></div><div class="bar-controls"><div class="turns" role="group" aria-label="${esc(t("turn"))}">${m.kind === "guest" ? "" : turnButtons(m, !live)}${live ? button(t("tpEnd"), "board-panel", boardPanel === "finish" ? "selected" : "secondary", 'data-panel="finish"') : ""}</div>${undoButton(m)}${featuresMenu(m)}</div></div>${boardSheet(m)}${(undecided || cpPending(m)) && boardPanel !== "initiative" ? initiativeBlock(m) : ""}<div class="halves">${boardHalf(m, players[0], leader?.id === players[0].id, bump[players[0].slot])}${m.demo ? "" : clockBoard(m)}${boardHalf(m, players[1], leader?.id === players[1].id, bump[players[1].slot])}</div>${live ? `<p class="muted board-hint">${t(isHotseat(m) ? "hotseatShared" : "opponentReadOnly")}</p>` : ""}</section>${m.demo ? "" : resultPanel(m) + sharePanel(m) + scoreTable(m)}`;
}

/* v1.9: listeners are registered from main.js in a fixed order (the former <script> order). */
export function init() {
  app.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-action]");
    if (!b || !currentMatch) return;
    const a = b.dataset.action;
    if (b.closest("#board-menu")) b.closest("#board-menu").open = false;
    if (
      [
        "score",
        "cp",
        "kills",
        "initiative",
        "turn",
        "cp-grant",
        "ploy-use",
      ].includes(a)
    )
      tap();
    if (a === "undo") {
      if (b.disabled) return;
      b.disabled = true;
      tap();
      try {
        await updateMatch("/undo", { audit_id: +b.dataset.audit }, false);
      } catch (err) {
        notify(err.message);
      } finally {
        b.disabled = false;
      }
    } else if (a === "tabletop") {
      try {
        if (isTabletop()) localStorage.removeItem(TABLETOP_KEY);
        else localStorage.setItem(TABLETOP_KEY, "1");
      } catch {}
      drawMatch(currentMatch);
    } else if (a === "print-roster")
      await printMatchRoster(currentMatch, +b.dataset.slot);
    else if (a === "board-panel") {
      const next = b.dataset.panel || null;
      boardPanel = boardPanel === next ? null : next;
      if (boardPanel === "dice") dice.open = true;
      drawMatch(currentMatch);
      if (boardPanel)
        document
          .querySelector("#board-sheet")
          ?.scrollIntoView({ block: "nearest" });
    } else if (a === "board-scroll")
      document
        .querySelector(b.dataset.target)
        ?.scrollIntoView({ block: "start", behavior: "smooth" });
  });
  document.addEventListener("click", (e) => {
    const menu = document.querySelector("#board-menu[open]");
    if (menu && !menu.contains(e.target)) menu.open = false;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const menu = document.querySelector("#board-menu[open]");
      if (menu) {
        menu.open = false;
        menu.querySelector("summary")?.focus();
      }
    }
  });
}
