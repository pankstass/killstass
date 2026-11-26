import { api, date, esc, lang, localizeRow, me, notify, t } from "./core.js";
import { currentMatch } from "./app.js";
import { hitCard } from "./library.js";
/* Non-modal reference lives outside #app: opening never replaces an edited form. */
let sequencePanel = null,
  sequenceOpener = null,
  sequenceContext = null;
const safeStorage = {
  get(k) {
    try {
      return JSON.parse(localStorage.getItem(k));
    } catch {
      return null;
    }
  },
  set(k, v) {
    try {
      localStorage.setItem(k, JSON.stringify(v));
    } catch {
      notify(t("localStorageUnavailable"));
    }
  },
};
export function sequenceButton(m) {
  return `<button type="button" class="secondary" data-sequence="${esc(m.id)}" aria-controls="game-sequence" aria-expanded="${!!sequencePanel}">${t("gameSequence")}</button>`;
}
export function closeSequence() {
  sequencePanel?.remove();
  sequencePanel = null;
  document.body.classList.remove("sequence-open");
  document
    .querySelectorAll("[data-sequence]")
    .forEach((b) => b.setAttribute("aria-expanded", "false"));
  const replacement = document.querySelector("[data-sequence]");
  (sequenceOpener?.isConnected ? sequenceOpener : replacement)?.focus();
  sequenceOpener = null;
  sequenceContext = null;
}
async function openSequence(button) {
  if (sequencePanel) {
    closeSequence();
    return;
  }
  sequenceOpener = button;
  const edition =
    document.querySelector('#setup-form [name="edition"]')?.value ||
    currentMatch.edition;
  const mid = button.dataset.sequence,
    cacheKey = "killstass-sequence-cache-" + edition;
  let saved = safeStorage.get(cacheKey),
    data;
  try {
    const response = await fetch(
      "/api/reference/game-sequence?edition=" + edition,
      {
        credentials: "same-origin",
        signal: AbortSignal.timeout ? AbortSignal.timeout(8000) : undefined,
        headers: saved?.etag ? { "If-None-Match": saved.etag } : {},
      },
    );
    if (response.status === 304 && saved) data = saved.data;
    else {
      if (!response.ok) {
        const err = new Error(
          t(
            response.status === 404
              ? "referenceNotVerified"
              : "referenceUnavailable",
          ),
        );
        err.status = response.status;
        throw err;
      }
      data = await response.json();
      saved = { etag: response.headers.get("ETag"), data };
      safeStorage.set(cacheKey, saved);
    }
  } catch (err) {
    if (err.status || !saved) {
      notify(err.message);
      return;
    }
    data = saved.data;
    notify(t("referenceCached"));
  }
  // Request may finish after navigation/logout.
  if (!me || !document.contains(button)) return;
  const key =
    "killstass-sequence-checks-" + mid + "-" + edition + "-" + saved.etag;
  sequenceContext = { key, checks: safeStorage.get(key) || {} };
  sequencePanel = document.createElement("aside");
  sequencePanel.id = "game-sequence";
  sequencePanel.className = "sequence-panel";
  sequencePanel.setAttribute("aria-labelledby", "sequence-title");
  let last = null,
    steps = "";
  for (const s of data.steps.map((x) => localizeRow(x, "sequence"))) {
    if (s.phase !== last) {
      if (last !== null) steps += "</fieldset>";
      steps += `<fieldset><legend>${esc(s.phase)}</legend>`;
      last = s.phase;
    }
    const id = "seq-" + s.code;
    steps += `<article class="sequence-step"><label for="${esc(id)}"><input id="${esc(id)}" type="checkbox" data-step="${esc(s.code)}" ${sequenceContext.checks[s.code] ? "checked" : ""}><strong>${esc(s.label)}</strong></label><p>${esc(s.description)}</p><a href="${esc(s.source_url)}" target="_blank" rel="noopener noreferrer">${t("source")}</a></article>`;
  }
  if (last !== null) steps += "</fieldset>";
  sequencePanel.innerHTML = `<header><div><span class="eyebrow">KILLSTASS / ${esc(edition)}</span><h2 id="sequence-title">${t("gameSequence")}</h2></div><button type="button" class="secondary" data-sequence-close aria-label="${t("close")}">×</button></header><div class="sequence-scroll"><p class="muted">${esc(data.rules_version)}<br>${t("retrievedAt")}: ${esc(date(data.retrieved_at))}</p><p>${t("sequenceLocalHint")}</p>${steps}<section><h3>${t("rulesSearch")}</h3><form id="reference-search"><label>${t("searchRule")}<input name="q" maxlength="120" type="search"></label><button>${t("search")}</button></form><div id="reference-results" aria-live="polite"></div></section><button type="button" class="secondary" data-sequence-reset>${t("resetChecklist")}</button></div>`;
  document.body.append(sequencePanel);
  document.body.classList.add("sequence-open");
  button.setAttribute("aria-expanded", "true");
  sequencePanel.querySelector("[data-sequence-close]").focus();
  if (innerWidth <= 1100 && currentMatch.status !== "setup") {
    const score = document.querySelector(".scoreboard");
    const host = document.querySelector("#app");
    if (score)
      host.scrollTop +=
        score.getBoundingClientRect().top -
        host.getBoundingClientRect().top -
        8;
  }
}

/* v1.12: the query in the core rules book (#core). */
const coreLink = (q) =>
  q.length >= 2
    ? `<p><a href="#core/search/${encodeURIComponent(q)}">${esc(t("cr_findInCore").replace("{q}", q))}</a></p>`
    : "";

/* v1.9: listeners are registered from main.js in a fixed order (the former <script> order). */
export function init() {
  document.addEventListener("click", (e) => {
    const button = e.target.closest("[data-sequence]");
    if (button) {
      if (button.disabled) return;
      button.disabled = true;
      openSequence(button)
        .catch((err) => notify(err.message))
        .finally(() => {
          button.disabled = false;
        });
      return;
    }
    if (e.target.closest("[data-sequence-close]")) closeSequence();
    if (e.target.closest("[data-sequence-reset]") && sequenceContext) {
      sequenceContext.checks = {};
      safeStorage.set(sequenceContext.key, {});
      sequencePanel
        .querySelectorAll("[data-step]")
        .forEach((x) => (x.checked = false));
    }
  });
  document.addEventListener("change", (e) => {
    if (e.target.matches("[data-step]") && sequenceContext) {
      sequenceContext.checks[e.target.dataset.step] = e.target.checked;
      safeStorage.set(sequenceContext.key, sequenceContext.checks);
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && sequencePanel) {
      e.preventDefault();
      closeSequence();
    }
  });
  window.addEventListener("hashchange", closeSequence);
  /* v1.11: the side panel searches the whole reference (rules, Tac Ops, teams), like the #reference page. */
  document.addEventListener("submit", async (e) => {
    if (e.target.id !== "reference-search") return;
    e.preventDefault();
    const target = document.querySelector("#reference-results");
    const q = String(new FormData(e.target).get("q") || "").trim();
    try {
      const data = await api(
        `/reference/search?q=${encodeURIComponent(q)}&lang=${lang}&limit=8`,
      );
      if (target)
        target.innerHTML = data.results.length
          ? `${data.results.map((r) => hitCard(r, data.terms)).join("")}<p><a href="#reference/${encodeURIComponent(q)}">${t("ref_openAll")} (${data.total})</a></p>${coreLink(q)}`
          : `<p>${t("noRules")}</p>${coreLink(q)}`;
    } catch (err) {
      notify(err.message);
    }
  });
}
