#!/usr/bin/env python3
"""Offline unit tests for custom Phase 2 weapon 3D models, TGA textures, GDT, and build_mod wiring."""

from __future__ import annotations

import math
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_mod  # noqa: E402
import generate_bz_weapon_models as bz_models  # noqa: E402


class TestCustomWeaponModelGenerator(unittest.TestCase):
    def test_all_10_custom_meshes_are_valid_xmodel_export_v6(self) -> None:
        meshes = bz_models.build_all_meshes()
        self.assertEqual([m.name for m in meshes], list(bz_models.ALL_CUSTOM_XMODELS))

        known_materials = set(bz_models.ALL_CUSTOM_MATERIALS)
        for mesh in meshes:
            self.assertGreaterEqual(len(mesh.verts), 40, f"{mesh.name} has too few vertices")
            self.assertLessEqual(len(mesh.verts), 4000, f"{mesh.name} exceeds WaW 1.7 safe viewmodel vertex budget")
            self.assertGreaterEqual(len(mesh.faces), 40, f"{mesh.name} has too few faces")
            self.assertGreaterEqual(len(mesh.materials), 2, f"{mesh.name} should use multi-material detailing")
            for mat_name in mesh.materials:
                self.assertIn(mat_name, known_materials)

            # Verify every vertex has finite coordinates and a valid bone index.
            for pos, bone_idx in mesh.verts:
                self.assertTrue(all(math.isfinite(c) for c in pos))
                self.assertGreaterEqual(bone_idx, 0)
                self.assertLess(bone_idx, len(mesh.bones))

            # Verify every face references valid vertices/materials with unit normals.
            for face in mesh.faces:
                self.assertGreaterEqual(face.mat_idx, 0)
                self.assertLess(face.mat_idx, len(mesh.materials))
                for vi in (face.v0, face.v1, face.v2):
                    self.assertGreaterEqual(vi, 0)
                    self.assertLess(vi, len(mesh.verts))
                for n in (face.n0, face.n1, face.n2):
                    mag = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
                    self.assertAlmostEqual(mag, 1.0, places=3)

            exported = mesh.to_xmodel_export()
            self.assertIn("MODEL\nVERSION 6\n", exported)
            self.assertIn(f"NUMBONES {len(mesh.bones)}\n", exported)
            self.assertIn(f"NUMVERTS {len(mesh.verts)}\n", exported)
            self.assertIn(f"NUMFACES {len(mesh.faces)}\n", exported)
            self.assertIn(f"NUMMATERIALS {len(mesh.materials)}\n", exported)

    def test_viewmodel_bone_hierarchies_match_exact_waw_donors(self) -> None:
        by_name = {m.name: m for m in bz_models.build_all_meshes()}

        acid_bones = [b.name for b in by_name["viewmodel_bz_acid_sprayer"].bones]
        self.assertEqual(acid_bones, ["j_gun", "tag_flash"])

        cryo_bones = [b.name for b in by_name["viewmodel_bz_cryo_cannon"].bones]
        self.assertEqual(cryo_bones[0], "j_gun")
        for req in ("j_bolt", "j_bulb_1", "j_bulb_2", "j_bulb_3", "tag_flash"):
            self.assertIn(req, cryo_bones)
        # Animated cryo vials must actually be skinned to j_bulb_1/2/3!
        cryo_used_bones = {b_idx for _, b_idx in by_name["viewmodel_bz_cryo_cannon"].verts}
        self.assertTrue({2, 3, 4} <= cryo_used_bones, "Cryo vials should bind to j_bulb_1/2/3")

        xbow_bones = [b.name for b in by_name["viewmodel_bz_multi_crossbow"].bones]
        self.assertEqual(xbow_bones[0], "j_gun")
        for req in ("tag_scope", "tag_flash", "tag_iron_sights"):
            self.assertIn(req, xbow_bones)
        # Crossbow prods must sweep wide in Y (+/- 10u+) to differentiate from any rifle!
        xbow_ys = [p[1] for p, _ in by_name["viewmodel_bz_multi_crossbow"].verts]
        self.assertLess(min(xbow_ys), -10.0)
        self.assertGreater(max(xbow_ys), 10.0)

        boom_bones = [b.name for b in by_name["viewmodel_bz_blade_boomerang"].bones]
        self.assertEqual(boom_bones[0], "j_gun")
        self.assertIn("tag_flash", boom_bones)
        # Airborne boomerang must lie in the YZ plane (10.15u radius, ~17.0u YZ span, thin X) so RotateRoll spins
        # the 3 wings squarely facing the thrower with zero edge-on frames (O18/F19/O19).
        air_pts = [p for p, _ in by_name["bz_boomerang_blade_air"].verts]
        xs = [p[0] for p in air_pts]
        ys = [p[1] for p in air_pts]
        zs = [p[2] for p in air_pts]
        self.assertLess(max(xs) - min(xs), 2.0)
        self.assertGreater(max(ys) - min(ys), 16.5)
        self.assertGreater(max(zs) - min(zs), 16.5)

    def test_generate_all_assets_writes_valid_tgas_and_gdt_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            r1 = Path(tmp1)
            r2 = Path(tmp2)
            s1 = bz_models.generate_all_assets(r1, tex_size=32)
            s2 = bz_models.generate_all_assets(r2, tex_size=32)
            self.assertEqual(s1["materials"], list(bz_models.ALL_CUSTOM_MATERIALS))
            self.assertEqual(s1["xmodels"], list(bz_models.ALL_CUSTOM_XMODELS))
            self.assertEqual(s1["images"], s2["images"])

            # Verify deterministic GDT & valid 32-bit uncompressed TGA headers
            gdt1 = (r1 / "source_data" / bz_models.GDT_FILENAME).read_text(encoding="ascii")
            gdt2 = (r2 / "source_data" / bz_models.GDT_FILENAME).read_text(encoding="ascii")
            self.assertEqual(gdt1, gdt2)
            for mtl in bz_models.ALL_CUSTOM_MATERIALS:
                self.assertIn(f'"{mtl}" ( "material.gdf" )', gdt1)
            for xm in bz_models.ALL_CUSTOM_XMODELS:
                self.assertIn(f'"{xm}" ( "xmodel.gdf" )', gdt1)

            tgas = sorted((r1 / "texture_assets" / bz_models.ASSET_SUBDIR).glob("*.tga"))
            self.assertGreaterEqual(len(tgas), len(bz_models.ALL_CUSTOM_MATERIALS))
            for tga in tgas:
                raw = tga.read_bytes()
                self.assertEqual(len(raw), 18 + 32 * 32 * 4)
                img_type = raw[2]
                width, height, bpp = struct.unpack_from("<HHB", raw, 12)
                self.assertEqual((img_type, width, height, bpp), (2, 32, 32, 32))

    def test_build_mod_wires_custom_models_and_iwd_images(self) -> None:
        specs = {name: (cands, overrides) for name, cands, overrides in build_mod.BZ_ELEMENT_WEAPON_SPECS}
        for weap_name, viewmodel in bz_models.CUSTOM_WEAPON_VIEWMODELS.items():
            self.assertIn(weap_name, specs)
            self.assertEqual(specs[weap_name][1]["gunModel"], viewmodel)
            self.assertEqual(specs[weap_name][1]["worldModel"], bz_models.CUSTOM_WEAPON_WORLDMODELS[weap_name])

        item_specs = {name: (cands, overrides) for name, cands, overrides in build_mod.BZ_SPECIAL_ITEM_WEAPON_SPECS}
        for weap_name, viewmodel in bz_models.CUSTOM_SPECIAL_WEAPON_VIEWMODELS.items():
            self.assertIn(weap_name, item_specs)
            self.assertEqual(item_specs[weap_name][1]["inventoryType"], "item")
            self.assertEqual(item_specs[weap_name][1]["gunModel"], viewmodel)
            self.assertEqual(item_specs[weap_name][1]["worldModel"], bz_models.CUSTOM_SPECIAL_WEAPON_WORLDMODELS[weap_name])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage = root / "stage"
            (stage / "maps").mkdir(parents=True)
            (stage / "maps" / "_bz_dummy.gsc").write_text("// ok\n", encoding="ascii")
            raw_img = root / "tools" / "raw" / "images"
            raw_img.mkdir(parents=True)
            (raw_img / "bz_cryo_hull_c.iwi").write_bytes(b"IWi\x06test")
            (raw_img / "~bz_cryo_hull_s-rgb&bz_cryo_h~51c58a90.iwi").write_bytes(b"IWi\x06spec")
            (raw_img / "stock_ignore.iwi").write_bytes(b"IWi\x06ignore")

            staged = build_mod.stage_custom_weapon_images(root / "tools", stage)
            self.assertEqual(
                staged,
                [
                    "images/bz_cryo_hull_c.iwi",
                    "images/~bz_cryo_hull_s-rgb&bz_cryo_h~51c58a90.iwi",
                ],
            )

            orig_dist = build_mod.DIST_DIR
            try:
                build_mod.DIST_DIR = root / "dist"
                iwd_path = build_mod.build_iwd(stage)
                with ZipFile(iwd_path, "r") as zf:
                    names = set(zf.namelist())
                self.assertIn("images/bz_cryo_hull_c.iwi", names)
                self.assertIn("images/~bz_cryo_hull_s-rgb&bz_cryo_h~51c58a90.iwi", names)
                self.assertNotIn("images/stock_ignore.iwi", names)
            finally:
                build_mod.DIST_DIR = orig_dist

    def test_all_exported_faces_have_consistent_clockwise_waw_winding_and_planar_caps(self) -> None:
        # 1. Every shipped mesh must have 100% consistent exported CW winding vs declared normals (O1)
        tri_re = re.compile(
            r"VERT\s+(\d+)\nNORMAL\s+([^\n]+)\nCOLOR[^\n]+\nUV[^\n]+\n"
            r"VERT\s+(\d+)\nNORMAL\s+([^\n]+)\nCOLOR[^\n]+\nUV[^\n]+\n"
            r"VERT\s+(\d+)\nNORMAL\s+([^\n]+)\nCOLOR[^\n]+\nUV[^\n]+",
            re.MULTILINE,
        )
        vert_re = re.compile(r"^VERT\s+(\d+)\nOFFSET\s+([^\n]+)", re.MULTILINE)
        for mesh in bz_models.build_all_meshes():
            text = mesh.to_xmodel_export()
            verts = {
                int(m.group(1)): tuple(float(c) for c in m.group(2).split(","))
                for m in vert_re.finditer(text)
            }
            tris = list(tri_re.finditer(text))
            self.assertEqual(len(tris), len(mesh.faces))
            flipped = 0
            for m in tris:
                p0, p1, p2 = verts[int(m.group(1))], verts[int(m.group(3))], verts[int(m.group(5))]
                n0 = tuple(float(c) for c in m.group(2).split())
                # Exported WaW DirectX9 CW winding: (p1-p0) x (p2-p0) points OPPOSITE outward normal n0
                e1 = bz_models.v_sub(p1, p0)
                e2 = bz_models.v_sub(p2, p0)
                if bz_models.v_dot(bz_models.v_cross(e1, e2), n0) >= 0.0:
                    flipped += 1
            self.assertEqual(flipped, 0, f"{mesh.name} has {flipped} faces with inconsistent winding")

        # 2. Prism side walls & caps all match outward normals and caps use distinct planar UVs (S2/A3)
        prism = bz_models.MeshBuilder("test_prism", bz_models.BONES_RIGID)
        prism.add_tapered_prism("mtl_bz_cryo_hull", (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), 1.0, 1.0, sides=8)
        for f in prism.faces:
            p0, p1, p2 = (prism.verts[i][0] for i in (f.v0, f.v1, f.v2))
            geo_n = bz_models.v_cross(bz_models.v_sub(p1, p0), bz_models.v_sub(p2, p0))
            self.assertGreater(bz_models.v_dot(geo_n, f.n0), 0.0)
        cap_uv_sets = {(f.uv0, f.uv1, f.uv2) for f in prism.faces[16:24]}
        self.assertEqual(len(cap_uv_sets), 8)

        # 3. Swept blades wind all 60 side tris outward and cap root & tip ends (O1/F6)
        blade = bz_models.MeshBuilder("test_blade", bz_models.BONES_RIGID)
        spine = [(float(i), 0.0, 0.0) for i in range(6)]
        blade.add_swept_blade("mtl_bz_blade_steel", "mtl_bz_blade_glow", spine, [2.0] * 6, [0.5] * 6)
        self.assertEqual(len(blade.faces), 72)  # 60 side tris + 12 root/tip cap tris
        for f in blade.faces[:60]:
            p0, p1, p2 = (blade.verts[i][0] for i in (f.v0, f.v1, f.v2))
            geo_n = bz_models.v_cross(bz_models.v_sub(p1, p0), bz_models.v_sub(p2, p0))
            c = tuple((p0[k] + p1[k] + p2[k]) / 3.0 for k in range(3))
            self.assertGreater(bz_models.v_dot(geo_n, bz_models.v_sub(c, (c[0], 0.0, 0.0))), 0.0)

    def test_cryo_ads_sightline_clear_crossbow_bolts_rigged_and_spec_calibrated(self) -> None:
        by_name = {m.name: m for m in bz_models.build_all_meshes()}

        # Cryo Cannon ADS sightline ray along +X through holo-ring center (3.8, 0.0, 5.10) hits 0 triangles (S3)
        cryo = by_name["viewmodel_bz_cryo_cannon"]
        ray_o = (4.0, 0.0, 5.10)
        ray_d = (1.0, 0.0, 0.0)
        hits = 0
        for f in cryo.faces:
            v0, v1, v2 = (cryo.verts[i][0] for i in (f.v0, f.v1, f.v2))
            e1, e2 = bz_models.v_sub(v1, v0), bz_models.v_sub(v2, v0)
            pvec = bz_models.v_cross(ray_d, e2)
            det = bz_models.v_dot(e1, pvec)
            if abs(det) < 1e-8:
                continue
            tvec = bz_models.v_sub(ray_o, v0)
            u = bz_models.v_dot(tvec, pvec) / det
            if u < 0.0 or u > 1.0:
                continue
            qvec = bz_models.v_cross(tvec, e1)
            v = bz_models.v_dot(ray_d, qvec) / det
            if v < 0.0 or u + v > 1.0:
                continue
            t = bz_models.v_dot(e2, qvec) / det
            if t > 0.0:
                hits += 1
        self.assertEqual(hits, 0, "Cryo Cannon ADS sightline should be unobstructed")

        # Multi-Crossbow ADS scope sightlines (z=3.68..4.60) must hit 0 front-facing triangles (O10)
        xbow = by_name["viewmodel_bz_multi_crossbow"]
        for eye_y, eye_z in ((-0.18, 3.68), (-0.18, 4.10), (-0.18, 4.28), (0.11, 4.28), (-0.18, 4.40), (-0.18, 4.60)):
            xbow_hits = 0
            o_pt = (-6.0, eye_y, eye_z)
            for f in xbow.faces:
                v0, v1, v2 = (xbow.verts[i][0] for i in (f.v0, f.v1, f.v2))
                e1, e2 = bz_models.v_sub(v1, v0), bz_models.v_sub(v2, v0)
                if bz_models.v_dot(bz_models.v_cross(e1, e2), ray_d) >= 0.0:
                    continue
                pvec = bz_models.v_cross(ray_d, e2)
                det = bz_models.v_dot(e1, pvec)
                if abs(det) < 1e-8:
                    continue
                tvec = bz_models.v_sub(o_pt, v0)
                u = bz_models.v_dot(tvec, pvec) / det
                if u < 0.0 or u > 1.0:
                    continue
                qvec = bz_models.v_cross(tvec, e1)
                v = bz_models.v_dot(ray_d, qvec) / det
                if v < 0.0 or u + v > 1.0:
                    continue
                if bz_models.v_dot(e2, qvec) / det > 0.0:
                    xbow_hits += 1
            self.assertEqual(xbow_hits, 0, f"Crossbow ADS blocked at y={eye_y}, z={eye_z}")

        # Multi-Crossbow binds its 3 loaded bolts + cassette to j_clip (bone_idx=2) so reload animates them (S6)
        used_bones = {xbow.bones[b_idx].name for _, b_idx in xbow.verts}
        self.assertIn("j_clip", used_bones)

        # World models expose per-weapon tag_flash matching each weapon's actual emitter (F9/A7)
        expected_world_flash = {
            "world_bz_acid_sprayer": (17.71, 0.0, -0.29),
            "world_bz_cryo_cannon": (41.0, 0.0, 2.16),
            "world_bz_multi_crossbow": (26.67, -0.12, 2.76),
            "world_bz_blade_boomerang": (4.5, 0.0, 2.05),
        }
        for wm_name, exp_flash in expected_world_flash.items():
            wm_bones = by_name[wm_name].bones
            self.assertEqual([b.name for b in wm_bones], ["tag_origin", "tag_flash"])
            self.assertEqual(wm_bones[1].offset, exp_flash)

        # World-held and airborne boomerang blade radii stay closely proportional (S12/O14/F15)
        # and the world grip collar extends continuously into the scaled hub with zero gap (A13/S15).
        world_boom = by_name["world_bz_blade_boomerang"]
        air_boom = by_name["bz_boomerang_blade_air"]
        w_hub = (0.35 * 2.45, 0.0, 2.05 * 2.45)
        w_rad = max(math.dist(p, w_hub) for p, _ in world_boom.verts)
        a_rad = max(math.dist(p, (0.0, 0.0, 0.0)) for p, _ in air_boom.verts)
        self.assertLessEqual(a_rad / w_rad, 1.25)
        grip_top_z = max(world_boom.verts[i][0][2] for f in world_boom.faces[:120] for i in (f.v0, f.v1, f.v2))
        self.assertGreaterEqual(grip_top_z, w_hub[2] - 0.1, "World boomerang grip collar must reach the scaled hub")

        # Boomerang fireTime must exceed full GSC flight duration by 0.05s (2 * steps * step_dt + 0.05 = 1.15s)
        # so catch clip refill lands cleanly before the engine exits fireTime (F17/F21).
        boom_spec = next(ov for name, _c, ov in build_mod.BZ_ELEMENT_WEAPON_SPECS if name == "bz_blade_boomerang")
        gsc_src = (REPO_ROOT / "mod" / "maps" / "_bz_special_weapons.gsc").read_text(encoding="utf-8")
        m_steps = re.search(r"\bsteps\s*=\s*(\d+)\s*;", gsc_src)
        m_dt = re.search(r"\bstep_dt\s*=\s*([0-9.]+)\s*;", gsc_src)
        self.assertIsNotNone(m_steps)
        self.assertIsNotNone(m_dt)
        expected_flight_s = 2 * int(m_steps.group(1)) * float(m_dt.group(1))
        self.assertAlmostEqual(float(boom_spec["fireTime"]), expected_flight_s + 0.05, places=3)

        # Specular maps stay calibrated well below raw white to prevent WaW blue sky tint (F2/O9)
        for spec in bz_models.MATERIAL_SPECS:
            if spec.material_type == "model phong":
                self.assertLessEqual(max(spec.spec_rgb), 80, f"{spec.name} specular too bright: {spec.spec_rgb}")

    def test_northstar_wave1_budgets_silhouettes_and_kiosk_contracts(self) -> None:
        """Verify ADR-0007 / NORTHSTAR_SPEC.md v2.1 Wave 1 mesh budgets, bones, and 1945 silhouettes."""
        by_name = {m.name: m for m in bz_models.build_all_meshes()}

        # 1. Strict ADR-0007 / NORTHSTAR_SPEC.md vertex budgets across all 19 XMODELs
        for vm in list(bz_models.CUSTOM_WEAPON_VIEWMODELS.values()) + list(bz_models.CUSTOM_SPECIAL_WEAPON_VIEWMODELS.values()):
            self.assertLessEqual(len(by_name[vm].verts), 3500, f"{vm} exceeds 3,500 VM vert cap")
            self.assertLessEqual(len(by_name[vm].materials), 4, f"{vm} exceeds 4-material-slot cap")
        for wm in list(bz_models.CUSTOM_WEAPON_WORLDMODELS.values()) + list(bz_models.CUSTOM_SPECIAL_WEAPON_WORLDMODELS.values()):
            self.assertLessEqual(len(by_name[wm].verts), 1800, f"{wm} exceeds 1,800 WM vert cap")
            self.assertLessEqual(len(by_name[wm].materials), 4, f"{wm} exceeds 4-material-slot cap")
        self.assertLessEqual(len(by_name["bz_crossbow_bolt"].verts), 400)
        self.assertLessEqual(len(by_name["bz_boomerang_blade_air"].verts), 750)
        self.assertLessEqual(len(by_name["bz_portal_orb_air"].verts), 900)

        # 2. Acid Sprayer: low outboard-left Olivgruen tank (Z <= 2.0), no secondary right tank
        acid_vm = by_name["viewmodel_bz_acid_sprayer"]
        self.assertLessEqual(max(p[2] for p, _ in acid_vm.verts), 2.05)

        # 3. Cryo Cannon: flasks sit flush/above receiver underside (z >= -0.05) & bell radius <= 2.4u
        cryo_vm = by_name["viewmodel_bz_cryo_cannon"]
        bulb_zs = [p[2] for p, b in cryo_vm.verts if b in (2, 3, 4)]
        self.assertGreaterEqual(min(bulb_zs), 0.0, "Cryo Dewar flasks must stay flush/above receiver underside")

        # 4. Multi-Crossbow: right-side j_bolt cocking sled & ~11u bolt
        xbow_vm = by_name["viewmodel_bz_multi_crossbow"]
        used_xbow_bones = {xbow_vm.bones[b].name for _, b in xbow_vm.verts}
        self.assertIn("j_bolt", used_xbow_bones)
        bolt_xs = [p[0] for p, _ in by_name["bz_crossbow_bolt"].verts]
        self.assertLessEqual(max(bolt_xs) - min(bolt_xs), 12.0)

        # 5. Portal deployed anchor spans exact ~25u tip-to-tip (+-12.5u)
        orb_zs = [p[2] for p, _ in by_name["bz_portal_orb_air"].verts]
        self.assertAlmostEqual(max(orb_zs) - min(orb_zs), 25.0, delta=0.5)

        # 6. Station Kiosks: <=1,500 verts, z=-4..0 burial skirt, <=72u max height, distinct heights
        expected_kiosk_heights = {
            "bz_station_perks_kiosk": 70.0,
            "bz_station_class_kiosk": 58.0,
            "bz_station_arsenal_kiosk": 62.0,
            "bz_station_pap_kiosk": 68.0,
        }
        for kname, exp_h in expected_kiosk_heights.items():
            km = by_name[kname]
            self.assertLessEqual(len(km.verts), 1500, f"{kname} exceeds 1,500 vert cap")
            kzs = [p[2] for p, _ in km.verts]
            self.assertAlmostEqual(min(kzs), -4.0, delta=0.2, msg=f"{kname} missing z=-4..0 burial skirt")
            self.assertLessEqual(max(kzs), 72.0, f"{kname} exceeds 72u height cap")
            self.assertAlmostEqual(max(kzs), exp_h, delta=0.6, msg=f"{kname} height mismatch")

        # 7. Wintertarnung whitewash stays <=185 albedo (no glossy sci-fi white) & Boomerang glow is crimson (#e81e50)
        by_mat = {s.name: s for s in bz_models.MATERIAL_SPECS}
        self.assertLessEqual(max(by_mat["mtl_bz_cryo_hull"].accent_rgb), 185)
        self.assertEqual(by_mat["mtl_bz_blade_glow"].base_rgb, (232, 30, 80))
        self.assertEqual(by_mat["mtl_bz_acid_glow"].base_rgb, (104, 240, 48))
        self.assertEqual(by_mat["mtl_bz_xbow_glow"].base_rgb, (255, 176, 32))
        self.assertEqual(by_mat["mtl_bz_club_glow"].base_rgb, (255, 74, 18))

    def test_compile_cache_manifest_cleanup_and_exact_iwd_staging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = root / "tools"
            raw = tools / "raw"
            for sub in ("materials", "xmodel", "xmodelparts", "xmodelsurfs", "images"):
                (raw / sub).mkdir(parents=True)

            summary = bz_models.generate_all_assets(tools, tex_size=16)

            def fake_converter(cmd, **_kwargs):
                kind, name = cmd[3:5]
                if kind == "material":
                    (raw / "materials" / name).write_bytes(b"material-bin")
                    prefix = name.removeprefix("mtl_")
                    for stem in summary["images"]:
                        if stem.rsplit("_", 1)[0] == prefix and not stem.endswith("_g"):
                            fname = f"~{stem}-rgb&{prefix[:8]}~deadbeef.iwi" if stem.endswith("_s") else f"{stem}.iwi"
                            (raw / "images" / fname).write_bytes(b"IWi\x06bin")
                else:
                    (raw / "xmodel" / name).write_bytes(b"xmodel-bin")
                    (raw / "xmodelparts" / f"{name}0").write_bytes(b"parts-bin")
                    (raw / "xmodelsurfs" / f"{name}0").write_bytes(b"surfs-bin")
                return subprocess.CompletedProcess(cmd, 0, stdout="ok")

            # Unrelated similarly-named assets (including digit siblings, alt-gloss, and same-prefix different-hash specs)
            # must all survive untouched (A5/A6/A10/S8/S13).
            unrelated = raw / "xmodelsurfs" / f"{summary['xmodels'][0]}_different_project"
            unrelated.write_bytes(b"other-project")
            sibling_bolt = raw / "xmodelparts" / "bz_crossbow_bolt20"
            sibling_bolt.write_bytes(b"sibling-bolt2")
            alt_gloss = raw / "images" / "~bz_cryo_hull_s-rgb&altgloss~12345678.iwi"
            alt_gloss.write_bytes(b"alt-gloss")
            same_prefix_foreign = raw / "images" / "~bz_cryo_hull_s-rgb&bz_cryo_h~12345678.iwi"
            same_prefix_foreign.write_bytes(b"same-prefix-foreign")
            other_mat = raw / "materials" / "other_mod_asset"
            other_mat.write_bytes(b"other-mat")
            retired = raw / "images" / "bz_retired_design.iwi"
            retired.write_bytes(b"retired-iwi")
            stale_spec = raw / "images" / "~bz_cryo_hull_s-rgb&old.iwi"
            stale_spec.write_bytes(b"old-spec")

            with (
                patch.object(build_mod.bz_models, "generate_all_assets", wraps=lambda _r: summary) as gen_mock,
                patch.object(build_mod.subprocess, "run", side_effect=fake_converter) as run_mock,
            ):
                # 1. Cold compile runs converter and writes manifest
                build_mod.compile_custom_weapon_assets(tools, root, root)
                self.assertEqual(gen_mock.call_count, 1)
                self.assertEqual(run_mock.call_count, len(summary["materials"]) + len(summary["xmodels"]))
                self.assertTrue(unrelated.is_file())

                # 2. Warm cache hit skips BOTH generate_all_assets() AND converter.exe (F8)
                gen_mock.reset_mock()
                run_mock.reset_mock()
                build_mod.compile_custom_weapon_assets(tools, root, root)
                self.assertEqual(gen_mock.call_count, 0)
                self.assertEqual(run_mock.call_count, 0)

                # 3. Deleting xmodelsurfs or truncating a spec .iwi invalidates cache (A4/S7)
                (raw / "xmodelsurfs" / "bz_crossbow_bolt0").unlink()
                (raw / "images" / "~bz_cryo_hull_s-rgb&bz_cryo_~deadbeef.iwi").write_bytes(b"")
                build_mod.compile_custom_weapon_assets(tools, root, root)
                self.assertEqual(gen_mock.call_count, 1)
                self.assertGreater(run_mock.call_count, 0)
                self.assertTrue(unrelated.is_file())

            # 4. stage_custom_weapon_images stages strictly manifest-recorded images (excludes retired & stale)
            (raw / "images" / "~bz_cryo_hull_s-rgb&old.iwi").write_bytes(b"old-spec-added-later")
            stage = root / "stage"
            staged = build_mod.stage_custom_weapon_images(tools, stage)
            self.assertNotIn("images/bz_retired_design.iwi", staged)
            self.assertNotIn("images/~bz_cryo_hull_s-rgb&old.iwi", staged)
            self.assertNotIn("images/~bz_cryo_hull_s-rgb&altgloss~12345678.iwi", staged)
            self.assertNotIn("images/~bz_cryo_hull_s-rgb&bz_cryo_h~12345678.iwi", staged)
            self.assertIn("images/bz_cryo_hull_c.iwi", staged)
            self.assertIn("images/~bz_cryo_hull_s-rgb&bz_cryo_~deadbeef.iwi", staged)
            self.assertTrue(sibling_bolt.is_file())
            self.assertTrue(alt_gloss.is_file())
            self.assertTrue(same_prefix_foreign.is_file())

            # 5. Tampered manifest pointing at foreign asset never deletes it (S13) and failed reconvert invalidates cache (S11)
            import json
            mpath = build_mod._custom_weapon_manifest_path(tools)
            mdata = json.loads(mpath.read_text(encoding="ascii"))
            mdata["outputs"]["materials"].append("materials/other_mod_asset")
            mpath.write_text(json.dumps(mdata), encoding="ascii")

            fail_last = [False]

            def flaky_converter(cmd, **_kwargs):
                res = fake_converter(cmd, **_kwargs)
                if fail_last[0] and cmd[4] == summary["xmodels"][-1]:
                    return subprocess.CompletedProcess(cmd, 1, stdout="Conversion failed")
                return res

            with (
                patch.object(build_mod.bz_models, "generate_all_assets", return_value=summary),
                patch.object(build_mod.subprocess, "run", side_effect=flaky_converter) as run_mock2,
            ):
                build_mod.compile_custom_weapon_assets(tools, root, root, force=True)
                self.assertTrue(other_mat.is_file())

                # Trigger reconversion that fails after writing partial files -> next call MUST re-run converter!
                (raw / "xmodelsurfs" / f"{summary['xmodels'][0]}0").unlink()
                fail_last[0] = True
                with self.assertRaises(RuntimeError):
                    build_mod.compile_custom_weapon_assets(tools, root, root)
                fail_last[0] = False
                run_mock2.reset_mock()
                build_mod.compile_custom_weapon_assets(tools, root, root)
                self.assertGreater(run_mock2.call_count, 0)

            # 6. Converter emitting invalid/wrong-gloss packed names MUST fail conversion cleanly (A11/S16)
            def wrong_gloss_converter(cmd, **_kwargs):
                kind, name = cmd[3:5]
                if kind == "material":
                    (raw / "materials" / name).write_bytes(b"material-bin")
                    prefix = name.removeprefix("mtl_")
                    for stem in summary["images"]:
                        if stem.rsplit("_", 1)[0] == prefix and not stem.endswith("_g"):
                            fname = f"~{stem}-rgb&wrong_gloss~12345678.iwi" if stem.endswith("_s") else f"{stem}.iwi"
                            (raw / "images" / fname).write_bytes(b"IWi\x06bin")
                else:
                    (raw / "xmodel" / name).write_bytes(b"xmodel-bin")
                    (raw / "xmodelparts" / f"{name}0").write_bytes(b"parts-bin")
                    (raw / "xmodelsurfs" / f"{name}0").write_bytes(b"surfs-bin")
                return subprocess.CompletedProcess(cmd, 0, stdout="ok")

            with (
                patch.object(build_mod.bz_models, "generate_all_assets", return_value=summary),
                patch.object(build_mod.subprocess, "run", side_effect=wrong_gloss_converter),
            ):
                with self.assertRaises(RuntimeError):
                    build_mod.compile_custom_weapon_assets(tools, root, root, force=True)
            self.assertTrue(same_prefix_foreign.is_file())

            # 7. Compiled material referencing a different or stale un-rewritten packed hash MUST fail conversion (A14/S18),
            #    and manifestless staging MUST recover exact hash from compiled material without packaging foreign peers (A15).
            stale_ref = raw / "images" / "~bz_cryo_hull_s-rgb&bz_cryo_h~51c58a90.iwi"
            stale_ref.write_bytes(b"IWi\x06")

            def mismatch_or_stale_converter(cmd, **_kwargs):
                kind, name = cmd[3:5]
                if kind == "material":
                    prefix = name.removeprefix("mtl_")
                    packed_stem = ""
                    for stem in summary["images"]:
                        if stem.rsplit("_", 1)[0] != prefix or stem.endswith("_g"):
                            continue
                        if stem == "bz_cryo_hull_s":
                            packed_stem = stale_ref.stem
                            # Emit a DIFFERENT hash while leaving stale_ref untouched -> must fail BOTH A14 & S18!
                            (raw / "images" / f"~{stem}-rgb&bz_cryo_~deadbeef.iwi").write_bytes(b"IWi\x06new")
                            continue
                        if stem.endswith("_s"):
                            packed_stem = f"~{stem}-rgb&{prefix[:8]}~87654321"
                            (raw / "images" / f"{packed_stem}.iwi").write_bytes(b"IWi\x06bin")
                        else:
                            (raw / "images" / f"{stem}.iwi").write_bytes(b"IWi\x06bin")
                    (raw / "materials" / name).write_bytes(b"mtl\x00" + packed_stem.encode("ascii") + b"\x00")
                else:
                    (raw / "xmodel" / name).write_bytes(b"xmodel-bin")
                    (raw / "xmodelparts" / f"{name}0").write_bytes(b"parts-bin")
                    (raw / "xmodelsurfs" / f"{name}0").write_bytes(b"surfs-bin")
                return subprocess.CompletedProcess(cmd, 0, stdout="ok")

            with (
                patch.object(build_mod.bz_models, "generate_all_assets", return_value=summary),
                patch.object(build_mod.subprocess, "run", side_effect=mismatch_or_stale_converter),
            ):
                with self.assertRaises(RuntimeError):
                    build_mod.compile_custom_weapon_assets(tools, root, root, force=True)

            # Manifestless staging uses compiled material reference (51c58a90) and excludes foreign 12345678 & deadbeef (A15)
            mpath.unlink(missing_ok=True)
            stage_nom = root / "stage_manifestless"
            staged_nom = build_mod.stage_custom_weapon_images(tools, stage_nom)
            self.assertIn(f"images/{stale_ref.name}", staged_nom)
            self.assertNotIn("images/~bz_cryo_hull_s-rgb&bz_cryo_h~12345678.iwi", staged_nom)
            self.assertNotIn("images/~bz_cryo_hull_s-rgb&bz_cryo_~deadbeef.iwi", staged_nom)

            # 8. Unowned embedded gloss reference (altgloss) and malformed 9-digit hash MUST fail BOTH conversion & manifestless staging (A17/S20)
            def unowned_ref_converter(cmd, **_kwargs):
                res = fake_converter(cmd, **_kwargs)
                if cmd[3] == "material" and cmd[4] == "mtl_bz_cryo_hull":
                    (raw / "materials" / "mtl_bz_cryo_hull").write_bytes(b"mtl\x00~bz_cryo_hull_s-rgb&altgloss~12345678\x00")
                return res

            with (
                patch.object(build_mod.bz_models, "generate_all_assets", return_value=summary),
                patch.object(build_mod.subprocess, "run", side_effect=unowned_ref_converter),
            ):
                with self.assertRaises(RuntimeError):
                    build_mod.compile_custom_weapon_assets(tools, root, root, force=True)
            with self.assertRaises(ValueError):
                build_mod.stage_custom_weapon_images(tools, root / "stage_bad_gloss")
            (raw / "materials" / "mtl_bz_cryo_hull").write_bytes(b"mtl\x00~bz_cryo_hull_s-rgb&bz_cryo_h~51c58a901\x00")
            with self.assertRaises(ValueError):
                build_mod.stage_custom_weapon_images(tools, root / "stage_bad_hash")
            # Empty suffix after -rgb& (A19/S21) and mixed unowned+owned tokens (A20) must also fail closed
            (raw / "materials" / "mtl_bz_cryo_hull").write_bytes(b"mtl\x00~bz_cryo_hull_s-rgb&\x00")
            with self.assertRaises(ValueError):
                build_mod.stage_custom_weapon_images(tools, root / "stage_empty_suffix")
            (raw / "materials" / "mtl_bz_cryo_hull").write_bytes(
                b"mtl\x00~bz_cryo_hull_s-rgb&altgloss~12345678\x00~bz_cryo_hull_s-rgb&bz_cryo_h~51c58a90\x00"
            )
            with self.assertRaises(ValueError):
                build_mod.stage_custom_weapon_images(tools, root / "stage_mixed_tokens")


if __name__ == "__main__":
    unittest.main()
