/* Independent of the module graph: show a recovery screen if the app cannot start. */
(() => {
  let ready = false;
  let shown = false;
  const version = document.querySelector(
    'meta[name="killstass-version"]',
  ).content;
  const prefix = `/static/v/${version}/`;
  let english = false;
  try {
    english = localStorage.getItem("killstass-lang") === "en";
  } catch {}
  const text = english
    ? {
        title: "The app could not load",
        help: "Check the server connection and try again. If the problem persists, select Repair.",
        reload: "Reload",
        repair: "Repair",
        progress: "Repairing the app…",
      }
    : {
        title: "Приложение не загрузилось",
        help: "Проверьте соединение с сервером и попробуйте ещё раз. Если ошибка повторяется, нажмите «Починить».",
        reload: "Обновить",
        repair: "Починить",
        progress: "Восстанавливаем загрузку…",
      };
  function fail() {
    if (ready || shown) return;
    const app = document.getElementById("app");
    if (!app) return;
    shown = true;
    app.innerHTML = `<main id="content"><section class="panel"><h1>${text.title}</h1><p>${text.help}</p><p><button id="boot-reload" type="button">${text.reload}</button> <button id="boot-repair" type="button">${text.repair}</button></p><p id="boot-status" role="status"></p></section></main>`;
    document.getElementById("boot-reload").onclick = () => location.reload();
    document.getElementById("boot-repair").onclick = repair;
    fetch("/api/client-errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        kind: "error",
        message: "Приложение не загрузилось",
        page: "boot",
        version,
      }),
    }).catch(() => {});
  }
  async function repair() {
    document.getElementById("boot-repair").disabled = true;
    document.getElementById("boot-status").textContent = text.progress;
    try {
      // Keep offline data and queued changes; remove only cached application shells.
      if ("caches" in window) {
        for (const key of await caches.keys())
          if (key.startsWith("killstass-shell-")) await caches.delete(key);
      }
      // Refresh the exact failed URLs, bypassing the browser HTTP cache. Fetch sequentially.
      const urls = new Set([prefix + "main.js", prefix + "boot.js"]);
      for (const entry of performance.getEntriesByType("resource")) {
        const url = new URL(entry.name, location.href);
        if (url.origin === location.origin && url.pathname.startsWith(prefix))
          urls.add(url.href);
      }
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 8000);
      try {
        for (const url of urls) {
          if (controller.signal.aborted) break;
          try {
            await fetch(url, { cache: "reload", signal: controller.signal });
          } catch {}
        }
      } finally {
        clearTimeout(timer);
      }
    } catch {
      /* A reload may still work; never delete offline data. */
    }
    location.reload();
  }
  window.killstassBootReady = () => {
    ready = true;
  };
  window.killstassBootFailed = fail;
  window.addEventListener(
    "error",
    (event) => {
      const target = event.target;
      if (target && target.tagName === "SCRIPT" && target.type === "module")
        fail();
    },
    true,
  );
  window.addEventListener("DOMContentLoaded", () => setTimeout(fail, 15000));
})();
