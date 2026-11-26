// A cold deep link to an unavailable match should render a usable shell.
import { test } from "node:test";
import assert from "node:assert/strict";
import { launch, signedIn, BASE } from "./helpers.mjs";

test("an unavailable match shows an error and a link to the headquarters", async () => {
  const browser = await launch();
  try {
    const page = await signedIn(browser, "alpha");
    await page.goto(`${BASE}/#match/00000000-0000-0000-0000-000000000000`);
    await page.waitForSelector('main a[href="#overview"]');
    assert.match(await page.textContent("main"), /Не удалось открыть страницу/);
    await page.click('main a[href="#overview"]');
    await page.waitForSelector('main[data-page="overview"]');
  } finally {
    await browser.close();
  }
});
