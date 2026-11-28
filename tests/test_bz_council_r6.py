"""Regression tests for Council Polish Pass 2 (feat/bz-council-polish-r6)."""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
for _p in (str(REPO_ROOT), str(SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_mod
from tests.gsc_runtime import FakeDvarStore, GscArray, GscStruct, UNDEFINED, _waw_to_str
from tests.test_bz_classes import BZ_CLASSES_MOD, ClassFakeEntity
from tests.test_bz_elem_stock import BZ_ELEM_STOCK_MOD, ElemStockFakeEntity, ElemStockGscRuntime
from tests.test_bz_gauntlet_bridge import (
    BZ_HOOKS_MOD,
    BZ_STATE_MOD,
    GAUNTLET_MODE_MOD,
    VERRUCKT,
    _make_enhanced_dvars,
)
from tests.test_bz_hooks_and_build import MOD_ROOT, MethodCallExpr
from tests.test_bz_pap import BZ_PAP_MOD
from tests.test_bz_perks import BZ_PERKS_MOD
from tests.test_bz_special_weapons import BZ_SPECIAL_MOD, SpecialFakeEntity, _setup_special_env
from tests.test_gauntlet_bz_integration import GAUNTLET_PERKS_MOD, GauntletBzRuntime, _make_player


class TestCouncilPass2Fixes(unittest.TestCase):
    def test_s1_portal_uses_stock_spawn_structs_honors_verruckt_side_and_skips_missing(self) -> None:
        # 1. Der Riese stock spawn structs (via common_scripts\utility::getstructarray)
        _, rt, player = _setup_special_env(map_name="nazi_zombie_factory")
        sp = GscStruct()
        sp.set_field("origin", GscArray([800.0, -300.0, 80.0]))
        sp.set_field("angles", GscArray([0.0, 180.0, 0.0]))
        rt.world_structs[("targetname", "initial_spawn_points")] = [sp]
        player.set_pos(350.0, 500.0, 25.0)
        rt.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_arsenal", "buy_gear:portal_grenade")
        portal = rt.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", player)
        self.assertIsNot(portal, UNDEFINED)
        player.set_pos(*portal.get_pos())
        self.assertEqual(rt.call(BZ_SPECIAL_MOD, "bz_special_portal_tick", portal, player), 1)
        pos = player.get_pos()
        self.assertGreater(pos[0], 700.0)
        self.assertLess(pos[1], -200.0)

        # 2. Verruckt split wings: player spawned on south side stays on south side
        _, v_rt, vp = _setup_special_env(map_name=VERRUCKT)
        north = GscStruct()
        north.set_field("origin", GscArray([1100.0, 200.0, 90.0]))
        south = GscStruct()
        south.set_field("origin", GscArray([-900.0, -400.0, 90.0]))
        v_rt.world_structs[("targetname", "initial_spawn_points")] = [north, south]
        vp.set_pos(-880.0, -390.0, 90.0)
        vp.set_field("bz_initial_spawn_origin", UNDEFINED)
        v_rt.call(BZ_HOOKS_MOD, "bz_on_player_spawned", vp)
        dest = v_rt.call(BZ_SPECIAL_MOD, "bz_special_resolve_spawn_destination", vp, 0)
        self.assertIsNot(dest, UNDEFINED)
        self.assertLess(float(dest.get_field("origin")[0]), -800.0)

        # 3. No valid spawn anywhere -> skip warp cleanly (never warp to hardcoded (36, 0, 0))
        _, empty_rt, ep = _setup_special_env(map_name="nazi_zombie_factory")
        ep.set_field("bz_initial_spawn_origin", UNDEFINED)
        ep.set_pos(400.0, 400.0, 10.0)
        empty_rt.call(BZ_HOOKS_MOD, "bz_on_menu_response", ep, "bz_station_arsenal", "buy_gear:portal_grenade")
        ep_portal = empty_rt.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", ep)
        ep.set_pos(*ep_portal.get_pos())
        before = ep.get_pos()
        self.assertEqual(empty_rt.call(BZ_SPECIAL_MOD, "bz_special_portal_tick", ep_portal, ep), 0)
        self.assertEqual(ep.get_pos(), before)

    def test_s3_o2_f4_portal_ignores_downed_players_for_activation_and_warp(self) -> None:
        _, rt, p1 = _setup_special_env(map_name="nazi_zombie_factory")
        sp = GscStruct()
        sp.set_field("origin", GscArray([800.0, -300.0, 80.0]))
        rt.world_structs[("targetname", "initial_spawn_points")] = [sp]
        p1.set_pos(200.0, 200.0, 0.0)
        rt.call(BZ_HOOKS_MOD, "bz_on_menu_response", p1, "bz_station_arsenal", "buy_gear:portal_grenade")

        # Downed player cannot activate portal or spend a charge
        p1.set_field("revivetrigger", GscStruct())
        self.assertIs(rt.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", p1), UNDEFINED)
        self.assertEqual(rt.call(BZ_STATE_MOD, "bz_state_get_portal_charges", p1), 2)

        # Standing player activates portal, downed teammate inside radius is NOT warped
        p1.set_field("revivetrigger", UNDEFINED)
        portal = rt.call(BZ_SPECIAL_MOD, "bz_special_try_activate_portal", p1)
        self.assertIsNot(portal, UNDEFINED)
        p2 = SpecialFakeEntity("DownedAlly", ent_num=1, is_player=True)
        p2.set_pos(*portal.get_pos())
        p2.set_field("revivetrigger", GscStruct())
        rt.players.append(p2)
        before_p2 = p2.get_pos()
        self.assertEqual(rt.call(BZ_SPECIAL_MOD, "bz_special_portal_tick", portal, p1), 0)
        self.assertEqual(p2.get_pos(), before_p2)

    def test_a1_s2_spectator_stock_perks_preserved_across_round_end_checkpoint(self) -> None:
        dvars = FakeDvarStore()
        dvars.set("gauntlet_enabled", "1")
        dvars.set("bz_enabled", "0")
        rt = GauntletBzRuntime(MOD_ROOT, dvars)
        rt.level.set_field("script", VERRUCKT)
        p = _make_player(rt, "7", "Reconnector")
        p.set_field("sessionstate", "spectator")
        p.set_field("health", 100)
        rt.call(GAUNTLET_PERKS_MOD, "record_player_perks", "7", "Reconnector", GscArray(["specialty_armorvest"]))

        # Defer restoration while spectating; checkpoint must NOT wipe saved stock perks
        rt.call(GAUNTLET_PERKS_MOD, "restore_player_perks", p, VERRUCKT)
        self.assertTrue(p.get_field("gauntlet_perks_deferred"))
        rt.call(GAUNTLET_PERKS_MOD, "snapshot_player_perks", p, VERRUCKT)
        saved = rt.call(GAUNTLET_PERKS_MOD, "get_recorded_player_perks", "7", "Reconnector")
        self.assertEqual(saved.to_list(), ["specialty_armorvest"])

        # Once spawned alive, perks restore; dying afterwards DOES clear saved perks
        p.set_field("sessionstate", "playing")
        p.set_field("gauntlet_perks_deferred", False)
        restored = rt.call(GAUNTLET_PERKS_MOD, "restore_player_perks", p, VERRUCKT)
        self.assertEqual(restored.to_list(), ["specialty_armorvest"])
        p.set_field("health", 0)
        rt.call(GAUNTLET_PERKS_MOD, "snapshot_player_perks", p, VERRUCKT)
        after_death = rt.call(GAUNTLET_PERKS_MOD, "get_recorded_player_perks", "7", "Reconnector")
        self.assertEqual(after_death.to_list(), [])

    def test_a2_stage_init_claims_player_before_wait_and_starts_late_join_watcher_first(self) -> None:
        dvars = _make_enhanced_dvars()
        rt = GauntletBzRuntime(MOD_ROOT, dvars)
        rt.level.set_field("script", VERRUCKT)
        p = _make_player(rt, "9", "InitGuard")
        p.set_field("initialized", True)
        rt.call(GAUNTLET_MODE_MOD, "apply_player_starting_points", p, 1, VERRUCKT, False)
        self.assertTrue(p.get_field("gauntlet_points_initializing"))
        self.assertTrue(p.get_field("gauntlet_points_applied"))

        src = (MOD_ROOT / "maps" / "_gauntlet_mode.gsc").read_text(encoding="latin1")
        self.assertLess(
            src.index("level thread watch_late_joining_players("),
            src.index("apply_connected_players_starting_points("),
        )

    def test_a3_s4_f3_daredevil_fall_and_stock_nonlethal_hits_do_not_spend_second_chance(self) -> None:
        rt = GauntletBzRuntime(MOD_ROOT, _make_enhanced_dvars())
        rt.level.set_field("script", "nazi_zombie_factory")
        rt.call(BZ_HOOKS_MOD, "bz_init")
        p = _make_player(rt, "7", "Daredevil")
        rt.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_class", "buy_class:daredevil")
        rt.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_perks", "buy_apex:second_chance")
        p.set_field("health", 10)
        pos = GscArray([0, 0, 0])
        rt.call_on(
            p, BZ_HOOKS_MOD, "bz_player_damage_override", UNDEFINED, UNDEFINED,
            15, 0, "MOD_FALLING", "none", pos, pos, "none", 0, 0,
        )
        self.assertTrue(p.get_field("bz_second_chance_ready"))

        # F3: Der Riese >75 HP self-grenade splash clamps to 75 in stock -> must NOT burn Second Chance
        p.set_field("health", 100)
        rt.call_on(
            p, BZ_HOOKS_MOD, "bz_player_damage_override", p, p,
            180, 0, "MOD_GRENADE_SPLASH", "stielhandgranate", pos, pos, "none", 0, 0,
        )
        self.assertTrue(p.get_field("bz_second_chance_ready"))

        # F3: repeat hit from player.ignoreAttacker must NOT burn Second Chance
        attacker = SpecialFakeEntity("z_repeat", ent_num=33, is_player=False)
        p.set_field("health", 30)
        p.set_field("ignoreattacker", attacker)
        rt.call_on(
            p, BZ_HOOKS_MOD, "bz_player_damage_override", attacker, attacker,
            50, 0, "MOD_MELEE", "none", pos, pos, "none", 0, 0,
        )
        self.assertTrue(p.get_field("bz_second_chance_ready"))

    def test_a4_field_medic_regen_tops_up_overflow_reserve_bank(self) -> None:
        from tests.test_bz_classes import TestFieldMedicAndTitanClasses

        f = TestFieldMedicAndTitanClasses()
        f.setUp()
        f.gsc.weapon_max_ammo["thompson"] = 200
        f.gsc.weapon_clip_sizes["thompson"] = 20
        orig_exec = f.gsc._exec_method

        def clamping_exec(receiver, method, args, line):
            if method == "setweaponammostock" and isinstance(receiver, ClassFakeEntity):
                w = _waw_to_str(args[0]).lower()
                cap = f.gsc.weapon_max_ammo.get(w, 200)
                receiver.ammo_stock[w] = max(0, min(int(args[1]), cap))
                return UNDEFINED
            return orig_exec(receiver, method, args, line)

        f.gsc._exec_method = clamping_exec
        f.p1.give_weapon("thompson", make_current=True)
        f.p1.ammo_stock["thompson"] = 200
        f.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", f.p1, "bz_station_class", "buy_class:medic")
        f.gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", f.p1, "bz_station_perks", "buy_apex:double_ammo")
        # Drain overflow bank to 0 while engine stock is at engine cap 200 (eff_max = 400)
        ov = GscArray()
        ov.set_item("thompson", 0)
        f.p1.set_field("bz_overflow_reserve", ov)
        added = f.gsc.call(BZ_CLASSES_MOD, "bz_medic_grant_reserve_ammo", f.p1, 1.0)
        self.assertEqual(added, 20)
        self.assertEqual(f.p1.ammo_stock["thompson"], 200)
        self.assertEqual(int(f.p1.get_field("bz_overflow_reserve")["thompson"]), 20)

    def test_a5_s5_boomerang_traces_from_eye_so_thin_wall_blocks_spawn_and_hit(self) -> None:
        _, rt, player = _setup_special_env()
        player.set_pos(0, 0, 0)
        player.set_angles(0, 0, 0)
        z = SpecialFakeEntity("behind_thin_wall", ent_num=40, is_player=False)
        z.set_pos(85, 0, 0)
        z.set_field("health", 5000)
        rt.ai_enemies.append(z)

        def thin_wall_trace(start, end, hit_characters, ignore):
            if (float(start[0]) < 16.0 < float(end[0])) or (float(end[0]) < 16.0 < float(start[0])):
                frac = (16.0 - float(start[0])) / (float(end[0]) - float(start[0]))
                hit = GscArray([float(start[i]) + frac * (float(end[i]) - float(start[i])) for i in range(3)])
                return {"fraction": frac, "position": hit}
            return {"fraction": 1.0, "position": end}

        rt.trace_handler = thin_wall_trace
        shot = rt.call(BZ_SPECIAL_MOD, "bz_special_fire_blade_boomerang", player, "bz_blade_boomerang")
        start = shot.get_field("start_pos")
        self.assertLess(float(start[0]), 16.0)
        res = rt.call(
            BZ_SPECIAL_MOD, "bz_special_run_boomerang_flight",
            player, shot.get_field("blade"), start, shot.get_field("apex"),
            shot.get_field("damage"), shot.get_field("max_pierce"),
        )
        self.assertEqual(res.get_field("pierce_count"), 0)
        self.assertEqual(len(z.damage_events), 0)

    def test_s6_native_pap_preserves_mule_kick_acquisition_order(self) -> None:
        rt = GauntletBzRuntime(MOD_ROOT, _make_enhanced_dvars())
        rt.level.set_field("script", "nazi_zombie_factory")
        zw = GscArray()
        th_entry = GscStruct()
        th_entry.set_field("upgrade_name", "thompson_upgraded")
        zw.set_item("thompson", th_entry)
        rt.level.set_field("zombie_weapons", zw)
        rt.call(BZ_HOOKS_MOD, "bz_init")
        p = _make_player(rt, "7", "MulePapper")
        p.set_field("score", 50000)
        p.take_weapon("stielhandgranate")
        rt.call(BZ_STATE_MOD, "bz_try_buy_perk", p, "mule_kick")
        for w in ("thompson", "stg44"):
            p.give_weapon(w, make_current=True)
            rt.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", p)
        # Order is [colt/zombie_colt, thompson, stg44]; upgrade slot #2 (thompson -> thompson_upgraded)
        rt.call(BZ_PAP_MOD, "bz_pap_apply_single_pap", p, "thompson")
        order = rt.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", p).to_list()
        self.assertEqual(order[1], "thompson_upgraded")
        self.assertEqual(order[2], "stg44")

    def test_f1_s7_rapid_real_hits_not_swallowed_and_scripted_echo_honors_instakill(self) -> None:
        rt = ElemStockGscRuntime(MOD_ROOT, _make_enhanced_dvars())
        rt.level.set_field("script", "nazi_zombie_factory")
        p = ElemStockFakeEntity("MG42", ent_num=0, is_player=True)
        p.set_field("score", 50000)
        p.give_weapon("zombie_mg42", make_current=True)
        z = ElemStockFakeEntity("TankZombie", ent_num=10, is_player=False)
        z.set_field("health", 5000)
        rt.players.append(p)
        rt.ai_enemies.append(z)
        rt.call(BZ_HOOKS_MOD, "bz_init")
        rt.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_perks", "buy_perk:ap")

        prev_calls: list[int] = []
        rt.level.set_field(
            "bz_prev_global_damage_func",
            rt.register_py_callback("prev_dmg", lambda *_a: (prev_calls.append(1), UNDEFINED)[1]),
        )

        # F1: two real bullet hits 50ms apart both invoke prev_cb and apply bonus damage
        z.set_field("damagetaken", 100)
        z.set_field("damageweapon", "zombie_mg42")
        rt.sim_time_ms = 1000
        rt.call_on(z, BZ_HOOKS_MOD, "bz_global_damage_wrapper", "MOD_RIFLE_BULLET", "torso_upper", GscArray([0, 0, 0]), p, False)
        rt.sim_time_ms = 1050
        rt.call_on(z, BZ_HOOKS_MOD, "bz_global_damage_wrapper", "MOD_RIFLE_BULLET", "torso_upper", GscArray([0, 0, 0]), p, False)
        self.assertEqual(len(prev_calls), 2)
        self.assertEqual(len(z.damage_events), 2)

        # S7: scripted MOD_UNKNOWN echo during Insta-Kill kills zombie without invoking prev_cb
        z2 = ElemStockFakeEntity("SplashVictim", ent_num=11, is_player=False)
        z2.set_field("health", 5000)
        z2.set_field("bz_in_damage_dispatch", True)
        z2.set_field("bz_damage_dispatch_time", 2000)
        zvars = GscArray()
        zvars.set_item("zombie_insta_kill", 1)
        rt.level.set_field("zombie_vars", zvars)
        rt.sim_time_ms = 2000
        prev_before = len(prev_calls)
        rt.call_on(z2, BZ_HOOKS_MOD, "bz_global_damage_wrapper", "MOD_UNKNOWN", "none", GscArray([0, 0, 0]), p, False)
        self.assertEqual(len(prev_calls), prev_before)
        self.assertEqual(int(z2.get_field("health")), 0)
        self.assertTrue(len(z2.damage_events) >= 1)

    def test_o1_f2_move_rate_recompute_preserves_stock_pre_entry_ignoreall(self) -> None:
        rt = ElemStockGscRuntime(MOD_ROOT, _make_enhanced_dvars())
        rt.level.set_field("script", "nazi_zombie_sumpf")
        z = ElemStockFakeEntity("WindowZombie", ent_num=12, is_player=False)
        z.set_field("health", 1000)
        z.set_field("ignoreall", True)
        z.set_field("bz_flame_dot_active", True)
        rt.ai_enemies.append(z)
        rt.call(BZ_HOOKS_MOD, "bz_init")

        # Flame / acid recompute must NOT clear stock pre-entry ignoreall=true
        rt.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", z)
        self.assertTrue(z.get_field("ignoreall"))

        # Stun then expiry restores prior ignoreall=true rather than forcing false
        rt.sim_time_ms = 1000
        z.set_field("bz_tesla_stun_until", 3000)
        rt.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", z)
        self.assertTrue(z.get_field("ignoreall"))
        rt.sim_time_ms = 4000
        rt.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", z)
        self.assertTrue(z.get_field("ignoreall"))

        # Active zombie (ignoreall=false before stun) DOES return to false on stun expiry
        z2 = ElemStockFakeEntity("ActiveZombie", ent_num=13, is_player=False)
        z2.set_field("health", 1000)
        z2.set_field("ignoreall", False)
        rt.sim_time_ms = 1000
        z2.set_field("bz_tesla_stun_until", 3000)
        rt.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", z2)
        self.assertTrue(z2.get_field("ignoreall"))
        rt.sim_time_ms = 4000
        rt.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", z2)
        self.assertFalse(z2.get_field("ignoreall"))

    def test_s8_f5_sapper_skips_monkey_bomb_blast_and_downed_round_refill(self) -> None:
        class StopAfterOne(Exception):
            pass

        class SingleThrowRt(GauntletBzRuntime):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.delivered = False
                self.thrown = SpecialFakeEntity("monkey", ent_num=77, is_player=False)

            def _eval_expr(self, expr, module, env):
                if isinstance(expr, MethodCallExpr) and expr.method_name == "waittill":
                    if self.delivered:
                        raise StopAfterOne
                    self.delivered = True
                    env[expr.args[1].name] = self.thrown
                    env[expr.args[2].name] = "zombie_cymbal_monkey"
                    return UNDEFINED
                return super()._eval_expr(expr, module, env)

        rt = SingleThrowRt(MOD_ROOT, _make_enhanced_dvars())
        rt.call(BZ_HOOKS_MOD, "bz_init")
        p = _make_player(rt, "7", "Sapper")
        p.set_field("score", 50000)
        rt.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_class", "buy_class:sapper")
        rt._threads.clear()
        with self.assertRaises(StopAfterOne):
            rt.call_on(p, BZ_CLASSES_MOD, "bz_sapper_grenade_watch")
        self.assertFalse(any(t[1] == "bz_sapper_track_thrown_grenade" for t in rt._threads))

        # F5: downed Sapper skips round-start refill (doesn't inflate reserve to 10 while clip is saved)
        p.set_field("revivetrigger", GscStruct())
        p.set_field("bz_sapper_grenade_reserve", 2)
        rt.call(BZ_CLASSES_MOD, "bz_classes_on_round_start", 5)
        self.assertEqual(int(p.get_field("bz_sapper_grenade_reserve")), 2)

    def test_s9_deploy_mod_rolls_back_mod_ff_if_iwd_replace_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "dist"
            appdata = root / "appdata"
            mod_dir = appdata / "mods" / build_mod.MOD_NAME
            dist.mkdir(parents=True)
            mod_dir.mkdir(parents=True)
            (dist / "mod.ff").write_bytes(b"new-ff")
            (dist / f"{build_mod.MOD_NAME}.iwd").write_bytes(b"new-iwd")
            (mod_dir / "mod.ff").write_bytes(b"old-ff")
            (mod_dir / f"{build_mod.MOD_NAME}.iwd").write_bytes(b"old-iwd")

            real_replace = Path.replace

            def fail_iwd_replace(self_path: Path, target: Path) -> Path:
                if target.name.endswith(".iwd") and self_path.name == f"{build_mod.MOD_NAME}.iwd":
                    raise PermissionError("simulated iwd lock")
                return real_replace(self_path, target)

            with patch.object(Path, "replace", fail_iwd_replace):
                with self.assertRaises(PermissionError):
                    build_mod.deploy_mod(dist, appdata)

            self.assertEqual((mod_dir / "mod.ff").read_bytes(), b"old-ff")
            self.assertEqual((mod_dir / f"{build_mod.MOD_NAME}.iwd").read_bytes(), b"old-iwd")

    def test_r2_s1_o4_f7_verruckt_prefers_stock_respawn_point_and_spawn_side(self) -> None:
        _, v_rt, vp = _setup_special_env(map_name=VERRUCKT)
        north = GscStruct()
        north.set_field("origin", GscArray([1100.0, 200.0, 90.0]))
        north.set_field("script_noteworthy", "north_spawn")
        south = GscStruct()
        south.set_field("origin", GscArray([-900.0, -400.0, 90.0]))
        south.set_field("script_noteworthy", "south_spawn")
        v_rt.world_structs[("targetname", "initial_spawn_points")] = [north, south]

        # Even without bz_initial_spawn_origin, stock player.respawn_point wins.
        vp.set_field("bz_initial_spawn_origin", UNDEFINED)
        vp.set_field("respawn_point", south)
        dest = v_rt.call(BZ_SPECIAL_MOD, "bz_special_resolve_spawn_destination", vp, 0)
        self.assertIsNot(dest, UNDEFINED)
        self.assertLess(float(dest.get_field("origin")[0]), -800.0)

        # Without respawn_point, stock player.spawn_side filters by script_noteworthy.
        vp.set_field("respawn_point", UNDEFINED)
        vp.set_field("spawn_side", "south_spawn")
        dest2 = v_rt.call(BZ_SPECIAL_MOD, "bz_special_resolve_spawn_destination", vp, 0)
        self.assertIsNot(dest2, UNDEFINED)
        self.assertLess(float(dest2.get_field("origin")[0]), -800.0)

        # A11: round 3 round_start must NOT capture mid-map position as bz_initial_spawn_origin.
        _, r3_rt, r3p = _setup_special_env(map_name="nazi_zombie_factory")
        r3p.set_field("bz_initial_spawn_origin", UNDEFINED)
        r3p.set_pos(400.0, 400.0, 10.0)
        r3_rt.call(BZ_SPECIAL_MOD, "bz_special_on_round_start", 3)
        self.assertIs(r3p.get_field("bz_initial_spawn_origin"), UNDEFINED)
        self.assertIs(r3_rt.call(BZ_SPECIAL_MOD, "bz_special_resolve_spawn_destination", r3p, 0), UNDEFINED)

    def test_r2_a1_s2_a6_init_wait_checkpoint_preserves_carried_points_and_perks(self) -> None:
        dvars = FakeDvarStore()
        dvars.set("gauntlet_enabled", "1")
        dvars.set("bz_enabled", "0")
        rt = GauntletBzRuntime(MOD_ROOT, dvars)
        rt.level.set_field("script", VERRUCKT)
        p = _make_player(rt, "7", "Waiter")
        p.set_field("score", 0)
        p.set_field("sessionstate", "spectator")
        p.set_field("initialized", False)
        # Seed carried points & stock perks and simulate apply_player_starting_points mid-wait.
        rt.call("maps/_gauntlet_state", "record_player_points", "7", "Waiter", 9000)
        rt.call(GAUNTLET_PERKS_MOD, "record_player_perks", "7", "Waiter", GscArray(["specialty_armorvest"]))
        p.set_field("gauntlet_points_initializing", True)
        p.set_field("gauntlet_perks_deferred", True)

        rt.call(GAUNTLET_MODE_MOD, "checkpoint_all_players_points")
        self.assertEqual(int(rt.call("maps/_gauntlet_state", "get_recorded_player_points", "7", "Waiter")), 9000)
        self.assertEqual(
            rt.call(GAUNTLET_PERKS_MOD, "get_recorded_player_perks", "7", "Waiter").to_list(),
            ["specialty_armorvest"],
        )

        rt.call(GAUNTLET_MODE_MOD, "snapshot_all_players_points", VERRUCKT)
        self.assertEqual(int(rt.call("maps/_gauntlet_state", "get_recorded_player_points", "7", "Waiter")), 9000)
        self.assertEqual(
            rt.call(GAUNTLET_PERKS_MOD, "get_recorded_player_perks", "7", "Waiter").to_list(),
            ["specialty_armorvest"],
        )

        # A1/S2/O5/F10: Full apply_player_starting_points flow on a spectating reconnector MUST
        # still launch restore_player_perks_when_alive() even though gauntlet_perks_deferred was pre-set.
        rt2 = GauntletBzRuntime(MOD_ROOT, dvars)
        rt2.level.set_field("script", VERRUCKT)
        p2 = _make_player(rt2, "8", "SpecWatcher")
        p2.set_field("sessionstate", "spectator")
        p2.set_field("initialized", True)
        rt2.call(GAUNTLET_PERKS_MOD, "record_player_perks", "8", "SpecWatcher", GscArray(["specialty_armorvest"]))
        rt2._threads.clear()
        rt2.call(GAUNTLET_MODE_MOD, "apply_player_starting_points", p2, 3, VERRUCKT, True)
        self.assertTrue(p2.get_field("gauntlet_perks_deferred"))
        self.assertTrue(p2.get_field("gauntlet_perks_restore_waiting"))
        self.assertIn("restore_player_perks_when_alive", [t[1] for t in rt2._threads])

    def test_r2_a7_classes_disabled_does_not_skip_second_chance_on_lethal_fall(self) -> None:
        dvars = _make_enhanced_dvars()
        # Isolated single-map subsystem gate check (ADR-0006 enforces classes when gauntlet_enabled=1).
        dvars.set("gauntlet_enabled", "0")
        rt = GauntletBzRuntime(MOD_ROOT, dvars)
        rt.level.set_field("script", "nazi_zombie_factory")
        rt.call(BZ_HOOKS_MOD, "bz_init")
        p = _make_player(rt, "7", "DisabledClass")
        p.set_field("score", 50000)
        rt.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_class", "buy_class:daredevil")
        rt.call(BZ_HOOKS_MOD, "bz_on_menu_response", p, "bz_station_perks", "buy_apex:second_chance")
        # Now disable classes gate (0 or non-1 value like 2) -> Second Chance MUST save lethal fall!
        dvars.set("bz_classes_enabled", "2")
        p.set_field("health", 10)
        pos = GscArray([0, 0, 0])
        rt.call_on(
            p, BZ_HOOKS_MOD, "bz_player_damage_override", UNDEFINED, UNDEFINED,
            15, 0, "MOD_FALLING", "none", pos, pos, "none", 0, 0,
        )
        self.assertFalse(p.get_field("bz_second_chance_ready"))

    def test_r2_a8_der_riese_native_console_handoff_preserves_mule_kick_slot(self) -> None:
        rt = GauntletBzRuntime(MOD_ROOT, _make_enhanced_dvars())
        rt.level.set_field("script", "nazi_zombie_factory")
        zw = GscArray()
        th_entry = GscStruct()
        th_entry.set_field("upgrade_name", "thompson_upgraded")
        zw.set_item("thompson", th_entry)
        rt.level.set_field("zombie_weapons", zw)
        rt.call(BZ_HOOKS_MOD, "bz_init")
        p = _make_player(rt, "7", "ConsoleMule")
        p.set_field("score", 50000)
        p.take_weapon("stielhandgranate")
        rt.call(BZ_STATE_MOD, "bz_try_buy_perk", p, "mule_kick")
        for w in ("thompson", "stg44"):
            p.give_weapon(w, make_current=True)
            rt.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", p)

        # Case A handoff returns false so stock Der Riese console runs rollers.
        handled = rt.call(BZ_PAP_MOD, "bz_pap_try_native_console_upgrade", UNDEFINED, p, "thompson", UNDEFINED, UNDEFINED)
        self.assertFalse(handled)
        # Stock takes thompson while inside rollers; player ALSO drops and reacquires slot 0 (colt)
        # while upgrading -> stg44 becomes older than reacquired colt, and thompson_upgraded returns
        # at its original slot without undoing the intervening swap (A8/S12).
        first_gun = p.primary_weapons[0]
        p.take_weapon("thompson")
        rt.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", p)
        p.take_weapon(first_gun)
        rt.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", p)
        p.give_weapon(first_gun, make_current=True)
        rt.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", p)
        p.give_weapon("thompson_upgraded", make_current=True)
        rt.call(BZ_PAP_MOD, "bz_pap_on_native_weapon_taken", p, "thompson_upgraded")
        order = rt.call(BZ_PERKS_MOD, "bz_perks_sync_weapon_order", p).to_list()
        self.assertEqual(order, ["stg44", "thompson_upgraded", first_gun])

    def test_r2_s7_s10_s11_instakill_flag_sapper_revive_refill_and_midstun_ignoreall(self) -> None:
        # S7: HUD-only zombie_powerup_insta_kill_on without zombie_insta_kill must NOT kill
        rt = ElemStockGscRuntime(MOD_ROOT, _make_enhanced_dvars())
        rt.level.set_field("script", "nazi_zombie_factory")
        p = ElemStockFakeEntity("Shooter", ent_num=0, is_player=True)
        z = ElemStockFakeEntity("Survivor", ent_num=14, is_player=False)
        z.set_field("health", 5000)
        z.set_field("bz_in_damage_dispatch", True)
        z.set_field("bz_damage_dispatch_time", 2000)
        rt.players.append(p)
        rt.ai_enemies.append(z)
        rt.call(BZ_HOOKS_MOD, "bz_init")
        zvars = GscArray()
        zvars.set_item("zombie_insta_kill", 0)
        zvars.set_item("zombie_powerup_insta_kill_on", 1)
        rt.level.set_field("zombie_vars", zvars)
        rt.sim_time_ms = 2000
        rt.call_on(z, BZ_HOOKS_MOD, "bz_global_damage_wrapper", "MOD_UNKNOWN", "none", GscArray([0, 0, 0]), p, False)
        self.assertEqual(int(z.get_field("health")), 5000)

        # S11/F6: Stock clears ignoreall while stunned -> overlapping recompute updates saved state
        z2 = ElemStockFakeEntity("RiserClearedMidStun", ent_num=15, is_player=False)
        z2.set_field("health", 1000)
        z2.set_field("ignoreall", True)
        rt.sim_time_ms = 1000
        z2.set_field("bz_tesla_stun_until", 5000)
        rt.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", z2)
        self.assertTrue(z2.get_field("ignoreall"))
        # Stock finishes entry and clears ignoreall while still stunned, then cryo re-hits!
        z2.set_field("ignoreall", False)
        rt.sim_time_ms = 2000
        rt.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", z2)
        self.assertTrue(z2.get_field("ignoreall"))
        # When stun expires, ignoreall MUST return to false (not stale true!)
        rt.sim_time_ms = 6000
        rt.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", z2)
        self.assertFalse(z2.get_field("ignoreall"))

        # S10: Sapper downed at round start receives pending grenade refill once revived
        crt = GauntletBzRuntime(MOD_ROOT, _make_enhanced_dvars())
        crt.call(BZ_HOOKS_MOD, "bz_init")
        sp = _make_player(crt, "8", "DownedSapper")
        sp.set_field("score", 50000)
        crt.call(BZ_HOOKS_MOD, "bz_on_menu_response", sp, "bz_station_class", "buy_class:sapper")
        sp.set_field("revivetrigger", GscStruct())
        sp.set_field("bz_sapper_grenade_reserve", 1)
        crt.call(BZ_CLASSES_MOD, "bz_classes_on_round_start", 6)
        self.assertEqual(int(sp.get_field("bz_sapper_pending_refill_round")), 6)
        self.assertEqual(int(sp.get_field("bz_sapper_grenade_reserve")), 1)
        # Revive completes (revivetrigger cleared) -> pending refill is delivered!
        sp.set_field("revivetrigger", UNDEFINED)
        crt.call(BZ_CLASSES_MOD, "bz_classes_on_player_revived", sp, sp)
        self.assertEqual(int(sp.get_field("bz_sapper_pending_refill_round")), 0)
        self.assertEqual(int(sp.get_field("bz_sapper_last_refill_round")), 6)
        self.assertEqual(int(crt.call(BZ_CLASSES_MOD, "bz_sapper_get_total_grenades", sp)), 10)


if __name__ == "__main__":
    unittest.main()
