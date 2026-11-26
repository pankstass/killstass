import { app, esc, t } from "./core.js";
import { rosterInfo } from "./rosters.js";
import { teamOf, teamTitle } from "./teams.js";
/* v1.13 — the operative count of the match setup. It comes from the attached roster, else from the team's
   composition (team_size of GET /api/teams); typing it in is the last resort («Change»). The server decides
   the same way (api/teams.py operative_count), so this only shows what it will store. The block follows the
   roster and team pickers of its form; data-manual keeps the player's choice to type the number in. */
export function autoCount(rosterId, teamId) {
  const r = rosterId ? rosterInfo(rosterId) : null;
  if (r?.operatives > 0 && r.operatives <= 40)
    return { n: r.operatives, source: "roster", name: r.name };
  const team = teamId ? teamOf(+teamId) : null;
  if (team?.team_size)
    return {
      n: team.team_size,
      source: "team",
      name: teamTitle(team),
      varies: !!team.team_size_varies,
    };
  return null;
}
function inner(auto, manual, value) {
  if (auto && !manual)
    return `<input type="hidden" name="operative_manual" value="0"><input type="hidden" name="operative_count" value="${auto.n}"><span class="op-count-label">${t("operativeCount")}</span><p class="op-count-auto"><b>${auto.n}</b> <span class="muted">${esc(t(auto.source === "roster" ? "opCountRoster" : "opCountTeam").replace("{name}", auto.name))}</span> <button type="button" class="text" data-action="op-count-edit">${t("opCountEdit")}</button></p>${auto.varies ? `<p class="muted small">${t("opCountVaries")}</p>` : ""}`;
  return `<input type="hidden" name="operative_manual" value="${auto ? 1 : 0}"><label>${t("operativeCount")}<input type="number" name="operative_count" min="1" max="40" inputmode="numeric" value="${esc(value ?? "")}"></label>${
    auto
      ? `<p class="op-count-auto"><button type="button" class="text" data-action="op-count-auto">${esc(t(auto.source === "roster" ? "opCountUseRoster" : "opCountUseTeam").replace("{n}", auto.n))}</button></p>`
      : `<p class="muted small">${t("opCountNone")}</p>`
  }`;
}
/* p: the match player (roster_id, operative_count, operative_source); team: the name of the form's team
   field (setup) or a fixed catalog team id (the hot-seat guest form). */
export function opCountField(p, team) {
  const field = typeof team === "string" ? team : "",
    teamId = field ? p.team_id : team,
    manual = p.operative_source === "manual";
  return `<div class="op-count" data-op-count data-manual="${manual ? 1 : 0}" ${field ? `data-team-field="${esc(field)}"` : `data-team-id="${esc(teamId ?? "")}"`}>${inner(autoCount(p.roster_id, teamId), manual, p.operative_count)}</div>`;
}
function refresh(box, focus = "") {
  const f = box.closest("form"),
    teamId = box.dataset.teamField
      ? f?.elements[box.dataset.teamField]?.value
      : box.dataset.teamId,
    auto = autoCount(f?.elements.roster_id?.value || null, teamId || null),
    typed = box.querySelector('input[name="operative_count"]')?.value;
  box.innerHTML = inner(auto, box.dataset.manual === "1", typed || auto?.n);
  if (focus) box.querySelector(focus)?.focus();
}
export function init() {
  document.addEventListener("change", (e) => {
    const box = e.target.form?.querySelector("[data-op-count]");
    if (
      box &&
      (e.target.name === "roster_id" || e.target.name === box.dataset.teamField)
    )
      refresh(box);
  });
  app.addEventListener("click", (e) => {
    const b = e.target.closest(
      '[data-action="op-count-edit"], [data-action="op-count-auto"]',
    );
    const box = b?.closest("[data-op-count]");
    if (!box) return;
    const edit = b.dataset.action === "op-count-edit";
    box.dataset.manual = edit ? "1" : "0";
    refresh(
      box,
      edit ? 'input[name="operative_count"]' : '[data-action="op-count-edit"]',
    );
  });
}
