# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root (the glossary; read `GLOSSARY.md` instead if that file exists). This repo is single-context; there is no `GLOSSARY-MAP.md` and no per-package glossary.
- **`docs/decisions/`**: read ADRs that touch the area you're about to work in. Files are dated `YYYY-MM-DD-<slug>.md` rather than zero-padded `0001-`. When two ADRs disagree, read both and treat the disagreement as unresolved rather than picking a winner.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

Single-context repo:

```
/
├── CONTEXT.md                ← glossary
├── docs/
│   ├── decisions/            ← ADRs, dated: 2026-11-08-position-first-t300.md
│   └── INDEX.md              ← handbook navigation
└── src/copytrade_pm/
```

`AGENTS.md` and `docs/ARCHITECTURE.md` own implementation boundaries; the glossary (`CONTEXT.md`) owns domain meanings only. Don't move implementation detail into the glossary or domain meaning into an ADR.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in the glossary (`CONTEXT.md`). Don't drift to synonyms the glossary explicitly avoids — e.g. "official position book" is not "fills", "first-known time" is not "exchange event time", "paper intent" is not "order".

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-2026-11-08 (position-first T+300), but worth reopening because…_
