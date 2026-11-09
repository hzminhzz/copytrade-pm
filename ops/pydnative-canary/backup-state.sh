#!/usr/bin/env bash
# Snapshot only the new private Pydantic V4 P1 canary, never producer journals.
set -Eeuo pipefail
ROOT=/home/quant/.local/share/copytrade
UNIT=copytrade-pydnative-v4-paper-p1-0911.service
STATE="$ROOT/prospective/pydnative-v4-paper-p1-0911"
BACKUPS="$ROOT/backups/pydnative-v4-paper-p1-0911"
[[ "$(id -un)" == quant ]] || { echo 'QUANT_REQUIRED' >&2; exit 2; }
[[ "$(systemctl --user show "$UNIT" -p ActiveState --value)" != active ]] || { echo 'STOP_CANARY_BEFORE_BACKUP' >&2; exit 2; }
[[ -d "$STATE" && ! -L "$STATE" ]] || { echo 'CANARY_STATE_MISSING_OR_SYMLINK' >&2; exit 2; }
umask 077
mkdir -p -m 700 "$BACKUPS"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$BACKUPS/$stamp.tar"
[[ ! -e "$out" ]] || { echo 'BACKUP_ALREADY_EXISTS' >&2; exit 2; }
tar -C "$ROOT/prospective" -cf "$out" pydnative-v4-paper-p1-0911
tar -tf "$out" >/dev/null
sha256sum "$out"
echo "BACKUP_VERIFIED=$out"
