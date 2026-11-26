import {
  VERSION,
  api,
  app,
  badge,
  button,
  cat,
  catName,
  catalogs,
  date,
  esc,
  hooks,
  icon,
  input,
  lang,
  langButton,
  link,
  loadI18n,
  localizeRow,
  logo,
  me,
  notify,
  num,
  select,
  setCatalogs,
  setMe,
  t,
  uuid,
} from "./core.js";
import { drawBoard } from "./board.js";
import { clockData, refreshClock } from "./clock.js";
import { demoPage } from "./demo.js";
import { opsSetup, refreshTacChoice } from "./ops.js";
import {
  cancelBlock,
  hotseatSetup,
  inviteBlock,
  inviteLink,
  joinForm,
  joinPage,
  newMatchPage,
  pendingJoin,
} from "./quickstart.js";
import { closeSequence, sequenceButton } from "./reference.js";
import { loadRosterIndex, rosterSelect, rostersRoute } from "./rosters.js";
import { feedbackPanel, sharedPage } from "./share.js";
import { loadTeamIndex, teamsRoute } from "./teams.js";
import { opCountField } from "./opcount.js";
import { equipmentSetup } from "./equipment.js";
import { LOCAL_LIST, fillLocalPlayers, localField } from "./localplayers.js";
import { referenceRoute } from "./library.js";
import { coreRoute, rulesPage } from "./corerules.js";
import { tournamentsRoute } from "./tournaments.js";
import { adminPage } from "./admin.js";
import { styleguidePage } from "./styleguide.js";
import {
  clearOffline,
  enqueue,
  isDown,
  overlay,
  patch,
  queueable,
  queued,
} from "./offline.js";
import { resetSeen, watch } from "./live.js";
import { trackerChanged } from "./alerts.js";
import {
  avatarImg,
  playerLink,
  playerPage,
  profileExtras,
  seasonPanel,
  syncPush,
} from "./players.js";
import { nightsRoute, nextNightPanel } from "./nights.js";
import { mapButton, mapsRoute } from "./map.js";
import { tvPage } from "./tv.js";
import {
  groupPage,
  groupTitle,
  navHtml,
  refreshSummary,
  resetSummary,
} from "./groups.js";
import { SECTIONS } from "./sections.js";
export let page = "overview",
  currentMatch = null,
  poll = null,
  historyOffset = 0,
  historyFilters = {},
  auditOffset = 0;
export const setPage = (v) => (page = v);
export const setCurrentMatch = (v) => (currentMatch = v);
function authHeader() {
  return `<div class="hero">${logo()}<h1>${t("hero1")} <span class="accent">${t("hero2")}</span></h1><p class="sub">${t("heroText")}</p><ul class="hero-points"><li>${t("heroPoint1")}</li><li>${t("heroPoint2")}</li><li>${t("heroPoint3")}</li></ul></div>`;
}
export function renderAuth(register = false) {
  stopSync();
  app.innerHTML = `<main id="content" class="auth">${authHeader()}<section class="panel">${pendingJoin() ? `<p class="warning">${t("invitedBanner")} <span class="mono accent">${esc(pendingJoin())}</span></p>` : ""}<h2 class="section-label">${t(register ? "register" : "login")}</h2><form id="auth-form" data-register="${register}">${register ? input("username", "login", "text", "", 'required minlength="3" maxlength="64" pattern="[a-zA-Z0-9_.\\-]+" autocomplete="username"') + input("email", "email", "email", "", 'maxlength="254" autocomplete="email"') + input("nameOptional", "display_name", "text", "", 'maxlength="64" autocomplete="nickname"') : input("loginLabel", "identity", "text", "", 'required autocomplete="username" maxlength="254"')}${input("password", "password", "password", "", `required minlength="${register ? 12 : 1}" maxlength="128" autocomplete="${register ? "new-password" : "current-password"}"`)}${register ? `<p class="muted">${t("passwordHint")}</p>` : ""}<button>${t(register ? "register" : "login")}</button></form><p class="auth-switch">${t(register ? "hasAccount" : "noAccount")} ${button(t(register ? "login" : "register"), register ? "show-login" : "show-register")}</p>${register ? "" : `<p class="auth-switch">${button(t("rs_have"), "show-reset", "text")}</p>`}<p class="auth-switch"><a href="#demo">${t("demoTry")}</a></p><p class="auth-switch">${t("language")}: ${langButton()}</p></section></main>`;
}
/* v1.10: password reset with a one-time code from the administrator (#admin or ./scripts/admin.sh password). */
export function renderReset() {
  stopSync();
  app.innerHTML = `<main id="content" class="auth">${authHeader()}<section class="panel"><h2 class="section-label">${t("rs_title")}</h2><p class="muted">${t("rs_hint")}</p><form id="reset-form">${input("loginLabel", "identity", "text", "", 'required autocomplete="username" maxlength="254"')}${input("rs_code", "code", "text", "", 'required minlength="8" maxlength="16" autocomplete="one-time-code" autocapitalize="characters" spellcheck="false"')}${input("newPassword", "new_password", "password", "", 'required minlength="12" maxlength="128" autocomplete="new-password"')}<p class="muted">${t("passwordHint")}</p><button>${t("rs_submit")}</button></form><p class="auth-switch">${button(t("login"), "show-login")}</p></section></main>`;
}
/* v1.14: the menu by purpose (web/sections.js, web/groups.js); the pages of a section lead back to its group. */
export function shell(content) {
  app.innerHTML = `<header class="topbar">${logo()}<div class="row right"><a class="identity" href="#player/${esc(me.public_id)}">${avatarImg(me.public_id, me.avatar, "sm")}<span>${esc(me.display_name)}<span class="muted">#${esc(me.public_id)}</span></span></a>${langButton()}${button("◐", "theme", "secondary", `aria-label="${t("theme")}" title="${t("theme")}"`)}</div></header><aside class="sidebar"><nav aria-label="${t("navigation")}">${navHtml(page)}</nav><footer>KILLSTASS ${esc(VERSION)}<br>${t("localOps")}</footer></aside><div class="shell"><main id="content" class="stack" data-page="${esc(page)}">${content}</main></div>`;
  refreshSummary();
}
export function title(k) {
  return SECTIONS[k]
    ? groupTitle(k)
    : `<header class="page-title"><h1>${esc(t(k))}</h1></header>`;
}
/* v1.12: the pages of the «Rules» section lead back to it (v1.14: any group, web/groups.js). */
export const rulesTitle = (k) => groupTitle(k, page);
export function metrics(s) {
  return `<div class="metrics">${[
    ["games", s.games],
    ["winRate", s.win_rate],
    ["avgFor", s.avg_for],
    ["avgDiff", s.avg_diff],
  ]
    .map(
      ([k, v]) =>
        `<div class="metric"><strong ${k === "winRate" ? 'class="accent"' : ""}>${num(v)}</strong><span>${t(k)}</span></div>`,
    )
    .join("")}</div>`;
}
export function historyRows(items) {
  return items
    .map(
      (r) =>
        `<article class="list-item"><div><span class="eyebrow">${esc(date(r.played_at))} / ${t(r.kind)}</span><h3>${esc(r.opponent_name)} <span class="accent mono">${r.vp_for}:${r.vp_against}</span></h3><span class="muted">${esc(catName(r.team_id))}</span></div><div class="row">${badge(r.result)}${link(t("open"), "match/" + r.match_id)}</div></article>`,
    )
    .join("");
}
/* v1.9: tournament notifications open the tournament or the pairing's match.
   v1.10: game nights, the match of a night's table and achievements (own player page). */
function notificationLink(x) {
  if (!x.resource_id) return "";
  if (x.kind === "tournament_added")
    return link(t("open"), "tournaments/" + x.resource_id);
  if (["tournament_match", "night_match"].includes(x.kind))
    return link(t("open"), "match/" + x.resource_id);
  if (x.kind.startsWith("night_"))
    return link(t("open"), "nights/" + x.resource_id);
  if (x.kind === "achievement")
    return link(t("open"), "player/" + me.public_id);
  if (x.kind.startsWith("match_"))
    return link(t("open"), "match/" + x.resource_id);
  return "";
}
async function overview() {
  const [s, h, live, n, nights] = await Promise.all([
    api("/stats"),
    api("/history?limit=4"),
    api("/live-matches"),
    api("/notifications"),
    api("/nights").catch(() => []),
  ]);
  if (page !== "overview") return;
  shell(
    `${title("welcome", "TACTICAL LOG")}<div class="row between"><p class="muted">${t("hello")}, ${esc(me.display_name)}.</p><div class="row">${link("+ " + t("newGame"), "new", "button")}${link(t("quick"), "quick")}</div></div><section class="panel"><h2 class="section-label">${t("joinByCode")}</h2>${joinForm()}</section>${metrics(s.summary)}${nextNightPanel(nights)}<section class="panel"><h2 class="section-label">${t("live")}</h2>${live.length ? live.map((m) => `<div class="list-item"><div>${badge(m.status)} <span class="mono">${esc(m.id.slice(0, 8))}</span><p class="muted">${esc(catName(m.mission_id))}</p></div>${link(t("open"), "match/" + m.id)}</div>`).join("") : `<p class="empty">${t("emptyLive")}</p>`}</section><div class="grid"><section class="panel"><div class="row between"><h2>${t("recent")}</h2>${link(t("history"), "history")}</div>${h.items.length ? historyRows(h.items) : `<p class="empty">${t("emptyHistory")}</p>`}</section><section class="panel"><h2>${t("notifications")}</h2><div class="notifications">${
      n.some((x) => !x.read_at)
        ? n
            .filter((x) => !x.read_at)
            .map(
              (x) =>
                `<div class="list-item"><div><b>${esc(t(x.kind))}</b><p class="muted">${esc(date(x.created_at))}</p></div><div class="row">${notificationLink(x)}${button(t("read"), "read", "secondary", `data-id="${x.id}"`)}</div></div>`,
            )
            .join("")
        : `<p class="empty">${t("emptyNotifications")}</p>`
    }</div></section></div>`,
  );
}
function catalogFields(edition, values = {}) {
  return `<div class="grid" id="catalog-fields">${select("mission", "mission_id", cat("mission", edition), values.mission_id)}${select("killzone", "killzone_id", cat("killzone", edition), values.killzone_id)}${select("team1", "team1_id", cat("team", edition), values.team1_id)}${select("team2", "team2_id", cat("team", edition), values.team2_id)}</div>`;
}
export function editionField(value = "2024") {
  return select(
    "edition",
    "edition",
    [
      { id: "2024", label: "Kill Team 2024" },
      { id: "2021", label: "Kill Team 2021" },
    ],
    value,
  );
}
function quickPage() {
  const moscow = new Date(Date.now() + 3 * 3600000).toISOString().slice(0, 16);
  shell(
    `${title("quick", "AFTER ACTION REPORT")}<p class="muted">${t("quickText")}</p><p class="warning">${t("catalogNotice")}</p><section class="panel"><form id="quick-form"><label>${t("opponentType")}<select name="opponent_type"><option value="guest">${t("opponentGuest")}</option><option value="account">${t("opponentAccount")}</option></select></label><div id="quick-guest">${input("guestName", "guest_name", "text", "", `required maxlength="64" ${LOCAL_LIST}`)}${localField()}</div><div id="quick-account" hidden><label>${t("publicId")}<input name="opponent_public_id" list="quick-friends" disabled required minlength="8" maxlength="8" pattern="[A-Za-z0-9]{8}" autocapitalize="characters" autocomplete="off"></label><datalist id="quick-friends"></datalist><p class="muted">${t("recordedConfirmHint")}</p></div>${editionField()}${catalogFields("2024")}<div class="grid">${input("vpFor", "vp_for", "number", "0", 'required min="0" max="999"')}${input("vpAgainst", "vp_against", "number", "0", 'required min="0" max="999"')}${input("date", "played_at", "datetime-local", moscow, "required")}</div><label>${t("notes")}<textarea name="notes" maxlength="4000"></textarea></label><button>${t("save")}</button></form></section>`,
  );
  fillLocalPlayers();
  api("/friends")
    .then((f) => {
      const list = document.querySelector("#quick-friends");
      if (list)
        list.innerHTML = f.relations
          .filter((r) => r.status === "accepted")
          .map(
            (r) =>
              `<option value="${esc(r.public_id)}">${esc(r.display_name)}</option>`,
          )
          .join("");
    })
    .catch(() => {});
}
function filterForm() {
  return `<form id="filter-form" class="filters">${input("from", "from_date", "date", historyFilters.from_date || "")}${input("to", "to_date", "date", historyFilters.to_date || "")}${input("opponent", "opponent", "text", historyFilters.opponent || "", 'maxlength="64"')}${select(
    "team",
    "team_id",
    catalogs.filter((x) => x.kind === "team"),
    historyFilters.team_id,
    true,
  )}${select(
    "mission",
    "mission_id",
    catalogs.filter((x) => x.kind === "mission"),
    historyFilters.mission_id,
    true,
  )}${select(
    "killzone",
    "killzone_id",
    catalogs.filter((x) => x.kind === "killzone"),
    historyFilters.killzone_id,
    true,
  )}${select(
    "type",
    "kind",
    [
      { id: "friend", label: t("friend") },
      { id: "guest", label: t("guest") },
      { id: "hotseat", label: t("hotseat") },
    ],
    historyFilters.kind,
    true,
  )}<button>${t("filter")}</button></form>`;
}
const filterQuery = () => new URLSearchParams(historyFilters).toString();
async function historyPage() {
  const data = await api(`/history?${filterQuery()}&offset=${historyOffset}`);
  if (page !== "history") return;
  shell(
    `${title("history", "MISSION ARCHIVE")}<section class="panel">${filterForm()}</section><section class="panel"><div class="row between"><h2>${t("total")}: ${data.total}</h2><div class="row"><a class="button secondary" href="/api/export?format=csv&${esc(filterQuery())}">${t("exportCsv")}</a><a class="button secondary" href="/api/export?format=json&${esc(filterQuery())}">${t("exportJson")}</a></div></div>${lang === "en" ? `<p class="muted">${t("exportLangNote")}</p>` : ""}${data.items.length ? historyRows(data.items) : `<p class="empty">${t("emptyHistory")}</p>`}<div class="row pagination">${button(t("previous"), "prev-history", "secondary", historyOffset ? "" : "disabled")}${button(t("next"), "next-history", "secondary", historyOffset + 20 < data.total ? "" : "disabled")}</div></section>`,
  );
}
async function friendsPage() {
  const [f, ch] = await Promise.all([api("/friends"), api("/challenges")]);
  if (page !== "friends") return;
  shell(
    `${title("friends", "COMMS CHANNEL")}<div class="grid"><section class="panel"><h2>${t("addFriend")}</h2><form id="friend-form">${input("publicId", "public_id", "text", "", 'required minlength="8" maxlength="8" autocapitalize="characters"')}<button>${t("send")}</button></form></section><section class="panel"><h2>${t("publicId")}</h2><h2 class="mono accent">${esc(me.public_id)}</h2>${button(t("copy"), "copy")}</section></div><section class="panel"><h2>${t("friends")}</h2>${f.relations.length ? f.relations.map((r) => `<div class="list-item"><div><h3>${r.status === "accepted" ? playerLink(r.public_id, r.display_name) : esc(r.display_name)}</h3><span class="mono muted">${esc(r.public_id)} / ${t(r.status)}${r.status === "pending" ? " / " + t(r.outgoing ? "outgoing" : "incoming") : ""}</span></div><div class="row">${r.status === "accepted" ? button(t("challenge"), "challenge-form", "", `data-id="${esc(r.public_id)}"`) + friendButton("remove", r.public_id) : r.outgoing ? friendButton("cancel", r.public_id) : friendButton("accept", r.public_id) + friendButton("decline", r.public_id)}${friendButton("block", r.public_id)}</div></div>`).join("") : `<p class="empty">${t("emptyFriends")}</p>`}</section><section class="panel"><h2>${t("challenges")}</h2>${ch.length ? ch.map((c) => `<div class="list-item"><div><h3>${esc(c.sender_name || t("opponentDeleted"))} → ${esc(c.recipient_name || t("opponentDeleted"))}</h3>${badge(c.status)} <span class="muted">${esc(date(c.expires_at))}</span><p class="muted">${esc(c.proposal.mode || "")} / ${esc(catName(c.proposal.mission_id))}</p></div><div class="row">${c.status === "pending" ? (c.sender_id === me.id ? challengeButton("cancelled", c.id, "cancel") : challengeButton("accepted", c.id, "accept") + challengeButton("declined", c.id, "decline")) : ""}${c.match_id ? link(t("open"), "match/" + c.match_id) : ""}</div></div>`).join("") : `<p class="empty">${t("emptyNotifications")}</p>`}</section>${f.blocks.length ? `<section class="panel"><h2>${t("blocks")}</h2>${f.blocks.map((r) => `<div class="list-item">${esc(r.display_name)} ${friendButton("unblock", r.public_id)}</div>`).join("")}</section>` : ""}`,
  );
}
function friendButton(action, id) {
  return button(
    t(action),
    "friend-action",
    "secondary",
    `data-id="${esc(id)}" data-kind="${action}"`,
  );
}
function challengeButton(action, id, label) {
  return button(
    t(label),
    "challenge-action",
    "secondary",
    `data-id="${id}" data-kind="${action}"`,
  );
}
function challengeForm(id) {
  shell(
    `${title("challenge", "NEW OPERATION")}<section class="panel"><h2>${t("challengeTo")} ${esc(id)}</h2><form id="challenge-form" data-id="${esc(id)}">${editionField()}<div id="challenge-mission">${select("mission", "mission_id", cat("mission", "2024"))}</div>${input("mode", "mode", "text", t("ordinary"), 'required maxlength="80"')}<button>${t("send")}</button></form></section>`,
  );
}
function objectives(edition, ids = []) {
  return `<fieldset id="objective-fields"><legend>${t("objectives")}</legend>${cat(
    "objective",
    edition,
  )
    .map(
      (o) =>
        `<label><input type="checkbox" name="objective_ids" value="${o.id}" ${ids.includes(o.id) ? "checked" : ""}>${esc(o.label)}</label>`,
    )
    .join("")}</fieldset>`;
}
function setupForm(m) {
  const own = m.players.find((p) => p.user_id === me.id);
  return `<section class="panel"><h2>${t("setup")}</h2><p class="warning">${t("catalogNotice")}</p><form id="setup-form">${editionField(m.edition)}${catalogFields(m.edition, { mission_id: m.mission_id, killzone_id: m.killzone_id, team1_id: m.players[0].team_id, team2_id: m.players[1].team_id })}<div id="mission-info"></div><div class="grid">${input("turns", "turns", "number", m.turns, 'required min="1" max="12"')}${select(
    "initiative",
    "initiative",
    [
      { id: 1, label: "1 — " + m.players[0].display_name },
      { id: 2, label: "2 — " + m.players[1].display_name },
    ],
    m.initiative,
  )}${opCountField(own, "team" + own.slot + "_id")}</div>${m.edition === "2024" ? opsSetup(m) : objectives(m.edition, m.setup.objective_ids)}${rosterSelect(own, own.team_id)}<label>${t("roster")}<textarea name="roster" maxlength="4000">${esc(own.roster)}</textarea></label><label>${t("ruleNotes")}<textarea name="rule_notes" maxlength="2000">${esc(m.setup.rule_notes || "")}</textarea></label><label>${t("notes")}<textarea name="notes" maxlength="4000">${esc(m.notes)}</textarea></label><button>${t("save")}</button></form><p></p>${button(t("start"), "match-action", "", `data-kind="start"`)}</section>`;
}
function auditList(rows) {
  return rows
    .map(
      (a) =>
        `<div class="audit list-item"><div><span class="muted">${esc(date(a.created_at))}</span><br><b>${esc(t(a.action === "score" ? "scoreChange" : a.action))}</b> / ${esc(a.actor_id === me.id ? t("you") : t("opponent"))}<p class="mono">${esc(JSON.stringify(a.before_data))} → ${esc(JSON.stringify(a.after_data))}</p></div></div>`,
    )
    .join("");
}
/* v1.10: the server snapshot plus board commands still waiting in the offline queue. */
const fetchMatch = async (id) => overlay(await api("/matches/" + id));
async function matchPage(id) {
  const m = await fetchMatch(id);
  if (m.status === "setup") await loadRosterIndex();
  if (location.hash !== "#match/" + id) return;
  currentMatch = m;
  auditOffset = 0;
  drawMatch(m);
  startSync(m);
}
export function drawMatch(m) {
  if (m.demo) return m.demo.draw(m);
  if (m.status === "setup") queueMicrotask(refreshTacChoice);
  shell(
    `<header class="match-header"><p class="row">${sequenceButton(m)}${mapButton(m)}</p><div class="row between"><span class="eyebrow">OPERATION / ${esc(m.id.slice(0, 8))}</span>${badge(m.status)}</div><h1>${esc(catName(m.mission_id))}</h1><p class="muted">${t("edition")} ${m.edition} · ${esc(catName(m.killzone_id))} · ${esc(date(m.played_at))}</p></header>${
      m.status === "setup"
        ? inviteBlock(m) +
          setupForm(m) +
          equipmentSetup(m) +
          hotseatSetup(m) +
          cancelBlock(m)
        : drawBoard(m)
    }<section class="panel"><details id="audit-detail"><summary>${t("audit")}</summary><div id="audit-list"></div>${button(t("loadMore"), "audit-more")}</details></section>`,
  );
}
function stopSync() {
  watch({}, {});
  clearInterval(poll);
  poll = null;
}
function startSync(m) {
  stopSync();
  const id = m.id;
  const refresh = async () => {
    if (document.hidden || !location.hash.endsWith(id)) return;
    try {
      const next = await fetchMatch(id);
      if (currentMatch?.id !== id) return;
      if (
        next.version !== currentMatch.version ||
        next.tracker_seq !== currentMatch.tracker_seq
      ) {
        const focused = document.activeElement;
        if (
          focused &&
          ["INPUT", "TEXTAREA", "SELECT"].includes(focused.tagName)
        ) {
          notify(t("remoteChange"));
          return;
        }
        const before = currentMatch;
        currentMatch = next;
        drawMatch(next);
        if (!next.cachedCopy) trackerChanged(before, next);
      }
    } catch (e) {
      if (e.code !== "network") notify(e.message);
    }
  };
  // v1.10: one event stream per tab (web/live.js); v1.9: tracker taps do not change matches.version.
  watch(
    { match: id },
    {
      revision: (v) => v !== currentMatch?.version && refresh(),
      clock: (v) => v !== clockData?.state.seq && refreshClock(),
      tracker: (v) => v !== currentMatch?.tracker_seq && refresh(),
    },
  );
  poll = setInterval(refresh, 10000);
}
/* v1.10: after the offline queue was sent, show the server's view of the open match. */
export async function afterFlush(ids) {
  if (!currentMatch || currentMatch.demo || !ids.includes(currentMatch.id))
    return;
  try {
    currentMatch = await fetchMatch(currentMatch.id);
    drawMatch(currentMatch);
    refreshClock();
  } catch {}
}
export const slotOf = (el) =>
  el.dataset.slot ? { slot: +el.dataset.slot } : {};
/* Board commands. Tracker and undo calls are not versioned (versioned=false); the demo board
   (currentMatch.demo) applies the same commands to its local state instead of the server.
   v1.10: without a connection scoreboard commands go to the offline queue (web/offline.js) and show at once;
   while the queue is not empty new commands wait behind it, so the order stays the same. */
export async function updateMatch(path, payload, versioned = true) {
  if (currentMatch.demo) {
    currentMatch = currentMatch.demo.apply(path, payload);
    drawMatch(currentMatch);
    return;
  }
  const mid = currentMatch.id,
    canQueue = queueable(path, payload);
  const local = (body) => {
    enqueue(mid, {
      kind: "match",
      path,
      payload,
      versioned,
      request_id: body?.request_id || uuid(),
      body: body || null,
    });
    // The board already shows the earlier queued commands: add only this one.
    currentMatch = patch(currentMatch, path, payload);
    drawMatch(currentMatch);
  };
  if (canQueue && (isDown() || queued(mid).length)) return local(null);
  const body = {
    request_id: uuid(),
    ...(versioned ? { version: currentMatch.version } : {}),
    ...payload,
  };
  try {
    await api("/matches/" + mid + path, "POST", body);
  } catch (e) {
    if (e.code === "network" && canQueue) return local(body);
    throw e;
  }
  currentMatch = await fetchMatch(mid);
  drawMatch(currentMatch);
}
function trendChart(rows) {
  if (!rows.length) return "";
  const max = Math.max(1, ...rows.flatMap((r) => [+r.avg_for, +r.avg_against]));
  const width = 640,
    height = 260,
    left = 52,
    right = 20,
    top = 18,
    bottom = 42;
  const gap = rows.length > 1 ? (width - left - right) / (rows.length - 1) : 0;
  const x = (i) => (rows.length === 1 ? width / 2 : left + i * gap);
  const y = (v) => height - bottom - (+v / max) * (height - top - bottom);
  let paths = "";
  for (const [k, cl] of [
    ["avg_for", "for"],
    ["avg_against", "against"],
  ]) {
    let previous = null;
    rows.forEach((r, i) => {
      const month = new Date(r.month + "-01T00:00:00Z");
      if (previous && month - previous.date < 32 * 86400000) {
        paths += `<path class="${cl}" d="M${x(i - 1)},${y(rows[i - 1][k])} L${x(i)},${y(r[k])}"/>`;
      }
      paths += `<circle class="${cl}-point" cx="${x(i)}" cy="${y(r[k])}" r="${cl === "for" ? 4 : 2}"/>`;
      previous = { date: month };
    });
  }
  return `<svg class="chart" viewBox="0 0 640 260" role="img" aria-label="${esc(t("trend"))}">${[0, 0.5, 1].map((v) => `<line x1="${left}" x2="620" y1="${y(v * max)}" y2="${y(v * max)}" stroke="currentColor" opacity=".15"/><text x="8" y="${y(v * max) + 4}">${num(v * max)}</text>`).join("")}${paths}${rows
    .filter((_, i) => i === 0 || i === rows.length - 1)
    .map(
      (r) =>
        `<text x="${r === rows[0] ? left : 620}" y="248" text-anchor="${r === rows[0] ? "start" : "end"}">${esc(r.month)}</text>`,
    )
    .join("")}</svg>`;
}
function statTable(rows, field = "") {
  return `<div class="table-wrap" tabindex="0"><table><thead><tr><th>${t("name")}</th><th>${t("games")}</th><th>${t("wins")}</th><th>${t("draws")}</th><th>${t("losses")}</th><th>Δ VP</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc((field !== "opponent_id" && r.key && catalogs.some((x) => x.id === r.key) ? catName(r.key) : r.label) || "—")}</td><td>${r.games}</td><td>${r.wins}</td><td>${r.draws}</td><td>${r.losses}</td><td>${num(r.avg_diff)}</td></tr>`).join("")}</tbody></table></div>`;
}
function winRing(value) {
  const circumference = 2 * Math.PI * 58;
  const progress =
    (Math.max(0, Math.min(100, Number(value))) / 100) * circumference;
  return `<svg class="win-ring" viewBox="0 0 140 140" role="img" aria-label="${t("winRate")}: ${num(value)}%"><circle class="ring-track" cx="70" cy="70" r="58"/><circle class="ring-progress" cx="70" cy="70" r="58" stroke-dasharray="${progress} ${circumference}" transform="rotate(-90 70 70)"/><text x="70" y="78" text-anchor="middle">${num(value)}%</text></svg>`;
}
/* v1.9: game clock time and the Elo rating among friends. */
export function dur(s) {
  if (s == null) return "—";
  const v = Math.max(0, Math.round(s)),
    h = Math.floor(v / 3600),
    m = Math.floor((v % 3600) / 60),
    x = String(v % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${x}` : `${m}:${x}`;
}
function clockStats(c) {
  if (!c?.games) return "";
  return `<section class="panel"><h2>${t("clockStats")}</h2><div class="metrics">${[
    [dur(c.avg_total_seconds), "clockAvgGame"],
    [dur(c.max_total_seconds), "clockLongest"],
    ...(c.split_games
      ? [
          [dur(c.avg_own_seconds), "clockAvgOwn"],
          [dur(c.avg_opponent_seconds), "clockAvgOpponent"],
        ]
      : []),
  ]
    .map(
      ([v, k]) =>
        `<div class="metric"><strong class="mono">${esc(v)}</strong><span>${t(k)}</span></div>`,
    )
    .join(
      "",
    )}</div><p class="muted">${t("clockStatsHint")}: ${c.games}${c.split_games ? ` · ${t("clockSplitHint")}: ${c.split_games}` : ""}</p></section>`;
}
/* v1.13: the rating is among friends or across the club (with local players); the choice is remembered. */
let ratingsScope =
  localStorage.getItem("killstass-ratings") === "all" ? "all" : "friends";
function ratingsPanel(r) {
  if (!r) return "";
  const scope = r.scope === "all" ? "all" : "friends";
  return `<section class="panel" id="ratings-panel"><div class="row between"><h2>${t("ratings")}</h2><div class="row" role="group" aria-label="${esc(t("ratingsScope"))}">${["friends", "all"].map((s) => button(t("ratings_" + s), "ratings-scope", scope === s ? "selected small" : "secondary small", `data-scope="${s}" aria-pressed="${scope === s}"`)).join("")}</div></div><p class="muted">${t(scope === "all" ? "ratingsAllHint" : "ratingsHint")}</p>${
    r.games
      ? `<div class="table-wrap" tabindex="0"><table class="ratings"><thead><tr><th>#</th><th>${t("name")}</th><th>Elo</th><th>${t("games")}</th><th>${t("wins")}</th><th>${t("draws")}</th><th>${t("losses")}</th></tr></thead><tbody>${r.players
          .map(
            (p) =>
              `<tr class="${p.me ? "me" : ""}"><td>${p.rank}</td><td>${playerLink(p.public_id, p.display_name)}${p.me ? ` <span class="muted">(${t("you")})</span>` : ""}${p.local ? ` <span class="badge local">${t("localBadge")}</span>` : ""}</td><td><b>${p.rating}</b></td><td>${p.games}</td><td>${p.wins}</td><td>${p.draws}</td><td>${p.losses}</td></tr>`,
          )
          .join("")}</tbody></table></div>`
      : `<p class="empty">${t("ratingsEmpty")}</p>`
  }</section>`;
}
/* v1.14: the viewer's ploys in the filtered matches (the board's protocol). */
function ployStats(rows) {
  if (!rows?.length) return "";
  return `<section class="panel"><h2>${t("ployStats")}</h2><div class="table-wrap" tabindex="0"><table><thead><tr><th>Ploy</th><th>${t("ployKind")}</th><th>${t("ployUses")}</th><th>${t("games")}</th><th>CP</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.name)}</td><td>${esc(t(r.kind === "strategy" ? "ployStrategy" : "ployFirefight"))}</td><td>${r.uses}</td><td>${r.games}</td><td>${r.cp}</td></tr>`).join("")}</tbody></table></div></section>`;
}
async function statsPage() {
  const [d, tacData, ratings, season, ploys] = await Promise.all([
    api("/stats?" + filterQuery()),
    api("/stats/tac-ops?" + filterQuery()),
    api("/ratings?scope=" + ratingsScope).catch(() => null),
    seasonPanel().catch(() => ""),
    api("/stats/ploys?" + filterQuery()).catch(() => []),
  ]);
  if (page !== "stats") return;
  shell(
    `${title("stats", "BATTLE INTELLIGENCE")}<section class="panel">${filterForm()}</section>${metrics(d.summary)}${season}${ratingsPanel(ratings)}<section class="panel"><h2>${t("tacStats")}</h2><div class="table-wrap" tabindex="0"><table><thead><tr><th>${t("tacOp")}</th><th>${t("games")}</th><th>VP</th><th>${t("avgTacVp")}</th></tr></thead><tbody>${tacData.map((r) => `<tr><td>${esc(catalogs.some((x) => x.id === r.tac_op_id) ? catName(r.tac_op_id) : r.label)}</td><td>${r.games}</td><td>${r.vp}</td><td>${num(r.avg_vp)}</td></tr>`).join("")}</tbody></table></div></section>${ployStats(ploys)}${
      !d.summary.games
        ? `<section class="panel empty">${t("emptyStats")}</section>`
        : `<div class="grid"><section class="panel"><h2>${t("winRate")}</h2><div class="row">${winRing(d.summary.win_rate)}<div><p>${d.summary.wins} ${t("wins")} / ${d.summary.draws} ${t("draws")} / ${d.summary.losses} ${t("losses")}</p><p class="muted">${t("streak")}: ${t("current")} ${d.streak.current} · ${t("best")} ${d.streak.best}</p><p class="muted">${t("avgAgainst")}: ${num(d.summary.avg_against)}</p></div></div></section><section class="panel"><h2>${t("trend")}</h2>${trendChart(d.trend)}<p class="muted">${t("trendHint")}</p><details><summary>${t("score")}</summary><table><thead><tr><th>${t("dateLabel")}</th><th>${t("avgFor")}</th><th>${t("avgAgainst")}</th></tr></thead><tbody>${d.trend.map((r) => `<tr><td>${esc(r.month)}</td><td>${num(r.avg_for)}</td><td>${num(r.avg_against)}</td></tr>`).join("")}</tbody></table></details></section></div><section class="panel">${[
            ["team_id", "byTeam"],
            ["roster_id", "byRoster"],
            ["opponent_team_id", "byOpponentTeam"],
            ["mission_id", "byMission"],
            ["killzone_id", "byKillzone"],
            ["opponent_id", "headToHead"],
          ]
            .filter(([k]) => d.breakdown[k]?.length || k !== "roster_id")
            .map(
              ([k, label]) =>
                `<details open><summary>${t(label)}</summary>${statTable(d.breakdown[k], k)}</details>`,
            )
            .join("")}</section>${clockStats(d.clock)}`
    }`,
  );
}
function profilePage() {
  /* v1.14: on a phone the bottom bar has no «Admin» item — administrators open it from here */
  const admin = me.is_admin
    ? `<section class="panel profile-admin"><h2>${t("admin")}</h2><p class="muted">${t("profileAdminHint")}</p><a class="button secondary" href="#admin">${icon("gear")}<span>${t("profileAdminOpen")}</span></a></section>`
    : "";
  shell(
    `${title("profile", "OPERATOR FILE")}${admin}<section class="panel"><h2>${t("language")}</h2><div class="row">${langButton()}<span class="muted">${t("langSaved")}</span></div></section><div class="grid"><section class="panel"><h2>${t("publicId")}</h2><h2 class="mono accent">${esc(me.public_id)}</h2>${button(t("copy"), "copy")}<p></p><form id="profile-form">${input("name", "display_name", "text", me.display_name, 'required maxlength="64"')}<button>${t("save")}</button></form></section><section class="panel"><h2>${t("changePassword")}</h2><form id="password-form">${input("currentPassword", "current_password", "password", "", 'required autocomplete="current-password" maxlength="128"')}${input("newPassword", "new_password", "password", "", 'required minlength="12" maxlength="128" autocomplete="new-password"')}<button>${t("changePassword")}</button></form></section></div><div id="profile-extra">${profileExtras()}</div><section class="panel"><h2>${t("security")}</h2>${button(t("logout"), "logout")}<details><summary>${t("deleteAccount")}</summary><p class="warning">${t("deleteWarning")}</p><form id="delete-form">${input("currentPassword", "password", "password", "", 'required autocomplete="current-password" maxlength="128"')}<button class="danger">${t("deleteAccount")}</button></form></details></section>${feedbackPanel()}`,
  );
}
/* v1.14 (Т1): the signed-in pages by the first part of the address (the menu and groups — web/sections.js). */
const ROUTES = {
  overview: () => overview(),
  match: (p) => matchPage(p[0]),
  quick: () => quickPage(),
  new: () => newMatchPage(),
  join: (p) => joinPage(p[0]),
  muster: () => groupPage("muster"),
  rosters: (p) => rostersRoute(p),
  maps: (p) => mapsRoute("maps", p),
  map: (p) => mapsRoute("map", p),
  results: () => groupPage("results"),
  history: () => historyPage(),
  stats: () => statsPage(),
  club: () => groupPage("club"),
  friends: () => friendsPage(),
  player: (p) => playerPage(p[0]),
  nights: (p) => nightsRoute(p),
  tournaments: (p) => tournamentsRoute(p),
  rules: () => rulesPage(),
  reference: (p) => referenceRoute(p),
  core: (p) => coreRoute(p),
  teams: (p) => teamsRoute(p),
  profile: () => profilePage(),
  admin: () => adminPage(),
};
async function route() {
  stopSync();
  currentMatch = null; // v1.9: board handlers act only while a match (or the demo) is on screen
  page = (location.hash.slice(1) || "overview").split("/")[0];
  const parts = location.hash.split("/").slice(1);
  // v1.5: demo and read-only result links work without a session; v1.10: the club TV screen too.
  if (page === "demo") return demoPage();
  if (page === "styleguide") return styleguidePage();
  if (page === "shared") return sharedPage(parts[0]);
  if (page === "tv") return tvPage(parts[0]);
  if (!me) return renderAuth(!!pendingJoin());
  try {
    const go = ROUTES[page];
    if (go) await go(parts);
    else shell(title("notFound"));
  } catch (e) {
    shell(
      `<section class="panel"><h1>${esc(t("routeErrorTitle"))}</h1><p>${esc(e.message || t("routeErrorFallback"))}</p><p><a href="#overview">${esc(t("routeErrorHome"))}</a></p></section>`,
    );
    notify(e.message);
  }
}
/* v1.10: after sign-in (password or reset code) — session, catalogs and the page. */
async function signedIn() {
  setMe(await api("/auth/me"));
  resetSeen();
  setCatalogs(
    (await api("/catalogs?include_inactive=true")).map((x) => localizeRow(x)),
  );
  await loadTeamIndex();
  await route();
  syncPush().catch(() => {});
}
export function signOut() {
  clearOffline();
  resetSummary();
  setMe(null);
  watch({}, {});
  closeSequence();
  renderAuth();
}

async function loadAudit() {
  const rows = await api(
    "/matches/" + currentMatch.id + "/audit?offset=" + auditOffset,
  );
  document
    .querySelector("#audit-list")
    .insertAdjacentHTML("beforeend", auditList(rows));
  auditOffset += rows.length;
  if (!rows.length) notify(t("emptyAudit"));
}

export async function boot() {
  try {
    let theme = null;
    try {
      theme = localStorage.getItem("killstass-theme");
    } catch {}
    document.documentElement.dataset.theme =
      theme ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    await loadI18n();
    document.querySelector(".skip").textContent = t("skip");
    try {
      setMe(await api("/auth/me"));
      setCatalogs(
        (await api("/catalogs?include_inactive=true")).map((x) =>
          localizeRow(x),
        ),
      );
      await loadTeamIndex();
    } catch {
      setMe(null);
    }
    await route();
    window.killstassBootReady?.();
  } catch (e) {
    window.killstassBootFailed?.();
    notify(e.message);
  }
}
export const rerender = () => route();

/* v1.9: listeners are registered from main.js in a fixed order (the former <script> order). */
export function init() {
  hooks.unauthorized = () => {
    closeSequence();
    watch({}, {});
    renderAuth(false);
  };
  app.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b || b.disabled) return;
    const a = b.dataset.action;
    b.disabled = true;
    try {
      if (a === "show-login") renderAuth();
      else if (a === "show-register") renderAuth(true);
      else if (a === "show-reset") renderReset();
      else if (a === "lang") {
        try {
          localStorage.setItem("killstass-lang", lang === "en" ? "ru" : "en");
        } catch {}
        location.reload();
      } else if (a === "theme") {
        const theme =
          document.documentElement.dataset.theme === "dark" ? "light" : "dark";
        document.documentElement.dataset.theme = theme;
        try {
          localStorage.setItem("killstass-theme", theme);
        } catch {}
      } else if (a === "copy") {
        await navigator.clipboard.writeText(me.public_id);
        notify(t("copied"));
      } else if (a === "logout") {
        await api("/auth/logout", "POST", {});
        signOut();
      } else if (a === "friend-action") {
        await api("/friends/" + b.dataset.id, "POST", {
          action: b.dataset.kind,
        });
        await friendsPage();
      } else if (a === "challenge-form") challengeForm(b.dataset.id);
      else if (a === "challenge-action") {
        const r = await api("/challenges/" + b.dataset.id, "POST", {
          action: b.dataset.kind,
          request_id: uuid(),
        });
        if (r.match_id) location.hash = "match/" + r.match_id;
        else await friendsPage();
      } else if (a === "read") {
        await api("/notifications/" + b.dataset.id + "/read", "POST", {});
        await overview();
      } else if (a === "primary-commit")
        await updateMatch("/primary", {
          primary_op: document.querySelector(
            b.dataset.slot
              ? "#primary-active-" + b.dataset.slot
              : "#primary-active",
          ).value,
          ...slotOf(b),
        });
      else if (a === "reveal-tac") await updateMatch("/reveal-tac", slotOf(b));
      else if (a === "kills")
        await updateMatch("/kills", {
          turning_point: currentMatch.current_turn,
          delta: +b.dataset.delta,
          ...slotOf(b),
        });
      else if (a === "score")
        await updateMatch("/scores", {
          turning_point: +b.dataset.tp || currentMatch.current_turn,
          source_id: +b.dataset.source,
          delta: +b.dataset.delta,
          ...slotOf(b),
        });
      else if (a === "cp")
        await updateMatch("/scores", {
          turning_point: currentMatch.current_turn,
          cp: +b.dataset.value,
          ...slotOf(b),
        });
      else if (a === "new-invite") {
        await api("/matches/" + currentMatch.id + "/invite", "POST", {
          request_id: uuid(),
        });
        currentMatch = await api("/matches/" + currentMatch.id);
        drawMatch(currentMatch);
      } else if (a === "copy-invite") {
        await navigator.clipboard.writeText(inviteLink(b.dataset.code));
        notify(t("copied"));
      } else if (a === "share-invite")
        await navigator
          .share({
            title: "KILLSTASS",
            text: t("shareInviteText") + " " + b.dataset.code,
            url: inviteLink(b.dataset.code),
          })
          .catch(() => {});
      else if (a === "cancel-match") {
        if (confirm(t("cancelConfirm")))
          await updateMatch("/actions", { action: "cancel" });
      } else if (a === "turn")
        await updateMatch("/actions", {
          action: "turn",
          turning_point: +b.dataset.value,
        });
      else if (a === "match-action")
        await updateMatch("/actions", {
          action: b.dataset.kind,
          ...(b.dataset.kind === "concede" ? { slot: +b.dataset.slot } : {}),
        });
      else if (a === "next-history") {
        historyOffset += 20;
        await historyPage();
      } else if (a === "prev-history") {
        historyOffset = Math.max(0, historyOffset - 20);
        await historyPage();
      } else if (a === "audit-more") await loadAudit();
      else if (a === "ratings-scope") {
        ratingsScope = b.dataset.scope === "all" ? "all" : "friends";
        localStorage.setItem("killstass-ratings", ratingsScope);
        const r = await api("/ratings?scope=" + ratingsScope),
          el = document.getElementById("ratings-panel");
        if (el && page === "stats") {
          el.outerHTML = ratingsPanel(r);
          document
            .querySelector(
              `[data-action="ratings-scope"][data-scope="${ratingsScope}"]`,
            )
            ?.focus();
        }
      }
    } catch (err) {
      notify(err.message);
    } finally {
      b.disabled = false;
    }
  });
  app.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target,
      b = f.querySelector("button[type=submit],button:not([type])");
    if (b) b.disabled = true;
    const data = Object.fromEntries(new FormData(f));
    try {
      if (f.id === "auth-form") {
        if (f.dataset.register === "true" && !data.email) delete data.email;
        await api(
          f.dataset.register === "true" ? "/auth/register" : "/auth/login",
          "POST",
          data,
        );
        await signedIn();
      } else if (f.id === "reset-form") {
        data.code = data.code.trim().toUpperCase();
        await api("/auth/password-reset", "POST", data);
        notify(t("rs_done"));
        await signedIn();
      } else if (f.id.startsWith("new-match-form")) {
        const r = await api("/matches", "POST", {
          request_id: uuid(),
          kind: f.dataset.kind,
          edition: data.edition,
          ...(f.dataset.kind === "hotseat"
            ? { guest_name: data.guest_name, local: data.local === "1" }
            : {}),
        });
        if (f.dataset.kind === "friend")
          await api("/matches/" + r.id + "/invite", "POST", {
            request_id: uuid(),
          });
        location.hash = "match/" + r.id;
      } else if (f.id === "join-form") {
        location.hash = "join/" + data.code.trim().toUpperCase();
      } else if (f.id === "player-setup-form") {
        const body = {
          request_id: uuid(),
          version: currentMatch.version,
          slot: +f.dataset.slot,
          roster: data.roster || "",
          roster_id: data.roster_id || null,
          operative_count: data.operative_count ? +data.operative_count : null,
          operative_manual: data.operative_manual === "1",
        };
        if (data.primary_op) body.primary_op = data.primary_op;
        if (data.tac_op_id !== undefined)
          body.tac_op_id = data.tac_op_id ? +data.tac_op_id : null;
        const counts = {};
        for (const k of [
          "dire_avenger",
          "howling_banshee",
          "striking_scorpion",
        ])
          if (+data["aspect_" + k]) counts[k] = +data["aspect_" + k];
        if (Object.keys(counts).length)
          for (const k of [
            "dire_avenger",
            "howling_banshee",
            "striking_scorpion",
          ])
            counts[k] ||= 0;
        body.aspect_counts = counts;
        await api("/matches/" + currentMatch.id + "/player-setup", "PUT", body);
        currentMatch = await api("/matches/" + currentMatch.id);
        drawMatch(currentMatch);
        notify(t("guestSecretSaved"));
      } else if (f.id === "friend-form") {
        await api("/friends", "POST", data);
        await friendsPage();
      } else if (f.id === "challenge-form") {
        data.request_id = uuid();
        data.public_id = f.dataset.id;
        data.mission_id = +data.mission_id;
        await api("/challenges", "POST", data);
        await friendsPage();
      } else if (f.id === "quick-form") {
        for (const key of [
          "team1_id",
          "team2_id",
          "mission_id",
          "killzone_id",
          "vp_for",
          "vp_against",
        ])
          data[key] = +data[key];
        data.played_at = new Date(data.played_at + ":00+03:00").toISOString();
        data.request_id = uuid();
        data.local = data.local === "1";
        delete data.opponent_type;
        if (data.opponent_public_id)
          data.opponent_public_id = data.opponent_public_id
            .trim()
            .toUpperCase();
        const r = await api("/quick-matches", "POST", data);
        location.hash = "match/" + r.id;
      } else if (f.id === "setup-form") {
        data.objective_ids = new FormData(f)
          .getAll("objective_ids")
          .map(Number);
        for (const key of [
          "team1_id",
          "team2_id",
          "mission_id",
          "killzone_id",
          "turns",
          "initiative",
        ])
          data[key] = +data[key];
        data.operative_count = data.operative_count
          ? +data.operative_count
          : null;
        data.operative_manual = data.operative_manual === "1";
        if (data.tac_op_id !== undefined)
          data.tac_op_id = data.tac_op_id ? +data.tac_op_id : null;
        data.aspect_counts = {};
        for (const k of [
          "dire_avenger",
          "howling_banshee",
          "striking_scorpion",
        ]) {
          if (+data["aspect_" + k])
            data.aspect_counts[k] = +data["aspect_" + k];
          delete data["aspect_" + k];
        }
        if (Object.keys(data.aspect_counts).length)
          for (const k of [
            "dire_avenger",
            "howling_banshee",
            "striking_scorpion",
          ])
            data.aspect_counts[k] ||= 0;
        data.roster_id = data.roster_id || null;
        data.request_id = uuid();
        data.version = currentMatch.version;
        await api("/matches/" + currentMatch.id + "/setup", "PUT", data);
        currentMatch = await api("/matches/" + currentMatch.id);
        drawMatch(currentMatch);
        notify(t("saved"));
      } else if (f.classList.contains("turn-notes-form")) {
        await updateMatch("/scores", {
          turning_point: currentMatch.current_turn,
          notes: data.notes,
          ...slotOf(f),
        });
        notify(t("notesSaved"));
      } else if (f.id === "filter-form") {
        historyFilters = Object.fromEntries(
          Object.entries(data).filter(([, v]) => v !== ""),
        );
        historyOffset = 0;
        if (page === "stats") await statsPage();
        else await historyPage();
      } else if (f.id === "profile-form") {
        await api("/profile", "PATCH", data);
        setMe(await api("/auth/me"));
        profilePage();
        notify(t("saved"));
      } else if (f.id === "password-form") {
        const r = await api("/profile/password", "POST", data);
        me.csrf = r.csrf;
        f.reset();
        notify(t("saved"));
      } else if (f.id === "delete-form" && confirm(t("deleteConfirm"))) {
        await api("/profile", "DELETE", data);
        signOut();
      }
    } catch (err) {
      notify(err.message);
    } finally {
      if (b) b.disabled = false;
    }
  });
  app.addEventListener("change", (e) => {
    if (
      e.target.name === "opponent_type" &&
      e.target.form?.id === "quick-form"
    ) {
      const account = e.target.value === "account";
      for (const [id, enabled] of [
        ["quick-guest", !account],
        ["quick-account", account],
      ]) {
        const group = document.getElementById(id);
        group.hidden = !enabled;
        group.querySelectorAll("input").forEach((el) => {
          el.disabled = !enabled;
        });
      }
    }
    if (e.target.name === "edition") {
      const f = e.target.form,
        ed = e.target.value;
      if (f.id === "challenge-form")
        document.querySelector("#challenge-mission").innerHTML = select(
          "mission",
          "mission_id",
          cat("mission", ed),
        );
      else {
        document.querySelector("#catalog-fields").outerHTML = catalogFields(ed);
        const ob = document.querySelector("#objective-fields");
        if (ob) ob.outerHTML = objectives(ed);
      }
    }
  });
  app.addEventListener(
    "toggle",
    (e) => {
      if (e.target.id === "audit-detail" && e.target.open && !auditOffset)
        loadAudit().catch((err) => notify(err.message));
    },
    true,
  );
  window.addEventListener("hashchange", route);
}
