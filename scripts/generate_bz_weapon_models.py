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
DEFAULT_TEX_SIZE = 512

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
# 1. CRYO CANNON (Arctic-White / Cobalt-Titanium Liquid-Nitrogen Projector)
# ---------------------------------------------------------------------------


def build_cryo_cannon(name: str, is_world: bool = False) -> MeshBuilder:
    bones = world_weapon_bones((41.0, 0.0, 2.16)) if is_world else BONES_TESLA
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0
    b_bolt = 0 if is_world else 1
    b_bulbs = (0, 0, 0) if is_world else (2, 3, 4)

    hull = "mtl_bz_cryo_hull"
    dark = "mtl_bz_cryo_dark"
    glow = "mtl_bz_cryo_glow"

    # Sculpted tapered rear stock, recoil buttpad & ergonomic pistol grip (slimmed for Tesla reload clearance!)
    m.add_tapered_prism(dark, (-7.6, 0.0, -0.02), (-6.8, 0.0, 0.12), 0.96, 0.92, sides=10, bone_idx=b_gun, scale_y=0.80, scale_z=0.92)
    m.add_tapered_prism(dark, (-7.0, 0.0, 0.10), (-1.5, 0.0, 0.65), 0.90, 1.25, sides=10, bone_idx=b_gun, scale_y=0.84, scale_z=0.74)
    m.add_tapered_prism(hull, (-1.8, 0.0, 0.65), (3.8, 0.0, 1.20), 1.25, 1.66, sides=10, bone_idx=b_gun, scale_y=0.86, scale_z=0.78)
    m.add_box(dark, (-0.5, 0.0, -2.8), (2.0, 1.32, 3.6), bone_idx=b_gun, rot_xyz=(0.0, 14.0, 0.0))
    # Rear cryogenic pressure dial embedded cleanly into left rear cheek (below sightline!)
    m.add_tapered_prism(dark, (1.4, 1.28, 1.80), (1.4, 1.66, 1.80), 0.56, 0.52, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(glow, (1.4, 1.60, 1.80), (1.4, 1.72, 1.80), 0.36, 0.34, sides=10, bone_idx=b_gun)

    # Main sculpted 10-sided arctic-titanium cryo projector chassis + layered bevel shroud plates (Z <= 3.35!)
    m.add_tapered_prism(hull, (3.6, 0.0, 1.40), (22.5, 0.0, 1.70), 1.74, 1.56, sides=10, bone_idx=b_gun, cap_start=False, scale_y=0.90)
    # Recessed dark-cobalt thermal side vents & contoured cheek armor along chassis flanks
    for side in (-1.0, +1.0):
        m.add_box(dark, (14.2, side * 1.44, 1.55), (14.5, 0.24, 0.72), bone_idx=b_gun)
        m.add_box(hull, (14.2, side * 1.54, 2.02), (13.6, 0.18, 0.34), bone_idx=b_gun, rot_xyz=(side * 16.0, 0.0, 0.0))
        m.add_box(hull, (14.2, side * 1.54, 1.08), (13.6, 0.18, 0.34), bone_idx=b_gun, rot_xyz=(-side * 16.0, 0.0, 0.0))
        m.add_tapered_prism(glow, (8.0, side * 1.56, 1.55), (20.4, side * 1.48, 1.62), 0.12, 0.10, sides=6, bone_idx=b_gun)
    # Dark cobalt-steel under-receiver & sculpted ribbed foregrip rail
    m.add_tapered_prism(dark, (2.5, 0.0, -0.20), (21.5, 0.0, 0.18), 1.12, 0.88, sides=8, bone_idx=b_gun)
    for gx in (13.0, 14.4, 15.8, 17.2, 18.6):
        m.add_box(hull, (gx, 0.0, -0.58), (0.45, 1.38, 0.26), bone_idx=b_gun)
    # Recessed glowing glacial-blue dorsal cryo-plasma conduit spine (below Z=3.20 -> unobstructed sightline!)
    m.add_tapered_prism(glow, (4.2, 0.0, 2.95), (29.5, 0.0, 2.95), 0.34, 0.24, sides=8, bone_idx=b_gun)
    # Sleek low-profile dark-titanium saddle clamps straddling the dorsal cryo conduit (Z <= 3.32)
    for rx in (6.0, 10.0, 14.0, 18.0, 22.0, 26.0):
        m.add_tapered_prism(dark, (rx - 0.36, 0.0, 2.10), (rx + 0.36, 0.0, 2.10), 1.28, 1.28, sides=8, bone_idx=b_gun)
        m.add_box(hull, (rx, 0.0, 3.24), (0.62, 1.62, 0.22), bone_idx=b_gun)

    # 3 animated octagonal glowing liquid-nitrogen cryo cartridges on left flank (j_bulb_1/2/3!) with protective cages
    bulb_xs = (7.89, 9.64, 11.39)
    for b_idx, bx in zip(b_bulbs, bulb_xs):
        m.add_tapered_prism(glow, (bx, 2.95, 0.18), (bx, 2.95, 2.58), 0.50, 0.50, sides=8, bone_idx=b_idx)
        m.add_tapered_prism(dark, (bx, 2.95, -0.22), (bx, 2.95, 0.28), 0.68, 0.68, sides=8, bone_idx=b_idx)
        m.add_tapered_prism(hull, (bx, 2.95, 0.88), (bx, 2.95, 1.06), 0.60, 0.60, sides=8, bone_idx=b_idx)
        m.add_tapered_prism(dark, (bx, 2.95, 1.56), (bx, 2.95, 1.76), 0.62, 0.62, sides=8, bone_idx=b_idx)
        m.add_tapered_prism(dark, (bx, 2.95, 2.46), (bx, 2.95, 3.00), 0.68, 0.50, sides=8, bone_idx=b_idx)
        # Outer twin protective roll-cage struts per nitrogen cell
        m.add_tapered_prism(hull, (bx - 0.38, 3.42, 0.12), (bx - 0.38, 3.42, 2.66), 0.08, 0.08, sides=5, bone_idx=b_idx)
        m.add_tapered_prism(hull, (bx + 0.38, 3.42, 0.12), (bx + 0.38, 3.42, 2.66), 0.08, 0.08, sides=5, bone_idx=b_idx)
    m.add_tapered_prism(dark, (6.6, 2.38, 0.02), (12.7, 2.38, 0.02), 0.58, 0.58, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(hull, (6.8, 2.38, 2.78), (12.5, 2.38, 2.78), 0.42, 0.42, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(glow, (12.4, 2.38, 2.78), (15.4, 1.35, 2.40), 0.16, 0.14, sides=6, bone_idx=b_gun)

    # Right-side pressurized liquid-nitrogen condenser drum with ringed cooling bands + dual frosted feed pipes
    m.add_tapered_prism(dark, (5.2, -2.38, 1.15), (15.0, -2.38, 1.15), 0.90, 0.88, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(hull, (4.7, -2.38, 1.15), (5.3, -2.38, 1.15), 0.60, 0.90, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(hull, (14.9, -2.38, 1.15), (15.6, -2.38, 1.15), 0.88, 0.56, sides=10, bone_idx=b_gun)
    for cx in (6.8, 8.6, 10.4, 12.2, 14.0):
        m.add_tapered_prism(hull, (cx - 0.18, -2.38, 1.15), (cx + 0.18, -2.38, 1.15), 0.98, 0.98, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(glow, (6.2, -2.72, 1.15), (14.2, -2.72, 1.15), 0.36, 0.36, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(hull, (15.4, -2.38, 1.15), (18.0, -1.25, 1.65), 0.34, 0.28, sides=6, bone_idx=b_gun)
    m.add_tapered_prism(glow, (15.2, -2.10, 1.55), (17.8, -1.15, 1.92), 0.14, 0.12, sides=6, bone_idx=b_gun)

    # Animated cryo-vent bolt shroud (skinned to j_bolt)
    m.add_tapered_prism(dark, (15.8, 1.15, 1.55), (19.4, 1.15, 1.55), 0.58, 0.46, sides=8, bone_idx=b_bolt)
    m.add_tapered_prism(hull, (16.2, 1.15, 1.55), (17.0, 1.15, 1.55), 0.64, 0.62, sides=8, bone_idx=b_bolt)
    m.add_tapered_prism(glow, (16.5, 1.58, 1.55), (18.9, 1.58, 1.55), 0.18, 0.16, sides=6, bone_idx=b_bolt)

    # Inner armored cryo barrel + luminous liquid-nitrogen plasma core + 6 graduated swept cryogenic radiator fins
    m.add_tapered_prism(dark, (22.0, 0.0, 1.80), (35.5, 0.0, 1.95), 1.06, 0.92, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(glow, (22.0, 0.0, 1.80), (36.4, 0.0, 1.96), 0.54, 0.46, sides=8, bone_idx=b_gun)
    for fi, fx in enumerate((21.2, 23.4, 25.6, 27.8, 30.0, 32.2)):
        span = 3.7 - fi * 0.20
        m.add_box(hull, (fx, +span * 0.54, 1.85), (0.52, span, 0.28), bone_idx=b_gun, rot_xyz=(18.0, 0.0, -20.0))
        m.add_box(hull, (fx, -span * 0.54, 1.85), (0.52, span, 0.28), bone_idx=b_gun, rot_xyz=(-18.0, 0.0, 20.0))
        m.add_box(dark, (fx + 0.18, +span * 0.48, 1.56), (0.36, span * 0.72, 0.16), bone_idx=b_gun, rot_xyz=(18.0, 0.0, -20.0))
        m.add_box(dark, (fx + 0.18, -span * 0.48, 1.56), (0.36, span * 0.72, 0.16), bone_idx=b_gun, rot_xyz=(-18.0, 0.0, 20.0))
        m.add_box(glow, (fx, +span * 0.94, 2.06), (0.42, 0.22, 0.22), bone_idx=b_gun)
        m.add_box(glow, (fx, -span * 0.94, 2.06), (0.42, 0.22, 0.22), bone_idx=b_gun)

    # Wide hexagonal Cryo-Diffuser Emitter Crown + armored shroud collar + 3 twin-rail Cryo-Focus Prongs
    m.add_tapered_prism(dark, (32.8, 0.0, 1.94), (34.0, 0.0, 1.95), 1.48, 1.72, sides=6, bone_idx=b_gun)
    m.add_tapered_prism(hull, (33.8, 0.0, 1.95), (36.0, 0.0, 1.98), 1.72, 1.92, sides=6, bone_idx=b_gun)
    m.add_tapered_prism(glow, (35.6, 0.0, 1.98), (36.6, 0.0, 1.98), 1.32, 1.18, sides=6, bone_idx=b_gun)
    for prong_deg in (30.0, 150.0, 270.0):
        rad = math.radians(prong_deg)
        py = math.cos(rad) * 1.72
        pz = 1.98 + math.sin(rad) * 1.72
        tip_y = math.cos(rad) * 0.92
        tip_z = 1.98 + math.sin(rad) * 0.92
        m.add_tapered_prism(dark, (34.8, py, pz), (39.2, tip_y, tip_z), 0.34, 0.18, sides=8, bone_idx=b_gun)
        m.add_tapered_prism(hull, (35.4, py * 1.08, pz + math.sin(rad) * 0.14), (38.6, tip_y * 1.06, tip_z + math.sin(rad) * 0.10), 0.16, 0.10, sides=6, bone_idx=b_gun)
        m.add_tapered_prism(glow, (38.9, tip_y, tip_z), (40.9, tip_y * 0.80, tip_z), 0.22, 0.06, sides=8, bone_idx=b_gun)

    # Elevated circular Cryo-Holo aperture ring at Z=5.10 -> crisp cyan reticle aligned to live ADS center (S3!)
    ring_c = (3.8, 0.0, 5.10)
    ring_segs = 16
    ring_r = 0.86
    m.add_box(dark, (3.8, -0.68, 3.88), (0.48, 0.22, 1.18), bone_idx=b_gun)
    m.add_box(dark, (3.8, +0.68, 3.88), (0.48, 0.22, 1.18), bone_idx=b_gun)
    m.add_box(hull, (3.8, 0.0, 3.40), (0.72, 1.62, 0.26), bone_idx=b_gun)
    for s in range(ring_segs):
        a0 = math.radians(360.0 * s / ring_segs)
        a1 = math.radians(360.0 * (s + 1) / ring_segs)
        p0 = (ring_c[0], ring_c[1] + math.cos(a0) * ring_r, ring_c[2] + math.sin(a0) * ring_r)
        p1 = (ring_c[0], ring_c[1] + math.cos(a1) * ring_r, ring_c[2] + math.sin(a1) * ring_r)
        m.add_tapered_prism(dark, p0, p1, 0.09, 0.09, sides=6, bone_idx=b_gun, cap_start=False, cap_end=False)
    m.add_tapered_prism(glow, (3.8, -0.80, 5.10), (3.8, -0.40, 5.10), 0.055, 0.038, sides=6, bone_idx=b_gun)
    m.add_tapered_prism(glow, (3.8, +0.80, 5.10), (3.8, +0.40, 5.10), 0.055, 0.038, sides=6, bone_idx=b_gun)
    m.add_tapered_prism(glow, (3.8, 0.0, 4.30), (3.8, 0.0, 4.66), 0.055, 0.035, sides=6, bone_idx=b_gun)

    return m


# ---------------------------------------------------------------------------
# 2. MULTI-CROSSBOW (3-Rail Heavy Tactical Compound Crossbow + Custom Bolt)
# ---------------------------------------------------------------------------


def build_multi_crossbow(name: str, is_world: bool = False) -> MeshBuilder:
    bones = world_weapon_bones((26.67, -0.12, 2.76)) if is_world else BONES_FG42_SCOPED
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0
    b_clip = 0 if is_world else 2  # j_clip: 3-bolt cassette animates cleanly during FG42 reload (S6)!

    wood = "mtl_bz_xbow_wood"
    metal = "mtl_bz_xbow_metal"
    brass = "mtl_bz_xbow_brass"
    glow = "mtl_bz_xbow_glow"

    # Sculpted dark-walnut crossbow stock, recoil buttpad, cheek rest, pistol grip & brass trigger assembly
    m.add_tapered_prism(metal, (-7.8, 0.0, -0.25), (-7.0, 0.0, -0.08), 1.12, 1.06, sides=12, bone_idx=b_gun, scale_y=0.70, scale_z=1.24)
    m.add_tapered_prism(wood, (-7.2, 0.0, -0.1), (0.8, 0.0, 1.05), 1.06, 1.38, sides=12, bone_idx=b_gun, scale_y=0.74, scale_z=1.20)
    m.add_tapered_prism(wood, (-5.4, 0.0, 0.92), (-1.2, 0.0, 1.48), 0.72, 0.86, sides=10, bone_idx=b_gun, scale_y=0.88, scale_z=0.58)
    m.add_tapered_prism(wood, (0.5, 0.0, 1.05), (16.8, 0.0, 1.35), 1.34, 1.14, sides=12, bone_idx=b_gun, scale_y=0.86, scale_z=0.92)
    m.add_tapered_prism(wood, (-1.1, 0.0, -2.85), (-0.2, 0.0, 0.5), 0.72, 0.86, sides=12, bone_idx=b_gun)
    m.add_tapered_prism(brass, (-1.25, 0.0, -3.05), (-1.05, 0.0, -2.75), 0.78, 0.74, sides=12, bone_idx=b_gun)
    m.add_box(brass, (1.0, 0.0, -0.95), (2.7, 0.28, 1.28), bone_idx=b_gun)
    m.add_box(metal, (0.65, 0.0, -0.70), (0.28, 0.14, 0.78), bone_idx=b_gun, rot_xyz=(0.0, -18.0, 0.0))

    # Tapered machined steel receiver ramp & beveled 3-rail bolt flight deck with brass retention guides
    m.add_tapered_prism(metal, (1.5, 0.0, 1.95), (6.5, 0.0, 2.05), 1.25, 2.38, sides=10, bone_idx=b_gun, scale_y=1.06, scale_z=0.38)
    m.add_box(metal, (14.0, 0.0, 2.05), (16.2, 4.7, 0.94), bone_idx=b_gun)
    for ry in (-2.12, -0.68, +0.68, +2.12):
        m.add_box(brass, (13.8, ry, 2.58), (16.0, 0.22, 0.30), bone_idx=b_gun)
    # Angled side cheek-guards & vented forend ribs
    for side in (-1.0, +1.0):
        m.add_box(metal, (7.0, side * 1.72, 1.45), (11.2, 0.26, 0.96), bone_idx=b_gun, rot_xyz=(-side * 20.0, 0.0, 0.0))
        m.add_box(brass, (13.5, side * 2.40, 2.08), (11.8, 0.18, 0.34), bone_idx=b_gun)
        m.add_tapered_prism(glow, (10.0, side * 2.48, 2.08), (18.2, side * 2.48, 2.08), 0.08, 0.08, sides=6, bone_idx=b_gun)

    # Removable 3-bolt tactical cassette + 3 glowing explosive bolts skinned to j_clip (animates on reload!)
    m.add_box(metal, (9.5, 0.0, 2.48), (4.4, 3.7, 0.28), bone_idx=b_clip)
    m.add_box(brass, (9.5, 0.0, 2.66), (1.1, 3.85, 0.18), bone_idx=b_clip)
    for by in (-1.38, 0.0, +1.38):
        m.add_tapered_prism(metal, (7.0, by, 2.66), (22.3, by, 2.66), 0.16, 0.16, sides=10, bone_idx=b_clip)
        m.add_tapered_prism(brass, (21.5, by, 2.66), (22.7, by, 2.66), 0.24, 0.24, sides=10, bone_idx=b_clip)
        m.add_tapered_prism(glow, (22.5, by, 2.66), (25.4, by, 2.66), 0.36, 0.05, sides=4, bone_idx=b_clip, angle_offset_deg=45.0)
        m.add_box(brass, (8.2, by, 2.94), (2.1, 0.08, 0.44), bone_idx=b_clip)
        m.add_tapered_prism(glow, (6.7, by, 2.66), (7.3, by, 2.66), 0.20, 0.18, sides=8, bone_idx=b_clip)

    # Heavy beveled forward steel riser block + reinforced limb pockets
    m.add_box(metal, (20.8, 0.0, 2.15), (3.2, 6.2, 2.00), bone_idx=b_gun)
    m.add_box(brass, (21.7, 0.0, 2.15), (1.00, 5.4, 2.20), bone_idx=b_gun)
    m.add_box(metal, (19.6, 0.0, 1.35), (2.2, 3.4, 0.85), bone_idx=b_gun)

    # Wide swept split-limb compound crossbow prods (+/- 12.0u wide!) with dual machined brass eccentric cams
    for side in (-1.0, +1.0):
        pts = [
            (20.6, side * 2.6, 2.35),
            (20.2, side * 5.6, 2.42),
            (18.5, side * 8.6, 2.52),
            (15.6, side * 11.0, 2.62),
            (12.5, side * 12.0, 2.68),
        ]
        # Reinforced brass limb-pocket clamp at riser junction
        m.add_box(brass, (20.5, side * 3.1, 2.38), (1.35, 1.15, 1.38), bone_idx=b_gun)
        for dz in (+0.38, -0.38):
            for i in range(len(pts) - 1):
                p0 = (pts[i][0], pts[i][1], pts[i][2] + dz)
                p1 = (pts[i + 1][0], pts[i + 1][1], pts[i + 1][2] + dz)
                r0 = 0.40 - i * 0.048
                r1 = 0.40 - (i + 1) * 0.048
                m.add_tapered_prism(metal, p0, p1, r0, r1, sides=10, bone_idx=b_gun)
        tip = pts[-1]
        # Machined brass cam pulley + center axle + glowing amber cam bearing cap
        m.add_tapered_prism(brass, (tip[0], tip[1], tip[2] - 0.58), (tip[0], tip[1], tip[2] + 0.58), 1.12, 1.12, sides=14, bone_idx=b_gun)
        m.add_tapered_prism(metal, (tip[0], tip[1], tip[2] - 0.66), (tip[0], tip[1], tip[2] + 0.66), 0.48, 0.48, sides=10, bone_idx=b_gun)
        m.add_tapered_prism(glow, (tip[0], tip[1], tip[2] - 0.70), (tip[0], tip[1], tip[2] + 0.70), 0.22, 0.22, sides=8, bone_idx=b_gun)
        # Taut bowstring + crossed buss cables
        m.add_tapered_prism(brass, (tip[0], tip[1], tip[2] + 0.14), (6.5, 0.0, 2.74), 0.085, 0.085, sides=6, bone_idx=b_gun)
        m.add_tapered_prism(metal, (tip[0], tip[1], tip[2] - 0.26), (17.5, -side * 1.2, 1.9), 0.065, 0.065, sides=6, bone_idx=b_gun)

    # Forward steel foot-stirrup loop with rubberized toe grip sleeve
    stirrup = [
        (22.0, -2.4, 1.6),
        (25.8, -2.2, 1.0),
        (26.9, 0.0, 0.8),
        (25.8, +2.2, 1.0),
        (22.0, +2.4, 1.6),
    ]
    for i in range(len(stirrup) - 1):
        m.add_tapered_prism(metal, stirrup[i], stirrup[i + 1], 0.24, 0.24, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(brass, (25.6, -1.3, 0.92), (25.6, +1.3, 0.92), 0.28, 0.28, sides=10, bone_idx=b_gun)

    # Low-profile brass-ringed tactical rail optic scope kept strictly below Z=3.60 (0 ADS occlusion, O10!)
    m.add_box(brass, (0.8, -0.18, 2.74), (0.72, 0.84, 0.56), bone_idx=b_gun)
    m.add_box(brass, (5.2, -0.18, 2.74), (0.72, 0.84, 0.56), bone_idx=b_gun)
    m.add_tapered_prism(metal, (-0.8, -0.18, 3.04), (7.6, -0.18, 3.04), 0.36, 0.42, sides=16, bone_idx=b_gun, cap_start=False, cap_end=False)
    m.add_tapered_prism(brass, (-1.18, -0.18, 3.04), (-0.74, -0.18, 3.04), 0.41, 0.38, sides=16, bone_idx=b_gun, cap_start=False, cap_end=False)
    # Side-mounted knurled windage & elevation turrets (never protruding into upper ADS sightline!)
    m.add_tapered_prism(brass, (3.0, +0.20, 3.04), (3.0, +0.60, 3.04), 0.19, 0.19, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(brass, (3.0, -0.54, 3.04), (3.0, -0.92, 3.04), 0.19, 0.19, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(metal, (7.4, -0.18, 3.04), (9.2, -0.18, 3.04), 0.42, 0.50, sides=16, bone_idx=b_gun, cap_start=False, cap_end=False)
    m.add_tapered_prism(brass, (9.0, -0.18, 3.04), (9.48, -0.18, 3.04), 0.52, 0.52, sides=16, bone_idx=b_gun, cap_start=False, cap_end=False)
    m.add_tapered_prism(glow, (9.36, -0.18, 3.04), (9.52, -0.18, 3.04), 0.53, 0.53, sides=16, bone_idx=b_gun, cap_start=False, cap_end=False)

    return m


def build_crossbow_bolt() -> MeshBuilder:
    """Custom rigid aerodynamic explosive crossbow bolt (replaces stock kbar knife)."""
    m = MeshBuilder("bz_crossbow_bolt", BONES_RIGID, model_type="rigid")
    metal = "mtl_bz_xbow_metal"
    brass = "mtl_bz_xbow_brass"
    glow = "mtl_bz_xbow_glow"

    # Centered along +X (total 21u length so flying & zombie-pinned bolts read clearly!)
    m.add_tapered_prism(metal, (-9.2, 0.0, 0.0), (5.0, 0.0, 0.0), 0.28, 0.28, sides=10, bone_idx=0)
    # Fluted brass retention collar + glowing explosive charge ring
    m.add_tapered_prism(brass, (3.8, 0.0, 0.0), (5.2, 0.0, 0.0), 0.44, 0.50, sides=10, bone_idx=0)
    m.add_tapered_prism(glow, (5.1, 0.0, 0.0), (6.0, 0.0, 0.0), 0.54, 0.56, sides=10, bone_idx=0)
    m.add_tapered_prism(brass, (5.9, 0.0, 0.0), (6.4, 0.0, 0.0), 0.50, 0.44, sides=10, bone_idx=0)
    # Glowing amber-orange diamond explosive broadhead tip
    m.add_tapered_prism(glow, (6.2, 0.0, 0.0), (11.4, 0.0, 0.0), 0.82, 0.06, sides=4, bone_idx=0, angle_offset_deg=45.0)
    # 3 swept brass fletching vanes at tail
    for fdeg in (0.0, 120.0, 240.0):
        rad = math.radians(fdeg)
        cy, cz = math.cos(rad), math.sin(rad)
        p0 = (-8.8, cy * 0.26, cz * 0.26)
        p1 = (-3.8, cy * 0.26, cz * 0.26)
        p2 = (-6.2, cy * 1.55, cz * 1.55)
        p3 = (-9.4, cy * 1.42, cz * 1.42)
        m.add_quad(brass, p0, p1, p2, p3, bone_idx=0, double_sided=True)
    # Bright glowing tail nock beacon so pinned bolts visibly pulse before detonation
    m.add_tapered_prism(glow, (-10.0, 0.0, 0.0), (-8.5, 0.0, 0.0), 0.46, 0.34, sides=10, bone_idx=0)
    return m


# ---------------------------------------------------------------------------
# 3. BLADE BOOMERANG (Custom Curved Crescent Tri-Blade Boomerang — Held & Air)
# ---------------------------------------------------------------------------


def build_blade_boomerang_held(name: str, is_world: bool = False) -> MeshBuilder:
    """Handheld sculpted 3-wing Crescent Boomerang framed cleanly above the Ray Gun idle right hand (O3/A2/F3/F25)!

    Compact wing radius (3.52u held wings, 4.87u pommel-to-hub) centered at (0.35, 0.0, 2.05) so ALL 3 curved
    Damascus steel wings and the leather grip/hand read cleanly on screen with zero bottom-edge clipping!
    """
    bones = world_weapon_bones((4.5, 0.0, 2.05)) if is_world else BONES_COLT45
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0

    steel = "mtl_bz_blade_steel"
    leather = "mtl_bz_blade_leather"
    brass = "mtl_bz_blade_brass"
    glow = "mtl_bz_blade_glow"

    # Match world-held boomerang scale closely to airborne bz_boomerang_blade_air (world 8.62u vs air 10.15u -> 1.18x, S12/O14/F15/O19/F22/F25!)
    # while keeping first-person held model crisp & unclipped inside viewmodel_ray_gun_idle (3.52u held wings, F3!).
    scale = 2.45 if is_world else 1.0
    hub: Vec3 = (0.35 * scale, 0.0, 2.05 * scale)

    # Compact stitched leather throwing grip seated directly inside the right palm (j_gun origin),
    # with the upper brass collar extending seamlessly into the scaled hub center (zero gap, A13/S15!).
    m.add_tapered_prism(leather, (0.0, 0.0, -2.4), (0.0, 0.0, 0.9), 0.38, 0.36, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(brass, (0.0, 0.0, -2.75), (0.0, 0.0, -2.35), 0.46, 0.40, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(brass, (0.0, 0.0, 0.80), hub, 0.44, 0.56 * scale, sides=10, bone_idx=b_gun)

    # Circular machined brass gyro-hub tilted cleanly toward the player so ALL 3 wings read!
    hub_axis = v_norm((-0.72, 0.42, 0.55))
    m.add_tapered_prism(
        brass,
        v_sub(hub, v_scale(hub_axis, 0.24 * scale)),
        v_add(hub, v_scale(hub_axis, 0.24 * scale)),
        0.78 * scale,
        0.78 * scale,
        sides=14,
        bone_idx=b_gun,
    )
    m.add_tapered_prism(
        glow,
        v_sub(hub, v_scale(hub_axis, 0.28 * scale)),
        v_add(hub, v_scale(hub_axis, 0.28 * scale)),
        0.36 * scale,
        0.36 * scale,
        sides=12,
        bone_idx=b_gun,
    )

    # 3 symmetric curved scimitar-boomerang wings (3.52u held wings / 8.62u world -> matches 10.15u air blade!)
    u_axis = v_norm((0.62, 0.52, 0.58))
    v_axis = v_norm(v_cross(hub_axis, u_axis))
    for arm in range(3):
        base_deg = arm * 120.0 + 15.0
        pts: list[Vec3] = []
        ws: list[float] = []
        ts: list[float] = []
        for k in range(11):
            u = k / 10.0
            r = (0.60 + u * 2.80) * scale
            ang = math.radians(base_deg + u * 48.0)
            local = v_add(v_scale(u_axis, math.cos(ang) * r), v_scale(v_axis, math.sin(ang) * r))
            pts.append(v_add(hub, local))
            ws.append((0.78 * (1.0 - 0.50 * u) + 0.18 * math.sin(u * math.pi)) * scale)
            ts.append((0.22 * (1.0 - 0.62 * u)) * scale)
        m.add_swept_blade(steel, glow, pts, ws, ts, normal_axis=hub_axis, bone_idx=b_gun, glow_outer=True)

    return m


def build_blade_boomerang_air() -> MeshBuilder:
    """Custom rigid YZ-plane 3-wing Crescent Tri-Blade Boomerang (10.15u radius, ~17.0u YZ span, normal along +X for wobble-free RotateRoll spin, O18/F19)."""
    m = MeshBuilder("bz_boomerang_blade_air", BONES_RIGID, model_type="rigid")
    steel = "mtl_bz_blade_steel"
    brass = "mtl_bz_blade_brass"
    glow = "mtl_bz_blade_glow"

    # Spin axis lies along +X so RotateRoll spins the 3 wings in their own plane facing squarely toward the thrower!
    m.add_tapered_prism(brass, (-0.64, 0.0, 0.0), (+0.64, 0.0, 0.0), 1.95, 1.95, sides=14, bone_idx=0)
    m.add_tapered_prism(glow, (-0.74, 0.0, 0.0), (+0.74, 0.0, 0.0), 1.05, 1.05, sides=12, bone_idx=0)

    for arm in range(3):
        base_deg = arm * 120.0
        pts: list[Vec3] = []
        ws: list[float] = []
        ts: list[float] = []
        for k in range(11):
            u = k / 10.0
            r = 1.45 + u * 8.35
            sweep_deg = base_deg + u * 48.0
            rad = math.radians(sweep_deg)
            pts.append((0.0, math.cos(rad) * r, math.sin(rad) * r))
            ws.append(2.25 * (1.0 - 0.48 * u) + 0.52 * math.sin(u * math.pi))
            ts.append(0.68 * (1.0 - 0.58 * u))
        m.add_swept_blade(steel, glow, pts, ws, ts, normal_axis=(1.0, 0.0, 0.0), bone_idx=0, glow_outer=True)

    return m


# ---------------------------------------------------------------------------
# 4. ACID SPRAYER (Industrial Biohazard Pressurized Chemical Projector)
# ---------------------------------------------------------------------------


def build_acid_sprayer(name: str, is_world: bool = False) -> MeshBuilder:
    bones = world_weapon_bones((17.71, 0.0, -0.29)) if is_world else BONES_FLAMETHROWER
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0

    metal = "mtl_bz_acid_metal"
    hazard = "mtl_bz_acid_hazard"
    glow = "mtl_bz_acid_glow"

    # Contoured rear industrial manifold + right-hand trigger grip seated directly in flamethrower fist (S5/O4)!
    m.add_tapered_prism(metal, (-5.6, -1.0, -1.2), (-0.8, -0.15, -0.30), 0.92, 1.25, sides=12, bone_idx=b_gun)
    # Angled right-hand pistol trigger grip extending straight into the right fist at bottom-right
    m.add_tapered_prism(metal, (-4.4, -2.55, -4.15), (-2.1, -1.35, -1.15), 0.72, 0.80, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(hazard, (-3.9, -2.25, -3.45), (-2.6, -1.62, -1.85), 0.78, 0.78, sides=10, bone_idx=b_gun, cap_start=False, cap_end=False)
    m.add_tapered_prism(metal, (-3.0, -1.85, -2.2), (-0.4, -0.35, -0.45), 0.52, 0.62, sides=8, bone_idx=b_gun)

    # Main heavy pressurized manifold barrel running to tag_flash (17.71, 0, -0.29)
    m.add_tapered_prism(metal, (-1.0, 0.0, -0.25), (14.4, 0.0, -0.30), 1.24, 1.05, sides=12, bone_idx=b_gun)
    # Forward ribbed support sleeve (left hand grips here cleanly!)
    m.add_tapered_prism(metal, (4.8, 0.0, -1.0), (10.8, 0.0, -1.0), 0.92, 0.86, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(hazard, (6.2, 0.0, -0.26), (9.4, 0.0, -0.26), 1.36, 1.36, sides=12, bone_idx=b_gun, cap_start=False, cap_end=False)

    # Lowered & outboard upper-left glowing neon-green Pressurized Acid Tank (Z top <= 2.0 -> 100% clear of hip reticle, F4!)
    m.add_tapered_prism(glow, (1.4, 2.45, 0.78), (10.4, 2.45, 0.78), 1.18, 1.18, sides=14, bone_idx=b_gun, cap_start=False, cap_end=False)
    m.add_tapered_prism(hazard, (0.3, 2.45, 0.78), (1.5, 2.45, 0.78), 1.30, 1.30, sides=14, bone_idx=b_gun, cap_start=False, cap_end=False)
    m.add_tapered_prism(hazard, (10.2, 2.45, 0.78), (11.3, 2.45, 0.78), 1.30, 1.12, sides=14, bone_idx=b_gun, cap_start=False, cap_end=False)
    # Domed brushed-steel pressure end-caps & valve stem (zero bullseye caps!)
    m.add_tapered_prism(metal, (-0.55, 2.45, 0.78), (0.35, 2.45, 0.78), 0.68, 1.30, sides=14, bone_idx=b_gun)
    m.add_tapered_prism(metal, (-1.05, 2.45, 0.78), (-0.50, 2.45, 0.78), 0.34, 0.34, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(metal, (11.25, 2.45, 0.78), (12.05, 2.45, 0.78), 1.12, 0.56, sides=14, bone_idx=b_gun)
    for ring_x in (3.6, 5.9, 8.2):
        m.add_tapered_prism(metal, (ring_x - 0.24, 2.45, 0.78), (ring_x + 0.24, 2.45, 0.78), 1.30, 1.30, sides=14, bone_idx=b_gun)
    # Curved chemical feed pipe from acid tank into front nozzle block
    m.add_tapered_prism(metal, (11.8, 2.45, 0.78), (13.8, 0.95, 0.10), 0.38, 0.35, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(glow, (11.8, 2.45, 0.78), (13.7, 1.15, 0.25), 0.18, 0.18, sides=8, bone_idx=b_gun)

    # Secondary right-side pressurized biohazard propellant cylinder (outboard & low!)
    m.add_tapered_prism(hazard, (2.2, -2.10, 0.55), (8.8, -2.10, 0.55), 0.92, 0.92, sides=12, bone_idx=b_gun, cap_start=False, cap_end=False)
    m.add_tapered_prism(metal, (1.4, -2.10, 0.55), (2.25, -2.10, 0.55), 0.48, 0.92, sides=12, bone_idx=b_gun)
    m.add_tapered_prism(metal, (8.75, -2.10, 0.55), (9.55, -2.10, 0.55), 0.92, 0.48, sides=12, bone_idx=b_gun)
    m.add_tapered_prism(metal, (9.4, -2.10, 0.55), (12.9, -0.75, -0.15), 0.32, 0.30, sides=8, bone_idx=b_gun)

    # Compact side-mounted pressure gauge with glowing neon-green dial (below hip reticle!)
    m.add_tapered_prism(metal, (1.8, -0.25, 0.85), (2.3, -0.25, 1.65), 0.72, 0.72, sides=12, bone_idx=b_gun)
    m.add_tapered_prism(glow, (1.68, -0.25, 1.12), (1.48, -0.25, 1.38), 0.48, 0.48, sides=12, bone_idx=b_gun)

    # Hazard-striped cowling collar + flared octagonal Bio-Atomizer Nozzle Cone
    m.add_tapered_prism(hazard, (11.8, 0.0, -0.26), (14.4, 0.0, -0.28), 1.52, 1.68, sides=10, bone_idx=b_gun, cap_start=False, cap_end=False)
    m.add_tapered_prism(metal, (14.2, 0.0, -0.28), (17.6, 0.0, -0.29), 1.52, 2.15, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(glow, (16.4, 0.0, -0.28), (17.85, 0.0, -0.29), 1.28, 1.48, sides=10, bone_idx=b_gun)
    for tdeg in (30.0, 150.0, 270.0):
        rad = math.radians(tdeg)
        ty = math.cos(rad) * 1.78
        tz = -0.29 + math.sin(rad) * 1.78
        m.add_tapered_prism(metal, (16.6, ty, tz), (18.4, ty * 0.78, -0.29 + math.sin(rad) * 1.4), 0.22, 0.12, sides=8, bone_idx=b_gun)
        m.add_tapered_prism(glow, (18.2, ty * 0.78, -0.29 + math.sin(rad) * 1.4), (18.9, ty * 0.72, -0.29 + math.sin(rad) * 1.3), 0.15, 0.07, sides=8, bone_idx=b_gun)

    return m


# ---------------------------------------------------------------------------
# 5. PORTAL GRENADE (Gyroscopic Violet-Blue Rift Orb — Held & Airborne/Anchor)
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
        m.add_tapered_prism(mat_name, p0, p1, tube_r, tube_r, sides=6, bone_idx=bone_idx, cap_start=False, cap_end=False)


def _add_octa_sphere_core(
    m: MeshBuilder,
    mat_name: str,
    center: Vec3,
    radius: float,
    bone_idx: int = 0,
) -> None:
    # Layered octagonal crystal orb built cleanly from watertight tapered prisms
    z_bands = (-1.0, -0.72, -0.30, 0.30, 0.72, 1.0)
    r_bands = (0.04, 0.68, 0.98, 0.98, 0.68, 0.04)
    for i in range(len(z_bands) - 1):
        p0 = (center[0], center[1], center[2] + z_bands[i] * radius)
        p1 = (center[0], center[1], center[2] + z_bands[i + 1] * radius)
        m.add_tapered_prism(
            mat_name,
            p0,
            p1,
            r_bands[i] * radius,
            r_bands[i + 1] * radius,
            sides=12,
            bone_idx=bone_idx,
            cap_start=(i == 0),
            cap_end=(i == len(z_bands) - 2),
        )


def build_portal_grenade_held(name: str, is_world: bool = False) -> MeshBuilder:
    bones = world_weapon_bones((4.0, 0.0, 2.0)) if is_world else BONES_COLT45
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0

    ring = "mtl_bz_portal_ring"
    core = "mtl_bz_portal_core"
    trim = "mtl_bz_portal_trim"

    scale = 1.65 if is_world else 1.0
    center: Vec3 = (1.6 * scale, 0.0, 2.1 * scale)

    # Palm cradle emitter stem seated in right hand (j_gun origin)
    m.add_tapered_prism(ring, (0.0, 0.0, -1.8 * scale), (0.5 * scale, 0.0, 0.4 * scale), 0.42 * scale, 0.56 * scale, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(trim, (0.4 * scale, 0.0, 0.3 * scale), (center[0] * 0.7, 0.0, center[2] - 1.15 * scale), 0.62 * scale, 0.95 * scale, sides=12, bone_idx=b_gun)

    # Luminous violet-blue crystalline portal orb core
    _add_octa_sphere_core(m, core, center, 1.38 * scale, bone_idx=b_gun)

    # 3 intersecting gyroscopic silver-violet & gold containment rings
    _add_gyro_ring(m, ring, center, 1.82 * scale, 0.16 * scale, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), segs=16, bone_idx=b_gun)
    _add_gyro_ring(m, trim, center, 1.98 * scale, 0.14 * scale, v_norm((0.7, 0.0, 0.7)), (0.0, 1.0, 0.0), segs=16, bone_idx=b_gun)
    _add_gyro_ring(m, ring, center, 2.12 * scale, 0.13 * scale, v_norm((-0.7, 0.0, 0.7)), (0.0, 1.0, 0.0), segs=16, bone_idx=b_gun)

    # 4 glowing emitter pylons around equator
    for deg in (0.0, 90.0, 180.0, 270.0):
        rad = math.radians(deg)
        dx, dy = math.cos(rad), math.sin(rad)
        p0 = v_add(center, (dx * 1.48 * scale, dy * 1.48 * scale, 0.0))
        p1 = v_add(center, (dx * 2.24 * scale, dy * 2.24 * scale, 0.0))
        m.add_tapered_prism(trim, p0, p1, 0.24 * scale, 0.14 * scale, sides=8, bone_idx=b_gun)
    return m


def build_portal_orb_air() -> MeshBuilder:
    """Rigid glowing violet-blue rift orb used for thrown orb & rotating deployed portal anchor."""
    m = MeshBuilder("bz_portal_orb_air", BONES_RIGID, model_type="rigid")
    ring = "mtl_bz_portal_ring"
    core = "mtl_bz_portal_core"
    trim = "mtl_bz_portal_trim"

    center: Vec3 = (0.0, 0.0, 0.0)
    _add_octa_sphere_core(m, core, center, 6.2, bone_idx=0)
    _add_gyro_ring(m, ring, center, 8.8, 0.72, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), segs=18, bone_idx=0)
    _add_gyro_ring(m, trim, center, 10.2, 0.62, v_norm((0.707, 0.0, 0.707)), (0.0, 1.0, 0.0), segs=18, bone_idx=0)
    _add_gyro_ring(m, ring, center, 11.4, 0.56, v_norm((-0.707, 0.0, 0.707)), (0.0, 1.0, 0.0), segs=18, bone_idx=0)
    # Vertical glowing rift spire needles at poles
    m.add_tapered_prism(trim, (0.0, 0.0, 6.0), (0.0, 0.0, 12.5), 1.0, 0.18, sides=8, bone_idx=0)
    m.add_tapered_prism(trim, (0.0, 0.0, -6.0), (0.0, 0.0, -12.5), 1.0, 0.18, sides=8, bone_idx=0)
    return m


def build_war_club_held(name: str, is_world: bool) -> MeshBuilder:
    """Custom 3D iron-banded spiked trench War Club (viewmodel & worldmodel)."""
    bones = world_weapon_bones((12.0, 0.0, 2.5)) if is_world else BONES_COLT45
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0
    s = 1.85 if is_world else 1.0

    wood = "mtl_bz_club_wood"
    iron = "mtl_bz_club_iron"
    glow = "mtl_bz_club_glow"
    leather = "mtl_bz_blade_leather"

    # Club axis sweeps forward-upward from the right grip so it fills the melee swing arc boldly
    def pt(t: float) -> Vec3:
        return (
            (-1.2 + t * 11.4) * s,
            (0.0) * s,
            (-2.4 + t * 10.6) * s,
        )

    axis = v_norm(v_sub(pt(1.0), pt(0.0)))
    side_u = (0.0, 1.0, 0.0)
    side_v = v_norm(v_cross(axis, side_u))

    # 1. Forged iron pommel cap & butt spike
    m.add_tapered_prism(iron, pt(-0.14), pt(-0.04), 0.14 * s, 0.72 * s, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(iron, pt(-0.04), pt(0.06), 0.76 * s, 0.62 * s, sides=10, bone_idx=b_gun)

    # 2. Ribbed leather grip & wrist-guard collar
    m.add_tapered_prism(leather, pt(0.06), pt(0.38), 0.56 * s, 0.60 * s, sides=10, bone_idx=b_gun)
    for gt in (0.12, 0.20, 0.28, 0.36):
        m.add_tapered_prism(iron, pt(gt - 0.015), pt(gt + 0.015), 0.64 * s, 0.64 * s, sides=10, bone_idx=b_gun)

    # 3. Heavy octagonal hardwood war-club shaft flaring into a brutal striking head
    m.add_tapered_prism(wood, pt(0.38), pt(0.68), 0.64 * s, 1.05 * s, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(wood, pt(0.68), pt(0.96), 1.05 * s, 1.38 * s, sides=10, bone_idx=b_gun)

    # 4. Three bolted forged-iron reinforcement collars around the striking head
    for band_t, r0, r1 in ((0.64, 1.06, 1.14), (0.80, 1.26, 1.36), (0.94, 1.42, 1.46)):
        m.add_tapered_prism(iron, pt(band_t - 0.045), pt(band_t + 0.045), r0 * s, r1 * s, sides=10, bone_idx=b_gun)

    # 5. Recessed glowing kinetic forge bands (shockwave energy rings on club head)
    for glow_t, gr in ((0.72, 1.18), (0.87, 1.36)):
        m.add_tapered_prism(glow, pt(glow_t - 0.018), pt(glow_t + 0.018), gr * s, gr * s, sides=10, bone_idx=b_gun)

    # 6. Heavy domed iron crown & top impact spike
    m.add_tapered_prism(iron, pt(0.96), pt(1.06), 1.40 * s, 0.86 * s, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(iron, pt(1.06), pt(1.18), 0.56 * s, 0.10 * s, sides=8, bone_idx=b_gun)

    # 7. 12 forged conical iron spikes radiating around the two head collars (2 rings x 6 spikes)
    for ring_t, base_r, spike_len, phase_deg in ((0.80, 1.24, 0.92, 0.0), (0.94, 1.36, 1.02, 30.0)):
        c = pt(ring_t)
        for k in range(6):
            ang = math.radians(phase_deg + k * 60.0)
            rad_dir = v_add(v_scale(side_u, math.cos(ang)), v_scale(side_v, math.sin(ang)))
            sp0 = v_add(c, v_scale(rad_dir, base_r * s))
            sp1 = v_add(c, v_scale(rad_dir, (base_r + spike_len) * s))
            m.add_tapered_prism(iron, sp0, sp1, 0.24 * s, 0.05 * s, sides=6, bone_idx=b_gun)
    return m


def build_station_kiosk(name: str, kind: str) -> MeshBuilder:
    """Tall color-coded 3D In-World Station Kiosk (rigid, z=0 floor flush, 0 added FX)."""
    m = MeshBuilder(name, BONES_RIGID, model_type="rigid")
    frame = "mtl_bz_kiosk_frame"
    brass = "mtl_bz_kiosk_brass"
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

    # Heavy beveled steel floor plinth (flush at z=0 so floor-snap seats it cleanly)
    add_aabb(frame, -11.5, -16.0, 0.0, 11.5, 16.0, 5.0)
    add_aabb(brass, -10.5, -15.0, 5.0, 10.5, 15.0, 7.2)

    if kind == "perks":
        # Emerald Perk Vending Terminal: sleek steel cabinet + 3 recessed emerald elixir vials + lit marquee
        add_aabb(frame, -9.5, -13.5, 7.2, 8.5, 13.5, 56.0)
        add_aabb(brass, -10.2, -14.5, 56.0, 10.2, 14.5, 59.0)
        add_aabb(frame, -9.2, -13.5, 59.0, 7.5, 13.5, 68.0)
        add_aabb(glow, 7.5, -11.5, 60.5, 9.4, 11.5, 66.5)
        add_aabb(frame, -10.0, -14.2, 68.0, 10.0, 14.2, 71.0)
        for ty in (-8.0, 0.0, 8.0):
            m.add_tapered_prism(glow, (9.0, ty, 19.0), (9.0, ty, 50.0), 2.1, 2.1, sides=10, bone_idx=0)
            m.add_tapered_prism(brass, (9.0, ty, 15.5), (9.0, ty, 19.2), 2.7, 2.5, sides=10, bone_idx=0)
            m.add_tapered_prism(brass, (9.0, ty, 49.8), (9.0, ty, 53.2), 2.5, 2.7, sides=10, bone_idx=0)
        add_aabb(brass, 8.0, -11.5, 11.0, 10.0, 11.5, 13.5)
        add_aabb(glow, 8.2, -9.5, 13.5, 9.6, 9.5, 15.2)
    elif kind == "class":
        # Cobalt/Gold Class Altar Console: octagonal dais + brass lectern + twin crest pylons + floating crystal
        m.add_tapered_prism(frame, (0.0, 0.0, 7.2), (0.0, 0.0, 39.0), 10.5, 7.5, sides=8, bone_idx=0)
        add_aabb(brass, -7.5, -11.5, 39.0, 9.5, 11.5, 43.0)
        add_aabb(glow, -5.5, -9.5, 43.0, 8.0, 9.5, 45.2)
        for sy in (-12.8, 12.8):
            m.add_tapered_prism(frame, (-1.5, sy, 7.2), (-1.5, sy, 60.0), 2.6, 1.9, sides=8, bone_idx=0)
            m.add_tapered_prism(brass, (-1.5, sy, 60.0), (-1.5, sy, 67.0), 2.3, 0.5, sides=8, bone_idx=0)
            add_aabb(glow, 0.8, sy - 0.9, 20.0, 2.2, sy + 0.9, 54.0)
        _add_octa_sphere_core(m, glow, (0.0, 0.0, 58.0), 5.0, bone_idx=0)
        _add_gyro_ring(m, brass, (0.0, 0.0, 58.0), 7.6, 0.62, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), segs=14, bone_idx=0)
    elif kind == "arsenal":
        # Amber/Gunmetal Arsenal Weapon Locker & Workbench: armored bench + slotted display rack + canopy
        add_aabb(frame, -10.0, -15.5, 7.2, 9.5, 15.5, 31.0)
        add_aabb(brass, -10.6, -16.2, 31.0, 10.8, 16.2, 33.8)
        add_aabb(frame, -9.5, -14.8, 33.8, -1.5, 14.8, 63.0)
        add_aabb(glow, -1.5, -12.2, 38.0, 0.6, 12.2, 58.5)
        for rz in (42.0, 48.5, 55.0):
            add_aabb(brass, 0.4, -11.5, rz, 2.4, 11.5, rz + 1.5)
        for sy in (-14.5, 14.5):
            m.add_tapered_prism(frame, (6.5, sy, 33.8), (6.5, sy, 63.0), 1.6, 1.4, sides=8, bone_idx=0)
        add_aabb(frame, -10.2, -16.0, 63.0, 9.5, 16.0, 67.5)
        add_aabb(glow, 8.8, -13.0, 64.0, 10.2, 13.0, 66.5)
    else:
        # Violet Pack-a-Punch Forge Console: vaulted chassis + glowing intake bay + twin plasma coils + spire
        add_aabb(frame, -10.5, -14.5, 7.2, 9.0, 14.5, 40.0)
        add_aabb(glow, 7.2, -9.5, 22.0, 9.8, 9.5, 33.5)
        add_aabb(brass, 7.5, -11.0, 19.5, 10.6, 11.0, 22.0)
        add_aabb(brass, 7.5, -11.0, 33.5, 10.6, 11.0, 36.0)
        add_aabb(frame, -9.0, -12.0, 40.0, 7.5, 12.0, 60.0)
        add_aabb(glow, 6.2, -9.0, 44.0, 8.4, 9.0, 56.0)
        for sy in (-14.2, 14.2):
            m.add_tapered_prism(glow, (0.0, sy, 13.0), (0.0, sy, 60.0), 2.3, 1.9, sides=10, bone_idx=0)
            for cz in (22.0, 35.0, 48.0):
                m.add_tapered_prism(brass, (0.0, sy, cz - 1.3), (0.0, sy, cz + 1.3), 3.1, 3.1, sides=10, bone_idx=0)
        m.add_tapered_prism(brass, (0.0, 0.0, 60.0), (0.0, 0.0, 67.0), 8.2, 3.8, sides=8, bone_idx=0)
        m.add_tapered_prism(glow, (0.0, 0.0, 67.0), (0.0, 0.0, 74.0), 3.4, 0.5, sides=8, bone_idx=0)
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
    # Calibrated WaW specular levels (30-72 for metals, 16-24 wood/leather) so Der Riese's cool sky
    # cubemap never washes weapon palettes blue or turns brass olive (F2/O9).
    # Cryo Cannon
    MaterialSpec("mtl_bz_cryo_hull", "model phong", "metal", "cryo_armor", (218, 232, 244), (118, 152, 182), (62, 68, 72), 205),
    MaterialSpec("mtl_bz_cryo_dark", "model phong", "metal", "brushed_metal", (34, 48, 66), (72, 96, 122), (48, 56, 66), 185),
    MaterialSpec("mtl_bz_cryo_glow", "model unlit", "glass", "cryo_glow", (16, 165, 246), (178, 246, 255)),
    # Multi-Crossbow
    MaterialSpec("mtl_bz_xbow_wood", "model phong", "wood", "wood_grain", (102, 58, 30), (58, 30, 14), (24, 18, 14), 85),
    MaterialSpec("mtl_bz_xbow_metal", "model phong", "metal", "panel_metal", (52, 54, 58), (80, 84, 90), (48, 50, 54), 165),
    MaterialSpec("mtl_bz_xbow_brass", "model phong", "metal", "brushed_metal", (206, 158, 62), (142, 98, 30), (68, 54, 24), 205),
    MaterialSpec("mtl_bz_xbow_glow", "model unlit", "glass", "amber_glow", (245, 132, 18), (255, 220, 118)),
    # Blade Boomerang
    MaterialSpec("mtl_bz_blade_steel", "model phong", "metal", "damascus", (176, 184, 194), (102, 110, 120), (68, 72, 76), 220),
    MaterialSpec("mtl_bz_blade_leather", "model phong", "cloth", "leather", (76, 48, 28), (46, 28, 14), (18, 14, 10), 65),
    MaterialSpec("mtl_bz_blade_brass", "model phong", "metal", "brushed_metal", (212, 162, 64), (144, 100, 32), (68, 54, 24), 205),
    MaterialSpec("mtl_bz_blade_glow", "model unlit", "glass", "edge_glow", (62, 185, 220), (210, 238, 245)),
    # Acid Sprayer
    MaterialSpec("mtl_bz_acid_metal", "model phong", "metal", "corroded_metal", (62, 68, 60), (96, 108, 86), (44, 48, 42), 145),
    MaterialSpec("mtl_bz_acid_hazard", "model phong", "metal", "hazard_stripes", (236, 194, 22), (26, 28, 26), (42, 40, 26), 130),
    MaterialSpec("mtl_bz_acid_glow", "model unlit", "glass", "acid_glow", (42, 242, 68), (182, 255, 116)),
    # Acid Sprayer Gas Stream (2D FLAMETABLEFILE effect materials, 0 added FX slots — ADR-0004)
    MaterialSpec("mtl_bz_acid_stream", "effect", "<none>", "acid_stream", (32, 235, 58), (190, 255, 120), blend_func="Add", z_feather=False, fogable=False),
    MaterialSpec("mtl_bz_acid_billow", "effect", "<none>", "acid_billow", (28, 220, 52), (175, 255, 102), blend_func="Add", z_feather=True, fogable=False),
    MaterialSpec("mtl_bz_acid_drips", "effect", "<none>", "acid_drips", (46, 248, 66), (215, 255, 138), blend_func="Add", z_feather=True, fogable=False),
    MaterialSpec("mtl_bz_acid_mist", "effect", "<none>", "acid_mist", (72, 175, 62), (145, 220, 96), blend_func="Blend", z_feather=True, fogable=True),
    # Portal Grenade (violet-blue rift orb & gyroscopic containment rings)
    MaterialSpec("mtl_bz_portal_ring", "model phong", "metal", "brushed_metal", (76, 68, 112), (142, 128, 188), (62, 56, 74), 210),
    MaterialSpec("mtl_bz_portal_core", "model unlit", "glass", "portal_glow", (112, 42, 248), (186, 232, 255)),
    MaterialSpec("mtl_bz_portal_trim", "model phong", "metal", "brushed_metal", (208, 166, 72), (138, 100, 32), (66, 54, 26), 205),
    # War Club (forged iron-banded hardwood trench club + glowing shockwave runes)
    MaterialSpec("mtl_bz_club_wood", "model phong", "wood", "wood_grain", (84, 48, 26), (44, 24, 12), (22, 18, 14), 78),
    MaterialSpec("mtl_bz_club_iron", "model phong", "metal", "corroded_metal", (54, 58, 64), (92, 98, 108), (58, 62, 68), 180),
    MaterialSpec("mtl_bz_club_glow", "model unlit", "glass", "amber_glow", (245, 118, 22), (255, 214, 110)),
    # In-World Station Kiosks (Perks emerald, Class cobalt, Arsenal amber, Pack-a-Punch violet)
    MaterialSpec("mtl_bz_kiosk_frame", "model phong", "metal", "panel_metal", (42, 48, 56), (72, 80, 92), (52, 56, 62), 180),
    MaterialSpec("mtl_bz_kiosk_brass", "model phong", "metal", "brushed_metal", (198, 152, 62), (132, 94, 30), (64, 52, 24), 200),
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

            if spec.style == "cryo_armor":
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
