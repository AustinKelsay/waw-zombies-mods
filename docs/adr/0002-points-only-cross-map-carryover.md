---
status: amended by ADR-0004
---

# Points-only cross-map carryover with Points Floor and Prep Phase

Between Stages, Zombie Gauntlet resets weapons, perks, and map doors to each stock map's fresh sandbox while carrying over each player's points balance, topped up to a round-scaled Points Floor (`500` on Round 1; `starting_round * 500` on Cycle 2+). Cycle 2+ Stages open with a 45-second Prep Phase before zombies spawn so players can spend their points to gear up before high-round enemies arrive.

## Considered Options

- **Full loadout carryover (weapons, Pack-a-Punch, perks)**: Stock maps have incompatible weapon and perk asset pools (Nacht der Untoten has no perks or Pack-a-Punch; Verrückt lacks Pack-a-Punch and Hellhounds/Wunderwaffe). Porting cross-map assets into one package risks exceeding WaW's hardcoded 400-FX and weapon limits and breaks each map's distinct identity.
- **Clean-slate stipend (no point carryover)**: Eliminates cross-map risk-reward economy and removes the incentive to manage points cleanly before Stage Clear.
- **Points carryover + Points Floor + Prep Phase**: Preserves run-wide economic momentum, prevents Cycle 2+ soft-locks or instant wipes, keeps each stock map's authentic sandbox intact, and stays strictly within stock asset budgets.

## Consequences

- Each Stage plays authentically to its stock map's native weapon box, perks, and progression layout.
- Economic skill compounds across a Run without requiring custom cross-map weapon or perk asset porting.
- Cycle 2+ balancing hinges on tuning the Points Floor multiplier and Prep Phase duration rather than reconciling missing map assets.

## Classic and Enhanced Zombie Gauntlet

Classic Zombie Gauntlet carries points and active stock perks across Stages as described in [ADR-0004](0004-perk-carryover-across-stages.md). Enhanced Zombie Gauntlet (`gauntlet_enabled=1` and `bz_enabled=1`) also carries Base Zombies progression through [the persistence bridge](../../mod/maps/_bz_gauntlet_bridge.gsc). The bridge stores permanent-per-Run gear in `gauntlet_bz_perm`, alive-only Base Zombies perks in `gauntlet_bz_perks`, and alive-only Elemental Weapons and their Pack-a-Punch tiers in `gauntlet_bz_weapons`.
