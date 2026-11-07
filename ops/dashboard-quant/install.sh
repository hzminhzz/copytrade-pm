#!/bin/sh
# Installs only a new quant-owned read-only dashboard user service.
# Strictly no sudo, protected-service operations or existing Tailscale changes.
set -eu
umask 077

[ "$(id -un)" = quant ] || { echo "EXPECTED_QUANT_USER" >&2; exit 60; }
ROOT=/home/quant/.local/share/copytrade-dashboard
RID=a51d0a675f2-cfaf2c4136f4
SHA=cfaf2c4136f4705402bac7018ac469669136c9517a47890dee2918bbc964871f
RELEASE="$ROOT/releases/$RID"
ENV_DIR=/home/quant/.config/copytrade-dashboard
ENV_FILE="$ENV_DIR/private.env"
UNIT_DIR=/home/quant/.config/systemd/user
UNIT="$UNIT_DIR/copytrade-dashboard.service"
CURRENT="$ROOT/current"
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

test -d "$RELEASE/venv" || exit 61
test -r "$RELEASE/dashboard.whl" || exit 62
OBSERVED=$(sha256sum "$RELEASE/dashboard.whl")
OBSERVED=${OBSERVED%% *}
[ "$OBSERVED" = "$SHA" ] || { echo "RELEASE_WHEEL_HASH_MISMATCH" >&2; exit 63; }
[ ! -e "$UNIT" ] && [ ! -L "$UNIT" ] || { echo "EXISTING_DASHBOARD_UNIT_REFUSED" >&2; exit 64; }
[ ! -e "$CURRENT" ] && [ ! -L "$CURRENT" ] || { echo "EXISTING_DASHBOARD_POINTER_REFUSED" >&2; exit 65; }
[ ! -e "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ] || { echo "EXISTING_DASHBOARD_SECRET_REFUSED" >&2; exit 66; }

# Never commit the tailnet hostname; provide it only at installation time.
TAILNET_HOST=${DASHBOARD_TAILNET_HOST:-}
case "$TAILNET_HOST" in *.ts.net) ;; *) echo "PRIVATE_TAILNET_HOST_REQUIRED" >&2; exit 67;; esac
install -d -m 700 "$ENV_DIR"
SECRET=$(openssl rand -hex 32)
{
  printf 'DASHBOARD_ACCESS_SECRET=%s\n' "$SECRET"
  printf 'DASHBOARD_ALLOWED_HOSTS=%s,localhost,127.0.0.1\n' "$TAILNET_HOST"
  printf 'DASHBOARD_ALLOWED_ORIGINS=https://%s:8443,http://localhost:18777,http://127.0.0.1:18777\n' "$TAILNET_HOST"
  printf 'DASHBOARD_GUARDIAN_CAPTURE_ROOT=\n'
  printf 'DASHBOARD_NOTIFICATION_STATE_FILE=\n'
  printf 'DASHBOARD_RESEARCH_CACHE_ROOT=\n'
} > "$ENV_FILE"
unset SECRET
chmod 600 "$ENV_FILE"
install -m 700 "$SOURCE_DIR/launch.sh" "$ROOT/launch.sh"
install -m 600 "$SOURCE_DIR/copytrade-dashboard.service" "$UNIT"
# Immutable snapshot for the process; future upgrades use a new release directory.
chmod -R a-w "$RELEASE"
ln -s "releases/$RID" "$CURRENT"
systemctl --user daemon-reload
systemctl --user enable --now copytrade-dashboard.service
echo "DASHBOARD_USER_UNIT_INSTALL_ATTEMPTED"
