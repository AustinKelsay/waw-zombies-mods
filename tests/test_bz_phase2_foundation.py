"""Offline TDD contract suite for P2-T1 (#23): Zero-FX Cloned Primary Weapons,
Phase 2 Rules/State, Mystery Box Wiring, Arsenal Station Phase 2 Popup, and
Enhancements Menu Presets.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import tempfile
from typing import Any
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_ROOT = REPO_ROOT / "mod"
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tests.gsc_runtime import (  # noqa: E402
    FakeDvarStore,
    GscArray,
    GscRuntime,
    GscStruct,
    UNDEFINED,
    tokenize,
)
from tests.test_bz_hooks_and_build import (  # noqa: E402
    BZ_HOOKS_MOD,
    BzGscRuntime,
    FakeEntity,
    _ast_contains_method_call,
)

RULES_MOD = "maps\\_bz_rules"
STATE_MOD = "maps\\_bz_state"
STATIONS_MOD = "maps\\_bz_stations"

SYNTHETIC_RAY_GUN = (
    "WEAPONFILE"
    "\\displayName\\WEAPON_RAY_GUN"
    "\\inventoryType\\primary"
    "\\ammoName\\ray_gun"
    "\\clipName\\ray_gun"
    "\\damage\\1500"
    "\\minDamage\\1000"
    "\\explosionInnerDamage\\1500"
    "\\explosionOuterDamage\\300"
    "\\explosionRadius\\128"
    "\\clipSize\\20"
    "\\maxAmmo\\160"
    "\\startAmmo\\160"
    "\\dropAmmoMin\\20"
    "\\dropAmmoMax\\40"
    "\\gunModel\\viewmodel_usa_ray_gun"
    "\\worldModel\\weapon_usa_ray_gun"
    "\\viewFlashEffect\\weapon/muzzleflashes/fx_raygun_custom_disallowed"
    "\\worldFlashEffect\\weapon/muzzleflashes/fx_raygun_world_disallowed"
    "\\viewShellEjectEffect\\weapon/shellejects/fx_custom_shell"
    "\\worldShellEjectEffect\\weapon/shellejects/fx_custom_shell_w"
    "\\projTrailEffect\\misc/fx_trail_raygun_geotrail"
    "\\projExplosionEffect\\misc/fx_exp_raygun_impact"
    "\\customTracerFx\\weapon/tracers/fx_not_in_intersection"
)

SYNTHETIC_M1GARAND_GL = (
    "WEAPONFILE"
    "\\displayName\\WEAPON_M1GARAND_GL"
    "\\inventoryType\\primary"
    "\\altWeapon\\m7_launcher"
    "\\ammoName\\m1garand"
    "\\clipName\\m1garand"
    "\\damage\\180"
    "\\minDamage\\120"
    "\\explosionInnerDamage\\250"
    "\\explosionOuterDamage\\50"
    "\\explosionRadius\\96"
    "\\clipSize\\8"
    "\\maxAmmo\\80"
    "\\startAmmo\\80"
    "\\dropAmmoMin\\8"
    "\\dropAmmoMax\\24"
    "\\gunModel\\viewmodel_usa_m1garand_rifle"
    "\\worldModel\\weapon_usa_m1garand_rifle"
    "\\viewFlashEffect\\weapon/muzzleflashes/rifleflash"
    "\\worldFlashEffect\\weapon/muzzleflashes/rifleflash_world"
)

SYNTHETIC_KAR98K = (
    "WEAPONFILE"
    "\\displayName\\WEAPON_KAR98K"
    "\\inventoryType\\primary"
    "\\ammoName\\kar98k"
    "\\clipName\\kar98k"
    "\\damage\\160"
    "\\minDamage\\100"
    "\\clipSize\\5"
    "\\maxAmmo\\50"
    "\\startAmmo\\50"
    "\\dropAmmoMin\\5"
    "\\dropAmmoMax\\15"
    "\\gunModel\\viewmodel_ger_kar98k_rifle"
    "\\worldModel\\weapon_ger_kar98k_rifle"
    "\\viewFlashEffect\\weapon/muzzleflashes/rifleflash"
    "\\worldFlashEffect\\weapon/muzzleflashes/rifleflash_world"
)

SYNTHETIC_ZOMBIE_COLT = (
    "WEAPONFILE"
    "\\displayName\\WEAPON_COLT"
    "\\inventoryType\\primary"
    "\\ammoName\\colt"
    "\\clipName\\colt"
    "\\damage\\40"
    "\\minDamage\\20"
    "\\clipSize\\8"
    "\\maxAmmo\\80"
    "\\startAmmo\\32"
    "\\dropAmmoMin\\8"
    "\\dropAmmoMax\\16"
    "\\gunModel\\viewmodel_usa_colt45_pistol"
    "\\worldModel\\weapon_usa_colt45_pistol"
    "\\viewFlashEffect\\weapon/muzzleflashes/pistolflash"
    "\\worldFlashEffect\\weapon/muzzleflashes/pistolflash_world"
)


class TestZeroFxWeaponClonerAndBuildStaging(unittest.TestCase):
    """Slice 1: Deterministic zero-FX weapon file cloning, staging, and mod.csv registration."""

    def setUp(self) -> None:
        import build_mod

        self.bm = build_mod

    def test_clone_zero_fx_weapon_file_strips_disallowed_fx_and_preserves_allowed_intersection(self) -> None:
        allowed = {
            "misc/fx_trail_raygun_geotrail",
            "misc/fx_exp_raygun_impact",
        }
        cloned = self.bm.clone_zero_fx_weapon_file(
            SYNTHETIC_RAY_GUN,
            overrides={
                "inventoryType": "primary",
                "ammoName": "bz_acid",
                "clipName": "bz_acid",
                "displayName": "BZ_ACID_SPRAYER",
                "clipSize": "20",
                "maxAmmo": "120",
                "startAmmo": "120",
                "viewFlashEffect": "maps/zombie/fx_not_cross_map",
            },
            allowed_fx_set=allowed,
        )
        pairs = dict(self.bm.parse_weapon_file(cloned))

        self.assertTrue(cloned.startswith("WEAPONFILE\\"))
        self.assertEqual(pairs["inventoryType"], "primary")
        self.assertEqual(pairs["ammoName"], "bz_acid")
        self.assertEqual(pairs["clipName"], "bz_acid")
        self.assertEqual(pairs["displayName"], "BZ_ACID_SPRAYER")
        self.assertEqual(pairs["clipSize"], "20")
        self.assertEqual(pairs["maxAmmo"], "120")
        self.assertEqual(pairs["startAmmo"], "120")

        # Allowed all-4-map intersection FX preserved verbatim
        self.assertEqual(pairs["projTrailEffect"], "misc/fx_trail_raygun_geotrail")
        self.assertEqual(pairs["projExplosionEffect"], "misc/fx_exp_raygun_impact")

        # Every disallowed *Effect / *Fx field (including disallowed overrides) cleared to ""
        self.assertEqual(pairs["viewFlashEffect"], "")
        self.assertEqual(pairs["worldFlashEffect"], "")
        self.assertEqual(pairs["viewShellEjectEffect"], "")
        self.assertEqual(pairs["worldShellEjectEffect"], "")
        self.assertEqual(pairs["customTracerFx"], "")

        # Deterministic output across repeated calls
        cloned_again = self.bm.clone_zero_fx_weapon_file(
            SYNTHETIC_RAY_GUN,
            overrides={
                "inventoryType": "primary",
                "ammoName": "bz_acid",
                "clipName": "bz_acid",
                "displayName": "BZ_ACID_SPRAYER",
                "clipSize": "20",
                "maxAmmo": "120",
                "startAmmo": "120",
                "viewFlashEffect": "maps/zombie/fx_not_cross_map",
            },
            allowed_fx_set=allowed,
        )
        self.assertEqual(cloned, cloned_again)

        # Rejects malformed non-WEAPONFILE payloads
        with self.assertRaises(ValueError):
            self.bm.clone_zero_fx_weapon_file("NOT_A_WEAPONFILE\\foo\\bar", {}, allowed)

        # Explicitly strips altWeapon (e.g. m1garand_gl -> m7_launcher) so no alt-weapon assets leak into mod.ff
        cloned_gl = self.bm.clone_zero_fx_weapon_file(SYNTHETIC_M1GARAND_GL, {}, allowed)
        gl_pairs = dict(self.bm.parse_weapon_file(cloned_gl))
        self.assertEqual(gl_pairs["altWeapon"], "")

    def test_stage_bz_element_weapons_generates_all_four_distinct_zero_fx_primaries_and_mod_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_sp = root / "tools" / "raw" / "weapons" / "sp"
            raw_sp.mkdir(parents=True)
            (raw_sp / "ray_gun").write_text(SYNTHETIC_RAY_GUN, encoding="latin1")
            # Provide m1garand_gl with altWeapon=m7_launcher to prove altWeapon & splash are sanitized
            (raw_sp / "m1garand_gl").write_text(SYNTHETIC_M1GARAND_GL, encoding="latin1")
            (raw_sp / "zombie_colt").write_text(SYNTHETIC_ZOMBIE_COLT, encoding="latin1")

            stage_dir = root / "stage"
            stage_dir.mkdir(parents=True)

            staged_relpaths = self.bm.stage_bz_element_weapons(root / "tools", stage_dir)
            self.assertEqual(
                staged_relpaths,
                [
                    "weapons/sp/bz_acid_sprayer",
                    "weapons/sp/bz_cryo_cannon",
                    "weapons/sp/bz_multi_crossbow",
                    "weapons/sp/bz_blade_boomerang",
                ],
            )

            expected_specs = {
                "bz_acid_sprayer": ("bz_acid", "Acid Sprayer", "20", "120", "120"),
                "bz_cryo_cannon": ("bz_cryo", "Cryo Cannon", "16", "96", "96"),
                "bz_multi_crossbow": ("bz_xbow", "Multi-Crossbow", "6", "36", "36"),
                "bz_blade_boomerang": ("bz_blade", "Blade Boomerang", "1", "20", "20"),
            }
            seen_ammo: set[str] = set()
            allowed_norm = {fx.lower() for fx in self.bm.VERIFIED_ALL_4_MAP_FX}

            for weap_name, (ammo, disp, clip, max_ammo, start_ammo) in expected_specs.items():
                weap_path = stage_dir / "weapons" / "sp" / weap_name
                self.assertTrue(weap_path.is_file(), f"Missing staged weapon file: {weap_path}")
                pairs = dict(self.bm.parse_weapon_file(weap_path.read_text(encoding="latin1")))
                self.assertEqual(pairs["inventoryType"], "primary")
                self.assertEqual(pairs["ammoName"], ammo)
                self.assertEqual(pairs["clipName"], ammo)
                self.assertEqual(pairs["displayName"], disp)
                self.assertTrue(disp.isascii())
                self.assertEqual(pairs["altWeapon"], "")
                self.assertEqual(pairs["damage"], "1")
                self.assertEqual(pairs["minDamage"], "1")
                self.assertEqual(pairs["explosionInnerDamage"], "0")
                self.assertEqual(pairs["explosionOuterDamage"], "0")
                self.assertEqual(pairs["explosionRadius"], "0")
                self.assertEqual(pairs["clipSize"], clip)
                self.assertEqual(pairs["maxAmmo"], max_ammo)
                self.assertEqual(pairs["startAmmo"], start_ammo)
                seen_ammo.add(ammo)

                # Zero added FX: every *Effect / *Fx field must be empty or in the all-4-map intersection
                for k, v in pairs.items():
                    kl = k.lower()
                    if kl.endswith("effect") or kl.endswith("fx"):
                        val_norm = v.strip().replace("\\", "/").lower()
                        self.assertTrue(
                            val_norm == "" or val_norm in allowed_norm,
                            f"{weap_name} field {k}={v!r} is not in VERIFIED_ALL_4_MAP_FX",
                        )

            self.assertEqual(len(seen_ammo), 4)

            # generate_staged_mod_csv appends weapon,sp/bz_* entries cleanly without duplicates
            base_csv = (MOD_ROOT / "mod.csv").read_text(encoding="latin1")
            staged_csv = self.bm.generate_staged_mod_csv(
                base_csv,
                ["maps/_bz_hooks.gsc"],
                staged_weapon_relpaths=staged_relpaths,
            )
            for weap_name in expected_specs:
                self.assertNotIn(f"weapon,sp/{weap_name}", base_csv)
                self.assertEqual(staged_csv.count(f"weapon,sp/{weap_name}"), 1)

            # Idempotent if run again on already-augmented csv
            staged_csv_2 = self.bm.generate_staged_mod_csv(
                staged_csv,
                ["maps/_bz_hooks.gsc"],
                staged_weapon_relpaths=staged_relpaths,
            )
            for weap_name in expected_specs:
                self.assertEqual(staged_csv_2.count(f"weapon,sp/{weap_name}"), 1)


class TestMysteryBoxAndElementHookSeams(unittest.TestCase):
    """Slice 1b: Mystery Box registration, precaching, and weapon_fired hook seam."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzGscRuntime(MOD_ROOT, self.dvars)
        self.player = FakeEntity("HostPlayer", ent_num=0)
        self.gsc.players.append(self.player)

    def test_box_registration_and_precache_are_strict_noops_when_elements_disabled(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_elements_enabled", "0")

        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_register_box_weapons")

        self.assertEqual(self.gsc.precached_items, [])
        self.assertIs(self.gsc.level.get_field("zombie_weapons"), UNDEFINED)

    def test_box_registration_and_precache_add_all_four_primaries_when_elements_enabled(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_elements_enabled", "1")

        # Pre-seed level.zombie_include_weapons to verify box inclusion table updates cleanly too
        self.gsc.level.set_field("zombie_include_weapons", GscArray())

        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.assertEqual(
            self.gsc.precached_items,
            [
                "bz_acid_sprayer",
                "bz_cryo_cannon",
                "bz_multi_crossbow",
                "bz_blade_boomerang",
            ],
        )

        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        zw = self.gsc.level.get_field("zombie_weapons")
        inc = self.gsc.level.get_field("zombie_include_weapons")
        expected_hints = {
            "bz_acid_sprayer": "Press &&1 for Acid Sprayer",
            "bz_cryo_cannon": "Press &&1 for Cryo Cannon",
            "bz_multi_crossbow": "Press &&1 for Multi-Crossbow",
            "bz_blade_boomerang": "Press &&1 for Blade Boomerang",
        }
        for weap, expected_hint in expected_hints.items():
            entry = zw[weap]
            self.assertIsNot(entry, UNDEFINED, f"{weap} missing from level.zombie_weapons")
            self.assertTrue(entry.get_field("is_in_box"), f"{weap} must have is_in_box=true")
            self.assertEqual(entry.get_field("weapon_name"), weap)
            self.assertEqual(entry.get_field("hint"), expected_hint)
            # upgrade_name MUST stay undefined so stock Der Riese can_upgrade_weapon() never eats the weapon
            self.assertIs(entry.get_field("upgrade_name"), UNDEFINED, f"{weap} must leave upgrade_name undefined")
            self.assertTrue(inc[weap], f"{weap} missing from level.zombie_include_weapons")

        # Calling again is idempotent
        ev_count = len(self.gsc.emitted_events)
        self.gsc.call(BZ_HOOKS_MOD, "bz_register_box_weapons")
        self.assertEqual(len(self.gsc.emitted_events), ev_count)

    def test_weapon_fired_hook_dispatches_only_under_elements_gate(self) -> None:
        fired_log: list[tuple[str, str]] = []
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "weapon_fired",
            self.gsc.register_py_callback(
                "on_wf",
                lambda _s, player, weap: fired_log.append((player.get_field("name"), weap)),
            ),
            "elements",
        )

        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_elements_enabled", "0")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", self.player, "bz_acid_sprayer")
        self.assertEqual(fired_log, [])

        self.dvars.set("bz_elements_enabled", "1")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", self.player, "bz_acid_sprayer")
        self.assertEqual(fired_log, [("HostPlayer", "bz_acid_sprayer")])


class TestPhase2RulesAndStatusMath(unittest.TestCase):
    """Slice 2a: Phase 2 catalog IDs, pricing, prerequisites, and pure combat/status math."""

    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)

    def test_phase2_element_weapons_and_special_gear_catalog_prices_and_metadata(self) -> None:
        elem_ids = self.gsc.call(RULES_MOD, "bz_get_element_weapon_ids").to_list()
        self.assertEqual(
            elem_ids,
            ["acid_sprayer", "cryo_cannon", "multi_crossbow", "blade_boomerang"],
        )

        expected_elems = [
            ("acid_sprayer", "bz_acid_sprayer", 5000, "Acid Sprayer"),
            ("cryo_cannon", "bz_cryo_cannon", 5000, "Cryo Cannon"),
            ("multi_crossbow", "bz_multi_crossbow", 5000, "Multi-Crossbow"),
            ("blade_boomerang", "bz_blade_boomerang", 5000, "Blade Boomerang"),
        ]
        for item_id, weap_name, price, display_name in expected_elems:
            self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_valid_element_weapon", item_id))
            self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_valid_element_weapon", item_id.upper()))
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_element_weapon_name", item_id), weap_name)
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_element_weapon_id_from_weapon", weap_name), item_id)
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_element_weapon_price", item_id), price)
            disp = self.gsc.call(RULES_MOD, "bz_get_item_display_name", "element_weapon", item_id)
            self.assertEqual(disp, display_name)
            self.assertTrue(disp.isascii())

            info = self.gsc.call(RULES_MOD, "bz_get_item_info", "element_weapon", item_id)
            self.assertEqual(info.category, "element_weapon")
            self.assertEqual(info.id, item_id)
            self.assertEqual(info.price, price)
            self.assertEqual(info.display_name, display_name)
            self.assertEqual(info.weapon_name, weap_name)

        self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_valid_element_weapon", "ray_gun"))
        self.assertIs(self.gsc.call(RULES_MOD, "bz_get_element_weapon_price", "ray_gun"), UNDEFINED)
        self.assertIs(self.gsc.call(RULES_MOD, "bz_get_element_weapon_name", "ray_gun"), UNDEFINED)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_element_weapon_id_from_weapon", "ray_gun"), "")

        gear_ids = self.gsc.call(RULES_MOD, "bz_get_special_gear_ids").to_list()
        self.assertEqual(gear_ids, ["war_club", "pap_war_club", "portal_grenade"])

        expected_gear = [
            ("war_club", 5000, "", "War Club"),
            ("pap_war_club", 5000, "war_club", "PaP War Club"),
            ("portal_grenade", 5000, "", "Portal Grenade"),
        ]
        for gear_id, price, prereq, display_name in expected_gear:
            self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_valid_special_gear", gear_id))
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_special_gear_price", gear_id), price)
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_special_gear_prereq", gear_id), prereq)
            disp = self.gsc.call(RULES_MOD, "bz_get_item_display_name", "special_gear", gear_id)
            self.assertEqual(disp, display_name)
            self.assertTrue(disp.isascii())

            info = self.gsc.call(RULES_MOD, "bz_get_item_info", "special_gear", gear_id)
            self.assertEqual(info.category, "special_gear")
            self.assertEqual(info.id, gear_id)
            self.assertEqual(info.price, price)
            self.assertEqual(info.prereq, prereq)

        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_item_display_name", "special_gear", "equip_bowie"), "Bowie Knife")
        self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_valid_special_gear", "chainsaw"))
        self.assertIs(self.gsc.call(RULES_MOD, "bz_get_special_gear_price", "chainsaw"), UNDEFINED)

    def test_phase2_status_effect_and_combat_math_helpers(self) -> None:
        # Acid Sprayer: 6s puddle, 40% slow (0.60 move scale), +50% brittle (1.50x incoming damage)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_acid_puddle_duration"), 6.0, places=6)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_acid_slow_scale"), 0.60, places=6)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_acid_brittle_mult"), 1.50, places=6)

        # Cryo Cannon: 4s freeze + 2.50x shatter damage multiplier
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_cryo_freeze_duration"), 4.0, places=6)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_cryo_shatter_mult"), 2.50, places=6)

        # Wunderwaffe DG-2 chain stun duration
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_wunderwaffe_stun_duration"), 3.5, places=6)

        # Enhanced Flamethrower close-range melt vs long-range % HP burn DOT (base vs upgraded)
        r1_long_base = self.gsc.call(RULES_MOD, "bz_calc_flame_dot_damage", 1, 150, False, False)
        r10_long_base = self.gsc.call(RULES_MOD, "bz_calc_flame_dot_damage", 10, 1045, False, False)
        r10_close_base = self.gsc.call(RULES_MOD, "bz_calc_flame_dot_damage", 10, 1045, True, False)
        r10_long_up = self.gsc.call(RULES_MOD, "bz_calc_flame_dot_damage", 10, 1045, False, True)
        r10_close_up = self.gsc.call(RULES_MOD, "bz_calc_flame_dot_damage", 10, 1045, True, True)
        r30_long_up = self.gsc.call(RULES_MOD, "bz_calc_flame_dot_damage", 30, 7000, False, True)
        self.assertEqual(r1_long_base, 120)
        self.assertEqual(r10_long_base, 229)
        self.assertEqual(r10_close_base, 418)
        self.assertEqual(r10_long_up, 344)
        self.assertEqual(r10_close_up, 627)
        self.assertEqual(r30_long_up, 2310)
        self.assertGreater(r10_close_base, r10_long_base)
        self.assertGreater(r10_close_up, r10_close_base)
        self.assertGreater(r30_long_up, r10_long_up)

        # War Club melee damage & AOE radius (base cleave vs PaP frontal smash)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_war_club_damage", 150, 150, False), 600)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_war_club_damage", 150, 2000, False), 1000)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_war_club_damage", 150, 150, True), 1500)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_war_club_damage", 150, 4000, True), 4000)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_war_club_aoe_radius", False), 96)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_war_club_aoe_radius", True), 160)

        # Multi-Crossbow: 3-bolt spread, round-scaled sticky explosive damage, +75% Double PaP
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_crossbow_bolt_count"), 3)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_crossbow_bolt_damage", 1, 150, False), 900)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_crossbow_bolt_damage", 1, 150, True), 1575)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_crossbow_bolt_damage", 20, 3000, False), 2400)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_crossbow_bolt_damage", 20, 3000, True), 4200)

        # Blade Boomerang: max 6 pierces, round-scaled damage, +75% Double PaP
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_boomerang_max_pierce"), 6)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_boomerang_damage", 1, 150, False), 800)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_boomerang_damage", 1, 150, True), 1400)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_boomerang_damage", 20, 4000, False), 3000)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_boomerang_damage", 20, 4000, True), 5250)

        # Portal Grenade constants
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_portal_duration"), 8.0, places=6)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_portal_cooldown"), 25.0, places=6)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_portal_max_charges"), 2)


class TestPhase2PlayerStateAndTransitions(unittest.TestCase):
    """Slice 2b: Phase 2 per-player state purchases, melee-slot free swaps, down persistence, round recharge."""

    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)
        self.player = GscStruct()
        self.player.set_field("score", 40000)
        self.gsc.call(STATE_MOD, "bz_state_init_player", self.player)

    def test_init_defaults_and_element_weapon_purchases(self) -> None:
        self.assertEqual(self.player.get_field("bz_melee_slot"), "knife")
        self.assertFalse(self.player.get_field("bz_owns_war_club"))
        self.assertFalse(self.player.get_field("bz_pap_war_club"))
        self.assertFalse(self.player.get_field("bz_owns_bowie"))
        self.assertFalse(self.player.get_field("bz_owns_portal_grenade"))
        self.assertEqual(self.player.get_field("bz_portal_charges"), 0)

        # Buy Acid Sprayer (5000 test cap)
        res = self.gsc.call(STATE_MOD, "bz_try_buy_element_weapon", self.player, "acid_sprayer", False)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "ok")
        self.assertEqual(res.cost, 5000)
        self.assertEqual(res.weapon_name, "bz_acid_sprayer")
        self.assertEqual(self.player.get_field("score"), 35000)

        # Already held rejection does not deduct score
        dup = self.gsc.call(STATE_MOD, "bz_try_buy_element_weapon", self.player, "acid_sprayer", True)
        self.assertFalse(dup.ok)
        self.assertEqual(dup.status, "already_owned")
        self.assertEqual(self.player.get_field("score"), 35000)

        # Invalid weapon ID rejected cleanly
        bad = self.gsc.call(STATE_MOD, "bz_try_buy_element_weapon", self.player, "bfg9000", False)
        self.assertFalse(bad.ok)
        self.assertEqual(bad.status, "invalid_item")

        # Insufficient points rejection
        self.player.set_field("score", 4999)
        poor = self.gsc.call(STATE_MOD, "bz_try_buy_element_weapon", self.player, "blade_boomerang", False)
        self.assertFalse(poor.ok)
        self.assertEqual(poor.status, "insufficient_points")
        self.assertEqual(self.player.get_field("score"), 4999)

    def test_melee_slot_war_club_purchase_pap_prereq_and_free_bowie_swap(self) -> None:
        # PaP War Club requires War Club first
        no_club = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "pap_war_club", False)
        self.assertFalse(no_club.ok)
        self.assertEqual(no_club.status, "missing_prereq")

        # Equip Bowie fails when player does not own Bowie
        no_bowie = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "equip_bowie", False)
        self.assertFalse(no_bowie.ok)
        self.assertEqual(no_bowie.status, "missing_prereq")

        # Acquire War Club (5000 pts) -> equips war_club
        buy_wc = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "war_club", False)
        self.assertTrue(buy_wc.ok)
        self.assertEqual(buy_wc.cost, 5000)
        self.assertFalse(buy_wc.swapped)
        self.assertTrue(self.player.get_field("bz_owns_war_club"))
        self.assertEqual(self.player.get_field("bz_melee_slot"), "war_club")
        self.assertEqual(self.player.get_field("score"), 35000)

        # Clicking War Club while already equipped returns already_owned at 0 charge
        dup_wc = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "war_club", False)
        self.assertFalse(dup_wc.ok)
        self.assertEqual(dup_wc.status, "already_owned")
        self.assertEqual(self.player.get_field("score"), 35000)

        # Upgrade PaP War Club (5000 pts)
        buy_pap_wc = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "pap_war_club", False)
        self.assertTrue(buy_pap_wc.ok)
        self.assertEqual(buy_pap_wc.cost, 5000)
        self.assertTrue(self.player.get_field("bz_pap_war_club"))
        self.assertEqual(self.player.get_field("score"), 30000)

        # Player also owns Bowie Knife -> free swap to Bowie (0 pts)
        swap_bowie = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "equip_bowie", True)
        self.assertTrue(swap_bowie.ok)
        self.assertEqual(swap_bowie.cost, 0)
        self.assertTrue(swap_bowie.swapped)
        self.assertEqual(self.player.get_field("bz_melee_slot"), "bowie")
        self.assertTrue(self.player.get_field("bz_owns_bowie"))
        self.assertEqual(self.player.get_field("score"), 30000)

        # Free swap back to owned War Club (0 pts)
        swap_wc = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "war_club", True)
        self.assertTrue(swap_wc.ok)
        self.assertEqual(swap_wc.cost, 0)
        self.assertTrue(swap_wc.swapped)
        self.assertEqual(self.player.get_field("bz_melee_slot"), "war_club")
        self.assertEqual(self.player.get_field("score"), 30000)

    def test_sync_bowie_ownership_switches_war_club_to_bowie_only_on_first_wall_buy_acquisition(self) -> None:
        # Player acquires War Club FIRST without owning Bowie
        buy_wc = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "war_club", False)
        self.assertTrue(buy_wc.ok)
        self.assertEqual(self.player.get_field("bz_melee_slot"), "war_club")
        self.assertFalse(self.player.get_field("bz_owns_bowie"))

        # Newly acquiring stock Bowie Knife off the wall transitions bz_owns_bowie false -> true
        # and switches bz_melee_slot to "bowie" so Bowie + War Club never stack.
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_sync_bowie_ownership", self.player, True))
        self.assertTrue(self.player.get_field("bz_owns_bowie"))
        self.assertEqual(self.player.get_field("bz_melee_slot"), "bowie")

        # After player explicitly free-swaps back to War Club, subsequent sync calls preserve "war_club"
        swap_back = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "war_club", True)
        self.assertTrue(swap_back.ok)
        self.assertTrue(swap_back.swapped)
        self.assertEqual(self.player.get_field("bz_melee_slot"), "war_club")
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_sync_bowie_ownership", self.player, True))
        self.assertEqual(self.player.get_field("bz_melee_slot"), "war_club")

    def test_portal_grenade_purchase_consumption_round_recharge_and_down_persistence(self) -> None:
        # Buy perks + War Club + PaP War Club + Portal Grenade
        self.gsc.call(STATE_MOD, "bz_try_buy_perk", self.player, "juggernog")
        self.gsc.call(STATE_MOD, "bz_try_buy_perk", self.player, "mule_kick")
        self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "war_club", True)
        self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "pap_war_club", True)

        portal = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "portal_grenade", True)
        self.assertTrue(portal.ok)
        self.assertEqual(portal.cost, 5000)
        self.assertTrue(self.player.get_field("bz_owns_portal_grenade"))
        self.assertEqual(self.player.get_field("bz_portal_charges"), 2)

        # Consume both charges cleanly, 3rd returns False
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_try_consume_portal_charge", self.player))
        self.assertEqual(self.player.get_field("bz_portal_charges"), 1)
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_try_consume_portal_charge", self.player))
        self.assertEqual(self.player.get_field("bz_portal_charges"), 0)
        self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_try_consume_portal_charge", self.player))

        # Down clears perks but strictly preserves War Club, PaP War Club, melee slot, and Portal Grenade
        down_summary = self.gsc.call(STATE_MOD, "bz_state_on_player_downed", self.player, 3)
        self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_has_perk", self.player, "juggernog"))
        self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_has_perk", self.player, "mule_kick"))
        self.assertEqual(self.player.get_field("bz_melee_slot"), "war_club")
        self.assertTrue(self.player.get_field("bz_owns_war_club"))
        self.assertTrue(self.player.get_field("bz_pap_war_club"))
        self.assertTrue(self.player.get_field("bz_owns_portal_grenade"))
        self.assertEqual(down_summary.preserved_melee_slot, "war_club")
        self.assertTrue(down_summary.preserved_war_club)
        self.assertTrue(down_summary.preserved_pap_war_club)
        self.assertTrue(down_summary.preserved_portal_grenade)

        # Round start refills portal charges to max (2)
        round_summary = self.gsc.call(STATE_MOD, "bz_state_on_round_start", self.player)
        self.assertTrue(round_summary.portal_recharged)
        self.assertEqual(round_summary.portal_charges, 2)
        self.assertEqual(self.player.get_field("bz_portal_charges"), 2)


class TestArsenalStationPhase2AndMenus(unittest.TestCase):
    """Slice 3: Arsenal Station buy_element/buy_gear end-to-end, bz_menus.inc, & WaW 1.7 compliance."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzGscRuntime(MOD_ROOT, self.dvars)
        self.p1 = FakeEntity("PlayerOne", ent_num=0)
        self.p1.set_field("score", 80000)
        self.p1.give_weapon("thompson", make_current=True)
        self.p1.give_perk("specialty_altmelee")
        self.p1.set_field("has_altmelee", True)
        self.gsc.players.append(self.p1)

    def test_arsenal_phase2_purchases_respect_elements_gate_and_classic_mode_noop(self) -> None:
        # Classic Mode (bz_enabled=0) -> strict noop
        self.dvars.set("bz_enabled", "0")
        self.dvars.set("bz_elements_enabled", "1")
        self.assertFalse(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:acid_sprayer")
        )
        self.assertEqual(self.p1.get_field("score"), 80000)
        self.assertEqual(self.gsc.emitted_events, [])

        # bz_enabled=1 but bz_elements_enabled=0 -> gate_disabled rejection, zero score loss
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")
        self.dvars.set("bz_elements_enabled", "0")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:acid_sprayer")
        )
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_gear:war_club")
        )
        self.assertEqual(self.p1.get_field("score"), 80000)
        self.assertNotIn("bz_acid_sprayer", self.p1.weapons)
        self.assertEqual(self.p1.client_dvars.get("ui_bz_elem_acid_sprayer"), "DISABLED")
        self.assertIn(
            "BZ_EVENT|STATION_PURCHASE|player=PlayerOne;menu=bz_station_arsenal;category=element_weapon;item=acid_sprayer;status=gate_disabled;cost=0;score=80000",
            self.gsc.emitted_events,
        )
        self.assertIn(
            "BZ_EVENT|STATION_PURCHASE|player=PlayerOne;menu=bz_station_arsenal;category=special_gear;item=war_club;status=gate_disabled;cost=0;score=80000",
            self.gsc.emitted_events,
        )

    def test_arsenal_phase2_buy_element_and_buy_gear_end_to_end_with_melee_swaps_and_ui_dvars(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")
        self.dvars.set("bz_elements_enabled", "1")

        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

        dispatched: list[tuple[str, str, int, str]] = []
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "item_purchased",
            self.gsc.register_py_callback(
                "p2_purchase_cb",
                lambda _s, ctx: dispatched.append(
                    (
                        ctx.get_field("category"),
                        ctx.get_field("item_id"),
                        int(ctx.get_field("result").get_field("cost")),
                        ctx.get_field("weapon_name"),
                    )
                ),
            ),
            "elements",
        )

        # Grant Mule Kick I (3 slots) so player can hold thompson + acid_sprayer + cryo_cannon
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_perk:mule_kick")
        self.assertEqual(self.p1.get_field("score"), 76000)

        # 1. Buy Acid Sprayer (5000 test cap)
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:acid_sprayer")
        )
        self.assertEqual(self.p1.get_field("score"), 71000)
        self.assertIn("bz_acid_sprayer", self.p1.weapons)
        self.assertEqual(self.p1.current_weapon, "bz_acid_sprayer")
        self.assertEqual(self.p1.client_dvars["ui_bz_elem_acid_sprayer"], "OWNED")
        self.assertEqual(self.p1.client_dvars["ui_bz_elem_cryo_cannon"], "BUY 5000")

        # 2. Buy Cryo Cannon (5000 test cap) -> fills 3rd Mule Kick slot without dropping thompson
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:cryo_cannon")
        )
        self.assertEqual(self.p1.get_field("score"), 66000)
        self.assertIn("thompson", self.p1.weapons)
        self.assertIn("bz_acid_sprayer", self.p1.weapons)
        self.assertIn("bz_cryo_cannon", self.p1.weapons)

        # 3. Buy Multi-Crossbow (5000 test cap) -> at 3-slot cap, replaces current weapon (bz_cryo_cannon)
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:multi_crossbow")
        )
        self.assertEqual(self.p1.get_field("score"), 61000)
        self.assertIn("bz_multi_crossbow", self.p1.weapons)
        self.assertEqual(len(self.p1.weapons), 3)

        # 4. Buy Blade Boomerang (5000 test cap)
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:blade_boomerang")
        )
        self.assertEqual(self.p1.get_field("score"), 56000)
        self.assertIn("bz_blade_boomerang", self.p1.weapons)

        # 5. Buy War Club (5000) -> unsets specialty_altmelee per ADR-0003 while preserving bz_owns_bowie
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_gear:war_club")
        )
        self.assertEqual(self.p1.get_field("score"), 51000)
        self.assertFalse(self.p1.has_perk("specialty_altmelee"))
        self.assertFalse(self.p1.get_field("has_altmelee"))
        self.assertEqual(self.p1.get_field("bz_melee_slot"), "war_club")
        self.assertTrue(self.p1.get_field("bz_owns_bowie"))
        self.assertEqual(self.p1.client_dvars["ui_bz_melee_slot"], "MELEE: WAR CLUB")
        self.assertEqual(self.p1.client_dvars["ui_bz_gear_war_club"], "EQUIPPED")
        self.assertEqual(self.p1.client_dvars["ui_bz_gear_equip_bowie"], "EQUIP FREE")

        # 6. Upgrade PaP War Club (5000)
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_gear:pap_war_club")
        )
        self.assertEqual(self.p1.get_field("score"), 46000)
        self.assertEqual(self.p1.client_dvars["ui_bz_melee_slot"], "MELEE: PAP WAR CLUB")
        self.assertEqual(self.p1.client_dvars["ui_bz_gear_pap_war_club"], "OWNED")

        # PaP Bowie does not interfere while War Club is the active melee slot
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_pap:pap_bowie")
        z_dummy = FakeEntity("zombie_0", ent_num=20, is_player=False)
        z_dummy.set_field("health", 5000)
        z_dummy.set_field("maxhealth", 5000)
        wc_melee_dmg = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_dummy,
            self.p1,
            self.p1,
            150,
            0,
            "MOD_MELEE",
            "none",
            GscArray([0, 0, 0]),
            GscArray([0, 0, 0]),
            "torso_upper",
            0,
        )
        # PaP Bowie defers while War Club is equipped; PaP War Club applies its heavy smash (5000 vs 20000 HP zombie, NOT 1-hit kill)
        self.assertEqual(wc_melee_dmg, 5000)

        # 7. Free swap back to owned Bowie Knife (0 pts) -> restores specialty_altmelee & PaP Bowie 1-hit kill
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_gear:equip_bowie")
        )
        self.assertEqual(self.p1.get_field("score"), 41000)
        self.assertTrue(self.p1.has_perk("specialty_altmelee"))
        self.assertTrue(self.p1.get_field("has_altmelee"))
        self.assertEqual(self.p1.get_field("bz_melee_slot"), "bowie")
        self.assertEqual(self.p1.client_dvars["ui_bz_melee_slot"], "MELEE: PAP BOWIE")
        self.assertEqual(self.p1.client_dvars["ui_bz_gear_war_club"], "EQUIP FREE")
        self.assertIn("Free swap", self.p1.client_dvars["ui_bz_feedback"])
        bowie_melee_dmg = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_dummy,
            self.p1,
            self.p1,
            1000,
            0,
            "MOD_MELEE",
            "none",
            GscArray([0, 0, 0]),
            GscArray([0, 0, 0]),
            "torso_upper",
            0,
        )
        self.assertGreaterEqual(bowie_melee_dmg, 5000)

        # 8. Buy Portal Grenade (5000 test cap)
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_gear:portal_grenade")
        )
        self.assertEqual(self.p1.get_field("score"), 36000)
        self.assertEqual(self.p1.client_dvars["ui_bz_portal"], "READY (2)")

        self.assertEqual(
            dispatched,
            [
                ("perk", "mule_kick", 4000, "thompson"),
                ("element_weapon", "acid_sprayer", 5000, "bz_acid_sprayer"),
                ("element_weapon", "cryo_cannon", 5000, "bz_cryo_cannon"),
                ("element_weapon", "multi_crossbow", 5000, "bz_multi_crossbow"),
                ("element_weapon", "blade_boomerang", 5000, "bz_blade_boomerang"),
                ("special_gear", "war_club", 5000, "bz_blade_boomerang"),
                ("special_gear", "pap_war_club", 5000, "bz_blade_boomerang"),
                ("pap", "pap_bowie", 5000, "bz_blade_boomerang"),
                ("special_gear", "equip_bowie", 0, "bz_blade_boomerang"),
                ("special_gear", "portal_grenade", 5000, "bz_blade_boomerang"),
            ],
        )

    def test_arsenal_menu_bz_menus_inc_and_waw17_gsc_compliance(self) -> None:
        import verify_hud_menus

        ui_dir = MOD_ROOT / "ui"
        arsenal_text = (ui_dir / "bz_station_arsenal.menu").read_text(encoding="latin1")
        bz_inc_text = (ui_dir / "bz_menus.inc").read_text(encoding="latin1")
        gauntlet_inc_text = (ui_dir / "gauntlet_menus.inc").read_text(encoding="latin1")

        # Brace balance & ASCII strictness
        for fname, content in (("bz_station_arsenal.menu", arsenal_text), ("bz_menus.inc", bz_inc_text)):
            self.assertEqual(verify_hud_menus.validate_menu_braces(content, filename=fname), [])
            non_ascii = [ch for ch in content if ord(ch) > 126 or (ord(ch) < 32 and ch not in "\t\r\n")]
            self.assertEqual(non_ascii, [], f"Non-ASCII chars in {fname}: {non_ascii!r}")

        # All Phase 2 clickable buttons present in bz_station_arsenal.menu
        found_tokens = set(re.findall(r'scriptMenuResponse\s+"([^"]+)"\s*;', arsenal_text))
        expected_tokens = {
            "buy_pap:pap_knife",
            "buy_pap:pap_bowie",
            "buy_pap:pap_cluster",
            "buy_element:acid_sprayer",
            "buy_element:cryo_cannon",
            "buy_element:multi_crossbow",
            "buy_element:blade_boomerang",
            "buy_gear:war_club",
            "buy_gear:pap_war_club",
            "buy_gear:equip_bowie",
            "buy_gear:portal_grenade",
            "close",
        }
        self.assertEqual(found_tokens, expected_tokens)
        self.assertIn("Phase 3", arsenal_text)
        self.assertIn("SQUAD COMPANIONS", arsenal_text)
        for line in arsenal_text.splitlines():
            if "exp" in line and "text(" in line:
                self.assertTrue(line.rstrip().endswith(";"), f"Missing semicolon: {line}")

        # Enhancements launch macros in bz_menus.inc enable bz_elements_enabled 1
        for macro in (
            "BZ_SOLO_START_ACTION",
            "BZ_SOLO_START_PROTOTYPE_ACTION",
            "BZ_SOLO_START_ASYLUM_ACTION",
            "BZ_SOLO_START_SUMPF_ACTION",
            "BZ_COOP_ACCEPT_ACTION",
        ):
            m = re.search(rf"#define\s+{macro}\b.*?(?:\n\n|\Z)", bz_inc_text, re.DOTALL)
            self.assertIsNotNone(m, f"Missing macro {macro}")
            self.assertIn("set bz_elements_enabled 1", m.group(0), f"{macro} must enable bz_elements_enabled 1")

        # Classic Mode and Classic Gauntlet macros keep bz_elements_enabled 0,
        # while Enhanced Gauntlet enables bz_elements_enabled 1 cleanly.
        classic_m = re.search(r"#define\s+BZ_CLASSIC_MODE_ACTION\b.*?(?:\n\n|\Z)", bz_inc_text, re.DOTALL)
        self.assertIsNotNone(classic_m)
        self.assertIn("set bz_elements_enabled 0", classic_m.group(0))
        for classic_gauntlet_macro in ("GAUNTLET_SOLO_START_ACTION", "GAUNTLET_CLASSIC_MODE_ACTION"):
            gm = re.search(rf"#define\s+{classic_gauntlet_macro}\b.*?(?:\n\n|\Z)", gauntlet_inc_text, re.DOTALL)
            self.assertIsNotNone(gm, f"Missing macro {classic_gauntlet_macro}")
            self.assertIn("set bz_elements_enabled 0", gm.group(0))
            self.assertNotIn("set bz_elements_enabled 1", gm.group(0))
        enh_gm = re.search(r"#define\s+GAUNTLET_ENHANCED_SOLO_START_ACTION\b.*?(?:\n\n|\Z)", gauntlet_inc_text, re.DOTALL)
        self.assertIsNotNone(enh_gm)
        self.assertIn("set bz_elements_enabled 1", enh_gm.group(0))

        # WaW 1.7 GSC compliance: zero foreach, clean tokenization, zero endon in sync callers
        gsc = BzGscRuntime(MOD_ROOT, FakeDvarStore())
        for rel in ("_bz_rules.gsc", "_bz_state.gsc", "_bz_hooks.gsc", "_bz_stations.gsc"):
            path = MOD_ROOT / "maps" / rel
            src = path.read_text(encoding="latin1")
            tokenize(src, filename=str(path))
            code_only = "\n".join(line.split("//", 1)[0] for line in src.splitlines())
            self.assertIsNone(re.search(r"\bforeach\b", code_only), f"Forbidden foreach in {rel}")

        hooks_mod = gsc.load_module(BZ_HOOKS_MOD)
        for fn in ("bz_precache_element_weapons", "bz_register_box_weapons", "bz_on_weapon_fired"):
            self.assertIn(fn, hooks_mod)
            self.assertFalse(_ast_contains_method_call(hooks_mod[fn].body, "endon"))

        state_mod = gsc.load_module(STATE_MOD)
        for fn in ("bz_try_buy_element_weapon", "bz_try_buy_special_gear", "bz_state_on_player_downed", "bz_state_on_round_start"):
            self.assertIn(fn, state_mod)
            self.assertFalse(_ast_contains_method_call(state_mod[fn].body, "endon"))


if __name__ == "__main__":
    unittest.main()
