"""Offline TDD contract suite for mod/maps/_gauntlet_perks.gsc.

Executes the real WaW 1.7 GSC script (mod/maps/_gauntlet_perks.gsc along with
_gauntlet_state.gsc and _gauntlet_log.gsc) through an extended GscRuntime
harness built on tests/gsc_runtime.py supporting WaW 1.7 player perk methods,
NewClientHudElem(), PrecacheShader(), IsAlive(), GetPlayers(), level globals,
and threaded endon/waittill/notify perk-loss lifecycles.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Any
import unittest

from tests.gsc_runtime import (
    CallExpr,
    ExprStmt,
    FakeDvarStore,
    FieldAccess,
    FunctionDef,
    GscArray,
    GscRuntime,
    GscRuntimeError,
    GscStruct,
    IndexAccess,
    Parser,
    UNDEFINED,
    VarRef,
    _ReturnSignal,
    _waw_to_str,
    tokenize,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_ROOT = REPO_ROOT / "mod"
PERKS_MOD = "maps\\_gauntlet_perks"
PERKS_GSC_PATH = MOD_ROOT / "maps" / "_gauntlet_perks.gsc"


# ---------------------------------------------------------------------------
# Extended GSC Parser & Runtime (built on tests/gsc_runtime.py) for WaW 1.7
# perk builtins, player entity methods, client HUD elements, and notify/waittill.
# ---------------------------------------------------------------------------


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
    def __init__(self, receiver: Any, event_name: str) -> None:
        self.receiver = receiver
        self.event_name = event_name


class FakeClientHudElem(GscStruct):
    """Tracks client perk HUD icon properties, shader, and Destroy() lifecycle."""

    def __init__(self, elem_id: int, owner: FakePlayer) -> None:
        super().__init__()
        self.elem_id = elem_id
        self.owner = owner
        self.shader: str | None = None
        self.shader_width: int | None = None
        self.shader_height: int | None = None
        self.destroyed: bool = False
        self.destroy_count: int = 0


class FakePlayer(GscStruct):
    """Simulates a WaW 1.7 player entity with perks, health, sessionstate, and HUD."""

    def __init__(
        self,
        entity_num: int = 0,
        guid: Any = 0,
        playername: str = "",
        alive: bool = True,
        sessionstate: str = "playing",
        perks: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._entity_num = entity_num
        self._alive = alive
        self._perks: set[str] = set(perks or [])
        self.set_perk_calls: list[str] = []
        self.unset_perk_calls: list[str] = []
        if guid is not UNDEFINED:
            self.set_field("guid", guid)
        if playername:
            self.set_field("playername", playername)
        self.set_field("sessionstate", sessionstate)
        self.set_field("maxhealth", 100)
        self.set_field("health", 100)

    def has_perk(self, perk: str) -> bool:
        return perk in self._perks

    def set_perk(self, perk: str) -> None:
        self._perks.add(perk)
        self.set_perk_calls.append(perk)

    def unset_perk(self, perk: str) -> None:
        self._perks.discard(perk)
        self.unset_perk_calls.append(perk)


class PerksGscParser(Parser):
    """Extends tests.gsc_runtime.Parser with WaW 1.7 entity method and thread calls."""

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


@dataclass
class _SuspendedThread:
    mod_key: str
    fn: FunctionDef
    stmt_index: int
    env: dict[str, Any]
    endons: set[tuple[int, str]]
    wait_receiver_id: int
    wait_event: str


class PerksGscRuntime(GscRuntime):
    """Executes WaW 1.7 perk scripts with fake player entities, HUDs, and threads."""

    def __init__(self, mod_root: Path = MOD_ROOT, dvars: FakeDvarStore | None = None) -> None:
        super().__init__(mod_root, dvars)
        self.level = GscStruct()
        self.players: list[FakePlayer] = []
        self.precached_shaders: list[str] = []
        self.client_huds: list[FakeClientHudElem] = []
        self.emitted_events: list[str] = []
        self._threads: list[_SuspendedThread] = []
        self._current_endons: set[tuple[int, str]] = set()

    @property
    def active_thread_count(self) -> int:
        return len(self._threads)

    @property
    def live_client_huds(self) -> list[FakeClientHudElem]:
        return [h for h in self.client_huds if not h.destroyed]

    def load_module(self, module_path: str) -> dict[str, FunctionDef]:
        key = self.normalize_module_key(module_path)
        if key not in self._modules:
            gsc_file = self.mod_root / f"{key}.gsc"
            if not gsc_file.is_file():
                raise FileNotFoundError(f"GSC module not found: {gsc_file}")
            source = gsc_file.read_text(encoding="latin1")
            tokens = tokenize(source, filename=str(gsc_file))
            self._modules[key] = PerksGscParser(tokens, filename=str(gsc_file)).parse_module()
        return self._modules[key]

    def _read_target(self, target: Any, mod_key: str, env: dict[str, Any]) -> Any:
        if isinstance(target, VarRef) and target.name.lower() == "level" and "level" not in env:
            return self.level
        return super()._read_target(target, mod_key, env)

    def _write_target(self, target: Any, value: Any, mod_key: str, env: dict[str, Any]) -> None:
        # In WaW 1.7 GSC, assigning `undefined` to an associative array entry removes
        # the key and decrements `.size` (used by stock perk_hud_destroy).
        if isinstance(target, IndexAccess) and value is UNDEFINED:
            obj = self._eval_expr(target.obj, mod_key, env)
            idx = self._eval_expr(target.index, mod_key, env)
            if isinstance(obj, GscArray):
                obj._data.pop(idx, None)
                return
        super()._write_target(target, value, mod_key, env)

    def _call_builtin(self, name_lower: str, args: list[Any], line: int) -> tuple[bool, Any]:
        if name_lower == "precacheshader":
            shader = _waw_to_str(args[0]) if args else ""
            self.precached_shaders.append(shader)
            return True, UNDEFINED
        if name_lower == "newclienthudelem":
            if not args or not isinstance(args[0], FakePlayer):
                raise GscRuntimeError(f"line {line}: NewClientHudElem requires a player entity")
            elem = FakeClientHudElem(len(self.client_huds) + 1, args[0])
            self.client_huds.append(elem)
            return True, elem
        if name_lower == "isalive":
            ent = args[0] if args else UNDEFINED
            if isinstance(ent, FakePlayer):
                return True, ent._alive
            return True, False
        if name_lower == "getplayers":
            return True, GscArray(list(self.players))
        if name_lower == "println":
            if args:
                msg = _waw_to_str(args[0])
                if msg.startswith("GAUNTLET_EVENT|"):
                    self.emitted_events.append(msg)
            return True, UNDEFINED
        return super()._call_builtin(name_lower, args, line)

    def _eval_expr(self, expr: Any, mod_key: str, env: dict[str, Any]) -> Any:
        if isinstance(expr, VarRef) and expr.name.lower() == "level" and "level" not in env:
            return self.level
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
        if isinstance(receiver, FakePlayer):
            if method == "hasperk":
                return receiver.has_perk(_waw_to_str(args[0]))
            if method == "setperk":
                receiver.set_perk(_waw_to_str(args[0]))
                return UNDEFINED
            if method == "unsetperk":
                receiver.unset_perk(_waw_to_str(args[0]))
                return UNDEFINED
            if method == "getentitynumber":
                return receiver._entity_num
        if isinstance(receiver, FakeClientHudElem):
            if method == "setshader":
                if receiver.destroyed:
                    raise GscRuntimeError(f"line {line}: SetShader called on destroyed HUD elem")
                receiver.shader = _waw_to_str(args[0])
                receiver.shader_width = int(args[1]) if len(args) > 1 else 0
                receiver.shader_height = int(args[2]) if len(args) > 2 else 0
                return UNDEFINED
            if method == "destroy":
                if receiver.destroyed:
                    raise GscRuntimeError(f"line {line}: Destroy called twice on HUD elem")
                receiver.destroyed = True
                receiver.destroy_count += 1
                return UNDEFINED
        if method == "endon":
            event_name = _waw_to_str(args[0]) if args else ""
            self._current_endons.add((id(receiver), event_name))
            return UNDEFINED
        if method == "waittill":
            event_name = _waw_to_str(args[0]) if args else ""
            raise _WaittillSuspend(receiver=receiver, event_name=event_name)
        if method == "notify":
            event_name = _waw_to_str(args[0]) if args else ""
            self.notify_entity(receiver, event_name)
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
        self._current_endons = set(endons)
        try:
            stmts = fn.body.statements
            for idx in range(start_idx, len(stmts)):
                try:
                    self._exec_stmt(stmts[idx], mod_key, env)
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
                except _ReturnSignal:
                    return
                except _EndonSignal:
                    return
        finally:
            self._current_endons = prev_endons

    def notify_entity(self, receiver: Any, event_name: str) -> None:
        recv_id = id(receiver)
        key = (recv_id, event_name)

        # Terminate any threads whose endon matches this (entity, event).
        survivors: list[_SuspendedThread] = []
        to_wake: list[_SuspendedThread] = []
        for thread in self._threads:
            if key in thread.endons:
                continue
            if thread.wait_receiver_id == recv_id and thread.wait_event == event_name:
                to_wake.append(thread)
            else:
                survivors.append(thread)
        self._threads = survivors

        for thread in to_wake:
            # Skip if an earlier woken thread's notify already killed this thread via endon.
            if key in thread.endons:
                continue
            self._run_thread_from(
                thread.mod_key,
                thread.fn,
                thread.stmt_index,
                thread.env,
                thread.endons,
            )


# ---------------------------------------------------------------------------
# Contract Tests for mod/maps/_gauntlet_perks.gsc
# ---------------------------------------------------------------------------


class TestGauntletPerksGsc(unittest.TestCase):
    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = PerksGscRuntime(MOD_ROOT, self.dvars)

    def test_no_foreach_in_gauntlet_perks_gsc(self) -> None:
        self.assertTrue(PERKS_GSC_PATH.is_file(), f"Missing {PERKS_GSC_PATH}")
        source = PERKS_GSC_PATH.read_text(encoding="latin1")
        code_only = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
        self.assertIsNone(re.search(r"\bforeach\b", code_only))
        tokens = tokenize(source, filename=str(PERKS_GSC_PATH))
        self.assertGreater(len(tokens), 20)

    def test_supported_perks_codes_shaders_and_codec_round_trip(self) -> None:
        supported = self.gsc.call(PERKS_MOD, "get_supported_perks").to_list()
        self.assertEqual(
            supported,
            [
                "specialty_armorvest",
                "specialty_fastreload",
                "specialty_rof",
                "specialty_quickrevive",
            ],
        )

        expected_codes = {
            "specialty_armorvest": "j",
            "specialty_fastreload": "f",
            "specialty_rof": "r",
            "specialty_quickrevive": "q",
        }
        expected_shaders = {
            "specialty_armorvest": "specialty_juggernaut_zombies",
            "specialty_fastreload": "specialty_fastreload_zombies",
            "specialty_rof": "specialty_doubletap_zombies",
            "specialty_quickrevive": "specialty_quickrevive_zombies",
        }

        for perk, code in expected_codes.items():
            self.assertEqual(self.gsc.call(PERKS_MOD, "perk_to_code", perk), code)
            self.assertEqual(self.gsc.call(PERKS_MOD, "code_to_perk", code), perk)
            self.assertEqual(self.gsc.call(PERKS_MOD, "code_to_perk", code.upper()), perk)
            self.assertEqual(self.gsc.call(PERKS_MOD, "perk_to_shader", perk), expected_shaders[perk])

        self.assertEqual(self.gsc.call(PERKS_MOD, "perk_to_code", "specialty_bogus"), "")
        self.assertEqual(self.gsc.call(PERKS_MOD, "code_to_perk", "z"), "")
        self.assertEqual(self.gsc.call(PERKS_MOD, "perk_to_shader", "specialty_bogus"), "")

        # Full round-trip of all 4 perks
        encoded_all = self.gsc.call(PERKS_MOD, "encode_perk_list", GscArray(supported))
        self.assertEqual(encoded_all, "j,f,r,q")
        decoded_all = self.gsc.call(PERKS_MOD, "decode_perk_list", encoded_all).to_list()
        self.assertEqual(decoded_all, supported)

        # Deduplication, canonical ordering, and unknown-value resilience
        messy_perks = GscArray(
            [
                "specialty_quickrevive",
                "specialty_unknown",
                "specialty_armorvest",
                "specialty_quickrevive",
                "specialty_rof",
            ]
        )
        self.assertEqual(self.gsc.call(PERKS_MOD, "encode_perk_list", messy_perks), "j,r,q")
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "decode_perk_list", "q,bogus,J,q,,r,x").to_list(),
            ["specialty_armorvest", "specialty_rof", "specialty_quickrevive"],
        )
        self.assertEqual(self.gsc.call(PERKS_MOD, "encode_perk_list", GscArray([])), "")
        self.assertEqual(self.gsc.call(PERKS_MOD, "decode_perk_list", "").to_list(), [])
        self.assertEqual(self.gsc.call(PERKS_MOD, "decode_perk_list", UNDEFINED).to_list(), [])

    def test_precache_perk_shaders_precaches_all_four_stock_shaders(self) -> None:
        self.gsc.call(PERKS_MOD, "precache_perk_shaders")
        self.assertEqual(
            self.gsc.precached_shaders,
            [
                "specialty_juggernaut_zombies",
                "specialty_fastreload_zombies",
                "specialty_doubletap_zombies",
                "specialty_quickrevive_zombies",
            ],
        )

    def test_multiplayer_perk_ledger_guid_name_fallback_overwrite_and_clear(self) -> None:
        # Record perks for multiple players (GUID-keyed + offline name-fallback)
        self.assertTrue(
            self.gsc.call(
                PERKS_MOD,
                "record_player_perks",
                10001,
                "Dempsey",
                GscArray(["specialty_armorvest", "specialty_fastreload"]),
            )
        )
        self.assertTrue(
            self.gsc.call(
                PERKS_MOD,
                "record_player_perks",
                10002,
                "Nikolai",
                GscArray(["specialty_rof", "specialty_quickrevive"]),
            )
        )
        self.assertTrue(
            self.gsc.call(
                PERKS_MOD,
                "record_player_perks",
                0,
                "[CLAN] Richtofen;=1",
                GscArray(["specialty_armorvest"]),
            )
        )

        # Lookup by GUID succeeds even if display name changes
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 10001, "RenamedDempsey").to_list(),
            ["specialty_armorvest", "specialty_fastreload"],
        )
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 10002, "Nikolai").to_list(),
            ["specialty_rof", "specialty_quickrevive"],
        )
        # Name fallback works when GUID is 0
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 0, "[CLAN] Richtofen;=1").to_list(),
            ["specialty_armorvest"],
        )
        # Unknown player returns empty array
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 99999, "LateJoiner").to_list(),
            [],
        )

        # Overwriting with empty list removes prior entry so a player who lost perks
        # before Stage Clear does NOT get old perks back!
        self.assertTrue(
            self.gsc.call(PERKS_MOD, "record_player_perks", 10001, "Dempsey", GscArray([]))
        )
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 10001, "Dempsey").to_list(),
            [],
        )
        self.assertNotIn("g_10001=", self.dvars.get("gauntlet_player_perks"))
        # Other players remain intact
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 10002, "Nikolai").to_list(),
            ["specialty_rof", "specialty_quickrevive"],
        )

        # Missing both GUID and name returns false without mutating ledger
        before = self.dvars.get("gauntlet_player_perks")
        self.assertFalse(
            self.gsc.call(PERKS_MOD, "record_player_perks", 0, "", GscArray(["specialty_armorvest"]))
        )
        self.assertEqual(self.dvars.get("gauntlet_player_perks"), before)

        # clear_perk_ledger wipes dvar cleanly
        self.gsc.call(PERKS_MOD, "clear_perk_ledger")
        self.assertEqual(self.dvars.get("gauntlet_player_perks"), "")
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 10002, "Nikolai").to_list(),
            [],
        )

    def test_snapshot_player_perks_alive_vs_dead_and_spectating(self) -> None:
        alive_player = FakePlayer(
            entity_num=0,
            guid=20001,
            playername="Takeo",
            alive=True,
            sessionstate="playing",
            perks=["specialty_armorvest", "specialty_rof"],
        )
        saved = self.gsc.call(PERKS_MOD, "snapshot_player_perks", alive_player, "nazi_zombie_asylum")
        self.assertEqual(saved.to_list(), ["specialty_armorvest", "specialty_rof"])
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 20001, "Takeo").to_list(),
            ["specialty_armorvest", "specialty_rof"],
        )
        self.assertIn(
            "GAUNTLET_EVENT|PERKS_SAVED|player=g_20001;perks=specialty_armorvest,specialty_rof;count=2;map=nazi_zombie_asylum",
            self.gsc.emitted_events,
        )

        # If that same player is now spectating at next Stage Clear, even if a stale
        # perk flag were still set, snapshot saves [] and clears their prior ledger entry.
        spectator = FakePlayer(
            entity_num=0,
            guid=20001,
            playername="Takeo",
            alive=True,
            sessionstate="spectator",
            perks=["specialty_armorvest"],
        )
        saved_spec = self.gsc.call(PERKS_MOD, "snapshot_player_perks", spectator, "nazi_zombie_sumpf")
        self.assertEqual(saved_spec.to_list(), [])
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 20001, "Takeo").to_list(),
            [],
        )
        self.assertIn(
            "GAUNTLET_EVENT|PERKS_SAVED|player=g_20001;perks=none;count=0;map=nazi_zombie_sumpf",
            self.gsc.emitted_events,
        )

        # Dead player (!IsAlive) also records empty []
        self.gsc.call(
            PERKS_MOD, "record_player_perks", 20002, "DeadHero", GscArray(["specialty_fastreload"])
        )
        dead_player = FakePlayer(
            entity_num=1,
            guid=20002,
            playername="DeadHero",
            alive=False,
            sessionstate="playing",
            perks=["specialty_fastreload"],
        )
        saved_dead = self.gsc.call(PERKS_MOD, "snapshot_player_perks", dead_player, "nazi_zombie_factory")
        self.assertEqual(saved_dead.to_list(), [])
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 20002, "DeadHero").to_list(),
            [],
        )

    def test_restore_player_perks_sets_perks_jugg_health_hud_positions_and_cleans_up_on_down(self) -> None:
        all_four = [
            "specialty_armorvest",
            "specialty_fastreload",
            "specialty_rof",
            "specialty_quickrevive",
        ]
        self.gsc.call(PERKS_MOD, "record_player_perks", 30001, "Dempsey", GscArray(all_four))

        # Test with level.zombie_vars["zombie_perk_juggernaut_health"] defined (Verrückt/SNN/Der Riese)
        zombie_vars = GscArray()
        zombie_vars.set_item("zombie_perk_juggernaut_health", 160)
        self.gsc.level.set_field("zombie_vars", zombie_vars)

        player = FakePlayer(entity_num=0, guid=30001, playername="Dempsey", alive=True)
        restored = self.gsc.call(PERKS_MOD, "restore_player_perks", player, "nazi_zombie_sumpf")

        self.assertEqual(restored.to_list(), all_four)
        self.assertTrue(player.gauntlet_perks_applied)
        self.assertEqual(player.set_perk_calls, all_four)
        for perk in all_four:
            self.assertTrue(player.has_perk(perk))

        # Juggernog health applied
        self.assertEqual(player.maxhealth, 160)
        self.assertEqual(player.health, 160)

        # Stock-compatible non-overlapping perk_hud entries at x = 0, 30, 60, 90 and y = -70
        perk_hud = player.perk_hud
        self.assertIsInstance(perk_hud, GscArray)
        self.assertEqual(perk_hud.size, 4)

        expected_layout = [
            ("specialty_armorvest", 0, "specialty_juggernaut_zombies"),
            ("specialty_fastreload", 30, "specialty_fastreload_zombies"),
            ("specialty_rof", 60, "specialty_doubletap_zombies"),
            ("specialty_quickrevive", 90, "specialty_quickrevive_zombies"),
        ]
        for perk, expected_x, expected_shader in expected_layout:
            elem = perk_hud[perk]
            self.assertIsInstance(elem, FakeClientHudElem)
            self.assertFalse(elem.destroyed)
            self.assertEqual(elem.alignX, "left")
            self.assertEqual(elem.alignY, "bottom")
            self.assertEqual(elem.horzAlign, "left")
            self.assertEqual(elem.vertAlign, "bottom")
            self.assertEqual(elem.x, expected_x)
            self.assertEqual(elem.y, -70)
            self.assertEqual(elem.alpha, 1)
            self.assertEqual(elem.shader, expected_shader)
            self.assertEqual((elem.shader_width, elem.shader_height), (24, 24))

        # Telemetry event emitted
        self.assertIn(
            "GAUNTLET_EVENT|PERKS_RESTORED|player=g_30001;perks=specialty_armorvest,specialty_fastreload,specialty_rof,specialty_quickrevive;count=4;maxhealth=160;map=nazi_zombie_sumpf",
            self.gsc.emitted_events,
        )

        # Double-restore guard: second call is a complete no-op
        prev_hud_count = len(self.gsc.client_huds)
        second = self.gsc.call(PERKS_MOD, "restore_player_perks", player, "nazi_zombie_sumpf")
        self.assertEqual(second.to_list(), [])
        self.assertEqual(len(self.gsc.client_huds), prev_hud_count)

        # Going down ("player_downed") strips all perks, restores maxhealth=100,
        # and destroys every perk HUD elem without double-destroying on subsequent "death".
        self.gsc.notify_entity(player, "player_downed")

        for perk in all_four:
            self.assertFalse(player.has_perk(perk))
            self.assertIs(player.perk_hud[perk], UNDEFINED)
        self.assertEqual(player.maxhealth, 100)
        self.assertEqual(player.perk_hud.size, 0)
        self.assertEqual(len(self.gsc.live_client_huds), 0)
        self.assertEqual(self.gsc.active_thread_count, 0)

        # Subsequent "death" and "fake_death" after bleedout do not double-destroy HUD elems
        self.gsc.notify_entity(player, "death")
        self.gsc.notify_entity(player, "fake_death")
        for elem in self.gsc.client_huds:
            self.assertEqual(elem.destroy_count, 1)

    def test_restore_juggernog_fallback_health_on_nacht_der_untoten(self) -> None:
        # On nazi_zombie_prototype (Cycle 2+), _zombiemode_perks never runs, so
        # level.zombie_vars["zombie_perk_juggernaut_health"] is undefined -> fallback 160.
        self.gsc.call(
            PERKS_MOD, "record_player_perks", 40001, "SoloRunner", GscArray(["specialty_armorvest"])
        )
        player = FakePlayer(entity_num=0, guid=40001, playername="SoloRunner", alive=True)

        restored = self.gsc.call(PERKS_MOD, "restore_player_perks", player, "nazi_zombie_prototype")
        self.assertEqual(restored.to_list(), ["specialty_armorvest"])
        self.assertEqual(player.maxhealth, 160)
        self.assertEqual(player.health, 160)
        self.assertTrue(player.has_perk("specialty_armorvest"))
        self.assertEqual(player.perk_hud["specialty_armorvest"].x, 0)
        self.assertEqual(player.perk_hud["specialty_armorvest"].shader, "specialty_juggernaut_zombies")

        # Disconnect cleanly terminates remaining perk-loss watcher threads
        self.assertGreater(self.gsc.active_thread_count, 0)
        self.gsc.notify_entity(player, "disconnect")
        self.assertEqual(self.gsc.active_thread_count, 0)

    def test_restore_skips_already_owned_perk_and_emits_none_when_empty(self) -> None:
        # Player with no recorded perks still emits PERKS_RESTORED with perks=none;count=0
        fresh_player = FakePlayer(entity_num=0, guid=50001, playername="Fresh", alive=True)
        restored_empty = self.gsc.call(
            PERKS_MOD, "restore_player_perks", fresh_player, "nazi_zombie_prototype"
        )
        self.assertEqual(restored_empty.to_list(), [])
        self.assertEqual(fresh_player.maxhealth, 100)
        self.assertIn(
            "GAUNTLET_EVENT|PERKS_RESTORED|player=g_50001;perks=none;count=0;maxhealth=100;map=nazi_zombie_prototype",
            self.gsc.emitted_events,
        )

        # Player who already owns one perk only receives the missing carried perk
        self.gsc.call(
            PERKS_MOD,
            "record_player_perks",
            50002,
            "Partial",
            GscArray(["specialty_armorvest", "specialty_fastreload"]),
        )
        partial_player = FakePlayer(
            entity_num=1,
            guid=50002,
            playername="Partial",
            alive=True,
            perks=["specialty_armorvest"],
        )
        restored_partial = self.gsc.call(
            PERKS_MOD, "restore_player_perks", partial_player, "nazi_zombie_asylum"
        )
        self.assertEqual(restored_partial.to_list(), ["specialty_fastreload"])
        self.assertEqual(partial_player.set_perk_calls, ["specialty_fastreload"])
        self.assertEqual(partial_player.perk_hud.size, 1)
        self.assertEqual(partial_player.perk_hud["specialty_fastreload"].x, 0)

    def test_corrupt_perk_ledger_and_snapshot_all_players(self) -> None:
        # Corrupt ledger entries do not crash and clean up on next write
        self.dvars.set(
            "gauntlet_player_perks",
            ";;broken;=j;g_111=zzz;g_222=r,j,bogus;g_222=q;g_333=f;",
        )
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 111, "Bad").to_list(),
            [],
        )
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 222, "Dup").to_list(),
            ["specialty_armorvest", "specialty_rof"],
        )
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 333, "Valid").to_list(),
            ["specialty_fastreload"],
        )

        # Updating g_222 deduplicates and strips malformed entries
        self.assertTrue(
            self.gsc.call(
                PERKS_MOD, "record_player_perks", 222, "Dup", GscArray(["specialty_quickrevive"])
            )
        )
        raw = self.dvars.get("gauntlet_player_perks")
        self.assertEqual(raw.count("g_222="), 1)
        self.assertNotIn("broken", raw)
        self.assertNotIn("g_111=", raw)
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 222, "Dup").to_list(),
            ["specialty_quickrevive"],
        )

        # snapshot_all_players_perks captures alive players and clears dead/spectating players
        self.gsc.players = [
            FakePlayer(
                entity_num=0,
                guid=222,
                playername="Dup",
                alive=True,
                sessionstate="playing",
                perks=["specialty_armorvest", "specialty_fastreload"],
            ),
            FakePlayer(
                entity_num=1,
                guid=333,
                playername="Valid",
                alive=True,
                sessionstate="spectator",
                perks=["specialty_fastreload"],
            ),
        ]
        self.gsc.call(PERKS_MOD, "snapshot_all_players_perks", "nazi_zombie_factory")
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 222, "Dup").to_list(),
            ["specialty_armorvest", "specialty_fastreload"],
        )
        self.assertEqual(
            self.gsc.call(PERKS_MOD, "get_recorded_player_perks", 333, "Valid").to_list(),
            [],
        )

    def test_death_event_cleanup_and_stock_perk_hud_stacking_offset(self) -> None:
        # Carrying 2 perks leaves player.perk_hud.size == 2 so a stock vending machine
        # purchase (self.perk_hud.size * 30) stacks cleanly at x = 60 with zero overlap.
        self.gsc.call(
            PERKS_MOD,
            "record_player_perks",
            60001,
            "Stacker",
            GscArray(["specialty_armorvest", "specialty_rof"]),
        )
        player = FakePlayer(entity_num=0, guid=60001, playername="Stacker", alive=True)
        self.gsc.call(PERKS_MOD, "restore_player_perks", player, "nazi_zombie_asylum")

        self.assertEqual(player.perk_hud["specialty_armorvest"].x, 0)
        self.assertEqual(player.perk_hud["specialty_rof"].x, 30)
        self.assertEqual(player.perk_hud.size * 30, 60)

        # Direct "death" event (without prior "player_downed") strips perks & resets maxhealth
        self.gsc.notify_entity(player, "death")
        self.assertFalse(player.has_perk("specialty_armorvest"))
        self.assertFalse(player.has_perk("specialty_rof"))
        self.assertEqual(player.maxhealth, 100)
        self.assertEqual(player.perk_hud.size, 0)
        self.assertEqual(len(self.gsc.live_client_huds), 0)
        self.assertEqual(self.gsc.active_thread_count, 0)

    def test_spectator_defers_perk_restore_until_spawned_player(self) -> None:
        self.gsc.call(
            PERKS_MOD,
            "record_player_perks",
            70001,
            "Reconnector",
            GscArray(["specialty_armorvest", "specialty_fastreload"]),
        )
        player = FakePlayer(
            entity_num=2,
            guid=70001,
            playername="Reconnector",
            alive=False,
            sessionstate="spectator",
        )

        # Calling restore while spectating must NOT grant perks, health, or HUDs yet
        initial = self.gsc.call(PERKS_MOD, "restore_player_perks", player, "nazi_zombie_factory")
        self.assertEqual(initial.to_list(), [])
        self.assertFalse(player.has_perk("specialty_armorvest"))
        self.assertEqual(player.maxhealth, 100)
        self.assertEqual(len(self.gsc.live_client_huds), 0)

        # Once player respawns alive on next round, perks + Juggernog HP + HUDs restore cleanly
        player._alive = True
        player.set_field("sessionstate", "playing")
        self.gsc.notify_entity(player, "spawned_player")

        self.assertTrue(player.has_perk("specialty_armorvest"))
        self.assertTrue(player.has_perk("specialty_fastreload"))
        self.assertEqual(player.maxhealth, 160)
        self.assertEqual(len(self.gsc.live_client_huds), 2)

    def test_one_shot_test_grant_perks_consumes_dvar_once(self) -> None:
        self.dvars.set("gauntlet_test_grant_perks", "j,f")
        player = FakePlayer(entity_num=0, guid=70002, playername="Tester", alive=True)

        self.gsc.call(PERKS_MOD, "restore_player_perks", player, "nazi_zombie_factory")
        self.assertEqual(self.dvars.get("gauntlet_test_grant_perks"), "")
        self.assertTrue(player.has_perk("specialty_armorvest"))
        self.assertTrue(player.has_perk("specialty_fastreload"))
        self.assertEqual(player.maxhealth, 160)
        self.assertIn(
            "GAUNTLET_EVENT|PERKS_TEST_GRANTED|player=g_70002;perks=specialty_armorvest,specialty_fastreload;count=2;map=nazi_zombie_factory",
            self.gsc.emitted_events,
        )


class TestVerifyPerksLogAnalyzers(unittest.TestCase):
    def setUp(self) -> None:
        scripts_dir = str(REPO_ROOT / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import verify_perks  # noqa: E402

        self.verify_perks = verify_perks

    def test_analyze_perk_carryover_log_pass_and_failures(self) -> None:
        valid_log = "\n".join(
            [
                "Loading fastfile 'mod'",
                "dvar set gauntlet_event GAUNTLET_EVENT|PERKS_TEST_GRANTED|player=n_player;perks=specialty_armorvest,specialty_fastreload;count=2;map=nazi_zombie_factory",
                "dvar set gauntlet_event GAUNTLET_EVENT|PERKS_SAVED|player=n_player;perks=specialty_armorvest,specialty_fastreload;count=2;map=nazi_zombie_factory",
                "dvar set gauntlet_event GAUNTLET_EVENT|PERKS_RESTORED|player=n_player;perks=specialty_armorvest,specialty_fastreload;count=2;maxhealth=160;map=nazi_zombie_prototype",
            ]
        )
        _, errs = self.verify_perks.analyze_perk_carryover_log(valid_log)
        self.assertEqual(errs, [])

        bad_hp = valid_log.replace("maxhealth=160", "maxhealth=100")
        _, errs_hp = self.verify_perks.analyze_perk_carryover_log(bad_hp)
        self.assertTrue(any("maxhealth" in e for e in errs_hp))

        _, errs_classic = self.verify_perks.analyze_classic_perks_isolation_log(
            "dvar set gauntlet_event GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_prototype;gauntlet_enabled=0\n"
        )
        self.assertEqual(errs_classic, [])

        _, errs_leak = self.verify_perks.analyze_classic_perks_isolation_log(
            "dvar set gauntlet_event GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_prototype;gauntlet_enabled=0\n"
            "dvar set gauntlet_event GAUNTLET_EVENT|PERKS_RESTORED|player=n_player;perks=none;count=0;maxhealth=100;map=nazi_zombie_prototype\n"
        )
        self.assertTrue(any("PERKS_RESTORED" in e for e in errs_leak))


if __name__ == "__main__":
    unittest.main()
