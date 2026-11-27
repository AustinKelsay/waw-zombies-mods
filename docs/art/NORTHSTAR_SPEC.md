# WaW Gauntlet / Base Zombies — North Star Concept Art Specification (v2.1 — Council-Locked Final)

## 1. Mission, Governing Rule, Asset Count & Core Art Pillar

This document is the **Council-Locked North Star Art Direction & Modeler Handoff Spec (v2.1, refined across 3 Council rounds)** covering all **10 designs (6 weapons + 4 stations) = 19 XMODELs** (6 viewmodels + 6 worldmodels + 3 projectiles/deployed forms + 4 rigid station kiosks) for **Call of Duty: World at War — WaW Gauntlet / Base Zombies**.

> **Governing Precedence Rule (Post-Council R3 Lock):** Where any illustrative 1P or 3P paintover differs in micro-placement or display scale from the Hero panel or written WaW-unit dimensions (e.g., Acid 1P upper-cap dial vs tank dome dial, Boomerang 1P enlarged showcase display vs `≤4.5u` donor scale, Portal 3P oversized orb display vs `25u` tip-to-tip spec), the **Hero design and the explicit WaW-unit dimensions in this spec govern** the Blender/XMODEL rebuild.

### Core Art Pillar: **1945 Group 935 Field-Retrofitted Dieselpunk (Engine-Honest WaW 1.7)**
- **Unified Period Structural Palette (F21/F35/O5/O6)**:
  - **Panzergrau / Dunkelgrau Steel**: `#363c42`
  - **Parkerized / Blued Steel**: `#2a2e33`
  - **Olivgruen / Feldgrau Enamel**: `#424b3a`
  - **Rotbraun Primer**: `#5c3528`
  - **Chipped Wintertarnung Whitewash**: `#9da4a8` (albedo ≤ 185, matte field-applied lime wash streaks over ≥ 65% dark steel; target 15–25% weathered coverage)
  - **Oiled Straight-Grain Walnut**: `#583520` | **Charred Ash**: `#563824` | **Stitched Leather**: `#4a2e1e`
  - **Weathered Brass (strictly ≤ 10% surface area)**: `#9b7b3c` (fasteners, valve collars, gauge bezels, scope turrets only)
- **Engine-True WaW 1.7 Rendering Rules (F3/O17/O18/O19/A11/S9)**:
  - **Opaque replacement shaders only (`model phong` + `model unlit`)**: Zero transparent glass, refraction, fluid simulation, or floor reflections. All reagent/cryo/serum vessels are **armored steel jackets with recessed opaque unlit sight-slits (≤ 30% of vessel/head surface)** with painted highlights and static frost/meniscus.
  - **Local `r_glow` vs Zero Dynamic Light Spill**: WaW's native post-process `r_glow` adds a tight soft halo immediately around bright unlit pixels, but **`model unlit` casts ZERO dynamic light onto hands, sleeves, rollers, workbenches, walls, or floors**. The sole dynamic weapon light in the set is the Acid Sprayer's active flame/gas stream (`FLAMETABLEFILE`).
  - **Emissive Budget (F23)**: Maximum **1 `model unlit` material slot** per asset, **≤ 3 emissive groups** (repeated identical elements such as 3 identical bolt nocks or 3 identical boomerang tip pellets = 1 group), **≤ 30% of vessel/head surface area**.
  - **Material Slot Budget (O19)**: Maximum **4 material slots** per asset (≤ 3 lit `model phong` sheets: Metals / Painted-Enamel / Wood-Leather + 1 `model unlit` slot), targeting **512²** textures (`1024²` optional for viewmodels).

### Unified Emissive Palette & PaP Tier Swatches (F22/O16/O20/O47/S15)
All handheld weapon base hues are separated across the color wheel (nearest pair: War Club `#ff4a12` at 14.3° vs Crossbow `#ffb020` at 38.8° = `24.5°` apart; Boomerang `#e81e50` at 345.1° is `29.2°` from War Club and `144°` from Cryo). All Pack-a-Punch tier glows stay strictly within **±8° hue** of their own base color (varying luminance/saturation only). Station Kiosks are static map furniture synced directly to shipped GDT accents:

| Asset | Base Accent Hex | Hue | GDT Status | Proposed PaP T1 | Proposed Double PaP |
|---|---|---|---|---|---|
| Acid Sprayer | `#68f030` | ~102.5° | V2 Target (brightened for SNN fog) | `#72f53d` (`+0.2°`) | `#98ff6e` (`+0.1°`) |
| Cryo Cannon | `#10a5f6` | ~201.2° | GDT-Synced | `#38c4ff` (`-3.2°`) | `#8ae2ff` (`-6.1°`) |
| Multi-Crossbow & Bolt | `#ffb020` | ~38.8° | V2 Target (`24.5°` from War Club) | `#ffc448` (`+1.6°`) | `#ffdc82` (`+4.1°`) |
| Blade Boomerang | `#e81e50` | ~345.1° | V2 Target (`29.2°` from War Club) | `#f24270` (`-0.8°`) | `#ff7a9e` (`-1.4°`) |
| Portal Grenade & Orb | `#8e22da` | ~275.2° | GDT-Synced | *(Excluded from PaP — ActionSlot 2)* | — |
| War Club | `#ff4a12` | ~14.3° | V2 Target (`24.5°` from Crossbow) | `#ff3008` (`-4.6°`) | *(Melee Slot)* |
| Specialty Perk Station | `#12a856` | ~147.2° | GDT-Synced (static map furniture) | — | — |
| Class Station | `#186ce2` | ~215.0° | GDT-Synced (static map furniture) | — | — |
| Arsenal & Squad | `#de7616` | ~28.8° | GDT-Synced (static map furniture) | — | — |
| Pack-a-Punch Press | `#8e22da` | ~275.2° | GDT-Synced (static map furniture) | — | — |

## 2. Engine Constraints, Donor Rigs & Perspective Grounding (F1/F2/O1/O2/A1/A2/S1/S2)

- **1P Perspective Grounding & Reticle Core Clearance**:
  - Grounded 1P panels (`Acid`, `Cryo Idle`, `Cryo ADS`, `Crossbow`, `Boomerang`, `Portal`) are painted over real captured Der Riese gameplay frames (`showcase_media/custom_models_r5/screenshots/14_acid_idle.png`, `01_cryo_idle.png`, `02_cryo_ads.png`, `05_crossbow_idle.png`, `10_boomerang_idle.png`).
  - **Reticle Core Verification (`r = 28px` at 1280×720)**: Because WaW's donor `tag_flash` anchors already sit at `43px` (Acid) and `57px` (Cryo) from `(640,360)`, the verifiable clear zone is the **28px-radius hip-reticle core** (matching the 4-tick crosshair span & Acid ring reticle). Every grounded 1P panel keeps all 4 crosshair ticks and the center `(640,360)` aiming point completely unobstructed; the dashed ring drawn on sheets is explicitly labeled as a **compositor verification overlay**.
  - **War Club 1P** is explicitly tagged **`PROVISIONAL: colt45_melee2 sweep`** (no static idle frame exists for the ~0.45s melee swap).
- **3P Perspective Grounding (PROVISIONAL CLOSE-UP + Unified Playable Soldier)**:
  - Live `cg_thirdPerson 1` co-op captures are not yet on disk; every 3P panel is therefore tagged **`PROVISIONAL 3P CLOSE-UP (2-3m)`** (framed close enough to verify silhouette, flank hardware, and zero glow-spill, while noting shipped `weaponClass`: `gas` for Acid, `tesla_gun` for Cryo, `rifle` for Crossbow/Boomerang/Portal/Club — Colt-derived items must be verified or changed to `pistol` after auditing `_laststand.gsc`).
  - All 6 3P panels feature **one consistent playable WaW soldier body** (US Marine / Dempsey-style olive fatigues + M1 steel helmet) in dim foggy Der Riese lighting without volumetric spotlights.
- **Unified Mesh Budgets — Tris & Welded Export Verts (O18/A11/A14/F25/S18)**:
  - **Viewmodels** (open hidden rear/underside faces allowed): target **1,400–2,400 tris** (`≤ 3,500` welded verts; hard WaW 1.7 ceiling 4,000 verts).
  - **Worldmodels** (closed shell, dedicated simplified mesh): target **700–1,400 tris** (**`≤ 1,800` welded verts** across all 6 weapons; LOD1 ~50%).
  - **Projectiles / Deployed Forms**: Bolt `≤ 250` tris / `400` verts; Boomerang Air `≤ 500` tris / `750` verts; Portal Orb Air `≤ 700` tris / `900` verts.
  - **Station Kiosks**: rigid `tag_origin`, **`+X` front face**, **4u below-floor burial skirt (`z=-4..0`)**, **max height `≤ 72u`**, zero forward overhang `> 3u` below `z=72`, target **600–1,200 tris** (`≤ 1,500` welded verts).

## 3. Asset-by-Asset North Star Redesigns (v2.1 Final)

### 3.1 Acid Sprayer (`viewmodel_bz_acid_sprayer` / `world_bz_acid_sprayer`)
- **Rig & Bounds**: `m2_flamethrower_zombie` (`j_gun`, `tag_flash` at `17.71, 0, -0.29`). Total length **`23.3u`** (`x=-5.6..17.71`). Hip-fire only.
- **Silhouette & Era**: **German Flammenwerfer-41 chemical wand** in 2 dominant masses: (1) a **low, squat armored outboard-left reagent tank** (`y=+2.45`, top strictly **`Z ≤ 2.0`**, separated below the upper wand tube by a riveted bracket seam) with ONE recessed bright lime-green (`#68f030`) sight slit, **brass-bezel analog pressure dial mounted on the reagent tank's rear dome** *(Hero/3P placement governs over the 1P rear-cap dial; wand butt-cap stays plain steel)*, and weathered **Gruenkreuz** + `AETZEND` stencil; (2) a **compact plain rolled cast-iron flared diffuser bell** (`OD ~2.4–2.9u` centered on `tag_flash`, keeping the 28px hip-reticle core clear; no crenellations, no igniter ring).
- **Hero Orientation**: True **rear-left 3/4** (muzzle pointing frame-left, left flank facing viewer). *(Note: 3P illustration exaggerates wand length/bell slightly for framing; Hero & `23.3u` / `~2.4–2.9u` bell OD govern Blender build.)*
- **Geometry vs Normal/Texture (F31)**: Modeled wand tube, low tank, mounting brackets, compact bell & pistol grip; normal-mapped/painted rivets, welds, dial face, and Gruenkreuz/AETZEND stencils.

### 3.2 Cryo Cannon (`viewmodel_bz_cryo_cannon` / `world_bz_cryo_cannon`)
- **Rig & Bones**: `tesla_gun` (12 bones): `j_gun` (receiver, barrel, bridged grip, circular iron ring sight at `(3.8, 0, 5.10)`, dorsal channel `Z ≤ 3.35`), `j_bulb_1/2/3` (3 steel-jacketed upright Dewar flasks on left flank `y=+2.95`, 1.75u pitch, ≤1.6u diameter, **flask bottoms flush with or above receiver underside** for `04_cryo_reload.png` hand clearance), `j_switch` + `j_switch_cover` (hinged steel latch), `j_bolt` + `j_charging_hinge`, `tag_fx_1` (`2.05, 0, 2.74` **centerline rear-face brass pressure dial** directly beneath the iron ring — ADS placement governs), `tag_flash` (`41.0, 0, 2.16`).
- **Silhouette & Era**: **Group 935 "Kaeltewaffe"** — ≥65% dark Panzergrau/parkerized steel with weathered **chipped Wintertarnung whitewash** (~15–25% streaky worn wash). Solid bridged grip, open circular iron ring sight keeping the **center aiming point clear** (bell OD capped at **`≤ 4.8u`** so the flared Dewar frost-ring bell stays cleanly beneath the ADS aim point), **4–5 stepped barrel cooling fins**, left-flank 3 steel-caged flasks, and a bold **right-flank dark-steel condenser housing + cold indicator slit** (`~11u × 3.2u` cylindrical canister along `x=10..21, y=-2.8`, showcased in 3P).
- **Geometry vs Normal/Texture (F31)**: Modeled 4–5 primary stepped cooling fins, 3 caged flasks, iron ring sight, latch & right condenser; normal-mapped knurling, rivets, and whitewash chip edges.

### 3.3 Multi-Crossbow & Bolt (`viewmodel_bz_multi_crossbow` / `world_bz_multi_crossbow` + `bz_crossbow_bolt`)
- **Rig & Bones**: `fg42_scoped` (10 bones): `j_gun` (walnut stock, stamped blued receiver, tri-channel rail, stacked leaf-spring prods `> ±10u`), `j_clip` (`0.76, 0.98, 2.56` left-side removable **3-bolt cassette — 3 visible bolts representing the 6-shot `clipSize`**), `j_bolt` (`7.66, -1.96, 1.90` **right-side steel cocking sled**, ~4.5u travel slot + knurled charging knob on right receiver flank), `tag_scope` (compact matte-black ZFG42 optic), `tag_flash` (`26.67, -0.12, 2.76`).
- **Silhouette & Era**: Straight-grain oiled dark walnut stock *(trigger guard loop is static decorative styling — no lever action)*, blued-steel receiver, **3–4 stepped truck leaf-spring steel prods with 2 bolted U-bolt clamps and plain hooked forged tips** (zero pulley cams; canted slightly downward in Blender build so prods & stirrup stay strictly below the 28px reticle core), open steel foot stirrup, compact black ZFG42 scope (brass turrets only).
- **Bolt (`bz_crossbow_bolt`)**: Length **`~11u`** (shown as an **enlarged detail** on the Hero sheet); identical in cassette & projectile — dark stepped barbed steel head, **opaque unlit sodium-amber (`#ffb020`) explosive collar**, dark stamped vanes, and **opaque unlit amber tail witness nock**.
- **Geometry vs Normal/Texture (F31)**: Modeled 3–4 leaf springs, U-bolts, ZFG42 scope, open 3-bolt cassette, right sled & stirrup; normal-mapped walnut grain, stamped receiver ribs, and bolt serrations. Welded WM cap strictly `≤ 1,800` verts.

### 3.4 Blade Boomerang & Airborne Rotor (`viewmodel_bz_blade_boomerang` / `world_bz_blade_boomerang` + `bz_boomerang_blade_air`)
- **Rig & Scale**: `zombie_colt` (`viewmodel_ray_gun_idle`, `viewmodel_germangrenade_throw`, `weaponClass="rifle"` — provisional 3P). **1P hub-to-tip radius strictly `≤ 4.5u` (shipped `3.52u`, ~115px screen radius matching `10_boomerang_idle.png` — 1P sheet illustration is enlarged for detail readability; donor `3.52–4.5u` scale governs Blender build!)**, World held **`8.62u`**, Airborne `bz_boomerang_blade_air` **`10.15u`** (`1.18×` world-held, YZ blade plane, `+X` roll axis; Hero pair shown **not to scale**). Clean 2-model swap.
- **Silhouette & Continuity**: **Improvised WWII aircraft/torpedo propeller tri-blade** — 3 airfoil-tapered brushed steel blades with 3 circular lightening holes bolted to a bronze/gunmetal gyro-hub. **Held form** adds a compact stitched-leather stirrup grip on the **wrapped-blade side of the knuckle gap** *(Hero grip orientation governs)*. **EXACTLY ONE asymmetric leather-wrapped + painted yellow-band identification spine blade** preserved at the same clock position across Held & Airborne.
- **Emissive**: Opaque unlit **industrial crimson (`#e81e50`)** hub ring + **1 small round tracer pellet per blade tip** (3 total).
- **Geometry vs Normal/Texture (F31)**: Modeled airfoil blades, hub, grip & pellets; blind-recessed/normal-mapped lightening holes on WM & Airborne (`≤ 1,150` / `750` verts).

### 3.5 Portal Grenade & Deployed Anchor (`viewmodel_bz_portal_grenade` / `world_bz_portal_grenade` + `bz_portal_orb_air`)
- **Rig & Scale**: `zombie_colt` ActionSlot 2 `[4]` (`viewmodel_ray_gun_idle`, `viewmodel_germangrenade_throw`; excluded from PaP). Held 1P core radius **`1.38u`** (outer hoop radius ~`2.12u`), World held core radius **`2.28u`**, Deployed `bz_portal_orb_air` **`25u` total tip-to-tip height (±12.5u spires) hovering at `Z=44u`** (rigid single-piece `RotateYaw`; **Hero pair is not to scale**, and **3P deployed orb is illustrated oversized for silhouette clarity — `25u` tip-to-tip governs Blender build!**).
- **Silhouette & Continuity**: Short knurled dark-iron Stielhandgranate stick handle + riveted brass collar + **visible 4-prong steel/brass chalice** cradling a **faceted raw dark-violet Element-115 crystal shard** (`#8e22da` unlit veins) encircled by **1 thick rectangular-section blued-steel/brass meridian hoop + 1 equatorial clamp ring** *(full 360° equatorial ring preferred on deployed orb so it never reads flat edge-on during `RotateYaw`)*. **Held form (`1P / Hero / 3P`) has ZERO top pole spire**; twin tapered pole emitter spires appear strictly on deployed `bz_portal_orb_air`.
- **Geometry vs Normal/Texture (F31)**: Modeled stick handle, 4-prong chalice, 24-seg beveled meridian hoop, equatorial ring & faceted shard; normal-mapped knurling, rivets & crystal facets.

### 3.6 War Club (`viewmodel_bz_war_club` / `world_bz_war_club`)
- **Rig & Timing**: `zombie_colt` Melee Slot temporary swap (`colt45_melee1` raise, `colt45_melee2` strike, ~0.45s swap; world scale `1.85×`).
- **Silhouette & Ergonomics**: Straight charred ash shaft, stitched leather grip protected by a **forged blackened-steel WWI trench-knife D-guard knuckle bow**, and a **compact domed iron pommel** (no spike). Heavy **flared octagonal cast-iron head** carrying **1 bolted upper collar studded with 8 thick pyramidal iron lugs (1 per octagon face) + 1 stout crown lug**. Four recessed vertical windows on alternating octagonal faces (framed by dark-lipped perforated steel end-plates) expose opaque unlit deep forge red-orange (`#ff4a12`) copper kinetic solenoid coils (`≤ 30%` head surface).
- **Geometry vs Normal/Texture (F31)**: Modeled octagonal head, 8 collar lugs + crown lug, D-guard, domed pommel, window frames; recessed solenoid coil modeled as a textured 10-sided inner cylinder behind the window cutouts.
- **1P & 3P (Both Explicitly Provisional)**: One-handed grip strictly **inside the steel D-guard knuckle bow**.

### 3.7 Station Kiosks — 4 Distinct Silhouettes, Footprints & GEO VS NORMAL (`F16–F20, F31, O22–O24, A9–A10, S10–S13`)
All 4 kiosks use a **shared heavy bolted Panzergrau cast-iron plinth family with a `z=-4..0` buried floor skirt**, share **`+X` front orientation**, respect **`≤ 72u` max height** and **`≤ 3u` forward overhang** below `z=72`, and verify dark-room readability via flat-hex Dark Glyph masks and Common-Scale Elevation (`72u` soldier ref):
1. **Specialty Perk Station (`bz_station_perks_kiosk`, Emerald `#12a856`, `26u W × 22u D × 70u H`)**: Tall narrow rounded-arch Group 935 Serum & Ampoule Dispensary — 3 recessed armored emerald sight-chambers, brass dispensing tap, catch basin. **GEO VS NORMAL**: Modeled arch body, plinth, 3 recessed slit frames, tap & basin; normal-mapped panel seams, rivets & brass knurling (`≤ 1,100` tris / `1,450` verts).
2. **Class Station (`bz_station_class_kiosk`, Cobalt `#186ce2`, `32u W × 26u D × 58u H`)**: Waist-high Group 935 Field Command Switchboard Lectern — sloped backlit frosted map-glass plate under riveted steel bezel (zero LCD/joystick), open rear steel fork yoke holding stamped `"935"` chevron shield crest, stamped `"935"` badge on plinth (zero eagle). **GEO VS NORMAL**: Modeled plinth, console desk, fork yoke & crest; normal-mapped/low-poly cylinder rotary dials, toggle switches & rivets (`≤ 1,000` tris / `1,350` verts).
3. **Arsenal & Squad (`bz_station_arsenal_kiosk`, Amber `#de7616`, `54u W × 28u D × 62u H`)**: Wide low armored Field Armorer's Workbench — bolted tool chest, **forged front-left bench vise**, recessed opaque unlit amber backlit wall silhouetting dark racked rifles (zero amber spill on benchtop), flush hood (`≤ 3u` overhang). **GEO VS NORMAL**: Modeled chest carcass, bench slab, chunky front-left vise & flush hood; **racked rifle silhouettes modeled as ultra-low-poly flat/extruded silhouette cards (~30 tris each)**; pegboard grid, hood louvers, drawer seams & pulls are **normal-mapped/baked texture** (`≤ 1,100` tris / `1,450` verts).
4. **Pack-a-Punch Press (`bz_station_pap_kiosk`, Violet `#8e22da`, `42u W × 30u D × 68u H`)**: Squat heavy armored Group 935 Prototype Processing Press (**spawns on Nacht, Verrueckt & Shi No Numa** — Der Riese uses native PaP). Broad riveted iron shoulders, horizontal weapon-intake bay with grooved steel rollers and opaque recessed violet plasma slit (zero violet fog spill on rollers), asymmetric right exhaust flue + caged violet sight tube, stamped **`"935"`** header plate (zero pyramid hat, zero `"X"`). **GEO VS NORMAL**: Modeled press body, shoulders, intake bay, smooth 12-sided roller cylinders, right flue & tube cage; **roller grooves, bolts & rivets are normal-mapped/painted** (`≤ 1,150` tris / `1,500` verts). Includes a labeled **`STAGING MOCK (VERRUECKT CORRIDOR)`** inset.
