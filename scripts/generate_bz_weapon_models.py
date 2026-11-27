#!/usr/bin/env python3
"""Generate custom CoD:WaW XMODEL_EXPORT v6 weapon meshes, 512px TGA textures, and GDT manifest.

Pure Python stdlib (deterministic, zero external pip dependencies) so both offline unit tests
on macOS/Linux and live Mod Tools builds via Treyarch's converter.exe on plebdev-ultra produce
identical, validated assets.

Custom weapon lineup:
  1. Cryo Cannon      -> viewmodel_bz_cryo_cannon (12 tesla_gun bones) + world_bz_cryo_cannon
  2. Multi-Crossbow   -> viewmodel_bz_multi_crossbow (10 fg42_scoped bones) + world_bz_multi_crossbow + bz_crossbow_bolt
  3. Blade Boomerang  -> viewmodel_bz_blade_boomerang (7 colt45 bones) + world_bz_blade_boomerang + bz_boomerang_blade_air
  4. Acid Sprayer     -> viewmodel_bz_acid_sprayer (2 flamethrower bones) + world_bz_acid_sprayer
"""

from __future__ import annotations

import argparse
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

ASSET_SUBDIR = "bz_weapons"
GDT_FILENAME = "bz_weapons.gdt"
DEFAULT_TEX_SIZE = 256

# Canonical custom asset names (exported for build_mod.py and offline unit tests).
CUSTOM_WEAPON_VIEWMODELS: dict[str, str] = {
    "bz_acid_sprayer": "viewmodel_bz_acid_sprayer",
    "bz_cryo_cannon": "viewmodel_bz_cryo_cannon",
    "bz_multi_crossbow": "viewmodel_bz_multi_crossbow",
    "bz_blade_boomerang": "viewmodel_bz_blade_boomerang",
}

CUSTOM_WEAPON_WORLDMODELS: dict[str, str] = {
    "bz_acid_sprayer": "world_bz_acid_sprayer",
    "bz_cryo_cannon": "world_bz_cryo_cannon",
    "bz_multi_crossbow": "world_bz_multi_crossbow",
    "bz_blade_boomerang": "world_bz_blade_boomerang",
}

CUSTOM_PROJECTILE_XMODELS: tuple[str, ...] = (
    "bz_crossbow_bolt",
    "bz_boomerang_blade_air",
    "bz_portal_orb_air",
)

CUSTOM_SPECIAL_WEAPON_VIEWMODELS: dict[str, str] = {
    "bz_portal_grenade": "viewmodel_bz_portal_grenade",
    "bz_war_club": "viewmodel_bz_war_club",
}

CUSTOM_SPECIAL_WEAPON_WORLDMODELS: dict[str, str] = {
    "bz_portal_grenade": "world_bz_portal_grenade",
    "bz_war_club": "world_bz_war_club",
}

CUSTOM_STATION_XMODELS: tuple[str, ...] = (
    "bz_station_perks_kiosk",
    "bz_station_class_kiosk",
    "bz_station_arsenal_kiosk",
    "bz_station_pap_kiosk",
)

ALL_CUSTOM_XMODELS: tuple[str, ...] = (
    "viewmodel_bz_acid_sprayer",
    "world_bz_acid_sprayer",
    "viewmodel_bz_cryo_cannon",
    "world_bz_cryo_cannon",
    "viewmodel_bz_multi_crossbow",
    "world_bz_multi_crossbow",
    "bz_crossbow_bolt",
    "viewmodel_bz_blade_boomerang",
    "world_bz_blade_boomerang",
    "bz_boomerang_blade_air",
    "viewmodel_bz_portal_grenade",
    "world_bz_portal_grenade",
    "bz_portal_orb_air",
    "viewmodel_bz_war_club",
    "world_bz_war_club",
    "bz_station_perks_kiosk",
    "bz_station_class_kiosk",
    "bz_station_arsenal_kiosk",
    "bz_station_pap_kiosk",
)

ALL_CUSTOM_MATERIALS: tuple[str, ...] = (
    "mtl_bz_cryo_hull",
    "mtl_bz_cryo_dark",
    "mtl_bz_cryo_glow",
    "mtl_bz_xbow_wood",
    "mtl_bz_xbow_metal",
    "mtl_bz_xbow_brass",
    "mtl_bz_xbow_glow",
    "mtl_bz_blade_steel",
    "mtl_bz_blade_leather",
    "mtl_bz_blade_brass",
    "mtl_bz_blade_glow",
    "mtl_bz_acid_metal",
    "mtl_bz_acid_hazard",
    "mtl_bz_acid_glow",
    "mtl_bz_acid_stream",
    "mtl_bz_acid_billow",
    "mtl_bz_acid_drips",
    "mtl_bz_acid_mist",
    "mtl_bz_portal_ring",
    "mtl_bz_portal_core",
    "mtl_bz_portal_trim",
    "mtl_bz_club_wood",
    "mtl_bz_club_iron",
    "mtl_bz_club_glow",
    "mtl_bz_kiosk_frame",
    "mtl_bz_kiosk_brass",
    "mtl_bz_kiosk_perks_glow",
    "mtl_bz_kiosk_class_glow",
    "mtl_bz_kiosk_arsenal_glow",
    "mtl_bz_kiosk_pap_glow",
)

EFFECT_MATERIALS: tuple[str, ...] = (
    "mtl_bz_acid_stream",
    "mtl_bz_acid_billow",
    "mtl_bz_acid_drips",
    "mtl_bz_acid_mist",
)


# ---------------------------------------------------------------------------
# Vector math helpers
# ---------------------------------------------------------------------------

Vec3 = tuple[float, float, float]


def v_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_scale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def v_cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def v_dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_norm(a: Vec3) -> Vec3:
    mag = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    if mag < 1e-8:
        return (0.0, 0.0, 1.0)
    return (a[0] / mag, a[1] / mag, a[2] / mag)


def rot_x(p: Vec3, deg: float) -> Vec3:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return (p[0], p[1] * c - p[2] * s, p[1] * s + p[2] * c)


def rot_y(p: Vec3, deg: float) -> Vec3:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return (p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c)


def rot_z(p: Vec3, deg: float) -> Vec3:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2])


def clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def clamp255(v: float) -> int:
    iv = int(round(v))
    return 0 if iv < 0 else (255 if iv > 255 else iv)


# ---------------------------------------------------------------------------
# Procedural 3D Mesh Builder -> CoD:WaW XMODEL_EXPORT VERSION 6
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BoneDef:
    name: str
    parent: int  # -1 for root
    offset: Vec3


@dataclass(frozen=True)
class FaceDef:
    mat_idx: int
    v0: int
    v1: int
    v2: int
    n0: Vec3
    n1: Vec3
    n2: Vec3
    uv0: tuple[float, float]
    uv1: tuple[float, float]
    uv2: tuple[float, float]


class MeshBuilder:
    """Builds clean, UV-mapped, bone-weighted triangle meshes for XMODEL_EXPORT v6."""

    def __init__(self, name: str, bones: Sequence[BoneDef], model_type: str = "animated") -> None:
        self.name = name
        self.bones = list(bones)
        self.model_type = model_type
        self.verts: list[tuple[Vec3, int]] = []  # (xyz, bone_idx)
        self.faces: list[FaceDef] = []
        self.materials: list[str] = []
        self._mat_map: dict[str, int] = {}

    def mat(self, mat_name: str) -> int:
        if mat_name not in self._mat_map:
            self._mat_map[mat_name] = len(self.materials)
            self.materials.append(mat_name)
        return self._mat_map[mat_name]

    def add_vert(self, pos: Vec3, bone_idx: int = 0) -> int:
        idx = len(self.verts)
        self.verts.append((pos, bone_idx))
        return idx

    def add_tri(
        self,
        mat_name: str,
        i0: int,
        i1: int,
        i2: int,
        uv0: tuple[float, float] = (0.0, 0.0),
        uv1: tuple[float, float] = (1.0, 0.0),
        uv2: tuple[float, float] = (0.0, 1.0),
        n0: Vec3 | None = None,
        n1: Vec3 | None = None,
        n2: Vec3 | None = None,
    ) -> None:
        p0, p1, p2 = self.verts[i0][0], self.verts[i1][0], self.verts[i2][0]
        fn = v_norm(v_cross(v_sub(p1, p0), v_sub(p2, p0)))
        self.faces.append(
            FaceDef(
                mat_idx=self.mat(mat_name),
                v0=i0,
                v1=i1,
                v2=i2,
                n0=v_norm(n0) if n0 is not None else fn,
                n1=v_norm(n1) if n1 is not None else fn,
                n2=v_norm(n2) if n2 is not None else fn,
                uv0=uv0,
                uv1=uv1,
                uv2=uv2,
            )
        )

    def add_quad(
        self,
        mat_name: str,
        p0: Vec3,
        p1: Vec3,
        p2: Vec3,
        p3: Vec3,
        bone_idx: int = 0,
        uv_scale: float = 0.08,
        double_sided: bool = False,
    ) -> None:
        """Add an oriented quad (p0->p1->p2->p3 CCW outward) with planar UVs."""
        i0 = self.add_vert(p0, bone_idx)
        i1 = self.add_vert(p1, bone_idx)
        i2 = self.add_vert(p2, bone_idx)
        i3 = self.add_vert(p3, bone_idx)
        w = math.sqrt(v_dot(v_sub(p1, p0), v_sub(p1, p0))) * uv_scale
        h = math.sqrt(v_dot(v_sub(p3, p0), v_sub(p3, p0))) * uv_scale
        w = max(w, 0.08)
        h = max(h, 0.08)
        self.add_tri(mat_name, i0, i1, i2, (0.0, 0.0), (w, 0.0), (w, h))
        self.add_tri(mat_name, i0, i2, i3, (0.0, 0.0), (w, h), (0.0, h))
        if double_sided:
            self.add_tri(mat_name, i0, i2, i1, (0.0, 0.0), (w, h), (w, 0.0))
            self.add_tri(mat_name, i0, i3, i2, (0.0, 0.0), (0.0, h), (w, h))

    def add_box(
        self,
        mat_name: str,
        center: Vec3,
        size: Vec3,
        bone_idx: int = 0,
        rot_xyz: Vec3 = (0.0, 0.0, 0.0),
        uv_scale: float = 0.08,
    ) -> None:
        hx, hy, hz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
        corners_local = [
            (-hx, -hy, -hz),
            (+hx, -hy, -hz),
            (+hx, +hy, -hz),
            (-hx, +hy, -hz),
            (-hx, -hy, +hz),
            (+hx, -hy, +hz),
            (+hx, +hy, +hz),
            (-hx, +hy, +hz),
        ]
        rx, ry, rz = rot_xyz
        pts: list[Vec3] = []
        for p in corners_local:
            if rx:
                p = rot_x(p, rx)
            if ry:
                p = rot_y(p, ry)
            if rz:
                p = rot_z(p, rz)
            pts.append(v_add(p, center))
        # 6 outward-facing CCW quads
        quads = (
            (0, 3, 2, 1),  # -Z
            (4, 5, 6, 7),  # +Z
            (0, 1, 5, 4),  # -Y
            (2, 3, 7, 6),  # +Y
            (0, 4, 7, 3),  # -X
            (1, 2, 6, 5),  # +X
        )
        for a, b, c, d in quads:
            self.add_quad(mat_name, pts[a], pts[b], pts[c], pts[d], bone_idx=bone_idx, uv_scale=uv_scale)

    def add_tapered_prism(
        self,
        mat_name: str,
        p_start: Vec3,
        p_end: Vec3,
        r_start: float,
        r_end: float,
        sides: int = 10,
        bone_idx: int = 0,
        cap_start: bool = True,
        cap_end: bool = True,
        angle_offset_deg: float = 0.0,
        scale_y: float = 1.0,
        scale_z: float = 1.0,
        uv_u_repeat: float = 1.0,
    ) -> None:
        """Cylinder / cone / hexagonal or octagonal tube between any two 3D points."""
        axis = v_sub(p_end, p_start)
        length = math.sqrt(v_dot(axis, axis))
        if length < 1e-6:
            return
        fwd = v_scale(axis, 1.0 / length)
        up_ref: Vec3 = (0.0, 0.0, 1.0) if abs(fwd[2]) < 0.92 else (0.0, 1.0, 0.0)
        right = v_norm(v_cross(up_ref, fwd))
        up = v_norm(v_cross(fwd, right))

        ring0_pts: list[Vec3] = []
        ring1_pts: list[Vec3] = []
        ring_dirs: list[Vec3] = []
        ring_cap_uvs: list[tuple[float, float]] = []
        for s in range(sides):
            ang = math.radians(angle_offset_deg + (360.0 * s / sides))
            ca, sa = math.cos(ang), math.sin(ang)
            radial = v_add(v_scale(right, ca * scale_y), v_scale(up, sa * scale_z))
            ring_dirs.append(v_norm(radial))
            ring0_pts.append(v_add(p_start, v_scale(radial, r_start)))
            ring1_pts.append(v_add(p_end, v_scale(radial, r_end)))
            ring_cap_uvs.append((0.5 + 0.45 * ca, 0.5 + 0.45 * sa))

        v_repeat = max(length * 0.08, 0.12)
        for s in range(sides):
            sn = (s + 1) % sides
            i0 = self.add_vert(ring0_pts[s], bone_idx)
            i1 = self.add_vert(ring1_pts[s], bone_idx)
            i2 = self.add_vert(ring1_pts[sn], bone_idx)
            i3 = self.add_vert(ring0_pts[sn], bone_idx)
            u0 = (s / sides) * uv_u_repeat
            u1 = ((s + 1) / sides) * uv_u_repeat
            n_s = ring_dirs[s]
            n_sn = ring_dirs[sn]
            # Consistent right-handed outward CCW winding internally; to_xmodel_export writes WaW CW order.
            self.add_tri(mat_name, i0, i3, i2, (u0, 0.0), (u1, 0.0), (u1, v_repeat), n_s, n_sn, n_sn)
            self.add_tri(mat_name, i0, i2, i1, (u0, 0.0), (u1, v_repeat), (u0, v_repeat), n_s, n_sn, n_s)

        if cap_start and r_start > 1e-5:
            ci = self.add_vert(p_start, bone_idx)
            n_cap = v_scale(fwd, -1.0)
            for s in range(sides):
                sn = (s + 1) % sides
                a = self.add_vert(ring0_pts[s], bone_idx)
                b = self.add_vert(ring0_pts[sn], bone_idx)
                self.add_tri(
                    mat_name,
                    ci,
                    b,
                    a,
                    (0.5, 0.5),
                    ring_cap_uvs[sn],
                    ring_cap_uvs[s],
                    n_cap,
                    n_cap,
                    n_cap,
                )

        if cap_end and r_end > 1e-5:
            ci = self.add_vert(p_end, bone_idx)
            n_cap = fwd
            for s in range(sides):
                sn = (s + 1) % sides
                a = self.add_vert(ring1_pts[s], bone_idx)
                b = self.add_vert(ring1_pts[sn], bone_idx)
                self.add_tri(
                    mat_name,
                    ci,
                    a,
                    b,
                    (0.5, 0.5),
                    ring_cap_uvs[s],
                    ring_cap_uvs[sn],
                    n_cap,
                    n_cap,
                    n_cap,
                )

    def add_swept_blade(
        self,
        steel_mat: str,
        glow_mat: str,
        spine_pts: Sequence[Vec3],
        widths: Sequence[float],
        thicknesses: Sequence[float],
        normal_axis: Vec3 = (0.0, 0.0, 1.0),
        bone_idx: int = 0,
        glow_outer: bool = True,
    ) -> None:
        """Build a sharp diamond-section curved blade strip with a glowing outer cutting bevel."""
        n_axis = v_norm(normal_axis)
        rings: list[tuple[Vec3, Vec3, Vec3, Vec3, Vec3]] = []
        count = len(spine_pts)
        for idx in range(count):
            p = spine_pts[idx]
            if idx == 0:
                tang = v_norm(v_sub(spine_pts[1], spine_pts[0]))
            elif idx == count - 1:
                tang = v_norm(v_sub(spine_pts[-1], spine_pts[-2]))
            else:
                tang = v_norm(v_sub(spine_pts[idx + 1], spine_pts[idx - 1]))
            side = v_norm(v_cross(n_axis, tang))
            w = widths[idx]
            t = thicknesses[idx]
            inner = v_add(p, v_scale(side, -w * 0.45))
            mid_top = v_add(p, v_scale(n_axis, +t * 0.5))
            mid_bot = v_add(p, v_scale(n_axis, -t * 0.5))
            bevel_top = v_add(v_add(p, v_scale(side, +w * 0.38)), v_scale(n_axis, +t * 0.16))
            bevel_bot = v_add(v_add(p, v_scale(side, +w * 0.38)), v_scale(n_axis, -t * 0.16))
            outer = v_add(p, v_scale(side, +w * 0.62))
            rings.append((inner, mid_top, bevel_top, outer, mid_bot, bevel_bot))  # type: ignore[arg-type]

        edge_mat = glow_mat if glow_outer else steel_mat
        for idx in range(count - 1):
            a = rings[idx]
            b = rings[idx + 1]
            # All 6 facets wound consistently CCW outward around the blade cross-section!
            # side = n_axis x tang, so walking inner(-side) -> top(+n_axis) -> outer(+side) -> bot(-n_axis)
            # has outward normal = (+tang) x (next - prev), i.e. quad order (a_prev, b_prev, b_next, a_next).
            self.add_quad(steel_mat, a[0], b[0], b[1], a[1], bone_idx=bone_idx, uv_scale=0.14)
            self.add_quad(steel_mat, a[1], b[1], b[2], a[2], bone_idx=bone_idx, uv_scale=0.14)
            self.add_quad(edge_mat, a[2], b[2], b[3], a[3], bone_idx=bone_idx, uv_scale=0.20)
            self.add_quad(edge_mat, a[3], b[3], b[5], a[5], bone_idx=bone_idx, uv_scale=0.20)
            self.add_quad(steel_mat, a[5], b[5], b[4], a[4], bone_idx=bone_idx, uv_scale=0.14)
            self.add_quad(steel_mat, a[4], b[4], b[0], a[0], bone_idx=bone_idx, uv_scale=0.14)

        # Cap both root and tip ends so blades are closed watertight solids (F6)!
        loop_order = (0, 1, 2, 3, 5, 4)
        for end_ring, center_pt, is_tip in ((rings[0], spine_pts[0], False), (rings[-1], spine_pts[-1], True)):
            ci = self.add_vert(center_pt, bone_idx)
            for k in range(len(loop_order)):
                p_cur = end_ring[loop_order[k]]
                p_nxt = end_ring[loop_order[(k + 1) % len(loop_order)]]
                ia = self.add_vert(p_cur, bone_idx)
                ib = self.add_vert(p_nxt, bone_idx)
                if is_tip:
                    self.add_tri(steel_mat, ci, ib, ia, (0.5, 0.5), (0.8, 0.5), (0.5, 0.8))
                else:
                    self.add_tri(steel_mat, ci, ia, ib, (0.5, 0.5), (0.5, 0.8), (0.8, 0.5))

    def to_xmodel_export(self) -> str:
        lines: list[str] = [
            f"// Generated by scripts/generate_bz_weapon_models.py ({self.name})",
            "MODEL",
            "VERSION 6",
            "",
            f"NUMBONES {len(self.bones)}",
        ]
        for idx, bone in enumerate(self.bones):
            lines.append(f'BONE {idx} {bone.parent} "{bone.name}"')
        lines.append("")
        # Compute world-space offsets for each bone in XMODEL_EXPORT
        world_offsets: list[Vec3] = []
        for idx, bone in enumerate(self.bones):
            if bone.parent < 0:
                wpos = bone.offset
            else:
                wpos = v_add(world_offsets[bone.parent], bone.offset)
            world_offsets.append(wpos)
            lines.append(f"BONE {idx}")
            lines.append(f"OFFSET {wpos[0]:.6f}, {wpos[1]:.6f}, {wpos[2]:.6f}")
            lines.append("SCALE 1.000000, 1.000000, 1.000000")
            lines.append("X 1.000000, 0.000000, 0.000000")
            lines.append("Y 0.000000, 1.000000, 0.000000")
            lines.append("Z 0.000000, 0.000000, 1.000000")
            lines.append("")

        lines.append(f"NUMVERTS {len(self.verts)}")
        for idx, (pos, bone_idx) in enumerate(self.verts):
            lines.append(f"VERT {idx}")
            lines.append(f"OFFSET {pos[0]:.6f}, {pos[1]:.6f}, {pos[2]:.6f}")
            lines.append("BONES 1")
            lines.append(f"BONE {bone_idx} 1.000000")
            lines.append("")

        lines.append(f"NUMFACES {len(self.faces)}")
        # CoD:WaW (DirectX9 XMODEL_EXPORT v6) treats clockwise vertex order (v0, v2, v1 relative
        # to right-handed outward normals) as front-facing under cullFace=Back*.
        for face in self.faces:
            lines.append(f"TRI 0 {face.mat_idx} 0 0")
            for vi, ni, uvi in (
                (face.v0, face.n0, face.uv0),
                (face.v2, face.n2, face.uv2),
                (face.v1, face.n1, face.uv1),
            ):
                lines.append(f"VERT {vi}")
                lines.append(f"NORMAL {ni[0]:.6f} {ni[1]:.6f} {ni[2]:.6f}")
                lines.append("COLOR 1.000000 1.000000 1.000000 1.000000")
                lines.append(f"UV 1 {uvi[0]:.6f} {uvi[1]:.6f}")
        lines.append("")
        lines.append("NUMOBJECTS 1")
        lines.append(f'OBJECT 0 "{self.name}_mesh"')
        lines.append("")
        lines.append(f"NUMMATERIALS {len(self.materials)}")
        for idx, mat_name in enumerate(self.materials):
            lines.extend(
                [
                    f'MATERIAL {idx} "{mat_name}" "Phong" ""',
                    "COLOR 0.800000 0.800000 0.800000 1.000000",
                    "TRANSPARENCY 0.000000 0.000000 0.000000 1.000000",
                    "AMBIENTCOLOR 0.000000 0.000000 0.000000 1.000000",
                    "INCANDESCENCE 0.000000 0.000000 0.000000 1.000000",
                    "COEFFS 0.800000 0.000000",
                    "GLOW 0.000000 0",
                    "REFRACTIVE 6 1.000000",
                    "SPECULARCOLOR 0.500000 0.500000 0.500000 1.000000",
                    "REFLECTIVECOLOR 0.000000 0.000000 0.000000 1.000000",
                    "REFLECTIVE 1 0.500000",
                    "BLINN -1.000000 -1.000000",
                    "PHONG 20.000000",
                    "",
                ]
            )
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Exact WaW Donor Bone Hierarchies (decoded directly from raw/xmodelparts)
# ---------------------------------------------------------------------------

BONES_FLAMETHROWER: tuple[BoneDef, ...] = (
    BoneDef("j_gun", -1, (0.0, 0.0, 0.0)),
    BoneDef("tag_flash", 0, (17.71, 0.0, -0.29)),
)

BONES_TESLA: tuple[BoneDef, ...] = (
    BoneDef("j_gun", -1, (0.0, 0.0, 0.0)),
    BoneDef("j_bolt", 0, (17.57, 1.03, 1.31)),
    BoneDef("j_bulb_1", 0, (7.89, 2.95, 1.13)),
    BoneDef("j_bulb_2", 0, (9.64, 2.95, 1.13)),
    BoneDef("j_bulb_3", 0, (11.39, 2.95, 1.13)),
    BoneDef("j_clip", 0, (9.72, 1.07, -12.77)),
    BoneDef("j_switch", 0, (6.24, 1.33, 1.26)),
    BoneDef("j_switch_cover", 0, (6.24, 1.52, 1.74)),
    BoneDef("tag_brass", 0, (9.64, 2.95, 1.13)),
    BoneDef("tag_flash", 0, (41.0, 0.0, 2.16)),
    BoneDef("tag_fx_1", 0, (2.05, 0.0, 2.74)),
    BoneDef("j_charging_hinge", 1, (0.76, 0.05, -0.02)),
)

BONES_FG42_SCOPED: tuple[BoneDef, ...] = (
    BoneDef("j_gun", -1, (0.0, 0.0, 0.0)),
    BoneDef("j_bolt", 0, (7.66, -1.96, 1.90)),
    BoneDef("j_clip", 0, (0.76, 0.98, 2.56)),
    BoneDef("tag_bipod_left", 0, (12.50, 0.47, 1.71)),
    BoneDef("tag_bipod_right", 0, (12.50, -0.90, 1.71)),
    BoneDef("tag_brass", 0, (0.41, -0.72, 2.83)),
    BoneDef("tag_flash", 0, (26.67, -0.12, 2.76)),
    BoneDef("tag_iron_sights", 0, (0.63, -0.12, 4.39)),
    BoneDef("tag_scope", 0, (1.18, -0.18, 3.40)),
    BoneDef("tag_telescopic", 0, (1.14, 0.11, 4.28)),
)

BONES_COLT45: tuple[BoneDef, ...] = (
    BoneDef("j_gun", -1, (0.0, 0.0, 0.0)),
    BoneDef("j_bolt", 0, (-1.95, 0.07, 1.57)),
    BoneDef("j_clip", 0, (-1.34, 0.07, -1.24)),
    BoneDef("joint1", 0, (-2.12, 0.05, 0.27)),
    BoneDef("joint2", 0, (0.90, 0.44, 0.39)),
    BoneDef("tag_brass", 0, (0.96, -0.34, 1.12)),
    BoneDef("tag_flash", 0, (5.43, 0.08, 1.18)),
)

BONES_RIGID: tuple[BoneDef, ...] = (
    BoneDef("tag_origin", -1, (0.0, 0.0, 0.0)),
)

BONES_WORLD_WEAPON: tuple[BoneDef, ...] = (
    BoneDef("tag_origin", -1, (0.0, 0.0, 0.0)),
    BoneDef("tag_flash", 0, (18.0, 0.0, 1.0)),
)


def world_weapon_bones(tag_flash: Vec3) -> tuple[BoneDef, ...]:
    """Return a world-model skeleton with tag_flash positioned at the weapon's actual emitter."""
    return (
        BoneDef("tag_origin", -1, (0.0, 0.0, 0.0)),
        BoneDef("tag_flash", 0, tag_flash),
    )


# ---------------------------------------------------------------------------
# 1. CRYO CANNON (1945 Group 935 "Kaeltewaffe" — Chipped Wintertarnung + Dewar Flasks)
# ---------------------------------------------------------------------------


def build_cryo_cannon(name: str, is_world: bool = False) -> MeshBuilder:
    bones = world_weapon_bones((41.0, 0.0, 2.16)) if is_world else BONES_TESLA
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0
    b_bolt = 0 if is_world else 1
    b_bulbs = (0, 0, 0) if is_world else (2, 3, 4)
    b_switch = 0 if is_world else 6

    hull = "mtl_bz_cryo_hull"   # Chipped Wintertarnung whitewash over Panzergrau steel
    dark = "mtl_bz_cryo_dark"   # Parkerized / blued steel
    glow = "mtl_bz_cryo_glow"   # Opaque unlit glacial cyan (#10a5f6)
    brass = "mtl_bz_xbow_brass"  # Restrained weathered brass dial/collar (<=10%, within 4-slot cap)
    s_cyl = 6 if is_world else 8

    # Solid bridged 1945 rear stock & grip (kept slim for Tesla reload hand clearance)
    m.add_tapered_prism(dark, (-7.6, 0.0, -0.05), (-6.8, 0.0, 0.08), 0.94, 0.90, sides=s_cyl, bone_idx=b_gun, cap_end=False, scale_y=0.78, scale_z=0.92)
    m.add_tapered_prism(dark, (-6.9, 0.0, 0.08), (-1.4, 0.0, 0.62), 0.88, 1.22, sides=s_cyl, bone_idx=b_gun, cap_start=False, cap_end=False, scale_y=0.82, scale_z=0.74)
    m.add_tapered_prism(hull, (-1.6, 0.0, 0.62), (3.8, 0.0, 1.18), 1.22, 1.60, sides=s_cyl, bone_idx=b_gun, cap_start=False, cap_end=False, scale_y=0.86, scale_z=0.78)
    # Bridged pistol grip + lower trigger guard bar
    m.add_box(dark, (-0.5, 0.0, -2.75), (1.9, 1.26, 3.5), bone_idx=b_gun, rot_xyz=(0.0, 14.0, 0.0))
    m.add_box(dark, (1.2, 0.0, -4.15), (3.4, 0.72, 0.42), bone_idx=b_gun)
    m.add_box(dark, (2.7, 0.0, -2.55), (0.58, 0.78, 3.1), bone_idx=b_gun)

    # Centerline rear-face brass pressure dial at tag_fx_1 (2.05, 0.0, 2.74) directly beneath iron ring sight!
    m.add_tapered_prism(brass, (1.62, 0.0, 2.74), (2.22, 0.0, 2.74), 0.56, 0.52, sides=s_cyl, bone_idx=b_gun)
    m.add_tapered_prism(glow, (1.56, 0.0, 2.74), (1.70, 0.0, 2.74), 0.36, 0.36, sides=s_cyl, bone_idx=b_gun, cap_end=False)

    # Main 1945 stamped-steel receiver jacket (Wintertarnung upper shroud + dark steel lower chassis, Z <= 3.35)
    m.add_tapered_prism(dark, (3.6, 0.0, 1.32), (22.4, 0.0, 1.62), 1.68, 1.48, sides=s_cyl, bone_idx=b_gun, cap_start=False, scale_y=0.90)
    m.add_box(hull, (13.0, 0.0, 2.52), (17.2, 2.25, 0.92), bone_idx=b_gun)
    m.add_tapered_prism(dark, (2.8, 0.0, -0.10), (21.2, 0.0, 0.25), 1.04, 0.84, sides=6, bone_idx=b_gun)
    # Recessed narrow opaque cyan dorsal conduit channel (Z <= 3.16 -> 100% clear of ADS sightline!)
    m.add_tapered_prism(glow, (4.8, 0.0, 3.00), (26.5, 0.0, 3.00), 0.24, 0.20, sides=6, bone_idx=b_gun, cap_start=False)
    for rx in (7.4, 13.4, 19.4):
        m.add_box(dark, (rx, 0.0, 3.16), (0.68, 1.72, 0.24), bone_idx=b_gun)

    # Hinged steel switch latch on left upper flank (skinned to j_switch)
    m.add_box(brass, (6.24, 1.38, 1.48), (1.15, 0.32, 0.64), bone_idx=b_switch)

    # 3 steel-caged upright Dewar flasks on left flank (j_bulb_1/2/3, bottoms >= 0.05 flush/above receiver underside!)
    s_flask = 4 if is_world else 6
    bulb_xs = (7.89, 9.64, 11.39)
    for b_idx, bx in zip(b_bulbs, bulb_xs):
        # Armored steel outer jacket with narrow vertical cyan sight-slit (<=30% vessel surface!)
        m.add_tapered_prism(dark, (bx, 2.95, 0.08), (bx, 2.95, 0.48), 0.66, 0.66, sides=s_flask, bone_idx=b_idx)
        m.add_tapered_prism(dark, (bx, 2.95, 0.44), (bx, 2.95, 2.46), 0.56, 0.56, sides=s_flask, bone_idx=b_idx, cap_start=False, cap_end=False)
        m.add_box(glow, (bx, 3.44, 1.45), (0.28, 0.16, 1.65), bone_idx=b_idx)
        if not is_world:
            m.add_tapered_prism(hull, (bx, 2.95, 1.35), (bx, 2.95, 1.55), 0.64, 0.64, sides=s_flask, bone_idx=b_idx)
        m.add_tapered_prism(dark, (bx, 2.95, 2.42), (bx, 2.95, 2.92), 0.66, 0.48, sides=s_flask, bone_idx=b_idx)
    m.add_tapered_prism(dark, (6.7, 2.38, 0.22), (12.6, 2.38, 0.22), 0.46, 0.46, sides=s_flask, bone_idx=b_gun)
    m.add_tapered_prism(hull, (6.8, 2.38, 2.74), (12.5, 2.38, 2.74), 0.36, 0.36, sides=s_flask, bone_idx=b_gun)

    # Bold right-flank dark-steel condenser housing + cold indicator slit (x=10..21, y=-2.8, ~11u x 3.2u)
    m.add_tapered_prism(dark, (10.0, -2.75, 1.25), (21.0, -2.75, 1.25), 1.48, 1.44, sides=s_cyl, bone_idx=b_gun)
    for cx in ((13.0, 18.0) if is_world else (12.0, 15.5, 19.0)):
        m.add_tapered_prism(hull, (cx - 0.26, -2.75, 1.25), (cx + 0.26, -2.75, 1.25), 1.58, 1.58, sides=s_cyl, bone_idx=b_gun)
    m.add_box(glow, (15.5, -4.18, 1.25), (7.6, 0.18, 0.36), bone_idx=b_gun)
    m.add_tapered_prism(dark, (20.8, -2.75, 1.25), (23.2, -1.25, 1.72), 0.42, 0.34, sides=s_flask, bone_idx=b_gun, cap_start=False, cap_end=False)

    # Animated cryo-vent bolt shroud (skinned to j_bolt)
    m.add_tapered_prism(dark, (15.8, 1.15, 1.55), (19.4, 1.15, 1.55), 0.56, 0.46, sides=s_flask, bone_idx=b_bolt)

    # Heavy 1945 barrel + 4 stepped circular radiator cooling fins (replacing sci-fi swept wings!)
    m.add_tapered_prism(dark, (22.0, 0.0, 1.82), (35.8, 0.0, 2.04), 1.04, 0.90, sides=s_cyl, bone_idx=b_gun, cap_start=False, cap_end=False)
    for fi, fx in enumerate((23.4, 26.2, 29.0, 31.8)):
        r_fin = 1.98 - fi * 0.10
        m.add_tapered_prism(hull, (fx - 0.34, 0.0, 1.90), (fx + 0.34, 0.0, 1.92), r_fin, r_fin, sides=s_cyl, bone_idx=b_gun)
    # Compact flared Dewar frost-ring bell (OD <= 4.6u -> radius <= 2.30u, cleanly beneath Z=5.10 ADS sightline!)
    m.add_tapered_prism(dark, (34.4, 0.0, 2.04), (36.4, 0.0, 2.08), 1.24, 1.76, sides=s_cyl, bone_idx=b_gun, cap_end=False)
    m.add_tapered_prism(hull, (36.2, 0.0, 2.08), (40.2, 0.0, 2.16), 1.76, 2.24, sides=s_cyl, bone_idx=b_gun, cap_start=False)
    m.add_tapered_prism(glow, (39.6, 0.0, 2.15), (40.5, 0.0, 2.16), 1.78, 1.62, sides=s_cyl, bone_idx=b_gun, cap_start=False)

    # Open circular iron ring sight at (3.8, 0.0, 5.10) — keeps center ADS aiming point 100% clear!
    ring_c = (3.8, 0.0, 5.10)
    ring_segs = 6 if is_world else 10
    ring_r = 0.86
    m.add_box(dark, (3.8, -0.68, 3.88), (0.46, 0.22, 1.18), bone_idx=b_gun)
    m.add_box(dark, (3.8, +0.68, 3.88), (0.46, 0.22, 1.18), bone_idx=b_gun)
    m.add_box(hull, (3.8, 0.0, 3.40), (0.72, 1.60, 0.24), bone_idx=b_gun)
    for s in range(ring_segs):
        a0 = math.radians(360.0 * s / ring_segs)
        a1 = math.radians(360.0 * (s + 1) / ring_segs)
        p0 = (ring_c[0], ring_c[1] + math.cos(a0) * ring_r, ring_c[2] + math.sin(a0) * ring_r)
        p1 = (ring_c[0], ring_c[1] + math.cos(a1) * ring_r, ring_c[2] + math.sin(a1) * ring_r)
        m.add_tapered_prism(dark, p0, p1, 0.085, 0.085, sides=4, bone_idx=b_gun, cap_start=False, cap_end=False)
    if not is_world:
        # Subtle opaque cyan witness posts on outer ring rim (never touching center!)
        m.add_tapered_prism(glow, (3.8, -0.80, 5.10), (3.8, -0.48, 5.10), 0.05, 0.035, sides=4, bone_idx=b_gun, cap_start=False, cap_end=False)
        m.add_tapered_prism(glow, (3.8, +0.80, 5.10), (3.8, +0.48, 5.10), 0.05, 0.035, sides=4, bone_idx=b_gun, cap_start=False, cap_end=False)

    return m


# ---------------------------------------------------------------------------
# 2. MULTI-CROSSBOW (1945 Stacked Leaf-Spring Prods + Left 3-Bolt Cassette + ZFG42 Scope)
# ---------------------------------------------------------------------------


def build_multi_crossbow(name: str, is_world: bool = False) -> MeshBuilder:
    bones = world_weapon_bones((26.67, -0.12, 2.76)) if is_world else BONES_FG42_SCOPED
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0
    b_bolt = 0 if is_world else 1  # j_bolt: right-side steel cocking sled (7.66, -1.96, 1.90)
    b_clip = 0 if is_world else 2  # j_clip: left-side removable 3-bolt cassette (0.76, 0.98, 2.56)

    wood = "mtl_bz_xbow_wood"    # Oiled straight-grain dark walnut (#583520)
    metal = "mtl_bz_xbow_metal"  # Stamped blued steel (#2a2e33)
    brass = "mtl_bz_xbow_brass"  # Weathered brass clamps/turrets only (<=10%)
    glow = "mtl_bz_xbow_glow"    # Opaque unlit sodium-amber (#ffb020) bolt collar & witness nock
    s_cyl = 6 if is_world else 8

    # Straight-grain oiled dark walnut rifle stock, steel buttplate & ergonomic grip
    m.add_tapered_prism(metal, (-7.8, 0.0, -0.25), (-7.0, 0.0, -0.08), 1.08, 1.04, sides=s_cyl, bone_idx=b_gun, scale_y=0.68, scale_z=1.22)
    m.add_tapered_prism(wood, (-7.2, 0.0, -0.10), (0.8, 0.0, 1.02), 1.04, 1.34, sides=s_cyl, bone_idx=b_gun, scale_y=0.72, scale_z=1.18)
    m.add_tapered_prism(wood, (0.5, 0.0, 1.02), (16.8, 0.0, 1.30), 1.30, 1.12, sides=s_cyl, bone_idx=b_gun, scale_y=0.84, scale_z=0.90)
    m.add_tapered_prism(wood, (-1.1, 0.0, -2.85), (-0.2, 0.0, 0.5), 0.70, 0.84, sides=s_cyl, bone_idx=b_gun)
    m.add_box(metal, (1.0, 0.0, -0.95), (2.6, 0.26, 1.22), bone_idx=b_gun)
    m.add_box(metal, (0.65, 0.0, -0.70), (0.26, 0.14, 0.76), bone_idx=b_gun, rot_xyz=(0.0, -18.0, 0.0))

    # Stamped blued-steel receiver & tri-channel bolt flight rail
    m.add_tapered_prism(metal, (1.5, 0.0, 1.92), (6.5, 0.0, 2.02), 1.22, 2.28, sides=s_cyl, bone_idx=b_gun, scale_y=1.04, scale_z=0.38)
    m.add_box(metal, (14.0, 0.0, 2.02), (16.0, 4.5, 0.88), bone_idx=b_gun)
    if not is_world:
        for ry in (-2.05, -0.66, +0.66, +2.05):
            m.add_box(metal, (13.8, ry, 2.52), (15.8, 0.20, 0.26), bone_idx=b_gun)

    # Right-side steel cocking sled & knurled charging knob (skinned to j_bolt!)
    m.add_box(metal, (7.66, -2.18, 1.90), (4.6, 0.34, 0.56), bone_idx=b_bolt)
    m.add_tapered_prism(brass, (7.66, -2.35, 1.90), (7.66, -3.15, 1.90), 0.26, 0.30, sides=4 if is_world else 6, bone_idx=b_bolt)

    # Left-side open removable 3-bolt cassette (skinned to j_clip!) + 3 visible explosive bolts
    m.add_box(metal, (9.4, 0.35, 2.46), (4.4, 4.2, 0.26), bone_idx=b_clip)
    m.add_box(metal, (9.4, 2.42, 2.68), (4.6, 0.24, 0.64), bone_idx=b_clip)
    m.add_box(brass, (9.4, 0.35, 2.62), (0.92, 4.1, 0.16), bone_idx=b_clip)
    s_bolt = 4 if is_world else 5
    for by in (-1.34, 0.0, +1.34):
        m.add_tapered_prism(metal, (7.0, by, 2.64), (21.8, by, 2.64), 0.15, 0.15, sides=s_bolt, bone_idx=b_clip)
        # Opaque sodium-amber explosive collar + dark stepped steel broadhead + amber tail witness nock
        m.add_tapered_prism(glow, (21.4, by, 2.64), (22.6, by, 2.64), 0.25, 0.25, sides=s_bolt, bone_idx=b_clip)
        m.add_tapered_prism(metal, (22.5, by, 2.64), (25.2, by, 2.64), 0.34, 0.05, sides=4, bone_idx=b_clip, angle_offset_deg=45.0)
        if not is_world:
            m.add_tapered_prism(glow, (6.7, by, 2.64), (7.3, by, 2.64), 0.19, 0.17, sides=s_bolt, bone_idx=b_clip)

    # Heavy riveted forward steel riser + 2 bolted U-bolt clamps
    m.add_box(metal, (20.8, 0.0, 2.08), (3.1, 5.8, 1.88), bone_idx=b_gun)
    for side in (-1.0, +1.0):
        m.add_box(brass, (20.8, side * 2.95, 2.08), (1.30, 0.85, 1.98), bone_idx=b_gun)

    # 3 stepped truck leaf-spring steel prods (+/- 11.6u wide, canted slightly down below reticle core, ZERO pulley cams!)
    leaf_spans = (
        ((1.00, 0.00, 0.36), (0.70, +0.34, 0.28))
        if is_world
        else ((1.00, 0.00, 0.34), (0.70, +0.34, 0.28), (0.45, -0.34, 0.24))
    )
    for side in (-1.0, +1.0):
        base_pts = [
            (20.6, side * 2.5, 2.15),
            (20.0, side * 5.8, 2.05),
            (18.0, side * 9.0, 1.92),
            (14.8, side * 11.6, 1.78),
        ]
        for span_frac, dz, thick in leaf_spans:
            segs = 3 if span_frac >= 0.99 else (2 if span_frac >= 0.65 else 1)
            for i in range(segs):
                p0 = (base_pts[i][0], base_pts[i][1], base_pts[i][2] + dz)
                p1 = (base_pts[i + 1][0], base_pts[i + 1][1], base_pts[i + 1][2] + dz)
                m.add_tapered_prism(metal, p0, p1, thick, thick * 0.82, sides=4, bone_idx=b_gun, scale_y=0.55, scale_z=1.35)
        # U-bolt spring clamp midway along stacked leaves
        m.add_box(brass, (19.6, side * 6.2, 2.04), (0.72, 0.62, 1.24), bone_idx=b_gun)
        # Plain forged hooked steel tip (zero modern pulley wheel!) + taut braided steel bowstring
        tip = base_pts[-1]
        hook_end = (tip[0] - 0.65, tip[1] + side * 0.25, tip[2])
        m.add_tapered_prism(metal, tip, hook_end, 0.24, 0.16, sides=4 if is_world else 6, bone_idx=b_gun)
        m.add_tapered_prism(metal, hook_end, (6.5, 0.0, 2.66), 0.075, 0.075, sides=4, bone_idx=b_gun, cap_start=False, cap_end=False)

    # Open forged steel foot-stirrup loop (canted cleanly downward below reticle!)
    stirrup = [
        (22.0, -2.3, 1.55),
        (25.4, -2.0, 0.82),
        (26.5, 0.0, 0.58),
        (25.4, +2.0, 0.82),
        (22.0, +2.3, 1.55),
    ]
    for i in range(len(stirrup) - 1):
        m.add_tapered_prism(metal, stirrup[i], stirrup[i + 1], 0.22, 0.22, sides=4 if is_world else 6, bone_idx=b_gun)

    # Compact matte-black 1945 ZFG42 optic scope (brass turrets only, strictly below Z=3.60 -> 0 ADS occlusion!)
    m.add_box(metal, (0.9, -0.18, 2.74), (0.68, 0.80, 0.54), bone_idx=b_gun)
    m.add_box(metal, (5.0, -0.18, 2.74), (0.68, 0.80, 0.54), bone_idx=b_gun)
    m.add_tapered_prism(metal, (-0.6, -0.18, 3.04), (7.8, -0.18, 3.04), 0.35, 0.42, sides=s_cyl, bone_idx=b_gun)
    if not is_world:
        m.add_tapered_prism(brass, (3.0, +0.20, 3.04), (3.0, +0.58, 3.04), 0.17, 0.17, sides=6, bone_idx=b_gun)
        m.add_tapered_prism(brass, (3.0, -0.52, 3.04), (3.0, -0.88, 3.04), 0.17, 0.17, sides=6, bone_idx=b_gun)

    return m


def build_crossbow_bolt() -> MeshBuilder:
    """Authentic ~11u 1945 explosive bolt (dark barbed steel head, #ffb020 collar & witness nock, <=400 verts)."""
    m = MeshBuilder("bz_crossbow_bolt", BONES_RIGID, model_type="rigid")
    metal = "mtl_bz_xbow_metal"
    brass = "mtl_bz_xbow_brass"
    glow = "mtl_bz_xbow_glow"

    # Total length ~11.2u (-5.6..+5.6) per NORTHSTAR_SPEC.md §3.3
    m.add_tapered_prism(metal, (-5.1, 0.0, 0.0), (2.4, 0.0, 0.0), 0.22, 0.22, sides=8, bone_idx=0)
    # Brass collar + opaque unlit sodium-amber (#ffb020) explosive charge collar
    m.add_tapered_prism(brass, (1.8, 0.0, 0.0), (2.5, 0.0, 0.0), 0.34, 0.38, sides=8, bone_idx=0)
    m.add_tapered_prism(glow, (2.45, 0.0, 0.0), (3.35, 0.0, 0.0), 0.42, 0.42, sides=8, bone_idx=0)
    # Dark stepped barbed forged-steel broadhead (zero glowing tip!)
    m.add_tapered_prism(metal, (3.3, 0.0, 0.0), (5.6, 0.0, 0.0), 0.62, 0.05, sides=4, bone_idx=0, angle_offset_deg=45.0)
    # 3 dark stamped steel fletching vanes
    for fdeg in (0.0, 120.0, 240.0):
        rad = math.radians(fdeg)
        cy, cz = math.cos(rad), math.sin(rad)
        p0 = (-4.9, cy * 0.20, cz * 0.20)
        p1 = (-2.1, cy * 0.20, cz * 0.20)
        p2 = (-3.4, cy * 1.15, cz * 1.15)
        p3 = (-5.2, cy * 1.05, cz * 1.05)
        m.add_quad(metal, p0, p1, p2, p3, bone_idx=0, double_sided=True)
    # Opaque unlit sodium-amber (#ffb020) tail witness nock
    m.add_tapered_prism(glow, (-5.6, 0.0, 0.0), (-4.9, 0.0, 0.0), 0.34, 0.26, sides=8, bone_idx=0)
    return m


# ---------------------------------------------------------------------------
# 3. BLADE BOOMERANG (WWII Aircraft Propeller Tri-Blade — Cold Steel + Crimson Hub/Tip Pellets)
# ---------------------------------------------------------------------------


def build_blade_boomerang_held(name: str, is_world: bool = False) -> MeshBuilder:
    """WWII propeller tri-blade boomerang (<=4.5u 1P / 8.62u WM) w/ leather stirrup grip & 1 wrapped ID blade."""
    bones = world_weapon_bones((4.5, 0.0, 2.05)) if is_world else BONES_COLT45
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0

    steel = "mtl_bz_blade_steel"
    leather = "mtl_bz_blade_leather"
    brass = "mtl_bz_blade_brass"
    glow = "mtl_bz_blade_glow"  # Industrial crimson (#e81e50) hub ring + 3 small tip tracer pellets!

    scale = 2.45 if is_world else 1.0
    hub: Vec3 = (0.35 * scale, 0.0, 2.05 * scale)
    s_hub = 10 if is_world else 12
    blade_steps = 6 if is_world else 8

    # Compact stitched-leather stirrup throwing grip seated in palm + continuous knuckle-gap collar into hub
    m.add_tapered_prism(leather, (0.0, 0.0, -2.35), (0.0, 0.0, 0.85), 0.36, 0.35, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(brass, (0.0, 0.0, -2.68), (0.0, 0.0, -2.30), 0.44, 0.38, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(brass, (0.0, 0.0, 0.78), hub, 0.40, 0.54 * scale, sides=8, bone_idx=b_gun)

    # Machined bronze/gunmetal propeller gyro-hub + crimson (#e81e50) hub ring
    hub_axis = v_norm((-0.72, 0.42, 0.55))
    m.add_tapered_prism(
        brass,
        v_sub(hub, v_scale(hub_axis, 0.24 * scale)),
        v_add(hub, v_scale(hub_axis, 0.24 * scale)),
        0.78 * scale,
        0.78 * scale,
        sides=s_hub,
        bone_idx=b_gun,
    )
    m.add_tapered_prism(
        glow,
        v_sub(hub, v_scale(hub_axis, 0.28 * scale)),
        v_add(hub, v_scale(hub_axis, 0.28 * scale)),
        0.38 * scale,
        0.38 * scale,
        sides=s_hub,
        bone_idx=b_gun,
    )

    # 3 airfoil-tapered COLD brushed-steel propeller blades (glow_outer=False!) + 1 crimson tip pellet each
    # Arm 0 carries the EXACT ONE asymmetric leather-wrapped + yellow-brass ID spine band!
    u_axis = v_norm((0.62, 0.52, 0.58))
    v_axis = v_norm(v_cross(hub_axis, u_axis))
    for arm in range(3):
        base_deg = arm * 120.0 + 15.0
        pts: list[Vec3] = []
        ws: list[float] = []
        ts: list[float] = []
        for k in range(blade_steps):
            u = k / (blade_steps - 1)
            r = (0.62 + u * 2.84) * scale
            ang = math.radians(base_deg + u * 34.0)
            local = v_add(v_scale(u_axis, math.cos(ang) * r), v_scale(v_axis, math.sin(ang) * r))
            pts.append(v_add(hub, local))
            ws.append((0.76 * (1.0 - 0.42 * u) + 0.16 * math.sin(u * math.pi)) * scale)
            ts.append((0.20 * (1.0 - 0.55 * u)) * scale)
        m.add_swept_blade(steel, glow, pts, ws, ts, normal_axis=hub_axis, bone_idx=b_gun, glow_outer=False)

        # Single small round crimson (#e81e50) tracer pellet recessed near each blade tip
        tip_pt = pts[-2]
        m.add_tapered_prism(
            glow,
            v_sub(tip_pt, v_scale(hub_axis, 0.12 * scale)),
            v_add(tip_pt, v_scale(hub_axis, 0.12 * scale)),
            0.16 * scale,
            0.16 * scale,
            sides=6,
            bone_idx=b_gun,
        )
        # Asymmetric leather-wrapped + yellow-brass ID band on Arm 0 ONLY!
        if arm == 0:
            m.add_tapered_prism(leather, pts[1], pts[3], 0.34 * scale, 0.30 * scale, sides=6, bone_idx=b_gun)
            m.add_tapered_prism(brass, pts[3], pts[4], 0.28 * scale, 0.26 * scale, sides=6, bone_idx=b_gun)

    return m


def build_blade_boomerang_air() -> MeshBuilder:
    """Airborne YZ-plane WWII propeller tri-blade (10.15u radius, <=750 verts, matching Arm 0 ID wrap)."""
    m = MeshBuilder("bz_boomerang_blade_air", BONES_RIGID, model_type="rigid")
    steel = "mtl_bz_blade_steel"
    leather = "mtl_bz_blade_leather"
    brass = "mtl_bz_blade_brass"
    glow = "mtl_bz_blade_glow"

    # Spin axis along +X for wobble-free RotateRoll
    m.add_tapered_prism(brass, (-0.58, 0.0, 0.0), (+0.58, 0.0, 0.0), 1.92, 1.92, sides=8, bone_idx=0)
    m.add_tapered_prism(glow, (-0.68, 0.0, 0.0), (+0.68, 0.0, 0.0), 1.02, 1.02, sides=8, bone_idx=0)

    for arm in range(3):
        base_deg = arm * 120.0 + 15.0
        pts: list[Vec3] = []
        ws: list[float] = []
        ts: list[float] = []
        for k in range(5):
            u = k / 4.0
            r = 1.48 + u * 8.67
            rad = math.radians(base_deg + u * 30.0)
            pts.append((0.0, math.cos(rad) * r, math.sin(rad) * r))
            ws.append(2.15 * (1.0 - 0.42 * u) + 0.44 * math.sin(u * math.pi))
            ts.append(0.58 * (1.0 - 0.55 * u))
        m.add_swept_blade(steel, glow, pts, ws, ts, normal_axis=(1.0, 0.0, 0.0), bone_idx=0, glow_outer=False)

        # Single crimson tip tracer pellet per blade
        tp = pts[-2]
        m.add_tapered_prism(glow, (-0.34, tp[1], tp[2]), (+0.34, tp[1], tp[2]), 0.44, 0.44, sides=5, bone_idx=0)
        # Matching Arm 0 asymmetric leather-wrapped + brass ID band
        if arm == 0:
            m.add_tapered_prism(leather, pts[1], pts[2], 0.88, 0.80, sides=5, bone_idx=0)
            m.add_tapered_prism(brass, pts[2], pts[3], 0.74, 0.68, sides=5, bone_idx=0)

    return m


# ---------------------------------------------------------------------------
# 4. ACID SPRAYER (1945 Flammenwerfer-41 Chemical Wand — Low Olivgruen Tank + Plain Bell)
# ---------------------------------------------------------------------------


def build_acid_sprayer(name: str, is_world: bool = False) -> MeshBuilder:
    bones = world_weapon_bones((17.71, 0.0, -0.29)) if is_world else BONES_FLAMETHROWER
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0

    metal = "mtl_bz_acid_metal"    # Panzergrau / parkerized steel (#363c42)
    enamel = "mtl_bz_acid_hazard"  # Olivgruen / Feldgrau enamel (#424b3a) w/ Gruenkreuz stencil
    glow = "mtl_bz_acid_glow"      # Opaque unlit bright lime-green (#68f030) sight slit
    brass = "mtl_bz_xbow_brass"    # Weathered brass rear-dome dial bezel (<=10%, within 4-slot cap)
    s_cyl = 8 if is_world else 10

    # Plain steel rear wand manifold + angled dark Bakelite pistol grip (zero butt-cap dial!)
    m.add_tapered_prism(metal, (-5.6, -0.95, -1.15), (-0.8, -0.15, -0.28), 0.90, 1.18, sides=s_cyl, bone_idx=b_gun)
    m.add_tapered_prism(metal, (-4.3, -2.45, -4.05), (-2.1, -1.30, -1.10), 0.70, 0.78, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(metal, (-3.0, -1.80, -2.15), (-0.4, -0.35, -0.42), 0.50, 0.60, sides=8, bone_idx=b_gun)

    # Clean Panzergrau Flammenwerfer-41 main wand tube + forward left-hand grip sleeve
    m.add_tapered_prism(metal, (-1.0, 0.0, -0.25), (14.8, 0.0, -0.29), 1.16, 0.98, sides=s_cyl, bone_idx=b_gun)
    m.add_tapered_prism(metal, (4.6, 0.0, -0.96), (10.6, 0.0, -0.96), 0.88, 0.84, sides=8, bone_idx=b_gun)
    for bx in (2.2, 9.6):
        m.add_box(metal, (bx, 1.28, 0.24), (0.95, 1.65, 0.52), bone_idx=b_gun)

    # Dominant Mass 1: Low squat armored Olivgruen outboard-left reagent tank (y=+2.45, top Z <= 1.98!)
    m.add_tapered_prism(enamel, (0.6, 2.45, 0.68), (11.0, 2.45, 0.68), 1.24, 1.24, sides=s_cyl, bone_idx=b_gun)
    # Domed brushed-steel front & rear tank end-caps + brass-bezel analog pressure dial on rear dome!
    m.add_tapered_prism(metal, (-0.35, 2.45, 0.68), (0.65, 2.45, 0.68), 0.74, 1.24, sides=s_cyl, bone_idx=b_gun)
    m.add_tapered_prism(brass, (-0.72, 2.45, 0.68), (-0.28, 2.45, 0.68), 0.54, 0.58, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(glow, (-0.78, 2.45, 0.68), (-0.68, 2.45, 0.68), 0.34, 0.34, sides=8, bone_idx=b_gun, cap_end=False)
    m.add_tapered_prism(metal, (10.95, 2.45, 0.68), (11.85, 2.45, 0.68), 1.24, 0.58, sides=s_cyl, bone_idx=b_gun)
    # Two riveted steel mounting straps + ONE recessed armored #68f030 reagent sight-slit (<=30% vessel surface!)
    for ring_x in (3.2, 8.4):
        m.add_tapered_prism(metal, (ring_x - 0.24, 2.45, 0.68), (ring_x + 0.24, 2.45, 0.68), 1.30, 1.30, sides=s_cyl, bone_idx=b_gun)
    m.add_box(glow, (5.8, 2.45, 1.88), (4.6, 0.36, 0.14), bone_idx=b_gun)
    m.add_box(glow, (5.8, 3.64, 0.68), (4.6, 0.14, 0.36), bone_idx=b_gun)
    # Armored chemical feed tube from tank dome into nozzle manifold
    m.add_tapered_prism(metal, (11.6, 2.45, 0.68), (14.0, 0.72, -0.08), 0.36, 0.32, sides=6, bone_idx=b_gun)

    # Dominant Mass 2: Compact plain rolled cast-iron flared diffuser bell (OD ~2.6u -> r=1.30u on tag_flash, 0 crenellations!)
    m.add_tapered_prism(brass, (14.4, 0.0, -0.29), (15.1, 0.0, -0.29), 1.06, 1.12, sides=s_cyl, bone_idx=b_gun)
    m.add_tapered_prism(metal, (15.0, 0.0, -0.29), (17.71, 0.0, -0.29), 1.02, 1.32, sides=s_cyl, bone_idx=b_gun)
    m.add_tapered_prism(glow, (17.25, 0.0, -0.29), (17.74, 0.0, -0.29), 0.88, 0.96, sides=s_cyl, bone_idx=b_gun, cap_start=False)

    return m


# ---------------------------------------------------------------------------
# 5. PORTAL GRENADE (1945 Stick Handle + 4-Prong Chalice + 1 Meridian Hoop + E115 Shard)
# ---------------------------------------------------------------------------


def _add_gyro_ring(
    m: MeshBuilder,
    mat_name: str,
    center: Vec3,
    radius: float,
    tube_r: float,
    axis_u: Vec3,
    axis_v: Vec3,
    segs: int = 16,
    bone_idx: int = 0,
) -> None:
    for s in range(segs):
        a0 = math.radians(360.0 * s / segs)
        a1 = math.radians(360.0 * (s + 1) / segs)
        p0 = v_add(center, v_add(v_scale(axis_u, math.cos(a0) * radius), v_scale(axis_v, math.sin(a0) * radius)))
        p1 = v_add(center, v_add(v_scale(axis_u, math.cos(a1) * radius), v_scale(axis_v, math.sin(a1) * radius)))
        m.add_tapered_prism(mat_name, p0, p1, tube_r, tube_r, sides=4, bone_idx=bone_idx, cap_start=False, cap_end=False)


def _add_octa_sphere_core(
    m: MeshBuilder,
    mat_name: str,
    center: Vec3,
    radius: float,
    bone_idx: int = 0,
    sides: int = 8,
) -> None:
    # Faceted raw Element-115 crystal shard (asymmetric mineral facets, watertight)
    z_bands = (-1.0, -0.62, -0.18, 0.26, 0.72, 1.0)
    r_bands = (0.06, 0.62, 0.96, 0.92, 0.58, 0.06)
    for i in range(len(z_bands) - 1):
        p0 = (center[0], center[1], center[2] + z_bands[i] * radius)
        p1 = (center[0], center[1], center[2] + z_bands[i + 1] * radius)
        m.add_tapered_prism(
            mat_name,
            p0,
            p1,
            r_bands[i] * radius,
            r_bands[i + 1] * radius,
            sides=sides,
            bone_idx=bone_idx,
            cap_start=(i == 0),
            cap_end=(i == len(z_bands) - 2),
        )


def build_portal_grenade_held(name: str, is_world: bool = False) -> MeshBuilder:
    """Held Portal Grenade: stick handle + 4-prong chalice + 1 meridian hoop + equatorial clamp (ZERO top spire!)."""
    bones = world_weapon_bones((4.0, 0.0, 2.0)) if is_world else BONES_COLT45
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0

    ring = "mtl_bz_portal_ring"  # Blued steel / dark iron
    core = "mtl_bz_portal_core"  # Faceted dark-violet Element-115 shard (#8e22da)
    trim = "mtl_bz_portal_trim"  # Riveted weathered brass collar & prongs

    scale = 1.65 if is_world else 1.0
    center: Vec3 = (1.5 * scale, 0.0, 2.15 * scale)
    segs = 12 if is_world else 16

    # Short knurled dark-iron Stielhandgranate stick handle + riveted brass collar
    m.add_tapered_prism(ring, (0.0, 0.0, -2.0 * scale), (0.35 * scale, 0.0, 0.15 * scale), 0.36 * scale, 0.44 * scale, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(trim, (0.32 * scale, 0.0, 0.10 * scale), (center[0] * 0.72, 0.0, center[2] - 1.30 * scale), 0.56 * scale, 0.78 * scale, sides=8, bone_idx=b_gun)

    # Visible 4-prong steel/brass chalice cradling the raw Element-115 shard
    chalice_base = (center[0] * 0.75, 0.0, center[2] - 1.25 * scale)
    for deg in (45.0, 135.0, 225.0, 315.0):
        rad = math.radians(deg)
        dx, dy = math.cos(rad), math.sin(rad)
        p0 = v_add(chalice_base, (dx * 0.56 * scale, dy * 0.56 * scale, 0.0))
        p1 = v_add(center, (dx * 1.48 * scale, dy * 1.48 * scale, -0.25 * scale))
        p2 = v_add(center, (dx * 1.56 * scale, dy * 1.56 * scale, +0.42 * scale))
        m.add_tapered_prism(trim, p0, p1, 0.14 * scale, 0.12 * scale, sides=6, bone_idx=b_gun)
        m.add_tapered_prism(ring, p1, p2, 0.12 * scale, 0.08 * scale, sides=6, bone_idx=b_gun)

    # Faceted dark-violet Element-115 crystal shard (core radius 1.38u held / 2.28u world)
    _add_octa_sphere_core(m, core, center, 1.38 * scale, bone_idx=b_gun, sides=8)

    # EXACTLY ONE thick rectangular-section blued-steel meridian hoop + ONE equatorial clamp ring (ZERO top pole spire!)
    _add_gyro_ring(m, ring, center, 2.02 * scale, 0.18 * scale, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), segs=segs, bone_idx=b_gun)
    _add_gyro_ring(m, trim, center, 1.72 * scale, 0.13 * scale, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), segs=segs, bone_idx=b_gun)
    return m


def build_portal_orb_air() -> MeshBuilder:
    """Deployed Portal Anchor (25u exact tip-to-tip height +-12.5u, full 360-deg equatorial + meridian hoop, <=900v)."""
    m = MeshBuilder("bz_portal_orb_air", BONES_RIGID, model_type="rigid")
    ring = "mtl_bz_portal_ring"
    core = "mtl_bz_portal_core"
    trim = "mtl_bz_portal_trim"

    center: Vec3 = (0.0, 0.0, 0.0)
    _add_octa_sphere_core(m, core, center, 5.8, bone_idx=0, sides=6)
    # 1 thick blued-steel meridian hoop + 1 full 360-deg equatorial clamp ring (never reads flat edge-on during RotateYaw!)
    _add_gyro_ring(m, ring, center, 8.8, 0.78, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), segs=12, bone_idx=0)
    _add_gyro_ring(m, trim, center, 8.0, 0.62, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), segs=12, bone_idx=0)
    # 4 equatorial clamp lugs
    for deg in (0.0, 90.0, 180.0, 270.0):
        rad = math.radians(deg)
        p0 = (math.cos(rad) * 7.4, math.sin(rad) * 7.4, 0.0)
        p1 = (math.cos(rad) * 9.5, math.sin(rad) * 9.5, 0.0)
        m.add_tapered_prism(ring, p0, p1, 0.68, 0.42, sides=4, bone_idx=0)
    # Twin tapered pole emitter spires spanning exact +/-12.5u (25.0u tip-to-tip!)
    m.add_tapered_prism(trim, (0.0, 0.0, 7.6), (0.0, 0.0, 12.5), 0.95, 0.16, sides=6, bone_idx=0)
    m.add_tapered_prism(trim, (0.0, 0.0, -7.6), (0.0, 0.0, -12.5), 0.95, 0.16, sides=6, bone_idx=0)
    return m


# ---------------------------------------------------------------------------
# 6. WAR CLUB (1945 Trench-Knife D-Guard + Domed Pommel + Octagonal 8-Lug Solenoid Head)
# ---------------------------------------------------------------------------


def build_war_club_held(name: str, is_world: bool) -> MeshBuilder:
    """Flared octagonal cast-iron War Club w/ D-guard knuckle bow, domed pommel (0 butt spike) & 8+1 pyramidal lugs."""
    bones = world_weapon_bones((12.0, 0.0, 2.5)) if is_world else BONES_COLT45
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0
    s = 1.85 if is_world else 1.0

    wood = "mtl_bz_club_wood"
    iron = "mtl_bz_club_iron"
    glow = "mtl_bz_club_glow"  # Deep forge red-orange (#ff4a12) recessed solenoid coils
    leather = "mtl_bz_blade_leather"

    def pt(t: float) -> Vec3:
        return ((-1.2 + t * 11.4) * s, 0.0, (-2.4 + t * 10.6) * s)

    axis = v_norm(v_sub(pt(1.0), pt(0.0)))
    side_u = (0.0, 1.0, 0.0)
    side_v = v_norm(v_cross(axis, side_u))

    # 1. Compact domed iron pommel (ZERO butt spike!)
    m.add_tapered_prism(iron, pt(-0.05), pt(0.02), 0.42 * s, 0.72 * s, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(iron, pt(0.02), pt(0.08), 0.72 * s, 0.60 * s, sides=8, bone_idx=b_gun)

    # 2. Stitched leather grip + forged blackened-steel WWI trench-knife D-guard knuckle bow
    m.add_tapered_prism(leather, pt(0.08), pt(0.40), 0.54 * s, 0.58 * s, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(iron, pt(0.38), pt(0.43), 0.66 * s, 0.66 * s, sides=8, bone_idx=b_gun)
    # D-guard knuckle bow wrapping forward (+side_v) from upper guard to pommel
    dguard_pts = [
        v_add(pt(0.03), v_scale(side_v, 0.50 * s)),
        v_add(pt(0.08), v_scale(side_v, 1.42 * s)),
        v_add(pt(0.24), v_scale(side_v, 1.62 * s)),
        v_add(pt(0.37), v_scale(side_v, 1.42 * s)),
        v_add(pt(0.41), v_scale(side_v, 0.56 * s)),
    ]
    for i in range(len(dguard_pts) - 1):
        m.add_tapered_prism(iron, dguard_pts[i], dguard_pts[i + 1], 0.16 * s, 0.16 * s, sides=6, bone_idx=b_gun)

    # 3. Straight charred ash shaft flaring into heavy octagonal (sides=8) cast-iron striking head
    m.add_tapered_prism(wood, pt(0.42), pt(0.64), 0.62 * s, 0.88 * s, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(iron, pt(0.62), pt(0.69), 0.96 * s, 1.12 * s, sides=8, bone_idx=b_gun)
    # Recessed inner copper kinetic solenoid coil cylinder + 4 alternating vertical iron ribs framing 4 coil windows!
    m.add_tapered_prism(glow, pt(0.68), pt(0.90), 1.06 * s, 1.24 * s, sides=8, bone_idx=b_gun)
    for k in range(4):
        ang = math.radians(k * 90.0 + 22.5)
        rad_dir = v_add(v_scale(side_u, math.cos(ang)), v_scale(side_v, math.sin(ang)))
        r_p0 = v_add(pt(0.68), v_scale(rad_dir, 1.10 * s))
        r_p1 = v_add(pt(0.91), v_scale(rad_dir, 1.28 * s))
        m.add_tapered_prism(iron, r_p0, r_p1, 0.34 * s, 0.38 * s, sides=4, bone_idx=b_gun)

    # 4. Single bolted upper cast-iron collar studded with 8 thick pyramidal iron lugs (1 per octagon face!) + 1 crown lug
    m.add_tapered_prism(iron, pt(0.89), pt(0.99), 1.34 * s, 1.38 * s, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(iron, pt(0.98), pt(1.06), 1.34 * s, 0.78 * s, sides=8, bone_idx=b_gun)
    # 1 stout pyramidal crown lug
    m.add_tapered_prism(iron, pt(1.05), pt(1.16), 0.48 * s, 0.14 * s, sides=4, bone_idx=b_gun, angle_offset_deg=45.0)
    # 8 thick pyramidal collar lugs (1 per octagon face at 45-deg intervals)
    c_collar = pt(0.94)
    for k in range(8):
        ang = math.radians(k * 45.0)
        rad_dir = v_add(v_scale(side_u, math.cos(ang)), v_scale(side_v, math.sin(ang)))
        sp0 = v_add(c_collar, v_scale(rad_dir, 1.28 * s))
        sp1 = v_add(c_collar, v_scale(rad_dir, 1.98 * s))
        m.add_tapered_prism(iron, sp0, sp1, 0.30 * s, 0.08 * s, sides=4, bone_idx=b_gun, angle_offset_deg=45.0)
    return m


# ---------------------------------------------------------------------------
# 7. STATION KIOSKS (4 Distinct 1945 Group 935 Silhouettes — +X Front, z=-4..0 Skirt, <=72u H)
# ---------------------------------------------------------------------------


def build_station_kiosk(name: str, kind: str) -> MeshBuilder:
    """1945 Group 935 Station Kiosk (rigid tag_origin, +X front, z=-4..0 burial skirt, <=72u H, <=1,500 verts)."""
    m = MeshBuilder(name, BONES_RIGID, model_type="rigid")
    frame = "mtl_bz_kiosk_frame"  # Bolted Panzergrau cast iron (#363c42)
    brass = "mtl_bz_kiosk_brass"  # Restrained weathered brass (<=10%)
    glow_by_kind = {
        "perks": "mtl_bz_kiosk_perks_glow",
        "class": "mtl_bz_kiosk_class_glow",
        "arsenal": "mtl_bz_kiosk_arsenal_glow",
        "pap": "mtl_bz_kiosk_pap_glow",
    }
    glow = glow_by_kind[kind]

    def add_aabb(mat: str, x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> None:
        m.add_box(
            mat,
            ((x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5),
            (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)),
            bone_idx=0,
        )

    if kind == "perks":
        # 1) Specialty Perk Station (26u W x 22u D x 70u H, Emerald #12a856)
        # Tall narrow rounded-arch Group 935 Serum & Ampoule Dispensary w/ z=-4..0 burial skirt!
        add_aabb(frame, -11.0, -13.0, -4.0, 11.0, 13.0, 6.0)
        add_aabb(brass, -10.2, -12.2, 6.0, 10.2, 12.2, 7.6)
        # Main cabinet + stepped rounded arch crown peaking cleanly at z=70.0u
        add_aabb(frame, -10.0, -12.0, 7.6, 8.8, 12.0, 56.0)
        add_aabb(frame, -9.5, -10.4, 56.0, 8.6, 10.4, 63.0)
        add_aabb(frame, -9.0, -7.8, 63.0, 8.4, 7.8, 67.6)
        add_aabb(frame, -8.5, -4.6, 67.6, 8.0, 4.6, 70.0)
        # 3 recessed armored emerald sight-chambers (<=30% front surface!)
        for ty in (-6.8, 0.0, 6.8):
            m.add_tapered_prism(frame, (8.6, ty, 24.0), (8.6, ty, 52.0), 2.1, 2.1, sides=8, bone_idx=0)
            add_aabb(glow, 9.8, ty - 0.9, 27.0, 10.8, ty + 0.9, 49.0)
            m.add_tapered_prism(brass, (8.6, ty, 22.0), (8.6, ty, 24.6), 2.3, 2.3, sides=8, bone_idx=0)
            m.add_tapered_prism(brass, (8.6, ty, 51.4), (8.6, ty, 53.8), 2.3, 2.3, sides=8, bone_idx=0)
        # Brass dispensing tap + catch basin on front (+X, <=3u overhang!)
        add_aabb(frame, 8.8, -8.5, 11.0, 11.4, 8.5, 14.0)
        m.add_tapered_prism(brass, (8.8, 0.0, 19.0), (11.2, 0.0, 19.0), 0.75, 0.55, sides=6, bone_idx=0)
        m.add_tapered_prism(brass, (11.0, 0.0, 19.2), (11.0, 0.0, 16.4), 0.48, 0.40, sides=6, bone_idx=0)
        add_aabb(glow, 8.4, -7.0, 57.5, 9.6, 7.0, 61.5)

    elif kind == "class":
        # 2) Class Station (32u W x 26u D x 58u H, Cobalt #186ce2)
        # Waist-high Group 935 Field Command Switchboard Lectern + open rear fork yoke & "935" chevron crest!
        add_aabb(frame, -13.0, -16.0, -4.0, 13.0, 16.0, 6.0)
        add_aabb(frame, -11.5, -14.5, 6.0, 10.5, 14.5, 34.0)
        # Sloped backlit frosted map-glass console plate under riveted steel bezel (zero LCD/joystick!)
        m.add_box(frame, (0.5, 0.0, 36.8), (22.0, 29.0, 6.4), bone_idx=0, rot_xyz=(0.0, 16.0, 0.0))
        m.add_box(glow, (1.8, 0.0, 40.0), (16.5, 22.5, 1.2), bone_idx=0, rot_xyz=(0.0, 16.0, 0.0))
        # Tactile rotary brass dial knobs along lower console edge
        for dy in (-9.0, -3.0, +3.0, +9.0):
            m.add_tapered_prism(brass, (9.8, dy, 35.4), (11.2, dy, 36.2), 0.85, 0.78, sides=6, bone_idx=0)
        # Open rear steel fork yoke holding circular stamped shield crest (peaking cleanly at z=58.0u!)
        for sy in (-9.5, +9.5):
            add_aabb(frame, -10.5, sy - 1.4, 34.0, -7.5, sy + 1.4, 52.0)
        add_aabb(frame, -10.5, -9.5, 49.5, -7.5, 9.5, 52.0)
        m.add_tapered_prism(frame, (-10.8, 0.0, 51.5), (-7.2, 0.0, 51.5), 6.5, 6.5, sides=10, bone_idx=0)
        m.add_tapered_prism(brass, (-7.4, 0.0, 51.5), (-6.8, 0.0, 51.5), 5.6, 5.6, sides=10, bone_idx=0)
        m.add_tapered_prism(glow, (-7.0, 0.0, 51.5), (-6.4, 0.0, 51.5), 4.0, 4.0, sides=8, bone_idx=0)

    elif kind == "arsenal":
        # 3) Arsenal & Squad Workbench (54u W x 28u D x 62u H, Amber #de7616)
        # Wide low armored Field Armorer's Workbench w/ front-left bench vise, backlit rifle wall & flush hood!
        add_aabb(frame, -14.0, -27.0, -4.0, 14.0, 27.0, 5.0)
        # Bolted tool chest base + thick armored steel bench slab (z=30..33u)
        add_aabb(frame, -13.0, -25.5, 5.0, 12.5, 25.5, 30.0)
        add_aabb(brass, -13.5, -26.2, 30.0, 13.5, 26.2, 32.8)
        # Forged front-left bench vise (y=+16..24, x=+9..15 -> unmistakable workbench silhouette!)
        add_aabb(frame, 8.5, 17.0, 32.8, 15.2, 23.0, 38.2)
        m.add_tapered_prism(brass, (14.8, 20.0, 35.4), (16.4, 20.0, 35.4), 0.72, 0.72, sides=6, bone_idx=0)
        m.add_tapered_prism(brass, (16.0, 16.5, 35.4), (16.0, 23.5, 35.4), 0.34, 0.34, sides=6, bone_idx=0)
        # Rear armored tool wall + recessed opaque amber backlit panel silhouetting 3 dark racked rifle cards
        add_aabb(frame, -13.5, -26.0, 32.8, -5.0, 26.0, 58.0)
        add_aabb(glow, -5.0, -22.5, 37.0, -3.6, 22.5, 55.5)
        for rz in (40.5, 46.5, 52.0):
            # Ultra-low-poly racked rifle silhouette card (dark steel over amber backlit wall!)
            add_aabb(frame, -3.5, -18.0, rz, -2.1, 18.0, rz + 1.8)
            add_aabb(frame, -3.5, -14.0, rz - 1.4, -2.1, -4.0, rz)
        # Side uprights + flush overhead hood (<=3u overhang, peaking at z=62.0u!)
        for sy in (-25.0, +25.0):
            add_aabb(frame, -13.5, sy - 1.5, 32.8, 2.0, sy + 1.5, 58.5)
        add_aabb(frame, -14.0, -26.5, 58.0, 3.0, 26.5, 62.0)

    else:
        # 4) Pack-a-Punch Prototype Processing Press (42u W x 30u D x 68u H, Violet #8e22da)
        # Squat heavy armored press w/ horizontal intake bay, twin steel rollers, right flue & flat "935" header!
        add_aabb(frame, -15.0, -21.0, -4.0, 15.0, 21.0, 6.0)
        # Broad heavy riveted cast-iron lower shoulders + weapon-intake bay
        add_aabb(frame, -14.0, -20.0, 6.0, 13.0, 20.0, 22.0)
        for sy in (-16.5, +16.5):
            add_aabb(frame, -14.0, sy - 3.5, 22.0, 13.0, sy + 3.5, 58.0)
        add_aabb(frame, -14.0, -13.0, 22.0, 5.0, 13.0, 58.0)
        # Recessed horizontal weapon-intake bay w/ opaque violet plasma slit & twin smooth steel rollers
        add_aabb(glow, 5.0, -11.5, 26.0, 7.2, 11.5, 38.0)
        m.add_tapered_prism(frame, (9.2, -12.6, 25.0), (9.2, +12.6, 25.0), 2.1, 2.1, sides=10, bone_idx=0)
        m.add_tapered_prism(frame, (9.2, -12.6, 39.0), (9.2, +12.6, 39.0), 2.1, 2.1, sides=10, bone_idx=0)
        # Flat heavy armored upper press header & "935" nameplate peaking cleanly at z=68.0u (ZERO pyramid spire!)
        add_aabb(frame, -14.5, -20.5, 58.0, 13.5, 20.5, 68.0)
        add_aabb(brass, 13.0, -11.0, 60.0, 14.2, 11.0, 66.0)
        add_aabb(glow, 12.6, -12.0, 45.0, 13.6, 12.0, 53.0)
        # Asymmetric right exhaust flue + caged violet sight tube (y=-18..-21)
        m.add_tapered_prism(frame, (-4.0, -21.0, 26.0), (-4.0, -21.0, 67.5), 2.8, 2.4, sides=8, bone_idx=0)
        m.add_tapered_prism(glow, (4.0, -20.8, 28.0), (4.0, -20.8, 56.0), 1.45, 1.45, sides=8, bone_idx=0)
        for cz in (34.0, 44.0, 54.0):
            m.add_tapered_prism(brass, (4.0, -20.8, cz - 0.9), (4.0, -20.8, cz + 0.9), 1.85, 1.85, sides=8, bone_idx=0)
    return m


# ---------------------------------------------------------------------------
# Procedural 32-bit Uncompressed TGA Texture Generator (Diffuse, Normal, Spec)
# ---------------------------------------------------------------------------


def write_tga_rgba(path: Path, width: int, height: int, pixels_rgba: bytearray) -> None:
    """Write an uncompressed 32-bit top-left origin TGA (BGRA byte order)."""
    if len(pixels_rgba) != width * height * 4:
        raise ValueError(f"Expected {width * height * 4} bytes, got {len(pixels_rgba)}")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 0x28)
    bgra = bytearray(len(pixels_rgba))
    bgra[0::4] = pixels_rgba[2::4]
    bgra[1::4] = pixels_rgba[1::4]
    bgra[2::4] = pixels_rgba[0::4]
    bgra[3::4] = pixels_rgba[3::4]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + bgra)


def _hash2(x: int, y: int) -> float:
    n = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def _height_to_normal_tga(path: Path, size: int, heightmap: list[float], strength: float = 2.6) -> None:
    buf = bytearray(size * size * 4)
    for y in range(size):
        ym = (y - 1) % size
        yp = (y + 1) % size
        row_m = ym * size
        row_c = y * size
        row_p = yp * size
        for x in range(size):
            xm = (x - 1) % size
            xp = (x + 1) % size
            dx = (heightmap[row_c + xp] - heightmap[row_c + xm]) * strength
            dy = (heightmap[row_p + x] - heightmap[row_m + x]) * strength
            nx, ny, nz = v_norm((-dx, -dy, 1.0))
            off = (row_c + x) * 4
            buf[off + 0] = clamp255((nx * 0.5 + 0.5) * 255.0)
            buf[off + 1] = clamp255((ny * 0.5 + 0.5) * 255.0)
            buf[off + 2] = clamp255((nz * 0.5 + 0.5) * 255.0)
            buf[off + 3] = 255
    write_tga_rgba(path, size, size, buf)


@dataclass(frozen=True)
class MaterialSpec:
    name: str
    material_type: str  # "model phong", "model unlit", or "effect"
    surface_type: str
    style: str
    base_rgb: tuple[int, int, int]
    accent_rgb: tuple[int, int, int]
    spec_rgb: tuple[int, int, int] = (140, 140, 140)
    gloss: int = 160
    blend_func: str = "Replace*"
    z_feather: bool = False
    fogable: bool = True


MATERIAL_SPECS: tuple[MaterialSpec, ...] = (
    # 1945 Group 935 Field-Retrofitted Dieselpunk Palette (ADR-0007 / NORTHSTAR_SPEC.md v2.1)
    # Calibrated WaW specular levels (<=72 metals, 16-24 wood/leather) so Der Riese's cool sky never tints brass olive.
    # Cryo Cannon ("Kaeltewaffe": chipped Wintertarnung <=185 over Panzergrau steel + glacial cyan #10a5f6)
    MaterialSpec("mtl_bz_cryo_hull", "model phong", "metal", "wintertarnung", (54, 60, 66), (157, 164, 168), (50, 54, 58), 160),
    MaterialSpec("mtl_bz_cryo_dark", "model phong", "metal", "brushed_metal", (42, 46, 51), (66, 72, 80), (48, 52, 58), 185),
    MaterialSpec("mtl_bz_cryo_glow", "model unlit", "glass", "cryo_glow", (16, 165, 246), (178, 246, 255)),
    # Multi-Crossbow (oiled dark walnut #583520, stamped blued steel #2a2e33, weathered brass #9b7b3c, amber #ffb020)
    MaterialSpec("mtl_bz_xbow_wood", "model phong", "wood", "wood_grain", (88, 53, 32), (52, 28, 14), (22, 16, 12), 82),
    MaterialSpec("mtl_bz_xbow_metal", "model phong", "metal", "panel_metal", (42, 46, 51), (68, 74, 82), (46, 50, 54), 165),
    MaterialSpec("mtl_bz_xbow_brass", "model phong", "metal", "brushed_metal", (155, 123, 60), (104, 78, 34), (62, 50, 24), 195),
    MaterialSpec("mtl_bz_xbow_glow", "model unlit", "glass", "amber_glow", (255, 176, 32), (255, 224, 128)),
    # Blade Boomerang (WWII brushed propeller steel, stitched leather #4a2e1e, weathered bronze, industrial crimson #e81e50)
    MaterialSpec("mtl_bz_blade_steel", "model phong", "metal", "brushed_metal", (142, 150, 158), (84, 92, 100), (64, 68, 72), 210),
    MaterialSpec("mtl_bz_blade_leather", "model phong", "cloth", "leather", (74, 46, 30), (44, 26, 14), (18, 14, 10), 65),
    MaterialSpec("mtl_bz_blade_brass", "model phong", "metal", "brushed_metal", (155, 123, 60), (108, 80, 34), (62, 50, 24), 195),
    MaterialSpec("mtl_bz_blade_glow", "model unlit", "glass", "crimson_glow", (232, 30, 80), (255, 138, 168)),
    # Acid Sprayer (Flammenwerfer-41: Panzergrau steel #363c42, Olivgruen enamel #424b3a, bright lime #68f030)
    MaterialSpec("mtl_bz_acid_metal", "model phong", "metal", "panel_metal", (54, 60, 66), (78, 86, 94), (46, 50, 54), 155),
    MaterialSpec("mtl_bz_acid_hazard", "model phong", "metal", "olivgruen_enamel", (66, 75, 58), (92, 106, 78), (38, 42, 34), 135),
    MaterialSpec("mtl_bz_acid_glow", "model unlit", "glass", "acid_glow", (104, 240, 48), (192, 255, 132)),
    # Acid Sprayer Gas Stream (2D FLAMETABLEFILE effect materials, 0 added FX slots — ADR-0004)
    MaterialSpec("mtl_bz_acid_stream", "effect", "<none>", "acid_stream", (32, 235, 58), (190, 255, 120), blend_func="Add", z_feather=False, fogable=False),
    MaterialSpec("mtl_bz_acid_billow", "effect", "<none>", "acid_billow", (28, 220, 52), (175, 255, 102), blend_func="Add", z_feather=True, fogable=False),
    MaterialSpec("mtl_bz_acid_drips", "effect", "<none>", "acid_drips", (46, 248, 66), (215, 255, 138), blend_func="Add", z_feather=True, fogable=False),
    MaterialSpec("mtl_bz_acid_mist", "effect", "<none>", "acid_mist", (72, 175, 62), (145, 220, 96), blend_func="Blend", z_feather=True, fogable=True),
    # Portal Grenade (blued steel #2a2e33, faceted dark-violet E115 shard #8e22da, weathered brass #9b7b3c)
    MaterialSpec("mtl_bz_portal_ring", "model phong", "metal", "brushed_metal", (42, 46, 51), (72, 78, 86), (52, 56, 62), 195),
    MaterialSpec("mtl_bz_portal_core", "model unlit", "glass", "portal_glow", (142, 34, 218), (224, 152, 255)),
    MaterialSpec("mtl_bz_portal_trim", "model phong", "metal", "brushed_metal", (155, 123, 60), (104, 78, 34), (62, 50, 24), 195),
    # War Club (charred ash #563824, forged blackened iron #2a2e33, deep forge red-orange #ff4a12)
    MaterialSpec("mtl_bz_club_wood", "model phong", "wood", "wood_grain", (86, 56, 36), (48, 28, 16), (20, 16, 12), 76),
    MaterialSpec("mtl_bz_club_iron", "model phong", "metal", "corroded_metal", (42, 46, 51), (70, 76, 84), (52, 56, 62), 175),
    MaterialSpec("mtl_bz_club_glow", "model unlit", "glass", "amber_glow", (255, 74, 18), (255, 178, 92)),
    # In-World Station Kiosks (bolted Panzergrau cast iron #363c42 + weathered brass #9b7b3c + GDT-synced accents)
    MaterialSpec("mtl_bz_kiosk_frame", "model phong", "metal", "panel_metal", (54, 60, 66), (78, 86, 94), (48, 52, 58), 175),
    MaterialSpec("mtl_bz_kiosk_brass", "model phong", "metal", "brushed_metal", (155, 123, 60), (104, 78, 34), (60, 48, 24), 190),
    MaterialSpec("mtl_bz_kiosk_perks_glow", "model unlit", "glass", "kiosk_panel", (18, 168, 86), (118, 242, 168)),
    MaterialSpec("mtl_bz_kiosk_class_glow", "model unlit", "glass", "kiosk_panel", (24, 108, 226), (124, 202, 255)),
    MaterialSpec("mtl_bz_kiosk_arsenal_glow", "model unlit", "glass", "kiosk_panel", (222, 118, 22), (255, 204, 98)),
    MaterialSpec("mtl_bz_kiosk_pap_glow", "model unlit", "glass", "kiosk_panel", (142, 34, 218), (228, 134, 255)),
)


def generate_material_textures(spec: MaterialSpec, tex_dir: Path, size: int = DEFAULT_TEX_SIZE) -> dict[str, str]:
    """Generate deterministic 32-bit TGA textures for one material; return relative asset paths."""
    color_buf = bytearray(size * size * 4)
    spec_buf = bytearray(size * size * 4)
    gloss_buf = bytearray(size * size * 4)
    hmap = [0.5] * (size * size)

    br, bg, bb = spec.base_rgb
    ar, ag, ab = spec.accent_rgb
    sr, sg, sb = spec.spec_rgb
    gl = spec.gloss

    for y in range(size):
        v = y / size
        for x in range(size):
            u = x / size
            n_fine = _hash2(x, y) - 0.5
            n_coarse = _hash2(x // 4, y // 4) - 0.5
            mix = 0.0
            h = 0.5 + n_fine * 0.06
            spec_mult = 1.0

            if spec.style == "wintertarnung":
                # 1945 chipped Wintertarnung lime whitewash (~20-25% streaky coverage over >=65% dark Panzergrau steel!)
                streak = math.sin(u * math.tau * 7.0 + math.sin(v * math.tau * 3.0) * 1.6) * 0.5 + 0.5
                chip = _hash2(x // 6, y // 3)
                seam_x = (x % 128) < 2
                seam_y = (y % 128) < 2
                rivet = ((x % 128) in (12, 116)) and ((y % 128) in (12, 116))
                wash = 1.0 if (streak > 0.62 and chip > 0.44) else (0.35 if streak > 0.54 and chip > 0.62 else 0.0)
                if seam_x or seam_y:
                    mix = 0.0
                    h = 0.18
                    spec_mult = 0.42
                elif rivet:
                    mix = 0.25
                    h = 0.86
                    spec_mult = 1.08
                else:
                    mix = clamp01(wash * 0.86 + n_coarse * 0.06)
                    h = 0.56 + wash * 0.08 + n_fine * 0.05
                    spec_mult = 0.55 if wash > 0.5 else 1.02
            elif spec.style == "olivgruen_enamel":
                # 1945 Olivgruen/Feldgrau steel enamel w/ dark rivets & subtle worn Gruenkreuz/stencil scuffing
                seam_x = (x % 128) < 2
                seam_y = (y % 128) < 2
                rivet = ((x % 128) in (12, 116)) and ((y % 128) in (12, 116))
                scuff = 0.42 if _hash2(x // 5, y // 5) > 0.84 else 0.0
                mix = clamp01(0.14 + scuff + n_coarse * 0.08)
                if seam_x or seam_y:
                    mix = 0.02
                    h = 0.20
                    spec_mult = 0.45
                elif rivet:
                    mix = 0.65
                    h = 0.86
                    spec_mult = 1.12
                else:
                    h = 0.52 + scuff * 0.10 + n_fine * 0.06
                    spec_mult = 0.90 + scuff * 0.25
            elif spec.style == "crimson_glow":
                # Industrial crimson (#e81e50) tracer & gyro-hub marker
                pulse = math.sin((u * 4.0 + v * 4.0) * math.tau) * 0.25 + 0.5
                mix = clamp01(0.22 + pulse * 0.55)
            elif spec.style == "cryo_armor":
                # Frosted arctic-titanium armor plates with crisp beveled seams & subtle ice rime
                grain = math.sin(u * math.tau * 20.0 + n_coarse * 1.8) * 0.04
                frost = max(0.0, math.sin((u * 5.0 + v * 3.0) * math.tau) * math.cos((u * 3.0 - v * 6.0) * math.tau))
                seam_x = (x % 128) < 2
                seam_y = (y % 128) < 2
                bevel_x = 2 <= (x % 128) < 6
                bevel_y = 2 <= (y % 128) < 6
                rivet = ((x % 128) in (12, 116)) and ((y % 128) in (12, 116))
                mix = clamp01(0.10 + grain + frost * 0.16 + n_coarse * 0.06)
                if seam_x or seam_y:
                    mix = 0.80
                    h = 0.18
                    spec_mult = 0.40
                elif rivet:
                    mix = 0.62
                    h = 0.88
                    spec_mult = 1.12
                elif bevel_x or bevel_y:
                    mix = clamp01(mix + 0.14)
                    h = 0.68
                    spec_mult = 1.08
                else:
                    h = 0.54 + grain * 0.35 + frost * 0.12
                    spec_mult = 0.96 + frost * 0.12
            elif spec.style == "panel_metal":
                # Machined armor plates (128px pitch so surfaces never look like a wireframe grid!)
                grain = math.sin(u * math.tau * 24.0 + n_coarse * 2.0) * 0.04
                seam_x = (x % 128) < 2
                seam_y = (y % 128) < 2
                rivet = ((x % 128) in (10, 118)) and ((y % 128) in (10, 118))
                mix = 0.12 + grain + n_coarse * 0.08
                if seam_x or seam_y:
                    mix = 0.72
                    h = 0.22
                    spec_mult = 0.45
                elif rivet:
                    mix = 0.55
                    h = 0.85
                    spec_mult = 1.10
                else:
                    h = 0.54 + grain * 0.4
            elif spec.style == "brushed_metal":
                streak = math.sin(v * math.tau * 48.0) * 0.12 + _hash2(x // 8, y) * 0.16
                band = 1.0 if (y % 32) < 2 else 0.0
                mix = clamp01(0.18 + streak + band * 0.55)
                h = 0.52 + streak * 0.35 - band * 0.30
                spec_mult = 1.05 - band * 0.45
            elif spec.style == "damascus":
                # Forged layered steel wave ripples
                wave = math.sin(u * math.tau * 6.0 + math.sin(v * math.tau * 4.0) * 2.2) * 0.5 + 0.5
                fine = math.sin((u + v) * math.tau * 22.0) * 0.15
                mix = clamp01(wave * 0.65 + fine + n_fine * 0.08)
                h = 0.5 + wave * 0.25 + fine * 0.2
                spec_mult = 0.85 + wave * 0.35
            elif spec.style == "wood_grain":
                rings = math.sin((v * 14.0 + math.sin(u * math.tau * 2.0) * 0.65) * math.tau) * 0.5 + 0.5
                fiber = _hash2(x // 6, y) * 0.25
                mix = clamp01(rings * 0.55 + fiber)
                h = 0.45 + rings * 0.30 + fiber * 0.15
                spec_mult = 0.8 + rings * 0.3
            elif spec.style == "leather":
                # Diagonal wrapped leather strips + stitch lines
                diag = (u * 5.0 + v * 5.0) % 1.0
                seam = diag < 0.07
                pebble = _hash2(x // 2, y // 2) * 0.28
                mix = clamp01((0.85 if seam else 0.25) + pebble)
                h = 0.18 if seam else (0.58 + pebble * 0.35)
                spec_mult = 0.4 if seam else 0.9
            elif spec.style == "corroded_metal":
                patch = math.sin(u * math.tau * 4.0) * math.cos(v * math.tau * 4.0)
                speck = _hash2(x // 3, y // 3)
                seam = (x % 64) < 2 or (y % 64) < 2
                mix = clamp01(0.2 + (0.45 if patch > 0.35 and speck > 0.55 else 0.0) + (0.5 if seam else 0.0))
                h = 0.2 if seam else (0.52 + (0.18 if patch > 0.35 else -0.05) + n_fine * 0.12)
                spec_mult = 0.45 if seam else 0.95
            elif spec.style == "hazard_stripes":
                # Crisp high-contrast diagonal yellow/black biohazard warning stripes!
                stripe = ((u * 6.0 + v * 6.0) % 1.0) < 0.50
                wear = 0.12 if _hash2(x // 3, y // 3) > 0.82 else 0.0
                mix = (0.0 + wear) if stripe else (1.0 - wear * 0.5)
                h = (0.58 if stripe else 0.46) + n_fine * 0.08
                spec_mult = 1.05 if stripe else 0.65
            elif spec.style == "cryo_glow":
                # Luminous icy-cyan liquid-nitrogen plasma veins + crystalline frost core highlights
                vein = abs(math.sin((u * 5.0 + math.sin(v * math.tau * 3.0) * 0.35) * math.tau))
                crystal = max(0.0, math.cos((u * 8.0 - v * 6.0) * math.tau)) * 0.22
                core = math.sin(v * math.pi) * 0.45
                mix = clamp01(core + (1.0 - vein) * 0.50 + crystal)
            elif spec.style == "amber_glow":
                # Incandescent orange-gold warhead core
                pulse = (math.sin(u * math.tau * 4.0) * 0.25 + 0.5) * 0.5 + math.sin(v * math.pi) * 0.55
                mix = clamp01(pulse)
            elif spec.style == "edge_glow":
                # Electric cyan-gold honed cutting edge shimmer
                shimmer = math.sin((u * 3.0 + v * 5.0) * math.tau) * 0.5 + 0.5
                mix = clamp01(0.25 + shimmer * 0.65)
            elif spec.style == "acid_glow":
                # Radioactive bubbling neon-green chemical fluid
                b1 = math.sin(u * math.tau * 6.0) * math.sin(v * math.tau * 6.0)
                b2 = math.cos((u * 9.0 - v * 7.0) * math.tau)
                mix = clamp01(0.32 + max(0.0, b1) * 0.55 + max(0.0, b2) * 0.30)
            elif spec.style == "portal_glow":
                # Swirling violet-indigo dimensional rift core with electric cyan-white plasma filaments
                swirl = math.sin((u * 4.0 + math.sin(v * math.tau * 2.0) * 0.45) * math.tau) * 0.5 + 0.5
                arc = max(0.0, math.cos((u * 7.0 - v * 5.0) * math.tau))
                mix = clamp01(0.24 + swirl * 0.46 + arc * 0.34)
            elif spec.style == "kiosk_panel":
                # Frosted illuminated station glass panel with subtle bezel vignette & warm vertical glow
                du = abs(u - 0.5) * 2.0
                dv = abs(v - 0.5) * 2.0
                bezel = 1.0 if (du > 0.90 or dv > 0.90) else 0.0
                radial = clamp01(1.0 - math.sqrt(du * du * 0.65 + dv * dv * 0.65))
                rib = 0.06 * math.sin(v * math.tau * 12.0)
                mix = 0.05 if bezel > 0.5 else clamp01(0.18 + radial * 0.68 + rib)
            elif spec.style in ("acid_stream", "acid_billow", "acid_drips", "acid_mist"):
                # Alpha-feathered 2D chemical stream/cloud/droplet sprites for FLAMETABLEFILE
                du = (u - 0.5) * 2.0
                dv = (v - 0.5) * 2.0
                r_dist = math.sqrt(du * du + dv * dv)
                if spec.style == "acid_stream":
                    # Continuous glowing liquid-jet ribbon running along U with soft cross-section V falloff
                    core = clamp01(1.0 - abs(dv) * 1.15)
                    streak = 0.65 + 0.35 * math.sin(u * math.tau * 5.0 + dv * 3.0)
                    alpha_f = (core * core) * clamp01(streak + n_coarse * 0.25)
                    mix = clamp01(core * 0.85)
                elif spec.style == "acid_billow":
                    # Billowing glowing acid vapor cloud with circular feather falloff
                    radial = clamp01(1.0 - r_dist)
                    swirl = 0.6 + 0.4 * math.sin((u * 3.0 + v * 2.0) * math.tau + n_coarse * 2.5)
                    alpha_f = (radial * radial) * swirl
                    mix = clamp01(radial * 0.90)
                elif spec.style == "acid_drips":
                    # Clustered bright sizzling acid droplets inside circular feather
                    radial = clamp01(1.0 - r_dist * 1.05)
                    drop = max(0.0, math.sin(u * math.tau * 4.0) * math.sin(v * math.tau * 4.0))
                    alpha_f = clamp01((radial * radial) * (0.45 + 0.75 * drop))
                    mix = clamp01(0.45 + 0.55 * drop)
                else:
                    # Soft lingering toxic yellow-green mist
                    radial = clamp01(1.0 - r_dist)
                    alpha_f = (radial * radial) * (0.42 + 0.22 * math.cos((u - v) * math.tau * 2.0))
                    mix = clamp01(radial * 0.65)
                r_c = clamp255(br * (1.0 - mix) + ar * mix)
                g_c = clamp255(bg * (1.0 - mix) + ag * mix)
                b_c = clamp255(bb * (1.0 - mix) + ab * mix)
                a_c = clamp255(alpha_f * 255.0)
                # Premultiply additive sprites so edges fade smoothly to zero
                if spec.blend_func == "Add":
                    r_c = clamp255(r_c * alpha_f)
                    g_c = clamp255(g_c * alpha_f)
                    b_c = clamp255(b_c * alpha_f)
                off = (y * size + x) * 4
                color_buf[off + 0] = r_c
                color_buf[off + 1] = g_c
                color_buf[off + 2] = b_c
                color_buf[off + 3] = a_c
                continue

            r = clamp255(br * (1.0 - mix) + ar * mix + n_fine * 10.0)
            g = clamp255(bg * (1.0 - mix) + ag * mix + n_fine * 10.0)
            b = clamp255(bb * (1.0 - mix) + ab * mix + n_fine * 10.0)
            off = (y * size + x) * 4
            color_buf[off + 0] = r
            color_buf[off + 1] = g
            color_buf[off + 2] = b
            color_buf[off + 3] = 255
            hmap[y * size + x] = h

            spec_buf[off + 0] = clamp255(sr * spec_mult)
            spec_buf[off + 1] = clamp255(sg * spec_mult)
            spec_buf[off + 2] = clamp255(sb * spec_mult)
            spec_buf[off + 3] = 255

            gv = clamp255(gl * spec_mult)
            gloss_buf[off + 0] = gv
            gloss_buf[off + 1] = gv
            gloss_buf[off + 2] = gv
            gloss_buf[off + 3] = 255

    stem = spec.name.removeprefix("mtl_")
    paths: dict[str, str] = {}
    c_file = tex_dir / f"{stem}_c.tga"
    write_tga_rgba(c_file, size, size, color_buf)
    paths["colorMap"] = f"texture_assets\\\\{ASSET_SUBDIR}\\\\{c_file.name}"

    if spec.material_type == "model phong":
        n_file = tex_dir / f"{stem}_n.tga"
        s_file = tex_dir / f"{stem}_s.tga"
        g_file = tex_dir / f"{stem}_g.tga"
        _height_to_normal_tga(n_file, size, hmap)
        write_tga_rgba(s_file, size, size, spec_buf)
        write_tga_rgba(g_file, size, size, gloss_buf)
        paths["normalMap"] = f"texture_assets\\\\{ASSET_SUBDIR}\\\\{n_file.name}"
        paths["specColorMap"] = f"texture_assets\\\\{ASSET_SUBDIR}\\\\{s_file.name}"
        paths["cosinePowerMap"] = f"texture_assets\\\\{ASSET_SUBDIR}\\\\{g_file.name}"

    return paths


# ---------------------------------------------------------------------------
# GDT Generator (material.gdf + xmodel.gdf)
# ---------------------------------------------------------------------------


def build_gdt_text(
    material_paths: dict[str, tuple[MaterialSpec, dict[str, str]]],
    xmodel_entries: Sequence[tuple[str, str, str]],
) -> str:
    """Build a valid WaW source_data/*.gdt manifest for converter.exe."""
    blocks: list[str] = ["{"]
    for mat_name, (spec, paths) in material_paths.items():
        if spec.material_type == "effect":
            lines = [
                f'\t"{mat_name}" ( "material.gdf" )',
                "\t{",
                '\t\t"alphaTest" "Always*"',
                f'\t\t"blendFunc" "{spec.blend_func}"',
                f'\t\t"colorMap" "{paths["colorMap"]}"',
                '\t\t"colorTint" "1.000000 1.000000 1.000000 1.000000"',
                '\t\t"cullFace" "None*"',
                '\t\t"depthTest" "LessEqual*"',
                '\t\t"depthWrite" "Off*"',
                '\t\t"filterColor" "mip standard (2x bilinear)*"',
                f'\t\t"fogable" "{"1" if spec.fogable else "0"}"',
                '\t\t"materialType" "effect"',
                '\t\t"nopicmipColor" "0"',
                '\t\t"polygonOffset" "None*"',
                '\t\t"sort" "Effect - Auto Sort*"',
                f'\t\t"surfaceType" "{spec.surface_type}"',
                '\t\t"template" "material.template"',
                '\t\t"tileColor" "no tile"',
                '\t\t"usage" "<not in editor>"',
                f'\t\t"zFeather" "{"1" if spec.z_feather else "0"}"',
                '\t\t"zFeatherDepth" "40"',
                "\t}",
            ]
            blocks.append("\n".join(lines))
            continue

        lines = [
            f'\t"{mat_name}" ( "material.gdf" )',
            "\t{",
            '\t\t"alphaTest" "Always*"',
            f'\t\t"blendFunc" "{spec.blend_func}"',
            f'\t\t"colorMap" "{paths["colorMap"]}"',
            '\t\t"colorTint" "1.000000 1.000000 1.000000 1.000000"',
            '\t\t"cullFace" "Back*"',
            '\t\t"depthTest" "LessEqual*"',
            '\t\t"depthWrite" "<auto>*"',
            '\t\t"filterColor" "mip standard (2x bilinear)*"',
            f'\t\t"materialType" "{spec.material_type}"',
            '\t\t"nopicmipColor" "0"',
            '\t\t"polygonOffset" "None*"',
            f'\t\t"surfaceType" "{spec.surface_type}"',
            '\t\t"template" "material.template"',
            '\t\t"tileColor" "tile both*"',
            '\t\t"usage" "<not in editor>"',
        ]
        if "normalMap" in paths:
            lines.extend(
                [
                    '\t\t"filterNormal" "mip standard (2x bilinear)*"',
                    f'\t\t"normalMap" "{paths["normalMap"]}"',
                    '\t\t"tileNormal" "tile both*"',
                    '\t\t"useLegacyNormalEncoding" "1"',
                ]
            )
        if "specColorMap" in paths:
            lines.extend(
                [
                    '\t\t"filterSpecular" "mip standard (2x bilinear)*"',
                    f'\t\t"specColorMap" "{paths["specColorMap"]}"',
                    f'\t\t"cosinePowerMap" "{paths["cosinePowerMap"]}"',
                    '\t\t"tileSpecular" "tile both*"',
                ]
            )
        lines.append("\t}")
        blocks.append("\n".join(lines))

    for xm_name, rel_export_path, xm_type in xmodel_entries:
        blocks.append(
            "\n".join(
                [
                    f'\t"{xm_name}" ( "xmodel.gdf" )',
                    "\t{",
                    '\t\t"allowHidingAllParts" "0"',
                    '\t\t"collisionLOD" "None"',
                    f'\t\t"filename" "{rel_export_path}"',
                    '\t\t"highLodDist" "0"',
                    f'\t\t"type" "{xm_type}"',
                    "\t}",
                ]
            )
        )
    blocks.append("}")
    return "\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------
# Public entry point (callable from build_mod.py or CLI)
# ---------------------------------------------------------------------------


def build_all_meshes() -> list[MeshBuilder]:
    return [
        build_acid_sprayer("viewmodel_bz_acid_sprayer", is_world=False),
        build_acid_sprayer("world_bz_acid_sprayer", is_world=True),
        build_cryo_cannon("viewmodel_bz_cryo_cannon", is_world=False),
        build_cryo_cannon("world_bz_cryo_cannon", is_world=True),
        build_multi_crossbow("viewmodel_bz_multi_crossbow", is_world=False),
        build_multi_crossbow("world_bz_multi_crossbow", is_world=True),
        build_crossbow_bolt(),
        build_blade_boomerang_held("viewmodel_bz_blade_boomerang", is_world=False),
        build_blade_boomerang_held("world_bz_blade_boomerang", is_world=True),
        build_blade_boomerang_air(),
        build_portal_grenade_held("viewmodel_bz_portal_grenade", is_world=False),
        build_portal_grenade_held("world_bz_portal_grenade", is_world=True),
        build_portal_orb_air(),
        build_war_club_held("viewmodel_bz_war_club", is_world=False),
        build_war_club_held("world_bz_war_club", is_world=True),
        build_station_kiosk("bz_station_perks_kiosk", "perks"),
        build_station_kiosk("bz_station_class_kiosk", "class"),
        build_station_kiosk("bz_station_arsenal_kiosk", "arsenal"),
        build_station_kiosk("bz_station_pap_kiosk", "pap"),
    ]


def generate_all_assets(tools_root: Path, tex_size: int = DEFAULT_TEX_SIZE) -> dict[str, list[str]]:
    """Write all custom XMODEL_EXPORTs, 32-bit TGA textures, and bz_weapons.gdt into tools_root."""
    model_dir = tools_root / "model_export" / ASSET_SUBDIR
    tex_dir = tools_root / "texture_assets" / ASSET_SUBDIR
    gdt_path = tools_root / "source_data" / GDT_FILENAME
    model_dir.mkdir(parents=True, exist_ok=True)
    tex_dir.mkdir(parents=True, exist_ok=True)
    gdt_path.parent.mkdir(parents=True, exist_ok=True)

    material_paths: dict[str, tuple[MaterialSpec, dict[str, str]]] = {}
    generated_images: list[str] = []
    for spec in MATERIAL_SPECS:
        paths = generate_material_textures(spec, tex_dir, size=tex_size)
        material_paths[spec.name] = (spec, paths)
        for p in paths.values():
            generated_images.append(Path(p.replace("\\\\", "/")).stem)

    meshes = build_all_meshes()
    xmodel_entries: list[tuple[str, str, str]] = []
    for mesh in meshes:
        export_path = model_dir / f"{mesh.name}.XMODEL_EXPORT"
        export_path.write_text(mesh.to_xmodel_export(), encoding="ascii")
        rel_win = f"{ASSET_SUBDIR}\\\\{export_path.name}"
        xmodel_entries.append((mesh.name, rel_win, mesh.model_type))

    gdt_text = build_gdt_text(material_paths, xmodel_entries)
    gdt_path.write_text(gdt_text, encoding="ascii")

    return {
        "materials": [spec.name for spec in MATERIAL_SPECS],
        "xmodels": [mesh.name for mesh in meshes],
        "images": sorted(set(generated_images)),
        "gdt": [str(gdt_path)],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tools-root",
        type=Path,
        required=True,
        help="Path to WaW Mod Tools game root containing model_export/, texture_assets/, source_data/",
    )
    parser.add_argument("--tex-size", type=int, default=DEFAULT_TEX_SIZE)
    args = parser.parse_args(argv)
    summary = generate_all_assets(args.tools_root, tex_size=args.tex_size)
    print(
        f"Generated {len(summary['xmodels'])} custom XMODEL_EXPORTs, "
        f"{len(summary['materials'])} materials, {len(summary['images'])} TGA textures -> {summary['gdt'][0]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
