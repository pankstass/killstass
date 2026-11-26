import { api, catalogs, date, esc, icon, lang, notify, t } from "./core.js";
import { page, rulesTitle, shell } from "./app.js";
import { loadTeamIndex, teamTitle } from "./teams.js";
/* v1.11 — «Справочник» (#reference, #reference/<query>): one search over the general rules (warhammer-oracle:
   weapon rules from BSData, phase overview), Tac Ops, missions, rule summaries and the game sequence (KILLSTASS
   catalog) and the imported teams (operatives, faction rules, ploys, equipment — BSData and kt-datacards).
   Without a query the weapon rules (English original + Russian paraphrase) and the phase overview are listed.
   Without a connection the saved general rules, Tac Ops and missions are searched in the browser. */
const KINDS = ["", "rules", "ops", "teams", "operatives", "ploys", "equipment"];
const LIMIT = 20;
let library = null,
  state = { q: "", kind: "", team: "", offset: 0 },
  timer = 0,
  seq = 0;

export const fold = (s) =>
  String(s ?? "")
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/\s+/g, " ")
    .trim();
export const words = (s) =>
  (fold(s).match(/[\p{L}\p{N}]+/gu) || []).slice(0, 8);
const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
/* Escaped text with **bold** / *italic* of the sources and the search terms marked. */
export function richText(text, terms = []) {
  const s = String(text ?? "");
  const re = terms.length
    ? new RegExp(
        "(" + terms.map((w) => reEsc(w).replace(/е/g, "[её]")).join("|") + ")",
        "giu",
      )
    : null;
  const marked = re
    ? s
        .split(re)
        .map((part, i) => (i % 2 ? `\u0001${esc(part)}\u0002` : esc(part)))
        .join("")
    : esc(s);
  return marked
    .replace(/\*\*\*([^*\n]+)\*\*\*/g, "<b><i>$1</i></b>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>")
    .replace(/\*([^*\n]+)\*/g, "<i>$1</i>")
    .replaceAll("\u0001", "<mark>")
    .replaceAll("\u0002", "</mark>");
}
const paragraphs = (text, terms) =>
  String(text ?? "")
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => `<p>${richText(l, terms)}</p>`)
    .join("");
const kindLabel = (r) =>
  t(
    r.kind === "ploy"
      ? /\/sp-/.test(r.link || "")
        ? "rk_ploy_strategy"
        : "rk_ploy_firefight"
      : "rk_" + r.kind,
  );
const teamName = (team) =>
  lang === "en" || !team.label ? team.name : team.label;

/* «Up to date as of»: rules import (oracle release), team import (commits), catalog version, last check. */
export function statusLine(s) {
  if (!s) return "";
  const parts = [];
  if (s.rules)
    parts.push(
      `${t("ref_rulesFrom")} <a href="https://github.com/${esc(s.rules.oracle?.repo || "gregario/warhammer-oracle")}" target="_blank" rel="noopener noreferrer">warhammer-oracle</a> <span class="mono">${esc(s.rules.oracle?.tag || "")}</span> — ${esc(date(s.rules.imported_at))}`,
    );
  else parts.push(t("ref_noRules"));
  if (s.teams)
    parts.push(
      `${t("ref_teamsFrom")} — ${esc(date(s.teams.imported_at))} (${s.teams.teams} / ${s.teams.operatives})`,
    );
  if (s.catalog)
    parts.push(`${t("ref_opsFrom")}: ${esc(s.catalog.rules_version)}`);
  if (s.checked_at)
    parts.push(`${t("ref_checked")} ${esc(date(s.checked_at))}`);
  return `<p class="muted ref-status">${t("ref_actual")}: ${parts.join(" · ")}</p>`;
}

function ruleCard(r, terms = []) {
  const ru = lang !== "en" && r.text_ru;
  const flag =
    r.verification === "unverified"
      ? `<span class="badge warn" title="${esc(t("ref_unverifiedHint"))}">${t("ref_unverified")}</span>`
      : `<span class="src-note" title="${esc(t("bsdataTextHint"))}">BSData</span>`;
  const tips = r.details?.tips?.length
    ? `<details><summary>${t("ref_tips")}</summary>${r.details.tips.map((x) => `<p>${richText(x, terms)}</p>`).join("")}</details>`
    : "";
  return `<article class="panel ref-rule" id="rule-${esc(r.code)}"><header><h3>${richText(r.name, terms)}</h3>${r.name_ru && lang !== "en" ? `<span class="muted">${esc(r.name_ru)}</span>` : ""}${flag}</header>${
    ru
      ? `${paragraphs(r.text_ru, terms)}<details><summary>${t("ref_original")}</summary><div lang="en" data-terms="text" data-terms-skip="${esc(r.code)}">${paragraphs(r.text_en, terms)}</div></details>`
      : `<div lang="en" data-terms="text" data-terms-skip="${esc(r.code)}">${paragraphs(r.text_en, terms)}</div>`
  }${tips}</article>`;
}

export function hitCard(r, terms) {
  const head = `<header><span class="badge">${esc(kindLabel(r))}</span><h3>${richText(r.title, terms)}</h3>${
    r.team
      ? `<span class="muted">${esc(teamName(r.team))}</span>`
      : r.subtitle
        ? `<span class="muted">${richText(r.subtitle, terms)}</span>`
        : ""
  }${r.verification === "unverified" ? `<span class="badge warn" title="${esc(t("ref_unverifiedHint"))}">${t("ref_unverified")}</span>` : ""}</header>`;
  if (r.team)
    return `<article class="panel ref-hit">${head}<p lang="en" data-terms="text">${richText(r.snippet, terms)}</p><p class="row"><a class="button secondary small" href="${esc(r.link)}">${icon("book")}${t("ref_open")}</a></p></article>`;
  const text =
    lang !== "en" && r.text_ru
      ? `${paragraphs(r.text_ru, terms)}<details><summary>${t("ref_original")}</summary><div lang="en" data-terms="text">${paragraphs(r.text, terms)}</div></details>`
      : `<div lang="en" data-terms="text">${paragraphs(r.text, terms)}</div>`;
  return `<article class="panel ref-hit">${head}${text}${
    /^https:\/\//.test(r.source_url || "")
      ? `<p><a href="${esc(r.source_url)}" target="_blank" rel="noopener noreferrer">${t("source")} ↗</a></p>`
      : ""
  }</article>`;
}

/* Offline: weapon rules and phases from the saved library, Tac Ops / missions / rules from the catalog. */
function localSearch(q, kind) {
  const f = fold(q),
    ws = words(q);
  /* As on the server: exact name 10, starts with the query 6, a word of it does 4, contains it 3. */
  const named = (n) =>
    n === f
      ? 10
      : n.startsWith(f)
        ? 6
        : n.includes(" " + f)
          ? 4
          : n.includes(f)
            ? 3
            : 0;
  const score = (names, text) => {
    const tf = names.map(fold).join(" "),
      xf = fold(text);
    const s = Math.max(0, ...names.map((n) => named(fold(n))));
    const tokens = (tf + " " + xf).match(/[\p{L}\p{N}]+/gu) || [];
    const hits = ws.filter((w) => tokens.some((x) => x.startsWith(w))).length;
    if (!s && !xf.includes(f) && (!ws.length || hits < ws.length)) return -1;
    return s + (2 * hits) / Math.max(ws.length, 1);
  };
  const out = [];
  if (!kind || kind === "rules")
    for (const r of library?.rules || []) {
      const s = score(
        [r.name, r.name_ru || "", ...(r.aliases || [])],
        r.text_en + " " + (r.text_ru || ""),
      );
      if (s >= 0)
        out.push({
          s,
          r: {
            kind: r.kind,
            title: r.name,
            subtitle: r.name_ru,
            text: r.text_en,
            text_ru: r.text_ru,
            verification: r.verification,
          },
        });
    }
  if (!kind || kind === "ops" || kind === "rules")
    for (const c of catalogs) {
      if (!c.active || c.verification !== "verified" || c.edition !== "2024")
        continue;
      if (
        !(
          kind === "rules"
            ? ["rule"]
            : kind === "ops"
              ? ["mission", "tac_op"]
              : ["mission", "tac_op", "rule"]
        ).includes(c.kind)
      )
        continue;
      const text = [c.config?.archetype, c.config?.reveal, c.config?.summary]
        .filter(Boolean)
        .join("\n");
      const s = score([c.label, c.label_en || ""], text);
      if (s >= 0)
        out.push({
          s: s + 1.5,
          r: {
            kind: c.kind,
            title: c.label,
            subtitle: lang === "en" ? "" : c.label_en,
            text,
            source_url: c.source_url,
            verification: c.verification,
          },
        });
    }
  return out.sort((a, b) => b.s - a.s).map((x) => x.r);
}

function browse() {
  const rules = (library?.rules || []).filter((r) => r.kind === "weapon_rule");
  const phases = (library?.rules || []).filter((r) => r.kind === "phase");
  if (!rules.length && !phases.length)
    return `<section class="panel"><h2>${t("ref_noRulesTitle")}</h2><p>${t("ref_noRulesHint")}</p><pre class="mono">./scripts/update-reference.sh</pre></section>`;
  return `<h2 class="section-label">${t("ref_weaponRules")}</h2><div class="rule-list ref-rules">${rules.map((r) => ruleCard(r)).join("")}</div>${
    phases.length
      ? `<h2 class="section-label">${t("ref_phases")}</h2><p class="muted">${t("ref_phasesHint")}</p><div class="rule-list">${phases.map((r) => ruleCard(r)).join("")}</div>`
      : ""
  }<p class="muted">${t("ref_disclaimer")}</p>`;
}

async function runSearch(more = false) {
  const box = document.querySelector("#ref-results");
  if (!box) return;
  const { q, kind, team } = state;
  const mine = ++seq;
  if (fold(q).length < 2 && !kind && !team) {
    box.innerHTML = browse();
    return;
  }
  if (!more) state.offset = 0;
  let data,
    offline = false;
  try {
    data = await api(
      `/reference/search?q=${encodeURIComponent(q)}&kind=${kind}&team=${encodeURIComponent(team)}&lang=${lang}&limit=${LIMIT}&offset=${state.offset}`,
    );
  } catch (err) {
    if (err.code !== "network") {
      if (mine === seq)
        box.innerHTML = `<p class="empty">${esc(err.message)}</p>`;
      return;
    }
    offline = true;
    const results = team ? [] : localSearch(q, kind);
    data = {
      total: results.length,
      offset: 0,
      terms: words(q),
      results: results.slice(0, 50),
    };
  }
  if (mine !== seq || page !== "reference") return;
  const html = data.results.map((r) => hitCard(r, data.terms)).join("");
  const hasMore = !offline && data.offset + data.results.length < data.total;
  const list = box.querySelector(".ref-list");
  if (more && list) {
    list.insertAdjacentHTML("beforeend", html);
    box.querySelector("[data-ref-more]")?.toggleAttribute("hidden", !hasMore);
    return;
  }
  /* v1.12: the same query in the core rules book (#core, searched in the browser) */
  const core =
    fold(q).length >= 2
      ? ` · <a href="#core/search/${encodeURIComponent(q)}">${esc(t("cr_findInCore").replace("{q}", q))}</a>`
      : "";
  box.innerHTML = `${offline ? `<p class="warning">${t("ref_offline")}</p>` : ""}<p class="muted" role="status">${data.total ? `${t("ref_found")}: ${data.total}` : t("nothingFound")}${core}</p><div class="ref-list">${html}</div><button type="button" class="secondary" data-ref-more ${hasMore ? "" : "hidden"}>${t("ref_more")}</button>`;
}

export async function referenceRoute(parts) {
  state = {
    q: decodeURIComponent(parts[0] || ""),
    kind: "",
    team: "",
    offset: 0,
  };
  const [lib, ix] = await Promise.all([
    api("/reference/library").catch(() => library),
    loadTeamIndex(),
  ]);
  library = lib || library;
  if (page !== "reference") return;
  const teams = [...(ix?.teams || [])].sort((a, b) =>
    teamTitle(a).localeCompare(teamTitle(b)),
  );
  shell(
    `${rulesTitle("rules_quick")}${statusLine(library?.status)}<form id="ref-form" class="panel ref-search" role="search"><label>${t("ref_searchLabel")}<input id="ref-q" name="q" type="search" maxlength="120" autocomplete="off" spellcheck="false" placeholder="${esc(t("ref_searchHint"))}" value="${esc(state.q)}"></label><div class="ref-filters"><fieldset class="segmented ref-kinds"><legend>${t("ref_section")}</legend>${KINDS.map((k) => `<label><input type="radio" name="kind" value="${k}" ${k === state.kind ? "checked" : ""}>${t("ref_kind_" + (k || "all"))}</label>`).join("")}</fieldset><label>${t("ref_team")}<select name="team"><option value="">${t("ref_allTeams")}</option>${teams.map((x) => `<option value="${esc(x.slug)}">${esc(teamTitle(x))}</option>`).join("")}</select></label></div></form><div id="ref-results" aria-live="polite"></div>`,
  );
  await runSearch();
}

function readForm() {
  const form = document.querySelector("#ref-form");
  if (!form) return;
  const d = new FormData(form);
  state.q = String(d.get("q") || "");
  state.kind = String(d.get("kind") || "");
  state.team = String(d.get("team") || "");
  // The query is kept in the address (back button, sharing) without re-rendering the page.
  history.replaceState(
    null,
    "",
    "#reference" + (state.q ? "/" + encodeURIComponent(state.q) : ""),
  );
}

/* v1.9 order: listeners are registered from main.js. */
export function init() {
  document.addEventListener("input", (e) => {
    if (e.target.id !== "ref-q") return;
    clearTimeout(timer);
    timer = setTimeout(() => {
      readForm();
      runSearch().catch((err) => notify(err.message));
    }, 280);
  });
  document.addEventListener("change", (e) => {
    if (!e.target.closest("#ref-form") || e.target.id === "ref-q") return;
    readForm();
    runSearch().catch((err) => notify(err.message));
  });
  document.addEventListener("submit", (e) => {
    if (e.target.id !== "ref-form") return;
    e.preventDefault();
    clearTimeout(timer);
    readForm();
    runSearch().catch((err) => notify(err.message));
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-ref-more]")) return;
    state.offset += LIMIT;
    runSearch(true).catch((err) => notify(err.message));
  });
}
