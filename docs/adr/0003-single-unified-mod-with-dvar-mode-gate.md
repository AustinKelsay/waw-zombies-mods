---
status: amended by ADR-0006
---

# Single unified mod package with dvar mode gate

Zombie Gauntlet ships as one unified script-and-UI mod package (`mod.ff`) that runs across all four stock Nazi Zombies maps (`nazi_zombie_prototype`, `nazi_zombie_asylum`, `nazi_zombie_sumpf`, `nazi_zombie_factory`), gated behind a dedicated mode dvar (`gauntlet_enabled`) exposed in both the Solo and Co-op Host Setup menus so Classic Mode remains completely unaffected when disabled.

## Considered Options

- **Separate mod packages per stock map (like asset-heavy overhauls such as Nazi Zombies Remastered)**: Necessary when bundling large custom weapons/models/FX per map to stay under the 400-FX cap, but breaks a single-Run multi-map mode because players would have to unload and reload a different mod package between every Stage.
- **Replace Classic Mode outright**: Forces players to unload the mod whenever they want a normal single-map Nazi Zombies match.
- **Single script/UI mod with mode gate**: Because Zombie Gauntlet adds only GSC logic and UI menu/HUD elements (no heavy FX/weapon/model assets), one fastfile easily fits within stock engine limits across all four maps while preserving Classic Mode side-by-side and exposing deterministic dvar controls for automated testing.

## Consequences

- All four stock maps share one unified `_zombiemode` hook and Gauntlet state module; changes ship in a single mod folder.
- Future features added to this mod must avoid heavy global FX/weapon/model bundling that could push any stock map over WaW's 400-FX asset ceiling.
- Automated verification agents can launch any Cycle, Stage, or Classic Mode regression check directly via command-line dvars without navigating menus.
