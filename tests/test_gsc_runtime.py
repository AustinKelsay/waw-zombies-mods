"""Tests for the WaW 1.7 GSC subset evaluator itself and WaW 1.7 syntax guards."""

from __future__ import annotations

from pathlib import Path
import unittest

from tests.gsc_runtime import GscRuntime, GscSyntaxError, tokenize

MOD_ROOT = Path(__file__).resolve().parent.parent / "mod"


class TestGscRuntimeCompliance(unittest.TestCase):
    def test_rejects_non_waw17_foreach_syntax(self) -> None:
        with self.assertRaises(GscSyntaxError):
            tokenize("foo( arr ) { foreach ( x in arr ) { } }")

    def test_gauntlet_rules_and_state_parse_as_valid_waw17_gsc(self) -> None:
        runtime = GscRuntime(MOD_ROOT)
        rules_funcs = runtime.load_module("maps\\_gauntlet_rules")
        state_funcs = runtime.load_module("maps\\_gauntlet_state")

        self.assertIn("get_next_stage_state", rules_funcs)
        self.assertIn("calculate_zombie_health", rules_funcs)
        self.assertIn("init_fresh_run", state_funcs)
        self.assertIn("resolve_player_starting_points", state_funcs)
        self.assertIn("clear_run_state", state_funcs)


if __name__ == "__main__":
    unittest.main()
