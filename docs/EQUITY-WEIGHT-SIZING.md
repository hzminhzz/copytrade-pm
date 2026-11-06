# Equity-normalized wallet exposure — historical fidelity sizing (2026-11-02)

**Owner policy update 2026-11-06:** The owner adopted [risk-budgeted fixed-k](RISK-BUDGETED-K-SIZING-20261106.md) as the **default** for new copytrading research and execution. This 2026-11-02 source-NAV formula remains the strict, optional **leader-equity-relative fidelity** contract, **not** a universal source NAV prerequisite or a veto over fixed-k work. Existing historical results are preserved; do not recast their outcomes as fixed-k results.

## Decision

**Copy the wallet's signed position notionals as fractions of its own account equity, not its fill tickets, independent episode notionals, margin utilized, or raw trade direction.** Every valid source snapshot updates a vector of target exposures. One or two missed follower executions do not invalidate the sizing method: they create measured tracking error and must be reconciled from the latest **verified source book vs actual follower holdings**, not applied as incremental per-trade signals.

Source equity must refer to the same precisely identified master/subaccount and perp/DEX scope as the positions. No invented collateral or aggregation across subaccounts. Only source-account equity including unrealized PnL is an eligible denominator. "Leverage" metadata, margin used, cumulative closed PnL and historical gross notional are not substitutes for source equity.

### Formula

For each market **i** at decision **t**, with independently evidenced source book and marks:

```
signed source notional_i(t) = signed source quantity_i(t) * source price_i(t)
source exposure weight_i(t) = signed source notional_i(t) / source equity(t)
follower target notional_i(t) = exposure weight_i(t) * allocated follower pod capital(t)
follower target quantity_i(t) = follower target notional_i(t) / follower price_i(t)
required catch-up delta_i(t) = target quantity_i(t) - actual follower quantity_i(t)
```

No per-fill sizing constant. No independent normalization of each long or hedge. A weight of +3 represents 300% BTC notional exposure relative to **source equity**, independent of the exchange's isolated/cross margin setting.

| | Wallet | Follower |
| --- | ---: | ---: |
| Equity / allocated pod capital | $100,000 | $2,000 |
| BTC long notional | $300,000 | **$6,000** |
| BTC signed exposure / equity | **+300%** | **+300%** |
| BTC quantity at $100,000/BTC | +3 BTC | **+0.06 BTC** |

If the first 0.06 BTC follower order is skipped, actual inventory remains **zero**. The following validated snapshot with unchanged source risk still requests **+0.06 BTC**. If the follower filled 0.04 BTC, request **+0.02 BTC** instead. Never apply the original trade delta again, and never interpret a missing fill message as a zero source position.

If source equity rises to $120,000 with unchanged 3 BTC at $100,000, signed BTC weight becomes +250%; on a $2,000 pod the next target is $5,000, not $6,000. If the allocated pod capital changes, the target changes accordingly. An independently observed source-equity update is itself a sizing decision, even when the wallet submits no fill; the historical equity-mode runner schedules a separate five-minute equity update only where a reconstructible source position book is already known.

### Implementation and evidence boundaries

- **Existing E0 path:** `pm_wallet_replica.replicate` already scales *all* signed source quantities by `pod_capital/source_equity` for identical native-market marks. It still requires prospective account state, legitimate local receipt, exact native instrument identity, continuous/capital-reconciled book and a sufficiently fresh source event. PM-03/PM-04 remain the only account/risk authority.
- **Explicit weight path:** `pm_exposure_sizing.calculate_weights`, `target_from_weights`, `build_intent`, `reconcile_actual`. These express the same wallet exposure vector in signed notionals, work with differing source/follower prices, and report required inventory catch-up and dollar-weighted tracking error. No orders or broker imports. A caller cannot bypass E0 trust gates via `build_intent`.
- **E0 attribution:** `fidelity` now also reports source-signed exposure weights, executed-signed weights, gross/net source exposure multiples and tracking deviation as a percentage of allocated pod equity (assuming matched native marks). Risk-approved, intended and actually executed books must remain distinct.
- **Missed trades:** an omitted/rejected *follower* order is allowed in **research accounting**; it changes executed holdings, not source intent. Recompute the entire target vector on a fresh, complete source snapshot and record the gap. A missing *source* event may be recovered only by a newly verified, complete account snapshot with source equity, book and receipt clocks; intervening historical exposure remains unknown. Unknown source inventory, unobserved hedges, stale account equity or invalid account scope are not "missed orders" and cannot be silently assigned zero.
- **Risk overlay:** E0 may intend more gross exposure than account rules allow. PM-04 must explicitly reduce or veto the unsupported order; it may not silently re-label the clipped portfolio as having matched source sizing. A $2,000 pod holding $6,000 BTC is 3× notional risk before futures funding, fees and any mark-to-market loss.
- **Timing:** live source first-local receipt and market mark first-known must precede decision; hypothetical fill at the next eligible market quote. Historical vendor timestamps are **hindsight event clocks**, not first-known evidence. A correctly sized *historical oracle* study is still not scientific follower qualification.

## Q3 retrospective equity recovery and its limits

**Exploratory execution completed November 2, 2026:** the user's full-portfolio research was run in a separately named sparse-NAV approximation using the actual signed-wallet-position/equity sizing equation, historical previous-positive NAV (8d/16d carry), five-minute delay, PM03 account, and market-gap/capacity stress. It does not weaken the strict E0/PIT contract. The executed 84-combination, 3-pod results and selected follow-up are documented in [Q3 sparse-equity execution results](Q3-SPARSE-EQUITY-PORTFOLIO-EXECUTION-20261102.md). Base A +$847.40 with ~90–100% exposure mismatch, B modeled +10% target Aug 21 with 13–41% mismatch, C daily loss breach Aug 13; none is a verified follower return. The strict source-equity replay remains blocked because weekly historical source NAV is insufficient to establish true per-decision account equity.


The previous PR #20 historical study used **July–August peak observed vendor gross notional**, not source wallet equity. Its A/B/C and 84 mixed-combo modeled PnLs are archived as an expressly obsolete **gross-normalized proxy**, not evidence of correct wallet risk sizing.

The corrected historical CLI now defaults to **equity-weight mode**. Without a complete, authentic source-equity ledger, it writes a private immutable report with `pnl_usd=null` for all 84 combinations and reason `BLOCKED_HISTORICAL_SOURCE_EQUITY`. Add `--legacy-gross-proxy` only to deliberately reproduce the old, scientifically limited method; never use its PnL to choose wallets.

We independently inspected the already locally cached official Hyperliquid `portfolio -> perpAllTime.accountValueHistory` equity series for C. We then acquired six new, rate-bounded, read-only official responses for A/B on 2026-11-02, each with a private raw SHA-256 record (six of six rehashed successfully). This uses **no official Hyperliquid account-fill API** and does not alter HyperX fill history.

| Source wallet | Actual Q3 perp account-value observations | Largest observed gap between Q3 samples |
| --- | ---: | ---: |
| W028 | 14 | 169.0 h |
| W042 | 14 | 169.0 h |
| W030 | 10 | 336.7 h |
| W044 | 12 | 170.0 h |
| CA-005 | 14 | 169.0 h |
| W031 | 14 | 170.0 h |
| CO-001 | 14 | 169.7 h |
| W015 | 14 | 169.7 h |
| VS066 | 7 | 336.3 h |

A few *retrospective account-value observations* are not hourly source equity, a continuous all-DEX account proof, transfer/funding reconciliation, or proof that the follower could have known that equity in Q3. No interpolation from seven-day gaps is authorized. The Q3 interval is July 1 through October 1 exclusive, 92 days.

A/B provider evidence: `/home/quant/.local/share/copytrade/reports/historical-equity-20261102/g20261102equityabv1`; report SHA256 `ea29b003d95db465272a199bee9c1f21c5654cc965b35bb6fa8f45a3109169f1`. C provider evidence: previously saved `pm-e4-hyperx-20261031/ge4live20261031first/info_raw`. Original private data should never enter Git.

**Default corrected Q3 preflight**: `/home/quant/.local/share/copytrade/reports/historical-3pod-20261102/pm01-36-wallets-fa6bf12d8cc72becb0ab.json`, SHA256 `fa6bf12d8cc72becb0ab7a670f2b4f7988b922edc705556bdc35445b6fa09670`. A/B/C PnL are null (not zero), 84/84 source-equity-blocked and zero genuinely faithful whole-wallet replays.

### Reproduction

```bash
# Correct default: requires actual as-of historical equity, never gross proxy
uv run --frozen --group dev --extra market python -m copytrade_pm.pm_historical_combos \
  --research-root /home/quant/.local/share/copytrade/reports/five-pod-20261029-research \
  --market-root /home/quant/dev/quant/ml4t-data/.data/store \
  --out /home/quant/.local/share/copytrade/reports/historical-3pod-20261102

# Once an independently reconciled historical ledger exists, provide:
# --source-equity-ledger /secure/pm_q3_historical_source_equity_v1.json
# Historical oracle only; still selection-biased from observed flat-to-flat episodes.

# To reproduce the previously delivered, non-equity-based comparison:
# --legacy-gross-proxy

# Optional authorized source research only, no wallet fill API or broker keys:
uv run --frozen --group dev --extra market python -m copytrade_pm.pm_historical_portfolio_equity \
  --research-root /home/quant/.local/share/copytrade/reports/five-pod-20261029-research \
  --generation /secure/new-unique-g-portfolio-source-generation
```

The new historical equity reader `pm_historical_equity.load_equity` requires exact frozen wallet identity digests, scope, positive account equity, non-future source clocks, distinct increasing observation timestamps, source hash, and an explicit externally reconciled funding/transfers flag. As-of equity max age is 3,600 seconds; points beyond that fail closed, never forward fill. **Those flags are upstream attestations and not independent proof**. A raw public `perpAllTime` series is *not* eligible until independently reconciled to the account scope and transferred cash/hedges.

Existing E1/E2/E3 and PR #20 legacy reports remain immutable. New snapshot series should be collected prospectively with full account/capital reconciliation and risk/tracking diagnostics. No present result authorizes a Propr order, a live Pod or a positive PM-02 R allocation.
