// v1.9: the administration page (#admin) and its API. e2e-bravo is never an administrator; e2e-alpha is one only
// after the operator granted it (./scripts/admin.sh grant e2e-alpha — scripts/e2e-docker.sh does this in its
// throwaway database). Without the grant the administrator part is skipped; E2E_ADMIN=1 makes it mandatory.
// v1.10: seasons, achievements, TV screens (the public #tv/<key> page) and one-time password reset codes;
// the reset sets e2e-bravo's password to the same E2E_PASSWORD and keeps the new session (helpers.saveAuth).
// v1.13: local players — the list with their matches, deleting one (the matches stay, the rating forgets it).
// v1.14: the browser error log — an unhandled error of a page is listed without the address parameters, cleared.
import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import {
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
  me,
  newPage,
  catalogId,
  saveAuth,
  until,
  PASSWORD,
  BASE,
} from "./helpers.mjs";

/* The administrator part runs only when e2e-alpha is an administrator (E2E_ADMIN=1 requires it). */
async function adminOnly(a, t) {
  if ((await me(a)).is_admin) return true;
  assert.notEqual(
    process.env.E2E_ADMIN,
    "1",
    "E2E_ADMIN=1, but e2e-alpha is not an administrator",
  );
  t.skip(
    "e2e-alpha is not an administrator: ./scripts/admin.sh grant e2e-alpha",
  );
  return false;
}

const count = async (page, metric) =>
  Number(
    (await page.textContent(`[data-metric="${metric}"] strong`)).replace(
      /\D/g,
      "",
    ),
  );

describe("administration", () => {
  let browser, a, b;
  before(async () => {
    browser = await launch();
    a = await signedIn(browser, "alpha");
    b = await signedIn(browser, "bravo");
  });
  after(() => browser?.close());

  it("a regular account has no admin menu item, sees an explanation, gets 403 from the API", async () => {
    assert.equal((await me(b)).is_admin, false);
    assert.equal(await b.$('a.nav-link[href="#admin"]'), null);
    await open(b, "admin", "main .panel");
    assert.equal(squash(await b.textContent("main .panel")), ru.adminOnly);
    for (const path of [
      "/admin/overview",
      "/admin/feedback?status=all",
      "/admin/users?q=e2e",
      "/admin/seasons",
      "/admin/achievements",
      "/admin/tv",
    ])
      assert.equal((await api(b, path)).status, 403, path);
    const handle = await api(b, "/admin/feedback/1", "POST", {
      request_id: uuid(),
      handled: true,
    });
    assert.equal(handle.status, 403);
    const reset = await api(
      b,
      `/admin/users/${(await me(a)).public_id}/password-reset`,
      "POST",
      { request_id: uuid() },
    );
    assert.equal(reset.status, 403, "only an administrator issues reset codes");
    assertClean(b, "admin as a regular user");
  });

  it("administrator: overview, feedback inbox, user search", async (t) => {
    if (!(await adminOnly(a, t))) return;
    const message = `E2E: отзыв ${new Date().toISOString()}`;
    await call(b, "/feedback", "POST", { message, page: "#admin-e2e" });

    await open(a, "admin", view("admin", "#admin-users table"));
    await a.waitForSelector("#admin-users table");
    const o = await call(a, "/admin/overview");
    assert.match(o.version, /^\d+\.\d+\.\d+$/);
    const before = await count(a, "adminFeedbackOpen");
    assert.equal(before, o.counts.feedback_open);
    // v1.11: the reference status and the journal of scripts/update-reference.sh
    assert.ok(Array.isArray(o.reference.updates));
    const ref = squash(await a.textContent("#admin-reference"));
    assert.match(ref, new RegExp(ru.ad_refTitle));
    assert.match(ref, /update-reference\.sh --rollback/);
    if (!o.reference.updates.length)
      assert.match(ref, new RegExp(ru.ad_refNone));
    await axe(a, "admin");

    const item = a.locator("article.feedback-item", { hasText: message });
    assert.match(
      squash(await item.textContent()),
      new RegExp(USERS.bravo.login),
    );
    await item.locator('[data-action="admin-fb-handle"]').click();
    await item.waitFor({ state: "detached" }); // handled feedback leaves the «new» list
    assert.equal(await count(a, "adminFeedbackOpen"), before - 1);
    await a.click('[data-action="admin-fb-filter"][data-status="all"]');
    await a
      .locator("article.feedback-item.handled", { hasText: message })
      .waitFor();

    await a.fill('#admin-user-search [name="q"]', USERS.bravo.login);
    await a.click("#admin-user-search button");
    await a.waitForFunction(
      ({ yes, no }) => {
        const text =
          document.querySelector("#admin-users tbody")?.textContent || "";
        return text.includes(yes) && !text.includes(no);
      },
      { yes: USERS.bravo.login, no: USERS.alpha.login },
    );
    assertClean(a, "admin");

    const phone = await signedIn(browser, "alpha", {
      theme: "dark",
      mobile: true,
    });
    await open(phone, "admin", "#admin-users table");
    await noHorizontalScroll(phone, "admin 390px");
    await axe(phone, "admin dark 390px");
    assertClean(phone, "admin phone");
    await phone.context().close();
  });

  it("administrator: a season and an achievement, shown on the statistics and player pages", async (t) => {
    if (!(await adminOnly(a, t))) return;
    for (const s of (await call(a, "/admin/seasons")).seasons)
      if (s.name.startsWith("E2E "))
        await api(a, `/admin/seasons/${s.id}`, "DELETE", {});
    for (const x of (await call(a, "/admin/achievements")).items)
      if (x.code.startsWith("e2e_"))
        await api(a, `/admin/achievements/${x.id}`, "DELETE", {});

    const name = `E2E сезон ${String(Date.now()).slice(-6)}`;
    await open(a, "admin", "#admin-seasons");
    await a.$eval("#season-editor", (d) => (d.open = true));
    await a.fill('#admin-season-form [name="name"]', name);
    // Far in the future: never overlaps a real season of the club.
    await a.fill('#admin-season-form [name="starts_on"]', "2099-01-01");
    await a.fill('#admin-season-form [name="ends_on"]', "2099-03-31");
    await a.click("#admin-season-form button:not([type=button])");
    await a.waitForSelector(`#admin-seasons tr:has-text("${name}")`);
    const season = (await call(a, "/admin/seasons")).seasons.find(
      (s) => s.name === name,
    );
    assert.equal(season.status, "upcoming");

    await open(a, "stats", "#season-pick");
    await a.selectOption("#season-pick", String(season.id));
    await a.waitForFunction(
      (n) =>
        document.querySelector("#season-panel h2")?.textContent.includes(n),
      name,
    );
    await axe(a, "season table");

    const code = `e2e_${String(Date.now()).slice(-6)}`,
      title = `E2E: первая победа ${code.slice(4)}`;
    await open(a, "admin", "#admin-achievements");
    await a.$eval("#ach-editor", (d) => (d.open = true));
    await a.fill('#admin-ach-form [name="code"]', code);
    await a.selectOption('#admin-ach-form [name="rule"]', "wins");
    await a.fill('#admin-ach-form [name="threshold"]', "1");
    await a.fill('#admin-ach-form [name="title_ru"]', title);
    await a.click("#admin-ach-form button:not([type=button])");
    await a.waitForSelector(`#admin-achievements tr:has-text("${code}")`);
    await a.click('[data-action="admin-ach-recompute"]');
    await axe(a, "admin seasons and achievements");

    await open(b, `player/${(await me(a)).public_id}`, ".ach-grid");
    assert.ok(
      (await b.textContent(".ach-grid")).includes(title),
      "the new achievement is listed on the player page",
    );

    const ach = (await call(a, "/admin/achievements")).items.find(
      (x) => x.code === code,
    );
    await open(a, "admin", `#admin-achievements tr:has-text("${code}")`);
    await a.click(`[data-action="admin-ach-delete"][data-id="${ach.id}"]`);
    await a.waitForSelector(`#admin-achievements tr:has-text("${code}")`, {
      state: "detached",
    });
    await a.click(
      `[data-action="admin-season-delete"][data-id="${season.id}"]`,
    );
    await a.waitForSelector(`#admin-seasons tr:has-text("${name}")`, {
      state: "detached",
    });
    assertClean(a, "seasons admin");
    assertClean(b, "achievements player");
  });

  it("administrator: local players are listed and can be deleted", async (t) => {
    const name = `E2E Локальный ${String(Date.now()).slice(-6)}`;
    await call(a, "/quick-matches", "POST", {
      request_id: uuid(),
      guest_name: name,
      local: true,
      edition: "2024",
      team1_id: await catalogId(a, "team", "team-angel-of-death"),
      team2_id: await catalogId(a, "team", "team-kommandos"),
      mission_id: await catalogId(a, "mission", "mission-secure"),
      killzone_id: await catalogId(a, "killzone", "volkus-1"),
      vp_for: 10,
      vp_against: 11,
      played_at: new Date().toISOString(),
    });
    assert.equal((await api(b, "/admin/local-players")).status, 403);
    if (!(await adminOnly(a, t))) return;
    await open(a, "admin", "#admin-locals");
    const row = a.locator("#admin-locals tbody tr", { hasText: name });
    await row.waitFor();
    assert.ok(squash(await row.textContent()).includes(USERS.alpha.name));
    await axe(a, "admin local players");
    await row.locator('[data-action="admin-local-delete"]').click(); // the confirmation is accepted
    await row.waitFor({ state: "detached" });
    assert.equal(
      await a.evaluate(() => document.activeElement?.closest("section")?.id),
      "admin-locals",
    );
    const club = await call(a, "/ratings?scope=all");
    assert.ok(!club.players.some((p) => p.display_name === name));
    assert.ok(
      !(await call(a, "/local-players")).items.some((x) => x.name === name),
    );
    assertClean(a, "admin local players");
  });

  it("administrator: a TV screen link works without signing in until it is deleted", async (t) => {
    if (!(await adminOnly(a, t))) return;
    const label = `E2E ТВ ${String(Date.now()).slice(-6)}`;
    await open(a, "admin", "#admin-tv-form");
    await a.fill('#admin-tv-form [name="label"]', label);
    await a.click("#admin-tv-form button");
    const item = a.locator(".tv-item", { hasText: label });
    await item.waitFor();
    const url = squash(await item.locator(".mono").textContent());
    assert.match(
      url,
      new RegExp(
        `^${BASE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/#tv/[\\w-]{20,}$`,
      ),
    );
    await item.locator("svg").waitFor(); // QR code of the link

    const tv = await newPage(browser, { theme: "dark" });
    await tv.goto(url);
    await tv.waitForSelector("main.tv .tv-grid");
    assert.equal(squash(await tv.textContent(".tv-head h1")), label);
    await axe(tv, "TV screen");
    assertClean(tv, "TV screen");
    await tv.context().close();

    const screen = (await call(a, "/admin/tv")).find((s) => s.label === label);
    await a.click(`[data-action="admin-tv-delete"][data-id="${screen.id}"]`);
    await item.waitFor({ state: "detached" });
    const gone = await fetch(`${BASE}/api/tv/${url.split("#tv/")[1]}`);
    assert.equal(gone.status, 404, "a deleted screen's link stops working");
    assertClean(a, "TV admin");
  });

  it("administrator: the browser error log lists an unhandled error without the address parameters, then is cleared", async (t) => {
    if (!(await adminOnly(a, t))) return;
    const tag = `E2E probe ${uuid().slice(0, 8)}`;
    await open(a, "stats", view("stats"));
    const sent = a.waitForResponse(
      (r) =>
        r.url().endsWith("/api/client-errors") &&
        r.request().method() === "POST",
    );
    await a.evaluate((tag) => {
      setTimeout(() => {
        throw new Error(`${tag} https://example.test/p?code=SECRET123#frag`);
      }, 0);
    }, tag);
    assert.equal((await sent).status(), 202);
    // the error was thrown on purpose
    await until(
      () => a.problems.some((x) => x.includes(tag)),
      "the page error",
    );
    a.problems = a.problems.filter((x) => !x.includes(tag));
    const { items } = await call(a, "/admin/client-errors");
    const row = items.find((x) => x.message.includes(tag));
    assert.ok(row, "the error is listed");
    assert.equal(row.kind, "error");
    assert.equal(row.page, "stats");
    assert.equal(row.version, (await call(a, "/health")).version);
    assert.equal(row.login, USERS.alpha.login);
    assert.ok(
      !/SECRET123|#frag/.test(row.message + row.stack),
      `no address parameters: ${row.message}`,
    );
    assert.equal((await api(b, "/admin/client-errors")).status, 403);
    await open(a, "admin", "#admin-errors .err-item");
    assert.ok((await count(a, "ad_errorsWeek")) >= 1);
    const item = a.locator("#admin-errors .err-item", { hasText: tag });
    await item.locator("summary").click();
    assert.ok(squash(await item.textContent()).includes(ru.ad_errError));
    await axe(a, "browser error log");
    await a.click('#admin-errors [data-action="admin-err-clear"]');
    await a.waitForSelector("#admin-errors .empty");
    assert.equal(
      squash(await a.textContent("#admin-errors .empty")),
      ru.ad_errNone,
    );
    assert.equal((await call(a, "/admin/client-errors")).items.length, 0);
    assertClean(a, "browser error log");
  });

  it("administrator: a one-time reset code lets a player choose a new password", async (t) => {
    if (!(await adminOnly(a, t))) return;
    await open(a, "admin", "#admin-user-search");
    await a.fill('#admin-user-search [name="q"]', USERS.bravo.login);
    await a.click("#admin-user-search button");
    const row = a.locator("#admin-users tbody tr", {
      hasText: USERS.bravo.login,
    });
    await row.locator('[data-action="admin-reset"]').click();
    await a.waitForSelector(".reset-code .code");
    const code = squash(await a.textContent(".reset-code .code"));
    assert.match(code, /^[A-Z0-9]{4}-[A-Z0-9]{4}$/);
    await axe(a, "reset code");

    const page = await newPage(browser);
    await page.goto(`${BASE}/#overview`);
    await page.click('[data-action="show-reset"]');
    await page.waitForSelector("#reset-form");
    await axe(page, "reset form");
    await page.fill('#reset-form [name="identity"]', USERS.bravo.login);
    await page.fill('#reset-form [name="code"]', code.toLowerCase());
    await page.fill('#reset-form [name="new_password"]', PASSWORD);
    await page.click("#reset-form button:not([type=button])");
    await page.waitForSelector('a.nav-link[href="#profile"]');
    assert.equal((await me(page)).login, USERS.bravo.login);
    await saveAuth(page, "bravo");
    assert.equal(
      (await api(b, "/auth/me")).status,
      401,
      "the reset ends every other session of the account",
    );
    const again = await api(page, "/auth/password-reset", "POST", {
      identity: USERS.bravo.login,
      code,
      new_password: PASSWORD,
    });
    assert.equal(again.status, 400, "a code works once");
    await a.click('[data-action="admin-reset-done"]');
    await a.waitForSelector(".reset-code", { state: "detached" });
    page.problems.splice(0); // the 401 of /api/auth/me before signing in
    assertClean(a, "reset admin");
    await page.context().close();
  });
});
