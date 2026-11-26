/* v1.9: shared core — i18n, session state, HTML primitives and the API client.
   This module imports nothing, so every other module can depend on it without cycles. */
export let L = {},
  lang = "ru",
  CE = null,
  me = null,
  catalogs = [];
export const app = document.querySelector("#app");
/* Single version source: the server substitutes VERSION into index.html; static assets live under /static/v/<VERSION>/. */
export const VERSION =
  document.querySelector('meta[name="killstass-version"]')?.content || "dev";
export const BASE = new URL("./", import.meta.url).pathname;
/* Late-bound callbacks set by app.js (avoids a core → pages import).
   v1.10: `net` reports the connection state to the offline layer: "ok", "down" (no answer from the
   server) or "cached" (the service worker answered from its copy). */
export const hooks = { unauthorized: () => {}, net: () => {} };
export const setMe = (v) => (me = v);
export const setCatalogs = (v) => (catalogs = v);
export const t = (k) => L[k] || k;
// v1.6: interface language. Russian is the default; the choice lives only in this browser.
export const locale = () => (lang === "en" ? "en-GB" : "ru-RU");
export function storedLang() {
  try {
    return localStorage.getItem("killstass-lang") === "en" ? "en" : "ru";
  } catch {
    return "ru";
  }
}
export async function loadI18n() {
  lang = storedLang();
  document.documentElement.lang = lang;
  L = await (await fetch(`${BASE}i18n/${lang}.json`)).json();
  CE =
    lang === "en"
      ? await (
          await fetch(`${BASE}i18n/catalog.en.json`)
        )
          .json()
          .catch(() => null)
      : null;
}
/* English catalog overlay keyed by code; missing entries fall back to the Russian label from the server. */
export function localizeRow(row, table = "catalog") {
  const tr = lang === "en" && CE?.[table]?.[row?.code];
  if (!tr) return row;
  if (table === "sequence") return { ...row, ...tr };
  return {
    ...row,
    label: tr.label || row.label,
    config: {
      ...(row.config || {}),
      ...(tr.summary ? { summary: tr.summary } : {}),
      ...(tr.reveal ? { reveal: tr.reveal } : {}),
    },
  };
}
/* The accessible name starts with the visible «EN»/«RU» (WCAG 2.5.3 label in name). */
export const langButton = () =>
  button(
    t("langToggle"),
    "lang",
    "secondary",
    `lang="${lang === "en" ? "ru" : "en"}" aria-label="${t("langToggle")} — ${t("langToggleLabel")}" title="${t("langToggleLabel")}"`,
  );
export const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const uuid = () => crypto.randomUUID();
export const icon = (id) =>
  `<svg class="icon" aria-hidden="true"><use href="${BASE}icons.svg#${id}"/></svg>`;
export const logo = () =>
  `<a class="logo" href="#overview" aria-label="KILLSTASS"><img src="${BASE}logo.svg" alt=""><b>KILL<span>STASS</span></b></a>`;
export const button = (text, action, cls = "secondary", attrs = "") =>
  `<button type="button" class="${cls}" data-action="${action}" ${attrs}>${esc(text)}</button>`;
export const link = (text, hash, cls = "button secondary") =>
  `<a class="${cls}" href="#${hash}">${esc(text)}</a>`;
export const badge = (s) =>
  `<span class="badge ${["active", "confirmed"].includes(s) ? "active" : ""}">${esc(t(s))}</span>`;
export const date = (v) =>
  new Intl.DateTimeFormat(locale(), {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Moscow",
  }).format(new Date(v));
export const num = (v) =>
  v === null || v === undefined
    ? "—"
    : new Intl.NumberFormat(locale(), { maximumFractionDigits: 2 }).format(v);
export function notify(msg) {
  const n = document.querySelector("#notice");
  n.textContent = msg;
  n.hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => (n.hidden = true), 6500);
}
/* v1.10: a request that never got an answer from the application (no network, or the proxy reports
   the API as unavailable) fails with code "network" — the offline scoreboard queues such commands. */
function networkError() {
  const err = new Error(t("connectionLost"));
  err.code = "network";
  hooks.net("down");
  return err;
}
export async function api(path, method = "GET", body, retry = true) {
  const headers = {};
  if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    if (me) headers["X-CSRF-Token"] = me.csrf;
  }
  let r;
  try {
    r = await fetch("/api" + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    if (retry && body?.request_id) return api(path, method, body, false);
    throw networkError();
  }
  if (
    [502, 503, 504].includes(r.status) &&
    !(r.headers.get("content-type") || "").includes("json")
  )
    throw networkError();
  const cached = r.headers.get("x-killstass-cache") === "1";
  hooks.net(cached ? "cached" : "ok");
  if (!r.ok) {
    let d;
    try {
      d = (await r.json()).detail;
    } catch {
      d = "requestFailed";
    }
    if (r.status === 401 && path !== "/auth/login") {
      me = null;
      hooks.unauthorized();
    }
    const err = new Error(
      typeof d === "string"
        ? L.errors?.[d] || t("requestFailed")
        : L.errors.validation,
    );
    err.code = typeof d === "string" ? d : "validation";
    throw err;
  }
  const data = await r.json();
  // v1.10: a copy from the service worker is marked (not enumerable, so it never goes back to the server).
  if (cached && data && typeof data === "object")
    Object.defineProperty(data, "cachedCopy", { value: true });
  return data;
}
export function input(key, name, type = "text", value = "", extra = "") {
  return `<label>${esc(t(key))}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
}
export function select(key, name, items, value, optional = false) {
  return `<label>${esc(t(key))}<select name="${name}">${optional ? `<option value="">${esc(t("all"))}</option>` : ""}${items.map((x) => `<option value="${esc(x.id)}" ${String(x.id) === String(value) ? "selected" : ""}>${esc(x.label)}</option>`).join("")}</select></label>`;
}
export function cat(kind, edition = "2024") {
  return catalogs.filter(
    (x) => x.kind === kind && x.edition === edition && x.active,
  );
}
export function catName(id) {
  return catalogs.find((x) => x.id === id)?.label || "—";
}
