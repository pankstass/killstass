import {
  app,
  badge,
  esc,
  icon,
  lang,
  locale,
  localizeRow,
  logo,
  t,
} from "./core.js";
import { page } from "./app.js";
import { fmtClock } from "./clock.js";
/* v1.10 — club TV screen (#tv/<key>): live scoreboards with clocks, the tournament table and pairings, the
   season top 10, the next game night and recent results. Works without a session: the key from #admin
   is the access (it can be deleted there). Polls every 5 seconds; clocks tick locally in between.
   Players who hid their profile are shown as «Player». */
let timer = null,
  data = null,
  key = null,
  fetchedAt = 0,
  wake = null,
  failed = false;
const label = (x) => (x ? localizeRow(x).label : "—");
const name = (v) => (v == null ? t("player") : v);
const hm = (v) =>
  new Intl.DateTimeFormat(locale(), {
    timeStyle: "short",
    timeZone: "Europe/Moscow",
  }).format(v);
const since = () => (performance.now() - fetchedAt) / 1000;
function clockText(c, slot) {
  const live = c.running ? since() : 0;
  if (!slot) return fmtClock(c.total_seconds + live);
  const x = c.slots.find((s) => s.slot === slot),
    run = c.active_slot === slot ? live : 0;
  return fmtClock(
    c.mode === "countdown"
      ? x.remaining_seconds - run
      : x.elapsed_seconds + run,
  );
}
function avatar(p) {
  return p.avatar
    ? `<img class="avatar md" src="/api/tv/${esc(key)}/avatar/${esc(p.avatar)}" alt="" width="48" height="48" loading="lazy">`
    : `<span class="avatar md none" aria-hidden="true">${icon("user")}</span>`;
}
function matchCard(m) {
  const c = m.clock,
    lead = Math.max(...m.players.map((p) => p.vp));
  return `<article class="tv-match"><header class="row between"><span class="eyebrow">${esc(label(m.mission))} · ${esc(label(m.killzone))}</span>${m.status === "active" ? `<span class="badge active">TP ${m.turn}/${m.turns}</span>` : badge(m.status)}</header><div class="tv-players">${m.players
    .map(
      (p) =>
        `<div class="tv-player slot-${p.slot} ${c?.running && c.active_slot === p.slot ? "turn" : ""} ${p.vp === lead && lead > 0 ? "lead" : ""}">${avatar(p)}<div class="grow"><b>${esc(name(p.name))}</b><small>${esc(label(p.team))}</small></div>${c && c.mode !== "stopwatch" ? `<span class="tv-clock mono" data-tv-clock="${p.slot}">${clockText(c, p.slot)}</span>` : ""}<b class="tv-vp">${p.vp}</b></div>`,
    )
    .join(
      "",
    )}</div>${c ? `<footer class="muted mono"><span data-tv-clock="0">${clockText(c, 0)}</span>${c.running ? "" : ` · ${t("tv_paused")}`}</footer>` : ""}</article>`;
}
function tournament(x) {
  return `<section class="tv-box"><h2>${icon("trophy")} ${esc(x.name)} <small>${t("tv_round")} ${x.round || "—"}/${x.rounds}</small></h2><table class="tv-table"><thead><tr><th>#</th><th>${t("player")}</th><th>${t("tv_points")}</th><th>±VP</th></tr></thead><tbody>${x.standings.map((r) => `<tr><td>${r.rank}</td><td>${esc(name(r.name))}</td><td><b>${r.points}</b></td><td>${r.diff > 0 ? "+" : ""}${r.diff}</td></tr>`).join("")}</tbody></table>${x.pairings.length ? `<h3>${t("tv_pairings")}</h3><ul class="tv-pairs">${x.pairings.map((p) => `<li><span class="muted">#${p.table}</span> ${esc(name(p.a))} <b class="mono">${p.vp1 ?? "–"}:${p.vp2 ?? "–"}</b> ${p.b === null ? t("nt_bye") : esc(name(p.b))}</li>`).join("")}</ul>` : ""}</section>`;
}
function season(s) {
  return `<section class="tv-box"><h2>${icon("chart")} ${esc(s.name)}</h2>${s.players.length ? `<ol class="tv-top">${s.players.map((p) => `<li><span>${esc(name(p.name))}</span><b>${p.rating}</b></li>`).join("")}</ol>` : `<p class="muted">${t("sn_noGames")}</p>`}</section>`;
}
function night(n) {
  return `<section class="tv-box"><h2>${icon("table")} ${esc(n.title)}</h2><p class="muted">${esc(new Intl.DateTimeFormat(locale(), { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Moscow" }).format(new Date(n.starts_at)))}${n.place ? ` · ${esc(n.place)}` : ""}</p><p>${icon("check")} ${n.attendees.length}${n.capacity ? "/" + n.capacity : ""}: ${n.attendees.map((p) => esc(name(p.name))).join(", ") || "—"}</p>${n.pairs.length ? `<ul class="tv-pairs">${n.pairs.map((p) => `<li><span class="muted">#${p.table}</span> ${esc(name(p.a))} — ${p.bye ? t("nt_bye") : esc(name(p.b))}</li>`).join("")}</ul>` : ""}</section>`;
}
function recent(list) {
  return `<section class="tv-box"><h2>${icon("history")} ${t("tv_recent")}</h2><ul class="tv-pairs">${list.map((m) => `<li>${m.players.map((p) => `${esc(name(p.name))} <b>${p.vp}</b>`).join(" : ")} <small class="muted">${esc(label(m.mission))}</small></li>`).join("")}</ul></section>`;
}
function draw() {
  const d = data;
  app.innerHTML = `<main id="content" class="tv"><header class="tv-head">${logo()}<h1>${esc(d.label)}</h1><span class="grow"></span><span class="tv-now mono" id="tv-now">${hm(new Date())}</span><button type="button" class="secondary" data-action="tv-full" aria-label="${esc(t("tv_fullscreen"))}">⛶</button></header>${failed ? `<p class="warning">${t("off_down")}</p>` : ""}<div class="tv-grid"><section class="tv-live"><h2>${icon("crosshair")} ${t("tv_live")} (${d.matches.length})</h2>${d.matches.length ? `<div class="tv-matches">${d.matches.map(matchCard).join("")}</div>` : `<p class="empty">${t("emptyLive")}</p>`}</section><aside class="tv-side">${d.tournaments.map(tournament).join("")}${d.night ? night(d.night) : ""}${d.season ? season(d.season) : ""}${d.recent.length ? recent(d.recent) : ""}</aside></div></main>`;
}
async function load() {
  if (page !== "tv") return stop();
  if (document.hidden) return;
  try {
    const r = await fetch("/api/tv/" + encodeURIComponent(key), {
      credentials: "omit",
      cache: "no-store",
    });
    if (r.status === 404) {
      stop();
      app.innerHTML = `<main id="content" class="tv"><section class="panel"><h1>${t("tv_notFound")}</h1><p class="muted">${t("tv_notFoundHint")}</p></section></main>`;
      return;
    }
    if (!r.ok) throw new Error(String(r.status));
    data = await r.json();
    fetchedAt = performance.now();
    failed = false;
  } catch {
    failed = true;
  }
  if (data && page === "tv") draw();
}
function tick() {
  if (page !== "tv" || !data) return;
  const now = document.querySelector("#tv-now");
  if (now) now.textContent = hm(new Date());
  document.querySelectorAll(".tv-match").forEach((card, i) => {
    const c = data.matches[i]?.clock;
    if (!c) return;
    card.querySelectorAll("[data-tv-clock]").forEach((n) => {
      n.textContent = clockText(c, +n.dataset.tvClock);
    });
  });
}
function keepAwake() {
  if (page !== "tv" || wake || document.hidden || !navigator.wakeLock) return;
  navigator.wakeLock
    .request("screen")
    .then((l) => {
      wake = l;
      l.addEventListener("release", () => (wake = null));
    })
    .catch(() => {});
}
function stop() {
  clearInterval(timer);
  timer = null;
  wake?.release().catch(() => {});
}
export function tvPage(k) {
  stop();
  key = k || "";
  data = null;
  document.documentElement.lang = lang;
  app.innerHTML = `<main id="content" class="tv"><p class="muted">${t("loading")}</p></main>`;
  load();
  keepAwake();
  let n = 0;
  timer = setInterval(() => {
    tick();
    if (++n % 5 === 0) load();
  }, 1000);
}
export function init() {
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && page === "tv") {
      keepAwake();
      load();
    }
  });
  app.addEventListener("click", (e) => {
    if (!e.target.closest("[data-action=tv-full]")) return;
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else document.documentElement.requestFullscreen?.().catch(() => {});
  });
}
