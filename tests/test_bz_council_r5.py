"""Regression tests for Council Polish Round 5 fixes."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import build_mod
from tests.gsc_runtime import FakeDvarStore, GscArray, GscStruct, UNDEFINED, _waw_to_str
from tests.test_bz_classes import BZ_CLASSES_MOD, ClassFakeEntity, TestFieldMedicAndTitanClasses
from tests.test_bz_elem_stock import BZ_ELEM_STOCK_MOD, ElemStockFakeEntity, ElemStockGscRuntime
from tests.test_bz_gauntlet_bridge import (
    ACID,
    BRIDGE_MOD,
    BZ_HOOKS_MOD,
    BZ_STATE_MOD,
    GAUNTLET_MODE_MOD,
    LEDGER,
    VERRUCKT,
    TestGauntletWeaponCarryover,
    _make_enhanced_dvars,
)
from tests.test_bz_hooks_and_build import BzGscParser, FakeEntity, MOD_ROOT, tokenize
from tests.test_bz_pap import BZ_PAP_MOD, PapFakeEntity, PapGscRuntime
from tests.test_bz_perks import BZ_PERKS_MOD, BzPerksRuntime, PerksFakeEntity
from tests.test_bz_special_weapons import BZ_SPECIAL_MOD, SpecialFakeEntity, _setup_special_env
from tests.test_bz_stations import BZ_STATIONS_MOD, StationHudRuntime
from tests.test_gauntlet_bz_integration import GauntletBzRuntime, _make_player


class TestCouncilRound5Fixes(unittest.TestCase):
    def test_s1_stage_clear_revive_deletes_revivetrigger_and_restores_weapons_before_notify(self) -> None:
        events: list[str] = []

        class ReviveRuntime(GauntletBzRuntime):
            def _exec_method(self, receiver, method, args, line):
                if method == "reviveplayer":
                    events.append("reviveplayer")
                    receiver.set_field("health", 100)
                    return UNDEFINED
                if method == "delete":
                    events.append("delete_trigger")
                if method == "notify" and args:
                    events.append(f"notify:{_waw_to_str(args[0])}")
                return super()._exec_method(receiver, method, args, line)

        runtime = ReviveRuntime(MOD_ROOT, _make_enhanced_dvars())
        laststand = (
            "player_is_in_laststand() { return IsDefined( self.revivetrigger ); }\n"
            "laststand_giveback_player_weapons() { self TakeWeapon( \"colt\" ); self GiveWeapon( \"thompson\" ); }\n"
        )
        utility = "setClientSysState( key, value, player ) { return; }"
        for mod_name, src in (("maps/_laststand", laststand), ("maps/_utility", utility)):
            runtime._modules[mod_name] = BzGscParser(tokenize(src, filename=mod_name), filename=mod_name).parse_module()

        player = _make_player(runtime, "7", "DownedAtClear")
        trigger = FakeEntity("revivetrigger", ent_num=50, is_player=False)
        player.set_field("revivetrigger", trigger)
        player.set_field("weaponinventory", GscArray(["colt", "thompson"]))
        runtime.call(GAUNTLET_MODE_MOD, "protect_players_for_stage_clear")

        notifies = [name for recv, name in runtime.notifies if recv is player]
        # Must NOT send stop_revive_trigger (which would strand an active reviver's syrette);
        # deleting revivetrigger lets stock revive_do_revive unwind cleanly and triggers our guard.
        self.assertNotIn("stop_revive_trigger", notifies)
        self.assertIn("player_revived", notifies)
        self.assertTrue(trigger.deleted)
        self.assertIs(player.get_field("revivetrigger"), UNDEFINED)
        self.assertIn("thompson", player.weapons)
        self.assertLess(events.index("delete_trigger"), events.index("notify:player_revived"))

    def test_f1_recompute_max_health_reasserts_after_health_write(self) -> None:
        class ClobberHealthEntity(PerksFakeEntity):
            def set_field(self, name: str, value) -> None:
                super().set_field(name, value)
                if name.lower() == "health":
                    super().set_field("maxhealth", 100)

        dvars = _make_enhanced_dvars()
        gsc = BzPerksRuntime(MOD_ROOT, dvars)
        gsc.level.set_field("script", "nazi_zombie_prototype")
        p = ClobberHealthEntity("HurtBuyer", ent_num=0)
        p.set_field("score", 50000)
        p.set_field("health", 40)
        p.set_field("maxhealth", 100)
        p.give_weapon("colt", make_current=True, stock=80)
        gsc.players.append(p)
        gsc.call(BZ_PERKS_MOD, "bz_perks_register")
        gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        gsc.call(BZ_HOOKS_MOD, "bz_init")

        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_perks", "buy_perk:juggernog")
        self.assertEqual(p.get_field("maxhealth"), 160)
        self.assertEqual(p.get_field("health"), 100)

    def test_f2_station_bought_stock_perks_are_unset_on_down(self) -> None:
        dvars = _make_enhanced_dvars()
        gsc = BzPerksRuntime(MOD_ROOT, dvars)
        gsc.level.set_field("script", "nazi_zombie_prototype")
        p = PerksFakeEntity("Solo", ent_num=0)
        p.set_field("score", 100000)
        p.set_field("health", 100)
        p.set_field("maxhealth", 100)
        p.give_weapon("colt", make_current=True, stock=80)
        gsc.players.append(p)
        gsc.call(BZ_PERKS_MOD, "bz_perks_register")
        gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        gsc.call(BZ_HOOKS_MOD, "bz_init")

        for pid in ("juggernog", "speed_cola", "double_tap", "quick_revive"):
            gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_perks", f"buy_perk:{pid}")

        gsc.call(BZ_HOOKS_MOD, "bz_on_player_downed", p)
        for spec in ("specialty_armorvest", "specialty_fastreload", "specialty_rof", "specialty_quickrevive"):
            self.assertFalse(p.has_perk(spec))
        gsc.call(BZ_PERKS_MOD, "bz_perks_sync_stock_perks", p)
        for pid in ("juggernog", "speed_cola", "double_tap", "quick_revive"):
            self.assertFalse(gsc.call(BZ_STATE_MOD, "bz_state_has_perk", p, pid))

    def test_f3_g1_double_ammo_overflow_reserve_feeds_clamped_stock_weapons(self) -> None:
        class ClampingRuntime(BzPerksRuntime):
            def _exec_method(self, receiver, method, args, line):
                if method == "setweaponammostock" and isinstance(receiver, PerksFakeEntity):
                    w = _waw_to_str(args[0]).lower()
                    amt = int(args[1])
                    cap = self.weapon_max_ammo.get(w, 120)
                    receiver.weapon_stock[w] = max(0, min(amt, cap))
                    return UNDEFINED
                return super()._exec_method(receiver, method, args, line)

        dvars = _make_enhanced_dvars()
        gsc = ClampingRuntime(MOD_ROOT, dvars)
        gsc.level.set_field("script", "nazi_zombie_factory")
        p = PerksFakeEntity("Apex", ent_num=0)
        p.set_field("score", 100000)
        p.give_weapon("thompson", make_current=True, stock=150)
        gsc.players.append(p)
        gsc.call(BZ_PERKS_MOD, "bz_perks_register")
        gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        gsc.call(BZ_HOOKS_MOD, "bz_init")

        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_perks", "buy_apex:double_ammo")
        base_cap = gsc.weapon_max_ammo["thompson"]
        self.assertEqual(p.weapon_stock["thompson"], base_cap)
        self.assertEqual(int(p.get_field("bz_overflow_reserve")["thompson"]), base_cap)

        # Spend 60 reserve rounds and drain overflow bank -> engine reserve tops back up!
        p.weapon_stock["thompson"] = base_cap - 60
        granted = gsc.call(BZ_PERKS_MOD, "bz_perks_drain_overflow_reserve", p)
        self.assertEqual(granted, 60)
        self.assertEqual(p.weapon_stock["thompson"], base_cap)
        self.assertEqual(int(p.get_field("bz_overflow_reserve")["thompson"]), base_cap - 60)

        # Going down clears the overflow bank.
        gsc.call(BZ_HOOKS_MOD, "bz_on_player_downed", p)
        self.assertEqual(len(p.get_field("bz_overflow_reserve")._data), 0)

    def test_f5_coop_skips_shared_server_dvars_while_solo_sets_them(self) -> None:
        # 1. Solo writes and resets the 5 server-simulated dvars (keys lowercased in FakeEntity).
        solo_gsc = BzPerksRuntime(MOD_ROOT, _make_enhanced_dvars())
        solo_gsc.level.set_field("script", "nazi_zombie_factory")
        solo_p = PerksFakeEntity("SoloHost", ent_num=0)
        solo_p.set_field("score", 100000)
        solo_p.give_weapon("colt", make_current=True, stock=80)
        solo_gsc.players.append(solo_p)
        solo_gsc.call(BZ_PERKS_MOD, "bz_perks_register")
        solo_gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        solo_gsc.call(BZ_HOOKS_MOD, "bz_init")
        solo_gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", solo_p, "bz_station_perks", "buy_perk:staminup")
        solo_gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", solo_p, "bz_station_perks", "buy_perk:speed_cola")
        solo_gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", solo_p, "bz_station_perks", "buy_t2:speed_cola")
        self.assertEqual(solo_p.client_dvars.get("player_sprinttime"), "8")
        self.assertEqual(solo_p.client_dvars.get("perk_weapreloadmultiplier"), "0.35")

        # 2. Mid-match 1->2 player join resets previously written solo dvars back to stock defaults,
        #    and going down also resets them even with 2 players present (A8 / O9 / F12).
        late_p2 = PerksFakeEntity("LateAlly", ent_num=1)
        late_p2.set_field("score", 50000)
        late_p2.give_weapon("colt", make_current=True, stock=80)
        solo_gsc.players.append(late_p2)
        solo_gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", late_p2)
        self.assertEqual(solo_p.client_dvars.get("player_sprinttime"), "4")
        self.assertEqual(solo_p.client_dvars.get("perk_weapreloadmultiplier"), "0.5")

        # Simulate solo dvars still flagged before down in a 2-player lobby -> down resets them.
        solo_p.set_field("bz_applied_solo_dvars", True)
        solo_p.client_dvars["player_sprinttime"] = "12"
        solo_gsc.call(BZ_HOOKS_MOD, "bz_on_player_downed", solo_p)
        self.assertEqual(solo_p.client_dvars.get("player_sprinttime"), "4")

        # 3. 2->1 disconnect re-applies owned solo perk dvars for the remaining solo survivor (A11 / S9).
        solo_gsc.players.remove(late_p2)
        solo_gsc.call(BZ_HOOKS_MOD, "bz_on_player_spawned", solo_p)
        solo_gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", solo_p, "bz_station_perks", "buy_perk:staminup")
        solo_gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", solo_p, "bz_station_perks", "buy_perk:speed_cola")
        solo_gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", solo_p, "bz_station_perks", "buy_t2:speed_cola")
        # A fresh 2nd player joins (1->2 resets solo dvars), then disconnects (2->1 restores them).
        late_p3 = PerksFakeEntity("LateAlly2", ent_num=2)
        late_p3.set_field("score", 50000)
        late_p3.give_weapon("colt", make_current=True, stock=80)
        solo_gsc.players.append(late_p3)
        solo_gsc.call(BZ_HOOKS_MOD, "bz_on_player_connect", late_p3)
        self.assertEqual(solo_p.client_dvars.get("player_sprinttime"), "4")
        self.assertEqual(solo_p.client_dvars.get("perk_weapreloadmultiplier"), "0.5")
        solo_gsc.players.remove(late_p3)
        solo_gsc.call(BZ_PERKS_MOD, "bz_perks_on_player_disconnect", late_p3)
        self.assertEqual(solo_p.client_dvars.get("player_sprinttime"), "8")
        self.assertEqual(solo_p.client_dvars.get("perk_weapreloadmultiplier"), "0.35")

        # 4. Co-op session never writes the 5 shared dvars, and Speed Cola II grants Fast Swap
        #    without an abusable reload-cancel script watcher (A10 / O10 / F15).
        dvars = _make_enhanced_dvars()
        gsc = BzPerksRuntime(MOD_ROOT, dvars)
        gsc.level.set_field("script", "nazi_zombie_factory")
        p1 = PerksFakeEntity("Host", ent_num=0)
        p2 = PerksFakeEntity("Ally", ent_num=1)
        for p in (p1, p2):
            p.set_field("score", 100000)
            p.give_weapon("thompson", make_current=True, stock=120)
            p.weapon_clips = {"thompson": 5}
            gsc.players.append(p)
        gsc.call(BZ_PERKS_MOD, "bz_perks_register")
        gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
        gsc.call(BZ_HOOKS_MOD, "bz_init")

        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_perks", "buy_perk:staminup")
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_perks", "buy_perk:speed_cola")
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_perks", "buy_t2:speed_cola")
        for key in (
            "player_sprinttime",
            "player_sprintspeedscale",
            "player_adsstrafespeedscale",
            "perk_weapreloadmultiplier",
            "perk_weapswitchmultiplier",
        ):
            self.assertNotIn(key, p1.client_dvars)
        self.assertTrue(p1.has_perk("specialty_longersprint"))
        self.assertTrue(p1.has_perk("specialty_fastreload"))
        self.assertTrue(p1.get_field("bz_fast_swap_active"))
        self.assertEqual(p1.client_dvars.get("cg_weaponcycledelay"), "0")
        self.assertEqual(float(p1.get_field("bz_reload_mult")), 0.5)
        self.assertEqual(float(p1.get_field("bz_swap_mult")), 1.0)

    def test_s2_f16_o11_coop_revive_strips_excess_mule_kick_weapons_in_live_order(self) -> None:
        runtime = GauntletBzRuntime(MOD_ROOT, _make_enhanced_dvars())
        player = _make_player(runtime, "7", "Revivable")
        player.take_weapon("stielhandgranate")
        runtime.call(BZ_HOOKS_MOD, "bz_init")
        self.assertTrue(runtime.call(BZ_STATE_MOD, "bz_try_buy_perk", player, "mule_kick").get_field("ok"))
        self.assertTrue(runtime.call(BZ_STATE_MOD, "bz_try_buy_perk_t2", player, "mule_kick").get_field("ok"))
        for w in ("thompson", "stg44", "zombie_mg42"):
            player.give_weapon(w, make_current=True)
            runtime.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", player)
        original = tuple(player.primary_weapons)
        self.assertEqual(len(original), 4)

        # Stock PlayerLastStand sets revivetrigger & swaps to colt BEFORE player_downed fires.
        player.set_field("revivetrigger", FakeEntity("trig", ent_num=60, is_player=False))
        for w in original:
            player.take_weapon(w)
        player.give_weapon("colt", make_current=True)
        runtime.call(BZ_HOOKS_MOD, "bz_on_player_downed", player)

        # Live WaW revive_success() order (F16 / O11):
        # 1. "player_revived" fires FIRST while revivetrigger is STILL defined and only colt is held.
        runtime.call(BZ_HOOKS_MOD, "bz_on_player_revived", player, player)
        # bz_pending_mule_strip_order MUST still be preserved!
        self.assertEqual(len(player.get_field("bz_pending_mule_strip_order")), 4)

        # 2. revivetrigger is deleted, then laststand_giveback_player_weapons() restores all 4 guns
        #    in reversed order, then our injected post-giveback bz_perks_on_player_revived runs.
        player.set_field("revivetrigger", UNDEFINED)
        player.take_weapon("colt")
        for w in reversed(original):
            player.give_weapon(w)
        runtime.call(BZ_PERKS_MOD, "bz_perks_on_player_revived", player, player)
        self.assertEqual(set(player.primary_weapons), set(original[:2]))
        self.assertEqual(len(player.primary_weapons), 2)

    def test_a2_o1_s3_spectator_reconnect_defers_bz_restore_and_preserves_ledger(self) -> None:
        fixtures = TestGauntletWeaponCarryover()
        dvars = _make_enhanced_dvars()
        dvars.set(LEDGER, "g_7=ac:2")
        dvars.set("gauntlet_bz_perks", "g_7=su|-|-")
        dvars.set("gauntlet_disconnected_players", "g_7")
        runtime = fixtures.make_stage(dvars, VERRUCKT)
        player = fixtures.add_player(runtime, "7")
        player.set_field("sessionstate", "spectator")

        runtime.call(GAUNTLET_MODE_MOD, "apply_player_starting_points", player, 1, VERRUCKT, True)
        self.assertTrue(player.get_field("gauntlet_bz_restore_pending"))
        self.assertNotEqual(player.get_field("gauntlet_bz_restored"), True)

        # Mid-stage checkpoint while still spectating must preserve ledgers.
        runtime.call(GAUNTLET_MODE_MOD, "snapshot_all_players_points", VERRUCKT)
        self.assertEqual(dvars.get(LEDGER), "g_7=ac:2")
        self.assertEqual(dvars.get("gauntlet_bz_perks"), "g_7=su|-|-")

        # Live spawn completes deferred BZ restore.
        player.set_field("sessionstate", "playing")
        player.give_weapon("zombie_colt", make_current=True)
        runtime.call(BZ_HOOKS_MOD, "bz_on_player_spawned", player)
        self.assertTrue(player.get_field("gauntlet_bz_restored"))
        self.assertFalse(player.get_field("gauntlet_bz_restore_pending"))
        self.assertIn(ACID, player.weapons)
        self.assertTrue(runtime.call(BZ_STATE_MOD, "bz_state_has_perk", player, "staminup"))

    def test_a3_a4_g2_equipment_rejected_by_pap_and_preserved_by_arsenal(self) -> None:
        betty = "mine_bouncing_betty"

        class EquipmentRuntime(PapGscRuntime):
            def _exec_method(self, receiver, method, args, line):
                if method == "getweaponslistprimaries":
                    return GscArray(sorted(receiver.weapons - {betty}))
                return super()._exec_method(receiver, method, args, line)

        r = EquipmentRuntime(MOD_ROOT, _make_enhanced_dvars())
        r.level.set_field("script", VERRUCKT)
        r.call(BZ_HOOKS_MOD, "bz_init")
        p = TestGauntletWeaponCarryover().add_player(r)
        for gun in ("zombie_colt", "zombie_thompson", betty):
            p.give_weapon(gun, make_current=True)

        before = p.get_field("score")
        r.call(BZ_STATIONS_MOD, "bz_stations_open_for_player", p, "pap")
        r.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_pap", "buy_pap:single_pap")
        self.assertEqual(p.get_field("score"), before)
        self.assertEqual(p.client_dvars["ui_bz_pap_single_pap"], "NO WEAPON")

        r.call(BZ_STATIONS_MOD, "bz_stations_open_for_player", p, "arsenal")
        r.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_arsenal", "buy_element:acid_sprayer")
        self.assertIn(betty, p.weapons)
        self.assertIn(ACID, p.weapons)
        self.assertEqual(len(p.weapons - {betty}), 2)

    def test_a5_o2_g3_s4_downed_and_stage_clear_block_station_and_native_pap(self) -> None:
        r = StationHudRuntime(MOD_ROOT, _make_enhanced_dvars())
        r.level.set_field("script", VERRUCKT)
        r.call(BZ_HOOKS_MOD, "bz_init")
        p = FakeEntity("Host", ent_num=0)
        p.set_field("score", 20000)
        p.set_field("sessionstate", "playing")
        r.players.append(p)
        r.call(BZ_HOOKS_MOD, "bz_on_player_spawned", p)

        # Downed blocks open & purchase
        p.set_field("revivetrigger", GscStruct())
        self.assertFalse(r.call(BZ_STATIONS_MOD, "bz_stations_open_for_player", p, "perks"))
        r.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_perks", "buy_perk:staminup")
        self.assertEqual(p.get_field("score"), 20000)

        # Stage clear blocks open & purchase
        p.set_field("revivetrigger", UNDEFINED)
        r.level.set_field("gauntlet_stage_clearing", True)
        self.assertFalse(r.call(BZ_STATIONS_MOD, "bz_stations_open_for_player", p, "arsenal"))
        r.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_arsenal", "buy_gear:portal_grenade")
        self.assertEqual(p.get_field("score"), 20000)

    def test_o3_pap_flags_pruned_when_weapon_dropped(self) -> None:
        rt = PapGscRuntime(MOD_ROOT, _make_enhanced_dvars())
        rt.level.set_field("script", VERRUCKT)
        rt.call(BZ_HOOKS_MOD, "bz_init")
        p = PapFakeEntity("Buyer", ent_num=0)
        p.set_field("score", 20000)
        p.set_field("sessionstate", "playing")
        rt.players.append(p)
        rt.call(BZ_HOOKS_MOD, "bz_on_player_spawned", p)
        p.give_weapon("colt")
        p.give_weapon("thompson", make_current=True)

        rt.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_pap", "buy_pap:single_pap")
        rt.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_pap", "buy_pap:double_pap")
        self.assertTrue(rt.call(BZ_PAP_MOD, "bz_pap_is_weapon_papped", p, "thompson"))

        p.weapons.discard("thompson")
        p.give_weapon("ray_gun", make_current=True)
        pruned = rt.call(BZ_PAP_MOD, "bz_pap_prune_unheld_weapons", p)
        self.assertGreaterEqual(pruned, 2)
        self.assertFalse(rt.call(BZ_PAP_MOD, "bz_pap_is_weapon_papped", p, "thompson"))
        self.assertFalse(rt.call(BZ_STATE_MOD, "bz_state_is_weapon_double_pap", p, "thompson"))

    def test_f4_s5_boomerang_uses_entity_ref_pierce_and_respects_walls(self) -> None:
        _, runtime, player = _setup_special_env()
        player.set_pos(0, 0, 0)
        player.set_angles(0, 0, 0)

        z_front = SpecialFakeEntity("front", ent_num=98, is_player=False)
        z_front.set_pos(120, 0, 0)
        z_front.set_field("health", 5000)
        z_wall = SpecialFakeEntity("behind_wall", ent_num=99, is_player=False)
        z_wall.set_pos(206, 0, 0)
        z_wall.set_field("health", 5000)
        runtime.ai_enemies.extend([z_front, z_wall])

        wall_x = 200.0

        def trace(start, end, include_entities, ignore):
            if float(start[0]) < wall_x <= float(end[0]):
                frac = (wall_x - float(start[0])) / (float(end[0]) - float(start[0]))
                return {"fraction": frac, "position": GscArray([wall_x, 0.0, float(start[2])])}
            return {"fraction": 1.0, "position": end}

        runtime.trace_handler = trace
        shot = runtime.call(BZ_SPECIAL_MOD, "bz_special_fire_blade_boomerang", player, "bz_blade_boomerang")
        res = runtime.call(
            BZ_SPECIAL_MOD,
            "bz_special_run_boomerang_flight",
            player,
            shot.get_field("blade"),
            shot.get_field("start_pos"),
            shot.get_field("apex"),
            shot.get_field("damage"),
            shot.get_field("max_pierce"),
        )
        self.assertEqual(res.get_field("pierce_count"), 1)
        self.assertEqual(len(z_front.damage_events), 1)
        self.assertEqual(len(z_wall.damage_events), 0)

    def test_a6_titan_releases_stale_favoriteenemy_when_ally_closer(self) -> None:
        f = TestFieldMedicAndTitanClasses()
        f.setUp()
        for ally in (f.p2, f.p3):
            ally.set_origin(400, 0, 64)
        f.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", f.p1, "bz_station_class", "buy_class:titan")
        z = ClassFakeEntity("zombie", 10, False, (260, 0, 64))
        f.gsc.zombies.append(z)
        self.assertEqual(f.gsc.call(BZ_CLASSES_MOD, "bz_titan_apply_aggro_bias", f.p1), 1)
        self.assertIs(z.get_field("favoriteenemy"), f.p1)

        f.p2.set_origin(260, 0, 64)
        self.assertEqual(f.gsc.call(BZ_CLASSES_MOD, "bz_titan_apply_aggro_bias", f.p1), 0)
        self.assertIs(z.get_field("favoriteenemy"), UNDEFINED)

    def test_a7_s6_linker_overlay_rolls_back_partial_failure(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage = root / "mods" / build_mod.MOD_NAME
            raw = root / "raw" / "ui"
            (stage / "ui").mkdir(parents=True)
            raw.mkdir(parents=True)
            (stage / "mod.csv").write_text("mod data")
            (stage / "ui" / "01.menu").write_text("patched first")
            (stage / "ui" / "02.menu").write_text("patched second")
            (raw / "01.menu").write_text("stock first")
            (raw / "02.menu").write_text("stock second")
            real_copy = build_mod.shutil.copyfile

            def fail_second(src, dst, *a, **kw):
                if Path(dst) == raw / "02.menu":
                    raise PermissionError("simulated copy failure")
                return real_copy(src, dst, *a, **kw)

            with patch.object(build_mod.shutil, "copyfile", side_effect=fail_second):
                with self.assertRaises(PermissionError):
                    build_mod.run_linker(root, root, root)

            self.assertEqual((raw / "01.menu").read_text(), "stock first")
            self.assertEqual((raw / "02.menu").read_text(), "stock second")

    def test_f10_flame_dot_refreshes_ticks_without_restarting_thread(self) -> None:
        dvars = _make_enhanced_dvars()
        rt = ElemStockGscRuntime(MOD_ROOT, dvars)
        p = ElemStockFakeEntity("Host", ent_num=0, is_player=True)
        z = ElemStockFakeEntity("Zombie", ent_num=10, is_player=False)
        z.set_field("health", 1000)
        rt.players.append(p)
        rt.ai_enemies.append(z)
        rt.call(BZ_ELEM_STOCK_MOD, "bz_elem_stock_register")
        rt.call(BZ_HOOKS_MOD, "bz_pre_init")
        rt.call(BZ_HOOKS_MOD, "bz_init")

        rt.sim_time_ms = 1000
        self.assertTrue(rt.call(BZ_ELEM_STOCK_MOD, "bz_flame_start_burn_dot", z, p, 10, 1000, False, False, False))
        threads_before = len([t for t in rt._threads if t[1] == "bz_flame_burn_dot_thread"])
        z.set_field("bz_flame_dot_ticks_left", 1)
        rt.sim_time_ms = 1600
        self.assertTrue(rt.call(BZ_ELEM_STOCK_MOD, "bz_flame_start_burn_dot", z, p, 10, 1000, False, False, False))
        threads_after = len([t for t in rt._threads if t[1] == "bz_flame_burn_dot_thread"])
        self.assertEqual(threads_before, 1)
        self.assertEqual(threads_after, 1)
        self.assertGreater(int(z.get_field("bz_flame_dot_ticks_left")), 1)

    def test_r2_s1_o8_laststand_patch_and_stage_clear_giveback_preserve_weapons(self) -> None:
        synthetic_laststand = (
            "PlayerLastStand()\n{\n\tif( player_all_players_in_laststand() )\n\t{\n\t\treturn;\n\t}\n}\n"
            "revive_trigger_think()\n{\n\tself endon ( \"disconnect\" );\n\tself endon ( \"zombified\" );\n"
            "\twhile ( 1 )\n\t{\n\t\twait ( 0.1 );\n\t\tself.revivetrigger setHintString( \"\" );\n\t}\n}\n"
            "revive_do_revive( playerBeingRevived, reviverGun )\n{\n\treviveTime = 3;\n}\n"
            "revive_success( reviver )\n{\n\tself reviveplayer();\n\tself laststand_giveback_player_weapons();\n}\n"
        )
        patched = build_mod.inject_laststand_hooks(synthetic_laststand.encode("latin1")).decode("latin1")
        self.assertNotIn("stop_revive_trigger", patched)
        self.assertIn("if ( !IsDefined( self.revivetrigger ) ) { return; }", patched)
        self.assertIn("maps\\_bz_perks::bz_perks_on_player_revived( self, reviver );", patched)

        # Downed player at Stage Clear gets weapons restored via laststand_giveback_player_weapons before snapshot.
        class GivebackRuntime(GauntletBzRuntime):
            def _exec_method(self, receiver, method, args, line):
                if method == "reviveplayer":
                    receiver.set_field("health", 100)
                    return UNDEFINED
                return super()._exec_method(receiver, method, args, line)

        dvars = _make_enhanced_dvars()
        rt = GivebackRuntime(MOD_ROOT, dvars)
        laststand_stub = (
            "player_is_in_laststand() { return IsDefined( self.revivetrigger ); }\n"
            "laststand_giveback_player_weapons() { self TakeWeapon( \"colt\" ); self GiveWeapon( \"bz_acid_sprayer\" ); }\n"
        )
        utility_stub = "setClientSysState( key, value, player ) { return; }"
        for mod_name, src in (("maps/_laststand", laststand_stub), ("maps/_utility", utility_stub)):
            rt._modules[mod_name] = BzGscParser(tokenize(src, filename=mod_name), filename=mod_name).parse_module()

        player = _make_player(rt, "7", "DownedCarrier")
        player.take_weapon("stielhandgranate")
        rt.call(BZ_HOOKS_MOD, "bz_init")
        rt.call(BZ_STATE_MOD, "bz_state_mark_weapon_double_pap", player, ACID)
        player.set_field("bz_single_pap_weapons", GscArray({ACID: True}))
        player.set_field("weaponinventory", GscArray(["colt", ACID]))
        player.set_field("revivetrigger", FakeEntity("trig", ent_num=51, is_player=False))

        # Mid-stage encode while downed still preserves Acid Sprayer from weaponInventory.
        self.assertEqual(rt.call(BRIDGE_MOD, "encode_weapons_record", player), "ac:2")

        # Stage Clear forced revive restores weapons before snapshot.
        rt.call(GAUNTLET_MODE_MOD, "protect_players_for_stage_clear")
        rt.call(BRIDGE_MOD, "save_all_players_bz_state", VERRUCKT)
        self.assertEqual(dvars.get(LEDGER), "g_7=ac:2")

    def test_r2_s3_unrestored_spectator_snapshot_before_apply_preserves_ledger(self) -> None:
        fixtures = TestGauntletWeaponCarryover()
        dvars = _make_enhanced_dvars()
        dvars.set(LEDGER, "g_7=ac:2")
        dvars.set("gauntlet_bz_perks", "g_7=su|-|-")
        dvars.set("gauntlet_disconnected_players", "g_7")
        runtime = fixtures.make_stage(dvars, VERRUCKT)
        player = fixtures.add_player(runtime, "7")
        player.set_field("sessionstate", "spectator")
        # Mid-stage checkpoint runs while reconnecting spectator is still waiting for first spawn.
        runtime.call(GAUNTLET_MODE_MOD, "snapshot_all_players_points", VERRUCKT)
        self.assertEqual(dvars.get(LEDGER), "g_7=ac:2")
        self.assertEqual(dvars.get("gauntlet_bz_perks"), "g_7=su|-|-")

    def test_r2_s5_boomerang_curved_return_clamped_by_side_wall(self) -> None:
        _, runtime, player = _setup_special_env()
        player.set_pos(0, 0, 0)
        player.set_angles(0, 0, 0)

        # Zombie sits behind a side wall at y = -25 (return curve bows toward -Y).
        z_side = SpecialFakeEntity("behind_side_wall", ent_num=97, is_player=False)
        z_side.set_pos(160, -55, 0)
        z_side.set_field("health", 5000)
        runtime.ai_enemies.append(z_side)

        wall_y = -25.0

        def side_wall_trace(start, end, include_entities, ignore):
            sy, ey = float(start[1]), float(end[1])
            if (sy > wall_y >= ey) or (sy < wall_y <= ey):
                frac = abs((wall_y - sy) / (ey - sy)) if ey != sy else 0.0
                return {"fraction": frac, "position": GscArray([float(start[0]), wall_y, float(start[2])])}
            return {"fraction": 1.0, "position": end}

        runtime.trace_handler = side_wall_trace
        shot = runtime.call(BZ_SPECIAL_MOD, "bz_special_fire_blade_boomerang", player, "bz_blade_boomerang")
        res = runtime.call(
            BZ_SPECIAL_MOD,
            "bz_special_run_boomerang_flight",
            player,
            shot.get_field("blade"),
            shot.get_field("start_pos"),
            shot.get_field("apex"),
            shot.get_field("damage"),
            shot.get_field("max_pierce"),
        )
        self.assertEqual(res.get_field("pierce_count"), 0)
        self.assertEqual(len(z_side.damage_events), 0)

    def test_r2_a7_s6_readonly_second_menu_still_rolls_back_first_and_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage = root / "mods" / build_mod.MOD_NAME
            raw = root / "raw" / "ui"
            zone_src = root / "zone_source"
            (stage / "ui").mkdir(parents=True)
            raw.mkdir(parents=True)
            zone_src.mkdir(parents=True)
            (stage / "mod.csv").write_text("mod csv")
            (stage / "ui" / "a.menu").write_text("patched a")
            (stage / "ui" / "b.menu").write_text("patched b")
            (raw / "a.menu").write_text("stock a")
            b_file = raw / "b.menu"
            b_file.write_text("stock b")
            b_file.chmod(0o444)
            try:
                with self.assertRaises(PermissionError):
                    build_mod.run_linker(root, root, root)
                self.assertEqual((raw / "a.menu").read_text(), "stock a")
                self.assertEqual(b_file.read_text(), "stock b")
                self.assertFalse((zone_src / "mod.csv").exists())
            finally:
                b_file.chmod(0o644)

        # A7/S6: a read-only STAGED menu must not make a writable stock destination read-only.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage = root / "mods" / build_mod.MOD_NAME
            raw = root / "raw" / "ui"
            zone_src = root / "zone_source"
            (stage / "ui").mkdir(parents=True)
            raw.mkdir(parents=True)
            zone_src.mkdir(parents=True)
            (stage / "mod.csv").write_text("mod csv")
            staged_ro = stage / "ui" / "ro.menu"
            staged_ro.write_text("patched ro")
            staged_ro.chmod(0o444)
            stock_rw = raw / "ro.menu"
            stock_rw.write_text("stock rw")
            try:
                with patch.object(
                    build_mod.subprocess,
                    "run",
                    return_value=type("R", (), {"returncode": 1, "stdout": "linker fail"})(),
                ):
                    with self.assertRaises(RuntimeError):
                        build_mod.run_linker(root, root, root)
                self.assertEqual(stock_rw.read_text(), "stock rw")
                self.assertFalse((zone_src / "mod.csv").exists())
            finally:
                staged_ro.chmod(0o644)

    def test_r2_a9_s7_f14_pap_overflow_drains_without_perks_and_survives_down(self) -> None:
        class ClampingPapRuntime(PapGscRuntime):
            def _exec_method(self, receiver, method, args, line):
                if method == "setweaponammostock" and isinstance(receiver, PapFakeEntity):
                    w = _waw_to_str(args[0]).lower()
                    amt = int(args[1])
                    cap = self.weapon_max_ammo.get(w, 200)
                    receiver.weapon_stock[w] = max(0, min(amt, cap))
                    return UNDEFINED
                return super()._exec_method(receiver, method, args, line)

        dvars = _make_enhanced_dvars()
        dvars.set("bz_perks_enabled", "0")
        rt = ClampingPapRuntime(MOD_ROOT, dvars)
        rt.weapon_max_ammo["thompson_upgraded"] = 200
        rt.level.set_field("script", "nazi_zombie_factory")
        rt.call(BZ_HOOKS_MOD, "bz_init")
        p = PapFakeEntity("PapOnly", ent_num=0)
        p.set_field("score", 20000)
        p.set_field("sessionstate", "playing")
        p.give_weapon("thompson_upgraded", make_current=True, stock=200)
        rt.players.append(p)
        rt.call(BZ_HOOKS_MOD, "bz_on_player_spawned", p)
        rt.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_pap", "buy_pap:double_pap")

        self.assertEqual(p.weapon_stock["thompson_upgraded"], 200)
        self.assertEqual(int(p.get_field("bz_overflow_reserve")["thompson_upgraded"]), 100)
        p.weapon_stock["thompson_upgraded"] = 140
        granted = rt.call(BZ_PAP_MOD, "bz_pap_drain_overflow_reserve", p)
        self.assertEqual(granted, 60)
        self.assertEqual(p.weapon_stock["thompson_upgraded"], 200)
        self.assertEqual(int(p.get_field("bz_overflow_reserve")["thompson_upgraded"]), 40)

        # F14: Double PaP + Double Ammo bank (400 overflow on a 200-cap gun) clamps down to
        # Double PaP's 100 on down rather than erasing it, while non-Double-PaP clears to 0.
        perk_rt = BzPerksRuntime(MOD_ROOT, _make_enhanced_dvars())
        perk_rt.weapon_max_ammo["thompson_upgraded"] = 200
        perk_rt.weapon_max_ammo["colt"] = 80
        perk_rt.level.set_field("script", "nazi_zombie_factory")
        p2 = PerksFakeEntity("ClampDown", ent_num=0)
        p2.set_field("score", 100000)
        p2.give_weapon("thompson_upgraded", make_current=True, stock=200)
        p2.give_weapon("colt", make_current=False, stock=80)
        perk_rt.players.append(p2)
        perk_rt.call(BZ_PERKS_MOD, "bz_perks_register")
        perk_rt.call(BZ_HOOKS_MOD, "bz_pre_init")
        perk_rt.call(BZ_HOOKS_MOD, "bz_init")
        perk_rt.call(BZ_STATE_MOD, "bz_state_mark_weapon_double_pap", p2, "thompson_upgraded")
        ov_in = GscArray()
        ov_in.set_item("thompson_upgraded", 400)
        ov_in.set_item("colt", 80)
        p2.set_field("bz_overflow_reserve", ov_in)
        perk_rt.call(BZ_HOOKS_MOD, "bz_on_player_downed", p2)
        ov = p2.get_field("bz_overflow_reserve")
        self.assertEqual(int(ov["thompson_upgraded"]), 100)
        self.assertNotIn("colt", ov._data)

    def test_r2_o6_s8_teddy_bear_refund_in_weapon_spawn_uses_bz_last_box_cost(self) -> None:
        # Matches real stock WaW _zombiemode_weapons.gsc: deduction in treasure_chest_think(),
        # teddy bear refund in treasure_chest_weapon_spawn( chest, player ).
        synthetic_weapons = (
            "treasure_chest_think()\n{\n"
            "\tif( user.score >= cost )\n\t{\n"
            "\t\tuser maps\\_zombiemode_score::minus_to_player_score( cost );\n"
            "\t}\n}\n"
            "treasure_chest_weapon_spawn( chest, player )\n{\n"
            "\tplayer maps\\_zombiemode_score::add_to_player_score( 950 );\n"
            "}\n"
            "weapon_give( weapon )\n{\n\tweapon_limit = 2;\n}\n"
        )
        patched = build_mod.inject_zombiemode_weapons_hooks(synthetic_weapons.encode("latin1")).decode("latin1")
        self.assertIn("user.bz_last_box_cost = maps\\_bz_hooks::bz_box_cost_modify( user, cost );", patched)
        self.assertIn("bz_refund = Int( player.bz_last_box_cost );", patched)
        self.assertIn("player.bz_last_box_cost = undefined;", patched)
        self.assertIn("player.score += bz_refund;", patched)
        self.assertIn("if ( !IsDefined( level.intermission ) || !level.intermission )", patched)
        self.assertIn("else", patched)
        self.assertIn("player maps\\_zombiemode_score::add_to_player_score( 950 );", patched)


if __name__ == "__main__":
    unittest.main()
