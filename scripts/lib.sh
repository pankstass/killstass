# KILLSTASS v1.10: shell helpers sourced by domain.sh, cert.sh, tailscale.sh, push.sh, firewall.sh and
# smoke.sh from the project directory (not a command of its own). .env stays the single place of settings:
# values are read with envget and changed with envset/envdel (atomic rename, mode 0600 kept).
say() { echo "killstass: $*"; }
die() { echo "killstass: ERROR: $*" >&2; exit 1; }
need_root() { [ "$(id -u)" = 0 ] || die 'run as root (su -)'; }

# KEY -> value from .env (last assignment wins; surrounding quotes removed; empty when missing).
envget() {
  [ -f .env ] || return 0
  sed -n "s/^$1=//p" .env | tail -n 1 | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}
# KEY VALUE: replaces the line KEY=… (or appends it). A value with spaces is written in double quotes,
# which docker compose reads as one value.
envset() {
  case "$2" in *[\"\'\\\$\`]*) die "envset $1: quotes, \\, \$ and \` are not supported" ;; esac
  case "$2" in *[[:space:]]*) _line="$1=\"$2\"" ;; *) _line="$1=$2" ;; esac
  _tmp=$(mktemp .env.XXXXXX)
  if [ -f .env ]; then grep -v "^$1=" .env > "$_tmp" || true; fi
  printf '%s\n' "$_line" >> "$_tmp"
  envreplace "$_tmp"
}
envdel() {
  [ -f .env ] || return 0
  _tmp=$(mktemp .env.XXXXXX)
  grep -v "^$1=" .env > "$_tmp" || true
  envreplace "$_tmp"
}
# The new .env keeps 0600 and the owner of the old one: scripts run as root, while the operator may run
# docker compose as a member of the docker group.
envreplace() {
  chmod 600 "$1"
  if [ -f .env ]; then chown --reference=.env "$1" 2>/dev/null || true; fi
  mv -f "$1" .env
}

# COMPOSE_PROFILES (comma-separated): push, tailscale.
profile_on() {
  _p=$(envget COMPOSE_PROFILES)
  case ",$_p," in *",$1,"*) ;; *) envset COMPOSE_PROFILES "${_p:+$_p,}$1" ;; esac
}
profile_off() {
  _p=$(envget COMPOSE_PROFILES | tr ',' '\n' | grep -vx "$1" | grep . | paste -sd, - || true)
  if [ -n "$_p" ]; then envset COMPOSE_PROFILES "$_p"; else envdel COMPOSE_PROFILES; fi
}
profile_has() { case ",$(envget COMPOSE_PROFILES)," in *",$1,"*) return 0 ;; esac; return 1; }

# KS_ALLOW_NETS (space-separated IPv4 networks the proxy and the firewall let in; default the LAN).
valid_cidr() {
  printf '%s\n' "$1" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$'
}
allowed_nets() { _n=$(envget KS_ALLOW_NETS); echo "${_n:-192.168.1.0/24}"; }
nets_add() {
  _n=$(allowed_nets)
  case " $_n " in *" $1 "*) ;; *) envset KS_ALLOW_NETS "$_n $1" ;; esac
}
nets_del() {
  # shellcheck disable=SC2086 # word splitting of the list is intended
  _n=$(printf '%s\n' $(allowed_nets) | grep -vx "$1" | paste -sd' ' - || true)
  envset KS_ALLOW_NETS "${_n:-192.168.1.0/24}"
}
valid_domain() {
  printf '%s\n' "$1" | grep -Eq '^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$'
}
