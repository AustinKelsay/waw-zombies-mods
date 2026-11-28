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
                dogs_bytes = build_mod.extract_stock_script(
                    map_name,
                    "maps/_zombiemode_dogs.gsc",
                    build_mod.DEFAULT_STEAM_GAME,
                    build_mod.DEFAULT_TOOLS_ROOT,
                )
                dogs_patched = build_mod.inject_zombiemode_dogs_hooks(dogs_bytes).decode("latin1")
                self.assertIn(".bz_spawning_dog = true;", dogs_patched)
                self.assertIn(".bz_spawning_dog = false;", dogs_patched)

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
    def _build_valid_cycle1_log(self, span: int = 1) -> str:
        seq = verify_cycle1.expected_cycle1_sequence(span)
        lines = ["Loading fastfile 'mod'"]
        prev_saved = 0
        for idx, (c, s, m, sr, tr) in enumerate(seq):
            lines.append(
                f"dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle={c};stage={s};map={m};start_round={sr};target_round={tr};run_id=run_100"
            )
            floor_pts = max(500, sr * 500)
            applied = 500 if idx == 0 else max(prev_saved, floor_pts)
            carried = "none" if idx == 0 else str(prev_saved)
            lines.append(
                f"dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points={applied};start_round={sr};map={m};carried={carried};floor={floor_pts}"
            )
            if sr > 1:
                lines.append(
                    f"dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_START|cycle={c};stage={s};map={m};duration=1"
                )
                lines.append(
                    f"dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_END|cycle={c};stage={s};map={m};duration=1"
                )
            if idx < 4:
                prev_saved = applied + 620
                nc, ns, nm, _, _ = seq[idx + 1]
                lines.append(
                    f"dvar set gauntlet_event GAUNTLET_EVENT|POINTS_SAVED|player=n_player;points={prev_saved};map={m}"
                )
                lines.append(
                    f"dvar set gauntlet_event GAUNTLET_EVENT|STAGE_CLEAR|cycle={c};stage={s};map={m};completed_round={tr};next_cycle={nc};next_stage={ns};next_map={nm}"
                )
                lines.append(
                    f"dvar set gauntlet_event GAUNTLET_EVENT|STAGE_TRANSITION|mode=solo;next_map={nm};next_cycle={nc};next_stage={ns}"
                )
        return "\n".join(lines) + "\n"

    def test_valid_cycle1_log_passes(self) -> None:
        for span in (1, 2):
            with self.subTest(span=span):
                log = self._build_valid_cycle1_log(span=span)
                events, errors = verify_cycle1.analyze_cycle1_log(log, expected_stage_span=span)
                self.assertEqual(errors, [])
                self.assertTrue(verify_cycle1.is_cycle1_complete(events, expected_stage_span=span))

    def test_missing_prep_phase_on_stage2_fails(self) -> None:
        log = self._build_valid_cycle1_log().replace(
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_START|cycle=1;stage=2;map=nazi_zombie_sumpf;duration=1\n",
            "",
        )
        _, errors = verify_cycle1.analyze_cycle1_log(log, expected_stage_span=1)
        self.assertTrue(any("Prep Phase" in err for err in errors), errors)

    def test_broken_points_carryover_fails(self) -> None:
        log = self._build_valid_cycle1_log().replace(
            "POINTS_APPLIED|player=n_player;points=1740;start_round=3;map=nazi_zombie_asylum",
            "POINTS_APPLIED|player=n_player;points=1500;start_round=3;map=nazi_zombie_asylum",
        )
        _, errors = verify_cycle1.analyze_cycle1_log(log, expected_stage_span=1)
        self.assertTrue(any("Points carryover mismatch" in err for err in errors))

    def test_lost_carryover_masked_by_floor_fails(self) -> None:
        log = self._build_valid_cycle1_log().replace(";carried=1120;", ";carried=none;")
        _, errors = verify_cycle1.analyze_cycle1_log(log, expected_stage_span=1)
        self.assertTrue(any("carried mismatch" in err for err in errors), errors)

    def test_fatal_script_error_fails(self) -> None:
        log = self._build_valid_cycle1_log() + "******* script runtime error *******\n"
        _, errors = verify_cycle1.analyze_cycle1_log(log, expected_stage_span=1)
        self.assertTrue(any("Script runtime error" in err for err in errors))


if __name__ == "__main__":
    unittest.main()
