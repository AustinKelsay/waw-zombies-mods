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

    def test_stage_and_cycle_advancement_with_continuous_rounds_and_shuffled_wrap(self) -> None:
        canonical = self.gsc.call(RULES_MOD, "get_stage_maps")
        # Cycle 1: Stage 1 (R1..R5) -> Stage 2 (R6..R10) -> Stage 3 (R11..R15) -> Stage 4 (R16..R20)
        s2 = self.gsc.call(RULES_MOD, "get_next_stage_state", 1, 1, canonical, 5, UNDEFINED, 5)
        self.assertEqual(s2.cycle, 1)
        self.assertEqual(s2.stage, 2)
        self.assertEqual(s2.map_name, "nazi_zombie_asylum")
        self.assertEqual(s2.display_name, "Verruckt")
        self.assertEqual(s2.start_round, 6)
        self.assertEqual(s2.target_round, 10)
        self.assertEqual(s2.prep_duration, 45)
        self.assertFalse(s2.wrapped_cycle)

        s3 = self.gsc.call(RULES_MOD, "get_next_stage_state", 1, 2, canonical, 10, UNDEFINED, 4)
        self.assertEqual((s3.cycle, s3.stage, s3.map_name, s3.start_round, s3.target_round, s3.wrapped_cycle), (1, 3, "nazi_zombie_sumpf", 11, 14, False))

        s4 = self.gsc.call(RULES_MOD, "get_next_stage_state", 1, 3, canonical, 14, UNDEFINED, 6)
        self.assertEqual((s4.cycle, s4.stage, s4.map_name, s4.start_round, s4.target_round, s4.wrapped_cycle), (1, 4, "nazi_zombie_factory", 15, 20, False))

        # Cycle 1 Stage 4 (factory) -> wraps to Cycle 2 Stage 1 (never repeats factory first!)
        c2_s1 = self.gsc.call(RULES_MOD, "get_next_stage_state", 1, 4, canonical, 20, UNDEFINED, 5)
        self.assertEqual(c2_s1.cycle, 2)
        self.assertEqual(c2_s1.stage, 1)
        self.assertNotEqual(c2_s1.map_name, "nazi_zombie_factory")
        self.assertEqual(c2_s1.start_round, 21)
        self.assertEqual(c2_s1.target_round, 25)
        self.assertEqual(c2_s1.prep_duration, 45)
        self.assertTrue(c2_s1.wrapped_cycle)

    def test_shuffled_cycle_order_and_no_repeat_boundary_across_many_rolls(self) -> None:
        all_maps = {
            "nazi_zombie_prototype",
            "nazi_zombie_asylum",
            "nazi_zombie_sumpf",
            "nazi_zombie_factory",
        }
        # Cycle 1 always opens on Nacht and shuffles Stages 2..4 across all 6 permutations
        c1_tails: set[tuple[str, ...]] = set()
        for _ in range(120):
            order = self.gsc.call(RULES_MOD, "build_shuffled_cycle_order", 1, "").to_list()
            self.assertEqual(len(order), 4)
            self.assertEqual(set(order), all_maps)
            self.assertEqual(order[0], "nazi_zombie_prototype")
            c1_tails.add(tuple(order[1:]))
        self.assertEqual(len(c1_tails), 6, f"Expected all 6 Cycle 1 tail permutations, got {len(c1_tails)}")

        # Cycle 2+ shuffles all 4 maps and NEVER repeats prev_last_map in slot 0
        for prev_last in sorted(all_maps):
            first_seen: set[str] = set()
            for _ in range(80):
                order = self.gsc.call(RULES_MOD, "build_shuffled_cycle_order", 2, prev_last).to_list()
                self.assertEqual(len(order), 4)
                self.assertEqual(set(order), all_maps)
                self.assertNotEqual(order[0], prev_last)
                first_seen.add(order[0])
            self.assertEqual(first_seen, all_maps - {prev_last})

    def test_parse_and_format_cycle_order_validation(self) -> None:
        raw = "nazi_zombie_prototype,nazi_zombie_sumpf,nazi_zombie_factory,nazi_zombie_asylum"
        parsed = self.gsc.call(RULES_MOD, "parse_cycle_order", raw)
        self.assertEqual(
            parsed.to_list(),
            ["nazi_zombie_prototype", "nazi_zombie_sumpf", "nazi_zombie_factory", "nazi_zombie_asylum"],
        )
        self.assertEqual(self.gsc.call(RULES_MOD, "format_cycle_order", parsed), raw)
        # Reject duplicates, missing maps, unknown maps, and empty strings
        self.assertIs(self.gsc.call(RULES_MOD, "parse_cycle_order", ""), UNDEFINED)
        self.assertIs(
            self.gsc.call(RULES_MOD, "parse_cycle_order", "nazi_zombie_prototype,nazi_zombie_prototype,nazi_zombie_sumpf,nazi_zombie_factory"),
            UNDEFINED,
        )
        self.assertIs(
            self.gsc.call(RULES_MOD, "parse_cycle_order", "nazi_zombie_prototype,nazi_zombie_asylum,nazi_zombie_sumpf"),
            UNDEFINED,
        )
        self.assertIs(
            self.gsc.call(RULES_MOD, "parse_cycle_order", "nazi_zombie_prototype,nazi_zombie_asylum,nazi_zombie_sumpf,bogus"),
            UNDEFINED,
        )

    def test_stage_span_rolls_in_four_to_six_and_averages_five(self) -> None:
        self.assertEqual(self.gsc.call(RULES_MOD, "get_min_stage_span"), 4)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_max_stage_span"), 6)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_default_stage_span"), 5)
        rolls = [self.gsc.call(RULES_MOD, "roll_stage_span") for _ in range(180)]
        self.assertEqual(set(rolls), {4, 5, 6})
        mean = sum(rolls) / len(rolls)
        self.assertAlmostEqual(mean, 5.0, delta=0.35)
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_stage_target_round", 1, 4), 4)
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_stage_target_round", 1, 5), 5)
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_stage_target_round", 1, 6), 6)
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_stage_target_round", 11, 5), 15)

    def test_full_three_cycle_stage_walk_and_stage_info_clamping(self) -> None:
        # Walk 12 consecutive Stage Transitions with continuous 5-round spans
        cycle, stage = 1, 1
        order = self.gsc.call(RULES_MOD, "build_shuffled_cycle_order", 1, "")
        completed = 5
        for step in range(12):
            prev_last = order.to_list()[3]
            nxt = self.gsc.call(RULES_MOD, "get_next_stage_state", cycle, stage, order, completed, UNDEFINED, 5)
            self.assertEqual(nxt.start_round, completed + 1)
            self.assertEqual(nxt.target_round, completed + 5)
            self.assertEqual(nxt.prep_duration, 45)
            if stage == 4:
                self.assertTrue(nxt.wrapped_cycle)
                self.assertEqual((nxt.cycle, nxt.stage), (cycle + 1, 1))
                self.assertNotEqual(nxt.map_name, prev_last)
            else:
                self.assertFalse(nxt.wrapped_cycle)
                self.assertEqual((nxt.cycle, nxt.stage), (cycle, stage + 1))
            cycle, stage, order, completed = nxt.cycle, nxt.stage, nxt.cycle_order, nxt.target_round

        # Defensive clamping in get_stage_info
        clamped_low = self.gsc.call(RULES_MOD, "get_stage_info", 0, 0)
        self.assertEqual((clamped_low.cycle, clamped_low.stage, clamped_low.map_name), (1, 1, "nazi_zombie_prototype"))
        clamped_high = self.gsc.call(RULES_MOD, "get_stage_info", 2, 9)
        self.assertEqual((clamped_high.cycle, clamped_high.stage, clamped_high.map_name), (2, 4, "nazi_zombie_factory"))


class TestGauntletRulesRoundBandsAndPrep(unittest.TestCase):
    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)

    def test_default_continuous_round_bands_across_cycles(self) -> None:
        # Default 5-round continuous progression: C1 S1=R1..5, C2 S1=R21..25, C3 S1=R41..45
        expected_cycle_starts = [
            (1, 1, 5),
            (2, 21, 25),
            (3, 41, 45),
            (4, 61, 65),
        ]
        for cycle, exp_start, exp_target in expected_cycle_starts:
            self.assertEqual(self.gsc.call(RULES_MOD, "get_cycle_start_round", cycle), exp_start)
            self.assertEqual(self.gsc.call(RULES_MOD, "get_cycle_target_round", cycle), exp_target)

        # Stage 3 of Cycle 1 defaults to R11..R15 (Prep Phase active since start_round > 1)
        info = self.gsc.call(RULES_MOD, "get_stage_info", 1, 3)
        self.assertEqual((info.cycle, info.stage, info.start_round, info.target_round, info.prep_duration), (1, 3, 11, 15, 45))

    def test_target_round_reached_boundaries(self) -> None:
        self.assertFalse(self.gsc.call(RULES_MOD, "is_target_round_reached", 4, 5))
        self.assertTrue(self.gsc.call(RULES_MOD, "is_target_round_reached", 5, 5))
        self.assertTrue(self.gsc.call(RULES_MOD, "is_target_round_reached", 6, 5))
        self.assertFalse(self.gsc.call(RULES_MOD, "is_target_round_reached", 14, 15))
        self.assertTrue(self.gsc.call(RULES_MOD, "is_target_round_reached", 15, 15))
        self.assertFalse(self.gsc.call(RULES_MOD, "is_target_round_reached", UNDEFINED, 10))

    def test_prep_phase_duration_by_start_round(self) -> None:
        self.assertEqual(self.gsc.call(RULES_MOD, "get_prep_phase_duration", 0), 0)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_prep_phase_duration", 1), 0)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_prep_phase_duration", 2), 45)
        self.assertEqual(self.gsc.call(RULES_MOD, "get_prep_phase_duration", 5), 45)
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

    def test_pre_round_zombie_health_avoids_double_scaling(self) -> None:
        self.assertEqual(self.gsc.call(RULES_MOD, "calculate_pre_round_zombie_health", 1), 150)
        self.assertEqual(self.gsc.call(RULES_MOD, "calculate_pre_round_zombie_health", 2), 150)
        self.assertEqual(self.gsc.call(RULES_MOD, "calculate_pre_round_zombie_health", 10), 950)
        self.assertEqual(self.gsc.call(RULES_MOD, "calculate_pre_round_zombie_health", 15), 1527)
        self.assertEqual(self.gsc.call(RULES_MOD, "calculate_pre_round_zombie_health", 20), 2456)

        # Simulate stock _zombiemode.gsc::ai_calculate_health() for rounds 1..30:
        # applying stock ai_calculate_health() once to pre-round health MUST equal exact round health.
        for round_num in range(1, 31):
            pre = self.gsc.call(RULES_MOD, "calculate_pre_round_zombie_health", round_num)
            expected = self.gsc.call(RULES_MOD, "calculate_zombie_health", round_num)
            if round_num >= 10:
                after_stock_step = pre + int(pre * 0.1)
            elif round_num > 1:
                after_stock_step = int(pre + 100)
            else:
                after_stock_step = pre
            self.assertEqual(
                after_stock_step,
                expected,
                msg=f"Stock ai_calculate_health step mismatch at Round {round_num}",
            )


class TestGauntletRulesHellhounds(unittest.TestCase):
    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)

    def test_map_has_hellhounds(self) -> None:
        self.assertFalse(self.gsc.call(RULES_MOD, "map_has_hellhounds", "nazi_zombie_prototype"))
        self.assertFalse(self.gsc.call(RULES_MOD, "map_has_hellhounds", "nazi_zombie_asylum"))
        self.assertTrue(self.gsc.call(RULES_MOD, "map_has_hellhounds", "nazi_zombie_sumpf"))
        self.assertTrue(self.gsc.call(RULES_MOD, "map_has_hellhounds", "nazi_zombie_factory"))
        self.assertTrue(self.gsc.call(RULES_MOD, "map_has_hellhounds", "NAZI_ZOMBIE_FACTORY"))
        self.assertFalse(self.gsc.call(RULES_MOD, "map_has_hellhounds", "unknown"))
        self.assertFalse(self.gsc.call(RULES_MOD, "map_has_hellhounds", UNDEFINED))

    def test_compute_next_dog_round_relative_to_stage_band(self) -> None:
        # Cycle 2 (rounds 10..15): offset 2..4 schedules rounds 12..14
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_next_dog_round", 10, 15, 2), 12)
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_next_dog_round", 10, 15, 3), 13)
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_next_dog_round", 10, 15, 4), 14)
        # Offset beyond target_round clamps to target_round
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_next_dog_round", 10, 15, 8), 15)
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_next_dog_round", 10, 12, 4), 12)

        # Cycle 3 (rounds 15..20) and Cycle 4 (rounds 20..25)
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_next_dog_round", 15, 20, 2), 17)
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_next_dog_round", 15, 20, 4), 19)
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_next_dog_round", 20, 25, 3), 23)

        # Defensive edges: never schedules on opening start_round itself
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_next_dog_round", 10, 15, 0), 11)
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_next_dog_round", 10, 15, -3), 11)
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_next_dog_round", 10, 10, 2), 12)
        self.assertEqual(self.gsc.call(RULES_MOD, "compute_next_dog_round", 10, UNDEFINED, 3), 13)


if __name__ == "__main__":
    unittest.main()
