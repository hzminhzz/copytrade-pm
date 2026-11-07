#!/bin/sh
# Activate owner-identity SSO on the existing quant-owned dashboard.
# A failed startup/HTTP identity check restores the password-mode env.
set -eu
umask 077
[ "$(id -un)" = quant ] || exit 60
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV=/home/quant/.config/copytrade-dashboard/private.env
TAILNET_HOST=$(tailscale status --json | jq -r '.Self.DNSName | rtrimstr(".")')
case "$TAILNET_HOST" in *.ts.net) ;; *) exit 64;; esac
BASE="https://$TAILNET_HOST:8443"
test -f "$ENV" || exit 62

restore() {
  /usr/bin/python3.14 "$HERE/configure_tailnet_sso.py" rollback
  systemctl --user reset-failed copytrade-dashboard.service || true
  systemctl --user restart copytrade-dashboard.service || true
}
trap 'restore' EXIT HUP INT TERM
/usr/bin/python3.14 "$HERE/configure_tailnet_sso.py" enable
systemctl --user reset-failed copytrade-dashboard.service
systemctl --user restart copytrade-dashboard.service
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if systemctl --user is-active --quiet copytrade-dashboard.service; then
    root_status=$(curl --silent --show-error --max-time 6 --output /dev/null --write-out '%{http_code}' "$BASE/" 2>/dev/null || true)
    login_status=$(curl --silent --show-error --max-time 6 --output /dev/null --write-out '%{http_code}' "$BASE/login" 2>/dev/null || true)
    direct_status=$(curl --silent --show-error --max-time 6 --output /dev/null --write-out '%{http_code}' http://127.0.0.1:18777/ 2>/dev/null || true)
    if [ "$root_status" = 200 ] && [ "$login_status" = 303 ] && [ "$direct_status" = 403 ]; then
      trap - EXIT HUP INT TERM
      echo "TAILSCALE_OWNER_SSO_ACTIVE_NO_VIEWER_PASSWORD"
      exit 0
    fi
  fi
  sleep 2
done
echo "TAILSCALE_OWNER_SSO_FAILED_ROLLED_BACK" >&2
exit 71
