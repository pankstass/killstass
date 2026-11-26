// v1.9: shared helpers for the browser e2e and accessibility tests (Playwright + axe-core), see docs/19-v1.9.md.
// Environment:
//   E2E_BASE_URL  application address (default http://localhost:8000; must be a secure context:
//                 https:// or http://localhost, because the session cookie is Secure)
//   E2E_CHROMIUM  Chromium binary (default: the browser bundled with Playwright)
//   E2E_BROWSER   v1.14: chromium (default), firefox or webkit
//   E2E_PASSWORD  password of the two e2e accounts
//   E2E_ADMIN=1   admin.test.mjs requires e2e-alpha to be an administrator (scripts/e2e-docker.sh grants it)
// v1.10: the administrator part of admin.test.mjs also resets the password of e2e-bravo with a one-time code
// (to the same E2E_PASSWORD) and stores the new session, so the fixed accounts keep working.
import assert from "node:assert/strict";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { chromium, firefox, webkit } from "playwright";

export const BASE = (
  process.env.E2E_BASE_URL || "http://localhost:8000"
).replace(/\/+$/, "");
export const PASSWORD = process.env.E2E_PASSWORD || "e2e-only-password-2024";
/* Fixed accounts: later runs sign in again instead of registering new users
   (the server allows 5 registrations and 15 sign-ins per 15 minutes per IP). */
export const USERS = {
  alpha: { login: "e2e-alpha", name: "Альфа E2E" },
  bravo: { login: "e2e-bravo", name: "Браво E2E" },
};
export const ru = JSON.parse(
  readFileSync(new URL("../../web/i18n/ru.json", import.meta.url), "utf8"),
);
export const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const AXE = readFileSync(
  createRequire(import.meta.url).resolve("axe-core/axe.min.js"),
  "utf8",
);
const AUTH_DIR = fileURLToPath(
  new URL("../../test-results/e2e-auth/", import.meta.url),
);

export const uuid = () => crypto.randomUUID();
export const squash = (s) => (s || "").replace(/\s+/g, " ").trim();

/* v1.14: the engine comes from E2E_BROWSER — chromium (default), firefox or webkit (Playwright's bundled
   builds; scripts/e2e-docker.sh runs every engine of E2E_BROWSERS). E2E_CHROMIUM points to another Chromium. */
export const BROWSER = (process.env.E2E_BROWSER || "chromium").toLowerCase();
const ENGINES = { chromium, firefox, webkit };
export function launch() {
  const engine = ENGINES[BROWSER];
  assert.ok(
    engine,
    `E2E_BROWSER must be chromium, firefox or webkit, not ${BROWSER}`,
  );
  return engine.launch(
    BROWSER === "chromium"
      ? { executablePath: process.env.E2E_CHROMIUM || undefined }
      : {},
  );
}

/* A fresh browser context (Russian UI) that collects problems: uncaught exceptions, console errors,
   CSP violations and 5xx responses. 4xx answers belong to normal flows (401 before sign-in,
   403 for non-admins) and are asserted by the tests where they matter. Dialogs are accepted. */
export async function newPage(
  browser,
  { theme = null, mobile = false, storageState } = {},
) {
  const context = await browser.newContext({
    locale: "ru-RU",
    reducedMotion: "reduce",
    viewport: mobile
      ? { width: 390, height: 844 }
      : { width: 1280, height: 900 },
    storageState,
  });
  await context.addInitScript((th) => {
    try {
      if (th) localStorage.setItem("killstass-theme", th);
    } catch {
      /* about:blank has no storage */
    }
    document.addEventListener("securitypolicyviolation", (e) =>
      console.error(`CSP violation: ${e.violatedDirective} ${e.blockedURI}`),
    );
  }, theme);
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.problems = [];
  page.on("pageerror", (e) => page.problems.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().startsWith("Failed to load resource"))
      page.problems.push(`console: ${m.text()}`);
  });
  page.on("response", (r) => {
    if (r.status() >= 500)
      page.problems.push(
        `HTTP ${r.status()} ${r.request().method()} ${r.url()}`,
      );
  });
  page.on("dialog", (d) => d.accept());
  return page;
}

export function assertClean(page, label) {
  assert.deepEqual(
    page.problems.splice(0),
    [],
    `${label}: problems in the browser`,
  );
}

/* Opens a route of the single-page app and waits for a selector that only this view renders. v1.14: the
   content of the previous view is emptied first, so a selector of the same kind (another match's board)
   cannot be satisfied by the page that is being left — reruns on one database made that visible. */
export async function open(page, hash, selector) {
  const url = `${BASE}/#${hash}`;
  if (page.url() === url) await page.reload();
  else {
    await page
      .evaluate(() => document.querySelector("main#content")?.replaceChildren())
      .catch(() => {});
    await page.goto(url);
  }
  await page.waitForSelector(selector);
}
/* Selector of a view drawn inside the signed-in shell, or one of `extra` (v1.14: the shell marks the rendered
   page — a section inside a menu group has no menu item of its own to wait for). */
export const view = (name, extra = "") =>
  `main#content[data-page="${name}"]${extra ? ", " + extra : ""}`;

export async function axe(page, label) {
  if (!(await page.evaluate(() => !!window.axe))) await page.evaluate(AXE);
  const violations = await page.evaluate(async (tags) => {
    const r = await window.axe.run(document, {
      runOnly: { type: "tag", values: tags },
      resultTypes: ["violations"],
    });
    return r.violations.map(
      (v) =>
        `${v.impact} ${v.id}: ${v.help} — ${v.nodes
          .slice(0, 4)
          .map((n) => n.target.join(" "))
          .join(" | ")}`,
    );
  }, AXE_TAGS);
  assert.deepEqual(violations, [], `${label}: accessibility violations`);
}

export async function noHorizontalScroll(page, label) {
  const [w, vw] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    window.innerWidth,
  ]);
  assert.ok(w <= vw, `${label}: page is ${w}px wide in a ${vw}px viewport`);
}

export const notice = (page) =>
  page.evaluate(() => {
    const n = document.querySelector("#notice");
    return n && !n.hidden ? n.textContent.replace(/\s+/g, " ").trim() : "";
  });

async function submitAuth(page, register, user) {
  if (
    ((await page.getAttribute("#auth-form", "data-register")) === "true") !==
    register
  )
    await page.click(
      `[data-action="${register ? "show-register" : "show-login"}"]`,
    );
  await page.waitForSelector(`#auth-form[data-register="${register}"]`);
  if (register) {
    await page.fill('#auth-form [name="login"]', user.login);
    await page.fill('#auth-form [name="display_name"]', user.name);
  } else await page.fill('#auth-form [name="identity"]', user.login);
  await page.fill('#auth-form [name="password"]', PASSWORD);
  const [res] = await Promise.all([
    page.waitForResponse((r) =>
      r.url().endsWith(register ? "/api/auth/register" : "/api/auth/login"),
    ),
    page.click("#auth-form button:not([type=button])"),
  ]);
  if (res.status() === 429)
    throw new Error(
      "The server rate-limited sign-in/registration (15/5 per 15 minutes per IP). Wait, or on a TEST database run: DELETE FROM rate_limits",
    );
  return res.status();
}

/* Signed-in page of a fixed e2e account. The session cookie is kept in test-results/e2e-auth/ between runs;
   without it the test signs in through the form and registers the account on the very first run. */
export async function signedIn(browser, who, opts = {}) {
  const user = USERS[who];
  const file = `${AUTH_DIR}${user.login}.json`;
  const page = await newPage(browser, {
    ...opts,
    storageState: existsSync(file) ? file : undefined,
  });
  await page.goto(`${BASE}/#overview`);
  await page.waitForSelector('#auth-form, a.nav-link[href="#profile"]');
  if (await page.$("#auth-form")) {
    let status = await submitAuth(page, false, user);
    if (status === 401) status = await submitAuth(page, true, user);
    assert.ok(
      status === 200 || status === 201,
      `sign-in of ${user.login}: HTTP ${status}`,
    );
    await page.waitForSelector('a.nav-link[href="#profile"]');
    await saveAuth(page, who);
  }
  page.problems.splice(0); // the 401 of the first /api/auth/me is expected
  return page;
}

/* Keeps the session cookie of a signed-in page for later runs (v1.10: also after a password reset). */
export async function saveAuth(page, who) {
  const state = await page.context().storageState();
  mkdirSync(AUTH_DIR, { recursive: true });
  writeFileSync(
    `${AUTH_DIR}${USERS[who].login}.json`,
    JSON.stringify({ cookies: state.cookies, origins: [] }),
  );
}

/* Polls `check` (async, truthy when done) — for autosave and other background work of the app. */
export async function until(check, label, ms = 15000) {
  const end = Date.now() + ms;
  for (;;) {
    const v = await check();
    if (v) return v;
    if (Date.now() > end) assert.fail(`timed out: ${label}`);
    await new Promise((r) => setTimeout(r, 250));
  }
}

/* A small PNG drawn by the page's canvas, for file inputs (avatar upload). */
export async function pngFile(page, color = "#c8372d") {
  const b64 = await page.evaluate((c) => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 96;
    const g = canvas.getContext("2d");
    g.fillStyle = c;
    g.fillRect(0, 0, 96, 96);
    g.fillStyle = "#ffffff";
    g.fillRect(24, 24, 48, 48);
    return canvas.toDataURL("image/png").split(",")[1];
  }, color);
  return {
    name: "avatar.png",
    mimeType: "image/png",
    buffer: Buffer.from(b64, "base64"),
  };
}

/* JSON API call from inside the page: same origin, session cookie and CSRF header, like the app itself. */
export async function api(page, path, method = "GET", body) {
  return page.evaluate(
    async ({ path, method, body }) => {
      const headers = {};
      if (method !== "GET") {
        window.__e2eCsrf ||= (await (await fetch("/api/auth/me")).json()).csrf;
        headers["Content-Type"] = "application/json";
        headers["X-CSRF-Token"] = window.__e2eCsrf;
      }
      const r = await fetch("/api" + path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      return { status: r.status, json: await r.json().catch(() => null) };
    },
    { path, method, body },
  );
}
export async function call(page, path, method = "GET", body) {
  const r = await api(page, path, method, body);
  assert.ok(
    r.status < 300,
    `${method} ${path}: HTTP ${r.status} ${JSON.stringify(r.json)}`,
  );
  return r.json;
}

export async function me(page) {
  return call(page, "/auth/me");
}

/* Accepted friendship between two signed-in pages (idempotent across runs). */
export async function befriend(a, b) {
  const [pa, pb] = [(await me(a)).public_id, (await me(b)).public_id];
  const find = async () =>
    (await call(a, "/friends")).relations.find((r) => r.public_id === pb);
  let rel = await find();
  if (rel?.status === "accepted") return;
  if (!rel) {
    await call(a, "/friends", "POST", { public_id: pb });
    rel = await find();
  }
  if (rel.outgoing)
    await call(b, `/friends/${pa}`, "POST", { action: "accept" });
  else await call(a, `/friends/${pb}`, "POST", { action: "accept" });
  assert.equal((await find()).status, "accepted");
}

export async function matchAction(page, id, action, extra = {}) {
  const { version } = await call(page, `/matches/${id}`);
  return call(page, `/matches/${id}/actions`, "POST", {
    request_id: uuid(),
    version,
    action,
    ...extra,
  });
}
export async function matchCommand(page, id, path, body, method = "POST") {
  const { version } = await call(page, `/matches/${id}`);
  return call(page, `/matches/${id}${path}`, method, {
    request_id: uuid(),
    version,
    ...body,
  });
}

let catalogs = null;
export async function catalogId(page, kind, code) {
  catalogs ||= await call(page, "/catalogs?edition=2024");
  const row = catalogs.find((r) => r.kind === kind && r.code.endsWith(code));
  assert.ok(row, `catalog entry ${kind} ${code}`);
  return row.id;
}
/* Player setup through the API (the setup form itself is covered by the Python integration tests). */
export async function setupPlayer(page, id, primary, extra = {}) {
  const body = {
    edition: "2024",
    mission_id: await catalogId(page, "mission", "mission-secure"),
    killzone_id: await catalogId(page, "killzone", "volkus-1"),
    team1_id: await catalogId(page, "team", "team-angel-of-death"),
    team2_id: await catalogId(page, "team", "team-kommandos"),
    turns: 4,
    initiative: 1,
    operative_count: 6,
    operative_manual: true, // v1.13: a typed count is kept only when chosen (else roster → team)
    tac_op_id: await catalogId(page, "tac_op", "tac-op-rout"),
    primary_op: primary,
    objective_ids: [],
    ...extra,
  };
  return matchCommand(page, id, "/setup", body, "PUT");
}
