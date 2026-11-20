#!/usr/bin/env python3
"""Studio turntable of HALIA-1. Offscreen VTK, captions in Pillow, H.264 via ffmpeg.

    python3 cad/render_video.py --stills
    python3 cad/render_video.py
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys

import numpy as np
import vtk
from PIL import Image, ImageDraw, ImageFont
from vtk.util.numpy_support import vtk_to_numpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIZ = os.path.join(ROOT, "export", "viz")
OUT = os.path.join(ROOT, "export", "video")

W, H = 1600, 900
FPS = 24

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Functional pose colours. Bone is ivory and translucent; wires are the only red.
STYLE = {
    "frame": ((0.18, 0.36, 0.55), 1.0, 0.40),
    "tongue": ((0.72, 0.74, 0.76), 1.0, 0.25),
    "blade": ((0.78, 0.58, 0.20), 1.0, 0.35),
    "turret": ((0.12, 0.50, 0.52), 1.0, 0.35),
    "clip": ((0.62, 0.34, 0.16), 1.0, 0.30),
    "bone_shaft": ((0.93, 0.89, 0.80), 0.46, 0.08),
    "bone_head": ((0.93, 0.89, 0.80), 0.46, 0.08),
    "wire1": ((0.86, 0.16, 0.13), 1.0, 0.55),
    "wire2": ((0.86, 0.16, 0.13), 1.0, 0.55),
}
SCREW_STYLE = ((0.80, 0.81, 0.84), 1.0, 0.65)


def _actor(path, color, opacity, specular):
    reader = vtk.vtkSTLReader()
    reader.SetFileName(path)
    reader.Update()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(reader.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*color)
    prop.SetOpacity(opacity)
    prop.SetInterpolationToPhong()
    prop.SetAmbient(0.22)
    prop.SetDiffuse(0.70)
    prop.SetSpecular(specular)
    prop.SetSpecularPower(32)
    return actor


def load_scene(ren):
    actors = {}
    for name, (color, opacity, spec) in STYLE.items():
        path = os.path.join(VIZ, f"{name}.stl")
        actors[name] = _actor(path, color, opacity, spec)
        ren.AddActor(actors[name])
    for name in (
        "screw_translation_M3x25",
        "screw_tongue_M3x10",
        "screw_angle_M3x12",
        "screw_hinge_M3x8",
    ):
        path = os.path.join(VIZ, f"{name}.stl")
        actors[name] = _actor(path, *SCREW_STYLE)
        ren.AddActor(actors[name])
    return actors


def add_lights(ren, focal):
    ren.AutomaticLightCreationOff()
    specs = [
        ((80, 40, 90), 0.85, (1.0, 0.98, 0.94)),
        ((-30, -90, 40), 0.45, (0.85, 0.90, 1.0)),
        ((-80, 30, 20), 0.30, (1.0, 0.95, 0.88)),
        ((10, 10, -60), 0.18, (0.7, 0.75, 0.85)),
    ]
    for pos, intensity, color in specs:
        light = vtk.vtkLight()
        light.SetLightTypeToSceneLight()
        light.SetPosition(*pos)
        light.SetFocalPoint(*focal)
        light.SetIntensity(intensity)
        light.SetColor(*color)
        ren.AddLight(light)


def make_window():
    ren = vtk.vtkRenderer()
    ren.SetBackground(0.045, 0.050, 0.060)
    ren.SetBackground2(0.145, 0.155, 0.175)
    ren.GradientBackgroundOn()
    ren.SetUseDepthPeeling(True)
    ren.SetMaximumNumberOfPeels(24)
    ren.SetOcclusionRatio(0.05)
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.SetAlphaBitPlanes(1)
    win.SetMultiSamples(0)
    win.AddRenderer(ren)
    win.SetSize(W, H)
    return ren, win


def look(ren, focal, pos, view_up=(0.0, 0.0, 1.0), angle=30.0):
    cam = ren.GetActiveCamera()
    cam.SetParallelProjection(False)
    cam.SetFocalPoint(*focal)
    cam.SetPosition(*pos)
    cam.SetViewUp(*view_up)
    cam.SetViewAngle(angle)
    ren.ResetCameraClippingRange()


def grab(win):
    win.Render()
    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(win)
    w2i.SetInputBufferTypeToRGB()
    w2i.ReadFrontBufferOff()
    w2i.Update()
    raw = vtk_to_numpy(w2i.GetOutput().GetPointData().GetScalars())
    img = raw.reshape(H, W, 3)
    return np.flipud(img).copy()


def orbit(focal, dist, az_deg, el_deg):
    """Camera position. az 0 looks from the distal side (+X), 90 from medial (+Y)."""
    az = math.radians(az_deg)
    el = math.radians(el_deg)
    return (
        focal[0] + dist * math.cos(el) * math.cos(az),
        focal[1] + dist * math.cos(el) * math.sin(az),
        focal[2] + dist * math.sin(el),
    )


def _font(path, size):
    return ImageFont.truetype(path, size)


def burn_caption(frame, text):
    if not text:
        return frame
    im = Image.fromarray(frame)
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(FONT, 28)
    pad = 18
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W - tw) // 2
    y = H - th - 46
    draw.rounded_rectangle(
        (x - pad, y - 10, x + tw + pad, y + th + 12),
        radius=8, fill=(8, 10, 14, 170),
    )
    draw.text((x, y), text, font=font, fill=(236, 236, 232, 255))
    im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
    return np.asarray(im)


def title_card(lines, footer):
    im = Image.new("RGB", (W, H), (12, 14, 18))
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 0, W, 8), fill=(196, 148, 74))
    y = 250
    for i, (text, size, color) in enumerate(lines):
        font = _font(FONTB if i == 0 else FONT, size)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) / 2, y), text, font=font, fill=color)
        y += size + 22
    font = _font(FONT, 22)
    bbox = draw.textbbox((0, 0), footer, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) / 2, H - 120), footer, font=font, fill=(180, 150, 110))
    return np.asarray(im)


def card_open():
    return title_card(
        [
            ("HALIA-1", 84, (244, 240, 230)),
            ("Направитель для чрескожной коррекции", 36, (210, 214, 218)),
            ("hallux valgus  ·  усовершенствованный прототип", 32, (210, 214, 218)),
        ],
        "Правая стопа  ·  смещение головки 8 мм  ·  угол канала 102°",
    )


def card_close():
    return title_card(
        [
            ("Инженерный прототип", 54, (244, 240, 230)),
            ("Не медицинское изделие.", 34, (230, 186, 120)),
            ("Не стерильно. Не для клинического применения.", 30, (210, 214, 218)),
            ("Геометрия — для проверки формы и печати.", 28, (180, 184, 190)),
        ],
        "HALIA-1  ·  смола для прототипа, не имплантат",
    )


# Exploded offsets in model millimetres. +X distal, +Y medial, +Z dorsal.
EXPLODE = {
    "tongue": (-22.0, 0.0, 10.0),
    "blade": (0.0, -26.0, 0.0),
    "turret": (0.0, 18.0, 16.0),
    "clip": (20.0, 8.0, 0.0),
    "screw_translation_M3x25": (0.0, -26.0, 8.0),
    "screw_tongue_M3x10": (-8.0, 0.0, 18.0),
    "screw_angle_M3x12": (0.0, 18.0, 24.0),
    "screw_hinge_M3x8": (0.0, 18.0, 22.0),
    "frame": (0.0, 0.0, 0.0),
    "wire1": (0.0, 0.0, 0.0),
    "wire2": (0.0, 0.0, 0.0),
    "bone_shaft": (0.0, 0.0, 0.0),
    "bone_head": (0.0, 0.0, 0.0),
}


def set_explode(actors, amount):
    for name, actor in actors.items():
        ox, oy, oz = EXPLODE.get(name, (0.0, 0.0, 0.0))
        actor.SetPosition(ox * amount, oy * amount, oz * amount)
    # Bone fades as the instrument opens, so the parts stay readable.
    fade = 0.46 * (1.0 - 0.65 * amount)
    for bone in ("bone_shaft", "bone_head"):
        actors[bone].GetProperty().SetOpacity(fade)


def lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    t = t * t * (3 - 2 * t)
    return a + (b - a) * t


def shot_at(t):
    """Return (focal, position, caption, explode) at time t seconds."""
    # 0–3 title, 3–11 full orbit, 11–13.5 dolly, 13.5–19 close orbit,
    # 19–24 explode, 24–27.5 end card. Caller handles the cards.
    full_f = np.array([-14.0, 18.0, 1.0])
    near_f = np.array([-2.0, 6.0, 0.0])
    if t < 11.0:
        u = (t - 3.0) / 8.0
        az = lerp(28, 200, u)
        el = 22 + 7 * math.sin(u * math.pi)
        pos = orbit(full_f, 158, az, el)
        return full_f, pos, "Сборка на правой стопе. Смещение 8 мм, канал спицы 102° к оси кости", 0.0
    if t < 13.5:
        u = (t - 11.0) / 2.5
        focal = full_f + (near_f - full_f) * (u * u * (3 - 2 * u))
        az = lerp(200, 215, u)
        dist = lerp(158, 64, u)
        el = lerp(22, 30, u)
        pos = orbit(focal, dist, az, el)
        return focal, pos, "Остеотомия, лопатка и две параллельные спицы", 0.0
    if t < 19.0:
        u = (t - 13.5) / 5.5
        az = lerp(215, 400, u)
        el = 28 + 6 * math.sin(u * math.pi)
        pos = orbit(near_f, 62, az, el)
        return near_f, pos, "Спицы 1,6 мм через 10 мм. Выход первой — 10 мм проксимальнее распила", 0.0
    u = (t - 19.0) / 5.0
    amount = lerp(0.0, 1.0, min(u / 0.45, 1.0))
    wide_f = np.array([-8.0, 12.0, 2.0])
    pos = orbit(wide_f, 168, 36 + 18 * u, 26)
    return wide_f, pos, "Язык, лопатка, турель и клипса печатаются отдельно", amount


def save_stills(ren, win, actors):
    os.makedirs(OUT, exist_ok=True)
    views = {
        "hero": (np.array([-12.0, 16.0, 1.0]), orbit(np.array([-12.0, 16.0, 1.0]), 150, 35, 26)),
        "dorsal": (np.array([-14.0, 18.0, 0.0]), (-14.0, 18.0, 220.0)),
        "working": (np.array([-1.0, 6.0, 0.0]), orbit(np.array([-1.0, 6.0, 0.0]), 55, 200, 32)),
        "lateral": (np.array([-8.0, 4.0, 0.0]), (-8.0, -90.0, 12.0)),
        "exploded": (np.array([-8.0, 12.0, 2.0]), orbit(np.array([-8.0, 12.0, 2.0]), 170, 40, 26)),
    }
    set_explode(actors, 0.0)
    for name, (focal, pos) in views.items():
        if name == "exploded":
            set_explode(actors, 1.0)
        else:
            set_explode(actors, 0.0)
        up = (1.0, 0.0, 0.0) if name == "dorsal" else (0.0, 0.0, 1.0)
        # Dorsal: looking down, distal (+X) to the right, medial (+Y) up.
        if name == "dorsal":
            up = (0.0, 1.0, 0.0)
        look(ren, focal, pos, up, angle=28 if name != "dorsal" else 32)
        if name == "dorsal":
            cam = ren.GetActiveCamera()
            cam.SetParallelProjection(True)
            cam.SetParallelScale(42)
            ren.ResetCameraClippingRange()
        frame = grab(win)
        Image.fromarray(frame).save(os.path.join(OUT, f"still_{name}.png"))
        print("still", name)
    set_explode(actors, 0.0)


def render_video(ren, win, actors):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "HALIA-1.mp4")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        "-movflags", "+faststart", path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    duration = 27.5
    n = int(duration * FPS)
    open_card = card_open()
    close_card = card_close()
    set_explode(actors, 0.0)
    for i in range(n):
        t = i / FPS
        if t < 3.0:
            frame = open_card
        elif t >= 24.0:
            frame = close_card
        else:
            focal, pos, caption, amount = shot_at(t)
            set_explode(actors, amount)
            look(ren, focal, pos, (0.0, 0.0, 1.0), angle=28)
            frame = burn_caption(grab(win), caption)
        proc.stdin.write(frame.tobytes())
        if i % FPS == 0:
            print(f"  {t:5.1f}s / {duration:.1f}s")
    proc.stdin.close()
    code = proc.wait()
    if code != 0:
        raise SystemExit(f"ffmpeg exited {code}")
    print(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stills", action="store_true")
    args = parser.parse_args()
    ren, win = make_window()
    actors = load_scene(ren)
    add_lights(ren, (-10.0, 16.0, 0.0))
    if args.stills:
        save_stills(ren, win, actors)
    else:
        render_video(ren, win, actors)


if __name__ == "__main__":
    sys.exit(main())
