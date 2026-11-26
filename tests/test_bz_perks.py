"""Offline TDD contract tests for P1-T4 (#15): Perks Expansion.

Tests observable behavior of `mod/maps/_bz_perks.gsc` through an extended WaW 1.7
GSC runtime built on `tests/gsc_runtime.py` + `tests/test_bz_hooks_and_build.py`
(without modifying either):
  1. Hook registration (`bz_perks_register()`), `"perks"` gate / Classic isolation,
     stock perk pickup sync -> `_bz_state` & `bz_stations_sync_player_ui`.
  2. New Standard Perks: Stamin-Up, Mule Kick (3rd slot), Armor Piercing (+35% bullet).
  3. All 7 Perk Tier 2 upgrades: Juggernog II (220 HP + Titan 440 HP composition),
     Speed Cola II, Double Tap II (+25% bullet), Quick Revive II (faster revive,
     2s post-revive invuln for both, extra Solo revive), Stamin-Up II (+25% speed +
     ADS strafe), Mule Kick II (4th slot), AP II (+60% bullet + 1.25x limb/armor).
  4. All 4 Apex Perks: Double Ammo (2x reserve + Double PaP 3x + Max Ammo/wall refills),
     Lightweight Heavy (dynamic weapon weight compensation composing with Stamin-Up &
     Daredevil), Second Chance (lethal save, heal, pushback + 3s stun, 2s invuln,
     round-start recharge), Blast Shield (self explosive/splash/fire/fall immunity).
  5. Down reset (Mule Kick 3rd & 4th weapon strip, modifier clear, Class/PaP preservation,
     telemetry) + compact ASCII right-lane HUD with zero disconnect/end_game leaks.
  6. WaW 1.7 GSC compliance (zero `foreach`, zero `endon` in synchronous callers,
     ASCII-only HUD/telemetry).
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_ROOT = REPO_ROOT / "mod"
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tests.gsc_runtime import (  # noqa: E402
    FakeDvarStore,
    GscArray,
    GscRuntimeError,
    GscStruct,
    UNDEFINED,
    _waw_to_str,
    tokenize,
)
from tests.test_bz_hooks_and_build import (  # noqa: E402
    BZ_HOOKS_MOD,
    BzGscRuntime,
    FakeEntity,
    _ast_contains_method_call,
)

BZ_PERKS_MOD = "maps\\_bz_perks"
BZ_PERKS_PATH = MOD_ROOT / "maps" / "_bz_perks.gsc"
BZ_STATIONS_MOD = "maps\\_bz_stations"
BZ_STATE_MOD = "maps\\_bz_state"
BZ_RULES_MOD = "maps\\_bz_rules"


class FakeHudElem(GscStruct):
    """Fake WaW 1.7 HUD element returned by NewClientHudElem()."""

    def __init__(self, owner: Any = None) -> None:
        super().__init__()
        self.owner = owner
        self.text: str = ""
        self.set_text_calls: list[str] = []
        self.destroyed: bool = False


class PerksFakeEntity(FakeEntity):
    """Extended FakeEntity with WaW 1.7 weapon, ammo, perk, ADS, and HUD methods."""

    def __init__(self, name: str = "player_0", ent_num: int = 0, is_player: bool = True) -> None:
        super().__init__(name=name, ent_num=ent_num, is_player=is_player)
        self.primary_weapons: list[str] = []
        self.weapon_stock: dict[str, int] = {}
        self.weapon_clip: dict[str, int] = {}
        self.ads_frac: float = 0.0
        self.taken_weapons: list[str] = []
        self.switched_weapons: list[str] = []
        self.set_field("origin", GscArray([0, 0, 0]))

    def give_weapon(self, weapon: str, make_current: bool = False, stock: int = 120) -> None:
        norm = weapon.lower()
        super().give_weapon(norm, make_current=make_current)
        if norm not in self.primary_weapons:
            self.primary_weapons.append(norm)
        self.weapon_stock[norm] = stock
        if make_current or self.current_weapon == "colt":
            if make_current:
                self.current_weapon = norm

    def take_weapon(self, weapon: str) -> None:
        norm = weapon.lower()
        self.taken_weapons.append(norm)
        self.weapons.discard(norm)
        if norm in self.primary_weapons:
            self.primary_weapons.remove(norm)
        self.weapon_stock.pop(norm, None)
        if self.current_weapon == norm:
            self.current_weapon = self.primary_weapons[0] if self.primary_weapons else "none"

    def unset_perk(self, perk: str) -> None:
        self._perks.discard(perk.lower())


class BzPerksRuntime(BzGscRuntime):
    """Extended BzGscRuntime adding WaW 1.7 weapon/ammo/AI/HUD builtins for _bz_perks.gsc."""

    def __init__(self, mod_root: Path, dvars: FakeDvarStore | None = None) -> None:
        super().__init__(mod_root, dvars)
        self.zombies: list[PerksFakeEntity] = []
        self.hud_elems: list[FakeHudElem] = []
        self.weapon_max_ammo: dict[str, int] = {
            "colt": 80,
            "thompson": 200,
            "thompson_upgraded": 300,
            "mp40": 192,
            "stg44": 180,
            "zombie_mg42": 500,
            "zombie_mg42_upgraded": 625,
            "zombie_30cal": 450,
            "zombie_bar": 140,
            "panzerschrek": 20,
            "ray_gun": 160,
            "m2_flamethrower": 100,
            "tesla_gun": 15,
            "ptrs41": 60,
        }

    def _call_builtin(self, name_lower: str, args: list[Any], line: int) -> tuple[bool, Any]:
        if name_lower == "weaponmaxammo":
            w = _waw_to_str(args[0]).lower() if args else ""
            return True, self.weapon_max_ammo.get(w, 120)
        if name_lower == "getaispeciesarray":
            return True, GscArray(list(self.zombies))
        if name_lower == "newclienthudelem":
            owner = args[0] if args else UNDEFINED
            hud = FakeHudElem(owner=owner)
            self.hud_elems.append(hud)
            return True, hud
        return super()._call_builtin(name_lower, args, line)

    def _exec_method(self, receiver: Any, method: str, args: list[Any], line: int) -> Any:
        if isinstance(receiver, FakeHudElem):
            if method == "settext":
                txt = _waw_to_str(args[0]) if args else ""
                receiver.text = txt
                receiver.set_text_calls.append(txt)
                return UNDEFINED
            if method == "destroy":
                receiver.destroyed = True
                return UNDEFINED
            raise GscRuntimeError(f"line {line}: unsupported HUD method {method!r}")

        if method == "setperk":
            if isinstance(receiver, FakeEntity):
                receiver.give_perk(_waw_to_str(args[0]) if args else "")
            return UNDEFINED
        if method == "unsetperk":
            if isinstance(receiver, PerksFakeEntity):
                receiver.unset_perk(_waw_to_str(args[0]) if args else "")
            elif isinstance(receiver, FakeEntity):
                receiver._perks.discard((_waw_to_str(args[0]) if args else "").lower())
            return UNDEFINED
        if method == "getweaponslistprimaries":
            if isinstance(receiver, PerksFakeEntity):
                return GscArray(list(receiver.primary_weapons))
            if isinstance(receiver, FakeEntity):
                return GscArray(sorted(receiver.weapons))
            return GscArray([])
        if method == "takeweapon":
            if isinstance(receiver, PerksFakeEntity):
                receiver.take_weapon(_waw_to_str(args[0]) if args else "")
            return UNDEFINED
        if method == "switchtoweapon":
            if isinstance(receiver, PerksFakeEntity):
                w = _waw_to_str(args[0]).lower() if args else ""
                receiver.current_weapon = w
                receiver.switched_weapons.append(w)
            return UNDEFINED
        if method == "getweaponammostock":
            if isinstance(receiver, PerksFakeEntity):
                w = _waw_to_str(args[0]).lower() if args else ""
                return receiver.weapon_stock.get(w, 0)
            return 0
        if method == "setweaponammostock":
            if isinstance(receiver, PerksFakeEntity):
                w = _waw_to_str(args[0]).lower() if len(args) > 0 else ""
                amt = int(args[1]) if len(args) > 1 else 0
                receiver.weapon_stock[w] = amt
            return UNDEFINED
        if method == "playerads":
            if isinstance(receiver, PerksFakeEntity):
                return receiver.ads_frac
            return 0.0
        if method in ("setorigin", "forceteleport"):
            if isinstance(receiver, FakeEntity) and args:
                if method == "setorigin" and not getattr(receiver, "is_player", False):
                    raise RuntimeError(f"WaW 1.7 forbids SetOrigin() on AI actor {receiver}; use ForceTeleport()")
                receiver.set_field("origin", args[0])
                if method == "forceteleport" and len(args) > 1:
                    receiver.set_field("angles", args[1])
            return UNDEFINED
        return super()._exec_method(receiver, method, args, line)


class TestBzPerksRegistrationAndStockSync(unittest.TestCase):
    """Slice 1: Hook registration, feature gate / Classic isolation, and stock perk sync."""

    EXPECTED_HOOKS = (
        "init",
        "player_connect",
        "player_spawned",
        "player_downed",
        "round_start",
        "end_game",
        "max_primary_weapons",
        "player_damage",
        "actor_damage",
        "item_purchased",
        "speed_scale",
        "max_health",
    )

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzPerksRuntime(MOD_ROOT, self.dvars)
        self.player = PerksFakeEntity("PerkTester", ent_num=0)
        self.player.set_field("score", 100000)
        self.player.give_weapon("thompson", make_current=True, stock=200)
        self.gsc.players.append(self.player)

    def _enable_perks(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")

    def test_register_is_idempotent_and_wires_all_12_hooks_under_perks_gate(self) -> None:
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_register")
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_register")

        hooks = self.gsc.level.get_field("bz_hooks")
        for hook_name in self.EXPECTED_HOOKS:
            entries = hooks[hook_name]
            self.assertIsNot(entries, UNDEFINED, f"Missing hook registration for {hook_name}")
            perks_entries = [
                entries[i]
                for i in range(entries.size)
                if entries[i].get_field("gate") == "perks"
            ]
            self.assertEqual(
                len(perks_entries),
                1,
                f"Expected exactly 1 idempotent 'perks' hook entry for {hook_name}, got {len(perks_entries)}",
            )

    def test_classic_mode_and_disabled_perks_gate_are_strict_noops(self) -> None:
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_register")

        # Classic mode (bz_enabled=0)
        self.dvars.set("bz_enabled", "0")
        self.dvars.set("bz_perks_enabled", "1")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")
        self.assertEqual(self.gsc.hud_elems, [])
        self.assertEqual(self.gsc.emitted_events, [])
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", self.player), 2)

        # Enabled core, disabled perks gate (bz_perks_enabled=0)
        dvars2 = FakeDvarStore()
        gsc2 = BzPerksRuntime(MOD_ROOT, dvars2)
        p2 = PerksFakeEntity("NoPerks", ent_num=0)
        p2.set_field("score", 50000)
        gsc2.players.append(p2)
        dvars2.set("bz_enabled", "1")
        dvars2.set("bz_perks_enabled", "0")
        gsc2.call(BZ_PERKS_MOD, "bz_perks_register")
        gsc2.call(BZ_HOOKS_MOD, "bz_init")
        self.assertEqual(gsc2.hud_elems, [])
        self.assertEqual(gsc2.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", p2), 2)

    def test_stock_perk_pickup_syncs_state_and_unlocks_tier2_station_ui(self) -> None:
        self._enable_perks()
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_register")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

        # Initially none of the 4 stock perks are owned -> Tier 2 locked
        self.assertEqual(self.player.client_dvars["ui_bz_t2_juggernog"], "REQ TIER 1")
        self.assertEqual(self.player.client_dvars["ui_bz_t2_speed_cola"], "REQ TIER 1")
        self.assertEqual(self.player.client_dvars["ui_bz_t2_double_tap"], "REQ TIER 1")
        self.assertEqual(self.player.client_dvars["ui_bz_t2_quick_revive"], "REQ TIER 1")

        # Simulate buying all 4 stock perk machines
        self.player.give_perk("specialty_armorvest")
        self.player.give_perk("specialty_fastreload")
        self.player.give_perk("specialty_rof")
        self.player.give_perk("specialty_quickrevive")

        synced = self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_stock_perks", self.player)
        self.assertTrue(synced)

        self.assertTrue(self.gsc.call(BZ_STATE_MOD, "bz_state_has_perk", self.player, "juggernog"))
        self.assertTrue(self.gsc.call(BZ_STATE_MOD, "bz_state_has_perk", self.player, "speed_cola"))
        self.assertTrue(self.gsc.call(BZ_STATE_MOD, "bz_state_has_perk", self.player, "double_tap"))
        self.assertTrue(self.gsc.call(BZ_STATE_MOD, "bz_state_has_perk", self.player, "quick_revive"))

        # Station UI dvars immediately unlock all 4 Tier 2 upgrades
        self.assertEqual(self.player.client_dvars["ui_bz_t2_juggernog"], "UPGRADE 5000")
        self.assertEqual(self.player.client_dvars["ui_bz_t2_speed_cola"], "UPGRADE 5000")
        self.assertEqual(self.player.client_dvars["ui_bz_t2_double_tap"], "UPGRADE 5000")
        self.assertEqual(self.player.client_dvars["ui_bz_t2_quick_revive"], "UPGRADE 5000")

        # Second sync with no new stock perks returns false (no redundant sync churn)
        self.assertFalse(self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_stock_perks", self.player))


class TestBzStandardPerksAndTier2Upgrades(unittest.TestCase):
    """Slices 2 & 3: New Standard Perks (Stamin-Up, Mule Kick, AP) & all 7 Perk Tier 2 upgrades."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzPerksRuntime(MOD_ROOT, self.dvars)
        self.player = PerksFakeEntity("CombatPlayer", ent_num=0)
        self.player.set_field("score", 200000)
        self.player.set_field("health", 100)
        self.player.set_field("maxhealth", 100)
        self.player.give_weapon("colt", make_current=True, stock=80)
        self.gsc.players.append(self.player)

        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")

        self.gsc.call(BZ_PERKS_MOD, "bz_perks_register")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

    def _buy_perks_menu(self, token: str, player: PerksFakeEntity | None = None) -> None:
        target = player if player is not None else self.player
        handled = self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", target, "bz_station_perks", token)
        self.assertTrue(handled, f"Menu token {token} not handled")

    def test_staminup_t1_and_t2_move_speed_sprint_ads_strafe_and_class_composition(self) -> None:
        # Stamin-Up I (2000): +15% speed + sprint endurance
        self._buy_perks_menu("buy_perk:staminup")
        self.assertEqual(self.player.get_field("score"), 198000)
        self.assertAlmostEqual(float(self.player.get_field("bz_move_speed_scale")), 1.15, places=4)
        self.assertAlmostEqual(self.player.speed_scale_calls[-1], 1.15, places=4)
        self.assertTrue(self.player.has_perk("specialty_longersprint"))
        self.assertEqual(self.player.client_dvars["player_sprinttime"], "8")

        # Composes cleanly with another module's speed modifier (e.g. Daredevil 1.35x burst)
        self.gsc.call(BZ_HOOKS_MOD, "bz_set_speed_modifier", self.player, "bz_daredevil_burst", 1.35)
        scale_composed = self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_speed", self.player)
        self.assertAlmostEqual(scale_composed, 1.15 * 1.35, places=4)

        # Upgrade to Stamin-Up II (5000): +25% speed, preserving Daredevil modifier
        self._buy_perks_menu("buy_t2:staminup")
        self.assertEqual(self.player.get_field("score"), 193000)
        self.assertAlmostEqual(float(self.player.get_field("bz_move_speed_scale")), 1.25 * 1.35, places=4)
        self.assertEqual(self.player.client_dvars["player_sprinttime"], "12")

        # Clear Daredevil and verify Stamin-Up II base speed vs ADS strafe boost
        self.gsc.call(BZ_HOOKS_MOD, "bz_clear_speed_modifier", self.player, "bz_daredevil_burst")
        self.player.ads_frac = 0.0
        self.assertAlmostEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_speed", self.player), 1.25, places=4)

        self.player.ads_frac = 1.0
        self.assertAlmostEqual(
            self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_speed", self.player),
            1.25 * 1.25,
            places=4,
        )

    def test_mule_kick_t1_and_t2_weapon_caps_and_acquisition_order(self) -> None:
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", self.player), 2)

        # Mule Kick I (4000): cap rises 2 -> 3
        self._buy_perks_menu("buy_perk:mule_kick")
        self.assertEqual(self.player.get_field("score"), 196000)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", self.player), 3)

        self.player.give_weapon("thompson", stock=200)
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", self.player)
        self.player.give_weapon("stg44", make_current=True, stock=180)
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", self.player)
        order = self.player.get_field("bz_primary_weapon_order")
        self.assertEqual(order.to_list(), ["colt", "thompson", "stg44"])

        # Mule Kick II (5000): cap rises 3 -> 4 (4th primary weapon slot)
        self._buy_perks_menu("buy_t2:mule_kick")
        self.assertEqual(self.player.get_field("score"), 191000)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", self.player), 4)

        self.player.give_weapon("zombie_mg42", make_current=True, stock=500)
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", self.player)
        order4 = self.player.get_field("bz_primary_weapon_order")
        self.assertEqual(order4.to_list(), ["colt", "thompson", "stg44", "zombie_mg42"])

        # Mule Kick I 3-weapon down strip: verify stripping 3 -> 2 cleanly removes only 3rd weapon
        p_mk1 = PerksFakeEntity("MuleOnePlayer", ent_num=5)
        p_mk1.set_field("score", 20000)
        p_mk1.give_weapon("colt", make_current=True, stock=80)
        self.gsc.players.append(p_mk1)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", p_mk1)
        self._buy_perks_menu("buy_perk:mule_kick", player=p_mk1)
        p_mk1.give_weapon("thompson", stock=200)
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", p_mk1)
        p_mk1.give_weapon("stg44", make_current=True, stock=180)
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", p_mk1)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_downed", p_mk1)
        self.assertEqual(p_mk1.primary_weapons, ["colt", "thompson"])
        self.assertEqual(p_mk1.taken_weapons, ["stg44"])
        self.assertIn(p_mk1.current_weapon, ("colt", "thompson"))

    def test_ap_t1_t2_and_double_tap_t2_bullet_and_limb_damage_composition(self) -> None:
        zombie = PerksFakeEntity("zombie_0", ent_num=20, is_player=False)
        zombie.set_field("health", 1000)

        # Baseline bullet hit = 100
        base = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie, self.player, self.player, 100, 0, "MOD_RIFLE_BULLET", "thompson",
            GscArray([0, 0, 0]), GscArray([1, 0, 0]), "torso_upper", 0,
        )
        self.assertEqual(base, 100)

        # AP I (3000): +35% bullet damage -> 135; non-bullet melee untouched -> 100
        self._buy_perks_menu("buy_perk:ap")
        ap1_dmg = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie, self.player, self.player, 100, 0, "MOD_RIFLE_BULLET", "thompson",
            GscArray([0, 0, 0]), GscArray([1, 0, 0]), "torso_upper", 0,
        )
        self.assertEqual(ap1_dmg, 135)

        melee_dmg = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie, self.player, self.player, 100, 0, "MOD_MELEE", "knife",
            GscArray([0, 0, 0]), GscArray([1, 0, 0]), "torso_upper", 0,
        )
        self.assertEqual(melee_dmg, 100)

        # Stock Double Tap + Double Tap II (5000): +25% bullet damage -> 100 * 1.35 * 1.25 = 168
        self.player.give_perk("specialty_rof")
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_stock_perks", self.player)
        self._buy_perks_menu("buy_t2:double_tap")
        ap1_dt2_dmg = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie, self.player, self.player, 100, 0, "MOD_PISTOL_BULLET", "colt",
            GscArray([0, 0, 0]), GscArray([1, 0, 0]), "torso_upper", 0,
        )
        self.assertEqual(ap1_dt2_dmg, 168)

        # Upgrade AP -> AP II (5000): +60% bullet damage + 1.25x limb/armor multiplier
        self._buy_perks_menu("buy_t2:ap")
        ap2_dt2_torso = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie, self.player, self.player, 100, 0, "MOD_RIFLE_BULLET", "thompson",
            GscArray([0, 0, 0]), GscArray([1, 0, 0]), "torso_upper", 0,
        )
        self.assertEqual(ap2_dt2_torso, 200)  # 100 * 1.6 * 1.25

        ap2_dt2_limb = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie, self.player, self.player, 100, 0, "MOD_RIFLE_BULLET", "thompson",
            GscArray([0, 0, 0]), GscArray([1, 0, 0]), "left_leg_lower", 0,
        )
        self.assertEqual(ap2_dt2_limb, 250)  # 100 * 1.6 * 1.25 * 1.25

        ap2_dt2_armor = self.gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie, self.player, self.player, 100, 0, "MOD_RIFLE_BULLET", "thompson",
            GscArray([0, 0, 0]), GscArray([1, 0, 0]), "armor", 0,
        )
        self.assertEqual(ap2_dt2_armor, 250)

    def test_juggernog_t2_sets_220_base_hp_and_composes_with_titan_440_hp(self) -> None:
        # Stock Juggernog -> 160 HP
        self.player.give_perk("specialty_armorvest")
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_stock_perks", self.player)
        self.assertEqual(self.player.get_field("maxhealth"), 160)

        # Juggernog II -> 220 HP
        self._buy_perks_menu("buy_t2:juggernog")
        self.assertEqual(self.player.get_field("maxhealth"), 220)
        self.assertEqual(self.player.get_field("health"), 220)

        # Compose cleanly with Titan 2x multiplier -> 440 HP without clobbering
        self.gsc.call(BZ_HOOKS_MOD, "bz_set_max_health_mult", self.player, "bz_class_titan", 2.0)
        final_hp = self.gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_max_health", self.player)
        self.assertEqual(final_hp, 440)
        self.assertEqual(self.player.get_field("maxhealth"), 440)

    def test_speed_cola_t2_applies_fast_swap_and_snappy_reload(self) -> None:
        self.player.give_perk("specialty_fastreload")
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_stock_perks", self.player)
        self._buy_perks_menu("buy_t2:speed_cola")

        self.assertTrue(self.player.get_field("bz_fast_swap_active"))
        self.assertEqual(self.player.client_dvars["perk_weapreloadmultiplier"], "0.35")
        self.assertEqual(self.player.client_dvars["perk_weapswitchmultiplier"], "0.5")

    def test_quick_revive_t2_revive_timing_post_revive_invuln_and_extra_solo_revive(self) -> None:
        ally = PerksFakeEntity("RevivedAlly", ent_num=1)
        ally.set_field("health", 100)
        ally.set_field("maxhealth", 100)
        self.gsc.players.append(ally)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", ally)

        # Stock Quick Revive -> 1.5s revive (50% of 3.0s)
        self.player.give_perk("specialty_quickrevive")
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_stock_perks", self.player)
        self.assertAlmostEqual(
            self.gsc.call(BZ_PERKS_MOD, "bz_perks_get_revive_time", self.player, 3.0),
            1.5,
            places=4,
        )

        # Quick Revive II -> 0.9s revive (30% of 3.0s) + 2 total Solo revive charges (1 QR I + 1 QR II)
        self._buy_perks_menu("buy_t2:quick_revive")
        self.assertAlmostEqual(
            self.gsc.call(BZ_PERKS_MOD, "bz_perks_get_revive_time", self.player, 3.0),
            0.9,
            places=4,
        )
        self.assertEqual(self.player.get_field("bz_extra_solo_revives"), 2)
        self.assertTrue(self.gsc.call(BZ_PERKS_MOD, "bz_perks_try_consume_solo_revive", self.player))
        self.assertEqual(self.player.get_field("bz_extra_solo_revives"), 1)
        self.assertTrue(self.gsc.call(BZ_PERKS_MOD, "bz_perks_try_consume_solo_revive", self.player))
        self.assertEqual(self.player.get_field("bz_extra_solo_revives"), 0)
        self.assertFalse(self.gsc.call(BZ_PERKS_MOD, "bz_perks_try_consume_solo_revive", self.player))

        # Revive completion grants 2s post-revive invulnerability to BOTH reviver and revived
        self.gsc.sim_time_ms = 10000
        granted = self.gsc.call(BZ_PERKS_MOD, "bz_perks_apply_revive_completed", self.player, ally)
        self.assertTrue(granted)

        # At t=11500ms (inside 2s window): damage to both reviver and revived is cancelled (0)
        zombie = PerksFakeEntity("zombie_1", ent_num=21, is_player=False)
        self.gsc.sim_time_ms = 11500
        dmg_reviver = self.gsc.call_on(
            self.player, BZ_HOOKS_MOD, "bz_player_damage_override",
            zombie, zombie, 50, 0, "MOD_MELEE", "none", GscArray([0, 0, 0]), GscArray([1, 0, 0]), "none", 0, 0,
        )
        dmg_ally = self.gsc.call_on(
            ally, BZ_HOOKS_MOD, "bz_player_damage_override",
            zombie, zombie, 50, 0, "MOD_MELEE", "none", GscArray([0, 0, 0]), GscArray([1, 0, 0]), "none", 0, 0,
        )
        self.assertEqual(dmg_reviver, 0)
        self.assertEqual(dmg_ally, 0)

        # At t=12000ms (window expired): normal damage resumes
        self.gsc.sim_time_ms = 12000
        dmg_after = self.gsc.call_on(
            ally, BZ_HOOKS_MOD, "bz_player_damage_override",
            zombie, zombie, 50, 0, "MOD_MELEE", "none", GscArray([0, 0, 0]), GscArray([1, 0, 0]), "none", 0, 0,
        )
        self.assertEqual(dmg_after, 50)


class TestBzApexPerks(unittest.TestCase):
    """Slice 4: All 4 Apex Perks (Double Ammo, Lightweight Heavy, Second Chance, Blast Shield)."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzPerksRuntime(MOD_ROOT, self.dvars)
        self.player = PerksFakeEntity("ApexPlayer", ent_num=0)
        self.player.set_field("score", 300000)
        self.player.set_field("health", 100)
        self.player.set_field("maxhealth", 100)
        self.player.set_field("origin", GscArray([100, 100, 0]))
        self.player.give_weapon("thompson", make_current=True, stock=200)
        self.player.give_weapon("zombie_mg42", stock=500)
        self.gsc.players.append(self.player)

        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")

        self.gsc.call(BZ_PERKS_MOD, "bz_perks_register")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

    def _buy_perks_menu(self, token: str) -> None:
        handled = self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.player, "bz_station_perks", token)
        self.assertTrue(handled, f"Menu token {token} not handled")

    def test_double_ammo_2x_reserve_composes_with_double_pap_and_refills(self) -> None:
        # Mark a Double PaP upgraded weapon as well to verify 2.0 * 1.5 = 3.0x composition
        self.player.give_weapon("thompson_upgraded", stock=300)
        self.gsc.call(BZ_STATE_MOD, "bz_state_mark_weapon_double_pap", self.player, "thompson_upgraded")

        self._buy_perks_menu("buy_apex:double_ammo")
        self.assertEqual(self.player.get_field("score"), 292000)

        # Purchase immediately grants 2x (and 3x for Double PaP) reserve ammo
        self.assertEqual(self.player.weapon_stock["thompson"], 400)           # 200 * 2.0
        self.assertEqual(self.player.weapon_stock["zombie_mg42"], 1000)       # 500 * 2.0
        self.assertEqual(self.player.weapon_stock["thompson_upgraded"], 900)  # 300 * 2.0 * 1.5

        # Deplete all stocks, then wall-buy refill only thompson
        self.player.weapon_stock["thompson"] = 40
        self.player.weapon_stock["zombie_mg42"] = 100
        self.player.weapon_stock["thompson_upgraded"] = 50

        self.gsc.call(BZ_PERKS_MOD, "bz_perks_refill_ammo_for_player", self.player, "thompson")
        self.assertEqual(self.player.weapon_stock["thompson"], 400)
        self.assertEqual(self.player.weapon_stock["zombie_mg42"], 100)
        self.assertEqual(self.player.weapon_stock["thompson_upgraded"], 50)

        # Max Ammo refill (empty weapon arg) refills ALL held primaries to 2x / 3x caps
        self.player.weapon_stock["thompson"] = 10
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_refill_ammo_for_player", self.player, "")
        self.assertEqual(self.player.weapon_stock["thompson"], 400)
        self.assertEqual(self.player.weapon_stock["zombie_mg42"], 1000)
        self.assertEqual(self.player.weapon_stock["thompson_upgraded"], 900)

        # Real wall-buy ammo purchase event (bz_on_wall_buy) refills both base & upgraded variant
        self.player.weapon_stock["thompson"] = 25
        self.player.weapon_stock["thompson_upgraded"] = 30
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_wall_buy", self.player, "thompson", GscArray([0, 0, 0]), True)
        self.assertEqual(self.player.weapon_stock["thompson"], 400)
        self.assertEqual(self.player.weapon_stock["thompson_upgraded"], 900)

    def test_lightweight_heavy_compensates_heavy_weapon_without_stomping_staminup_or_daredevil(self) -> None:
        self._buy_perks_menu("buy_perk:staminup")
        self._buy_perks_menu("buy_t2:staminup")
        self._buy_perks_menu("buy_apex:lightweight_heavy")

        # Holding SMG (thompson, moveScale 1.0): no extra compensation beyond Stamin-Up II (1.25)
        self.player.current_weapon = "thompson"
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_update_lightweight_heavy", self.player)
        self.assertAlmostEqual(float(self.player.get_field("bz_move_speed_scale")), 1.25, places=4)

        # Switch to LMG (zombie_mg42, moveScale 0.78): comp = 1/0.78, composed with Stamin-Up II (1.25)
        self.player.current_weapon = "zombie_mg42"
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_update_lightweight_heavy", self.player)
        self.assertAlmostEqual(
            float(self.player.get_field("bz_move_speed_scale")),
            1.25 * (1.0 / 0.78),
            places=4,
        )

        # Add Daredevil burst (1.35x) and switch to panzerschrek (0.75 -> comp 1.3333):
        # 1.25 * 1.3333 * 1.35 = 2.25 -> clamped cleanly to 2.0 by bz_recompute_player_speed
        self.gsc.call(BZ_HOOKS_MOD, "bz_set_speed_modifier", self.player, "bz_daredevil_burst", 1.35)
        self.player.give_weapon("panzerschrek", make_current=True, stock=20)
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_update_lightweight_heavy", self.player)
        self.assertAlmostEqual(float(self.player.get_field("bz_move_speed_scale")), 2.0, places=4)

        # Clear Daredevil and switch back to SMG -> Stamin-Up II 1.25 still intact (never stomped!)
        self.gsc.call(BZ_HOOKS_MOD, "bz_clear_speed_modifier", self.player, "bz_daredevil_burst")
        self.player.current_weapon = "thompson"
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_update_lightweight_heavy", self.player)
        self.assertAlmostEqual(float(self.player.get_field("bz_move_speed_scale")), 1.25, places=4)

    def test_second_chance_cancels_lethal_hit_stuns_and_pushes_zombies_and_recharges_each_round(self) -> None:
        self._buy_perks_menu("buy_apex:second_chance")
        self.assertTrue(self.player.get_field("bz_second_chance_ready"))

        # Spawn 2 nearby zombies (within 256 units) and 1 far zombie (500 units away)
        z_near1 = PerksFakeEntity("z_near1", ent_num=30, is_player=False)
        z_near1.set_field("origin", GscArray([150, 100, 0]))
        z_near1.set_field("health", 250)

        z_near2 = PerksFakeEntity("z_near2", ent_num=31, is_player=False)
        z_near2.set_field("origin", GscArray([100, 200, 0]))
        z_near2.set_field("health", 250)

        z_far = PerksFakeEntity("z_far", ent_num=32, is_player=False)
        z_far.set_field("origin", GscArray([600, 100, 0]))
        z_far.set_field("health", 250)
        self.gsc.zombies.extend([z_near1, z_near2, z_far])

        # 1. Non-lethal hit (40 dmg on 100 HP) passes through without consuming Second Chance
        self.gsc.sim_time_ms = 5000
        dmg1 = self.gsc.call_on(
            self.player, BZ_HOOKS_MOD, "bz_player_damage_override",
            z_near1, z_near1, 40, 0, "MOD_MELEE", "none", GscArray([100, 100, 0]), GscArray([-1, 0, 0]), "none", 0, 0,
        )
        self.assertEqual(dmg1, 40)
        self.assertTrue(self.player.get_field("bz_second_chance_ready"))
        self.player.set_field("health", 60)

        # 2. Lethal hit (60 dmg on 60 HP) triggers Second Chance!
        self.gsc.sim_time_ms = 6000
        dmg2 = self.gsc.call_on(
            self.player, BZ_HOOKS_MOD, "bz_player_damage_override",
            z_near1, z_near1, 60, 0, "MOD_MELEE", "none", GscArray([100, 100, 0]), GscArray([-1, 0, 0]), "none", 0, 0,
        )
        self.assertEqual(dmg2, 0)
        self.assertFalse(self.player.get_field("bz_second_chance_ready"))
        self.assertEqual(self.player.get_field("health"), 100)  # Restored to 100% maxhealth
        self.assertEqual(self.player.get_field("bz_invuln_until"), 8000)  # 2s invuln

        # Nearby zombies pushed radially outward and stunned for 3s (until 9000ms)
        self.assertEqual(z_near1.get_field("bz_second_chance_stun_until"), 9000)
        self.assertTrue(z_near1.get_field("bz_stunned"))
        self.assertTrue(z_near1.get_field("ignoreall"))
        self.assertGreater(float(z_near1.get_field("origin")[0]), 150.0)

        self.assertEqual(z_near2.get_field("bz_second_chance_stun_until"), 9000)
        self.assertGreater(float(z_near2.get_field("origin")[1]), 200.0)

        # Far zombie untouched
        self.assertIs(z_far.get_field("bz_second_chance_stun_until"), UNDEFINED)
        self.assertEqual(float(z_far.get_field("origin")[0]), 600.0)

        # Telemetry emitted
        self.assertTrue(
            any(
                ev.startswith("BZ_EVENT|PERK_SECOND_CHANCE|") and "stunned=2;" in ev
                for ev in self.gsc.emitted_events
            ),
            f"Missing PERK_SECOND_CHANCE telemetry in {self.gsc.emitted_events}",
        )

        # 3. Follow-up damage during 2s invuln window (t=7000ms) is cancelled
        self.gsc.sim_time_ms = 7000
        dmg_invuln = self.gsc.call_on(
            self.player, BZ_HOOKS_MOD, "bz_player_damage_override",
            z_near1, z_near1, 150, 0, "MOD_MELEE", "none", GscArray([100, 100, 0]), GscArray([-1, 0, 0]), "none", 0, 0,
        )
        self.assertEqual(dmg_invuln, 0)

        # 4. After invuln expires (t=8500ms) in SAME round, lethal hit is NOT cancelled
        self.gsc.sim_time_ms = 8500
        dmg_second_lethal = self.gsc.call_on(
            self.player, BZ_HOOKS_MOD, "bz_player_damage_override",
            z_near1, z_near1, 100, 0, "MOD_MELEE", "none", GscArray([100, 100, 0]), GscArray([-1, 0, 0]), "none", 0, 0,
        )
        self.assertEqual(dmg_second_lethal, 100)

        # 5. Next round start automatically recharges Second Chance
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_round_start", 2)
        self.assertTrue(self.player.get_field("bz_second_chance_ready"))
        self.assertTrue(
            any(ev.startswith("BZ_EVENT|PERK_SECOND_CHANCE_RECHARGE|") for ev in self.gsc.emitted_events)
        )

        self.gsc.sim_time_ms = 15000
        dmg_recharged = self.gsc.call_on(
            self.player, BZ_HOOKS_MOD, "bz_player_damage_override",
            z_near1, z_near1, 120, 0, "MOD_MELEE", "none", GscArray([100, 100, 0]), GscArray([-1, 0, 0]), "none", 0, 0,
        )
        self.assertEqual(dmg_recharged, 0)

    def test_second_chance_pushback_clamps_before_wall_via_bullettrace(self) -> None:
        self._buy_perks_menu("buy_apex:second_chance")
        z_wall = PerksFakeEntity("z_wall", ent_num=40, is_player=False)
        z_wall.set_field("origin", GscArray([150, 100, 0]))
        z_wall.set_field("health", 250)
        self.gsc.zombies.append(z_wall)

        # Simulate a solid wall halfway along the 96-unit push vector (fraction=0.5 -> safe_frac=0.35 -> +33.6u)
        self.gsc.bullet_trace_fn = lambda s, e: {"fraction": 0.5, "position": e}
        self.gsc.sim_time_ms = 20000
        dmg = self.gsc.call_on(
            self.player, BZ_HOOKS_MOD, "bz_player_damage_override",
            z_wall, z_wall, 150, 0, "MOD_MELEE", "none", GscArray([100, 100, 0]), GscArray([-1, 0, 0]), "none", 0, 0,
        )
        self.assertEqual(dmg, 0)
        pushed_x = float(z_wall.get_field("origin")[0])
        self.assertAlmostEqual(pushed_x, 150.0 + 96.0 * 0.35, places=3)
        self.assertLess(pushed_x, 150.0 + 96.0 * 0.5)

    def test_second_chance_skips_spawning_hellhounds_and_protects_active_hellhounds(self) -> None:
        self._buy_perks_menu("buy_apex:second_chance")

        dog_spawning = PerksFakeEntity("dog_spawning", ent_num=41, is_player=False)
        dog_spawning.set_field("species", "dog")
        dog_spawning.set_field("animname", "zombie_dog")
        dog_spawning.set_field("ignoreall", True)
        dog_spawning.set_field("magic_bullet_shield", True)
        dog_spawning.set_field("moveplaybackrate", 1.0)
        dog_spawning.set_field("origin", GscArray([130, 100, 0]))
        dog_spawning.set_field("health", 400)

        dog_active = PerksFakeEntity("dog_active", ent_num=42, is_player=False)
        dog_active.set_field("species", "dog")
        dog_active.set_field("animname", "zombie_dog")
        dog_active.set_field("ignoreall", False)
        dog_active.set_field("moveplaybackrate", 1.0)
        dog_active.set_field("origin", GscArray([140, 100, 0]))
        dog_active.set_field("health", 400)

        z_normal = PerksFakeEntity("z_normal", ent_num=43, is_player=False)
        z_normal.set_field("moveplaybackrate", 1.0)
        z_normal.set_field("origin", GscArray([150, 100, 0]))
        z_normal.set_field("health", 250)

        self.gsc.zombies.extend([dog_spawning, dog_active, z_normal])
        self.gsc.sim_time_ms = 25000

        dmg = self.gsc.call_on(
            self.player, BZ_HOOKS_MOD, "bz_player_damage_override",
            z_normal, z_normal, 150, 0, "MOD_MELEE", "none", GscArray([100, 100, 0]), GscArray([-1, 0, 0]), "none", 0, 0,
        )
        self.assertEqual(dmg, 0)

        # Spawning Hellhound skipped completely: no ForceTeleport, no stun, no ignoreall or moveplaybackrate change
        self.assertEqual(float(dog_spawning.get_field("origin")[0]), 130.0)
        self.assertIs(dog_spawning.get_field("bz_second_chance_stun_until"), UNDEFINED)
        self.assertAlmostEqual(float(dog_spawning.get_field("moveplaybackrate")), 1.0, places=4)
        self.assertTrue(dog_spawning.get_field("ignoreall"))

        # Active Hellhound: NOT ForceTeleported, slowed safely to 0.55 floor (never 0.01), ignoreall stays False
        self.assertEqual(float(dog_active.get_field("origin")[0]), 140.0)
        self.assertEqual(dog_active.get_field("bz_second_chance_stun_until"), 28000)
        self.assertAlmostEqual(float(dog_active.get_field("moveplaybackrate")), 0.55, places=4)
        self.assertFalse(dog_active.get_field("ignoreall"))

        # Regular zombie still pushed outward and stunned to 0.01 + ignoreall=True
        self.assertGreater(float(z_normal.get_field("origin")[0]), 150.0)
        self.assertAlmostEqual(float(z_normal.get_field("moveplaybackrate")), 0.01, places=4)
        self.assertTrue(z_normal.get_field("ignoreall"))

    def test_blast_shield_blocks_all_self_explosive_splash_fire_and_fall_without_wasting_second_chance(self) -> None:
        self._buy_perks_menu("buy_apex:blast_shield")
        self._buy_perks_menu("buy_apex:second_chance")

        self_mods = (
            ("MOD_GRENADE_SPLASH", self.player),
            ("MOD_EXPLOSIVE", self.player),
            ("MOD_PROJECTILE_SPLASH", self.player),
            ("MOD_BURNED", self.player),
            ("MOD_FALLING", UNDEFINED),
        )
        for mod, attacker in self_mods:
            dmg = self.gsc.call_on(
                self.player, BZ_HOOKS_MOD, "bz_player_damage_override",
                attacker, attacker, 200, 0, mod, "frag_grenade", GscArray([0, 0, 0]), GscArray([0, 0, 1]), "none", 0, 0,
            )
            self.assertEqual(dmg, 0, f"Blast Shield failed to cancel self-damage {mod}")
            self.assertTrue(
                self.player.get_field("bz_second_chance_ready"),
                f"Blast Shield should cancel {mod} before Second Chance is consumed",
            )

        # Enemy zombie melee is NOT blocked by Blast Shield
        zombie = PerksFakeEntity("z_melee", ent_num=33, is_player=False)
        melee = self.gsc.call_on(
            self.player, BZ_HOOKS_MOD, "bz_player_damage_override",
            zombie, zombie, 45, 0, "MOD_MELEE", "none", GscArray([0, 0, 0]), GscArray([1, 0, 0]), "none", 0, 0,
        )
        self.assertEqual(melee, 45)


class TestBzPerksDownResetHudAndWaw17Compliance(unittest.TestCase):
    """Slice 5: Down reset (Mule Kick 3rd/4th strip, Class/PaP preservation), ASCII HUD & WaW 1.7 compliance."""

    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = BzPerksRuntime(MOD_ROOT, self.dvars)
        self.p1 = PerksFakeEntity("HostP1", ent_num=0)
        self.p2 = PerksFakeEntity("CoopP2", ent_num=1)
        for p in (self.p1, self.p2):
            p.set_field("score", 300000)
            p.set_field("health", 100)
            p.set_field("maxhealth", 100)
            p.give_weapon("colt", make_current=True, stock=80)
        self.gsc.players.extend([self.p1, self.p2])

        self.dvars.set("bz_enabled", "1")
        self.dvars.set("bz_perks_enabled", "1")
        self.dvars.set("bz_classes_enabled", "1")
        self.dvars.set("bz_pap_enabled", "1")

        self.gsc.call(BZ_PERKS_MOD, "bz_perks_register")
        self.gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        self.gsc.call(BZ_HOOKS_MOD, "bz_init")

    def test_down_reset_strips_3rd_and_4th_mule_weapons_clears_perks_and_preserves_class_and_pap(self) -> None:
        # Equip full loadout: Titan class (2x HP), PaP Knife, Double PaP thompson_upgraded,
        # Juggernog II (440 HP), Stamin-Up II, Mule Kick II (4 primaries), AP II, Speed Cola II,
        # Quick Revive II, Double Ammo, Lightweight Heavy, Second Chance, Blast Shield.
        self.p1.give_perk("specialty_armorvest")
        self.p1.give_perk("specialty_fastreload")
        self.p1.give_perk("specialty_rof")
        self.p1.give_perk("specialty_quickrevive")
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_stock_perks", self.p1)

        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_class", "buy_class:titan")
        self.gsc.call(BZ_HOOKS_MOD, "bz_set_max_health_mult", self.p1, "bz_class_titan", 2.0)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_arsenal", "buy_pap:pap_knife")
        self.gsc.call(BZ_STATE_MOD, "bz_state_mark_weapon_double_pap", self.p1, "thompson_upgraded")

        for tok in (
            "buy_perk:staminup",
            "buy_perk:mule_kick",
            "buy_perk:ap",
            "buy_t2:juggernog",
            "buy_t2:speed_cola",
            "buy_t2:double_tap",
            "buy_t2:quick_revive",
            "buy_t2:staminup",
            "buy_t2:mule_kick",
            "buy_t2:ap",
            "buy_apex:double_ammo",
            "buy_apex:lightweight_heavy",
            "buy_apex:second_chance",
            "buy_apex:blast_shield",
        ):
            self.assertTrue(self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", tok))

        # Acquire 4 primary weapons in order, holding 4th (zombie_mg42)
        self.p1.give_weapon("thompson_upgraded", stock=900)
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", self.p1)
        self.p1.give_weapon("stg44", stock=360)
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", self.p1)
        self.p1.give_weapon("zombie_mg42", make_current=True, stock=1000)
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", self.p1)
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_update_lightweight_heavy", self.p1)

        self.assertEqual(self.p1.get_field("maxhealth"), 440)
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", self.p1), 4)
        self.assertEqual(self.p1.primary_weapons, ["colt", "thompson_upgraded", "stg44", "zombie_mg42"])

        # Player 1 goes down (station-bought stock specialties must be unset by BZ down reset)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_downed", self.p1)

        # 3rd and 4th weapons stripped cleanly; switched to a surviving primary
        self.assertEqual(self.p1.primary_weapons, ["colt", "thompson_upgraded"])
        self.assertIn("stg44", self.p1.taken_weapons)
        self.assertIn("zombie_mg42", self.p1.taken_weapons)
        self.assertIn(self.p1.current_weapon, ("colt", "thompson_upgraded"))
        self.assertEqual(self.gsc.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", self.p1), 2)

        # Speed reset to 1.0; max health recomputed to Titan base (100 * 2 = 200), NOT 440!
        self.assertAlmostEqual(float(self.p1.get_field("bz_move_speed_scale")), 1.0, places=4)
        self.assertEqual(self.p1.get_field("maxhealth"), 200)
        self.assertFalse(self.p1.has_perk("specialty_longersprint"))
        self.assertFalse(self.p1.get_field("bz_fast_swap_active"))

        # All perks/T2/Apex cleared, while Class + PaP upgrades strictly preserved!
        self.assertFalse(self.gsc.call(BZ_STATE_MOD, "bz_state_has_perk", self.p1, "staminup"))
        self.assertFalse(self.gsc.call(BZ_STATE_MOD, "bz_state_has_perk_t2", self.p1, "juggernog"))
        self.assertFalse(self.gsc.call(BZ_STATE_MOD, "bz_state_has_apex", self.p1, "second_chance"))
        self.assertEqual(self.gsc.call(BZ_STATE_MOD, "bz_state_get_class", self.p1), "titan")
        self.assertTrue(self.gsc.call(BZ_STATE_MOD, "bz_state_has_pap_upgrade", self.p1, "pap_knife", ""))
        self.assertTrue(self.gsc.call(BZ_STATE_MOD, "bz_state_is_weapon_double_pap", self.p1, "thompson_upgraded"))

        # Station UI refreshed to reflect lost perks
        self.assertEqual(self.p1.client_dvars["ui_bz_perk_staminup"], "BUY 2000")
        self.assertEqual(self.p1.client_dvars["ui_bz_t2_juggernog"], "REQ TIER 1")
        self.assertEqual(self.p1.client_dvars["ui_bz_apex_second_chance"], "BUY 8000")

        # Telemetry emitted
        self.assertTrue(
            any(
                ev.startswith("BZ_EVENT|PERK_DOWN_RESET|")
                and "max_weapons=2" in ev
                and "stg44" in ev
                and "zombie_mg42" in ev
                for ev in self.gsc.emitted_events
            ),
            f"Missing PERK_DOWN_RESET telemetry in {self.gsc.emitted_events}",
        )

    def test_compact_ascii_right_lane_hud_coop_isolation_and_zero_leaks_on_disconnect_and_end_game(self) -> None:
        # Buy custom Standard Perk, Tier 2, and Apex on p1 only
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_perk:staminup")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_t2:staminup")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_apex:second_chance")

        hud_p1 = self.p1.get_field("bz_perks_hud")
        self.assertIsInstance(hud_p1, FakeHudElem)
        self.assertEqual(hud_p1.get_field("alignX"), "right")
        self.assertEqual(hud_p1.get_field("horzAlign"), "right")
        self.assertEqual(hud_p1.get_field("x"), -12)
        self.assertEqual(hud_p1.get_field("y"), 32)
        self.assertIn("STAM II", hud_p1.text)
        self.assertIn("2ND CH", hud_p1.text)
        self.assertTrue(
            all(32 <= ord(ch) <= 126 for ch in hud_p1.text),
            f"Non-ASCII HUD text: {hud_p1.text!r}",
        )

        # Redundant update with unchanged state does not spam SetText()
        prev_calls = len(hud_p1.set_text_calls)
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_update_hud", self.p1)
        self.assertEqual(len(hud_p1.set_text_calls), prev_calls)

        # Co-op isolation: p2 has no custom perks so p2 HUD is untouched / hidden
        hud_p2 = self.p2.get_field("bz_perks_hud")
        if isinstance(hud_p2, FakeHudElem):
            self.assertEqual(hud_p2.get_field("alpha"), 0)

        # Give p2 Blast Shield so p2 gets its own HUD, then test disconnect on p1 and end_game on p2
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p2, "bz_station_perks", "buy_apex:blast_shield")
        hud_p2 = self.p2.get_field("bz_perks_hud")
        self.assertIsInstance(hud_p2, FakeHudElem)
        self.assertIn("BLAST", hud_p2.text)

        # Maxed perk loadout wraps cleanly into 2 compact non-overflowing right-hand HUD rows (y=32 & y=84)
        for tok in (
            "buy_perk:juggernog", "buy_t2:juggernog",
            "buy_perk:speed_cola", "buy_t2:speed_cola",
            "buy_perk:double_tap", "buy_t2:double_tap",
            "buy_perk:quick_revive", "buy_t2:quick_revive",
            "buy_perk:mule_kick", "buy_t2:mule_kick",
            "buy_perk:ap", "buy_t2:ap",
            "buy_apex:double_ammo", "buy_apex:lightweight_heavy", "buy_apex:blast_shield",
        ):
            self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", tok)
        hud_p1_row2 = self.p1.get_field("bz_perks_hud_row2")
        self.assertIsInstance(hud_p1_row2, FakeHudElem)
        self.assertEqual(hud_p1_row2.get_field("y"), 84)
        self.assertLessEqual(len(hud_p1.text), 56)
        self.assertIn("BLAST", hud_p1_row2.text)

        # Disconnect destroys both p1 HUD rows cleanly without touching p2
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_destroy_hud", self.p1)
        self.assertTrue(hud_p1.destroyed)
        self.assertTrue(hud_p1_row2.destroyed)
        self.assertIs(self.p1.get_field("bz_perks_hud"), UNDEFINED)
        self.assertIs(self.p1.get_field("bz_perks_hud_row2"), UNDEFINED)
        self.assertFalse(hud_p2.destroyed)

        # end_game destroys all remaining HUDs with zero leaks
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.assertTrue(hud_p2.destroyed)
        self.assertTrue(all(h.destroyed for h in self.gsc.hud_elems))

    def test_bz_perks_gsc_is_strictly_waw17_compliant(self) -> None:
        source = BZ_PERKS_PATH.read_text(encoding="latin1")
        tokenize(source, filename=str(BZ_PERKS_PATH))
        code_only = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
        self.assertIsNone(re.search(r"\bforeach\b", code_only), "Forbidden foreach in _bz_perks.gsc")

        # ASCII-only source file check
        non_ascii = [ch for ch in source if ord(ch) > 126 or (ord(ch) < 32 and ch not in "\t\r\n")]
        self.assertEqual(non_ascii, [], f"Non-ASCII chars in _bz_perks.gsc: {non_ascii!r}")

        mod = self.gsc.load_module(BZ_PERKS_MOD)
        sync_funcs = (
            "bz_perks_register",
            "bz_perks_init",
            "bz_perks_on_player_connect",
            "bz_perks_on_player_spawned",
            "bz_perks_on_player_downed",
            "bz_perks_on_round_start",
            "bz_perks_on_end_game",
            "bz_perks_on_max_primary_weapons",
            "bz_perks_on_player_damage",
            "bz_perks_on_actor_damage",
            "bz_perks_on_item_purchased",
            "bz_perks_on_speed_scale",
            "bz_perks_on_max_health",
            "bz_perks_sync_stock_perks",
            "bz_perks_sync_weapon_order",
            "bz_perks_strip_excess_mule_weapons",
            "bz_perks_apply_double_ammo_to_player",
            "bz_perks_refill_ammo_for_player",
            "bz_perks_update_lightweight_heavy",
            "bz_perks_apply_revive_completed",
            "bz_perks_update_hud",
            "bz_perks_destroy_hud",
        )
        for fn_name in sync_funcs:
            self.assertIn(fn_name, mod, f"Missing {fn_name}() in _bz_perks.gsc")
            self.assertFalse(
                _ast_contains_method_call(mod[fn_name].body, "endon"),
                f"Forbidden endon() inside synchronous caller {fn_name}()",
            )

    def test_staged_3x_stock_weapons_write_native_2x_3x_hud_counts_and_strictly_clamp_classic_mode_to_1x(
        self,
    ) -> None:
        import tempfile
        from scripts import build_mod as bm

        # 1. Every entry in build_mod.STOCK_3X_AMMO_WEAPONS must match _bz_rules.gsc 1x baseline table
        for weap_name, base_1x in bm.STOCK_3X_AMMO_WEAPONS.items():
            self.assertEqual(
                int(self.gsc.call(r"maps\_bz_rules", "bz_get_staged_stock_base_reserve", weap_name)),
                base_1x,
                f"Mismatch in _bz_rules.gsc for staged stock weapon {weap_name}",
            )

        # 2. stage_bz_stock_3x_ammo_weapons raises maxAmmo to 3x, keeps startAmmo/clipSize, and remaps non-factory FX
        with tempfile.TemporaryDirectory() as tmp:
            tools_root = Path(tmp) / "tools"
            stage_dir = Path(tmp) / "stage"
            raw_w = tools_root / "raw" / "weapons" / "sp"
            raw_w.mkdir(parents=True)
            (raw_w / "zombie_thompson").write_text(
                r"WEAPONFILE\displayName\Thompson\clipSize\20\startAmmo\200\maxAmmo\200\viewFlashEffect\weapon/muzzleflashes/standardflashview",
                encoding="latin1",
            )
            (raw_w / "springfield").write_text(
                r"WEAPONFILE\displayName\Springfield\clipSize\5\startAmmo\50\maxAmmo\50\viewFlashEffect\weapon/muzzleflashes/rifle_flash_view\worldFlashEffect\weapon/muzzleflashes/rifleflash",
                encoding="latin1",
            )
            staged = bm.stage_bz_stock_3x_ammo_weapons(tools_root, stage_dir)
            self.assertEqual(staged, ["weapons/sp/springfield", "weapons/sp/zombie_thompson"])
            thomp = dict(bm.parse_weapon_file((stage_dir / "weapons" / "sp" / "zombie_thompson").read_text(encoding="latin1")))
            self.assertEqual(thomp["maxAmmo"], "600")
            self.assertEqual(thomp["startAmmo"], "200")
            self.assertEqual(thomp["clipSize"], "20")
            spr = dict(bm.parse_weapon_file((stage_dir / "weapons" / "sp" / "springfield").read_text(encoding="latin1")))
            self.assertEqual(spr["maxAmmo"], "150")
            self.assertEqual(spr["viewFlashEffect"], "weapon/muzzleflashes/fx_kar98k_view")
            self.assertEqual(spr["worldFlashEffect"], "weapon/muzzleflashes/fx_kar98k")

        # 3. Native 2x (400) & 3x (600) HUD stock counts with 0 overflow when weapon is 3x-staged (WeaponMaxAmmo=600)
        self.gsc.weapon_max_ammo["zombie_thompson"] = 600
        self.p1.give_weapon("zombie_thompson", stock=200, make_current=True)
        self.assertEqual(int(self.gsc.call(BZ_HOOKS_MOD, "bz_get_effective_max_stock", self.p1, "zombie_thompson")), 200)
        self.p1.weapon_stock["zombie_thompson"] = 600
        self.gsc.call(BZ_HOOKS_MOD, "bz_normalize_weapon_stock", self.p1, "zombie_thompson")
        self.assertEqual(self.p1.weapon_stock["zombie_thompson"], 200)

        # Double Ammo -> writes 400 directly to engine stock with 0 hidden overflow!
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_apex:double_ammo")
        self.assertEqual(self.p1.weapon_stock["zombie_thompson"], 400)
        self.assertEqual(int(self.p1.get_field("bz_overflow_reserve")["zombie_thompson"]), 0)
        self.assertEqual(int(self.gsc.call(BZ_HOOKS_MOD, "bz_get_effective_max_stock", self.p1, "zombie_thompson")), 400)

        # Double Ammo + Double PaP -> writes 600 directly to engine stock with 0 hidden overflow!
        self.dvars.set("bz_pap_enabled", "1")
        self.gsc.call(BZ_STATE_MOD, "bz_state_mark_weapon_double_pap", self.p1, "zombie_thompson")
        self.gsc.call(BZ_PERKS_MOD, "bz_perks_refill_ammo_for_player", self.p1, "zombie_thompson")
        self.assertEqual(self.p1.weapon_stock["zombie_thompson"], 600)
        self.assertEqual(int(self.p1.get_field("bz_overflow_reserve")["zombie_thompson"]), 0)
        self.assertEqual(int(self.gsc.call(BZ_HOOKS_MOD, "bz_get_effective_max_stock", self.p1, "zombie_thompson")), 600)

        # 4. Classic Mode (bz_enabled=0) STRICTLY clamps 3x-staged stock weapons back to 1x (200) with zero telemetry!
        self.dvars.set("bz_enabled", "0")
        self.gsc.emitted_events.clear()
        self.p1.weapon_stock["zombie_thompson"] = 600
        self.assertEqual(int(self.gsc.call(BZ_HOOKS_MOD, "bz_get_effective_max_stock", self.p1, "zombie_thompson")), 200)
        self.gsc.call(BZ_HOOKS_MOD, "bz_normalize_all_player_stocks")
        self.assertEqual(self.p1.weapon_stock["zombie_thompson"], 200)
        self.assertEqual(self.gsc.emitted_events, [])

        # 5. Patched ammo_give() and full_ammo_powerup() wire bz_get_effective_max_stock & bz_normalize_*
        sample_weapons = (
            "init_weapons()\n{\n\tinclude_weapon( \"zombie_thompson\" );\n}\n"
            "ammo_give( weapon, also_has_upgrade )\n{\n"
            "\tstockMax = WeaponMaxAmmo( weapon );\n"
            "\tif( also_has_upgrade )\n\t{\n\t\tstockMax += WeaponMaxAmmo( weapon+\"_upgraded\" );\n\t}\n"
            "\tself GivemaxAmmo( weapon );\n\treturn true;\n}\n"
            "weapon_give( weapon, is_upgrade )\n{\n"
            "\tif( primaryWeapons.size >= 2 )\n\t{\n\t}\n"
            "\tself GiveWeapon( weapon, 0 );\n\tself GiveMaxAmmo( weapon );\n}\n"
        ).encode("latin1")
        patched_w = bm.inject_zombiemode_weapons_hooks(sample_weapons).decode("latin1")
        self.assertIn("stockMax = maps\\_bz_hooks::bz_get_effective_max_stock( self, weapon );", patched_w)
        self.assertIn('stockMax += maps\\_bz_hooks::bz_get_effective_max_stock( self, weapon+"_upgraded" );', patched_w)
        self.assertGreaterEqual(patched_w.count("maps\\_bz_hooks::bz_normalize_weapon_stock( self, weapon );"), 2)

        sample_powerups = b"full_ammo_powerup( drop_item )\n{\n\tplayers = get_players();\n}\n"
        patched_p = bm.inject_zombiemode_powerups_hooks(sample_powerups).decode("latin1")
        self.assertIn("maps\\_bz_hooks::bz_normalize_all_player_stocks();", patched_p)

    def test_p2o_t7_lightweight_phase2_blast_shield_molotov_and_coop_speed_cola2_assist(self) -> None:
        # 1. Lightweight Heavy compensates all 3 heavy Phase 2 weapons
        self.assertAlmostEqual(self.gsc.call(BZ_PERKS_MOD, "bz_perks_get_weapon_move_scale", "bz_acid_sprayer"), 0.75)
        self.assertAlmostEqual(self.gsc.call(BZ_PERKS_MOD, "bz_perks_get_weapon_move_scale", "bz_cryo_cannon"), 0.82)
        self.assertAlmostEqual(self.gsc.call(BZ_PERKS_MOD, "bz_perks_get_weapon_move_scale", "bz_multi_crossbow"), 0.9)

        # 2. Blast Shield blocks MOD_PROJECTILE self-damage AND world-attributed MOD_BURNED Molotov fire
        self.assertEqual(self.gsc.call(BZ_PERKS_MOD, "bz_perks_map_mod_to_self_damage_type", "MOD_PROJECTILE"), "splash")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_apex:blast_shield")
        dmg_proj = self.gsc.call_on(
            self.p1,
            BZ_HOOKS_MOD,
            "bz_player_damage_override",
            self.p1,
            self.p1,
            60,
            0,
            "MOD_PROJECTILE",
            "panzerschrek_zombie",
            UNDEFINED,
            UNDEFINED,
            "none",
            0,
            0,
        )
        self.assertEqual(dmg_proj, 0)
        dmg_world_fire = self.gsc.call_on(
            self.p1,
            BZ_HOOKS_MOD,
            "bz_player_damage_override",
            UNDEFINED,
            UNDEFINED,
            40,
            0,
            "MOD_BURNED",
            "molotov",
            UNDEFINED,
            UNDEFINED,
            "none",
            0,
            0,
        )
        self.assertEqual(dmg_world_fire, 0)

        # 3. Co-op Speed Cola II reload assist refills clip from stock without touching global reload dvars
        p2 = PerksFakeEntity("CoopAlly", ent_num=1)
        p2.set_field("score", 50000)
        self.gsc.players.append(p2)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", p2)
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_perk:speed_cola")
        self.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", self.p1, "bz_station_perks", "buy_t2:speed_cola")
        self.p1.give_weapon("zombie_thompson", make_current=True)
        self.gsc._exec_method(self.p1, "setweaponammoclip", ["zombie_thompson", 5], 0)
        self.p1.weapon_stock["zombie_thompson"] = 100
        taken = self.gsc.call(BZ_PERKS_MOD, "bz_perks_try_coop_speed_cola2_assist", self.p1, "zombie_thompson")
        self.assertGreater(taken, 0)
        self.assertEqual(self.gsc._exec_method(self.p1, "getweaponammoclip", ["zombie_thompson"], 0), 5 + taken)
        self.assertEqual(self.p1.weapon_stock["zombie_thompson"], 100 - taken)


if __name__ == "__main__":
    unittest.main()
