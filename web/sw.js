/* KILLSTASS {{VERSION}} — service worker (v1.10). Served by the API from /sw.js (scope «/»).
   The app shell (index and this release's /static/v/<VERSION>/ files) is cached on install, so the
   scoreboard opens without a server; API reads are network-first with a copy of the last answer
   (header X-Killstass-Cache: 1) for offline use; writes are never cached — the page queues them
   (web/offline.js). Also shows Web Push notifications (api/push.py). */
const VERSION = "{{VERSION}}";
const SHELL = "killstass-shell-" + VERSION;
const DATA = "killstass-data";
const ASSETS = /*ASSETS*/ [];
const MAX_DATA = 150;
// Never kept: streams, downloads, administrator data, public screens, images and sign-in calls;
// v1.11: reference search answers (one per typed query; offline the page searches the saved rules itself).
const SKIP =
  /^\/api\/(events|matches\/[^/]+\/events|export|calendar|tv|admin|reference\/search|users\/[^/]+\/avatar|auth\/(login|logout|register|password-reset)|health)/;

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL);
      const assets = ["/", ...ASSETS];
      // Avoid a burst of dozens of simultaneous connections during an update.
      for (let i = 0; i < assets.length; i += 8)
        await cache.addAll(assets.slice(i, i + 8));
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys())
        if (key.startsWith("killstass-shell-") && key !== SHELL)
          await caches.delete(key);
      await self.clients.claim();
    })(),
  );
});

async function fromShell(request) {
  const hit = await caches.match(request, { cacheName: SHELL });
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok) (await caches.open(SHELL)).put(request, response.clone());
  return response;
}

async function page(request) {
  try {
    const response = await fetch(request);
    if (response.ok)
      (await caches.open(SHELL)).put("/", response.clone()).catch(() => {});
    return response;
  } catch (err) {
    const hit = await caches.match("/", { cacheName: SHELL });
    if (hit) return hit;
    throw err;
  }
}

async function trim(cache) {
  const keys = await cache.keys();
  for (const key of keys.slice(0, Math.max(0, keys.length - MAX_DATA)))
    await cache.delete(key);
}

async function apiRead(request) {
  const cache = await caches.open(DATA);
  try {
    const response = await fetch(request);
    const type = response.headers.get("content-type") || "";
    if (response.status === 200 && type.includes("application/json")) {
      await cache.delete(request, { ignoreVary: true });
      await cache.put(request, response.clone());
      trim(cache);
    } else if (response.status === 401) await caches.delete(DATA);
    return response;
  } catch (err) {
    const hit = await cache.match(request, { ignoreVary: true });
    if (!hit) throw err;
    const headers = new Headers(hit.headers);
    headers.set("X-Killstass-Cache", "1");
    return new Response(await hit.blob(), { status: 200, headers });
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request,
    url = new URL(request.url);
  // ?fresh=1: the offline queue needs the current version, never a copy.
  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.searchParams.has("fresh")
  )
    return;
  if (url.pathname.startsWith("/static/v/" + VERSION + "/"))
    event.respondWith(fromShell(request));
  else if (request.mode === "navigate" && url.pathname === "/")
    event.respondWith(page(request));
  else if (
    url.pathname.startsWith("/api/") &&
    !SKIP.test(url.pathname) &&
    !(request.headers.get("accept") || "").includes("text/event-stream")
  )
    event.respondWith(apiRead(request));
});

// The page clears the copies on logout and account deletion.
self.addEventListener("message", (event) => {
  if (event.data?.type === "clear") event.waitUntil(caches.delete(DATA));
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data?.text() || "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "KILLSTASS", {
      body: data.body || "",
      tag: data.tag || undefined,
      icon: "/static/v/" + VERSION + "/icon-192.png",
      badge: "/static/v/" + VERSION + "/icon-192.png",
      data: { url: data.url || "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(
    event.notification.data?.url || "/",
    self.location.origin,
  );
  if (target.origin !== self.location.origin) return;
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      const open = windows.find(
        (c) => new URL(c.url).origin === self.location.origin,
      );
      if (open) {
        await open.focus();
        open.postMessage({ type: "open", hash: target.hash });
        return;
      }
      await self.clients.openWindow(target.href);
    })(),
  );
});
