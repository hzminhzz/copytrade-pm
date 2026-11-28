# Single-owner Copytrade Appliance

Status: implemented from the owner's 2026-11-28 execution request; activation requires the verification contract below.
Review baseline: `a2cf400c3aeb7a9d47be87b6e1576bde3bda2669`.

## Requirements and decisions

Copytrade-PM owns FactStore, RosterStore, canonical CWSA source observation, PM03 paper journals and wallet health. Protected execution belongs to independent Prop-Production. Routine engineering, software activation and recovery are authorized by the single owner. Signed financial policy, first-known evidence, fixed-k, financial history and trading permission remain separate.

1. Use the canonical clean checkout and its frozen uv environment for every retained worker. Systemd supplies process supervision and one target supplies lifecycle. No worker-specific software releases, release controllers, Prefect, dashboard, Site publisher or replacement control plane.
2. Use one private configuration beneath `~/.local/share/copytrade`. Source scopes and paper portfolios are data. Existing source and financial journals retain their paths and identities where an independent consumer or signed policy depends on them. Historical paths are data lineage, never executable deployment choices.
3. Run one canonical source workflow over independently journaled source epochs, one paper workflow over independently journaled financial owners, one shared market quote acquisition, and one daily wallet-health schedule. All use the same code and dependency lock. A failed source outcome remains unavailable, never flat. Restart preserves each owner cursor and rebaselines after a continuity gap.
4. Adopt existing observation membership into RosterStore with original seals, origin clocks and a new adoption clock. An observation selection is not a researched seat promotion. Do not fabricate scorecards, coefficients or financial attestations to populate an empty store. Existing signed paper mandates retain their exact owners and coefficients. New researched seat books continue to use the existing reconciler and signing workflow.
5. Permanently delete web presentation and obsolete executable orchestration. Preserve historical evidence, Git objects, private uncommitted work, unfinished research obligations and financial journals. Archive inactive releases before deleting their executable paths; retain independent account installations.
6. Expose status, configuration reconciliation, update and recovery through the installed CLI. These operations use git, uv and systemd directly. Software updates never sign mandates, mutate Guardian or grant trading permission.

## Structural findings and deletion decisions

| Finding | Kind | Resolution |
| --- | --- | --- |
| Chapter 2/V4Pod3 use f697c036444e, Liquid12 uses 7d1531f and a missing observer checkout, wallet health uses 0e5f6bb, Prefect uses aa68600 | Hidden deployment links | One checkout/environment and one lifecycle |
| Current source/PM03 code expects RosterStore; installed workers still read the retired registry | Hidden adoption dependency | Explicit provenance-preserving membership adoption before cutover |
| Default roster contains one account declaration, zero books, zero leases and zero release bindings | Missing operational adoption | Preserve undeveloped account; adopt authentic observation selections without invented research |
| Six portfolio definitions and wallet counts are Python constants; Liquid12 duplicates the module on a branch | Special case / surplus | One configured paper consumer; same finance implementation and independent journals |
| Source selection imports legacy WS observation just to select addresses | Needless link | Isolate roster selection from historical transport |
| Ops Control Center, Site sync, Grafana and Marimo retain builds, scripts, containers, tests, capabilities and service paths | Explicitly retired surplus | Delete executable UI and publication surfaces; retain dated evidence in Git/docs |
| CI requires npm/frontend success for a Python observation application | Needless link | Remove frontend gate with its feature; retain exact-revision Python, financial and source verification |
| Separate Prefect and wallet-health releases schedule overlapping advisory work | Surplus orchestration | One native daily health capture into FactStore |
| Old research engines and V4/CCXT rollout units remain discoverable as executable choices | Superseded machinery | Remove unused active entry points and deployment scripts; retain required historical replay interpreters |
| Timer-driven ensemble studies and tracker are outside current CWSA observation | Historical obligations | Inspect and preserve their frozen outputs/unfinished assessment before retirement; do not silently claim completion |
| Prop-Production explicitly Wants Chapter 2 source and reads independent account finance | External dependency | Keep source database stable and provide only a systemd alias to the canonical source unit; do not restart or mutate protected accounts |

## Evidence observed before edits

- 239 Python source modules, 93,110 source lines; 74 declared capabilities; 126 locked packages.
- 41 installed Copytrade units (33 services, eight timers), 83 historical release directories, and 40 linked worktrees including the inspection worktree. A verified archive preserves 38 stale worktrees and the retired installations before removal.
- Six Chapter 2 paper journals have financial cursor 0; source receipts are not fills.
- Liquid12 paper journal has cursor 752 and a three-mandate signed bundle; its source stopped at checkpoint 1795527000000.
- Three source journals have 14, 3 and 3 scope heads respectively. Scope/policy/first-known identities must survive unchanged.
- Eight Copytrade timers include an unfinished frozen forward assessment scheduled for 2026-12-02. Retiring its executable machinery must preserve this obligation and originals.
- Canonical `main` is clean. Two local feature worktrees have unmerged work; preserve them before removing stale deployment worktrees.

## Operational limits and preserved obligations

- The pinned registry snapshot has 17 historical seals. One `gemini.phase5/B` selection contains five unresolved wallet IDs (ACT08, N01, N02, N05, N07). Quarantine that entire selection; adopt the 16 complete versions atomically. Never infer wallet addresses or import partial membership.
- Liquid12's signed source generation binds a default-DEX-only scope. The current canonical collector requires a complete DEX census. Its coverage gap remains explicit until a separately approved source generation and mandate transition resolve that policy conflict. Software consolidation does not grant that financial-policy change.
- V4Pod3 has an observation source but no approved paper epoch. Retain observation only.
- The frozen forward assessment due 2026-12-02 00:10 UTC remains an open research obligation after its old timer is retired. Preserve its pinned inputs and handoff; retirement is not completion.
- Full financial replay repeatedly validated the same source history for every event. A replay now verifies each complete source chain once under the journal owner lock and checks every event against that proof. Proofs never survive a replay call. A subsequent restore revalidates all bytes and detects tampering.
- Paper owner groups poll independently within one process. Cancellation drains admitted work before releasing owner leases. Native systemd startup and stop timeouts allow authentic history verification.
- Software update renders units through the newly installed interpreter. Rollback changes software only and never rewinds a financial or source journal.

## Verification contract

Verify authentic journal copies with the new implementation before touching active workers. Assert preserved run/account/mandate identities, exact coefficients, monotone financial and source cursors, source baseline semantics, idempotent membership adoption, known-at cutoffs, unknown-data behavior, health scope and CLI read-only behavior. Test systemd configuration and software rollback without mutating financial policy. Review against this spec and CODING_STANDARDS independently in direct passes. Run required full local CI at the committed candidate and verify active PIDs, working directories, revision and new source/quote receipts after cutover. No economic qualification or trading authorization follows from those tests.
