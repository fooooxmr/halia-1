#!/usr/bin/env python3
"""HALIA-1 — improved hallux valgus wire guide, print-ready prototype.

Engineering prototype for bench fit only. Not a medical device.
Geometry is an original design informed by the published description of the
Dzhanelidze guide (Oleinik et al., 2023; Belenkiy et al., 2025), not a copy
of patent drawings.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

import cadquery as cq
import numpy as np
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex, BRepBuilderAPI_Transform
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.TopAbs import TopAbs_IN, TopAbs_ON
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXPORT = os.path.join(ROOT, "export")
STL = os.path.join(EXPORT, "stl")
STEP = os.path.join(EXPORT, "step")
FIX = os.path.join(EXPORT, "fixture")

# --- clinical / functional targets (mm, degrees) ---
OBL_NOM = 12.0          # distal obliquity; hole axis is 90+12 = 102° to the shaft
HOLE_ANGLE = 90.0 + OBL_NOM
SHAFT_R = 7.0           # design-point metatarsal, Ø14
EXIT_X = -10.0          # wire 1 leaves the lateral cortex this far proximal of the cut
WIRE_SPACING = 10.0     # second wire is this far distal, parallel
WIRE_D = 1.6
BORE_D = 1.80           # printed bore; ream to 1.70–1.75 for a 1.6 mm wire
SLEEVE_OD = 7.0
T_BUILD = 8.0           # translation shown in the master assembly
T_MAX = 12.0
CORTEX_Y = SHAFT_R      # medial cortex of the Ø14 design bone
INDEX_Y = 17.20         # scale reading face on the frame
STOP_GAP = 0.25
CHAN_CLEAR = 0.25       # per side, resin slide fit

# paddle / channel
PAD_X0, PAD_X1 = 1.90, 3.40
PAD_ZC = 2.25
CHAN_X0, CHAN_X1 = PAD_X0 - CHAN_CLEAR, PAD_X1 + CHAN_CLEAR
CHAN_ZC = PAD_ZC + CHAN_CLEAR
CHAN_Y0, CHAN_Y1 = 11.00, INDEX_Y

# tongue blade (size M)
TONGUE_X_TIP = -36.0    # proximal tip, inside the canal
TONGUE_X_SOLID = -8.0   # slot ends here; distal of this the blade is solid
TONGUE_X_END = -5.2
TONGUE_HY = 1.20        # half-thickness, medial-lateral
TONGUE_HZ = 3.75        # half-width, dorsal-plantar
SLOT_HZ = 1.75

HINGE_Y = 14.20
ARM_R = 50.0
ARM_SWEEP = 6.0         # ±6° → hole angles 96 / 102 / 108


def _ang(obl: float):
    a = math.radians(obl)
    return math.sin(a), math.cos(a), math.tan(a)


def wire_point(exit_x: float, y: float, obl: float) -> np.ndarray:
    """Point on the wire axis at a given medial coordinate Y.

    Axis passes through the lateral-cortex exit (exit_x, -SHAFT_R, 0)
    and runs at `obl` degrees distal of pure medial-lateral.
    Going medial (+Y), X moves proximal.
    """
    _s, _c, tn = _ang(obl)
    x = exit_x - (y - (-SHAFT_R)) * tn
    return np.array([x, y, 0.0])


def hinge_xy() -> np.ndarray:
    p = wire_point(EXIT_X, HINGE_Y, OBL_NOM)
    return p[:2].copy()


def face_y(T: float) -> float:
    return CORTEX_Y - T


# ---------- CAD helpers ----------

def _wp(shape) -> cq.Workplane:
    return cq.Workplane(obj=shape)


def _wrapped(shape):
    return shape.wrapped if hasattr(shape, "wrapped") else shape


def fuse(a, b):
    return a.union(b)


def cut(a, b):
    return a.cut(b)


def fuse_all(parts):
    acc = parts[0]
    for p in parts[1:]:
        acc = fuse(acc, p)
    return acc


def cut_all(base, tools):
    acc = base
    for t in tools:
        acc = cut(acc, t)
    return acc


def box(cx, cy, cz, lx, ly, lz):
    return cq.Workplane("XY").box(lx, ly, lz).translate((cx, cy, cz))


def bbox(wp):
    bb = wp.val().BoundingBox()
    return (bb.xmin, bb.ymin, bb.zmin, bb.xmax, bb.ymax, bb.zmax)


def volume(wp) -> float:
    return wp.val().Volume()


def cyl_along(p0, p1, r):
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    v = p1 - p0
    h = float(np.linalg.norm(v))
    if h < 1e-9:
        raise ValueError("zero-length cylinder")
    d = v / h
    wp = cq.Workplane("XY").circle(float(r)).extrude(h)
    z = np.array([0.0, 0.0, 1.0])
    c = np.cross(z, d)
    n = float(np.linalg.norm(c))
    if n < 1e-8:
        if d[2] < 0:
            wp = wp.rotate((0, 0, 0), (1, 0, 0), 180)
    else:
        ang = math.degrees(math.acos(float(np.clip(np.dot(z, d), -1, 1))))
        # right-hand about (z × d) rotates +Z toward +d? verified by self-test;
        # the sign is corrected there if the first try points backwards.
        wp = wp.rotate((0, 0, 0), (float(c[0]), float(c[1]), float(c[2])), ang)
    return wp.translate((float(p0[0]), float(p0[1]), float(p0[2])))


_CYL_SIGN = [1]


def cyl_along_checked(p0, p1, r):
    wp = cyl_along(p0, p1, r)
    if _CYL_SIGN[0] < 0:
        # rebuild with flipped angle — handled by swapping ends
        wp = cyl_along(p1, p0, r)
    return wp


def calibrate_cylinder():
    """Make sure cyl_along points from p0 to p1. Flip convention if needed."""
    probe = cyl_along((0, 0, 0), (10, 0, 0), 1.0)
    bb = bbox(probe)
    if bb[3] > 9.0 and bb[0] > -0.5:
        _CYL_SIGN[0] = 1
        return
    probe = cyl_along((10, 0, 0), (0, 0, 0), 1.0)
    bb = bbox(probe)
    if bb[3] > 9.0 and bb[0] > -0.5:
        _CYL_SIGN[0] = -1
        return
    raise RuntimeError(f"cylinder orientation failed, bbox={bbox(cyl_along((0,0,0),(10,0,0),1))}")


def hex_prism(cx, cy, cz, af, length, axis="Y"):
    """Regular hex prism. `af` is across flats. Length along `axis`."""
    # CQ polygon() diameter is the corner-to-corner diameter.
    corner = af / math.cos(math.radians(30.0))
    if axis == "Y":
        wp = (
            cq.Workplane("XZ")
            .center(cx, cz)
            .polygon(6, corner)
            .extrude(length)
            .translate((0, cy - length / 2.0, 0))
        )
    elif axis == "Z":
        wp = (
            cq.Workplane("XY")
            .center(cx, cy)
            .polygon(6, corner)
            .extrude(length)
            .translate((0, 0, cz - length / 2.0))
        )
    else:
        raise ValueError(axis)
    return wp


def mirror_y(wp):
    tr = gp_Trsf()
    tr.SetMirror(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)))
    sh = BRepBuilderAPI_Transform(_wrapped(wp.val()), tr, True, False).Shape()
    return cq.Workplane(obj=cq.Shape.cast(sh))


def point_state(shape, p, tol=1e-5):
    cl = BRepClass3d_SolidClassifier(
        _wrapped(shape), gp_Pnt(float(p[0]), float(p[1]), float(p[2])), tol
    )
    return cl.State()


def point_inside(shape, p) -> bool:
    return point_state(shape, p) in (TopAbs_IN, TopAbs_ON)


def min_dist(shape, pts) -> float:
    sh = _wrapped(shape)
    best = 1e9
    for p in pts:
        vx = BRepBuilderAPI_MakeVertex(gp_Pnt(float(p[0]), float(p[1]), float(p[2]))).Shape()
        dss = BRepExtrema_DistShapeShape(sh, vx)
        dss.Perform()
        if dss.IsDone():
            best = min(best, dss.Value())
    return best


def shape_gap(a, b) -> float:
    dss = BRepExtrema_DistShapeShape(_wrapped(a.val()), _wrapped(b.val()))
    dss.Perform()
    if not dss.IsDone():
        return -1.0
    return float(dss.Value())


def rot_about_hinge(p, deg):
    H = hinge_xy()
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    x, y = float(p[0]) - float(H[0]), float(p[1]) - float(H[1])
    return np.array([
        float(H[0]) + c * x - s * y,
        float(H[1]) + s * x + c * y,
        float(p[2]),
    ])


def _exit_x(obl: float) -> float:
    """Where the rotated wire crosses the lateral cortex y=-R, z=0."""
    delta = obl - OBL_NOM
    a = rot_about_hinge(wire_point(EXIT_X, -SHAFT_R, OBL_NOM), delta)
    b = rot_about_hinge(wire_point(EXIT_X, 10.0, OBL_NOM), delta)
    # line a + t (b-a), solve Y = -SHAFT_R
    dy = b[1] - a[1]
    t = (-SHAFT_R - a[1]) / dy
    return float(a[0] + t * (b[0] - a[0]))


def axis_samples(exit_x, obl, y0, y1, n=40):
    ys = np.linspace(y0, y1, n)
    return [wire_point(exit_x, float(y), obl) for y in ys]


def lay_on_bed(wp, mode: str):
    """Rotate a part so the chosen functional axis points +Z, then sit it on Z=0."""
    if mode == "Yup":
        wp = wp.rotate((0, 0, 0), (1, 0, 0), -90)
    elif mode == "bore":
        # nominal bore is ~12° off +Y toward -X; rotate so that direction → +Z
        # direction of bore from lateral to medial is (-sin, cos, 0). Printer axis
        # should follow the bore. Rotate +Y to +Z first (−90 about X), then
        # roll −12° about Y so the obliquity stands vertical.
        wp = wp.rotate((0, 0, 0), (1, 0, 0), -90)
        wp = wp.rotate((0, 0, 0), (0, 1, 0), -OBL_NOM)
    elif mode == "as_is":
        pass
    else:
        raise ValueError(mode)
    bb = bbox(wp)
    wp = wp.translate((-bb[0] + 2.0, -bb[1] + 2.0, -bb[2]))
    return wp


def export_stl(wp, path, tol=0.025, ang=0.08):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cq.exporters.export(wp, path, tolerance=tol, angularTolerance=ang)
    # Drop boolean dust smaller than 1 mm³ so the slicer sees one body.
    try:
        import trimesh
        mesh = trimesh.load(path, force="mesh")
        pieces = mesh.split(only_watertight=False)
        keep = [p for p in pieces if abs(p.volume) >= 1.0]
        if keep and len(keep) != len(pieces):
            (keep[0] if len(keep) == 1 else trimesh.util.concatenate(keep)).export(path)
    except Exception as exc:
        print("  stl cleanup skipped:", exc)


def export_step(wp, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cq.exporters.export(wp, path)


# ---------- parts ----------

@dataclass
class TongueSize:
    name: str
    hy: float
    hz: float
    slot_hz: float


SIZES = {
    "S": TongueSize("S", 1.00, 3.15, 1.50),
    "M": TongueSize("M", TONGUE_HY, TONGUE_HZ, SLOT_HZ),
    "L": TongueSize("L", 1.45, 4.35, 1.75),
}


def build_tongue(size: TongueSize):
    """Intramedullary fork + portal neck + dorsal flange. Mounts on one frame."""
    hy, hz, shz = size.hy, size.hz, size.slot_hz
    parts = []
    # main blade, proximal tip through the solid distal stub
    parts.append(box(
        (TONGUE_X_TIP + TONGUE_X_END) / 2, 0, 0,
        TONGUE_X_END - TONGUE_X_TIP, 2 * hy, 2 * hz,
    ))
    # dorsal bridge over wire 2, then down into the portal neck. One solid.
    parts.append(box((-6.2 + -4.4) / 2, (0.0 + 1.7) / 2, (1.7 + 4.3) / 2, 1.8, 1.7, 2.6))
    parts.append(box((-6.2 + -0.3) / 2, (0.55 + 2.15) / 2, (2.55 + 4.35) / 2, 5.9, 1.60, 1.80))
    parts.append(box((-0.9 + 1.25) / 2, (1.7 + 5.3) / 2, (1.15 + 4.25) / 2, 2.15, 3.6, 3.10))
    # portal neck (side-by-side with the paddle, distal of wire 2)
    parts.append(box((-0.5 + 1.15) / 2, (4.3 + 10.3) / 2, 0, 1.65, 6.0, 4.0))
    # riser just outside the skin, lateral of the frame
    parts.append(box((0.45 + 1.35) / 2, (10.0 + 11.65) / 2, (-1.6 + 7.3) / 2, 0.90, 1.65, 8.9))
    # dorsal bar to the flange — fat overlap so the fuse is one solid
    parts.append(box((0.40 + 7.6) / 2, (10.2 + 12.35) / 2, (6.50 + 8.05) / 2, 7.2, 2.15, 1.55))
    # flange over the shelf. Wide enough that the Ø3.4 lock hole does not split it.
    parts.append(box((2.8 + 8.8) / 2, (12.0 + 16.2) / 2, (6.40 + 9.10) / 2, 6.0, 4.2, 2.70))
    tongue = fuse_all(parts)
    # open proximal fork: slot through Y, open past the proximal tip, stop at x=-8
    slot = box(
        (TONGUE_X_TIP - 2 + TONGUE_X_SOLID) / 2, 0, 0,
        (TONGUE_X_SOLID - (TONGUE_X_TIP - 2)), 2 * hy + 3.0, 2 * shz,
    )
    tongue = cut(tongue, slot)
    # lock-screw clearance Ø3.4 through the flange, aligned with the shelf hole
    tongue = cut(tongue, cyl_along_checked((5.8, 14.1, 5.6), (5.8, 14.1, 10.4), 1.70))
    return tongue


def angle_geom():
    """Hinge, arm direction (proximal-medial) and the angle-lock post."""
    H = hinge_xy()
    direction = np.array([-math.sin(math.radians(42.0)), math.cos(math.radians(42.0))])
    boss = np.array([float(H[0]), float(H[1])]) + ARM_R * direction
    return H, direction, boss


def build_frame():
    H, direction, boss = angle_geom()
    hx, hy = float(H[0]), float(H[1])
    parts = []
    # proximal block
    parts.append(box((-34 + -22) / 2, (11.2 + 17.6) / 2, 0, 12.0, 6.4, 16.0))
    # dorsal + plantar beams across the wire window
    parts.append(box((-22 + -2.4) / 2, (10.8 + 17.8) / 2, (6.7 + 10.3) / 2, 19.6, 7.0, 3.6))
    parts.append(box((-22 + -2.4) / 2, (10.8 + 17.8) / 2, (-10.3 + -6.7) / 2, 19.6, 7.0, 3.6))
    # link from the dorsal beam into the top of the distal block
    parts.append(box((-3.2 + 2.6) / 2, (15.2 + 16.9) / 2, (6.2 + 10.5) / 2, 5.8, 1.7, 4.3))
    # distal block (channel, shelf, pointer)
    parts.append(box((0.45 + 8.6) / 2, (11.15 + INDEX_Y) / 2, (-7.5 + 8.6) / 2, 8.15, INDEX_Y - 11.15, 16.1))
    # rails, top strap and end plate — the paddle tower slides between the rails
    # tower envelope x 0.60..5.10, z -3.6..8.0; at T=0 the tower ends at y=40.45
    parts.append(box((-0.70 + 0.28) / 2, (16.45 + 41.80) / 2, (0.30 + 9.40) / 2, 0.98, 25.35, 9.10))
    parts.append(box((5.42 + 6.90) / 2, (16.45 + 41.80) / 2, (0.30 + 9.40) / 2, 1.48, 25.35, 9.10))
    parts.append(box((-1.20 + 6.90) / 2, (16.45 + 41.80) / 2, (8.35 + 9.55) / 2, 8.10, 25.35, 1.20))
    parts.append(box((-1.20 + 6.90) / 2, (40.70 + 44.40) / 2, (0.30 + 9.55) / 2, 8.10, 3.70, 9.25))
    # shelf for the tongue flange
    parts.append(box((2.6 + 9.0) / 2, (12.15 + 16.40) / 2, (3.40 + 6.20) / 2, 6.4, 4.25, 2.80))
    # osteotomy pointer at x = 0
    parts.append(box((-0.15 + 0.70) / 2, (11.2 + 13.4) / 2, (-6.4 + -4.2) / 2, 0.85, 2.2, 2.2))
    # yoke arms
    parts.append(box((-31.0 + -23.5) / 2, (2.3 + 11.4) / 2, (7.55 + 10.6) / 2, 7.5, 9.1, 3.05))
    parts.append(box((-31.0 + -23.5) / 2, (2.3 + 11.4) / 2, (-10.6 + -7.55) / 2, 7.5, 9.1, 3.05))
    # clevis body. The slot cut opens it; a short dorsal lug stays only over the eye.
    parts.append(box(hx, hy, (4.6 + 10.05) / 2, 12.0, 11.0, 5.45))
    parts.append(box(hx + 0.6, hy, (10.25 + 12.40) / 2, 10.0, 6.2, 2.15))
    # dogleg around the turret riser: z 9.80–10.60 sits between the bridge and the arm
    parts.append(box((-11.0 + -6.2) / 2, (14.8 + 17.6) / 2, (9.80 + 12.20) / 2, 4.8, 2.8, 2.40))
    parts.append(box((-8.6 + -5.8) / 2, (16.8 + 36.8) / 2, (9.80 + 10.60) / 2, 2.8, 20.0, 0.80))
    parts.append(_bar(np.array([-7.2, 36.4]), boss, z0=9.80, z1=10.60, half_w=2.5))
    parts.append(box(float(boss[0]), float(boss[1]), (7.6 + 10.60) / 2, 18.0, 18.0, 3.00))
    frame = fuse_all(parts)
    # paddle channel
    frame = cut(frame, box(
        (CHAN_X0 + CHAN_X1) / 2, (CHAN_Y0 + CHAN_Y1) / 2 + 0.2, 0,
        CHAN_X1 - CHAN_X0, (CHAN_Y1 - CHAN_Y0) + 0.6, 2 * CHAN_ZC,
    ))
    # clevis slot: the eye sits in it and the bridge leaves medially. Lugs remain above and below.
    frame = cut(frame, box(hx, hy + 6.0, (7.55 + 10.10) / 2, 5.10, 16.0, 2.55))
    frame = cut(frame, cyl_along_checked((hx, hy, 4.4), (hx, hy, 13.2), 1.70))
    # yoke conforming scoop — design bone plus 1.35 mm of soft tissue
    frame = cut(frame, cyl_along_checked((-42, 0, 0), (-18, 0, 0), SHAFT_R + 1.35))
    # translation screw through the end plate only (the shank must not enter the paddle channel)
    frame = cut(frame, cyl_along_checked((2.65, 40.40, 5.20), (2.65, 45.2, 5.20), 1.70))
    frame = cut(frame, cyl_along_checked((2.65, 42.55, 5.20), (2.65, 45.4, 5.20), 3.20))
    # angle-lock hole and a nut trap that opens to the side of the post
    frame = cut(frame, cyl_along_checked(
        (float(boss[0]), float(boss[1]), 6.8),
        (float(boss[0]), float(boss[1]), 11.3),
        1.70,
    ))
    nut = hex_prism(float(boss[0]), float(boss[1]), 8.55, 5.70, 2.6, axis="Z")
    mouth = box(float(boss[0]) + 6.0, float(boss[1]), 8.55, 12.0, 5.75, 2.7)
    frame = cut(cut(frame, nut), mouth)
    # pocket so the tongue flange and its dorsal bar sit on the shelf instead of inside the block
    frame = cut(frame, box((2.5 + 9.1) / 2, (11.85 + 16.50) / 2, (6.25 + 11.2) / 2, 6.6, 4.65, 4.95))
    frame = cut(frame, box((0.15 + 7.90) / 2, (11.00 + 12.55) / 2, (6.30 + 8.30) / 2, 7.75, 1.55, 2.00))
    frame = cut(frame, box((0.20 + 1.60) / 2, (10.90 + 12.10) / 2, (-1.9 + 7.6) / 2, 1.40, 1.20, 9.5))
    # tongue-lock hole through the shelf + nut trap from plantar
    frame = cut(frame, cyl_along_checked((5.8, 14.1, 2.8), (5.8, 14.1, 7.2), 1.70))
    nut2 = hex_prism(5.8, 14.1, 4.55, 5.70, 2.6, axis="Z")
    mouth2 = box(5.8, 14.1 - 5.0, 4.55, 5.75, 10.0, 2.7)
    frame = cut(cut(frame, nut2), mouth2)
    # datum notch on the pointer, apex at x = 0
    frame = cut(frame, box(0.0, 12.3, -5.3, 0.50, 1.4, 1.6))
    return frame, {"hinge_xy": [hx, hy], "boss_xy": [float(boss[0]), float(boss[1])]}


def _bar(a, b, z0, z1, half_w):
    """Rectangular bar in plan from point a to b, constant Z, width 2*half_w."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    d = b - a
    length = float(np.linalg.norm(d))
    ang = math.degrees(math.atan2(d[1], d[0]))
    wp = box(length / 2.0, 0, (z0 + z1) / 2.0, length, 2 * half_w, z1 - z0)
    wp = wp.rotate((0, 0, 0), (0, 0, 1), ang)
    wp = wp.translate((float(a[0]), float(a[1]), 0))
    return wp


def build_blade(T: float):
    """Translating paddle. Face Y = 7 - T. Scale reads at the index face."""
    tip = face_y(T)
    # shoulder sits STOP_GAP medial of the index at T=0
    shoulder = tip + (INDEX_Y - CORTEX_Y) + STOP_GAP
    # lug (nut-block face) sits STOP_GAP medial of the index at T=12
    lug = shoulder + T_MAX
    y_end = lug + 11.0
    parts = []
    # slim paddle, including a 2.2 mm foot flare near the tip (Z only)
    parts.append(box(
        (PAD_X0 + PAD_X1) / 2, (tip + 2.4 + y_end) / 2, 0,
        PAD_X1 - PAD_X0, y_end - (tip + 2.4), 2 * PAD_ZC,
    ))
    parts.append(box(
        (PAD_X0 + PAD_X1) / 2, (tip + tip + 2.6) / 2, 0,
        PAD_X1 - PAD_X0, 2.6, 2 * (PAD_ZC + 0.65),
    ))
    # nut block / stop lug. Starts at `lug`. Wider, with a dorsal tower for the nut.
    parts.append(box(
        (0.6 + 5.1) / 2, (lug + y_end) / 2, (-3.6 + 3.6) / 2,
        4.5, y_end - lug, 7.2,
    ))
    parts.append(box(
        (0.9 + 4.6) / 2, (lug + y_end) / 2, (2.2 + 8.0) / 2,
        3.7, y_end - lug, 5.8,
    ))
    blade = fuse_all(parts)
    # nut pocket, axis along Y, centered on the screw (x=2.65, z=5.2)
    nut_y = lug + 2.0
    nut = hex_prism(2.65, nut_y, 5.20, 5.70, 2.70, axis="Y")
    mouth = box(2.65, nut_y, 5.20 + 3.2, 5.75, 2.8, 6.4)
    blade = cut(cut(blade, nut), mouth)
    # screw clearance through the nut block so the shank can pass
    blade = cut(blade, cyl_along_checked((2.65, lug - 0.2, 5.20), (2.65, y_end + 0.2, 5.20), 1.70))
    # scale ticks on the dorsal face of the slim section: tick n at the index when translation = n
    # tick y = tip + (INDEX_Y - CORTEX_Y) + n    so at the matching T it sits on INDEX_Y
    for n in range(0, int(T_MAX) + 1):
        ty = tip + (INDEX_Y - CORTEX_Y) + n
        depth_x = 1.15 if n % 6 == 0 else 0.65
        blade = cut(blade, box(
            PAD_X1 - depth_x / 2.0, ty, PAD_ZC - 0.15,
            depth_x, 0.28 if n % 6 else 0.18, 0.55,
        ))
    return blade


def build_turret(obl: float):
    """Dual-bore turret. Built at 12° and rotated about the hinge for the other detents."""
    H, direction, boss = angle_geom()
    hx, hy = float(H[0]), float(H[1])
    sleeves = []
    axes = []
    for exit in (EXIT_X, EXIT_X + WIRE_SPACING):
        p0 = wire_point(exit, 13.6, OBL_NOM)
        p1 = wire_point(exit, 33.0, OBL_NOM)
        axes.append((p0, p1))
        sleeves.append(cyl_along_checked(p0, p1, SLEEVE_OD / 2))
    # web stays proximal of the paddle column (x < -3)
    web = box((-20.5 + -3.6) / 2, (17.2 + 31.5) / 2, (-1.2 + 3.5) / 2, 16.9, 14.3, 4.7)
    # post joins the sleeves (z ≤ 3.5) to the riser (z ≥ 8)
    post = box(hx, hy + 12.4, (2.6 + 9.2) / 2, 4.4, 4.8, 6.6)
    eye = box(hx, hy, (7.95 + 9.70) / 2, 4.10, 2.90, 1.75)
    bridge = box(hx, hy + 7.2, (8.05 + 9.55) / 2, 3.10, 12.4, 1.50)
    riser = box(hx, hy + 12.6, (8.0 + 14.4) / 2, 4.6, 5.2, 6.4)
    arm = _bar(
        np.array([hx, hy + 11.0]),
        boss + direction * 8.0,
        z0=10.95, z1=14.20, half_w=9.5,
    )
    turret = fuse_all(sleeves + [web, post, eye, bridge, riser, arm])
    turret = cut(turret, cyl_along_checked((hx, hy, 6.6), (hx, hy, 11.2), 1.75))
    for p0, p1 in axes:
        d = p1 - p0
        d = d / np.linalg.norm(d)
        turret = cut(turret, cyl_along_checked(p0 - d, p1 + d, BORE_D / 2))
    for delta in (-ARM_SWEEP, 0.0, ARM_SWEEP):
        ang = math.radians(-delta)
        rot = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
        pos = np.array([hx, hy]) + rot @ (direction * ARM_R)
        turret = cut(turret, cyl_along_checked(
            (float(pos[0]), float(pos[1]), 10.2),
            (float(pos[0]), float(pos[1]), 15.0),
            1.70,
        ))
    if abs(obl - OBL_NOM) > 1e-6:
        turret = turret.rotate((hx, hy, 0.0), (hx, hy, 1.0), obl - OBL_NOM)
    return turret


def build_clip():
    """Slave block. Slides onto wire 1 from the free end; bore 2 is 10 mm distal."""
    p0 = wire_point(EXIT_X, 40.0, OBL_NOM)
    p1 = wire_point(EXIT_X, 54.0, OBL_NOM)
    q0 = p0 + np.array([WIRE_SPACING, 0.0, 0.0])
    q1 = p1 + np.array([WIRE_SPACING, 0.0, 0.0])
    body = fuse(
        cyl_along_checked(p0, p1, 4.2),
        cyl_along_checked(q0, q1, 4.2),
    )
    web = box(
        float((p0[0] + q0[0]) / 2 + 2), float((p0[1] + p1[1]) / 2), -0.4,
        WIRE_SPACING + 6, 12.0, 6.5,
    )
    foot = box(
        float((p0[0] + q0[0]) / 2 + 2), float((p0[1] + p1[1]) / 2), -4.7,
        WIRE_SPACING + 10, 16.0, 2.8,
    )
    clip = fuse_all([body, web, foot])
    d = p1 - p0
    d = d / np.linalg.norm(d)
    clip = cut(clip, cyl_along_checked(p0 - d * 2, p1 + d * 2, BORE_D / 2))
    clip = cut(clip, cyl_along_checked(q0 - d * 2, q1 + d * 2, BORE_D / 2))
    return clip


def build_screw(p0, p1, head_r=2.8, head_h=3.0):
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    d = p1 - p0
    d = d / np.linalg.norm(d)
    shank = cyl_along_checked(p0, p1, 1.45)
    head = cyl_along_checked(p1, p1 + d * head_h, head_r)
    return fuse(shank, head)


def build_bone(T: float):
    """Schematic Ø14 shaft, osteotomy at x=0, head translated by T. Viz + fixture source."""
    shaft = cyl_along_checked((-52, 0, 0), (0, 0, 0), SHAFT_R)
    # head: sphere whose cut face (x=1.6) has its medial rim on the paddle face
    # section radius at x=1.6 with center x=9.2, R=9 → sqrt(81 - 7.6^2)=sqrt(23.24)=4.82
    sec_r = math.sqrt(max(9.0 ** 2 - (9.2 - 1.6) ** 2, 1))
    head_y = face_y(T) - sec_r + 0.4  # rim just lateral of the paddle, so they kiss
    head = cq.Workplane("XY").sphere(9.0).translate((9.2, head_y, 0))
    head = cut(head, box(-8, head_y, 0, 20, 40, 40))  # keep x>1.6 approximately: cut x<1.6
    # the cut above removes a box centered at x=-8 size 20, so x from -18 to 2. Re-cut properly:
    head = cq.Workplane("XY").sphere(9.0).translate((9.2, head_y, 0))
    head = cut(head, box(-6.0, head_y, 0, 16.0, 40, 40))
    return shaft, head


def build_fixture():
    """Split Ø14 shaft fixture with a groove for tongue M. Bench fit only."""
    shaft = cyl_along_checked((-46, 0, 0), (0.4, 0, 0), SHAFT_R)
    groove = box((-46 + -5.0) / 2, 0, 0, 41.0, 2 * TONGUE_HY + 0.70, 2 * TONGUE_HZ + 0.70)
    body = cut(shaft, groove)
    dorsal = cut(body, box(-23, 0, -20, 60, 40, 40))
    plantar = cut(body, box(-23, 0, 20, 60, 40, 40))
    # two Ø3 alignment pins as holes on the cut face
    for x in (-12.0, -30.0):
        pin = cyl_along_checked((x, 5.2, -8), (x, 5.2, 8), 1.55)
        dorsal = cut(dorsal, pin)
        plantar = cut(plantar, pin)
    return dorsal, plantar


# ---------- checks ----------

class Report:
    def __init__(self):
        self.rows = []

    def add(self, name, ok, detail):
        self.rows.append({"name": name, "ok": bool(ok), "detail": detail})
        flag = "OK  " if ok else "FAIL"
        print(f"  [{flag}] {name}: {detail}")

    @property
    def ok(self):
        return all(r["ok"] for r in self.rows)


def _wire_clearance(solids_far, solids_bore, exit_x, obl, y0, y1):
    """Return (min distance to far solids, min distance to bore solid)."""
    pts = axis_samples(exit_x, obl, y0, y1, n=50)
    far = min((min_dist(s.val(), pts) for s in solids_far), default=1e9)
    bore = min((min_dist(s.val(), pts) for s in solids_bore), default=1e9)
    return far, bore


def run_checks():
    rep = Report()
    calibrate_cylinder()
    # cylinder actually reaches x=10
    bb = bbox(cyl_along_checked((0, 0, 0), (10, 0, 0), 1))
    rep.add("cylinder helper", bb[3] > 9.5 and bb[0] > -0.3 and bb[1] > -1.2, f"bbox={tuple(round(v,2) for v in bb)}")

    H = hinge_xy()
    # nominal exit is exactly on the lateral cortex
    exit_pt = wire_point(EXIT_X, -SHAFT_R, OBL_NOM)
    rep.add(
        "wire 1 lateral exit",
        abs(exit_pt[0] - EXIT_X) < 1e-6 and abs(exit_pt[1] + SHAFT_R) < 1e-6,
        f"{exit_pt.round(3).tolist()}  (10 mm proximal of the osteotomy)",
    )
    # 102°: angle between +X (distal shaft) and the medial-going direction
    direction = wire_point(EXIT_X, 0, OBL_NOM) - wire_point(EXIT_X, -SHAFT_R, OBL_NOM)
    d = direction / np.linalg.norm(direction)
    # Into the bone the wire runs lateral and slightly distal. The published 102°
    # is the obtuse angle between that direction and the IM axis (proximal, -X).
    into = -d
    im_axis = np.array([-1.0, 0.0, 0.0])
    cosang = float(np.clip(np.dot(into, im_axis) / np.linalg.norm(into), -1, 1))
    hole = math.degrees(math.acos(cosang))
    rep.add("hole angle vs IM axis", abs(hole - HOLE_ANGLE) < 0.05, f"{hole:.2f}° (target {HOLE_ANGLE:.0f}°)")

    print("building frame…")
    frame, meta = build_frame()
    print("building tongue M…")
    tongue = build_tongue(SIZES["M"])
    print("building blade…")
    blade = build_blade(T_BUILD)
    print("building turret…")
    turret = build_turret(OBL_NOM)
    print("building clip…")
    clip = build_clip()

    for name, wp, lo, hi in (
        ("frame", frame, 4000, 60000),
        ("tongue M", tongue, 250, 15000),
        ("blade", blade, 400, 15000),
        ("turret", turret, 1500, 40000),
        ("clip", clip, 400, 15000),
    ):
        v = volume(wp)
        rep.add(f"volume {name}", lo < v < hi, f"{v:.0f} mm³")

    # paddle face
    bb = bbox(blade)
    rep.add(
        "paddle face Y",
        abs(bb[1] - face_y(T_BUILD)) < 0.08,
        f"minY={bb[1]:.2f}, target {face_y(T_BUILD):.2f} at T={T_BUILD}",
    )

    # separations
    pairs = [
        ("blade-frame", blade, frame, 0.12, 0.55),
        ("tongue-frame", tongue, frame, 0.08, 1.20),
        ("turret-frame", turret, frame, 0.05, 2.50),
        ("clip-frame", clip, frame, 2.0, 80),
        ("tongue-blade", tongue, blade, 0.40, 20),
        ("turret-tongue", turret, tongue, 0.25, 40),
        ("turret-blade", turret, blade, 0.40, 40),
    ]
    for name, a, b, lo, hi in pairs:
        g = shape_gap(a, b)
        rep.add(f"gap {name}", lo <= g <= hi, f"{g:.2f} mm (allowed {lo}–{hi})")

    far = [frame, tongue, blade, clip]
    for label, exit in (("wire1", EXIT_X), ("wire2", EXIT_X + WIRE_SPACING)):
        far_d, bore_d = _wire_clearance(far, [turret], exit, OBL_NOM, -6.5, 33.5)
        rep.add(f"{label} misses other parts", far_d >= 0.90, f"min dist {far_d:.2f} mm")
        rep.add(f"{label} centered in bore", bore_d >= (BORE_D / 2) - 0.08, f"dist to turret {bore_d:.2f} mm")

    # wire 1 actually passes the tongue fork (close to the tongue, not a miss by centimetres)
    pts = axis_samples(EXIT_X, OBL_NOM, -2.0, 1.2, n=12)
    d_tongue = min_dist(tongue.val(), pts)
    rep.add("wire 1 in the fork", 0.70 <= d_tongue <= SLOT_HZ + 0.15, f"dist to tongue {d_tongue:.2f} mm")

    # scale: tick 0 sits on the index at T=0, tick 12 at T=12
    b0 = build_blade(0.0)
    b12 = build_blade(T_MAX)
    # tick cuts remove material; check a point that should be VOID at the tick and SOLID beside it
    # tick 0 y at T=0: tip + (INDEX-CORTEX) = 7 + 10.2 = 17.2
    tick0 = CORTEX_Y + (INDEX_Y - CORTEX_Y)
    solid_beside = (PAD_X0 + 0.4, tick0 + 0.8, 0.0)
    void_tick = (PAD_X1 - 0.15, tick0, PAD_ZC - 0.05)
    rep.add("tick 0 is a cut", point_inside(b0.val(), void_tick) is False, f"point {void_tick}")
    rep.add("blade solid beside tick", point_inside(b0.val(), solid_beside) is True, f"point {solid_beside}")
    g0 = shape_gap(b0, frame)
    g12 = shape_gap(b12, frame)
    rep.add("stop gap at 0 mm", 0.10 <= g0 <= 0.50, f"{g0:.2f} mm")
    rep.add("stop gap at 12 mm", 0.10 <= g12 <= 0.50, f"{g12:.2f} mm")

    # angle variants: turret must still clear the frame, wire still in the fork
    for obl in (6.0, 18.0):
        print(f"checking obliquity {obl:.0f}°…")
        tur = build_turret(obl)
        g = shape_gap(tur, frame)
        rep.add(f"turret clears frame at {obl:.0f}°", g >= 0.10, f"gap {g:.2f} mm")
        delta = obl - OBL_NOM
        bore_pts = [rot_about_hinge(wire_point(EXIT_X, y, OBL_NOM), delta) for y in np.linspace(16, 31, 16)]
        bore_d = min_dist(tur.val(), bore_pts)
        fork_pts = [rot_about_hinge(wire_point(EXIT_X, y, OBL_NOM), delta) for y in (-1.0, 0.0, 1.0)]
        dt = min_dist(tongue.val(), fork_pts)
        far_pts = [rot_about_hinge(wire_point(EXIT_X, y, OBL_NOM), delta) for y in np.linspace(8, 32, 20)]
        far_d = min(min_dist(frame.val(), far_pts), min_dist(blade.val(), far_pts))
        exit_x = _exit_x(obl)
        rep.add(
            f"wire 1 follows bore at {obl:.0f}°",
            bore_d >= (BORE_D / 2) - 0.08,
            f"bore dist {bore_d:.2f} mm, lateral exit x={exit_x:.2f} mm",
        )
        rep.add(
            f"wire 1 in fork at {obl:.0f}°",
            0.55 <= dt <= SLOT_HZ + 0.35,
            f"dist {dt:.2f} mm",
        )
        rep.add(f"wire 1 misses frame/blade at {obl:.0f}°", far_d >= 0.70, f"{far_d:.2f} mm")
        rep.add(
            f"exit stays near 10 mm at {obl:.0f}°",
            -14.5 <= exit_x <= -6.0,
            f"{-exit_x:.1f} mm proximal of the cut",
        )

    # S and L tongues share the flange envelope: gap to frame stays positive
    for key in ("S", "L"):
        tg = build_tongue(SIZES[key])
        g = shape_gap(tg, frame)
        rep.add(f"tongue {key} fits frame", 0.08 <= g <= 1.5, f"gap {g:.2f} mm, vol {volume(tg):.0f}")

    parts = {
        "frame": frame,
        "tongue": tongue,
        "blade": blade,
        "turret": turret,
        "clip": clip,
    }
    return rep, parts, meta


def build_hardware(meta):
    hx, hy = meta["hinge_xy"]
    bx, by = meta["boss_xy"]
    screws = [
        ("screw_translation_M3x25", build_screw((2.65, 19.0, 5.20), (2.65, 42.4, 5.20))),
        ("screw_tongue_M3x10", build_screw((5.8, 14.1, 4.2), (5.8, 14.1, 8.9))),
        ("screw_angle_M3x12", build_screw((bx, by, 7.6), (bx, by, 13.6))),
        ("screw_hinge_M3x8", build_screw((hx, hy, 5.2), (hx, hy, 12.4))),
    ]
    return screws


def main():
    os.makedirs(STL, exist_ok=True)
    os.makedirs(STEP, exist_ok=True)
    os.makedirs(FIX, exist_ok=True)
    print("HALIA-1 geometry build")
    rep, parts, meta = run_checks()
    if not rep.ok:
        # still write the report, then raise so the failure is obvious
        path = os.path.join(EXPORT, "validation.json")
        with open(path, "w") as f:
            json.dump({"ok": False, "checks": rep.rows, "meta": meta}, f, indent=2)
        raise SystemExit(f"geometry checks failed — see {path}")

    print("exporting STEP and STL…")
    # functional-position STEP assembly (exact)
    assy = cq.Assembly(name="HALIA-1")
    colors = {
        "frame": cq.Color(0.16, 0.32, 0.48),
        "tongue": cq.Color(0.62, 0.64, 0.66),
        "blade": cq.Color(0.72, 0.55, 0.22),
        "turret": cq.Color(0.10, 0.45, 0.46),
        "clip": cq.Color(0.55, 0.27, 0.14),
    }
    for name, wp in parts.items():
        assy.add(wp, name=name, color=colors[name])
    hardware = build_hardware(meta)
    for name, wp in hardware:
        assy.add(wp, name=name, color=cq.Color(0.75, 0.75, 0.78))
    assy.save(os.path.join(STEP, "HALIA-1_assembly.step"))

    # individual exact STEP in the functional pose (for the drawing / CAD)
    for name, wp in parts.items():
        export_step(wp, os.path.join(STEP, f"{name}.step"))

    # print-oriented STLs
    print_plan = [
        ("frame", parts["frame"], "Yup"),
        ("blade", parts["blade"], "Yup"),
        ("turret", parts["turret"], "bore"),
        ("clip", parts["clip"], "bore"),
    ]
    for size in SIZES.values():
        tg = parts["tongue"] if size.name == "M" else build_tongue(size)
        print_plan.append((f"tongue_{size.name}", tg, "Yup"))
        if size.name != "M":
            export_step(tg, os.path.join(STEP, f"tongue_{size.name}.step"))

    manifest_prints = []
    for name, wp, mode in print_plan:
        laid = lay_on_bed(wp, mode)
        path = os.path.join(STL, f"print_{name}.stl")
        export_stl(laid, path)
        bb = bbox(laid)
        manifest_prints.append({
            "file": os.path.relpath(path, ROOT),
            "part": name,
            "bed_orientation": mode,
            "size_mm": [round(bb[3] - bb[0], 2), round(bb[4] - bb[1], 2), round(bb[5] - bb[2], 2)],
        })
        print(f"  STL {name}: {manifest_prints[-1]['size_mm']} mm")

    # functional-pose meshes for the video (finer not required)
    viz_dir = os.path.join(EXPORT, "viz")
    os.makedirs(viz_dir, exist_ok=True)
    for name, wp in parts.items():
        export_stl(wp, os.path.join(viz_dir, f"{name}.stl"), tol=0.05, ang=0.12)
    for name, wp in hardware:
        export_stl(wp, os.path.join(viz_dir, f"{name}.stl"), tol=0.06, ang=0.15)
    shaft, head = build_bone(T_BUILD)
    export_stl(shaft, os.path.join(viz_dir, "bone_shaft.stl"), tol=0.08, ang=0.12)
    export_stl(head, os.path.join(viz_dir, "bone_head.stl"), tol=0.08, ang=0.12)
    # wires
    for label, exit in (("wire1", EXIT_X), ("wire2", EXIT_X + WIRE_SPACING)):
        p0 = wire_point(exit, 56.0, OBL_NOM)
        p1 = wire_point(exit, -8.0, OBL_NOM)
        export_stl(cyl_along_checked(p1, p0, WIRE_D / 2), os.path.join(viz_dir, f"{label}.stl"), tol=0.04, ang=0.1)

    # left-foot set (mirror). Print files.
    print("mirroring left-foot set…")
    for name, wp, mode in (
        ("frame", parts["frame"], "Yup"),
        ("blade", parts["blade"], "Yup"),
        ("turret", parts["turret"], "bore"),
        ("clip", parts["clip"], "bore"),
        ("tongue_M", parts["tongue"], "Yup"),
        ("tongue_S", build_tongue(SIZES["S"]), "Yup"),
        ("tongue_L", build_tongue(SIZES["L"]), "Yup"),
    ):
        laid = lay_on_bed(mirror_y(wp), mode)
        export_stl(laid, os.path.join(STL, f"print_{name}_LEFT.stl"))

    dorsal, plantar = build_fixture()
    export_stl(lay_on_bed(dorsal, "as_is"), os.path.join(FIX, "print_fixture_shaft_dorsal.stl"))
    export_stl(lay_on_bed(plantar, "as_is"), os.path.join(FIX, "print_fixture_shaft_plantar.stl"))
    export_step(fuse(dorsal, plantar), os.path.join(STEP, "fixture_shaft.step"))

    # left mirror of functional step (assembly of mirrored parts) — one combined STEP
    left = cq.Assembly(name="HALIA-1-LEFT")
    for name, wp in parts.items():
        left.add(mirror_y(wp), name=name, color=colors[name])
    left.save(os.path.join(STEP, "HALIA-1_assembly_LEFT.step"))

    manifest = {
        "name": "HALIA-1",
        "units": "mm",
        "foot": "right (LEFT files are mirrored)",
        "hole_angle_deg": HOLE_ANGLE,
        "obliquity_deg": OBL_NOM,
        "obliquity_options_deg": [OBL_NOM - ARM_SWEEP, OBL_NOM, OBL_NOM + ARM_SWEEP],
        "hole_angle_options_deg": [96, 102, 108],
        "wire_exit_proximal_of_cut_mm": -EXIT_X,
        "wire_spacing_along_shaft_mm": WIRE_SPACING,
        "translation_in_assembly_mm": T_BUILD,
        "translation_range_mm": [0, T_MAX],
        "design_shaft_diameter_mm": 2 * SHAFT_R,
        "wire_diameter_mm": WIRE_D,
        "printed_bore_mm": BORE_D,
        "ream_bore_mm": [1.70, 1.75],
        "hinge_xy": meta["hinge_xy"],
        "angle_boss_xy": meta["boss_xy"],
        "index_y": INDEX_Y,
        "paddle_face_y_at_T8": face_y(T_BUILD),
        "checks": rep.rows,
        "print_files": manifest_prints,
        "hardware": [
            "M3x25 socket head — translation screw, 1",
            "M3 nut — translation, 1 (slides into the dorsal mouth of the paddle block)",
            "M3x10 socket head — tongue lock, 1",
            "M3 nut — tongue lock, 1 (plantar mouth of the shelf)",
            "M3x12 socket head — angle lock, 1 (through the 96, 102 or 108 hole)",
            "M3 nut — angle lock, 1",
            "M3x8 socket head — hinge axle, 1 (dorsal clevis only; a through-screw would cross the wire)",
        ],
    }
    with open(os.path.join(EXPORT, "validation.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print("ALL CHECKS PASSED")
    print(os.path.join(EXPORT, "validation.json"))


if __name__ == "__main__":
    main()
