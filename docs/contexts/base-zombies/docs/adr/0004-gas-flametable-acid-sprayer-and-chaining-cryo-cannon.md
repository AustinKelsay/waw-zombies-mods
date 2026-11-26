---
status: accepted
date: 2026-11-26
---

# ADR-0004: Gas-Flametable Acid Sprayer & Chaining-Arc Cryo Cannon (0 Added FX)

## Context

Base Zombies ADR-0003 originally modeled `bz_acid_sprayer` and `bz_cryo_cannon` as `weaponType = bullet` hitscan weapons firing single shots (`fireTime = 0.40–0.50s`) to guarantee `0` added FX slots under WaW 1.7's 400-FX ceiling (Der Riese sits at `329/400`). Live playtesting showed that semi-auto hitscan clicks make both Elemental Weapons feel flat and ineffective despite working status effects: Acid Sprayer needs continuous hold-to-spray flamethrower ergonomics, and Cryo Cannon needs Wunderwaffe-style hop-by-hop chaining freeze and damage.

Inspection of stock WaW 1.7 raw assets revealed two key engine capabilities:
1. WaW's `m2_flamethrower_zombie` (`weaponType = gas`, `weaponClass = gas`) renders its continuous stream through a `FLAMETABLEFILE` (`raw/weapons/sp/quinn_flame_firstperson` / `_thirdperson`) driven by **2D materials and dynamic RGB lighting—not `.efx` particle files (`0` FX slots)**.
2. Stock Wunderwaffe (`maps/_zombiemode_tesla.gsc`) is only precached on Shi No Numa and Der Riese and hardcodes instant kills (`health + 666`), whereas a `tesla_gun`-derived projectile/impact watcher in `_bz_elem_new.gsc` can drive a cross-map hop-by-hop freeze chain across all 4 Stock Maps while reusing already-loaded stock frost/electric FX (`0` added FX slots).

## Decision

1. **Acid Sprayer (`weaponType = gas` + Custom Green `FLAMETABLEFILE`):** Convert `bz_acid_sprayer` to `weaponType = gas` / `weaponClass = gas` backed by custom toxic-green first- and third-person `FLAMETABLEFILE` assets (`bz_acid_flame_firstperson`, `bz_acid_flame_thirdperson`) using custom green spray/drip/mist 2D materials and green dynamic lighting (`0` new FX slots). Route stream contact (`MOD_BURNED` / `bz_acid_sprayer` and continuous attack watcher) into the existing Acid slow, 1.50x brittle, and round-scaled melt DOT while depositing throttled sizzling acid puddles along the spray path (with per-player Co-op puddle caps). If any map-specific engine quirk prevents custom flametable rendering, fall back to continuous `Full Auto` spray pulses with the same Acid debuff/puddle loop rather than reverting to semi-auto clicking.
2. **Cryo Cannon (Wunderwaffe-Style Chaining Freeze Bolt):** Rework `bz_cryo_cannon` from a straight beam/cone into a projectile/impact weapon that chains hop-by-hop across nearby zombies (decaying hop radius, scaling max chained targets across Base, Tier 1 PaP, and Double PaP), applying round-scaled frost damage + ~4s freeze to every chained zombie, rendering visible icy arc/frost bursts between hops using verified all-4-map stock FX (`0` new FX slots), and preserving the 2.50x shatter bonus and shatter-splash.

## Consequences

- Both Elemental Weapons deliver distinct, high-impact wonder-weapon ergonomics (hold-to-spray stream vs. chaining freeze arcs) across all 4 Stock Maps while keeping Der Riese's FX footprint at **329/400 (`0` added FX)**.
- `scripts/build_mod.py` and `scripts/generate_bz_weapon_models.py` now own the custom toxic-green flametable materials and `FLAMETABLEFILE` staging alongside custom XMODELs.
- Enhanced Flamethrower (`m2_flamethrower_zombie*`) and Acid Sprayer (`bz_acid_sprayer`) both emit `MOD_BURNED`, so `_bz_elem_stock.gsc` and `_bz_elem_new.gsc` must strictly branch on weapon name (`bz_acid_sprayer` vs. `m2_flamethrower_zombie*`) so Acid never triggers fire DOT and Flamethrower never triggers Acid puddles.
