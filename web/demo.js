import { L, button, esc, icon, me, t } from "./core.js";
import { page, renderAuth, setCurrentMatch, setPage } from "./app.js";
import { drawBoard, setBoardPanel } from "./board.js";
import { resetRollOffs } from "./dice.js";
import { standalone } from "./share.js";
/* v1.9 — the demo runs on the real match board. Its state lives only in this browser (localStorage) and
   becomes a synthetic hot-seat match (Approved Ops 2025 scoring) that the board draws as usual; board
   commands (updateMatch) are applied here by the same rules the server checks, and «Undo last» walks back
   a local history. Nothing is sent to the server. */
const DEMO_KEY = "killstass-demo";
const TURNS = 4;
const CRIT_CAPS = [0, 2, 2, 2];
const SOURCES = { 1: "crit", 2: "tac" };
/* Kill Op grade thresholds by the enemy's starting operative count (Approved Ops 2025). */
export const THRESHOLDS = {
  5: [1, 2, 3, 4, 5],
  6: [1, 2, 4, 5, 6],
  7: [1, 3, 4, 6, 7],
  8: [2, 3, 5, 6, 8],
  9: [2, 4, 5, 7, 9],
  10: [2, 4, 6, 8, 10],
  11: [2, 4, 7, 9, 11],
  12: [2, 5, 7, 10, 12],
  13: [3, 5, 8, 10, 13],
  14: [3, 6, 8, 11, 14],
};
const MAX_OPS = 40;
let history = [];
const fail = (code) => {
  throw new Error(L.errors?.[code] || t("demoInvalid"));
};
function fresh(names) {
  return {
    v: 2,
    tp: 1,
    status: "active",
    seq: 1,
    names: names || [1, 2].map((slot) => `${t("player")} ${slot}`),
    counts: [10, 10],
    initiative: {},
    scores: {},
    cp: {},
    notes: {},
    kills: {},
    primary: [
      { op: "crit", committed: false },
      { op: "crit", committed: false },
    ],
    ops: [],
    nextId: 1,
  };
}
export function demoState() {
  try {
    const s = JSON.parse(localStorage.getItem(DEMO_KEY));
    if (s?.v === 2 && Array.isArray(s.names) && s.names.length === 2) return s;
    if (s?.v === 1 && Array.isArray(s.players))
      return fresh(
        s.players.map((p, i) => p.name || `${t("player")} ${i + 1}`),
      );
  } catch {}
  return fresh();
}
function save(s) {
  try {
    localStorage.setItem(DEMO_KEY, JSON.stringify(s));
  } catch {}
}
export const killGrade = (kills, count) =>
  (THRESHOLDS[count] || []).filter((x) => x <= Math.max(kills, 0)).length;
const sum = (obj, prefix) =>
  Object.entries(obj)
    .filter(([k]) => k.startsWith(prefix))
    .reduce((a, [, v]) => a + v, 0);
const scoreOf = (s, comp, slot, tp) => s.scores[`${comp}:${slot}:${tp}`] || 0;
const killsOf = (s, slot) => sum(s.kills, slot + ":");
/* Totals exactly as the server's player_totals view: Kill = grade (+1 at the end when ahead),
   primary bonus = ceil(min(VP of the chosen op, 6) / 2) once the game is finished. */
export function totals(s, finished = s.status === "finished") {
  const base = [1, 2].map((slot) => {
    const crit = sum(s.scores, `crit:${slot}:`),
      tac = sum(s.scores, `tac:${slot}:`),
      incapacitated = killsOf(s, slot),
      grade = killGrade(incapacitated, s.counts[2 - slot]);
    return { slot, crit, tac, incapacitated, grade };
  });
  return base.map((p, i) => {
    const other = base[1 - i],
      kill_bonus = finished && p.grade > other.grade ? 1 : 0,
      kill = p.grade + kill_bonus,
      pr = s.primary[i],
      chosen = pr.committed ? { crit: p.crit, tac: p.tac, kill }[pr.op] : null,
      primary_bonus =
        finished && chosen != null ? Math.ceil(Math.min(chosen, 6) / 2) : 0;
    return {
      ...p,
      kill,
      kill_bonus,
      primary_bonus,
      vp: p.crit + p.tac + kill + primary_bonus,
    };
  });
}
function toMatch(s) {
  const finished = s.status === "finished",
    tot = totals(s);
  const players = [1, 2].map((slot) => ({
    id: slot,
    slot,
    user_id: null,
    display_name: s.names[slot - 1],
    team_id: null,
    roster_id: null,
    roster: "",
    operative_count: s.counts[slot - 1],
    tac_op_id: null,
    tac_revealed: false,
    secret_set: false,
    primary_op: s.primary[slot - 1].op,
    primary_committed: s.primary[slot - 1].committed,
    ...tot[slot - 1],
  }));
  const scores = [],
    turn_states = [];
  for (const [k, vp] of Object.entries(s.scores)) {
    const [comp, slot, tp] = k.split(":");
    if (vp)
      scores.push({
        player_id: +slot,
        turning_point: +tp,
        source_id: comp === "crit" ? 1 : 2,
        vp,
      });
  }
  for (const slot of [1, 2])
    for (let tp = 1; tp <= TURNS; tp++) {
      const k = `${slot}:${tp}`;
      if (k in s.cp || k in s.notes)
        turn_states.push({
          player_id: slot,
          turning_point: tp,
          cp: s.cp[k] ?? 0,
          notes: s.notes[k] || "",
        });
    }
  const top = history[history.length - 1];
  return {
    id: "demo",
    demo: adapter,
    kind: "hotseat",
    status: finished ? "confirmed" : "active",
    scoring_mode: "approved2025",
    edition: "2024",
    turns: TURNS,
    current_turn: s.tp,
    version: s.seq,
    tracker_seq: 0,
    players,
    scores,
    turn_states,
    initiatives: Object.entries(s.initiative).map(([tp, slot]) => ({
      turning_point: +tp,
      slot,
    })),
    initiative: s.initiative[1] || null,
    rules_snapshot: {
      sources: SOURCES,
      mission: { per_turn_caps: CRIT_CAPS },
      thresholds: THRESHOLDS,
    },
    mission_id: null,
    killzone_id: null,
    played_at: new Date().toISOString(),
    clock: null,
    setup: {},
    notes: "",
    operatives: s.ops.map((o) => ({
      ...o,
      player_id: o.slot,
      stats: {},
      weapons: [],
      card: null,
    })),
    undo: top && !finished ? { ...top.summary, id: history.length } : null,
  };
}
/* Kills follow tracked operatives like on the server: reaching 0 wounds credits the opponent. */
function killChange(s, victimSlot, tp, delta) {
  const k = `${3 - victimSlot}:${tp}`;
  s.kills[k] = Math.max(0, (s.kills[k] || 0) + delta);
}
function operative(s, p) {
  const tp = s.tp;
  if (p.action === "populate") fail("roster_required");
  if (p.action === "add") {
    const slot = p.slot || 1;
    if (s.ops.filter((o) => o.slot === slot).length >= MAX_OPS)
      fail("tracker_full");
    const name = String(p.name || p.card || "")
      .trim()
      .slice(0, 80);
    if (!name) fail("operative_name_required");
    const w = Math.max(1, Math.min(99, +p.wounds_max || 1)),
      position =
        Math.max(
          0,
          ...s.ops.filter((o) => o.slot === slot).map((o) => o.position),
        ) + 1;
    s.ops.push({
      id: s.nextId++,
      slot,
      position,
      name,
      wounds_max: w,
      wounds: w,
      order_token: null,
      activated_tp: null,
      incapacitated_tp: null,
    });
    return { action: "operative", change: "add", name, wounds: [null, w] };
  }
  const o = s.ops.find((x) => x.id === p.operative_id);
  if (!o) fail("operative_not_found");
  const before = o.wounds;
  if (p.action === "remove") {
    if (o.incapacitated_tp) killChange(s, o.slot, o.incapacitated_tp, -1);
    s.ops = s.ops.filter((x) => x !== o);
  } else if (p.action === "wounds") {
    const next = Math.max(0, Math.min(o.wounds_max, o.wounds + (p.delta || 0)));
    if (o.wounds > 0 && next === 0) {
      o.incapacitated_tp = tp;
      killChange(s, o.slot, tp, 1);
    } else if (o.wounds === 0 && next > 0) {
      if (o.incapacitated_tp) killChange(s, o.slot, o.incapacitated_tp, -1);
      o.incapacitated_tp = null;
    }
    o.wounds = next;
  } else if (p.action === "order") o.order_token = p.order;
  else if (p.action === "activate") o.activated_tp = p.activated ? tp : null;
  return {
    action: "operative",
    change: p.action,
    name: o.name,
    wounds: [before, o.wounds],
  };
}
function apply(path, p) {
  const s = demoState(),
    prev = JSON.parse(JSON.stringify(s)),
    live = s.status === "active";
  let summary = null;
  if (path === "/undo") {
    const top = history[history.length - 1];
    if (!top || p.audit_id !== history.length) fail("undo_conflict");
    history.pop();
    const back = { ...top.state, seq: s.seq + 1 };
    save(back);
    return toMatch(back);
  }
  if (path === "/actions" && p.action === "reopen") s.status = "active";
  else if (!live) fail("scoring_closed");
  else if (path === "/scores") {
    const tp = p.turning_point,
      slot = p.slot || 1,
      k = `${slot}:${tp}`;
    if (tp < 1 || tp > s.tp) fail("turn_invalid");
    if (p.cp !== undefined) {
      if (p.cp < 0 || p.cp > 99) fail("score_out_of_range");
      const old = s.cp[k] ?? carried(s, slot, tp);
      s.cp[k] = p.cp;
      summary = { action: "score", slot, turning_point: tp, cp: [old, p.cp] };
    } else if (p.notes !== undefined) {
      s.notes[k] = String(p.notes).slice(0, 2000);
      s.cp[k] ??= carried(s, slot, tp);
    } else {
      const comp = SOURCES[p.source_id];
      if (!comp) fail("score_out_of_range");
      const old = scoreOf(s, comp, slot, tp),
        v = old + (p.delta || 0),
        total = sum(s.scores, `${comp}:${slot}:`) - old + v;
      if (v < 0 || total > 6 || (comp === "crit" && v > CRIT_CAPS[tp - 1]))
        fail("score_out_of_range");
      s.scores[`${comp}:${slot}:${tp}`] = v;
      summary = {
        action: "score",
        slot,
        turning_point: tp,
        source_id: p.source_id,
        vp: [old, v],
      };
    }
  } else if (path === "/kills") {
    const slot = p.slot || 1,
      tp = p.turning_point,
      k = `${slot}:${tp}`,
      old = s.kills[k] || 0;
    if (s.ops.some((o) => o.slot === 3 - slot)) fail("kills_tracked");
    const next = old + p.delta,
      total = killsOf(s, slot) - old + next;
    if (next < -MAX_OPS || total < 0 || total > s.counts[2 - slot])
      fail("kills_out_of_range");
    s.kills[k] = next;
    summary = { action: "kills", slot, turning_point: tp, delta: [old, next] };
  } else if (path === "/initiative") {
    s.initiative[p.turning_point] = p.slot;
    summary = {
      action: "initiative",
      slot: p.slot,
      turning_point: p.turning_point,
    };
  } else if (path === "/primary") {
    const i = (p.slot || 1) - 1;
    if (s.tp !== 1 || s.primary[i].committed) fail("primary_closed");
    s.primary[i] = { op: p.primary_op, committed: true };
  } else if (path === "/operatives") summary = operative(s, p);
  else if (path === "/actions" && p.action === "turn") {
    if (p.turning_point < 1 || p.turning_point > TURNS) fail("turn_invalid");
    summary = { action: "turn", turn: [s.tp, p.turning_point] };
    s.tp = p.turning_point;
  } else if (path === "/actions" && p.action === "finish") {
    s.status = "finished";
    history = [];
  } else fail("demoInvalid");
  s.seq += 1;
  if (summary) {
    history.push({ state: prev, summary });
    if (history.length > 30) history.shift();
  }
  save(s);
  return toMatch(s);
}
function carried(s, slot, tp) {
  for (let x = tp - 1; x >= 1; x--)
    if (`${slot}:${x}` in s.cp) return s.cp[`${slot}:${x}`];
  return 0;
}
/* Same shape as GET /api/matches/{id}/preview (final count before finishing). */
function preview() {
  const s = demoState(),
    tot = totals(s, true);
  return {
    scoring_mode: "approved2025",
    ready: s.primary.every((x) => x.committed),
    players: tot.map((x, i) => ({
      ...x,
      display_name: s.names[i],
      base: x.crit + x.tac + x.kill,
      primary_op: s.primary[i].op,
      primary_committed: s.primary[i].committed,
    })),
  };
}
function settingsPanel(s) {
  const counts = Object.keys(THRESHOLDS);
  return `<details class="panel demo-settings"><summary>${icon("gear")}<span>${t("demoSettings")}</span></summary><form id="demo-settings-form" class="grid">${[
    1, 2,
  ]
    .map(
      (slot) =>
        `<fieldset><legend>${t("player")} ${slot}</legend><label>${t("demoName")}<input name="name${slot}" value="${esc(s.names[slot - 1])}" maxlength="32" required></label><label>${t("demoOperatives")}<select name="count${slot}">${counts.map((n) => `<option value="${n}" ${+n === s.counts[slot - 1] ? "selected" : ""}>${n}</option>`).join("")}</select></label></fieldset>`,
    )
    .join(
      "",
    )}<div class="row"><button>${t("save")}</button></div></form><p class="muted">${t("demoSettingsHint")}</p></details>`;
}
function finalPanel(m) {
  const rows = [...m.players];
  return `<section class="panel final-count demo-final"><h2>${t("demoFinished")}</h2><div class="table-wrap" tabindex="0"><table><thead><tr><th>${t("player")}</th><th>Crit</th><th>Tac</th><th>Kill</th><th>${t("primaryShort")}</th><th>${t("total")}</th></tr></thead><tbody>${rows
    .map(
      (p) =>
        `<tr><td>${esc(p.display_name)}</td><td>${p.crit}</td><td>${p.tac}</td><td>${p.kill}${p.kill_bonus ? ` <span class="muted">(${t("killBonusShort")})</span>` : ""}</td><td>${p.primary_committed ? `+${p.primary_bonus} (${esc(t("op_" + p.primary_op))})` : `<span class="muted">${t("primaryNotChosen")}</span>`}</td><td><b>${p.vp}</b></td></tr>`,
    )
    .join(
      "",
    )}</tbody></table></div><p class="muted">${t("demoScoringNote")}</p><div class="row">${button(t("demoReopen"), "match-action", "secondary", 'data-kind="reopen"')}${button(t("demoReset"), "demo-reset", "")}${me ? "" : button(t("demoRegister"), "demo-register", "secondary")}</div></section>`;
}
function draw(m) {
  const s = demoState();
  standalone(
    `<p class="warning demo-banner" role="note">${t("demoBanner")}</p><header class="match-header"><div class="row between"><span class="eyebrow">DEMO / APPROVED OPS 2025</span>${m.status === "active" ? "" : `<span class="badge active">${t("demoFinishedShort")}</span>`}</div><h1>${t("demoTitle")}</h1><p class="muted">${t("demoLead")}</p></header>${settingsPanel(s)}${drawBoard(m)}${m.status === "active" ? `<section class="panel demo-foot"><div class="row">${button(t("demoReset"), "demo-reset", "secondary")}${me ? "" : button(t("demoRegister"), "demo-register", "secondary")}</div></section>` : finalPanel(m)}`,
  );
}
const adapter = { apply, preview, draw };
export function demoPage() {
  const m = toMatch(demoState());
  setCurrentMatch(m);
  draw(m);
}

/* v1.9: listeners are registered from main.js in a fixed order (the former <script> order). */
export function init() {
  document.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b || b.disabled || page !== "demo") return;
    const a = b.dataset.action;
    if (a === "demo-reset") {
      if (confirm(t("demoResetConfirm"))) {
        const names = demoState().names;
        try {
          localStorage.removeItem(DEMO_KEY);
        } catch {}
        save(fresh(names));
        history = [];
        resetRollOffs();
        setBoardPanel(null);
        demoPage();
      }
    } else if (a === "demo-register") {
      history = [];
      window.history.replaceState(null, "", location.pathname);
      setPage("overview");
      renderAuth(true);
    }
  });
  document.addEventListener("submit", (e) => {
    if (page !== "demo" || e.target.id !== "demo-settings-form") return;
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target)),
      s = demoState();
    s.names = [1, 2].map(
      (slot) =>
        String(d["name" + slot] || "")
          .trim()
          .slice(0, 32) || `${t("player")} ${slot}`,
    );
    s.counts = [1, 2].map((slot) => +d["count" + slot] || 10);
    s.seq += 1;
    save(s);
    demoPage();
  });
}
