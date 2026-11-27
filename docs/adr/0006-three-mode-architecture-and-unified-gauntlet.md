---
status: accepted
---

# Three-Mode Architecture and Unified Zombie Gauntlet

Amends [ADR-0002](0002-points-only-cross-map-carryover.md), [ADR-0003](0003-single-unified-mod-with-dvar-mode-gate.md), [ADR-0004](0004-perk-carryover-across-stages.md), and [ADR-0005](0005-modular-feature-gates-in-unified-package.md): the unified `waw_gauntlet` Mod Package exposes exactly **three** player-facing modes instead of a four-way Classic/Enhanced Gauntlet matrix:

1. **Classic Mode** (`gauntlet_enabled=0`, `bz_enabled=0`) — 100% untouched vanilla Call of Duty: World at War Nazi Zombies on any single Stock Map.
2. **Enhanced Mode** (`gauntlet_enabled=0`, `bz_enabled=1`) — Single-map Base Zombies enhancements (Perks Expansion, 6 Classes, Pack-a-Punch Expansion, Elemental & Special Arsenal, and future Phase 3 systems) playable on any of the four individual Stock Maps.
3. **Zombie Gauntlet** (`gauntlet_enabled=1`, implicitly enabling Enhanced Mode) — Enhanced Mode composed with the endless four-map Gauntlet progression loop and cross-Stage progression carryover.

There is no standalone un-enhanced "Classic Gauntlet" mode and no separate "Enhanced Gauntlet" menu label or launch path.

## Considered Options

- **Keep the 2×2 toggle matrix (Classic, Enhanced, Classic Gauntlet, Enhanced Gauntlet)**: Clutters Solo and Co-op Host Setup menus with duplicate Gauntlet entries, forces players to reconcile two overlapping mode toggles, and duplicates carryover and E2E test paths for a vanilla Gauntlet variant we do not intend to ship.
- **Replace Classic Mode entirely**: Breaks the core requirement that players can still play untouched vanilla Nazi Zombies without unloading the Mod Package.
- **Three-mode model with unified Gauntlet (chosen)**: Keeps Classic Mode 100% isolated, makes Enhanced Mode available on any single Stock Map, and makes Zombie Gauntlet the single definitive progression mode built directly on top of Enhanced Mode.

## Consequences

- **Runtime coupling**: Setting `gauntlet_enabled=1` automatically enforces `bz_enabled=1` and all shipped Base Zombies subsystem gates (`bz_perks_enabled`, `bz_classes_enabled`, `bz_pap_enabled`, `bz_elements_enabled`; unbuilt Phase 3 gates stay `0` until shipped). Internal per-subsystem dvars remain available for isolated single-map testing when `gauntlet_enabled=0`.
- **Simpler Solo & Co-op menus**: Solo exposes Classic maps, single-map Enhanced Mode for all four Stock Maps, and one `"ZOMBIE GAUNTLET"` entry; Co-op Host Setup exposes one 3-mode choice with no way to configure an un-enhanced Gauntlet lobby.
- **Single Gauntlet carryover contract**: Cross-Stage carryover always runs through the unified Base Zombies bridge ([`_bz_gauntlet_bridge.gsc`](../../mod/maps/_bz_gauntlet_bridge.gsc)) alongside points/Points Floor and stock perks, eliminating Classic-Gauntlet-only divergence.
