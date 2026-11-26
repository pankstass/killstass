import {
  api,
  app,
  button,
  date,
  esc,
  icon,
  input,
  link,
  me,
  notify,
  t,
  uuid,
} from "./core.js";
import { page, shell, title } from "./app.js";
/* v1.9 — LAN tournaments: a league (round robin) or Swiss rounds among friends and guests. The organizer
   starts rounds; results come from each pairing's match or are entered by hand (api/tournaments.py). */
let current = null;
const fmt = (f) => t(f === "swiss" ? "tFormatSwiss" : "tFormatLeague");
const statusLabel = (s) => t("tStatus_" + s);
async function listPage() {
  const [rows, friends] = await Promise.all([
    api("/tournaments"),
    api("/friends").catch(() => ({ relations: [] })),
  ]);
  if (page !== "tournaments") return;
  const accepted = friends.relations.filter((r) => r.status === "accepted");
  shell(
    `${title("tournaments", "LAN LEAGUE")}<p class="muted">${t("tHint")}</p><section class="panel"><h2>${t("tCreate")}</h2><form id="tournament-form" class="stack">${input("tName", "name", "text", "", 'required maxlength="80"')}<fieldset class="row"><legend>${t("tFormat")}</legend><label class="check"><input type="radio" name="format" value="swiss" checked>${t("tFormatSwiss")}</label><label class="check"><input type="radio" name="format" value="league">${t("tFormatLeague")}</label></fieldset>${input("tRounds", "rounds", "number", "", 'min="1" max="30" inputmode="numeric"')}<p class="muted small">${t("tRoundsHint")}</p><fieldset><legend>${t("tPlayers")}</legend><label class="check"><input type="checkbox" name="me" checked>${esc(me.display_name)} <span class="muted">(${t("you")})</span></label>${accepted.map((r) => `<label class="check"><input type="checkbox" name="friend" value="${esc(r.public_id)}">${esc(r.display_name)} <span class="mono muted">${esc(r.public_id)}</span></label>`).join("")}${accepted.length ? "" : `<p class="muted small">${t("tNoFriends")}</p>`}<label>${t("tGuests")}<textarea name="guests" maxlength="2000" rows="3" placeholder="${esc(t("tGuestsPlaceholder"))}"></textarea></label></fieldset><button>${icon("trophy")}<span>${t("tCreateGo")}</span></button></form></section><section class="panel"><h2>${t("tList")}</h2>${
      rows.length
        ? `<div class="team-grid">${rows
            .map(
              (r) =>
                `<a class="team-tile" href="#tournaments/${esc(r.id)}"><strong>${esc(r.name)}</strong><span class="muted">${fmt(r.format)} · ${t("tPlayersCount")}: ${r.players}</span><span class="row"><span class="badge ${r.status === "active" ? "active" : ""}">${statusLabel(r.status)}</span><span class="muted">${r.status === "draft" ? "" : `${t("tRound")} ${r.current_round}/${r.rounds}`}</span></span><span class="muted">${esc(date(r.created_at))}${r.is_owner ? " · " + t("tOrganizer") : ""}</span></a>`,
            )
            .join("")}</div>`
        : `<p class="empty">${t("tEmpty")}</p>`
    }</section>`,
  );
}
const nameOf = (tr, id) =>
  id == null ? t("tBye") : tr.players.find((p) => p.id === id)?.name || "—";
function standingsTable(tr) {
  return `<div class="table-wrap" tabindex="0"><table class="standings"><thead><tr><th>#</th><th>${t("name")}</th><th title="${esc(t("games"))}">${t("tPlayed")}</th><th>${t("wins")}</th><th>${t("draws")}</th><th>${t("losses")}</th><th>${t("tPoints")}</th><th>VP</th><th>Δ VP</th><th title="${esc(t("tSosHint"))}">SoS</th></tr></thead><tbody>${tr.standings
    .map((r) => {
      const p = tr.players.find((x) => x.id === r.player_id);
      return `<tr class="${r.player_id === tr.my_player_id ? "me" : ""} ${p?.dropped ? "dropped" : ""}"><td>${r.rank}</td><td>${esc(p?.name || "—")}${p?.dropped ? ` <span class="muted">(${t("tDropped")})</span>` : ""}</td><td>${r.played}${r.byes ? ` <span class="muted">+${r.byes} ${t("tByeShort")}</span>` : ""}</td><td>${r.wins}</td><td>${r.draws}</td><td>${r.losses}</td><td><b>${r.points}</b></td><td>${r.vp_for}</td><td>${r.diff}</td><td>${r.sos}</td></tr>`;
    })
    .join("")}</tbody></table></div>`;
}
function pairingRow(tr, x) {
  const mine =
      tr.my_player_id != null &&
      [x.player1_id, x.player2_id].includes(tr.my_player_id),
    open = tr.status === "active" && x.round === tr.current_round,
    canReport = open && x.player2_id && (tr.is_owner || mine),
    result =
      x.player2_id == null
        ? `<span class="muted">${t("tByeWin")}</span>`
        : x.vp1 == null
          ? `<span class="muted">${x.match_id ? t(x.match_status || "active") : "—"}</span>`
          : `<b class="mono">${x.vp1} : ${x.vp2}</b> <small class="muted">${t(x.source === "match" ? "tFromMatch" : "tManual")}</small>`;
  const actions = [
    x.match_id ? link(t("open"), "match/" + x.match_id) : "",
    open && mine && x.player2_id && x.vp1 == null && !x.match_id
      ? button(
          t("tMatchCreate"),
          "t-match",
          "secondary small",
          `data-pairing="${x.id}"`,
        )
      : "",
    canReport
      ? `<details class="t-report"><summary>${t(x.source === "manual" ? "tResultEdit" : "tResultEnter")}</summary><form class="t-result-form row" data-pairing="${x.id}"><label>${esc(nameOf(tr, x.player1_id))}<input name="vp1" type="number" min="0" max="999" inputmode="numeric" value="${x.source === "manual" ? x.vp1 : ""}" required></label><label>${esc(nameOf(tr, x.player2_id))}<input name="vp2" type="number" min="0" max="999" inputmode="numeric" value="${x.source === "manual" ? x.vp2 : ""}" required></label><button class="secondary">${t("save")}</button>${x.source === "manual" ? button(t("tResultClear"), "t-clear", "text small", `data-pairing="${x.id}"`) : ""}</form></details>`
      : "",
  ].join("");
  return `<tr><td>${x.table_no}</td><td>${esc(nameOf(tr, x.player1_id))}</td><td>${esc(nameOf(tr, x.player2_id))}</td><td>${result}</td><td class="t-actions">${actions}</td></tr>`;
}
function roundsHtml(tr) {
  const rounds = [...new Set(tr.pairings.map((x) => x.round))].sort(
    (a, b) => b - a,
  );
  if (!rounds.length) return `<p class="muted">${t("tNoRounds")}</p>`;
  return rounds
    .map(
      (r) =>
        `<details class="t-round" ${r === tr.current_round ? "open" : ""}><summary>${t("tRound")} ${r}</summary><div class="table-wrap" tabindex="0"><table><thead><tr><th>${t("tTable")}</th><th>${t("player")} 1</th><th>${t("player")} 2</th><th>${t("score")}</th><th></th></tr></thead><tbody>${tr.pairings
          .filter((x) => x.round === r)
          .map((x) => pairingRow(tr, x))
          .join("")}</tbody></table></div></details>`,
    )
    .join("");
}
function ownerControls(tr) {
  if (!tr.is_owner) return "";
  const roundOpen = tr.pairings.some(
      (x) => x.round === tr.current_round && x.player2_id && x.vp1 == null,
    ),
    actions = [];
  if (tr.status === "draft")
    actions.push(button(t("tStart"), "t-action", "", 'data-kind="start"'));
  if (tr.status === "active" && tr.current_round < tr.rounds)
    actions.push(
      button(
        t("tNextRound"),
        "t-action",
        roundOpen ? "secondary" : "",
        `data-kind="next_round" ${roundOpen ? `title="${esc(t("tRoundOpenHint"))}"` : ""}`,
      ),
    );
  if (tr.status === "active")
    actions.push(
      button(
        t("tFinish"),
        "t-action",
        tr.current_round >= tr.rounds && !roundOpen ? "" : "secondary",
        'data-kind="finish"',
      ),
    );
  actions.push(button(t("tDelete"), "t-delete", "secondary"));
  return `<div class="row">${actions.join("")}</div>${roundOpen && tr.status === "active" ? `<p class="muted small">${t("tRoundOpenHint")}</p>` : ""}`;
}
function playersHtml(tr) {
  return `<ul class="t-players">${tr.players
    .map(
      (p) =>
        `<li class="${p.dropped ? "dropped" : ""}"><span>${p.seed}. ${esc(p.name)}${p.is_user ? ` <span class="mono muted">${esc(p.public_id || "")}</span>` : ` <span class="muted">(${t("tGuest")})</span>`}</span>${tr.is_owner && tr.status !== "finished" ? button(t(p.dropped ? "tReturn" : "tDrop"), "t-drop", "text small", `data-player="${p.id}" data-dropped="${!p.dropped}"`) : ""}</li>`,
    )
    .join("")}</ul>`;
}
async function detailPage(id) {
  const tr = await api("/tournaments/" + encodeURIComponent(id));
  if (page !== "tournaments" || location.hash.split("/")[1] !== id) return;
  current = tr;
  shell(
    `<header class="match-header"><a href="#tournaments" class="back">← ${t("tournaments")}</a><div class="row between"><span class="eyebrow">${fmt(tr.format)} / ${esc(tr.owner_name || "")}</span><span class="badge ${tr.status === "active" ? "active" : ""}">${statusLabel(tr.status)}</span></div><h1>${icon("trophy")} ${esc(tr.name)}</h1><p class="muted">${tr.status === "draft" ? t("tDraftHint") : `${t("tRound")} ${tr.current_round} / ${tr.rounds}`}</p>${ownerControls(tr)}</header><section class="panel"><h2>${t("tStandings")}</h2>${standingsTable(tr)}<p class="muted small">${t("tStandingsHint")}</p></section><section class="panel"><h2>${t("tRounds")}</h2>${roundsHtml(tr)}</section><section class="panel"><details><summary>${t("tPlayers")} · ${tr.players.length}</summary>${playersHtml(tr)}</details></section>`,
  );
}
export async function tournamentsRoute(parts) {
  current = null;
  if (parts[0]) return detailPage(decodeURIComponent(parts[0]));
  return listPage();
}
const refresh = () => detailPage(current.id);
export function init() {
  app.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b || b.disabled || !b.dataset.action.startsWith("t-") || !current)
      return;
    const a = b.dataset.action,
      id = current.id;
    b.disabled = true;
    try {
      if (a === "t-action") {
        if (b.dataset.kind === "finish" && !confirm(t("tFinishConfirm")))
          return;
        await api(`/tournaments/${id}/actions`, "POST", {
          request_id: uuid(),
          version: current.version,
          action: b.dataset.kind,
        });
        await refresh();
      } else if (a === "t-delete") {
        if (!confirm(t("tDeleteConfirm"))) return;
        await api(`/tournaments/${id}`, "DELETE", {});
        location.hash = "tournaments";
      } else if (a === "t-drop") {
        await api(
          `/tournaments/${id}/players/${b.dataset.player}/drop`,
          "POST",
          {
            request_id: uuid(),
            dropped: b.dataset.dropped === "true",
          },
        );
        await refresh();
      } else if (a === "t-match") {
        const r = await api(
          `/tournaments/${id}/pairings/${b.dataset.pairing}/match`,
          "POST",
          {
            request_id: uuid(),
          },
        );
        location.hash = "match/" + r.id;
      } else if (a === "t-clear") {
        await api(
          `/tournaments/${id}/pairings/${b.dataset.pairing}/result`,
          "POST",
          {
            request_id: uuid(),
            vp1: null,
            vp2: null,
          },
        );
        await refresh();
      }
    } catch (err) {
      notify(err.message);
    } finally {
      b.disabled = false;
    }
  });
  app.addEventListener("submit", async (e) => {
    const f = e.target;
    if (f.id !== "tournament-form" && !f.classList.contains("t-result-form"))
      return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const b = f.querySelector("button:not([type=button])");
    if (b) b.disabled = true;
    try {
      if (f.id === "tournament-form") {
        const d = new FormData(f),
          players = [
            ...(d.get("me") ? [{ public_id: me.public_id }] : []),
            ...d.getAll("friend").map((public_id) => ({ public_id })),
            ...String(d.get("guests") || "")
              .split("\n")
              .map((s) => s.trim())
              .filter(Boolean)
              .map((name) => ({ name: name.slice(0, 64) })),
          ];
        if (players.length < 2) return notify(t("tNeedPlayers"));
        const r = await api("/tournaments", "POST", {
          request_id: uuid(),
          name: String(d.get("name") || "").trim(),
          format: d.get("format"),
          ...(d.get("format") === "swiss" && d.get("rounds")
            ? { rounds: +d.get("rounds") }
            : {}),
          players,
        });
        location.hash = "tournaments/" + r.id;
      } else if (current) {
        const d = Object.fromEntries(new FormData(f));
        await api(
          `/tournaments/${current.id}/pairings/${f.dataset.pairing}/result`,
          "POST",
          {
            request_id: uuid(),
            vp1: +d.vp1,
            vp2: +d.vp2,
          },
        );
        await refresh();
      }
    } catch (err) {
      notify(err.message);
    } finally {
      if (b) b.disabled = false;
    }
  });
}
