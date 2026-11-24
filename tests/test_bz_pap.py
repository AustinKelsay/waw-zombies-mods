"""Offline TDD contract suite for P1-T6 (#17): Pack-a-Punch Expansion.

Exercises real WaW 1.7 `.gsc` source (`mod/maps/_bz_pap.gsc`) through an
extended GSC runtime built on `tests/gsc_runtime.py` + `BzGscRuntime`
(without modifying `tests/gsc_runtime.py`), covering all 5 seams:
  1. Hook registration, Feature Gate isolation & 4-Map Single PaP (Der Riese
     native `*_upgraded` swap vs Nacht/Verruckt/Sumpf scripted Tier 1 PaP).
  2. Double Pack-a-Punch (+75% bullet damage, +50% reserve ammo composing with
     Double Ammo, no elemental procs, down persistence).
  3. PaP Knife (3x melee) & PaP Bowie Knife (1-hit kill regular zombies on any
     round, 3x on boss/dogs, down persistence).
  4. PaP Cluster Grenade (round-scaled primary + 4 staggered mini-clusters,
     Sapper radius/capacity stacking, Blast Shield self-damage immunity).
  5. Top-right ASCII PaP HUD badge, disconnect/end_game zero-leak cleanup,
     and WaW 1.7 syntax compliance (zero `foreach`, zero `endon` in sync callers).
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_ROOT = REPO_ROOT / "mod"

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

BZ_PAP_MOD = "maps\\_bz_pap"
BZ_PAP_PATH = MOD_ROOT / "maps" / "_bz_pap.gsc"
BZ_STATE_MOD = "maps\\_bz_state"
BZ_STATIONS_MOD = "maps\\_bz_stations"


class FakeHudElem(GscStruct):
    """Fake WaW 1.7 client HUD element created by NewClientHudElem(player)."""

    def __init__(self, owner: FakeEntity | None = None) -> None:
        super().__init__()
        self.owner = owner
        self.text_history: list[str] = []
        self.destroyed: bool = False
        self.destroy_count: int = 0

    @property
    def current_text(self) -> str:
        return self.text_history[-1] if self.text_history else ""


class PapFakeEntity(FakeEntity):
    """Extends FakeEntity with weapon inventory, ammo stocks, and damage logs."""

    def __init__(self, name: str = "player_0", ent_num: int = 0, is_player: bool = True) -> None:
        super().__init__(name=name, ent_num=ent_num, is_player=is_player)
        self.set_field("origin", GscArray([0, 0, 0]))
        self.weapon_stock: dict[str, int] = {}
        self.max_ammo_calls: list[str] = []
        self.switch_calls: list[str] = []
        self.taken_weapons: list[str] = []
        self.given_weapons: list[str] = []
        self.damage_events: list[dict[str, Any]] = []

    def give_weapon(self, weapon: str, make_current: bool = False, stock: int | None = None) -> None:
        super().give_weapon(weapon, make_current=make_current)
        norm = weapon.lower()
        self.given_weapons.append(norm)
        if stock is not None:
            self.weapon_stock[norm] = stock
        elif norm not in self.weapon_stock:
            self.weapon_stock[norm] = 100


class PapGscRuntime(BzGscRuntime):
    """Extends BzGscRuntime with WaW 1.7 weapon/ammo, AI, damage, and client HUD builtins."""

    def __init__(self, mod_root: Path, dvars: FakeDvarStore | None = None) -> None:
        super().__init__(mod_root, dvars)
        self.weapon_max_ammo: dict[str, int] = {
            "colt": 80,
            "thompson": 200,
            "thompson_upgraded": 220,
            "stg44": 180,
            "stg44_upgraded": 240,
            "zombie_ppsh": 355,
            "zombie_ppsh_upgraded": 700,
            "ray_gun": 160,
            "ray_gun_upgraded": 200,
            "kar98k": 60,
            "bz_acid_sprayer": 120,
            "bz_cryo_cannon": 96,
            "bz_multi_crossbow": 36,
            "bz_blade_boomerang": 20,
        }
        self.ai_enemies: list[PapFakeEntity] = []
        self.hud_elems: list[FakeHudElem] = []
        self.played_sounds: list[tuple[Any, str]] = []
        self.sound_positions: list[tuple[str, Any]] = []
        self.played_fx: list[tuple[Any, Any]] = []

    def _call_builtin(self, name_lower: str, args: list[Any], line: int) -> tuple[bool, Any]:
        if name_lower == "weaponmaxammo":
            weap = _waw_to_str(args[0]).lower() if args else ""
            return True, self.weapon_max_ammo.get(weap, 120)
        if name_lower == "getaispeciesarray":
            return True, GscArray([z for z in self.ai_enemies if not z.deleted])
        if name_lower == "newclienthudelem":
            if not args or not isinstance(args[0], FakeEntity):
                raise GscRuntimeError(f"line {line}: NewClientHudElem requires a player entity")
            hud = FakeHudElem(owner=args[0])
            self.hud_elems.append(hud)
            return True, hud
        if name_lower == "playsoundatposition":
            snd = _waw_to_str(args[0]) if len(args) > 0 else ""
            pos = args[1] if len(args) > 1 else UNDEFINED
            self.sound_positions.append((snd, pos))
            return True, UNDEFINED
        if name_lower == "playfx":
            fx = args[0] if len(args) > 0 else UNDEFINED
            pos = args[1] if len(args) > 1 else UNDEFINED
            self.played_fx.append((fx, pos))
            return True, UNDEFINED
        if name_lower == "getent":
            val = _waw_to_str(args[0]).lower() if len(args) > 0 else ""
            key = _waw_to_str(args[1]).lower() if len(args) > 1 else ""
            matches = self.world_entities.get((key, val), [])
            return True, (matches[0] if matches else UNDEFINED)
        return super()._call_builtin(name_lower, args, line)

    def _exec_method(self, receiver: Any, method: str, args: list[Any], line: int) -> Any:
        if method == "playsound":
            snd = _waw_to_str(args[0]) if args else ""
            self.played_sounds.append((receiver, snd))
            return UNDEFINED
        if isinstance(receiver, FakeHudElem):
            if method == "settext":
                txt = _waw_to_str(args[0]) if args else ""
                receiver.text_history.append(txt)
                return UNDEFINED
            if method == "destroy":
                receiver.destroyed = True
                receiver.destroy_count += 1
                return UNDEFINED

        if isinstance(receiver, PapFakeEntity):
            if method == "takeweapon":
                w = _waw_to_str(args[0]).lower() if args else ""
                receiver.weapons.discard(w)
                receiver.taken_weapons.append(w)
                if receiver.current_weapon == w:
                    receiver.current_weapon = next(iter(receiver.weapons), "none")
                return UNDEFINED
            if method == "giveweapon":
                w = _waw_to_str(args[0]).lower() if args else ""
                receiver.weapons.add(w)
                receiver.given_weapons.append(w)
                if w not in receiver.weapon_stock:
                    receiver.weapon_stock[w] = self.weapon_max_ammo.get(w, 120)
                return UNDEFINED
            if method == "givemaxammo":
                w = _waw_to_str(args[0]).lower() if args else ""
                receiver.max_ammo_calls.append(w)
                receiver.weapon_stock[w] = self.weapon_max_ammo.get(w, 120)
                return UNDEFINED
            if method == "switchtoweapon":
                w = _waw_to_str(args[0]).lower() if args else ""
                receiver.current_weapon = w
                receiver.switch_calls.append(w)
                return UNDEFINED
            if method == "getweaponammostock":
                w = _waw_to_str(args[0]).lower() if args else ""
                return receiver.weapon_stock.get(w, 0)
            if method == "setweaponammostock":
                w = _waw_to_str(args[0]).lower() if len(args) > 0 else ""
                amt = int(args[1]) if len(args) > 1 else 0
                receiver.weapon_stock[w] = amt
                return UNDEFINED
            if method == "getweaponslistprimaries":
                return GscArray(sorted(receiver.weapons))
            if method == "dodamage":
                dmg = int(args[0]) if len(args) > 0 else 0
                pos = args[1] if len(args) > 1 else UNDEFINED
                attacker = args[2] if len(args) > 2 else UNDEFINED
                receiver.damage_events.append(
                    {"damage": dmg, "pos": pos, "attacker": attacker}
                )
                cur_hp = int(receiver.get_field("health"))
                receiver.set_field("health", max(0, cur_hp - dmg))
                return UNDEFINED

        return super()._exec_method(receiver, method, args, line)


def _setup_pap_env(
    map_name: str = "nazi_zombie_factory",
    *,
    bz_enabled: bool = True,
    pap_enabled: bool = True,
    perks_enabled: bool = True,
    classes_enabled: bool = True,
    native_weapons: dict[str, str] | None = None,
) -> tuple[FakeDvarStore, PapGscRuntime, PapFakeEntity]:
    dvars = FakeDvarStore()
    dvars.set("bz_enabled", "1" if bz_enabled else "0")
    dvars.set("bz_pap_enabled", "1" if pap_enabled else "0")
    dvars.set("bz_perks_enabled", "1" if perks_enabled else "0")
    dvars.set("bz_classes_enabled", "1" if classes_enabled else "0")
    dvars.set("bz_elements_enabled", "0")
    dvars.set("bz_companions_enabled", "0")

    gsc = PapGscRuntime(MOD_ROOT, dvars)
    gsc.level.set_field("script", map_name)
    gsc.level.set_field("round_number", 1)

    if native_weapons is not None:
        zw = GscArray()
        for base_w, upg_w in native_weapons.items():
            entry = GscStruct()
            entry.set_field("upgrade_name", upg_w)
            zw.set_item(base_w, entry)
        gsc.level.set_field("zombie_weapons", zw)

    player = PapFakeEntity("PlayerOne", ent_num=0)
    player.set_field("score", 50000)
    player.give_weapon("thompson", make_current=True, stock=100)
    gsc.players.append(player)

    gsc.call(BZ_PAP_MOD, "bz_pap_register")
    gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
    gsc.call(BZ_HOOKS_MOD, "bz_init")
    return dvars, gsc, player


class TestBzPapRegistrationAndFourMapSinglePap(unittest.TestCase):
    """Seam 1: Hook registration, gate isolation, and 4-Map Single PaP (native vs scripted)."""

    def test_register_is_idempotent_and_classic_or_gate_off_is_noop(self) -> None:
        dvars = FakeDvarStore()
        dvars.set("bz_enabled", "0")
        dvars.set("bz_pap_enabled", "1")
        gsc = PapGscRuntime(MOD_ROOT, dvars)
        player = PapFakeEntity("ClassicPlayer", ent_num=0)
        player.give_weapon("thompson", make_current=True)
        gsc.players.append(player)

        gsc.call(BZ_PAP_MOD, "bz_pap_register")
        gsc.call(BZ_PAP_MOD, "bz_pap_register")  # idempotent

        hooks = gsc.level.get_field("bz_hooks")
        for hook_name in (
            "init",
            "player_connect",
            "player_spawned",
            "player_downed",
            "round_start",
            "end_game",
            "item_purchased",
            "actor_damage",
        ):
            entries = hooks[hook_name]
            self.assertIsNot(entries, UNDEFINED, f"Missing hook registration for {hook_name}")
            pap_entries = [entries[i] for i in range(entries.size) if entries[i].get_field("gate") == "pap"]
            self.assertEqual(len(pap_entries), 1, f"Hook {hook_name} must register exactly once under 'pap'")

        # Classic Mode: zero HUD, zero telemetry, zero damage changes
        gsc.call(BZ_HOOKS_MOD, "bz_init")
        zombie = PapFakeEntity("Z1", ent_num=20, is_player=False)
        zombie.set_field("health", 500)
        dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie,
            player,
            player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "thompson",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg, 100)
        self.assertEqual(gsc.hud_elems, [])
        self.assertEqual(gsc.emitted_events, [])

    def test_der_riese_single_pap_swaps_to_native_upgraded_weapon_when_available(self) -> None:
        _dvars, gsc, player = _setup_pap_env(
            map_name="nazi_zombie_factory",
            native_weapons={"thompson": "thompson_upgraded"},
        )

        self.assertFalse(gsc.call(BZ_PAP_MOD, "bz_pap_is_weapon_papped", player, "thompson"))
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_pap", "buy_pap:single_pap")
        )

        # Native Der Riese swap: thompson -> thompson_upgraded with max ammo
        self.assertEqual(player.get_field("score"), 45000)
        self.assertEqual(player.current_weapon, "thompson_upgraded")
        self.assertNotIn("thompson", player.weapons)
        self.assertIn("thompson_upgraded", player.weapons)
        self.assertEqual(player.weapon_stock["thompson_upgraded"], 220)
        self.assertTrue(gsc.call(BZ_PAP_MOD, "bz_pap_is_weapon_papped", player, "thompson_upgraded"))
        self.assertFalse(gsc.call(BZ_PAP_MOD, "bz_pap_is_weapon_papped", player, "thompson"))

        # Native *_upgraded weapon does NOT double-dip scripted +100% Tier 1 multiplier
        zombie = PapFakeEntity("Z1", ent_num=20, is_player=False)
        zombie.set_field("health", 1000)
        dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie,
            player,
            player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "thompson_upgraded",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg, 100)
        self.assertTrue(
            any("BZ_EVENT|PAP_SINGLE_UPGRADE|" in e and "mode=native" in e for e in gsc.emitted_events)
        )

    def test_nacht_verruckt_sumpf_single_pap_uses_scripted_tier1_with_double_damage_and_full_ammo(self) -> None:
        for stock_map in ("nazi_zombie_prototype", "nazi_zombie_asylum", "nazi_zombie_sumpf"):
            _dvars, gsc, player = _setup_pap_env(
                map_name=stock_map,
                native_weapons={"thompson": "thompson_upgraded"},  # even if table populated, non-factory stays scripted
            )
            player.weapon_stock["thompson"] = 25

            self.assertTrue(
                gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_pap", "buy_pap:single_pap")
            )

            # Weapon name stays "thompson" (no missing *_upgraded fastfile crash), flagged as Tier 1 PaP
            self.assertEqual(player.current_weapon, "thompson")
            self.assertNotIn("thompson_upgraded", player.weapons)
            self.assertTrue(player.get_field("bz_single_pap_weapons")["thompson"])
            self.assertTrue(gsc.call(BZ_PAP_MOD, "bz_pap_is_weapon_papped", player, "thompson"))
            self.assertEqual(player.weapon_stock["thompson"], 200)  # full reserve ammo refill

            # +100% Tier 1 PaP bullet damage (100 -> 200)
            zombie = PapFakeEntity("Z1", ent_num=20, is_player=False)
            zombie.set_field("health", 1000)
            dmg = gsc.call(
                BZ_HOOKS_MOD,
                "bz_actor_damage_dispatch",
                zombie,
                player,
                player,
                100,
                0,
                "MOD_RIFLE_BULLET",
                "thompson",
                UNDEFINED,
                UNDEFINED,
                "torso_upper",
                0,
            )
            self.assertEqual(dmg, 200, f"Scripted Tier 1 PaP should grant +100% damage on {stock_map}")
            self.assertTrue(
                any("BZ_EVENT|PAP_SINGLE_UPGRADE|" in e and "mode=scripted" in e for e in gsc.emitted_events),
                f"Missing scripted PAP_SINGLE_UPGRADE event on {stock_map}",
            )

    def test_der_riese_weapon_lacking_native_upgrade_falls_back_cleanly_to_scripted_tier1(self) -> None:
        _dvars, gsc, player = _setup_pap_env(
            map_name="nazi_zombie_factory",
            native_weapons={"thompson": "thompson_upgraded"},  # kar98k intentionally missing
        )
        player.give_weapon("kar98k", make_current=True, stock=15)

        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_pap", "buy_pap:single_pap")
        )
        self.assertEqual(player.current_weapon, "kar98k")
        self.assertTrue(gsc.call(BZ_PAP_MOD, "bz_pap_is_weapon_papped", player, "kar98k"))
        self.assertEqual(player.weapon_stock["kar98k"], 60)


class TestBzDoublePapAndPersistence(unittest.TestCase):
    """Seam 2: Double PaP (+75% damage, +50% reserve ammo composing with Double Ammo, down persistence)."""

    def test_double_pap_on_native_upgraded_weapon_boosts_damage_reserve_ammo_and_telemetry(self) -> None:
        _dvars, gsc, player = _setup_pap_env(
            map_name="nazi_zombie_factory",
            native_weapons={"thompson": "thompson_upgraded"},
        )
        # Simulate native Der Riese PaP weapon already held
        player.give_weapon("thompson_upgraded", make_current=True, stock=220)
        zombie = PapFakeEntity("Z1", ent_num=20, is_player=False)
        zombie.set_field("health", 5000)

        # Purchase Double PaP (5,000 pts test cap)
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_pap", "buy_pap:double_pap")
        )
        self.assertEqual(player.get_field("score"), 45000)
        self.assertTrue(gsc.call(BZ_STATE_MOD, "bz_state_is_weapon_double_pap", player, "thompson_upgraded"))

        # +50% reserve ammo: 220 * 1.5 = 330
        self.assertEqual(player.weapon_stock["thompson_upgraded"], 330)

        # +75% bullet damage: 200 * 1.75 = 350
        dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie,
            player,
            player,
            200,
            0,
            "MOD_RIFLE_BULLET",
            "thompson_upgraded",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg, 350)

        # Strictly independent of Elemental Weapons (no elemental state attached)
        self.assertIs(player.get_field("bz_element"), UNDEFINED)
        self.assertIs(zombie.get_field("bz_element_proc"), UNDEFINED)

        # Emits structured PAP_DOUBLE_UPGRADE telemetry
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|PAP_DOUBLE_UPGRADE|")
                and "weapon=thompson_upgraded" in e
                and "stock=330" in e
                for e in gsc.emitted_events
            ),
            f"Missing PAP_DOUBLE_UPGRADE event: {gsc.emitted_events}",
        )

    def test_double_pap_composes_with_double_ammo_in_both_purchase_orders(self) -> None:
        # Order A: Double Ammo first -> then Double PaP on native thompson_upgraded (220 * 3.0 = 660)
        _dvars1, gsc1, p1 = _setup_pap_env(map_name="nazi_zombie_factory")
        p1.give_weapon("thompson_upgraded", make_current=True, stock=220)
        self.assertTrue(
            gsc1.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_perks", "buy_apex:double_ammo")
        )
        self.assertTrue(
            gsc1.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_pap", "buy_pap:double_pap")
        )
        self.assertEqual(p1.weapon_stock["thompson_upgraded"], 660)

        # Order B: Double PaP first (330) -> then Double Ammo refreshes to 660
        _dvars2, gsc2, p2 = _setup_pap_env(map_name="nazi_zombie_factory")
        p2.give_weapon("thompson_upgraded", make_current=True, stock=220)
        self.assertTrue(
            gsc2.call(BZ_HOOKS_MOD, "bz_on_menu_response", p2, "bz_station_pap", "buy_pap:double_pap")
        )
        self.assertEqual(p2.weapon_stock["thompson_upgraded"], 330)
        self.assertTrue(
            gsc2.call(BZ_HOOKS_MOD, "bz_on_menu_response", p2, "bz_station_perks", "buy_apex:double_ammo")
        )
        self.assertEqual(p2.weapon_stock["thompson_upgraded"], 660)

    def test_scripted_tier1_plus_double_pap_stacks_on_non_factory_maps_and_persists_through_downs(self) -> None:
        _dvars, gsc, player = _setup_pap_env(map_name="nazi_zombie_prototype")
        player.give_perk("specialty_altmelee")
        zombie = PapFakeEntity("Z1", ent_num=20, is_player=False)
        zombie.set_field("health", 5000)

        # Single PaP (5000) + Double PaP (10000) + PaP Knife (5000) + PaP Bowie (5000) + PaP Cluster (5000)
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_pap", "buy_pap:single_pap")
        )
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_pap", "buy_pap:double_pap")
        )
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_arsenal", "buy_pap:pap_knife")
        )
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_arsenal", "buy_pap:pap_bowie")
        )
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_arsenal", "buy_pap:pap_cluster")
        )

        # Scripted Tier 1 (2.0x) * Double PaP (1.75x) = 3.5x -> 100 * 3.5 = 350; stock 200 * 1.5 = 300
        self.assertEqual(player.weapon_stock["thompson"], 300)
        dmg_before = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie,
            player,
            player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "thompson",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg_before, 350)

        # Down the player (clear stock perks too) -> ALL PaP upgrades must persist!
        player.clear_perks()
        gsc.call(BZ_STATE_MOD, "bz_state_on_player_downed", player, 2)
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_downed", player)

        self.assertTrue(gsc.call(BZ_PAP_MOD, "bz_pap_is_weapon_papped", player, "thompson"))
        self.assertTrue(gsc.call(BZ_STATE_MOD, "bz_state_is_weapon_double_pap", player, "thompson"))
        self.assertTrue(player.get_field("bz_pap_knife"))
        self.assertTrue(player.get_field("bz_pap_bowie"))
        self.assertTrue(player.get_field("bz_pap_cluster"))

        dmg_after = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie,
            player,
            player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "thompson",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg_after, 350)


class TestBzPapMeleeUpgrades(unittest.TestCase):
    """Seam 3: PaP Knife (3x melee) & PaP Bowie Knife (1-hit kill regular zombies any round)."""

    def test_pap_knife_deals_3x_melee_damage_and_emits_telemetry(self) -> None:
        _dvars, gsc, player = _setup_pap_env(map_name="nazi_zombie_factory")
        zombie = PapFakeEntity("Z1", ent_num=20, is_player=False)
        zombie.set_field("health", 1000)

        # Unupgraded knife: 150 dmg
        base_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie,
            player,
            player,
            150,
            0,
            "MOD_MELEE",
            "knife",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(base_dmg, 150)

        # Buy PaP Knife (5,000 pts) -> 3x melee = 450 dmg
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_arsenal", "buy_pap:pap_knife")
        )
        upgraded_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie,
            player,
            player,
            150,
            0,
            "MOD_MELEE",
            "knife",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(upgraded_dmg, 450)
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|PAP_MELEE_UPGRADE|") and "upgrade=pap_knife" in e
                for e in gsc.emitted_events
            )
        )

        # Owning Bowie Knife without pap_bowie does NOT get PaP Knife 3x multiplier
        player.give_perk("specialty_altmelee")
        bowie_unupgraded = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie,
            player,
            player,
            1000,
            0,
            "MOD_MELEE",
            "bowie_knife",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(bowie_unupgraded, 1000)

    def test_pap_bowie_one_hit_kills_regular_zombies_on_any_round_and_deals_3x_to_boss_or_dogs(self) -> None:
        _dvars, gsc, player = _setup_pap_env(map_name="nazi_zombie_factory")
        player.give_perk("specialty_altmelee")

        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_arsenal", "buy_pap:pap_bowie")
        )
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|PAP_MELEE_UPGRADE|") and "upgrade=pap_bowie" in e
                for e in gsc.emitted_events
            )
        )

        # Round 50 regular zombie with 500,000 HP -> instant kill (> 500,000)
        round50_zombie = PapFakeEntity("Z50", ent_num=21, is_player=False)
        round50_zombie.set_field("health", 500000)
        round50_zombie.set_field("maxhealth", 500000)
        kill_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            round50_zombie,
            player,
            player,
            1000,
            0,
            "MOD_MELEE",
            "thompson",  # WaW often passes held gun as sWeapon on MOD_MELEE
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertGreaterEqual(kill_dmg, 500000)

        # Hellhound (special enemy) -> 3x melee (3000), NOT instant kill
        dog = PapFakeEntity("Hellhound", ent_num=22, is_player=False)
        dog.set_field("health", 50000)
        dog.set_field("isdog", True)
        dog_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            dog,
            player,
            player,
            1000,
            0,
            "MOD_MELEE",
            "bowie_knife",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dog_dmg, 3000)

        # Boss enemy -> 3x melee (3000), NOT instant kill
        boss = PapFakeEntity("BossZombie", ent_num=23, is_player=False)
        boss.set_field("health", 50000)
        boss.set_field("is_boss", True)
        boss_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            boss,
            player,
            player,
            1000,
            0,
            "MOD_MELEE",
            "bowie_knife",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(boss_dmg, 3000)

        # Persists through down even when specialty_altmelee perk is cleared
        player.clear_perks()
        gsc.call(BZ_STATE_MOD, "bz_state_on_player_downed", player, 2)
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_downed", player)
        post_down_dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            round50_zombie,
            player,
            player,
            1000,
            0,
            "MOD_MELEE",
            "knife",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertGreaterEqual(post_down_dmg, 500000)


class TestBzPapClusterGrenade(unittest.TestCase):
    """Seam 4: PaP Cluster Grenade round-scaled primary + mini-clusters, Sapper & Blast Shield stacking."""

    def test_cluster_grenade_scales_lethally_spawns_mini_clusters_and_respects_sapper_and_blast_shield(self) -> None:
        _dvars, gsc, player = _setup_pap_env(map_name="nazi_zombie_factory")

        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_arsenal", "buy_pap:pap_cluster")
        )
        self.assertTrue(player.get_field("bz_pap_cluster"))
        self.assertTrue(gsc.call(BZ_PAP_MOD, "bz_pap_is_frag_grenade", "stielhandgranate"))
        self.assertTrue(gsc.call(BZ_PAP_MOD, "bz_pap_is_frag_grenade", "fraggrenade"))
        self.assertFalse(gsc.call(BZ_PAP_MOD, "bz_pap_is_frag_grenade", "zombie_cymbal_monkey"))
        self.assertFalse(gsc.call(BZ_PAP_MOD, "bz_pap_is_frag_grenade", "molotov"))

        # Round 25 (zombie health = 5240 -> primary = 6550, mini = 3406)
        gsc.level.set_field("round_number", 25)
        gsc.level.set_field("zombie_health", 5240)
        gsc.call(BZ_HOOKS_MOD, "bz_on_round_start", 25)

        z_center = PapFakeEntity("ZCenter", ent_num=30, is_player=False)
        z_center.set_field("health", 5240)
        z_center.set_field("origin", GscArray([100, 100, 0]))

        z_sapper_ring = PapFakeEntity("ZSapperRing", ent_num=31, is_player=False)
        z_sapper_ring.set_field("health", 5240)
        z_sapper_ring.set_field("origin", GscArray([440, 100, 0]))  # dist = 340 (> 256 base, <= 384 Sapper)

        z_far = PapFakeEntity("ZFar", ent_num=32, is_player=False)
        z_far.set_field("health", 5240)
        z_far.set_field("origin", GscArray([1200, 1200, 0]))

        gsc.ai_enemies.extend([z_center, z_sapper_ring, z_far])
        player.set_field("origin", GscArray([100, 100, 0]))
        player.set_field("health", 100)

        # Non-Sapper, no Blast Shield detonation at (100, 100, 0)
        res1 = gsc.call(BZ_PAP_MOD, "bz_pap_detonate_cluster", player, GscArray([100, 100, 0]), "stielhandgranate")
        self.assertEqual(res1.get_field("primary_damage"), 6550)
        self.assertEqual(res1.get_field("mini_damage"), 3406)
        self.assertEqual(res1.get_field("mini_count"), 4)
        self.assertEqual(res1.get_field("primary_radius"), 256)
        self.assertEqual(res1.get_field("mini_radius"), 160)
        self.assertEqual(z_center.get_field("health"), 0)  # killed lethally
        self.assertEqual(z_sapper_ring.get_field("health"), 5240)  # outside non-Sapper 256 radius
        self.assertEqual(z_far.get_field("health"), 5240)
        self.assertGreater(len(player.damage_events), 0)  # took capped self-damage without Blast Shield
        self.assertGreater(player.get_field("health"), 0)  # self-damage is capped, not 6550 instant self-kill
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|PAP_CLUSTER_DETONATE|")
                and "round=25" in e
                and "primary_dmg=6550" in e
                and "mini_dmg=3406" in e
                and "self_immune=0" in e
                for e in gsc.emitted_events
            )
        )

        # Now equip Sapper (1.5x radius -> 384/240, 10 grenades) + Blast Shield (0 self-damage)
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_class", "buy_class:sapper")
        )
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_perks", "buy_apex:blast_shield")
        )
        self.assertEqual(gsc.call(BZ_STATE_MOD, "bz_state_get_max_grenades", player), 10)
        player.damage_events.clear()
        player.set_field("health", 100)

        res2 = gsc.call(BZ_PAP_MOD, "bz_pap_detonate_cluster", player, GscArray([100, 100, 0]), "stielhandgranate")
        self.assertEqual(res2.get_field("primary_radius"), 384)
        self.assertEqual(res2.get_field("mini_radius"), 240)
        self.assertEqual(z_sapper_ring.get_field("health"), 0)  # now killed inside Sapper's 384 radius!
        self.assertEqual(z_far.get_field("health"), 5240)
        self.assertEqual(player.damage_events, [])  # 100% Blast Shield self-damage immunity
        self.assertEqual(player.get_field("health"), 100)
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|PAP_CLUSTER_DETONATE|")
                and "primary_radius=384" in e
                and "mini_radius=240" in e
                and "self_immune=1" in e
                for e in gsc.emitted_events
            )
        )


class TestBzPapHudAndWaw17Compliance(unittest.TestCase):
    """Seam 5: Top-right ASCII HUD badge, zero-leak disconnect/end_game cleanup, and WaW 1.7 syntax."""

    def test_top_right_ascii_pap_hud_updates_dynamically_and_cleans_up_with_zero_leaks(self) -> None:
        _dvars, gsc, p1 = _setup_pap_env(map_name="nazi_zombie_prototype")
        p2 = PapFakeEntity("PlayerTwo", ent_num=1)
        p2.set_field("score", 50000)
        p2.give_weapon("stg44", make_current=True, stock=100)
        gsc.players.append(p2)
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", p2)

        # No upgrades yet -> no HUD clutter created
        self.assertEqual(gsc.hud_elems, [])

        # Single PaP scripted on Nacht -> creates top-right badge showing "PAP I"
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_pap", "buy_pap:single_pap")
        self.assertEqual(len(gsc.hud_elems), 1)
        hud1 = gsc.hud_elems[0]
        self.assertIs(hud1.owner, p1)
        self.assertEqual(hud1.get_field("alignX"), "right")
        self.assertEqual(hud1.get_field("horzAlign"), "right")
        self.assertEqual(hud1.get_field("x"), -12)
        self.assertEqual(hud1.get_field("y"), 50)
        self.assertEqual(hud1.current_text, "PAP I")

        # Double PaP + PaP Knife + PaP Bowie + PaP Cluster -> shows "PAP II" and all concise flags
        p1.give_perk("specialty_altmelee")
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_pap", "buy_pap:double_pap")
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_pap:pap_knife")
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_pap:pap_bowie")
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_pap:pap_cluster")

        self.assertEqual(hud1.current_text, "PAP II | KNIFE+ | BOWIE+ | CLUSTER")
        self.assertTrue(all(32 <= ord(ch) <= 126 for ch in hud1.current_text))

        # Redundant HUD refresh with same state skips SetText() to protect configstrings
        prev_writes = len(hud1.text_history)
        gsc.call(BZ_PAP_MOD, "bz_pap_update_hud", p1)
        self.assertEqual(len(hud1.text_history), prev_writes)

        # Switching to un-upgraded secondary weapon drops "PAP II" while keeping melee/cluster flags
        p1.give_weapon("colt", make_current=True)
        gsc.call(BZ_PAP_MOD, "bz_pap_update_hud", p1)
        self.assertEqual(hud1.current_text, "KNIFE+ | BOWIE+ | CLUSTER")

        # Player 2 gets their own independent HUD element
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p2, "bz_station_pap", "buy_pap:single_pap")
        self.assertEqual(len(gsc.hud_elems), 2)
        hud2 = gsc.hud_elems[1]
        self.assertIs(hud2.owner, p2)
        self.assertEqual(hud2.current_text, "PAP I")

        # Disconnect destroys p1's HUD without affecting p2
        gsc.call(BZ_PAP_MOD, "bz_pap_destroy_player_hud", p1)
        self.assertTrue(hud1.destroyed)
        self.assertFalse(hud2.destroyed)

        # end_game destroys all remaining HUD elements with zero leaks and zero double-destroys
        gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.assertTrue(all(h.destroyed for h in gsc.hud_elems))
        self.assertTrue(all(h.destroy_count == 1 for h in gsc.hud_elems))

        # Dedicated child watcher threads were spawned cleanly on connect (never inline endon)
        spawned_thread_names = {t[1] for t in gsc._threads if t[0] is p1}
        for expected_watcher in (
            "bz_pap_watch_grenade_throws",
            "bz_pap_watch_weapon_switch",
            "bz_pap_watch_max_ammo",
            "bz_pap_watch_player_disconnect",
        ):
            self.assertIn(expected_watcher, spawned_thread_names)

    def test_pap_gate_disabled_is_noop_even_when_bz_enabled_and_double_pap_composes_with_other_damage_hooks(
        self,
    ) -> None:
        # Gate-off check: bz_enabled=1, bz_pap_enabled=0 -> complete noop
        _dvars_off, gsc_off, p_off = _setup_pap_env(
            map_name="nazi_zombie_factory", bz_enabled=True, pap_enabled=False
        )
        self.assertEqual(gsc_off.call(BZ_PAP_MOD, "bz_pap_apply_single_pap", p_off, "thompson"), "")
        self.assertFalse(gsc_off.call(BZ_PAP_MOD, "bz_pap_apply_double_pap", p_off, "thompson_upgraded"))
        self.assertIs(
            gsc_off.call(BZ_PAP_MOD, "bz_pap_detonate_cluster", p_off, GscArray([0, 0, 0]), "stielhandgranate"),
            UNDEFINED,
        )
        self.assertEqual(gsc_off.hud_elems, [])

        # Composition check: Double PaP (1.75x) composes cleanly with Perks/Class actor_damage hooks (e.g. AP II 1.6x * DT II 1.25x = 2.0x -> total 3.5x)
        _dvars, gsc, player = _setup_pap_env(map_name="nazi_zombie_factory")
        player.give_weapon("thompson_upgraded", make_current=True, stock=220)
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_pap", "buy_pap:double_pap")

        def mock_perks_damage(_self: Any, _zombie: Any, ctx: GscStruct) -> None:
            ctx.set_field("damage_mult", float(ctx.get_field("damage_mult")) * 1.6 * 1.25)

        gsc.call(
            BZ_HOOKS_MOD,
            "bz_register_hook",
            "actor_damage",
            gsc.register_py_callback("mock_perks_dmg", mock_perks_damage),
            "perks",
        )
        zombie = PapFakeEntity("ZComp", ent_num=40, is_player=False)
        zombie.set_field("health", 5000)
        dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie,
            player,
            player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "thompson_upgraded",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg, 350)  # 100 * 1.75 * 1.6 * 1.25 = 350

    def test_bz_pap_gsc_is_strictly_waw17_compliant(self) -> None:
        source = BZ_PAP_PATH.read_text(encoding="latin1")
        tokenize(source, filename=str(BZ_PAP_PATH))
        code_only = "\n".join(line.split("//", 1)[0] for line in source.splitlines())
        self.assertIsNone(re.search(r"\bforeach\b", code_only), "Forbidden foreach in _bz_pap.gsc")

        # Non-ASCII check across entire script (HUD strings & telemetry must be ASCII)
        non_ascii = [ch for ch in source if ord(ch) > 126 or (ord(ch) < 32 and ch not in "\t\r\n")]
        self.assertEqual(non_ascii, [], f"Non-ASCII characters in _bz_pap.gsc: {non_ascii!r}")

        gsc = PapGscRuntime(MOD_ROOT, FakeDvarStore())
        pap_mod = gsc.load_module(BZ_PAP_MOD)

        sync_funcs = (
            "bz_pap_register",
            "bz_pap_on_init",
            "bz_pap_on_player_connect",
            "bz_pap_on_player_spawned",
            "bz_pap_on_player_downed",
            "bz_pap_on_round_start",
            "bz_pap_on_end_game",
            "bz_pap_on_item_purchased",
            "bz_pap_on_actor_damage",
            "bz_pap_is_weapon_papped",
            "bz_pap_apply_single_pap",
            "bz_pap_apply_double_pap",
            "bz_pap_detonate_cluster",
            "bz_pap_update_hud",
            "bz_pap_destroy_player_hud",
            "bz_pap_try_native_console_upgrade",
            "bz_pap_on_native_weapon_taken",
            "bz_pap_format_native_prompt_text",
            "bz_pap_update_native_prompt_hud",
            "bz_pap_hide_native_prompt_hud",
        )
        for fn_name in sync_funcs:
            self.assertIn(fn_name, pap_mod, f"Missing expected function {fn_name}() in _bz_pap.gsc")
            self.assertFalse(
                _ast_contains_method_call(pap_mod[fn_name].body, "endon"),
                f"Forbidden endon() inside synchronous caller {fn_name}()",
            )


class TestBzNativePapConsoleIntegration(unittest.TestCase):
    """Seam 6 (POL-T4 #40): Der Riese native PaP console Double PaP, scripted bz_* Tier 1, & Co-op prompt HUD."""

    def _make_native_console_entities(
        self, gsc: PapGscRuntime
    ) -> tuple[PapFakeEntity, PapFakeEntity, PapFakeEntity]:
        trig = PapFakeEntity("zombie_vending_upgrade", ent_num=90, is_player=False)
        trig.set_field("origin", GscArray([-61, 577, 153]))
        trig.hint_string = "Hold &&1 for Pack-a-Punch [Cost: 5000]"
        machine = PapFakeEntity("vending_pack_a_punch", ent_num=91, is_player=False)
        machine.set_field("origin", GscArray([-61, 591.5, 114.5]))
        rollers = PapFakeEntity("packa_rollers", ent_num=92, is_player=False)
        rollers.set_field("origin", GscArray([-61, 591.5, 128]))
        gsc.world_entities[("targetname", "zombie_vending_upgrade")] = [trig]

        fx_table = GscArray()
        fx_table.set_item("packapunch_fx", "fx:packapunch")
        gsc.level.set_field("_effect", fx_table)

        inc = GscArray()
        for w in ("thompson", "thompson_upgraded", "stg44", "stg44_upgraded", "zombie_colt", "zombie_colt_upgraded"):
            inc.set_item(w, True)
        gsc.level.set_field("zombie_include_weapons", inc)
        return trig, machine, rollers

    def test_native_console_case_a_base_stock_falls_through_and_classic_mode_is_untouched(self) -> None:
        _dvars, gsc, player = _setup_pap_env(
            map_name="nazi_zombie_factory",
            native_weapons={"thompson": "thompson_upgraded", "stg44": "stg44_upgraded"},
        )
        trig, machine, rollers = self._make_native_console_entities(gsc)

        # Case A: Base stock native-upgradable weapon returns False -> 100% stock PaP path
        handled = gsc.call(
            BZ_PAP_MOD, "bz_pap_try_native_console_upgrade", trig, player, "thompson", machine, rollers
        )
        self.assertFalse(handled)
        self.assertEqual(player.get_field("score"), 50000)
        self.assertEqual(gsc.played_sounds, [])
        self.assertEqual(gsc.sound_positions, [])
        self.assertEqual(gsc.played_fx, [])

        # Utility / non-primary item (e.g. perk bottle) returns False without charging or playing deny
        handled_bottle = gsc.call(
            BZ_PAP_MOD,
            "bz_pap_try_native_console_upgrade",
            trig,
            player,
            "zombie_perk_bottle_jugg",
            machine,
            rollers,
        )
        self.assertFalse(handled_bottle)
        self.assertEqual(player.get_field("score"), 50000)
        self.assertEqual(gsc.played_sounds, [])

        # Classic Mode (bz_pap_enabled=0) returns False even for native *_upgraded or bz_* weapons
        _dvars_off, gsc_off, p_off = _setup_pap_env(
            map_name="nazi_zombie_factory", bz_enabled=True, pap_enabled=False
        )
        trig_off, machine_off, rollers_off = self._make_native_console_entities(gsc_off)
        p_off.give_weapon("thompson_upgraded", make_current=True, stock=220)
        self.assertFalse(
            gsc_off.call(
                BZ_PAP_MOD,
                "bz_pap_try_native_console_upgrade",
                trig_off,
                p_off,
                "thompson_upgraded",
                machine_off,
                rollers_off,
            )
        )
        self.assertEqual(p_off.get_field("score"), 50000)
        self.assertEqual(gsc_off.played_sounds, [])

    def test_native_console_case_b_and_d_double_pap_dynamic_cost_audio_fx_debounce_and_deny(self) -> None:
        _dvars, gsc, player = _setup_pap_env(
            map_name="nazi_zombie_factory",
            native_weapons={"thompson": "thompson_upgraded", "stg44": "stg44_upgraded"},
        )
        trig, machine, rollers = self._make_native_console_entities(gsc)
        player.give_weapon("thompson_upgraded", make_current=True, stock=220)

        # Case B: Already native-PaP'd weapon -> Double PaP at dynamic bz_get_pap_upgrade_price("double_pap") (5000)
        handled = gsc.call(
            BZ_PAP_MOD, "bz_pap_try_native_console_upgrade", trig, player, "thompson_upgraded", machine, rollers
        )
        self.assertTrue(handled)
        self.assertEqual(player.get_field("score"), 45000)
        self.assertTrue(gsc.call(BZ_STATE_MOD, "bz_state_is_weapon_double_pap", player, "thompson_upgraded"))
        self.assertEqual(player.weapon_stock["thompson_upgraded"], 330)
        self.assertEqual(player.client_dvars.get("ui_bz_pap_double_pap"), "MAXED (II)")
        self.assertTrue(
            any(snd == "bottle_dispense3d" for snd, _ in gsc.sound_positions),
            f"Expected bottle_dispense3d sound, got {gsc.sound_positions}",
        )
        self.assertTrue(
            any(ent is rollers and snd == "packa_weap_ready" for ent, snd in gsc.played_sounds),
            f"Expected packa_weap_ready on rollers, got {gsc.played_sounds}",
        )
        self.assertTrue(
            any(fx == "fx:packapunch" for fx, _ in gsc.played_fx),
            f"Expected packapunch_fx, got {gsc.played_fx}",
        )
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|PAP_DOUBLE_UPGRADE|")
                and "weapon=thompson_upgraded" in e
                and "console=native" in e
                for e in gsc.emitted_events
            ),
            f"Missing console=native PAP_DOUBLE_UPGRADE event: {gsc.emitted_events}",
        )

        # Debounce: rapid Use repeat within 750ms is silently consumed without deny spam
        gsc.played_sounds.clear()
        gsc.sim_time_ms += 200
        self.assertTrue(
            gsc.call(
                BZ_PAP_MOD, "bz_pap_try_native_console_upgrade", trig, player, "thompson_upgraded", machine, rollers
            )
        )
        self.assertEqual(gsc.played_sounds, [])
        self.assertEqual(player.get_field("score"), 45000)

        # Case D: After debounce expires, already Double PaP'd weapon plays deny sound & consumes cleanly
        gsc.sim_time_ms += 800
        self.assertTrue(
            gsc.call(
                BZ_PAP_MOD, "bz_pap_try_native_console_upgrade", trig, player, "thompson_upgraded", machine, rollers
            )
        )
        self.assertTrue(any(ent is trig and snd == "deny" for ent, snd in gsc.played_sounds))
        self.assertEqual(player.get_field("score"), 45000)

        # Insufficient points on another player plays deny & deducts 0 without interfering with p1
        p2 = PapFakeEntity("PoorPlayer", ent_num=1)
        p2.set_field("score", 2000)
        p2.give_weapon("stg44_upgraded", make_current=True, stock=240)
        gsc.players.append(p2)
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", p2)
        gsc.played_sounds.clear()

        self.assertTrue(
            gsc.call(
                BZ_PAP_MOD, "bz_pap_try_native_console_upgrade", trig, p2, "stg44_upgraded", machine, rollers
            )
        )
        self.assertTrue(any(ent is trig and snd == "deny" for ent, snd in gsc.played_sounds))
        self.assertEqual(p2.get_field("score"), 2000)
        self.assertFalse(gsc.call(BZ_STATE_MOD, "bz_state_is_weapon_double_pap", p2, "stg44_upgraded"))

    def test_native_console_case_c_bz_weapon_scripted_tier1_to_double_pap_and_native_pickup_sync(self) -> None:
        _dvars, gsc, player = _setup_pap_env(
            map_name="nazi_zombie_factory",
            native_weapons={"thompson": "thompson_upgraded", "stg44": "stg44_upgraded"},
        )
        trig, machine, rollers = self._make_native_console_entities(gsc)
        player.set_field("score", 25000)
        player.give_weapon("bz_acid_sprayer", make_current=True, stock=40)

        # Case C: Un-upgraded bz_* weapon -> scripted Tier 1 PaP (5000 pts)
        self.assertTrue(
            gsc.call(
                BZ_PAP_MOD, "bz_pap_try_native_console_upgrade", trig, player, "bz_acid_sprayer", machine, rollers
            )
        )
        self.assertEqual(player.get_field("score"), 20000)
        self.assertTrue(gsc.call(BZ_PAP_MOD, "bz_pap_is_weapon_papped", player, "bz_acid_sprayer"))
        self.assertEqual(player.weapon_stock["bz_acid_sprayer"], 120)
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|PAP_SINGLE_UPGRADE|")
                and "weapon=bz_acid_sprayer" in e
                and "mode=scripted" in e
                and "console=native" in e
                for e in gsc.emitted_events
            ),
            f"Missing console=native PAP_SINGLE_UPGRADE event: {gsc.emitted_events}",
        )

        # Case B follow-up after debounce: scripted Tier 1 bz_acid_sprayer -> Double PaP (5000 pts)
        gsc.sim_time_ms += 900
        self.assertTrue(
            gsc.call(
                BZ_PAP_MOD, "bz_pap_try_native_console_upgrade", trig, player, "bz_acid_sprayer", machine, rollers
            )
        )
        self.assertEqual(player.get_field("score"), 15000)
        self.assertTrue(gsc.call(BZ_STATE_MOD, "bz_state_is_weapon_double_pap", player, "bz_acid_sprayer"))
        self.assertEqual(player.weapon_stock["bz_acid_sprayer"], 180)  # 120 * 1.5

        zombie = PapFakeEntity("ZAcid", ent_num=30, is_player=False)
        zombie.set_field("health", 5000)
        dmg = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            zombie,
            player,
            player,
            100,
            0,
            "MOD_RIFLE_BULLET",
            "bz_acid_sprayer",
            UNDEFINED,
            UNDEFINED,
            "torso_upper",
            0,
        )
        self.assertEqual(dmg, 350)  # 100 * 2.0 (Tier 1) * 1.75 (Double PaP)

        # Native pickup hook refreshes Double Ammo reserve stock & HUD immediately
        self.assertTrue(
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_perks", "buy_apex:double_ammo")
        )
        player.give_weapon("stg44_upgraded", make_current=True, stock=240)
        gsc.call(BZ_PAP_MOD, "bz_pap_on_native_weapon_taken", player, "stg44_upgraded")
        self.assertEqual(player.weapon_stock["stg44_upgraded"], 480)  # 240 * 2.0 Double Ammo

    def test_coop_safe_native_pap_proximity_prompt_hud_and_zero_leak_cleanup(self) -> None:
        _dvars, gsc, p1 = _setup_pap_env(
            map_name="nazi_zombie_factory",
            native_weapons={"thompson": "thompson_upgraded"},
        )
        trig, machine, rollers = self._make_native_console_entities(gsc)
        orig_hint = trig.hint_string

        p2 = PapFakeEntity("PlayerTwo", ent_num=1)
        p2.set_field("score", 50000)
        p2.give_weapon("bz_cryo_cannon", make_current=True, stock=96)
        gsc.players.append(p2)
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", p2)

        # Factory spawns the native console prompt watcher child thread
        p1_threads = {t[1] for t in gsc._threads if t[0] is p1}
        self.assertIn("bz_pap_watch_native_console_prompt", p1_threads)

        # Both players stand right next to native PaP, but PaP is NOT unlocked yet -> prompt stays hidden
        p1.set_field("origin", GscArray([-61, 520, 153]))
        p2.set_field("origin", GscArray([-40, 530, 153]))
        p1.give_weapon("thompson_upgraded", make_current=True, stock=220)
        gsc.call(BZ_PAP_MOD, "bz_pap_update_native_prompt_hud", p1)
        gsc.call(BZ_PAP_MOD, "bz_pap_update_native_prompt_hud", p2)
        self.assertEqual(gsc.hud_elems, [])

        # Unlock native PaP via Pack_A_Punch_on flag
        flags = GscArray()
        flags.set_item("Pack_A_Punch_on", True)
        gsc.level.set_field("flag", flags)

        # P1 holding base stock gun -> prompt stays hidden (stock hint untouched)
        p1.give_weapon("thompson", make_current=True, stock=200)
        gsc.call(BZ_PAP_MOD, "bz_pap_update_native_prompt_hud", p1)
        self.assertIs(p1.get_field("bz_pap_prompt_hud"), UNDEFINED)

        # P1 switches to native thompson_upgraded, P2 holds un-upgraded bz_cryo_cannon
        p1.give_weapon("thompson_upgraded", make_current=True, stock=220)
        gsc.call(BZ_PAP_MOD, "bz_pap_update_native_prompt_hud", p1)
        gsc.call(BZ_PAP_MOD, "bz_pap_update_native_prompt_hud", p2)

        prompt1 = p1.get_field("bz_pap_prompt_hud")
        prompt2 = p2.get_field("bz_pap_prompt_hud")
        self.assertIsInstance(prompt1, FakeHudElem)
        self.assertIsInstance(prompt2, FakeHudElem)
        self.assertEqual(prompt1.current_text, "Press [F] for Double Pack-a-Punch [Cost: 5000]")
        self.assertEqual(prompt2.current_text, "Press [F] for Pack-a-Punch [Cost: 5000]")
        self.assertEqual(prompt1.get_field("alpha"), 1)
        self.assertEqual(prompt2.get_field("alpha"), 1)
        # Global trigger hint string was NEVER mutated for teammates!
        self.assertEqual(trig.hint_string, orig_hint)

        # P1 Double-PaPs thompson_upgraded -> prompt updates to PAP II maxed message
        self.assertTrue(
            gsc.call(
                BZ_PAP_MOD, "bz_pap_try_native_console_upgrade", trig, p1, "thompson_upgraded", machine, rollers
            )
        )
        self.assertEqual(prompt1.current_text, "Weapon Already Double Pack-a-Punched (PAP II)")
        self.assertEqual(prompt2.current_text, "Press [F] for Pack-a-Punch [Cost: 5000]")

        # P1 walks away (> 110u) -> P1 prompt hides, P2 prompt stays visible
        p1.set_field("origin", GscArray([500, 500, 153]))
        gsc.call(BZ_PAP_MOD, "bz_pap_update_native_prompt_hud", p1)
        gsc.call(BZ_PAP_MOD, "bz_pap_update_native_prompt_hud", p2)
        self.assertEqual(prompt1.get_field("alpha"), 0)
        self.assertEqual(prompt2.get_field("alpha"), 1)

        # Disconnect destroys P1's HUDs (badge + prompt) without affecting P2; end_game cleans up P2 cleanly
        gsc.call(BZ_PAP_MOD, "bz_pap_destroy_player_hud", p1)
        self.assertTrue(prompt1.destroyed)
        self.assertFalse(prompt2.destroyed)
        gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.assertTrue(all(h.destroyed for h in gsc.hud_elems))
        self.assertTrue(all(h.destroy_count == 1 for h in gsc.hud_elems))


if __name__ == "__main__":
    unittest.main()
