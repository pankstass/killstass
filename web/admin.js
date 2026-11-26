import {
  api,
  app,
  button,
  date,
  esc,
  icon,
  input,
  lang,
  me,
  notify,
  num,
  select,
  t,
  uuid,
} from "./core.js";
import { page, shell, title } from "./app.js";
import { qrSvg } from "./qr.js";
import { copyText } from "./share.js";
import { statusLine } from "./library.js";
/* v1.9 — administrator page (#admin) instead of scripts/feedback.sh: instance overview, the feedback
   inbox and the user list. Administrators are flagged on the server: ./scripts/admin.sh grant LOGIN.
   v1.10: password reset codes, seasons, achievements and TV screens.
   v1.11: the rules reference — "up to date as of" and the journal of ./scripts/update-reference.sh.
   v1.13: local players (people without an account) — the list with their matches; deleting one.
   v1.14: the browser error log (web/errors.js → POST /api/client-errors), newest first, with «Clear». */
const state = {
  status: "open",
  feedback: [],
  total: 0,
  q: "",
  users: null,
  reset: null,
  seasons: null,
  achievements: null,
  screens: null,
  tournaments: [],
  locals: null,
  errors: null,
};
const bytes = (n) =>
  n > 1 << 30
    ? `${num((n / (1 << 30)).toFixed(2))} GB`
    : `${num((n / (1 << 20)).toFixed(1))} MB`;
function overviewHtml(o) {
  const c = o.counts;
  return `<div class="metrics">${[
    [c.users, "adminUsers"],
    [c.sessions, "adminSessions"],
    [c.rosters, "rosters"],
    [c.tournaments, "tournaments"],
    [c.feedback_open, "adminFeedbackOpen"],
    [c.teams, "teams"],
    [c.client_errors_week, "ad_errorsWeek"],
  ]
    .map(
      ([v, k]) =>
        `<div class="metric" data-metric="${k}"><strong>${num(v)}</strong><span>${t(k)}</span></div>`,
    )
    .join(
      "",
    )}</div><div class="grid"><section class="panel"><h2>${t("adminInstance")}</h2><dl class="kv"><dt>${t("version")}</dt><dd class="mono">${esc(o.version)}</dd><dt>${t("adminMigrations")}</dt><dd>${o.migrations.length} · <span class="mono muted">${esc(o.migrations[o.migrations.length - 1]?.version || "")}</span></dd><dt>${t("adminDbSize")}</dt><dd>${bytes(c.db_bytes)}</dd><dt>${t("adminAdmins")}</dt><dd>${c.admins}</dd><dt>${t("adminTeamImport")}</dt><dd>${o.team_import ? `${esc(date(o.team_import.imported_at))} · ${o.team_import.teams} / ${o.team_import.operatives}${o.team_import.warnings ? ` · ⚠ ${o.team_import.warnings}` : ""}` : "—"}</dd></dl></section><section class="panel"><h2>${t("adminMatches")}</h2>${o.matches.length ? `<dl class="kv">${o.matches.map((r) => `<dt>${esc(t(r.status))}</dt><dd>${r.n}</dd>`).join("")}</dl>` : `<p class="muted">—</p>`}</section></div>`;
}
const counts = (d) =>
  d
    ? `${d.before} → ${d.after} (+${d.added.length} −${d.removed.length} ~${d.changed.length})`
    : "—";
const list = (label, items) =>
  items?.length
    ? `<dt>${label}</dt><dd>${items.map((x) => esc(x)).join(", ")}</dd>`
    : "";
function updateHtml(u, open) {
  const r = u.report || {},
    failing = r.rosters?.failing || [];
  const summary = `<span class="badge ${u.status === "failed" ? "danger" : u.status === "ok" ? "ok" : ""}">${t("ad_refStatus_" + u.status)}</span> ${esc(date(u.finished_at || u.started_at))} · ${t("ad_refAction_" + u.action)} · ${t("ad_refTrigger_" + u.trigger)}${
    r.teams || r.rules
      ? ` · ${t("ad_refTeams")} ${counts(r.teams)} · ${t("ad_refRules")} ${counts(r.rules)}`
      : ""
  }${failing.length ? ` · ⚠ ${failing.length}` : ""}`;
  const body = `<dl class="kv">${r.error ? `<dt>${t("ad_refError")}</dt><dd class="mono">${esc(r.error)}</dd>` : ""}${
    r.teams
      ? `<dt>${t("ad_refOperatives")}</dt><dd>${r.teams.operatives_before} → ${r.teams.operatives_after}</dd>${list(t("ad_refAdded"), r.teams.added)}${list(t("ad_refChanged"), r.teams.changed)}${list(t("ad_refRemoved"), r.teams.removed)}`
      : ""
  }${
    r.rules
      ? `${list(t("ad_refRules") + " +", r.rules.added)}${list(t("ad_refRules") + " ~", r.rules.changed)}${list(t("ad_refRules") + " −", r.rules.removed)}`
      : ""
  }${r.rosters ? `<dt>${t("ad_refRosters")}</dt><dd>${t("ad_refChecked")}: ${r.rosters.checked}${failing.length ? `<ul>${failing.map((x) => `<li>${esc(x.name)} · ${esc(x.team)} · ${esc(x.owner)} — <span class="mono">${esc(x.errors.join(", "))}</span></li>`).join("")}</ul>` : ` · ${t("ad_refRostersOk")}`}</dd>` : ""}${list(t("ad_refWarnings"), r.warnings)}${u.backup ? `<dt>${t("ad_refBackup")}</dt><dd class="mono">${esc(u.backup)}</dd>` : ""}${u.snapshot ? `<dt>${t("ad_refSnapshot")}</dt><dd class="mono">${esc(u.snapshot)}</dd>` : ""}</dl>`;
  return `<details class="ref-update"${open ? " open" : ""}><summary>${summary}</summary>${body}</details>`;
}
function referenceHtml(ref) {
  if (!ref) return "";
  return `<section class="panel" id="admin-reference"><h2>${t("ad_refTitle")}</h2>${statusLine(ref.status)}${
    ref.updates.length
      ? ref.updates.map((u, i) => updateHtml(u, i === 0)).join("")
      : `<p class="muted">${t("ad_refNone")}</p>`
  }<p class="muted">${t("ad_refHint")}</p><pre class="mono">./scripts/update-reference.sh\n./scripts/update-reference.sh --status\n./scripts/update-reference.sh --rollback</pre></section>`;
}
function feedbackHtml() {
  return `<section class="panel" id="admin-feedback"><div class="row between"><h2>${t("adminFeedback")}</h2><div class="row" role="group" aria-label="${esc(t("adminFeedback"))}">${["open", "all"].map((s) => button(t("adminFb_" + s), "admin-fb-filter", state.status === s ? "selected small" : "secondary small", `data-status="${s}" aria-pressed="${state.status === s}"`)).join("")}</div></div>${
    state.feedback.length
      ? state.feedback
          .map(
            (f) =>
              `<article class="list-item feedback-item ${f.handled_at ? "handled" : ""}"><div><span class="eyebrow">${esc(date(f.created_at))} · ${esc(f.display_name)} <span class="mono">${esc(f.login)} #${esc(f.public_id)}</span>${f.page ? ` · ${esc(f.page)}` : ""}</span><p class="pre">${esc(f.message)}</p>${f.handled_at ? `<small class="muted">${t("adminHandled")}: ${esc(date(f.handled_at))}</small>` : ""}</div>${button(t(f.handled_at ? "adminReopen" : "adminMarkHandled"), "admin-fb-handle", "secondary small", `data-id="${f.id}" data-handled="${!f.handled_at}"`)}</article>`,
          )
          .join("")
      : `<p class="empty">${t("adminFeedbackEmpty")}</p>`
  }${state.feedback.length < state.total ? button(t("loadMore"), "admin-fb-more") : ""}</section>`;
}
function usersHtml() {
  const u = state.users;
  return `<section class="panel" id="admin-users"><h2>${t("adminUsers")}</h2><form id="admin-user-search" class="row" role="search"><label class="grow">${t("adminSearch")}<input name="q" value="${esc(state.q)}" maxlength="64" type="search"></label><button class="secondary">${t("search")}</button></form>${
    u
      ? `<p class="muted small">${t("adminFound")}: ${u.total}</p><div class="table-wrap" tabindex="0"><table><thead><tr><th>${t("name")}</th><th>${t("loginLabel")}</th><th>ID</th><th>${t("adminJoined")}</th><th>${t("adminLastLogin")}</th><th>${t("games")}</th><th>${t("rosters")}</th><th><span class="sr-only">${t("ad_reset")}</span></th></tr></thead><tbody>${u.items.map((x) => `<tr><td>${esc(x.display_name)}${x.is_admin ? ` <span class="badge active">${icon("gear")}${t("admin")}</span>` : ""}${x.email ? `<br><small class="muted">${esc(x.email)}</small>` : ""}</td><td class="mono">${esc(x.login)}</td><td class="mono">${esc(x.public_id)}</td><td>${esc(date(x.created_at))}</td><td>${x.last_login ? esc(date(x.last_login)) : "—"}</td><td>${x.matches}</td><td>${x.rosters}</td><td>${x.is_admin && x.public_id !== me.public_id ? "" : button(t("ad_reset"), "admin-reset", "secondary small", `data-id="${esc(x.public_id)}" data-name="${esc(x.display_name)}"`)}</td></tr>`).join("")}</tbody></table></div>`
      : `<p class="muted">${t("loading")}</p>`
  }${resetHtml()}<p class="muted small">${t("adminGrantHint")} <code>./scripts/admin.sh grant LOGIN</code> · ${t("ad_resetCli")} <code>./scripts/admin.sh password LOGIN</code></p></section>`;
}
/* One-time code (shown once): the player enters it on the login page («I have a reset code»). */
function resetHtml() {
  const r = state.reset;
  if (!r) return "";
  return `<div class="reset-code panel" role="status"><h3>${t("ad_resetFor")} ${esc(r.name)}</h3><p class="code mono accent">${esc(r.code)}</p><p class="muted">${t("ad_resetUntil")} ${esc(date(r.expires_at))}. ${t("ad_resetHint")}</p><div class="row">${button(t("ad_copyCode"), "admin-copy-code", "", `data-code="${esc(r.code)}"`)}${button(t("ad_done"), "admin-reset-done")}</div></div>`;
}
function localsHtml() {
  const l = state.locals?.items || [];
  return `<section class="panel" id="admin-locals"><h2 tabindex="-1">${icon("people")} ${t("ad_locals")}</h2><p class="muted">${t("ad_localsHint")}</p>${
    l.length
      ? `<div class="table-wrap" tabindex="0"><table><thead><tr><th>${t("name")}</th><th>${t("games")}</th><th>${t("ad_localLast")}</th><th>${t("ad_localBy")}</th><th><span class="sr-only">${t("ad_delete")}</span></th></tr></thead><tbody>${l.map((x) => `<tr><td>${esc(x.name)}</td><td>${x.matches}</td><td>${x.last_played ? esc(date(x.last_played)) : "—"}</td><td>${x.created_by_name ? esc(x.created_by_name) : "—"}<br><small class="muted">${esc(date(x.created_at))}</small></td><td>${button(t("ad_delete"), "admin-local-delete", "secondary small", `data-id="${esc(x.id)}" data-name="${esc(x.name)}" aria-label="${esc(t("ad_delete") + ": " + x.name)}"`)}</td></tr>`).join("")}</tbody></table></div>`
      : `<p class="empty">${t("ad_localsEmpty")}</p>`
  }</section>`;
}
async function loadLocals() {
  state.locals = await api("/admin/local-players");
}
const ruleLabel = (r) => t("rule_" + r);
function seasonsHtml() {
  const list = state.seasons?.seasons || [];
  return `<section class="panel" id="admin-seasons"><h2>${icon("chart")} ${t("ad_seasons")}</h2><p class="muted">${t("ad_seasonsHint")}</p>${
    list.length
      ? `<div class="table-wrap" tabindex="0"><table><thead><tr><th>${t("ad_seasonName")}</th><th>${t("ad_dates")}</th><th>K</th><th>${t("sn_start")}</th><th>${t("games")}</th><th></th></tr></thead><tbody>${list
          .map(
            (s) =>
              `<tr><td>${esc(s.name)} <span class="badge ${s.status === "current" ? "active" : ""}">${t("sn_" + s.status)}</span></td><td>${esc(s.starts_on)} — ${esc(s.ends_on)}</td><td>${s.k_factor}</td><td>${s.start_rating}</td><td>${s.games}</td><td class="row">${button(t("ad_edit"), "admin-season-edit", "secondary small", `data-id="${s.id}"`)}${button(t("ad_delete"), "admin-season-delete", "secondary small", `data-id="${s.id}"`)}</td></tr>`,
          )
          .join("")}</tbody></table></div>`
      : `<p class="empty">${t("sn_none")}</p>`
  }<details id="season-editor" ${state.seasonEdit ? "open" : ""}><summary>${icon("plus")} ${t(state.seasonEdit ? "ad_seasonEdit" : "ad_seasonNew")}</summary>${seasonForm(list.find((s) => s.id === state.seasonEdit))}</details></section>`;
}
function seasonForm(s) {
  const year = new Date().getFullYear();
  return `<form id="admin-season-form" data-id="${s?.id || ""}" class="stack-tight">${input("ad_seasonName", "name", "text", s?.name || `${t("sn_title")} ${year}`, 'required maxlength="60"')}<div class="grid">${input("ad_from", "starts_on", "date", s?.starts_on || `${year}-01-01`, "required")}${input("ad_to", "ends_on", "date", s?.ends_on || `${year}-12-31`, "required")}${input("ad_k", "k_factor", "number", s?.k_factor || 24, 'min="4" max="64" required')}${input("sn_start", "start_rating", "number", s?.start_rating || 1500, 'min="100" max="3000" required')}</div><div class="row"><button>${t("save")}</button>${s ? button(t("ad_cancelEdit"), "admin-season-new") : ""}</div></form>`;
}
function achievementsHtml() {
  const a = state.achievements;
  if (!a) return "";
  const edit = a.items.find((x) => x.id === state.achEdit);
  return `<section class="panel" id="admin-achievements"><div class="row between"><h2>${icon("trophy")} ${t("ach_title")}</h2>${button(t("ad_recompute"), "admin-ach-recompute")}</div><p class="muted">${t("ad_achHint")}</p><div class="table-wrap" tabindex="0"><table><thead><tr><th></th><th>${t("ad_seasonName")}</th><th>${t("ad_rule")}</th><th>${t("ad_threshold")}</th><th>${t("sn_title")}</th><th>${t("ad_holders")}</th><th></th></tr></thead><tbody>${a.items
    .map(
      (x) =>
        `<tr class="${x.active ? "" : "muted"}"><td>${icon(x.icon)}</td><td><b>${esc((lang === "en" && x.title_en) || x.title_ru)}</b> <code>${esc(x.code)}</code>${x.builtin ? ` <span class="badge">${t("ad_builtin")}</span>` : ""}${x.active ? "" : ` <span class="badge">${t("ad_inactive")}</span>`}<br><small class="muted">${esc((lang === "en" && x.description_en) || x.description_ru)}</small></td><td>${esc(ruleLabel(x.rule))}</td><td>${x.threshold}</td><td>${esc(state.seasons?.seasons.find((s) => s.id === x.season_id)?.name || "—")}</td><td>${x.holders}</td><td class="row">${button(t("ad_edit"), "admin-ach-edit", "secondary small", `data-id="${x.id}"`)}${x.builtin ? "" : button(t("ad_delete"), "admin-ach-delete", "secondary small", `data-id="${x.id}"`)}</td></tr>`,
    )
    .join(
      "",
    )}</tbody></table></div><details id="ach-editor" ${edit ? "open" : ""}><summary>${icon("plus")} ${t(edit ? "ad_achEdit" : "ad_achNew")}</summary>${achievementForm(edit, a)}</details></section>`;
}
function achievementForm(x, a) {
  const seasons = state.seasons?.seasons || [];
  return `<form id="admin-ach-form" data-id="${x?.id || ""}" class="stack-tight"><div class="grid">${input("ad_code", "code", "text", x?.code || "", `required pattern="[a-z0-9_]{2,40}" maxlength="40" ${x?.builtin ? "readonly" : ""}`)}${select(
    "ad_icon",
    "icon",
    a.icons.map((i) => ({ id: i, label: i })),
    x?.icon || "star",
  )}${select(
    "ad_rule",
    "rule",
    a.rules.map((r) => ({ id: r, label: ruleLabel(r) })),
    x?.rule || "wins",
  )}${input("ad_threshold", "threshold", "number", x?.threshold || 1, 'min="1" max="1000" required')}</div><p class="muted small">${t("ad_ruleHint")}</p><div class="grid">${input("ad_titleRu", "title_ru", "text", x?.title_ru || "", 'required maxlength="60"')}${input("ad_titleEn", "title_en", "text", x?.title_en || "", 'maxlength="60"')}</div><div class="grid">${input("ad_descRu", "description_ru", "text", x?.description_ru || "", 'maxlength="200"')}${input("ad_descEn", "description_en", "text", x?.description_en || "", 'maxlength="200"')}</div><div class="grid">${select("ad_seasonOnly", "season_id", [{ id: "", label: t("ad_anyTime") }, ...seasons.map((s) => ({ id: s.id, label: s.name }))], x?.season_id ?? "")}${input("ad_position", "position", "number", x?.position ?? 100, 'min="0" max="10000"')}</div><label class="check"><input type="checkbox" name="active" ${!x || x.active ? "checked" : ""}>${t("ad_active")}</label><div class="row"><button>${t("save")}</button>${x ? button(t("ad_cancelEdit"), "admin-ach-new") : ""}</div></form>`;
}
function screensHtml() {
  const list = state.screens || [];
  return `<section class="panel" id="admin-tv"><h2>${icon("eye")} ${t("ad_tv")}</h2><p class="muted">${t("ad_tvHint")}</p>${list
    .map((s) => {
      const url = `${location.origin}/#tv/${s.key}`;
      return `<article class="list-item tv-item"><div class="tv-qr">${qrSvg(url, { label: s.label })}</div><div class="grow"><h3>${esc(s.label)}</h3><p class="muted">${s.tournament_name ? `${t("tournaments")}: ${esc(s.tournament_name)} · ` : ""}${t("ad_tvSeen")}: ${s.last_seen_at ? esc(date(s.last_seen_at)) : "—"}</p><p class="mono break small">${esc(url)}</p><div class="row"><a class="button secondary" href="#tv/${esc(s.key)}" target="_blank" rel="noopener">${t("open")}</a>${button(t("nt_copyLink"), "admin-tv-copy", "secondary", `data-url="${esc(url)}"`)}${button(t("ad_delete"), "admin-tv-delete", "secondary", `data-id="${s.id}"`)}</div></div></article>`;
    })
    .join(
      "",
    )}<form id="admin-tv-form" class="row">${input("ad_tvLabel", "label", "text", t("ad_tvDefault"), 'required maxlength="60"')}${select("ad_tvTournament", "tournament_id", [{ id: "", label: t("ad_tvAnyTournament") }, ...state.tournaments.map((x) => ({ id: x.id, label: x.name }))], "")}<button>${t("ad_tvCreate")}</button></form></section>`;
}
async function loadV110() {
  const [seasons, achievements, screens, tours] = await Promise.all([
    api("/admin/seasons"),
    api("/admin/achievements"),
    api("/admin/tv"),
    api("/tournaments").catch(() => []),
  ]);
  Object.assign(state, { seasons, achievements, screens, tournaments: tours });
}
const v110Html = () => seasonsHtml() + achievementsHtml() + screensHtml();
function redrawV110() {
  redraw("#admin-seasons", seasonsHtml());
  redraw("#admin-achievements", achievementsHtml());
  redraw("#admin-tv", screensHtml());
}
function errorsHtml() {
  const d = state.errors;
  if (!d) return "";
  const item = (e) =>
    `<details class="list-item err-item"><summary><b>${esc(e.message)}</b> <span class="muted">· #${esc(e.page || "—")} · ${esc(e.version || "—")} · ×${num(e.count)} · ${esc(date(e.last_at))}</span></summary>${e.source ? `<p class="mono small">${esc(e.source)}</p>` : ""}${e.stack ? `<pre class="mono small err-stack">${esc(e.stack)}</pre>` : ""}<p class="muted small">${esc(t(e.kind === "rejection" ? "ad_errRejection" : "ad_errError"))} · ${esc(e.agent || "—")}${e.login ? ` · ${esc(e.login)}` : ""} · ${esc(t("ad_errFirst"))} ${esc(date(e.first_at))}</p></details>`;
  return `<section class="panel" id="admin-errors"><div class="row between"><h2>${icon("alert")} ${t("ad_errors")}</h2>${d.items.length ? button(t("ad_errClear"), "admin-err-clear") : ""}</div><p class="muted">${esc(t("ad_errorsHint").replace("{n}", d.keep_days))}</p>${
    d.items.length
      ? `<p class="muted small">${esc(t("ad_errTotal").replace("{n}", num(d.total.n)).replace("{m}", num(d.total.events)))}</p>${d.items.map(item).join("")}${d.items.length < d.total.n ? button(t("loadMore"), "admin-err-more") : ""}`
      : `<p class="empty">${t("ad_errNone")}</p>`
  }</section>`;
}
async function loadErrors(reset = true) {
  const offset = reset ? 0 : state.errors?.items.length || 0,
    r = await api("/admin/client-errors?offset=" + offset);
  state.errors =
    reset || !state.errors
      ? r
      : { ...r, items: [...state.errors.items, ...r.items] };
}
async function loadFeedback(reset = true) {
  const offset = reset ? 0 : state.feedback.length,
    r = await api(`/admin/feedback?status=${state.status}&offset=${offset}`);
  state.feedback = reset ? r.items : [...state.feedback, ...r.items];
  state.total = r.total;
}
async function loadUsers() {
  state.users = await api("/admin/users?q=" + encodeURIComponent(state.q));
}
function redraw(id, html) {
  const el = document.querySelector(id);
  if (el) el.outerHTML = html;
}
export async function adminPage() {
  if (!me?.is_admin)
    return shell(
      `${title("admin")}<section class="panel"><p>${t("adminOnly")}</p></section>`,
    );
  const [o] = await Promise.all([
    api("/admin/overview"),
    loadFeedback(),
    loadUsers(),
    loadV110(),
    loadLocals(),
    loadErrors(),
  ]);
  if (page !== "admin") return;
  shell(
    `${title("admin", "COMMAND POST")}${overviewHtml(o)}${referenceHtml(o.reference)}${errorsHtml()}${feedbackHtml()}${usersHtml()}${localsHtml()}${v110Html()}`,
  );
}
export function init() {
  app.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (
      !b ||
      b.disabled ||
      page !== "admin" ||
      !b.dataset.action.startsWith("admin-")
    )
      return;
    const a = b.dataset.action;
    b.disabled = true;
    try {
      if (await v110Click(a, b)) return;
      if (a === "admin-err-clear" || a === "admin-err-more") {
        if (a === "admin-err-clear") {
          if (!confirm(t("ad_errClearConfirm"))) return;
          await api("/admin/client-errors/clear", "POST", {
            request_id: uuid(),
          });
        }
        await loadErrors(a === "admin-err-clear");
        redraw("#admin-errors", errorsHtml());
        return;
      }
      if (a === "admin-fb-filter") {
        state.status = b.dataset.status;
        await loadFeedback();
      } else if (a === "admin-fb-more") await loadFeedback(false);
      else if (a === "admin-fb-handle") {
        await api("/admin/feedback/" + b.dataset.id, "POST", {
          request_id: uuid(),
          handled: b.dataset.handled === "true",
        });
        await loadFeedback();
        /* Keep the «new feedback» counter in the overview in step with the inbox. */
        const n = document.querySelector(
          '[data-metric="adminFeedbackOpen"] strong',
        );
        if (n && state.status === "open") n.textContent = num(state.total);
        else if (n)
          n.textContent = num((await api("/admin/feedback?status=open")).total);
      }
      redraw("#admin-feedback", feedbackHtml());
    } catch (err) {
      notify(err.message);
    } finally {
      b.disabled = false;
    }
  });
  app.addEventListener("submit", async (e) => {
    if (
      ["admin-season-form", "admin-ach-form", "admin-tv-form"].includes(
        e.target.id,
      )
    ) {
      e.preventDefault();
      e.stopImmediatePropagation();
      try {
        await v110Submit(e.target);
      } catch (err) {
        notify(err.message);
      }
      return;
    }
    if (e.target.id !== "admin-user-search") return;
    e.preventDefault();
    e.stopImmediatePropagation();
    state.q = String(new FormData(e.target).get("q") || "").trim();
    try {
      await loadUsers();
      redraw("#admin-users", usersHtml());
      document.querySelector("#admin-user-search input")?.focus();
    } catch (err) {
      notify(err.message);
    }
  });
}

/* v1.10 actions; returns true when handled. */
async function v110Click(a, b) {
  if (a === "admin-reset") {
    if (!confirm(t("ad_resetConfirm").replace("{name}", b.dataset.name)))
      return true;
    const r = await api(`/admin/users/${b.dataset.id}/password-reset`, "POST", {
      request_id: uuid(),
    });
    state.reset = { ...r, name: b.dataset.name };
    redraw("#admin-users", usersHtml());
    document.querySelector(".reset-code")?.scrollIntoView({ block: "nearest" });
  } else if (a === "admin-copy-code") await copyText(b.dataset.code);
  else if (a === "admin-reset-done") {
    state.reset = null;
    redraw("#admin-users", usersHtml());
  } else if (a === "admin-season-edit") {
    state.seasonEdit = +b.dataset.id;
    redraw("#admin-seasons", seasonsHtml());
    document.querySelector("#admin-season-form input")?.focus();
  } else if (a === "admin-season-new") {
    state.seasonEdit = null;
    redraw("#admin-seasons", seasonsHtml());
  } else if (a === "admin-season-delete") {
    if (!confirm(t("ad_deleteConfirm"))) return true;
    await api("/admin/seasons/" + b.dataset.id, "DELETE", {});
    await loadV110();
    redrawV110();
  } else if (a === "admin-ach-edit") {
    state.achEdit = +b.dataset.id;
    redraw("#admin-achievements", achievementsHtml());
    document.querySelector("#admin-ach-form input:not([readonly])")?.focus();
  } else if (a === "admin-ach-new") {
    state.achEdit = null;
    redraw("#admin-achievements", achievementsHtml());
  } else if (a === "admin-ach-delete") {
    if (!confirm(t("ad_deleteConfirm"))) return true;
    await api("/admin/achievements/" + b.dataset.id, "DELETE", {});
    await loadV110();
    redrawV110();
  } else if (a === "admin-ach-recompute") {
    const r = await api("/admin/achievements/recompute", "POST", {});
    notify(t("ad_recomputed").replace("{n}", r.awarded));
    await loadV110();
    redrawV110();
  } else if (a === "admin-local-delete") {
    if (!confirm(t("ad_localDeleteConfirm").replace("{name}", b.dataset.name)))
      return true;
    await api("/admin/local-players/" + b.dataset.id, "DELETE", {});
    await loadLocals();
    redraw("#admin-locals", localsHtml());
    document.querySelector("#admin-locals h2")?.focus();
  } else if (a === "admin-tv-copy") await copyText(b.dataset.url);
  else if (a === "admin-tv-delete") {
    if (!confirm(t("ad_tvDeleteConfirm"))) return true;
    await api("/admin/tv/" + b.dataset.id, "DELETE", {});
    await loadV110();
    redrawV110();
  } else return false;
  return true;
}
async function v110Submit(f) {
  const d = Object.fromEntries(new FormData(f));
  if (f.id === "admin-season-form") {
    const body = {
      name: d.name,
      starts_on: d.starts_on,
      ends_on: d.ends_on,
      k_factor: +d.k_factor,
      start_rating: +d.start_rating,
    };
    if (f.dataset.id) await api("/admin/seasons/" + f.dataset.id, "PUT", body);
    else await api("/admin/seasons", "POST", body);
    state.seasonEdit = null;
  } else if (f.id === "admin-ach-form") {
    const body = {
      code: d.code,
      title_ru: d.title_ru,
      title_en: d.title_en || "",
      description_ru: d.description_ru || "",
      description_en: d.description_en || "",
      icon: d.icon,
      rule: d.rule,
      threshold: +d.threshold,
      season_id: d.season_id ? +d.season_id : null,
      active: !!d.active,
      position: +d.position || 0,
    };
    if (f.dataset.id)
      await api("/admin/achievements/" + f.dataset.id, "PUT", body);
    else await api("/admin/achievements", "POST", body);
    state.achEdit = null;
  } else if (f.id === "admin-tv-form") {
    await api("/admin/tv", "POST", {
      label: d.label,
      ...(d.tournament_id ? { tournament_id: d.tournament_id } : {}),
    });
  }
  notify(t("saved"));
  await loadV110();
  redrawV110();
}
