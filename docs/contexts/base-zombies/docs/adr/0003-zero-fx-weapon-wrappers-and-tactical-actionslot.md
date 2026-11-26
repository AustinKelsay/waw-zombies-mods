---
status: accepted (partially evolved by ADR-0004 and ADR-0006)
date: 2026-11-23
---

# ADR-0003: Zero-FX Cloned Primary Weapons, Melee-Slot State & ActionSlot 2 Portal Key

## Context

Base Zombies Phase 2 (#19) adds four Elemental Weapons (Enhanced Flamethrower, Wunderwaffe DG-2 fix/stun, Acid Sprayer, Cryo Cannon) and four Special Weapons (War Club, Multi-Crossbow, Blade Boomerang, Portal Grenade) to the unified `waw_gauntlet` mod package. Primary-source inspection of stock WaW 1.7 fastfiles and `CoDWaW.exe` (`docs/research/phase2-phase3-engine-feasibility.md`) revealed four hard engine constraints:

1. **400-FX ceiling:** Der Riese already sits at `329/400` runtime FX; adding custom weapon muzzle/trail/impact FX risks tripping the fatal 400-FX crash across maps.
2. **Primary weapon slots:** Only three real-model stock primary weapons (`colt`, `walther`, `mg42`) are unused across all four maps, and `colt` collides on `ammoName` with `zombie_colt`.
3. **Melee slot:** Stock Bowie Knife binds `specialty_altmelee` to the global `perk_altMeleeDamage` server dvar, so a second melee weapon cannot use `specialty_altmelee` without clobbering Bowie players.
4. **Tactical input:** `SecondaryOffhandButtonPressed()` and `ActionSlot*ButtonPressed()` do not exist in `CoDWaW.exe`'s PlayerCmd table, while ActionSlot 1 and ActionSlot 2 are completely unused across all four stock zombie maps.
5. **Wunderwaffe Juggernog bug:** Stock `tesla_pvp_thread()` in `_zombiemode_tesla.gsc` listens to `"weapon_pvp_attack"` (bypassing `level.overridePlayerDamage`) and writes `self.health` directly without restoring `self.maxhealth`, wiping Juggernog I/II and Titan HP.

## Decision

1. **Zero-FX Cloned Primary Weapon Definitions:** Define four lightweight cloned text weapon files (`bz_acid_sprayer`, `bz_cryo_cannon`, `bz_multi_crossbow`, `bz_blade_boomerang`) with `inventoryType = primary`, distinct `ammoName` values, already-loaded stock view/world models, and FX fields restricted strictly to empty `""` or the 89-FX all-4-map stock intersection. Drive elemental/projectile/boomerang effects from per-player `"weapon_fired"` watchers reusing already-loaded map FX (`0` new FX slots).
2. **Per-Player Melee Slot State:** Track `player.bz_melee_slot` (`"knife"` | `"bowie"` | `"war_club"`). Equipping War Club clears `specialty_altmelee` and routes heavy damage + frontal AOE knockback through the existing `"actor_damage"` hook; switching back to Bowie restores `specialty_altmelee`.
3. **Networked Tactical Key for Portal Grenade:** Bind Portal Grenade per-player via `player NotifyOnCommand("bz_portal_throw", "+actionslot 2")` (leaving Frags, Monkeys/Molotovs, and Bouncing Betties untouched) and reuse Der Riese's native `transporter_*` FX + `SetTransported()` (with all-4-map stock fallbacks).
4. **Build-Staged Wunderwaffe Fix:** Patch `maps/_zombiemode_tesla.gsc` at build time (guarded by `bz_elements_enabled()`) so `tesla_pvp_thread()` preserves `self.maxhealth` and calls `bz_recompute_player_max_health(self)` after any self-shock.

## Consequences

- Acid Sprayer, Cryo Cannon, Multi-Crossbow, and Blade Boomerang behave as first-class primary weapons inside Mule Kick I/II (3–4 slots), Mystery Box, Arsenal Station, and Double Pack-a-Punch with **0 new FX slots**.
- War Club and Bowie Knife swap cleanly per player in Co-op without affecting teammates' melee damage.
- Portal Grenade works identically for host and remote Co-op clients on a dedicated tactical key with zero offhand slot conflicts.
- Wunderwaffe DG-2 self-shock can never strip Juggernog I/II or Titan max health.
