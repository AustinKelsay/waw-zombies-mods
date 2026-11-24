#!/usr/bin/env python3
"""Automated in-engine verification for Base Zombies Phase 2 on Der Riese (Issue #27 / P2-T5).

Verifies real Steam/Proton CoD:WaW 1.7 execution across two live runs:
  1. Run A (Der Riese Base Zombies Phase 2):
     +set fs_game mods/waw_gauntlet +set bz_enabled 1 +set bz_perks_enabled 1
     +set bz_classes_enabled 1 +set bz_pap_enabled 1 +set bz_elements_enabled 1
     +set gauntlet_enabled 0 +set bz_test_p2_selftest 1 +devmap nazi_zombie_factory
     Asserts mod.ff loaded, zero fatal script/asset/400-FX errors, BZ_INIT with
     elements=1, ELEMENTS_BOX_REGISTER for all 4 zero-FX cloned primaries
     (bz_acid_sprayer, bz_cryo_cannon, bz_multi_crossbow, bz_blade_boomerang),
     Phase 2 combat/gear telemetry (ELEM_TESLA_SELF_GUARD, ELEM_TESLA_STUN,
     ELEM_FLAME_DOT, ELEM_ACID_PUDDLE, ELEM_CRYO_FREEZE, ELEM_CRYO_SHATTER,
     SPECIAL_WAR_CLUB_SMASH, SPECIAL_CROSSBOW_FIRE, SPECIAL_CROSSBOW_DETONATE,
     SPECIAL_BOOMERANG_THROW, SPECIAL_PORTAL_OPEN, SPECIAL_PORTAL_TELEPORT),
     Arsenal ammo and Max Ammo portal refill telemetry, and BZ_P2_SELFTEST_PASS.
  2. Run B (Classic Mode Untouched):
     +set fs_game mods/waw_gauntlet +set bz_enabled 0 +set bz_elements_enabled 0
     +set gauntlet_enabled 0 +devmap nazi_zombie_factory
     Asserts clean Der Riese boot with MOD_LOADED, zero BZ_EVENT emissions, and
     zero fatal script/asset/400-FX errors.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_mod  # noqa: E402
import smoke_verify  # noqa: E402
import verify_base_zombies_p1 as vb1  # noqa: E402

REPO_ROOT = build_mod.REPO_ROOT
DEFAULT_LOG_DIR = REPO_ROOT / ".smoke_logs"

REQUIRED_BOX_WEAPONS: tuple[str, ...] = (
    "bz_acid_sprayer",
    "bz_cryo_cannon",
    "bz_multi_crossbow",
    "bz_blade_boomerang",
)

REQUIRED_P2_EVENT_TYPES: tuple[str, ...] = (
    "ELEMENTS_BOX_REGISTER",
    "ELEM_TESLA_SELF_GUARD",
    "ELEM_TESLA_STUN",
    "ELEM_FLAME_DOT",
    "ELEM_ACID_PUDDLE",
    "ELEM_CRYO_FREEZE",
    "ELEM_CRYO_SHATTER",
    "SPECIAL_WAR_CLUB_SMASH",
    "SPECIAL_CROSSBOW_FIRE",
    "SPECIAL_CROSSBOW_DETONATE",
    "SPECIAL_BOOMERANG_THROW",
    "SPECIAL_PORTAL_OPEN",
    "SPECIAL_PORTAL_TELEPORT",
)


def analyze_bz_p2_log(
    log_text: str,
    map_name: str = "nazi_zombie_factory",
) -> tuple[list[vb1.BzEvent], list[str]]:
    """Validate Run A: Der Riese Base Zombies Phase 2 live self-test console.log."""
    events = vb1.parse_bz_events(log_text)
    errors: list[str] = []
    vb1._check_fatal_patterns(log_text, errors)

    if not re.search(r"Loading fastfile '?mod'?", log_text, re.IGNORECASE):
        errors.append("mod.ff was not reported as loaded in console.log")

    init_events = [
        e for e in events if e.event_type == "BZ_INIT" and e.fields.get("map") == map_name
    ]
    if not init_events:
        errors.append(f"Missing BZ_INIT event for map={map_name!r}")
    else:
        ev = init_events[0]
        for gate in ("perks", "classes", "pap", "elements"):
            if ev.fields.get(gate) != "1":
                errors.append(
                    f"BZ_INIT gate {gate}={ev.fields.get(gate)!r}, expected '1' ({ev.raw})"
                )

    box_events = [e for e in events if e.event_type == "ELEMENTS_BOX_REGISTER"]
    if not box_events:
        errors.append("Missing ELEMENTS_BOX_REGISTER telemetry for Phase 2 cloned primaries")
    else:
        bev = box_events[0]
        if bev.fields.get("count") != "4":
            errors.append(
                f"ELEMENTS_BOX_REGISTER count={bev.fields.get('count')!r}, expected '4' ({bev.raw})"
            )
        registered = {
            w.strip() for w in bev.fields.get("weapons", "").split(",") if w.strip()
        }
        for weap in REQUIRED_BOX_WEAPONS:
            if weap not in registered:
                errors.append(
                    f"ELEMENTS_BOX_REGISTER missing weapon {weap!r} ({bev.raw})"
                )

    event_types = {e.event_type for e in events}
    for req_type in REQUIRED_P2_EVENT_TYPES:
        if req_type not in event_types:
            errors.append(f"Missing required Phase 2 telemetry event: BZ_EVENT|{req_type}|...")

    refill_evidence = (
        ("STATION_PURCHASE",
         {"menu": "bz_station_arsenal", "category": "element_ammo", "item": "acid_sprayer",
          "status": "ok", "cost": "2500"},
         "Missing successful 2500-point Acid Sprayer ammo purchase from the Arsenal"),
        ("SPECIAL_PORTAL_REFILL", {"reason": "max_ammo", "charges": "2"},
         "Missing SPECIAL_PORTAL_REFILL restoring both charges via Max Ammo"),
    )
    for event_type, fields, message in refill_evidence:
        if not any(
            e.event_type == event_type and all(e.fields.get(key) == value for key, value in fields.items())
            for e in events
        ):
            errors.append(message)

    # Confirm real patched tesla_pvp_thread preserved 440 maxhealth on Titan + Jugg II
    tesla_pvp_events = [
        e
        for e in events
        if e.event_type == "ELEM_TESLA_SELF_GUARD"
        and e.fields.get("source") == "pvp_thread"
    ]
    if not tesla_pvp_events:
        errors.append(
            "Missing ELEM_TESLA_SELF_GUARD telemetry from patched tesla_pvp_thread()"
        )
    elif not any(e.fields.get("maxhealth") == "440" for e in tesla_pvp_events):
        errors.append(
            f"ELEM_TESLA_SELF_GUARD did not report maxhealth=440 ({tesla_pvp_events[0].raw})"
        )

    fail_events = [e for e in events if e.event_type == "BZ_P2_SELFTEST_FAIL"]
    for fev in fail_events:
        errors.append(f"Phase 2 self-test reported failure: {fev.raw}")

    pass_events = [e for e in events if e.event_type == "BZ_P2_SELFTEST_PASS"]
    if not pass_events:
        errors.append("Missing BZ_EVENT|BZ_P2_SELFTEST_PASS|... telemetry")
    else:
        pev = pass_events[-1]
        expected_fields = (
            ("map", map_name),
            ("box_weapons", "4"),
            ("primaries", "4"),
            ("titan_tesla_hp", "440"),
            ("acid_brittle_dmg", "150"),
            ("cryo_shatter_dmg", "250"),
            ("xbow_bolts", "3"),
            ("portal_warped", "1"),
            ("cleanup", "1"),
        )
        for key, exp in expected_fields:
            actual = pev.fields.get(key)
            if actual != exp:
                errors.append(
                    f"BZ_P2_SELFTEST_PASS {key}={actual!r}, expected {exp!r} ({pev.raw})"
                )
        checks_raw = pev.fields.get("checks", "0")
        if not checks_raw.isdigit() or int(checks_raw) < 20:
            errors.append(
                f"BZ_P2_SELFTEST_PASS checks={checks_raw!r}, expected >= 20 ({pev.raw})"
            )

    return events, errors


def analyze_classic_bz_p2_isolation_log(
    log_text: str,
    map_name: str = "nazi_zombie_factory",
) -> tuple[list[vb1.BzEvent], list[str]]:
    """Validate Run B: Classic Mode (bz_enabled=0, bz_elements_enabled=0, gauntlet_enabled=0)."""
    return vb1.analyze_classic_bz_isolation_log(log_text, map_name=map_name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--tools-root", type=Path, default=build_mod.DEFAULT_TOOLS_ROOT)
    parser.add_argument("--steam-root", type=Path, default=build_mod.DEFAULT_STEAM_ROOT)
    parser.add_argument("--dev-root", type=Path, default=build_mod.DEFAULT_DEV_ROOT)
    parser.add_argument("--steam-game", type=Path, default=build_mod.DEFAULT_STEAM_GAME)
    parser.add_argument("--steam-appdata", type=Path, default=build_mod.DEFAULT_STEAM_APPDATA)
    parser.add_argument(
        "--playtest-prefix", type=Path, default=smoke_verify.DEFAULT_PLAYTEST_PREFIX
    )
    parser.add_argument("--proton", type=Path, default=smoke_verify.DEFAULT_PROTON)
    args = parser.parse_args(argv)

    playtest_appdata = (
        args.playtest_prefix
        / "pfx/drive_c/users/steamuser/AppData/Local/Activision/CoDWaW"
    )
    if not playtest_appdata.is_dir():
        print(
            f"ERROR: Playtest AppData folder missing: {playtest_appdata}",
            file=sys.stderr,
        )
        return 1
    if not args.proton.is_file():
        print(f"ERROR: Proton launcher not found: {args.proton}", file=sys.stderr)
        return 1
    if shutil.which("Xvfb") is None or shutil.which("xfwm4") is None:
        print(
            "ERROR: Xvfb and xfwm4 must be installed for in-engine verification.",
            file=sys.stderr,
        )
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

    print("\n=== Starting headless Xvfb display for Base Zombies Phase 2 verification ===")
    display_num, xvfb, xfwm, xdg_tmp = smoke_verify.start_virtual_display()
    all_errors: list[str] = []
    try:
        # Run A: Der Riese Base Zombies Phase 2 full live self-test
        print(
            "\n--> Run A: Der Riese Base Zombies Phase 2 "
            "(bz_enabled=1, perks+classes+pap+elements, p2_selftest=1)"
        )
        res_a = vb1.run_bz_scenario(
            name="Der Riese Base Zombies Phase 2",
            log_filename="bz_p2_factory_selftest.console.log",
            map_name="nazi_zombie_factory",
            dvars=[
                ("gauntlet_enabled", "0"),
                ("bz_enabled", "1"),
                ("bz_perks_enabled", "1"),
                ("bz_classes_enabled", "1"),
                ("bz_pap_enabled", "1"),
                ("bz_elements_enabled", "1"),
                ("bz_companions_enabled", "0"),
                ("bz_test_selftest", "0"),
                ("bz_test_p2_selftest", "1"),
            ],
            stop_predicate=lambda text: (
                "BZ_EVENT|BZ_P2_SELFTEST_PASS|" in text
                or "BZ_EVENT|BZ_P2_SELFTEST_FAIL|" in text
            ),
            analyzer=lambda text: analyze_bz_p2_log(text, map_name="nazi_zombie_factory"),
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
            pass_ev = next(
                (e for e in res_a.events if e.event_type == "BZ_P2_SELFTEST_PASS"),
                None,
            )
            print(
                f"  [PASS] Run A ({res_a.duration_s:.1f}s{fx_note}) — {res_a.saved_log}"
            )
            if pass_ev:
                print(f"         {pass_ev.raw}")
        else:
            print(
                f"  [FAIL] Run A ({res_a.duration_s:.1f}s{fx_note}) — {res_a.saved_log}"
            )
            for err in res_a.errors:
                print(f"         ERROR: {err}", file=sys.stderr)
            all_errors.extend(res_a.errors)

        # Run B: Classic Mode untouched on Der Riese
        print(
            "\n--> Run B: Der Riese Classic Mode Untouched "
            "(bz_enabled=0, bz_elements_enabled=0, gauntlet_enabled=0)"
        )
        res_b = vb1.run_bz_scenario(
            name="Der Riese Classic Mode Phase 2 isolation",
            log_filename="bz_p2_factory_classic.console.log",
            map_name="nazi_zombie_factory",
            dvars=[
                ("gauntlet_enabled", "0"),
                ("bz_enabled", "0"),
                ("bz_perks_enabled", "0"),
                ("bz_classes_enabled", "0"),
                ("bz_pap_enabled", "0"),
                ("bz_elements_enabled", "0"),
                ("bz_test_selftest", "0"),
                ("bz_test_p2_selftest", "0"),
            ],
            stop_predicate=lambda text: (
                "GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_factory;gauntlet_enabled=0"
                in text
            ),
            analyzer=lambda text: analyze_classic_bz_p2_isolation_log(
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
                f"  [PASS] Run B (Classic Mode untouched, 0 BZ_EVENTs) "
                f"({res_b.duration_s:.1f}s) — {res_b.saved_log}"
            )
        else:
            print(
                f"  [FAIL] Run B (Classic Mode untouched) ({res_b.duration_s:.1f}s) "
                f"— {res_b.saved_log}"
            )
            for err in res_b.errors:
                print(f"         ERROR: {err}", file=sys.stderr)
            all_errors.extend(res_b.errors)
    finally:
        smoke_verify.stop_virtual_display(xvfb, xfwm, xdg_tmp)

    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
