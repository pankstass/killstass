import { api, app, input, notify, select, t, uuid } from "./core.js";
import { currentMatch, slotOf } from "./app.js";
import { boardPanel, clockBoard, setBoardPanel } from "./board.js";
import { enqueue, isDown, pendingClock, queued } from "./offline.js";
import { clockChanged } from "./alerts.js";
/* v1.4 — game clock. Server events are the source of truth; the client only interpolates between them.
   v1.10: taps carry their moment (`at`, on the server's clock) so taps queued offline keep their time. */
export let clockData = null,
  wakeLock = null;
let offset = 0;
export function setClock(id, state) {
  if (!state) return;
  if (state.server_now) offset = Date.parse(state.server_now) - Date.now();
  // Taps still in the offline queue are shown locally until the server has them.
  if (clockData?.id === id && clockData.state.local && pendingClock(id)) return;
  if (!clockData || clockData.id !== id || state.seq >= clockData.state.seq)
    clockData = { id, state, at: performance.now() };
}
const serverNow = () => new Date(Date.now() + offset).toISOString();
/* Same fold as api/domain.py clock_state for one tap, applied to the interpolated state. */
function localTap(id, action, slot) {
  if (!clockData || clockData.id !== id) return;
  const s = JSON.parse(JSON.stringify(clockData.state)),
    live = s.running ? clockSince() : 0;
  s.total_seconds += live;
  for (const x of s.slots)
    if (s.active_slot === x.slot) {
      x.elapsed_seconds += live;
      if (x.remaining_seconds != null) x.remaining_seconds -= live;
    }
  if (action === "start" && s.mode && !s.running) {
    s.running = true;
    s.started = true;
    if (s.mode !== "stopwatch") s.active_slot = slot || s.active_slot || 1;
  } else if (action === "pause" && s.running) s.running = false;
  else if (action === "switch" && s.running && s.mode !== "stopwatch")
    s.active_slot = 3 - s.active_slot;
  s.local = true;
  clockData = { id, state: s, at: performance.now() };
}
const clockSince = () => (performance.now() - clockData.at) / 1000;
function clockSeconds(kind, slot) {
  const s = clockData.state,
    live = s.running ? clockSince() : 0;
  if (kind === "total") return s.total_seconds + live;
  const x = s.slots.find((r) => r.slot === slot),
    run = s.active_slot === slot ? live : 0;
  return s.mode === "countdown"
    ? x.remaining_seconds - run
    : x.elapsed_seconds + run;
}
export function fmtClock(sec) {
  const neg = sec < 0,
    v = Math.floor(Math.abs(sec)),
    h = Math.floor(v / 3600),
    m = Math.floor((v % 3600) / 60),
    s = String(v % 60).padStart(2, "0");
  return (
    (neg ? "−" : "") +
    (h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`)
  );
}
export function clockForm(s) {
  const mode = s.mode || "chess",
    minutes = s.limit_seconds ? s.limit_seconds / 60 : 45;
  return `<form id="clock-form" class="clock-form">${select(
    "clockMode",
    "mode",
    ["stopwatch", "chess", "countdown"].map((id) => ({
      id,
      label: t("clockMode_" + id),
    })),
    mode,
  )}${input("clockLimit", "limit_minutes", "number", minutes, 'min="1" max="600"')}<p class="muted">${t("clockLimitHint")}</p><button>${t(s.mode ? "clockApply" : "clockEnable")}</button></form>`;
}
export function clockTime(kind, slot) {
  return `<span class="clock-time" data-clock="${kind}" ${slot ? `data-slot="${slot}"` : ""}>${fmtClock(clockSeconds(kind, slot))}</span>`;
}
function redrawClock() {
  const el = document.querySelector("#clock-panel");
  if (!el || !currentMatch) return;
  if (
    el.contains(document.activeElement) &&
    document.activeElement.matches("input,select")
  )
    return;
  el.outerHTML = clockBoard(currentMatch);
  keepAwake();
}
export async function refreshClock() {
  if (!currentMatch) return;
  const id = currentMatch.id;
  try {
    const before = clockData?.id === id ? clockData.state : null;
    const s = await api("/matches/" + id + "/clock");
    if (currentMatch?.id !== id) return;
    setClock(id, s);
    redrawClock();
    if (!s.cachedCopy) clockChanged(currentMatch, before, s);
  } catch (err) {
    if (err.code !== "network") notify(err.message);
  }
}
function queueTap(id, body, sent) {
  enqueue(id, {
    kind: "clock",
    request_id: body.request_id,
    payload: body,
    body: sent ? body : null,
  });
  localTap(id, body.action, body.slot);
  redrawClock();
}
async function clockCmd(payload) {
  const id = currentMatch.id;
  const body = {
    request_id: uuid(),
    ...payload,
    ...(payload.action === "configure" ? {} : { at: serverNow() }),
  };
  if (payload.action !== "configure" && (isDown() || queued(id).length))
    return queueTap(id, body, false);
  let r;
  try {
    r = await api("/matches/" + id + "/clock", "POST", body);
  } catch (err) {
    if (err.code === "network" && payload.action !== "configure")
      return queueTap(id, body, true);
    throw err;
  }
  if (clockData?.id === id) clockData.state.local = false;
  setClock(id, r.clock);
  redrawClock();
  // v1.8: settings live in a board sheet; close it once applied.
  if (boardPanel === "clock" && payload.action === "configure") {
    setBoardPanel(null);
    document.querySelector("#board-sheet")?.remove();
  }
}
/* Keep a phone screen on while the clock runs (HTTPS only; silently ignored elsewhere). */
function keepAwake() {
  const want = !!(
    clockData?.state.running && document.querySelector("#clock-panel")
  );
  if (want && !wakeLock && navigator.wakeLock && !document.hidden)
    navigator.wakeLock
      .request("screen")
      .then((l) => {
        wakeLock = l;
        l.addEventListener("release", () => (wakeLock = null));
      })
      .catch(() => {});
  else if (!want && wakeLock) wakeLock.release().catch(() => {});
}

/* v1.9: listeners are registered from main.js in a fixed order (the former <script> order). */
export function init() {
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      keepAwake();
      if (document.querySelector("#clock-panel")) refreshClock();
    }
  });
  setInterval(() => {
    const nodes = document.querySelectorAll("#clock-panel [data-clock]");
    if (!nodes.length || !clockData) return keepAwake();
    nodes.forEach((n) => {
      const v = clockSeconds(n.dataset.clock, +n.dataset.slot || null);
      n.textContent = fmtClock(v);
      if (clockData.state.mode === "countdown" && n.dataset.slot)
        n.closest(".clock-tile")?.classList.toggle("overtime", v < 0);
    });
  }, 250);
  app.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b || b.disabled || !currentMatch) return;
    const a = b.dataset.action;
    if (a !== "clock" && a !== "clock-reset") return;
    b.disabled = true;
    try {
      if (a === "clock") {
        if (b.dataset.cmd === "switch") navigator.vibrate?.(30);
        await clockCmd({ action: b.dataset.cmd, ...slotOf(b) });
      } else if (confirm(t("clockResetConfirm"))) {
        const s = clockData.state;
        await clockCmd({
          action: "configure",
          mode: s.mode,
          ...(s.limit_seconds ? { limit_minutes: s.limit_seconds / 60 } : {}),
        });
      }
    } catch (err) {
      notify(err.message);
    } finally {
      b.disabled = false;
    }
  });
  app.addEventListener("submit", async (e) => {
    if (e.target.id !== "clock-form") return;
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    document.activeElement?.blur();
    try {
      await clockCmd({
        action: "configure",
        mode: d.mode,
        ...(d.mode === "countdown" ? { limit_minutes: +d.limit_minutes } : {}),
      });
    } catch (err) {
      notify(err.message);
    }
  });
}
