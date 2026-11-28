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
import shutil
import sys
from pathlib import Path

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


def _cycle2_nacht_perks_settled(events: list[GauntletEvent]) -> bool:
    """Stop once Cycle 2 Nacht has restored perks AND spawned a Round 10 zombie."""
    has_restored = any(
        e.event_type == "PERKS_RESTORED" and e.fields.get("map") == "nazi_zombie_prototype"
        for e in events
    )
    if not has_restored:
        return False
    return any(
        e.event_type == "ZOMBIE_SPAWNED_SAMPLE" and e.fields.get("round") == "10"
        for e in events
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--tools-root", type=Path, default=build_mod.DEFAULT_TOOLS_ROOT)
    parser.add_argument("--steam-root", type=Path, default=build_mod.DEFAULT_STEAM_ROOT)
    parser.add_argument("--dev-root", type=Path, default=build_mod.DEFAULT_DEV_ROOT)
    parser.add_argument("--steam-game", type=Path, default=build_mod.DEFAULT_STEAM_GAME)
    parser.add_argument("--steam-appdata", type=Path, default=build_mod.DEFAULT_STEAM_APPDATA)
    parser.add_argument("--playtest-prefix", type=Path, default=smoke_verify.DEFAULT_PLAYTEST_PREFIX)
    parser.add_argument("--proton", type=Path, default=smoke_verify.DEFAULT_PROTON)
    args = parser.parse_args(argv)

    import verify_cycle2

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
        for target in deploy_targets:
            for dest in build_mod.deploy_mod(build_mod.DIST_DIR, target):
                print(f"Deployed {dest}")

    print("\n=== Starting headless Xvfb display for Cross-map Perk Carryover verification ===")
    display_num, xvfb, xfwm, xdg_tmp = smoke_verify.start_virtual_display()
    all_errors: list[str] = []
    try:
        # Scenario A: Der Riese (C1 S4) with Juggernog + Speed Cola -> Cycle 2 Nacht der Untoten
        print("\n--> Scenario A: Der Riese (C1 S4, Juggernog + Speed Cola) -> Cycle 2 Nacht der Untoten")
        res_a = verify_cycle2.run_waw_scenario(
            name="Der Riese -> Cycle 2 Nacht perk carryover",
            log_filename="perks_c1s4_to_c2_nacht.console.log",
            start_map="nazi_zombie_factory",
            extra_dvars=[
                ("gauntlet_active", "1"),
                ("gauntlet_run_id", "verify_perks_run"),
                ("gauntlet_cycle", "1"),
                ("gauntlet_stage", "4"),
                ("gauntlet_cycle_order", "nazi_zombie_prototype,nazi_zombie_asylum,nazi_zombie_sumpf,nazi_zombie_factory"),
                ("gauntlet_start_round", "9"),
                ("gauntlet_target_round", "9"),
                ("gauntlet_total_rounds", "8"),
                ("gauntlet_pending_transition", "1"),
                ("gauntlet_player_perks", ""),
                ("gauntlet_test_next_cycle_order", "nazi_zombie_prototype,nazi_zombie_sumpf,nazi_zombie_asylum,nazi_zombie_factory"),
                ("gauntlet_test_stage_span", "5"),
                ("gauntlet_test_grant_perks", "j,f"),
                ("gauntlet_test_target_round", "9"),
                ("gauntlet_test_autoclear", "1"),
                ("gauntlet_test_banner_delay", "1.0"),
                ("gauntlet_test_prep_duration", "2"),
            ],
            stop_predicate=_cycle2_nacht_perks_settled,
            analyzer=analyze_perk_carryover_log,
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=args.timeout,
        )
        if res_a.passed:
            print(
                f"  [PASS] Scenario A (Der Riese -> Cycle 2 Nacht perks, Jugg 160 HP) "
                f"({res_a.duration_s:.1f}s) — {res_a.saved_log}"
            )
        else:
            print(f"  [FAIL] Scenario A (Der Riese -> Cycle 2 Nacht perks) — {res_a.saved_log}")
            for err in res_a.errors:
                print(f"        ERROR: {err}", file=sys.stderr)
            all_errors.extend(res_a.errors)

        # Scenario B: Classic Mode zero perk telemetry
        print("\n--> Scenario B: Classic Mode (gauntlet_enabled=0) zero perk carryover telemetry")
        res_b = smoke_verify.smoke_map(
            map_name="nazi_zombie_prototype",
            gauntlet_enabled=0,
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=min(args.timeout, 90.0),
            settle_s=2.5,
        )
        log_b = (
            res_b.saved_log.read_text(encoding="utf-8", errors="replace")
            if res_b.saved_log and res_b.saved_log.is_file()
            else ""
        )
        _, errs_b = analyze_classic_perks_isolation_log(log_b)
        combined_b = list(res_b.errors) + errs_b
        if not combined_b:
            print(
                f"  [PASS] Scenario B (Classic Mode perk isolation) "
                f"({res_b.duration_s:.1f}s) — {res_b.saved_log}"
            )
        else:
            print(f"  [FAIL] Scenario B (Classic Mode perk isolation) — {res_b.saved_log}")
            for err in combined_b:
                print(f"        ERROR: {err}", file=sys.stderr)
            all_errors.extend(combined_b)
    finally:
        smoke_verify.stop_virtual_display(xvfb, xfwm, xdg_tmp)

    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
