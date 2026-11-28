"""Offline unit tests for scripts/verify_base_zombies_p3.py log analyzers (#113)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_base_zombies_p3 as vb3  # noqa: E402

VALID_P3_FACTORY_LOG = """
Loading fastfile 'mod'
      dvar set bz_event BZ_EVENT|COMPANION_INIT|map=nazi_zombie_factory;cap=4;price=2000;weapon=kar98k
      dvar set bz_event BZ_EVENT|BZ_INIT|map=nazi_zombie_factory;perks=1;classes=1;pap=1;elements=1;companions=1
      dvar set gauntlet_event GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_factory;gauntlet_enabled=0
      dvar set bz_event BZ_EVENT|COMPANION_SPAWN|player=WaveTest;id=1;character=Nikolai;model=char_rus_guard_chernova_zomb;attach=0;squad=2;weapon=kar98k
      dvar set bz_event BZ_EVENT|STATION_PURCHASE|player=WaveTest;menu=bz_station_arsenal;category=companion;item=hire;status=ok;cost=2000;score=48000
      dvar set bz_event BZ_EVENT|COMPANION_WARP|id=1;reason=teleport;dist=62
      dvar set bz_event BZ_EVENT|COMPANION_FIRE|id=1;owner=WaveTest;weapon=kar98k;dist=410
      dvar set bz_event BZ_EVENT|COMPANION_REMOVE|id=1;reason=selftest
      dvar set bz_event BZ_EVENT|BZ_P3_SELFTEST_PASS|map=nazi_zombie_factory;checks=9;model=char_rus_guard_chernova_zomb;cap=3;follow_dist=62;points=40;cleanup=1
"""


class TestVerifyBaseZombiesP3LogAnalyzer(unittest.TestCase):
    def test_valid_factory_log_passes(self) -> None:
        events, errors = vb3.analyze_bz_p3_log(VALID_P3_FACTORY_LOG)
        self.assertEqual(errors, [])
        self.assertTrue(any(e.event_type == "BZ_P3_SELFTEST_PASS" for e in events))

    def test_prototype_expects_marine_body(self) -> None:
        proto = VALID_P3_FACTORY_LOG.replace("nazi_zombie_factory", "nazi_zombie_prototype")
        _, errors = vb3.analyze_bz_p3_log(proto, map_name="nazi_zombie_prototype")
        self.assertTrue(any("char_usa_marine_player_body2_1" in e for e in errors))
        fixed = proto.replace("char_rus_guard_chernova_zomb", "char_usa_marine_player_body2_1")
        self.assertEqual(vb3.analyze_bz_p3_log(fixed, map_name="nazi_zombie_prototype")[1], [])

    def test_rejects_closed_gate_missing_fire_or_zero_points(self) -> None:
        for broken, needle in (
            (VALID_P3_FACTORY_LOG.replace("companions=1", "companions=0"), "companions"),
            (VALID_P3_FACTORY_LOG.replace("COMPANION_FIRE", "COMPANION_IDLE"), "COMPANION_FIRE"),
            (VALID_P3_FACTORY_LOG.replace("points=40", "points=0"), "points"),
            (VALID_P3_FACTORY_LOG.replace("status=ok;cost=2000", "status=gate_disabled;cost=0"), "2000-point"),
        ):
            with self.subTest(needle=needle):
                _, errors = vb3.analyze_bz_p3_log(broken)
                self.assertTrue(any(needle in e for e in errors), errors)

    def test_rejects_selftest_fail_fatal_errors_and_missing_pass(self) -> None:
        failed = VALID_P3_FACTORY_LOG.replace(
            "BZ_P3_SELFTEST_PASS|map=nazi_zombie_factory;checks=9;model=char_rus_guard_chernova_zomb;cap=3;follow_dist=62;points=40;cleanup=1",
            "BZ_P3_SELFTEST_FAIL|map=nazi_zombie_factory;passed=7;failed=1;reasons=teleport_catch_up",
        )
        _, errors = vb3.analyze_bz_p3_log(failed)
        self.assertTrue(any("teleport_catch_up" in e for e in errors))
        self.assertTrue(any("BZ_P3_SELFTEST_PASS" in e for e in errors))

        fatal = VALID_P3_FACTORY_LOG + "\nERROR: Exceeded limit of 400 'fx' assets.\n"
        self.assertNotEqual(vb3.analyze_bz_p3_log(fatal)[1], [])


if __name__ == "__main__":
    unittest.main()
