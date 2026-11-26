"""Offline TDD contract suite for P2-T1 (#23): Zero-FX Cloned Primary Weapons,
Phase 2 Rules/State, Mystery Box Wiring, Arsenal Station Phase 2 Popup, and
Enhancements Menu Presets.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_ROOT = REPO_ROOT / "mod"
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tests.gsc_runtime import (  # noqa: E402
    FakeDvarStore,
    GscArray,
    GscRuntime,
    GscStruct,
    UNDEFINED,
    tokenize,
)
from tests.test_bz_hooks_and_build import (  # noqa: E402
    BZ_HOOKS_MOD,
    BzGscRuntime,
    FakeEntity,
    _ast_contains_method_call,
)

RULES_MOD = "maps\\_bz_rules"
STATE_MOD = "maps\\_bz_state"
STATIONS_MOD = "maps\\_bz_stations"

SYNTHETIC_RAY_GUN = (
    "WEAPONFILE"
    "\\displayName\\WEAPON_RAY_GUN"
    "\\inventoryType\\primary"
    "\\ammoName\\ray_gun"
    "\\clipName\\ray_gun"
    "\\damage\\1500"
    "\\minDamage\\1000"
    "\\explosionInnerDamage\\1500"
    "\\explosionOuterDamage\\300"
    "\\explosionRadius\\128"
    "\\clipSize\\20"
    "\\maxAmmo\\160"
    "\\startAmmo\\160"
    "\\dropAmmoMin\\20"
    "\\dropAmmoMax\\40"
    "\\gunModel\\viewmodel_usa_ray_gun"
    "\\worldModel\\weapon_usa_ray_gun"
    "\\viewFlashEffect\\weapon/muzzleflashes/fx_raygun_custom_disallowed"
    "\\worldFlashEffect\\weapon/muzzleflashes/fx_raygun_world_disallowed"
    "\\viewShellEjectEffect\\weapon/shellejects/fx_custom_shell"
    "\\worldShellEjectEffect\\weapon/shellejects/fx_custom_shell_w"
    "\\projTrailEffect\\misc/fx_trail_raygun_geotrail"
    "\\projExplosionEffect\\misc/fx_exp_raygun_impact"
    "\\customTracerFx\\weapon/tracers/fx_not_in_intersection"
)

SYNTHETIC_M1GARAND_GL = (
    "WEAPONFILE"
    "\\displayName\\WEAPON_M1GARAND_GL"
    "\\inventoryType\\primary"
    "\\altWeapon\\m7_launcher"
    "\\ammoName\\m1garand"
    "\\clipName\\m1garand"
    "\\damage\\180"
    "\\minDamage\\120"
    "\\explosionInnerDamage\\250"
    "\\explosionOuterDamage\\50"
    "\\explosionRadius\\96"
    "\\clipSize\\8"
    "\\maxAmmo\\80"
    "\\startAmmo\\80"
    "\\dropAmmoMin\\8"
    "\\dropAmmoMax\\24"
    "\\gunModel\\viewmodel_usa_m1garand_rifle"
    "\\worldModel\\weapon_usa_m1garand_rifle"
    "\\viewFlashEffect\\weapon/muzzleflashes/rifleflash"
    "\\worldFlashEffect\\weapon/muzzleflashes/rifleflash_world"
)

SYNTHETIC_KAR98K = (
    "WEAPONFILE"
    "\\displayName\\WEAPON_KAR98K"
    "\\inventoryType\\primary"
    "\\ammoName\\kar98k"
    "\\clipName\\kar98k"
    "\\damage\\160"
    "\\minDamage\\100"
    "\\clipSize\\5"
    "\\maxAmmo\\50"
    "\\startAmmo\\50"
    "\\dropAmmoMin\\5"
    "\\dropAmmoMax\\15"
    "\\gunModel\\viewmodel_ger_kar98k_rifle"
    "\\worldModel\\weapon_ger_kar98k_rifle"
    "\\viewFlashEffect\\weapon/muzzleflashes/rifleflash"
    "\\worldFlashEffect\\weapon/muzzleflashes/rifleflash_world"
)

SYNTHETIC_ZOMBIE_COLT = (
    "WEAPONFILE"
    "\\displayName\\WEAPON_COLT"
    "\\inventoryType\\primary"
    "\\ammoName\\colt"
    "\\clipName\\colt"
    "\\damage\\40"
    "\\minDamage\\20"
    "\\clipSize\\8"
    "\\maxAmmo\\80"
    "\\startAmmo\\32"
    "\\dropAmmoMin\\8"
    "\\dropAmmoMax\\16"
    "\\idleAnim\\viewmodel_colt45_idle"
    "\\emptyIdleAnim\\viewmodel_colt45_idle"
    "\\fireAnim\\viewmodel_colt45_fire"
    "\\lastShotAnim\\viewmodel_colt45_lastshot"
    "\\raiseAnim\\viewmodel_colt45_pullout"
    "\\dropAnim\\viewmodel_colt45_putaway"
    "\\reloadAnim\\viewmodel_colt45_reload_notempty"
    "\\reloadEmptyAnim\\viewmodel_colt45_reload"
    "\\adsUpAnim\\viewmodel_colt45_missing_ads_up"
    "\\gunModel\\viewmodel_usa_colt45_pistol"
    "\\worldModel\\weapon_usa_colt45_pistol"
    "\\viewFlashEffect\\weapon/muzzleflashes/pistolflash"
    "\\worldFlashEffect\\weapon/muzzleflashes/pistolflash_world"
)

SYNTHETIC_M2_FLAMETHROWER_ZOMBIE = (
    "WEAPONFILE"
    "\\displayName\\WEAPON_M2_FLAMETHROWER"
    "\\inventoryType\\primary"
    "\\weaponType\\gas"
    "\\weaponClass\\gas"
    "\\fireType\\Full Auto"
    "\\ammoName\\fuel"
    "\\clipName\\fuel"
    "\\damage\\30"
    "\\minDamage\\30"
    "\\explosionInnerDamage\\0"
    "\\explosionOuterDamage\\0"
    "\\explosionRadius\\0"
    "\\clipSize\\100"
    "\\maxAmmo\\300"
    "\\startAmmo\\300"
    "\\dropAmmoMin\\100"
    "\\dropAmmoMax\\300"
    "\\fireTime\\0.05"
    "\\aimDownSight\\1"
    "\\adsFire\\1"
    "\\adsUpAnim\\viewmodel_usa_flamethrower_ADS_up"
    "\\adsDownAnim\\viewmodel_usa_flamethrower_ADS_down"
    "\\adsFireAnim\\viewmodel_usa_flamethrower_ADS_fire"
    "\\adsLastShotAnim\\viewmodel_usa_flamethrower_ADS_lastshot"
    "\\adsRechamberAnim\\viewmodel_usa_flamethrower_ADS_rechamber"
    "\\idleAnim\\viewmodel_usa_flamethrower_idle"
    "\\fireAnim\\viewmodel_usa_flamethrower_fire"
    "\\fireSound\\weap_flamethrower_fire"
    "\\fireSoundPlayer\\weap_flamethrower_fire_plr"
    "\\gunModel\\viewmodel_usa_flamethrower"
    "\\worldModel\\weapon_usa_flamethrower"
    "\\viewFlashEffect\\weapon/flamethrower/fx_flamethrower_disallowed"
    "\\worldFlashEffect\\weapon/flamethrower/fx_flamethrower_world_disallowed"
)

SYNTHETIC_TESLA_GUN = (
    "WEAPONFILE"
    "\\displayName\\ZOMBIE_TESLA_GUN"
    "\\inventoryType\\primary"
    "\\weaponType\\projectile"
    "\\weaponClass\\rifle"
    "\\fireType\\Single Shot"
    "\\ammoName\\tesla"
    "\\clipName\\tesla"
    "\\damage\\1000"
    "\\minDamage\\1000"
    "\\explosionInnerDamage\\1"
    "\\explosionOuterDamage\\1"
    "\\explosionRadius\\110"
    "\\clipSize\\3"
    "\\maxAmmo\\15"
    "\\startAmmo\\15"
    "\\dropAmmoMin\\3"
    "\\dropAmmoMax\\9"
    "\\fireTime\\1.0"
    "\\adsUpAnim\\viewmodel_usa_tesla_ADS_up"
    "\\adsDownAnim\\viewmodel_usa_tesla_ADS_down"
    "\\adsFireAnim\\viewmodel_usa_tesla_ADS_fire"
    "\\idleAnim\\viewmodel_usa_tesla_idle"
    "\\fireAnim\\viewmodel_usa_tesla_fire"
    "\\gunModel\\viewmodel_usa_tesla_gun"
    "\\worldModel\\weapon_usa_tesla"
    "\\viewFlashEffect\\maps/zombie/fx_zombie_tesla_muzzle_disallowed"
    "\\worldFlashEffect\\maps/zombie/fx_zombie_tesla_muzzle_world_disallowed"
    "\\projTrailEffect\\maps/zombie/fx_zombie_tesla_trail_disallowed"
    "\\projExplosionEffect\\maps/zombie/fx_zombie_tesla_impact_disallowed"
)

SYNTHETIC_M7_LAUNCHER_ZOMBIE = (
    "WEAPONFILE"
    "\\displayName\\WEAPON_M7_LAUNCHER"
    "\\inventoryType\\primary"
    "\\weaponType\\grenade"
    "\\weaponClass\\grenade"
    "\\fireType\\Single Shot"
    "\\altWeapon\\m1garand_gl_zombie"
    "\\ammoName\\m7_launcher"
    "\\clipName\\m7_launcher"
    "\\damage\\250"
    "\\minDamage\\150"
    "\\explosionInnerDamage\\300"
    "\\explosionOuterDamage\\100"
    "\\explosionRadius\\192"
    "\\clipSize\\1"
    "\\maxAmmo\\10"
    "\\startAmmo\\10"
    "\\dropAmmoMin\\1"
    "\\dropAmmoMax\\4"
    "\\fireTime\\1.25"
    "\\adsUpAnim\\viewmodel_m1garand_gl_ADS_up"
    "\\adsFireAnim\\viewmodel_m1garand_gl_ADS_fire"
    "\\idleAnim\\viewmodel_m1garand_gl_idle"
    "\\fireAnim\\viewmodel_m1garand_gl_fire"
    "\\gunModel\\viewmodel_zombie_m1garand_rifle_grenade"
    "\\worldModel\\weapon_zombie_m1garand_rifle_grenade"
    "\\viewFlashEffect\\weapon/muzzleflashes/rifleflash_disallowed"
    "\\projTrailEffect\\weapon/grenade/fx_trail_rifle_grenade"
)

SYNTHETIC_ZOMBIE_DOUBLEBARREL_SAWED = (
    "WEAPONFILE"
    "\\displayName\\WEAPON_DOUBLEBARREL_SAWED"
    "\\inventoryType\\primary"
    "\\weaponType\\bullet"
    "\\weaponClass\\spread"
    "\\fireType\\Single Shot"
    "\\ammoName\\doublebarrel"
    "\\clipName\\doublebarrel"
    "\\damage\\150"
    "\\minDamage\\100"
    "\\clipSize\\2"
    "\\maxAmmo\\60"
    "\\startAmmo\\60"
    "\\fireTime\\0.35"
    "\\reloadTime\\1.8"
    "\\reloadEmptyTime\\1.8"
    "\\aimDownSight\\1"
    "\\adsFire\\1"
    "\\adsUpAnim\\viewmodel_doublebarrel_missing_ads_up"
    "\\idleAnim\\viewmodel_doublebarrel_idle"
    "\\emptyIdleAnim\\viewmodel_doublebarrel_idle"
    "\\fireAnim\\viewmodel_doublebarrel_fire"
    "\\reloadAnim\\viewmodel_doublebarrel_reload"
    "\\reloadEmptyAnim\\viewmodel_doublebarrel_reload"
    "\\fireSound\\weap_dbshotgun_fire"
    "\\fireSoundPlayer\\weap_dbshotgun_fire_plr"
    "\\gunModel\\viewmodel_usa_sawed_off_shotgun"
    "\\worldModel\\weapon_usa_sawed_off_shotgun"
    "\\viewFlashEffect\\weapon/muzzleflashes/shotgunflash_disallowed"
)

SYNTHETIC_FG42_SCOPED = (
    "WEAPONFILE"
    "\\displayName\\WEAPON_FG42_SCOPED"
    "\\inventoryType\\primary"
    "\\weaponType\\bullet"
    "\\weaponClass\\rifle"
    "\\fireType\\Full Auto"
    "\\ammoName\\fg42"
    "\\clipName\\fg42"
    "\\damage\\160"
    "\\minDamage\\100"
    "\\explosionInnerDamage\\0"
    "\\explosionOuterDamage\\0"
    "\\explosionRadius\\0"
    "\\clipSize\\20"
    "\\maxAmmo\\160"
    "\\startAmmo\\160"
    "\\dropAmmoMin\\20"
    "\\dropAmmoMax\\40"
    "\\fireTime\\0.1"
    "\\adsUpAnim\\viewmodel_fg42_ADS_up"
    "\\adsFireAnim\\viewmodel_fg42_ADS_fire"
    "\\idleAnim\\viewmodel_fg42_idle"
    "\\fireAnim\\viewmodel_fg42_fire"
    "\\reloadAnim\\viewmodel_fg42_reload"
    "\\gunModel\\viewmodel_ger_fg42_scoped_lmg"
    "\\worldModel\\weapon_ger_fg42_scoped_lmg"
    "\\viewFlashEffect\\weapon/muzzleflashes/rifleflash_disallowed"
    "\\fireSound\\weap_fg42_fire"
    "\\fireSoundPlayer\\weap_fg42_fire_plr"
)

SYNTHETIC_M1CARBINE_BAYONET = (
    "WEAPONFILE"
    "\\displayName\\WEAPON_M1CARBINE_BAYONET"
    "\\inventoryType\\primary"
    "\\weaponType\\bullet"
    "\\weaponClass\\rifle"
    "\\fireType\\Single Shot"
    "\\ammoName\\m1carbine"
    "\\clipName\\m1carbine"
    "\\damage\\120"
    "\\minDamage\\80"
    "\\clipSize\\15"
    "\\maxAmmo\\150"
    "\\startAmmo\\60"
    "\\fireTime\\0.15"
    "\\reloadTime\\1.8"
    "\\reloadEmptyTime\\2.2"
    "\\idleAnim\\viewmodel_carbine_idle"
    "\\emptyIdleAnim\\viewmodel_carbine_empty_idle"
    "\\fireAnim\\viewmodel_carbine_fire"
    "\\lastShotAnim\\viewmodel_carbine_fire"
    "\\meleeAnim\\viewmodel_carbine_bayonet_swipe"
    "\\reloadAnim\\viewmodel_carbine_reload"
    "\\reloadEmptyAnim\\viewmodel_carbine_reload_empty"
    "\\raiseAnim\\viewmodel_carbine_pullout"
    "\\dropAnim\\viewmodel_carbine_putaway"
    "\\adsUpAnim\\viewmodel_carbine_ADS_up"
    "\\gunModel\\viewmodel_usa_m1carbine_rifle_bayonet"
    "\\worldModel\\weapon_usa_m1carbine_rifle_bayonet"
    "\\viewFlashEffect\\weapon/muzzleflashes/rifleflash_disallowed"
    "\\fireSound\\weap_m1carbine_fire"
    "\\fireSoundPlayer\\weap_m1carbine_fire_plr"
)

SYNTHETIC_ZOMBIE_BOWIE_FLOURISH = (
    "WEAPONFILE"
    "\\displayName\\ZOMBIE_BOWIE_FLOURISH"
    "\\inventoryType\\item"
    "\\weaponType\\bullet"
    "\\weaponClass\\rifle"
    "\\fireType\\Full Auto"
    "\\ammoName\\bowie"
    "\\clipName\\bowie"
    "\\damage\\150"
    "\\minDamage\\150"
    "\\clipSize\\1"
    "\\maxAmmo\\1"
    "\\startAmmo\\1"
    "\\fireTime\\1.0"
    "\\reloadTime\\1.5"
    "\\aimDownSight\\1"
    "\\adsFire\\1"
    "\\adsUpAnim\\viewmodel_knife_bowie_missing_ads_up"
    "\\idleAnim\\viewmodel_zombie_perksacola_idle"
    "\\emptyIdleAnim\\viewmodel_zombie_perksacola_idle"
    "\\fireAnim\\viewmodel_zombie_perksacola_idle"
    "\\raiseAnim\\viewmodel_zombie_bowie"
    "\\dropAnim\\viewmodel_zombie_perksacola_lower"
    "\\fireSound\\weap_colt_fire"
    "\\fireSoundPlayer\\weap_colt_fire_plr"
    "\\gunModel\\viewmodel_knife_bowie"
    "\\worldModel\\viewmodel_knife_bowie"
    "\\viewFlashEffect\\weapon/muzzleflashes/pistolflash_disallowed"
)


class TestZeroFxWeaponClonerAndBuildStaging(unittest.TestCase):
    """Slice 1: Deterministic zero-FX weapon file cloning, staging, and mod.csv registration."""

    def setUp(self) -> None:
        import build_mod

        self.bm = build_mod

    def test_clone_zero_fx_weapon_file_strips_disallowed_fx_and_preserves_allowed_intersection(self) -> None:
        allowed = {
            "misc/fx_trail_raygun_geotrail",
            "misc/fx_exp_raygun_impact",
        }
        cloned = self.bm.clone_zero_fx_weapon_file(
            SYNTHETIC_RAY_GUN,
            overrides={
                "inventoryType": "primary",
                "ammoName": "bz_acid",
                "clipName": "bz_acid",
                "displayName": "BZ_ACID_SPRAYER",
                "clipSize": "20",
                "maxAmmo": "120",
                "startAmmo": "120",
                "viewFlashEffect": "maps/zombie/fx_not_cross_map",
            },
            allowed_fx_set=allowed,
        )
        pairs = dict(self.bm.parse_weapon_file(cloned))

        self.assertTrue(cloned.startswith("WEAPONFILE\\"))
        self.assertEqual(pairs["inventoryType"], "primary")
        self.assertEqual(pairs["ammoName"], "bz_acid")
        self.assertEqual(pairs["clipName"], "bz_acid")
        self.assertEqual(pairs["displayName"], "BZ_ACID_SPRAYER")
        self.assertEqual(pairs["clipSize"], "20")
        self.assertEqual(pairs["maxAmmo"], "120")
        self.assertEqual(pairs["startAmmo"], "120")

        # Allowed all-4-map intersection FX preserved verbatim
        self.assertEqual(pairs["projTrailEffect"], "misc/fx_trail_raygun_geotrail")
        self.assertEqual(pairs["projExplosionEffect"], "misc/fx_exp_raygun_impact")

        # Every disallowed *Effect / *Fx field (including disallowed overrides) cleared to ""
        self.assertEqual(pairs["viewFlashEffect"], "")
        self.assertEqual(pairs["worldFlashEffect"], "")
        self.assertEqual(pairs["viewShellEjectEffect"], "")
        self.assertEqual(pairs["worldShellEjectEffect"], "")
        self.assertEqual(pairs["customTracerFx"], "")

        # Deterministic output across repeated calls
        cloned_again = self.bm.clone_zero_fx_weapon_file(
            SYNTHETIC_RAY_GUN,
            overrides={
                "inventoryType": "primary",
                "ammoName": "bz_acid",
                "clipName": "bz_acid",
                "displayName": "BZ_ACID_SPRAYER",
                "clipSize": "20",
                "maxAmmo": "120",
                "startAmmo": "120",
                "viewFlashEffect": "maps/zombie/fx_not_cross_map",
            },
            allowed_fx_set=allowed,
        )
        self.assertEqual(cloned, cloned_again)

        # Rejects malformed non-WEAPONFILE payloads
        with self.assertRaises(ValueError):
            self.bm.clone_zero_fx_weapon_file("NOT_A_WEAPONFILE\\foo\\bar", {}, allowed)

        # Explicitly strips altWeapon (e.g. m1garand_gl -> m7_launcher) so no alt-weapon assets leak into mod.ff
        cloned_gl = self.bm.clone_zero_fx_weapon_file(SYNTHETIC_M1GARAND_GL, {}, allowed)
        gl_pairs = dict(self.bm.parse_weapon_file(cloned_gl))
        self.assertEqual(gl_pairs["altWeapon"], "")

    def test_stage_bz_element_weapons_generates_all_four_distinct_zero_fx_primaries_and_mod_csv(self) -> None:
        # Verify canonical primary template specs are distinct per weapon
        spec_templates = {
            weap_name: templates
            for weap_name, templates, _overrides in self.bm.BZ_ELEMENT_WEAPON_SPECS
        }
        self.assertEqual(
            spec_templates["bz_acid_sprayer"],
            ("m2_flamethrower_zombie",),
        )
        self.assertEqual(
            spec_templates["bz_cryo_cannon"],
            ("tesla_gun",),
        )
        self.assertEqual(
            spec_templates["bz_multi_crossbow"],
            ("fg42_scoped",),
        )
        self.assertEqual(
            spec_templates["bz_blade_boomerang"],
            ("zombie_colt", "colt"),
        )
        self.assertEqual(
            len({templates[0] for templates in spec_templates.values()}),
            4,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_sp = root / "tools" / "raw" / "weapons" / "sp"
            raw_sp.mkdir(parents=True)
            (raw_sp / "m2_flamethrower_zombie").write_text(
                SYNTHETIC_M2_FLAMETHROWER_ZOMBIE, encoding="latin1"
            )
            (raw_sp / "tesla_gun").write_text(SYNTHETIC_TESLA_GUN, encoding="latin1")
            (raw_sp / "fg42_scoped").write_text(
                SYNTHETIC_FG42_SCOPED, encoding="latin1"
            )
            (raw_sp / "m1carbine_bayonet").write_text(
                SYNTHETIC_M1CARBINE_BAYONET, encoding="latin1"
            )
            # Also include fallback templates to prove primary distinct templates win
            (raw_sp / "ray_gun").write_text(SYNTHETIC_RAY_GUN, encoding="latin1")
            (raw_sp / "m1garand_gl").write_text(SYNTHETIC_M1GARAND_GL, encoding="latin1")
            (raw_sp / "zombie_colt").write_text(SYNTHETIC_ZOMBIE_COLT, encoding="latin1")

            stage_dir = root / "stage"
            stage_dir.mkdir(parents=True)

            staged_relpaths = self.bm.stage_bz_element_weapons(root / "tools", stage_dir)
            self.assertEqual(
                staged_relpaths,
                [
                    "weapons/sp/bz_acid_sprayer",
                    "weapons/sp/bz_cryo_cannon",
                    "weapons/sp/bz_multi_crossbow",
                    "weapons/sp/bz_blade_boomerang",
                ],
            )

            expected_specs = {
                "bz_acid_sprayer": (
                    "bz_acid",
                    "Acid Sprayer",
                    "100",
                    "360",
                    "120",
                    "viewmodel_bz_acid_sprayer",
                    "world_bz_acid_sprayer",
                    "0.10",
                ),
                "bz_cryo_cannon": (
                    "bz_cryo",
                    "Cryo Cannon",
                    "8",
                    "288",
                    "96",
                    "viewmodel_bz_cryo_cannon",
                    "world_bz_cryo_cannon",
                    "0.55",
                ),
                "bz_multi_crossbow": (
                    "bz_xbow",
                    "Multi-Crossbow",
                    "6",
                    "108",
                    "36",
                    "viewmodel_bz_multi_crossbow",
                    "world_bz_multi_crossbow",
                    "0.52",
                ),
                "bz_blade_boomerang": (
                    "bz_blade",
                    "Blade Boomerang",
                    "1",
                    "0",
                    "0",
                    "viewmodel_bz_blade_boomerang",
                    "world_bz_blade_boomerang",
                    "1.15",
                ),
            }
            seen_ammo: set[str] = set()
            seen_gun_models: set[str] = set()
            seen_world_models: set[str] = set()
            allowed_norm = {fx.lower() for fx in self.bm.VERIFIED_ALL_4_MAP_FX}
            staged_pairs: dict[str, dict[str, str]] = {}

            for (
                weap_name,
                (ammo, disp, clip, max_ammo, start_ammo, gun_model, world_model, fire_time),
            ) in expected_specs.items():
                weap_path = stage_dir / "weapons" / "sp" / weap_name
                self.assertTrue(weap_path.is_file(), f"Missing staged weapon file: {weap_path}")
                pairs = dict(self.bm.parse_weapon_file(weap_path.read_text(encoding="latin1")))
                staged_pairs[weap_name] = pairs
                self.assertEqual(pairs["inventoryType"], "primary")
                expected_wtype = "gas" if weap_name == "bz_acid_sprayer" else "bullet"
                self.assertEqual(pairs["weaponType"], expected_wtype)
                self.assertEqual(pairs["ammoName"], ammo)
                self.assertEqual(pairs["clipName"], ammo)
                self.assertEqual(pairs["displayName"], disp)
                self.assertTrue(disp.isascii())
                self.assertEqual(pairs["altWeapon"], "")
                expected_base_dmg = "15" if weap_name == "bz_acid_sprayer" else "1"
                self.assertEqual(pairs["damage"], expected_base_dmg)
                self.assertEqual(pairs["minDamage"], expected_base_dmg)
                for loc_key, loc_val in self.bm.BZ_ELEMENT_LOC_MULTIPLIERS.items():
                    self.assertEqual(
                        pairs.get(loc_key),
                        loc_val,
                        f"{weap_name} must define {loc_key}={loc_val} so bullet hits and DoDamage(..., player) are not zeroed",
                    )
                self.assertEqual(pairs["explosionInnerDamage"], "0")
                self.assertEqual(pairs["explosionOuterDamage"], "0")
                self.assertEqual(pairs["explosionRadius"], "0")
                self.assertEqual(pairs["clipSize"], clip)
                self.assertEqual(pairs["maxAmmo"], max_ammo)
                self.assertEqual(pairs["startAmmo"], start_ammo)
                self.assertEqual(pairs["fireTime"], fire_time)
                self.assertEqual(pairs["gunModel"], gun_model)
                self.assertEqual(pairs["worldModel"], world_model)
                seen_ammo.add(ammo)
                seen_gun_models.add(gun_model)
                seen_world_models.add(world_model)

                # Zero added FX: every *Effect / *Fx field must be empty or in the all-4-map intersection
                for k, v in pairs.items():
                    kl = k.lower()
                    if kl.endswith("effect") or kl.endswith("fx"):
                        val_norm = v.strip().replace("\\", "/").lower()
                        self.assertTrue(
                            val_norm == "" or val_norm in allowed_norm,
                            f"{weap_name} field {k}={v!r} is not in VERIFIED_ALL_4_MAP_FX",
                        )

            self.assertEqual(len(seen_ammo), 4)
            self.assertEqual(len(seen_gun_models), 4)
            self.assertEqual(len(seen_world_models), 4)

            # Weapon-specific feel, ADS, and audio overrides
            acid = staged_pairs["bz_acid_sprayer"]
            self.assertEqual(acid["weaponType"], "gas")
            self.assertEqual(acid["weaponClass"], "gas")
            self.assertEqual(acid["fireType"], "Full Auto")
            self.assertEqual(acid["flameTableFirstPerson"], "bz_acid_flame_firstperson")
            self.assertEqual(acid["flameTableThirdPerson"], "bz_acid_flame_thirdperson")
            self.assertEqual(acid["aimDownSight"], "0")
            self.assertEqual(acid["adsFire"], "0")
            for ads_key in ("adsUpAnim", "adsDownAnim", "adsFireAnim", "adsLastShotAnim", "adsRechamberAnim"):
                self.assertEqual(acid[ads_key], "")
            self.assertEqual(acid["fireSound"], "")
            self.assertEqual(acid["fireSoundPlayer"], "")
            self.assertEqual(acid["emptyIdleAnim"], "viewmodel_flamethrower_idle")
            self.assertEqual(acid["reloadAnim"], "viewmodel_flamethrower_reload")
            self.assertEqual(acid["reloadEmptyAnim"], "viewmodel_flamethrower_reload")
            for ft_name in ("bz_acid_flame_firstperson", "bz_acid_flame_thirdperson"):
                ft_path = stage_dir / "weapons" / "sp" / ft_name
                self.assertTrue(ft_path.is_file(), f"Missing staged flametable: {ft_path}")
                ft_text = ft_path.read_text(encoding="latin1")
                self.assertTrue(ft_text.startswith("FLAMETABLEFILE\\"))
                self.assertIn("\\streamFuel\\mtl_bz_acid_stream", ft_text)
                self.assertIn("\\flameVar_streamPrimaryLightG\\0.95", ft_text)

            xbow = staged_pairs["bz_multi_crossbow"]
            self.assertEqual(xbow["fireType"], "Single Shot")
            self.assertEqual(xbow["fireTime"], "0.52")
            self.assertEqual(xbow["fireSound"], "gr_kar98_bolt_front_plr")
            self.assertEqual(xbow["fireSoundPlayer"], "gr_kar98_bolt_front_plr")

            blade = staged_pairs["bz_blade_boomerang"]
            self.assertEqual(blade["weaponClass"], "rifle")
            self.assertEqual(blade["shotCount"], "1")
            self.assertEqual(blade["fireType"], "Single Shot")
            self.assertEqual(blade["reloadTime"], "0.25")
            self.assertEqual(blade["reloadEmptyTime"], "0.25")
            self.assertEqual(blade["aimDownSight"], "0")
            self.assertEqual(blade["adsFire"], "0")
            self.assertEqual(blade["fireSound"], "foley_throw")
            self.assertEqual(blade["fireSoundPlayer"], "foley_throw")
            self.assertEqual(blade["idleAnim"], "viewmodel_ray_gun_idle")
            self.assertEqual(blade["emptyIdleAnim"], "viewmodel_ray_gun_drop")
            self.assertEqual(blade["fireAnim"], "viewmodel_germangrenade_throw")
            self.assertEqual(blade["lastShotAnim"], "viewmodel_germangrenade_throw")
            self.assertEqual(blade["cancelAutoHolsterWhenEmpty"], "1")
            self.assertEqual(blade["raiseAnim"], "viewmodel_ray_gun_raise")
            self.assertEqual(blade["reloadAnim"], "viewmodel_ray_gun_raise")
            self.assertEqual(blade["reloadEmptyAnim"], "viewmodel_ray_gun_raise")

            # generate_staged_mod_csv appends weapon,sp/bz_* entries cleanly without duplicates
            base_csv = (MOD_ROOT / "mod.csv").read_text(encoding="latin1")
            staged_csv = self.bm.generate_staged_mod_csv(
                base_csv,
                ["maps/_bz_hooks.gsc"],
                staged_weapon_relpaths=staged_relpaths,
            )
            for weap_name in expected_specs:
                self.assertNotIn(f"weapon,sp/{weap_name}", base_csv)
                self.assertEqual(staged_csv.count(f"weapon,sp/{weap_name}"), 1)

            # Idempotent if run again on already-augmented csv
            staged_csv_2 = self.bm.generate_staged_mod_csv(
                staged_csv,
                ["maps/_bz_hooks.gsc"],
                staged_weapon_relpaths=staged_relpaths,
            )
            for weap_name in expected_specs:
                self.assertEqual(staged_csv_2.count(f"weapon,sp/{weap_name}"), 1)

    def test_clone_zero_fx_weapon_file_resolves_linux_xanim_case_clears_missing_ads_and_falls_back_fire_anim(
        self,
    ) -> None:
        stock_fg42 = (
            "WEAPONFILE"
            "\\displayName\\WEAPON_FG42_SCOPED"
            "\\inventoryType\\primary"
            "\\playerAnimType\\rifle"
            "\\idleAnim\\viewmodel_fg42_IDLE"
            "\\fireAnim\\viewmodel_fg42_fire"
            "\\adsUpAnim\\viewmodel_ray_gun_ADS_up"
            "\\adsFireAnim\\viewmodel_fg42_ADS_fire"
            "\\adsDownAnim\\viewmodel_fg42_MISSING_ADS_down"
            "\\adsLastShotAnim\\viewmodel_fg42_MISSING_ADS_lastshot"
            "\\adsRechamberAnim\\viewmodel_fg42_MISSING_ADS_rechamber"
        )
        xanim_case_map = {
            "viewmodel_fg42_idle": "viewmodel_fg42_idle",
            "viewmodel_fg42_fire": "viewmodel_fg42_fire",
            "viewmodel_ray_gun_ads_up": "viewmodel_ray_gun_ads_up",
            "viewmodel_fg42_ads_fire": "viewmodel_fg42_ads_fire",
        }

        cloned = self.bm.clone_zero_fx_weapon_file(
            stock_fg42,
            overrides={"displayName": "Multi-Crossbow"},
            xanim_case_map=xanim_case_map,
        )
        pairs = dict(self.bm.parse_weapon_file(cloned))

        # Uppercase _ADS_ and _IDLE names resolve to exact lowercase on-disk filenames
        self.assertEqual(pairs["idleAnim"], "viewmodel_fg42_idle")
        self.assertEqual(pairs["fireAnim"], "viewmodel_fg42_fire")
        self.assertEqual(pairs["adsUpAnim"], "viewmodel_ray_gun_ads_up")
        self.assertEqual(pairs["adsFireAnim"], "viewmodel_fg42_ads_fire")
        # Non-*Anim fields like playerAnimType are untouched
        self.assertEqual(pairs["playerAnimType"], "rifle")
        # Missing optional ADS anims are cleared to "" so linker_pc.exe never errors
        self.assertEqual(pairs["adsDownAnim"], "")
        self.assertEqual(pairs["adsLastShotAnim"], "")
        self.assertEqual(pairs["adsRechamberAnim"], "")

        # fireAnim override falls back to template's existing anim when absent from xanim_case_map
        cloned_blade_fallback = self.bm.clone_zero_fx_weapon_file(
            SYNTHETIC_ZOMBIE_BOWIE_FLOURISH,
            overrides={"fireAnim": "viewmodel_knife_slash"},
            xanim_case_map={
                "viewmodel_zombie_perksacola_idle": "viewmodel_zombie_perksacola_idle",
                "viewmodel_zombie_bowie": "viewmodel_zombie_bowie",
                "viewmodel_zombie_perksacola_lower": "viewmodel_zombie_perksacola_lower",
            },
        )
        blade_fb_pairs = dict(self.bm.parse_weapon_file(cloned_blade_fallback))
        self.assertEqual(blade_fb_pairs["fireAnim"], "viewmodel_zombie_perksacola_idle")
        self.assertEqual(blade_fb_pairs["adsUpAnim"], "")

        # When viewmodel_knife_slash IS present on disk, override resolves to exact on-disk casing
        cloned_blade_present = self.bm.clone_zero_fx_weapon_file(
            SYNTHETIC_ZOMBIE_BOWIE_FLOURISH,
            overrides={"fireAnim": "viewmodel_knife_slash"},
            xanim_case_map={
                "viewmodel_zombie_perksacola_idle": "viewmodel_zombie_perksacola_idle",
                "viewmodel_zombie_bowie": "viewmodel_zombie_bowie",
                "viewmodel_zombie_perksacola_lower": "viewmodel_zombie_perksacola_lower",
                "viewmodel_knife_slash": "viewmodel_knife_slash",
            },
        )
        blade_ok_pairs = dict(self.bm.parse_weapon_file(cloned_blade_present))
        self.assertEqual(blade_ok_pairs["fireAnim"], "viewmodel_knife_slash")

    def test_stage_bz_element_weapons_auto_wires_raw_xanim_case_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_sp = root / "tools" / "raw" / "weapons" / "sp"
            raw_xanim = root / "tools" / "raw" / "xanim"
            raw_sp.mkdir(parents=True)
            raw_xanim.mkdir(parents=True)

            (raw_sp / "m2_flamethrower_zombie").write_text(
                SYNTHETIC_M2_FLAMETHROWER_ZOMBIE, encoding="latin1"
            )
            (raw_sp / "tesla_gun").write_text(SYNTHETIC_TESLA_GUN, encoding="latin1")
            (raw_sp / "fg42_scoped").write_text(
                SYNTHETIC_FG42_SCOPED, encoding="latin1"
            )
            (raw_sp / "zombie_colt").write_text(
                SYNTHETIC_ZOMBIE_COLT, encoding="latin1"
            )

            # Populate Linux lowercase xanim files (deliberately omitting tesla adsDownAnim & colt adsUpAnim)
            for anim_name in (
                "viewmodel_usa_flamethrower_idle",
                "viewmodel_usa_flamethrower_fire",
                "viewmodel_flamethrower_idle",
                "viewmodel_flamethrower_reload",
                "viewmodel_usa_tesla_idle",
                "viewmodel_usa_tesla_fire",
                "viewmodel_usa_tesla_ads_up",
                "viewmodel_usa_tesla_ads_fire",
                "viewmodel_fg42_idle",
                "viewmodel_fg42_fire",
                "viewmodel_fg42_reload",
                "viewmodel_fg42_ads_up",
                "viewmodel_fg42_ads_fire",
                "viewmodel_colt45_idle",
                "viewmodel_colt45_fire",
                "viewmodel_colt45_pullout",
                "viewmodel_colt45_putaway",
                "viewmodel_colt45_reload",
                "viewmodel_ray_gun_idle",
                "viewmodel_ray_gun_raise",
                "viewmodel_ray_gun_drop",
                "viewmodel_germangrenade_idle",
                "viewmodel_germangrenade_throw",
            ):
                (raw_xanim / anim_name).write_bytes(b"XANIM")

            stage_dir = root / "stage"
            stage_dir.mkdir(parents=True)
            self.bm.stage_bz_element_weapons(root / "tools", stage_dir)

            cryo = dict(
                self.bm.parse_weapon_file(
                    (stage_dir / "weapons" / "sp" / "bz_cryo_cannon").read_text(encoding="latin1")
                )
            )
            self.assertEqual(cryo["adsUpAnim"], "viewmodel_usa_tesla_ads_up")
            self.assertEqual(cryo["adsFireAnim"], "viewmodel_usa_tesla_ads_fire")
            # Missing optional adsDownAnim cleared to ""
            self.assertEqual(cryo["adsDownAnim"], "")

            xbow = dict(
                self.bm.parse_weapon_file(
                    (stage_dir / "weapons" / "sp" / "bz_multi_crossbow").read_text(encoding="latin1")
                )
            )
            self.assertEqual(xbow["adsUpAnim"], "viewmodel_fg42_ads_up")
            self.assertEqual(xbow["adsFireAnim"], "viewmodel_fg42_ads_fire")

            blade = dict(
                self.bm.parse_weapon_file(
                    (stage_dir / "weapons" / "sp" / "bz_blade_boomerang").read_text(encoding="latin1")
                )
            )
            self.assertEqual(blade["idleAnim"], "viewmodel_ray_gun_idle")
            self.assertEqual(blade["fireAnim"], "viewmodel_germangrenade_throw")
            self.assertEqual(blade["lastShotAnim"], "viewmodel_germangrenade_throw")
            self.assertEqual(blade["emptyIdleAnim"], "viewmodel_ray_gun_drop")
            self.assertEqual(blade["reloadAnim"], "viewmodel_ray_gun_raise")
            # Missing optional adsUpAnim cleared to ""
            self.assertEqual(blade["adsUpAnim"], "")


class TestMysteryBoxAndElementHookSeams(unittest.TestCase):
    """Slice 1b: Mystery Box registration, precaching, and weapon_fired hook seam."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzGscRuntime(MOD_ROOT, self.dvars)
        self.player = FakeEntity("HostPlayer", ent_num=0)
        self.gsc.players.append(self.player)

    def test_box_registration_and_precache_are_strict_noops_when_elements_disabled(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_elements_enabled", "0")

        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_register_box_weapons")

        self.assertEqual(self.gsc.precached_items, [])
        self.assertIs(self.gsc.level.get_field("zombie_weapons"), UNDEFINED)

    def test_box_registration_and_precache_add_all_four_primaries_when_elements_enabled(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_elements_enabled", "1")

        # Pre-seed level.zombie_include_weapons to verify box inclusion table updates cleanly too
        self.gsc.level.set_field("zombie_include_weapons", GscArray())

        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.assertEqual(
            self.gsc.precached_items,
            [
                "bz_acid_sprayer",
                "bz_cryo_cannon",
                "bz_multi_crossbow",
                "bz_blade_boomerang",
            ],
        )

        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        zw = self.gsc.level.get_field("zombie_weapons")
        inc = self.gsc.level.get_field("zombie_include_weapons")
        expected_hints = {
            "bz_acid_sprayer": "Press &&1 for Acid Sprayer",
            "bz_cryo_cannon": "Press &&1 for Cryo Cannon",
            "bz_multi_crossbow": "Press &&1 for Multi-Crossbow",
            "bz_blade_boomerang": "Press &&1 for Blade Boomerang",
        }
        for weap, expected_hint in expected_hints.items():
            entry = zw[weap]
            self.assertIsNot(entry, UNDEFINED, f"{weap} missing from level.zombie_weapons")
            self.assertTrue(entry.get_field("is_in_box"), f"{weap} must have is_in_box=true")
            self.assertEqual(entry.get_field("weapon_name"), weap)
            self.assertEqual(entry.get_field("hint"), expected_hint)
            # upgrade_name MUST stay undefined so stock Der Riese can_upgrade_weapon() never eats the weapon
            self.assertIs(entry.get_field("upgrade_name"), UNDEFINED, f"{weap} must leave upgrade_name undefined")
            self.assertTrue(inc[weap], f"{weap} missing from level.zombie_include_weapons")

        # Calling again is idempotent
        ev_count = len(self.gsc.emitted_events)
        self.gsc.call(BZ_HOOKS_MOD, "bz_register_box_weapons")
        self.assertEqual(len(self.gsc.emitted_events), ev_count)

    def test_weapon_fired_hook_dispatches_only_under_elements_gate(self) -> None:
        fired_log: list[tuple[str, str]] = []
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "weapon_fired",
            self.gsc.register_py_callback(
                "on_wf",
                lambda _s, player, weap: fired_log.append((player.get_field("name"), weap)),
            ),
            "elements",
        )

        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_elements_enabled", "0")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", self.player, "bz_acid_sprayer")
        self.assertEqual(fired_log, [])

        self.dvars.set("bz_elements_enabled", "1")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_weapon_fired", self.player, "bz_acid_sprayer")
        self.assertEqual(fired_log, [("HostPlayer", "bz_acid_sprayer")])


class TestPhase2RulesAndStatusMath(unittest.TestCase):
    """Slice 2a: Phase 2 catalog IDs, pricing, prerequisites, and pure combat/status math."""

    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)

    def test_element_ammo_cost_is_half_the_weapon_price_and_zero_for_invalid_ids(self) -> None:
        for item_id in ("acid_sprayer", "cryo_cannon", "multi_crossbow"):
            with self.subTest(item_id=item_id):
                weapon_cost = self.gsc.call(RULES_MOD, "bz_get_element_weapon_price", item_id)
                self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_element_ammo_cost", item_id.upper()), weapon_cost // 2)

        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_element_ammo_cost", "blade_boomerang"), 0)

        for item_id in ("", "ray_gun", "portal_grenade", "bz_acid_sprayer", UNDEFINED):
            with self.subTest(item_id=item_id):
                self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_element_ammo_cost", item_id), 0)

    def test_phase2_element_weapons_and_special_gear_catalog_prices_and_metadata(self) -> None:
        elem_ids = self.gsc.call(RULES_MOD, "bz_get_element_weapon_ids").to_list()
        self.assertEqual(
            elem_ids,
            ["acid_sprayer", "cryo_cannon", "multi_crossbow", "blade_boomerang"],
        )

        expected_elems = [
            ("acid_sprayer", "bz_acid_sprayer", 5000, "Acid Sprayer"),
            ("cryo_cannon", "bz_cryo_cannon", 5000, "Cryo Cannon"),
            ("multi_crossbow", "bz_multi_crossbow", 5000, "Multi-Crossbow"),
            ("blade_boomerang", "bz_blade_boomerang", 5000, "Blade Boomerang"),
        ]
        for item_id, weap_name, price, display_name in expected_elems:
            self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_valid_element_weapon", item_id))
            self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_valid_element_weapon", item_id.upper()))
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_element_weapon_name", item_id), weap_name)
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_element_weapon_id_from_weapon", weap_name), item_id)
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_element_weapon_price", item_id), price)
            disp = self.gsc.call(RULES_MOD, "bz_get_item_display_name", "element_weapon", item_id)
            self.assertEqual(disp, display_name)
            self.assertTrue(disp.isascii())

            info = self.gsc.call(RULES_MOD, "bz_get_item_info", "element_weapon", item_id)
            self.assertEqual(info.category, "element_weapon")
            self.assertEqual(info.id, item_id)
            self.assertEqual(info.price, price)
            self.assertEqual(info.display_name, display_name)
            self.assertEqual(info.weapon_name, weap_name)

        self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_valid_element_weapon", "ray_gun"))
        self.assertIs(self.gsc.call(RULES_MOD, "bz_get_element_weapon_price", "ray_gun"), UNDEFINED)
        self.assertIs(self.gsc.call(RULES_MOD, "bz_get_element_weapon_name", "ray_gun"), UNDEFINED)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_element_weapon_id_from_weapon", "ray_gun"), "")

        gear_ids = self.gsc.call(RULES_MOD, "bz_get_special_gear_ids").to_list()
        self.assertEqual(gear_ids, ["war_club", "pap_war_club", "portal_grenade"])

        expected_gear = [
            ("war_club", 5000, "", "War Club"),
            ("pap_war_club", 5000, "war_club", "PaP War Club"),
            ("portal_grenade", 5000, "", "Portal Grenade"),
        ]
        for gear_id, price, prereq, display_name in expected_gear:
            self.assertTrue(self.gsc.call(RULES_MOD, "bz_is_valid_special_gear", gear_id))
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_special_gear_price", gear_id), price)
            self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_special_gear_prereq", gear_id), prereq)
            disp = self.gsc.call(RULES_MOD, "bz_get_item_display_name", "special_gear", gear_id)
            self.assertEqual(disp, display_name)
            self.assertTrue(disp.isascii())

            info = self.gsc.call(RULES_MOD, "bz_get_item_info", "special_gear", gear_id)
            self.assertEqual(info.category, "special_gear")
            self.assertEqual(info.id, gear_id)
            self.assertEqual(info.price, price)
            self.assertEqual(info.prereq, prereq)

        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_item_display_name", "special_gear", "equip_bowie"), "Bowie Knife")
        self.assertFalse(self.gsc.call(RULES_MOD, "bz_is_valid_special_gear", "chainsaw"))
        self.assertIs(self.gsc.call(RULES_MOD, "bz_get_special_gear_price", "chainsaw"), UNDEFINED)

    def test_phase2_status_effect_and_combat_math_helpers(self) -> None:
        # Acid Sprayer: 6s puddle, 40% slow (0.60 move scale), +50% brittle (1.50x incoming damage)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_acid_puddle_duration"), 6.0, places=6)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_acid_slow_scale"), 0.60, places=6)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_acid_brittle_mult"), 1.50, places=6)

        # Cryo Cannon: 4s freeze + 2.50x shatter damage multiplier
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_cryo_freeze_duration"), 4.0, places=6)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_cryo_shatter_mult"), 2.50, places=6)

        # Wunderwaffe DG-2 chain stun duration
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_wunderwaffe_stun_duration"), 3.5, places=6)

        # Enhanced Flamethrower close-range melt vs long-range % HP burn DOT (base vs upgraded)
        r1_long_base = self.gsc.call(RULES_MOD, "bz_calc_flame_dot_damage", 1, 150, False, False)
        r10_long_base = self.gsc.call(RULES_MOD, "bz_calc_flame_dot_damage", 10, 1045, False, False)
        r10_close_base = self.gsc.call(RULES_MOD, "bz_calc_flame_dot_damage", 10, 1045, True, False)
        r10_long_up = self.gsc.call(RULES_MOD, "bz_calc_flame_dot_damage", 10, 1045, False, True)
        r10_close_up = self.gsc.call(RULES_MOD, "bz_calc_flame_dot_damage", 10, 1045, True, True)
        r30_long_up = self.gsc.call(RULES_MOD, "bz_calc_flame_dot_damage", 30, 7000, False, True)
        self.assertEqual(r1_long_base, 120)
        self.assertEqual(r10_long_base, 229)
        self.assertEqual(r10_close_base, 418)
        self.assertEqual(r10_long_up, 344)
        self.assertEqual(r10_close_up, 627)
        self.assertEqual(r30_long_up, 2310)
        self.assertGreater(r10_close_base, r10_long_base)
        self.assertGreater(r10_close_up, r10_close_base)
        self.assertGreater(r30_long_up, r10_long_up)

        # War Club melee damage & AOE radius (base cleave vs PaP frontal smash)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_war_club_damage", 150, 150, False), 600)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_war_club_damage", 150, 2000, False), 1000)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_war_club_damage", 150, 150, True), 1500)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_war_club_damage", 150, 4000, True), 4000)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_war_club_aoe_radius", False), 96)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_war_club_aoe_radius", True), 160)

        # Multi-Crossbow: 3-bolt spread, round-scaled sticky explosive damage, +75% Double PaP
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_crossbow_bolt_count"), 3)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_crossbow_bolt_damage", 1, 150, False), 900)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_crossbow_bolt_damage", 1, 150, True), 1575)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_crossbow_bolt_damage", 20, 3000, False), 2400)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_crossbow_bolt_damage", 20, 3000, True), 4200)

        # Blade Boomerang: max 6 pierces, round-scaled damage, +75% Double PaP
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_boomerang_max_pierce"), 6)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_boomerang_damage", 1, 150, False), 800)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_boomerang_damage", 1, 150, True), 1400)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_boomerang_damage", 20, 4000, False), 3000)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_calc_boomerang_damage", 20, 4000, True), 5250)

        # Portal Grenade constants
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_portal_duration"), 8.0, places=6)
        self.assertAlmostEqual(self.gsc.call(RULES_MOD, "bz_get_portal_cooldown"), 25.0, places=6)
        self.assertEqual(self.gsc.call(RULES_MOD, "bz_get_portal_max_charges"), 2)


class TestPhase2PlayerStateAndTransitions(unittest.TestCase):
    """Slice 2b: Phase 2 per-player state purchases, melee-slot free swaps, down persistence, round recharge."""

    def setUp(self) -> None:
        self.gsc = GscRuntime(MOD_ROOT)
        self.player = GscStruct()
        self.player.set_field("score", 40000)
        self.gsc.call(STATE_MOD, "bz_state_init_player", self.player)

    def test_init_defaults_and_element_weapon_purchases(self) -> None:
        self.assertEqual(self.player.get_field("bz_melee_slot"), "knife")
        self.assertFalse(self.player.get_field("bz_owns_war_club"))
        self.assertFalse(self.player.get_field("bz_pap_war_club"))
        self.assertFalse(self.player.get_field("bz_owns_bowie"))
        self.assertFalse(self.player.get_field("bz_owns_portal_grenade"))
        self.assertEqual(self.player.get_field("bz_portal_charges"), 0)

        # Buy Acid Sprayer (5000 test cap)
        res = self.gsc.call(STATE_MOD, "bz_try_buy_element_weapon", self.player, "acid_sprayer", False)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "ok")
        self.assertEqual(res.cost, 5000)
        self.assertEqual(res.weapon_name, "bz_acid_sprayer")
        self.assertEqual(self.player.get_field("score"), 35000)

        # Already held rejection does not deduct score
        dup = self.gsc.call(STATE_MOD, "bz_try_buy_element_weapon", self.player, "acid_sprayer", True)
        self.assertFalse(dup.ok)
        self.assertEqual(dup.status, "already_owned")
        self.assertEqual(self.player.get_field("score"), 35000)

        # Invalid weapon ID rejected cleanly
        bad = self.gsc.call(STATE_MOD, "bz_try_buy_element_weapon", self.player, "bfg9000", False)
        self.assertFalse(bad.ok)
        self.assertEqual(bad.status, "invalid_item")

        # Insufficient points rejection
        self.player.set_field("score", 4999)
        poor = self.gsc.call(STATE_MOD, "bz_try_buy_element_weapon", self.player, "blade_boomerang", False)
        self.assertFalse(poor.ok)
        self.assertEqual(poor.status, "insufficient_points")
        self.assertEqual(self.player.get_field("score"), 4999)

    def test_melee_slot_war_club_purchase_pap_prereq_and_free_bowie_swap(self) -> None:
        # PaP War Club requires War Club first
        no_club = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "pap_war_club", False)
        self.assertFalse(no_club.ok)
        self.assertEqual(no_club.status, "missing_prereq")

        # Buying Bowie Knife when unowned succeeds for 3000 pts (cross-map Arsenal support)
        # Reject cleanly if player has insufficient points first
        self.player.set_field("score", 2999)
        poor_bowie = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "equip_bowie", False)
        self.assertFalse(poor_bowie.ok)
        self.assertEqual(poor_bowie.status, "insufficient_points")
        self.assertEqual(poor_bowie.cost, 3000)
        self.player.set_field("score", 40000)

        # Acquire War Club (5000 pts) -> equips war_club
        buy_wc = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "war_club", False)
        self.assertTrue(buy_wc.ok)
        self.assertEqual(buy_wc.cost, 5000)
        self.assertFalse(buy_wc.swapped)
        self.assertTrue(self.player.get_field("bz_owns_war_club"))
        self.assertEqual(self.player.get_field("bz_melee_slot"), "war_club")
        self.assertEqual(self.player.get_field("score"), 35000)

        # Clicking War Club while already equipped returns already_owned at 0 charge
        dup_wc = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "war_club", False)
        self.assertFalse(dup_wc.ok)
        self.assertEqual(dup_wc.status, "already_owned")
        self.assertEqual(self.player.get_field("score"), 35000)

        # Upgrade PaP War Club (5000 pts)
        buy_pap_wc = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "pap_war_club", False)
        self.assertTrue(buy_pap_wc.ok)
        self.assertEqual(buy_pap_wc.cost, 5000)
        self.assertTrue(self.player.get_field("bz_pap_war_club"))
        self.assertEqual(self.player.get_field("score"), 30000)

        # Player also owns Bowie Knife -> free swap to Bowie (0 pts)
        swap_bowie = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "equip_bowie", True)
        self.assertTrue(swap_bowie.ok)
        self.assertEqual(swap_bowie.cost, 0)
        self.assertTrue(swap_bowie.swapped)
        self.assertEqual(self.player.get_field("bz_melee_slot"), "bowie")
        self.assertTrue(self.player.get_field("bz_owns_bowie"))
        self.assertEqual(self.player.get_field("score"), 30000)

        # Free swap back to owned War Club (0 pts)
        swap_wc = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "war_club", True)
        self.assertTrue(swap_wc.ok)
        self.assertEqual(swap_wc.cost, 0)
        self.assertTrue(swap_wc.swapped)
        self.assertEqual(self.player.get_field("bz_melee_slot"), "war_club")
        self.assertEqual(self.player.get_field("score"), 30000)

    def test_sync_bowie_ownership_switches_war_club_to_bowie_only_on_first_wall_buy_acquisition(self) -> None:
        # Player acquires War Club FIRST without owning Bowie
        buy_wc = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "war_club", False)
        self.assertTrue(buy_wc.ok)
        self.assertEqual(self.player.get_field("bz_melee_slot"), "war_club")
        self.assertFalse(self.player.get_field("bz_owns_bowie"))

        # Newly acquiring stock Bowie Knife off the wall transitions bz_owns_bowie false -> true
        # and switches bz_melee_slot to "bowie" so Bowie + War Club never stack.
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_sync_bowie_ownership", self.player, True))
        self.assertTrue(self.player.get_field("bz_owns_bowie"))
        self.assertEqual(self.player.get_field("bz_melee_slot"), "bowie")

        # After player explicitly free-swaps back to War Club, subsequent sync calls preserve "war_club"
        swap_back = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "war_club", True)
        self.assertTrue(swap_back.ok)
        self.assertTrue(swap_back.swapped)
        self.assertEqual(self.player.get_field("bz_melee_slot"), "war_club")
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_sync_bowie_ownership", self.player, True))
        self.assertEqual(self.player.get_field("bz_melee_slot"), "war_club")

    def test_portal_grenade_purchase_consumption_round_recharge_and_down_persistence(self) -> None:
        # Buy perks + War Club + PaP War Club + Portal Grenade
        self.gsc.call(STATE_MOD, "bz_try_buy_perk", self.player, "juggernog")
        self.gsc.call(STATE_MOD, "bz_try_buy_perk", self.player, "mule_kick")
        self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "war_club", True)
        self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "pap_war_club", True)

        portal = self.gsc.call(STATE_MOD, "bz_try_buy_special_gear", self.player, "portal_grenade", True)
        self.assertTrue(portal.ok)
        self.assertEqual(portal.cost, 5000)
        self.assertTrue(self.player.get_field("bz_owns_portal_grenade"))
        self.assertEqual(self.player.get_field("bz_portal_charges"), 2)

        # Consume both charges cleanly, 3rd returns False
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_try_consume_portal_charge", self.player))
        self.assertEqual(self.player.get_field("bz_portal_charges"), 1)
        self.assertTrue(self.gsc.call(STATE_MOD, "bz_state_try_consume_portal_charge", self.player))
        self.assertEqual(self.player.get_field("bz_portal_charges"), 0)
        self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_try_consume_portal_charge", self.player))

        # Down clears perks but strictly preserves War Club, PaP War Club, melee slot, and Portal Grenade
        down_summary = self.gsc.call(STATE_MOD, "bz_state_on_player_downed", self.player, 3)
        self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_has_perk", self.player, "juggernog"))
        self.assertFalse(self.gsc.call(STATE_MOD, "bz_state_has_perk", self.player, "mule_kick"))
        self.assertEqual(self.player.get_field("bz_melee_slot"), "war_club")
        self.assertTrue(self.player.get_field("bz_owns_war_club"))
        self.assertTrue(self.player.get_field("bz_pap_war_club"))
        self.assertTrue(self.player.get_field("bz_owns_portal_grenade"))
        self.assertEqual(down_summary.preserved_melee_slot, "war_club")
        self.assertTrue(down_summary.preserved_war_club)
        self.assertTrue(down_summary.preserved_pap_war_club)
        self.assertTrue(down_summary.preserved_portal_grenade)

        # Round start refills portal charges to max (2)
        round_summary = self.gsc.call(STATE_MOD, "bz_state_on_round_start", self.player)
        self.assertTrue(round_summary.portal_recharged)
        self.assertEqual(round_summary.portal_charges, 2)
        self.assertEqual(self.player.get_field("bz_portal_charges"), 2)


class TestArsenalStationPhase2AndMenus(unittest.TestCase):
    """Slice 3: Arsenal Station buy_element/buy_gear end-to-end, bz_menus.inc, & WaW 1.7 compliance."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzGscRuntime(MOD_ROOT, self.dvars)
        self.p1 = FakeEntity("PlayerOne", ent_num=0)
        self.p1.set_field("score", 80000)
        self.p1.give_weapon("thompson", make_current=True)
        self.p1.give_perk("specialty_altmelee")
        self.p1.set_field("has_altmelee", True)
        self.gsc.players.append(self.p1)

    def test_arsenal_phase2_purchases_respect_elements_gate_and_classic_mode_noop(self) -> None:
        # Classic Mode (bz_enabled=0) -> strict noop
        self.dvars.set("bz_enabled", "0")
        self.dvars.set("bz_elements_enabled", "1")
        self.assertFalse(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:acid_sprayer")
        )
        self.assertEqual(self.p1.get_field("score"), 80000)
        self.assertEqual(self.gsc.emitted_events, [])

        # bz_enabled=1 but bz_elements_enabled=0 -> gate_disabled rejection, zero score loss
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")
        self.dvars.set("bz_elements_enabled", "0")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:acid_sprayer")
        )
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_gear:war_club")
        )
        self.assertEqual(self.p1.get_field("score"), 80000)
        self.assertNotIn("bz_acid_sprayer", self.p1.weapons)
        self.assertEqual(self.p1.client_dvars.get("ui_bz_elem_acid_sprayer"), "DISABLED")
        self.assertIn(
            "BZ_EVENT|STATION_PURCHASE|player=PlayerOne;menu=bz_station_arsenal;category=element_weapon;item=acid_sprayer;status=gate_disabled;cost=0;score=80000",
            self.gsc.emitted_events,
        )
        self.assertIn(
            "BZ_EVENT|STATION_PURCHASE|player=PlayerOne;menu=bz_station_arsenal;category=special_gear;item=war_club;status=gate_disabled;cost=0;score=80000",
            self.gsc.emitted_events,
        )

    def test_elemental_ammo_purchase_refreshes_all_four_arsenal_pills(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_elements_enabled", "1")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        menu = "bz_station_arsenal"
        for item_id, display_name, base_stock in (
            ("acid_sprayer", "Acid Sprayer", 120),
            ("cryo_cannon", "Cryo Cannon", 96),
            ("multi_crossbow", "Multi-Crossbow", 36),
        ):
            with self.subTest(item_id=item_id):
                weapon = "bz_" + item_id
                pill = "ui_bz_elem_" + item_id
                action = "buy_element:" + item_id
                self.gsc.call(STATIONS_MOD, "bz_stations_sync_player_ui", self.p1)
                self.assertEqual(self.p1.client_dvars[pill], "BUY 5000")
                self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, menu, action))
                self.assertEqual(self.p1.client_dvars[pill], "FULL")

                self.p1.weapon_clips[weapon] = 29
                self.gsc.call(STATIONS_MOD, "bz_stations_sync_player_ui", self.p1)
                self.assertEqual(self.p1.client_dvars[pill], "AMMO 2500")
                self.p1.weapon_stocks[weapon] = base_stock - 1
                score = self.p1.get_field("score")
                self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, menu, action))
                self.assertEqual(self.p1.get_field("score"), score - 2500)
                self.assertEqual(self.p1.weapon_clips[weapon], 30)
                self.assertEqual(self.p1.weapon_stocks[weapon], base_stock)
                self.assertEqual(self.p1.client_dvars[pill], "FULL")
                self.assertEqual(self.p1.client_dvars["ui_bz_feedback"], f"Refilled {display_name} ammo (-2500)")
                self.assertEqual(self.gsc.played_local_sounds, [(self.p1, "cha_ching")] * 2)
                self.gsc.played_local_sounds.clear()
                self.assertIn(
                    f"BZ_EVENT|STATION_PURCHASE|player=PlayerOne;menu={menu};category=element_ammo;"
                    f"item={item_id};status=ok;cost=2500;score={score - 2500}",
                    self.gsc.emitted_events,
                )

        # Blade Boomerang is a single infinite-use throwable (1/0): displays OWNED and never charges ammo refills.
        self.gsc.call(STATIONS_MOD, "bz_stations_sync_player_ui", self.p1)
        self.assertEqual(self.p1.client_dvars["ui_bz_elem_blade_boomerang"], "BUY 5000")
        self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, menu, "buy_element:blade_boomerang"))
        self.assertEqual(self.p1.client_dvars["ui_bz_elem_blade_boomerang"], "OWNED")
        self.assertEqual(self.p1.weapon_stocks["bz_blade_boomerang"], 0)
        score_before_boom = self.p1.get_field("score")
        self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, menu, "buy_element:blade_boomerang"))
        self.assertEqual(self.p1.get_field("score"), score_before_boom)
        self.assertEqual(self.p1.client_dvars["ui_bz_elem_blade_boomerang"], "OWNED")

    def test_elemental_ammo_purchase_rejects_full_and_insufficient_points(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_elements_enabled", "1")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        menu = "bz_station_arsenal"
        action = "buy_element:acid_sprayer"
        weapon = "bz_acid_sprayer"
        self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, menu, action))
        self.p1.set_field("score", 2499)

        self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, menu, action))
        self.assertEqual(self.p1.get_field("score"), 2499)
        self.assertEqual(self.p1.client_dvars["ui_bz_feedback"], "Acid Sprayer ammo already full")
        event = f"BZ_EVENT|STATION_PURCHASE|player=PlayerOne;menu={menu};category=element_ammo;item=acid_sprayer"
        self.assertIn(event + ";status=already_full;cost=0;score=2499", self.gsc.emitted_events)

        self.p1.weapon_stocks[weapon] = 119
        self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, menu, action))
        self.assertEqual(self.p1.get_field("score"), 2499)
        self.assertEqual(self.p1.weapon_stocks[weapon], 119)
        self.assertEqual(self.p1.weapon_clips[weapon], 30)
        self.assertEqual(self.p1.client_dvars["ui_bz_elem_acid_sprayer"], "AMMO 2500")
        self.assertEqual(self.p1.client_dvars["ui_bz_feedback"], "Need 2500 pts for Acid Sprayer Ammo")
        self.assertIn(event + ";status=insufficient_points;cost=2500;score=2499", self.gsc.emitted_events)
        self.assertEqual(
            self.gsc.played_local_sounds,
            [(self.p1, "cha_ching"), (self.p1, "no_cha_ching"), (self.p1, "no_cha_ching")],
        )

    def test_elemental_ammo_refills_scale_reserve_and_update_existing_pap_cache(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_elements_enabled", "1")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        self.gsc.call(STATE_MOD, "bz_state_ensure_init", self.p1)
        weapon = "bz_multi_crossbow"
        self.p1.give_weapon(weapon)
        cache = GscArray()
        self.p1.set_field("bz_pap_target_stock", cache)

        for double_ammo, double_pap, expected in (
            (False, False, 36),
            (False, True, 54),
            (True, False, 72),
            (True, True, 108),
        ):
            with self.subTest(double_ammo=double_ammo, double_pap=double_pap):
                self.p1.get_field("bz_apex_perks").set_item("double_ammo", double_ammo)
                self.p1.get_field("bz_double_pap_weapons").set_item(weapon, double_pap)
                self.assertEqual(
                    self.gsc.call(STATIONS_MOD, "bz_stations_get_element_target_stock", self.p1, weapon),
                    expected,
                )
                self.p1.weapon_clips = {weapon: 30}
                self.p1.weapon_stocks = {weapon: expected - 1}
                self.p1.set_field("score", 2500)
                cache.set_item(weapon, expected - 1)
                self.assertTrue(
                    self.gsc.call(
                        BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:multi_crossbow"
                    )
                )
                self.assertEqual(self.p1.get_field("score"), 0)
                self.assertEqual(self.p1.weapon_stocks[weapon], expected)
                self.assertEqual(cache[weapon], expected)
                self.assertEqual(self.p1.client_dvars["ui_bz_elem_multi_crossbow"], "FULL")
                self.assertEqual(self.p1.current_weapon, "thompson")

    def test_elemental_ammo_falls_back_to_120_reserve_and_supports_clipless_weapons(self) -> None:
        weapon = "bz_custom_clipless"
        self.p1.give_weapon(weapon)
        original_builtin = self.gsc._call_builtin
        for max_ammo in (UNDEFINED, 0, -1):
            def weapon_builtin(name, args, line):
                if name == "weaponmaxammo":
                    return True, max_ammo
                if name == "weaponclipsize":
                    return True, 0
                return original_builtin(name, args, line)

            with self.subTest(max_ammo=max_ammo), patch.object(self.gsc, "_call_builtin", side_effect=weapon_builtin):
                self.p1.weapon_stocks = {weapon: 7}
                self.assertFalse(self.gsc.call(STATIONS_MOD, "bz_stations_is_element_ammo_full", self.p1, weapon))
                self.gsc.call(STATIONS_MOD, "bz_stations_refill_element_ammo", self.p1, weapon)
                self.assertEqual(self.p1.weapon_stocks[weapon], 120)
                self.assertIs(self.p1.weapon_clips, UNDEFINED)
                self.assertTrue(self.gsc.call(STATIONS_MOD, "bz_stations_is_element_ammo_full", self.p1, weapon))

    def test_arsenal_element_ammo_refill_handles_waw17_engine_stock_clamp(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")
        self.dvars.set("bz_elements_enabled", "1")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

        weapon = "bz_acid_sprayer"
        self.p1.set_field("score", 30000)
        self.p1.weapons = {weapon}
        self.p1.weapon_stocks = {weapon: 0}
        self.p1.weapon_clips = {weapon: 0}
        self.gsc.call(STATE_MOD, "bz_state_mark_weapon_double_pap", self.p1, weapon)
        self.gsc.call(STATE_MOD, "bz_try_buy_apex", self.p1, "double_ammo")

        orig_exec = self.gsc._exec_method
        orig_builtin = self.gsc._call_builtin

        # 1. Under the built weaponfile maxAmmo=360 (3x base 120), Arsenal refill delivers the full 360 reserve.
        def real_acid_builtin(name, args, line):
            if name == "weaponmaxammo" and args and args[0] == weapon:
                return True, 360
            if name == "weaponclipsize" and args and args[0] == weapon:
                return True, 20
            return orig_builtin(name, args, line)

        def real_acid_exec(receiver, method, args, line):
            if method == "setweaponammostock" and len(args) >= 2:
                return orig_exec(receiver, method, [args[0], min(int(args[1]), 360)], line)
            return orig_exec(receiver, method, args, line)

        with patch.object(self.gsc, "_call_builtin", side_effect=real_acid_builtin), patch.object(
            self.gsc, "_exec_method", side_effect=real_acid_exec
        ):
            score_before = int(self.p1.get_field("score"))
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:acid_sprayer")
            self.assertEqual(int(self.p1.get_field("score")), score_before - 2500)
            self.assertEqual(self.p1.weapon_stocks[weapon], 360)
            self.assertEqual(self.p1.weapon_clips[weapon], 20)
            self.assertEqual(self.p1.get_field("bz_pap_target_stock")[weapon], 360)
            self.assertTrue(self.gsc.call(STATIONS_MOD, "bz_stations_is_element_ammo_full", self.p1, weapon))
            self.assertEqual(self.p1.client_dvars["ui_bz_elem_acid_sprayer"], "FULL")

            # Clicking again while full at 360 must reject already_full with 0 pts spent.
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:acid_sprayer")
            self.assertEqual(int(self.p1.get_field("score")), score_before - 2500)
            self.assertIn("already full", self.p1.client_dvars["ui_bz_feedback"].lower())

        # 2. If a weapon's engine WeaponMaxAmmo is lower than target_stock, fullness still prevents repeat charges.
        self.p1.weapon_stocks = {weapon: 160}
        self.p1.weapon_clips = {weapon: 30}
        score_before_clamp = int(self.p1.get_field("score"))
        self.assertTrue(self.gsc.call(STATIONS_MOD, "bz_stations_is_element_ammo_full", self.p1, weapon))
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:acid_sprayer")
        self.assertEqual(int(self.p1.get_field("score")), score_before_clamp)
        self.assertIn("already full", self.p1.client_dvars["ui_bz_feedback"].lower())

    def test_arsenal_phase2_buy_element_and_buy_gear_end_to_end_with_melee_swaps_and_ui_dvars(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")
        self.dvars.set("bz_elements_enabled", "1")

        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

        dispatched: list[tuple[str, str, int, str]] = []
        self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "item_purchased",
            self.gsc.register_py_callback(
                "p2_purchase_cb",
                lambda _s, ctx: dispatched.append(
                    (
                        ctx.get_field("category"),
                        ctx.get_field("item_id"),
                        int(ctx.get_field("result").get_field("cost")),
                        ctx.get_field("weapon_name"),
                    )
                ),
            ),
            "elements",
        )

        # Grant Mule Kick I (3 slots) so player can hold thompson + acid_sprayer + cryo_cannon
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_perk:mule_kick")
        self.assertEqual(self.p1.get_field("score"), 76000)

        # 1. Buy Acid Sprayer (5000 test cap)
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:acid_sprayer")
        )
        self.assertEqual(self.p1.get_field("score"), 71000)
        self.assertIn("bz_acid_sprayer", self.p1.weapons)
        self.assertEqual(self.p1.current_weapon, "bz_acid_sprayer")
        self.assertEqual(self.p1.client_dvars["ui_bz_elem_acid_sprayer"], "FULL")
        self.assertEqual(self.p1.client_dvars["ui_bz_elem_cryo_cannon"], "BUY 5000")

        # 2. Buy Cryo Cannon (5000 test cap) -> fills 3rd Mule Kick slot without dropping thompson
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:cryo_cannon")
        )
        self.assertEqual(self.p1.get_field("score"), 66000)
        self.assertIn("thompson", self.p1.weapons)
        self.assertIn("bz_acid_sprayer", self.p1.weapons)
        self.assertIn("bz_cryo_cannon", self.p1.weapons)

        # 3. Buy Multi-Crossbow (5000 test cap) -> at 3-slot cap, replaces current weapon (bz_cryo_cannon)
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:multi_crossbow")
        )
        self.assertEqual(self.p1.get_field("score"), 61000)
        self.assertIn("bz_multi_crossbow", self.p1.weapons)
        self.assertEqual(len(self.p1.weapons), 3)

        # 4. Buy Blade Boomerang (5000 test cap)
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_element:blade_boomerang")
        )
        self.assertEqual(self.p1.get_field("score"), 56000)
        self.assertIn("bz_blade_boomerang", self.p1.weapons)

        # 5. Buy War Club (5000) -> unsets specialty_altmelee per ADR-0003 while preserving bz_owns_bowie
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_gear:war_club")
        )
        self.assertEqual(self.p1.get_field("score"), 51000)
        self.assertFalse(self.p1.has_perk("specialty_altmelee"))
        self.assertFalse(self.p1.get_field("has_altmelee"))
        self.assertEqual(self.p1.get_field("bz_melee_slot"), "war_club")
        self.assertTrue(self.p1.get_field("bz_owns_bowie"))
        self.assertEqual(self.p1.client_dvars["ui_bz_melee_slot"], "MELEE: WAR CLUB")
        self.assertEqual(self.p1.client_dvars["ui_bz_gear_war_club"], "EQUIPPED")
        self.assertEqual(self.p1.client_dvars["ui_bz_gear_equip_bowie"], "EQUIP FREE")

        # 6. Upgrade PaP War Club (5000)
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_gear:pap_war_club")
        )
        self.assertEqual(self.p1.get_field("score"), 46000)
        self.assertEqual(self.p1.client_dvars["ui_bz_melee_slot"], "MELEE: PAP WAR CLUB")
        self.assertEqual(self.p1.client_dvars["ui_bz_gear_pap_war_club"], "OWNED")

        # PaP Bowie does not interfere while War Club is the active melee slot
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_pap:pap_bowie")
        z_dummy = FakeEntity("zombie_0", ent_num=20, is_player=False)
        z_dummy.set_field("health", 5000)
        z_dummy.set_field("maxhealth", 5000)
        wc_melee_dmg = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_dummy,
            self.p1,
            self.p1,
            150,
            0,
            "MOD_MELEE",
            "none",
            GscArray([0, 0, 0]),
            GscArray([0, 0, 0]),
            "torso_upper",
            0,
        )
        # PaP Bowie defers while War Club is equipped; PaP War Club applies its heavy smash (5000 vs 20000 HP zombie, NOT 1-hit kill)
        self.assertEqual(wc_melee_dmg, 5000)

        # 7. Free swap back to owned Bowie Knife (0 pts) -> restores specialty_altmelee & PaP Bowie 1-hit kill
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_gear:equip_bowie")
        )
        self.assertEqual(self.p1.get_field("score"), 41000)
        self.assertTrue(self.p1.has_perk("specialty_altmelee"))
        self.assertTrue(self.p1.get_field("has_altmelee"))
        self.assertEqual(self.p1.get_field("bz_melee_slot"), "bowie")
        self.assertEqual(self.p1.client_dvars["ui_bz_melee_slot"], "MELEE: PAP BOWIE")
        self.assertEqual(self.p1.client_dvars["ui_bz_gear_war_club"], "EQUIP FREE")
        self.assertIn("Free swap", self.p1.client_dvars["ui_bz_feedback"])
        bowie_melee_dmg = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_dummy,
            self.p1,
            self.p1,
            1000,
            0,
            "MOD_MELEE",
            "none",
            GscArray([0, 0, 0]),
            GscArray([0, 0, 0]),
            "torso_upper",
            0,
        )
        self.assertGreaterEqual(bowie_melee_dmg, 5000)

        # 8. Buy Portal Grenade (5000 test cap)
        self.assertTrue(
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_gear:portal_grenade")
        )
        self.assertEqual(self.p1.get_field("score"), 36000)
        self.assertEqual(self.p1.client_dvars["ui_bz_portal"], "READY (2)")

        self.assertEqual(
            dispatched,
            [
                ("perk", "mule_kick", 4000, "thompson"),
                ("element_weapon", "acid_sprayer", 5000, "bz_acid_sprayer"),
                ("element_weapon", "cryo_cannon", 5000, "bz_cryo_cannon"),
                ("element_weapon", "multi_crossbow", 5000, "bz_multi_crossbow"),
                ("element_weapon", "blade_boomerang", 5000, "bz_blade_boomerang"),
                ("special_gear", "war_club", 5000, "bz_blade_boomerang"),
                ("special_gear", "pap_war_club", 5000, "bz_blade_boomerang"),
                ("pap", "pap_bowie", 5000, "bz_blade_boomerang"),
                ("special_gear", "equip_bowie", 0, "bz_blade_boomerang"),
                ("special_gear", "portal_grenade", 5000, "bz_blade_boomerang"),
            ],
        )

    def test_arsenal_menu_bz_menus_inc_and_waw17_gsc_compliance(self) -> None:
        import verify_hud_menus

        ui_dir = MOD_ROOT / "ui"
        arsenal_text = (ui_dir / "bz_station_arsenal.menu").read_text(encoding="latin1")
        bz_inc_text = (ui_dir / "bz_menus.inc").read_text(encoding="latin1")
        gauntlet_inc_text = (ui_dir / "gauntlet_menus.inc").read_text(encoding="latin1")

        # Brace balance & ASCII strictness
        for fname, content in (("bz_station_arsenal.menu", arsenal_text), ("bz_menus.inc", bz_inc_text)):
            self.assertEqual(verify_hud_menus.validate_menu_braces(content, filename=fname), [])
            non_ascii = [ch for ch in content if ord(ch) > 126 or (ord(ch) < 32 and ch not in "\t\r\n")]
            self.assertEqual(non_ascii, [], f"Non-ASCII chars in {fname}: {non_ascii!r}")

        # All Phase 2 clickable buttons present in bz_station_arsenal.menu
        found_tokens = set(re.findall(r'scriptMenuResponse\s+"([^"]+)"\s*;', arsenal_text))
        expected_tokens = {
            "buy_pap:pap_knife",
            "buy_pap:pap_bowie",
            "buy_pap:pap_cluster",
            "buy_element:acid_sprayer",
            "buy_element:cryo_cannon",
            "buy_element:multi_crossbow",
            "buy_element:blade_boomerang",
            "buy_gear:war_club",
            "buy_gear:pap_war_club",
            "buy_gear:equip_bowie",
            "buy_gear:portal_grenade",
            "close",
        }
        self.assertEqual(found_tokens, expected_tokens)
        self.assertIn("Phase 3", arsenal_text)
        self.assertIn("SQUAD COMPANIONS", arsenal_text)
        for line in arsenal_text.splitlines():
            if "exp" in line and "text(" in line:
                self.assertTrue(line.rstrip().endswith(";"), f"Missing semicolon: {line}")

        # Enhancements launch macros in bz_menus.inc enable bz_elements_enabled 1
        for macro in (
            "BZ_SOLO_START_ACTION",
            "BZ_SOLO_START_PROTOTYPE_ACTION",
            "BZ_SOLO_START_ASYLUM_ACTION",
            "BZ_SOLO_START_SUMPF_ACTION",
            "BZ_COOP_ACCEPT_ACTION",
        ):
            m = re.search(rf"#define\s+{macro}\b.*?(?:\n\n|\Z)", bz_inc_text, re.DOTALL)
            self.assertIsNotNone(m, f"Missing macro {macro}")
            self.assertIn("set bz_elements_enabled 1", m.group(0), f"{macro} must enable bz_elements_enabled 1")

        # Classic Mode and Classic Gauntlet macros keep bz_elements_enabled 0,
        # while Enhanced Gauntlet enables bz_elements_enabled 1 cleanly.
        classic_m = re.search(r"#define\s+BZ_CLASSIC_MODE_ACTION\b.*?(?:\n\n|\Z)", bz_inc_text, re.DOTALL)
        self.assertIsNotNone(classic_m)
        self.assertIn("set bz_elements_enabled 0", classic_m.group(0))
        for classic_gauntlet_macro in ("GAUNTLET_SOLO_START_ACTION", "GAUNTLET_CLASSIC_MODE_ACTION"):
            gm = re.search(rf"#define\s+{classic_gauntlet_macro}\b.*?(?:\n\n|\Z)", gauntlet_inc_text, re.DOTALL)
            self.assertIsNotNone(gm, f"Missing macro {classic_gauntlet_macro}")
            self.assertIn("set bz_elements_enabled 0", gm.group(0))
            self.assertNotIn("set bz_elements_enabled 1", gm.group(0))
        enh_gm = re.search(r"#define\s+GAUNTLET_ENHANCED_SOLO_START_ACTION\b.*?(?:\n\n|\Z)", gauntlet_inc_text, re.DOTALL)
        self.assertIsNotNone(enh_gm)
        self.assertIn("set bz_elements_enabled 1", enh_gm.group(0))

        # WaW 1.7 GSC compliance: zero foreach, clean tokenization, zero endon in sync callers
        gsc = BzGscRuntime(MOD_ROOT, FakeDvarStore())
        for rel in ("_bz_rules.gsc", "_bz_state.gsc", "_bz_hooks.gsc", "_bz_stations.gsc"):
            path = MOD_ROOT / "maps" / rel
            src = path.read_text(encoding="latin1")
            tokenize(src, filename=str(path))
            code_only = "\n".join(line.split("//", 1)[0] for line in src.splitlines())
            self.assertIsNone(re.search(r"\bforeach\b", code_only), f"Forbidden foreach in {rel}")

        hooks_mod = gsc.load_module(BZ_HOOKS_MOD)
        for fn in ("bz_precache_element_weapons", "bz_register_box_weapons", "bz_on_weapon_fired"):
            self.assertIn(fn, hooks_mod)
            self.assertFalse(_ast_contains_method_call(hooks_mod[fn].body, "endon"))

        state_mod = gsc.load_module(STATE_MOD)
        for fn in ("bz_try_buy_element_weapon", "bz_try_buy_special_gear", "bz_state_on_player_downed", "bz_state_on_round_start"):
            self.assertIn(fn, state_mod)
            self.assertFalse(_ast_contains_method_call(state_mod[fn].body, "endon"))


if __name__ == "__main__":
    unittest.main()
