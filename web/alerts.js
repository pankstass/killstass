import { esc, me, notify, t } from "./core.js";
/* v1.10 — sounds and vibration: «your turn» (the chess clock passes to you, or the opponent activated an
   operative) and match results (the opponent finished or confirmed the result), achievements and club news.
   Tones are synthesised with Web Audio (no sound files); vibration works on Android browsers only.
   Settings live in this browser. Browsers allow sound only after the first tap on the page. */
const KEY = "killstass-alerts";
const DEFAULTS = { sound: true, vibrate: true, turn: true, results: true };
let ctx = null,
  lastTurn = 0;
export function settings() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return { ...DEFAULTS };
  }
}
function store(s) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {}
}
const TUNES = {
  turn: [
    [660, 0, 0.12],
    [880, 0.14, 0.18],
  ],
  result: [
    [523, 0, 0.14],
    [659, 0.15, 0.14],
    [784, 0.3, 0.26],
  ],
  achievement: [
    [523, 0, 0.1],
    [659, 0.1, 0.1],
    [784, 0.2, 0.1],
    [1047, 0.3, 0.34],
  ],
  alert: [
    [587, 0, 0.12],
    [587, 0.2, 0.12],
  ],
};
const VIBES = {
  turn: [60, 60, 120],
  result: [120, 80, 120],
  achievement: [40, 40, 40, 40, 160],
  alert: [80],
};
function unlock() {
  try {
    ctx ||= new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
  } catch {
    ctx = null;
  }
}
export function play(kind, force = false) {
  const s = settings();
  if (s.sound || force) {
    try {
      unlock();
      const now = ctx.currentTime + 0.02;
      for (const [freq, at, len] of TUNES[kind] || TUNES.alert) {
        const osc = ctx.createOscillator(),
          gain = ctx.createGain();
        osc.type = "triangle";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, now + at);
        gain.gain.exponentialRampToValueAtTime(0.25, now + at + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + at + len);
        osc.connect(gain).connect(ctx.destination);
        osc.start(now + at);
        osc.stop(now + at + len + 0.05);
      }
    } catch {}
  }
  if (s.vibrate || force)
    try {
      navigator.vibrate?.(VIBES[kind] || VIBES.alert);
    } catch {}
}
/* «Your turn»: at most once per 3 seconds (clock and tracker may report the same moment). */
export function yourTurn() {
  if (!settings().turn || Date.now() - lastTurn < 3000) return;
  lastTurn = Date.now();
  play("turn");
  notify(t("al_yourTurn"));
}
const mySlot = (m) => m?.players?.find((p) => p.user_id === me?.id)?.slot;
const shared = (m) => !m || m.kind === "hotseat" || m.demo || !mySlot(m);
/* Called with the previous and the new clock state after a change made by the other phone. */
export function clockChanged(m, before, after) {
  if (shared(m) || !after?.running || after.mode === "stopwatch") return;
  const slot = mySlot(m);
  if (
    after.active_slot === slot &&
    (before?.active_slot !== slot || !before?.running)
  )
    yourTurn();
}
/* The opponent marked an operative as activated in this turning point: the next activation is yours. */
export function trackerChanged(before, after) {
  if (shared(after) || !before || before.id !== after.id) return;
  if (after.status !== "active") return;
  const slot = mySlot(after),
    tp = after.current_turn,
    was = new Set(
      (before.operatives || [])
        .filter((o) => o.activated_tp === tp)
        .map((o) => o.id),
    );
  if (
    (after.operatives || []).some(
      (o) => o.slot !== slot && o.activated_tp === tp && !was.has(o.id),
    )
  )
    yourTurn();
}
const RESULT = [
  "match_confirmed",
  "match_awaiting_confirmation",
  "match_disputed",
];
/* New notifications that arrived while the app is open (web/live.js). */
export function notification(x) {
  const s = settings();
  if (RESULT.includes(x.kind)) {
    if (!s.results) return;
    play(x.kind === "match_confirmed" ? "result" : "alert");
  } else if (x.kind === "achievement") play("achievement");
  else play("alert");
  notify(t(x.kind));
}
export function settingsPanel() {
  const s = settings(),
    box = (k) =>
      `<label class="check"><input type="checkbox" name="${k}" ${s[k] ? "checked" : ""}>${esc(t("al_" + k))}</label>`;
  return `<section class="panel" id="alert-settings"><h2>${t("al_title")}</h2><p class="muted">${t("al_hint")}</p><form id="alerts-form" class="stack-tight">${box("sound")}${box("vibrate")}${box("turn")}${box("results")}</form><div class="row"><button type="button" class="secondary" data-action="alert-test">${t("al_test")}</button></div>${"vibrate" in navigator ? "" : `<p class="muted small">${t("al_noVibrate")}</p>`}</section>`;
}
export function init() {
  // The first tap unlocks Web Audio (autoplay policy).
  document.addEventListener("pointerdown", unlock, {
    once: true,
    capture: true,
  });
  document.addEventListener("change", (e) => {
    const f = e.target.form;
    if (f?.id !== "alerts-form") return;
    const next = settings();
    for (const k of Object.keys(DEFAULTS)) next[k] = !!f.elements[k]?.checked;
    store(next);
    notify(t("saved"));
  });
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-action=alert-test]")) play("turn", true);
  });
}
