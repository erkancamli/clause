#!/usr/bin/env bash
# Install Clause on a fresh Ubuntu server, behind nginx and TLS.
#
# Run as root, from inside the unpacked source directory:
#
#     sudo bash deploy/install.sh api.clause.insure you@example.com
#
# It is safe to run again: every step checks before it acts, so a failed run can
# be fixed and repeated without undoing anything.

set -euo pipefail

# An activated virtual environment in the installing shell poisons the one this
# script builds: `python3 -m venv` run from inside a venv can point the new
# venv's interpreter back at the parent's, and the parent usually lives under
# /root. The service sets ProtectHome=yes, so /root is invisible to it, and the
# unit dies with status=203/EXEC before it prints anything. That failure names
# nothing useful, so it is cheaper to make it impossible than to diagnose it.
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH PYTHONSTARTUP
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
SYSTEM_PYTHON=/usr/bin/python3

DOMAIN="${1:-}"
EMAIL="${2:-}"
APP_DIR=/opt/clause
ENV_DIR=/etc/clause
STATE_DIR=/var/lib/clause

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
  echo "usage: sudo bash deploy/install.sh <api domain> <email for the certificate>" >&2
  exit 2
fi
if [[ $EUID -ne 0 ]]; then
  echo "run this with sudo" >&2
  exit 2
fi

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED="$("$SYSTEM_PYTHON" -c "import re,pathlib; print(re.search(r'__version__ = \"([^\"]+)\"', pathlib.Path('$SOURCE/clause/__init__.py').read_text()).group(1))")"
echo "==> installing clause $EXPECTED from $SOURCE for $DOMAIN"

# A server that already runs Caddy has its own front door and its own
# certificates; nginx is not installed on it at all, let alone started, and
# deploy/README.md has the Caddyfile block that proxies to 127.0.0.1:8080.
NGINX=1
if [[ -f /etc/caddy/Caddyfile ]]; then
  NGINX=0
  echo "    /etc/caddy/Caddyfile found: reverse proxy already present, nginx skipped"
fi

echo "==> packages"
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip rsync curl sqlite3
if [[ $NGINX -eq 1 ]]; then
  apt-get install -y -qq nginx certbot python3-certbot-nginx
fi

echo "==> user and directories"
id -u clause >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin clause
mkdir -p "$APP_DIR" "$ENV_DIR" "$STATE_DIR"

echo "==> code"
# Beside the running release, never into it.
#
# This used to rsync --delete straight over /opt/clause while the service was
# answering requests out of it. Python imports a module the first time
# something asks for it, so a request arriving during those few seconds could
# reach for a file that had just been deleted and not yet rewritten. The new
# release is assembled in a directory of its own and the service is pointed at
# it by moving one symlink, which is a single atomic rename: the old release
# is whole until the instant the new one is, and the process that is running
# holds its own files open regardless.
RELEASES="$APP_DIR/releases"
NEW="$RELEASES/$EXPECTED-$(date -u +%Y%m%d-%H%M%S)"
CURRENT="$APP_DIR/current"
mkdir -p "$RELEASES"

# A server installed by an older version of this script has the source lying
# flat in /opt/clause. Move it aside rather than delete it: it is the release
# that is running right now and the one to fall back to if the new one will
# not start.
if [[ -d "$APP_DIR/clause" && ! -L "$CURRENT" ]]; then
  LEGACY="$RELEASES/legacy-$(date -u +%Y%m%d-%H%M%S)"
  mkdir -p "$LEGACY"
  for item in "$APP_DIR"/*; do
    case "$(basename "$item")" in
      releases|current|.venv) continue ;;
    esac
    mv "$item" "$LEGACY"/ 2>/dev/null || true
  done
  ln -sfn "$LEGACY" "$CURRENT"
  echo "    the flat layout was moved to $LEGACY and is the release to fall back to"
fi

PREVIOUS=""
[[ -L "$CURRENT" ]] && PREVIOUS="$(readlink -f "$CURRENT" || true)"

mkdir -p "$NEW"
rsync -a --exclude .venv --exclude '__pycache__' \
      --exclude '.pytest_cache' --exclude 'node_modules' --exclude 'hazard_build' \
      --exclude 'privy-bundle' "$SOURCE"/ "$NEW"/
chown -R clause:clause "$NEW" "$STATE_DIR"
chmod 750 "$STATE_DIR"
echo "    assembled $NEW"

echo "==> python environment"
# A venv whose interpreter resolves outside /opt or /usr is one the service
# cannot execute. Rebuild rather than trust it: it costs a minute and it is the
# difference between a working install and a unit that exits 203 silently.
if [[ -e "$APP_DIR/.venv/bin/python" ]]; then
  VENV_REAL="$(readlink -f "$APP_DIR/.venv/bin/python" || true)"
  case "$VENV_REAL" in
    /usr/*|/opt/clause/*) ;;
    *) echo "    the existing environment points at $VENV_REAL, rebuilding"
       rm -rf "$APP_DIR/.venv" ;;
  esac
fi
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  "$SYSTEM_PYTHON" -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$NEW/requirements.txt"
chown -R clause:clause "$APP_DIR/.venv"

# Prove it runs before the service is told to run it, and prove it runs the way
# the service will: as the clause user, from the directory the unit uses. Both
# halves matter. Running it from wherever the installer happens to sit tests
# nothing, and fails anyway when that is a home directory the clause user
# cannot enter, which is a fault in the test rather than in the install.
CHECK="$(cd "$NEW" && setpriv --reuid=clause --regid=clause --clear-groups \
         "$APP_DIR/.venv/bin/python" -c 'import clause' 2>&1)" || {
  echo >&2
  echo "the environment at $APP_DIR/.venv cannot run as the clause user:" >&2
  echo >&2
  echo "$CHECK" >&2
  echo >&2
  echo "if that names a missing module, the package list is wrong; otherwise" >&2
  echo "try:  rm -rf $APP_DIR/.venv  and run this again" >&2
  exit 1
}

echo "==> wind model"
# Storm cover is priced from clause/hazard/models/wind_TR.json, built from
# NASA POWER the way the rain model was. The file is not in the source until
# somebody commits one, so the first install builds it here, once, as the
# service user; the fetched series are kept in hazard_build/ (never deleted
# by the sync above), so a later run rebuilds from the cache in seconds. A
# build that cannot reach NASA, or that fails its own test, leaves storm
# cover unpriceable everywhere and the install goes on: nothing is sold on a
# model that has not passed.
if [[ ! -f "$NEW/clause/hazard/models/wind_TR.json" ]]; then
  echo "    building clause/hazard/models/wind_TR.json from NASA POWER (81 places; minutes on a first run)"
  if (cd "$NEW" && setpriv --reuid=clause --regid=clause --clear-groups \
        "$APP_DIR/.venv/bin/python" -m clause.hazard.wind_build > "$STATE_DIR/wind_build.log" 2>&1); then
    tail -n 12 "$STATE_DIR/wind_build.log" | sed 's/^/    /'
  else
    echo "    the wind build did not finish (see $STATE_DIR/wind_build.log); storm cover stays off until it does" >&2
  fi
else
  echo "    clause/hazard/models/wind_TR.json is present"
fi

echo "==> configuration"
if [[ ! -f "$ENV_DIR/clause.env" ]]; then
  sed "s/api\.clause\.insure/$DOMAIN/g" "$SOURCE/deploy/clause.env.example" \
      > "$ENV_DIR/clause.env"
  echo "    wrote $ENV_DIR/clause.env; read it before going live"
else
  echo "    $ENV_DIR/clause.env exists, left alone"
fi
# The two demonstration switches. This script used to turn both of them ON in
# a file it had just created, so every fresh server came up handing out money
# and showing fabricated insurers, and the only thing standing between that
# and a real deployment was somebody remembering to read the file. They are
# written OFF, and an operator running a demonstration turns them on
# deliberately, which is the only way round that fails safely.
#
# Each is added once, to a file written by an older version of this script
# that never mentioned it; any line that names the setting, on or off,
# commented or not, is the operator's decision and is left exactly as it is.
mentioned() { grep -qE "^[[:space:]]*#?[[:space:]]*$1=" "$ENV_DIR/clause.env"; }
if ! mentioned CLAUSE_SPECIMENS; then
  printf '\n# Stand in companies in every country, each marked as not a real company.\n# Set to 1 only for a demonstration.\nCLAUSE_SPECIMENS=0\n' >> "$ENV_DIR/clause.env"
  echo "    stand in companies left off (CLAUSE_SPECIMENS=0)"
fi
if ! mentioned CLAUSE_FAUCET; then
  printf '\n# Demonstration money: new addresses are funded, and My cover has a top up\n# button. This is free money. Set to 1 only for a demonstration.\nCLAUSE_FAUCET=0\n' >> "$ENV_DIR/clause.env"
  echo "    demonstration money left off (CLAUSE_FAUCET=0)"
fi
chmod 600 "$ENV_DIR/clause.env"
chown root:root "$ENV_DIR/clause.env"

echo "==> service"
install -m 644 "$SOURCE/deploy/clause.service" /etc/systemd/system/clause.service
systemctl daemon-reload
systemctl enable clause.service

# Whether the service is answering, and with which version. Asked of the
# service directly rather than through nginx, so that a proxy that has not
# been reconfigured yet cannot make a healthy service look broken.
answering() {
  local body
  body="$(curl -fsS --max-time 4 http://127.0.0.1:8080/api/health 2>/dev/null)" || return 1
  [[ "$body" == *'"status":"ok"'* || "$body" == *'"status": "ok"'* ]] || return 1
  [[ -n "${1:-}" ]] && [[ "$body" != *"\"$1\""* ]] && return 1
  return 0
}

# Up, or back to what was up before.
#
# A release that cannot start used to take the site with it: the unit was
# restarted, it raised on the way up, systemd restarted it again, and it did
# that forty five times while every request got a 502. Nothing checked, and
# nothing went back. Now the symlink is moved, the service is restarted, and
# it has ninety seconds to answer with the version that was just installed.
# If it does not, the symlink goes back to the release that was serving a
# minute ago, that one is started again, and this script exits non-zero
# without having changed anything that lasts. The rule is that a deployment
# either replaces what is running or leaves it exactly alone.
swap_to() {
  ln -sfn "$1" "$APP_DIR/current.tmp"
  mv -Tf "$APP_DIR/current.tmp" "$CURRENT"
}

echo "    pointing at $(basename "$NEW")"
swap_to "$NEW"
systemctl restart clause.service

WAITED=0
until answering "$EXPECTED"; do
  WAITED=$((WAITED + 2))
  if [[ $WAITED -ge 90 ]]; then
    echo >&2
    echo "the new release did not answer in 90 seconds." >&2
    journalctl -u clause.service -n 25 --no-pager >&2 || true
    if [[ -n "$PREVIOUS" && -d "$PREVIOUS" ]]; then
      echo >&2
      echo "==> going back to $(basename "$PREVIOUS")" >&2
      swap_to "$PREVIOUS"
      systemctl restart clause.service
      BACK=0
      until answering ""; do
        BACK=$((BACK + 2))
        [[ $BACK -ge 60 ]] && { echo "the previous release did not come back either." >&2; break; }
        sleep 2
      done
      answering "" && echo "    the previous release is serving again; nothing was changed" >&2
    else
      echo "there is no previous release to go back to." >&2
    fi
    exit 1
  fi
  sleep 2
done
echo "    $EXPECTED is answering after ${WAITED}s"

# Three releases kept: the one running, the one to fall back to, and one more.
# Directories, not symlinks, and never the one being pointed at.
KEEP="$(readlink -f "$CURRENT")"
# shellcheck disable=SC2012
ls -1dt "$RELEASES"/*/ 2>/dev/null | tail -n +4 | while read -r old; do
  [[ "$(readlink -f "$old")" == "$KEEP" ]] && continue
  rm -rf "$old"
done

front_door() {
if [[ $NGINX -eq 0 ]]; then
  echo "==> nginx: reverse proxy already present, nginx skipped"
  return 0
fi
echo "==> nginx"
# nginx will not start if something already holds port 80. That is not a
# fault: it is another proxy (Caddy, Apache, a container) that already fronts
# this server, and the protocol is reachable behind it on 127.0.0.1:8080.
# Name the occupant, stand nginx down, and carry on; deploy/README.md has the
# block to add to that proxy.
if ! systemctl is-active --quiet nginx; then
  HOLDER="$(ss -ltnpH '( sport = :80 )' 2>/dev/null | head -1 || true)"
  if [[ -n "$HOLDER" ]]; then
    echo "    port 80 is already taken, so nginx cannot start:"
    echo "      $HOLDER"
    echo "    reverse proxy already present, nginx skipped"
    systemctl disable --now nginx >/dev/null 2>&1 || true
    return 0
  fi
fi
[[ -f /etc/nginx/proxy_params ]] || install -m 644 "$SOURCE/deploy/proxy_params" /etc/nginx/proxy_params
sed "s/api\.clause\.insure/$DOMAIN/g" "$SOURCE/deploy/nginx.conf" \
    > /etc/nginx/sites-available/clause
ln -sf /etc/nginx/sites-available/clause /etc/nginx/sites-enabled/clause
rm -f /etc/nginx/sites-enabled/default

# The TLS block refuses to load before a certificate exists, so the first run
# starts with plain HTTP and certbot writes the rest.
if [[ ! -d "/etc/letsencrypt/live/$DOMAIN" ]]; then
  echo "==> first run: serving plain HTTP so the certificate can be issued"
  cat > /etc/nginx/sites-available/clause <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { proxy_pass http://127.0.0.1:8080; include /etc/nginx/proxy_params; }
}
NGINX
  nginx -t && systemctl restart nginx
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect
  # Now put the real configuration in place, over whatever certbot wrote.
  sed "s/api\.clause\.insure/$DOMAIN/g" "$SOURCE/deploy/nginx.conf" \
      > /etc/nginx/sites-available/clause
fi

nginx -t
systemctl reload nginx 2>/dev/null || systemctl restart nginx
}
front_door

echo "==> health"
# The service was restarted above; give it a moment, then ask it what it is.
# A version other than the one just installed means the unit is running
# something else (an old checkout, a failed restart), and that is a failure
# whatever the front door says.
RUNNING=""
for _ in $(seq 1 30); do
  RUNNING="$(curl -fsS --max-time 3 http://127.0.0.1:8080/api/health 2>/dev/null | "$SYSTEM_PYTHON" -c 'import json,sys; print(json.load(sys.stdin).get("version",""))' 2>/dev/null || true)"
  [[ -n "$RUNNING" ]] && break
  sleep 2
done
if [[ "$RUNNING" != "$EXPECTED" ]]; then
  echo >&2
  echo "the service at 127.0.0.1:8080 answers with version '${RUNNING:-nothing}', not $EXPECTED" >&2
  echo "logs:  journalctl -u clause -n 50" >&2
  exit 1
fi
echo "    127.0.0.1:8080/api/health: clause $RUNNING"

echo
echo "==> done"
systemctl --no-pager --lines=0 status clause.service || true
echo
echo "check it:   curl -s https://$DOMAIN/api/health"
echo "rider:      off until ANTHROPIC_API_KEY or CLAUSE_RIDER_LATCH is set"
echo "logs:       journalctl -u clause -f"
echo "settings:   $ENV_DIR/clause.env   (then: systemctl restart clause)"
