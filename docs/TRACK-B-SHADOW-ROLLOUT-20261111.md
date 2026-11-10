# Track B v2 read-only rollout — 2026-11-11

## Explicit boundary

This change wires the existing v2 redacted strategy-health gateway and publisher bridge.
It does not create or authenticate a private original v2 assessment, infer net follower
PnL, provision an Ed25519 original-publication signer, or authorize risk. The live
gateway MUST return HTTP 503 until a fresh, independently verified redacted v2
projection exists. A 503 with no original report is an expected safe state, **not**
successful monitoring of a live campaign.

## Existing protected state to preserve

- Official selected-position source and paper workers: never restart or repin.
- Existing Grafana v1 /v1/wallet-health bytes, token/host policy, ingress and 8444 Serve.
- PM03/04, SQLite authority, original journals, protected k and Guardian.
- Before a Grafana image update, capture container IDs/digests, original release
  symlink, original v1 payload SHA, source/paper PIDs and ExecStart, Tailscale Serve route.
- Release on the same Grafana 8444 stack only, updating publisher and projection
  containers individually with their previous images preserved for rollback.
- Abort and restore the pinned v1 images if v1 SHA/GET, 403/405/400, 503-on-missing,
  or any original service invariants regress.

## Operator presentation

The v2 Grafana dashboard is versioned at
`ops/grafana-phase1/dashboards/strategy-health.json`. The existing mounted
Grafana dashboard release remains pinned until a separately verified dashboard
bundle cutover. The new read-only gateway may run safely in HTTP 503 mode
without activating the dashboard or publishing unauthenticated assessments.

## Evidence prerequisites before publishing a live strategy-health value

1. Read-only producer creates `strategy_health_assessment_v1` from original signed
   V4 first-known, SQLite selection seal and real PM03/04+market evidence;
   missing proof stays UNKNOWN. Do not substitute the retrospective Track C fills.
2. Strict 0700 private directory / 0600 original file, SHA validated.
3. Project fresh aggregate `strategy-health.json` into the existing redacted host
   health-source directory (without private report or keys).
4. Bind private report SHA and redacted file SHA using original offline
   `strategy_release_candidate.create_private_binding` and a separately
   provisioned Ed25519 publisher key, independently pin its public key.
5. Run `python -m copytrade_pm.strategy_release_candidate` on the real original
   v1 rollback snapshot. Accept only a verified binding and original v1 bytes.
6. Confirm authorized read-only HTTP GET 200, unauthorized 403, mutation method
   405, unsupported query 400, stale/corrupt/missing 503. No private fields.
7. Recheck source/paper PID, broker/Guardian access (none), original journal
   cursor, SQLite inventory seal and active k. Record exact release/build hashes.
8. Actual owner-paging transport and <=10 minute acknowledgement remain disabled
   until cadence/delivery/ACK proof exists. Scientific warning calibration is
   separate from operational installation.

## Prefect (independent opt-in)

The pinned 3.9.2 adapter accepts only a sealed 0600 immutable manifest containing
1–16 already-authoritative original assessments, their byte hashes, and an existing
owner-private 0700 output directory whose basename is `track-b-prefect-staging`.
Prefect neither generates original source inputs nor scientifically authenticates
them. Re-running a frozen manifest checks existing SHA outputs; it does not generate
new daily observations.

The supplied systemd unit/timer are **not auto-enabled**. Install them only after
(1) a pinned `copytrade-track-b/current` release with the `prefect` extra,
(2) an owner-created output path inside
`%h/.local/share/copytrade-track-b/track-b-prefect-staging`,
(3) `%h/.config/copytrade/track-b-prefect.env` mode 0600 containing only
`TRACK_B_PREFECT_MANIFEST_PATH` and `TRACK_B_PREFECT_MANIFEST_SHA256`,
(4) successful direct one-shot with exact input SHA and private 0600 receipts,
(5) crash/replay/failed-job canary and journal inspections.

The unit uses private loopback networking, bounded memory, CPU and tasks, and
read-only home except its private staging directory. Configure next genuinely
new sealed manifest explicitly; the timer cannot invent a new source campaign.
If missing or rejected, leave the timer disabled rather than fake success.

## Qualification follow-ups

- #262: full-registry read-only provider acquisition and original provenance.
- #263: matched original PM03/04 follower net, fees, funding, exits, OOS controls.
- #272: unified/portfolio-margin collateral interpretation.
- #267: independent Track C follower finance proof (not an activation by Track B).

All errors/unknowns remain UNKNOWN/INSUFFICIENT_EVIDENCE. No trading authority.
