import {
  api,
  button,
  catalogs,
  date,
  esc,
  input,
  link,
  me,
  notify,
  select,
  t,
  uuid,
} from "./core.js";
import { currentMatch, editionField, shell, title } from "./app.js";
import { allowedTacOps, primaryOptions, tacSelect } from "./ops.js";
import { rosterSelect } from "./rosters.js";
import { opCountField } from "./opcount.js";
import { LOCAL_LIST, fillLocalPlayers, localField } from "./localplayers.js";
import { qrSvg } from "./qr.js";
/* v1.2: quick start (invite by code), single-device hot-seat matches. */
export const pendingJoin = () => {
  const [p, code] = (location.hash.slice(1) || "").split("/");
  return p === "join" && /^[A-Za-z2-9]{6,8}$/.test(code || "")
    ? code.toUpperCase()
    : null;
};
export const inviteLink = (code) => `${location.origin}/#join/${code}`;
export const isHotseat = (m) => m.kind === "hotseat";
const isCreator = (m) => m.created_by === me.id;
export const slotAttr = (m, p) => (isHotseat(m) ? `data-slot="${p.slot}"` : "");

export function newMatchPage() {
  shell(
    `${title("newGame", "NEW OPERATION")}<div class="grid"><section class="panel"><h2>${t("hotseat")}</h2><p class="muted">${t("hotseatHint")}</p><form id="new-match-form" data-kind="hotseat">${input("guestName", "guest_name", "text", t("guestDefault"), `required maxlength="64" ${LOCAL_LIST}`)}${localField()}${editionField()}<button>${t("startSetup")}</button></form></section><section class="panel"><h2>${t("inviteGame")}</h2><p class="muted">${t("inviteHint")}</p><form id="new-match-form-invite" data-kind="friend">${editionField()}<button>${t("createInvite")}</button></form></section></div><section class="panel"><h2>${t("joinByCode")}</h2>${joinForm()}</section><p class="muted">${t("quickAlt")} ${link(t("quick"), "quick")}</p>`,
  );
  fillLocalPlayers();
}
export function joinForm() {
  return `<form id="join-form" class="row">${input("inviteCode", "code", "text", "", 'required minlength="6" maxlength="8" autocapitalize="characters" autocomplete="off" pattern="[A-Za-z2-9]{6,8}"')}<button>${t("join")}</button></form>`;
}
export async function joinPage(code) {
  try {
    const r = await api("/invites/" + code + "/join", "POST", {
      request_id: uuid(),
    });
    location.hash = "match/" + r.match_id;
  } catch (e) {
    if (!me) return;
    location.hash = "new";
    notify(e.message);
  }
}
export function inviteBlock(m) {
  if (m.kind !== "friend" || !isCreator(m) || m.status !== "setup") return "";
  const empty = !m.players[1].user_id;
  if (!empty) return "";
  const inv = m.invite;
  return `<section class="panel invite"><h2>${t("waitingOpponent")}</h2>${
    inv
      ? `<div class="invite-body"><div><p class="muted">${t("inviteCodeText")}</p><p class="invite-code mono accent" aria-label="${t("inviteCode")}">${esc(inv.code)}</p><p class="mono muted invite-link">${esc(inviteLink(inv.code))}</p></div><figure class="invite-qr">${qrSvg(inviteLink(inv.code), { label: t("inviteQr") })}<figcaption class="muted">${t("inviteQrHint")}</figcaption></figure></div><p class="muted">${t("inviteExpires")}: ${esc(date(inv.expires_at))}</p><div class="row">${button(t("copyLink"), "copy-invite", "", `data-code="${esc(inv.code)}"`)}${navigator.share ? button(t("share"), "share-invite", "secondary", `data-code="${esc(inv.code)}"`) : ""}${button(t("newCode"), "new-invite", "secondary")}</div>`
      : `<p class="muted">${t("inviteMissing")}</p>${button(t("createInvite"), "new-invite")}`
  }</section>`;
}
export function cancelBlock(m) {
  if (m.status !== "setup" || !isCreator(m)) return "";
  return `<p>${button(t("cancelMatch"), "cancel-match", "secondary")}</p>`;
}
function guestSecretFields(m, p) {
  if (m.scoring_mode !== "approved2025")
    return `<p class="muted">${t("guestSetupLegacyHint")}</p>`;
  const counts = {};
  return `${select("primaryOp", "primary_op", primaryOptions(), "crit")}<p class="muted">${t("primaryTiming")}</p><div id="p2-aspect-fields" ${catalogs.find((c) => c.id === p.team_id)?.config.conditional_archetypes ? "" : "hidden"}><div class="grid">${["dire_avenger", "howling_banshee", "striking_scorpion"].map((k) => input(k, "aspect_" + k, "number", 0, 'min="0" max="14"')).join("")}</div><p class="muted">${t("aspectHint")}</p></div><div id="p2-tac-choice">${tacSelect(allowedTacOps(m, p.team_id, counts))}</div>`;
}
export function hotseatSetup(m) {
  if (!isHotseat(m) || m.status !== "setup") return "";
  const p = m.players[1];
  return `<section class="panel"><h2>${t("guestSetup")}: ${esc(p.display_name)}</h2><p class="warning">${t("passDevice")} ${esc(p.display_name)}. ${t("passDeviceHint")}</p>${p.secret_set ? `<p class="accent">✓ ${t("guestSecretSaved")}</p>` : ""}${!p.team_id ? `<p class="muted">${t("guestSetupFirst")}</p>` : ""}<details ${p.secret_set ? "" : "open"}><summary>${t("guestSetupOpen")}</summary><form id="player-setup-form" data-slot="2">${guestSecretFields(m, p)}${rosterSelect(p, p.team_id)}${opCountField(p, p.team_id)}<label>${t("roster")}<textarea name="roster" maxlength="4000">${esc(p.roster)}</textarea></label><button>${t("save")}</button></form></details></section>`;
}
function refreshGuestTac() {
  const f = document.querySelector("#player-setup-form");
  if (!f || !currentMatch || !f.elements.tac_op_id) return;
  const p = currentMatch.players[1];
  const counts = Object.fromEntries(
    ["dire_avenger", "howling_banshee", "striking_scorpion"].map((k) => [
      k,
      +f.elements["aspect_" + k]?.value || 0,
    ]),
  );
  document.querySelector("#p2-tac-choice").innerHTML = tacSelect(
    allowedTacOps(currentMatch, p.team_id, counts),
    +f.elements.tac_op_id.value,
  );
}

/* v1.9: listeners are registered from main.js in a fixed order (the former <script> order). */
export function init() {
  document.addEventListener("change", (e) => {
    if (
      e.target.closest("#player-setup-form") &&
      e.target.name.startsWith("aspect_")
    )
      refreshGuestTac();
  });
}
