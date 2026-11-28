"""Offline unit tests for scripts/verify_coop.py log analyzers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_coop  # noqa: E402


class TestCoopLogAnalyzers(unittest.TestCase):
    def _build_valid_coop_transition_log(self) -> str:
        lines = [
            "Loading fastfile 'mod'",
            "      dvar set gauntlet_active 1",
            "      dvar set gauntlet_run_id run_1234",
            "      dvar set gauntlet_cycle 1",
            "      dvar set gauntlet_stage 1",
            "      dvar set gauntlet_pending_transition 0",
            "      dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=1;stage=1;map=nazi_zombie_prototype;start_round=1;target_round=1;run_id=run_1234",
            "      dvar set gauntlet_event GAUNTLET_EVENT|PLAYER_ROSTER_RESOLVED|player=n_player;role=late_joiner;points=500;carried=none;floor=500;map=nazi_zombie_prototype",
            "      dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=500;start_round=1;map=nazi_zombie_prototype;carried=none;floor=500",
            "      dvar set gauntlet_event GAUNTLET_EVENT|POINTS_SAVED|player=n_player;points=560;map=nazi_zombie_prototype",
            "      dvar set gauntlet_cycle 1",
            "      dvar set gauntlet_stage 2",
            "      dvar set gauntlet_pending_transition 1",
            "      dvar set gauntlet_next_map nazi_zombie_asylum",
            "      dvar set gauntlet_next_display Verruckt",
            "      dvar set gauntlet_lobby_status NEXT STAGE: C1 S2/4 - Verruckt (Starting R2)",
            "      dvar set gauntlet_event GAUNTLET_EVENT|STAGE_CLEAR|cycle=1;stage=1;map=nazi_zombie_prototype;completed_round=1;next_cycle=1;next_stage=2;next_map=nazi_zombie_asylum",
            "      dvar set gauntlet_event GAUNTLET_EVENT|STAGE_TRANSITION|mode=coop;next_map=nazi_zombie_asylum;next_cycle=1;next_stage=2;player_count=1",
            "----- Server Shutdown -----",
            "Loading fastfile 'ui'",
            "      dvar set cl_ingame 0",
        ]
        return "\n".join(lines) + "\n"

    def _build_valid_roster_log(
        self,
        role: str,
        points: int,
        carried: str,
    ) -> str:
        lines = [
            "Loading fastfile 'mod'",
            "      dvar set gauntlet_pending_transition 0",
            "      dvar set gauntlet_next_map ",
            "      dvar set gauntlet_lobby_status ",
            "      dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=2;stage=2;map=nazi_zombie_asylum;start_round=10;target_round=15;run_id=coop_roster_test",
            f"      dvar set gauntlet_event GAUNTLET_EVENT|PLAYER_ROSTER_RESOLVED|player=n_player;role={role};points={points};carried={carried};floor=5000;map=nazi_zombie_asylum",
            f"      dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points={points};start_round=10;map=nazi_zombie_asylum;carried={carried};floor=5000",
        ]
        return "\n".join(lines) + "\n"

    def _build_valid_stale_reset_log(self, reason: str = "stale_no_pending_transition") -> str:
        lines = [
            "Loading fastfile 'mod'",
            f"      dvar set gauntlet_event GAUNTLET_EVENT|RUN_RESET|reason={reason};prev_cycle=2;prev_stage=3;prev_run_id=stale_run;map=nazi_zombie_prototype",
            "      dvar set gauntlet_active 0",
            "      dvar set gauntlet_next_map ",
            "      dvar set gauntlet_lobby_status ",
            "      dvar set gauntlet_fresh_run 0",
            "      dvar set gauntlet_active 1",
            "      dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=1;stage=1;map=nazi_zombie_prototype;start_round=1;target_round=10;run_id=run_9999",
            "      dvar set gauntlet_event GAUNTLET_EVENT|PLAYER_ROSTER_RESOLVED|player=n_player;role=late_joiner;points=500;carried=none;floor=500;map=nazi_zombie_prototype",
            "      dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=500;start_round=1;map=nazi_zombie_prototype;carried=none;floor=500",
        ]
        return "\n".join(lines) + "\n"

    def test_valid_coop_transition_passes(self) -> None:
        _, errors = verify_coop.analyze_coop_stage_clear_log(
            self._build_valid_coop_transition_log()
        )
        self.assertEqual(errors, [])

    def test_coop_transition_rejects_solo_mode_or_changelevel_load(self) -> None:
        solo_mode = self._build_valid_coop_transition_log().replace(
            "mode=coop;", "mode=solo;"
        )
        _, errors = verify_coop.analyze_coop_stage_clear_log(solo_mode)
        self.assertTrue(any("mode" in err for err in errors))

        leaked_changelevel = (
            self._build_valid_coop_transition_log()
            + "Loading fastfile 'nazi_zombie_asylum'\n"
        )
        _, errors = verify_coop.analyze_coop_stage_clear_log(leaked_changelevel)
        self.assertTrue(any("ChangeLevel" in err for err in errors))

    def test_coop_transition_requires_lobby_handoff_dvars(self) -> None:
        missing_status = self._build_valid_coop_transition_log().replace(
            "      dvar set gauntlet_lobby_status NEXT STAGE: C1 S2/4 - Verruckt (Starting R2)\n",
            "",
        )
        _, errors = verify_coop.analyze_coop_stage_clear_log(missing_status)
        self.assertTrue(any("gauntlet_lobby_status" in err for err in errors))

    def test_roster_recovery_analyzers_all_four_roles(self) -> None:
        cases = (
            ("returning", 12400, "12400"),
            ("spectator", 5000, "0"),
            ("late_joiner", 5000, "none"),
            ("reconnecting", 8750, "8750"),
        )
        for role, pts, carried in cases:
            log = self._build_valid_roster_log(role=role, points=pts, carried=carried)
            _, errors = verify_coop.analyze_roster_recovery_log(
                log,
                expected_role=role,
                expected_points=pts,
                expected_carried=carried,
                expected_floor=5000,
            )
            self.assertEqual(errors, [], f"Failed for role={role}: {errors}")

        # Wrong role fails
        bad_role = self._build_valid_roster_log("returning", 5000, "0")
        _, errors = verify_coop.analyze_roster_recovery_log(
            bad_role,
            expected_role="spectator",
            expected_points=5000,
            expected_carried="0",
            expected_floor=5000,
        )
        self.assertTrue(any("role" in err for err in errors))

    def test_stale_reset_analyzer_pass_and_leak_failures(self) -> None:
        _, errors = verify_coop.analyze_stale_reset_log(
            self._build_valid_stale_reset_log("stale_no_pending_transition"),
            expected_reason="stale_no_pending_transition",
            stale_run_id="stale_run",
        )
        self.assertEqual(errors, [])

        _, errors_fresh = verify_coop.analyze_stale_reset_log(
            self._build_valid_stale_reset_log("fresh_run_requested"),
            expected_reason="fresh_run_requested",
            stale_run_id="stale_run",
        )
        self.assertEqual(errors_fresh, [])

        # Leaked stale points fails
        leaked_pts = self._build_valid_stale_reset_log().replace(
            "points=500;carried=none", "points=25000;carried=25000"
        )
        _, errors = verify_coop.analyze_stale_reset_log(
            leaked_pts,
            expected_reason="stale_no_pending_transition",
            stale_run_id="stale_run",
        )
        self.assertTrue(any("500" in err for err in errors))


if __name__ == "__main__":
    unittest.main()
