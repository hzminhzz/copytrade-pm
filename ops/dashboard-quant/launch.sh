#!/bin/sh
# Read-only Marimo dashboard launcher for quant-owned user-systemd.
# The OS identity is quant; Bubblewrap limits the app's filesystem view.
set -eu
umask 077

ROOT=/home/quant/.local/share/copytrade-dashboard
CURRENT="$ROOT/current"
REGISTRY=/home/quant/.local/share/copytrade/registry/wallet_registry.sqlite
SOURCE_RELEASES="$ROOT/releases"

test -L "$CURRENT" || { echo "DASHBOARD_CURRENT_POINTER_REQUIRED" >&2; exit 51; }
RELEASE=$(readlink -f -- "$CURRENT")
case "$RELEASE" in "$SOURCE_RELEASES"/*) ;; *) echo "DASHBOARD_UNTRUSTED_RELEASE" >&2; exit 52;; esac
test -f "$RELEASE/dashboard.whl" || exit 53
test -x "$RELEASE/venv/bin/python" || exit 54
test -r "$REGISTRY" || exit 55
test -n "${DASHBOARD_ACCESS_SECRET:-}" || exit 56
test -n "${DASHBOARD_ALLOWED_HOSTS:-}" || exit 57
test -n "${DASHBOARD_ALLOWED_ORIGINS:-}" || exit 58

# Do not mount ~/dev, .env, the host journal, protected service roots,
# broker credentials, Docker socket or host dbus. The only private data mount
# is the canonical registry database file, bound read-only.
exec /usr/bin/bwrap \
  --unshare-all --share-net --die-with-parent --new-session --cap-drop ALL \
  --ro-bind /usr /usr \
  --ro-bind /lib /lib \
  --ro-bind /lib64 /lib64 \
  --dir /etc \
  --ro-bind /etc/ssl /etc/ssl \
  --ro-bind /etc/resolv.conf /etc/resolv.conf \
  --ro-bind /etc/hosts /etc/hosts \
  --ro-bind /etc/nsswitch.conf /etc/nsswitch.conf \
  --ro-bind /etc/passwd /etc/passwd \
  --ro-bind /etc/group /etc/group \
  --ro-bind /etc/mime.types /etc/mime.types \
  --proc /proc --dev /dev --tmpfs /tmp --dir /run \
  --dir /home --dir /home/quant \
  --dir /home/quant/.local --dir /home/quant/.local/share \
  --dir "$ROOT" --dir "$SOURCE_RELEASES" \
  --ro-bind "$RELEASE" "$RELEASE" \
  --dir /home/quant/.local/share/copytrade \
  --dir /home/quant/.local/share/copytrade/registry \
  --ro-bind "$REGISTRY" "$REGISTRY" \
  --symlink usr/bin /bin \
  --chdir "$RELEASE" \
  --setenv HOME /home/quant \
  --setenv PYTHONDONTWRITEBYTECODE 1 \
  --setenv PYTHONNOUSERSITE 1 \
  --setenv XDG_CACHE_HOME /tmp/dashboard-cache \
  --setenv XDG_CONFIG_HOME /tmp/dashboard-config \
  --setenv POLARS_MAX_THREADS 2 \
  --setenv OPENBLAS_NUM_THREADS 1 \
  --setenv OMP_NUM_THREADS 1 \
  "$RELEASE/venv/bin/python" -I -m uvicorn \
  copytrade_pm.dashboard.server:app \
  --host 127.0.0.1 --port 18777 --workers 1 \
  --no-access-log --no-proxy-headers
