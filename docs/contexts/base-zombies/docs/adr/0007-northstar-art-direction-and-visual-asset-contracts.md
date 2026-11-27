---
status: accepted
date: 2026-11-27
---

# ADR-0007: Canonical North Star Art Direction & WaW 1.7 Visual Asset Contracts

## Context

With `v0.9.0` establishing functional custom 3D placeholder models for the six custom weapons and four Base Zombies stations, visual consistency, era authenticity, and engine-honest handoff rules needed to be locked before full Blender mesh/texture replacement, Arsenal upgrade visuals, Sapper trap models, Pack-a-Punch material progression, Phase 3 Companion rigs, and 2D HUD icon sets are built.

Unconstrained concept art routinely breaks Call of Duty: World at War 1.7 engine limits (transparent glass refraction, dynamic light spill from `model unlit` shaders, added FX pushing Der Riese past its `400`-FX ceiling, runtime material swaps that WaW 1.7 XMODELs do not support, HUD icon shapes collapsing in monochrome at `24u` / `36px @ 720p`, or weapon-variant suffixes breaking exact-name GSC comparisons and Gauntlet carryover).

To prevent drift across modeling, shader authoring, and GSC wiring, we produced and verified two complete visual North Star packs across six blind multi-model Council review rounds:
- **Core Pack (`v2.1`, Sheets 01–08):** [docs/art/NORTHSTAR_SPEC.md](../../../../art/NORTHSTAR_SPEC.md) (`10` designs = `19` shipped XMODELs)
- **Expansion Pack (`v3.1`, Sheets 09–11):** [docs/art/NORTHSTAR_EXPANSION_SPEC.md](../../../../art/NORTHSTAR_EXPANSION_SPEC.md) (`9` Arsenal/Trap XMODELs, `+8` custom PaP primary variants, `1` Phase 3 Companion rig, `21` 2D HUD materials)

## Decision

1. **Canonical Art Pillar — 1945 Group 935 Field-Retrofitted Dieselpunk (Engine-Honest WaW 1.7):**
   - All custom 3D weapons, traps, stations, and rigs target opaque **`model phong` + opaque `model unlit`** materials only (`≤4` material slots per asset, `≤1` unlit slot, `≤3` emissive groups, `≤30%` vessel/head emissive surface, brass `≤10%` base / `≤15%` PaP exception, **zero added FX slots**).
   - **Governing Precedence Rule:** Whenever an illustrative 1P or 3P paintover differs in micro-placement or display scale from the Hero panel or written WaW-unit dimensions, the **Hero design and explicit WaW-unit specs govern** the Blender/XMODEL build.
   - All 6 handheld weapons occupy distinct hue sectors (`≥24.5°` separation), and Pack-a-Punch tiers remain strictly within `±8°` of their own base hue (zero violet bleed).

2. **4-Primary Custom PaP Variant Scope & Canonical `bz_strip_pap_suffix()` Normalization:**
   - Because WaW 1.7 binds materials into compiled XMODELs referenced by weapon files (no runtime XMODEL material swaps), custom Tier 1 (`_pap1`) and Double-PaP (`_pap2`) finishes are scoped strictly to the **4 PaP-eligible custom primaries** (`bz_acid_sprayer`, `bz_cryo_cannon`, `bz_multi_crossbow`, `bz_blade_boomerang` = `+8` weapon files / `+16` XMODELs). Per ADR-0006 and `_bz_pap.gsc:74-88`, `bz_war_club` and `bz_portal_grenade` remain excluded from 2-tier Pack-a-Punch (`pap_war_club` uses at most `+1` optional standalone `bz_war_club_pap` weapon file). Stock firearms retain their stock / native Der Riese `_upgraded` finish and display the Double-PaP `II` HUD badge.
   - Combined expansion weapon-file delta (`+3` Sheet-9 Arsenal weapons + `+8` primary PaP variants + `0..1` optional War Club PaP = `+11..12` weapon files) must pass linked 4-map pool and FX headroom verification on implementation.
   - **Mandatory Normalization Contract:** Every base-weapon ID comparison across the mod MUST normalize via one shared **`bz_strip_pap_suffix(weap)`** helper while preserving the live suffixed weapon name for `GiveWeapon` / `TakeWeapon` / clip / ammo-refill calls. This explicitly includes Gauntlet carryover save/restore (`_bz_gauntlet_bridge.gsc:141-158, 514-517, 858` — saving base ID + tier and restoring the matching `_pap1`/`_pap2` variant across map transitions), Arsenal display/ownership (`_bz_stations.gsc:1162-1185, 2159`), `bz_is_infinite_single_item_weapon()` (`_bz_rules.gsc:284-296, 336, 361-373`), Medic regen exclusion (`_bz_classes.gsc:1004-1010`), move-speed scaling (`_bz_perks.gsc:116-157`), Acid burn exclusion (`_bz_elem_stock.gsc:397-417`), elemental/special weapon hooks (`_bz_elem_new.gsc`, `_bz_special_weapons.gsc:1606`), `_bz_state.gsc:82, 212`, and `_bz_pap.gsc`.

3. **Sapper Wall-Buy Deployable Traps (`bz_sapper_trap_fire` & `bz_sapper_trap_betty`):**
   - Spawned inside `bz_sapper_on_wall_buy(player, wall_id, origin)` (`_bz_classes.gsc:1758`) using flattened `player.origin - origin` outward push-off (`18u`), `BulletTrace` floor snapping with player-floor fallback **before** committing the cooldown (`:1798`), pitch/roll alignment to `trace["normal"]`, and `SetContents(0)` + `NotSolid()` — replacing the generic green `zapper_light_ready`/`powerup_on` marker FX.

4. **Phase 3 Squad Companion Field-Relay Pack (`bz_companion_rig`, Forward-Looking ADR-0002):**
   - Rigid `j_spine4` mount (`12u × 6u × 14u` body, `~24u` incl. centered whip antenna) with 360° Workshop Amber (`#ffb020`) IFF readability. Must execute `SetModel()` -> `Attach("bz_companion_rig", "j_spine4")` -> `SetContents(0)` + `NotSolid()` and pass Phase 3 Ultimis/Marine fit, shoot-through, and distance-scaled `~500u` fog acceptance gates.

5. **21-Material 2D HUD Icon System, Consolidated `STATUS` Lane & Shared `player.perk_hud` Contract:**
   - Package `21` linked `mod.ff` materials (`64×64` DXT5 `.iwi` textures in `waw_gauntlet.iwd`, `0` FX) with a monochrome-distinct shape hierarchy at `24u` (`36px @ 720p`): **Pointed Steel Shield** (6 Classes), **Beveled Steel Square** (3 new Standard Perks), **Dark-Separated Gold-Bezel Square w/ High-Gap Bottom-Right `"II"` Pip** (7 Baked Tier-2 Perks swapped in-place via `SetShader()` on shared `player.perk_hud` slots `x = perk_hud.size * 30` = `0` extra HUD elements), **Pure Circular Antique-Bronze Medallion** (4 Apex Perks), and **Obsidian/Brushed-Steel `#ffdc82` `"II"` Diamond** (Double-PaP badge).
   - Retire static `CLASS` / `PERKS` / `PERKS+` text lists once icons are active, while **preserving all 6 dynamic live gameplay readouts** (`GREN: clip+reserve`, `2X DMG`, `BURST`, `2ND CH[RDY/USED]`, `QRx<n>`, `INVULN`) in one consolidated **`STATUS`** lane at `bz_get_hud_lane_y(50)` (`UPGRADES` at `y(14)`, `SPECIAL` at `y(32)`, Double-PaP `II` diamond at `x=-12, y=bz_get_hud_lane_y(68)`, keeping `PAP I` and Double-PaP `II` mutually exclusive per `_bz_pap.gsc:1118-1127` and staying under WaW's `31` per-client HUD cap at `19` mod persistent / `~24–26` combined elements).

## Consequences

- Future modeling, texture/material authoring, HUD artwork, and GSC integration PRs have a single versioned visual and technical specification under `docs/art/` with zero ambiguity between concept renders and WaW 1.7 engine limits.
- Every future custom weapon variant or HUD icon implementation automatically inherits the Gauntlet carryover normalization contract, zero-FX guardrail, and `<31` HUD element budget.
- No gameplay code or `mod.ff` assets are changed by this decision record alone; each visual implementation wave (3D weapons/kiosks, Arsenal/Traps, PaP finishes, HUD icons, Phase 3 Companion) links back to this ADR and verifies its linked 4-map pools on `plebdev-ultra`.
