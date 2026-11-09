#!/usr/bin/env bash
# Reversible additive Pydantic-native P1 virtual SHADOW canary; no broker.
set -Eeuo pipefail
ROOT=/home/quant/.local/share/copytrade
RELEASE="$ROOT/releases/pydnative-v4-canary-0911"
STATE="$ROOT/prospective/pydnative-v4-paper-p1-0911"
SOURCE="$ROOT/prospective/v4-selected-positions-0811/paper-events.sqlite3"
PRICE="$ROOT/prospective/v4-minute-0811/paper-events.sqlite3"
REGISTRY="$ROOT/registry/wallet_registry.sqlite"
UNIT=copytrade-pydnative-v4-paper-p1-0911.service

[[ "$(id -un)" == quant ]] || { echo 'RUN_AS_QUANT_REQUIRED' >&2; exit 2; }
if [[ "${1:-}" == --rollback ]]; then
  systemctl --user disable --now "$UNIT"
  systemctl --user show "$UNIT" -p ActiveState -p MainPID -p NRestarts --no-pager
  echo 'ROLLBACK_ONLY_CANARY_JOURNALS_PRESERVED'
  exit 0
fi
sha="${1:?pass reviewed 40-character exact commit SHA}"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo 'BAD_EXACT_SHA' >&2; exit 2; }
repo="$(git rev-parse --show-toplevel)"
[[ -z "$(git status --porcelain)" ]] || { echo 'DIRTY_CHECKOUT' >&2; exit 2; }
[[ "$(git rev-parse HEAD)" == "$sha" ]] || { echo 'COMMIT_NOT_CHECKED_OUT' >&2; exit 2; }
[[ "$(git ls-remote origin refs/heads/main | cut -f 1)" == "$sha" ]] || { echo 'SHA_NOT_CURRENT_MERGED_MAIN' >&2; exit 2; }
[[ -f "$SOURCE" && -f "$PRICE" && -f "$REGISTRY" ]] || { echo 'MISSING_UPSTREAM_EVIDENCE' >&2; exit 2; }
if [[ -e "$RELEASE" ]]; then
  [[ -f "$RELEASE/source.sha" ]] && [[ "$(cat "$RELEASE/source.sha")" == "$sha" ]] || { echo 'RELEASE_PIN_MISMATCH' >&2; exit 2; }
else
  mkdir -m 700 "$RELEASE"
  git archive "$sha" | tar -xf - -C "$RELEASE"
  (cd "$RELEASE" && uv sync --frozen --group dev --extra source)
  printf '%s\n' "$sha" > "$RELEASE/source.sha"
fi
# Do not permit service installation on failed immutable signed selection.
"$RELEASE/.venv/bin/python" -m copytrade_pm.pm_forward_observed_paper \
  --source-db "$SOURCE" --price-db "$PRICE" --registry-db "$REGISTRY" \
  --price-mode vike_minute \
  --propr-catalog "$RELEASE/docs/FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.json" \
  --paper-min-notional 10 --state-root "$STATE" \
  --run-id pydnative_p1_shadow_0911 --portfolio P1 > /dev/null
chmod 700 "$STATE"
systemctl --user link "$RELEASE/ops/pydnative-canary/$UNIT"
systemctl --user daemon-reload
systemctl --user enable --now "$UNIT"
sleep 3
[[ "$(systemctl --user show "$UNIT" -p ActiveState --value)" == active ]] || { echo 'CANARY_NOT_ACTIVE' >&2; exit 3; }
[[ "$(systemctl --user show "$UNIT" -p MainPID --value)" != 0 ]] || { echo 'CANARY_MISSING_PID' >&2; exit 3; }
echo "DEPLOYED_SHADOW_ONLY sha=$sha release=$RELEASE state=$STATE"
systemctl --user show "$UNIT" -p Id -p ActiveState -p MainPID -p NRestarts -p ExecStart --no-pager
