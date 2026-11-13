# Agent system design and execution plan

**Status:** DESIGN TARGET, revised 2026-11-12 UTC and aligned with parent specification [#334](https://github.com/hzminhzz/copytrade-pm/issues/334) / D0 ticket [#335](https://github.com/hzminhzz/copytrade-pm/issues/335) on 2026-11-13 UTC. This document owns the proposed agent interaction model and its dependency-aware implementation plan. The documentation revision does not implement the planned interfaces, merge D1–D6 code, authorize deployment, change a signed policy, or grant trading permission.

**Read when:** changing discovery, diagnostics, operator workflows, research-job planning, or cross-repository ergonomics. Start with [architecture](ARCHITECTURE.md) for existing owners and [agent operations](AGENT-NATIVE-OPERATIONS.md) for commands available now. Domain meanings live in [CONTEXT](../CONTEXT.md). Existing source, finance, release and qualification contracts remain authoritative.

## 1. Optimize the next decision

The system should help an agent choose and complete the next useful, authorized action from evidence it can inspect. Optimize decision correctness and reproducibility first; then reduce the reads, context, compute, network traffic and repeated work needed to reach that decision. Cheap but misleading summaries are regressions.

The unit of work is an operator or research objective with a declared scope and a checkable outcome. A repository, service, ticket or module is an implementation owner, not the objective. Examples are: explain why this portfolio cannot produce financial paper effects; establish which release a service is running; compare two policies on admissible follower evidence; repair one missing data interval.

A successful system makes five things easy:

1. Find the correct owner and existing operation without reconstructing the repositories.
2. Distinguish what is known, inferred, hypothesized and unknown, with inspectable provenance.
3. Identify the smallest missing prerequisite that can change the requested decision.
4. Apply a bounded action through its owner and verify its actual effect.
5. Leave a reusable finding, test or corrected contract so the next investigation is cheaper.

Use one coherent navigation and evidence vocabulary across the repositories. Preserve independent source, metadata, paper finance, protected finance and provider authorities. The agent-facing composition layer reads their results; it does not become a new financial authority.

## 2. Linked abstractions

Each layer answers a question using the contracts below it. A higher layer may summarize evidence but cannot manufacture the lower layer's proof or permission.

| Layer | Agent question | Contract and owner |
| --- | --- | --- |
| Identity and time | Which exact object, version and instant are we discussing? | Qualified portfolio/version/seal, source scope/epoch, mandate generation, run, account binding, venue/environment, code revision and original clocks |
| Original evidence | What was actually received or observed? | Source/provider originals and hashes, receipt clocks, journal sequences; provenance retained by the producing owner |
| Owned state | What does that evidence establish here? | SQLite metadata, CWSA continuity, PM03/PM04 paper finance, Guardian finance, provider facts, independent runtime observations |
| Operation assessment | Can this particular operation proceed, and why? | Requested operation plus applicable prerequisites, evidence references, independent dimensions and scoped blockers |
| Owned action | What changes, under whose authority? | Existing owner operation, explicit target/preconditions, current authorization, durable intent where required, bounded effects and recovery |
| Verified outcome and learning | Did the intended result occur, and what should be reused? | Independently checked postconditions, causal receipts, regression evidence and a corrected canonical contract |

The abstraction links must be traversable in both directions: objective → operation → owner → evidence → original receipt; outcome → effect → intent or research job → frozen inputs and policy. An agent should not need to infer those links from filenames, timestamps or service names.

Three uses of “capability” remain distinct: a catalog describes an available software operation; provider evidence describes native account/instrument semantics; Guardian grants financial authority only through its existing protected lifecycle. Neither of the first two is a permit.

## 3. Two feedback loops, one evidence discipline

**Operating loop:** observe the relevant state → assess one requested action → invoke its owner if authorized → verify the resulting effect → reconcile uncertainty. Source-driven changes and follower-account risk protection retain their separate clocks and responsibilities.

**Research loop:** state a falsifiable question → freeze admissible data, trial and cost assumptions → run the smallest informative experiment → compare against independent evidence → retain the result and limitations → propose a separately versioned policy change. Negative and inconclusive results are first-class outputs. Research cannot rewrite historical first-known times or activate its own k proposal.

The loops meet through versioned, reviewed contracts: qualified research can support a new frozen release or mandate; observed outcomes can inform a later research question. They do not meet through an agent changing live parameters in response to a dashboard score.

### Task workflow

| Step | Work | Completion criterion |
| --- | --- | --- |
| Scope | State objective, requested operation, exact target, policy/time context, allowed read/write footprint, resource bound and current authorization | Ambiguous identities resolved; unnecessary private/system-wide reads excluded |
| Locate | Use the index and capability record; inspect the owner and relevant public behavior | One owner for each fact and effect; existing interfaces and concurrent work identified |
| Inspect | Read the cheapest sufficient owner evidence; follow references only for disputed or missing facts | Each material claim has evidence, scope and clock, or an explicit unknown |
| Decide | List causal blockers, unaffected work and the smallest next action that could change the result | A reviewable action with preconditions, expected effect, verification and recovery; no unrelated universal gate |
| Act and verify | Use the existing owner, retain original operation identity across retry, inspect independent postconditions | Verified effect, explicit rejection, or unresolved outcome retained by its owner |
| Retain | Update the relevant test/contract/catalog and preserve the evidence receipt | A later agent can reproduce the conclusion without reading the whole conversation |

These are conceptual workflow steps, not new CLI verbs or a required new workflow engine. Read-only questions finish after the relevant inspection and supported answer. Existing authorization carries forward within scope; do not add an approval ceremony for every step.

## 4. Operation discovery and result contracts

Extend [pm_capabilities](../src/copytrade_pm/pm_capabilities.py) and the existing [operations facade](../src/copytrade_pm/pm_operations.py). Keep domain logic and strict wire contracts with their owners. Do not add another service, global state machine, plugin platform, financial database or general command executor.

### Operation record: target additions

Every public command leaf or materially different effect mode should resolve to one reviewed record. A parent command's safety class cannot describe every child or an optional `--apply`.

| Record element | Required meaning |
| --- | --- |
| Stable operation identity | Exact supported entrypoint/subcommand/mode, input schema and required arguments; aliases resolve to the same owner |
| Owner and contract | Canonical guide, public implementation boundary, behavioral tests and relevant version |
| Effects and access | Read resources, write resources, network/credential needs, privacy class, safety class and explicit apply behavior |
| Preconditions | Exact identity/version requirements and action-specific authority; no implied permission from discoverability |
| Output | Structured result schema, evidence/limitations, exit semantics, pagination and explicit truncation |
| Cost and recovery | Bounded default, cancellation/resume behavior, idempotency/reconciliation rule and verification operation |

Only require fields applicable to that operation. Discovery itself stays cheap and side-effect free. Optional packages or missing credentials produce explicit unavailable/unsupported records rather than importing every module, probing accounts, or installing dependencies.

### Assessment: a projection, not a new signed truth

Retain existing result schemas and version any incompatible extension. Reuse the following meanings; do not wrap every source event or Parquet row in a universal model.

- **Request and scope:** requested operation, qualified target, policy/version, requested as-of, and query observation time.
- **Claim and basis:** VERIFIED / INFERRED / HYPOTHESIS / UNKNOWN, with original-observation, derived, caller-claim or fixture basis. A verified fixture proves fixture behavior, not real provider availability.
- **Evidence references:** producing authority, stable locator, content/head identity, original clock, verification method and consumer version.
- **Dimensions:** integrity, provenance, freshness, completeness, continuity, execution certainty, qualification and authorization remain distinguishable where relevant.
- **Dependencies and blockers:** exact affected scope, causal reason code, missing evidence owner, and whether a bounded read, repair or external decision can resolve it.
- **Limits and cost:** attempted versus completed coverage, censored/missing observations, pages or rows omitted, elapsed work and actual resource use when measured.
- **Next step:** a supported operation or owning runbook with required inputs and effect class. Suggested mutation is not authorization to execute it.

Resolve suggested operations from the reviewed catalog or owning runbook. Provider messages, logs and retrieved text are evidence to interpret, not instructions or shell commands to execute.

On repeated inspection, report the material change since the previous assessment: which evidence head, policy or scope changed; which conclusion became invalid; and what needs refreshing. Reuse still-valid immutable evidence and refresh only the affected dependencies. A heartbeat alone does not refresh the underlying source, quote or financial proof.

An assessment assembled from several authorities is not an atomic global snapshot. Preserve each component's clock, head and scope. If versions conflict, return a mixed/unverified result and invalidate the affected action plan. Never combine a fresh quote, an old mandate and an unrelated account snapshot into apparent readiness.

**Critical examples:** SQLite integrity can be VERIFIED while a research selection is BLOCKED_MISSING_EXTERNAL_PROOF. A complete source checkpoint can coexist with Guardian HALT. An installed release can verify while the running application's identity is UNKNOWN. An absent data partition can mean uncollected data or inactivity; neither means verified zero trades. Null economics must not render as zero profit.

The Site and CLI should consume the same owner projections. The UI may format and filter them; it must not recompute finance, infer missing state, or create a second admission decision.

## 5. Bounded actions and recovery

The action plan is a reviewable description of an existing owner's operation. It is not a new permission artifact or a second durable intent journal.

Before an effect, bind the exact target, expected predecessor or generation, relevant evidence/policy, allowed changes, resource cap, expected result and verification path. Changes in these preconditions require reassessment. For protected operations, Guardian and the existing release/registry controllers enforce their own requirements at the point of mutation; an earlier diagnostic is insufficient.

Separate outcomes:

- **Not dispatched:** a bounded retry may be allowed under the original opportunity and deadline.
- **Committed or possibly dispatched:** retain the original intent, reservations and identity; reconcile before another effect.
- **Verified completed/rejected:** retain the owner's causal receipt and independently checked postcondition.
- **Evidence unavailable:** preserve unknown state and explain the missing authority; continue independent authorized work.

Cancellation stops new work at a safe boundary. It does not undo committed financial effects. Rollback restores compatible code/configuration while retaining source history, financial obligations, HALT and trust floors. A crash between a durable effect and a status update is recovered from the owning journal, never from the stale presentation file.

Failures isolate to causal dependents. A wallet-specific source gap blocks that source's new risk; shared account limits, signer failure or broker uncertainty can legitimately block a wider scope. The projection must show both the local cause and the actual shared dependency.

## 6. Resource-aware research and inspection

Choose work by the decision it can change. Use this order: resolve identity → inspect catalog/coverage and immutable receipts → reuse valid existing results → plan missing work → run a bounded probe → execute only the necessary remainder → verify and publish the result through its existing owner.

| Resource | Design requirement |
| --- | --- |
| Context and tool calls | Short task summary first; evidence by reference; bounded pages; task-relevant recall; no full journal, all-history memory or repository-wide scan by default |
| Data acquisition | Frozen source/cohort, selected DEX/instruments, exact date interval, provider budget, missing-partition plan and incremental resume |
| Remote reads | Estimate source objects/columns/row groups and compressed bytes; measure actual reads/requests. A wallet filter or small returned row count does not prove cheap remote I/O |
| Compute and storage | Plan memory/disk/work limits and checkpoint boundaries; reuse existing Polars/DuckDB/Parquet and job owners; stop explicitly at the bound |
| Provider access | Bound concurrency and shared-IP/request cost; report expired/inaccessible credentials; reuse approved identity and access flow |
| Tests | Run risk-relevant public behavioral checks; use exact-revision evidence for merge/release gates; expand only for a concrete remaining risk |

A reusable result is keyed by immutable inputs and relevant scope, as-of, schema, policy, assumptions, code/consumer and dependency versions. Changing any meaning-bearing input creates a new result identity. Record whether the result was executed or reused and why it remains applicable. TTL alone is not provenance.

Cache immutable research and evidence verification where valid. Re-read mutable authorization, account state, quotes, HALT and runtime identity when the owning operation requires it. Never cache a permit as a reusable approval. Cache invalidation must expose which dependent claims need re-evaluation without rewriting their historical receipts.

Use [pm_offline_job](../src/copytrade_pm/pm_offline_job.py), its [catalog](../src/copytrade_pm/pm_offline_job_catalog.py), [data acquisition](DATA-ACQUISITION.md), and the existing source-specific storage owner. Inspect any active acquisition work before extending it. In particular, [PR #332](https://github.com/hzminhzz/copytrade-pm/pull/332) is a separate Reservoir history/backfill candidate; its open status and prepared-versus-completed results require rechecking. This design neither duplicates that acquisition nor authorizes a larger roster, extra DEX scope or automatic resumption.

Do not adopt an orchestration product merely to display task state. [Prefect](TRACK-B-PREFECT-ORCHESTRATION-20261110.md) remains optional research scheduling; the financial/source hot path retains its existing owners. Long deterministic batches may use an explicitly authorized worker, with ChatGPT retaining decisions and evidence review.

## 7. Make knowledge accretive

Every resolved ambiguity should reduce future reconstruction cost. Retain the smallest durable artifact at the layer that owns the lesson.

| Finding | Durable home | What stays out |
| --- | --- | --- |
| Domain meaning or ownership | CONTEXT, architecture, or a scoped ADR | Process IDs, balances, temporary blockers |
| New supported operation or corrected effect classification | Capability record and its canonical guide | Another independently maintained command list |
| Defect or misleading diagnostic | Public behavioral regression plus the owning contract | A memory note presented as a fix |
| Research result, including negative result | Immutable job/experiment receipt with frozen inputs, trial lineage, limitations and supersession links | Retrospective promotion into PIT or hidden repeated trials |
| Incident and recovery | Existing incident/evidence record and bounded runbook correction | Rewriting original journals or clearing financial latches from prose |

An agent-authored explanation is a claim until its basis is checked. Repeating it in memory, a dashboard and a report does not create three independent sources. Use independent accounting/quantity oracles for financial tests and independent host-owned traces for actual agent-performance claims.

Keep one current contract for each meaning. Index by the question a reader has. Mark documents as current contract, design target, implementation ledger, or dated evidence; state the boundary superseded when replacing an instruction. Preserve historical results by link and Git history rather than appending every release narrative to the architecture.

A completed slice updates the owner, caller-facing contract, affected capability record, necessary behavioral test and navigation together. A pause/handoff retains objective, exact worktree/revision, changed paths, validated receipts and unresolved dependencies in the existing work record; durable memory retains policies and canonical pointers, not that temporary state.

## 8. Verified baseline and implementation frontier

Reviewed source baselines for this design: copytrade-pm `1c4ac38e76dc7ed31e3421273269750b2f03e086`; prop-production `22861edd5e42bed4e5bf8eb286423928afdcf937`; trading-connector `1a9cc6b39e78dc7745e3b5675df8abc838a9bd9a`. These are inspected source revisions, not a claim that those three heads run together. Protected companion pins come only from prop-production's `src/prop_production/compatibility.json`.

Existing foundations include the capability directory, read-only operations facade, registry-native readers, isolated paper journals, CWSA/mandate transitions, Guardian reconciliation and provider capability contracts. Reuse the [Pydantic acceptance](PYDANTIC-NATIVE-ACCEPTANCE-RESULTS-20261109.md) and [CWSA implementation ledger](CANONICAL-5M-IMPLEMENTATION-313.md); do not restart their completed engineering from an older planning document.

### D0 — coherent documentation (this revision)

Reframe the architecture and index around owners and user questions; separate current interfaces from this target; correct stale pin/UI routing and the session integration backlog. Preserve the accepted trading policies and all original scientific evidence.

Acceptance: every changed document has an unambiguous role, reachable owning guide and valid links; competing current instructions are resolved; code and runtime remain unchanged.

### D1 — truthful registry diagnostics

**Owner:** `wallet_registry`, `pm_operations`; downstream `pm_contract_selector`. **Dependency:** D0; independent of D2/D3.

At the reviewed baseline, `_generation` produces VERIFIED while `_read_registry` and `_wallets` compare against CURRENT, and `_doctor` strips native `research_selection_integrity` and maps a legitimate exit-2 selection-proof block to a SQLite-integrity failure. Generation lookup also delegates to broad `status`, which can reach financial runtime state unnecessarily.

Deepen the existing metadata seam. Retain `research_selection_integrity` alongside `database_integrity`, `inventory_sha256` and historical import lineage in `pm_operations._doctor` and native readers. Resolve metadata without opening paper/Guardian journals. Delete the contradictory facade translation and broad metadata-to-runtime dependency; in `pm_contract_selector._registry_identity`, check SQLite integrity and the requested portfolio's independent seal/proof so an unrelated blocked `--current` selection does not reject an independently sealed portfolio while unsigned selections remain blocked.

Acceptance through the public facade: valid metadata; valid SQLite plus missing selection proof (preserving the existing mocked count-mismatch doctor test distinct from a new native exit-2 regression); true corruption; missing database; later SQLite-only cohort; explicit historical as-of; unrelated selection block. Prove zero financial-reader calls for metadata-only operations and no promotion of the blocked selection. Reuse [operational discovery tests](../tests/test_pm_operational_discovery.py).

### D2 — truthful running-release evidence

**Owner:** `pm_runtime_readonly`; callers `pm_cwsa_chapter2_gate` and existing deployment diagnostics. **Dependency:** D0; independent of D1/D3.

At the reviewed baseline, the Chapter 2 verifier can accept a live unrelated PID alongside a valid configured checkout. Its installed/configured checks do not independently bind that PID's application launch to the expected release. A health endpoint's self-reported revision is also insufficient.

Deepen the existing runtime reader with one parameterized process/release verifier reused across both existing V4 and CWSA Chapter 2 unit names (keeping their scopes distinct), and remove duplicate partial proof composition from callers. Report configured unit, installed immutable bundle, observed process identity and freshness separately. Obtain process liveness separately from release-binding evidence, and in `pm_cwsa_chapter2_gate.GateCheck` (`PASS | BLOCKED_EVIDENCE | FAIL`) map active-but-unproved binding to `BLOCKED_EVIDENCE` rather than `PASS` or `FAIL: PAPER_SERVICE_NOT_RUNNING`. Handle restart/PID reuse and inspection races; preserve UNKNOWN in `pm_runtime_readonly` when protected evidence is inaccessible. Python interpreter identity, cwd or a startup claim alone cannot prove all loaded application bytes.

Acceptance: correct release; valid configured checkout plus unrelated process; process from old release; mutable source; PID reuse; restart during inspection; hidden process metadata; stale self-report. Return no stronger claim than the independent evidence supports. Rollout uses existing release owners; no new privileged inspector daemon or permission expansion is assumed.

### D3 — complete operation discovery

**Owner:** `pm_capabilities` and existing parser/entrypoint owners. **Dependency:** D0; independent of D1/D2.

At the reviewed baseline, the public `cwsa chapter2 verify` and `projection` leaves are absent from catalog coverage even though validation can pass. Enumerated scripts and curated module entries are not proof of complete public leaf coverage.

Add explicit records and a closed coverage check for supported public command leaves/effect modes (`cwsa chapter2 verify/projection`, `portfolios list`, `research show`, `contracts rules`, `status`, `capabilities list/show/validate`), register missing `REGISTRY_REQUIRED_ARGUMENTS` for `native exclude` / `native exclude --apply` (`--expected-inventory-sha`, `--expected-manifest-sha`, `--manifest`), and distinguish material `GROUPS` modes (`public-trades --mode observe|plan`, `public-observer-unit --apply`, shadow/receipts modes). Validate against actual supported parser subcommands and declared scripts without running provider/account mutations during discovery. Preserve the existing four-class safety taxonomy (`READ_ONLY | LOCAL_MUTATION | PROTECTED_MUTATION | BROKER_OR_TRADING`). Retain stable IDs, conservative classifications, required inputs and module-only records; avoid importing arbitrary modules or inventing a plugin registry.

Acceptance: existing leaves covered; an added uncataloged public leaf fails; `--apply` cannot inherit read-only status; alias/mode handling is explicit; optional dependency absence remains truthful; catalog validation itself performs no provider/account I/O.

### D4 — one scoped explanation from existing owners

**Owner:** `pm_operations` and existing CWSA/Site projections; protected diagnostics remain in prop-production. **Dependencies:** D1–D3.

Implement only the missing composition needed by the task examples below. Preserve each owner's schema/semantics and make evidence drill-down explicit. Show causal blockers, unaffected scopes and a supported next operation. Avoid a persistent duplicate “system state” database or a new all-purpose readiness flag.

For prop-production, follow the coordinated candidate's `prop-production:docs/EXECUTION-SESSION-20261111.md` and inspect the actual Guardian source/mandate/account-proof owners before integrating a native evidence adapter. Its v1 caller claims and T+300 checks are not a CWSA or permission interface. That companion document owns the updated integration plan; dated source permalinks are baseline evidence only.

Acceptance: source healthy/finance blocked; one wallet gap/independent portfolio unaffected; stale or conflicting component generations; fixture basis visible; missing financial P&L remains null; CLI and Site agree on the same projection. A suggested next action never dispatches itself.

### D5 — bounded, reusable research work

**Owner:** existing acquisition/storage adapters, `pm_offline_job` and its catalog. **Dependencies:** D3; D1 for portfolio-bound scope; D4 only where a composed explanation is needed.

Add only missing preflight/cost/coverage/resume information at those boundaries, after inspecting and reconciling the concurrent untracked `copytrade_pm.wallet_store`, `docs/WALLET-STORE.md`, Reservoir DuckDB plan and open PR #332 alongside the established offline-job owners. Reuse immutable source and completed job evidence; avoid rescanning remote history per wallet or reconstructing unmerged parallel work. Preserve the chosen cohort, DEX/date bounds, PIT exclusions and full trial history. Any no-new-module stopping conclusion requires executable tests, not prose alone.

Acceptance: valid cache hit; changed input invalidates reuse; empty versus uncollected interval; interrupted acquisition resumes only missing verified units; expired access stops explicitly; byte/request/disk budget reached without wider scan; missing coverage blocks the relevant conclusion. Measure source bytes and end-to-end work, not only small output size.

### D6 — measure and retain the improvement

**Owner:** existing [agent trace evaluation](AGENT-TRACE-EVAL-20261105.md), public behavioral suites and canonical docs. **Dependencies:** the slices being compared, not every unrelated program.

Replay fixed tasks against baseline and candidate with the same evidence, permissions and resource bounds. Compare supported-answer accuracy, abstention correctness, unsafe/off-target calls, tool calls, bytes, latency and repeated work. Use the existing independent host-trace protocol for claims about model-selected behavior. Scripted CLI fixtures verify contracts; they do not establish observed agent productivity.

Retire a wrapper, document or running component only after static callers, entrypoints, runbooks, installed units/timers and historical reproducibility obligations have been checked. A zero-reference search alone is insufficient. Keep only abstractions that reduce caller knowledge or verified effort.

## 9. End-to-end acceptance tasks

| Task | Successful behavior | Falsifier |
| --- | --- | --- |
| Resolve a portfolio | Reach owner within two documentation links from AGENTS; resolve qualified version/as-of and evidence | Bare-name collision, old Markdown roster, or unnecessary financial-journal read |
| Explain blocked paper | Separate source collection, sealed metadata, signed mandate, quotes and financial effects | Active process or empty journal presented as financial admission |
| Establish deployed identity | Distinguish candidate, installed and running revisions; state the exact unverified part | Valid unit configuration plus unrelated PID reported as running expected code |
| Change frozen k under authorized scope | Research evidence → new reviewed generation → independent owner admission and future baseline | Editing historical seal, automatic activation or clearing old exposure |
| Investigate one source gap | Preserve original clocks and affected scope; identify independent work | Backdated signal, fabricated flat or unrelated global halt |
| Plan a historical study | Reuse verified inputs/results, expose missing coverage, bound reads and trial use | Full rescan without preflight, ex-post cohort labeled PIT, output size treated as read cost |
| Recover an interrupted action | Read the original owner effect, reconcile uncertain outcome and resume safely | New intent ID or fresh deadline after possible dispatch |
| Hand off and continue | Recover objective, exact candidate, receipts and next unmet dependency from a compact work record | Repeating the entire audit or treating a previous answer as current evidence |

Two links is a navigation target, not a claim already empirically met for every workflow. Resource/performance thresholds must be registered against a measured baseline before claiming improvement. Success requires correct answers and preserved authority boundaries; fewer tool calls alone cannot pass.

## 10. Delivery, migration and stopping rules

Execute future authorized engineering as small vertical slices with one accountable owner, public behavior, negative case, required caller migration, explicit deletion and a bounded rollback. D1, D2 and D3 are independent implementation branches after D0. D4 follows their truthful foundations. D5 may proceed independently where its existing owners already supply them. D6 evaluates each completed slice.

Keep existing public contracts readable during migration; version incompatible output semantics. Prop-production alone owns cross-repository compatibility pins. Do not repin every repository head together, copy pins into instructions, or reopen completed Pydantic/CWSA work because an old roadmap lists it.

The [Chapter 2 runbook](CWSA-CHAPTER2-20261112.md) still owns its premerge/predeploy/postdeploy gates. Parent [#313](https://github.com/hzminhzz/copytrade-pm/issues/313) and its original prospective/economic/release acceptance remain unchanged; six Chapter 2 portfolios do not satisfy the original sixteen-portfolio requirement. Existing external blockers remain blockers.

This plan is complete when the scoped interfaces and acceptance tasks are evidenced at exact revisions, duplicated caller logic is removed, documentation routes are current, and measured benefit justifies the added surface. Stop adding abstraction when the existing owner already answers the question correctly within budget. Engineering verification, merge, deployment, prospective paper activity, economic/scientific qualification and trading authorization remain separate outcomes.
