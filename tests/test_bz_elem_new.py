"""Offline TDD contract suite for P2-T3 (#25): New Elemental Primary Weapons
(Acid Sprayer & Cryo Cannon), part of Parent Spec #19.

Exercises real WaW 1.7 `.gsc` source (`mod/maps/_bz_elem_new.gsc`) through an
extended GSC runtime built on `tests/gsc_runtime.py` + `BzGscRuntime`
(without modifying `tests/gsc_runtime.py` or `tests/test_bz_hooks_and_build.py`).
"""

from __future__ import annotations

import math
from pathlib import Path
import re
from typing import Any
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_ROOT = REPO_ROOT / "mod"

from tests.gsc_runtime import (  # noqa: E402
    FakeDvarStore,
    GscArray,
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

BZ_ELEM_NEW_MOD = "maps\\_bz_elem_new"
BZ_ELEM_NEW_PATH = MOD_ROOT / "maps" / "_bz_elem_new.gsc"
BZ_PAP_MOD = "maps\\_bz_pap"
BZ_PERKS_MOD = "maps\\_bz_perks"
BZ_CLASSES_MOD = "maps\\_bz_classes"
BZ_STATE_MOD = "maps\\_bz_state"

VERIFIED_STOCK_FX_PATHS: frozenset[str] = frozenset(
    {
        "maps/zombie/fx_zombie_light_glow_green",
        "misc/fx_exp_raygun_impact",
        "misc/fx_zombie_powerup_on",
        "maps/zombie/fx_zombie_mainframe_steam",
        "maps/zombie/fx_zombie_tesla_shock_secondary",
        "env/electrical/fx_elec_short_oneshot",
        "bio/player/fx_footstep_water",
    }
)


class ElemNewFakeEntity(FakeEntity):
    """Extends FakeEntity with eye/angles, zombie movement rate, and damage logs."""

    def __init__(
        self,
        name: str = "player_0",
        ent_num: int = 0,
        is_player: bool = True,
        origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
        angles: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        super().__init__(name=name, ent_num=ent_num, is_player=is_player)
        self.set_field("origin", GscArray([origin[0], origin[1], origin[2]]))
        self.angles: tuple[float, float, float] = angles
        self.eye_offset_z: float = 60.0 if is_player else 48.0
        self.damage_events: list[dict[str, Any]] = []
        if not is_player:
            self.set_field("moveplaybackrate", 1.0)


class ElemNewGscRuntime(BzGscRuntime):
    """Extends BzGscRuntime with WaW 1.7 FX, AI, and eye/angle trace builtins."""

    def __init__(self, mod_root: Path, dvars: FakeDvarStore | None = None) -> None:
        super().__init__(mod_root, dvars)
        self.ai_enemies: list[ElemNewFakeEntity] = []
        self.loaded_fx: list[str] = []
        self.played_fx: list[tuple[Any, Any]] = []
        self.spawned_fx_entities: list[FakeEntity] = []
        self.triggered_fx_entities: list[FakeEntity] = []
        self.bullet_trace_calls: list[tuple[Any, Any, Any, Any]] = []

    def _call_builtin(self, name_lower: str, args: list[Any], line: int) -> tuple[bool, Any]:
        if name_lower == "getaispeciesarray":
            return True, GscArray([z for z in self.ai_enemies if not z.deleted])
        if name_lower == "loadfx":
            path = _waw_to_str(args[0]) if args else ""
            self.loaded_fx.append(path)
            return True, f"fx_handle:{path}"
        if name_lower == "playfx":
            fx_handle = args[0] if len(args) > 0 else UNDEFINED
            origin = args[1] if len(args) > 1 else UNDEFINED
            self.played_fx.append((fx_handle, origin))
            return True, UNDEFINED
        if name_lower == "spawnfx":
            fx_handle = args[0] if len(args) > 0 else UNDEFINED
            origin = args[1] if len(args) > 1 else GscArray([0, 0, 0])
            ent = FakeEntity(
                name="fx_entity",
                ent_num=500 + len(self.spawned_fx_entities),
                is_player=False,
            )
            ent.classname = "script_fx"
            ent.set_field("classname", "script_fx")
            ent.set_field("fx_handle", fx_handle)
            ent.set_field("origin", origin)
            self.spawned_fx_entities.append(ent)
            self.spawned_entities.append(ent)
            return True, ent
        if name_lower == "triggerfx":
            ent = args[0] if args else UNDEFINED
            if isinstance(ent, FakeEntity):
                ent.set_field("triggered", True)
                self.triggered_fx_entities.append(ent)
            return True, UNDEFINED
        if name_lower == "anglestoforward":
            ang = args[0] if args else GscArray([0.0, 0.0, 0.0])
            pitch = math.radians(float(ang[0]))
            yaw = math.radians(float(ang[1]))
            cp = math.cos(pitch)
            sp = math.sin(pitch)
            cy = math.cos(yaw)
            sy = math.sin(yaw)
            return True, GscArray([cp * cy, cp * sy, -sp])
        if name_lower == "bullettrace":
            start = args[0] if len(args) > 0 else GscArray([0, 0, 0])
            end = args[1] if len(args) > 1 else GscArray([0, 0, 0])
            hit_chars = args[2] if len(args) > 2 else False
            ignore = args[3] if len(args) > 3 else UNDEFINED
            self.bullet_trace_calls.append((start, end, hit_chars, ignore))
            return super()._call_builtin(name_lower, args, line)
        return super()._call_builtin(name_lower, args, line)

    def _exec_method(self, receiver: Any, method: str, args: list[Any], line: int) -> Any:
        if isinstance(receiver, ElemNewFakeEntity):
            if method == "geteye":
                org = receiver.get_field("origin")
                return GscArray(
                    [float(org[0]), float(org[1]), float(org[2]) + receiver.eye_offset_z]
                )
            if method == "getplayerangles":
                return GscArray(list(receiver.angles))
            if method == "dodamage":
                dmg = int(args[0]) if len(args) > 0 else 0
                pos = args[1] if len(args) > 1 else UNDEFINED
                attacker = args[2] if len(args) > 2 else UNDEFINED
                receiver.damage_events.append(
                    {"damage": dmg, "pos": pos, "attacker": attacker}
                )
                cur_hp = int(receiver.get_field("health"))
                receiver.set_field("health", max(0, cur_hp - dmg))
                return UNDEFINED
        return super()._exec_method(receiver, method, args, line)


def _setup_elem_new_env(
    map_name: str = "nazi_zombie_factory",
    *,
    bz_enabled: bool = True,
    elements_enabled: bool = True,
    pap_enabled: bool = True,
    perks_enabled: bool = False,
    classes_enabled: bool = False,
    populate_der_riese_effects: bool = True,
) -> tuple[FakeDvarStore, ElemNewGscRuntime, ElemNewFakeEntity]:
    dvars = FakeDvarStore()
    dvars.set("bz_enabled", "1" if bz_enabled else "0")
    dvars.set("bz_elements_enabled", "1" if elements_enabled else "0")
    dvars.set("bz_pap_enabled", "1" if pap_enabled else "0")
    dvars.set("bz_perks_enabled", "1" if perks_enabled else "0")
    dvars.set("bz_classes_enabled", "1" if classes_enabled else "0")
    dvars.set("bz_companions_enabled", "0")

    gsc = ElemNewGscRuntime(MOD_ROOT, dvars)
    gsc.level.set_field("script", map_name)
    gsc.level.set_field("round_number", 5)

    effects = GscArray()
    if map_name == "nazi_zombie_factory" and populate_der_riese_effects:
        effects.set_item("zapper_light_ready", "dr_fx:zapper_light_ready")
        effects.set_item("powerup_on", "dr_fx:powerup_on")
        effects.set_item("zombie_mainframe_steam", "dr_fx:zombie_mainframe_steam")
        effects.set_item("tesla_shock_secondary", "dr_fx:tesla_shock_secondary")
    elif map_name == "nazi_zombie_sumpf":
        effects.set_item("powerup_on", "sumpf_fx:powerup_on")
        effects.set_item("tesla_shock_secondary", "sumpf_fx:tesla_shock_secondary")
    gsc.level.set_field("_effect", effects)

    player = ElemNewFakeEntity(
        "PlayerOne",
        ent_num=0,
        is_player=True,
        origin=(0.0, 0.0, 0.0),
        angles=(0.0, 0.0, 0.0),
    )
    player.set_field("score", 50000)
    player.give_weapon("bz_acid_sprayer", make_current=True)
    gsc.players.append(player)

    gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_register")
    gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
    gsc.call(BZ_HOOKS_MOD, "bz_init")
    return dvars, gsc, player


class TestBzElemNewRegistrationAndZeroFxResolver(unittest.TestCase):
    """Seam 1: Idempotent registration, Feature Gate isolation, and Section 2 zero-FX resolver."""

    def test_register_is_idempotent_under_elements_gate_and_classic_mode_is_noop(self) -> None:
        dvars = FakeDvarStore()
        dvars.set("bz_enabled", "0")
        dvars.set("bz_elements_enabled", "1")
        gsc = ElemNewGscRuntime(MOD_ROOT, dvars)
        player = ElemNewFakeEntity("ClassicPlayer", ent_num=0)
        zombie = ElemNewFakeEntity("Z1", ent_num=10, is_player=False, origin=(200.0, 0.0, 0.0))
        zombie.set_field("health", 500)
        gsc.players.append(player)
        gsc.ai_enemies.append(zombie)

        gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_register")
        gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_register")  # idempotent

        hooks = gsc.level.get_field("bz_hooks")
        for hook_name in ("pre_init", "init", "weapon_fired", "actor_damage", "end_game"):
            entries = hooks[hook_name]
            self.assertIsNot(entries, UNDEFINED, f"Missing hook registration for {hook_name}")
            elem_entries = [
                entries[i]
                for i in range(entries.size)
                if entries[i].get_field("gate") == "elements"
            ]
            self.assertEqual(
                len(elem_entries),
                1,
                f"Expected exactly 1 'elements' entry on {hook_name}, got {len(elem_entries)}",
            )

        # Classic Mode (bz_enabled=0): complete noop
        gsc.call(BZ_HOOKS_MOD, "bz_init")
        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_acid_sprayer")
        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_cryo_cannon")
        dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie,
            player,
            player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "stg44",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")

        self.assertEqual(dmg, 100)
        self.assertEqual(gsc.spawned_entities, [])
        self.assertEqual(gsc.loaded_fx, [])
        self.assertEqual(gsc.played_fx, [])
        self.assertEqual(gsc.emitted_events, [])

    def test_elements_gate_off_is_noop_even_when_bz_enabled(self) -> None:
        _, gsc, player = _setup_elem_new_env(bz_enabled=True, elements_enabled=False)
        zombie = ElemNewFakeEntity("Z1", ent_num=10, is_player=False, origin=(200.0, 0.0, 0.0))
        zombie.set_field("health", 500)
        gsc.ai_enemies.append(zombie)

        before_events = len(gsc.emitted_events)
        before_entities = len(gsc.spawned_entities)
        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_acid_sprayer")
        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_cryo_cannon")

        self.assertEqual(len(gsc.emitted_events), before_events)
        self.assertEqual(len(gsc.spawned_entities), before_entities)
        self.assertEqual(gsc.loaded_fx, [])
        self.assertEqual(gsc.played_fx, [])
        self.assertEqual(float(zombie.get_field("moveplaybackrate")), 1.0)

    def test_zero_fx_resolver_prefers_der_riese_level_effect_and_falls_back_to_all_4_map_stock_fx(
        self,
    ) -> None:
        # 1. Der Riese with stock level._effect populated
        _, gsc_dr, _ = _setup_elem_new_env(
            map_name="nazi_zombie_factory", populate_der_riese_effects=True
        )
        acid_dr = gsc_dr.call(BZ_ELEM_NEW_MOD, "bz_elem_new_resolve_acid_fx")
        cryo_dr = gsc_dr.call(BZ_ELEM_NEW_MOD, "bz_elem_new_resolve_cryo_fx")

        self.assertEqual(acid_dr.get_field("puddle_fx"), "dr_fx:zapper_light_ready")
        self.assertEqual(acid_dr.get_field("puddle_fx_source"), "level_effect:zapper_light_ready")
        self.assertEqual(cryo_dr.get_field("freeze_fx"), "dr_fx:zombie_mainframe_steam")
        self.assertEqual(cryo_dr.get_field("shatter_fx"), "dr_fx:tesla_shock_secondary")

        # 2. Der Riese when zapper_light_ready absent -> prefers powerup_on
        effects = gsc_dr.level.get_field("_effect")
        effects.set_item("zapper_light_ready", UNDEFINED)
        acid_dr_fallback = gsc_dr.call(BZ_ELEM_NEW_MOD, "bz_elem_new_resolve_acid_fx")
        self.assertEqual(acid_dr_fallback.get_field("puddle_fx"), "dr_fx:powerup_on")
        self.assertEqual(acid_dr_fallback.get_field("puddle_fx_source"), "level_effect:powerup_on")

        # 3. Nacht der Untoten (empty level._effect) -> strictly verified all-4-map fallbacks
        _, gsc_nacht, _ = _setup_elem_new_env(
            map_name="nazi_zombie_prototype", populate_der_riese_effects=False
        )
        acid_nacht = gsc_nacht.call(BZ_ELEM_NEW_MOD, "bz_elem_new_resolve_acid_fx")
        cryo_nacht = gsc_nacht.call(BZ_ELEM_NEW_MOD, "bz_elem_new_resolve_cryo_fx")

        self.assertEqual(acid_nacht.get_field("puddle_fx"), "fx_handle:misc/fx_zombie_powerup_on")
        self.assertEqual(acid_nacht.get_field("impact_fx"), "fx_handle:misc/fx_exp_raygun_impact")
        self.assertEqual(
            cryo_nacht.get_field("freeze_fx"), "fx_handle:env/electrical/fx_elec_short_oneshot"
        )
        self.assertEqual(
            cryo_nacht.get_field("shatter_fx"), "fx_handle:bio/player/fx_footstep_water"
        )

        # Every LoadFX path across both maps must be strictly inside verified stock FX set,
        # and firing/shatter post-init must trigger zero additional LoadFX calls (WaW 1.7 rule).
        for path in gsc_dr.loaded_fx + gsc_nacht.loaded_fx:
            self.assertIn(path, VERIFIED_STOCK_FX_PATHS, f"Unverified FX loaded: {path!r}")

        loaded_count_before_fire = len(gsc_nacht.loaded_fx)
        gsc_nacht.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", gsc_nacht.players[0], "bz_acid_sprayer")
        gsc_nacht.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", gsc_nacht.players[0], "bz_cryo_cannon")
        self.assertEqual(len(gsc_nacht.loaded_fx), loaded_count_before_fire)

    def test_post_init_fx_resolvers_never_call_loadfx_even_without_pre_init(self) -> None:
        # Fresh runtime with NO bz_pre_init() call: resolvers must ONLY read cached handles
        # and trigger 0 LoadFX calls (strict WaW 1.7 post-wait LoadFX ban).
        dvars = FakeDvarStore()
        dvars.set("bz_enabled", "1")
        dvars.set("bz_elements_enabled", "1")
        gsc = ElemNewGscRuntime(MOD_ROOT, dvars)
        gsc.level.set_field("script", "nazi_zombie_prototype")
        gsc.level.set_field("_effect", GscArray())

        acid = gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_resolve_acid_fx")
        cryo = gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_resolve_cryo_fx")
        self.assertEqual(gsc.loaded_fx, [])
        self.assertIs(acid.get_field("puddle_fx"), UNDEFINED)
        self.assertIs(acid.get_field("impact_fx"), UNDEFINED)
        self.assertIs(cryo.get_field("freeze_fx"), UNDEFINED)
        self.assertIs(cryo.get_field("shatter_fx"), UNDEFINED)

        # Static AST verification: LoadFX() appears ONLY inside bz_elem_new_on_pre_init()
        mod = gsc.load_module(BZ_ELEM_NEW_MOD)
        for fn_name, fn_def in mod.items():
            # Check source lines via re on AST-free or simple Call check
            has_loadfx = _ast_contains_method_call(fn_def.body, "loadfx")
            self.assertFalse(has_loadfx, f"Unexpected method LoadFX on {fn_name}")
        source = BZ_ELEM_NEW_PATH.read_text(encoding="latin1")
        code_only = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
        # Every LoadFX( occurrence must lie strictly inside bz_elem_new_on_pre_init()
        pre_init_m = re.search(r"bz_elem_new_on_pre_init\(\)\s*\{.*?\n\}", code_only, re.DOTALL)
        self.assertIsNotNone(pre_init_m)
        outside_pre_init = code_only[: pre_init_m.start()] + code_only[pre_init_m.end() :]
        self.assertIsNone(
            re.search(r"\bLoadFX\s*\(", outside_pre_init, re.IGNORECASE),
            "LoadFX() must ONLY be called inside bz_elem_new_on_pre_init()",
        )


class TestAcidSprayerWeapon(unittest.TestCase):
    """Seam 2: Acid Sprayer floor-snapped puddle, 40% slow, 50% brittle, tick damage, PaP & cap."""

    def test_acid_sprayer_spawns_floor_snapped_puddle_applies_slow_brittle_tick_and_telemetry(
        self,
    ) -> None:
        _, gsc, player = _setup_elem_new_env(map_name="nazi_zombie_factory")
        gsc.sim_time_ms = 5000

        # First BulletTrace (forward aim ray) hits at (250, 0, 60); second (floor snap) hits floor z=12.
        trace_idx = {"n": 0}

        def fake_trace(start: GscArray, end: GscArray) -> dict[str, Any]:
            idx = trace_idx["n"]
            trace_idx["n"] += 1
            if idx == 0:
                return {"fraction": 0.25, "position": GscArray([250.0, 0.0, 60.0])}
            return {"fraction": 0.2, "position": GscArray([250.0, 0.0, 12.0])}

        gsc.bullet_trace_fn = fake_trace

        z_in = ElemNewFakeEntity("ZIn", ent_num=10, is_player=False, origin=(280.0, 40.0, 12.0))
        z_in.set_field("health", 500)
        z_in.set_field("moveplaybackrate", 1.0)
        z_out = ElemNewFakeEntity("ZOut", ent_num=11, is_player=False, origin=(420.0, 0.0, 12.0))
        z_out.set_field("health", 500)
        z_out.set_field("moveplaybackrate", 1.0)
        gsc.ai_enemies.extend([z_in, z_out])

        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_acid_sprayer")

        # 1. Tracked puddle spawned at floor-snapped position with 6.0s duration and 128 radius
        puddles = gsc.level.get_field("bz_acid_puddles")
        self.assertEqual(puddles.size, 1)
        puddle = puddles[0]
        p_org = puddle.get_field("origin")
        self.assertAlmostEqual(float(p_org[0]), 250.0)
        self.assertAlmostEqual(float(p_org[1]), 0.0)
        self.assertAlmostEqual(float(p_org[2]), 12.0)
        self.assertEqual(float(puddle.get_field("duration")), 6.0)
        self.assertEqual(int(puddle.get_field("radius")), 128)
        self.assertEqual(int(puddle.get_field("tick_damage")), 25)
        self.assertTrue(puddle.get_field("active"))

        # Looping stock FX spawned & triggered, and tracked in level.bz_elem_new_entities
        self.assertEqual(len(gsc.spawned_fx_entities), 1)
        self.assertEqual(len(gsc.triggered_fx_entities), 1)
        self.assertGreaterEqual(len(gsc.played_fx), 1)
        tracked = gsc.level.get_field("bz_elem_new_entities")
        self.assertGreaterEqual(tracked.size, 2)  # script_origin anchor + fx_ent

        # 2. In-radius zombie got 40% slow (0.60), brittle timestamp, and 25 tick dmg attributed to player
        self.assertAlmostEqual(float(z_in.get_field("bz_base_moveplaybackrate")), 1.0)
        self.assertAlmostEqual(float(z_in.get_field("moveplaybackrate")), 0.60)
        self.assertGreater(int(z_in.get_field("bz_acid_slow_until")), 5000)
        self.assertGreater(int(z_in.get_field("bz_acid_brittle_until")), 5000)
        self.assertEqual(len(z_in.damage_events), 1)
        self.assertEqual(z_in.damage_events[0]["damage"], 25)
        self.assertIs(z_in.damage_events[0]["attacker"], player)

        # Out-of-radius zombie untouched
        self.assertAlmostEqual(float(z_out.get_field("moveplaybackrate")), 1.0)
        self.assertEqual(z_out.damage_events, [])

        # 3. 50% brittle multiplies ANY subsequent damage in actor_damage by 1.50x
        bullet_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_in,
            player,
            player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "stg44",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        melee_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_in,
            player,
            player,
            150,
            0,
            "MOD_MELEE",
            "knife",
            UNDEFINED,
            UNDEFINED,
            "none",
            0,
        )
        out_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_out,
            player,
            player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "stg44",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(bullet_dmg, 150)  # 100 * 1.50
        self.assertEqual(melee_dmg, 225)   # 150 * 1.50
        self.assertEqual(out_dmg, 100)

        # 4. Structured ASCII telemetry emitted
        acid_events = [e for e in gsc.emitted_events if e.startswith("BZ_EVENT|ELEM_ACID_PUDDLE|")]
        self.assertEqual(len(acid_events), 1)
        self.assertIn("radius=128", acid_events[0])
        self.assertIn("hits=1", acid_events[0])
        self.assertTrue(all(32 <= ord(ch) <= 126 for ch in acid_events[0]))

        # 5. Expiry of slow & brittle restores moveplaybackrate cleanly and removes 1.50x bonus
        gsc.sim_time_ms = int(z_in.get_field("bz_acid_brittle_until")) + 500
        gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_recompute_zombie_move_rate", z_in)
        self.assertAlmostEqual(float(z_in.get_field("moveplaybackrate")), 1.0)
        post_expiry_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_in,
            player,
            player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "stg44",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(post_expiry_dmg, 100)

        # 6. Puddle cleanup deletes anchor & FX entities cleanly
        gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_cleanup_puddle", puddle)
        self.assertFalse(puddle.get_field("active"))
        self.assertTrue(gsc.spawned_fx_entities[0].deleted)

    def test_acid_sprayer_pap_and_double_pap_expand_radius_and_scale_tick_damage(self) -> None:
        _, gsc, player = _setup_elem_new_env(map_name="nazi_zombie_factory", pap_enabled=True)
        gsc.bullet_trace_fn = lambda s, e: {"fraction": 0.25, "position": GscArray([200.0, 0.0, 0.0])}

        # Zombie at 150 units from (200, 0, 0) -> outside base 128, inside PaP 168!
        z_ring = ElemNewFakeEntity("ZRing", ent_num=20, is_player=False, origin=(350.0, 0.0, 0.0))
        z_ring.set_field("health", 1000)
        gsc.ai_enemies.append(z_ring)

        # Base shot misses 150-unit zombie
        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_acid_sprayer")
        self.assertEqual(z_ring.damage_events, [])

        # Single PaP (scripted Tier 1 PaP) expands radius to 168 and tick damage to 45
        gsc.call(BZ_PAP_MOD, "bz_pap_apply_single_pap", player, "bz_acid_sprayer")
        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_acid_sprayer")
        self.assertEqual(len(z_ring.damage_events), 1)
        self.assertEqual(z_ring.damage_events[0]["damage"], 45)
        self.assertAlmostEqual(float(z_ring.get_field("moveplaybackrate")), 0.60)

        # Double PaP keeps 168 radius and scales tick damage to 75, setting bz_in_damage_dispatch
        # so global actor_damage / _bz_pap NEVER double-multiplies acid puddle ticks!
        gsc.call(BZ_PAP_MOD, "bz_pap_apply_double_pap", player, "bz_acid_sprayer")
        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_acid_sprayer")
        self.assertEqual(len(z_ring.damage_events), 2)
        self.assertEqual(z_ring.damage_events[1]["damage"], 75)
        self.assertTrue(z_ring.get_field("bz_in_damage_dispatch"))

        # Even if MOD_UNKNOWN reached _bz_pap directly while holding Double-PaP bz_acid_sprayer,
        # _bz_pap MUST ignore MOD_UNKNOWN and never multiply it!
        z_clean = ElemNewFakeEntity("ZClean", ent_num=21, is_player=False, origin=(900.0, 0.0, 0.0))
        z_clean.set_field("health", 1000)
        unk_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_clean,
            player,
            player,
            75,
            0,
            "MOD_UNKNOWN",
            "bz_acid_sprayer",
            UNDEFINED,
            UNDEFINED,
            "none",
            0,
        )
        self.assertEqual(unk_dmg, 75)

        # Shared helper bz_elem_new_apply_status_damage_mult composes Acid Brittle (1.5x) + Cryo Shatter (2.5x)
        # for scripted MOD_GRENADE_SPLASH (PaP Cluster) and MOD_EXPLOSIVE (Multi-Crossbow)!
        z_combo = ElemNewFakeEntity("ZCombo", ent_num=22, is_player=False, origin=(200.0, 0.0, 0.0))
        z_combo.set_field("health", 5000)
        gsc.sim_time_ms = 5000
        z_combo.set_field("bz_acid_brittle_until", 9000)
        z_combo.set_field("bz_is_frozen", True)
        z_combo.set_field("bz_cryo_frozen_until", 9000)
        scaled = gsc.call(
            BZ_ELEM_NEW_MOD,
            "bz_elem_new_apply_status_damage_mult",
            z_combo,
            1000,
            "MOD_EXPLOSIVE",
            "bz_multi_crossbow",
        )
        self.assertEqual(scaled, 3750)  # 1000 * 1.50 * 2.50
        self.assertFalse(bool(z_combo.get_field("bz_is_frozen")))

        # PaP Cluster Grenade blast triggers Cryo Shatter (2.5x) + Acid Brittle (1.5x) cleanly!
        gsc.call(BZ_PAP_MOD, "bz_pap_apply_cluster_upgrade", player)
        z_cluster = ElemNewFakeEntity("ZCluster", ent_num=23, is_player=False, origin=(200.0, 0.0, 0.0))
        z_cluster.set_field("health", 10000)
        z_cluster.set_field("bz_acid_brittle_until", 9000)
        z_cluster.set_field("bz_is_frozen", True)
        z_cluster.set_field("bz_cryo_frozen_until", 9000)
        gsc.ai_enemies.append(z_cluster)
        gsc.call(
            BZ_PAP_MOD,
            "bz_pap_apply_radial_blast",
            player,
            GscArray([200.0, 0.0, 0.0]),
            160,
            1000,
            0,
            True,
        )
        self.assertEqual(z_cluster.damage_events[0]["damage"], 3750)  # 1000 * 1.50 * 2.50
        self.assertFalse(bool(z_cluster.get_field("bz_is_frozen")))
        self.assertTrue(z_cluster.get_field("bz_in_damage_dispatch"))

    def test_acid_puddle_cap_evicts_oldest_puddle_cleanly_to_prevent_entity_spam(self) -> None:
        _, gsc, player = _setup_elem_new_env(map_name="nazi_zombie_factory")
        gsc.bullet_trace_fn = lambda s, e: {"fraction": 0.25, "position": GscArray([200.0, 0.0, 0.0])}

        max_cap = int(gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_get_max_acid_puddles"))
        self.assertGreaterEqual(max_cap, 4)
        self.assertLessEqual(max_cap, 12)

        for _ in range(max_cap + 4):
            gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_acid_sprayer")

        puddles = gsc.level.get_field("bz_acid_puddles")
        self.assertEqual(puddles.size, max_cap)

        # Oldest 4 FX entities must have been deleted on eviction, newest max_cap alive
        deleted_fx = [ent for ent in gsc.spawned_fx_entities if ent.deleted]
        alive_fx = [ent for ent in gsc.spawned_fx_entities if not ent.deleted]
        self.assertEqual(len(deleted_fx), 4)
        self.assertEqual(len(alive_fx), max_cap)


class TestCryoCannonWeapon(unittest.TestCase):
    """Seam 3: Cryo Cannon beam/cone freeze, 4.0s thaw, 2.50x shatter & PaP cone scaling."""

    def test_cryo_cannon_freezes_cone_and_beam_zombies_and_restores_on_thaw(self) -> None:
        _, gsc, player = _setup_elem_new_env(map_name="nazi_zombie_factory")
        gsc.sim_time_ms = 2000
        # Player at (0,0,0) eye (0,0,60), aiming along +X; trace hits at (360, 0, 60)
        gsc.bullet_trace_fn = lambda s, e: {"fraction": 0.35, "position": GscArray([360.0, 0.0, 60.0])}

        z_cone = ElemNewFakeEntity("ZCone", ent_num=10, is_player=False, origin=(390.0, 60.0, 0.0))
        z_beam = ElemNewFakeEntity("ZBeam", ent_num=11, is_player=False, origin=(180.0, 20.0, 0.0))
        z_behind = ElemNewFakeEntity("ZBehind", ent_num=12, is_player=False, origin=(-120.0, 0.0, 0.0))
        z_far = ElemNewFakeEntity("ZFar", ent_num=13, is_player=False, origin=(360.0, 140.0, 0.0))
        for z in (z_cone, z_beam, z_behind, z_far):
            z.set_field("health", 800)
            z.set_field("moveplaybackrate", 1.0)
        gsc.ai_enemies.extend([z_cone, z_beam, z_behind, z_far])

        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_cryo_cannon")

        # Cone & beam zombies frozen for 4.0s (2000 + 4000 = 6000)
        for z in (z_cone, z_beam):
            self.assertTrue(z.get_field("bz_is_frozen"))
            self.assertEqual(int(z.get_field("bz_cryo_frozen_until")), 6000)
            self.assertAlmostEqual(float(z.get_field("bz_base_moveplaybackrate")), 1.0)
            self.assertAlmostEqual(float(z.get_field("moveplaybackrate")), 0.01)

        # Behind & outside-110-cone zombies remain unfrozen
        for z in (z_behind, z_far):
            self.assertFalse(bool(z.get_field("bz_is_frozen")))
            self.assertAlmostEqual(float(z.get_field("moveplaybackrate")), 1.0)

        # Icy stock FX played (Der Riese prefers zombie_mainframe_steam)
        fx_handles = [fx for fx, _pos in gsc.played_fx]
        self.assertIn("dr_fx:zombie_mainframe_steam", fx_handles)

        # Structured ASCII telemetry emitted
        cryo_events = [e for e in gsc.emitted_events if e.startswith("BZ_EVENT|ELEM_CRYO_FREEZE|")]
        self.assertEqual(len(cryo_events), 1)
        self.assertIn("radius=110", cryo_events[0])
        self.assertIn("frozen=2", cryo_events[0])
        self.assertTrue(all(32 <= ord(ch) <= 126 for ch in cryo_events[0]))

        # Thaw after 4.0s restores moveplaybackrate cleanly to 1.0
        gsc.sim_time_ms = 6000
        gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_thaw_zombie", z_cone)
        self.assertFalse(bool(z_cone.get_field("bz_is_frozen")))
        self.assertAlmostEqual(float(z_cone.get_field("moveplaybackrate")), 1.0)

    def test_cryo_shatter_applies_2_5x_on_bullet_melee_explosive_and_ignores_self_freeze(self) -> None:
        _, gsc, player = _setup_elem_new_env(map_name="nazi_zombie_factory")
        gsc.sim_time_ms = 3000
        gsc.bullet_trace_fn = lambda s, e: {"fraction": 0.25, "position": GscArray([200.0, 0.0, 60.0])}

        z_bullet = ElemNewFakeEntity("ZBullet", ent_num=10, is_player=False, origin=(200.0, 10.0, 0.0))
        z_melee = ElemNewFakeEntity("ZMelee", ent_num=11, is_player=False, origin=(210.0, -10.0, 0.0))
        z_expl = ElemNewFakeEntity("ZExpl", ent_num=12, is_player=False, origin=(190.0, 15.0, 0.0))
        for z in (z_bullet, z_melee, z_expl):
            z.set_field("health", 1000)
        gsc.ai_enemies.extend([z_bullet, z_melee, z_expl])

        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_cryo_cannon")

        # Self-freeze hit from bz_cryo_cannon MUST NOT shatter or multiply damage
        self_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_bullet,
            player,
            player,
            100,
            0,
            "MOD_PROJECTILE",
            "bz_cryo_cannon",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(self_dmg, 100)
        self.assertTrue(z_bullet.get_field("bz_is_frozen"))

        # Burn DOT / unknown MOD does NOT shatter
        burn_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_bullet,
            player,
            player,
            100,
            0,
            "MOD_BURNED",
            "m2_flamethrower_zombie",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(burn_dmg, 100)
        self.assertTrue(z_bullet.get_field("bz_is_frozen"))

        # Bullet, melee, and explosive hits each shatter for 2.50x and clear freeze!
        gsc.played_fx.clear()
        b_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_bullet,
            player,
            player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "stg44",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        m_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_melee,
            player,
            player,
            150,
            0,
            "MOD_MELEE",
            "knife",
            UNDEFINED,
            UNDEFINED,
            "none",
            0,
        )
        e_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_expl,
            player,
            player,
            200,
            0,
            "MOD_GRENADE_SPLASH",
            "stielhandgranate",
            UNDEFINED,
            UNDEFINED,
            "none",
            0,
        )
        self.assertEqual(b_dmg, 250)  # 100 * 2.50
        self.assertEqual(m_dmg, 375)  # 150 * 2.50
        self.assertEqual(e_dmg, 500)  # 200 * 2.50

        for z in (z_bullet, z_melee, z_expl):
            self.assertFalse(bool(z.get_field("bz_is_frozen")))
            # Active Flamethrower burn DOT from the MOD_BURNED check keeps 0.80 until burn ends
            self.assertAlmostEqual(float(z.get_field("moveplaybackrate")), 0.8)
            z.set_field("bz_flame_dot_active", False)
            gsc.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", z)
            self.assertAlmostEqual(float(z.get_field("moveplaybackrate")), 1.0)

        # Follow-up hit after shatter does NOT get shatter multiplier again
        follow_up = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_bullet,
            player,
            player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "stg44",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(follow_up, 100)

        # Shatter burst FX and BZ_EVENT|ELEM_CRYO_SHATTER telemetry emitted
        shatter_fx = [fx for fx, _pos in gsc.played_fx]
        self.assertEqual(shatter_fx.count("dr_fx:tesla_shock_secondary"), 3)
        shatter_events = [
            e for e in gsc.emitted_events if e.startswith("BZ_EVENT|ELEM_CRYO_SHATTER|")
        ]
        self.assertEqual(len(shatter_events), 3)
        self.assertIn("mult=2.5", shatter_events[0])
        self.assertTrue(all(32 <= ord(ch) <= 126 for ch in shatter_events[0]))

    def test_cryo_cannon_pap_and_double_pap_expand_cone_radius_from_110_to_150(self) -> None:
        _, gsc, player = _setup_elem_new_env(map_name="nazi_zombie_prototype", pap_enabled=True)
        gsc.sim_time_ms = 4000
        gsc.bullet_trace_fn = lambda s, e: {"fraction": 0.25, "position": GscArray([300.0, 0.0, 0.0])}

        # Zombie at 135 units from impact -> outside base 110, inside PaP 150
        z_outer = ElemNewFakeEntity("ZOuter", ent_num=30, is_player=False, origin=(300.0, 135.0, 0.0))
        z_outer.set_field("health", 800)
        gsc.ai_enemies.append(z_outer)

        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_cryo_cannon")
        self.assertFalse(bool(z_outer.get_field("bz_is_frozen")))

        # Single PaP expands cone radius to 150 and freezes outer zombie!
        gsc.call(BZ_PAP_MOD, "bz_pap_apply_single_pap", player, "bz_cryo_cannon")
        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_cryo_cannon")
        self.assertTrue(z_outer.get_field("bz_is_frozen"))
        self.assertAlmostEqual(float(z_outer.get_field("moveplaybackrate")), 0.01)


class TestElemNewCompositionCleanupAndCompliance(unittest.TestCase):
    """Seam 4 & 5: Acid+Cryo move rate composition, Phase 1/2 damage stacking, end_game & WaW 1.7."""

    def test_acid_slow_and_cryo_freeze_never_corrupt_saved_base_move_rate_in_any_order(
        self,
    ) -> None:
        _, gsc, player = _setup_elem_new_env(map_name="nazi_zombie_factory")
        gsc.bullet_trace_fn = lambda s, e: {"fraction": 0.25, "position": GscArray([200.0, 0.0, 0.0])}

        # Order A: Acid slow first -> Cryo freeze -> thaw while Acid still active -> Acid expires
        gsc.sim_time_ms = 1000
        z_a = ElemNewFakeEntity("ZA", ent_num=40, is_player=False, origin=(200.0, 0.0, 0.0))
        z_a.set_field("health", 2000)
        z_a.set_field("moveplaybackrate", 1.0)
        gsc.ai_enemies.append(z_a)

        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_acid_sprayer")
        self.assertAlmostEqual(float(z_a.get_field("bz_base_moveplaybackrate")), 1.0)
        self.assertAlmostEqual(float(z_a.get_field("moveplaybackrate")), 0.60)

        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_cryo_cannon")
        self.assertAlmostEqual(float(z_a.get_field("bz_base_moveplaybackrate")), 1.0)
        self.assertAlmostEqual(float(z_a.get_field("moveplaybackrate")), 0.01)

        # Refresh acid puddle at t=4500 so acid slow outlives cryo freeze (cryo ends at 5000)
        puddles = gsc.level.get_field("bz_acid_puddles")
        gsc.sim_time_ms = 4500
        gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_tick_acid_puddle", puddles[0])
        self.assertAlmostEqual(float(z_a.get_field("moveplaybackrate")), 0.01)

        # At t=5000 cryo thaws while acid slow is active (until 6000) -> MUST restore 0.60, not 1.0!
        gsc.sim_time_ms = 5000
        gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_thaw_zombie", z_a)
        self.assertFalse(bool(z_a.get_field("bz_is_frozen")))
        self.assertAlmostEqual(float(z_a.get_field("moveplaybackrate")), 0.60)

        # At t=6100 acid slow expires -> MUST restore original base 1.0
        gsc.sim_time_ms = 6100
        gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_recompute_zombie_move_rate", z_a)
        self.assertAlmostEqual(float(z_a.get_field("moveplaybackrate")), 1.0)

        # Order B: Cryo first on fast sprinter (base=1.25) -> Acid expires during Cryo -> Thaw restores 1.25
        gsc.ai_enemies.clear()
        gsc.sim_time_ms = 10000
        z_b = ElemNewFakeEntity("ZB", ent_num=41, is_player=False, origin=(200.0, 0.0, 0.0))
        z_b.set_field("health", 2000)
        z_b.set_field("moveplaybackrate", 1.25)
        gsc.ai_enemies.append(z_b)

        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_cryo_cannon")
        self.assertAlmostEqual(float(z_b.get_field("bz_base_moveplaybackrate")), 1.25)
        self.assertAlmostEqual(float(z_b.get_field("moveplaybackrate")), 0.01)

        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_acid_sprayer")
        self.assertAlmostEqual(float(z_b.get_field("bz_base_moveplaybackrate")), 1.25)
        self.assertAlmostEqual(float(z_b.get_field("moveplaybackrate")), 0.01)

        # Acid expires at t=12000 while Cryo still active (until 14000) -> stays 0.01
        gsc.sim_time_ms = 12000
        gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_recompute_zombie_move_rate", z_b)
        self.assertAlmostEqual(float(z_b.get_field("moveplaybackrate")), 0.01)

        # Cryo thaws at t=14000 -> cleanly restores custom base 1.25!
        gsc.sim_time_ms = 14000
        gsc.call(BZ_ELEM_NEW_MOD, "bz_elem_new_thaw_zombie", z_b)
        self.assertAlmostEqual(float(z_b.get_field("moveplaybackrate")), 1.25)

    def test_acid_brittle_and_cryo_shatter_compose_with_perks_classes_double_pap_and_mule_kick(
        self,
    ) -> None:
        _, gsc, player = _setup_elem_new_env(
            map_name="nazi_zombie_factory",
            bz_enabled=True,
            elements_enabled=True,
            pap_enabled=True,
            perks_enabled=True,
            classes_enabled=True,
        )
        gsc.sim_time_ms = 5000
        gsc.bullet_trace_fn = lambda s, e: {"fraction": 0.25, "position": GscArray([200.0, 0.0, 0.0])}

        # Grant Mule Kick I + II (4 primary slots) carrying both elemental primaries + 2 stock guns
        gsc.call(BZ_STATE_MOD, "bz_try_buy_perk", player, "mule_kick")
        gsc.call(BZ_STATE_MOD, "bz_try_buy_perk_t2", player, "mule_kick")
        self.assertEqual(gsc.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", player), 4)
        player.give_weapon("bz_acid_sprayer")
        player.give_weapon("bz_cryo_cannon")
        player.give_weapon("thompson")
        player.give_weapon("stg44_upgraded", make_current=True)

        # Grant AP II (1.60), Double Tap II (1.25), Titan stationary (2.0), Double PaP (1.75)
        gsc.call(BZ_STATE_MOD, "bz_try_buy_perk", player, "ap")
        gsc.call(BZ_STATE_MOD, "bz_try_buy_perk_t2", player, "ap")
        gsc.call(BZ_STATE_MOD, "bz_try_buy_perk", player, "double_tap")
        gsc.call(BZ_STATE_MOD, "bz_try_buy_perk_t2", player, "double_tap")
        gsc.call(BZ_STATE_MOD, "bz_try_buy_class", player, "titan")
        player.set_field("bz_titan_is_stationary", True)
        gsc.call(BZ_PAP_MOD, "bz_pap_apply_double_pap", player, "stg44_upgraded")

        # Register a zombie and apply BOTH Acid Brittle (1.50x) and Cryo Freeze (2.50x shatter)
        z = ElemNewFakeEntity("ZBoss", ent_num=50, is_player=False, origin=(200.0, 0.0, 0.0))
        z.set_field("health", 10000)
        gsc.ai_enemies.append(z)

        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_acid_sprayer")
        gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_cryo_cannon")

        # Full stack: 100 * 1.60 (AP II) * 1.25 (DT II) * 2.0 (Titan) * 1.75 (Double PaP) * 1.50 (Brittle) * 2.50 (Shatter)
        # = 100 * 2.0 * 2.0 * 1.75 * 1.50 * 2.50 = 2625
        composed_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z,
            player,
            player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "stg44_upgraded",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(composed_dmg, 2625)

        # Assassin 5.0x headshot + Acid Brittle 1.50x (after shatter cleared freeze) = 100 * 1.6 * 1.25 * 5.0 * 1.75 * 1.50 = 2625
        gsc.call(BZ_STATE_MOD, "bz_try_buy_class", player, "assassin")
        assassin_brittle_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z,
            player,
            player,
            100,
            0,
            "MOD_HEAD_SHOT",
            "stg44_upgraded",
            UNDEFINED,
            UNDEFINED,
            "head",
            0,
        )
        self.assertEqual(assassin_brittle_dmg, 2625)

    def test_end_game_deletes_all_tracked_puddle_and_fx_entities_with_zero_leaks(self) -> None:
        _, gsc, player = _setup_elem_new_env(map_name="nazi_zombie_factory")
        gsc.bullet_trace_fn = lambda s, e: {"fraction": 0.25, "position": GscArray([200.0, 0.0, 0.0])}

        for _ in range(3):
            gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", player, "bz_acid_sprayer")

        tracked_before = gsc.level.get_field("bz_elem_new_entities")
        self.assertEqual(tracked_before.size, 6)  # 3 script_origin anchors + 3 SpawnFx entities
        saved_entities = [tracked_before[i] for i in range(tracked_before.size)]

        gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")

        self.assertEqual(gsc.level.get_field("bz_acid_puddles").size, 0)
        self.assertEqual(gsc.level.get_field("bz_elem_new_entities").size, 0)
        for ent in saved_entities:
            self.assertTrue(ent.deleted, f"Leaked entity after end_game: {ent!r}")

    def test_bz_elem_new_gsc_is_strictly_waw17_compliant(self) -> None:
        source = BZ_ELEM_NEW_PATH.read_text(encoding="latin1")
        tokenize(source, filename=str(BZ_ELEM_NEW_PATH))
        code_only = "\n".join(line.split("//", 1)[0] for line in source.splitlines())

        # Zero foreach and zero VectorScale (neither exists in vanilla WaW 1.7)
        self.assertIsNone(re.search(r"\bforeach\b", code_only), "Forbidden foreach in _bz_elem_new.gsc")
        self.assertIsNone(
            re.search(r"\bvectorscale\b", code_only, re.IGNORECASE),
            "Forbidden VectorScale() in _bz_elem_new.gsc (not a WaW 1.7 builtin)",
        )

        # Strictly printable ASCII across the entire script
        non_ascii = [ch for ch in source if ord(ch) > 126 or (ord(ch) < 32 and ch not in "\t\r\n")]
        self.assertEqual(non_ascii, [], f"Non-ASCII characters in _bz_elem_new.gsc: {non_ascii!r}")

        # Zero endon() in any synchronous function; only dedicated child threads may call endon()
        gsc = ElemNewGscRuntime(MOD_ROOT, FakeDvarStore())
        mod = gsc.load_module(BZ_ELEM_NEW_MOD)
        allowed_threaded_funcs = {
            "bz_elem_new_acid_puddle_think",
            "bz_elem_new_watch_acid_slow_expiry",
            "bz_elem_new_watch_cryo_thaw",
        }
        for fn_name, fn_def in mod.items():
            if fn_name in allowed_threaded_funcs:
                self.assertTrue(
                    _ast_contains_method_call(fn_def.body, "endon"),
                    f"Child thread {fn_name}() should guard with endon()",
                )
            else:
                self.assertFalse(
                    _ast_contains_method_call(fn_def.body, "endon"),
                    f"Forbidden endon() inside synchronous function {fn_name}()",
                )


if __name__ == "__main__":
    unittest.main()
