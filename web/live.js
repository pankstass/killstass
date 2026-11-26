import { api, me } from "./core.js";
import { notification } from "./alerts.js";
/* v1.10 — one server-sent event stream per tab (/api/events): `notify` on every page (sounds and toasts for
   new notifications), plus the events of the open match (revision, clock, tracker) or killzone board. */
let source = null,
  key = null,
  handlers = {},
  seen = null,
  onOpen = () => {},
  onNotify = () => {};
export const setOnOpen = (f) => (onOpen = f);
/* v1.14: a new notification refreshes the menu summary (the dot on a group). */
export const setOnNotify = (f) => (onNotify = f);
export function watch(params = {}, on = {}) {
  handlers = on;
  const q = new URLSearchParams(params).toString();
  if (!me) return close();
  if (source && key === q) return;
  close();
  key = q;
  source = new EventSource("/api/events" + (q ? "?" + q : ""));
  for (const name of ["revision", "clock", "tracker", "board"])
    source.addEventListener(name, (e) => handlers[name]?.(+e.data));
  source.addEventListener("notify", (e) => fresh(+e.data));
  source.addEventListener("open", () => onOpen());
  // The server ends the stream for good when the session is gone.
  source.addEventListener("end", () => close());
}
export function close() {
  source?.close();
  source = null;
  key = null;
}
export const resetSeen = () => (seen = null);
async function fresh(n) {
  if (seen === null || n <= seen) {
    seen = Math.max(seen ?? 0, n);
    return;
  }
  const before = seen;
  seen = n;
  onNotify();
  try {
    const rows = await api("/notifications");
    rows
      .filter((x) => x.id > before && !x.read_at)
      .reverse()
      .forEach((x) => notification(x));
  } catch {}
}
