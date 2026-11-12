# Native checkpoint capacity — #317

**Status: measured bounded capture; operational qualification UNKNOWN.**

Exact capture revision: `dd9aceb10a4112b44860f8a9a79a846ba6221037`.
Three fresh processes covered the current campaign's 14 deduplicated parents
and all 11 native DEX scopes: abcd, cash, default, flx, hyna, io, km, mkts,
para, vntl, xyz. The loader checked current SQLite identities and exclusions.
Three profiles have historical SQLite approval; thirteen are unsigned paper
scenarios. No signed Copy Mandates were created.

Roster SHA: `6271f8b3ab1f7c5695fd6ee7d2e80db25ea7dfba96cb9a3860dc55689eb74f69`.
Campaign manifest SHA: `7c0b2a021a449c06f818cacf2f757a4d40b89e77669316107dc08ca659237e6f`.

| Run | Workers / weight per second | Native scopes complete | Within original grid | Requests | Cohort ms | Max account acquisition ms | Max provider age ms | Max DEX skew ms | Request p95 / max ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| burst | 3 / 8 | 14/14 | 14/14 | 169 | 75668 | 17926 | 8086 | 7637 | 445 / 679 |
| restart | 3 / 8 | 14/14 | 3/14 | 169 | 75941 | 18535 | 10712 | 10331 | 418 / 821 |
| constrained | 1 / 6 | 14/14 | 14/14 | 169 | 103229 | 10074 | 4130 | 3723 | 408 / 776 |

UTC capture intervals on 2026-11-11: burst 19:48:15.920–19:49:31.588;
restart 19:49:32.233–19:50:48.174; constrained 19:50:48.972–19:52:32.201.
All runs observed zero HTTP errors, timeouts or 429s. Explicit empty native
books count as flat evidence; missing data does not. The v1 report's
`complete_scope_count` also requires finishing in the original grid window.
The restart run crossed that boundary; native response completeness stayed
14/14. No observation was qualified against approved production timing limits.

Each cohort made 154 account/DEX and 15 catalog calls: 608 documented weight
units. The [official rate documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)
assigns weight 2 to clearinghouseState, 20 to other documented info calls,
and a shared-IP limit of 1200/minute. The nominal five-minute average of
121.6/minute is not measured shared-IP headroom. Other clients share the IP.

## Bounds and outstanding evidence

Freshness, skew, grace, throughput and source-gap qualification remain
**UNKNOWN**. Observed maxima are descriptive inputs, not an SLA or signed
policy. Native timestamp guarantees, economic acceptance bounds, aligned
prospective cohorts, shared-IP traffic, longer-run tails and gap evidence
are unresolved. The slower serial run reduces interleaving within one
account but takes longer across the entire roster.

Fault evidence: deterministic tests cover timeout, 429, missing scope and
invalid clocks; source/receiver tests use actual SIGKILL around commit.
No native outage or 429 was induced on the shared IP. The DevSpace RPC timed
out while the experiment continued. All three receipts were subsequently
recovered and independently reproduced from their retained original bytes.

## Immutable evidence

Private roots:
`/home/quant/.local/share/copytrade/research/cwsa-313-capacity-20261112-{burst,restart,constrained}`.

| Run | SHA-256 of capture.json |
| --- | --- |
| burst | `0d06a105888f870d36699e1f9d3cb95ae5251a57431c01b42cf6a8c84e7db869` |
| restart | `1fc34be937392e0e3f021fc37b48a3fe717bbb9e1662996a43d6e36baa97fe41` |
| constrained | `c0c6323f001fbf78591eede6e5f5a9771aedeb6a66f941ddddc2e17883221682` |

Each receipt binds exact revision, roster, raw sidecars, request/provider/
acquisition/receipt/validation clocks and descriptive report. Verification:

```bash
uv run --frozen python -m copytrade_pm.pm_checkpoint_capacity --root /home/quant/.local/share/copytrade/research/cwsa-313-capacity-20261112-burst --verify
```

A new capture requires a clean checkout and new private root:

```bash
uv run --frozen python -m copytrade_pm.pm_checkpoint_capacity --root /home/quant/.local/share/copytrade/research/cwsa-313-capacity-NEW --registry /home/quant/.local/share/copytrade/registry/wallet_registry.sqlite --manifest /home/quant/dev/copytrade-pm/data/private/gemini_phase3_phase4_eligibility_20261104.json --mode burst --workers 3 --weight-per-second 8
```

The command performs native info reads only. It changes no registry authority,
services, broker permissions, protected journal or trading activation.
