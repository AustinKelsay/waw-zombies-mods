---
status: accepted
date: 2026-11-26
---

# ADR-0005: Build-Staged 3x `maxAmmo` Stock Weapon Overrides with Strict 1x Classic Clamp

## Context

In WaW 1.7, `SetWeaponAmmoStock(weapon, amount)` is hard-clamped by the engine to the compiled weapon file's `maxAmmo` field. Custom `bz_*` weapons already set `maxAmmo = 3 * base_reserve` so Double Ammo (2.0x) and Double Pack-a-Punch (1.5x, composing to 3.0x) display true reserve counts on the native HUD. Stock zombie weapons kept their stock `1x` `maxAmmo`, so `_bz_perks.gsc` banked extra reserve in a hidden script-side `player.bz_overflow_reserve` pool and drained it on reload.

Live playtesting exposed two severe UX failures from hidden overflow:
1. **Invisible extra ammo:** The native bottom-right ammo counter stays frozen at `1x` (e.g., `200`) until the player burns through the entire invisible overflow pool.
2. **Wall-buy ammo lockout:** Because `bz_overflow_reserve` continuously tops engine stock back to `WeaponMaxAmmo(w)`, stock `_zombiemode_weapons.gsc` sees full ammo and refuses wall-buy ammo refills while overflow is depleted.

## Considered Options

- **Option A (Chosen): Build-staged `3x maxAmmo` stock weapon overrides + runtime `1x` clamp.** Extract stock zombie primary weapon files during `scripts/build_mod.py`, stage `maxAmmo = 3 * stock_maxAmmo` in `mod.ff` (`0` added FX slots), and enforce the canonical `1x` reserve ceiling in script whenever Classic Mode (`bz_enabled = 0`) or neither Double Ammo nor Double PaP is active.
- **Option B (Rejected): Keep stock weapon files untouched and render a secondary `+200` HUD overflow badge.** Avoids touching stock weapon files, but leaves the native WaW ammo counter showing the wrong number and still requires patching stock wall-buy fullness checks to avoid ammo lockouts.

## Decision

Stage `3x maxAmmo` overrides in `mod.ff` for stock zombie primary weapons (base and `_upgraded` across all 4 Stock Maps) while keeping `startAmmo`, `clipSize`, damage, and all FX fields identical to stock. Enforce canonical reserve ceilings (`1x` in Classic Mode or unboosted Base Zombies, `1.5x` with Double PaP, `2.0x` with Double Ammo, `3.0x` with both) on weapon acquisition, `GiveMaxAmmo`, Max Ammo powerups, wall-buys, Mystery Box draws, and Pack-a-Punch. Retain `bz_overflow_reserve` only as a defensive fallback (surfaced via a visible HUD indicator if any un-staged weapon ever exceeds its engine cap).

## Consequences

- Players see the true doubled (`400`) or tripled (`600`) reserve count directly in WaW's native bottom-right ammo counter, and wall-buy ammo purchases work naturally whenever stock is below the active cap.
- **Classic Mode invariant:** Because `mod.ff` raises `maxAmmo` on staged stock weapons, Classic Mode (`bz_enabled = 0`) **must** clamp reserve stock to `1x` on Max Ammo powerups and wall-buy/Box refills (covered by automated Classic Mode non-regression tests).
- `scripts/build_mod.py` must generate a deterministic stock-weapon `1x` lookup table (or derive `base_max = WeaponMaxAmmo(w) / 3` for staged weapons) so `_bz_rules.gsc` / `_bz_perks.gsc` / `_bz_pap.gsc` never confuse the `3x` engine cap with the `1x` baseline.
