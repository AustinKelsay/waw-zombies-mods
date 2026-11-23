# WaW 1.7 Engine & Stock-Asset Research Report (Base Zombies Phases 2 & 3)

Strictly read-only fact-finding on `plebdev-ultra` against stock WaW 1.7 fastfiles (`/home/plebdev/Games/waw-zombies-dev/game/zone/english/*.ff`), raw mod-tool sources (`/home/plebdev/Games/waw-zombies-dev/game/raw/`), zone CSVs, and `CoDWaW.exe`.

---

## 1. Wunderwaffe DG-2 (`_zombiemode_tesla.gsc`) — Exact Juggernog Bug & Stun Mechanics

### Exact Location & Root Cause of the Famous Juggernog HP Bug
- **File:** [`_zombiemode_tesla.gsc:485-532`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode_tesla.gsc:485-532) (byte-for-byte identical in `nazi_zombie_factory_patch.ff` and `nazi_zombie_factory.ff`, differing only in CRLF line endings; `nazi_zombie_sumpf_patch.ff` has the pre-PaP version at lines 486–533 without `"tesla_gun_upgraded"`).
- **Exact offending lines (`tesla_pvp_thread()`, lines 510–526):**
  ```gsc
  if ( self == attacker )
  {
      damage = int( self.maxhealth * .25 );
      if ( damage < 25 )
      {
          damage = 25;
      }

      if ( self.health - damage < 1 )
      {
          self.health = 1;           // <-- L520: CLOBBERS self.maxhealth!
      }
      else
      {
          self.health -= damage;     // <-- L524: CLOBBERS self.maxhealth!
      }
  }
  ```
- **Why this overwrites Juggernog `maxhealth`:**
  In WaW 1.7's C++ engine (the player `.health` script field setter), assigning directly to `player.health` in GSC resets `player.maxhealth` back down (to `100` / default). Treyarch themselves had to work around this exact engine quirk everywhere else by bracketing player `.health` writes with `sav = self.maxhealth; ... self.maxhealth = sav;`:
  - Confirmed in `nazi_zombie_factory_patch.ff` `maps/_gameskill.gsc:1361-1366` (explicitly added in Der Riese's patch over `sumpf_patch`!):
    ```gsc
    if ( GetDvar( "zombiemode" ) == "1" )
    {
        sav = self.maxHealth;
        self.health = int( newHealth * self.maxHealth );
        self.maxHealth = sav;
    }
    ```
  - Confirmed in [`_collectibles_game.gsc:98-100`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_collectibles_game.gsc:98-100), [`L109-116`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_collectibles_game.gsc:109-116), and [`L502-504`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_collectibles_game.gsc:502-504).
  - In `tesla_pvp_thread()`, Treyarch wrote `self.health = 1;` and `self.health -= damage;` **without saving/restoring `self.maxhealth`**. Worse, if `self.health` drops to `1`, `playerHealthRegen()` in `maps/_gameskill.gsc:1367-1371` calls `self setnormalhealth( 2 / self.maxHealth );` on the next frame against the already-clobbered `maxhealth`.

### Interaction with `level.overridePlayerDamage` & `_bz_hooks::bz_recompute_player_max_health`
- **Two separate damage paths fire on close-range self-shock on Der Riese:**
  1. **Engine splash damage -> `level.overridePlayerDamage`**: `tesla_gun` (`explosionRadius = 110`, `explosionInnerDamage = 1`, `explosionOuterDamage = 1`) and `tesla_gun_upgraded` (`explosionRadius = 150`) emit `MOD_PROJECTILE_SPLASH`. In `nazi_zombie_factory_patch.ff` `maps/_zombiemode.gsc:2604-2612`, `player_damage_override` clamps `finalDamage = 75` whenever `self.health > 75` and calls `finishPlayerDamageWrapper`. This path **does** go through [`_bz_hooks.gsc:598-677`](/home/plebdev/Work/waw-zombies-mods/mod/maps/_bz_hooks.gsc:598-677) (`bz_player_damage_override`), so Blast Shield can zero it.
  2. **Engine notify `"weapon_pvp_attack"` -> `tesla_pvp_thread()`** (`_zombiemode_tesla.gsc:493`): **Completely bypasses `level.overridePlayerDamage`!** Even if `bz_player_damage_override` returns `0`, `tesla_pvp_thread()` still runs, subtracts `25%` of `maxhealth`, clobbers `self.maxhealth` (breaking Juggernog I `160`, Juggernog II `220`, and Titan+Jugg II `440`), and applies `setelectrified(1.0)` + `shellshock("electrocution", 1.0)`.

### Wunderwaffe Constants, Mechanics & Map Precache Coverage
- **Chain / Damage Constants ([`_zombiemode_tesla.gsc:32-40`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode_tesla.gsc:32-40), [`L118-142`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode_tesla.gsc:118-142), [`L217-310`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode_tesla.gsc:217-310)):**
  - `tesla_max_arcs = 5` (stop condition `arc_num >= 5` at L120 -> 4 jump hops from primary target)
  - `tesla_max_enemies_killed = 20` (checked at L127)
  - `tesla_radius_start = 300`, `tesla_radius_decay = 20` per hop (L34–35, L93–94)
  - `tesla_arc_travel_time = 0.5`s, arc stagger delay `RandomFloat( 0.2, 0.6 ) * arc_num` (L37, L223)
  - `tesla_head_gib_chance = 50`, `tesla_kills_for_powerup = 15`, `tesla_min_fx_distance = 128`, `tesla_network_death_choke = 4`
  - Damage: `self DoDamage( self.health + 666, origin, player )` (lethal to all normal zombies & hellhounds; `level.boss_tesla_damage = 1000` for `boss_zombie`, L290–301); awards `"death"` points at L302.
  - Self-shock (`_zombiemode_tesla.gsc:512-530`): `max(25, int(self.maxhealth * 0.25))` damage (clamped to `>= 1` HP), `self setelectrified( 1.0 )`, `self shellshock( "electrocution", 1.0 )` (defined in [`raw/shock/electrocution.shock`](/home/plebdev/Games/waw-zombies-dev/game/raw/shock/electrocution.shock)), `self playsound( "tesla_bounce" )`.
  - Weapon file stats ([`raw/weapons/sp/tesla_gun`](/home/plebdev/Games/waw-zombies-dev/game/raw/weapons/sp/tesla_gun), [`tesla_gun_upgraded`](/home/plebdev/Games/waw-zombies-dev/game/raw/weapons/sp/tesla_gun_upgraded)): clip/reserve `3/15` (`6/30` upgraded), `explosionRadius = 110` (`150` upgraded).
- **Map Precache Coverage (verified in compiled `.ff` binaries):**
  - `nazi_zombie_factory` (Der Riese): **`tesla_gun` + `tesla_gun_upgraded`** ([`nazi_zombie_factory.csv:163-164`](/home/plebdev/Games/waw-zombies-dev/game/zone_source/nazi_zombie_factory.csv:163-164), [`nazi_zombie_factory.gsc:530-531`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/nazi_zombie_factory.gsc:530-531)).
  - `nazi_zombie_sumpf` (Shi No Numa): **`tesla_gun` only** ([`nazi_zombie_sumpf.gsc:175`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/nazi_zombie_sumpf.gsc:175)).
  - `nazi_zombie_prototype` (Nacht) & `nazi_zombie_asylum` (Verrückt): **Neither** (`tesla_gun_exists()` returns `false`).

### Recommended Fix Seam for Phase 2
- Build-stage-patch `maps/_zombiemode_tesla.gsc` (for Sumpf & Der Riese, guarded by `maps\_bz_hooks::bz_enabled()` / `bz_elements_enabled()`, matching `build_mod.py`'s existing stock-script staging pattern):
  1. In `tesla_pvp_thread()` around lines 510–526, save/restore `maxhealth` AND call `maps\_bz_hooks::bz_recompute_player_max_health( self )` immediately after modifying `self.health` (or skip self-damage/shock entirely when `bz_elements_enabled()` applies the Wunderwaffe fix/upgrade).
  2. In `bz_player_damage_override` (`player_damage` hook), also guard against `sWeapon == "tesla_gun" || sWeapon == "tesla_gun_upgraded"` self-splash when the player has the fixed/enhanced Wunderwaffe or Blast Shield.

---

## 2. Stock FX & Stock Model Inventory Across All 4 Maps (0 New FX Slots)

### Verified Stock Fastfile FX Footprints
Scanning compiled `.ff` binaries directly:
- `nazi_zombie_prototype.ff`: 164 FX paths
- `nazi_zombie_asylum.ff`: 196 FX paths
- `nazi_zombie_sumpf.ff`: 213 FX paths
- `nazi_zombie_factory.ff`: 237 FX paths (+ `common.ff` / impactfx / map FX = **329/400** runtime FX baseline)
- **89 FX paths are loaded in ALL FOUR stock map `.ff`s** (guaranteed safe cross-map with **0** `mod.csv` FX entries).

### Best Already-Loaded Stock FX & Models per Phase 2 Item (0 New FX Slots)

All FX below were verified in both compiled `.ff` fastfiles and their raw `.efx` files for color and looping behavior. Where a `level._effect[...]` key is already populated by stock map scripts, you do not even need a duplicate `LoadFX()` call.

| Phase 2 Feature | Best Der Riese Already-Loaded FX (`level._effect` key if stock-populated) | Cross-Map Fallback (All 4 Maps, 0 New FX) | Visual Behavior (`.efx` verified) |
|---|---|---|---|
| **Acid Sprayer** | `maps/zombie/fx_zombie_light_glow_green` (`zapper_light_ready`)<br>`misc/fx_exp_raygun_impact`<br>`misc/fx_trail_raygun_geotrail`<br>`misc/fx_zombie_powerup_on` (`powerup_on`)<br>`env/smoke/fx_fog_zombie_amb` | `misc/fx_exp_raygun_impact` (all 4)<br>`misc/fx_trail_raygun_geotrail` (all 4)<br>`misc/fx_zombie_powerup_on` (all 4)<br>`env/smoke/fx_fog_zombie_amb` (all 4) | Bright neon-green glow (`RGB 0, 0.8, 0` looping) + green plasma impact/trail + pale-green looping aura (`RGB 0.7, 1.0, 0.7`) + low ground mist for acid puddles. |
| **Cryo Cannon** | `maps/zombie/fx_zombie_mainframe_steam` (`zombie_mainframe_steam`)<br>`maps/zombie/fx_zombie_body_wtr_burst` / `_billowing`<br>`maps/zombie/fx_zombie_tesla_shock_secondary` (`tesla_shock_secondary`)<br>`env/smoke/fx_grenade_smoke_w` | `bio/player/fx_footstep_water` (all 4)<br>`env/electrical/fx_elec_short_oneshot` (all 4)<br>`env/electrical/fx_elec_wire_spark_burst` (all 4)<br>`bio/player/fx_footstep_snow` (Nacht/Verrückt) | White icy steam jet (`RGB 1, 1, 1` looping) + blue-white water/ice crystal burst + electric-blue frost crackle on frozen zombies. |
| **War Club** | `maps/mp_maps/fx_mp_zombie_hand_dirt_burst` (`rise_burst`)<br>`maps/mp_maps/fx_mp_zombie_body_dirt_billowing` (`rise_billow`)<br>`env/dirt/fx_dust_ceiling_impact_lg_mdbrown` (`large_ceiling_dust`)<br>`misc/fx_zombie_bloodsplat` | `env/dirt/fx_dust_ceiling_impact_lg_mdbrown` (all 4)<br>`misc/fx_zombie_bloodsplat` (all 4)<br>`bio/player/fx_footstep_sand` (all 4) | Heavy rock/dirt shockwave burst + billowing dust cloud + blood impact burst (pair with `Earthquake()`). |
| **Multi-Crossbow** | `weapon/grenade/fx_trail_rifle_grenade` (bolt trail)<br>`weapon/rocket/fx_trail_panzerfaust_geotrail` (heavy trail)<br>`weapon/bouncing_betty/fx_explosion_betty_generic` (`betty_explode`)<br>`weapon/satchel/fx_explosion_satchel_generic` | `weapon/grenade/fx_trail_rifle_grenade` (all 4)<br>`weapon/rocket/fx_trail_panzerfaust_geotrail` (all 4)<br>`weapon/molotov/fx_molotov_exp` (all 4)<br>`misc/fx_zombie_mini_nuke` (all 4) | Looping smoke/rocket trail on bolt `script_model` + explosive detonation burst (`betty_explode` on Verrückt/Sumpf/Der Riese). |
| **Blade Boomerang** | **Spinning `xmodel`:** `viewmodel_knife_bowie` (Der Riese) or `weapon_usa_kbar_knife` (`common.ff`, all 4)<br>**FX:** `misc/fx_zombie_bloodsplat`, `misc/fx_zombie_bloodspurt`, `maps/zombie/fx_zombie_wire_spark` (`wire_spark`) | **Spinning `xmodel`:** `weapon_usa_kbar_knife` (`common.ff`, all 4); optional map-flavor: `zombie_surgical_bonesaw` (Verrückt/Sumpf), `static_berlin_knives_cleaver` (Verrückt)<br>**FX:** `misc/fx_zombie_bloodsplat` + `misc/fx_zombie_bloodspurt` + `env/electrical/fx_elec_wire_spark_burst` (all 4) | Spinning blade `script_model` (`RotateYaw` / `RotatePitch`) with spark glint trail and blood-splat burst on every zombie pierce. |
| **Portal Grenade** | **Native Der Riese teleporter FX ([`nazi_zombie_factory_fx.gsc:118-128`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/nazi_zombie_factory_fx.gsc:118-128)):**<br>`maps/zombie/fx_transporter_ambient` (`transporter_ambient`)<br>`maps/zombie/fx_transporter_pad_start` (`transporter_pad_start`)<br>`maps/zombie/fx_transporter_beam` (`transporter_beam`)<br>`maps/zombie/fx_transporter_start` (`transporter_start`)<br>`maps/zombie/fx_zombie_mainframe_flat` (`zombie_mainframe_flat`) | `misc/fx_zombie_powerup_wave` (all 4)<br>`misc/fx_zombie_powerup_grab` (all 4)<br>`env/electrical/fx_elec_short_oneshot` (all 4)<br>`misc/fx_zombie_electric_trap` (Verrückt/Sumpf/Der Riese) | Blue-violet glowing portal loop (`RGB 0.72, 0.73, 1.0`), electric radial burst, vertical blue beam with floating motes, and flat portal disc. Plus `player SetTransported( sec )` ([`nazi_zombie_factory_teleporter.gsc:485`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/nazi_zombie_factory_teleporter.gsc:485)) for native 1st-person warp distortion! |

---

## 3. Stock Flamethrower, Melee Slot (Bowie / War Club), & Tactical Key Primitives

### Stock Flamethrower (`m2_flamethrower_zombie` / `_upgraded`)
- **Map availability:** `m2_flamethrower_zombie` is precached in **ALL 4 stock maps** ([`nazi_zombie_prototype.gsc:284`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/nazi_zombie_prototype.gsc:284), [`nazi_zombie_asylum.gsc:656`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/nazi_zombie_asylum.gsc:656), [`nazi_zombie_sumpf.gsc:156`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/nazi_zombie_sumpf.gsc:156), [`nazi_zombie_factory.gsc:500`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/nazi_zombie_factory.gsc:500)). `m2_flamethrower_zombie_upgraded` is precached on **Der Riese only** (`nazi_zombie_factory.gsc:501`).
- **Weapon stats ([`raw/weapons/sp/m2_flamethrower_zombie`](/home/plebdev/Games/waw-zombies-dev/game/raw/weapons/sp/m2_flamethrower_zombie), [`_upgraded`](/home/plebdev/Games/waw-zombies-dev/game/raw/weapons/sp/m2_flamethrower_zombie_upgraded)):** `weaponType = gas`, `weaponClass = gas`, `inventoryType = primary`, `damage = 30` (`45` upgraded), `clipSize = 100`, `maxAmmo = 300`, `ammoName = fuel`. Limited to 1 box holder via `add_limited_weapon( "m2_flamethrower_zombie", 1 )` ([`_zombiemode_weapons.gsc:318`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode_weapons.gsc:318)).
- **Damage/MOD & Burning DOT ([`_zombiemode_spawner.gsc:2606-2642`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode_spawner.gsc:2606-2642), [`L2780-2826`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode_spawner.gsc:2780-2826)):**
  - Emits `sMeansOfDeath = "MOD_BURNED"` and `sWeapon = "m2_flamethrower_zombie"` (or `_upgraded`).
  - `zombie_flame_damage()` sets `self.moveplaybackrate = 0.8` (20% slow), launches `damage_on_fire( player )`, and spawns `animscripts\death::flame_death_fx()` if no other burning zombie is within 100 units.
  - `damage_on_fire()` waits 2s then ticks every `RandomFloatRange( 1.0, 3.0 )`s dealing `%` of `level.zombie_health` (`20–30%` R<6, `15–25%` R<9, `10–20%` R<11, `10–15%` R>=11) via `self DoDamage( dmg, self.origin, player )`.
  - Hit point award is throttled by `zombie_flame_dmg_point_delay = 500`ms ([`_zombiemode.gsc:556`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode.gsc:556)); burn kill bonus is `zombie_score_bonus_burn = 10` ([`_zombiemode_score.gsc:120-123`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode_score.gsc:120-123)).
  - **Phase 2 seam:** Our existing `actor_damage` hook in `_bz_hooks.gsc` (`bz_handle_global_actor_damage`) already intercepts `zombie_damage` / `zombie_damage_ads`, so Enhanced Flamethrower can cleanly amplify `MOD_BURNED` / `m2_flamethrower_zombie*` damage, spread fire to nearby zombies, and add ground flame pools.

### Bowie Knife (`_zombiemode_bowie.gsc` & `specialty_altmelee`) vs. War Club Slot
- **How stock Bowie Knife works:**
  - [`_zombiemode_bowie.gsc:111-127`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode_bowie.gsc:111-127): calls `self SetPerk( "specialty_altmelee" )`, sets `self.has_altmelee = true` (restored on spectator respawn in [`_zombiemode.gsc:1256-1259`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode.gsc:1256-1259)), and plays flourish via `GiveWeapon( "zombie_bowie_flourish" )` (Der Riese only).
  - Engine damage is controlled by a **global server dvar** `SetDvar( "perk_altMeleeDamage", 1000 )` set only in [`nazi_zombie_factory.gsc:39`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/nazi_zombie_factory.gsc:39) (standard knife is `meleeDamage = 150` per weapon file). `specialty_altmelee` also triggers 75% melee gib chance ([`_zombiemode_spawner.gsc:1762`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode_spawner.gsc:1762)) and swaps the knife viewmodel to `viewmodel_knife_bowie` on Der Riese.
- **How War Club cleanly shares/swaps the melee slot with Bowie Knife:**
  - Maintain explicit per-player state `player.bz_melee_slot` (`"knife"` | `"bowie"` | `"war_club"`).
  - **Important engine constraint:** Because `perk_altMeleeDamage` is global (not per-player) and `specialty_altmelee` hard-binds the Bowie Knife swipe viewmodel/VO, **do NOT set `specialty_altmelee` for War Club**.
  - When equipping **War Club**: call `player UnsetPerk( "specialty_altmelee" )`, `player.has_altmelee = false`, set `player.bz_melee_slot = "war_club"`. When switching back to **Bowie Knife**: set `player SetPerk( "specialty_altmelee" )`, `player.has_altmelee = true`, `player.bz_melee_slot = "bowie"`.
  - Distinguish War Club visually & mechanically on every `MOD_MELEE` hit (via `actor_damage` hook) and swing (`MeleeButtonPressed()` / `IsMeleeing()`):
    - Apply War Club's heavy damage bonus (`DoDamage` extra), frontal AoE cone cleave + knockback/stagger, `PlayFX` dirt shockwave (`rise_burst` / `large_ceiling_dust`), `Earthquake( 0.35, 0.3, player.origin, 128 )`, and distinct HUD indicator (`MELEE: WAR CLUB` vs `MELEE: BOWIE` vs `MELEE: PAP BOWIE`).

### Per-Player Input Builtins Verified in `CoDWaW.exe` PlayerCmd Table (134 Methods)
Direct extraction from `CoDWaW.exe`'s `.rdata` `PlayerCmd` method table (at file offset `0x43c10c` / VA `0x83c10c`):

- **CONFIRMED PRESENT in WaW 1.7:**
  - `UseButtonPressed()` (`0x4eea10`)
  - `AttackButtonPressed()` (`0x4eeab0`)
  - `AdsButtonPressed()` (`0x4eeb50`)
  - `MeleeButtonPressed()` (`0x4eebf0`)
  - `FragButtonPressed()` (`0x4eec90`)
  - `NotifyOnCommand( notifyName, cmdString )` (`0x4eede0`) — **networked per-player command notify** (see [`_zombiemode.gsc:1191`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode.gsc:1191), [`pby_fly.gsc:826`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/pby_fly.gsc:826)).
  - `SetActionSlot( slotNum, type, weaponName )` (`0x4f1810`) — confirmed in [`_zombiemode_betty.gsc:137`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode_betty.gsc:137) (`SetActionSlot(4, "weapon", "mine_bouncing_betty")`) and [`_c4.gsc:221`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_c4.gsc:221) (`SetActionSlot(2, "weapon", "c4")`).
  - `ButtonPressed( keyName )` (`0x4eeda0`) — **WARNING:** host/local polling only (used in `_createfx.gsc` / `_debug.gsc` on `players[0]`), unreliable for remote co-op clients.
  - Offhand helpers: `GetCurrentOffhand()`, `SwitchToOffhand()`, `SetOffhandSecondaryClass()`, `GetOffhandSecondaryClass()`, `IsThrowingGrenade()`, `IsMeleeing()`, `IsFiring()`, `IsSwitchingWeapons()`.
- **CONFIRMED ABSENT in WaW 1.7 (DO NOT CALL — will error):**
  - `SecondaryOffhandButtonPressed()` — **NOT in `CoDWaW.exe`**.
  - `ActionSlotOneButtonPressed()` .. `ActionSlotFourButtonPressed()` — **NOT in `CoDWaW.exe`**.
- **Recommended Portal Grenade Keybinding Seam:**
  - Stock zombies uses **Frag (`+frag`)** for `stielhandgranate`, **Secondary Offhand (`+smoke`)** for `molotov` / `zombie_cymbal_monkey` (`offhandClass = Smoke Grenade` in [`raw/weapons/sp/zombie_cymbal_monkey`](/home/plebdev/Games/waw-zombies-dev/game/raw/weapons/sp/zombie_cymbal_monkey)), **ActionSlot 3** for `altMode` (M7 rifle grenade), and **ActionSlot 4** for `mine_bouncing_betty`.
  - **ActionSlots 1 and 2 are completely unused across all 4 zombie maps!**
  - Use **`player NotifyOnCommand( "bz_portal_throw", "+actionslot 2" )`** (and/or `"+smoke"` fallback when the player does not hold Monkeys/Molotovs) — works cleanly per-player in both Solo and Co-op, never conflicts with Frags, Monkey Bombs, or Bouncing Betties, and requires zero custom offhand weapon slots. On notify, spawn a scripted thrown projectile (`script_model` arcing via `BulletTrace` physics) or launch a `MagicBullet`/fake grenade with blue teleporter trail and deploy the Portal at impact!

---

## 4. Scripted Primary Weapon Slot Architecture (Acid Sprayer, Cryo Cannon, Multi-Crossbow, Blade Boomerang)

To occupy **real primary weapon slots** that natively integrate with Mule Kick I/II (3–4 slots via `GetWeaponsListPrimaries()`), weapon switching, clip/reserve ammo HUD, Mystery Box, and Arsenal Station without compiling any custom 3D `.xmodel` files or adding any FX slots:

### Option A (Recommended): 4 Zero-FX Cloned Stock Weapon Definitions in `mod.csv`
Add 4 tiny text weapon files (`raw/weapons/sp/bz_acid_sprayer`, `bz_cryo_cannon`, `bz_multi_crossbow`, `bz_blade_boomerang`) via `weapon,sp/bz_*` in `mod.csv`, cloned from stock weapon templates with:
- **`inventoryType = primary`** -> native Mule Kick 3–4 primary slot tracking, `GiveWeapon`, `SwitchToWeapon`, `HasWeapon`, `TakeWeapon`, and reload/ammo HUD!
- **Distinct `ammoName`** (`bz_acid`, `bz_cryo`, `bz_xbow`, `bz_blade`) -> **zero ammo-pool collisions** with standard weapons!
- **Custom `displayName`** -> bottom-right HUD natively displays the true weapon name.
- **Already-loaded stock `gunModel` & `worldModel`** (all verified present in `/home/plebdev/Games/waw-zombies-dev/game/raw/xmodel/`):
  - `bz_acid_sprayer`: `viewmodel_usa_flamethrower` / `weapon_usa_flamethrower` (or `viewmodel_usa_ray_gun`)
  - `bz_cryo_cannon`: `viewmodel_usa_ray_gun` / `weapon_usa_ray_gun` (or `viewmodel_usa_tesla_gun` on Der Riese/Sumpf; `viewmodel_usa_flamethrower` is cross-map!)
  - `bz_multi_crossbow`: `viewmodel_zombie_m1garand_rifle` / `weapon_zombie_m1garand_rifle_grenade` (with iron sights + bolt fire feel)
  - `bz_blade_boomerang`: `viewmodel_usa_colt45_pistol` or `viewmodel_usa_kbar_knife` / `weapon_usa_kbar_knife`
- **0 Extra FX:** Set all weapon FX fields (`viewFlashEffect`, `worldFlashEffect`, `viewShellEjectEffect`, `worldShellEjectEffect`, `projTrailEffect`, `projExplosionEffect`) either empty `""` or strictly to paths from the **89 all-4-map FX intersection** (e.g., `misc/fx_trail_raygun_geotrail`, `weapon/grenade/fx_trail_rifle_grenade`, `misc/fx_exp_raygun_impact`).
- **Scripted firing loop:** Per-player `self waittill( "weapon_fired" )` checks `cur = self GetCurrentWeapon()` -> executes elemental projectile/cone/puddle/boomerang logic in `_bz_elements.gsc` (base weapon damage set low/0 if purely scripted, or combined with `MagicBullet`).

### Option B (Fallback — 0 New Weapon Assets in `mod.csv`): Hijack Already-Precached Unused Stock Weapons
Direct inspection of all 4 compiled map `.ff` files + `common.ff` shows which primary weapons are precached across all 4 maps and **never** included in Box or wall-buys (`include_weapon()`):

| Weapon Name | Precached in `.ff` | Used in Box / Wall-Buy? | Suitability as Carrier |
|---|---|---|---|
| `colt` | All 4 maps (`zombiemode.csv`, `_zombiemode.gsc:16`) + `common.ff` | **Never** (players spawn with `zombie_colt`; `colt` is unused except `level.laststandpistol` fallback) | Clean carrier #1 (`inv=primary`, pistol) |
| `walther` | All 4 map `.ff`s + `common.ff` | **Never** (0 maps call `include_weapon("walther")`) | Clean carrier #2 (`inv=primary`, pistol) |
| `mg42` | All 4 map `.ff`s + `common.ff` | **Never** (Nacht/Verrückt use `mg42_bipod`; Sumpf/Der Riese use `zombie_mg42`) | Clean carrier #3 (`inv=primary`, full-auto) |
| `defaultweapon` | `common.ff` only (verify `PrecacheItem("defaultweapon")` in `pre_init`) | **Never** | Carrier #4 (`inv=primary`, clip 10 / max 100), but has placeholder finger-gun model |
| `kar98k` | All 4 map `.ff`s | **Wall-buy on Nacht & Verrückt** (unused on Sumpf & Der Riese which use `zombie_kar98k`) | **Unsafe** on Nacht/Verrückt |

**Takeaway:** Because only **3** real-model primary weapons (`colt`, `walther`, `mg42`) are both precached and unused across all 4 maps (and `colt` shares `ammoName = colt` with `zombie_colt`), **Option A (4 zero-FX cloned weapon definitions in `mod.csv`) is strongly recommended** for clean HUD names, distinct ammo pools, distinct viewmodels, and zero cross-map collisions. (Verify `mod.ff` FX count stays at 329/400 during Phase 2 build verification.)

---

## 5. Phase 3 Scripted Squad Companions — Stock Character Models & `MagicBullet` Primitives

### Precached Friendly Soldier `xmodel`s Across All 4 Stock Maps (0 Custom Assets)
Verified directly inside all 4 compiled `.ff` binaries and their `mptype` / `character` definitions:

#### Der Riese (`nazi_zombie_factory.ff`) & Shi No Numa (`nazi_zombie_sumpf.ff`)
Loaded via `mptype,nazi_zombie_heroes` ([`raw/mptype/nazi_zombie_heroes.csv`](/home/plebdev/Games/waw-zombies-dev/game/raw/mptype/nazi_zombie_heroes.csv)) — **all 4 iconic Ultimis heroes are already precached!**
1. **Tank Dempsey** ([`char_zomb_player_0.gsc:5`](/home/plebdev/Games/waw-zombies-dev/game/raw/character/char_zomb_player_0.gsc:5)):
   - `SetModel( "char_usa_marine_polonsky_zomb" )` *(complete body + head single model)*
2. **Nikolai Belinski** ([`char_zomb_player_1.gsc:5`](/home/plebdev/Games/waw-zombies-dev/game/raw/character/char_zomb_player_1.gsc:5)):
   - `SetModel( "char_rus_guard_chernova_zomb" )` *(complete body + head single model)*
3. **Takeo Masaki** ([`char_zomb_player_2.gsc:5-9`](/home/plebdev/Games/waw-zombies-dev/game/raw/character/char_zomb_player_2.gsc:5-9)):
   - `SetModel( "char_jap_impinf_officer_body_zomb" )`
   - `Attach( "char_jap_impinf_officer_head", "", true )`
   - `Attach( "char_jap_impinf_officer_hat_zomb" )`
4. **Edward Richtofen** ([`char_zomb_player_3.gsc:5-9`](/home/plebdev/Games/waw-zombies-dev/game/raw/character/char_zomb_player_3.gsc:5-9)):
   - `SetModel( "char_ger_ansel_body_zomb" )`
   - `Attach( "char_ger_ansel_head_zomb", "", true )`
   - `Attach( "char_ger_waffen_officercap1_zomb" )`

#### Nacht der Untoten (`nazi_zombie_prototype.ff`) & Verrückt (`nazi_zombie_asylum.ff`)
Loaded via `include,common_player_us` -> `mptype,player_usa_marine` ([`raw/mptype/player_usa_marine.csv`](/home/plebdev/Games/waw-zombies-dev/game/raw/mptype/player_usa_marine.csv)) — **Ultimis heroes are NOT precached on these 2 maps!** Instead, all **4 US Marine player soldiers** are precached:
- **Marine 1** ([`char_usa_marine_player1.gsc`](/home/plebdev/Games/waw-zombies-dev/game/raw/character/char_usa_marine_player1.gsc)): `char_usa_marine_player_body1_1` + `Attach("char_usa_marine_head1_1", "", true)` + `Attach("char_usa_raider_helm1")` + `Attach("char_usa_raider_gear2")`
- **Marine 2** ([`char_usa_marine_player2.gsc`](/home/plebdev/Games/waw-zombies-dev/game/raw/character/char_usa_marine_player2.gsc)): `char_usa_marine_player_body2_1` + `Attach("char_usa_marine_head2_2", "", true)` + `Attach("char_usa_raider_helm2")` + `Attach("char_usa_raider_gear3")`
- **Marine 3**: `char_usa_marine_player_body1_1` + `Attach("char_usa_marine_head3_3", "", true)` + `Attach("char_usa_raider_helm2")` + `Attach("char_usa_raider_gear2")`
- **Marine 4**: `char_usa_marine_player_body2_1` + `Attach("char_usa_marine_head4_4", "", true)` + `Attach("char_usa_raider_helm1")` + `Attach("char_usa_raider_gear3")`

> **Design Note:** Using a per-map model resolver (just like [`_bz_stations.gsc:432-516`](/home/plebdev/Work/waw-zombies-mods/mod/maps/_bz_stations.gsc:432-516)) spawns recognizable Ultimis Heroes on Shi No Numa & Der Riese and US Marine Squadmates on Nacht & Verrückt with **0 custom models and 0 extra FX**.

### `MagicBullet` Signature, Point Attribution & `SetContents(0)` Verification
- **`MagicBullet( weapon_name, start_pos, target_pos, owner_player )`** (`CoDWaW.exe` VA `0x51aff0`):
  - 4-argument form with player owner is confirmed in stock [`raw/maps/pby_fly.gsc:902,908`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/pby_fly.gsc:902):
    ```gsc
    MagicBullet( "pby_20mm", right_barrel.origin + (AnglesToForward(right_barrel.origin) * 5), bullet_target, level.player );
    ```
  - Passing `owner_player` as the 4th argument sets `eAttacker = owner_player` in engine damage dispatch, which flows automatically into:
    - [`_zombiemode_spawner.gsc:2677`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode_spawner.gsc:2677) (`player maps\_zombiemode_score::player_add_points( "damage", ... )`)
    - [`_zombiemode_spawner.gsc:2592`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_zombiemode_spawner.gsc:2592) (`level zombie_death_points( ..., self.attacker, self )`)
    - Our patched `_zombiemode_score.gsc` (`bz_points_modify`, so Broker 2x points and all kill stats credit 100% to `owner_player`).
  - **Cross-map weapon name safety for `MagicBullet`:** Always pass a weapon precached on the active map (e.g., all-4-map guaranteed weapons: `"zombie_colt"`, `"kar98k"`, `"mg42"`, `"ptrs41_zombie"`, `"ray_gun"` — or map-resolved `"thompson"`/`"zombie_thompson"`, `"stg44"`/`"zombie_stg44"`, `"ppsh"`/`"zombie_ppsh"`).
- **`SetContents( 0 )` on `script_model`** (`CoDWaW.exe` VA `0x51cdd0`):
  - Confirmed in stock [`raw/maps/_drones.gsc:921`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_drones.gsc:921) and [`raw/maps/_interactive_objects.gsc:455-457`](/home/plebdev/Games/waw-zombies-dev/game/raw/maps/_interactive_objects.gsc:455-457) (`// Set the contents to 0 to make it non-solid.`).
  - Zeroing the content bitmask removes **all** solid, clip, and bullet-hit flags simultaneously, guaranteeing that **both player movement AND player/zombie bullets pass cleanly through** the Companion `script_model`. Call `companion SetContents( 0 )` *after* `SetModel()` and all `Attach()` calls, and pair with `companion NotSolid()` for defense-in-depth.

---

## Summary of Recommended Implementation Seams

1. **Phase 2 (`_bz_elements.gsc`, gated by `bz_elements_enabled()`):**
   - Build-stage-patch `maps/_zombiemode_tesla.gsc` (Sumpf + Der Riese) to eliminate the `tesla_pvp_thread()` `self.maxhealth` clobber and call `bz_recompute_player_max_health( self )`.
   - Use **4 zero-FX cloned `weapon,sp/bz_*` primary definitions** in `mod.csv` for Acid Sprayer, Cryo Cannon, Multi-Crossbow, and Blade Boomerang so Mule Kick 3–4 slots, HUD names, and ammo pools work natively at **0 additional FX**.
   - Use `player.bz_melee_slot` (`"knife"` / `"bowie"` / `"war_club"`) with `UnsetPerk("specialty_altmelee")` when equipping War Club so Bowie Knife and War Club swap cleanly without colliding on the global `perk_altMeleeDamage` dvar.
   - Bind **Portal Grenade** via `player NotifyOnCommand( "bz_portal_throw", "+actionslot 2" )` (verified networked in `CoDWaW.exe`, zero conflict with Frags / Monkeys / Betties) and reuse Der Riese's native `transporter_*` FX (with all-4-map fallbacks).
2. **Phase 3 (`_bz_companions.gsc`, gated by `bz_companions_enabled()`):**
   - Spawn `script_model` Companions using per-map precached Ultimis Hero models (Der Riese / Shi No Numa) and US Marine player models (Nacht / Verrückt), call `SetContents( 0 )` + `NotSolid()` after `SetModel`/`Attach`, and fire map-safe stock weapons via 4-arg `MagicBullet( weapon, muzzlePos, targetPos, owner )` for native 100% owner point attribution.