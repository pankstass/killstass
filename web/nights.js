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
  link,
  locale,
  notify,
  select,
  t,
  uuid,
} from "./core.js";
import { page, shell, title } from "./app.js";
import { playerLink } from "./players.js";
import { copyText } from "./share.js";
/* v1.10 — game nights (#nights): date and place, who comes and with which team, pairs per table and the
   matches of the tables, calendar export (.ics for one night, a private subscription link for all). */
const ANSWERS = ["yes", "maybe", "no"];
let current = null,
  showPast = false,
  feedLink = null;
const hm = (v) =>
  new Intl.DateTimeFormat(locale(), {
    timeStyle: "short",
    timeZone: "Europe/Moscow",
  }).format(new Date(v));
const when = (n) => `${date(n.starts_at)} — ${hm(n.ends_at)}`;
/* Moscow wall time of a form → ISO with offset; an end before the start is the next morning. */
function period(d) {
  const start = new Date(`${d.day}T${d.start}:00+03:00`);
  let end = new Date(`${d.day}T${d.end}:00+03:00`);
  if (end <= start) end = new Date(end.getTime() + 86400000);
  return { starts_at: start.toISOString(), ends_at: end.toISOString() };
}
const moscow = (v) => {
  const x = new Date(new Date(v).getTime() + 3 * 3600000).toISOString();
  return { day: x.slice(0, 10), time: x.slice(11, 16) };
};
function nightForm(n) {
  const s = n ? moscow(n.starts_at) : null,
    e = n ? moscow(n.ends_at) : null,
    tomorrow = moscow(Date.now() + 86400000).day;
  return `<form id="${n ? "night-edit-form" : "night-form"}" class="stack-tight">${input("nt_title", "title", "text", n?.title || t("nt_defaultTitle"), 'required maxlength="80"')}<div class="grid">${input("dateLabel", "day", "date", s?.day || tomorrow, "required")}${input("nt_start", "start", "time", s?.time || "18:00", "required")}${input("nt_end", "end", "time", e?.time || "23:00", "required")}</div><div class="grid">${input("nt_place", "place", "text", n?.place || "", 'maxlength="120"')}${input("nt_capacity", "capacity", "number", n?.capacity || "", 'min="2" max="64"')}</div><label>${t("notes")}<textarea name="notes" maxlength="1000">${esc(n?.notes || "")}</textarea></label><button>${t(n ? "save" : "nt_create")}</button></form>`;
}
function body(f) {
  const d = Object.fromEntries(new FormData(f));
  return {
    title: d.title.trim(),
    ...period(d),
    place: d.place || "",
    notes: d.notes || "",
    capacity: d.capacity ? +d.capacity : null,
  };
}
function nightRow(n) {
  return `<article class="list-item night-item ${n.status}"><div><span class="eyebrow">${esc(when(n))}${n.place ? ` · ${esc(n.place)}` : ""}</span><h3>${esc(n.title)}</h3><span class="muted">${t("nt_going")}: ${n.yes}${n.capacity ? "/" + n.capacity : ""} · ${t("nt_maybe")}: ${n.maybe}${n.organizer_name ? ` · ${t("nt_organizer")}: ${esc(n.organizer_name)}` : ""}</span></div><div class="row">${n.status === "cancelled" ? badge("nt_cancelled") : n.my_answer ? badge("nt_" + n.my_answer) : ""}${n.pairs_published_at ? `<span class="badge active">${t("nt_pairsReady")}</span>` : ""}${link(t("open"), "nights/" + n.id)}</div></article>`;
}
export function nextNightPanel(list) {
  const n = (list || []).find((x) => x.status === "planned");
  if (!n) return "";
  return `<section class="panel next-night"><div class="row between"><h2>${icon("table")} ${t("nt_next")}</h2>${link(t("nights"), "nights")}</div>${nightRow(n)}</section>`;
}
async function feedPanel() {
  const s = await api("/calendar/token");
  const url = feedLink ? location.origin + feedLink : null;
  return `<section class="panel" id="feed-panel"><h2>${icon("clock")} ${t("nt_feed")}</h2><p class="muted">${t("nt_feedHint")}</p>${
    url
      ? `<p class="warning">${t("nt_feedOnce")}</p><p class="mono break">${esc(url)}</p><div class="row">${button(t("nt_copyLink"), "nt-copy", "", `data-url="${esc(url)}"`)}<a class="button secondary" href="${esc(url.replace(/^https:/, "webcal:"))}">${t("nt_feedOpen")}</a></div>`
      : s.active
        ? `<p>${icon("check")} ${t("nt_feedActive")} ${esc(date(s.created_at))}</p>`
        : ""
  }<div class="row">${button(t(s.active ? "nt_feedRotate" : "nt_feedCreate"), "nt-feed")}${s.active ? button(t("nt_feedOff"), "nt-feed-off") : ""}</div></section>`;
}
async function listPage() {
  const [upcoming, past, feed] = await Promise.all([
    api("/nights"),
    showPast ? api("/nights?scope=past") : null,
    feedPanel(),
  ]);
  if (page !== "nights") return;
  shell(
    `${title("nights")}<p class="muted">${t("nt_lead")}</p><section class="panel"><details ${upcoming.length ? "" : "open"}><summary>${icon("plus")} ${t("nt_new")}</summary>${nightForm(null)}</details></section><section class="panel"><h2>${t("nt_upcoming")}</h2>${upcoming.length ? upcoming.map(nightRow).join("") : `<p class="empty">${t("nt_empty")}</p>`}</section><section class="panel"><div class="row between"><h2>${t("nt_past")}</h2>${showPast ? "" : button(t("nt_showPast"), "nt-past")}</div>${past ? (past.length ? past.map(nightRow).join("") : `<p class="empty">${t("nt_empty")}</p>`) : ""}</section>${feed}`,
  );
}
function attendee(p) {
  return `<li><span class="who">${playerLink(p.public_id, p.display_name)}</span>${p.team_id ? ` <span class="muted">· ${esc(catName(p.team_id))}</span>` : ""}${p.comment ? `<small class="muted"> — ${esc(p.comment)}</small>` : ""}</li>`;
}
function pairRow(n, x) {
  const vs = x.b_name
    ? `${esc(x.a_name)} <span class="muted">vs</span> ${esc(x.b_name)}`
    : `${esc(x.a_name)} <span class="muted">· ${t("nt_bye")}</span>`;
  let act = "";
  if (x.match_id) act = link(t("nt_openMatch"), "match/" + x.match_id);
  else if (x.mine && x.b_name && n.pairs_published_at && n.status === "planned")
    act = button(t("nt_startMatch"), "nt-match", "", `data-pair="${x.id}"`);
  return `<li class="list-item"><div><span class="eyebrow">${t("nt_table")} ${x.table_no}</span><h3>${vs}</h3>${x.match_status ? badge(x.match_status) : ""}</div><div class="row">${act}</div></li>`;
}
function pairsEditor(n) {
  const yes = n.attendees.filter((p) => p.answer === "yes"),
    opts = (v, bye) =>
      `${bye ? `<option value="">${esc(t("nt_bye"))}</option>` : `<option value="">—</option>`}${yes.map((p) => `<option value="${esc(p.public_id)}" ${p.public_id === v ? "selected" : ""}>${esc(p.display_name)}</option>`).join("")}`,
    rows = [...n.pairs, { a_id: "", b_id: "" }];
  return `<details class="pairs-edit"><summary>${t("nt_pairsManual")}</summary><form id="pairs-form" class="stack-tight">${rows.map((x, i) => `<div class="row pair-edit"><b>${t("nt_table")} ${i + 1}</b><label class="sr-only" for="pa-${i}">A</label><select id="pa-${i}" name="a">${opts(x.a_id)}</select><label class="sr-only" for="pb-${i}">B</label><select id="pb-${i}" name="b">${opts(x.b_id, true)}</select></div>`).join("")}<button class="secondary">${t("nt_pairsSave")}</button></form></details>`;
}
async function detailPage(id) {
  const n = await api("/nights/" + id);
  if (page !== "nights") return;
  current = n;
  const open = n.status === "planned" && new Date(n.ends_at) > new Date(),
    my = n.my || {},
    groups = ANSWERS.map((a) => [a, n.attendees.filter((p) => p.answer === a)]);
  shell(
    `<header class="page-title"><p>${link("← " + t("nights"), "nights", "text")}</p><span class="eyebrow">${esc(when(n))}${n.place ? ` · ${esc(n.place)}` : ""}</span><h1>${esc(n.title)} ${n.status === "cancelled" ? badge("nt_cancelled") : ""}</h1>${n.organizer ? `<p class="muted">${t("nt_organizer")}: ${playerLink(n.organizer.public_id, n.organizer.display_name)}</p>` : ""}${n.notes ? `<p class="pre">${esc(n.notes)}</p>` : ""}<p class="row"><a class="button secondary" href="/api/nights/${esc(n.id)}/calendar.ics" download>${icon("clock")} ${t("nt_ics")}</a></p></header>${
      open
        ? `<section class="panel"><h2>${t("nt_rsvp")}</h2><form id="rsvp-form" class="stack-tight"><fieldset class="segmented"><legend>${t("nt_coming")}</legend>${ANSWERS.map((a) => `<label><input type="radio" name="answer" value="${a}" ${(my.answer || "yes") === a ? "checked" : ""}>${t("nt_" + a)}</label>`).join("")}</fieldset>${select("nt_team", "team_id", [{ id: "", label: t("none") }, ...cat("team", "2024")], my.team_id ?? "")}${input("nt_comment", "comment", "text", my.comment || "", 'maxlength="140"')}<button>${t("nt_answer")}</button></form></section>`
        : ""
    }<section class="panel"><h2>${t("nt_who")} <small class="muted">${n.counts.yes}${n.capacity ? "/" + n.capacity : ""}</small></h2><div class="grid night-groups">${groups.map(([a, list]) => `<div><h3>${t("nt_" + a)} (${list.length})</h3>${list.length ? `<ul class="plain">${list.map(attendee).join("")}</ul>` : `<p class="muted">—</p>`}</div>`).join("")}</div></section><section class="panel" id="night-pairs"><div class="row between"><h2>${t("nt_pairs")}</h2>${n.pairs_published_at ? `<span class="badge active">${t("nt_pairsReady")}</span>` : n.can_edit && n.pairs.length ? `<span class="badge">${t("nt_pairsDraft")}</span>` : ""}</div>${n.pairs.length ? `<ul class="plain">${n.pairs.map((x) => pairRow(n, x)).join("")}</ul>` : `<p class="empty">${t(n.can_edit ? "nt_pairsHint" : "nt_pairsWait")}</p>`}${
      n.can_edit && open
        ? `<div class="row">${button(t("nt_generate"), "nt-pairs", "", `data-kind="generate"`)}${n.pairs.length && !n.pairs_published_at ? button(t("nt_publish"), "nt-pairs", "", `data-kind="publish"`) : ""}${n.pairs.length ? button(t("nt_clear"), "nt-pairs", "secondary", `data-kind="clear"`) : ""}</div><p class="muted small">${t("nt_generateHint")}</p>${pairsEditor(n)}`
        : ""
    }</section>${
      n.can_edit
        ? `<section class="panel"><details><summary>${t("nt_edit")}</summary>${nightForm(n)}${n.status === "planned" ? `<p></p>${button(t("nt_cancel"), "nt-cancel", "danger")}` : ""}</details></section>`
        : ""
    }`,
  );
}
export async function nightsRoute(parts) {
  if (parts[0]) return detailPage(parts[0]);
  return listPage();
}
async function pairs(kind, extra = {}) {
  await api("/nights/" + current.id + "/pairs", "POST", {
    request_id: uuid(),
    version: current.version,
    action: kind,
    ...extra,
  });
  await detailPage(current.id);
}
async function update(status) {
  const f = document.querySelector("#night-edit-form");
  await api("/nights/" + current.id, "PUT", {
    request_id: uuid(),
    version: current.version,
    status,
    ...body(f),
  });
  await detailPage(current.id);
}
export function init() {
  app.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (
      !b ||
      b.disabled ||
      page !== "nights" ||
      !b.dataset.action.startsWith("nt-")
    )
      return;
    const a = b.dataset.action;
    b.disabled = true;
    try {
      if (a === "nt-past") {
        showPast = true;
        await listPage();
      } else if (a === "nt-feed") {
        feedLink = (
          await api("/calendar/token", "POST", { request_id: uuid() })
        ).path;
        await listPage();
      } else if (a === "nt-feed-off") {
        await api("/calendar/token", "DELETE", {});
        feedLink = null;
        await listPage();
      } else if (a === "nt-copy") {
        await copyText(b.dataset.url);
      } else if (a === "nt-pairs") {
        if (b.dataset.kind !== "clear" || confirm(t("nt_clearConfirm")))
          await pairs(b.dataset.kind);
      } else if (a === "nt-match") {
        const r = await api(
          `/nights/${current.id}/pairs/${b.dataset.pair}/match`,
          "POST",
          { request_id: uuid() },
        );
        location.hash = "match/" + r.id;
      } else if (a === "nt-cancel") {
        if (confirm(t("nt_cancelConfirm"))) await update("cancelled");
      }
    } catch (err) {
      notify(err.message);
    } finally {
      b.disabled = false;
    }
  });
  app.addEventListener("submit", async (e) => {
    const f = e.target;
    if (
      !["night-form", "night-edit-form", "rsvp-form", "pairs-form"].includes(
        f.id,
      )
    )
      return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const b = f.querySelector("button:not([type=button])");
    if (b) b.disabled = true;
    try {
      if (f.id === "night-form") {
        const r = await api("/nights", "POST", {
          request_id: uuid(),
          ...body(f),
        });
        location.hash = "nights/" + r.id;
      } else if (f.id === "night-edit-form") await update("planned");
      else if (f.id === "rsvp-form") {
        const d = Object.fromEntries(new FormData(f));
        await api("/nights/" + current.id + "/rsvp", "POST", {
          request_id: uuid(),
          answer: d.answer,
          team_id: d.team_id ? +d.team_id : null,
          comment: d.comment || "",
        });
        notify(t("saved"));
        await detailPage(current.id);
      } else if (f.id === "pairs-form") {
        const a = [...f.querySelectorAll("select[name=a]")].map((s) => s.value),
          bb = [...f.querySelectorAll("select[name=b]")].map((s) => s.value);
        await pairs("set", {
          pairs: a.map((x, i) => [x, bb[i] || null]).filter(([x]) => x),
        });
      }
    } catch (err) {
      notify(err.message);
    } finally {
      if (b) b.disabled = false;
    }
  });
}
