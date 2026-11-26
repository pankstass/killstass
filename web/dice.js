import { button, esc, t } from "./core.js";
import { currentMatch } from "./app.js";
import { demoState } from "./demo.js";
import { ordered } from "./turns.js";
/* v1.5 — dice roller. Local only: crypto RNG with rejection sampling (no modulo bias), nothing is sent to the server. */
export const dice = { values: [], selected: new Set(), target: 4, open: false };
let rollOffs = {};
export const resetRollOffs = () => (rollOffs = {});
function d6() {
  const b = new Uint8Array(1);
  do crypto.getRandomValues(b);
  while (b[0] >= 252); // 252 = 6 * 42: uniform 0..251
  return (b[0] % 6) + 1;
}
/* Roll-off: 1d6 each, ties re-rolled. The winner decides who takes the initiative. */
function rollOff() {
  const rounds = [];
  let r;
  do rounds.push((r = [d6(), d6()]));
  while (r[0] === r[1] && rounds.length < 20);
  return { rounds, winner: r[0] > r[1] ? 1 : 2 };
}
function rollOffText(res, names) {
  return `${res.rounds.map((r) => `${esc(names[0])} ${r[0]} : ${r[1]} ${esc(names[1])}`).join(" → ")} — <b>${esc(names[res.winner - 1])}</b> ${t("rollOffWins")}`;
}
export function rollOffButton(key) {
  return `${button(t("rollOff"), "roll-off", "secondary", `data-key="${esc(key)}"`)}${rollOffs[key] ? `<p class="rolloff" role="status">${rollOffs[key]}</p>` : ""}`;
}
export function diceBody() {
  const v = dice.values,
    hits = v.filter((x) => x >= dice.target).length,
    crits = v.filter((x) => x === 6).length;
  return `<div class="row dice-presets">${[1, 2, 3, 4, 5, 6].map((n) => button(n + "d6", "dice-roll", "secondary", `data-n="${n}"`)).join("")}</div><div class="row dice-custom"><label>${t("diceCount")}<input id="dice-n" type="number" min="1" max="20" value="${Math.max(v.length, 1)}"></label>${button(t("diceRoll"), "dice-roll", "", 'data-n="custom"')}<label>${t("diceTarget")}<select id="dice-target">${[2, 3, 4, 5, 6].map((n) => `<option value="${n}" ${n === dice.target ? "selected" : ""}>${n}+</option>`).join("")}</select></label></div>${
    v.length
      ? `<div class="dice-row" role="list" aria-label="${t("diceResult")}">${v.map((x, i) => `<button type="button" role="listitem" class="die ${x === 6 ? "crit" : x === 1 ? "fail" : x >= dice.target ? "hit" : "miss"} ${dice.selected.has(i) ? "picked" : ""}" data-action="die-toggle" data-i="${i}" aria-pressed="${dice.selected.has(i)}" aria-label="${x}">${x}</button>`).join("")}</div><p class="dice-sum" role="status">${t("diceSum")}: <b>${v.reduce((a, b) => a + b, 0)}</b> · ${t("diceHits")} (${dice.target}+): <b>${hits}</b> · ${t("diceCrits")}: <b>${crits}</b></p><div class="row">${button(t("diceRerollPicked"), "dice-reroll", "secondary", dice.selected.size ? "" : "disabled")}${button(t("diceRerollMiss"), "dice-reroll-miss", "secondary", hits < v.length ? "" : "disabled")}</div><p class="muted">${t("diceHint")}</p>`
      : `<p class="muted">${t("diceHint")}</p>`
  }`;
}
export function dicePanel() {
  return `<section class="panel dice" id="dice-panel"><details ${dice.open ? "open" : ""}><summary>${t("dice")}</summary><div id="dice-body">${diceBody()}</div></details></section>`;
}
function redrawDice() {
  const el = document.querySelector("#dice-body");
  if (el) el.innerHTML = diceBody();
}

/* v1.9: listeners are registered from main.js in a fixed order (the former <script> order). */
export function init() {
  document.addEventListener(
    "toggle",
    (e) => {
      if (e.target.closest?.("#dice-panel")) dice.open = e.target.open;
    },
    true,
  );
  document.addEventListener("change", (e) => {
    if (e.target.id === "dice-target") {
      dice.target = +e.target.value;
      redrawDice();
    }
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b || b.disabled) return;
    const a = b.dataset.action;
    if (a === "dice-roll") {
      const n =
        b.dataset.n === "custom"
          ? Math.min(
              20,
              Math.max(1, +document.querySelector("#dice-n").value || 1),
            )
          : +b.dataset.n;
      dice.values = Array.from({ length: n }, d6);
      dice.selected.clear();
    } else if (a === "die-toggle") {
      const i = +b.dataset.i;
      dice.selected.has(i) ? dice.selected.delete(i) : dice.selected.add(i);
    } else if (a === "dice-reroll") {
      dice.values = dice.values.map((x, i) =>
        dice.selected.has(i) ? d6() : x,
      );
      dice.selected.clear();
    } else if (a === "dice-reroll-miss") {
      dice.values = dice.values.map((x) => (x < dice.target ? d6() : x));
      dice.selected.clear();
    } else if (a === "roll-off") {
      const names = b.dataset.key.startsWith("demo")
        ? demoState().players.map((p) => p.name)
        : ordered(currentMatch).map((p) => p.display_name);
      const slots = b.dataset.key.startsWith("demo")
        ? [1, 2]
        : ordered(currentMatch).map((p) => p.slot);
      const res = rollOff();
      rollOffs[b.dataset.key] =
        rollOffText(res, names) +
        `<span hidden data-winner="${slots[res.winner - 1]}"></span>`;
      const p = b.parentElement.querySelector(".rolloff");
      if (p) p.innerHTML = rollOffs[b.dataset.key];
      else
        b.insertAdjacentHTML(
          "afterend",
          `<p class="rolloff" role="status">${rollOffs[b.dataset.key]}</p>`,
        );
      return;
    } else return;
    redrawDice();
  });
}
