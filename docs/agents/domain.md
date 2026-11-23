# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`GLOSSARY-MAP.md`** at the repo root: lists all bounded contexts and points at each context's `GLOSSARY.md`. Read `GLOSSARY.md` (Shared Platform) plus every context glossary relevant to the topic.
- **`docs/adr/`**: read system-wide ADRs that touch the area you're about to work in. Also check `docs/contexts/<context>/docs/adr/` for context-scoped decisions when present.

If any context-level file doesn't exist yet, **proceed silently**. Don't flag its absence; don't suggest creating it upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates context ADRs lazily when decisions actually crystallize.

## File structure

Multi-context repo:

```text
/
├── GLOSSARY-MAP.md
├── GLOSSARY.md                                 ← Shared Platform vocabulary
├── docs/
│   ├── adr/                                    ← System-wide decisions
│   │   ├── 0001-vanilla-lobby-assisted-coop-transitions.md
│   │   ├── 0002-points-only-cross-map-carryover.md
│   │   ├── 0003-single-unified-mod-with-dvar-mode-gate.md
│   │   └── 0004-perk-carryover-across-stages.md
│   └── contexts/
│       ├── base-zombies/
│       │   ├── GLOSSARY.md
│       │   └── docs/adr/                       ← Created lazily on first context ADR
│       └── zombie-gauntlet/
│           └── GLOSSARY.md
├── mod/
├── scripts/
└── tests/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in the relevant `GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (example decision), but worth reopening because…_
