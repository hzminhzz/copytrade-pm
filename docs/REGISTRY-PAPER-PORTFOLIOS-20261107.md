# Registry-bound additional forward-paper portfolios (2026-11-07)

## Purpose and scope

The existing P1 worker is *not* a general-purpose strategy allocator. This
change reuses its read-only first-known source/market journal and the PM-03/PM-04
single-shot v3 accounting implementation for **two additional, isolated virtual
portfolio experiments**. It does not activate any broker route, Guardian account,
funded challenge, P15 higher-risk scenario or non-executable signed research
selection. Each campaign has a separate initial $10,000 **virtual** ledger.

The registrar is the private SQLite registry. A paper execution profile is a
separate reviewed risk/sizing scenario. A registry seal alone is not sufficient
to create a financial paper strategy. The consumer reads the authoritative
`select_asof` registry owner at run-start, verifies member count/identities,
the exact virtual-paper sizing-contract family, version and definition SHA, and
pins the registry seal into the journal policy hash. On restart the same frozen
profile and seal must still match; no silent reseal or mutation.

## Profiles and comparisons

| Portfolio | Selected source aliases | Nominal pod risk | Research-only fixed k |
| --- | --- | --- | --- |
| P1 baseline | S035, S051, S053 | $200 each, $600 combined | .0282 / .0430 / .0296 |
| P14 challenger | S035, S051, S053, S064, Whale_0x5f94 | $120 each, $600 combined | .0169 / .0258 / .0178 / .0191 / .00011 |
| P16 optional control | S035, S051, S053, Whale_0x5f94 | $180 / $180 / $150 / $90, $600 combined | .02538 / .0387 / .0222 / .0000825 |

P1 and P14 values are the **Gemini Phase 3 research references**, not
independently validated live sizing. P16 risk percentages (30/30/25/15) came
from the approved *optional research control* design. P16's fixed-k values
are explicitly **DERIVED research scenario assumptions**: P1 core k multiplied
by each P16 pod-risk / $200; whale P14 k multiplied by $90 / $120.
This is not a claim those k values were signed in the registry or approved as
a broker execution policy. Do not compare raw modeled PnL of portfolios without
matching forward observation periods and accounting for extra accounts.

All campaigns consume the **same** read-only first-known public tape; they do
not independently open WebSockets or submit transactions. They retain the
single market attempt per instrument, first-known + 300s entry window, immediate
single-attempt exits, no residual chasing, one-use L2-side receipts, risk-stop
overrides, native lots, cost/fee accounting and isolated PM03 state.
The nominal $600 is a research-loss-trigger budget, not a guaranteed
drawdown bound or source collateral authorization.

### Evidence limitations

The running public observer currently captures only the P1/P14 five-wallet
cohort. Current signed `regime.macro/TriadA` and
`regime.macro/TriadChop` have the registry's
`NON_EXECUTABLE_SIGNED_RESEARCH` sizing type and no verified first-known
source feed in that observer. They must not be auto-instantiated as financial
paper campaigns. Historical Q3 portfolios and Gemini reference cohorts also
lack validated forward sizing contracts. Existing `P14` and `P16` identities
may hold HIP-3 positions outside the frozen default-perp market admission.
The engine correctly blocks those complete source books; it must **never**
silently drop the unsupported hedges to fabricate follower returns.

Older run journals are not retroactive evidence; first-known receipt dates
before new run creation are excluded. Real portfolio entry/exit execution
remains unobserved until a qualifying future source and sufficient fresh
market depth arrive. Printed reports from a running paper process are
virtual/research evidence only, not scientifically qualified follower PnL.

## Operator procedure

Verify the live registry's exact v2 definitions and the selected accounts
before any restart or release. Keep each run in its own private state root:

- `copytrade-paper-research-p1-0711.service`: existing P1, unchanged.
- `copytrade-registry-paper@P14.service`: persistent P14 research instance.
- `copytrade-registry-paper@P16.service`: persistent P16 research instance.

The persistent **instance template**
[`copytrade-registry-paper@.service`](copytrade-registry-paper@.service)
is versioned in this repository and may be installed using
`systemctl --user link /ABSOLUTE_PINNED_UNIT_FILE`,
`systemctl --user daemon-reload`, and
`systemctl --user enable --now copytrade-registry-paper@P14.service
copytrade-registry-paper@P16.service`. The
`quant` systemd user manager must have `Linger=yes` for boot survival.
The two prior `systemd-run` transient services must be stopped **before**
starting the persistent instances. They have separate original journals,
which must be preserved rather than merged or deleted.

Both new services use the reviewed frozen code checkout at `814db12`,
the exact public-observer SQLite tape and private native registry (read-only).
Use `--watch --poll-seconds 2`, resource bounds, systemd user identity,
isolated run names and a fail-closed restart policy.
Never point two processes at the same PM03 state root/run ID.
The input market catalog uses a one-time public metadata read; new paper
consumers do not add market subscriptions or mutate producer receipts.

Review `systemctl --user show UNIT -p ActiveState -p MainPID -p ExecStart
-p NRestarts`, `journalctl --user -u UNIT`, frozen release SHA, source head
freshness, recent ledger SHA/entry counts, and read-only PM03 replay. Record
the installed release/manifest SHA and whether there is any post-start
authentic `PM04_PAPER_EXECUTE` / `PM04_PAPER_EXIT`; do not infer a fill
from a unit's active status.

**Rollback:** Stop only the failing additional unit. Preserve its immutable
private evidence. Reinstall the pinned release with a newly named campaign
if the startup policy changes. Do not overwrite P1, alter the public observer,
modify production Guardian, or mix virtual portfolios on one broker account.
