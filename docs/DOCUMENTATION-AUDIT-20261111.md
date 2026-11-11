# Documentation authority and contradiction audit — 2026-11-11

**Scope:** `hzminhzz/copytrade-pm`, baseline `origin/main` `1a005e47155f157ad2326fdf1ff3186b2e3b90d3`. An isolated worktree was used; the existing primary checkout and private journals were not modified. The tracked Markdown inventory at audit start was **163 docs/ Markdown files**, including **24 decision records**, **4 research papers**, **3 spec documents**, and the root agent/README instructions. The inventory was obtained from `git ls-files 'docs/*.md' 'docs/**/*.md'`; exact file content was inspected for source/position/registry/risk/operations contracts and the entire Markdown corpus was searched for conflicting source-provider and completeness claims. This is an architectural/documentation audit, not scientific validation of every historical study.

## Agent cold-start failure map

| Cold-start question | Before | Canonical answer after this change |
| --- | --- | --- |
| Which provider for new wallets? | 2026-11-08 official-first ADR and separate Vike research candidates without clear migration priority | [New Vike-first transport decision](decisions/2026-11-11-vike-first-wallet-source.md) |
| Can Vike positions drive live T+300 already? | Risk of confusing WS channel availability with complete source-book authority | **No**; [official position-first ADR](decisions/2026-11-08-position-first-t300.md) still owns current paper admission |
| Are 14 selected parents continuously covered? | Dated 14/14 cumulative baseline mentions coexist with 7-of-14 continuous subscription notes | Inspect live source GAP epochs; [0911 7-at-a-time incident](V4-0911-WS-SUBSCRIPTION-RECOVERY-292.md) is explicitly non-simultaneous |
| Where is canonical runbook? | Many dated V3, 0811, 0911 and Pydnative runbooks | [Current canonical 16-paper runbook](V4-CANONICAL-FRESH-PAPER-20261111.md); verify actual release/service before executing |
| Which clock makes a new intent? | Historical vendor event-time and local first-known terminology distributed across docs | Original prospective, post-baseline, independent local receipt; no retroactive REST timestamps; [Vike ADR](decisions/2026-11-11-vike-first-wallet-source.md) |
| Does historical profit qualify a wallet? | Legacy equity-relative studies and newer fixed-k reports have different assumptions | [Qualification](QUALIFICATION.md); separate synthetic, genuine forward and executable follower-net proof |
| Is passing a test permission to deploy/trade? | Long documents mix merged/verified/installed/date-specific facts | [Merge vs runtime promotion](decisions/2026-11-10-merge-vs-runtime-promotion.md) and actual Guardian contract |
| What is the source of truth for portfolios? | Markdown roster/snapshot values appear alongside registry rules | [SQLite registry-first](WALLET-REGISTRY-AGENT-WORKFLOW.md), not the dated written roster |
| How does a new agent navigate? | `AGENTS.md` was 267 lines, `docs/INDEX.md` mixed guides and dated status updates | Compact agent entrypoint plus [responsibility-first index](INDEX.md) |

## Disposition — avoid destroying history

| Action | Documents / families | Reason |
| --- | --- | --- |
| **UPDATE** | Root `AGENTS.md`, `README.md`, `ARCHITECTURE.md`, `INDEX.md`, `DATA-ACQUISITION.md`, `RUNBOOK.md`, `QUALIFICATION.md` | Make source preference, current authority, status distinctions, commands and navigation discoverable |
| **UPDATE / SUPERSEDE BOUNDARY** | `decisions/2026-11-08-position-first-t300.md`, `FORWARD-PAPER-VIKE-MIGRATION-20261108.md`, `V4-0911-WS-SUBSCRIPTION-RECOVERY-292.md`, `V4-CANONICAL-FRESH-PAPER-20261111.md` | Explain approved target versus currently implemented transport, preserving historical claims |
| **CREATE CANONICAL DECISION** | `decisions/2026-11-11-vike-first-wallet-source.md` | One owner for preferred wallet transport, baseline/reconciliation contract, evidence gates and rollback |
| **KEEP CURRENT OWNERS** | `WALLET-REGISTRY-AGENT-WORKFLOW.md`, `RISK-BUDGETED-K-SIZING-20261106.md`, `PM-03-shadow-account.md`, `PM-04-shadow-hardening.md`, `PRODUCTION-HANDOFF.md`, `GOVERNANCE-GATES.md`, `BLOCKER-RECOVERY.md`, `AGENT-NATIVE-OPERATIONS.md` | Binding independent contracts, now pointed to from the short root/navigation |
| **KEEP AS HISTORICAL / LOGICAL ARCHIVE** | Earlier PM-01, PM-02, Q3, Gemini, E0/equity-NAV, pre-V4 FORWARD-PAPER, CCXT, Marimo DASHBOARD, Pydantic design-grill, Track B/C, 2026-11-04..10 research, reconciliation and incident papers | Immutable experiment/incident/decision provenance: their dated facts stay true as-of capture; they do not override current navigation or the newer transport decision |
| **MERGE NAVIGATION, NOT EVIDENCE** | Repeated ownership and routing explanations in root `AGENTS.md` and the handbook; multiple historical observer/Pydnative release descriptions | Centralize links/authority precedence; preserve distinct experiment bytes, old compatibility contracts and incident timelines |
| **REMOVE FROM CURRENT INSTRUCTIONS** | Old unqualified scaling preference and live-runtime extrapolations, not historical files | Agent should discover target/current from canonical ADRs, not infer present state from stale narrative |
| **PHYSICAL ARCHIVE / DELETE** | None | Moving/deleting historically referenced files risks breaking external links and SHA-pinned evidence; logical historical labeling provides the benefit without destroying identity |

The old `docs/INDEX.md` detailed and historical sections remain available as **navigation into evidence**, not second owners of live contracts. No separate replacement registry, simulator, Guardian, provider transport or duplicate risk policy was created.

## Evidence and release boundaries

- Current Vike stream registry: `hl.fills` and `hl.positions`, wallet filter up to 1,000, explicit fill `min_usd: 0`, key/path connection replacement, REST cursor catch-up and 3-day cursor retention. This proves provider capability, not selected-account full-book parity or a qualified 14/14 migration.
- Official source remains current desired-position authority. A Vike event cannot replace official complete-position evidence without independent baseline, signed native quantity reconstruction, causally observed receipt, deduplication, continuous reconciliation, explicit GAP/STALE handling and dual-run fault tests.
- Service observation on audit day: canonical 16-portfolio paper, official 0811/0911 source and Vike minute-price services reported active. Their install revisions must be queried again, and a process being active does not prove journal health, 14/14 source continuity or positive net economic outcomes.
- The 2026-11-11 $10,000 / 5% daily / 8% trailing paper rules are **scenario assumptions**, not verified prop-firm contract terms. No source migration, account reset, database mutation, broker order, production release or funded authorization was performed here.

## Remaining implementation work (outside this docs-only change)

1. Implement a durable, event-deduplicated Vike source-observation transport and measure actual event lag/coverage.
2. Build and independently reconcile a complete selected-account position state with official baseline and end-to-end recovery semantics.
3. Qualify every selected parent/subaccount across all selected DEX markets with continuous **14/14**, not cumulative, evidence.
4. Demonstrate a versioned, paper-only causal source handoff preserving T+300, immediate risk-off, fixed-k, PM03/04, original journals and Guardian separation.
5. Complete separate deployment/canary, prospective economic research and trading authorization.

**Regression checks:** Markdown relative-path link scan, `git diff --check`, documentation-policy grep, supported CLI/tests and repo lint. See the associated PR for exact command receipts. OptMem is a navigation cache, not source/installed/economic authority.
