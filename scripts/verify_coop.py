#!/usr/bin/env python3
"""Real in-engine Co-op lobby-assisted Stage Transition and squad roster verification harness.

Runs focused CoDWaW.exe verification scenarios against the built waw_gauntlet mod:
  1. Co-op Stage Clear on Nacht der Untoten (gauntlet_test_force_coop=1):
     - Verifies STAGE_CLEAR, POINTS_SAVED, and STAGE_TRANSITION|mode=coop
       with next_map=nazi_zombie_asylum and player_count>=1.
     - Verifies SetUINextLevel + ui_mapname + exitLevel(false) without calling
       in-game ChangeLevel() (no nazi_zombie_asylum fastfile load / second STAGE_INIT).
     - Verifies persisted host dvars: gauntlet_active=1, gauntlet_pending_transition=1,
       gauntlet_next_map=nazi_zombie_asylum, gauntlet_next_display=Verruckt,
       gauntlet_lobby_status="NEXT STAGE: C1 S2/4 - Verruckt (R1-R10)".
  2. Co-op next-Stage launch on Verruckt (nazi_zombie_asylum, Cycle 2 Stage 2, R10):
     Seeded with persisted Co-op host dvars testing all 4 squad roster recovery roles
     against real CoDWaW.exe player entities:
       - 2a: Returning player with surplus (12400 > 5000 floor) -> role=returning, 12400 pts
       - 2b: Dead/spectating player at Stage Clear (0 pts) -> role=spectator, 5000 pts
       - 2c: Late joiner (unrecorded in ledger) -> role=late_joiner, 5000 pts
       - 2d: Reconnecting player (dropped mid-Run with 8750 pts) -> role=reconnecting, 8750 pts
  3. Stale-lobby / fresh-Run reset guard on Nacht der Untoten:
       - 3a: Stale state (gauntlet_active=1; cycle=2; stage=3; pending_transition=0; 25000 pts)
             triggers RUN_RESET|reason=stale_no_pending_transition and starts fresh at
             Cycle 1, Stage 1, Round 1 with 500 points.
       - 3b: Explicit gauntlet_fresh_run=1 (even with matching pending_transition=1)
             triggers RUN_RESET|reason=fresh_run_requested and starts fresh at
             Cycle 1, Stage 1, Round 1 with 500 points.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_mod  # noqa: E402
import smoke_verify  # noqa: E402
import verify_cycle1  # noqa: E402
import verify_cycle2  # noqa: E402

GauntletEvent = verify_cycle1.GauntletEvent
ScenarioResult = verify_cycle2.ScenarioResult

DVAR_SET_RE = re.compile(r"^\s*dvar set\s+([A-Za-z0-9_]+)(?:\s(.*))?$")


def parse_dvar_history(log_text: str) -> dict[str, list[str]]:
    """Return all logged `dvar set <name> <val>` transitions in chronological order."""
    history: dict[str, list[str]] = {}
    for line in log_text.splitlines():
        match = DVAR_SET_RE.match(line.rstrip("\r"))
        if not match:
            continue
        name = match.group(1).lower()
        val = (match.group(2) or "").strip()
        history.setdefault(name, []).append(val)
    return history


def latest_dvar_values(log_text: str) -> dict[str, str]:
    """Return the last logged value for each dvar seen in console.log."""
    return {k: vals[-1] for k, vals in parse_dvar_history(log_text).items() if vals}


def analyze_coop_stage_clear_log(
    log_text: str,
    expected_next_map: str = "nazi_zombie_asylum",
    expected_next_display: str = "Verruckt",
    expected_lobby_status: str = "NEXT STAGE: C1 S2/4 - Verruckt (R1-R10)",
) -> tuple[list[GauntletEvent], list[str]]:
    """Validate Scenario 1: Co-op Stage Clear -> lobby handoff without ChangeLevel()."""
    events = verify_cycle1.parse_gauntlet_events(log_text)
    errors: list[str] = []
    verify_cycle2._check_fatal_patterns(log_text, errors)

    stage_inits = [e for e in events if e.event_type == "STAGE_INIT"]
    if len(stage_inits) != 1:
        errors.append(
            f"Expected exactly 1 STAGE_INIT (no ChangeLevel into next map), found {len(stage_inits)}"
        )
    else:
        init0 = stage_inits[0]
        for k, exp in (("cycle", "1"), ("stage", "1"), ("map", "nazi_zombie_prototype")):
            if init0.fields.get(k) != exp:
                errors.append(f"STAGE_INIT {k}={init0.fields.get(k)!r}, expected {exp!r}")

    # Ensure ChangeLevel did NOT load the next map fastfile
    next_map_load_re = re.compile(
        rf"Loading fastfile\s+'?{re.escape(expected_next_map)}'?", re.IGNORECASE
    )
    if next_map_load_re.search(log_text):
        errors.append(
            f"Co-op transition unexpectedly triggered ChangeLevel() load of {expected_next_map}"
        )

    pts_saved = [e for e in events if e.event_type == "POINTS_SAVED"]
    if not pts_saved:
        errors.append("Missing POINTS_SAVED event on Co-op Stage Clear")
    else:
        saved_pts = int(pts_saved[0].fields.get("points", "0"))
        if saved_pts <= 500:
            errors.append(f"Expected POINTS_SAVED > 500 after killing enemies, got {saved_pts}")

    clear_events = [e for e in events if e.event_type == "STAGE_CLEAR"]
    if not clear_events:
        errors.append("Missing STAGE_CLEAR event")
    else:
        ce = clear_events[0]
        for k, exp in (
            ("cycle", "1"),
            ("stage", "1"),
            ("map", "nazi_zombie_prototype"),
            ("next_cycle", "1"),
            ("next_stage", "2"),
            ("next_map", expected_next_map),
        ):
            if ce.fields.get(k) != exp:
                errors.append(f"STAGE_CLEAR {k}={ce.fields.get(k)!r}, expected {exp!r} ({ce.raw})")

    trans_events = [e for e in events if e.event_type == "STAGE_TRANSITION"]
    if not trans_events:
        errors.append("Missing STAGE_TRANSITION event")
    else:
        te = trans_events[0]
        for k, exp in (
            ("mode", "coop"),
            ("next_map", expected_next_map),
            ("next_cycle", "1"),
            ("next_stage", "2"),
        ):
            if te.fields.get(k) != exp:
                errors.append(
                    f"STAGE_TRANSITION {k}={te.fields.get(k)!r}, expected {exp!r} ({te.raw})"
                )
        pc_raw = te.fields.get("player_count", "")
        try:
            pc = int(pc_raw)
        except ValueError:
            errors.append(f"STAGE_TRANSITION missing integer player_count: {te.raw}")
        else:
            if pc < 1:
                errors.append(f"STAGE_TRANSITION player_count={pc}, expected >= 1")

    # Ensure exitLevel(false) returned cleanly to UI/lobby without calling ChangeLevel
    returned_to_ui = bool(
        re.search(r"Loading fastfile\s+'?ui'?", log_text, re.IGNORECASE)
        or re.search(r"^\s*dvar set\s+cl_ingame\s+0\b", log_text, re.MULTILINE)
    )
    if not returned_to_ui:
        errors.append(
            "Expected exitLevel(false) to unload map and return to UI/lobby (missing ui load / cl_ingame 0)"
        )

    dvars = latest_dvar_values(log_text)
    expected_dvars = (
        ("gauntlet_active", "1"),
        ("gauntlet_pending_transition", "1"),
        ("gauntlet_next_map", expected_next_map),
        ("gauntlet_next_display", expected_next_display),
        ("gauntlet_lobby_status", expected_lobby_status),
    )
    for dvar_key, exp_val in expected_dvars:
        actual = dvars.get(dvar_key)
        if actual != exp_val:
            errors.append(
                f"Persisted dvar {dvar_key}={actual!r}, expected {exp_val!r}"
            )

    return events, errors


def analyze_roster_recovery_log(
    log_text: str,
    expected_role: str,
    expected_points: int,
    expected_carried: str,
    expected_floor: int = 5000,
    expected_cycle: int = 2,
    expected_stage: int = 2,
    expected_map: str = "nazi_zombie_asylum",
    expected_start_round: int = 10,
) -> tuple[list[GauntletEvent], list[str]]:
    """Validate Scenario 2 sub-runs: next-Stage Co-op launch & roster role resolution."""
    events = verify_cycle1.parse_gauntlet_events(log_text)
    errors: list[str] = []
    verify_cycle2._check_fatal_patterns(log_text, errors)

    if any(e.event_type == "RUN_RESET" for e in events):
        errors.append("Unexpected RUN_RESET during valid Co-op Stage transition")

    stage_inits = [e for e in events if e.event_type == "STAGE_INIT"]
    if not stage_inits:
        errors.append("Missing STAGE_INIT event")
    else:
        si = stage_inits[0]
        for k, exp in (
            ("cycle", str(expected_cycle)),
            ("stage", str(expected_stage)),
            ("map", expected_map),
            ("start_round", str(expected_start_round)),
        ):
            if si.fields.get(k) != exp:
                errors.append(f"STAGE_INIT {k}={si.fields.get(k)!r}, expected {exp!r} ({si.raw})")

    roster_events = [e for e in events if e.event_type == "PLAYER_ROSTER_RESOLVED"]
    if not roster_events:
        errors.append("Missing PLAYER_ROSTER_RESOLVED event")
    else:
        re_ev = roster_events[0]
        for k, exp in (
            ("role", expected_role),
            ("points", str(expected_points)),
            ("carried", expected_carried),
            ("floor", str(expected_floor)),
            ("map", expected_map),
        ):
            if re_ev.fields.get(k) != exp:
                errors.append(
                    f"PLAYER_ROSTER_RESOLVED {k}={re_ev.fields.get(k)!r}, "
                    f"expected {exp!r} ({re_ev.raw})"
                )

    applied_events = [e for e in events if e.event_type == "POINTS_APPLIED"]
    if not applied_events:
        errors.append("Missing POINTS_APPLIED event")
    else:
        pa = applied_events[0]
        for k, exp in (
            ("points", str(expected_points)),
            ("start_round", str(expected_start_round)),
            ("map", expected_map),
            ("carried", expected_carried),
            ("floor", str(expected_floor)),
        ):
            if pa.fields.get(k) != exp:
                errors.append(
                    f"POINTS_APPLIED {k}={pa.fields.get(k)!r}, expected {exp!r} ({pa.raw})"
                )

    return events, errors


def analyze_stale_reset_log(
    log_text: str,
    expected_reason: str,
    stale_run_id: str,
) -> tuple[list[GauntletEvent], list[str]]:
    """Validate Scenario 3: stale-lobby / fresh-Run reset wipes persisted dvars cleanly."""
    events = verify_cycle1.parse_gauntlet_events(log_text)
    errors: list[str] = []
    verify_cycle2._check_fatal_patterns(log_text, errors)

    reset_events = [e for e in events if e.event_type == "RUN_RESET"]
    if not reset_events:
        errors.append("Missing expected RUN_RESET event")
    else:
        rr = reset_events[0]
        if rr.fields.get("reason") != expected_reason:
            errors.append(
                f"RUN_RESET reason={rr.fields.get('reason')!r}, expected {expected_reason!r} ({rr.raw})"
            )
        if rr.fields.get("map") != "nazi_zombie_prototype":
            errors.append(
                f"RUN_RESET map={rr.fields.get('map')!r}, expected 'nazi_zombie_prototype' ({rr.raw})"
            )

    stage_inits = [e for e in events if e.event_type == "STAGE_INIT"]
    if not stage_inits:
        errors.append("Missing STAGE_INIT after RUN_RESET")
    else:
        si = stage_inits[0]
        for k, exp in (
            ("cycle", "1"),
            ("stage", "1"),
            ("map", "nazi_zombie_prototype"),
            ("start_round", "1"),
        ):
            if si.fields.get(k) != exp:
                errors.append(f"STAGE_INIT {k}={si.fields.get(k)!r}, expected {exp!r} ({si.raw})")
        if si.fields.get("run_id") == stale_run_id:
            errors.append(f"Stale run_id {stale_run_id!r} leaked after RUN_RESET")

    roster_events = [e for e in events if e.event_type == "PLAYER_ROSTER_RESOLVED"]
    if not roster_events:
        errors.append("Missing PLAYER_ROSTER_RESOLVED after RUN_RESET")
    else:
        re_ev = roster_events[0]
        for k, exp in (
            ("role", "late_joiner"),
            ("points", "500"),
            ("carried", "none"),
            ("floor", "500"),
            ("map", "nazi_zombie_prototype"),
        ):
            if re_ev.fields.get(k) != exp:
                errors.append(
                    f"PLAYER_ROSTER_RESOLVED {k}={re_ev.fields.get(k)!r}, "
                    f"expected {exp!r} ({re_ev.raw})"
                )

    applied_events = [e for e in events if e.event_type == "POINTS_APPLIED"]
    if not applied_events:
        errors.append("Missing POINTS_APPLIED after RUN_RESET")
    else:
        pa = applied_events[0]
        if pa.fields.get("points") != "500" or pa.fields.get("carried") != "none":
            errors.append(
                f"Expected fresh 500 points (carried=none) after RUN_RESET, got {pa.raw}"
            )

    return events, errors


def _has_event(events: list[GauntletEvent], event_type: str) -> bool:
    return any(e.event_type == event_type for e in events)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="Skip building mod.ff before launching.")
    parser.add_argument("--timeout", type=float, default=120.0, help="Per-scenario timeout in seconds.")
    parser.add_argument("--banner-delay", type=float, default=1.0, help="gauntlet_test_banner_delay override.")
    parser.add_argument("--prep-duration", type=int, default=2, help="gauntlet_test_prep_duration override.")
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

    print("\n=== Starting headless Xvfb display for Co-op verification ===")
    display_num, xvfb, xfwm, xdg_tmp = smoke_verify.start_virtual_display()
    results: list[ScenarioResult] = []
    try:
        # Scenario 1: Co-op Stage Clear on Nacht -> SetUINextLevel + exitLevel(false), NO ChangeLevel()
        print("\n--> Scenario 1: Co-op Stage Clear on Nacht -> Verruckt lobby handoff (no ChangeLevel)")
        coop_transition_seen_at: list[float] = []

        def _stop_after_coop_exit(evs: list[GauntletEvent]) -> bool:
            if any(e.event_type == "STAGE_TRANSITION" for e in evs):
                if not coop_transition_seen_at:
                    coop_transition_seen_at.append(time.monotonic())
                # Settle briefly after exitLevel(false) to verify ChangeLevel never fires
                return (time.monotonic() - coop_transition_seen_at[0]) >= 2.5
            return False

        res1 = verify_cycle2.run_waw_scenario(
            name="S1: Co-op Stage Clear -> lobby handoff",
            log_filename="coop_s1_stage_clear_lobby_handoff.console.log",
            start_map="nazi_zombie_prototype",
            extra_dvars=[
                ("gauntlet_active", "0"),
                ("gauntlet_pending_transition", "0"),
                ("gauntlet_next_map", ""),
                ("gauntlet_next_display", ""),
                ("gauntlet_lobby_status", ""),
                ("gauntlet_test_force_coop", "1"),
                ("gauntlet_test_target_round", "1"),
                ("gauntlet_test_banner_delay", str(args.banner_delay)),
                ("gauntlet_test_autoclear", "1"),
            ],
            stop_predicate=_stop_after_coop_exit,
            analyzer=analyze_coop_stage_clear_log,
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=args.timeout,
        )
        results.append(res1)

        # Extract the real local player key observed by CoDWaW.exe in Scenario 1
        observed_key = "n_player"
        for ev in res1.events:
            if ev.event_type in ("POINTS_SAVED", "PLAYER_ROSTER_RESOLVED", "POINTS_APPLIED"):
                if ev.fields.get("player"):
                    observed_key = ev.fields["player"]
                    break
        print(f"    Observed CoDWaW player key: {observed_key}")

        # Scenario 2: Co-op next-Stage launch on Verruckt (Cycle 2 Stage 2, R10, Floor=5000)
        roster_cases = [
            (
                "S2a: Roster recovery - returning surplus (12400)",
                "coop_s2a_returning_surplus.console.log",
                f"{observed_key}=12400;g_90002=1500;g_90003=0",
                "",
                "",
                "returning",
                12400,
                "12400",
            ),
            (
                "S2b: Roster recovery - spectator (0 -> 5000 floor)",
                "coop_s2b_spectator_floor.console.log",
                f"{observed_key}=0;g_90001=12400",
                observed_key,
                "",
                "spectator",
                5000,
                "0",
            ),
            (
                "S2c: Roster recovery - late joiner (unrecorded -> 5000 floor)",
                "coop_s2c_late_joiner_floor.console.log",
                "g_90001=12400;g_90002=8100",
                "",
                "",
                "late_joiner",
                5000,
                "none",
            ),
            (
                "S2d: Roster recovery - reconnector (8750 recovered)",
                "coop_s2d_reconnector_recovery.console.log",
                f"{observed_key}=8750;g_90001=12400",
                "",
                observed_key,
                "reconnecting",
                8750,
                "8750",
            ),
        ]

        for label, logfile, ledger, spectators, disconnected, exp_role, exp_pts, exp_carried in roster_cases:
            print(f"\n--> {label}")
            res = verify_cycle2.run_waw_scenario(
                name=label,
                log_filename=logfile,
                start_map="nazi_zombie_asylum",
                extra_dvars=[
                    ("gauntlet_active", "1"),
                    ("gauntlet_run_id", "coop_roster_run"),
                    ("gauntlet_cycle", "2"),
                    ("gauntlet_stage", "2"),
                    ("gauntlet_total_rounds", "45"),
                    ("gauntlet_pending_transition", "1"),
                    ("gauntlet_next_map", "nazi_zombie_asylum"),
                    ("gauntlet_next_display", "Verruckt"),
                    ("gauntlet_lobby_status", "NEXT STAGE: C2 S2/4 - Verruckt (R10-R15)"),
                    ("gauntlet_player_points", ledger),
                    ("gauntlet_spectators", spectators),
                    ("gauntlet_disconnected_players", disconnected),
                    ("gauntlet_test_force_coop", "1"),
                    ("gauntlet_test_prep_duration", str(args.prep_duration)),
                    ("gauntlet_test_autoclear", "0"),
                ],
                stop_predicate=lambda evs: _has_event(evs, "POINTS_APPLIED"),
                analyzer=lambda txt, r=exp_role, p=exp_pts, c=exp_carried: analyze_roster_recovery_log(
                    txt,
                    expected_role=r,
                    expected_points=p,
                    expected_carried=c,
                    expected_floor=5000,
                ),
                display_num=display_num,
                xdg_config_home=xdg_tmp.name,
                proton=args.proton,
                steam_root=args.steam_root,
                steam_game=args.steam_game,
                playtest_prefix=args.playtest_prefix,
                timeout_s=args.timeout,
            )
            results.append(res)

        # Scenario 3a: Stale-lobby reset (active=1, cycle=2, stage=3, pending_transition=0)
        print("\n--> Scenario 3a: Stale-lobby reset (pending_transition=0 -> RUN_RESET -> C1 S1 R1 500 pts)")
        res3a = verify_cycle2.run_waw_scenario(
            name="S3a: Stale-lobby reset (pending_transition=0)",
            log_filename="coop_s3a_stale_lobby_reset.console.log",
            start_map="nazi_zombie_prototype",
            extra_dvars=[
                ("gauntlet_active", "1"),
                ("gauntlet_run_id", "stale_coop_run"),
                ("gauntlet_cycle", "2"),
                ("gauntlet_stage", "3"),
                ("gauntlet_total_rounds", "50"),
                ("gauntlet_pending_transition", "0"),
                ("gauntlet_next_map", "nazi_zombie_sumpf"),
                ("gauntlet_lobby_status", "NEXT STAGE: C2 S3/4 - Shi No Numa (R10-R15)"),
                ("gauntlet_player_points", f"{observed_key}=25000"),
                ("gauntlet_test_force_coop", "1"),
                ("gauntlet_test_autoclear", "0"),
            ],
            stop_predicate=lambda evs: _has_event(evs, "POINTS_APPLIED"),
            analyzer=lambda txt: analyze_stale_reset_log(
                txt,
                expected_reason="stale_no_pending_transition",
                stale_run_id="stale_coop_run",
            ),
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=args.timeout,
        )
        results.append(res3a)

        # Scenario 3b: Explicit gauntlet_fresh_run=1 reset
        print("\n--> Scenario 3b: Explicit fresh-Run reset (gauntlet_fresh_run=1 -> RUN_RESET -> C1 S1 R1 500 pts)")
        res3b = verify_cycle2.run_waw_scenario(
            name="S3b: Explicit fresh-Run reset (gauntlet_fresh_run=1)",
            log_filename="coop_s3b_fresh_run_reset.console.log",
            start_map="nazi_zombie_prototype",
            extra_dvars=[
                ("gauntlet_active", "1"),
                ("gauntlet_run_id", "stale_fresh_run"),
                ("gauntlet_cycle", "2"),
                ("gauntlet_stage", "1"),
                ("gauntlet_total_rounds", "40"),
                ("gauntlet_pending_transition", "1"),
                ("gauntlet_fresh_run", "1"),
                ("gauntlet_player_points", f"{observed_key}=18000"),
                ("gauntlet_test_force_coop", "1"),
                ("gauntlet_test_autoclear", "0"),
            ],
            stop_predicate=lambda evs: _has_event(evs, "POINTS_APPLIED"),
            analyzer=lambda txt: analyze_stale_reset_log(
                txt,
                expected_reason="fresh_run_requested",
                stale_run_id="stale_fresh_run",
            ),
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=args.timeout,
        )
        results.append(res3b)
    finally:
        smoke_verify.stop_virtual_display(xvfb, xfwm, xdg_tmp)

    print("\n=== Co-op In-Engine Verification Summary ===")
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
