import { api, hooks, me, notify, t, uuid } from "./core.js";
import { THRESHOLDS } from "./demo.js";
/* v1.10 — offline scoreboard. The service worker (/sw.js) keeps the app shell and copies of the last API
   answers; this module queues board commands made without a connection (per player, in localStorage),
   shows them on the board at once and sends them in order when the server answers again.
   A command that already went out keeps its body (same request_id and version), so a lost answer is
   replayed idempotently; a queued command that was never sent gets the current match version. */
const KEY = "killstass-queue:";
const MAX = 300;
let down = false,
  cachedView = false,
  flushing = false;
export const isDown = () => down;
const storeKey = () => (me ? KEY + me.id : null);
function readAll() {
  try {
    return JSON.parse(localStorage.getItem(storeKey())) || {};
  } catch {
    return {};
  }
}
function writeAll(all) {
  try {
    for (const k of Object.keys(all)) if (!all[k].length) delete all[k];
    if (Object.keys(all).length)
      localStorage.setItem(storeKey(), JSON.stringify(all));
    else localStorage.removeItem(storeKey());
  } catch {}
  banner();
}
export const queued = (mid) => (storeKey() ? readAll()[mid] || [] : []);
export const pendingCount = () =>
  storeKey() ? Object.values(readAll()).reduce((a, q) => a + q.length, 0) : 0;
export const pendingClock = (mid) =>
  queued(mid).some((e) => e.kind === "clock");
function save(mid, q) {
  const all = readAll();
  all[mid] = q;
  writeAll(all);
}

/* Commands that make sense without the server: scores, CP, notes, kills, initiative, the turning point,
   tracker taps and the clock. Setup, finishing, undo and operative lists need an answer. */
export function queueable(path, payload) {
  if (["/scores", "/kills", "/initiative"].includes(path)) return true;
  if (path === "/actions") return payload.action === "turn";
  if (path === "/operatives")
    return ["wounds", "order", "activate"].includes(payload.action);
  return false;
}

const clone = (v) => JSON.parse(JSON.stringify(v));
const grade = (m, kills, count) =>
  ((m.rules_snapshot?.thresholds || THRESHOLDS)[count] || []).filter(
    (x) => x <= Math.max(kills, 0),
  ).length;
function actor(m, payload) {
  if (payload.slot) return m.players.find((p) => p.slot === payload.slot);
  return m.players.find((p) => p.user_id === me?.id) || m.players[0];
}
/* Kill grade and VP follow the player's net incapacitated count (as the server's player_totals). */
function setKills(m, p, value) {
  const other = m.players.find((x) => x.slot !== p.slot);
  if (m.scoring_mode !== "approved2025") return;
  const before = p.kill ?? 0;
  p.incapacitated = Math.max(0, value);
  p.grade = grade(m, p.incapacitated, other.operative_count);
  p.kill = p.grade;
  p.vp = (p.vp || 0) + p.kill - before;
}
/* Optimistic copy of the snapshot with one queued command applied (the server stays the referee). */
export function patch(m, path, payload) {
  const s = clone(m);
  const p = actor(s, payload);
  if (!p) return s;
  const tp = payload.turning_point;
  if (path === "/scores" && payload.source_id) {
    let row = s.scores.find(
      (r) =>
        r.player_id === p.id &&
        r.turning_point === tp &&
        r.source_id === payload.source_id,
    );
    if (!row)
      s.scores.push(
        (row = {
          player_id: p.id,
          turning_point: tp,
          source_id: payload.source_id,
          vp: 0,
        }),
      );
    const next = Math.max(0, row.vp + payload.delta),
      d = next - row.vp;
    row.vp = next;
    p.vp = (p.vp || 0) + d;
    const comp = s.rules_snapshot?.sources?.[payload.source_id];
    if (comp === "crit" || comp === "tac") p[comp] = (p[comp] || 0) + d;
  } else if (path === "/scores") {
    let row = s.turn_states.find(
      (r) => r.player_id === p.id && r.turning_point === tp,
    );
    if (!row) {
      const prev = s.turn_states
        .filter((r) => r.player_id === p.id && r.turning_point < tp)
        .sort((a, b) => b.turning_point - a.turning_point)[0];
      s.turn_states.push(
        (row = {
          player_id: p.id,
          turning_point: tp,
          cp: prev?.cp || 0,
          notes: "",
        }),
      );
    }
    if (payload.cp !== undefined) row.cp = payload.cp;
    if (payload.notes !== undefined) row.notes = payload.notes;
  } else if (path === "/kills") {
    let row = (s.kills ||= []).find(
      (r) => r.player_id === p.id && r.turning_point === tp,
    );
    if (!row)
      s.kills.push((row = { player_id: p.id, turning_point: tp, delta: 0 }));
    row.delta += payload.delta;
    setKills(s, p, (p.incapacitated || 0) + payload.delta);
  } else if (path === "/initiative") {
    s.initiatives = (s.initiatives || []).filter((x) => x.turning_point !== tp);
    s.initiatives.push({ turning_point: tp, slot: payload.slot });
    if (tp === 1) s.initiative = payload.slot;
  } else if (path === "/actions" && payload.action === "turn")
    s.current_turn = tp;
  else if (path === "/operatives") {
    const o = (s.operatives || []).find((x) => x.id === payload.operative_id);
    if (!o) return s;
    if (payload.action === "wounds") {
      const next = Math.max(
        0,
        Math.min(o.wounds_max, o.wounds + (payload.delta || 0)),
      );
      const killer = s.players.find((x) => x.slot !== o.slot);
      if (o.wounds > 0 && next === 0) {
        o.incapacitated_tp = s.current_turn;
        setKills(s, killer, (killer.incapacitated || 0) + 1);
      } else if (o.wounds === 0 && next > 0) {
        o.incapacitated_tp = null;
        setKills(s, killer, (killer.incapacitated || 0) - 1);
      }
      o.wounds = next;
    } else if (payload.action === "order") o.order_token = payload.order;
    else if (payload.action === "activate")
      o.activated_tp = payload.activated ? s.current_turn : null;
  }
  return s;
}
/* A fresh server snapshot plus the commands still waiting in the queue. */
export function overlay(m) {
  if (!m?.id) return m;
  let s = m;
  for (const e of queued(m.id))
    if (e.kind !== "clock") s = patch(s, e.path, e.payload);
  return s;
}

/* body: the exact request that may already have reached the server (null: not sent yet). */
export function enqueue(mid, entry) {
  const q = queued(mid);
  if (q.length >= MAX) throw new Error(t("off_queueFull"));
  q.push({ created_at: Date.now(), ...entry });
  save(mid, q);
  down = true;
  banner();
}

async function send(mid, e) {
  if (!e.body) {
    e.body = { request_id: e.request_id, ...e.payload };
    if (e.versioned)
      e.body.version = (await api("/matches/" + mid + "?fresh=1")).version;
    const q = queued(mid);
    const i = q.findIndex((x) => x.request_id === e.request_id);
    if (i >= 0) q[i] = e;
    save(mid, q);
  }
  const path = e.kind === "clock" ? "/clock" : e.path;
  return api("/matches/" + mid + path, "POST", e.body, false);
}
function drop(mid, id) {
  save(
    mid,
    queued(mid).filter((x) => x.request_id !== id),
  );
}
let onFlushed = () => {};
export const setOnFlushed = (f) => (onFlushed = f);
/* Sends every queued command in order; stops at the first network failure (the rest waits). */
export async function flush() {
  if (flushing || !me || !pendingCount()) return;
  flushing = true;
  banner();
  let sent = 0;
  const rejected = [],
    touched = new Set();
  try {
    for (const mid of Object.keys(readAll())) {
      for (let e = queued(mid)[0]; e; e = queued(mid)[0]) {
        try {
          await send(mid, e);
          drop(mid, e.request_id);
          sent += 1;
          touched.add(mid);
        } catch (err) {
          if (err.code === "network") throw err;
          if (err.code === "version_conflict" && (e.tries || 0) < 3) {
            // Not applied: the opponent changed the match in between. Send it again on the new version.
            const q = queued(mid);
            q[0] = {
              ...e,
              body: null,
              request_id: uuid(),
              tries: (e.tries || 0) + 1,
            };
            save(mid, q);
            continue;
          }
          // Signed out, stale CSRF token or rate limit: keep the queue for the next attempt.
          if (
            ["unauthenticated", "csrf_invalid", "rate_limited"].includes(
              err.code,
            )
          )
            throw err;
          drop(mid, e.request_id);
          rejected.push(err.message);
          touched.add(mid);
        }
      }
    }
  } catch {
    /* still offline (or signed out): the queue waits for the next attempt */
  } finally {
    flushing = false;
    banner();
  }
  if (sent) notify(t("off_sent").replace("{n}", sent));
  if (rejected.length)
    notify(
      t("off_rejected").replace("{n}", rejected.length) + " " + rejected[0],
    );
  if (touched.size) onFlushed([...touched]);
}

export function banner() {
  const el = document.querySelector("#netstate");
  if (!el) return;
  const n = pendingCount();
  let text = "";
  if (n && flushing) text = t("off_sending").replace("{n}", n);
  else if (n) text = t("off_queued").replace("{n}", n);
  else if (down) text = t("off_down");
  else if (cachedView) text = t("off_cached");
  el.textContent = text;
  el.hidden = !text;
  el.classList.toggle("pending", !!n);
}

/* Logout or account deletion: forget queued commands and the service worker's copies. */
export function clearOffline() {
  try {
    if (storeKey()) localStorage.removeItem(storeKey());
  } catch {}
  navigator.serviceWorker?.controller?.postMessage({ type: "clear" });
  down = false;
  cachedView = false;
  banner();
}

export function init() {
  hooks.net = (state) => {
    const was = down;
    down = state === "down";
    cachedView = state === "cached";
    if (state === "cached") down = true;
    banner();
    if (was && state === "ok" && pendingCount()) setTimeout(flush, 0);
  };
  window.addEventListener("online", () => flush());
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) flush();
  });
  setInterval(() => {
    if (pendingCount()) flush();
  }, 10000);
  // The service worker needs a secure context with a trusted certificate (a domain with Let's Encrypt,
  // or the installed local CA). Without it the app works as before, online only.
  if ("serviceWorker" in navigator && window.isSecureContext)
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
  navigator.serviceWorker?.addEventListener("message", (e) => {
    if (e.data?.type === "open" && e.data.hash) location.hash = e.data.hash;
  });
}
