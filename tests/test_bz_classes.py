"""Offline TDD contract suite for P1-T5 (#16): 6-Class System
(Field Medic, Titan, Sapper, Daredevil, Assassin, Broker).

Executes real WaW 1.7 `.gsc` scripts (`mod/maps/_bz_classes.gsc` composed with
`_bz_hooks.gsc`, `_bz_rules.gsc`, `_bz_state.gsc`, `_bz_stations.gsc`, `_bz_log.gsc`)
through an extended runtime built on `tests/gsc_runtime.py` without modifying it.
"""

from __future__ import annotations

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

BZ_CLASSES_MOD = "maps\\_bz_classes"
BZ_STATE_MOD = "maps\\_bz_state"
BZ_RULES_MOD = "maps\\_bz_rules"
BZ_STATIONS_MOD = "maps\\_bz_stations"
BZ_CLASSES_PATH = MOD_ROOT / "maps" / "_bz_classes.gsc"

ALL_CLASS_IDS = ("medic", "titan", "sapper", "daredevil", "assassin", "broker")


class FakeHudElem(GscStruct):
    """Fake WaW 1.7 NewClientHudElem() handle for HUD lifecycle & leak tests."""

    def __init__(self, owner: Any) -> None:
        super().__init__()
        self.owner = owner
        self.text: str = ""
        self.set_text_calls: list[str] = []
        self.destroyed: bool = False


class ClassFakeEntity(FakeEntity):
    """Extended FakeEntity supporting velocity, ammo, grenades, contents, and damage."""

    def __init__(
        self,
        name: str = "player_0",
        ent_num: int = 0,
        is_player: bool = True,
        origin: tuple[float, float, float] = (0.0, 0.0, 64.0),
    ) -> None:
        super().__init__(name=name, ent_num=ent_num, is_player=is_player)
        self.set_field("origin", GscArray([origin[0], origin[1], origin[2]]))
        self.velocity: list[float] = [0.0, 0.0, 0.0]
        self.velocity_calls: list[tuple[float, float, float]] = []
        self.on_ground: bool = True
        self.ammo_stock: dict[str, int] = {}
        self.ammo_clip: dict[str, int] = {}
        self.contents: int = 16777216  # Realistic non-zero WaW actor contents bitmask
        self.contents_history: list[int] = []
        self.damage_taken: list[tuple[int, Any, Any]] = []
        self.notifies: list[str] = []

    def set_origin(self, x: float, y: float, z: float) -> None:
        self.set_field("origin", GscArray([x, y, z]))

    def set_velocity(self, vx: float, vy: float, vz: float) -> None:
        self.velocity = [float(vx), float(vy), float(vz)]


class BzClassesRuntime(BzGscRuntime):
    """Extended BzGscRuntime adding WaW 1.7 class-related engine builtins & methods."""

    def __init__(self, mod_root: Path, dvars: FakeDvarStore | None = None) -> None:
        super().__init__(mod_root, dvars)
        self.zombies: list[ClassFakeEntity] = []
        self.hud_elems: list[FakeHudElem] = []
        self.weapon_clip_sizes: dict[str, int] = {
            "thompson": 20,
            "colt": 8,
            "browning": 100,
            "stg44": 30,
        }
        self.weapon_max_ammo: dict[str, int] = {
            "thompson": 200,
            "colt": 80,
            "browning": 500,
            "stg44": 180,
        }

    def _call_builtin(self, name_lower: str, args: list[Any], line: int) -> tuple[bool, Any]:
        if name_lower == "newclienthudelem":
            owner = args[0] if args else UNDEFINED
            elem = FakeHudElem(owner=owner)
            self.hud_elems.append(elem)
            return True, elem
        if name_lower == "getaispeciesarray":
            return True, GscArray(list(self.zombies))
        if name_lower == "weaponclipsize":
            weap = _waw_to_str(args[0]).lower() if args else ""
            return True, self.weapon_clip_sizes.get(weap, 30)
        if name_lower == "weaponmaxammo":
            weap = _waw_to_str(args[0]).lower() if args else ""
            return True, self.weapon_max_ammo.get(weap, 240)
        return super()._call_builtin(name_lower, args, line)

    def _exec_method(self, receiver: Any, method: str, args: list[Any], line: int) -> Any:
        if method == "notsolid":
            raise AssertionError("Forbidden NotSolid() call! Must use SetContents(0)/restore instead.")
        if isinstance(receiver, FakeHudElem):
            if method == "settext":
                txt = _waw_to_str(args[0]) if args else ""
                receiver.text = txt
                receiver.set_text_calls.append(txt)
                return UNDEFINED
            if method == "destroy":
                receiver.destroyed = True
                return UNDEFINED
        if isinstance(receiver, ClassFakeEntity):
            if method == "getvelocity":
                return GscArray(list(receiver.velocity))
            if method == "setvelocity":
                vec = args[0]
                v = (float(vec[0]), float(vec[1]), float(vec[2]))
                receiver.velocity = [v[0], v[1], v[2]]
                receiver.velocity_calls.append(v)
                return UNDEFINED
            if method == "isonground":
                return receiver.on_ground
            if method == "getweaponammostock":
                w = _waw_to_str(args[0]).lower() if args else ""
                return receiver.ammo_stock.get(w, 0)
            if method == "setweaponammostock":
                w = _waw_to_str(args[0]).lower()
                amt = int(args[1])
                receiver.ammo_stock[w] = amt
                return UNDEFINED
            if method == "getweaponammoclip":
                w = _waw_to_str(args[0]).lower() if args else ""
                return receiver.ammo_clip.get(w, 0)
            if method == "setweaponammoclip":
                w = _waw_to_str(args[0]).lower()
                amt = int(args[1])
                receiver.ammo_clip[w] = amt
                return UNDEFINED
            if method == "giveweapon":
                w = _waw_to_str(args[0]).lower()
                receiver.give_weapon(w)
                return UNDEFINED
            if method == "setcontents":
                prev = receiver.contents
                new_val = int(args[0])
                receiver.contents = new_val
                receiver.contents_history.append(new_val)
                return prev
            if method == "dodamage":
                dmg = int(args[0])
                origin = args[1] if len(args) > 1 else UNDEFINED
                attacker = args[2] if len(args) > 2 else UNDEFINED
                receiver.damage_taken.append((dmg, origin, attacker))
                cur_hp = int(receiver.get_field("health"))
                receiver.set_field("health", cur_hp - dmg)
                return UNDEFINED
            if method == "notify":
                evt = _waw_to_str(args[0]) if args else ""
                receiver.notifies.append(evt)
                return UNDEFINED
        return super()._exec_method(receiver, method, args, line)


class TestBzClassesLifecycleHudAndCompliance(unittest.TestCase):
    """Slice 1: Registration, Classic/gate isolation, persistence across down/spawn, swap teardown, HUD & WaW 1.7 compliance."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzClassesRuntime(MOD_ROOT, self.dvars)
        self.p1 = ClassFakeEntity("PlayerOne", ent_num=0, origin=(0, 0, 64))
        self.p2 = ClassFakeEntity("PlayerTwo", ent_num=1, origin=(120, 0, 64))
        self.p1.set_field("score", 100000)
        self.p2.set_field("score", 100000)
        self.p1.give_weapon("thompson", make_current=True)
        self.p1.give_weapon("stielhandgranate")
        self.p1.ammo_clip["stielhandgranate"] = 4
        self.p2.give_weapon("stg44", make_current=True)
        self.p2.give_weapon("stielhandgranate")
        self.p2.ammo_clip["stielhandgranate"] = 4
        self.gsc.players.extend([self.p1, self.p2])

    def _enable_classes(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")
        self.gsc.call(BZ_CLASSES_MOD, "bz_classes_register")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

    def test_classic_mode_and_disabled_classes_gate_are_complete_noops(self) -> None:
        self.dvars.set("bz_enabled", "0")
        self.dvars.set("bz_classes_enabled", "1")
        self.gsc.call(BZ_CLASSES_MOD, "bz_classes_register")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

        self.assertEqual(self.gsc.hud_elems, [])
        self.assertEqual(self.gsc.emitted_events, [])

        # Enable bz_enabled but keep bz_classes_enabled=0
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_classes_enabled", "0")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:titan")
        self.assertEqual(self.gsc.hud_elems, [])
        self.assertEqual(self.gsc.call(BZ_STATE_MOD, "bz_state_get_class", self.p1), "")
        self.assertEqual(self.p1.get_field("maxhealth"), 100)

    def test_register_is_idempotent_and_wires_all_eleven_hooks_under_classes_gate(self) -> None:
        self.gsc.call(BZ_CLASSES_MOD, "bz_classes_register")
        self.gsc.call(BZ_CLASSES_MOD, "bz_classes_register")  # second call must be a noop

        expected_hooks = (
            "init",
            "player_connect",
            "player_spawned",
            "player_downed",
            "round_start",
            "end_game",
            "item_purchased",
            "player_damage",
            "actor_damage",
            "points_modify",
            "box_cost_modify",
        )
        hooks_table = self.gsc.level.get_field("bz_hooks")
        for hook_name in expected_hooks:
            entries = hooks_table[hook_name]
            self.assertIsNot(entries, UNDEFINED, f"Missing hook registration for {hook_name}")
            class_entries = [
                entries[i]
                for i in range(entries.size)
                if entries[i].get_field("gate") == "classes"
            ]
            self.assertEqual(len(class_entries), 1, f"Expected exactly 1 'classes' entry for {hook_name}")

    def test_class_purchase_swap_teardown_and_ascii_top_right_hud_without_leaks(self) -> None:
        self._enable_classes()
        # No HUD created before player owns a Class
        self.assertEqual(self.gsc.hud_elems, [])

        # Buy Titan (10,000 pts) via Class Altar menu response
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:titan")
        )
        self.assertEqual(self.p1.get_field("score"), 90000)
        self.assertEqual(self.p1.get_field("maxhealth"), 200)
        self.assertAlmostEqual(self.p1.get_field("bz_aggro_weight"), 2.0)

        # HUD badge created on top-right lane with ASCII text
        self.assertEqual(len(self.gsc.hud_elems), 1)
        hud = self.gsc.hud_elems[0]
        self.assertIs(hud.owner, self.p1)
        self.assertEqual(hud.get_field("alignX"), "right")
        self.assertEqual(hud.get_field("horzAlign"), "right")
        self.assertEqual(hud.get_field("x"), -12)
        self.assertEqual(hud.get_field("y"), 14)
        self.assertEqual(hud.text, "CLASS: TITAN")
        self.assertTrue(all(32 <= ord(ch) <= 126 for ch in hud.text))
        self.assertFalse(hud.destroyed)

        # Emitted CLASS_EQUIPPED telemetry
        self.assertIn(
            "BZ_EVENT|CLASS_EQUIPPED|player=PlayerOne;class=titan;previous=;swapped=0",
            self.gsc.emitted_events,
        )

        # Swap Titan -> Sapper: tears down Titan 2x HP & aggro, equips Sapper 10 grenades, reuses same HUD elem
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:sapper")
        )
        self.assertEqual(self.p1.get_field("score"), 80000)
        self.assertEqual(self.p1.get_field("maxhealth"), 100)
        self.assertAlmostEqual(self.p1.get_field("bz_aggro_weight"), 1.0)
        self.assertEqual(self.p1.ammo_clip["stielhandgranate"], 10)
        self.assertEqual(len(self.gsc.hud_elems), 1, "HUD elem must be reused on swap, not leaked")
        self.assertEqual(hud.text, "CLASS: SAPPER")
        self.assertIn(
            "BZ_EVENT|CLASS_EQUIPPED|player=PlayerOne;class=sapper;previous=titan;swapped=1",
            self.gsc.emitted_events,
        )

        # Swap Sapper -> Field Medic: clamps grenades back to 4, updates HUD to ASCII "CLASS: FIELD MEDIC"
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:medic")
        )
        self.assertEqual(self.p1.ammo_clip["stielhandgranate"], 4)
        self.assertEqual(hud.text, "CLASS: FIELD MEDIC")

        # Co-op p2 buys Broker -> p2 gets its own HUD, p1 unaffected
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p2, "bz_station_class", "buy_class:broker")
        )
        self.assertEqual(len(self.gsc.hud_elems), 2)
        self.assertEqual(self.gsc.hud_elems[1].text, "CLASS: BROKER")

        # Disconnect p2 destroys ONLY p2's HUD
        self.gsc.call(BZ_CLASSES_MOD, "bz_class_on_disconnect", self.p2)
        self.assertTrue(self.gsc.hud_elems[1].destroyed)
        self.assertFalse(self.gsc.hud_elems[0].destroyed)

        # end_game destroys remaining p1 HUD with zero leaks
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.assertTrue(all(elem.destroyed for elem in self.gsc.hud_elems))

    def test_class_persists_across_down_bleedout_and_spawn_and_recomputes_titan_hp(self) -> None:
        self._enable_classes()
        # Equip Titan + Juggernog I + Juggernog II -> 440 HP
        self.p1.give_perk("specialty_armorvest")
        self.gsc.call(BZ_HOOKS_MOD, "bz_set_base_max_health", self.p1, "juggernog_t2", 220)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:titan")
        self.assertEqual(self.p1.get_field("maxhealth"), 440)

        # Simulate player down: perks cleared, Class MUST persist -> 200 HP
        self.p1.clear_perks()
        self.gsc.call(BZ_HOOKS_MOD, "bz_clear_base_max_health", self.p1, "juggernog_t2")
        self.gsc.call(BZ_STATE_MOD, "bz_state_on_player_downed", self.p1, 2)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_downed", self.p1)

        self.assertEqual(self.gsc.call(BZ_STATE_MOD, "bz_state_get_class", self.p1), "titan")
        self.assertEqual(self.p1.get_field("maxhealth"), 200)
        self.assertFalse(self.gsc.hud_elems[0].destroyed)

        # Simulate revive / respawn after bleedout: Class stays Titan and HP stays 200
        self.p1.set_field("maxhealth", 100)
        self.p1.set_field("health", 100)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_spawned", self.p1)
        self.assertEqual(self.gsc.call(BZ_STATE_MOD, "bz_state_get_class", self.p1), "titan")
        self.assertEqual(self.p1.get_field("maxhealth"), 200)

        # Re-buying Jugg I after revive composes cleanly back to 320 HP
        self.p1.give_perk("specialty_armorvest")
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_max_health", self.p1), 320)

    def test_bz_classes_is_strictly_waw17_compliant(self) -> None:
        source = BZ_CLASSES_PATH.read_text(encoding="latin1")
        tokenize(source, filename=str(BZ_CLASSES_PATH))
        code_only = "\n".join(line.split("//", 1)[0] for line in source.splitlines())

        # Zero foreach, zero NotSolid, zero global jump_height dvar mutation
        self.assertIsNone(re.search(r"\bforeach\b", code_only), "Forbidden foreach in _bz_classes.gsc")
        self.assertIsNone(re.search(r"\bNotSolid\b", code_only, re.IGNORECASE), "Forbidden NotSolid() in _bz_classes.gsc")
        self.assertIsNone(re.search(r"jump_height", code_only, re.IGNORECASE), "Must never mutate global jump_height")

        # ASCII-only file contents (safe for WaW bitmap HUD & console.log telemetry)
        non_ascii = [ch for ch in source if ord(ch) > 126 or (ord(ch) < 32 and ch not in "\t\r\n")]
        self.assertEqual(non_ascii, [], f"Non-ASCII characters in _bz_classes.gsc: {non_ascii!r}")

        # Zero endon() inside any synchronous hook/entry function
        classes_mod = self.gsc.load_module(BZ_CLASSES_MOD)
        sync_funcs = (
            "bz_classes_register",
            "bz_classes_init",
            "bz_classes_on_player_connect",
            "bz_classes_on_player_spawned",
            "bz_classes_on_player_downed",
            "bz_classes_on_round_start",
            "bz_classes_on_end_game",
            "bz_classes_on_item_purchased",
            "bz_classes_on_player_damage",
            "bz_classes_on_actor_damage",
            "bz_classes_on_points_modify",
            "bz_classes_on_box_cost_modify",
            "bz_class_apply",
            "bz_class_teardown",
            "bz_class_update_hud",
            "bz_class_destroy_hud",
            "bz_class_on_disconnect",
            "bz_medic_get_revive_time",
            "bz_medic_is_instant_revive",
            "bz_medic_ammo_regen_tick",
            "bz_titan_update_stationary_state",
            "bz_titan_apply_aggro_bias",
            "bz_sapper_get_grenade_radius",
            "bz_sapper_on_grenade_detonate",
            "bz_sapper_on_wall_buy",
            "bz_sapper_fire_trap_tick",
            "bz_sapper_betty_trap_check",
            "bz_daredevil_movement_tick",
            "bz_daredevil_execute_slam",
            "bz_daredevil_end_burst",
            "bz_assassin_ghost_tick",
            "bz_assassin_restore_all_zombies",
            "bz_broker_is_near_ally",
        )
        for fn_name in sync_funcs:
            self.assertIn(fn_name, classes_mod, f"Missing exported function {fn_name}() in _bz_classes.gsc")
            self.assertFalse(
                _ast_contains_method_call(classes_mod[fn_name].body, "endon"),
                f"Forbidden endon() inside synchronous function {fn_name}()",
            )


class TestFieldMedicAndTitanClasses(unittest.TestCase):
    """Slice 2: Field Medic (revive speed + ammo regen/ally trickle) & Titan (2x HP, 2x aggro, 2x stationary dmg)."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzClassesRuntime(MOD_ROOT, self.dvars)
        self.p1 = ClassFakeEntity("PlayerOne", ent_num=0, origin=(0, 0, 64))
        self.p2 = ClassFakeEntity("PlayerTwo", ent_num=1, origin=(150, 0, 64))
        self.p3 = ClassFakeEntity("FarAlly", ent_num=2, origin=(400, 0, 64))
        for p in (self.p1, self.p2, self.p3):
            p.set_field("score", 50000)
            p.give_weapon("thompson", make_current=True)
            p.ammo_stock["thompson"] = 40
            p.give_weapon("stielhandgranate")
            p.ammo_clip["stielhandgranate"] = 4
        self.gsc.players.extend([self.p1, self.p2, self.p3])

        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")
        self.gsc.call(BZ_CLASSES_MOD, "bz_classes_register")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

    def test_field_medic_revive_speed_with_and_without_quick_revive(self) -> None:
        # Baseline non-medic without QR = 3.0s, with QR = 1.5s
        self.assertAlmostEqual(
            self.gsc.call(BZ_CLASSES_MOD, "bz_medic_get_revive_time", self.p1, 3.0),
            3.0,
        )
        self.assertFalse(self.gsc.call(BZ_CLASSES_MOD, "bz_medic_is_instant_revive", self.p1))

        # Equip Field Medic without Quick Revive -> 2x faster (1.5s), not instant
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:medic")
        self.assertAlmostEqual(
            self.gsc.call(BZ_CLASSES_MOD, "bz_medic_get_revive_time", self.p1, 3.0),
            1.5,
        )
        self.assertFalse(self.gsc.call(BZ_CLASSES_MOD, "bz_medic_is_instant_revive", self.p1))

        # Acquire Quick Revive -> instant revive (0.05s engine floor + instant helper true)
        self.p1.give_perk("specialty_quickrevive")
        self.assertAlmostEqual(
            self.gsc.call(BZ_CLASSES_MOD, "bz_medic_get_revive_time", self.p1, 3.0),
            0.05,
        )
        self.assertTrue(self.gsc.call(BZ_CLASSES_MOD, "bz_medic_is_instant_revive", self.p1))

        # Swap away to Broker -> loses instant revive, returns to normal QR (1.5s)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:broker")
        self.assertAlmostEqual(
            self.gsc.call(BZ_CLASSES_MOD, "bz_medic_get_revive_time", self.p1, 3.0),
            1.5,
        )
        self.assertFalse(self.gsc.call(BZ_CLASSES_MOD, "bz_medic_is_instant_revive", self.p1))

    def test_field_medic_passive_reserve_ammo_regen_clamping_and_coop_ally_trickle(self) -> None:
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:medic")
        # Thompson clip=20, max_ammo=200. p1 at 190 -> clamps cleanly at 200 (+10).
        # p2 at 150u (within 280u aura) at 40 -> +25% of 20 = +5 -> 45.
        # p3 at 400u (outside 280u aura) at 40 -> untouched (40).
        self.p1.ammo_stock["thompson"] = 190
        self.p2.ammo_stock["thompson"] = 40
        self.p3.ammo_stock["thompson"] = 40

        summary = self.gsc.call(BZ_CLASSES_MOD, "bz_medic_ammo_regen_tick", self.p1)
        self.assertEqual(self.p1.ammo_stock["thompson"], 200)
        self.assertEqual(summary.get_field("self_added"), 10)
        self.assertEqual(self.p2.ammo_stock["thompson"], 45)
        self.assertEqual(summary.get_field("allies_helped"), 1)
        self.assertEqual(self.p3.ammo_stock["thompson"], 40)

        # Full magazine grant when well below max stock
        self.p1.ammo_stock["thompson"] = 40
        summary2 = self.gsc.call(BZ_CLASSES_MOD, "bz_medic_ammo_regen_tick", self.p1)
        self.assertEqual(self.p1.ammo_stock["thompson"], 60)
        self.assertEqual(summary2.get_field("self_added"), 20)

        # Verify Double Ammo Apex Perk raises clamp ceiling to 400
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_apex:double_ammo")
        self.p1.ammo_stock["thompson"] = 390
        self.gsc.call(BZ_CLASSES_MOD, "bz_medic_ammo_regen_tick", self.p1)
        self.assertEqual(self.p1.ammo_stock["thompson"], 400)

        # Downed medic does not regen ammo
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_downed", self.p1)
        self.p1.ammo_stock["thompson"] = 40
        self.p2.ammo_stock["thompson"] = 40
        self.gsc.call(BZ_CLASSES_MOD, "bz_medic_ammo_regen_tick", self.p1)
        self.assertEqual(self.p1.ammo_stock["thompson"], 40)
        self.assertEqual(self.p2.ammo_stock["thompson"], 40)

        # Co-op revive clears bz_is_downed and restores Medic ammo regen immediately
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_revived", self.p1, self.p2)
        self.assertFalse(self.p1.get_field("bz_is_downed"))
        revived_summary = self.gsc.call(BZ_CLASSES_MOD, "bz_medic_ammo_regen_tick", self.p1)
        self.assertEqual(revived_summary.get_field("self_added"), 20)
        self.assertEqual(self.p1.ammo_stock["thompson"], 60)

    def test_titan_health_aggro_priority_and_stationary_double_damage(self) -> None:
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:titan")
        # 2x HP composition: 200 base / 320 Jugg I / 440 Jugg II
        self.assertEqual(self.p1.get_field("maxhealth"), 200)
        self.p1.give_perk("specialty_armorvest")
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_max_health", self.p1), 320)
        self.gsc.call(BZ_HOOKS_MOD, "bz_set_base_max_health", self.p1, "juggernog_t2", 220)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_max_health", self.p1), 440)

        # 2x Zombie Aggro Priority:
        # Titan at (0,0,64), p2 at (400,0,64), Zombie at (260,0,64):
        # dist to Titan = 260 -> weighted = 130; dist to p2 = 140 -> weighted = 140.
        # Titan wins aggro despite being physically farther!
        self.p2.set_origin(400, 0, 64)
        z_mid = ClassFakeEntity("ZombieMid", ent_num=10, is_player=False, origin=(260, 0, 64))
        z_mid.set_field("health", 500)
        # Zombie right next to p2 (390,0,64): dist to Titan=390 (weighted 195), dist to p2=10 (weighted 10) -> p2 wins
        z_p2 = ClassFakeEntity("ZombieNearP2", ent_num=11, is_player=False, origin=(390, 0, 64))
        z_p2.set_field("health", 500)
        self.gsc.zombies.extend([z_mid, z_p2])

        biased = self.gsc.call(BZ_CLASSES_MOD, "bz_titan_apply_aggro_bias", self.p1)
        self.assertEqual(biased, 1)
        self.assertIs(z_mid.get_field("favoriteenemy"), self.p1)
        self.assertIsNot(z_p2.get_field("favoriteenemy"), self.p1)

        # Stationary 2x weapon damage (>= 0.25s with low horizontal speed)
        # 1. Moving -> 1.0x
        self.p1.set_velocity(180, 0, 0)
        self.assertFalse(self.gsc.call(BZ_CLASSES_MOD, "bz_titan_update_stationary_state", self.p1, 0.30))
        dmg_moving = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_mid,
            self.p1,
            self.p1,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "thompson",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg_moving, 100)

        # 2. Standing still for 0.20s (< 0.25s threshold) -> still 1.0x
        self.p1.set_velocity(0, 0, 0)
        self.assertFalse(self.gsc.call(BZ_CLASSES_MOD, "bz_titan_update_stationary_state", self.p1, 0.20))
        dmg_short = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_mid,
            self.p1,
            self.p1,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "thompson",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg_short, 100)

        # 3. Additional 0.05s (total 0.25s >= threshold) -> 2.0x weapon damage!
        self.assertTrue(self.gsc.call(BZ_CLASSES_MOD, "bz_titan_update_stationary_state", self.p1, 0.05))
        dmg_still = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_mid,
            self.p1,
            self.p1,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "thompson",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg_still, 200)

        # 4. Moving again resets stationary bonus immediately back to 1.0x
        self.p1.set_velocity(0, 120, 0)
        self.assertFalse(self.gsc.call(BZ_CLASSES_MOD, "bz_titan_update_stationary_state", self.p1, 0.05))
        dmg_moved_again = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_mid,
            self.p1,
            self.p1,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "thompson",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg_moved_again, 100)

        # 5. Swapping off Titan clears favoriteenemy bias
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:broker")
        self.assertIs(z_mid.get_field("favoriteenemy"), UNDEFINED)


class TestSapperAndBrokerClasses(unittest.TestCase):
    """Slice 3: Sapper (10 grenades, 1.5x blast, alternating wall-buy traps) & Broker (2x pts, 1.5x aura, 50% box)."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzClassesRuntime(MOD_ROOT, self.dvars)
        self.p1 = ClassFakeEntity("PlayerOne", ent_num=0, origin=(0, 0, 64))
        self.p2 = ClassFakeEntity("NearAlly", ent_num=1, origin=(200, 0, 64))
        self.p3 = ClassFakeEntity("FarAlly", ent_num=2, origin=(500, 0, 64))
        for p in (self.p1, self.p2, self.p3):
            p.set_field("score", 50000)
            p.give_weapon("thompson", make_current=True)
            p.give_weapon("stielhandgranate")
            p.ammo_clip["stielhandgranate"] = 4
        self.gsc.players.extend([self.p1, self.p2, self.p3])

        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")
        self.gsc.call(BZ_CLASSES_MOD, "bz_classes_register")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

    def test_sapper_grenade_cap_round_start_refill_and_expanded_blast_radius(self) -> None:
        # Baseline non-sapper radius is 256
        self.assertEqual(self.gsc.call(BZ_CLASSES_MOD, "bz_sapper_get_grenade_radius", self.p1, 256), 256)

        # Equip Sapper -> immediate refill to 10 grenades & 1.5x radius (384)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:sapper")
        self.assertEqual(self.p1.ammo_clip["stielhandgranate"], 10)
        self.assertEqual(self.gsc.call(BZ_CLASSES_MOD, "bz_sapper_get_grenade_radius", self.p1, 256), 384)

        # Spend 7 grenades (3 left), then trigger round_start -> refills to 10 via bz_state_consume_sapper_grenade_refill
        self.p1.ammo_clip["stielhandgranate"] = 3
        self.p2.ammo_clip["stielhandgranate"] = 2
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_round_start", 2)
        self.assertEqual(self.p1.ammo_clip["stielhandgranate"], 10)
        self.assertEqual(self.p2.ammo_clip["stielhandgranate"], 2, "Non-Sapper teammate must not get Sapper refill")
        self.assertIn(
            "BZ_EVENT|SAPPER_GRENADE_REFILL|player=PlayerOne;count=10;round=2",
            self.gsc.emitted_events,
        )

        # Max Ammo powerup refills Sapper back to 10 grenades mid-round
        self.p1.ammo_clip["stielhandgranate"] = 1
        self.p1.set_field("bz_sapper_grenade_reserve", 0)
        refilled = self.gsc.call(BZ_CLASSES_MOD, "bz_sapper_on_max_ammo", self.p1)
        self.assertEqual(refilled, 10)
        self.assertEqual(self.gsc.call(BZ_CLASSES_MOD, "bz_sapper_get_total_grenades", self.p1), 10)

        # Expanded outer-ring blast hits zombie at 320u (between 256 and 384), misses zombie at 420u
        z_outer = ClassFakeEntity("ZombieOuter", ent_num=20, is_player=False, origin=(320, 0, 64))
        z_outer.set_field("health", 500)
        z_far = ClassFakeEntity("ZombieFar", ent_num=21, is_player=False, origin=(420, 0, 64))
        z_far.set_field("health", 500)
        self.gsc.zombies.extend([z_outer, z_far])

        blast = self.gsc.call(
            BZ_CLASSES_MOD,
            "bz_sapper_on_grenade_detonate",
            self.p1,
            GscArray([0, 0, 64]),
            256,
            400,
        )
        self.assertEqual(blast.get_field("expanded_radius"), 384)
        self.assertEqual(blast.get_field("hits"), 1)
        self.assertEqual(len(z_outer.damage_taken), 1)
        self.assertGreater(z_outer.damage_taken[0][0], 0)
        self.assertEqual(len(z_far.damage_taken), 0)

    def test_sapper_wall_buy_traps_alternate_fire_and_betty_with_10s_per_wall_cooldown(self) -> None:
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:sapper")
        self.gsc.sim_time_ms = 10000

        # Non-Sapper buying a wall weapon deploys nothing
        self.assertIs(
            self.gsc.call(BZ_CLASSES_MOD, "bz_sapper_on_wall_buy", self.p2, "thompson_wall", GscArray([100, 50, 64])),
            UNDEFINED,
        )

        # 1. First wall-buy at thompson_wall -> Fire DOT trap
        trap1 = self.gsc.call(
            BZ_CLASSES_MOD, "bz_sapper_on_wall_buy", self.p1, "thompson_wall", GscArray([100, 50, 64])
        )
        self.assertIsNot(trap1, UNDEFINED)
        self.assertEqual(trap1.get_field("trap_type"), "fire")
        self.assertIn(
            "BZ_EVENT|SAPPER_TRAP_PLANTED|player=PlayerOne;wall=thompson_wall;type=fire;x=100;y=50;z=64",
            self.gsc.emitted_events,
        )

        # 2. Re-buy same wall within 10s (5s elapsed) -> blocked by per-wall cooldown
        self.gsc.sim_time_ms = 15000
        blocked = self.gsc.call(
            BZ_CLASSES_MOD, "bz_sapper_on_wall_buy", self.p1, "thompson_wall", GscArray([100, 50, 64])
        )
        self.assertIs(blocked, UNDEFINED)

        # 3. Different wall (kar98k_wall) at same timestamp -> allowed & alternates to Bouncing Betty!
        trap2 = self.gsc.call(
            BZ_CLASSES_MOD, "bz_sapper_on_wall_buy", self.p1, "kar98k_wall", GscArray([300, 50, 64])
        )
        self.assertIsNot(trap2, UNDEFINED)
        self.assertEqual(trap2.get_field("trap_type"), "betty")
        self.assertIn(
            "BZ_EVENT|SAPPER_TRAP_PLANTED|player=PlayerOne;wall=kar98k_wall;type=betty;x=300;y=50;z=64",
            self.gsc.emitted_events,
        )

        # 4. After 10s on thompson_wall (t=20000) -> cooldown expired, alternates back to Fire DOT
        self.gsc.sim_time_ms = 20000
        trap3 = self.gsc.call(
            BZ_CLASSES_MOD, "bz_sapper_on_wall_buy", self.p1, "thompson_wall", GscArray([100, 50, 64])
        )
        self.assertIsNot(trap3, UNDEFINED)
        self.assertEqual(trap3.get_field("trap_type"), "fire")

        # Verify Fire DOT tick damages zombie inside 128u radius, misses zombie outside
        z_fire = ClassFakeEntity("ZFire", ent_num=30, is_player=False, origin=(140, 50, 64))
        z_fire.set_field("health", 500)
        z_safe = ClassFakeEntity("ZSafe", ent_num=31, is_player=False, origin=(500, 500, 64))
        z_safe.set_field("health", 500)
        self.gsc.zombies.extend([z_fire, z_safe])

        fire_hits = self.gsc.call(BZ_CLASSES_MOD, "bz_sapper_fire_trap_tick", trap1)
        self.assertEqual(fire_hits, 1)
        self.assertEqual(len(z_fire.damage_taken), 1)
        self.assertEqual(len(z_safe.damage_taken), 0)

        # Verify Bouncing Betty waits until zombie enters trigger radius (96u), then blasts high damage
        self.assertFalse(self.gsc.call(BZ_CLASSES_MOD, "bz_sapper_betty_trap_check", trap2))
        self.assertFalse(trap2.get_field("detonated"))

        z_betty = ClassFakeEntity("ZBetty", ent_num=32, is_player=False, origin=(340, 50, 64))
        z_betty.set_field("health", 2000)
        self.gsc.zombies.append(z_betty)
        self.assertTrue(self.gsc.call(BZ_CLASSES_MOD, "bz_sapper_betty_trap_check", trap2))
        self.assertTrue(trap2.get_field("detonated"))
        self.assertEqual(len(z_betty.damage_taken), 1)
        self.assertGreaterEqual(z_betty.damage_taken[0][0], 1200)

        # end_game deletes spawned trap anchors cleanly
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.assertTrue(trap1.get_field("anchor").deleted)
        self.assertTrue(trap2.get_field("anchor").deleted)

    def test_broker_personal_2x_team_aura_no_double_stack_and_box_discount(self) -> None:
        # Baseline: 1x points, 950 Mystery Box
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_points_modify", self.p1, 130, "kill"), 130)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_box_cost_modify", self.p1, 950), 950)

        # Equip Broker on p1
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:broker")

        # 2x personal points (130 -> 260) and 50% off Mystery Box (950 -> 475)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_points_modify", self.p1, 130, "kill"), 260)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_box_cost_modify", self.p1, 950), 475)

        # Near Co-op ally p2 (200u <= 384u) gets 1.5x Team Points Aura (100 -> 150), pays full 950 box
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_points_modify", self.p2, 100, "kill"), 150)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_box_cost_modify", self.p2, 950), 950)

        # Far Co-op ally p3 (500u > 384u) gets 1.0x (100 -> 100)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_points_modify", self.p3, 100, "kill"), 100)

        # Two Brokers standing right next to each other MUST NOT double-stack (strictly 2.0x, NEVER 3.0x!)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p2, "bz_station_class", "buy_class:broker")
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_points_modify", self.p1, 100, "kill"), 200)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_points_modify", self.p2, 100, "kill"), 200)

        # Downed Broker stops providing Team Points Aura to non-Broker allies
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p2, "bz_station_class", "buy_class:medic")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_downed", self.p1)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_points_modify", self.p2, 100, "kill"), 100)

        # Swapping p1 off Broker restores 1x personal points and 950 box cost
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_spawned", self.p1)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:titan")
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_points_modify", self.p1, 130, "kill"), 130)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_box_cost_modify", self.p1, 950), 950)


class TestDaredevilAndAssassinClasses(unittest.TestCase):
    """Slice 4: Daredevil (per-player 3x jump, Flopper slam, fall/slam immunity, 2.5s Sprint Burst, no DR shield)
    & Assassin (5x headshot, safe SetContents(0)/restore Ghost Slip-Through with normal melee damage)."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzClassesRuntime(MOD_ROOT, self.dvars)
        self.p1 = ClassFakeEntity("PlayerOne", ent_num=0, origin=(0, 0, 64))
        self.p2 = ClassFakeEntity("PlayerTwo", ent_num=1, origin=(100, 0, 64))
        for p in (self.p1, self.p2):
            p.set_field("score", 50000)
            p.give_weapon("thompson", make_current=True)
            p.give_weapon("stielhandgranate")
            p.ammo_clip["stielhandgranate"] = 4
        self.gsc.players.extend([self.p1, self.p2])

        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")
        self.gsc.call(BZ_CLASSES_MOD, "bz_classes_register")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

    def test_daredevil_per_player_jump_height_flopper_slam_sprint_burst_and_no_dr_shield(self) -> None:
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_round_start", 3)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:daredevil")
        # Layer Stamin-Up II to verify Sprint Burst composes cleanly without stomping
        self.gsc.call(BZ_HOOKS_MOD, "bz_set_speed_modifier", self.p1, "staminup", 1.25)
        self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_speed", self.p1)

        # 1. Takeoff applies upward SetVelocity boost ONLY to Daredevil (never global jump_height dvar!)
        self.p1.on_ground = False
        self.p1.set_velocity(120, 0, 250)
        self.p1.set_origin(0, 0, 70)
        self.gsc.call(BZ_CLASSES_MOD, "bz_daredevil_movement_tick", self.p1)

        self.assertEqual(self.dvars.get("jump_height"), "", "Must NEVER mutate global jump_height dvar")
        self.assertEqual(len(self.p1.velocity_calls), 1)
        boosted_vx, boosted_vy, boosted_vz = self.p1.velocity_calls[0]
        self.assertAlmostEqual(boosted_vx, 120.0)
        self.assertAlmostEqual(boosted_vy, 0.0)
        # sqrt(3) * 250 = 433.0 for 3x jump height
        self.assertAlmostEqual(boosted_vz, 433.0, delta=2.0)

        # Co-op teammate jumping is completely unaffected
        self.p2.on_ground = False
        self.p2.set_velocity(100, 0, 250)
        self.gsc.call(BZ_CLASSES_MOD, "bz_daredevil_movement_tick", self.p2)
        self.assertEqual(self.p2.velocity_calls, [])

        # 2. Climb to peak Z=184 (fall_height = 184 - 64 = 120 >= 64) and land near zombies
        self.p1.set_origin(0, 0, 184)
        self.p1.set_velocity(120, 0, 0)
        self.gsc.call(BZ_CLASSES_MOD, "bz_daredevil_movement_tick", self.p1)

        z_near = ClassFakeEntity("ZNear", ent_num=40, is_player=False, origin=(150, 0, 64))
        z_near.set_field("health", 2000)
        z_far = ClassFakeEntity("ZFar", ent_num=41, is_player=False, origin=(260, 0, 64))
        z_far.set_field("health", 2000)
        self.gsc.zombies.extend([z_near, z_far])

        # Land at Z=64 -> triggers height-scaled slam (round 3, h=120 -> dmg=1080, radius=208)
        self.p1.on_ground = True
        self.p1.set_origin(0, 0, 64)
        self.p1.set_velocity(120, 0, 0)
        self.gsc.call(BZ_CLASSES_MOD, "bz_daredevil_movement_tick", self.p1)

        self.assertEqual(len(z_near.damage_taken), 1)
        self.assertEqual(z_near.damage_taken[0][0], 1080)
        self.assertEqual(len(z_far.damage_taken), 0)
        self.assertIn(
            "BZ_EVENT|DAREDEVIL_SLAM|player=PlayerOne;height=120;damage=1080;radius=208;hits=1",
            self.gsc.emitted_events,
        )

        # 3. Sprint Burst activated on landing: 1.25 (Stamin-Up II) * 1.35 = 1.6875
        self.assertTrue(self.p1.get_field("bz_daredevil_burst_active"))
        self.assertAlmostEqual(self.p1.get_field("bz_move_speed_scale"), 1.6875)

        # 4. Damage immunity: fall & own slam = 0; zombie melee = full 50 (NO extra DR shield!)
        dmg_fall = self.gsc.call_on(
            self.p1,
            BZ_HOOKS_MOD,
            "bz_player_damage_override",
            self.p1,
            self.p1,
            80,
            0,
            "MOD_FALLING",
            "none",
            UNDEFINED,
            UNDEFINED,
            "none",
            0,
            0,
        )
        self.assertEqual(dmg_fall, 0)

        dmg_slam = self.gsc.call_on(
            self.p1,
            BZ_HOOKS_MOD,
            "bz_player_damage_override",
            self.p1,
            self.p1,
            120,
            0,
            "MOD_EXPLOSIVE",
            "bz_daredevil_slam",
            UNDEFINED,
            UNDEFINED,
            "none",
            0,
            0,
        )
        self.assertEqual(dmg_slam, 0)

        dmg_melee_during_burst = self.gsc.call_on(
            self.p1,
            BZ_HOOKS_MOD,
            "bz_player_damage_override",
            z_near,
            z_near,
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
        self.assertEqual(dmg_melee_during_burst, 50, "Daredevil must have NO extra damage-reduction shield")

        # 5. Ending Sprint Burst restores Stamin-Up II (1.25), never stomping to 1.0
        self.gsc.call(BZ_CLASSES_MOD, "bz_daredevil_end_burst", self.p1)
        self.assertFalse(self.p1.get_field("bz_daredevil_burst_active"))
        self.assertAlmostEqual(self.p1.get_field("bz_move_speed_scale"), 1.25)

        # 6. Small hop (< 64u) triggers no slam and no burst
        self.p1.on_ground = False
        self.p1.set_origin(0, 0, 90)
        self.p1.set_velocity(0, 0, 10)
        self.gsc.call(BZ_CLASSES_MOD, "bz_daredevil_movement_tick", self.p1)
        self.p1.on_ground = True
        self.p1.set_origin(0, 0, 64)
        self.gsc.call(BZ_CLASSES_MOD, "bz_daredevil_movement_tick", self.p1)
        self.assertFalse(self.p1.get_field("bz_daredevil_burst_active"))
        self.assertEqual(len(z_near.damage_taken), 1)

    def test_assassin_5x_headshot_and_safe_ghost_slip_through_contents_restore(self) -> None:
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:assassin")

        z_close = ClassFakeEntity("ZClose", ent_num=50, is_player=False, origin=(48, 0, 64))
        z_close.set_field("health", 1000)
        orig_contents = z_close.contents  # 16777216
        z_far = ClassFakeEntity("ZFar", ent_num=51, is_player=False, origin=(250, 0, 64))
        z_far.set_field("health", 1000)
        self.gsc.zombies.extend([z_close, z_far])

        # 1. 5x headshot/critical damage on head, helmet, neck; 1x on torso
        for loc in ("head", "helmet", "neck"):
            dmg = self.gsc.call(
                BZ_HOOKS_MOD,
                "bz_actor_damage_dispatch",
                z_close,
                self.p1,
                self.p1,
                100,
                0,
                "MOD_RIFLE_BULLET",
                "thompson",
                UNDEFINED,
                UNDEFINED,
                loc,
                0,
            )
            self.assertEqual(dmg, 500, f"Assassin should deal 5x on {loc}")

        dmg_body = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_close,
            self.p1,
            self.p1,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "thompson",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg_body, 100)

        # 2. Ghost Slip-Through inactive while standing still
        self.p1.set_velocity(0, 0, 0)
        self.gsc.call(BZ_CLASSES_MOD, "bz_assassin_ghost_tick", self.p1)
        self.assertEqual(z_close.contents, orig_contents)

        # 3. Moving near zombie calls SetContents(0) on close zombie only (never NotSolid)
        self.p1.set_velocity(200, 0, 0)
        self.gsc.call(BZ_CLASSES_MOD, "bz_assassin_ghost_tick", self.p1)
        self.assertEqual(z_close.contents, 0)
        self.assertEqual(z_far.contents, orig_contents)

        # 4. Zombies STILL land full normal melee damage while ghosted
        melee_dmg = self.gsc.call_on(
            self.p1,
            BZ_HOOKS_MOD,
            "bz_player_damage_override",
            z_close,
            z_close,
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
        self.assertEqual(melee_dmg, 50)

        # 5. Stopping restores original contents cleanly
        self.p1.set_velocity(0, 0, 0)
        self.gsc.call(BZ_CLASSES_MOD, "bz_assassin_ghost_tick", self.p1)
        self.assertEqual(z_close.contents, orig_contents)

        # 6. Co-op refcount safety: two moving Assassins share zombie, restoring only after both release
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p2, "bz_station_class", "buy_class:assassin")
        self.p2.set_origin(60, 0, 64)
        self.p1.set_velocity(200, 0, 0)
        self.p2.set_velocity(200, 0, 0)
        self.gsc.call(BZ_CLASSES_MOD, "bz_assassin_ghost_tick", self.p1)
        self.gsc.call(BZ_CLASSES_MOD, "bz_assassin_ghost_tick", self.p2)
        self.assertEqual(z_close.contents, 0)

        # p1 goes down -> p2 still moving nearby keeps contents=0
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_downed", self.p1)
        self.assertEqual(z_close.contents, 0)

        # p2 swaps off Assassin -> last ref released, original contents restored!
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p2, "bz_station_class", "buy_class:broker")
        self.assertEqual(z_close.contents, orig_contents)


if __name__ == "__main__":
    unittest.main()
