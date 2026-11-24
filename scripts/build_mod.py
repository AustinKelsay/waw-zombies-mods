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
BZ_BUILD_VERSION = "0.6.0"
BZ_BUILD_COMMIT_RE = re.compile(r"[0-9a-zA-Z_-]+")
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
BZ_PRE_HOOK_CALL = "if ( maps\\_bz_hooks::bz_enabled() ) { maps\\_bz_hooks::bz_pre_init(); }"
BZ_POST_HOOK_CALL = "if ( maps\\_bz_hooks::bz_enabled() ) { level thread maps\\_bz_hooks::bz_init(); }"

WEAPON_ARRAY_CAP_RE = re.compile(
    r"(?P<lhs>\b(?:primaries|primaryweapons|primary_weapons|weapons|weaponslist|weapon_list|current_weapons)\.size)[ \t]*>=[ \t]*2\b",
    re.IGNORECASE,
)
WEAPON_LIMIT_ASSIGN_RE = re.compile(
    r"(?P<lhs>\bweapon_limit[ \t]*=[ \t]*)2(?P<semi>[ \t]*;)",
    re.IGNORECASE,
)
GET_PRIMARIES_ENT_RE = re.compile(
    r"\b(?P<ent>[A-Za-z_][A-Za-z0-9_]*)[ \t]+GetWeaponsListPrimaries[ \t]*\([ \t]*\)",
    re.IGNORECASE,
)
CHEST_THINK_DEF_RE = re.compile(
    r"^treasure_chest_think\([ \t]*\)[ \t]*\r?\n\{",
    re.MULTILINE,
)
TOP_LEVEL_FUNC_DEF_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\([^)]*\)[ \t]*\r?\n\{",
    re.MULTILINE,
)
CHEST_SCORE_CHECK_RE = re.compile(
    r"(?P<ent>\b[A-Za-z_][A-Za-z0-9_]*)\.score[ \t]*(?P<op>>=|<)[ \t]*(?P<cost>self\.zombie_cost|cost)\b"
)
CHEST_SCORE_DEDUCT_RE = re.compile(
    r"(?P<ent>\b[A-Za-z_][A-Za-z0-9_]*)[ \t]+maps\\_zombiemode_score::minus_to_player_score\([ \t]*(?P<cost>self\.zombie_cost|cost)[ \t]*\)"
)
JUGG_HEALTH_BLOCK_RE = re.compile(
    r'^(?P<indent>[ \t]*)(?P<ent>[A-Za-z_][A-Za-z0-9_]*)\.maxhealth[ \t]*=[ \t]*(?:level\.zombie_vars\[[ \t]*"zombie_perk_juggernaut_health"[ \t]*\]|160);(?P<trailing>[ \t]*)\r?'
    r'(?:\r?\n[ \t]*(?P=ent)\.health[ \t]*=[^\n;]*;[ \t]*\r?)?',
    re.MULTILINE,
)
WEAPONS_FALLBACK_STRIP_RE = re.compile(
    r"if\([ \t]*IsDefined\([ \t]*primaryWeapons[ \t]*\)[ \t]*&&[ \t]*!isDefined\([ \t]*current_weapon[ \t]*\)[ \t]*\)",
    re.IGNORECASE,
)
WEAPONS_FALLBACK_TAKE_RE = re.compile(
    r"^(?P<indent>[ \t]*)self[ \t]+TakeWeapon\([ \t]*primaryWeapons\[i\][ \t]*\);(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE,
)
PERK_RESET_HEALTH_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<ent>[A-Za-z_][A-Za-z0-9_]*)\.maxhealth[ \t]*=[ \t]*100;(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE,
)
VENDING_UPGRADE_DEF_RE = re.compile(
    r"^vending_upgrade\([ \t]*\)[ \t]*\r?\n\{",
    re.MULTILINE,
)
PAP_FLAG_WAIT_RE = re.compile(
    r'^(?P<indent>[ \t]*)(?:flag_wait|level[ \t]+waittill)[ \t]*\([ \t]*"Pack_A_Punch_on"[ \t]*\);(?P<trailing>[ \t]*)\r?$',
    re.MULTILINE | re.IGNORECASE,
)
PAP_UPGRADE_GUARD_RE = re.compile(
    r'^(?P<indent>[ \t]*)if[ \t]*\([ \t]*!IsDefined[ \t]*\([ \t]*level\.zombie_include_weapons\[[ \t]*current_weapon[ \t]*\][ \t]*\)[ \t]*\|\|[ \t]*!IsDefined[ \t]*\([ \t]*level\.zombie_include_weapons\[[ \t]*current_weapon[ \t]*\+[ \t]*"_upgraded"[ \t]*\][ \t]*\)[ \t]*\)(?P<trailing>[ \t]*)\r?$',
    re.MULTILINE | re.IGNORECASE,
)
PAP_STOCK_BUSY_START_RE = re.compile(
    r"^(?P<indent>[ \t]*)self[ \t]+(?:disable_trigger\([ \t]*\)|SetHintString[ \t]*\([ \t]*&\"ZOMBIE_GET_UPGRADED\"[ \t]*\));(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE | re.IGNORECASE,
)
PAP_STOCK_BUSY_END_RE = re.compile(
    r"^(?P<indent>[ \t]*)self[ \t]+(?:setvisibletoall\([ \t]*\)|enable_trigger\([ \t]*\));(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE | re.IGNORECASE,
)
WAIT_FOR_PLAYER_TAKE_DEF_RE = re.compile(
    r"^wait_for_player_to_take\([^)]*\)[ \t]*\r?\n\{",
    re.MULTILINE,
)
PAP_TAKE_GIVE_MAX_AMMO_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<ent>[A-Za-z_][A-Za-z0-9_]*)[ \t]+GiveMaxAmmo[ \t]*\([ \t]*(?P<weap>[^,)]+?)[ \t]*\);(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE | re.IGNORECASE,
)
PAP_TAKE_GIVE_WEAPON_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<ent>[A-Za-z_][A-Za-z0-9_]*)[ \t]+GiveWeapon[ \t]*\([ \t]*(?P<weap>[^,)]+?)(?:[ \t]*,[^)]*)?\);(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE | re.IGNORECASE,
)
PAP_TAKE_WEAPON_GIVE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<ent>[A-Za-z_][A-Za-z0-9_]*)[ \t]+maps\\_zombiemode_weapons::weapon_give[ \t]*\([ \t]*(?P<weap>[^,)]+?)(?:[ \t]*,[^)]*)?\);(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE | re.IGNORECASE,
)
DOG_HIDE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<ent>[A-Za-z_][A-Za-z0-9_]*)[ \t]+hide\([ \t]*\);(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE | re.IGNORECASE,
)
DOG_STOP_SHIELD_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<ent>[A-Za-z_][A-Za-z0-9_]*)[ \t]+(?:thread[ \t]+)?stop_magic_bullet_shield\([ \t]*\);(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE | re.IGNORECASE,
)
DOG_SHOW_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<ent>[A-Za-z_][A-Za-z0-9_]*)[ \t]+show\([ \t]*\);(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE | re.IGNORECASE,
)
ADD_PLAYER_SCORE_DEF_RE = re.compile(
    r"^add_to_player_score\([ \t]*(?P<param>[A-Za-z_][A-Za-z0-9_]*)[ \t]*\)[ \t]*\r?\n\{",
    re.MULTILINE,
)
PLAYER_ADD_POINTS_SCORE_RE = re.compile(
    r"^(?P<indent>[ \t]*)self\.score[ \t]*\+=[ \t]*points;(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE,
)
SCORE_INSTA_KILL_RE = re.compile(
    r'if\([ \t]*level\.zombie_vars\["zombie_powerup_insta_kill_on"\][ \t]*==[ \t]*1[ \t]*&&[ \t]*mod[ \t]*==[ \t]*"MOD_UNKNOWN"[ \t]*\)'
)
SCORE_DLC3_ACHIEVEMENT_RE = re.compile(
    r'^[ \t]*self[ \t]+achievement_notify\([^\n]*\);[ \t]*\r?$',
    re.MULTILINE,
)
WALL_WEAPON_GIVE_RE = re.compile(
    r"^(?P<indent>[ \t]*)player[ \t]+weapon_give\([ \t]*self\.zombie_weapon_upgrade[ \t]*\);(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE,
)
WALL_AMMO_GIVEN_RE = re.compile(
    r"^(?P<indent>[ \t]*)if\([ \t]*ammo_given[ \t]*\)[ \t]*\r?\n(?P=indent)\{",
    re.MULTILINE,
)
LASTSTAND_REVIVE_TIME_RE = re.compile(
    r"^(?P<indent>[ \t]*)reviveTime[ \t]*=[ \t]*3;[ \t]*\r?"
    r'(?:(?:\r?\n[ \t]*)*if[ \t]*\([ \t]*self[ \t]+HasPerk\([ \t]*"specialty_quickrevive"[ \t]*\)[ \t]*\)[ \t]*\r?\n[ \t]*\{[ \t]*\r?\n[ \t]*reviveTime[ \t]*=[ \t]*reviveTime[ \t]*/[ \t]*2;[ \t]*\r?\n[ \t]*\}[ \t]*\r?)?',
    re.MULTILINE,
)
LASTSTAND_REVIVE_SUCCESS_RE = re.compile(
    r"^(?P<indent>[ \t]*)self[ \t]+reviveplayer\([ \t]*\);(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE,
)
LASTSTAND_ALL_DOWN_RE = re.compile(
    r"^(?P<indent>[ \t]*)if[ \t]*\([ \t]*player_all_players_in_laststand\([ \t]*\)[ \t]*\)",
    re.MULTILINE,
)
TESLA_PVP_THREAD_DEF_RE = re.compile(
    r"^tesla_pvp_thread\([ \t]*\)[ \t]*\r?\n\{",
    re.MULTILINE,
)
TESLA_SELF_DAMAGE_BLOCK_RE = re.compile(
    r"^(?P<indent>[ \t]*)if[ \t]*\([ \t]*self\.health[ \t]*-[ \t]*damage[ \t]*<[ \t]*1[ \t]*\)[ \t]*\r?\n"
    r"[ \t]*\{[ \t]*\r?\n"
    r"[ \t]*self\.health[ \t]*=[ \t]*1;[ \t]*\r?\n"
    r"[ \t]*\}[ \t]*\r?\n"
    r"[ \t]*else[ \t]*\r?\n"
    r"[ \t]*\{[ \t]*\r?\n"
    r"[ \t]*self\.health[ \t]*-=[ \t]*damage;[ \t]*\r?\n"
    r"[ \t]*\}(?P<trailing>[ \t]*)\r?$",
    re.MULTILINE,
)
TESLA_CHAIN_FN_CANDIDATES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^tesla_arc_damage\((?P<params>[^)]*)\)[ \t]*\r?\n\{", re.MULTILINE),
    re.compile(r"^tesla_do_damage\((?P<params>[^)]*)\)[ \t]*\r?\n\{", re.MULTILINE),
    re.compile(r"^tesla_damage_init\((?P<params>[^)]*)\)[ \t]*\r?\n\{", re.MULTILINE),
)

# Verified subset of the 89 FX paths present in ALL FOUR stock Nazi Zombies map fastfiles
# (nazi_zombie_prototype, nazi_zombie_asylum, nazi_zombie_sumpf, nazi_zombie_factory)
# per docs/research/phase2-phase3-engine-feasibility.md — guaranteed 0 added FX slots.
VERIFIED_ALL_4_MAP_FX: frozenset[str] = frozenset(
    {
        "misc/fx_exp_raygun_impact",
        "misc/fx_trail_raygun_geotrail",
        "misc/fx_zombie_powerup_on",
        "misc/fx_zombie_powerup_wave",
        "misc/fx_zombie_powerup_grab",
        "misc/fx_zombie_mini_nuke",
        "misc/fx_zombie_bloodsplat",
        "misc/fx_zombie_bloodspurt",
        "env/smoke/fx_fog_zombie_amb",
        "env/electrical/fx_elec_short_oneshot",
        "env/electrical/fx_elec_wire_spark_burst",
        "env/dirt/fx_dust_ceiling_impact_lg_mdbrown",
        "bio/player/fx_footstep_water",
        "bio/player/fx_footstep_sand",
        "weapon/grenade/fx_trail_rifle_grenade",
        "weapon/rocket/fx_trail_panzerfaust_geotrail",
        "weapon/molotov/fx_molotov_exp",
    }
)

# Canonical Phase 2 zero-FX cloned primary weapon definitions (ADR-0003).
# Each weapon clones a verified stock template at build time, enforces inventoryType=primary
# and a distinct ammoName/clipName pool, and clears any FX outside VERIFIED_ALL_4_MAP_FX.
BZ_ELEMENT_WEAPON_SPECS: tuple[tuple[str, tuple[str, ...], dict[str, str]], ...] = (
    (
        "bz_acid_sprayer",
        ("m2_flamethrower_zombie", "ray_gun"),
        {
            "displayName": "Acid Sprayer",
            "inventoryType": "primary",
            "weaponType": "bullet",
            "weaponClass": "rifle",
            "fireType": "Single Shot",
            "ammoName": "bz_acid",
            "clipName": "bz_acid",
            "clipSize": "20",
            "maxAmmo": "120",
            "startAmmo": "120",
            "dropAmmoMin": "20",
            "dropAmmoMax": "60",
            "fireTime": "0.45",
            "reloadTime": "1.2",
            "reloadEmptyTime": "1.2",
            "emptyIdleAnim": "viewmodel_flamethrower_idle",
            "reloadAnim": "viewmodel_flamethrower_reload",
            "reloadEmptyAnim": "viewmodel_flamethrower_reload",
            "damage": "1",
            "minDamage": "1",
            "explosionInnerDamage": "0",
            "explosionOuterDamage": "0",
            "explosionRadius": "0",
            "altWeapon": "",
            "aimDownSight": "0",
            "adsFire": "0",
            "adsUpAnim": "",
            "adsDownAnim": "",
            "adsFireAnim": "",
            "adsLastShotAnim": "",
            "adsRechamberAnim": "",
            "fireSound": "weap_raygun_fire",
            "fireSoundPlayer": "weap_raygun_fire_plr",
        },
    ),
    (
        "bz_cryo_cannon",
        ("tesla_gun", "ray_gun"),
        {
            "displayName": "Cryo Cannon",
            "inventoryType": "primary",
            "weaponType": "bullet",
            "ammoName": "bz_cryo",
            "clipName": "bz_cryo",
            "clipSize": "16",
            "maxAmmo": "96",
            "startAmmo": "96",
            "dropAmmoMin": "16",
            "dropAmmoMax": "48",
            "fireTime": "0.55",
            "damage": "1",
            "minDamage": "1",
            "explosionInnerDamage": "0",
            "explosionOuterDamage": "0",
            "explosionRadius": "0",
            "altWeapon": "",
        },
    ),
    (
        "bz_multi_crossbow",
        ("m7_launcher_zombie", "fg42_scoped", "m1garand_gl", "zombie_m1garand", "kar98k"),
        {
            "displayName": "Multi-Crossbow",
            "inventoryType": "primary",
            "weaponType": "bullet",
            "fireType": "Single Shot",
            "ammoName": "bz_xbow",
            "clipName": "bz_xbow",
            "clipSize": "6",
            "maxAmmo": "36",
            "startAmmo": "36",
            "dropAmmoMin": "6",
            "dropAmmoMax": "18",
            "fireTime": "0.60",
            "damage": "1",
            "minDamage": "1",
            "explosionInnerDamage": "0",
            "explosionOuterDamage": "0",
            "explosionRadius": "0",
            "altWeapon": "",
        },
    ),
    (
        "bz_blade_boomerang",
        ("zombie_doublebarrel_sawed", "walther", "zombie_colt", "colt"),
        {
            "displayName": "Blade Boomerang",
            "inventoryType": "primary",
            "weaponType": "bullet",
            "weaponClass": "pistol",
            "shotCount": "1",
            "fireType": "Single Shot",
            "ammoName": "bz_blade",
            "clipName": "bz_blade",
            "clipSize": "1",
            "maxAmmo": "20",
            "startAmmo": "20",
            "dropAmmoMin": "1",
            "dropAmmoMax": "10",
            "fireTime": "0.65",
            "reloadTime": "0.45",
            "reloadEmptyTime": "0.45",
            "damage": "1",
            "minDamage": "1",
            "explosionInnerDamage": "0",
            "explosionOuterDamage": "0",
            "explosionRadius": "0",
            "altWeapon": "",
            "aimDownSight": "0",
            "adsFire": "0",
            "fireSound": "melee_swing_plr",
            "fireSoundPlayer": "melee_swing_plr",
        },
    ),
)


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


def zombiemode_weapons_module_for_map(map_name: str) -> str:
    """Return the per-map hooked _zombiemode_weapons script stem (without .gsc)."""
    slug = STOCK_MAP_SLUGS.get(map_name)
    if slug is None:
        raise ValueError(f"Unsupported stock Nazi Zombies map: {map_name!r}")
    return f"_zombiemode_weapons_bz_{slug}"


def zombiemode_perks_module_for_map(map_name: str) -> str:
    """Return the per-map hooked _zombiemode_perks script stem (without .gsc)."""
    slug = STOCK_MAP_SLUGS.get(map_name)
    if slug is None:
        raise ValueError(f"Unsupported stock Nazi Zombies map: {map_name!r}")
    return f"_zombiemode_perks_bz_{slug}"


def zombiemode_dogs_module_for_map(map_name: str) -> str:
    """Return the per-map hooked _zombiemode_dogs script stem (without .gsc)."""
    slug = STOCK_MAP_SLUGS.get(map_name)
    if slug is None:
        raise ValueError(f"Unsupported stock Nazi Zombies map: {map_name!r}")
    return f"_zombiemode_dogs_bz_{slug}"


def zombiemode_powerups_module_for_map(map_name: str) -> str:
    """Return the per-map hooked _zombiemode_powerups script stem (without .gsc)."""
    slug = STOCK_MAP_SLUGS.get(map_name)
    if slug is None:
        raise ValueError(f"Unsupported stock Nazi Zombies map: {map_name!r}")
    return f"_zombiemode_powerups_bz_{slug}"


def extract_stock_script(
    map_name: str, rawfile_rel: str, steam_game: Path, tools_root: Path
) -> bytes:
    """Extract an era-specific stock rawfile script, preferring <map>_patch.ff."""
    ff_patch = resolve_stock_ff(map_name, steam_game, tools_root, prefer_patch=True)
    try:
        return extract_rawfile_from_ff(ff_patch, rawfile_rel)
    except ValueError:
        ff_base = resolve_stock_ff(map_name, steam_game, tools_root, prefer_patch=False)
        if ff_base == ff_patch:
            raise
        return extract_rawfile_from_ff(ff_base, rawfile_rel)


def try_extract_stock_script(
    map_name: str, rawfile_rel: str, steam_game: Path, tools_root: Path
) -> bytes | None:
    """Extract an era-specific stock script or return None if absent on that map."""
    try:
        return extract_stock_script(map_name, rawfile_rel, steam_game, tools_root)
    except ValueError:
        return None


def extract_stock_zombiemode(map_name: str, steam_game: Path, tools_root: Path) -> bytes:
    """Extract era-specific stock maps/_zombiemode.gsc, preferring <map>_patch.ff."""
    return extract_stock_script(map_name, "maps/_zombiemode.gsc", steam_game, tools_root)


def _rewire_stock_module_refs(
    text: str,
    rewire_weapons_module: str | None = None,
    rewire_perks_module: str | None = None,
    rewire_dogs_module: str | None = None,
    rewire_powerups_module: str | None = None,
) -> str:
    if rewire_weapons_module:
        text = text.replace("maps\\_zombiemode_weapons::", f"maps\\{rewire_weapons_module}::")
    if rewire_perks_module:
        text = text.replace("maps\\_zombiemode_perks::", f"maps\\{rewire_perks_module}::")
    if rewire_dogs_module:
        text = text.replace("maps\\_zombiemode_dogs::", f"maps\\{rewire_dogs_module}::")
    if rewire_powerups_module:
        text = text.replace("maps\\_zombiemode_powerups::", f"maps\\{rewire_powerups_module}::")
    return text


def inject_map_hooks(
    script_bytes: bytes,
    map_name: str,
    *,
    rewire_weapons_module: str | None = None,
    rewire_perks_module: str | None = None,
    rewire_dogs_module: str | None = None,
    rewire_powerups_module: str | None = None,
) -> bytes:
    """Inject Gauntlet + guarded Base Zombies bootstrap hooks and rewire maps\\_zombiemode::main(...)."""
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
    coop_dog_hook = ""
    if map_name == "nazi_zombie_factory" and rewire_dogs_module:
        # Keep the factory-only stock script dependency out of the shared BZ hooks.
        coop_dog_hook = (
            f'{indent}if ( maps\\_bz_hooks::bz_enabled() && GetDvarInt( "bz_test_coop_selftest" ) == 1 ) '
            f"{{ level.bz_test_coop_spawn_dog = maps\\{rewire_dogs_module}::special_dog_spawn; }}{newline}"
        )
    replacement = (
        f"{indent}{PRE_HOOK_CALL}{newline}"
        f"{indent}{BZ_PRE_HOOK_CALL}{newline}"
        f"{coop_dog_hook}"
        f"{rewired_line}{newline}"
        f"{indent}{POST_HOOK_CALL}{newline}"
        f"{indent}{BZ_POST_HOOK_CALL}{line_ending}"
    )
    patched = text[: match.start()] + replacement + text[match.end() :]
    patched = _rewire_stock_module_refs(
        patched,
        rewire_weapons_module=rewire_weapons_module,
        rewire_perks_module=rewire_perks_module,
        rewire_dogs_module=rewire_dogs_module,
        rewire_powerups_module=rewire_powerups_module,
    )
    return patched.encode("latin1")


def inject_zombiemode_hooks(
    script_bytes: bytes,
    map_name: str,
    *,
    rewire_weapons_module: str | None = None,
    rewire_perks_module: str | None = None,
    rewire_dogs_module: str | None = None,
    rewire_powerups_module: str | None = None,
) -> bytes:
    """Inject strictly gated Gauntlet & Base Zombies hooks into a stock map's maps/_zombiemode.gsc.

    Hooks injected:
      1. round_start(): before `level thread round_think();`
         - Gauntlet: on_stage_init() (guarded by is_gauntlet_enabled())
         - Base Zombies: bz_init() (guarded by bz_enabled())
      2. round_think(): around `round_wait();`
         - Gauntlet: on_round_started / on_round_completed
         - Base Zombies: bz_on_round_start(level.round_number) (guarded by bz_enabled())
      3. end_game(): after `level.intermission = true;`
         - Base Zombies: bz_on_end_game() (guarded by bz_enabled())
         - Gauntlet: if (on_end_game()) return; (guarded by is_gauntlet_enabled())

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
        f"{rt_indent}if ( maps\\_bz_hooks::bz_enabled() ){newline}"
        f"{rt_indent}{{{newline}"
        f"{rt_indent}\tmaps\\_bz_hooks::bz_init();{newline}"
        f"{rt_indent}}}{newline}"
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
        f"{rw_indent}if ( maps\\_bz_hooks::bz_enabled() ){newline}"
        f"{rw_indent}{{{newline}"
        f"{rw_indent}\tlevel thread maps\\_bz_hooks::bz_on_round_start( level.round_number );{newline}"
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
        f"{eg_indent}if ( maps\\_bz_hooks::bz_enabled() ){newline}"
        f"{eg_indent}{{{newline}"
        f"{eg_indent}\tmaps\\_bz_hooks::bz_on_end_game();{newline}"
        f"{eg_indent}}}{newline}"
        f"{eg_indent}if ( maps\\_gauntlet_mode::is_gauntlet_enabled() ){newline}"
        f"{eg_indent}{{{newline}"
        f"{eg_indent}\tif ( maps\\_gauntlet_mode::on_end_game() ){newline}"
        f"{eg_indent}\t{{{newline}"
        f"{eg_indent}\t\treturn;{newline}"
        f"{eg_indent}\t}}{newline}"
        f"{eg_indent}}}{eg_ending}"
    )
    text = text[: inter_match.start()] + eg_hook + text[inter_match.end() :]

    text = _rewire_stock_module_refs(
        text,
        rewire_weapons_module=rewire_weapons_module,
        rewire_perks_module=rewire_perks_module,
        rewire_dogs_module=rewire_dogs_module,
        rewire_powerups_module=rewire_powerups_module,
    )
    return text.encode("latin1")


def _infer_player_entity_before(text: str, pos: int) -> str:
    """Find the player variable calling GetWeaponsListPrimaries() nearest before pos."""
    window_start = max(0, pos - 600)
    window = text[window_start:pos]
    # Stop at the nearest function opening brace if any top-level function boundary exists
    last_fn = window.rfind("\n{")
    if last_fn != -1:
        window = window[last_fn:]
    matches = list(GET_PRIMARIES_ENT_RE.finditer(window))
    if matches:
        return matches[-1].group("ent")
    return "self"


def _replace_weapon_cap_checks(text: str) -> tuple[str, int]:
    """Replace hardcoded 2-weapon primary slot caps with bz_get_max_primary_weapons(<ent>)."""
    total = 0

    def _sub_limit(match: re.Match[str]) -> str:
        nonlocal total
        total += 1
        ent = _infer_player_entity_before(text, match.start())
        return f"{match.group('lhs')}maps\\_bz_hooks::bz_get_max_primary_weapons( {ent} ){match.group('semi')}"

    text = WEAPON_LIMIT_ASSIGN_RE.sub(_sub_limit, text)

    def _sub_arr(match: re.Match[str]) -> str:
        nonlocal total
        total += 1
        ent = _infer_player_entity_before(text, match.start())
        return f"{match.group('lhs')} >= maps\\_bz_hooks::bz_get_max_primary_weapons( {ent} )"

    text = WEAPON_ARRAY_CAP_RE.sub(_sub_arr, text)
    return text, total


def inject_zombiemode_weapons_hooks(script_bytes: bytes) -> bytes:
    """Patch stock _zombiemode_weapons.gsc with dynamic weapon caps, Mystery Box cost, and wall-buy hooks."""
    text = script_bytes.decode("latin1")
    newline = "\r\n" if "\r\n" in text else "\n"
    text, cap_count = _replace_weapon_cap_checks(text)
    if cap_count == 0:
        raise ValueError(
            "Expected at least 1 primary weapon cap check (>= 2 or weapon_limit = 2) "
            "in _zombiemode_weapons.gsc"
        )

    # Stock WaW 1.7 treasure_chest_give_weapon() (all 4 maps) and weapon_give()
    # (Nacht/Verruckt/Shi No Numa) have a fallback loop:
    #   if( IsDefined( primaryWeapons ) && !isDefined( current_weapon ) )
    #       for(...) if( primaryWeapons[i] != "zombie_colt" ) self TakeWeapon( primaryWeapons[i] );
    # When Mule Kick raises the weapon cap to 3 or 4 and the player holds 2+ non-Colt guns,
    # primaryWeapons.size >= max_weapons is false, leaving current_weapon == undefined and
    # causing that fallback loop to WIPE every non-Colt gun in the player's inventory!
    # Gate the fallback on actually being at/over the dynamic weapon cap, and break after
    # taking one weapon when bz_enabled() so holding a Bouncing Betty at full slots never
    # wipes the entire loadout either.
    text = WEAPONS_FALLBACK_STRIP_RE.sub(
        "if( IsDefined( primaryWeapons ) && !isDefined( current_weapon ) && ( !maps\\_bz_hooks::bz_enabled() || primaryWeapons.size >= maps\\_bz_hooks::bz_get_max_primary_weapons( self ) ) )",
        text,
    )

    def _inject_fallback_take_break(match: re.Match[str]) -> str:
        indent = match.group("indent")
        orig = match.group(0).rstrip("\r")
        ending = "\r" if match.group(0).endswith("\r") else ""
        return (
            f"{orig}{newline}"
            f"{indent}if ( maps\\_bz_hooks::bz_enabled() ) {{ break; }}{ending}"
        )

    text = WEAPONS_FALLBACK_TAKE_RE.sub(_inject_fallback_take_break, text)

    # Route Mystery Box cost checks and deductions strictly inside treasure_chest_think()
    # through bz_box_cost_modify (noop when bz_enabled=0). Supports both Nacht's direct
    # `self.zombie_cost` and Verruckt/Shi No Numa/Der Riese's local `cost` variable without
    # accidentally discounting wall buys / weapon cabinets in weapon_spawn_think().
    chest_match = CHEST_THINK_DEF_RE.search(text)
    if chest_match is not None:
        next_fn = TOP_LEVEL_FUNC_DEF_RE.search(text, pos=chest_match.end())
        chest_end = next_fn.start() if next_fn is not None else len(text)
        chest_body = text[chest_match.start() : chest_end]
        chest_body = CHEST_SCORE_CHECK_RE.sub(
            lambda m: (
                f"{m.group('ent')}.score {m.group('op')} "
                f"maps\\_bz_hooks::bz_box_cost_modify( {m.group('ent')}, {m.group('cost')} )"
            ),
            chest_body,
        )
        chest_body = CHEST_SCORE_DEDUCT_RE.sub(
            lambda m: (
                f"{m.group('ent')} maps\\_zombiemode_score::minus_to_player_score( "
                f"maps\\_bz_hooks::bz_box_cost_modify( {m.group('ent')}, {m.group('cost')} ) )"
            ),
            chest_body,
        )
        text = text[: chest_match.start()] + chest_body + text[chest_end:]

    # Inject guarded wall-buy weapon purchase hook (Sapper Wall-Buy Traps)
    def _inject_wall_weapon(match: re.Match[str]) -> str:
        indent = match.group("indent")
        orig = match.group(0).rstrip("\r")
        ending = "\r" if match.group(0).endswith("\r") else ""
        return (
            f"{orig}{newline}"
            f"{indent}if ( maps\\_bz_hooks::bz_enabled() ) "
            f"{{ maps\\_bz_hooks::bz_on_wall_buy( player, self.zombie_weapon_upgrade, self.origin, false ); }}{ending}"
        )

    text = WALL_WEAPON_GIVE_RE.sub(_inject_wall_weapon, text)

    # Inject guarded wall-buy ammo purchase hook (Double Ammo 2x refill + Sapper Wall-Buy Traps)
    def _inject_wall_ammo(match: re.Match[str]) -> str:
        indent = match.group("indent")
        orig = match.group(0)
        return (
            f"{orig}{newline}"
            f"{indent}\tif ( maps\\_bz_hooks::bz_enabled() ) "
            f"{{ maps\\_bz_hooks::bz_on_wall_buy( player, self.zombie_weapon_upgrade, self.origin, true ); }}"
        )

    text = WALL_AMMO_GIVEN_RE.sub(_inject_wall_ammo, text)
    return text.encode("latin1")


def inject_zombiemode_perks_hooks(
    script_bytes: bytes,
    *,
    rewire_weapons_module: str | None = None,
) -> bytes:
    """Patch stock _zombiemode_perks.gsc with dynamic weapon cap and unified maxhealth recompute."""
    text = script_bytes.decode("latin1")
    newline = "\r\n" if "\r\n" in text else "\n"

    text, cap_count = _replace_weapon_cap_checks(text)
    health_hooks = 0

    # Inject guarded bz_recompute_player_max_health right after stock Juggernog health assignment
    def _inject_after_jugg(match: re.Match[str]) -> str:
        nonlocal health_hooks
        health_hooks += 1
        indent = match.group("indent")
        ent = match.group("ent")
        orig = match.group(0).rstrip("\r")
        ending = "\r" if match.group(0).endswith("\r") else ""
        return (
            f"{orig}{newline}"
            f"{indent}if ( maps\\_bz_hooks::bz_enabled() ){newline}"
            f"{indent}{{{newline}"
            f"{indent}\tmaps\\_bz_hooks::bz_recompute_player_max_health( {ent} );{newline}"
            f"{indent}}}{ending}"
        )

    text = JUGG_HEALTH_BLOCK_RE.sub(_inject_after_jugg, text)

    # Inject guarded bz_recompute_player_max_health right after stock perk loss reset (maxhealth = 100)
    def _inject_after_reset(match: re.Match[str]) -> str:
        nonlocal health_hooks
        health_hooks += 1
        indent = match.group("indent")
        ent = match.group("ent")
        orig = match.group(0).rstrip("\r")
        ending = "\r" if match.group(0).endswith("\r") else ""
        return (
            f"{orig}{newline}"
            f"{indent}if ( maps\\_bz_hooks::bz_enabled() ){newline}"
            f"{indent}{{{newline}"
            f"{indent}\tmaps\\_bz_hooks::bz_recompute_player_max_health( {ent} );{newline}"
            f"{indent}}}{ending}"
        )

    text = PERK_RESET_HEALTH_RE.sub(_inject_after_reset, text)

    if cap_count == 0 and health_hooks == 0:
        raise ValueError(
            "Expected at least 1 weapon-cap or maxhealth hook site in _zombiemode_perks.gsc"
        )

    # Der Riese native Pack-a-Punch console hooks (only when vending_upgrade() exists,
    # so Verruckt & Shi No Numa _zombiemode_perks.gsc patch cleanly without error).
    vu_match = VENDING_UPGRADE_DEF_RE.search(text)
    if vu_match is not None:
        next_fn = TOP_LEVEL_FUNC_DEF_RE.search(text, pos=vu_match.end())
        vu_end = next_fn.start() if next_fn is not None else len(text)
        vu_body = text[vu_match.start() : vu_end]

        def _inject_after_pap_flag(match: re.Match[str]) -> str:
            indent = match.group("indent")
            orig = match.group(0).rstrip("\r")
            ending = "\r" if match.group(0).endswith("\r") else ""
            return (
                f"{orig}{newline}"
                f"{indent}if ( maps\\_bz_hooks::bz_pap_enabled() ) "
                f"{{ level.bz_native_pap_unlocked = true; level.bz_native_pap_unlock_hook_fired = true; }}{ending}"
            )

        vu_body = PAP_FLAG_WAIT_RE.sub(_inject_after_pap_flag, vu_body, count=1)

        def _inject_before_pap_guard(match: re.Match[str]) -> str:
            indent = match.group("indent")
            orig = match.group(0)
            return (
                f"{indent}if ( maps\\_bz_hooks::bz_pap_enabled() && "
                f"maps\\_bz_pap::bz_pap_try_native_console_upgrade( self, player, current_weapon, perk_machine, packa_rollers ) ){newline}"
                f"{indent}{{{newline}"
                f"{indent}\tcontinue;{newline}"
                f"{indent}}}{newline}"
                f"{orig}"
            )

        vu_body, guard_hits = PAP_UPGRADE_GUARD_RE.subn(_inject_before_pap_guard, vu_body, count=1)
        if guard_hits != 1:
            raise ValueError(
                "Could not locate zombie_include_weapons upgrade guard inside vending_upgrade() "
                "in _zombiemode_perks.gsc"
            )

        def _inject_busy_start(match: re.Match[str]) -> str:
            indent = match.group("indent")
            orig = match.group(0).rstrip("\r")
            ending = "\r" if match.group(0).endswith("\r") else ""
            return (
                f"{orig}{newline}"
                f"{indent}if ( maps\\_bz_hooks::bz_pap_enabled() ) "
                f"{{ self.bz_pap_stock_busy = true; }}{ending}"
            )

        def _inject_busy_end(match: re.Match[str]) -> str:
            indent = match.group("indent")
            orig = match.group(0).rstrip("\r")
            ending = "\r" if match.group(0).endswith("\r") else ""
            return (
                f"{orig}{newline}"
                f"{indent}if ( maps\\_bz_hooks::bz_pap_enabled() ) "
                f"{{ self.bz_pap_stock_busy = false; }}{ending}"
            )

        vu_body = PAP_STOCK_BUSY_START_RE.sub(_inject_busy_start, vu_body)
        vu_body = PAP_STOCK_BUSY_END_RE.sub(_inject_busy_end, vu_body)
        text = text[: vu_match.start()] + vu_body + text[vu_end:]

        # Hook wait_for_player_to_take() across ALL pickup branches (weapon_give at cap AND
        # GiveMaxAmmo/GiveWeapon below cap) so picking up a native *_upgraded weapon refreshes
        # reserve ammo & HUD regardless of current primary weapon count.
        take_match = WAIT_FOR_PLAYER_TAKE_DEF_RE.search(text)
        if take_match is not None:
            next_take_fn = TOP_LEVEL_FUNC_DEF_RE.search(text, pos=take_match.end())
            take_end = next_take_fn.start() if next_take_fn is not None else len(text)
            take_body = text[take_match.start() : take_end]

            def _inject_after_take(match: re.Match[str]) -> str:
                indent = match.group("indent")
                ent = match.group("ent")
                weap = match.group("weap").strip()
                orig = match.group(0).rstrip("\r")
                ending = "\r" if match.group(0).endswith("\r") else ""
                return (
                    f"{orig}{newline}"
                    f"{indent}if ( maps\\_bz_hooks::bz_pap_enabled() ) "
                    f"{{ maps\\_bz_pap::bz_pap_on_native_weapon_taken( {ent}, {weap} ); }}{ending}"
                )

            take_body, wg_hits = PAP_TAKE_WEAPON_GIVE_RE.subn(_inject_after_take, take_body)
            take_body, gma_hits = PAP_TAKE_GIVE_MAX_AMMO_RE.subn(_inject_after_take, take_body)
            gw_hits = 0
            if gma_hits == 0:
                take_body, gw_hits = PAP_TAKE_GIVE_WEAPON_RE.subn(_inject_after_take, take_body)
            take_hits = wg_hits + gma_hits + gw_hits
            if take_hits == 0:
                raise ValueError(
                    "Could not locate GiveMaxAmmo/GiveWeapon/weapon_give inside "
                    "wait_for_player_to_take() in _zombiemode_perks.gsc"
                )
            text = text[: take_match.start()] + take_body + text[take_end:]

    text = _rewire_stock_module_refs(
        text,
        rewire_weapons_module=rewire_weapons_module,
    )
    return text.encode("latin1")


def inject_zombiemode_dogs_hooks(
    script_bytes: bytes,
    *,
    rewire_weapons_module: str | None = None,
    rewire_powerups_module: str | None = None,
) -> bytes:
    """Patch stock maps/_zombiemode_dogs.gsc to keep bz_spawning_dog set through Show().

    Stock dog_spawn_fx() clears ignoreall and calls stop_magic_bullet_shield(), then waits
    100 ms before calling show(). Setting bz_spawning_dog=true on hide() and right before
    stop_magic_bullet_shield() and clearing it right after show() guarantees Base Zombies
    combat/CC effects never hit a still-hidden Hellhound during that 100 ms window.
    """
    text = script_bytes.decode("latin1")
    newline = "\r\n" if "\r\n" in text else "\n"

    def _inject_after_hide(match: re.Match[str]) -> str:
        indent = match.group("indent")
        ent = match.group("ent")
        orig = match.group(0).rstrip("\r")
        ending = "\r" if match.group(0).endswith("\r") else ""
        return (
            f"{orig}{newline}"
            f"{indent}if ( maps\\_bz_hooks::bz_enabled() ) {{ {ent}.bz_spawning_dog = true; }}{ending}"
        )

    def _inject_before_stop_shield(match: re.Match[str]) -> str:
        indent = match.group("indent")
        ent = match.group("ent")
        orig = match.group(0)
        return (
            f"{indent}if ( maps\\_bz_hooks::bz_enabled() ) {{ {ent}.bz_spawning_dog = true; }}{newline}"
            f"{orig}"
        )

    def _inject_after_show(match: re.Match[str]) -> str:
        indent = match.group("indent")
        ent = match.group("ent")
        orig = match.group(0).rstrip("\r")
        ending = "\r" if match.group(0).endswith("\r") else ""
        return (
            f"{orig}{newline}"
            f"{indent}if ( maps\\_bz_hooks::bz_enabled() ) {{ {ent}.bz_spawning_dog = false; }}{ending}"
        )

    text, _hide_hits = DOG_HIDE_RE.subn(_inject_after_hide, text)
    text, stop_hits = DOG_STOP_SHIELD_RE.subn(_inject_before_stop_shield, text)
    text, show_hits = DOG_SHOW_RE.subn(_inject_after_show, text)
    if stop_hits == 0 or show_hits == 0:
        raise ValueError(
            f"Could not locate stop_magic_bullet_shield()/show() spawn markers in _zombiemode_dogs.gsc "
            f"(stop_hits={stop_hits}, show_hits={show_hits})"
        )
    text = _rewire_stock_module_refs(
        text,
        rewire_weapons_module=rewire_weapons_module,
        rewire_powerups_module=rewire_powerups_module,
    )
    return text.encode("latin1")


def inject_zombiemode_score_hooks(script_bytes: bytes) -> bytes:
    """Patch stock _zombiemode_score.gsc with guarded bz_points_modify on all point awards."""
    text = script_bytes.decode("latin1")
    newline = "\r\n" if "\r\n" in text else "\n"

    # Guard DLC3-only zombie_powerup_insta_kill_on and omit DLC3-only achievement_notify
    # so the unified _zombiemode_score.gsc compiles and runs cleanly across all 4 stock maps.
    text = SCORE_INSTA_KILL_RE.sub(
        'if( IsDefined( level.zombie_vars["zombie_powerup_insta_kill_on"] ) && level.zombie_vars["zombie_powerup_insta_kill_on"] == 1 && mod == "MOD_UNKNOWN" )',
        text,
    )
    text = SCORE_DLC3_ACHIEVEMENT_RE.sub(
        "\t\t\t\t// DLC3 achievement_notify omitted for 4-map stock parity",
        text,
    )

    # 1. Hook add_to_player_score( cost ) for repair/carpenter/revive/scripted point awards
    match = ADD_PLAYER_SCORE_DEF_RE.search(text)
    if match is None:
        raise ValueError("Could not locate add_to_player_score( points ) in _zombiemode_score.gsc")
    param = match.group("param")
    hook = (
        f"{newline}"
        f"\tif ( maps\\_bz_hooks::bz_enabled() ){newline}"
        f"\t{{{newline}"
        f'\t\t{param} = maps\\_bz_hooks::bz_points_modify( self, {param}, "score" );{newline}'
        f"\t}}"
    )
    text = text[: match.end()] + hook + text[match.end() :]

    # 2. Hook player_add_points() right before `self.score += points;` for hit & kill awards
    def _inject_player_add_points(m: re.Match[str]) -> str:
        indent = m.group("indent")
        orig = m.group(0)
        return (
            f"{indent}if ( maps\\_bz_hooks::bz_enabled() ){newline}"
            f"{indent}{{{newline}"
            f"{indent}\tpoints = maps\\_bz_hooks::bz_points_modify( self, points, event );{newline}"
            f"{indent}}}{newline}"
            f"{orig}"
        )

    text = PLAYER_ADD_POINTS_SCORE_RE.sub(_inject_player_add_points, text, count=1)
    return text.encode("latin1")


def inject_laststand_hooks(script_bytes: bytes) -> bytes:
    """Patch stock _laststand.gsc with unified revive speed, QR II invuln, and Solo extra revive."""
    text = script_bytes.decode("latin1")
    newline = "\r\n" if "\r\n" in text else "\n"

    # 1. Unified revive timing in revive_do_revive() (Quick Revive I/II + Field Medic)
    rev_match = LASTSTAND_REVIVE_TIME_RE.search(text)
    if rev_match is None:
        raise ValueError("Could not locate reviveTime = 3; in _laststand.gsc")
    rev_indent = rev_match.group("indent")
    rev_orig = rev_match.group(0).rstrip("\r")
    rev_ending = "\r" if rev_match.group(0).endswith("\r") else ""
    rev_hook = (
        f"{rev_orig}{newline}"
        f"{rev_indent}if ( maps\\_bz_hooks::bz_enabled() ){newline}"
        f"{rev_indent}{{{newline}"
        f"{rev_indent}\treviveTime = maps\\_bz_hooks::bz_get_revive_time( self, 3.0 );{newline}"
        f"{rev_indent}}}{rev_ending}"
    )
    text = text[: rev_match.start()] + rev_hook + text[rev_match.end() :]

    # 2. Post-revive invulnerability hook in revive_success( reviver )
    succ_match = LASTSTAND_REVIVE_SUCCESS_RE.search(text)
    if succ_match is None:
        raise ValueError("Could not locate self reviveplayer(); in _laststand.gsc")
    succ_indent = succ_match.group("indent")
    succ_orig = succ_match.group(0).rstrip("\r")
    succ_ending = "\r" if succ_match.group(0).endswith("\r") else ""
    succ_hook = (
        f"{succ_orig}{newline}"
        f"{succ_indent}if ( maps\\_bz_hooks::bz_enabled() ){newline}"
        f"{succ_indent}{{{newline}"
        f"{succ_indent}\tmaps\\_bz_perks::bz_perks_apply_revive_completed( reviver, self );{newline}"
        f"{succ_indent}}}{succ_ending}"
    )
    text = text[: succ_match.start()] + succ_hook + text[succ_match.end() :]

    # 3. Solo extra revive hook in PlayerLastStand() before mission fail check
    all_match = LASTSTAND_ALL_DOWN_RE.search(text)
    if all_match is None:
        raise ValueError("Could not locate player_all_players_in_laststand() check in _laststand.gsc")
    all_indent = all_match.group("indent")
    solo_hook = (
        f"{all_indent}if ( maps\\_bz_hooks::bz_enabled() && GetPlayers().size == 1 && maps\\_bz_perks::bz_perks_try_consume_solo_revive( self ) ){newline}"
        f"{all_indent}{{{newline}"
        f"{all_indent}\tself reviveplayer();{newline}"
        f"{all_indent}\tself.health = self.maxhealth;{newline}"
        f"{all_indent}\tmaps\\_bz_perks::bz_perks_apply_revive_completed( self, self );{newline}"
        f"{all_indent}\treturn;{newline}"
        f"{all_indent}}}{newline}"
        f"{all_match.group(0)}"
    )
    text = text[: all_match.start()] + solo_hook + text[all_match.end() :]

    return text.encode("latin1")


def _pick_tesla_player_param(params_raw: str) -> str:
    """Resolve the player parameter identifier from a stock _zombiemode_tesla.gsc signature."""
    params = [p.strip() for p in params_raw.split(",") if p.strip()]
    for param in params:
        if param.lower() in ("player", "attacker", "eattacker"):
            return param
    if params:
        return params[-1]
    return "player"


def inject_zombiemode_tesla_hooks(source_text: str | bytes) -> str | bytes:
    """Patch stock maps/_zombiemode_tesla.gsc for Wunderwaffe DG-2 Juggernog fix & chain-stun.

    Fixes WaW 1.7's infamous `tesla_pvp_thread()` self-shock bug where assigning directly to
    `self.health` resets `self.maxhealth` back to 100 (wiping Juggernog I 160, Juggernog II
    220, and Titan 320/440 HP):
      1. Strictly gated under `maps\\_bz_hooks::bz_elements_enabled()` so Classic Mode and
         `bz_elements_enabled 0` execute the exact stock self-shock code untouched.
      2. When enabled, skips self-shock completely when Blast Shield grants self-damage
         immunity (`bz_tesla_is_self_shock_immune`), otherwise brackets `self.health` writes
         with `sav = self.maxhealth; ... self.maxhealth = sav;` and calls
         `maps\\_bz_hooks::bz_recompute_player_max_health( self )` immediately after.
      3. Hooks `tesla_arc_damage` / `tesla_do_damage` / `tesla_damage_init` with a guarded
         `maps\\_bz_elem_stock::bz_tesla_on_chain_hit( self, <player> )` call for the 3.5s
         chain-stun buff on chained/nearby zombies.
    """
    is_bytes = isinstance(source_text, (bytes, bytearray))
    text = source_text.decode("latin1") if is_bytes else str(source_text)
    newline = "\r\n" if "\r\n" in text else "\n"

    # 1. Patch tesla_pvp_thread() self-shock health assignment (Sumpf & Der Riese shapes)
    pvp_match = TESLA_PVP_THREAD_DEF_RE.search(text)
    if pvp_match is None:
        raise ValueError("Could not locate tesla_pvp_thread() in _zombiemode_tesla.gsc")

    dmg_match = TESLA_SELF_DAMAGE_BLOCK_RE.search(text, pos=pvp_match.end())
    if dmg_match is None:
        raise ValueError(
            "Could not locate self.health self-shock block inside tesla_pvp_thread() in _zombiemode_tesla.gsc"
        )

    indent = dmg_match.group("indent")
    trailing = dmg_match.group("trailing")
    line_ending = "\r" if dmg_match.group(0).endswith("\r") else ""
    t = "\t"
    patched_pvp_block = (
        f"{indent}if ( maps\\_bz_hooks::bz_elements_enabled() ){newline}"
        f"{indent}{{{newline}"
        f"{indent}{t}if ( maps\\_bz_elem_stock::bz_tesla_is_self_shock_immune( self ) ){newline}"
        f"{indent}{t}{{{newline}"
        f"{indent}{t}{t}maps\\_bz_elem_stock::bz_tesla_on_self_shock( self, damage, true );{newline}"
        f"{indent}{t}{t}continue;{newline}"
        f"{indent}{t}}}{newline}"
        f"{indent}{t}sav = self.maxhealth;{newline}"
        f"{indent}{t}if ( self.health - damage < 1 ){newline}"
        f"{indent}{t}{{{newline}"
        f"{indent}{t}{t}self.health = 1;{newline}"
        f"{indent}{t}}}{newline}"
        f"{indent}{t}else{newline}"
        f"{indent}{t}{{{newline}"
        f"{indent}{t}{t}self.health -= damage;{newline}"
        f"{indent}{t}}}{newline}"
        f"{indent}{t}self.maxhealth = sav;{newline}"
        f"{indent}{t}maps\\_bz_hooks::bz_recompute_player_max_health( self );{newline}"
        f"{indent}{t}maps\\_bz_elem_stock::bz_tesla_on_self_shock( self, damage, false );{newline}"
        f"{indent}}}{newline}"
        f"{indent}else{newline}"
        f"{indent}{{{newline}"
        f"{indent}{t}if ( self.health - damage < 1 ){newline}"
        f"{indent}{t}{{{newline}"
        f"{indent}{t}{t}self.health = 1;{newline}"
        f"{indent}{t}}}{newline}"
        f"{indent}{t}else{newline}"
        f"{indent}{t}{{{newline}"
        f"{indent}{t}{t}self.health -= damage;{newline}"
        f"{indent}{t}}}{newline}"
        f"{indent}}}{trailing}{line_ending}"
    )
    text = text[: dmg_match.start()] + patched_pvp_block + text[dmg_match.end() :]

    # 2. Hook chain-hit seam for buffed Wunderwaffe stun
    chain_match: re.Match[str] | None = None
    for pattern in TESLA_CHAIN_FN_CANDIDATES:
        chain_match = pattern.search(text)
        if chain_match is not None:
            break
    if chain_match is None:
        raise ValueError(
            "Could not locate tesla_arc_damage(), tesla_do_damage(), or tesla_damage_init() "
            "in _zombiemode_tesla.gsc"
        )
    player_param = _pick_tesla_player_param(chain_match.group("params"))
    chain_hook = (
        f"{newline}"
        f"\tif ( maps\\_bz_hooks::bz_elements_enabled() ){newline}"
        f"\t{{{newline}"
        f"\t\tmaps\\_bz_elem_stock::bz_tesla_on_chain_hit( self, {player_param} );{newline}"
        f"\t}}"
    )
    text = text[: chain_match.end()] + chain_hook + text[chain_match.end() :]

    # 3. Cross-map DLC2/DLC3 era parity (Shi No Numa + Der Riese):
    #    - Shi No Numa's maps/_zombiemode_net.gsc defines init(), which collides with
    #      maps/_zombiemode_tesla.gsc's init() if `#include maps\_zombiemode_net;` is kept.
    #    - Replace network_safe_play_fx_on_tag(...) with PlayFxOnTag(...) (stock Sumpf path).
    #    - Guard DLC3-only upgraded viewmodel FX loadfx() calls to nazi_zombie_factory.
    #    - Support both Sumpf's flat level._zombie_tesla_death arrays and Factory's
    #      animname-indexed dictionaries.
    text = re.sub(
        r"^[ \t]*#include[ \t]+maps\\_zombiemode_net;[ \t]*\r?\n?",
        "",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r'network_safe_play_fx_on_tag\(\s*"[^"]*"\s*,\s*\d+\s*,\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^)]+?)\s*\)',
        r"PlayFxOnTag( \1, \2, \3 )",
        text,
    )
    text = re.sub(
        r'^(?P<indent>[ \t]*)(?P<stmt>level\._effect\["tesla_viewmodel_[^"]+_upgraded"\][^\r\n]+)',
        rf'\g<indent>if ( IsDefined( level.script ) && tolower( level.script ) == "nazi_zombie_factory" ) {{ \g<stmt> }}',
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r'^(?P<indent>[ \t]*)self\.deathanim\s*=\s*random\(\s*level\._zombie_tesla_death\[self\.animname\]\s*\);',
        (
            rf"\g<indent>if ( IsDefined( self.animname ) && IsDefined( level._zombie_tesla_death[self.animname] ) ){newline}"
            rf"\g<indent>{{{newline}"
            rf"\g<indent>\tself.deathanim = random( level._zombie_tesla_death[self.animname] );{newline}"
            rf"\g<indent>}}{newline}"
            rf"\g<indent>else{newline}"
            rf"\g<indent>{{{newline}"
            rf"\g<indent>\tself.deathanim = random( level._zombie_tesla_death );{newline}"
            rf"\g<indent>}}"
        ),
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r'^(?P<indent>[ \t]*)self\.deathanim\s*=\s*random\(\s*level\._zombie_tesla_crawl_death\[self\.animname\]\s*\);',
        (
            rf"\g<indent>if ( IsDefined( self.animname ) && IsDefined( level._zombie_tesla_crawl_death[self.animname] ) ){newline}"
            rf"\g<indent>{{{newline}"
            rf"\g<indent>\tself.deathanim = random( level._zombie_tesla_crawl_death[self.animname] );{newline}"
            rf"\g<indent>}}{newline}"
            rf"\g<indent>else{newline}"
            rf"\g<indent>{{{newline}"
            rf"\g<indent>\tself.deathanim = random( level._zombie_tesla_crawl_death );{newline}"
            rf"\g<indent>}}"
        ),
        text,
        flags=re.MULTILINE,
    )

    return text.encode("latin1") if is_bytes else text


def stage_bz_tesla_script(
    tools_root: Path,
    stage_dir: Path,
    steam_game: Path | None = None,
) -> Path | None:
    """Patch and stage maps/_zombiemode_tesla.gsc when stock Tesla script is available.

    Prefers installed stock fastfile archives (`nazi_zombie_factory_patch.ff`,
    `nazi_zombie_factory.ff`, `nazi_zombie_sumpf_patch.ff`, `nazi_zombie_sumpf.ff`)
    before falling back to `tools_root/raw/maps/_zombiemode_tesla.gsc`.
    Returns the staged Path, or None if no stock `_zombiemode_tesla.gsc` exists on this host.
    """
    stock_bytes: bytes | None = None
    search_steam = steam_game if steam_game is not None else tools_root
    for map_name in ("nazi_zombie_factory", "nazi_zombie_sumpf"):
        try:
            extracted = try_extract_stock_script(
                map_name, "maps/_zombiemode_tesla.gsc", search_steam, tools_root
            )
        except FileNotFoundError:
            extracted = None
        if extracted is not None:
            stock_bytes = extracted
            break

    if stock_bytes is None:
        raw_tesla = tools_root / "raw" / "maps" / "_zombiemode_tesla.gsc"
        if raw_tesla.is_file():
            stock_bytes = raw_tesla.read_bytes()

    if stock_bytes is None:
        return None

    patched_bytes = inject_zombiemode_tesla_hooks(stock_bytes)
    assert isinstance(patched_bytes, bytes)
    out_path = stage_dir / "maps" / "_zombiemode_tesla.gsc"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(patched_bytes)
    return out_path


_CSC_LEVEL_NOTIFY_1ARG_RE = re.compile(
    r"(?P<sig>level_notify\s*\(\s*notify_name\s*\)\s*\{)"
    r"(?P<body>[^}]*?\blevel\s+notify\s*\(\s*notify_name\s*\)\s*;[^}]*?\})",
    re.DOTALL,
)


def inject_clientscript_callbacks_patch(source: bytes | str) -> bytes | str:
    """Ensure clientscripts/_callbacks.csc::level_notify accepts DLC 3-arg notetrack callbacks.

    Pre-DLC2 stock maps (Nacht der Untoten, Verruckt) load common.ff's 1-arg
    `level_notify(notify_name)`, which throws a client script runtime error when
    `bz_cryo_cannon` (cloned from `tesla_gun`) dispatches viewmodel animation
    notetracks via `level_notify("notetrack", localClientNum, note)`.
    """
    is_bytes = isinstance(source, bytes)
    text = source.decode("latin1") if is_bytes else source
    if re.search(r"level_notify\s*\(\s*notify_name\s*,\s*\w+\s*,\s*\w+\s*\)", text):
        return source

    newline = "\r\n" if "\r\n" in text else "\n"
    patched, count = _CSC_LEVEL_NOTIFY_1ARG_RE.subn(
        f"level_notify(notify_name, param1, param2){newline}"
        f"{{{newline}"
        f"\tlevel notify(notify_name, param1, param2);{newline}"
        f"}}",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError("Could not locate level_notify() in clientscripts/_callbacks.csc")
    return patched.encode("latin1") if is_bytes else patched


def stage_bz_clientscript_callbacks(
    tools_root: Path,
    stage_dir: Path,
    steam_game: Path | None = None,
) -> Path | None:
    """Stage DLC-compatible clientscripts/_callbacks.csc so Cryo Cannon notetracks work on all 4 maps."""
    stock_bytes: bytes | None = None
    search_steam = steam_game if steam_game is not None else tools_root
    for map_name in ("nazi_zombie_factory", "nazi_zombie_sumpf"):
        try:
            extracted = try_extract_stock_script(
                map_name, "clientscripts/_callbacks.csc", search_steam, tools_root
            )
        except FileNotFoundError:
            extracted = None
        if extracted is not None:
            stock_bytes = extracted
            break

    if stock_bytes is None:
        raw_csc = tools_root / "raw" / "clientscripts" / "_callbacks.csc"
        if raw_csc.is_file():
            stock_bytes = raw_csc.read_bytes()

    if stock_bytes is None:
        for base in (search_steam, tools_root):
            common_ff = base / "zone" / "english" / "common.ff"
            if common_ff.is_file():
                try:
                    stock_bytes = extract_rawfile_from_ff(common_ff, "clientscripts/_callbacks.csc")
                    break
                except ValueError:
                    continue

    if stock_bytes is None:
        return None

    patched_bytes = inject_clientscript_callbacks_patch(stock_bytes)
    assert isinstance(patched_bytes, bytes)
    out_path = stage_dir / "clientscripts" / "_callbacks.csc"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(patched_bytes)
    return out_path


def stamp_bz_station_menu_build_parity(menu_text: str, build_id: str) -> str:
    """Stamp an independent retail-visible client-package build fingerprint & mismatch alert into a station menu."""
    if not re.fullmatch(r"[0-9a-zA-Z_.-]+", build_id):
        raise ValueError("Invalid Base Zombies client build ID")
    if '"bz_parity_mismatch"' in menu_text:
        return menu_text

    newline = "\r\n" if "\r\n" in menu_text else "\n"
    # Insert just before the final closing braces of `menuDef { ... }` inside outer `{ ... }`.
    closing_re = re.compile(r"(?P<tail>\r?\n\t\}\r?\n\}\s*)$")
    match = closing_re.search(menu_text)
    if match is None:
        raise ValueError("Could not locate closing menuDef brace in Base Zombies station menu")

    snippet = (
        f"{newline}"
        f"\t\t// Build-stamped local mod.ff fingerprint & retail-visible host parity alert{newline}"
        f"\t\titemDef{newline}"
        f"\t\t{{{newline}"
        f'\t\t\tname\t\t\t"bz_parity_ok"{newline}'
        f"\t\t\ttype\t\t\tITEM_TYPE_TEXT{newline}"
        f"\t\t\trect\t\t\t28 465 584 14{newline}"
        f'\t\t\ttext\t\t\t"BUILD: {build_id}"{newline}'
        f"\t\t\ttextfont\t\tUI_FONT_NORMAL{newline}"
        f"\t\t\ttextscale\t\t0.22{newline}"
        f"\t\t\ttextstyle\t\tITEM_TEXTSTYLE_SHADOWED{newline}"
        f"\t\t\ttextalign\t\tITEM_ALIGN_RIGHT{newline}"
        f"\t\t\ttextaligny\t\t11{newline}"
        f"\t\t\tforecolor\t\t0.70 0.78 0.85 0.90{newline}"
        f'\t\t\tvisible\t\t\twhen( dvarString( "bz_host_build_id" ) == "" || dvarString( "bz_host_build_id" ) == "{build_id}" );{newline}'
        f"\t\t\tdecoration{newline}"
        f"\t\t}}{newline}"
        f"\t\titemDef{newline}"
        f"\t\t{{{newline}"
        f'\t\t\tname\t\t\t"bz_parity_mismatch"{newline}'
        f"\t\t\ttype\t\t\tITEM_TYPE_TEXT{newline}"
        f"\t\t\trect\t\t\t28 465 584 14{newline}"
        f'\t\t\texp\t\t\t\ttext( "BUILD MISMATCH! LOCAL {build_id} != HOST " + dvarString( "bz_host_build_id" ) );{newline}'
        f"\t\t\ttextfont\t\tUI_FONT_NORMAL{newline}"
        f"\t\t\ttextscale\t\t0.22{newline}"
        f"\t\t\ttextstyle\t\tITEM_TEXTSTYLE_SHADOWED{newline}"
        f"\t\t\ttextalign\t\tITEM_ALIGN_CENTER{newline}"
        f"\t\t\ttextaligny\t\t11{newline}"
        f"\t\t\tforecolor\t\t1.0 0.25 0.25 1.0{newline}"
        f'\t\t\tvisible\t\t\twhen( dvarString( "bz_host_build_id" ) != "" && dvarString( "bz_host_build_id" ) != "{build_id}" );{newline}'
        f"\t\t\tdecoration{newline}"
        f"\t\t}}"
    )
    return menu_text[: match.start()] + snippet + match.group("tail")


def parse_weapon_file(text: str) -> list[tuple[str, str]]:
    """Parse a WaW 1.7 backslash-delimited WEAPONFILE\\key\\val\\... string."""
    cleaned = text.rstrip("\r\n")
    tokens = cleaned.split("\\")
    if not tokens or tokens[0] != "WEAPONFILE":
        raise ValueError("Invalid WaW weapon file: missing leading 'WEAPONFILE\\\\' header")
    body = tokens[1:]
    if len(body) % 2 != 0:
        raise ValueError(
            f"Malformed WaW weapon file: expected even key/value token count, got {len(body)}"
        )
    return [(body[i], body[i + 1]) for i in range(0, len(body), 2)]


def serialize_weapon_file(pairs: list[tuple[str, str]]) -> str:
    """Serialize ordered (key, value) pairs back into WaW 1.7 WEAPONFILE format."""
    parts = ["WEAPONFILE"]
    for key, val in pairs:
        parts.append(str(key))
        parts.append(str(val))
    return "\\".join(parts)


def build_xanim_case_map(xanim_dir: Path) -> dict[str, str]:
    """Build a lowercase -> exact on-disk filename map from raw/xanim/ for Linux case-safe linking."""
    if not xanim_dir.is_dir():
        return {}
    case_map: dict[str, str] = {}
    for entry in sorted(xanim_dir.iterdir()):
        if entry.is_file():
            case_map[entry.name.lower()] = entry.name
    return case_map


def clone_zero_fx_weapon_file(
    stock_text: str,
    overrides: dict[str, str],
    allowed_fx_set: set[str] | frozenset[str] | None = None,
    xanim_case_map: dict[str, str] | None = None,
) -> str:
    """Deterministically clone a WaW stock weapon definition with 0 added FX slots.

    Any `*Effect` or `*Fx` field (case-insensitive) whose value is non-empty and not
    present in `allowed_fx_set` (defaults to VERIFIED_ALL_4_MAP_FX) is cleared to `""`.
    When `xanim_case_map` (lowercase -> exact on-disk filename from `raw/xanim/`) is
    provided, every non-empty `*Anim` value is resolved case-insensitively to its exact
    on-disk casing, overridden `*Anim` values missing from disk fall back to the
    template's existing anim, and missing optional `ads*Anim` fields are cleared to `""`.
    """
    pairs = parse_weapon_file(stock_text)
    allowed = {
        fx.strip().replace("\\", "/").lower()
        for fx in (VERIFIED_ALL_4_MAP_FX if allowed_fx_set is None else allowed_fx_set)
        if fx and fx.strip()
    }
    anim_map: dict[str, str] | None = None
    if xanim_case_map is not None:
        anim_map = {
            k.strip().lower(): v.strip()
            for k, v in xanim_case_map.items()
            if k and k.strip() and v and v.strip()
        }

    original_values: dict[str, str] = {key: val for key, val in pairs}
    applied_keys: set[str] = set()
    updated: list[tuple[str, str]] = []
    for key, val in pairs:
        if key in overrides:
            val = str(overrides[key])
            applied_keys.add(key)
        updated.append((key, val))

    for key, val in overrides.items():
        if key not in applied_keys:
            updated.append((key, str(val)))

    sanitized: list[tuple[str, str]] = []
    for key, val in updated:
        key_lower = key.lower()
        if key_lower == "altweapon":
            val = ""
        elif key_lower.endswith("effect") or key_lower.endswith("fx"):
            norm_val = val.strip().replace("\\", "/").lower()
            if norm_val and norm_val not in allowed:
                val = ""
        elif anim_map is not None and key_lower.endswith("anim"):
            stripped = val.strip()
            if stripped:
                resolved = anim_map.get(stripped.lower())
                if resolved is not None:
                    val = resolved
                elif key in overrides:
                    orig_val = original_values.get(key, "").strip()
                    if orig_val:
                        orig_resolved = anim_map.get(orig_val.lower())
                        if orig_resolved is not None:
                            val = orig_resolved
                        elif key_lower.startswith("ads"):
                            val = ""
                        else:
                            val = orig_val
                    else:
                        val = ""
                elif key_lower.startswith("ads"):
                    val = ""
        sanitized.append((key, val))

    return serialize_weapon_file(sanitized)


def stage_bz_element_weapons(
    tools_root: Path,
    stage_dir: Path,
    allowed_fx_set: set[str] | frozenset[str] | None = None,
) -> list[str]:
    """Generate and stage the 4 zero-FX cloned Phase 2 primary weapons under stage_dir/weapons/sp/.

    Returns the relative paths (e.g. `weapons/sp/bz_acid_sprayer`) staged. Returns an empty list
    if stock weapon templates are not present under `tools_root/raw/weapons/sp/`.
    """
    raw_weapons_dir = tools_root / "raw" / "weapons" / "sp"
    if not raw_weapons_dir.is_dir():
        return []

    raw_xanim_dir = tools_root / "raw" / "xanim"
    xanim_case_map = build_xanim_case_map(raw_xanim_dir) if raw_xanim_dir.is_dir() else None

    out_dir = stage_dir / "weapons" / "sp"
    staged_relpaths: list[str] = []
    for weap_name, template_candidates, overrides in BZ_ELEMENT_WEAPON_SPECS:
        template_path: Path | None = None
        for candidate in template_candidates:
            path = raw_weapons_dir / candidate
            if path.is_file():
                template_path = path
                break
        if template_path is None:
            raise FileNotFoundError(
                f"No stock weapon template found for {weap_name} in {raw_weapons_dir} "
                f"(tried: {', '.join(template_candidates)})"
            )
        stock_text = template_path.read_text(encoding="latin1")
        cloned_text = clone_zero_fx_weapon_file(
            stock_text,
            overrides=overrides,
            allowed_fx_set=allowed_fx_set,
            xanim_case_map=xanim_case_map,
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / weap_name
        out_path.write_text(cloned_text, encoding="latin1")
        staged_relpaths.append(f"weapons/sp/{weap_name}")

    return staged_relpaths


# Stock iw_14.iwd ptrs41_zombie & m2_flamethrower_zombie reference these xmodels, which exist
# in Nacht/Verruckt/Shi No Numa but were renamed in Der Riese (nazi_zombie_factory.ff).
# Including these 4 xmodels in staged mod.csv (0 added FX) fixes missing PTRS-41 & Flamethrower
# models on Der Riese under fs_game without breaking the other 3 stock maps.
DER_RIESE_COMPAT_XMODELS: tuple[str, ...] = (
    "viewmodel_mp_ptrs41",
    "weapon_mp_ptrs41",
    "viewmodel_usa_flamethrower",
    "weapon_usa_flamethrower",
)


def generate_staged_mod_csv(
    base_csv_text: str,
    staged_gsc_relpaths: list[str],
    staged_weapon_relpaths: list[str] | None = None,
    extra_xmodels: list[str] | None = None,
) -> str:
    """Ensure mod.csv includes all staged _bz_*.gsc, BZ-patched stock scripts, cloned bz_* weapons, and compat xmodels."""
    newline = "\r\n" if "\r\n" in base_csv_text else "\n"
    existing_lines = {line.strip().lower() for line in base_csv_text.splitlines()}
    additions: list[str] = []
    for rel in sorted(staged_gsc_relpaths):
        norm = rel.replace("\\", "/").lstrip("/")
        stem = Path(norm).name.lower()
        is_bz_script = (
            stem.startswith("_bz_")
            or stem.startswith("_zombiemode_weapons_bz_")
            or stem.startswith("_zombiemode_perks_bz_")
            or stem.startswith("_zombiemode_dogs_bz_")
            or stem.startswith("_zombiemode_powerups_bz_")
            or stem
            in (
                "_zombiemode_score.gsc",
                "_laststand.gsc",
                "_zombiemode_tesla.gsc",
                "_callbacks.csc",
                "nazi_zombie_factory_teleporter.gsc",
            )
        )
        if not is_bz_script:
            continue
        entry = f"rawfile,{norm}"
        if entry.lower() not in existing_lines:
            existing_lines.add(entry.lower())
            additions.append(entry)

    for rel in sorted(staged_weapon_relpaths or []):
        norm = rel.replace("\\", "/").lstrip("/")
        if norm.lower().startswith("weapons/"):
            weap_ref = norm[len("weapons/") :]
        else:
            weap_ref = norm
        entry = f"weapon,{weap_ref}"
        if entry.lower() not in existing_lines:
            existing_lines.add(entry.lower())
            additions.append(entry)

    for xmodel in sorted(extra_xmodels or []):
        entry = f"xmodel,{xmodel}"
        if entry.lower() not in existing_lines:
            existing_lines.add(entry.lower())
            additions.append(entry)

    if not additions:
        return base_csv_text

    suffix = "" if base_csv_text.endswith(("\n", "\r")) else newline
    return base_csv_text + suffix + newline.join(additions) + newline


# ---------------------------------------------------------------------------
# Base Zombies Stock Menu Patchers (layered cleanly on Gauntlet-patched menus)
# ---------------------------------------------------------------------------


def patch_main_menu_bz(source: str) -> str:
    """Add Solo 'ENHANCEMENTS' launch entry and Classic bz_enabled=0 reset to ui/main.menu."""
    newline = "\r\n" if "\r\n" in source else "\n"
    text = source

    # 1. Ensure LOCAL_ZOMBIE_RESET resets all 6 bz_*_enabled gates to 0 alongside gauntlet_enabled 0
    if "set bz_enabled 0" not in text:
        reset_re = re.compile(r'(set gauntlet_enabled 0)";')
        new_text, count = reset_re.subn(
            r'\1; set bz_enabled 0; set bz_perks_enabled 0; set bz_classes_enabled 0; set bz_pap_enabled 0; set bz_elements_enabled 0; set bz_companions_enabled 0";',
            text,
            count=1,
        )
        if count != 1:
            raise ValueError("Could not locate LOCAL_ZOMBIE_RESET gauntlet_enabled reset in ui/main.menu")
        text = new_text

    # 2. Inject Solo "ENHANCEMENTS" (slot 5) and "ENHANCED GAUNTLET" (slot 6) right after "ZOMBIE GAUNTLET"
    if "BZ_SOLO_START_ACTION" not in text:
        gauntlet_btn_re = re.compile(
            r'^(?P<indent>[ \t]*)CHOICE_BUTTON_VIS\(\s*4,\s*"ZOMBIE GAUNTLET"[^\n]*$',
            re.MULTILINE,
        )
        match = gauntlet_btn_re.search(text)
        if match is None:
            raise ValueError("Could not locate Solo ZOMBIE GAUNTLET button in ui/main.menu")
        indent = match.group("indent")
        bz_btn = (
            f'{indent}CHOICE_BUTTON_VIS( 5, "ENHANCEMENTS", '
            f'BZ_SOLO_START_ACTION, when( !localvarBool( ui_hideBack ) ); ){newline}'
            f'{indent}CHOICE_BUTTON_VIS( 6, "ENHANCED GAUNTLET", '
            f'GAUNTLET_ENHANCED_SOLO_START_ACTION, when( !localvarBool( ui_hideBack ) ); )'
        )
        text = text[: match.end()] + f"{newline}{bz_btn}" + text[match.end() :]

    return text


def patch_levels_menu_bz(source: str) -> str:
    """Add Solo 'ENHANCEMENTS' launch button and Classic bz_enabled=0 guard to ui/levels.menu."""
    newline = "\r\n" if "\r\n" in source else "\n"
    text = source

    # 1. Ensure Classic Solo Nazi Zombies map entries explicitly zero all 6 bz_*_enabled gates
    if 'setdvar bz_enabled "0"' not in text:
        gauntlet_zero_re = re.compile(
            r'(setdvar gauntlet_enabled "0";[ \t]*\\\r?\n)',
            re.MULTILINE,
        )
        new_text, count = gauntlet_zero_re.subn(
            rf'\1\tsetdvar bz_enabled "0"; \\{newline}'
            rf'\tsetdvar bz_perks_enabled "0"; \\{newline}'
            rf'\tsetdvar bz_classes_enabled "0"; \\{newline}'
            rf'\tsetdvar bz_pap_enabled "0"; \\{newline}'
            rf'\tsetdvar bz_elements_enabled "0"; \\{newline}'
            rf'\tsetdvar bz_companions_enabled "0"; \\{newline}',
            text,
            count=1,
        )
        if count != 1:
            raise ValueError("Could not locate gauntlet_enabled reset in ui/levels.menu")
        text = new_text

    # 2. Inject Solo Enhancements buttons for all 4 Stock Maps at slots 6..9 alongside ZOMBIE GAUNTLET
    if "BZ_SOLO_START_ACTION" not in text:
        gauntlet_lvl_re = re.compile(
            r'^(?P<indent>[ \t]*)(?:BZ_)?ZOMBIE_CHOICE_BUTTON\(\s*1,\s*"ZOMBIE GAUNTLET"[^\n]*$',
            re.MULTILINE,
        )
        match = gauntlet_lvl_re.search(text)
        if match is None:
            raise ValueError("Could not locate levels_unlock ZOMBIE GAUNTLET entry in ui/levels.menu")
        indent = match.group("indent")
        bz_entries = (
            f'{indent}BZ_ZOMBIE_CHOICE_BUTTON( 6, "ENHANCEMENTS: DER RIESE", BZ_SOLO_START_ACTION, '
            f'"bz_factory", "nazi_zombie_factory", "Base Zombies Enhancements on Der Riese (Perks, Classes, PaP & Arsenal).", '
            f'18, exec "set ui_load_index 18" ){newline}'
            f'{indent}BZ_ZOMBIE_CHOICE_BUTTON( 7, "ENHANCEMENTS: NACHT", BZ_SOLO_START_PROTOTYPE_ACTION, '
            f'"bz_prototype", "nazi_zombie_prototype", "Base Zombies Enhancements on Nacht der Untoten (Perks, Classes, PaP & Arsenal).", '
            f'15, exec "set ui_load_index 15" ){newline}'
            f'{indent}BZ_ZOMBIE_CHOICE_BUTTON( 8, "ENHANCEMENTS: VERRUCKT", BZ_SOLO_START_ASYLUM_ACTION, '
            f'"bz_asylum", "nazi_zombie_asylum", "Base Zombies Enhancements on Verruckt (Perks, Classes, PaP & Arsenal).", '
            f'16, exec "set ui_load_index 16" ){newline}'
            f'{indent}BZ_ZOMBIE_CHOICE_BUTTON( 9, "ENHANCEMENTS: SHI NO NUMA", BZ_SOLO_START_SUMPF_ACTION, '
            f'"bz_sumpf", "nazi_zombie_sumpf", "Base Zombies Enhancements on Shi No Numa (Perks, Classes, PaP & Arsenal).", '
            f'17, exec "set ui_load_index 17" ){newline}'
            f'{indent}BZ_ZOMBIE_CHOICE_BUTTON( 10, "ENHANCED GAUNTLET", GAUNTLET_ENHANCED_SOLO_START_ACTION, '
            f'"gauntlet_bz_prototype", "nazi_zombie_prototype", "Endless 4-map Zombie Gauntlet with Full Base Zombies Enhancements (Perks, Classes, PaP & Arsenal carry over).", '
            f'15, exec "set ui_load_index 15" )'
        )
        text = text[: match.end()] + f"{newline}{bz_entries}" + text[match.end() :]

    return text


def _patch_coop_lobby_menu_bz(source: str, filename: str) -> str:
    """Inject BZ_COOP_LOBBY_STATUS_PANEL into a Co-op lobby menu."""
    newline = "\r\n" if "\r\n" in source else "\n"
    text = source
    if "BZ_COOP_LOBBY_STATUS_PANEL" not in text:
        anchor_re = re.compile(
            r"^(?P<indent>[ \t]*)GAUNTLET_COOP_LOBBY_STATUS_PANEL\([^\n]*$",
            re.MULTILINE,
        )
        match = anchor_re.search(text)
        if match is None:
            raise ValueError(f"Could not locate GAUNTLET_COOP_LOBBY_STATUS_PANEL in {filename}")
        indent = match.group("indent")
        panel = f"{indent}BZ_COOP_LOBBY_STATUS_PANEL( 30, 178, 250, 44, HORIZONTAL_ALIGN_LEFT, VERTICAL_ALIGN_TOP )"
        text = text[: match.end()] + f"{newline}{panel}" + text[match.end() :]
    return text


def patch_xboxlive_lobby_menu_bz(source: str) -> str:
    text = _patch_coop_lobby_menu_bz(source, "ui/xboxlive_lobby.menu")
    # Hide the legacy lobby playlist_totalonline readout so it never collides with
    # the unconditionally visible build stamp or Gauntlet status panel for either
    # hosts or guests. The find-game popup keeps its separate playlist count.
    lobby = re.search(
        r'(?ms)^[ \t]*name[ \t]+"?menu_xboxlive_lobby"?[ \t]*\r?$.*?(?=^[ \t]*menuDef\b|\Z)',
        text,
    )
    if lobby is None:
        return text
    count_item = re.compile(
        r'(?m)\bitemDef\s*\{[^{}]*?^[ \t]*dvar[ \t]+"?playlist_totalonline"?[ \t]*\r?$[^{}]*\}',
    ).search(text, lobby.start(), lobby.end())
    if count_item is None:
        return text
    item = re.sub(
        r"(?m)^([ \t]*visible[ \t]+)1(?=[ \t]*\r?$)",
        r"\g<1>0",
        count_item.group(),
    )
    return text[:count_item.start()] + item + text[count_item.end():]


def patch_systemlink_lobby_menu_bz(source: str) -> str:
    return _patch_coop_lobby_menu_bz(source, "ui/systemlink_lobby.menu")


def apply_bz_menu_patches(stage_dir: Path) -> list[Path]:
    """Apply Base Zombies Solo/Co-op menu patches to staged stock menus and validate braces."""
    import verify_hud_menus

    out_ui = stage_dir / "ui"
    patchers = (
        ("main.menu", patch_main_menu_bz),
        ("levels.menu", patch_levels_menu_bz),
        ("xboxlive_lobby.menu", patch_xboxlive_lobby_menu_bz),
        ("systemlink_lobby.menu", patch_systemlink_lobby_menu_bz),
    )
    updated: list[Path] = []
    for filename, patch_fn in patchers:
        path = out_ui / filename
        if not path.is_file():
            raise FileNotFoundError(f"Staged menu missing before BZ patch: {path}")
        patched = patch_fn(path.read_text(encoding="latin1"))
        brace_errors = verify_hud_menus.validate_menu_braces(patched, filename=filename)
        if brace_errors:
            raise ValueError(f"BZ-patched menu {filename} failed brace validation: {brace_errors}")
        path.write_text(patched, encoding="latin1")
        updated.append(path)
    return updated


def render_bz_version_gsc(version: str, commit_sha: str) -> str:
    """Render ASCII GSC getters for the build fingerprint."""
    if not re.fullmatch(r"[0-9a-zA-Z_.-]+", version):
        raise ValueError("Invalid Base Zombies build version")
    if not BZ_BUILD_COMMIT_RE.fullmatch(commit_sha):
        raise ValueError("Invalid Base Zombies build commit")

    return f'''\
// The build stamps the commit in the staged copy of this module.
bz_get_build_version()
{{
\treturn "{version}";
}}

bz_get_build_commit()
{{
\treturn "{commit_sha}";
}}

bz_get_build_id()
{{
\treturn bz_get_build_version() + "-" + bz_get_build_commit();
}}
'''


def resolve_git_short_sha(repo_root: Path) -> str:
    """Read the short HEAD commit or use the dev fallback for source-only builds."""
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
        )
        commit_sha = output.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError):
        return "dev"
    return commit_sha if BZ_BUILD_COMMIT_RE.fullmatch(commit_sha) else "dev"


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

    # Both the linker and IWD packager use this staged script.
    build_commit = resolve_git_short_sha(REPO_ROOT)
    build_id = f"{BZ_BUILD_VERSION}-{build_commit}"
    (stage_dir / "maps" / "_bz_version.gsc").write_text(
        render_bz_version_gsc(BZ_BUILD_VERSION, build_commit),
        encoding="ascii",
    )

    # Extract each stock map entry script and era-specific _zombiemode, _zombiemode_weapons,
    # and _zombiemode_perks scripts (preferring <map>_patch.ff so DLC3 features and local
    # waw_solo_fov() stay intact while preserving era parity across all 4 stock maps).
    for map_name in STOCK_MAPS:
        weapons_mod: str | None = None
        weapons_stock = try_extract_stock_script(
            map_name, "maps/_zombiemode_weapons.gsc", steam_game, tools_root
        )
        if weapons_stock is not None:
            weapons_mod = zombiemode_weapons_module_for_map(map_name)
            weapons_patched = inject_zombiemode_weapons_hooks(weapons_stock)
            weapons_dst = stage_dir / "maps" / f"{weapons_mod}.gsc"
            weapons_dst.parent.mkdir(parents=True, exist_ok=True)
            weapons_dst.write_bytes(weapons_patched)

        perks_mod: str | None = None
        perks_stock = try_extract_stock_script(
            map_name, "maps/_zombiemode_perks.gsc", steam_game, tools_root
        )
        if perks_stock is not None:
            perks_mod = zombiemode_perks_module_for_map(map_name)
            perks_patched = inject_zombiemode_perks_hooks(
                perks_stock,
                rewire_weapons_module=weapons_mod,
            )
            perks_dst = stage_dir / "maps" / f"{perks_mod}.gsc"
            perks_dst.parent.mkdir(parents=True, exist_ok=True)
            perks_dst.write_bytes(perks_patched)

        dogs_mod: str | None = None
        powerups_mod: str | None = None
        dogs_stock = try_extract_stock_script(
            map_name, "maps/_zombiemode_dogs.gsc", steam_game, tools_root
        )
        if dogs_stock is not None:
            dogs_mod = zombiemode_dogs_module_for_map(map_name)
            powerups_stock = try_extract_stock_script(
                map_name, "maps/_zombiemode_powerups.gsc", steam_game, tools_root
            )
            if powerups_stock is not None and b"maps\\_zombiemode_dogs::" in powerups_stock:
                powerups_mod = zombiemode_powerups_module_for_map(map_name)
                powerups_patched = _rewire_stock_module_refs(
                    powerups_stock.decode("latin1"),
                    rewire_weapons_module=weapons_mod,
                    rewire_dogs_module=dogs_mod,
                    rewire_powerups_module=powerups_mod,
                ).encode("latin1")
                powerups_dst = stage_dir / "maps" / f"{powerups_mod}.gsc"
                powerups_dst.parent.mkdir(parents=True, exist_ok=True)
                powerups_dst.write_bytes(powerups_patched)

            dogs_patched = inject_zombiemode_dogs_hooks(
                dogs_stock,
                rewire_weapons_module=weapons_mod,
                rewire_powerups_module=powerups_mod,
            )
            dogs_dst = stage_dir / "maps" / f"{dogs_mod}.gsc"
            dogs_dst.parent.mkdir(parents=True, exist_ok=True)
            dogs_dst.write_bytes(dogs_patched)

            teleporter_rel = f"maps/{map_name}_teleporter.gsc"
            teleporter_stock = try_extract_stock_script(
                map_name, teleporter_rel, steam_game, tools_root
            )
            if teleporter_stock is not None and (
                b"maps\\_zombiemode_dogs::" in teleporter_stock
                or b"maps\\_zombiemode_powerups::" in teleporter_stock
            ):
                teleporter_patched = _rewire_stock_module_refs(
                    teleporter_stock.decode("latin1"),
                    rewire_weapons_module=weapons_mod,
                    rewire_dogs_module=dogs_mod,
                    rewire_powerups_module=powerups_mod,
                ).encode("latin1")
                teleporter_dst = stage_dir / teleporter_rel
                teleporter_dst.parent.mkdir(parents=True, exist_ok=True)
                teleporter_dst.write_bytes(teleporter_patched)

        rawfile_rel = f"maps/{map_name}.gsc"
        ff_path = resolve_stock_ff(map_name, steam_game, tools_root, prefer_patch=False)
        stock_bytes = extract_rawfile_from_ff(ff_path, rawfile_rel)
        patched_map_bytes = inject_map_hooks(
            stock_bytes,
            map_name,
            rewire_weapons_module=weapons_mod,
            rewire_perks_module=perks_mod,
            rewire_dogs_module=dogs_mod,
            rewire_powerups_module=powerups_mod,
        )
        dst = stage_dir / rawfile_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(patched_map_bytes)

        zm_stock_bytes = extract_stock_zombiemode(map_name, steam_game, tools_root)
        zm_patched_bytes = inject_zombiemode_hooks(
            zm_stock_bytes,
            map_name,
            rewire_weapons_module=weapons_mod,
            rewire_perks_module=perks_mod,
            rewire_dogs_module=dogs_mod,
            rewire_powerups_module=powerups_mod,
        )
        zm_dst = stage_dir / "maps" / f"{zombiemode_module_for_map(map_name)}.gsc"
        zm_dst.parent.mkdir(parents=True, exist_ok=True)
        zm_dst.write_bytes(zm_patched_bytes)

    # Stage unified, era-safe patched maps/_zombiemode_score.gsc and maps/_laststand.gsc
    # from Der Riese (which is a clean superset across all 4 stock maps) so every stock
    # caller (spawner, powerups, blockers, weapons, perks, dogs) routes through our guarded
    # Broker score multiplier, unified revive speed, QR II invuln, and Solo extra revive hooks.
    score_stock = extract_stock_script(
        "nazi_zombie_factory", "maps/_zombiemode_score.gsc", steam_game, tools_root
    )
    score_patched = inject_zombiemode_score_hooks(score_stock)
    score_dst = stage_dir / "maps" / "_zombiemode_score.gsc"
    score_dst.parent.mkdir(parents=True, exist_ok=True)
    score_dst.write_bytes(score_patched)

    laststand_stock = extract_stock_script(
        "nazi_zombie_factory", "maps/_laststand.gsc", steam_game, tools_root
    )
    laststand_patched = inject_laststand_hooks(laststand_stock)
    laststand_dst = stage_dir / "maps" / "_laststand.gsc"
    laststand_dst.parent.mkdir(parents=True, exist_ok=True)
    laststand_dst.write_bytes(laststand_patched)

    # Patch and stage stock maps/_zombiemode_tesla.gsc (Wunderwaffe Juggernog fix & chain-stun)
    stage_bz_tesla_script(tools_root=tools_root, stage_dir=stage_dir, steam_game=steam_game)

    # Stage DLC-compatible clientscripts/_callbacks.csc (3-arg level_notify for Cryo Cannon on Nacht/Verruckt)
    stage_bz_clientscript_callbacks(
        tools_root=tools_root,
        stage_dir=stage_dir,
        steam_game=steam_game,
    )

    # Generate and stage zero-FX cloned Phase 2 primary weapons (when raw weapon templates exist)
    staged_weapons = stage_bz_element_weapons(tools_root=tools_root, stage_dir=stage_dir)

    # Auto-register any tracked _bz_*.gsc, staged per-map BZ wrapper scripts, cloned bz_* weapons,
    # and Der Riese PTRS-41/Flamethrower compat xmodels (when raw xmodels exist).
    staged_mod_csv = stage_dir / "mod.csv"
    if staged_mod_csv.is_file():
        staged_gscs = [
            p.relative_to(stage_dir).as_posix()
            for p in sorted((stage_dir / "maps").rglob("*.gsc"))
        ]
        clientscripts_dir = stage_dir / "clientscripts"
        if clientscripts_dir.is_dir():
            staged_gscs.extend(
                p.relative_to(stage_dir).as_posix()
                for p in sorted(clientscripts_dir.rglob("*.csc"))
            )
        raw_xmodel_dir = tools_root / "raw" / "xmodel"
        compat_xmodels = [
            xm for xm in DER_RIESE_COMPAT_XMODELS if (raw_xmodel_dir / xm).is_file()
        ]
        updated_csv = generate_staged_mod_csv(
            staged_mod_csv.read_text(encoding="latin1"),
            staged_gscs,
            staged_weapon_relpaths=staged_weapons,
            extra_xmodels=compat_xmodels,
        )
        staged_mod_csv.write_text(updated_csv, encoding="latin1")

    # Stage stock DLC weapon definition files missing from base iw_*.iwd into stage_dir/weapons/sp/
    # so build_iwd() packs them into waw_gauntlet.iwd. Under fs_game, WaW 1.7 resolves weapons/sp/*
    # via IWD/disk search paths; without these in waw_gauntlet.iwd, DLC weapons (Gewehr 43, Kar98k,
    # MP40, Wunderwaffe, PaP guns, perk bottles, etc.) fall back to the pink Default Weapon box.
    # Kept out of mod.csv so zero fastfile FX assets are added.
    stage_dlc_iwd_weapon_files(tools_root=tools_root, steam_game=steam_game, stage_dir=stage_dir)

    import verify_hud_menus

    verify_hud_menus.stage_patched_menus(tools_root=tools_root, stage_dir=stage_dir)
    apply_bz_menu_patches(stage_dir=stage_dir)

    lobby_include = stage_dir / "ui" / "bz_menus.inc"
    stamped_lobby, count = re.subn(
        r'"BUILD: [0-9a-zA-Z_.-]+"',
        f'"BUILD: {build_id}"',
        lobby_include.read_text(encoding="ascii"),
    )
    if count != 1:
        raise ValueError(f"Expected one build label in {lobby_include}")
    brace_errors = verify_hud_menus.validate_menu_braces(stamped_lobby, filename=lobby_include.name)
    if brace_errors:
        raise ValueError(f"Parity-stamped include {lobby_include.name} failed brace validation: {brace_errors}")
    lobby_include.write_text(stamped_lobby, encoding="ascii")

    # Mirror Base Zombies station popups under ui/scriptmenus/ with build-stamped local
    # mod.ff parity indicators so WaW 1.7 PrecacheMenu()/openMenu() resolve them cleanly
    # and show retail-visible host/client mismatch alerts without modifying tracked menus.
    scriptmenus_dir = stage_dir / "ui" / "scriptmenus"
    scriptmenus_dir.mkdir(parents=True, exist_ok=True)
    for menu_src in sorted((stage_dir / "ui").glob("bz_station_*.menu")):
        stamped = stamp_bz_station_menu_build_parity(menu_src.read_text(encoding="latin1"), build_id)
        brace_errors = verify_hud_menus.validate_menu_braces(stamped, filename=menu_src.name)
        if brace_errors:
            raise ValueError(f"Parity-stamped menu {menu_src.name} failed brace validation: {brace_errors}")
        (scriptmenus_dir / menu_src.name).write_text(stamped, encoding="latin1")

    return stage_dir


def _overlay_staged_ui_into_raw(stage_dir: Path, tools_root: Path) -> list[tuple[Path, bytes | None]]:
    """Temporarily overlay staged ui/ files onto tools_root/raw/ui/ for linker_pc.exe.

    In CoD:WaW 1.7, linker_pc.exe resolves menufile assets (and #include'd .inc files)
    from raw/ ahead of mods/<moddir>/ whenever a stock file of the same name exists in
    raw/. Overlaying staged ui/ files before linking and restoring them immediately
    afterward guarantees mod.ff compiles our patched menus while leaving raw/ untouched.
    """
    staged_ui_dir = stage_dir / "ui"
    raw_dir = tools_root / "raw"
    backups: list[tuple[Path, bytes | None]] = []
    if not staged_ui_dir.is_dir():
        return backups

    for src_path in sorted(staged_ui_dir.rglob("*")):
        if not src_path.is_file():
            continue
        rel = src_path.relative_to(stage_dir)
        dst_path = raw_dir / rel
        prior = dst_path.read_bytes() if dst_path.is_file() else None
        backups.append((dst_path, prior))
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
    return backups


def _restore_raw_ui_overlay(backups: list[tuple[Path, bytes | None]]) -> None:
    """Restore tools_root/raw/ui/ files backed up by _overlay_staged_ui_into_raw()."""
    for dst_path, prior in reversed(backups):
        if prior is not None:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            dst_path.write_bytes(prior)
        else:
            dst_path.unlink(missing_ok=True)


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
    raw_ui_backups: list[tuple[Path, bytes | None]] = []
    if zone_out.exists():
        zone_out.unlink()

    try:
        shutil.copy2(mod_csv_src, zone_csv)
        if not assetlist_csv.exists():
            assetlist_csv.write_bytes(b"")
        raw_ui_backups = _overlay_staged_ui_into_raw(stage_dir=stage_dir, tools_root=tools_root)

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
        _restore_raw_ui_overlay(raw_ui_backups)
        if prior_zone_csv is not None:
            zone_csv.write_bytes(prior_zone_csv)
        else:
            zone_csv.unlink(missing_ok=True)
        if prior_assetlist_csv is not None:
            assetlist_csv.write_bytes(prior_assetlist_csv)
        else:
            assetlist_csv.unlink(missing_ok=True)


def stage_dlc_iwd_weapon_files(
    tools_root: Path,
    steam_game: Path,
    stage_dir: Path,
) -> list[str]:
    """Copy stock DLC weapon defs missing from base main/iw_*.iwd into stage_dir/weapons/sp/.

    In CoD:WaW 1.7 with fs_game active, BG_LoadWeaponDef loads weapon files from .iwd / disk
    for DLC maps (Verruckt, Shi No Numa, Der Riese). Packing the missing stock weapons/sp/*
    text definitions into waw_gauntlet.iwd (without adding them to mod.csv) restores all DLC
    wall/box/PaP weapons while adding zero fastfile FX assets.
    """
    raw_weapons_dir = tools_root / "raw" / "weapons" / "sp"
    if not raw_weapons_dir.is_dir():
        return []

    stock_iwd_weapons: set[str] = set()
    main_dir = steam_game / "main"
    if main_dir.is_dir():
        for iwd_path in sorted(main_dir.glob("iw_*.iwd")):
            try:
                with ZipFile(iwd_path, "r") as archive:
                    for name in archive.namelist():
                        norm = name.replace("\\", "/")
                        if norm.startswith("weapons/sp/") and not norm.endswith("/"):
                            stock_iwd_weapons.add(norm[len("weapons/sp/") :].lower())
            except Exception:
                continue

    out_dir = stage_dir / "weapons" / "sp"
    out_dir.mkdir(parents=True, exist_ok=True)
    staged_relpaths: list[str] = []
    for src_path in sorted(raw_weapons_dir.iterdir()):
        if not src_path.is_file():
            continue
        if src_path.name.lower() in stock_iwd_weapons:
            continue
        dst_path = out_dir / src_path.name
        if dst_path.exists():
            continue
        shutil.copy2(src_path, dst_path)
        staged_relpaths.append(f"weapons/sp/{src_path.name}")
    return staged_relpaths


def build_iwd(stage_dir: Path) -> Path:
    """Package staged maps/*.gsc and weapons/sp/* into dist/waw_gauntlet/waw_gauntlet.iwd.

    In CoD:WaW 1.7, <map>.ff loads after mod.ff and takes precedence over mod.ff
    for rawfile (.gsc) assets that already exist inside the stock map fastfile, and
    fs_game loads DLC/mod weapon definitions from weapons/sp/* inside .iwd archives.
    Shipping waw_gauntlet.iwd alongside mod.ff (matching Treyarch's Launcher)
    ensures both stock map script overrides and all DLC/Base Zombies weapons load
    cleanly without adding fastfile FX assets.
    """
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    dist_iwd = DIST_DIR / f"{MOD_NAME}.iwd"
    gsc_files = sorted((stage_dir / "maps").rglob("*.gsc"))
    if not gsc_files:
        raise RuntimeError(f"No staged GSC files found under {stage_dir / 'maps'}")
    clientscripts_dir = stage_dir / "clientscripts"
    csc_files = sorted(clientscripts_dir.rglob("*.csc")) if clientscripts_dir.is_dir() else []
    weapons_sp_dir = stage_dir / "weapons" / "sp"
    weapon_files = (
        sorted(p for p in weapons_sp_dir.iterdir() if p.is_file())
        if weapons_sp_dir.is_dir()
        else []
    )

    with TemporaryDirectory(dir=DIST_DIR) as tmp:
        staged_iwd = Path(tmp) / dist_iwd.name
        with ZipFile(staged_iwd, "w") as archive:
            for file_path in (*gsc_files, *csc_files, *weapon_files):
                rel = file_path.relative_to(stage_dir).as_posix()
                archive.writestr(ZipInfo(rel), file_path.read_bytes(), compress_type=ZIP_DEFLATED)
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
