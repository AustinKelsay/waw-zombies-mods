"""Offline contracts for Elemental Weapon carryover in Enhanced Gauntlet."""

from __future__ import annotations

import unittest

from tests.gsc_runtime import FakeDvarStore, GscArray, UNDEFINED
from tests.test_bz_pap import PapFakeEntity, PapGscRuntime
from tests.test_gauntlet_bz_integration import (
    BRIDGE_MOD,
    BZ_HOOKS_MOD,
    BZ_STATE_MOD,
    GAUNTLET_MODE_MOD,
    MOD_ROOT,
    _make_enhanced_dvars,
)

NACHT = "nazi_zombie_prototype"
VERRUCKT = "nazi_zombie_asylum"
LEDGER = "gauntlet_bz_weapons"
ACID = "bz_acid_sprayer"
CRYO = "bz_cryo_cannon"
CROSSBOW = "bz_multi_crossbow"
BOOMERANG = "bz_blade_boomerang"
ELEMENTAL_LOADOUT = (ACID, BOOMERANG, CRYO, CROSSBOW)


class TestGauntletWeaponCarryover(unittest.TestCase):
    def make_stage(self, dvars: FakeDvarStore, map_name: str) -> PapGscRuntime:
        runtime = PapGscRuntime(MOD_ROOT, dvars)
        runtime.level.set_field("script", map_name)
        runtime.call(BZ_HOOKS_MOD, "bz_init")
        return runtime

    def add_player(self, runtime: PapGscRuntime, guid: str = "1") -> PapFakeEntity:
        player = PapFakeEntity(f"Player {guid}", ent_num=len(runtime.players))
        player.set_field("guid", guid)
        player.set_field("sessionstate", "playing")
        player.set_field("initialized", True)
        player.set_field("score", 50000)
        runtime.players.append(player)
        runtime.call(BZ_HOOKS_MOD, "bz_on_player_connect", player)
        return player

    def assert_restored_counts(
        self, runtime: PapGscRuntime, weapons: int, dpap: int, weapons_record: str | None = None
    ) -> None:
        events = [event for event in runtime.emitted_events if event.startswith("BZ_EVENT|GAUNTLET_BZ_RESTORED|")]
        self.assertEqual(len(events), 1)
        if weapons_record is not None:
            self.assertIn(f";weapons={weapons_record};", events[0])
        self.assertTrue(events[0].endswith(f";bz_weapons={weapons};bz_dpap={dpap}"), events[0])

    def test_encode_and_parse_all_four_primaries_with_all_tiers(self) -> None:
        runtime = self.make_stage(_make_enhanced_dvars(), NACHT)
        player = self.add_player(runtime)
        for weapon in (*ELEMENTAL_LOADOUT, "colt", "bz_unknown"):
            player.give_weapon(weapon)
        runtime.call(BZ_STATE_MOD, "bz_state_mark_weapon_double_pap", player, ACID)

        scripted = GscArray()
        scripted.set_item(CROSSBOW, True)
        player.set_field("bz_single_pap_weapons", scripted)
        station = GscArray()
        station.set_item(BOOMERANG, True)
        player.set_field("bz_pap_weapons", station)

        raw = runtime.call(BRIDGE_MOD, "encode_weapons_record", player)
        self.assertEqual(raw, "ac:2,bm:1,cr:0,xb:1")
        records = runtime.call(BRIDGE_MOD, "parse_weapons_record", raw).to_list()
        self.assertEqual(
            [(record.get_field("weapon_name"), record.get_field("pap_tier")) for record in records],
            [(ACID, 2), (BOOMERANG, 1), (CRYO, 0), (CROSSBOW, 1)],
        )

    def test_parser_ignores_malformed_tokens_and_keeps_first_valid_tier(self) -> None:
        runtime = self.make_stage(_make_enhanced_dvars(), NACHT)
        raw = "ac:3,ac:2,ac:0,zz:1,bm,bm::1,:bm:1,bm:1:,bm:01,bm:1:0,xb: 1,cr:-1,,cr:0"
        records = runtime.call(BRIDGE_MOD, "parse_weapons_record", raw).to_list()
        self.assertEqual(
            [(record.get_field("weapon_name"), record.get_field("pap_tier")) for record in records],
            [(ACID, 2), (CRYO, 0)],
        )
        for empty in ("", UNDEFINED):
            self.assertEqual(runtime.call(BRIDGE_MOD, "parse_weapons_record", empty).size, 0)

    def test_dead_and_spectating_players_lose_prior_weapon_entries(self) -> None:
        dvars = _make_enhanced_dvars()
        runtime = self.make_stage(dvars, NACHT)
        dead, spectator, unarmed = [self.add_player(runtime, str(guid)) for guid in (1, 2, 3)]
        for player in (dead, spectator):
            player.give_weapon(ACID)
        unarmed.give_weapon("colt")
        runtime.call(BRIDGE_MOD, "save_all_players_bz_state", NACHT)
        self.assertEqual(dvars.get(LEDGER), "g_1=ac:0;g_2=ac:0")

        dead.set_field("health", 0)
        spectator.set_field("sessionstate", "spectator")
        for player in (dead, spectator, unarmed):
            self.assertEqual(runtime.call(BRIDGE_MOD, "encode_weapons_record", player), "")
        runtime.call(BRIDGE_MOD, "save_all_players_bz_state", NACHT)
        self.assertEqual(dvars.get(LEDGER), "")

    def test_four_player_saves_fit_and_can_be_cleared(self) -> None:
        dvars = _make_enhanced_dvars()
        runtime = self.make_stage(dvars, NACHT)
        for index in range(4):
            player = self.add_player(runtime, f"7656119826385510{index}")
            for weapon in ELEMENTAL_LOADOUT:
                player.give_weapon(weapon)

        runtime.call(BRIDGE_MOD, "save_all_players_bz_state", NACHT)
        raw = dvars.get(LEDGER)
        self.assertEqual(len(raw.split(";")), 4)
        self.assertLess(len(raw.encode("ascii")), 200)
        self.assertIn("g_76561198263855103=ac:0,bm:0,cr:0,xb:0", raw)
        runtime.call(BRIDGE_MOD, "clear_bz_gauntlet_dvars")
        self.assertEqual(dvars.get(LEDGER), "")

    def test_verruckt_round_trip_preserves_tiers_and_restocks_double_pap(self) -> None:
        for double_ammo, acid_stock in ((False, 180), (True, 360)):
            with self.subTest(double_ammo=double_ammo):
                dvars = _make_enhanced_dvars()
                source = self.make_stage(dvars, NACHT)
                player = self.add_player(source)
                for weapon in (ACID, CRYO):
                    player.give_weapon(weapon)
                source.call(BZ_STATE_MOD, "bz_state_mark_weapon_double_pap", player, ACID)
                if double_ammo:
                    result = source.call(BZ_STATE_MOD, "bz_try_buy_apex", player, "double_ammo")
                    self.assertTrue(result.get_field("ok"))
                source.call(GAUNTLET_MODE_MOD, "snapshot_all_players_points", NACHT)
                self.assertEqual(dvars.get(LEDGER), "g_1=ac:2,cr:0")
                self.assertTrue(
                    any(
                        event.endswith(";weapons=ac:2,cr:0;bz_weapons=2;bz_dpap=1")
                        for event in source.emitted_events
                    ),
                    source.emitted_events,
                )

                destination = self.make_stage(dvars, VERRUCKT)
                returning = self.add_player(destination)
                returning.give_weapon("zombie_colt", make_current=True)
                destination.call(GAUNTLET_MODE_MOD, "apply_connected_players_starting_points", 11, VERRUCKT)
                self.assertEqual(returning.weapons, {ACID, CRYO})
                self.assertEqual(returning.taken_weapons, ["zombie_colt"])
                self.assertCountEqual(returning.max_ammo_calls, [ACID, CRYO])
                self.assertEqual(returning.weapon_stock[ACID], acid_stock)
                self.assertEqual(returning.weapon_stock[CRYO], 192 if double_ammo else 96)
                self.assertTrue(returning.get_field("bz_single_pap_weapons")[ACID])
                self.assertTrue(returning.get_field("bz_pap_weapons")[ACID])
                self.assertEqual(destination.call(BRIDGE_MOD, "encode_weapons_record", returning), "ac:2,cr:0")
                self.assert_restored_counts(destination, 2, 1, "ac:2,cr:0")

    def test_mule_kick_tiers_set_restore_cap_and_telemetry_counts_applied_weapons(self) -> None:
        for perks, expected in (
            ("", {ACID, BOOMERANG}),
            ("g_1=mk|-|-", {ACID, BOOMERANG, CRYO}),
            ("g_1=mk|mk|-", set(ELEMENTAL_LOADOUT)),
        ):
            with self.subTest(perks=perks):
                dvars = _make_enhanced_dvars()
                dvars.set("gauntlet_bz_perks", perks)
                dvars.set(LEDGER, "g_1=ac:2,bm:1,cr:0,xb:2")
                runtime = self.make_stage(dvars, VERRUCKT)
                player = self.add_player(runtime)
                player.give_weapon("colt", make_current=True)
                runtime.call(BRIDGE_MOD, "restore_player_bz_state", player, VERRUCKT)
                self.assertEqual(runtime.call(BZ_HOOKS_MOD, "bz_get_max_primary_weapons", player), len(expected))
                self.assertEqual(player.weapons, expected)
                self.assertTrue(player.get_field("bz_single_pap_weapons")[BOOMERANG])
                self.assertTrue(player.get_field("bz_pap_weapons")[BOOMERANG])
                self.assertFalse(runtime.call(BZ_STATE_MOD, "bz_state_is_weapon_double_pap", player, BOOMERANG))
                self.assert_restored_counts(runtime, len(expected), 2 if CROSSBOW in expected else 1)

    def test_restore_refreshes_pap_hud_and_station_for_held_weapon(self) -> None:
        dvars = _make_enhanced_dvars()
        dvars.set(LEDGER, "g_1=ac:2,cr:0")
        runtime = self.make_stage(dvars, VERRUCKT)
        player = self.add_player(runtime)
        player.give_weapon(ACID, make_current=True)
        runtime.call(BRIDGE_MOD, "restore_player_bz_state", player, VERRUCKT)

        self.assertEqual(player.get_field("bz_pap_hud_text"), "PAP II")
        self.assertEqual(player.client_dvars["ui_bz_pap_single_pap"], "UPGRADED")
        self.assertEqual(player.client_dvars["ui_bz_pap_double_pap"], "MAXED (II)")
        self.assert_restored_counts(runtime, 2, 1)

    def test_restore_honors_feature_and_player_gates(self) -> None:
        for gate, player_state, expected in (
            ("bz_elements_enabled", "playing", set()),
            ("bz_pap_enabled", "playing", {ACID, CRYO}),
            (None, "dead", set()),
            (None, "spectator", set()),
        ):
            with self.subTest(gate=gate, player_state=player_state):
                dvars = _make_enhanced_dvars()
                dvars.set(LEDGER, "g_1=ac:2,cr:0")
                if gate:
                    dvars.set(gate, "0")
                runtime = self.make_stage(dvars, VERRUCKT)
                player = self.add_player(runtime)
                if player_state == "dead":
                    player.set_field("health", 0)
                else:
                    player.set_field("sessionstate", player_state)
                restored_ok = runtime.call(BRIDGE_MOD, "restore_player_bz_state", player, VERRUCKT)
                self.assertEqual(player.weapons, expected)
                self.assertFalse(runtime.call(BZ_STATE_MOD, "bz_state_is_weapon_double_pap", player, ACID))
                if player_state in ("dead", "spectator"):
                    # Dead/spectating players defer alive-only restore until live spawn
                    # so carried perks & weapons are never permanently skipped.
                    self.assertFalse(restored_ok)
                    self.assertTrue(player.get_field("gauntlet_bz_restore_pending"))
                    self.assertNotEqual(player.get_field("gauntlet_bz_restored"), True)
                else:
                    if expected:
                        self.assertEqual(player.weapon_stock[ACID], 120)
                        self.assertEqual(runtime.call(BRIDGE_MOD, "encode_weapons_record", player), "ac:0,cr:0")
                    self.assert_restored_counts(runtime, len(expected), 0)

    def test_save_gates_leave_classic_state_alone_and_clear_disabled_element_entry(self) -> None:
        dvars = _make_enhanced_dvars()
        runtime = self.make_stage(dvars, NACHT)
        self.add_player(runtime).give_weapon(ACID)
        runtime.call(BRIDGE_MOD, "save_all_players_bz_state", NACHT)
        self.assertEqual(dvars.get(LEDGER), "g_1=ac:0")

        dvars.set("bz_enabled", "0")
        runtime.call(BRIDGE_MOD, "save_all_players_bz_state", NACHT)
        self.assertEqual(dvars.get(LEDGER), "g_1=ac:0")

        dvars.set("bz_enabled", "1")
        dvars.set("bz_elements_enabled", "0")
        runtime.call(BRIDGE_MOD, "save_all_players_bz_state", NACHT)
        self.assertEqual(dvars.get(LEDGER), "")
        self.assertTrue(runtime.emitted_events[-1].endswith(";weapons=none;bz_weapons=0;bz_dpap=0"))

    def test_disconnect_before_restore_preserves_ledgers_and_after_restore_checkpoints(self) -> None:
        class DisconnectRuntime(PapGscRuntime):
            def _exec_method(self, receiver, method, args, line):
                if method == "waittill" and args == ["disconnect"]:
                    self._current_self = UNDEFINED
                    return UNDEFINED
                return super()._exec_method(receiver, method, args, line)

        dvars = _make_enhanced_dvars()
        dvars.set("gauntlet_bz_perm", "g_7=titan|wc,pwc|war_club")
        dvars.set("gauntlet_bz_perks", "g_7=su,mk|-|-")
        dvars.set(LEDGER, "g_7=ac:2,cr:0")

        runtime = DisconnectRuntime(MOD_ROOT, dvars)
        runtime.level.set_field("script", VERRUCKT)
        runtime.call(BZ_HOOKS_MOD, "bz_init")

        guest = PapFakeEntity("Guest", ent_num=1)
        guest.set_field("guid", "7")
        guest.set_field("sessionstate", "spectator")
        guest.set_field("score", 0)
        runtime.players.append(guest)

        # Disconnect while still loading before restore must preserve all BZ ledgers.
        runtime.call_on(guest, GAUNTLET_MODE_MOD, "watch_player_disconnect")
        self.assertEqual(dvars.get("gauntlet_bz_perm"), "g_7=titan|wc,pwc|war_club")
        self.assertEqual(dvars.get("gauntlet_bz_perks"), "g_7=su,mk|-|-")
        self.assertEqual(dvars.get(LEDGER), "g_7=ac:2,cr:0")

        # After spawning and restoring, a subsequent disconnect checkpoints current state.
        guest.set_field("sessionstate", "playing")
        guest.set_field("initialized", True)
        guest.give_weapon("colt", make_current=True)
        runtime.call(BRIDGE_MOD, "restore_player_bz_state", guest, VERRUCKT)
        self.assertTrue(guest.get_field("gauntlet_bz_restored"))
        guest.weapons.discard(CRYO)
        runtime.call_on(guest, GAUNTLET_MODE_MOD, "watch_player_disconnect")
        self.assertEqual(dvars.get(LEDGER), "g_7=ac:2")
