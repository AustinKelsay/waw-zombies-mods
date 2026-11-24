#!/usr/bin/env python3
"""Menu patchers, offline UI contract validators, and in-engine HUD verifier for Ticket #8.

Provides:
  1. Pure build-time stock menu patchers (`patch_main_menu`, `patch_levels_menu`,
     `patch_xboxlive_lobby_menu`, `patch_systemlink_lobby_menu`, `stage_patched_menus`)
     so `scripts/build_mod.py` can inject Zombie Gauntlet entries into installed
     stock WaW 1.7 `tools_root/raw/ui/*.menu` files cleanly without duplicating
     large stock menus into git.
  2. Pure offline UI contract & syntax validators (`validate_menu_braces`,
     `validate_ui_contracts`) verifying balanced braces, Solo Gauntlet & Classic
     Mode dvar actions, Co-op `gauntlet_enabled` toggle, Nacht der Untoten fresh
     Run map-lock, and `gauntlet_lobby_status` readout.
  3. Pure in-engine HUD log analyzer (`analyze_hud_log`) and headless Xvfb/Proton
     CLI runner matching `scripts/verify_cycle1.py` and `scripts/verify_cycle2.py`.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import re
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_mod  # noqa: E402
import smoke_verify  # noqa: E402
import verify_cycle1  # noqa: E402

GauntletEvent = verify_cycle1.GauntletEvent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_MOD_UI_DIR = REPO_ROOT / "mod" / "ui"


# ---------------------------------------------------------------------------
# Pure WaW 1.7 Menu Syntax & Contract Validators
# ---------------------------------------------------------------------------


def format_expected_badge(cycle: int, stage: int, target_round: int) -> str:
    """Return the canonical ASCII-safe Gauntlet HUD badge text."""
    return f"GAUNTLET - C{cycle} S{stage}/4 - TARGET R{target_round}"


def _strip_c_comments_and_strings(text: str) -> str:
    """Replace // comments, /* ... */ blocks, and quoted strings with spaces."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        # Line comment
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] != "\n":
                i += 1
            continue
        # Block comment
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                if text[i] == "\n":
                    out.append("\n")
                i += 1
            i += 2
            continue
        # String literal
        if ch == '"':
            i += 1
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if text[i] == "\n":
                    out.append("\n")
                i += 1
            i += 1
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def validate_menu_braces(text: str, filename: str = "<menu>") -> list[str]:
    """Verify every `{` and `}` is balanced outside comments and string literals."""
    errors: list[str] = []
    cleaned = _strip_c_comments_and_strings(text)
    depth = 0
    line_num = 1
    for ch in cleaned:
        if ch == "\n":
            line_num += 1
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                errors.append(
                    f"{filename}:{line_num}: Unbalanced closing brace '}}' (depth went negative)"
                )
                depth = 0
    if depth != 0:
        errors.append(f"{filename}: Unbalanced opening brace '{{' ({depth} unclosed at EOF)")
    return errors


def validate_ui_contracts(ui_dir: Path = DEFAULT_MOD_UI_DIR) -> list[str]:
    """Validate mod/ui/ menu files, brace balance, and Solo / Co-op dvar contracts."""
    errors: list[str] = []

    required_files = ("patch_menus.txt", "gauntlet_menus.inc", "pc_gamesetup_coop.menu")
    texts: dict[str, str] = {}
    for rel in required_files:
        path = ui_dir / rel
        if not path.is_file():
            errors.append(f"Missing required UI file: {path}")
            continue
        content = path.read_text(encoding="latin1")
        texts[rel] = content
        errors.extend(validate_menu_braces(content, filename=rel))

    # Validate patch_menus.txt loads all overridden menus
    patch_txt = texts.get("patch_menus.txt", "")
    if patch_txt:
        for menu_path in (
            "ui/main.menu",
            "ui/levels.menu",
            "ui/pc_gamesetup_coop.menu",
            "ui/xboxlive_lobby.menu",
            "ui/systemlink_lobby.menu",
        ):
            if f'"{menu_path}"' not in patch_txt:
                errors.append(f"patch_menus.txt missing loadMenu entry for {menu_path!r}")

    # Validate shared macros in gauntlet_menus.inc
    inc = texts.get("gauntlet_menus.inc", "")
    if inc:
        solo_macro_checks = (
            ("GAUNTLET_SOLO_START_ACTION", "Solo start action macro"),
            ("set gauntlet_enabled 1", "Solo Gauntlet mode enable"),
            ("set gauntlet_active 0", "Solo stale active reset"),
            ("set gauntlet_pending_transition 0", "Solo stale transition reset"),
            ("set gauntlet_cycle 1", "Solo cycle reset"),
            ("set gauntlet_stage 1", "Solo stage reset"),
            ("set gauntlet_total_rounds 0", "Solo total_rounds reset"),
            ("set gauntlet_player_points", "Solo player points ledger reset"),
            ("set gauntlet_player_perks", "Solo player perks ledger reset"),
            ("set gauntlet_next_map", "Solo next map handoff reset"),
            ("set gauntlet_next_display", "Solo next display handoff reset"),
            ("set gauntlet_lobby_status", "Solo lobby status reset"),
            ("map nazi_zombie_prototype", "Solo launch Nacht der Untoten"),
            ("GAUNTLET_CLASSIC_MODE_ACTION", "Classic Mode disable macro"),
            ("set gauntlet_enabled 0", "Classic Mode explicit disable"),
            ("GAUNTLET_COOP_SETUP_TOGGLE", "Co-op Host Setup toggle macro"),
            ("gauntlet_enabled", "Co-op gauntlet_enabled dvar binding"),
            ("Classic Mode", "Co-op toggle Classic Mode label"),
            ("Zombie Gauntlet", "Co-op toggle Zombie Gauntlet label"),
            ("GAUNTLET_COOP_FRESH_LOCK_ACTION", "Co-op fresh Run map-lock macro"),
            ("set ui_mapname nazi_zombie_prototype", "Co-op Nacht der Untoten lock"),
            ("GAUNTLET_COOP_LOBBY_STATUS_PANEL", "Co-op lobby status panel macro"),
            ("gauntlet_lobby_status", "Co-op queued next-Stage status dvar binding"),
            ("dvarInt( gauntlet_pending_transition ) == 1", "Co-op queued Stage visibility condition"),
        )
        for needle, label in solo_macro_checks:
            if needle not in inc:
                errors.append(f"gauntlet_menus.inc missing {label} ({needle!r})")

    # Validate pc_gamesetup_coop.menu structure and contracts
    coop = texts.get("pc_gamesetup_coop.menu", "")
    if coop:
        coop_checks = (
            ('#include "ui/gauntlet_menus.inc"', "gauntlet_menus.inc include"),
            ("menuDef", "menuDef block"),
            ('"pc_gamesetup_coop"', "pc_gamesetup_coop menu name"),
            ("GAUNTLET_COOP_SETUP_TOGGLE", "Zombie Gauntlet toggle item"),
            ("GAUNTLET_COOP_SETUP_LOCKED_MAP_BOX", "locked map / queued status panel"),
            ("FEEDER_ALLMAPS", "stock Classic Mode maplist feeder"),
            ("dvarInt( gauntlet_enabled ) == 0", "Classic Mode unmodified maplist visibility"),
            ("GAUNTLET_COOP_FRESH_LOCK_ACTION", "fresh Run Nacht der Untoten lock on OK"),
            ("GAUNTLET_CLASSIC_MODE_ACTION", "Classic Mode action on OK"),
            ("dvarInt( gauntlet_pending_transition ) == 1", "mid-Run queued OK branch"),
        )
        for needle, label in coop_checks:
            if needle not in coop:
                errors.append(f"pc_gamesetup_coop.menu missing {label} ({needle!r})")

    return errors


# ---------------------------------------------------------------------------
# Pure Build-Time Stock Menu Patchers (for tools_root/raw/ui/*.menu)
# ---------------------------------------------------------------------------

GAUNTLET_INCLUDE_LINE = '#include "ui/gauntlet_menus.inc"'


def _ensure_include_gauntlet_menus(source: str) -> str:
    if GAUNTLET_INCLUDE_LINE in source:
        return source
    newline = "\r\n" if "\r\n" in source else "\n"
    anchor = '#include "ui/choices_setup_common.menu"'
    idx = source.find(anchor)
    if idx == -1:
        raise ValueError(f"Could not find {anchor!r} anchor to inject {GAUNTLET_INCLUDE_LINE}")
    insert_pos = idx + len(anchor)
    return source[:insert_pos] + f"{newline}{GAUNTLET_INCLUDE_LINE}" + source[insert_pos:]


def patch_main_menu(source: str) -> str:
    """Patch stock ui/main.menu to add Solo 'ZOMBIE GAUNTLET' entry and Classic reset."""
    newline = "\r\n" if "\r\n" in source else "\n"
    text = _ensure_include_gauntlet_menus(source)

    # 1. Ensure LOCAL_ZOMBIE_RESET also resets gauntlet_enabled to 0 for Classic Mode entries
    zombie_reset_re = re.compile(r'(exec\s+"set zombiemode 0)";')
    if 'set gauntlet_enabled 0' not in text:
        new_text, count = zombie_reset_re.subn(
            r'\1; set gauntlet_enabled 0";', text, count=1
        )
        if count != 1:
            raise ValueError("Could not locate LOCAL_ZOMBIE_RESET in ui/main.menu")
        text = new_text

    # 2. Inject dedicated Solo "ZOMBIE GAUNTLET" button into PC main_solo slot 4
    mission_select_re = re.compile(
        r'^(?P<indent>[ \t]*)CHOICE_BUTTON_VIS\(\s*3,\s*"@MENU_MISSION_SELECT"[^\n]*$',
        re.MULTILINE,
    )
    if "GAUNTLET_SOLO_START_ACTION" not in text:
        match = mission_select_re.search(text)
        if match is None:
            raise ValueError("Could not locate PC main_solo Mission Select button in ui/main.menu")
        indent = match.group("indent")
        gauntlet_btn = (
            f'{indent}CHOICE_BUTTON_VIS( 4, "ZOMBIE GAUNTLET", '
            f'GAUNTLET_SOLO_START_ACTION, when( !localvarBool( ui_hideBack ) ); )'
        )
        text = text[: match.end()] + f"{newline}{gauntlet_btn}" + text[match.end() :]

    return text


def patch_levels_menu(source: str) -> str:
    """Patch stock ui/levels.menu (levels_unlock) with Solo Gauntlet + Classic Mode guard."""
    newline = "\r\n" if "\r\n" in source else "\n"
    text = _ensure_include_gauntlet_menus(source)

    # 1. Define missing NOT_CHEAT_CONDITION present in stock WaW 1.4 Mod Tools levels.menu
    if "#define NOT_CHEAT_CONDITION" not in text:
        cheat_not_re = re.compile(r"^(#define[ \t]+CHEAT_CONDITION_NOT[^\n]*)$", re.MULTILINE)
        match = cheat_not_re.search(text)
        if match is None:
            raise ValueError("Could not locate CHEAT_CONDITION_NOT in ui/levels.menu")
        text = (
            text[: match.end()]
            + f"{newline}#define NOT_CHEAT_CONDITION\t\t( 1 )"
            + text[match.end() :]
        )

    # 2. Ensure all Classic Mode Solo Nazi Zombies entries explicitly set gauntlet_enabled 0
    if 'setdvar gauntlet_enabled "0"' not in text:
        nodiff_re = re.compile(
            r'(#define[ \t]+LOCAL_MAP_ACTION_NODIFFICULTY[^\n]*\\\r?\n)',
            re.MULTILINE,
        )
        new_text, count = nodiff_re.subn(
            rf'\1\tsetdvar gauntlet_enabled "0"; \\{newline}', text, count=1
        )
        if count != 1:
            raise ValueError("Could not locate LOCAL_MAP_ACTION_NODIFFICULTY in ui/levels.menu")
        text = new_text

    # 3. Add dedicated "ZOMBIE GAUNTLET" button at slot 1 of levels_unlock above the 4 Classic maps
    if "GAUNTLET_SOLO_START_ACTION" not in text:
        proto_re = re.compile(
            r'^(?P<indent>[ \t]*)LOCAL_NONGERMAN_MAP_SELECTION_NODIFFICULTY2\(\s*2,\s*"@MENU_LEVEL_ZOMBIE_PROTOTYPE"',
            re.MULTILINE,
        )
        match = proto_re.search(text)
        if match is None:
            raise ValueError("Could not locate levels_unlock Nacht der Untoten entry in ui/levels.menu")
        indent = match.group("indent")
        gauntlet_entry = (
            f'{indent}BZ_ZOMBIE_CHOICE_BUTTON( 1, "ZOMBIE GAUNTLET", GAUNTLET_SOLO_START_ACTION, '
            f'"gauntlet_prototype", "nazi_zombie_prototype", "Endless 4-map escalating Zombies Run starting on Nacht der Untoten.", '
            f'15, exec "set ui_load_index 15" ){newline}'
        )
        text = text[: match.start()] + gauntlet_entry + text[match.start() :]

    return text


def patch_xboxlive_lobby_menu(source: str) -> str:
    """Patch stock ui/xboxlive_lobby.menu with Co-op status readout, fresh-Run lock, and disband reset."""
    newline = "\r\n" if "\r\n" in source else "\n"
    text = _ensure_include_gauntlet_menus(source)

    # 1. Guard host Start Match so a fresh Gauntlet Run always launches Nacht der Untoten
    if "GAUNTLET_COOP_FRESH_LOCK_ACTION" not in text:
        start_btn_re = re.compile(
            r'^(?P<indent>[ \t]*)CHOICE_BUTTON_FOCUS_VIS_EX\(\s*1,\s*"@MPUI_START_MATCH",\s*SETUP_ACTION_STARTMATCH,'
            r'(?P<rest>[^\n]*)when\(\s*IS_PARTY_HOST\s*\),(?P<tail>[^\n]*)$',
            re.MULTILINE,
        )
        match = start_btn_re.search(text)
        if match is None:
            raise ValueError("Could not locate PC Start Match button in ui/xboxlive_lobby.menu")
        indent = match.group("indent")
        rest = match.group("rest")
        tail = match.group("tail")
        replacement = (
            f'{indent}CHOICE_BUTTON_FOCUS_VIS_EX( 1, "@MPUI_START_MATCH", SETUP_ACTION_STARTMATCH,{rest}'
            f'when( IS_PARTY_HOST && ( dvarInt( gauntlet_enabled ) == 0 || dvarInt( gauntlet_pending_transition ) == 1 ) ),{tail}{newline}'
            f'{indent}CHOICE_BUTTON_FOCUS_VIS_EX( 1, "@MPUI_START_MATCH", GAUNTLET_COOP_FRESH_LOCK_ACTION SETUP_ACTION_STARTMATCH,{rest}'
            f'when( IS_PARTY_HOST && dvarInt( gauntlet_enabled ) == 1 && dvarInt( gauntlet_pending_transition ) == 0 ),{tail}'
        )
        text = text[: match.start()] + replacement + text[match.end() :]

    # 2. Inject Co-op lobby Gauntlet status readout panel (bound to gauntlet_lobby_status)
    if "GAUNTLET_COOP_LOBBY_STATUS_PANEL" not in text:
        safearea_re = re.compile(r'^(?P<indent>[ \t]*)#include\s+"ui/safearea\.menu"', re.MULTILINE)
        match = safearea_re.search(text)
        if match is None:
            raise ValueError('Could not locate #include "ui/safearea.menu" in ui/xboxlive_lobby.menu')
        indent = match.group("indent")
        panel = (
            f"{indent}GAUNTLET_COOP_LOBBY_STATUS_PANEL( 30, 178, 250, 44, HORIZONTAL_ALIGN_LEFT, VERTICAL_ALIGN_TOP ){newline}"
        )
        text = text[: match.start()] + panel + text[match.start() :]

    # 3. Clear persisted Run state if the host/player leaves the Co-op lobby
    if "GAUNTLET_CLEAR_RUN_STATE_EXEC" not in text:
        leave_re = re.compile(
            r'(#define[ \t]+LOCAL_ACCEPT_LEAVELOBBY_PC[ \t]*\\\r?\n)',
            re.MULTILINE,
        )
        new_text, count = leave_re.subn(
            rf"\1\t\t\t\tGAUNTLET_CLEAR_RUN_STATE_EXEC \\{newline}", text, count=1
        )
        if count != 1:
            raise ValueError("Could not locate LOCAL_ACCEPT_LEAVELOBBY_PC in ui/xboxlive_lobby.menu")
        text = new_text

    return text


def patch_systemlink_lobby_menu(source: str) -> str:
    """Patch stock ui/systemlink_lobby.menu with Start Match fresh-Run lock, status readout, and disband reset."""
    newline = "\r\n" if "\r\n" in source else "\n"
    text = _ensure_include_gauntlet_menus(source)

    if "GAUNTLET_COOP_FRESH_LOCK_ACTION" not in text:
        start_btn_re = re.compile(
            r'^(?P<indent>[ \t]*)CHOICE_BUTTON_VIS\(\s*1,\s*"@MPUI_START_MATCH",\s*SETUP_ACTION_STARTMATCH,\s*'
            r'when\(\s*dvarbool\(\s*systemlinkpartyandhost\s*\)\s*\)\s*\)(?P<tail>[^\n]*)$',
            re.MULTILINE | re.IGNORECASE,
        )
        match = start_btn_re.search(text)
        if match is None:
            raise ValueError("Could not locate Start Match button in ui/systemlink_lobby.menu")
        indent = match.group("indent")
        tail = match.group("tail")
        replacement = (
            f'{indent}CHOICE_BUTTON_VIS( 1, "@MPUI_START_MATCH", SETUP_ACTION_STARTMATCH, '
            f'when( dvarbool( systemlinkpartyandhost ) && ( dvarInt( gauntlet_enabled ) == 0 || dvarInt( gauntlet_pending_transition ) == 1 ) ) ){tail}{newline}'
            f'{indent}CHOICE_BUTTON_VIS( 1, "@MPUI_START_MATCH", GAUNTLET_COOP_FRESH_LOCK_ACTION SETUP_ACTION_STARTMATCH, '
            f'when( dvarbool( systemlinkpartyandhost ) && dvarInt( gauntlet_enabled ) == 1 && dvarInt( gauntlet_pending_transition ) == 0 ) ){tail}'
        )
        text = text[: match.start()] + replacement + text[match.end() :]

    if "GAUNTLET_COOP_LOBBY_STATUS_PANEL" not in text:
        safearea_re = re.compile(r'^(?P<indent>[ \t]*)#include\s+"ui/safearea\.menu"', re.MULTILINE)
        match = safearea_re.search(text)
        if match is None:
            raise ValueError('Could not locate #include "ui/safearea.menu" in ui/systemlink_lobby.menu')
        indent = match.group("indent")
        panel = (
            f"{indent}GAUNTLET_COOP_LOBBY_STATUS_PANEL( 30, 178, 250, 44, HORIZONTAL_ALIGN_LEFT, VERTICAL_ALIGN_TOP ){newline}"
        )
        text = text[: match.start()] + panel + text[match.start() :]

    if "GAUNTLET_CLEAR_RUN_STATE_EXEC" not in text:
        leave_re = re.compile(
            r'(#define[ \t]+LOCAL_ACCEPT_LEAVE[ \t]*\\\r?\n)',
            re.MULTILINE,
        )
        new_text, count = leave_re.subn(
            rf"\1\t\t\t\tGAUNTLET_CLEAR_RUN_STATE_EXEC \\{newline}", text, count=1
        )
        if count != 1:
            raise ValueError("Could not locate LOCAL_ACCEPT_LEAVE in ui/systemlink_lobby.menu")
        text = new_text

    return text


def stage_patched_menus(tools_root: Path, stage_dir: Path) -> list[Path]:
    """Patch installed stock WaW 1.7 menus from tools_root/raw/ui/ into stage_dir/ui/."""
    raw_ui = tools_root / "raw" / "ui"
    out_ui = stage_dir / "ui"
    out_ui.mkdir(parents=True, exist_ok=True)

    patchers = (
        ("main.menu", patch_main_menu),
        ("levels.menu", patch_levels_menu),
        ("xboxlive_lobby.menu", patch_xboxlive_lobby_menu),
        ("systemlink_lobby.menu", patch_systemlink_lobby_menu),
    )

    written: list[Path] = []
    for filename, patch_fn in patchers:
        src_path = raw_ui / filename
        if not src_path.is_file():
            raise FileNotFoundError(f"Stock WaW menu file missing: {src_path}")
        stock_text = src_path.read_text(encoding="latin1")
        patched_text = patch_fn(stock_text)
        brace_errors = validate_menu_braces(patched_text, filename=filename)
        if brace_errors:
            raise ValueError(f"Patched menu {filename} failed brace validation: {brace_errors}")
        dst_path = out_ui / filename
        dst_path.write_text(patched_text, encoding="latin1")
        written.append(dst_path)

    return written


# ---------------------------------------------------------------------------
# Pure In-Engine HUD Telemetry Log Analyzer
# ---------------------------------------------------------------------------


def analyze_hud_log(
    log_text: str,
    gauntlet_enabled: int = 1,
    expected_badges: list[tuple[int, int, int]] | None = None,
    expected_destroy_reasons: list[str] | None = None,
) -> tuple[list[GauntletEvent], list[str]]:
    """Validate HUD_INIT / HUD_DESTROYED telemetry and Classic Mode isolation in console.log."""
    events = verify_cycle1.parse_gauntlet_events(log_text)
    errors: list[str] = []

    for label, pattern in smoke_verify.FATAL_LOG_PATTERNS:
        for line in log_text.splitlines():
            if pattern.search(line):
                errors.append(f"{label}: {line.strip()}")
                break

    hud_inits = [e for e in events if e.event_type == "HUD_INIT"]
    hud_destroys = [e for e in events if e.event_type == "HUD_DESTROYED"]

    if gauntlet_enabled == 0:
        if hud_inits:
            errors.append(
                f"Classic Mode (gauntlet_enabled=0) must emit ZERO HUD_INIT events, found {len(hud_inits)}"
            )
        if hud_destroys:
            errors.append(
                f"Classic Mode (gauntlet_enabled=0) must emit ZERO HUD_DESTROYED events, found {len(hud_destroys)}"
            )
        return events, errors

    if expected_badges is not None:
        if len(hud_inits) < len(expected_badges):
            errors.append(
                f"Expected at least {len(expected_badges)} HUD_INIT events, found {len(hud_inits)}"
            )
        else:
            for idx, (exp_c, exp_s, exp_t) in enumerate(expected_badges):
                ev = hud_inits[idx]
                exp_text = format_expected_badge(exp_c, exp_s, exp_t)
                checks = (
                    ("cycle", str(exp_c)),
                    ("stage", str(exp_s)),
                    ("target_round", str(exp_t)),
                    ("text", exp_text),
                )
                for key, exp_val in checks:
                    actual_val = ev.fields.get(key)
                    if actual_val != exp_val:
                        errors.append(
                            f"HUD_INIT #{idx + 1} field {key}={actual_val!r}, "
                            f"expected {exp_val!r} ({ev.raw})"
                        )

    if expected_destroy_reasons is not None:
        if len(hud_destroys) < len(expected_destroy_reasons):
            errors.append(
                f"Expected at least {len(expected_destroy_reasons)} HUD_DESTROYED events, "
                f"found {len(hud_destroys)}"
            )
        else:
            for idx, exp_reason in enumerate(expected_destroy_reasons):
                ev = hud_destroys[idx]
                actual_reason = ev.fields.get("reason")
                if actual_reason != exp_reason:
                    errors.append(
                        f"HUD_DESTROYED #{idx + 1} reason={actual_reason!r}, "
                        f"expected {exp_reason!r} ({ev.raw})"
                    )

    return events, errors


# ---------------------------------------------------------------------------
# CLI Runner (Offline UI Check + Optional Headless In-Engine Verification)
# ---------------------------------------------------------------------------


@dataclass
class HudVerifySummary:
    ui_errors: list[str] = field(default_factory=list)
    scenario_results: list[tuple[str, bool, list[str]]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.ui_errors and all(ok for _, ok, _ in self.scenario_results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline-only",
        action="store_true",
        help="Validate mod/ui/ menu syntax and contracts offline without launching CoDWaW.exe.",
    )
    parser.add_argument("--skip-build", action="store_true", help="Skip building mod.ff before launching.")
    parser.add_argument("--timeout", type=float, default=140.0, help="Per-scenario timeout in seconds.")
    parser.add_argument("--target-round", type=int, default=1, help="gauntlet_test_target_round override.")
    parser.add_argument("--banner-delay", type=float, default=1.0, help="gauntlet_test_banner_delay override.")
    parser.add_argument("--prep-duration", type=int, default=3, help="gauntlet_test_prep_duration override.")
    parser.add_argument("--tools-root", type=Path, default=build_mod.DEFAULT_TOOLS_ROOT)
    parser.add_argument("--steam-root", type=Path, default=build_mod.DEFAULT_STEAM_ROOT)
    parser.add_argument("--dev-root", type=Path, default=build_mod.DEFAULT_DEV_ROOT)
    parser.add_argument("--steam-game", type=Path, default=build_mod.DEFAULT_STEAM_GAME)
    parser.add_argument("--steam-appdata", type=Path, default=build_mod.DEFAULT_STEAM_APPDATA)
    parser.add_argument("--playtest-prefix", type=Path, default=smoke_verify.DEFAULT_PLAYTEST_PREFIX)
    parser.add_argument("--proton", type=Path, default=smoke_verify.DEFAULT_PROTON)
    args = parser.parse_args(argv)

    print("=== Validating mod/ui/ Solo & Co-op menu contracts ===")
    ui_errors = validate_ui_contracts(DEFAULT_MOD_UI_DIR)
    if ui_errors:
        for err in ui_errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        return 1
    print("  [PASS] mod/ui/ syntax and dvar-action contracts verified")

    if args.offline_only:
        return 0

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

    print("\n=== Starting headless Xvfb display for HUD & Menu in-engine verification ===")
    display_num, xvfb, xfwm, xdg_tmp = smoke_verify.start_virtual_display()
    summary = HudVerifySummary()
    try:
        # Scenario 1: Gauntlet Stage 1 -> Stage 2 HUD_INIT + HUD_DESTROYED + HUD_INIT update
        print("\n--> Scenario 1: Gauntlet HUD badge lifecycle across Stage 1 -> Stage 2")
        res1 = verify_cycle2.run_waw_scenario(
            name="Gauntlet HUD lifecycle (Stage 1 -> Stage 2)",
            log_filename="hud_s1_stage_lifecycle.console.log",
            start_map="nazi_zombie_prototype",
            extra_dvars=[
                ("gauntlet_active", "0"),
                ("gauntlet_test_target_round", str(args.target_round)),
                ("gauntlet_test_banner_delay", str(args.banner_delay)),
                ("gauntlet_test_prep_duration", str(args.prep_duration)),
                ("gauntlet_test_autoclear", "1"),
            ],
            stop_predicate=lambda evs: sum(1 for e in evs if e.event_type == "HUD_INIT") >= 2,
            analyzer=lambda txt: analyze_hud_log(
                txt,
                gauntlet_enabled=1,
                expected_badges=[(1, 1, args.target_round), (1, 2, args.target_round)],
                expected_destroy_reasons=["gauntlet_stage_clear"],
            ),
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=args.timeout,
        )
        summary.scenario_results.append((res1.name, res1.passed, res1.errors))

        # Scenario 2: Classic Mode (gauntlet_enabled=0) emits ZERO HUD_INIT events
        print("\n--> Scenario 2: Classic Mode zero Gauntlet HUD regression check")
        classic_res = smoke_verify.smoke_map(
            map_name="nazi_zombie_prototype",
            gauntlet_enabled=0,
            display_num=display_num,
            xdg_config_home=xdg_tmp.name,
            proton=args.proton,
            steam_root=args.steam_root,
            steam_game=args.steam_game,
            playtest_prefix=args.playtest_prefix,
            timeout_s=args.timeout,
            settle_s=2.5,
        )
        classic_log = (
            classic_res.saved_log.read_text(encoding="utf-8", errors="replace")
            if classic_res.saved_log and classic_res.saved_log.is_file()
            else ""
        )
        _, classic_hud_errors = analyze_hud_log(classic_log, gauntlet_enabled=0)
        combined_classic_errors = list(classic_res.errors) + classic_hud_errors
        summary.scenario_results.append(
            ("Classic Mode zero HUD_INIT", len(combined_classic_errors) == 0, combined_classic_errors)
        )
    finally:
        smoke_verify.stop_virtual_display(xvfb, xfwm, xdg_tmp)

    print("\n=== HUD & Menu Verification Summary ===")
    for name, ok, errs in summary.scenario_results:
        tag = "PASS" if ok else "FAIL"
        print(f"  [{tag}] {name}")
        for err in errs:
            print(f"        ERROR: {err}", file=sys.stderr)
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
