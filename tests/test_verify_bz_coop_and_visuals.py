"""Offline contracts for the gated Base Zombies live verification scenarios."""

from __future__ import annotations

import hashlib
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import verify_bz_coop_and_visuals as verifier  # noqa: E402
from tests.gsc_runtime import FakeDvarStore  # noqa: E402
from tests.test_bz_hooks_and_build import BZ_HOOKS_MOD, BzGscRuntime, FakeEntity  # noqa: E402

COOP_LOG = """Loading fastfile 'mod'
dvar set bz_event BZ_EVENT|BUILD_PARITY|build_id=0.5.0-dev;player=Host;map=nazi_zombie_factory
dvar set bz_event BZ_EVENT|PAP_DOUBLE_UPGRADE|map=nazi_zombie_factory;weapon=zombie_colt_upgraded;console=native
dvar set bz_event BZ_EVENT|BZ_COOP_SELFTEST_PASS|map=nazi_zombie_factory;checks=10;build_id=0.5.0-dev;dog_rate=0.55
"""


class TestCoopAnalyzer(unittest.TestCase):
    def test_accepts_build_parity_native_purchase_and_passing_dog_checks(self) -> None:
        _, errors = verifier.analyze_bz_coop_selftest_log(COOP_LOG)
        self.assertEqual(errors, [])

    def test_rejects_missing_parity_non_native_purchase_and_selftest_failure(self) -> None:
        cases = (
            (COOP_LOG.replace("BUILD_PARITY", "IGNORED"), "BUILD_PARITY"),
            (
                COOP_LOG + "BZ_EVENT|BUILD_PARITY_MISMATCH|host=0.5.0-dev;client=0.5.0-old\n",
                "BUILD_PARITY_MISMATCH",
            ),
            (
                COOP_LOG + "BZ_EVENT|BUILD_PARITY|version=0.5.0;player=Guest;map=nazi_zombie_factory\n",
                "missing build_id",
            ),
            (COOP_LOG.replace("checks=10;build_id=0.5.0-dev", "checks=10;build_id=0.5.0-different"), "Conflicting build_id"),
            (
                COOP_LOG
                + "BZ_EVENT|BUILD_PARITY|build_id=0.5.0-other;player=Client;map=nazi_zombie_factory\n",
                "Conflicting BUILD_PARITY",
            ),
            (COOP_LOG.replace("console=native", "console=station"), "console=native"),
            (COOP_LOG + "BZ_EVENT|BZ_COOP_SELFTEST_FAIL|reasons=dog_floor\n", "dog_floor"),
            (COOP_LOG.replace("Loading fastfile 'mod'", ""), "mod.ff"),
        )
        for log, expected in cases:
            with self.subTest(expected=expected):
                _, errors = verifier.analyze_bz_coop_selftest_log(log)
                self.assertTrue(any(expected in error for error in errors), errors)


GAUNTLET_LOG = """Loading fastfile 'mod'
GAUNTLET_EVENT|STAGE_INIT|cycle=1;stage=1;map=nazi_zombie_prototype;run_id=run_10
BZ_EVENT|GAUNTLET_BZ_SEEDED|map=nazi_zombie_prototype;class=titan;weapons=2
BZ_EVENT|GAUNTLET_BZ_SAVED|player=host;map=nazi_zombie_prototype;perm=titan|wc,pwc|war_club;perks=su,mk|-|-
GAUNTLET_EVENT|STAGE_CLEAR|cycle=1;stage=1;map=nazi_zombie_prototype;next_map=nazi_zombie_asylum
GAUNTLET_EVENT|STAGE_TRANSITION|mode=solo;next_map=nazi_zombie_asylum;next_cycle=1;next_stage=2
GAUNTLET_EVENT|STAGE_INIT|cycle=1;stage=2;map=nazi_zombie_asylum;run_id=run_10
BZ_EVENT|GAUNTLET_BZ_RESTORED|player=host;map=nazi_zombie_asylum;class=titan;t1=2;t2=0;apex=0;war_club=1;pap_war_club=1;melee_slot=war_club
"""


class TestEnhancedGauntletAnalyzer(unittest.TestCase):
    def test_accepts_seed_snapshot_transition_and_restore(self) -> None:
        _, errors = verifier.analyze_enhanced_gauntlet_log(GAUNTLET_LOG)
        self.assertEqual(errors, [])

    def test_rejects_empty_snapshot_missing_restore_and_wrong_transition(self) -> None:
        cases = (
            (GAUNTLET_LOG.replace("perm=titan|wc,pwc|war_club", "perm=none"), "GAUNTLET_BZ_SAVED"),
            (GAUNTLET_LOG.replace("perm=titan|wc,pwc|war_club", "perm=titan|-|knife"), "GAUNTLET_BZ_SAVED"),
            (GAUNTLET_LOG.replace("perm=titan|wc,pwc|war_club", "perm=titan|wc|war_club"), "GAUNTLET_BZ_SAVED"),
            (GAUNTLET_LOG.replace("t1=2", "t1=0"), "GAUNTLET_BZ_RESTORED"),
            (GAUNTLET_LOG.replace("pap_war_club=1", "pap_war_club=0"), "GAUNTLET_BZ_RESTORED"),
            (GAUNTLET_LOG.replace("melee_slot=war_club", "melee_slot=knife"), "GAUNTLET_BZ_RESTORED"),
            (GAUNTLET_LOG.replace("GAUNTLET_BZ_RESTORED", "IGNORED"), "GAUNTLET_BZ_RESTORED"),
            (GAUNTLET_LOG.replace("STAGE_TRANSITION|mode=solo;next_map=nazi_zombie_asylum",
                                  "STAGE_TRANSITION|mode=solo;next_map=nazi_zombie_sumpf"), "STAGE_TRANSITION"),
        )
        for log, expected in cases:
            with self.subTest(expected=expected):
                _, errors = verifier.analyze_enhanced_gauntlet_log(log)
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_restore_telemetry_reports_applied_state_when_destination_gates_disabled(self) -> None:
        dvars = FakeDvarStore()
        dvars.set("bz_enabled", "1")
        dvars.set("bz_perks_enabled", "1")
        dvars.set("bz_classes_enabled", "0")
        dvars.set("bz_pap_enabled", "1")
        dvars.set("bz_elements_enabled", "0")
        dvars.set("gauntlet_bz_perm", "n_host=titan|wc,pwc|war_club")
        dvars.set("gauntlet_bz_perks", "n_host=su,mk|-|-")
        runtime = BzGscRuntime(REPO_ROOT / "mod", dvars)
        runtime.level.set_field("script", "nazi_zombie_asylum")
        host = FakeEntity("Host", ent_num=0)
        runtime.players.append(host)
        runtime.call(BZ_HOOKS_MOD, "bz_init")
        runtime.call(r"maps\_bz_gauntlet_bridge", "restore_player_bz_state", host, "nazi_zombie_asylum")

        restored = [ev for ev in runtime.emitted_events if ev.startswith("BZ_EVENT|GAUNTLET_BZ_RESTORED|")]
        self.assertEqual(len(restored), 1)
        self.assertIn("class=none;", restored[0])
        self.assertIn("war_club=0;", restored[0])
        self.assertIn("pap_war_club=0;", restored[0])
        self.assertIn("melee_slot=knife", restored[0])


class TestVisualTourAnalyzer(unittest.TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.out_dir = Path(directory.name)

    def make_tour(self, slug: str, phases: list[str], frozen: bool = False):
        log = ["Loading fastfile 'mod'"]
        frames = []
        for index, phase in enumerate(phases):
            game_time = 2000 + index * 1000
            log.append(f"dvar set bz_event BZ_EVENT|VISUAL_TOUR_PHASE|phase={phase};t={game_time}")
            path = self.out_dir / f"{phase}.png"
            img = b"fixed screenshot" if frozen else phase.encode("ascii")
            path.write_bytes(img)
            frames.append(verifier.CapturedFrame(phase, path, hashlib.sha256(img).hexdigest(), game_time))
        log.append(f"BZ_EVENT|VISUAL_TOUR_DONE|map=nazi_zombie_{slug};phases={len(phases)}")
        return "\n".join(log), frames

    def test_accepts_all_seventeen_factory_capture_phases(self) -> None:
        phases = ["factory_perks_prompt", "factory_class_prompt", "factory_arsenal_prompt"]
        phases += [f"{weapon}_{state}" for weapon in ("acid", "cryo", "crossbow", "boomerang")
                   for state in ("idle", "active", "post")]
        phases += ["native_pap_prompt", "native_pap_ii_badge"]
        log, frames = self.make_tour("factory", phases)
        _, errors = verifier.analyze_visual_tour_result(log, frames)
        self.assertEqual(errors, [])

    def test_accepts_four_station_phases_on_other_stock_maps(self) -> None:
        for slug in ("prototype", "asylum", "sumpf"):
            with self.subTest(map=slug):
                phases = [
                    f"{slug}_perks_prompt",
                    f"{slug}_class_prompt",
                    f"{slug}_arsenal_prompt",
                    f"{slug}_pap_prompt",
                ]
                log, frames = self.make_tour(slug, phases)
                _, errors = verifier.analyze_visual_tour_result(log, frames)
                self.assertEqual(errors, [])

    def test_rejects_frozen_tour(self) -> None:
        phases = [
            "asylum_perks_prompt",
            "asylum_class_prompt",
            "asylum_arsenal_prompt",
            "asylum_pap_prompt",
        ]
        log, frames = self.make_tour("asylum", phases, frozen=True)
        _, errors = verifier.analyze_visual_tour_result(log, frames)
        self.assertTrue(any("frozen" in error for error in errors), errors)

    def test_rejects_missing_phase_empty_png_and_missing_done(self) -> None:
        phases = [
            "sumpf_perks_prompt",
            "sumpf_class_prompt",
            "sumpf_arsenal_prompt",
            "sumpf_pap_prompt",
        ]
        log, frames = self.make_tour("sumpf", phases)
        frames[0].path.write_bytes(b"")
        _, errors = verifier.analyze_visual_tour_result(log, frames[:3])
        self.assertTrue(any("sumpf_pap_prompt" in error for error in errors), errors)
        self.assertTrue(any("empty" in error for error in errors), errors)
        _, errors = verifier.analyze_visual_tour_result(log.replace("VISUAL_TOUR_DONE", "IGNORED"), frames)
        self.assertTrue(any("VISUAL_TOUR_DONE" in error for error in errors), errors)

    def test_all_analyzers_reject_engine_errors(self) -> None:
        phases = [
            "prototype_perks_prompt",
            "prototype_class_prompt",
            "prototype_arsenal_prompt",
            "prototype_pap_prompt",
        ]
        visual_log, frames = self.make_tour("prototype", phases)
        for suffix in ("Error: script runtime error", "Exceeded limit of 400 'fx' assets", "Fatal error"):
            with self.subTest(error=suffix):
                for result in (
                    verifier.analyze_bz_coop_selftest_log(COOP_LOG + "\n" + suffix),
                    verifier.analyze_enhanced_gauntlet_log(GAUNTLET_LOG + "\n" + suffix),
                    verifier.analyze_visual_tour_result(visual_log + "\n" + suffix, frames),
                ):
                    self.assertTrue(any(suffix in error for error in result[1]), result[1])

    def test_capture_visuals_alias_and_missing_dialog_responder_error(self) -> None:
        import builtins
        from threading import Event

        with patch.object(verifier.shutil, "which", return_value=None), patch.object(
            verifier.importlib.util, "find_spec", return_value=None
        ):
            with self.assertRaises(RuntimeError):
                verifier.require_dialog_responder()

        real_import = builtins.__import__

        def block_xlib(name, *args, **kwargs):
            if name.split(".")[0] == "Xlib":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        with patch.object(verifier.shutil, "which", return_value=None), patch(
            "builtins.__import__", side_effect=block_xlib
        ):
            with self.assertRaises(RuntimeError):
                verifier.dismiss_optimal_settings(":121", Event())

        # Verify --capture-visuals is accepted by CLI argparse (fails at preflight, not exit code 2).
        with patch.object(verifier.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                verifier.main(["--capture-visuals", "/tmp/unused_bz_visuals"])
            self.assertEqual(ctx.exception.code, 1)


class TestVisualCapture(unittest.TestCase):
    def test_tails_complete_phase_lines_once_and_captures_from_the_requested_display(self) -> None:
        first = "BZ_EVENT|VISUAL_TOUR_PHASE|phase=prototype_arsenal_prompt;t=2500"
        second = "BZ_EVENT|VISUAL_TOUR_PHASE|phase=prototype_pap_prompt;t=4000"

        def fake_import(cmd, *, env, **_):
            self.assertEqual(env["DISPLAY"], ":121")
            self.assertEqual(cmd[:3], ["import", "-window", "root"])
            Path(cmd[-1]).write_bytes(Path(cmd[-1]).stem.encode("ascii"))

        with TemporaryDirectory() as directory, patch.object(
            verifier.subprocess, "run", side_effect=fake_import,
        ) as run:
            capture = verifier.VisualCapture("prototype", Path(directory), 121)
            capture(first)
            self.assertEqual(run.call_count, 0)
            capture(f"{first}\n")
            self.assertEqual(run.call_count, 1)
            capture(f"{first}\n{first}\n{second}\n")
            self.assertEqual(run.call_count, 2)
            self.assertEqual(
                [(frame.phase, frame.game_t_ms) for frame in capture.frames],
                [("prototype_arsenal_prompt", 2500), ("prototype_pap_prompt", 4000)],
            )
            self.assertEqual(capture.errors, [])


class TestLiveHookGates(unittest.TestCase):
    HOOKS = {
        "bz_test_coop_selftest": "bz_run_coop_selftest",
        "bz_test_visual_tour": "bz_run_visual_tour",
        "bz_test_gauntlet_seed": "bz_run_gauntlet_seed",
    }

    def test_init_threads_only_the_explicitly_enabled_scenario(self) -> None:
        for dvar, expected_thread in self.HOOKS.items():
            for bz_enabled, value in (("0", "1"), ("1", ""), ("1", "2"), ("1", "1")):
                with self.subTest(dvar=dvar, enabled=bz_enabled, value=value):
                    dvars = FakeDvarStore()
                    dvars.set("bz_enabled", bz_enabled)
                    dvars.set("gauntlet_enabled", "1")
                    dvars.set(dvar, value)
                    runtime = BzGscRuntime(REPO_ROOT / "mod", dvars)
                    runtime.level.set_field("script", "nazi_zombie_prototype")
                    runtime.call(BZ_HOOKS_MOD, "bz_init")
                    launched = [name for _, name, _ in runtime._threads if name in self.HOOKS.values()]
                    self.assertEqual(launched, [expected_thread] if (bz_enabled, value) == ("1", "1") else [])

    def test_seed_requires_enhanced_gauntlet_on_nacht(self) -> None:
        for slug, gauntlet in (("prototype", "0"), ("asylum", "1")):
            with self.subTest(map=slug, gauntlet=gauntlet):
                dvars = FakeDvarStore()
                dvars.set("bz_enabled", "1")
                dvars.set("gauntlet_enabled", gauntlet)
                dvars.set("bz_test_gauntlet_seed", "1")
                runtime = BzGscRuntime(REPO_ROOT / "mod", dvars)
                runtime.level.set_field("script", f"nazi_zombie_{slug}")
                runtime.call(BZ_HOOKS_MOD, "bz_init")
                self.assertNotIn("bz_run_gauntlet_seed", [name for _, name, _ in runtime._threads])

    def test_seed_loadout_populates_real_bridge_records(self) -> None:
        dvars = FakeDvarStore()
        for name in ("bz_enabled", "bz_test_gauntlet_seed", "gauntlet_enabled",
                     "bz_perks_enabled", "bz_classes_enabled", "bz_pap_enabled", "bz_elements_enabled"):
            dvars.set(name, "1")
        runtime = BzGscRuntime(REPO_ROOT / "mod", dvars)
        runtime.level.set_field("script", "nazi_zombie_prototype")
        host = FakeEntity("Host", ent_num=0)
        host.set_field("gauntlet_points_applied", True)
        runtime.players.append(host)
        runtime.call(BZ_HOOKS_MOD, "bz_init")
        runtime.call(BZ_HOOKS_MOD, "bz_on_player_spawned", host)
        runtime.call(BZ_HOOKS_MOD, "bz_run_gauntlet_seed")

        bridge = r"maps\_bz_gauntlet_bridge"
        self.assertEqual(runtime.call(bridge, "encode_perm_record", host), "titan|wc,pwc|war_club")
        self.assertEqual(runtime.call(bridge, "encode_perks_record", host), "su,mk|-|-")
        self.assertTrue(runtime.call(r"maps\_bz_state", "bz_state_has_pap_war_club", host))
        self.assertTrue({"bz_acid_sprayer", "bz_cryo_cannon"}.issubset(host.weapons))
        self.assertTrue(runtime.call(r"maps\_bz_state", "bz_state_is_weapon_double_pap", host, "bz_acid_sprayer"))
        self.assertIn("BZ_EVENT|GAUNTLET_BZ_SEEDED|map=nazi_zombie_prototype;class=titan;weapons=2",
                      runtime.emitted_events)

    def test_stock_spawn_dependency_is_gated_and_factory_only(self) -> None:
        source = b'main()\n{\n\tmaps\\_zombiemode::main("spawners");\n}\n'
        for slug in ("factory", "sumpf"):
            patched = verifier.build_mod.inject_map_hooks(
                source, f"nazi_zombie_{slug}", rewire_dogs_module=f"_zombiemode_dogs_bz_{slug}",
            ).decode("ascii")
            with self.subTest(map=slug):
                if slug == "factory":
                    self.assertIn(
                        'if ( maps\\_bz_hooks::bz_enabled() && GetDvarInt( "bz_test_coop_selftest" ) == 1 ) '
                        '{ level.bz_test_coop_spawn_dog = maps\\_zombiemode_dogs_bz_factory::special_dog_spawn; }',
                        patched,
                    )
                else:
                    self.assertNotIn("bz_test_coop_spawn_dog", patched)

    def test_waw17_hooks_keep_waits_in_child_threads_and_teleport_only_players(self) -> None:
        mod_root = REPO_ROOT / "mod"
        path = mod_root / "maps" / "_bz_hooks.gsc"
        source = path.read_text(encoding="ascii")
        runtime = BzGscRuntime(mod_root)
        runtime.load_module(BZ_HOOKS_MOD)
        code = re.sub(r"//[^\n]*", "", source)
        self.assertNotRegex(code, r"\b(?:foreach|NotifyOnCommand)\b")
        self.assertEqual(set(re.findall(r"\b(\w+)\s+SetOrigin\s*\(", code)), {"p"})

        for match in re.finditer(r"^(bz_(?:test_\w+|run_\w+))\([^\n]*\)\n\{(.*?)^\}", code, re.M | re.S):
            name, body = match.groups()
            if name in self.HOOKS.values():
                self.assertIn('level endon( "end_game" );', body)
                self.assertRegex(code, rf"level thread {name}\(\);")
            elif name.startswith("bz_test_"):
                self.assertNotRegex(body, r"\b(?:wait|waittill|endon)\(")

    def test_enhanced_gauntlet_uses_map_launch_and_bz_scenarios_use_devmap(self) -> None:
        source = (REPO_ROOT / "scripts" / "verify_bz_coop_and_visuals.py").read_text(encoding="utf-8")
        self.assertIn('launch_cmd="+map" if gauntlet else "+devmap"', source)
        p1_source = (REPO_ROOT / "scripts" / "verify_base_zombies_p1.py").read_text(encoding="utf-8")
        self.assertIn('launch_cmd: str = "+devmap"', p1_source)
        self.assertIn("cmd.extend([launch_cmd, map_name])", p1_source)
