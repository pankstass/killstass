import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import {
  launch,
  signedIn,
  open,
  view,
  call,
  me,
  assertClean,
  axe,
  noHorizontalScroll,
  uuid,
} from "./helpers.mjs";
import { factionGroup, factionIcon } from "../../web/faction-icons.js";

describe("v1.15", () => {
  let browser, a, b;
  before(async () => {
    browser = await launch();
    a = await signedIn(browser, "alpha", { mobile: true });
    b = await signedIn(browser, "bravo");
  });
  after(async () => {
    await browser?.close();
  });
  it("classifies all imported teams, shows local insignia and filters groups", async (t) => {
    const { teams } = await call(a, "/teams");
    if (teams.length < 49) return t.skip("full team bundle not imported");
    assert.ok(teams.every((x) => factionGroup(x) !== "other"));
    assert.equal(
      factionGroup({ slug: "future-team", faction: "new" }),
      "other",
    );
    assert.equal(factionIcon("battleclade").placeholder, true);
    await open(a, "teams", view("teams"));
    assert.equal(await a.locator(".team-group").count(), 3);
    assert.equal(await a.locator(".team-tile img").count(), teams.length);
    await a.fill("#team-search", "Kommandos");
    assert.equal(await a.locator(".team-group:visible").count(), 1);
    assert.equal(await a.locator(".team-tile:visible").count(), 1);
    await noHorizontalScroll(a, "faction mobile");
    await axe(a, "faction mobile");
    await assertClean(a, "faction");
  });
  it("records a match by public ID and opponent confirms", async () => {
    const ub = await me(b);
    const before = (await call(a, "/stats")).summary.games;
    await open(a, "quick", "#quick-form");
    await a.selectOption("[name=opponent_type]", "account");
    await axe(a, "registered match form");
    await a.fill("[name=opponent_public_id]", ub.public_id);
    await a.fill("[name=vp_for]", "17");
    await a.fill("[name=vp_against]", "11");
    const [res] = await Promise.all([
      a.waitForResponse(
        (r) =>
          r.url().endsWith("/api/quick-matches") &&
          r.request().method() === "POST",
      ),
      a.click("#quick-form button"),
    ]);
    assert.equal(res.status(), 201);
    const { id } = await res.json();
    await a.waitForSelector(".recorded-score");
    assert.match(await a.locator(".recorded-score").innerText(), /17/);
    assert.equal((await call(a, "/stats")).summary.games, before);
    await open(b, "match/" + id, ".recorded-score");
    await b.click("[data-action=match-action][data-kind=confirm]");
    await b.waitForFunction(() =>
      document
        .querySelector(".result-panel")
        ?.textContent.includes("подтвержд"),
    );
    assert.equal((await call(a, "/stats")).summary.games, before + 1);
    await noHorizontalScroll(a, "recorded result mobile");
    await assertClean(a, "record author");
    await assertClean(b, "record opponent");
  });
  it("groups and marks Tac Ops when setting up a match", async () => {
    const { id } = await call(a, "/matches", "POST", {
      request_id: uuid(),
      kind: "hotseat",
      guest_name: "Guest",
    });
    await open(a, "match/" + id, "#setup-form");
    const groups = await a
      .locator("#tac-choice optgroup")
      .evaluateAll((ns) => ns.map((n) => n.label));
    assert.ok(groups.length > 0);
    assert.ok(
      groups.every((x) =>
        [
          "Seek & Destroy",
          "Recon",
          "Security",
          "Infiltration",
          "Other",
        ].includes(x),
      ),
    );
    await axe(a, "tac setup");
    const select = a.locator("#tac-choice select");
    const opts = await select.locator("option").count();
    for (let i = 0; i < opts; i++) {
      const o = select.locator("option").nth(i);
      await select.selectOption(await o.getAttribute("value"));
      assert.ok(await a.locator("#tac-choice .tac-indicator").innerText());
    }
    await assertClean(a, "tac setup");
  });
});
