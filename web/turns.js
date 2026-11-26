import { api, app, button, esc, notify, t } from "./core.js";
import { currentMatch, drawMatch, updateMatch } from "./app.js";
import { rollOffButton } from "./dice.js";
import { isHotseat } from "./quickstart.js";
/* v1.3 — turning points: initiative, final count preview, client-only seat swap, CP carry-over.
   v1.14: the CP of the Ready step with one tap in the initiative block. */
let finalPreview = null;
const swapKey = (m) => "killstass-swap-" + m.id;
export const isSwapped = (m) => localStorage.getItem(swapKey(m)) === "1";
export const ordered = (m) =>
  isSwapped(m) ? [...m.players].reverse() : m.players;
/* TP1 falls back to the setup choice; later TPs need an explicit roll-off record. */
export const initiativeOf = (m, tp) =>
  (m.initiatives || []).find((x) => x.turning_point === tp)?.slot ||
  (tp === 1 && m.initiative) ||
  null;
const playerBySlot = (m, slot) => m.players.find((p) => p.slot === slot);
/* CP is a running resource: show the last known value when this TP has no saved state yet. */
export function cpState(m, player, tp) {
  const own = m.turn_states.find(
    (s) => s.player_id === player.id && s.turning_point === tp,
  );
  if (own) return { cp: own.cp, notes: own.notes, carried: false };
  const prev = m.turn_states
    .filter((s) => s.player_id === player.id && s.turning_point < tp)
    .sort((a, b) => b.turning_point - a.turning_point)[0];
  return { cp: prev?.cp || 0, notes: "", carried: !!prev };
}
export function turnButtons(m, readonly) {
  return Array.from({ length: m.turns }, (_, i) => {
    const tp = i + 1,
      slot = initiativeOf(m, tp),
      who = slot ? playerBySlot(m, slot).display_name : "";
    return button(
      String(tp),
      "turn",
      tp === m.current_turn ? "selected" : "secondary",
      `data-value="${tp}" ${slot ? `data-mark="★${esc(who.slice(0, 1).toUpperCase())}" title="${esc(t("initiativeLabel") + ": " + who)}"` : ""} aria-label="${t("turn")} ${tp}${slot ? ", " + esc(t("initiativeLabel") + ": " + who) : ""}" ${readonly ? "disabled" : ""}`,
    );
  }).join("");
}
/* v1.14: the Ready step of the Strategy phase (Kill Team 2024) — CP for the current turning point with one tap,
   once per TP: +1 each; from TP2 the player who doesn't have initiative gains 2CP instead. */
export const cpGranted = (m, tp = m.current_turn) =>
  (m.cp_grants || []).some((g) => g.turning_point === tp);
export const cpPending = (m) =>
  m.status === "active" &&
  m.edition === "2024" &&
  m.kind !== "guest" &&
  !m.demo &&
  !cpGranted(m);
function cpGrantRow(m, slot) {
  const tp = m.current_turn;
  if (!cpPending(m)) return "";
  if (!slot)
    return `<p class="muted cp-grant-hint">${t("cpAfterInitiative")}</p>`;
  const gains = tp === 1 ? { 1: 1, 2: 1 } : { [slot]: 1, [3 - slot]: 2 },
    text = ordered(m)
      .map((p) => `${p.display_name} +${gains[p.slot]}CP`)
      .join(", ");
  return `<div class="cp-grant"><span>${esc(t("cpReady"))}: <b>${esc(text)}</b></span>${button(t("cpGrant"), "cp-grant", "", `data-tp="${tp}" aria-label="${esc(t("cpGrant") + " (" + t("turn") + " " + tp + "): " + text)}"`)}</div>`;
}
export function initiativeBlock(m) {
  const tp = m.current_turn,
    slot = initiativeOf(m, tp),
    active = m.status === "active";
  if (!active && !slot) return "";
  const choices = ordered(m)
    .map((p) =>
      button(
        p.display_name,
        "initiative",
        p.slot === slot ? "selected" : "secondary",
        `data-slot="${p.slot}" aria-pressed="${p.slot === slot}" ${!active ? "disabled" : ""}`,
      ),
    )
    .join("");
  return slot
    ? `<div class="initiative"><span>${t("initiativeLabel")}: <b>${esc(playerBySlot(m, slot).display_name)}</b></span>${active ? `<details><summary>${t("initiativeChange")}</summary><div class="row">${choices}</div></details>` : ""}${cpGrantRow(m, slot)}</div>`
    : `<div class="initiative initiative-prompt" role="group" aria-label="${t("initiativeAsk")}"><b>${t("initiativeAsk")} (${t("turn")} ${tp})</b><p class="muted">${t("initiativeHint")}</p><div class="row">${choices}</div>${rollOffButton(m.id + "-" + tp)}${cpGrantRow(m, null)}</div>`;
}
function previewTable(m, d) {
  const hidden = isHotseat(m);
  const rows = ordered(m).map((p) => d.players.find((x) => x.slot === p.slot));
  if (d.scoring_mode !== "approved2025")
    return `<table><thead><tr><th>${t("player")}</th><th>VP</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.display_name)}</td><td><b>${r.vp}</b></td></tr>`).join("")}</tbody></table>`;
  const primary = (r) =>
    hidden || r.primary_bonus === null
      ? `<span class="muted">${t(hidden ? "afterFinish" : "hiddenUntilFinish")}</span>`
      : !r.primary_committed
        ? `<span class="muted">${t("primaryNotChosen")}</span>`
        : `+${r.primary_bonus} (${esc(t("op_" + r.primary_op))})`;
  const total = (r) =>
    hidden || r.vp === null ? `${r.base} + ?` : String(r.vp);
  return `<table><thead><tr><th>${t("player")}</th><th>Crit</th><th>Tac</th><th>Kill</th><th title="${t("primaryBonus")}">${t("primaryShort")}</th><th>${t("total")}</th></tr></thead><tbody>${rows
    .map(
      (r) =>
        `<tr><td>${esc(r.display_name)}</td><td>${r.crit}</td><td>${r.tac}</td><td>${r.kill}${r.kill_bonus ? ` <span class="muted">(${t("killBonusShort")})</span>` : ""}</td><td>${primary(r)}</td><td><b>${total(r)}</b></td></tr>`,
    )
    .join("")}</tbody></table>`;
}
export function finishPanel(m, hintKey) {
  const last = m.current_turn === m.turns,
    d =
      finalPreview &&
      finalPreview.id === m.id &&
      finalPreview.version === m.version
        ? finalPreview.data
        : null;
  const label = m.demo ? "demoFinish" : "finish";
  const finishBtn = button(
    t(label),
    "match-action",
    last && !d ? "secondary" : "",
    `data-kind="finish"`,
  );
  return `<section class="panel final-count"><h2>${t(last ? "finalCount" : label)}</h2><p class="muted">${t(last ? "finalCountHint" : hintKey)}</p>${
    d
      ? `<div class="table-wrap" tabindex="0">${previewTable(m, d)}</div><p class="muted small">${t("previewLegend")}</p>${!d.ready ? `<p class="warning">${t("previewNotReady")}</p>` : ""}<p class="muted">${t(hintKey)}</p>`
      : ""
  }<div class="row">${last ? button(t(d ? "recount" : "finalCount"), "preview", d ? "secondary" : "") : ""}${finishBtn}</div></section>`;
}

/* v1.9: listeners are registered from main.js in a fixed order (the former <script> order). */
export function init() {
  app.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b || b.disabled || !currentMatch) return;
    const a = b.dataset.action;
    if (!["initiative", "swap", "preview", "cp-grant"].includes(a)) return;
    b.disabled = true;
    try {
      if (a === "cp-grant")
        await updateMatch("/cp", { turning_point: +b.dataset.tp });
      else if (a === "initiative")
        await updateMatch("/initiative", {
          turning_point: currentMatch.current_turn,
          slot: +b.dataset.slot,
        });
      else if (a === "swap") {
        if (isSwapped(currentMatch))
          localStorage.removeItem(swapKey(currentMatch));
        else localStorage.setItem(swapKey(currentMatch), "1");
        drawMatch(currentMatch);
      } else if (a === "preview") {
        const m = currentMatch;
        finalPreview = {
          id: m.id,
          version: m.version,
          data: m.demo
            ? m.demo.preview(m)
            : await api("/matches/" + m.id + "/preview"),
        };
        drawMatch(currentMatch);
        document
          .querySelector(".final-count")
          ?.scrollIntoView({ block: "nearest" });
      }
    } catch (err) {
      notify(err.message);
    } finally {
      b.disabled = false;
    }
  });
}
