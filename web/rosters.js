import {
  api,
  app,
  button,
  catName,
  date,
  esc,
  icon,
  input,
  me,
  notify,
  select,
  t,
  uuid,
} from "./core.js";
import { currentMatch, page, shell, title } from "./app.js";
import { copyText } from "./share.js";
import { printButton, printRoster } from "./sheets.js";
import { apBadge, apSplit, ruleText, teamData } from "./teams.js";
/* v1.8 — roster builder (in the spirit of newrecruit.eu): choose operatives and their options from the
   BattleScribe data imported by the operator. The server validates every save (api/rosterkit.py);
   this file only shapes the UI from raw constraints and keeps the document. */
let rosterIndex = null,
  roster = null,
  rosterTimer = null,
  rosterSaving = false;
/* v1.14: rule texts on the operative cards — «expand all» is remembered; single chips flip their own text. */
const RULES_KEY = "killstass-roster-rules";
let rulesAll = localStorage.getItem(RULES_KEY) === "1";
const rulesFlipped = new Set();
const rosterSchemas = {};
const RK = {
  uid: () => {
    const b = new Uint8Array(10);
    crypto.getRandomValues(b);
    return Array.from(
      b,
      (x) => "abcdefghijklmnopqrstuvwxyz0123456789"[x % 36],
    ).join("");
  },
  lim(n) {
    const c = (n.con || []).filter(
      (x) => x.s === "parent" && x.f === "selections",
    );
    const mins = c.filter((x) => x.t === "min").map((x) => x.v),
      maxs = c.filter((x) => x.t === "max" && x.v >= 0).map((x) => x.v);
    return {
      min: mins.length ? Math.max(...mins) : 0,
      max: maxs.length ? Math.min(...maxs) : Infinity,
    };
  },
  /* Hidden without a modifier = never offered; conditionally hidden entries stay visible (server warns). */
  visible: (n) => !n.h || (n.mod || []).some((m) => m.f === "hidden"),
  entries(n) {
    const out = [];
    const walk = (ch, groups) =>
      (ch || []).forEach((x) =>
        x.t === "group"
          ? walk(x.ch, [...groups, x])
          : out.push({ node: x, groups }),
      );
    walk(n.ch, []);
    return out;
  },
  defaults(n) {
    const out = [];
    const visit = (ch) =>
      (ch || []).forEach((c) => {
        if (c.h) return;
        const { min } = RK.lim(c);
        if (c.t === "group") {
          const list = (c.ch || []).filter((x) => x.t !== "group" && !x.h);
          let left = min;
          list
            .sort(
              (a, b) =>
                (b.id === c.def || b.k.endsWith(c.def || "\u0000")) -
                (a.id === c.def || a.k.endsWith(c.def || "\u0000")),
            )
            .forEach((x) => {
              if (left <= 0) return;
              const k = Math.min(left, RK.lim(x).max);
              if (k > 0)
                out.push({
                  uid: RK.uid(),
                  key: x.k,
                  n: k,
                  sel: RK.defaults(x),
                });
              left -= k;
            });
          visit((c.ch || []).filter((x) => x.t === "group"));
        } else if (min)
          out.push({ uid: RK.uid(), key: c.k, n: min, sel: RK.defaults(c) });
      });
    visit(n.ch);
    return out;
  },
  find(list, uid, parent = null) {
    for (const s of list) {
      if (s.uid === uid) return { sel: s, list, parent };
      const hit = RK.find(s.sel || [], uid, s);
      if (hit) return hit;
    }
    return null;
  },
  clone: (s) => ({ ...s, uid: RK.uid(), sel: (s.sel || []).map(RK.clone) }),
};
const rosterNode = (key, parentNode) =>
  parentNode
    ? RK.entries(parentNode).find((e) => e.node.k === key)
    : rosterRoot().find((e) => e.node.k === key);
function rosterRoot() {
  return (roster.schema.root || []).flatMap((n) =>
    n.t === "group" ? RK.entries({ ch: [n] }) : [{ node: n, groups: [] }],
  );
}
export async function loadRosterIndex(force = false) {
  if (rosterIndex && !force) return rosterIndex;
  try {
    rosterIndex = await api("/rosters");
  } catch {
    rosterIndex = { rosters: [], teams: [], limit: 0 };
  }
  return rosterIndex;
}
async function rosterSchema(slug) {
  const hit = rosterSchemas[slug];
  if (hit) return hit;
  return (rosterSchemas[slug] = await api(
    "/teams/" + encodeURIComponent(slug) + "/roster-schema",
  ));
}
const issueText = (i) =>
  esc(t("rosterIssue_" + i.code)).replace(/\{(\w+)\}/g, (_, k) =>
    esc(i.params?.[k] ?? ""),
  );
function profileLine(pid) {
  const p = roster.schema.profiles?.[pid];
  if (!p) return "";
  if (p.t === "Weapons")
    return `<span class="wline"><b>${esc(String(p.n).replace(/^[⌖⚔]\s*/, ""))}</b> ${p.c
      .map(([n, , v]) =>
        n === "WR"
          ? !v || v === "-"
            ? ""
            : `<span class="wr">${esc(n)} <span data-terms="wr">${esc(v)}</span></span>`
          : `<span>${esc(n)} ${esc(v)}</span>`,
      )
      .join("")}</span>`;
  return "";
}
function statLine(node) {
  const p = (node.p || [])
    .map((id) => roster.schema.profiles?.[id])
    .find((x) => x?.t === "Operative");
  return p
    ? `<span class="statline">${p.c.map(([n, , v]) => `<span><small>${esc(n)}</small>${esc(v)}</span>`).join("")}</span>`
    : "";
}
function optionProfiles(node) {
  const w = (node.p || []).map(profileLine).filter(Boolean);
  return w.length ? `<span class="opt-profiles">${w.join("")}</span>` : "";
}
function optionLabel(node) {
  return `<span class="opt-name">${esc(node.n)}</span>${optionProfiles(node)}`;
}
/* v1.14: a pick/toggle row is a box with the button (name) and, beside it, the weapon profiles — outside the
   button, so the weapon rules can carry term tooltips; a tap elsewhere on the box presses the button. */
const optBox = (kind, have, btnAttrs, node) =>
  `<div class="opt ${kind} ${have ? "on" : ""}" data-opt><button type="button" class="opt-btn" ${btnAttrs} aria-pressed="${!!have}"><span class="opt-name">${esc(node.n)}</span></button>${optionProfiles(node)}</div>`;
/* One container's options: groups become radio/checkbox lists, single entries fixed/toggle/counter. */
function optionsHtml(node, sel, depth = 0) {
  if (depth > 6) return "";
  const kids = node.ch || [];
  const chosen = (k) => (sel.sel || []).filter((x) => x.key === k);
  const sub = (x) => {
    const c = chosen(x.k)[0];
    return c && (x.ch || []).length
      ? `<div class="opt-sub">${optionsHtml(x, c, depth + 1)}</div>`
      : "";
  };
  const entry = (x, group) => {
    if (!RK.visible(x) && !chosen(x.k).length) return "";
    const own = RK.lim(x),
      g = group ? RK.lim(group) : null,
      have = chosen(x.k).reduce((a, s) => a + s.n, 0),
      attrs = `data-parent="${esc(sel.uid)}" data-key="${esc(x.k)}"`;
    if (group && g.max === 1)
      return `<li>${optBox("pick", have, `data-action="roster-pick" ${attrs} data-group="${esc(group.k)}"`, x)}${sub(x)}</li>`;
    if (!group && own.min >= 1 && own.max === own.min)
      return `<li><span class="opt fixed">${icon("check")}${own.min > 1 ? own.min + "× " : ""}${optionLabel(x)}</span>${sub(x)}</li>`;
    const max = Math.min(own.max, g ? g.max : Infinity);
    if (max === 1)
      return `<li>${optBox("toggle", have, `data-action="roster-toggle" ${attrs}`, x)}${sub(x)}</li>`;
    return `<li><span class="opt count ${have ? "on" : ""}">${optionLabel(x)}<span class="stepper">${button("−", "roster-count", "mini", `${attrs} data-delta="-1" aria-label="−1 ${esc(x.n)}" ${have ? "" : "disabled"}`)}<output>${have}</output>${button("+", "roster-count", "mini", `${attrs} data-delta="1" aria-label="+1 ${esc(x.n)}" ${have >= max ? "disabled" : ""}`)}</span></span>${sub(x)}</li>`;
  };
  const group = (gr) => {
    if (!RK.visible(gr)) return "";
    const l = RK.lim(gr),
      range =
        l.max === Infinity
          ? l.min
            ? `≥${l.min}`
            : ""
          : l.min === l.max
            ? String(l.min)
            : `${l.min}–${l.max}`;
    return `<fieldset class="opt-group"><legend>${esc(gr.n)}${range ? ` <small>${range}</small>` : ""}</legend><ul>${(
      gr.ch || []
    )
      .map((x) => (x.t === "group" ? `<li>${group(x)}</li>` : entry(x, gr)))
      .join("")}</ul></fieldset>`;
  };
  const singles = kids
    .filter((x) => x.t !== "group")
    .map((x) => entry(x, null))
    .join("");
  return `${singles ? `<ul class="opt-list">${singles}</ul>` : ""}${kids
    .filter((x) => x.t === "group")
    .map(group)
    .join("")}`;
}
/* v1.14 (Т2): what the operative brings to the table as selected — the profiles of the model and of its
   selected options (each once, in selection order): abilities and other rules, unique actions; keywords from the
   datacard or the BSData categories. Without any rule profile in the schema — the datacard's rules, as in print.
   The server does the same for print, the board and the opponent's roster (api/tracker.py roster_build). */
const OWN_TYPES = ["Operative", "Weapons"];
const SERVICE_CAT =
  /^(operative|operatives|requisitioned operatives|configuration)$|^(up to )?(one|two|three|four|five|six|seven|eight|nine|ten)( of)?:?$| or /i;
const rulesCache = new WeakMap();
function hasRules(node, depth = 0) {
  if (rulesCache.has(node)) return rulesCache.get(node);
  const P = roster.schema.profiles || {},
    yes =
      (node.p || []).some((id) => P[id] && !OWN_TYPES.includes(P[id].t)) ||
      (depth < 8 && (node.ch || []).some((c) => hasRules(c, depth + 1)));
  rulesCache.set(node, yes);
  return yes;
}
const profileText = (p) =>
  p.c.length === 1
    ? String(p.c[0][2] || "").trim()
    : p.c
        .filter(([, , v]) => String(v || "").trim())
        .map(([k, , v]) => `**${k}:** ${String(v).trim()}`)
        .join("\n");
function selectedProfiles(node, sel) {
  const P = roster.schema.profiles || {},
    out = [],
    seen = new Set();
  const visit = (n, s, depth) => {
    for (const id of n.p || [])
      if (P[id] && !seen.has(id)) {
        seen.add(id);
        out.push(P[id]);
      }
    if (depth < 8)
      for (const c of s?.sel || []) {
        const hit = rosterNode(c.key, n);
        if (hit) visit(hit.node, c, depth + 1);
      }
  };
  visit(node, sel, 0);
  return out;
}
function opRules(node, sel, withCard = true) {
  const names = new Set(),
    rules = [],
    actions = [];
  for (const p of selectedProfiles(node, sel)) {
    const k = p.t + ":" + String(p.n).toLowerCase();
    if (OWN_TYPES.includes(p.t) || names.has(k)) continue;
    names.add(k);
    const item = { name: p.n, text: profileText(p) };
    if (p.t === "Unique Actions") actions.push(item);
    else rules.push({ ...item, type: p.t === "Abilities" ? "" : p.t });
  }
  const card = withCard
    ? roster.cards?.[String(node.n).toLowerCase()] || null
    : null;
  if (card && !hasRules(node)) {
    rules.push(...(card.abilities || []).map((a) => ({ ...a, type: "" })));
    actions.push(...(card.actions || []));
  }
  let keywords = [];
  if (withCard) {
    if (card?.keywords?.length) keywords = card.keywords;
    else {
      const cats = (node.cat || [])
        .map((id) => roster.schema.cats?.[id])
        .filter((n) => n && !SERVICE_CAT.test(n));
      cats.sort(
        (a, b) =>
          (a === a.toUpperCase() ? 0 : 1) - (b === b.toUpperCase() ? 0 : 1),
      );
      keywords = [...new Set(cats.map((n) => n.toUpperCase()))];
    }
  }
  return { rules, actions, keywords };
}
/* Names in one line (a unique action with its AP cost); a tap opens the text below, «expand all» opens every one. */
function rulesBlock(uid, r) {
  const items = [
    ...r.rules.map((x) => ({ ...x, kind: "rule" })),
    ...r.actions.map((x) => ({ ...x, kind: "action" })),
  ];
  if (!items.length) return "";
  const id = (i) => `rr-${uid}-${i}`,
    open = (x) => rulesAll !== rulesFlipped.has(uid + "\u0000" + x.name);
  return `<div class="rrules"><div class="rchips">${items
    .map((x, i) => {
      const [name, ap] = x.kind === "action" ? apSplit(x.name) : [x.name, ""];
      return `<button type="button" class="rchip ${x.kind}" data-action="roster-rule" data-uid="${esc(uid)}" data-rule="${esc(x.name)}" aria-expanded="${open(x)}" aria-controls="${id(i)}">${x.kind === "action" ? icon("bolt") : ""}<span>${esc(name)}</span>${ap ? `<span class="ap">${esc(ap)}</span>` : ""}${x.type ? `<small>${esc(x.type)}</small>` : ""}</button>`;
    })
    .join("")}</div>${items
    .map((x, i) => {
      const [name, ap] = x.kind === "action" ? apSplit(x.name) : [x.name, ""];
      return `<div class="rrule ${x.kind}" id="${id(i)}" ${open(x) ? "" : "hidden"}><h4>${esc(name)}${apBadge(ap)}${x.type ? ` <small class="dc-type">${esc(x.type)}</small>` : ""}</h4><div data-terms="text">${ruleText(x.text)}</div></div>`;
    })
    .join("")}</div>`;
}
function rosterIssues(uid) {
  const list = [
    ...(roster.summary?.errors || []),
    ...(roster.summary?.warnings || []),
  ].filter((i) => (i.uid || null) === uid);
  return list.length
    ? `<ul class="issues">${list.map((i) => `<li class="${i.level}">${issueText(i)}</li>`).join("")}</ul>`
    : "";
}
function operativeCard(s, i) {
  const hit = rosterNode(s.key);
  if (!hit)
    return `<article class="rcard broken" id="sel-${esc(s.uid)}"><header><b>${esc(s.name || s.key)}</b>${button("×", "roster-remove", "mini", `data-uid="${esc(s.uid)}" aria-label="${esc(t("rosterRemove"))}"`)}</header>${rosterIssues(s.uid)}</article>`;
  const n = hit.node,
    errs = (roster.summary?.errors || []).some((x) => x.uid === s.uid),
    r = opRules(n, s),
    card = roster.cards?.[String(n.n).toLowerCase()];
  return `<article class="rcard ${errs ? "invalid" : ""}" id="sel-${esc(s.uid)}"><header><span class="rnum">${i}</span><div class="rtitle"><input class="rname" data-uid="${esc(s.uid)}" value="${esc(s.name || "")}" placeholder="${esc(n.n)}" maxlength="80" aria-label="${esc(t("rosterCustomName"))}"><small>${s.name ? esc(n.n) : ""}</small></div><div class="ractions"><button type="button" class="mini" data-action="roster-dup" data-uid="${esc(s.uid)}" title="${esc(t("duplicate"))}" aria-label="${esc(t("duplicate"))}">${icon("copy")}</button>${button("×", "roster-remove", "mini", `data-uid="${esc(s.uid)}" title="${esc(t("rosterRemove"))}" aria-label="${esc(t("rosterRemove"))}"`)}</div></header>${statLine(n)}${rosterIssues(s.uid)}<div class="rbody"><div class="ropts">${optionsHtml(n, s)}</div>${rulesBlock(s.uid, r)}</div>${
    r.keywords.length || card
      ? `<footer class="rfoot"><span class="rkeywords">${esc(r.keywords.join(", "))}</span>${card ? `<a href="#teams/${esc(roster.team_slug)}/operatives/op-${card.idx}" class="small">${icon("book")}<span>${t("datacard")}</span></a>` : ""}</footer>`
      : ""
  }</article>`;
}
function rosterSummary() {
  const s = roster.summary || {},
    errors = (s.errors || []).filter((i) => !i.uid),
    warns = (s.warnings || []).filter((i) => !i.uid);
  return `<div class="rsummary ${s.valid ? "ok" : "bad"}" id="roster-summary" role="status"><div class="rstate"><b>${s.valid ? "✓ " + t("rosterValid") : "⚠ " + t("rosterInvalid")}</b><span class="muted">${t("operativesCount")}: ${s.operatives ?? 0}</span><span class="muted save-state">${rosterSaving ? t("saving") : rosterTimer ? t("unsaved") : t("saved")}</span></div>${
    (s.limits || []).length
      ? `<div class="limits">${s.limits
          .map((l) => {
            const bad =
              (l.min !== undefined && l.count < l.min) ||
              (l.max !== undefined && l.count > l.max);
            return `<span class="limit ${bad ? "bad" : l.count ? "on" : ""}">${esc(l.name)} <b>${l.count}${l.max !== undefined ? "/" + l.max : l.min !== undefined ? "/" + l.min + "+" : ""}</b></span>`;
          })
          .join("")}</div>`
      : ""
  }${errors.length || warns.length ? `<ul class="issues">${[...errors, ...warns].map((i) => `<li class="${i.level}">${issueText(i)}</li>`).join("")}</ul>` : ""}</div>`;
}
function rosterEditor() {
  const r = roster,
    root = rosterRoot().filter((e) => RK.visible(e.node)),
    models = root.filter((e) => ["model", "unit"].includes(e.node.t)),
    other = root.filter((e) => !["model", "unit"].includes(e.node.t)),
    sels = r.data.selections,
    ops = sels.filter(
      (s) =>
        ["model", "unit"].includes(rosterNode(s.key)?.node.t) ||
        !rosterNode(s.key),
    ),
    count = (k) => sels.filter((s) => s.key === k).reduce((a, s) => a + s.n, 0),
    url = (f) => `/api/rosters/${encodeURIComponent(r.id)}/export?format=${f}`;
  return `<header class="team-header roster-head"><a href="#rosters" class="back">← ${t("rosters")}</a><input id="roster-name" class="roster-title" value="${esc(r.name)}" maxlength="80" aria-label="${esc(t("rosterName"))}"><div class="row"><a class="team-link" href="#teams/${esc(r.team_slug)}">${esc(r.team_name || r.team_slug)} ${icon("book")}</a><span class="muted">${esc(r.schema.cat?.n || "")} rev ${esc(r.schema.cat?.rev || "?")}</span></div></header>${r.stale ? `<p class="warning">${t("rosterStale")}</p>` : ""}${rosterSummary()}<div class="roster-layout"><section class="panel roster-add"><h2>${t("rosterAddOperative")}</h2><ul class="add-list">${models.map((e) => `<li><button type="button" class="add-op" data-action="roster-add" data-key="${esc(e.node.k)}"><span>${esc(e.node.n)}</span>${count(e.node.k) ? `<b class="count">${count(e.node.k)}</b>` : ""}${icon("plus")}</button></li>`).join("")}</ul></section><section class="roster-team"><div class="row between roster-team-head"><h2 class="section-label">${t("rosterOperatives")} <span class="count">${ops.length}</span></h2>${ops.length ? `<button type="button" class="text small" data-action="roster-rules-all" aria-pressed="${rulesAll}">${icon(rulesAll ? "collapse" : "expand")}<span>${t(rulesAll ? "rosterRulesCollapse" : "rosterRulesExpand")}</span></button>` : ""}</div>${ops.length ? ops.map((s, i) => operativeCard(s, i + 1)).join("") : `<p class="empty">${t("rosterEmpty")}</p>`}${
    other.length
      ? `<h2 class="section-label">${t("rosterExtras")}</h2>${other
          .map((e) => {
            const s = sels.find((x) => x.key === e.node.k);
            return s
              ? `<article class="rcard extra ${(r.summary?.errors || []).some((x) => x.uid === s.uid) ? "invalid" : ""}" id="sel-${esc(s.uid)}"><header><div class="rtitle"><b>${esc(e.node.n)}</b></div><div class="ractions">${button("×", "roster-remove", "mini", `data-uid="${esc(s.uid)}" aria-label="${esc(t("rosterRemove"))}"`)}</div></header>${rosterIssues(s.uid)}<div class="rbody"><div class="ropts">${optionsHtml(e.node, s)}</div>${rulesBlock(s.uid, opRules(e.node, s, false))}</div></article>`
              : `<button type="button" class="secondary add-extra" data-action="roster-add" data-key="${esc(e.node.k)}">${icon("plus")}<span>${esc(e.node.n)}</span></button>`;
          })
          .join("")}`
      : ""
  }<label class="roster-notes">${t("notes")}<textarea id="roster-notes" maxlength="2000">${esc(r.data.notes || "")}</textarea></label></section></div><section class="panel roster-export"><h2>${t("rosterExport")}</h2><p class="muted">${t("rosterExportHint")}</p><div class="row">${button(t("rosterCopyText"), "roster-copy")}<a class="button secondary" href="${url("ros")}" download>.ros</a><a class="button secondary" href="${url("rosz")}" download>.rosz</a><a class="button secondary" href="${url("json")}" download>JSON</a>${printButton("roster-print", `data-id="${esc(r.id)}"`)}</div><p class="muted small">${t("rosterExportNote")}</p><div class="row">${button(t("duplicate"), "roster-copy-roster", "secondary")}${button(t("rosterDelete"), "roster-delete", "secondary")}</div></section>`;
}
function drawRoster() {
  const y = window.scrollY;
  shell(rosterEditor());
  window.scrollTo(0, y);
}
function redrawRosterSummary() {
  const el = document.querySelector("#roster-summary");
  if (el) el.outerHTML = rosterSummary();
}
function rosterChanged(structural = true) {
  clearTimeout(rosterTimer);
  rosterTimer = setTimeout(saveRoster, 700);
  if (structural) drawRoster();
  else redrawRosterSummary();
}
async function saveRoster() {
  if (!roster) return;
  if (rosterSaving) return void (rosterTimer = setTimeout(saveRoster, 400));
  rosterTimer = null;
  rosterSaving = true;
  redrawRosterSummary();
  const id = roster.id;
  try {
    const r = await api("/rosters/" + encodeURIComponent(id), "PUT", {
      version: roster.version,
      name: roster.name.trim() || t("rosterUntitled"),
      data: roster.data,
    });
    if (roster?.id !== id) return;
    Object.assign(roster, {
      version: r.version,
      summary: r.summary,
      stale: r.stale,
    });
    rosterIndex = null;
  } catch (e) {
    if (e.code === "version_conflict" && roster?.id === id) {
      notify(t("rosterConflict"));
      return rosterPage(id);
    }
    notify(e.message);
  } finally {
    rosterSaving = false;
  }
  if (!rosterTimer && page === "rosters") {
    const focus = document.activeElement;
    if (focus && focus.matches("input,textarea")) redrawRosterSummary();
    else drawRoster();
  }
}
async function rosterPage(id) {
  const r = await api("/rosters/" + encodeURIComponent(id));
  const [sc, team] = await Promise.all([
    rosterSchema(r.team_slug),
    teamData(r.team_slug).catch(() => null),
  ]);
  if (page !== "rosters" || location.hash.split("/")[1] !== id) return;
  const cards = {};
  (team?.data?.operatives || []).forEach((o, i) => {
    if (o.name) cards[o.name.toLowerCase()] = { ...o, idx: i };
  });
  roster = { ...r, schema: sc.schema, cards };
  drawRoster();
}
/* v1.9: import a BattleScribe / New Recruit file (.ros or .rosz). The team is recognised from the file;
   when it is not, the server answers import_team_unknown and the team picker appears. */
const IMPORT_MAX = 700 * 1024;
function importPanel(ix) {
  return `<section class="panel roster-import"><h2>${icon("upload")} ${t("rosterImport")}</h2><p class="muted">${t("rosterImportHint")}</p><form id="roster-import-form" class="grid"><label>${t("rosterImportFile")}<input type="file" name="file" accept=".ros,.rosz" required></label><div id="import-team" hidden>${select(
    "rosterTeam",
    "team_slug",
    ix.teams.map((x) => ({
      id: x.slug,
      label: x.catalog_id ? catName(x.catalog_id) : x.name,
    })),
  )}</div><div class="row"><button>${t("rosterImportGo")}</button></div></form><div id="roster-import-result" aria-live="polite"></div></section>`;
}
const fileBase64 = (file) =>
  new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1] || "");
    r.onerror = () => reject(new Error(t("rosterImportReadError")));
    r.readAsDataURL(file);
  });
async function importRoster(f) {
  const file = f.elements.file.files[0],
    out = document.querySelector("#roster-import-result"),
    teamBox = document.querySelector("#import-team");
  if (!file) return;
  if (file.size > IMPORT_MAX) return notify(t("rosterImportTooLarge"));
  try {
    const r = await api("/rosters/import", "POST", {
      request_id: uuid(),
      filename: file.name.slice(0, 200),
      data_b64: await fileBase64(file),
      ...(teamBox && !teamBox.hidden
        ? { team_slug: f.elements.team_slug.value }
        : {}),
    });
    rosterIndex = null;
    const skipped = r.skipped?.length
      ? `<p class="warning">${t("rosterImportSkipped")}: ${esc(r.skipped.join(", "))}</p>`
      : "";
    if (skipped && out) {
      out.innerHTML = `<p>${t("rosterImportDone")}: <a href="#rosters/${esc(r.id)}">${esc(r.name)}</a></p>${skipped}`;
      return;
    }
    notify(t("rosterImportDone"));
    location.hash = "rosters/" + r.id;
  } catch (err) {
    if (err.code === "import_team_unknown" && teamBox) teamBox.hidden = false;
    notify(err.message);
  }
}
async function rostersList() {
  const ix = await loadRosterIndex(true);
  if (page !== "rosters") return;
  const pre = location.hash.split("/")[2]
    ? decodeURIComponent(location.hash.split("/")[2])
    : "";
  shell(
    `${title("rosters")}<p class="muted">${t("rostersHint")}</p>${
      ix.teams.length
        ? `<section class="panel"><h2>${t("rosterNew")}</h2><form id="roster-new-form" class="grid">${select(
            "rosterTeam",
            "team_slug",
            ix.teams.map((x) => ({
              id: x.slug,
              label: x.catalog_id ? catName(x.catalog_id) : x.name,
            })),
            pre,
          )}${input("rosterName", "name", "text", "", 'required maxlength="80"')}<button>${t("rosterCreate")}</button></form></section>`
        : `<section class="panel"><h2>${t("teamsEmptyTitle")}</h2><p>${t("rostersNoData")}</p><pre class="mono">./scripts/import-teams.sh</pre></section>`
    }${ix.teams.length ? importPanel(ix) : ""}${
      ix.rosters.length
        ? `<div class="team-grid">${ix.rosters
            .map(
              (r) =>
                `<a class="team-tile roster-tile" href="#rosters/${esc(r.id)}"><strong>${esc(r.name)}</strong><span class="muted">${esc(r.catalog_id ? catName(r.catalog_id) : r.team_name || r.team_slug)}</span><span class="row"><span class="badge ${r.valid ? "active" : ""}">${r.valid ? "✓ " + t("rosterValid") : "⚠ " + t("rosterErrors") + ": " + r.errors}</span>${r.stale ? `<span class="badge">${t("rosterStaleShort")}</span>` : ""}</span><span class="muted">${t("operativesCount")}: ${r.operatives ?? 0} · ${esc(date(r.updated_at))}</span></a>`,
            )
            .join("")}</div>`
        : `<p class="empty">${t("rostersEmpty")}</p>`
    }<p class="muted">${t("rostersSource")}</p>`,
  );
}
export async function rostersRoute(parts) {
  roster = null;
  if (parts[0] && parts[0] !== "new")
    return rosterPage(decodeURIComponent(parts[0]));
  return rostersList();
}
/* Match setup: pick one of your rosters to fill team, operative count and roster text. */
/* v1.13: a roster of the index (operatives — its validated count) for the operative count of the setup. */
export const rosterInfo = (id) =>
  rosterIndex?.rosters.find((x) => x.id === id) || null;
export function rosterSelect(own, teamId) {
  const list = rosterIndex?.rosters || [];
  if (!list.length) return "";
  return `<label>${t("rosterUse")}<select name="roster_id" class="roster-pick"><option value="">${t("rosterNone")}</option>${list
    .map(
      (r) =>
        `<option value="${esc(r.id)}" ${r.id === own.roster_id ? "selected" : ""} ${teamId && r.catalog_id && r.catalog_id !== teamId ? "data-other-team" : ""}>${esc(r.name)} — ${esc(r.catalog_id ? catName(r.catalog_id) : r.team_name || r.team_slug)}${r.valid ? "" : " ⚠"}</option>`,
    )
    .join("")}</select></label>`;
}

/* Selection -> its schema node, by walking from the root (keys are only unique per parent). */
function rosterNodeOf(sel) {
  const path = [];
  let cur = RK.find(roster.data.selections, sel.uid);
  while (cur) {
    path.unshift(cur.sel);
    cur = cur.parent ? RK.find(roster.data.selections, cur.parent.uid) : null;
  }
  let node = null;
  for (const s of path) {
    const hit = node
      ? RK.entries(node).find((x) => x.node.k === s.key)
      : rosterRoot().find((x) => x.node.k === s.key);
    if (!hit) return null;
    node = hit.node;
  }
  return node;
}

/* v1.9: listeners are registered from main.js in a fixed order (the former <script> order). */
export function init() {
  document.addEventListener("change", async (e) => {
    const el = e.target;
    if (!el.matches?.("select.roster-pick") || !el.value) return;
    const f = el.form,
      r = rosterIndex?.rosters.find((x) => x.id === el.value);
    if (!r) return;
    try {
      const text = await (
        await fetch(
          `/api/rosters/${encodeURIComponent(r.id)}/export?format=text`,
          { credentials: "same-origin" },
        )
      ).text();
      if (f.elements.roster) f.elements.roster.value = text.slice(0, 4000);
      const own = currentMatch?.players.find((p) => p.user_id === me.id);
      const teamField =
        f.id === "setup-form" && own
          ? f.elements["team" + own.slot + "_id"]
          : null;
      if (
        teamField &&
        r.catalog_id &&
        [...teamField.options].some((o) => +o.value === r.catalog_id)
      ) {
        teamField.value = r.catalog_id;
        teamField.dispatchEvent(new Event("change", { bubbles: true }));
      }
      notify(t("rosterApplied"));
    } catch (err) {
      notify(err.message);
    }
  });
  app.addEventListener("click", async (e) => {
    /* A tap on an option box outside its button and term tooltips presses the button. */
    const box = e.target.closest?.(".opt[data-opt]");
    if (box && !e.target.closest("button, a, .term, input, select, textarea")) {
      box.querySelector(":scope > .opt-btn")?.click();
      return;
    }
    const b = e.target.closest("button[data-action]");
    if (!b || b.disabled || !b.dataset.action.startsWith("roster-") || !roster)
      return;
    const a = b.dataset.action,
      d = roster.data;
    if (a === "roster-rule") {
      const key = b.dataset.uid + "\u0000" + b.dataset.rule,
        panel = document.getElementById(b.getAttribute("aria-controls"));
      if (rulesFlipped.has(key)) rulesFlipped.delete(key);
      else rulesFlipped.add(key);
      const open = rulesAll !== rulesFlipped.has(key);
      b.setAttribute("aria-expanded", String(open));
      if (panel) panel.hidden = !open;
      return;
    }
    if (a === "roster-rules-all") {
      rulesAll = !rulesAll;
      rulesFlipped.clear();
      if (rulesAll) localStorage.setItem(RULES_KEY, "1");
      else localStorage.removeItem(RULES_KEY);
      drawRoster();
      document.querySelector('[data-action="roster-rules-all"]')?.focus();
      return;
    }
    if (a === "roster-add") {
      const hit = rosterNode(b.dataset.key);
      if (!hit) return;
      const s = {
        uid: RK.uid(),
        key: hit.node.k,
        n: 1,
        sel: RK.defaults(hit.node),
      };
      d.selections.push(s);
      rosterChanged();
      if (["model", "unit"].includes(hit.node.t))
        document
          .querySelector("#sel-" + s.uid)
          ?.scrollIntoView({ block: "nearest" });
    } else if (a === "roster-remove" || a === "roster-dup") {
      const hit = RK.find(d.selections, b.dataset.uid);
      if (!hit) return;
      const i = hit.list.indexOf(hit.sel);
      if (a === "roster-remove") hit.list.splice(i, 1);
      else hit.list.splice(i + 1, 0, RK.clone(hit.sel));
      rosterChanged();
    } else if (["roster-pick", "roster-toggle", "roster-count"].includes(a)) {
      const parent = RK.find(d.selections, b.dataset.parent)?.sel;
      if (!parent) return;
      parent.sel ||= [];
      const pnode = parent === null ? null : rosterNodeOf(parent),
        hit =
          pnode && RK.entries(pnode).find((x) => x.node.k === b.dataset.key);
      if (!hit) return;
      const mine = parent.sel.filter((x) => x.key === hit.node.k);
      if (a === "roster-pick") {
        const group = hit.groups.find((g) => g.k === b.dataset.group),
          keys = new Set(RK.entries({ ch: [group] }).map((x) => x.node.k)),
          min = RK.lim(group).min;
        if (mine.length && min === 0)
          parent.sel = parent.sel.filter((x) => x.key !== hit.node.k);
        else if (!mine.length)
          parent.sel = [
            ...parent.sel.filter((x) => !keys.has(x.key)),
            {
              uid: RK.uid(),
              key: hit.node.k,
              n: 1,
              sel: RK.defaults(hit.node),
            },
          ];
      } else if (a === "roster-toggle") {
        if (mine.length)
          parent.sel = parent.sel.filter((x) => x.key !== hit.node.k);
        else
          parent.sel.push({
            uid: RK.uid(),
            key: hit.node.k,
            n: 1,
            sel: RK.defaults(hit.node),
          });
      } else {
        const delta = +b.dataset.delta;
        if (mine.length) {
          mine[0].n += delta;
          if (mine[0].n <= 0)
            parent.sel = parent.sel.filter((x) => x !== mine[0]);
        } else if (delta > 0)
          parent.sel.push({
            uid: RK.uid(),
            key: hit.node.k,
            n: 1,
            sel: RK.defaults(hit.node),
          });
      }
      rosterChanged();
    } else if (a === "roster-copy") {
      try {
        const text = await (
          await fetch(
            `/api/rosters/${encodeURIComponent(roster.id)}/export?format=text`,
            { credentials: "same-origin" },
          )
        ).text();
        await copyText(text);
      } catch (err) {
        notify(err.message);
      }
    } else if (a === "roster-print") {
      if (rosterTimer) await saveRoster();
      await printRoster(b.dataset.id);
    } else if (a === "roster-copy-roster") {
      const r = await api("/rosters", "POST", {
        request_id: uuid(),
        team_slug: roster.team_slug,
        name: (roster.name + " (2)").slice(0, 80),
        data: roster.data,
      });
      rosterIndex = null;
      location.hash = "rosters/" + r.id;
    } else if (a === "roster-delete" && confirm(t("rosterDeleteConfirm"))) {
      await api("/rosters/" + encodeURIComponent(roster.id), "DELETE", {});
      roster = null;
      rosterIndex = null;
      location.hash = "rosters";
    }
  });
  app.addEventListener("input", (e) => {
    if (!roster || page !== "rosters") return;
    const el = e.target;
    if (el.id === "roster-name") roster.name = el.value;
    else if (el.id === "roster-notes") roster.data.notes = el.value;
    else if (el.classList.contains("rname")) {
      const hit = RK.find(roster.data.selections, el.dataset.uid);
      if (!hit) return;
      if (el.value.trim()) hit.sel.name = el.value.slice(0, 80);
      else delete hit.sel.name;
    } else return;
    rosterChanged(false);
  });
  app.addEventListener("submit", async (e) => {
    if (e.target.id === "roster-import-form") {
      e.preventDefault();
      e.stopImmediatePropagation();
      const b = e.target.querySelector("button");
      b.disabled = true;
      try {
        await importRoster(e.target);
      } finally {
        b.disabled = false;
      }
      return;
    }
    if (e.target.id !== "roster-new-form") return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const d = Object.fromEntries(new FormData(e.target));
    try {
      const r = await api("/rosters", "POST", {
        request_id: uuid(),
        team_slug: d.team_slug,
        name: d.name.trim() || t("rosterUntitled"),
      });
      rosterIndex = null;
      location.hash = "rosters/" + r.id;
    } catch (err) {
      notify(err.message);
    }
  });
  window.addEventListener("beforeunload", (e) => {
    if (rosterTimer) {
      saveRoster();
      e.preventDefault();
    }
  });
}
