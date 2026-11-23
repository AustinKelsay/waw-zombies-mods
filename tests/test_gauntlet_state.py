"""Offline contract tests for mod/maps/_gauntlet_state.gsc.

Exercises real WaW 1.7 GSC dvar persistence and per-player point ledger code
against an in-memory FakeDvarStore.
"""

from __future__ import annotations

from pathlib import Path
import unittest

from tests.gsc_runtime import FakeDvarStore, GscRuntime, GscStruct, UNDEFINED

MOD_ROOT = Path(__file__).resolve().parent.parent / "mod"
STATE_MOD = "maps\\_gauntlet_state"


class TestGauntletStatePersistence(unittest.TestCase):
    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.gsc = GscRuntime(MOD_ROOT, self.dvars)

    def test_init_fresh_run_and_round_trip(self) -> None:
        created = self.gsc.call(STATE_MOD, "init_fresh_run", "run_42")
        self.assertTrue(created.active)
        self.assertEqual(created.run_id, "run_42")
        self.assertEqual(created.cycle, 1)
        self.assertEqual(created.stage, 1)
        self.assertEqual(created.total_rounds, 0)
        self.assertFalse(created.pending_transition)

        loaded = self.gsc.call(STATE_MOD, "load_run_state")
        self.assertTrue(loaded.active)
        self.assertEqual(loaded.run_id, "run_42")
        self.assertEqual(loaded.cycle, 1)
        self.assertEqual(loaded.stage, 1)
        self.assertEqual(loaded.total_rounds, 0)
        self.assertFalse(loaded.pending_transition)

        # Verify exact dvar values written
        self.assertEqual(self.dvars.get("gauntlet_active"), "1")
        self.assertEqual(self.dvars.get("gauntlet_run_id"), "run_42")
        self.assertEqual(self.dvars.get("gauntlet_cycle"), "1")
        self.assertEqual(self.dvars.get("gauntlet_stage"), "1")
        self.assertEqual(self.dvars.get("gauntlet_total_rounds"), "0")
        self.assertEqual(self.dvars.get("gauntlet_pending_transition"), "0")

    def test_save_and_reload_mid_run_state(self) -> None:
        state = GscStruct()
        state.set_field("active", True)
        state.set_field("run_id", "coop_99")
        state.set_field("cycle", 3)
        state.set_field("stage", 4)
        state.set_field("total_rounds", 65)
        state.set_field("pending_transition", True)

        self.gsc.call(STATE_MOD, "save_run_state", state)
        loaded = self.gsc.call(STATE_MOD, "load_run_state")

        self.assertTrue(loaded.active)
        self.assertEqual(loaded.run_id, "coop_99")
        self.assertEqual(loaded.cycle, 3)
        self.assertEqual(loaded.stage, 4)
        self.assertEqual(loaded.total_rounds, 65)
        self.assertTrue(loaded.pending_transition)

    def test_advance_run_state_wraps_cycle_and_accumulates_rounds(self) -> None:
        s = self.gsc.call(STATE_MOD, "init_fresh_run", "solo_1")
        # Clear Stage 1..4 of Cycle 1 (10 rounds each -> 40 total rounds, wrap to Cycle 2 Stage 1)
        s = self.gsc.call(STATE_MOD, "advance_run_state", s, 10)
        self.assertEqual((s.cycle, s.stage, s.total_rounds, s.pending_transition), (1, 2, 10, True))
        s = self.gsc.call(STATE_MOD, "advance_run_state", s, 10)
        self.assertEqual((s.cycle, s.stage, s.total_rounds), (1, 3, 20))
        s = self.gsc.call(STATE_MOD, "advance_run_state", s, 10)
        self.assertEqual((s.cycle, s.stage, s.total_rounds), (1, 4, 30))
        s = self.gsc.call(STATE_MOD, "advance_run_state", s, 10)
        self.assertEqual((s.cycle, s.stage, s.total_rounds, s.pending_transition), (2, 1, 40, True))

        reloaded = self.gsc.call(STATE_MOD, "load_run_state")
        self.assertEqual(reloaded.cycle, 2)
        self.assertEqual(reloaded.stage, 1)
        self.assertEqual(reloaded.total_rounds, 40)
        self.assertTrue(reloaded.pending_transition)

    def test_per_player_ledger_returning_reconnecting_spectator_and_late_joiner(self) -> None:
        self.gsc.call(STATE_MOD, "init_fresh_run", "squad_run")

        # 1. Returning player with surplus above Cycle 2 Points Floor (5000)
        self.assertTrue(self.gsc.call(STATE_MOD, "record_player_points", 10001, "Dempsey", 14250))
        # 2. Returning player below floor
        self.assertTrue(self.gsc.call(STATE_MOD, "record_player_points", 10002, "Nikolai", 1800))
        # 3. Dead/spectating player snapshotted at 0 points
        self.assertTrue(self.gsc.call(STATE_MOD, "record_player_points", 10003, "Takeo", 0))
        # 4. Offline/LAN player with guid=0 -> keyed by sanitized player name fallback
        self.assertTrue(self.gsc.call(STATE_MOD, "record_player_points", 0, "[CLAN] Richtofen;=1", 9300))

        # Returning surplus preserved
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 10001, "Dempsey", 10),
            14250,
        )
        # Reconnecting player with same GUID even after display-name change
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 10001, "TankDempsey_New", 10),
            14250,
        )
        # Returning player below floor -> topped up to 5000
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 10002, "Nikolai", 10),
            5000,
        )
        # Dead/spectating player with 0 recorded points -> topped up to 5000
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 10003, "Takeo", 10),
            5000,
        )
        # Name-fallback player (guid=0) with delimiter characters in name
        self.assertEqual(
            self.gsc.call(
                STATE_MOD, "resolve_player_starting_points", 0, "[CLAN] Richtofen;=1", 10
            ),
            9300,
        )
        # Late joiner not in ledger -> receives Points Floor (Round 15 -> 7500)
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 99999, "LateFriend", 15),
            7500,
        )

        # Updating an existing player's points replaces rather than duplicating the entry
        self.assertTrue(self.gsc.call(STATE_MOD, "record_player_points", 10001, "Dempsey", 21000))
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 10001, "Dempsey", 15),
            21000,
        )
        ledger_raw = self.dvars.get("gauntlet_player_points")
        self.assertEqual(ledger_raw.count("g_10001="), 1)

    def test_corrupt_and_missing_dvar_resilience(self) -> None:
        # Completely empty dvar store -> clean inactive defaults
        empty = self.gsc.call(STATE_MOD, "load_run_state")
        self.assertFalse(empty.active)
        self.assertEqual(empty.run_id, "")
        self.assertEqual(empty.cycle, 1)
        self.assertEqual(empty.stage, 1)
        self.assertEqual(empty.total_rounds, 0)
        self.assertFalse(empty.pending_transition)

        # Corrupt / out-of-range Run state dvars
        self.dvars.set("gauntlet_active", "1")
        self.dvars.set("gauntlet_run_id", "corrupt_test")
        self.dvars.set("gauntlet_cycle", "-99")
        self.dvars.set("gauntlet_stage", "42")
        self.dvars.set("gauntlet_total_rounds", "-15")
        self.dvars.set("gauntlet_pending_transition", "bogus")

        recovered = self.gsc.call(STATE_MOD, "load_run_state")
        self.assertTrue(recovered.active)
        self.assertEqual(recovered.cycle, 1)
        self.assertEqual(recovered.stage, 4)
        self.assertEqual(recovered.total_rounds, 0)
        self.assertFalse(recovered.pending_transition)

        # Corrupt player points ledger entries do not crash and fall back safely
        self.dvars.set(
            "gauntlet_player_points",
            ";;broken_entry;=500;g_111=notanint;g_222=-300;g_333=8400;g_444=12abc;",
        )
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 111, "BadInt", 10), 5000
        )
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 222, "NegPts", 10), 5000
        )
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 444, "Mixed", 10), 5000
        )
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 333, "Valid", 10), 8400
        )

    def test_clear_run_state_wipes_all_run_dvars_without_touching_mode_gate(self) -> None:
        self.dvars.set("gauntlet_enabled", "1")
        self.gsc.call(STATE_MOD, "init_fresh_run", "wipe_test")
        self.gsc.call(STATE_MOD, "record_player_points", 5555, "Survivor", 18500)
        state = self.gsc.call(STATE_MOD, "load_run_state")
        self.gsc.call(STATE_MOD, "advance_run_state", state, 10)

        self.gsc.call(STATE_MOD, "clear_run_state")

        # Mode gate untouched
        self.assertEqual(self.dvars.get("gauntlet_enabled"), "1")

        # Every Run state dvar cleanly wiped
        self.assertEqual(self.dvars.get("gauntlet_active"), "0")
        self.assertEqual(self.dvars.get("gauntlet_run_id"), "")
        self.assertEqual(self.dvars.get("gauntlet_cycle"), "")
        self.assertEqual(self.dvars.get("gauntlet_stage"), "")
        self.assertEqual(self.dvars.get("gauntlet_total_rounds"), "")
        self.assertEqual(self.dvars.get("gauntlet_pending_transition"), "0")
        self.assertEqual(self.dvars.get("gauntlet_player_points"), "")

        cleared = self.gsc.call(STATE_MOD, "load_run_state")
        self.assertFalse(cleared.active)
        self.assertEqual(cleared.run_id, "")
        self.assertEqual(cleared.cycle, 1)
        self.assertEqual(cleared.stage, 1)
        self.assertEqual(cleared.total_rounds, 0)
        self.assertFalse(cleared.pending_transition)

        # Previous player's surplus is completely gone after clear
        self.assertIs(
            self.gsc.call(STATE_MOD, "get_recorded_player_points", 5555, "Survivor"), UNDEFINED
        )
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 5555, "Survivor", 1), 500
        )

    def test_identity_edge_cases_and_init_fresh_run_resets_stale_ledger(self) -> None:
        self.gsc.call(STATE_MOD, "init_fresh_run", "old_run")
        self.gsc.call(STATE_MOD, "record_player_points", 7777, "Veteran", 30000)

        # Starting a new Run with undefined/empty run_id defaults cleanly and clears old ledger
        fresh = self.gsc.call(STATE_MOD, "init_fresh_run", UNDEFINED)
        self.assertEqual(fresh.run_id, "run_1")
        self.assertIs(
            self.gsc.call(STATE_MOD, "get_recorded_player_points", 7777, "Veteran"), UNDEFINED
        )

        # Missing both GUID and name returns false without mutating ledger
        self.assertFalse(self.gsc.call(STATE_MOD, "record_player_points", 0, "", 5000))
        self.assertFalse(self.gsc.call(STATE_MOD, "record_player_points", UNDEFINED, UNDEFINED, 5000))
        self.assertEqual(self.dvars.get("gauntlet_player_points"), "")

        # String GUID and negative-1 fallback
        self.assertTrue(
            self.gsc.call(STATE_MOD, "record_player_points", "76561198012345678", "SteamUser", 11500)
        )
        self.assertEqual(
            self.gsc.call(
                STATE_MOD, "resolve_player_starting_points", "76561198012345678", "Renamed", 10
            ),
            11500,
        )
        self.assertTrue(self.gsc.call(STATE_MOD, "record_player_points", -1, "OfflineHost", 6400))
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", -1, "OfflineHost", 10),
            6400,
        )

        # Negative recorded points clamp to 0 and resolve to Points Floor
        self.assertTrue(self.gsc.call(STATE_MOD, "record_player_points", 8888, "Broke", -250))
        self.assertEqual(self.gsc.call(STATE_MOD, "get_recorded_player_points", 8888, "Broke"), 0)
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 8888, "Broke", 10), 5000
        )

        # Duplicate keys in a corrupt ledger deduplicate on next update
        self.dvars.set("gauntlet_player_points", "g_900=1000;g_900=2000;g_901=7000")
        self.assertTrue(self.gsc.call(STATE_MOD, "record_player_points", 900, "Dup", 9500))
        self.assertEqual(self.dvars.get("gauntlet_player_points").count("g_900="), 1)
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 900, "Dup", 10), 9500
        )
        self.assertEqual(
            self.gsc.call(STATE_MOD, "resolve_player_starting_points", 901, "Other", 10), 7000
        )

    def test_lobby_handoff_dvars_and_clear_run_state(self) -> None:
        self.dvars.set("gauntlet_enabled", "1")
        self.dvars.set("gauntlet_fresh_run", "1")
        self.gsc.call(STATE_MOD, "init_fresh_run", "coop_handoff")

        next_info = self.gsc.call("maps\\_gauntlet_rules", "get_stage_info", 2, 2)
        status = self.gsc.call(STATE_MOD, "set_lobby_handoff_dvars", next_info)
        self.assertEqual(status, "NEXT STAGE: C2 S2/4 - Verruckt (R10-R15)")
        self.assertEqual(self.dvars.get("gauntlet_pending_transition"), "1")
        self.assertEqual(self.dvars.get("gauntlet_next_map"), "nazi_zombie_asylum")
        self.assertEqual(self.dvars.get("gauntlet_next_display"), "Verruckt")
        self.assertEqual(
            self.dvars.get("gauntlet_lobby_status"),
            "NEXT STAGE: C2 S2/4 - Verruckt (R10-R15)",
        )

        # Mark disconnected and spectator flags to verify clear_run_state wipes them too
        self.gsc.call(STATE_MOD, "mark_player_disconnected", 2001, "Dropper")
        self.gsc.call(STATE_MOD, "mark_player_spectator", 2002, "Fallen")
        self.assertTrue(self.gsc.call(STATE_MOD, "is_player_marked_disconnected", 2001, "Dropper"))
        self.assertTrue(self.gsc.call(STATE_MOD, "is_player_marked_spectator", 2002, "Fallen"))

        self.gsc.call(STATE_MOD, "clear_run_state")

        # Mode gate untouched; all handoff, fresh-run, and roster-flag dvars cleared
        self.assertEqual(self.dvars.get("gauntlet_enabled"), "1")
        self.assertEqual(self.dvars.get("gauntlet_next_map"), "")
        self.assertEqual(self.dvars.get("gauntlet_next_display"), "")
        self.assertEqual(self.dvars.get("gauntlet_lobby_status"), "")
        self.assertEqual(self.dvars.get("gauntlet_fresh_run"), "0")
        self.assertEqual(self.dvars.get("gauntlet_disconnected_players"), "")
        self.assertEqual(self.dvars.get("gauntlet_spectators"), "")
        self.assertFalse(self.gsc.call(STATE_MOD, "is_player_marked_disconnected", 2001, "Dropper"))
        self.assertFalse(self.gsc.call(STATE_MOD, "is_player_marked_spectator", 2002, "Fallen"))

    def test_four_player_roster_resolution_roles_and_recovery(self) -> None:
        self.gsc.call(STATE_MOD, "init_fresh_run", "coop_4p")

        # 4-player squad snapshot on Stage Clear before Cycle 2 Stage 2 (start_round=10, floor=5000):
        # P1: returning with surplus (12400)
        self.assertTrue(self.gsc.call(STATE_MOD, "record_player_points", 30001, "Dempsey", 12400))
        # P2: returning below floor (1650)
        self.assertTrue(self.gsc.call(STATE_MOD, "record_player_points", 30002, "Nikolai", 1650))
        # P3: dead/spectating at Stage Clear with 0 points
        self.assertTrue(self.gsc.call(STATE_MOD, "record_player_points", 30003, "Takeo", 0))
        self.assertTrue(self.gsc.call(STATE_MOD, "mark_player_spectator", 30003, "Takeo"))
        # P4: disconnected mid-Stage with 8750 points (offline/LAN name fallback, guid=0)
        self.assertTrue(self.gsc.call(STATE_MOD, "record_player_points", 0, "Richtofen", 8750))
        self.assertTrue(self.gsc.call(STATE_MOD, "mark_player_disconnected", 0, "Richtofen"))

        # 1. Returning player with surplus
        e1 = self.gsc.call(STATE_MOD, "resolve_player_roster_entry", 30001, "Dempsey", 10, False)
        self.assertEqual(e1.player_key, "g_30001")
        self.assertEqual(e1.role, "returning")
        self.assertEqual(e1.points, 12400)
        self.assertEqual(e1.carried, 12400)
        self.assertEqual(e1.floor, 5000)

        # 2. Returning player below Points Floor -> topped up to 5000
        e2 = self.gsc.call(STATE_MOD, "resolve_player_roster_entry", 30002, "Nikolai", 10, False)
        self.assertEqual(e2.role, "returning")
        self.assertEqual(e2.points, 5000)
        self.assertEqual(e2.carried, 1650)
        self.assertEqual(e2.floor, 5000)

        # 3a. Spectator resolved via persisted spectator flag (spawning alive on next map: was_spectator=False)
        e3 = self.gsc.call(STATE_MOD, "resolve_player_roster_entry", 30003, "Takeo", 10, False)
        self.assertEqual(e3.role, "spectator")
        self.assertEqual(e3.points, 5000)
        self.assertEqual(e3.carried, 0)
        self.assertEqual(e3.floor, 5000)

        # 3b. Spectator resolved via explicit was_spectator=True parameter even without marker
        self.gsc.call(STATE_MOD, "clear_player_spectator", 30003, "Takeo")
        e3_explicit = self.gsc.call(STATE_MOD, "resolve_player_roster_entry", 30003, "Takeo", 10, True)
        self.assertEqual(e3_explicit.role, "spectator")
        self.assertEqual(e3_explicit.points, 5000)
        # And once cleared + alive on next Stage, classifies as returning
        e3_after = self.gsc.call(STATE_MOD, "resolve_player_roster_entry", 30003, "Takeo", 10, False)
        self.assertEqual(e3_after.role, "returning")

        # 4. Disconnected player reconnecting recovers saved 8750 points with role="reconnecting"
        e4 = self.gsc.call(STATE_MOD, "resolve_player_roster_entry", 0, "Richtofen", 10, False)
        self.assertEqual(e4.player_key, "n_richtofen")
        self.assertEqual(e4.role, "reconnecting")
        self.assertEqual(e4.points, 8750)
        self.assertEqual(e4.carried, 8750)
        self.assertEqual(e4.floor, 5000)

        # Clearing disconnect flag restores normal returning classification on next Stage
        self.gsc.call(STATE_MOD, "clear_player_disconnected", 0, "Richtofen")
        e4_after = self.gsc.call(STATE_MOD, "resolve_player_roster_entry", 0, "Richtofen", 10, False)
        self.assertEqual(e4_after.role, "returning")
        self.assertEqual(e4_after.points, 8750)

        # Mid-Stage reconnect with is_late_join=True and existing record classifies as reconnecting
        e1_mid = self.gsc.call(
            STATE_MOD, "resolve_player_roster_entry", 30001, "DempseyRenamed", 10, False, True
        )
        self.assertEqual(e1_mid.role, "reconnecting")
        self.assertEqual(e1_mid.points, 12400)

        # 5. Late joiner (unrecorded player) receives exact Stage Points Floor
        e5 = self.gsc.call(STATE_MOD, "resolve_player_roster_entry", 99999, "NewSquadmate", 10, False)
        self.assertEqual(e5.player_key, "g_99999")
        self.assertEqual(e5.role, "late_joiner")
        self.assertEqual(e5.points, 5000)
        self.assertIs(e5.carried, UNDEFINED)
        self.assertEqual(e5.floor, 5000)

        # Late joiner on Cycle 3 (Round 15) receives 7500 floor
        e5_c3 = self.gsc.call(STATE_MOD, "resolve_player_roster_entry", 99999, "NewSquadmate", 15, False, True)
        self.assertEqual(e5_c3.role, "late_joiner")
        self.assertEqual(e5_c3.points, 7500)

    def test_stale_run_reset_detection(self) -> None:
        # Inactive Run without force_fresh_run -> not a stale reset
        inactive = GscStruct()
        inactive.set_field("active", False)
        inactive.set_field("cycle", 1)
        inactive.set_field("stage", 1)
        inactive.set_field("pending_transition", False)
        self.assertFalse(
            self.gsc.call(STATE_MOD, "should_reset_stale_run", inactive, "nazi_zombie_prototype", False)
        )
        self.assertEqual(
            self.gsc.call(STATE_MOD, "get_stale_run_reset_reason", inactive, "nazi_zombie_prototype", False),
            "",
        )

        # Explicit gauntlet_fresh_run=1 always resets even if inactive or pending matches
        self.assertTrue(
            self.gsc.call(STATE_MOD, "should_reset_stale_run", inactive, "nazi_zombie_prototype", True)
        )
        self.assertEqual(
            self.gsc.call(STATE_MOD, "get_stale_run_reset_reason", inactive, "nazi_zombie_prototype", True),
            "fresh_run_requested",
        )

        # Active Run with pending_transition=True and matching map (case-insensitive) -> valid continuation
        valid_next = GscStruct()
        valid_next.set_field("active", True)
        valid_next.set_field("cycle", 2)
        valid_next.set_field("stage", 2)
        valid_next.set_field("pending_transition", True)
        self.assertFalse(
            self.gsc.call(STATE_MOD, "should_reset_stale_run", valid_next, "NAZI_ZOMBIE_ASYLUM", False)
        )
        # Same valid state with force_fresh_run=True -> resets
        self.assertTrue(
            self.gsc.call(STATE_MOD, "should_reset_stale_run", valid_next, "nazi_zombie_asylum", True)
        )
        self.assertEqual(
            self.gsc.call(STATE_MOD, "get_stale_run_reset_reason", valid_next, "nazi_zombie_asylum", True),
            "fresh_run_requested",
        )

        # Active Run with pending_transition=True but host picked wrong map -> stale_map_mismatch
        self.assertTrue(
            self.gsc.call(STATE_MOD, "should_reset_stale_run", valid_next, "nazi_zombie_prototype", False)
        )
        self.assertEqual(
            self.gsc.call(STATE_MOD, "get_stale_run_reset_reason", valid_next, "nazi_zombie_prototype", False),
            "stale_map_mismatch",
        )

        # Active Run with pending_transition=False (host disbanded / quit mid-Stage) -> resets
        stale_mid = GscStruct()
        stale_mid.set_field("active", True)
        stale_mid.set_field("cycle", 2)
        stale_mid.set_field("stage", 3)
        stale_mid.set_field("pending_transition", False)
        self.assertTrue(
            self.gsc.call(STATE_MOD, "should_reset_stale_run", stale_mid, "nazi_zombie_prototype", False)
        )
        self.assertEqual(
            self.gsc.call(STATE_MOD, "get_stale_run_reset_reason", stale_mid, "nazi_zombie_prototype", False),
            "stale_no_pending_transition",
        )
        # Even if host relaunched the same map after quitting mid-Stage without Stage Clear -> resets
        self.assertTrue(
            self.gsc.call(STATE_MOD, "should_reset_stale_run", stale_mid, "nazi_zombie_sumpf", False)
        )


if __name__ == "__main__":
    unittest.main()
