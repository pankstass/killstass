import { api, esc, t } from "./core.js";
/* v1.13 — local players: people without an account whom the club records matches against (hot-seat matches
   and quick records). The opponent field suggests their names and the «Local player» box links the match to
   the club's shared list (api/localplayers.py), so it counts in the club rating. Typing a known name ticks the
   box; once the player changes the box by hand it stays as chosen (a one-off guest keeps it empty). */
let names = [];
const fold = (s) =>
  String(s || "")
    .toLowerCase()
    .replaceAll("ё", "е")
    .replace(/\s+/g, " ")
    .trim();
export const LOCAL_LIST = 'list="local-players" autocomplete="off"';
export function localField() {
  return `<datalist id="local-players"></datalist><label class="check"><input type="checkbox" name="local" value="1">${esc(t("localPlayer"))}</label><p class="muted small">${esc(t("localPlayerHint"))}</p>`;
}
export async function fillLocalPlayers() {
  try {
    names = (await api("/local-players")).items.map((x) => x.name);
  } catch {
    return;
  }
  const list = document.getElementById("local-players");
  if (list)
    list.innerHTML = names
      .map((n) => `<option value="${esc(n)}"></option>`)
      .join("");
}
export function init() {
  document.addEventListener("input", (e) => {
    const f = e.target;
    if (
      !(f instanceof HTMLInputElement) ||
      f.getAttribute("list") !== "local-players"
    )
      return;
    const box = f.form?.querySelector('input[name="local"]');
    if (box && !box.dataset.touched)
      box.checked = names.some((n) => fold(n) === fold(f.value));
  });
  document.addEventListener("change", (e) => {
    const box = e.target;
    if (box instanceof HTMLInputElement && box.name === "local")
      box.dataset.touched = "1";
  });
}
