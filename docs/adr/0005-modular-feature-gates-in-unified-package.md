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

## Base Zombies economy and live verification

The tuned Base Zombies economy caps purchases at 5,000 points for Tier 2 Perks, Classes, Pack-a-Punch upgrades, Elemental Weapons, and Special Gear. Apex Perks use an 8,000-point cap.

The explicitly gated live scenarios stay in [`_bz_selftest.gsc`](../../mod/maps/_bz_selftest.gsc). The selftest module uses grouped callbacks from the modules that own the tested functions to reduce cross-file compiler references and preserve headroom under WaW 1.7's `MAX_PRECACHE_ENTRIES` limit.

## WaW 1.7 Solo vs Co-op server-simulated perk dvars

In WaW 1.7, `player_sprintTime`, `player_sprintSpeedScale`, `player_adsStrafeSpeedScale`, `perk_weapReloadMultiplier`, and `perk_weapSwitchMultiplier` are server-simulated dvars shared across the listen host. To prevent one player's perks (or downs) from mutating teammates' sprint or reload physics in Co-op, Base Zombies applies those five dvars in Solo only (resetting them on mid-match 1→2 join and re-applying them on 2→1 disconnect). In Co-op, Stamin-Up and Speed Cola II apply strictly per-player effects (`SetPerk`, `SetMoveSpeedScale`, and client-local `cg_weaponCycleDelay 0` Fast Swap).
