# WaW Gauntlet / Base Zombies — North Star Expansion Spec (v3.1 — Council-Locked Final)

## 1. Mission, Exact Asset Roster & Engine-Honest Scope

This companion spec extends [NORTHSTAR_SPEC.md](NORTHSTAR_SPEC.md) (19 core Weapon & Station XMODELs) to cover all remaining visual features across `waw_gauntlet` / Base Zombies under the **1945 Group 935 Field-Retrofitted Dieselpunk (Engine-Honest WaW 1.7)** pillar (`model phong` + opaque `model unlit`, zero dynamic light spill, zero added FX slots — keeping Der Riese's `329/400` stock FX baseline intact, with exact per-map linked FX and weapon-pool headroom verified during implementation).

### Exact Expansion Inventory (Reconciled Roster)
- **Sheet 9 — Arsenal Upgrades & Sapper Traps (`9` New 3D XMODELs, `+3` Weapon Files, `0` new FX):**
  1. `viewmodel_bz_pap_cluster` (`≤1,100` tris / `1,650` verts, `512²`), `world_bz_pap_cluster` (`≤650` tris / `950` verts, `256²`, LOD1 ~50%), `bz_pap_cluster_sub` (`≤220` tris / `340` verts, shared `256²` sheet) -> `+1` cloned zero-FX offhand weapon (`bz_pap_cluster_grenade`)
  2. `viewmodel_bz_pap_knife` (`≤550` tris / `850` verts, `512²`) + `world_bz_pap_knife` (`≤320` tris / `500` verts, `256²`) -> `+1` ADR-0006 temporary `~0.45s` melee-swap weapon (`bz_pap_knife`)
  3. `viewmodel_bz_pap_bowie` (`≤750` tris / `1,100` verts, `512²`) + `world_bz_pap_bowie` (`≤400` tris / `620` verts, `256²`) -> `+1` ADR-0006 temporary `~0.45s` melee-swap weapon (`bz_pap_bowie`)
  4. `bz_sapper_trap_fire` (`≤450` tris / `650` verts, `256²`, 2 slots) + `bz_sapper_trap_betty` (`≤400` tris / `600` verts, `256²`, 2 slots) -> `0` weapon files (`script_model` props)
- **Sheet 10 — Custom PaP Finish Variants (`4` Eligible Primaries) & Phase 3 Companion Rig:**
  - **Custom PaP Tier 1 / Double PaP Variants (`+8` Weapon Files / `+16` XMODELs; `+1` Optional War Club PaP):**
    - Per `_bz_pap.gsc:74-88` and ADR-0006, **`bz_war_club` and `bz_portal_grenade` are EXCLUDED from 2-tier Pack-a-Punch**. Exactly **4 custom primary weapons** (`bz_acid_sprayer`, `bz_cryo_cannon`, `bz_multi_crossbow`, `bz_blade_boomerang`) receive compiled zero-FX `_pap1` / `_pap2` weapon + VM/WM XMODEL pairs (**`+8` weapon files / `+16` XMODELs**). War Club's standalone single-bool Arsenal upgrade (`pap_war_club` in `_bz_state.gsc:300`) uses at most **1 optional `+1` weapon file (`bz_war_club_pap`, `+2` XMODELs)**.
    - **Combined Weapon-Asset Delta:** `+3` (Sheet 9) + `+8` (4 primaries × 2 tiers) [+ `1` optional War Club PaP] = **`+11` to `+12` weapon definitions total** (per-map stock weapon pool headroom and `329/400` Der Riese FX baseline are **pending linked 4-map smoke verification** on implementation).
    - **Canonical Base-ID Normalization Contract (ALL Call Sites):** Because swapping to `bz_<w>_pap1`/`_pap2` changes `GetCurrentWeapon()`, **every** base-weapon ID comparison across the mod MUST route through one canonical helper **`bz_strip_pap_suffix(weap)`** (stripping `_pap1` / `_pap2`), while keeping the live owned variant name for `GiveWeapon` / `TakeWeapon` / clip / ammo-refill operations. Verified call sites:
      1. `_bz_gauntlet_bridge.gsc:141-158, 514-517, 858` — **Gauntlet Carryover Round-Trip**: encode base ID + PaP tier on stage save, restore the matching `_pap1`/`_pap2` weapon variant on stage load (mandatory 4-primary × 2-tier transition round-trip test!).
      2. `_bz_stations.gsc:1162-1185, 2159` — Arsenal display names & already-owned purchase check (prevents re-buying an already-owned PaP custom primary).
      3. `_bz_rules.gsc:284-296, 336, 361-373` — `bz_is_infinite_single_item_weapon()` & custom weapon category checks (keeps `bz_blade_boomerang_pap1/2` compliant with ADR-0006 §3).
      4. `_bz_classes.gsc:1004-1010` — Medic primary ammo-regen exclusion for Boomerang variants.
      5. `_bz_perks.gsc:116-157` — Heavy-weapon move-speed scales (`0.75` Acid / `0.82` Cryo / `0.90` Crossbow).
      6. `_bz_elem_stock.gsc:397-417` — Acid burn exclusion.
      7. `_bz_elem_new.gsc` — Acid/Cryo signature firing dispatch & clip queries.
      8. `_bz_special_weapons.gsc:1606` — Crossbow spread & Boomerang catch/refill routed to the live held variant.
      9. `_bz_state.gsc:82, 212` — `bz_state_norm()` (`:82`) so `bz_state_is_weapon_double_pap()` (`:212`) stays keyed by base ID.
      10. `_bz_pap.gsc` — Mule Kick slot order & ammo preservation on swap (Tier 1 `5,000` fallback at `:389-396`; Double PaP `5,000` at `_bz_rules.gsc:242-249`).
    - **Stock firearms** keep their stock / native Der Riese `_upgraded` finish and display the Double-PaP `II` HUD badge.
  - **Phase 3 Squad Companion Rig (`bz_companion_rig`, Forward-Looking Phase 3 — `bz_companions_enabled=0` in v0.9.0):** `1` rigid XMODEL (`≤650` tris / `900` verts, 2 material slots: `512²` phong + unlit, brass `≤10%`, `12u W × 6u D × 14u H` body / `~24u H` incl. centered `~10u` whip antenna), flush spine plate authored in `j_spine4` local axes (zero loose straps; omit Marine `char_usa_raider_gear2/3`). Exact call order: **`SetModel()` -> `Attach("bz_companion_rig", "j_spine4")` -> `SetContents(0)` + `NotSolid()`**. Phase 3 acceptance gates: per-body fit-test (Ultimis + Marines), static/idle stance verification, shoot-through + walk-through verification, and distance-scaled fog capture verifying `~500u` IFF legibility.
- **Sheet 11 — 1945 Stamped-Enamel 2D HUD Icons (`21` Linked `mod.ff` Materials w/ `64×64` DXT5 `.iwi` Textures in `.iwd`, `0` FX):**
  - `6` Class Shields: `bz_icon_class_{medic,titan,sapper,daredevil,assassin,broker}` (**Pointed Dark-Steel Heraldic Shield**)
  - `3` New Standard Perks: `bz_icon_perk_{staminup,mulekick,armorpiercing}` (**Beveled Steel Square**)
  - `7` Baked Tier-2 (`II`) Gold-Bezel Perks: `bz_icon_perk_{jugg,speed,dtap,revive,staminup,mulekick,armorpiercing}_t2` (bright-gold outer bezel + dark inner separator ring + crisp high-gap bottom-right `"II"` pip — swapped in-place via `SetShader()` on existing `player.perk_hud` slot = **0 extra HUD elements!**)
  - `4` Apex Perks: `bz_icon_apex_{dblammo,lightheavy,secondchance,blastshield}` (**Stamped Circular Antique-Bronze Medallion**)
  - `1` Double-PaP `II` Badge: `bz_icon_pap2_badge` (**Obsidian/Brushed-Steel Diamond w/ `#ffdc82` Pale-Gold `"II"`** — synced to Sheet 10 Stage 2, eliminating Assassin/Portal violet overlap!)

## 2. Asset-by-Asset V3.1 Engineering & Visual Contracts

### 2.1 PaP Cluster Grenade (`bz_pap_cluster_grenade` + `bz_pap_cluster_sub`)
- **Authentic 1945 *Geballte Ladung*:** Smooth cylindrical Panzergrau German M24 head ringed by **4 smooth cylindrical stamped-steel submunition canisters** bound with bolted harness & copper wire (**ZERO US Mk2 pineapple waffle grooves in Hero OR 1P!**), oiled walnut stick handle, opaque unlit `#ffc448` PaP arming bands. Overall `14.5u L × 5.6u dia`; detached submunition `2.0u dia × 4.5u H`.
- **Engine Path:** Cloned zero-FX offhand weapon `bz_pap_cluster_grenade` swapped on purchase (updating `bz_pap_is_frag_grenade()` & Sapper reserve logic in `_bz_classes.gsc:161-176`); on primary blast, spawn 4 non-solid `bz_pap_cluster_sub` `script_model`s arcing outward `±72u` (`0.35s`), deleting each on detonation. 1P view tagged **`PROVISIONAL: stielhandgranate cook/throw`** composited on a completely weapon-free Der Riese courtyard plate.

### 2.2 PaP Combat Knife & PaP Bowie Knife (`bz_pap_knife` / `bz_pap_bowie`)
- **Engine Path:** ADR-0006 per-player temporary `~0.45s` melee weapon-swap (`bz_pap_knife` / `bz_pap_bowie`, `+2` weapon files + closed world shells for co-op).
- **Visual Consistency:** PaP Combat Knife embeds its opaque unlit `#ff6a1a` heating filament inside a **recessed fuller channel on both blade faces** (cold matte steel cutting edge). PaP Bowie Knife shows the **exact clipped-point 3-window coil Bowie** across BOTH Hero and 1P (flat alpha/cutout steel shroud over a textured inner `#ff4a12` copper coil cylinder; zero lightsaber edges; weapon-free 1P plate).

### 2.3 Sapper Wall-Buy Deployable Traps (`bz_sapper_trap_fire` & `bz_sapper_trap_betty`)
- **Real Engine Hook, Outward Direction & Slope Alignment:** Inside **`bz_sapper_on_wall_buy(player, wall_id, origin)`** (`_bz_classes.gsc:1758`):
  1. Derive outward wall push-off direction from the flattened player-from-wall vector `dir = VectorNormalize((player.origin[0] - origin[0], player.origin[1] - origin[1], 0))` (or wall-buy target model angles when passed), pushing **`18u`** cleanly out from the wall face.
  2. Run `trace = BulletTrace(push_pos, push_pos - (0, 0, 128), false, undefined)`; if `trace["fraction"] >= 1.0`, fall back to tracing directly below `player.origin` **before** committing the 10s wall cooldown (`_bz_classes.gsc:1798`).
  3. Spawn non-solid `script_model` (`SetContents(0)` + `NotSolid()`), **aligning trap pitch/roll to `trace["normal"]`** so the flat `z=-1..0` circular base sits flush on uneven cobbles/slopes, delete on expiry/detonation/reset, and **replace** the old generic green `zapper_light_ready`/`powerup_on` marker FX.
- **Reconciled Proportions:**
  - **Fire Trap (`bz_sapper_trap_fire`):** Wide squat **`11u dia × 6u H`** bolted Panzergrau/Rotbraun drum, 1945 **`BRANDSATZ`** stencil, bright top-facing `#ff7818` concentric ring & cross-slit.
  - **Blast Mine (`bz_sapper_trap_betty`):** Tall slender **`5.2u body dia (6.6u flange) × 13.8u overall H`** (`10.3u` body + `3.5u` steel prongs) Olivgruen S-Mine 35, bright top-facing `#e81e50` crimson cap & shoulder rings.

### 2.4 Pack-a-Punch 3-Stage Material Language (4 Eligible Custom Primaries)
- Applies strictly to the **4 PaP-eligible custom primaries** (`+5,000 pts` Tier 1 fallback at `_bz_pap.gsc:389-396`; `+5,000 pts` Double PaP at `_bz_rules.gsc:242-249` = `10,000 pts` cumulative), preserving each weapon's signature era finish and its own base-hue ramp (`±8°`, ZERO violet bleed!):
  - **Stage 1 (`_pap1`):** Darkened blued steel + restrained geometric oxidized brass etching (`≤15%` PaP exception) + bold player-visible **brass dorsal collar/hub bezel** + T1 accent hex.
  - **Stage 2 (`_pap2`):** Obsidian-gunmetal steel + neutral **brushed-steel geometric crystalline relief inlays** + crisp **`"II"` proof stamp** + peak-luminance Double-PaP hex.
  - **Per-Weapon 1P Visibility Anchors:** Multi-Crossbow = dorsal receiver collar + rear end-cap `"II"`; Acid Sprayer = rear wand collar + top tank strap `"II"` (preserves Olivgruen tank & `Gruenkreuz`); Cryo Cannon = rear receiver top band + dorsal channel rim `"II"` (preserves Wintertarnung streaks); Blade Boomerang = machined hub bezel + center hub `"II"` cap.

### 2.5 Phase 3 Squad Companion Field-Relay Pack (`bz_companion_rig`, Forward-Looking Phase 3)
- **Workshop Amber IFF (`#ffb020` primary):** Flat contrast `4.94:1` against `#404A54` blue-grey fog (`3.22:1` at 30% fog blend, `2.36:1` at 50% blend). **`~500u` in-map legibility is a Phase 3 acceptance target** to be verified with a distance-scaled in-engine capture once companions are enabled. Unobstructed rear twin-chevron panel (`≤20%` rear area, zero crossing bars) + left/right side-flank amber bars + raised **360° amber top antenna-collar ring** around the centered steel whip antenna.
- **Rigid `j_spine4` Fit:** `12u W × 6u D × 14u H` body (`~24u H` incl. `~10u` whip antenna), flush spine plate (zero loose straps), omit Marine `char_usa_raider_gear2/3`, `2` material slots (`512²` phong + unlit, brass `≤10%`). Sheet 10 3P panel is a provisional visual reference composite; exact body proportions are verified on Ultimis + Marine models during Phase 3 fit-testing.

### 2.6 1945 Stamped-Enamel 2D HUD Layout, Dynamic `STATUS` Lane, Perk Slot Contract & Element Tally
- **Shape Hierarchy (Verified Monochrome at `24u = 36px @ 720p`):** **Pointed Steel Shield** (Class) | **Beveled Steel Square** (Std Perk) | **Dark-Separated Gold-Bezel Square w/ High-Gap Bottom-Right `"II"` Pip** (Baked Tier-2 — leaves upper icon motif 100% uncovered!) | **Pure Circular Bronze Medallion** (Apex Perk) | **Obsidian/Brushed-Steel `#ffdc82` `"II"` Diamond** (Double PaP). *(Note for 64×64 final pixel-art authoring: Double Ammo straightens mags to WWII MP40/Thompson stick mags and Lightweight Heavy swaps wing for crane/chevron lift bar so zero Apex motifs repeat Stamin-Up's wing.)*
- **Bottom-Left Shared Perk-Slot Contract:** All custom Standard & Apex perk icons share the stock **`player.perk_hud`** slot array (`x = perk_hud.size * 30`, matching `_gauntlet_perks.gsc:452-465`, `24×24u` at `y=-70` above stock round chalk). Peak 11-icon row spans `324u` virtual width (`10 × 30u + 24u`). Tier-2 upgrades perform an **in-place `SetShader()` swap** on the existing slot (`0` extra HUD elements).
- **Top-Right Lane Retirement + Consolidated Dynamic `STATUS` Lane (via `bz_get_hud_lane_y()` — adds `+18` in Gauntlet below fixed `y=12` badge at `_gauntlet_hud.gsc:124`):**
  - Static class/perk name lists from `CLASS` (`y=14`) & `PERKS`/`PERKS+` (`y=32/84`) retire once icons are active, **WITHOUT dropping any live dynamic gameplay readouts**:
  - `y = bz_get_hud_lane_y(14)` (`14u` Base / `32u` Gauntlet): **`UPGRADES`** (`PAP I` *or* `KNIFE+ | BOWIE+ | CLUSTER` — `_bz_pap.gsc:1118-1127` keeps `PAP I` and Double-PaP `II` mutually exclusive!)
  - `y = bz_get_hud_lane_y(32)` (`32u` Base / `50u` Gauntlet): **`SPECIAL`** (`PORTAL: 4` / `(CD Ns)` matching `_bz_special_weapons.gsc:2266`)
  - `y = bz_get_hud_lane_y(50)` (`50u` Base / `68u` Gauntlet): **Consolidated `STATUS` Lane** carrying all 6 dynamic non-icon readouts when active (`GREN: clip+reserve` `_bz_classes.gsc:321`, `2X DMG` `:325`, `BURST` `:329`, `2ND CH[RDY/USED]` `_bz_perks.gsc:1855-1859`, `QRx<n>` `:1870`, `INVULN` `:1874`).
  - `y = bz_get_hud_lane_y(68)` (`68u` Base / `86u` Gauntlet): **Double-PaP `II` Brushed-Steel Diamond** (`28×28u` at `x=-12`, `0` collision in Base or Gauntlet!), toggled by **`bz_state_is_weapon_double_pap(player, weap)`** (`_bz_state.gsc:212`).
- **Honest Per-Client HUD Element Budget (`<31` WaW Cap):**
  - **Mod Persistent Peak = `19` elements:** `11` shared `player.perk_hud` slots (`0` Tier-2 overlays) + `1` Class Shield + `1` Double-PaP `II` Diamond + `3` top-right text lanes (`UPGRADES`, `SPECIAL`, `STATUS`) + `1` Gauntlet persistent badge (`_gauntlet_hud.gsc:118`) + `2` always-allocated hidden/toggled prompts (`bz_station_prompt_hud` `_bz_stations.gsc:754`, `bz_pap_prompt_hud` `_bz_pap.gsc:1413`).
  - **Combined Peak incl. Stock & Transients = `~24–26` elements** (adding stock `chalk_hud1/2`, active power-up icons, and transient Gauntlet prep/banners `_gauntlet_mode.gsc:468-469`) — stays safely under WaW's `31` per-client cap; verify exact simultaneous peak in a 4-player Gauntlet smoke test.
