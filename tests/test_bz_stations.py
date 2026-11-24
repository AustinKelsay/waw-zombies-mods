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


class TestBzStationCoordinatesAndSpawning(unittest.TestCase):
    """Slice 1: 4-map coordinate coverage, floor-snap, Classic/Feature-Gate isolation & cleanup."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzGscRuntime(MOD_ROOT, self.dvars)
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
            expected_ids = (
                EXPECTED_FACTORY_STATION_IDS if map_name == "nazi_zombie_factory" else EXPECTED_STATION_IDS
            )
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

            # Every pair of stations must be separated beyond the 78u prompt / 64u trigger radius (>= 85u)
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
                # Shi No Numa arsenal moved off central stairwell cutout onto solid -528 upstairs floor
                self.assertEqual(tuple(by_id["arsenal"].get_field("origin")[i] for i in range(3)), (9960, 520, -492))
                self.assertEqual(tuple(by_id["perks"].get_field("origin")[i] for i in range(3)), (10020, 610, -492))
                self.assertEqual(tuple(by_id["class"].get_field("origin")[i] for i in range(3)), (10280, 610, -492))
                self.assertEqual(tuple(by_id["pap"].get_field("origin")[i] for i in range(3)), (10280, 410, -492))
            elif map_name == "nazi_zombie_asylum":
                # Verruckt arsenal nudged for clean breathing room from Quick Revive (1149, 402)
                self.assertEqual(tuple(by_id["arsenal"].get_field("origin")[i] for i in range(3)), (1010, 390, 96))

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

        self.assertEqual(self.gsc.precached_menus, [])
        self.assertEqual(self.gsc.spawned_entities, [])
        self.assertFalse(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.player, "bz_station_perks", "buy_perk:staminup")
        )
        self.assertEqual(self.gsc.emitted_events, [])

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

        # Non-Factory maps (Nacht, Verruckt, Shi No Numa) still spawn all 4 stations including standalone pap
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
            self.assertEqual(len(gsc2.spawned_entities), 12, f"Expected 12 entities on {non_factory}")

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
            expected_count = 3 if map_name == "nazi_zombie_factory" else 4
            self.assertEqual(
                len(models),
                expected_count,
                f"Expected {expected_count} station script_models on {map_name}",
            )
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
