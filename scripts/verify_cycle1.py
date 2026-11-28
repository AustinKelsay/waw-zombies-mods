#!/usr/bin/env python3
"""Real in-engine Solo Cycle 1 4-map verification harness for Zombie Gauntlet.

Launches a single continuous CoDWaW.exe Solo process starting on
nazi_zombie_prototype with deterministic test dvars and verifies:
  1. Automatic ChangeLevel progression across all 4 stock maps:
     Nacht (prototype) -> Verruckt (asylum) -> Shi No Numa (sumpf) -> Der Riese (factory)
     -> wrap-around to Cycle 2 Stage 1 on Nacht (prototype).
  2. Structured GAUNTLET_EVENT telemetry for STAGE_INIT, POINTS_APPLIED,
     POINTS_SAVED, STAGE_CLEAR, and STAGE_TRANSITION (mode=solo).
  3. Authentic player points carryover across every Stage Transition (with
     Points Floor applied on Cycle 2 Stage 1).
  4. Zero fatal engine, script, or asset-limit errors.
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

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_mod  # noqa: E402
import smoke_verify  # noqa: E402

TEST_CYCLE1_ORDER = "nazi_zombie_prototype,nazi_zombie_sumpf,nazi_zombie_asylum,nazi_zombie_factory"
TEST_CYCLE2_ORDER = "nazi_zombie_asylum,nazi_zombie_prototype,nazi_zombie_factory,nazi_zombie_sumpf"

EXPECTED_CYCLE1_MAPS: tuple[tuple[int, int, str], ...] = (
    (1, 1, "nazi_zombie_prototype"),
    (1, 2, "nazi_zombie_sumpf"),
    (1, 3, "nazi_zombie_asylum"),
    (1, 4, "nazi_zombie_factory"),
    (2, 1, "nazi_zombie_asylum"),
)


def expected_cycle1_sequence(stage_span: int = 1) -> tuple[tuple[int, int, str, int, int], ...]:
    """Compute (cycle, stage, map, start_round, target_round) for any fixed stage span."""
    span = max(1, int(stage_span))
    return tuple(
        (c, s, m, 1 + idx * span, (idx + 1) * span)
        for idx, (c, s, m) in enumerate(EXPECTED_CYCLE1_MAPS)
    )


EXPECTED_CYCLE1_SEQUENCE: tuple[tuple[int, int, str, int, int], ...] = expected_cycle1_sequence(1)


@dataclass(frozen=True)
class GauntletEvent:
    event_type: str
    fields: dict[str, str]
    raw: str


@dataclass
class Cycle1VerifyResult:
    passed: bool
    duration_s: float
    events: list[GauntletEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    saved_log: Path | None = None


def parse_gauntlet_events(log_text: str) -> list[GauntletEvent]:
    """Parse structured GAUNTLET_EVENT|<TYPE>|<k=v;...> lines from console.log."""
    events: list[GauntletEvent] = []
    for line in log_text.splitlines():
        match = smoke_verify.GAUNTLET_EVENT_RE.search(line)
        if not match:
            continue
        event_type = match.group(1)
        payload = match.group(2).strip()
        fields: dict[str, str] = {}
        if payload:
            for item in payload.split(";"):
                if "=" in item:
                    k, v = item.split("=", 1)
                    fields[k.strip()] = v.strip()
        raw = f"GAUNTLET_EVENT|{event_type}|{payload}"
        events.append(GauntletEvent(event_type=event_type, fields=fields, raw=raw))
    return events


def is_cycle1_complete(events: list[GauntletEvent], expected_stage_span: int = 1) -> bool:
    """Return True once Cycle 2 Stage 1 has initialized and applied player points."""
    exp_c, exp_s, exp_map, exp_start, _ = expected_cycle1_sequence(expected_stage_span)[-1]
    saw_c2_init = False
    for ev in events:
        if (
            ev.event_type == "STAGE_INIT"
            and ev.fields.get("cycle") == str(exp_c)
            and ev.fields.get("stage") == str(exp_s)
            and ev.fields.get("map") == exp_map
        ):
            saw_c2_init = True
        elif (
            saw_c2_init
            and ev.event_type == "POINTS_APPLIED"
            and ev.fields.get("map") == exp_map
            and ev.fields.get("start_round") == str(exp_start)
        ):
            return True
    return False


def _split_stage_slices(events: list[GauntletEvent]) -> list[list[GauntletEvent]]:
    """Group events into slices starting at each STAGE_INIT event."""
    slices: list[list[GauntletEvent]] = []
    current: list[GauntletEvent] | None = None
    for ev in events:
        if ev.event_type == "STAGE_INIT":
            current = [ev]
            slices.append(current)
        elif current is not None:
            current.append(ev)
    return slices


def analyze_cycle1_log(
    log_text: str,
    expected_stage_span: int = 1,
) -> tuple[list[GauntletEvent], list[str]]:
    """Validate full Solo Cycle 1 shuffled 4-map continuous progression and points carryover."""
    events = parse_gauntlet_events(log_text)
    errors: list[str] = []
    expected_seq = expected_cycle1_sequence(expected_stage_span)

    for label, pattern in smoke_verify.FATAL_LOG_PATTERNS:
        for line in log_text.splitlines():
            if pattern.search(line):
                errors.append(f"{label}: {line.strip()}")
                break

    # 1. Verify shuffled STAGE_INIT events across all 4 Cycle 1 maps + Cycle 2 wrap
    stage_inits = [e for e in events if e.event_type == "STAGE_INIT"]
    if len(stage_inits) < len(expected_seq):
        errors.append(
            f"Expected at least {len(expected_seq)} STAGE_INIT events "
            f"(4 Cycle 1 stages + Cycle 2 Stage 1 wrap), found {len(stage_inits)}"
        )
    else:
        run_ids: set[str] = set()
        for idx, (exp_cycle, exp_stage, exp_map, exp_start, exp_target) in enumerate(expected_seq):
            ev = stage_inits[idx]
            run_id = ev.fields.get("run_id", "")
            if not run_id:
                errors.append(f"STAGE_INIT #{idx + 1} missing run_id: {ev.raw}")
            else:
                run_ids.add(run_id)

            checks = (
                ("cycle", str(exp_cycle)),
                ("stage", str(exp_stage)),
                ("map", exp_map),
                ("start_round", str(exp_start)),
                ("target_round", str(exp_target)),
            )
            for key, expected_val in checks:
                actual_val = ev.fields.get(key)
                if actual_val != expected_val:
                    errors.append(
                        f"STAGE_INIT #{idx + 1} field {key}={actual_val!r}, "
                        f"expected {expected_val!r} ({ev.raw})"
                    )
        if len(run_ids) != 1:
            errors.append(f"Expected consistent run_id across all stages, got {sorted(run_ids)}")

    # 1b. Verify Prep Phase runs on Cycle 1 Stages 2-4 (start_round > 1) and NOT on Stage 1 (start_round == 1)
    slices = _split_stage_slices(events)
    if len(slices) >= 4:
        s1_prep = [e for e in slices[0] if e.event_type in ("PREP_PHASE_START", "PREP_PHASE_END")]
        if s1_prep:
            errors.append(f"Stage 1 (start_round=1) should not run Prep Phase, found {len(s1_prep)} events")
        for idx in range(1, 4):
            sl = slices[idx]
            exp_cycle, exp_stage, exp_map, _, _ = expected_seq[idx]
            has_start = any(
                e.event_type == "PREP_PHASE_START"
                and e.fields.get("cycle") == str(exp_cycle)
                and e.fields.get("stage") == str(exp_stage)
                and e.fields.get("map") == exp_map
                for e in sl
            )
            has_end = any(
                e.event_type == "PREP_PHASE_END"
                and e.fields.get("cycle") == str(exp_cycle)
                and e.fields.get("stage") == str(exp_stage)
                and e.fields.get("map") == exp_map
                for e in sl
            )
            if not has_start or not has_end:
                errors.append(
                    f"Cycle {exp_cycle} Stage {exp_stage} ({exp_map}) missing Prep Phase "
                    f"events (start={has_start}, end={has_end})"
                )

    # 2. Verify all 4 Cycle 1 STAGE_CLEAR and solo STAGE_TRANSITION events
    stage_clears = [e for e in events if e.event_type == "STAGE_CLEAR"]
    stage_transitions = [e for e in events if e.event_type == "STAGE_TRANSITION"]

    expected_transitions = tuple(
        (
            expected_seq[idx][0],
            expected_seq[idx][1],
            expected_seq[idx][2],
            expected_seq[idx][4],
            expected_seq[idx + 1][0],
            expected_seq[idx + 1][1],
            expected_seq[idx + 1][2],
        )
        for idx in range(4)
    )

    if len(stage_clears) < len(expected_transitions):
        errors.append(
            f"Expected at least {len(expected_transitions)} STAGE_CLEAR events, found {len(stage_clears)}"
        )
    else:
        for idx, (c, s, m, comp_r, nc, ns, nm) in enumerate(expected_transitions):
            ev = stage_clears[idx]
            checks = (
                ("cycle", str(c)),
                ("stage", str(s)),
                ("map", m),
                ("completed_round", str(comp_r)),
                ("next_cycle", str(nc)),
                ("next_stage", str(ns)),
                ("next_map", nm),
            )
            for key, expected_val in checks:
                if ev.fields.get(key) != expected_val:
                    errors.append(
                        f"STAGE_CLEAR #{idx + 1} field {key}={ev.fields.get(key)!r}, "
                        f"expected {expected_val!r} ({ev.raw})"
                    )

    if len(stage_transitions) < len(expected_transitions):
        errors.append(
            f"Expected at least {len(expected_transitions)} STAGE_TRANSITION events, "
            f"found {len(stage_transitions)}"
        )
    else:
        for idx, (_, _, _, _, nc, ns, nm) in enumerate(expected_transitions):
            ev = stage_transitions[idx]
            checks = (
                ("mode", "solo"),
                ("next_map", nm),
                ("next_cycle", str(nc)),
                ("next_stage", str(ns)),
            )
            for key, expected_val in checks:
                if ev.fields.get(key) != expected_val:
                    errors.append(
                        f"STAGE_TRANSITION #{idx + 1} field {key}={ev.fields.get(key)!r}, "
                        f"expected {expected_val!r} ({ev.raw})"
                    )

    # 3. Verify player points carryover across all 4 continuous Stage Transitions
    points_applied = [e for e in events if e.event_type == "POINTS_APPLIED"]
    points_saved = [e for e in events if e.event_type == "POINTS_SAVED"]
    if len(points_applied) < 5 or len(points_saved) < 4:
        errors.append(
            f"Expected >=5 POINTS_APPLIED and >=4 POINTS_SAVED events, "
            f"found {len(points_applied)} applied and {len(points_saved)} saved"
        )
    else:
        applied_vals = [int(e.fields["points"]) for e in points_applied[:5]]
        saved_vals = [int(e.fields["points"]) for e in points_saved[:4]]

        if applied_vals[0] != 500:
            errors.append(f"Stage 1 starting points should be 500, got {applied_vals[0]}")

        for idx in range(4):
            if saved_vals[idx] <= applied_vals[idx]:
                errors.append(
                    f"Stage {idx + 1} did not earn kill points before Stage Clear: "
                    f"applied={applied_vals[idx]}, saved={saved_vals[idx]}"
                )

        # Continuous Points Floors + carried-balance verification across every transition
        for idx in range(4):
            saved_ev = points_saved[idx]
            dest_ev = points_applied[idx + 1]
            next_start_round = expected_seq[idx + 1][3]
            floor_pts = max(500, next_start_round * 500)
            expected_pts = max(saved_vals[idx], floor_pts)
            if saved_ev.fields.get("player") != dest_ev.fields.get("player"):
                errors.append(
                    f"Points carryover player mismatch into Stage #{idx + 2}: "
                    f"saved player={saved_ev.fields.get('player')!r}, "
                    f"applied player={dest_ev.fields.get('player')!r}"
                )
            if dest_ev.fields.get("carried") != str(saved_vals[idx]):
                errors.append(
                    f"Points carryover carried mismatch into Stage #{idx + 2}: "
                    f"carried={dest_ev.fields.get('carried')!r}, expected {str(saved_vals[idx])!r} ({dest_ev.raw})"
                )
            if applied_vals[idx + 1] != expected_pts:
                errors.append(
                    f"Points carryover mismatch into Stage #{idx + 2} (start_round={next_start_round}): "
                    f"expected {expected_pts} (max(saved={saved_vals[idx]}, floor={floor_pts})), "
                    f"got {applied_vals[idx + 1]}"
                )

    return events, errors


def run_cycle1_verification(
    display_num: int,
    xdg_config_home: str,
    proton: Path,
    steam_root: Path,
    steam_game: Path,
    playtest_prefix: Path,
    timeout_s: float,
    target_round: int,
    banner_delay: float,
) -> Cycle1VerifyResult:
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
        "+set",
        "gauntlet_active",
        "0",
        "+set",
        "gauntlet_test_cycle_order",
        TEST_CYCLE1_ORDER,
        "+set",
        "gauntlet_test_next_cycle_order",
        TEST_CYCLE2_ORDER,
        "+set",
        "gauntlet_test_stage_span",
        str(target_round),
        "+set",
        "gauntlet_test_target_round",
        "0",
        "+set",
        "gauntlet_test_prep_duration",
        "1",
        "+set",
        "gauntlet_test_banner_delay",
        str(banner_delay),
        "+set",
        "gauntlet_test_autoclear",
        "1",
        "+map",
        "nazi_zombie_prototype",
    ]

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
    try:
        while True:
            now = time.monotonic()
            log_text, _ = smoke_verify.read_console_logs(appdata)
            parsed = parse_gauntlet_events(log_text)
            if len(parsed) > last_event_count:
                for ev in parsed[last_event_count:]:
                    print(f"    [{now - t0:5.1f}s] {ev.raw}")
                last_event_count = len(parsed)

            if any(pat.search(log_text) for _, pat in smoke_verify.FATAL_LOG_PATTERNS):
                break

            if is_cycle1_complete(parsed, expected_stage_span=target_round):
                time.sleep(0.8)
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
    saved_log = smoke_verify.SMOKE_LOG_DIR / "cycle1_solo_4map.console.log"
    saved_log.write_text(log_text, encoding="utf-8", errors="replace")

    events, errors = analyze_cycle1_log(log_text, expected_stage_span=target_round)
    if timed_out and not is_cycle1_complete(events, expected_stage_span=target_round):
        errors.insert(0, f"Timed out after {timeout_s:.1f}s before completing 4-map Cycle 1 run")

    return Cycle1VerifyResult(
        passed=len(errors) == 0,
        duration_s=duration_s,
        events=events,
        errors=errors,
        saved_log=saved_log,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="Skip building mod.ff before launching.")
    parser.add_argument("--timeout", type=float, default=180.0, help="Total timeout in seconds.")
    parser.add_argument("--target-round", type=int, default=1, help="gauntlet_test_target_round override.")
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

    print("\n=== Starting headless Xvfb display for Solo 4-Map Cycle 1 verification ===")
    display_num, xvfb, xfwm, xdg_tmp = smoke_verify.start_virtual_display()
    try:
        print(
            f"--> Launching continuous Solo Run on nazi_zombie_prototype "
            f"(target_round={args.target_round}, banner_delay={args.banner_delay}, autoclear=1)..."
        )
        res = run_cycle1_verification(
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=args.timeout,
            target_round=args.target_round,
            banner_delay=args.banner_delay,
        )
    finally:
        smoke_verify.stop_virtual_display(xvfb, xfwm, xdg_tmp)

    status = "PASS" if res.passed else "FAIL"
    print(f"\n=== Solo 4-Map Cycle 1 Verification: [{status}] ({res.duration_s:.1f}s) ===")
    print(f"Total GAUNTLET_EVENT lines captured: {len(res.events)}")
    if res.saved_log:
        print(f"Saved console log: {res.saved_log}")
    for err in res.errors:
        print(f"  ERROR: {err}", file=sys.stderr)
    return 0 if res.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
