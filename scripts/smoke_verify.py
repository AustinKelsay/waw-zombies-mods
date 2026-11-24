#!/usr/bin/env python3
"""Build, deploy, and run automated in-engine smoke verification across all 4 stock WaW Zombies maps."""

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
from tempfile import TemporaryDirectory

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_mod  # noqa: E402

REPO_ROOT = SCRIPT_DIR.parent
SMOKE_LOG_DIR = REPO_ROOT / ".smoke_logs"
DEFAULT_PLAYTEST_PREFIX = build_mod.DEFAULT_DEV_ROOT / "playtest"
DEFAULT_PROTON = Path(
    os.environ.get(
        "WAW_PROTON",
        build_mod.DEFAULT_STEAM_ROOT / "steamapps/common/Proton - Experimental/proton",
    )
)

# Fatal / script / asset-limit signatures that must NEVER appear in console.log.
# (Stock WaW emits benign "Error: Could not load xanim/material" messages during
# normal startup; those are intentionally excluded.)
FATAL_LOG_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("400-FX asset limit exceeded", re.compile(r"Exceeded limit of 400 'fx' assets", re.IGNORECASE)),
    ("Asset limit exceeded", re.compile(r"Exceeded limit of \d+ '[^']+' assets", re.IGNORECASE)),
    ("Script compile error", re.compile(r"script compile error", re.IGNORECASE)),
    ("Script runtime error", re.compile(r"script runtime error", re.IGNORECASE)),
    (
        "Missing server script",
        re.compile(r"Could not find script '(?!clientscripts/_zombie_mode')[^']+'", re.IGNORECASE),
    ),
    ("Unknown GSC function", re.compile(r"unknown function", re.IGNORECASE)),
    ("Sys_Error", re.compile(r"Sys_Error|Fatal error", re.IGNORECASE)),
    ("Fastfile load failure", re.compile(r"ERROR: Could not find zone 'mod'", re.IGNORECASE)),
    (
        "Missing weapon file",
        re.compile(r"WARNING:\s*Could not load weapon file\s+'weapons/sp/", re.IGNORECASE),
    ),
)

GAUNTLET_EVENT_RE = re.compile(r"GAUNTLET_EVENT\|([A-Z0-9_]+)\|(.*)")


@dataclass
class MapSmokeResult:
    map_name: str
    gauntlet_enabled: int
    passed: bool
    duration_s: float
    mod_ff_loaded: bool = False
    events: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    saved_log: Path | None = None


def find_free_display(start: int = 110, end: int = 160) -> int:
    for display_num in range(start, end):
        socket_path = Path(f"/tmp/.X11-unix/X{display_num}")
        lock_path = Path(f"/tmp/.X{display_num}-lock")
        if not socket_path.exists() and not lock_path.exists():
            return display_num
    raise RuntimeError(f"No free X11 display found in :{start}-:{end - 1}")


def start_virtual_display() -> tuple[int, subprocess.Popen[bytes], subprocess.Popen[bytes], TemporaryDirectory[str]]:
    display_num = find_free_display()
    display_str = f":{display_num}"
    xdg_tmp = TemporaryDirectory(prefix="waw_smoke_xdg_")

    xvfb = subprocess.Popen(
        ["Xvfb", display_str, "-screen", "0", "1280x720x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    socket_path = Path(f"/tmp/.X11-unix/X{display_num}")
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if xvfb.poll() is not None:
            xdg_tmp.cleanup()
            raise RuntimeError(f"Xvfb exited unexpectedly with code {xvfb.returncode}")
        if socket_path.exists():
            break
        time.sleep(0.1)
    else:
        xvfb.terminate()
        xdg_tmp.cleanup()
        raise RuntimeError(f"Timed out waiting for Xvfb socket {socket_path}")

    wm_env = os.environ.copy()
    wm_env["DISPLAY"] = display_str
    wm_env["XDG_SESSION_TYPE"] = "x11"
    wm_env["XDG_CONFIG_HOME"] = xdg_tmp.name
    for key in ("WAYLAND_DISPLAY", "WAYLAND_SOCKET", "DESKTOP_STARTUP_ID"):
        wm_env.pop(key, None)

    xfwm = subprocess.Popen(
        ["xfwm4", "--compositor=off"],
        env=wm_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.6)
    return display_num, xvfb, xfwm, xdg_tmp


def stop_virtual_display(
    xvfb: subprocess.Popen[bytes],
    xfwm: subprocess.Popen[bytes],
    xdg_tmp: TemporaryDirectory[str],
) -> None:
    for proc in (xfwm, xvfb):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    xdg_tmp.cleanup()


def kill_prefix_wineserver(proton: Path, playtest_prefix: Path) -> None:
    wineserver = proton.parent / "files" / "bin" / "wineserver"
    pfx = playtest_prefix / "pfx"
    if wineserver.is_file() and pfx.is_dir():
        env = os.environ.copy()
        env["WINEPREFIX"] = str(pfx)
        try:
            subprocess.run(
                [str(wineserver), "-k"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            pass
        try:
            subprocess.run(
                [str(wineserver), "-w"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            pass


def read_console_logs(appdata: Path) -> tuple[str, Path | None]:
    candidates = [
        appdata / "mods" / build_mod.MOD_NAME / "console.log",
        appdata / "main" / "console.log",
    ]
    existing = [p for p in candidates if p.is_file() and p.stat().st_size > 0]
    if not existing:
        return "", None
    # Prefer the most recently modified non-empty log
    latest = max(existing, key=lambda p: p.stat().st_mtime)
    return latest.read_text(encoding="latin1", errors="replace"), latest


def clear_previous_run_state(appdata: Path) -> None:
    # Remove WaW's crash-recovery sentinel so the "Run in Safe Mode?" modal never triggers.
    (appdata / "__CoDWaW").unlink(missing_ok=True)
    for rel in (f"mods/{build_mod.MOD_NAME}/console.log", "main/console.log"):
        (appdata / rel).unlink(missing_ok=True)


def analyze_log(
    log_text: str,
    map_name: str,
    gauntlet_enabled: int,
) -> tuple[bool, list[str], list[str]]:
    mod_loaded_ff = bool(re.search(r"Loading fastfile '?mod'?", log_text, re.IGNORECASE))
    events: list[str] = []
    for line in log_text.splitlines():
        match = GAUNTLET_EVENT_RE.search(line)
        if match:
            events.append(f"GAUNTLET_EVENT|{match.group(1)}|{match.group(2).strip()}")

    errors: list[str] = []
    for label, pattern in FATAL_LOG_PATTERNS:
        for line in log_text.splitlines():
            if pattern.search(line):
                errors.append(f"{label}: {line.strip()}")
                break

    expected_mod_loaded = (
        f"GAUNTLET_EVENT|MOD_LOADED|map={map_name};gauntlet_enabled={gauntlet_enabled}"
    )
    if expected_mod_loaded not in events:
        errors.append(f"Missing expected event: {expected_mod_loaded}")

    if gauntlet_enabled == 1:
        expected_ready = f"GAUNTLET_EVENT|GAUNTLET_READY|map={map_name}"
        if expected_ready not in events:
            errors.append(f"Missing expected event: {expected_ready}")

    if not mod_loaded_ff:
        errors.append("mod.ff was not reported as loaded in console.log")

    return mod_loaded_ff, events, errors


def smoke_map(
    map_name: str,
    gauntlet_enabled: int,
    display_num: int,
    xdg_config_home: str,
    proton: Path,
    steam_root: Path,
    steam_game: Path,
    playtest_prefix: Path,
    timeout_s: float,
    settle_s: float,
) -> MapSmokeResult:
    appdata = (
        playtest_prefix
        / "pfx/drive_c/users/steamuser/AppData/Local/Activision/CoDWaW"
    )
    clear_previous_run_state(appdata)

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
        "+set",
        "gauntlet_enabled",
        str(gauntlet_enabled),
        "+map",
        map_name,
    ]

    expected_mod_loaded = (
        f"GAUNTLET_EVENT|MOD_LOADED|map={map_name};gauntlet_enabled={gauntlet_enabled}"
    )

    t0 = time.monotonic()
    log_text = ""
    timed_out = False
    for attempt in range(2):
        clear_previous_run_state(appdata)
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
        found_at: float | None = None
        timed_out = False
        init_stall_retry = False
        init_stall_seen_at: float | None = None
        last_log_len = 0
        last_log_growth_at = attempt_t0
        try:
            while True:
                now = time.monotonic()
                log_text, _ = read_console_logs(appdata)
                if len(log_text) != last_log_len:
                    last_log_len = len(log_text)
                    last_log_growth_at = now

                # Fast-fail if a fatal error appears in the log
                fatal_hit = any(pat.search(log_text) for _, pat in FATAL_LOG_PATTERNS)
                if fatal_hit:
                    break

                if expected_mod_loaded in log_text:
                    if found_at is None:
                        found_at = now
                    elif now - found_at >= settle_s:
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
                    # Re-read once after exit in case the final buffer flushed
                    time.sleep(0.3)
                    log_text, _ = read_console_logs(appdata)
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
            kill_prefix_wineserver(proton, playtest_prefix)
            time.sleep(0.5)
            # Re-read log after process teardown to capture flushed lines
            final_log, _ = read_console_logs(appdata)
            if len(final_log) >= len(log_text):
                log_text = final_log
            (appdata / "__CoDWaW").unlink(missing_ok=True)

        if not init_stall_retry:
            break

    duration_s = time.monotonic() - t0
    SMOKE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    saved_log = SMOKE_LOG_DIR / f"{map_name}_gauntlet{gauntlet_enabled}.console.log"
    saved_log.write_text(log_text, encoding="utf-8", errors="replace")

    mod_ff_loaded, events, errors = analyze_log(log_text, map_name, gauntlet_enabled)
    if timed_out and expected_mod_loaded not in events:
        errors.insert(0, f"Timed out after {timeout_s:.1f}s waiting for {expected_mod_loaded}")

    return MapSmokeResult(
        map_name=map_name,
        gauntlet_enabled=gauntlet_enabled,
        passed=len(errors) == 0,
        duration_s=duration_s,
        mod_ff_loaded=mod_ff_loaded,
        events=events,
        errors=errors,
        saved_log=saved_log,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--maps",
        nargs="+",
        default=list(build_mod.STOCK_MAPS),
        choices=list(build_mod.STOCK_MAPS),
        help="Stock maps to smoke-test (default: all 4 stock Nazi Zombies maps).",
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        type=int,
        default=[0],
        choices=[0, 1],
        help="gauntlet_enabled values to verify (default: 0 for Classic Mode).",
    )
    parser.add_argument("--skip-build", action="store_true", help="Skip building mod.ff before launching.")
    parser.add_argument("--timeout", type=float, default=75.0, help="Per-map timeout in seconds.")
    parser.add_argument("--settle", type=float, default=2.5, help="Post-MOD_LOADED settle wait in seconds.")
    parser.add_argument("--tools-root", type=Path, default=build_mod.DEFAULT_TOOLS_ROOT)
    parser.add_argument("--steam-root", type=Path, default=build_mod.DEFAULT_STEAM_ROOT)
    parser.add_argument("--dev-root", type=Path, default=build_mod.DEFAULT_DEV_ROOT)
    parser.add_argument("--steam-game", type=Path, default=build_mod.DEFAULT_STEAM_GAME)
    parser.add_argument("--steam-appdata", type=Path, default=build_mod.DEFAULT_STEAM_APPDATA)
    parser.add_argument("--playtest-prefix", type=Path, default=DEFAULT_PLAYTEST_PREFIX)
    parser.add_argument("--proton", type=Path, default=DEFAULT_PROTON)
    args = parser.parse_args(argv)

    playtest_appdata = (
        args.playtest_prefix
        / "pfx/drive_c/users/steamuser/AppData/Local/Activision/CoDWaW"
    )
    if not playtest_appdata.is_dir():
        print(
            f"ERROR: Playtest Proton prefix AppData folder is missing: {playtest_appdata}",
            file=sys.stderr,
        )
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
        for artifact_name in ("mod.ff", f"{build_mod.MOD_NAME}.iwd"):
            artifact = build_mod.DIST_DIR / artifact_name
            if not artifact.is_file():
                print(f"ERROR: --skip-build specified but {artifact} does not exist", file=sys.stderr)
                return 1
        for target in deploy_targets:
            for dest in build_mod.deploy_mod(build_mod.DIST_DIR, target):
                print(f"Deployed {dest}")

    print("\n=== Starting headless Xvfb display for CoD:WaW smoke verification ===")
    display_num, xvfb, xfwm, xdg_tmp = start_virtual_display()
    results: list[MapSmokeResult] = []
    try:
        for mode in args.modes:
            for map_name in args.maps:
                print(f"\n--> Launching {map_name} (gauntlet_enabled={mode}) on :{display_num} ...")
                res = smoke_map(
                    map_name=map_name,
                    gauntlet_enabled=mode,
                    display_num=display_num,
                    xdg_config_home=xdg_tmp.name,
                    proton=args.proton,
                    steam_root=args.steam_root,
                    steam_game=args.steam_game,
                    playtest_prefix=args.playtest_prefix,
                    timeout_s=args.timeout,
                    settle_s=args.settle,
                )
                results.append(res)
                status = "PASS" if res.passed else "FAIL"
                print(
                    f"    [{status}] {map_name} (gauntlet_enabled={mode}) "
                    f"in {res.duration_s:.1f}s | mod.ff={res.mod_ff_loaded} | "
                    f"events={res.events}"
                )
                for err in res.errors:
                    print(f"    ERROR: {err}", file=sys.stderr)
                if res.saved_log:
                    print(f"    log: {res.saved_log}")
    finally:
        stop_virtual_display(xvfb, xfwm, xdg_tmp)

    print("\n=== Smoke Verification Summary ===")
    passed_count = sum(1 for r in results if r.passed)
    for r in results:
        tag = "PASS" if r.passed else "FAIL"
        print(
            f"  [{tag}] {r.map_name:24s} gauntlet_enabled={r.gauntlet_enabled} "
            f"({r.duration_s:.1f}s) events={len(r.events)}"
        )
    print(f"Total: {passed_count}/{len(results)} passed")
    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
