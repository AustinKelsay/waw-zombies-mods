#!/usr/bin/env python3
"""Real in-engine team wipe, Run Summary, and clean Run reset verification harness.

Runs three focused CoDWaW.exe verification scenarios against the built
waw_gauntlet mod:
  Scenario A (Team Wipe & Run Reset):
    - Seeds an active Gauntlet Run (default Cycle 2 Stage 2 on nazi_zombie_asylum
      with prior total_rounds=45, carried player points, and lobby handoff dvars).
    - Triggers deterministic wipe on target round (default Round 12).
    - Asserts structured RUN_WIPE (exact cycle, stage, map, display, final_round,
      total_rounds), RUN_RESET (active=0, ledger_cleared=1, matching run_id),
      RUN_SUMMARY, zero duplicate wipes, and zero fatal script errors.
  Scenario B (Immediate Fresh Run After Wipe):
    - Launches nazi_zombie_prototype immediately after Scenario A with Gauntlet
      enabled and zero seeded Run state.
    - Asserts fresh Run starts cleanly at Cycle 1, Stage 1, Round 1 with stock
      500 points (carried=none;floor=500;points=500) and a new run_id.
  Scenario C (Classic Mode Isolation):
    - Launches nazi_zombie_prototype with gauntlet_enabled=0 (Classic Mode).
    - Asserts MOD_LOADED reports gauntlet_enabled=0 and ZERO RUN_WIPE,
      RUN_SUMMARY, RUN_RESET, STAGE_INIT, or GAUNTLET_READY events occur.
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

MAP_DISPLAY_NAMES: dict[str, str] = {
    "nazi_zombie_prototype": "Nacht der Untoten",
    "nazi_zombie_asylum": "Verruckt",
    "nazi_zombie_sumpf": "Shi No Numa",
    "nazi_zombie_factory": "Der Riese",
}

MAP_STAGE_NUMBERS: dict[str, int] = {
    "nazi_zombie_prototype": 1,
    "nazi_zombie_asylum": 2,
    "nazi_zombie_sumpf": 3,
    "nazi_zombie_factory": 4,
}


@dataclass
class WipeScenarioResult:
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


def analyze_wipe_log(
    log_text: str,
    expected_cycle: int,
    expected_stage: int,
    expected_map: str,
    expected_display: str,
    expected_final_round: int,
    expected_total_rounds: int,
    expected_run_id: str | None = None,
) -> tuple[list[GauntletEvent], list[str]]:
    """Validate RUN_WIPE, RUN_RESET, RUN_SUMMARY, ordering, and zero fatal errors."""
    events = verify_cycle1.parse_gauntlet_events(log_text)
    errors: list[str] = []
    _check_fatal_patterns(log_text, errors)

    stage_inits = [e for e in events if e.event_type == "STAGE_INIT"]
    if not stage_inits:
        errors.append("Missing STAGE_INIT before wipe")
    else:
        init_ev = stage_inits[0]
        for key, exp in (
            ("cycle", str(expected_cycle)),
            ("stage", str(expected_stage)),
            ("map", expected_map),
        ):
            if init_ev.fields.get(key) != exp:
                errors.append(
                    f"STAGE_INIT {key}={init_ev.fields.get(key)!r}, expected {exp!r} ({init_ev.raw})"
                )

    wipe_indices = [i for i, e in enumerate(events) if e.event_type == "RUN_WIPE"]
    if len(wipe_indices) != 1:
        errors.append(f"Expected 1 RUN_WIPE event, found {len(wipe_indices)}")
        return events, errors

    wipe_idx = wipe_indices[0]
    wipe_ev = events[wipe_idx]
    wipe_checks = (
        ("cycle", str(expected_cycle)),
        ("stage", str(expected_stage)),
        ("map", expected_map),
        ("display", expected_display),
        ("final_round", str(expected_final_round)),
        ("total_rounds", str(expected_total_rounds)),
    )
    for key, exp in wipe_checks:
        if wipe_ev.fields.get(key) != exp:
            errors.append(
                f"RUN_WIPE {key}={wipe_ev.fields.get(key)!r}, expected {exp!r} ({wipe_ev.raw})"
            )

    wipe_run_id = wipe_ev.fields.get("run_id", "")
    if not wipe_run_id:
        errors.append(f"RUN_WIPE missing run_id ({wipe_ev.raw})")
    elif expected_run_id is not None and wipe_run_id != expected_run_id:
        errors.append(
            f"RUN_WIPE run_id={wipe_run_id!r}, expected {expected_run_id!r} ({wipe_ev.raw})"
        )

    reset_indices = [i for i, e in enumerate(events) if e.event_type == "RUN_RESET"]
    if len(reset_indices) != 1:
        errors.append(f"Expected 1 RUN_RESET event, found {len(reset_indices)}")
    else:
        reset_idx = reset_indices[0]
        reset_ev = events[reset_idx]
        if reset_idx <= wipe_idx:
            errors.append("RUN_RESET must occur after RUN_WIPE")
        if reset_ev.fields.get("active") != "0":
            errors.append(
                f"RUN_RESET active={reset_ev.fields.get('active')!r}, expected '0' ({reset_ev.raw})"
            )
        if reset_ev.fields.get("ledger_cleared") != "1":
            errors.append(
                f"RUN_RESET ledger_cleared={reset_ev.fields.get('ledger_cleared')!r}, "
                f"expected '1' ({reset_ev.raw})"
            )
        if reset_ev.fields.get("perks_cleared") != "1":
            errors.append(
                f"RUN_RESET perks_cleared={reset_ev.fields.get('perks_cleared')!r}, "
                f"expected '1' ({reset_ev.raw})"
            )
        if reset_ev.fields.get("handoff_cleared") != "1":
            errors.append(
                f"RUN_RESET handoff_cleared={reset_ev.fields.get('handoff_cleared')!r}, "
                f"expected '1' ({reset_ev.raw})"
            )
        if reset_ev.fields.get("progression_cleared") != "1":
            errors.append(
                f"RUN_RESET progression_cleared={reset_ev.fields.get('progression_cleared')!r}, "
                f"expected '1' ({reset_ev.raw})"
            )
        if wipe_run_id and reset_ev.fields.get("run_id") != wipe_run_id:
            errors.append(
                f"RUN_RESET run_id={reset_ev.fields.get('run_id')!r} does not match "
                f"RUN_WIPE run_id={wipe_run_id!r}"
            )

    summary_indices = [i for i, e in enumerate(events) if e.event_type == "RUN_SUMMARY"]
    if len(summary_indices) != 1:
        errors.append(f"Expected 1 RUN_SUMMARY event, found {len(summary_indices)}")
    else:
        summary_ev = events[summary_indices[0]]
        for key, exp in (
            ("cycle", str(expected_cycle)),
            ("stage", str(expected_stage)),
            ("display", expected_display),
            ("final_round", str(expected_final_round)),
            ("total_rounds", str(expected_total_rounds)),
        ):
            if summary_ev.fields.get(key) != exp:
                errors.append(
                    f"RUN_SUMMARY {key}={summary_ev.fields.get(key)!r}, "
                    f"expected {exp!r} ({summary_ev.raw})"
                )

    for idx, ev in enumerate(events):
        if idx > wipe_idx and ev.event_type == "STAGE_CLEAR":
            errors.append(f"Unexpected STAGE_CLEAR after RUN_WIPE: {ev.raw}")

    return events, errors


def analyze_post_wipe_fresh_run_log(
    log_text: str,
    prior_run_id: str | None = None,
) -> tuple[list[GauntletEvent], list[str]]:
    """Validate that a Run launched immediately after wipe starts clean at C1 S1 R1 with 500 pts."""
    events = verify_cycle1.parse_gauntlet_events(log_text)
    errors: list[str] = []
    _check_fatal_patterns(log_text, errors)

    stage_inits = [e for e in events if e.event_type == "STAGE_INIT"]
    if not stage_inits:
        errors.append("Missing STAGE_INIT on post-wipe fresh Run")
    else:
        init_ev = stage_inits[0]
        for key, exp in (
            ("cycle", "1"),
            ("stage", "1"),
            ("map", "nazi_zombie_prototype"),
            ("start_round", "1"),
        ):
            if init_ev.fields.get(key) != exp:
                errors.append(
                    f"Post-wipe STAGE_INIT {key}={init_ev.fields.get(key)!r}, "
                    f"expected {exp!r} ({init_ev.raw})"
                )
        new_run_id = init_ev.fields.get("run_id", "")
        if not new_run_id:
            errors.append(f"Post-wipe STAGE_INIT missing run_id ({init_ev.raw})")
        elif prior_run_id and new_run_id == prior_run_id:
            errors.append(
                f"Post-wipe STAGE_INIT reused stale run_id={new_run_id!r} from wiped Run"
            )

    pts_events = [e for e in events if e.event_type == "POINTS_APPLIED"]
    if not pts_events:
        errors.append("Missing POINTS_APPLIED on post-wipe fresh Run")
    else:
        pts_ev = pts_events[0]
        for key, exp in (
            ("map", "nazi_zombie_prototype"),
            ("start_round", "1"),
            ("carried", "none"),
            ("floor", "500"),
            ("points", "500"),
        ):
            if pts_ev.fields.get(key) != exp:
                errors.append(
                    f"Post-wipe POINTS_APPLIED {key}={pts_ev.fields.get(key)!r}, "
                    f"expected {exp!r} ({pts_ev.raw})"
                )

    perk_events = [e for e in events if e.event_type == "PERKS_RESTORED"]
    for perk_ev in perk_events:
        if perk_ev.fields.get("count") != "0" or perk_ev.fields.get("perks") != "none":
            errors.append(
                f"Stale carried perks leaked into post-wipe Run: {perk_ev.raw}"
            )

    for forbidden in ("HIGH_ROUND_APPLIED", "PREP_PHASE_START"):
        if any(e.event_type == forbidden for e in events):
            errors.append(f"Stale Cycle 2+ event {forbidden} leaked into post-wipe Cycle 1 Run")

    return events, errors


def analyze_classic_gameover_log(
    log_text: str,
    expected_map: str = "nazi_zombie_prototype",
) -> tuple[list[GauntletEvent], list[str]]:
    """Validate Classic Mode (gauntlet_enabled=0) emits zero Gauntlet wipe/summary/reset events."""
    events = verify_cycle1.parse_gauntlet_events(log_text)
    errors: list[str] = []
    _check_fatal_patterns(log_text, errors)

    mod_loaded = [
        e
        for e in events
        if e.event_type == "MOD_LOADED"
        and e.fields.get("map") == expected_map
        and e.fields.get("gauntlet_enabled") == "0"
    ]
    if not mod_loaded:
        errors.append(
            f"Missing MOD_LOADED event with map={expected_map};gauntlet_enabled=0"
        )

    forbidden_types = {"RUN_WIPE", "RUN_SUMMARY", "RUN_RESET", "STAGE_INIT", "GAUNTLET_READY"}
    for ev in events:
        if ev.event_type in forbidden_types:
            errors.append(f"Classic Mode unexpectedly emitted {ev.event_type}: {ev.raw}")

    return events, errors


def run_wipe_scenario(
    name: str,
    log_filename: str,
    start_map: str,
    gauntlet_enabled: int,
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
    settle_s: float = 0.8,
) -> WipeScenarioResult:
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
        str(gauntlet_enabled),
    ]
    for dvar_key, dvar_val in extra_dvars:
        cmd.extend(["+set", dvar_key, dvar_val])
    cmd.extend(["+map", start_map])

    t0 = time.monotonic()
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
    last_event_count = 0
    matched_at: float | None = None
    try:
        while True:
            now = time.monotonic()
            log_text, _ = smoke_verify.read_console_logs(appdata)
            parsed = verify_cycle1.parse_gauntlet_events(log_text)
            if len(parsed) > last_event_count:
                for ev in parsed[last_event_count:]:
                    print(f"    [{now - t0:5.1f}s] {ev.raw}")
                last_event_count = len(parsed)

            if any(pat.search(log_text) for _, pat in smoke_verify.FATAL_LOG_PATTERNS):
                break

            if stop_predicate(parsed):
                if matched_at is None:
                    matched_at = now
                elif now - matched_at >= settle_s:
                    log_text, _ = smoke_verify.read_console_logs(appdata)
                    break

            if proc.poll() is not None:
                time.sleep(0.3)
                log_text, _ = smoke_verify.read_console_logs(appdata)
                break

            if now - t0 >= timeout_s:
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

    duration_s = time.monotonic() - t0
    smoke_verify.SMOKE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    saved_log = smoke_verify.SMOKE_LOG_DIR / log_filename
    saved_log.write_text(log_text, encoding="utf-8", errors="replace")

    events, errors = analyzer(log_text)
    if timed_out and not stop_predicate(events):
        errors.insert(0, f"Timed out after {timeout_s:.1f}s before scenario completed")

    return WipeScenarioResult(
        name=name,
        passed=len(errors) == 0,
        duration_s=duration_s,
        events=events,
        errors=errors,
        saved_log=saved_log,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--maps",
        nargs="+",
        default=["nazi_zombie_asylum"],
        choices=list(build_mod.STOCK_MAPS),
        help="Stock map(s) to verify active-Run team wipe on (default: nazi_zombie_asylum).",
    )
    parser.add_argument("--skip-build", action="store_true", help="Skip building mod.ff before launching.")
    parser.add_argument("--timeout", type=float, default=140.0, help="Per-scenario timeout in seconds.")
    parser.add_argument("--prep-duration", type=int, default=2, help="gauntlet_test_prep_duration override.")
    parser.add_argument(
        "--summary-delay",
        type=float,
        default=1.5,
        help="gauntlet_test_summary_delay override in seconds.",
    )
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

    print("\n=== Starting headless Xvfb display for Team Wipe & Run Reset verification ===")
    display_num, xvfb, xfwm, xdg_tmp = smoke_verify.start_virtual_display()
    results: list[WipeScenarioResult] = []
    last_wipe_run_id: str | None = None
    try:
        # Scenario A: Active Gauntlet Run hits team wipe on each selected map (seeded at Cycle 2)
        for wipe_map in args.maps:
            stage_num = MAP_STAGE_NUMBERS[wipe_map]
            display_name = MAP_DISPLAY_NAMES[wipe_map]
            prior_rounds = 40 + (stage_num - 1) * 5
            wipe_round = 12
            expected_total = prior_rounds + (wipe_round - 10)
            run_id = f"verify_wipe_c2s{stage_num}"
            last_wipe_run_id = run_id

            print(
                f"\n--> Scenario A ({wipe_map}): Cycle 2 Stage {stage_num} ({display_name}) "
                f"team wipe on Round {wipe_round} (expected total_rounds={expected_total})"
            )
            res_a = run_wipe_scenario(
                name=f"Scenario A: Team Wipe on {wipe_map} (C2 S{stage_num} R{wipe_round})",
                log_filename=f"wipe_scenario_a_{wipe_map}.console.log",
                start_map=wipe_map,
                gauntlet_enabled=1,
                extra_dvars=[
                    ("gauntlet_active", "1"),
                    ("gauntlet_run_id", run_id),
                    ("gauntlet_cycle", "2"),
                    ("gauntlet_stage", str(stage_num)),
                    ("gauntlet_cycle_order", "nazi_zombie_prototype,nazi_zombie_asylum,nazi_zombie_sumpf,nazi_zombie_factory"),
                    ("gauntlet_start_round", "10"),
                    ("gauntlet_target_round", "14"),
                    ("gauntlet_total_rounds", str(prior_rounds)),
                    ("gauntlet_pending_transition", "1"),
                    ("gauntlet_player_points", "n_player=12500"),
                    ("gauntlet_next_map", "nazi_zombie_sumpf"),
                    ("gauntlet_next_display", "Shi No Numa"),
                    ("gauntlet_lobby_status", "Next: Shi No Numa"),
                    ("gauntlet_test_target_round", "15"),
                    ("gauntlet_test_prep_duration", str(args.prep_duration)),
                    ("gauntlet_test_summary_delay", str(args.summary_delay)),
                    ("gauntlet_test_autoclear", "1"),
                    ("gauntlet_test_force_wipe", "1"),
                    ("gauntlet_test_wipe_round", str(wipe_round)),
                ],
                stop_predicate=lambda evs: (
                    any(e.event_type == "RUN_WIPE" for e in evs)
                    and any(e.event_type == "RUN_RESET" for e in evs)
                    and any(e.event_type == "RUN_SUMMARY" for e in evs)
                ),
                analyzer=lambda txt, _s=stage_num, _m=wipe_map, _d=display_name, _r=wipe_round, _t=expected_total, _id=run_id: analyze_wipe_log(
                    txt,
                    expected_cycle=2,
                    expected_stage=_s,
                    expected_map=_m,
                    expected_display=_d,
                    expected_final_round=_r,
                    expected_total_rounds=_t,
                    expected_run_id=_id,
                ),
                display_num=display_num,
                xdg_config_home=xdg_tmp.name,
                proton=args.proton,
                steam_root=args.steam_root,
                steam_game=args.steam_game,
                playtest_prefix=args.playtest_prefix,
                timeout_s=args.timeout,
                settle_s=args.summary_delay + 0.5,
            )
            results.append(res_a)

        # Scenario B: Fresh Run launched immediately after wipe on Nacht der Untoten
        print("\n--> Scenario B: Post-wipe fresh Run on nazi_zombie_prototype (C1 S1 R1, 500 pts)")
        res_b = run_wipe_scenario(
            name="Scenario B: Post-wipe fresh Run (C1 S1 R1, 500 pts)",
            log_filename="wipe_scenario_b_fresh_run.console.log",
            start_map="nazi_zombie_prototype",
            gauntlet_enabled=1,
            extra_dvars=[
                ("gauntlet_test_target_round", "0"),
                ("gauntlet_test_autoclear", "0"),
                ("gauntlet_test_force_wipe", "0"),
                ("gauntlet_test_wipe_round", "0"),
            ],
            stop_predicate=lambda evs: (
                any(e.event_type == "STAGE_INIT" for e in evs)
                and any(e.event_type == "POINTS_APPLIED" for e in evs)
            ),
            analyzer=lambda txt: analyze_post_wipe_fresh_run_log(txt, prior_run_id=last_wipe_run_id),
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=args.timeout,
        )
        results.append(res_b)

        # Scenario C: Classic Mode (gauntlet_enabled=0) produces zero wipe/summary/reset events
        print("\n--> Scenario C: Classic Mode (gauntlet_enabled=0) emits zero Gauntlet wipe events")
        res_c = run_wipe_scenario(
            name="Scenario C: Classic Mode isolation (gauntlet_enabled=0)",
            log_filename="wipe_scenario_c_classic.console.log",
            start_map="nazi_zombie_prototype",
            gauntlet_enabled=0,
            extra_dvars=[
                ("gauntlet_test_force_wipe", "1"),
                ("gauntlet_test_wipe_round", "1"),
            ],
            stop_predicate=lambda evs: any(
                e.event_type == "MOD_LOADED" and e.fields.get("gauntlet_enabled") == "0"
                for e in evs
            ),
            analyzer=lambda txt: analyze_classic_gameover_log(txt, expected_map="nazi_zombie_prototype"),
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=args.timeout,
            settle_s=2.5,
        )
        results.append(res_c)
    finally:
        smoke_verify.stop_virtual_display(xvfb, xfwm, xdg_tmp)

    print("\n=== Team Wipe & Run Reset Verification Summary ===")
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
