#!/usr/bin/env bash
# Additive, reversible quant-owned virtual-paper deployment. NO broker routes.
set -Eeuo pipefail

ROOT=/home/quant/.local/share/copytrade
RELEASE="$ROOT/releases/v4-sixteen-paper-0911"
REGISTRY="$ROOT/registry/wallet_registry.sqlite"
SOURCE="$ROOT/prospective/v4-selected-sixteen-0911"
PAPER="$ROOT/prospective/v4-paper-sixteen-0911"
MANIFEST=/home/quant/dev/copytrade-pm/data/private/gemini_phase3_phase4_eligibility_20261104.json
MANIFEST_SHA=7c0b2a021a449c06f818cacf2f757a4d40b89e77669316107dc08ca659237e6f
SRC_UNIT=copytrade-v4-sixteen-source-0911.service
PAPER_UNIT=copytrade-v4-sixteen-paper-0911.service

if [[ "$(id -un)" != quant ]]; then
  echo "ERROR: run as quant, not root" >&2
  exit 2
fi

if [[ "${1:-}" == "--rollback" ]]; then
  systemctl --user disable --now "$PAPER_UNIT" "$SRC_UNIT"
  systemctl --user show "$PAPER_UNIT" "$SRC_UNIT" -p ActiveState -p MainPID --no-pager
  echo "ROLLBACK: only new sixteen-campaign units stopped; journals and older V4 untouched"
  exit 0
fi

sha="${1:?pass exact reviewed/merged 40-character commit SHA}"
if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: exact hexadecimal commit required" >&2
  exit 2
fi
repo="$(git rev-parse --show-toplevel)"
if [[ "$(git -C "$repo" rev-parse "$sha^{commit}")" != "$sha" ]]; then
  echo "ERROR: commit not accessible" >&2
  exit 2
fi
if [[ "$(sha256sum "$MANIFEST" | awk '{print $1}')" != "$MANIFEST_SHA" ]]; then
  echo "ERROR: private manifest SHA mismatch" >&2
  exit 2
fi

if [[ -e "$RELEASE" ]]; then
  if [[ ! -f "$RELEASE/source.sha" || "$(cat "$RELEASE/source.sha")" != "$sha" ]]; then
    echo "ERROR: pinned release directory already holds different or incomplete content" >&2
    exit 2
  fi
else
  mkdir -p "$ROOT/releases"
  # uv virtualenv entrypoints contain absolute paths. Build at the *final*
  # immutable path, never move a virtualenv from a temporary directory.
  mkdir -m 700 "$RELEASE"
  git -C "$repo" archive "$sha" | tar -x -C "$RELEASE"
  (
    cd "$RELEASE"
    uv sync --frozen --group dev --extra source
  )
  printf '%s\n' "$sha" > "$RELEASE/source.sha"
fi
(
  cd "$RELEASE"
  .venv/bin/python -m copytrade_pm.pm_v4_sixteen_paper \
    --registry-db "$REGISTRY" \
    --source-db "$SOURCE/paper-events.sqlite3" \
    --price-db "$ROOT/prospective/v4-minute-0811/paper-events.sqlite3" \
    --propr-catalog docs/FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.json \
    --campaign-manifest "$MANIFEST" --campaign-sha256 "$MANIFEST_SHA" \
    --state-root "$PAPER" --dry-run >/dev/null
)
mkdir -p "$SOURCE" "$PAPER"
chmod 700 "$SOURCE" "$PAPER"

systemctl --user link "$RELEASE/ops/v4-sixteen-paper/$SRC_UNIT"
systemctl --user link "$RELEASE/ops/v4-sixteen-paper/$PAPER_UNIT"
systemctl --user daemon-reload
systemctl --user enable --now "$SRC_UNIT"
# The source journal must exist before paper starts, even when official frames
# have yet to arrive. Do not backfill an earlier first-known signal.
for _ in $(seq 1 30); do
  if [[ -f "$SOURCE/paper-events.sqlite3" ]]; then
    break
  fi
  if [[ "$(systemctl --user is-active "$SRC_UNIT")" != active ]]; then
    echo "ERROR: source observer not running" >&2
    exit 3
  fi
  sleep 2
done
if [[ ! -f "$SOURCE/paper-events.sqlite3" ]]; then
  echo "ERROR: source observer failed to initialize journal" >&2
  exit 3
fi
systemctl --user enable --now "$PAPER_UNIT"
sleep 4
for unit in "$SRC_UNIT" "$PAPER_UNIT"; do
  state="$(systemctl --user show "$unit" -p ActiveState --value)"
  pid="$(systemctl --user show "$unit" -p MainPID --value)"
  if [[ "$state" != active || "$pid" == 0 ]]; then
    echo "ERROR: new service not live: $unit state=$state pid=$pid" >&2
    systemctl --user disable --now "$PAPER_UNIT" "$SRC_UNIT" || true
    exit 3
  fi
done
printf 'DEPLOYED_VIRTUAL_PAPER_ONLY commit=%s release=%s\n' "$sha" "$RELEASE"
systemctl --user show "$SRC_UNIT" "$PAPER_UNIT" -p Id -p ActiveState -p MainPID -p NRestarts --no-pager
systemctl --user show copytrade-v4-paper-p1-0811.service copytrade-v4-paper-p14-0811.service copytrade-v4-paper-p16-0811.service -p Id -p ActiveState -p MainPID --no-pager
