# V4 sixteen-portfolio virtual-paper experiment (2026-11-09)

## Decision and authority

Owner explicitly requested that the 16 existing research configurations be run as
**prospective V4 virtual-paper experiments**. This does **not** reverse the
November 4 Gemini historical findings, register new SQLite scientific
selections, revoke wallet exclusions, admit any live-risk authority, or permit
Propr/Bybit orders. Research-only, NO BROKER throughout.

The source of the 16 historical names is the quant-private
`data/private/gemini_phase3_phase4_eligibility_20261104.json`, SHA-256
`7c0b2a021a449c06f818cacf2f757a4d40b89e77669316107dc08ca659237e6f`.
Addresses remain private. Every startup verifies the complete private file
hash and resolves all source wallets against the **current read-only SQLite**
identity ledger. The prospective paper manifest digest is explicitly an
**unsigned experiment**, not an owner-signed research selection or a native
SQLite portfolio seal. The three original P1/P14/P16 profiles retain their
native SQLite seal checks unchanged. Missing or conflicting account identities
abort the entire sixteen-source startup before paper admission.

## One shared source, sixteen independent ledgers

- One additive official Hyperliquid selected-position V4 observer captures 14
  deduplicated parent accounts in **one WebSocket**. Native selected perp scope,
  first-seen baseline, official stream SHA, gap fencing and T+300 clocks remain
  identical to V4. No fill reconstruction and no new trading route.
- One existing shared Vike 1-minute collector provides price/volume evidence.
  It is not L2 or proof of executable market liquidity.
- One V4 supervisor ticks **16 separate PM03/PM04 ShadowRun financial ledgers**,
  each with independent `$10,000` hypothetical starting balance and isolated
  lock/run name. A per-portfolio financial-journal exception quarantines that
  portfolio rather than creating a synthetic close or contaminating others.
- The account is *not* a shared $10,000 funded challenge across all 16. The
  16 virtual accounts must not be summed to claim portfolio economics.
- Original 2026-11-08 P1/P14/P16 V4 services, V3 paper, Guardian, Planner,
  Grafana, CCXT observer and historical journals are retained unchanged.
  No real broker dependencies, credentials or order routes are present.

## Frozen sizing and remediation decisions

| Research IDs | New virtual-paper sizing | Historical evidence maintained |
| --- | --- | --- |
| P1, P14, P16 | Existing reviewed V4 fixed-k and independent pod budgets | All existing SQLite seal and account checks stay mandatory |
| E1, E3-E8, E11-E12 | Published `100k` reference k scaled by 0.1 for virtual `10k`; additional 0.6 risk scale when historical nominal budget was `$1,000` | No claim these are independently calibrated copy ratios |
| P15 | Original `$1,000` risk and missing k **not** promoted; new `$600` control uses P14-derived, risk-capped k (equivalent to P14) | `MISSING_ORIGINAL_P15_K_VALUES` remains an explicit blocker for historical P15 |
| E2 | Resolve research-only scenario using the **lower** of contradictory k values for each affected wallet, then 0.1 scaling | Original P8 sizing disagreement remains visible |
| E9 | Lower ACT08 k of `0.0199` before 0.1 and 0.6 scaling | Original P9 discrepancy remains visible |
| E10 | Reduce published k by 0.5 after 0.1 scaling; label as a negative-control remediation | Historic no-stops daily MTM breach remains a rejection |

**All new E/P15 scenarios have $600 total nominal pod loss** ($200 per pod
for three accounts, $120 for five), never $1,000. This is necessary because
PM03 daily $500/static $1,000 floors, $10 reserve and PM04 stress reserve
cannot independently fund five $200 pods. Each pod's daily limit remains 75%
of its own nominal loss limit; the PM04 aggregate controls remain unchanged.
The preserved original P1/P14/P16 campaign values are not overwritten.
This nominal limit is a *trigger*, not a guarantee of terminal drawdown.

Source exclusions (including `CM-002` and `Whale_0x5f94`) are preserved,
emitted as `PREEXISTING_EXCLUSION` research warnings, and **never revoked or
converted to a scientific/trading permit**. These candidates are tracked in
isolated negative-control paper research only, not admitted to live trading.
Unknown aliases in the historical file (`N051-HYPE`, `W004`, `VS005`)
require unique currently registered address equality; no synthetic address or
later-known historical alias is written into SQLite.

## Install and runtime

Run `bash ops/v4-sixteen-paper/deploy.sh <EXACT_MERGED_40_CHAR_SHA>`
as the `quant` user, from the verified, isolated source worktree. The script:

1. Validates the exact source commit and pinned private-manifest digest.
2. Archives the exact Git revision to the private
   `/home/quant/.local/share/copytrade/releases/v4-sixteen-paper-0911`
   installation (never a dirty working-tree import), installs frozen uv
   dependencies with source WS extra, and runs a private dry-run preflight.
3. Links and starts *additive* user systemd units:
   `copytrade-v4-sixteen-source-0911.service` and
   `copytrade-v4-sixteen-paper-0911.service`.
4. Validates active service PIDs, checks the original three V4 service states,
   and exits nonzero on failed startup. Existing 2026-11-08 services remain
   untouched.

Owner-private prospective evidence directories:

- Shared official selected source:
  `/home/quant/.local/share/copytrade/prospective/v4-selected-sixteen-0911`
- Sixteen isolated ledgers:
  `/home/quant/.local/share/copytrade/prospective/v4-paper-sixteen-0911/<pid-lower>/`
- Shared Vike price source remains:
  `/home/quant/.local/share/copytrade/prospective/v4-minute-0811`

Check `systemctl --user show copytrade-v4-sixteen-source-0911.service
copytrade-v4-sixteen-paper-0911.service -p MainPID -p ActiveState -p NRestarts`
and journal timestamps. Verify the source journal with
`copytrade_pm.pm_forward_stream_journal.verify_streams`, all 16 paper
`manifest.json` and PM03 event ledgers, correct SHA and no broker fills.
A healthy process with no real post-baseline source changes does not constitute
a completed paper entry/exit or economic qualification.

## Acceptance and rollback

**Engineering startup acceptance:** 14 unique selected account identities,
16 isolated private ledgers with PM04 configuration, source & price journal
integrity, positive service PIDs and no other service changes. For economic
validation, separately wait for authentic observed official source transitions,
verify first-known T+300 attempts, real available Vike quotes, correct
native quantities, explicitly modeled fees and exits, and account-wide
loss/gross/concentration accounting. No qualifying transitions yet means
`UNKNOWN`, not `PASS`.

**Rollback:** `bash ops/v4-sixteen-paper/deploy.sh --rollback`.
This disables/stops only the two *new* user services, retains all source
and finance evidence, and leaves the older P1/P14/P16 V4 and separate
Guardian/production services untouched. Do not delete journals on rollback.

**Prohibited claims:** scientific alpha, positive follower PnL, exact fills
or impact, authentic challenge-pass probability, live-risk approval, or
qualified performance of the four historically blocked configurations.
