---
status: accepted
---

# Scripted Combat Companions Over Imported Ally AI Spawners

In Track A (Phase 3), hireable Companions are implemented as scripted combat units (`script_model` + `SetContents(0)` collision bypass + smooth follow pathing + `MagicBullet` weapon firing) rather than importing campaign `actor_ally_*` AI spawners into `mod.ff`.

## Considered Options

- **Import campaign `actor_ally_*` spawners and animtrees**: Stock Nazi Zombies `.ff` archives contain zero friendly AI spawners (only melee zombie actors). Pulling campaign soldier animtrees, weapons, and FX into `mod.ff` risks exceeding WaW's 400-FX pool cap on Der Riese (329/400 FX baseline).
- **Clone stock zombie spawners with `team = "allies"`**: Stock zombie actors only carry melee zombie animscripts and cannot fire player-purchased guns.
- **Scripted `script_model` Combat Companions**: Zero FX/animtree budget bloat, guaranteed `SetContents(0)` walk-through and shoot-through behavior, deterministic owner-following, permanent weapon upgrades, automatic round respawn, and 100% owner point attribution across all four Stock Maps.

## Consequences

- Companions work identically across all four Stock Maps without risking Der Riese's 400-FX ceiling.
- Follow movement, target acquisition, damageability, and round respawn are governed by pure, testable GSC logic rather than unpredictable campaign AI nodes.
