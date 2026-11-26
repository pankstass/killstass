// v1.14: the menu by purpose — HQ · Muster · Results · Club · Rules · Profile: the sections of the open group, the
// group pages with short summaries, the dot of a group that waits for the player, «← group» and the sibling tabs
// on a phone, the old addresses; the operative card of a roster (rules and unique actions as chips, a rule on tap,
// «Expand all» remembered, the same in print); equipment chosen in secret before the start and revealed with 2CP
// each, the calculator's grenades from it, the CP of a turning point with one tap; ploys: CP spent with a record in
// the protocol, a repeat in the same turning point asks first, Command Re-roll does not — both themes and at phone
// width. Accounts: e2e-alpha, e2e-bravo (the browser error log of #admin is in admin.test.mjs).
import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import {
  BASE,
  ru,
  launch,
  signedIn,
  open,
  view,
  axe,
  assertClean,
  noHorizontalScroll,
  squash,
  api,
  call,
  until,
  uuid,
  me,
  befriend,
  matchAction,
  matchCommand,
  catalogId,
  setupPlayer,
} from "./helpers.mjs";

const stamp = () => String(Date.now()).slice(-6);
const MENU = [
  "#overview",
  "#muster",
  "#results",
  "#club",
  "#rules",
  "#profile",
];
const NO_TEAMS =
  "no team reference: scripts/import-teams.sh (or E2E_TEAMS_BUNDLE for scripts/e2e-docker.sh)";
const hrefs = (page, sel) =>
  page.$$eval(sel, (l) => l.map((x) => x.getAttribute("href")));
/* The menu items marked as current, `#href=page|true` in the order of the menu. */
const current = (page) =>
  page.$$eval(".sidebar a.nav-link[aria-current]", (l) =>
    l.map((x) => `${x.getAttribute("href")}=${x.getAttribute("aria-current")}`),
  );
const hasDot = async (page, group) =>
  !!(await page.$(`.sidebar a.nav-link[data-group="${group}"] .nav-dot`));
/* The CP of both players on the board. */
const cp = (page) =>
  Promise.all(
    [1, 2].map(async (s) =>
      squash(await page.textContent(`.slot-${s} .cp-box output`)),
    ),
  );
const count = (n) => ru.equipCount.replace("{n}", n).replace("{max}", "4");
/* A fresh page load: the summary of the menu is fetched again. */
async function reload(page, hash, selector) {
  await page.goto(`${BASE}/#${hash}`);
  await page.reload();
  await page.waitForSelector(selector);
}
/* A hot-seat match of alpha against a guest with both players set up (not started). */
async function hotseat(a) {
  const { id } = await call(a, "/matches", "POST", {
    request_id: uuid(),
    kind: "hotseat",
    guest_name: `Гость ${stamp()}`,
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
  return id;
}

describe("v1.14", () => {
  let browser, a, b;
  before(async () => {
    browser = await launch();
    a = await signedIn(browser, "alpha");
    b = await signedIn(browser, "bravo");
    await befriend(a, b);
  });
  after(async () => {
    await browser?.close();
  });

  it("menu groups: six items, the open group unfolds, group pages with summaries, «← group», old addresses", async () => {
    await open(a, "results", view("results"));
    await a.waitForSelector(".rules-hub");
    assert.deepEqual(
      await hrefs(a, ".sidebar a.nav-link[data-group]:not(.nav-admin)"),
      MENU,
    );
    assert.deepEqual(await current(a), ["#results=page"]);
    assert.deepEqual(await hrefs(a, ".sidebar a.nav-subitem"), [
      "#history",
      "#stats",
    ]);
    assert.deepEqual(await hrefs(a, ".rules-hub a.rules-tile"), [
      "#history",
      "#stats",
    ]);
    const s = await call(a, "/nav-summary");
    await until(
      async () =>
        squash(await a.textContent('[data-sum="history"]')).startsWith(
          ru.sum_games.replace("{n}", s.history.games),
        ),
      "the summary on the tile",
    );
    await axe(a, "a group page");
    // A section: its group stays current; «← group» and the sibling sections (tabs on a phone).
    await a.click('.rules-hub a[href="#history"]');
    await a.waitForSelector(view("history"));
    assert.deepEqual(await current(a), ["#results=true", "#history=page"]);
    assert.equal(
      await a.getAttribute(".page-title a.back", "href"),
      "#results",
    );
    assert.equal(
      squash(await a.textContent(".page-title a.back")),
      `← ${ru.results}`,
    );
    assert.deepEqual(await hrefs(a, ".page-title .group-tabs a"), [
      "#history",
      "#stats",
    ]);
    assert.equal(
      await a.getAttribute('.group-tabs a[aria-current="page"]', "href"),
      "#history",
    );
    // The addresses stay: the rules books, a page opened from a section belongs to its group.
    await open(a, "core", view("core"));
    assert.deepEqual(await current(a), ["#rules=true", "#core=page"]);
    await open(a, `player/${(await me(b)).public_id}`, view("player"));
    assert.deepEqual(await current(a), ["#club=true", "#friends=true"]);
    await open(a, "maps", view("maps"));
    assert.deepEqual(await current(a), ["#muster=true", "#maps=page"]);
    assertClean(a, "menu groups");
  });

  it("menu groups on a phone: six items without scrolling, the sibling sections as tabs (dark theme)", async () => {
    const p = await signedIn(browser, "alpha", { mobile: true, theme: "dark" });
    try {
      await open(p, "history", view("history"));
      const shown = await p.$$eval(".sidebar a.nav-link", (l) =>
        l
          .filter((x) => x.getClientRects().length)
          .map((x) => {
            const s = x.querySelector(".nav-label");
            return [x.getAttribute("href"), s.scrollWidth <= s.clientWidth + 1];
          }),
      );
      assert.deepEqual(
        shown.map(([h]) => h),
        MENU,
      );
      assert.ok(
        shown.every(([, fits]) => fits),
        `labels fit: ${JSON.stringify(shown)}`,
      );
      assert.ok(await p.isVisible(".page-title .group-tabs"), "sibling tabs");
      await p.click('.page-title .group-tabs a[href="#stats"]');
      await p.waitForSelector(view("stats"));
      assert.equal(
        await p.getAttribute('.group-tabs a[aria-current="page"]', "href"),
        "#stats",
      );
      await noHorizontalScroll(p, "phone: a section");
      await axe(p, "phone: a section (dark)");
      if ((await me(p)).is_admin) {
        await open(p, "profile", view("profile"));
        assert.ok(
          await p.isVisible('.profile-admin a[href="#admin"]'),
          "on a phone the administration opens from the profile",
        );
      }
      assertClean(p, "phone menu");
    } finally {
      await p.context().close();
    }
  });

  it("a dot on the group that waits for the player: an incoming challenge", async () => {
    const ch = await call(b, "/challenges", "POST", {
      request_id: uuid(),
      public_id: (await me(a)).public_id,
      edition: "2024",
    });
    const club = '.sidebar a.nav-link[data-group="club"]';
    try {
      await reload(a, "club", view("club"));
      await a.waitForSelector(`${club} .nav-dot`);
      assert.equal(
        squash(await a.textContent(`${club} .sr-only`)),
        ru.navAttention,
      );
      const marked = await a.$$eval('[data-sum="friends"] .attn', (l) =>
        l.map((x) => x.textContent),
      );
      assert.ok(
        marked.some((x) => x.startsWith(ru.sum_challenges.split("{n}")[0])),
        marked.join(" | "),
      );
      assert.equal(
        await hasDot(a, "results"),
        (await call(a, "/nav-summary")).history.to_confirm > 0,
      );
      await axe(a, "a group with a dot");
    } finally {
      await call(b, `/challenges/${ch.id}`, "POST", {
        request_id: uuid(),
        action: "cancelled",
      });
    }
    await reload(a, "club", '[data-sum="friends"] span');
    const s = await call(a, "/nav-summary");
    assert.equal(
      await hasDot(a, "club"),
      s.friends.challenges + s.friends.requests + s.nights.unanswered > 0,
      "the dot follows the summary",
    );
    assertClean(a, "the dot of a group");
  });

  it("operative card: rules and unique actions as chips, a rule on tap, «Expand all» remembered, the same in print", async (t) => {
    const { teams } = await call(a, "/teams");
    if (!teams.find((x) => x.slug === "kommandos" && x.has_roster))
      return t.skip(NO_TEAMS);
    const roster = await call(a, "/rosters", "POST", {
      request_id: uuid(),
      team_slug: "kommandos",
      name: `Карточка E2E ${stamp()}`,
    });
    const card = ".rcard";
    const all = '[data-action="roster-rules-all"]';
    try {
      await open(a, `rosters/${roster.id}`, ".roster-add");
      await a.click('.add-op:has-text("Kommando Boss Nob")');
      await a.waitForSelector(`${card} .rchips .rchip`);
      const chips = await a.$$eval(`${card} .rchip`, (l) =>
        l.map((x) => ({
          kind: x.classList.contains("action") ? "action" : "rule",
          text: x.textContent.replace(/\s+/g, " ").trim(),
          open: x.getAttribute("aria-expanded"),
        })),
      );
      const list = JSON.stringify(chips);
      assert.ok(
        chips.some((c) => c.kind === "rule" && c.text === "Krumpin' Time"),
        list,
      );
      assert.ok(
        chips.some(
          (c) =>
            c.kind === "action" &&
            c.text.startsWith("Get It Dun!") &&
            c.text.endsWith("1AP"),
        ),
        list,
      );
      assert.ok(
        chips.every((c) => c.open === "false"),
        list,
      );
      assert.equal(
        await a.$$eval(`${card} .rrule:not([hidden])`, (l) => l.length),
        0,
      );
      // The card reads from top to bottom: stats, weapons, rules and actions, keywords.
      const tops = await a.$eval(card, (c) =>
        [".statline", ".ropts", ".rrules", ".rfoot"].map(
          (s) => c.querySelector(s)?.getBoundingClientRect().top ?? -1,
        ),
      );
      assert.ok(
        tops.every((v, i) => v >= 0 && (i === 0 || v >= tops[i - 1])),
        `order of the card: ${tops.join(" ")}`,
      );
      assert.ok(
        squash(await a.textContent(`${card} .rkeywords`)).includes("LEADER"),
      );
      // A chip opens its rule below the chips.
      const chip = `${card} .rchip[data-rule="Krumpin' Time"]`;
      await a.click(chip);
      assert.equal(await a.getAttribute(chip, "aria-expanded"), "true");
      const panel = `#${await a.getAttribute(chip, "aria-controls")}`;
      await a.waitForSelector(`${panel}:not([hidden])`);
      assert.ok(
        squash(await a.textContent(`${panel} h4`)).startsWith("Krumpin' Time"),
      );
      await a.click(chip);
      await a.waitForSelector(panel, { state: "hidden" });
      // «Expand all» opens every rule and is remembered on this device.
      await until(
        async () =>
          (await call(a, `/rosters/${roster.id}`)).data.selections?.length ===
          1,
        "the operative is saved",
      );
      await a.click(all);
      await a.waitForSelector(`${all}[aria-pressed="true"]`);
      assert.equal(
        await a.$$eval(`${card} .rrule[hidden]`, (l) => l.length),
        0,
      );
      await axe(a, "operative card, all rules open");
      await a.reload();
      await a.waitForSelector(`${all}[aria-pressed="true"]`);
      assert.equal(
        await a.$$eval(`${card} .rrule[hidden]`, (l) => l.length),
        0,
      );
      await a.click(all);
      await a.waitForSelector(`${all}[aria-pressed="false"]`);
      assert.equal(
        await a.evaluate(() => localStorage.getItem("killstass-roster-rules")),
        null,
      );
      // Print: the same rules and actions on the sheet.
      await a.evaluate(() => {
        window.print = () => (window.__printed = (window.__printed || 0) + 1);
      });
      await a.click('[data-action="roster-print"]');
      await a.waitForFunction(() => window.__printed === 1);
      const sheet = squash(await a.textContent("#print-root"));
      for (const x of ["Krumpin' Time", "Get It Dun!"])
        assert.ok(sheet.includes(x), `printed: ${x}`);
      await a.evaluate(() => window.dispatchEvent(new Event("afterprint")));
      const p = await signedIn(browser, "alpha", {
        mobile: true,
        theme: "dark",
      });
      try {
        await open(p, `rosters/${roster.id}`, `${card} .rchips .rchip`);
        await noHorizontalScroll(p, "phone: operative card");
        await axe(p, "phone: operative card (dark)");
        assertClean(p, "phone: operative card");
      } finally {
        await p.context().close();
      }
      assertClean(a, "operative card");
    } finally {
      await call(a, `/rosters/${roster.id}`, "DELETE");
    }
  });

  it("equipment: up to 4 in secret, revealed at the start with 2CP each, the calculator's weapons from it; CP of a turning point with one tap", async (t) => {
    const id = await hotseat(a);
    const [o1, o2] = await Promise.all(
      [1, 2].map((s) => call(a, `/matches/${id}/equipment?slot=${s}`)),
    );
    if (!o1.options.length || !o2.options.length) return t.skip(NO_TEAMS);
    const names = (o, keys) =>
      o.options.filter((x) => keys.includes(x.key)).map((x) => x.name);
    // Alpha: an option with weapons (grenades) and three more; the guest: one without a profile.
    const pick1 = [
      ...new Set(
        [
          o1.options.find((x) => x.weapons.length)?.key,
          ...o1.options.map((x) => x.key),
        ].filter(Boolean),
      ),
    ].slice(0, 4);
    const pick2 = [
      (o2.options.find((x) => !x.weapons.length) || o2.options[0]).key,
    ];
    await open(a, `match/${id}`, "#equip-form-1 input[name=equipment]");
    for (const k of pick1) await a.check(`#equip-form-1 input[value="${k}"]`);
    assert.equal(
      squash(await a.textContent("#equip-form-1 .equip-count")),
      count(4),
    );
    assert.equal(
      await a.$$eval(
        "#equip-form-1 input[name=equipment]:disabled",
        (l) => l.length,
      ),
      o1.options.length - 4,
      "a fifth option cannot be chosen",
    );
    const opt = `#equip-form-1 .equip-opt:has(input[value="${pick1[1]}"])`;
    await a.click(`${opt} .equip-more`);
    assert.equal(
      await a.getAttribute(`${opt} .equip-more`, "aria-expanded"),
      "true",
    );
    await a.waitForSelector(`${opt} .equip-text:not([hidden])`);
    await axe(a, "equipment before the start");
    await a.click("#equip-form-1 button:not([type])");
    await until(
      async () =>
        (await call(a, `/matches/${id}`)).players[0].equipment_count === 4,
      "alpha's equipment is saved",
    );
    // The guest chooses behind «pass the device».
    await a.click(".equip-panel details > summary");
    await a.check(`#equip-form-2 input[value="${pick2[0]}"]`);
    await a.click("#equip-form-2 button:not([type])");
    await until(
      async () =>
        (await call(a, `/matches/${id}`)).players[1].equipment_count === 1,
      "the guest's equipment is saved",
    );
    // The start reveals the equipment and gives each player 2CP.
    await matchAction(a, id, "start");
    await open(a, `match/${id}`, ".slot-1 .equip-box .rchip");
    const chips = (s) =>
      a.$$eval(`.slot-${s} .equip-box .rchip`, (l) =>
        l.map((x) => x.textContent.trim()),
      );
    assert.deepEqual(await chips(1), names(o1, pick1));
    assert.deepEqual(await chips(2), names(o2, pick2));
    assert.deepEqual(await cp(a), ["2", "2"]);
    const chip = `.slot-1 .equip-box .rchip[data-key="${id}:1:${pick1[1]}"]`;
    await a.click(chip);
    const rule = `#${await a.getAttribute(chip, "aria-controls")}`;
    await a.waitForSelector(`${rule}:not([hidden])`);
    assert.ok(
      squash(await a.textContent(`${rule} h4`)).startsWith(
        names(o1, [pick1[1]])[0],
      ),
    );
    // The attack calculator offers the weapons of the chosen equipment instead of every grenade.
    await a.click("#board-menu summary");
    await a.click('#board-menu [data-panel="attack"]');
    const groupsOf = async (player) => {
      const value = await until(
        () =>
          a
            .$eval(
              '#board-sheet select[name="attacker"]',
              (s, n) => s.querySelector(`optgroup[label="${n}"] option`)?.value,
              player,
            )
            .catch(() => null),
        `an operative of ${player} in the calculator`,
      );
      await a.selectOption('#board-sheet select[name="attacker"]', value);
      await a.waitForFunction(
        (v) =>
          document.querySelector('#board-sheet select[name="attacker"]')
            ?.value === v,
        value,
      );
      return a.$$eval('#board-sheet select[name="weapon"] optgroup', (l) =>
        l.map((g) => [
          g.label,
          [...g.querySelectorAll("option")].map((o) => o.textContent),
        ]),
      );
    };
    const m = await call(a, `/matches/${id}`);
    const weapons = o1.options
      .filter((x) => pick1.includes(x.key))
      .flatMap((x) => x.weapons.map((w) => w.name));
    const g1 = await groupsOf(m.players[0].display_name);
    const extra = g1.find(([label]) => label === ru.equipment);
    assert.ok(extra, JSON.stringify(g1));
    assert.equal(extra[1].length, weapons.length, JSON.stringify(extra));
    for (const w of weapons)
      assert.ok(
        extra[1].some((x) => x.includes(w)),
        `${w} in ${extra[1]}`,
      );
    assert.ok(
      !g1.some(([label]) => label === ru.atkGrenades),
      "no universal grenades",
    );
    const g2 = await groupsOf(m.players[1].display_name);
    assert.ok(
      !g2.some(([label]) => label === ru.equipment || label === ru.atkGrenades),
      JSON.stringify(g2),
    );
    // TP1: +1CP each with one tap; «Undo» takes it back.
    const grant = '[data-action="cp-grant"]';
    assert.ok(squash(await a.textContent(".cp-grant")).includes("+1CP"));
    await a.click(grant);
    await a.waitForSelector(grant, { state: "detached" });
    assert.deepEqual(await cp(a), ["3", "3"]);
    assert.ok(
      (await a.getAttribute(".undo", "aria-label")).includes(ru.cpReady),
    );
    await a.click(".undo");
    await a.waitForSelector(grant);
    assert.deepEqual(await cp(a), ["2", "2"]);
    await a.click(grant);
    await a.waitForSelector(grant, { state: "detached" });
    // TP2: first the initiative, then the player with it +1, the other +2.
    for (const [slot, op] of [
      [1, "crit"],
      [2, "kill"],
    ])
      await matchCommand(a, id, "/primary", { primary_op: op, slot });
    await matchAction(a, id, "turn", { turning_point: 2 });
    await open(a, `match/${id}`, ".cp-grant-hint");
    assert.equal(
      squash(await a.textContent(".cp-grant-hint")),
      ru.cpAfterInitiative,
    );
    await a.click('[data-action="initiative"][data-slot="2"]');
    await a.waitForSelector(grant);
    await a.click(grant);
    await a.waitForSelector(grant, { state: "detached" });
    assert.deepEqual(await cp(a), ["5", "4"]);
    await axe(a, "board with equipment");
    assertClean(a, "equipment and CP");
  });

  it("equipment stays secret until the start: the opponent sees only the count", async (t) => {
    const { id } = await call(a, "/matches", "POST", {
      request_id: uuid(),
      kind: "friend",
    });
    const { code } = await call(a, `/matches/${id}/invite`, "POST", {
      request_id: uuid(),
    });
    await call(b, `/invites/${code}/join`, "POST", { request_id: uuid() });
    try {
      await setupPlayer(a, id, "crit");
      const own = await call(a, `/matches/${id}/equipment`);
      if (!own.options.length) return t.skip(NO_TEAMS);
      const keys = own.options.slice(0, 2).map((x) => x.key);
      await matchCommand(a, id, "/equipment", { keys }, "PUT");
      const seen = (await call(b, `/matches/${id}`)).players.find(
        (x) => x.slot === 1,
      );
      assert.equal(seen.equipment_count, 2);
      assert.deepEqual(seen.equipment || [], []);
      assert.ok(
        (await api(b, `/matches/${id}/equipment?slot=1`)).status >= 400,
      );
      await open(b, `match/${id}`, ".equip-panel > p.muted");
      assert.equal(
        squash(await b.textContent(".equip-panel > p.muted")),
        `${(await me(a)).display_name}: ${count(2)}`,
      );
      assertClean(b, "the opponent's equipment before the start");
    } finally {
      await matchAction(a, id, "cancel");
    }
  });

  it("ploys: CP spent with a record in the protocol, a repeat asks first, Command Re-roll does not, «Undo» returns the CP", async () => {
    const id = await hotseat(a);
    await matchAction(a, id, "start");
    const m = await call(a, `/matches/${id}`);
    const ref = (await call(a, "/teams")).teams.find(
      (x) => x.catalog_id === m.players[0].team_id,
    );
    const strategy = ref
      ? (await call(a, `/teams/${ref.slug}`)).data.strategy_ploys || []
      : [];
    const name = m.players[0].display_name;
    const open1 = '.slot-1 [data-action="ploys-open"]';
    await open(a, `match/${id}`, open1);
    assert.deepEqual(await cp(a), ["2", "2"]);
    await a.click(open1);
    await a.waitForSelector("#board-sheet .ploy-list");
    assert.equal(
      squash(await a.textContent("#board-sheet h2")),
      `${ru.ploys}: ${name}`,
    );
    const use = (n) =>
      `#board-sheet [data-action="ploy-use"][data-name="${n}"]`;
    const dialogs = [];
    let answer = "dismiss";
    a.removeAllListeners("dialog");
    a.on("dialog", (d) => {
      dialogs.push(d.message());
      return answer === "accept" ? d.accept() : d.dismiss();
    });
    try {
      if (strategy.length) {
        const s1 = use(strategy[0].name);
        await a.waitForSelector(s1);
        await a.click(s1);
        await until(async () => (await cp(a))[0] === "1", "CP after a ploy");
        await a.waitForSelector(
          `#board-sheet .ploy.used [data-name="${strategy[0].name}"][data-used="1"]`,
        );
        // a repeat in the same turning point asks first: «No» changes nothing
        await a.click(s1);
        await until(() => dialogs.length === 1, "the repeat warning");
        assert.equal(dialogs[0], ru.ployRepeatConfirm);
        await a.waitForTimeout(300);
        assert.deepEqual(await cp(a), ["1", "2"]);
        answer = "accept";
        await a.click(s1);
        await until(
          async () => (await cp(a))[0] === "0",
          "CP after the repeat",
        );
        assert.ok(
          await a.$eval(use("Command Re-roll"), (x) => x.disabled),
          "no CP left",
        );
        // «Undo» reverts the repeat
        await a.click(".undo");
        await until(async () => (await cp(a))[0] === "1", "CP after «Undo»");
      } else {
        assert.ok(
          squash(await a.textContent("#board-sheet")).includes(
            ru.ployTeamUnknown,
          ),
        );
        await a.click('[data-action="cp-grant"]');
        await until(async () => (await cp(a))[0] === "3", "CP of TP1");
      }
      // Command Re-roll can be used again in the same turning point without a question.
      const asked = dialogs.length;
      const cr = use("Command Re-roll");
      let left = Number((await cp(a))[0]);
      const tap = async (sel, delta, label) => {
        await a.click(sel);
        left += delta;
        await until(async () => Number((await cp(a))[0]) === left, label);
      };
      await tap(cr, -1, "CP after Command Re-roll");
      if (strategy.length)
        await tap('[data-action="cp-grant"]', 1, "CP of TP1");
      await tap(cr, -1, "CP after the second re-roll");
      assert.equal(dialogs.length, asked, "Command Re-roll asks nothing");
      await a.click("#board-sheet .ploy-protocol > summary");
      const log = await a.$$eval("#board-sheet .ploy-log li", (l) =>
        l.map((x) => x.textContent.replace(/\s+/g, " ").trim()),
      );
      assert.equal(log.length, strategy.length ? 3 : 2, log.join(" | "));
      assert.ok(log[0].startsWith(`TP1 ${name} · Command Re-roll`), log[0]);
      assert.ok(log[0].includes(`${ru.ployFirefight} · 1CP`), log[0]);
      if (strategy.length)
        assert.ok(
          log[2].includes(`${strategy[0].name} ${ru.ployStrategy} · 1CP`),
          log[2],
        );
      // the guest's ploys are a tab away in a hot-seat match
      await a.click('#board-sheet .ploy-tabs [data-slot="2"]');
      await a.waitForSelector(
        '#board-sheet .ploy-tabs [data-slot="2"][aria-pressed="true"]',
      );
      assert.equal(
        squash(await a.textContent("#board-sheet h2")),
        `${ru.ploys}: ${m.players[1].display_name}`,
      );
      await axe(a, "ploys");
    } finally {
      a.removeAllListeners("dialog");
      a.on("dialog", (d) => d.accept());
    }
    const p = await signedIn(browser, "alpha", { mobile: true, theme: "dark" });
    try {
      await open(p, `match/${id}`, open1);
      await p.click(open1);
      await p.waitForSelector("#board-sheet .ploy-list");
      await p.click("#board-sheet .ploy-name");
      await p.waitForSelector("#board-sheet .ploy-text:not([hidden])");
      await noHorizontalScroll(p, "phone: ploys");
      await axe(p, "phone: ploys (dark)");
      assertClean(p, "phone: ploys");
    } finally {
      await p.context().close();
    }
    assertClean(a, "ploys");
  });
});
