# Copytrade Ops Control Center — isolated read-only sidecar

**Owner:** copytrade-pm. **Effective:** 2026-11-11. **Authority:** visualization only (`NO_TRADE`). The existing Grafana/Tailscale operator surface, Guardian, registry and PM03/PM04 remain separate authorities. This sidecar does not supersede the Grafana cutover contracts or make trading/paper qualification decisions.

## Why

The previous site served a manually patched Vinext/Next pre-rendered HTML plus separate minified bundle. They could diverge and cause React hydration error #418. Its public origin exposed unauthenticated POST/PATCH routes that could overwrite statuses in an operations notes database. Historic seeded notes were displayed as verified/live, and a registry selection was conflated with running paper execution. The original untracked site remains in the primary checkout; it is not deleted or overwritten.

## Boundary and source ownership

- **Frontend**: `ops/control-center/src/` is the single TypeScript/React source. Vite produces one client-only, reproducibly built HTML + content-hashed JS/CSS set. No server-side hydration, manual chunk patch, Cloudflare worker, D1 or duplicate state writer.
- **HTTP read projection**: `scripts/dashboard_server.py` listens on `127.0.0.1:8888` under `copytrade-ops-center.service`; only GET `/api/state`, `/api/records`, and `/api/health`. No write method or permissive CORS, no broker integration, no API secrets. Hash-named assets cache immutably; HTML and dynamic API use no-store. Security headers prevent iframe mounting and restrictive asset loading.
- **SQLite**: registry metadata, projection expert equity diagnostic, and imported operations notes opened with `mode=ro`, bounded snapshot and connection cleanup. A singleflight 8-second read cache bounds concurrent WAL readers. No `CREATE TABLE`, startup seed, migration, update, journal checkpoint or production registry mutation.
- **Evidence**: cached registry identity, saved seal aliases and observable projected equity are metadata, not current health, scientific qualification, paper PnL or follower sizing. `inventorySha256` remains unknown until independently verified. Import-page drawdown is excluded rather than manufactured from current equity plus loss; missing health and risk are explicitly unknown.
- **Portfolio semantics**: `portfolio_seals` are versioned research definitions. Their `portfolio_memberships.member_alias` is read as sealed; do not reinterpret earlier history using later alias mappings. A saved member count is not a running pod count. The separate 16-portfolio virtual-paper campaign does not change the registry's number of seals.
- **Fixed k**: the true default is `FIXED_K_NATIVE_QUANTITY`: signed per-pod `k × source_native_quantity × source_mark`, translated at independent follower quotes, with actual Guardian follower risk controls. The dashboard has no capacity to calculate/authorize orders from `projection.db` equity.
- **Legacy notes**: any `ops_dashboard.sqlite` record is an imported *claim*: `reportedStatus` retains the raw label; outward `status=pending`, `quality=unverified` until independently attested. No seed records are created. This is a deliberate conservative downgrade of historical UI annotations, not an edit to the original notes.

## Build and acceptance

From repository root:

```sh
cd ops/control-center && npm ci --no-audit --no-fund && npm run build
cd ../..
uv run --frozen --group dev pytest -q tests/test_ops_control_center.py
uv run --frozen --group dev ruff check scripts/dashboard_server.py scripts/deploy_ops_control_center.py tests/test_ops_control_center.py
node ops/control-center/tests/browser.cjs
```

The browser suite starts its own loopback canary, probes public mutation denial, checks state against actual registry data, validates main navigation, sorting/search/comparison, light/dark theme, and browser JS errors at 1440×900, 768×1024, and 390×844. `TARGET_URL=https://ops.hzminhzz.space/` checks the active Cloudflare route instead. No trade mutation or hosted-site cookie is used.

## Deployment and rollback (after verified merge)

Never run the public server from an editable checkout. From a clean source tree containing the deployment script:

```sh
python3 scripts/deploy_ops_control_center.py --revision origin/main
python3 scripts/deploy_ops_control_center.py --revision origin/main --apply
```

The apply operation checks the exact commit SHA, creates a detached pinned worktree under `~/.local/share/copytrade/releases/ops-control-center-<SHA12>`, runs `npm ci`, production TypeScript/Vite build, and Playwright canary **before** changing the service. It atomically replaces the *user* systemd unit after a private 0600 backup, restarts, verifies the service SHA and `NO_TRADE` API and live registry status, and restores the previous unit automatically if cutover health fails. It does not alter Cloudflare DNS, tunnel credentials, or any upstream research/Guardian unit.

The deploy receipt includes the rollback backup basename. Roll back to that specific saved unit:

```sh
python3 scripts/deploy_ops_control_center.py --rollback-unit <BACKUP_BASENAME> --apply
```

Verify `systemctl --user status copytrade-ops-center.service`, `GET /api/health`, `GET /api/state`, and the public HTTPS front door after any action. Do not describe a newly merged commit as deployed until the unit's OS PID and SHA match.

## Explicit exclusions

Cloudflare currently publishes the read-only web/API surface at `https://ops.hzminhzz.space/`. **Public access is not authentication.** The API hides raw wallet addresses but exposes aliases, saved research portfolio names, and projected equity diagnostics. If privacy is required, add Cloudflare Access (or another verified ingress owner) with a separate authorization decision; do not infer security from an obscure URL.

Research selection, paper-running status, current broker risk budgets, live Guardian health and trading authorization remain UNKNOWN or NO_TRADE. Historical notes and passing tests do not upgrade their authority.
