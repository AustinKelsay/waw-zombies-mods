---
status: accepted
---

# Modular Feature Gates Inside One Unified Mod Package

All Base Experience Enhancements (Perks Expansion, 6-Class System, Pack-a-Punch Expansion, Elemental & Special Weapons, and Scripted Companions) are built as independently toggleable Feature Modules inside one unified `Mod Package`, extending ADR-0003.

## Considered Options

- **Separate standalone `mods/<name>/` folders per enhancement**: Vanilla Steam Call of Duty: World at War 1.7 only mounts a single `fs_game mods/<name>` folder at a time, so separate mod folders could never be combined in-game or composed into Zombie Gauntlet without maintaining duplicate merged builds.
- **Single unified `Mod Package` with per-module dvar Feature Gates**: Lets each Enhancement be developed, tested, and toggled independently in Solo or Co-op menus, keeps Classic Mode 100% unmodified when disabled, and makes composing Base Experience Enhancements into Zombie Gauntlet trivial later.

## Consequences

- Every Enhancement owns its own GSC module(s), offline contract tests, structured telemetry events, and dvar Feature Gate defaulting to `0` (Classic Mode untouched).
- All modules share one build-staged hook seam in `scripts/build_mod.py` and stay collectively within WaW's 400-FX asset ceiling across all four Stock Maps (especially Der Riese at 329/400 FX).
