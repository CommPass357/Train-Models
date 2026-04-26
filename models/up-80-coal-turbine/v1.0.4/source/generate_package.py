from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import textwrap
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source"
PARAMS_PATH = SOURCE / "up80_parameters.json"


Vec = tuple[float, float, float]
Tri = tuple[Vec, Vec, Vec]


def vsub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vcross(a: Vec, b: Vec) -> Vec:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vnorm(a: Vec) -> Vec:
    length = math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2)
    if length < 1e-9:
        return (0.0, 0.0, 0.0)
    return (a[0] / length, a[1] / length, a[2] / length)


def normal(tri: Tri) -> Vec:
    return vnorm(vcross(vsub(tri[1], tri[0]), vsub(tri[2], tri[0])))


def fmt(n: float) -> str:
    if abs(n) < 1e-9:
        n = 0.0
    return f"{n:.5f}"


@dataclass
class Mesh:
    name: str
    triangles: list[Tri] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add_tri(self, a: Vec, b: Vec, c: Vec) -> None:
        self.triangles.append((a, b, c))

    def add_quad(self, a: Vec, b: Vec, c: Vec, d: Vec) -> None:
        self.add_tri(a, b, c)
        self.add_tri(a, c, d)

    def extend(self, other: "Mesh") -> None:
        self.triangles.extend(other.triangles)
        self.notes.extend(other.notes)

    def bounds(self) -> dict[str, list[float]]:
        if not self.triangles:
            return {"min": [0, 0, 0], "max": [0, 0, 0], "size": [0, 0, 0]}
        xs, ys, zs = [], [], []
        for tri in self.triangles:
            for x, y, z in tri:
                xs.append(x)
                ys.append(y)
                zs.append(z)
        mn = [min(xs), min(ys), min(zs)]
        mx = [max(xs), max(ys), max(zs)]
        return {"min": mn, "max": mx, "size": [mx[i] - mn[i] for i in range(3)]}

    def write_stl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(f"solid {self.name}\n")
            for tri in self.triangles:
                n = normal(tri)
                f.write(f"  facet normal {fmt(n[0])} {fmt(n[1])} {fmt(n[2])}\n")
                f.write("    outer loop\n")
                for vertex in tri:
                    f.write(f"      vertex {fmt(vertex[0])} {fmt(vertex[1])} {fmt(vertex[2])}\n")
                f.write("    endloop\n")
                f.write("  endfacet\n")
            f.write(f"endsolid {self.name}\n")


def add_box(mesh: Mesh, center: Vec, size: Vec) -> None:
    cx, cy, cz = center
    lx, ly, lz = size
    x0, x1 = cx - lx / 2, cx + lx / 2
    y0, y1 = cy - ly / 2, cy + ly / 2
    z0, z1 = cz - lz / 2, cz + lz / 2
    p = {
        "000": (x0, y0, z0),
        "100": (x1, y0, z0),
        "110": (x1, y1, z0),
        "010": (x0, y1, z0),
        "001": (x0, y0, z1),
        "101": (x1, y0, z1),
        "111": (x1, y1, z1),
        "011": (x0, y1, z1),
    }
    mesh.add_quad(p["000"], p["100"], p["110"], p["010"])
    mesh.add_quad(p["001"], p["011"], p["111"], p["101"])
    mesh.add_quad(p["000"], p["001"], p["101"], p["100"])
    mesh.add_quad(p["100"], p["101"], p["111"], p["110"])
    mesh.add_quad(p["110"], p["111"], p["011"], p["010"])
    mesh.add_quad(p["010"], p["011"], p["001"], p["000"])


def orient(local: Vec, center: Vec, axis: str) -> Vec:
    x, y, z = local
    cx, cy, cz = center
    if axis == "z":
        return (cx + x, cy + y, cz + z)
    if axis == "y":
        return (cx + x, cy + z, cz + y)
    if axis == "x":
        return (cx + z, cy + x, cz + y)
    raise ValueError(f"unsupported axis {axis}")


def add_cylinder(mesh: Mesh, center: Vec, radius: float, height: float, segments: int = 32, axis: str = "z", caps: bool = True) -> None:
    bottom, top = -height / 2, height / 2
    cb = orient((0, 0, bottom), center, axis)
    ct = orient((0, 0, top), center, axis)
    for i in range(segments):
        a0 = 2 * math.pi * i / segments
        a1 = 2 * math.pi * (i + 1) / segments
        p0 = orient((radius * math.cos(a0), radius * math.sin(a0), bottom), center, axis)
        p1 = orient((radius * math.cos(a1), radius * math.sin(a1), bottom), center, axis)
        p2 = orient((radius * math.cos(a1), radius * math.sin(a1), top), center, axis)
        p3 = orient((radius * math.cos(a0), radius * math.sin(a0), top), center, axis)
        mesh.add_quad(p0, p1, p2, p3)
        if caps:
            mesh.add_tri(cb, p1, p0)
            mesh.add_tri(ct, p3, p2)


def add_annular_cylinder(mesh: Mesh, center: Vec, outer_r: float, inner_r: float, height: float, segments: int = 32, axis: str = "z") -> None:
    bottom, top = -height / 2, height / 2
    for i in range(segments):
        a0 = 2 * math.pi * i / segments
        a1 = 2 * math.pi * (i + 1) / segments
        ob0 = orient((outer_r * math.cos(a0), outer_r * math.sin(a0), bottom), center, axis)
        ob1 = orient((outer_r * math.cos(a1), outer_r * math.sin(a1), bottom), center, axis)
        ot1 = orient((outer_r * math.cos(a1), outer_r * math.sin(a1), top), center, axis)
        ot0 = orient((outer_r * math.cos(a0), outer_r * math.sin(a0), top), center, axis)
        ib0 = orient((inner_r * math.cos(a0), inner_r * math.sin(a0), bottom), center, axis)
        ib1 = orient((inner_r * math.cos(a1), inner_r * math.sin(a1), bottom), center, axis)
        it1 = orient((inner_r * math.cos(a1), inner_r * math.sin(a1), top), center, axis)
        it0 = orient((inner_r * math.cos(a0), inner_r * math.sin(a0), top), center, axis)
        mesh.add_quad(ob0, ob1, ot1, ot0)
        mesh.add_quad(ib1, ib0, it0, it1)
        mesh.add_quad(ot0, ot1, it1, it0)
        mesh.add_quad(ob1, ob0, ib0, ib1)


def add_extruded_polygon_x(mesh: Mesh, x0: float, x1: float, yz_points: list[tuple[float, float]]) -> None:
    n = len(yz_points)
    front = [(x0, y, z) for y, z in yz_points]
    back = [(x1, y, z) for y, z in yz_points]
    for i in range(n):
        j = (i + 1) % n
        mesh.add_quad(front[i], front[j], back[j], back[i])
    for i in range(1, n - 1):
        mesh.add_tri(front[0], front[i], front[i + 1])
        mesh.add_tri(back[0], back[i + 1], back[i])


def add_arched_roof(mesh: Mesh, x0: float, x1: float, width: float, eave_z: float, rise: float, thickness: float, segments: int = 18) -> None:
    outer = []
    inner = []
    for i in range(segments + 1):
        theta = math.pi - math.pi * i / segments
        outer.append((math.cos(theta) * width / 2, eave_z + math.sin(theta) * rise))
        inner.append((math.cos(theta) * (width / 2 - thickness), eave_z - thickness + math.sin(theta) * max(rise - thickness, 0.8)))
    ring = outer + list(reversed(inner))
    add_extruded_polygon_x(mesh, x0, x1, ring)


def add_pa_nose(mesh: Mesh, x_front: float, nose_length: float, width: float, height: float, segments_x: int = 16, segments_ring: int = 32) -> None:
    rings: list[list[Vec]] = []
    for ix in range(segments_x + 1):
        u = ix / segments_x
        scale = 0.08 + 0.92 * (math.sin(u * math.pi / 2) ** 0.68)
        x = x_front + nose_length * u
        ring = []
        for j in range(segments_ring):
            t = 2 * math.pi * j / segments_ring
            y = math.cos(t) * width * 0.5 * scale
            z = height * 0.52 + math.sin(t) * height * 0.48 * scale
            ring.append((x, y, z))
        rings.append(ring)
    for ix in range(segments_x):
        for j in range(segments_ring):
            k = (j + 1) % segments_ring
            mesh.add_quad(rings[ix][j], rings[ix][k], rings[ix + 1][k], rings[ix + 1][j])
    center_tip = (x_front - 1.4, 0, height * 0.52)
    for j in range(segments_ring):
        mesh.add_tri(center_tip, rings[0][j], rings[0][(j + 1) % segments_ring])


def add_grid_plate(mesh: Mesh, length: float, width: float, height: float, holes: list[tuple[float, float, float]], cell: float = 2.5) -> None:
    nx = max(4, math.ceil(length / cell))
    ny = max(4, math.ceil(width / cell))
    dx = length / nx
    dy = width / ny
    occupied = [[False for _ in range(ny)] for _ in range(nx)]

    def inside_hole(x: float, y: float) -> bool:
        return any((x - hx) ** 2 + (y - hy) ** 2 <= hr ** 2 for hx, hy, hr in holes)

    for i in range(nx):
        x = -length / 2 + (i + 0.5) * dx
        for j in range(ny):
            y = -width / 2 + (j + 0.5) * dy
            occupied[i][j] = not inside_hole(x, y)

    z0, z1 = 0.0, height
    for i in range(nx):
        for j in range(ny):
            if not occupied[i][j]:
                continue
            x0 = -length / 2 + i * dx
            x1 = x0 + dx
            y0 = -width / 2 + j * dy
            y1 = y0 + dy
            mesh.add_quad((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0))
            mesh.add_quad((x0, y0, z1), (x0, y1, z1), (x1, y1, z1), (x1, y0, z1))
            for di, dj, face in [
                (-1, 0, "left"),
                (1, 0, "right"),
                (0, -1, "front"),
                (0, 1, "back"),
            ]:
                ni, nj = i + di, j + dj
                neighbor = 0 <= ni < nx and 0 <= nj < ny and occupied[ni][nj]
                if neighbor:
                    continue
                if face == "left":
                    mesh.add_quad((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0))
                elif face == "right":
                    mesh.add_quad((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1))
                elif face == "front":
                    mesh.add_quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1))
                elif face == "back":
                    mesh.add_quad((x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0))


def add_side_grilles(mesh: Mesh, length: float, width: float, z: float, x_start: float, x_end: float, count: int, side: int, tall: bool = False) -> None:
    span = x_end - x_start
    pitch = span / count
    grille_h = 8.5 if tall else 5.2
    grille_w = pitch * 0.55
    for i in range(count):
        x = x_start + (i + 0.5) * pitch
        add_box(mesh, (x, side * (width / 2 + 0.28), z), (grille_w, 0.55, grille_h))
        if i % 2 == 0:
            add_box(mesh, (x, side * (width / 2 + 0.62), z), (grille_w * 0.65, 0.22, grille_h + 1.2))


def add_ladder(mesh: Mesh, x: float, y: float, z0: float, height: float, side: int) -> None:
    add_box(mesh, (x - 1.6, y, z0 + height / 2), (0.45, 0.45, height))
    add_box(mesh, (x + 1.6, y, z0 + height / 2), (0.45, 0.45, height))
    for k in range(5):
        z = z0 + 1.5 + k * (height - 3.0) / 4
        add_box(mesh, (x, y, z), (3.8, 0.45, 0.35))


def add_roof_fan(mesh: Mesh, x: float, y: float, z: float, radius: float = 4.2) -> None:
    add_cylinder(mesh, (x, y, z), radius, 0.75, 32, "z", True)
    for angle in (0, 60, 120):
        rad = math.radians(angle)
        add_box(mesh, (x + math.cos(rad) * radius * 0.35, y + math.sin(rad) * radius * 0.35, z + 0.55), (radius * 1.25, 0.55, 0.4))


def add_side_panel(mesh: Mesh, x: float, width: float, side: int, z: float, panel_w: float, panel_h: float, depth: float = 0.7) -> None:
    add_box(mesh, (x, side * (width / 2 + depth / 2), z), (panel_w, depth, panel_h))


def add_door_panel(mesh: Mesh, x: float, width: float, side: int, z: float, panel_w: float = 9.0, panel_h: float = 17.0) -> None:
    add_side_panel(mesh, x, width, side, z, panel_w, panel_h, 0.55)
    add_side_panel(mesh, x, width, side, z + panel_h / 2 - 1.0, panel_w + 1.2, 0.45, 0.8)
    add_side_panel(mesh, x, width, side, z - panel_h / 2 + 1.0, panel_w + 1.2, 0.45, 0.8)
    add_side_panel(mesh, x - panel_w / 2 + 0.35, width, side, z, 0.45, panel_h + 0.8, 0.8)
    add_side_panel(mesh, x + panel_w / 2 - 0.35, width, side, z, 0.45, panel_h + 0.8, 0.8)
    add_box(mesh, (x + panel_w * 0.28, side * (width / 2 + 0.85), z + 1.0), (0.9, 0.55, 0.9))


def add_window_frame(mesh: Mesh, x: float, width: float, side: int, z: float, w: float, h: float) -> None:
    add_side_panel(mesh, x, width, side, z, w, h, 0.35)
    add_side_panel(mesh, x, width, side, z + h / 2, w + 1.0, 0.45, 0.75)
    add_side_panel(mesh, x, width, side, z - h / 2, w + 1.0, 0.45, 0.75)
    add_side_panel(mesh, x - w / 2, width, side, z, 0.45, h + 1.0, 0.75)
    add_side_panel(mesh, x + w / 2, width, side, z, 0.45, h + 1.0, 0.75)


def add_louver_bank(mesh: Mesh, x0: float, x1: float, width: float, side: int, z: float, rows: int, cols: int, h: float = 4.0) -> None:
    span = x1 - x0
    for c in range(cols):
        x = x0 + (c + 0.5) * span / cols
        for r in range(rows):
            zz = z - (rows - 1) * h * 0.42 + r * h * 0.84
            add_side_panel(mesh, x, width, side, zz, span / cols * 0.62, 0.35, 0.72)


def add_rivet_row(mesh: Mesh, x0: float, x1: float, width: float, side: int, z: float, count: int) -> None:
    if count <= 1:
        return
    for i in range(count):
        x = x0 + (x1 - x0) * i / (count - 1)
        add_cylinder(mesh, (x, side * (width / 2 + 0.72), z), 0.35, 0.45, 10, "y", True)


def add_side_handrail(mesh: Mesh, x0: float, x1: float, width: float, side: int, z: float, posts: int = 8) -> None:
    add_box(mesh, ((x0 + x1) / 2, side * (width / 2 + 1.15), z), (x1 - x0, 0.35, 0.35))
    for i in range(posts):
        x = x0 + (x1 - x0) * i / max(posts - 1, 1)
        add_box(mesh, (x, side * (width / 2 + 1.05), z - 2.0), (0.35, 0.35, 4.0))


def add_grab_irons(mesh: Mesh, x: float, width: float, side: int, z0: float, count: int = 4) -> None:
    for i in range(count):
        z = z0 + i * 2.5
        add_box(mesh, (x, side * (width / 2 + 1.05), z), (3.2, 0.32, 0.32))
        add_box(mesh, (x - 1.6, side * (width / 2 + 0.95), z - 0.8), (0.32, 0.32, 1.6))
        add_box(mesh, (x + 1.6, side * (width / 2 + 0.95), z - 0.8), (0.32, 0.32, 1.6))


def add_pilot_steps(mesh: Mesh, x: float, width: float, front_sign: int) -> None:
    for side in (-1, 1):
        for i, z in enumerate((3.0, 5.1, 7.2)):
            add_box(mesh, (x, side * (width / 2 + 2.2), z), (5.2 - i * 0.5, 2.8, 0.45))
        add_box(mesh, (x + front_sign * 2.6, side * (width / 2 + 1.2), 5.2), (0.5, 0.55, 5.0))


def add_horn_cluster(mesh: Mesh, x: float, y: float, z: float) -> None:
    add_box(mesh, (x, y, z), (6.0, 1.2, 0.8))
    for dx, length in ((-2.2, 5.5), (0.0, 6.5), (2.2, 5.0)):
        add_cylinder(mesh, (x + dx, y + 1.6, z + 0.5), 0.55, length, 14, "y", True)
        add_cylinder(mesh, (x + dx, y + 1.6 + length / 2, z + 0.5), 0.9, 0.45, 14, "y", True)


def add_roof_hatch(mesh: Mesh, x: float, y: float, z: float, length: float, width: float) -> None:
    add_box(mesh, (x, y, z), (length, width, 0.8))
    add_box(mesh, (x, y, z + 0.65), (length - 1.6, width - 1.6, 0.55))
    add_cylinder(mesh, (x - length * 0.28, y, z + 1.05), 0.45, width - 2.5, 12, "y", True)


def add_roof_walkway(mesh: Mesh, x0: float, x1: float, y: float, z: float) -> None:
    add_box(mesh, ((x0 + x1) / 2, y, z), (x1 - x0, 3.0, 0.45))
    for i in range(9):
        x = x0 + (x1 - x0) * i / 8
        add_box(mesh, (x, y, z + 0.35), (0.45, 3.4, 0.4))


def add_tender_side_ribs(mesh: Mesh, length: float, width: float, side: int, height: float) -> None:
    for x in (-length / 2 + 16, -length / 2 + 42, -length / 2 + 68, -length / 2 + 94, -length / 2 + 122, length / 2 - 44, length / 2 - 18):
        add_side_panel(mesh, x, width, side, height / 2, 0.7, height - 3.5, 0.75)
    add_rivet_row(mesh, -length / 2 + 8, length / 2 - 8, width, side, height - 2.0, 30)
    add_rivet_row(mesh, -length / 2 + 8, length / 2 - 8, width, side, 5.2, 30)


def add_truck_sideframes(mesh: Mesh, x_positions: Iterable[float], width: float, wheelbase: float, axle_count: int, z: float, side_prefix: str) -> None:
    for x in x_positions:
        axles = []
        if axle_count == 2:
            axles = [x - wheelbase / 2, x + wheelbase / 2]
        else:
            spacing = wheelbase / max(axle_count - 1, 1)
            axles = [x - wheelbase / 2 + i * spacing for i in range(axle_count)]
        for side in (-1, 1):
            y = side * (width / 2 + 1.35)
            add_box(mesh, (x, y, z + 2.6), (wheelbase + 5.5, 1.1, 2.4))
            add_box(mesh, (x, y, z + 5.0), (wheelbase + 3.0, 0.8, 1.2))
            for ax in axles:
                add_cylinder(mesh, (ax, y + side * 0.25, z + 2.15), 2.25, 0.85, 18, "y", True)
                add_box(mesh, (ax, y, z + 4.8), (2.0, 1.0, 1.0))


def make_body_shell(unit_key: str, unit: dict, variant: str) -> Mesh:
    detail = variant == "resin"
    wall = 1.25 if detail else 1.8
    name = f"{unit_key}_shell_{variant}"
    m = Mesh(name)
    L = unit["shell_length_mm"]
    W = unit["shell_width_mm"]
    H = unit["shell_side_height_mm"]
    roof = unit.get("roof_rise_mm", 0.0)
    if unit_key == "a_control":
        nose_len = unit["nose_length_mm"]
        x_front = -L / 2
        x_body0 = x_front + nose_len
        body_len = L - nose_len
        add_box(m, (x_body0 + body_len / 2, 0, 2.0), (body_len, W - 3.0, 2.0))
        add_box(m, (x_body0 + body_len / 2, -W / 2 + wall / 2, H / 2), (body_len, wall, H))
        add_box(m, (x_body0 + body_len / 2, W / 2 - wall / 2, H / 2), (body_len, wall, H))
        add_box(m, (L / 2 - wall / 2, 0, H / 2), (wall, W, H))
        add_arched_roof(m, x_body0, L / 2, W, H, roof, wall, 22 if detail else 12)
        add_pa_nose(m, x_front, nose_len + 2.0, W, H + roof * 0.8, 20 if detail else 12, 36 if detail else 20)
        add_box(m, (x_front + 10.5, 0, 20.0), (3.0, 7.5, 2.2))
        add_box(m, (x_front + 16.0, -9.5, 29.0), (1.2, 5.5, 3.0))
        add_box(m, (x_front + 16.0, 9.5, 29.0), (1.2, 5.5, 3.0))
        add_cylinder(m, (x_front + 3.2, -3.0, 22.8), 1.05, 1.2, 18, "x", True)
        add_cylinder(m, (x_front + 3.2, 3.0, 22.8), 1.05, 1.2, 18, "x", True)
        add_cylinder(m, (x_front + 5.5, 0, 27.0), 1.1, 1.0, 18, "x", True)
        add_cylinder(m, (x_front + 5.0, -6.8, 20.6), 0.65, 0.65, 14, "x", True)
        add_cylinder(m, (x_front + 5.0, 6.8, 20.6), 0.65, 0.65, 14, "x", True)
        add_box(m, (x_front + 8.8, -7.4, 28.2), (1.0, 5.8, 2.8))
        add_box(m, (x_front + 8.8, 7.4, 28.2), (1.0, 5.8, 2.8))
        for side in (-1, 1):
            add_side_grilles(m, L, W, 20.0, x_body0 + 30.0, L / 2 - 24.0, 22 if detail else 12, side)
            add_louver_bank(m, x_body0 + 38.0, L / 2 - 31.0, W, side, 25.0, 4, 12 if detail else 7, 2.4)
            add_window_frame(m, x_body0 + 12.5, W, side, 27.0, 8.0, 5.2)
            add_door_panel(m, x_body0 + 23.0, W, side, 18.0, 8.5, 18.0)
            add_door_panel(m, L / 2 - 18.0, W, side, 17.0, 10.0, 17.0)
            add_side_panel(m, x_body0 + 92.0, W, side, 13.0, 18.0, 8.0, 0.55)
            add_side_handrail(m, x_body0 + 34.0, L / 2 - 18.0, W, side, 11.5, 10)
            add_grab_irons(m, x_body0 + 6.0, W, side, 11.0, 5)
            add_rivet_row(m, x_body0 + 3.0, L / 2 - 8.0, W, side, 6.0, 28)
            add_rivet_row(m, x_body0 + 3.0, L / 2 - 8.0, W, side, H - 1.8, 28)
            add_ladder(m, L / 2 - 7.0, side * (W / 2 + 0.9), 4.0, 16.0, side)
        add_roof_fan(m, x_body0 + 58.0, 0, H + roof + 0.8, 4.0)
        add_roof_fan(m, x_body0 + 96.0, 0, H + roof + 0.8, 4.0)
        add_roof_hatch(m, x_body0 + 33.0, 0, H + roof + 0.9, 18.0, 7.5)
        add_roof_hatch(m, x_body0 + 128.0, 0, H + roof + 0.9, 24.0, 8.0)
        add_horn_cluster(m, x_body0 + 22.0, -3.5, H + roof + 2.2)
        add_roof_walkway(m, x_body0 + 38.0, L / 2 - 22.0, -W / 2 + 4.0, H + roof + 1.0)
        add_box(m, (x_front + 8.0, 0, 2.2), (15.0, W + 2.0, 4.4))
        add_box(m, (L / 2 - 3.5, 0, 2.0), (7.0, W + 1.2, 4.0))
        add_pilot_steps(m, x_front + 9.0, W, -1)
        add_pilot_steps(m, L / 2 - 5.0, W, 1)
    elif unit_key == "center_turbine":
        add_box(m, (0, 0, 2.0), (L - 6.0, W - 3.0, 2.0))
        add_box(m, (0, -W / 2 + wall / 2, H / 2), (L, wall, H))
        add_box(m, (0, W / 2 - wall / 2, H / 2), (L, wall, H))
        add_box(m, (-L / 2 + wall / 2, 0, H / 2), (wall, W, H))
        add_box(m, (L / 2 - wall / 2, 0, H / 2), (wall, W, H))
        add_arched_roof(m, -L / 2, L / 2, W, H, roof, wall, 20 if detail else 12)
        for x in (-104, -72, -38, 0, 38, 72, 104):
            add_box(m, (x, 0, 18.0), (16.0, W - 5.5, 10.0))
        for x in (-130, -12, 118):
            add_box(m, (x, 0, 9.0), (34.0, W - 4.0, 6.0))
        for side in (-1, 1):
            add_side_grilles(m, L, W, 23.0, -L / 2 + 18.0, L / 2 - 18.0, 48 if detail else 24, side, tall=True)
            add_louver_bank(m, -L / 2 + 32.0, L / 2 - 32.0, W, side, 29.0, 5, 24 if detail else 12, 2.2)
            add_box(m, (0, side * (W / 2 + 0.7), 8.5), (L - 28.0, 1.0, 2.2))
            for x in (-L / 2 + 34, -L / 2 + 70, -L / 4, 0, L / 4, L / 2 - 70, L / 2 - 34):
                add_door_panel(m, x, W, side, 17.0, 8.5, 13.0)
            add_side_handrail(m, -L / 2 + 24.0, L / 2 - 24.0, W, side, 10.0, 16)
            add_rivet_row(m, -L / 2 + 12.0, L / 2 - 12.0, W, side, 6.0, 42)
            add_rivet_row(m, -L / 2 + 12.0, L / 2 - 12.0, W, side, H - 2.0, 42)
            add_grab_irons(m, -L / 2 + 20.0, W, side, 9.0, 5)
            add_grab_irons(m, L / 2 - 20.0, W, side, 9.0, 5)
            add_ladder(m, -L / 2 + 12.0, side * (W / 2 + 0.95), 3.5, 18.0, side)
            add_ladder(m, L / 2 - 12.0, side * (W / 2 + 0.95), 3.5, 18.0, side)
        for x in (-96, -48, 0, 48, 96):
            add_roof_fan(m, x, 0, H + roof + 0.9, 4.5)
        for x in (-18, 18):
            add_cylinder(m, (x, 0, H + roof + 3.0), 3.0, 5.0, 24, "z", True)
        for x in (-132, -70, 70, 132):
            add_roof_hatch(m, x, 0, H + roof + 1.0, 26.0, 8.0)
        add_roof_walkway(m, -L / 2 + 22.0, L / 2 - 22.0, W / 2 - 4.0, H + roof + 0.9)
        add_roof_walkway(m, -L / 2 + 22.0, L / 2 - 22.0, -W / 2 + 4.0, H + roof + 0.9)
        add_box(m, (-L / 2 + 6.0, 0, 3.0), (12.0, W + 1.8, 6.0))
        add_box(m, (L / 2 - 6.0, 0, 3.0), (12.0, W + 1.8, 6.0))
        add_pilot_steps(m, -L / 2 + 7.5, W, -1)
        add_pilot_steps(m, L / 2 - 7.5, W, 1)
    elif unit_key == "coal_tender":
        add_box(m, (0, 0, 2.0), (L - 4.0, W - 3.0, 2.0))
        add_box(m, (0, -W / 2 + wall / 2, H / 2), (L, wall, H))
        add_box(m, (0, W / 2 - wall / 2, H / 2), (L, wall, H))
        add_box(m, (-L / 2 + wall / 2, 0, H / 2), (wall, W, H))
        add_box(m, (L / 2 - wall / 2, 0, H / 2), (wall, W, H))
        add_box(m, (-L / 2 + 32.0, 0, H + 5.5), (52.0, W - 5.0, 10.0))
        add_coal_load(m, -L / 2 + 8.0, L / 2 - 50.0, W - 5.0, H + 11.0, detail)
        add_box(m, (L / 2 - 34.0, 0, H + 7.0), (42.0, W - 6.0, 12.0))
        add_cylinder(m, (L / 2 - 22.0, 0, H + 15.5), 4.8, 3.0, 24, "z", True)
        add_box(m, (L / 2 - 62.0, 0, H + 5.0), (18.0, W - 7.0, 8.0))
        add_cylinder(m, (L / 2 - 54.0, 0, H + 10.5), 2.2, 13.0, 20, "x", True)
        for x in (-L / 2 + 22.0, -L / 2 + 52.0, L / 2 - 62.0):
            add_roof_hatch(m, x, 0, H + 16.5, 18.0, 8.0)
        for side in (-1, 1):
            add_tender_side_ribs(m, L, W, side, H)
            for x in (-L / 2 + 20, -L / 2 + 58, -L / 2 + 96, L / 2 - 32):
                add_door_panel(m, x, W, side, 17.0, 11.0, 10.5)
            add_ladder(m, L / 2 - 9.0, side * (W / 2 + 0.95), 4.0, 18.0, side)
            add_ladder(m, -L / 2 + 9.0, side * (W / 2 + 0.95), 4.0, 18.0, side)
            add_box(m, (0, side * (W / 2 + 0.9), H + 2.0), (L - 16.0, 0.55, 0.7))
            add_side_handrail(m, -L / 2 + 12.0, L / 2 - 12.0, W, side, H + 4.0, 14)
            add_grab_irons(m, L / 2 - 14.0, W, side, 7.0, 5)
        add_cylinder(m, (L / 2 + 0.6, -5.0, 20.0), 1.0, 0.7, 16, "x", True)
        add_cylinder(m, (L / 2 + 0.6, 5.0, 20.0), 1.0, 0.7, 16, "x", True)
        add_cylinder(m, (L / 2 + 0.6, 0, 23.5), 1.1, 0.7, 16, "x", True)
    return m


def add_coal_load(mesh: Mesh, x0: float, x1: float, width: float, z: float, detail: bool) -> None:
    nx, ny = (18, 8) if detail else (10, 5)
    points = []
    for i in range(nx + 1):
        row = []
        x = x0 + (x1 - x0) * i / nx
        for j in range(ny + 1):
            y = -width / 2 + width * j / ny
            hump = 2.0 * math.sin(i * 1.8) * math.sin(j * 1.3) + 1.4 * math.cos((i + j) * 0.9)
            edge = min(j, ny - j) / (ny / 2)
            row.append((x, y, z + hump * max(edge, 0.25)))
        points.append(row)
    for i in range(nx):
        for j in range(ny):
            mesh.add_quad(points[i][j], points[i + 1][j], points[i + 1][j + 1], points[i][j + 1])


def make_chassis(unit_key: str, unit: dict, variant: str) -> Mesh:
    m = Mesh(f"{unit_key}_chassis_{variant}")
    L = unit["chassis_length_mm"]
    W = unit["chassis_width_mm"]
    plate_h = 3.2 if variant == "resin" else 4.0
    holes = [(x, 0.0, 2.4) for x in unit["truck_centers_mm"]]
    holes += [(-L / 2 + 8.0, 0.0, 1.4), (L / 2 - 8.0, 0.0, 1.4)]
    holes += [(-L / 2 + 14.5, 0.0, 1.5), (L / 2 - 14.5, 0.0, 1.5)]
    add_grid_plate(m, L, W, plate_h, holes, 2.4 if variant == "resin" else 3.2)
    for x in unit["truck_centers_mm"]:
        add_annular_cylinder(m, (x, 0, plate_h + 0.9), 5.0, 2.25, 1.8, 32, "z")
        add_box(m, (x, 0, plate_h + 2.2), (22.0, W - 7.0, 1.0))
    add_coupler_mounts(m, L, W, plate_h)
    add_shell_mount_bosses(m, L, W, plate_h)
    if unit_key in ("a_control", "center_turbine"):
        motor_len = 46.0 if unit_key == "a_control" else 60.0
        add_box(m, (0, -5.8, plate_h + 2.4), (motor_len, 2.2, 3.6))
        add_box(m, (0, 5.8, plate_h + 2.4), (motor_len, 2.2, 3.6))
        add_box(m, (0, 0, plate_h + 1.1), (motor_len + 6.0, 8.5, 1.0))
        add_box(m, (-L / 2 + 44.0, 0, plate_h + 1.0), (35.0, 18.0, 1.2))
        add_box(m, (L / 2 - 43.0, 0, plate_h + 1.0), (30.0, 18.0, 1.2))
        add_box(m, (0, 0, plate_h + 0.8), (L - 82.0, 2.3, 1.0))
        for x in (-L / 2 + 62.0, L / 2 - 62.0):
            add_box(m, (x, -W / 2 + 4.0, plate_h + 2.0), (28.0, 5.0, 2.4))
            add_box(m, (x, W / 2 - 4.0, plate_h + 2.0), (28.0, 5.0, 2.4))
    else:
        add_box(m, (-L / 2 + 45.0, 0, plate_h + 1.0), (52.0, 18.0, 1.2))
        add_box(m, (L / 2 - 43.0, 0, plate_h + 1.0), (38.0, 17.0, 1.2))
        add_box(m, (0, 0, plate_h + 0.8), (L - 40.0, 2.1, 1.0))
        for x in (-L / 2 + 50.0, 10.0, L / 2 - 45.0):
            add_box(m, (x, -W / 2 + 3.5, plate_h + 2.0), (24.0, 4.5, 2.4))
            add_box(m, (x, W / 2 - 3.5, plate_h + 2.0), (24.0, 4.5, 2.4))
    axle_count = 3 if unit_key == "a_control" else 4 if unit_key == "center_turbine" else 5
    if unit_key == "coal_tender":
        add_truck_sideframes(m, unit["truck_centers_mm"], W, unit["truck_wheelbase_mm"], axle_count, -0.6, unit_key)
    else:
        add_truck_sideframes(m, unit["truck_centers_mm"], W, unit["truck_wheelbase_mm"], axle_count, -0.6, unit_key)
    return m


def translate_mesh(mesh: Mesh, dx: float, dy: float, dz: float, name: str | None = None) -> Mesh:
    moved = Mesh(name or mesh.name)
    moved.triangles = [
        tuple((v[0] + dx, v[1] + dy, v[2] + dz) for v in tri)
        for tri in mesh.triangles
    ]
    moved.notes = list(mesh.notes)
    return moved


def make_base_plate_part(unit_key: str, unit: dict) -> Mesh:
    L = unit["chassis_length_mm"]
    W = unit["chassis_width_mm"]
    m = Mesh(f"{unit_key}_chassis_base_plate")
    holes = [(x, 0.0, 2.4) for x in unit["truck_centers_mm"]]
    holes += [(-L / 2 + 8.0, 0.0, 1.4), (L / 2 - 8.0, 0.0, 1.4)]
    holes += [(-L / 2 + 26.0, -W / 2 + 4.0, 1.0), (-L / 2 + 26.0, W / 2 - 4.0, 1.0)]
    holes += [(L / 2 - 26.0, -W / 2 + 4.0, 1.0), (L / 2 - 26.0, W / 2 - 4.0, 1.0)]
    add_grid_plate(m, L, W, 3.2, holes, 2.4)
    add_box(m, (0, 0, 3.9), (L - 18.0, 1.8, 1.4))
    for x in (-L / 2 + 18.0, L / 2 - 18.0):
        add_box(m, (x, 0, 4.2), (10.0, 8.0, 1.2))
    return m


def make_coupler_pocket_part(unit_key: str, unit: dict, end_name: str, end_sign: int) -> Mesh:
    m = Mesh(f"{unit_key}_{end_name}_coupler_pocket")
    add_box(m, (0, 0, 1.6), (13.5, 9.0, 3.2))
    add_box(m, (end_sign * 4.8, 0, 3.6), (4.2, 7.3, 1.2))
    add_annular_cylinder(m, (0, 0, 4.5), 2.9, 1.1, 1.0, 24, "z")
    add_box(m, (-end_sign * 7.5, 0, 1.2), (3.0, 6.5, 2.4))
    return m


def make_truck_bolster_part(unit_key: str, unit: dict, index: int, x: float) -> Mesh:
    m = Mesh(f"{unit_key}_truck_bolster_{index:02d}")
    W = unit["chassis_width_mm"]
    add_box(m, (0, 0, 1.4), (27.0, W - 6.0, 2.8))
    add_annular_cylinder(m, (0, 0, 3.4), 5.4, 2.2, 2.4, 32, "z")
    add_box(m, (-10.0, 0, 4.4), (2.6, W - 11.0, 1.0))
    add_box(m, (10.0, 0, 4.4), (2.6, W - 11.0, 1.0))
    for y in (-W / 2 + 6.0, W / 2 - 6.0):
        add_annular_cylinder(m, (0, y, 4.4), 2.0, 0.85, 1.4, 20, "z")
    m.notes.append(f"Install at chassis X={x:.1f} mm")
    return m


def make_motor_cradle_part(unit_key: str, unit: dict) -> Mesh:
    m = Mesh(f"{unit_key}_motor_cradle")
    L = 56.0 if unit_key == "a_control" else 72.0
    add_box(m, (0, -5.8, 2.4), (L, 2.2, 4.8))
    add_box(m, (0, 5.8, 2.4), (L, 2.2, 4.8))
    add_box(m, (0, 0, 0.6), (L + 8.0, 12.5, 1.2))
    add_box(m, (-L / 2 + 5.0, 0, 4.9), (4.0, 14.0, 1.2))
    add_box(m, (L / 2 - 5.0, 0, 4.9), (4.0, 14.0, 1.2))
    for x in (-L / 2 + 11.0, L / 2 - 11.0):
        add_annular_cylinder(m, (x, 0, 1.8), 2.3, 0.8, 1.8, 20, "z")
    return m


def make_decoder_tray_part(unit_key: str, unit: dict) -> Mesh:
    m = Mesh(f"{unit_key}_decoder_tray")
    add_box(m, (0, 0, 0.6), (39.0, 21.0, 1.2))
    add_box(m, (0, -10.0, 2.2), (39.0, 1.0, 3.2))
    add_box(m, (0, 10.0, 2.2), (39.0, 1.0, 3.2))
    add_box(m, (-19.0, 0, 2.0), (1.0, 21.0, 2.8))
    for x in (-13.0, 13.0):
        add_annular_cylinder(m, (x, 0, 1.5), 2.0, 0.8, 1.6, 20, "z")
    return m


def make_speaker_box_part(unit_key: str, unit: dict) -> Mesh:
    m = Mesh(f"{unit_key}_speaker_box")
    length = 32.0 if unit_key != "center_turbine" else 36.0
    width = 20.0
    add_box(m, (0, 0, 0.8), (length, width, 1.6))
    add_box(m, (0, -width / 2 + 0.7, 4.4), (length, 1.4, 7.2))
    add_box(m, (0, width / 2 - 0.7, 4.4), (length, 1.4, 7.2))
    add_box(m, (-length / 2 + 0.7, 0, 4.4), (1.4, width, 7.2))
    add_box(m, (length / 2 - 0.7, 0, 4.4), (1.4, width, 7.2))
    for x in (-length / 2 + 6.0, length / 2 - 6.0):
        add_annular_cylinder(m, (x, 0, 2.2), 2.0, 0.75, 1.8, 18, "z")
    return m


def make_ballast_box_part(unit_key: str, unit: dict, side_name: str, side_sign: int) -> Mesh:
    m = Mesh(f"{unit_key}_{side_name}_ballast_box")
    L = 42.0 if unit_key != "center_turbine" else 58.0
    add_box(m, (0, 0, 0.8), (L, 8.0, 1.6))
    add_box(m, (0, -3.8, 4.0), (L, 0.8, 6.4))
    add_box(m, (0, 3.8, 4.0), (L, 0.8, 6.4))
    add_box(m, (-L / 2 + 0.4, 0, 4.0), (0.8, 8.0, 6.4))
    add_box(m, (L / 2 - 0.4, 0, 4.0), (0.8, 8.0, 6.4))
    m.notes.append(f"Install on {side_name} side of {unit_key}; fill with tungsten/lead-free weight after test fitting.")
    return m


def make_wire_retainers_part(unit_key: str, unit: dict) -> Mesh:
    m = Mesh(f"{unit_key}_wire_retainers")
    for i, x in enumerate((-18.0, 0.0, 18.0)):
        add_box(m, (x, 0, 0.6), (10.0, 3.0, 1.2))
        add_box(m, (x, -3.2, 2.1), (10.0, 0.8, 3.0))
        add_box(m, (x, 3.2, 2.1), (10.0, 0.8, 3.0))
        add_box(m, (x, 0, 3.4), (10.0, 7.2, 0.8))
    return m


def make_shell_boss_set_part(unit_key: str, unit: dict) -> Mesh:
    m = Mesh(f"{unit_key}_shell_mount_boss_set")
    L = unit["chassis_length_mm"]
    W = unit["chassis_width_mm"]
    for x in (-L / 2 + 26.0, L / 2 - 26.0):
        for y in (-W / 2 + 4.0, W / 2 - 4.0):
            add_annular_cylinder(m, (x, y, 2.2), 2.9, 0.8, 4.4, 24, "z")
            add_box(m, (x, y, 0.35), (7.2, 7.2, 0.7))
    return m


def make_pickup_mounts_part(unit_key: str, unit: dict) -> Mesh:
    m = Mesh(f"{unit_key}_pickup_wiper_mounts")
    W = unit["chassis_width_mm"]
    for i, x in enumerate((-18.0, 18.0)):
        add_box(m, (x, -W / 4, 0.7), (18.0, 3.0, 1.4))
        add_box(m, (x, W / 4, 0.7), (18.0, 3.0, 1.4))
        add_box(m, (x, -W / 4, 2.1), (2.0, 6.0, 2.0))
        add_box(m, (x, W / 4, 2.1), (2.0, 6.0, 2.0))
    return m


def make_sideframe_part(unit_key: str, unit: dict) -> Mesh:
    m = Mesh(f"{unit_key}_cosmetic_sideframes")
    axle_count = 3 if unit_key == "a_control" else 4 if unit_key == "center_turbine" else 5
    spacing = unit["truck_wheelbase_mm"] + 10.0
    x_cursor = 0.0
    for idx, _truck_x in enumerate(unit["truck_centers_mm"], start=1):
        add_truck_sideframes(m, [x_cursor], unit["chassis_width_mm"], unit["truck_wheelbase_mm"], axle_count, 0.0, unit_key)
        x_cursor += spacing
    return m


def make_lighting_tray_part(unit_key: str, unit: dict) -> Mesh:
    m = Mesh(f"{unit_key}_lighting_tray")
    add_box(m, (0, 0, 0.6), (28.0, 10.0, 1.2))
    add_box(m, (-8.0, 0, 2.0), (3.0, 8.0, 2.8))
    add_box(m, (8.0, 0, 2.0), (3.0, 8.0, 2.8))
    add_cylinder(m, (-8.0, 0, 3.8), 1.4, 1.2, 18, "x", True)
    add_cylinder(m, (8.0, 0, 3.8), 1.4, 1.2, 18, "x", True)
    return m


def make_optional_power_plate_part(unit_key: str, unit: dict) -> Mesh:
    m = Mesh(f"{unit_key}_optional_power_truck_adapter")
    add_box(m, (0, 0, 0.8), (34.0, 18.0, 1.6))
    add_annular_cylinder(m, (0, 0, 2.3), 5.0, 2.1, 2.2, 28, "z")
    for x in (-11.5, 11.5):
        add_annular_cylinder(m, (x, 0, 1.8), 2.2, 0.8, 1.6, 18, "z")
    return m


def make_chassis_part_meshes(unit_key: str, unit: dict) -> dict[str, Mesh]:
    parts: dict[str, Mesh] = {
        "base_plate": make_base_plate_part(unit_key, unit),
        "front_coupler_pocket": make_coupler_pocket_part(unit_key, unit, "front", -1),
        "rear_coupler_pocket": make_coupler_pocket_part(unit_key, unit, "rear", 1),
        "decoder_tray": make_decoder_tray_part(unit_key, unit),
        "speaker_box": make_speaker_box_part(unit_key, unit),
        "left_ballast_box": make_ballast_box_part(unit_key, unit, "left", -1),
        "right_ballast_box": make_ballast_box_part(unit_key, unit, "right", 1),
        "wire_retainers": make_wire_retainers_part(unit_key, unit),
        "shell_mount_boss_set": make_shell_boss_set_part(unit_key, unit),
        "pickup_wiper_mounts": make_pickup_mounts_part(unit_key, unit),
        "cosmetic_sideframes": make_sideframe_part(unit_key, unit),
        "lighting_tray": make_lighting_tray_part(unit_key, unit),
    }
    for idx, x in enumerate(unit["truck_centers_mm"], start=1):
        parts[f"truck_bolster_{idx:02d}"] = make_truck_bolster_part(unit_key, unit, idx, x)
    if unit.get("powered_ready", False):
        parts["motor_cradle"] = make_motor_cradle_part(unit_key, unit)
    else:
        parts["optional_power_truck_adapter"] = make_optional_power_plate_part(unit_key, unit)
    return parts


def combine_parts_for_reference(name: str, parts: dict[str, Mesh]) -> Mesh:
    combined = Mesh(name)
    cursor_x = 0.0
    cursor_y = 0.0
    row_height = 0.0
    for idx, mesh in enumerate(parts.values()):
        bounds = mesh.bounds()["size"]
        if idx and cursor_x + bounds[0] > 260.0:
            cursor_x = 0.0
            cursor_y += row_height + 14.0
            row_height = 0.0
        moved = translate_mesh(mesh, cursor_x + bounds[0] / 2 + 2.0, cursor_y + bounds[1] / 2 + 2.0, 0.0)
        combined.extend(moved)
        cursor_x += bounds[0] + 10.0
        row_height = max(row_height, bounds[1])
    return combined


def add_coupler_mounts(mesh: Mesh, length: float, width: float, z: float) -> None:
    for x in (-length / 2 + 4.8, length / 2 - 4.8):
        add_box(mesh, (x, 0, z + 1.25), (9.0, 8.2, 2.5))
        add_annular_cylinder(mesh, (x, 0, z + 2.75), 2.5, 1.05, 1.0, 20, "z")


def add_shell_mount_bosses(mesh: Mesh, length: float, width: float, z: float) -> None:
    for x in (-length / 2 + 26.0, length / 2 - 26.0):
        for y in (-width / 2 + 4.0, width / 2 - 4.0):
            add_annular_cylinder(mesh, (x, y, z + 2.0), 2.9, 0.8, 4.0, 24, "z")


def make_detail_sprue(params: dict, variant: str) -> Mesh:
    m = Mesh(f"up80_detail_sprue_{variant}")
    x = -72.0
    for i in range(7):
        add_roof_fan(m, x + i * 24.0, -18.0, 1.0, 4.2)
    for i in range(12):
        add_box(m, (-80 + i * 14, 0, 2.0), (8.0, 0.8, 4.0))
        add_box(m, (-80 + i * 14, 6.0, 2.0), (8.0, 0.8, 4.0))
    for i in range(8):
        add_ladder(m, -78 + i * 22, 18.0, 0.5, 14.0, 1)
    for i in range(10):
        add_cylinder(m, (-85 + i * 18, 32.0, 2.0), 1.4, 3.0, 16, "z", True)
    add_box(m, (0, -35.0, 0.6), (180.0, 1.0, 1.2))
    add_box(m, (0, 38.0, 0.6), (180.0, 1.0, 1.2))
    return m


def make_test_coupons() -> Mesh:
    m = Mesh("up80_test_coupons")
    for i, wall in enumerate([0.8, 1.0, 1.25, 1.5, 1.8, 2.2]):
        x = -45 + i * 18
        add_box(m, (x, 0, 5.0), (12.0, wall, 10.0))
        add_annular_cylinder(m, (x, 13.0, 3.0), 3.2, 0.75 + i * 0.12, 6.0, 24, "z")
    for i in range(10):
        add_box(m, (-45 + i * 10, 28.0, 2.0), (5.5, 0.5, 4.0 + i * 0.45))
    add_box(m, (0, -20.0, 1.0), (118.0, 2.0, 2.0))
    return m


def write_step_from_mesh(mesh: Mesh, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "ISO-10303-21;",
        "HEADER;",
        "FILE_DESCRIPTION(('Faceted chassis interchange generated from the parametric source'),'2;1');",
        f"FILE_NAME('{path.name}','{now}',('Codex'),('OpenAI'),'{mesh.name}','Python mesh generator','');",
        "FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));",
        "ENDSEC;",
        "DATA;",
        "#1=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));",
        "#2=(PLANE_ANGLE_UNIT() NAMED_UNIT(*) SI_UNIT($,.RADIAN.));",
        "#3=(SOLID_ANGLE_UNIT() NAMED_UNIT(*) SI_UNIT($,.STERADIAN.));",
        "#4=UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.01000),#1,'distance_accuracy_value','');",
        "#5=(GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#4)) GLOBAL_UNIT_ASSIGNED_CONTEXT((#1,#2,#3)) REPRESENTATION_CONTEXT('ID1','3D'));",
    ]
    entity_id = 6
    face_ids = []
    for tri in mesh.triangles:
        point_ids = []
        for vertex in tri:
            lines.append(f"#{entity_id}=CARTESIAN_POINT('',({fmt(vertex[0])},{fmt(vertex[1])},{fmt(vertex[2])}));")
            point_ids.append(entity_id)
            entity_id += 1
        tri_normal = normal(tri)
        edge = vnorm(vsub(tri[1], tri[0]))
        if abs(edge[0]) + abs(edge[1]) + abs(edge[2]) < 1e-6:
            edge = (1.0, 0.0, 0.0)
        normal_id = entity_id
        lines.append(f"#{normal_id}=DIRECTION('',({fmt(tri_normal[0])},{fmt(tri_normal[1])},{fmt(tri_normal[2])}));")
        entity_id += 1
        ref_id = entity_id
        lines.append(f"#{ref_id}=DIRECTION('',({fmt(edge[0])},{fmt(edge[1])},{fmt(edge[2])}));")
        entity_id += 1
        axis_id = entity_id
        lines.append(f"#{axis_id}=AXIS2_PLACEMENT_3D('',#{point_ids[0]},#{normal_id},#{ref_id});")
        entity_id += 1
        plane_id = entity_id
        lines.append(f"#{plane_id}=PLANE('',#{axis_id});")
        entity_id += 1
        loop_id = entity_id
        lines.append(f"#{loop_id}=POLY_LOOP('',(#{point_ids[0]},#{point_ids[1]},#{point_ids[2]}));")
        entity_id += 1
        bound_id = entity_id
        lines.append(f"#{bound_id}=FACE_OUTER_BOUND('',#{loop_id},.T.);")
        entity_id += 1
        face_id = entity_id
        lines.append(f"#{face_id}=FACE_SURFACE('',(#{bound_id}),#{plane_id},.T.);")
        entity_id += 1
        face_ids.append(face_id)
    shell_id = entity_id
    face_list = ",".join(f"#{i}" for i in face_ids)
    lines.append(f"#{shell_id}=CLOSED_SHELL('{mesh.name}',({face_list}));")
    entity_id += 1
    solid_id = entity_id
    lines.append(f"#{solid_id}=MANIFOLD_SOLID_BREP('{mesh.name}',#{shell_id});")
    entity_id += 1
    rep_id = entity_id
    lines.append(f"#{rep_id}=ADVANCED_BREP_SHAPE_REPRESENTATION('{mesh.name}',(#{solid_id}),#5);")
    lines.append("ENDSEC;")
    lines.append("END-ISO-10303-21;")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_3mf(mesh: Mesh, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    vertices: list[Vec] = []
    index: dict[tuple[int, int, int], int] = {}
    triangles = []
    for tri in mesh.triangles:
        tri_idx = []
        for v in tri:
            key = (round(v[0] * 1000), round(v[1] * 1000), round(v[2] * 1000))
            if key not in index:
                index[key] = len(vertices)
                vertices.append(v)
            tri_idx.append(index[key])
        triangles.append(tuple(tri_idx))
    verts_xml = "\n".join(f'<vertex x="{fmt(v[0])}" y="{fmt(v[1])}" z="{fmt(v[2])}"/>' for v in vertices)
    tris_xml = "\n".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in triangles)
    model = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <metadata name="Title">{mesh.name}</metadata>
  <resources>
    <object id="1" type="model">
      <mesh>
        <vertices>
{verts_xml}
        </vertices>
        <triangles>
{tris_xml}
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="1"/>
  </build>
</model>
'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr("3D/3dmodel.model", model)


def write_dxf_plate(params: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = ["0", "SECTION", "2", "ENTITIES"]
    for key, unit in params["units"].items():
        L, W = unit["chassis_length_mm"], unit["chassis_width_mm"]
        offset = {"a_control": 0, "center_turbine": -60, "coal_tender": 60}[key]
        pts = [(-L / 2, -W / 2 + offset), (L / 2, -W / 2 + offset), (L / 2, W / 2 + offset), (-L / 2, W / 2 + offset)]
        parts += ["0", "LWPOLYLINE", "8", key, "90", str(len(pts)), "70", "1"]
        for x, y in pts:
            parts += ["10", fmt(x), "20", fmt(y)]
        for x in unit["truck_centers_mm"]:
            parts += ["0", "CIRCLE", "8", f"{key}_truck_pivots", "10", fmt(x), "20", fmt(offset), "40", "2.4"]
        for x in (-L / 2 + 8, L / 2 - 8, -L / 2 + 26, L / 2 - 26):
            parts += ["0", "CIRCLE", "8", f"{key}_screw_pilots", "10", fmt(x), "20", fmt(offset), "40", "0.85"]
    parts += ["0", "ENDSEC", "0", "EOF"]
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def write_svg_guides(params: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    paint = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="500" viewBox="-20 -20 840 320">']
    decal = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="500" viewBox="-20 -20 840 320">']
    x_cursor = 0.0
    for key, unit in params["units"].items():
        L = unit["shell_length_mm"]
        W = unit["shell_width_mm"]
        y = {"a_control": 20, "center_turbine": 115, "coal_tender": 220}[key]
        paint.append(f'<rect x="{fmt(x_cursor)}" y="{fmt(y)}" width="{fmt(L)}" height="{fmt(W)}" fill="none" stroke="black" stroke-width="1"/>')
        paint.append(f'<rect x="{fmt(x_cursor)}" y="{fmt(y + W * 0.52)}" width="{fmt(L)}" height="{fmt(W * 0.18)}" fill="none" stroke="red" stroke-dasharray="4 2"/>')
        paint.append(f'<text x="{fmt(x_cursor)}" y="{fmt(y - 4)}" font-size="8">{unit["display_name"]} paint mask: gray roof/bottom, Armour Yellow body, red stripe guide</text>')
        decal.append(f'<rect x="{fmt(x_cursor)}" y="{fmt(y)}" width="{fmt(L)}" height="{fmt(W)}" fill="none" stroke="black" stroke-width="1"/>')
        decal.append(f'<text x="{fmt(x_cursor + L * 0.08)}" y="{fmt(y + W * 0.42)}" font-size="8">UNION PACIFIC lettering zone</text>')
        decal.append(f'<text x="{fmt(x_cursor + L * 0.76)}" y="{fmt(y + W * 0.42)}" font-size="8">road number zone</text>')
        decal.append(f'<text x="{fmt(x_cursor)}" y="{fmt(y - 4)}" font-size="8">{unit["display_name"]} decal placement guide</text>')
    paint.append("</svg>")
    decal.append("</svg>")
    (out_dir / "up80_paint_masks.svg").write_text("\n".join(paint) + "\n", encoding="utf-8")
    (out_dir / "up80_decal_placement.svg").write_text("\n".join(decal) + "\n", encoding="utf-8")
    glazing = '<svg xmlns="http://www.w3.org/2000/svg" width="500" height="200" viewBox="0 0 220 90"><rect x="10" y="10" width="20" height="8" fill="none" stroke="black"/><rect x="38" y="10" width="20" height="8" fill="none" stroke="black"/><rect x="10" y="30" width="28" height="10" fill="none" stroke="black"/><rect x="45" y="30" width="28" height="10" fill="none" stroke="black"/><text x="10" y="62" font-size="8">Cut clear PETG/acetate glazing oversized, then trim to fit cab and number-board recesses.</text></svg>\n'
    (out_dir / "up80_glazing_masks.svg").write_text(glazing, encoding="utf-8")


def doc(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def write_docs(params: dict, manifest: dict) -> None:
    docs = ROOT / "docs"
    total_mm = params["prototype_total_length_ft"] * 304.8 / params["scale"]
    doc(ROOT / "README.md", f"""
    # HO Union Pacific #80 Coal Turbine v1.0.4

    This package is a cleaner printable kit for a three-unit HO scale Union Pacific #80 coal turbine: A/control unit, center turbine unit, and Challenger-style coal tender.

    v1.0.4 keeps one shell STL per unit and split chassis parts, then adds a denser reference-informed shell detail pass for phone/app review and first print checks.

    Scale target: 1:{params["scale"]}. The reported 226 ft prototype length scales to {total_mm:.1f} mm / {total_mm / 25.4:.2f} in overall.

    ## Included
    - Parametric Python source and JSON dimensions in `source/`.
    - One shell file per unit in `exports/stl/shells/`.
    - Split chassis part files in `exports/stl/chassis_parts/`.
    - Detail sprues and test coupons in `exports/stl/details/`.
    - 3MF print-set previews in `exports/3mf/`.
    - Faceted split-chassis STEP references and metal plate DXF in `exports/step/` and `exports/dxf/`.
    - Paint masks, decal placement guides, glazing guides, BOM, research notes, and build notes in `docs/`.

    ## Important Limits
    These files are generated from public dimensional references and photo/model-informed proportions. v1.0.4 adds visible grilles, doors, windows, lights, number boards, roof fittings, walkways, handrails, tender ribs, and coal/turbine equipment suggestions, but it is still not a blueprint-grade historical CAD master. Final fit depends on donor trucks, motors, couplers, printer, resin/plastic shrink, and builder wiring.
    """)
    doc(docs / "BOM.md", """
    # Bill of Materials

    ## Recommended Drive And Running Gear
    - A/control unit: HO ALCO PA donor mechanism if available, such as Walthers Proto/Proto 2000 or Rapido PA/PB. Use the printed chassis as an adapter pattern and adjust parameters to measured donor geometry.
    - Center turbine unit: commercial HO powered trucks or NWSL Stanton-style drives under cosmetic turbine/W-1 sideframes.
    - Tender: free-rolling HO tender trucks with optional pickup wipers; the chassis includes optional powered-truck envelope space.

    ## Couplers And Setup
    - Kadee #158 scale whisker couplers with insulated boxes.
    - Kadee #205 HO coupler height gauge.
    - 2-56 screws for coupler boxes; M1.4/M1.6 or 0-80 screws for shell retention depending on print material.

    ## DCC, Lighting, And Sound
    - ESU LokSound 5 or SoundTraxx TSU-2200 class decoder.
    - One diesel speaker in the A unit and one turbine speaker in the center unit.
    - Optional keep-alive/power pack in the tender or center unit.
    - Warm white LEDs for headlight/Mars/number boards; red/green marker LEDs; resistors sized for the chosen decoder outputs.
    - Micro JST connectors between units, fine decoder wire, phosphor-bronze pickup wire.

    ## Materials
    - High-detail resin for shells, vents, grilles, cab details, fans, and tender body.
    - PETG/ABS/ASA or tough resin for chassis prototypes; brass, aluminum, or stainless sheet for final chassis plates.
    - Clear PETG/acetate for glazing.
    - Tungsten putty, lead-free shot, or machined ballast blocks for weight.
    - Phosphor-bronze or brass wire for handrails where resin would be fragile.
    """)
    part_lines = ["# Chassis Parts", "", "Each unit now has one shell file and multiple separate chassis parts.", ""]
    for key, unit in params["units"].items():
        part_dir = ROOT / "exports" / "stl" / "chassis_parts" / key
        part_lines.append(f"## {unit['display_name']}")
        for path in sorted(part_dir.glob("*.stl")):
            part_lines.append(f"- `{path.relative_to(ROOT).as_posix()}`")
        part_lines.append("")
    part_lines += [
        "## Assembly Notes",
        "- Print base plate flat and test truck swing before gluing or screwing accessories.",
        "- Coupler pockets, bolsters, decoder tray, speaker box, and ballast boxes are separate so they can be reprinted or adjusted independently.",
        "- Use the DXF plate as the metal-cutting reference if replacing printed base plates with brass, aluminum, or stainless.",
    ]
    doc(docs / "CHASSIS_PARTS.md", "\n".join(part_lines))
    doc(docs / "PAINT_AND_DECAL_PLAN.md", """
    # Paint And Decal Plan

    ## Colors
    - Tru-Color TCP-026 Union Pacific Armour Yellow.
    - Tru-Color TCP-025 Union Pacific Harbor Mist Gray.
    - Black or grimy black for roof exhaust zones, trucks, and underframe.
    - Aluminum/stainless color for grilles and metal detail.
    - Gloss clear before decals; satin or flat clear after decals/weathering.

    ## Decals And Stickers
    - Recommended commercial decal: Microscale HO 87-580 Union Pacific #8080 coal turbine locomotive, if available.
    - The package includes placement guides for original #80 / 80B and later #8080 / 80B variants.
    - UP logo artwork is not bundled; use licensed decals or user-supplied art.

    ## Finish Sequence
    1. Wash and fully cure printed parts.
    2. Sand and fill visible print artifacts.
    3. Prime plastic/resin/metal; use metal prep for brass/aluminum chassis.
    4. Spray Harbor Mist Gray areas and roof/underbody dark areas.
    5. Mask and spray Armour Yellow body areas.
    6. Apply red stripe/lettering decals over gloss.
    7. Seal with satin or flat clear.
    8. Add restrained coal dust, turbine exhaust soot, road grime, and truck weathering.
    """)
    doc(docs / "BUILD_GUIDE.md", """
    # Build Guide

    ## Printing
    - Use `exports/stl/shells/` for the three one-piece shells.
    - Use `exports/stl/chassis_parts/` for the split chassis parts.
    - Use `exports/stl/details/` for detail sprues and test coupons.
    - Use `exports/3mf/` for quick print-set previews.
    - Print small details from `up80_detail_sprue.stl` separately for cleaner painting and easier replacement.
    - Print `up80_test_coupons.stl` before committing to full shells.

    ## Chassis
    - The A/control and center turbine chassis are powered-ready split assemblies.
    - The tender chassis is a rolling/unpowered split assembly by default, with lighting, pickup, speaker, keep-alive, and optional power-adapter provisions.
    - Drill pilot holes to final screw size after printing or machining.
    - If using metal plates, cut from `exports/dxf/up80_chassis_plates.dxf`, then transfer printed mounts/trays as needed.

    ## Assembly
    - Fit donor trucks and motor components before painting shells.
    - Confirm Kadee coupler height before final wiring.
    - Use removable connectors between units so shells can be removed without desoldering.
    - Add weight gradually and verify each powered unit independently before coupling the full train.
    """)
    doc(docs / "RESEARCH_NOTES.md", """
    # Research Notes

    Confirmed/included facts:
    - UP #80 was a three-unit coal-burning gas turbine-electric experiment built in 1962.
    - The consist used a modified ALCO PA-style control unit, a W-1-derived turbine/electric center unit, and a Challenger-style coal tender.
    - Reported overall length is 226 ft, which scales to about 790.9 mm in HO at 1:87.1.
    - The prototype was originally #80 and later renumbered #8080; model/decal guides include both.
    - Existing OMI/MTH model references support a powered lead unit, powered center unit, and unpowered tender arrangement.

    Modeled as inferred/approximate:
    - Exact side grille count, small door placement, roof equipment spacing, handrail routing, tender equipment, and underframe equipment are photo/model-informed approximations.
    - Chassis mechanics are deliberately functional rather than historically exact.
    - Commercial donor drivetrain interfaces are parametric and should be measured against parts on hand before final machining.

    Source links used in planning:
    - https://locomotive.fandom.com/wiki/Union_Pacific_No._80
    - https://www.mthtrains.com/products/20-2678-1
    - https://www.mthtrains.com/products/20-21055-1
    - https://www.brasstrains.com/classic/Product/Detail/068360/HO-Scale-Brass-Model-Train-OMI-5096-UP-Union-Pacific-8080-Ex-80-Coal-Turbine-Custom
    - https://trainiax.net/mephase-alcofa.php
    - https://trucolorpaint.com/products/paint/
    - https://houseoftrains.com/products/microscale-87-580-ho-union-pacific-8080-coal-turbine-locomotive
    """)
    doc(ROOT / "RELEASE_NOTES.md", """
    # v1.0.4

    Android-control fix plus improved visible shell detail for the HO Union Pacific #80 coal turbine.

    ## Added
    - Native Android catalog app source package for v1.0.4, generated from the v1.0.4 STL catalog.
    - Android immersive mode so phone navigation buttons hide during preview and return by edge swipe.
    - Extra bottom padding in the app command area for phones using gesture or three-button navigation.
    - More detailed A/control shell: PA-style windows, number boards, dual headlights, Mars/marker lights, doors, handrails, grilles, rivets, roof hatches, horns, fans, and pilot steps.
    - More detailed center turbine shell: dense side grille texture, see-through equipment suggestions, roof fans/stacks/hatches, walkways, handrails, doors, ladders, and pilot steps.
    - More detailed tender shell: coal load, tender ribs/rivets, service doors, ladders, handrails, rear lights, pulverizer/crusher equipment, hatches, and deck fittings.
    - Continued one-shell-per-unit and split chassis part organization.

    ## Assets
    - `up-80-coal-turbine-ho-v1.0.4.zip`: printable/model package with STL, 3MF, STEP, DXF, docs, source, paint/decal plan, BOM, and validation report.
    - `up80-android-app-v1.0.4-source.zip`: native Android app source package.
    - `up80-catalog-v1.0.4-debug.apk`: Android debug APK, built by GitHub Actions after the tag is pushed.

    ## Known Limits
    - STEP files are faceted interchange exports generated without a local CAD kernel.
    - Donor drive mounting should be adjusted from measured parts before final metal cutting.
    - Exterior accuracy is still limited by public/reference-model data until v1.1 CAD and printer feedback are available.
    """)
    doc(ROOT / "NOTICE.md", """
    # Notice

    Union Pacific names, logos, paint schemes, and related marks may be trademarks of their owners. This package does not bundle protected logo artwork. Use licensed decals or user-supplied artwork where required.
    """)


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_stl(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {
        "file": str(path.relative_to(ROOT)),
        "ascii_stl": text.startswith("solid ") and "endsolid" in text,
        "facet_count": text.count("facet normal"),
        "size_bytes": path.stat().st_size,
        "sha256": hash_file(path),
    }


def collect_manifest(params: dict, meshes: dict[str, Mesh]) -> dict:
    files = []
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and "release" not in path.parts:
            files.append({
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "size_bytes": path.stat().st_size,
                "sha256": hash_file(path),
            })
    return {
        "project": params["project"],
        "version": params["version"],
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scale": params["scale"],
        "target_overall_length_mm": params["prototype_total_length_ft"] * 304.8 / params["scale"],
        "unit_count": 3,
        "chassis_count": 3,
        "shell_file_count": len(list((ROOT / "exports" / "stl" / "shells").glob("*.stl"))),
        "chassis_part_file_count": len(list((ROOT / "exports" / "stl" / "chassis_parts").rglob("*.stl"))),
        "mesh_bounds_mm": {name: mesh.bounds() for name, mesh in meshes.items()},
        "files": files,
    }


def write_release_zip() -> Path:
    release_dir = ROOT / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    zip_path = release_dir / "up-80-coal-turbine-ho-v1.0.4.zip"
    if zip_path.exists():
        zip_path = release_dir / f"up-80-coal-turbine-ho-v1.0.4-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or path == zip_path:
                continue
            if ".git" in path.parts or "release" in path.relative_to(ROOT).parts:
                continue
            z.write(path, path.relative_to(ROOT))
    return zip_path


def copy_original_prompt() -> None:
    source_prompt = ROOT.parents[2] / "New Text Document.txt"
    if source_prompt.exists():
        shutil.copyfile(source_prompt, ROOT / "source" / "original_prompt.txt")


def clean_generated_outputs() -> None:
    for rel in ("exports", "docs", "release"):
        path = ROOT / rel
        if path.exists():
            shutil.rmtree(path)
    for rel in ("README.md", "RELEASE_NOTES.md", "NOTICE.md", "manifest.json", "validation_report.json"):
        path = ROOT / rel
        if path.exists():
            path.unlink()


def generate() -> None:
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    clean_generated_outputs()
    copy_original_prompt()
    for rel in ["exports/stl/shells", "exports/stl/chassis_parts", "exports/stl/details", "exports/3mf", "exports/step", "exports/dxf", "exports/svg", "docs", "release"]:
        (ROOT / rel).mkdir(parents=True, exist_ok=True)
    meshes: dict[str, Mesh] = {}
    chassis_part_index: dict[str, list[str]] = {}
    for key, unit in params["units"].items():
        shell = make_body_shell(key, unit, "resin")
        shell.name = f"{key}_shell"
        meshes[shell.name] = shell
        shell.write_stl(ROOT / "exports" / "stl" / "shells" / f"{shell.name}.stl")
        parts = make_chassis_part_meshes(key, unit)
        chassis_part_index[key] = []
        for part_name, mesh in parts.items():
            meshes[mesh.name] = mesh
            part_path = ROOT / "exports" / "stl" / "chassis_parts" / key / f"{mesh.name}.stl"
            mesh.write_stl(part_path)
            chassis_part_index[key].append(str(part_path.relative_to(ROOT)).replace("\\", "/"))
        combined = combine_parts_for_reference(f"{key}_split_chassis_reference", parts)
        meshes[combined.name] = combined
        write_step_from_mesh(combined, ROOT / "exports" / "step" / f"{key}_split_chassis_reference.step")
        print_set = Mesh(f"{key}_shell_and_split_chassis_print_set")
        print_set.extend(shell)
        moved_chassis = translate_mesh(combined, 0.0, unit["shell_width_mm"] + 20.0, 0.0)
        print_set.extend(moved_chassis)
        write_3mf(print_set, ROOT / "exports" / "3mf" / f"{key}_shell_and_split_chassis_print_set.3mf")
    sprue = make_detail_sprue(params, "resin")
    sprue.name = "up80_detail_sprue"
    meshes[sprue.name] = sprue
    sprue.write_stl(ROOT / "exports" / "stl" / "details" / "up80_detail_sprue.stl")
    coupons = make_test_coupons()
    meshes[coupons.name] = coupons
    coupons.write_stl(ROOT / "exports" / "stl" / "details" / "up80_test_coupons.stl")
    write_dxf_plate(params, ROOT / "exports" / "dxf" / "up80_chassis_plates.dxf")
    write_svg_guides(params, ROOT / "exports" / "svg")
    validation = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stl_files": [validate_stl(path) for path in sorted((ROOT / "exports" / "stl").rglob("*.stl"))],
        "shell_stl_files": [str(path.relative_to(ROOT)).replace("\\", "/") for path in sorted((ROOT / "exports" / "stl" / "shells").glob("*.stl"))],
        "chassis_part_index": chassis_part_index,
        "overall_length_check_mm": params["prototype_total_length_ft"] * 304.8 / params["scale"],
        "minimum_radius_mm": params["track"]["minimum_radius_mm"],
    }
    (ROOT / "validation_report.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    manifest = collect_manifest(params, meshes)
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_docs(params, manifest)
    manifest = collect_manifest(params, meshes)
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    zip_path = write_release_zip()
    print(json.dumps({
        "root": str(ROOT),
        "mesh_count": len(meshes),
        "zip": str(zip_path),
        "zip_size": zip_path.stat().st_size,
        "stl_count": len(list((ROOT / "exports" / "stl").rglob("*.stl"))),
        "shell_file_count": manifest["shell_file_count"],
        "chassis_part_file_count": manifest["chassis_part_file_count"],
        "step_count": len(list((ROOT / "exports" / "step").glob("*.step"))),
        "overall_length_mm": manifest["target_overall_length_mm"],
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true", help="Generate all model exports and docs")
    args = parser.parse_args()
    if not args.generate:
        parser.print_help()
        return
    generate()


if __name__ == "__main__":
    main()
