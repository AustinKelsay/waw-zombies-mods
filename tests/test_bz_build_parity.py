"""Offline contracts for the Base Zombies co-op build fingerprint."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import call, patch
from zipfile import ZipFile

from tests.gsc_runtime import FakeDvarStore, GscRuntime, UNDEFINED
from tests.test_bz_hooks_and_build import BZ_HOOKS_MOD, MOD_ROOT, BzGscRuntime, FakeEntity

import build_mod
import verify_hud_menus


VERSION_MODULE = "maps/_bz_version"
VERSION_PATH = Path(f"{VERSION_MODULE}.gsc")
VERSION_ENTRY = f"rawfile,{VERSION_PATH.as_posix()}"


class TestBzBuildStamp(unittest.TestCase):
    def test_rendered_version_getters_execute_as_ascii_gsc(self) -> None:
        source = build_mod.render_bz_version_gsc("0.9.0", "abc1234")
        self.assertTrue(source.isascii())
        self.assertNotRegex(source, r"(?i)\b(?:foreach|endon|wait|notifyoncommand|setorigin)\b")
        with TemporaryDirectory() as tmp:
            mod_root = Path(tmp)
            module_path = mod_root / VERSION_PATH
            module_path.parent.mkdir()
            module_path.write_text(source, encoding="ascii")
            runtime = GscRuntime(mod_root)
            self.assertEqual(runtime.call(VERSION_MODULE, "bz_get_build_version"), "0.9.0")
            self.assertEqual(runtime.call(VERSION_MODULE, "bz_get_build_commit"), "abc1234")
            self.assertEqual(runtime.call(VERSION_MODULE, "bz_get_build_id"), "0.9.0-abc1234")
        fallback = GscRuntime(MOD_ROOT)
        self.assertTrue((MOD_ROOT / VERSION_PATH).read_bytes().isascii())
        self.assertEqual(fallback.call(VERSION_MODULE, "bz_get_build_version"), "0.9.0")
        self.assertEqual(fallback.call(VERSION_MODULE, "bz_get_build_commit"), "dev")
        self.assertEqual(fallback.call(VERSION_MODULE, "bz_get_build_id"), "0.9.0-dev")

    def test_short_sha_uses_repository_and_falls_back_on_bad_git_output(self) -> None:
        git_outputs = ((b"a1B2_c-3\n", "a1B2_c-3"), (b"", "dev"), (b"abc;def", "dev"), (b"\xff", "dev"))
        for output, expected in git_outputs:
            with (
                self.subTest(output=output),
                patch.object(build_mod.subprocess, "check_output", side_effect=[output, b""]) as git,
            ):
                self.assertEqual(build_mod.resolve_git_short_sha(MOD_ROOT.parent), expected)
                self.assertEqual(git.call_args_list[0].args[0], ["git", "rev-parse", "--short", "HEAD"])
                self.assertEqual(git.call_args_list[0].kwargs["cwd"], MOD_ROOT.parent)

        with patch.object(
            build_mod.subprocess,
            "check_output",
            side_effect=[b"abc1234\n", b" M mod/maps/_bz_perks.gsc\n"],
        ):
            self.assertEqual(build_mod.resolve_git_short_sha(MOD_ROOT.parent), "abc1234-dirty")

        for error in (FileNotFoundError(), subprocess.CalledProcessError(128, "git")):
            with (
                self.subTest(error=type(error)),
                patch.object(build_mod.subprocess, "check_output", side_effect=error),
            ):
                self.assertEqual(build_mod.resolve_git_short_sha(MOD_ROOT.parent), "dev")

    def test_staging_and_iwd_use_stamp_without_editing_tracked_fallback(self) -> None:
        tracked_version = MOD_ROOT / VERSION_PATH
        original = tracked_version.read_bytes()
        lobby_path = Path("ui/bz_menus.inc")
        original_lobby = (MOD_ROOT / lobby_path).read_bytes()
        self.assertIn(b'"BUILD: 0.9.0-dev"', original_lobby)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Isolate Steam extraction and menu patching from the real staging and packaging.
            with (
                patch.object(build_mod, "STOCK_MAPS", ()),
                patch.object(build_mod, "extract_stock_script", return_value=b""),
                patch.object(build_mod, "try_extract_stock_script", return_value=None),
                patch.object(build_mod, "inject_zombiemode_score_hooks", return_value=b""),
                patch.object(build_mod, "inject_laststand_hooks", return_value=b""),
                patch("verify_hud_menus.stage_patched_menus"),
                patch.object(build_mod, "apply_bz_menu_patches"),
                patch.object(build_mod, "resolve_git_short_sha", return_value="abc1234") as resolve_sha,
                patch.object(build_mod, "DIST_DIR", root / "dist"),
            ):
                staged = build_mod.stage_mod_files(root / "tools", root / "steam")
                iwd = build_mod.build_iwd(staged)

            resolve_sha.assert_called_once_with(MOD_ROOT.parent)
            staged_version = (staged / VERSION_PATH).read_bytes()
            self.assertNotEqual(staged_version, original)
            self.assertEqual(tracked_version.read_bytes(), original)
            self.assertEqual(GscRuntime(staged).call(VERSION_MODULE, "bz_get_build_id"), "0.9.0-abc1234")
            staged_lobby = (staged / lobby_path).read_text(encoding="ascii")
            self.assertIn('"BUILD: 0.9.0-abc1234"', staged_lobby)
            self.assertNotIn('"BUILD: 0.9.0-dev"', staged_lobby)
            self.assertEqual(verify_hud_menus.validate_menu_braces(staged_lobby, filename=lobby_path.name), [])
            self.assertEqual((MOD_ROOT / lobby_path).read_bytes(), original_lobby)
            self.assertEqual((staged / "mod.csv").read_text().splitlines().count(VERSION_ENTRY), 1)
            with ZipFile(iwd) as archive:
                self.assertEqual(archive.read(VERSION_PATH.as_posix()), staged_version)

    def test_manifest_includes_version_once_with_zero_fx(self) -> None:
        manifest = (MOD_ROOT / "mod.csv").read_text(encoding="ascii")
        self.assertEqual(manifest.splitlines().count(VERSION_ENTRY), 1)
        staged_paths = [VERSION_PATH.as_posix(), r"maps\_bz_version.gsc"]
        self.assertEqual(build_mod.generate_staged_mod_csv(manifest, staged_paths), manifest)
        without_version = manifest.replace(f"{VERSION_ENTRY}\n", "")
        generated = build_mod.generate_staged_mod_csv(without_version, staged_paths)
        self.assertEqual(generated, without_version + f"{VERSION_ENTRY}\n")
        self.assertNotRegex(generated, r"(?im)^\s*fx\s*,")


class TestBzBuildParityHooks(unittest.TestCase):
    def setUp(self) -> None:
        self.dvars = FakeDvarStore()
        self.runtime = BzGscRuntime(MOD_ROOT, self.dvars)
        self.host = FakeEntity("Host", ent_num=0)
        self.client = FakeEntity("Client", ent_num=1)
        self.runtime.players.extend((self.host, self.client))

    def test_classic_mode_has_no_build_writes_telemetry_or_player_prints(self) -> None:
        self.dvars.set("bz_enabled", "0")
        with patch.object(self.dvars, "set", wraps=self.dvars.set) as write_dvar:
            self.runtime.call(BZ_HOOKS_MOD, "bz_pre_init")
            self.runtime.call(BZ_HOOKS_MOD, "bz_init")
            self.runtime.call(BZ_HOOKS_MOD, "bz_on_player_spawned", self.host)
            self.runtime.call(BZ_HOOKS_MOD, "bz_on_end_game")
        write_dvar.assert_not_called()
        self.assertEqual(self.runtime.emitted_events, [])
        self.assertEqual(self.runtime.player_prints, [])
        self.assertIs(self.host.get_field("bz_build_parity_announced"), UNDEFINED)
        self.assertNotIn("bz_build_id", self.host.client_dvars)
        self.assertNotIn("bz_host_build_id", self.host.client_dvars)

    def test_enabled_announces_once_per_player_per_match(self) -> None:
        self.dvars.set("bz_enabled", "1")
        with patch.object(self.dvars, "set", wraps=self.dvars.set) as write_dvar:
            self.runtime.call(BZ_HOOKS_MOD, "bz_init")
            self.runtime.call(BZ_HOOKS_MOD, "bz_init")
        self.assertEqual(self.dvars.get("bz_build_id"), "0.9.0-dev")
        build_writes = [write for write in write_dvar.call_args_list if write.args[0] == "bz_build_id"]
        self.assertEqual(build_writes, [call("bz_build_id", "0.9.0-dev")])

        for player in (self.host, self.host, self.client, self.client):
            self.runtime.call(BZ_HOOKS_MOD, "bz_on_player_spawned", player)
        self.runtime.call(BZ_HOOKS_MOD, "bz_on_player_revived", self.host, self.client)
        self.assertEqual(
            [line for line in self.runtime.emitted_events if line.startswith("BZ_EVENT|BUILD_PARITY|")],
            [
                "BZ_EVENT|BUILD_PARITY|version=0.9.0;commit=dev;build_id=0.9.0-dev;player=Host;map=nazi_zombie_factory",
                "BZ_EVENT|BUILD_PARITY|version=0.9.0;commit=dev;build_id=0.9.0-dev;player=Client;map=nazi_zombie_factory",
            ],
        )
        banner = "Base Zombies v0.9.0 (dev) - Co-op: all players must share mod.ff + waw_gauntlet.iwd"
        self.assertEqual(self.runtime.player_prints, [(self.host, banner), (self.client, banner)])
        for player in (self.host, self.client):
            self.assertEqual(player.client_dvars.get("bz_build_id"), "0.9.0-dev")
            self.assertEqual(player.client_dvars.get("bz_host_build_id"), "0.9.0-dev")

        self.runtime.call(BZ_HOOKS_MOD, "bz_on_end_game")
        for player in self.runtime.players:
            self.assertIs(player.get_field("bz_build_parity_announced"), UNDEFINED)
            self.assertEqual(player.client_dvars.get("bz_host_build_id"), "")
        next_match = BzGscRuntime(MOD_ROOT, self.dvars)
        next_match.players.extend(self.runtime.players)
        next_match.call(BZ_HOOKS_MOD, "bz_init")
        next_match.call(BZ_HOOKS_MOD, "bz_on_player_spawned", self.host)
        self.assertEqual(next_match.player_prints, [(self.host, banner)])

    def test_parity_log_keeps_non_ascii_and_delimiters_out_of_player_field(self) -> None:
        self.dvars.set("bz_enabled", "1")
        self.client.set_field("playername", "Caf\xe9;|=\n")
        self.runtime.call(BZ_HOOKS_MOD, "bz_init")
        self.runtime.call(BZ_HOOKS_MOD, "bz_on_player_spawned", self.client)
        self.assertIn(
            "BZ_EVENT|BUILD_PARITY|version=0.9.0;commit=dev;build_id=0.9.0-dev;player=Caf_____;map=nazi_zombie_factory",
            self.runtime.emitted_events,
        )
