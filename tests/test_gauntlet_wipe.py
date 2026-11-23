"""Offline TDD contract suite for mod/maps/_gauntlet_wipe.gsc and scripts/verify_wipe.py.

Executes the real WaW 1.7 GSC scripts (mod/maps/_gauntlet_wipe.gsc along with
_gauntlet_rules.gsc, _gauntlet_state.gsc, and _gauntlet_log.gsc) through an
extended GscRuntime harness built on tests/gsc_runtime.py, plus unit tests for
scripts/verify_wipe.py's console.log analyzers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Any
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_ROOT = REPO_ROOT / "mod"
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tests.gsc_runtime import (  # noqa: E402
    ExprStmt,
    FakeDvarStore,
    FunctionDef,
    GscRuntime,
    GscRuntimeError,
    GscStruct,
    Parser,
    UNDEFINED,
    _waw_to_str,
    tokenize,
)

WIPE_MOD = "maps\\_gauntlet_wipe"
STATE_MOD = "maps\\_gauntlet_state"
RULES_MOD = "maps\\_gauntlet_rules"


# ---------------------------------------------------------------------------
# Engine-level GSC harness extending tests/gsc_runtime.py for WaW 1.7 HUD /
# level / vector syntax used by _gauntlet_wipe.gsc.
# ---------------------------------------------------------------------------


@dataclass
class VectorLiteral:
    x: Any
    y: Any
    z: Any


@dataclass
class MethodCallExpr:
    receiver: Any
    method: str
    args: list[Any]
    line: int


class FakeHudElem(GscStruct):
    """Tracks HUD element lifecycle and mutations for zero-leak verification."""

    def __init__(self, elem_id: int) -> None:
        super().__init__()
        self._elem_id = elem_id
        self._destroyed = False
        self._texts: list[str] = []
        self._fades: list[float] = []

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    @property
    def texts(self) -> list[str]:
        return list(self._texts)

    @property
    def fades(self) -> list[float]:
        return list(self._fades)


class EngineGscParser(Parser):
    """Extends gsc_runtime.Parser with WaW 1.7 3-vectors and entity method calls."""

    def parse_stmt(self) -> Any:
        tok = self.peek()
        if tok.kind in ("{", "IF", "FOR", "WHILE", "RETURN", "BREAK", "CONTINUE", ";"):
            return super().parse_stmt()
        expr = self.parse_expr()
        if self.peek().kind == "IDENT" and self.peek(1).kind == "(":
            method_tok = self.expect("IDENT")
            args = self.parse_arg_list()
            self.expect(";")
            return ExprStmt(MethodCallExpr(receiver=expr, method=method_tok.value, args=args, line=method_tok.line))
        self.expect(";")
        return ExprStmt(expr)

    def parse_primary(self) -> Any:
        if self.peek().kind == "(":
            self.pos += 1
            first = self.parse_expr()
            if self.match(","):
                second = self.parse_expr()
                self.expect(",")
                third = self.parse_expr()
                self.expect(")")
                return VectorLiteral(first, second, third)
            self.expect(")")
            return first
        return super().parse_primary()


class WipeGscRuntime(GscRuntime):
    """Executes real mod/maps/_gauntlet_*.gsc scripts with fake WaW level & HUD engine."""

    def __init__(
        self,
        mod_root: Path = MOD_ROOT,
        dvars: FakeDvarStore | None = None,
        coop_game: bool = False,
    ) -> None:
        super().__init__(mod_root, dvars)
        self.level = GscStruct()
        self.coop_game = coop_game
        self.created_huds: list[FakeHudElem] = []
        self.notifications: list[str] = []
        self.endons: list[str] = []
        self.waits: list[float] = []
        self.dvar_snapshots_at_wait: list[dict[str, str]] = []
        self.exit_level_calls: list[bool] = []
        self.emitted_events: list[str] = []

    def load_module(self, module_path: str) -> dict[str, FunctionDef]:
        key = self.normalize_module_key(module_path)
        if key not in self._modules:
            gsc_file = self.mod_root / f"{key}.gsc"
            if not gsc_file.is_file():
                raise FileNotFoundError(f"GSC module not found: {gsc_file}")
            source = gsc_file.read_text(encoding="latin1")
            tokens = tokenize(source, filename=str(gsc_file))
            self._modules[key] = EngineGscParser(tokens, filename=str(gsc_file)).parse_module()
        return self._modules[key]

    def call(self, module_path: str, func_name: str, *args: Any) -> Any:
        mod_key = self.normalize_module_key(module_path)
        fn_lower = func_name.lower()

        # Engine / parent seams outside the wipe/rules/state/log modules
        if mod_key == "maps/_utility" and fn_lower == "coopgame":
            return self.coop_game
        if mod_key == "maps/_gauntlet_mode":
            if fn_lower == "is_gauntlet_enabled":
                if self.dvars.get("gauntlet_enabled") == "":
                    self.dvars.set("gauntlet_enabled", "0")
                return self.dvars.get_int("gauntlet_enabled") == 1
            if fn_lower == "get_current_map_name":
                lvl_script = self.level.get_field("script")
                if lvl_script is not UNDEFINED and _waw_to_str(lvl_script) != "":
                    return _waw_to_str(lvl_script).lower()
                return self.dvars.get("mapname").lower()

        return super().call(module_path, func_name, *args)

    def _read_target(self, target: Any, mod_key: str, env: dict[str, Any]) -> Any:
        if hasattr(target, "name") and target.name.lower() == "level" and "level" not in env:
            return self.level
        return super()._read_target(target, mod_key, env)

    def _call_builtin(self, name_lower: str, args: list[Any], line: int) -> tuple[bool, Any]:
        if name_lower == "setuinextlevel":
            if not hasattr(self, "next_level_calls"):
                self.next_level_calls = []
            self.next_level_calls.append(_waw_to_str(args[0]) if args else "")
            return True, UNDEFINED
        if name_lower == "getdvarfloat":
            raw = self.dvars.get(_waw_to_str(args[0])) if args else ""
            try:
                return True, float(raw)
            except ValueError:
                return True, 0.0
        if name_lower == "newhudelem":
            hud = FakeHudElem(len(self.created_huds))
            self.created_huds.append(hud)
            return True, hud
        if name_lower == "wait":
            dur = float(args[0]) if args else 0.0
            self.waits.append(dur)
            self.dvar_snapshots_at_wait.append(self.dvars.snapshot())
            return True, UNDEFINED
        if name_lower == "exitlevel":
            save = bool(args[0]) if args else False
            self.exit_level_calls.append(save)
            return True, UNDEFINED
        if name_lower == "println":
            msg = _waw_to_str(args[0]) if args else ""
            if msg.startswith("GAUNTLET_EVENT|"):
                self.emitted_events.append(msg)
            return True, UNDEFINED
        return super()._call_builtin(name_lower, args, line)

    def _eval_expr(self, expr: Any, mod_key: str, env: dict[str, Any]) -> Any:
        if isinstance(expr, VectorLiteral):
            return (
                self._eval_expr(expr.x, mod_key, env),
                self._eval_expr(expr.y, mod_key, env),
                self._eval_expr(expr.z, mod_key, env),
            )
        if isinstance(expr, MethodCallExpr):
            recv = self._eval_expr(expr.receiver, mod_key, env)
            eval_args = [self._eval_expr(a, mod_key, env) for a in expr.args]
            method = expr.method.lower()
            if recv is self.level:
                if method == "notify":
                    self.notifications.append(_waw_to_str(eval_args[0]))
                    return UNDEFINED
                if method == "endon":
                    self.endons.append(_waw_to_str(eval_args[0]))
                    return UNDEFINED
            if isinstance(recv, FakeHudElem):
                if method == "settext":
                    if recv.destroyed:
                        raise GscRuntimeError(f"line {expr.line}: SetText called on destroyed HUD elem")
                    recv._texts.append(_waw_to_str(eval_args[0]))
                    return UNDEFINED
                if method == "fadeovertime":
                    if recv.destroyed:
                        raise GscRuntimeError(f"line {expr.line}: FadeOverTime called on destroyed HUD elem")
                    recv._fades.append(float(eval_args[0]))
                    return UNDEFINED
                if method == "destroy":
                    if recv.destroyed:
                        raise GscRuntimeError(f"line {expr.line}: Destroy called twice on HUD elem")
                    recv._destroyed = True
                    return UNDEFINED
            raise GscRuntimeError(f"line {expr.line}: unsupported method {expr.method!r} on {recv!r}")
        if hasattr(expr, "name") and expr.__class__.__name__ == "VarRef" and expr.name.lower() == "level":
            return self.level
        return super()._eval_expr(expr, mod_key, env)


# ---------------------------------------------------------------------------
# GSC Contract Tests for mod/maps/_gauntlet_wipe.gsc
# ---------------------------------------------------------------------------


class TestGauntletWipeGsc(unittest.TestCase):
    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = WipeGscRuntime(MOD_ROOT, self.dvars)

    def test_no_foreach_in_gauntlet_wipe_gsc(self) -> None:
        wipe_path = MOD_ROOT / "maps" / "_gauntlet_wipe.gsc"
        self.assertTrue(wipe_path.is_file(), f"Missing {wipe_path}")
        source = wipe_path.read_text(encoding="latin1")
        code_only = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
        self.assertIsNone(re.search(r"\bforeach\b", code_only))
        # Also verify gsc_runtime.tokenize accepts the full file cleanly
        tokens = tokenize(source, filename=str(wipe_path))
        self.assertGreater(len(tokens), 10)

    def test_build_wipe_summary_cycle1_round1_zero_cleared(self) -> None:
        state = GscStruct()
        state.set_field("cycle", 1)
        state.set_field("stage", 1)
        state.set_field("total_rounds", 0)
        state.set_field("run_id", "run_c1r1")
        stage_info = self.gsc.call(RULES_MOD, "get_stage_info", 1, 1)

        summary = self.gsc.call(WIPE_MOD, "build_wipe_summary", state, stage_info, 1, "nazi_zombie_prototype")
        self.assertEqual(summary.final_cycle, 1)
        self.assertEqual(summary.final_stage, 1)
        self.assertEqual(summary.map_name, "nazi_zombie_prototype")
        self.assertEqual(summary.display_name, "Nacht der Untoten")
        self.assertEqual(summary.final_round, 1)
        self.assertEqual(summary.total_rounds_cleared, 0)
        self.assertEqual(summary.title_line, "RUN OVER - TEAM WIPE")
        self.assertEqual(summary.stage_line, "Final Cycle: 1 | Stage: 1/4 (Nacht der Untoten)")
        self.assertEqual(summary.round_line, "Final Round Reached: 1")
        self.assertEqual(summary.total_line, "Total Rounds Cleared: 0")

    def test_build_wipe_summary_cycle1_round5_four_cleared(self) -> None:
        state = GscStruct()
        state.set_field("cycle", 1)
        state.set_field("stage", 1)
        state.set_field("total_rounds", 0)
        state.set_field("run_id", "run_c1r5")
        stage_info = self.gsc.call(RULES_MOD, "get_stage_info", 1, 1)

        summary = self.gsc.call(WIPE_MOD, "build_wipe_summary", state, stage_info, 5, "nazi_zombie_prototype")
        self.assertEqual(summary.final_cycle, 1)
        self.assertEqual(summary.final_stage, 1)
        self.assertEqual(summary.final_round, 5)
        self.assertEqual(summary.total_rounds_cleared, 4)
        self.assertEqual(summary.round_line, "Final Round Reached: 5")
        self.assertEqual(summary.total_line, "Total Rounds Cleared: 4")

    def test_build_wipe_summary_cycle2_stage2_round12_with_prior_45_cleared(self) -> None:
        state = GscStruct()
        state.set_field("cycle", 2)
        state.set_field("stage", 2)
        state.set_field("total_rounds", 45)
        state.set_field("run_id", "run_c2s2")
        stage_info = self.gsc.call(RULES_MOD, "get_stage_info", 2, 2)

        summary = self.gsc.call(WIPE_MOD, "build_wipe_summary", state, stage_info, 12, "nazi_zombie_asylum")
        self.assertEqual(summary.final_cycle, 2)
        self.assertEqual(summary.final_stage, 2)
        self.assertEqual(summary.map_name, "nazi_zombie_asylum")
        self.assertEqual(summary.display_name, "Verruckt")
        self.assertEqual(summary.final_round, 12)
        self.assertEqual(summary.total_rounds_cleared, 47)
        self.assertEqual(summary.title_line, "RUN OVER - TEAM WIPE")
        self.assertEqual(summary.stage_line, "Final Cycle: 2 | Stage: 2/4 (Verruckt)")
        self.assertEqual(summary.round_line, "Final Round Reached: 12")
        self.assertEqual(summary.total_line, "Total Rounds Cleared: 47")

    def test_handle_team_wipe_clears_all_state_and_lobby_dvars_before_overlay_wait(self) -> None:
        # Seed active Cycle 2 Stage 2 Run with saved points and Co-op lobby handoff dvars
        self.dvars.set("gauntlet_enabled", "1")
        self.dvars.set("gauntlet_test_summary_delay", "1.5")
        state = self.gsc.call(STATE_MOD, "init_fresh_run", "run_wipe_777")
        state.set_field("cycle", 2)
        state.set_field("stage", 2)
        state.set_field("total_rounds", 45)
        state.set_field("pending_transition", True)
        state = self.gsc.call(STATE_MOD, "save_run_state", state)
        self.gsc.call(STATE_MOD, "record_player_points", 10001, "Dempsey", 18500)
        self.gsc.call(STATE_MOD, "record_player_points", 0, "Nikolai", 9200)
        self.dvars.set("gauntlet_next_map", "nazi_zombie_sumpf")
        self.dvars.set("gauntlet_next_display", "Shi No Numa")
        self.dvars.set("gauntlet_lobby_status", "Next: Cycle 2 Stage 3 (Shi No Numa)")

        self.gsc.level.set_field("script", "nazi_zombie_asylum")
        self.gsc.level.set_field("round_number", 12)
        self.gsc.level.set_field("gauntlet_state", state)
        self.gsc.level.set_field("gauntlet_stage_info", self.gsc.call(RULES_MOD, "get_stage_info", 2, 2))
        self.gsc.level.set_field("gauntlet_stage_cleared", False)

        handled = self.gsc.call(WIPE_MOD, "handle_team_wipe")
        self.assertTrue(handled)

        # HUD cleanup notification fired
        self.assertIn("gauntlet_run_wipe", self.gsc.notifications)

        # State and ledger were ALREADY wiped BEFORE the first overlay wait()
        self.assertGreaterEqual(len(self.gsc.dvar_snapshots_at_wait), 1)
        snap_before_wait = self.gsc.dvar_snapshots_at_wait[0]
        self.assertEqual(snap_before_wait.get("gauntlet_active"), "0")
        self.assertEqual(snap_before_wait.get("gauntlet_player_points"), "")
        self.assertEqual(snap_before_wait.get("gauntlet_next_map"), "")
        self.assertEqual(snap_before_wait.get("gauntlet_next_display"), "")
        self.assertEqual(snap_before_wait.get("gauntlet_lobby_status"), "")
        self.assertEqual(snap_before_wait.get("gauntlet_pending_transition"), "0")

        # Final dvar store after return: all Run & lobby dvars wiped, mode gate preserved
        self.assertEqual(self.dvars.get("gauntlet_enabled"), "1")
        self.assertEqual(self.dvars.get("gauntlet_active"), "0")
        self.assertEqual(self.dvars.get("gauntlet_run_id"), "")
        self.assertEqual(self.dvars.get("gauntlet_cycle"), "")
        self.assertEqual(self.dvars.get("gauntlet_stage"), "")
        self.assertEqual(self.dvars.get("gauntlet_total_rounds"), "")
        self.assertEqual(self.dvars.get("gauntlet_pending_transition"), "0")
        self.assertEqual(self.dvars.get("gauntlet_player_points"), "")
        self.assertEqual(self.dvars.get("gauntlet_next_map"), "")
        self.assertEqual(self.dvars.get("gauntlet_next_display"), "")
        self.assertEqual(self.dvars.get("gauntlet_lobby_status"), "")

        # Structured telemetry assertions
        self.assertIn(
            "GAUNTLET_EVENT|RUN_WIPE|cycle=2;stage=2;map=nazi_zombie_asylum;display=Verruckt;final_round=12;total_rounds=47;run_id=run_wipe_777",
            self.gsc.emitted_events,
        )
        self.assertIn(
            "GAUNTLET_EVENT|RUN_RESET|run_id=run_wipe_777;active=0;ledger_cleared=1;perks_cleared=1;handoff_cleared=1",
            self.gsc.emitted_events,
        )
        self.assertIn(
            "GAUNTLET_EVENT|RUN_SUMMARY|cycle=2;stage=2;map=nazi_zombie_asylum;display=Verruckt;final_round=12;total_rounds=47",
            self.gsc.emitted_events,
        )
        # RUN_WIPE -> RUN_RESET -> RUN_SUMMARY ordering
        idx_wipe = next(i for i, e in enumerate(self.gsc.emitted_events) if e.startswith("GAUNTLET_EVENT|RUN_WIPE|"))
        idx_reset = next(i for i, e in enumerate(self.gsc.emitted_events) if e.startswith("GAUNTLET_EVENT|RUN_RESET|"))
        idx_summary = next(i for i, e in enumerate(self.gsc.emitted_events) if e.startswith("GAUNTLET_EVENT|RUN_SUMMARY|"))
        self.assertLess(idx_wipe, idx_reset)
        self.assertLess(idx_reset, idx_summary)

        # HUD lifecycle: 4 lines created with exact text, and every single one destroyed cleanly
        self.assertEqual(len(self.gsc.created_huds), 4)
        rendered_texts = [h.texts[-1] for h in self.gsc.created_huds]
        self.assertEqual(
            rendered_texts,
            [
                "RUN OVER - TEAM WIPE",
                "Final Cycle: 2 | Stage: 2/4 (Verruckt)",
                "Final Round Reached: 12",
                "Total Rounds Cleared: 47",
            ],
        )
        leaked = [h for h in self.gsc.created_huds if not h.destroyed]
        self.assertEqual(leaked, [], "All Run Summary HUD elements must be destroyed cleanly")

        # Clean exitLevel(false)
        self.assertEqual(self.gsc.exit_level_calls, [False])

    def test_fresh_run_immediately_after_wipe_starts_cycle1_stage1_round1_with_500_points(self) -> None:
        # Run a Cycle 2 Stage 2 wipe with wealthy saved players
        self.dvars.set("gauntlet_enabled", "1")
        self.dvars.set("gauntlet_test_summary_delay", "0.5")
        state = self.gsc.call(STATE_MOD, "init_fresh_run", "run_old")
        state.set_field("cycle", 2)
        state.set_field("stage", 2)
        state.set_field("total_rounds", 45)
        state = self.gsc.call(STATE_MOD, "save_run_state", state)
        self.gsc.call(STATE_MOD, "record_player_points", 10001, "Dempsey", 25000)
        self.gsc.call(STATE_MOD, "record_player_points", 0, "SoloHost", 14000)

        self.gsc.level.set_field("script", "nazi_zombie_asylum")
        self.gsc.level.set_field("round_number", 12)
        self.gsc.level.set_field("gauntlet_state", state)
        self.gsc.level.set_field("gauntlet_stage_info", self.gsc.call(RULES_MOD, "get_stage_info", 2, 2))
        self.gsc.call(WIPE_MOD, "handle_team_wipe")

        # Reload persisted state -> inactive
        after_wipe = self.gsc.call(STATE_MOD, "load_run_state")
        self.assertFalse(after_wipe.active)
        self.assertIs(self.gsc.call(STATE_MOD, "get_recorded_player_points", 10001, "Dempsey"), UNDEFINED)
        self.assertIs(self.gsc.call(STATE_MOD, "get_recorded_player_points", 0, "SoloHost"), UNDEFINED)

        # Start fresh Run immediately on Nacht der Untoten
        fresh = self.gsc.call(STATE_MOD, "init_fresh_run", "run_new_after_wipe")
        fresh_info = self.gsc.call(RULES_MOD, "get_stage_info", fresh.cycle, fresh.stage)
        self.assertTrue(fresh.active)
        self.assertEqual(fresh.cycle, 1)
        self.assertEqual(fresh.stage, 1)
        self.assertEqual(fresh.total_rounds, 0)
        self.assertEqual(fresh_info.map_name, "nazi_zombie_prototype")
        self.assertEqual(fresh_info.start_round, 1)
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 10001, "Dempsey", fresh_info.start_round),
            500,
        )
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 0, "SoloHost", fresh_info.start_round),
            500,
        )

    def test_coop_wipe_exits_to_lobby_cleanly(self) -> None:
        self.gsc.coop_game = True
        self.dvars.set("gauntlet_enabled", "1")
        self.dvars.set("gauntlet_test_summary_delay", "0.5")
        state = self.gsc.call(STATE_MOD, "init_fresh_run", "coop_run_1")
        self.gsc.level.set_field("script", "nazi_zombie_asylum")
        self.gsc.level.set_field("round_number", 4)
        self.gsc.level.set_field("gauntlet_state", state)
        self.gsc.level.set_field("gauntlet_stage_info", self.gsc.call(RULES_MOD, "get_stage_info", 1, 2))

        self.assertTrue(self.gsc.call(WIPE_MOD, "handle_team_wipe"))
        self.assertEqual(getattr(self.gsc, "next_level_calls", []), ["nazi_zombie_prototype"])
        self.assertEqual(self.gsc.exit_level_calls, [False])
        self.assertEqual(len(self.gsc.created_huds), 4)
        self.assertTrue(all(h.destroyed for h in self.gsc.created_huds))

    def test_double_trigger_guard_prevents_duplicate_wipe(self) -> None:
        self.dvars.set("gauntlet_enabled", "1")
        self.dvars.set("gauntlet_test_summary_delay", "0.5")
        state = self.gsc.call(STATE_MOD, "init_fresh_run", "run_once")
        self.gsc.level.set_field("script", "nazi_zombie_prototype")
        self.gsc.level.set_field("round_number", 3)
        self.gsc.level.set_field("gauntlet_state", state)
        self.gsc.level.set_field("gauntlet_stage_info", self.gsc.call(RULES_MOD, "get_stage_info", 1, 1))

        self.assertTrue(self.gsc.call(WIPE_MOD, "handle_team_wipe"))
        events_after_first = list(self.gsc.emitted_events)
        huds_after_first = len(self.gsc.created_huds)

        # Second call must be a clean no-op returning True
        self.assertTrue(self.gsc.call(WIPE_MOD, "handle_team_wipe"))
        self.assertEqual(self.gsc.emitted_events, events_after_first)
        self.assertEqual(len(self.gsc.created_huds), huds_after_first)
        self.assertEqual(self.gsc.exit_level_calls, [False])

    def test_stage_clear_collision_guard_skips_wipe_and_preserves_state(self) -> None:
        self.dvars.set("gauntlet_enabled", "1")
        state = self.gsc.call(STATE_MOD, "init_fresh_run", "run_transitioning")
        self.gsc.call(STATE_MOD, "record_player_points", 5555, "Survivor", 11200)
        advanced = self.gsc.call(STATE_MOD, "advance_run_state", state, 10)

        self.gsc.level.set_field("script", "nazi_zombie_prototype")
        self.gsc.level.set_field("round_number", 10)
        self.gsc.level.set_field("gauntlet_state", advanced)
        self.gsc.level.set_field("gauntlet_stage_info", self.gsc.call(RULES_MOD, "get_stage_info", 1, 1))
        self.gsc.level.set_field("gauntlet_stage_cleared", True)

        self.assertTrue(self.gsc.call(WIPE_MOD, "handle_team_wipe"))
        self.assertEqual(self.gsc.emitted_events, [])
        self.assertEqual(self.gsc.created_huds, [])
        self.assertEqual(self.gsc.exit_level_calls, [])
        # Persisted state & player points remain intact for the upcoming Stage Transition
        self.assertEqual(self.dvars.get("gauntlet_active"), "1")
        self.assertEqual(self.dvars.get("gauntlet_stage"), "2")
        self.assertEqual(
            self.gsc.call(STATE_MOD, "get_recorded_player_points", 5555, "Survivor"),
            11200,
        )

    def test_classic_mode_disabled_returns_false_without_side_effects(self) -> None:
        self.dvars.set("gauntlet_enabled", "0")
        self.gsc.level.set_field("script", "nazi_zombie_prototype")
        self.gsc.level.set_field("round_number", 7)

        self.assertFalse(self.gsc.call(WIPE_MOD, "handle_team_wipe"))
        self.assertEqual(self.gsc.emitted_events, [])
        self.assertEqual(self.gsc.created_huds, [])
        self.assertEqual(self.gsc.notifications, [])
        self.assertEqual(self.gsc.exit_level_calls, [])

    def test_resolve_summary_delay_default_and_override(self) -> None:
        self.assertAlmostEqual(self.gsc.call(WIPE_MOD, "resolve_summary_delay"), 6.0)
        self.dvars.set("gauntlet_test_summary_delay", "2.25")
        self.assertAlmostEqual(self.gsc.call(WIPE_MOD, "resolve_summary_delay"), 2.25)
        self.dvars.set("gauntlet_test_summary_delay", "-1")
        self.assertAlmostEqual(self.gsc.call(WIPE_MOD, "resolve_summary_delay"), 6.0)

    def test_maybe_run_test_force_wipe_deterministic_trigger(self) -> None:
        # Disabled by default
        self.assertFalse(self.gsc.call(WIPE_MOD, "maybe_run_test_force_wipe", 1))
        self.assertEqual(self.gsc.notifications, [])

        # Enabled with specific target wipe round 12
        self.dvars.set("gauntlet_test_force_wipe", "1")
        self.dvars.set("gauntlet_test_wipe_round", "12")
        self.assertFalse(self.gsc.call(WIPE_MOD, "maybe_run_test_force_wipe", 10))
        self.assertFalse(self.gsc.call(WIPE_MOD, "maybe_run_test_force_wipe", 11))
        self.assertEqual(self.gsc.notifications, [])

        self.assertTrue(self.gsc.call(WIPE_MOD, "maybe_run_test_force_wipe", 12))
        self.assertEqual(self.gsc.notifications, ["end_game"])

        # Skips if stage already cleared
        self.gsc.notifications.clear()
        self.gsc.level.set_field("gauntlet_stage_cleared", True)
        self.assertFalse(self.gsc.call(WIPE_MOD, "maybe_run_test_force_wipe", 12))
        self.assertEqual(self.gsc.notifications, [])


# ---------------------------------------------------------------------------
# Unit Tests for scripts/verify_wipe.py Log Analyzers
# ---------------------------------------------------------------------------


class TestVerifyWipeLogAnalyzers(unittest.TestCase):
    def setUp(self) -> None:
        import verify_wipe  # noqa: E402

        self.verify_wipe = verify_wipe

    def _valid_wipe_log(self) -> str:
        lines = [
            "Loading fastfile 'mod'",
            "dvar set gauntlet_event GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_asylum;gauntlet_enabled=1",
            "dvar set gauntlet_event GAUNTLET_EVENT|GAUNTLET_READY|map=nazi_zombie_asylum",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=2;stage=2;map=nazi_zombie_asylum;start_round=10;target_round=15;run_id=verify_wipe_c2s2",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=12500;start_round=10;map=nazi_zombie_asylum;carried=12500;floor=5000",
            "dvar set gauntlet_event GAUNTLET_EVENT|HIGH_ROUND_APPLIED|cycle=2;stage=2;map=nazi_zombie_asylum;start_round=10;zombie_health=1045;zombie_move_speed=80;spawn_delay=1.2605;next_dog_round=none",
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_START|cycle=2;stage=2;map=nazi_zombie_asylum;duration=2",
            "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_END|cycle=2;stage=2;map=nazi_zombie_asylum;duration=2",
            "dvar set gauntlet_event GAUNTLET_EVENT|RUN_WIPE|cycle=2;stage=2;map=nazi_zombie_asylum;display=Verruckt;final_round=12;total_rounds=47;run_id=verify_wipe_c2s2",
            "dvar set gauntlet_event GAUNTLET_EVENT|RUN_RESET|run_id=verify_wipe_c2s2;active=0;ledger_cleared=1;perks_cleared=1;handoff_cleared=1",
            "dvar set gauntlet_event GAUNTLET_EVENT|RUN_SUMMARY|cycle=2;stage=2;map=nazi_zombie_asylum;display=Verruckt;final_round=12;total_rounds=47",
        ]
        return "\n".join(lines) + "\n"

    def _valid_post_wipe_fresh_run_log(self) -> str:
        lines = [
            "Loading fastfile 'mod'",
            "dvar set gauntlet_event GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_prototype;gauntlet_enabled=1",
            "dvar set gauntlet_event GAUNTLET_EVENT|GAUNTLET_READY|map=nazi_zombie_prototype",
            "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=1;stage=1;map=nazi_zombie_prototype;start_round=1;target_round=10;run_id=run_90210",
            "dvar set gauntlet_event GAUNTLET_EVENT|POINTS_APPLIED|player=n_player;points=500;start_round=1;map=nazi_zombie_prototype;carried=none;floor=500",
        ]
        return "\n".join(lines) + "\n"

    def _valid_classic_gameover_log(self) -> str:
        lines = [
            "Loading fastfile 'mod'",
            "dvar set gauntlet_event GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_prototype;gauntlet_enabled=0",
        ]
        return "\n".join(lines) + "\n"

    def test_analyze_wipe_log_valid_passes(self) -> None:
        _, errors = self.verify_wipe.analyze_wipe_log(
            self._valid_wipe_log(),
            expected_cycle=2,
            expected_stage=2,
            expected_map="nazi_zombie_asylum",
            expected_display="Verruckt",
            expected_final_round=12,
            expected_total_rounds=47,
            expected_run_id="verify_wipe_c2s2",
        )
        self.assertEqual(errors, [])

    def test_analyze_wipe_log_negative_cases(self) -> None:
        # Wrong total_rounds
        bad_total = self._valid_wipe_log().replace("total_rounds=47", "total_rounds=45")
        _, errs = self.verify_wipe.analyze_wipe_log(
            bad_total, 2, 2, "nazi_zombie_asylum", "Verruckt", 12, 47
        )
        self.assertTrue(any("total_rounds" in e for e in errs))

        # Missing RUN_RESET
        no_reset = "\n".join(
            l for l in self._valid_wipe_log().splitlines() if "RUN_RESET" not in l
        )
        _, errs = self.verify_wipe.analyze_wipe_log(
            no_reset, 2, 2, "nazi_zombie_asylum", "Verruckt", 12, 47
        )
        self.assertTrue(any("RUN_RESET" in e for e in errs))

        # RUN_RESET reports ledger_cleared=0
        dirty_ledger = self._valid_wipe_log().replace("ledger_cleared=1", "ledger_cleared=0")
        _, errs = self.verify_wipe.analyze_wipe_log(
            dirty_ledger, 2, 2, "nazi_zombie_asylum", "Verruckt", 12, 47
        )
        self.assertTrue(any("ledger_cleared" in e for e in errs))

        # Duplicate RUN_WIPE event
        dup_wipe = self._valid_wipe_log() + (
            "dvar set gauntlet_event GAUNTLET_EVENT|RUN_WIPE|cycle=2;stage=2;map=nazi_zombie_asylum;"
            "display=Verruckt;final_round=12;total_rounds=47;run_id=verify_wipe_c2s2\n"
        )
        _, errs = self.verify_wipe.analyze_wipe_log(
            dup_wipe, 2, 2, "nazi_zombie_asylum", "Verruckt", 12, 47
        )
        self.assertTrue(any("duplicate" in e.lower() or "expected 1" in e.lower() for e in errs))

        # Fatal script runtime error
        fatal_log = self._valid_wipe_log() + "******* script runtime error *******\n"
        _, errs = self.verify_wipe.analyze_wipe_log(
            fatal_log, 2, 2, "nazi_zombie_asylum", "Verruckt", 12, 47
        )
        self.assertTrue(any("Script runtime error" in e for e in errs))

    def test_analyze_post_wipe_fresh_run_log_pass_and_fail(self) -> None:
        _, errors = self.verify_wipe.analyze_post_wipe_fresh_run_log(
            self._valid_post_wipe_fresh_run_log(), prior_run_id="verify_wipe_c2s2"
        )
        self.assertEqual(errors, [])

        # Stale carried points leak fails
        stale_pts = self._valid_post_wipe_fresh_run_log().replace(
            "points=500;start_round=1;map=nazi_zombie_prototype;carried=none;floor=500",
            "points=12500;start_round=1;map=nazi_zombie_prototype;carried=12500;floor=500",
        )
        _, errs = self.verify_wipe.analyze_post_wipe_fresh_run_log(
            stale_pts, prior_run_id="verify_wipe_c2s2"
        )
        self.assertTrue(any("carried" in e or "points" in e for e in errs))

        # Stale cycle=2 fails
        stale_cycle = self._valid_post_wipe_fresh_run_log().replace("cycle=1;", "cycle=2;")
        _, errs = self.verify_wipe.analyze_post_wipe_fresh_run_log(
            stale_cycle, prior_run_id="verify_wipe_c2s2"
        )
        self.assertTrue(any("cycle" in e for e in errs))

        # Reused prior run_id fails
        reused_id = self._valid_post_wipe_fresh_run_log().replace("run_90210", "verify_wipe_c2s2")
        _, errs = self.verify_wipe.analyze_post_wipe_fresh_run_log(
            reused_id, prior_run_id="verify_wipe_c2s2"
        )
        self.assertTrue(any("run_id" in e for e in errs))

    def test_analyze_classic_gameover_log_pass_and_fail(self) -> None:
        _, errors = self.verify_wipe.analyze_classic_gameover_log(
            self._valid_classic_gameover_log(), expected_map="nazi_zombie_prototype"
        )
        self.assertEqual(errors, [])

        # Any leaked RUN_WIPE / RUN_SUMMARY / RUN_RESET event fails Classic Mode check
        for bad_ev in (
            "GAUNTLET_EVENT|RUN_WIPE|cycle=1;stage=1;map=nazi_zombie_prototype;display=Nacht der Untoten;final_round=3;total_rounds=2;run_id=r1",
            "GAUNTLET_EVENT|RUN_SUMMARY|cycle=1;stage=1;map=nazi_zombie_prototype;display=Nacht der Untoten;final_round=3;total_rounds=2",
            "GAUNTLET_EVENT|RUN_RESET|run_id=r1;active=0;ledger_cleared=1",
        ):
            bad_log = self._valid_classic_gameover_log() + f"dvar set gauntlet_event {bad_ev}\n"
            _, errs = self.verify_wipe.analyze_classic_gameover_log(
                bad_log, expected_map="nazi_zombie_prototype"
            )
            self.assertTrue(len(errs) > 0, f"Expected failure when {bad_ev} leaks into Classic Mode")


if __name__ == "__main__":
    unittest.main()
