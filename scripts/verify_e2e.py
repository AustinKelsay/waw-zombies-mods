#!/usr/bin/env python3
"""Single-command end-to-end verification gate for waw_gauntlet (Zombie Gauntlet).

Orchestrates offline contract tests, mod.ff + waw_gauntlet.iwd build/deploy, and all
in-engine Steam/Proton verification scenarios across the four stock Nazi Zombies maps
with live progress, structured summary reporting, optional JSON output, and actionable
plebdev-ultra failure diagnostics.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence, TextIO

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_TAIL_MAX_LINES = 40
OUTPUT_TAIL_MAX_CHARS = 4000
BZ_COOP_VISUALS_SCRIPT = "scripts/verify_bz_coop_and_visuals.py"
DEFAULT_VISUAL_OUT_DIR = Path(".smoke_logs/bz_coop_and_visuals")


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    name: str
    category: str  # "offline" | "build" | "engine"
    args: tuple[str, ...]
    script_relpath: str | None
    description: str
    optional: bool = False

    def build_command(self, python_executable: str = sys.executable) -> list[str]:
        return [python_executable, *self.args]


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    output: str = ""


@dataclass
class StageResult:
    stage_id: str
    name: str
    category: str
    command: list[str]
    status: str  # "PASSED" | "FAILED" | "SKIPPED" | "NOT_RUN"
    exit_code: int | None
    duration_s: float
    started_at: str | None = None
    finished_at: str | None = None
    script_path: str | None = None
    failure_reason: str | None = None
    skip_reason: str | None = None
    hints: list[str] = field(default_factory=list)
    output_tail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "stage_id": self.stage_id,
            "name": self.name,
            "category": self.category,
            "command": list(self.command),
            "status": self.status,
            "exit_code": self.exit_code,
            "duration_s": round(self.duration_s, 3),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "script_path": self.script_path,
            "failure_reason": self.failure_reason,
            "skip_reason": self.skip_reason,
            "hints": list(self.hints),
            "output_tail": self.output_tail,
        }


@dataclass(frozen=True)
class GateConfig:
    offline_only: bool = False
    skip_build: bool = False
    only: tuple[str, ...] = ()
    continue_on_error: bool = False
    allow_missing_scripts: bool = False
    json_report: Path | None = None
    python_executable: str = sys.executable
    include_visual_tour: bool = False
    visual_out_dir: Path = DEFAULT_VISUAL_OUT_DIR


@dataclass
class GateReport:
    status: str  # "PASSED" | "FAILED"
    exit_code: int
    started_at: str
    finished_at: str
    total_duration_s: float
    config: GateConfig
    results: list[StageResult]

    def summary_counts(self) -> dict[str, int]:
        return {
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.status == "PASSED"),
            "failed": sum(1 for r in self.results if r.status == "FAILED"),
            "skipped": sum(1 for r in self.results if r.status == "SKIPPED"),
            "not_run": sum(1 for r in self.results if r.status == "NOT_RUN"),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "status": self.status,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_duration_s": round(self.total_duration_s, 3),
            "options": {
                "offline_only": self.config.offline_only,
                "skip_build": self.config.skip_build,
                "only": list(self.config.only),
                "include_visual_tour": self.config.include_visual_tour,
                "visual_out_dir": str(self.config.visual_out_dir),
                "continue_on_error": self.config.continue_on_error,
                "allow_missing_scripts": self.config.allow_missing_scripts,
            },
            "summary": self.summary_counts(),
            "stages": [r.to_dict() for r in self.results],
        }


RunnerFn = Callable[[StageSpec, Path], CommandResult]


GATE_STAGES: tuple[StageSpec, ...] = (
    StageSpec(
        stage_id="offline-tests",
        name="Offline contract & unit tests",
        category="offline",
        args=("-m", "unittest", "discover", "-s", "tests", "-v"),
        script_relpath=None,
        description="Run all offline Python contract, rules, persistence, and harness unit tests.",
    ),
    StageSpec(
        stage_id="build-deploy",
        name="Build & deploy mod.ff + .iwd",
        category="build",
        args=("scripts/build_mod.py", "--deploy"),
        script_relpath="scripts/build_mod.py",
        description="Compile waw_gauntlet mod.ff + waw_gauntlet.iwd via linker_pc.exe and deploy.",
    ),
    StageSpec(
        stage_id="classic-gauntlet-smoke",
        name="Classic & Gauntlet 4-map smoke",
        category="engine",
        args=("scripts/smoke_verify.py", "--skip-build", "--modes", "0", "1"),
        script_relpath="scripts/smoke_verify.py",
        description="Boot all 4 stock maps in Classic Mode (0) and Zombie Gauntlet (1) with zero fatal errors.",
    ),
    StageSpec(
        stage_id="solo-cycle1",
        name="Solo Cycle 1 4-map progression",
        category="engine",
        args=("scripts/verify_cycle1.py", "--skip-build"),
        script_relpath="scripts/verify_cycle1.py",
        description="Verify continuous Solo 4-map Cycle 1 progression, points carryover, and Cycle 2 wrap.",
    ),
    StageSpec(
        stage_id="solo-cycle2",
        name="Solo Cycle 2+ scaling & Prep Phase",
        category="engine",
        args=("scripts/verify_cycle2.py", "--skip-build"),
        script_relpath="scripts/verify_cycle2.py",
        description="Verify Cycle 2/3 high-round health/speed scaling, Points Floor vs surplus, and Prep Phase.",
    ),
    StageSpec(
        stage_id="coop-transition",
        name="Co-op Stage Transition & roster",
        category="engine",
        args=("scripts/verify_coop.py", "--skip-build"),
        script_relpath="scripts/verify_coop.py",
        description="Verify lobby-assisted Co-op Stage Transition (SetUINextLevel + exitLevel) and roster recovery.",
    ),
    StageSpec(
        stage_id="team-wipe",
        name="Team wipe & Run Summary reset",
        category="engine",
        args=("scripts/verify_wipe.py", "--skip-build"),
        script_relpath="scripts/verify_wipe.py",
        description="Verify Run Summary emission on team wipe and clean Run state reset for the next Run.",
    ),
    StageSpec(
        stage_id="hud-menus",
        name="Gauntlet HUD & Solo/Co-op menus",
        category="engine",
        args=("scripts/verify_hud_menus.py", "--skip-build"),
        script_relpath="scripts/verify_hud_menus.py",
        description="Verify persistent Gauntlet HUD overlay and Solo / Co-op menu mode entry points.",
    ),
    StageSpec(
        stage_id="perk-carryover",
        name="Cross-map Perk Carryover",
        category="engine",
        args=("scripts/verify_perks.py", "--skip-build"),
        script_relpath="scripts/verify_perks.py",
        description="Verify active perks carry across Stages onto Cycle 2 Nacht der Untoten (ADR-0004) with Classic isolation.",
    ),
    StageSpec(
        stage_id="base-zombies-p1",
        name="Base Zombies Phase 1 Der Riese E2E",
        category="engine",
        args=("scripts/verify_base_zombies_p1.py", "--skip-build"),
        script_relpath="scripts/verify_base_zombies_p1.py",
        description="Verify Der Riese Base Zombies Phase 1 (4 Stations, Perks, 6 Classes, PaP, HUD) and Classic Mode isolation.",
    ),
    StageSpec(
        stage_id="base-zombies-p2",
        name="Base Zombies Phase 2 Der Riese E2E",
        category="engine",
        args=("scripts/verify_base_zombies_p2.py", "--skip-build"),
        script_relpath="scripts/verify_base_zombies_p2.py",
        description="Verify Der Riese Base Zombies Phase 2 (4 cloned weapons, Wunderwaffe HP fix & stun, Flamethrower, Acid, Cryo, War Club, Crossbow, Boomerang, Portal) and Classic Mode isolation.",
    ),
    StageSpec(
        stage_id="base-zombies-p3",
        name="Base Zombies Phase 3 Squad Companions E2E",
        category="engine",
        args=("scripts/verify_base_zombies_p3.py", "--skip-build"),
        script_relpath="scripts/verify_base_zombies_p3.py",
        description="Verify Squad Companions on Der Riese and Nacht (Arsenal hire, per-map stock model, squad cap, teleport catch-up, owner-credited MagicBullet points, cleanup) and Classic Mode isolation.",
    ),
    StageSpec(
        stage_id="bz-coop",
        name="Base Zombies Co-op self-test",
        category="engine",
        args=(BZ_COOP_VISUALS_SCRIPT, "--skip-build", "--mode", "coop"),
        script_relpath=BZ_COOP_VISUALS_SCRIPT,
        description="Verify Base Zombies Co-op behavior on Der Riese.",
    ),
    StageSpec(
        stage_id="enhanced-gauntlet",
        name="Enhanced Gauntlet carryover",
        category="engine",
        args=(BZ_COOP_VISUALS_SCRIPT, "--skip-build", "--mode", "enhanced-gauntlet"),
        script_relpath=BZ_COOP_VISUALS_SCRIPT,
        description="Verify Base Zombies state through four Gauntlet handoffs and Cycle 2 Stage 1 wipe cleanup.",
    ),
    StageSpec(
        stage_id="bz-visual-tour",
        name="Base Zombies visual tour",
        category="engine",
        args=(BZ_COOP_VISUALS_SCRIPT, "--skip-build", "--mode", "visual-tour"),
        script_relpath=BZ_COOP_VISUALS_SCRIPT,
        description="Capture Base Zombies screenshots across all four stock maps.",
        optional=True,
    ),
)


DIAGNOSIS_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"Xvfb|xfwm4|No free X11 display|cannot open display|Timed out waiting for Xvfb",
            re.IGNORECASE,
        ),
        "Headless X11 tooling issue: verify 'Xvfb' and 'xfwm4' are installed on plebdev-ultra, "
        "and remove stale '/tmp/.X11-unix/X*' or '/tmp/.X*-lock' files if displays :110-:159 are exhausted.",
    ),
    (
        re.compile(r"Missing X11 startup-dialog responder|python-xlib|xdotool|No module named ['\"]Xlib", re.IGNORECASE),
        "X11 startup-dialog responder unavailable: install 'xdotool' or make 'python-xlib' "
        "available to the Python interpreter running the gate.",
    ),
    (
        re.compile(r"Missing live verification tools:[^\n]*\bimport\b|['\"]import['\"], ['\"]-window['\"]", re.IGNORECASE),
        "Visual screenshot capture requires ImageMagick's 'import' command on PATH and access to the X11 display.",
    ),
    (
        re.compile(
            r"PermissionError|Permission denied|Text file busy|Device or resource busy|"
            r"sharing violation|being used by another process|Access is denied|"
            r"(?:CoDWaW\.exe.*(?:running|lock))|(?:mod\.ff.*lock)",
            re.IGNORECASE,
        ),
        "File lock / stale WaW process: close any running CoDWaW.exe or Steam session holding "
        "mod.ff/waw_gauntlet.iwd, and kill lingering Wine/Proton processes "
        "(pkill -f CoDWaW.exe; WINEPREFIX=~/Games/waw-zombies-dev/playtest/pfx .../wineserver -k).",
    ),
    (
        re.compile(
            r"Exceeded limit of 400 'fx' assets|400-FX|Exceeded limit of \d+ '[^']+' assets",
            re.IGNORECASE,
        ),
        "WaW 400-FX / asset cap exceeded: keep mod/mod.csv strictly limited to GSC scripts, UI menus, "
        "and localized strings with zero custom FX, weapon, or model assets (see ADR-0003).",
    ),
    (
        re.compile(
            r"script compile error|script runtime error|unknown function|Could not find script|"
            r"bad syntax|\bforeach\b|linker_pc\.exe failed",
            re.IGNORECASE,
        ),
        "GSC script compile/runtime error: inspect the latest '.smoke_logs/*.console.log' and "
        "verify WaW 1.7 GSC syntax (note: 'foreach' is NOT supported in WaW 1.7 — use indexed "
        "'for ( i = 0; i < arr.size; i++ )' loops).",
    ),
    (
        re.compile(
            r"Playtest.*AppData.*missing|World at War AppData folder is missing|"
            r"Expected a playtest AppData folder|Proton launcher not found|Could not locate stock fastfile",
            re.IGNORECASE,
        ),
        "Missing Steam/Proton or playtest prefix prerequisites on this host: check WAW_STEAM_ROOT, "
        "WAW_DEV_ROOT, WAW_PROTON, and '~/Games/waw-zombies-dev/playtest' (with an initialized WaW profile), "
        "or run 'python3 scripts/verify_e2e.py --offline-only' on dev laptops.",
    ),
    (
        re.compile(
            r"--skip-build specified but .* does not exist|Missing built mod artifact",
            re.IGNORECASE,
        ),
        "Built mod artifacts are missing in dist/waw_gauntlet/: run 'python3 scripts/build_mod.py --deploy' "
        "first or re-run without '--skip-build'.",
    ),
    (
        re.compile(
            r"Timed out after|Missing expected event:\s*GAUNTLET_EVENT",
            re.IGNORECASE,
        ),
        "Engine scenario timed out or missed GAUNTLET_EVENT telemetry: inspect the saved log under "
        "'.smoke_logs/', confirm no Safe Mode modal ('__CoDWaW' sentinel) blocked startup, and check for a hung wineserver.",
    ),
    (
        re.compile(
            r"Required verification script not found",
            re.IGNORECASE,
        ),
        "Missing verification script: verify dependent tickets (#6, #7, #8) are merged on this branch, "
        "or pass '--allow-missing-scripts' for incremental verification.",
    ),
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tail_output(output: str) -> str:
    if not output:
        return ""
    lines = output.splitlines()
    tail = "\n".join(lines[-OUTPUT_TAIL_MAX_LINES:])
    if len(tail) > OUTPUT_TAIL_MAX_CHARS:
        tail = tail[-OUTPUT_TAIL_MAX_CHARS:]
    return tail


def _configure_stage(stage: StageSpec, config: GateConfig) -> StageSpec:
    if stage.stage_id == "bz-visual-tour":
        return replace(stage, args=(*stage.args, "--capture-visuals", str(config.visual_out_dir)))
    return stage


def plan_stages(
    config: GateConfig,
    stages: Sequence[StageSpec] = GATE_STAGES,
) -> list[StageSpec]:
    """Resolve the ordered list of stages to execute for the given GateConfig."""
    if config.offline_only and config.include_visual_tour:
        raise ValueError("--offline-only cannot be combined with --include-visual-tour.")

    known_ids = {s.stage_id for s in stages}
    if config.only:
        unknown = [sid for sid in config.only if sid not in known_ids]
        if unknown:
            valid_list = ", ".join(s.stage_id for s in stages)
            raise ValueError(
                f"Unknown stage ID(s): {', '.join(unknown)}. Valid stages: {valid_list}"
            )
        selected_set = set(config.only)
        planned = [s for s in stages if s.stage_id in selected_set]
    else:
        planned = [s for s in stages if not s.optional or config.include_visual_tour]

    if config.offline_only:
        planned = [s for s in planned if s.category == "offline"]

    if config.skip_build:
        planned = [s for s in planned if s.category != "build"]

    if not planned:
        raise ValueError(
            "Stage filters selected 0 stages to run (check --offline-only, --skip-build, and --only)."
        )
    return [_configure_stage(stage, config) for stage in planned]


def diagnose_failure(stage_id: str, output: str) -> list[str]:
    """Return deduplicated, actionable troubleshooting hints for a failed stage."""
    hints: list[str] = []
    for pattern, hint in DIAGNOSIS_RULES:
        if pattern.search(output) and hint not in hints:
            hints.append(hint)

    if not hints:
        if stage_id == "offline-tests":
            hints.append(
                "Offline contract tests failed: re-run 'python3 -m unittest discover -s tests -v' "
                "to inspect the full traceback before running in-engine stages."
            )
        else:
            hints.append(
                f"Stage '{stage_id}' failed: inspect the stage output above and the saved console logs "
                "under '.smoke_logs/' (see docs/verification.md for troubleshooting steps)."
            )
    return hints


def run_subprocess_stage(
    stage: StageSpec,
    repo_root: Path,
    python_executable: str = sys.executable,
    stream: TextIO | None = None,
) -> CommandResult:
    """Run a single stage subprocess in repo_root, streaming live output while buffering it."""
    out_stream = stream if stream is not None else sys.stdout
    cmd = stage.build_command(python_executable)
    captured: list[str] = []
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        msg = f"{type(exc).__name__}: {exc}\n"
        out_stream.write(msg)
        out_stream.flush()
        return CommandResult(exit_code=127, output=msg)

    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            captured.append(line)
            out_stream.write(line)
            out_stream.flush()
    finally:
        proc.stdout.close()
    returncode = proc.wait()
    return CommandResult(exit_code=returncode, output="".join(captured))


def run_gate(
    config: GateConfig,
    repo_root: Path = REPO_ROOT,
    stages: Sequence[StageSpec] = GATE_STAGES,
    runner: RunnerFn | None = None,
    stream: TextIO | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> GateReport:
    """Execute the planned verification stages and return a structured GateReport."""
    out = stream if stream is not None else sys.stdout
    planned = plan_stages(config, stages)
    exec_fn: RunnerFn = (
        runner
        if runner is not None
        else lambda stage, cwd: run_subprocess_stage(
            stage,
            cwd,
            python_executable=config.python_executable,
            stream=out,
        )
    )

    gate_started_at = _utc_now_iso()
    gate_t0 = clock()
    results: list[StageResult] = []
    total = len(planned)
    aborted = False

    for idx, stage in enumerate(planned, start=1):
        cmd = stage.build_command(config.python_executable)
        cmd_display = " ".join(shlex.quote(part) for part in cmd)

        if aborted:
            results.append(
                StageResult(
                    stage_id=stage.stage_id,
                    name=stage.name,
                    category=stage.category,
                    command=cmd,
                    status="NOT_RUN",
                    exit_code=None,
                    duration_s=0.0,
                    script_path=stage.script_relpath,
                    skip_reason="Skipped after prior failure (use --continue-on-error to run remaining stages)",
                )
            )
            continue

        out.write(f"\n[{idx}/{total}] === {stage.stage_id}: {stage.name} ===\n")
        out.write(f"$ {cmd_display}\n")
        out.flush()

        # Verify required script exists on disk before invoking subprocess
        if stage.script_relpath is not None:
            script_abs = repo_root / stage.script_relpath
            if not script_abs.is_file():
                if config.allow_missing_scripts:
                    reason = f"Missing script: {stage.script_relpath} (allowed by --allow-missing-scripts)"
                    out.write(f"    [SKIPPED] {reason}\n")
                    out.flush()
                    results.append(
                        StageResult(
                            stage_id=stage.stage_id,
                            name=stage.name,
                            category=stage.category,
                            command=cmd,
                            status="SKIPPED",
                            exit_code=0,
                            duration_s=0.0,
                            script_path=stage.script_relpath,
                            skip_reason=reason,
                        )
                    )
                    continue

                reason = f"Required verification script not found: {stage.script_relpath}"
                hints = diagnose_failure(stage.stage_id, reason)
                out.write(f"    [FAILED] {reason}\n")
                for hint in hints:
                    out.write(f"    HINT: {hint}\n")
                out.flush()
                results.append(
                    StageResult(
                        stage_id=stage.stage_id,
                        name=stage.name,
                        category=stage.category,
                        command=cmd,
                        status="FAILED",
                        exit_code=127,
                        duration_s=0.0,
                        script_path=stage.script_relpath,
                        failure_reason=reason,
                        hints=hints,
                        output_tail=reason,
                    )
                )
                if not config.continue_on_error:
                    aborted = True
                continue

        stage_started_at = _utc_now_iso()
        stage_t0 = clock()
        cmd_result = exec_fn(stage, repo_root)
        stage_duration = max(0.0, clock() - stage_t0)
        stage_finished_at = _utc_now_iso()

        if cmd_result.exit_code == 0:
            out.write(f"    [PASSED] {stage.stage_id} in {stage_duration:.2f}s\n")
            out.flush()
            results.append(
                StageResult(
                    stage_id=stage.stage_id,
                    name=stage.name,
                    category=stage.category,
                    command=cmd,
                    status="PASSED",
                    exit_code=0,
                    duration_s=stage_duration,
                    started_at=stage_started_at,
                    finished_at=stage_finished_at,
                    script_path=stage.script_relpath,
                    output_tail=_tail_output(cmd_result.output),
                )
            )
        else:
            reason = f"Command exited with code {cmd_result.exit_code}"
            hints = diagnose_failure(stage.stage_id, cmd_result.output)
            out.write(f"    [FAILED] {stage.stage_id} ({reason}) in {stage_duration:.2f}s\n")
            for hint in hints:
                out.write(f"    HINT: {hint}\n")
            out.flush()
            results.append(
                StageResult(
                    stage_id=stage.stage_id,
                    name=stage.name,
                    category=stage.category,
                    command=cmd,
                    status="FAILED",
                    exit_code=cmd_result.exit_code,
                    duration_s=stage_duration,
                    started_at=stage_started_at,
                    finished_at=stage_finished_at,
                    script_path=stage.script_relpath,
                    failure_reason=reason,
                    hints=hints,
                    output_tail=_tail_output(cmd_result.output),
                )
            )
            if not config.continue_on_error:
                aborted = True

    total_duration = max(0.0, clock() - gate_t0)
    gate_finished_at = _utc_now_iso()
    any_failed = any(r.status == "FAILED" for r in results)

    return GateReport(
        status="FAILED" if any_failed else "PASSED",
        exit_code=1 if any_failed else 0,
        started_at=gate_started_at,
        finished_at=gate_finished_at,
        total_duration_s=total_duration,
        config=config,
        results=results,
    )


def format_stage_list(
    stages: Sequence[StageSpec] = GATE_STAGES,
    repo_root: Path = REPO_ROOT,
    python_executable: str = "python3",
) -> str:
    """Format configured gate stages for --list-stages."""
    lines = ["=== Zombie Gauntlet E2E Gate Stages ==="]
    config = GateConfig()
    for idx, stage in enumerate(stages, start=1):
        if stage.script_relpath is None:
            presence = "builtin"
        elif (repo_root / stage.script_relpath).is_file():
            presence = "present"
        else:
            presence = "missing"
        cmd_str = shlex.join(_configure_stage(stage, config).build_command(python_executable))
        optional = " [optional]" if stage.optional else ""
        lines.append(
            f"  {idx}. {stage.stage_id:<22s} [{stage.category:<7s}] [{presence:<7s}]{optional} {cmd_str}"
        )
        lines.append(f"     {stage.description}")
    return "\n".join(lines) + "\n"


def format_summary_table(report: GateReport) -> str:
    """Render a structured pass/fail summary table and troubleshooting hints."""
    lines = ["", "=== Zombie Gauntlet E2E Verification Summary ==="]
    header = f"  {'Stage':<24s} {'Status':<9s} {'Exit':<6s} {'Duration':>9s}  Notes"
    sep = "  " + "-" * (len(header) - 2)
    lines.append(header)
    lines.append(sep)

    for res in report.results:
        exit_str = "-" if res.exit_code is None else str(res.exit_code)
        dur_str = f"{res.duration_s:8.2f}s"
        note = res.failure_reason or res.skip_reason or ""
        lines.append(
            f"  {res.stage_id:<24s} {res.status:<9s} {exit_str:<6s} {dur_str}  {note}".rstrip()
        )

    counts = report.summary_counts()
    lines.append(sep)
    lines.append(
        f"  Overall: [{report.status}] "
        f"passed={counts['passed']}/{counts['total']} "
        f"failed={counts['failed']} skipped={counts['skipped']} not_run={counts['not_run']} "
        f"({report.total_duration_s:.2f}s total)"
    )

    failed_with_hints = [r for r in report.results if r.status == "FAILED" and r.hints]
    if failed_with_hints:
        lines.append("")
        lines.append("=== Troubleshooting Hints ===")
        for res in failed_with_hints:
            lines.append(f"  [{res.stage_id}]")
            for hint in res.hints:
                lines.append(f"    - {hint}")

    return "\n".join(lines) + "\n"


def write_json_report(report: GateReport, path: Path) -> Path:
    """Write structured JSON report to disk, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Single-command end-to-end verification quality gate for waw_gauntlet "
            "(offline tests, mod build/deploy, and all in-engine WaW scenarios)."
        )
    )
    parser.add_argument(
        "--offline-only",
        action="store_true",
        help="Run only offline contract/unit tests (no Steam/Proton/WaW required).",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip build-deploy and assume dist/waw_gauntlet/ artifacts are already built.",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="STAGE",
        default=[],
        help="Run only the selected stage ID(s) in canonical gate order.",
    )
    parser.add_argument(
        "--include-visual-tour",
        action="store_true",
        help="Add the optional Base Zombies visual tour to the default stage selection.",
    )
    parser.add_argument(
        "--visual-out-dir",
        type=Path,
        default=DEFAULT_VISUAL_OUT_DIR,
        metavar="PATH",
        help=f"Write visual tour captures to PATH (default: {DEFAULT_VISUAL_OUT_DIR}).",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue running remaining stages after a failure (still exits non-zero at the end).",
    )
    parser.add_argument(
        "--allow-missing-scripts",
        action="store_true",
        help="Mark stages whose verification script is not yet on disk as SKIPPED instead of FAILED.",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write structured JSON verification report to PATH.",
    )
    parser.add_argument(
        "--list-stages",
        action="store_true",
        help="Print all configured verification gate stages and exit 0.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    runner: RunnerFn | None = None,
    stream: TextIO | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    out = stream if stream is not None else sys.stdout
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.list_stages:
        out.write(format_stage_list(GATE_STAGES, repo_root=repo_root))
        out.flush()
        return 0

    config = GateConfig(
        offline_only=args.offline_only,
        skip_build=args.skip_build,
        only=tuple(args.only),
        continue_on_error=args.continue_on_error,
        allow_missing_scripts=args.allow_missing_scripts,
        json_report=args.json_report,
        python_executable=sys.executable,
        include_visual_tour=args.include_visual_tour,
        visual_out_dir=args.visual_out_dir,
    )

    try:
        report = run_gate(
            config=config,
            repo_root=repo_root,
            runner=runner,
            stream=out,
            clock=clock,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    out.write(format_summary_table(report))
    if config.json_report is not None:
        written = write_json_report(report, config.json_report)
        out.write(f"JSON report written to: {written}\n")
    out.flush()
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
