#!/usr/bin/env python3
"""Build and deploy the unified waw_gauntlet fastfile (mod.ff) via Treyarch's linker."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import generate_bz_weapon_models as bz_models

MOD_NAME = "waw_gauntlet"
BZ_BUILD_VERSION = "0.9.0"
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

# Explicit WaW 1.7 hitloc multipliers required when cloning non-bullet stock templates
# (gas / projectile) to weaponType=bullet. Stock non-bullet templates omit loc* keys,
# which WaW defaults to 0.0 for bullet weapons — silently zeroing both bullet hits and
# scripted DoDamage(..., player) calls (which use hitloc="none") while the weapon is held.
BZ_ELEMENT_LOC_MULTIPLIERS: dict[str, str] = {
    "locNone": "1",
    "locHelmet": "1",
    "locHead": "1",
    "locNeck": "1",
    "locTorsoUpper": "1",
    "locTorsoLower": "1",
    "locRightArmUpper": "1",
    "locRightArmLower": "1",
    "locRightHand": "1",
    "locLeftArmUpper": "1",
    "locLeftArmLower": "1",
    "locLeftHand": "1",
    "locRightLegUpper": "1",
    "locRightLegLower": "1",
    "locRightFoot": "1",
    "locLeftLegUpper": "1",
    "locLeftLegLower": "1",
    "locLeftFoot": "1",
    "locGun": "0",
}

# Canonical Phase 2 zero-FX cloned primary weapon definitions (ADR-0003).
# Each weapon clones a verified stock template at build time, enforces inventoryType=primary
# and a distinct ammoName/clipName pool, and clears any FX outside VERIFIED_ALL_4_MAP_FX.
BZ_ELEMENT_WEAPON_SPECS: tuple[tuple[str, tuple[str, ...], dict[str, str]], ...] = (
    (
        "bz_acid_sprayer",
        ("m2_flamethrower_zombie",),
        {
            **BZ_ELEMENT_LOC_MULTIPLIERS,
            "displayName": "Acid Sprayer",
            "gunModel": bz_models.CUSTOM_WEAPON_VIEWMODELS["bz_acid_sprayer"],
            "worldModel": bz_models.CUSTOM_WEAPON_WORLDMODELS["bz_acid_sprayer"],
            "inventoryType": "primary",
            "weaponType": "gas",
            "weaponClass": "gas",
            "fireType": "Full Auto",
            "flameTableFirstPerson": "bz_acid_flame_firstperson",
            "flameTableThirdPerson": "bz_acid_flame_thirdperson",
            "ammoName": "bz_acid",
            "clipName": "bz_acid",
            "clipSize": "100",
            "maxAmmo": "360",
            "startAmmo": "120",
            "dropAmmoMin": "20",
            "dropAmmoMax": "60",
            "fireTime": "0.10",
            "reloadTime": "1.2",
            "reloadEmptyTime": "1.2",
            "emptyIdleAnim": "viewmodel_flamethrower_idle",
            "reloadAnim": "viewmodel_flamethrower_reload",
            "reloadEmptyAnim": "viewmodel_flamethrower_reload",
            "damage": "15",
            "minDamage": "15",
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
            "fireSound": "",
            "fireSoundPlayer": "",
        },
    ),
    (
        "bz_cryo_cannon",
        ("tesla_gun",),
        {
            **BZ_ELEMENT_LOC_MULTIPLIERS,
            "displayName": "Cryo Cannon",
            "gunModel": bz_models.CUSTOM_WEAPON_VIEWMODELS["bz_cryo_cannon"],
            "worldModel": bz_models.CUSTOM_WEAPON_WORLDMODELS["bz_cryo_cannon"],
            "inventoryType": "primary",
            "weaponType": "bullet",
            "ammoName": "bz_cryo",
            "clipName": "bz_cryo",
            "clipSize": "8",
            "maxAmmo": "288",
            "startAmmo": "96",
            "dropAmmoMin": "8",
            "dropAmmoMax": "32",
            "fireTime": "0.55",
            "damage": "1",
            "minDamage": "1",
            "explosionInnerDamage": "0",
            "explosionOuterDamage": "0",
            "explosionRadius": "0",
            "altWeapon": "",
            "fireSound": "",
            "fireSoundPlayer": "",
        },
    ),
    (
        "bz_multi_crossbow",
        ("fg42_scoped",),
        {
            **BZ_ELEMENT_LOC_MULTIPLIERS,
            "displayName": "Multi-Crossbow",
            "gunModel": bz_models.CUSTOM_WEAPON_VIEWMODELS["bz_multi_crossbow"],
            "worldModel": bz_models.CUSTOM_WEAPON_WORLDMODELS["bz_multi_crossbow"],
            "inventoryType": "primary",
            "weaponType": "bullet",
            "weaponClass": "rifle",
            "fireType": "Single Shot",
            "ammoName": "bz_xbow",
            "clipName": "bz_xbow",
            "clipSize": "6",
            "maxAmmo": "108",
            "startAmmo": "36",
            "dropAmmoMin": "6",
            "dropAmmoMax": "18",
            "fireTime": "0.52",
            "reloadTime": "2.0",
            "reloadEmptyTime": "2.4",
            "adsZoomFov": "32",
            "damage": "1",
            "minDamage": "1",
            "explosionInnerDamage": "0",
            "explosionOuterDamage": "0",
            "explosionRadius": "0",
            "altWeapon": "",
            "fireSound": "gr_kar98_bolt_front_plr",
            "fireSoundPlayer": "gr_kar98_bolt_front_plr",
        },
    ),
    (
        "bz_blade_boomerang",
        ("zombie_colt", "colt"),
        {
            **BZ_ELEMENT_LOC_MULTIPLIERS,
            "displayName": "Blade Boomerang",
            "gunModel": bz_models.CUSTOM_WEAPON_VIEWMODELS["bz_blade_boomerang"],
            "worldModel": bz_models.CUSTOM_WEAPON_WORLDMODELS["bz_blade_boomerang"],
            "inventoryType": "primary",
            "weaponType": "bullet",
            "weaponClass": "rifle",
            "shotCount": "1",
            "fireType": "Single Shot",
            "ammoName": "bz_blade",
            "clipName": "bz_blade",
            "clipSize": "1",
            "maxAmmo": "0",
            "startAmmo": "0",
            "dropAmmoMin": "0",
            "dropAmmoMax": "0",
            "moveSpeedScale": "1",
            "fireTime": "1.15",
            "reloadTime": "0.25",
            "reloadEmptyTime": "0.25",
            "cancelAutoHolsterWhenEmpty": "1",
            "idleAnim": "viewmodel_ray_gun_idle",
            "fireAnim": "viewmodel_germangrenade_throw",
            "lastShotAnim": "viewmodel_germangrenade_throw",
            "emptyIdleAnim": "viewmodel_ray_gun_drop",
            "raiseAnim": "viewmodel_ray_gun_raise",
            "firstRaiseAnim": "viewmodel_ray_gun_raise",
            "dropAnim": "viewmodel_ray_gun_drop",
            "reloadAnim": "viewmodel_ray_gun_raise",
            "reloadEmptyAnim": "viewmodel_ray_gun_raise",
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
            "fireSound": "foley_throw",
            "fireSoundPlayer": "foley_throw",
        },
    ),
)

# Special item-slot weapons (inventoryType = "item", excluded from primary weapon slots & PaP — ADR-0006).
BZ_SPECIAL_ITEM_WEAPON_SPECS: tuple[tuple[str, tuple[str, ...], dict[str, str]], ...] = (
    (
        "bz_portal_grenade",
        ("zombie_colt", "colt"),
        {
            **BZ_ELEMENT_LOC_MULTIPLIERS,
            "displayName": "Portal Grenade",
            "gunModel": bz_models.CUSTOM_SPECIAL_WEAPON_VIEWMODELS["bz_portal_grenade"],
            "worldModel": bz_models.CUSTOM_SPECIAL_WEAPON_WORLDMODELS["bz_portal_grenade"],
            "inventoryType": "item",
            "weaponType": "bullet",
            "weaponClass": "rifle",
            "shotCount": "1",
            "fireType": "Single Shot",
            "ammoName": "bz_portal",
            "clipName": "bz_portal",
            "clipSize": "2",
            "maxAmmo": "0",
            "startAmmo": "0",
            "dropAmmoMin": "0",
            "dropAmmoMax": "0",
            "moveSpeedScale": "1",
            "fireTime": "0.85",
            "reloadTime": "0.25",
            "reloadEmptyTime": "0.25",
            "cancelAutoHolsterWhenEmpty": "1",
            "idleAnim": "viewmodel_ray_gun_idle",
            "fireAnim": "viewmodel_germangrenade_throw",
            "lastShotAnim": "viewmodel_germangrenade_throw",
            "emptyIdleAnim": "viewmodel_ray_gun_drop",
            "raiseAnim": "viewmodel_ray_gun_raise",
            "firstRaiseAnim": "viewmodel_ray_gun_raise",
            "dropAnim": "viewmodel_ray_gun_drop",
            "reloadAnim": "viewmodel_ray_gun_raise",
            "reloadEmptyAnim": "viewmodel_ray_gun_raise",
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
            "fireSound": "foley_throw",
            "fireSoundPlayer": "foley_throw",
        },
    ),
    (
        "bz_war_club",
        ("zombie_colt", "colt"),
        {
            **BZ_ELEMENT_LOC_MULTIPLIERS,
            "displayName": "War Club",
            "gunModel": bz_models.CUSTOM_SPECIAL_WEAPON_VIEWMODELS["bz_war_club"],
            "worldModel": bz_models.CUSTOM_SPECIAL_WEAPON_WORLDMODELS["bz_war_club"],
            "inventoryType": "item",
            "weaponType": "bullet",
            "weaponClass": "rifle",
            "shotCount": "1",
            "fireType": "Single Shot",
            "ammoName": "bz_war_club",
            "clipName": "bz_war_club",
            "clipSize": "1",
            "maxAmmo": "0",
            "startAmmo": "0",
            "dropAmmoMin": "0",
            "dropAmmoMax": "0",
            "moveSpeedScale": "1",
            "fireTime": "0.45",
            "reloadTime": "0.25",
            "reloadEmptyTime": "0.25",
            "cancelAutoHolsterWhenEmpty": "1",
            "idleAnim": "viewmodel_ray_gun_idle",
            "fireAnim": "viewmodel_colt45_melee2",
            "lastShotAnim": "viewmodel_colt45_melee2",
            "emptyIdleAnim": "viewmodel_ray_gun_idle",
            "raiseAnim": "viewmodel_colt45_melee1",
            "firstRaiseAnim": "viewmodel_colt45_melee1",
            "quickRaiseAnim": "viewmodel_colt45_melee1",
            "dropAnim": "viewmodel_ray_gun_drop",
            "quickDropAnim": "viewmodel_ray_gun_drop",
            "meleeAnim": "viewmodel_colt45_melee1",
            "meleeChargeAnim": "viewmodel_colt45_melee2",
            "reloadAnim": "viewmodel_ray_gun_raise",
            "reloadEmptyAnim": "viewmodel_ray_gun_raise",
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
            "fireSound": "attack_whoosh",
            "fireSoundPlayer": "attack_whoosh",
        },
    ),
    (
        "bz_pap_knife",
        ("zombie_colt", "colt"),
        {
            **BZ_ELEMENT_LOC_MULTIPLIERS,
            "displayName": "PaP Combat Knife",
            "gunModel": bz_models.CUSTOM_SPECIAL_WEAPON_VIEWMODELS["bz_pap_knife"],
            "worldModel": bz_models.CUSTOM_SPECIAL_WEAPON_WORLDMODELS["bz_pap_knife"],
            "inventoryType": "item",
            "weaponType": "bullet",
            "weaponClass": "rifle",
            "shotCount": "1",
            "fireType": "Single Shot",
            "ammoName": "bz_pap_knife",
            "clipName": "bz_pap_knife",
            "clipSize": "1",
            "maxAmmo": "0",
            "startAmmo": "0",
            "dropAmmoMin": "0",
            "dropAmmoMax": "0",
            "moveSpeedScale": "1",
            "fireTime": "0.42",
            "reloadTime": "0.25",
            "reloadEmptyTime": "0.25",
            "cancelAutoHolsterWhenEmpty": "1",
            "idleAnim": "viewmodel_ray_gun_idle",
            "fireAnim": "viewmodel_colt45_melee2",
            "lastShotAnim": "viewmodel_colt45_melee2",
            "emptyIdleAnim": "viewmodel_ray_gun_idle",
            "raiseAnim": "viewmodel_colt45_melee1",
            "firstRaiseAnim": "viewmodel_colt45_melee1",
            "quickRaiseAnim": "viewmodel_colt45_melee1",
            "dropAnim": "viewmodel_ray_gun_drop",
            "quickDropAnim": "viewmodel_ray_gun_drop",
            "meleeAnim": "viewmodel_colt45_melee1",
            "meleeChargeAnim": "viewmodel_colt45_melee2",
            "reloadAnim": "viewmodel_ray_gun_raise",
            "reloadEmptyAnim": "viewmodel_ray_gun_raise",
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
            "fireSound": "attack_whoosh",
            "fireSoundPlayer": "attack_whoosh",
        },
    ),
    (
        "bz_pap_bowie",
        ("zombie_colt", "colt"),
        {
            **BZ_ELEMENT_LOC_MULTIPLIERS,
            "displayName": "PaP Bowie Knife",
            "gunModel": bz_models.CUSTOM_SPECIAL_WEAPON_VIEWMODELS["bz_pap_bowie"],
            "worldModel": bz_models.CUSTOM_SPECIAL_WEAPON_WORLDMODELS["bz_pap_bowie"],
            "inventoryType": "item",
            "weaponType": "bullet",
            "weaponClass": "rifle",
            "shotCount": "1",
            "fireType": "Single Shot",
            "ammoName": "bz_pap_bowie",
            "clipName": "bz_pap_bowie",
            "clipSize": "1",
            "maxAmmo": "0",
            "startAmmo": "0",
            "dropAmmoMin": "0",
            "dropAmmoMax": "0",
            "moveSpeedScale": "1",
            "fireTime": "0.45",
            "reloadTime": "0.25",
            "reloadEmptyTime": "0.25",
            "cancelAutoHolsterWhenEmpty": "1",
            "idleAnim": "viewmodel_ray_gun_idle",
            "fireAnim": "viewmodel_colt45_melee2",
            "lastShotAnim": "viewmodel_colt45_melee2",
            "emptyIdleAnim": "viewmodel_ray_gun_idle",
            "raiseAnim": "viewmodel_colt45_melee1",
            "firstRaiseAnim": "viewmodel_colt45_melee1",
            "quickRaiseAnim": "viewmodel_colt45_melee1",
            "dropAnim": "viewmodel_ray_gun_drop",
            "quickDropAnim": "viewmodel_ray_gun_drop",
            "meleeAnim": "viewmodel_colt45_melee1",
            "meleeChargeAnim": "viewmodel_colt45_melee2",
            "reloadAnim": "viewmodel_ray_gun_raise",
            "reloadEmptyAnim": "viewmodel_ray_gun_raise",
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
            "fireSound": "attack_whoosh",
            "fireSoundPlayer": "attack_whoosh",
        },
    ),
)

# Offhand Arsenal upgrade weapons (zero added FX — ADR-0007 / NSV-W2).
BZ_OFFHAND_WEAPON_SPECS: tuple[tuple[str, tuple[str, ...], dict[str, str]], ...] = (
    (
        "bz_pap_cluster_grenade",
        ("stielhandgranate", "fraggrenade"),
        {
            "displayName": "PaP Cluster Grenade",
            "gunModel": bz_models.CUSTOM_OFFHAND_WEAPON_VIEWMODELS["bz_pap_cluster_grenade"],
            "worldModel": bz_models.CUSTOM_OFFHAND_WEAPON_WORLDMODELS["bz_pap_cluster_grenade"],
            "projectileModel": bz_models.CUSTOM_OFFHAND_WEAPON_WORLDMODELS["bz_pap_cluster_grenade"],
            "inventoryType": "offhand",
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


def zombiemode_spawner_module_for_map(map_name: str) -> str:
    """Return the per-map hooked _zombiemode_spawner script stem (without .gsc)."""
    slug = STOCK_MAP_SLUGS.get(map_name)
    if slug is None:
        raise ValueError(f"Unsupported stock Nazi Zombies map: {map_name!r}")
    return f"_zombiemode_spawner_bz_{slug}"


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
    rewire_spawner_module: str | None = None,
) -> str:
    if rewire_weapons_module:
        text = text.replace("maps\\_zombiemode_weapons_sumpf::", f"maps\\{rewire_weapons_module}::")
        text = text.replace("maps\\_zombiemode_weapons::", f"maps\\{rewire_weapons_module}::")
    if rewire_perks_module:
        text = text.replace("maps\\_zombiemode_perks::", f"maps\\{rewire_perks_module}::")
    if rewire_dogs_module:
        text = text.replace("maps\\_zombiemode_dogs::", f"maps\\{rewire_dogs_module}::")
    if rewire_powerups_module:
        text = text.replace("maps\\_zombiemode_powerups::", f"maps\\{rewire_powerups_module}::")
    if rewire_spawner_module:
        text = text.replace("maps\\_zombiemode_spawner::", f"maps\\{rewire_spawner_module}::")
    return text


def inject_map_hooks(
    script_bytes: bytes,
    map_name: str,
    *,
    rewire_weapons_module: str | None = None,
    rewire_perks_module: str | None = None,
    rewire_dogs_module: str | None = None,
    rewire_powerups_module: str | None = None,
    rewire_spawner_module: str | None = None,
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
    powerups_flag_hook = ""
    if rewire_powerups_module:
        powerups_flag_hook = (
            f"{indent}level.bz_powerup_drop_fn = maps\\{rewire_powerups_module}::powerup_drop;{newline}"
            f"{indent}if ( maps\\_bz_hooks::bz_enabled() ) {{ level.bz_powerups_hooked = true; }}{newline}"
        )
    p2_powerup_hook = ""
    if map_name == "nazi_zombie_factory" and rewire_powerups_module:
        p2_powerup_hook = (
            f'{indent}if ( maps\\_bz_hooks::bz_enabled() && GetDvarInt( "bz_test_p2_selftest" ) == 1 ) '
            f"{{ level.bz_test_full_ammo_powerup = maps\\{rewire_powerups_module}::full_ammo_powerup; }}{newline}"
        )
    replacement = (
        f"{indent}{PRE_HOOK_CALL}{newline}"
        f"{indent}{BZ_PRE_HOOK_CALL}{newline}"
        f"{coop_dog_hook}"
        f"{powerups_flag_hook}"
        f"{p2_powerup_hook}"
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
        rewire_spawner_module=rewire_spawner_module,
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
    rewire_spawner_module: str | None = None,
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
        rewire_spawner_module=rewire_spawner_module,
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
                f"{m.group('ent')}.bz_last_box_cost = maps\\_bz_hooks::bz_box_cost_modify( {m.group('ent')}, {m.group('cost')} ); "
                f"{m.group('ent')} maps\\_zombiemode_score::minus_to_player_score( {m.group('ent')}.bz_last_box_cost )"
            ),
            chest_body,
        )
        text = text[: chest_match.start()] + chest_body + text[chest_end:]

    # Refund the actual box cost paid on teddy bear inside treasure_chest_weapon_spawn()
    # without passing through bz_points_modify (prevents Broker from netting +1,425 pts).
    bear_refund_re = re.compile(
        r"^(?P<indent>[ \t]*)(?P<ent>[A-Za-z_][A-Za-z0-9_]*)[ \t]+maps\\_zombiemode_score::add_to_player_score\([ \t]*950[ \t]*\);(?P<trailing>[ \t]*)\r?$",
        re.MULTILINE | re.IGNORECASE,
    )

    def _patch_bear_refund(m: re.Match[str]) -> str:
        indent = m.group("indent")
        ent = m.group("ent")
        orig = m.group(0).rstrip("\r")
        ending = "\r" if m.group(0).endswith("\r") else ""
        return (
            f"{indent}if ( maps\\_bz_hooks::bz_enabled() ){newline}"
            f"{indent}{{{newline}"
            f"{indent}\tif ( !IsDefined( level.intermission ) || !level.intermission ){newline}"
            f"{indent}\t{{{newline}"
            f"{indent}\t\tbz_refund = maps\\_bz_hooks::bz_box_cost_modify( {ent}, 950 );{newline}"
            f"{indent}\t\tif ( IsDefined( {ent}.bz_last_box_cost ) && Int( {ent}.bz_last_box_cost ) > 0 ){newline}"
            f"{indent}\t\t{{{newline}"
            f"{indent}\t\t\tbz_refund = Int( {ent}.bz_last_box_cost );{newline}"
            f"{indent}\t\t}}{newline}"
            f"{indent}\t\t{ent}.bz_last_box_cost = undefined;{newline}"
            f"{indent}\t\t{ent}.score += bz_refund;{newline}"
            f"{indent}\t\t{ent}.score_total += bz_refund;{newline}"
            f"{indent}\t\t{ent} maps\\_zombiemode_score::set_player_score_hud();{newline}"
            f"{indent}\t}}{newline}"
            f"{indent}}}{newline}"
            f"{indent}else{newline}"
            f"{indent}{{{newline}"
            f"{indent}\t{orig.lstrip()}{newline}"
            f"{indent}}}{ending}"
        )

    text = bear_refund_re.sub(_patch_bear_refund, text)

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

    # Normalize weapon reserves in ammo_give(), weapon_give(), and treasure_chest_give_weapon()
    # so build-staged 3x maxAmmo stock weapons clamp strictly to 1x in Classic Mode and
    # use true 1x/1.5x/2x/3x caps in Base Zombies (ADR-0005, fixes wall-buy ammo lockout).
    ammo_give_match = re.search(r"^ammo_give\([^)]*\)[ \t]*\r?\n\{", text, re.MULTILINE | re.IGNORECASE)
    if ammo_give_match is not None:
        next_fn = TOP_LEVEL_FUNC_DEF_RE.search(text, pos=ammo_give_match.end())
        ag_end = next_fn.start() if next_fn is not None else len(text)
        ag_body = text[ammo_give_match.start() : ag_end]
        ag_body = re.sub(
            r"stockMax\s*=\s*WeaponMaxAmmo\s*\(\s*weapon\s*\)\s*;",
            "stockMax = maps\\_bz_hooks::bz_get_effective_max_stock( self, weapon );",
            ag_body,
            flags=re.IGNORECASE,
        )
        ag_body = re.sub(
            r'stockMax\s*\+=\s*WeaponMaxAmmo\s*\(\s*weapon\s*\+\s*"_upgraded"\s*\)\s*;',
            'stockMax += maps\\_bz_hooks::bz_get_effective_max_stock( self, weapon+"_upgraded" );',
            ag_body,
            flags=re.IGNORECASE,
        )

        def _inject_after_give_max(match: re.Match[str]) -> str:
            indent = match.group("indent")
            ent = match.group("ent")
            weap = match.group("weap").strip()
            orig = match.group(0).rstrip("\r")
            ending = "\r" if match.group(0).endswith("\r") else ""
            return (
                f"{orig}{newline}"
                f"{indent}maps\\_bz_hooks::bz_normalize_weapon_stock( {ent}, {weap} );{ending}"
            )

        ag_body = PAP_TAKE_GIVE_MAX_AMMO_RE.sub(_inject_after_give_max, ag_body)
        text = text[: ammo_give_match.start()] + ag_body + text[ag_end:]

    weap_give_match = re.search(r"^weapon_give\([^)]*\)[ \t]*\r?\n\{", text, re.MULTILINE | re.IGNORECASE)
    if weap_give_match is not None:
        next_fn = TOP_LEVEL_FUNC_DEF_RE.search(text, pos=weap_give_match.end())
        wg_end = next_fn.start() if next_fn is not None else len(text)
        wg_body = text[weap_give_match.start() : wg_end]

        def _inject_wg_norm(match: re.Match[str]) -> str:
            indent = match.group("indent")
            ent = match.group("ent")
            weap = match.group("weap").strip()
            orig = match.group(0).rstrip("\r")
            ending = "\r" if match.group(0).endswith("\r") else ""
            return (
                f"{orig}{newline}"
                f"{indent}maps\\_bz_hooks::bz_normalize_weapon_stock( {ent}, {weap} );{ending}"
            )

        wg_body = PAP_TAKE_GIVE_MAX_AMMO_RE.sub(_inject_wg_norm, wg_body)
        text = text[: weap_give_match.start()] + wg_body + text[wg_end:]

    box_give_match = re.search(r"^treasure_chest_give_weapon\([^)]*\)[ \t]*\r?\n\{", text, re.MULTILINE)
    if box_give_match is not None:
        next_fn = TOP_LEVEL_FUNC_DEF_RE.search(text, pos=box_give_match.end())
        box_give_end = next_fn.start() if next_fn is not None else len(text)
        box_give_body = text[box_give_match.start() : box_give_end]

        def _inject_box_element_ammo(match: re.Match[str]) -> str:
            indent = match.group("indent")
            ent = match.group("ent")
            weap = match.group("weap").strip()
            orig = match.group(0).rstrip("\r")
            ending = "\r" if match.group(0).endswith("\r") else ""
            return (
                f"{orig}{newline}"
                f"{indent}maps\\_bz_hooks::bz_normalize_weapon_stock( {ent}, {weap} );{newline}"
                f"{indent}if ( maps\\_bz_hooks::bz_elements_enabled() ) "
                f"{{ maps\\_bz_stations::bz_stations_normalize_box_element_ammo( {ent}, {weap} ); }}{ending}"
            )

        box_give_body = PAP_TAKE_GIVE_MAX_AMMO_RE.sub(_inject_box_element_ammo, box_give_body)
        text = text[: box_give_match.start()] + box_give_body + text[box_give_end:]

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
                    f"{indent}maps\\_bz_hooks::bz_normalize_weapon_stock( {ent}, {weap} );{newline}"
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


FULL_AMMO_POWERUP_DEF_RE = re.compile(
    r"^[ \t]*full_ammo_powerup\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)


def _find_matching_close_brace(text: str, open_brace_idx: int) -> int:
    """Return index of the matching '}' for text[open_brace_idx] == '{', skipping comments/strings."""
    depth = 0
    i = open_brace_idx
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            nl = text.find("\n", i + 2)
            i = n if nl == -1 else nl + 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            if end == -1:
                break
            i = end + 2
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def inject_zombiemode_powerups_hooks(
    script_bytes: bytes,
    *,
    rewire_weapons_module: str | None = None,
    rewire_dogs_module: str | None = None,
    rewire_powerups_module: str | None = None,
) -> bytes:
    """Patch stock maps/_zombiemode_powerups.gsc so full_ammo_powerup notifies Base Zombies directly."""
    text = script_bytes.decode("latin1")
    newline = "\r\n" if "\r\n" in text else "\n"
    match = FULL_AMMO_POWERUP_DEF_RE.search(text)
    if match is None:
        raise ValueError("Could not locate full_ammo_powerup() in _zombiemode_powerups.gsc")
    close_idx = _find_matching_close_brace(text, match.end() - 1)
    if close_idx == -1:
        raise ValueError("Could not locate closing brace of full_ammo_powerup() in _zombiemode_powerups.gsc")

    hook = (
        f"{newline}"
        f"\tmaps\\_bz_hooks::bz_normalize_all_player_stocks();{newline}"
        f"\tif ( maps\\_bz_hooks::bz_enabled() ){newline}"
        f"\t{{{newline}"
        f"\t\tmaps\\_bz_hooks::bz_notify_all_players_max_ammo();{newline}"
        f"\t}}{newline}"
    )
    text = text[:close_idx] + hook + text[close_idx:]
    text = _rewire_stock_module_refs(
        text,
        rewire_weapons_module=rewire_weapons_module,
        rewire_dogs_module=rewire_dogs_module,
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
        f"{all_indent}\tmaps\\_bz_hooks::bz_recompute_player_max_health( self );{newline}"
        f"{all_indent}\tself.health = self.maxhealth;{newline}"
        f"{all_indent}\tmaps\\_bz_perks::bz_perks_apply_revive_completed( self, self );{newline}"
        f"{all_indent}\treturn;{newline}"
        f"{all_indent}}}{newline}"
        f"{all_match.group(0)}"
    )
    text = text[: all_match.start()] + solo_hook + text[all_match.end() :]

    # 4. Exit revive_trigger_think() cleanly once Gauntlet Stage Clear deletes revivetrigger
    #    without aborting an active reviver mid-revive (so revive_do_revive unwinds cleanly
    #    and revive_give_back_weapons() still removes the syrette and restores weapon cycling).
    rt_def_re = re.compile(r"^revive_trigger_think[ \t]*\([ \t]*\)[ \t]*\r?\n\{", re.MULTILINE | re.IGNORECASE)
    rt_match = rt_def_re.search(text)
    if rt_match is None:
        raise ValueError("Could not locate revive_trigger_think() in _laststand.gsc")
    rt_next = TOP_LEVEL_FUNC_DEF_RE.search(text, pos=rt_match.end())
    rt_end = rt_next.start() if rt_next is not None else len(text)
    rt_body = text[rt_match.start() : rt_end]
    hint_clear_re = re.compile(
        r'^(?P<indent>[ \t]*)self\.revivetrigger[ \t]+setHintString[ \t]*\([ \t]*""[ \t]*\);(?P<trailing>[ \t]*)\r?$',
        re.MULTILINE | re.IGNORECASE,
    )
    h_match = hint_clear_re.search(rt_body)
    if h_match is None:
        raise ValueError("Could not locate self.revivetrigger setHintString(\"\") in revive_trigger_think()")
    h_indent = h_match.group("indent")
    h_orig = h_match.group(0).rstrip("\r")
    h_ending = "\r" if h_match.group(0).endswith("\r") else ""
    h_hook = f"{h_indent}if ( !IsDefined( self.revivetrigger ) ) {{ return; }}{newline}{h_orig}{h_ending}"
    rt_body = rt_body[: h_match.start()] + h_hook + rt_body[h_match.end() :]
    text = text[: rt_match.start()] + rt_body + text[rt_end:]

    # 5. Guard revive_do_revive() post-loop cleanup so deleting revivetrigger during an active
    #    revive (e.g. Gauntlet Stage Clear) never dereferences a deleted trigger before returning
    #    false to the caller's revive_give_back_weapons() cleanup.
    do_rev_re = re.compile(r"^revive_do_revive[ \t]*\([^)]*\)[ \t]*\r?\n\{", re.MULTILINE | re.IGNORECASE)
    do_match = do_rev_re.search(text)
    if do_match is None:
        raise ValueError("Could not locate revive_do_revive() in _laststand.gsc")
    do_next = TOP_LEVEL_FUNC_DEF_RE.search(text, pos=do_match.end())
    do_end = do_next.start() if do_next is not None else len(text)
    do_body = text[do_match.start() : do_end]
    not_revived_re = re.compile(
        r"^(?P<indent>[ \t]*)if[ \t]*\([ \t]*!revived[ \t]*\)(?P<trailing>[ \t]*)\r?$",
        re.MULTILINE | re.IGNORECASE,
    )
    nr_match = not_revived_re.search(do_body)
    if nr_match is None:
        raise ValueError("Could not locate if ( !revived ) cleanup in revive_do_revive()")
    nr_indent = nr_match.group("indent")
    nr_orig = nr_match.group(0).rstrip("\r")
    nr_ending = "\r" if nr_match.group(0).endswith("\r") else ""
    nr_hook = (
        f"{nr_indent}if ( !IsDefined( playerBeingRevived ) || !IsDefined( playerBeingRevived.revivetrigger ) ){newline}"
        f"{nr_indent}{{{newline}"
        f"{nr_indent}\treturn false;{newline}"
        f"{nr_indent}}}{newline}"
        f"{nr_orig}{nr_ending}"
    )
    do_body = do_body[: nr_match.start()] + nr_hook + do_body[nr_match.end() :]
    text = text[: do_match.start()] + do_body + text[do_end:]

    # 6. Strip excess Mule Kick weapons AFTER stock revive_success() gives back saved weapons.
    giveback_re = re.compile(
        r"^(?P<indent>[ \t]*)self[ \t]+laststand_giveback_player_weapons\([ \t]*\);(?P<trailing>[ \t]*)\r?$",
        re.MULTILINE | re.IGNORECASE,
    )
    gb_match = giveback_re.search(text)
    if gb_match is None:
        raise ValueError("Could not locate self laststand_giveback_player_weapons(); in _laststand.gsc")
    gb_indent = gb_match.group("indent")
    gb_orig = gb_match.group(0).rstrip("\r")
    gb_ending = "\r" if gb_match.group(0).endswith("\r") else ""
    gb_hook = (
        f"{gb_orig}{newline}"
        f"{gb_indent}if ( maps\\_bz_hooks::bz_enabled() ){newline}"
        f"{gb_indent}{{{newline}"
        f"{gb_indent}\tmaps\\_bz_perks::bz_perks_on_player_revived( self, reviver );{newline}"
        f"{gb_indent}}}{gb_ending}"
    )
    text = text[: gb_match.start()] + gb_hook + text[gb_match.end() :]

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

    # 4. Route Wunderwaffe chain-kill powerup drops through the active map's
    #    patched powerups module (bound to level.bz_powerup_drop_fn by inject_map_hooks)
    #    so Max Ammo drops on Shi No Numa and Der Riese never bypass the Portal
    #    Grenade refill hook while staying stock-identical in Classic Mode.
    text = re.sub(
        r"^(?P<indent>[ \t]*)level\s+thread\s+maps\\_zombiemode_powerups::powerup_drop\(\s*(?P<args>[^)]+?)\s*\)\s*;",
        (
            rf"\g<indent>if ( IsDefined( level.bz_powerup_drop_fn ) ){newline}"
            rf"\g<indent>{{{newline}"
            rf"\g<indent>\tlevel thread [[ level.bz_powerup_drop_fn ]]( \g<args> );{newline}"
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

    # Align build parity footer directly beneath each station menu's panel border
    footer_rect = "28 456 584 14"
    if '"bz_station_pap"' in menu_text:
        footer_rect = "86 404 468 14"
    elif '"bz_station_class"' in menu_text:
        footer_rect = "38 452 564 14"
    elif '"bz_station_arsenal"' in menu_text:
        footer_rect = "34 465 572 14"

    snippet = (
        f"{newline}"
        f"\t\t// Build-stamped local mod.ff fingerprint & retail-visible host parity alert{newline}"
        f"\t\titemDef{newline}"
        f"\t\t{{{newline}"
        f'\t\t\tname\t\t\t"bz_parity_ok"{newline}'
        f"\t\t\ttype\t\t\tITEM_TYPE_TEXT{newline}"
        f"\t\t\trect\t\t\t{footer_rect}{newline}"
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
        f"\t\t\trect\t\t\t{footer_rect}{newline}"
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


ACID_FLAMETABLE_DEFAULT_FIELDS: tuple[tuple[str, str], ...] = (
    ("fire", "mtl_bz_acid_billow"),
    ("smoke", "mtl_bz_acid_mist"),
    ("heat", ""),
    ("drips", "mtl_bz_acid_drips"),
    ("streamFuel", "mtl_bz_acid_stream"),
    ("streamFlames", "mtl_bz_acid_billow"),
    ("streamFuel2", "mtl_bz_acid_stream"),
    ("streamFlames2", "mtl_bz_acid_billow"),
    ("flameOffLoopSound", ""),
    ("flameIgniteSound", "weap_flamethrower_start"),
    ("flameOnLoopSound", "weap_flamethrower_fireloop"),
    ("flameCooldownSound", "weap_flamethrower_cooldown"),
    ("flameVar_streamChunkGravityStart", "250"),
    ("flameVar_streamChunkGravityEnd", "200"),
    ("flameVar_streamChunkMaxSize", "96"),
    ("flameVar_streamChunkStartSize", "10"),
    ("flameVar_streamChunkEndSize", "96"),
    ("flameVar_streamChunkSpeed", "1050"),
    ("flameVar_streamChunkDuration", "1.45"),
    ("flameVar_streamFuelSizeStart", "3"),
    ("flameVar_streamFuelSizeEnd", "16"),
    ("flameVar_streamFuelLength", "320"),
    ("flameVar_streamFuelNumSegments", "60"),
    ("flameVar_streamFlameSizeStart", "3"),
    ("flameVar_streamFlameSizeEnd", "15"),
    ("flameVar_streamFlameLength", "280"),
    ("flameVar_streamFlameNumSegments", "60"),
    ("flameVar_streamPrimaryLightRadius", "320"),
    ("flameVar_streamPrimaryLightRadiusFlutter", "80"),
    ("flameVar_streamPrimaryLightR", "0.10"),
    ("flameVar_streamPrimaryLightG", "0.95"),
    ("flameVar_streamPrimaryLightB", "0.15"),
    ("flameVar_dripsGravity", "360"),
    ("flameVar_dripsGravityEnd", "440"),
)

ACID_FLAMETABLE_OVERRIDES: dict[str, str] = {
    "fire": "mtl_bz_acid_billow",
    "smoke": "mtl_bz_acid_mist",
    "heat": "",
    "drips": "mtl_bz_acid_drips",
    "streamFuel": "mtl_bz_acid_stream",
    "streamFlames": "mtl_bz_acid_billow",
    "streamFuel2": "mtl_bz_acid_stream",
    "streamFlames2": "mtl_bz_acid_billow",
    "flameVar_streamChunkSpeed": "1050",
    "flameVar_streamFuelLength": "320",
    "flameVar_streamFlameLength": "280",
    "flameVar_streamPrimaryLightR": "0.10",
    "flameVar_streamPrimaryLightG": "0.95",
    "flameVar_streamPrimaryLightB": "0.15",
    "flameVar_dripsGravity": "360",
    "flameVar_dripsGravityEnd": "440",
}


def build_acid_flametable_text(stock_text: str | None, table_name: str, is_third_person: bool = False) -> str:
    """Build a WaW FLAMETABLEFILE with toxic-green 2D effect materials & green dynamic light (0 FX)."""
    pairs: list[tuple[str, str]] = []
    if stock_text and stock_text.startswith("FLAMETABLEFILE\\"):
        tokens = stock_text.strip().split("\\")[1:]
        for i in range(0, len(tokens) - 1, 2):
            pairs.append((tokens[i], tokens[i + 1]))
    else:
        pairs.append(("name", table_name))
        pairs.extend(ACID_FLAMETABLE_DEFAULT_FIELDS)

    overrides = dict(ACID_FLAMETABLE_OVERRIDES)
    overrides["name"] = table_name
    if is_third_person and not stock_text:
        overrides["flameIgniteSound"] = "weap_flamethrower_start_3p"
        overrides["flameOnLoopSound"] = "weap_flamethrower_fireloop_3p"
        overrides["flameCooldownSound"] = "weap_flamethrower_cooldown_3p"

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for k, v in pairs:
        if k in overrides:
            out.append((k, overrides[k]))
        else:
            out.append((k, v))
        seen.add(k)
    for k, v in overrides.items():
        if k not in seen:
            out.append((k, v))
    flat = ["FLAMETABLEFILE"]
    for k, v in out:
        flat.extend((k, v))
    return "\\".join(flat)


def stage_bz_element_weapons(
    tools_root: Path,
    stage_dir: Path,
    allowed_fx_set: set[str] | frozenset[str] | None = None,
) -> list[str]:
    """Generate and stage the 4 zero-FX cloned Phase 2 primary weapons (plus Acid flametables) under stage_dir/weapons/sp/.

    Returns the relative paths (e.g. `weapons/sp/bz_acid_sprayer`) staged. Returns an empty list
    if stock weapon templates are not present under `tools_root/raw/weapons/sp/`.
    """
    raw_weapons_dir = tools_root / "raw" / "weapons" / "sp"
    if not raw_weapons_dir.is_dir():
        return []

    raw_xanim_dir = tools_root / "raw" / "xanim"
    xanim_case_map = build_xanim_case_map(raw_xanim_dir) if raw_xanim_dir.is_dir() else None

    out_dir = stage_dir / "weapons" / "sp"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Stage custom toxic-green FLAMETABLEFILEs for bz_acid_sprayer (0 added FX slots — ADR-0004).
    for ft_name, stock_ft, is_3p in (
        ("bz_acid_flame_firstperson", "quinn_flame_firstperson", False),
        ("bz_acid_flame_thirdperson", "quinn_flame_thirdperson", True),
    ):
        stock_ft_path = raw_weapons_dir / stock_ft
        stock_ft_text = stock_ft_path.read_text(encoding="latin1") if stock_ft_path.is_file() else None
        ft_text = build_acid_flametable_text(stock_ft_text, ft_name, is_third_person=is_3p)
        (out_dir / ft_name).write_text(ft_text, encoding="latin1")

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
        out_path = out_dir / weap_name
        out_path.write_text(cloned_text, encoding="latin1")
        staged_relpaths.append(f"weapons/sp/{weap_name}")

    return staged_relpaths


def stage_bz_special_item_weapons(
    tools_root: Path,
    stage_dir: Path,
    allowed_fx_set: set[str] | frozenset[str] | None = None,
) -> list[str]:
    """Generate and stage zero-FX item-slot Special Weapons (Portal Grenade, War Club) under stage_dir/weapons/sp/."""
    raw_weapons_dir = tools_root / "raw" / "weapons" / "sp"
    if not raw_weapons_dir.is_dir():
        return []

    raw_xanim_dir = tools_root / "raw" / "xanim"
    xanim_case_map = build_xanim_case_map(raw_xanim_dir) if raw_xanim_dir.is_dir() else None

    out_dir = stage_dir / "weapons" / "sp"
    out_dir.mkdir(parents=True, exist_ok=True)

    staged_items: list[str] = []
    for weap_name, template_candidates, overrides in BZ_SPECIAL_ITEM_WEAPON_SPECS:
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
        (out_dir / weap_name).write_text(cloned_text, encoding="latin1")
        staged_items.append(f"weapons/sp/{weap_name}")
    return staged_items


def stage_bz_offhand_weapons(
    tools_root: Path,
    stage_dir: Path,
    allowed_fx_set: set[str] | frozenset[str] | None = None,
) -> list[str]:
    """Generate and stage zero-FX offhand Arsenal upgrade weapons (PaP Cluster Grenade) under stage_dir/weapons/sp/."""
    raw_weapons_dir = tools_root / "raw" / "weapons" / "sp"
    if not raw_weapons_dir.is_dir():
        return []

    raw_xanim_dir = tools_root / "raw" / "xanim"
    xanim_case_map = build_xanim_case_map(raw_xanim_dir) if raw_xanim_dir.is_dir() else None

    out_dir = stage_dir / "weapons" / "sp"
    out_dir.mkdir(parents=True, exist_ok=True)

    staged_offhand: list[str] = []
    for weap_name, template_candidates, overrides in BZ_OFFHAND_WEAPON_SPECS:
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
        (out_dir / weap_name).write_text(cloned_text, encoding="latin1")
        staged_offhand.append(f"weapons/sp/{weap_name}")
    return staged_offhand


# Canonical 1x base reserve stock for all 72 playable stock zombie primary weapons across
# Nacht, Verruckt, Shi No Numa, and Der Riese (ADR-0005). Staged into mod.ff with maxAmmo = 3x
# so Double Ammo (2x) and Double PaP (1.5x -> 3x) display true native WaW HUD counts while
# Classic Mode (bz_enabled=0) strictly clamps back to 1x.
STOCK_3X_AMMO_WEAPONS: dict[str, int] = {
    "30cal_bipod": 500,
    "bar": 140,
    "bar_bipod": 140,
    "colt": 80,
    "doublebarrel": 60,
    "doublebarrel_sawed_grip": 60,
    "fg42_bipod": 192,
    "gewehr43": 120,
    "kar98k": 50,
    "kar98k_scoped_zombie": 50,
    "m1carbine": 120,
    "m1garand": 128,
    "m1garand_gl": 128,
    "m1garand_gl_zombie": 128,
    "m1garand_gl_zombie_upgraded": 150,
    "m2_flamethrower_zombie": 300,
    "m2_flamethrower_zombie_upgraded": 300,
    "mg42_bipod": 500,
    "mp40": 192,
    "panzerschrek": 4,
    "panzerschrek_zombie": 20,
    "panzerschrek_zombie_upgraded": 30,
    "ppsh": 355,
    "ptrs41_zombie": 60,
    "ptrs41_zombie_upgraded": 60,
    "ray_gun": 160,
    "ray_gun_upgraded": 200,
    "shotgun": 60,
    "springfield": 50,
    "stg44": 180,
    "sw_357": 80,
    "tesla_gun": 15,
    "tesla_gun_upgraded": 30,
    "thompson": 200,
    "type99_rifle_scoped_zombie": 50,
    "walther": 80,
    "zombie_30cal": 500,
    "zombie_30cal_upgraded": 750,
    "zombie_bar": 140,
    "zombie_bar_upgraded": 180,
    "zombie_colt": 80,
    "zombie_colt_upgraded": 40,
    "zombie_doublebarrel": 60,
    "zombie_doublebarrel_sawed": 60,
    "zombie_doublebarrel_upgraded": 60,
    "zombie_fg42": 192,
    "zombie_fg42_upgraded": 400,
    "zombie_gewehr43": 120,
    "zombie_gewehr43_upgraded": 170,
    "zombie_kar98k": 50,
    "zombie_kar98k_upgraded": 60,
    "zombie_m1carbine": 120,
    "zombie_m1carbine_upgraded": 150,
    "zombie_m1garand": 128,
    "zombie_m1garand_upgraded": 150,
    "zombie_mg42": 500,
    "zombie_mg42_upgraded": 750,
    "zombie_mp40": 192,
    "zombie_mp40_upgraded": 192,
    "zombie_ppsh": 355,
    "zombie_ppsh_upgraded": 700,
    "zombie_shotgun": 60,
    "zombie_shotgun_upgraded": 60,
    "zombie_stg44": 180,
    "zombie_stg44_upgraded": 300,
    "zombie_sw_357": 80,
    "zombie_sw_357_upgraded": 80,
    "zombie_thompson": 200,
    "zombie_thompson_upgraded": 250,
    "zombie_type100_smg": 160,
    "zombie_type100_smg_upgraded": 220,
    "zombie_type99_rifle": 50,
    "zombie_type99_rifle_upgraded": 60,
}

# Remap the 6 non-Der-Riese muzzleflash FX strings used by Nacht/Verruckt/Sumpf stock rifles
# to exact Der Riese equivalents so staging all 72 stock weapons adds 0 FX slots (329/400).
STOCK_WEAPON_FX_REMAP: dict[str, str] = {
    "weapon/muzzleflashes/heavy_view": "weapon/muzzleflashes/fx_30cal_bulletweap_view",
    "weapon/muzzleflashes/heavy": "weapon/muzzleflashes/fx_30cal_bulletweap",
    "weapon/muzzleflashes/rifle_flash_view": "weapon/muzzleflashes/fx_kar98k_view",
    "weapon/muzzleflashes/rifleflash": "weapon/muzzleflashes/fx_kar98k",
    "weapon/muzzleflashes/fx_type99_rifle_view": "weapon/muzzleflashes/fx_kar98k_view",
    "weapon/muzzleflashes/fx_type99_rifle": "weapon/muzzleflashes/fx_kar98k",
}


def build_stock_3x_ammo_weapon_file(
    stock_text: str,
    base_max_ammo: int,
    *,
    xanim_case_map: dict[str, str] | None = None,
) -> str:
    """Return a stock WEAPONFILE with maxAmmo raised to 3x and zero added Der Riese FX slots."""
    pairs = parse_weapon_file(stock_text)
    updated: list[tuple[str, str]] = []
    seen_max = False
    for k, v in pairs:
        if k == "maxAmmo":
            updated.append((k, str(int(base_max_ammo) * 3)))
            seen_max = True
        elif "effect" in k.lower() and v in STOCK_WEAPON_FX_REMAP:
            updated.append((k, STOCK_WEAPON_FX_REMAP[v]))
        elif xanim_case_map and k.lower().endswith("anim") and v and v.lower() in xanim_case_map:
            updated.append((k, xanim_case_map[v.lower()]))
        else:
            updated.append((k, v))
    if not seen_max:
        updated.append(("maxAmmo", str(int(base_max_ammo) * 3)))
    return serialize_weapon_file(updated)


def stage_bz_stock_3x_ammo_weapons(
    tools_root: Path,
    stage_dir: Path,
    steam_game: Path | None = None,
) -> list[str]:
    """Stage 3x maxAmmo overrides for present stock zombie primary weapons under stage_dir/weapons/sp/.

    When `steam_game` is provided, reads matching base weapon files from retail `main/iw_*.iwd`
    first (falling back to Mod Tools `raw/weapons/sp/`) so retail base-game weapon definitions
    are preserved byte-for-byte apart from the 3x `maxAmmo` ceiling.
    """
    raw_weapons_dir = tools_root / "raw" / "weapons" / "sp"
    if not raw_weapons_dir.is_dir():
        return []

    retail_iwd_texts: dict[str, str] = {}
    if steam_game is not None:
        main_dir = steam_game / "main"
        if main_dir.is_dir():
            for iwd_path in sorted(main_dir.glob("iw_*.iwd")):
                try:
                    with ZipFile(iwd_path, "r") as archive:
                        for name in archive.namelist():
                            norm = name.replace("\\", "/")
                            if norm.startswith("weapons/sp/") and not norm.endswith("/"):
                                wname = norm[len("weapons/sp/") :]
                                if wname in STOCK_3X_AMMO_WEAPONS:
                                    retail_iwd_texts[wname] = archive.read(name).decode("latin1")
                except Exception:
                    continue

    raw_xanim_dir = tools_root / "raw" / "xanim"
    xanim_case_map = build_xanim_case_map(raw_xanim_dir) if raw_xanim_dir.is_dir() else None

    out_dir = stage_dir / "weapons" / "sp"
    out_dir.mkdir(parents=True, exist_ok=True)

    staged: list[str] = []
    for weap_name, base_max in sorted(STOCK_3X_AMMO_WEAPONS.items()):
        stock_text = retail_iwd_texts.get(weap_name)
        if stock_text is None:
            src = raw_weapons_dir / weap_name
            if not src.is_file():
                continue
            stock_text = src.read_text(encoding="latin1")
        if not stock_text.startswith("WEAPONFILE"):
            continue
        out_text = build_stock_3x_ammo_weapon_file(
            stock_text,
            base_max,
            xanim_case_map=xanim_case_map,
        )
        (out_dir / weap_name).write_text(out_text, encoding="latin1")
        staged.append(f"weapons/sp/{weap_name}")
    return staged


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

CUSTOM_WEAPON_MANIFEST_NAME = ".bz_weapons_manifest.json"
CUSTOM_WEAPON_MANIFEST_VERSION = 1


def _custom_weapon_manifest_path(tools_root: Path) -> Path:
    return tools_root / "model_export" / bz_models.ASSET_SUBDIR / CUSTOM_WEAPON_MANIFEST_NAME


def _custom_weapon_source_digest() -> str:
    hasher = hashlib.sha256()
    hasher.update(Path(bz_models.__file__).read_bytes())
    return hasher.hexdigest()


def _expected_custom_image_stems() -> tuple[list[str], list[str]]:
    direct_images: list[str] = []
    spec_stems: list[str] = []
    for spec in bz_models.MATERIAL_SPECS:
        stem = spec.name.removeprefix("mtl_")
        if spec.material_type in ("model unlit", "effect"):
            direct_images.append(f"{stem}_c")
        else:
            direct_images.append(f"{stem}_c")
            direct_images.append(f"{stem}_n")
            spec_stems.append(f"{stem}_s")
    return direct_images, spec_stems


def _find_xmodel_payloads(subdir: Path, xm: str) -> list[Path]:
    """Return exact compiled xmodelparts/xmodelsurfs payload files for single-LOD xm (`xm`, `xm0`, or `xm1`)."""
    if not subdir.is_dir():
        return []
    pat = re.compile(rf"^{re.escape(xm)}[01]?$")
    return sorted(p for p in subdir.iterdir() if p.is_file() and pat.match(p.name))


def _is_owned_spec_iwi_name(filename: str, spec_stem: str) -> bool:
    """Return True iff filename is a WaW-hashed packed spec map for our exact material's gloss map."""
    gloss_stem = spec_stem.removesuffix("_s") + "_g"
    m = re.fullmatch(rf"~{re.escape(spec_stem)}-rgb&([^~]+)~[0-9a-fA-F]{{8}}\.iwi", filename)
    if m is None:
        return False
    gloss_frag = m.group(1)
    return len(gloss_frag) >= 3 and gloss_stem.startswith(gloss_frag)


def _find_spec_iwis(img_dir: Path, spec_stem: str) -> list[Path]:
    if not img_dir.is_dir():
        return []
    return [
        p
        for p in sorted(img_dir.glob(f"~{spec_stem}-rgb&*.iwi"))
        if p.is_file() and _is_owned_spec_iwi_name(p.name, spec_stem)
    ]


def _extract_material_packed_spec_name(mtl_path: Path, spec_stem: str) -> str | None:
    """Extract the exact packed spec .iwi filename referenced inside a compiled WaW material binary (A14/A15/A17/S18/S20).

    Returns None when the material binary has no embedded packed-spec token (e.g., minimal test fixtures).
    Raises ValueError if an embedded token for spec_stem is malformed (e.g. non-8-hex hash) or references
    an unowned gloss map, preventing fallback to unreferenced files.
    """
    if not _is_nonempty_file(mtl_path):
        return None
    raw_bytes = mtl_path.read_bytes()
    pat = re.compile(rb"~" + re.escape(spec_stem.encode("ascii")) + rb"-rgb&[^\x00\s]*")
    matches = list(pat.finditer(raw_bytes))
    if not matches:
        return None
    owned_candidates: set[str] = set()
    bad_tokens: list[str] = []
    for m in matches:
        token = m.group(0).decode("ascii", errors="replace")
        candidate = token + ".iwi"
        if _is_owned_spec_iwi_name(candidate, spec_stem):
            owned_candidates.add(candidate)
        else:
            bad_tokens.append(token)
    if bad_tokens or len(owned_candidates) != 1:
        raise ValueError(
            f"Compiled material {mtl_path.name} references unowned, malformed, or conflicting packed spec image(s): "
            f"{bad_tokens or sorted(owned_candidates)}"
        )
    return next(iter(owned_candidates))


def _is_owned_manifest_output(group: str, rel: str) -> bool:
    """Validate that a manifest output path stays strictly inside our managed directories and custom asset names."""
    if not isinstance(rel, str) or "\\" in rel or rel.startswith("/") or ".." in Path(rel).parts:
        return False
    parts = Path(rel).parts
    if len(parts) != 2 or parts[0] != group:
        return False
    name = parts[1]
    if group == "materials":
        return name in bz_models.ALL_CUSTOM_MATERIALS
    if group == "xmodel":
        return name in bz_models.ALL_CUSTOM_XMODELS
    if group in ("xmodelparts", "xmodelsurfs"):
        return any(re.fullmatch(rf"{re.escape(xm)}[01]?", name) for xm in bz_models.ALL_CUSTOM_XMODELS)
    if group == "images":
        direct_images, spec_stems = _expected_custom_image_stems()
        if name in {f"{img}.iwi" for img in direct_images}:
            return True
        return any(_is_owned_spec_iwi_name(name, stem) for stem in spec_stems)
    return False


def _read_custom_weapon_manifest(manifest_path: Path) -> dict | None:
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != CUSTOM_WEAPON_MANIFEST_VERSION:
        return None
    return data


def _is_nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _manifest_cache_valid(manifest: dict, raw_dir: Path, expected_digest: str) -> bool:
    if manifest.get("digest") != expected_digest:
        return False
    summary = manifest.get("summary")
    outputs = manifest.get("outputs")
    if not isinstance(summary, dict) or not isinstance(outputs, dict):
        return False
    if summary.get("materials") != list(bz_models.ALL_CUSTOM_MATERIALS):
        return False
    if summary.get("xmodels") != list(bz_models.ALL_CUSTOM_XMODELS):
        return False

    group_to_dir = {
        "materials": "materials",
        "xmodels": "xmodel",
        "xmodelparts": "xmodelparts",
        "xmodelsurfs": "xmodelsurfs",
        "images": "images",
    }
    for group, subdir in group_to_dir.items():
        entries = outputs.get(group)
        if not isinstance(entries, list) or not entries:
            return False
        for rel in entries:
            if not _is_owned_manifest_output(subdir, rel) or not _is_nonempty_file(raw_dir / rel):
                return False

    parts_names = {Path(rel).name for rel in outputs["xmodelparts"]}
    surfs_names = {Path(rel).name for rel in outputs["xmodelsurfs"]}
    for xm in bz_models.ALL_CUSTOM_XMODELS:
        pat = re.compile(rf"^{re.escape(xm)}[01]?$")
        if f"xmodel/{xm}" not in outputs["xmodels"]:
            return False
        if not any(pat.match(n) for n in parts_names):
            return False
        if not any(pat.match(n) for n in surfs_names):
            return False

    img_names = {Path(rel).name for rel in outputs["images"]}
    direct_images, spec_stems = _expected_custom_image_stems()
    for img in direct_images:
        if f"{img}.iwi" not in img_names:
            return False
    for stem in spec_stems:
        if not any(_is_owned_spec_iwi_name(n, stem) for n in img_names):
            return False
    return True


def compile_custom_weapon_assets(
    tools_root: Path,
    steam_root: Path,
    dev_root: Path,
    force: bool = False,
) -> dict[str, list[str]]:
    """Generate and compile custom Phase 2 weapon XMODELs and materials via Treyarch's converter.exe.

    Checks the JSON build manifest before invoking generate_all_assets() or converter.exe,
    invalidates any prior manifest before replacing outputs so failed conversions never leave
    a stale cache hit, verifies every compiled material, xmodel, xmodelparts, xmodelsurfs,
    and non-empty .iwi output, and cleans strictly owned paths without touching unrelated files.
    """
    raw_dir = tools_root / "raw"
    manifest_path = _custom_weapon_manifest_path(tools_root)
    digest = _custom_weapon_source_digest()

    prior_manifest = _read_custom_weapon_manifest(manifest_path)
    if not force and prior_manifest is not None and _manifest_cache_valid(prior_manifest, raw_dir, digest):
        return prior_manifest["summary"]

    # Invalidate any prior success manifest BEFORE modifying or converting outputs (S11)
    # so a partial/failed converter run can never be accepted by a subsequent build.
    manifest_path.unlink(missing_ok=True)

    summary = bz_models.generate_all_assets(tools_root)

    direct_images = [img for img in summary["images"] if not img.endswith(("_s", "_g"))]
    spec_stems = [img for img in summary["images"] if img.endswith("_s")]
    expected_materials = [raw_dir / "materials" / mtl for mtl in summary["materials"]]
    expected_xmodels = [raw_dir / "xmodel" / xm for xm in summary["xmodels"]]
    expected_direct_imgs = [raw_dir / "images" / f"{img}.iwi" for img in direct_images]

    # Remove ONLY validated owned prior-manifest paths and exact single-LOD / direct custom outputs (A5/A10/S13).
    # Never glob-delete arbitrary packed spec .iwi files not recorded in our prior manifest, so foreign packed
    # images sharing a truncated gloss prefix with a different hash survive untouched.
    group_to_dir = {
        "materials": "materials",
        "xmodels": "xmodel",
        "xmodelparts": "xmodelparts",
        "xmodelsurfs": "xmodelsurfs",
        "images": "images",
    }
    if prior_manifest is not None and isinstance(prior_manifest.get("outputs"), dict):
        for group, entries in prior_manifest["outputs"].items():
            subdir = group_to_dir.get(group)
            if subdir and isinstance(entries, list):
                for rel in entries:
                    if _is_owned_manifest_output(subdir, rel):
                        (raw_dir / rel).unlink(missing_ok=True)
    # Before unlinking our compiled materials, remove any exact owned packed spec .iwi referenced by them
    # so manifestless retries after an aborted conversion self-heal without touching foreign peers (F26).
    for stem in spec_stems:
        mtl_path = raw_dir / "materials" / f"mtl_{stem.removesuffix('_s')}"
        try:
            prev_ref = _extract_material_packed_spec_name(mtl_path, stem)
        except ValueError:
            prev_ref = None
        if prev_ref is not None:
            (raw_dir / "images" / prev_ref).unlink(missing_ok=True)
    for out_path in (*expected_materials, *expected_xmodels, *expected_direct_imgs):
        out_path.unlink(missing_ok=True)
    for xm in summary["xmodels"]:
        for sub in ("xmodelparts", "xmodelsurfs"):
            for stale in _find_xmodel_payloads(raw_dir / sub, xm):
                stale.unlink(missing_ok=True)

    env = os.environ.copy()
    env["WAW_STEAM_ROOT"] = str(steam_root)
    env["WAW_DEV_ROOT"] = str(dev_root)

    def _convert_single(asset_type: str, asset_name: str) -> None:
        cmd = [str(OPEN_TOOL_SH), "converter", "-single", asset_type, asset_name, "-n"]
        res = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            check=False,
        )
        if res.returncode != 0 or "Conversion failed" in (res.stdout or ""):
            raise RuntimeError(
                f"converter.exe failed for {asset_type} {asset_name!r} (rc={res.returncode}):\n"
                f"{(res.stdout or '').strip()}"
            )

    pre_spec_meta: dict[str, dict[str, tuple[int, int]]] = {
        stem: {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in _find_spec_iwis(raw_dir / "images", stem)}
        for stem in spec_stems
    }
    for mtl in summary["materials"]:
        _convert_single("material", mtl)
    for xm in summary["xmodels"]:
        _convert_single("xmodel", xm)

    missing: list[str] = []
    recorded_materials: list[str] = []
    recorded_xmodels: list[str] = []
    recorded_parts: list[str] = []
    recorded_surfs: list[str] = []
    recorded_images: list[str] = []

    for p in expected_materials:
        if _is_nonempty_file(p):
            recorded_materials.append(p.relative_to(raw_dir).as_posix())
        else:
            missing.append(str(p))

    for xm, p in zip(summary["xmodels"], expected_xmodels):
        if _is_nonempty_file(p):
            recorded_xmodels.append(p.relative_to(raw_dir).as_posix())
        else:
            missing.append(str(p))
        parts = [f for f in _find_xmodel_payloads(raw_dir / "xmodelparts", xm) if _is_nonempty_file(f)]
        if parts:
            recorded_parts.extend(f.relative_to(raw_dir).as_posix() for f in parts)
        else:
            missing.append(str(raw_dir / "xmodelparts" / xm))
        surfs = [f for f in _find_xmodel_payloads(raw_dir / "xmodelsurfs", xm) if _is_nonempty_file(f)]
        if surfs:
            recorded_surfs.extend(f.relative_to(raw_dir).as_posix() for f in surfs)
        else:
            missing.append(str(raw_dir / "xmodelsurfs" / xm))

    for p in expected_direct_imgs:
        if _is_nonempty_file(p):
            recorded_images.append(p.relative_to(raw_dir).as_posix())
        else:
            missing.append(str(p))

    # Identify exact converter-owned packed specular maps using the same strict ownership predicate as
    # cache validation and staging (A10/A11/A14/S16/S18):
    # - When the compiled material binary embeds an exact packed image name, require THAT exact file
    #   to exist, be non-empty, AND have been freshly written/updated during this conversion run.
    # - Otherwise (synthetic mock material binary without embedded image strings), require newly
    #   created/updated valid owned packed images from this conversion run.
    for stem in spec_stems:
        mtl_path = raw_dir / "materials" / f"mtl_{stem.removesuffix('_s')}"
        try:
            ref_name = _extract_material_packed_spec_name(mtl_path, stem)
        except ValueError as exc:
            missing.append(str(exc))
            continue
        if ref_name is not None:
            ref_path = raw_dir / "images" / ref_name
            if (
                _is_nonempty_file(ref_path)
                and pre_spec_meta[stem].get(ref_name) != (ref_path.stat().st_mtime_ns, ref_path.stat().st_size)
            ):
                owned_spec = [ref_path]
            else:
                owned_spec = []
        else:
            candidates = [f for f in _find_spec_iwis(raw_dir / "images", stem) if _is_nonempty_file(f)]
            owned_spec = [
                f
                for f in candidates
                if pre_spec_meta[stem].get(f.name) != (f.stat().st_mtime_ns, f.stat().st_size)
            ]
        if owned_spec:
            recorded_images.extend(f.relative_to(raw_dir).as_posix() for f in owned_spec)
        else:
            expected_label = ref_name if ref_name is not None else f"~{stem}-rgb&*.iwi"
            missing.append(str(raw_dir / "images" / expected_label))

    if missing:
        raise RuntimeError(f"Custom weapon conversion succeeded but outputs are missing or empty: {missing}")

    manifest_data = {
        "version": CUSTOM_WEAPON_MANIFEST_VERSION,
        "digest": digest,
        "summary": summary,
        "outputs": {
            "materials": sorted(set(recorded_materials)),
            "xmodels": sorted(set(recorded_xmodels)),
            "xmodelparts": sorted(set(recorded_parts)),
            "xmodelsurfs": sorted(set(recorded_surfs)),
            "images": sorted(set(recorded_images)),
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=manifest_path.parent) as tmp:
        staged_manifest = Path(tmp) / manifest_path.name
        staged_manifest.write_text(json.dumps(manifest_data, indent=2, sort_keys=True) + "\n", encoding="ascii")
        staged_manifest.replace(manifest_path)
    return summary


def stage_custom_weapon_images(tools_root: Path, stage_dir: Path) -> list[str]:
    """Copy ONLY the exact owned compiled custom weapon .iwi images into stage_dir/images/ for IWD packing."""
    raw_dir = tools_root / "raw"
    raw_images_dir = raw_dir / "images"
    if not raw_images_dir.is_dir():
        return []

    out_dir = stage_dir / "images"
    staged_relpaths: list[str] = []

    manifest = _read_custom_weapon_manifest(_custom_weapon_manifest_path(tools_root))
    if manifest is not None and isinstance(manifest.get("outputs", {}).get("images"), list):
        candidates: list[Path] = []
        missing: list[str] = []
        for rel in sorted(manifest["outputs"]["images"]):
            if not _is_owned_manifest_output("images", rel):
                continue
            src = raw_dir / rel
            if not _is_nonempty_file(src):
                missing.append(str(src))
            else:
                candidates.append(src)
        if missing:
            raise FileNotFoundError(
                f"Manifest-recorded custom weapon images are missing or empty: {', '.join(missing)}"
            )
    else:
        direct_images, spec_stems = _expected_custom_image_stems()
        candidates = []
        for img in direct_images:
            p = raw_images_dir / f"{img}.iwi"
            if _is_nonempty_file(p):
                candidates.append(p)
        for stem in spec_stems:
            mtl_path = raw_dir / "materials" / f"mtl_{stem.removesuffix('_s')}"
            ref_name = _extract_material_packed_spec_name(mtl_path, stem)
            if ref_name is not None:
                p = raw_images_dir / ref_name
                if not _is_nonempty_file(p):
                    raise FileNotFoundError(f"Compiled material {mtl_path.name} references missing packed image: {p}")
                candidates.append(p)
            else:
                matches = [p for p in _find_spec_iwis(raw_images_dir, stem) if _is_nonempty_file(p)]
                if len(matches) == 1:
                    candidates.append(matches[0])
                elif len(matches) > 1:
                    raise FileNotFoundError(
                        f"Manifest missing and multiple packed images match {stem} without a compiled material reference: "
                        f"{[m.name for m in matches]}"
                    )
        candidates = sorted(set(candidates))

    for src_path in candidates:
        out_dir.mkdir(parents=True, exist_ok=True)
        dst_path = out_dir / src_path.name
        shutil.copy2(src_path, dst_path)
        staged_relpaths.append(f"images/{src_path.name}")
    return staged_relpaths


def generate_staged_mod_csv(
    base_csv_text: str,
    staged_gsc_relpaths: list[str],
    staged_weapon_relpaths: list[str] | None = None,
    extra_xmodels: list[str] | None = None,
    extra_materials: list[str] | None = None,
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
            or stem.startswith("_zombiemode_spawner_bz_")
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

    for mat in sorted(extra_materials or []):
        entry = f"material,{mat}"
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
    return _patch_coop_lobby_menu_bz(source, "ui/xboxlive_lobby.menu")


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
    """Read the short HEAD commit (with -dirty when working tree is dirty) or dev fallback."""
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
        )
        commit_sha = output.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError):
        return "dev"
    if not BZ_BUILD_COMMIT_RE.fullmatch(commit_sha):
        return "dev"
    try:
        status_out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
        )
        if status_out.strip() and not commit_sha.endswith("-dirty"):
            commit_sha = f"{commit_sha}-dirty"
    except (OSError, subprocess.CalledProcessError):
        pass
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
        weapons_stock: bytes | None = None
        if map_name == "nazi_zombie_sumpf":
            weapons_stock = try_extract_stock_script(
                map_name, "maps/_zombiemode_weapons_sumpf.gsc", steam_game, tools_root
            )
        if weapons_stock is None:
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
        spawner_mod: str | None = None
        dogs_stock = try_extract_stock_script(
            map_name, "maps/_zombiemode_dogs.gsc", steam_game, tools_root
        )
        if dogs_stock is not None:
            dogs_mod = zombiemode_dogs_module_for_map(map_name)

        powerups_stock = try_extract_stock_script(
            map_name, "maps/_zombiemode_powerups.gsc", steam_game, tools_root
        )
        if powerups_stock is not None:
            powerups_mod = zombiemode_powerups_module_for_map(map_name)

        spawner_stock = try_extract_stock_script(
            map_name, "maps/_zombiemode_spawner.gsc", steam_game, tools_root
        )
        if spawner_stock is not None and powerups_mod is not None and b"maps\\_zombiemode_powerups::" in spawner_stock:
            spawner_mod = zombiemode_spawner_module_for_map(map_name)
            spawner_text = _rewire_stock_module_refs(
                spawner_stock.decode("latin1"),
                rewire_weapons_module=weapons_mod,
                rewire_perks_module=perks_mod,
                rewire_dogs_module=dogs_mod,
                rewire_powerups_module=powerups_mod,
                rewire_spawner_module=spawner_mod,
            )
            # Prevent stock orange flame ignition when sprayed by bz_acid_sprayer (ADR-0004).
            spawner_text = re.sub(
                r"(zombie_flame_damage\s*\(\s*mod\s*,\s*player\s*\)\s*\{)",
                r'\1\n\tif ( maps\\_bz_hooks::bz_elements_enabled() && IsDefined( player ) && IsPlayer( player ) && tolower( "" + player GetCurrentWeapon() ) == "bz_acid_sprayer" )\n\t{\n\t\treturn false;\n\t}',
                spawner_text,
                count=1,
            )
            spawner_patched = spawner_text.encode("latin1")
            spawner_dst = stage_dir / "maps" / f"{spawner_mod}.gsc"
            spawner_dst.parent.mkdir(parents=True, exist_ok=True)
            spawner_dst.write_bytes(spawner_patched)

        if powerups_stock is not None:
            powerups_patched = inject_zombiemode_powerups_hooks(
                powerups_stock,
                rewire_weapons_module=weapons_mod,
                rewire_dogs_module=dogs_mod,
                rewire_powerups_module=powerups_mod,
            )
            if spawner_mod is not None:
                powerups_patched = _rewire_stock_module_refs(
                    powerups_patched.decode("latin1"),
                    rewire_spawner_module=spawner_mod,
                ).encode("latin1")
            powerups_dst = stage_dir / "maps" / f"{powerups_mod}.gsc"
            powerups_dst.parent.mkdir(parents=True, exist_ok=True)
            powerups_dst.write_bytes(powerups_patched)

        if dogs_stock is not None:
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
                or b"maps\\_zombiemode_spawner::" in teleporter_stock
            ):
                teleporter_patched = _rewire_stock_module_refs(
                    teleporter_stock.decode("latin1"),
                    rewire_weapons_module=weapons_mod,
                    rewire_dogs_module=dogs_mod,
                    rewire_powerups_module=powerups_mod,
                    rewire_spawner_module=spawner_mod,
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
            rewire_spawner_module=spawner_mod,
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
            rewire_spawner_module=spawner_mod,
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

    # Generate and stage zero-FX cloned Phase 2 primary weapons + item-slot special weapons for mod.csv.
    staged_weapons = stage_bz_element_weapons(tools_root=tools_root, stage_dir=stage_dir)
    staged_weapons.extend(stage_bz_special_item_weapons(tools_root=tools_root, stage_dir=stage_dir))
    staged_weapons.extend(stage_bz_offhand_weapons(tools_root=tools_root, stage_dir=stage_dir))
    # Stage 3x maxAmmo stock weapon overrides into stage_dir/weapons/sp/ for waw_gauntlet.iwd ONLY
    # (NOT mod.csv): under fs_game, WaW 1.7 BG_LoadWeaponDef reads weapons/sp/* from .iwd without
    # duplicating stock weapon FxEffectDef assets inside mod.ff (keeping Der Riese strictly at 329/400 FX).
    stage_bz_stock_3x_ammo_weapons(tools_root=tools_root, stage_dir=stage_dir, steam_game=steam_game)

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
        if staged_weapons and raw_xmodel_dir.is_dir():
            missing_custom = [
                xm for xm in bz_models.ALL_CUSTOM_XMODELS if not _is_nonempty_file(raw_xmodel_dir / xm)
            ]
            if missing_custom:
                raise FileNotFoundError(
                    f"Missing compiled custom weapon xmodels in {raw_xmodel_dir}: {', '.join(missing_custom)}"
                )
        compat_xmodels = [
            xm
            for xm in (*DER_RIESE_COMPAT_XMODELS, *bz_models.ALL_CUSTOM_XMODELS)
            if (raw_xmodel_dir / xm).is_file()
        ]
        raw_mat_dir = tools_root / "raw" / "materials"
        effect_materials = [
            mat
            for mat in bz_models.EFFECT_MATERIALS
            if (raw_mat_dir / mat).is_file()
        ]
        updated_csv = generate_staged_mod_csv(
            staged_mod_csv.read_text(encoding="latin1"),
            staged_gscs,
            staged_weapon_relpaths=staged_weapons,
            extra_xmodels=compat_xmodels,
            extra_materials=effect_materials,
        )
        staged_mod_csv.write_text(updated_csv, encoding="latin1")

    # Stage compiled custom weapon .iwi images so build_iwd() packs them into waw_gauntlet.iwd.
    stage_custom_weapon_images(tools_root=tools_root, stage_dir=stage_dir)

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


def _overlay_staged_ui_into_raw(
    stage_dir: Path,
    tools_root: Path,
    backups: list[tuple[Path, bytes | None]] | None = None,
) -> list[tuple[Path, bytes | None]]:
    """Temporarily overlay staged ui/ files onto tools_root/raw/ui/ for linker_pc.exe.

    In CoD:WaW 1.7, linker_pc.exe resolves menufile assets (and #include'd .inc files)
    from raw/ ahead of mods/<moddir>/ whenever a stock file of the same name exists in
    raw/. Overlaying staged ui/ files before linking and restoring them immediately
    afterward guarantees mod.ff compiles our patched menus while leaving raw/ untouched.
    """
    staged_ui_dir = stage_dir / "ui"
    raw_dir = tools_root / "raw"
    if backups is None:
        backups = []
    if not staged_ui_dir.is_dir():
        return backups

    for src_path in sorted(staged_ui_dir.rglob("*")):
        if not src_path.is_file():
            continue
        rel = src_path.relative_to(stage_dir)
        dst_path = raw_dir / rel
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        prior = dst_path.read_bytes() if dst_path.is_file() else None
        backups.append((dst_path, prior))
        # Preserve destination permissions instead of copying staged file modes
        # (a read-only staged file must not make a writable stock menu unwritable).
        shutil.copyfile(src_path, dst_path)
    return backups


def _restore_raw_ui_overlay(backups: list[tuple[Path, bytes | None]]) -> list[str]:
    """Restore tools_root/raw/ui/ files backed up by _overlay_staged_ui_into_raw().

    Attempts every file even if one destination fails and returns any error strings.
    """
    errors: list[str] = []
    for dst_path, prior in reversed(backups):
        try:
            if prior is not None:
                if dst_path.is_file():
                    try:
                        if dst_path.read_bytes() == prior:
                            continue
                    except OSError:
                        pass
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                dst_path.write_bytes(prior)
            elif dst_path.parent.is_dir():
                dst_path.unlink(missing_ok=True)
        except OSError as exc:
            errors.append(f"{dst_path}: {exc}")
    return errors


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

    primary_exc: BaseException | None = None
    try:
        shutil.copyfile(mod_csv_src, zone_csv)
        if not assetlist_csv.exists():
            assetlist_csv.write_bytes(b"")
        _overlay_staged_ui_into_raw(
            stage_dir=stage_dir,
            tools_root=tools_root,
            backups=raw_ui_backups,
        )

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
    except BaseException as exc:
        primary_exc = exc
        raise
    finally:
        restore_errors = _restore_raw_ui_overlay(raw_ui_backups)
        for target_path, prior_bytes in (
            (zone_csv, prior_zone_csv),
            (assetlist_csv, prior_assetlist_csv),
        ):
            try:
                if prior_bytes is not None:
                    target_path.write_bytes(prior_bytes)
                else:
                    target_path.unlink(missing_ok=True)
            except OSError as exc:
                restore_errors.append(f"{target_path}: {exc}")
        if restore_errors:
            err_msg = (
                "Failed to restore raw UI overlay / manifests after linking: "
                + "; ".join(restore_errors)
            )
            if primary_exc is None:
                raise RuntimeError(err_msg)
            print(f"WARNING: {err_msg}", file=sys.stderr)


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
    images_dir = stage_dir / "images"
    image_files = (
        sorted(p for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() == ".iwi")
        if images_dir.is_dir()
        else []
    )

    with TemporaryDirectory(dir=DIST_DIR) as tmp:
        staged_iwd = Path(tmp) / dist_iwd.name
        with ZipFile(staged_iwd, "w") as archive:
            for file_path in (*gsc_files, *csc_files, *weapon_files, *image_files):
                rel = file_path.relative_to(stage_dir).as_posix()
                archive.writestr(ZipInfo(rel), file_path.read_bytes(), compress_type=ZIP_DEFLATED)
        staged_iwd.replace(dist_iwd)
    return dist_iwd


@contextmanager
def _deploy_mod_lock(mod_dir: Path):
    """Serialize concurrent deploy_mod() runs targeting the same mod directory (A9/S9)."""
    lock_path = mod_dir / ".deploy.lock"
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def deploy_mod(dist_dir: Path, appdata: Path) -> list[Path]:
    """Atomically deploy mod.ff and waw_gauntlet.iwd to <appdata>/mods/waw_gauntlet/.

    Serializes overlapping deployments targeting the same mod directory, stages both
    artifacts before replacing either destination, and rolls back any completed
    replacement if a subsequent replace fails so mod.ff and waw_gauntlet.iwd never mismatch.
    """
    if not appdata.is_dir():
        raise FileNotFoundError(f"World at War AppData folder is missing: {appdata}")

    artifact_names = ("mod.ff", f"{MOD_NAME}.iwd")
    sources: list[tuple[str, Path]] = []
    for artifact_name in artifact_names:
        src = dist_dir / artifact_name
        if not src.is_file():
            raise FileNotFoundError(f"Missing built mod artifact: {src}")
        sources.append((artifact_name, src))

    mod_dir = appdata / "mods" / MOD_NAME
    mod_dir.mkdir(parents=True, exist_ok=True)

    installed: list[Path] = []
    replaced: list[tuple[Path, Path | None]] = []
    with _deploy_mod_lock(mod_dir):
        with TemporaryDirectory(dir=mod_dir) as tmp:
            tmp_dir = Path(tmp)
            staged_pairs: list[tuple[Path, Path, Path | None]] = []
            for artifact_name, src in sources:
                dest = mod_dir / artifact_name
                staged = tmp_dir / artifact_name
                shutil.copyfile(src, staged)
                backup: Path | None = None
                if dest.is_file():
                    backup = tmp_dir / f"{artifact_name}.bak"
                    shutil.copyfile(dest, backup)
                staged_pairs.append((staged, dest, backup))

            try:
                for staged, dest, backup in staged_pairs:
                    staged.replace(dest)
                    replaced.append((dest, backup))
                    installed.append(dest)
            except BaseException:
                restore_errors: list[str] = []
                for dest, backup in reversed(replaced):
                    try:
                        if backup is not None and backup.is_file():
                            backup.replace(dest)
                        else:
                            dest.unlink(missing_ok=True)
                    except OSError as exc:
                        restore_errors.append(f"{dest}: {exc}")
                if restore_errors:
                    print(
                        "WARNING: Failed to roll back partial mod deployment: " + "; ".join(restore_errors),
                        file=sys.stderr,
                    )
                raise
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
    compile_custom_weapon_assets(tools_root=tools_root, steam_root=steam_root, dev_root=dev_root)
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
