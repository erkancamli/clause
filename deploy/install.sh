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
echo "==> installing from $SOURCE for $DOMAIN"

echo "==> packages"
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip rsync nginx certbot python3-certbot-nginx sqlite3

echo "==> user and directories"
id -u clause >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin clause
mkdir -p "$APP_DIR" "$ENV_DIR" "$STATE_DIR"

echo "==> code"
# The venv is kept across runs; only the source is replaced.
rsync -a --delete --exclude .venv --exclude '__pycache__' \
      --exclude '.pytest_cache' --exclude 'node_modules' --exclude 'hazard_build' \
      --exclude 'privy-bundle' "$SOURCE"/ "$APP_DIR"/
chown -R clause:clause "$APP_DIR" "$STATE_DIR"
chmod 750 "$STATE_DIR"

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
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chown -R clause:clause "$APP_DIR/.venv"

# Prove it runs before the service is told to run it, and prove it runs the way
# the service will: as the clause user, from the directory the unit uses. Both
# halves matter. Running it from wherever the installer happens to sit tests
# nothing, and fails anyway when that is a home directory the clause user
# cannot enter, which is a fault in the test rather than in the install.
CHECK="$(cd "$APP_DIR" && setpriv --reuid=clause --regid=clause --clear-groups \
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

echo "==> configuration"
if [[ ! -f "$ENV_DIR/clause.env" ]]; then
  sed "s/api\.clause\.insure/$DOMAIN/g" "$SOURCE/deploy/clause.env.example" \
      > "$ENV_DIR/clause.env"
  echo "    wrote $ENV_DIR/clause.env; read it before going live"
else
  echo "    $ENV_DIR/clause.env exists, left alone"
fi
# The two demonstration switches. Each is added once, to a file written by
# an older version of this script that never mentioned it; any line that
# names the setting, on or off, commented or not, is the operator's decision
# and is left exactly as it is.
mentioned() { grep -qE "^[[:space:]]*#?[[:space:]]*$1=" "$ENV_DIR/clause.env"; }
if ! mentioned CLAUSE_SPECIMENS; then
  printf '\n# Stand in companies in every country, each marked as not a real company.\n# Set to 0 before real companies register.\nCLAUSE_SPECIMENS=1\n' >> "$ENV_DIR/clause.env"
  echo "    turned on stand in companies in every country (CLAUSE_SPECIMENS=1)"
fi
if ! mentioned CLAUSE_FAUCET; then
  printf '\n# Demonstration money: new addresses are funded, and My cover has a top up\n# button. Set to 0 before anything real is sold.\nCLAUSE_FAUCET=1\n' >> "$ENV_DIR/clause.env"
  echo "    turned on demonstration money (CLAUSE_FAUCET=1)"
fi
chmod 600 "$ENV_DIR/clause.env"
chown root:root "$ENV_DIR/clause.env"

echo "==> service"
install -m 644 "$SOURCE/deploy/clause.service" /etc/systemd/system/clause.service
systemctl daemon-reload
systemctl enable clause.service
systemctl restart clause.service

echo "==> nginx"
# nginx will not start if something already holds port 80, and the failure that
# follows is three steps downstream: no certificate, no https, and a curl that
# returns nothing. Name the occupant here instead.
if ! systemctl is-active --quiet nginx; then
  HOLDER="$(ss -ltnpH '( sport = :80 )' 2>/dev/null | head -1 || true)"
  if [[ -n "$HOLDER" ]]; then
    echo >&2
    echo "port 80 is already taken, so nginx cannot start:" >&2
    echo "  $HOLDER" >&2
    echo >&2
    echo "That is something else you are already running, so nothing here will" >&2
    echo "touch it. Put this domain on the proxy that is already there instead:" >&2
    echo "deploy/README.md has the block to add, for Caddy, Apache and Docker." >&2
    echo >&2
    echo "Nothing has been broken. The protocol itself is installed, enabled" >&2
    echo "and listening on 127.0.0.1:8080; all it lacks is a front door." >&2
    systemctl disable --now nginx >/dev/null 2>&1 || true
    exit 1
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

echo
echo "==> done"
systemctl --no-pager --lines=0 status clause.service || true
echo
echo "check it:   curl -s https://$DOMAIN/api/health"
echo "rider:      off until ANTHROPIC_API_KEY or CLAUSE_RIDER_LATCH is set"
echo "logs:       journalctl -u clause -f"
echo "settings:   $ENV_DIR/clause.env   (then: systemctl restart clause)"
