// v1.9: two signed-in players in two browser contexts: invite by link and QR, the shared operative tracker
// (live updates over SSE, automatic kills, undo), attack calculator permissions, finishing and confirming
// a game, history, Elo, rosters (.ros/.rosz export and import, attached roster, printing), tournaments,
// accessibility of the signed-in pages in both themes. Accounts: e2e-alpha and e2e-bravo (see helpers.mjs).
import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import { qrSvg } from "../../web/qr.js";
import {
  BASE,
  USERS,
  ru,
  launch,
  signedIn,
  open,
  view,
  axe,
  assertClean,
  noHorizontalScroll,
  squash,
  uuid,
  api,
  call,
  befriend,
  matchAction,
  matchCommand,
  setupPlayer,
} from "./helpers.mjs";

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const ops = (page, slot) => `.half.slot-${slot} li.op`;
const killsOf = (page, slot) =>
  page.textContent(`.half.slot-${slot} .kill-num output`).then(squash);

/* Both primary operations, turning points 2–4 (alpha scores Crit Op VP), finish by alpha, confirm by bravo. */
async function playOut(a, b, id) {
  await matchCommand(a, id, "/primary", { primary_op: "crit" });
  await matchCommand(b, id, "/primary", { primary_op: "kill" });
  for (let tp = 2; tp <= 4; tp++) {
    await matchAction(a, id, "turn", { turning_point: tp });
    const m = await call(a, `/matches/${id}`);
    const crit = Object.entries(m.rules_snapshot.sources).find(
      ([, kind]) => kind === "crit",
    )[0];
    await matchCommand(a, id, "/scores", {
      turning_point: tp,
      source_id: Number(crit),
      delta: 1,
    });
  }
  await matchAction(a, id, "finish");
  await matchAction(b, id, "confirm");
  assert.equal((await call(a, `/matches/${id}`)).status, "confirmed");
}

async function inviteMatch(a, b) {
  const { id } = await call(a, "/matches", "POST", {
    request_id: uuid(),
    kind: "friend",
    edition: "2024",
  });
  const { code } = await call(a, `/matches/${id}/invite`, "POST", {
    request_id: uuid(),
  });
  await call(b, `/invites/${code}/join`, "POST", { request_id: uuid() });
  return id;
}

describe("two players", () => {
  let browser, a, b, matchId;
  before(async () => {
    browser = await launch();
    a = await signedIn(browser, "alpha");
    b = await signedIn(browser, "bravo");
    await befriend(a, b);
  });
  after(() => browser?.close());

  it("invite: the QR code encodes the link, the opponent joins by opening it", async () => {
    await open(a, "new", "#new-match-form-invite");
    await a.click("#new-match-form-invite button");
    await a.waitForSelector(".invite-qr svg");
    matchId = a.url().split("#match/")[1];
    const link = squash(await a.textContent(".invite-link"));
    assert.match(link, new RegExp(`^${escapeRe(BASE)}/#join/[A-Z0-9]{6,}$`));
    const expected = qrSvg(link, { label: ru.inviteQr });
    const shown = await a.$eval(".invite-qr svg", (s) => ({
      box: s.getAttribute("viewBox"),
      label: s.getAttribute("aria-label"),
      d: s.querySelector("path").getAttribute("d"),
    }));
    assert.equal(shown.box, expected.match(/viewBox="([^"]+)"/)[1]);
    assert.equal(shown.label, ru.inviteQr);
    assert.equal(
      shown.d,
      expected.match(/ d="([^"]+)"/)[1],
      "same modules as web/qr.js (unit-tested)",
    );
    await axe(a, "invite");

    await b.goto(link);
    await b.waitForURL(`**/#match/${matchId}`);
    const m = await call(a, `/matches/${matchId}`);
    assert.equal(m.players[1].display_name, USERS.bravo.name);
    await setupPlayer(a, matchId, "crit");
    await setupPlayer(b, matchId, "kill");
    await matchAction(a, matchId, "start");
    assertClean(a, "invite");
    assertClean(b, "join");
  });

  it("tracker: shared live, kills counted automatically, undo only for the author", async () => {
    await open(a, `match/${matchId}`, ".board .half.slot-1 .op-add");
    await open(b, `match/${matchId}`, ".board .half.slot-2 .op-add");
    assert.equal(
      await b.$(".half.slot-1 .op-add"),
      null,
      "the opponent's half is read-only",
    );

    await a.click(".half.slot-1 .op-add summary");
    await a.fill('.half.slot-1 .op-add-form [name="name"]', "Сержант E2E");
    await a.fill('.half.slot-1 .op-add-form [name="wounds_max"]', "9");
    await a.click(".half.slot-1 .op-add-form button");
    await a.waitForSelector(`${ops(a, 1)}:has-text("Сержант E2E")`);
    await b.waitForSelector(`${ops(b, 1)}:has-text("Сержант E2E")`); // over SSE
    assert.equal(
      await b.$$eval(`${ops(b, 1)} [data-action="op-wound"]`, (l) => l.length),
      0,
    );

    await a.click(`${ops(a, 1)} .op-down`);
    await a.waitForSelector(`${ops(a, 1)}.down`);
    await b.waitForSelector(`${ops(b, 1)}.down`);
    await b.waitForFunction(
      () =>
        document
          .querySelector(".half.slot-2 .kill-num output")
          ?.textContent.trim() === "1",
    );
    assert.equal(
      await killsOf(a, 2),
      "1",
      "the opponent's kill count follows the tracker",
    );

    assert.ok(await a.$('[data-action="undo"]'), "the author can undo");
    assert.equal(
      await b.$('[data-action="undo"]'),
      null,
      "the opponent cannot",
    );
    await a.click('[data-action="undo"]');
    await a.waitForSelector(`${ops(a, 1)}:not(.down)`);
    await b.waitForSelector(`${ops(b, 1)}:not(.down)`);
    await b.waitForFunction(
      () =>
        document
          .querySelector(".half.slot-2 .kill-num output")
          ?.textContent.trim() === "0",
    );

    await a.click(`${ops(a, 1)} [data-action="op-activate"]`);
    await b.waitForSelector(`${ops(b, 1)}.activated`);
    await axe(a, "board with the tracker");
    assertClean(a, "tracker alpha");
    assertClean(b, "tracker bravo");
  });

  it("attack calculator: damage can be applied only to an operative the user may edit", async () => {
    const roll = async (page, tries) => {
      for (let i = 0; i < tries; i++) {
        await page.click('#board-sheet [data-action="attack-roll"]');
        await page.waitForSelector("#board-sheet .atk-roll");
        if (await page.$('#board-sheet [data-action="attack-apply"]'))
          return true;
      }
      return false;
    };
    const target = async (page) => {
      await page.click("#board-menu summary");
      await page.click('#board-menu [data-panel="attack"]');
      await page.waitForSelector('#board-sheet select[name="target"]');
      const value = await page.$eval(
        '#board-sheet select[name="target"]',
        (s) =>
          [...s.options].map((o) => o.value).find((v) => v.startsWith("op:")),
      );
      assert.ok(value, "alpha's operative is a possible target");
      await page.selectOption('#board-sheet select[name="target"]', value);
    };
    await target(b);
    assert.equal(
      await roll(b, 8),
      false,
      "bravo cannot change alpha's operative",
    );
    await target(a);
    assert.ok(await roll(a, 40), "a roll with damage offers to apply it");
    await a.click('#board-sheet [data-action="attack-apply"]');
    await b.waitForFunction(() => {
      const w = document.querySelector(".half.slot-1 li.op .wnum");
      return w && Number(w.textContent) < 9;
    });
    assertClean(a, "attack alpha");
    assertClean(b, "attack bravo");
  });

  it("finished game: confirmation, history, Elo rating", async () => {
    await playOut(a, b, matchId);
    await open(a, `match/${matchId}`, ".result-panel");
    await axe(a, "confirmed match");
    await open(a, "history", `${view("history")}`);
    await a.waitForSelector(`a[href="#match/${matchId}"]`);
    await open(a, "stats", view("stats"));
    await a.waitForSelector("table.ratings");
    const ratings = squash(await a.textContent("table.ratings"));
    for (const u of [USERS.alpha, USERS.bravo])
      assert.ok(ratings.includes(u.name), `${u.name} in the Elo table`);
    await axe(a, "stats");
    assertClean(a, "history and stats");
  });

  it("rosters: export .ros/.rosz, import back, attached roster fills the tracker, printing", async (t) => {
    const { teams } = await call(b, "/teams");
    if (!teams.find((x) => x.slug === "kommandos" && x.has_roster))
      return t.skip(
        "no team reference with roster schemas: scripts/import-teams.sh (or E2E_TEAMS_BUNDLE for scripts/e2e-docker.sh)",
      );
    const { schema } = await call(b, "/teams/kommandos/roster-schema");
    const models = schema.root.filter((n) => n.t === "model");
    const pick = (re) => models.find((n) => re.test(n.n));
    const chosen = [
      pick(/Boss Nob/),
      pick(/Kommando Boy$/),
      pick(/Kommando Boy$/),
      pick(/Snipa/),
    ];
    assert.ok(
      chosen.every(Boolean),
      "Kommandos roster schema has the expected models",
    );
    const name = `Ваагх E2E ${Date.now().toString(36)}`;
    const roster = await call(b, "/rosters", "POST", {
      request_id: uuid(),
      team_slug: "kommandos",
      name,
      data: {
        selections: chosen.map((n, i) => ({
          uid: `e2e${i}${Date.now().toString(36)}`,
          key: n.k,
          n: 1,
          sel: [],
        })),
      },
    });

    const files = await b.evaluate(async (id) => {
      const get = async (format) => {
        const r = await fetch(`/api/rosters/${id}/export?format=${format}`);
        return {
          status: r.status,
          type: r.headers.get("content-type"),
          bytes: [...new Uint8Array(await r.arrayBuffer())],
        };
      };
      return { ros: await get("ros"), rosz: await get("rosz") };
    }, roster.id);
    assert.equal(files.ros.status, 200);
    assert.match(
      Buffer.from(files.ros.bytes).toString("utf8"),
      /<roster[\s>][\s\S]*Boss Nob/,
    );
    assert.equal(files.rosz.status, 200);
    assert.equal(
      Buffer.from(files.rosz.bytes.slice(0, 2)).toString(),
      "PK",
      ".rosz is a zip archive",
    );

    await open(b, "rosters", "#roster-import-form");
    await axe(b, "rosters");
    await b.setInputFiles('#roster-import-form [name="file"]', {
      name: "waagh.rosz",
      mimeType: "application/zip",
      buffer: Buffer.from(files.rosz.bytes),
    });
    await b.click("#roster-import-form button");
    await b.waitForURL(
      (u) =>
        /#rosters\/[0-9a-f-]{36}$/.test(u.hash) && !u.hash.endsWith(roster.id),
    );
    const imported = await call(b, `/rosters/${b.url().split("#rosters/")[1]}`);
    assert.equal(imported.team_slug, "kommandos");
    assert.equal(imported.data.selections.length, 4);

    const id = await inviteMatch(a, b);
    await setupPlayer(a, id, "crit");
    await setupPlayer(b, id, "kill", { roster_id: roster.id });
    await matchAction(a, id, "start");
    await open(a, `match/${id}`, `${ops(a, 2)}`);
    assert.equal(
      await a.$$eval(ops(a, 2), (l) => l.length),
      4,
      "operatives of the attached roster",
    );
    await a.click(`${ops(a, 2)} .op-name`);
    await a.waitForSelector("#board-sheet .datacard");
    await axe(a, "datacard sheet");

    await a.evaluate(() => {
      window.print = () => (window.__printed = (window.__printed || 0) + 1);
    });
    await a.click("#board-menu summary");
    await a.click('#board-menu [data-panel="roster"]');
    await a.waitForSelector('#board-sheet [data-action="print-roster"]');
    await a.click('#board-sheet [data-action="print-roster"]');
    await a.waitForFunction(() => window.__printed === 1);
    assert.ok(
      (await a.$$("#print-root .datacard")).length >= 3,
      "printed datacards",
    );
    await a.evaluate(() => window.dispatchEvent(new Event("afterprint")));
    await playOut(a, b, id);
    assertClean(a, "roster match");
    assertClean(b, "rosters");
  });

  it("tournament: create with a friend and guests, start, results, finish", async () => {
    await open(a, "tournaments", "#tournament-form");
    await axe(a, "tournaments");
    const tname = `Кубок E2E ${new Date().toISOString().slice(0, 16)}`;
    await a.fill('#tournament-form [name="name"]', tname);
    await a.fill('#tournament-form [name="rounds"]', "1");
    const bravoPid = (await call(b, "/auth/me")).public_id;
    await a.check(`#tournament-form [name="friend"][value="${bravoPid}"]`);
    await a.fill('#tournament-form [name="guests"]', "Гость Один\nГость Два");
    await a.click("#tournament-form button:not([type=button])");
    await a.waitForURL(/#tournaments\/[0-9a-f-]{36}$/);
    const tid = a.url().split("#tournaments/")[1];
    await a.click('[data-action="t-action"][data-kind="start"]');
    await a.waitForSelector(".t-result-form", { state: "attached" });
    for (let i = 0; i < 4; i++) {
      let form = null;
      for (const f of await a.$$(".t-result-form"))
        if (!(await f.$eval('[name="vp1"]', (x) => x.value))) {
          form = f;
          break;
        }
      if (!form) break;
      await form.evaluate((el) => (el.closest("details").open = true));
      await (await form.$('[name="vp1"]')).fill(String(12 + i));
      await (await form.$('[name="vp2"]')).fill("8");
      await (await form.$("button:not([type=button])")).click();
      await a.waitForFunction((el) => !el.isConnected, form); // the view is redrawn with the result
    }
    assert.equal(
      await a.$$eval(
        '.t-result-form [name="vp1"]',
        (l) => l.filter((x) => x.value).length,
      ),
      2,
      "two pairings of four players have results",
    );
    await a.click('[data-action="t-action"][data-kind="finish"]');
    await a.waitForFunction(
      () =>
        !document.querySelector('[data-action="t-action"][data-kind="finish"]'),
    );
    const standings = await a.$$eval("table.standings tbody tr", (rows) =>
      rows.map((r) => r.textContent),
    );
    assert.equal(standings.length, 4);
    await axe(a, "finished tournament");
    const notes = await call(b, "/notifications");
    assert.ok(
      notes.some((n) => n.kind === "tournament_added" && n.resource_id === tid),
      "bravo was notified",
    );
    await open(b, `tournaments/${tid}`, "table.standings");
    assertClean(a, "tournament");
    assertClean(b, "tournament bravo");
  });

  it("signed-in pages pass axe in both themes and fit a phone", async () => {
    for (const theme of ["light", "dark"]) {
      const page = await signedIn(browser, "alpha", {
        theme,
        mobile: theme === "dark",
      });
      for (const [hash, sel] of [
        ["overview", view("overview")],
        ["new", "#new-match-form-invite"],
        ["history", view("history")],
        ["friends", view("friends")],
        ["stats", "table.ratings"],
        ["teams", view("teams")], // v1.12: Faction Rules are a page of the «Rules» section
        ["rosters", view("rosters")],
        ["profile", view("profile")],
        [`match/${matchId}`, ".result-panel"],
      ]) {
        await open(page, hash, sel);
        if (theme === "dark") await noHorizontalScroll(page, `${hash} 390px`);
        await axe(page, `${hash} ${theme}`);
      }
      assertClean(page, `pages ${theme}`);
      await page.context().close();
    }
  });

  it("the API requires the CSRF token and lets only the creator cancel", async () => {
    const id = await inviteMatch(a, b);
    const { version } = await call(a, `/matches/${id}`);
    const noCsrf = await a.evaluate(
      async ({ id, version }) => {
        const r = await fetch(`/api/matches/${id}/actions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            request_id: crypto.randomUUID(),
            version,
            action: "cancel",
          }),
        });
        return r.status;
      },
      { id, version },
    );
    assert.equal(noCsrf, 403);
    assert.equal(
      (
        await api(b, `/matches/${id}/actions`, "POST", {
          request_id: uuid(),
          version,
          action: "cancel",
        })
      ).status,
      409,
      "only the creator cancels",
    );
    await matchAction(a, id, "cancel");
    assert.equal((await call(a, `/matches/${id}`)).status, "cancelled");
  });
});
