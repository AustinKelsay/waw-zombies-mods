"""Offline TDD contract tests for P1-T3 (#14): Physical In-World Stations & Clickable .menu Shop Popups.

Tests observable behavior across the three core seams:
  1. 4-map Station coordinate registry, floor-snap, Classic/Feature-Gate spawn isolation & cleanup.
  2. Per-player UI dvar sync, Co-op isolation, server-side scriptMenuResponse validation, and
     the shared `"item_purchased"` hook dispatch for Chunk 3 modules (T4/T5/T6).
  3. Clickable WaW 1.7 `.menu` popup syntax, ASCII/brace validation, mod.csv/patch_menus.txt
     registration, zero FX/model bloat, and WaW 1.7 GSC compliance.
"""

from __future__ import annotations

import math
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
    GscStruct,
    UNDEFINED,
    tokenize,
)
from tests.test_bz_hooks_and_build import (  # noqa: E402
    BZ_HOOKS_MOD,
    BzGscRuntime,
    FakeEntity,
    _ast_contains_method_call,
)

BZ_STATIONS_MOD = "maps\\_bz_stations"
BZ_STATIONS_PATH = MOD_ROOT / "maps" / "_bz_stations.gsc"
BZ_HOOKS_PATH = MOD_ROOT / "maps" / "_bz_hooks.gsc"

STOCK_MAPS = (
    "nazi_zombie_factory",
    "nazi_zombie_prototype",
    "nazi_zombie_asylum",
    "nazi_zombie_sumpf",
)
EXPECTED_STATION_IDS = ("perks", "class", "arsenal", "pap")
EXPECTED_FACTORY_STATION_IDS = ("perks", "class", "arsenal")
EXPECTED_STATION_IDS_BY_MAP = {
    "nazi_zombie_factory": EXPECTED_FACTORY_STATION_IDS,
    "nazi_zombie_asylum": EXPECTED_STATION_IDS * 2,
}
VERRUCKT_STATION_PLACEMENTS = (
    ((920, 370, 96), (0, 0, 0)),
    ((920, 180, 96), (0, 0, 0)),
    ((985, 295, 96), (0, 0, 0)),
    ((1060, 180, 96), (0, 180, 0)),
    ((940, -15, 96), (0, 0, 0)),
    ((940, -155, 96), (0, 0, 0)),
    ((940, -300, 96), (0, 0, 0)),
    ((1090, -365, 96), (0, 90, 0)),
)
EXPECTED_MENUS = (
    "bz_station_perks",
    "bz_station_class",
    "bz_station_arsenal",
    "bz_station_pap",
)


def _vec_dist(a: GscArray, b: GscArray) -> float:
    dx = float(a[0]) - float(b[0])
    dy = float(a[1]) - float(b[1])
    dz = float(a[2]) - float(b[2])
    return math.sqrt(dx * dx + dy * dy + dz * dz)


class StationHudRuntime(BzGscRuntime):
    """Record client HUD allocation and destruction while executing the station GSC."""

    def __init__(self, mod_root: Path, dvars: FakeDvarStore) -> None:
        super().__init__(mod_root, dvars)
        self.hud_elems: list[GscStruct] = []
        self.destroyed_huds: list[GscStruct] = []
        self.waits: list[tuple[Any, str]] = []

    def _call_builtin(self, name_lower: str, args: list[Any], line: int) -> tuple[bool, Any]:
        handled, result = super()._call_builtin(name_lower, args, line)
        if name_lower == "newclienthudelem":
            self.hud_elems.append(result)
        return handled, result

    def _exec_method(self, receiver: Any, method: str, args: list[Any], line: int) -> Any:
        if method == "destroy" and receiver in self.hud_elems:
            self.destroyed_huds.append(receiver)
        if method == "waittill":
            self.waits.append((receiver, args[0]))
        return super()._exec_method(receiver, method, args, line)


class TestBzStationCoordinatesAndSpawning(unittest.TestCase):
    """Slice 1: 4-map coordinate coverage, floor-snap, Classic/Feature-Gate isolation & cleanup."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = StationHudRuntime(MOD_ROOT, self.dvars)
        self.player = FakeEntity("HostPlayer", ent_num=0)
        self.gsc.players.append(self.player)

    def _enable_all_phase1(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")
        self.dvars.set("bz_elements_enabled", "0")
        self.dvars.set("bz_companions_enabled", "0")

    def test_all_four_stock_maps_have_distinct_non_overlapping_ascii_station_specs(self) -> None:
        for map_name in STOCK_MAPS:
            specs = self.gsc.call(BZ_STATIONS_MOD, "bz_stations_get_map_specs", map_name)
            expected_ids = EXPECTED_STATION_IDS_BY_MAP.get(map_name, EXPECTED_STATION_IDS)
            self.assertEqual(
                specs.size,
                len(expected_ids),
                f"{map_name} should define {len(expected_ids)} stations",
            )

            seen_ids: list[str] = []
            origins: list[tuple[str, GscArray]] = []
            by_id: dict[str, GscStruct] = {}
            for i in range(specs.size):
                spec = specs[i]
                sid = spec.get_field("id")
                seen_ids.append(sid)
                by_id[sid] = spec
                self.assertFalse(spec.get_field("is_fallback"), f"{map_name}/{sid} should be curated")

                hint = spec.get_field("hint_string")
                display = spec.get_field("display_name")
                self.assertTrue(len(hint) > 0 and "&&1" in hint, f"{map_name}/{sid} missing &&1 prompt")
                self.assertTrue(all(32 <= ord(ch) <= 126 for ch in hint), f"Non-ASCII hint on {map_name}/{sid}")
                self.assertTrue(all(32 <= ord(ch) <= 126 for ch in display), f"Non-ASCII name on {map_name}/{sid}")

                origin = spec.get_field("origin")
                self.assertEqual(origin.size, 3, f"{map_name}/{sid} origin must be 3D vector")
                origins.append((sid, origin))

                if sid == "pap":
                    self.assertFalse(spec.get_field("paired_with_native_pap"))

            self.assertEqual(tuple(seen_ids), expected_ids, f"Station IDs mismatch on {map_name}")

            # Keep at least 85u between station anchors so their interact points stay distinct.
            for i in range(len(origins)):
                for j in range(i + 1, len(origins)):
                    sid_a, pos_a = origins[i]
                    sid_b, pos_b = origins[j]
                    dist = _vec_dist(pos_a, pos_b)
                    self.assertGreaterEqual(
                        dist,
                        85.0,
                        f"{map_name}: stations {sid_a} and {sid_b} too close ({dist:.1f} units)",
                    )

            # Verify BSP-verified non-blocking station placement polish (POL-T4 #40)
            if map_name == "nazi_zombie_factory":
                self.assertEqual(tuple(by_id["perks"].get_field("origin")[i] for i in range(3)), (-310, -240, 20))
                self.assertEqual(tuple(by_id["perks"].get_field("angles")[i] for i in range(3)), (0, 0, 0))
                self.assertEqual(tuple(by_id["class"].get_field("origin")[i] for i in range(3)), (230, -200, 20))
                self.assertEqual(tuple(by_id["class"].get_field("angles")[i] for i in range(3)), (0, 180, 0))
                self.assertEqual(tuple(by_id["arsenal"].get_field("origin")[i] for i in range(3)), (180, 120, 20))
                self.assertEqual(tuple(by_id["arsenal"].get_field("angles")[i] for i in range(3)), (0, 225, 0))
                self.assertNotIn("pap", by_id)
            elif map_name == "nazi_zombie_sumpf":
                # Shi No Numa arsenal placed along open north upstairs floor line between perks and class
                self.assertEqual(tuple(by_id["arsenal"].get_field("origin")[i] for i in range(3)), (10150, 610, -492))
                self.assertEqual(tuple(by_id["perks"].get_field("origin")[i] for i in range(3)), (10020, 610, -492))
                self.assertEqual(tuple(by_id["class"].get_field("origin")[i] for i in range(3)), (10280, 610, -492))
                self.assertEqual(tuple(by_id["pap"].get_field("origin")[i] for i in range(3)), (10280, 410, -492))

    def test_verruckt_arsenal_trigger_clears_all_four_north_spawns(self) -> None:
        specs = self.gsc.call(BZ_STATIONS_MOD, "bz_stations_get_map_specs", "nazi_zombie_asylum")
        arsenal = next(spec for spec in specs.to_list() if spec.get_field("id") == "arsenal")
        origin = arsenal.get_field("origin")
        self.assertEqual(tuple(origin.to_list()), (985, 295, 96))
        self.assertEqual(tuple(arsenal.get_field("angles").to_list()), (0, 0, 0))

        # initial_spawn_points with script_noteworthy=north_spawn in nazi_zombie_asylum.ff.
        north_spawns = ((1097, 302, 91), (1098, 237, 91), (1076.5, 394.5, 97), (1137.5, 121.5, 88))
        for x, y, z in north_spawns:
            with self.subTest(spawn=(x, y, z)):
                self.assertGreaterEqual(math.hypot(origin[0] - x, origin[1] - y), 65.0)

    def test_unrecognized_map_uses_safe_spawn_offset_fallback_and_floor_snap(self) -> None:
        spawn_ent = FakeEntity("info_player_start", ent_num=50, is_player=False)
        spawn_ent.set_field("origin", GscArray([500, -300, 100]))
        self.gsc.world_entities[("classname", "info_player_start")] = [spawn_ent]

        specs = self.gsc.call(BZ_STATIONS_MOD, "bz_stations_get_map_specs", "nazi_zombie_custom_map")
        self.assertEqual(specs.size, 4)
        for i in range(specs.size):
            spec = specs[i]
            self.assertTrue(spec.get_field("is_fallback"))
            origin = spec.get_field("origin")
            self.assertGreaterEqual(_vec_dist(origin, GscArray([500, -300, 100])), 100.0)

        # Verify floor-snap honors BulletTrace hit Z
        self.gsc.bullet_trace_fn = lambda start, _end: {
            "fraction": 0.4,
            "position": GscArray([start[0], start[1], 72]),
        }
        snapped = self.gsc.call(BZ_STATIONS_MOD, "bz_stations_snap_to_floor", GscArray([10, 20, 95]))
        self.assertEqual(snapped[0], 10)
        self.assertEqual(snapped[1], 20)
        self.assertEqual(snapped[2], 72)

    def test_classic_mode_spawns_zero_stations_and_precaches_zero_menus(self) -> None:
        self.dvars.set("bz_enabled", "0")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")

        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

        self.player.set_field("origin", GscArray([-310, -240, 20]))
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_spawned", self.player)
        self.gsc.call(BZ_STATIONS_MOD, "bz_stations_update_prompt_hud", self.player)

        self.assertEqual(self.gsc.precached_menus, [])
        self.assertEqual(self.gsc.spawned_entities, [])
        self.assertEqual(self.gsc.hud_elems, [])
        self.assertFalse(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.player, "bz_station_perks", "buy_perk:staminup")
        )
        self.assertEqual(self.gsc.emitted_events, [])
        self.assertFalse(self.gsc.call(BZ_STATIONS_MOD, "bz_stations_open_for_player", self.player, "perks"))
        self.assertFalse(
            self.gsc.call(BZ_STATIONS_MOD, "bz_stations_on_menu_response", self.player, "bz_station_perks", "close")
        )
        self.gsc.call(BZ_STATIONS_MOD, "bz_stations_play_sound", self.player, "lid_open")
        self.assertEqual(self.gsc.played_local_sounds, [])

    def test_auto_registration_precaches_menus_spawns_expected_stations_and_cleans_up_on_end_game(self) -> None:
        self._enable_all_phase1()
        self.gsc.level.set_field("script", "nazi_zombie_factory")

        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        # Keep bz_station_pap precached across all maps for non-Factory compatibility
        self.assertEqual(tuple(self.gsc.precached_menus), EXPECTED_MENUS)

        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        stations = self.gsc.level.get_field("bz_stations")
        for sid in EXPECTED_FACTORY_STATION_IDS:
            self.assertIsNot(stations[sid], UNDEFINED, f"Station {sid} did not spawn on Der Riese")
        self.assertIs(stations["pap"], UNDEFINED, "Der Riese must NOT spawn duplicate standalone PaP station")

        # Der Riese: 3 stations x (script_origin + trigger_radius + visible script_model) = 9 entities, zero FX
        self.assertEqual(len(self.gsc.spawned_entities), 9)
        triggers = [e for e in self.gsc.spawned_entities if e.classname == "trigger_radius"]
        models = [e for e in self.gsc.spawned_entities if e.classname == "script_model"]
        self.assertEqual(len(triggers), 3)
        self.assertEqual(len(models), 3)
        for mdl in models:
            self.assertTrue(bool(mdl.get_field("model")))
        for trig in triggers:
            self.assertEqual(trig.cursor_hint, "HINT_NOICON")
            self.assertIn("&&1", trig.hint_string)

        spawn_events = [e for e in self.gsc.emitted_events if e.startswith("BZ_EVENT|STATION_SPAWN|")]
        self.assertEqual(len(spawn_events), 3)

        # End game cleans up all spawned station entities cleanly
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.assertTrue(all(e.deleted for e in self.gsc.spawned_entities))

        # Non-Factory maps still spawn standalone PaP in each starting area.
        for non_factory in ("nazi_zombie_prototype", "nazi_zombie_asylum", "nazi_zombie_sumpf"):
            dvars2 = FakeDvarStore()
            gsc2 = BzGscRuntime(MOD_ROOT, dvars2)
            dvars2.set("bz_enabled", "1")
            dvars2.set("bz_perks_enabled", "1")
            dvars2.set("bz_classes_enabled", "1")
            dvars2.set("bz_pap_enabled", "1")
            gsc2.level.set_field("script", non_factory)

            gsc2.call(BZ_HOOKS_MOD, "bz_pre_init")
            gsc2.call(BZ_HOOKS_MOD, "bz_init")
            stations2 = gsc2.level.get_field("bz_stations")
            for sid in EXPECTED_STATION_IDS:
                self.assertIsNot(stations2[sid], UNDEFINED, f"Station {sid} did not spawn on {non_factory}")
            expected_ids = EXPECTED_STATION_IDS_BY_MAP.get(non_factory, EXPECTED_STATION_IDS)
            self.assertEqual(len(gsc2.spawned_entities), len(expected_ids) * 3, non_factory)

    def test_verruckt_spawns_eight_stations_preserves_north_primaries_and_cleans_up(self) -> None:
        self._enable_all_phase1()
        self.gsc.level.set_field("script", "nazi_zombie_asylum")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        primaries = self.gsc.level.get_field("bz_stations")
        instances = self.gsc.level.get_field("bz_station_list").to_list()
        self.assertEqual(tuple(st.get_field("id") for st in instances), EXPECTED_STATION_IDS * 2)
        for i, (station, (origin, angles)) in enumerate(zip(instances, VERRUCKT_STATION_PLACEMENTS)):
            with self.subTest(station=i):
                self.assertEqual(tuple(station.get_field("origin").to_list()), origin)
                self.assertEqual(tuple(station.get_field("angles").to_list()), angles)
                self.assertIs(primaries[station.get_field("id")], instances[i % 4])

        south_origins = [station.get_field("origin") for station in instances[4:]]
        for i, origin in enumerate(south_origins):
            for other in south_origins[i + 1:]:
                self.assertGreaterEqual(_vec_dist(origin, other), 128.0)

        tracked = self.gsc.level.get_field("bz_station_entities").to_list()
        expected = [st.get_field(part) for st in instances for part in ("anchor", "trigger", "model")]
        self.assertEqual(tracked, expected)
        self.assertEqual(len({id(ent) for ent in tracked}), 24)
        self.assertTrue(all(not ent.deleted for ent in tracked))
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.assertTrue(all(ent.deleted for ent in tracked))
        for field in ("bz_station_entities", "bz_stations", "bz_station_list"):
            self.assertEqual(self.gsc.level.get_field(field).size, 0)

    def test_spawned_station_models_are_non_solid_with_zero_contents_across_all_maps(self) -> None:
        for map_name in STOCK_MAPS:
            dvars = FakeDvarStore()
            gsc = BzGscRuntime(MOD_ROOT, dvars)
            dvars.set("bz_enabled", "1")
            dvars.set("bz_perks_enabled", "1")
            dvars.set("bz_classes_enabled", "1")
            dvars.set("bz_pap_enabled", "1")
            gsc.level.set_field("script", map_name)

            gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
            gsc.call(BZ_HOOKS_MOD, "bz_init")

            models = [e for e in gsc.spawned_entities if e.classname == "script_model"]
            expected_count = len(EXPECTED_STATION_IDS_BY_MAP.get(map_name, EXPECTED_STATION_IDS))
            self.assertEqual(
                len(models),
                expected_count,
                f"Expected {expected_count} station script_models on {map_name}",
            )
            models_by_station = {mdl.get_field("bz_station_id"): mdl.get_field("model") for mdl in models}
            if map_name == "nazi_zombie_prototype":
                self.assertEqual(models_by_station["perks"], "static_berlin_ger_radio")
                self.assertEqual(models_by_station["class"], "dest_peleliu_generator_mobile_dmg0")
                self.assertEqual(models_by_station["arsenal"], "german_grenade_bag")
                self.assertEqual(models_by_station["pap"], "global_explosive_barrel_japanese")
            else:
                self.assertEqual(models_by_station["arsenal"], "zombie_treasure_box")
                if map_name == "nazi_zombie_factory":
                    self.assertEqual(models_by_station["class"], "zombie_vending_revive_on")

            for mdl in models:
                self.assertEqual(
                    mdl.__dict__.get("contents"),
                    0,
                    f"Station model {mdl.get_field('model')} on {map_name} must call SetContents(0)",
                )
                self.assertTrue(
                    mdl.not_solid,
                    f"Station model {mdl.get_field('model')} on {map_name} must call NotSolid()",
                )

    def test_feature_gate_isolation_skips_disabled_stations(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "0")
        self.dvars.set("bz_pap_enabled", "0")
        self.dvars.set("bz_elements_enabled", "0")
        self.dvars.set("bz_companions_enabled", "0")

        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

        stations = self.gsc.level.get_field("bz_stations")
        self.assertIsNot(stations["perks"], UNDEFINED)
        self.assertIs(stations["class"], UNDEFINED)
        self.assertIs(stations["arsenal"], UNDEFINED)
        self.assertIs(stations["pap"], UNDEFINED)
        self.assertEqual(len(self.gsc.spawned_entities), 3)

        # Arsenal opens if reserved elements or companions gate is enabled even with pap=0
        dvars2 = FakeDvarStore()
        gsc2 = BzGscRuntime(MOD_ROOT, dvars2)
        dvars2.set("bz_enabled", "1")
        dvars2.set("bz_perks_enabled", "0")
        dvars2.set("bz_classes_enabled", "0")
        dvars2.set("bz_pap_enabled", "0")
        dvars2.set("bz_elements_enabled", "1")
        gsc2.call(BZ_HOOKS_MOD, "bz_init")
        stations2 = gsc2.level.get_field("bz_stations")
        self.assertIsNot(stations2["arsenal"], UNDEFINED)
        self.assertIs(stations2["pap"], UNDEFINED)


class TestBzStationProximityPrompt(unittest.TestCase):
    def setUp(self) -> None:
        dvars = FakeDvarStore()
        for gate in ("bz_enabled", "bz_perks_enabled", "bz_classes_enabled", "bz_pap_enabled"):
            dvars.set(gate, "1")

        self.gsc = StationHudRuntime(MOD_ROOT, dvars)
        self.gsc.level.set_field("script", "nazi_zombie_prototype")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        self.player = FakeEntity("HostPlayer", ent_num=0)
        self.gsc.players.append(self.player)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_spawned", self.player)

    def update_at(self, origin: tuple[int, int, int]) -> None:
        self.player.set_field("origin", GscArray(list(origin)))
        self.gsc.call(BZ_STATIONS_MOD, "bz_stations_update_prompt_hud", self.player)

    def test_moving_between_stations_updates_text_and_color_on_one_client_hud(self) -> None:
        cases = (
            ((-140, 460, 24), "[PERKS] Specialty Perk Station - Press [F]", (1.0, 0.35, 0.35)),
            ((-140, 320, 24), "[CLASS] Class Altar - Press [F]", (0.35, 0.85, 1.0)),
            ((150, 460, 24), "[ARSENAL] Arsenal & Squad Station - Press [F]", (0.45, 1.0, 0.55)),
            ((150, 320, 24), "[PAP] Pack-a-Punch Station - Press [F]", (1.0, 0.85, 0.30)),
        )
        self.assertEqual(self.gsc.hud_elems, [])
        for origin, label, color in cases:
            with self.subTest(label=label):
                self.update_at(origin)
                hud = self.player.get_field("bz_station_prompt_hud")
                self.assertEqual(self.gsc.hud_elems, [hud])
                self.assertIs(hud.get_field("owner"), self.player)
                self.assertEqual(hud.get_field("text"), label)
                self.assertEqual(tuple(hud.get_field("color").to_list()), color)
                self.assertEqual(hud.get_field("alpha"), 1)

    def test_prompt_uses_nearest_station_within_64_unit_trigger_cylinder(self) -> None:
        self.update_at((-235, 460, 24))  # 95u horizontally (outside 64u trigger)
        self.assertEqual(self.gsc.hud_elems, [])
        self.update_at((-205, 460, 24))  # 65u horizontally (outside 64u trigger)
        self.assertEqual(self.gsc.hud_elems, [])
        self.update_at((-204, 460, 24))  # 64u horizontally (on trigger boundary)
        hud = self.player.get_field("bz_station_prompt_hud")
        self.assertEqual(hud.get_field("alpha"), 1)
        self.assertIn("[PERKS]", hud.get_field("text"))

        # Within 64u of Perks (-140, 460) and outside Class (-140, 320)
        self.update_at((-140, 400, 24))
        self.assertIn("[PERKS]", hud.get_field("text"))
        # Within 64u of Class (-140, 320) and outside Perks (-140, 460)
        self.update_at((-140, 380, 24))
        self.assertIn("[CLASS]", hud.get_field("text"))

        self.update_at((-140, 460, 96))  # +72u vertically (inside trigger height)
        self.assertEqual(hud.get_field("alpha"), 1)
        self.update_at((-140, 460, 97))  # +73u vertically (above trigger height)
        self.assertEqual(hud.get_field("alpha"), 0)
        self.update_at((-140, 460, -9))  # -33u vertically (below trigger floor tolerance)
        self.assertEqual(hud.get_field("alpha"), 0)
        triggers = [e for e in self.gsc.spawned_entities if e.classname == "trigger_radius"]
        self.assertTrue(triggers)
        self.assertTrue(all(trig.get_field("radius") == 64 for trig in triggers))

    def test_verruckt_prompts_and_use_resolve_each_wing(self) -> None:
        self.gsc.call(BZ_STATIONS_MOD, "bz_stations_cleanup")
        self.gsc.level.set_field("script", "nazi_zombie_asylum")
        self.gsc.call(BZ_STATIONS_MOD, "bz_stations_init")
        instances = self.gsc.level.get_field("bz_station_list")
        for i, (origin, _) in enumerate(VERRUCKT_STATION_PLACEMENTS):
            sid = EXPECTED_STATION_IDS[i % 4]
            with self.subTest(station=sid, origin=origin):
                self.update_at(origin)
                hud = self.player.get_field("bz_station_prompt_hud")
                self.assertEqual(hud.get_field("alpha"), 1)
                self.assertTrue(hud.get_field("text").startswith(f"[{sid.upper()}]"))
                self.assertEqual(self.player.get_field("bz_station_prompt_id"), sid)
                self.assertIs(
                    self.gsc.call(BZ_STATIONS_MOD, "bz_stations_find_nearest_in_range", self.player), instances[i]
                )
                self.assertEqual(
                    self.gsc.call(BZ_STATIONS_MOD, "bz_stations_resolve_use_target", self.player, "fallback"), sid
                )

        # Simulate overlapping instances to distinguish the south HUD preference from the nearest fallback.
        self.update_at((940, -15, 96))
        instances[5].set_field("origin", GscArray([940, -65, 96]))
        self.player.set_field("origin", GscArray([940, -55, 96]))
        self.assertIs(
            self.gsc.call(BZ_STATIONS_MOD, "bz_stations_find_nearest_in_range", self.player), instances[5]
        )
        self.assertEqual(
            self.gsc.call(BZ_STATIONS_MOD, "bz_stations_resolve_use_target", self.player, "class"), "perks"
        )

    def test_station_selection_falls_back_to_primary_registry(self) -> None:
        perks = self.gsc.level.get_field("bz_stations")["perks"]
        for station_list in (UNDEFINED, GscArray()):
            with self.subTest(station_list=station_list):
                self.gsc.level.set_field("bz_station_list", station_list)
                self.update_at((-140, 460, 24))
                self.assertEqual(self.player.get_field("bz_station_prompt_id"), "perks")
                self.assertIs(
                    self.gsc.call(BZ_STATIONS_MOD, "bz_stations_find_nearest_in_range", self.player), perks
                )
                self.assertEqual(
                    self.gsc.call(BZ_STATIONS_MOD, "bz_stations_resolve_use_target", self.player, "class"), "perks"
                )

    def test_overlapping_verruckt_triggers_open_same_nearest_station_as_hud(self) -> None:
        class _StopTriggerLoop(Exception):
            pass

        class _TriggerStationRuntime(StationHudRuntime):
            def __init__(self, mod_root: Path, dvars: FakeDvarStore) -> None:
                super().__init__(mod_root, dvars)
                self.trigger_player: FakeEntity | None = None
                self.trigger_delivered = False

            def _eval_expr(self, expr: Any, mod_key: str, env: dict[str, Any]) -> Any:
                from tests.gsc_runtime import VarRef
                from tests.test_bz_hooks_and_build import MethodCallExpr

                if isinstance(expr, MethodCallExpr) and expr.method_name.lower() == "waittill" and expr.args:
                    ev_name = self._eval_expr(expr.args[0], mod_key, env)
                    if ev_name == "trigger":
                        if self.trigger_delivered:
                            raise _StopTriggerLoop()
                        self.trigger_delivered = True
                        if len(expr.args) > 1 and isinstance(expr.args[1], VarRef):
                            env[expr.args[1].name.lower()] = self.trigger_player
                        return UNDEFINED
                return super()._eval_expr(expr, mod_key, env)

            def _exec_method(self, receiver: Any, method: str, args: list[Any], line: int) -> Any:
                if method == "usebuttonpressed":
                    return True
                return super()._exec_method(receiver, method, args, line)

        dvars = FakeDvarStore()
        for gate in ("bz_enabled", "bz_perks_enabled", "bz_classes_enabled", "bz_pap_enabled", "bz_elements_enabled"):
            dvars.set(gate, "1")
        gsc = _TriggerStationRuntime(MOD_ROOT, dvars)
        gsc.level.set_field("script", "nazi_zombie_asylum")
        gsc.call(BZ_HOOKS_MOD, "bz_init")
        player = FakeEntity("VerrucktPlayer", ent_num=0)
        gsc.players.append(player)
        gsc.trigger_player = player
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_spawned", player)

        # (949, 335, 96) lies inside BOTH Perks (920, 370; ~45u) and Arsenal (985, 295; ~54u).
        player.set_field("origin", GscArray([949, 335, 96]))
        gsc.call(BZ_STATIONS_MOD, "bz_stations_update_prompt_hud", player)
        hud = player.get_field("bz_station_prompt_hud")
        self.assertIn("[PERKS]", hud.get_field("text"))

        # Move to (955, 330, 96) BEFORE the next HUD refresh (Perks ~53u, Arsenal ~46u — both eligible).
        # Exercise Arsenal's actual bz_station_trigger_think(): it must open the displayed Perks station.
        player.set_field("origin", GscArray([955, 330, 96]))
        arsenal_station = gsc.level.get_field("bz_stations")["arsenal"]
        with self.assertRaises(_StopTriggerLoop):
            gsc.call_on(arsenal_station, BZ_STATIONS_MOD, "bz_station_trigger_think")
        self.assertEqual(player.get_field("bz_active_station_id"), "perks")
        self.assertEqual(player.get_field("bz_active_station_menu"), "bz_station_perks")

        # Close menu, advance past Use cooldown, refresh HUD at (955, 330, 96) -> [ARSENAL].
        # Now Perks's trigger firing Use must open the displayed Arsenal station.
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_perks", "close")
        player.set_field("bz_station_next_use_time", 0)
        gsc.call(BZ_STATIONS_MOD, "bz_stations_update_prompt_hud", player)
        self.assertIn("[ARSENAL]", hud.get_field("text"))
        perks_station = gsc.level.get_field("bz_stations")["perks"]
        gsc.trigger_delivered = False
        with self.assertRaises(_StopTriggerLoop):
            gsc.call_on(perks_station, BZ_STATIONS_MOD, "bz_station_trigger_think")
        self.assertEqual(player.get_field("bz_active_station_id"), "arsenal")
        self.assertEqual(player.get_field("bz_active_station_menu"), "bz_station_arsenal")

    def test_prompt_hides_when_dead_in_last_stand_or_in_station_menu(self) -> None:
        origin = (-140, 460, 24)
        self.update_at(origin)
        hud = self.player.get_field("bz_station_prompt_hud")
        for field, blocked, restored in (
            ("health", 0, 100),
            ("revivetrigger", GscStruct(), UNDEFINED),
            ("is_in_laststand", True, False),
            ("in_last_stand", True, False),
        ):
            with self.subTest(field=field):
                self.player.set_field(field, blocked)
                self.update_at(origin)
                self.assertEqual(hud.get_field("alpha"), 0)
                self.player.set_field(field, restored)
                self.update_at(origin)
                self.assertEqual(hud.get_field("alpha"), 1)

        self.assertTrue(self.gsc.call(BZ_STATIONS_MOD, "bz_stations_open_for_player", self.player, "perks"))
        self.assertEqual(hud.get_field("alpha"), 0)
        self.update_at(origin)
        self.assertEqual(hud.get_field("alpha"), 0)
        self.assertEqual(self.gsc.hud_elems, [hud])

    def test_disconnect_and_end_game_destroy_each_tracked_client_hud_once(self) -> None:
        second = FakeEntity("PlayerTwo", ent_num=1)
        third = FakeEntity("PlayerThree", ent_num=2)
        self.gsc.players.extend([second, third])
        for player in (self.player, second, third):
            player.set_field("origin", GscArray([-140, 460, 24]))
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_spawned", player)
            self.gsc.call(BZ_STATIONS_MOD, "bz_stations_update_prompt_hud", player)

        watcher = "bz_stations_watch_prompt_disconnect"
        self.assertEqual(self.gsc._threads.count((self.player, watcher, [])), 1)
        first_hud, second_hud, third_hud = self.gsc.hud_elems

        # Run the scheduled child for the departing player. The offline runtime
        # records waittill and executes the body that would resume at disconnect.
        self.gsc.players.remove(self.player)
        self.gsc.call_on(self.player, BZ_STATIONS_MOD, watcher)
        self.assertIn((self.player, "disconnect"), self.gsc.waits)
        self.assertEqual(self.gsc.destroyed_huds, [first_hud])
        self.assertIs(self.player.get_field("bz_station_prompt_hud"), UNDEFINED)
        self.assertEqual(second_hud.get_field("alpha"), 1)
        self.assertEqual(third_hud.get_field("alpha"), 1)

        # The tracked list covers a client already absent from GetPlayers at shutdown.
        self.gsc.players.remove(second)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.gsc.call(BZ_STATIONS_MOD, "bz_stations_cleanup")
        self.assertEqual(self.gsc.destroyed_huds, [first_hud, second_hud, third_hud])
        self.assertIs(third.get_field("bz_station_prompt_hud"), UNDEFINED)
        self.assertEqual(self.gsc.level.get_field("bz_station_prompt_huds").size, 0)


class TestBzStationUiSyncAndPurchases(unittest.TestCase):
    """Slice 2: Per-player UI dvar sync, Co-op isolation, scriptMenuResponse validation & item_purchased hook."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzGscRuntime(MOD_ROOT, self.dvars)
        self.p1 = FakeEntity("PlayerOne", ent_num=0)
        self.p2 = FakeEntity("PlayerTwo", ent_num=1)
        self.p1.set_field("score", 50000)
        self.p2.set_field("score", 1500)
        self.p1.give_weapon("thompson", make_current=True)
        self.p2.give_weapon("colt", make_current=True)
        self.gsc.players.extend([self.p1, self.p2])

        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")
        self.dvars.set("bz_elements_enabled", "0")
        self.dvars.set("bz_companions_enabled", "0")

        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

    def test_open_and_close_station_menu_are_strictly_per_player_in_coop(self) -> None:
        # Clear any connect-time dvars on p2 to verify p1 opening a menu never touches p2
        self.p2.client_dvars.clear()
        self.p2.opened_menus.clear()

        opened = self.gsc.call(BZ_STATIONS_MOD, "bz_stations_open_for_player", self.p1, "perks")
        self.assertTrue(opened)
        self.assertEqual(self.p1.opened_menus, ["bz_station_perks"])
        self.assertEqual(self.p2.opened_menus, [])
        self.assertEqual(self.p2.client_dvars, {})

        # Verify p1 received live affordability dvars
        self.assertEqual(self.p1.client_dvars["ui_bz_score"], "POINTS: 50000")
        self.assertEqual(self.p1.client_dvars["ui_bz_class"], "CLASS: NONE")
        self.assertEqual(self.p1.client_dvars["ui_bz_perk_staminup"], "BUY 2000")
        self.assertEqual(self.p1.client_dvars["ui_bz_perk_mule_kick"], "BUY 4000")
        self.assertEqual(self.p1.client_dvars["ui_bz_t2_staminup"], "REQ TIER 1")
        self.assertEqual(self.p1.client_dvars["ui_bz_apex_second_chance"], "BUY 8000")
        self.assertIn(
            "BZ_EVENT|STATION_OPEN|player=PlayerOne;station=perks;menu=bz_station_perks;score=50000",
            self.gsc.emitted_events,
        )

        # Closing via scriptMenuResponse only closes p1's menu and ignores unrelated menus
        self.assertFalse(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "pausedmenu", "close")
        )
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "close")
        )
        self.assertEqual(self.p1.closed_menus, 1)
        self.assertEqual(self.p2.closed_menus, 0)
        self.assertFalse(self.p1.get_field("bz_station_open"))
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "close")
        )
        self.assertEqual(self.p1.closed_menus, 1)
        self.assertEqual(self.gsc.played_local_sounds, [(self.p1, "lid_open"), (self.p1, "lid_close")])

    def test_valid_purchases_deduct_score_dispatch_item_purchased_and_sync_ui(self) -> None:
        purchased_log: list[tuple[str, str, str, int, str]] = []

        def on_purchased(_self: Any, ctx: GscStruct) -> None:
            res = ctx.get_field("result")
            purchased_log.append(
                (
                    ctx.get_field("player").get_field("name"),
                    ctx.get_field("category"),
                    ctx.get_field("item_id"),
                    int(res.get_field("cost")),
                    ctx.get_field("weapon_name"),
                )
            )

        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "item_purchased",
            self.gsc.register_py_callback("on_item_purchased_all", on_purchased),
            "core",
        )

        # 1. Buy Stamin-Up (2000) -> 48000 remaining
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_perk:staminup")
        )
        self.assertEqual(self.p1.get_field("score"), 48000)
        self.assertEqual(self.p1.client_dvars["ui_bz_perk_staminup"], "OWNED")
        self.assertEqual(self.p1.client_dvars["ui_bz_t2_staminup"], "UPGRADE 5000")

        # 2. Upgrade Stamin-Up II (5000) -> 43000 remaining
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_t2:staminup")
        )
        self.assertEqual(self.p1.get_field("score"), 43000)
        self.assertEqual(self.p1.client_dvars["ui_bz_t2_staminup"], "OWNED")

        # 3. Stock Juggernog picked up from stock machine unlocks Juggernog II automatically
        self.p1.give_perk("specialty_armorvest")
        self.gsc.call(BZ_STATIONS_MOD, "bz_stations_sync_player_ui", self.p1)
        self.assertEqual(self.p1.client_dvars["ui_bz_perk_juggernog"], "OWNED")
        self.assertEqual(self.p1.client_dvars["ui_bz_t2_juggernog"], "UPGRADE 5000")
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_t2:juggernog")
        )
        self.assertEqual(self.p1.get_field("score"), 38000)

        # 4. Buy Apex Perk Second Chance (8000 test cap) -> 30000 remaining
        self.assertTrue(
            self.gsc.call(
                BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_apex:second_chance"
            )
        )
        self.assertEqual(self.p1.get_field("score"), 30000)
        self.assertEqual(self.p1.client_dvars["ui_bz_apex_second_chance"], "OWNED")

        # 5. Buy Titan Class (5000 test cap) -> 25000 remaining
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:titan")
        )
        self.assertEqual(self.p1.get_field("score"), 25000)
        self.assertEqual(self.p1.client_dvars["ui_bz_class"], "CLASS: Titan")
        self.assertEqual(self.p1.client_dvars["ui_bz_class_titan"], "ACTIVE")

        # 6. Top up score and buy Single PaP (5000) -> Double PaP (5000 test cap) -> PaP Knife / Bowie / Cluster
        self.p1.set_field("score", 35000)
        self.p1.give_perk("specialty_altmelee")
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_pap", "buy_pap:single_pap")
        )
        self.assertEqual(self.p1.get_field("score"), 30000)
        self.assertEqual(self.p1.client_dvars["ui_bz_pap_single_pap"], "UPGRADED")
        self.assertEqual(self.p1.client_dvars["ui_bz_pap_double_pap"], "UPGRADE 5000")

        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_pap", "buy_pap:double_pap")
        )
        self.assertEqual(self.p1.get_field("score"), 25000)
        self.assertEqual(self.p1.client_dvars["ui_bz_pap_double_pap"], "MAXED (II)")

        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_pap:pap_knife")
        )
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_pap:pap_bowie")
        )
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_pap:pap_cluster")
        )
        self.assertEqual(self.p1.get_field("score"), 10000)

        self.assertEqual(
            purchased_log,
            [
                ("PlayerOne", "perk", "staminup", 2000, "thompson"),
                ("PlayerOne", "perk_t2", "staminup", 5000, "thompson"),
                ("PlayerOne", "perk_t2", "juggernog", 5000, "thompson"),
                ("PlayerOne", "apex", "second_chance", 8000, "thompson"),
                ("PlayerOne", "class", "titan", 5000, "thompson"),
                ("PlayerOne", "pap", "single_pap", 5000, "thompson"),
                ("PlayerOne", "pap", "double_pap", 5000, "thompson"),
                ("PlayerOne", "pap", "pap_knife", 5000, "thompson"),
                ("PlayerOne", "pap", "pap_bowie", 5000, "thompson"),
                ("PlayerOne", "pap", "pap_cluster", 5000, "thompson"),
            ],
        )
        self.assertEqual(self.gsc.played_local_sounds, [(self.p1, "cha_ching")] * 10)
        self.assertIn(
            "BZ_EVENT|STATION_PURCHASE|player=PlayerOne;menu=bz_station_perks;category=perk;item=staminup;status=ok;cost=2000;score=48000",
            self.gsc.emitted_events,
        )

    def test_rejected_purchases_and_disabled_gates_never_deduct_score_or_fire_hook(self) -> None:
        hook_calls: list[str] = []
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "item_purchased",
            self.gsc.register_py_callback("no_fire", lambda _s, ctx: hook_calls.append(ctx.get_field("item_id"))),
            "core",
        )

        # Insufficient points on p2 (1500 < 2000)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p2, "bz_station_perks", "buy_perk:staminup")
        self.assertEqual(self.p2.get_field("score"), 1500)
        self.assertIn("Need 2000", self.p2.client_dvars["ui_bz_feedback"])

        # Missing prereq: Tier 2 without Tier 1, Double PaP without PaP, PaP Bowie without Bowie
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_t2:mule_kick")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_pap", "buy_pap:double_pap")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_pap:pap_bowie")
        self.assertEqual(self.p1.get_field("score"), 50000)

        # Disabled Feature Gate rejects buy_class:* even with plenty of points
        self.dvars.set("bz_classes_enabled", "0")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:broker")
        self.assertEqual(self.p1.get_field("score"), 50000)
        self.assertIn(
            "BZ_EVENT|STATION_PURCHASE|player=PlayerOne;menu=bz_station_class;category=class;item=broker;status=gate_disabled;cost=0;score=50000",
            self.gsc.emitted_events,
        )

        # Invalid item token
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_perk:bogus_perk")
        self.assertEqual(self.p1.get_field("score"), 50000)
        self.assertEqual(hook_calls, [])

        # Already owned rejection
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_perk:ap")
        self.assertEqual(self.p1.get_field("score"), 47000)
        self.assertEqual(hook_calls, ["ap"])
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_perk:ap")
        self.assertEqual(self.p1.get_field("score"), 47000)
        self.assertEqual(hook_calls, ["ap"])
        self.assertEqual(
            self.gsc.played_local_sounds,
            [(self.p2, "no_cha_ching")]
            + [(self.p1, "no_cha_ching")] * 5
            + [(self.p1, "cha_ching"), (self.p1, "no_cha_ching")],
        )


SCRIPT_MENU_RESP_RE = re.compile(r'scriptMenuResponse\s+"([^"]+)"\s*;')

EXPECTED_MENU_TOKENS: dict[str, set[str]] = {
    "bz_station_perks": {
        "buy_perk:staminup",
        "buy_perk:mule_kick",
        "buy_perk:ap",
        "buy_t2:juggernog",
        "buy_t2:speed_cola",
        "buy_t2:double_tap",
        "buy_t2:quick_revive",
        "buy_t2:staminup",
        "buy_t2:mule_kick",
        "buy_t2:ap",
        "buy_apex:double_ammo",
        "buy_apex:lightweight_heavy",
        "buy_apex:second_chance",
        "buy_apex:blast_shield",
        "close",
    },
    "bz_station_class": {
        "buy_class:medic",
        "buy_class:titan",
        "buy_class:sapper",
        "buy_class:daredevil",
        "buy_class:assassin",
        "buy_class:broker",
        "close",
    },
    "bz_station_arsenal": {
        "buy_pap:pap_knife",
        "buy_pap:pap_bowie",
        "buy_pap:pap_cluster",
        "buy_element:acid_sprayer",
        "buy_element:cryo_cannon",
        "buy_element:multi_crossbow",
        "buy_element:blade_boomerang",
        "buy_gear:war_club",
        "buy_gear:pap_war_club",
        "buy_gear:equip_bowie",
        "buy_gear:portal_grenade",
        "close",
    },
    "bz_station_pap": {
        "buy_pap:single_pap",
        "buy_pap:double_pap",
        "close",
    },
}


class TestBzStationMenusManifestAndWaw17Compliance(unittest.TestCase):
    """Slice 3: .menu structural/ASCII/token validation, manifest registration, and WaW 1.7 GSC compliance."""

    def test_all_four_station_menus_are_ascii_balanced_non_fullscreen_and_complete(self) -> None:
        import verify_hud_menus

        ui_dir = MOD_ROOT / "ui"
        for menu_name, expected_tokens in EXPECTED_MENU_TOKENS.items():
            menu_path = ui_dir / f"{menu_name}.menu"
            self.assertTrue(menu_path.is_file(), f"Missing station menu file: {menu_path}")

            text = menu_path.read_text(encoding="latin1")
            self.assertEqual(
                verify_hud_menus.validate_menu_braces(text, filename=menu_path.name),
                [],
                f"Unbalanced braces in {menu_path.name}",
            )
            non_ascii = [ch for ch in text if ord(ch) > 126 or (ord(ch) < 32 and ch not in "\t\r\n")]
            self.assertEqual(non_ascii, [], f"Non-ASCII chars in {menu_path.name}: {non_ascii!r}")

            self.assertIn(f'name\t\t\t"{menu_name}"', text)
            self.assertRegex(text, r"fullscreen\s+0\b")
            self.assertIn("onEsc", text)
            self.assertIn('exp\t\t\t\ttext( dvarString( "ui_bz_score" ) );', text)
            self.assertIn('exp\t\t\t\ttext( dvarString( "ui_bz_feedback" ) );', text)
            # Every WaW 1.7 `exp text(...)` directive must be semicolon-terminated for linker_pc.exe
            for line in text.splitlines():
                if "exp" in line and "text(" in line:
                    self.assertTrue(
                        line.rstrip().endswith(";"),
                        f"Missing trailing semicolon on exp text() in {menu_path.name}: {line}",
                    )

            found_tokens = set(SCRIPT_MENU_RESP_RE.findall(text))
            self.assertEqual(
                found_tokens,
                expected_tokens,
                f"scriptMenuResponse token set mismatch in {menu_path.name}",
            )

        # Verify Phase 2 & Phase 3 future placeholders exist in Arsenal menu
        arsenal_text = (ui_dir / "bz_station_arsenal.menu").read_text(encoding="latin1")
        self.assertIn("Phase 2", arsenal_text)
        self.assertIn("Phase 3", arsenal_text)

        # Verify Mule Kick II - 4th Slot label is present in Perks menu
        perks_text = (ui_dir / "bz_station_perks.menu").read_text(encoding="latin1")
        self.assertIn("4th Slot", perks_text)

    def test_every_menu_script_response_token_executes_cleanly_in_stations_gsc(self) -> None:
        dvars = FakeDvarStore()
        gsc = BzGscRuntime(MOD_ROOT, dvars)
        dvars.set("bz_enabled", "1")
        dvars.set("bz_perks_enabled", "1")
        dvars.set("bz_classes_enabled", "1")
        dvars.set("bz_pap_enabled", "1")
        dvars.set("bz_elements_enabled", "1")

        player = FakeEntity("TokenTester", ent_num=0)
        player.set_field("score", 500000)
        player.give_perk("specialty_armorvest")
        player.give_perk("specialty_fastreload")
        player.give_perk("specialty_rof")
        player.give_perk("specialty_quickrevive")
        player.give_perk("specialty_altmelee")
        player.give_weapon("thompson", make_current=True)
        gsc.players.append(player)

        gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        gsc.call(BZ_HOOKS_MOD, "bz_init")

        ui_dir = MOD_ROOT / "ui"
        # Execute every non-close token in each menu in file order (buy_perk before buy_t2; single_pap before double_pap)
        for menu_name in EXPECTED_MENUS:
            text = (ui_dir / f"{menu_name}.menu").read_text(encoding="latin1")
            tokens = SCRIPT_MENU_RESP_RE.findall(text)
            seen: set[str] = set()
            for tok in tokens:
                if tok == "close" or tok in seen:
                    continue
                seen.add(tok)
                prev_len = len(gsc.emitted_events)
                handled = gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, menu_name, tok)
                self.assertTrue(handled, f"Menu token {menu_name}/{tok} was not handled")
                new_events = gsc.emitted_events[prev_len:]
                self.assertTrue(
                    any("status=ok;" in ev for ev in new_events),
                    f"Menu token {menu_name}/{tok} did not succeed: {new_events}",
                )

    def test_mod_csv_and_patch_menus_register_all_station_menus_with_zero_fx_bloat(self) -> None:
        patch_menus = (MOD_ROOT / "ui" / "patch_menus.txt").read_text(encoding="latin1")
        mod_csv = (MOD_ROOT / "mod.csv").read_text(encoding="latin1")

        for menu_name in EXPECTED_MENUS:
            rel = f"ui/scriptmenus/{menu_name}.menu"
            self.assertIn(f'loadMenu {{ "{rel}" }}', patch_menus)
            self.assertIn(f"menufile,{rel}", mod_csv)

        self.assertIn("rawfile,maps/_bz_stations.gsc", mod_csv)
        # Enforce 400-FX budget discipline: zero FX, weapon, or model entries in mod.csv
        for line in mod_csv.splitlines():
            stripped = line.strip().lower()
            if not stripped or stripped.startswith("//"):
                continue
            self.assertFalse(
                stripped.startswith(("fx,", "weapon,", "xmodel,")),
                f"Forbidden asset type in mod.csv (400-FX safety): {line}",
            )

    def test_raw_ui_overlay_preserves_and_restores_stock_files(self) -> None:
        import build_mod
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage_dir = root / "mods" / "waw_gauntlet"
            raw_ui = root / "raw" / "ui"
            (stage_dir / "ui" / "scriptmenus").mkdir(parents=True)
            raw_ui.mkdir(parents=True)

            stock_patch = raw_ui / "patch_menus.txt"
            stock_patch.write_bytes(b"// stock patch_menus\n")
            (stage_dir / "ui" / "patch_menus.txt").write_bytes(b"// patched patch_menus\n")
            (stage_dir / "ui" / "scriptmenus" / "bz_station_perks.menu").write_bytes(b"// perks\n")

            backups = build_mod._overlay_staged_ui_into_raw(stage_dir=stage_dir, tools_root=root)
            self.assertEqual(stock_patch.read_bytes(), b"// patched patch_menus\n")
            self.assertTrue((raw_ui / "scriptmenus" / "bz_station_perks.menu").is_file())

            build_mod._restore_raw_ui_overlay(backups)
            self.assertEqual(stock_patch.read_bytes(), b"// stock patch_menus\n")
            self.assertFalse((raw_ui / "scriptmenus" / "bz_station_perks.menu").exists())

    def test_bz_stations_and_hooks_are_waw17_compliant(self) -> None:
        gsc = BzGscRuntime(MOD_ROOT, FakeDvarStore())

        for path in (BZ_STATIONS_PATH, BZ_HOOKS_PATH):
            source = path.read_text(encoding="latin1")
            tokenize(source, filename=str(path))
            code_only = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
            self.assertIsNone(re.search(r"\bforeach\b", code_only), f"Forbidden foreach in {path.name}")

        stations_mod = gsc.load_module(BZ_STATIONS_MOD)
        sync_station_funcs = (
            "bz_stations_register",
            "bz_stations_pre_init",
            "bz_stations_init",
            "bz_stations_spawn_one",
            "bz_stations_cleanup",
            "bz_stations_sync_player_ui",
            "bz_stations_open_for_player",
            "bz_stations_on_menu_response",
            "bz_stations_on_player_connect",
            "bz_stations_on_player_spawned",
            "bz_stations_on_player_downed",
        )
        for fn_name in sync_station_funcs:
            self.assertIn(fn_name, stations_mod, f"Missing {fn_name}() in _bz_stations.gsc")
            self.assertFalse(
                _ast_contains_method_call(stations_mod[fn_name].body, "endon"),
                f"Forbidden endon() inside synchronous caller {fn_name}()",
            )

        hooks_mod = gsc.load_module(BZ_HOOKS_MOD)
        self.assertIn("bz_on_item_purchased", hooks_mod)
        self.assertFalse(
            _ast_contains_method_call(hooks_mod["bz_on_item_purchased"].body, "endon"),
            "Forbidden endon() inside synchronous caller bz_on_item_purchased()",
        )


if __name__ == "__main__":
    unittest.main()
