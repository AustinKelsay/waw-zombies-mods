"""Offline unit and contract tests for build_mod patching and Cycle 1 verification."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_mod  # noqa: E402
import verify_cycle1  # noqa: E402

SYNTHETIC_MAP_PROTOTYPE = (
    "main()\n"
    "{\n"
    "\tmaps\\_zombiemode::main();\n"
    "}\n"
).encode("latin1")

SYNTHETIC_MAP_FACTORY = (
    "main()\r\n"
    "{\r\n"
    "\tmaps\\_zombiemode::main(\"receiver_zone_spawners\");\r\n"
    "}\r\n"
).encode("latin1")

SYNTHETIC_ZOMBIEMODE = (
    "round_start()\n"
    "{\n"
    "\tlevel.round_number = 1;\n"
    "\tlevel thread round_think();\n"
    "}\n"
    "\n"
    "round_think()\n"
    "{\n"
    "\tfor( ;; )\n"
    "\t{\n"
    "\t\tlevel thread round_spawning();\n"
    "\t\tround_wait();\n"
    "\t\tlevel.round_number++;\n"
    "\t}\n"
    "}\n"
    "\n"
    "round_wait()\n"
    "{\n"
    "\twait( 1 );\n"
    "}\n"
    "\n"
    "end_game()\n"
    "{\n"
    "\tlevel waittill ( \"end_game\" );\n"
    "\tlevel.intermission = true;\n"
    "\tupdate_leaderboards();\n"
    "}\n"
).encode("latin1")


class TestBuildModPatching(unittest.TestCase):
    def test_inject_map_hooks_rewires_no_arg_and_arg_main_calls(self) -> None:
        patched_proto = build_mod.inject_map_hooks(
            SYNTHETIC_MAP_PROTOTYPE, "nazi_zombie_prototype"
        ).decode("latin1")
        self.assertIn("maps\\_gauntlet_bootstrap::pre_zombiemode_init();", patched_proto)
        self.assertIn("maps\\_zombiemode_gauntlet_prototype::main();", patched_proto)
        self.assertIn("level thread maps\\_gauntlet_bootstrap::post_zombiemode_init();", patched_proto)
        self.assertNotIn("maps\\_zombiemode::main(", patched_proto)

        patched_factory = build_mod.inject_map_hooks(
            SYNTHETIC_MAP_FACTORY, "nazi_zombie_factory"
        ).decode("latin1")
        self.assertIn(
            'maps\\_zombiemode_gauntlet_factory::main("receiver_zone_spawners");',
            patched_factory,
        )
        self.assertNotIn("maps\\_zombiemode::main(", patched_factory)

    def test_inject_zombiemode_hooks_gates_all_seams(self) -> None:
        patched = build_mod.inject_zombiemode_hooks(
            SYNTHETIC_ZOMBIEMODE, "nazi_zombie_factory"
        ).decode("latin1")

        # All 4 hooks present and strictly gated behind is_gauntlet_enabled()
        self.assertEqual(patched.count("maps\\_gauntlet_mode::is_gauntlet_enabled()"), 4)
        self.assertEqual(patched.count("maps\\_gauntlet_mode::on_stage_init();"), 1)
        self.assertEqual(
            patched.count("level thread maps\\_gauntlet_mode::on_round_started( level.round_number );"),
            1,
        )
        self.assertEqual(
            patched.count("if ( maps\\_gauntlet_mode::on_round_completed( level.round_number ) )"),
            1,
        )
        self.assertEqual(patched.count("if ( maps\\_gauntlet_mode::on_end_game() )"), 1)

        # Verify ordering: on_stage_init BEFORE round_think, on_round_started BEFORE round_wait,
        # on_round_completed AFTER round_wait and BEFORE level.round_number++
        self.assertLess(
            patched.index("on_stage_init()"),
            patched.index("level thread round_think();"),
        )
        self.assertLess(
            patched.index("on_round_started("),
            patched.index("round_wait();"),
        )
        self.assertLess(
            patched.index("round_wait();"),
            patched.index("on_round_completed("),
        )
        self.assertLess(
            patched.index("on_round_completed("),
            patched.index("level.round_number++;"),
        )
        self.assertLess(
            patched.index("level.intermission = true;"),
            patched.index("on_end_game()"),
        )

    def test_inject_zombiemode_hooks_rejects_malformed_script(self) -> None:
        with self.assertRaises(ValueError):
            build_mod.inject_zombiemode_hooks(b"main() {}\n", "nazi_zombie_prototype")

    def test_real_stock_zombiemode_scripts_patch_cleanly_and_preserve_fov(self) -> None:
        if not build_mod.DEFAULT_STEAM_GAME.is_dir():
            self.skipTest("Stock WaW game files not installed on this host")

        for map_name in build_mod.STOCK_MAPS:
            zm_bytes = build_mod.extract_stock_zombiemode(
                map_name, build_mod.DEFAULT_STEAM_GAME, build_mod.DEFAULT_TOOLS_ROOT
            )
            patched = build_mod.inject_zombiemode_hooks(zm_bytes, map_name).decode("latin1")
            self.assertEqual(patched.count("maps\\_gauntlet_mode::is_gauntlet_enabled()"), 4)
            self.assertIn("maps\\_gauntlet_mode::on_stage_init();", patched)
            self.assertIn("maps\\_gauntlet_mode::on_round_completed( level.round_number )", patched)
            self.assertIn("maps\\_gauntlet_mode::on_end_game()", patched)
            if map_name in ("nazi_zombie_sumpf", "nazi_zombie_factory"):
                self.assertIn("waw_solo_fov()", patched)

    def test_no_foreach_in_tracked_gauntlet_gsc_files(self) -> None:
        gsc_files = sorted((REPO_ROOT / "mod" / "maps").glob("_gauntlet_*.gsc"))
        self.assertGreaterEqual(len(gsc_files), 5)
        foreach_re = re.compile(r"\bforeach\b")
        for gsc_path in gsc_files:
            content = gsc_path.read_text(encoding="latin1")
            # Strip // single-line comments before scanning
            code_only = "\n".join(line.split("//", 1)[0] for line in content.splitlines())
            self.assertIsNone(
                foreach_re.search(code_only),
                f"Forbidden WaW 1.7 keyword 'foreach' found in {gsc_path.name}",
            )


class TestCycle1LogAnalyzer(unittest.TestCase):
    def _build_valid_cycle1_log(self) -> str:
        lines = [
            "Loading fastfile 'mod'",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=1;stage=1;map=nazi_zombie_prototype;start_round=1;target_round=1;run_id=run_100",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=500;start_round=1;map=nazi_zombie_prototype",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_SAVED|player=n_player;points=560;map=nazi_zombie_prototype",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_CLEAR|cycle=1;stage=1;map=nazi_zombie_prototype;completed_round=1;next_cycle=1;next_stage=2;next_map=nazi_zombie_asylum",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_TRANSITION|mode=solo;next_map=nazi_zombie_asylum;next_cycle=1;next_stage=2",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=1;stage=2;map=nazi_zombie_asylum;start_round=1;target_round=1;run_id=run_100",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=560;start_round=1;map=nazi_zombie_asylum",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_SAVED|player=n_player;points=620;map=nazi_zombie_asylum",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_CLEAR|cycle=1;stage=2;map=nazi_zombie_asylum;completed_round=1;next_cycle=1;next_stage=3;next_map=nazi_zombie_sumpf",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_TRANSITION|mode=solo;next_map=nazi_zombie_sumpf;next_cycle=1;next_stage=3",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=1;stage=3;map=nazi_zombie_sumpf;start_round=1;target_round=1;run_id=run_100",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=620;start_round=1;map=nazi_zombie_sumpf",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_SAVED|player=n_player;points=680;map=nazi_zombie_sumpf",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_CLEAR|cycle=1;stage=3;map=nazi_zombie_sumpf;completed_round=1;next_cycle=1;next_stage=4;next_map=nazi_zombie_factory",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_TRANSITION|mode=solo;next_map=nazi_zombie_factory;next_cycle=1;next_stage=4",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=1;stage=4;map=nazi_zombie_factory;start_round=1;target_round=1;run_id=run_100",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=680;start_round=1;map=nazi_zombie_factory",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_SAVED|player=n_player;points=740;map=nazi_zombie_factory",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_CLEAR|cycle=1;stage=4;map=nazi_zombie_factory;completed_round=1;next_cycle=2;next_stage=1;next_map=nazi_zombie_prototype",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_TRANSITION|mode=solo;next_map=nazi_zombie_prototype;next_cycle=2;next_stage=1",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=2;stage=1;map=nazi_zombie_prototype;start_round=10;target_round=1;run_id=run_100",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=5000;start_round=10;map=nazi_zombie_prototype",
        ]
        return "\n".join(lines) + "\n"

    def test_valid_cycle1_log_passes(self) -> None:
        log = self._build_valid_cycle1_log()
        events, errors = verify_cycle1.analyze_cycle1_log(log, expected_target_round=1)
        self.assertEqual(errors, [])
        self.assertTrue(verify_cycle1.is_cycle1_complete(events))

    def test_broken_points_carryover_fails(self) -> None:
        log = self._build_valid_cycle1_log().replace(
            "POINTS_APPLIED|player=n_player;points=560;start_round=1;map=nazi_zombie_asylum",
            "POINTS_APPLIED|player=n_player;points=500;start_round=1;map=nazi_zombie_asylum",
        )
        _, errors = verify_cycle1.analyze_cycle1_log(log, expected_target_round=1)
        self.assertTrue(any("Points carryover mismatch" in err for err in errors))

    def test_fatal_script_error_fails(self) -> None:
        log = self._build_valid_cycle1_log() + "******* script runtime error *******\n"
        _, errors = verify_cycle1.analyze_cycle1_log(log, expected_target_round=1)
        self.assertTrue(any("Script runtime error" in err for err in errors))


if __name__ == "__main__":
    unittest.main()
