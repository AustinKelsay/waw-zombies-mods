"""Offline unit tests for scripts/verify_base_zombies_p2.py log analyzers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_base_zombies_p2 as vb2  # noqa: E402


VALID_P2_RUN_A_LOG = """
Loading fastfile 'mod'
      dvar set bz_event BZ_EVENT|ELEMENTS_BOX_REGISTER|count=4;weapons=bz_acid_sprayer,bz_cryo_cannon,bz_multi_crossbow,bz_blade_boomerang
      dvar set bz_event BZ_EVENT|BZ_INIT|map=nazi_zombie_factory;perks=1;classes=1;pap=1;elements=1;companions=0
      dvar set gauntlet_event GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_factory;gauntlet_enabled=0
      dvar set bz_event BZ_EVENT|ELEM_ACID_PUDDLE|player=Player0;radius=128;duration=6;tick_dmg=25;pap=0;dpap=0;hits=1;active=1;fx=maps/zombie/fx_zombie_light_glow_green
      dvar set bz_event BZ_EVENT|ELEM_CRYO_FREEZE|player=Player0;radius=110;duration=4;pap=0;dpap=0;frozen=1;fx=maps/zombie/fx_zombie_mainframe_steam
      dvar set bz_event BZ_EVENT|ELEM_CRYO_SHATTER|player=Player0;weapon=stielhandgranate;mod=mod_explosive;mult=2.5;fx=maps/zombie/fx_zombie_tesla_shock_secondary
      dvar set bz_event BZ_EVENT|ELEM_FLAME_DOT|player=Player0;damage=4000;close=0;upgraded=0;tick=1;map=nazi_zombie_factory
      dvar set bz_event BZ_EVENT|SPECIAL_WAR_CLUB_SMASH|player=Player0;pap=1;damage=1200;radius=160;cleave_hits=1;knockbacks=1
      dvar set bz_event BZ_EVENT|ELEM_TESLA_STUN|player=Player0;stunned=1;duration=3.5;radius=300;map=nazi_zombie_factory
      dvar set bz_event BZ_EVENT|ELEM_TESLA_SELF_GUARD|player=Player0;damage=110;blocked=0;maxhealth=440;health=330;source=pvp_thread
      dvar set bz_event BZ_EVENT|ELEM_TESLA_SELF_GUARD|player=Player0;damage=110;blocked=1;maxhealth=440;health=440;source=pvp_thread
      dvar set bz_event BZ_EVENT|SPECIAL_CROSSBOW_FIRE|player=Player0;bolts=3;stuck_zombies=0;stuck_world=3;double_pap=0
      dvar set bz_event BZ_EVENT|SPECIAL_CROSSBOW_DETONATE|player=Player0;round=1;damage=650;radius=160;hits=0;double_pap=0;self_immune=1
      dvar set bz_event BZ_EVENT|SPECIAL_BOOMERANG_THROW|player=Player0;model=viewmodel_knife_bowie;range=480;max_pierce=6;damage=350;double_pap=0
      dvar set bz_event BZ_EVENT|SPECIAL_PORTAL_OPEN|player=Player0;map=nazi_zombie_factory;x=10;y=20;z=0;duration=12;charges_left=0;fx=transporter_ambient
      dvar set bz_event BZ_EVENT|SPECIAL_PORTAL_TELEPORT|owner=Player0;target=Player0;x=-50;y=0;z=64
      dvar set bz_event BZ_EVENT|BZ_P2_SELFTEST_PASS|map=nazi_zombie_factory;checks=15;box_weapons=4;primaries=4;titan_tesla_hp=440;acid_brittle_dmg=150;cryo_shatter_dmg=250;xbow_bolts=3;portal_warped=1;cleanup=1
"""

VALID_P2_RUN_B_CLASSIC_LOG = """
Loading fastfile 'mod'
      dvar set gauntlet_event GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_factory;gauntlet_enabled=0
"""


class TestVerifyBaseZombiesP2LogAnalyzers(unittest.TestCase):
    def test_analyze_bz_p2_log_passes_on_valid_run_a(self) -> None:
        events, errors = vb2.analyze_bz_p2_log(VALID_P2_RUN_A_LOG)
        self.assertEqual(errors, [])
        self.assertTrue(any(e.event_type == "BZ_P2_SELFTEST_PASS" for e in events))

    def test_analyze_bz_p2_log_rejects_missing_box_weapon_or_elements_gate(self) -> None:
        broken_gate = VALID_P2_RUN_A_LOG.replace("elements=1", "elements=0")
        _, errs_gate = vb2.analyze_bz_p2_log(broken_gate)
        self.assertTrue(any("elements" in err for err in errs_gate))

        missing_weap = VALID_P2_RUN_A_LOG.replace(",bz_blade_boomerang", "")
        _, errs_weap = vb2.analyze_bz_p2_log(missing_weap)
        self.assertTrue(any("bz_blade_boomerang" in err for err in errs_weap))

    def test_analyze_bz_p2_log_rejects_clobbered_tesla_hp(self) -> None:
        clobbered = VALID_P2_RUN_A_LOG.replace("titan_tesla_hp=440", "titan_tesla_hp=100")
        _, errors = vb2.analyze_bz_p2_log(clobbered)
        self.assertTrue(any("titan_tesla_hp" in err for err in errors))

        clobbered_pvp = VALID_P2_RUN_A_LOG.replace("maxhealth=440", "maxhealth=100")
        _, errors_pvp = vb2.analyze_bz_p2_log(clobbered_pvp)
        self.assertTrue(any("maxhealth=440" in err for err in errors_pvp))

    def test_analyze_bz_p2_log_rejects_fatal_400_fx_and_script_error(self) -> None:
        fx_log = VALID_P2_RUN_A_LOG + "\nERROR: Exceeded limit of 400 'fx' assets\n"
        _, errs_fx = vb2.analyze_bz_p2_log(fx_log)
        self.assertTrue(any("400-FX" in err for err in errs_fx))

        rt_log = VALID_P2_RUN_A_LOG + "\n******* script runtime error *******\nBad model\n"
        _, errs_rt = vb2.analyze_bz_p2_log(rt_log)
        self.assertTrue(any("Script runtime error" in err for err in errs_rt))

    def test_analyze_bz_p2_log_rejects_selftest_fail_or_missing_pass(self) -> None:
        no_pass = "\n".join(
            line for line in VALID_P2_RUN_A_LOG.splitlines() if "BZ_P2_SELFTEST_PASS" not in line
        )
        _, errs = vb2.analyze_bz_p2_log(no_pass)
        self.assertTrue(any("BZ_P2_SELFTEST_PASS" in err for err in errs))

        with_fail = (
            no_pass
            + "\ndvar set bz_event BZ_EVENT|BZ_P2_SELFTEST_FAIL|map=nazi_zombie_factory;passed=12;failed=1;reasons=cryo_freeze_shatter_250\n"
        )
        _, errs_fail = vb2.analyze_bz_p2_log(with_fail)
        self.assertTrue(any("BZ_P2_SELFTEST_FAIL" in err for err in errs_fail))

    def test_analyze_bz_p2_log_rejects_missing_combat_telemetry(self) -> None:
        no_portal = "\n".join(
            line for line in VALID_P2_RUN_A_LOG.splitlines() if "SPECIAL_PORTAL_TELEPORT" not in line
        )
        _, errs = vb2.analyze_bz_p2_log(no_portal)
        self.assertTrue(any("SPECIAL_PORTAL_TELEPORT" in err for err in errs))

    def test_analyze_classic_bz_p2_isolation_log_passes_and_catches_leak(self) -> None:
        events, errors = vb2.analyze_classic_bz_p2_isolation_log(VALID_P2_RUN_B_CLASSIC_LOG)
        self.assertEqual(events, [])
        self.assertEqual(errors, [])

        leaked = (
            VALID_P2_RUN_B_CLASSIC_LOG
            + "\ndvar set bz_event BZ_EVENT|ELEMENTS_BOX_REGISTER|count=4;weapons=bz_acid_sprayer\n"
        )
        leaked_events, leaked_errors = vb2.analyze_classic_bz_p2_isolation_log(leaked)
        self.assertEqual(len(leaked_events), 1)
        self.assertTrue(any("leaked" in err.lower() for err in leaked_errors))


if __name__ == "__main__":
    unittest.main()
