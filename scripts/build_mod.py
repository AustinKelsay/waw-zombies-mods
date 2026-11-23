#!/usr/bin/env python3
"""Build and deploy the unified waw_gauntlet fastfile (mod.ff) via Treyarch's linker."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

MOD_NAME = "waw_gauntlet"
STOCK_MAPS = (
    "nazi_zombie_prototype",
    "nazi_zombie_asylum",
    "nazi_zombie_sumpf",
    "nazi_zombie_factory",
)
STOCK_MAP_SLUGS = {
    "nazi_zombie_prototype": "prototype",
    "nazi_zombie_asylum": "asylum",
    "nazi_zombie_sumpf": "sumpf",
    "nazi_zombie_factory": "factory",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_SRC_DIR = REPO_ROOT / "mod"
DIST_DIR = REPO_ROOT / "dist" / MOD_NAME
OPEN_TOOL_SH = REPO_ROOT / "scripts" / "open_tool.sh"

DEFAULT_STEAM_ROOT = Path(os.environ.get("WAW_STEAM_ROOT", Path.home() / ".local/share/Steam"))
DEFAULT_DEV_ROOT = Path(os.environ.get("WAW_DEV_ROOT", Path.home() / "Games/waw-zombies-dev"))
DEFAULT_TOOLS_ROOT = DEFAULT_DEV_ROOT / "game"
DEFAULT_STEAM_GAME = DEFAULT_STEAM_ROOT / "steamapps/common/Call of Duty World at War"
DEFAULT_STEAM_APPDATA = (
    DEFAULT_STEAM_ROOT
    / "steamapps/compatdata/10090/pfx/drive_c/users/steamuser/AppData/Local/Activision/CoDWaW"
)

ZOMBIEMODE_MAIN_RE = re.compile(
    r"^(?P<indent>[ \t]*)maps\\_zombiemode::main\((?P<args>[^)]*)\);(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE,
)
ROUND_THINK_CALL_RE = re.compile(
    r"^(?P<indent>[ \t]*)level[ \t]+thread[ \t]+round_think\(\);(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE,
)
ROUND_WAIT_CALL_RE = re.compile(
    r"^(?P<indent>[ \t]*)round_wait\(\);(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE,
)
END_GAME_DEF_RE = re.compile(
    r"^end_game\(\)[ \t]*\r?\n\{",
    re.MULTILINE,
)
INTERMISSION_TRUE_RE = re.compile(
    r"^(?P<indent>[ \t]*)level\.intermission[ \t]*=[ \t]*true;(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE,
)

PRE_HOOK_CALL = "maps\\_gauntlet_bootstrap::pre_zombiemode_init();"
POST_HOOK_CALL = "level thread maps\\_gauntlet_bootstrap::post_zombiemode_init();"


def extract_rawfile_from_ff(ff_path: Path, rawfile_name: str) -> bytes:
    """Extract a null-terminated rawfile asset payload from a WaW .ff fastfile."""
    data = ff_path.read_bytes()
    if len(data) < 12 or not data.startswith(b"IWff"):
        raise ValueError(f"Not a valid WaW fastfile: {ff_path}")

    decompressed = zlib.decompress(data[12:])
    needle = rawfile_name.encode("ascii") + b"\x00"
    idx = decompressed.find(needle)
    if idx == -1:
        raise ValueError(f"Rawfile {rawfile_name!r} not found in {ff_path}")

    start = idx + len(needle)
    end = decompressed.find(b"\x00", start)
    if end == -1:
        raise ValueError(f"Unterminated rawfile {rawfile_name!r} in {ff_path}")
    return decompressed[start:end]


def resolve_stock_ff(map_name: str, steam_game: Path, tools_root: Path, prefer_patch: bool = False) -> Path:
    """Find the installed stock fastfile for a Nazi Zombies map."""
    candidates = []
    if prefer_patch:
        candidates.extend(
            [
                steam_game / "zone/english" / f"{map_name}_patch.ff",
                tools_root / "zone/english" / f"{map_name}_patch.ff",
            ]
        )
    candidates.extend(
        [
            steam_game / "zone/english" / f"{map_name}.ff",
            tools_root / "zone/english" / f"{map_name}.ff",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Could not locate stock fastfile for {map_name} in {steam_game} or {tools_root}"
    )


def zombiemode_module_for_map(map_name: str) -> str:
    """Return the per-map hooked _zombiemode script stem (without .gsc)."""
    slug = STOCK_MAP_SLUGS.get(map_name)
    if slug is None:
        raise ValueError(f"Unsupported stock Nazi Zombies map: {map_name!r}")
    return f"_zombiemode_gauntlet_{slug}"


def extract_stock_zombiemode(map_name: str, steam_game: Path, tools_root: Path) -> bytes:
    """Extract era-specific stock maps/_zombiemode.gsc, preferring <map>_patch.ff."""
    rawfile_rel = "maps/_zombiemode.gsc"
    ff_patch = resolve_stock_ff(map_name, steam_game, tools_root, prefer_patch=True)
    try:
        return extract_rawfile_from_ff(ff_patch, rawfile_rel)
    except ValueError:
        ff_base = resolve_stock_ff(map_name, steam_game, tools_root, prefer_patch=False)
        if ff_base == ff_patch:
            raise
        return extract_rawfile_from_ff(ff_base, rawfile_rel)


def inject_map_hooks(script_bytes: bytes, map_name: str) -> bytes:
    """Inject Gauntlet bootstrap hooks and rewire maps\\_zombiemode::main(...) to per-map wrapper."""
    text = script_bytes.decode("latin1")
    newline = "\r\n" if "\r\n" in text else "\n"
    matches = list(ZOMBIEMODE_MAIN_RE.finditer(text))
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly 1 maps\\_zombiemode::main(...) call in maps/{map_name}.gsc, "
            f"found {len(matches)}"
        )

    match = matches[0]
    indent = match.group("indent")
    args = match.group("args")
    trailing = match.group("trailing")
    line_ending = "\r" if match.group(0).endswith("\r") else ""
    zm_mod = zombiemode_module_for_map(map_name)
    rewired_line = f"{indent}maps\\{zm_mod}::main({args});{trailing}"
    replacement = (
        f"{indent}{PRE_HOOK_CALL}{newline}"
        f"{rewired_line}{newline}"
        f"{indent}{POST_HOOK_CALL}{line_ending}"
    )
    patched = text[: match.start()] + replacement + text[match.end() :]
    return patched.encode("latin1")


def inject_zombiemode_hooks(script_bytes: bytes, map_name: str) -> bytes:
    """Inject strictly gated Gauntlet hooks into a stock map's maps/_zombiemode.gsc.

    Hooks injected (all strictly guarded by maps\\_gauntlet_mode::is_gauntlet_enabled()):
      1. round_start(): before `level thread round_think();` -> on_stage_init()
      2. round_think(): before `round_wait();` -> level thread on_round_started(level.round_number)
         and after `round_wait();` -> if (on_round_completed(level.round_number)) return;
      3. end_game(): after `level.intermission = true;` -> if (on_end_game()) return;

    Leaves all stock/DLC3 features and local waw_solo_fov() definitions 100% intact.
    """
    text = script_bytes.decode("latin1")
    newline = "\r\n" if "\r\n" in text else "\n"

    # 1. Hook round_start() before `level thread round_think();`
    rt_matches = list(ROUND_THINK_CALL_RE.finditer(text))
    if len(rt_matches) != 1:
        raise ValueError(
            f"Expected exactly 1 'level thread round_think();' in {map_name} _zombiemode.gsc, "
            f"found {len(rt_matches)}"
        )
    rt_match = rt_matches[0]
    rt_indent = rt_match.group("indent")
    rt_orig = rt_match.group(0)
    rt_hook = (
        f"{rt_indent}if ( maps\\_gauntlet_mode::is_gauntlet_enabled() ){newline}"
        f"{rt_indent}{{{newline}"
        f"{rt_indent}\tmaps\\_gauntlet_mode::on_stage_init();{newline}"
        f"{rt_indent}}}{newline}"
        f"{rt_orig}"
    )
    text = text[: rt_match.start()] + rt_hook + text[rt_match.end() :]

    # 2. Hook round_think() around `round_wait();`
    rw_matches = list(ROUND_WAIT_CALL_RE.finditer(text))
    if len(rw_matches) != 1:
        raise ValueError(
            f"Expected exactly 1 'round_wait();' call in {map_name} _zombiemode.gsc, "
            f"found {len(rw_matches)}"
        )
    rw_match = rw_matches[0]
    rw_indent = rw_match.group("indent")
    rw_orig = rw_match.group(0).rstrip("\r")
    rw_ending = "\r" if rw_match.group(0).endswith("\r") else ""
    rw_hook = (
        f"{rw_indent}if ( maps\\_gauntlet_mode::is_gauntlet_enabled() ){newline}"
        f"{rw_indent}{{{newline}"
        f"{rw_indent}\tlevel thread maps\\_gauntlet_mode::on_round_started( level.round_number );{newline}"
        f"{rw_indent}}}{newline}"
        f"{rw_orig}{newline}"
        f"{rw_indent}if ( maps\\_gauntlet_mode::is_gauntlet_enabled() ){newline}"
        f"{rw_indent}{{{newline}"
        f"{rw_indent}\tif ( maps\\_gauntlet_mode::on_round_completed( level.round_number ) ){newline}"
        f"{rw_indent}\t{{{newline}"
        f"{rw_indent}\t\treturn;{newline}"
        f"{rw_indent}\t}}{newline}"
        f"{rw_indent}}}{rw_ending}"
    )
    text = text[: rw_match.start()] + rw_hook + text[rw_match.end() :]

    # 3. Hook end_game() right after `level.intermission = true;`
    eg_matches = list(END_GAME_DEF_RE.finditer(text))
    if len(eg_matches) != 1:
        raise ValueError(
            f"Expected exactly 1 end_game() definition in {map_name} _zombiemode.gsc, "
            f"found {len(eg_matches)}"
        )
    eg_start = eg_matches[0].end()
    inter_match = INTERMISSION_TRUE_RE.search(text, pos=eg_start, endpos=eg_start + 300)
    if inter_match is None:
        raise ValueError(
            f"Could not locate 'level.intermission = true;' inside end_game() for {map_name}"
        )
    eg_indent = inter_match.group("indent")
    eg_orig = inter_match.group(0).rstrip("\r")
    eg_ending = "\r" if inter_match.group(0).endswith("\r") else ""
    eg_hook = (
        f"{eg_orig}{newline}"
        f"{eg_indent}if ( maps\\_gauntlet_mode::is_gauntlet_enabled() ){newline}"
        f"{eg_indent}{{{newline}"
        f"{eg_indent}\tif ( maps\\_gauntlet_mode::on_end_game() ){newline}"
        f"{eg_indent}\t{{{newline}"
        f"{eg_indent}\t\treturn;{newline}"
        f"{eg_indent}\t}}{newline}"
        f"{eg_indent}}}{eg_ending}"
    )
    text = text[: inter_match.start()] + eg_hook + text[inter_match.end() :]

    return text.encode("latin1")


def stage_mod_files(tools_root: Path, steam_game: Path) -> Path:
    """Stage mod sources, hooked stock map entry scripts, and per-map _zombiemode wrappers."""
    stage_dir = tools_root / "mods" / MOD_NAME
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)

    # Copy all tracked mod files (mod.csv, maps/_gauntlet_*.gsc, etc.)
    for src_path in sorted(MOD_SRC_DIR.rglob("*")):
        if src_path.is_dir():
            continue
        rel = src_path.relative_to(MOD_SRC_DIR)
        dst = stage_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst)

    # Extract each stock map entry script and era-specific maps/_zombiemode.gsc
    # (preferring <map>_patch.ff so DLC3 features and local waw_solo_fov() stay intact).
    for map_name in STOCK_MAPS:
        rawfile_rel = f"maps/{map_name}.gsc"
        ff_path = resolve_stock_ff(map_name, steam_game, tools_root, prefer_patch=False)
        stock_bytes = extract_rawfile_from_ff(ff_path, rawfile_rel)
        patched_map_bytes = inject_map_hooks(stock_bytes, map_name)
        dst = stage_dir / rawfile_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(patched_map_bytes)

        zm_stock_bytes = extract_stock_zombiemode(map_name, steam_game, tools_root)
        zm_patched_bytes = inject_zombiemode_hooks(zm_stock_bytes, map_name)
        zm_dst = stage_dir / "maps" / f"{zombiemode_module_for_map(map_name)}.gsc"
        zm_dst.parent.mkdir(parents=True, exist_ok=True)
        zm_dst.write_bytes(zm_patched_bytes)

    return stage_dir


def run_linker(tools_root: Path, steam_root: Path, dev_root: Path) -> Path:
    """Compile mod.ff using Treyarch's linker_pc.exe under Proton Experimental."""
    stage_dir = tools_root / "mods" / MOD_NAME
    mod_csv_src = stage_dir / "mod.csv"
    zone_source_dir = tools_root / "zone_source"
    zone_csv = zone_source_dir / "mod.csv"
    assetlist_dir = zone_source_dir / "english" / "assetlist"
    assetlist_csv = assetlist_dir / "mod.csv"
    zone_out = tools_root / "zone" / "english" / "mod.ff"

    if not mod_csv_src.is_file():
        raise FileNotFoundError(f"Missing mod manifest: {mod_csv_src}")

    assetlist_dir.mkdir(parents=True, exist_ok=True)

    prior_zone_csv = zone_csv.read_bytes() if zone_csv.exists() else None
    prior_assetlist_csv = assetlist_csv.read_bytes() if assetlist_csv.exists() else None
    if zone_out.exists():
        zone_out.unlink()

    try:
        shutil.copy2(mod_csv_src, zone_csv)
        if not assetlist_csv.exists():
            assetlist_csv.write_bytes(b"")

        env = os.environ.copy()
        env["WAW_STEAM_ROOT"] = str(steam_root)
        env["WAW_DEV_ROOT"] = str(dev_root)

        cmd = [
            str(OPEN_TOOL_SH),
            "linker",
            "-language",
            "english",
            "-compress",
            "-cleanup",
            "-nopause",
            "-moddir",
            MOD_NAME,
            "mod",
        ]
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            check=False,
        )
        if result.stdout:
            print(result.stdout.rstrip())
        if result.returncode != 0:
            raise RuntimeError(f"linker_pc.exe failed with exit code {result.returncode}")
        if not zone_out.is_file() or zone_out.stat().st_size == 0:
            raise RuntimeError(f"Expected compiled fastfile missing or empty: {zone_out}")

        DIST_DIR.mkdir(parents=True, exist_ok=True)
        dist_ff = DIST_DIR / "mod.ff"
        with TemporaryDirectory(dir=DIST_DIR) as tmp:
            staged_ff = Path(tmp) / "mod.ff"
            shutil.copy2(zone_out, staged_ff)
            staged_ff.replace(dist_ff)

        zone_out.unlink(missing_ok=True)
        return dist_ff
    finally:
        if prior_zone_csv is not None:
            zone_csv.write_bytes(prior_zone_csv)
        else:
            zone_csv.unlink(missing_ok=True)
        if prior_assetlist_csv is not None:
            assetlist_csv.write_bytes(prior_assetlist_csv)
        else:
            assetlist_csv.unlink(missing_ok=True)


def build_iwd(stage_dir: Path) -> Path:
    """Package staged maps/*.gsc into dist/waw_gauntlet/waw_gauntlet.iwd.

    In CoD:WaW 1.7, <map>.ff loads after mod.ff and takes precedence over mod.ff
    for rawfile (.gsc) assets that already exist inside the stock map fastfile.
    Shipping waw_gauntlet.iwd alongside mod.ff (matching Treyarch's Launcher)
    ensures stock map script overrides take precedence cleanly while mod.ff
    carries compiled fastfile assets (menus, localized strings, new scripts).
    """
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    dist_iwd = DIST_DIR / f"{MOD_NAME}.iwd"
    gsc_files = sorted((stage_dir / "maps").rglob("*.gsc"))
    if not gsc_files:
        raise RuntimeError(f"No staged GSC files found under {stage_dir / 'maps'}")

    with TemporaryDirectory(dir=DIST_DIR) as tmp:
        staged_iwd = Path(tmp) / dist_iwd.name
        with ZipFile(staged_iwd, "w") as archive:
            for gsc_path in gsc_files:
                rel = gsc_path.relative_to(stage_dir).as_posix()
                archive.writestr(ZipInfo(rel), gsc_path.read_bytes(), compress_type=ZIP_DEFLATED)
        staged_iwd.replace(dist_iwd)
    return dist_iwd


def deploy_mod(dist_dir: Path, appdata: Path) -> list[Path]:
    """Atomically deploy mod.ff and waw_gauntlet.iwd to <appdata>/mods/waw_gauntlet/."""
    if not appdata.is_dir():
        raise FileNotFoundError(f"World at War AppData folder is missing: {appdata}")

    mod_dir = appdata / "mods" / MOD_NAME
    mod_dir.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    for artifact_name in ("mod.ff", f"{MOD_NAME}.iwd"):
        src = dist_dir / artifact_name
        if not src.is_file():
            raise FileNotFoundError(f"Missing built mod artifact: {src}")
        dest = mod_dir / artifact_name
        with TemporaryDirectory(dir=mod_dir) as tmp:
            staged = Path(tmp) / artifact_name
            shutil.copyfile(src, staged)
            staged.replace(dest)
        installed.append(dest)
    return installed


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_and_optionally_deploy(
    tools_root: Path = DEFAULT_TOOLS_ROOT,
    steam_root: Path = DEFAULT_STEAM_ROOT,
    dev_root: Path = DEFAULT_DEV_ROOT,
    steam_game: Path = DEFAULT_STEAM_GAME,
    deploy_targets: list[Path] | None = None,
) -> tuple[list[Path], list[Path]]:
    stage_dir = stage_mod_files(tools_root=tools_root, steam_game=steam_game)
    dist_ff = run_linker(tools_root=tools_root, steam_root=steam_root, dev_root=dev_root)
    dist_iwd = build_iwd(stage_dir=stage_dir)
    artifacts = [dist_ff, dist_iwd]
    installed: list[Path] = []
    for target in deploy_targets or []:
        installed.extend(deploy_mod(DIST_DIR, target))
    return artifacts, installed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools-root", type=Path, default=DEFAULT_TOOLS_ROOT)
    parser.add_argument("--steam-root", type=Path, default=DEFAULT_STEAM_ROOT)
    parser.add_argument("--dev-root", type=Path, default=DEFAULT_DEV_ROOT)
    parser.add_argument("--steam-game", type=Path, default=DEFAULT_STEAM_GAME)
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Deploy compiled mod.ff and waw_gauntlet.iwd into the Steam/Proton WaW mods directory.",
    )
    parser.add_argument(
        "--appdata",
        type=Path,
        default=DEFAULT_STEAM_APPDATA,
        help="Target CoDWaW AppData directory for --deploy.",
    )
    args = parser.parse_args(argv)

    try:
        targets = [args.appdata] if args.deploy else []
        artifacts, installed = build_and_optionally_deploy(
            tools_root=args.tools_root,
            steam_root=args.steam_root,
            dev_root=args.dev_root,
            steam_game=args.steam_game,
            deploy_targets=targets,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for artifact in artifacts:
        size = artifact.stat().st_size
        digest = sha256_file(artifact)
        print(f"Built {artifact} ({size} bytes, sha256={digest[:16]})")
    for dest in installed:
        print(f"Deployed {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
