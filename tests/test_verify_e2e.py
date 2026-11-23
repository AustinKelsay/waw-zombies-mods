"""Offline unit tests for scripts/verify_e2e.py quality gate orchestrator."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_e2e  # noqa: E402


ALL_STAGE_IDS = [
    "offline-tests",
    "build-deploy",
    "classic-gauntlet-smoke",
    "solo-cycle1",
    "solo-cycle2",
    "coop-transition",
    "team-wipe",
    "hud-menus",
    "perk-carryover",
]


def _make_fake_repo(tmp_dir: Path, existing_scripts: list[str] | None = None) -> Path:
    """Create a minimal fake repository layout with selected scripts present on disk."""
    scripts_to_create = (
        existing_scripts
        if existing_scripts is not None
        else [
            "scripts/build_mod.py",
            "scripts/smoke_verify.py",
            "scripts/verify_cycle1.py",
            "scripts/verify_cycle2.py",
            "scripts/verify_coop.py",
            "scripts/verify_wipe.py",
            "scripts/verify_hud_menus.py",
            "scripts/verify_perks.py",
        ]
    )
    for rel in scripts_to_create:
        path = tmp_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    return tmp_dir


class TestStagePlanning(unittest.TestCase):
    def test_default_stage_order_and_exact_commands(self) -> None:
        config = verify_e2e.GateConfig(python_executable="python3")
        planned = verify_e2e.plan_stages(config)
        self.assertEqual([s.stage_id for s in planned], ALL_STAGE_IDS)

        cmds = {s.stage_id: s.build_command("python3") for s in planned}
        self.assertEqual(
            cmds["offline-tests"],
            ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"],
        )
        self.assertEqual(
            cmds["build-deploy"],
            ["python3", "scripts/build_mod.py", "--deploy"],
        )
        self.assertEqual(
            cmds["classic-gauntlet-smoke"],
            ["python3", "scripts/smoke_verify.py", "--skip-build", "--modes", "0", "1"],
        )
        self.assertEqual(
            cmds["solo-cycle1"],
            ["python3", "scripts/verify_cycle1.py", "--skip-build"],
        )
        self.assertEqual(
            cmds["solo-cycle2"],
            ["python3", "scripts/verify_cycle2.py", "--skip-build"],
        )
        self.assertEqual(
            cmds["coop-transition"],
            ["python3", "scripts/verify_coop.py", "--skip-build"],
        )
        self.assertEqual(
            cmds["team-wipe"],
            ["python3", "scripts/verify_wipe.py", "--skip-build"],
        )
        self.assertEqual(
            cmds["hud-menus"],
            ["python3", "scripts/verify_hud_menus.py", "--skip-build"],
        )

    def test_offline_only_selects_only_offline_tests(self) -> None:
        planned = verify_e2e.plan_stages(verify_e2e.GateConfig(offline_only=True))
        self.assertEqual([s.stage_id for s in planned], ["offline-tests"])

    def test_skip_build_omits_build_deploy_and_keeps_others(self) -> None:
        planned = verify_e2e.plan_stages(verify_e2e.GateConfig(skip_build=True))
        self.assertEqual(
            [s.stage_id for s in planned],
            [sid for sid in ALL_STAGE_IDS if sid != "build-deploy"],
        )

    def test_only_filters_and_preserves_canonical_order(self) -> None:
        planned = verify_e2e.plan_stages(
            verify_e2e.GateConfig(only=("hud-menus", "solo-cycle1", "build-deploy", "solo-cycle1"))
        )
        self.assertEqual(
            [s.stage_id for s in planned],
            ["build-deploy", "solo-cycle1", "hud-menus"],
        )

    def test_only_rejects_unknown_stage_id(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            verify_e2e.plan_stages(verify_e2e.GateConfig(only=("solo-cycle1", "bogus-stage")))
        self.assertIn("bogus-stage", str(ctx.exception))

    def test_conflicting_filters_producing_empty_plan_raises(self) -> None:
        with self.assertRaises(ValueError):
            verify_e2e.plan_stages(
                verify_e2e.GateConfig(offline_only=True, only=("solo-cycle1",))
            )


class TestMissingScriptsHandling(unittest.TestCase):
    def test_strict_mode_fails_cleanly_when_script_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = _make_fake_repo(
                Path(tmp),
                existing_scripts=[
                    "scripts/build_mod.py",
                    "scripts/smoke_verify.py",
                    "scripts/verify_cycle1.py",
                    "scripts/verify_cycle2.py",
                    # coop, wipe, hud missing
                ],
            )
            executed: list[str] = []

            def fake_runner(stage: verify_e2e.StageSpec, cwd: Path) -> verify_e2e.CommandResult:
                executed.append(stage.stage_id)
                return verify_e2e.CommandResult(exit_code=0, output=f"ok {stage.stage_id}\n")

            buf = io.StringIO()
            report = verify_e2e.run_gate(
                verify_e2e.GateConfig(allow_missing_scripts=False),
                repo_root=fake_repo,
                runner=fake_runner,
                stream=buf,
            )

            self.assertEqual(report.status, "FAILED")
            self.assertEqual(report.exit_code, 1)
            # Ran through solo-cycle2, then failed fast on missing coop-transition
            self.assertEqual(
                executed,
                [
                    "offline-tests",
                    "build-deploy",
                    "classic-gauntlet-smoke",
                    "solo-cycle1",
                    "solo-cycle2",
                ],
            )
            by_id = {r.stage_id: r for r in report.results}
            self.assertEqual(by_id["coop-transition"].status, "FAILED")
            self.assertIn("verify_coop.py", by_id["coop-transition"].failure_reason or "")
            self.assertEqual(by_id["team-wipe"].status, "NOT_RUN")
            self.assertEqual(by_id["hud-menus"].status, "NOT_RUN")
            self.assertTrue(
                any("--allow-missing-scripts" in h for h in by_id["coop-transition"].hints)
            )

    def test_allow_missing_scripts_skips_missing_and_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = _make_fake_repo(
                Path(tmp),
                existing_scripts=[
                    "scripts/build_mod.py",
                    "scripts/smoke_verify.py",
                    "scripts/verify_cycle1.py",
                    "scripts/verify_cycle2.py",
                ],
            )
            executed: list[str] = []

            def fake_runner(stage: verify_e2e.StageSpec, cwd: Path) -> verify_e2e.CommandResult:
                executed.append(stage.stage_id)
                return verify_e2e.CommandResult(exit_code=0, output="PASS\n")

            report = verify_e2e.run_gate(
                verify_e2e.GateConfig(allow_missing_scripts=True),
                repo_root=fake_repo,
                runner=fake_runner,
                stream=io.StringIO(),
            )

            self.assertEqual(report.status, "PASSED")
            self.assertEqual(report.exit_code, 0)
            self.assertEqual(
                executed,
                [
                    "offline-tests",
                    "build-deploy",
                    "classic-gauntlet-smoke",
                    "solo-cycle1",
                    "solo-cycle2",
                ],
            )
            by_id = {r.stage_id: r for r in report.results}
            for missing_id in ("coop-transition", "team-wipe", "hud-menus", "perk-carryover"):
                self.assertEqual(by_id[missing_id].status, "SKIPPED")
                self.assertIn("Missing script", by_id[missing_id].skip_reason or "")
            self.assertEqual(
                report.summary_counts(),
                {"total": 9, "passed": 5, "failed": 0, "skipped": 4, "not_run": 0},
            )


class TestExecutionModes(unittest.TestCase):
    def test_fail_fast_stops_immediately_on_first_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = _make_fake_repo(Path(tmp))
            executed: list[str] = []

            def fake_runner(stage: verify_e2e.StageSpec, cwd: Path) -> verify_e2e.CommandResult:
                executed.append(stage.stage_id)
                if stage.stage_id == "classic-gauntlet-smoke":
                    return verify_e2e.CommandResult(
                        exit_code=1,
                        output="ERROR: Exceeded limit of 400 'fx' assets\n",
                    )
                return verify_e2e.CommandResult(exit_code=0, output="ok\n")

            report = verify_e2e.run_gate(
                verify_e2e.GateConfig(continue_on_error=False),
                repo_root=fake_repo,
                runner=fake_runner,
                stream=io.StringIO(),
            )

            self.assertEqual(report.status, "FAILED")
            self.assertEqual(report.exit_code, 1)
            self.assertEqual(
                executed,
                ["offline-tests", "build-deploy", "classic-gauntlet-smoke"],
            )
            by_id = {r.stage_id: r for r in report.results}
            self.assertEqual(by_id["offline-tests"].status, "PASSED")
            self.assertEqual(by_id["build-deploy"].status, "PASSED")
            self.assertEqual(by_id["classic-gauntlet-smoke"].status, "FAILED")
            self.assertEqual(by_id["solo-cycle1"].status, "NOT_RUN")
            self.assertEqual(by_id["hud-menus"].status, "NOT_RUN")
            self.assertEqual(by_id["perk-carryover"].status, "NOT_RUN")
            self.assertEqual(
                report.summary_counts(),
                {"total": 9, "passed": 2, "failed": 1, "skipped": 0, "not_run": 6},
            )

    def test_continue_on_error_runs_all_remaining_stages_and_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = _make_fake_repo(Path(tmp))
            executed: list[str] = []

            def fake_runner(stage: verify_e2e.StageSpec, cwd: Path) -> verify_e2e.CommandResult:
                executed.append(stage.stage_id)
                if stage.stage_id in ("solo-cycle1", "team-wipe"):
                    return verify_e2e.CommandResult(
                        exit_code=2,
                        output="******* script compile error *******\n",
                    )
                return verify_e2e.CommandResult(exit_code=0, output="ok\n")

            report = verify_e2e.run_gate(
                verify_e2e.GateConfig(continue_on_error=True),
                repo_root=fake_repo,
                runner=fake_runner,
                stream=io.StringIO(),
            )

            self.assertEqual(report.status, "FAILED")
            self.assertEqual(report.exit_code, 1)
            self.assertEqual(executed, ALL_STAGE_IDS)
            self.assertEqual(
                report.summary_counts(),
                {"total": 9, "passed": 7, "failed": 2, "skipped": 0, "not_run": 0},
            )


class TestReportingAndCLI(unittest.TestCase):
    def test_json_report_schema_and_summary_table_formatting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = _make_fake_repo(Path(tmp))
            report_path = Path(tmp) / "reports" / "e2e_report.json"

            ticks = iter([100.0, 100.0, 101.25, 101.25, 104.75, 104.75])

            def fake_clock() -> float:
                return next(ticks)

            def fake_runner(stage: verify_e2e.StageSpec, cwd: Path) -> verify_e2e.CommandResult:
                if stage.stage_id == "solo-cycle1":
                    return verify_e2e.CommandResult(
                        exit_code=1,
                        output="FileNotFoundError: [Errno 2] No such file or directory: 'Xvfb'\n",
                    )
                return verify_e2e.CommandResult(exit_code=0, output="Ran 42 tests\nOK\n")

            buf = io.StringIO()
            rc = verify_e2e.main(
                [
                    "--only",
                    "offline-tests",
                    "solo-cycle1",
                    "--json-report",
                    str(report_path),
                ],
                repo_root=fake_repo,
                runner=fake_runner,
                stream=buf,
                clock=fake_clock,
            )

            self.assertEqual(rc, 1)
            self.assertTrue(report_path.is_file())

            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["status"], "FAILED")
            self.assertEqual(payload["exit_code"], 1)
            self.assertIn("started_at", payload)
            self.assertIn("finished_at", payload)
            self.assertIsInstance(payload["total_duration_s"], (int, float))
            self.assertEqual(
                payload["summary"],
                {"total": 2, "passed": 1, "failed": 1, "skipped": 0, "not_run": 0},
            )
            self.assertEqual(len(payload["stages"]), 2)
            self.assertEqual(payload["stages"][0]["stage_id"], "offline-tests")
            self.assertEqual(payload["stages"][0]["status"], "PASSED")
            self.assertAlmostEqual(payload["stages"][0]["duration_s"], 1.25, places=2)
            self.assertEqual(payload["stages"][1]["stage_id"], "solo-cycle1")
            self.assertEqual(payload["stages"][1]["status"], "FAILED")
            self.assertEqual(payload["stages"][1]["exit_code"], 1)
            self.assertAlmostEqual(payload["stages"][1]["duration_s"], 3.5, places=2)
            self.assertTrue(any("Xvfb" in h for h in payload["stages"][1]["hints"]))
            self.assertIn("Xvfb", payload["stages"][1]["output_tail"])

            rendered = buf.getvalue()
            self.assertIn("Zombie Gauntlet E2E Verification Summary", rendered)
            self.assertIn("offline-tests", rendered)
            self.assertIn("PASSED", rendered)
            self.assertIn("solo-cycle1", rendered)
            self.assertIn("FAILED", rendered)
            self.assertIn("Troubleshooting Hints", rendered)
            self.assertIn("Xvfb", rendered)

    def test_list_stages_prints_all_stages_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = _make_fake_repo(
                Path(tmp),
                existing_scripts=["scripts/build_mod.py", "scripts/smoke_verify.py"],
            )
            buf = io.StringIO()
            rc = verify_e2e.main(
                ["--list-stages"],
                repo_root=fake_repo,
                stream=buf,
            )
            self.assertEqual(rc, 0)
            output = buf.getvalue()
            for stage_id in ALL_STAGE_IDS:
                self.assertIn(stage_id, output)
            self.assertIn("--modes 0 1", output)
            self.assertIn("missing", output.lower())

    def test_cli_offline_only_and_skip_build_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = _make_fake_repo(Path(tmp))
            seen: list[str] = []

            def fake_runner(stage: verify_e2e.StageSpec, cwd: Path) -> verify_e2e.CommandResult:
                seen.append(stage.stage_id)
                return verify_e2e.CommandResult(exit_code=0, output="ok\n")

            rc_offline = verify_e2e.main(
                ["--offline-only"],
                repo_root=fake_repo,
                runner=fake_runner,
                stream=io.StringIO(),
            )
            self.assertEqual(rc_offline, 0)
            self.assertEqual(seen, ["offline-tests"])

            seen.clear()
            rc_skip = verify_e2e.main(
                ["--skip-build"],
                repo_root=fake_repo,
                runner=fake_runner,
                stream=io.StringIO(),
            )
            self.assertEqual(rc_skip, 0)
            self.assertNotIn("build-deploy", seen)
            self.assertEqual(len(seen), 8)


class TestFailureDiagnosis(unittest.TestCase):
    def test_diagnose_missing_xvfb(self) -> None:
        hints = verify_e2e.diagnose_failure(
            "classic-gauntlet-smoke",
            "FileNotFoundError: [Errno 2] No such file or directory: 'Xvfb'",
        )
        self.assertTrue(any("Xvfb" in h and "xfwm4" in h for h in hints))

    def test_diagnose_codwaw_mod_ff_lock(self) -> None:
        hints = verify_e2e.diagnose_failure(
            "build-deploy",
            "PermissionError: [Errno 13] Permission denied: '.../mods/waw_gauntlet/mod.ff'",
        )
        self.assertTrue(any("CoDWaW.exe" in h and "wineserver" in h for h in hints))

    def test_diagnose_400_fx_limit_exceeded(self) -> None:
        hints = verify_e2e.diagnose_failure(
            "classic-gauntlet-smoke",
            "ERROR: 400-FX asset limit exceeded: Exceeded limit of 400 'fx' assets",
        )
        self.assertTrue(any("400-FX" in h and "mod.csv" in h for h in hints))

    def test_diagnose_gsc_compile_and_foreach_error(self) -> None:
        hints = verify_e2e.diagnose_failure(
            "solo-cycle1",
            "******* script compile error *******\nbad syntax near foreach\n",
        )
        self.assertTrue(any("GSC" in h and "foreach" in h for h in hints))

    def test_diagnose_missing_playtest_prefix(self) -> None:
        hints = verify_e2e.diagnose_failure(
            "solo-cycle2",
            "ERROR: Playtest AppData folder missing: /home/plebdev/Games/waw-zombies-dev/playtest/pfx/...",
        )
        self.assertTrue(any("playtest" in h.lower() and "--offline-only" in h for h in hints))

    def test_diagnose_missing_script(self) -> None:
        hints = verify_e2e.diagnose_failure(
            "coop-transition",
            "Required verification script not found: scripts/verify_coop.py",
        )
        self.assertTrue(any("--allow-missing-scripts" in h for h in hints))


if __name__ == "__main__":
    unittest.main()
