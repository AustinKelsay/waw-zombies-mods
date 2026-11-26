---
status: accepted
date: 2026-11-26
---

# ADR-0006: Melee-Slot Viewmodel Swap for War Club & ActionSlot 2 Weapon for Portal Grenade

## Context

Playtesting and codebase auditing exposed two visual and ergonomic gaps from ADR-0003:
1. **War Club had no 3D model and looked identical to the starting knife.** In WaW 1.7, quick-melee `knifeModel` is defined per held firearm (not per player), and `specialty_altmelee` globally binds `perk_altMeleeDamage` plus Der Riese's `viewmodel_knife_bowie`. Putting War Club in a primary weapon slot would eat one of the player's precious primary slots and break the intended Melee Slot duality (Bowie Knife = single-target 1-hit extreme vs. War Club = group knockback/pushback extreme).
2. **Portal Grenade moved to a `USE + MELEE` chord** after `NotifyOnCommand` proved rejected in Co-op, causing unintended melee swipes and constant collisions with nearby Use triggers (doors, perks, Mystery Box, Stations, revives) while lacking any held/thrown 3D model.

Inspection of `CoDWaW.exe` and stock scripts (`_zombiemode_betty.gsc`, `_c4.gsc`, `_zombiemode_bowie.gsc`) confirmed:
- WaW natively supports temporary viewmodel swaps (`GiveWeapon` / `SwitchToWeapon` / `TakeWeapon`, as in `zombie_bowie_flourish`) without permanently occupying a primary slot.
- `ActionSlot 2` is completely unused across all 4 Stock Maps, and `SetActionSlot(2, "weapon", <weapon_name>)` is natively networked and Co-op-safe (identical to Bouncing Betties on ActionSlot 4).

## Decision

1. **War Club — Melee Slot + Custom 3D Swing Viewmodel (`bz_war_club`):** Keep War Club in the per-player **Melee Slot** (`player.bz_melee_slot == "war_club"`, zero primary weapon slot cost, freely swappable with Bowie Knife at the Arsenal Station). Build custom 3D `viewmodel_bz_war_club` and `world_bz_war_club` XMODELs (`0` added FX). On melee press while War Club is equipped, briefly swap in/swing `bz_war_club` (mirroring WaW's `zombie_bowie_flourish` pattern, with strict weapon-restore safety across downs/switches) and execute the frontal-cone group pushback/bounce-back smash even on air swings (no single-target knife lock-on required).
2. **Portal Grenade — ActionSlot 2 Weapon (`bz_portal_grenade`) + Custom 3D Portal Orb:** Replace the `USE + MELEE` chord with a dedicated Co-op-safe `SetActionSlot(2, "weapon", "bz_portal_grenade")` weapon backed by custom 3D `viewmodel_bz_portal_grenade`, `world_bz_portal_grenade`, and `bz_portal_orb_air` XMODELs (`0` added FX). Firing/throwing launches an arcing 3D portal orb and deploys the squad warp portal at impact, with a visible cooldown countdown on the HUD and zero conflict with Frags, Monkeys/Molotovs, Bouncing Betties (ActionSlot 4), or Use triggers.
3. **Blade Boomerang — Single Infinite-Use Item:** Keep `bz_blade_boomerang` in a primary slot (`clipSize = 1`, `maxAmmo = 0`, zero reserve ammo, excluded from Arsenal ammo refills and Double Ammo/Max Ammo) with a guaranteed return-to-hand catch timer so the single boomerang can be thrown infinitely and never lost.

## Consequences

- Bowie Knife and War Club remain clean, mutually exclusive Melee Slot extremes with unmistakable first-person visuals and zero primary weapon slot tax.
- Portal Grenade works identically in Solo and Co-op with zero Use/Melee trigger collisions and clear visual/HUD affordances.
- `bz_war_club` and `bz_portal_grenade` must be excluded from Mule Kick primary-slot counting, Pack-a-Punch primary weapon eligibility, Field Medic ammo regen, and last-stand weapon stripping (just like `zombie_bowie_flourish` and `mine_bouncing_betty`).
