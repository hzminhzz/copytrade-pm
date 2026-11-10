# Track B v2 — separately approvable SHADOW release and rollback package

Date: 2026-11-10. Specification #273, implementation tickets #274–#288.
THIS IS A RELEASE CANDIDATE, NOT DEPLOYMENT OR TRADING AUTHORIZATION.

## Read-only baseline actually observed on VPS

| Protected component | Observed state | Existing executable/release binding |
| --- | --- | --- |
| Official selected 16-account V4 source producer | active (running) | copytrade-v4-sixteen-source-0911.service; /home/quant/.local/share/copytrade/releases/v4-sixteen-paper-0911/.venv/bin/python |
| Original 16-account paper owner | active (running) | copytrade-v4-sixteen-paper-0911.service; same existing pinned v4-sixteen-paper-0911 environment |
| Existing Grafana Phase 1 gateway | active (exited launcher) | copytrade-grafana.service; /home/quant/.local/share/copytrade-grafana/current/ops/grafana-phase1/production.sh |
| Wallet-health v1 supervision service | inactive (dead) at inspection | copytrade-wallet-health.service; do not infer v1 production health from this status |
| Tailnet Grafana ingress | read-only Tailscale Serve listing observed | HTTPS, tailnet only, hostname vmi2637217-1.tailbcb51e.ts.net, port 8444, unix socket /run/copytrade-grafana-phase1/serve.sock |

The read-only preflight was performed in the same VPS context as the feature worktree. Source/paper releases and live 8444 ingress are NOT targets of this PR. A running service alone does not prove its Git source commit, owner SLA, production data correctness or whether the new v2 code has ever been loaded. No service was started, stopped or restarted in this program.

## Candidate identity and private/public receipt split

- Code candidate: isolated feature branch feat/track-b-v2-strategy-health-273-20261110; base remote SHA 5df554dce30a3bc7b6df455754aa0fab8c557295. Pin the exact final PR head SHA and build-artifact SHA256 in the PR receipt after all checks. Do not self-embed a commit's own SHA into its commit.
- Private original: strict strategy_health_assessment_v1, owner-created 0700 directory and 0600 no-clobber sealed report; contains selected source, campaign, policy/k, first-known opportunities, original evidence, finance UNKNOWN flags, and advisory.
- Separate owner-private publication link: strategy_health_publication_binding_v1, signed with an OUT-OF-REPO Ed25519 private publisher key; contains original private report byte SHA, strict report seal, public aggregate byte SHA, publisher alias and publication time. Signed binding also stays 0600. Public key must be independently pinned by the operator; a private publication signature is NOT independent financial proof.
- Redacted public artifact: strategy_health_grafana_v1 in strategy-health.json. Only aggregate counters/warning state/incident count and broad evidence class; no wallet address, policy k, source/PM03/Track C receipts, private report SHA, original file path, or owner identity. New GET-only /v1/strategy-health route is opt-in on a future authorized rollout.
- Original wallet-health Grafana v1 remains independent: wallet-health.json and existing /v1/wallet-health contract unchanged. The v2 parser refuses stale (>900 seconds), malformed, oversized or changed-hash files with 503.
- Release verifier: python -m copytrade_pm.strategy_release_candidate. Its CLI only reads already created private report, signed binding, public aggregate, independent publisher public key and ORIGINAL wallet-health v1 rollback snapshot, then prints a nonactivating JSON attestation. It contains no publish/merge/restart/trade switch.

## Offline candidate proof (current branch, no live writes)

1. Record exact current original release path/commit and Grafana/Tailscale ingress from read-only systemctl show and tailscale serve status. Recheck rather than reuse this snapshot for future deployment.
2. Freeze the candidate Python dependency lock and build SHA. Run full tests, 24 Q32 injections, Ruff, build, capability validation, with the exact Git SHA. Record all skipped tests.
3. In an isolated 0700 nonproduction directory owned by the operator, produce a representative selected SHADOW assessment from **verified original V4 and SQLite** inputs if such evidence exists; otherwise use a clearly labeled RESEARCH_SYNTHETIC fixture that cannot become an approved live health signal.
4. Generate the redacted strategy-health.json in a separate nonproduction projection directory. Do not put the private assessment, source addresses, publisher keys, or private signed binding in the web root.
5. Using an independently provisioned publisher signing key, explicitly create the private binding with strategy_release_candidate.create_private_binding(private_report, projection_directory, private_binding_path=..., publisher_alias=..., signer=...). Do not store the signing key in the repo, test output, CI logs or Grafana.
6. Pin the publisher public key. Preserve a copy of the ACTUAL v1 wallet-health.json as a rollback checkpoint and calculate its SHA256. If this snapshot does not exist or cannot be verified, block release attestation; never fabricate the v1 baseline.
7. Run the read-only nonactivating verifier in staging using real absolute paths:

    uv run --frozen --extra dashboard python -m copytrade_pm.strategy_release_candidate \
      --private-report /operator-private/assessment.json \
      --private-binding /operator-private/signed-publication.json \
      --publisher-public-key /operator-private/publisher-public-key.raw \
      --projection-dir /isolated-projection \
      --v1-wallet-health /v1-baseline/wallet-health.json \
      --as-of 2026-11-10T08:00:00+00:00

Replace placeholder paths/timestamp with actual operator-pinned values. The verifier fails on invalid private permissions, stale v2 projection, altered v1 schema, untrusted/mismatched publication signature, mismatched original private report, or wrong public aggregate. A successful candidate receipt reports DEPLOYED=false, TRADING_AUTHORIZED=false, OWNER_PAGING_ACTIVE=false, SCIENTIFICALLY_QUALIFIED=false and asks for separate deployment authorization.

## Separately gated SHADOW deployment (NOT EXECUTED)

Before a separate explicit authorization, the operator must independently record: live deployed revision (not just a symlink), exact systemd unit drop-ins/ExecStart, live Tailscale 8444 ingress binding, service account identity, read-only source journal head, selected SQLite portfolio/version seal, original PM03/PM04 journal identities, v1 wallet-health payload SHA, original Grafana config SHA and environment provenance without exposing credentials.

After explicit authorization only, stage the new code at a reversible isolated release path; maintain original source/paper executable pins and PM03/PM04 journals unchanged. Enable the new route and evidence publication solely through read-only Grafana code. Do not alter source subscription selection, first-known signals, 5-minute batch, frozen k, broker connections, source writers or protected financial authority.

Acceptance probes from a trusted tailnet client (record HTTP codes and payload redaction, not tokens):

| Probe | Expected |
| --- | --- |
| GET /v1/strategy-health with correct configured auth and fresh sealed aggregate | 200, strict allowlisted schema, no private identifiers |
| Same GET without/with wrong auth | 403 (or existing ingress-specific rejection) |
| POST/PUT/DELETE to new v2 route | 405, never a write |
| GET with mutation-style query/body | 400 or existing fixed-route rejection |
| Corrupt, stale, missing, symlinked v2 publication | 503 fail closed, no stale warning clearance |
| GET original /v1/wallet-health | same v1 authorization, content and byte SHA as pinned; no replacement |
| Source/market journal heads, selected SQLite definition, PM03/PM04 ledger and active k | no unauthorized mutations attributable to v2 |
| Original active source and paper services | exactly original pinned units/revisions, no restarts by Track B |
| No new network mutations | no Guardian, broker, webhooks or paging from Track B |

Synthetic HTTP tests validate code behavior, NOT the actual production ingress. The v2 deployed-route status must stay PENDING until a separately authorized endpoint canary records it.

## Operational owner-route and cadence gate

The two-cycle notification design is not a timer-only heuristic and never delays the original immediate source-GAP risk fence. Before enabling any owner page: independently measure selected-source expected-observation cadence from original producer metadata and actual misses, establish real owner/on-call route alias and notification transport, test two missed expected cycles without speculative gaps, verify delivery receipt, and observe a real acknowledgement timestamp <=10 minutes **from delivery**, not from fault detection. An incomplete cycle proof, unconfirmed route or unverified delivery keeps OWNER_PAGING_ACTIVE=false and SLA=PENDING. A research fixture's ACK target is not a measured SLA.

## Reversible rollback plan (after separate authorization only)

Trigger on new v2 redaction leak, version/signature drift, stale 503 without timely recovery, operational paging without cadence/route proof, v1 HTTP regression, unexpected source/finance-state mutation, or Grafana failure.

1. Preserve immutable incident evidence and private report/binding; immediately disable isolated v2 publication and route in the candidate release only (do not remove v1).
2. Re-point the Grafana candidate to the previously SHA-pinned v1 release/config using the platform's approved reversible release procedure; restart/reload ONLY the authorized Grafana service if that procedure requires it. NEVER restart source or paper services for a v2 health rollback.
3. Verify old /v1/wallet-health behavior and v1 payload SHA. Verify v2 endpoint absent/503 as prescribed by rollback policy and that the 8444 tailnet service still accepts authorized original access.
4. Compare original source cursor/hash chain, first-known T+300 journal identities, PM03/PM04 ledger head and financial guards, and SQLite portfolio/selection seal against independently recorded baseline. Active writers may advance natural cursors; compare causally valid heads/approved changes, not naive byte equality of a mutable WAL file.
5. Confirm original source/paper unit PIDs/revisions unaffected by Track B, existing frozen k unchanged, risk HALT latch unchanged, no broker trades or Guardian commands from v2, and owner paging disabled.
6. Record full pre/after rollback receipts, timestamps, authorized approver, exact rollback head SHA, regression probes, observed unknowns and cleanup actions. Keep immutable private evidence; do not delete original journals or keys.

## Current decision / pending blockers

Engineering code/tests and offline release candidate can be reviewed. No merge, deployment, canary, endpoint switch, source/PM04 mutation, active k release, owner alert or trading authorization occurred here.

Pending independently verified selected source/registry and economic evidence, qualified matched market/fee/funding costs, scientifically calibrated alerts, original Track C version-aware release consumer (#267/#268), live publisher signing identity/key, actual v1 rollback checkpoint, original deployed commit SHA, observed cadence and owner route, and separate release/rollback authorization.

Decision requested at review time: approve **merge** and/or a **separate 14–16 selected-account SHADOW-only canary** only after the stated independent gates. This documentation is not such approval.
