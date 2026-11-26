import {
  api,
  app,
  button,
  catName,
  date,
  esc,
  icon,
  input,
  link,
  notify,
  t,
  uuid,
} from "./core.js";
import { page, shell, title } from "./app.js";
import {
  layoutLegend,
  layoutName,
  layoutSelect,
  layoutSvg,
} from "./killzones.js";
import { watch } from "./live.js";
/* v1.10 — «Killzone sketch» (#maps, #map/<id>): a top-down board in inches with operatives of both sides,
   objective markers, markers, terrain and arrows. Frame 0 is deployment, frame n the end of turning point n;
   replay walks through the frames. A match board is shared by the two players (live updates through the
   `board` event), a free board is private. Frames are saved whole (optimistic versions, api/boards.py).
   v1.12: ready-made terrain (web/killzones.js) is a static layer between the grid and the tokens. */
const COLORS = { 0: "#8a94a3", 1: "#c8372d", 2: "#3d6fd1" };
const TERRAIN = {
  heavy: ["#4a525c", "#8a96a3"],
  light: ["#3c5a3a", "#7fa37a"],
  vantage: ["#6b5530", "#c79a4a"],
  wall: ["#a9b4c0", "#d8e0e8"],
};
const TOOLS = [
  ["move", "pass"],
  ["op1", "user"],
  ["op2", "user"],
  ["objective", "target"],
  ["marker", "flag"],
  ["heavy", "grid"],
  ["light", "grid"],
  ["vantage", "grid"],
  ["wall", "list"],
  ["arrow", "share"],
  ["measure", "crosshair"],
  ["erase", "skull"],
];
let board = null,
  frame = 0,
  tokens = [],
  note = "",
  selected = null,
  tool = "move",
  drag = null,
  measure = null,
  dirty = false,
  saving = null,
  saveTimer = null,
  replay = null;
const clone = (v) => JSON.parse(JSON.stringify(v));
const round = (v) => Math.round(v * 10) / 10;
const newId = () => "t" + Math.random().toString(36).slice(2, 10);
const saved = (n) => board.frames.find((f) => f.frame === n);
function maxFrame() {
  const last = Math.max(0, ...board.frames.map((f) => f.frame));
  const turns = board.match ? board.match.turns : 0;
  return Math.min(12, Math.max(turns, last + (board.match ? 0 : 1)));
}
const frameName = (n) => (n ? "TP" + n : t("map_deploy"));
/* An empty frame starts as a copy of the closest earlier one. */
function load(n) {
  frame = n;
  const own = saved(n),
    prev = [...board.frames]
      .filter((f) => f.frame < n)
      .sort((a, b) => b.frame - a.frame)[0];
  tokens = clone((own || prev)?.state.tokens || []);
  note = own?.note || "";
  selected = null;
  dirty = false;
}
const tok = (id) => tokens.find((x) => x.id === id);
function short(label) {
  const s = String(label || "").trim();
  if (s.length <= 3) return s;
  const words = s.split(/\s+/);
  return words.length > 1
    ? words
        .slice(0, 2)
        .map((w) => w[0])
        .join("")
        .toUpperCase()
    : s.slice(0, 2);
}
function tokenSvg(x) {
  const sel = x.id === selected ? " selected" : "",
    c = COLORS[x.side || 0];
  if (x.kind === "terrain") {
    const [fill, stroke] = TERRAIN[x.terrain || "heavy"];
    return `<g class="tok${sel}" data-id="${esc(x.id)}" transform="translate(${x.x} ${x.y}) rotate(${x.rot || 0})"><rect x="${-(x.w || 4) / 2}" y="${-(x.h || 3) / 2}" width="${x.w || 4}" height="${x.h || 3}" rx="0.15" fill="${fill}" fill-opacity="0.85" stroke="${stroke}" stroke-width="0.08"/>${x.label ? `<text y="0.15" font-size="0.45" text-anchor="middle" fill="#fff">${esc(x.label)}</text>` : ""}</g>`;
  }
  if (x.kind === "arrow")
    return `<g class="tok${sel}" data-id="${esc(x.id)}"><line x1="${x.x}" y1="${x.y}" x2="${x.x2 ?? x.x + 2}" y2="${x.y2 ?? x.y}" stroke="${c}" stroke-width="0.14" stroke-linecap="round" marker-end="url(#ah${x.side || 0})"/><line class="hit" x1="${x.x}" y1="${x.y}" x2="${x.x2 ?? x.x + 2}" y2="${x.y2 ?? x.y}" stroke="transparent" stroke-width="0.8"/>${x.label ? `<text x="${(x.x + (x.x2 ?? x.x)) / 2}" y="${(x.y + (x.y2 ?? x.y)) / 2 - 0.3}" font-size="0.45" text-anchor="middle" fill="#fff">${esc(x.label)}</text>` : ""}</g>`;
  if (x.kind === "objective")
    return `<g class="tok${sel}" data-id="${esc(x.id)}" transform="translate(${x.x} ${x.y})"><circle r="${x.r || 0.79}" fill="#ff6a13" fill-opacity="0.18" stroke="#ff6a13" stroke-width="0.12"/><circle r="0.12" fill="#ff6a13"/>${x.label ? `<text y="-0.95" font-size="0.5" text-anchor="middle" fill="#ffb68a">${esc(x.label)}</text>` : ""}</g>`;
  if (x.kind === "marker")
    return `<g class="tok${sel}" data-id="${esc(x.id)}" transform="translate(${x.x} ${x.y})"><path d="M0 -0.4 L0.4 0 L0 0.4 L-0.4 0 Z" fill="${x.side ? c : "#ffd166"}" stroke="#111" stroke-width="0.05"/>${x.label ? `<text y="-0.55" font-size="0.4" text-anchor="middle" fill="#fff">${esc(x.label)}</text>` : ""}</g>`;
  const r = x.r || 0.5,
    ring =
      x.order === "engage"
        ? "#ffb000"
        : x.order === "conceal"
          ? "#5ec8ff"
          : "#0b0b0b";
  return `<g class="tok op${sel}${x.dead ? " dead" : ""}" data-id="${esc(x.id)}" transform="translate(${x.x} ${x.y})"><circle r="${r}" fill="${c}" fill-opacity="${x.dead ? 0.35 : 1}" stroke="${ring}" stroke-width="0.12"/><text y="0.17" font-size="0.45" font-weight="700" text-anchor="middle" fill="#fff">${esc(short(x.label))}</text>${x.dead ? `<path d="M${-r * 0.7} ${-r * 0.7} L${r * 0.7} ${r * 0.7} M${r * 0.7} ${-r * 0.7} L${-r * 0.7} ${r * 0.7}" stroke="#fff" stroke-width="0.1"/>` : ""}${x.label && x.label.length > 3 ? `<text y="${r + 0.45}" font-size="0.36" text-anchor="middle" fill="#e5e9ee">${esc(x.label.slice(0, 14))}</text>` : ""}</g>`;
}
function svgBody() {
  const W = board.width,
    H = board.height;
  let grid = "";
  for (let x = 1; x < W; x++)
    grid += `<line x1="${x}" y1="0" x2="${x}" y2="${H}" stroke="${x % 6 ? "#2a313a" : "#3c4550"}" stroke-width="${x % 6 ? 0.02 : 0.05}"/>`;
  for (let y = 1; y < H; y++)
    grid += `<line x1="0" y1="${y}" x2="${W}" y2="${y}" stroke="${y % 6 ? "#2a313a" : "#3c4550"}" stroke-width="${y % 6 ? 0.02 : 0.05}"/>`;
  const order = { terrain: 0, objective: 1, marker: 2, arrow: 3, op: 4 },
    list = [...tokens].sort((a, b) => order[a.kind] - order[b.kind]);
  const m = measure
    ? `<g class="measure"><line x1="${measure.x1}" y1="${measure.y1}" x2="${measure.x2}" y2="${measure.y2}" stroke="#fff" stroke-width="0.08" stroke-dasharray="0.3 0.2"/><text x="${(measure.x1 + measure.x2) / 2}" y="${(measure.y1 + measure.y2) / 2 - 0.35}" font-size="0.6" text-anchor="middle" fill="#fff" stroke="#000" stroke-width="0.04">${Math.hypot(measure.x2 - measure.x1, measure.y2 - measure.y1).toFixed(1)}″</text></g>`
    : "";
  return `<defs>${[0, 1, 2].map((s) => `<marker id="ah${s}" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" fill="${COLORS[s]}"/></marker>`).join("")}</defs><rect x="-0.5" y="-0.5" width="${W + 1}" height="${H + 1}" fill="#14181d"/><rect x="0" y="0" width="${W}" height="${H}" fill="#1b2026" stroke="#5b6672" stroke-width="0.08"/>${grid}${board.layout ? layoutSvg(board.layout, board.swap) : ""}<text x="0.2" y="${H - 0.2}" font-size="0.4" fill="#5b6672">${W}″ × ${H}″</text>${list.map(tokenSvg).join("")}${m}`;
}
function propsHtml() {
  const x = tok(selected);
  if (!x) return `<p class="muted">${t("map_select")}</p>`;
  const num = (k, key, v, attrs) =>
    `<label>${esc(t(k))}<input type="number" step="0.1" data-prop="${key}" value="${v ?? ""}" ${attrs}></label>`;
  const side = `<label>${t("map_side")}<select data-prop="side">${[0, 1, 2].map((s) => `<option value="${s}" ${(x.side || 0) === s ? "selected" : ""}>${t("map_side" + s)}</option>`).join("")}</select></label>`;
  let extra = "";
  if (x.kind === "op")
    extra = `${side}<label>${t("opOrder")}<select data-prop="order"><option value="">—</option>${["engage", "conceal"].map((o) => `<option value="${o}" ${x.order === o ? "selected" : ""}>${t("order_" + o)}</option>`).join("")}</select></label><label class="check"><input type="checkbox" data-prop="dead" ${x.dead ? "checked" : ""}>${t("map_dead")}</label>`;
  else if (x.kind === "terrain")
    extra = `<label>${t("map_terrain")}<select data-prop="terrain">${Object.keys(
      TERRAIN,
    )
      .map(
        (k) =>
          `<option value="${k}" ${x.terrain === k ? "selected" : ""}>${t("map_" + k)}</option>`,
      )
      .join(
        "",
      )}</select></label>${num("map_w", "w", x.w, 'min="0.1" max="60"')}${num("map_h", "h", x.h, 'min="0.1" max="60"')}${num("map_rot", "rot", x.rot || 0, 'min="-360" max="360" step="15"')}`;
  else if (x.kind === "marker" || x.kind === "arrow") extra = side;
  return `<div class="map-props-grid"><label>${t("map_label")}<input data-prop="label" maxlength="40" value="${esc(x.label || "")}"></label>${num("map_x", "x", x.x, 'min="-10" max="70"')}${num("map_y", "y", x.y, 'min="-10" max="70"')}${x.kind === "arrow" ? num("map_x2", "x2", x.x2, 'min="-10" max="70"') + num("map_y2", "y2", x.y2, 'min="-10" max="70"') : ""}${extra}</div><div class="row">${button(t("map_duplicate"), "map-dup")}${button(t("ad_delete"), "map-del", "danger")}</div>`;
}
function listHtml() {
  if (!tokens.length) return `<p class="muted">${t("map_noTokens")}</p>`;
  return `<ul class="map-tokens">${tokens.map((x) => `<li><button type="button" class="text ${x.id === selected ? "selected" : ""}" data-action="map-pick" data-id="${esc(x.id)}" aria-pressed="${x.id === selected}"><span class="dot side-${x.side || 0}"></span>${esc(t("map_kind_" + x.kind))}${x.label ? ": " + esc(x.label) : ""}${x.dead ? " ✕" : ""}</button></li>`).join("")}</ul>`;
}
function framesHtml() {
  const n = maxFrame();
  return `<div class="frames row" role="group" aria-label="${esc(t("map_frames"))}">${Array.from({ length: n + 1 }, (_, i) => button(frameName(i), "map-frame", i === frame ? "selected small" : "secondary small", `data-frame="${i}" aria-pressed="${i === frame}" ${saved(i) ? "" : 'data-empty="1"'}`)).join("")}</div>`;
}
function statusText() {
  if (saving) return t("map_saving");
  if (dirty) return t("map_unsaved");
  return saved(frame) ? t("map_saved") : t("map_copyHint");
}
function draw() {
  const m = board.match;
  shell(
    `<header class="page-title"><p>${link("← " + t("maps"), "maps", "text")}${m ? " " + link(t("map_toMatch"), "match/" + m.id, "text") : ""}</p><span class="eyebrow">KILLZONE · ${board.width}″ × ${board.height}″${m ? ` · ${esc(catName(m.killzone_id))}` : board.layout ? ` · ${esc(layoutName(board.layout))}` : ""}</span><h1>${esc(board.title || (m ? catName(m.mission_id) : t("map_untitled")))}</h1>${m ? `<p class="legend"><span class="dot side-1"></span>${esc(m.players[0]?.display_name || "1")} <span class="dot side-2"></span>${esc(m.players[1]?.display_name || "2")}</p>` : ""}</header><section class="panel map-panel"><div class="row between">${framesHtml()}<div class="row">${button(replay ? t("map_stop") : t("map_replay"), "map-replay")}${button("PNG", "map-png")}</div></div><div class="map-tools row" role="toolbar" aria-label="${esc(t("map_tools"))}">${TOOLS.map(([k, ic]) => `<button type="button" class="${tool === k ? "selected" : "secondary"} small" data-action="map-tool" data-tool="${k}" aria-pressed="${tool === k}">${icon(ic)}<span>${t("map_tool_" + k)}</span></button>`).join("")}</div><div class="map-wrap" id="map-wrap" tabindex="0" aria-label="${esc(t("map_keys"))}"><svg id="map-svg" class="map-svg tool-${tool}" viewBox="-0.5 -0.5 ${board.width + 1} ${board.height + 1}" role="img" aria-label="${esc(`${t("map_title")}: ${frameName(frame)}, ${tokens.length}`)}">${svgBody()}</svg></div><p class="muted small" id="map-status" role="status">${esc(statusText())}</p>${board.layout ? layoutLegend(board.layout) : ""}<label>${t("map_note")} · ${esc(frameName(frame))}<textarea id="map-note" maxlength="500">${esc(note)}</textarea></label><div class="row">${saved(frame) && frame ? button(t("map_deleteFrame"), "map-frame-delete") : ""}</div></section><div class="grid"><section class="panel"><h2>${t("map_props")}</h2><div id="map-props">${propsHtml()}</div></section><section class="panel"><h2>${t("map_tokens")} (${tokens.length})</h2><div id="map-list">${listHtml()}</div></section></div><section class="panel"><details><summary>${t("map_settings")}</summary><form id="map-settings" class="row">${input("map_name", "title", "text", board.title, 'maxlength="80"')}${sizeInputs(board.width, board.height, board.layout)}${layoutSelect(board.layout || "")}${swapBox(board)}<button class="secondary">${t("save")}</button></form><p class="muted small">${t("map_layoutHint")}</p><p></p>${button(t("map_deleteBoard"), "map-delete", "danger")}</details></section>`,
  );
}
function redrawBoard() {
  const svg = document.querySelector("#map-svg");
  if (svg) svg.innerHTML = svgBody();
  const props = document.querySelector("#map-props");
  if (props && !props.contains(document.activeElement))
    props.innerHTML = propsHtml();
  const list = document.querySelector("#map-list");
  if (list) list.innerHTML = listHtml();
  const st = document.querySelector("#map-status");
  if (st) st.textContent = statusText();
}
function changed() {
  dirty = true;
  redrawBoard();
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => save().catch((e) => notify(e.message)), 700);
}
async function save() {
  clearTimeout(saveTimer);
  if (!dirty || !board) return;
  if (saving) return saving.then(() => save());
  const n = frame,
    own = saved(n),
    body = {
      version: own ? own.version : null,
      state: { tokens: clone(tokens) },
      note,
    };
  dirty = false;
  saving = (async () => {
    try {
      const r = await api(`/boards/${board.id}/frames/${n}`, "PUT", body);
      board.seq = r.seq;
      if (own)
        Object.assign(own, { version: r.version, state: body.state, note });
      else
        board.frames.push({
          frame: n,
          version: r.version,
          state: body.state,
          note,
        });
    } catch (err) {
      if (err.code === "version_conflict") {
        notify(t("map_conflict"));
        await reload(true);
      } else {
        dirty = true;
        throw err;
      }
    } finally {
      saving = null;
      const st = document.querySelector("#map-status");
      if (st) st.textContent = statusText();
      document
        .querySelector(`[data-action=map-frame][data-frame="${n}"]`)
        ?.removeAttribute("data-empty");
    }
  })();
  return saving;
}
async function reload(keepFrame = true) {
  board = await api("/boards/" + board.id);
  load(keepFrame ? frame : latest());
  if (page === "map") draw();
}
const latest = () => Math.max(0, ...board.frames.map((f) => f.frame));
function point(e) {
  const svg = document.querySelector("#map-svg"),
    pt = svg.createSVGPoint();
  pt.x = e.clientX;
  pt.y = e.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());
  return { x: round(p.x), y: round(p.y) };
}
const clampX = (v) => Math.max(-0.5, Math.min(board.width + 0.5, v));
const clampY = (v) => Math.max(-0.5, Math.min(board.height + 0.5, v));
function add(kind, p) {
  const x = { id: newId(), x: clampX(p.x), y: clampY(p.y), label: "" };
  if (kind === "op1" || kind === "op2") {
    const side = kind === "op1" ? 1 : 2,
      n = tokens.filter((o) => o.kind === "op" && o.side === side).length + 1;
    Object.assign(x, { kind: "op", side, r: 0.5, label: String(n) });
  } else if (kind === "objective")
    Object.assign(x, {
      kind: "objective",
      r: 0.79,
      label: String(tokens.filter((o) => o.kind === "objective").length + 1),
    });
  else if (kind === "marker") Object.assign(x, { kind: "marker", side: 0 });
  else if (kind === "wall")
    Object.assign(x, {
      kind: "terrain",
      terrain: "wall",
      w: 4,
      h: 0.3,
      rot: 0,
    });
  else Object.assign(x, { kind: "terrain", terrain: kind, w: 4, h: 3, rot: 0 });
  tokens.push(x);
  selected = x.id;
  return x;
}
export function mapButton(m) {
  if (m.demo || m.status === "setup" || m.kind === "guest") return "";
  return button(
    t("map_title"),
    "map-open",
    "secondary",
    `data-match="${esc(m.id)}"`,
  );
}
/* Width and depth follow the terrain preset when one is chosen (the server fixes 30″ × 22″). */
const sizeInputs = (w, h, layout) =>
  input(
    "map_w",
    "width",
    "number",
    w,
    `min="6" max="60" step="0.5" required${layout ? " disabled" : ""}`,
  ) +
  input(
    "map_h",
    "height",
    "number",
    h,
    `min="6" max="60" step="0.5" required${layout ? " disabled" : ""}`,
  );
const swapBox = (b) =>
  `<label class="check" ${b.layout ? "" : "hidden"}><input type="checkbox" name="swap" ${b.swap ? "checked" : ""}>${esc(t("map_swap"))}</label>`;
async function listPage() {
  const list = await api("/boards");
  if (page !== "maps") return;
  shell(
    `${title("maps")}<p class="muted">${t("map_lead")}</p><section class="panel"><h2>${t("map_new")}</h2><form id="map-new" class="row">${input("map_name", "title", "text", "", 'maxlength="80"')}${sizeInputs(30, 22)}${layoutSelect("")}<button>${t("map_create")}</button></form><p class="muted small">${t("map_newHint")}</p></section><section class="panel"><h2>${t("maps")}</h2>${
      list.length
        ? list
            .map(
              (b) =>
                `<article class="list-item"><div><span class="eyebrow">${esc(date(b.updated_at))} · ${b.frames} ${t("map_framesShort")}${b.layout ? ` · ${esc(layoutName(b.layout))}` : ""}</span><h3>${esc(b.title || (b.match_id ? catName(b.mission_id) : t("map_untitled")))}</h3>${b.players ? `<span class="muted">${esc(b.players)}</span>` : `<span class="muted">${t("map_private")}</span>`}</div>${link(t("open"), "map/" + b.id)}</article>`,
            )
            .join("")
        : `<p class="empty">${t("map_empty")}</p>`
    }</section>`,
  );
}
export async function mapsRoute(kind, parts) {
  stopReplay();
  if (kind === "maps") return listPage();
  board = await api("/boards/" + parts[0]);
  if (page !== "map") return;
  tool = "move";
  measure = null;
  load(latest());
  draw();
  watch(
    { board: board.id },
    {
      board: (seq) => {
        if (
          page === "map" &&
          board &&
          seq !== board.seq &&
          !dirty &&
          !drag &&
          !saving
        )
          reload(true).catch(() => {});
      },
    },
  );
}
function stopReplay() {
  clearInterval(replay);
  replay = null;
}
async function exportPng() {
  const svg = document.querySelector("#map-svg").cloneNode(true),
    scale = 40;
  svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  svg.setAttribute("width", (board.width + 1) * scale);
  svg.setAttribute("height", (board.height + 1) * scale);
  svg.querySelectorAll(".hit").forEach((n) => n.remove());
  const img = new Image();
  img.src =
    "data:image/svg+xml;charset=utf-8," +
    encodeURIComponent(new XMLSerializer().serializeToString(svg));
  await img.decode();
  const canvas = document.createElement("canvas");
  canvas.width = (board.width + 1) * scale;
  canvas.height = (board.height + 1) * scale;
  const g = canvas.getContext("2d");
  g.drawImage(img, 0, 0);
  g.font = `${scale * 0.5}px sans-serif`;
  g.fillStyle = "#c9d1d9";
  g.fillText(
    `KILLSTASS · ${board.title || ""} · ${frameName(frame)}`,
    scale * 0.6,
    scale * 0.45,
  );
  const a = document.createElement("a");
  a.href = canvas.toDataURL("image/png");
  a.download = `killstass-${(board.title || "board").replace(/[^\w-]+/g, "_")}-${frame}.png`;
  document.body.append(a);
  a.click();
  a.remove();
}
export function init() {
  app.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b || b.disabled || !b.dataset.action.startsWith("map-")) return;
    const a = b.dataset.action;
    try {
      if (a === "map-open") {
        b.disabled = true;
        const r = await api("/boards", "POST", {
          request_id: uuid(),
          match_id: b.dataset.match,
        });
        location.hash = "map/" + r.id;
        return;
      }
      if (page !== "map" || !board) return;
      if (a === "map-tool") {
        tool = b.dataset.tool;
        measure = null;
        document.querySelectorAll("[data-action=map-tool]").forEach((x) => {
          const on = x.dataset.tool === tool;
          x.className = (on ? "selected" : "secondary") + " small";
          x.setAttribute("aria-pressed", on);
        });
        document
          .querySelector("#map-svg")
          .setAttribute("class", "map-svg tool-" + tool);
        redrawBoard();
      } else if (a === "map-frame") {
        stopReplay();
        await save();
        load(+b.dataset.frame);
        draw();
      } else if (a === "map-pick") {
        selected = b.dataset.id;
        redrawBoard();
        document.querySelector("#map-props input")?.focus();
      } else if (a === "map-del") {
        tokens = tokens.filter((x) => x.id !== selected);
        selected = null;
        changed();
      } else if (a === "map-dup") {
        const x = tok(selected);
        if (!x) return;
        const copy = {
          ...clone(x),
          id: newId(),
          x: clampX(x.x + 1),
          y: clampY(x.y + 1),
        };
        if (copy.x2 != null)
          Object.assign(copy, { x2: x.x2 + 1, y2: x.y2 + 1 });
        tokens.push(copy);
        selected = copy.id;
        changed();
      } else if (a === "map-replay") {
        if (replay) {
          stopReplay();
          draw();
          return;
        }
        await save();
        const list = [...board.frames]
          .map((f) => f.frame)
          .sort((x, y) => x - y);
        if (!list.length) return;
        let i = 0;
        load(list[0]);
        replay = setInterval(() => {
          if (page !== "map") return stopReplay();
          i += 1;
          if (i >= list.length) {
            stopReplay();
            draw();
            return;
          }
          load(list[i]);
          draw();
        }, 1500);
        draw();
      } else if (a === "map-png") await exportPng();
      else if (a === "map-frame-delete") {
        if (!confirm(t("map_deleteFrameConfirm"))) return;
        const r = await api(
          `/boards/${board.id}/frames/${frame}`,
          "DELETE",
          {},
        );
        board.seq = r.seq;
        board.frames = board.frames.filter((f) => f.frame !== frame);
        load(frame);
        draw();
      } else if (a === "map-delete") {
        if (!confirm(t("map_deleteBoardConfirm"))) return;
        await api("/boards/" + board.id, "DELETE", {});
        board = null;
        location.hash = "maps";
      }
    } catch (err) {
      notify(err.message);
    } finally {
      b.disabled = false;
    }
  });
  app.addEventListener("pointerdown", (e) => {
    const svg = e.target.closest?.("#map-svg");
    if (!svg || !board || replay) return;
    e.preventDefault();
    const p = point(e),
      hit = e.target.closest(".tok")?.dataset.id;
    if (tool === "measure") {
      measure = { x1: p.x, y1: p.y, x2: p.x, y2: p.y };
      drag = { measure: true };
    } else if (tool === "erase") {
      if (hit) {
        tokens = tokens.filter((x) => x.id !== hit);
        if (selected === hit) selected = null;
        changed();
      }
      return;
    } else if (tool === "arrow") {
      const x = {
        id: newId(),
        kind: "arrow",
        side: tok(selected)?.side || 0,
        x: p.x,
        y: p.y,
        x2: p.x,
        y2: p.y,
        label: "",
      };
      tokens.push(x);
      selected = x.id;
      drag = { arrow: x.id };
    } else if (tool === "move") {
      if (!hit) {
        selected = null;
        redrawBoard();
        return;
      }
      const x = tok(hit);
      selected = hit;
      drag = { id: hit, dx: p.x - x.x, dy: p.y - x.y, moved: false };
    } else {
      add(tool, p);
      changed();
      return;
    }
    svg.setPointerCapture?.(e.pointerId);
    redrawBoard();
  });
  app.addEventListener("pointermove", (e) => {
    if (!drag || !board) return;
    const p = point(e);
    if (drag.measure) Object.assign(measure, { x2: p.x, y2: p.y });
    else if (drag.arrow)
      Object.assign(tok(drag.arrow), { x2: clampX(p.x), y2: clampY(p.y) });
    else {
      const x = tok(drag.id);
      if (!x) return;
      const nx = clampX(round(p.x - drag.dx)),
        ny = clampY(round(p.y - drag.dy));
      if (x.kind === "arrow") {
        const ddx = nx - x.x,
          ddy = ny - x.y;
        x.x2 = clampX(round(x.x2 + ddx));
        x.y2 = clampY(round(x.y2 + ddy));
      }
      x.x = nx;
      x.y = ny;
      drag.moved = true;
    }
    const svg = document.querySelector("#map-svg");
    if (svg) svg.innerHTML = svgBody();
  });
  const end = () => {
    if (!drag) return;
    const d = drag;
    drag = null;
    if (d.arrow) {
      const x = tok(d.arrow);
      if (x && Math.hypot(x.x2 - x.x, x.y2 - x.y) < 0.3)
        tokens = tokens.filter((o) => o !== x);
      changed();
    } else if (d.moved) changed();
    else redrawBoard();
  };
  app.addEventListener("pointerup", end);
  app.addEventListener("pointercancel", end);
  app.addEventListener("keydown", (e) => {
    if (page !== "map" || !board || e.target.id !== "map-wrap") return;
    const x = tok(selected);
    const step = e.shiftKey ? 0.1 : 0.5,
      moves = {
        ArrowLeft: [-step, 0],
        ArrowRight: [step, 0],
        ArrowUp: [0, -step],
        ArrowDown: [0, step],
      };
    if (e.key === "Escape") {
      selected = null;
      tool = "move";
      measure = null;
      redrawBoard();
    } else if (x && moves[e.key]) {
      e.preventDefault();
      const [dx, dy] = moves[e.key];
      x.x = clampX(round(x.x + dx));
      x.y = clampY(round(x.y + dy));
      if (x.x2 != null) {
        x.x2 = clampX(round(x.x2 + dx));
        x.y2 = clampY(round(x.y2 + dy));
      }
      changed();
    } else if (x && (e.key === "Delete" || e.key === "Backspace")) {
      e.preventDefault();
      tokens = tokens.filter((o) => o !== x);
      selected = null;
      changed();
    }
  });
  app.addEventListener("change", (e) => {
    const f = e.target.closest("#map-new, #map-settings");
    if (!f || !e.target.matches("[data-layout]")) return;
    const on = !!e.target.value;
    f.querySelectorAll('input[name="width"], input[name="height"]').forEach(
      (i) => (i.disabled = on),
    );
    const swap = f.querySelector('input[name="swap"]')?.closest("label");
    if (swap) swap.hidden = !on;
  });
  app.addEventListener("input", (e) => {
    if (page !== "map" || !board) return;
    if (e.target.id === "map-note") {
      note = e.target.value;
      dirty = true;
      clearTimeout(saveTimer);
      saveTimer = setTimeout(
        () => save().catch((err) => notify(err.message)),
        900,
      );
      return;
    }
    const prop = e.target.dataset?.prop,
      x = tok(selected);
    if (!prop || !x) return;
    let v = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    if (["x", "y", "x2", "y2", "w", "h", "rot", "side"].includes(prop)) {
      if (v === "" || Number.isNaN(+v)) return;
      v = +v;
    }
    if (prop === "order" && !v) delete x.order;
    else x[prop] = v;
    changed();
  });
  app.addEventListener("submit", async (e) => {
    const f = e.target;
    if (f.id !== "map-new" && f.id !== "map-settings") return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const d = Object.fromEntries(new FormData(f));
    try {
      // disabled size inputs are not in the form data: the preset decides
      const size = d.layout ? {} : { width: +d.width, height: +d.height };
      if (f.id === "map-new") {
        const r = await api("/boards", "POST", {
          request_id: uuid(),
          title: d.title || "",
          ...size,
          layout: d.layout || "",
        });
        location.hash = "map/" + r.id;
      } else {
        await save();
        const r = await api("/boards/" + board.id, "PATCH", {
          title: d.title || "",
          ...size,
          layout: d.layout || "",
          swap: !!d.swap,
        });
        board = r;
        load(frame);
        draw();
        notify(t("saved"));
      }
    } catch (err) {
      notify(err.message);
    }
  });
  window.addEventListener("beforeunload", () => {
    if (dirty) save();
  });
}
