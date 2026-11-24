"""Offline TDD contract suite for P1-T1 (#12): Base Zombies Framework, Feature Gates,
Shared Hooks, Stock Script Patchers, and Solo/Co-op Enhancements Menus.

Executes real WaW 1.7 `.gsc` files (`mod/maps/_bz_log.gsc`, `mod/maps/_bz_hooks.gsc`)
through an extended GSC runtime built on `tests/gsc_runtime.py` (without modifying it),
and verifies build-time stock script/menu patchers and `mod/ui/` contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Any, Callable
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_ROOT = REPO_ROOT / "mod"
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tests.gsc_runtime import (  # noqa: E402
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
    PostfixUpdateExpr,
    UNDEFINED,
    VarRef,
    _waw_to_str,
    tokenize,
)

BZ_LOG_MOD = "maps\\_bz_log"
BZ_HOOKS_MOD = "maps\\_bz_hooks"
BZ_LOG_PATH = MOD_ROOT / "maps" / "_bz_log.gsc"
BZ_HOOKS_PATH = MOD_ROOT / "maps" / "_bz_hooks.gsc"


# ---------------------------------------------------------------------------
# Extended WaW 1.7 GSC Parser & Runtime (built on tests/gsc_runtime.py)
# Supports: level/self globals, function pointers (::fn, mod::fn),
# indirect calls ([[ fn ]](args), ent [[ fn ]](args)), entity method calls,
# `thread`, `endon`, `waittill`, `notify`, and fake player/zombie entities.
# ---------------------------------------------------------------------------


@dataclass
class FuncPtrExpr:
    module_path: str | None
    func_name: str
    line: int


@dataclass
class IndirectCallExpr:
    receiver: Any | None
    fn_expr: Any
    args: list[Any]
    threaded: bool
    line: int


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


@dataclass
class VectorExpr:
    x: Any
    y: Any
    z: Any


@dataclass(frozen=True)
class GscFuncPtr:
    module_key: str
    func_name: str


class _EndonSignal(Exception):
    pass


class _WaittillSuspend(Exception):
    def __init__(self, receiver: Any, event_name: str, out_vars: list[str]) -> None:
        self.receiver = receiver
        self.event_name = event_name
        self.out_vars = out_vars


class FakeEntity(GscStruct):
    """Fake WaW 1.7 player, zombie, or world entity for offline hook contract tests."""

    def __init__(self, name: str = "player_0", ent_num: int = 0, is_player: bool = True) -> None:
        super().__init__()
        self.set_field("playername", name)
        self.set_field("name", name)
        self.set_field("health", 100)
        self.set_field("maxhealth", 100)
        self.set_field("score", 500)
        self._ent_num = ent_num
        self._perks: set[str] = set()
        self.speed_scale_calls: list[float] = []
        self.is_player = is_player
        self.classname = "player" if is_player else name
        self.client_dvars: dict[str, str] = {}
        self.opened_menus: list[str] = []
        self.closed_menus: int = 0
        self.weapons: set[str] = set()
        self.current_weapon: str = "colt"
        self.use_pressed: bool = False
        self.hint_string: str = ""
        self.cursor_hint: str = ""
        self.deleted: bool = False
        self.not_solid: bool = False

    def give_perk(self, perk: str) -> None:
        self._perks.add(perk.lower())

    def clear_perks(self) -> None:
        self._perks.clear()

    def has_perk(self, perk: str) -> bool:
        return perk.lower() in self._perks

    def give_weapon(self, weapon: str, make_current: bool = False) -> None:
        norm = weapon.lower()
        self.weapons.add(norm)
        if make_current:
            self.current_weapon = norm


class BzGscParser(Parser):
    """Extends tests.gsc_runtime.Parser with WaW 1.7 function pointers and entity calls."""

    def parse_stmt(self) -> Any:
        tok = self.peek()
        if tok.kind == "IDENT" and tok.value.lower() == "thread":
            self.pos += 1
            if self.peek().kind == "[" and self.peek(1).kind == "[":
                return ExprStmt(self._parse_indirect_call(receiver=None, threaded=True))
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
            return CallExpr(
                module_path=tok.value,
                func_name=fn_tok.value,
                args=args,
                line=fn_tok.line,
            )
        args = self.parse_arg_list()
        return CallExpr(module_path=None, func_name=tok.value, args=args, line=tok.line)

    def _parse_indirect_call(self, receiver: Any | None, threaded: bool) -> IndirectCallExpr:
        open_tok = self.expect("[")
        self.expect("[")
        fn_expr = self.parse_expr()
        self.expect("]")
        self.expect("]")
        args = self.parse_arg_list()
        return IndirectCallExpr(
            receiver=receiver,
            fn_expr=fn_expr,
            args=args,
            threaded=threaded,
            line=open_tok.line,
        )

    def parse_postfix(self) -> Any:
        expr = self.parse_primary()
        while True:
            if self.match("."):
                field = self.expect("IDENT").value
                expr = FieldAccess(expr, field)
            elif self.peek().kind == "[" and self.peek(1).kind == "[":
                # Handle `ent [[ fn ]]( args )` BEFORE single-bracket indexing
                expr = self._parse_indirect_call(receiver=expr, threaded=False)
            elif self.match("["):
                idx = self.parse_expr()
                self.expect("]")
                expr = IndexAccess(expr, idx)
            elif self.peek().kind in ("++", "--"):
                op = self.match("++", "--")
                assert op is not None
                expr = PostfixUpdateExpr(expr, op.kind)
            elif self.peek().kind == "IDENT":
                lower = self.peek().value.lower()
                if lower == "thread":
                    self.pos += 1
                    if self.peek().kind == "[" and self.peek(1).kind == "[":
                        expr = self._parse_indirect_call(receiver=expr, threaded=True)
                        continue
                    target = self._parse_call_target()
                    expr = MethodCallExpr(
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
                    continue
                if self.peek(1).kind == "::":
                    target = self._parse_call_target()
                    expr = MethodCallExpr(
                        receiver=expr,
                        method_name=f"{target.module_path}::{target.func_name}",
                        args=target.args,
                        threaded=False,
                        line=target.line,
                    )
                    continue
                if self.peek(1).kind == "(":
                    method_tok = self.expect("IDENT")
                    args = self.parse_arg_list()
                    expr = MethodCallExpr(
                        receiver=expr,
                        method_name=method_tok.value,
                        args=args,
                        threaded=False,
                        line=method_tok.line,
                    )
                    continue
                break
            else:
                break
        return expr

    def parse_primary(self) -> Any:
        tok = self.peek()
        # Parenthesized expression OR WaW 1.7 3D vector literal `( x, y, z )`
        if tok.kind == "(":
            self.pos += 1
            first = self.parse_expr()
            if self.match(","):
                second = self.parse_expr()
                self.expect(",")
                third = self.parse_expr()
                self.expect(")")
                return VectorExpr(first, second, third)
            self.expect(")")
            return first
        # Function pointer literal: `::func_name`
        if tok.kind == "::":
            self.pos += 1
            fn_tok = self.expect("IDENT")
            return FuncPtrExpr(module_path=None, func_name=fn_tok.value, line=fn_tok.line)
        # Indirect call without receiver: `[[ fn ]]( args )`
        if tok.kind == "[" and self.peek(1).kind == "[":
            return self._parse_indirect_call(receiver=None, threaded=False)
        # Module function pointer vs call: `maps\_mod::fn` vs `maps\_mod::fn(...)`
        if tok.kind == "IDENT" and self.peek(1).kind == "::":
            mod_tok = self.expect("IDENT")
            self.expect("::")
            fn_tok = self.expect("IDENT")
            if self.peek().kind == "(":
                args = self.parse_arg_list()
                return CallExpr(
                    module_path=mod_tok.value,
                    func_name=fn_tok.value,
                    args=args,
                    line=fn_tok.line,
                )
            return FuncPtrExpr(
                module_path=mod_tok.value,
                func_name=fn_tok.value,
                line=fn_tok.line,
            )
        return super().parse_primary()


class BzGscRuntime(GscRuntime):
    """Executes WaW 1.7 Base Zombies hook scripts with fake entities and callbacks."""

    def __init__(self, mod_root: Path, dvars: FakeDvarStore | None = None) -> None:
        super().__init__(mod_root, dvars)
        self.level = GscStruct()
        self.level.set_field("script", "nazi_zombie_factory")
        self.players: list[FakeEntity] = []
        self.emitted_events: list[str] = []
        self.player_prints: list[tuple[FakeEntity, str]] = []
        self.played_local_sounds: list[tuple[FakeEntity, str]] = []
        self._py_callbacks: dict[str, Callable[..., Any]] = {}
        self._current_self: Any = self.level
        self._threads: list[tuple[Any, str, list[Any]]] = []
        self.precached_menus: list[str] = []
        self.precached_items: list[str] = []
        self.spawned_entities: list[FakeEntity] = []
        self.world_entities: dict[tuple[str, str], list[FakeEntity]] = {}
        self.bullet_trace_fn: Callable[[GscArray, GscArray], dict[str, Any]] | None = None
        self.sim_time_ms: int = 1000
        self.notifies: list[tuple[Any, str]] = []

    def register_py_callback(self, name: str, fn: Callable[..., Any]) -> GscFuncPtr:
        key = name.lower()
        self._py_callbacks[key] = fn
        return GscFuncPtr(module_key="__py__", func_name=key)

    def load_module(self, module_path: str) -> dict[str, FunctionDef]:
        key = self.normalize_module_key(module_path)
        if key not in self._modules:
            gsc_file = self.mod_root / f"{key}.gsc"
            if not gsc_file.is_file():
                raise FileNotFoundError(f"GSC module not found: {gsc_file}")
            source = gsc_file.read_text(encoding="latin1")
            tokens = tokenize(source, filename=str(gsc_file))
            self._modules[key] = BzGscParser(tokens, filename=str(gsc_file)).parse_module()
        return self._modules[key]

    def call_on(self, receiver: Any, module_path: str, func_name: str, *args: Any) -> Any:
        prev_self = self._current_self
        self._current_self = receiver
        try:
            return self.call(module_path, func_name, *args)
        finally:
            self._current_self = prev_self

    def _invoke_ptr(self, receiver: Any, ptr: Any, args: list[Any], line: int) -> Any:
        if not isinstance(ptr, GscFuncPtr):
            raise GscRuntimeError(f"line {line}: cannot call non-function pointer {ptr!r}")
        if ptr.module_key == "__py__":
            cb = self._py_callbacks[ptr.func_name]
            return cb(receiver, *args)
        return self.call_on(receiver, ptr.module_key, ptr.func_name, *args)

    def _call_builtin(self, name_lower: str, args: list[Any], line: int) -> tuple[bool, Any]:
        if name_lower == "println":
            if args:
                self.emitted_events.append(_waw_to_str(args[0]))
            return True, UNDEFINED
        if name_lower == "getplayers":
            return True, GscArray(list(self.players))
        if name_lower == "isalive":
            ent = args[0] if args else UNDEFINED
            if isinstance(ent, FakeEntity):
                return True, int(ent.get_field("health")) > 0
            return True, False
        if name_lower == "isplayer":
            ent = args[0] if args else UNDEFINED
            return True, isinstance(ent, FakeEntity) and ent.is_player
        if name_lower == "wait":
            return True, UNDEFINED
        if name_lower == "gettime":
            return True, self.sim_time_ms
        if name_lower == "issubstr":
            haystack = _waw_to_str(args[0]) if len(args) > 0 else ""
            needle = _waw_to_str(args[1]) if len(args) > 1 else ""
            return True, needle in haystack
        if name_lower == "precachemenu":
            menu = _waw_to_str(args[0]) if args else ""
            self.precached_menus.append(menu)
            return True, UNDEFINED
        if name_lower == "precacheitem":
            item = _waw_to_str(args[0]) if args else ""
            self.precached_items.append(item)
            return True, UNDEFINED
        if name_lower == "precachemodel":
            model = _waw_to_str(args[0]) if args else ""
            self.__dict__.setdefault("precached_models", []).append(model)
            return True, UNDEFINED
        if name_lower == "spawn":
            classname = _waw_to_str(args[0]) if args else "script_origin"
            ent = FakeEntity(name=classname, ent_num=100 + len(self.spawned_entities), is_player=False)
            ent.classname = classname
            ent.set_field("classname", classname)
            if len(args) > 1:
                ent.set_field("origin", args[1])
            if len(args) > 3:
                ent.set_field("radius", args[3])
            if len(args) > 4:
                ent.set_field("height", args[4])
            self.spawned_entities.append(ent)
            return True, ent
        if name_lower == "getentarray":
            val = _waw_to_str(args[0]).lower() if len(args) > 0 else ""
            key = _waw_to_str(args[1]).lower() if len(args) > 1 else ""
            matches = self.world_entities.get((key, val), [])
            return True, GscArray(list(matches))
        if name_lower == "bullettrace":
            start = args[0] if len(args) > 0 else GscArray([0, 0, 0])
            end = args[1] if len(args) > 1 else GscArray([0, 0, 0])
            trace = GscArray()
            if self.bullet_trace_fn is not None:
                res = self.bullet_trace_fn(start, end)
                for k, v in res.items():
                    trace.set_item(k, v)
            else:
                # Default ground plane sits at start_z - 64 (matching original origin.z)
                hit_pos = GscArray([start[0], start[1], start[2] - 64])
                trace.set_item("fraction", 0.25)
                trace.set_item("position", hit_pos)
            return True, trace
        if name_lower == "distance":
            a = args[0]
            b = args[1]
            dx = float(a[0]) - float(b[0])
            dy = float(a[1]) - float(b[1])
            dz = float(a[2]) - float(b[2])
            return True, (dx * dx + dy * dy + dz * dz) ** 0.5
        if name_lower == "getaispeciesarray":
            return True, GscArray([])
        if name_lower == "newclienthudelem":
            elem = GscStruct()
            elem.set_field("owner", args[0] if args else UNDEFINED)
            elem.set_field("destroyed", False)
            return True, elem
        if name_lower == "weaponmaxammo":
            return True, 160
        if name_lower == "weaponclipsize":
            return True, 30
        if name_lower == "loadfx":
            fx_path = _waw_to_str(args[0]) if args else ""
            return True, f"fx:{fx_path}"
        if name_lower in ("playfx", "triggerfx", "earthquake"):
            return True, UNDEFINED
        if name_lower == "spawnfx":
            ent = FakeEntity(name="script_fx", ent_num=200 + len(self.spawned_entities), is_player=False)
            if len(args) > 1:
                ent.set_field("origin", args[1])
            self.spawned_entities.append(ent)
            return True, ent
        return super()._call_builtin(name_lower, args, line)

    def _read_target(self, target: Any, mod_key: str, env: dict[str, Any]) -> Any:
        if isinstance(target, VarRef):
            lower = target.name.lower()
            if lower == "level":
                return self.level
            if lower == "self":
                return self._current_self
        return super()._read_target(target, mod_key, env)

    def _eval_expr(self, expr: Any, mod_key: str, env: dict[str, Any]) -> Any:
        if isinstance(expr, VectorExpr):
            return GscArray(
                [
                    self._eval_expr(expr.x, mod_key, env),
                    self._eval_expr(expr.y, mod_key, env),
                    self._eval_expr(expr.z, mod_key, env),
                ]
            )
        if isinstance(expr, VarRef):
            lower = expr.name.lower()
            if lower == "level":
                return self.level
            if lower == "self":
                return self._current_self
        if isinstance(expr, FuncPtrExpr):
            target_mod = self.normalize_module_key(expr.module_path) if expr.module_path else mod_key
            return GscFuncPtr(module_key=target_mod, func_name=expr.func_name.lower())
        if isinstance(expr, IndirectCallExpr):
            receiver = (
                self._eval_expr(expr.receiver, mod_key, env)
                if expr.receiver is not None
                else self._current_self
            )
            fn_val = self._eval_expr(expr.fn_expr, mod_key, env)
            eval_args = [self._eval_expr(a, mod_key, env) for a in expr.args]
            if expr.threaded:
                self._threads.append((receiver, repr(fn_val), eval_args))
                return UNDEFINED
            return self._invoke_ptr(receiver, fn_val, eval_args, expr.line)
        if isinstance(expr, ThreadCallExpr):
            eval_args = [self._eval_expr(a, mod_key, env) for a in expr.args]
            target_mod = expr.module_path if expr.module_path else mod_key
            self._threads.append((self._current_self, f"{target_mod}::{expr.func_name}", eval_args))
            return UNDEFINED
        if isinstance(expr, MethodCallExpr):
            receiver = self._eval_expr(expr.receiver, mod_key, env)
            eval_args = [self._eval_expr(a, mod_key, env) for a in expr.args]
            if expr.threaded:
                self._threads.append((receiver, expr.method_name, eval_args))
                return UNDEFINED
            m_lower = expr.method_name.lower()
            if "::" not in m_lower and m_lower in self.load_module(mod_key):
                return self.call_on(receiver, mod_key, m_lower, *eval_args)
            return self._exec_method(receiver, m_lower, eval_args, expr.line)
        return super()._eval_expr(expr, mod_key, env)

    def _exec_method(self, receiver: Any, method: str, args: list[Any], line: int) -> Any:
        if "::" in method:
            mod_path, fn_name = method.split("::", 1)
            return self.call_on(receiver, mod_path, fn_name, *args)
        if method == "setmodel":
            if isinstance(receiver, FakeEntity):
                receiver.set_field("model", _waw_to_str(args[0]) if args else "")
            return UNDEFINED
        if method == "dodamage":
            if isinstance(receiver, FakeEntity) and args:
                dmg = int(args[0])
                cur_hp = int(receiver.get_field("health")) if receiver.get_field("health") is not UNDEFINED else 100
                receiver.set_field("health", cur_hp - dmg)
                if "damage_events" not in receiver.__dict__:
                    receiver.damage_events = []
                receiver.damage_events.append((dmg, args[1] if len(args) > 1 else UNDEFINED, args[2] if len(args) > 2 else UNDEFINED))
            return UNDEFINED
        if method == "setmovespeedscale":
            if not isinstance(receiver, FakeEntity):
                raise GscRuntimeError(f"line {line}: SetMoveSpeedScale on non-entity {receiver!r}")
            scale = float(args[0]) if args else 1.0
            receiver.speed_scale_calls.append(scale)
            return UNDEFINED
        if method == "hasperk":
            if not isinstance(receiver, FakeEntity):
                return False
            perk = _waw_to_str(args[0]) if args else ""
            return receiver.has_perk(perk)
        if method == "getentitynumber":
            if isinstance(receiver, FakeEntity):
                return receiver._ent_num
            return 0
        if method == "iprintln":
            if not isinstance(receiver, FakeEntity) or not receiver.is_player:
                raise GscRuntimeError(f"line {line}: IPrintLn on non-player {receiver!r}")
            self.player_prints.append((receiver, _waw_to_str(args[0])))
            return UNDEFINED
        if method == "playlocalsound":
            if not isinstance(receiver, FakeEntity) or not receiver.is_player:
                raise GscRuntimeError(f"line {line}: PlayLocalSound on non-player {receiver!r}")
            self.played_local_sounds.append((receiver, _waw_to_str(args[0])))
            return UNDEFINED
        if method == "setclientdvar":
            if not isinstance(receiver, FakeEntity):
                raise GscRuntimeError(f"line {line}: SetClientDvar on non-entity {receiver!r}")
            key = _waw_to_str(args[0]).lower() if len(args) > 0 else ""
            val = _waw_to_str(args[1]) if len(args) > 1 else ""
            receiver.client_dvars[key] = val
            return UNDEFINED
        if method == "openmenu":
            if not isinstance(receiver, FakeEntity):
                raise GscRuntimeError(f"line {line}: openMenu on non-entity {receiver!r}")
            menu = _waw_to_str(args[0]) if args else ""
            receiver.opened_menus.append(menu)
            return UNDEFINED
        if method == "closemenu":
            if not isinstance(receiver, FakeEntity):
                raise GscRuntimeError(f"line {line}: closeMenu on non-entity {receiver!r}")
            receiver.closed_menus += 1
            return UNDEFINED
        if method == "setcursorhint":
            if isinstance(receiver, FakeEntity):
                receiver.cursor_hint = _waw_to_str(args[0]) if args else ""
            return UNDEFINED
        if method == "sethintstring":
            if isinstance(receiver, FakeEntity):
                receiver.hint_string = _waw_to_str(args[0]) if args else ""
            return UNDEFINED
        if method == "delete":
            if isinstance(receiver, FakeEntity):
                receiver.deleted = True
            return UNDEFINED
        if method == "getcurrentweapon":
            if isinstance(receiver, FakeEntity):
                return receiver.current_weapon
            return "none"
        if method == "hasweapon":
            if isinstance(receiver, FakeEntity):
                w = _waw_to_str(args[0]).lower() if args else ""
                return w in receiver.weapons
            return False
        if method == "getweaponslistprimaries":
            if isinstance(receiver, FakeEntity):
                primaries = receiver.__dict__.get("primary_weapons")
                if isinstance(primaries, (list, tuple, set)):
                    return GscArray(list(primaries))
                if receiver.weapons:
                    return GscArray(sorted(receiver.weapons))
                if receiver.current_weapon and receiver.current_weapon != "none":
                    return GscArray([receiver.current_weapon])
            return GscArray([])
        if method == "getweaponslist":
            if isinstance(receiver, FakeEntity):
                if receiver.weapons:
                    return GscArray(sorted(receiver.weapons))
                if receiver.current_weapon and receiver.current_weapon != "none":
                    return GscArray([receiver.current_weapon])
            return GscArray([])
        if method in ("setperk", "unsetperk"):
            if isinstance(receiver, FakeEntity) and args:
                perk = _waw_to_str(args[0]).lower()
                if method == "setperk":
                    receiver.give_perk(perk)
                else:
                    receiver._perks.discard(perk)
            return UNDEFINED
        if method == "giveweapon":
            if isinstance(receiver, FakeEntity) and args:
                receiver.give_weapon(_waw_to_str(args[0]))
            return UNDEFINED
        if method == "takeweapon":
            if isinstance(receiver, FakeEntity) and args:
                w = _waw_to_str(args[0]).lower()
                receiver.weapons.discard(w)
            return UNDEFINED
        if method == "switchtoweapon":
            if isinstance(receiver, FakeEntity) and args:
                receiver.current_weapon = _waw_to_str(args[0]).lower()
            return UNDEFINED
        if method in ("givemaxammo", "setweaponammoclip", "setweaponammostock"):
            if isinstance(receiver, FakeEntity) and args:
                w = _waw_to_str(args[0]).lower()
                if method == "setweaponammoclip" and len(args) > 1:
                    if "weapon_clips" not in receiver.__dict__:
                        receiver.weapon_clips = {}
                    receiver.weapon_clips[w] = int(args[1])
                elif method == "setweaponammostock" and len(args) > 1:
                    if "weapon_stocks" not in receiver.__dict__:
                        receiver.weapon_stocks = {}
                    receiver.weapon_stocks[w] = int(args[1])
            return UNDEFINED
        if method == "getweaponammoclip":
            if isinstance(receiver, FakeEntity) and args:
                w = _waw_to_str(args[0]).lower()
                return receiver.__dict__.get("weapon_clips", {}).get(w, 0)
            return 0
        if method == "getweaponammostock":
            if isinstance(receiver, FakeEntity) and args:
                w = _waw_to_str(args[0]).lower()
                return receiver.__dict__.get("weapon_stocks", {}).get(w, 0)
            return 0
        if method == "settext":
            if isinstance(receiver, GscStruct):
                receiver.set_field("text", _waw_to_str(args[0]) if args else "")
            return UNDEFINED
        if method == "destroy":
            if isinstance(receiver, GscStruct):
                receiver.set_field("destroyed", True)
            return UNDEFINED
        if method == "getcurrentoffhand":
            if isinstance(receiver, FakeEntity):
                return receiver.__dict__.get("current_offhand", "stielhandgranate")
            return "stielhandgranate"
        if method == "isonground":
            if isinstance(receiver, FakeEntity):
                return bool(receiver.__dict__.get("on_ground", True))
            return True
        if method == "getvelocity":
            if isinstance(receiver, FakeEntity):
                vel = receiver.__dict__.get("velocity", (0.0, 0.0, 0.0))
                return GscArray(list(vel))
            return GscArray([0.0, 0.0, 0.0])
        if method == "setvelocity":
            if isinstance(receiver, FakeEntity) and args:
                receiver.velocity = args[0]
            return UNDEFINED
        if method == "setcontents":
            if isinstance(receiver, FakeEntity) and args:
                old = receiver.__dict__.get("contents", 1)
                receiver.contents = int(args[0])
                return old
            return 1
        if method == "notsolid":
            if isinstance(receiver, FakeEntity):
                receiver.not_solid = True
            return UNDEFINED
        if method == "playerads":
            if isinstance(receiver, FakeEntity):
                return float(receiver.__dict__.get("ads_fraction", 0.0))
            return 0.0
        if method == "notifyoncommand":
            if isinstance(receiver, FakeEntity) and len(args) >= 2:
                if "notify_commands" not in receiver.__dict__:
                    receiver.notify_commands = []
                receiver.notify_commands.append((_waw_to_str(args[0]), _waw_to_str(args[1])))
            return UNDEFINED
        if method == "usebuttonpressed":
            if isinstance(receiver, FakeEntity):
                return receiver.use_pressed
            return False
        if method == "notify":
            ev = _waw_to_str(args[0]) if args else ""
            self.notifies.append((receiver, ev))
            return UNDEFINED
        if method in ("endon", "waittill"):
            return UNDEFINED
        raise GscRuntimeError(f"line {line}: unsupported method {method!r} on {receiver!r}")


# ---------------------------------------------------------------------------
# Slice 1: Structured BZ_EVENT Telemetry & Modular Feature Gates
# ---------------------------------------------------------------------------


class TestBzLogGsc(unittest.TestCase):
    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzGscRuntime(MOD_ROOT, self.dvars)

    def test_bz_log_emits_structured_ascii_events_and_resets_duplicate_dvar(self) -> None:
        kv_pair = self.gsc.call(BZ_LOG_MOD, "kv", "map", "nazi_zombie_factory")
        self.assertEqual(kv_pair, "map=nazi_zombie_factory")

        fields = GscArray(["map=nazi_zombie_factory", "perks=1", "classes=1"])
        joined = self.gsc.call(BZ_LOG_MOD, "join_fields", fields)
        self.assertEqual(joined, "map=nazi_zombie_factory;perks=1;classes=1")

        self.gsc.call(BZ_LOG_MOD, "emit", "BZ_INIT", joined)
        expected = "BZ_EVENT|BZ_INIT|map=nazi_zombie_factory;perks=1;classes=1"
        self.assertEqual(self.dvars.get("bz_event"), expected)
        self.assertEqual(self.gsc.emitted_events, [expected])
        self.assertTrue(all(32 <= ord(ch) <= 126 for ch in expected))

        # log_event alias emits identical format
        self.gsc.call(BZ_LOG_MOD, "log_event", "ROUND_START", "round=2")
        self.assertEqual(self.dvars.get("bz_event"), "BZ_EVENT|ROUND_START|round=2")
        self.assertEqual(len(self.gsc.emitted_events), 2)

    def test_bz_log_is_waw17_compliant(self) -> None:
        source = BZ_LOG_PATH.read_text(encoding="latin1")
        tokenize(source, filename=str(BZ_LOG_PATH))
        code_only = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
        self.assertIsNone(re.search(r"\bforeach\b", code_only))


class TestBzFeatureGates(unittest.TestCase):
    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzGscRuntime(MOD_ROOT, self.dvars)

    def test_all_feature_gates_default_to_disabled_in_classic_mode(self) -> None:
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_enabled"))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_perks_enabled"))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_classes_enabled"))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_pap_enabled"))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_elements_enabled"))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_companions_enabled"))

    def test_master_gate_off_overrides_individual_subsystem_dvars(self) -> None:
        self.dvars.set("bz_enabled", "0")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")
        self.dvars.set("bz_elements_enabled", "1")
        self.dvars.set("bz_companions_enabled", "1")

        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_enabled"))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_perks_enabled"))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_classes_enabled"))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_pap_enabled"))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_elements_enabled"))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_companions_enabled"))

    def test_subsystem_gates_toggle_independently_when_bz_enabled(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "0")
        self.dvars.set("bz_pap_enabled", "1")
        self.dvars.set("bz_elements_enabled", "0")
        self.dvars.set("bz_companions_enabled", "0")

        self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_enabled"))
        self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_perks_enabled"))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_classes_enabled"))
        self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_pap_enabled"))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_elements_enabled"))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_companions_enabled"))

        # Flip classes & reserved gates independently
        self.dvars.set("bz_perks_enabled", "0")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_elements_enabled", "1")
        self.dvars.set("bz_companions_enabled", "1")

        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_perks_enabled"))
        self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_classes_enabled"))
        self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_elements_enabled"))
        self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_companions_enabled"))


# ---------------------------------------------------------------------------
# Slice 2: Classic Mode Noop, Shared Hook Seams, Composition & WaW 1.7 Safety
# ---------------------------------------------------------------------------


class TestBzHooksAndComposition(unittest.TestCase):
    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzGscRuntime(MOD_ROOT, self.dvars)
        self.player = FakeEntity("PlayerOne", ent_num=0)
        self.zombie = FakeEntity("Zombie_1", ent_num=10)
        self.zombie.set_field("health", 500)
        self.zombie.set_field("maxhealth", 500)
        self.gsc.players.append(self.player)

    def _enable_all_phase1(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")

    def test_classic_mode_is_complete_noop_across_all_hooks(self) -> None:
        self.dvars.set("bz_enabled", "0")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")

        # Register a stock/Gauntlet damage callback to ensure Classic preserves it
        stock_calls: list[int] = []
        stock_cb = self.gsc.register_py_callback(
            "stock_dmg",
            lambda _self, _inf, _att, dmg, *_rest: (stock_calls.append(int(dmg)), int(dmg))[1],
        )
        self.gsc.level.set_field("overrideplayerdamage", stock_cb)

        # Register a BZ hook that MUST NOT fire in Classic Mode
        fired: list[str] = []
        hook_cb = self.gsc.register_py_callback(
            "should_not_fire",
            lambda _self, *_args: (fired.append("fired"), 999)[1],
        )
        self.gsc.call(BZ_HOOKS_MOD, "bz_register_hook", "init", hook_cb, "core")
        self.gsc.call(BZ_HOOKS_MOD, "bz_register_hook", "max_primary_weapons", hook_cb, "perks")
        self.gsc.call(BZ_HOOKS_MOD, "bz_register_hook", "actor_damage", hook_cb, "perks")
        self.gsc.call(BZ_HOOKS_MOD, "bz_register_hook", "points_modify", hook_cb, "classes")
        self.gsc.call(BZ_HOOKS_MOD, "bz_register_hook", "box_cost_modify", hook_cb, "classes")
        self.gsc.call(BZ_HOOKS_MOD, "bz_register_hook", "menu_response", hook_cb, "core")

        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", self.player)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_spawned", self.player)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_downed", self.player)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_round_start", 1)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")

        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", self.player), 2)
        self.assertEqual(
            self.gsc.call_on(
                self.player,
                BZ_HOOKS_MOD,
                "bz_player_damage_override",
                self.zombie,
                self.zombie,
                45,
                0,
                "MOD_MELEE",
                "none",
                UNDEFINED,
                UNDEFINED,
                "none",
                0,
                0,
            ),
            45,
        )
        self.assertEqual(
            self.gsc.call(
                BZ_HOOKS_MOD,
                "bz_actor_damage_dispatch",
                self.zombie,
                self.player,
                self.player,
                120,
                0,
                "MOD_RIFLE_BULLET",
                "thompson",
                UNDEFINED,
                UNDEFINED,
                "torso_upper",
                0,
            ),
            120,
        )
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_points_modify", self.player, 100, "kill"), 100)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_box_cost_modify", self.player, 950), 950)
        self.assertFalse(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.player, "bz_perk_station", "buy_staminup")
        )
        self.assertAlmostEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_speed", self.player), 1.0)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_max_health", self.player), 100)

        self.assertEqual(fired, [])
        self.assertEqual(self.gsc.emitted_events, [])
        self.assertEqual(self.player.speed_scale_calls, [])
        self.assertEqual(self.gsc.level.get_field("overrideplayerdamage"), stock_cb)
        self.assertIs(self.gsc.level.get_field("bz_initialized"), UNDEFINED)

    def test_bz_init_and_lifecycle_hooks_emit_telemetry_and_dispatch(self) -> None:
        self._enable_all_phase1()
        seen: list[tuple[str, Any]] = []

        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "init",
            self.gsc.register_py_callback("on_init", lambda _s: seen.append(("init", None))),
            "core",
        )
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "player_connect",
            self.gsc.register_py_callback("on_conn", lambda _s, p: seen.append(("connect", p.get_field("name")))),
            "core",
        )
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "player_spawned",
            self.gsc.register_py_callback("on_spwn", lambda _s, p: seen.append(("spawn", p.get_field("name")))),
            "core",
        )
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "player_downed",
            self.gsc.register_py_callback("on_down", lambda _s, p: seen.append(("down", p.get_field("name")))),
            "perks",
        )
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "round_start",
            self.gsc.register_py_callback("on_rnd", lambda _s, r: seen.append(("round", int(r)))),
            "classes",
        )
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "end_game",
            self.gsc.register_py_callback("on_end", lambda _s: seen.append(("end", None))),
            "core",
        )

        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        # Calling bz_init a second time must be idempotent
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_spawned", self.player)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_downed", self.player)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_round_start", 5)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")

        self.assertEqual(
            seen,
            [
                ("init", None),
                ("connect", "PlayerOne"),
                ("spawn", "PlayerOne"),
                ("down", "PlayerOne"),
                ("round", 5),
                ("end", None),
            ],
        )
        self.assertIn(
            "BZ_EVENT|BZ_INIT|map=nazi_zombie_factory;perks=1;classes=1;pap=1;elements=0;companions=0",
            self.gsc.emitted_events,
        )
        self.assertIn("BZ_EVENT|ROUND_START|round=5", self.gsc.emitted_events)
        self.assertIn("BZ_EVENT|END_GAME|map=nazi_zombie_factory", self.gsc.emitted_events)
        # Fix #6: bz_on_end_game emits level notify("end_game") idempotently after cleanup
        end_notifies = [ev for target, ev in self.gsc.notifies if target is self.gsc.level and ev == "end_game"]
        self.assertEqual(len(end_notifies), 1)
        # Calling bz_on_end_game a second time must be an idempotent noop (no loop / duplicate telemetry)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        end_notifies_after = [ev for target, ev in self.gsc.notifies if target is self.gsc.level and ev == "end_game"]
        self.assertEqual(len(end_notifies_after), 1)

    def test_global_actor_damage_wrapper_applies_extra_damage_with_reentrancy_guard(self) -> None:
        self._enable_all_phase1()
        stock_calls: list[str] = []
        stock_dmg = self.gsc.register_py_callback(
            "stock_zombie_dmg",
            lambda _self, mod, *_rest: stock_calls.append(str(mod)),
        )
        self.gsc.level.set_field("global_damage_func", stock_dmg)
        self.gsc.level.set_field("global_damage_func_ads", stock_dmg)
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

        self.assertTrue(self.gsc.level.get_field("bz_actor_damage_hooked"))
        self.assertEqual(self.gsc.level.get_field("bz_prev_global_damage_func"), stock_dmg)
        self.assertEqual(self.gsc.level.get_field("bz_prev_global_damage_func_ads"), stock_dmg)

        # Register 2x multiplier hook on actor_damage
        def double_dmg(_s: Any, _z: Any, ctx: GscStruct) -> None:
            ctx.set_field("damage_mult", ctx.get_field("damage_mult") * 2.0)

        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "actor_damage",
            self.gsc.register_py_callback("double_dmg", double_dmg),
            "perks",
        )

        self.zombie.set_field("health", 500)
        self.zombie.set_field("damagetaken", 100)
        self.zombie.set_field("damageweapon", "thompson")
        self.zombie.set_field("origin", GscArray([10, 20, 0]))

        # First call applies stock_dmg + extra 100 damage (200 - 100) via DoDamage
        self.gsc.call_on(
            self.zombie,
            BZ_HOOKS_MOD,
            "bz_global_damage_wrapper",
            "MOD_RIFLE_BULLET",
            "torso_upper",
            GscArray([10, 20, 0]),
            self.player,
            UNDEFINED,
        )
        self.assertEqual(stock_calls, ["MOD_RIFLE_BULLET"])
        self.assertEqual(self.zombie.get_field("health"), 400)
        self.assertTrue(self.zombie.get_field("bz_in_damage_dispatch"))

        # Re-entrant call triggered by our own DoDamage on the same tick MUST short-circuit
        self.gsc.call_on(
            self.zombie,
            BZ_HOOKS_MOD,
            "bz_global_damage_wrapper",
            "MOD_UNKNOWN",
            "none",
            GscArray([10, 20, 0]),
            self.player,
            UNDEFINED,
        )
        self.assertEqual(stock_calls, ["MOD_RIFLE_BULLET"])
        self.assertEqual(self.zombie.get_field("health"), 400)
        self.assertFalse(self.zombie.get_field("bz_in_damage_dispatch"))

    def test_wall_buy_and_unified_revive_time_seams(self) -> None:
        self._enable_all_phase1()
        seen_walls: list[tuple[str, bool]] = []
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "wall_buy",
            self.gsc.register_py_callback(
                "wall_cb",
                lambda _s, _p, w, _o, is_ammo: seen_walls.append((str(w), bool(is_ammo))),
            ),
            "perks",
        )
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_wall_buy", self.player, "thompson", GscArray([0, 0, 0]), True)
        self.assertEqual(seen_walls, [("thompson", True)])

        # Unified revive time: vanilla 3.0s -> QR I 1.5s -> QR II 0.9s -> Field Medic + QR 0.05s
        self.assertAlmostEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_revive_time", self.player, 3.0), 3.0)
        self.player.give_perk("specialty_quickrevive")
        self.assertAlmostEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_revive_time", self.player, 3.0), 1.5)
        self.gsc.call("maps\\_bz_state", "bz_state_ensure_init", self.player)
        self.player.get_field("bz_perks").set_item("quick_revive", True)
        self.player.get_field("bz_perks_t2").set_item("quick_revive", True)
        self.assertAlmostEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_revive_time", self.player, 3.0), 0.9)
        self.player.set_field("bz_class", "medic")
        self.assertAlmostEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_revive_time", self.player, 3.0), 0.05)

    def test_max_primary_weapons_supports_mule_kick_1_and_2_and_respects_perks_gate(self) -> None:
        self._enable_all_phase1()
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", self.player), 2)

        tier_state = {"tier": 1}
        mule_cb = self.gsc.register_py_callback(
            "mule_cap",
            lambda _s, _p, _cap: 3 if tier_state["tier"] == 1 else 4,
        )
        self.gsc.call(BZ_HOOKS_MOD, "bz_register_hook", "max_primary_weapons", mule_cb, "perks")

        # Mule Kick I -> 3 primary weapon slots
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", self.player), 3)

        # Mule Kick II -> 4 primary weapon slots
        tier_state["tier"] = 2
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", self.player), 4)

        # Disabling perks gate alone restores stock 2-weapon cap
        self.dvars.set("bz_perks_enabled", "0")
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", self.player), 2)

    def test_player_damage_override_chains_previous_callback_and_supports_cancel(self) -> None:
        self._enable_all_phase1()
        chain_log: list[str] = []

        # Stock/Gauntlet previous callback adjusts incoming 50 damage to 40
        prev_cb = self.gsc.register_py_callback(
            "prev_player_dmg",
            lambda _self, _inf, _att, dmg, *_rest: (chain_log.append("prev"), int(dmg) - 10)[1],
        )
        self.gsc.level.set_field("overrideplayerdamage", prev_cb)
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

        # Register Blast Shield hook that cancels self-explosive damage
        def blast_shield(_self: Any, _player: Any, ctx: GscStruct) -> None:
            chain_log.append("blast_shield")
            if ctx.get_field("mod") == "MOD_GRENADE_SPLASH":
                ctx.set_field("cancelled", True)

        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "player_damage",
            self.gsc.register_py_callback("blast_shield", blast_shield),
            "perks",
        )

        # Normal zombie melee passes through BZ hooks first, then chains into previous callback (50 -> 40)
        dmg_melee = self.gsc.call_on(
            self.player,
            BZ_HOOKS_MOD,
            "bz_player_damage_override",
            self.zombie,
            self.zombie,
            50,
            0,
            "MOD_MELEE",
            "none",
            UNDEFINED,
            UNDEFINED,
            "none",
            0,
            0,
        )
        self.assertEqual(dmg_melee, 40)
        self.assertEqual(chain_log, ["blast_shield", "prev"])

        # Explosive splash cancelled to 0 by Blast Shield BEFORE prev_cb runs
        # (prevents stock player_damage_override from downing/ending game on intercepted hits)
        chain_log.clear()
        dmg_splash = self.gsc.call_on(
            self.player,
            BZ_HOOKS_MOD,
            "bz_player_damage_override",
            self.player,
            self.player,
            90,
            0,
            "MOD_GRENADE_SPLASH",
            "fraggrenade",
            UNDEFINED,
            UNDEFINED,
            "none",
            0,
            0,
        )
        self.assertEqual(dmg_splash, 0)
        self.assertEqual(chain_log, ["blast_shield"])

    def test_actor_damage_dispatch_composes_multipliers_and_instant_kill_with_gates(self) -> None:
        self._enable_all_phase1()

        # AP I (+35%), Titan standing still (2x), Double PaP (+75%)
        def ap_hook(_s: Any, _z: Any, ctx: GscStruct) -> None:
            ctx.set_field("damage_mult", ctx.get_field("damage_mult") * 1.35)

        def titan_hook(_s: Any, _z: Any, ctx: GscStruct) -> None:
            ctx.set_field("damage_mult", ctx.get_field("damage_mult") * 2.0)

        def double_pap_hook(_s: Any, _z: Any, ctx: GscStruct) -> None:
            if ctx.get_field("mod") == "MOD_MELEE" and ctx.get_field("weapon") == "bowie_knife":
                ctx.set_field("instant_kill", True)
            else:
                ctx.set_field("damage_mult", ctx.get_field("damage_mult") * 1.75)

        self.gsc.call(
            BZ_HOOKS_MOD, "bz_register_hook", "actor_damage", self.gsc.register_py_callback("ap", ap_hook), "perks"
        )
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "actor_damage",
            self.gsc.register_py_callback("titan", titan_hook),
            "classes",
        )
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "actor_damage",
            self.gsc.register_py_callback("dpap", double_pap_hook),
            "pap",
        )

        # Base 100 * 1.35 * 2.0 * 1.75 = 472.5 -> 472 (C-style Int truncation)
        dmg = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            self.zombie,
            self.player,
            self.player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "thompson_upgraded",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg, 472)

        # Turn off classes gate -> 100 * 1.35 * 1.75 = 236.25 -> 236
        self.dvars.set("bz_classes_enabled", "0")
        dmg_no_classes = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            self.zombie,
            self.player,
            self.player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "thompson_upgraded",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg_no_classes, 236)

        # PaP Bowie Knife instant_kill guarantees > zombie.health regardless of round health
        self.zombie.set_field("health", 50000)
        dmg_bowie = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            self.zombie,
            self.player,
            self.player,
            1000,
            0,
            "MOD_MELEE",
            "bowie_knife",
            UNDEFINED,
            UNDEFINED,
            "none",
            0,
        )
        self.assertGreater(dmg_bowie, 50000)

    def test_points_and_box_cost_and_menu_response_hooks(self) -> None:
        self._enable_all_phase1()

        # Broker 2x points + 50% Mystery Box discount
        def broker_pts(_s: Any, _p: Any, ctx: GscStruct) -> None:
            ctx.set_field("multiplier", ctx.get_field("multiplier") * 2.0)

        def broker_box(_s: Any, _p: Any, ctx: GscStruct) -> None:
            ctx.set_field("multiplier", ctx.get_field("multiplier") * 0.5)

        menu_handled: list[tuple[str, str]] = []

        def station_menu(_s: Any, _p: Any, menu: str, resp: str) -> bool:
            if menu == "bz_perk_station":
                menu_handled.append((menu, resp))
                return True
            return False

        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "points_modify",
            self.gsc.register_py_callback("b_pts", broker_pts),
            "classes",
        )
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "box_cost_modify",
            self.gsc.register_py_callback("b_box", broker_box),
            "classes",
        )
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "menu_response",
            self.gsc.register_py_callback("st_menu", station_menu),
            "core",
        )

        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_points_modify", self.player, 130, "kill"), 260)
        # Negative point adjustments (deductions) must never be multiplied
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_points_modify", self.player, -500, "purchase"), -500)
        # Broker 50% Mystery Box discount: 950 -> 475
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_box_cost_modify", self.player, 950), 475)

        # Station menu dispatch
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.player, "bz_perk_station", "buy_staminup")
        )
        self.assertFalse(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.player, "unrelated_menu", "close")
        )
        self.assertEqual(menu_handled, [("bz_perk_station", "buy_staminup")])

    def test_unified_speed_composition_prevents_perk_and_class_stomping(self) -> None:
        self._enable_all_phase1()

        # Stamin-Up II (+25% -> 1.25)
        self.gsc.call(BZ_HOOKS_MOD, "bz_set_speed_modifier", self.player, "staminup", 1.25)
        s1 = self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_speed", self.player)
        self.assertAlmostEqual(s1, 1.25)

        # Daredevil Sprint Burst (+35% -> 1.35) stacks with Stamin-Up II (1.25 * 1.35 = 1.6875)
        self.gsc.call(BZ_HOOKS_MOD, "bz_set_speed_modifier", self.player, "daredevil_burst", 1.35)
        s2 = self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_speed", self.player)
        self.assertAlmostEqual(s2, 1.6875)

        # Clearing Daredevil Sprint Burst restores Stamin-Up II (1.25), NEVER stomps to 1.0!
        self.gsc.call(BZ_HOOKS_MOD, "bz_clear_speed_modifier", self.player, "daredevil_burst")
        s3 = self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_speed", self.player)
        self.assertAlmostEqual(s3, 1.25)
        self.assertAlmostEqual(self.player.speed_scale_calls[-1], 1.25)

    def test_unified_max_health_composition_matches_phase1_worked_examples(self) -> None:
        self._enable_all_phase1()

        # Base vanilla: 100 HP
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_max_health", self.player), 100)
        self.assertEqual(self.player.get_field("maxhealth"), 100)

        # Juggernog I (stock perk): 160 HP
        self.player.give_perk("specialty_armorvest")
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_max_health", self.player), 160)
        self.assertEqual(self.player.get_field("maxhealth"), 160)

        # Juggernog I + Titan (2x): 320 HP
        self.gsc.call(BZ_HOOKS_MOD, "bz_set_max_health_mult", self.player, "titan", 2.0)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_max_health", self.player), 320)
        self.assertEqual(self.player.get_field("maxhealth"), 320)

        # Juggernog II (220 base) + Titan (2x): 440 HP
        self.gsc.call(BZ_HOOKS_MOD, "bz_set_base_max_health", self.player, "juggernog_t2", 220)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_max_health", self.player), 440)
        self.assertEqual(self.player.get_field("maxhealth"), 440)

        # Down clears Juggernog I & II, but Titan class persists -> 200 HP!
        self.player.clear_perks()
        self.gsc.call(BZ_HOOKS_MOD, "bz_clear_base_max_health", self.player, "juggernog_t2")
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_max_health", self.player), 200)
        self.assertEqual(self.player.get_field("maxhealth"), 200)

    def test_bz_hooks_waw17_compliance_no_foreach_and_no_endon_in_sync_callers(self) -> None:
        source = BZ_HOOKS_PATH.read_text(encoding="latin1")
        # Strictly lexes under WaW 1.7 tokenizer (rejects foreach)
        tokenize(source, filename=str(BZ_HOOKS_PATH))
        code_only = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
        self.assertIsNone(re.search(r"\bforeach\b", code_only))

        # Every synchronous public seam MUST NOT call endon() directly
        sync_funcs = {
            "bz_enabled",
            "bz_perks_enabled",
            "bz_classes_enabled",
            "bz_pap_enabled",
            "bz_elements_enabled",
            "bz_companions_enabled",
            "bz_pre_init",
            "bz_init",
            "bz_on_player_connect",
            "bz_on_player_spawned",
            "bz_on_player_downed",
            "bz_on_round_start",
            "bz_on_end_game",
            "bz_get_max_primary_weapons",
            "bz_player_damage_override",
            "bz_actor_damage_dispatch",
            "bz_points_modify",
            "bz_box_cost_modify",
            "bz_on_menu_response",
            "bz_on_wall_buy",
            "bz_get_revive_time",
            "bz_install_actor_damage_hooks",
            "bz_global_damage_wrapper",
            "bz_global_damage_ads_wrapper",
            "bz_recompute_player_speed",
            "bz_recompute_player_max_health",
            "bz_is_dog_entity",
            "bz_is_spawning_dog",
            "bz_recompute_zombie_move_rate",
        }
        module = self.gsc.load_module(BZ_HOOKS_MOD)
        for fn_name in sync_funcs:
            self.assertIn(fn_name, module, f"Missing exported hook function {fn_name}()")
            # Walk AST of this function to ensure zero endon() calls in sync body
            fn_def = module[fn_name]
            self.assertFalse(
                _ast_contains_method_call(fn_def.body, "endon"),
                f"Forbidden endon() inside synchronous caller {fn_name}()",
            )

    def test_hellhound_detection_and_move_rate_protection(self) -> None:
        self._enable_all_phase1()
        self.gsc.sim_time_ms = 5000

        # Undefined and normal zombies are NOT dogs
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_is_dog_entity", UNDEFINED))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_is_dog_entity", self.zombie))
        self.assertFalse(self.gsc.call(BZ_HOOKS_MOD, "bz_is_spawning_dog", self.zombie))

        # Every canonical Hellhound marker is recognized
        for field_name, field_val in (
            ("animname", "zombie_dog"),
            ("targetname", "zombie_dog"),
            ("species", "dog"),
            ("is_dog", True),
        ):
            dog = FakeEntity(f"dog_{field_name}", ent_num=60, is_player=False)
            dog.set_field(field_name, field_val)
            self.assertTrue(
                self.gsc.call(BZ_HOOKS_MOD, "bz_is_dog_entity", dog),
                f"Expected bz_is_dog_entity=True for {field_name}={field_val!r}",
            )
            self.assertFalse(
                self.gsc.call(BZ_HOOKS_MOD, "bz_is_spawning_dog", dog),
                f"Active dog ({field_name}) without spawn flags must not be spawning",
            )

        # Spawning dog during dog_spawn_fx() (ignoreall=True, not bz_stunned) -> skipped untouched
        spawning_dog = FakeEntity("spawning_dog", ent_num=61, is_player=False)
        spawning_dog.set_field("species", "dog")
        spawning_dog.set_field("animname", "zombie_dog")
        spawning_dog.set_field("ignoreall", True)
        spawning_dog.set_field("moveplaybackrate", 1.0)
        spawning_dog.set_field("bz_cryo_frozen_until", 9000)
        spawning_dog.set_field("bz_is_frozen", True)
        self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_is_spawning_dog", spawning_dog))

        rate_spawning = self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", spawning_dog)
        self.assertAlmostEqual(float(rate_spawning), 1.0, places=4)
        self.assertAlmostEqual(float(spawning_dog.get_field("moveplaybackrate")), 1.0, places=4)
        self.assertTrue(spawning_dog.get_field("ignoreall"))
        self.assertIs(spawning_dog.get_field("bz_stunned"), UNDEFINED)

        # Spawning dog with magic_bullet_shield=True -> skipped untouched
        shield_dog = FakeEntity("shield_dog", ent_num=62, is_player=False)
        shield_dog.set_field("animname", "zombie_dog")
        shield_dog.set_field("magic_bullet_shield", True)
        shield_dog.set_field("ignoreall", True)
        shield_dog.set_field("moveplaybackrate", 1.0)
        shield_dog.set_field("bz_tesla_stun_until", 9000)
        self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_is_spawning_dog", shield_dog))
        self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", shield_dog)
        self.assertAlmostEqual(float(shield_dog.get_field("moveplaybackrate")), 1.0, places=4)
        self.assertTrue(shield_dog.get_field("ignoreall"))

        # Active Hellhound under Cryo freeze / Tesla stun / Second Chance stun:
        # NEVER drops below 0.55 and NEVER flips ignoreall to True!
        active_dog = FakeEntity("active_dog", ent_num=63, is_player=False)
        active_dog.set_field("species", "dog")
        active_dog.set_field("animname", "zombie_dog")
        active_dog.set_field("ignoreall", False)
        active_dog.set_field("moveplaybackrate", 1.0)

        active_dog.set_field("bz_is_frozen", True)
        active_dog.set_field("bz_cryo_frozen_until", 9000)
        rate_frozen = self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", active_dog)
        self.assertAlmostEqual(float(rate_frozen), 0.55, places=4)
        self.assertAlmostEqual(float(active_dog.get_field("moveplaybackrate")), 0.55, places=4)
        self.assertFalse(active_dog.get_field("ignoreall"))

        # Acid slow on active dog applies 0.60 (>= 0.55 floor)
        active_dog.set_field("bz_is_frozen", False)
        active_dog.set_field("bz_cryo_frozen_until", 0)
        active_dog.set_field("bz_acid_slow_until", 9000)
        rate_acid = self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", active_dog)
        self.assertAlmostEqual(float(rate_acid), 0.60, places=4)
        self.assertFalse(active_dog.get_field("ignoreall"))

        # Even if a dog had a lower base rate (0.8), acid slow (0.48) clamps cleanly to 0.55 floor
        slow_dog = FakeEntity("slow_dog", ent_num=64, is_player=False)
        slow_dog.set_field("species", "dog")
        slow_dog.set_field("ignoreall", False)
        slow_dog.set_field("moveplaybackrate", 0.8)
        slow_dog.set_field("bz_acid_slow_until", 9000)
        rate_clamped = self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", slow_dog)
        self.assertAlmostEqual(float(rate_clamped), 0.55, places=4)

        # When debuffs expire, active dog restores to base rate 1.0 without touching ignoreall
        active_dog.set_field("bz_acid_slow_until", 0)
        rate_restored = self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", active_dog)
        self.assertAlmostEqual(float(rate_restored), 1.0, places=4)
        self.assertFalse(active_dog.get_field("ignoreall"))


def _ast_contains_method_call(node: Any, method_lower: str) -> bool:
    if node is None:
        return False
    if isinstance(node, MethodCallExpr) and node.method_name.lower() == method_lower:
        return True
    if isinstance(node, list):
        return any(_ast_contains_method_call(item, method_lower) for item in node)
    if hasattr(node, "__dict__"):
        return any(_ast_contains_method_call(val, method_lower) for val in vars(node).values())
    return False


# ---------------------------------------------------------------------------
# Slice 3: Build Patchers, mod.csv Staging, and Solo/Co-op Enhancements Menus
# ---------------------------------------------------------------------------

SYNTHETIC_ZOMBIEMODE_FULL = (
    "main()\n"
    "{\n"
    "\tmaps\\_zombiemode_weapons::init();\n"
    "\tmaps\\_zombiemode_perks::init();\n"
    "}\n"
    "\n"
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

SYNTHETIC_ZOMBIEMODE_WEAPONS = (
    "weapon_give( weapon, is_upgrade )\n"
    "{\n"
    "\tprimaryWeapons = self GetWeaponsListPrimaries();\n"
    "\tweapon_limit = 2;\n"
    "\tif ( primaryWeapons.size >= 2 )\n"
    "\t{\n"
    "\t\tself TakeWeapon( current_weapon );\n"
    "\t}\n"
    "\tplayers = GetPlayers();\n"
    "\tif ( players.size >= 2 )\n"
    "\t{\n"
    "\t\t// Must NOT be rewritten!\n"
    "\t}\n"
    "}\n"
    "\n"
    "weapon_spawn_think()\n"
    "{\n"
    "\tself waittill( \"trigger\", player );\n"
    "\tprimaries = player GetWeaponsListPrimaries();\n"
    "\tif( primaries.size >= 2 )\n"
    "\t{\n"
    "\t\tplayer TakeWeapon( player GetCurrentWeapon() );\n"
    "\t}\n"
    "}\n"
    "\n"
    "treasure_chest_think()\n"
    "{\n"
    "\tself.zombie_cost = 950;\n"
    "\tself waittill( \"trigger\", user );\n"
    "\tif( user.score >= self.zombie_cost )\n"
    "\t{\n"
    "\t\tuser maps\\_zombiemode_score::minus_to_player_score( self.zombie_cost );\n"
    "\t}\n"
    "}\n"
).encode("latin1")

SYNTHETIC_ZOMBIEMODE_PERKS = (
    "vending_set_perk( perk )\n"
    "{\n"
    "\tif ( perk == \"specialty_armorvest\" )\n"
    "\t{\n"
    "\t\tself.maxhealth = level.zombie_vars[\"zombie_perk_juggernaut_health\"];\n"
    "\t\tself.health = level.zombie_vars[\"zombie_perk_juggernaut_health\"];\n"
    "\t}\n"
    "}\n"
    "\n"
    "perk_think( perk )\n"
    "{\n"
    "\tprimaries = self GetWeaponsListPrimaries();\n"
    "\tif ( primaries.size >= 2 )\n"
    "\t{\n"
    "\t\t// stock check\n"
    "\t}\n"
    "\tself waittill( \"player_downed\" );\n"
    "\tself.maxhealth = 100;\n"
    "}\n"
).encode("latin1")

SYNTHETIC_ZOMBIEMODE_SCORE = (
    "add_to_player_score( points )\n"
    "{\n"
    "\tif( !IsDefined( points ) )\n"
    "\t{\n"
    "\t\treturn;\n"
    "\t}\n"
    "\tself.score += points;\n"
    "}\n"
).encode("latin1")


class TestBzBuildPatchersAndMenus(unittest.TestCase):
    def setUp(self) -> None:
        import build_mod
        import verify_hud_menus

        self.bm = build_mod
        self.vhm = verify_hud_menus

    def test_inject_map_hooks_stages_guarded_bz_pre_and_post_init(self) -> None:
        src = (
            "main()\n"
            "{\n"
            "\tmaps\\_zombiemode::main(\"receiver_zone_spawners\");\n"
            "}\n"
        ).encode("latin1")
        patched = self.bm.inject_map_hooks(src, "nazi_zombie_factory").decode("latin1")
        self.assertIn("maps\\_bz_hooks::bz_enabled()", patched)
        self.assertIn("maps\\_bz_hooks::bz_pre_init();", patched)
        self.assertIn("level thread maps\\_bz_hooks::bz_init();", patched)
        self.assertLess(
            patched.index("maps\\_bz_hooks::bz_pre_init();"),
            patched.index("maps\\_zombiemode_gauntlet_factory::main("),
        )
        self.assertLess(
            patched.index("maps\\_zombiemode_gauntlet_factory::main("),
            patched.index("level thread maps\\_bz_hooks::bz_init();"),
        )

    def test_inject_zombiemode_hooks_stages_guarded_bz_lifecycle_and_rewires_wrappers(self) -> None:
        patched = self.bm.inject_zombiemode_hooks(
            SYNTHETIC_ZOMBIEMODE_FULL,
            "nazi_zombie_factory",
            rewire_weapons_module="_zombiemode_weapons_bz_factory",
            rewire_perks_module="_zombiemode_perks_bz_factory",
        ).decode("latin1")

        # Gauntlet hooks remain intact
        self.assertEqual(patched.count("maps\\_gauntlet_mode::is_gauntlet_enabled()"), 4)
        # Base Zombies lifecycle hooks strictly guarded behind bz_enabled()
        self.assertEqual(patched.count("maps\\_bz_hooks::bz_enabled()"), 3)
        self.assertIn("maps\\_bz_hooks::bz_init();", patched)
        self.assertIn("level thread maps\\_bz_hooks::bz_on_round_start( level.round_number );", patched)
        self.assertIn("maps\\_bz_hooks::bz_on_end_game();", patched)
        # Ordering checks
        self.assertLess(patched.index("maps\\_bz_hooks::bz_init();"), patched.index("level thread round_think();"))
        self.assertLess(patched.index("maps\\_bz_hooks::bz_on_round_start("), patched.index("round_wait();"))
        self.assertLess(patched.index("maps\\_bz_hooks::bz_on_end_game();"), patched.index("maps\\_gauntlet_mode::on_end_game()"))
        # Per-map wrapper rewiring preserves era parity
        self.assertIn("maps\\_zombiemode_weapons_bz_factory::init();", patched)
        self.assertIn("maps\\_zombiemode_perks_bz_factory::init();", patched)

    def test_inject_zombiemode_weapons_hooks_replaces_weapon_caps_and_box_cost(self) -> None:
        patched = self.bm.inject_zombiemode_weapons_hooks(SYNTHETIC_ZOMBIEMODE_WEAPONS).decode("latin1")

        self.assertIn("weapon_limit = maps\\_bz_hooks::bz_get_max_primary_weapons( self );", patched)
        self.assertIn("primaryWeapons.size >= maps\\_bz_hooks::bz_get_max_primary_weapons( self )", patched)
        self.assertIn("primaries.size >= maps\\_bz_hooks::bz_get_max_primary_weapons( player )", patched)
        # Must NOT touch unrelated non-weapon .size >= 2 checks
        self.assertIn("if ( players.size >= 2 )", patched)
        # Mystery Box cost routes through bz_box_cost_modify
        self.assertIn("maps\\_bz_hooks::bz_box_cost_modify( user, self.zombie_cost )", patched)

        # Verruckt / Shi No Numa / Der Riese use local `cost` inside treasure_chest_think()
        # and `self.zombie_cost` for wall-buy cabinets in weapon_spawn_think() — only the box must be discounted!
        dlc_weapons = (
            "treasure_chest_think()\n"
            "{\n"
            "\tcost = self.zombie_cost;\n"
            "\tif( is_player_valid( user ) && user.score >= cost )\n"
            "\t{\n"
            "\t\tuser maps\\_zombiemode_score::minus_to_player_score( cost );\n"
            "\t}\n"
            "\telse if ( user.score < cost )\n"
            "\t{\n"
            "\t\tcontinue;\n"
            "\t}\n"
            "}\n"
            "\n"
            "weapon_spawn_think()\n"
            "{\n"
            "\tprimaryWeapons = player GetWeaponsListPrimaries();\n"
            "\tif( primaryWeapons.size >= 2 )\n"
            "\t{\n"
            "\t\tplayer TakeWeapon( player GetCurrentWeapon() );\n"
            "\t}\n"
            "\tplayer maps\\_zombiemode_score::minus_to_player_score( self.zombie_cost );\n"
            "}\n"
        ).encode("latin1")
        dlc_patched = self.bm.inject_zombiemode_weapons_hooks(dlc_weapons).decode("latin1")
        self.assertIn("user.score >= maps\\_bz_hooks::bz_box_cost_modify( user, cost )", dlc_patched)
        self.assertIn("user.score < maps\\_bz_hooks::bz_box_cost_modify( user, cost )", dlc_patched)
        self.assertIn(
            "user maps\\_zombiemode_score::minus_to_player_score( maps\\_bz_hooks::bz_box_cost_modify( user, cost ) );",
            dlc_patched,
        )
        # Wall-buy cabinet in weapon_spawn_think() must remain untouched!
        self.assertIn("player maps\\_zombiemode_score::minus_to_player_score( self.zombie_cost );", dlc_patched)

        # Mule Kick regression: stock !isDefined( current_weapon ) fallback loop in
        # treasure_chest_give_weapon() / weapon_give() must NEVER strip non-Colt weapons
        # when primaryWeapons.size < bz_get_max_primary_weapons( self ).
        mule_box_src = (
            "treasure_chest_give_weapon( weapon_string )\n"
            "{\n"
            "\tprimaryWeapons = self GetWeaponsListPrimaries();\n"
            "\tcurrent_weapon = undefined;\n"
            "\tif( primaryWeapons.size >= 2 )\n"
            "\t{\n"
            "\t\tcurrent_weapon = self getCurrentWeapon();\n"
            "\t\tself TakeWeapon( current_weapon );\n"
            "\t}\n"
            "\tif( IsDefined( primaryWeapons ) && !isDefined( current_weapon ) )\n"
            "\t{\n"
            "\t\tfor( i = 0; i < primaryWeapons.size; i++ )\n"
            "\t\t{\n"
            "\t\t\tself TakeWeapon( primaryWeapons[i] );\n"
            "\t\t}\n"
            "\t}\n"
            "}\n"
        ).encode("latin1")
        mule_patched = self.bm.inject_zombiemode_weapons_hooks(mule_box_src).decode("latin1")
        self.assertIn(
            "if( IsDefined( primaryWeapons ) && !isDefined( current_weapon ) && ( !maps\\_bz_hooks::bz_enabled() || primaryWeapons.size >= maps\\_bz_hooks::bz_get_max_primary_weapons( self ) ) )",
            mule_patched,
        )
        self.assertIn("if ( maps\\_bz_hooks::bz_enabled() ) { break; }", mule_patched)

        with self.assertRaises(ValueError):
            self.bm.inject_zombiemode_weapons_hooks(b"init()\n{\n}\n")

    def test_inject_zombiemode_perks_hooks_routes_weapon_cap_and_max_health_recompute(self) -> None:
        patched = self.bm.inject_zombiemode_perks_hooks(SYNTHETIC_ZOMBIEMODE_PERKS).decode("latin1")

        self.assertIn("primaries.size >= maps\\_bz_hooks::bz_get_max_primary_weapons( self )", patched)
        self.assertEqual(patched.count("maps\\_bz_hooks::bz_recompute_player_max_health( self );"), 2)
        self.assertEqual(patched.count("if ( maps\\_bz_hooks::bz_enabled() )"), 2)
        # Recompute must run AFTER both stock maxhealth and stock health assignments so stock health never clobbers Titan HP
        self.assertLess(
            patched.index('self.health = level.zombie_vars["zombie_perk_juggernaut_health"];'),
            patched.index("maps\\_bz_hooks::bz_recompute_player_max_health( self );"),
        )

        # Verruckt & Shi No Numa assign literal `player.maxhealth = 160;` and Der Riese PaP calls weapon_give
        asylum_perks = (
            "vending_trigger_think()\n"
            "{\n"
            "\tif(perk == \"specialty_armorvest\")\n"
            "\t{\n"
            "\t\tplayer.maxhealth = 160;\n"
            "\t\tplayer.health = 160;\n"
            "\t}\n"
            "\tplayer maps\\_zombiemode_weapons::weapon_give( \"thompson_upgraded\" );\n"
            "}\n"
        ).encode("latin1")
        asylum_patched = self.bm.inject_zombiemode_perks_hooks(
            asylum_perks,
            rewire_weapons_module="_zombiemode_weapons_bz_asylum",
        ).decode("latin1")
        self.assertIn("maps\\_bz_hooks::bz_recompute_player_max_health( player );", asylum_patched)
        self.assertIn("maps\\_zombiemode_weapons_bz_asylum::weapon_give(", asylum_patched)
        # Non-Factory perks scripts lack vending_upgrade() and must patch cleanly without injecting PaP hooks
        self.assertNotIn("bz_pap_try_native_console_upgrade", asylum_patched)
        self.assertNotIn("bz_pap_on_native_weapon_taken", asylum_patched)

    def test_inject_zombiemode_perks_hooks_patches_factory_vending_upgrade_and_pickup(self) -> None:
        factory_perks = (
            "vending_set_perk( perk )\n"
            "{\n"
            "\tif ( perk == \"specialty_armorvest\" )\n"
            "\t{\n"
            "\t\tself.maxhealth = level.zombie_vars[\"zombie_perk_juggernaut_health\"];\n"
            "\t\tself.health = level.zombie_vars[\"zombie_perk_juggernaut_health\"];\n"
            "\t}\n"
            "}\n"
            "\n"
            "vending_upgrade()\n"
            "{\n"
            "\tperk_machine = getent( self.target, \"targetname\" );\n"
            "\tpacka_rollers = spawn( \"script_origin\", self.origin );\n"
            "\tflag_wait( \"Pack_A_Punch_on\" );\n"
            "\tfor( ;; )\n"
            "\t{\n"
            "\t\tself waittill( \"trigger\", player );\n"
            "\t\tcurrent_weapon = player getCurrentWeapon();\n"
            "\t\tif( !IsDefined( level.zombie_include_weapons[current_weapon] ) || !IsDefined( level.zombie_include_weapons[current_weapon + \"_upgraded\"] ) )\n"
            "\t\t{\n"
            "\t\t\tcontinue;\n"
            "\t\t}\n"
            "\t}\n"
            "}\n"
            "\n"
            "wait_for_player_to_take( player, weapon_name, packa_timer )\n"
            "{\n"
            "\tplayer GiveWeapon( weapon_name );\n"
            "\tplayer GiveMaxAmmo( weapon_name );\n"
            "\tplayer SwitchToWeapon( weapon_name );\n"
            "}\n"
        ).encode("latin1")

        patched = self.bm.inject_zombiemode_perks_hooks(
            factory_perks,
            rewire_weapons_module="_zombiemode_weapons_bz_factory",
        ).decode("latin1")

        # 1. Native PaP unlock flag & dedicated build-hook marker set right after flag_wait( "Pack_A_Punch_on" )
        self.assertIn(
            'if ( maps\\_bz_hooks::bz_pap_enabled() ) { level.bz_native_pap_unlocked = true; level.bz_native_pap_unlock_hook_fired = true; }',
            patched,
        )
        self.assertLess(
            patched.index('flag_wait( "Pack_A_Punch_on" );'),
            patched.index("level.bz_native_pap_unlock_hook_fired = true;"),
        )

        # 2. Native console upgrade hook injected right BEFORE stock zombie_include_weapons check
        hook_call = (
            "if ( maps\\_bz_hooks::bz_pap_enabled() && "
            "maps\\_bz_pap::bz_pap_try_native_console_upgrade( self, player, current_weapon, perk_machine, packa_rollers ) )"
        )
        stock_guard = (
            'if( !IsDefined( level.zombie_include_weapons[current_weapon] ) || '
            '!IsDefined( level.zombie_include_weapons[current_weapon + "_upgraded"] ) )'
        )
        self.assertIn(hook_call, patched)
        self.assertIn(stock_guard, patched)
        self.assertLess(patched.index(hook_call), patched.index(stock_guard))

        # 3. Post-pickup hook injected right AFTER GiveMaxAmmo( weapon_name ) in wait_for_player_to_take()
        pickup_hook = "if ( maps\\_bz_hooks::bz_pap_enabled() ) { maps\\_bz_pap::bz_pap_on_native_weapon_taken( player, weapon_name ); }"
        self.assertIn(pickup_hook, patched)
        self.assertLess(patched.index("player GiveMaxAmmo( weapon_name );"), patched.index(pickup_hook))
        self.assertLess(patched.index(pickup_hook), patched.index("player SwitchToWeapon( weapon_name );"))

        # 4. Also supports dual-branch wait_for_player_to_take() (weapon_give at cap + GiveMaxAmmo below cap)
        #    AND level waittill("Pack_A_Punch_on") + stock busy state hooks!
        factory_perks_dual = (
            "vending_set_perk( perk )\n"
            "{\n"
            "\tif ( primaryWeapons.size >= 2 )\n"
            "\t{\n"
            "\t\tself.maxhealth = level.zombie_vars[\"zombie_perk_juggernaut_health\"];\n"
            "\t}\n"
            "}\n"
            "\n"
            "vending_upgrade()\n"
            "{\n"
            "\tlevel waittill( \"Pack_A_Punch_on\" );\n"
            "\tfor( ;; )\n"
            "\t{\n"
            "\t\tself waittill( \"trigger\", player );\n"
            "\t\tcurrent_weapon = player getCurrentWeapon();\n"
            "\t\tif( !IsDefined( level.zombie_include_weapons[current_weapon] ) || !IsDefined( level.zombie_include_weapons[current_weapon + \"_upgraded\"] ) )\n"
            "\t\t{\n"
            "\t\t\tcontinue;\n"
            "\t\t}\n"
            "\t\tself disable_trigger();\n"
            "\t\tself setvisibletoall();\n"
            "\t}\n"
            "}\n"
            "\n"
            "wait_for_player_to_take( player, weapon, packa_timer )\n"
            "{\n"
            "\tif ( primaries.size >= 2 )\n"
            "\t{\n"
            "\t\tplayer maps\\_zombiemode_weapons::weapon_give( weapon+\"_upgraded\" );\n"
            "\t}\n"
            "\telse\n"
            "\t{\n"
            "\t\tplayer GiveWeapon( weapon+\"_upgraded\" );\n"
            "\t\tplayer GiveMaxAmmo( weapon+\"_upgraded\" );\n"
            "\t}\n"
            "\tplayer SwitchToWeapon( weapon+\"_upgraded\" );\n"
            "}\n"
        ).encode("latin1")
        patched_dual = self.bm.inject_zombiemode_perks_hooks(
            factory_perks_dual,
            rewire_weapons_module="_zombiemode_weapons_bz_factory",
        ).decode("latin1")
        self.assertIn("level.bz_native_pap_unlocked = true;", patched_dual)
        self.assertIn("level.bz_native_pap_unlock_hook_fired = true;", patched_dual)
        self.assertIn("self.bz_pap_stock_busy = true;", patched_dual)
        self.assertIn("self.bz_pap_stock_busy = false;", patched_dual)
        take_section = patched_dual.split("wait_for_player_to_take", 1)[1]
        if_part, else_part = take_section.split("else", 1)
        self.assertIn("bz_pap_on_native_weapon_taken( player, weapon+\"_upgraded\" )", if_part)
        self.assertIn("bz_pap_on_native_weapon_taken( player, weapon+\"_upgraded\" )", else_part)

    def test_inject_zombiemode_dogs_hooks_preserves_spawning_marker_through_show(self) -> None:
        stock_dogs = (
            "dog_init()\n"
            "{\n"
            "\tself hide();\n"
            "\tself thread magic_bullet_shield();\n"
            "}\n"
            "\n"
            "dog_spawn_fx( ai, ent )\n"
            "{\n"
            "\tai zombie_setup_attack_properties_dog();\n"
            "\tai stop_magic_bullet_shield();\n"
            "\twait( 0.1 );\n"
            "\tai show();\n"
            "}\n"
        ).encode("latin1")
        patched = self.bm.inject_zombiemode_dogs_hooks(stock_dogs).decode("latin1")
        self.assertIn("if ( maps\\_bz_hooks::bz_enabled() ) { self.bz_spawning_dog = true; }", patched)
        self.assertIn("if ( maps\\_bz_hooks::bz_enabled() ) { ai.bz_spawning_dog = true; }", patched)
        self.assertIn("if ( maps\\_bz_hooks::bz_enabled() ) { ai.bz_spawning_dog = false; }", patched)
        self.assertLess(
            patched.index("ai.bz_spawning_dog = true;"),
            patched.index("ai stop_magic_bullet_shield();"),
        )
        self.assertLess(
            patched.index("ai show();"),
            patched.index("ai.bz_spawning_dog = false;"),
        )

        # Verify generate_staged_mod_csv includes per-map dog/powerups modules and teleporter script
        base_csv = (MOD_ROOT / "mod.csv").read_text(encoding="latin1")
        staged_csv = self.bm.generate_staged_mod_csv(
            base_csv,
            [
                "maps/_zombiemode_dogs_bz_sumpf.gsc",
                "maps/_zombiemode_dogs_bz_factory.gsc",
                "maps/_zombiemode_powerups_bz_factory.gsc",
                "maps/nazi_zombie_factory_teleporter.gsc",
            ],
        )
        for rel in (
            "maps/_zombiemode_dogs_bz_sumpf.gsc",
            "maps/_zombiemode_dogs_bz_factory.gsc",
            "maps/_zombiemode_powerups_bz_factory.gsc",
            "maps/nazi_zombie_factory_teleporter.gsc",
        ):
            self.assertIn(f"rawfile,{rel}", staged_csv.splitlines())

        # Verify _rewire_stock_module_refs routes Der Riese teleporter & powerups dog callers cleanly
        teleporter_src = (
            "teleporter_dogs()\n{\n"
            "\tmaps\\_zombiemode_dogs::special_dog_spawn( undefined, 4 );\n"
            "\tss thread maps\\_zombiemode_powerups::special_powerup_drop( ss.origin );\n"
            "}\n"
        )
        rewired_tp = self.bm._rewire_stock_module_refs(
            teleporter_src,
            rewire_dogs_module="_zombiemode_dogs_bz_factory",
            rewire_powerups_module="_zombiemode_powerups_bz_factory",
        )
        self.assertIn("maps\\_zombiemode_dogs_bz_factory::special_dog_spawn", rewired_tp)
        self.assertIn("maps\\_zombiemode_powerups_bz_factory::special_powerup_drop", rewired_tp)
        self.assertNotIn("maps\\_zombiemode_dogs::", rewired_tp)

    def test_inject_zombiemode_score_hooks_routes_points_through_bz_points_modify(self) -> None:
        patched = self.bm.inject_zombiemode_score_hooks(SYNTHETIC_ZOMBIEMODE_SCORE).decode("latin1")
        self.assertIn("if ( maps\\_bz_hooks::bz_enabled() )", patched)
        self.assertIn('points = maps\\_bz_hooks::bz_points_modify( self, points, "score" );', patched)

    def test_mod_csv_stages_bz_scripts_and_supports_future_bz_modules(self) -> None:
        mod_csv = (MOD_ROOT / "mod.csv").read_text(encoding="latin1")
        self.assertIn("rawfile,maps/_bz_log.gsc", mod_csv)
        self.assertIn("rawfile,maps/_bz_hooks.gsc", mod_csv)
        self.assertIn("rawfile,maps/_bz_selftest.gsc", mod_csv.splitlines())

        staged = self.bm.generate_staged_mod_csv(
            mod_csv,
            [
                "maps/_bz_log.gsc",
                "maps/_bz_hooks.gsc",
                "maps/_bz_selftest.gsc",
                "maps/_bz_rules.gsc",
                "maps/_bz_state.gsc",
                "maps/_zombiemode_weapons_bz_factory.gsc",
                "maps/_zombiemode_perks_bz_factory.gsc",
            ],
        )
        self.assertEqual(staged.count("rawfile,maps/_bz_log.gsc"), 1)
        self.assertEqual(staged.count("rawfile,maps/_bz_hooks.gsc"), 1)
        self.assertEqual(staged.splitlines().count("rawfile,maps/_bz_selftest.gsc"), 1)
        self.assertIn("rawfile,maps/_bz_rules.gsc", staged)
        self.assertIn("rawfile,maps/_bz_state.gsc", staged)
        self.assertIn("rawfile,maps/_zombiemode_weapons_bz_factory.gsc", staged)
        self.assertIn("rawfile,maps/_zombiemode_perks_bz_factory.gsc", staged)

        staged_with_score_ls = self.bm.generate_staged_mod_csv(
            mod_csv,
            [
                "maps/_zombiemode_score.gsc",
                "maps/_laststand.gsc",
            ],
        )
        self.assertIn("rawfile,maps/_zombiemode_score.gsc", staged_with_score_ls)
        self.assertIn("rawfile,maps/_laststand.gsc", staged_with_score_ls)

    def test_inject_laststand_weapons_wallbuy_and_real_stock_scripts(self) -> None:
        # Synthetic _laststand.gsc patching
        synthetic_ls = (
            "PlayerLastStand()\n"
            "{\n"
            "\tif ( player_all_players_in_laststand() )\n"
            "\t{\n"
            "\t\treturn;\n"
            "\t}\n"
            "}\n"
            "revive_do_revive( playerBeingRevived, reviverGun )\n"
            "{\n"
            "\treviveTime = 3;\n"
            "\tif ( self HasPerk( \"specialty_quickrevive\" ) )\n"
            "\t{\n"
            "\t\treviveTime = reviveTime / 2;\n"
            "\t}\n"
            "}\n"
            "revive_success( reviver )\n"
            "{\n"
            "\tself reviveplayer();\n"
            "}\n"
        ).encode("latin1")
        patched_ls = self.bm.inject_laststand_hooks(synthetic_ls).decode("latin1")
        self.assertIn("reviveTime = maps\\_bz_hooks::bz_get_revive_time( self, 3.0 );", patched_ls)
        self.assertIn("maps\\_bz_perks::bz_perks_apply_revive_completed( reviver, self );", patched_ls)
        self.assertIn("maps\\_bz_perks::bz_perks_try_consume_solo_revive( self )", patched_ls)
        self.assertIn("\tself reviveplayer();", patched_ls)

        # Real installed stock scripts (runs on plebdev-ultra when WaW fastfiles exist)
        try:
            ff = self.bm.resolve_stock_ff(
                "nazi_zombie_factory", self.bm.DEFAULT_STEAM_GAME, self.bm.DEFAULT_TOOLS_ROOT
            )
        except FileNotFoundError:
            ff = None
        if ff is not None:
            for m in self.bm.STOCK_MAPS:
                wp = self.bm.extract_stock_script(
                    m, "maps/_zombiemode_weapons.gsc", self.bm.DEFAULT_STEAM_GAME, self.bm.DEFAULT_TOOLS_ROOT
                )
                wp_patched = self.bm.inject_zombiemode_weapons_hooks(wp).decode("latin1")
                self.assertIn("maps\\_bz_hooks::bz_on_wall_buy( player, self.zombie_weapon_upgrade, self.origin, false )", wp_patched)
                self.assertIn("maps\\_bz_hooks::bz_on_wall_buy( player, self.zombie_weapon_upgrade, self.origin, true )", wp_patched)

            sc = self.bm.extract_stock_script(
                "nazi_zombie_factory", "maps/_zombiemode_score.gsc", self.bm.DEFAULT_STEAM_GAME, self.bm.DEFAULT_TOOLS_ROOT
            )
            sc_patched = self.bm.inject_zombiemode_score_hooks(sc).decode("latin1")
            self.assertIn('cost = maps\\_bz_hooks::bz_points_modify( self, cost, "score" );', sc_patched)
            self.assertIn("points = maps\\_bz_hooks::bz_points_modify( self, points, event );", sc_patched)
            self.assertIn('IsDefined( level.zombie_vars["zombie_powerup_insta_kill_on"] )', sc_patched)
            self.assertNotIn("self achievement_notify(", sc_patched)

            ls = self.bm.extract_stock_script(
                "nazi_zombie_factory", "maps/_laststand.gsc", self.bm.DEFAULT_STEAM_GAME, self.bm.DEFAULT_TOOLS_ROOT
            )
            ls_patched = self.bm.inject_laststand_hooks(ls).decode("latin1")
            self.assertIn("reviveTime = maps\\_bz_hooks::bz_get_revive_time( self, 3.0 );", ls_patched)
            self.assertIn("maps\\_bz_perks::bz_perks_apply_revive_completed( reviver, self );", ls_patched)
            self.assertIn("maps\\_bz_perks::bz_perks_try_consume_solo_revive( self )", ls_patched)

            # Real stock _zombiemode_perks.gsc: Factory hooks native PaP console; Verruckt & Sumpf skip cleanly
            fp = self.bm.extract_stock_script(
                "nazi_zombie_factory", "maps/_zombiemode_perks.gsc", self.bm.DEFAULT_STEAM_GAME, self.bm.DEFAULT_TOOLS_ROOT
            )
            fp_patched = self.bm.inject_zombiemode_perks_hooks(
                fp, rewire_weapons_module="_zombiemode_weapons_bz_factory"
            ).decode("latin1")
            self.assertIn(
                "maps\\_bz_pap::bz_pap_try_native_console_upgrade( self, player, current_weapon, perk_machine, packa_rollers )",
                fp_patched,
            )
            self.assertIn("maps\\_bz_pap::bz_pap_on_native_weapon_taken(", fp_patched)
            for non_factory in ("nazi_zombie_asylum", "nazi_zombie_sumpf"):
                nfp = self.bm.try_extract_stock_script(
                    non_factory, "maps/_zombiemode_perks.gsc", self.bm.DEFAULT_STEAM_GAME, self.bm.DEFAULT_TOOLS_ROOT
                )
                if nfp is not None:
                    nfp_patched = self.bm.inject_zombiemode_perks_hooks(nfp).decode("latin1")
                    self.assertNotIn("bz_pap_try_native_console_upgrade", nfp_patched)

            # Verify stage_mod_files() stages patched _zombiemode_score.gsc and _laststand.gsc into mod.csv
            if (self.bm.DEFAULT_TOOLS_ROOT / "raw" / "ui" / "main.menu").is_file():
                stage_dir = self.bm.stage_mod_files(
                    tools_root=self.bm.DEFAULT_TOOLS_ROOT,
                    steam_game=self.bm.DEFAULT_STEAM_GAME,
                )
                staged_score = (stage_dir / "maps" / "_zombiemode_score.gsc").read_text(encoding="latin1")
                staged_ls = (stage_dir / "maps" / "_laststand.gsc").read_text(encoding="latin1")
                staged_csv = (stage_dir / "mod.csv").read_text(encoding="latin1")
                self.assertIn("maps\\_bz_hooks::bz_points_modify(", staged_score)
                self.assertIn("maps\\_bz_hooks::bz_get_revive_time(", staged_ls)
                self.assertIn("rawfile,maps/_zombiemode_score.gsc", staged_csv)
                self.assertIn("rawfile,maps/_laststand.gsc", staged_csv)

    def test_solo_and_coop_enhancements_menus_are_ascii_balanced_and_preserve_classic_and_gauntlet(self) -> None:
        import tempfile
        from tests.test_gauntlet_hud_menus import (
            SYNTHETIC_STOCK_LEVELS_MENU,
            SYNTHETIC_STOCK_MAIN_MENU,
            SYNTHETIC_STOCK_SYSTEMLINK_LOBBY_MENU,
            SYNTHETIC_STOCK_XBOXLIVE_LOBBY_MENU,
        )

        # All tracked mod/ui files must be strictly ASCII and brace-balanced
        ui_dir = MOD_ROOT / "ui"
        self.assertEqual(self.vhm.validate_ui_contracts(ui_dir), [])
        for ui_file in sorted(ui_dir.iterdir()):
            if ui_file.is_dir():
                continue
            text = ui_file.read_text(encoding="latin1")
            self.assertEqual(self.vhm.validate_menu_braces(text, filename=ui_file.name), [])
            non_ascii = [ch for ch in text if ord(ch) > 126 or (ord(ch) < 32 and ch not in "\t\r\n")]
            self.assertEqual(non_ascii, [], f"Non-ASCII chars in {ui_file.name}: {non_ascii!r}")

        # Verify bz_menus.inc defines Enhancements Solo/Co-op macros for all 4 Stock Maps + full Gauntlet reset
        bz_inc = (ui_dir / "bz_menus.inc").read_text(encoding="latin1")
        for token in (
            "BZ_SOLO_START_ACTION",
            "BZ_SOLO_START_PROTOTYPE_ACTION",
            "BZ_SOLO_START_ASYLUM_ACTION",
            "BZ_SOLO_START_SUMPF_ACTION",
            "GAUNTLET_CLEAR_RUN_STATE_EXEC",
            "set bz_enabled 1",
            "set bz_perks_enabled 1",
            "set bz_classes_enabled 1",
            "set bz_pap_enabled 1",
            "set gauntlet_enabled 0",
            "map nazi_zombie_factory",
            "map nazi_zombie_prototype",
            "map nazi_zombie_asylum",
            "map nazi_zombie_sumpf",
            "BZ_CLASSIC_MODE_ACTION",
            "set bz_enabled 0",
            "BZ_COOP_SETUP_TOGGLE",
            "BZ_COOP_LOBBY_STATUS_PANEL",
        ):
            self.assertIn(token, bz_inc)

        # Verify Gauntlet Solo & Classic actions explicitly zero all 6 bz_*_enabled gates
        gauntlet_inc = (ui_dir / "gauntlet_menus.inc").read_text(encoding="latin1")
        self.assertIn('#include "ui/bz_menus.inc"', gauntlet_inc)
        for gate in (
            "set bz_enabled 0",
            "set bz_perks_enabled 0",
            "set bz_classes_enabled 0",
            "set bz_pap_enabled 0",
            "set bz_elements_enabled 0",
            "set bz_companions_enabled 0",
        ):
            self.assertIn(gate, gauntlet_inc)

        # Verify pc_gamesetup_coop.menu exposes Enhancements toggle without breaking Gauntlet/Classic
        coop_menu = (ui_dir / "pc_gamesetup_coop.menu").read_text(encoding="latin1")
        self.assertIn("BZ_COOP_SETUP_TOGGLE", coop_menu)
        self.assertIn("accept_bz_enhancements", coop_menu)
        self.assertIn("BZ_CLASSIC_MODE_ACTION", coop_menu)

        # Verify staged stock menus get Enhancements Solo/Co-op patches cleanly with balanced braces
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
            self.vhm.stage_patched_menus(root / "tools", stage_dir)
            self.bm.apply_bz_menu_patches(stage_dir)

            patched_main = (stage_dir / "ui" / "main.menu").read_text(encoding="latin1")
            patched_levels = (stage_dir / "ui" / "levels.menu").read_text(encoding="latin1")
            patched_xbox = (stage_dir / "ui" / "xboxlive_lobby.menu").read_text(encoding="latin1")
            patched_sys = (stage_dir / "ui" / "systemlink_lobby.menu").read_text(encoding="latin1")

            for name, content in (
                ("main.menu", patched_main),
                ("levels.menu", patched_levels),
                ("xboxlive_lobby.menu", patched_xbox),
                ("systemlink_lobby.menu", patched_sys),
            ):
                self.assertEqual(self.vhm.validate_menu_braces(content, filename=name), [])
                non_ascii = [ch for ch in content if ord(ch) > 126 or (ord(ch) < 32 and ch not in "\t\r\n")]
                self.assertEqual(non_ascii, [], f"Non-ASCII chars in patched {name}")

            self.assertIn("ENHANCEMENTS", patched_main)
            self.assertIn("BZ_SOLO_START_ACTION", patched_main)
            for gate in (
                "set bz_enabled 0",
                "set bz_perks_enabled 0",
                "set bz_classes_enabled 0",
                "set bz_pap_enabled 0",
                "set bz_elements_enabled 0",
                "set bz_companions_enabled 0",
            ):
                self.assertIn(gate, patched_main)
            self.assertIn("ENHANCEMENTS: DER RIESE", patched_levels)
            self.assertIn("ENHANCEMENTS: NACHT", patched_levels)
            self.assertIn("ENHANCEMENTS: VERRUCKT", patched_levels)
            self.assertIn("ENHANCEMENTS: SHI NO NUMA", patched_levels)
            self.assertIn("BZ_SOLO_START_ACTION", patched_levels)
            self.assertIn("BZ_SOLO_START_PROTOTYPE_ACTION", patched_levels)
            self.assertIn("BZ_SOLO_START_ASYLUM_ACTION", patched_levels)
            self.assertIn("BZ_SOLO_START_SUMPF_ACTION", patched_levels)
            for dvar in (
                'setdvar bz_enabled "0"',
                'setdvar bz_perks_enabled "0"',
                'setdvar bz_classes_enabled "0"',
                'setdvar bz_pap_enabled "0"',
                'setdvar bz_elements_enabled "0"',
                'setdvar bz_companions_enabled "0"',
            ):
                self.assertIn(dvar, patched_levels)
            self.assertIn("BZ_COOP_LOBBY_STATUS_PANEL", patched_xbox)
            self.assertIn("BZ_COOP_LOBBY_STATUS_PANEL", patched_sys)

    def test_xboxlive_lobby_keeps_online_count_and_gives_build_stamp_separate_space(self) -> None:
        from tests.test_gauntlet_hud_menus import SYNTHETIC_STOCK_XBOXLIVE_LOBBY_MENU

        lobby_count = (
            '\t\titemDef\n\t\t{\n'
            '\t\t\trect 12 38 210 36 CHOICE_HORIZONTAL_ALIGN VERTICAL_ALIGN_TOP\n'
            '\t\t\torigin ORIGIN_DESCRIPTION\n'
            '\t\t\tdvar playlist_totalonline\n'
            '\t\t\tvisible 1\n'
            '\t\t}\n'
        )
        find_game_count = (
            '\t\titemDef\n\t\t{\n'
            '\t\t\trect 4 10 230 14\n'
            '\t\t\tdvar playlist_totalonline\n'
            '\t\t\tvisible 1\n'
            '\t\t}\n'
        )
        stock = SYNTHETIC_STOCK_XBOXLIVE_LOBBY_MENU.replace(
            '\t\t#include "ui/safearea.menu"', lobby_count + '\t\t#include "ui/safearea.menu"'
        )
        stock = stock.replace(
            '\tmenuDef\n\t{\n\t\tname\tleavelobbywarning',
            '\tmenuDef\n\t{\n\t\tname\tpopup_findgame\n' + find_game_count + '\t}\n'
            '\tmenuDef\n\t{\n\t\tname\tleavelobbywarning',
        )
        staged = self.vhm.patch_xboxlive_lobby_menu(stock)
        patched = self.bm.patch_xboxlive_lobby_menu_bz(staged)

        self.assertIn(lobby_count, patched)
        self.assertIn(find_game_count, patched)
        self.assertEqual(self.vhm.validate_menu_braces(patched, filename="xboxlive_lobby.menu"), [])
        self.assertEqual(self.bm.patch_xboxlive_lobby_menu_bz(patched), patched)

        bz_inc = (MOD_ROOT / "ui" / "bz_menus.inc").read_text(encoding="ascii")
        build_item = re.search(r"name\s+bz_lobby_build_text\b.*?decoration", bz_inc, re.DOTALL)
        self.assertIsNotNone(build_item)
        assert build_item is not None
        self.assertRegex(build_item.group(0), r"\bvisible\s+1\b")
        self.assertNotIn("bz_enabled", build_item.group(0))
        # Panel sits at y=178..222, queued BZ banner at y=226..248, stock online count at y=196..232.
        # Build stamp sits below all three at py + ph + 34 (y=256).
        self.assertIn("(py + ph + 34)", build_item.group(0))

    def test_bz_hooks_cross_file_ref_budget_prevents_max_precache_entries(self) -> None:
        # Leave room for stock and Gauntlet scripts in WaW 1.7's 1,024-entry table.
        sources = {}
        for path in (MOD_ROOT / "maps").glob("_bz_*.gsc"):
            source = path.read_text(encoding="latin1")
            sources[path.name] = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
        ref_pattern = r"maps\\[a-zA-Z0-9_]+::[a-zA-Z0-9_]+"
        counts = {name: len(re.findall(ref_pattern, code)) for name, code in sources.items()}
        budgets = {
            "_bz_hooks.gsc": 65,
            "_bz_selftest.gsc": 45,
            "_bz_stations.gsc": 55,
        }
        for name, budget in budgets.items():
            self.assertIn(name, counts)
            with self.subTest(module=name):
                self.assertLessEqual(counts[name], budget)
        self.assertLessEqual(sum(counts.values()), 550, counts)

        selftest_path = MOD_ROOT / "maps" / "_bz_selftest.gsc"
        selftest_code = sources[selftest_path.name]
        self.assertTrue(selftest_path.read_bytes().isascii())
        self.assertNotRegex(selftest_code, r"(?i)\b(?:foreach|NotifyOnCommand)\b")
        # The harness teleports its local player p. AI positions are read-only.
        without_player_teleports = re.sub(r"(?i)\bp\s+SetOrigin\s*\(", "", selftest_code)
        self.assertNotRegex(without_player_teleports, r"(?i)\bSetOrigin\s*\(")

        BzGscRuntime(MOD_ROOT, FakeDvarStore()).load_module(r"maps\_bz_selftest")
        for name, body in re.findall(r"(?ms)^(\w+)\([^\n]*\)\n\{\n(.*?)^\}", selftest_code):
            if not name.startswith("bz_run_"):
                self.assertNotRegex(body, r"(?i)\b(?:endon|wait|waittill\w*|waitframe)\s*\(", name)

    def test_clientscript_callbacks_patch_stages_manifest_and_iwd(self) -> None:
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from zipfile import ZipFile

        import build_mod
        import verify_hud_menus

        stock_1arg = (
            b"localclientconnect(clientNum)\n{\n\tlevel notify(\"connected\");\n}\n"
            b"level_notify(notify_name)\n{\n\tlevel notify(notify_name);\n}\n"
        )
        patched = build_mod.inject_clientscript_callbacks_patch(stock_1arg)
        assert isinstance(patched, bytes)
        self.assertIn(b"level_notify(notify_name, param1, param2)", patched)
        self.assertIn(b"level notify(notify_name, param1, param2);", patched)
        # WaW 1.7 CSC SetClientDvar rejects custom dvars; _callbacks.csc must stay clean.
        self.assertNotIn(b"SetClientDvar", patched)
        # Idempotent when already patched
        self.assertEqual(build_mod.inject_clientscript_callbacks_patch(patched), patched)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = root / "tools"
            stage = root / "stage"
            raw_csc = tools / "raw" / "clientscripts" / "_callbacks.csc"
            raw_csc.parent.mkdir(parents=True)
            raw_csc.write_bytes(stock_1arg)
            (stage / "maps").mkdir(parents=True)
            (stage / "maps" / "_bz_version.gsc").write_text("bz_get_build_id() { return \"0.7.0-dev\"; }\n", encoding="ascii")

            out_csc = build_mod.stage_bz_clientscript_callbacks(
                tools, stage, steam_game=root / "steam"
            )
            self.assertEqual(out_csc, stage / "clientscripts" / "_callbacks.csc")
            assert out_csc is not None
            csc_bytes = out_csc.read_bytes()
            self.assertIn(b"level_notify(notify_name, param1, param2)", csc_bytes)

            updated_csv = build_mod.generate_staged_mod_csv(
                "rawfile,maps/_bz_version.gsc\n",
                ["maps/_bz_version.gsc", "clientscripts/_callbacks.csc"],
            )
            self.assertIn("rawfile,clientscripts/_callbacks.csc", updated_csv)
            self.assertNotRegex(updated_csv, r"(?im)^\s*fx\s*,")

            with patch.object(build_mod, "DIST_DIR", root / "dist"):
                iwd = build_mod.build_iwd(stage)
            with ZipFile(iwd) as archive:
                self.assertIn("clientscripts/_callbacks.csc", archive.namelist())
                self.assertIn(b"level_notify(notify_name, param1, param2)", archive.read("clientscripts/_callbacks.csc"))

        # Retail-visible client-package parity stamp across all 4 station menus
        for menu_path in sorted((MOD_ROOT / "ui").glob("bz_station_*.menu")):
            raw_menu = menu_path.read_text(encoding="latin1")
            stamped = build_mod.stamp_bz_station_menu_build_parity(raw_menu, "0.7.0-abc1234")
            self.assertEqual(
                verify_hud_menus.validate_menu_braces(stamped, filename=menu_path.name),
                [],
                f"Brace imbalance in stamped {menu_path.name}",
            )
            self.assertIn('"BUILD: 0.7.0-abc1234"', stamped)
            self.assertIn('dvarString( "bz_host_build_id" ) != "0.7.0-abc1234"', stamped)
            self.assertIn('BUILD MISMATCH! LOCAL 0.7.0-abc1234 != HOST ', stamped)
            # Idempotent
            self.assertEqual(build_mod.stamp_bz_station_menu_build_parity(stamped, "0.7.0-abc1234"), stamped)
            # Tracked menu remains unstamped
            self.assertNotIn("bz_parity_mismatch", raw_menu)


if __name__ == "__main__":
    unittest.main()
