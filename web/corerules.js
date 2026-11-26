import { api, esc, icon, lang, t } from "./core.js";
import { page, rulesTitle, shell } from "./app.js";
import { groupPage } from "./groups.js";
import { fold, richText, words } from "./library.js";
import { provideTerms } from "./terms.js";
/* v1.12 — «Правила» (#rules): three ways into the rules — Quick Reference (#reference, the v1.11 search),
   Core Rules (#core) and Faction Rules (#teams). «Основные правила» (#core, #core/<chapter|section>[/<heading>],
   #core/search/<query>): the current Kill Team core rules — the core book text with the official updates
   applied (api/data/core-rules.json; v1.13: no change marks, no page numbers): contents, one page per chapter,
   a search in the browser — also offline, from the copy the service worker keeps — where Russian terms find
   the English ones («укрытие» → cover, «затенение» → obscured). */
let doc = null,
  units = null,
  marks = [],
  fromQuery = "",
  timer = 0,
  spy = null;

/* Russian stems -> English rule terms (the text is English; the section titles also have Russian names). */
const GLOSSARY = [
  [["укрыт"], ["cover"]],
  [["затен", "заслон"], ["obscured"]],
  [["видим", "видн", "видет"], ["visible"]],
  [["перекры", "помех"], ["intervening"]],
  [["контрол"], ["control"]],
  [["дистанц", "дальн"], ["range"]],
  [["приказ"], ["order"]],
  [["скрыт", "маскир"], ["conceal"]],
  [["вступ", "сближ"], ["engage"]],
  [["рывок", "рывк"], ["dash"]],
  [["перемещ"], ["reposition", "move"]],
  [
    ["движен", "передвиж", "двига"],
    ["move", "movement"],
  ],
  [["отступ", "отход"], ["fall back"]],
  [["прыж", "прыг"], ["jump"]],
  [["спрыг", "падени", "спуск", "спуст"], ["drop"]],
  [
    ["лазат", "лазить", "залез", "карабк", "взбир", "подъем", "подня"],
    ["climb"],
  ],
  [["стрел", "выстрел", "обстрел"], ["shoot"]],
  [
    ["ближн", "рукопаш", "схватк"],
    ["fight", "melee"],
  ],
  [["атак"], ["attack"]],
  [["урон", "поврежд"], ["damage"]],
  [
    ["раны", "рана", "ранени", "ранен"],
    ["wound", "injured"],
  ],
  [["инициатив"], ["initiative"]],
  [["уловк", "плой"], ["ploy"]],
  [["снаряж", "экипир"], ["equipment"]],
  [["маркер"], ["marker"]],
  [["жетон", "фишк"], ["token"]],
  [["цел"], ["target"]],
  [["допуст"], ["valid"]],
  [["объект", "точк", "контрольн"], ["objective"]],
  [["мисси"], ["mission"]],
  [["операц"], ["op", "operation"]],
  [["двер"], ["door"]],
  [["люк"], ["hatchway", "hatch"]],
  [["тяжел"], ["heavy"]],
  [["легк"], ["light"]],
  [["блокир"], ["blocking"]],
  [["возвыш", "высот"], ["vantage"]],
  [["доступ", "проходим"], ["accessible"]],
  [["незначит", "несуществ"], ["insignificant"]],
  [["открыт", "оголен"], ["exposed"]],
  [["потол", "навес"], ["ceiling"]],
  [["контрудар", "контратак", "противодейств"], ["counteract"]],
  [["охран", "страж", "дозор"], ["guard"]],
  [["оруж"], ["weapon"]],
  [["крит"], ["critical", "crit"]],
  [
    ["успех", "попадан"],
    ["success", "hit"],
  ],
  [
    ["провал", "промах"],
    ["fail", "miss"],
  ],
  [
    ["кубик", "куб", "кост"],
    ["dice", "d6", "d3"],
  ],
  [["брос", "броск"], ["roll"]],
  [["переброс"], ["re-roll"]],
  [
    ["защит", "спасбр", "сейв"],
    ["defence", "save"],
  ],
  [["выведен", "выбыв", "выбыт", "убит"], ["incapacitated"]],
  [["поворот", "раунд"], ["turning point"]],
  [["фаз"], ["phase"]],
  [["стратег"], ["strategy"]],
  [["перестрел"], ["firefight"]],
  [["активац", "активир"], ["activat"]],
  [["действи"], ["action"]],
  [["команд"], ["team", "command"]],
  [["оператив", "боец", "бойц", "модел"], ["operative"]],
  [["карточ", "датакард"], ["datacard"]],
  [["ключев"], ["keyword"]],
  [["основан", "подстав", "база", "базы"], ["base"]],
  [
    ["расстоян", "измер"],
    ["distance", "measure"],
  ],
  [["высадк", "развертыв", "деплой"], ["drop zone"]],
  [
    ["килзон", "карта", "карты", "карте", "карту"],
    ["killzone", "map"],
  ],
  [["местност", "рельеф", "террейн"], ["terrain"]],
  [["руин"], ["ruin"]],
  [["крепост", "укреплен", "бастион"], ["stronghold"]],
  [["обломк", "завал", "щебен"], ["rubble"]],
  [["стен"], ["wall"]],
  [["правил"], ["rule"]],
  [["приоритет", "старшинств"], ["precedence"]],
  [["гамбит"], ["gambit"]],
  [["готов"], ["ready"]],
  [["исчерпан", "истрач", "отработ"], ["expended"]],
  [["очк", "очед"], ["point"]],
  [["побед"], ["victory"]],
  [["взрыв", "бласт"], ["blast"]],
  [["смертонос", "летал"], ["lethal"]],
  [["точн", "аккурат"], ["accurate"]],
  [["разруш", "девастейт", "опустош"], ["devastating"]],
  [["пронз", "бронебой"], ["piercing"]],
  [["безжалост", "неумолим"], ["relentless"]],
  [["беспрестан", "непрерывн", "бесконечн"], ["ceaseless"]],
  [["насыщ"], ["saturate"]],
  [["бесшум", "тих"], ["silent"]],
  [["жесток", "брутал"], ["brutal"]],
  [["баланс"], ["balanced"]],
  [["поток", "торрент"], ["torrent"]],
  [["перегрев", "горяч"], ["hot"]],
  [["сокруш", "карающ"], ["punishing"]],
  [["рвущ", "разрыв"], ["rending"]],
  [["ограничен"], ["limited"]],
  [["поиск", "ищущ", "наведен"], ["seek"]],
  [["шок", "ударн"], ["shock"]],
  [["оглуш"], ["stun"]],
  [["гарнизон"], ["garrisoned"]],
  [["побег", "эвакуац"], ["escape"]],
  [["саботаж", "диверс"], ["sabotage"]],
  [["прорыв", "брешь", "бреш"], ["breach"]],
  [["лут", "добыч", "трофе"], ["loot"]],
  [["захват", "удерж"], ["secure"]],
  [["кооператив", "совместн"], ["joint"]],
  [["соло", "одиночн"], ["solo"]],
  [["поведен"], ["behaviour"]],
  [["угроз"], ["threat"]],
  [["линия", "линии", "прицел"], ["targeting line"]],
  [["этаж", "уровн", "ярус"], ["level"]],
  [["бортик", "парапет", "огражд"], ["rampart"]],
  [["окн"], ["window"]],
  [["лестниц"], ["ladder"]],
  [["мостк", "эстакад", "гантри"], ["gantry"]],
  [["опасн"], ["hazardous"]],
  [["последоват"], ["sequence"]],
];
/* Search text: folded, letters and digits only («re-roll» -> «re roll»), so that " " + term finds a word start. */
const norm = (s) =>
  " " + (fold(s).match(/[\p{L}\p{N}]+/gu) || []).join(" ") + " ";
const plain = (s) => String(s ?? "").replace(/\*+/g, "");
const gloss = (ru) =>
  lang === "en" || !ru ? "" : `<span class="muted cr-ru">${esc(ru)}</span>`;
const sectionHref = (id, anchor = "") =>
  "#core/" + id + (anchor ? "/" + anchor : "");

async function load() {
  if (!doc) {
    doc = await api("/reference/core-rules");
    provideTerms(doc); // v1.13: the tooltips need no second request here
  }
  return doc;
}
function lookup(id) {
  for (const ch of doc.chapters) {
    if (ch.id === id) return { ch, sec: null };
    const sec = ch.sections.find((s) => s.id === id);
    if (sec) return { ch, sec };
  }
  return null;
}
const neighbours = (ch) => {
  const i = doc.chapters.indexOf(ch);
  return [doc.chapters[i - 1], doc.chapters[i + 1]];
};

/* ---------- rendering of the source blocks (see tools/core-rules/build.py) ---------- */
function item(it, terms) {
  const sub = it.sub?.length
    ? `<ul>${it.sub.map((x) => item(x, terms)).join("")}</ul>`
    : "";
  return `<li>${richText(it.x, terms)}${sub}</li>`;
}
function block(b, terms) {
  const rt = (x) => richText(x, terms);
  const all = (bl) => bl.map((x) => block(x, terms)).join("");
  let html;
  switch (b.t) {
    case "p":
      html = `<p>${rt(b.x)}</p>`;
      break;
    case "h": {
      const n = Math.min(6, b.l + 1);
      html = `<h${n} class="cr-h" id="cr-${esc(b.id)}" tabindex="-1">${rt(b.x)}</h${n}>`;
      break;
    }
    case "ul":
      html = `<ul>${b.items.map((x) => item(x, terms)).join("")}</ul>`;
      break;
    case "ol":
      html = `<ol class="cr-ol">${b.items.map((x) => `<li value="${esc(x.n)}">${rt(x.x)}${x.sub?.length ? `<ul>${x.sub.map((y) => item(y, terms)).join("")}</ul>` : ""}</li>`).join("")}</ol>`;
      break;
    case "note":
      html = `<aside class="cr-note">${all(b.blocks)}</aside>`;
      break;
    case "ex":
      html = `<p class="cr-ex"><span class="cr-ex-label">${t("cr_figure")}</span> ${rt(b.x)}</p>`;
      break;
    case "box":
      html = `<section class="cr-box">${b.title ? `<h4>${rt(b.title)}</h4>` : ""}${all(b.blocks)}</section>`;
      break;
    case "action":
      html = `<section class="cr-action"><header><h4>${rt(b.name)}</h4><span class="cr-ap">${esc(b.ap)}</span></header><ul class="cr-eff">${b.eff.map((x) => `<li>${rt(x.x)}${x.sub?.length ? `<ul>${x.sub.map((y) => `<li>${rt(y.x)}</li>`).join("")}</ul>` : ""}</li>`).join("")}</ul>${b.cond.length ? `<ul class="cr-cond">${b.cond.map((x) => `<li>${rt(x.x)}</li>`).join("")}</ul>` : ""}</section>`;
      break;
    case "ploy":
      html = `<section class="cr-ploy"><header><h4>${rt(b.name)}</h4><span class="cr-ap">${esc(b.cost)}</span><span class="muted">${esc(b.kind)}</span></header><div class="cr-body">${all(b.blocks)}</div></section>`;
      break;
    case "card":
      html = `<section class="cr-card"><header><h4>${rt(b.name)}</h4><span class="muted">${esc(b.sub)}</span></header><div class="cr-body">${all(b.blocks)}</div></section>`;
      break;
    case "stats":
      html = `<p class="cr-stats">${b.items.map((x) => `<span>${rt(x)}</span>`).join("")}</p>`;
      break;
    case "table":
      html = `<div class="table-wrap cr-table"><table><thead><tr>${b.head.map((x) => `<th scope="col">${rt(x)}</th>`).join("")}</tr></thead><tbody>${b.rows.map((r) => `<tr>${r.map((x) => `<td>${rt(x)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
      break;
    case "flow":
      html = `<div class="cr-flow"><ol>${b.items.map((x) => `<li>${rt(x)}</li>`).join("")}</ol>${b.loop ? `<p class="muted">↻ ${rt(b.loop)}</p>` : ""}</div>`;
      break;
    default:
      html = "";
  }
  return html;
}
const blocks = (bl, terms) => (bl || []).map((b) => block(b, terms)).join("");

/* ---------- search ---------- */
/* the term a paragraph defines: «**Conceal:** The operative…» */
const lead = (x) =>
  (/^\*\*([^*]{1,40}?)(?::\*\*|\*\*:)/.exec(x || "") || [])[1] || "";
function buildUnits() {
  const out = [];
  let order = 0;
  for (const ch of doc.chapters)
    for (const sec of ch.sections) {
      let anchor = "",
        head = "";
      /* name: a heading or an action, ploy or card as it is named (an exact hit ranks higher) */
      const add = (kind, text, name = "") =>
        text &&
        out.push({
          ch,
          sec,
          anchor,
          head,
          kind,
          name: name && norm(name).trim(),
          text: plain(text),
          hay: norm(text),
          order: order++,
        });
      add("title", sec.title + " " + sec.ru);
      const walk = (bl) => {
        for (const b of bl || []) {
          if (b.t === "h") {
            anchor = b.id;
            head = plain(b.x);
            add("h", b.x, b.x);
          } else if (b.t === "p" || b.t === "ex") add("p", b.x, lead(b.x));
          else if (b.t === "ul" || b.t === "ol")
            for (const it of b.items) {
              add("p", it.x, lead(it.x));
              for (const s of it.sub || []) add("p", s.x, lead(s.x));
            }
          else if (b.t === "action") {
            add("h", b.name + " " + b.ap, b.name);
            for (const x of b.eff) {
              add("p", x.x);
              for (const s of x.sub || []) add("p", s.x);
            }
            for (const x of b.cond) add("p", x.x);
          } else if (b.t === "ploy") {
            add("h", b.name + " " + b.cost, b.name);
            walk(b.blocks);
          } else if (b.t === "card") {
            add("h", b.name + " " + b.sub, b.name);
            walk(b.blocks);
          } else if (b.t === "box") {
            if (b.title) add("p", b.title);
            walk(b.blocks);
          } else if (b.t === "note") walk(b.blocks);
          else if (b.t === "stats") add("p", b.items.join(" · "));
          else if (b.t === "flow") add("p", b.items.join(" → "));
          else if (b.t === "table")
            for (const r of [b.head, ...b.rows]) add("p", r.join(" · "));
        }
      };
      walk(sec.blocks);
    }
  return out;
}
/* Every query word must match (a word start; a Russian word also through its English terms). */
function compile(q) {
  const ws = words(q);
  const groups = ws.map((w) => {
    const alts = new Set([norm(w).trim()]);
    for (const [stems, terms] of GLOSSARY)
      if (stems.some((s) => w.startsWith(s)))
        terms.forEach((x) => alts.add(norm(x).trim()));
    return [...alts];
  });
  const marks = new Set(ws.filter((w) => w.length > 1));
  for (const g of groups) for (const a of g.slice(1)) marks.add(a);
  /* «re roll» is highlighted as written in the text */
  return {
    ws,
    groups,
    phrase: norm(q).trim(),
    terms: [...marks].map((x) => (x === "re roll" ? "re-roll" : x)),
  };
}
function search(q) {
  units ||= buildUnits();
  const c = compile(q);
  if (!c.groups.length) return { c, hits: [] };
  /* named as the query or, for one word, as one of its English terms («рывок» → the Dash action) */
  const named = (x) =>
    x === c.phrase || (c.groups.length === 1 && c.groups[0].includes(x));
  const bySec = new Map();
  for (const u of units) {
    if (!c.groups.every((g) => g.some((a) => u.hay.includes(" " + a))))
      continue;
    let s = u.kind === "title" ? 8 : u.kind === "h" ? 5 : 1;
    if (c.ws.length > 1 && u.hay.includes(" " + c.phrase + " ")) s += 2;
    if (
      u.kind === "title" &&
      [u.sec.title, u.sec.ru].some((x) => named(norm(x).trim()))
    )
      s += 6;
    else if (u.name && named(u.name)) s += 3;
    let g = bySec.get(u.sec.id);
    if (!g) bySec.set(u.sec.id, (g = { u, score: 0, units: [] }));
    g.score = Math.max(g.score, s);
    if (u.kind !== "title") g.units.push(u);
  }
  const hits = [...bySec.values()]
    .map((g) => ({ ...g, score: g.score + Math.min(g.units.length, 6) * 0.3 }))
    .sort((a, b) => b.score - a.score || a.u.order - b.u.order);
  return { c, hits };
}
function snippet(text, terms, width = 220) {
  const low = text.toLowerCase().replace(/ё/g, "е");
  const pos = terms
    .map((w) => low.indexOf(w.toLowerCase()))
    .filter((p) => p >= 0);
  if (text.length <= width) return text;
  let start = pos.length ? Math.max(0, Math.min(...pos) - width / 3) : 0;
  if (start) {
    const sp = text.indexOf(" ", start);
    start = sp >= 0 && sp < start + 20 ? sp + 1 : start;
  }
  let end = Math.min(text.length, start + width);
  if (end < text.length) {
    const sp = text.lastIndexOf(" ", end);
    if (sp > start + width / 2) end = sp;
  }
  return (
    (start ? "…" : "") +
    text.slice(start, end).trim() +
    (end < text.length ? "…" : "")
  );
}
function resultsHtml(q) {
  const { c, hits } = search(q);
  if (!hits.length)
    return `<p class="empty" role="status">${t("nothingFound")}</p><p class="muted">${t("cr_searchEnHint")}</p>`;
  const total = hits.reduce((n, g) => n + Math.max(1, g.units.length), 0);
  return `<p class="muted" role="status">${t("cr_found").replace("{n}", hits.length).replace("{m}", total)}</p><div class="ref-list cr-hits">${hits
    .map((g) => {
      const s = g.u.sec;
      const shown = g.units.slice(0, 3);
      return `<article class="panel cr-hit"><header><h3><a href="${sectionHref(s.id)}" data-cr-hit>${richText(s.title, c.terms)}</a></h3>${lang === "en" ? "" : `<span class="muted">${richText(s.ru, c.terms)}</span>`}<span class="muted">${esc(g.u.ch.title)}</span></header>${
        shown.length
          ? `<ul class="cr-snips">${shown.map((u) => `<li><a href="${sectionHref(s.id, u.anchor)}" data-cr-hit>${u.head && u.kind !== "h" ? `<span class="cr-snip-head">${esc(u.head)}</span>` : ""}<span lang="en">${richText(snippet(u.text, c.terms), c.terms)}</span></a></li>`).join("")}</ul>${g.units.length > shown.length ? `<p class="muted">${t("cr_more").replace("{n}", g.units.length - shown.length)}</p>` : ""}`
          : ""
      }</article>`;
    })
    .join("")}</div>`;
}

/* ---------- pages ---------- */
export function rulesPage() {
  /* the core rules are fetched in the background: the service worker keeps them for use without a connection */
  load().catch(() => {});
  groupPage("rules");
}
function sourceLine() {
  return `<p class="muted cr-source">${t("cr_source")}</p>`;
}
function contents(q) {
  shell(
    `${rulesTitle("rules_core")}<p class="muted">${t("cr_intro")}</p><form id="core-form" class="panel ref-search" role="search"><label>${t("cr_searchLabel")}<input id="core-q" name="q" type="search" maxlength="120" autocomplete="off" spellcheck="false" placeholder="${esc(t("cr_searchHint"))}" value="${esc(q)}"></label></form><div id="core-results" aria-live="polite"></div>`,
  );
  showResults(q);
}
function tocHtml() {
  return `<div class="cr-toc">${doc.chapters
    .map(
      (ch) =>
        `<section class="panel cr-chapter"><h2><a href="${sectionHref(ch.id)}">${esc(ch.title)}</a>${gloss(ch.ru)}</h2><ol class="cr-sections">${ch.sections.map((s) => `<li><a href="${sectionHref(s.id)}"><span class="cr-name">${esc(s.title)}</span>${gloss(s.ru)}</a></li>`).join("")}</ol></section>`,
    )
    .join("")}</div>${sourceLine()}`;
}
function showResults(q) {
  const box = document.querySelector("#core-results");
  if (!box) return;
  box.innerHTML = fold(q).length < 2 ? tocHtml() : resultsHtml(q);
}
function chapterPage(ch, target) {
  const terms = marks;
  marks = [];
  const [prev, next] = neighbours(ch);
  const back = fromQuery
    ? `<a class="back" href="#core/search/${encodeURIComponent(fromQuery)}">← ${esc(t("cr_backToResults").replace("{q}", fromQuery))}</a>`
    : `<a class="back" href="#core">← ${t("rules_core")}</a>`;
  const side = `<nav class="cr-side" aria-label="${esc(t("cr_inChapter"))}"><details open><summary>${t("cr_inChapter")}</summary><ol>${ch.sections.map((s) => `<li><a href="${sectionHref(s.id)}" data-cr-sec="${esc(s.id)}">${esc(s.title)}${gloss(s.ru)}</a></li>`).join("")}</ol></details></nav>`;
  const body = ch.sections
    .map(
      (s) =>
        `<section class="cr-section" id="cr-${esc(s.id)}" data-section="${esc(s.id)}" tabindex="-1" data-terms="text" data-terms-skip="${esc(s.id)}"><header class="cr-sec-head"><h2>${richText(s.title, terms)}</h2>${gloss(s.ru)}</header>${blocks(s.blocks, terms)}</section>`,
    )
    .join("");
  shell(
    `<header class="team-header cr-head">${back}<h1>${esc(ch.title)}</h1>${gloss(ch.ru)}</header><div class="cr-layout" data-chapter="${esc(ch.id + ":" + lang)}">${side}<article class="panel cr-text" lang="en">${ch.intro?.length ? `<div class="cr-intro" data-terms="text">${blocks(ch.intro, terms)}</div>` : ""}${body}</article></div><nav class="cr-pager" aria-label="${esc(t("cr_chapters"))}">${prev ? `<a class="button secondary" href="${sectionHref(prev.id)}">← ${esc(prev.title)}</a>` : "<span></span>"}<a class="button secondary" href="#core">${icon("list")}${t("cr_contents")}</a>${next ? `<a class="button secondary" href="${sectionHref(next.id)}">${esc(next.title)} →</a>` : "<span></span>"}</nav>${sourceLine()}`,
  );
  if (matchMedia("(max-width: 900px)").matches)
    document.querySelector(".cr-side details")?.removeAttribute("open");
  watchSections();
  reveal(target, true);
}
/* Scroll to a section or heading of the chapter on screen (the top for the chapter itself). */
function reveal(id, fresh) {
  const el = id ? document.getElementById("cr-" + id) : null;
  if (!el) {
    if (fresh) window.scrollTo(0, 0);
    return;
  }
  el.scrollIntoView({ block: "start" });
  el.focus({ preventScroll: true });
  if (el.matches(".cr-h")) {
    el.classList.remove("ref-target");
    void el.offsetWidth;
    el.classList.add("ref-target");
  }
}
/* The contents beside the text follow the section being read. */
function watchSections() {
  spy?.disconnect();
  if (!("IntersectionObserver" in window)) return;
  spy = new IntersectionObserver(
    (entries) => {
      for (const e of entries)
        if (e.isIntersecting) {
          const id = e.target.dataset.section;
          document
            .querySelectorAll("[data-cr-sec]")
            .forEach((a) =>
              a.toggleAttribute("aria-current", a.dataset.crSec === id),
            );
        }
    },
    { rootMargin: "-20% 0px -70% 0px" },
  );
  document.querySelectorAll(".cr-section").forEach((s) => spy.observe(s));
}

export async function coreRoute(parts) {
  let a = "",
    b = "";
  try {
    [a = "", b = ""] = parts.map(decodeURIComponent);
  } catch {
    /* a broken address shows the contents */
  }
  await load();
  if (page !== "core") return;
  if (!a || a === "search") {
    fromQuery = "";
    return contents(a ? b : "");
  }
  const hit = lookup(a);
  if (!hit) return contents("");
  /* The same chapter is already on screen (same language): only scroll — links of the side contents. */
  const on = document.querySelector(".cr-layout")?.dataset.chapter;
  const first = !hit.sec || hit.sec === hit.ch.sections[0];
  const target = b || (first ? "" : hit.sec.id);
  if (on === hit.ch.id + ":" + lang && !marks.length)
    return reveal(target || (hit.sec ? hit.sec.id : ""), false);
  chapterPage(hit.ch, target);
}

function readQuery() {
  const q = String(document.querySelector("#core-q")?.value || "");
  history.replaceState(
    null,
    "",
    "#core" + (fold(q) ? "/search/" + encodeURIComponent(q) : ""),
  );
  return q;
}

/* v1.9 order: listeners are registered from main.js. */
export function init() {
  document.addEventListener("input", (e) => {
    if (e.target.id !== "core-q") return;
    clearTimeout(timer);
    timer = setTimeout(() => showResults(readQuery()), 200);
  });
  document.addEventListener("submit", (e) => {
    if (e.target.id !== "core-form") return;
    e.preventDefault();
    clearTimeout(timer);
    showResults(readQuery());
  });
  document.addEventListener("click", (e) => {
    const hit = e.target.closest("[data-cr-hit]");
    if (hit) {
      const q = String(document.querySelector("#core-q")?.value || "");
      fromQuery = q;
      marks = compile(q).terms;
    } else if (e.target.closest(".cr-side a, .cr-pager a, .cr-head .back"))
      fromQuery = "";
  });
}
