"""Offline unit tests for scripts/verify_base_zombies_p1.py and Phase 1 HUD lane offset."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
MOD_ROOT = REPO_ROOT / "mod"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_base_zombies_p1 as vb  # noqa: E402
from tests.gsc_runtime import FakeDvarStore  # noqa: E402
from tests.test_bz_hooks_and_build import BzGscRuntime  # noqa: E402


VALID_RUN_A_LOG = """
Loading fastfile 'mod'
      dvar set bz_event BZ_EVENT|BZ_INIT|map=nazi_zombie_factory;perks=1;classes=1;pap=1;elements=0;companions=0
      dvar set bz_event BZ_EVENT|STATION_SPAWN|map=nazi_zombie_factory;station=perks;menu=bz_station_perks;x=-310;y=-240;z=0;paired_native=0
      dvar set bz_event BZ_EVENT|STATION_SPAWN|map=nazi_zombie_factory;station=class;menu=bz_station_class;x=230;y=-200;z=0;paired_native=0
      dvar set bz_event BZ_EVENT|STATION_SPAWN|map=nazi_zombie_factory;station=arsenal;menu=bz_station_arsenal;x=180;y=120;z=0;paired_native=0
      dvar set bz_event BZ_EVENT|PAP_DOUBLE_UPGRADE|player=Host;map=nazi_zombie_factory;weapon=zombie_colt_upgraded;dmg_mult=1.75;ammo_mult=3;stock=240;console=native
      dvar set gauntlet_event GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_factory;gauntlet_enabled=0
      dvar set bz_event BZ_EVENT|BZ_SELFTEST_PASS|map=nazi_zombie_factory;checks=23;stations=3;titan_hp=440;sapper_nades=10;broker_pts=200;broker_box=475;dpap_weapon=zombie_colt_upgraded;assassin_ghost=1
"""

VALID_RUN_B_CLASSIC_LOG = """
Loading fastfile 'mod'
      dvar set gauntlet_event GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_factory;gauntlet_enabled=0
"""


class TestVerifyBaseZombiesP1LogAnalyzers(unittest.TestCase):
    def test_parse_bz_events_extracts_types_and_kv_fields(self) -> None:
        events = vb.parse_bz_events(VALID_RUN_A_LOG)
        self.assertEqual(len(events), 6)
        self.assertEqual(events[0].event_type, "BZ_INIT")
        self.assertEqual(events[0].fields["map"], "nazi_zombie_factory")
        self.assertEqual(events[-1].event_type, "BZ_SELFTEST_PASS")
        self.assertEqual(events[-1].fields["titan_hp"], "440")
        self.assertEqual(events[-1].fields["broker_box"], "475")

    def test_analyze_bz_p1_log_passes_on_valid_run_a(self) -> None:
        events, errors = vb.analyze_bz_p1_log(VALID_RUN_A_LOG)
        self.assertEqual(errors, [])
        self.assertTrue(any(e.event_type == "BZ_SELFTEST_PASS" for e in events))

    def test_analyze_bz_p1_log_rejects_missing_station_or_duplicate_factory_pap(self) -> None:
        broken = VALID_RUN_A_LOG.replace("station=arsenal", "station=other")
        _, errors = vb.analyze_bz_p1_log(broken)
        self.assertTrue(any("station='arsenal'" in err for err in errors))

        dup_pap = (
            VALID_RUN_A_LOG
            + "\ndvar set bz_event BZ_EVENT|STATION_SPAWN|map=nazi_zombie_factory;station=pap;menu=bz_station_pap;x=-130;y=-490;z=68;paired_native=1\n"
        )
        _, dup_errors = vb.analyze_bz_p1_log(dup_pap)
        self.assertTrue(any("pap" in err.lower() for err in dup_errors))

        no_native_dpap = "\n".join(
            line for line in VALID_RUN_A_LOG.splitlines() if "PAP_DOUBLE_UPGRADE" not in line
        )
        _, native_errors = vb.analyze_bz_p1_log(no_native_dpap)
        self.assertTrue(any("console=native" in err for err in native_errors))

    def test_analyze_bz_p1_log_rejects_fatal_400_fx_and_script_runtime_error(self) -> None:
        log_fx = VALID_RUN_A_LOG + "\nERROR: Exceeded limit of 400 'fx' assets\n"
        _, errors_fx = vb.analyze_bz_p1_log(log_fx)
        self.assertTrue(any("400-FX" in err for err in errors_fx))

        log_err = VALID_RUN_A_LOG + "\n******* script runtime error *******\nUnknown weapon name\n"
        _, errors_rt = vb.analyze_bz_p1_log(log_err)
        self.assertTrue(any("Script runtime error" in err for err in errors_rt))

    def test_analyze_bz_p1_log_rejects_selftest_fail_or_missing_pass(self) -> None:
        no_pass = "\n".join(
            line for line in VALID_RUN_A_LOG.splitlines() if "BZ_SELFTEST_PASS" not in line
        )
        _, errors = vb.analyze_bz_p1_log(no_pass)
        self.assertTrue(any("BZ_SELFTEST_PASS" in err for err in errors))

        with_fail = no_pass + "\ndvar set bz_event BZ_EVENT|BZ_SELFTEST_FAIL|map=nazi_zombie_factory;passed=20;failed=1;reasons=class_titan_440hp\n"
        _, errors_fail = vb.analyze_bz_p1_log(with_fail)
        self.assertTrue(any("BZ_SELFTEST_FAIL" in err for err in errors_fail))

    def test_analyze_bz_p1_log_rejects_wrong_selftest_metrics(self) -> None:
        wrong_hp = VALID_RUN_A_LOG.replace("titan_hp=440", "titan_hp=220")
        _, errors = vb.analyze_bz_p1_log(wrong_hp)
        self.assertTrue(any("titan_hp" in err for err in errors))

    def test_analyze_classic_bz_isolation_log_passes_cleanly(self) -> None:
        events, errors = vb.analyze_classic_bz_isolation_log(VALID_RUN_B_CLASSIC_LOG)
        self.assertEqual(events, [])
        self.assertEqual(errors, [])

    def test_analyze_classic_bz_isolation_log_rejects_bz_event_leak(self) -> None:
        leaked = (
            VALID_RUN_B_CLASSIC_LOG
            + "\ndvar set bz_event BZ_EVENT|STATION_SPAWN|map=nazi_zombie_factory;station=perks\n"
        )
        events, errors = vb.analyze_classic_bz_isolation_log(leaked)
        self.assertEqual(len(events), 1)
        self.assertTrue(any("leaked" in err.lower() for err in errors))

    def test_analyze_classic_bz_isolation_log_rejects_missing_mod_loaded(self) -> None:
        _, errors = vb.analyze_classic_bz_isolation_log("Loading fastfile 'mod'\n")
        self.assertTrue(any("MOD_LOADED" in err for err in errors))


class TestBzHudLaneOffsetGsc(unittest.TestCase):
    def test_hud_lane_y_shifts_only_when_gauntlet_enabled(self) -> None:
        dvars = FakeDvarStore()
        dvars.set("gauntlet_enabled", "0")
        gsc = BzGscRuntime(MOD_ROOT, dvars)
        self.assertEqual(gsc.call("maps\\_bz_hooks", "bz_get_hud_lane_y", 14), 14)
        self.assertEqual(gsc.call("maps\\_bz_hooks", "bz_get_hud_lane_y", 32), 32)
        self.assertEqual(gsc.call("maps\\_bz_hooks", "bz_get_hud_lane_y", 50), 50)

        dvars.set("gauntlet_enabled", "1")
        self.assertEqual(gsc.call("maps\\_bz_hooks", "bz_get_hud_lane_y", 14), 32)
        self.assertEqual(gsc.call("maps\\_bz_hooks", "bz_get_hud_lane_y", 32), 50)
        self.assertEqual(gsc.call("maps\\_bz_hooks", "bz_get_hud_lane_y", 50), 68)

    def test_sapper_virtual_grenade_pouch_handles_waw17_4_clip_cap(self) -> None:
        from tests.test_bz_classes import BzClassesRuntime, ClassFakeEntity

        dvars = FakeDvarStore()
        dvars.set("bz_enabled", "1")
        dvars.set("bz_classes_enabled", "1")

        class ClampingClassesRuntime(BzClassesRuntime):
            def _exec_method(self, receiver, method, args, line):
                if method == "setweaponammoclip" and isinstance(receiver, ClassFakeEntity):
                    weap = str(args[0]).lower()
                    val = int(args[1])
                    if weap == "stielhandgranate" and val > 4:
                        val = 4  # Real WaW 1.7 engine clipSize=4 clamp
                    receiver.ammo_clip[weap] = val
                    return None
                return super()._exec_method(receiver, method, args, line)

        gsc = ClampingClassesRuntime(MOD_ROOT, dvars)
        p = ClassFakeEntity(name="SapperReal", ent_num=0)
        p.set_field("score", 50000)
        p.give_weapon("stielhandgranate")
        p.ammo_clip["stielhandgranate"] = 4
        gsc.players = [p]
        gsc.call("maps\\_bz_hooks", "bz_init")

        gsc.call("maps\\_bz_hooks", "bz_on_menu_response", p, "bz_station_class", "buy_class:sapper")
        self.assertEqual(p.ammo_clip["stielhandgranate"], 4)
        self.assertEqual(p.get_field("bz_sapper_grenade_reserve"), 6)
        self.assertEqual(gsc.call("maps\\_bz_classes", "bz_sapper_get_total_grenades", p), 10)

        # Simulate throwing a grenade: engine decrements clip 4 -> 3, watcher tops clip back to 4 from reserve (6 -> 5)
        p.ammo_clip["stielhandgranate"] = 3
        remaining = gsc.call("maps\\_bz_classes", "bz_sapper_on_grenade_thrown", p, "stielhandgranate")
        self.assertEqual(remaining, 9)
        self.assertEqual(p.ammo_clip["stielhandgranate"], 4)
        self.assertEqual(p.get_field("bz_sapper_grenade_reserve"), 5)


if __name__ == "__main__":
    unittest.main()
