import {
  api,
  app,
  badge,
  button,
  catName,
  date,
  esc,
  langButton,
  localizeRow,
  logo,
  me,
  notify,
  t,
} from "./core.js";
import { currentMatch, page, shell } from "./app.js";
import { fmtClock } from "./clock.js";
import { ordered } from "./turns.js";
/* v1.5 — share result (text, PNG card, read-only LAN link), public result page, feedback form. */
export const ENDED = [
  "awaiting_confirmation",
  "confirmed",
  "disputed",
  "unconfirmed",
];
const shareLinks = {},
  sharePreviews = {};
const sharedLink = (token) => `${location.origin}/#shared/${token}`;
function resultLine(names, vps) {
  return vps[0] === vps[1]
    ? t("shareDraw")
    : `${t("shareWinner")}: ${vps[0] > vps[1] ? names[0] : names[1]}`;
}
function matchSummary(m) {
  const ps = ordered(m);
  return {
    mission: catName(m.mission_id),
    killzone: catName(m.killzone_id),
    edition: m.edition,
    status: m.status,
    date: m.played_at,
    names: ps.map((p) => p.display_name),
    teams: ps.map((p) => catName(p.team_id)),
    vps: ps.map((p) => p.vp),
  };
}
function shareText(s) {
  return `KILLSTASS · ${s.mission}\n${s.names[0]} ${s.vps[0]} : ${s.vps[1]} ${s.names[1]}\n${resultLine(s.names, s.vps)} · ${t(s.status)}\n${date(s.date)}`;
}
/* 1200×630 card drawn locally; no external fonts or images (CSP: self only). */
function shareCard(s) {
  const c = document.createElement("canvas");
  c.width = 1200;
  c.height = 630;
  const g = c.getContext("2d"),
    accent = "#ff6a13";
  g.fillStyle = "#0b0b0b";
  g.fillRect(0, 0, 1200, 630);
  g.fillStyle = accent;
  g.fillRect(0, 0, 1200, 10);
  g.fillRect(60, 560, 120, 6);
  const text = (
    v,
    x,
    y,
    font,
    color = "#f5f5f5",
    align = "left",
    max = 1080,
  ) => {
    g.font = font;
    g.fillStyle = color;
    g.textAlign = align;
    g.fillText(String(v), x, y, max);
  };
  text("KILL", 60, 90, "bold 44px Arial, sans-serif");
  g.font = "bold 44px Arial, sans-serif";
  text(
    "STASS",
    60 + g.measureText("KILL").width,
    90,
    "bold 44px Arial, sans-serif",
    accent,
  );
  text(s.mission.toUpperCase(), 60, 160, "bold 40px Arial, sans-serif");
  text(
    `${t("edition")} ${s.edition} · ${s.killzone} · ${date(s.date)}`,
    60,
    205,
    "26px Arial, sans-serif",
    "#a8a8a8",
  );
  [0, 1].forEach((i) => {
    const x = i ? 1140 : 60,
      align = i ? "right" : "left",
      win = s.vps[i] > s.vps[1 - i];
    text(
      s.names[i],
      x,
      300,
      "bold 40px Arial, sans-serif",
      "#f5f5f5",
      align,
      480,
    );
    text(s.teams[i], x, 340, "26px Arial, sans-serif", "#a8a8a8", align, 480);
    text(
      s.vps[i],
      x,
      480,
      "bold 150px 'Courier New', monospace",
      win ? accent : "#f5f5f5",
      align,
    );
  });
  text(
    ":",
    600,
    470,
    "bold 110px 'Courier New', monospace",
    "#6f6f6f",
    "center",
  );
  text(
    `${resultLine(s.names, s.vps)} · ${t(s.status)}`,
    60,
    545,
    "28px Arial, sans-serif",
    "#f5f5f5",
  );
  text(
    t("shareFooter"),
    1140,
    600,
    "20px Arial, sans-serif",
    "#6f6f6f",
    "right",
  );
  return c;
}
export function sharePanel(m) {
  if (!ENDED.includes(m.status)) return "";
  const link = shareLinks[m.id];
  return `<section class="panel share" id="share-panel"><h2>${t("shareResult")}</h2><div class="row">${button(t("shareText"), "share-text", "")}${button(t("shareImage"), "share-image", "secondary")}</div><div id="share-preview">${sharePreviews[m.id] || ""}</div><h3>${t("shareLink")}</h3><p class="muted">${t("shareLinkHint")}</p>${
    link
      ? `<p class="mono share-url">${esc(link)}</p><div class="row">${button(t("copyLink"), "share-copy-link", "secondary")}${button(t("shareRevoke"), "share-revoke", "secondary")}</div>`
      : `<div class="row">${button(t("shareCreateLink"), "share-link", "secondary")}${button(t("shareRevoke"), "share-revoke", "secondary")}</div>`
  }</section>`;
}
function redrawShare() {
  const el = document.querySelector("#share-panel");
  if (el && currentMatch) el.outerHTML = sharePanel(currentMatch);
}
export async function copyText(v) {
  try {
    await navigator.clipboard.writeText(v);
    notify(t("copied"));
  } catch {
    prompt(t("copyManually"), v);
  }
}

/* Pages that work with or without a session (#shared/TOKEN, #demo). */
export function standalone(content) {
  if (me) return shell(content);
  app.innerHTML = `<main id="content" class="stack standalone"><header class="row between">${logo()}<div class="row">${langButton()}<a class="button secondary" href="#overview">${t("openApp")}</a></div></header>${content}</main>`;
}
export async function sharedPage(token) {
  let s;
  try {
    s = await api("/shared/" + encodeURIComponent(token || ""));
  } catch (err) {
    return standalone(
      `<section class="panel"><h1>${t("shareNotFound")}</h1><p class="muted">${t("shareNotFoundHint")}</p></section>`,
    );
  }
  const tr = (code, label) => localizeRow({ code, label }).label;
  s.mission = tr(s.mission_code, s.mission);
  s.killzone = tr(s.killzone_code, s.killzone);
  s.players.forEach((p) => (p.team = tr(p.team_code, p.team)));
  const names = s.players.map((p) => p.display_name),
    vps = s.players.map((p) => p.vp),
    approved = s.scoring_mode === "approved2025";
  const lead = vps[0] === vps[1] ? 0 : vps[0] > vps[1] ? 1 : 2;
  standalone(
    `<header class="match-header"><div class="row between"><span class="eyebrow">${t("sharedResult")}</span>${badge(s.status)}</div><h1>${esc(s.mission || "—")}</h1><p class="muted">${t("edition")} ${esc(s.edition)} · ${esc(s.killzone || "—")} · ${esc(date(s.played_at))}</p></header><div class="scoreboard">${s.players
      .map(
        (p) =>
          `<section class="player slot-${p.slot} ${lead === p.slot ? "leader" : ""}"><span class="eyebrow">${t("player")} ${p.slot}</span><h2 class="player-name">${esc(p.display_name)}</h2><span class="score ${lead === p.slot ? "accent" : ""}">${p.vp}</span><span class="muted">VP</span><p class="muted">${esc(p.team || "—")}</p>${approved ? `<p class="ops-line">Crit ${p.crit} · Tac ${p.tac} · Kill ${p.kill}<br>${t("primaryBonus")}: +${p.primary_bonus}${p.primary_op ? " · " + esc(t("op_" + p.primary_op)) : ""}</p>` : ""}${lead === p.slot ? badge(s.status === "confirmed" ? "winner" : "leader") : !lead ? badge("tie") : ""}</section>`,
      )
      .join(
        "",
      )}</div><section class="panel"><h2>${t("score")}</h2><div class="table-wrap" tabindex="0"><table><thead><tr><th>${t("turn")}</th>${names.map((n) => `<th>${esc(n)}</th>`).join("")}</tr></thead><tbody>${Array.from(
      { length: s.kind === "guest" ? 1 : s.turns },
      (_, i) =>
        `<tr><td>${i + 1}</td>${[1, 2].map((slot) => `<td>${s.turn_scores.find((x) => x.slot === slot && x.turning_point === i + 1)?.vp || 0}</td>`).join("")}</tr>`,
    ).join("")}</tbody></table></div>${
      s.clock
        ? `<p class="muted">${t("clockSummary")} (${esc(t("clockMode_" + s.clock.mode))}): ${t("clockTotal")} ${fmtClock(s.clock.total_seconds)}${s.clock.mode !== "stopwatch" ? " · " + s.clock.slots.map((x, i) => esc(names[i]) + " " + fmtClock(x.elapsed_seconds)).join(" · ") : ""}</p>`
        : ""
    }<p class="muted">${esc(resultLine(names, vps))}</p></section>`,
  );
}
export function feedbackPanel() {
  return `<section class="panel"><h2>${t("feedback")}</h2><p class="muted">${t("feedbackHint")}</p><form id="feedback-form"><label>${t("feedbackMessage")}<textarea name="message" required maxlength="2000" rows="4"></textarea></label><button>${t("feedbackSend")}</button></form></section>`;
}

/* v1.9: listeners are registered from main.js in a fixed order (the former <script> order). */
export function init() {
  app.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b || b.disabled || !currentMatch) return;
    const a = b.dataset.action;
    if (!a.startsWith("share-") || a === "share-invite") return;
    const m = currentMatch,
      s = matchSummary(m);
    b.disabled = true;
    try {
      if (a === "share-text") {
        const text = shareText(s);
        if (navigator.share)
          await navigator.share({ title: "KILLSTASS", text }).catch(() => {});
        else await copyText(text);
      } else if (a === "share-image") {
        const canvas = shareCard(s),
          url = canvas.toDataURL("image/png"),
          name = `killstass-${m.id.slice(0, 8)}.png`;
        const blob = await new Promise((r) => canvas.toBlob(r, "image/png"));
        const file = new File([blob], name, { type: "image/png" });
        if (navigator.canShare?.({ files: [file] }))
          await navigator
            .share({ files: [file], title: "KILLSTASS", text: shareText(s) })
            .catch(() => {});
        sharePreviews[m.id] =
          `<img class="share-card" src="${url}" alt="${esc(shareText(s))}"><p><a class="button secondary" href="${url}" download="${name}">${t("shareDownload")}</a></p>`;
        document.querySelector("#share-preview").innerHTML =
          sharePreviews[m.id];
      } else if (a === "share-link") {
        const r = await api("/matches/" + m.id + "/share", "POST", {});
        shareLinks[m.id] = sharedLink(r.token);
        redrawShare();
      } else if (a === "share-copy-link") await copyText(shareLinks[m.id]);
      else if (a === "share-revoke") {
        if (confirm(t("shareRevokeConfirm"))) {
          await api("/matches/" + m.id + "/share", "DELETE", {});
          delete shareLinks[m.id];
          redrawShare();
          notify(t("shareRevoked"));
        }
      }
    } catch (err) {
      notify(err.message);
    } finally {
      b.disabled = false;
    }
  });
  app.addEventListener("submit", async (e) => {
    if (e.target.id !== "feedback-form") return;
    e.preventDefault();
    const f = e.target,
      b = f.querySelector("button");
    b.disabled = true;
    try {
      await api("/feedback", "POST", {
        message: f.message.value.trim(),
        page: "#" + page,
      });
      f.reset();
      notify(t("feedbackThanks"));
    } catch (err) {
      notify(err.message);
    } finally {
      b.disabled = false;
    }
  });
}
