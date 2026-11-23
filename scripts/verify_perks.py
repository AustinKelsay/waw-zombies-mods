#!/usr/bin/env python3
"""Automated in-engine verification for cross-map Perk Carryover (ADR-0004).

Verifies real Steam/Proton CoD:WaW execution across:
  1. Scenario A: Active Gauntlet Run seeded with perks via one-shot
     `gauntlet_test_grant_perks="j,f"` on Cycle 1 Stage 4 (Der Riese) clears
     Stage 4 and wraps to Cycle 2 Stage 1 (Nacht der Untoten), asserting
     `PERKS_SAVED` on Der Riese and `PERKS_RESTORED` with Juggernog
     `maxhealth=160` and zero missing-shader/400-FX errors on Nacht der Untoten.
  2. Scenario B: Classic Mode (`gauntlet_enabled=0`) emits zero perk carryover
     telemetry (`PERKS_SAVED`, `PERKS_RESTORED`, `PERKS_TEST_GRANTED`).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_mod  # noqa: E402
import smoke_verify  # noqa: E402
import verify_cycle1  # noqa: E402
from verify_cycle1 import GauntletEvent  # noqa: E402

REPO_ROOT = build_mod.REPO_ROOT
DEFAULT_LOG_DIR = REPO_ROOT / ".smoke_logs"


def _check_fatal_patterns(log_text: str, errors: list[str]) -> None:
    for label, pattern in smoke_verify.FATAL_LOG_PATTERNS:
        for line in log_text.splitlines():
            if pattern.search(line):
                errors.append(f"{label}: {line.strip()}")
                break


def analyze_perk_carryover_log(
    log_text: str,
    expected_from_map: str = "nazi_zombie_factory",
    expected_to_map: str = "nazi_zombie_prototype",
    expected_perks_csv: str = "specialty_armorvest,specialty_fastreload",
    expected_count: int = 2,
    expected_maxhealth: int = 160,
) -> tuple[list[GauntletEvent], list[str]]:
    """Validate cross-map perk snapshot and restoration across a Stage Transition."""
    events = verify_cycle1.parse_gauntlet_events(log_text)
    errors: list[str] = []
    _check_fatal_patterns(log_text, errors)

    saved_from = [
        e
        for e in events
        if e.event_type == "PERKS_SAVED" and e.fields.get("map") == expected_from_map
    ]
    if not saved_from:
        errors.append(f"Missing PERKS_SAVED on source map {expected_from_map!r}")
    else:
        ev = saved_from[-1]
        if ev.fields.get("perks") != expected_perks_csv:
            errors.append(
                f"PERKS_SAVED perks={ev.fields.get('perks')!r}, expected {expected_perks_csv!r} ({ev.raw})"
            )
        if ev.fields.get("count") != str(expected_count):
            errors.append(
                f"PERKS_SAVED count={ev.fields.get('count')!r}, expected {str(expected_count)!r} ({ev.raw})"
            )

    restored_to = [
        e
        for e in events
        if e.event_type == "PERKS_RESTORED" and e.fields.get("map") == expected_to_map
    ]
    if not restored_to:
        errors.append(f"Missing PERKS_RESTORED on destination map {expected_to_map!r}")
    else:
        ev = restored_to[0]
        if ev.fields.get("perks") != expected_perks_csv:
            errors.append(
                f"PERKS_RESTORED perks={ev.fields.get('perks')!r}, expected {expected_perks_csv!r} ({ev.raw})"
            )
        if ev.fields.get("count") != str(expected_count):
            errors.append(
                f"PERKS_RESTORED count={ev.fields.get('count')!r}, expected {str(expected_count)!r} ({ev.raw})"
            )
        if ev.fields.get("maxhealth") != str(expected_maxhealth):
            errors.append(
                f"PERKS_RESTORED maxhealth={ev.fields.get('maxhealth')!r}, "
                f"expected {str(expected_maxhealth)!r} ({ev.raw})"
            )

    if saved_from and restored_to:
        saved_idx = events.index(saved_from[-1])
        restored_idx = events.index(restored_to[0])
        if restored_idx <= saved_idx:
            errors.append("PERKS_RESTORED on destination map occurred before PERKS_SAVED on source map")

    return events, errors


def analyze_classic_perks_isolation_log(log_text: str) -> tuple[list[GauntletEvent], list[str]]:
    """Validate Classic Mode (gauntlet_enabled=0) emits zero perk carryover telemetry."""
    events = verify_cycle1.parse_gauntlet_events(log_text)
    errors: list[str] = []
    _check_fatal_patterns(log_text, errors)

    if not any(e.event_type == "MOD_LOADED" for e in events):
        errors.append("Classic Mode log missing MOD_LOADED telemetry")

    for forbidden in ("PERKS_SAVED", "PERKS_RESTORED", "PERKS_TEST_GRANTED"):
        leaked = [e for e in events if e.event_type == forbidden]
        if leaked:
            errors.append(f"Classic Mode leaked forbidden event {forbidden}: {leaked[0].raw}")

    return events, errors


def run_perk_scenario(
    scenario_name: str,
    launch_map: str,
    extra_args: list[str],
    stop_predicate,
    display_num: int,
    xdg_config_home: Path,
    proton: Path,
    steam_root: Path,
    steam_game: Path,
    playtest_prefix: Path,
    log_dir: Path,
    timeout_s: float,
) -> tuple[str, Path]:
    """Run a single CoDWaW.exe scenario and archive its console.log."""
    appdata = smoke_verify.playtest_appdata(playtest_prefix)
    mod_log = appdata / "mods" / build_mod.MOD_NAME / "console.log"
    main_log = appdata / "main" / "console.log"
    sentinel = appdata / "__CoDWaW"

    for stale in (mod_log, main_log, sentinel):
        stale.unlink(missing_ok=True)
    mod_log.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["DISPLAY"] = f":{display_num}"
    env["XDG_CONFIG_HOME"] = str(xdg_config_home)
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = str(steam_root)
    env["STEAM_COMPAT_DATA_PATH"] = str(playtest_prefix)
    env["SteamAppId"] = "10090"
    env["SteamGameId"] = "10090"
    env["PROTON_USE_WINED3D"] = "1"
    env["PROTON_NO_ESYNC"] = "1"
    env["PROTON_NO_FSYNC"] = "1"

    cmd = [
        str(proton),
        "run",
        str(steam_game / "CoDWaW.exe"),
        "+set",
        "r_fullscreen",
        "0",
        "+set",
        "r_mode",
        "800x600",
        "+set",
        "logfile",
        "2",
        "+set",
        "fs_game",
        f"mods/{build_mod.MOD_NAME}",
        *extra_args,
        "+map",
        launch_map,
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=steam_game,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    log_text = ""
    deadline = time.monotonic() + timeout_s
    try:
        while time.monotonic() < deadline:
            if mod_log.is_file():
                log_text = mod_log.read_text(encoding="latin1", errors="replace")
            elif main_log.is_file():
                log_text = main_log.read_text(encoding="latin1", errors="replace")

            if log_text:
                events = verify_cycle1.parse_gauntlet_events(log_text)
                if stop_predicate(events, log_text):
                    time.sleep(1.5)
                    if mod_log.is_file():
                        log_text = mod_log.read_text(encoding="latin1", errors="replace")
                    break
                if any(pat.search(log_text) for _, pat in smoke_verify.FATAL_LOG_PATTERNS):
                    break

            if proc.poll() is not None:
                if mod_log.is_file():
                    log_text = mod_log.read_text(encoding="latin1", errors="replace")
                break
            time.sleep(1.0)
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, 15)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, 9)
                except ProcessLookupError:
                    pass
                proc.wait(timeout=5)
        smoke_verify.kill_prefix_wineserver(proton, playtest_prefix)

    log_dir.mkdir(parents=True, exist_ok=True)
    saved_log = log_dir / f"perks_{scenario_name}.console.log"
    saved_log.write_text(log_text, encoding="latin1", errors="replace")
    return log_text, saved_log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--steam-root", type=Path, default=build_mod.DEFAULT_STEAM_ROOT)
    parser.add_argument("--dev-root", type=Path, default=build_mod.DEFAULT_DEV_ROOT)
    parser.add_argument("--proton", type=Path, default=smoke_verify.DEFAULT_PROTON)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    args = parser.parse_args(argv)

    steam_game = args.steam_root / "steamapps/common/Call of Duty World at War"
    tools_root = args.dev_root / "game"
    playtest_prefix = args.dev_root / "playtest"
    playtest_app = smoke_verify.playtest_appdata(playtest_prefix)
    steam_app = (
        args.steam_root
        / "steamapps/compatdata/10090/pfx/drive_c/users/steamuser/AppData/Local/Activision/CoDWaW"
    )

    if not args.skip_build:
        targets = [playtest_app]
        if steam_app.is_dir():
            targets.append(steam_app)
        build_mod.build_and_optionally_deploy(
            tools_root=tools_root,
            steam_root=args.steam_root,
            dev_root=args.dev_root,
            steam_game=steam_game,
            deploy_targets=targets,
        )
    else:
        build_mod.deploy_mod(build_mod.DIST_DIR, playtest_app)

    if shutil.which("Xvfb") is None or shutil.which("xfwm4") is None:
        print("ERROR: Xvfb and xfwm4 must be installed for in-engine verification.", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    with TemporaryDirectory(prefix="waw-perks-xdg-") as tmp_xdg:
        xdg_path = Path(tmp_xdg)
        display_num, xvfb_proc, wm_proc = smoke_verify.start_headless_display(xdg_path)
        try:
            # Scenario A: Der Riese (C1 S4) with Juggernog + Speed Cola -> Cycle 2 Nacht der Untoten
            log_a, saved_a = run_perk_scenario(
                scenario_name="c1s4_to_c2_nacht",
                launch_map="nazi_zombie_factory",
                extra_args=[
                    "+set", "gauntlet_enabled", "1",
                    "+set", "gauntlet_active", "1",
                    "+set", "gauntlet_run_id", "verify_perks_run",
                    "+set", "gauntlet_cycle", "1",
                    "+set", "gauntlet_stage", "4",
                    "+set", "gauntlet_total_rounds", "30",
                    "+set", "gauntlet_pending_transition", "1",
                    "+set", "gauntlet_test_grant_perks", "j,f",
                    "+set", "gauntlet_test_target_round", "1",
                    "+set", "gauntlet_test_autoclear", "1",
                    "+set", "gauntlet_test_banner_delay", "1.0",
                    "+set", "gauntlet_test_prep_duration", "2",
                ],
                stop_predicate=lambda evs, _txt: any(
                    e.event_type == "PERKS_RESTORED" and e.fields.get("map") == "nazi_zombie_prototype"
                    for e in evs
                ),
                display_num=display_num,
                xdg_config_home=xdg_path,
                proton=args.proton,
                steam_root=args.steam_root,
                steam_game=steam_game,
                playtest_prefix=playtest_prefix,
                log_dir=args.log_dir,
                timeout_s=args.timeout,
            )
            _, errs_a = analyze_perk_carryover_log(log_a)
            if errs_a:
                print(f"[FAIL] Scenario A (Der Riese -> Cycle 2 Nacht perks) — {saved_a}")
                for e in errs_a:
                    print(f"  - {e}")
                all_errors.extend(errs_a)
            else:
                print(f"[PASS] Scenario A (Der Riese -> Cycle 2 Nacht perks, Jugg 160 HP) — {saved_a}")

            # Scenario B: Classic Mode zero perk telemetry
            log_b, saved_b = run_perk_scenario(
                scenario_name="classic_isolation",
                launch_map="nazi_zombie_prototype",
                extra_args=["+set", "gauntlet_enabled", "0"],
                stop_predicate=lambda evs, _txt: any(e.event_type == "MOD_LOADED" for e in evs),
                display_num=display_num,
                xdg_config_home=xdg_path,
                proton=args.proton,
                steam_root=args.steam_root,
                steam_game=steam_game,
                playtest_prefix=playtest_prefix,
                log_dir=args.log_dir,
                timeout_s=90.0,
            )
            _, errs_b = analyze_classic_perks_isolation_log(log_b)
            if errs_b:
                print(f"[FAIL] Scenario B (Classic Mode perk isolation) — {saved_b}")
                for e in errs_b:
                    print(f"  - {e}")
                all_errors.extend(errs_b)
            else:
                print(f"[PASS] Scenario B (Classic Mode perk isolation) — {saved_b}")
        finally:
            smoke_verify.stop_headless_display(xvfb_proc, wm_proc)

    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
