#!/bin/sh
# KILLSTASS v1.11: update the whole rules reference in one step — the general rules (warhammer-oracle) and the
# teams (kt-datacards + BSData) — with a database backup, checks, loading in one transaction and a report.
#   ./scripts/update-reference.sh                    download, check, back up and load (or record "unchanged")
#   ./scripts/update-reference.sh --check            download and check only: the report, nothing is loaded
#   ./scripts/update-reference.sh --rollback [STAMP] load the bundles that were in place before the last applied
#                                                    change (a repeated --rollback returns it) or before STAMP
#   ./scripts/update-reference.sh --status           last imports, the journal and the saved snapshots
# Environment: BACKUP_DIR (/var/backups/killstass; snapshots in BACKUP_DIR/reference), KEEP_REFERENCE (5 applied
# snapshots), MIN_SHARE (0.8: an update must keep this share of the teams, operatives and weapon rules now loaded),
# ORACLE_REF / KTD_REF / BSDATA_REF (pin the sources), TEAMS_BUNDLE / RULES_BUNDLE (prepared bundles instead of
# downloading), TRIGGER (manual | timer; set by systemd/killstass-reference.service).
# Downloads run in throwaway containers on Docker's default network: the web app itself never goes online.
# Every run except --check and --status is recorded in the journal shown on #admin.
set -eu
umask 077
cd "$(dirname "$0")/.."

say() { echo "reference: $*" >&2; }
die() { echo "reference: ERROR: $*" >&2; exit 1; }
usage() { echo 'usage: update-reference.sh [--check | --status | --rollback [STAMP]]' >&2; exit 2; }

MODE=update FROM=''
case "${1:-}" in
  '') [ $# -eq 0 ] || usage ;;
  --check) [ $# -eq 1 ] || usage; MODE=check ;;
  --status) [ $# -eq 1 ] || usage; MODE=status ;;
  --rollback) [ $# -le 2 ] || usage; MODE=rollback; FROM=${2:-} ;;
  -h|--help) sed -n 2,15p "$0"; exit 0 ;;
  *) usage ;;
esac
BACKUP_DIR=${BACKUP_DIR:-/var/backups/killstass}
export BACKUP_DIR
ROOT=$BACKUP_DIR/reference
KEEP_REFERENCE=${KEEP_REFERENCE:-5}
MIN_SHARE=${MIN_SHARE:-0.8}
TRIGGER=${TRIGGER:-manual}
case "$KEEP_REFERENCE" in ''|*[!0-9]*|0) die 'KEEP_REFERENCE must be a positive integer' ;; esac
case "$MIN_SHARE" in 0|1|0.[0-9]|0.[0-9][0-9]) ;; *) die 'MIN_SHARE must be a share between 0 and 1, e.g. 0.8' ;; esac
case "$TRIGGER" in manual|timer) ;; *) die 'TRIGGER must be manual or timer' ;; esac
case "$FROM" in '') ;; *[!0-9TZ]*) die 'STAMP looks like 20261104T051500Z (see --status)' ;; esac

api() { docker compose exec -T api "$@"; }
# The database owner over the local socket of the db container, one transaction; psql variables ks_backup and
# ks_snapshot name the database backup and the bundle directory in the journal record.
owner_sql() {
  docker compose exec -T -e "KS_BACKUP=${KS_BACKUP:-}" -e "KS_SNAPSHOT=${KS_SNAPSHOT:-}" db sh -c \
    'psql -X -q -A -t -v ON_ERROR_STOP=1 --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ks_backup="$KS_BACKUP" -v ks_snapshot="$KS_SNAPSHOT"'
}
snapshots() { ls -1 "$ROOT" 2>/dev/null | grep -E '^[0-9]{8}T[0-9]{6}Z$' | sort -r || true; }

if [ "$MODE" = status ]; then
  echo '== general rules (warhammer-oracle)'
  api python -m api.rulesdata status || true
  echo '== teams (kt-datacards, BSData)'
  api python -m api.teamdata status || true
  echo '== journal (last 10, Moscow time)'
  docker compose exec -T db sh -c 'psql -X -q -P pager=off -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL' || true
SELECT id, to_char(finished_at AT TIME ZONE 'Europe/Moscow', 'YYYY-MM-DD HH24:MI') AS finished, action, status, trigger,
       regexp_replace(snapshot, '^.*/', '') AS snapshot, left(coalesce(report->>'error', ''), 60) AS error
FROM reference_updates ORDER BY id DESC LIMIT 10;
SQL
  echo "== snapshots in $ROOT (newest first; ./scripts/update-reference.sh --rollback STAMP)"
  for d in $(snapshots); do
    state=incomplete
    [ ! -f "$ROOT/$d/.failed" ] || state=failed
    [ ! -f "$ROOT/$d/.applied" ] || state=applied
    [ ! -f "$ROOT/$d/rollback-of" ] || state="$state, rollback of $(cat "$ROOT/$d/rollback-of")"
    echo "$d  $state"
  done
  exit 0
fi

mkdir -p "$ROOT"
exec 8>"$ROOT/.lock"
flock -n 8 || die 'another reference update is running'
while :; do  # one snapshot directory per run (UTC second); the lock makes waiting a second enough
  STAMP=$(date -u +%Y%m%dT%H%M%SZ)
  STARTED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  DIR=$ROOT/$STAMP
  [ -e "$DIR" ] || break
  sleep 1
done
mkdir "$DIR"
ACTION=update JOURNAL='' STEP=start ERROR='' KS_BACKUP='' KS_SNAPSHOT=''
[ "$MODE" != rollback ] || ACTION=rollback
[ "$MODE" = check ] || JOURNAL=1

# Applied snapshots: the newest KEEP_REFERENCE; the latest failed run is kept for a look, everything else goes.
prune() {
  _applied=0 _failed=0
  for _d in $(snapshots); do
    if [ -f "$ROOT/$_d/.applied" ]; then
      _applied=$((_applied + 1))
      [ "$_applied" -gt "$KEEP_REFERENCE" ] || continue
    elif [ -f "$ROOT/$_d/.failed" ] && [ "$_failed" = 0 ]; then
      _failed=1
      continue
    fi
    rm -rf -- "${ROOT:?}/$_d"
  done
}
journal_failed() {
  docker compose exec -T -e "KS_ERROR=${ERROR:-$STEP failed}" -e "KS_ACTION=$ACTION" -e "KS_TRIGGER=$TRIGGER" \
    -e "KS_STARTED=$STARTED" -e "KS_DIR=$DIR" db sh -c \
    'psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v err="$KS_ERROR" -v act="$KS_ACTION" -v trig="$KS_TRIGGER" -v started="$KS_STARTED" -v dir="$KS_DIR"' <<'SQL' >/dev/null
INSERT INTO reference_updates(started_at, action, status, trigger, snapshot, report)
VALUES (:'started'::timestamptz, :'act', 'failed', :'trig', :'dir', jsonb_build_object('error', left(:'err', 2000)));
SQL
}
finish() {
  rc=$?
  trap - EXIT
  if [ "$rc" != 0 ]; then
    echo "reference: ERROR: ${ERROR:-$STEP failed} — nothing was loaded" >&2
    if [ -d "$DIR" ]; then : > "$DIR/.failed"; fi
    if [ -n "$JOURNAL" ]; then journal_failed || echo 'reference: WARNING: the failure is not in the journal' >&2; fi
    if [ -d "$DIR" ]; then echo "reference: files of this run: $DIR" >&2; fi
  fi
  prune
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' HUP INT TERM

# NAME OUT CMD...: stdout to OUT, stderr to DIR/NAME.log (shown afterwards; its end is the error of a failure).
logged() {
  _name=$1 _out=$2
  shift 2
  STEP=$_name
  if "$@" > "$_out" 2> "$DIR/$_name.log"; then
    cat "$DIR/$_name.log" >&2
    return 0
  fi
  cat "$DIR/$_name.log" >&2
  ERROR="$_name: $(tail -n 3 "$DIR/$_name.log" | tr '\n' ' ' | sed 's/ *$//')"
  return 1
}
fetch() {  # docker run of the api image without the app network: MODULE OUT ENV...
  _m=$1 _out=$2
  shift 2
  logged "fetch-$_m" "$_out" docker run --rm --network bridge --read-only --tmpfs /tmp:size=16m --cap-drop ALL \
    --security-opt no-new-privileges "$@" killstass-api:local python -m "api.$_m" fetch
}

# 1. The reference now in the database: the report compares with it, --rollback loads it back later.
logged export-teams "$DIR/teams-before.json" api python -m api.teamdata export
logged export-rules "$DIR/rules-before.json" api python -m api.rulesdata export

# 2. The new bundles: downloaded, prepared files, or (rollback) the "before" bundles of an applied snapshot.
if [ "$MODE" = rollback ]; then
  STEP=rollback
  if [ -n "$FROM" ]; then SRC=$ROOT/$FROM
  else SRC=''
    for d in $(snapshots); do
      if [ "$ROOT/$d" != "$DIR" ] && [ -f "$ROOT/$d/.applied" ]; then SRC=$ROOT/$d; break; fi
    done
  fi
  if [ -z "$SRC" ] || [ ! -f "$SRC/.applied" ] || [ ! -s "$SRC/teams-before.json" ] || [ ! -s "$SRC/rules-before.json" ]; then
    ERROR="rollback: no applied snapshot ${FROM:-} in $ROOT (see --status)"
    exit 1
  fi
  say "rolling back to the reference before ${SRC##*/}"
  cp -- "$SRC/teams-before.json" "$DIR/teams-new.json"
  cp -- "$SRC/rules-before.json" "$DIR/rules-new.json"
  echo "${SRC##*/}" > "$DIR/rollback-of"
else
  if [ -n "${TEAMS_BUNDLE:-}" ]; then STEP=teams-bundle; cp -- "$TEAMS_BUNDLE" "$DIR/teams-new.json"
  else
    say 'downloading the teams (kt-datacards, BSData)...'
    fetch teamdata "$DIR/teams-new.json" -e "KTD_REF=${KTD_REF:-main}" -e "BSDATA_REF=${BSDATA_REF:-master}"
  fi
  if [ -n "${RULES_BUNDLE:-}" ]; then STEP=rules-bundle; cp -- "$RULES_BUNDLE" "$DIR/rules-new.json"
  else
    say 'downloading the general rules (warhammer-oracle)...'
    fetch rulesdata "$DIR/rules-new.json" -e "ORACLE_REF=${ORACLE_REF:-}"
  fi
fi

# 3. Checks, the comparison and one SQL script (planner in the api container, read-only database role).
STEP=check
set +e
tar -C "$DIR" -cf - teams-new.json rules-new.json | api python -m api.refupdate plan --action "$ACTION" \
  --trigger "$TRIGGER" --started "$STARTED" --min-share "$MIN_SHARE" > "$DIR/apply.sql" 2> "$DIR/report.txt"
rc=$?
set -e
cat "$DIR/report.txt" >&2
case "$rc" in
  0) ;;
  3)
    if [ "$MODE" = check ]; then say 'check: nothing changed'; rm -rf -- "$DIR"; exit 0; fi
    STEP=journal
    owner_sql < "$DIR/apply.sql" >/dev/null
    rm -rf -- "$DIR"
    say 'nothing changed: the reference is up to date (recorded in the journal)'
    exit 0 ;;
  2) ERROR=$(grep -m 1 '^check failed' "$DIR/report.txt" || echo 'check failed'); exit 1 ;;
  *) ERROR="check: planner exited with $rc: $(tail -n 1 "$DIR/report.txt")"; exit 1 ;;
esac
if [ "$MODE" = check ]; then
  say 'check: the changes above would be loaded (run without --check)'
  rm -rf -- "$DIR"
  exit 0
fi

# 4. Database backup (pg_dump via scripts/backup.sh; waits for a scheduled backup that is running), then the load.
STEP=backup
flock -w 900 "$BACKUP_DIR/.backup.lock" true 2>/dev/null || true
KS_BACKUP=$(./scripts/backup.sh) || { ERROR='backup: scripts/backup.sh failed'; exit 1; }
if [ -z "$KS_BACKUP" ] || [ ! -s "$KS_BACKUP" ]; then ERROR='backup: no dump was created (another backup running?)'; exit 1; fi
say "backup: $KS_BACKUP"
STEP=load
KS_SNAPSHOT=$DIR
owner_sql < "$DIR/apply.sql"
: > "$DIR/.applied"
rm -f -- "$DIR/apply.sql"  # the bundles stay: --rollback loads teams-before.json and rules-before.json
say "loaded in one transaction; bundles: $DIR"
say 'undo: ./scripts/update-reference.sh --rollback'
