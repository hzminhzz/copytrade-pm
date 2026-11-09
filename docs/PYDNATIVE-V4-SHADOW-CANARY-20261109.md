# Pydantic-native V4 P1 SHADOW operational acceptance — 2026-11-09

## Disposition

**DEPLOYED_SHADOW_CANARY / RUNNING_OBSERVED; #229 remains OPEN.**

Owner's separate deployment authorization is recorded in issue #229 and the
2026-11-09 conversation. This release is **additive and virtual-paper only**.
No protected finance, signer authority, Guardian, portfolio fleet, existing
service, broker credential or order route was changed.

- PR #246 merged: `1989e65fb0a8bfa8bf48baeacecd4355dbd998e3`.
- Installed source SHA: `1989e65fb0a8bfa8bf48baeacecd4355dbd998e3`.
- OS user: `quant`.
- Release: `/home/quant/.local/share/copytrade/releases/pydnative-v4-canary-0911`.
- New user unit: `copytrade-pydnative-v4-paper-p1-0911.service`.
- Initial PID `547815`; verified restart/restore PID `555771`, `NRestarts=0`,
  active/running and enabled at 2026-11-09T10:01 UTC.
- New private run root:
  `/home/quant/.local/share/copytrade/prospective/pydnative-v4-paper-p1-0911/pydnative_p1_shadow_0911`.
- Selected sealed portfolio: `P1`, version 2, SHA
  `0862c6dd3e1932182d3c4b2d38c3edea42dee11cf2b27c4be04b0eae6df0c4de`.
  Members `S035-ENA`, `S051-BTC`, `S053-HYPE`.
- One **existing** official V4 selected-account WS producer reused with source
  `/home/quant/.local/share/copytrade/prospective/v4-selected-positions-0811/paper-events.sqlite3`.
  Existing independent Vike minute source:
  `/home/quant/.local/share/copytrade/prospective/v4-minute-0811/paper-events.sqlite3`.
  No extra WebSocket source service was installed.

## Exact artifact and data hashes

- Installed `uv.lock` SHA-256:
  `182c79eb81920f0b42064a91c7b3775cb3e8f53a059a854e28b05b100e09369e`.
- Installed new unit SHA-256:
  `ec1e16b23245fd356e77e501d52cbd1919ab9a5c13ef631783c65b5db55d1d64`.
- Initial and post-rollback `events.jsonl` SHA-256:
  `9c9afa34da18aed5078a7774625bd9c387cb88b1136e78224ca0cf9fbb668390`.
- Private stopped-state backup archive:
  `/home/quant/.local/share/copytrade/backups/pydnative-v4-paper-p1-0911/20261109T100048Z.tar`,
  SHA-256 `759362bc6bc928d6a70c7bd086aebc56e70d6d03f5697d30562c21bda7c125fe`;
  `tar -tf` verification passed.
- Source stream audit: `verify_streams(...).integrity=VERIFIED`,
  `order_route=NONE`, `paper_admitted=false`.
  Sampled source stream head digest
  `a074ef8cc943c04bd826a03e3e4b06697b19e231fe4276adba3df83e7a979247`
  at approximately 2026-11-09T09:58 UTC. This head is live and advances,
  so it is not a permanent release hash.

## Executed checks

```bash
uv run --frozen --all-extras --group dev pytest -q
# 1757 passed, 3 skipped in 55.14 s
uv run --frozen --group dev pytest -q tests/test_pydantic_crossrepo_contracts.py tests/test_pydantic_combined_authorities.py tests/test_pydantic_halt_origins.py tests/test_pm_forward_observed_paper.py
# 14 passed, 1 skipped
uv run --frozen --group dev ruff check .
# All checks passed
uv run --frozen --group dev ruff format --check .
# 561 files already formatted
uv run --frozen --group dev copytrade-pm capabilities validate
# status VERIFIED; 113 capabilities, errors=[]
uv run --frozen --group dev copytrade-wallet-registry doctor
# database_integrity VERIFIED; research_selection_integrity VERIFIED
# indexed import freshness STALE, runtime admission UNKNOWN
bash ops/pydnative-canary/deploy.sh 1989e65fb0a8bfa8bf48baeacecd4355dbd998e3
systemctl --user show copytrade-pydnative-v4-paper-p1-0911.service -p MainPID -p ActiveState -p NRestarts
# active, PID 547815, restarts 0 initially
bash ops/pydnative-canary/deploy.sh --rollback
# stopped/disabled ONLY the new unit, journal hash preserved
systemctl --user link /home/quant/.local/share/copytrade/releases/pydnative-v4-canary-0911/ops/pydnative-canary/copytrade-pydnative-v4-paper-p1-0911.service
systemctl --user daemon-reload
systemctl --user enable --now copytrade-pydnative-v4-paper-p1-0911.service
# active, restore PID 554163
systemctl --user stop copytrade-pydnative-v4-paper-p1-0911.service
bash ops/pydnative-canary/backup-state.sh
systemctl --user start copytrade-pydnative-v4-paper-p1-0911.service
# active, PID 555771, restarts 0
```

Note: systemd `disable` removes linked unit references. **Restoration requires
`systemctl --user link <installed absolute unit path>` before `enable --now`**.
This was found during the actual rollback drill and verified, not guessed.
Unrelated host-wide `systemd-analyze verify` emitted XFS unit option warnings.

## Authentic forward evidence

The existing official source journal had, during inspection, 40 BASELINE,
75 GAP, 7 OBSERVATION, 26,939 TRANSPORT and 67,449 UNCHANGED stream records.
These counts are a changing snapshot and **not P1 post-start trades**.
The full live source chain verifier passed and reported baseline-valid scopes.

At 2026-11-09T10:01:16 UTC the new consumer reported:

- `source_results` for S035/S051/S053:
  `BLOCKED_SOURCE_NOT_PROSPECTIVE_POSITION_TRANSITION` — correctly does
  not convert the pre-existing official source positions into fresh risk.
- `execution_intents={}`; `execution_outcomes={}`; `exit_results={}`.
- `cash=10000`, `equity=10000`, `positions={}`,
  `risk=GREEN`, `real_broker_fills=0`, `order_route=NONE`,
  `trading_authorized=false`.
- Run journal head:
  `6b4e7a0129ee20302563df3b394d44990fe626adec2045dce6f29a5b4f983b4a`.
  No duplicate financial event on stop/restore/start.
- Existing Vike minute collector remained running. A **matched independent
  fresh quote at a genuine T+300 opportunity is not yet observed**.

`FORWARD_ENTRY_NOT_YET_OBSERVED`.
`FORWARD_EXIT_NOT_YET_OBSERVED`.

T0+300 latency, modeled decision timestamp, terminal fill/blocked/expired,
native-quantity realized opportunity sizing, modeled fee and protective
exit behavior are **UNKNOWN in authentic forward operation**; offline
engineering tests do not satisfy #229's real-market criterion.

## Original service preservation

Before/after canary actions, these original PIDs remained unchanged:
selected V4 source `2383440`, Vike minute `2380697`, old P1 paper
`2383186`, and sixteen-portfolio paper `2776865`. Existing Grafana
remained active. Sixteen-portfolio **source** had already restarted and
increased from 9 to 10 restarts during observation; its PID moved from
`503956` to `541799` independently of the new canary. That instability
is *not* claimed as fixed or caused by this rollout.

## Acceptance dimensions

| Dimension | Status |
| --- | --- |
| IMPLEMENTED | YES; merged and installed exact SHA above |
| ENGINEERING VERIFIED | YES for executed available gates, with 3 full-suite skips |
| MERGED | YES, #246 |
| DEPLOYED | YES; new user-systemd unit, exact release |
| RUNNING OBSERVED | YES; source chain, physical service and genuine journal receipts |
| T+300 VERIFIED | NO — authentic post-start entry still absent |
| EXIT VERIFIED | NO — authentic reduction/close still absent |
| SCIENTIFICALLY QUALIFIED | NO |
| TRADING AUTHORIZED | NO |

**Issue disposition:** leave #229 OPEN. No automatic fleet expansion, funded
execution, order authorization or closure of #213. Resume forward evaluation
only on authentic position transitions. Optional #230 remains separate.
