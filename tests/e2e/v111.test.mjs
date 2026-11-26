// v1.11: the rules reference (#reference): one search over the general rules, the KILLSTASS catalog and the
// imported teams, the query kept in the address, section filters, a team entry opened and highlighted on the
// team page, the offline search of the saved rules and Tac Ops, accessibility in both themes and at phone width.
// Sweep & Clear (migration 013) is always there; the weapon rules and the teams only after an import
// (scripts/update-reference.sh; E2E_RULES_BUNDLE / E2E_TEAMS_BUNDLE of scripts/e2e-docker.sh) — those checks
// are skipped without them. Account: e2e-alpha.
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
} from "./helpers.mjs";

const titles = (page) =>
  page.$$eval(".ref-hit h3", (h) => h.map((x) => x.textContent.trim()));
const badges = (page) =>
  page.$$eval(".ref-hit header .badge:first-child", (b) =>
    b.map((x) => x.textContent.trim()),
  );
/* Types a query and waits for the answer to it (the status line of the results is redrawn). */
async function search(page, q) {
  await page.evaluate(() => {
    const s = document.querySelector("#ref-results [role=status]");
    if (s) s.dataset.old = "1";
  });
  await page.fill("#ref-q", q);
  await page.waitForSelector("#ref-results [role=status]:not([data-old])");
}

/* Opens the reference page and waits for its new form. After a change of the hash the previous page
   stays on screen until the library is loaded, and a query typed into it would be lost (v1.12: seen
   once in a full run with the team reference loaded). */
async function openReference(page) {
  await page.evaluate(() =>
    document.querySelector("#ref-form")?.setAttribute("data-old", ""),
  );
  await open(page, "reference", "#ref-form:not([data-old]) #ref-q");
}

describe("rules reference", () => {
  let browser, a, lib;
  before(async () => {
    browser = await launch();
    a = await signedIn(browser, "alpha");
    lib = await call(a, "/reference/library");
  });
  after(async () => {
    await browser?.close();
  });

  it("lists the general rules or explains how to load them", async () => {
    await openReference(a);
    assert.match(
      squash(await a.textContent(".ref-status")),
      new RegExp(ru.ref_actual),
    );
    if (lib.rules.length) {
      await a.waitForSelector(".ref-rule");
      const names = await a.$$eval(".ref-rule h3", (h) =>
        h.map((x) => x.textContent.trim()),
      );
      assert.ok(names.includes(lib.rules[0].name), "first rule listed");
      assert.equal(names.length, lib.rules.length);
    } else {
      assert.match(
        squash(await a.textContent("#ref-results")),
        new RegExp(ru.ref_noRulesTitle),
      );
    }
    await axe(a, "reference light");
    assertClean(a, "reference browse");
  });

  it("finds Sweep & Clear by either name, keeps the query in the address and filters by section", async () => {
    await openReference(a);
    await search(a, "Sweep");
    await a.waitForFunction(() => location.hash === "#reference/Sweep");
    assert.equal((await titles(a))[0], "Зачистка");
    assert.equal((await badges(a))[0], ru.rk_tac_op);
    await axe(a, "reference results light");
    assert.match(
      squash(await a.textContent(".ref-hit")),
      /Sweep & Clear.*swept/,
    );
    await a.reload(); // the address restores the search
    await a.waitForSelector(".ref-hit");
    assert.equal(await a.inputValue("#ref-q"), "Sweep");
    assert.equal((await titles(a))[0], "Зачистка");

    await a.check('.ref-kinds input[value="ops"]');
    await search(a, "зачистка");
    const kinds = await badges(a);
    assert.ok(kinds.length >= 1);
    for (const k of kinds)
      assert.ok([ru.rk_tac_op, ru.rk_mission].includes(k), k);
    await a.check('.ref-kinds input[value=""]');
    assertClean(a, "reference search");
  });

  it("finds a weapon rule by its Russian name and by the players' word for it", async (t) => {
    if (!lib.rules.some((r) => r.code === "weapon-lethal-x"))
      return t.skip("no weapon rules loaded (scripts/update-reference.sh)");
    await openReference(a);
    for (const q of ["Lethal", "смертоносное", "летал"]) {
      await search(a, q);
      assert.equal((await titles(a))[0], "Lethal x+", q);
    }
    assert.equal((await badges(a))[0], ru.rk_weapon_rule);
    assertClean(a, "reference weapon rule");
  });

  it("opens a team entry highlighted on the team page", async (t) => {
    await openReference(a);
    await a.check('.ref-kinds input[value="operatives"]');
    await search(a, "leader");
    const link = a.locator(".ref-hit a.button").first();
    if (!(await link.count()))
      return t.skip("no team data loaded (scripts/update-reference.sh)");
    const href = await link.getAttribute("href");
    assert.match(href, /^#teams\/[a-z0-9-]+\/operatives\/op-\d+$/);
    await link.click();
    await a.waitForFunction((h) => location.hash === h, href);
    const target = a.locator(".ref-target");
    await target.waitFor();
    assert.equal(
      await target.getAttribute("id"),
      "ref-" + href.split("/").pop(),
    );
    const box = await target.boundingBox();
    assert.ok(box && box.y < 900 && box.y + box.height > 0, "in view");
    assertClean(a, "reference team entry");
  });

  it("searches the saved rules and Tac Ops without a connection", async () => {
    await openReference(a);
    await a.context().setOffline(true);
    try {
      await search(a, "зачистка");
      assert.equal(
        squash(await a.textContent("#ref-results .warning")),
        ru.ref_offline,
      );
      assert.equal((await titles(a))[0], "Зачистка");
      if (lib.rules.some((r) => r.code === "weapon-lethal-x")) {
        await search(a, "летал");
        assert.equal((await titles(a))[0], "Lethal x+");
      }
    } finally {
      await a.context().setOffline(false);
    }
    a.problems.splice(0); // failed requests while offline are expected
  });

  it("fits a phone and passes axe in the dark theme", async () => {
    const phone = await signedIn(browser, "alpha", {
      theme: "dark",
      mobile: true,
    });
    await open(phone, "reference/Sweep", ".ref-hit");
    await noHorizontalScroll(phone, "reference 390px");
    await axe(phone, "reference dark 390px");
    // v1.12: the reference is opened from the «Rules» menu item
    const label = phone.locator('a.nav-link[href="#rules"] .nav-label');
    const [sw, cw] = await label.evaluate((x) => [
      x.scrollWidth,
      x.clientWidth,
    ]);
    assert.ok(sw <= cw, `the menu label is cut: ${sw} > ${cw}`);
    assertClean(phone, "reference phone");
    await phone.context().close();
  });
});
