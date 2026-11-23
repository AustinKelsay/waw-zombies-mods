"""Offline contract tests for mod/maps/_gauntlet_rules.gsc.

All assertions execute the actual WaW 1.7 GSC script directly via GscRuntime
using independently worked-out expected literals (no formula mirroring).
"""

from __future__ import annotations

from pathlib import Path
import unittest

from tests.gsc_runtime import GscRuntime, UNDEFINED

MOD_ROOT = Path(__file__).resolve().parent.parent / "mod"
RULES_MOD = "maps\\_gauntlet_rules"


class TestGauntletRulesStages(unittest.TestCase):
    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)

    def test_chronological_four_map_table_and_ascii_display_names(self) -> None:
        self.assertEqual(self.gsc.call(RULES_MOD, "get_stage_count"), 4)

        expected = [
            (1, "nazi_zombie_prototype", "Nacht der Untoten"),
            (2, "nazi_zombie_asylum", "Verruckt"),
            (3, "nazi_zombie_sumpf", "Shi No Numa"),
            (4, "nazi_zombie_factory", "Der Riese"),
        ]
        maps_arr = self.gsc.call(RULES_MOD, "get_stage_maps").to_list()
        self.assertEqual(
            maps_arr,
            [
                "nazi_zombie_prototype",
                "nazi_zombie_asylum",
                "nazi_zombie_sumpf",
                "nazi_zombie_factory",
            ],
        )

        for stage_num, map_name, display_name in expected:
            self.assertEqual(self.gsc.call(RULES_MOD, "get_map_for_stage", stage_num), map_name)
            self.assertEqual(
                self.gsc.call(RULES_MOD, "get_display_name_for_stage", stage_num), display_name
            )
            self.assertEqual(
                self.gsc.call(RULES_MOD, "get_display_name_for_map", map_name), display_name
            )
            self.assertEqual(self.gsc.call(RULES_MOD, "stage_index_for_map", map_name), stage_num)
            # Display names must be strictly ASCII-safe for WaW HUD font rendering.
            self.assertTrue(display_name.isascii())

    def test_stage_lookup_case_insensitivity_and_invalid_inputs(self) -> None:
        self.assertEqual(self.gsc.call(RULES_MOD, "stage_index_for_map", "NAZI_ZOMBIE_ASYLUM"), 2)
        self.assertEqual(self.gsc.call(RULES_MOD, "stage_index_for_map", "Nazi_Zombie_Factory"), 4)
        self.assertEqual(self.gsc.call(RULES_MOD, "stage_index_for_map", "mak"), 0)
        self.assertEqual(self.gsc.call(RULES_MOD, "stage_index_for_map", ""), 0)
        self.assertEqual(self.gsc.call(RULES_MOD, "stage_index_for_map", UNDEFINED), 0)

        self.assertIs(self.gsc.call(RULES_MOD, "get_map_for_stage", 0), UNDEFINED)
        self.assertIs(self.gsc.call(RULES_MOD, "get_map_for_stage", 5), UNDEFINED)
        self.assertIs(self.gsc.call(RULES_MOD, "get_display_name_for_stage", 0), UNDEFINED)
        self.assertIs(self.gsc.call(RULES_MOD, "get_display_name_for_stage", 5), UNDEFINED)
        self.assertIs(self.gsc.call(RULES_MOD, "get_display_name_for_map", "unknown_map"), UNDEFINED)

    def test_stage_and_cycle_advancement_with_stage_4_wrap_around(self) -> None:
        # Cycle 1: Stage 1 -> 2 -> 3 -> 4
        s2 = self.gsc.call(RULES_MOD, "get_next_stage_state", 1, 1)
        self.assertEqual(s2.cycle, 1)
        self.assertEqual(s2.stage, 2)
        self.assertEqual(s2.map_name, "nazi_zombie_asylum")
        self.assertEqual(s2.display_name, "Verruckt")
        self.assertEqual(s2.start_round, 1)
        self.assertEqual(s2.target_round, 10)
        self.assertFalse(s2.wrapped_cycle)

        s3 = self.gsc.call(RULES_MOD, "get_next_stage_state", 1, 2)
        self.assertEqual((s3.cycle, s3.stage, s3.map_name, s3.wrapped_cycle), (1, 3, "nazi_zombie_sumpf", False))

        s4 = self.gsc.call(RULES_MOD, "get_next_stage_state", 1, 3)
        self.assertEqual((s4.cycle, s4.stage, s4.map_name, s4.wrapped_cycle), (1, 4, "nazi_zombie_factory", False))

        # Cycle 1 Stage 4 -> wraps to Cycle 2 Stage 1 (Nacht der Untoten, rounds 10->15)
        c2_s1 = self.gsc.call(RULES_MOD, "get_next_stage_state", 1, 4)
        self.assertEqual(c2_s1.cycle, 2)
        self.assertEqual(c2_s1.stage, 1)
        self.assertEqual(c2_s1.map_name, "nazi_zombie_prototype")
        self.assertEqual(c2_s1.display_name, "Nacht der Untoten")
        self.assertEqual(c2_s1.start_round, 10)
        self.assertEqual(c2_s1.target_round, 15)
        self.assertTrue(c2_s1.wrapped_cycle)

        # Cycle 9 Stage 4 -> wraps to Cycle 10 Stage 1 (rounds 50->55)
        c10_s1 = self.gsc.call(RULES_MOD, "get_next_stage_state", 9, 4)
        self.assertEqual(c10_s1.cycle, 10)
        self.assertEqual(c10_s1.stage, 1)
        self.assertEqual(c10_s1.map_name, "nazi_zombie_prototype")
        self.assertEqual(c10_s1.start_round, 50)
        self.assertEqual(c10_s1.target_round, 55)
        self.assertTrue(c10_s1.wrapped_cycle)

    def test_full_three_cycle_stage_walk_and_stage_info_clamping(self) -> None:
        # Walk 12 consecutive Stage Transitions starting from Cycle 1, Stage 1
        expected_walk = [
            (1, 2, "nazi_zombie_asylum", 1, 10, False),
            (1, 3, "nazi_zombie_sumpf", 1, 10, False),
            (1, 4, "nazi_zombie_factory", 1, 10, False),
            (2, 1, "nazi_zombie_prototype", 10, 15, True),
            (2, 2, "nazi_zombie_asylum", 10, 15, False),
            (2, 3, "nazi_zombie_sumpf", 10, 15, False),
            (2, 4, "nazi_zombie_factory", 10, 15, False),
            (3, 1, "nazi_zombie_prototype", 15, 20, True),
            (3, 2, "nazi_zombie_asylum", 15, 20, False),
            (3, 3, "nazi_zombie_sumpf", 15, 20, False),
            (3, 4, "nazi_zombie_factory", 15, 20, False),
            (4, 1, "nazi_zombie_prototype", 20, 25, True),
        ]
        cycle, stage = 1, 1
        for exp in expected_walk:
            nxt = self.gsc.call(RULES_MOD, "get_next_stage_state", cycle, stage)
            self.assertEqual(
                (nxt.cycle, nxt.stage, nxt.map_name, nxt.start_round, nxt.target_round, nxt.wrapped_cycle),
                exp,
            )
            cycle, stage = nxt.cycle, nxt.stage

        # Defensive clamping in get_stage_info
        clamped_low = self.gsc.call(RULES_MOD, "get_stage_info", 0, 0)
        self.assertEqual((clamped_low.cycle, clamped_low.stage, clamped_low.map_name), (1, 1, "nazi_zombie_prototype"))
        clamped_high = self.gsc.call(RULES_MOD, "get_stage_info", 2, 9)
        self.assertEqual((clamped_high.cycle, clamped_high.stage, clamped_high.map_name), (2, 4, "nazi_zombie_factory"))


class TestGauntletRulesRoundBandsAndPrep(unittest.TestCase):
    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)

    def test_inclusive_round_bands_cycles_1_through_10(self) -> None:
        # Independent worked-out round-band table for Cycles 1..10
        expected_bands = [
            (1, 1, 10),
            (2, 10, 15),
            (3, 15, 20),
            (4, 20, 25),
            (5, 25, 30),
            (6, 30, 35),
            (7, 35, 40),
            (8, 40, 45),
            (9, 45, 50),
            (10, 50, 55),
        ]
        for cycle, exp_start, exp_target in expected_bands:
            self.assertEqual(self.gsc.call(RULES_MOD, "get_cycle_start_round", cycle), exp_start)
            self.assertEqual(self.gsc.call(RULES_MOD, "get_cycle_target_round", cycle), exp_target)
            info = self.gsc.call(RULES_MOD, "get_stage_info", cycle, 3)
            self.assertEqual(info.cycle, cycle)
            self.assertEqual(info.stage, 3)
            self.assertEqual(info.map_name, "nazi_zombie_sumpf")
            self.assertEqual(info.display_name, "Shi No Numa")
            self.assertEqual(info.start_round, exp_start)
            self.assertEqual(info.target_round, exp_target)

    def test_target_round_reached_boundaries(self) -> None:
        self.assertFalse(self.gsc.call(RULES_MOD, "is_target_round_reached", 9, 10))
        self.assertTrue(self.gsc.call(RULES_MOD, "is_target_round_reached", 10, 10))
        self.assertTrue(self.gsc.call(RULES_MOD, "is_target_round_reached", 11, 10))
        self.assertFalse(self.gsc.call(RULES_MOD, "is_target_round_reached", 14, 15))
        self.assertTrue(self.gsc.call(RULES_MOD, "is_target_round_reached", 15, 15))
        self.assertFalse(self.gsc.call(RULES_MOD, "is_target_round_reached", UNDEFINED, 10))

    def test_prep_phase_duration(self) -> None:
        self.assertEqual(self.gsc.call(RULES_MOD, "get_prep_phase_duration", 0), 0)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_prep_phase_duration", 1), 0)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_prep_phase_duration", 2), 45)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_prep_phase_duration", 3), 45)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_prep_phase_duration", 10), 45)


class TestGauntletRulesPointsFloor(unittest.TestCase):
    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)

    def test_points_floor_table(self) -> None:
        self.assertEqual(self.gsc.call(RULES_MOD, "get_points_floor", 1), 500)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_points_floor", 0), 500)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_points_floor", -5), 500)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_points_floor", 10), 5000)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_points_floor", 15), 7500)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_points_floor", 20), 10000)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_points_floor", 50), 25000)

    def test_apply_points_floor_preserves_surplus_and_tops_up_deficits(self) -> None:
        # Cycle 1 (starting round 1, floor 500)
        self.assertEqual(self.gsc.call(RULES_MOD, "apply_points_floor", 0, 1), 500)
        self.assertEqual(self.gsc.call(RULES_MOD, "apply_points_floor", 250, 1), 500)
        self.assertEqual(self.gsc.call(RULES_MOD, "apply_points_floor", 500, 1), 500)
        self.assertEqual(self.gsc.call(RULES_MOD, "apply_points_floor", 4320, 1), 4320)

        # Cycle 2 (starting round 10, floor 5000)
        self.assertEqual(self.gsc.call(RULES_MOD, "apply_points_floor", 12450, 10), 12450)
        self.assertEqual(self.gsc.call(RULES_MOD, "apply_points_floor", 5000, 10), 5000)
        self.assertEqual(self.gsc.call(RULES_MOD, "apply_points_floor", 4990, 10), 5000)
        self.assertEqual(self.gsc.call(RULES_MOD, "apply_points_floor", 0, 10), 5000)
        self.assertEqual(self.gsc.call(RULES_MOD, "apply_points_floor", -200, 10), 5000)
        self.assertEqual(self.gsc.call(RULES_MOD, "apply_points_floor", UNDEFINED, 10), 5000)


class TestGauntletRulesStockZombieScaling(unittest.TestCase):
    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)

    def test_stock_waw_iterative_integer_zombie_health(self) -> None:
        # Exact vanilla WaW 1.7 _zombiemode::ai_calculate_health() integers:
        # R1=150; R2..9 += 100; R10+ += Int(health * 0.1)
        expected_health = [
            (1, 150),
            (2, 250),
            (3, 350),
            (9, 950),
            (10, 1045),
            (11, 1149),
            (12, 1263),
            (15, 1679),
            (20, 2701),
            (25, 4348),
            (30, 7000),
        ]
        for round_num, exp_hp in expected_health:
            self.assertEqual(
                self.gsc.call(RULES_MOD, "calculate_zombie_health", round_num),
                exp_hp,
                msg=f"Health mismatch at Round {round_num}",
            )

        # Clamps non-positive rounds defensively to Round 1
        self.assertEqual(self.gsc.call(RULES_MOD, "calculate_zombie_health", 0), 150)
        self.assertEqual(self.gsc.call(RULES_MOD, "calculate_zombie_health", -3), 150)

    def test_stock_waw_zombie_move_speed(self) -> None:
        self.assertEqual(self.gsc.call(RULES_MOD, "calculate_zombie_move_speed", 1), 8)
        self.assertEqual(self.gsc.call(RULES_MOD, "calculate_zombie_move_speed", 5), 40)
        self.assertEqual(self.gsc.call(RULES_MOD, "calculate_zombie_move_speed", 10), 80)
        self.assertEqual(self.gsc.call(RULES_MOD, "calculate_zombie_move_speed", 15), 120)
        self.assertEqual(self.gsc.call(RULES_MOD, "calculate_zombie_move_speed", 20), 160)
        self.assertEqual(self.gsc.call(RULES_MOD, "calculate_zombie_move_speed", 0), 8)

    def test_stock_waw_zombie_spawn_delay_decay_and_floor(self) -> None:
        # Default base delay = 2.0 (stock raw/_zombiemode.gsc / Der Riese)
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "calculate_zombie_spawn_delay", 1), 2.0, places=6
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "calculate_zombie_spawn_delay", 2), 1.9, places=6
        )
        # Round 10: 2.0 * 0.95^9 = 1.26049887...
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "calculate_zombie_spawn_delay", 10), 1.26049887, places=5
        )
        # Round 15: 2.0 * 0.95^14 = 0.97535024...
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "calculate_zombie_spawn_delay", 15), 0.97535024, places=5
        )
        # High round hits exact 0.08 floor and never dips below it
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "calculate_zombie_spawn_delay", 70), 0.08, places=6
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "calculate_zombie_spawn_delay", 120), 0.08, places=6
        )

        # Optional per-map base delay (3.0 on Nacht/Verruckt/Shi No Numa)
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "calculate_zombie_spawn_delay", 1, 3.0), 3.0, places=6
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "calculate_zombie_spawn_delay", 10, 3.0), 1.89074830, places=5
        )
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "calculate_zombie_spawn_delay", 100, 3.0), 0.08, places=6
        )
        # Tiny base delay is still clamped at 0.08 floor
        self.assertAlmostEqual(
            self.gsc.call(RULES_MOD, "calculate_zombie_spawn_delay", 1, 0.02), 0.08, places=6
        )


if __name__ == "__main__":
    unittest.main()
