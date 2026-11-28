"""Offline contract suite for P3C-T1 (#113): Scripted Squad Companions tracer bullet.

Executes the real WaW 1.7 `mod/maps/_bz_companions.gsc` (plus the Base Zombies hooks
and Arsenal & Squad Station menu dispatch) through the shared BzGscRuntime harness:
  1. Feature Gate isolation (Classic Mode, Zombie Gauntlet, bz_companions_enabled=0).
  2. Hiring through the Arsenal menu response: points charged, non-solid per-map
     stock character model, SetModel/Attach before SetContents(0) + NotSolid().
  3. Squad cap: active players + active Companions <= 4.
  4. Breadcrumb follow and teleport / stranded warp catch-up.
  5. Combat: nearest visible zombie, 4-argument MagicBullet credited to the owner,
     fire interval, range and line-of-sight limits.
  6. Teardown on owner release and end_game.
"""

from __future__ import annotations

from pathlib import Path
import unittest

from tests.gsc_runtime import UNDEFINED, FakeDvarStore
from tests.test_bz_hooks_and_build import BZ_HOOKS_MOD
from tests.test_bz_special_weapons import SpecialFakeEntity, SpecialWeaponsGscRuntime

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_ROOT = REPO_ROOT / "mod"
BZ_COMPANIONS_MOD = "maps\\_bz_companions"
BZ_COMPANIONS_PATH = MOD_ROOT / "maps" / "_bz_companions.gsc"
ARSENAL = "bz_station_arsenal"
HIRE = "buy_companion:hire"


def _setup(
    map_name: str = "nazi_zombie_factory",
    *,
    bz_enabled: str = "1",
    companions_enabled: str = "1",
    gauntlet_enabled: str = "0",
    player_count: int = 1,
) -> tuple[FakeDvarStore, SpecialWeaponsGscRuntime, list[SpecialFakeEntity]]:
    dvars = FakeDvarStore()
    dvars.set("gauntlet_enabled", gauntlet_enabled)
    dvars.set("bz_enabled", bz_enabled)
    dvars.set("bz_perks_enabled", "0")
    dvars.set("bz_classes_enabled", "0")
    dvars.set("bz_pap_enabled", "0")
    dvars.set("bz_elements_enabled", "0")
    dvars.set("bz_companions_enabled", companions_enabled)

    gsc = SpecialWeaponsGscRuntime(MOD_ROOT, dvars)
    gsc.level.set_field("script", map_name)
    gsc.level.set_field("round_number", 1)
    players = []
    for i in range(player_count):
        p = SpecialFakeEntity(f"Player{i + 1}", ent_num=i, is_player=True)
        p.set_field("score", 50000)
        p.set_pos(100.0 * i, 0.0, 0.0)
        p.set_angles(0.0, 0.0, 0.0)
        gsc.players.append(p)
        players.append(p)

    gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
    gsc.call(BZ_HOOKS_MOD, "bz_init")
    return dvars, gsc, players


def _hire(gsc: SpecialWeaponsGscRuntime, player: SpecialFakeEntity) -> list[str]:
    before = len(gsc.emitted_events)
    gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, ARSENAL, HIRE)
    return gsc.emitted_events[before:]


def _companions(gsc: SpecialWeaponsGscRuntime) -> list:
    comps = gsc.level.get_field("bz_companions")
    return [comps[i] for i in range(comps.size)]


def _script_models(gsc: SpecialWeaponsGscRuntime) -> list:
    # Station kiosks are script_models too; Companions are the stock character bodies.
    return [
        e
        for e in gsc.spawned_entities
        if e.classname == "script_model" and not e.deleted and str(e.get_field("model")).startswith("char_")
    ]


def _purchase_status(events: list[str]) -> str:
    for ev in events:
        if "STATION_PURCHASE" in ev and "category=companion" in ev:
            return ev.split("status=", 1)[1].split(";", 1)[0]
    return ""


def _zombie(name: str, x: float, y: float, z: float = 0.0, health: int = 500) -> SpecialFakeEntity:
    zomb = SpecialFakeEntity(name, ent_num=50, is_player=False)
    zomb.set_pos(x, y, z)
    zomb.set_field("health", health)
    return zomb


class TestCompanionGateAndHiring(unittest.TestCase):
    def test_gate_closed_refuses_hire_with_zero_side_effects(self) -> None:
        cases = (
            {"bz_enabled": "0", "companions_enabled": "1", "gauntlet_enabled": "0"},  # Classic Mode
            {"bz_enabled": "1", "companions_enabled": "0", "gauntlet_enabled": "0"},  # gate off
            {"bz_enabled": "1", "companions_enabled": "1", "gauntlet_enabled": "1"},  # Zombie Gauntlet
        )
        for case in cases:
            with self.subTest(**case):
                _, gsc, (player,) = _setup(**case)
                events = _hire(gsc, player)
                self.assertEqual(_script_models(gsc), [])
                self.assertEqual(player.get_field("score"), 50000)
                self.assertFalse(any("COMPANION_" in ev for ev in gsc.emitted_events))
                if case["bz_enabled"] == "1":
                    self.assertEqual(_purchase_status(events), "gate_disabled")

    def test_hire_via_arsenal_charges_points_and_spawns_non_solid_stock_model(self) -> None:
        _, gsc, (player,) = _setup("nazi_zombie_factory")
        events = _hire(gsc, player)

        self.assertEqual(_purchase_status(events), "ok")
        self.assertEqual(player.get_field("score"), 48000)
        (comp,) = _companions(gsc)
        self.assertEqual(_script_models(gsc), [comp])
        # Solo player is character 0, so the first Companion is the next Ultimis hero.
        self.assertEqual(comp.get_field("model"), "char_rus_guard_chernova_zomb")
        self.assertEqual(comp.contents, 0)
        self.assertTrue(comp.not_solid)
        log = comp.method_log
        self.assertLess(log.index("setmodel"), log.index("setcontents"))
        self.assertTrue(any(ev.startswith("BZ_EVENT|COMPANION_SPAWN|") and "character=Nikolai" in ev for ev in events))
        self.assertIn("Squad 2/4", player.client_dvars["ui_bz_companion_status"])
        self.assertIn("Hired Nikolai", gsc.dvars.get("ui_bz_feedback") or player.client_dvars.get("ui_bz_feedback", ""))

    def test_insufficient_points_refused_without_spawning(self) -> None:
        _, gsc, (player,) = _setup()
        player.set_field("score", 1999)
        events = _hire(gsc, player)
        self.assertEqual(_purchase_status(events), "insufficient_points")
        self.assertEqual(player.get_field("score"), 1999)
        self.assertEqual(_script_models(gsc), [])

    def test_per_map_character_models_attach_parts_before_clearing_contents(self) -> None:
        expected = {
            "nazi_zombie_factory": [
                ("char_rus_guard_chernova_zomb", []),
                ("char_jap_impinf_officer_body_zomb", ["char_jap_impinf_officer_head", "char_jap_impinf_officer_hat_zomb"]),
                ("char_ger_ansel_body_zomb", ["char_ger_ansel_head_zomb", "char_ger_waffen_officercap1_zomb"]),
            ],
            "nazi_zombie_sumpf": [
                ("char_rus_guard_chernova_zomb", []),
                ("char_jap_impinf_officer_body_zomb", ["char_jap_impinf_officer_head", "char_jap_impinf_officer_hat_zomb"]),
                ("char_ger_ansel_body_zomb", ["char_ger_ansel_head_zomb", "char_ger_waffen_officercap1_zomb"]),
            ],
            "nazi_zombie_prototype": [
                ("char_usa_marine_player_body2_1", ["char_usa_marine_head2_2", "char_usa_raider_helm2", "char_usa_raider_gear3"]),
                ("char_usa_marine_player_body1_1", ["char_usa_marine_head3_3", "char_usa_raider_helm2", "char_usa_raider_gear2"]),
                ("char_usa_marine_player_body2_1", ["char_usa_marine_head4_4", "char_usa_raider_helm1", "char_usa_raider_gear3"]),
            ],
            "nazi_zombie_asylum": [
                ("char_usa_marine_player_body2_1", ["char_usa_marine_head2_2", "char_usa_raider_helm2", "char_usa_raider_gear3"]),
                ("char_usa_marine_player_body1_1", ["char_usa_marine_head3_3", "char_usa_raider_helm2", "char_usa_raider_gear2"]),
                ("char_usa_marine_player_body2_1", ["char_usa_marine_head4_4", "char_usa_raider_helm1", "char_usa_raider_gear3"]),
            ],
        }
        for map_name, models in expected.items():
            with self.subTest(map=map_name):
                _, gsc, (player,) = _setup(map_name)
                for _ in range(3):
                    _hire(gsc, player)
                comps = _companions(gsc)
                self.assertEqual(len(comps), 3)
                for comp, (body, parts) in zip(comps, models):
                    self.assertEqual(comp.get_field("model"), body)
                    self.assertEqual([a[0] for a in comp.__dict__.get("attachments", [])], parts)
                    if parts:
                        last_attach = max(i for i, m in enumerate(comp.method_log) if m == "attach")
                        self.assertLess(last_attach, comp.method_log.index("setcontents"))
                    self.assertEqual(comp.contents, 0)
                    self.assertTrue(comp.not_solid)


class TestCompanionSquadCap(unittest.TestCase):
    def test_solo_fields_three_companions_and_refuses_fourth_without_charging(self) -> None:
        _, gsc, (player,) = _setup()
        statuses = [_purchase_status(_hire(gsc, player)) for _ in range(4)]
        self.assertEqual(statuses, ["ok", "ok", "ok", "squad_full"])
        self.assertEqual(len(_companions(gsc)), 3)
        self.assertEqual(player.get_field("score"), 50000 - 3 * 2000)
        self.assertIn("Squad full", player.client_dvars["ui_bz_companion_status"])

    def test_cap_counts_every_human_player(self) -> None:
        for player_count, allowed in ((2, 2), (3, 1), (4, 0)):
            with self.subTest(players=player_count):
                _, gsc, players = _setup(player_count=player_count)
                statuses = [_purchase_status(_hire(gsc, players[0])) for _ in range(allowed + 1)]
                self.assertEqual(statuses, ["ok"] * allowed + ["squad_full"])
                self.assertEqual(len(_companions(gsc)), allowed)


class TestCompanionFollow(unittest.TestCase):
    def _walk(self, gsc, player, comp, xs: list[float]) -> list[str]:
        results = []
        for x in xs:
            player.set_pos(x, 0.0, 0.0)
            gsc.call(BZ_COMPANIONS_MOD, "bz_companions_sample_owner", player)
            results.append(gsc.call(BZ_COMPANIONS_MOD, "bz_companions_tick_follow", comp, 0.1))
        return results

    def test_follows_owner_breadcrumb_trail_and_holds_spacing_behind(self) -> None:
        _, gsc, (player,) = _setup()
        _hire(gsc, player)
        (comp,) = _companions(gsc)

        # Owner walks +x in 40u steps; the Companion trails along recorded crumbs.
        self._walk(gsc, player, comp, [40.0 * i for i in range(1, 16)])
        self.assertGreater(len(comp.move_calls), 0)
        for _ in range(40):
            gsc.call(BZ_COMPANIONS_MOD, "bz_companions_tick_follow", comp, 0.1)
        cx, cy, _ = comp.get_pos()
        # Settles two crumbs (80u) behind the owner on the owner's own path.
        self.assertAlmostEqual(cx, 600.0 - 80.0, delta=1.0)
        self.assertAlmostEqual(cy, 0.0, delta=1.0)
        self.assertEqual(gsc.call(BZ_COMPANIONS_MOD, "bz_companions_tick_follow", comp, 0.1), "hold")

    def test_move_step_is_speed_limited(self) -> None:
        _, gsc, (player,) = _setup()
        _hire(gsc, player)
        (comp,) = _companions(gsc)
        comp.set_pos(0.0, 0.0, 0.0)
        self._walk(gsc, player, comp, [40.0 * i for i in range(1, 6)])
        prev = (0.0, 0.0, 0.0)
        for dest, _dur in comp.move_calls:
            step = sum((a - b) ** 2 for a, b in zip(dest, prev)) ** 0.5
            self.assertLessEqual(step, 29.0 + 1e-6)  # catch-up speed 290 u/s * 0.1 s
            prev = dest

    def test_owner_teleport_warps_companion_behind_owner(self) -> None:
        _, gsc, (player,) = _setup()
        _hire(gsc, player)
        (comp,) = _companions(gsc)
        player.set_pos(2000.0, 500.0, 0.0)
        before = len(gsc.emitted_events)
        gsc.call(BZ_COMPANIONS_MOD, "bz_companions_sample_owner", player)
        self.assertEqual(gsc.call(BZ_COMPANIONS_MOD, "bz_companions_tick_follow", comp, 0.1), "warp")
        cx, cy, _ = comp.get_pos()
        self.assertLess(((cx - 2000.0) ** 2 + (cy - 500.0) ** 2) ** 0.5, 120.0)
        self.assertTrue(any("COMPANION_WARP" in ev and "reason=teleport" in ev for ev in gsc.emitted_events[before:]))

    def test_stranded_companion_warps_even_without_teleport(self) -> None:
        _, gsc, (player,) = _setup()
        _hire(gsc, player)
        (comp,) = _companions(gsc)
        comp.set_pos(-1500.0, 0.0, 0.0)
        self.assertEqual(gsc.call(BZ_COMPANIONS_MOD, "bz_companions_tick_follow", comp, 0.1), "warp")
        self.assertTrue(any("reason=stranded" in ev for ev in gsc.emitted_events))

    def test_warp_falls_back_to_owner_position_when_offset_is_behind_a_wall(self) -> None:
        _, gsc, (player,) = _setup()
        _hire(gsc, player)
        (comp,) = _companions(gsc)
        gsc.trace_passed_fn = lambda start, end: False
        player.set_pos(3000.0, 0.0, 0.0)
        gsc.call(BZ_COMPANIONS_MOD, "bz_companions_sample_owner", player)
        gsc.call(BZ_COMPANIONS_MOD, "bz_companions_tick_follow", comp, 0.1)
        cx, cy, _ = comp.get_pos()
        self.assertEqual((round(cx), round(cy)), (3000, 0))


class TestCompanionCombat(unittest.TestCase):
    def test_fires_magicbullet_at_nearest_visible_zombie_credited_to_owner(self) -> None:
        _, gsc, (player,) = _setup()
        _hire(gsc, player)
        (comp,) = _companions(gsc)
        comp.set_pos(0.0, 0.0, 0.0)
        far = _zombie("Far", 700.0, 0.0)
        near = _zombie("Near", 0.0, 300.0)
        gsc.ai_enemies.extend([far, near])

        target = gsc.call(BZ_COMPANIONS_MOD, "bz_companions_tick_combat", comp, 5000)
        self.assertIs(target, near)
        (shot,) = gsc.magic_bullets
        self.assertEqual(shot["weapon"], "kar98k")
        self.assertIs(shot["owner"], player)
        self.assertEqual([round(float(shot["end"][i])) for i in range(3)], [0, 300, 44])
        self.assertTrue(any("COMPANION_FIRE" in ev for ev in gsc.emitted_events))

    def test_respects_fire_interval(self) -> None:
        _, gsc, (player,) = _setup()
        _hire(gsc, player)
        (comp,) = _companions(gsc)
        comp.set_pos(0.0, 0.0, 0.0)
        gsc.ai_enemies.append(_zombie("Z", 200.0, 0.0))
        for now in (1000, 1100, 1899, 1900, 2800):
            gsc.call(BZ_COMPANIONS_MOD, "bz_companions_tick_combat", comp, now)
        self.assertEqual(len(gsc.magic_bullets), 3)  # 1000, 1900, 2800

    def test_ignores_dead_out_of_range_and_hidden_zombies(self) -> None:
        _, gsc, (player,) = _setup()
        _hire(gsc, player)
        (comp,) = _companions(gsc)
        comp.set_pos(0.0, 0.0, 0.0)
        gsc.ai_enemies.extend([_zombie("Dead", 100.0, 0.0, health=0), _zombie("Far", 1200.0, 0.0)])
        self.assertIs(gsc.call(BZ_COMPANIONS_MOD, "bz_companions_tick_combat", comp, 1000), UNDEFINED)
        gsc.ai_enemies.append(_zombie("Hidden", 300.0, 0.0))
        gsc.trace_passed_fn = lambda start, end: False
        self.assertIs(gsc.call(BZ_COMPANIONS_MOD, "bz_companions_tick_combat", comp, 1000), UNDEFINED)
        self.assertEqual(getattr(gsc, "magic_bullets", []), [])


class TestCompanionTeardown(unittest.TestCase):
    def test_owner_release_removes_only_that_owners_companions(self) -> None:
        _, gsc, (p1, p2) = _setup(player_count=2)
        _hire(gsc, p1)
        _hire(gsc, p2)
        removed = gsc.call(BZ_COMPANIONS_MOD, "bz_companions_release_owner", p1, "disconnect")
        self.assertEqual(removed, 1)
        (left,) = _companions(gsc)
        self.assertIs(left.get_field("bz_owner"), p2)
        self.assertEqual(_script_models(gsc), [left])

    def test_end_game_removes_every_companion(self) -> None:
        _, gsc, (player,) = _setup()
        for _ in range(3):
            _hire(gsc, player)
        gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
        self.assertEqual(_companions(gsc), [])
        self.assertEqual(_script_models(gsc), [])
        self.assertTrue(any("COMPANION_CLEANUP|removed=3" in ev for ev in gsc.emitted_events))


class TestCompanionWaw17Compliance(unittest.TestCase):
    def test_module_is_ascii_without_foreach_or_loadfx(self) -> None:
        raw = BZ_COMPANIONS_PATH.read_bytes()
        self.assertTrue(raw.isascii())
        code = "\n".join(line.split("//", 1)[0] for line in raw.decode("ascii").splitlines())
        self.assertNotIn("foreach", code)
        self.assertNotIn("LoadFX", code)
        self.assertNotIn("PrecacheModel", code)


if __name__ == "__main__":
    unittest.main()
