"""Offline TDD contract suite for P2-T2 (#24): Stock Elemental Upgrades
(Enhanced Flamethrower & Wunderwaffe DG-2 Stun + Juggernog HP-Reset Fix).

Exercises real WaW 1.7 `.gsc` source (`mod/maps/_bz_elem_stock.gsc`) and the
build-time `_zombiemode_tesla.gsc` patcher (`scripts/build_mod.py`) through an
extended GSC runtime built on `tests/gsc_runtime.py` + `BzGscRuntime`:
  1. `inject_zombiemode_tesla_hooks()` on both Sumpf & Der Riese shapes,
     staging into `stage_mod_files()` / `generate_staged_mod_csv()`, and
     simulating WaW 1.7's C++ `player.health` setter clobbering `maxhealth = 100`
     to prove Classic Mode stays untouched when `bz_elements_enabled == 0` while
     Jugg I (160), Jugg II (220), and Titan + Jugg II (440) HP are preserved
     when `bz_elements_enabled == 1`.
  2. Wunderwaffe DG-2 `bz_tesla_on_chain_hit()` applying 3.5s stun to
     chained/nearby zombies, Blast Shield/Wunderwaffe self-splash guard in
     `player_damage`, and `BZ_EVENT|ELEM_TESLA_STUN|...` telemetry.
  3. Enhanced Flamethrower (`m2_flamethrower_zombie` & `_upgraded`, `MOD_BURNED`):
     close-range (<= 192 units) heavy melt + long-range (> 192 units)
     percentage-HP burn DOT loop across all 4 Stock Maps (0 new FX), respecting
     zombie death & `end_game`, and emitting `BZ_EVENT|ELEM_FLAME_DOT|...`.
  4. Strict Classic Mode / `bz_elements_enabled 0` noop and WaW 1.7 syntax
     compliance (zero `foreach`, zero `endon` in sync callers, ASCII-only).
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import tempfile
from typing import Any
import unittest
import zlib

REPO_ROOT = Path(__file__).resolve().parent.parent
MOD_ROOT = REPO_ROOT / "mod"
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tests.gsc_runtime import (  # noqa: E402
    FakeDvarStore,
    GscArray,
    GscStruct,
    UNDEFINED,
    _waw_to_str,
    tokenize,
)
from tests.test_bz_hooks_and_build import (  # noqa: E402
    BZ_HOOKS_MOD,
    BzGscParser,
    BzGscRuntime,
    FakeEntity,
    _ast_contains_method_call,
)

BZ_ELEM_STOCK_MOD = "maps\\_bz_elem_stock"
BZ_ELEM_STOCK_PATH = MOD_ROOT / "maps" / "_bz_elem_stock.gsc"
BZ_STATE_MOD = "maps\\_bz_state"
BZ_PERKS_MOD = "maps\\_bz_perks"
BZ_CLASSES_MOD = "maps\\_bz_classes"


SYNTHETIC_SUMPF_TESLA_GSC = (
    "tesla_damage_init( hit_location, hit_origin, player )\n"
    "{\n"
    "\tlevel.tesla_enemies_hit = 1;\n"
    "\tself tesla_arc_damage( self, player, 1 );\n"
    "}\n"
    "\n"
    "tesla_arc_damage( source_enemy, player, arc_num )\n"
    "{\n"
    "\tif ( arc_num >= level.zombie_vars[\"tesla_max_arcs\"] )\n"
    "\t{\n"
    "\t\treturn;\n"
    "\t}\n"
    "\tself DoDamage( self.health + 666, self.origin, player );\n"
    "}\n"
    "\n"
    "tesla_pvp_thread()\n"
    "{\n"
    "\tself endon( \"disconnect\" );\n"
    "\tself endon( \"death\" );\n"
    "\tself endon( \"spawned_spectator\" );\n"
    "\n"
    "\tfor( ;; )\n"
    "\t{\n"
    "\t\tself waittill( \"weapon_pvp_attack\", attacker, weapon );\n"
    "\n"
    "\t\tif ( weapon != \"tesla_gun\" )\n"
    "\t\t{\n"
    "\t\t\tcontinue;\n"
    "\t\t}\n"
    "\n"
    "\t\tif ( self == attacker )\n"
    "\t\t{\n"
    "\t\t\tdamage = int( self.maxhealth * .25 );\n"
    "\t\t\tif ( damage < 25 )\n"
    "\t\t\t{\n"
    "\t\t\t\tdamage = 25;\n"
    "\t\t\t}\n"
    "\n"
    "\t\t\tif ( self.health - damage < 1 )\n"
    "\t\t\t{\n"
    "\t\t\t\tself.health = 1;\n"
    "\t\t\t}\n"
    "\t\t\telse\n"
    "\t\t\t{\n"
    "\t\t\t\tself.health -= damage;\n"
    "\t\t\t}\n"
    "\t\t}\n"
    "\n"
    "\t\tself setelectrified( 1.0 );\n"
    "\t\tself shellshock( \"electrocution\", 1.0 );\n"
    "\t\tself playsound( \"tesla_bounce\" );\n"
    "\t}\n"
    "}\n"
)

SYNTHETIC_FACTORY_TESLA_GSC = (
    "tesla_damage_init( hit_location, hit_origin, player )\r\n"
    "{\r\n"
    "\tlevel.tesla_enemies_hit = 1;\r\n"
    "\tself thread tesla_do_damage( self, 1, player );\r\n"
    "}\r\n"
    "\r\n"
    "tesla_do_damage( source_enemy, arc_num, player )\r\n"
    "{\r\n"
    "\ttesla_network_choke();\r\n"
    "\tself DoDamage( self.health + 666, self.origin, player );\r\n"
    "}\r\n"
    "\r\n"
    "tesla_network_choke()\r\n"
    "{\r\n"
    "\tlevel.tesla_network_choke_count++;\r\n"
    "}\r\n"
    "\r\n"
    "tesla_pvp_thread()\r\n"
    "{\r\n"
    "\tself endon( \"disconnect\" );\r\n"
    "\tself endon( \"death\" );\r\n"
    "\tself endon( \"spawned_spectator\" );\r\n"
    "\r\n"
    "\tfor( ;; )\r\n"
    "\t{\r\n"
    "\t\tself waittill( \"weapon_pvp_attack\", attacker, weapon );\r\n"
    "\r\n"
    "\t\tif ( weapon != \"tesla_gun\" && weapon != \"tesla_gun_upgraded\" )\r\n"
    "\t\t{\r\n"
    "\t\t\tcontinue;\r\n"
    "\t\t}\r\n"
    "\r\n"
    "\t\tif ( self == attacker )\r\n"
    "\t\t{\r\n"
    "\t\t\tdamage = int( self.maxhealth * .25 );\r\n"
    "\t\t\tif ( damage < 25 )\r\n"
    "\t\t\t{\r\n"
    "\t\t\t\tdamage = 25;\r\n"
    "\t\t\t}\r\n"
    "\r\n"
    "\t\t\tif ( self.health - damage < 1 )\r\n"
    "\t\t\t{\r\n"
    "\t\t\t\tself.health = 1;\r\n"
    "\t\t\t}\r\n"
    "\t\t\telse\r\n"
    "\t\t\t{\r\n"
    "\t\t\t\tself.health -= damage;\r\n"
    "\t\t\t}\r\n"
    "\t\t}\r\n"
    "\r\n"
    "\t\tself setelectrified( 1.0 );\r\n"
    "\t\tself shellshock( \"electrocution\", 1.0 );\r\n"
    "\t\tself playsound( \"tesla_bounce\" );\r\n"
    "\t}\r\n"
    "}\r\n"
)


class ElemStockFakeEntity(FakeEntity):
    """Fake WaW 1.7 entity with optional C++ player.health -> maxhealth=100 clobber simulation."""

    def __init__(
        self,
        name: str = "player_0",
        ent_num: int = 0,
        is_player: bool = True,
        *,
        simulate_waw_health_clobber: bool = False,
    ) -> None:
        self._simulate_clobber = False
        super().__init__(name=name, ent_num=ent_num, is_player=is_player)
        self.set_field("origin", GscArray([0, 0, 0]))
        self.set_field("moveplaybackrate", 1.0)
        self.damage_events: list[dict[str, Any]] = []
        self.electrified_calls: list[float] = []
        self.shellshock_calls: list[tuple[str, float]] = []
        self.sounds_played: list[str] = []
        self._simulate_clobber = simulate_waw_health_clobber

    def set_field(self, name: str, value: Any) -> None:
        super().set_field(name, value)
        # Replicate WaW 1.7 C++ engine quirk: writing player.health resets player.maxhealth to 100!
        if self._simulate_clobber and self.is_player and name.lower() == "health":
            super().set_field("maxhealth", 100)


class ElemStockGscRuntime(BzGscRuntime):
    """Extends BzGscRuntime with AI list, DoDamage, FX call tracking, and inline module loading."""

    def __init__(self, mod_root: Path, dvars: FakeDvarStore | None = None) -> None:
        super().__init__(mod_root, dvars)
        self.ai_enemies: list[ElemStockFakeEntity] = []
        self.fx_loads: list[str] = []
        self.fx_plays: list[Any] = []

    def load_source_module(self, module_path: str, source_text: str) -> None:
        key = self.normalize_module_key(module_path)
        tokens = tokenize(source_text, filename=f"<{key}.gsc>")
        self._modules[key] = BzGscParser(tokens, filename=f"<{key}.gsc>").parse_module()

    def _call_builtin(self, name_lower: str, args: list[Any], line: int) -> tuple[bool, Any]:
        if name_lower == "getaispeciesarray":
            return True, GscArray([z for z in self.ai_enemies if not z.deleted])
        if name_lower == "loadfx":
            self.fx_loads.append(_waw_to_str(args[0]) if args else "")
            return True, 1
        if name_lower == "playfx":
            self.fx_plays.append(args)
            return True, UNDEFINED
        return super()._call_builtin(name_lower, args, line)

    def _exec_method(self, receiver: Any, method: str, args: list[Any], line: int) -> Any:
        if isinstance(receiver, ElemStockFakeEntity):
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
            if method == "setelectrified":
                receiver.electrified_calls.append(float(args[0]) if args else 0.0)
                return UNDEFINED
            if method == "shellshock":
                receiver.shellshock_calls.append(
                    (_waw_to_str(args[0]) if args else "", float(args[1]) if len(args) > 1 else 0.0)
                )
                return UNDEFINED
            if method == "playsound":
                receiver.sounds_played.append(_waw_to_str(args[0]) if args else "")
                return UNDEFINED
        return super()._exec_method(receiver, method, args, line)


def _extract_tesla_pvp_single_pass_fn(patched_tesla_src: str) -> str:
    """Wrap the patched `tesla_pvp_thread()` loop body into a single-step testable GSC function."""
    m = re.search(
        r'self\s+waittill\(\s*"weapon_pvp_attack"\s*,\s*attacker\s*,\s*weapon\s*\)\s*;',
        patched_tesla_src,
    )
    if m is None:
        raise AssertionError("Could not find waittill weapon_pvp_attack in patched tesla source")
    # Extract everything from after waittill to the matching closing brace of the `for( ;; )` loop
    # and wrap in `tesla_pvp_step( attacker, weapon )` with `for ( _once = 0; _once < 1; _once++ )`
    # so `continue;` inside the patched block behaves identically to WaW's `for( ;; )`!
    rest = patched_tesla_src[m.end() :]
    # Find the `for( ;; )` closing brace by tracking brace depth starting at 1
    depth = 1
    end_idx = -1
    for i, ch in enumerate(rest):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = i
                break
    if end_idx == -1:
        raise AssertionError("Unbalanced braces inside patched tesla_pvp_thread()")
    loop_body = rest[:end_idx]
    return (
        "tesla_pvp_step( attacker, weapon )\n"
        "{\n"
        "\tfor ( _bz_once = 0; _bz_once < 1; _bz_once++ )\n"
        "\t{\n"
        f"{loop_body}\n"
        "\t}\n"
        "}\n"
    )


def _setup_elem_stock_env(
    map_name: str = "nazi_zombie_factory",
    *,
    bz_enabled: bool = True,
    elements_enabled: bool = True,
    perks_enabled: bool = True,
    classes_enabled: bool = True,
    simulate_waw_health_clobber: bool = False,
) -> tuple[FakeDvarStore, ElemStockGscRuntime, ElemStockFakeEntity]:
    dvars = FakeDvarStore()
    dvars.set("bz_enabled", "1" if bz_enabled else "0")
    dvars.set("bz_elements_enabled", "1" if elements_enabled else "0")
    dvars.set("bz_perks_enabled", "1" if perks_enabled else "0")
    dvars.set("bz_classes_enabled", "1" if classes_enabled else "0")
    dvars.set("bz_pap_enabled", "1")
    dvars.set("bz_companions_enabled", "0")

    gsc = ElemStockGscRuntime(MOD_ROOT, dvars)
    gsc.level.set_field("script", map_name)
    gsc.level.set_field("round_number", 1)

    player = ElemStockFakeEntity(
        "PlayerOne",
        ent_num=0,
        is_player=True,
        simulate_waw_health_clobber=simulate_waw_health_clobber,
    )
    player.set_field("score", 100000)
    player.set_field("origin", GscArray([0, 0, 0]))
    player.give_weapon("tesla_gun", make_current=True)
    gsc.players.append(player)

    gsc.call(BZ_ELEM_STOCK_MOD, "bz_elem_stock_register")
    gsc.call(BZ_HOOKS_MOD, "bz_pre_init")
    gsc.call(BZ_HOOKS_MOD, "bz_init")
    return dvars, gsc, player


class TestTeslaBuildPatcherAndStaging(unittest.TestCase):
    """Slice 1: build_mod.inject_zombiemode_tesla_hooks() on Sumpf & Der Riese shapes + staging."""

    def setUp(self) -> None:
        import build_mod

        self.bm = build_mod

    def test_inject_zombiemode_tesla_hooks_patches_sumpf_and_factory_shapes_and_preserves_classic(self) -> None:
        for label, src in (
            ("sumpf", SYNTHETIC_SUMPF_TESLA_GSC),
            ("factory", SYNTHETIC_FACTORY_TESLA_GSC),
        ):
            patched = self.bm.inject_zombiemode_tesla_hooks(src)
            self.assertIsInstance(patched, str)

            # Must gate all custom behavior behind bz_elements_enabled()
            self.assertIn("maps\\_bz_hooks::bz_elements_enabled()", patched, f"{label}: missing elements gate")
            # Must bracket self.health writes with sav = self.maxhealth; ... self.maxhealth = sav;
            self.assertIn("sav = self.maxhealth;", patched, f"{label}: missing maxhealth save")
            self.assertIn("self.maxhealth = sav;", patched, f"{label}: missing maxhealth restore")
            # Must recompute player max health via _bz_hooks
            self.assertIn(
                "maps\\_bz_hooks::bz_recompute_player_max_health( self );",
                patched,
                f"{label}: missing bz_recompute_player_max_health",
            )
            # Must guard self-shock immunity (Blast Shield)
            self.assertIn(
                "maps\\_bz_elem_stock::bz_tesla_is_self_shock_immune( self )",
                patched,
                f"{label}: missing self-shock immunity guard",
            )
            # Must hook chain hit for buffed Wunderwaffe stun
            self.assertIn(
                "maps\\_bz_elem_stock::bz_tesla_on_chain_hit( self, player );",
                patched,
                f"{label}: missing chain-hit stun hook",
            )
            # Classic Mode else-branch preserves stock self.health logic untouched
            self.assertIn("else", patched)
            # Zero foreach and valid WaW 1.7 tokenization
            tokens = tokenize(patched, filename=f"{label}_zombiemode_tesla.gsc")
            self.assertGreater(len(tokens), 10)
            BzGscParser(tokens, filename=f"{label}_zombiemode_tesla.gsc").parse_module()

        # Also accepts bytes and returns bytes
        patched_bytes = self.bm.inject_zombiemode_tesla_hooks(SYNTHETIC_FACTORY_TESLA_GSC.encode("latin1"))
        self.assertIsInstance(patched_bytes, bytes)
        self.assertIn(b"bz_recompute_player_max_health", patched_bytes)

        # Rejects malformed scripts lacking tesla_pvp_thread or chain anchors
        with self.assertRaises(ValueError):
            self.bm.inject_zombiemode_tesla_hooks("init()\n{\n}\n")

    def test_inject_zombiemode_tesla_hooks_preserves_sumpf_dlc2_era_parity(self) -> None:
        factory_with_dlc3 = (
            "#include maps\\_utility;\n"
            "#include maps\\_zombiemode_net;\n"
            "init()\n{\n"
            '\tlevel._effect["tesla_viewmodel_rail_upgraded"] = loadfx( "maps/zombie/fx_zombie_tesla_rail_view_ug" );\n'
            "}\n"
            "tesla_play_death_fx( fx, tag )\n{\n"
            '\tnetwork_safe_play_fx_on_tag( "tesla_death_fx", 2, level._effect[fx], self, tag );\n'
            "\tself.deathanim = random( level._zombie_tesla_death[self.animname] );\n"
            "\tself.deathanim = random( level._zombie_tesla_crawl_death[self.animname] );\n"
            "}\n"
            + SYNTHETIC_FACTORY_TESLA_GSC
        )
        patched = self.bm.inject_zombiemode_tesla_hooks(factory_with_dlc3)
        assert isinstance(patched, str)
        self.assertNotIn("#include maps\\_zombiemode_net;", patched)
        self.assertNotIn("network_safe_play_fx_on_tag", patched)
        self.assertIn("PlayFxOnTag( level._effect[fx], self, tag )", patched)
        self.assertIn('tolower( level.script ) == "nazi_zombie_factory"', patched)
        self.assertIn("random( level._zombie_tesla_death )", patched)
        self.assertIn("random( level._zombie_tesla_crawl_death )", patched)
        code_no_pp = "\n".join(line for line in patched.splitlines() if not line.lstrip().startswith("#"))
        tokens = tokenize(code_no_pp, filename="era_safe_tesla.gsc")
        BzGscParser(tokens, filename="era_safe_tesla.gsc").parse_module()

    def test_stage_bz_tesla_script_and_generate_staged_mod_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools_root = root / "tools"
            stage_dir = root / "stage"
            stage_dir.mkdir(parents=True)

            # When raw/maps/_zombiemode_tesla.gsc does not exist, staging is a clean noop (returns None)
            self.assertIsNone(self.bm.stage_bz_tesla_script(tools_root=tools_root, stage_dir=stage_dir))
            self.assertFalse((stage_dir / "maps" / "_zombiemode_tesla.gsc").exists())

            # When raw/maps/_zombiemode_tesla.gsc exists, it is patched and staged cleanly
            raw_tesla = tools_root / "raw" / "maps" / "_zombiemode_tesla.gsc"
            raw_tesla.parent.mkdir(parents=True)
            raw_tesla.write_text(SYNTHETIC_FACTORY_TESLA_GSC, encoding="latin1")

            staged_path = self.bm.stage_bz_tesla_script(tools_root=tools_root, stage_dir=stage_dir)
            self.assertEqual(staged_path, stage_dir / "maps" / "_zombiemode_tesla.gsc")
            self.assertTrue(staged_path.is_file())
            staged_text = staged_path.read_text(encoding="latin1")
            self.assertIn("maps\\_bz_hooks::bz_recompute_player_max_health( self );", staged_text)
            self.assertIn("maps\\_bz_elem_stock::bz_tesla_on_chain_hit( self, player );", staged_text)

            # generate_staged_mod_csv registers rawfile,maps/_zombiemode_tesla.gsc idempotently
            base_csv = (MOD_ROOT / "mod.csv").read_text(encoding="latin1")
            self.assertNotIn("rawfile,maps/_zombiemode_tesla.gsc", base_csv)
            updated_csv = self.bm.generate_staged_mod_csv(
                base_csv,
                ["maps/_bz_elem_stock.gsc", "maps/_zombiemode_tesla.gsc"],
            )
            self.assertEqual(updated_csv.count("rawfile,maps/_bz_elem_stock.gsc"), 1)
            self.assertEqual(updated_csv.count("rawfile,maps/_zombiemode_tesla.gsc"), 1)
            updated_csv_2 = self.bm.generate_staged_mod_csv(
                updated_csv,
                ["maps/_bz_elem_stock.gsc", "maps/_zombiemode_tesla.gsc"],
            )
            self.assertEqual(updated_csv_2.count("rawfile,maps/_zombiemode_tesla.gsc"), 1)

    def test_stage_bz_tesla_script_prefers_fastfiles_over_raw_tree(self) -> None:
        def _make_fake_ff(path: Path, rawfile_name: str, payload: bytes) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            blob = rawfile_name.encode("ascii") + b"\x00" + payload + b"\x00"
            path.write_bytes(b"IWffu100\x00\x00\x00\x00" + zlib.compress(blob))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools_root = root / "tools"
            steam_game = root / "steam"
            stage_dir = root / "stage"
            stage_dir.mkdir(parents=True)

            # Seed raw tree with a distinct marker
            raw_tesla = tools_root / "raw" / "maps" / "_zombiemode_tesla.gsc"
            raw_tesla.parent.mkdir(parents=True)
            raw_tesla.write_text("// SOURCE: RAW_TREE\n" + SYNTHETIC_FACTORY_TESLA_GSC, encoding="latin1")

            # Seed sumpf.ff, factory.ff, and factory_patch.ff with distinct markers
            sumpf_ff = steam_game / "zone" / "english" / "nazi_zombie_sumpf.ff"
            factory_ff = steam_game / "zone" / "english" / "nazi_zombie_factory.ff"
            factory_patch_ff = steam_game / "zone" / "english" / "nazi_zombie_factory_patch.ff"

            _make_fake_ff(
                sumpf_ff,
                "maps/_zombiemode_tesla.gsc",
                ("// SOURCE: SUMPF_FF\n" + SYNTHETIC_SUMPF_TESLA_GSC).encode("latin1"),
            )
            _make_fake_ff(
                factory_ff,
                "maps/_zombiemode_tesla.gsc",
                ("// SOURCE: FACTORY_FF\n" + SYNTHETIC_FACTORY_TESLA_GSC).encode("latin1"),
            )
            _make_fake_ff(
                factory_patch_ff,
                "maps/_zombiemode_tesla.gsc",
                ("// SOURCE: FACTORY_PATCH_FF\n" + SYNTHETIC_FACTORY_TESLA_GSC).encode("latin1"),
            )

            # 1. Prefers nazi_zombie_factory_patch.ff over factory.ff, sumpf.ff, and raw tree
            staged = self.bm.stage_bz_tesla_script(tools_root=tools_root, stage_dir=stage_dir, steam_game=steam_game)
            assert staged is not None
            self.assertIn("SOURCE: FACTORY_PATCH_FF", staged.read_text(encoding="latin1"))

            # 2. Without factory_patch.ff, prefers nazi_zombie_factory.ff over raw tree
            factory_patch_ff.unlink()
            staged = self.bm.stage_bz_tesla_script(tools_root=tools_root, stage_dir=stage_dir, steam_game=steam_game)
            assert staged is not None
            self.assertIn("SOURCE: FACTORY_FF", staged.read_text(encoding="latin1"))

            # 3. Without factory fastfiles, prefers nazi_zombie_sumpf.ff over raw tree
            factory_ff.unlink()
            staged = self.bm.stage_bz_tesla_script(tools_root=tools_root, stage_dir=stage_dir, steam_game=steam_game)
            assert staged is not None
            self.assertIn("SOURCE: SUMPF_FF", staged.read_text(encoding="latin1"))

            # 4. Only falls back to raw tree when no fastfile contains _zombiemode_tesla.gsc
            sumpf_ff.unlink()
            staged = self.bm.stage_bz_tesla_script(tools_root=tools_root, stage_dir=stage_dir, steam_game=steam_game)
            assert staged is not None
            self.assertIn("SOURCE: RAW_TREE", staged.read_text(encoding="latin1"))

    def test_patched_tesla_pvp_preserves_jugg1_jugg2_and_titan_440_hp_and_classic_untouched(self) -> None:
        patched_factory = self.bm.inject_zombiemode_tesla_hooks(SYNTHETIC_FACTORY_TESLA_GSC)
        assert isinstance(patched_factory, str)
        step_gsc = _extract_tesla_pvp_single_pass_fn(patched_factory)

        # Case 1: Classic Mode (bz_elements_enabled == 0) -> executes untouched stock branch
        dvars_c, gsc_c, player_c = _setup_elem_stock_env(
            bz_enabled=True,
            elements_enabled=False,
            simulate_waw_health_clobber=True,
        )
        gsc_c.load_source_module("maps\\_test_tesla_pvp", step_gsc)
        # Set up 160 HP Jugg without elements fix: stock self.health -= damage clobbers maxhealth -> 100
        player_c._simulate_clobber = False
        player_c.set_field("maxhealth", 160)
        player_c.set_field("health", 160)
        player_c._simulate_clobber = True
        gsc_c.emitted_events.clear()
        gsc_c.call_on(player_c, "maps\\_test_tesla_pvp", "tesla_pvp_step", player_c, "tesla_gun")
        self.assertEqual(player_c.get_field("health"), 120)
        self.assertEqual(player_c.get_field("maxhealth"), 100)  # stock untouched behavior
        self.assertEqual(len(player_c.electrified_calls), 1)
        self.assertFalse(any("ELEM_TESLA" in e for e in gsc_c.emitted_events))

        # Case 2: bz_elements_enabled == 1 -> Jugg I (160), Jugg II (220), Titan + Jugg II (440) preserved!
        _dvars, gsc, player = _setup_elem_stock_env(
            bz_enabled=True,
            elements_enabled=True,
            simulate_waw_health_clobber=True,
        )
        gsc.load_source_module("maps\\_test_tesla_pvp", step_gsc)

        # 2a. Juggernog I (160 HP)
        player.give_perk("specialty_armorvest")
        gsc.call(BZ_STATE_MOD, "bz_try_buy_perk", player, "juggernog")
        gsc.call(BZ_HOOKS_MOD, "bz_recompute_player_max_health", player)
        player._simulate_clobber = False
        player.set_field("maxhealth", 160)
        player.set_field("health", 160)
        player._simulate_clobber = True
        gsc.call_on(player, "maps\\_test_tesla_pvp", "tesla_pvp_step", player, "tesla_gun")
        self.assertEqual(player.get_field("health"), 120)
        self.assertEqual(player.get_field("maxhealth"), 160)

        # 2b. Juggernog II (220 HP)
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_perks", "buy_t2:juggernog")
        player._simulate_clobber = False
        player.set_field("maxhealth", 220)
        player.set_field("health", 220)
        player._simulate_clobber = True
        gsc.call_on(player, "maps\\_test_tesla_pvp", "tesla_pvp_step", player, "tesla_gun_upgraded")
        self.assertEqual(player.get_field("health"), 165)
        self.assertEqual(player.get_field("maxhealth"), 220)

        # 2c. Titan + Juggernog II (440 HP) — normal self-shock (440 - 110 = 330) AND near-death clamp (health = 1)
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_class", "buy_class:titan")
        player._simulate_clobber = False
        player.set_field("maxhealth", 440)
        player.set_field("health", 440)
        player._simulate_clobber = True
        gsc.call_on(player, "maps\\_test_tesla_pvp", "tesla_pvp_step", player, "tesla_gun_upgraded")
        self.assertEqual(player.get_field("health"), 330)
        self.assertEqual(player.get_field("maxhealth"), 440)

        # Near-death clamp to 1 HP must STILL keep maxhealth == 440
        player._simulate_clobber = False
        player.set_field("health", 40)
        player._simulate_clobber = True
        gsc.call_on(player, "maps\\_test_tesla_pvp", "tesla_pvp_step", player, "tesla_gun_upgraded")
        self.assertEqual(player.get_field("health"), 1)
        self.assertEqual(player.get_field("maxhealth"), 440)

        # 2d. Blast Shield owned -> completely skips self-shock damage AND electrocution/shellshock
        gsc.call(BZ_HOOKS_MOD, "bz_on_menu_response", player, "bz_station_perks", "buy_apex:blast_shield")
        player._simulate_clobber = False
        player.set_field("health", 440)
        player.set_field("maxhealth", 440)
        player._simulate_clobber = True
        elec_before = len(player.electrified_calls)
        gsc.call_on(player, "maps\\_test_tesla_pvp", "tesla_pvp_step", player, "tesla_gun_upgraded")
        self.assertEqual(player.get_field("health"), 440)
        self.assertEqual(player.get_field("maxhealth"), 440)
        self.assertEqual(len(player.electrified_calls), elec_before)
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|ELEM_TESLA_SELF_GUARD|") and "blocked=1" in e and "maxhealth=440" in e
                for e in gsc.emitted_events
            ),
            f"Missing blocked ELEM_TESLA_SELF_GUARD telemetry: {gsc.emitted_events}",
        )


class TestWunderwaffeChainStunAndSplashGuard(unittest.TestCase):
    """Slice 2: Wunderwaffe DG-2 3.5s chain-stun, player_damage splash guard, and telemetry."""

    def test_register_is_idempotent_under_elements_gate(self) -> None:
        dvars = FakeDvarStore()
        dvars.set("bz_enabled", "1")
        dvars.set("bz_elements_enabled", "1")
        gsc = ElemStockGscRuntime(MOD_ROOT, dvars)

        gsc.call(BZ_ELEM_STOCK_MOD, "bz_elem_stock_register")
        gsc.call(BZ_ELEM_STOCK_MOD, "bz_elem_stock_register")  # idempotent

        hooks = gsc.level.get_field("bz_hooks")
        for hook_name in ("init", "player_damage", "actor_damage", "end_game"):
            entries = hooks[hook_name]
            self.assertIsNot(entries, UNDEFINED, f"Missing hook registration for {hook_name}")
            elem_entries = [entries[i] for i in range(entries.size) if entries[i].get_field("gate") == "elements"]
            self.assertEqual(len(elem_entries), 1, f"Hook {hook_name} must register exactly once under 'elements'")

    def test_wunderwaffe_chain_hit_stuns_nearby_zombies_for_3_5s_and_emits_telemetry(self) -> None:
        import build_mod

        _dvars, gsc, player = _setup_elem_stock_env(map_name="nazi_zombie_sumpf")
        gsc.sim_time_ms = 5000

        z_primary = ElemStockFakeEntity("ZPrimary", ent_num=10, is_player=False)
        z_primary.set_field("health", 2000)
        z_primary.set_field("origin", GscArray([100, 0, 0]))

        z_near = ElemStockFakeEntity("ZNear", ent_num=11, is_player=False)
        z_near.set_field("health", 2000)
        z_near.set_field("origin", GscArray([320, 0, 0]))  # dist = 220 <= 300

        z_far = ElemStockFakeEntity("ZFar", ent_num=12, is_player=False)
        z_far.set_field("health", 2000)
        z_far.set_field("origin", GscArray([700, 0, 0]))  # dist = 600 > 300

        gsc.ai_enemies.extend([z_primary, z_near, z_far])

        stunned = gsc.call(BZ_ELEM_STOCK_MOD, "bz_tesla_on_chain_hit", z_primary, player)
        self.assertEqual(stunned, 2)

        # Primary + nearby zombie stunned for 3.5s (3500ms); far zombie untouched
        for z in (z_primary, z_near):
            self.assertTrue(z.get_field("bz_stunned"))
            self.assertTrue(z.get_field("bz_tesla_stunned"))
            self.assertTrue(z.get_field("ignoreall"))
            self.assertAlmostEqual(float(z.get_field("moveplaybackrate")), 0.01, places=6)
            self.assertEqual(z.get_field("bz_tesla_stun_until"), 8500)

        self.assertNotEqual(z_far.get_field("bz_stunned"), True)
        self.assertAlmostEqual(float(z_far.get_field("moveplaybackrate")), 1.0, places=6)

        # Emits structured BZ_EVENT|ELEM_TESLA_STUN|...
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|ELEM_TESLA_STUN|")
                and "player=PlayerOne" in e
                and "stunned=2" in e
                and "duration=3.5" in e
                for e in gsc.emitted_events
            ),
            f"Missing ELEM_TESLA_STUN telemetry: {gsc.emitted_events}",
        )

        # Dedicated child stun timer clears stun cleanly when its wait elapses
        gsc.call_on(z_near, BZ_ELEM_STOCK_MOD, "bz_elem_stock_tesla_stun_timer", 3.5, 8500)
        self.assertFalse(z_near.get_field("bz_stunned"))
        self.assertFalse(z_near.get_field("bz_tesla_stunned"))
        self.assertFalse(z_near.get_field("ignoreall"))
        self.assertAlmostEqual(float(z_near.get_field("moveplaybackrate")), 1.0, places=6)

        # Also verify patched _zombiemode_tesla.gsc chain hook invokes bz_tesla_on_chain_hit end-to-end
        patched_sumpf = build_mod.inject_zombiemode_tesla_hooks(SYNTHETIC_SUMPF_TESLA_GSC)
        assert isinstance(patched_sumpf, str)
        gsc.load_source_module("maps\\_test_sumpf_tesla", patched_sumpf)
        zv = GscArray()
        zv.set_item("tesla_max_arcs", 5)
        gsc.level.set_field("zombie_vars", zv)
        z_hooked = ElemStockFakeEntity("ZHooked", ent_num=13, is_player=False)
        z_hooked.set_field("health", 1000)
        z_hooked.set_field("origin", GscArray([1000, 0, 0]))
        z_hooked_neighbor = ElemStockFakeEntity("ZHookedNeighbor", ent_num=14, is_player=False)
        z_hooked_neighbor.set_field("health", 1000)
        z_hooked_neighbor.set_field("origin", GscArray([1150, 0, 0]))
        gsc.ai_enemies.extend([z_hooked, z_hooked_neighbor])
        gsc.sim_time_ms = 12000
        gsc.call_on(z_hooked, "maps\\_test_sumpf_tesla", "tesla_arc_damage", z_hooked, player, 1)
        self.assertTrue(z_hooked_neighbor.get_field("bz_tesla_stunned"))
        self.assertEqual(z_hooked_neighbor.get_field("bz_tesla_stun_until"), 15500)

    def test_wunderwaffe_chain_hit_and_flame_spread_skip_spawning_hellhounds_and_clamp_active_dogs(self) -> None:
        _dvars, gsc, player = _setup_elem_stock_env(map_name="nazi_zombie_factory")
        gsc.sim_time_ms = 5000

        dog_spawning = ElemStockFakeEntity("DogSpawning", ent_num=70, is_player=False)
        dog_spawning.set_field("species", "dog")
        dog_spawning.set_field("animname", "zombie_dog")
        dog_spawning.set_field("ignoreall", True)
        dog_spawning.set_field("magic_bullet_shield", True)
        dog_spawning.set_field("health", 600)
        dog_spawning.set_field("origin", GscArray([140, 0, 0]))

        dog_active = ElemStockFakeEntity("DogActive", ent_num=71, is_player=False)
        dog_active.set_field("species", "dog")
        dog_active.set_field("animname", "zombie_dog")
        dog_active.set_field("ignoreall", False)
        dog_active.set_field("health", 600)
        dog_active.set_field("origin", GscArray([180, 0, 0]))

        z_primary = ElemStockFakeEntity("ZPrimary", ent_num=72, is_player=False)
        z_primary.set_field("health", 2000)
        z_primary.set_field("origin", GscArray([100, 0, 0]))

        gsc.ai_enemies.extend([dog_spawning, dog_active, z_primary])

        # Direct chain hit on a spawning Hellhound must return 0 and leave it untouched
        self.assertEqual(gsc.call(BZ_ELEM_STOCK_MOD, "bz_tesla_on_chain_hit", dog_spawning, player), 0)
        self.assertIs(dog_spawning.get_field("bz_tesla_stunned"), UNDEFINED)
        self.assertTrue(dog_spawning.get_field("ignoreall"))
        self.assertAlmostEqual(float(dog_spawning.get_field("moveplaybackrate")), 1.0, places=4)

        # Chain hit on primary zombie stuns primary (0.01) + slows active dog (0.55), skips spawning dog!
        stunned = gsc.call(BZ_ELEM_STOCK_MOD, "bz_tesla_on_chain_hit", z_primary, player)
        self.assertEqual(stunned, 2)
        self.assertAlmostEqual(float(z_primary.get_field("moveplaybackrate")), 0.01, places=4)
        self.assertTrue(z_primary.get_field("ignoreall"))
        self.assertAlmostEqual(float(dog_active.get_field("moveplaybackrate")), 0.55, places=4)
        self.assertFalse(dog_active.get_field("ignoreall"))
        self.assertIs(dog_spawning.get_field("bz_tesla_stunned"), UNDEFINED)
        self.assertTrue(dog_spawning.get_field("ignoreall"))
        self.assertAlmostEqual(float(dog_spawning.get_field("moveplaybackrate")), 1.0, places=4)

        # Flame spread near spawning Hellhound (40u <= 96u) must also skip spawning dog
        spread = gsc.call(BZ_ELEM_STOCK_MOD, "bz_flame_spread_nearby", z_primary, player, 10, 1045, False)
        self.assertEqual(spread, 1)  # spreads to dog_active (80u <= 96u), NOT dog_spawning
        self.assertIs(dog_spawning.get_field("bz_flame_dot_active"), UNDEFINED)
        self.assertTrue(dog_spawning.get_field("ignoreall"))

    def test_wunderwaffe_self_splash_guard_in_player_damage_respects_blast_shield_and_preserves_hp(self) -> None:
        # Disable perks hook temporarily so we verify _bz_elem_stock's own player_damage Blast Shield guard directly
        _dvars, gsc, player = _setup_elem_stock_env(
            map_name="nazi_zombie_factory",
            perks_enabled=False,
            classes_enabled=True,
            elements_enabled=True,
        )
        player.set_field("maxhealth", 440)
        player.set_field("health", 440)

        # Without Blast Shield: Wunderwaffe self-splash is NOT cancelled to 0
        dmg_no_bs = gsc.call_on(
            player,
            BZ_HOOKS_MOD,
            "bz_player_damage_override",
            player,
            player,
            75,
            0,
            "MOD_PROJECTILE_SPLASH",
            "tesla_gun_upgraded",
            GscArray([0, 0, 0]),
            GscArray([0, 0, 0]),
            "none",
            0,
            0,
        )
        self.assertEqual(dmg_no_bs, 75)

        # With Blast Shield owned in state: Wunderwaffe self-splash is cancelled to 0
        gsc.call(BZ_STATE_MOD, "bz_try_buy_apex", player, "blast_shield")
        dmg_with_bs = gsc.call_on(
            player,
            BZ_HOOKS_MOD,
            "bz_player_damage_override",
            player,
            player,
            75,
            0,
            "MOD_PROJECTILE_SPLASH",
            "tesla_gun",
            GscArray([0, 0, 0]),
            GscArray([0, 0, 0]),
            "none",
            0,
            0,
        )
        self.assertEqual(dmg_with_bs, 0)
        self.assertTrue(
            any(
                e.startswith("BZ_EVENT|ELEM_TESLA_SELF_GUARD|") and "blocked=1" in e
                for e in gsc.emitted_events
            )
        )

        # Zombie melee damage is NOT cancelled by the Wunderwaffe self-splash guard
        enemy = ElemStockFakeEntity("ZAttacker", ent_num=25, is_player=False)
        enemy_dmg = gsc.call_on(
            player,
            BZ_HOOKS_MOD,
            "bz_player_damage_override",
            enemy,
            enemy,
            50,
            0,
            "MOD_MELEE",
            "none",
            GscArray([0, 0, 0]),
            GscArray([0, 0, 0]),
            "none",
            0,
            0,
        )
        self.assertEqual(enemy_dmg, 50)


class TestEnhancedFlamethrower(unittest.TestCase):
    """Slice 3: Enhanced Flamethrower close-range melt + long-range % HP burn DOT across all 4 maps."""

    def test_close_range_heavy_melt_vs_long_range_threshold_base_and_upgraded(self) -> None:
        _dvars, gsc, player = _setup_elem_stock_env(map_name="nazi_zombie_factory")
        gsc.level.set_field("round_number", 10)
        gsc.level.set_field("zombie_health", 1045)
        player.set_field("origin", GscArray([0, 0, 0]))

        # Close range (dist = 192 <= 192), base flamethrower: base 30 + close melt 418 = 448
        z_close = ElemStockFakeEntity("ZClose", ent_num=30, is_player=False)
        z_close.set_field("health", 1045)
        z_close.set_field("maxhealth", 1045)
        z_close.set_field("origin", GscArray([192, 0, 0]))

        dmg_close_base = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_close,
            player,
            player,
            30,
            0,
            "MOD_BURNED",
            "m2_flamethrower_zombie",
            z_close.get_field("origin"),
            GscArray([1, 0, 0]),
            "torso_upper",
            0,
        )
        self.assertEqual(dmg_close_base, 448)
        self.assertTrue(z_close.get_field("bz_flame_dot_active"))
        self.assertEqual(z_close.get_field("bz_flame_dot_damage"), 418)

        # Close range upgraded (m2_flamethrower_zombie_upgraded): base 45 + close melt 627 = 672
        z_close_up = ElemStockFakeEntity("ZCloseUp", ent_num=31, is_player=False)
        z_close_up.set_field("health", 1045)
        z_close_up.set_field("maxhealth", 1045)
        z_close_up.set_field("origin", GscArray([120, 0, 0]))

        dmg_close_up = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_close_up,
            player,
            player,
            45,
            0,
            "MOD_BURNED",
            "m2_flamethrower_zombie_upgraded",
            z_close_up.get_field("origin"),
            GscArray([1, 0, 0]),
            "torso_upper",
            0,
        )
        self.assertEqual(dmg_close_up, 672)
        self.assertEqual(z_close_up.get_field("bz_flame_dot_damage"), 627)

        # Long range (dist = 193 > 192): direct damage stays 30 (no close melt bonus),
        # while igniting long-range % HP burn DOT (229/tick on R10)
        z_long = ElemStockFakeEntity("ZLong", ent_num=32, is_player=False)
        z_long.set_field("health", 1045)
        z_long.set_field("maxhealth", 1045)
        z_long.set_field("origin", GscArray([193, 0, 0]))

        dmg_long_base = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_long,
            player,
            player,
            30,
            0,
            "MOD_BURNED",
            "m2_flamethrower_zombie",
            z_long.get_field("origin"),
            GscArray([1, 0, 0]),
            "torso_upper",
            0,
        )
        self.assertEqual(dmg_long_base, 30)
        self.assertTrue(z_long.get_field("bz_flame_dot_active"))
        self.assertFalse(z_long.get_field("bz_flame_dot_close"))
        self.assertEqual(z_long.get_field("bz_flame_dot_damage"), 229)

        # Also verify scripted Tier 1 PaP flamethrower on Nacht (no native _upgraded weapon) gets upgraded scaling
        _dvars_p, gsc_p, player_p = _setup_elem_stock_env(map_name="nazi_zombie_prototype")
        gsc_p.level.set_field("round_number", 10)
        gsc_p.level.set_field("zombie_health", 1045)
        player_p.set_field("origin", GscArray([0, 0, 0]))
        pap_tbl = GscArray()
        pap_tbl.set_item("m2_flamethrower_zombie", True)
        player_p.set_field("bz_single_pap_weapons", pap_tbl)
        z_nacht = ElemStockFakeEntity("ZNacht", ent_num=34, is_player=False)
        z_nacht.set_field("health", 1045)
        z_nacht.set_field("origin", GscArray([100, 0, 0]))
        dmg_nacht = gsc_p.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_nacht,
            player_p,
            player_p,
            30,
            0,
            "MOD_BURNED",
            "m2_flamethrower_zombie",
            z_nacht.get_field("origin"),
            GscArray([1, 0, 0]),
            "torso_upper",
            0,
        )
        self.assertEqual(dmg_nacht, 687)  # 30 * 2.0 (scripted Tier 1 PaP) + 627 (upgraded close melt)
        self.assertTrue(z_nacht.get_field("bz_flame_dot_upgraded"))

        # Melee while holding flamethrower must NOT trigger flame melt or DOT
        z_melee = ElemStockFakeEntity("ZMelee", ent_num=33, is_player=False)
        z_melee.set_field("health", 1045)
        z_melee.set_field("origin", GscArray([40, 0, 0]))
        dmg_melee = gsc.call(
            BZ_HOOKS_MOD,
            "bz_actor_damage_dispatch",
            z_melee,
            player,
            player,
            150,
            0,
            "MOD_MELEE",
            "m2_flamethrower_zombie",
            z_melee.get_field("origin"),
            GscArray([1, 0, 0]),
            "torso_upper",
            0,
        )
        self.assertEqual(dmg_melee, 150)
        self.assertNotEqual(z_melee.get_field("bz_flame_dot_active"), True)

    def test_long_range_burn_dot_ticks_across_all_4_stock_maps_spreads_and_respects_death_and_end_game(self) -> None:
        stock_maps = (
            "nazi_zombie_prototype",
            "nazi_zombie_asylum",
            "nazi_zombie_sumpf",
            "nazi_zombie_factory",
        )
        for stock_map in stock_maps:
            _dvars, gsc, player = _setup_elem_stock_env(map_name=stock_map)
            gsc.level.set_field("round_number", 10)
            gsc.level.set_field("zombie_health", 1045)
            player.set_field("origin", GscArray([0, 0, 0]))

            z_target = ElemStockFakeEntity("ZBurn", ent_num=40, is_player=False)
            z_target.set_field("health", 1045)
            z_target.set_field("maxhealth", 1045)
            z_target.set_field("origin", GscArray([320, 0, 0]))  # > 192 units (long range)

            z_spread = ElemStockFakeEntity("ZSpread", ent_num=41, is_player=False)
            z_spread.set_field("health", 1045)
            z_spread.set_field("maxhealth", 1045)
            z_spread.set_field("origin", GscArray([390, 0, 0]))  # dist = 70 <= 96 from z_target

            z_far = ElemStockFakeEntity("ZFar", ent_num=42, is_player=False)
            z_far.set_field("health", 1045)
            z_far.set_field("maxhealth", 1045)
            z_far.set_field("origin", GscArray([900, 0, 0]))

            gsc.ai_enemies.extend([z_target, z_spread, z_far])

            gsc.call(
                BZ_HOOKS_MOD,
                "bz_actor_damage_dispatch",
                z_target,
                player,
                player,
                30,
                0,
                "MOD_BURNED",
                "m2_flamethrower_zombie",
                z_target.get_field("origin"),
                GscArray([1, 0, 0]),
                "torso_upper",
                0,
            )

            # Target and nearby zombie ignited; far zombie untouched; 0 custom FX loaded/played
            self.assertTrue(z_target.get_field("bz_flame_dot_active"), f"Failed on {stock_map}")
            self.assertTrue(z_spread.get_field("bz_flame_dot_active"), f"Spread failed on {stock_map}")
            self.assertNotEqual(z_far.get_field("bz_flame_dot_active"), True)
            self.assertTrue(
                all(
                    fx in (
                        "misc/fx_zombie_powerup_on",
                        "misc/fx_exp_raygun_impact",
                        "env/electrical/fx_elec_short_oneshot",
                        "bio/player/fx_footstep_water",
                        "misc/fx_zombie_bloodsplat",
                    )
                    for fx in gsc.fx_loads
                ),
                f"Zero new FX allowed on {stock_map}: {gsc.fx_loads}",
            )
            self.assertEqual(gsc.fx_plays, [], f"Zero new FX allowed on {stock_map}")

            # Run the child DOT loop on z_target (4 ticks of 229 = 916 damage -> 1045 - 916 = 129 HP left)
            gsc.call_on(z_target, BZ_ELEM_STOCK_MOD, "bz_flame_burn_dot_thread", player, 10, 1045, False, False)
            self.assertEqual(len(z_target.damage_events), 4, f"Expected 4 burn ticks on {stock_map}")
            self.assertEqual(z_target.get_field("health"), 129)
            self.assertFalse(z_target.get_field("bz_flame_dot_active"))
            self.assertTrue(
                any(
                    e.startswith("BZ_EVENT|ELEM_FLAME_DOT|")
                    and f"map={stock_map}" in e
                    and "damage=229" in e
                    and "close=0" in e
                    for e in gsc.emitted_events
                ),
                f"Missing ELEM_FLAME_DOT event on {stock_map}: {gsc.emitted_events}",
            )

            # Respects zombie death: dead zombie takes 0 ticks
            z_dead = ElemStockFakeEntity("ZDead", ent_num=43, is_player=False)
            z_dead.set_field("health", 0)
            z_dead.set_field("origin", GscArray([320, 0, 0]))
            ticked_dead = gsc.call(
                BZ_ELEM_STOCK_MOD, "bz_flame_apply_dot_tick", z_dead, player, 229, False, False, 1
            )
            self.assertFalse(ticked_dead)
            self.assertEqual(z_dead.damage_events, [])

            # Respects end_game: once bz_on_end_game runs, DOT ticks stop immediately
            gsc.call(BZ_HOOKS_MOD, "bz_on_end_game")
            z_post_end = ElemStockFakeEntity("ZPostEnd", ent_num=44, is_player=False)
            z_post_end.set_field("health", 1045)
            z_post_end.set_field("origin", GscArray([320, 0, 0]))
            gsc.call_on(z_post_end, BZ_ELEM_STOCK_MOD, "bz_flame_burn_dot_thread", player, 10, 1045, False, False)
            self.assertEqual(z_post_end.damage_events, [])
            self.assertEqual(z_post_end.get_field("health"), 1045)

    def test_flame_dot_respects_acid_brittle_and_never_overwrites_cryo_or_acid_move_rate(self) -> None:
        _dvars, gsc, player = _setup_elem_stock_env(map_name="nazi_zombie_factory")
        gsc.sim_time_ms = 5000

        # 1. Acid brittle (1.5x) amplifies Flamethrower burn DOT tick without overwriting Acid slow (0.60)
        z_acid = ElemStockFakeEntity("ZAcidBurn", ent_num=60, is_player=False)
        z_acid.set_field("health", 2000)
        z_acid.set_field("origin", GscArray([250, 0, 0]))
        z_acid.set_field("bz_acid_slow_until", 9000)
        z_acid.set_field("bz_acid_brittle_until", 9000)
        z_acid.set_field("bz_flame_dot_active", True)

        ok = gsc.call(BZ_ELEM_STOCK_MOD, "bz_flame_apply_dot_tick", z_acid, player, 200, False, False, 1)
        self.assertTrue(ok)
        self.assertEqual(z_acid.damage_events[0]["damage"], 300)  # 200 * 1.50 Acid Brittle
        self.assertAlmostEqual(float(z_acid.get_field("moveplaybackrate")), 0.60, places=6)

        # 2. Cryo freeze (0.01 + ignoreall=true) is NEVER overwritten by Flamethrower burn (0.80)
        #    and MOD_BURNED does NOT shatter Cryo freeze!
        z_cryo = ElemStockFakeEntity("ZCryoBurn", ent_num=61, is_player=False)
        z_cryo.set_field("health", 2000)
        z_cryo.set_field("origin", GscArray([250, 0, 0]))
        z_cryo.set_field("bz_is_frozen", True)
        z_cryo.set_field("bz_cryo_frozen_until", 9000)
        z_cryo.set_field("bz_flame_dot_active", True)

        ok2 = gsc.call(BZ_ELEM_STOCK_MOD, "bz_flame_apply_dot_tick", z_cryo, player, 200, False, False, 1)
        self.assertTrue(ok2)
        self.assertEqual(z_cryo.damage_events[0]["damage"], 200)  # no shatter on MOD_BURNED
        self.assertTrue(z_cryo.get_field("bz_is_frozen"))
        self.assertTrue(z_cryo.get_field("ignoreall"))
        self.assertAlmostEqual(float(z_cryo.get_field("moveplaybackrate")), 0.01, places=6)

        # 3. Overlapping stuns: Tesla stun expiring while Second Chance stun is still active keeps 0.01 & ignoreall=true
        z_overlap = ElemStockFakeEntity("ZOverlap", ent_num=62, is_player=False)
        z_overlap.set_field("health", 2000)
        z_overlap.set_field("origin", GscArray([200, 0, 0]))
        z_overlap.set_field("bz_tesla_stun_until", 8500)
        z_overlap.set_field("bz_tesla_stunned", True)
        z_overlap.set_field("bz_second_chance_stun_until", 11000)
        gsc.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", z_overlap)
        self.assertAlmostEqual(float(z_overlap.get_field("moveplaybackrate")), 0.01, places=6)
        self.assertTrue(z_overlap.get_field("ignoreall"))

        # Tesla timer finishes at t=8500 while Second Chance lasts until 11000 -> MUST stay stunned!
        gsc.sim_time_ms = 8500
        gsc.call_on(z_overlap, BZ_ELEM_STOCK_MOD, "bz_elem_stock_tesla_stun_timer", 3.5, 8500)
        self.assertFalse(z_overlap.get_field("bz_tesla_stunned"))
        self.assertTrue(z_overlap.get_field("bz_stunned"))
        self.assertTrue(z_overlap.get_field("ignoreall"))
        self.assertAlmostEqual(float(z_overlap.get_field("moveplaybackrate")), 0.01, places=6)

        # Once Second Chance expires too (at t=11000), restores cleanly to base rate 1.0 & ignoreall=false
        gsc.sim_time_ms = 11000
        gsc.call(BZ_HOOKS_MOD, "bz_recompute_zombie_move_rate", z_overlap)
        self.assertFalse(z_overlap.get_field("bz_stunned"))
        self.assertFalse(z_overlap.get_field("ignoreall"))
        self.assertAlmostEqual(float(z_overlap.get_field("moveplaybackrate")), 1.0, places=6)


class TestClassicModeIsolationAndWaw17Compliance(unittest.TestCase):
    """Slice 4: Strict Classic Mode / bz_elements_enabled 0 noop + WaW 1.7 syntax & endon safety."""

    def test_classic_mode_and_elements_disabled_are_strict_noops(self) -> None:
        for bz_on, elem_on in ((False, True), (True, False), (False, False)):
            _dvars, gsc, player = _setup_elem_stock_env(
                map_name="nazi_zombie_factory",
                bz_enabled=bz_on,
                elements_enabled=elem_on,
                perks_enabled=False,
                classes_enabled=False,
            )
            gsc.emitted_events.clear()
            gsc.level.set_field("round_number", 10)
            gsc.level.set_field("zombie_health", 1045)
            player.set_field("origin", GscArray([0, 0, 0]))
            gsc.call(BZ_STATE_MOD, "bz_try_buy_apex", player, "blast_shield")

            z = ElemStockFakeEntity("Z1", ent_num=50, is_player=False)
            z.set_field("health", 1045)
            z.set_field("origin", GscArray([64, 0, 0]))
            gsc.ai_enemies.append(z)

            # Flamethrower hit stays untouched (30 dmg, no DOT, no events)
            dmg = gsc.call(
                BZ_HOOKS_MOD,
                "bz_actor_damage_dispatch",
                z,
                player,
                player,
                30,
                0,
                "MOD_BURNED",
                "m2_flamethrower_zombie",
                z.get_field("origin"),
                GscArray([1, 0, 0]),
                "torso_upper",
                0,
            )
            self.assertEqual(dmg, 30)
            self.assertNotEqual(z.get_field("bz_flame_dot_active"), True)

            # Wunderwaffe chain-hit & self-shock immunity are complete noops
            self.assertEqual(gsc.call(BZ_ELEM_STOCK_MOD, "bz_tesla_on_chain_hit", z, player), 0)
            self.assertFalse(gsc.call(BZ_ELEM_STOCK_MOD, "bz_tesla_is_self_shock_immune", player))
            self.assertNotEqual(z.get_field("bz_tesla_stunned"), True)

            # Wunderwaffe self-splash in player_damage stays untouched
            splash = gsc.call_on(
                player,
                BZ_HOOKS_MOD,
                "bz_player_damage_override",
                player,
                player,
                75,
                0,
                "MOD_PROJECTILE_SPLASH",
                "tesla_gun",
                GscArray([0, 0, 0]),
                GscArray([0, 0, 0]),
                "none",
                0,
                0,
            )
            self.assertEqual(splash, 75)
            self.assertEqual(gsc.emitted_events, [])

    def test_bz_elem_stock_is_strictly_waw17_compliant_and_zero_fx(self) -> None:
        source = BZ_ELEM_STOCK_PATH.read_text(encoding="latin1")

        # ASCII-only compliance
        non_ascii = [ch for ch in source if ord(ch) > 126 or (ord(ch) < 32 and ch not in "\t\r\n")]
        self.assertEqual(non_ascii, [], f"Non-ASCII chars in _bz_elem_stock.gsc: {non_ascii!r}")

        # Zero foreach and zero LoadFX / PlayFX in code (ignoring comments)
        code_only = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
        code_only = re.sub(r"//[^\n]*", "", code_only)
        self.assertNotRegex(code_only, r"\bforeach\b")
        self.assertNotRegex(code_only, r"\bLoadFX\s*\(")
        self.assertNotRegex(code_only, r"\bPlayFX\s*\(")

        # Full parse via WaW 1.7 parser + endon thread-scope safety audit
        tokens = tokenize(source, filename=str(BZ_ELEM_STOCK_PATH))
        funcs = BzGscParser(tokens, filename=str(BZ_ELEM_STOCK_PATH)).parse_module()

        allowed_endon_threads = {
            "bz_elem_stock_tesla_stun_timer",
            "bz_flame_burn_dot_thread",
        }
        for fn_key, fn_def in funcs.items():
            has_endon = _ast_contains_method_call(fn_def.body, "endon")
            if has_endon:
                self.assertIn(
                    fn_key,
                    allowed_endon_threads,
                    f"Sync-callable function {fn_def.name}() must NOT contain endon()",
                )


if __name__ == "__main__":
    unittest.main()
