/* v1.9: single ES-module entry. Listeners are registered in the former <script> order, then the app boots.
   v1.10: the offline queue, the event stream, alerts and the new pages (players, game nights, TV, killzone maps).
   v1.11: the rules reference with search (library.js); v1.12: the «Rules» section and the core rules (corerules.js).
   v1.13: tooltips for game terms and weapon rules (terms.js); the operative count of the setup (opcount.js);
   local players in the opponent field (localplayers.js).
   v1.14: the menu by purpose (sections.js, groups.js); the browser error log (errors.js). */
import { afterFlush, boot, init as initApp } from "./app.js";
import { flush, init as initOffline, setOnFlushed } from "./offline.js";
import { setOnNotify, setOnOpen } from "./live.js";
import { refreshSummary } from "./groups.js";
import { init as initAlerts } from "./alerts.js";
import { init as initPlayers, syncPush } from "./players.js";
import { init as initNights } from "./nights.js";
import { init as initTv } from "./tv.js";
import { init as initMap } from "./map.js";
import { init as initReference } from "./reference.js";
import { init as initOps } from "./ops.js";
import { init as initQuickstart } from "./quickstart.js";
import { init as initTurns } from "./turns.js";
import { init as initClock } from "./clock.js";
import { init as initDice } from "./dice.js";
import { init as initShare } from "./share.js";
import { init as initBoard } from "./board.js";
import { init as initDemo } from "./demo.js";
import { init as initTeams } from "./teams.js";
import { init as initRosters } from "./rosters.js";
import { init as initTracker } from "./tracker.js";
import { init as initAttack } from "./attack.js";
import { init as initTournaments } from "./tournaments.js";
import { init as initAdmin } from "./admin.js";
import { init as initStyleguide } from "./styleguide.js";
import { init as initLibrary } from "./library.js";
import { init as initCoreRules } from "./corerules.js";
import { init as initTerms } from "./terms.js";
import { init as initOpCount } from "./opcount.js";
import { init as initLocalPlayers } from "./localplayers.js";
import { init as initEquipment } from "./equipment.js";
import { init as initPloys } from "./ploys.js";
import { init as initErrors } from "./errors.js";

for (const init of [
  initErrors,
  initOffline,
  initApp,
  initReference,
  initOps,
  initQuickstart,
  initTurns,
  initClock,
  initDice,
  initShare,
  initBoard,
  initDemo,
  initTeams,
  initRosters,
  initTracker,
  initAttack,
  initTournaments,
  initAdmin,
  initStyleguide,
  initAlerts,
  initPlayers,
  initNights,
  initTv,
  initMap,
  initLibrary,
  initCoreRules,
  initTerms,
  initOpCount,
  initLocalPlayers,
  initEquipment,
  initPloys,
])
  init();
// Commands queued without a connection go out as soon as the server answers again (or the stream reopens).
setOnFlushed(afterFlush);
setOnOpen(() => flush());
setOnNotify(() => refreshSummary(true));
boot().then(() => syncPush().catch(() => {}));
