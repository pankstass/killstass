// v1.13: tooltips of game terms and weapon rules (core rules, datacards: hover, focus, Escape, tap), the weapon
// rules of the attack calculator as buttons and the universal grenades, the operative count of the match setup
// (roster → team → typed in by choice), conceding (a hot-seat match at once, a friend match after the opponent's
// confirmation, 10:0), local players (the opponent field, the club rating) — accessibility in both themes and at
// phone width. Accounts: e2e-alpha, e2e-bravo (the administrator part is in admin.test.mjs).
import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import {
  ru,
  launch,
  signedIn,
  open,
  axe,
  assertClean,
  noHorizontalScroll,
  squash,
  call,
  until,
  uuid,
  matchAction,
  matchCommand,
  catalogId,
  setupPlayer,
} from "./helpers.mjs";

const stamp = () => String(Date.now()).slice(-6);
const tipShown = (page) => page.waitForSelector("#term-tip:not([hidden])");
const tipHidden = (page) =>
  page.waitForSelector("#term-tip", { state: "hidden" });
/* A started hot-seat match of alpha against a guest (both counts typed in: the thresholds need 5..14). */
async function hotseat(a, guest = "Гость", extra = {}) {
  const { id } = await call(a, "/matches", "POST", {
    request_id: uuid(),
    kind: "hotseat",
    guest_name: guest,
    ...extra,
  });
  await setupPlayer(a, id, "crit");
  await matchCommand(
    a,
    id,
    "/player-setup",
    {
      slot: 2,
      operative_count: 6,
      operative_manual: true,
      tac_op_id: await catalogId(a, "tac_op", "tac-op-rout"),
      primary_op: "kill",
    },
    "PUT",
  );
  await matchAction(a, id, "start");
  return id;
}

describe("v1.13", () => {
  let browser, a, b;
  before(async () => {
    browser = await launch();
    a = await signedIn(browser, "alpha");
    b = await signedIn(browser, "bravo");
  });
  after(async () => {
    await browser?.close();
  });

  it("tooltips: game terms of the core rules open on hover and focus, close with Escape", async () => {
    await open(a, "core/shoot", '#cr-shoot .term[data-term="valid-target"]');
    const term = a.locator('#cr-shoot .term[data-term="valid-target"]').first();
    assert.equal(await term.getAttribute("role"), "button");
    assert.equal(await term.getAttribute("tabindex"), "0");
    await term.hover();
    await tipShown(a);
    const text = squash(await a.textContent("#term-tip"));
    assert.ok(
      text.includes("Valid target") && text.includes("Допустимая цель"),
      text,
    );
    assert.ok(text.includes(ru.term_kind_term), text);
    assert.equal(await term.getAttribute("aria-describedby"), "term-tip");
    assert.equal(await a.getAttribute("#term-tip", "role"), "tooltip");
    await axe(a, "core rules tooltip");
    await a.mouse.move(5, 5);
    await tipHidden(a);
    await term.focus();
    await tipShown(a);
    await a.keyboard.press("Escape");
    await tipHidden(a);
    assert.equal(await term.getAttribute("aria-describedby"), null);
    // Enter pins it; a click elsewhere closes it.
    await term.focus();
    await a.keyboard.press("Enter");
    await a.waitForSelector("#term-tip.pinned:not([hidden])");
    await a.click("h1");
    await tipHidden(a);
    // A section does not explain its own terms; the first mention in a block only.
    const ids = await a.$$eval("#cr-shoot p", (ps) =>
      ps.map((p) =>
        [...p.querySelectorAll(".term")].map((x) => x.dataset.term),
      ),
    );
    for (const list of ids)
      assert.equal(new Set(list).size, list.length, list.join(" "));
    assertClean(a, "core rules tooltips");
  });

  it("tooltips: every weapon rule of a datacard, the imported text unchanged", async () => {
    const { teams } = await call(a, "/teams");
    const slug = teams.some((x) => x.slug === "kasrkin")
      ? "kasrkin"
      : teams[0].slug;
    const team = await call(a, "/teams/" + slug);
    await open(a, "teams/" + slug, ".dc-weapons small .term");
    const shown = await a.$$eval(".dc-weapons small", (l) =>
      l.map((x) => x.textContent.trim()).filter(Boolean),
    );
    const imported = team.data.operatives
      .flatMap((o) => o.weapons || [])
      .map((w) => (w.wr || "").trim())
      .filter((x) => x && x !== "-");
    for (const s of shown.slice(0, 20))
      assert.ok(imported.includes(s), `«${s}» is the imported text`);
    const wr = a
      .locator('.dc-weapons small .term[data-term^="weapon-"]')
      .first();
    await wr.hover();
    await tipShown(a);
    assert.ok(
      squash(await a.textContent("#term-tip")).includes(ru.term_kind_weapon),
    );
    await axe(a, "datacard tooltip");
    assertClean(a, "datacard tooltips");
  });

  it("tooltips on a phone (dark): a tap opens one inside the screen, a tap elsewhere closes it", async () => {
    const page = await signedIn(browser, "alpha", {
      theme: "dark",
      mobile: true,
    });
    await open(page, "core/obscured", "#cr-obscured .term");
    const term = page.locator("#cr-obscured .term").last();
    await term.scrollIntoViewIfNeeded();
    await term.click();
    await page.waitForSelector("#term-tip.pinned:not([hidden])");
    const box = await page.locator("#term-tip").boundingBox();
    assert.ok(box.x >= 0 && box.x + box.width <= 390, JSON.stringify(box));
    await noHorizontalScroll(page, "phone tooltip");
    await axe(page, "phone tooltip dark");
    await page.click("h1");
    await tipHidden(page);
    assertClean(page, "phone tooltips");
    await page.context().close();
  });

  it("attack calculator: weapon rules as buttons, universal grenades", async () => {
    const page = await signedIn(browser, "alpha", { mobile: true });
    await open(page, "demo", '[data-action="score"]');
    await page.click("#board-menu summary");
    await page.click('#board-menu [data-panel="attack"]');
    await page.waitForSelector("#board-sheet .atk-wr");
    const mean = () => page.textContent("#attack-result .atk-stats dd");
    const before = await mean();
    const lethal = '#board-sheet button.chip[data-rule="lethal"]:not([data-v])';
    assert.equal(await page.getAttribute(lethal, "aria-pressed"), "false");
    await page.click(lethal);
    await page.waitForSelector(`${lethal}[aria-pressed="true"]`);
    assert.equal(
      await page.evaluate(() => document.activeElement?.dataset?.rule),
      "lethal",
      "the focus stays on the pressed button",
    );
    await page.click(
      '#board-sheet button.chip[data-rule="lethal"][data-v="4"]',
    );
    await page.waitForSelector(
      '#board-sheet button.chip[data-rule="lethal"][data-v="4"][aria-pressed="true"]',
    );
    assert.notEqual(await mean(), before);
    const groups = await page.$$eval(
      '#board-sheet select[name="weapon"] optgroup',
      (l) => l.map((g) => g.label),
    );
    assert.ok(groups.includes(ru.atkGrenades), groups.join(" "));
    await page.selectOption('#board-sheet select[name="weapon"]', "g:frag");
    await until(
      async () =>
        (await page.inputValue('#board-sheet [name="dmg"]')) === "2/4",
      "frag grenade profile",
    );
    assert.equal(await page.inputValue('#board-sheet [name="atk"]'), "4");
    assert.equal(await page.inputValue('#board-sheet [name="hit"]'), "4+");
    assert.equal(
      await page.getAttribute(
        '#board-sheet button.chip[data-rule="saturate"]',
        "aria-pressed",
      ),
      "true",
    );
    const info = await page.$$eval("#board-sheet .atk-wr-other .chip", (l) =>
      l.map((x) => x.textContent.trim()),
    );
    assert.deepEqual(info, ['Range 6"', 'Blast 2"']);
    await page.selectOption('#board-sheet select[name="weapon"]', "g:krak");
    await page.waitForSelector(
      '#board-sheet button.chip[data-rule="piercing"][data-v="1"][aria-pressed="true"]',
    );
    assert.equal(await page.inputValue('#board-sheet [name="dmg"]'), "4/5");
    await page.selectOption('#board-sheet select[name="type"]', "melee");
    await page.waitForSelector(
      '#board-sheet button.chip[data-rule="saturate"]:disabled',
    );
    await axe(page, "attack calculator chips");
    await noHorizontalScroll(page, "attack calculator");
    assertClean(page, "attack calculator");
    await page.context().close();
  });

  it("match setup: the operative count from the team, typed in only by choice", async () => {
    const { teams } = await call(a, "/teams");
    const sized = teams.find((x) => x.team_size && x.catalog_id);
    const unsized = teams.find((x) => !x.team_size && x.catalog_id);
    assert.ok(sized, "a team with a known composition");
    const { id } = await call(a, "/matches", "POST", {
      request_id: uuid(),
      kind: "hotseat",
      guest_name: "Гость",
    });
    await open(a, "match/" + id, "#setup-form [data-op-count]");
    const box = "#setup-form [data-op-count]";
    await a.selectOption(
      '#setup-form select[name="team1_id"]',
      String(sized.catalog_id),
    );
    await until(
      async () =>
        squash(await a.textContent(box)).includes(String(sized.team_size)),
      "count from the team",
    );
    assert.equal(await a.$(`${box} input[type="number"]`), null);
    await a.click(`${box} [data-action="op-count-edit"]`);
    assert.equal(
      await a.evaluate(() => document.activeElement?.name),
      "operative_count",
    );
    await a.fill(`${box} input[name="operative_count"]`, "9");
    await axe(a, "typed count");
    await a.click(`${box} [data-action="op-count-auto"]`);
    await a.waitForSelector(`${box} [data-action="op-count-edit"]`);
    if (unsized) {
      await a.selectOption(
        '#setup-form select[name="team1_id"]',
        String(unsized.catalog_id),
      );
      await a.waitForSelector(`${box} input[type="number"]`);
      assert.ok(squash(await a.textContent(box)).includes(ru.opCountNone));
      await a.selectOption(
        '#setup-form select[name="team1_id"]',
        String(sized.catalog_id),
      );
      await a.waitForSelector(`${box} [data-action="op-count-edit"]`);
    }
    await a.click("#setup-form > button");
    await until(async () => {
      const m = await call(a, "/matches/" + id);
      return (
        m.players[0].operative_source === "team" &&
        m.players[0].operative_count === sized.team_size
      );
    }, "the server stores the team's count");
    assertClean(a, "operative count");
  });

  it("conceding a hot-seat match: either player, at once, 10:0", async () => {
    const id = await hotseat(a, "Гость сдачи " + stamp());
    await open(a, "match/" + id, '[data-action="score"]');
    await a.click("#board-menu summary");
    await a.click('#board-menu [data-panel="concede"]');
    await a.waitForSelector('#board-sheet [data-kind="concede"]');
    assert.deepEqual(
      await a.$$eval('#board-sheet [data-kind="concede"]', (l) =>
        l.map((x) => x.dataset.slot),
      ),
      ["1", "2"],
    );
    await axe(a, "concede sheet");
    await a.click('#board-sheet [data-kind="concede"][data-slot="2"]');
    await a.waitForSelector(".result-panel .concede-note");
    const m = await call(a, "/matches/" + id);
    assert.deepEqual(
      [m.status, m.conceded_slot, m.players.map((p) => p.vp)],
      ["unconfirmed", 2, [10, 0]],
    );
    await axe(a, "conceded hot-seat");
    assertClean(a, "concede hot-seat");
  });

  it("conceding a friend match: the opponent confirms, 10:0", async () => {
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
    await open(b, "match/" + id, '[data-action="score"]');
    await b.click("#board-menu summary");
    await b.click('#board-menu [data-panel="concede"]');
    await b.waitForSelector('#board-sheet [data-kind="concede"]');
    assert.equal(
      await b.$$eval('#board-sheet [data-kind="concede"]', (l) => l.length),
      1,
    );
    await b.click('#board-sheet [data-kind="concede"]');
    await b.waitForSelector(".result-panel .concede-note");
    assert.ok(
      squash(await b.textContent(".result-panel")).includes(ru.waiting),
    );
    await open(a, "match/" + id, ".result-panel .concede-note");
    await a.click('.result-panel [data-kind="confirm"]');
    await until(
      async () => (await call(a, "/matches/" + id)).status === "confirmed",
      "confirmed",
    );
    const m = await call(a, "/matches/" + id);
    assert.deepEqual(
      [m.conceded_slot, m.players.map((p) => p.vp)],
      [2, [10, 0]],
    );
    assertClean(a, "concede friend");
    assertClean(b, "concede friend (bravo)");
  });

  it("local players: the opponent field suggests them, the club rating lists them", async () => {
    const name = "Локальный Е2Е " + stamp();
    const { id } = await call(a, "/quick-matches", "POST", {
      request_id: uuid(),
      guest_name: name,
      local: true,
      edition: "2024",
      team1_id: await catalogId(a, "team", "team-angel-of-death"),
      team2_id: await catalogId(a, "team", "team-kommandos"),
      mission_id: await catalogId(a, "mission", "mission-secure"),
      killzone_id: await catalogId(a, "killzone", "volkus-1"),
      vp_for: 14,
      vp_against: 9,
      played_at: new Date().toISOString(),
    });
    assert.ok(id);
    await open(a, "new", "#new-match-form");
    await until(
      async () =>
        (
          await a.$$eval("#local-players option", (l) => l.map((o) => o.value))
        ).includes(name),
      "the name in the suggestions",
    );
    const field = '#new-match-form input[name="guest_name"]';
    await a.fill(field, name.toLowerCase());
    assert.ok(
      await a.isChecked('#new-match-form input[name="local"]'),
      "a known name ticks the box",
    );
    await a.fill(field, "Разовый гость");
    assert.ok(!(await a.isChecked('#new-match-form input[name="local"]')));
    await axe(a, "hot-seat form");
    await open(a, "stats", "#ratings-panel");
    await a.click('#ratings-panel [data-scope="all"]');
    await a.waitForSelector(
      '#ratings-panel [data-scope="all"][aria-pressed="true"]',
    );
    const row = a.locator("#ratings-panel tbody tr", { hasText: name });
    await row.waitFor();
    assert.ok(squash(await row.textContent()).includes(ru.localBadge));
    assert.equal(
      await row.locator("a").count(),
      0,
      "no player page for a local player",
    );
    await axe(a, "club rating");
    await open(a, "stats", "#ratings-panel");
    assert.equal(
      await a.getAttribute('#ratings-panel [data-scope="all"]', "aria-pressed"),
      "true",
      "the choice is remembered",
    );
    await a.click('#ratings-panel [data-scope="friends"]');
    await a.waitForSelector(
      '#ratings-panel [data-scope="friends"][aria-pressed="true"]',
    );
    assert.ok(!squash(await a.textContent("#ratings-panel")).includes(name));
    assertClean(a, "local players");
  });
});
