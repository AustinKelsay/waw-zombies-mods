---
status: amended by ADR-0006
---

# Carry over active perks across Stages alongside points

Amends [ADR-0002](0002-points-only-cross-map-carryover.md): between Stages in a Zombie Gauntlet Run, each alive player carries over both their points balance (with the round-scaled Points Floor) **and** their currently active perks, while weapons, Pack-a-Punch upgrades, and map doors continue to reset to each stock map's fresh sandbox. Perks still reset on down/death (`player_downed`, `death`, `fake_death`) just like stock Nazi Zombies, and clear completely on team wipe or fresh Run (`clear_run_state()`).

## Considered Options

- **Keep points-only carryover (original ADR-0002)**: Forces players to re-buy Juggernog, Speed Cola, Double Tap, and Quick Revive on every map transition, leaving Cycle 2+ Nacht der Untoten (which has no perk machines) permanently without perks and diminishing the payoff of surviving a Stage without going down.
- **Full weapon + Pack-a-Punch + perk carryover**: Still infeasible within WaW 1.7's stock asset budgets — porting cross-map weapon pools, Pack-a-Punch machines, and FX into one fastfile risks hitting WaW's hardcoded 400-FX and weapon limits and dilutes each map's identity.
- **Points + active perk carryover (chosen)**: Reuses WaW's four engine-native perks (`specialty_armorvest`, `specialty_fastreload`, `specialty_rof`, `specialty_quickrevive`) and their four stock HUD icon materials (`specialty_juggernaut_zombies`, `specialty_fastreload_zombies`, `specialty_doubletap_zombies`, `specialty_quickrevive_zombies`) with zero custom FX, weapon, or model assets.

## Consequences

- **Safe on all 4 stock maps (including Cycle 2+ Nacht der Untoten)**: Speed Cola (`specialty_fastreload`) and Double Tap (`specialty_rof`) are engine-native, Quick Revive (`specialty_quickrevive`) is read directly in stock `_laststand.gsc`, and Juggernog (`specialty_armorvest`) applies stock `zombie_perk_juggernaut_health` (`160` fallback when `_zombiemode_perks` is absent on `nazi_zombie_prototype`). Precaching the four stock HUD materials in `mod.csv` and `on_pre_zombiemode_init()` ensures perk icons render cleanly even on Nacht der Untoten with zero FX budget impact.
- **Seamless coexistence with stock perk machines**: Restored perks populate `player.perk_hud[perk]` with the exact stock bottom-left layout (`x = count * 30`, `y = -70`, `24x24` shader) and call `player SetPerk(perk)`, so stock vending machines on Verrückt, Shi No Numa, and Der Riese automatically hide duplicate purchase prompts and stack any newly purchased perks beside carried ones without overlap.
- **Authentic risk-reward survival loop**: Staying alive without going down preserves perks into the next Stage (including Nacht der Untoten on Cycle 2+); going down or bleeding out strips carried perks via per-perk watchers (`player_downed` / `death` / `fake_death`), and dead or spectating players at Stage Clear snapshot an empty perk set (`[]`) so lost perks never resurrect on the next map.
- **Compact host-dvar persistence**: Active perks persist across map transitions in the `gauntlet_player_perks` dvar (`"key1=j,f,r,q;key2=j"`) keyed by GUID with name fallback, mirroring `gauntlet_player_points` and cleared alongside it on team wipe or fresh Run.
