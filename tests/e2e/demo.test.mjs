// v1.9: pages that work without an account, in a real browser: sign-in screen, demo board
// (nothing is saved on the server) and the component style guide (#styleguide).
import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import {
  launch,
  newPage,
  open,
  axe,
  assertClean,
  noHorizontalScroll,
  notice,
  squash,
  ru,
} from "./helpers.mjs";

describe("without an account", () => {
  let browser;
  before(async () => {
    browser = await launch();
  });
  after(() => browser?.close());

  it("sign-in screen: accessible in both themes, fits a phone, reports a wrong password", async () => {
    for (const theme of ["light", "dark"]) {
      const page = await newPage(browser, { theme, mobile: true });
      await open(page, "overview", "#auth-form");
      assert.equal(
        await page.evaluate(() => document.documentElement.dataset.theme),
        theme,
      );
      await noHorizontalScroll(page, `auth ${theme}`);
      await axe(page, `auth ${theme}`);
      await page.click('[data-action="show-register"]');
      await page.waitForSelector('#auth-form[data-register="true"]');
      await axe(page, `register ${theme}`);
      if (theme === "dark") {
        await page.click('[data-action="show-login"]');
        await page.fill('#auth-form [name="identity"]', "e2e-nobody");
        await page.fill('#auth-form [name="password"]', "wrong-password-123");
        const [res] = await Promise.all([
          page.waitForResponse((r) => r.url().endsWith("/api/auth/login")),
          page.click("#auth-form button:not([type=button])"),
        ]);
        assert.equal(res.status(), 401);
        await page.waitForFunction(
          () => !document.querySelector("#notice").hidden,
        );
        assert.equal(await notice(page), ru.errors.invalid_credentials);
      }
      assertClean(page, `auth ${theme}`);
      await page.context().close();
    }
  });

  it("demo board: score, CP, operatives with automatic kills, undo, attack calculator, finish and reset", async () => {
    const page = await newPage(browser);
    const text = async (sel) => squash(await page.textContent(sel));
    const kills = (slot) => text(`.half.slot-${slot} .kill-num output`);
    await open(page, "demo", '[data-action="score"]');
    assert.equal(await text(".board-score"), "0–0");
    await axe(page, "demo");

    await page.click('[data-action="score"][data-slot="1"][data-delta="1"]');
    assert.equal(await text(".board-score"), "1–0");
    const cp = () => text('.half.slot-2 .cp-box output[aria-label="CP"]');
    const cp0 = Number(await cp());
    await page.click('[data-action="cp"][data-slot="2"][data-value="1"]');
    assert.equal(Number(await cp()), cp0 + 1);

    // operative of player 2: the skull incapacitates it and counts a kill for player 1
    await page.click(".half.slot-2 .op-add summary");
    await page.fill('.half.slot-2 .op-add-form [name="name"]', "Гретчин");
    await page.fill('.half.slot-2 .op-add-form [name="wounds_max"]', "7");
    await page.click(".half.slot-2 .op-add-form button");
    await page.waitForSelector(".half.slot-2 li.op");
    assert.match(await text(".half.slot-2 li.op .op-w"), /7\/7/);
    assert.equal(await kills(1), "0");
    await page.click(".half.slot-2 li.op .op-down");
    await page.waitForSelector(".half.slot-2 li.op.down");
    assert.equal(await kills(1), "1");
    await axe(page, "demo with an incapacitated operative");

    await page.click('[data-action="undo"]');
    await page.waitForSelector(".half.slot-2 li.op:not(.down)");
    assert.equal(await kills(1), "0");
    assert.equal(
      await text(".board-score"),
      "1–0",
      "undo reverts only the last step",
    );

    // attack calculator: the roll shows attack and defence dice
    await page.click("#board-menu summary");
    await page.click('#board-menu [data-panel="attack"]');
    await page.waitForSelector('#board-sheet [data-action="attack-roll"]');
    await page.click('#board-sheet [data-action="attack-roll"]');
    await page.waitForSelector("#board-sheet .atk-roll .die");
    assert.ok((await page.$$("#board-sheet .atk-roll .die")).length >= 4);
    await axe(page, "demo attack calculator");

    // tabletop mode is remembered on this device
    await page.click("#board-menu summary");
    await page.click('#board-menu [data-action="tabletop"]');
    await page.waitForSelector(".board.tabletop");
    assert.equal(
      await page.evaluate(() => localStorage.getItem("killstass-tabletop")),
      "1",
    );
    await page.click("#board-menu summary");
    await page.click('#board-menu [data-action="tabletop"]');
    await page.waitForSelector(".board:not(.tabletop)");

    // turning point 4 → final count → finish → result table → reset
    await page.click('[data-action="turn"][data-value="4"]');
    await page.click(
      '[data-action="board-panel"][data-panel="finish"] >> nth=0',
    );
    await page.click('#board-sheet [data-action="preview"]');
    await page.click('#board-sheet [data-action="match-action"]');
    await page.waitForSelector(".demo-final");
    assert.match(await text(".demo-final"), new RegExp(ru.demoFinished));
    await axe(page, "demo final");
    await page.click('[data-action="demo-reset"]');
    await page.waitForFunction(() => !document.querySelector(".demo-final"));
    assert.equal(await text(".board-score"), "0–0");
    assert.equal(await page.$$eval("li.op", (l) => l.length), 0);
    assertClean(page, "demo");
    await page.context().close();
  });

  it("demo on a phone in the dark theme: no horizontal scroll, accessible", async () => {
    const page = await newPage(browser, { theme: "dark", mobile: true });
    await open(page, "demo", '[data-action="score"]');
    await noHorizontalScroll(page, "demo 390px");
    await axe(page, "demo dark 390px");
    assertClean(page, "demo mobile");
    await page.context().close();
  });

  it("style guide renders every component and passes axe in both themes", async () => {
    for (const theme of ["light", "dark"]) {
      const page = await newPage(browser, { theme });
      await open(page, "styleguide", ".sg-qr svg");
      const sections = [
        "colors",
        "type",
        "buttons",
        "badges",
        "forms",
        "icons",
        "emblems",
        "board",
        "cards",
        "print",
      ];
      for (const id of sections)
        assert.ok(await page.$(`#sg-${id}`), `style guide section ${id}`);
      assert.equal(
        await page.$$eval(".sg-nav a[data-sg]", (l) => l.length),
        sections.length,
      );
      for (const sel of [
        ".sg-board .half",
        ".datacards",
        ".sg-emblems svg",
        ".sg-icons svg",
      ])
        assert.ok(await page.$(sel), `style guide shows ${sel}`);
      await axe(page, `styleguide ${theme}`);
      if (theme === "light") {
        // printing: only #print-root is shown on paper while body.printing is set
        await page.evaluate(() => {
          window.print = () => (window.__printed = (window.__printed || 0) + 1);
        });
        await page.click('[data-action="sg-print"]');
        await page.waitForFunction(() => window.__printed === 1);
        assert.ok(
          await page.$("body.printing #print-root .roster-sheet .datacards"),
        );
        await page.emulateMedia({ media: "print" });
        const shown = await page.evaluate(() =>
          [...document.body.children]
            .filter((e) => getComputedStyle(e).display !== "none")
            .map((e) => e.id),
        );
        assert.deepEqual(shown, ["print-root"]);
        await page.emulateMedia({ media: "screen" });
        await page.evaluate(() =>
          window.dispatchEvent(new Event("afterprint")),
        );
        assert.equal(await page.$("body.printing"), null);
      }
      assertClean(page, `styleguide ${theme}`);
      await page.context().close();
    }
  });
});
