"""Offline TDD contract suite for P2-T4 (#26): Special Weapons
(War Club, Multi-Crossbow, Blade Boomerang & Portal Grenade).

Exercises real WaW 1.7 `.gsc` source (`mod/maps/_bz_special_weapons.gsc`) through
an extended GSC runtime built on `tests/gsc_runtime.py` + `BzGscRuntime`
(without modifying `tests/gsc_runtime.py`), covering all 5 seams:
  1. Hook registration under Feature Gate `"elements"`, Classic/gate-off noop,
     and War Club per-player melee slot swap + frontal cleave + PaP AOE knockback
     smash with `BulletTrace` wall safety, stock FX, Earthquake, and telemetry.
  2. Multi-Crossbow 3-bolt (`-6`, `0`, `+6`) sticky explosive spread, world/zombie
     attachment, round + Double PaP scaling, Blast Shield self-damage immunity,
     and entity cleanup.
  3. Blade Boomerang primary weapon slot spinning stock `script_model` (`SetContents(0)`),
     wall-safe outbound + curved return flight, 6-unique-zombie pierce cap, Double PaP
     scaling, and zero-leak cleanup on catch, disconnect, and `end_game`.
  4. Portal Grenade dedicated `+actionslot 2` binding via `NotifyOnCommand`, ownership /
     25s cooldown / charge consumption & round-start recharge, stock portal FX,
     thrower + Co-op teammate spawn teleport with anti-stack offset + floor safety +
     `SetTransported(1.5)`, strict zombie exclusion, and entity cleanup.
  5. Special Weapons top-right ASCII HUD badge on lane `y = bz_get_hud_lane_y(68)`,
     redundant `SetText()` suppression, zero-leak disconnect & `end_game` cleanup,
     and WaW 1.7 syntax compliance.
"""

from __future__ import annotations

import math
from pathlib import Path
import re
from typing import Any, Callable
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_ROOT = REPO_ROOT / "mod"

from tests.gsc_runtime import (  # noqa: E402
    FakeDvarStore,
    GscArray,
    GscRuntimeError,
    GscStruct,
    UNDEFINED,
    _waw_to_str,
    tokenize,
)
from tests.test_bz_hooks_and_build import (  # noqa: E402
    BZ_HOOKS_MOD,
    BzGscRuntime,
    FakeEntity,
    _ast_contains_method_call,
)

BZ_SPECIAL_MOD = "maps\\_bz_special_weapons"
BZ_SPECIAL_PATH = MOD_ROOT / "maps" / "_bz_special_weapons.gsc"
BZ_STATE_MOD = "maps\\_bz_state"
BZ_STATIONS_MOD = "maps\\_bz_stations"
BZ_PAP_MOD = "maps\\_bz_pap"


class SpecialHudElem(GscStruct):
    """Fake WaW 1.7 client HUD element created by NewClientHudElem(player)."""

    def __init__(self, owner: FakeEntity | None = None) -> None:
        super().__init__()
        self.owner = owner
        self.text_history: list[str] = []
        self.destroyed: bool = False
        self.destroy_count: int = 0

    @property
    def current_text(self) -> str:
        return self.text_history[-1] if self.text_history else ""


class SpecialFakeEntity(FakeEntity):
    """Extends FakeEntity with aim, movement, linkage, transport, and command logs."""

    def __init__(self, name: str = "player_0", ent_num: int = 0, is_player: bool = True) -> None:
        super().__init__(name=name, ent_num=ent_num, is_player=is_player)
        self.set_field("origin", GscArray([0.0, 0.0, 0.0]))
        self.set_field("angles", GscArray([0.0, 0.0, 0.0]))
        self.eye_offset_z: float = 60.0
        self.damage_events: list[dict[str, Any]] = []
        self.origin_history: list[tuple[float, float, float]] = []
        self.notify_commands: list[tuple[str, str]] = []
        self.transported_calls: list[float] = []
        self.not_solid: bool = False
        self.linked_to: Any = None
        self.move_calls: list[tuple[tuple[float, float, float], float]] = []
        self.rotate_yaw_calls: list[tuple[float, float]] = []
        self.rotate_roll_calls: list[tuple[float, float]] = []
        self.delete_count: int = 0
        self.ads_pressed: bool = False

    def set_pos(self, x: float, y: float, z: float) -> None:
        self.set_field("origin", GscArray([float(x), float(y), float(z)]))

    def get_pos(self) -> tuple[float, float, float]:
        org = self.get_field("origin")
        return (float(org[0]), float(org[1]), float(org[2]))

    def set_angles(self, pitch: float, yaw: float, roll: float = 0.0) -> None:
        self.set_field("angles", GscArray([float(pitch), float(yaw), float(roll)]))


class SpecialWeaponsGscRuntime(BzGscRuntime):
    """Extends BzGscRuntime with WaW 1.7 FX, Earthquake, vector, trace, and entity builtins."""

    def __init__(self, mod_root: Path, dvars: FakeDvarStore | None = None) -> None:
        super().__init__(mod_root, dvars)
        self.ai_enemies: list[SpecialFakeEntity] = []
        self.hud_elems: list[SpecialHudElem] = []
        self.earthquakes: list[dict[str, Any]] = []
        self.played_fx: list[dict[str, Any]] = []
        self.played_sounds_at_pos: list[dict[str, Any]] = []
        self.spawned_fx_entities: list[SpecialFakeEntity] = []
        self.triggered_fx_entities: list[SpecialFakeEntity] = []
        self.load_fx_calls: list[str] = []
        self.trace_handler: Callable[[GscArray, GscArray, bool, Any], dict[str, Any]] | None = None
        self.spawned_special_ents: list[SpecialFakeEntity] = []

    def _call_builtin(self, name_lower: str, args: list[Any], line: int) -> tuple[bool, Any]:
        if name_lower == "loadfx":
            fx_path = _waw_to_str(args[0]) if args else ""
            self.load_fx_calls.append(fx_path)
            return True, f"fx:{fx_path}"
        if name_lower == "playfx":
            fx_id = args[0] if len(args) > 0 else UNDEFINED
            pos = args[1] if len(args) > 1 else GscArray([0, 0, 0])
            self.played_fx.append({"fx": fx_id, "pos": (float(pos[0]), float(pos[1]), float(pos[2]))})
            return True, UNDEFINED
        if name_lower == "playsoundatposition":
            alias = _waw_to_str(args[0]) if len(args) > 0 else ""
            pos = args[1] if len(args) > 1 else GscArray([0, 0, 0])
            self.played_sounds_at_pos.append(
                {"alias": alias, "pos": (float(pos[0]), float(pos[1]), float(pos[2]))}
            )
            return True, UNDEFINED
        if name_lower == "spawnfx":
            fx_id = args[0] if len(args) > 0 else UNDEFINED
            pos = args[1] if len(args) > 1 else GscArray([0, 0, 0])
            ent = SpecialFakeEntity(
                name="script_fx",
                ent_num=600 + len(self.spawned_fx_entities),
                is_player=False,
            )
            ent.classname = "script_fx"
            ent.set_field("classname", "script_fx")
            ent.set_field("fx_handle", fx_id)
            ent.set_field("origin", pos)
            self.spawned_fx_entities.append(ent)
            self.spawned_entities.append(ent)
            self.spawned_special_ents.append(ent)
            return True, ent
        if name_lower == "triggerfx":
            ent = args[0] if args else UNDEFINED
            if isinstance(ent, SpecialFakeEntity):
                ent.set_field("triggered", True)
                self.triggered_fx_entities.append(ent)
            return True, UNDEFINED
        if name_lower == "earthquake":
            scale = float(args[0]) if len(args) > 0 else 0.0
            duration = float(args[1]) if len(args) > 1 else 0.0
            source = args[2] if len(args) > 2 else GscArray([0, 0, 0])
            radius = float(args[3]) if len(args) > 3 else 0.0
            self.earthquakes.append(
                {
                    "scale": scale,
                    "duration": duration,
                    "source": (float(source[0]), float(source[1]), float(source[2])),
                    "radius": radius,
                }
            )
            return True, UNDEFINED
        if name_lower == "anglestoforward":
            ang = args[0] if args else GscArray([0.0, 0.0, 0.0])
            pitch = math.radians(float(ang[0]))
            yaw = math.radians(float(ang[1]))
            fx = math.cos(pitch) * math.cos(yaw)
            fy = math.cos(pitch) * math.sin(yaw)
            fz = -math.sin(pitch)
            return True, GscArray([fx, fy, fz])
        if name_lower == "anglestoright":
            ang = args[0] if args else GscArray([0.0, 0.0, 0.0])
            yaw = math.radians(float(ang[1]))
            return True, GscArray([math.sin(yaw), -math.cos(yaw), 0.0])
        if name_lower == "getaispeciesarray":
            return True, GscArray([z for z in self.ai_enemies if not z.deleted])
        if name_lower == "newclienthudelem":
            if not args or not isinstance(args[0], FakeEntity):
                raise GscRuntimeError(f"line {line}: NewClientHudElem requires a player entity")
            hud = SpecialHudElem(owner=args[0])
            self.hud_elems.append(hud)
            return True, hud
        if name_lower == "spawn":
            classname = _waw_to_str(args[0]) if args else "script_origin"
            ent = SpecialFakeEntity(
                name=classname,
                ent_num=200 + len(self.spawned_entities),
                is_player=False,
            )
            ent.classname = classname
            ent.set_field("classname", classname)
            if len(args) > 1:
                ent.set_field("origin", args[1])
            self.spawned_entities.append(ent)
            self.spawned_special_ents.append(ent)
            return True, ent
        if name_lower == "bullettrace":
            start = args[0] if len(args) > 0 else GscArray([0.0, 0.0, 0.0])
            end = args[1] if len(args) > 1 else GscArray([0.0, 0.0, 0.0])
            hit_chars = bool(args[2]) if len(args) > 2 else False
            ignore_ent = args[3] if len(args) > 3 else UNDEFINED
            trace = GscArray()
            if self.trace_handler is not None:
                res = self.trace_handler(start, end, hit_chars, ignore_ent)
                for k, v in res.items():
                    trace.set_item(k, v)
                return True, trace
            if self.bullet_trace_fn is not None:
                res = self.bullet_trace_fn(start, end)
                for k, v in res.items():
                    trace.set_item(k, v)
                return True, trace
            # Default: unobstructed horizontal traces (fraction=1.0), downward floor traces hit z=0
            if float(end[2]) < float(start[2]) - 50.0 and abs(float(end[0]) - float(start[0])) < 1.0 and abs(float(end[1]) - float(start[1])) < 1.0:
                trace.set_item("fraction", 0.25)
                trace.set_item("position", GscArray([float(start[0]), float(start[1]), 0.0]))
            else:
                trace.set_item("fraction", 1.0)
                trace.set_item("position", GscArray([float(end[0]), float(end[1]), float(end[2])]))
            return True, trace
        return super()._call_builtin(name_lower, args, line)

    def _exec_method(self, receiver: Any, method: str, args: list[Any], line: int) -> Any:
        if isinstance(receiver, SpecialHudElem):
            if method == "settext":
                txt = _waw_to_str(args[0]) if args else ""
                receiver.text_history.append(txt)
                return UNDEFINED
            if method == "destroy":
                receiver.destroyed = True
                receiver.destroy_count += 1
                return UNDEFINED

        if isinstance(receiver, SpecialFakeEntity):
            if method == "geteye":
                x, y, z = receiver.get_pos()
                return GscArray([x, y, z + receiver.eye_offset_z])
            if method == "adsbuttonpressed":
                return bool(receiver.ads_pressed)
            if method == "getplayerangles":
                ang = receiver.get_field("angles")
                if ang is UNDEFINED:
                    return GscArray([0.0, 0.0, 0.0])
                return ang
            if method == "setplayerangles":
                if args:
                    receiver.set_field("angles", args[0])
                return UNDEFINED
            if method in ("setorigin", "forceteleport"):
                if args:
                    if method == "setorigin" and not receiver.is_player:
                        raise RuntimeError(f"WaW 1.7 forbids SetOrigin() on AI actor {receiver}; use ForceTeleport()")
                    pos = args[0]
                    receiver.set_field("origin", GscArray([float(pos[0]), float(pos[1]), float(pos[2])]))
                    receiver.origin_history.append((float(pos[0]), float(pos[1]), float(pos[2])))
                    if method == "forceteleport" and len(args) > 1:
                        receiver.set_field("angles", args[1])
                return UNDEFINED
            if method == "notsolid":
                receiver.not_solid = True
                return UNDEFINED
            if method == "linkto":
                receiver.linked_to = args[0] if args else None
                return UNDEFINED
            if method == "unlink":
                receiver.linked_to = None
                return UNDEFINED
            if method == "moveto":
                pos = args[0] if len(args) > 0 else GscArray([0.0, 0.0, 0.0])
                dur = float(args[1]) if len(args) > 1 else 0.05
                receiver.set_field("origin", GscArray([float(pos[0]), float(pos[1]), float(pos[2])]))
                receiver.move_calls.append(((float(pos[0]), float(pos[1]), float(pos[2])), dur))
                return UNDEFINED
            if method == "rotateyaw":
                deg = float(args[0]) if len(args) > 0 else 0.0
                dur = float(args[1]) if len(args) > 1 else 0.05
                receiver.rotate_yaw_calls.append((deg, dur))
                return UNDEFINED
            if method == "rotateroll":
                deg = float(args[0]) if len(args) > 0 else 0.0
                dur = float(args[1]) if len(args) > 1 else 0.05
                receiver.rotate_roll_calls.append((deg, dur))
                return UNDEFINED
            if method == "notifyoncommand":
                ev = _waw_to_str(args[0]) if len(args) > 0 else ""
                cmd = _waw_to_str(args[1]) if len(args) > 1 else ""
                receiver.notify_commands.append((ev, cmd))
                return UNDEFINED
            if method == "settransported":
                dur = float(args[0]) if len(args) > 0 else 1.5
                receiver.transported_calls.append(dur)
                return UNDEFINED
            if method == "playsound":
                return UNDEFINED
            if method == "delete":
                receiver.deleted = True
                receiver.delete_count += 1
                return UNDEFINED
            if method == "dodamage":
                dmg = int(args[0]) if len(args) > 0 else 0
                pos = args[1] if len(args) > 1 else UNDEFINED
                attacker = args[2] if len(args) > 2 else UNDEFINED
                receiver.damage_events.append({"damage": dmg, "pos": pos, "attacker": attacker})
                cur_hp = int(receiver.get_field("health"))
                receiver.set_field("health", max(0, cur_hp - dmg))
                return UNDEFINED

        return super()._exec_method(receiver, method, args, line)


def _seed_stock_effects(gsc: SpecialWeaponsGscRuntime, map_name: str) -> None:
    fx = GscArray()
    fx.set_item("large_ceiling_dust", "stock_fx:large_ceiling_dust")
    fx.set_item("powerup_on", "stock_fx:powerup_on")
    fx.set_item("powerup_grabbed", "stock_fx:powerup_grabbed")
    fx.set_item("powerup_grabbed_wave", "stock_fx:powerup_grabbed_wave")
    fx.set_item("mini_nuke", "stock_fx:mini_nuke")
    if map_name == "nazi_zombie_factory":
        fx.set_item("rise_burst", "stock_fx:rise_burst")
        fx.set_item("betty_explode", "stock_fx:betty_explode")
        fx.set_item("wire_spark", "stock_fx:wire_spark")
        fx.set_item("wire_sparks_oneshot", "stock_fx:wire_sparks_oneshot")
        fx.set_item("transporter_ambient", "stock_fx:transporter_ambient")
        fx.set_item("transporter_beam", "stock_fx:transporter_beam")
        fx.set_item("transporter_start", "stock_fx:transporter_start")
    gsc.level.set_field("_effect", fx)


def _setup_special_env(
    map_name: str = "nazi_zombie_factory",
    *,
    bz_enabled: bool = True,
    elements_enabled: bool = True,
    pap_enabled: bool = True,
    perks_enabled: bool = True,
) -> tuple[FakeDvarStore, SpecialWeaponsGscRuntime, SpecialFakeEntity]:
    dvars = FakeDvarStore()
    dvars.set("bz_enabled", "1" if bz_enabled else "0")
    dvars.set("bz_elements_enabled", "1" if elements_enabled else "0")
    dvars.set("bz_pap_enabled", "1" if pap_enabled else "0")
    dvars.set("bz_perks_enabled", "1" if perks_enabled else "0")
    dvars.set("bz_classes_enabled", "0")
    dvars.set("bz_companions_enabled", "0")

    gsc = SpecialWeaponsGscRuntime(MOD_ROOT, dvars)
    gsc.level.set_field("script", map_name)
    gsc.level.set_field("round_number", 1)
    _seed_stock_effects(gsc, map_name)

    player = SpecialFakeEntity("PlayerOne", ent_num=0, is_player=True)
    player.set_field("score", 50000)
    player.set_pos(0.0, 0.0, 0.0)
    player.set_angles(0.0, 0.0, 0.0)
    player.give_weapon("thompson", make_current=True)
    gsc.players.append(player)

    gsc.call(BZ_SPECIAL_MOD, "bz_special_weapons_register")
    gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
    gsc.call(BZ_HOOKS_MOD, "bz_init")
    return dvars, gsc, player


class TestSpecialWeaponsRegistrationAndWarClub(unittest.TestCase):
    """Seam 1: Idempotent hook registration, gate isolation, and War Club melee slot + PaP smash."""

    def test_register_is_idempotent_under_elements_gate_and_classic_or_gate_off_is_noop(self) -> None:
        dvars = FakeDvarStore()
        dvars.set("bz_enabled", "0")
        dvars.set("bz_elements_enabled", "1")
        gsc = SpecialWeaponsGscRuntime(MOD_ROOT, dvars)
        player = SpecialFakeEntity("ClassicPlayer", ent_num=0, is_player=True)
        gsc.players.append(player)

        gsc.call(BZ_SPECIAL_MOD, "bz_special_weapons_register")
        gsc.call(BZ_SPECIAL_MOD, "bz_special_weapons_register")

        hooks = gsc.level.get_field("bz_hooks")
        for hook_name in (
            "pre_init",
            "init",
            "player_connect",
            "player_spawned",
            "round_start",
            "item_purchased",
            "weapon_fired",
            "actor_damage",
            "end_game",
        ):
            entries = hooks[hook_name]
            self.assertIsNot(entries, UNDEFINED, f"Missing hook registration for {hook_name}")
            elem_entries = [entries[i] for i in range(entries.size) if entries[i].get_field("gate") == "elements"]
            self.assertEqual(len(elem_entries), 1, f"Hook {hook_name} must register exactly once under 'elements'")

        # Classic Mode: zero HUD, zero telemetry, zero damage changes, zero LoadFX
        gsc.call(BZ_HOOKS_MOD, "bz_init")
        zombie = SpecialFakeEntity("Z1", ent_num=10, is_player=False)
        zombie.set_field("health", 500)
        dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie,
            player,
            player,
            150,
            0,
            "MOD_MELEE",
            "knife",
            GscArray([40.0, 0.0, 0.0]),
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg, 150)
        self.assertEqual(gsc.hud_elems, [])
        self.assertEqual(gsc.emitted_events, [])
        self.assertEqual(gsc.earthquakes, [])
        self.assertEqual(gsc.load_fx_calls, [])

    def test_war_club_swaps_per_player_without_touching_teammate_bowie_and_pap_smash_knocks_back_safely(self) -> None:
        dvars, gsc, p1 = _setup_special_env(map_name="nazi_zombie_factory")
        dvars.set("perk_altMeleeDamage", "1000")

        # Co-op teammate p2 owns Bowie Knife + PaP Bowie
        p2 = SpecialFakeEntity("PlayerTwo", ent_num=1, is_player=True)
        p2.set_field("score", 50000)
        p2.set_pos(0.0, 200.0, 0.0)
        p2.give_perk("specialty_altmelee")
        p2.set_field("has_altmelee", True)
        gsc.players.append(p2)
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", p2)

        # Give p1 Bowie first, then buy War Club -> swaps cleanly to war_club without touching global dvar or p2
        p1.give_perk("specialty_altmelee")
        p1.set_field("has_altmelee", True)
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_gear:war_club")
        )
        self.assertEqual(gsc.call(BZ_STATE_MOD, "bz_state_get_melee_slot", p1), "war_club")
        self.assertFalse(p1.has_perk("specialty_altmelee"))
        self.assertTrue(p2.has_perk("specialty_altmelee"))
        self.assertEqual(dvars.get("perk_altMeleeDamage"), "1000")

        # Set up zombies: z_primary directly in front, z_cone in frontal cone, z_walled near wall, z_behind behind player
        z_primary = SpecialFakeEntity("ZPrimary", ent_num=20, is_player=False)
        z_primary.set_field("health", 2500)
        z_primary.set_pos(48.0, 0.0, 0.0)

        z_cone = SpecialFakeEntity("ZCone", ent_num=21, is_player=False)
        z_cone.set_field("health", 2500)
        z_cone.set_pos(90.0, 30.0, 0.0)

        z_walled = SpecialFakeEntity("ZWalled", ent_num=22, is_player=False)
        z_walled.set_field("health", 2500)
        z_walled.set_pos(110.0, -25.0, 0.0)

        z_behind = SpecialFakeEntity("ZBehind", ent_num=23, is_player=False)
        z_behind.set_field("health", 2500)
        z_behind.set_pos(-120.0, 0.0, 0.0)

        gsc.ai_enemies.extend([z_primary, z_cone, z_walled, z_behind])

        # Simulate a wall blocking z_walled's knockback at fraction=0.35
        def wall_trace(start: GscArray, end: GscArray, _hit_chars: bool, ignore_ent: Any) -> dict[str, Any]:
            if ignore_ent is z_walled:
                return {
                    "fraction": 0.35,
                    "position": GscArray([float(start[0]) + 15.0, float(start[1]), float(start[2])]),
                }
            return {
                "fraction": 1.0,
                "position": GscArray([float(end[0]), float(end[1]), float(end[2])]),
            }

        gsc.trace_handler = wall_trace

        # Base War Club hit: max(150*4=600, 2500*0.5=1250) = 1250
        # Base War Club is heavy frontal cleave damage ONLY: NO knockback, NO stagger, NO shockwave FX, NO Earthquake!
        base_wc_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_primary,
            p1,
            p1,
            150,
            0,
            "MOD_MELEE",
            "knife",
            GscArray([48.0, 0.0, 0.0]),
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(base_wc_dmg, 1250)
        self.assertEqual(gsc.played_sounds_at_pos, [])
        self.assertEqual(len(gsc.earthquakes), 0)
        self.assertEqual(len(gsc.played_fx), 0)
        self.assertEqual(z_cone.get_pos(), (90.0, 30.0, 0.0))  # NOT knocked back by base War Club
        self.assertNotEqual(z_cone.get_field("bz_stunned"), True)
        self.assertGreater(len(z_cone.damage_events), 0)  # DID take frontal cleave damage (dist ~95 <= 96)
        self.assertTrue(
            all(fx in ("misc/fx_zombie_powerup_on", "misc/fx_exp_raygun_impact", "env/electrical/fx_elec_short_oneshot", "bio/player/fx_footstep_water", "misc/fx_zombie_bloodsplat", "misc/fx_trail_raygun_geotrail", "weapon/grenade/fx_trail_rifle_grenade") for fx in gsc.load_fx_calls),
            f"Unexpected LoadFX calls: {gsc.load_fx_calls}",
        )

        # Reset positions & upgrade to PaP War Club -> radius expands to 160, heavy damage = 2500, AOE knockback smash + FX + Earthquake
        z_primary.set_pos(48.0, 0.0, 0.0)
        z_primary.set_field("health", 2500)
        z_cone.set_pos(90.0, 30.0, 0.0)
        z_cone.set_field("health", 2500)
        z_cone.damage_events.clear()
        z_walled.set_pos(110.0, -25.0, 0.0)
        z_walled.set_field("health", 2500)
        z_behind.set_pos(-120.0, 0.0, 0.0)
        z_behind.set_field("health", 2500)
        z_walled.origin_history.clear()
        z_cone.origin_history.clear()
        z_behind.origin_history.clear()

        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_gear:pap_war_club")
        )
        gsc.sim_time_ms = 5000
        pap_wc_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_primary,
            p1,
            p1,
            150,
            0,
            "MOD_MELEE",
            "knife",
            GscArray([48.0, 0.0, 0.0]),
            UNDEFINED,
            "torso_upper",
            0,
        )
        # PaP War Club: max(150*8=1200, 1500, zhp=2500) = 2500
        self.assertEqual(pap_wc_dmg, 2500)
        self.assertEqual(gsc.played_sounds_at_pos, [{"alias": "couch_slam", "pos": (48.0, 0.0, 0.0)}])
        self.assertEqual(len(gsc.earthquakes), 1)
        self.assertAlmostEqual(gsc.earthquakes[0]["scale"], 0.35)
        self.assertAlmostEqual(gsc.earthquakes[0]["duration"], 0.3)
        self.assertAlmostEqual(gsc.earthquakes[0]["radius"], 128.0)
        self.assertGreater(len(gsc.played_fx), 0)

        # z_cone pushed far back cleanly (~112 units away from player) and staggered
        self.assertGreater(z_cone.get_pos()[0], 180.0)
        self.assertTrue(z_cone.get_field("bz_stunned"))
        self.assertGreater(len(z_cone.damage_events), 0)

        # z_walled stopped safely before wall (safe_frac = 0.35 - 0.15 = 0.20 -> ~22 units, NOT 112!)
        self.assertGreater(z_walled.get_pos()[0], 110.0)
        self.assertLess(z_walled.get_pos()[0], 140.0)

        # z_behind was behind player -> NOT hit or pushed
        self.assertEqual(z_behind.get_pos(), (-120.0, 0.0, 0.0))
        self.assertEqual(z_behind.damage_events, [])

        # Emits SPECIAL_WAR_CLUB_SMASH telemetry
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|SPECIAL_WAR_CLUB_SMASH|") and "pap=1" in e and "radius=160" in e
                for e in gsc.emitted_events
            ),
            f"Missing SPECIAL_WAR_CLUB_SMASH telemetry: {gsc.emitted_events}",
        )

        # Free swap back to Bowie restores specialty_altmelee for p1; War Club hook stops firing for p1
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_gear:equip_bowie")
        )
        self.assertEqual(gsc.call(BZ_STATE_MOD, "bz_state_get_melee_slot", p1), "bowie")
        self.assertTrue(p1.has_perk("specialty_altmelee"))
        self.assertEqual(gsc.played_local_sounds, [(p1, "cha_ching")] * 3)
        bowie_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_primary,
            p1,
            p1,
            1000,
            0,
            "MOD_MELEE",
            "bowie_knife",
            GscArray([48.0, 0.0, 0.0]),
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(bowie_dmg, 1000)

    def test_war_club_lethal_primary_hit_still_cleaves_and_wall_buy_bowie_prevents_stacking(self) -> None:
        _dvars, gsc, p1 = _setup_special_env(map_name="nazi_zombie_factory")
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_gear:war_club")
        )
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_gear:pap_war_club")
        )

        # Primary zombie is ALREADY dead (health == 0) from initial lethal melee hit,
        # while adjacent zombie in frontal cone is alive!
        z_dead_primary = SpecialFakeEntity("ZDeadPrimary", ent_num=70, is_player=False)
        z_dead_primary.set_field("health", 0)
        z_dead_primary.set_field("maxhealth", 1000)
        z_dead_primary.set_field("damagetaken", 150)
        z_dead_primary.set_pos(48.0, 0.0, 0.0)

        z_neighbor = SpecialFakeEntity("ZNeighbor", ent_num=71, is_player=False)
        z_neighbor.set_field("health", 2500)
        z_neighbor.set_pos(90.0, 20.0, 0.0)
        gsc.ai_enemies.extend([z_dead_primary, z_neighbor])

        gsc.sim_time_ms = 5000
        gsc.call_on(
            z_dead_primary,
            BZ_HOOKS_MOD,
            "bz_global_damage_wrapper",
            "MOD_MELEE",
            "torso_upper",
            GscArray([48.0, 0.0, 0.0]),
            p1,
        )
        # Dead primary took zero extra DoDamage, while alive neighbor was cleaved & knocked back!
        self.assertEqual(z_dead_primary.damage_events, [])
        self.assertEqual(len(z_neighbor.damage_events), 1)
        self.assertGreater(z_neighbor.get_pos()[0], 150.0)
        self.assertEqual(len(gsc.earthquakes), 1)

        # Now simulate buying stock Bowie Knife off the wall AFTER equipping War Club
        p1.give_perk("specialty_altmelee")
        p1.set_field("has_altmelee", True)
        z_check = SpecialFakeEntity("ZCheck", ent_num=72, is_player=False)
        z_check.set_field("health", 3000)
        z_check.set_pos(48.0, 0.0, 0.0)
        gsc.earthquakes.clear()
        dmg_after_bowie_wallbuy = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_check,
            p1,
            p1,
            1000,
            0,
            "MOD_MELEE",
            "bowie_knife",
            GscArray([48.0, 0.0, 0.0]),
            UNDEFINED,
            "torso_upper",
            0,
        )
        # Switched cleanly to "bowie": NO War Club damage stacking and NO smash!
        self.assertEqual(gsc.call(BZ_STATE_MOD, "bz_state_get_melee_slot", p1), "bowie")
        self.assertEqual(dmg_after_bowie_wallbuy, 1000)
        self.assertEqual(gsc.earthquakes, [])


class TestMultiCrossbowSpecialWeapon(unittest.TestCase):
    """Seam 2: Multi-Crossbow 3-bolt sticky explosive spread, Double PaP, Blast Shield & cleanup."""

    def test_multi_crossbow_fires_three_spread_bolts_sticks_and_detonates_with_blast_shield_and_double_pap(self) -> None:
        _dvars, gsc, player = _setup_special_env(map_name="nazi_zombie_factory")
        gsc.level.set_field("round_number", 16)
        gsc.level.set_field("zombie_health", 2000)
        gsc.call(BZ_HOOKS_MOD, "bz_on_round_start", 16)

        player.set_pos(0.0, 0.0, 0.0)
        player.set_angles(0.0, 0.0, 0.0)  # aiming +X
        player.give_weapon("bz_multi_crossbow", make_current=True)

        z_stuck = SpecialFakeEntity("ZStuck", ent_num=30, is_player=False)
        z_stuck.set_field("health", 2000)
        z_stuck.set_pos(300.0, 0.0, 0.0)

        z_near_left = SpecialFakeEntity("ZNearLeft", ent_num=31, is_player=False)
        z_near_left.set_field("health", 2000)
        z_near_left.set_pos(290.0, -45.0, 0.0)

        z_far = SpecialFakeEntity("ZFar", ent_num=32, is_player=False)
        z_far.set_field("health", 2000)
        z_far.set_pos(1200.0, 1200.0, 0.0)

        gsc.ai_enemies.extend([z_stuck, z_near_left, z_far])

        trace_dirs: list[tuple[float, float]] = []

        def xbow_trace(start: GscArray, end: GscArray, hit_chars: bool, _ignore: Any) -> dict[str, Any]:
            self.assertTrue(hit_chars, "Multi-Crossbow BulletTrace must set hitCharacters=true")
            dx = float(end[0]) - float(start[0])
            dy = float(end[1]) - float(start[1])
            yaw_deg = math.degrees(math.atan2(dy, dx))
            trace_dirs.append((round(yaw_deg, 1), dx))
            if abs(yaw_deg) < 1.0:
                return {
                    "fraction": 0.20,
                    "position": GscArray([300.0, 0.0, 48.0]),
                    "entity": z_stuck,
                }
            # Left (-6 deg) and right (+6 deg) bolts hit world surfaces
            hit_y = 300.0 * math.tan(math.radians(yaw_deg))
            return {
                "fraction": 0.25,
                "position": GscArray([300.0, hit_y, 40.0]),
                "entity": UNDEFINED,
            }

        gsc.trace_handler = xbow_trace

        # Fire Multi-Crossbow via weapon_fired hook
        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_multi_crossbow")

        # Exactly 3 spread bolts (-6, 0, +6 deg)
        self.assertEqual([d[0] for d in trace_dirs], [-6.0, 0.0, 6.0])
        tracked = gsc.level.get_field("bz_special_entities")
        bolts = [tracked[i] for i in range(tracked.size) if tracked[i] is not UNDEFINED]
        self.assertEqual(len(bolts), 3)

        stuck_to_zombie = [b for b in bolts if b.get_field("bz_stuck_type") == "zombie"]
        stuck_to_world = [b for b in bolts if b.get_field("bz_stuck_type") == "world"]
        self.assertEqual(len(stuck_to_zombie), 1)
        self.assertEqual(len(stuck_to_world), 2)
        # Bolts spawn near muzzle (not teleported to 300u), stagger fuses (0.65 / 0.77 / 0.89),
        # and fly via MoveTo before sticking with instant piercing impact + pin stagger at hit height 48.0
        self.assertEqual(
            [round(float(b.get_field("bz_fuse_time")), 2) for b in bolts],
            [0.65, 0.77, 0.89],
        )
        for b in bolts:
            self.assertLess(b.get_pos()[0], 40.0)
            self.assertGreaterEqual(float(b.get_field("bz_travel_time")), 0.05)
            self.assertLessEqual(float(b.get_field("bz_travel_time")), 0.20)
            self.assertTrue(b.not_solid)
            self.assertEqual(b.contents, 0)

        # Simulate bolt flight & stick helper for zombie bolt -> MoveTo + LinkTo + instant piercing impact + 0.30x pin stagger
        self.assertAlmostEqual(float(stuck_to_zombie[0].get_field("bz_stuck_z_offset")), 48.0)
        gsc.sim_time_ms = 5000
        gsc.call(BZ_SPECIAL_MOD, "bz_special_crossbow_bolt_fly_and_stick", stuck_to_zombie[0])
        self.assertEqual(len(stuck_to_zombie[0].move_calls), 1)
        self.assertIs(stuck_to_zombie[0].linked_to, z_stuck)
        self.assertAlmostEqual(stuck_to_zombie[0].get_pos()[2], 48.0)
        # Instant piercing impact damage: 55% of 2000 = 1100, leaving 900 HP + brief 0.30x pin stagger
        self.assertEqual(len(z_stuck.damage_events), 1)
        self.assertEqual(z_stuck.damage_events[0]["damage"], 1100)
        self.assertEqual(z_stuck.get_field("health"), 900)
        self.assertAlmostEqual(float(z_stuck.get_field("moveplaybackrate")), 0.30)
        self.assertTrue(any(s["alias"] == "impact_wood_flesh" for s in gsc.played_sounds_at_pos))

        # Child fuse threads scheduled (zero inline wait/endon in weapon_fired)
        fuse_threads = [t for t in gsc._threads if t[1] == "bz_special_crossbow_bolt_fuse"]
        self.assertEqual(len(fuse_threads), 3)

        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|SPECIAL_CROSSBOW_FIRE|")
                and "bolts=3" in e
                and "stuck_zombies=1" in e
                and "stuck_world=2" in e
                for e in gsc.emitted_events
            ),
            f"Missing SPECIAL_CROSSBOW_FIRE event: {gsc.emitted_events}",
        )

        # Move player near left bolt without Blast Shield -> takes capped non-lethal self-damage
        left_bolt = stuck_to_world[0]
        player.set_pos(290.0, -30.0, 0.0)
        player.set_field("health", 100)
        res1 = gsc.call(BZ_SPECIAL_MOD, "bz_special_detonate_crossbow_bolt", player, left_bolt, False, 16)
        self.assertEqual(res1.get_field("damage"), 1600)  # 2000 * 0.80 = 1600
        self.assertFalse(res1.get_field("self_immune"))
        self.assertGreater(len(player.damage_events), 0)
        self.assertGreater(player.get_field("health"), 0)
        self.assertEqual(z_near_left.get_field("health"), 400)  # 2000 - 1600
        self.assertEqual(z_far.get_field("health"), 2000)
        self.assertTrue(left_bolt.deleted)
        self.assertEqual(left_bolt.delete_count, 1)

        # Equip Blast Shield + Double PaP -> 2800 damage (1600 * 1.75) and 0 self-damage
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_perks", "buy_apex:blast_shield")
        )
        gsc.call(BZ_STATE_MOD, "bz_state_mark_weapon_double_pap", player, "bz_multi_crossbow")
        player.damage_events.clear()
        player.set_pos(300.0, 0.0, 0.0)
        player.set_field("health", 100)

        center_bolt = stuck_to_zombie[0]
        res2 = gsc.call(BZ_SPECIAL_MOD, "bz_special_detonate_crossbow_bolt", player, center_bolt, True, 16)
        self.assertEqual(res2.get_field("damage"), 2800)  # 1600 * 1.75 = 2800
        self.assertTrue(res2.get_field("self_immune"))
        self.assertEqual(player.damage_events, [])
        self.assertEqual(player.get_field("health"), 100)
        self.assertEqual(z_stuck.get_field("health"), 0)  # killed lethally
        self.assertAlmostEqual(float(res2.get_field("center")[2]), 48.0)  # hit height, NOT feet z=0
        self.assertTrue(
            any(s["alias"] == "grenade_explode_default" and abs(s["pos"][2] - 48.0) < 0.1 for s in gsc.played_sounds_at_pos),
            f"Missing explosion sound at hit height: {gsc.played_sounds_at_pos}",
        )
        self.assertTrue(center_bolt.deleted)
        self.assertEqual(center_bolt.delete_count, 1)
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|SPECIAL_CROSSBOW_DETONATE|")
                and "damage=2800" in e
                and "double_pap=1" in e
                and "self_immune=1" in e
                for e in gsc.emitted_events
            ),
            f"Missing SPECIAL_CROSSBOW_DETONATE event: {gsc.emitted_events}",
        )

        # Remaining 3rd bolt cleaned up cleanly on end_game with zero double-deletes
        third_bolt = stuck_to_world[1]
        self.assertFalse(third_bolt.deleted)
        gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.assertTrue(third_bolt.deleted)
        self.assertTrue(all(b.delete_count == 1 for b in bolts))

    def test_crossbow_and_boomerang_trigger_cryo_shatter_acid_brittle_without_double_pap_double_mult(self) -> None:
        _dvars, gsc, player = _setup_special_env(map_name="nazi_zombie_factory")
        gsc.level.set_field("round_number", 16)
        gsc.level.set_field("zombie_health", 2000)
        gsc.sim_time_ms = 5000

        # Double-PaP both Multi-Crossbow and Blade Boomerang
        gsc.call(BZ_STATE_MOD, "bz_state_mark_weapon_double_pap", player, "bz_multi_crossbow")
        gsc.call(BZ_STATE_MOD, "bz_state_mark_weapon_double_pap", player, "bz_blade_boomerang")

        # Frozen + Acid-brittle zombie hit by Double-PaP Multi-Crossbow bolt:
        # bolt_dmg = 1600 * 1.75 = 2800; status mult = 1.50 (Brittle) * 2.50 (Shatter) -> 10500 (NOT double-PaP'd twice!)
        z_xbow = SpecialFakeEntity("ZXbowShatter", ent_num=80, is_player=False)
        z_xbow.set_field("health", 20000)
        z_xbow.set_pos(200.0, 0.0, 0.0)
        z_xbow.set_field("bz_acid_brittle_until", 9000)
        z_xbow.set_field("bz_is_frozen", True)
        z_xbow.set_field("bz_cryo_frozen_until", 9000)
        gsc.ai_enemies.append(z_xbow)

        bolt = SpecialFakeEntity("TestBolt", ent_num=81, is_player=False)
        bolt.set_pos(200.0, 0.0, 0.0)
        bolt.set_field("bz_detonated", False)
        gsc.call(BZ_SPECIAL_MOD, "bz_special_detonate_crossbow_bolt", player, bolt, True, 16)
        self.assertEqual(z_xbow.damage_events[0]["damage"], 10500)  # 2800 * 1.5 * 2.5
        self.assertFalse(bool(z_xbow.get_field("bz_is_frozen")))
        self.assertTrue(z_xbow.get_field("bz_in_damage_dispatch"))
        self.assertTrue(
            any(e.startswith("BZ_EVENT|ELEM_CRYO_SHATTER|") and "weapon=bz_multi_crossbow" in e for e in gsc.emitted_events)
        )

        # Frozen + Acid-brittle zombie hit by Double-PaP Blade Boomerang:
        # dmg = 1500 * 1.75 = 2625; status mult = 1.50 * 2.50 -> 9843
        z_blade = SpecialFakeEntity("ZBladeShatter", ent_num=82, is_player=False)
        z_blade.set_field("health", 20000)
        z_blade.set_pos(400.0, 0.0, 0.0)
        z_blade.set_field("bz_acid_brittle_until", 9000)
        z_blade.set_field("bz_is_frozen", True)
        z_blade.set_field("bz_cryo_frozen_until", 9000)
        gsc.ai_enemies.append(z_blade)

        pierced = GscArray()
        gsc.call(
            BZ_SPECIAL_MOD,
            "bz_special_boomerang_pierce_at",
            player,
            GscArray([400.0, 0.0, 0.0]),
            2625,
            6,
            pierced,
        )
        self.assertEqual(z_blade.damage_events[0]["damage"], 9843)  # int(2625 * 1.5 * 2.5)
        self.assertFalse(bool(z_blade.get_field("bz_is_frozen")))
        self.assertTrue(z_blade.get_field("bz_in_damage_dispatch"))


class TestBladeBoomerangSpecialWeapon(unittest.TestCase):
    """Seam 3: Blade Boomerang stock blade model, wall stop, 6-unique-zombie pierce, return & cleanup."""

    def test_boomerang_resolves_map_models_respects_wall_stop_pierces_six_unique_zombies_and_returns(self) -> None:
        # Cross-map custom boomerang model verification (map-independent bz_boomerang_blade_air, F14/S10)
        _dvars_n, gsc_n, _p_n = _setup_special_env(map_name="nazi_zombie_prototype")
        self.assertEqual(
            gsc_n.call(BZ_SPECIAL_MOD, "bz_special_get_boomerang_model"),
            "bz_boomerang_blade_air",
        )

        _dvars, gsc, player = _setup_special_env(map_name="nazi_zombie_factory")
        gsc.level.set_field("round_number", 16)
        gsc.level.set_field("zombie_health", 2000)
        gsc.call(BZ_HOOKS_MOD, "bz_on_round_start", 16)

        player.set_pos(0.0, 0.0, 0.0)
        player.set_angles(0.0, 0.0, 0.0)
        player.give_weapon("bz_blade_boomerang", make_current=True)

        # Place 8 zombies: 4 along outbound line (+X), 4 along curved return arc (y ~ -60..-40)
        outbound_positions = [
            (100.0, 0.0, 40.0),
            (180.0, 0.0, 40.0),
            (260.0, 0.0, 40.0),
            (340.0, 0.0, 40.0),
        ]
        return_positions = [
            (310.0, -68.0, 40.0),
            (230.0, -82.0, 40.0),
            (160.0, -80.0, 40.0),
            (100.0, -64.0, 40.0),
        ]
        all_zombies: list[SpecialFakeEntity] = []
        for idx, (zx, zy, zz) in enumerate(outbound_positions + return_positions):
            z = SpecialFakeEntity(f"ZB_{idx}", ent_num=40 + idx, is_player=False)
            z.set_field("health", 2000)
            z.set_pos(zx, zy, zz)
            all_zombies.append(z)
        gsc.ai_enemies.extend(all_zombies)

        # Wall at x = 420 -> fraction = 400 / 520 (~0.77) stops outbound before 520,
        # while unobstructed traces in front of the wall (x < 420) pass with fraction 1.0.
        def wall_stop_trace(start: GscArray, end: GscArray, _hit_chars: bool, _ignore: Any) -> dict[str, Any]:
            if max(float(start[0]), float(end[0])) < 420.0:
                return {"fraction": 1.0, "position": end}
            return {
                "fraction": 0.77,
                "position": GscArray([420.0, float(start[1]), float(start[2])]),
            }

        gsc.trace_handler = wall_stop_trace

        # Fire Blade Boomerang via weapon_fired
        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_blade_boomerang")

        tracked = gsc.level.get_field("bz_special_entities")
        blades = [tracked[i] for i in range(tracked.size) if tracked[i] is not UNDEFINED]
        self.assertEqual(len(blades), 1)
        blade = blades[0]
        self.assertEqual(blade.get_field("model"), "bz_boomerang_blade_air")
        self.assertEqual(blade.contents, 0)
        self.assertTrue(blade.not_solid)

        # Child flight thread scheduled with wall-clamped apex (< 420)
        flight_threads = [t for t in gsc._threads if t[1] == "bz_special_boomerang_flight_thread"]
        self.assertEqual(len(flight_threads), 1)
        _recv, _fname, fargs = flight_threads[0]
        f_blade, start_pos, apex, dmg, max_pierce = fargs
        self.assertIs(f_blade, blade)
        self.assertLess(float(apex[0]), 420.0)
        self.assertEqual(dmg, 1500)  # Round 16: 2000 * 0.75 = 1500
        self.assertEqual(max_pierce, 6)

        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|SPECIAL_BOOMERANG_THROW|")
                and "model=bz_boomerang_blade_air" in e
                and "max_pierce=6" in e
                and "damage=1500" in e
                for e in gsc.emitted_events
            ),
            f"Missing SPECIAL_BOOMERANG_THROW event: {gsc.emitted_events}",
        )

        # Execute flight synchronously: pierces exactly 6 unique zombies (4 outbound + 2 return),
        # never double-hits any zombie, spins, returns to player, and deletes cleanly on catch
        res = gsc.call(
            BZ_SPECIAL_MOD,
            "bz_special_run_boomerang_flight",
            player,
            blade,
            start_pos,
            apex,
            dmg,
            max_pierce,
        )
        self.assertEqual(res.get_field("pierce_count"), 6)
        self.assertGreaterEqual(res.get_field("outbound_hits"), 4)
        self.assertGreaterEqual(res.get_field("return_hits"), 2)
        self.assertTrue(res.get_field("caught"))
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|SPECIAL_BOOMERANG_RETURN|")
                and "model=bz_boomerang_blade_air" in e
                and "pierce=6" in e
                and "caught=1" in e
                for e in gsc.emitted_events
            ),
            f"Missing SPECIAL_BOOMERANG_RETURN event: {gsc.emitted_events}",
        )
        self.assertTrue(blade.deleted)
        self.assertEqual(blade.delete_count, 1)
        self.assertGreater(len(blade.rotate_roll_calls), 0)
        self.assertGreater(len(blade.move_calls), 0)

        # Every hit zombie took exactly 1 hit of 1500 attributed to player; 2 zombies untouched
        hit_counts = [len(z.damage_events) for z in all_zombies]
        self.assertEqual(hit_counts.count(1), 6)
        self.assertEqual(hit_counts.count(0), 2)
        for z in all_zombies:
            for ev in z.damage_events:
                self.assertEqual(ev["damage"], 1500)
                self.assertIs(ev["attacker"], player)

        # Double PaP boomerang damage = 1500 * 1.75 = 2625, and disconnect/end_game clean up mid-flight blades
        gsc.call(BZ_STATE_MOD, "bz_state_mark_weapon_double_pap", player, "bz_blade_boomerang")
        p2 = SpecialFakeEntity("PlayerTwo", ent_num=1, is_player=True)
        p2.set_pos(0.0, 200.0, 0.0)
        p2.give_weapon("bz_blade_boomerang", make_current=True)
        gsc.players.append(p2)
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", p2)

        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_blade_boomerang")
        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", p2, "bz_blade_boomerang")
        dpap_threads = [t for t in gsc._threads if t[1] == "bz_special_boomerang_flight_thread"]
        self.assertEqual(dpap_threads[-2][2][3], 2625)  # player Double PaP
        self.assertEqual(dpap_threads[-1][2][3], 1500)  # p2 non-Double-PaP

        p1_blade = dpap_threads[-2][2][0]
        p2_blade = dpap_threads[-1][2][0]

        # Player 1 disconnects mid-flight -> p1_blade deleted, p2_blade still active
        gsc.call(BZ_SPECIAL_MOD, "bz_special_destroy_player_entities", player)
        self.assertTrue(p1_blade.deleted)
        self.assertFalse(p2_blade.deleted)

        # end_game cleans up p2_blade with zero double-deletes
        gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.assertTrue(p2_blade.deleted)
        self.assertEqual(p1_blade.delete_count, 1)
        self.assertEqual(p2_blade.delete_count, 1)


class TestPortalGrenadeSpecialWeapon(unittest.TestCase):
    """Seam 4: Portal Grenade +actionslot 2 binding, cooldown/charges, squad warp & zombie exclusion."""

    def test_max_ammo_notification_refills_portal_charges_and_refreshes_owner_hud(self) -> None:
        _dvars, gsc, player = _setup_special_env()
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", player)
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_spawned", player)
        watcher = "bz_special_watch_max_ammo"
        self.assertEqual(gsc._threads.count((player, watcher, [])), 1)
        self.assertTrue(player.bz_special_max_ammo_watch_started)

        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_arsenal", "buy_gear:portal_grenade")
        gsc.sim_time_ms = 5000
        self.assertIsNot(gsc.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", player), UNDEFINED)
        self.assertEqual(player.bz_portal_charges, 1)
        self.assertEqual(player.bz_special_hud.current_text, "PORTAL: 1")

        gsc.call(BZ_HOOKS_MOD, "bz_notify_all_players_max_ammo")
        self.assertIn((player, "zmb_max_ammo"), gsc.notifies)
        pending = list(gsc.notifies)
        endon_guards = []

        class WatcherWaiting(Exception):
            pass

        original_method = gsc._exec_method

        def deliver_notification(receiver, method, args, line):
            if method == "endon":
                endon_guards.append((receiver, args[0]))
            if method == "waittill":
                self.assertEqual((receiver, args[0]), (player, "zmb_max_ammo"))
                if (receiver, args[0]) not in pending:
                    raise WatcherWaiting
                pending.remove((receiver, args[0]))
                return UNDEFINED
            return original_method(receiver, method, args, line)

        with patch.object(gsc, "_exec_method", side_effect=deliver_notification):
            with self.assertRaises(WatcherWaiting):
                gsc.call_on(player, BZ_SPECIAL_MOD, watcher)

        self.assertEqual(endon_guards, [(player, "disconnect"), (gsc.level, "end_game")])
        self.assertEqual(player.bz_portal_charges, 2)
        self.assertEqual(player.bz_special_hud.current_text, "PORTAL: 2")
        self.assertEqual(
            gsc.emitted_events.count("BZ_EVENT|SPECIAL_PORTAL_REFILL|player=PlayerOne;reason=max_ammo;charges=2"),
            1,
        )
        gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.assertIs(player.bz_special_watchers_started, UNDEFINED)
        self.assertIs(player.bz_special_max_ammo_watch_started, UNDEFINED)

    def test_max_ammo_is_a_strict_noop_for_undefined_unowned_and_disabled_players(self) -> None:
        dvars, gsc, player = _setup_special_env()
        refill = "bz_special_on_max_ammo"
        events = list(gsc.emitted_events)
        uninitialized = SpecialFakeEntity("LateJoiner", ent_num=1)
        uninitialized_fields = uninitialized.to_dict()
        self.assertFalse(gsc.call(BZ_SPECIAL_MOD, refill, UNDEFINED))
        self.assertFalse(gsc.call(BZ_SPECIAL_MOD, refill, uninitialized))
        self.assertEqual(uninitialized.to_dict(), uninitialized_fields)

        gsc.call(BZ_STATE_MOD, "bz_state_ensure_init", player)
        unowned_fields = player.to_dict()
        self.assertFalse(gsc.call(BZ_SPECIAL_MOD, refill, player))
        self.assertEqual(player.to_dict(), unowned_fields)
        self.assertEqual(gsc.hud_elems, [])
        self.assertEqual(gsc.emitted_events, events)

        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_arsenal", "buy_gear:portal_grenade")
        player.set_field("bz_portal_charges", 0)
        gsc.call(BZ_SPECIAL_MOD, "bz_special_update_hud", player)
        hud = player.bz_special_hud
        self.assertEqual(hud.current_text, "PORTAL: 0")
        events = list(gsc.emitted_events)
        hud_writes = list(hud.text_history)
        owned_fields = player.to_dict()
        for disabled_gate in ("bz_enabled", "bz_elements_enabled"):
            with self.subTest(disabled_gate=disabled_gate):
                dvars.set(disabled_gate, "0")
                self.assertFalse(gsc.call(BZ_SPECIAL_MOD, refill, player))
                self.assertEqual(player.to_dict(), owned_fields)
                self.assertEqual(hud.text_history, hud_writes)
                self.assertEqual(gsc.emitted_events, events)
                dvars.set(disabled_gate, "1")

    def test_special_weapon_audio_is_silent_in_classic_mode(self) -> None:
        dvars, gsc, player = _setup_special_env()
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_arsenal", "buy_gear:portal_grenade")
        portal = gsc.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", player)
        self.assertIsNot(portal, UNDEFINED)
        player.set_pos(*portal.get_pos())
        gsc.sim_time_ms += 30000  # Past cooldown with one charge available.
        gsc.played_sounds_at_pos.clear()
        gsc.played_local_sounds.clear()
        dvars.set("bz_enabled", "0")

        self.assertIs(
            gsc.call(BZ_SPECIAL_MOD, "bz_special_war_club_smash", player, UNDEFINED, UNDEFINED, True, 1200),
            UNDEFINED,
        )
        self.assertIs(gsc.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", player), UNDEFINED)
        self.assertEqual(gsc.call(BZ_SPECIAL_MOD, "bz_special_portal_tick", portal, player), 0)
        self.assertEqual(gsc.played_sounds_at_pos, [])
        self.assertEqual(gsc.played_local_sounds, [])

    def test_portal_binds_actionslot2_enforces_cooldown_teleports_squad_excludes_zombies_and_cleans_up(self) -> None:
        _dvars, gsc, p1 = _setup_special_env(map_name="nazi_zombie_factory")
        p1.set_pos(500.0, 500.0, 0.0)
        p1.set_angles(0.0, 0.0, 0.0)

        # Register a verified map spawn point in world_entities ("targetname", "initial_spawn_points")
        sp0 = SpecialFakeEntity("spawn_0", ent_num=90, is_player=False)
        sp0.set_pos(-100.0, -200.0, 64.0)
        sp0.set_angles(0.0, 90.0, 0.0)
        gsc.world_entities[("targetname", "initial_spawn_points")] = [sp0]

        # Co-op teammate standing near where portal will land
        p2 = SpecialFakeEntity("PlayerTwo", ent_num=1, is_player=True)
        p2.set_pos(710.0, 500.0, 0.0)
        p2.set_field("score", 50000)
        gsc.players.append(p2)
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", p2)

        # Dedicated Coop-safe child watcher threads were spawned on connect (zero NotifyOnCommand in Coop)
        p1_threads = {t[1] for t in gsc._threads if t[0] is p1}
        p2_threads = {t[1] for t in gsc._threads if t[0] is p2}
        self.assertIn("bz_special_watch_portal_command", p1_threads)
        self.assertIn("bz_special_watch_portal_notify", p1_threads)
        self.assertIn("bz_special_watch_portal_command", p2_threads)
        self.assertIn("bz_special_watch_portal_notify", p2_threads)
        self.assertEqual(p1.notify_commands, [])
        self.assertEqual(p2.notify_commands, [])

        # Cannot activate before purchasing Portal Grenade
        self.assertIs(gsc.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", p1), UNDEFINED)
        self.assertEqual(gsc.played_sounds_at_pos, [])

        # Buy Portal Grenade (6000 pts) -> does NOT consume primary weapon slot or change offhand
        primaries_before = set(p1.weapons)
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_gear:portal_grenade")
        )
        self.assertEqual(p1.weapons, primaries_before)
        self.assertTrue(gsc.call(BZ_STATE_MOD, "bz_state_owns_portal_grenade", p1))
        self.assertEqual(gsc.call(BZ_STATE_MOD, "bz_state_get_portal_charges", p1), 2)

        # Activate Portal Grenade at t=5000ms -> consumes 1 charge (1 left), spawns 8s portal at ~(720, 500, 0)
        gsc.sim_time_ms = 5000
        portal = gsc.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", p1)
        self.assertIsNot(portal, UNDEFINED)
        self.assertEqual(gsc.call(BZ_STATE_MOD, "bz_state_get_portal_charges", p1), 1)
        self.assertAlmostEqual(float(portal.get_field("bz_duration")), 8.0)
        self.assertEqual(portal.get_field("bz_fx_name"), "transporter_ambient")
        # Portal looping FX MUST use tracked SpawnFx + TriggerFx (never unmanaged PlayFX!)
        portal_fx_ent = portal.get_field("bz_fx_ent")
        self.assertIsNot(portal_fx_ent, UNDEFINED)
        self.assertEqual(portal_fx_ent.get_field("fx_handle"), "stock_fx:transporter_ambient")
        self.assertTrue(portal_fx_ent.get_field("triggered"))
        self.assertEqual(gsc.played_fx, [])
        self.assertTrue(
            all(fx in ("misc/fx_zombie_powerup_on", "misc/fx_exp_raygun_impact", "env/electrical/fx_elec_short_oneshot", "bio/player/fx_footstep_water", "misc/fx_zombie_bloodsplat", "misc/fx_trail_raygun_geotrail", "weapon/grenade/fx_trail_rifle_grenade") for fx in gsc.load_fx_calls),
            f"Unexpected LoadFX calls: {gsc.load_fx_calls}",
        )
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|SPECIAL_PORTAL_OPEN|")
                and "duration=8" in e
                and "charges_left=1" in e
                for e in gsc.emitted_events
            ),
            f"Missing SPECIAL_PORTAL_OPEN event: {gsc.emitted_events}",
        )

        # Cooldown enforced (25s): trying again at t=15000ms (10s later) fails without spending 2nd charge
        gsc.sim_time_ms = 15000
        self.assertIs(gsc.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", p1), UNDEFINED)
        self.assertEqual(gsc.call(BZ_STATE_MOD, "bz_state_get_portal_charges", p1), 1)

        # Place thrower p1, teammate p2, AND two zombies directly inside the portal radius (<= 96 units)
        portal_pos = portal.get_pos()
        self.assertEqual(gsc.played_sounds_at_pos, [{"alias": "spawn_powerup", "pos": portal_pos}])
        p1.set_pos(portal_pos[0] + 10.0, portal_pos[1], portal_pos[2])
        p2.set_pos(portal_pos[0] - 20.0, portal_pos[1], portal_pos[2])

        z_on_portal = SpecialFakeEntity("ZOnPortal", ent_num=60, is_player=False)
        z_on_portal.set_field("health", 500)
        z_on_portal.set_pos(portal_pos[0], portal_pos[1], portal_pos[2])

        z_near_portal = SpecialFakeEntity("ZNearPortal", ent_num=61, is_player=False)
        z_near_portal.set_field("health", 500)
        z_near_portal.set_pos(portal_pos[0] + 15.0, portal_pos[1] - 10.0, portal_pos[2])
        gsc.ai_enemies.extend([z_on_portal, z_near_portal])

        # Tick portal -> BOTH p1 and p2 warp to spawn area with anti-stack separation + SetTransported(1.5)
        warped = gsc.call(BZ_SPECIAL_MOD, "bz_special_portal_tick", portal, p1)
        self.assertEqual(warped, 2)

        # Both players are now near spawn (-100, -200) and NOT stacked on identical coordinates
        self.assertLess(math.hypot(p1.get_pos()[0] - (-100.0), p1.get_pos()[1] - (-200.0)), 64.0)
        self.assertLess(math.hypot(p2.get_pos()[0] - (-100.0), p2.get_pos()[1] - (-200.0)), 64.0)
        self.assertGreater(
            math.hypot(p1.get_pos()[0] - p2.get_pos()[0], p1.get_pos()[1] - p2.get_pos()[1]),
            10.0,
            "Co-op teammates must receive anti-stack offset at spawn destination",
        )
        self.assertEqual(p1.transported_calls, [1.5])
        self.assertEqual(p2.transported_calls, [1.5])
        self.assertEqual(
            gsc.played_local_sounds,
            [(p1, "cha_ching"), (p1, "powerup_grabbed"), (p2, "powerup_grabbed")],
        )

        # STRICT ZOMBIE EXCLUSION: neither zombie moved at all!
        self.assertEqual(z_on_portal.get_pos(), portal_pos)
        self.assertEqual(z_on_portal.origin_history, [])
        self.assertEqual(z_near_portal.get_pos(), (portal_pos[0] + 15.0, portal_pos[1] - 10.0, portal_pos[2]))
        self.assertEqual(z_near_portal.origin_history, [])

        teleport_events = [e for e in gsc.emitted_events if e.startswith("BZ_EVENT|SPECIAL_PORTAL_TELEPORT|")]
        self.assertEqual(len(teleport_events), 2)

        # Cross-map fallback FX (Nacht der Untoten without transporter_ambient -> uses deletable powerup_on SpawnFx)
        _dvars_n, gsc_n, pn = _setup_special_env(map_name="nazi_zombie_prototype")
        gsc_n.call(BZ_HOOKS_MOD, "bz_on_menu_response", pn, "bz_station_arsenal", "buy_gear:portal_grenade")
        gsc_n.sim_time_ms = 5000
        portal_n = gsc_n.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", pn)
        self.assertEqual(portal_n.get_field("bz_fx_name"), "misc/fx_zombie_powerup_wave")
        portal_n_fx = portal_n.get_field("bz_fx_ent")
        self.assertIsNot(portal_n_fx, UNDEFINED)
        self.assertEqual(portal_n_fx.get_field("fx_handle"), "stock_fx:powerup_on")
        self.assertTrue(portal_n_fx.get_field("triggered"))
        self.assertEqual(gsc_n.played_fx, [])
        self.assertTrue(
            all(
                fx in (
                    "misc/fx_zombie_powerup_on",
                    "misc/fx_exp_raygun_impact",
                    "env/electrical/fx_elec_short_oneshot",
                    "bio/player/fx_footstep_water",
                    "misc/fx_zombie_bloodsplat",
                    "misc/fx_trail_raygun_geotrail",
                    "weapon/grenade/fx_trail_rifle_grenade",
                )
                for fx in gsc_n.load_fx_calls
            ),
            f"Unexpected LoadFX calls: {gsc_n.load_fx_calls}",
        )

        # Round start recharges portal back to 2 charges, and cooldown expiry allows 2nd throw
        gsc.call(BZ_HOOKS_MOD, "bz_on_round_start", 2)
        self.assertEqual(gsc.call(BZ_STATE_MOD, "bz_state_get_portal_charges", p1), 2)
        gsc.sim_time_ms = 31000  # 26s after first throw (>= 25s)
        portal2 = gsc.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", p1)
        self.assertIsNot(portal2, UNDEFINED)
        portal2_fx_ent = portal2.get_field("bz_fx_ent")
        self.assertIsNot(portal2_fx_ent, UNDEFINED)
        self.assertEqual(gsc.call(BZ_STATE_MOD, "bz_state_get_portal_charges", p1), 1)

        # Close portal1 explicitly (deletes both portal AND portal.bz_fx_ent cleanly),
        # then end_game cleans up portal2 + portal2.bz_fx_ent with zero double-deletes
        gsc.call(BZ_SPECIAL_MOD, "bz_special_close_portal", portal)
        self.assertTrue(portal.deleted)
        self.assertTrue(portal_fx_ent.deleted)
        self.assertFalse(portal2.deleted)
        self.assertFalse(portal2_fx_ent.deleted)
        gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.assertTrue(portal2.deleted)
        self.assertTrue(portal2_fx_ent.deleted)
        self.assertEqual(portal.delete_count, 1)
        self.assertEqual(portal_fx_ent.delete_count, 1)
        self.assertEqual(portal2.delete_count, 1)
        self.assertEqual(portal2_fx_ent.delete_count, 1)


class TestSpecialWeaponsHudAndWaw17Compliance(unittest.TestCase):
    """Seam 5: Special HUD lane y=68, redundant SetText suppression, zero leaks & WaW 1.7 compliance."""

    def test_special_hud_lane_68_updates_deduplicates_and_cleans_up_with_zero_leaks(self) -> None:
        _dvars, gsc, p1 = _setup_special_env(map_name="nazi_zombie_factory")
        p2 = SpecialFakeEntity("PlayerTwo", ent_num=1, is_player=True)
        p2.set_field("score", 50000)
        gsc.players.append(p2)
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", p2)

        # Default gear -> zero HUD elements created
        self.assertEqual(gsc.hud_elems, [])

        # Purchase War Club -> creates top-right badge at x=-12, y=68
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_gear:war_club")
        self.assertEqual(len(gsc.hud_elems), 1)
        hud1 = gsc.hud_elems[0]
        self.assertIs(hud1.owner, p1)
        self.assertEqual(hud1.get_field("alignX"), "right")
        self.assertEqual(hud1.get_field("horzAlign"), "right")
        self.assertEqual(hud1.get_field("x"), -12)
        self.assertEqual(hud1.get_field("y"), 68)
        self.assertEqual(hud1.current_text, "MELEE: WAR CLUB")

        # Upgrade to PaP War Club + buy Portal Grenade -> "MELEE: WAR CLUB+ | PORTAL: 2"
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_gear:pap_war_club")
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_gear:portal_grenade")
        self.assertEqual(hud1.current_text, "MELEE: WAR CLUB+ | PORTAL: 2")
        self.assertTrue(all(32 <= ord(ch) <= 126 for ch in hud1.current_text))

        # Tracked in level.bz_special_hud_elems
        tracked_huds = gsc.level.get_field("bz_special_hud_elems")
        self.assertGreaterEqual(tracked_huds.size, 1)

        # Redundant HUD refresh skips SetText() to protect WaW configstrings
        writes_before = len(hud1.text_history)
        gsc.call(BZ_SPECIAL_MOD, "bz_special_update_hud", p1)
        self.assertEqual(len(hud1.text_history), writes_before)

        # Activating Portal decrements HUD count to PORTAL: 1; round_start recharges to PORTAL: 2
        gsc.sim_time_ms = 5000
        gsc.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", p1)
        self.assertEqual(hud1.current_text, "MELEE: WAR CLUB+ | PORTAL: 1")
        gsc.call(BZ_HOOKS_MOD, "bz_on_round_start", 2)
        self.assertEqual(hud1.current_text, "MELEE: WAR CLUB+ | PORTAL: 2")

        # Swapping back to Bowie drops War Club badge while preserving PORTAL: 2
        p1.give_perk("specialty_altmelee")
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_gear:equip_bowie")
        self.assertEqual(hud1.current_text, "PORTAL: 2")

        # Player 2 gets independent HUD element; Gauntlet HUD active shifts y from 68 -> 86
        gsc.dvars.set("gauntlet_enabled", "1")
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p2, "bz_station_arsenal", "buy_gear:war_club")
        self.assertEqual(len(gsc.hud_elems), 2)
        hud2 = gsc.hud_elems[1]
        self.assertIs(hud2.owner, p2)
        self.assertEqual(hud2.get_field("y"), 86)
        self.assertEqual(hud2.current_text, "MELEE: WAR CLUB")

        # Disconnect destroys p1's HUD without touching p2's HUD, and compacts level.bz_special_hud_elems
        gsc.call(BZ_SPECIAL_MOD, "bz_special_destroy_player_hud", p1)
        self.assertTrue(hud1.destroyed)
        self.assertEqual(hud1.destroy_count, 1)
        self.assertFalse(hud2.destroyed)
        compacted_huds = gsc.level.get_field("bz_special_hud_elems")
        self.assertEqual(compacted_huds.size, 1)
        self.assertIs(compacted_huds[0], hud2)

        # end_game destroys all remaining HUDs with zero leaks and zero double-destroys
        gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.assertTrue(all(h.destroyed for h in gsc.hud_elems))
        self.assertTrue(all(h.destroy_count == 1 for h in gsc.hud_elems))

    def test_tracked_entity_compaction_never_leaves_undefined_holes_or_skips_trailing_entities(self) -> None:
        _dvars, gsc, p1 = _setup_special_env(map_name="nazi_zombie_factory")
        ents = []
        for idx in range(3):
            e = SpecialFakeEntity(f"E{idx}", ent_num=120 + idx, is_player=False)
            e.set_field("bz_owner", p1)
            gsc.call(BZ_SPECIAL_MOD, "bz_special_track_entity", e)
            ents.append(e)

        # Untracking index 0 compacts [E1, E2] densely (no UNDEFINED hole at index 0)
        self.assertTrue(gsc.call(BZ_SPECIAL_MOD, "bz_special_untrack_and_delete_entity", ents[0]))
        tracked = gsc.level.get_field("bz_special_entities")
        self.assertEqual(tracked.size, 2)
        self.assertIs(tracked[0], ents[1])
        self.assertIs(tracked[1], ents[2])

        # Destroying remaining player entities deletes BOTH E1 and E2 without skipping trailing entries
        removed = gsc.call(BZ_SPECIAL_MOD, "bz_special_destroy_player_entities", p1)
        self.assertEqual(removed, 2)
        self.assertTrue(all(e.deleted and e.delete_count == 1 for e in ents))
        self.assertEqual(gsc.level.get_field("bz_special_entities").size, 0)

    def test_gate_disabled_is_complete_noop_even_when_bz_enabled(self) -> None:
        _dvars, gsc, p = _setup_special_env(
            map_name="nazi_zombie_factory",
            bz_enabled=True,
            elements_enabled=False,
        )
        self.assertIs(gsc.call(BZ_SPECIAL_MOD, "bz_special_fire_multi_crossbow", p, "bz_multi_crossbow"), UNDEFINED)
        self.assertIs(gsc.call(BZ_SPECIAL_MOD, "bz_special_fire_blade_boomerang", p, "bz_blade_boomerang"), UNDEFINED)
        self.assertIs(gsc.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", p), UNDEFINED)
        self.assertEqual(gsc.hud_elems, [])
        self.assertIs(gsc.level.get_field("bz_special_entities"), UNDEFINED)
        self.assertEqual(p.notify_commands, [])

    def test_bz_special_weapons_gsc_is_strictly_waw17_compliant(self) -> None:
        source = BZ_SPECIAL_PATH.read_text(encoding="latin1")
        tokenize(source, filename=str(BZ_SPECIAL_PATH))
        code_only = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
        self.assertIsNone(re.search(r"\bforeach\b", code_only), "Forbidden foreach in _bz_special_weapons.gsc")
        self.assertIsNone(re.search(r"\bNotifyOnCommand\s*\(", code_only, re.IGNORECASE), "Forbidden NotifyOnCommand() in WaW 1.7 Coop zombies (_bz_special_weapons.gsc)")
        self.assertIsNone(re.search(r"\bLoadFX\s*\(", code_only, re.IGNORECASE), "Forbidden LoadFX() in _bz_special_weapons.gsc (must use 0 new FX)")
        # Must use array compaction rather than sparse `arr[i] = undefined` holes
        self.assertIsNone(
            re.search(r"level\.bz_special_(?:entities|hud_elems)\s*\[[^\]]+\]\s*=\s*undefined", code_only),
            "Must compact level.bz_special_entities / level.bz_special_hud_elems instead of assigning undefined",
        )
        # Round-start portal refill delegates to _bz_state::bz_state_on_round_start (no direct write)
        round_start = code_only.split("bz_special_on_round_start( round_num )", 1)[1].split("\n}", 1)[0]
        self.assertIsNone(
            re.search(r"\.bz_portal_charges\s*=", round_start),
            "Portal charge refill must delegate to maps\\_bz_state::bz_state_on_round_start()",
        )

        non_ascii = [ch for ch in source if ord(ch) > 126 or (ord(ch) < 32 and ch not in "\t\r\n")]
        self.assertEqual(non_ascii, [], f"Non-ASCII characters in _bz_special_weapons.gsc: {non_ascii!r}")

        gsc = SpecialWeaponsGscRuntime(MOD_ROOT, FakeDvarStore())
        mod = gsc.load_module(BZ_SPECIAL_MOD)

        sync_funcs = (
            "bz_special_weapons_register",
            "bz_special_on_pre_init",
            "bz_special_on_init",
            "bz_special_on_player_connect",
            "bz_special_on_player_spawned",
            "bz_special_on_round_start",
            "bz_special_on_max_ammo",
            "bz_special_on_item_purchased",
            "bz_special_on_weapon_fired",
            "bz_special_on_actor_damage",
            "bz_special_on_end_game",
            "bz_special_war_club_smash",
            "bz_special_fire_multi_crossbow",
            "bz_special_crossbow_bolt_fly_and_stick",
            "bz_special_detonate_crossbow_bolt",
            "bz_special_fire_blade_boomerang",
            "bz_special_run_boomerang_flight",
            "bz_special_try_activate_portal",
            "bz_special_portal_tick",
            "bz_special_close_portal",
            "bz_special_update_hud",
            "bz_special_destroy_player_hud",
            "bz_special_destroy_all_huds",
        )
        for fn_name in sync_funcs:
            self.assertIn(fn_name, mod, f"Missing expected function {fn_name}() in _bz_special_weapons.gsc")
            self.assertFalse(
                _ast_contains_method_call(mod[fn_name].body, "endon"),
                f"Forbidden endon() inside synchronous caller {fn_name}()",
            )

        # Dedicated child watchers MUST hold endon() guards
        for child_fn in (
            "bz_special_watch_portal_command",
            "bz_special_watch_portal_notify",
            "bz_special_watch_player_disconnect",
            "bz_special_watch_max_ammo",
        ):
            self.assertIn(child_fn, mod)
            self.assertTrue(
                _ast_contains_method_call(mod[child_fn].body, "endon"),
                f"Child watcher {child_fn}() must hold endon() termination guard",
            )

    def test_fx_audit_forbids_looping_sparks_steam_and_mini_nuke_and_uses_safe_oneshots(self) -> None:
        source = BZ_SPECIAL_PATH.read_text(encoding="latin1")
        code_only = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
        for forbidden in (
            "wire_spark",
            "fx_zombie_wire_spark",
            "fx_elec_wire_spark_burst",
            "fx_zombie_elec_trail_oneshot",
            "zombie_mainframe_steam",
            "mini_nuke",
        ):
            self.assertIsNone(
                re.search(rf'"{re.escape(forbidden)}"', code_only),
                f"Forbidden FX token {forbidden!r} found in active _bz_special_weapons.gsc code",
            )

        # Der Riese: Boomerang prefers cached bloodsplat (never wire_spark!); Crossbow uses betty_explode
        _dvars, gsc_dr, _p = _setup_special_env(map_name="nazi_zombie_factory")
        boom_fx = gsc_dr.call(BZ_SPECIAL_MOD, "bz_special_resolve_stock_fx", "boomerang")
        self.assertEqual(boom_fx, "fx:misc/fx_zombie_bloodsplat")
        self.assertNotEqual(boom_fx, "stock_fx:wire_spark")

        xbow_fx_dr = gsc_dr.call(BZ_SPECIAL_MOD, "bz_special_resolve_stock_fx", "crossbow")
        self.assertEqual(xbow_fx_dr, "stock_fx:betty_explode")

        # Without cached bloodsplat: Boomerang falls back to wire_sparks_oneshot -> powerup_grabbed (never wire_spark)
        gsc_dr.level.set_field("bz_elem_new_fx", GscArray())
        self.assertEqual(
            gsc_dr.call(BZ_SPECIAL_MOD, "bz_special_resolve_stock_fx", "boomerang"),
            "stock_fx:wire_sparks_oneshot",
        )
        effects_dr = gsc_dr.level.get_field("_effect")
        effects_dr.set_item("wire_sparks_oneshot", UNDEFINED)
        self.assertEqual(
            gsc_dr.call(BZ_SPECIAL_MOD, "bz_special_resolve_stock_fx", "boomerang"),
            "stock_fx:powerup_grabbed",
        )

        # Crossbow fallback chain: betty_explode -> molotov_exp -> cached fx_exp_raygun_impact (NEVER mini_nuke!)
        effects_dr.set_item("betty_explode", UNDEFINED)
        effects_dr.set_item("molotov_exp", "stock_fx:molotov_exp")
        self.assertEqual(
            gsc_dr.call(BZ_SPECIAL_MOD, "bz_special_resolve_stock_fx", "crossbow"),
            "stock_fx:molotov_exp",
        )

        # Nacht (mini_nuke present in level._effect, no betty_explode/molotov_exp): uses cached raygun impact, NEVER mini_nuke
        _dvars_n, gsc_n, _pn = _setup_special_env(map_name="nazi_zombie_prototype")
        xbow_fx_nacht = gsc_n.call(BZ_SPECIAL_MOD, "bz_special_resolve_stock_fx", "crossbow")
        self.assertEqual(xbow_fx_nacht, "fx:misc/fx_exp_raygun_impact")
        self.assertNotEqual(xbow_fx_nacht, "stock_fx:mini_nuke")

    def test_multi_crossbow_drops_sky_misses_clamps_hit_height_staggers_fuses_and_plays_audio(self) -> None:
        _dvars, gsc, player = _setup_special_env(map_name="nazi_zombie_prototype")
        player.set_pos(0.0, 0.0, 0.0)
        player.set_angles(0.0, 0.0, 0.0)

        z_low = SpecialFakeEntity("ZLow", ent_num=91, is_player=False)
        z_low.set_field("health", 500)
        z_low.set_pos(200.0, 0.0, 10.0)

        z_high = SpecialFakeEntity("ZHigh", ent_num=92, is_player=False)
        z_high.set_field("health", 500)
        z_high.set_pos(320.0, 35.0, 10.0)
        gsc.ai_enemies.extend([z_low, z_high])

        # Left (-6 deg): sky miss (fraction=1.0, no entity) -> MUST be skipped!
        # Center (0 deg): hits z_low near feet (z=14 -> offset 4 -> clamped to 24.0)
        # Right (+6 deg): hits z_high high head (z=90 -> offset 80 -> clamped to 56.0)
        def mixed_trace(start: GscArray, end: GscArray, _hit_chars: bool, _ignore: Any) -> dict[str, Any]:
            yaw_deg = math.degrees(math.atan2(float(end[1]) - float(start[1]), float(end[0]) - float(start[0])))
            if yaw_deg < -1.0:
                return {"fraction": 1.0, "position": end, "entity": UNDEFINED}
            if abs(yaw_deg) <= 1.0:
                return {"fraction": 0.125, "position": GscArray([200.0, 0.0, 14.0]), "entity": z_low}
            return {"fraction": 0.20, "position": GscArray([320.0, 35.0, 90.0]), "entity": z_high}

        gsc.trace_handler = mixed_trace
        res = gsc.call(BZ_SPECIAL_MOD, "bz_special_fire_multi_crossbow", player, "bz_multi_crossbow")
        bolts = res.get_field("bolts")
        self.assertEqual(bolts.size, 2)  # Sky miss skipped cleanly!
        self.assertEqual(res.get_field("stuck_zombies"), 2)
        self.assertEqual(res.get_field("stuck_world"), 0)

        b0 = bolts[0]
        b1 = bolts[1]
        self.assertAlmostEqual(float(b0.get_field("bz_fuse_time")), 0.65)
        self.assertAlmostEqual(float(b1.get_field("bz_fuse_time")), 0.77)
        self.assertAlmostEqual(float(b0.get_field("bz_stuck_z_offset")), 24.0)  # clamped min 24
        self.assertAlmostEqual(float(b1.get_field("bz_stuck_z_offset")), 56.0)  # clamped max 56

        # Fly & detonate both bolts -> verify detonation height = z.origin[2] + clamped offset & bolt/explosion audio
        gsc.call(BZ_SPECIAL_MOD, "bz_special_crossbow_bolt_fly_and_stick", b0)
        gsc.call(BZ_SPECIAL_MOD, "bz_special_crossbow_bolt_fly_and_stick", b1)
        det0 = gsc.call(BZ_SPECIAL_MOD, "bz_special_detonate_crossbow_bolt", player, b0, False, 1)
        det1 = gsc.call(BZ_SPECIAL_MOD, "bz_special_detonate_crossbow_bolt", player, b1, False, 1)
        self.assertAlmostEqual(float(det0.get_field("center")[2]), 34.0)  # 10 + 24
        self.assertAlmostEqual(float(det1.get_field("center")[2]), 66.0)  # 10 + 56
        aliases = [s["alias"] for s in gsc.played_sounds_at_pos]
        self.assertIn("attack_whoosh", aliases)
        self.assertEqual(aliases.count("impact_wood_flesh"), 2)
        self.assertEqual(aliases.count("grenade_explode_default"), 2)

        # ADS tightens spread from [-6, 0, +6] to [-2.5, 0, +2.5]
        ads_yaws: list[float] = []
        player.ads_pressed = True

        def ads_trace(start: GscArray, end: GscArray, _hit_chars: bool, _ignore: Any) -> dict[str, Any]:
            yaw_deg = math.degrees(math.atan2(float(end[1]) - float(start[1]), float(end[0]) - float(start[0])))
            ads_yaws.append(round(yaw_deg, 1))
            return {"fraction": 0.25, "position": GscArray([250.0, float(end[1]) * 0.25, 40.0]), "entity": UNDEFINED}

        gsc.trace_handler = ads_trace
        ads_res = gsc.call(BZ_SPECIAL_MOD, "bz_special_fire_multi_crossbow", player, "bz_multi_crossbow")
        self.assertEqual(ads_yaws, [-2.5, 0.0, 2.5])
        self.assertTrue(ads_res.get_field("ads"))
        player.ads_pressed = False

        # Pure sky shot (all 3 fraction >= 0.99, no entity) -> 0 bolts spawned
        gsc.trace_handler = lambda s, e, _hc, _ig: {"fraction": 0.995, "position": e, "entity": UNDEFINED}
        sky_res = gsc.call(BZ_SPECIAL_MOD, "bz_special_fire_multi_crossbow", player, "bz_multi_crossbow")
        self.assertEqual(sky_res.get_field("bolts").size, 0)

    def test_boomerang_flies_smooth_elliptical_arc_spins_without_aliasing_and_refills_on_catch(self) -> None:
        _dvars, gsc, player = _setup_special_env(map_name="nazi_zombie_factory")
        player.set_pos(0.0, 0.0, 0.0)
        player.set_angles(-24.0, 0.0, 0.0)
        player.give_weapon("bz_blade_boomerang", make_current=True)
        player.weapon_clips = {"bz_blade_boomerang": 0}

        res = gsc.call(BZ_SPECIAL_MOD, "bz_special_fire_blade_boomerang", player, "bz_blade_boomerang")
        blade = res.get_field("blade")
        # YZ-plane 3-wing boomerang tilted -20 deg relative to view pitch and spun via RotateRoll around +X
        # so the 3-wing star stays face-on across level and angled throws (O18/F19/A18/O21/F24).
        ang = blade.get_field("angles")
        self.assertAlmostEqual(float(ang[0]), -44.0)  # player pitch=-24.0 -> -24.0 - 20.0
        self.assertAlmostEqual(float(ang[2]), 0.0)

        # Downward-aimed throw (+45 deg pitch) also preserves relative -20 deg tilt (+25 deg) instead of turning edge-on
        player.set_angles(45.0, 0.0, 0.0)
        res_down = gsc.call(BZ_SPECIAL_MOD, "bz_special_fire_blade_boomerang", player, "bz_blade_boomerang")
        down_ang = res_down.get_field("blade").get_field("angles")
        self.assertAlmostEqual(float(down_ang[0]), 25.0)
        self.assertAlmostEqual(float(down_ang[2]), 0.0)
        player.set_angles(-24.0, 0.0, 0.0)

        # Simulate player strafing laterally while the boomerang is in flight -> must home to moved player!
        gsc.played_fx.clear()
        player.set_pos(30.0, 120.0, 0.0)
        flight_res = gsc.call(
            BZ_SPECIAL_MOD,
            "bz_special_run_boomerang_flight",
            player,
            blade,
            res.get_field("start_pos"),
            res.get_field("apex"),
            res.get_field("damage"),
            res.get_field("max_pierce"),
        )
        self.assertTrue(flight_res.get_field("caught"))
        self.assertTrue(flight_res.get_field("refilled_clip"))
        self.assertEqual(player.weapon_clips["bz_blade_boomerang"], 1)
        self.assertIn((player, "knife_pull_plr"), gsc.played_local_sounds)

        # 22 total steps (11 outbound + 11 return) with smooth 135 deg/tick RotateRoll spin and light 2-puff trail (O18/F19/F20)
        self.assertEqual(len(blade.move_calls), 22)
        self.assertEqual(len(blade.rotate_roll_calls), 22)
        self.assertTrue(all(deg == 135.0 and dt == 0.05 for deg, dt in blade.rotate_roll_calls))
        self.assertEqual(len(gsc.played_fx), 2)

        # True oval arc: outbound bows left (+Y when aiming +X), return sweeps around & homes to moved player (30, 120)
        outbound_ys = [pos[1] for pos, _dt in blade.move_calls[:11]]
        self.assertGreater(max(outbound_ys), 30.0)
        end_pos, _end_dt = blade.move_calls[-1]
        self.assertLess(math.hypot(end_pos[0] - 30.0, end_pos[1] - 120.0), 15.0)

        # Downed player (Last Stand) must NOT receive boomerang catch refill, catch sound, or caught=1 telemetry (A9/O13)
        gsc.played_local_sounds.clear()
        gsc.emitted_events.clear()
        player.weapon_clips["bz_blade_boomerang"] = 0
        player.set_field("is_in_laststand", True)
        res2 = gsc.call(BZ_SPECIAL_MOD, "bz_special_fire_blade_boomerang", player, "bz_blade_boomerang")
        flight_downed = gsc.call(
            BZ_SPECIAL_MOD,
            "bz_special_run_boomerang_flight",
            player,
            res2.get_field("blade"),
            res2.get_field("start_pos"),
            res2.get_field("apex"),
            res2.get_field("damage"),
            res2.get_field("max_pierce"),
        )
        self.assertFalse(flight_downed.get_field("caught"))
        self.assertFalse(flight_downed.get_field("refilled_clip"))
        self.assertEqual(player.weapon_clips["bz_blade_boomerang"], 0)
        self.assertEqual(gsc.played_local_sounds, [])
        self.assertTrue(any("caught=0;refilled=0" in ev for ev in gsc.emitted_events))
        player.set_field("is_in_laststand", False)

        # Blocked launch against angled cover stays strictly on player's side of the plane, skips model (<16u), and uses short bounce (A12/S14/F17)
        player.set_pos(0.0, 0.0, 0.0)
        player.set_angles(0.0, 0.0, 0.0)
        gsc.played_fx.clear()

        def angled_wall_plane(pt):
            return float(pt[0]) + 0.75 * float(pt[1]) + 0.75 * (float(pt[2]) - 60.0) - 17.0

        def angled_trace(start, end, _hc, _ig):
            sd, ed = angled_wall_plane(start), angled_wall_plane(end)
            if sd * ed < 0.0:
                frac = sd / (sd - ed)
                hit = GscArray([float(start[i]) + frac * (float(end[i]) - float(start[i])) for i in range(3)])
                return {"fraction": frac, "position": hit, "entity": UNDEFINED}
            return {"fraction": 1.0, "position": end, "entity": UNDEFINED}

        gsc.trace_handler = angled_trace
        res_blocked = gsc.call(BZ_SPECIAL_MOD, "bz_special_fire_blade_boomerang", player, "bz_blade_boomerang")
        spawn_pt = res_blocked.get_field("start_pos")
        self.assertLess(angled_wall_plane(spawn_pt), 0.0, "Blocked launch must stay on player side of angled cover")
        blocked_blade = res_blocked.get_field("blade")
        self.assertIs(blocked_blade.get_field("model"), UNDEFINED, "Point-blank <16u throw must skip SetModel")
        gsc.call(
            BZ_SPECIAL_MOD,
            "bz_special_run_boomerang_flight",
            player,
            blocked_blade,
            spawn_pt,
            res_blocked.get_field("apex"),
            res_blocked.get_field("damage"),
            res_blocked.get_field("max_pierce"),
        )
        self.assertEqual(len(blocked_blade.move_calls), 6, "Short throw (<48u) must use 3 outbound + 3 return steps")
        self.assertEqual(gsc.played_fx, [], "Short throw (<48u) must suppress trail FX")
        gsc.trace_handler = None

        # Lethal crossbow piercing impact leaves bolt unlinked at hit_pos (no corpse carry)
        z_fragile = SpecialFakeEntity("ZFragile", ent_num=98, is_player=False)
        z_fragile.set_field("health", 100)
        z_fragile.set_pos(200.0, 0.0, 0.0)
        gsc.ai_enemies.append(z_fragile)
        bolt_lethal = SpecialFakeEntity("BoltLethal", ent_num=99, is_player=False)
        bolt_lethal.set_pos(24.0, 0.0, 60.0)
        bolt_lethal.set_field("bz_owner", player)
        bolt_lethal.set_field("bz_stuck_entity", z_fragile)
        bolt_lethal.set_field("bz_stuck_z_offset", 44.0)
        bolt_lethal.set_field("bz_travel_time", 0.05)
        bolt_lethal.set_field("bz_round_num", 1)
        gsc.call(BZ_SPECIAL_MOD, "bz_special_crossbow_bolt_fly_and_stick", bolt_lethal)
        self.assertEqual(z_fragile.get_field("health"), 0)
        self.assertIsNone(bolt_lethal.linked_to)
        self.assertIs(bolt_lethal.get_field("bz_stuck_entity"), UNDEFINED)

    def test_special_weapons_skip_hidden_spawning_hellhounds_and_never_force_teleport_them(self) -> None:
        _dvars, gsc, p1 = _setup_special_env(map_name="nazi_zombie_factory")
        p1.set_pos(0.0, 0.0, 0.0)
        p1.set_angles(0.0, 0.0, 0.0)

        dog_spawning = SpecialFakeEntity("SpawningDog", ent_num=95, is_player=False)
        dog_spawning.set_field("health", 1000)
        dog_spawning.set_field("animname", "zombie_dog")
        dog_spawning.set_field("ignoreall", True)
        dog_spawning.set_pos(80.0, 0.0, 0.0)

        dog_active = SpecialFakeEntity("ActiveDog", ent_num=96, is_player=False)
        dog_active.set_field("health", 1000)
        dog_active.set_field("animname", "zombie_dog")
        dog_active.set_field("ignoreall", False)
        dog_active.set_pos(90.0, 10.0, 0.0)
        gsc.ai_enemies.extend([dog_spawning, dog_active])

        # Direct push helper refuses hidden spawning dog (zero ForceTeleport)
        pushed = gsc.call(
            BZ_SPECIAL_MOD,
            "bz_special_push_zombie_safely",
            dog_spawning,
            GscArray([0.0, 0.0, 0.0]),
            GscArray([1.0, 0.0, 0.0]),
            112,
        )
        self.assertFalse(pushed)
        self.assertEqual(dog_spawning.origin_history, [])

        # PaP War Club smash skips hidden spawning dog; damages active dog with 0.55 stagger floor and ZERO ForceTeleport
        gsc.call(BZ_SPECIAL_MOD, "bz_special_war_club_smash", p1, UNDEFINED, GscArray([80.0, 0.0, 0.0]), True, 500)
        self.assertEqual(dog_spawning.damage_events, [])
        self.assertEqual(dog_spawning.origin_history, [])
        self.assertIs(dog_spawning.get_field("bz_war_club_staggered"), UNDEFINED)
        self.assertEqual(len(dog_active.damage_events), 1)
        self.assertEqual(dog_active.origin_history, [])
        self.assertAlmostEqual(float(dog_active.get_field("moveplaybackrate")), 0.55)

        # Multi-Crossbow detonation skips hidden spawning dog
        bolt = SpecialFakeEntity("DogBolt", ent_num=97, is_player=False)
        bolt.set_pos(80.0, 0.0, 20.0)
        bolt.set_field("bz_detonated", False)
        gsc.call(BZ_SPECIAL_MOD, "bz_special_detonate_crossbow_bolt", p1, bolt, False, 1)
        self.assertEqual(dog_spawning.damage_events, [])

        # Blade Boomerang pierce skips hidden spawning dog
        pierced = GscArray()
        gsc.call(BZ_SPECIAL_MOD, "bz_special_boomerang_pierce_at", p1, GscArray([80.0, 0.0, 20.0]), 300, 6, pierced)
        self.assertEqual(dog_spawning.damage_events, [])


if __name__ == "__main__":
    unittest.main()
