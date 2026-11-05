# ML4T principles for wallet ingestion and screening

**Contract date:** 2026-11-05. **Scope:** research methodology, not qualification, trading authorization, or a new SQLite finance ledger.

The source of truth for wallet/cohort/alias/exclusion/selection **metadata** is owner-private SQLite. Hyperliquid, HyperX, Nansen, vendor raw pages, source books, historical market Parquet, first-local journals, and independently measured follower economics have **different evidentiary roles**. Do not use a leader's reported PnL or a retrospective fill time as a true follower outcome.

## 1. Source ingestion must be causal, reproducible, and fail closed

| Layer | Required artifact or check | If absent |
| --- | --- | --- |
| Identity | Venue/network, normalized address, namespace-qualified alias, observed-at timestamp | UNKNOWN_IDENTITY; do not infer from a display alias |
| Provenance | Exact source bytes, SHA-256, provider/method, retrieval clock, immutable private copy | UNVERIFIED_IMPORT; metadata only |
| Fills | Schema, identifier uniqueness, UTC timestamps, pagination completeness, signed position-after continuity, duplicates and gaps | PARTIAL_HISTORICAL_FILLS |
| Market | Canonical symbol/timestamp, venue/DEX, OHLCV integrity, exact 1m coverage | MARKET_COVERAGE_BLOCKED; no synthetic bars |
| Book | All parent/subaccount perpetuals including HIP-3, hedges, funding, collateral, mode-aware NAV | WHOLE_WALLET_EQUITY_UNKNOWN; no follower sizing |
| First-known | Local receipt/decision clocks distinct from source event time | PIT_FOLLOWER_EVIDENCE_UNKNOWN |
| Follower | Matched quote, order, fill, fee, slippage, funding and joint mark-to-market PnL | FOLLOWER_ECONOMICS_UNKNOWN; no qualification |

Use the existing modules in [DATA-ACQUISITION](DATA-ACQUISITION.md) and [RUNBOOK](RUNBOOK.md). **Native SQLite registration records membership and immutable evidence references, not economics.** A registered wallet is not necessarily profitable or eligible.

Provider-specific schemas must be normalized once at acquisition. Preserve raw bytes and source event clocks. Never assume two vendors share trade identifiers or an account-complete state.

## 2. Research screening is a sequence of hypotheses

1. **Economic mechanism.** State a falsifiable explanation for profits (trend, liquidity/inventory, forced liquidations, funding); a leaderboard rank is insufficient.
2. **Sampling.** Count independent episodes and observation days, not fills alone. Record discovery selection, survivorship, strategy churn, multiple testing and position overlap.
3. **Return evidence.** Only with a complete independently valued account or follower return path: report risk-adjusted return, effective sample size, confidence, PSR with nonnormality assumptions, drawdown, skew and excess kurtosis. Missing NAV means UNCOMPUTABLE.
4. **Tail risk.** Inspect intra-day trailing drawdown, large losses, leverage/martingale concentration, common factor exposures and joint tail events. Positive skew is desirable, but negative skew alone is not a universal rejection rule.
5. **Execution.** Model faithful exposure, delay 0m/2m/5m, native next-bar or first-known quote, fees, funding, liquidity and participation constraints. Stress baseline, 1.5x and 2x costs. With measured baseline *net follower* PnL P and traded notional N, incremental tolerable adverse slippage is 10,000 × P/N bps (N > 0). It is not inferable from leader PnL.
6. **Dependence.** Inspect time-varying correlation, shared instruments, joint drawdowns and HRP-like clustering. Do not claim optimality or diversification without OOS stability.
7. **Prospective.** Preserve genuine known-at selection, fresh first-local observations, mature matched follower/control net results, and protected forward-paper gates.

### DSR and PSR: neither is a universal qualification gate

**No blanket DSR cutoff for externally observed wallets.** DSR's trial-family input cannot be defined by naively setting K to the count of all independent wallet addresses. Yet external-wallet selection still has multiple-comparison and survivorship bias. Record the discovery universe and selection history; use multiplicity-aware robustness checks where justified and truly prospective holdouts. PSR is descriptive without a well-defined return series, horizon and assumptions. Neither statistic independently authorizes trading.

Do **not** silently convert illustrative PSR, skew, slippage, day-count or Sharpe thresholds from a draft into an enforced exclusion policy. Such thresholds require a reviewed, versioned research policy.

## 3. Ownership and technology

- **Large arrays:** Polars, DuckDB and Parquet own market/fill history and immutable reproducible sweeps.
- **Operational metadata:** SQLite owns wallets, aliases, cohorts, exclusions, research selections and indexed artifact references.
- **Financial dynamics:** sequential PM-03 simulation owns stateful daily/trailing loss barriers.
- **Prospective facts:** signed observations, real source equity and matched follower economics remain independent evidence; the observer does not authorize orders.
- **Agent interface:** discover capabilities, then query the pinned read-only CLI and verified installed release. Markdown and OptMem provide directions, never live truth.

## 4. Acceptance before labeling a real wallet screened

- Verify registry doctor integrity, cohort counts, full inventory SHA, known-at identities and unverified import labels.
- Validate private manifest SHA, duplicates, alias conflicts, temporal precedence, append-only cohort/exclusion decisions, idempotency, transaction rollback, backup and no tracker mutations using disposable SQLite.
- Verify source account mode, all-parent/subaccount book and mode-aware NAV independently. Do not replace missing equity with quote balances, guessed leverage or non-SHA labels.
- Screen only known native market legs/days and report unknown coverage, funding, fee and slippage assumptions explicitly.
- Separate IMPLEMENTED, ENGINEERING VERIFIED, SCIENTIFICALLY QUALIFIED, AUTHORIZED and DEPLOYED.
- If matched follower/control observations are unavailable, label screening PRELIMINARY / HISTORICAL ONLY regardless of hypothetical returns.

## References and ownership

- [Wallet data acquisition](DATA-ACQUISITION.md)
- [Registry-first workflow](WALLET-REGISTRY-AGENT-WORKFLOW.md)
- [Qualification contract](QUALIFICATION.md)
- [Native SQLite and exclusion contract](SQLITE-NATIVE-LEGACY-LOCK-20261105.md)

Original local ML4T study notes informed these guardrails; claims about named wallets or universal statistical thresholds must be reverified before use.
