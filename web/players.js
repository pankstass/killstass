import {
  api,
  app,
  badge,
  button,
  cat,
  catName,
  date,
  esc,
  icon,
  input,
  lang,
  link,
  locale,
  me,
  notify,
  select,
  setMe,
  t,
} from "./core.js";
import { metrics, page, shell } from "./app.js";
import { settingsPanel } from "./alerts.js";
/* v1.10 — player page (#player/<ID>): avatar, motto, favourite team, statistics, the season rating,
   achievements, recent results and the head-to-head record; profile extras and Web Push on #profile.
   A hidden profile is visible to friends only and leaves club-wide tables and the TV screen. */
const SIZES = { sm: 28, md: 48, lg: 96 };
export function avatarImg(pid, hash, size = "md", src = null) {
  const px = SIZES[size] || 48;
  if (!pid || !hash)
    return `<span class="avatar ${size} none" aria-hidden="true">${icon("user")}</span>`;
  return `<img class="avatar ${size}" src="${esc(src || `/api/users/${pid}/avatar`)}?h=${esc(hash)}" alt="" width="${px}" height="${px}" loading="lazy" decoding="async">`;
}
export const playerLink = (pid, name) =>
  pid
    ? `<a class="player-link" href="#player/${esc(pid)}">${esc(name)}</a>`
    : esc(name);
const titleOf = (a) => (lang === "en" && a.title_en) || a.title_ru;
const descOf = (a) => (lang === "en" && a.description_en) || a.description_ru;
function achievement(a) {
  const earned = !!a.earned_at,
    value = Math.min(a.progress ?? 0, a.threshold);
  return `<li class="ach ${earned ? "earned" : "locked"}"><span class="ach-icon">${icon(a.icon)}</span><div><b>${esc(titleOf(a))}</b><small>${esc(descOf(a))}</small>${
    earned
      ? `<small class="muted">${esc(date(a.earned_at))}</small>`
      : `<span class="ach-progress"><progress max="${a.threshold}" value="${value}" aria-label="${esc(titleOf(a))}"></progress><small>${value}/${a.threshold}</small></span>`
  }${a.season_name ? `<small class="muted">${t("pl_seasonOnly")}: ${esc(a.season_name)}</small>` : ""}</div></li>`;
}
export const day = (v) =>
  new Intl.DateTimeFormat(locale(), {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(v + "T00:00:00Z"));
function seasonBox(s) {
  if (!s) return `<p class="muted">${t("sn_none")}</p>`;
  return `<p class="eyebrow">${esc(s.name)} · ${esc(day(s.starts_on))} — ${esc(day(s.ends_on))}</p>${
    s.rating == null
      ? `<p class="muted">${t("sn_noGames")}</p>`
      : `<div class="metrics compact"><div class="metric"><strong class="accent">${s.rating}</strong><span>Elo</span></div><div class="metric"><strong>#${s.rank}</strong><span>${t("sn_rank")}</span></div><div class="metric"><strong>${s.wins}/${s.draws}/${s.losses}</strong><span>${t("wins")}/${t("draws")}/${t("losses")}</span></div></div>`
  }`;
}
function actions(p) {
  if (p.me) return link(t("pl_edit"), "profile");
  const f = p.friendship;
  if (!f)
    return button(
      t("addFriend"),
      "pl-friend",
      "secondary",
      `data-id="${esc(p.public_id)}"`,
    );
  if (f.status === "accepted")
    return `${badge("accepted")}${button(t("challenge"), "challenge-form", "", `data-id="${esc(p.public_id)}"`)}`;
  return f.outgoing
    ? `<span class="muted">${t("pl_requestSent")}</span>`
    : link(t("friends"), "friends");
}
function recentRow(r) {
  return `<article class="list-item"><div><span class="eyebrow">${r.played_at ? esc(date(r.played_at)) : "—"} / ${t(r.kind)}</span><h3>${playerLink(r.opponent_public_id, r.opponent_name)} <span class="accent mono">${r.vp_for}:${r.vp_against}</span></h3><span class="muted">${esc(catName(r.team_id))} — ${esc(catName(r.opponent_team_id))}</span></div><div class="row">${badge(r.result)}${r.match_id ? link(t("open"), "match/" + r.match_id) : ""}</div></article>`;
}
export async function playerPage(pid) {
  const p = await api("/players/" + encodeURIComponent(pid || me.public_id));
  if (page !== "player") return;
  const earned = p.achievements.filter((a) => a.earned_at).length,
    h = p.head_to_head;
  shell(
    `<header class="panel player-head">${avatarImg(p.public_id, p.avatar, "lg")}<div class="grow"><span class="eyebrow">OPERATIVE FILE · #${esc(p.public_id)}</span><h1>${esc(p.display_name)}</h1>${p.motto ? `<p class="motto">«${esc(p.motto)}»</p>` : ""}<p class="muted">${p.favorite_team_id ? `${t("pl_favorite")}: ${esc(catName(p.favorite_team_id))} · ` : ""}${t("pl_since")} ${esc(date(p.member_since))}${p.summary.last_played ? ` · ${t("pl_lastGame")} ${esc(date(p.summary.last_played))}` : ""}</p>${p.hidden ? `<p><span class="badge">${icon("lock")}${t("pl_hiddenBadge")}</span></p>` : ""}</div><div class="row">${actions(p)}</div></header>${metrics(p.summary)}${
      h
        ? `<div class="grid"><section class="panel"><h2>${t("sn_title")}</h2>${seasonBox(p.season)}</section><section class="panel"><h2>${t("pl_h2h")}</h2>${h.games ? `<p class="big-score"><b class="accent">${h.wins}</b> : ${h.losses}${h.draws ? ` <small>(${t("draws")}: ${h.draws})</small>` : ""}</p><p class="muted">${t("games")}: ${h.games}</p>` : `<p class="muted">${t("pl_h2hNone")}</p>`}</section></div>`
        : `<section class="panel"><h2>${t("sn_title")}</h2>${seasonBox(p.season)}</section>`
    }<section class="panel"><h2>${t("ach_title")} <small class="muted">${earned}/${p.achievements.length}</small></h2>${p.achievements.length ? `<ul class="ach-grid">${p.achievements.map(achievement).join("")}</ul>` : `<p class="empty">${t("ach_empty")}</p>`}</section><div class="grid"><section class="panel"><h2>${t("pl_teams")}</h2>${p.teams.length ? `<div class="table-wrap" tabindex="0"><table><thead><tr><th>${t("teams")}</th><th>${t("games")}</th><th>${t("wins")}</th></tr></thead><tbody>${p.teams.map((r) => `<tr><td>${esc(catName(r.team_id))}</td><td>${r.games}</td><td>${r.wins}</td></tr>`).join("")}</tbody></table></div>` : `<p class="empty">${t("emptyHistory")}</p>`}</section><section class="panel"><h2>${t("recent")}</h2>${p.recent.length ? p.recent.map(recentRow).join("") : `<p class="empty">${t("emptyHistory")}</p>`}</section></div>`,
  );
}

/* Season table on the statistics page (club-wide: every confirmed friend match in the season dates). */
let seasonChoice = null;
export async function seasonPanel() {
  const s = await api("/seasons");
  if (!s.seasons.length) return "";
  const id = seasonChoice ?? s.current_id ?? s.seasons[0].id,
    r = await api("/seasons/" + id + "/ratings");
  return `<section class="panel" id="season-panel"><div class="row between"><h2>${t("sn_title")}: ${esc(r.season.name)} ${badge("sn_" + r.season.status)}</h2><label class="inline">${t("sn_pick")}<select id="season-pick">${s.seasons.map((x) => `<option value="${x.id}" ${x.id === id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></label></div><p class="muted">${esc(r.season.starts_on)} — ${esc(r.season.ends_on)} · K = ${r.season.k_factor} · ${t("sn_start")} ${r.season.start_rating} · ${t("games")}: ${r.games}</p>${
    r.players.length
      ? `<div class="table-wrap" tabindex="0"><table class="ratings"><thead><tr><th>#</th><th>${t("player")}</th><th>Elo</th><th>${t("games")}</th><th>${t("wins")}</th><th>${t("draws")}</th><th>${t("losses")}</th></tr></thead><tbody>${r.players.map((p) => `<tr class="${p.me ? "me" : ""}"><td>${p.rank}</td><td class="who">${avatarImg(p.public_id, p.avatar, "sm")}${playerLink(p.public_id, p.display_name)}</td><td><b>${p.rating}</b></td><td>${p.games}</td><td>${p.wins}</td><td>${p.draws}</td><td>${p.losses}</td></tr>`).join("")}</tbody></table></div>`
      : `<p class="empty">${t("sn_noGames")}</p>`
  }</section>`;
}

/* ------------------------------------------------------------------ profile extras */
export function profileExtras() {
  queueMicrotask(() => loadExtras().catch((e) => notify(e.message)));
  return `<section class="panel"><p class="muted">${t("loading")}</p></section>`;
}
const pushSupported = () =>
  window.isSecureContext &&
  "serviceWorker" in navigator &&
  "PushManager" in window &&
  "Notification" in window;
async function registration() {
  return Promise.race([
    navigator.serviceWorker.ready,
    new Promise((_, no) =>
      setTimeout(() => no(new Error(t("push_noWorker"))), 4000),
    ),
  ]);
}
/* The registration of the service worker, without waiting: none without a trusted certificate. */
async function workerReg() {
  if (!pushSupported()) return null;
  try {
    return (await navigator.serviceWorker.getRegistration()) || null;
  } catch {
    return null;
  }
}
async function deviceSubscription() {
  const reg = await workerReg();
  try {
    return (await reg?.pushManager.getSubscription()) || null;
  } catch {
    return null;
  }
}
function pushPanel(cfg, sub, worker) {
  let body;
  if (!cfg.enabled) body = `<p class="muted">${t("push_off")}</p>`;
  else if (!pushSupported())
    body = `<p class="muted">${t("push_unsupported")}</p>`;
  else if (!worker) body = `<p class="muted">${t("push_noWorker")}</p>`;
  else
    body = `<p>${sub ? `${icon("check")} ${t("push_on")}` : t("push_offDevice")}</p><div class="row">${sub ? button(t("push_disable"), "push-off") + button(t("push_test"), "push-test") : button(t("push_enable"), "push-on", "")}</div><p class="muted small">${t("push_hint")}</p>`;
  return `<section class="panel" id="push-panel"><h2>${t("push_title")}</h2>${body}<p class="muted small">${t("push_devices")}: ${cfg.subscriptions}</p></section>`;
}
async function loadExtras() {
  const [x, cfg] = await Promise.all([
    api("/profile/extra"),
    api("/push/config").catch(() => ({ enabled: false, subscriptions: 0 })),
  ]);
  const worker = await workerReg(),
    sub = await deviceSubscription();
  const el = document.querySelector("#profile-extra");
  if (!el || page !== "profile") return;
  el.innerHTML = `<section class="panel" id="extra-panel"><div class="row between"><h2>${t("pl_profile")}</h2>${link(t("pl_myPage"), "player/" + me.public_id)}</div><div class="avatar-edit">${avatarImg(me.public_id, x.avatar, "lg")}<div class="stack-tight"><label class="button secondary file-button">${icon("upload")}<span>${t(x.avatar ? "pl_avatarChange" : "pl_avatarUpload")}</span><input type="file" id="avatar-file" accept="image/png,image/jpeg,image/webp" class="sr-only"></label>${x.avatar ? button(t("pl_avatarDelete"), "avatar-delete") : ""}<small class="muted">${t("pl_avatarHint")}</small></div></div><form id="extra-form">${input("pl_motto", "motto", "text", x.motto || "", 'maxlength="140"')}${select("pl_favorite", "favorite_team_id", [{ id: "", label: t("none") }, ...cat("team", "2024")], x.favorite_team_id ?? "")}<label class="check"><input type="checkbox" name="hidden" ${x.hidden ? "checked" : ""}>${t("pl_hidden")}</label><p class="muted small">${t("pl_hiddenHint")}</p><button>${t("save")}</button></form></section>${pushPanel(cfg, sub, !!worker)}${settingsPanel()}`;
}
/* Square crop, 256 px, WebP (JPEG where the browser cannot encode WebP) — stays under the server limit. */
async function decode(file) {
  if (window.createImageBitmap)
    try {
      return await createImageBitmap(file);
    } catch {}
  const url = await new Promise((ok, no) => {
    const r = new FileReader();
    r.onload = () => ok(r.result);
    r.onerror = no;
    r.readAsDataURL(file);
  });
  const img = new Image();
  img.src = url;
  await img.decode();
  return img;
}
const base64 = (blob) =>
  new Promise((ok, no) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1]);
    r.onerror = no;
    r.readAsDataURL(blob);
  });
export async function avatarData(file) {
  if (!/^image\//.test(file.type) || file.size > 20 * 1024 * 1024)
    throw new Error(t("pl_avatarBad"));
  const img = await decode(file),
    w = img.width,
    h = img.height,
    side = Math.min(w, h),
    canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  canvas
    .getContext("2d")
    .drawImage(img, (w - side) / 2, (h - side) / 2, side, side, 0, 0, 256, 256);
  for (const [type, q] of [
    ["image/webp", 0.85],
    ["image/jpeg", 0.85],
    ["image/jpeg", 0.65],
  ]) {
    const blob = await new Promise((ok) => canvas.toBlob(ok, type, q));
    if (blob && blob.type === type && blob.size <= 190000)
      return { mime: type, data: await base64(blob) };
  }
  throw new Error(t("pl_avatarBad"));
}
const keyBytes = (b64) => {
  const s = atob(
    (b64 + "=".repeat((4 - (b64.length % 4)) % 4))
      .replace(/-/g, "+")
      .replace(/_/g, "/"),
  );
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
};
async function pushOn() {
  const cfg = await api("/push/config");
  if (!cfg.enabled) throw new Error(t("push_off"));
  if ((await Notification.requestPermission()) !== "granted")
    throw new Error(t("push_denied"));
  const reg = await registration();
  const sub =
    (await reg.pushManager.getSubscription()) ||
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: keyBytes(cfg.public_key),
    }));
  const j = sub.toJSON();
  await api("/push/subscriptions", "POST", {
    endpoint: j.endpoint,
    keys: { p256dh: j.keys.p256dh, auth: j.keys.auth },
    lang,
  });
}
async function pushOff() {
  const sub = await deviceSubscription();
  if (!sub) return;
  await api("/push/unsubscribe", "POST", { endpoint: sub.endpoint });
  await sub.unsubscribe().catch(() => {});
}
/* Keeps the server's copy of this device's subscription fresh (it may change after browser updates). */
export async function syncPush() {
  if (!me || !pushSupported() || Notification.permission !== "granted") return;
  const sub = await deviceSubscription();
  if (!sub) return;
  const j = sub.toJSON();
  await api("/push/subscriptions", "POST", {
    endpoint: j.endpoint,
    keys: { p256dh: j.keys.p256dh, auth: j.keys.auth },
    lang,
  }).catch(() => {});
}
export function init() {
  app.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b || b.disabled) return;
    const a = b.dataset.action;
    if (
      ![
        "pl-friend",
        "avatar-delete",
        "push-on",
        "push-off",
        "push-test",
      ].includes(a)
    )
      return;
    b.disabled = true;
    try {
      if (a === "pl-friend") {
        await api("/friends", "POST", { public_id: b.dataset.id });
        notify(t("pl_requestSent"));
        await playerPage(b.dataset.id);
      } else if (a === "avatar-delete") {
        await api("/profile/avatar", "DELETE", {});
        setMe({ ...me, avatar: null });
        await loadExtras();
      } else if (a === "push-on") {
        await pushOn();
        notify(t("push_on"));
        await loadExtras();
      } else if (a === "push-off") {
        await pushOff();
        await loadExtras();
      } else if (a === "push-test") {
        await api("/push/test", "POST", {});
        notify(t("push_testSent"));
      }
    } catch (err) {
      notify(err.message);
    } finally {
      b.disabled = false;
    }
  });
  app.addEventListener("change", async (e) => {
    if (e.target.id !== "avatar-file" || !e.target.files[0]) return;
    try {
      const r = await api(
        "/profile/avatar",
        "POST",
        await avatarData(e.target.files[0]),
      );
      setMe({ ...me, avatar: r.avatar });
      notify(t("saved"));
      await loadExtras();
    } catch (err) {
      notify(err.message);
    }
  });
  app.addEventListener("submit", async (e) => {
    if (e.target.id !== "extra-form") return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const f = e.target,
      d = Object.fromEntries(new FormData(f));
    try {
      await api("/profile/extra", "PATCH", {
        motto: d.motto || "",
        hidden: !!d.hidden,
        ...(d.favorite_team_id
          ? { favorite_team_id: +d.favorite_team_id }
          : { clear_team: true }),
      });
      notify(t("saved"));
    } catch (err) {
      notify(err.message);
    }
  });
  app.addEventListener("change", async (e) => {
    if (e.target.id !== "season-pick") return;
    seasonChoice = +e.target.value;
    try {
      const html = await seasonPanel();
      document.querySelector("#season-panel").outerHTML = html;
      document.querySelector("#season-pick")?.focus();
    } catch (err) {
      notify(err.message);
    }
  });
}
