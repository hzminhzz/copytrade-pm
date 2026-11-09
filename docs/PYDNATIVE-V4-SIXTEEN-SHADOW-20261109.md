# Pydantic-native V4 sixteen-portfolio SHADOW rollout — 2026-11-09

## Status: 16/16 RUNNING OBSERVED; FORWARD ENTRY/EXIT NOT YET OBSERVED

Owner explicitly expanded the additive paper-only rollout from one P1 canary to the
sixteen existing virtual-paper scenarios on 2026-11-09. The scope and exact unit were
recorded in [#229](https://github.com/hzminhzz/copytrade-pm/issues/229)
before installation. This is not an authorization to alter protected Guardian,
production services, broker routes, source selection, exclusions or financial policies.

**R2 remains running under OS user `quant`; this is a paper consumer using the
existing official V4 source observer, not a newly installed Pydantic source collector.**
Full source-side Pydantic deployment and authentic complete T+300 lifecycle proof
are still separate UNKNOWNs.

## Exact releases and runtime

| Item | Verified value |
| --- | --- |
| Additive initial rollout | PR #248, merged `81a06af21c0c5ea8d168ced2f491e990b2aa3237` |
| Contention correction | PR #249, merged `7de2f03c327ca98ef06cc0e64d8429ccd9589980` |
| **Installed release SHA** | `7de2f03c327ca98ef06cc0e64d8429ccd9589980` |
| **Installed release path** | `/home/quant/.local/share/copytrade/releases/pydnative-v4-sixteen-0911-r2` |
| OS user | `quant` |
| New user systemd unit | `copytrade-pydnative-v4-sixteen-paper-0911.service` |
| MainPID | `624197`, `ActiveState=active`, `NRestarts=0` at the observation |
| New private state | `/home/quant/.local/share/copytrade/prospective/pydnative-v4-paper-sixteen-0911`, mode 0700 |
| Shared *existing* official source | `/home/quant/.local/share/copytrade/prospective/v4-selected-sixteen-0911/paper-events.sqlite3` |
| Shared *existing* price source | `/home/quant/.local/share/copytrade/prospective/v4-minute-0811/paper-events.sqlite3` |
| Private campaign SHA-256 | `7c0b2a021a449c06f818cacf2f757a4d40b89e77669316107dc08ca659237e6f` |
| Installed uv.lock SHA-256 | `182c79eb81920f0b42064a91c7b3775cb3e8f53a059a854e28b05b100e09369e` |
| R2 installed unit SHA-256 | `13b0f77bce96a0bd4812c84030a8eab9120f629c5f50969adf9493513ce11338` |
| Portfolio supervisor | One process, 16 distinct PM03/PM04 private ledger trees |
| Trade route / authorization | `NONE` / `false` |

All sixteen distinct `manifest.json` files and sixteen distinct `events.jsonl`
files exist beneath private per-portfolio directories. Runtime emitted
`ADMITTED_VIRTUAL_PAPER_ONLY`, then at
**2026-11-09T10:35:32 UTC** reported `active_ledgers=16`,
`quarantined={}`, `retrying_sqlite_busy=[]`, `order_route=NONE`.
The result remained **16/16 active and GREEN** at
2026-11-09T10:36:34 UTC. A systemd `active` result alone is *not* sufficient;
the source-stream startup verification took approximately two minutes and the
actual application-admission event was explicitly inspected.

Original Pydantic P1 paper PID `555771`, original sixteen-paper PID `2776865`
and shared Vike-minute PID `2380697` remained unchanged.
The *pre-existing* sixteen-source restarted independently and was observed at
PID `624227`, 14 restart counts. Its prior `PAPER_JOURNAL_BUSY_OR_UNAVAILABLE`
failures and recovered baselines remain a **known operational weakness**; the
new rollout did not modify its unit, state, code or connection scope.

## Selection and source authority

The original 2026-11-04 private campaign resolves 16 study profiles and 14
deduplicated official Hyperliquid parent accounts. The official source-stream
chain audit returned `integrity=VERIFIED` across 14 streams and `order_route=NONE`;
14/14 latest baseline-valid accounts were observed during one of the live audits.
A baseline after a reconnect is **never** counted as a post-baseline entry signal.

P1/P14/P16 retain actual SQLite historical profile/seal verification.
The other 13 configurations remain **unsigned, explicitly approved paper-only
research scenarios**, with original exclusions and negative-control flags
visible; their paper ledgers are not signed trading selections.
Each virtual portfolio has its own hypothetical $10,000 accounting scope and
fixed-k PM03/PM04 risk. No broker credentials or trade API were connected.

At the final source journal inspection the existing service reported
474 BASELINE, 830 GAP, 102 OBSERVATION, 66,540 TRANSPORT and 145,856 UNCHANGED
stream events. These are cumulative **historical original-source observations**,
not fresh post-R2 entry proofs. Their counts can advance while this document
remains a frozen checkpoint.

Independent Vike price evidence was still advancing: the receipt database's
maximum known-at timestamp reached `2026-11-09T10:37:36.347466+00:00`.

## Actual contention failure and correction

R1 initialized all 16 paper accounts but then permanently quarantined P1,
P14, P15 and P16 on `OperationalError:database is locked`; active fell to
12/16. This was **not** an acceptable healthy rollout. The original R1 canary
was stopped and its private immutable evidence retained.

R2 changes **only the sixteen-paper supervisor's** handling of actual
SQLite BUSY/LOCKED operational contention: no new model entry, no source clock
rewrite, no skip of quote/signature/finance gates. It retains the last ledger
projection and retries next tick. A recovered reader emits
`recovered_from_sqlite_busy=true`. Repeated transient locks do not flood
the log. Every non-busy operational error still quarantines the affected
portfolio; `--once` fails closed when a portfolio remains busy.

The new R2 application successfully admitted and ticked **all 16** existing
ledgers from the original state root, showing no permanent quarantines at the
observed time. Synthetic regression verifies the lock/recovery path;
**a live post-R2 contention/recovery occurrence was not observed**, so it is
not claimed as a production recovery test.

## Verification and private rollback evidence

```bash
uv run --frozen --all-extras --group dev pytest -q tests
# 1761 passed, 3 skipped; 45.35 seconds

uv run --frozen --all-extras --group dev pytest -q \
  tests/test_pm_v4_sixteen_busy_retry.py tests/test_pm_v4_sixteen_paper.py \
  tests/test_pm_forward_observed_paper.py tests/test_pydantic_combined_authorities.py
# 19 passed

uv run --frozen --group dev ruff check .
# All checks passed
uv run --frozen --group dev ruff format --check .
# 563 files already formatted

bash ops/pydnative-sixteen/deploy.sh 7de2f03c327ca98ef06cc0e64d8429ccd9589980
systemctl --user show copytrade-pydnative-v4-sixteen-paper-0911.service \
  -p ActiveState -p MainPID -p NRestarts
# active, PID 624197, NRestarts=0
```

The R1 state was stopped and backed up with the exact
`bash ops/pydnative-sixteen/backup-state.sh` script. Verified backup:
`/home/quant/.local/share/copytrade/backups/pydnative-v4-sixteen-0911/20261109T103253Z.tar`
SHA-256:
`1a04d6ceaa8b5fd1e31348b59d22e76b26442ab8a50678b9d67858ded2694f4e`.
Its TAR directory listing was verified; it contains only the new sixteen-ledger
state, no upstream producer or old paper state.

Combined SHA-256 of sorted path+content checksums for 16 paper `events.jsonl`
was `12791c25d2bbee19254928cbe2407707dad7dd9e6e675a365250d93db31dffb3`
before the R2 upgrade and **unchanged after admission**. This is evidence
of journal preservation and restart continuity, not a live trade.

To rollback **only** this new service while retaining its evidence:
```bash
bash ops/pydnative-sixteen/deploy.sh --rollback
```
Reinstall the *same* exact `7de2f03c...` SHA with
`bash ops/pydnative-sixteen/deploy.sh 7de2f03c327ca98ef06cc0e64d8429ccd9589980`.
The script re-links a unit removed by `systemctl disable` and preserves
original state. **R1 stop/backup/R2 restoration was executed and verified;
a separate full R2 stop/rollback/reinstall drill was not run**, to prioritize
continuous authentic source observation. The R1 release remains separately
immutable for forensic evidence.

## Prospective evidence and outstanding gates

The R2 runtime log had no accepted genuine post-start source transition,
`execution_results` or `exit_results` at the recorded checkpoint. All 16
risk summaries were GREEN and no broker fills or financial trading authorization
were present.

- `FORWARD_ENTRY_NOT_YET_OBSERVED`.
- `FORWARD_EXIT_NOT_YET_OBSERVED`.
- **T+300 VERIFIED: NO.** There is no authentic first-known T0 + due + actual
  modeled decision + matched independent Vike quote + one terminal outcome yet.
- **EXIT VERIFIED: NO.** No genuine post-start reduction/close was observed.
- **SCIENTIFICALLY QUALIFIED: NO.**
- **TRADING AUTHORIZED: NO.**

The existing policy remains first-known T0 + 300 seconds, a 30-second
eligibility grace, 2-second configured idle polling interval; actual
operational decision times can be seconds late and must still fall in the
accepted window or expire. There is no benchmark-based latency qualification
claim and no modified financial threshold.

### Remaining operational blocker

The old shared official sixteen-source service is **degraded by repeated SQLite
journal-busy failures** and reconnect GAPs. Although stream integrity validates
and price rows arrive, genuine source transitions after the new consumer's start
have not yet appeared. Future source changes must be observed before asserting
the requested real end-to-end trade lifecycle. Expanding from one to sixteen
**portfolios** increases shared-wallet coverage to 14 unique accounts, not
sixteen independent source wallets.

**Issue decision:** leave #229 OPEN for genuine T+300 and exit proof.
No fleet financial promotion, optional #230 closure, parent #213 closure,
protected Guardian mutation or funded/demo/live execution authorization.
