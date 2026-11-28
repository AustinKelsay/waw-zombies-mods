#!/usr/bin/env python3
"""Automated in-engine verification for Base Zombies Phase 3 Squad Companions (Issue #113 / P3C-T1).

Verifies real Steam/Proton CoD:WaW 1.7 execution across three live runs:
  1. Run A (Der Riese, Ultimis Heroes): Enhanced Mode with every Base Zombies gate on,
     bz_companions_enabled=1 and bz_test_p3_selftest=1. The self-test hires through the
     Arsenal & Squad Station menu response, checks the per-map stock character model,
     the 4-member squad cap, teleport catch-up, owner-attributed MagicBullet points,
     and release cleanup, then emits BZ_P3_SELFTEST_PASS.
  2. Run B (Nacht der Untoten, US Marine player bodies): the same self-test on the map
     that does not precache the Ultimis Heroes.
  3. Run C (Classic Mode untouched on Der Riese): zero BZ_EVENT emissions and zero fatal
     script/asset/400-FX errors.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_mod  # noqa: E402
import smoke_verify  # noqa: E402
import verify_base_zombies_p1 as vb1  # noqa: E402

EXPECTED_FIRST_COMPANION_MODEL: dict[str, str] = {
    "nazi_zombie_factory": "char_rus_guard_chernova_zomb",
    "nazi_zombie_sumpf": "char_rus_guard_chernova_zomb",
    "nazi_zombie_prototype": "char_usa_marine_player_body2_1",
    "nazi_zombie_asylum": "char_usa_marine_player_body2_1",
}

REQUIRED_P3_EVENT_TYPES: tuple[str, ...] = (
    "COMPANION_INIT",
    "COMPANION_SPAWN",
    "COMPANION_WARP",
    "COMPANION_FIRE",
    "COMPANION_REMOVE",
)


def analyze_bz_p3_log(
    log_text: str,
    map_name: str = "nazi_zombie_factory",
) -> tuple[list[vb1.BzEvent], list[str]]:
    """Validate a Phase 3 Companion live self-test console.log."""
    events = vb1.parse_bz_events(log_text)
    errors: list[str] = []
    vb1._check_fatal_patterns(log_text, errors)

    if not re.search(r"Loading fastfile '?mod'?", log_text, re.IGNORECASE):
        errors.append("mod.ff was not reported as loaded in console.log")

    init_events = [e for e in events if e.event_type == "BZ_INIT" and e.fields.get("map") == map_name]
    if not init_events:
        errors.append(f"Missing BZ_INIT event for map={map_name!r}")
    elif init_events[0].fields.get("companions") != "1":
        errors.append(f"BZ_INIT companions={init_events[0].fields.get('companions')!r}, expected '1' ({init_events[0].raw})")

    event_types = {e.event_type for e in events}
    for req_type in REQUIRED_P3_EVENT_TYPES:
        if req_type not in event_types:
            errors.append(f"Missing required Phase 3 telemetry event: BZ_EVENT|{req_type}|...")

    if not any(
        e.event_type == "STATION_PURCHASE"
        and e.fields.get("menu") == "bz_station_arsenal"
        and e.fields.get("category") == "companion"
        and e.fields.get("status") == "ok"
        and e.fields.get("cost") == "2000"
        for e in events
    ):
        errors.append("Missing successful 2000-point Companion hire from the Arsenal & Squad Station")

    expected_model = EXPECTED_FIRST_COMPANION_MODEL.get(map_name, "")
    spawns = [e for e in events if e.event_type == "COMPANION_SPAWN"]
    if spawns and expected_model and spawns[0].fields.get("model") != expected_model:
        errors.append(f"First COMPANION_SPAWN model={spawns[0].fields.get('model')!r}, expected {expected_model!r} ({spawns[0].raw})")

    for fev in (e for e in events if e.event_type == "BZ_P3_SELFTEST_FAIL"):
        errors.append(f"Phase 3 self-test reported failure: {fev.raw}")

    pass_events = [e for e in events if e.event_type == "BZ_P3_SELFTEST_PASS"]
    if not pass_events:
        errors.append("Missing BZ_EVENT|BZ_P3_SELFTEST_PASS|... telemetry")
    else:
        pev = pass_events[-1]
        for key, exp in (("map", map_name), ("model", expected_model), ("cap", "3"), ("cleanup", "1")):
            if pev.fields.get(key) != exp:
                errors.append(f"BZ_P3_SELFTEST_PASS {key}={pev.fields.get(key)!r}, expected {exp!r} ({pev.raw})")
        checks_raw = pev.fields.get("checks", "0")
        if not checks_raw.isdigit() or int(checks_raw) < 8:
            errors.append(f"BZ_P3_SELFTEST_PASS checks={checks_raw!r}, expected >= 8 ({pev.raw})")
        points_raw = pev.fields.get("points", "0")
        if not points_raw.lstrip("-").isdigit() or int(points_raw) <= 0:
            errors.append(f"BZ_P3_SELFTEST_PASS points={points_raw!r}, expected owner-credited points > 0 ({pev.raw})")

    return events, errors


class CompanionVisualCapture:
    """Screenshots the Xvfb display once per COMPANION_VISUAL phase (requires ImageMagick import)."""

    def __init__(self, out_dir: Path, display_num: int, prefix: str) -> None:
        self.out_dir = out_dir
        self.prefix = prefix
        self.env = dict(os.environ, DISPLAY=f":{display_num}")
        self.seen: set[str] = set()
        self.paths: list[Path] = []

    def __call__(self, log_text: str) -> None:
        for event in vb1.parse_bz_events(log_text):
            phase = event.fields.get("phase", "")
            if event.event_type != "COMPANION_VISUAL" or not phase or phase in self.seen:
                continue
            self.seen.add(phase)
            path = self.out_dir / f"{self.prefix}_{phase}.png"
            try:
                subprocess.run(["import", "-window", "root", str(path)], env=self.env, check=True, capture_output=True, timeout=5)
            except (OSError, subprocess.SubprocessError) as exc:
                print(f"    WARN: capture {path.name} failed: {exc}", file=sys.stderr)
                continue
            self.paths.append(path)
            print(f"    Captured {path}", flush=True)


def _selftest_dvars() -> list[tuple[str, str]]:
    return [
        ("gauntlet_enabled", "0"),
        ("bz_enabled", "1"),
        ("bz_perks_enabled", "1"),
        ("bz_classes_enabled", "1"),
        ("bz_pap_enabled", "1"),
        ("bz_elements_enabled", "1"),
        ("bz_companions_enabled", "1"),
        ("bz_test_selftest", "0"),
        ("bz_test_p2_selftest", "0"),
        ("bz_test_p3_selftest", "1"),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--timeout", type=float, default=150.0)
    parser.add_argument("--tools-root", type=Path, default=build_mod.DEFAULT_TOOLS_ROOT)
    parser.add_argument("--steam-root", type=Path, default=build_mod.DEFAULT_STEAM_ROOT)
    parser.add_argument("--dev-root", type=Path, default=build_mod.DEFAULT_DEV_ROOT)
    parser.add_argument("--steam-game", type=Path, default=build_mod.DEFAULT_STEAM_GAME)
    parser.add_argument("--steam-appdata", type=Path, default=build_mod.DEFAULT_STEAM_APPDATA)
    parser.add_argument("--playtest-prefix", type=Path, default=smoke_verify.DEFAULT_PLAYTEST_PREFIX)
    parser.add_argument("--proton", type=Path, default=smoke_verify.DEFAULT_PROTON)
    parser.add_argument("--capture-dir", type=Path, default=None, help="Save COMPANION_VISUAL screenshots here")
    args = parser.parse_args(argv)
    if args.capture_dir is not None:
        args.capture_dir.mkdir(parents=True, exist_ok=True)

    playtest_appdata = args.playtest_prefix / "pfx/drive_c/users/steamuser/AppData/Local/Activision/CoDWaW"
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
                print(f"ERROR: --skip-build specified but {artifact} does not exist", file=sys.stderr)
                return 1
        for target in deploy_targets:
            for dest in build_mod.deploy_mod(build_mod.DIST_DIR, target):
                print(f"Deployed {dest}")

    common = {
        "xdg_config_home": None,
        "proton": args.proton,
        "steam_root": args.steam_root,
        "steam_game": args.steam_game,
        "playtest_prefix": args.playtest_prefix,
    }

    print("\n=== Starting headless Xvfb display for Base Zombies Phase 3 verification ===")
    display_num, xvfb, xfwm, xdg_tmp = smoke_verify.start_virtual_display()
    common["xdg_config_home"] = xdg_tmp.name
    all_errors: list[str] = []
    try:
        selftest_runs = (
            ("A", "Der Riese", "nazi_zombie_factory", "bz_p3_factory_selftest.console.log"),
            ("B", "Nacht der Untoten", "nazi_zombie_prototype", "bz_p3_prototype_selftest.console.log"),
        )
        for run_id, display, map_name, log_name in selftest_runs:
            print(f"\n--> Run {run_id}: {display} Squad Companions self-test (bz_companions_enabled=1, p3_selftest=1)")
            capture = None
            if args.capture_dir is not None:
                capture = CompanionVisualCapture(args.capture_dir, display_num, map_name)
            res = vb1.run_bz_scenario(
                name=f"{display} Base Zombies Phase 3",
                log_filename=log_name,
                map_name=map_name,
                dvars=_selftest_dvars(),
                stop_predicate=lambda text: (
                    "BZ_EVENT|BZ_P3_SELFTEST_PASS|" in text or "BZ_EVENT|BZ_P3_SELFTEST_FAIL|" in text
                ),
                analyzer=lambda text, m=map_name: analyze_bz_p3_log(text, map_name=m),
                display_num=display_num,
                timeout_s=args.timeout,
                settle_s=1.5,
                observe_log=capture,
                **common,
            )
            fx_note = f" | fx={res.fx_count}/400" if res.fx_count is not None else ""
            if res.passed:
                pass_ev = next((e for e in res.events if e.event_type == "BZ_P3_SELFTEST_PASS"), None)
                print(f"  [PASS] Run {run_id} ({res.duration_s:.1f}s{fx_note}) — {res.saved_log}")
                if pass_ev:
                    print(f"         {pass_ev.raw}")
            else:
                print(f"  [FAIL] Run {run_id} ({res.duration_s:.1f}s{fx_note}) — {res.saved_log}")
                for err in res.errors:
                    print(f"         ERROR: {err}", file=sys.stderr)
                all_errors.extend(res.errors)

        print("\n--> Run C: Der Riese Classic Mode Untouched (bz_enabled=0, bz_companions_enabled=0, gauntlet_enabled=0)")
        res_c = vb1.run_bz_scenario(
            name="Der Riese Classic Mode Phase 3 isolation",
            log_filename="bz_p3_factory_classic.console.log",
            map_name="nazi_zombie_factory",
            dvars=[
                ("gauntlet_enabled", "0"),
                ("bz_enabled", "0"),
                ("bz_perks_enabled", "0"),
                ("bz_classes_enabled", "0"),
                ("bz_pap_enabled", "0"),
                ("bz_elements_enabled", "0"),
                ("bz_companions_enabled", "0"),
                ("bz_test_p3_selftest", "0"),
            ],
            stop_predicate=lambda text: "GAUNTLET_EVENT|MOD_LOADED|map=nazi_zombie_factory;gauntlet_enabled=0" in text,
            analyzer=lambda text: vb1.analyze_classic_bz_isolation_log(text, map_name="nazi_zombie_factory"),
            display_num=display_num,
            timeout_s=min(args.timeout, 90.0),
            settle_s=2.5,
            **common,
        )
        if res_c.passed:
            print(f"  [PASS] Run C (Classic Mode untouched, 0 BZ_EVENTs) ({res_c.duration_s:.1f}s) — {res_c.saved_log}")
        else:
            print(f"  [FAIL] Run C (Classic Mode untouched) ({res_c.duration_s:.1f}s) — {res_c.saved_log}")
            for err in res_c.errors:
                print(f"         ERROR: {err}", file=sys.stderr)
            all_errors.extend(res_c.errors)
    finally:
        smoke_verify.stop_virtual_display(xvfb, xfwm, xdg_tmp)

    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
