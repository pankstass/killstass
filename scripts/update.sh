#!/bin/sh
# KILLSTASS update. Run as root (su -) from any directory.
#   ./scripts/update.sh                          rebuild and restart the files already in place (backup first)
#   ./scripts/update.sh /root/killstass-vX.zip   v1.10: install a release archive — checksums, backup of the
#                                                database, code, .env and images, deploy; when the new release
#                                                does not start, the previous one comes back automatically
#   ./scripts/update.sh --rollback               v1.10: return to the release saved by the last archive update
# The archive is checked against killstass-vX.zip.sha256 lying next to it (or --sha256 HEX) and against
# SHA256SUMS inside. --force reinstalls the same or an older version. Saved copies: BACKUP_DIR
# (/var/backups/killstass), the last 5 releases. Deploy order: build while the old stack runs, smoke.sh --pre,
# stop proxy and api, database, migrations, start, checks of the running release.
set -eu
umask 022

say() { echo "update: $*"; }
warn() { echo "update: WARNING: $*" >&2; }
die() { echo "update: ERROR: $*" >&2; exit 1; }
usage() {
  echo 'usage: update.sh [ARCHIVE.zip [--sha256 HEX] [--force] | --rollback]' >&2
  exit "${1:-2}"
}

ZIP='' SUM='' FORCE='' MODE=plain
while [ $# -gt 0 ]; do
  case "$1" in
    --rollback) MODE=rollback ;;
    --force) FORCE=1 ;;
    --sha256) [ $# -ge 2 ] || usage; SUM=$2; shift ;;
    --sha256=*) SUM=${1#--sha256=} ;;
    -h|--help) usage 0 ;;
    -*) usage ;;
    *) [ -z "$ZIP" ] || usage; ZIP=$1 ;;
  esac
  shift
done
if [ -n "$ZIP" ]; then
  [ "$MODE" = plain ] || usage
  MODE=archive
  case "$ZIP" in /*) ;; *) ZIP=$(pwd)/$ZIP ;; esac
elif [ -n "$SUM$FORCE" ]; then
  usage
fi

cd "$(dirname "$0")/.."
APP=$(pwd -P)
BACKUP_DIR=${BACKUP_DIR:-/var/backups/killstass}
STATE=$BACKUP_DIR/last-update
STAGE=''

# KEY -> value of the state file written before an archive update.
stateget() { sed -n "s/^$1=//p" "$STATE" | tail -n 1; }
# Paths of a manifest: relative, no "..", never the settings or runtime data of the installation.
safe_path() {
  case "$1" in ''|/*|..|../*|*/..|*/../*|.env|.env.rollback-*|local/*|backups/*) return 1 ;; esac
  return 0
}
manifest() { cut -c67- "$1" | LC_ALL=C sort; }
# v1.12: after a file of the release is deleted, its directories go too once they are empty.
prune() { d=$(dirname -- "$1"); [ "$d" = . ] || rmdir -p -- "$d" 2>/dev/null || true; }

extract() {  # ZIP DIR
  if command -v unzip >/dev/null 2>&1; then unzip -q -o "$1" -d "$2" < /dev/null
  elif command -v bsdtar >/dev/null 2>&1; then bsdtar -xf "$1" -C "$2"
  elif command -v python3 >/dev/null 2>&1; then python3 -m zipfile -e "$1" "$2"
  elif docker image inspect killstass-api:local >/dev/null 2>&1; then
    # Python of the installed api image, without network and capabilities.
    docker run --rm --network none --user 0:0 --cap-drop ALL --read-only -v "$1:/in.zip:ro" -v "$2:/out" \
      --entrypoint python killstass-api:local -m zipfile -e /in.zip /out
  else
    die 'no unzip, bsdtar or python3: install one of them (apt-get install unzip)'
  fi
}

# Puts the files of the release in SRC into place: files of the installed release that the new one no longer
# has are deleted; each file is replaced by a new inode (a running script keeps its old copy).
install_release() {  # SRC
  owner=$(stat -c %u:%g VERSION) || return 1
  if [ -f SHA256SUMS ]; then
    manifest SHA256SUMS | LC_ALL=C comm -23 - "$STAGE/manifest" | while IFS= read -r f; do
      if safe_path "$f" && [ -f "$f" ]; then rm -f -- "$f" && prune "$f"; fi
    done
  fi
  while IFS= read -r f; do
    d=$(dirname -- "$f")
    [ -d "$d" ] || { mkdir -p -- "$d" && chown "$owner" -- "$d"; } || return 1
    cp --remove-destination -- "$1/$f" "$f" || return 1
    mode=644
    case "$f" in *.sh) [ "$(head -c 2 -- "$f")" = '#!' ] && mode=755 ;; esac
    chmod "$mode" -- "$f" && chown "$owner" -- "$f" || return 1
  done < "$STAGE/manifest"
  cp --remove-destination -- "$1/SHA256SUMS" SHA256SUMS && chmod 644 SHA256SUMS && chown "$owner" SHA256SUMS
}

# Rollback to the release recorded in the state file: code, .env and images of the previous release. The
# database is not restored (migrations only add tables and columns; the dump is printed for data problems).
rollback() {
  code=$(stateget CODE) envcopy=$(stateget ENV_COPY) prev=$(stateget PREV_VERSION) dump=$(stateget DUMP)
  [ -s "$code" ] || { warn "saved code $code is missing"; return 1; }
  say "rollback to $prev"
  tar -tzf "$code" | sed -e 's|^\./||' -e '/\/$/d' -e '/^$/d' | LC_ALL=C sort > "$STAGE/prevfiles" || return 1
  if [ -f SHA256SUMS ]; then
    manifest SHA256SUMS | LC_ALL=C comm -23 - "$STAGE/prevfiles" | while IFS= read -r f; do
      if safe_path "$f" && [ -f "$f" ]; then rm -f -- "$f" && prune "$f"; fi
    done
  fi
  tar -xzf "$code" || return 1
  if [ -s "$envcopy" ] && ! cmp -s "$envcopy" .env; then
    cp -p .env ".env.rollback-$(date -u +%Y%m%dT%H%M%SZ)" && cp -p "$envcopy" .env || return 1
    say ".env of $prev restored (the newer one is kept as .env.rollback-*)"
  fi
  build=''
  for img in api db proxy; do
    if docker image inspect "killstass-$img:prev" >/dev/null 2>&1; then
      docker tag "killstass-$img:prev" "killstass-$img:local" || return 1
    else
      build=1
    fi
  done
  if [ -n "$build" ]; then docker compose build || return 1; fi
  docker compose up -d --wait --remove-orphans || return 1
  ./scripts/migrate.sh || warn "migrate.sh of $prev failed (grants of the runtime role)"
  i=0
  until docker compose exec -T api python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=5)" >/dev/null 2>&1; do
    i=$((i + 1)); [ "$i" -lt 15 ] || { warn 'the api of the previous release is not healthy'; return 1; }
    sleep 2
  done
  printf 'ROLLED_BACK=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" >> "$STATE"
  say "rolled back to $(tr -d ' \r\n' < VERSION). The database keeps the data of the newer release;"
  say "only if the data itself is damaged: ./scripts/restore.sh $dump --yes"
}

deploy() {
  # Build first; the old stack keeps running while the images are built.
  docker compose build || return 1
  # A broken Caddyfile or compose file stops the update here, while the old stack still runs.
  ./scripts/smoke.sh --pre || return 1
  docker compose stop proxy api || return 1
  # The db image contains the migrations; PostgreSQL is recreated, its volume is kept.
  docker compose up -d --wait db || return 1
  ./scripts/migrate.sh || return 1
  docker compose up -d --wait || return 1
  # Health, VERSION, migrations, static files and the service worker of the running release.
  ./scripts/smoke.sh --post || return 1
}

plain_update() {
  ./scripts/backup.sh
  deploy || die 'checks failed: see above. Return to the previous release: ./scripts/restore.sh and its files, or ./scripts/update.sh --rollback after an archive update'
  say "updated to $(tr -d ' \r\n' < VERSION)"
}

archive_update() {
  [ -f "$ZIP" ] || die "no such file: $ZIP"
  if [ -z "$SUM" ] && [ -f "$ZIP.sha256" ]; then SUM=$(awk 'NR == 1 { print $1 }' "$ZIP.sha256"); fi
  [ -n "$SUM" ] || die "checksum needed: put $(basename "$ZIP").sha256 next to the archive or pass --sha256 HEX"
  SUM=$(printf '%s' "$SUM" | tr 'A-F' 'a-f')
  printf '%s\n' "$SUM" | grep -Eq '^[0-9a-f]{64}$' || die 'the checksum must be 64 hexadecimal characters'
  [ "$(sha256sum "$ZIP" | cut -d ' ' -f 1)" = "$SUM" ] || die "$(basename "$ZIP"): SHA-256 does not match (damaged or a different file)"
  say "archive checksum ok"

  mkdir -p "$STAGE/x"
  extract "$ZIP" "$STAGE/x" || die 'the archive could not be unpacked'
  if [ -f "$STAGE/x/SHA256SUMS" ]; then SRC=$STAGE/x
  else
    set -- "$STAGE"/x/*
    [ $# -eq 1 ] && [ -f "$1/SHA256SUMS" ] || die 'not a KILLSTASS release: no SHA256SUMS'
    SRC=$1
  fi
  [ -f "$SRC/VERSION" ] && [ -f "$SRC/docker-compose.yml" ] && [ -f "$SRC/scripts/update.sh" ] || die 'not a KILLSTASS release'
  [ -z "$(find "$SRC" -type l | head -n 1)" ] || die 'the archive contains symbolic links'
  (cd "$SRC" && sha256sum -c --quiet --strict SHA256SUMS) || die 'SHA256SUMS check failed: the archive is damaged'
  manifest "$SRC/SHA256SUMS" > "$STAGE/manifest"
  (cd "$SRC" && find . -type f ! -path ./SHA256SUMS | sed 's|^\./||' | LC_ALL=C sort) > "$STAGE/files"
  cmp -s "$STAGE/files" "$STAGE/manifest" || die 'the archive and its SHA256SUMS list different files'
  while IFS= read -r f; do safe_path "$f" || die "unsafe path in SHA256SUMS: $f"; done < "$STAGE/manifest"

  NEW=$(tr -d ' \r\n' < "$SRC/VERSION")
  CUR=$(tr -d ' \r\n' < VERSION)
  printf '%s\n' "$NEW" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || die "strange VERSION in the archive: $NEW"
  if [ "$NEW" = "$CUR" ]; then
    [ -n "$FORCE" ] || die "$NEW is already installed (--force reinstalls it)"
  elif [ "$(printf '%s\n%s\n' "$CUR" "$NEW" | sort -V | tail -n 1)" != "$NEW" ]; then
    [ -n "$FORCE" ] || die "the archive has $NEW, older than the installed $CUR (--force; to undo an update: --rollback)"
  fi
  say "files of $NEW verified (installed: $CUR)"

  say 'backup of the database'
  DUMP=$(./scripts/backup.sh | tail -n 1) || die 'backup failed; nothing was changed'
  [ -n "$DUMP" ] && [ -s "$DUMP" ] || die 'backup.sh made no dump (another backup is running?): try again in a minute'
  STAMP=$(date -u +%Y%m%dT%H%M%SZ)
  CODE=$BACKUP_DIR/killstass-code-$STAMP-$CUR.tar.gz
  ENV_COPY=$BACKUP_DIR/killstass-env-$STAMP-$CUR
  (umask 077 && tar -czf "$CODE.tmp" --exclude=./.env --exclude=./local --exclude=./backups \
    --exclude=./node_modules --exclude=./test-results --exclude=./.git --exclude=./catalog-cache \
    --exclude=./catalog-output . && mv "$CODE.tmp" "$CODE") || { rm -f "$CODE.tmp"; die 'could not save the code'; }
  (umask 077 && cp -p .env "$ENV_COPY") || die 'could not save .env'
  for img in api db proxy; do
    if docker image inspect "killstass-$img:local" >/dev/null 2>&1; then
      docker tag "killstass-$img:local" "killstass-$img:prev" || die "docker tag killstass-$img"
    fi
  done
  printf 'PREV_VERSION=%s\nNEW_VERSION=%s\nCODE=%s\nENV_COPY=%s\nDUMP=%s\nSTAMP=%s\nAPP=%s\n' \
    "$CUR" "$NEW" "$CODE" "$ENV_COPY" "$DUMP" "$STAMP" "$APP" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE" \
    || die 'could not write the state file'
  # Only the last 5 saved releases.
  ls -1 "$BACKUP_DIR"/killstass-code-*.tar.gz 2>/dev/null | LC_ALL=C sort -r | tail -n +6 | while IFS= read -r old; do
    rm -f -- "$old" "$BACKUP_DIR/killstass-env-$(basename "$old" .tar.gz | sed 's/^killstass-code-//')"
  done
  say "saved: $DUMP, $CODE"

  say "installing $NEW"
  if install_release "$SRC" && deploy; then
    say "updated $CUR -> $NEW (undo: ./scripts/update.sh --rollback)"
    return 0
  fi
  warn "$NEW did not start; returning to $CUR"
  if rollback; then
    die "update to $NEW failed and was rolled back to $CUR. Causes: messages above, docker compose logs api proxy"
  fi
  die "ROLLBACK FAILED. Saved code: $CODE (tar -xzf in $APP), .env: $ENV_COPY, database: $DUMP; images killstass-*:prev"
}

main() {
  case "$MODE" in
    plain) plain_update; return ;;
  esac
  [ "$(id -u)" = 0 ] || die 'run as root (su -)'
  [ -f VERSION ] && [ -f docker-compose.yml ] && [ -f .env ] || die "$APP is not an installed KILLSTASS (no VERSION, docker-compose.yml or .env)"
  mkdir -p -m 700 "$BACKUP_DIR"
  exec 8> "$BACKUP_DIR/.update.lock"
  flock -n 8 || die 'another update is running'
  STAGE=$(mktemp -d /var/tmp/killstass-update.XXXXXX)
  trap 'rm -rf "$STAGE"' EXIT
  trap 'warn "interrupted; the previous release comes back with ./scripts/update.sh --rollback"; exit 130' HUP INT TERM
  if [ "$MODE" = rollback ]; then
    [ -f "$STATE" ] || die "nothing to roll back: no $STATE (it is written by an archive update)"
    [ -z "$(stateget ROLLED_BACK)" ] || die "already rolled back to $(stateget PREV_VERSION)"
    [ "$(stateget APP)" = "$APP" ] || die "the saved release belongs to $(stateget APP)"
    rollback || die 'rollback failed: see above'
  else
    archive_update
  fi
}

main "$@"; exit $?
