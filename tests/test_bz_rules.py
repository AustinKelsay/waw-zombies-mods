"""Offline TDD contract suite for Base Zombies rules and player state engine.

Executes real WaW 1.7 GSC scripts (mod/maps/_bz_rules.gsc and
mod/maps/_bz_state.gsc) directly via tests/gsc_runtime.py using independent
worked-example literals from Spec #11 and Ticket #13.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from tests.gsc_runtime import GscRuntime, GscStruct, UNDEFINED

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_ROOT = REPO_ROOT / "mod"
RULES_MOD = "maps\\_bz_rules"
STATE_MOD = "maps\\_bz_state"
RULES_GSC = MOD_ROOT / "maps" / "_bz_rules.gsc"
STATE_GSC = MOD_ROOT / "maps" / "_bz_state.gsc"


class TestBzRulesCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)

    def test_standard_perks_catalog_prices_and_ascii_names(self) -> None:
        ids = self.gsc.call(RULES_MOD, "bz_get_standard_perk_ids").to_list()
        self.assertEqual(
            ids,
            [
                "juggernog",
                "speed_cola",
                "double_tap",
                "quick_revive",
                "staminup",
                "mule_kick",
                "ap",
            ],
        )

        expected = [
            ("juggernog", 2500, "Juggernog"),
            ("speed_cola", 3000, "Speed Cola"),
            ("double_tap", 2000, "Double Tap"),
            ("quick_revive", 1500, "Quick Revive"),
            ("staminup", 2000, "Stamin-Up"),
            ("mule_kick", 4000, "Mule Kick"),
            ("ap", 3000, "Armor Piercing"),
        ]
        for perk_id, price, display_name in expected:
            self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_valid_standard_perk", perk_id))
            self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_valid_standard_perk", perk_id.upper()))
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_standard_perk_price", perk_id), price)
            name = self.gsc.call(RULES_MOD, "bz_get_item_display_name", "perk", perk_id)
            self.assertEqual(name, display_name)
            self.assertTrue(name.isascii())

            info = self.gsc.call(RULES_MOD, "bz_get_item_info", "perk", perk_id)
            self.assertEqual(info.category, "perk")
            self.assertEqual(info.id, perk_id)
            self.assertEqual(info.price, price)
            self.assertEqual(info.display_name, display_name)
            self.assertEqual(info.prereq, "")

        self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_valid_standard_perk", "phd_flopper"))
        self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_valid_standard_perk", ""))
        self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_valid_standard_perk", UNDEFINED))
        self.assertIs(self.gsc.call(RULES_MOD, "bz_get_standard_perk_price", "unknown"), UNDEFINED)

    def test_perk_tier_2_catalog_prices_and_prerequisites(self) -> None:
        ids = self.gsc.call(RULES_MOD, "bz_get_perk_t2_ids").to_list()
        self.assertEqual(
            ids,
            [
                "juggernog",
                "speed_cola",
                "double_tap",
                "quick_revive",
                "staminup",
                "mule_kick",
                "ap",
            ],
        )

        expected_names = {
            "juggernog": "Juggernog II",
            "speed_cola": "Speed Cola II",
            "double_tap": "Double Tap II",
            "quick_revive": "Quick Revive II",
            "staminup": "Stamin-Up II",
            "mule_kick": "Mule Kick II",
            "ap": "Armor Piercing II",
        }
        for perk_id, display_name in expected_names.items():
            self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_valid_perk_t2", perk_id))
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_perk_t2_price", perk_id), 5000)
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_perk_t2_prereq", perk_id), perk_id)
            name = self.gsc.call(RULES_MOD, "bz_get_item_display_name", "perk_t2", perk_id)
            self.assertEqual(name, display_name)
            self.assertTrue(name.isascii())

            info = self.gsc.call(RULES_MOD, "bz_get_item_info", "perk_t2", perk_id)
            self.assertEqual(info.price, 5000)
            self.assertEqual(info.prereq, perk_id)

        self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_valid_perk_t2", "bogus"))
        self.assertIs(self.gsc.call(RULES_MOD, "bz_get_perk_t2_price", "bogus"), UNDEFINED)
        self.assertIs(self.gsc.call(RULES_MOD, "bz_get_perk_t2_prereq", "bogus"), UNDEFINED)

    def test_apex_perks_catalog_and_prices(self) -> None:
        ids = self.gsc.call(RULES_MOD, "bz_get_apex_perk_ids").to_list()
        self.assertEqual(
            ids,
            ["double_ammo", "lightweight_heavy", "second_chance", "blast_shield"],
        )

        expected = [
            ("double_ammo", 8000, "Double Ammo"),
            ("lightweight_heavy", 8000, "Lightweight Heavy"),
            ("second_chance", 8000, "Second Chance"),
            ("blast_shield", 8000, "Blast Shield"),
        ]
        for apex_id, price, display_name in expected:
            self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_valid_apex_perk", apex_id))
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_apex_perk_price", apex_id), price)
            name = self.gsc.call(RULES_MOD, "bz_get_item_display_name", "apex", apex_id)
            self.assertEqual(name, display_name)
            self.assertTrue(name.isascii())

        self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_valid_apex_perk", "juggernog"))
        self.assertIs(self.gsc.call(RULES_MOD, "bz_get_apex_perk_price", "juggernog"), UNDEFINED)

    def test_classes_catalog_and_prices(self) -> None:
        ids = self.gsc.call(RULES_MOD, "bz_get_class_ids").to_list()
        self.assertEqual(
            ids,
            ["medic", "titan", "sapper", "daredevil", "assassin", "broker"],
        )

        expected = [
            ("medic", 5000, "Field Medic"),
            ("titan", 5000, "Titan"),
            ("sapper", 5000, "Sapper"),
            ("daredevil", 5000, "Daredevil"),
            ("assassin", 5000, "Assassin"),
            ("broker", 5000, "Broker"),
        ]
        for class_id, price, display_name in expected:
            self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_valid_class", class_id))
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_class_price", class_id), price)
            name = self.gsc.call(RULES_MOD, "bz_get_item_display_name", "class", class_id)
            self.assertEqual(name, display_name)
            self.assertTrue(name.isascii())

        self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_valid_class", "tank"))
        self.assertIs(self.gsc.call(RULES_MOD, "bz_get_class_price", "tank"), UNDEFINED)

    def test_pap_expansion_catalog_and_prices(self) -> None:
        ids = self.gsc.call(RULES_MOD, "bz_get_pap_upgrade_ids").to_list()
        self.assertEqual(ids, ["double_pap", "pap_knife", "pap_bowie", "pap_cluster"])

        expected = [
            ("double_pap", 5000, "Double Pack-a-Punch"),
            ("pap_knife", 5000, "PaP Knife"),
            ("pap_bowie", 5000, "PaP Bowie Knife"),
            ("pap_cluster", 5000, "PaP Cluster Grenade"),
        ]
        for upgrade_id, price, display_name in expected:
            self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_valid_pap_upgrade", upgrade_id))
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_pap_upgrade_price", upgrade_id), price)
            name = self.gsc.call(RULES_MOD, "bz_get_item_display_name", "pap", upgrade_id)
            self.assertEqual(name, display_name)
            self.assertTrue(name.isascii())

        self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_valid_pap_upgrade", "triple_pap"))
        self.assertIs(self.gsc.call(RULES_MOD, "bz_get_pap_upgrade_price", "triple_pap"), UNDEFINED)
        self.assertIs(self.gsc.call(RULES_MOD, "bz_get_item_info", "unknown_cat", "juggernog"), UNDEFINED)


class TestBzRulesMath(unittest.TestCase):
    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)

    def test_max_primary_weapons_mule_kick_tiers(self) -> None:
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_primary_weapons", False, False), 2)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_primary_weapons", True, False), 3)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_primary_weapons", True, True), 4)
        # Tier 2 without Tier 1 prerequisite must not grant extra slots
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_primary_weapons", False, True), 2)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_primary_weapons", UNDEFINED, UNDEFINED), 2)

    def test_max_health_juggernog_tiers_and_titan_stacking(self) -> None:
        # Non-Titan health progression
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_health", False, False, ""), 100)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_health", True, False, ""), 160)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_health", True, True, ""), 220)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_health", True, True, "medic"), 220)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_health", True, True, "assassin"), 220)

        # Titan 2x health stacking (200 / 320 / 440)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_health", False, False, "titan"), 200)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_health", True, False, "titan"), 320)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_health", True, True, "titan"), 440)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_health", True, True, "TITAN"), 440)

        # Juggernog II without Juggernog I prerequisite falls back to base HP
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_health", False, True, ""), 100)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_health", False, True, "titan"), 200)

    def test_move_speed_scale_staminup_lightweight_heavy_and_daredevil_burst(self) -> None:
        # Baseline pistol/SMG (1.0)
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_move_speed_scale", False, False, False, 1.0, False),
            1.0,
            places=6,
        )
        # Stamin-Up I (+15%) and Stamin-Up II (+25%, replaces +15%)
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_move_speed_scale", True, False, False, 1.0, False),
            1.15,
            places=6,
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_move_speed_scale", True, True, False, 1.0, False),
            1.25,
            places=6,
        )
        # Stamin-Up II without Stamin-Up I falls back to 1.0
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_move_speed_scale", False, True, False, 1.0, False),
            1.0,
            places=6,
        )
        # Lightweight Heavy cancels 0.80 LMG speed penalty (1.0 / 0.80 = 1.25 -> effective 0.80 * 1.25 = 1.0)
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_move_speed_scale", False, False, True, 0.8, False),
            1.25,
            places=6,
        )
        # Lightweight Heavy does not over-buff an already-fast 1.0 weapon
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_move_speed_scale", False, False, True, 1.0, False),
            1.0,
            places=6,
        )
        # Daredevil 2.5s Sprint Burst (+35%)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_daredevil_burst_duration"), 2.5, places=6)
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_move_speed_scale", False, False, False, 1.0, True),
            1.35,
            places=6,
        )
        # Full multiplicative composition: Stamin-Up II (1.25) * LMG compensation (1.25) * Burst (1.35) = 2.109375
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_move_speed_scale", True, True, True, 0.8, True),
            2.109375,
            places=6,
        )
        # Defensive clamping when weapon_move_scale is undefined or non-positive
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_move_speed_scale", False, False, True, 0.0, False),
            1.0,
            places=6,
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_move_speed_scale", False, False, True, UNDEFINED, False),
            1.0,
            places=6,
        )

    def test_bullet_damage_multiplier_and_limb_bonus_stacking(self) -> None:
        # Baseline
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_bullet_damage_mult", False, False, False, False, "", False, False),
            1.0,
            places=6,
        )
        # Individual modifiers
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_bullet_damage_mult", True, False, False, False, "", False, False),
            1.35,
            places=6,
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_bullet_damage_mult", True, True, False, False, "", False, False),
            1.6,
            places=6,
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_bullet_damage_mult", False, False, True, False, "", False, False),
            1.25,
            places=6,
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_bullet_damage_mult", False, False, False, True, "", False, False),
            1.75,
            places=6,
        )
        # Titan stationary 2x (only when stationary)
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_bullet_damage_mult", False, False, False, False, "titan", True, False),
            2.0,
            places=6,
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_bullet_damage_mult", False, False, False, False, "titan", False, False),
            1.0,
            places=6,
        )
        # Assassin headshot 5x (only on headshot)
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_bullet_damage_mult", False, False, False, False, "assassin", False, True),
            5.0,
            places=6,
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_bullet_damage_mult", False, False, False, False, "assassin", False, False),
            1.0,
            places=6,
        )
        # AP II + DT II + Double PaP = 1.6 * 1.25 * 1.75 = 3.5
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_bullet_damage_mult", True, True, True, True, "medic", True, True),
            3.5,
            places=6,
        )
        # Full Titan stationary stack = 3.5 * 2.0 = 7.0
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_bullet_damage_mult", True, True, True, True, "titan", True, False),
            7.0,
            places=6,
        )
        # Full Assassin headshot stack = 3.5 * 5.0 = 17.5
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_bullet_damage_mult", True, True, True, True, "assassin", False, True),
            17.5,
            places=6,
        )
        # AP II without AP I prereq must not apply
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_bullet_damage_mult", False, True, False, False, "", False, False),
            1.0,
            places=6,
        )

        # AP II armor/limb bonus multiplier
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_limb_damage_mult", True, True, "right_leg_upper"),
            1.25,
            places=6,
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_limb_damage_mult", True, True, "torso_lower"),
            1.25,
            places=6,
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_limb_damage_mult", True, True, "head"),
            1.0,
            places=6,
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_limb_damage_mult", True, False, "right_leg_upper"),
            1.0,
            places=6,
        )

    def test_melee_damage_pap_knife_and_pap_bowie_true_one_hit_kill(self) -> None:
        # Unupgraded standard knife and Bowie knife
        self.assertEqual(
            self.gsc.call(RULES_MOD, "bz_calc_melee_damage", 150, 150, False, False, False, True),
            150,
        )
        self.assertEqual(
            self.gsc.call(RULES_MOD, "bz_calc_melee_damage", 1000, 1045, False, False, True, True),
            1000,
        )
        # PaP Knife = 3x melee damage on standard knife
        self.assertEqual(
            self.gsc.call(RULES_MOD, "bz_calc_melee_damage", 150, 1045, True, False, False, True),
            450,
        )
        # PaP Knife does not automatically upgrade Bowie without PaP Bowie
        self.assertEqual(
            self.gsc.call(RULES_MOD, "bz_calc_melee_damage", 1000, 2701, True, False, True, True),
            1000,
        )
        # PaP Bowie = true 1-hit kill on regular zombies at ANY round health
        self.assertEqual(
            self.gsc.call(RULES_MOD, "bz_calc_melee_damage", 1000, 150, False, True, True, True),
            3000,
        )
        r50_dmg = self.gsc.call(RULES_MOD, "bz_calc_melee_damage", 1000, 47228, False, True, True, True)
        self.assertGreaterEqual(r50_dmg, 47228)
        r100_dmg = self.gsc.call(RULES_MOD, "bz_calc_melee_damage", 1000, 5500000, False, True, True, True)
        self.assertGreaterEqual(r100_dmg, 5500000)
        # Non-regular enemy (e.g., boss/hellhound) gets 3x Bowie (3000) rather than infinite 1-shot
        self.assertEqual(
            self.gsc.call(RULES_MOD, "bz_calc_melee_damage", 1000, 50000, False, True, True, False),
            3000,
        )
        # Owning PaP Bowie without Bowie equipped does not buff standard knife
        self.assertEqual(
            self.gsc.call(RULES_MOD, "bz_calc_melee_damage", 150, 1045, False, True, False, True),
            150,
        )

    def test_broker_points_aura_never_double_stacks_and_mystery_box_discount(self) -> None:
        # Points multiplier
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_calc_points_mult", "", False), 1.0, places=6)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_calc_points_mult", "titan", False), 1.0, places=6)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_calc_points_mult", "titan", True), 1.5, places=6)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_calc_points_mult", "", True), 1.5, places=6)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_calc_points_mult", "broker", False), 2.0, places=6)
        # Broker near another Broker MUST stay 2.0 (never 3.0!)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_calc_points_mult", "broker", True), 2.0, places=6)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_calc_points_mult", "BROKER", True), 2.0, places=6)

        # Mystery Box 50% discount for Broker
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_box_cost", 950, "broker"), 475)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_box_cost", 10, "broker"), 5)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_box_cost", 950, ""), 950)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_box_cost", 950, "sapper"), 950)

    def test_sapper_grenades_cluster_grenade_flopper_slam_and_reserve_ammo(self) -> None:
        # Max grenades
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_grenades", "sapper"), 10)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_grenades", "SAPPER"), 10)
        for cls in ("", "medic", "titan", "daredevil", "assassin", "broker"):
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_max_grenades", cls), 4)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_grenade_radius", 256, "sapper"), 384)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_grenade_radius", 256, "medic"), 256)

        # PaP Cluster Grenade round-scaled lethal blast + mini-clusters
        c1 = self.gsc.call(RULES_MOD, "bz_calc_cluster_grenade_damage", 1, 150)
        self.assertEqual(c1.primary_damage, 1500)
        self.assertEqual(c1.mini_damage, 750)
        self.assertEqual(c1.mini_count, 4)

        c20 = self.gsc.call(RULES_MOD, "bz_calc_cluster_grenade_damage", 20, 2701)
        self.assertEqual(c20.primary_damage, 3376)
        self.assertEqual(c20.mini_damage, 1755)
        self.assertGreater(c20.primary_damage, 2701)

        c50 = self.gsc.call(RULES_MOD, "bz_calc_cluster_grenade_damage", 50, 47228)
        self.assertEqual(c50.primary_damage, 59035)
        self.assertEqual(c50.mini_damage, 30698)
        self.assertGreater(c50.primary_damage, 47228)

        # Fallback round scaling when zombie_health is undefined
        c30_auto = self.gsc.call(RULES_MOD, "bz_calc_cluster_grenade_damage", 30, UNDEFINED)
        self.assertEqual(c30_auto.primary_damage, 8750)
        self.assertEqual(c30_auto.mini_damage, 4550)

        # PhD Flopper height-scaled slam damage
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_flopper_slam_damage", 40, 1), 0)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_flopper_slam_damage", 63, 10), 0)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_flopper_slam_damage", 100, 1), 600)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_flopper_slam_damage", 120, 1), 720)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_flopper_slam_damage", 100, 10), 1950)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_flopper_slam_damage", 200, 10), 3900)
        # Height scaling caps at 3.0x (300 units)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_flopper_slam_damage", 300, 10), 5850)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_flopper_slam_damage", 500, 10), 5850)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_flopper_slam_damage", 100, 20), 3450)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_flopper_slam_radius", 50), 0)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_flopper_slam_radius", 164), 230)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_flopper_slam_radius", 400), 298)

        # Reserve ammo multiplier (Double Ammo 2.0x + Double PaP 1.5x -> 3.0x)
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_reserve_ammo_mult", False, False), 1.0, places=6
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_reserve_ammo_mult", True, False), 2.0, places=6
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_reserve_ammo_mult", False, True), 1.5, places=6
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_reserve_ammo_mult", True, True), 3.0, places=6
        )

    def test_revive_time_invuln_solo_revives_and_self_damage_immunity(self) -> None:
        # Revive timing: base 3.0s
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_revive_time", 3.0, False, False, ""), 3.0, places=6
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_revive_time", 3.0, True, False, ""), 1.5, places=6
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_revive_time", 3.0, True, True, ""), 0.9, places=6
        )
        # Field Medic without QR = 2x faster (1.5s); with QR = instant (0.0s)
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_revive_time", 3.0, False, False, "medic"), 1.5, places=6
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_revive_time", 3.0, True, False, "medic"), 0.0, places=6
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_calc_revive_time", 3.0, True, True, "medic"), 0.0, places=6
        )

        # Quick Revive II post-revive invuln (2s) and +1 extra Solo revive
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_get_post_revive_invuln_duration", True, True), 2.0, places=6
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "bz_get_post_revive_invuln_duration", True, False), 0.0, places=6
        )
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_extra_solo_revives", True, True), 2)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_extra_solo_revives", True, False), 1)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_extra_solo_revives", False, False), 0)

        # Self-damage immunity (Blast Shield = all 4; Daredevil = fall & slam only)
        for dmg_type in ("explosive", "splash", "fire", "fall"):
            self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_self_damage_immune", True, "", dmg_type))
            self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_self_damage_immune", False, "", dmg_type))
        self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_self_damage_immune", False, "daredevil", "fall"))
        self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_self_damage_immune", False, "daredevil", "slam"))
        self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_self_damage_immune", False, "daredevil", "fire"))
        self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_self_damage_immune", False, "daredevil", "explosive"))


def _make_player(score: int | None = 500) -> GscStruct:
    player = GscStruct()
    if score is not None:
        player.set_field("score", score)
    return player


class TestBzStatePurchases(unittest.TestCase):
    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)

    def test_init_player_sets_clean_defaults_and_preserves_existing_score(self) -> None:
        p = _make_player(2500)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p)

        self.assertTrue(p.bz_initialized)
        self.assertEqual(p.score, 2500)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_class", p), "")
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_primary_weapons", p), 2)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_health", p), 100)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_grenades", p), 4)
        self.assertFalse(p.bz_pap_knife)
        self.assertFalse(p.bz_pap_bowie)
        self.assertFalse(p.bz_pap_cluster)
        self.assertFalse(p.bz_second_chance_ready)
        self.assertFalse(p.bz_sapper_grenade_refill_ready)

        # Undefined score initializes cleanly to 0
        p_no_score = _make_player(None)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p_no_score)
        self.assertEqual(p_no_score.score, 0)

    def test_buy_standard_perks_happy_paths_and_rejections(self) -> None:
        p = _make_player(20000)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p)

        # Buy all 7 Standard Perks; exact total cost = 2500+3000+2000+1500+2000+4000+3000 = 18000
        buys = [
            ("juggernog", 2500, 17500),
            ("speed_cola", 3000, 14500),
            ("double_tap", 2000, 12500),
            ("quick_revive", 1500, 11000),
            ("staminup", 2000, 9000),
            ("mule_kick", 4000, 5000),
            ("ap", 3000, 2000),
        ]
        for perk_id, cost, expected_score in buys:
            res = self.gsc.call(STATE_MOD, "bz_try_buy_perk", p, perk_id)
            self.assertTrue(res.ok)
            self.assertEqual(res.status, "ok")
            self.assertEqual(res.item_id, perk_id)
            self.assertEqual(res.cost, cost)
            self.assertEqual(res.remaining_score, expected_score)
            self.assertEqual(p.score, expected_score)
            self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_has_perk", p, perk_id))

        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_health", p), 160)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_primary_weapons", p), 3)

        # Duplicate purchase rejected with no score deduction
        dup = self.gsc.call(STATE_MOD, "bz_try_buy_perk", p, "JUGGERNOG")
        self.assertFalse(dup.ok)
        self.assertEqual(dup.status, "already_owned")
        self.assertEqual(p.score, 2000)

        # Invalid perk rejected with no score deduction
        inv = self.gsc.call(STATE_MOD, "bz_try_buy_perk", p, "electric_cherry")
        self.assertFalse(inv.ok)
        self.assertEqual(inv.status, "invalid_item")
        self.assertEqual(inv.cost, 0)
        self.assertEqual(p.score, 2000)

        # Insufficient points rejected with no score deduction
        p_broke = _make_player(3990)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p_broke)
        insuff = self.gsc.call(STATE_MOD, "bz_try_buy_perk", p_broke, "mule_kick")
        self.assertFalse(insuff.ok)
        self.assertEqual(insuff.status, "insufficient_points")
        self.assertEqual(insuff.cost, 4000)
        self.assertEqual(p_broke.score, 3990)
        self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_has_perk", p_broke, "mule_kick"))

    def test_buy_perk_tier_2_enforces_prereq_and_unlocks_tier2_caps(self) -> None:
        p = _make_player(25000)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p)

        # Missing base perk prerequisite -> missing_prereq (even with plenty of points)
        no_prereq = self.gsc.call(STATE_MOD, "bz_try_buy_perk_t2", p, "mule_kick")
        self.assertFalse(no_prereq.ok)
        self.assertEqual(no_prereq.status, "missing_prereq")
        self.assertEqual(p.score, 25000)
        self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_has_perk_t2", p, "mule_kick"))

        # Buy Mule Kick I (4000) then Mule Kick II (5000) -> 4 primary weapon slots
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_try_buy_perk", p, "mule_kick").status, "ok")
        mk2 = self.gsc.call(STATE_MOD, "bz_try_buy_perk_t2", p, "mule_kick")
        self.assertTrue(mk2.ok)
        self.assertEqual(mk2.status, "ok")
        self.assertEqual(mk2.cost, 5000)
        self.assertEqual(p.score, 16000)
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_has_perk_t2", p, "mule_kick"))
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_primary_weapons", p), 4)

        # Buy Juggernog I (2500) then Juggernog II (5000) -> 220 HP
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_try_buy_perk", p, "juggernog").status, "ok")
        j2 = self.gsc.call(STATE_MOD, "bz_try_buy_perk_t2", p, "juggernog")
        self.assertTrue(j2.ok)
        self.assertEqual(p.score, 8500)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_health", p), 220)

        # Duplicate T2 rejected
        dup = self.gsc.call(STATE_MOD, "bz_try_buy_perk_t2", p, "juggernog")
        self.assertEqual(dup.status, "already_owned")
        self.assertEqual(p.score, 8500)

        # Insufficient points on unlocked T2
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_try_buy_perk", p, "ap").status, "ok")  # 5500 left
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_try_buy_perk", p, "staminup").status, "ok")  # 3500 left
        insuff = self.gsc.call(STATE_MOD, "bz_try_buy_perk_t2", p, "ap")
        self.assertEqual(insuff.status, "insufficient_points")
        self.assertEqual(p.score, 3500)

        # Invalid T2 ID
        inv = self.gsc.call(STATE_MOD, "bz_try_buy_perk_t2", p, "double_ammo")
        self.assertEqual(inv.status, "invalid_item")

    def test_buy_apex_perks_and_second_chance_arming(self) -> None:
        p = _make_player(37000)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p)

        for apex_id in ("double_ammo", "lightweight_heavy", "second_chance", "blast_shield"):
            res = self.gsc.call(STATE_MOD, "bz_try_buy_apex", p, apex_id)
            self.assertTrue(res.ok)
            self.assertEqual(res.status, "ok")
            self.assertEqual(res.cost, 8000)
            self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_has_apex", p, apex_id))

        self.assertEqual(p.score, 5000)
        # Buying Second Chance immediately arms it for the current round
        self.assertTrue(p.bz_second_chance_ready)

        # Duplicate rejected
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_try_buy_apex", p, "blast_shield").status, "already_owned")
        # Invalid rejected
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_try_buy_apex", p, "god_mode").status, "invalid_item")

        # Insufficient points rejected
        p2 = _make_player(7990)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p2)
        insuff = self.gsc.call(STATE_MOD, "bz_try_buy_apex", p2, "double_ammo")
        self.assertEqual(insuff.status, "insufficient_points")
        self.assertEqual(p2.score, 7990)

    def test_buy_and_swap_classes_updates_derived_stats(self) -> None:
        p = _make_player(20000)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p)
        self.gsc.call(STATE_MOD, "bz_try_buy_perk", p, "juggernog")      # -2500 -> 17500
        self.gsc.call(STATE_MOD, "bz_try_buy_perk_t2", p, "juggernog")   # -5000 -> 12500

        # Buy Titan (5,000 test cap) -> 440 HP with Juggernog II
        c1 = self.gsc.call(STATE_MOD, "bz_try_buy_class", p, "titan")
        self.assertTrue(c1.ok)
        self.assertEqual(c1.status, "ok")
        self.assertEqual(c1.cost, 5000)
        self.assertEqual(c1.previous_class, "")
        self.assertFalse(c1.swapped)
        self.assertEqual(p.score, 7500)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_class", p), "titan")
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_health", p), 440)

        # Buying the same active class is rejected as already_owned
        same = self.gsc.call(STATE_MOD, "bz_try_buy_class", p, "TITAN")
        self.assertFalse(same.ok)
        self.assertEqual(same.status, "already_owned")
        self.assertEqual(p.score, 7500)

        # Swapping to Sapper (5,000 test cap) reports previous_class="titan", drops HP back to 220, raises grenades to 10
        c2 = self.gsc.call(STATE_MOD, "bz_try_buy_class", p, "sapper")
        self.assertTrue(c2.ok)
        self.assertEqual(c2.status, "ok")
        self.assertEqual(c2.previous_class, "titan")
        self.assertTrue(c2.swapped)
        self.assertEqual(p.score, 2500)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_class", p), "sapper")
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_health", p), 220)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_grenades", p), 10)

        # Insufficient points to swap to Broker (need 5000, have 2500)
        insuff = self.gsc.call(STATE_MOD, "bz_try_buy_class", p, "broker")
        self.assertEqual(insuff.status, "insufficient_points")
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_class", p), "sapper")
        self.assertEqual(p.score, 2500)

        # Invalid class rejected
        inv = self.gsc.call(STATE_MOD, "bz_try_buy_class", p, "necromancer")
        self.assertEqual(inv.status, "invalid_item")

    def test_buy_pap_upgrades_and_double_pap_weapon_flags(self) -> None:
        p = _make_player(27500)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p)

        # Double PaP rejected if weapon not Tier 1 PaP'd or empty weapon name
        no_pap = self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "double_pap", "zombie_ppsh", False)
        self.assertEqual(no_pap.status, "missing_prereq")
        no_weap = self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "double_pap", "", True)
        self.assertEqual(no_weap.status, "missing_prereq")
        self.assertEqual(p.score, 27500)

        # Double PaP succeeds on PaP'd PPSH (5,000 pts test cap)
        dp1 = self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "double_pap", "zombie_ppsh_upgraded", True)
        self.assertTrue(dp1.ok)
        self.assertEqual(dp1.status, "ok")
        self.assertEqual(dp1.cost, 5000)
        self.assertEqual(p.score, 22500)
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_is_weapon_double_pap", p, "zombie_ppsh_upgraded"))
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_is_weapon_double_pap", p, "ZOMBIE_PPSH_UPGRADED"))
        self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_is_weapon_double_pap", p, "zombie_mg42_upgraded"))

        # Re-buying Double PaP on the SAME weapon -> already_owned
        dp_dup = self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "double_pap", "zombie_ppsh_upgraded", True)
        self.assertEqual(dp_dup.status, "already_owned")
        self.assertEqual(p.score, 22500)

        # Buying Double PaP on a SECOND distinct PaP'd weapon succeeds (5,000 pts test cap)
        dp2 = self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "double_pap", "zombie_mg42_upgraded", True)
        self.assertTrue(dp2.ok)
        self.assertEqual(p.score, 17500)
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_is_weapon_double_pap", p, "zombie_mg42_upgraded"))

        # Direct mark/unmark helpers work cleanly
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_unmark_weapon_double_pap", p, "zombie_mg42_upgraded"))
        self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_is_weapon_double_pap", p, "zombie_mg42_upgraded"))
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_mark_weapon_double_pap", p, "zombie_mg42_upgraded"))
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_is_weapon_double_pap", p, "zombie_mg42_upgraded"))
        self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_mark_weapon_double_pap", p, ""))

        # PaP Knife (5,000 pts) - no prereq required
        pk = self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "pap_knife")
        self.assertTrue(pk.ok)
        self.assertEqual(pk.cost, 5000)
        self.assertEqual(p.score, 12500)
        self.assertTrue(p.bz_pap_knife)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "pap_knife").status, "already_owned")

        # PaP Bowie (5,000 pts) - requires owning Bowie Knife
        pb_no = self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "pap_bowie", "", False)
        self.assertEqual(pb_no.status, "missing_prereq")
        pb_yes = self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "pap_bowie", "", True)
        self.assertTrue(pb_yes.ok)
        self.assertEqual(pb_yes.cost, 5000)
        self.assertEqual(p.score, 7500)
        self.assertTrue(p.bz_pap_bowie)

        # PaP Cluster Grenade (5,000 pts)
        pc = self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "pap_cluster")
        self.assertTrue(pc.ok)
        self.assertEqual(pc.cost, 5000)
        self.assertEqual(p.score, 2500)
        self.assertTrue(p.bz_pap_cluster)

        # Insufficient points for another Double PaP (need 5,000, have 2,500)
        insuff = self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "double_pap", "ray_gun_upgraded", True)
        self.assertEqual(insuff.status, "insufficient_points")
        self.assertEqual(p.score, 2500)

        # Invalid PaP upgrade ID
        inv = self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "pap_monkey")
        self.assertEqual(inv.status, "invalid_item")


class TestBzStateLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)

    def test_downed_clears_perks_t2_apex_and_excess_weapons_while_preserving_class_and_pap(self) -> None:
        p = _make_player(250000)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p)

        # Equip full endgame build: all 7 perks, all 7 T2, all 4 Apex, Titan class, Double PaP x2, PaP Knife/Bowie/Cluster
        for perk_id in ("juggernog", "speed_cola", "double_tap", "quick_revive", "staminup", "mule_kick", "ap"):
            self.assertTrue(self.gsc.call(STATE_MOD, "bz_try_buy_perk", p, perk_id).ok)
            self.assertTrue(self.gsc.call(STATE_MOD, "bz_try_buy_perk_t2", p, perk_id).ok)
        for apex_id in ("double_ammo", "lightweight_heavy", "second_chance", "blast_shield"):
            self.assertTrue(self.gsc.call(STATE_MOD, "bz_try_buy_apex", p, apex_id).ok)

        self.assertTrue(self.gsc.call(STATE_MOD, "bz_try_buy_class", p, "titan").ok)
        self.assertTrue(
            self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "double_pap", "zombie_ppsh_upgraded", True).ok
        )
        self.assertTrue(
            self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "double_pap", "zombie_mg42_upgraded", True).ok
        )
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "pap_knife").ok)
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "pap_bowie", "", True).ok)
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_try_buy_pap_upgrade", p, "pap_cluster").ok)

        score_before_down = p.score
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_health", p), 440)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_primary_weapons", p), 4)

        # Player goes down while carrying 4 primary weapons
        summary = self.gsc.call(STATE_MOD, "bz_state_on_player_downed", p, 4)

        # Excess Mule Kick weapon slots reported accurately
        self.assertEqual(summary.prev_max_weapons, 4)
        self.assertEqual(summary.new_max_weapons, 2)
        self.assertEqual(summary.excess_weapon_slots, 2)
        self.assertEqual(summary.cleared_perks.size, 7)
        self.assertEqual(summary.cleared_perks_t2.size, 7)
        self.assertEqual(summary.cleared_apex.size, 4)

        # All Standard Perks, Perk Tier 2, Apex Perks, and Second Chance cleared
        for perk_id in ("juggernog", "speed_cola", "double_tap", "quick_revive", "staminup", "mule_kick", "ap"):
            self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_has_perk", p, perk_id))
            self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_has_perk_t2", p, perk_id))
        for apex_id in ("double_ammo", "lightweight_heavy", "second_chance", "blast_shield"):
            self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_has_apex", p, apex_id))
        self.assertFalse(p.bz_second_chance_ready)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_primary_weapons", p), 2)

        # Strictly preserved: Class (Titan -> 200 HP base), Double PaP flags, PaP Melee/Cluster, Score
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_class", p), "titan")
        self.assertEqual(summary.preserved_class, "titan")
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_health", p), 200)
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_is_weapon_double_pap", p, "zombie_ppsh_upgraded"))
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_is_weapon_double_pap", p, "zombie_mg42_upgraded"))
        self.assertTrue(p.bz_pap_knife)
        self.assertTrue(p.bz_pap_bowie)
        self.assertTrue(p.bz_pap_cluster)
        self.assertTrue(summary.preserved_pap_knife)
        self.assertTrue(summary.preserved_pap_bowie)
        self.assertTrue(summary.preserved_pap_cluster)
        self.assertEqual(p.score, score_before_down)

        # Trying to buy Juggernog II right after down is blocked by missing_prereq until Jugg I is re-bought
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_try_buy_perk_t2", p, "juggernog").status, "missing_prereq")
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_try_buy_perk", p, "juggernog").status, "ok")
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_get_max_health", p), 320)

    def test_downed_excess_mule_kick_slot_edge_cases(self) -> None:
        # Mule Kick I holding 3 weapons -> 1 excess slot
        p1 = _make_player(10000)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p1)
        self.gsc.call(STATE_MOD, "bz_try_buy_perk", p1, "mule_kick")
        s1 = self.gsc.call(STATE_MOD, "bz_state_on_player_downed", p1, 3)
        self.assertEqual((s1.prev_max_weapons, s1.new_max_weapons, s1.excess_weapon_slots), (3, 2, 1))

        # Mule Kick II holding only 2 weapons -> 0 excess slots to drop
        p2 = _make_player(20000)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p2)
        self.gsc.call(STATE_MOD, "bz_try_buy_perk", p2, "mule_kick")
        self.gsc.call(STATE_MOD, "bz_try_buy_perk_t2", p2, "mule_kick")
        s2 = self.gsc.call(STATE_MOD, "bz_state_on_player_downed", p2, 2)
        self.assertEqual((s2.prev_max_weapons, s2.new_max_weapons, s2.excess_weapon_slots), (4, 2, 0))

        # Mule Kick II with omitted weapon count -> defaults to prev_max - 2 = 2
        p3 = _make_player(20000)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p3)
        self.gsc.call(STATE_MOD, "bz_try_buy_perk", p3, "mule_kick")
        self.gsc.call(STATE_MOD, "bz_try_buy_perk_t2", p3, "mule_kick")
        s3 = self.gsc.call(STATE_MOD, "bz_state_on_player_downed", p3)
        self.assertEqual((s3.prev_max_weapons, s3.new_max_weapons, s3.excess_weapon_slots), (4, 2, 2))

        # No Mule Kick -> 0 excess slots
        p4 = _make_player(5000)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p4)
        s4 = self.gsc.call(STATE_MOD, "bz_state_on_player_downed", p4, 2)
        self.assertEqual((s4.prev_max_weapons, s4.new_max_weapons, s4.excess_weapon_slots), (2, 2, 0))

    def test_round_start_recharges_second_chance_and_sapper_grenades(self) -> None:
        p = _make_player(40000)
        self.gsc.call(STATE_MOD, "bz_state_init_player", p)

        # Without Second Chance or Sapper
        self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_try_consume_second_chance", p))
        r0 = self.gsc.call(STATE_MOD, "bz_state_on_round_start", p)
        self.assertFalse(r0.second_chance_recharged)
        self.assertFalse(r0.sapper_grenade_refill)
        self.assertEqual(r0.target_grenades, 4)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_consume_sapper_grenade_refill", p), 0)

        # Buy Second Chance (20k) + Sapper (10k)
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_try_buy_apex", p, "second_chance").ok)
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_try_buy_class", p, "sapper").ok)

        # Second Chance triggers once per round, then rejects a second lethal hit in the same round
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_try_consume_second_chance", p))
        self.assertFalse(p.bz_second_chance_ready)
        self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_try_consume_second_chance", p))

        # Round start recharges Second Chance and arms Sapper 10-grenade refill
        r1 = self.gsc.call(STATE_MOD, "bz_state_on_round_start", p)
        self.assertTrue(r1.second_chance_recharged)
        self.assertTrue(r1.sapper_grenade_refill)
        self.assertEqual(r1.target_grenades, 10)
        self.assertTrue(p.bz_second_chance_ready)
        self.assertTrue(p.bz_sapper_grenade_refill_ready)
        self.assertEqual(p.bz_grenades_to_refill, 10)

        # Second Chance works again in the new round; Sapper refill consumes cleanly once per round
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_try_consume_second_chance", p))
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_consume_sapper_grenade_refill", p), 10)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_consume_sapper_grenade_refill", p), 0)

        # After going down: Second Chance is lost (not recharged next round), but Sapper class persists and still refills!
        self.gsc.call(STATE_MOD, "bz_state_on_player_downed", p, 2)
        r2 = self.gsc.call(STATE_MOD, "bz_state_on_round_start", p)
        self.assertFalse(r2.second_chance_recharged)
        self.assertFalse(p.bz_second_chance_ready)
        self.assertTrue(r2.sapper_grenade_refill)
        self.assertEqual(r2.target_grenades, 10)
        self.assertEqual(self.gsc.call(STATE_MOD, "bz_state_consume_sapper_grenade_refill", p), 10)


class TestBzWaw17SyntaxCompliance(unittest.TestCase):
    def _strip_comments(self, source: str) -> str:
        no_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
        return re.sub(r"//[^\n]*", "", no_block)

    def test_bz_rules_and_state_are_valid_waw17_gsc_with_no_foreach_or_endon(self) -> None:
        gsc = GscRuntime(MOD_ROOT)
        rules_fns = gsc.load_module(RULES_MOD)
        state_fns = gsc.load_module(STATE_MOD)

        self.assertIn("bz_calc_max_health", rules_fns)
        self.assertIn("bz_calc_bullet_damage_mult", rules_fns)
        self.assertIn("bz_state_init_player", state_fns)
        self.assertIn("bz_state_on_player_downed", state_fns)
        self.assertIn("bz_state_on_round_start", state_fns)

        for path in (RULES_GSC, STATE_GSC):
            raw = path.read_text(encoding="utf-8")
            self.assertTrue(raw.isascii(), msg=f"Non-ASCII characters found in {path.name}")
            code = self._strip_comments(raw)
            self.assertIsNone(
                re.search(r"\bforeach\b", code, flags=re.IGNORECASE),
                msg=f"Forbidden WaW 1.7 'foreach' syntax found in {path.name}",
            )
            self.assertIsNone(
                re.search(r"\bendon\s*\(", code, flags=re.IGNORECASE),
                msg=f"Forbidden 'endon(' in pure sync module {path.name}",
            )


if __name__ == "__main__":
    unittest.main()
