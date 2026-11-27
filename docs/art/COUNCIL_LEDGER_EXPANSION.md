# Council Review Ledger — North Star Expansion Pack (Sheets 9–11)

## Council Score History (3 Blind Multi-Model Rounds + V3.1 Final Errata Lock)

| Round | Target | Seat F (`claude-fable-5-2`) | Seat O (`claude-opus-5-5`) | Seat A (`gpt-6.2-astra`) | Seat S (`gpt-6.2-sol`) | Seat G (`grok-4.7`, non-blocking) |
|---|---|---|---|---|---|---|
| **Round 1** | Expansion V1 Sheets (`8d8039a7…`) | `4/10` (`CHANGES`) | `5/10` (`CHANGES`) | `4/10` (`CHANGES`) | `4/10` (`CHANGES`) | `non-blocking` |
| **Round 2** | Expansion V2 Sheets (`b067787b…`) | `6/10` (`CHANGES`) | `6/10` (`CHANGES`) | `4/10` (`CHANGES`) | `4/10` (`CHANGES`) | `non-blocking` |
| **Round 3** | Expansion V3 Sheets (`93899d5e…`) | **`7/10`** | **`7/10`** | **`7/10`** | **`7/10`** | `non-blocking` (cancelled) |
| **V3.1 Final Lock** | Post-R3 Errata Resolution | All R3 findings resolved below | All R3 findings resolved below | All R3 findings resolved below | All R3 findings resolved below | — |

---

## Round 1 -> V2 Disposition (Verified Resolved in R2)
- PaP prices (`+5,000` / `10,000` cumulative), zero violet bleed on Stage 2 (`#ffb020 -> #ffc448 -> #ffdc82`), `bz_sapper_on_wall_buy()` hook, `BRANDSATZ` stencil, `9` Sheet-9 XMODELs + `1` Companion XMODEL + `21` HUD materials count, Shield/Square/Circle/Diamond monochrome shape separation at `36px`, baked Tier-2 gold bezels, `#ffb020` `4.94:1` flat fog contrast, and Companion `SetModel -> Attach -> SetContents(0) + NotSolid()` call order confirmed across seats.

## Round 2 -> V3 Disposition (Verified Resolved in R3 — All 4 Seats Jumped to 7/10)
- Scoped 2-tier custom PaP finishes strictly to the **4 PaP-eligible primaries** (`+8` weapon files / `+16` XMODELs; `bz_war_club` & `bz_portal_grenade` excluded per ADR-0006 & `_bz_pap.gsc:74-88`, optional `+1` `bz_war_club_pap`, `+11..12` total weapons incl. Sheet 9).
- Matched Sheet 9 1P silhouettes to exact V2 smooth-cylinder M24 *Geballte Ladung* and clipped-point 3-window coil Bowie; replaced Sapper patched cobble mock with one continuous gun-free Der Riese courtyard floor; reconciled Blast Mine dimensions (`5.2u body / 6.6u flange × 13.8u H`, verified `~24 px/u` on Hero).
- Mounted exact V2 unobstructed amber Companion pack on 3P Marine (zero blue V1 remnant, zero sky speckles) + verified multi-distance `4.94 / 3.22 / 2.36:1` fog-blend contrast chips.
- Upgraded Sheet 11 to full uncropped 16:9 720p layout composite + brushed-steel `#ffdc82` PaP II diamond + bottom-right Tier-2 pip leaving Stamin-Up's wing clear.

## Round 3 -> V3.1 Final Lock Disposition (Every Remaining R3 Blocker, Should & Nit Resolved)
1. **Complete Canonical `bz_strip_pap_suffix()` & Gauntlet Carryover Round-Trip (`A1/S13` blocker, `F53/O-should`) — RESOLVED:** Extended Spec §1 and Sheet 10 to mandate `bz_strip_pap_suffix()` on **every** custom base-ID compare across all 10 verified sites (`_bz_gauntlet_bridge.gsc:141-158, 514-517, 858` save base+tier & restore matching `_pap1`/`_pap2` variant, `_bz_stations.gsc:1162-1185, 2159`, `_bz_rules.gsc:284-296, 336, 361-373`, `_bz_classes.gsc:1004-1010`, `_bz_perks.gsc:116-157`, `_bz_elem_stock.gsc:397-417`, `_bz_elem_new.gsc`, `_bz_special_weapons.gsc:1606`, `_bz_state.gsc:82, 212`, `_bz_pap.gsc:389-396`) while keeping the live suffixed weapon name for `GiveWeapon`/`TakeWeapon`/clip/refill calls.
2. **Sheet 9 Weapon-Free 1P Plates & Unclipped Honest Sapper Caption (`O-blocker`, `F51/F52/A3/S2`) — RESOLVED:** Replaced the `multi_crossbow_fpv.jpg` donor patches in both 1P Cluster and 1P Bowie with 100% weapon-free continuous Der Riese courtyard plates (zero leftover crossbow scope/receiver, zero paste seams!). Moved Sapper traps closer to the sidewalk apron, raised the unclipped caption box, and dropped the literal `18u` claim from the approximate mock banner.
3. **Sheet 11 Dynamic `STATUS` Lane, Valid Gauntlet State, Crisp 36px `"II"`, Perk Slot Contract & Honest Tally (`F50` blocker, `F54/F55/F57/F58/A6/A7/S5/S11/O-nits`) — RESOLVED:** Retained all 6 live dynamic readouts (`GREN: clip+reserve`, `2X DMG`, `BURST`, `2ND CH[RDY/USED]`, `QRx<n>`, `INVULN`) in ONE compact **`STATUS`** lane at `bz_get_hud_lane_y(50)` and anchored the Double-PaP `II` diamond cleanly at `bz_get_hud_lane_y(68)` (`y=68` Base / `y=86` Gauntlet — zero collision!). Updated the 16:9 720p layout composite to valid Gauntlet state (`GAUNTLET 4/4`, `KNIFE+ | BOWIE+ | CLUSTER`, `PORTAL: 4`, `GREN: 2+4 | 2ND CH[RDY]`, `<- PAP II BADGE` — removing mutually exclusive `PAP I` and the awkward Speed Cola stand-in!). Widened Tier-2 `"II"` bar spacing so both vertical strokes remain distinct at 1:1 `36px`, padded the `36px` strip header against clipping, documented the shared `player.perk_hud` slot contract (`x = size * 30`, max 11 = `324u`, in-place `SetShader()` swap), and reconciled the exact element budget (`19` mod persistent incl. both prompts; `~24–26` combined incl. stock & transients `< 31` cap).
4. **Sheet 10 Companion Scale/500u Target & Stage 1 Speck (`A4/S8/F56/F59/S10/O-should`) — RESOLVED:** Erased Stage 1's `1×5px` backdrop speck (`(1157, 294–298)`), reconciled Hero whip height (`~24u` incl. `~10u` whip), labeled the 3P view honestly as a provisional visual reference composite (dropping "true 12×14u scale"), and marked `~500u` as a Phase 3 distance-scaled acceptance target.
