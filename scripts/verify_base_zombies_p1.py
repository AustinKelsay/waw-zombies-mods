#!/usr/bin/env python3
"""Automated in-engine verification for Base Zombies Phase 1 on Der Riese (Issue #18 / P1-T7).

Verifies real Steam/Proton CoD:WaW 1.7 execution across two live runs:
  1. Run A (Der Riese Base Zombies Phase 1):
     +set fs_game mods/waw_gauntlet +set bz_enabled 1 +set bz_perks_enabled 1
     +set bz_classes_enabled 1 +set bz_pap_enabled 1 +set gauntlet_enabled 0
     +set bz_test_selftest 1 +devmap nazi_zombie_factory
     Asserts mod.ff loaded, zero fatal script/asset/400-FX errors, BZ_INIT,
     all 4 Stations spawned (perks, class, arsenal, pap), and BZ_SELFTEST_PASS
     covering Perks (Standard, T2, Apex), all 6 Classes (Titan 440 HP, Sapper
     10 nades, Daredevil slam+burst, Assassin SetContents(0), Broker 2x & 475),
     Double PaP + PaP Bowie + PaP Cluster, down-reset persistence boundary,
     and HUD creation/cleanup.
  2. Run B (Classic Mode Untouched):
     +set fs_game mods/waw_gauntlet +set bz_enabled 0 +set gauntlet_enabled 0
     +devmap nazi_zombie_factory
     Asserts clean Der Riese boot with zero BZ_EVENT emissions, zero stations
     spawned, and zero fatal script/asset/400-FX errors.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
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

REPO_ROOT = build_mod.REPO_ROOT
DEFAULT_LOG_DIR = REPO_ROOT / ".smoke_logs"
REQUIRED_STATIONS: tuple[str, ...] = ("perks", "class", "arsenal", "pap")

BZ_EVENT_RE = re.compile(r"BZ_EVENT\|([A-Z0-9_]+)\|(.*)")
FX_COUNT_RE = re.compile(r"(\d+)\s+of\s+400\s+'?fx'?\s+assets", re.IGNORECASE)


@dataclass(frozen=True)
class BzEvent:
    event_type: str
    fields: dict[str, str]
    raw: str


@dataclass
class BzScenarioResult:
    name: str
    passed: bool
    duration_s: float
    events: list[BzEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    saved_log: Path | None = None
    fx_count: int | None = None


def parse_bz_events(log_text: str) -> list[BzEvent]:
    """Parse structured BZ_EVENT|<TYPE>|<k=v;...> lines from console.log."""
    events: list[BzEvent] = []
    for line in log_text.splitlines():
        match = BZ_EVENT_RE.search(line)
        if not match:
            continue
        event_type = match.group(1)
        payload = match.group(2).strip()
        fields: dict[str, str] = {}
        if payload:
            for part in payload.split(";"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    fields[k.strip()] = v.strip()
        events.append(
            BzEvent(
                event_type=event_type,
                fields=fields,
                raw=f"BZ_EVENT|{event_type}|{payload}",
            )
        )
    return events


def extract_fx_count(log_text: str) -> int | None:
    """Return the reported FX asset count if logged by WaW, else None."""
    match = FX_COUNT_RE.search(log_text)
    if match:
        return int(match.group(1))
    return None


def _check_fatal_patterns(log_text: str, errors: list[str]) -> None:
    for label, pattern in smoke_verify.FATAL_LOG_PATTERNS:
        for line in log_text.splitlines():
            if pattern.search(line):
                errors.append(f"{label}: {line.strip()}")
                break
    missing_bz_menu = re.compile(r'Could not load menufile\s+"[^"]*bz_station_', re.IGNORECASE)
    for line in log_text.splitlines():
        if missing_bz_menu.search(line):
            errors.append(f"Missing Base Zombies station menufile: {line.strip()}")
            break


def analyze_bz_p1_log(
    log_text: str,
    map_name: str = "nazi_zombie_factory",
) -> tuple[list[BzEvent], list[str]]:
    """Validate Run A: Der Riese Base Zombies Phase 1 self-test console.log."""
    events = parse_bz_events(log_text)
    errors: list[str] = []
    _check_fatal_patterns(log_text, errors)

    if not re.search(r"Loading fastfile '?mod'?", log_text, re.IGNORECASE):
        errors.append("mod.ff was not reported as loaded in console.log")

    init_events = [e for e in events if e.event_type == "BZ_INIT" and e.fields.get("map") == map_name]
    if not init_events:
        errors.append(f"Missing BZ_INIT event for map={map_name!r}")
    else:
        ev = init_events[0]
        for gate in ("perks", "classes", "pap"):
            if ev.fields.get(gate) != "1":
                errors.append(f"BZ_INIT gate {gate}={ev.fields.get(gate)!r}, expected '1' ({ev.raw})")

    spawned_stations = {
        e.fields.get("station", "")
        for e in events
        if e.event_type == "STATION_SPAWN" and e.fields.get("map") == map_name
    }
    for station_id in REQUIRED_STATIONS:
        if station_id not in spawned_stations:
            errors.append(f"Missing STATION_SPAWN for station={station_id!r} on {map_name!r}")

    fail_events = [e for e in events if e.event_type == "BZ_SELFTEST_FAIL"]
    for fev in fail_events:
        errors.append(f"Self-test reported failure: {fev.raw}")

    pass_events = [e for e in events if e.event_type == "BZ_SELFTEST_PASS"]
    if not pass_events:
        errors.append("Missing BZ_EVENT|BZ_SELFTEST_PASS|... telemetry")
    else:
        pev = pass_events[-1]
        expected_fields = (
            ("map", map_name),
            ("stations", "4"),
            ("titan_hp", "440"),
            ("sapper_nades", "10"),
            ("broker_pts", "200"),
            ("broker_box", "475"),
            ("assassin_ghost", "1"),
        )
        for key, exp in expected_fields:
            actual = pev.fields.get(key)
            if actual != exp:
                errors.append(
                    f"BZ_SELFTEST_PASS {key}={actual!r}, expected {exp!r} ({pev.raw})"
                )
        if not pev.fields.get("dpap_weapon"):
            errors.append(f"BZ_SELFTEST_PASS missing dpap_weapon ({pev.raw})")

    return events, errors


def analyze_classic_bz_isolation_log(
    log_text: str,
    map_name: str = "nazi_zombie_factory",
) -> tuple[list[BzEvent], list[str]]:
    """Validate Run B: Classic Mode (bz_enabled=0, gauntlet_enabled=0) emits zero BZ_EVENT lines."""
    events = parse_bz_events(log_text)
    errors: list[str] = []
    _check_fatal_patterns(log_text, errors)

    if not re.search(r"Loading fastfile '?mod'?", log_text, re.IGNORECASE):
        errors.append("mod.ff was not reported as loaded in console.log")

    expected_mod_loaded = f"GAUNTLET_EVENT|MOD_LOADED|map={map_name};gauntlet_enabled=0"
    if expected_mod_loaded not in log_text:
        errors.append(f"Missing expected Classic Mode event: {expected_mod_loaded}")

    if events:
        errors.append(
            f"Classic Mode leaked {len(events)} BZ_EVENT(s); first: {events[0].raw}"
        )

    return events, errors


def run_bz_scenario(
    *,
    name: str,
    log_filename: str,
    map_name: str,
    dvars: list[tuple[str, str]],
    stop_predicate: Callable[[str], bool],
    analyzer: Callable[[str], tuple[list[BzEvent], list[str]]],
    display_num: int,
    xdg_config_home: str,
    proton: Path,
    steam_root: Path,
    steam_game: Path,
    playtest_prefix: Path,
    timeout_s: float,
    settle_s: float = 2.0,
) -> BzScenarioResult:
    """Launch CoDWaW.exe via Proton + Xvfb, collect console.log, tear down wineserver cleanly."""
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
    ]
    for key, val in dvars:
        cmd.extend(["+set", key, str(val)])
    cmd.extend(["+devmap", map_name])

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
        settled_at: float | None = None
        timed_out = False
        init_stall_retry = False
        init_stall_seen_at: float | None = None
        last_log_len = 0
        last_log_growth_at = attempt_t0
        try:
            while True:
                now = time.monotonic()
                log_text, _ = smoke_verify.read_console_logs(appdata)
                if len(log_text) != last_log_len:
                    last_log_len = len(log_text)
                    last_log_growth_at = now

                if any(pat.search(log_text) for _, pat in smoke_verify.FATAL_LOG_PATTERNS):
                    break

                if stop_predicate(log_text):
                    if settled_at is None:
                        settled_at = now
                    elif now - settled_at >= settle_s:
                        break

                # Detect transient Proton/Wine pre-map startup deadlock ($init or early
                # sys_configSum hang before common.ff loads) and retry once cleanly.
                if attempt == 0 and "Loading fastfile 'common'" not in log_text:
                    if (
                        "Waiting for $init to finish." in log_text
                        and "end $init" not in log_text
                    ):
                        if init_stall_seen_at is None:
                            init_stall_seen_at = now
                        elif now - init_stall_seen_at >= 10.0:
                            print("    [WARN] Transient Wine $init startup stall detected; retrying once...")
                            init_stall_retry = True
                            break
                    elif (
                        last_log_len > 0
                        and "sys_configSum" in log_text
                        and (now - last_log_growth_at) >= 12.0
                    ):
                        print("    [WARN] Transient Wine early startup stall detected; retrying once...")
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
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    saved_log = DEFAULT_LOG_DIR / log_filename
    saved_log.write_text(log_text, encoding="utf-8", errors="replace")

    events, errors = analyzer(log_text)
    if timed_out and not stop_predicate(log_text):
        errors.insert(0, f"Timed out after {timeout_s:.1f}s waiting for {name} completion")

    return BzScenarioResult(
        name=name,
        passed=len(errors) == 0,
        duration_s=duration_s,
        events=events,
        errors=errors,
        saved_log=saved_log,
        fx_count=extract_fx_count(log_text),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--timeout", type=float, default=120.0)
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
    if shutil.which("Xvfb") is None or shutil.which("xfwm4") is None:
        print("ERROR: Xvfb and xfwm4 must be installed for in-engine verification.", file=sys.stderr)
        return 1

    deploy_targets = [playtest_appdata]
    if args.steam_appdata.is_dir():
        deploy_targets.insert(0, args.steam_appdata)

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
        for artifact_name in ("mod.ff", f"{build_mod.MOD_NAME}.iwd"):
            artifact = build_mod.DIST_DIR / artifact_name
            if not artifact.is_file():
                print(
                    f"ERROR: --skip-build specified but {artifact} does not exist",
                    file=sys.stderr,
                )
                return 1
        for target in deploy_targets:
            for dest in build_mod.deploy_mod(build_mod.DIST_DIR, target):
                print(f"Deployed {dest}")

    print("\n=== Starting headless Xvfb display for Base Zombies Phase 1 verification ===")
    display_num, xvfb, xfwm, xdg_tmp = smoke_verify.start_virtual_display()
    all_errors: list[str] = []
    try:
        # Run A: Der Riese Base Zombies Phase 1 full live self-test
        print("\n--> Run A: Der Riese Base Zombies Phase 1 (bz_enabled=1, perks+classes+pap, selftest=1)")
        res_a = run_bz_scenario(
            name="Der Riese Base Zombies Phase 1",
            log_filename="bz_p1_factory_selftest.console.log",
            map_name="nazi_zombie_factory",
            dvars=[
                ("gauntlet_enabled", "0"),
                ("bz_enabled", "1"),
                ("bz_perks_enabled", "1"),
                ("bz_classes_enabled", "1"),
                ("bz_pap_enabled", "1"),
                ("bz_elements_enabled", "0"),
                ("bz_companions_enabled", "0"),
                ("bz_test_selftest", "1"),
            ],
            stop_predicate=lambda text: (
                "BZ_EVENT|BZ_SELFTEST_PASS|" in text or "BZ_EVENT|BZ_SELFTEST_FAIL|" in text
            ),
            analyzer=lambda text: analyze_bz_p1_log(text, map_name="nazi_zombie_factory"),
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=args.timeout,
            settle_s=1.5,
        )
        fx_note = f" | fx={res_a.fx_count}/400" if res_a.fx_count is not None else ""
        if res_a.passed:
            pass_ev = next((e for e in res_a.events if e.event_type == "BZ_SELFTEST_PASS"), None)
            print(
                f"  [PASS] Run A ({res_a.duration_s:.1f}s{fx_note}) — {res_a.saved_log}"
            )
            if pass_ev:
                print(f"         {pass_ev.raw}")
        else:
            print(f"  [FAIL] Run A ({res_a.duration_s:.1f}s{fx_note}) — {res_a.saved_log}")
            for err in res_a.errors:
                print(f"         ERROR: {err}", file=sys.stderr)
            all_errors.extend(res_a.errors)

        # Run B: Classic Mode untouched on Der Riese
        print("\n--> Run B: Der Riese Classic Mode Untouched (bz_enabled=0, gauntlet_enabled=0)")
        res_b = run_bz_scenario(
            name="Der Riese Classic Mode isolation",
            log_filename="bz_p1_factory_classic.console.log",
            map_name="nazi_zombie_factory",
            dvars=[
                ("gauntlet_enabled", "0"),
                ("bz_enabled", "0"),
                ("bz_perks_enabled", "0"),
                ("bz_classes_enabled", "0"),
                ("bz_pap_enabled", "0"),
                ("bz_test_selftest", "0"),
            ],
            stop_predicate=lambda text: (
                "GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_factory;gauntlet_enabled=0" in text
            ),
            analyzer=lambda text: analyze_classic_bz_isolation_log(
                text, map_name="nazi_zombie_factory"
            ),
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=min(args.timeout, 90.0),
            settle_s=2.5,
        )
        if res_b.passed:
            print(
                f"  [PASS] Run B (Classic Mode untouched, 0 BZ_EVENTs) ({res_b.duration_s:.1f}s) "
                f"— {res_b.saved_log}"
            )
        else:
            print(f"  [FAIL] Run B (Classic Mode untouched) ({res_b.duration_s:.1f}s) — {res_b.saved_log}")
            for err in res_b.errors:
                print(f"         ERROR: {err}", file=sys.stderr)
            all_errors.extend(res_b.errors)
    finally:
        smoke_verify.stop_virtual_display(xvfb, xfwm, xdg_tmp)

    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
