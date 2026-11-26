import { api, app, esc, lang, me, t } from "./core.js";
/* v1.13 — tooltips for game terms, terrain types, universal actions and weapon rules.
   The terms and their official definitions come from the core rules (tools/core-rules/src/terms.md →
   api/data/core-rules.json → GET /api/reference/terms); nothing is added to the imported team data.
   Pages mark the text that may carry them: data-terms="text" (rules text: the first mention of each term in
   the block) or data-terms="wr" (the weapon rules of a datacard: every rule); data-terms-skip lists the terms or
   core sections not to mark there (a section does not explain its own terms). A MutationObserver on #app
   decorates new blocks; one shared tooltip (role=tooltip) opens on hover, focus or tap, stays while the
   pointer is over it, and closes with Escape, a tap elsewhere or scrolling (a pinned or focused one follows
   its term). */
let data = null,
  loading = null,
  rx = null,
  tip = null,
  current = null,
  pinned = false,
  showTimer = 0,
  hideTimer = 0;
const SKIP =
  "a, button, label, select, option, textarea, input, h1, h2, h3, h4, h5, h6, summary, code, pre, .term, .cr-ap, [data-no-terms]";
const KIND = {
  term: "term_kind_term",
  terrain: "term_kind_terrain",
  action: "term_kind_action",
  weapon: "term_kind_weapon",
};
const rich = (s) =>
  esc(s)
    .replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>")
    .replace(/\*([^*\n]+)\*/g, "<i>$1</i>");

/* One RegExp per context (t: rules text, w: weapon rules) and case mode, the longest aliases first. */
function setData(d) {
  if (!d?.terms) return;
  const lists = { t: { s: [], i: [] }, w: { s: [], i: [] } };
  d.terms.forEach((term, k) =>
    term.alias.forEach((a) => {
      if (a.t) lists.t[a.t].push([a.n, a.re, k]);
      if (a.w) lists.w[a.w].push([a.n, a.re, k]);
    }),
  );
  rx = {};
  for (const c of ["t", "w"])
    rx[c] = ["s", "i"]
      .map((mode) => {
        const list = lists[c][mode].sort((x, y) => y[0] - x[0]);
        return list.length
          ? {
              re: new RegExp(
                list.map((x) => `(${x[1]})`).join("|"),
                mode === "i" ? "gi" : "g",
              ),
              map: list.map((x) => x[2]),
            }
          : null;
      })
      .filter(Boolean);
  data = d;
}
export function provideTerms(doc) {
  if (!data && doc?.terms) {
    setData(doc);
    scan();
  }
}
export const termsReady = () => !!data;

/* The earliest match of any alias (the longer one at the same place). */
function nextMatch(text, from, list) {
  let best = null;
  for (const r of list) {
    r.re.lastIndex = from;
    const m = r.re.exec(text);
    if (!m) continue;
    if (
      !best ||
      m.index < best.index ||
      (m.index === best.index && m[0].length > best.text.length)
    ) {
      let g = 1;
      while (m[g] === undefined) g++;
      best = { index: m.index, text: m[0], term: r.map[g - 1] };
    }
  }
  return best;
}
/* In rules text a weapon rule is a capitalised word: not when it is part of a name («Shock Assault»,
   «Stun Grenade»); a capitalised keyword before it is fine («WR Range 6"»). */
const inName = (text, start, end) =>
  /[A-Z][a-z][\w’'-]*\s$/.test(text.slice(Math.max(0, start - 40), start)) ||
  /^\s[A-Z][a-z]/.test(text.slice(end, end + 3));

function decorate(scope) {
  scope.dataset.termsDone = "1";
  const mode = scope.dataset.terms === "wr" ? "w" : "t";
  const skip = new Set((scope.dataset.termsSkip || "").split(/\s+/));
  const seen = new Set();
  const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, {
    acceptNode(n) {
      const p = n.parentElement;
      if (!p || !n.data.trim() || p.closest("[data-terms]") !== scope)
        return NodeFilter.FILTER_REJECT;
      const no = p.closest(SKIP);
      return no && scope.contains(no)
        ? NodeFilter.FILTER_REJECT
        : NodeFilter.FILTER_ACCEPT;
    },
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    const text = node.data;
    let from = 0,
      last = 0,
      out = null;
    for (;;) {
      const hit = nextMatch(text, from, rx[mode]);
      if (!hit) break;
      const term = data.terms[hit.term],
        end = hit.index + hit.text.length;
      from = end;
      if (skip.has(term.id) || skip.has(term.sec)) continue;
      if (mode === "t" && seen.has(hit.term)) continue;
      if (
        mode === "t" &&
        term.kind === "weapon" &&
        inName(text, hit.index, end)
      )
        continue;
      seen.add(hit.term);
      out ??= document.createDocumentFragment();
      out.append(text.slice(last, hit.index));
      const span = document.createElement("span");
      span.className = "term";
      span.dataset.term = term.id;
      span.tabIndex = 0;
      span.setAttribute("role", "button");
      span.textContent = hit.text;
      out.append(span);
      last = end;
    }
    if (out) {
      out.append(text.slice(last));
      node.replaceWith(out);
    }
  }
}
function scan() {
  const scopes = app.querySelectorAll("[data-terms]:not([data-terms-done])");
  if (!scopes.length) return;
  if (!data) return load();
  scopes.forEach(decorate);
}
function load() {
  if (loading || !me) return;
  loading = api("/reference/terms")
    .then((d) => {
      setData(d);
      scan();
    })
    .catch(() => setTimeout(() => (loading = null), 30000));
}

/* ---------- the tooltip ---------- */
function body(term) {
  const parts = [];
  let list = null;
  for (const d of term.def) {
    const m = /^(- |▶ |◆ |\d+\) )/.exec(d);
    if (!m) {
      list = null;
      parts.push(`<p>${rich(d)}</p>`);
      continue;
    }
    if (!list) parts.push((list = []));
    const mark = m[1].trim();
    list.push(
      `<li${mark === "-" ? "" : ` data-mark="${esc(mark)}"`}>${rich(d.slice(m[1].length))}</li>`,
    );
  }
  const where = lang === "en" ? term.where : term.where_ru;
  return `<p class="term-tip-head"><span class="term-tip-kind">${esc(t(KIND[term.kind]))}</span><b lang="en">${esc(term.name)}</b>${lang === "en" ? "" : `<span class="term-tip-ru">${esc(term.ru)}</span>`}</p><div class="term-tip-def" lang="en">${parts.map((p) => (Array.isArray(p) ? `<ul>${p.join("")}</ul>` : p)).join("")}</div><p class="term-tip-src">${esc(t("term_source").replace("{where}", where))}</p>`;
}
function ensureTip() {
  if (tip) return tip;
  tip = document.createElement("div");
  tip.id = "term-tip";
  tip.className = "term-tip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  tip.addEventListener("mouseenter", () => clearTimeout(hideTimer));
  tip.addEventListener("mouseleave", () => pinned || hideSoon());
  document.body.append(tip);
  return tip;
}
function place(el) {
  const r = el.getBoundingClientRect(),
    vw = document.documentElement.clientWidth,
    vh = window.innerHeight;
  tip.style.left = "0px";
  tip.style.top = "0px";
  const w = tip.offsetWidth,
    h = tip.offsetHeight;
  const left = Math.max(8, Math.min(r.left + r.width / 2 - w / 2, vw - w - 8));
  let top = r.bottom + 6;
  if (top + h > vh - 8 && r.top - 6 - h >= 8) top = r.top - 6 - h;
  tip.style.left = Math.round(left) + "px";
  tip.style.top = Math.round(Math.max(8, top)) + "px";
}
function show(el, pin = false) {
  const term = data?.terms.find((x) => x.id === el.dataset.term);
  if (!term || !el.isConnected) return;
  clearTimeout(showTimer);
  clearTimeout(hideTimer);
  if (current && current !== el) current.removeAttribute("aria-describedby");
  const box = ensureTip();
  if (current !== el || box.hidden) {
    box.innerHTML = body(term);
    box.dataset.term = term.id;
  }
  current = el;
  pinned = pin;
  box.classList.toggle("pinned", pin);
  box.hidden = false;
  el.setAttribute("aria-describedby", "term-tip");
  place(el);
}
export function hideTerm() {
  clearTimeout(showTimer);
  clearTimeout(hideTimer);
  if (tip) tip.hidden = true;
  current?.removeAttribute("aria-describedby");
  current = null;
  pinned = false;
}
const hideSoon = () => {
  clearTimeout(hideTimer);
  hideTimer = setTimeout(hideTerm, 200);
};
const termOf = (e) =>
  e.target instanceof Element ? e.target.closest(".term[data-term]") : null;

export function init() {
  new MutationObserver(scan).observe(app, { childList: true, subtree: true });
  document.addEventListener("mouseover", (e) => {
    const el = termOf(e);
    if (!el || pinned) return;
    clearTimeout(hideTimer);
    if (el === current) return;
    clearTimeout(showTimer);
    showTimer = setTimeout(() => show(el), 150);
  });
  document.addEventListener("mouseout", (e) => {
    const el = termOf(e);
    if (!el) return;
    clearTimeout(showTimer);
    if (el === current && !pinned) hideSoon();
  });
  document.addEventListener("focusin", (e) => {
    const el = termOf(e);
    if (el && el !== current) show(el);
  });
  document.addEventListener("focusout", (e) => {
    if (termOf(e) === current && !pinned) hideTerm();
  });
  document.addEventListener("click", (e) => {
    const el = termOf(e);
    if (el) {
      if (pinned && el === current) hideTerm();
      else show(el, true);
    } else if (
      current &&
      !(e.target instanceof Element && e.target.closest("#term-tip"))
    )
      hideTerm();
  });
  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key === "Escape" && current) {
        hideTerm();
        e.stopPropagation();
      } else if ((e.key === "Enter" || e.key === " ") && termOf(e)) {
        e.preventDefault();
        const el = termOf(e);
        if (pinned && el === current) hideTerm();
        else show(el, true);
      }
    },
    true,
  );
  addEventListener(
    "scroll",
    (e) => {
      if (
        !current ||
        (tip && e.target instanceof Node && tip.contains(e.target))
      )
        return;
      /* A pinned or focused tooltip follows its term (focus itself may scroll it into view). */
      const r = current.getBoundingClientRect();
      if (
        (pinned || document.activeElement === current) &&
        r.bottom > 0 &&
        r.top < innerHeight
      )
        place(current);
      else hideTerm();
    },
    { passive: true, capture: true },
  );
  addEventListener("resize", hideTerm);
  addEventListener("hashchange", hideTerm);
}
