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

# Wave 3 (NSV-W3, Sheet 10 — +8 PaP variant weapons / +16 XMODELs, strictly 4 PaP-eligible primaries)
CUSTOM_PAP_WEAPON_VIEWMODELS: dict[str, str] = {
    "bz_acid_sprayer_pap1": "viewmodel_bz_acid_sprayer_pap1",
    "bz_acid_sprayer_pap2": "viewmodel_bz_acid_sprayer_pap2",
    "bz_cryo_cannon_pap1": "viewmodel_bz_cryo_cannon_pap1",
    "bz_cryo_cannon_pap2": "viewmodel_bz_cryo_cannon_pap2",
    "bz_multi_crossbow_pap1": "viewmodel_bz_multi_crossbow_pap1",
    "bz_multi_crossbow_pap2": "viewmodel_bz_multi_crossbow_pap2",
    "bz_blade_boomerang_pap1": "viewmodel_bz_blade_boomerang_pap1",
    "bz_blade_boomerang_pap2": "viewmodel_bz_blade_boomerang_pap2",
}

CUSTOM_PAP_WEAPON_WORLDMODELS: dict[str, str] = {
    "bz_acid_sprayer_pap1": "world_bz_acid_sprayer_pap1",
    "bz_acid_sprayer_pap2": "world_bz_acid_sprayer_pap2",
    "bz_cryo_cannon_pap1": "world_bz_cryo_cannon_pap1",
    "bz_cryo_cannon_pap2": "world_bz_cryo_cannon_pap2",
    "bz_multi_crossbow_pap1": "world_bz_multi_crossbow_pap1",
    "bz_multi_crossbow_pap2": "world_bz_multi_crossbow_pap2",
    "bz_blade_boomerang_pap1": "world_bz_blade_boomerang_pap1",
    "bz_blade_boomerang_pap2": "world_bz_blade_boomerang_pap2",
}

CUSTOM_PROJECTILE_XMODELS: tuple[str, ...] = (
    "bz_crossbow_bolt",
    "bz_boomerang_blade_air",
    "bz_portal_orb_air",
    "bz_pap_cluster_sub",
)

CUSTOM_SPECIAL_WEAPON_VIEWMODELS: dict[str, str] = {
    "bz_portal_grenade": "viewmodel_bz_portal_grenade",
    "bz_war_club": "viewmodel_bz_war_club",
    "bz_pap_knife": "viewmodel_bz_pap_knife",
    "bz_pap_bowie": "viewmodel_bz_pap_bowie",
}

CUSTOM_SPECIAL_WEAPON_WORLDMODELS: dict[str, str] = {
    "bz_portal_grenade": "world_bz_portal_grenade",
    "bz_war_club": "world_bz_war_club",
    "bz_pap_knife": "world_bz_pap_knife",
    "bz_pap_bowie": "world_bz_pap_bowie",
}

CUSTOM_OFFHAND_WEAPON_VIEWMODELS: dict[str, str] = {
    "bz_pap_cluster_grenade": "viewmodel_bz_pap_cluster",
}

CUSTOM_OFFHAND_WEAPON_WORLDMODELS: dict[str, str] = {
    "bz_pap_cluster_grenade": "world_bz_pap_cluster",
}

CUSTOM_TRAP_XMODELS: tuple[str, ...] = (
    "bz_sapper_trap_fire",
    "bz_sapper_trap_betty",
)

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
    # Wave 2 (NSV-W2, Sheet 09 — 9 XMODELs, +3 weapons, 0 FX)
    "viewmodel_bz_pap_cluster",
    "world_bz_pap_cluster",
    "bz_pap_cluster_sub",
    "viewmodel_bz_pap_knife",
    "world_bz_pap_knife",
    "viewmodel_bz_pap_bowie",
    "world_bz_pap_bowie",
    "bz_sapper_trap_fire",
    "bz_sapper_trap_betty",
    # Wave 3 (NSV-W3, Sheet 10 — 16 XMODELs, +8 weapons, 0 FX)
    "viewmodel_bz_acid_sprayer_pap1",
    "world_bz_acid_sprayer_pap1",
    "viewmodel_bz_acid_sprayer_pap2",
    "world_bz_acid_sprayer_pap2",
    "viewmodel_bz_cryo_cannon_pap1",
    "world_bz_cryo_cannon_pap1",
    "viewmodel_bz_cryo_cannon_pap2",
    "world_bz_cryo_cannon_pap2",
    "viewmodel_bz_multi_crossbow_pap1",
    "world_bz_multi_crossbow_pap1",
    "viewmodel_bz_multi_crossbow_pap2",
    "world_bz_multi_crossbow_pap2",
    "viewmodel_bz_blade_boomerang_pap1",
    "world_bz_blade_boomerang_pap1",
    "viewmodel_bz_blade_boomerang_pap2",
    "world_bz_blade_boomerang_pap2",
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
    "mtl_bz_kiosk_enamel",
    "mtl_bz_kiosk_iron",
    "mtl_bz_kiosk_935",
    "mtl_bz_kiosk_brass",
    "mtl_bz_kiosk_perks_glow",
    "mtl_bz_kiosk_class_glow",
    "mtl_bz_kiosk_arsenal_glow",
    "mtl_bz_kiosk_pap_glow",
    # Wave 2 (NSV-W2, Sheet 09)
    "mtl_bz_pap_cluster_steel",
    "mtl_bz_pap_cluster_wood",
    "mtl_bz_pap_cluster_glow",
    "mtl_bz_pap_melee_steel",
    "mtl_bz_pap_knife_glow",
    "mtl_bz_pap_bowie_glow",
    "mtl_bz_trap_fire_body",
    "mtl_bz_trap_fire_glow",
    "mtl_bz_trap_betty_body",
    "mtl_bz_trap_betty_glow",
    # Wave 3 (NSV-W3, Sheet 10 — Stage 1 & Stage 2 PaP weapon finishes, zero violet bleed)
    "mtl_bz_pap1_steel",
    "mtl_bz_pap1_brass",
    "mtl_bz_pap2_steel",
    "mtl_bz_pap2_trim",
    "mtl_bz_acid_glow_pap1",
    "mtl_bz_acid_glow_pap2",
    "mtl_bz_cryo_glow_pap1",
    "mtl_bz_cryo_glow_pap2",
    "mtl_bz_xbow_glow_pap1",
    "mtl_bz_xbow_glow_pap2",
    "mtl_bz_blade_glow_pap1",
    "mtl_bz_blade_glow_pap2",
    # Wave 4 (NSV-W4, Sheet 11 — 21 linked 2D HUD icon materials, 0 FX)
    "bz_icon_class_medic",
    "bz_icon_class_titan",
    "bz_icon_class_sapper",
    "bz_icon_class_daredevil",
    "bz_icon_class_assassin",
    "bz_icon_class_broker",
    "bz_icon_perk_staminup",
    "bz_icon_perk_mulekick",
    "bz_icon_perk_armorpiercing",
    "bz_icon_perk_jugg_t2",
    "bz_icon_perk_speed_t2",
    "bz_icon_perk_dtap_t2",
    "bz_icon_perk_revive_t2",
    "bz_icon_perk_staminup_t2",
    "bz_icon_perk_mulekick_t2",
    "bz_icon_perk_armorpiercing_t2",
    "bz_icon_apex_dblammo",
    "bz_icon_apex_lightheavy",
    "bz_icon_apex_secondchance",
    "bz_icon_apex_blastshield",
    "bz_icon_pap2_badge",
)

EFFECT_MATERIALS: tuple[str, ...] = (
    "mtl_bz_acid_stream",
    "mtl_bz_acid_billow",
    "mtl_bz_acid_drips",
    "mtl_bz_acid_mist",
)

HUD_ICON_MATERIALS: tuple[str, ...] = (
    "bz_icon_class_medic",
    "bz_icon_class_titan",
    "bz_icon_class_sapper",
    "bz_icon_class_daredevil",
    "bz_icon_class_assassin",
    "bz_icon_class_broker",
    "bz_icon_perk_staminup",
    "bz_icon_perk_mulekick",
    "bz_icon_perk_armorpiercing",
    "bz_icon_perk_jugg_t2",
    "bz_icon_perk_speed_t2",
    "bz_icon_perk_dtap_t2",
    "bz_icon_perk_revive_t2",
    "bz_icon_perk_staminup_t2",
    "bz_icon_perk_mulekick_t2",
    "bz_icon_perk_armorpiercing_t2",
    "bz_icon_apex_dblammo",
    "bz_icon_apex_lightheavy",
    "bz_icon_apex_secondchance",
    "bz_icon_apex_blastshield",
    "bz_icon_pap2_badge",
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
        self._vert_map: dict[tuple[int, int, int, int], int] = {}

    def mat(self, mat_name: str) -> int:
        if mat_name not in self._mat_map:
            self._mat_map[mat_name] = len(self.materials)
            self.materials.append(mat_name)
        return self._mat_map[mat_name]

    def add_vert(self, pos: Vec3, bone_idx: int = 0) -> int:
        key = (round(pos[0] * 10000), round(pos[1] * 10000), round(pos[2] * 10000), bone_idx)
        existing = self._vert_map.get(key)
        if existing is not None:
            return existing
        idx = len(self.verts)
        self.verts.append((pos, bone_idx))
        self._vert_map[key] = idx
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

    def add_quad_uv(
        self,
        mat_name: str,
        p0: Vec3,
        p1: Vec3,
        p2: Vec3,
        p3: Vec3,
        uv0: tuple[float, float] = (0.0, 1.0),
        uv1: tuple[float, float] = (1.0, 1.0),
        uv2: tuple[float, float] = (1.0, 0.0),
        uv3: tuple[float, float] = (0.0, 0.0),
        bone_idx: int = 0,
    ) -> None:
        """Add an oriented quad (p0->p1->p2->p3 CCW outward) with explicit [0,1] UVs."""
        i0 = self.add_vert(p0, bone_idx)
        i1 = self.add_vert(p1, bone_idx)
        i2 = self.add_vert(p2, bone_idx)
        i3 = self.add_vert(p3, bone_idx)
        self.add_tri(mat_name, i0, i1, i2, uv0, uv1, uv2)
        self.add_tri(mat_name, i0, i2, i3, uv0, uv2, uv3)

    def add_beveled_box(
        self,
        mat_name: str,
        center: Vec3,
        size: Vec3,
        bevel: float = 0.6,
        bone_idx: int = 0,
        rot_xyz: Vec3 = (0.0, 0.0, 0.0),
        uv_scale: float = 0.04,
    ) -> None:
        """Chamfered box along Z (inset top & bottom faces) for realistic industrial specular catch-lights."""
        sx, sy, sz = size
        b = min(bevel, sx * 0.24, sy * 0.24, sz * 0.24)
        if b < 1e-4:
            self.add_box(mat_name, center, size, bone_idx=bone_idx, rot_xyz=rot_xyz, uv_scale=uv_scale)
            return
        hx, hy, hz = sx * 0.5, sy * 0.5, sz * 0.5
        rx, ry, rz = rot_xyz

        def xf(p: Vec3) -> Vec3:
            if rx:
                p = rot_x(p, rx)
            if ry:
                p = rot_y(p, ry)
            if rz:
                p = rot_z(p, rz)
            return v_add(p, center)

        # 4 horizontal rings: bottom inset, lower shoulder, upper shoulder, top inset
        rings_spec = (
            (hx - b, hy - b, -hz),
            (hx, hy, -hz + b),
            (hx, hy, +hz - b),
            (hx - b, hy - b, +hz),
        )
        rings = [
            [
                xf((-ax, -ay, az)),
                xf((+ax, -ay, az)),
                xf((+ax, +ay, az)),
                xf((-ax, +ay, az)),
            ]
            for ax, ay, az in rings_spec
        ]
        # Bottom (-Z) and Top (+Z) caps
        self.add_quad(mat_name, rings[0][0], rings[0][3], rings[0][2], rings[0][1], bone_idx=bone_idx, uv_scale=uv_scale)
        self.add_quad(mat_name, rings[3][0], rings[3][1], rings[3][2], rings[3][3], bone_idx=bone_idx, uv_scale=uv_scale)
        # 3 side bands (bottom chamfer, vertical wall, top chamfer)
        for band in range(3):
            r0 = rings[band]
            r1 = rings[band + 1]
            for k in range(4):
                kn = (k + 1) % 4
                self.add_quad(mat_name, r0[k], r0[kn], r1[kn], r1[k], bone_idx=bone_idx, uv_scale=uv_scale)

    def add_extruded_yz_profile(
        self,
        mat_name: str,
        x_back: float,
        x_front: float,
        yz_pts: Sequence[tuple[float, float]],
        bone_idx: int = 0,
        uv_scale: float = 0.04,
        front_uv_fit: bool = False,
    ) -> None:
        """Extrude a convex CCW 2D polygon in the (Y, Z) plane from x_back to x_front (+X front face)."""
        n = len(yz_pts)
        if n < 3:
            return
        # Ensure CCW in (Y, Z) so +X cap faces +X outward: signed area > 0
        area = sum(
            yz_pts[i][0] * yz_pts[(i + 1) % n][1] - yz_pts[(i + 1) % n][0] * yz_pts[i][1]
            for i in range(n)
        )
        pts = list(yz_pts) if area > 0.0 else list(reversed(yz_pts))
        cy = sum(p[0] for p in pts) / n
        cz = sum(p[1] for p in pts) / n
        min_y = min(p[0] for p in pts)
        max_y = max(p[0] for p in pts)
        min_z = min(p[1] for p in pts)
        max_z = max(p[1] for p in pts)
        span_y = max(max_y - min_y, 1e-4)
        span_z = max(max_z - min_z, 1e-4)

        def cap_uv(py: float, pz: float, flip_u: bool = False) -> tuple[float, float]:
            if front_uv_fit:
                u = (py - min_y) / span_y
                v = 1.0 - (pz - min_z) / span_z
                return (1.0 - u if flip_u else u, v)
            return ((py - min_y) * uv_scale, (pz - min_z) * uv_scale)

        # Front cap (+X outward: normal +X -> in YZ plane CCW: center -> p[i] -> p[i+1])
        # Viewer standing at +X looking -X sees -Y on the left and +Y on the right -> flip_u=False reads left-to-right!
        c_front = self.add_vert((x_front, cy, cz), bone_idx)
        c_front_uv = cap_uv(cy, cz, flip_u=False)
        for i in range(n):
            inext = (i + 1) % n
            va = self.add_vert((x_front, pts[i][0], pts[i][1]), bone_idx)
            vb = self.add_vert((x_front, pts[inext][0], pts[inext][1]), bone_idx)
            self.add_tri(
                mat_name,
                c_front,
                va,
                vb,
                c_front_uv,
                cap_uv(pts[i][0], pts[i][1], flip_u=False),
                cap_uv(pts[inext][0], pts[inext][1], flip_u=False),
                (1.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
            )
        # Back cap (-X outward: reverse winding)
        c_back = self.add_vert((x_back, cy, cz), bone_idx)
        c_back_uv = cap_uv(cy, cz, flip_u=True)
        for i in range(n):
            inext = (i + 1) % n
            va = self.add_vert((x_back, pts[i][0], pts[i][1]), bone_idx)
            vb = self.add_vert((x_back, pts[inext][0], pts[inext][1]), bone_idx)
            self.add_tri(
                mat_name,
                c_back,
                vb,
                va,
                c_back_uv,
                cap_uv(pts[inext][0], pts[inext][1], flip_u=True),
                cap_uv(pts[i][0], pts[i][1], flip_u=True),
                (-1.0, 0.0, 0.0),
                (-1.0, 0.0, 0.0),
                (-1.0, 0.0, 0.0),
            )
        # Perimeter walls: CCW outward around extruded rim
        for i in range(n):
            inext = (i + 1) % n
            b0 = (x_back, pts[i][0], pts[i][1])
            f0 = (x_front, pts[i][0], pts[i][1])
            f1 = (x_front, pts[inext][0], pts[inext][1])
            b1 = (x_back, pts[inext][0], pts[inext][1])
            self.add_quad(mat_name, b0, b1, f1, f0, bone_idx=bone_idx, uv_scale=uv_scale)

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
    glow = "mtl_bz_cryo_glow"   # Opaque unlit glacial cyan (#10a5f6) — recessed slits ONLY!
    brass = "mtl_bz_xbow_brass"  # Restrained weathered brass dial bezel/valve collars (<=10%, 4-slot cap)
    s_cyl = 6 if is_world else 8

    # Solid bridged 1945 skeletal rear stock & angled pistol grip (slim for Tesla reload clearance)
    m.add_beveled_box(dark, (-7.4, 0.0, -0.35), (1.1, 1.48, 3.6), bevel=0.22, bone_idx=b_gun)
    m.add_tapered_prism(hull, (-6.9, 0.0, 0.95), (-1.4, 0.0, 1.20), 0.56, 0.66, sides=s_cyl, bone_idx=b_gun, cap_start=False, cap_end=False, scale_y=0.82)
    m.add_tapered_prism(dark, (-6.8, 0.0, -1.65), (-1.0, 0.0, -0.25), 0.36, 0.42, sides=6, bone_idx=b_gun)
    m.add_beveled_box(hull, (0.8, 0.0, 1.35), (5.2, 2.24, 2.20), bevel=0.32, bone_idx=b_gun)
    # Contoured Bakelite/dark-steel pistol grip + trigger guard
    m.add_beveled_box(dark, (-0.55, 0.0, -2.55), (1.72, 1.18, 3.3), bevel=0.20, bone_idx=b_gun, rot_xyz=(0.0, 15.0, 0.0))
    m.add_box(dark, (1.15, 0.0, -3.95), (3.1, 0.64, 0.34), bone_idx=b_gun)
    m.add_box(dark, (2.55, 0.0, -2.45), (0.48, 0.68, 2.9), bone_idx=b_gun)

    # Centerline rear-face mechanical brass pressure dial at tag_fx_1 (2.05, 0.0, 2.74) directly beneath iron ring sight!
    # Smooth 12-sided lit brass bezel + high-contrast steel dial face + 3D brass indicator needle (ZERO glowing cyan bulb!)
    s_dial = 8 if is_world else 12
    m.add_tapered_prism(brass, (1.62, 0.0, 2.76), (2.28, 0.0, 2.76), 0.72, 0.66, sides=s_dial, bone_idx=b_gun)
    m.add_tapered_prism(hull, (1.54, 0.0, 2.76), (1.66, 0.0, 2.76), 0.54, 0.54, sides=s_dial, bone_idx=b_gun, cap_end=False)
    if not is_world:
        m.add_box(dark, (1.51, 0.07, 2.84), (0.06, 0.09, 0.42), bone_idx=b_gun, rot_xyz=(34.0, 0.0, 0.0))
        m.add_tapered_prism(brass, (1.48, 0.0, 2.76), (1.58, 0.0, 2.76), 0.11, 0.11, sides=8, bone_idx=b_gun)

    # Main 1945 stamped-steel boxy receiver (heavily chamfered Wintertarnung upper shroud + beveled armor cheeks, Z <= 3.25)
    # Sheet 03: clean chipped Wintertarnung steel top with longitudinal stamping ribs (NO glowing cyan dorsal laser strip!)
    m.add_beveled_box(hull, (12.8, 0.0, 1.56), (18.6, 2.82, 2.86), bevel=0.46, bone_idx=b_gun)
    m.add_beveled_box(dark, (12.6, 0.0, -0.04), (18.0, 2.10, 1.04), bevel=0.24, bone_idx=b_gun)
    # Raised dorsal sight-rail ribs (clean dark steel, Z <= 3.18 -> 100% clear of ADS sightline!)
    for ry in (-0.82, +0.82):
        m.add_beveled_box(dark, (13.2, ry, 3.06), (16.4, 0.26, 0.22), bevel=0.05, bone_idx=b_gun)
    for rx in (7.4, 13.4, 19.4):
        m.add_beveled_box(brass, (rx, 0.0, 3.08), (0.58, 1.98, 0.20), bevel=0.05, bone_idx=b_gun)
    # Recessed Wintertarnung side-panel armor cheek plates on left & right receiver flanks
    if not is_world:
        m.add_beveled_box(hull, (12.6, +1.46, 1.65), (15.2, 0.22, 1.24), bevel=0.08, bone_idx=b_gun)
        m.add_beveled_box(hull, (12.6, -1.46, 1.65), (15.2, 0.22, 1.24), bevel=0.08, bone_idx=b_gun)

    # Hinged steel switch latch on left upper flank (skinned to j_switch)
    m.add_beveled_box(brass, (6.24, 1.54, 1.52), (1.12, 0.30, 0.62), bevel=0.06, bone_idx=b_switch)

    # 3 steel-caged upright Dewar flasks on left flank (j_bulb_1/2/3, raised slightly into 1P hero silhouette!)
    s_flask = 5 if is_world else 8
    bulb_xs = (7.89, 9.64, 11.39)
    for b_idx, bx in zip(b_bulbs, bulb_xs):
        # Armored steel flask body + bottom/top brass valve collars + recessed narrow vertical cyan sight-slit!
        m.add_tapered_prism(dark, (bx, 2.78, 0.26), (bx, 2.78, 0.64), 0.72, 0.72, sides=s_flask, bone_idx=b_idx)
        m.add_tapered_prism(dark, (bx, 2.78, 0.62), (bx, 2.78, 2.74), 0.62, 0.62, sides=s_flask, bone_idx=b_idx, cap_start=False, cap_end=False)
        # Narrow recessed cyan slit framed by dark steel side cage ribs (angled toward 1P eye!)
        m.add_box(glow, (bx, 3.34, 1.68), (0.24, 0.12, 1.68), bone_idx=b_idx)
        if not is_world:
            m.add_box(dark, (bx - 0.19, 3.36, 1.68), (0.10, 0.14, 1.82), bone_idx=b_idx)
            m.add_box(dark, (bx + 0.19, 3.36, 1.68), (0.10, 0.14, 1.82), bone_idx=b_idx)
            m.add_tapered_prism(hull, (bx, 2.78, 1.62), (bx, 2.78, 1.76), 0.68, 0.68, sides=s_flask, bone_idx=b_idx)
        # Stepped steel shoulder + prominent knurled top brass valve cap
        m.add_tapered_prism(dark, (bx, 2.78, 2.70), (bx, 2.78, 3.10), 0.70, 0.48, sides=s_flask, bone_idx=b_idx)
        m.add_tapered_prism(brass, (bx, 2.78, 3.08), (bx, 2.78, 3.40), 0.42, 0.40, sides=s_flask, bone_idx=b_idx)
    m.add_tapered_prism(dark, (6.7, 2.26, 0.42), (12.6, 2.26, 0.42), 0.44, 0.44, sides=s_flask, bone_idx=b_gun)
    m.add_tapered_prism(hull, (6.8, 2.26, 2.94), (12.5, 2.26, 2.94), 0.36, 0.36, sides=s_flask, bone_idx=b_gun)

    # Bold right-flank dark-steel condenser housing + narrow cold indicator slit (x=10..21, y=-2.8, ~11u x 3.2u)
    m.add_tapered_prism(dark, (10.0, -2.75, 1.25), (21.0, -2.75, 1.25), 1.44, 1.40, sides=s_cyl, bone_idx=b_gun)
    for cx in ((13.0, 18.0) if is_world else (11.8, 15.5, 19.2)):
        m.add_tapered_prism(hull, (cx - 0.26, -2.75, 1.25), (cx + 0.26, -2.75, 1.25), 1.56, 1.56, sides=s_cyl, bone_idx=b_gun)
    m.add_box(glow, (15.5, -4.16, 1.25), (6.4, 0.14, 0.28), bone_idx=b_gun)
    m.add_tapered_prism(brass, (20.8, -2.75, 1.25), (23.2, -1.25, 1.72), 0.38, 0.32, sides=s_flask, bone_idx=b_gun, cap_start=False, cap_end=False)

    # Animated cryo-vent bolt shroud (skinned to j_bolt)
    m.add_tapered_prism(dark, (15.8, 1.22, 1.55), (19.4, 1.22, 1.55), 0.50, 0.42, sides=s_flask, bone_idx=b_bolt)

    # Heavy 1945 barrel + 5 stepped circular dark-steel radiator cooling fins (matching Sheet 03!)
    m.add_tapered_prism(dark, (22.0, 0.0, 1.82), (35.8, 0.0, 2.04), 1.06, 0.94, sides=s_cyl, bone_idx=b_gun, cap_start=False, cap_end=False)
    for fi, fx in enumerate((23.2, 25.5, 27.8, 30.1, 32.4)):
        r_fin = 2.04 - fi * 0.08
        m.add_tapered_prism(dark, (fx - 0.38, 0.0, 1.88 + fi * 0.02), (fx + 0.38, 0.0, 1.90 + fi * 0.02), r_fin, r_fin, sides=s_cyl, bone_idx=b_gun)
    # Compact flared Dewar frost-ring bell (OD <= 4.6u -> r <= 2.28u, cleanly beneath Z=5.10 ADS sightline, dark interior!)
    m.add_tapered_prism(dark, (34.4, 0.0, 2.04), (36.4, 0.0, 2.08), 1.26, 1.80, sides=s_cyl, bone_idx=b_gun, cap_end=False)
    m.add_tapered_prism(hull, (36.2, 0.0, 2.08), (40.3, 0.0, 2.16), 1.80, 2.26, sides=s_cyl, bone_idx=b_gun, cap_start=False)
    # Rolled steel muzzle rim + recessed dark interior collar (NO blinding solid cyan plug!)
    m.add_tapered_prism(dark, (40.0, 0.0, 2.15), (40.7, 0.0, 2.16), 2.28, 2.12, sides=s_cyl, bone_idx=b_gun)
    m.add_tapered_prism(dark, (38.8, 0.0, 2.14), (40.72, 0.0, 2.16), 1.48, 1.56, sides=s_cyl, bone_idx=b_gun, cap_start=False)

    # Open circular forged iron ring sight at (3.8, 0.0, 5.10) — keeps center ADS aiming point 100% clear!
    ring_c = (3.8, 0.0, 5.10)
    ring_segs = 8 if is_world else 12
    ring_r = 0.86
    m.add_box(dark, (3.8, -0.66, 3.88), (0.42, 0.20, 1.18), bone_idx=b_gun)
    m.add_box(dark, (3.8, +0.66, 3.88), (0.42, 0.20, 1.18), bone_idx=b_gun)
    m.add_beveled_box(hull, (3.8, 0.0, 3.38), (0.84, 1.66, 0.28), bevel=0.08, bone_idx=b_gun)
    for s in range(ring_segs):
        a0 = math.radians(360.0 * s / ring_segs)
        a1 = math.radians(360.0 * (s + 1) / ring_segs)
        p0 = (ring_c[0], ring_c[1] + math.cos(a0) * ring_r, ring_c[2] + math.sin(a0) * ring_r)
        p1 = (ring_c[0], ring_c[1] + math.cos(a1) * ring_r, ring_c[2] + math.sin(a1) * ring_r)
        m.add_tapered_prism(dark, p0, p1, 0.095, 0.095, sides=5, bone_idx=b_gun, cap_start=False, cap_end=False)
    if not is_world:
        # Subtle machined steel outer alignment posts (no oversized neon cyan bars!)
        m.add_box(dark, (3.8, -0.68, 5.10), (0.14, 0.26, 0.07), bone_idx=b_gun)
        m.add_box(dark, (3.8, +0.68, 5.10), (0.14, 0.26, 0.07), bone_idx=b_gun)

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
    s_cyl = 6 if is_world else 10

    # Contoured straight-grain oiled dark walnut rifle stock (steel buttpad, raised comb, slim grip wrist, forend)
    m.add_tapered_prism(metal, (-8.0, 0.0, -0.35), (-7.2, 0.0, -0.18), 1.12, 1.08, sides=s_cyl, bone_idx=b_gun, scale_y=0.64, scale_z=1.32)
    m.add_tapered_prism(wood, (-7.3, 0.0, -0.18), (-1.4, 0.0, 0.92), 1.08, 1.18, sides=s_cyl, bone_idx=b_gun, scale_y=0.68, scale_z=1.24)
    m.add_tapered_prism(wood, (-1.6, 0.0, 0.92), (1.8, 0.0, 1.16), 0.96, 1.28, sides=s_cyl, bone_idx=b_gun, scale_y=0.78, scale_z=0.92)
    m.add_tapered_prism(wood, (1.5, 0.0, 1.14), (17.2, 0.0, 1.32), 1.26, 1.02, sides=s_cyl, bone_idx=b_gun, scale_y=0.82, scale_z=0.84)
    # Pistol-grip wrist + decorative steel trigger guard loop
    m.add_tapered_prism(wood, (-1.2, 0.0, -2.65), (-0.1, 0.0, 0.55), 0.64, 0.80, sides=s_cyl, bone_idx=b_gun)
    m.add_box(metal, (1.1, 0.0, -1.05), (2.7, 0.24, 0.22), bone_idx=b_gun)
    m.add_box(metal, (2.3, 0.0, -0.45), (0.24, 0.24, 1.20), bone_idx=b_gun)
    m.add_box(metal, (0.65, 0.0, -0.62), (0.22, 0.14, 0.72), bone_idx=b_gun, rot_xyz=(0.0, -18.0, 0.0))

    # Chamfered stamped blued-steel receiver & tri-channel bolt flight rail
    m.add_beveled_box(metal, (4.2, 0.0, 1.98), (6.4, 2.8, 1.12), bevel=0.22, bone_idx=b_gun)
    m.add_beveled_box(metal, (14.0, 0.0, 2.02), (15.8, 4.4, 0.86), bevel=0.18, bone_idx=b_gun)
    if not is_world:
        for ry in (-2.00, -0.66, +0.66, +2.00):
            m.add_box(metal, (13.8, ry, 2.50), (15.6, 0.18, 0.24), bone_idx=b_gun)

    # Right-side steel cocking sled & knurled charging knob (skinned to j_bolt!)
    m.add_beveled_box(metal, (7.66, -2.18, 1.90), (4.6, 0.36, 0.58), bevel=0.06, bone_idx=b_bolt)
    m.add_tapered_prism(brass, (7.66, -2.35, 1.90), (7.66, -3.15, 1.90), 0.24, 0.28, sides=6, bone_idx=b_bolt)

    # Centerline flight rail (1 active chambered bolt, matching 11.4u projectile profile) + distinct LEFT-SIDE removable 3-bolt cassette (j_clip!)
    # Flight rail active bolt (x=10.2..21.8 -> ~11.6u matching bz_crossbow_bolt!)
    s_bolt = 4 if is_world else 6
    m.add_tapered_prism(metal, (10.5, 0.0, 2.66), (18.4, 0.0, 2.66), 0.16, 0.16, sides=s_bolt, bone_idx=b_gun)
    m.add_tapered_prism(brass, (18.1, 0.0, 2.66), (18.7, 0.0, 2.66), 0.24, 0.26, sides=s_bolt, bone_idx=b_gun)
    m.add_tapered_prism(glow, (18.65, 0.0, 2.66), (19.55, 0.0, 2.66), 0.28, 0.28, sides=s_bolt, bone_idx=b_gun)
    m.add_tapered_prism(metal, (19.50, 0.0, 2.66), (21.8, 0.0, 2.66), 0.40, 0.04, sides=4, bone_idx=b_gun, angle_offset_deg=45.0)
    m.add_tapered_prism(glow, (10.15, 0.0, 2.66), (10.65, 0.0, 2.66), 0.22, 0.18, sides=s_bolt, bone_idx=b_gun)
    for fdeg in (0.0, 120.0, 240.0):
        rad = math.radians(fdeg)
        cy, cz_v = math.cos(rad), math.sin(rad)
        m.add_quad(
            metal,
            (10.6, cy * 0.14, 2.66 + cz_v * 0.14),
            (12.2, cy * 0.14, 2.66 + cz_v * 0.14),
            (11.5, cy * 0.48, 2.66 + cz_v * 0.48),
            (10.5, cy * 0.44, 2.66 + cz_v * 0.44),
            bone_idx=b_gun,
            double_sided=True,
        )

    # Left-side open removable 3-bolt magazine cassette (skinned to j_clip! Offset left at y=+1.65..+3.15!)
    # Uses matching ~11.2u projectile profile (shaft + brass collar + #ffb020 charge + broadhead + 3 radial vanes + nock in VM & WM! S9)
    m.add_beveled_box(metal, (11.8, +2.35, 2.38), (5.2, 1.55, 0.30), bevel=0.06, bone_idx=b_clip)
    m.add_beveled_box(metal, (11.8, +3.12, 2.86), (5.4, 0.26, 1.05), bevel=0.06, bone_idx=b_clip)
    m.add_box(brass, (11.8, +2.35, 3.05), (0.90, 1.60, 0.16), bone_idx=b_clip)
    for cz in (2.68, 3.08, 3.44):
        by = 2.42
        m.add_tapered_prism(metal, (8.6, by, cz), (16.1, by, cz), 0.14, 0.14, sides=s_bolt, bone_idx=b_clip)
        m.add_tapered_prism(brass, (15.7, by, cz), (16.3, by, cz), 0.20, 0.22, sides=s_bolt, bone_idx=b_clip)
        m.add_tapered_prism(glow, (16.25, by, cz), (17.15, by, cz), 0.24, 0.24, sides=s_bolt, bone_idx=b_clip)
        m.add_tapered_prism(metal, (17.10, by, cz), (19.3, by, cz), 0.34, 0.04, sides=4, bone_idx=b_clip, angle_offset_deg=45.0)
        m.add_tapered_prism(glow, (8.10, by, cz), (8.65, by, cz), 0.20, 0.16, sides=s_bolt, bone_idx=b_clip)
        # 3 matching radial stamped steel fletching vanes (0/120/240 deg) matching bz_crossbow_bolt in both VM & WM (S9!)
        for fdeg in (0.0, 120.0, 240.0):
            rad = math.radians(fdeg)
            cy, cz_v = math.cos(rad), math.sin(rad)
            m.add_quad(
                metal,
                (8.6, by + cy * 0.12, cz + cz_v * 0.12),
                (10.1, by + cy * 0.12, cz + cz_v * 0.12),
                (9.4, by + cy * 0.42, cz + cz_v * 0.42),
                (8.5, by + cy * 0.38, cz + cz_v * 0.38),
                bone_idx=b_clip,
                double_sided=True,
            )

    # Heavy riveted forward steel riser + 2 bolted brass U-bolt clamps
    m.add_beveled_box(metal, (20.8, 0.0, 2.08), (3.1, 5.8, 1.88), bevel=0.22, bone_idx=b_gun)
    for side in (-1.0, +1.0):
        m.add_beveled_box(brass, (20.8, side * 2.95, 2.08), (1.26, 0.82, 1.96), bevel=0.10, bone_idx=b_gun)

    # 3 visibly stepped laminated truck leaf-spring steel prods (+/- 11.8u wide, ZERO pulley cams!)
    leaf_spans = (
        ((1.00, 0.00, 0.36), (0.68, +0.44, 0.28))
        if is_world
        else ((1.00, 0.00, 0.36), (0.68, +0.44, 0.28), (0.44, -0.44, 0.24))
    )
    for side in (-1.0, +1.0):
        base_pts = [
            (20.6, side * 2.5, 2.15),
            (20.0, side * 5.8, 2.05),
            (18.0, side * 9.0, 1.92),
            (14.8, side * 11.8, 1.76),
        ]
        for span_frac, dz, thick in leaf_spans:
            segs = 3 if span_frac >= 0.99 else (2 if span_frac >= 0.65 else 1)
            for i in range(segs):
                p0 = (base_pts[i][0], base_pts[i][1], base_pts[i][2] + dz)
                p1 = (base_pts[i + 1][0], base_pts[i + 1][1], base_pts[i + 1][2] + dz)
                m.add_tapered_prism(metal, p0, p1, thick, thick * 0.82, sides=4, bone_idx=b_gun, scale_y=0.55, scale_z=1.40)
        # Dual weathered brass leaf-spring binding bands
        m.add_beveled_box(brass, (19.6, side * 6.0, 2.05), (0.74, 0.64, 1.44), bevel=0.08, bone_idx=b_gun)
        m.add_beveled_box(brass, (18.2, side * 8.8, 1.92), (0.58, 0.52, 1.06), bevel=0.06, bone_idx=b_gun)
        tip = base_pts[-1]
        hook_end = (tip[0] - 0.68, tip[1] + side * 0.28, tip[2])
        m.add_tapered_prism(metal, tip, hook_end, 0.24, 0.16, sides=6, bone_idx=b_gun)
        m.add_tapered_prism(metal, hook_end, (10.2, 0.0, 2.66), 0.075, 0.075, sides=4, bone_idx=b_gun, cap_start=False, cap_end=False)

    # Open forged steel foot-stirrup loop (canted cleanly downward below reticle!)
    stirrup = [
        (22.0, -2.3, 1.55),
        (25.4, -2.0, 0.82),
        (26.5, 0.0, 0.58),
        (25.4, +2.0, 0.82),
        (22.0, +2.3, 1.55),
    ]
    for i in range(len(stirrup) - 1):
        m.add_tapered_prism(metal, stirrup[i], stirrup[i + 1], 0.21, 0.21, sides=6, bone_idx=b_gun)

    # Bold matte-black 1945 ZFG42 optic scope w/ tapered objective/ocular bells & brass turrets (Z <= 3.55 -> 0 ADS occlusion!)
    m.add_beveled_box(metal, (0.9, -0.18, 2.70), (0.76, 0.84, 0.56), bevel=0.06, bone_idx=b_gun)
    m.add_beveled_box(metal, (5.2, -0.18, 2.70), (0.76, 0.84, 0.56), bevel=0.06, bone_idx=b_gun)
    m.add_tapered_prism(metal, (-1.4, -0.18, 3.04), (0.3, -0.18, 3.04), 0.52, 0.40, sides=s_cyl, bone_idx=b_gun)
    m.add_tapered_prism(metal, (0.2, -0.18, 3.04), (6.2, -0.18, 3.04), 0.40, 0.40, sides=s_cyl, bone_idx=b_gun)
    m.add_tapered_prism(metal, (6.1, -0.18, 3.04), (8.6, -0.18, 3.04), 0.40, 0.56, sides=s_cyl, bone_idx=b_gun)
    if not is_world:
        m.add_tapered_prism(brass, (3.1, +0.26, 3.04), (3.1, +0.68, 3.04), 0.19, 0.19, sides=6, bone_idx=b_gun)
        m.add_tapered_prism(brass, (3.1, -0.58, 3.04), (3.1, -0.98, 3.04), 0.19, 0.19, sides=6, bone_idx=b_gun)
        # Matte-black forged steel ocular ring (brass stays strictly on compact turrets only! F25)
        m.add_tapered_prism(metal, (-1.46, -0.18, 3.04), (-1.22, -0.18, 3.04), 0.54, 0.52, sides=s_cyl, bone_idx=b_gun)

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
    """WWII propeller tri-blade boomerang (<=4.5u 1P / 8.62u WM) w/ leather stirrup grip, lightening holes & 1 wrapped ID blade."""
    bones = world_weapon_bones((4.5, 0.0, 2.05)) if is_world else BONES_COLT45
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0

    steel = "mtl_bz_blade_steel"
    leather = "mtl_bz_blade_leather"
    brass = "mtl_bz_blade_brass"
    glow = "mtl_bz_blade_glow"  # Industrial crimson (#e81e50) narrow hub ring + 3 tiny tip tracer pellets!

    scale = 2.45 if is_world else 1.0
    hub: Vec3 = (0.35 * scale, 0.0, 2.05 * scale)
    s_hub = 10 if is_world else 14
    blade_steps = 6 if is_world else 8

    # Compact stitched-leather stirrup throwing grip seated in palm + rear-offset collar meeting BACK of hub!
    # Terminating collar behind the hub keeps the front crimson annulus 100% continuous & unbroken (A11/S10/F12)!
    hub_axis = v_norm((-0.72, 0.42, 0.55))
    hub_rear = v_sub(hub, v_scale(hub_axis, 0.24 * scale))
    m.add_tapered_prism(leather, (0.0, 0.0, -2.35), (0.0, 0.0, 0.82), 0.35, 0.34, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(brass, (0.0, 0.0, -2.68), (0.0, 0.0, -2.30), 0.44, 0.37, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(brass, (0.0, 0.0, 0.78), hub_rear, 0.36, 0.44 * scale, sides=8, bone_idx=b_gun)

    # Machined stepped bronze/steel propeller gyro-hub + unbroken 360-deg crimson ring + bolted steel center boss!
    m.add_tapered_prism(
        brass,
        v_sub(hub, v_scale(hub_axis, 0.24 * scale)),
        v_add(hub, v_scale(hub_axis, 0.24 * scale)),
        0.84 * scale,
        0.84 * scale,
        sides=s_hub,
        bone_idx=b_gun,
    )
    m.add_tapered_prism(
        glow,
        v_sub(hub, v_scale(hub_axis, 0.28 * scale)),
        v_add(hub, v_scale(hub_axis, 0.28 * scale)),
        0.58 * scale,
        0.58 * scale,
        sides=s_hub,
        bone_idx=b_gun,
    )
    # Bolted steel center hub cap inside the crimson ring (creates crisp continuous crimson annulus!)
    m.add_tapered_prism(
        steel,
        v_sub(hub, v_scale(hub_axis, 0.33 * scale)),
        v_add(hub, v_scale(hub_axis, 0.33 * scale)),
        0.40 * scale,
        0.38 * scale,
        sides=s_hub,
        bone_idx=b_gun,
    )

    # 3 taut airfoil-tapered brushed-steel WWII propeller blades + 3 recessed lightening holes + tiny crimson tip pellet
    # Arm 0 carries the EXACT ONE asymmetric leather-wrapped + brass ID spine band!
    u_axis = v_norm((0.62, 0.52, 0.58))
    v_axis = v_norm(v_cross(hub_axis, u_axis))
    hole_sides = 5 if is_world else 6
    for arm in range(3):
        base_deg = arm * 120.0 + 24.0
        pts: list[Vec3] = []
        ws: list[float] = []
        ts: list[float] = []
        for k in range(blade_steps):
            u = k / (blade_steps - 1)
            r = (0.62 + u * 2.84) * scale
            ang = math.radians(base_deg + u * 16.0)
            local = v_add(v_scale(u_axis, math.cos(ang) * r), v_scale(v_axis, math.sin(ang) * r))
            pts.append(v_add(hub, local))
            # Authentic taut WWII aircraft propeller airfoil taper
            ws.append((0.66 + 0.30 * math.sin(u * math.pi) - 0.28 * u) * scale)
            ts.append((0.18 * (1.0 - 0.54 * u)) * scale)
        m.add_swept_blade(steel, glow, pts, ws, ts, normal_axis=hub_axis, bone_idx=b_gun, glow_outer=False)

        # 3 dark recessed lightening-hole bosses along each blade on BOTH 1P VM and 3P WM (A11/S10/G7!)
        hole_indices = ((2, 0.14), (3, 0.12), (4, 0.095)) if is_world else ((3, 0.14), (4, 0.12), (5, 0.095))
        for hole_idx, hole_r in hole_indices:
            hp = pts[hole_idx]
            m.add_tapered_prism(
                leather,
                v_sub(hp, v_scale(hub_axis, 0.11 * scale)),
                v_add(hp, v_scale(hub_axis, 0.11 * scale)),
                hole_r * scale,
                hole_r * scale,
                sides=hole_sides,
                bone_idx=b_gun,
            )

        # Single tiny crisp round crimson (#e81e50) tracer pellet recessed near each blade tip
        tip_pt = pts[-2]
        m.add_tapered_prism(
            glow,
            v_sub(tip_pt, v_scale(hub_axis, 0.09 * scale)),
            v_add(tip_pt, v_scale(hub_axis, 0.09 * scale)),
            0.095 * scale,
            0.095 * scale,
            sides=6,
            bone_idx=b_gun,
        )
        # Bold asymmetric leather-wrapped + brass ID band on Arm 0 ONLY!
        if arm == 0:
            m.add_tapered_prism(leather, pts[1], pts[3], 0.44 * scale, 0.40 * scale, sides=8, bone_idx=b_gun)
            m.add_tapered_prism(brass, pts[3], pts[4], 0.36 * scale, 0.32 * scale, sides=8, bone_idx=b_gun)

    return m


def build_blade_boomerang_air() -> MeshBuilder:
    """Airborne YZ-plane WWII propeller tri-blade (10.15u radius, <=750 verts, matching Arm 0 ID wrap & lightening holes)."""
    m = MeshBuilder("bz_boomerang_blade_air", BONES_RIGID, model_type="rigid")
    steel = "mtl_bz_blade_steel"
    leather = "mtl_bz_blade_leather"
    brass = "mtl_bz_blade_brass"
    glow = "mtl_bz_blade_glow"

    # Spin axis along +X for wobble-free RotateRoll (stepped bronze hub + continuous crimson ring + steel center boss)
    m.add_tapered_prism(brass, (-0.58, 0.0, 0.0), (+0.58, 0.0, 0.0), 1.98, 1.98, sides=8, bone_idx=0)
    m.add_tapered_prism(glow, (-0.65, 0.0, 0.0), (+0.65, 0.0, 0.0), 1.38, 1.38, sides=8, bone_idx=0)
    m.add_tapered_prism(steel, (-0.72, 0.0, 0.0), (+0.72, 0.0, 0.0), 0.94, 0.94, sides=8, bone_idx=0)

    for arm in range(3):
        base_deg = arm * 120.0 + 24.0

        def blade_pt(u_val: float) -> Vec3:
            r_val = 1.48 + u_val * 8.67
            rad_val = math.radians(base_deg + u_val * 16.0)
            return (0.0, math.cos(rad_val) * r_val, math.sin(rad_val) * r_val)

        pts: list[Vec3] = []
        ws: list[float] = []
        ts: list[float] = []
        for k in range(5):
            u = k / 4.0
            pts.append(blade_pt(u))
            ws.append(1.92 + 0.66 * math.sin(u * math.pi) - 0.72 * u)
            ts.append(0.52 * (1.0 - 0.54 * u))
        m.add_swept_blade(steel, glow, pts, ws, ts, normal_axis=(1.0, 0.0, 0.0), bone_idx=0, glow_outer=False)

        # 3 crisp circular (6-sided) dark recessed lightening holes per blade at r=5.12, 6.60, 7.98 —
        # 100% clear of Arm-0 root wrap (r<=3.91) and outer crimson tip pellet (r=9.37), staying <=500 tris (A11/S10/S15!).
        for hole_u, hole_r in ((0.42, 0.40), (0.59, 0.34), (0.75, 0.28)):
            hp = blade_pt(hole_u)
            for face_x in (-0.28, +0.28):
                nx = 1.0 if face_x > 0 else -1.0
                ring_ids: list[int] = []
                for s_idx in range(6):
                    ang = math.radians(s_idx * 60.0)
                    vp = (face_x, hp[1] + math.cos(ang) * hole_r, hp[2] + math.sin(ang) * hole_r)
                    ring_ids.append(m.add_vert(vp, 0))
                n_vec = (nx, 0.0, 0.0)
                for s_idx in range(1, 5):
                    if face_x > 0:
                        m.add_tri(leather, ring_ids[0], ring_ids[s_idx], ring_ids[s_idx + 1], (0.5, 0.5), (0.6, 0.5), (0.5, 0.6), n_vec, n_vec, n_vec)
                    else:
                        m.add_tri(leather, ring_ids[0], ring_ids[s_idx + 1], ring_ids[s_idx], (0.5, 0.5), (0.5, 0.6), (0.6, 0.5), n_vec, n_vec, n_vec)

        # Single crisp crimson tip tracer pellet cleanly outboard of the 3rd lightening hole (r=9.37)
        tp = blade_pt(0.91)
        m.add_tapered_prism(glow, (-0.30, tp[1], tp[2]), (+0.30, tp[1], tp[2]), 0.28, 0.28, sides=5, bone_idx=0)
        # Matching bold Arm-0 asymmetric leather-wrapped + brass ID band confined cleanly to inner root (r=2.00..3.91)
        if arm == 0:
            m.add_tapered_prism(leather, blade_pt(0.06), blade_pt(0.20), 0.92, 0.86, sides=6, bone_idx=0)
            m.add_tapered_prism(brass, blade_pt(0.20), blade_pt(0.28), 0.84, 0.78, sides=6, bone_idx=0)

    return m


# ---------------------------------------------------------------------------
# 4. ACID SPRAYER (1945 Flammenwerfer-41 Chemical Wand — Low Olivgruen Tank + Plain Bell)
# ---------------------------------------------------------------------------


def build_acid_sprayer(name: str, is_world: bool = False) -> MeshBuilder:
    bones = world_weapon_bones((17.71, 0.0, -0.29)) if is_world else BONES_FLAMETHROWER
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0

    metal = "mtl_bz_acid_metal"    # Panzergrau / parkerized steel (#363c42)
    enamel = "mtl_bz_acid_hazard"  # Olivgruen / Feldgrau enamel (#424b3a) w/ Gruenkreuz patina
    glow = "mtl_bz_acid_glow"      # Opaque unlit bright lime-green (#68f030) recessed sight slit ONLY!
    brass = "mtl_bz_xbow_brass"    # Weathered brass rear-dome dial bezel & valve trim (<=10%, 4-slot cap)
    s_cyl = 8 if is_world else 12

    # Axis-aligned rear wand manifold cap at x=-5.60 -> exact 23.31u length to tag_flash x=17.71 (O24/A8/S8!)
    m.add_tapered_prism(metal, (-5.60, -0.88, -1.05), (-4.60, -0.88, -1.05), 1.04, 1.04, sides=s_cyl, bone_idx=b_gun)
    m.add_tapered_prism(metal, (-4.70, -0.88, -1.05), (-0.80, -0.10, -0.26), 1.00, 1.18, sides=s_cyl, bone_idx=b_gun)
    m.add_beveled_box(metal, (-3.4, -1.85, -2.65), (1.65, 1.10, 3.3), bevel=0.20, bone_idx=b_gun, rot_xyz=(0.0, 24.0, 18.0))
    m.add_tapered_prism(metal, (-2.8, -1.50, -1.75), (-0.4, -0.35, -0.45), 0.44, 0.52, sides=6, bone_idx=b_gun)

    # Clean Panzergrau Flammenwerfer-41 main wand tube + ribbed cooling rings terminating on tag_flash (17.71, 0, -0.29)!
    m.add_tapered_prism(metal, (-1.0, 0.0, -0.22), (15.0, 0.0, -0.29), 1.14, 0.76, sides=s_cyl, bone_idx=b_gun)
    # 7 machined barrel cooling/heat-shield ribs (signature Flammenwerfer-41 silhouette from Sheet 02!)
    rib_xs = (6.4, 8.2, 10.0, 11.8) if is_world else (5.8, 7.0, 8.2, 9.4, 10.6, 11.8, 13.0)
    for rx in rib_xs:
        rz = -0.22 + (rx + 1.0) / 16.0 * (-0.07)
        m.add_tapered_prism(metal, (rx - 0.18, 0.0, rz), (rx + 0.18, 0.0, rz), 1.16, 1.16, sides=s_cyl, bone_idx=b_gun)
    # Forward left-hand grip sleeve + heavy riveted mounting brackets into low outboard reagent tank
    m.add_tapered_prism(metal, (4.4, 0.0, -0.92), (10.4, 0.0, -0.88), 0.82, 0.78, sides=8, bone_idx=b_gun)
    for bx in (1.7, 10.9):
        m.add_beveled_box(metal, (bx, 1.35, -0.46), (0.98, 1.85, 0.52), bevel=0.10, bone_idx=b_gun)

    # Dominant Mass 1: Low squat armored Olivgruen outboard-left reagent tank (y=+2.45, z=-0.62, top Z=+0.56 <= 2.0)
    # Positioned LOW and outboard per §3.1 so the upper wand tube & flared 2.72u bell project cleanly into 1P view (O14/A8/S8!)
    m.add_tapered_prism(enamel, (0.8, 2.45, -0.62), (11.8, 2.45, -0.62), 1.18, 1.18, sides=s_cyl, bone_idx=b_gun)
    # Domed brushed-steel front & rear tank end-caps + prominent 12-sided brass-bezel analog pressure dial facing player (-X)!
    s_dial = 8 if is_world else 12
    m.add_tapered_prism(metal, (-0.32, 2.45, -0.62), (0.85, 2.45, -0.62), 0.78, 1.18, sides=s_cyl, bone_idx=b_gun)
    m.add_tapered_prism(brass, (-0.84, 2.45, -0.62), (-0.24, 2.45, -0.62), 0.68, 0.74, sides=s_dial, bone_idx=b_gun)
    m.add_tapered_prism(metal, (-0.90, 2.45, -0.62), (-0.80, 2.45, -0.62), 0.50, 0.50, sides=s_dial, bone_idx=b_gun, cap_end=False)
    if not is_world:
        # Crisp 3D mechanical gauge needle & center hub inside brass bezel
        m.add_box(brass, (-0.94, 2.53, -0.52), (0.06, 0.09, 0.40), bone_idx=b_gun, rot_xyz=(-30.0, 0.0, 0.0))
        m.add_tapered_prism(brass, (-0.98, 2.45, -0.62), (-0.88, 2.45, -0.62), 0.14, 0.14, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(metal, (11.75, 2.45, -0.62), (12.85, 2.45, -0.62), 1.18, 0.56, sides=s_cyl, bone_idx=b_gun)
    # Two riveted steel mounting straps set cleanly at tank ends (x=1.65 & x=10.95) so central stencil bay is 100% unobstructed (A8/G9!)
    for ring_x in (1.65, 10.95):
        m.add_tapered_prism(metal, (ring_x - 0.26, 2.45, -0.62), (ring_x + 0.26, 2.45, -0.62), 1.25, 1.25, sides=s_cyl, bone_idx=b_gun)
        m.add_box(brass, (ring_x, 2.45, +0.62), (0.38, 0.42, 0.12), bone_idx=b_gun)
    # Single recessed narrow lime-green sight slit angled inboard (+38 deg -> faces 1P camera cleanly, top Z <= 0.72!)
    m.add_beveled_box(metal, (6.3, 1.88, +0.34), (6.0, 0.70, 0.16), bevel=0.04, bone_idx=b_gun, rot_xyz=(38.0, 0.0, 0.0))
    m.add_box(glow, (6.3, 1.74, +0.44), (5.5, 0.30, 0.12), bone_idx=b_gun, rot_xyz=(38.0, 0.0, 0.0))
    # Armored chemical feed tube from tank front dome into nozzle manifold
    m.add_tapered_prism(brass, (12.7, 2.45, -0.62), (13.3, 2.45, -0.62), 0.36, 0.36, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(metal, (13.0, 2.45, -0.62), (14.6, 0.52, -0.29), 0.30, 0.26, sides=8, bone_idx=b_gun)

    # Dominant Mass 2: Bold HOLLOW open-bore rolled cast-iron flared diffuser bell anchored on tag_flash (17.71, 0, -0.29), OD 2.72u (O24/S8!)
    m.add_tapered_prism(brass, (14.1, 0.0, -0.29), (14.95, 0.0, -0.29), 0.92, 0.98, sides=s_cyl, bone_idx=b_gun)
    m.add_tapered_prism(metal, (14.90, 0.0, -0.29), (16.30, 0.0, -0.29), 0.84, 1.08, sides=s_cyl, bone_idx=b_gun, cap_start=False, cap_end=False)
    m.add_tapered_prism(metal, (16.25, 0.0, -0.29), (17.60, 0.0, -0.29), 1.08, 1.24, sides=s_cyl, bone_idx=b_gun, cap_start=False, cap_end=False)
    # Hollow rolled steel outer lip ring centered on tag_flash (x=17.57 + 0.14 = 17.71u, r=1.22, tube_r=0.14 -> OD = 2.72u!)
    _add_gyro_ring(
        m,
        metal,
        (17.57, 0.0, -0.29),
        1.22,
        0.14,
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        segs=s_cyl,
        bone_idx=b_gun,
    )
    # Inner recessed dark baffle throat behind the open lip (gives genuine hollow depth, NOT a solid flat plug!)
    m.add_tapered_prism(metal, (14.95, 0.0, -0.29), (15.45, 0.0, -0.29), 0.68, 0.68, sides=s_cyl, bone_idx=b_gun)

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
    radius_v: float | None = None,
) -> None:
    """Continuous watertight mitered circular or elliptical torus ring (ZERO open-ended segment seams!)."""
    ru = radius
    rv = radius if radius_v is None else radius_v
    normal_w = v_norm(v_cross(axis_u, axis_v))
    c_sides = 6
    rings: list[list[Vec3]] = []
    ring_ns: list[list[Vec3]] = []
    for s in range(segs):
        ang = math.radians(360.0 * s / segs)
        ca, sa = math.cos(ang), math.sin(ang)
        spine_pt = v_add(center, v_add(v_scale(axis_u, ca * ru), v_scale(axis_v, sa * rv)))
        # Outward radial direction in the ring plane perpendicular to the ellipse tangent
        tang = v_norm(v_add(v_scale(axis_u, -sa * ru), v_scale(axis_v, ca * rv)))
        rad_out = v_norm(v_cross(tang, normal_w))
        pts_s: list[Vec3] = []
        ns_s: list[Vec3] = []
        for k in range(c_sides):
            phi = math.radians(360.0 * k / c_sides)
            cp, sp = math.cos(phi), math.sin(phi)
            n_dir = v_norm(v_add(v_scale(rad_out, cp), v_scale(normal_w, sp)))
            pts_s.append(v_add(spine_pt, v_scale(n_dir, tube_r)))
            ns_s.append(n_dir)
        rings.append(pts_s)
        ring_ns.append(ns_s)

    for s in range(segs):
        sn = (s + 1) % segs
        u0 = s / segs
        u1 = (s + 1) / segs
        for k in range(c_sides):
            kn = (k + 1) % c_sides
            v0 = k / c_sides
            v1 = (k + 1) / c_sides
            i0 = m.add_vert(rings[s][k], bone_idx)
            i1 = m.add_vert(rings[sn][k], bone_idx)
            i2 = m.add_vert(rings[sn][kn], bone_idx)
            i3 = m.add_vert(rings[s][kn], bone_idx)
            # Outward CCW winding
            m.add_tri(mat_name, i0, i1, i2, (u0, v0), (u1, v0), (u1, v1), ring_ns[s][k], ring_ns[sn][k], ring_ns[sn][kn])
            m.add_tri(mat_name, i0, i2, i3, (u0, v0), (u1, v1), (u0, v1), ring_ns[s][k], ring_ns[sn][kn], ring_ns[s][kn])


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
    """Held Portal Grenade: knurled Stielhandgranate handle + 4-prong chalice + 1 meridian hoop + equatorial clamp (ZERO top spire!)."""
    bones = world_weapon_bones((4.0, 0.0, 2.0)) if is_world else BONES_COLT45
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0

    ring = "mtl_bz_portal_ring"  # Blued steel / dark iron
    core = "mtl_bz_portal_core"  # Dark faceted obsidian-violet Element-115 shard (#8e22da veins)
    trim = "mtl_bz_portal_trim"  # Riveted weathered brass collar & prongs

    scale = 1.65 if is_world else 1.0
    center: Vec3 = (1.5 * scale, 0.0, 2.15 * scale)
    segs = 14 if is_world else 20

    # Knurled dark-iron Stielhandgranate stick handle w/ bottom pommel cap + cord-wrap ribs + riveted brass collar
    m.add_tapered_prism(ring, (-0.06 * scale, 0.0, -2.25 * scale), (0.02 * scale, 0.0, -1.92 * scale), 0.44 * scale, 0.40 * scale, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(ring, (0.0, 0.0, -1.95 * scale), (0.35 * scale, 0.0, 0.15 * scale), 0.36 * scale, 0.44 * scale, sides=10, bone_idx=b_gun)
    if not is_world:
        for rz in (-1.4, -0.95, -0.50, -0.05):
            u = (rz + 1.95) / 2.10
            rx = u * 0.35 * scale
            m.add_tapered_prism(trim, (rx, 0.0, (rz - 0.08) * scale), (rx, 0.0, (rz + 0.08) * scale), 0.42 * scale, 0.42 * scale, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(trim, (0.32 * scale, 0.0, 0.10 * scale), (center[0] * 0.72, 0.0, center[2] - 1.30 * scale), 0.58 * scale, 0.80 * scale, sides=10, bone_idx=b_gun)

    # Visible 4-prong forged steel/brass chalice cradling the raw Element-115 shard
    chalice_base = (center[0] * 0.75, 0.0, center[2] - 1.25 * scale)
    for deg in (45.0, 135.0, 225.0, 315.0):
        rad = math.radians(deg)
        dx, dy = math.cos(rad), math.sin(rad)
        p0 = v_add(chalice_base, (dx * 0.58 * scale, dy * 0.58 * scale, 0.0))
        p1 = v_add(center, (dx * 1.48 * scale, dy * 1.48 * scale, -0.25 * scale))
        p2 = v_add(center, (dx * 1.56 * scale, dy * 1.56 * scale, +0.44 * scale))
        m.add_tapered_prism(trim, p0, p1, 0.15 * scale, 0.12 * scale, sides=6, bone_idx=b_gun)
        m.add_tapered_prism(ring, p1, p2, 0.12 * scale, 0.08 * scale, sides=6, bone_idx=b_gun)

    # Faceted dark-violet Element-115 crystal shard (core radius 1.38u held / 2.28u world)
    _add_octa_sphere_core(m, core, center, 1.38 * scale, bone_idx=b_gun, sides=8)

    # EXACTLY ONE thick rectangular-section blued-steel meridian hoop + ONE equatorial brass clamp ring (ZERO top pole spire!)
    _add_gyro_ring(m, ring, center, 2.04 * scale, 0.19 * scale, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), segs=segs, bone_idx=b_gun)
    _add_gyro_ring(m, trim, center, 1.74 * scale, 0.14 * scale, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), segs=segs, bone_idx=b_gun)
    return m


def build_portal_orb_air() -> MeshBuilder:
    """Deployed Portal Anchor (25u exact tip-to-tip height +-12.5u, full 360-deg equatorial + meridian hoop, <=900v)."""
    m = MeshBuilder("bz_portal_orb_air", BONES_RIGID, model_type="rigid")
    ring = "mtl_bz_portal_ring"
    core = "mtl_bz_portal_core"
    trim = "mtl_bz_portal_trim"

    center: Vec3 = (0.0, 0.0, 0.0)
    # Elongated faceted Element-115 crystal shard (matches Sheet 06 deployed hero!)
    z_bands = (-1.15, -0.70, -0.18, 0.28, 0.74, 1.15)
    r_bands = (0.08, 0.56, 0.88, 0.84, 0.52, 0.08)
    for i in range(len(z_bands) - 1):
        p0 = (0.0, 0.0, z_bands[i] * 5.6)
        p1 = (0.0, 0.0, z_bands[i + 1] * 5.6)
        m.add_tapered_prism(core, p0, p1, r_bands[i] * 5.6, r_bands[i + 1] * 5.6, sides=6, bone_idx=0, cap_start=(i == 0), cap_end=(i == len(z_bands) - 2))
    # 1 elongated vertical oval blued-steel meridian hoop + 1 full 360-deg brass equatorial clamp ring (mitered, ZERO gaps!)
    _add_gyro_ring(m, ring, center, 7.2, 0.78, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), segs=16, bone_idx=0, radius_v=9.5)
    _add_gyro_ring(m, trim, center, 7.6, 0.62, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), segs=16, bone_idx=0)
    # 4 riveted equatorial clamp lugs
    for deg in (0.0, 90.0, 180.0, 270.0):
        rad = math.radians(deg)
        p0 = (math.cos(rad) * 6.8, math.sin(rad) * 6.8, 0.0)
        p1 = (math.cos(rad) * 9.2, math.sin(rad) * 9.2, 0.0)
        m.add_tapered_prism(ring, p0, p1, 0.70, 0.42, sides=4, bone_idx=0)
    # Twin stepped pole emitter collars + sharp tapered spires spanning exact +/-12.5u (25.0u tip-to-tip!)
    m.add_tapered_prism(ring, (0.0, 0.0, 8.8), (0.0, 0.0, 10.1), 1.32, 0.94, sides=6, bone_idx=0)
    m.add_tapered_prism(trim, (0.0, 0.0, 10.0), (0.0, 0.0, 12.5), 0.76, 0.12, sides=6, bone_idx=0)
    m.add_tapered_prism(ring, (0.0, 0.0, -8.8), (0.0, 0.0, -10.1), 1.32, 0.94, sides=6, bone_idx=0)
    m.add_tapered_prism(trim, (0.0, 0.0, -10.0), (0.0, 0.0, -12.5), 0.76, 0.12, sides=6, bone_idx=0)
    return m


# ---------------------------------------------------------------------------
# 6. WAR CLUB (1945 Trench-Knife D-Guard + Domed Pommel + Octagonal 8-Lug Solenoid Head)
# ---------------------------------------------------------------------------


def build_war_club_held(name: str, is_world: bool) -> MeshBuilder:
    """Flared octagonal cast-iron War Club w/ bold D-guard knuckle bow, domed pommel & oversized 8+1 lug solenoid head."""
    bones = world_weapon_bones((12.0, 0.0, 2.5)) if is_world else BONES_COLT45
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0
    s = 1.85 if is_world else 1.0

    wood = "mtl_bz_club_wood"
    iron = "mtl_bz_club_iron"
    glow = "mtl_bz_club_glow"  # Deep forge red-orange (#ff4a12) wound copper solenoid coils
    leather = "mtl_bz_blade_leather"

    def pt(t: float) -> Vec3:
        return ((-1.2 + t * 11.4) * s, 0.0, (-2.4 + t * 10.6) * s)

    axis = v_norm(v_sub(pt(1.0), pt(0.0)))
    side_u = (0.0, 1.0, 0.0)
    side_v = v_norm(v_cross(axis, side_u))
    # Forward-left vector wrapping directly around the player's melee grip hand so fist sits INSIDE D-guard bow (G8!)
    bow_dir = v_norm(v_add(v_scale(side_v, -0.28), v_scale(side_u, +0.96)))

    # 1. Compact domed iron pommel + stepped ferrule below gripping fist (ZERO butt spike! G8!)
    m.add_tapered_prism(iron, pt(-0.44), pt(-0.36), 0.36 * s, 0.78 * s, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(iron, pt(-0.36), pt(-0.29), 0.78 * s, 0.62 * s, sides=10, bone_idx=b_gun)

    # 2. Stitched leather grip + bold forged blackened-steel WWI trench-knife D-guard knuckle bow fully enclosing the player's fist (G8!)
    m.add_tapered_prism(leather, pt(-0.30), pt(0.20), 0.56 * s, 0.60 * s, sides=10, bone_idx=b_gun)
    m.add_tapered_prism(iron, pt(0.18), pt(0.25), 0.84 * s, 0.80 * s, sides=8, bone_idx=b_gun)
    dguard_pts = [
        v_add(pt(-0.36), v_scale(bow_dir, 0.58 * s)),
        v_add(pt(-0.28), v_scale(bow_dir, 2.30 * s)),
        v_add(pt(-0.08), v_scale(bow_dir, 2.56 * s)),
        v_add(pt(0.12), v_scale(bow_dir, 2.26 * s)),
        v_add(pt(0.21), v_scale(bow_dir, 0.68 * s)),
    ]
    for i in range(len(dguard_pts) - 1):
        m.add_tapered_prism(iron, dguard_pts[i], dguard_pts[i + 1], 0.22 * s, 0.22 * s, sides=6, bone_idx=b_gun)
    # 3 forged trench-knuckle studs on outer bow
    for idx_stud in (1, 2, 3):
        sp0 = dguard_pts[idx_stud]
        sp1 = v_add(sp0, v_scale(bow_dir, 0.42 * s))
        m.add_tapered_prism(iron, sp0, sp1, 0.16 * s, 0.05 * s, sides=4, bone_idx=b_gun)

    # 3. Straight charred ash shaft flaring into heavy 1.3x oversized octagonal (sides=8) cast-iron striking head!
    m.add_tapered_prism(wood, pt(0.24), pt(0.64), 0.64 * s, 0.98 * s, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(iron, pt(0.62), pt(0.71), 1.18 * s, 1.58 * s, sides=8, bone_idx=b_gun)
    # Recessed inner copper kinetic solenoid coil cylinder + 4 slender forged-iron cage ribs opening 4 bold vertical coil windows!
    m.add_tapered_prism(glow, pt(0.70), pt(0.93), 1.34 * s, 1.54 * s, sides=12, bone_idx=b_gun)
    for k in range(4):
        ang = math.radians(k * 90.0 + 45.0)
        rad_dir = v_add(v_scale(side_u, math.cos(ang)), v_scale(side_v, math.sin(ang)))
        r_p0 = v_add(pt(0.69), v_scale(rad_dir, 1.46 * s))
        r_p1 = v_add(pt(0.94), v_scale(rad_dir, 1.66 * s))
        m.add_tapered_prism(iron, r_p0, r_p1, 0.34 * s, 0.38 * s, sides=4, bone_idx=b_gun)

    # 4. Heavy bolted upper cast-iron collar studded with 8 bold pyramidal iron lugs (1 per octagon face!) + 1 crown lug
    m.add_tapered_prism(iron, pt(0.92), pt(1.04), 1.76 * s, 1.82 * s, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(iron, pt(1.03), pt(1.13), 1.74 * s, 0.96 * s, sides=8, bone_idx=b_gun)
    m.add_tapered_prism(iron, pt(1.12), pt(1.26), 0.64 * s, 0.14 * s, sides=4, bone_idx=b_gun, angle_offset_deg=45.0)
    c_collar = pt(0.98)
    for k in range(8):
        ang = math.radians(k * 45.0)
        rad_dir = v_add(v_scale(side_u, math.cos(ang)), v_scale(side_v, math.sin(ang)))
        sp0 = v_add(c_collar, v_scale(rad_dir, 1.66 * s))
        sp1 = v_add(c_collar, v_scale(rad_dir, 2.58 * s))
        m.add_tapered_prism(iron, sp0, sp1, 0.42 * s, 0.09 * s, sides=4, bone_idx=b_gun, angle_offset_deg=45.0)
    return m


# ---------------------------------------------------------------------------
# 7. STATION KIOSKS (4 Distinct 1945 Group 935 Silhouettes — +X Front, z=-4..0 Skirt, <=72u H)
# ---------------------------------------------------------------------------


def build_station_kiosk(name: str, kind: str) -> MeshBuilder:
    """1945 Group 935 Station Kiosk (rigid tag_origin, +X front, z=-4..0 burial skirt, <=72u H, <=1,500 verts, <=4 mats)."""
    m = MeshBuilder(name, BONES_RIGID, model_type="rigid")
    frame = "mtl_bz_kiosk_frame"    # Bolted Panzergrau cast iron (#363c42)
    enamel = "mtl_bz_kiosk_enamel"  # Olivgruen Group 935 apothecary steel (#424b3a)
    iron = "mtl_bz_kiosk_iron"      # Dark forged parkerized iron (#262b30)
    plate935 = "mtl_bz_kiosk_935"   # Stamped "935" riveted steel faceplate
    brass = "mtl_bz_kiosk_brass"    # Restrained weathered brass (<=10%)
    glow_by_kind = {
        "perks": "mtl_bz_kiosk_perks_glow",
        "class": "mtl_bz_kiosk_class_glow",
        "arsenal": "mtl_bz_kiosk_arsenal_glow",
        "pap": "mtl_bz_kiosk_pap_glow",
    }
    glow = glow_by_kind[kind]

    def add_aabb(mat: str, x0: float, y0: float, z0: float, x1: float, y1: float, z1: float, bevel: float = 0.0) -> None:
        c = ((x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5)
        sz = (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
        if bevel > 0.0:
            m.add_beveled_box(mat, c, sz, bevel=bevel, bone_idx=0)
        else:
            m.add_box(mat, c, sz, bone_idx=0, uv_scale=0.04)

    if kind == "perks":
        # 1) Specialty Perk Station (26u W x 22u D x 70u H, Emerald #12a856, <=1,450v / <=1,100t, 4 mats)
        # Tall narrow 16-segment smooth-arched Olivgruen Group 935 Serum & Ampoule Dispensary over bolted Panzergrau plinth!
        add_aabb(frame, -11.0, -13.0, -4.0, 11.0, 13.0, 4.5, bevel=0.7)
        add_aabb(frame, -10.2, -12.0, 4.5, 10.2, 12.0, 7.6, bevel=0.45)
        add_aabb(brass, -9.8, -11.6, 7.4, 9.8, 11.6, 8.4)
        # True smooth 16-segment rounded-arch Olivgruen cabinet body (z=8.4..70.0u!)
        arch_pts: list[tuple[float, float]] = [(-11.4, 8.4), (11.4, 8.4), (11.4, 58.6)]
        for s in range(1, 16):
            ang = math.radians(180.0 * s / 16.0)
            arch_pts.append((math.cos(ang) * 11.4, 58.6 + math.sin(ang) * 11.4))
        arch_pts.append((-11.4, 58.6))
        m.add_extruded_yz_profile(enamel, -10.0, 7.2, arch_pts, bone_idx=0, uv_scale=0.04)
        # Raised Panzergrau front outer arch trim pillars & recessed shadow alcove framing the 3 serum tubes
        add_aabb(frame, 7.0, -11.6, 8.4, 9.6, -8.8, 58.6, bevel=0.3)
        add_aabb(frame, 7.0, 8.8, 8.4, 9.6, 11.6, 58.6, bevel=0.3)
        add_aabb(frame, 7.0, -11.6, 8.4, 9.8, 11.6, 25.0, bevel=0.35)
        # Smooth 12-segment curved arch crown molding around top!
        for s in range(12):
            a0 = math.radians(180.0 * s / 12.0)
            a1 = math.radians(180.0 * (s + 1) / 12.0)
            p0 = (8.4, math.cos(a0) * 10.6, 58.6 + math.sin(a0) * 10.6)
            p1 = (8.4, math.cos(a1) * 10.6, 58.6 + math.sin(a1) * 10.6)
            m.add_tapered_prism(frame, p0, p1, 1.10, 1.10, sides=5, bone_idx=0, cap_start=False, cap_end=False)
        # Continuous seamless 12-segment narrow curved arched emerald transom strip following the arch (Sheet 08 / O13!)
        r_in, r_out = 6.8, 8.3
        for s in range(12):
            a0 = math.radians(164.0 - 148.0 * s / 12.0)
            a1 = math.radians(164.0 - 148.0 * (s + 1) / 12.0)
            p_bl = (7.60, math.cos(a0) * r_in, 58.6 + math.sin(a0) * r_in)
            p_br = (7.60, math.cos(a1) * r_in, 58.6 + math.sin(a1) * r_in)
            p_tr = (7.60, math.cos(a1) * r_out, 58.6 + math.sin(a1) * r_out)
            p_tl = (7.60, math.cos(a0) * r_out, 58.6 + math.sin(a0) * r_out)
            m.add_quad_uv(glow, p_bl, p_br, p_tr, p_tl, (0.35, 0.65), (0.65, 0.65), (0.65, 0.35), (0.35, 0.35), bone_idx=0)
        # 3 slender steel-caged emerald serum ampoules (recessed vertical slits clear of collars, ZERO ring clipping!)
        for ty in (-5.6, 0.0, 5.6):
            m.add_tapered_prism(frame, (7.7, ty, 27.0), (7.7, ty, 54.0), 1.65, 1.65, sides=8, bone_idx=0)
            # Clean unobstructed vertical emerald slit proud of tube barrel
            m.add_quad_uv(
                glow,
                (9.55, ty - 0.68, 28.4),
                (9.55, ty + 0.68, 28.4),
                (9.55, ty + 0.68, 52.4),
                (9.55, ty - 0.68, 52.4),
                bone_idx=0,
            )
            # Side framing iron rails hugging the slit (no mid-ring crossing over the glass!)
            add_aabb(frame, 8.8, ty - 1.15, 28.0, 9.65, ty - 0.68, 52.8)
            add_aabb(frame, 8.8, ty + 0.68, 28.0, 9.65, ty + 1.15, 52.8)
            m.add_tapered_prism(brass, (7.7, ty, 25.6), (7.7, ty, 27.6), 1.94, 1.94, sides=8, bone_idx=0)
            m.add_tapered_prism(brass, (7.7, ty, 53.2), (7.7, ty, 55.2), 1.94, 1.94, sides=8, bone_idx=0)
        # Genuine recessed cast-iron drip catch basin (4 rim walls + recessed floor) + protruding curved brass gooseneck tap! (O13)
        add_aabb(frame, 9.4, -7.2, 11.4, 12.6, 7.2, 13.0, bevel=0.25)        # basin floor
        add_aabb(frame, 12.0, -7.2, 13.0, 12.7, 7.2, 15.2)                    # front lip wall
        add_aabb(frame, 9.4, -7.2, 13.0, 12.6, -6.4, 15.2)                    # left rim wall
        add_aabb(frame, 9.4, 6.4, 13.0, 12.6, 7.2, 15.2)                      # right rim wall
        add_aabb(brass, 9.8, -6.2, 13.0, 11.9, 6.2, 13.4)                     # brass drain grate inside basin
        m.add_tapered_prism(brass, (9.4, 0.0, 21.4), (11.6, 0.0, 21.4), 0.72, 0.56, sides=6, bone_idx=0)
        m.add_tapered_prism(brass, (11.4, 0.0, 21.6), (11.4, 0.0, 17.8), 0.46, 0.36, sides=6, bone_idx=0)
        m.add_tapered_prism(brass, (10.7, -2.0, 22.5), (10.7, 2.0, 22.5), 0.28, 0.28, sides=6, bone_idx=0)

    elif kind == "class":
        # 2) Class Station (32u W x 26u D x 58u H, Cobalt #186ce2, 4 mats: frame/plate935/brass/glow)
        # Waist-high tapered Group 935 Field Command Switchboard Lectern + open rear fork yoke & pointed "935" shield!
        add_aabb(frame, -13.0, -16.0, -4.0, 13.0, 16.0, 4.2, bevel=0.8)
        add_aabb(frame, -10.8, -13.2, 4.2, 10.8, 13.2, 7.6, bevel=0.5)
        # Slimmer tapered pedestal column (authentic lectern silhouette, NOT a fat cube!)
        add_aabb(frame, -7.8, -9.8, 7.6, 7.2, 9.8, 32.0, bevel=0.5)
        # Circular stamped "935" plinth medallion on lower front pedestal (outward +X CCW: -Y -> +Y)!
        m.add_tapered_prism(frame, (6.8, 0.0, 13.5), (7.8, 0.0, 13.5), 4.2, 4.2, sides=10, bone_idx=0)
        m.add_quad_uv(
            plate935,
            (7.86, -3.2, 10.6),
            (7.86, +3.2, 10.6),
            (7.86, +3.2, 16.4),
            (7.86, -3.2, 16.4),
            bone_idx=0,
        )
        # Wide flared angled command switchboard console desk (32u W x 26u D, sloped 20 deg toward player!)
        m.add_beveled_box(frame, (1.2, 0.0, 35.8), (22.0, 31.0, 6.2), bevel=0.65, bone_idx=0, rot_xyz=(0.0, 20.0, 0.0))
        # Raised riveted side cheek bezels flanking ONE continuous backlit frosted map-glass tactical plate!
        m.add_beveled_box(frame, (1.6, -12.8, 37.8), (18.5, 4.2, 3.2), bevel=0.35, bone_idx=0, rot_xyz=(0.0, 20.0, 0.0))
        m.add_beveled_box(frame, (1.6, +12.8, 37.8), (18.5, 4.2, 3.2), bevel=0.35, bone_idx=0, rot_xyz=(0.0, 20.0, 0.0))
        # Single crisp [0,1] UV-mapped backlit tactical blueprint screen (outward +X,+Z CCW: -Y -> +Y!)
        # Sloped plane centered at (1.8, 0, 39.2), pitch +20 deg (+X slopes down toward viewer)
        cp = math.cos(math.radians(20.0))
        sp = math.sin(math.radians(20.0))
        dx_h, dy_h = 7.4, 9.8
        sc_c = (1.6, 0.0, 39.35)
        p_bl = (sc_c[0] + dx_h * cp, sc_c[1] - dy_h, sc_c[2] - dx_h * sp)
        p_br = (sc_c[0] + dx_h * cp, sc_c[1] + dy_h, sc_c[2] - dx_h * sp)
        p_tr = (sc_c[0] - dx_h * cp, sc_c[1] + dy_h, sc_c[2] + dx_h * sp)
        p_tl = (sc_c[0] - dx_h * cp, sc_c[1] - dy_h, sc_c[2] + dx_h * sp)
        m.add_quad_uv(glow, p_bl, p_br, p_tr, p_tl, bone_idx=0)
        # Tactile brass rotary dials & toggle switches mounted on left/right control cheeks & lower rail!
        for dy in (-12.8, +12.8):
            for rx_off, rz_off in ((-3.5, 40.8), (1.0, 39.2), (5.5, 37.6)):
                m.add_tapered_prism(brass, (rx_off, dy, rz_off - 0.3), (rx_off + 0.5, dy, rz_off + 0.9), 0.95, 0.82, sides=8, bone_idx=0)
        for dy in (-6.0, 0.0, +6.0):
            m.add_tapered_prism(brass, (9.6, dy, 35.8), (10.8, dy, 36.4), 0.72, 0.62, sides=6, bone_idx=0)
        # Slender curved open rear steel fork yoke holding pointed heraldic "935" shield crest (peaking cleanly at z=58.0u!)
        for sy in (-1.0, +1.0):
            m.add_tapered_prism(frame, (-6.2, sy * 3.8, 39.5), (-7.8, sy * 7.6, 46.5), 0.85, 0.78, sides=6, bone_idx=0)
            m.add_tapered_prism(frame, (-7.8, sy * 7.6, 46.5), (-7.8, sy * 6.8, 53.5), 0.78, 0.72, sides=6, bone_idx=0)
        m.add_tapered_prism(frame, (-7.8, -7.2, 46.8), (-7.8, 7.2, 46.8), 0.72, 0.72, sides=6, bone_idx=0)
        # Pointed 1945 heraldic shield crest (top flat z=58.0, tapered point z=47.5!)
        shield_poly = [
            (-5.4, 58.0),
            (5.4, 58.0),
            (5.4, 52.4),
            (3.2, 49.4),
            (0.0, 47.4),
            (-3.2, 49.4),
            (-5.4, 52.4),
        ]
        m.add_extruded_yz_profile(frame, -9.2, -7.0, shield_poly, bone_idx=0, uv_scale=0.05)
        shield_face = [
            (-4.4, 57.1),
            (4.4, 57.1),
            (4.4, 52.7),
            (2.5, 50.1),
            (0.0, 48.5),
            (-2.5, 50.1),
            (-4.4, 52.7),
        ]
        m.add_extruded_yz_profile(plate935, -7.05, -6.55, shield_face, bone_idx=0, front_uv_fit=True)

    elif kind == "arsenal":
        # 3) Arsenal & Squad Workbench (54u W x 28u D x 62u H, Amber #de7616, <=1,450v / <=1,100t, 4 mats)
        # Wide armored Field Armorer's Workbench w/ paneled drawers, BOLD front-LEFT vise, contoured WWII rifle rack & louvered hood!
        add_aabb(frame, -14.0, -27.0, -4.0, 14.0, 27.0, 4.2, bevel=0.75)
        # Bolted tool chest carcass (z=4.2..30.0) + 9 recessed drawer fronts + 3D brass handles!
        add_aabb(frame, -13.0, -25.4, 4.2, 11.4, 25.4, 30.2, bevel=0.45)
        for dy in (-15.5, 0.0, +15.5):
            for dz in (10.0, 17.5, 24.8):
                add_aabb(iron, 11.1, dy - 6.8, dz - 2.6, 12.1, dy + 6.8, dz + 2.6)
                m.add_tapered_prism(brass, (12.6, dy - 3.4, dz), (12.6, dy + 3.4, dz), 0.38, 0.38, sides=5, bone_idx=0)
        # Thick dark forged-iron armored benchtop slab (z=30.2..33.0) with lighter steel front edge trim!
        add_aabb(iron, -13.8, -26.8, 30.2, 13.8, 26.8, 33.0, bevel=0.40)
        # BOLD sculpted heavy machinist's bench vise on PLAYER'S FRONT-LEFT (y = -22..-12, high-contrast steel jaw plates!)
        m.add_tapered_prism(frame, (8.8, -17.2, 32.9), (8.8, -17.2, 34.8), 4.2, 3.6, sides=8, bone_idx=0)
        add_aabb(frame, 5.4, -20.8, 34.6, 9.6, -13.6, 40.4, bevel=0.40)        # tall rear fixed jaw + anvil deck
        add_aabb(iron, 9.4, -20.6, 38.2, 10.2, -13.8, 40.2)                   # contrasting machined jaw face
        add_aabb(frame, 11.4, -20.8, 34.6, 15.2, -13.6, 40.2, bevel=0.40)     # tall sliding front jaw
        add_aabb(iron, 10.8, -20.6, 38.2, 11.6, -13.8, 40.0)                  # contrasting front jaw face
        add_aabb(iron, 8.6, -19.0, 34.6, 12.2, -15.4, 37.2)                   # forged slide beam
        m.add_tapered_prism(brass, (15.0, -17.2, 36.8), (17.6, -17.2, 36.8), 0.72, 0.72, sides=6, bone_idx=0)
        m.add_tapered_prism(brass, (17.1, -22.2, 36.8), (17.1, -12.2, 36.8), 0.36, 0.36, sides=6, bone_idx=0)
        # Rear armored tool wall + single [0,1]-mapped warm dark-amber perforated pegboard panel (outward +X CCW: -Y -> +Y!)
        add_aabb(frame, -13.6, -26.2, 33.0, -5.6, 26.2, 57.5, bevel=0.4)
        m.add_quad_uv(
            glow,
            (-5.45, -22.8, 36.2),
            (-5.45, +22.8, 36.2),
            (-5.45, +22.8, 54.8),
            (-5.45, -22.8, 54.8),
            bone_idx=0,
        )
        # 3 contoured extruded WWII weapon silhouette cards mounted in front of the amber pegboard (A6/S6/G3/O16!)
        # Top: Kar98k bolt-action rifle (angled sloped buttstock, narrow wrist, receiver, long tapered barrel + front sight)
        def add_sloped_card(mat: str, y0: float, z0: float, y1: float, z1: float, h0: float, h1: float) -> None:
            pts_c = [(y0, z0 - h0 * 0.5), (y1, z1 - h1 * 0.5), (y1, z1 + h1 * 0.5), (y0, z0 + h0 * 0.5)]
            m.add_extruded_yz_profile(mat, -5.0, -3.9, pts_c, bone_idx=0, uv_scale=0.08)

        # 1) Kar98k (top row, z~51.5)
        add_sloped_card(iron, -20.2, 50.6, -10.5, 51.9, 3.0, 1.35)    # angled wooden buttstock -> wrist
        add_sloped_card(iron, -10.6, 51.9, +4.2, 52.1, 1.65, 1.35)    # receiver + handguard
        add_sloped_card(iron, +4.0, 52.2, +20.2, 52.2, 0.72, 0.52)    # long tapered rifle barrel
        add_aabb(iron, -5.0, 17.6, 52.4, -3.9, 18.6, 53.6)            # hooded front sight post
        add_aabb(brass, -5.0, -6.2, 51.2, -3.7, -5.4, 52.5)           # bolt handle knob
        # 2) STG-44 assault rifle (middle row, z~45.5 — sloped stock, angled grip, curved banana mag, gas tube!)
        add_sloped_card(iron, -19.2, 44.8, -9.8, 45.9, 2.8, 1.45)     # sloped buttstock
        add_sloped_card(iron, -10.0, 45.9, +7.6, 46.1, 1.85, 1.55)    # stamped receiver + handguard
        add_sloped_card(iron, -7.8, 43.0, -5.8, 45.4, 1.45, 1.50)     # angled pistol grip
        add_sloped_card(iron, +0.4, 41.6, +3.6, 45.4, 1.75, 1.85)     # curved forward-swept banana magazine!
        add_sloped_card(iron, +7.4, 46.2, +18.2, 46.2, 0.86, 0.62)    # gas tube + barrel
        add_aabb(iron, -5.0, 15.6, 46.4, -3.9, 16.5, 47.6)            # front sight triangle
        # 3) MP40 SMG (bottom row, z~39.2 — slim wire stock strut, receiver, grip, vertical stick mag, muzzle nut!)
        add_sloped_card(iron, -18.0, 38.8, -11.5, 39.7, 0.65, 0.65)   # underfolder steel stock strut
        add_aabb(iron, -5.0, -18.4, 37.8, -3.9, -17.5, 39.8)          # buttplate
        add_sloped_card(iron, -12.0, 39.8, +5.8, 40.0, 1.55, 1.35)    # tubular receiver
        add_sloped_card(iron, -10.8, 37.2, -9.0, 39.3, 1.25, 1.30)    # angled Bakelite grip
        add_sloped_card(iron, -1.2, 36.2, +0.6, 39.4, 1.15, 1.20)     # slender vertical stick magazine
        add_sloped_card(iron, +5.6, 40.1, +14.8, 40.1, 0.68, 0.56)    # barrel + muzzle nut
        # Side uprights + flush louvered overhead hood (<=3u overhang, peaking at z=62.0u!)
        for sy in (-25.0, +25.0):
            add_aabb(frame, -13.6, sy - 1.5, 33.0, 2.2, sy + 1.5, 57.8)
        add_aabb(iron, -14.0, -26.6, 57.4, 3.0, 26.6, 62.0, bevel=0.55)
        for lz in (58.6, 60.2):
            add_aabb(frame, 2.8, -22.5, lz, 3.4, 22.5, lz + 0.55)

    else:
        # 4) Pack-a-Punch Prototype Processing Press (<=42u overall W incl. detached +Y flue to 68.0u H, 600-1,150t, 4 mats!)
        # Squat heavy armored press w/ crisp vector "935" header, ribbed 12-sided grooved steel roller pack, narrow violet slit,
        # and detached PLAYER'S-RIGHT exhaust flue + FORWARD-VISIBLE caged violet sight tube (A7/S7/F10/F24/F27/O10)!
        add_aabb(frame, -15.0, -18.6, -4.0, 15.0, 18.6, 4.8, bevel=0.80)
        # Broad heavy bolted cast-iron lower body + stepped press shoulders (body width 34.8u -> flue fits inside 42u overall!)
        add_aabb(frame, -14.0, -17.4, 4.8, 13.0, 17.4, 21.0, bevel=0.50)
        for sy in (-14.2, +14.2):
            add_aabb(frame, -14.0, sy - 3.3, 21.0, 13.4, sy + 3.3, 44.0)
        # Deep dark shadowed intake throat cavity behind the rollers
        add_aabb(iron, -14.0, -11.0, 21.0, 3.4, 11.0, 44.0)
        # Angled lighter-steel weapon-intake feed lip & upper baffle so intake mouth reads clearly in dark maps (G14/O10!)
        add_aabb(frame, 3.4, -11.0, 20.8, 14.4, 11.0, 23.0)
        add_aabb(iron, 3.4, -11.0, 41.4, 13.6, 11.0, 43.8)
        # Bold 12-sided grooved forged-iron roller pack w/ 4 machined steel traction ribs per drum (A7/S7/O10/F24!)
        for rz in (26.2, 38.4):
            m.add_tapered_prism(iron, (8.6, -10.8, rz), (8.6, +10.8, rz), 3.12, 3.12, sides=12, bone_idx=0)
            for ry in (-7.2, -2.4, +2.4, +7.2):
                m.add_tapered_prism(frame, (8.6, ry - 0.62, rz), (8.6, ry + 0.62, rz), 3.38, 3.38, sides=12, bone_idx=0)
        # ONE narrow, deep-recessed moody horizontal violet plasma slit between the rollers (outward +X CCW: -Y -> +Y!)
        m.add_quad_uv(
            glow,
            (4.0, -10.2, 30.2),
            (4.0, +10.2, 30.2),
            (4.0, +10.2, 34.4),
            (4.0, -10.2, 34.4),
            bone_idx=0,
        )
        # Squat riveted upper armored press crown (z=43.8..57.6 so the right-side flue towers 10.4u proud to exact 68.0u! F10/O10)
        add_aabb(frame, -14.5, -18.0, 43.8, 13.6, 18.0, 55.4, bevel=0.60)
        add_aabb(iron, -13.4, -16.6, 55.4, 12.4, 16.6, 57.6)
        # Crisp vector SDF "935" riveted steel nameplate on front upper header (outward +X CCW: -Y -> +Y!)
        m.add_quad_uv(
            plate935,
            (13.72, -12.4, 45.2),
            (13.72, +12.4, 45.2),
            (13.72, +12.4, 54.4),
            (13.72, -12.4, 54.4),
            bone_idx=0,
        )
        # DETACHED asymmetric PLAYER'S-RIGHT (+Y) exhaust flue rising 10.4u proud to exact 68.0u H w/ clean air gap outside crown (total W <= 40.6u! F31)
        m.add_tapered_prism(iron, (-2.2, +20.1, 22.0), (-2.2, +20.1, 67.6), 1.65, 1.50, sides=8, bone_idx=0)
        m.add_tapered_prism(frame, (-2.2, +20.1, 65.0), (-2.2, +20.1, 68.0), 1.85, 1.75, sides=8, bone_idx=0)
        for bz in (28.0, 50.0):
            add_aabb(frame, -3.8, 17.2, bz - 1.3, -0.4, 20.3, bz + 1.3)
        # FORWARD-OFFSET unoccluded caged vertical violet plasma sight-tube at x=+10.2, y=+18.8 (visible head-on AND oblique! F10/O10)
        m.add_tapered_prism(glow, (10.2, +18.8, 24.5), (10.2, +18.8, 52.0), 1.42, 1.42, sides=8, bone_idx=0)
        for cz in (24.0, 38.2, 52.4):
            m.add_tapered_prism(iron, (10.2, +18.8, cz - 0.85), (10.2, +18.8, cz + 0.85), 1.82, 1.82, sides=8, bone_idx=0)
        for c_ang in (45.0, 135.0, 225.0, 315.0):
            rad = math.radians(c_ang)
            m.add_tapered_prism(
                iron,
                (10.2 + math.cos(rad) * 1.72, 18.8 + math.sin(rad) * 1.72, 24.0),
                (10.2 + math.cos(rad) * 1.72, 18.8 + math.sin(rad) * 1.72, 52.4),
                0.22,
                0.22,
                sides=4,
                bone_idx=0,
            )
        for bz in (24.0, 52.4):
            add_aabb(iron, 8.6, 17.0, bz - 0.9, 11.6, 19.2, bz + 0.9)
    return m


# ---------------------------------------------------------------------------
# 8. WAVE 2: ARSENAL UPGRADES & SAPPER DEPLOYABLE TRAPS (Sheet 09 — 9 XMODELs)
# ---------------------------------------------------------------------------


def build_pap_cluster_grenade(name: str, is_world: bool = False) -> MeshBuilder:
    """1945 smooth-cylinder M24 Geballte Ladung (14.5u L x 5.6u dia; 0 US pineapple grooves; VM <=1,650v, WM <=950v)."""
    bones = world_weapon_bones((4.0, 0.0, 2.0)) if is_world else BONES_COLT45
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0
    steel = "mtl_bz_pap_cluster_steel"
    wood = "mtl_bz_pap_cluster_wood"
    brass = "mtl_bz_xbow_brass"
    glow = "mtl_bz_pap_cluster_glow"

    s = 1.0 if not is_world else 1.15
    sides = 6 if is_world else 8

    # Turned oiled walnut M24 stick handle + screwed bottom steel fuse cap (14.5u overall length!)
    m.add_tapered_prism(steel, (0.0, 0.0, -5.8 * s), (0.0, 0.0, -4.9 * s), 0.56 * s, 0.58 * s, sides=sides, bone_idx=b_gun)
    m.add_tapered_prism(wood, (0.0, 0.0, -4.9 * s), (0.0, 0.0, 3.6 * s), 0.54 * s, 0.48 * s, sides=sides, bone_idx=b_gun)
    m.add_tapered_prism(brass, (0.0, 0.0, 3.2 * s), (0.0, 0.0, 4.0 * s), 0.62 * s, 0.68 * s, sides=sides, bone_idx=b_gun)

    # Central smooth cylindrical M24 head + #ffc448 PaP arming band
    m.add_tapered_prism(steel, (0.0, 0.0, 3.8 * s), (0.0, 0.0, 8.7 * s), 1.28 * s, 1.28 * s, sides=sides, bone_idx=b_gun)
    m.add_tapered_prism(glow, (0.0, 0.0, 5.9 * s), (0.0, 0.0, 6.5 * s), 1.32 * s, 1.32 * s, sides=sides, bone_idx=b_gun, cap_start=False, cap_end=False)

    # 4 strapped smooth cylindrical submunition canisters ringing the M24 head (total ~5.6u dia!) + copper wire clamps
    for k in range(4):
        ang = math.radians(k * 90.0 + 45.0)
        cy = math.cos(ang) * 1.92 * s
        cz_x = math.sin(ang) * 1.92 * s
        m.add_tapered_prism(steel, (cz_x, cy, 4.1 * s), (cz_x, cy, 8.3 * s), 0.88 * s, 0.88 * s, sides=sides, bone_idx=b_gun)
        m.add_tapered_prism(glow, (cz_x, cy, 5.95 * s), (cz_x, cy, 6.45 * s), 0.91 * s, 0.91 * s, sides=sides, bone_idx=b_gun, cap_start=False, cap_end=False)
    m.add_tapered_prism(brass, (0.0, 0.0, 5.0 * s), (0.0, 0.0, 5.45 * s), 2.80 * s, 2.80 * s, sides=8, bone_idx=b_gun, cap_start=False, cap_end=False)
    m.add_tapered_prism(brass, (0.0, 0.0, 7.15 * s), (0.0, 0.0, 7.55 * s), 2.80 * s, 2.80 * s, sides=8, bone_idx=b_gun, cap_start=False, cap_end=False)
    return m


def build_pap_cluster_submunition() -> MeshBuilder:
    """Detached 2.0u dia x 4.5u H smooth cylindrical M24 submunition (<=340 verts, 0 FX)."""
    m = MeshBuilder("bz_pap_cluster_sub", BONES_RIGID, model_type="rigid")
    steel = "mtl_bz_pap_cluster_steel"
    glow = "mtl_bz_pap_cluster_glow"
    m.add_tapered_prism(steel, (0.0, 0.0, -2.25), (0.0, 0.0, +2.25), 1.0, 1.0, sides=8, bone_idx=0)
    m.add_tapered_prism(glow, (0.0, 0.0, -0.35), (0.0, 0.0, +0.35), 1.04, 1.04, sides=8, bone_idx=0, cap_start=False, cap_end=False)
    m.add_tapered_prism(steel, (0.0, 0.0, +2.20), (0.0, 0.0, +2.55), 0.42, 0.36, sides=6, bone_idx=0)
    return m


def build_pap_knife(name: str, is_world: bool = False) -> MeshBuilder:
    """PaP Combat Knife: walnut handle, cold matte steel edge, recessed #ff6a1a fuller on BOTH blade faces (VM <=850v, WM <=500v)."""
    bones = world_weapon_bones((6.0, 0.0, 1.2)) if is_world else BONES_COLT45
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0
    steel = "mtl_bz_pap_melee_steel"
    wood = "mtl_bz_pap_cluster_wood"
    glow = "mtl_bz_pap_knife_glow"
    s = 1.35 if is_world else 1.0
    sides = 6 if is_world else 8

    m.add_tapered_prism(steel, (-0.4 * s, 0.0, -2.8 * s), (-0.2 * s, 0.0, -2.2 * s), 0.42 * s, 0.48 * s, sides=sides, bone_idx=b_gun)
    m.add_tapered_prism(wood, (-0.2 * s, 0.0, -2.2 * s), (0.3 * s, 0.0, 1.2 * s), 0.44 * s, 0.46 * s, sides=sides, bone_idx=b_gun)
    m.add_box(steel, (0.45 * s, 0.0, 1.35 * s), (1.75 * s, 0.62 * s, 0.34 * s), bone_idx=b_gun)
    m.add_box(steel, (1.55 * s, 0.0, 4.4 * s), (1.10 * s, 0.20 * s, 5.8 * s), bone_idx=b_gun, rot_xyz=(0.0, 14.0, 0.0))
    m.add_tapered_prism(steel, (2.25 * s, 0.0, 7.1 * s), (2.95 * s, 0.0, 9.6 * s), 0.56 * s, 0.04 * s, sides=4, bone_idx=b_gun, scale_y=0.22)
    # Recessed #ff6a1a thermal fuller slot visible on BOTH +Y and -Y blade faces (cold steel edge!)
    for side in (-1.0, +1.0):
        m.add_box(glow, (1.42 * s, side * 0.11 * s, 4.45 * s), (0.28 * s, 0.05 * s, 4.1 * s), bone_idx=b_gun, rot_xyz=(0.0, 14.0, 0.0))
    return m


def build_pap_bowie(name: str, is_world: bool = False) -> MeshBuilder:
    """PaP Bowie Knife: clipped-point heavy blade, stacked leather grip, 3 oblong #ff4a12 coil windows (VM <=1,100v, WM <=620v)."""
    bones = world_weapon_bones((8.0, 0.0, 1.5)) if is_world else BONES_COLT45
    m = MeshBuilder(name, bones, model_type="animated")
    b_gun = 0
    steel = "mtl_bz_pap_melee_steel"
    leather = "mtl_bz_blade_leather"
    glow = "mtl_bz_pap_bowie_glow"
    s = 1.40 if is_world else 1.0
    sides = 6 if is_world else 8

    m.add_tapered_prism(steel, (-0.5 * s, 0.0, -3.1 * s), (-0.2 * s, 0.0, -2.4 * s), 0.48 * s, 0.56 * s, sides=sides, bone_idx=b_gun)
    m.add_tapered_prism(leather, (-0.2 * s, 0.0, -2.4 * s), (0.3 * s, 0.0, 1.3 * s), 0.48 * s, 0.52 * s, sides=sides, bone_idx=b_gun)
    m.add_box(steel, (0.45 * s, 0.0, 1.45 * s), (2.45 * s, 0.72 * s, 0.38 * s), bone_idx=b_gun)
    m.add_box(steel, (1.95 * s, 0.0, 5.2 * s), (1.72 * s, 0.26 * s, 7.2 * s), bone_idx=b_gun, rot_xyz=(0.0, 16.0, 0.0))
    m.add_tapered_prism(steel, (2.95 * s, 0.0, 8.6 * s), (4.15 * s, 0.0, 11.8 * s), 0.86 * s, 0.05 * s, sides=4, bone_idx=b_gun, scale_y=0.22)
    # 3 oblong recessed #ff4a12 copper coil windows along upper spine on BOTH faces!
    for w_idx, wz in enumerate((3.1, 4.9, 6.7)):
        wx = 1.08 + w_idx * 0.52
        for side in (-1.0, +1.0):
            m.add_box(glow, (wx * s, side * 0.14 * s, wz * s), (0.34 * s, 0.06 * s, 1.35 * s), bone_idx=b_gun, rot_xyz=(0.0, 16.0, 0.0))
    return m


def build_sapper_trap_fire() -> MeshBuilder:
    """Sapper BRANDSATZ Fire Trap (11u dia x 6u H, flat z=-1..0 base, 2 material slots, <=650 verts)."""
    m = MeshBuilder("bz_sapper_trap_fire", BONES_RIGID, model_type="rigid")
    body = "mtl_bz_trap_fire_body"
    glow = "mtl_bz_trap_fire_glow"
    m.add_tapered_prism(body, (0.0, 0.0, -1.0), (0.0, 0.0, 0.6), 6.0, 5.8, sides=10, bone_idx=0)
    m.add_tapered_prism(body, (0.0, 0.0, 0.5), (0.0, 0.0, 5.6), 5.4, 5.4, sides=10, bone_idx=0)
    m.add_tapered_prism(body, (0.0, 0.0, 5.4), (0.0, 0.0, 6.0), 5.6, 5.3, sides=10, bone_idx=0)
    m.add_tapered_prism(glow, (0.0, 0.0, 5.85), (0.0, 0.0, 6.12), 4.3, 4.3, sides=10, bone_idx=0, cap_start=False)
    m.add_box(body, (0.0, 0.0, 6.18), (8.6, 0.62, 0.24), bone_idx=0, rot_xyz=(0.0, 0.0, 45.0))
    m.add_box(body, (0.0, 0.0, 6.18), (8.6, 0.62, 0.24), bone_idx=0, rot_xyz=(0.0, 0.0, -45.0))
    return m


def build_sapper_trap_betty() -> MeshBuilder:
    """Sapper S-Mine 35 Blast Mine (5.2u body / 6.6u flange x 13.8u overall H w/ 3 prongs, 2 slots, <=600 verts)."""
    m = MeshBuilder("bz_sapper_trap_betty", BONES_RIGID, model_type="rigid")
    body = "mtl_bz_trap_betty_body"
    glow = "mtl_bz_trap_betty_glow"
    m.add_tapered_prism(body, (0.0, 0.0, -1.0), (0.0, 0.0, 0.6), 3.3, 3.2, sides=10, bone_idx=0)
    m.add_tapered_prism(body, (0.0, 0.0, 0.5), (0.0, 0.0, 9.2), 2.6, 2.6, sides=10, bone_idx=0)
    m.add_tapered_prism(glow, (0.0, 0.0, 9.1), (0.0, 0.0, 10.3), 2.85, 2.75, sides=10, bone_idx=0)
    m.add_tapered_prism(body, (0.0, 0.0, 10.2), (0.0, 0.0, 11.0), 0.72, 0.56, sides=6, bone_idx=0)
    for pdeg in (0.0, 120.0, 240.0):
        rad = math.radians(pdeg)
        m.add_tapered_prism(
            body,
            (math.cos(rad) * 0.25, math.sin(rad) * 0.25, 10.8),
            (math.cos(rad) * 1.45, math.sin(rad) * 1.45, 13.8),
            0.14,
            0.05,
            sides=4,
            bone_idx=0,
        )
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
    MaterialSpec("mtl_bz_cryo_hull", "model phong", "metal", "wintertarnung", (62, 68, 76), (174, 180, 184), (50, 54, 58), 160),
    MaterialSpec("mtl_bz_cryo_dark", "model phong", "metal", "brushed_metal", (46, 52, 58), (78, 86, 94), (48, 52, 58), 185),
    MaterialSpec("mtl_bz_cryo_glow", "model unlit", "glass", "cryo_glow", (16, 165, 246), (178, 246, 255)),
    # Multi-Crossbow (oiled dark walnut #583520, stamped blued steel #2a2e33, weathered brass #9b7b3c, amber #ffb020)
    MaterialSpec("mtl_bz_xbow_wood", "model phong", "wood", "wood_grain", (96, 58, 34), (56, 30, 15), (22, 16, 12), 82),
    MaterialSpec("mtl_bz_xbow_metal", "model phong", "metal", "panel_metal", (46, 52, 58), (78, 86, 94), (46, 50, 54), 165),
    MaterialSpec("mtl_bz_xbow_brass", "model phong", "metal", "brushed_metal", (164, 130, 64), (108, 82, 36), (60, 48, 24), 195),
    MaterialSpec("mtl_bz_xbow_glow", "model unlit", "glass", "amber_glow", (255, 176, 32), (255, 218, 114)),
    # Blade Boomerang (WWII brushed propeller steel, stitched leather #4a2e1e, weathered bronze, deep industrial crimson #c81840)
    MaterialSpec("mtl_bz_blade_steel", "model phong", "metal", "brushed_metal", (104, 112, 120), (62, 68, 76), (58, 62, 66), 210),
    MaterialSpec("mtl_bz_blade_leather", "model phong", "cloth", "leather", (78, 48, 30), (44, 26, 14), (18, 14, 10), 65),
    MaterialSpec("mtl_bz_blade_brass", "model phong", "metal", "brushed_metal", (158, 126, 62), (108, 80, 34), (60, 48, 24), 195),
    MaterialSpec("mtl_bz_blade_glow", "model unlit", "glass", "crimson_glow", (232, 30, 80), (238, 68, 102)),
    # Acid Sprayer (Flammenwerfer-41: Panzergrau steel #363c42, Olivgruen tank w/ Gruenkreuz + "AETZEND", bright lime #68f030)
    MaterialSpec("mtl_bz_acid_metal", "model phong", "metal", "panel_metal", (64, 70, 78), (98, 106, 116), (46, 50, 54), 155),
    MaterialSpec("mtl_bz_acid_hazard", "model phong", "metal", "acid_enamel", (86, 102, 70), (192, 198, 184), (38, 42, 34), 135),
    MaterialSpec("mtl_bz_acid_glow", "model unlit", "glass", "acid_glow", (104, 240, 48), (192, 255, 132)),
    # Acid Sprayer Gas Stream (2D FLAMETABLEFILE effect materials, 0 added FX slots — ADR-0004)
    MaterialSpec("mtl_bz_acid_stream", "effect", "<none>", "acid_stream", (32, 235, 58), (190, 255, 120), blend_func="Add", z_feather=False, fogable=False),
    MaterialSpec("mtl_bz_acid_billow", "effect", "<none>", "acid_billow", (28, 220, 52), (175, 255, 102), blend_func="Add", z_feather=True, fogable=False),
    MaterialSpec("mtl_bz_acid_drips", "effect", "<none>", "acid_drips", (46, 248, 66), (215, 255, 138), blend_func="Add", z_feather=True, fogable=False),
    MaterialSpec("mtl_bz_acid_mist", "effect", "<none>", "acid_mist", (72, 175, 62), (145, 220, 96), blend_func="Blend", z_feather=True, fogable=True),
    # Portal Grenade (blued steel #2a2e33, faceted dark-violet E115 shard #8e22da, weathered brass #9b7b3c)
    MaterialSpec("mtl_bz_portal_ring", "model phong", "metal", "brushed_metal", (46, 52, 58), (82, 88, 98), (52, 56, 62), 195),
    MaterialSpec("mtl_bz_portal_core", "model unlit", "glass", "portal_glow", (142, 34, 218), (224, 152, 255)),
    MaterialSpec("mtl_bz_portal_trim", "model phong", "metal", "brushed_metal", (162, 128, 62), (108, 82, 36), (60, 48, 24), 195),
    # War Club (charred ash #563824, forged blackened iron #2a2e33, deep forge red-orange #ff4a12 solenoid coils)
    MaterialSpec("mtl_bz_club_wood", "model phong", "wood", "wood_grain", (92, 60, 38), (48, 28, 15), (20, 16, 12), 76),
    MaterialSpec("mtl_bz_club_iron", "model phong", "metal", "corroded_metal", (54, 60, 66), (92, 98, 108), (52, 56, 62), 175),
    MaterialSpec("mtl_bz_club_glow", "model unlit", "glass", "solenoid_coil", (255, 74, 18), (255, 168, 72)),
    # In-World Station Kiosks (lifted value Panzergrau + Olivgruen + forged iron + SDF stamped "935" so silhouettes read in Verruckt!)
    MaterialSpec("mtl_bz_kiosk_frame", "model phong", "metal", "panel_metal", (96, 104, 112), (138, 148, 158), (54, 58, 64), 175),
    MaterialSpec("mtl_bz_kiosk_enamel", "model phong", "metal", "olivgruen_enamel", (94, 108, 80), (130, 144, 110), (42, 46, 38), 145),
    MaterialSpec("mtl_bz_kiosk_iron", "model phong", "metal", "forged_iron", (64, 70, 78), (104, 114, 124), (56, 60, 66), 190),
    MaterialSpec("mtl_bz_kiosk_935", "model phong", "metal", "kiosk_plate_935", (86, 94, 102), (218, 222, 226), (48, 52, 58), 165),
    MaterialSpec("mtl_bz_kiosk_brass", "model phong", "metal", "brushed_metal", (172, 138, 68), (112, 84, 36), (60, 48, 24), 190),
    MaterialSpec("mtl_bz_kiosk_perks_glow", "model unlit", "glass", "kiosk_perks_serum", (16, 154, 78), (94, 210, 138)),
    MaterialSpec("mtl_bz_kiosk_class_glow", "model unlit", "glass", "kiosk_class_map", (26, 86, 174), (96, 162, 218)),
    MaterialSpec("mtl_bz_kiosk_arsenal_glow", "model unlit", "glass", "kiosk_arsenal_pegboard", (176, 76, 12), (214, 118, 26)),
    MaterialSpec("mtl_bz_kiosk_pap_glow", "model unlit", "glass", "kiosk_pap_slit", (142, 34, 218), (212, 118, 248)),
    # Wave 2: Arsenal Upgrades & Sapper Traps (Sheet 09 — 100% opaque WaW 1.7)
    MaterialSpec("mtl_bz_pap_cluster_steel", "model phong", "metal", "panel_metal", (54, 60, 66), (80, 88, 96), (48, 52, 56), 165),
    MaterialSpec("mtl_bz_pap_cluster_wood", "model phong", "wood", "wood_grain", (88, 53, 32), (48, 26, 12), (20, 16, 12), 78),
    MaterialSpec("mtl_bz_pap_cluster_glow", "model unlit", "glass", "amber_glow", (255, 196, 72), (255, 232, 152)),
    MaterialSpec("mtl_bz_pap_melee_steel", "model phong", "metal", "brushed_metal", (42, 46, 51), (78, 84, 92), (56, 60, 64), 195),
    MaterialSpec("mtl_bz_pap_knife_glow", "model unlit", "glass", "amber_glow", (255, 106, 26), (255, 196, 110)),
    MaterialSpec("mtl_bz_pap_bowie_glow", "model unlit", "glass", "solenoid_coil", (255, 74, 18), (255, 178, 92)),
    MaterialSpec("mtl_bz_trap_fire_body", "model phong", "metal", "panel_metal", (92, 53, 40), (54, 60, 66), (46, 48, 50), 150),
    MaterialSpec("mtl_bz_trap_fire_glow", "model unlit", "glass", "amber_glow", (255, 120, 24), (255, 204, 102)),
    MaterialSpec("mtl_bz_trap_betty_body", "model phong", "metal", "olivgruen_enamel", (66, 75, 58), (94, 106, 80), (40, 44, 36), 140),
    MaterialSpec("mtl_bz_trap_betty_glow", "model unlit", "glass", "crimson_glow", (232, 30, 80), (255, 138, 168)),
    # Wave 3: Custom Primary Pack-a-Punch Stage 1 & Stage 2 Finishes (Sheet 10 — 0 violet bleed, +/-8 deg hue lock)
    MaterialSpec("mtl_bz_pap1_steel", "model phong", "metal", "pap1_etched", (37, 42, 50), (155, 123, 60), (54, 56, 58), 185),
    MaterialSpec("mtl_bz_pap1_brass", "model phong", "metal", "brushed_metal", (155, 123, 60), (108, 82, 36), (64, 52, 26), 205),
    MaterialSpec("mtl_bz_pap2_steel", "model phong", "metal", "pap2_crystalline", (25, 29, 34), (138, 146, 156), (62, 66, 70), 205),
    MaterialSpec("mtl_bz_pap2_trim", "model phong", "metal", "pap2_crystalline", (138, 146, 156), (82, 90, 98), (66, 70, 72), 215),
    MaterialSpec("mtl_bz_acid_glow_pap1", "model unlit", "glass", "acid_glow", (114, 245, 61), (198, 255, 152)),
    MaterialSpec("mtl_bz_acid_glow_pap2", "model unlit", "glass", "acid_glow", (152, 255, 110), (226, 255, 196)),
    MaterialSpec("mtl_bz_cryo_glow_pap1", "model unlit", "glass", "cryo_glow", (56, 196, 255), (186, 244, 255)),
    MaterialSpec("mtl_bz_cryo_glow_pap2", "model unlit", "glass", "cryo_glow", (138, 226, 255), (228, 250, 255)),
    MaterialSpec("mtl_bz_xbow_glow_pap1", "model unlit", "glass", "amber_glow", (255, 196, 72), (255, 234, 160)),
    MaterialSpec("mtl_bz_xbow_glow_pap2", "model unlit", "glass", "amber_glow", (255, 220, 130), (255, 246, 206)),
    MaterialSpec("mtl_bz_blade_glow_pap1", "model unlit", "glass", "crimson_glow", (242, 66, 112), (255, 164, 190)),
    MaterialSpec("mtl_bz_blade_glow_pap2", "model unlit", "glass", "crimson_glow", (255, 122, 158), (255, 208, 222)),
    # Wave 4: 21 Linked 64x64 2D HUD Icons (Sheet 11 — Shield / Square / Gold-T2 / Bronze-Circle / Steel-Diamond)
    MaterialSpec("bz_icon_class_medic", "2d", "<none>", "hud_class_medic", (42, 48, 54), (224, 52, 64), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_class_titan", "2d", "<none>", "hud_class_titan", (42, 48, 54), (176, 186, 196), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_class_sapper", "2d", "<none>", "hud_class_sapper", (42, 48, 54), (255, 148, 42), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_class_daredevil", "2d", "<none>", "hud_class_daredevil", (42, 48, 54), (255, 204, 56), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_class_assassin", "2d", "<none>", "hud_class_assassin", (42, 48, 54), (232, 30, 80), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_class_broker", "2d", "<none>", "hud_class_broker", (42, 48, 54), (222, 182, 74), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_perk_staminup", "2d", "<none>", "hud_perk_staminup", (54, 44, 24), (255, 192, 52), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_perk_mulekick", "2d", "<none>", "hud_perk_mulekick", (28, 56, 36), (92, 224, 118), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_perk_armorpiercing", "2d", "<none>", "hud_perk_armorpiercing", (28, 44, 62), (76, 198, 255), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_perk_jugg_t2", "2d", "<none>", "hud_t2_jugg", (128, 28, 36), (255, 220, 130), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_perk_speed_t2", "2d", "<none>", "hud_t2_speed", (28, 108, 54), (255, 220, 130), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_perk_dtap_t2", "2d", "<none>", "hud_t2_dtap", (152, 86, 20), (255, 220, 130), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_perk_revive_t2", "2d", "<none>", "hud_t2_revive", (24, 108, 148), (255, 220, 130), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_perk_staminup_t2", "2d", "<none>", "hud_t2_staminup", (142, 96, 22), (255, 220, 130), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_perk_mulekick_t2", "2d", "<none>", "hud_t2_mulekick", (34, 114, 56), (255, 220, 130), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_perk_armorpiercing_t2", "2d", "<none>", "hud_t2_armorpiercing", (34, 84, 136), (255, 220, 130), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_apex_dblammo", "2d", "<none>", "hud_apex_dblammo", (148, 108, 52), (248, 222, 152), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_apex_lightheavy", "2d", "<none>", "hud_apex_lightheavy", (148, 108, 52), (248, 222, 152), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_apex_secondchance", "2d", "<none>", "hud_apex_secondchance", (148, 108, 52), (248, 222, 152), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_apex_blastshield", "2d", "<none>", "hud_apex_blastshield", (148, 108, 52), (248, 222, 152), blend_func="Blend", fogable=False),
    MaterialSpec("bz_icon_pap2_badge", "2d", "<none>", "hud_pap2_diamond", (42, 48, 56), (255, 220, 130), blend_func="Blend", fogable=False),
)


def _render_hud_icon_64(spec: MaterialSpec, size: int = 64) -> bytearray:
    """Render a crisp 2D HUD icon (default 64x64) with monochrome-distinct silhouette (Sheet 11 / ADR-0007)."""
    buf = bytearray(size * size * 4)
    br, bg, bb = spec.base_rgb
    ar, ag, ab = spec.accent_rgb
    style = spec.style
    is_shield = style.startswith("hud_class_")
    is_perk = style.startswith("hud_perk_")
    is_t2 = style.startswith("hud_t2_")
    is_apex = style.startswith("hud_apex_")
    is_diamond = style == "hud_pap2_diamond"

    def _sample(nx: float, ny: float) -> tuple[int, int, int, int]:
        # nx, ny in [-1, 1], ny=-1 top, ny=+1 bottom
        ax, ay = abs(nx), abs(ny)
        # 1. Silhouette SDF (negative inside, positive outside)
        if is_shield:
            # Pointed WWII heraldic shield: flat top y=-0.88, tapered curved lower point to y=+0.92
            if ny < -0.88 or ny > 0.92:
                return (0, 0, 0, 0)
            max_w = 0.80 if ny <= 0.05 else max(0.0, 0.80 * (1.0 - ((ny - 0.05) / 0.87) ** 1.45))
            if ax > max_w:
                return (0, 0, 0, 0)
            edge = min(max_w - ax, ny - (-0.88), 0.92 - ny)
            if edge < 0.09:
                return (20, 24, 28, 255)
            if edge < 0.17:
                return (142, 150, 160, 255)
            r, g, b = br, bg, bb
            # Distinct class center glyphs
            glyph = False
            if style == "hud_class_medic":
                glyph = (ax < 0.16 and -0.48 < ny < 0.36) or (ax < 0.44 and -0.22 < ny < 0.10)
            elif style == "hud_class_titan":
                glyph = (ax < 0.46 and abs(ny - (-0.18 + ax * 0.55)) < 0.11) or (ax < 0.40 and abs(ny - (0.14 + ax * 0.55)) < 0.10)
            elif style == "hud_class_sapper":
                d = math.hypot(nx, ny - 0.06)
                glyph = (d < 0.34) or (ax < 0.10 and -0.52 < ny < -0.22) or (abs(ax - 0.24) < 0.07 and -0.44 < ny < -0.20)
            elif style == "hud_class_daredevil":
                glyph = (abs(nx + ny * 0.38) < 0.13 and -0.50 < ny < 0.05) or (abs(nx - 0.14 + ny * 0.38) < 0.13 and -0.10 < ny < 0.48)
            elif style == "hud_class_assassin":
                glyph = (ax < 0.09 and -0.52 < ny < 0.48) or (ax < 0.36 and abs(ny - 0.10) < 0.07) or (abs(math.hypot(nx, ny + 0.10) - 0.34) < 0.06)
            elif style == "hud_class_broker":
                glyph = (ax < 0.42 and abs(ny + 0.28) < 0.08) or (ax < 0.34 and abs(ny + 0.02) < 0.08) or (ax < 0.44 and abs(ny - 0.24) < 0.08)
            if glyph:
                return (ar, ag, ab, 255)
            return (r, g, b, 255)

        if is_perk or is_t2:
            # Beveled square (0.86 half-width, 0.12 corner chamfer)
            if ax > 0.88 or ay > 0.88 or (ax + ay) > 1.62:
                return (0, 0, 0, 0)
            edge = min(0.88 - ax, 0.88 - ay, (1.62 - (ax + ay)) * 0.707)
            if is_t2:
                # Dark-separated bright gold (#ffdc82) Tier-2 bezel!
                if edge < 0.07:
                    return (18, 16, 14, 255)
                if edge < 0.19:
                    return (255, 220, 130, 255)
                if edge < 0.25:
                    return (22, 20, 18, 255)
            else:
                if edge < 0.08:
                    return (18, 20, 24, 255)
                if edge < 0.16:
                    return (136, 144, 154, 255)

            # Baked wide-gap bottom-right "II" Roman bars for Tier-2 (0 extra HUD elements!)
            if is_t2 and nx > 0.18 and ny > 0.16:
                if nx > 0.22 and ny > 0.20:
                    # Dark backing pill for high legibility
                    in_bar1 = (0.32 <= nx <= 0.43) and (0.28 <= ny <= 0.64)
                    in_bar2 = (0.53 <= nx <= 0.64) and (0.28 <= ny <= 0.64)
                    in_cap = (0.28 <= nx <= 0.68) and ((0.26 <= ny <= 0.32) or (0.60 <= ny <= 0.66))
                    if in_bar1 or in_bar2 or in_cap:
                        return (255, 228, 142, 255)
                    return (20, 18, 16, 255)

            # Inner perk symbol
            sym = False
            sx, sy = (nx + 0.06, ny + 0.06) if is_t2 else (nx, ny)
            if "staminup" in style:
                sym = (abs(sy + sx * 0.55) < 0.14 and -0.45 < sx < 0.42) or (sx > 0.05 and abs(sy - (0.38 - sx)) < 0.12)
            elif "mulekick" in style:
                sym = (-0.44 < sx < 0.44) and (abs(sy + 0.26) < 0.09 or abs(sy) < 0.09 or abs(sy - 0.26) < 0.09)
            elif "armorpiercing" in style:
                sym = (abs(sx) < 0.38 and abs(sy + 0.28 - abs(sx) * 0.9) < 0.11) or (abs(sx) < 0.12 and -0.18 < sy < 0.44)
            elif "jugg" in style:
                sym = (abs(sx) < 0.15 and -0.44 < sy < 0.40) or (abs(sx) < 0.42 and -0.15 < sy < 0.15)
            elif "speed" in style:
                sym = (abs(sx + 0.16) < 0.14 and -0.42 < sy < 0.42) or (abs(sx - 0.18) < 0.10 and -0.34 < sy < 0.34)
            elif "dtap" in style:
                sym = (abs(sx + 0.20) < 0.11 and -0.42 < sy < 0.42) or (abs(sx - 0.20) < 0.11 and -0.42 < sy < 0.42)
            elif "revive" in style:
                sym = (abs(sx) < 0.13 and -0.44 < sy < 0.44) or (abs(sx) < 0.44 and -0.13 < sy < 0.13)
            if sym:
                return (248, 246, 238, 255) if is_t2 else (ar, ag, ab, 255)
            return (br, bg, bb, 255)

        if is_apex:
            # Circular antique-bronze Apex medallion
            dist = math.hypot(nx, ny)
            if dist > 0.90:
                return (0, 0, 0, 0)
            if dist > 0.80:
                return (28, 20, 14, 255)
            if dist > 0.68:
                return (188, 144, 74, 255)
            if dist > 0.62:
                return (46, 32, 18, 255)
            sym = False
            if style == "hud_apex_dblammo":
                sym = (abs(nx + 0.18) < 0.10 and -0.36 < ny < 0.36) or (abs(nx - 0.18) < 0.10 and -0.36 < ny < 0.36) or (abs(ny - 0.26) < 0.08 and ax < 0.34)
            elif style == "hud_apex_lightheavy":
                sym = (abs(ny + 0.24 - ax * 0.7) < 0.10 and ax < 0.44) or (abs(ny - 0.18) < 0.10 and ax < 0.38)
            elif style == "hud_apex_secondchance":
                sym = (dist < 0.20) or (ax < 0.08 and ay < 0.46) or (ay < 0.08 and ax < 0.46) or (abs(ax - ay) < 0.08 and dist < 0.44)
            elif style == "hud_apex_blastshield":
                sym = (abs(dist - 0.36) < 0.10 and ny < 0.20) or (ax < 0.12 and -0.22 < ny < 0.36)
            if sym:
                return (ar, ag, ab, 255)
            return (br, bg, bb, 255)

        if is_diamond:
            # Brushed-steel Double-PaP "II" diamond (zero violet!)
            man = ax + ay
            if man > 0.92:
                return (0, 0, 0, 0)
            if man > 0.82:
                return (20, 24, 28, 255)
            if man > 0.70:
                return (146, 154, 164, 255)
            if man > 0.62:
                return (ar, ag, ab, 255)
            # Bold centered Roman "II" in warm gold #ffdc82
            bar1 = (-0.24 <= nx <= -0.09) and (-0.32 <= ny <= 0.32)
            bar2 = (0.09 <= nx <= 0.24) and (-0.32 <= ny <= 0.32)
            caps = (-0.30 <= nx <= 0.30) and ((-0.34 <= ny <= -0.24) or (0.24 <= ny <= 0.34))
            if bar1 or bar2 or caps:
                return (ar, ag, ab, 255)
            return (br, bg, bb, 255)

        return (br, bg, bb, 255)

    for y in range(size):
        for x in range(size):
            # 2x2 supersampling for crisp anti-aliased silhouettes
            sr_t = sg_t = sb_t = sa_t = 0
            for sy in (0.25, 0.75):
                for sx in (0.25, 0.75):
                    nx = ((x + sx) / size) * 2.0 - 1.0
                    ny = ((y + sy) / size) * 2.0 - 1.0
                    r, g, b, a = _sample(nx, ny)
                    sr_t += r * a
                    sg_t += g * a
                    sb_t += b * a
                    sa_t += a
            off = (y * size + x) * 4
            if sa_t > 0:
                buf[off + 0] = clamp255(sr_t / sa_t)
                buf[off + 1] = clamp255(sg_t / sa_t)
                buf[off + 2] = clamp255(sb_t / sa_t)
                buf[off + 3] = clamp255(sa_t / 4.0)
            else:
                buf[off + 0] = 0
                buf[off + 1] = 0
                buf[off + 2] = 0
                buf[off + 3] = 0
    return buf


_FBM_CACHE: dict[tuple[int, int], list[float]] = {}


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def _get_tile_fbm(size: int, seed: int) -> list[float]:
    """Deterministic seamlessly tileable 3-octave smooth bilinear value-noise fBm in [0, 1]."""
    key = (size, seed)
    cached = _FBM_CACHE.get(key)
    if cached is not None:
        return cached
    out = [0.0] * (size * size)
    # 3 octaves: coarse (4 cells), mid (12 cells), fine (32 cells), clamped to <= size
    octaves = (
        (min(4, max(2, size // 4)), 0.52, seed * 17 + 1),
        (min(12, max(2, size // 2)), 0.31, seed * 31 + 7),
        (min(32, max(2, size)), 0.17, seed * 53 + 19),
    )
    for freq, amp, oseed in octaves:
        grid = [_hash2((gx % freq) + oseed * 97, (gy % freq) + oseed * 193) for gy in range(freq) for gx in range(freq)]
        xs = [(x * freq) / size for x in range(size)]
        x0s = [int(fx) % freq for fx in xs]
        x1s = [(ix + 1) % freq for ix in x0s]
        txs = [_smoothstep(fx - int(fx)) for fx in xs]
        for y in range(size):
            fy = (y * freq) / size
            y0 = int(fy) % freq
            y1 = (y0 + 1) % freq
            ty = _smoothstep(fy - int(fy))
            r0 = y0 * freq
            r1 = y1 * freq
            row_off = y * size
            for x in range(size):
                ix0, ix1, tx = x0s[x], x1s[x], txs[x]
                a = grid[r0 + ix0] * (1.0 - tx) + grid[r0 + ix1] * tx
                b = grid[r1 + ix0] * (1.0 - tx) + grid[r1 + ix1] * tx
                out[row_off + x] += (a * (1.0 - ty) + b * ty) * amp
    _FBM_CACHE[key] = out
    return out


# ---------------------------------------------------------------------------
# Smooth Anti-Aliased Vector SDF 1945 Wehrmacht DIN Stencil Renderer ("935" & "AETZEND")
# ---------------------------------------------------------------------------


def _sd_seg(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    denom = vx * vx + vy * vy
    t = clamp01((wx * vx + wy * vy) / denom) if denom > 1e-8 else 0.0
    dx, dy = wx - vx * t, wy - vy * t
    return math.hypot(dx, dy)


def _sd_arc_ellipse(px: float, py: float, cx: float, cy: float, rx: float, ry: float, a0: float, a1: float) -> float:
    """Signed distance to an elliptical stroke arc from angle a0 to a1 (radians, 0=+X, +pi/2=+Y)."""
    # Map point to normalized circle space to find nearest parameter, then measure true distance
    nx = (px - cx) / max(rx, 1e-5)
    ny = (py - cy) / max(ry, 1e-5)
    ang = math.atan2(ny, nx)
    # Unwrap angle into [a0, a1]
    two_pi = math.tau
    while ang < a0 - math.pi:
        ang += two_pi
    while ang > a1 + math.pi:
        ang -= two_pi
    best = min(max(ang, a0), a1)
    qx = cx + math.cos(best) * rx
    qy = cy + math.sin(best) * ry
    return math.hypot(px - qx, py - qy)


def _sdf_din_digit(ch: str, lx: float, ly: float) -> float:
    """Signed distance (negative inside) for crisp 1945 Wehrmacht DIN stencil digits '9','3','5' in [0,1]x[0,1]."""
    stroke = 0.095
    if ch == "9":
        # Upper rounded oval bowl + right stem sweeping down into lower hook, with stencil bridges!
        d = min(
            _sd_arc_ellipse(lx, ly, 0.48, 0.30, 0.33, 0.22, math.radians(-165.0), math.radians(175.0)),
            _sd_seg(lx, ly, 0.80, 0.30, 0.80, 0.72),
            _sd_arc_ellipse(lx, ly, 0.48, 0.72, 0.32, 0.20, math.radians(0.0), math.radians(155.0)),
        ) - stroke
        # Stencil bridge gaps at left-top of bowl & right waist
        if (0.44 < lx < 0.52 and ly < 0.14) or (0.70 < lx < 0.92 and 0.48 < ly < 0.55):
            return 0.06
        return d
    if ch == "3":
        # Twin DIN stencil arcs with crisp center waist bridge
        d = min(
            _sd_arc_ellipse(lx, ly, 0.46, 0.28, 0.34, 0.20, math.radians(-155.0), math.radians(78.0)),
            _sd_arc_ellipse(lx, ly, 0.46, 0.72, 0.35, 0.20, math.radians(-78.0), math.radians(160.0)),
            _sd_seg(lx, ly, 0.36, 0.50, 0.64, 0.50),
        ) - stroke
        if 0.64 < lx < 0.88 and 0.45 < ly < 0.55:
            return 0.06
        return d
    if ch == "5":
        # Crisp DIN flat top bar + vertical drop + rounded lower belly with stencil bridge
        d = min(
            _sd_seg(lx, ly, 0.20, 0.10, 0.82, 0.10),
            _sd_seg(lx, ly, 0.20, 0.10, 0.20, 0.46),
            _sd_seg(lx, ly, 0.20, 0.46, 0.52, 0.46),
            _sd_arc_ellipse(lx, ly, 0.48, 0.69, 0.34, 0.22, math.radians(-82.0), math.radians(165.0)),
        ) - stroke
        if 0.12 < lx < 0.30 and 0.26 < ly < 0.33:
            return 0.06
        return d
    return 1.0


def _sample_935_stencil_alpha(u: float, v: float, pixel_step: float) -> float:
    """Return smooth anti-aliased [0,1] stencil coverage for '935' at UV (u,v) (ZERO blocky 5x7 pixels!)."""
    if not (0.16 <= v <= 0.74 and 0.10 <= u <= 0.90):
        return 0.0
    # 3 digit slots across u in [0.12..0.88] -> slot width 0.253 (digit 0.215 + gap 0.038)
    rel_u = (u - 0.12) / 0.253
    g_idx = int(rel_u)
    if g_idx < 0 or g_idx > 2:
        return 0.0
    lu = (rel_u - g_idx) / 0.85
    if lu < -0.05 or lu > 1.05:
        return 0.0
    lv = (v - 0.18) / 0.54
    if lv < -0.05 or lv > 1.05:
        return 0.0
    ch = "935"[g_idx]
    d = _sdf_din_digit(ch, lu, lv)
    aa = max(pixel_step * 4.5, 0.014)
    return clamp01(0.5 - d / aa)


def _sdf_stencil_letter(ch: str, lx: float, ly: float) -> float:
    """Vector SDF stroke glyph for 'A','E','T','Z','N','D' (AETZEND tank stencil)."""
    w = 0.11
    segs: tuple[tuple[float, float, float, float], ...]
    if ch == "A":
        segs = ((0.14, 0.92, 0.50, 0.08), (0.86, 0.92, 0.50, 0.08), (0.28, 0.62, 0.72, 0.62))
    elif ch == "E":
        segs = ((0.18, 0.10, 0.18, 0.90), (0.26, 0.10, 0.84, 0.10), (0.26, 0.50, 0.72, 0.50), (0.26, 0.90, 0.84, 0.90))
    elif ch == "T":
        segs = ((0.12, 0.10, 0.88, 0.10), (0.50, 0.16, 0.50, 0.90))
    elif ch == "Z":
        segs = ((0.16, 0.10, 0.84, 0.10), (0.84, 0.10, 0.16, 0.90), (0.16, 0.90, 0.84, 0.90))
    elif ch == "N":
        segs = ((0.16, 0.90, 0.16, 0.10), (0.16, 0.10, 0.84, 0.90), (0.84, 0.90, 0.84, 0.10))
    elif ch == "D":
        d_arc = _sd_arc_ellipse(lx, ly, 0.42, 0.50, 0.40, 0.40, math.radians(-90.0), math.radians(90.0))
        d_stem = _sd_seg(lx, ly, 0.18, 0.10, 0.18, 0.90)
        d_top = _sd_seg(lx, ly, 0.18, 0.10, 0.42, 0.10)
        d_bot = _sd_seg(lx, ly, 0.18, 0.90, 0.42, 0.90)
        return min(d_arc, d_stem, d_top, d_bot) - w
    else:
        return 1.0
    return min(_sd_seg(lx, ly, a, b, c, d) for a, b, c, d in segs) - w


def _sample_aetzend_alpha(u: float, v: float, pixel_step: float) -> float:
    """Return smooth anti-aliased axial stencil coverage for 'AETZEND' along V inside strap-free top tank bay (A8/S8/G9!)."""
    # Tank cylinder maps U around circumference (u=0.00 outboard +Y, u=0.25 top +Z) and V along tank length (0..0.88).
    # Orient 'AETZEND' cleanly along the strap-free central top-outboard bay (v=0.30..0.72, u=0.09..0.26) facing the 1P eye!
    if not (0.30 <= v <= 0.72 and 0.09 <= u <= 0.26):
        return 0.0
    word = "AETZEND"
    slot = (0.72 - 0.30) / len(word)
    rel = (v - 0.30) / slot
    idx = int(rel)
    if idx < 0 or idx >= len(word):
        return 0.0
    lx = (rel - idx) / 0.84
    if lx < -0.05 or lx > 1.05:
        return 0.0
    ly = (0.26 - u) / (0.26 - 0.09)
    d = _sdf_stencil_letter(word[idx], lx, ly)
    return clamp01(0.5 - d / max(pixel_step * 8.0, 0.022))


def generate_material_textures(spec: MaterialSpec, tex_dir: Path, size: int = DEFAULT_TEX_SIZE) -> dict[str, str]:
    """Generate deterministic 32-bit TGA textures for one material; return relative asset paths."""
    if spec.material_type == "2d":
        stem = spec.name.removeprefix("mtl_")
        c_file = tex_dir / f"{stem}_c.tga"
        icon_size = min(size, 64)
        write_tga_rgba(c_file, icon_size, icon_size, _render_hud_icon_64(spec, size=icon_size))
        return {"colorMap": f"texture_assets\\\\{ASSET_SUBDIR}\\\\{c_file.name}"}

    color_buf = bytearray(size * size * 4)
    spec_buf = bytearray(size * size * 4)
    gloss_buf = bytearray(size * size * 4)
    hmap = [0.5] * (size * size)

    br, bg, bb = spec.base_rgb
    ar, ag, ab = spec.accent_rgb
    sr, sg, sb = spec.spec_rgb
    gl = spec.gloss
    style = spec.style

    fbm_a = _get_tile_fbm(size, 1)
    fbm_b = _get_tile_fbm(size, 2)
    fbm_c = _get_tile_fbm(size, 3)
    inv_size = 1.0 / size

    for y in range(size):
        v = y * inv_size
        row_off = y * size
        for x in range(size):
            u = x * inv_size
            idx = row_off + x
            na = fbm_a[idx]          # smooth [0, 1] organic mottling
            nb = fbm_b[idx]          # secondary organic noise
            nc = fbm_c[idx]          # tertiary wear mask
            n_fine = _hash2(x, y) - 0.5
            mix = 0.0
            shade = 1.0
            h = 0.5 + (na - 0.5) * 0.14 + n_fine * 0.04
            spec_mult = 1.0

            if style == "wintertarnung":
                # Coherent hand-brushed 1945 Wintertarnung whitewash (~30% chalky wash streaks over Panzergrau steel! A9/S8)
                bx = (x // 2) % size
                by = (y * 2) % size
                brush = fbm_b[by * size + bx]
                edge_d = min(u, 1.0 - u, v, 1.0 - v)
                wash_field = na * 0.52 + brush * 0.48
                if wash_field > 0.46:
                    wash = clamp01((wash_field - 0.46) * 4.4) * (0.80 + 0.20 * nc)
                else:
                    wash = 0.0
                # Edge scuffing / worn gunmetal scratches along panel edges
                edge_chip = 1.0 if (edge_d < 0.045 and nb > 0.46) else 0.0
                scratch = 1.0 if (nb > 0.76 and abs(na - 0.50) < 0.045) else 0.0
                mix = clamp01(wash * 0.94 + edge_chip * 0.45 + scratch * 0.30)
                shade = 0.90 + 0.20 * nc
                h = 0.48 + wash * 0.16 + (na - 0.5) * 0.10 + n_fine * 0.04
                spec_mult = (0.50 if wash > 0.45 else 1.04) + scratch * 0.22
            elif style == "acid_enamel":
                # Olivgruen chemical reagent tank w/ world-aspect-corrected circular Gruenkreuz + strap-free axial SDF "AETZEND" (A8/S8/G9!)
                grime = clamp01((0.46 - na) * 2.2)
                streak = fbm_c[((y // 3) % size) * size + x]
                # Tank circumference = 2*pi*1.28 = 8.04u per U, length = 12.5u per V -> scale (du*8.04, dv*12.5) for true circular emblem!
                # Primary Gruenkreuz in foreground top-outboard bay (u=0.19, v=0.20 -> x=3.3u, clear of x=1.65 strap!) + secondary outer flank (0.90, 0.48)
                in_cross = False
                cross_ring = False
                for cu, cv in ((0.19, 0.20), (0.90, 0.48)):
                    du_w = abs(u - cu) * 8.04
                    dv_w = abs(v - cv) * 12.50
                    if (du_w < 0.13 and dv_w < 0.46) or (dv_w < 0.13 and du_w < 0.46):
                        in_cross = True
                    if abs(math.hypot(du_w, dv_w) - 0.56) < 0.09:
                        cross_ring = True
                # Axial SDF "AETZEND" lettering running along strap-free central top bay (v=0.30..0.72, u=0.09..0.26)
                txt_a = _sample_aetzend_alpha(u, v, inv_size)
                mark_a = max(txt_a, 1.0 if (in_cross or cross_ring) else 0.0)
                chip_f = clamp01(0.86 + (na - 0.35) * 0.40)
                if mark_a > 0.05:
                    mix = mark_a * 0.96 * chip_f
                    shade = 1.04 + 0.06 * nb
                    h = 0.64
                    spec_mult = 0.70
                else:
                    mix = clamp01(0.06 + (streak - 0.5) * 0.14)
                    shade = 0.86 + 0.24 * na - grime * 0.16
                    h = 0.52 - grime * 0.08 + n_fine * 0.04
                    spec_mult = 0.84 - grime * 0.20
            elif style == "olivgruen_enamel":
                # Authentic weathered 1945 Wehrmacht Olivgruen enamel w/ chipped steel edge highlights & oil patina
                grime = clamp01((0.46 - na) * 2.0)
                edge_d = min(u, 1.0 - u, v, 1.0 - v)
                edge_wear = clamp01((0.042 - edge_d) / 0.042) * clamp01((nb - 0.30) * 2.4)
                chip = clamp01((nb - 0.74) * 4.2) * (0.5 + 0.5 * nc)
                streak = fbm_c[((y // 3) % size) * size + x]
                mix = clamp01(0.14 + chip * 0.65 + edge_wear * 0.68 + (streak - 0.5) * 0.18)
                shade = 0.88 + 0.22 * na - grime * 0.16 + edge_wear * 0.14
                h = 0.52 - grime * 0.08 - chip * 0.18 + n_fine * 0.04
                spec_mult = 0.82 - grime * 0.20 + (chip + edge_wear) * 0.34
            elif style == "panel_metal":
                # Weathered cast-iron / Panzergrau armor plate w/ baked edge wear, recessed perimeter seam & rivets (F13/O11)
                streak = fbm_b[((y // 4) % size) * size + x]
                wear = clamp01((nc - 0.62) * 2.6)
                edge_d = min(u, 1.0 - u, v, 1.0 - v)
                seam = edge_d < 0.009
                bevel_hi = (0.009 <= edge_d < 0.026) and (nb > 0.34)
                rivet_hit = False
                if 0.028 < edge_d < 0.062:
                    for rv in (0.08, 0.25, 0.50, 0.75, 0.92):
                        if math.hypot(u - rv, v - 0.044) < 0.013 or math.hypot(u - rv, v - 0.956) < 0.013:
                            rivet_hit = True
                            break
                        if math.hypot(u - 0.044, v - rv) < 0.013 or math.hypot(u - 0.956, v - rv) < 0.013:
                            rivet_hit = True
                            break
                if seam:
                    mix = 0.0
                    shade = 0.46
                    h = 0.14
                    spec_mult = 0.32
                elif rivet_hit:
                    mix = 0.78
                    shade = 1.14
                    h = 0.92
                    spec_mult = 1.20
                elif bevel_hi:
                    mix = 0.58 + 0.25 * nc
                    shade = 1.08
                    h = 0.70
                    spec_mult = 1.12
                else:
                    mix = clamp01(0.10 + wear * 0.58 + (streak - 0.5) * 0.20)
                    shade = 0.84 + 0.28 * na
                    h = 0.50 + (na - 0.5) * 0.22 + (nb - 0.5) * 0.12 + n_fine * 0.05
                    spec_mult = 0.86 + wear * 0.30
            elif style == "forged_iron":
                # Dark forged parkerized cast iron with hammered micro-pitting & crisp burnished edge wear
                edge_d = min(u, 1.0 - u, v, 1.0 - v)
                edge_hi = clamp01((0.032 - edge_d) / 0.032) * clamp01((nb - 0.35) * 2.5)
                pit = (na - 0.5) * 0.34 + (nb - 0.5) * 0.20
                burnish = clamp01((nc - 0.58) * 2.5)
                mix = clamp01(0.12 + burnish * 0.56 + edge_hi * 0.52)
                shade = 0.86 + 0.26 * na + edge_hi * 0.16
                h = 0.50 + pit + n_fine * 0.06
                spec_mult = 0.88 + burnish * 0.32 + edge_hi * 0.24
            elif style == "kiosk_plate_935":
                # Heavy riveted steel faceplate with smooth vector SDF 1945 DIN stenciled "935" & crisp upward wing bar (A5/S5/G2/F4/O9!)
                edge_d = min(u, 1.0 - u, v, 1.0 - v)
                border = edge_d < 0.042
                bevel_lip = (0.042 <= edge_d < 0.058)
                rivet = (
                    math.hypot(u - 0.08, v - 0.10) < 0.024
                    or math.hypot(u - 0.92, v - 0.10) < 0.024
                    or math.hypot(u - 0.08, v - 0.90) < 0.024
                    or math.hypot(u - 0.92, v - 0.90) < 0.024
                )
                stencil_a = _sample_935_stencil_alpha(u, v, inv_size)
                # Crisp split horizontal divider bar below "935" (zero curved frown bar! O9/F27)
                bar_a = 1.0 if ((0.81 <= v <= 0.855) and (0.18 <= u <= 0.82) and abs(u - 0.50) > 0.03) else 0.0
                if border:
                    mix = 0.0
                    shade = 0.54 + 0.14 * na
                    h = 0.24
                    spec_mult = 0.55
                elif bevel_lip:
                    mix = 0.35
                    shade = 1.06
                    h = 0.72
                    spec_mult = 1.08
                elif rivet:
                    mix = 0.55
                    shade = 1.14
                    h = 0.92
                    spec_mult = 1.18
                elif stencil_a > 0.04 or bar_a > 0.04:
                    # Weathered stenciled paint w/ subtle organic chipping & crisp embossed edge height!
                    cov = max(stencil_a, bar_a * 0.72)
                    chip_f = clamp01(0.78 + (na - 0.32) * 0.55)
                    mix = cov * 0.90 * chip_f
                    shade = 0.98 + 0.08 * nb
                    h = 0.52 + cov * 0.24
                    spec_mult = 0.86 + cov * 0.20
                else:
                    mix = clamp01(0.06 + max(0.0, nc - 0.62) * 0.36)
                    shade = 0.84 + 0.24 * na
                    h = 0.50 + (na - 0.5) * 0.18 + n_fine * 0.04
                    spec_mult = 0.92
            elif style == "brushed_metal":
                # Anisotropic fine brushed gunmetal / WWII propeller steel / weathered brass
                bx = (x // 8) % size
                streak = fbm_b[y * size + bx]
                fine_line = fbm_c[y * size + ((x // 4) % size)]
                patina = clamp01((0.48 - na) * 1.9)
                mix = clamp01(0.14 + (streak - 0.5) * 0.36 + patina * 0.32)
                shade = 0.84 + 0.26 * streak - patina * 0.18
                h = 0.50 + (fine_line - 0.5) * 0.22 + (streak - 0.5) * 0.14 + n_fine * 0.04
                spec_mult = 1.08 - patina * 0.32
            elif style == "wood_grain":
                # Smooth oiled WWII walnut aligned LENGTHWISE along V (tapered prism axial coordinate! A10)
                wy = (y // 7) % size
                warp = int((na - 0.5) * size * 0.07)
                wx = (x + warp) % size
                fiber_hi = fbm_c[wy * size + wx]
                fiber_lo = fbm_b[(y // 11) % size * size + ((wx * 2) % size)]
                pore = 1.0 if (fiber_hi < 0.22 and n_fine < -0.25) else 0.0
                mix = clamp01(0.16 + fiber_lo * 0.44 + fiber_hi * 0.22 + pore * 0.14)
                shade = 0.84 + 0.28 * (1.0 - fiber_lo) - pore * 0.14
                h = 0.52 + (fiber_lo - 0.5) * 0.18 - pore * 0.14 + n_fine * 0.03
                spec_mult = 0.84 + (1.0 - fiber_lo) * 0.24 - pore * 0.22
            elif style == "leather":
                # Diagonal wrapped stitched leather strips w/ pebbled hide grain & dark stitch seams
                diag = (u * 5.0 + v * 5.0) % 1.0
                seam = diag < 0.065
                stitch = (0.09 < diag < 0.14) and (((u * 26.0 - v * 26.0) % 1.0) < 0.42)
                pebble = (nb - 0.5) * 0.32 + (nc - 0.5) * 0.18
                if seam:
                    mix = 0.88
                    shade = 0.55
                    h = 0.16
                    spec_mult = 0.35
                elif stitch:
                    mix = 0.12
                    shade = 1.12
                    h = 0.78
                    spec_mult = 0.75
                else:
                    mix = clamp01(0.28 + pebble + (na - 0.5) * 0.25)
                    shade = 0.84 + 0.24 * na
                    h = 0.56 + pebble * 0.45 + n_fine * 0.05
                    spec_mult = 0.86
            elif style == "corroded_metal":
                # Hammered blackened WWII trench-mace iron w/ organic peen dimples & burnished high ridges
                dimple = fbm_a[((y * 2) % size) * size + ((x * 2) % size)]
                ridge = clamp01((dimple - 0.58) * 2.8)
                soot = clamp01((0.40 - nb) * 2.4)
                mix = clamp01(0.14 + ridge * 0.62)
                shade = 0.78 + 0.34 * dimple - soot * 0.26
                h = 0.48 + (dimple - 0.5) * 0.42 - soot * 0.12 + n_fine * 0.05
                spec_mult = 0.90 + ridge * 0.36 - soot * 0.32
            elif style == "pap1_etched":
                # Stage 1 PaP: darkened blued steel (#252a32) w/ restrained geometric oxidized brass filigree (<=15%)
                gx = (x * 4) % size
                gy = (y * 4) % size
                fu = gx * inv_size
                fv = gy * inv_size
                d_diag1 = abs((fu + fv) - 1.0)
                d_diag2 = abs(fu - fv)
                in_cell = 0.14 < fu < 0.86 and 0.14 < fv < 0.86
                border = fu < 0.03 or fv < 0.03
                etch = in_cell and (d_diag1 < 0.045 or d_diag2 < 0.045)
                if border:
                    mix = 0.0
                    shade = 0.58
                    h = 0.24
                    spec_mult = 0.48
                elif etch:
                    mix = 0.84
                    shade = 0.94 + 0.12 * na
                    h = 0.80
                    spec_mult = 1.18
                else:
                    mix = clamp01(0.05 + (na - 0.5) * 0.08)
                    shade = 0.84 + 0.24 * nb
                    h = 0.50 + (na - 0.5) * 0.14 + n_fine * 0.04
                    spec_mult = 0.94
            elif style == "pap2_crystalline":
                # Stage 2 PaP: obsidian gunmetal (#191d22) w/ neutral brushed-steel crystalline facet relief
                fu = ((u * 6.0) % 1.0) - 0.5
                fv = ((v * 6.0) % 1.0) - 0.5
                diamond = abs(fu) + abs(fv)
                ridge = (0.36 <= diamond <= 0.41) or (abs(fu) < 0.025 and diamond < 0.37) or (abs(fv) < 0.025 and diamond < 0.37)
                facet_hi = diamond < 0.37 and (fu + fv) > 0.08
                if ridge:
                    mix = 0.78
                    shade = 1.04
                    h = 0.86
                    spec_mult = 1.20
                elif facet_hi:
                    mix = 0.26
                    shade = 0.96 + 0.12 * na
                    h = 0.64
                    spec_mult = 1.06
                else:
                    mix = clamp01(0.06 + (nb - 0.5) * 0.08)
                    shade = 0.82 + 0.22 * na
                    h = 0.42 + (na - 0.5) * 0.12 + n_fine * 0.04
                    spec_mult = 0.88
            elif style == "kiosk_perks_serum":
                # Deep moody Group 935 emerald serum inside recessed armored sight-tube (vignetted edges + meniscus + graduations)
                du = abs(u - 0.5) * 2.0
                dv = abs(v - 0.5) * 2.0
                cyl_shade = clamp01(1.0 - du * du * 0.82)
                top_meniscus = 1.0 if (0.14 <= v <= 0.17) else 0.0
                above_liq = v < 0.14
                tick = (du > 0.45) and ((y % max(8, size // 12)) < max(1, size // 128))
                if above_liq:
                    mix = 0.0
                    shade = 0.18 + 0.10 * cyl_shade
                elif tick:
                    mix = 0.05
                    shade = 0.28
                else:
                    bubble = clamp01((na - 0.62) * 2.4) * 0.35
                    mix = clamp01(cyl_shade * 0.48 + bubble + top_meniscus * 0.45)
                    shade = (0.24 + 0.68 * cyl_shade) * clamp01(1.0 - dv * dv * 0.35)
            elif style == "kiosk_class_map":
                # Authentic 1945 Group 935 frosted topographical tactical map-glass (contour isolines, river, sector pins, ZERO crosshair! G4/F20/O12)
                du = abs(u - 0.5) * 2.0
                dv = abs(v - 0.5) * 2.0
                rad = math.hypot(du, dv)
                bezel = du > 0.91 or dv > 0.91
                # Subtle coordinate grid + margin tick marks
                grid = (abs(((u * 6.0) % 1.0) - 0.5) > 0.472) or (abs(((v * 4.0) % 1.0) - 0.5) > 0.472)
                # Topographical elevation contour lines from smooth fBm height field
                elev = na * 0.72 + nb * 0.28
                contour = abs((elev * 7.5) % 1.0 - 0.5) < 0.055
                # Winding map river/canal running diagonally across sheet
                river_y = 0.24 + 0.52 * u + 0.09 * math.sin(u * math.tau * 1.4)
                river = abs(v - river_y) < 0.022
                # Pencil triangulation lines between 3 tactical facility sector pins
                p1, p2, p3 = (0.28, 0.36), (0.68, 0.30), (0.52, 0.70)
                tri_line = (
                    _sd_seg(u, v, p1[0], p1[1], p2[0], p2[1]) < 0.0055
                    or _sd_seg(u, v, p2[0], p2[1], p3[0], p3[1]) < 0.0055
                    or _sd_seg(u, v, p3[0], p3[1], p1[0], p1[1]) < 0.0055
                )
                pin = any(math.hypot(u - px, v - py) < 0.026 for px, py in (p1, p2, p3))
                pin_ring = any(abs(math.hypot(u - px, v - py) - 0.044) < 0.008 for px, py in (p1, p2, p3))
                vignette = clamp01(1.0 - rad * rad * 0.48)
                if bezel:
                    mix = 0.0
                    shade = 0.16
                elif pin or pin_ring:
                    mix = 0.92
                    shade = 0.86 * vignette
                elif river:
                    mix = 0.08
                    shade = 0.26 * vignette
                elif contour or tri_line:
                    mix = 0.62
                    shade = 0.72 * vignette
                elif grid:
                    mix = 0.32
                    shade = 0.56 * vignette
                else:
                    mix = clamp01(0.12 + vignette * 0.22 + (na - 0.5) * 0.14)
                    shade = 0.34 + 0.34 * vignette
            elif style == "kiosk_arsenal_pegboard":
                # Warm deep-amber backlit armorer's perforated pegboard (bloom-capped shade <= 0.72 so it stays rich amber, NEVER cream! F12)
                du = abs(u - 0.5) * 2.0
                dv = abs(v - 0.5) * 2.0
                vignette = clamp01(1.0 - (du * du * 0.56 + dv * dv * 0.62))
                pu = ((u * 16.0) % 1.0) - 0.5
                pv = ((v * 12.0) % 1.0) - 0.5
                hole = math.hypot(pu, pv) < 0.20
                frame_shadow = du > 0.92 or dv > 0.90
                if frame_shadow:
                    mix = 0.0
                    shade = 0.16
                elif hole:
                    mix = 0.0
                    shade = 0.18 * (0.45 + 0.55 * vignette)
                else:
                    mix = clamp01(0.10 + vignette * 0.36 + (na - 0.5) * 0.08)
                    shade = 0.28 + 0.42 * vignette
            elif style == "kiosk_pap_slit":
                # Deep moody recessed Group 935 violet plasma slit (steep dark top/bottom mechanical shadow -> zero neon slab!)
                du = abs(u - 0.5) * 2.0
                dv = abs(v - 0.5) * 2.0
                core_v = clamp01(1.0 - dv * 1.15)
                core_u = clamp01(1.0 - du * du * 0.55)
                arc = clamp01(0.5 + 0.5 * math.sin(u * math.tau * 5.0 + (na - 0.5) * 4.0))
                intensity = (core_v * core_v) * core_u
                mix = clamp01(intensity * (0.45 + 0.45 * arc))
                shade = 0.12 + 0.84 * intensity
            elif style == "solenoid_coil":
                # Wound copper kinetic solenoid wire coils glowing deep forge red-orange between dark wire wraps!
                wrap = math.sin(v * math.tau * 18.0) * 0.5 + 0.5
                du = abs(u - 0.5) * 2.0
                edge_shadow = clamp01(1.0 - du * du * 0.55)
                if wrap < 0.32:
                    # Dark oxidized copper wire gap shadow
                    mix = 0.0
                    shade = 0.22 * edge_shadow
                else:
                    mix = clamp01((wrap - 0.32) * 1.15 * edge_shadow)
                    shade = (0.48 + 0.50 * wrap) * edge_shadow
            elif style == "portal_glow":
                # Dark faceted obsidian-violet Element-115 mineral crystal w/ glowing #8e22da energy fracture veins!
                vein1 = abs(na - 0.50)
                vein2 = abs(nb - 0.52)
                crack = clamp01(1.0 - min(vein1, vein2) * 14.0)
                facet = 0.22 + 0.26 * nc
                mix = clamp01(crack * 0.92 + facet * 0.22)
                shade = 0.32 + 0.68 * crack + 0.14 * nc
            elif style in ("cryo_glow", "acid_glow", "amber_glow", "crimson_glow"):
                # Recessed armored sight-slit / glowing core w/ dark edge vignette (bloom-safe crimson cap <= 0.78! F12)
                du = abs(u - 0.5) * 2.0
                dv = abs(v - 0.5) * 2.0
                edge_v = clamp01(1.0 - max(du, dv) ** 3 * 0.58)
                if style == "crimson_glow":
                    mix = clamp01(0.18 + na * 0.28)
                    shade = 0.48 + 0.30 * edge_v
                else:
                    mix = clamp01(0.24 + na * 0.46 + (nb - 0.5) * 0.20)
                    shade = 0.56 + 0.44 * edge_v
            elif style in ("acid_stream", "acid_billow", "acid_drips", "acid_mist"):
                # Alpha-feathered 2D chemical stream/cloud/droplet sprites for FLAMETABLEFILE
                du = (u - 0.5) * 2.0
                dv = (v - 0.5) * 2.0
                r_dist = math.sqrt(du * du + dv * dv)
                if style == "acid_stream":
                    core = clamp01(1.0 - abs(dv) * 1.15)
                    streak = 0.65 + 0.35 * math.sin(u * math.tau * 5.0 + dv * 3.0)
                    alpha_f = (core * core) * clamp01(streak + (na - 0.5) * 0.30)
                    mix = clamp01(core * 0.85)
                elif style == "acid_billow":
                    radial = clamp01(1.0 - r_dist)
                    swirl = 0.6 + 0.4 * math.sin((u * 3.0 + v * 2.0) * math.tau + (na - 0.5) * 3.0)
                    alpha_f = (radial * radial) * swirl
                    mix = clamp01(radial * 0.90)
                elif style == "acid_drips":
                    radial = clamp01(1.0 - r_dist * 1.05)
                    drop = max(0.0, math.sin(u * math.tau * 4.0) * math.sin(v * math.tau * 4.0))
                    alpha_f = clamp01((radial * radial) * (0.45 + 0.75 * drop))
                    mix = clamp01(0.45 + 0.55 * drop)
                else:
                    radial = clamp01(1.0 - r_dist)
                    alpha_f = (radial * radial) * (0.42 + 0.22 * math.cos((u - v) * math.tau * 2.0))
                    mix = clamp01(radial * 0.65)
                r_c = clamp255(br * (1.0 - mix) + ar * mix)
                g_c = clamp255(bg * (1.0 - mix) + ag * mix)
                b_c = clamp255(bb * (1.0 - mix) + ab * mix)
                a_c = clamp255(alpha_f * 255.0)
                if spec.blend_func == "Add":
                    r_c = clamp255(r_c * alpha_f)
                    g_c = clamp255(g_c * alpha_f)
                    b_c = clamp255(b_c * alpha_f)
                off = idx * 4
                color_buf[off + 0] = r_c
                color_buf[off + 1] = g_c
                color_buf[off + 2] = b_c
                color_buf[off + 3] = a_c
                continue

            r = clamp255((br * (1.0 - mix) + ar * mix) * shade + n_fine * 7.0)
            g = clamp255((bg * (1.0 - mix) + ag * mix) * shade + n_fine * 7.0)
            b = clamp255((bb * (1.0 - mix) + ab * mix) * shade + n_fine * 7.0)
            if style == "wintertarnung":
                # Keep emitted Cryo Wintertarnung whitewash strictly <= 185 per NORTHSTAR_SPEC palette cap (S16!)
                r = min(r, 185)
                g = min(g, 185)
                b = min(b, 185)
            off = idx * 4
            color_buf[off + 0] = r
            color_buf[off + 1] = g
            color_buf[off + 2] = b
            color_buf[off + 3] = 255
            hmap[idx] = h

            # Enforce calibrated WaW specular pixel ceiling AFTER style multiplier (<=74 PaP, <=78 general! A13/S13)
            spec_cap = 74.0 if ("_pap1" in spec.name or "_pap2" in spec.name) else 78.0
            spec_buf[off + 0] = clamp255(min(spec_cap, sr * spec_mult))
            spec_buf[off + 1] = clamp255(min(spec_cap, sg * spec_mult))
            spec_buf[off + 2] = clamp255(min(spec_cap, sb * spec_mult))
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
        if spec.material_type == "2d":
            lines = [
                f'\t"{mat_name}" ( "material.gdf" )',
                "\t{",
                '\t\t"alphaTest" "Always*"',
                f'\t\t"blendFunc" "{spec.blend_func}"',
                f'\t\t"colorMap" "{paths["colorMap"]}"',
                '\t\t"colorTint" "1.000000 1.000000 1.000000 1.000000"',
                '\t\t"cullFace" "None"',
                '\t\t"depthTest" "Always"',
                '\t\t"depthWrite" "Off"',
                '\t\t"filterColor" "mip standard (2x bilinear)*"',
                '\t\t"materialType" "2d"',
                '\t\t"nopicmipColor" "1"',
                '\t\t"polygonOffset" "None*"',
                f'\t\t"surfaceType" "{spec.surface_type}"',
                '\t\t"template" "material.template"',
                '\t\t"tileColor" "no tile"',
                '\t\t"usage" "<not in editor>"',
                "\t}",
            ]
            blocks.append("\n".join(lines))
            continue

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


def _clone_mesh_for_pap_tier(
    base_mesh: MeshBuilder,
    new_name: str,
    mat_remap: dict[str, str],
    weapon_key: str,
    pap_tier: int,
    is_world: bool,
) -> MeshBuilder:
    """Clone one of the 4 custom primary meshes into a Stage-1 or Stage-2 PaP finish (<=4 material slots)."""
    m = MeshBuilder(new_name, base_mesh.bones, model_type=base_mesh.model_type)
    m.verts = list(base_mesh.verts)
    for face in base_mesh.faces:
        orig_mat = base_mesh.materials[face.mat_idx]
        mapped_mat = mat_remap.get(orig_mat, orig_mat)
        m.faces.append(
            FaceDef(
                mat_idx=m.mat(mapped_mat),
                v0=face.v0,
                v1=face.v1,
                v2=face.v2,
                n0=face.n0,
                n1=face.n1,
                n2=face.n2,
                uv0=face.uv0,
                uv1=face.uv1,
                uv2=face.uv2,
            )
        )

    # Subtle 1P-visible rear dorsal collar (Stage 1) or parallel "II" crest bars (Stage 2)
    accent = "mtl_bz_pap1_brass" if pap_tier == 1 else "mtl_bz_pap2_trim"
    glow = f"mtl_bz_{weapon_key}_glow_pap{pap_tier}"
    if weapon_key == "acid":
        if pap_tier == 1:
            m.add_tapered_prism(accent, (1.6, 0.0, -0.26), (2.2, 0.0, -0.26), 1.24, 1.24, sides=6, bone_idx=0)
        else:
            m.add_box(accent, (2.4, -0.28, 0.96), (1.4, 0.16, 0.16), bone_idx=0)
            m.add_box(accent, (2.4, +0.28, 0.96), (1.4, 0.16, 0.16), bone_idx=0)
            m.add_box(glow, (2.4, 0.0, 0.94), (1.0, 0.24, 0.10), bone_idx=0)
    elif weapon_key == "cryo":
        if pap_tier == 1:
            m.add_box(accent, (4.8, 0.0, 3.06), (1.2, 2.05, 0.22), bone_idx=0)
        else:
            m.add_box(accent, (5.2, -0.34, 3.10), (1.35, 0.16, 0.16), bone_idx=0)
            m.add_box(accent, (5.2, +0.34, 3.10), (1.35, 0.16, 0.16), bone_idx=0)
    elif weapon_key == "xbow":
        if pap_tier == 1:
            m.add_box(accent, (3.2, 0.0, 2.48), (1.15, 2.10, 0.18), bone_idx=0)
        else:
            m.add_box(accent, (3.2, -0.32, 2.52), (1.25, 0.14, 0.14), bone_idx=0)
            m.add_box(accent, (3.2, +0.32, 2.52), (1.25, 0.14, 0.14), bone_idx=0)
    elif weapon_key == "blade":
        s = 2.45 if is_world else 1.0
        if pap_tier == 1:
            m.add_tapered_prism(accent, (0.0, 0.0, 0.30 * s), (0.0, 0.0, 0.72 * s), 0.44 * s, 0.44 * s, sides=6, bone_idx=0)
        else:
            m.add_box(accent, (0.15 * s, -0.18 * s, 1.35 * s), (0.14 * s, 0.08 * s, 0.56 * s), bone_idx=0)
            m.add_box(accent, (0.15 * s, +0.18 * s, 1.35 * s), (0.14 * s, 0.08 * s, 0.56 * s), bone_idx=0)
    return m


def build_all_meshes() -> list[MeshBuilder]:
    acid_vm = build_acid_sprayer("viewmodel_bz_acid_sprayer", is_world=False)
    acid_wm = build_acid_sprayer("world_bz_acid_sprayer", is_world=True)
    cryo_vm = build_cryo_cannon("viewmodel_bz_cryo_cannon", is_world=False)
    cryo_wm = build_cryo_cannon("world_bz_cryo_cannon", is_world=True)
    xbow_vm = build_multi_crossbow("viewmodel_bz_multi_crossbow", is_world=False)
    xbow_wm = build_multi_crossbow("world_bz_multi_crossbow", is_world=True)
    blade_vm = build_blade_boomerang_held("viewmodel_bz_blade_boomerang", is_world=False)
    blade_wm = build_blade_boomerang_held("world_bz_blade_boomerang", is_world=True)

    pap_variants: list[MeshBuilder] = []
    pap_specs = (
        (
            "acid",
            "bz_acid_sprayer",
            acid_vm,
            acid_wm,
            {
                "mtl_bz_acid_metal": "mtl_bz_pap1_steel",
                "mtl_bz_xbow_brass": "mtl_bz_pap1_brass",
                "mtl_bz_acid_glow": "mtl_bz_acid_glow_pap1",
            },
            {
                "mtl_bz_acid_metal": "mtl_bz_pap2_steel",
                "mtl_bz_xbow_brass": "mtl_bz_pap2_trim",
                "mtl_bz_acid_glow": "mtl_bz_acid_glow_pap2",
            },
        ),
        (
            "cryo",
            "bz_cryo_cannon",
            cryo_vm,
            cryo_wm,
            {
                "mtl_bz_cryo_dark": "mtl_bz_pap1_steel",
                "mtl_bz_xbow_brass": "mtl_bz_pap1_brass",
                "mtl_bz_cryo_glow": "mtl_bz_cryo_glow_pap1",
            },
            {
                "mtl_bz_cryo_dark": "mtl_bz_pap2_steel",
                "mtl_bz_xbow_brass": "mtl_bz_pap2_trim",
                "mtl_bz_cryo_glow": "mtl_bz_cryo_glow_pap2",
            },
        ),
        (
            "xbow",
            "bz_multi_crossbow",
            xbow_vm,
            xbow_wm,
            {
                "mtl_bz_xbow_metal": "mtl_bz_pap1_steel",
                "mtl_bz_xbow_brass": "mtl_bz_pap1_brass",
                "mtl_bz_xbow_glow": "mtl_bz_xbow_glow_pap1",
            },
            {
                "mtl_bz_xbow_metal": "mtl_bz_pap2_steel",
                "mtl_bz_xbow_brass": "mtl_bz_pap2_trim",
                "mtl_bz_xbow_glow": "mtl_bz_xbow_glow_pap2",
            },
        ),
        (
            "blade",
            "bz_blade_boomerang",
            blade_vm,
            blade_wm,
            {
                "mtl_bz_blade_steel": "mtl_bz_pap1_steel",
                "mtl_bz_blade_brass": "mtl_bz_pap1_brass",
                "mtl_bz_blade_glow": "mtl_bz_blade_glow_pap1",
            },
            {
                "mtl_bz_blade_steel": "mtl_bz_pap2_steel",
                "mtl_bz_blade_brass": "mtl_bz_pap2_trim",
                "mtl_bz_blade_glow": "mtl_bz_blade_glow_pap2",
            },
        ),
    )
    for wkey, base_weap, vm, wm, remap1, remap2 in pap_specs:
        pap_variants.append(
            _clone_mesh_for_pap_tier(vm, f"viewmodel_{base_weap}_pap1", remap1, wkey, 1, False)
        )
        pap_variants.append(
            _clone_mesh_for_pap_tier(wm, f"world_{base_weap}_pap1", remap1, wkey, 1, True)
        )
        pap_variants.append(
            _clone_mesh_for_pap_tier(vm, f"viewmodel_{base_weap}_pap2", remap2, wkey, 2, False)
        )
        pap_variants.append(
            _clone_mesh_for_pap_tier(wm, f"world_{base_weap}_pap2", remap2, wkey, 2, True)
        )

    return [
        acid_vm,
        acid_wm,
        cryo_vm,
        cryo_wm,
        xbow_vm,
        xbow_wm,
        build_crossbow_bolt(),
        blade_vm,
        blade_wm,
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
        # Wave 2 (NSV-W2, Sheet 09 — 9 XMODELs)
        build_pap_cluster_grenade("viewmodel_bz_pap_cluster", is_world=False),
        build_pap_cluster_grenade("world_bz_pap_cluster", is_world=True),
        build_pap_cluster_submunition(),
        build_pap_knife("viewmodel_bz_pap_knife", is_world=False),
        build_pap_knife("world_bz_pap_knife", is_world=True),
        build_pap_bowie("viewmodel_bz_pap_bowie", is_world=False),
        build_pap_bowie("world_bz_pap_bowie", is_world=True),
        build_sapper_trap_fire(),
        build_sapper_trap_betty(),
        # Wave 3 (NSV-W3, Sheet 10 — 16 XMODELs)
        *pap_variants,
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
