// A failing module must be recoverable even when Chromium cached an immutable 503.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";

const index = (await readFile("web/index.html", "utf8")).replaceAll(
  "{{VERSION}}",
  "test",
);
const boot = await readFile("web/boot.js", "utf8");

test("boot guard repairs cached module errors and preserves offline data", async () => {
  let broken = true;
  let moduleRequests = 0;
  const server = createServer((req, res) => {
    if (req.url === "/") {
      res.writeHead(200, {
        "Content-Type": "text/html",
        "Cache-Control": "no-store",
      });
      return res.end(index);
    }
    if (req.url === "/static/v/test/boot.js") {
      res.writeHead(200, { "Content-Type": "text/javascript" });
      return res.end(boot);
    }
    if (req.url === "/static/v/test/main.js") {
      res.writeHead(200, { "Content-Type": "text/javascript" });
      return res.end(
        'import "./failed.js"; document.querySelector("#app").textContent="OK"; window.killstassBootReady();',
      );
    }
    if (req.url === "/static/v/test/failed.js") {
      moduleRequests++;
      res.writeHead(broken ? 503 : 200, {
        "Content-Type": "text/javascript",
        "Cache-Control": broken
          ? "public, max-age=31536000, immutable"
          : "no-store",
      });
      return res.end(broken ? "failure" : "export {}; ");
    }
    if (req.url === "/sw.js") {
      res.writeHead(200, {
        "Content-Type": "text/javascript",
        "Service-Worker-Allowed": "/",
      });
      return res.end(
        `self.addEventListener("install", e => self.skipWaiting());
        self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
        self.addEventListener("fetch", e => {
          if (!new URL(e.request.url).pathname.startsWith("/static/v/test/")) return;
          e.respondWith((async () => {
            const cache = await caches.open("killstass-shell-test");
            const hit = await cache.match(e.request);
            if (hit) return hit;
            const response = await fetch(e.request);
            if (response.ok) await cache.put(e.request, response.clone());
            return response;
          })());
        });`,
      );
    }
    res.writeHead(req.url === "/api/client-errors" ? 202 : 404);
    res.end();
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const browser = await chromium.launch({
    executablePath: process.env.E2E_CHROMIUM || undefined,
    headless: true,
  });
  try {
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForSelector("#boot-repair");
    await page.evaluate(async () => {
      await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;
      await caches.open("killstass-shell-test");
      await caches.open("killstass-data");
      localStorage.setItem("offline-sentinel", "keep");
    });
    broken = false;
    await page.click("#boot-repair");
    await page.waitForFunction(
      () => document.querySelector("#app")?.textContent === "OK",
      null,
      { timeout: 15000 },
    );
    assert.ok(
      moduleRequests >= 2,
      "failed dependency must be refreshed from server",
    );
    assert.equal(
      await page.evaluate(() => localStorage.getItem("offline-sentinel")),
      "keep",
    );
    const keys = await page.evaluate(() => caches.keys());
    assert.ok(keys.includes("killstass-data"));
    // The active worker can recreate the shell; offline data must remain.
    assert.ok(keys.includes("killstass-shell-test"));
    assert.equal(
      (await page.evaluate(() => navigator.serviceWorker.getRegistrations()))
        .length,
      1,
    );
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
});
