#!/usr/bin/env bash
# Additive Pydantic V4 sixteen-portfolio research SHADOW only. No extra WS, brokers or Guardian.
set -Eeuo pipefail
ROOT=/home/quant/.local/share/copytrade
RELEASE="$ROOT/releases/pydnative-v4-sixteen-0911-r2"
STATE="$ROOT/prospective/pydnative-v4-paper-sixteen-0911"
REGISTRY="$ROOT/registry/wallet_registry.sqlite"
SOURCE="$ROOT/prospective/v4-selected-sixteen-0911/paper-events.sqlite3"
PRICE="$ROOT/prospective/v4-minute-0811/paper-events.sqlite3"
MANIFEST=/home/quant/dev/copytrade-pm/data/private/gemini_phase3_phase4_eligibility_20261104.json
MANIFEST_SHA=7c0b2a021a449c06f818cacf2f757a4d40b89e77669316107dc08ca659237e6f
UNIT=copytrade-pydnative-v4-sixteen-paper-0911.service

[[ "$(id -un)" == quant ]] || { echo 'ERROR: quant user required' >&2; exit 2; }
if [[ "${1:-}" == --rollback ]]; then
  systemctl --user disable --now "$UNIT"
  systemctl --user show "$UNIT" -p ActiveState -p MainPID --no-pager || true
  echo "ROLLBACK_ONLY_NEW_CANARY; source, other paper services and canary evidence preserved"
  exit 0
fi

sha="${1:?pass exact reviewed merged SHA; --rollback to stop only new canary}"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo 'ERROR: exact 40-char SHA required' >&2; exit 2; }
repo="$(git rev-parse --show-toplevel)"
[[ -z "$(git -C "$repo" status --porcelain)" ]] || { echo 'ERROR: dirty project worktree' >&2; exit 2; }
[[ "$(git -C "$repo" rev-parse HEAD)" == "$sha" ]] || { echo 'ERROR: working tree is not exact release SHA' >&2; exit 2; }
[[ "$(git -C "$repo" ls-remote origin refs/heads/main | cut -f 1)" == "$sha" ]] || { echo 'ERROR: release is not current merged main' >&2; exit 2; }
[[ "$(sha256sum "$MANIFEST" | cut -d ' ' -f 1)" == "$MANIFEST_SHA" ]] || { echo 'ERROR: private campaign digest mismatch' >&2; exit 2; }
for p in "$SOURCE" "$PRICE" "$REGISTRY"; do
  [[ -f "$p" && ! -L "$p" ]] || { echo "ERROR: missing/linked existing input: $p" >&2; exit 2; }
done
[[ ! -L "$STATE" ]] || { echo 'ERROR: linked state root prohibited' >&2; exit 2; }

if [[ -e "$RELEASE" ]]; then
  [[ -f "$RELEASE/source.sha" && "$(cat "$RELEASE/source.sha")" == "$sha" ]] ||
    { echo 'ERROR: immutable release pin mismatch' >&2; exit 2; }
else
  [[ -d "$ROOT/releases" ]] || mkdir -m 700 "$ROOT/releases"
  mkdir -m 700 "$RELEASE"
  git -C "$repo" archive "$sha" | tar -x -C "$RELEASE"
  (cd "$RELEASE" && uv sync --frozen --group dev --extra source)
  printf '%s\n' "$sha" > "$RELEASE/source.sha"
fi
# Frozen/explicit portfolio profile and identity checks execute before service state is touched.
(
  cd "$RELEASE"
  .venv/bin/python -m copytrade_pm.pm_v4_sixteen_paper \
    --registry-db "$REGISTRY" --source-db "$SOURCE" --price-db "$PRICE" \
    --propr-catalog "$RELEASE/docs/FORWARD-PAPER-PROPR-157-THREE-SOCKETS-20261105.json" \
    --campaign-manifest "$MANIFEST" --campaign-sha256 "$MANIFEST_SHA" \
    --state-root "$STATE" --dry-run
)
mkdir -p -m 700 "$STATE"
chmod 700 "$STATE"
systemctl --user link "$RELEASE/ops/pydnative-sixteen/$UNIT"
systemctl --user daemon-reload
systemctl --user enable --now "$UNIT"
sleep 3
active="$(systemctl --user show "$UNIT" -p ActiveState --value)"
pid="$(systemctl --user show "$UNIT" -p MainPID --value)"
if [[ "$active" != active || "$pid" == 0 ]]; then
  echo "ERROR: new canary failed to start active=$active pid=$pid" >&2
  systemctl --user disable --now "$UNIT" || true
  exit 3
fi
echo "DEPLOYED_SHADOW_ONLY_SHA=$sha"
systemctl --user show "$UNIT" -p Id -p MainPID -p NRestarts -p ActiveState -p ExecStart --no-pager
