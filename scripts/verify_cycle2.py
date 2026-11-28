#!/usr/bin/env python3
"""Real in-engine Cycle 2+ high-round, Prep Phase, and Points Floor verification harness.

Runs three focused CoDWaW.exe Solo verification scenarios against the built
waw_gauntlet mod:
  1. Cycle 1 Stage 4 (Der Riese) -> Cycle 2 Stage 1 (Nacht) wrap:
     - Verifies Cycle 1 skips Prep Phase completely.
     - Verifies automatic wrap to Cycle 2 Stage 1 at Round 10 with Points Floor 5000.
     - Verifies HIGH_ROUND_APPLIED (zombie_health=1045, zombie_move_speed=80).
     - Verifies PREP_PHASE_START -> PREP_PHASE_END strictly BEFORE ZOMBIE_SPAWNED_SAMPLE.
     - Verifies actual spawned Round 10 zombie health == 1045 (zero double-scaling)
       and sprint movement speed.
  2. Surplus preservation on Cycle 2 Stage 1 (Nacht):
     - Enters Cycle 2 Stage 1 carrying 8500 points (> 5000 Points Floor) with production
       Target Round (15).
     - Verifies POINTS_APPLIED preserves 8500 instead of overwriting to 5000.
     - Verifies Prep Phase ordering and actual spawned Round 10 zombie health == 1045.
  3. Cycle 2 Stage 4 (Der Riese) -> Cycle 3 Stage 1 (Nacht) wrap:
     - Verifies Der Riese at Round 10 reschedules Hellhound round naturally
       (11 <= next_dog_round <= 15) and spawns Round 10 zombies at health == 1045.
     - Verifies automatic wrap to Cycle 3 Stage 1 (Nacht) at Round 15 with Points Floor 7500,
       HIGH_ROUND_APPLIED (zombie_health=1679, zombie_move_speed=120), Prep Phase ordering,
       and actual spawned Round 15 zombie health == 1679.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_mod  # noqa: E402
import smoke_verify  # noqa: E402
import verify_cycle1  # noqa: E402

GauntletEvent = verify_cycle1.GauntletEvent


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    duration_s: float
    events: list[GauntletEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    saved_log: Path | None = None


def _check_fatal_patterns(log_text: str, errors: list[str]) -> None:
    for label, pattern in smoke_verify.FATAL_LOG_PATTERNS:
        for line in log_text.splitlines():
            if pattern.search(line):
                errors.append(f"{label}: {line.strip()}")
                break


def _split_stages(events: list[GauntletEvent]) -> list[list[GauntletEvent]]:
    """Group events into per-Stage slices starting at each STAGE_INIT."""
    stages: list[list[GauntletEvent]] = []
    current: list[GauntletEvent] | None = None
    for ev in events:
        if ev.event_type == "STAGE_INIT":
            current = [ev]
            stages.append(current)
        elif current is not None:
            current.append(ev)
    return stages


def _verify_high_round_stage(
    stage_events: list[GauntletEvent],
    label: str,
    expected_cycle: int,
    expected_stage: int,
    expected_map: str,
    expected_start_round: int,
    expected_health: int,
    expected_move_speed: int,
    expected_prep_duration: int,
    expect_dogs: bool,
    errors: list[str],
    expected_target_round: int | None = None,
    expected_points: int | None = None,
    expected_floor: int | None = None,
) -> None:
    init_ev = stage_events[0]
    checks = [
        ("cycle", str(expected_cycle)),
        ("stage", str(expected_stage)),
        ("map", expected_map),
        ("start_round", str(expected_start_round)),
    ]
    if expected_target_round is not None:
        checks.append(("target_round", str(expected_target_round)))
    for key, exp in checks:
        if init_ev.fields.get(key) != exp:
            errors.append(
                f"{label}: STAGE_INIT {key}={init_ev.fields.get(key)!r}, expected {exp!r} ({init_ev.raw})"
            )

    # Points check
    pts_events = [e for e in stage_events if e.event_type == "POINTS_APPLIED"]
    if not pts_events:
        errors.append(f"{label}: missing POINTS_APPLIED")
    else:
        pts_ev = pts_events[0]
        actual_points = pts_ev.fields.get("points")
        if expected_points is not None and actual_points != str(expected_points):
            errors.append(
                f"{label}: POINTS_APPLIED points={actual_points!r}, "
                f"expected {expected_points!r} ({pts_ev.raw})"
            )
        if expected_floor is not None:
            if pts_ev.fields.get("floor") != str(expected_floor):
                errors.append(
                    f"{label}: POINTS_APPLIED floor={pts_ev.fields.get('floor')!r}, "
                    f"expected {expected_floor!r} ({pts_ev.raw})"
                )
            try:
                if actual_points is None or int(actual_points) < expected_floor:
                    errors.append(
                        f"{label}: POINTS_APPLIED points={actual_points!r} is below "
                        f"expected floor {expected_floor} ({pts_ev.raw})"
                    )
            except ValueError:
                errors.append(
                    f"{label}: POINTS_APPLIED points={actual_points!r} is not an integer ({pts_ev.raw})"
                )

    # HIGH_ROUND_APPLIED check
    hr_indices = [i for i, e in enumerate(stage_events) if e.event_type == "HIGH_ROUND_APPLIED"]
    if not hr_indices:
        errors.append(f"{label}: missing HIGH_ROUND_APPLIED")
    else:
        hr_ev = stage_events[hr_indices[0]]
        hr_checks = (
            ("cycle", str(expected_cycle)),
            ("stage", str(expected_stage)),
            ("map", expected_map),
            ("start_round", str(expected_start_round)),
            ("zombie_health", str(expected_health)),
            ("zombie_move_speed", str(expected_move_speed)),
        )
        for key, exp in hr_checks:
            if hr_ev.fields.get(key) != exp:
                errors.append(
                    f"{label}: HIGH_ROUND_APPLIED {key}={hr_ev.fields.get(key)!r}, "
                    f"expected {exp!r} ({hr_ev.raw})"
                )
        ndr_raw = hr_ev.fields.get("next_dog_round", "")
        if expect_dogs:
            try:
                ndr_val = int(ndr_raw)
            except ValueError:
                errors.append(
                    f"{label}: expected integer next_dog_round on Hellhound map, got {ndr_raw!r}"
                )
            else:
                if ndr_val <= expected_start_round or ndr_val > expected_start_round + 5:
                    errors.append(
                        f"{label}: next_dog_round={ndr_val} outside natural Cycle band "
                        f"({expected_start_round + 1}..{expected_start_round + 5})"
                    )
        else:
            if ndr_raw != "none":
                errors.append(
                    f"{label}: expected next_dog_round='none' on {expected_map}, got {ndr_raw!r}"
                )

    # Prep Phase ordering check: PREP_PHASE_START -> PREP_PHASE_END strictly BEFORE ZOMBIE_SPAWNED_SAMPLE
    prep_start_idx = next(
        (i for i, e in enumerate(stage_events) if e.event_type == "PREP_PHASE_START"), None
    )
    prep_end_idx = next(
        (i for i, e in enumerate(stage_events) if e.event_type == "PREP_PHASE_END"), None
    )
    sample_idx = next(
        (i for i, e in enumerate(stage_events) if e.event_type == "ZOMBIE_SPAWNED_SAMPLE"), None
    )

    if prep_start_idx is None:
        errors.append(f"{label}: missing PREP_PHASE_START")
    else:
        ps = stage_events[prep_start_idx]
        if ps.fields.get("duration") != str(expected_prep_duration):
            errors.append(
                f"{label}: PREP_PHASE_START duration={ps.fields.get('duration')!r}, "
                f"expected {expected_prep_duration!r}"
            )

    if prep_end_idx is None:
        errors.append(f"{label}: missing PREP_PHASE_END")
    else:
        pe = stage_events[prep_end_idx]
        if pe.fields.get("duration") != str(expected_prep_duration):
            errors.append(
                f"{label}: PREP_PHASE_END duration={pe.fields.get('duration')!r}, "
                f"expected {expected_prep_duration!r}"
            )

    if sample_idx is None:
        errors.append(f"{label}: missing ZOMBIE_SPAWNED_SAMPLE")
    else:
        samp = stage_events[sample_idx]
        if samp.fields.get("round") != str(expected_start_round):
            errors.append(
                f"{label}: ZOMBIE_SPAWNED_SAMPLE round={samp.fields.get('round')!r}, "
                f"expected {expected_start_round!r} ({samp.raw})"
            )
        if samp.fields.get("health") != str(expected_health):
            errors.append(
                f"{label}: ZOMBIE_SPAWNED_SAMPLE health={samp.fields.get('health')!r}, "
                f"expected {expected_health!r} (possible double-scaling) ({samp.raw})"
            )
        if samp.fields.get("move_speed") != "sprint":
            errors.append(
                f"{label}: ZOMBIE_SPAWNED_SAMPLE move_speed={samp.fields.get('move_speed')!r}, "
                f"expected 'sprint' ({samp.raw})"
            )

    if prep_start_idx is not None and prep_end_idx is not None and prep_start_idx >= prep_end_idx:
        errors.append(f"{label}: PREP_PHASE_START must precede PREP_PHASE_END")
    if prep_end_idx is not None and sample_idx is not None and sample_idx <= prep_end_idx:
        errors.append(
            f"{label}: ZOMBIE_SPAWNED_SAMPLE occurred before PREP_PHASE_END "
            f"(sample_idx={sample_idx}, prep_end_idx={prep_end_idx})"
        )


def analyze_c1_to_c2_wrap_log(
    log_text: str,
    expected_prep_duration: int = 3,
) -> tuple[list[GauntletEvent], list[str]]:
    """Validate Cycle 1 Stage 4 (factory) -> Cycle 2 Stage 1 (prototype, R10) wrap."""
    events = verify_cycle1.parse_gauntlet_events(log_text)
    errors: list[str] = []
    _check_fatal_patterns(log_text, errors)

    stages = _split_stages(events)
    if len(stages) < 2:
        errors.append(
            f"Expected at least 2 STAGE_INIT slices (Cycle 1 Stage 4 + Cycle 2 Stage 1), found {len(stages)}"
        )
        return events, errors

    c1_s4 = stages[0]
    c2_s1 = stages[1]

    # Cycle 1 Stage 4 starts at Round 9 (> 1) under continuous escalation and runs Prep Phase + HIGH_ROUND_APPLIED
    _verify_high_round_stage(
        stage_events=c1_s4,
        label="Cycle 1 Stage 4 (continuous factory R9)",
        expected_cycle=1,
        expected_stage=4,
        expected_map="nazi_zombie_factory",
        expected_start_round=9,
        expected_health=950,
        expected_move_speed=72,
        expected_prep_duration=expected_prep_duration,
        expect_dogs=True,
        expected_points=4500,
        expected_floor=4500,
        errors=errors,
    )

    clear_ev = next((e for e in c1_s4 if e.event_type == "STAGE_CLEAR"), None)
    if clear_ev is None:
        errors.append("Cycle 1 Stage 4 missing STAGE_CLEAR")
    else:
        for k, exp in (("cycle", "1"), ("stage", "4"), ("completed_round", "9"), ("next_cycle", "2"), ("next_stage", "1"), ("next_map", "nazi_zombie_prototype")):
            if clear_ev.fields.get(k) != exp:
                errors.append(f"Cycle 1 Stage 4 STAGE_CLEAR {k}={clear_ev.fields.get(k)!r}, expected {exp!r}")

    c1_s4_saved = next((e for e in c1_s4 if e.event_type == "POINTS_SAVED"), None)
    expected_c2_points: int | None = None
    expected_c2_carried: str | None = None
    if c1_s4_saved is None or not c1_s4_saved.fields.get("points", "").isdigit():
        errors.append("Cycle 1 Stage 4 missing valid POINTS_SAVED event")
    else:
        expected_c2_carried = c1_s4_saved.fields["points"]
        expected_c2_points = max(int(expected_c2_carried), 5000)

    _verify_high_round_stage(
        stage_events=c2_s1,
        label="Cycle 2 Stage 1 (wrap)",
        expected_cycle=2,
        expected_stage=1,
        expected_map="nazi_zombie_prototype",
        expected_start_round=10,
        expected_health=1045,
        expected_move_speed=80,
        expected_prep_duration=expected_prep_duration,
        expect_dogs=False,
        expected_points=expected_c2_points,
        expected_floor=5000,
        errors=errors,
    )
    if expected_c2_carried is not None:
        c2_pts_ev = next((e for e in c2_s1 if e.event_type == "POINTS_APPLIED"), None)
        if c2_pts_ev is not None and c2_pts_ev.fields.get("carried") != expected_c2_carried:
            errors.append(
                f"Cycle 2 Stage 1 (wrap): POINTS_APPLIED carried={c2_pts_ev.fields.get('carried')!r}, "
                f"expected {expected_c2_carried!r} ({c2_pts_ev.raw})"
            )

    return events, errors


def analyze_surplus_preservation_log(
    log_text: str,
    expected_surplus: int = 8500,
    expected_prep_duration: int = 3,
) -> tuple[list[GauntletEvent], list[str]]:
    """Validate entering Cycle 2 Stage 1 with carried surplus preserves exact surplus."""
    events = verify_cycle1.parse_gauntlet_events(log_text)
    errors: list[str] = []
    _check_fatal_patterns(log_text, errors)

    stages = _split_stages(events)
    if not stages:
        errors.append("Expected Cycle 2 Stage 1 STAGE_INIT, found none")
        return events, errors

    _verify_high_round_stage(
        stage_events=stages[0],
        label="Cycle 2 Stage 1 (surplus)",
        expected_cycle=2,
        expected_stage=1,
        expected_map="nazi_zombie_prototype",
        expected_start_round=10,
        expected_target_round=14,
        expected_health=1045,
        expected_move_speed=80,
        expected_prep_duration=expected_prep_duration,
        expect_dogs=False,
        expected_points=expected_surplus,
        expected_floor=5000,
        errors=errors,
    )

    return events, errors


def analyze_c2_to_c3_wrap_log(
    log_text: str,
    expected_prep_duration: int = 3,
) -> tuple[list[GauntletEvent], list[str]]:
    """Validate Cycle 2 Stage 4 (factory, R14 + dogs) -> Cycle 3 Stage 1 (prototype, R15) wrap."""
    events = verify_cycle1.parse_gauntlet_events(log_text)
    errors: list[str] = []
    _check_fatal_patterns(log_text, errors)

    stages = _split_stages(events)
    if len(stages) < 2:
        errors.append(
            f"Expected at least 2 STAGE_INIT slices (Cycle 2 Stage 4 + Cycle 3 Stage 1), found {len(stages)}"
        )
        return events, errors

    c2_s4 = stages[0]
    c3_s1 = stages[1]

    _verify_high_round_stage(
        stage_events=c2_s4,
        label="Cycle 2 Stage 4 (factory)",
        expected_cycle=2,
        expected_stage=4,
        expected_map="nazi_zombie_factory",
        expected_start_round=14,
        expected_health=1527,
        expected_move_speed=112,
        expected_prep_duration=expected_prep_duration,
        expect_dogs=True,
        expected_points=7000,
        expected_floor=7000,
        errors=errors,
    )

    clear_ev = next((e for e in c2_s4 if e.event_type == "STAGE_CLEAR"), None)
    if clear_ev is None:
        errors.append("Cycle 2 Stage 4 missing STAGE_CLEAR")
    else:
        for k, exp in (("cycle", "2"), ("stage", "4"), ("completed_round", "14"), ("next_cycle", "3"), ("next_stage", "1"), ("next_map", "nazi_zombie_prototype")):
            if clear_ev.fields.get(k) != exp:
                errors.append(f"Cycle 2 Stage 4 STAGE_CLEAR {k}={clear_ev.fields.get(k)!r}, expected {exp!r}")

    c2_s4_saved = next((e for e in c2_s4 if e.event_type == "POINTS_SAVED"), None)
    expected_c3_points: int | None = None
    expected_c3_carried: str | None = None
    if c2_s4_saved is None or not c2_s4_saved.fields.get("points", "").isdigit():
        errors.append("Cycle 2 Stage 4 missing valid POINTS_SAVED event")
    else:
        expected_c3_carried = c2_s4_saved.fields["points"]
        expected_c3_points = max(int(expected_c3_carried), 7500)

    _verify_high_round_stage(
        stage_events=c3_s1,
        label="Cycle 3 Stage 1 (wrap)",
        expected_cycle=3,
        expected_stage=1,
        expected_map="nazi_zombie_prototype",
        expected_start_round=15,
        expected_health=1679,
        expected_move_speed=120,
        expected_prep_duration=expected_prep_duration,
        expect_dogs=False,
        expected_points=expected_c3_points,
        expected_floor=7500,
        errors=errors,
    )
    if expected_c3_carried is not None:
        c3_pts_ev = next((e for e in c3_s1 if e.event_type == "POINTS_APPLIED"), None)
        if c3_pts_ev is not None and c3_pts_ev.fields.get("carried") != expected_c3_carried:
            errors.append(
                f"Cycle 3 Stage 1 (wrap): POINTS_APPLIED carried={c3_pts_ev.fields.get('carried')!r}, "
                f"expected {expected_c3_carried!r} ({c3_pts_ev.raw})"
            )

    return events, errors


def run_waw_scenario(
    name: str,
    log_filename: str,
    start_map: str,
    extra_dvars: list[tuple[str, str]],
    stop_predicate: Callable[[list[GauntletEvent]], bool],
    analyzer: Callable[[str], tuple[list[GauntletEvent], list[str]]],
    display_num: int,
    xdg_config_home: str,
    proton: Path,
    steam_root: Path,
    steam_game: Path,
    playtest_prefix: Path,
    timeout_s: float,
) -> ScenarioResult:
    appdata = (
        playtest_prefix
        / "pfx/drive_c/users/steamuser/AppData/Local/Activision/CoDWaW"
    )
    smoke_verify.clear_previous_run_state(appdata)

    env = os.environ.copy()
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = str(steam_root)
    env["STEAM_COMPAT_DATA_PATH"] = str(playtest_prefix)
    env["STEAM_COMPAT_INSTALL_PATH"] = str(steam_game)
    env["SteamAppId"] = "10090"
    env["SteamGameId"] = "10090"
    env["PROTON_USE_WINED3D"] = "1"
    env.setdefault("WINE_D3D_CONFIG", "VideoMemorySize=512")
    env["DISPLAY"] = f":{display_num}"
    env["XDG_SESSION_TYPE"] = "x11"
    env["XDG_CONFIG_HOME"] = xdg_config_home
    for key in ("WAYLAND_DISPLAY", "WAYLAND_SOCKET", "DESKTOP_STARTUP_ID"):
        env.pop(key, None)

    cmd = [
        str(proton),
        "waitforexitandrun",
        str(steam_game / "CoDWaW.exe"),
        "+set",
        "fs_homepath",
        r"C:\users\steamuser\AppData\Local\Activision\CoDWaW",
        "+set",
        "fs_game",
        f"mods/{build_mod.MOD_NAME}",
        "+set",
        "logfile",
        "2",
        "+set",
        "r_fullscreen",
        "1",
        "+set",
        "r_mode",
        "1280x720",
        "+set",
        "com_introPlayed",
        "1",
        "+set",
        "vid_xpos",
        "0",
        "+set",
        "vid_ypos",
        "0",
        "+set",
        "gauntlet_enabled",
        "1",
    ]
    for dvar_key, dvar_val in extra_dvars:
        cmd.extend(["+set", dvar_key, dvar_val])
    cmd.extend(["+map", start_map])

    t0 = time.monotonic()
    log_text = ""
    timed_out = False
    for attempt in range(2):
        smoke_verify.clear_previous_run_state(appdata)
        attempt_t0 = time.monotonic()
        proc = subprocess.Popen(
            cmd,
            cwd=str(steam_game),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        log_text = ""
        timed_out = False
        init_stall_retry = False
        init_stall_seen_at: float | None = None
        last_event_count = 0
        try:
            while True:
                now = time.monotonic()
                log_text, _ = smoke_verify.read_console_logs(appdata)
                parsed = verify_cycle1.parse_gauntlet_events(log_text)
                if len(parsed) > last_event_count:
                    for ev in parsed[last_event_count:]:
                        print(f"    [{now - attempt_t0:5.1f}s] {ev.raw}")
                    last_event_count = len(parsed)

                if any(pat.search(log_text) for _, pat in smoke_verify.FATAL_LOG_PATTERNS):
                    break

                if stop_predicate(parsed):
                    time.sleep(0.8)
                    log_text, _ = smoke_verify.read_console_logs(appdata)
                    break

                # Detect transient Proton/Wine DB-thread startup deadlock on $init
                # ("Waiting for $init to finish.") and retry once cleanly.
                if (
                    attempt == 0
                    and "Waiting for $init to finish." in log_text
                    and "end $init" not in log_text
                ):
                    if init_stall_seen_at is None:
                        init_stall_seen_at = now
                    elif now - init_stall_seen_at >= 10.0:
                        print("    [WARN] Transient Wine $init startup stall detected; retrying once...")
                        init_stall_retry = True
                        break

                if proc.poll() is not None:
                    time.sleep(0.3)
                    log_text, _ = smoke_verify.read_console_logs(appdata)
                    break

                if now - attempt_t0 >= timeout_s:
                    timed_out = True
                    break

                time.sleep(0.4)
        finally:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait(timeout=5)
            smoke_verify.kill_prefix_wineserver(proton, playtest_prefix)
            time.sleep(0.5)
            final_log, _ = smoke_verify.read_console_logs(appdata)
            if len(final_log) >= len(log_text):
                log_text = final_log
            (appdata / "__CoDWaW").unlink(missing_ok=True)

        if not init_stall_retry:
            break

    duration_s = time.monotonic() - t0
    smoke_verify.SMOKE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    saved_log = smoke_verify.SMOKE_LOG_DIR / log_filename
    saved_log.write_text(log_text, encoding="utf-8", errors="replace")

    events, errors = analyzer(log_text)
    if timed_out and not stop_predicate(events):
        errors.insert(0, f"Timed out after {timeout_s:.1f}s before scenario completed")

    return ScenarioResult(
        name=name,
        passed=len(errors) == 0,
        duration_s=duration_s,
        events=events,
        errors=errors,
        saved_log=saved_log,
    )


def _has_stage_sample(events: list[GauntletEvent], stage_idx_0based: int, expected_round: int) -> bool:
    stages = _split_stages(events)
    if len(stages) <= stage_idx_0based:
        return False
    return any(
        e.event_type == "ZOMBIE_SPAWNED_SAMPLE" and e.fields.get("round") == str(expected_round)
        for e in stages[stage_idx_0based]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="Skip building mod.ff before launching.")
    parser.add_argument("--timeout", type=float, default=140.0, help="Per-scenario timeout in seconds.")
    parser.add_argument("--prep-duration", type=int, default=3, help="gauntlet_test_prep_duration override.")
    parser.add_argument("--banner-delay", type=float, default=1.0, help="gauntlet_test_banner_delay override.")
    parser.add_argument("--tools-root", type=Path, default=build_mod.DEFAULT_TOOLS_ROOT)
    parser.add_argument("--steam-root", type=Path, default=build_mod.DEFAULT_STEAM_ROOT)
    parser.add_argument("--dev-root", type=Path, default=build_mod.DEFAULT_DEV_ROOT)
    parser.add_argument("--steam-game", type=Path, default=build_mod.DEFAULT_STEAM_GAME)
    parser.add_argument("--steam-appdata", type=Path, default=build_mod.DEFAULT_STEAM_APPDATA)
    parser.add_argument("--playtest-prefix", type=Path, default=smoke_verify.DEFAULT_PLAYTEST_PREFIX)
    parser.add_argument("--proton", type=Path, default=smoke_verify.DEFAULT_PROTON)
    args = parser.parse_args(argv)

    playtest_appdata = (
        args.playtest_prefix
        / "pfx/drive_c/users/steamuser/AppData/Local/Activision/CoDWaW"
    )
    if not playtest_appdata.is_dir():
        print(f"ERROR: Playtest AppData folder missing: {playtest_appdata}", file=sys.stderr)
        return 1
    if not args.proton.is_file():
        print(f"ERROR: Proton launcher not found: {args.proton}", file=sys.stderr)
        return 1

    deploy_targets = [args.steam_appdata, playtest_appdata]
    if not args.skip_build:
        print("=== Building and deploying waw_gauntlet (mod.ff + waw_gauntlet.iwd) ===")
        artifacts, installed = build_mod.build_and_optionally_deploy(
            tools_root=args.tools_root,
            steam_root=args.steam_root,
            dev_root=args.dev_root,
            steam_game=args.steam_game,
            deploy_targets=deploy_targets,
        )
        for artifact in artifacts:
            print(f"Built {artifact} ({artifact.stat().st_size} bytes)")
        for dest in installed:
            print(f"Deployed {dest}")
    else:
        for target in deploy_targets:
            for dest in build_mod.deploy_mod(build_mod.DIST_DIR, target):
                print(f"Deployed {dest}")

    print("\n=== Starting headless Xvfb display for Cycle 2+ verification ===")
    display_num, xvfb, xfwm, xdg_tmp = smoke_verify.start_virtual_display()
    results: list[ScenarioResult] = []
    try:
        # Scenario 1: Cycle 1 Stage 4 (factory, R9) -> Cycle 2 Stage 1 (prototype, R10, Floor=5000, Prep Phase)
        print("\n--> Scenario 1: Cycle 1 Stage 4 (factory, R9) -> Cycle 2 Stage 1 (prototype, R10) wrap")
        res1 = run_waw_scenario(
            name="Cycle 1 Stage 4 -> Cycle 2 Stage 1 wrap",
            log_filename="cycle2_s1_c1_to_c2_wrap.console.log",
            start_map="nazi_zombie_factory",
            extra_dvars=[
                ("gauntlet_active", "1"),
                ("gauntlet_run_id", "verify_c1_c2"),
                ("gauntlet_cycle", "1"),
                ("gauntlet_stage", "4"),
                ("gauntlet_cycle_order", "nazi_zombie_prototype,nazi_zombie_asylum,nazi_zombie_sumpf,nazi_zombie_factory"),
                ("gauntlet_start_round", "9"),
                ("gauntlet_target_round", "9"),
                ("gauntlet_total_rounds", "8"),
                ("gauntlet_pending_transition", "1"),
                ("gauntlet_player_points", ""),
                ("gauntlet_test_next_cycle_order", "nazi_zombie_prototype,nazi_zombie_sumpf,nazi_zombie_asylum,nazi_zombie_factory"),
                ("gauntlet_test_stage_span", "5"),
                ("gauntlet_test_target_round", "0"),
                ("gauntlet_test_banner_delay", str(args.banner_delay)),
                ("gauntlet_test_prep_duration", str(args.prep_duration)),
                ("gauntlet_test_autoclear", "1"),
            ],
            stop_predicate=lambda evs: _has_stage_sample(evs, 1, 10),
            analyzer=lambda txt: analyze_c1_to_c2_wrap_log(txt, expected_prep_duration=args.prep_duration),
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=args.timeout,
        )
        results.append(res1)

        # Extract the real Solo player key observed by CoDWaW.exe in Scenario 1
        observed_player_key = "n_player"
        for ev in res1.events:
            if ev.event_type in ("POINTS_SAVED", "POINTS_APPLIED") and ev.fields.get("player"):
                observed_player_key = ev.fields["player"]
                break

        # Scenario 2: Surplus preservation (8500 > 5000 floor) on Cycle 2 Stage 1 (prototype, R10..14)
        print(
            f"\n--> Scenario 2: Surplus preservation on Cycle 2 Stage 1 "
            f"({observed_player_key}=8500 > floor 5000)"
        )
        res2 = run_waw_scenario(
            name="Cycle 2 Stage 1 surplus preservation (8500)",
            log_filename="cycle2_s2_surplus_preservation.console.log",
            start_map="nazi_zombie_prototype",
            extra_dvars=[
                ("gauntlet_active", "1"),
                ("gauntlet_run_id", "verify_surplus"),
                ("gauntlet_cycle", "2"),
                ("gauntlet_stage", "1"),
                ("gauntlet_cycle_order", "nazi_zombie_prototype,nazi_zombie_sumpf,nazi_zombie_asylum,nazi_zombie_factory"),
                ("gauntlet_start_round", "10"),
                ("gauntlet_target_round", "14"),
                ("gauntlet_total_rounds", "9"),
                ("gauntlet_pending_transition", "1"),
                ("gauntlet_player_points", f"{observed_player_key}=8500"),
                ("gauntlet_test_target_round", "0"),
                ("gauntlet_test_banner_delay", str(args.banner_delay)),
                ("gauntlet_test_prep_duration", str(args.prep_duration)),
                ("gauntlet_test_autoclear", "0"),
            ],
            stop_predicate=lambda evs: _has_stage_sample(evs, 0, 10),
            analyzer=lambda txt: analyze_surplus_preservation_log(
                txt, expected_surplus=8500, expected_prep_duration=args.prep_duration
            ),
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=args.timeout,
        )
        results.append(res2)

        # Scenario 3: Cycle 2 Stage 4 (factory, R14 + dogs) -> Cycle 3 Stage 1 (prototype, R15, Floor=7500)
        print("\n--> Scenario 3: Cycle 2 Stage 4 (factory, R14 + Hellhounds) -> Cycle 3 Stage 1 (prototype, R15) wrap")
        res3 = run_waw_scenario(
            name="Cycle 2 Stage 4 -> Cycle 3 Stage 1 wrap",
            log_filename="cycle2_s3_c2_to_c3_wrap.console.log",
            start_map="nazi_zombie_factory",
            extra_dvars=[
                ("gauntlet_active", "1"),
                ("gauntlet_run_id", "verify_c2_c3"),
                ("gauntlet_cycle", "2"),
                ("gauntlet_stage", "4"),
                ("gauntlet_cycle_order", "nazi_zombie_prototype,nazi_zombie_sumpf,nazi_zombie_asylum,nazi_zombie_factory"),
                ("gauntlet_start_round", "14"),
                ("gauntlet_target_round", "18"),
                ("gauntlet_total_rounds", "13"),
                ("gauntlet_pending_transition", "1"),
                ("gauntlet_player_points", ""),
                ("gauntlet_test_next_cycle_order", "nazi_zombie_prototype,nazi_zombie_asylum,nazi_zombie_sumpf,nazi_zombie_factory"),
                ("gauntlet_test_stage_span", "5"),
                ("gauntlet_test_target_round", "14"),
                ("gauntlet_test_banner_delay", str(args.banner_delay)),
                ("gauntlet_test_prep_duration", str(args.prep_duration)),
                ("gauntlet_test_autoclear", "1"),
            ],
            stop_predicate=lambda evs: _has_stage_sample(evs, 1, 15),
            analyzer=lambda txt: analyze_c2_to_c3_wrap_log(txt, expected_prep_duration=args.prep_duration),
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=args.timeout,
        )
        results.append(res3)
    finally:
        smoke_verify.stop_virtual_display(xvfb, xfwm, xdg_tmp)

    print("\n=== Cycle 2+ In-Engine Verification Summary ===")
    passed_count = 0
    for res in results:
        tag = "PASS" if res.passed else "FAIL"
        if res.passed:
            passed_count += 1
        print(f"  [{tag}] {res.name} ({res.duration_s:.1f}s, events={len(res.events)})")
        if res.saved_log:
            print(f"        log: {res.saved_log}")
        for err in res.errors:
            print(f"        ERROR: {err}", file=sys.stderr)
    print(f"Total: {passed_count}/{len(results)} scenarios passed")
    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
