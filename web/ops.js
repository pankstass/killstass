import { cat, catalogs, esc, input, me, select, t } from "./core.js";
import { currentMatch } from "./app.js";
export function catalogDetail(id) {
  const row = catalogs.find((c) => c.id === +id);
  if (!row?.config.summary) return "";
  return `<details><summary>${t("missionRules")}: ${esc(row.label)}</summary><p>${esc(row.config.summary)}</p><p class="muted">${t("turnCaps")}: ${esc((row.config.per_turn_caps || []).join(" / "))} · ${t("battleCap")}: ${row.config.max_per_battle || "—"}</p><p class="muted">${t("capHint")}</p><a href="${esc(row.source_url)}" target="_blank" rel="noopener noreferrer">${t("source")}</a></details>`;
}
function showMissionInfo() {
  const target = document.querySelector("#mission-info");
  if (target)
    target.innerHTML = catalogDetail(
      document.querySelector("#setup-form [name=mission_id]")?.value,
    );
}
/* Approved Ops controls; values come from DB catalogs, not hard-coded rules. */
export function primaryOptions() {
  return ["crit", "tac", "kill"].map((id) => ({ id, label: t("op_" + id) }));
}
export function allowedTacOps(m, teamId, counts = {}) {
  const team = catalogs.find((c) => c.id === +teamId);
  let arcs = team?.config.archetypes || [];
  const conditional = team?.config.conditional_archetypes;
  if (conditional) {
    const max = Math.max(0, ...Object.values(counts).map(Number));
    arcs = [
      "Seek & Destroy",
      ...Object.entries(conditional)
        .filter(([k]) => max > 0 && +counts[k] === max)
        .map(([, v]) => v),
    ];
  }
  return cat("tac_op", m.edition).filter((c) =>
    arcs.includes(c.config.archetype),
  );
}
const tacGroups = [
  ["Seek & Destroy", "seek"],
  ["Recon", "recon"],
  ["Security", "security"],
  ["Infiltration", "infiltration"],
];
export function tacSelect(items, selected) {
  const groups = [...tacGroups, ["Other", "other"]];
  const first =
    items.find((x) => String(x.id) === String(selected)) ||
    groups.flatMap(([name]) =>
      items.filter((x) =>
        name === "Other"
          ? !tacGroups.some(([n]) => n === x.config.archetype)
          : x.config.archetype === name,
      ),
    )[0];
  const cls =
    tacGroups.find(([name]) => name === first?.config.archetype)?.[1] ||
    "other";
  return `<label class="tac-select tac-${cls}">${t("tacOp")}<select name="tac_op_id">${groups
    .map(([name, color]) => {
      const rows = items
        .filter((x) =>
          name === "Other"
            ? !tacGroups.some(([n]) => n === x.config.archetype)
            : x.config.archetype === name,
        )
        .sort((a, b) => a.label.localeCompare(b.label));
      return rows.length
        ? `<optgroup label="${esc(name)}">${rows.map((x) => `<option value="${x.id}" data-color="${color}" ${String(x.id) === String(first?.id) ? "selected" : ""}>${esc(x.label)}</option>`).join("")}</optgroup>`
        : "";
    })
    .join(
      "",
    )}</select><span class="tac-indicator">${esc(first?.config.archetype || "")}</span></label>`;
}
export function opsSetup(m) {
  const own = m.players.find((p) => p.user_id === me.id);
  const counts = own.aspect_counts || {};
  return `<div id="ops-fields"><p class="warning">${t("approvedSetupHint")}</p>${select("primaryOp", "primary_op", primaryOptions(), own.primary_op || "crit")}<p class="muted">${t("primaryTiming")}</p><div id="aspect-fields"><div class="grid">${["dire_avenger", "howling_banshee", "striking_scorpion"].map((k) => input(k, "aspect_" + k, "number", counts[k] || 0, 'min="0" max="14"')).join("")}</div><p class="muted">${t("aspectHint")}</p></div><div id="tac-choice">${tacSelect(allowedTacOps(m, own.team_id, counts), own.tac_op_id)}</div><div id="tac-info" class="muted"></div></div>`;
}
export function refreshTacChoice() {
  const form = document.querySelector("#setup-form");
  if (!form || !currentMatch) return;
  const own = currentMatch.players.find((p) => p.user_id === me.id);
  const teamId = form.elements["team" + own.slot + "_id"]?.value;
  const counts = Object.fromEntries(
    ["dire_avenger", "howling_banshee", "striking_scorpion"].map((k) => [
      k,
      +form.elements["aspect_" + k]?.value || 0,
    ]),
  );
  const old = form.elements.tac_op_id?.value;
  document.querySelector("#tac-choice").innerHTML = tacSelect(
    allowedTacOps(currentMatch, teamId, counts),
    +old,
  );
  const conditional = catalogs.find((c) => c.id === +teamId)?.config
    .conditional_archetypes;
  document.querySelector("#aspect-fields").hidden = !conditional;
  showTacInfo();
  showMissionInfo();
}

function showTacInfo() {
  const selected = +document.querySelector("#setup-form [name=tac_op_id]")
    ?.value;
  const card = catalogs.find((c) => c.id === selected);
  const target = document.querySelector("#tac-info");
  if (target)
    target.innerHTML = card
      ? `<p><b>${t("revealTiming")}:</b> ${esc(card.config.reveal)}</p><p>${esc(card.config.summary)}</p>`
      : t("tacNotAvailable");
}
export function matchSources(m) {
  if (m.scoring_mode === "approved2025")
    return catalogs.filter((s) =>
      Object.hasOwn(m.rules_snapshot.sources || {}, String(s.id)),
    );
  return catalogs.filter(
    (s) =>
      s.kind === "source" &&
      s.edition === m.edition &&
      s.verification === "legacy",
  );
}

/* v1.9: listeners are registered from main.js in a fixed order (the former <script> order). */
export function init() {
  document.addEventListener("change", (e) => {
    if (
      e.target.closest("#setup-form") &&
      (/^team[12]_id$/.test(e.target.name) ||
        e.target.name.startsWith("aspect_"))
    )
      refreshTacChoice();
    if (e.target.name === "tac_op_id") {
      const label = e.target.closest(".tac-select"),
        option = e.target.selectedOptions[0];
      if (label && option) {
        label.className = "tac-select tac-" + option.dataset.color;
        label.querySelector(".tac-indicator").textContent =
          option.parentElement.label;
      }
      if (e.target.closest("#setup-form")) showTacInfo();
    }
    if (e.target.closest("#setup-form") && e.target.name === "mission_id")
      showMissionInfo();
  });
}
