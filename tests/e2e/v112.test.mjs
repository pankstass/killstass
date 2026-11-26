// v1.12: the «Rules» section (one menu item for Quick Reference, Core Rules and Faction Rules), the Core Rules
// reference (#core: contents, a Russian term finds the English text, the hit highlighted, back to the results,
// a section by address, reading without a connection) and ready-made Volkus terrain on the killzone map (new
// board, the other drop zone, no terrain); accessibility in both themes and at phone width. Account: e2e-alpha.
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
} from "./helpers.mjs";

const hrefs = (page, sel) =>
  page.$$eval(sel, (l) => l.map((x) => x.getAttribute("href")));
/* v1.14: the menu group «Rules» is the current page on #rules and the current group on its sections. */
const current = (page) =>
  page.getAttribute('a.nav-link[data-group="rules"]', "aria-current");

describe("v1.12", () => {
  let browser, a;
  before(async () => {
    browser = await launch();
    a = await signedIn(browser, "alpha");
  });
  after(async () => {
    await browser?.close();
  });

  it("one menu item opens the three rules references", async () => {
    await open(a, "rules", ".rules-hub");
    const menu = await hrefs(a, "a.nav-link[data-group]");
    assert.ok(menu.includes("#rules"), menu.join(" "));
    assert.ok(!menu.includes("#reference") && !menu.includes("#teams"));
    // v1.14: the open group lists its sections below the group item
    assert.deepEqual(await hrefs(a, "a.nav-subitem"), [
      "#reference",
      "#core",
      "#teams",
    ]);
    assert.deepEqual(await hrefs(a, ".rules-hub a"), [
      "#reference",
      "#core",
      "#teams",
    ]);
    assert.equal(await current(a), "page");
    await axe(a, "rules light");
    for (const [href, sel] of [
      ["#reference", "#ref-q"],
      ["#core", "#core-q"],
      ["#teams", ".team-header h1"],
    ]) {
      await open(a, "rules", ".rules-hub");
      await a.click(`.rules-hub a[href="${href}"]`);
      await a.waitForSelector(sel);
      assert.equal(await current(a), "true", href);
      assert.equal(
        await a.getAttribute(`a.nav-subitem[href="${href}"]`, "aria-current"),
        "page",
        href,
      );
    }
    assert.equal(
      squash(await a.textContent(".team-header h1")),
      ru.rules_faction,
    );
    await a.click(".team-header a.back");
    await a.waitForSelector(".rules-hub");
    assertClean(a, "rules hub");
  });

  it("core rules: a Russian term finds the English rule, the hit is highlighted", async () => {
    const doc = await call(a, "/reference/core-rules");
    await open(a, "core", ".cr-toc");
    assert.equal(
      await a.$$eval(".cr-chapter", (c) => c.length),
      doc.chapters.length,
    );
    await a.fill("#core-q", "укрытие");
    await a.waitForSelector(".cr-hit");
    assert.equal(
      decodeURIComponent(a.url().split("#")[1]),
      "core/search/укрытие",
      "the query is kept in the address",
    );
    const sections = await hrefs(a, ".cr-hit h3 a");
    assert.ok(sections.includes("#core/cover"), sections.join(" "));
    await a.click('.cr-hit h3 a[href="#core/cover"]');
    await a.waitForSelector("#cr-cover");
    await a.waitForFunction(() => document.activeElement?.id === "cr-cover");
    assert.ok(
      (await a.$$eval("#cr-cover mark", (m) => m.length)) > 0,
      "the found term is marked",
    );
    assert.equal(
      await a.getAttribute('.cr-side a[data-cr-sec="cover"]', "href"),
      "#core/cover",
    );
    await a.click(".cr-head a.back");
    await a.waitForSelector(".cr-hit");
    assert.equal(await a.inputValue("#core-q"), "укрытие");
    await axe(a, "core results");

    await a.fill("#core-q", "zzqx");
    await a.waitForSelector("#core-results .empty");
    await a.fill("#core-q", "");
    await a.waitForSelector(".cr-toc");
    assert.equal(a.url().split("#")[1], "core");
    assertClean(a, "core search");
  });

  it("core rules: a section by address, current text without marks, no connection", async () => {
    await open(a, "core/volkus", "#cr-volkus");
    await a.waitForFunction(() => document.activeElement?.id === "cr-volkus");
    assert.match(squash(await a.textContent(".cr-head h1")), /Killzones/);
    assert.ok((await a.$$eval(".cr-section", (s) => s.length)) > 3);
    await axe(a, "core chapter");
    await open(a, "core/principles", ".cr-text");
    // v1.13: only the current rules — no «updated» marks, no book wording, no PDF pages
    assert.equal(
      await a.$$eval(
        ".cr-updated, .cr-upd, .cr-book, .cr-page",
        (l) => l.length,
      ),
      0,
    );
    await a.context().setOffline(true);
    try {
      // the text is already in the page: chapters open without the server
      await a.click('.cr-pager a[href="#core/killzones"]');
      await a.waitForSelector("#cr-volkus");
      await a.click('.cr-pager a[href="#core"]');
      await a.waitForSelector(".cr-toc");
    } finally {
      await a.context().setOffline(false);
    }
    a.problems.splice(0);
  });

  it("killzone map: ready-made Volkus terrain, the other drop zone, no terrain", async () => {
    await open(a, "maps", "#map-new");
    const layouts = await a.$$eval('#map-new [name="layout"] option', (o) =>
      o.map((x) => x.value),
    );
    assert.ok(layouts.length >= 8 && layouts[0] === "", layouts.join(" "));
    await a.selectOption('#map-new [name="layout"]', "volkus-2025-4");
    assert.ok(await a.isDisabled('#map-new [name="width"]'));
    await a.selectOption('#map-new [name="layout"]', "");
    assert.ok(!(await a.isDisabled('#map-new [name="width"]')));
    await a.selectOption('#map-new [name="layout"]', "volkus-2025-4");
    await a.fill('#map-new [name="title"]', `E2E Volkus ${Date.now()}`);
    await a.click("#map-new button");
    await a.waitForURL(/#map\/[0-9a-f-]{36}$/);
    const bid = a.url().split("#map/")[1];
    await a.waitForSelector("#map-svg g.kz");
    const board = () => call(a, `/boards/${bid}`);
    const b = await board();
    assert.deepEqual(
      [b.layout, b.swap, b.width, b.height],
      ["volkus-2025-4", false, 30, 22],
    );
    assert.equal(await a.$$eval("#map-svg .kz-obj", (o) => o.length), 3);
    assert.match(
      squash(await a.textContent(".kz-legend summary")),
      new RegExp(ru.kz_legend),
    );
    await axe(a, "map with terrain");

    const settings = () =>
      a.$eval("details:has(#map-settings)", (d) => (d.open = true));
    await settings();
    assert.ok(await a.isVisible('#map-settings [name="swap"]'));
    await a.check('#map-settings [name="swap"]');
    await a.click("#map-settings button");
    await until(async () => (await board()).swap === true, "swap saved");

    await settings();
    await a.selectOption('#map-settings [name="layout"]', "");
    assert.ok(await a.isHidden('#map-settings [name="swap"]'));
    assert.ok(!(await a.isDisabled('#map-settings [name="width"]')));
    await a.click("#map-settings button");
    await until(async () => (await board()).layout === null, "no terrain");
    await a.waitForSelector("#map-svg g.kz", { state: "detached" });
    assert.equal(await a.$(".kz-legend"), null);

    await settings();
    await a.click('[data-action="map-delete"]');
    await a.waitForURL(/#maps$/);
    assertClean(a, "map terrain");
  });

  it("fits a phone and passes axe in the dark theme", async () => {
    const phone = await signedIn(browser, "alpha", {
      theme: "dark",
      mobile: true,
    });
    const { id } = await call(phone, "/boards", "POST", {
      request_id: uuid(),
      title: "E2E Volkus phone",
      layout: "volkus-example-3",
    });
    for (const [hash, sel] of [
      ["rules", ".rules-hub"],
      ["core", ".cr-toc"],
      ["core/search/obscured", ".cr-hit"],
      ["core/killzones", "#cr-volkus"],
      [`map/${id}`, "#map-svg g.kz"],
    ]) {
      await open(phone, hash, sel);
      await noHorizontalScroll(phone, `${hash} 390px`);
      await axe(phone, `${hash} dark 390px`);
    }
    const label = phone.locator('a.nav-link[href="#rules"] .nav-label');
    const [sw, cw] = await label.evaluate((x) => [
      x.scrollWidth,
      x.clientWidth,
    ]);
    assert.ok(sw <= cw, `the menu label is cut: ${sw} > ${cw}`);
    await call(phone, `/boards/${id}`, "DELETE", {});
    assertClean(phone, "v1.12 phone");
    await phone.context().close();
  });
});
