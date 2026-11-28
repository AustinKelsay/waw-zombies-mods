"""Offline unit tests for scripts/verify_cycle2.py log analyzers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_cycle2  # noqa: E402


class TestCycle2LogAnalyzers(unittest.TestCase):
    def _build_valid_c1_to_c2_wrap_log(self) -> str:
        lines = [
            "Loading fastfile 'mod'",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=1;stage=4;map=nazi_zombie_factory;start_round=9;target_round=9;run_id=verify_c1_c2",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=4500;start_round=9;map=nazi_zombie_factory;carried=none;floor=4500",
            "dvar set gauntlet_event GAUNTLET_EVENT|HIGH_ROUND_APPLIED|cycle=1;stage=4;map=nazi_zombie_factory;start_round=9;zombie_health=950;zombie_move_speed=72;spawn_delay=1.3268;next_dog_round=11",
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_START|cycle=1;stage=4;map=nazi_zombie_factory;duration=3",
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_END|cycle=1;stage=4;map=nazi_zombie_factory;duration=3",
            "dvar set gauntlet_event GAUNTLET_EVENT|ZOMBIE_SPAWNED_SAMPLE|round=9;health=950;move_speed=sprint",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_SAVED|player=n_player;points=4560;map=nazi_zombie_factory",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_CLEAR|cycle=1;stage=4;map=nazi_zombie_factory;completed_round=9;next_cycle=2;next_stage=1;next_map=nazi_zombie_prototype",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_TRANSITION|mode=solo;next_map=nazi_zombie_prototype;next_cycle=2;next_stage=1",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=2;stage=1;map=nazi_zombie_prototype;start_round=10;target_round=14;run_id=verify_c1_c2",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=5000;start_round=10;map=nazi_zombie_prototype;carried=4560;floor=5000",
            "dvar set gauntlet_event GAUNTLET_EVENT|HIGH_ROUND_APPLIED|cycle=2;stage=1;map=nazi_zombie_prototype;start_round=10;zombie_health=1045;zombie_move_speed=80;spawn_delay=1.89075;next_dog_round=none",
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_START|cycle=2;stage=1;map=nazi_zombie_prototype;duration=3",
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_END|cycle=2;stage=1;map=nazi_zombie_prototype;duration=3",
            "dvar set gauntlet_event GAUNTLET_EVENT|ZOMBIE_SPAWNED_SAMPLE|round=10;health=1045;move_speed=sprint",
        ]
        return "\n".join(lines) + "\n"

    def _build_valid_surplus_log(self) -> str:
        lines = [
            "Loading fastfile 'mod'",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=2;stage=1;map=nazi_zombie_prototype;start_round=10;target_round=14;run_id=verify_surplus",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=8500;start_round=10;map=nazi_zombie_prototype;carried=8500;floor=5000",
            "dvar set gauntlet_event GAUNTLET_EVENT|HIGH_ROUND_APPLIED|cycle=2;stage=1;map=nazi_zombie_prototype;start_round=10;zombie_health=1045;zombie_move_speed=80;spawn_delay=1.89075;next_dog_round=none",
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_START|cycle=2;stage=1;map=nazi_zombie_prototype;duration=3",
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_END|cycle=2;stage=1;map=nazi_zombie_prototype;duration=3",
            "dvar set gauntlet_event GAUNTLET_EVENT|ZOMBIE_SPAWNED_SAMPLE|round=10;health=1045;move_speed=sprint",
        ]
        return "\n".join(lines) + "\n"

    def _build_valid_c2_to_c3_wrap_log(self) -> str:
        lines = [
            "Loading fastfile 'mod'",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=2;stage=4;map=nazi_zombie_factory;start_round=14;target_round=14;run_id=verify_c2_c3",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=7000;start_round=14;map=nazi_zombie_factory;carried=none;floor=7000",
            "dvar set gauntlet_event GAUNTLET_EVENT|HIGH_ROUND_APPLIED|cycle=2;stage=4;map=nazi_zombie_factory;start_round=14;zombie_health=1527;zombie_move_speed=112;spawn_delay=1.02668;next_dog_round=16",
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_START|cycle=2;stage=4;map=nazi_zombie_factory;duration=3",
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_END|cycle=2;stage=4;map=nazi_zombie_factory;duration=3",
            "dvar set gauntlet_event GAUNTLET_EVENT|ZOMBIE_SPAWNED_SAMPLE|round=14;health=1527;move_speed=sprint",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_SAVED|player=n_player;points=7060;map=nazi_zombie_factory",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_CLEAR|cycle=2;stage=4;map=nazi_zombie_factory;completed_round=14;next_cycle=3;next_stage=1;next_map=nazi_zombie_prototype",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_TRANSITION|mode=solo;next_map=nazi_zombie_prototype;next_cycle=3;next_stage=1",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=3;stage=1;map=nazi_zombie_prototype;start_round=15;target_round=19;run_id=verify_c2_c3",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=7500;start_round=15;map=nazi_zombie_prototype;carried=7060;floor=7500",
            "dvar set gauntlet_event GAUNTLET_EVENT|HIGH_ROUND_APPLIED|cycle=3;stage=1;map=nazi_zombie_prototype;start_round=15;zombie_health=1679;zombie_move_speed=120;spawn_delay=1.46303;next_dog_round=none",
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_START|cycle=3;stage=1;map=nazi_zombie_prototype;duration=3",
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_END|cycle=3;stage=1;map=nazi_zombie_prototype;duration=3",
            "dvar set gauntlet_event GAUNTLET_EVENT|ZOMBIE_SPAWNED_SAMPLE|round=15;health=1679;move_speed=sprint",
        ]
        return "\n".join(lines) + "\n"

    def test_valid_c1_to_c2_wrap_passes(self) -> None:
        _, errors = verify_cycle2.analyze_c1_to_c2_wrap_log(
            self._build_valid_c1_to_c2_wrap_log(), expected_prep_duration=3
        )
        self.assertEqual(errors, [])

    def test_wrap_points_below_floor_fails(self) -> None:
        bad = self._build_valid_c1_to_c2_wrap_log().replace(
            "POINTS_APPLIED|player=n_player;points=5000;start_round=10;map=nazi_zombie_prototype;carried=4560;floor=5000",
            "POINTS_APPLIED|player=n_player;points=4560;start_round=10;map=nazi_zombie_prototype;carried=4560;floor=5000",
        )
        _, errors = verify_cycle2.analyze_c1_to_c2_wrap_log(bad, expected_prep_duration=3)
        self.assertTrue(any("5000" in err for err in errors), errors)

    def test_wrap_missing_points_saved_and_bogus_balance_fail(self) -> None:
        for fn, log in (
            (verify_cycle2.analyze_c1_to_c2_wrap_log, self._build_valid_c1_to_c2_wrap_log()),
            (verify_cycle2.analyze_c2_to_c3_wrap_log, self._build_valid_c2_to_c3_wrap_log()),
        ):
            with self.subTest(fn=fn.__name__):
                missing_saved = "\n".join(l for l in log.splitlines() if "|POINTS_SAVED|" not in l)
                bogus = missing_saved.replace("points=5000;", "points=9999;").replace("points=7500;", "points=9999;")
                _, errors = fn(bogus, expected_prep_duration=3)
                self.assertTrue(any("POINTS_SAVED" in err for err in errors), errors)

                bad_carried = log.replace("carried=4560;", "carried=none;").replace("carried=7060;", "carried=none;")
                _, errors2 = fn(bad_carried, expected_prep_duration=3)
                self.assertTrue(any("carried=" in err for err in errors2), errors2)

    def test_double_scaled_round10_health_fails(self) -> None:
        bad = self._build_valid_c1_to_c2_wrap_log().replace(
            "ZOMBIE_SPAWNED_SAMPLE|round=10;health=1045;move_speed=sprint",
            "ZOMBIE_SPAWNED_SAMPLE|round=10;health=1149;move_speed=sprint",
        )
        _, errors = verify_cycle2.analyze_c1_to_c2_wrap_log(bad, expected_prep_duration=3)
        self.assertTrue(any("1045" in err for err in errors))

    def test_zombie_spawned_before_prep_end_fails(self) -> None:
        bad = self._build_valid_c1_to_c2_wrap_log().replace(
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_END|cycle=2;stage=1;map=nazi_zombie_prototype;duration=3\n"
            "dvar set gauntlet_event GAUNTLET_EVENT|ZOMBIE_SPAWNED_SAMPLE|round=10;health=1045;move_speed=sprint",
            "dvar set gauntlet_event GAUNTLET_EVENT|ZOMBIE_SPAWNED_SAMPLE|round=10;health=1045;move_speed=sprint\n"
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_END|cycle=2;stage=1;map=nazi_zombie_prototype;duration=3",
        )
        _, errors = verify_cycle2.analyze_c1_to_c2_wrap_log(bad, expected_prep_duration=3)
        self.assertTrue(any("PREP_PHASE_END" in err for err in errors))

    def test_missing_prep_phase_on_continuous_cycle1_stage4_fails(self) -> None:
        bad = self._build_valid_c1_to_c2_wrap_log().replace(
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_START|cycle=1;stage=4;map=nazi_zombie_factory;duration=3\n",
            "",
        )
        _, errors = verify_cycle2.analyze_c1_to_c2_wrap_log(bad, expected_prep_duration=3)
        self.assertTrue(any("PREP_PHASE_START" in err for err in errors))

    def test_surplus_preservation_pass_and_overwrite_fail(self) -> None:
        _, errors = verify_cycle2.analyze_surplus_preservation_log(
            self._build_valid_surplus_log(), expected_surplus=8500, expected_prep_duration=3
        )
        self.assertEqual(errors, [])

        bad = self._build_valid_surplus_log().replace(
            "POINTS_APPLIED|player=n_player;points=8500;start_round=10",
            "POINTS_APPLIED|player=n_player;points=5000;start_round=10",
        )
        _, errors = verify_cycle2.analyze_surplus_preservation_log(
            bad, expected_surplus=8500, expected_prep_duration=3
        )
        self.assertTrue(any("8500" in err for err in errors))

    def test_valid_c2_to_c3_wrap_and_dog_round_checks(self) -> None:
        _, errors = verify_cycle2.analyze_c2_to_c3_wrap_log(
            self._build_valid_c2_to_c3_wrap_log(), expected_prep_duration=3
        )
        self.assertEqual(errors, [])

        # Stale stock dog round (< start_round=14) on factory fails
        bad_dogs = self._build_valid_c2_to_c3_wrap_log().replace(
            "next_dog_round=16", "next_dog_round=6"
        )
        _, errors = verify_cycle2.analyze_c2_to_c3_wrap_log(bad_dogs, expected_prep_duration=3)
        self.assertTrue(any("next_dog_round" in err for err in errors))

        # Double-scaled Round 15 zombie health fails
        bad_hp = self._build_valid_c2_to_c3_wrap_log().replace(
            "ZOMBIE_SPAWNED_SAMPLE|round=15;health=1679;move_speed=sprint",
            "ZOMBIE_SPAWNED_SAMPLE|round=15;health=1846;move_speed=sprint",
        )
        _, errors = verify_cycle2.analyze_c2_to_c3_wrap_log(bad_hp, expected_prep_duration=3)
        self.assertTrue(any("1679" in err for err in errors))


if __name__ == "__main__":
    unittest.main()
