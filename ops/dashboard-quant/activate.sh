#!/bin/sh
# Atomic quant-user release switch with dashboard-only rollback on failed smoke.
set -eu
umask 077
[ "$(id -un)" = quant ] || exit 60
ROOT=/home/quant/.local/share/copytrade-dashboard
RID=29d006131662-aa94784c356f
SHA=aa94784c356f6fed2d39ea1922c4725a9266d145deeb6fd6f24d375f6bc9b6a7
RELEASE="$ROOT/releases/$RID"
CURRENT="$ROOT/current"
test -L "$CURRENT" || exit 61
test -f "$RELEASE/dashboard.whl" || exit 62
OBSERVED=$(sha256sum "$RELEASE/dashboard.whl")
OBSERVED=${OBSERVED%% *}
[ "$OBSERVED" = "$SHA" ] || exit 63
TAILNET_HOST=$(tailscale status --json | jq -r '.Self.DNSName | rtrimstr(".")')
case "$TAILNET_HOST" in *.ts.net) ;; *) exit 65;; esac
PRIVATE_LOGIN="https://$TAILNET_HOST:8443/login"
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
    if systemctl --user is-active --quiet copytrade-dashboard.service \
      && curl -sS --max-time 6 --output /dev/null --write-out '%{http_code}' \
         --user-agent 'OpenAI File Downloader, XaiImageApiFetch/1.0' \
         "$PRIVATE_LOGIN" | grep -qx '200' \
      && curl -sS --max-time 6 --output /dev/null --write-out '%{http_code}' \
         --user-agent 'OpenAI File Downloader, XaiImageApiFetch/1.0' \
         "https://$TAILNET_HOST:8443/" | grep -qx '303'
    then
      echo "HTTPS_DASHBOARD_ACTIVATED"
      exit 0
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
