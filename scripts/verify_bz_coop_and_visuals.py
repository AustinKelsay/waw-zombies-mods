#!/usr/bin/env python3
"""Verify host-side Co-op native PaP & Hellhounds, enhanced Gauntlet, and 4-map visuals.

Note on WaW 1.7 CoDWaW.exe Co-op: the stock Steam Co-op binary has no CLI `connect`
command and rejects join-in-progress (`Client connect ignored because join in progress
isn't allowed in COOP`), so live Co-op verification runs host-side on Der Riese (matching
`scripts/verify_coop.py`) while multi-player prompt/state isolation is verified offline.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event, Thread

import build_mod
import smoke_verify
import verify_base_zombies_p1 as bz
from verify_cycle1 import GauntletEvent, parse_gauntlet_events


def engine_errors(log_text: str) -> list[str]:
    errors: list[str] = []
    bz._check_fatal_patterns(log_text, errors)
    if not re.search(r"Loading fastfile ['\"]?mod(?:\.ff)?(?=['\"\s]|$)", log_text, re.IGNORECASE):
        errors.append("mod.ff was not reported as loaded in console.log")
    return errors


def analyze_bz_coop_selftest_log(log_text: str) -> tuple[list[bz.BzEvent], list[str]]:
    """Check the host's parity consistency, live native purchase, and self-test verdict."""
    events = bz.parse_bz_events(log_text)
    errors = engine_errors(log_text)
    parity_ids = {
        event.fields.get("build_id", "")
        for event in events
        if event.event_type == "BUILD_PARITY" and event.fields.get("build_id")
    }
    if not parity_ids:
        errors.append("Missing BUILD_PARITY with a build ID")
    elif len(parity_ids) > 1:
        errors.append(f"Conflicting BUILD_PARITY build IDs: {sorted(parity_ids)}")
    if not any(
        event.event_type == "PAP_DOUBLE_UPGRADE" and event.fields.get("console") == "native"
        for event in events
    ):
        errors.append("Missing PAP_DOUBLE_UPGRADE with console=native")
    pass_events = [event for event in events if event.event_type == "BZ_COOP_SELFTEST_PASS"]
    if not pass_events:
        errors.append("Missing BZ_COOP_SELFTEST_PASS")
    elif parity_ids:
        expected_id = next(iter(parity_ids))
        for pass_ev in pass_events:
            pass_id = pass_ev.fields.get("build_id", "")
            if pass_id != expected_id:
                errors.append(
                    f"Conflicting build_id between BUILD_PARITY ({expected_id}) "
                    f"and BZ_COOP_SELFTEST_PASS ({pass_id})"
                )
    for event in events:
        if event.event_type == "BZ_COOP_SELFTEST_FAIL":
            errors.append(event.raw)
    return events, errors


def _has_seeded_perm_and_perks(perm: str, perks: str) -> bool:
    perm_parts = perm.split("|")
    if len(perm_parts) < 3:
        return False
    cls, flags_csv, melee_slot = perm_parts[0], perm_parts[1], perm_parts[2]
    flags = {tok for tok in flags_csv.split(",") if tok and tok != "-"}
    perks_parts = perks.split("|")
    t1 = {tok for tok in perks_parts[0].split(",") if tok and tok != "-"} if perks_parts else set()
    return cls == "titan" and {"wc", "pwc"} <= flags and melee_slot == "war_club" and {"su", "mk"} <= t1


def analyze_enhanced_gauntlet_log(log_text: str) -> tuple[list[bz.BzEvent], list[str]]:
    """Check the first enhanced Stage handoff (class, perks, war_club, pap_war_club)."""
    events = bz.parse_bz_events(log_text)
    gauntlet = parse_gauntlet_events(log_text)
    errors = engine_errors(log_text)
    source = "nazi_zombie_prototype"
    destination = "nazi_zombie_asylum"

    def matches(event: bz.BzEvent | GauntletEvent, event_type: str, **fields: str) -> bool:
        return event.event_type == event_type and all(
            event.fields.get(key) == value for key, value in fields.items()
        )

    errors.extend(e.raw for e in events if e.event_type == "GAUNTLET_BZ_SEED_FAIL")
    if not any(
        matches(e, "GAUNTLET_BZ_SEEDED", map=source, **{"class": "titan", "weapons": "2"}) for e in events
    ):
        errors.append(f"Missing GAUNTLET_BZ_SEEDED on {source}")
    saved_players = {
        e.fields["player"]
        for e in events
        if matches(e, "GAUNTLET_BZ_SAVED", map=source)
        and e.fields.get("player")
        and _has_seeded_perm_and_perks(e.fields.get("perm", ""), e.fields.get("perks", ""))
    }
    if not saved_players:
        errors.append(
            f"Missing GAUNTLET_BZ_SAVED on {source} with titan, war_club+pap_war_club (wc,pwc), and perks (su,mk)"
        )
    for event_type, fields in (
        ("STAGE_CLEAR", {"map": source, "next_map": destination}),
        ("STAGE_TRANSITION", {"next_map": destination}),
        ("STAGE_INIT", {"map": destination, "stage": "2"}),
    ):
        if not any(matches(e, event_type, **fields) for e in gauntlet):
            errors.append(f"Missing {event_type} for {destination}")
    if not any(
        matches(e, "GAUNTLET_BZ_RESTORED", map=destination, **{"class": "titan", "war_club": "1", "pap_war_club": "1"})
        and e.fields.get("player") in saved_players
        and e.fields.get("t1", "").isdecimal()
        and int(e.fields["t1"]) >= 2
        for e in events
    ):
        errors.append(
            f"Missing GAUNTLET_BZ_RESTORED on {destination} with class=titan, t1>=2, war_club=1, pap_war_club=1"
        )
    return events, errors


MAP_SLUGS = ("factory", "prototype", "asylum", "sumpf")
WEAPON_SLUGS = ("acid", "cryo", "crossbow", "boomerang")


def expected_visual_phases(slug: str) -> tuple[str, ...]:
    if slug != "factory":
        return (
            f"{slug}_perks_prompt",
            f"{slug}_class_prompt",
            f"{slug}_arsenal_prompt",
            f"{slug}_pap_prompt",
        )
    return (
        "factory_perks_prompt", "factory_class_prompt", "factory_arsenal_prompt",
        *(f"{weapon}_{state}" for weapon in WEAPON_SLUGS for state in ("idle", "active", "post")),
        "native_pap_prompt", "native_pap_ii_badge",
    )


@dataclass(frozen=True)
class CapturedFrame:
    phase: str
    path: Path
    sha256: str
    game_t_ms: int


def analyze_visual_tour_result(
    log_text: str, captured_frames: Sequence[CapturedFrame],
) -> tuple[list[bz.BzEvent], list[str]]:
    """Check phase telemetry, frame files, and screenshot diversity for one Stock Map."""
    events = bz.parse_bz_events(log_text)
    errors = engine_errors(log_text)
    done = [e for e in events if e.event_type == "VISUAL_TOUR_DONE"]
    errors.extend(e.raw for e in events if e.event_type == "VISUAL_TOUR_FAIL")
    if not done:
        errors.append("Missing VISUAL_TOUR_DONE")
        return events, errors

    slug = done[-1].fields.get("map", "").removeprefix("nazi_zombie_")
    if slug not in MAP_SLUGS:
        errors.append(f"Unexpected Stock Map in {done[-1].raw}")
        return events, errors
    expected = expected_visual_phases(slug)
    if done[-1].fields.get("phases") != str(len(expected)):
        errors.append(f"Expected {len(expected)} phases in {done[-1].raw}")

    phase_times = {
        e.fields.get("phase"): e.fields.get("t") for e in events if e.event_type == "VISUAL_TOUR_PHASE"
    }
    frames = {frame.phase: frame for frame in captured_frames}
    hashes: dict[str, str] = {}
    for phase in expected:
        if phase not in phase_times:
            errors.append(f"Missing VISUAL_TOUR_PHASE for {phase}")
        if phase not in frames:
            errors.append(f"Missing captured frame for {phase}")
            continue
        frame = frames[phase]
        if phase_times.get(phase) != str(frame.game_t_ms):
            errors.append(f"Capture timestamp does not match VISUAL_TOUR_PHASE for {phase}")
        try:
            contents = frame.path.read_bytes()
        except OSError as exc:
            errors.append(f"Cannot read PNG for {phase}: {exc}")
            continue
        if not contents:
            errors.append(f"PNG is empty for {phase}: {frame.path}")
            continue
        hashes[phase] = hashlib.sha256(contents).hexdigest()
        if hashes[phase] != frame.sha256:
            errors.append(f"PNG SHA-256 does not match capture for {phase}")

    if len(hashes) > 1 and len(set(hashes.values())) == 1:
        errors.append("Visual tour appears frozen: all captured frames have identical SHA-256")
    elif slug == "factory":
        for weapon in WEAPON_SLUGS:
            group = [hashes.get(f"{weapon}_{state}") for state in ("idle", "active", "post")]
            if all(group) and len(set(group)) == 1:
                errors.append(f"Visual tour appears frozen during {weapon}: idle, active, and post match")
    return events, errors


def require_dialog_responder() -> str:
    """Return the available X11 responder backend or raise an actionable dependency error."""
    if shutil.which("xdotool") is not None:
        return "xdotool"
    if importlib.util.find_spec("Xlib") is not None:
        return "xlib"
    raise RuntimeError(
        "Missing X11 startup-dialog responder: install python-xlib or xdotool so "
        "'Set Optimal Settings?' cannot hang headless runs."
    )


def dismiss_optimal_settings(display_name: str, stop: Event) -> None:
    """Decline the optional hardware-settings dialog on the isolated X11 display."""
    if shutil.which("xdotool") is not None:
        env = dict(os.environ, DISPLAY=display_name)
        while not stop.is_set():
            try:
                res = subprocess.run(
                    ["xdotool", "search", "--onlyvisible", "--name", "^Set Optimal Settings\\?$"],
                    env=env, capture_output=True, text=True, timeout=2, check=False,
                )
                for wid in res.stdout.split():
                    subprocess.run(
                        ["xdotool", "windowfocus", "--sync", wid, "key", "Alt+n"],
                        env=env, capture_output=True, timeout=2, check=False,
                    )
            except (OSError, subprocess.SubprocessError):
                pass
            stop.wait(0.25)
        return

    try:
        from Xlib import X, XK, display, error
        from Xlib.ext import xtest
    except ImportError as exc:
        raise RuntimeError(
            "Missing X11 startup-dialog responder: install python-xlib or xdotool so "
            "'Set Optimal Settings?' cannot hang headless runs."
        ) from exc

    try:
        connection = display.Display(display_name)
    except (OSError, error.DisplayError):
        return

    try:
        if not connection.has_extension("XTEST"):
            return
        root = connection.screen().root
        net_name = connection.intern_atom("_NET_WM_NAME")
        utf8 = connection.intern_atom("UTF8_STRING")
        while not stop.is_set():
            for frame in root.query_tree().children:
                try:
                    for window in [frame, *frame.query_tree().children]:
                        if window.get_attributes().map_state != X.IsViewable:
                            continue
                        title = window.get_wm_name()
                        if not title:
                            prop = window.get_full_property(net_name, utf8)
                            if prop is not None:
                                title = prop.value.decode("utf-8", errors="replace")
                        if title != "Set Optimal Settings?":
                            continue
                        window.set_input_focus(X.RevertToParent, X.CurrentTime)
                        # Alt+N selects No and preserves the requested capture resolution.
                        alt = connection.keysym_to_keycode(XK.string_to_keysym("Alt_L"))
                        no = connection.keysym_to_keycode(XK.string_to_keysym("n"))
                        for action, key in (
                            (X.KeyPress, alt), (X.KeyPress, no), (X.KeyRelease, no), (X.KeyRelease, alt),
                        ):
                            xtest.fake_input(connection, action, key)
                        connection.sync()
                except error.BadWindow:
                    # Wine and xfwm can destroy startup windows between queries.
                    continue
            stop.wait(0.25)
    except (OSError, error.XError, error.DisplayError):
        pass
    finally:
        connection.close()


class VisualCapture:
    """Take a root-window PNG as each complete, expected phase line is appended."""

    def __init__(self, slug: str, out_dir: Path, display_num: int) -> None:
        self.expected = expected_visual_phases(slug)
        self.out_dir = out_dir
        self.env = dict(os.environ, DISPLAY=f":{display_num}")
        self.offset = 0
        self.seen: set[str] = set()
        self.frames: list[CapturedFrame] = []
        self.errors: list[str] = []

    def __call__(self, log_text: str) -> None:
        if len(log_text) < self.offset:
            self.offset = 0
        latest = log_text.rfind("\n") + 1
        if latest <= self.offset:
            return
        events = bz.parse_bz_events(log_text[self.offset:latest])
        self.offset = latest
        for event in events:
            phase = event.fields.get("phase", "")
            timestamp = event.fields.get("t", "")
            if (event.event_type != "VISUAL_TOUR_PHASE" or phase not in self.expected
                    or phase in self.seen or not timestamp.isdecimal()):
                continue
            self.seen.add(phase)
            path = self.out_dir / f"{phase}.png"
            path.unlink(missing_ok=True)
            try:
                subprocess.run(
                    ["import", "-window", "root", str(path)],
                    env=self.env, check=True, capture_output=True, timeout=3,
                )
                checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            except (OSError, subprocess.SubprocessError) as exc:
                self.errors.append(f"Failed to capture {phase} at {timestamp}ms: {exc}")
                continue
            self.frames.append(CapturedFrame(phase, path, checksum, int(timestamp)))
            print(f"    Captured {phase} at {timestamp}ms", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("coop", "enhanced-gauntlet", "visual-tour", "all"), default="all")
    parser.add_argument(
        "--out-dir", "--capture-visuals", dest="out_dir",
        type=Path, default=smoke_verify.SMOKE_LOG_DIR / "bz_coop_and_visuals",
    )
    parser.add_argument("--maps", nargs="+", choices=MAP_SLUGS, default=MAP_SLUGS,
                        help="Stock Maps for visual-tour (Co-op runs on factory; Gauntlet starts on prototype).")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--timeout", type=float, default=120.0, help="Per-scenario timeout in seconds.")
    parser.add_argument("--tools-root", type=Path, default=build_mod.DEFAULT_TOOLS_ROOT)
    parser.add_argument("--steam-root", type=Path, default=build_mod.DEFAULT_STEAM_ROOT)
    parser.add_argument("--dev-root", type=Path, default=build_mod.DEFAULT_DEV_ROOT)
    parser.add_argument("--steam-game", type=Path, default=build_mod.DEFAULT_STEAM_GAME)
    parser.add_argument("--playtest-prefix", type=Path, default=smoke_verify.DEFAULT_PLAYTEST_PREFIX)
    parser.add_argument("--proton", type=Path, default=smoke_verify.DEFAULT_PROTON)
    args = parser.parse_args(argv)

    appdata = args.playtest_prefix / "pfx/drive_c/users/steamuser/AppData/Local/Activision/CoDWaW"
    has_visual_tour = args.mode in ("all", "visual-tour")
    required_tools = ("Xvfb", "xfwm4", "import") if has_visual_tour else ("Xvfb", "xfwm4")
    missing = [tool for tool in required_tools if shutil.which(tool) is None]
    if missing:
        parser.exit(1, f"ERROR: Missing live verification tools: {', '.join(missing)}\n")
    try:
        require_dialog_responder()
    except RuntimeError as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    if not appdata.is_dir() or not args.proton.is_file():
        parser.exit(1, f"ERROR: Expected a playtest AppData folder at {appdata} and Proton at {args.proton}\n")

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.skip_build:
        for name in ("mod.ff", f"{build_mod.MOD_NAME}.iwd"):
            if not (build_mod.DIST_DIR / name).is_file():
                parser.exit(1, f"ERROR: --skip-build specified but {build_mod.DIST_DIR / name} does not exist\n")
        build_mod.deploy_mod(build_mod.DIST_DIR, appdata)
    else:
        build_mod.build_and_optionally_deploy(
            tools_root=args.tools_root, steam_root=args.steam_root, dev_root=args.dev_root,
            steam_game=args.steam_game, deploy_targets=[appdata],
        )

    results: list[bz.BzScenarioResult] = []
    frames: list[CapturedFrame] = []
    display_num, xvfb, xfwm, xdg_tmp = smoke_verify.start_virtual_display()
    stop = Event()
    responder = Thread(target=dismiss_optimal_settings, args=(f":{display_num}", stop), daemon=True)

    def run(
        mode: str,
        slug: str,
        test_dvar: str,
        analyzer: Callable[[str], tuple[list[bz.BzEvent], list[str]]],
        completion_events: Callable[[str], bool],
        capture: VisualCapture | None = None,
    ) -> None:
        print(f"--> Running {mode} on nazi_zombie_{slug} (:{display_num})", flush=True)
        gauntlet = mode == "enhanced-gauntlet"
        dvars = [
            ("gauntlet_enabled", str(int(gauntlet))),
            ("bz_enabled", "1"),
            ("bz_perks_enabled", "1"),
            ("bz_classes_enabled", "1"),
            ("bz_pap_enabled", "1"),
            ("bz_elements_enabled", "1"),
            ("bz_companions_enabled", "0"),
        ]
        for key in ("bz_test_coop_selftest", "bz_test_visual_tour", "bz_test_gauntlet_seed"):
            dvars.append((key, str(int(key == test_dvar))))
        if gauntlet:
            dvars.extend([
                ("gauntlet_active", "0"),
                ("gauntlet_test_force_coop", "0"),
                ("gauntlet_test_autoclear", "1"),
                ("gauntlet_test_target_round", "1"),
                ("gauntlet_test_banner_delay", "1.0"),
            ])

        result = bz.run_bz_scenario(
            name=f"{mode} {slug}", log_filename=f"{mode}_{slug}.console.log",
            map_name=f"nazi_zombie_{slug}", dvars=dvars, stop_predicate=completion_events,
            analyzer=analyzer, display_num=display_num, xdg_config_home=xdg_tmp.name,
            proton=args.proton, steam_root=args.steam_root, steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix, timeout_s=args.timeout, settle_s=0.8,
            log_dir=out_dir, observe_log=capture,
            launch_cmd="+map" if gauntlet else "+devmap",
        )
        if capture is not None:
            result.errors.extend(capture.errors)
            result.passed = not result.errors
        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"    [{status}] {result.name} in {result.duration_s:.1f}s ({result.saved_log})")
        for message in result.errors:
            print(f"      {message}")

    def gauntlet_finished(log_text: str) -> bool:
        return any(
            e.event_type == "GAUNTLET_BZ_SEED_FAIL"
            or (e.event_type == "GAUNTLET_BZ_RESTORED" and e.fields.get("map") == "nazi_zombie_asylum")
            for e in bz.parse_bz_events(log_text)
        )

    try:
        responder.start()
        if args.mode in ("all", "coop"):
            run("coop", "factory", "bz_test_coop_selftest", analyze_bz_coop_selftest_log,
                lambda log: "BZ_EVENT|BZ_COOP_SELFTEST_PASS|" in log or "BZ_EVENT|BZ_COOP_SELFTEST_FAIL|" in log)
        if args.mode in ("all", "enhanced-gauntlet"):
            run("enhanced-gauntlet", "prototype", "bz_test_gauntlet_seed",
                analyze_enhanced_gauntlet_log, gauntlet_finished)
        if has_visual_tour:
            for slug in dict.fromkeys(args.maps):
                capture = VisualCapture(slug, out_dir, display_num)
                try:
                    run("visual-tour", slug, "bz_test_visual_tour",
                        lambda log: analyze_visual_tour_result(log, capture.frames),
                        lambda log: "BZ_EVENT|VISUAL_TOUR_DONE|" in log or "BZ_EVENT|VISUAL_TOUR_FAIL|" in log,
                        capture=capture)
                finally:
                    frames.extend(capture.frames)
    finally:
        stop.set()
        try:
            if responder.ident is not None:
                responder.join(timeout=2)
        finally:
            smoke_verify.stop_virtual_display(xvfb, xfwm, xdg_tmp)
        if has_visual_tour:
            manifest = [dict(asdict(frame), path=str(frame.path)) for frame in frames]
            (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
