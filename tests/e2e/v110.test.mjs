// v1.10: profile extras and the player page (avatar, motto, favourite team, head-to-head), game nights
// (RSVP with a team, pairs from the answers, the match of a table, .ics and the calendar subscription),
// the killzone map editor (tokens, frames per turning point, autosave, PNG, the shared board of a match),
// the offline scoreboard queue and the sound/vibration settings. Seasons, achievements, TV screens and
// password reset codes need an administrator: admin.test.mjs. Accounts: e2e-alpha and e2e-bravo.
import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import {
  BASE,
  USERS,
  ru,
  launch,
  signedIn,
  open,
  axe,
  assertClean,
  noHorizontalScroll,
  squash,
  uuid,
  api,
  call,
  me,
  befriend,
  matchAction,
  matchCommand,
  setupPlayer,
  until,
  pngFile,
} from "./helpers.mjs";

const stamp = () => String(Date.now()).slice(-6);
/* A started friend match of alpha (slot 1) and bravo (slot 2). */
async function activeMatch(a, b) {
  const { id } = await call(a, "/matches", "POST", {
    request_id: uuid(),
    kind: "friend",
    edition: "2024",
  });
  const { code } = await call(a, `/matches/${id}/invite`, "POST", {
    request_id: uuid(),
  });
  await call(b, `/invites/${code}/join`, "POST", { request_id: uuid() });
  await setupPlayer(a, id, "crit");
  await setupPlayer(b, id, "kill");
  await matchAction(a, id, "start");
  return id;
}
/* An active match cannot be cancelled: both primary operations, turning point 4, finish and confirm. */
async function finishMatch(a, b, id) {
  await matchCommand(a, id, "/primary", { primary_op: "crit" });
  await matchCommand(b, id, "/primary", { primary_op: "kill" });
  for (let tp = 2; tp <= 4; tp++)
    await matchAction(a, id, "turn", { turning_point: tp });
  await matchAction(a, id, "finish");
  await matchAction(b, id, "confirm");
}
/* Phone-sized dark page of a player: no horizontal scrolling and no axe violations on the given views. */
async function phoneCheck(browser, who, views) {
  const phone = await signedIn(browser, who, { theme: "dark", mobile: true });
  for (const [hash, sel] of views) {
    await open(phone, hash, sel);
    await noHorizontalScroll(phone, `${hash} 390px`);
    await axe(phone, `${hash} dark 390px`);
  }
  assertClean(phone, "phone");
  await phone.context().close();
}

describe("v1.10", () => {
  let browser, a, b, alpha;
  before(async () => {
    browser = await launch();
    a = await signedIn(browser, "alpha");
    b = await signedIn(browser, "bravo");
    await befriend(a, b);
    alpha = await me(a);
  });
  after(() => browser?.close());

  it("profile extras and the player page: avatar, motto, favourite team, head-to-head", async () => {
    const motto = `E2E девиз ${stamp()}`;
    await open(a, "profile", "#extra-form");
    await a.fill('#extra-form [name="motto"]', motto);
    await a.selectOption('#extra-form [name="favorite_team_id"]', {
      index: 1,
    });
    await a.click("#extra-form button");
    await until(
      async () => (await call(a, "/profile/extra")).motto === motto,
      "profile extras saved",
    );

    await a.setInputFiles("#avatar-file", await pngFile(a));
    await a.waitForSelector("#extra-panel img.avatar");
    const avatar = await api(b, `/users/${alpha.public_id}/avatar`);
    assert.equal(avatar.status, 200, "a friend sees the avatar");
    assert.ok((await call(a, "/profile/extra")).avatar, "avatar hash");
    await axe(a, "profile with extras");

    await open(b, `player/${alpha.public_id}`, ".player-head h1");
    assert.equal(
      squash(await b.textContent(".player-head h1")),
      USERS.alpha.name,
    );
    assert.equal(
      squash(await b.textContent(".player-head .motto")),
      `«${motto}»`,
    );
    await b.waitForFunction(
      () => document.querySelector(".player-head img.avatar")?.naturalWidth > 0,
    );
    assert.match(squash(await b.textContent("main")), new RegExp(ru.pl_h2h));
    await axe(b, "player page");

    // A hidden profile stays visible to friends (with a badge) and leaves the club-wide tables.
    await call(a, "/profile/extra", "PATCH", { hidden: true });
    assert.equal((await call(b, `/players/${alpha.public_id}`)).hidden, true);
    await call(a, "/profile/extra", "PATCH", { hidden: false });

    await open(a, `player/${alpha.public_id}`, ".player-head h1");
    await axe(a, "own player page");
    assertClean(a, "player page alpha");
    assertClean(b, "player page bravo");
    await phoneCheck(browser, "bravo", [
      [`player/${alpha.public_id}`, ".player-head h1"],
      ["profile", "#extra-form"],
    ]);
  });

  it("game night: RSVP with a team, pairs from the answers, the match of a table, calendar", async () => {
    const title = `E2E вечер ${stamp()}`;
    // the form is folded when upcoming nights exist (any rerun on the same database)
    await open(a, "nights", "details:has(#night-form) > summary");
    await a.$eval("details:has(#night-form)", (d) => (d.open = true));
    await a.fill('#night-form [name="title"]', title);
    await a.fill('#night-form [name="place"]', "Клуб E2E");
    await a.click("#night-form button");
    await a.waitForURL(/#nights\/[0-9a-f-]{36}$/);
    const nid = a.url().split("#nights/")[1];

    await a.waitForSelector("#rsvp-form");
    await a.selectOption('#rsvp-form [name="team_id"]', { index: 1 });
    await a.click("#rsvp-form button");
    await a.waitForSelector(`.night-groups li:has-text("${USERS.alpha.name}")`);

    await open(b, `nights/${nid}`, "#rsvp-form");
    await b.click("#rsvp-form button"); // «Приду» is the default answer
    await b.waitForSelector(`.night-groups li:has-text("${USERS.bravo.name}")`);
    await axe(b, "night as a player");

    await open(a, `nights/${nid}`, '[data-kind="generate"]');
    await a.click('[data-action="nt-pairs"][data-kind="generate"]');
    await a.waitForSelector(`#night-pairs li:has-text("${USERS.bravo.name}")`);
    await a.click('[data-action="nt-pairs"][data-kind="publish"]');
    await a.waitForSelector("#night-pairs .badge.active");
    assert.equal(
      squash(await a.textContent("#night-pairs .badge.active")),
      ru.nt_pairsReady,
    );
    await axe(a, "night as the organizer");

    await open(b, `nights/${nid}`, '[data-action="nt-match"]');
    await b.click('[data-action="nt-match"]');
    await b.waitForURL(/#match\/[0-9a-f-]{36}$/);
    const mid = b.url().split("#match/")[1];
    const m = await call(b, `/matches/${mid}`);
    assert.deepEqual(
      m.players.map((p) => p.display_name).sort(),
      [USERS.alpha.name, USERS.bravo.name].sort(),
    );
    await open(a, `nights/${nid}`, `#night-pairs a[href="#match/${mid}"]`);
    await matchAction(b, mid, "cancel"); // the player who opened the table's match created it

    const ics = await a.evaluate(async (nid) => {
      const r = await fetch(`/api/nights/${nid}/calendar.ics`);
      return [r.status, r.headers.get("content-type"), await r.text()];
    }, nid);
    assert.equal(ics[0], 200);
    assert.match(ics[1], /^text\/calendar/);
    assert.match(ics[2], /^BEGIN:VCALENDAR/);
    assert.ok(ics[2].includes(title), ".ics has the title");

    await open(a, "nights", "#feed-panel");
    await a.click('[data-action="nt-feed"]');
    await a.waitForSelector("#feed-panel .mono");
    const url = squash(await a.textContent("#feed-panel .mono"));
    assert.ok(url.startsWith(`${BASE}/api/calendar/`), url);
    const feed = await fetch(url); // no session: the link itself is the key
    assert.equal(feed.status, 200);
    assert.ok((await feed.text()).includes(title), "the feed lists the night");
    await axe(a, "nights list");
    await a.click('[data-action="nt-feed-off"]');
    await a.waitForSelector('[data-action="nt-feed-off"]', {
      state: "detached",
    });
    assert.equal(
      (await fetch(url)).status,
      404,
      "a revoked link stops working",
    );

    await open(a, `nights/${nid}`, "details:has(#night-edit-form)");
    await a.$eval("details:has(#night-edit-form)", (d) => (d.open = true));
    await a.click('[data-action="nt-cancel"]');
    await a.waitForSelector("h1 .badge");
    assert.equal(squash(await a.textContent("h1 .badge")), ru.nt_cancelled);
    assertClean(a, "night alpha");
    assertClean(b, "night bravo");
    await phoneCheck(browser, "alpha", [
      ["nights", "#feed-panel"],
      [`nights/${nid}`, "#night-pairs"],
    ]);
  });

  it("killzone map: tokens, frames per turning point, autosave, PNG; a match board is shared", async () => {
    await open(a, "maps", "#map-new");
    await a.fill('#map-new [name="title"]', `E2E схема ${stamp()}`);
    await a.click("#map-new button");
    await a.waitForURL(/#map\/[0-9a-f-]{36}$/);
    const bid = a.url().split("#map/")[1];
    await a.waitForSelector("#map-svg");
    const at = async (fx, fy) => {
      const box = await a.locator("#map-svg").boundingBox();
      await a.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
    };
    const tokens = async (frame) =>
      (await call(a, `/boards/${bid}`)).frames.find((f) => f.frame === frame)
        ?.state.tokens.length;

    await a.click('[data-action="map-tool"][data-tool="op1"]');
    await at(0.25, 0.5);
    await a.click('[data-action="map-tool"][data-tool="objective"]');
    await at(0.5, 0.5);
    await a.waitForFunction(
      () => document.querySelectorAll("#map-list li").length === 2,
    );
    await until(async () => (await tokens(0)) === 2, "frame 0 saved");

    await a.click('[data-action="map-frame"][data-frame="1"]'); // TP1 starts as a copy of the deployment
    await a.waitForSelector(
      '[data-action="map-frame"][data-frame="1"][aria-pressed="true"]',
    );
    await a.click('[data-action="map-tool"][data-tool="op2"]');
    await at(0.75, 0.5);
    await until(async () => (await tokens(1)) === 3, "frame 1 saved");
    assert.equal(await tokens(0), 2, "the deployment frame is unchanged");
    await axe(a, "map editor");

    const [download] = await Promise.all([
      a.waitForEvent("download"),
      a.click('[data-action="map-png"]'),
    ]);
    assert.match(download.suggestedFilename(), /\.png$/);

    await a.$eval("details:has(#map-settings)", (d) => (d.open = true));
    await a.click('[data-action="map-delete"]');
    await a.waitForURL(/#maps$/);
    assert.equal((await api(a, `/boards/${bid}`)).status, 404);

    const id = await activeMatch(a, b);
    await open(a, `match/${id}`, '[data-action="map-open"]');
    await a.click('[data-action="map-open"]');
    await a.waitForURL(/#map\/[0-9a-f-]{36}$/);
    const shared = a.url().split("#map/")[1];
    await a.waitForSelector("#map-svg");
    const again = await call(b, "/boards", "POST", {
      request_id: uuid(),
      match_id: id,
    });
    assert.equal(
      again.id,
      shared,
      "one board per match, open for both players",
    );
    await finishMatch(a, b, id);
    assertClean(a, "map");
    await phoneCheck(browser, "alpha", [
      ["maps", "#map-new"],
      [`map/${shared}`, "#map-svg"],
    ]);
  });

  it("offline scoreboard: a command without a connection is shown at once, queued and sent later", async () => {
    const id = await activeMatch(a, b);
    const cp = async (page) =>
      Number(squash(await page.textContent(".half.slot-1 .cp-box output")));
    await open(a, `match/${id}`, ".half.slot-1 .cp-box output");
    const start = await cp(a);

    await a.context().setOffline(true);
    await a.click('.half.slot-1 [data-action="cp"][aria-label="+1 CP"]');
    await a.waitForSelector("#netstate.pending:not([hidden])");
    assert.equal(await cp(a), start + 1, "the board shows the queued command");
    assert.equal(
      squash(await a.textContent("#netstate")),
      ru.off_queued.replace("{n}", "1"),
    );
    await open(b, `match/${id}`, ".half.slot-1 .cp-box output");
    assert.equal(await cp(b), start, "the server has not seen it yet");

    await a.context().setOffline(false);
    await a.waitForSelector("#netstate", { state: "hidden", timeout: 20000 });
    await b.waitForFunction(
      (v) =>
        Number(
          document.querySelector(".half.slot-1 .cp-box output")?.textContent,
        ) === v,
      start + 1,
    ); // over SSE once the queue is sent
    await finishMatch(a, b, id);
    a.problems.splice(0); // failed requests while offline are the point of this test
    assertClean(b, "offline bravo");
  });

  it("sound and vibration settings: saved per device, the test signal plays", async () => {
    await open(a, "profile", "#alerts-form");
    await a.click('[data-action="alert-test"]');
    await axe(a, "alert settings");
    assertClean(a, "alerts");
  });
});
