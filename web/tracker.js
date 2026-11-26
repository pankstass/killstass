import { app, button, esc, icon, notify, t } from "./core.js";
import { currentMatch, updateMatch } from "./app.js";
import { isHotseat, slotAttr } from "./quickstart.js";
import { cachedTeam } from "./teams.js";
/* v1.9 — operative tracker on the board: wounds, Engage/Conceal, activation per turning point and
   incapacitation. Tracker commands carry no match version (see api/tracker.py); kills of the opponent's
   Kill Op follow automatically from operatives reaching 0 wounds. */
const opened = {};
export const opsOf = (m, slot) =>
  (m.operatives || [])
    .filter((o) => o.slot === slot)
    .sort((a, b) => a.position - b.position);
export const injured = (o) => o.wounds > 0 && o.wounds < o.wounds_max / 2;
export const tracked = (m, slot) => opsOf(m, slot).length > 0;
export const tap = () => {
  try {
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches)
      navigator.vibrate?.(12);
  } catch {}
};
function pips(o) {
  const n = o.wounds_max;
  if (n > 30) return `<span class="wnum">${o.wounds}/${n}</span>`;
  return `<span class="pips" aria-hidden="true">${Array.from({ length: n }, (_, i) => `<i class="${i < o.wounds ? "on" : ""}"></i>`).join("")}</span>`;
}
function opRow(m, o, editable) {
  const tp = m.current_turn,
    down = o.wounds === 0,
    act = o.activated_tp === tp,
    hurt = injured(o),
    label = `${o.name}: ${o.wounds}/${o.wounds_max}`,
    order = o.order_token,
    next = order === "engage" ? "conceal" : "engage";
  const controls = editable
    ? `<div class="op-controls">${button("−", "op-wound", "mini", `data-op="${o.id}" data-delta="-1" aria-label="${esc(o.name)}: −1 ${esc(t("woundsShort"))}" ${down ? "disabled" : ""}`)}${button("+", "op-wound", "mini", `data-op="${o.id}" data-delta="1" aria-label="${esc(o.name)}: +1 ${esc(t("woundsShort"))}" ${o.wounds >= o.wounds_max ? "disabled" : ""}`)}${down ? "" : `<button type="button" class="mini op-down" data-action="op-wound" data-op="${o.id}" data-delta="${-o.wounds}" aria-label="${esc(t("opIncapacitate"))}: ${esc(o.name)}" title="${esc(t("opIncapacitate"))}">${icon("skull")}</button>`}<button type="button" class="mini order ${order || ""}" data-action="op-order" data-op="${o.id}" data-order="${next}" aria-label="${esc(t("opOrder"))}: ${esc(order ? t("order_" + order) : "—")} → ${esc(t("order_" + next))}" ${down ? "disabled" : ""}>${icon(order === "conceal" ? "eye" : "bolt")}<span>${order ? esc(t("order_" + order)) : "—"}</span></button><button type="button" class="mini act ${act ? "on" : ""}" data-action="op-activate" data-op="${o.id}" data-on="${!act}" aria-pressed="${act}" aria-label="${esc(t("opActivated"))} · TP${tp}: ${esc(o.name)}" ${down ? "disabled" : ""}>${icon("check")}<span>TP${tp}</span></button></div>`
    : `<div class="op-controls readonly">${order ? `<span class="chip order ${order}">${esc(t("order_" + order))}</span>` : ""}${act ? `<span class="chip">${icon("check")} TP${tp}</span>` : ""}</div>`;
  return `<li class="op ${down ? "down" : ""} ${hurt ? "injured" : ""} ${act ? "activated" : ""}" data-op="${o.id}"><div class="op-main"><button type="button" class="op-name text" data-action="board-panel" data-panel="card:${o.id}"><span class="sr-only">${esc(t("datacard"))}: </span><b>${esc(o.name)}</b>${o.card && o.card !== o.name ? ` <small>${esc(o.card)}</small>` : ""}</button><span class="op-w" role="img" aria-label="${esc(label)}">${pips(o)}<b class="wnum">${o.wounds}</b><small>/${o.wounds_max}</small></span>${down ? `<span class="badge down">${icon("skull")}${esc(t("opDown"))}${o.incapacitated_tp ? " · TP" + o.incapacitated_tp : ""}</span>` : hurt ? `<span class="badge injured">${esc(t("opInjured"))}</span>` : ""}</div>${controls}</li>`;
}
const teamCards = (p) => cachedTeam(p?.team_id)?.data?.operatives || [];
function addForm(m, p) {
  const cards = [...new Set(teamCards(p).map((c) => c.name))];
  return `<details class="op-add"><summary>${icon("plus")}${t("opAdd")}</summary><form class="op-add-form row" ${slotAttr(m, p)} data-slot-id="${p.slot}"><label>${t("opName")}<input name="name" maxlength="80" list="op-cards-${p.slot}"></label><datalist id="op-cards-${p.slot}">${cards.map((c) => `<option value="${esc(c)}"></option>`).join("")}</datalist><label>${t("woundsShort")}<input name="wounds_max" type="number" min="1" max="99" inputmode="numeric"></label><button class="secondary">${t("add")}</button></form></details>`;
}
export function trackerBlock(m, p, editable) {
  const ops = opsOf(m, p.slot),
    live = m.status === "active";
  if (!ops.length && !(editable && live)) return "";
  const up = ops.filter((o) => o.wounds > 0).length,
    key = m.id + ":" + p.slot,
    open = opened[key] ?? true;
  return `<details class="tracker" data-key="${esc(key)}" ${open ? "open" : ""}><summary>${icon("heart")}<span>${t("tracker")}</span>${ops.length ? `<b class="count">${up}/${ops.length}</b>` : ""}</summary>${
    ops.length
      ? `<ul class="ops">${ops.map((o) => opRow(m, o, editable && live)).join("")}</ul>`
      : `<p class="muted">${t(p.roster_id || isHotseat(m) ? "trackerEmpty" : "trackerEmptyNoRoster")}</p>${p.roster_id ? button(t("trackerFill"), "op-populate", "secondary", slotAttr(m, p)) : ""}`
  }${editable && live ? addForm(m, p) : ""}</details>`;
}
export async function trackerCommand(payload) {
  await updateMatch("/operatives", payload, false);
}
export function init() {
  app.addEventListener(
    "toggle",
    (e) => {
      const d = e.target;
      if (d.classList?.contains("tracker")) opened[d.dataset.key] = d.open;
    },
    true,
  );
  app.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b || b.disabled || !currentMatch) return;
    const a = b.dataset.action;
    if (!a.startsWith("op-")) return;
    b.disabled = true;
    tap();
    try {
      if (a === "op-wound")
        await trackerCommand({
          action: "wounds",
          operative_id: +b.dataset.op,
          delta: +b.dataset.delta,
        });
      else if (a === "op-order")
        await trackerCommand({
          action: "order",
          operative_id: +b.dataset.op,
          order: b.dataset.order,
        });
      else if (a === "op-activate")
        await trackerCommand({
          action: "activate",
          operative_id: +b.dataset.op,
          activated: b.dataset.on === "true",
        });
      else if (a === "op-remove") {
        if (confirm(b.dataset.confirm || t("opRemove")))
          await trackerCommand({
            action: "remove",
            operative_id: +b.dataset.op,
          });
      } else if (a === "op-populate")
        await trackerCommand({
          action: "populate",
          ...(b.dataset.slot ? { slot: +b.dataset.slot } : {}),
        });
    } catch (err) {
      notify(err.message);
    } finally {
      b.disabled = false;
    }
  });
  app.addEventListener("submit", async (e) => {
    const f = e.target;
    if (!f.classList.contains("op-add-form")) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const d = Object.fromEntries(new FormData(f)),
      name = (d.name || "").trim(),
      cards = teamCards(
        currentMatch.players.find((p) => p.slot === +f.dataset.slotId),
      ),
      card = cards.find((c) => c.name.toLowerCase() === name.toLowerCase());
    if (!card && (!name || !d.wounds_max)) {
      notify(t(name ? "opWoundsNeeded" : "opNameNeeded"));
      return;
    }
    try {
      await trackerCommand({
        action: "add",
        ...(f.dataset.slot ? { slot: +f.dataset.slot } : {}),
        ...(card ? { card: card.name } : { name }),
        ...(d.wounds_max ? { wounds_max: +d.wounds_max } : {}),
      });
    } catch (err) {
      notify(err.message);
    }
  });
}
