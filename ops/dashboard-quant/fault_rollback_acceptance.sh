#!/bin/sh
# Deliberate failure and recovery ONLY of the independent quant-owned dashboard.
# Never targets financial units, protected journal, registry or Tailscale settings.
set -eu
ROOT=/home/quant/.local/share/copytrade-dashboard
CURRENT="$ROOT/current"
UNIT=copytrade-dashboard.service
NEXT="$ROOT/.fault-current.$$"
test -L "$CURRENT" || exit 71
TAILNET_HOST=$(tailscale status --json | jq -r '.Self.DNSName | rtrimstr(".")')
case "$TAILNET_HOST" in *.ts.net) ;; *) exit 75;; esac
PRIVATE_LOGIN="https://$TAILNET_HOST:8443/login"
if grep -q '^DASHBOARD_TAILSCALE_USER_LOGIN=' /home/quant/.config/copytrade-dashboard/private.env; then
  HEALTH_URL="https://$TAILNET_HOST:8443/"
else
  HEALTH_URL="$PRIVATE_LOGIN"
fi
PREVIOUS=$(readlink "$CURRENT")
case "$PREVIOUS" in releases/b4989bbdc098-59ba035cabeb) ;; *) exit 72;; esac

restore() {
  active=$(readlink "$CURRENT" 2>/dev/null || true)
  if [ "$active" != "$PREVIOUS" ]; then
    rm -f "$NEXT"
    ln -s "$PREVIOUS" "$NEXT"
    mv -Tf "$NEXT" "$CURRENT"
  fi
  systemctl --user reset-failed "$UNIT" || true
  systemctl --user restart "$UNIT" || true
}
trap 'restore' EXIT HUP INT TERM

# A nonexistent release tests an actual failed service start.
ln -s releases/missing-dashboard-fault-candidate "$NEXT"
mv -Tf "$NEXT" "$CURRENT"
systemctl --user restart "$UNIT" || true
sleep 2
FAILED_STATUS=$(curl --silent --show-error --max-time 4 --output /dev/null \
  --write-out '%{http_code}' \
  --user-agent 'OpenAI File Downloader, XaiImageApiFetch/1.0' \
  "$HEALTH_URL" 2>/dev/null || true)
[ "$FAILED_STATUS" != 200 ] || { echo "FAILED_START_STILL_REACHABLE" >&2; exit 73; }

# Exact pre-fault release restored atomically. No root/system financial unit touched.
rm -f "$NEXT"
ln -s "$PREVIOUS" "$NEXT"
mv -Tf "$NEXT" "$CURRENT"
systemctl --user reset-failed "$UNIT"
systemctl --user restart "$UNIT"
for i in 1 2 3 4 5 6 7 8 9 10; do
  if systemctl --user is-active --quiet "$UNIT" && \
     curl --silent --max-time 6 --output /dev/null --write-out '%{http_code}' \
       --user-agent 'OpenAI File Downloader, XaiImageApiFetch/1.0' \
       "$HEALTH_URL" | grep -qx 200
  then
    trap - EXIT HUP INT TERM
    echo "DASHBOARD_FAILED_START_ROLLBACK_VERIFIED"
    exit 0
  fi
  sleep 2
done
echo "ROLLBACK_NOT_VERIFIED" >&2
exit 74
