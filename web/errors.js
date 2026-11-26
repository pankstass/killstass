import { VERSION } from "./core.js";
/* v1.14 (Т4) — the browser error log. Unhandled errors and promise rejections go to POST /api/client-errors:
   version, route name, message and the start of the stack — never form data, URL parameters or the
   identifiers in the address — so that errors on real phones show up in #admin. Each distinct error is
   sent once per page load, at most MAX per load, nothing while offline; failures of the report are ignored.
   Errors the app already handles (API answers and network errors carry a code) are not reported. */
const MAX = 10;
const sent = new Set();
let count = 0;
export const route = () =>
  (location.hash.slice(1).split(/[/?]/)[0] || "overview")
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "")
    .slice(0, 40);
const cut = (s, n) => String(s || "").slice(0, n);
const where = (file, line, col) =>
  file
    ? `${String(file).replace(location.origin, "").split(/[?#]/)[0]}:${line || 0}:${col || 0}`
    : "";
export function report(kind, message, source = "", stack = "") {
  const msg = cut(message, 500).trim();
  if (!msg || /^Script error\.?$/i.test(msg)) return false;
  if (count >= MAX || navigator.onLine === false) return false;
  const key = `${kind}|${msg}|${source}`;
  if (sent.has(key)) return false;
  sent.add(key);
  count++;
  try {
    fetch("/api/client-errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      keepalive: true,
      body: JSON.stringify({
        kind,
        message: msg,
        source: cut(source, 300),
        stack: cut(stack, 4000),
        page: route(),
        version: cut(VERSION, 20).replace(/[^0-9A-Za-z.+-]/g, ""),
      }),
    }).catch(() => {});
  } catch {
    /* a report must never break the page */
  }
  return true;
}
export function init() {
  window.addEventListener("error", (e) => {
    // Failed <img>/<script> loads have no message (their target is the element): not script errors.
    if (!e.message) return;
    report(
      "error",
      e.message,
      where(e.filename, e.lineno, e.colno),
      e.error?.stack,
    );
  });
  window.addEventListener("unhandledrejection", (e) => {
    const r = e.reason;
    if (r && typeof r === "object" && r.code) return;
    report(
      "rejection",
      r instanceof Error ? `${r.name}: ${r.message}` : String(r),
      "",
      r?.stack,
    );
  });
}
