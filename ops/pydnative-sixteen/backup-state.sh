#!/usr/bin/env bash
# Immutable private backup of only the new 16-ledger Pydantic SHADOW canary.
set -Eeuo pipefail
ROOT=/home/quant/.local/share/copytrade
STATE="$ROOT/prospective/pydnative-v4-paper-sixteen-0911"
BACKUPS="$ROOT/backups/pydnative-v4-sixteen-0911"
UNIT=copytrade-pydnative-v4-sixteen-paper-0911.service

[[ "$(id -un)" == quant ]] || { echo 'ERROR: run as quant' >&2; exit 2; }
[[ "$(systemctl --user show "$UNIT" -p ActiveState --value)" != active ]] ||
  { echo 'ERROR: stop only the new canary before snapshot' >&2; exit 2; }
[[ -d "$STATE" && ! -L "$STATE" ]] ||
  { echo 'ERROR: canary state root missing or linked' >&2; exit 2; }
umask 077
mkdir -p -m 700 "$BACKUPS"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$BACKUPS/$stamp.tar"
[[ ! -e "$out" ]] || { echo 'ERROR: backup timestamp already exists' >&2; exit 2; }
tar -C "$ROOT/prospective" -cf "$out" pydnative-v4-paper-sixteen-0911
tar -tf "$out" >/dev/null
sha256sum "$out"
printf 'BACKUP_VERIFIED=%s\n' "$out"
