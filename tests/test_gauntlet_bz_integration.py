"""Offline integration tests for Base Zombies Enhancements inside Zombie Gauntlet Mode.

Exercises real GSC scripts via tests/gsc_interpreter.py:
  - mod/maps/_bz_gauntlet_bridge.gsc (cross-stage persistence, serialization, restore, menu close)
  - mod/maps/_gauntlet_state.gsc (clear_run_state wipes the Base Zombies ledgers)
  - mod/maps/_gauntlet_perks.gsc (Titan + Juggernog I/II maxhealth composition & loss)
  - mod/maps/_gauntlet_mode.gsc (Stage Clear / checkpoint / restore wiring)
  - mod/ui/gauntlet_menus.inc, mod/ui/bz_menus.inc, mod/ui/pc_gamesetup_coop.menu
  - scripts/build_mod.py (bz_init before on_stage_init, Solo & Co-op menu patches)
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_ROOT = REPO_ROOT / "mod"
SCRIPTS_DIR = REPO_ROOT / "scripts"

for p in (str(REPO_ROOT), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import build_mod  # noqa: E402
import verify_hud_menus  # noqa: E402
from tests.gsc_runtime import FakeDvarStore, UNDEFINED, _waw_to_str, tokenize  # noqa: E402
from tests.test_bz_hooks_and_build import _ast_contains_method_call  # noqa: E402
from tests.test_bz_perks import BzPerksRuntime, FakeHudElem, PerksFakeEntity  # noqa: E402
from tests.test_gauntlet_hud_menus import (  # noqa: E402
    SYNTHETIC_STOCK_LEVELS_MENU,
    SYNTHETIC_STOCK_MAIN_MENU,
    SYNTHETIC_STOCK_SYSTEMLINK_LOBBY_MENU,
    SYNTHETIC_STOCK_XBOXLIVE_LOBBY_MENU,
)

BRIDGE_MOD = "maps\\_bz_gauntlet_bridge"
BZ_HOOKS_MOD = "maps\\_bz_hooks"
BZ_STATE_MOD = "maps\\_bz_state"
BZ_PERKS_MOD = "maps\\_bz_perks"
BZ_CLASSES_MOD = "maps\\_bz_classes"
BZ_STATIONS_MOD = "maps\\_bz_stations"
GAUNTLET_STATE_MOD = "maps\\_gauntlet_state"
GAUNTLET_PERKS_MOD = "maps\\_gauntlet_perks"
GAUNTLET_MODE_MOD = "maps\\_gauntlet_mode"


class GauntletBzRuntime(BzPerksRuntime):
    """Extends BzPerksRuntime with Gauntlet player/HUD methods needed by _gauntlet_mode/_gauntlet_perks."""

    def _exec_method(self, receiver, method: str, args, line: int):
        if isinstance(receiver, FakeHudElem) and method in ("setshader", "scaleovertime", "fadeovertime"):
            return UNDEFINED
        if method == "closemenu":
            receiver.closed_menus = getattr(receiver, "closed_menus", 0) + 1
            return UNDEFINED
        if method == "getguid":
            return receiver.get_field("guid") or ""
        if method == "enableinvulnerability":
            return UNDEFINED
        if method == "setclientdvar":
            if len(args) >= 2:
                if not hasattr(receiver, "client_dvars"):
                    receiver.client_dvars = {}
                receiver.client_dvars[_waw_to_str(args[0])] = _waw_to_str(args[1])
            return UNDEFINED
        if method == "getweaponammoclip":
            w = _waw_to_str(args[0]).lower() if args else ""
            return getattr(receiver, "weapon_clip", {}).get(w, 0)
        if method == "setweaponammoclip":
            if len(args) >= 2 and hasattr(receiver, "weapon_clip"):
                receiver.weapon_clip[_waw_to_str(args[0]).lower()] = int(args[1])
            return UNDEFINED
        return super()._exec_method(receiver, method, args, line)


def _make_enhanced_dvars() -> FakeDvarStore:
    dvars = FakeDvarStore()
    dvars.set("gauntlet_enabled", "1")
    dvars.set("bz_enabled", "1")
    dvars.set("bz_perks_enabled", "1")
    dvars.set("bz_classes_enabled", "1")
    dvars.set("bz_pap_enabled", "1")
    dvars.set("bz_elements_enabled", "1")
    dvars.set("bz_companions_enabled", "0")
    return dvars


def _make_player(gsc: GauntletBzRuntime, guid: str, name: str, score: int = 50000) -> PerksFakeEntity:
    p = PerksFakeEntity(name=name, ent_num=len(gsc.players), is_player=True)
    p.set_field("guid", guid)
    p.set_field("playername", name)
    p.set_field("name", name)
    p.set_field("score", score)
    p.set_field("maxhealth", 100)
    p.set_field("health", 100)
    p.set_field("sessionstate", "playing")
    p.set_field("initialized", True)
    p.alive = True
    p.give_weapon("colt", make_current=True, stock=32)
    p.give_weapon("stielhandgranate", make_current=False, stock=0)
    p.weapon_clip["colt"] = 8
    p.weapon_clip["stielhandgranate"] = 4
    gsc.players.append(p)
    return p


class TestGauntletBzIntegration(unittest.TestCase):
    def test_bridge_gsc_compliance_and_manifest_and_hook_ordering(self) -> None:
        bridge_path = MOD_ROOT / "maps" / "_bz_gauntlet_bridge.gsc"
        self.assertTrue(bridge_path.is_file())
        src = bridge_path.read_text(encoding="latin1")
        tokenize(src, filename=str(bridge_path))
        code_only = "\n".join(line.split("//", 1)[0] for line in src.splitlines())
        self.assertIsNone(re.search(r"\bforeach\b", code_only))

        gsc = GauntletBzRuntime(MOD_ROOT, _make_enhanced_dvars())
        mod = gsc.load_module(BRIDGE_MOD)
        for fn_name, fn_ast in mod.items():
            self.assertFalse(
                _ast_contains_method_call(fn_ast.body, "endon"),
                f"_bz_gauntlet_bridge::{fn_name} must not call endon() directly",
            )

        mod_csv = (MOD_ROOT / "mod.csv").read_text(encoding="latin1")
        self.assertIn("rawfile,maps/_bz_gauntlet_bridge.gsc", mod_csv)

        # Verify inject_zombiemode_hooks places bz_init() BEFORE on_stage_init()
        # so all 4 BZ shop stations exist during Cycle 2+ Prep Phase.
        synthetic_zm = (
            "round_start()\n{\n\tlevel thread round_think();\n}\n"
            "round_think()\n{\n\tround_wait();\n}\n"
            "end_game()\n{\n\tlevel.intermission = true;\n}\n"
        ).encode("latin1")
        patched = build_mod.inject_zombiemode_hooks(synthetic_zm, "nazi_zombie_prototype").decode("latin1")
        self.assertLess(
            patched.index("maps\\_bz_hooks::bz_init();"),
            patched.index("maps\\_gauntlet_mode::on_stage_init();"),
        )
        self.assertLess(
            patched.index("maps\\_gauntlet_mode::on_stage_init();"),
            patched.index("level thread round_think();"),
        )

    def test_cross_stage_persistence_solo_full_loadout(self) -> None:
        # Stage 1 (Nacht der Untoten): player acquires full BZ loadout
        dvars = _make_enhanced_dvars()
        gsc1 = GauntletBzRuntime(MOD_ROOT, dvars)
        gsc1.level.set_field("script", "nazi_zombie_prototype")
        gsc1.call(BZ_HOOKS_MOD, "bz_init")
        p1 = _make_player(gsc1, "1001", "Austin", score=250000)
        gsc1.call(BZ_HOOKS_MOD, "bz_on_player_connect", p1)

        # Equip Titan class + Standard/T2/Apex perks + PaP melee/cluster + War Club/Portal
        gsc1.call(BZ_STATE_MOD, "bz_try_buy_class", p1, "titan")
        gsc1.call(BZ_CLASSES_MOD, "bz_class_apply", p1, "titan")
        for pid in ("juggernog", "speed_cola", "staminup", "mule_kick", "ap"):
            gsc1.call(BZ_STATE_MOD, "bz_try_buy_perk", p1, pid)
            gsc1.call(BZ_PERKS_MOD, "bz_perks_apply_standard_perk", p1, pid)
        for pid in ("juggernog", "mule_kick", "staminup"):
            gsc1.call(BZ_STATE_MOD, "bz_try_buy_perk_t2", p1, pid)
            gsc1.call(BZ_PERKS_MOD, "bz_perks_apply_perk_t2", p1, pid)
        for aid in ("double_ammo", "second_chance", "blast_shield"):
            gsc1.call(BZ_STATE_MOD, "bz_try_buy_apex", p1, aid)
            gsc1.call(BZ_PERKS_MOD, "bz_perks_apply_apex_perk", p1, aid)

        p1.set_field("bz_pap_knife", True)
        p1.set_field("bz_pap_bowie", True)
        p1.set_field("bz_pap_cluster", True)
        p1.set_field("bz_owns_bowie", True)
        p1.set_field("bz_owns_war_club", True)
        p1.set_field("bz_pap_war_club", True)
        p1.set_field("bz_owns_portal_grenade", True)
        p1.set_field("bz_melee_slot", "war_club")

        # Snapshot at Stage 1 Clear
        saved = gsc1.call(BRIDGE_MOD, "snapshot_player_bz_state", p1, "nazi_zombie_prototype")
        self.assertTrue(saved)
        perm_dvar = dvars.get("gauntlet_bz_perm")
        perks_dvar = dvars.get("gauntlet_bz_perks")
        self.assertIn("g_1001=titan|", perm_dvar)
        self.assertIn("war_club", perm_dvar)
        self.assertIn("g_1001=", perks_dvar)

        # Stage 2 (Verruckt): fresh runtime sharing host dvars
        gsc2 = GauntletBzRuntime(MOD_ROOT, dvars)
        gsc2.level.set_field("script", "nazi_zombie_asylum")
        gsc2.call(BZ_HOOKS_MOD, "bz_init")
        p2 = _make_player(gsc2, "1001", "Austin", score=14500)

        restored = gsc2.call(BRIDGE_MOD, "restore_player_bz_state", p2, "nazi_zombie_asylum")
        self.assertTrue(restored)
        # Idempotent second call
        self.assertFalse(gsc2.call(BRIDGE_MOD, "restore_player_bz_state", p2, "nazi_zombie_asylum"))

        # Verify Class, PaP, Special Gear
        self.assertEqual(gsc2.call(BZ_STATE_MOD, "bz_state_get_class", p2), "titan")
        self.assertTrue(p2.get_field("bz_pap_knife"))
        self.assertTrue(p2.get_field("bz_pap_bowie"))
        self.assertTrue(p2.get_field("bz_pap_cluster"))
        self.assertTrue(p2.get_field("bz_owns_bowie"))
        self.assertTrue(p2.get_field("bz_owns_war_club"))
        self.assertTrue(p2.get_field("bz_pap_war_club"))
        self.assertTrue(p2.get_field("bz_owns_portal_grenade"))
        self.assertEqual(p2.get_field("bz_melee_slot"), "war_club")
        self.assertEqual(p2.get_field("bz_portal_charges"), 2)

        # Verify Perks + T2 + Apex + composed runtime stats
        for pid in ("juggernog", "speed_cola", "staminup", "mule_kick", "ap"):
            self.assertTrue(gsc2.call(BZ_STATE_MOD, "bz_state_has_perk", p2, pid), f"Missing T1 {pid}")
        for pid in ("juggernog", "mule_kick", "staminup"):
            self.assertTrue(gsc2.call(BZ_STATE_MOD, "bz_state_has_perk_t2", p2, pid), f"Missing T2 {pid}")
        for aid in ("double_ammo", "second_chance", "blast_shield"):
            self.assertTrue(gsc2.call(BZ_STATE_MOD, "bz_state_has_apex", p2, aid), f"Missing Apex {aid}")

        # Titan (2x) + Juggernog II (220) = 440 HP!
        self.assertEqual(p2.get_field("maxhealth"), 440)
        self.assertEqual(p2.get_field("health"), 440)
        # Mule Kick II = 4 primary weapons!
        self.assertEqual(gsc2.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", p2), 4)
        # Second Chance armed on Stage 2!
        self.assertTrue(p2.get_field("bz_second_chance_ready"))
        # Station UI synced with carried-over score!
        self.assertEqual(p2.client_dvars.get("ui_bz_score"), "POINTS: 14500")
        self.assertEqual(p2.client_dvars.get("ui_bz_class"), "CLASS: Titan")

    def test_dead_spectator_loses_perks_but_keeps_permanent_class_and_gear(self) -> None:
        dvars = _make_enhanced_dvars()
        gsc1 = GauntletBzRuntime(MOD_ROOT, dvars)
        gsc1.level.set_field("script", "nazi_zombie_asylum")
        gsc1.call(BZ_HOOKS_MOD, "bz_init")

        alive_p = _make_player(gsc1, "2001", "Host", score=50000)
        dead_p = _make_player(gsc1, "2002", "Friend", score=50000)
        gsc1.call(BZ_HOOKS_MOD, "bz_on_player_connect", alive_p)
        gsc1.call(BZ_HOOKS_MOD, "bz_on_player_connect", dead_p)

        # Both buy Sapper + PaP Cluster + Portal Grenade + Stamin-Up + Blast Shield
        for p in (alive_p, dead_p):
            p.set_field("bz_class", "sapper")
            p.set_field("bz_pap_cluster", True)
            p.set_field("bz_owns_portal_grenade", True)
            r1 = gsc1.call(BZ_STATE_MOD, "bz_try_buy_perk", p, "staminup")
            r2 = gsc1.call(BZ_STATE_MOD, "bz_try_buy_apex", p, "blast_shield")
            self.assertTrue(r1.get_field("ok"))
            self.assertTrue(r2.get_field("ok"))

        # Friend died and is spectating at Stage Clear
        dead_p.alive = False
        dead_p.set_field("sessionstate", "spectator")

        gsc1.call(BRIDGE_MOD, "snapshot_player_bz_state", alive_p, "nazi_zombie_asylum")
        gsc1.call(BRIDGE_MOD, "snapshot_player_bz_state", dead_p, "nazi_zombie_asylum")

        # Next stage (Shi No Numa): both spawn alive
        gsc2 = GauntletBzRuntime(MOD_ROOT, dvars)
        gsc2.level.set_field("script", "nazi_zombie_sumpf")
        gsc2.call(BZ_HOOKS_MOD, "bz_init")
        alive_p2 = _make_player(gsc2, "2001", "Host", score=20000)
        dead_p2 = _make_player(gsc2, "2002", "Friend", score=15000)

        gsc2.call(BRIDGE_MOD, "restore_player_bz_state", alive_p2, "nazi_zombie_sumpf")
        gsc2.call(BRIDGE_MOD, "restore_player_bz_state", dead_p2, "nazi_zombie_sumpf")

        # Host kept everything including Stamin-Up & Blast Shield
        self.assertEqual(gsc2.call(BZ_STATE_MOD, "bz_state_get_class", alive_p2), "sapper")
        self.assertTrue(gsc2.call(BZ_STATE_MOD, "bz_state_has_perk", alive_p2, "staminup"))
        self.assertTrue(gsc2.call(BZ_STATE_MOD, "bz_state_has_apex", alive_p2, "blast_shield"))
        self.assertEqual(alive_p2.get_field("bz_max_grenades"), 10)

        # Friend kept Sapper + PaP Cluster + Portal Grenade, lost Stamin-Up & Blast Shield
        self.assertEqual(gsc2.call(BZ_STATE_MOD, "bz_state_get_class", dead_p2), "sapper")
        self.assertTrue(dead_p2.get_field("bz_pap_cluster"))
        self.assertTrue(dead_p2.get_field("bz_owns_portal_grenade"))
        self.assertEqual(dead_p2.get_field("bz_max_grenades"), 10)
        self.assertFalse(gsc2.call(BZ_STATE_MOD, "bz_state_has_perk", dead_p2, "staminup"))
        self.assertFalse(gsc2.call(BZ_STATE_MOD, "bz_state_has_apex", dead_p2, "blast_shield"))

    def test_four_player_coop_maxed_dvar_length_well_under_waw_limit(self) -> None:
        dvars = _make_enhanced_dvars()
        gsc = GauntletBzRuntime(MOD_ROOT, dvars)
        gsc.level.set_field("script", "nazi_zombie_factory")
        gsc.call(BZ_HOOKS_MOD, "bz_init")

        for idx in range(4):
            p = _make_player(gsc, f"9000000{idx}", f"Player{idx}", score=500000)
            gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", p)
            p.set_field("bz_class", "daredevil")
            p.set_field("bz_pap_knife", True)
            p.set_field("bz_pap_bowie", True)
            p.set_field("bz_pap_cluster", True)
            p.set_field("bz_owns_war_club", True)
            p.set_field("bz_pap_war_club", True)
            p.set_field("bz_owns_bowie", True)
            p.set_field("bz_owns_portal_grenade", True)
            p.set_field("bz_melee_slot", "war_club")
            for pid in ("juggernog", "speed_cola", "double_tap", "quick_revive", "staminup", "mule_kick", "ap"):
                gsc.call(BZ_STATE_MOD, "bz_try_buy_perk", p, pid)
                gsc.call(BZ_STATE_MOD, "bz_try_buy_perk_t2", p, pid)
            for aid in ("double_ammo", "lightweight_heavy", "second_chance", "blast_shield"):
                gsc.call(BZ_STATE_MOD, "bz_try_buy_apex", p, aid)
            gsc.call(BRIDGE_MOD, "snapshot_player_bz_state", p, "nazi_zombie_factory")

        perm_dvar = dvars.get("gauntlet_bz_perm")
        perks_dvar = dvars.get("gauntlet_bz_perks")
        self.assertLess(len(perm_dvar), 350, f"gauntlet_bz_perm too long: {len(perm_dvar)}")
        self.assertLess(len(perks_dvar), 400, f"gauntlet_bz_perks too long: {len(perks_dvar)}")

    def test_gauntlet_perks_juggernog_restore_and_loss_preserve_titan_hp(self) -> None:
        dvars = _make_enhanced_dvars()
        gsc = GauntletBzRuntime(MOD_ROOT, dvars)
        gsc.level.set_field("script", "nazi_zombie_prototype")
        gsc.call(BZ_HOOKS_MOD, "bz_init")
        p = _make_player(gsc, "3001", "TitanPlayer", score=50000)
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", p)
        gsc.call(BZ_STATE_MOD, "bz_try_buy_class", p, "titan")
        gsc.call(BZ_CLASSES_MOD, "bz_class_apply", p, "titan")
        self.assertEqual(p.get_field("maxhealth"), 200)

        # Restoring carried Juggernog via _gauntlet_perks must compose to Titan 320 HP (not 160)
        gsc.call(GAUNTLET_PERKS_MOD, "apply_single_perk_to_player", p, "specialty_armorvest")
        self.assertEqual(p.get_field("maxhealth"), 320)
        self.assertEqual(p.get_field("health"), 320)

        # Losing carried Juggernog via _gauntlet_perks must drop Titan to 200 HP (not 100)
        gsc.call(GAUNTLET_PERKS_MOD, "handle_carried_perk_lost", p, "specialty_armorvest")
        self.assertEqual(p.get_field("maxhealth"), 200)

    def test_clear_run_state_and_stage_clear_menu_close_and_hud_lane_offset(self) -> None:
        dvars = _make_enhanced_dvars()
        dvars.set("gauntlet_bz_perm", "g_1=titan|pk|knife")
        dvars.set("gauntlet_bz_perks", "g_1=jg,su|jg|bs")
        dvars.set("gauntlet_bz_weapons", "g_1=ac:2,cr:0")

        gsc = GauntletBzRuntime(MOD_ROOT, dvars)
        gsc.level.set_field("script", "nazi_zombie_prototype")
        gsc.call(BZ_HOOKS_MOD, "bz_init")

        # HUD lane offset shifts +18px when gauntlet_enabled == 1
        self.assertEqual(gsc.call(BZ_HOOKS_MOD, "bz_get_hud_lane_y", 14), 32)
        self.assertEqual(gsc.call(BZ_HOOKS_MOD, "bz_get_hud_lane_y", 68), 86)

        # Open station menu on a player, verify close_all_bz_station_menus closes it cleanly
        p = _make_player(gsc, "4001", "Shopper", score=10000)
        p.set_field("bz_station_open", True)
        p.set_field("bz_active_station_id", "perks")
        p.set_field("bz_active_station_menu", "bz_station_perks")
        closed = gsc.call(BRIDGE_MOD, "close_all_bz_station_menus")
        self.assertEqual(closed, 1)
        self.assertFalse(p.get_field("bz_station_open"))
        self.assertEqual(p.closed_menus, 1)

        # clear_run_state wipes all Base Zombies ledgers.
        gsc.call(GAUNTLET_STATE_MOD, "clear_run_state")
        self.assertEqual(dvars.get("gauntlet_bz_perm"), "")
        self.assertEqual(dvars.get("gauntlet_bz_perks"), "")
        self.assertEqual(dvars.get("gauntlet_bz_weapons"), "")

    def test_gauntlet_enabled_automatically_couples_enhanced_mode_gates(self) -> None:
        # ADR-0006: launching with gauntlet_enabled=1 alone (bz_* unset or 0) forces Enhanced Mode on.
        dvars = FakeDvarStore()
        dvars.set("gauntlet_enabled", "1")
        dvars.set("bz_enabled", "0")
        dvars.set("bz_perks_enabled", "0")
        dvars.set("bz_classes_enabled", "0")
        dvars.set("bz_pap_enabled", "0")
        dvars.set("bz_elements_enabled", "0")
        gsc = GauntletBzRuntime(MOD_ROOT, dvars)
        # Pure gate predicates evaluate open immediately when gauntlet_enabled=1
        self.assertTrue(gsc.call(BZ_HOOKS_MOD, "bz_enabled"))
        self.assertTrue(gsc.call(BZ_HOOKS_MOD, "bz_perks_enabled"))
        self.assertTrue(gsc.call(BZ_HOOKS_MOD, "bz_classes_enabled"))
        self.assertTrue(gsc.call(BZ_HOOKS_MOD, "bz_pap_enabled"))
        self.assertTrue(gsc.call(BZ_HOOKS_MOD, "bz_elements_enabled"))
        self.assertFalse(gsc.call(BZ_HOOKS_MOD, "bz_companions_enabled"))
        # ensure_bz_dvars() (called on stage/map boot) persists the coupled dvars
        gsc.call(BZ_HOOKS_MOD, "ensure_bz_dvars")
        self.assertEqual(dvars.get("bz_enabled"), "1")
        self.assertEqual(dvars.get("bz_perks_enabled"), "1")
        self.assertEqual(dvars.get("bz_classes_enabled"), "1")
        self.assertEqual(dvars.get("bz_pap_enabled"), "1")
        self.assertEqual(dvars.get("bz_elements_enabled"), "1")
        self.assertEqual(dvars.get("bz_companions_enabled"), "0")

        # Classic Mode (gauntlet_enabled=0, bz_enabled=0) stays strictly disabled.
        classic_dvars = FakeDvarStore()
        classic_dvars.set("gauntlet_enabled", "0")
        classic_gsc = GauntletBzRuntime(MOD_ROOT, classic_dvars)
        classic_gsc.call(BZ_HOOKS_MOD, "ensure_bz_dvars")
        self.assertFalse(classic_gsc.call(BZ_HOOKS_MOD, "bz_enabled"))
        self.assertEqual(classic_dvars.get("bz_enabled"), "0")
        self.assertEqual(classic_dvars.get("bz_perks_enabled"), "0")

    def test_solo_and_coop_three_mode_gauntlet_menu_contracts(self) -> None:
        ui_dir = MOD_ROOT / "ui"
        self.assertEqual(verify_hud_menus.validate_ui_contracts(ui_dir), [])

        gauntlet_inc = (ui_dir / "gauntlet_menus.inc").read_text(encoding="latin1")
        bz_inc = (ui_dir / "bz_menus.inc").read_text(encoding="latin1")
        coop_menu = (ui_dir / "pc_gamesetup_coop.menu").read_text(encoding="latin1")

        # 1. Co-op Host Setup uses a single 3-mode GAME MODE selector (no separate BZ toggle)
        self.assertNotIn("BZ_COOP_SETUP_TOGGLE", bz_inc)
        self.assertNotIn("BZ_COOP_SETUP_TOGGLE", coop_menu)
        toggle_m = re.search(r"#define\s+GAUNTLET_COOP_SETUP_TOGGLE\b.*?(?:\n\n|\Z)", gauntlet_inc, re.DOTALL)
        self.assertIsNotNone(toggle_m)
        for label in ('"Classic Mode" 0', '"Enhanced Mode" 1', '"Zombie Gauntlet" 2'):
            self.assertIn(label, toggle_m.group(0))

        # 2. Retired Classic-vs-Enhanced Gauntlet split macros/labels are completely absent
        for forbidden in ("GAUNTLET_ENHANCED_SOLO_START_ACTION", "ENHANCED GAUNTLET", "Classic Gauntlet"):
            self.assertNotIn(forbidden, gauntlet_inc)

        # 3. Every Run reset / launch macro clears BZ ledgers and shuffled-cycle dvars
        for macro in (
            "GAUNTLET_CLEAR_RUN_STATE_EXEC",
            "GAUNTLET_SOLO_START_ACTION",
            "GAUNTLET_CLASSIC_MODE_ACTION",
            "GAUNTLET_COOP_FRESH_LOCK_ACTION",
        ):
            with self.subTest(macro=macro):
                m = re.search(rf"#define\s+{macro}\b.*?(?:\n\n|\Z)", gauntlet_inc, re.DOTALL)
                self.assertIsNotNone(m, f"Missing {macro}")
                for dvar in (
                    "gauntlet_cycle_order",
                    "gauntlet_start_round",
                    "gauntlet_target_round",
                    "gauntlet_bz_perm",
                    "gauntlet_bz_perks",
                    "gauntlet_bz_weapons",
                ):
                    self.assertIn(f"set {dvar}", m.group(0))

        # 4. Unified GAUNTLET_SOLO_START_ACTION and GAUNTLET_COOP_FRESH_LOCK_ACTION enable full Enhanced Mode
        for macro in ("GAUNTLET_SOLO_START_ACTION", "GAUNTLET_COOP_FRESH_LOCK_ACTION"):
            m = re.search(rf"#define\s+{macro}\b.*?(?:\n\n|\Z)", gauntlet_inc, re.DOTALL)
            self.assertIsNotNone(m)
            for token in (
                "set gauntlet_enabled 1",
                "set bz_enabled 1",
                "set bz_perks_enabled 1",
                "set bz_classes_enabled 1",
                "set bz_pap_enabled 1",
                "set bz_elements_enabled 1",
                "set bz_companions_enabled 0",
            ):
                self.assertIn(token, m.group(0))

        # 5. Staged stock menus expose single ZOMBIE GAUNTLET + single-map Enhanced Mode (zero ENHANCED GAUNTLET)
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
            verify_hud_menus.stage_patched_menus(root / "tools", stage_dir)
            build_mod.apply_bz_menu_patches(stage_dir)

            patched_main = (stage_dir / "ui" / "main.menu").read_text(encoding="latin1")
            patched_levels = (stage_dir / "ui" / "levels.menu").read_text(encoding="latin1")
            self.assertIn("ZOMBIE GAUNTLET", patched_main)
            self.assertIn("ENHANCED MODE", patched_main)
            self.assertNotIn("ENHANCED GAUNTLET", patched_main)
            self.assertIn("ZOMBIE GAUNTLET", patched_levels)
            self.assertIn("ENHANCED: DER RIESE", patched_levels)
            self.assertNotIn("ENHANCED GAUNTLET", patched_levels)


if __name__ == "__main__":
    unittest.main()
