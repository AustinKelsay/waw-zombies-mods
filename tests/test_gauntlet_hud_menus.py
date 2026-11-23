"""Offline TDD contract suite for Ticket #8: Gauntlet HUD overlay and Solo / Co-op menus.

Tests:
  1. Real WaW 1.7 GSC execution of mod/maps/_gauntlet_hud.gsc via an extended
     GscRuntime (built on tests/gsc_runtime.py) with fake NewHudElem(), level
     struct, and notify/waittill/endon thread scheduling.
  2. Authentic WaW 1.7 menu syntax, brace balance, dvar-action contracts, and
     build-time stock menu patchers in mod/ui/ and scripts/verify_hud_menus.py.
  3. In-engine console.log HUD analyzers (both passing and failing cases) in
     scripts/verify_hud_menus.py.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    ArrayLiteral,
    AssignExpr,
    BinaryExpr,
    BlockStmt,
    BreakStmt,
    CallExpr,
    ContinueStmt,
    ExprStmt,
    FakeDvarStore,
    FieldAccess,
    ForStmt,
    FunctionDef,
    GscArray,
    GscRuntime,
    GscRuntimeError,
    GscStruct,
    GscSyntaxError,
    IfStmt,
    IndexAccess,
    Literal,
    Parser,
    PostfixUpdateExpr,
    ReturnStmt,
    Token,
    UNDEFINED,
    UnaryExpr,
    VarRef,
    WhileStmt,
    _waw_to_str,
    _waw_truthy,
    tokenize,
)

HUD_MOD = "maps\\_gauntlet_hud"
HUD_GSC_PATH = MOD_ROOT / "maps" / "_gauntlet_hud.gsc"


# ---------------------------------------------------------------------------
# Extended GSC Parser & Runtime (built on tests/gsc_runtime.py) supporting
# WaW 1.7 entity methods, level global, vector literals, NewHudElem(), and
# threaded endon/waittill/notify lifecycle execution without modifying
# tests/gsc_runtime.py.
# ---------------------------------------------------------------------------


@dataclass
class VectorLiteral:
    elements: list[Any]


@dataclass
class MethodCallExpr:
    receiver: Any
    method_name: str
    args: list[Any]
    threaded: bool
    line: int


@dataclass
class ThreadCallExpr:
    module_path: str | None
    func_name: str
    args: list[Any]
    line: int


class _EndonSignal(Exception):
    pass


class _WaittillSuspend(Exception):
    def __init__(self, receiver: Any, event_name: str, out_var: str | None) -> None:
        self.receiver = receiver
        self.event_name = event_name
        self.out_var = out_var


class FakeHudElem(GscStruct):
    """Tracks HUD element properties, SetText history, and Destroy() state."""

    def __init__(self, elem_id: int) -> None:
        super().__init__()
        self.elem_id = elem_id
        self.text_history: list[str] = []
        self.current_text: str | None = None
        self.destroyed: bool = False
        self.destroy_count: int = 0
        self.fade_calls: list[float] = []


class HudGscParser(Parser):
    """Extends tests.gsc_runtime.Parser with WaW 1.7 vector/method/thread syntax."""

    def parse_stmt(self) -> Any:
        tok = self.peek()
        if tok.kind == "IDENT" and tok.value.lower() == "thread":
            self.pos += 1
            call = self._parse_call_target()
            self.expect(";")
            return ExprStmt(
                ThreadCallExpr(
                    module_path=call.module_path,
                    func_name=call.func_name,
                    args=call.args,
                    line=call.line,
                )
            )
        return super().parse_stmt()

    def _parse_call_target(self) -> CallExpr:
        tok = self.expect("IDENT")
        if self.match("::"):
            fn_tok = self.expect("IDENT")
            args = self.parse_arg_list()
            return CallExpr(module_path=tok.value, func_name=fn_tok.value, args=args, line=fn_tok.line)
        args = self.parse_arg_list()
        return CallExpr(module_path=None, func_name=tok.value, args=args, line=tok.line)

    def parse_postfix(self) -> Any:
        expr = super().parse_postfix()
        # Handle WaW 1.7 entity method calls:
        #   hud SetText( "abc" )
        #   hud Destroy()
        #   level notify( "evt" )
        #   level endon( "evt" )
        #   level waittill( "evt" )
        #   level thread some_func( arg1 )
        if self.peek().kind == "IDENT":
            next_tok = self.peek()
            lower = next_tok.value.lower()
            if lower == "thread":
                self.pos += 1
                target = self._parse_call_target()
                return MethodCallExpr(
                    receiver=expr,
                    method_name=(
                        f"{target.module_path}::{target.func_name}"
                        if target.module_path
                        else target.func_name
                    ),
                    args=target.args,
                    threaded=True,
                    line=target.line,
                )
            if self.peek(1).kind == "(":
                method_tok = self.expect("IDENT")
                args = self.parse_arg_list()
                return MethodCallExpr(
                    receiver=expr,
                    method_name=method_tok.value,
                    args=args,
                    threaded=False,
                    line=method_tok.line,
                )
        return expr

    def parse_primary(self) -> Any:
        tok = self.peek()
        if tok.kind == "(":
            self.pos += 1
            first = self.parse_expr()
            if self.match(","):
                elems = [first, self.parse_expr()]
                while self.match(","):
                    elems.append(self.parse_expr())
                self.expect(")")
                return VectorLiteral(elems)
            self.expect(")")
            return first
        return super().parse_primary()


@dataclass
class _SuspendedThread:
    mod_key: str
    fn: FunctionDef
    stmt_index: int
    env: dict[str, Any]
    endons: set[tuple[int, str]]
    wait_receiver_id: int
    wait_event: str


class HudGscRuntime(GscRuntime):
    """Executes WaW 1.7 HUD scripts with fake NewHudElem(), level, and notifies."""

    def __init__(self, mod_root: Path, dvars: FakeDvarStore | None = None) -> None:
        super().__init__(mod_root, dvars)
        self.level = GscStruct()
        self.hud_elems: list[FakeHudElem] = []
        self.emitted_events: list[str] = []
        self._threads: list[_SuspendedThread] = []
        self._current_endons: set[tuple[int, str]] = set()

    @property
    def live_hud_elems(self) -> list[FakeHudElem]:
        return [h for h in self.hud_elems if not h.destroyed]

    def load_module(self, module_path: str) -> dict[str, FunctionDef]:
        key = self.normalize_module_key(module_path)
        if key not in self._modules:
            gsc_file = self.mod_root / f"{key}.gsc"
            if not gsc_file.is_file():
                raise FileNotFoundError(f"GSC module not found: {gsc_file}")
            source = gsc_file.read_text(encoding="latin1")
            tokens = tokenize(source, filename=str(gsc_file))
            self._modules[key] = HudGscParser(tokens, filename=str(gsc_file)).parse_module()
        return self._modules[key]

    def _call_builtin(self, name_lower: str, args: list[Any], line: int) -> tuple[bool, Any]:
        if name_lower == "newhudelem":
            elem = FakeHudElem(len(self.hud_elems) + 1)
            self.hud_elems.append(elem)
            return True, elem
        if name_lower == "println":
            if args:
                self.emitted_events.append(_waw_to_str(args[0]))
            return True, UNDEFINED
        return super()._call_builtin(name_lower, args, line)

    def _read_target(self, target: Any, mod_key: str, env: dict[str, Any]) -> Any:
        if isinstance(target, VarRef) and target.name.lower() == "level":
            return self.level
        return super()._read_target(target, mod_key, env)

    def _eval_expr(self, expr: Any, mod_key: str, env: dict[str, Any]) -> Any:
        if isinstance(expr, VarRef) and expr.name.lower() == "level":
            return self.level
        if isinstance(expr, VectorLiteral):
            return tuple(self._eval_expr(e, mod_key, env) for e in expr.elements)
        if isinstance(expr, ThreadCallExpr):
            eval_args = [self._eval_expr(a, mod_key, env) for a in expr.args]
            target_mod = expr.module_path if expr.module_path else mod_key
            self._spawn_thread(target_mod, expr.func_name, eval_args)
            return UNDEFINED
        if isinstance(expr, MethodCallExpr):
            receiver = self._eval_expr(expr.receiver, mod_key, env)
            eval_args = [self._eval_expr(a, mod_key, env) for a in expr.args]
            if expr.threaded:
                if "::" in expr.method_name:
                    m_path, fn_name = expr.method_name.split("::", 1)
                else:
                    m_path, fn_name = mod_key, expr.method_name
                self._spawn_thread(m_path, fn_name, eval_args)
                return UNDEFINED
            return self._exec_method(receiver, expr.method_name.lower(), eval_args, expr.line)
        return super()._eval_expr(expr, mod_key, env)

    def _exec_method(self, receiver: Any, method: str, args: list[Any], line: int) -> Any:
        if method == "settext":
            if not isinstance(receiver, FakeHudElem):
                raise GscRuntimeError(f"line {line}: SetText called on non-HUD {receiver!r}")
            if receiver.destroyed:
                raise GscRuntimeError(f"line {line}: SetText called on destroyed HUD elem")
            text = _waw_to_str(args[0]) if args else ""
            receiver.current_text = text
            receiver.text_history.append(text)
            return UNDEFINED
        if method == "destroy":
            if not isinstance(receiver, FakeHudElem):
                raise GscRuntimeError(f"line {line}: Destroy called on non-HUD {receiver!r}")
            receiver.destroyed = True
            receiver.destroy_count += 1
            return UNDEFINED
        if method == "fadeovertime":
            if isinstance(receiver, FakeHudElem):
                receiver.fade_calls.append(float(args[0]) if args else 0.0)
            return UNDEFINED
        if method == "endon":
            event_name = _waw_to_str(args[0]) if args else ""
            self._current_endons.add((id(receiver), event_name))
            return UNDEFINED
        if method == "waittill":
            event_name = _waw_to_str(args[0]) if args else ""
            raise _WaittillSuspend(receiver=receiver, event_name=event_name, out_var=None)
        if method == "notify":
            event_name = _waw_to_str(args[0]) if args else ""
            self.notify(receiver, event_name)
            return UNDEFINED
        raise GscRuntimeError(f"line {line}: unsupported method {method!r} on {receiver!r}")

    def _spawn_thread(self, module_path: str, func_name: str, args: list[Any]) -> None:
        mod_key = self.normalize_module_key(module_path)
        module = self.load_module(mod_key)
        fn = module.get(func_name.lower())
        if fn is None:
            raise GscRuntimeError(f"Threaded function {func_name!r} not found in {mod_key!r}")
        env: dict[str, Any] = {}
        for idx, param in enumerate(fn.params):
            env[param.lower()] = args[idx] if idx < len(args) else UNDEFINED
        self._run_thread_from(mod_key, fn, 0, env, set())

    def _run_thread_from(
        self,
        mod_key: str,
        fn: FunctionDef,
        start_idx: int,
        env: dict[str, Any],
        endons: set[tuple[int, str]],
    ) -> None:
        prev_endons = self._current_endons
        self._current_endons = endons
        try:
            for idx in range(start_idx, len(fn.body.statements)):
                stmt = fn.body.statements[idx]
                try:
                    self._exec_stmt(stmt, mod_key, env)
                except _WaittillSuspend as susp:
                    self._threads.append(
                        _SuspendedThread(
                            mod_key=mod_key,
                            fn=fn,
                            stmt_index=idx + 1,
                            env=env,
                            endons=set(self._current_endons),
                            wait_receiver_id=id(susp.receiver),
                            wait_event=susp.event_name,
                        )
                    )
                    return
                except _EndonSignal:
                    return
        finally:
            self._current_endons = prev_endons

    def notify(self, receiver: Any, event_name: str) -> None:
        key = (id(receiver), event_name)
        # First cancel any threads with matching endon
        surviving: list[_SuspendedThread] = []
        to_resume: list[_SuspendedThread] = []
        for th in self._threads:
            if key in th.endons:
                continue
            if th.wait_receiver_id == id(receiver) and th.wait_event == event_name:
                to_resume.append(th)
            else:
                surviving.append(th)
        self._threads = surviving

        for th in to_resume:
            self._run_thread_from(th.mod_key, th.fn, th.stmt_index, th.env, th.endons)

        # Match real WaW 1.7 GSC semantics: notifying an event that matches an
        # active endon on the currently executing thread aborts it immediately.
        if key in self._current_endons:
            raise _EndonSignal()

    def notify_level(self, event_name: str) -> None:
        self.notify(self.level, event_name)


# ---------------------------------------------------------------------------
# 1. Real GSC HUD Execution Tests
# ---------------------------------------------------------------------------


class TestGauntletHudGsc(unittest.TestCase):
    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.dvars.set("gauntlet_enabled", "1")
        self.gsc = HudGscRuntime(MOD_ROOT, self.dvars)

    def _make_state(self, cycle: int, stage: int) -> GscStruct:
        s = GscStruct()
        s.set_field("active", True)
        s.set_field("cycle", cycle)
        s.set_field("stage", stage)
        return s

    def _make_stage_info(self, cycle: int, stage: int, target_round: int) -> GscStruct:
        info = GscStruct()
        info.set_field("cycle", cycle)
        info.set_field("stage", stage)
        info.set_field("target_round", target_round)
        return info

    def test_no_foreach_in_gauntlet_hud_gsc(self) -> None:
        source = HUD_GSC_PATH.read_text(encoding="latin1")
        # Must tokenize cleanly under strict WaW 1.7 lexer (rejects foreach)
        tokenize(source, filename=str(HUD_GSC_PATH))
        code_only = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
        self.assertIsNone(re.search(r"\bforeach\b", code_only))

    def test_format_gauntlet_badge_text_is_ascii_and_matches_spec(self) -> None:
        cases = [
            (1, 1, 10, "GAUNTLET - C1 S1/4 - TARGET R10"),
            (1, 4, 10, "GAUNTLET - C1 S4/4 - TARGET R10"),
            (2, 1, 15, "GAUNTLET - C2 S1/4 - TARGET R15"),
            (3, 3, 20, "GAUNTLET - C3 S3/4 - TARGET R20"),
            (5, 2, 30, "GAUNTLET - C5 S2/4 - TARGET R30"),
        ]
        for cycle, stage, target, expected in cases:
            actual = self.gsc.call(HUD_MOD, "format_gauntlet_badge_text", cycle, stage, target)
            self.assertEqual(actual, expected)
            self.assertTrue(all(32 <= ord(ch) <= 126 for ch in actual), f"Non-ASCII in {actual!r}")

    def test_init_gauntlet_hud_creates_non_overlapping_top_corner_badge_and_emits_event(self) -> None:
        state = self._make_state(1, 1)
        info = self._make_stage_info(1, 1, 10)

        hud = self.gsc.call(HUD_MOD, "init_gauntlet_hud", state, info, 10)
        self.assertIsInstance(hud, FakeHudElem)
        self.assertEqual(len(self.gsc.live_hud_elems), 1)
        self.assertIs(self.gsc.level.get_field("gauntlet_hud_badge"), hud)

        # Top-right anchor, non-overlapping with center-top Prep Phase (y=24..52),
        # center-middle Stage Clear banner, bottom-left chalk, bottom-right ammo/score.
        self.assertEqual(hud.get_field("alignx"), "right")
        self.assertEqual(hud.get_field("aligny"), "top")
        self.assertEqual(hud.get_field("horzalign"), "right")
        self.assertEqual(hud.get_field("vertalign"), "top")
        self.assertEqual(hud.get_field("x"), -12)
        self.assertEqual(hud.get_field("y"), 12)
        self.assertAlmostEqual(hud.get_field("fontscale"), 1.35)
        self.assertTrue(hud.get_field("hidewheninmenu"))
        self.assertEqual(hud.current_text, "GAUNTLET - C1 S1/4 - TARGET R10")

        self.assertIn(
            "GAUNTLET_EVENT|HUD_INIT|cycle=1;stage=1;target_round=10;text=GAUNTLET - C1 S1/4 - TARGET R10",
            self.gsc.emitted_events,
        )

    def test_update_gauntlet_hud_updates_badge_and_avoids_redundant_settext(self) -> None:
        self.gsc.call(
            HUD_MOD,
            "init_gauntlet_hud",
            self._make_state(1, 1),
            self._make_stage_info(1, 1, 10),
            10,
        )
        badge = self.gsc.level.get_field("gauntlet_hud_badge")
        self.assertEqual(len(badge.text_history), 1)

        # Updating with identical values must NOT re-call SetText (protects configstring budget)
        self.assertTrue(self.gsc.call(HUD_MOD, "update_gauntlet_hud", 1, 1, 10))
        self.assertEqual(len(badge.text_history), 1)

        # Updating to Cycle 2 Stage 3 Target R15 updates badge text and emits HUD_UPDATE
        self.assertTrue(self.gsc.call(HUD_MOD, "update_gauntlet_hud", 2, 3, 15))
        self.assertEqual(badge.current_text, "GAUNTLET - C2 S3/4 - TARGET R15")
        self.assertEqual(len(badge.text_history), 2)
        self.assertIn(
            "GAUNTLET_EVENT|HUD_UPDATE|cycle=2;stage=3;target_round=15;text=GAUNTLET - C2 S3/4 - TARGET R15",
            self.gsc.emitted_events,
        )

    def test_cleanup_on_stage_clear_run_wipe_and_end_game_leaves_zero_leaks(self) -> None:
        for trigger_event in ("gauntlet_stage_clear", "gauntlet_run_wipe", "end_game"):
            with self.subTest(trigger_event=trigger_event):
                gsc = HudGscRuntime(MOD_ROOT, self.dvars)
                hud = gsc.call(
                    HUD_MOD,
                    "init_gauntlet_hud",
                    self._make_state(2, 2),
                    self._make_stage_info(2, 2, 15),
                    15,
                )
                self.assertEqual(len(gsc.live_hud_elems), 1)

                gsc.notify_level(trigger_event)

                self.assertTrue(hud.destroyed)
                self.assertEqual(hud.destroy_count, 1)
                self.assertEqual(len(gsc.live_hud_elems), 0)
                self.assertIs(gsc.level.get_field("gauntlet_hud_badge"), UNDEFINED)
                self.assertEqual(len(gsc._threads), 0, "Cleanup watchers must terminate on destroy")
                self.assertIn(
                    f"GAUNTLET_EVENT|HUD_DESTROYED|reason={trigger_event}",
                    gsc.emitted_events,
                )

                # Subsequent end_game / wipe notifications must be safe no-ops
                events_before = len(gsc.emitted_events)
                gsc.notify_level("end_game")
                gsc.notify_level("gauntlet_run_wipe")
                self.assertEqual(hud.destroy_count, 1)
                self.assertEqual(len(gsc.emitted_events), events_before)

    def test_reinit_destroys_previous_badge_without_leak(self) -> None:
        first = self.gsc.call(
            HUD_MOD,
            "init_gauntlet_hud",
            self._make_state(1, 1),
            self._make_stage_info(1, 1, 10),
            10,
        )
        second = self.gsc.call(
            HUD_MOD,
            "init_gauntlet_hud",
            self._make_state(1, 2),
            self._make_stage_info(1, 2, 10),
            10,
        )
        self.assertTrue(first.destroyed)
        self.assertFalse(second.destroyed)
        self.assertEqual(len(self.gsc.live_hud_elems), 1)
        self.assertIs(self.gsc.level.get_field("gauntlet_hud_badge"), second)

    def test_classic_mode_is_complete_noop(self) -> None:
        self.dvars.set("gauntlet_enabled", "0")
        res = self.gsc.call(
            HUD_MOD,
            "init_gauntlet_hud",
            self._make_state(1, 1),
            self._make_stage_info(1, 1, 10),
            10,
        )
        self.assertIs(res, UNDEFINED)
        self.assertEqual(len(self.gsc.hud_elems), 0)
        self.assertEqual(len(self.gsc.emitted_events), 0)
        self.assertIs(self.gsc.level.get_field("gauntlet_hud_badge"), UNDEFINED)


# ---------------------------------------------------------------------------
# 2. Menu Syntax, Patcher & Contract Validation Tests
# ---------------------------------------------------------------------------


SYNTHETIC_STOCK_MAIN_MENU = """#include "ui/menudef.h"
#include "ui/choices_setup_common.menu"
{
\t#define LOCAL_ZOMBIE_RESET\\
\t\texec "set zombiemode 0";
\tmenuDef
\t{
\t\tname\tmain_solo
#ifdef PC
\t\t\tCHOICE_BUTTON_VIS( 3, "@MENU_MISSION_SELECT", open levels; LOCAL_NETWORK_RESET; LOCAL_ZOMBIE_RESET, when( !localvarBool( ui_hideBack ) ); )
#endif // #ifdef PC
\t\t#include "ui/safearea.menu"
\t}
}
"""

SYNTHETIC_STOCK_LEVELS_MENU = """#include "ui/menudef.h"
#include "ui/choices_setup_common.menu"
#define CHEAT_CONDITION ( 0 )
#define CHEAT_CONDITION_NOT ( 1 )
#define LOCAL_MAP_ACTION_NODIFFICULTY( p_mapname, p_mapname_text, offset ) \\
\tsetdvar credits "0"; \\
\tsetdvar credits_active "0"; \\
\texec "devmap "p_mapname;
{
\tmenuDef
\t{
\t\tname\tlevels_unlock
#if !GERMAN_ZOMBIE_BUILD
\t\tLOCAL_NONGERMAN_MAP_SELECTION_NODIFFICULTY2( 2,\t"@MENU_LEVEL_ZOMBIE_PROTOTYPE", "nazi_zombie_prototype",\t"",\t"@MENU_LEVEL_DESC_ZOM_PROTO",\t15,\texec "set ui_load_index 15" )
#endif
\t}
}
"""

SYNTHETIC_STOCK_XBOXLIVE_LOBBY_MENU = """#include "ui/menudef.h"
#include "ui/choices_setup_common.menu"
{
\tmenuDef
\t{
\t\tname\tmenu_xboxlive_lobby
\t\t#define SETUP_ACTION_STARTMATCH \\
\t\t\t\texecOnDvarIntValue party_playerCount 1 "openmenu startmatch_popup"; \\
\t\t\t\texecOnDvarIntValue party_playerCount 2 "selectStringTableEntryInDvar maps/didyouknow_coop.csv 0 didyouknow; xpartygo";
\t\tCHOICE_BUTTON_FOCUS_VIS_EX( 1, "@MPUI_START_MATCH", SETUP_ACTION_STARTMATCH, exec "set ui_hint_text @MPUI_DESC_START_MATCH", CLEARUIHINT, when( IS_PARTY_HOST ), SETUP_EXTRA_FIRST )
\t\t#include "ui/safearea.menu"
\t}
\tmenuDef
\t{
\t\tname\tleavelobbywarning
\t\t#define LOCAL_ACCEPT_LEAVELOBBY_PC \\
\t\t\t\tplay "mouse_click"; \\
\t\t\t\tclose menu_xboxlive_lobby; \\
\t\t\t\tclose leavelobbywarning;
\t}
}
"""

SYNTHETIC_STOCK_SYSTEMLINK_LOBBY_MENU = """#include "ui/menudef.h"
#include "ui/choices_setup_common.menu"
{
\tmenuDef
\t{
\t\tname\tmenu_systemlink_lobby
\t\tCHOICE_BUTTON_VIS( 1, "@MPUI_START_MATCH", SETUP_ACTION_STARTMATCH, when( dvarbool( systemlinkpartyandhost ) ) )
\t\t#include "ui/safearea.menu"
\t}
\tmenuDef
\t{
\t\tname\tleavesystemlinklobbywarning
\t\t#define LOCAL_ACCEPT_LEAVE \\
\t\t\t\tplay "mouse_click"; \\
\t\t\t\tclose menu_systemlink_lobby;
\t}
}
"""


class TestGauntletMenusAndPatchers(unittest.TestCase):
    def setUp(self) -> None:
        import verify_hud_menus

        self.vhm = verify_hud_menus

    def test_repo_mod_ui_files_pass_full_contract_validation(self) -> None:
        errors = self.vhm.validate_ui_contracts(MOD_ROOT / "ui")
        self.assertEqual(errors, [])

    def test_validate_menu_braces_detects_imbalance_and_ignores_comments_and_strings(self) -> None:
        self.assertEqual(
            self.vhm.validate_menu_braces('menuDef { // {\n text "}" /* { */ itemDef { } }'),
            [],
        )
        self.assertTrue(len(self.vhm.validate_menu_braces("menuDef { itemDef { }")) > 0)
        self.assertTrue(len(self.vhm.validate_menu_braces("menuDef { } }")) > 0)

    def test_stock_menu_patchers_inject_solo_and_coop_gauntlet_entries(self) -> None:
        patched_main = self.vhm.patch_main_menu(SYNTHETIC_STOCK_MAIN_MENU)
        self.assertEqual(self.vhm.validate_menu_braces(patched_main), [])
        self.assertIn('#include "ui/gauntlet_menus.inc"', patched_main)
        self.assertIn("ZOMBIE GAUNTLET", patched_main)
        self.assertIn("GAUNTLET_SOLO_START_ACTION", patched_main)
        self.assertIn("gauntlet_enabled 0", patched_main)

        patched_levels = self.vhm.patch_levels_menu(SYNTHETIC_STOCK_LEVELS_MENU)
        self.assertEqual(self.vhm.validate_menu_braces(patched_levels), [])
        self.assertIn('#include "ui/gauntlet_menus.inc"', patched_levels)
        self.assertIn("#define NOT_CHEAT_CONDITION", patched_levels)
        self.assertIn("ZOMBIE GAUNTLET", patched_levels)
        self.assertIn("GAUNTLET_SOLO_START_ACTION", patched_levels)
        self.assertIn('setdvar gauntlet_enabled "0"', patched_levels)

        patched_xbox = self.vhm.patch_xboxlive_lobby_menu(SYNTHETIC_STOCK_XBOXLIVE_LOBBY_MENU)
        self.assertEqual(self.vhm.validate_menu_braces(patched_xbox), [])
        self.assertIn('#include "ui/gauntlet_menus.inc"', patched_xbox)
        self.assertIn("GAUNTLET_COOP_LOBBY_STATUS_PANEL", patched_xbox)
        self.assertIn("GAUNTLET_COOP_FRESH_LOCK_ACTION", patched_xbox)
        self.assertIn("GAUNTLET_CLEAR_RUN_STATE_EXEC", patched_xbox)

        patched_syslink = self.vhm.patch_systemlink_lobby_menu(SYNTHETIC_STOCK_SYSTEMLINK_LOBBY_MENU)
        self.assertEqual(self.vhm.validate_menu_braces(patched_syslink), [])
        self.assertIn('#include "ui/gauntlet_menus.inc"', patched_syslink)
        self.assertIn("GAUNTLET_COOP_FRESH_LOCK_ACTION", patched_syslink)
        self.assertIn("GAUNTLET_COOP_LOBBY_STATUS_PANEL", patched_syslink)
        self.assertIn("GAUNTLET_CLEAR_RUN_STATE_EXEC", patched_syslink)

    def test_stage_patched_menus_stages_all_four_stock_menus(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_ui = root / "tools" / "raw" / "ui"
            raw_ui.mkdir(parents=True)
            (raw_ui / "main.menu").write_text(SYNTHETIC_STOCK_MAIN_MENU, encoding="latin1")
            (raw_ui / "levels.menu").write_text(SYNTHETIC_STOCK_LEVELS_MENU, encoding="latin1")
            (raw_ui / "xboxlive_lobby.menu").write_text(SYNTHETIC_STOCK_XBOXLIVE_LOBBY_MENU, encoding="latin1")
            (raw_ui / "systemlink_lobby.menu").write_text(SYNTHETIC_STOCK_SYSTEMLINK_LOBBY_MENU, encoding="latin1")

            stage_dir = root / "stage"
            stage_dir.mkdir(parents=True)

            written = self.vhm.stage_patched_menus(root / "tools", stage_dir)
            self.assertEqual(len(written), 4)
            for out_path in written:
                self.assertTrue(out_path.is_file())
                self.assertEqual(
                    self.vhm.validate_menu_braces(out_path.read_text(encoding="latin1")),
                    [],
                )

    def test_validate_ui_contracts_fails_on_broken_menu_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_ui = Path(tmp) / "ui"
            bad_ui.mkdir()
            (bad_ui / "patch_menus.txt").write_text("{\n loadMenu { \"ui/main.menu\" }\n}\n", encoding="latin1")
            (bad_ui / "gauntlet_menus.inc").write_text("// missing all required macros\n", encoding="latin1")
            (bad_ui / "pc_gamesetup_coop.menu").write_text("menuDef { name \"pc_gamesetup_coop\" \n", encoding="latin1")

            errors = self.vhm.validate_ui_contracts(bad_ui)
            self.assertGreaterEqual(len(errors), 3)
            joined = "\n".join(errors)
            self.assertIn("Unbalanced", joined)
            self.assertIn("gauntlet_enabled", joined)
            self.assertIn("gauntlet_lobby_status", joined)


# ---------------------------------------------------------------------------
# 3. In-Engine HUD Log Analyzer Tests
# ---------------------------------------------------------------------------


class TestHudLogAnalyzer(unittest.TestCase):
    def setUp(self) -> None:
        import verify_hud_menus

        self.vhm = verify_hud_menus

    def _valid_gauntlet_hud_log(self) -> str:
        return "\n".join(
            [
                "Loading fastfile 'mod'",
                "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=1;stage=1;map=nazi_zombie_prototype;start_round=1;target_round=10;run_id=run_1",
                "dvar set gauntlet_event GAUNTLET_EVENT|HUD_INIT|cycle=1;stage=1;target_round=10;text=GAUNTLET - C1 S1/4 - TARGET R10",
                "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_CLEAR|cycle=1;stage=1;map=nazi_zombie_prototype;completed_round=10;next_cycle=1;next_stage=2;next_map=nazi_zombie_asylum",
                "dvar set gauntlet_event GAUNTLET_EVENT|HUD_DESTROYED|reason=gauntlet_stage_clear",
                "dvar set gauntlet_event GAUNTLET_EVENT|STAGE_INIT|cycle=2;stage=1;map=nazi_zombie_prototype;start_round=10;target_round=15;run_id=run_1",
                "dvar set gauntlet_event GAUNTLET_EVENT|HUD_INIT|cycle=2;stage=1;target_round=15;text=GAUNTLET - C2 S1/4 - TARGET R15",
                "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_START|cycle=2;stage=1;map=nazi_zombie_prototype;duration=3",
                "dvar set gauntlet_event GAUNTLET_EVENT|PREP_PHASE_END|cycle=2;stage=1;map=nazi_zombie_prototype;duration=3",
                "dvar set gauntlet_event GAUNTLET_EVENT|HUD_DESTROYED|reason=gauntlet_run_wipe",
            ]
        ) + "\n"

    def test_valid_gauntlet_hud_log_passes(self) -> None:
        _, errors = self.vhm.analyze_hud_log(
            self._valid_gauntlet_hud_log(),
            gauntlet_enabled=1,
            expected_badges=[(1, 1, 10), (2, 1, 15)],
            expected_destroy_reasons=["gauntlet_stage_clear", "gauntlet_run_wipe"],
        )
        self.assertEqual(errors, [])

    def test_valid_classic_mode_log_passes_with_zero_hud_events(self) -> None:
        classic_log = "\n".join(
            [
                "Loading fastfile 'mod'",
                "dvar set gauntlet_event GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_prototype;gauntlet_enabled=0",
            ]
        ) + "\n"
        _, errors = self.vhm.analyze_hud_log(classic_log, gauntlet_enabled=0)
        self.assertEqual(errors, [])

    def test_classic_mode_with_leaked_hud_init_fails(self) -> None:
        bad_classic = "\n".join(
            [
                "Loading fastfile 'mod'",
                "dvar set gauntlet_event GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_prototype;gauntlet_enabled=0",
                "dvar set gauntlet_event GAUNTLET_EVENT|HUD_INIT|cycle=1;stage=1;target_round=10;text=GAUNTLET - C1 S1/4 - TARGET R10",
            ]
        ) + "\n"
        _, errors = self.vhm.analyze_hud_log(bad_classic, gauntlet_enabled=0)
        self.assertTrue(any("Classic Mode" in e for e in errors))

    def test_wrong_badge_text_or_missing_destroy_fails(self) -> None:
        bad_text = self._valid_gauntlet_hud_log().replace(
            "text=GAUNTLET - C2 S1/4 - TARGET R15",
            "text=GAUNTLET - C2 S1/4 - TARGET R10",
        )
        _, errors = self.vhm.analyze_hud_log(
            bad_text,
            gauntlet_enabled=1,
            expected_badges=[(1, 1, 10), (2, 1, 15)],
            expected_destroy_reasons=["gauntlet_stage_clear", "gauntlet_run_wipe"],
        )
        self.assertTrue(any("TARGET R15" in e for e in errors))

        missing_destroy = self._valid_gauntlet_hud_log().replace(
            "dvar set gauntlet_event GAUNTLET_EVENT|HUD_DESTROYED|reason=gauntlet_run_wipe\n",
            "",
        )
        _, errors2 = self.vhm.analyze_hud_log(
            missing_destroy,
            gauntlet_enabled=1,
            expected_badges=[(1, 1, 10), (2, 1, 15)],
            expected_destroy_reasons=["gauntlet_stage_clear", "gauntlet_run_wipe"],
        )
        self.assertTrue(any("HUD_DESTROYED" in e for e in errors2))

    def test_fatal_script_error_fails_hud_log_analysis(self) -> None:
        bad = self._valid_gauntlet_hud_log() + "******* script runtime error *******\n"
        _, errors = self.vhm.analyze_hud_log(
            bad,
            gauntlet_enabled=1,
            expected_badges=[(1, 1, 10), (2, 1, 15)],
        )
        self.assertTrue(any("Script runtime error" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
