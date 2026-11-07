#!/bin/sh
# Switch only the quant dashboard's current release. Preserve previous pointer.
set -eu
umask 077
[ "$(id -un)" = quant ] || exit 60
ROOT=/home/quant/.local/share/copytrade-dashboard
RID=b4989bbdc098-59ba035cabeb
SHA=59ba035cabeb55dc6c64e3c90ef28cdb704ce1afd44c6dc89a7cdc987099cc16
RELEASE="$ROOT/releases/$RID"
CURRENT="$ROOT/current"
ENV_FILE=/home/quant/.config/copytrade-dashboard/private.env
test -L "$CURRENT" || exit 61
test -f "$RELEASE/dashboard.whl" || exit 62
OBSERVED=$(sha256sum "$RELEASE/dashboard.whl")
OBSERVED=${OBSERVED%% *}
[ "$OBSERVED" = "$SHA" ] || exit 63
TAILNET_HOST=$(tailscale status --json | jq -r '.Self.DNSName | rtrimstr(".")')
case "$TAILNET_HOST" in *.ts.net) ;; *) exit 65;; esac
PRIVATE_BASE="https://$TAILNET_HOST:8443"
if grep -q '^DASHBOARD_TAILSCALE_USER_LOGIN=' "$ENV_FILE"; then
  EXPECT_LOGIN=303
  EXPECT_ROOT=200
else
  EXPECT_LOGIN=200
  EXPECT_ROOT=303
fi
PREVIOUS=$(readlink "$CURRENT")
case "$PREVIOUS" in releases/*) ;; *) exit 64;; esac
[ "$PREVIOUS" != "releases/$RID" ] || { echo "ALREADY_ACTIVE"; exit 0; }
NEXT="$ROOT/.current.$$"
trap 'rm -f "$NEXT"' EXIT HUP INT TERM
ln -s "releases/$RID" "$NEXT"
mv -Tf "$NEXT" "$CURRENT"
systemctl --user reset-failed copytrade-dashboard.service
if systemctl --user restart copytrade-dashboard.service; then
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if systemctl --user is-active --quiet copytrade-dashboard.service; then
      login_status=$(curl -sS --max-time 6 --output /dev/null --write-out '%{http_code}' "$PRIVATE_BASE/login" 2>/dev/null || true)
      root_status=$(curl -sS --max-time 6 --output /dev/null --write-out '%{http_code}' "$PRIVATE_BASE/" 2>/dev/null || true)
      if [ "$login_status" = "$EXPECT_LOGIN" ] && [ "$root_status" = "$EXPECT_ROOT" ]; then
        echo "HTTPS_DASHBOARD_ACTIVATED"
        exit 0
      fi
    fi
    sleep 2
  done
fi
echo "ACTIVATION_FAILED_ROLLING_BACK" >&2
ln -s "$PREVIOUS" "$NEXT"
mv -Tf "$NEXT" "$CURRENT"
systemctl --user reset-failed copytrade-dashboard.service
systemctl --user restart copytrade-dashboard.service
exit 70
