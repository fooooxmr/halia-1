#!/usr/bin/env python3
"""A3 drawing of HALIA-1: pictorial views, a 3:1 control schematic, and a 1:1 DXF.

Numbers come from halia_gen and export/validation.json. The STEP file is the
master 3D model; this sheet records the dimensions the prototype is built to.
"""
from __future__ import annotations

import json
import math
import os
import sys

import ezdxf
from ezdxf.enums import TextEntityAlignment
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Frame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import halia_gen as g

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "export", "drawing")
STILLS = os.path.join(ROOT, "export", "video")
VAL = json.load(open(os.path.join(ROOT, "export", "validation.json"), encoding="utf-8"))

pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVuBold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))

PAGE = landscape(A3)  # 420 × 297 mm
INK = (0.12, 0.13, 0.15)
DIM = (0.55, 0.16, 0.12)
BONE = (0.45, 0.40, 0.32)
WIRE = (0.70, 0.12, 0.10)
HAIR = (0.35, 0.38, 0.42)
RULE = (0.25, 0.27, 0.30)

PAGES = 3


def wrap_style(name, size, leading, color=INK, bold=False):
    return ParagraphStyle(
        name, fontName="DejaVuBold" if bold else "DejaVu",
        fontSize=size, leading=leading, textColor=color,
    )


def para(c, text, x, y, w, h, style):
    story = [Paragraph(text, style)]
    Frame(x, y, w, h, showBoundary=0, leftPadding=0, rightPadding=0,
          topPadding=0, bottomPadding=0).addFromList(story, c)


def header(c, sheet, title):
    c.setFillColorRGB(0.16, 0.22, 0.30)
    c.rect(0, PAGE[1] - 16 * mm, PAGE[0], 16 * mm, stroke=0, fill=1)
    c.setFillColorRGB(0.78, 0.58, 0.28)
    c.rect(0, PAGE[1] - 17.4 * mm, PAGE[0], 1.4 * mm, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("DejaVuBold", 11)
    c.drawString(12 * mm, PAGE[1] - 10.5 * mm, "HALIA-1")
    c.setFont("DejaVu", 9)
    c.drawString(38 * mm, PAGE[1] - 10.2 * mm, title)
    c.setFont("DejaVu", 8)
    c.drawRightString(PAGE[0] - 12 * mm, PAGE[1] - 10.2 * mm, f"Лист {sheet} из {PAGES}")


def title_block(c, sheet, name):
    x0, y0, w, h = 12 * mm, 7 * mm, PAGE[0] - 24 * mm, 16 * mm
    c.setStrokeColorRGB(*RULE)
    c.setLineWidth(0.6)
    c.setFillColorRGB(0.97, 0.96, 0.94)
    c.roundRect(x0, y0, w, h, 2 * mm, stroke=1, fill=1)
    c.setFillColorRGB(*INK)
    c.setFont("DejaVuBold", 8)
    c.drawString(x0 + 4 * mm, y0 + 9.2 * mm, "HALIA-1")
    c.setFont("DejaVu", 7.5)
    c.drawString(x0 + 28 * mm, y0 + 9.4 * mm, name)
    c.setFont("DejaVu", 7)
    c.drawString(x0 + 4 * mm, y0 + 3.2 * mm,
                 "мм    правая стопа, +X дистально, +Y медиально, +Z дорсально    "
                 "мастер-модель: export/step/HALIA-1_assembly.step    21.11.2026")
    c.setFillColorRGB(0.45, 0.22, 0.10)
    c.setFont("DejaVuBold", 7.5)
    c.drawRightString(x0 + w - 4 * mm, y0 + 9.2 * mm, "НЕ МЕДИЦИНСКОЕ ИЗДЕЛИЕ")
    c.setFont("DejaVu", 7)
    c.drawRightString(x0 + w - 4 * mm, y0 + 3.2 * mm, "Не стерильно. Не для клинического применения.")


def footer_rule(c):
    pass


# ---------- schematic geometry (model millimetres) ----------

def head_center_y():
    sec_r = math.sqrt(max(9.0 ** 2 - (9.2 - 1.6) ** 2, 1.0))
    return g.face_y(g.T_BUILD) - sec_r + 0.4


def wire_polyline(exit_x, y0, y1, n=2):
    pts = []
    for i in range(n):
        y = y0 + (y1 - y0) * i / (n - 1)
        p = g.wire_point(exit_x, y, g.OBL_NOM)
        pts.append((float(p[0]), float(y)))
    return pts


def schematic(c, ox, oy, scale):
    """Dorsal control view. scale is paper-mm per model-mm; ox, oy in points."""
    S = scale * mm

    def X(x):
        return ox + x * S

    def Y(y):
        return oy + y * S

    # bone shaft Ø14, osteotomy at x = 0
    c.setStrokeColorRGB(*BONE)
    c.setFillColorRGB(0.93, 0.90, 0.84)
    c.setLineWidth(0.8)
    c.rect(X(-40), Y(-g.SHAFT_R), 40 * S, 2 * g.SHAFT_R * S, stroke=1, fill=1)
    hy = head_center_y()
    c.saveState()
    path = c.beginPath()
    path.moveTo(X(2.0), Y(-16))
    path.lineTo(X(20), Y(-16))
    path.lineTo(X(20), Y(8))
    path.lineTo(X(2.0), Y(8))
    path.close()
    c.clipPath(path, stroke=0, fill=0)
    c.circle(X(9.2), Y(hy), 9.0 * S, stroke=1, fill=1)
    c.restoreState()

    # osteotomy datum
    c.setStrokeColorRGB(*INK)
    c.setDash(2, 2)
    c.setLineWidth(0.7)
    c.line(X(0), Y(-13), X(0), Y(14))
    c.setDash()

    # tongue, dorsal outline of the fork only
    c.setStrokeColorRGB(0.35, 0.38, 0.42)
    c.setFillColorRGB(0.82, 0.84, 0.86)
    c.setLineWidth(0.6)
    c.rect(X(g.TONGUE_X_TIP), Y(-g.TONGUE_HY), (g.TONGUE_X_END - g.TONGUE_X_TIP) * S,
           2 * g.TONGUE_HY * S, stroke=1, fill=1)
    c.setDash(1, 1.5)
    c.line(X(g.TONGUE_X_SOLID), Y(-g.TONGUE_HY - 1.2), X(g.TONGUE_X_SOLID), Y(g.TONGUE_HY + 1.2))
    c.setDash()

    # paddle face at the shown translation
    face = g.face_y(g.T_BUILD)
    c.setFillColorRGB(0.86, 0.72, 0.40)
    c.setStrokeColorRGB(0.45, 0.32, 0.08)
    c.rect(X(g.PAD_X0), Y(face), (g.PAD_X1 - g.PAD_X0) * S, 12 * S, stroke=1, fill=1)

    # wires, stopped above the bone so the sheet stays readable
    c.setStrokeColorRGB(*WIRE)
    c.setLineWidth(1.3)
    for exit in (g.EXIT_X, g.EXIT_X + g.WIRE_SPACING):
        (x0, y0), (x1, y1) = wire_polyline(exit, -9.0, 22.0)
        c.line(X(x0), Y(y0), X(x1), Y(y1))

    # 102° is the obtuse angle between the into-bone wire and the proximal axis.
    # Drawn in the open space medial of the cortex, where both legs are visible.
    ay = 18.0
    apex = g.wire_point(g.EXIT_X, ay, g.OBL_NOM)
    ax = float(apex[0])
    radius = 6.0
    c.setStrokeColorRGB(*DIM)
    c.setLineWidth(0.8)
    c.arc(X(ax - radius), Y(ay - radius), X(ax + radius), Y(ay + radius), 180, 102)
    c.setStrokeColorRGB(*HAIR)
    c.setDash(1, 1.2)
    c.line(X(ax), Y(ay), X(ax - 14), Y(ay))
    c.setDash()

    # dimensions
    def hdim(x1, x2, y, text):
        c.setStrokeColorRGB(*DIM)
        c.setFillColorRGB(*DIM)
        c.setLineWidth(0.5)
        c.line(X(x1), Y(y), X(x2), Y(y))
        for x in (x1, x2):
            c.line(X(x), Y(y - 1.1), X(x), Y(y + 1.1))
        c.setFont("DejaVu", 6.5)
        c.drawCentredString((X(x1) + X(x2)) / 2, Y(y) + 1.6 * mm, text)

    def vdim(x, y1, y2, text):
        c.setStrokeColorRGB(*DIM)
        c.setFillColorRGB(*DIM)
        c.setLineWidth(0.5)
        c.line(X(x), Y(y1), X(x), Y(y2))
        for y in (y1, y2):
            c.line(X(x - 1.1), Y(y), X(x + 1.1), Y(y))
        c.setFont("DejaVu", 6.5)
        c.saveState()
        c.translate(X(x) - 1.8 * mm, (Y(y1) + Y(y2)) / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, text)
        c.restoreState()

    hdim(g.EXIT_X, 0, -12.2, "10")
    hdim(g.EXIT_X, g.EXIT_X + g.WIRE_SPACING, -15.2, "10  шаг спиц")
    vdim(20.2, face, g.CORTEX_Y, "T = 8")
    vdim(-42.5, -g.SHAFT_R, g.SHAFT_R, "Ø14")

    c.setFillColorRGB(*INK)
    c.setFont("DejaVu", 6.5)
    c.drawString(X(1.4), Y(10.2), "остеотомия, x = 0")
    c.drawString(X(g.TONGUE_X_SOLID - 1.0), Y(-9.6), "конец паза")
    c.drawString(X(g.PAD_X1 + 0.6), Y(face + 7.2), "лопатка")
    c.drawString(X(-40), Y(9.4), "язык M, паз открыт влево")
    c.setFillColorRGB(*DIM)
    c.setFont("DejaVuBold", 8)
    mid_ang = math.radians(230)
    c.drawString(X(ax + 8.2 * math.cos(mid_ang)),
                 Y(ay + 8.2 * math.sin(mid_ang)), "102°")
    c.setFillColorRGB(*INK)
    c.setFont("DejaVu", 6.5)
    c.drawString(X(-40), Y(-19.2), "М 3:1, вид сверху. Спица 1 выходит на 10 мм проксимальнее распила.")


def dxf_schematic(path):
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    doc.styles.add("HALIA", font="DejaVu Sans")
    for layer, color in (
        ("BONE", 7), ("TONGUE", 8), ("PADDLE", 30), ("WIRE", 1),
        ("DATUM", 5), ("DIM", 1), ("NOTE", 7),
    ):
        doc.layers.add(layer, color=color)
    msp = doc.modelspace()
    # shaft
    msp.add_lwpolyline(
        [(-40, -g.SHAFT_R), (0, -g.SHAFT_R), (0, g.SHAFT_R), (-40, g.SHAFT_R)],
        close=True, dxfattribs={"layer": "BONE"},
    )
    hy = head_center_y()
    msp.add_arc((9.2, hy), 9.0, 0, 360, dxfattribs={"layer": "BONE"})
    msp.add_line((0, -16), (0, 18), dxfattribs={"layer": "DATUM"})
    msp.add_lwpolyline(
        [(g.TONGUE_X_TIP, -g.TONGUE_HY), (g.TONGUE_X_END, -g.TONGUE_HY),
         (g.TONGUE_X_END, g.TONGUE_HY), (g.TONGUE_X_TIP, g.TONGUE_HY)],
        close=True, dxfattribs={"layer": "TONGUE"},
    )
    msp.add_line((g.TONGUE_X_SOLID, -3), (g.TONGUE_X_SOLID, 3), dxfattribs={"layer": "TONGUE"})
    face = g.face_y(g.T_BUILD)
    msp.add_lwpolyline(
        [(g.PAD_X0, face), (g.PAD_X1, face), (g.PAD_X1, face + 12), (g.PAD_X0, face + 12)],
        close=True, dxfattribs={"layer": "PADDLE"},
    )
    for exit in (g.EXIT_X, g.EXIT_X + g.WIRE_SPACING):
        (x0, y0), (x1, y1) = wire_polyline(exit, -12, 56)
        msp.add_line((x0, y0), (x1, y1), dxfattribs={"layer": "WIRE"})
    apex = g.wire_point(g.EXIT_X, 18.0, g.OBL_NOM)
    msp.add_arc((float(apex[0]), 18.0), 6.0, 180, 282, dxfattribs={"layer": "DIM"})
    notes = [
        (2, 20, "HALIA-1  control schematic, model mm, right foot"),
        (2, 16, "osteotomy datum x=0 ; +X distal ; +Y medial"),
        (2, 12, "wire 1 lateral exit 10 mm proximal of the cut ; wire spacing 10 mm"),
        (2, 8, "hole angle 102 deg to the proximal shaft axis at 12 deg obliquity"),
        (2, 4, "translation T=8 mm shown ; range 0..12 ; paddle face Y = 7 - T"),
        (2, 0, "printed bore dia 1.80, ream 1.70-1.75 for a 1.6 wire"),
        (2, -4, "NOT A MEDICAL DEVICE. Prototype geometry only."),
        (2, -8, "6 deg exit 12.3 mm proximal ; 18 deg exit 7.6 mm proximal"),
    ]
    for x, y, text in notes:
        msp.add_text(text, height=2.2, dxfattribs={"layer": "NOTE", "style": "HALIA"}).set_placement(
            (x, y), align=TextEntityAlignment.LEFT,
        )
    doc.saveas(path)


# ---------- sheets ----------

BODY = wrap_style("body", 8.2, 11.0)
SMALL = wrap_style("small", 7.4, 9.6)
H2 = wrap_style("h2", 9, 12, bold=True)
WARN = wrap_style("warn", 8, 10.6, color=(0.40, 0.18, 0.05))


def sheet_general(c):
    header(c, 1, "Общий вид прототипа")
    title_block(c, 1, "Направитель для чрескожной коррекции hallux valgus")
    img = os.path.join(STILLS, "still_hero.png")
    c.drawImage(img, 12 * mm, 70 * mm, width=236 * mm, height=188 * mm,
                preserveAspectRatio=True, anchor="c")
    c.setFillColorRGB(*HAIR)
    c.setFont("DejaVu", 7)
    c.drawString(14 * mm, 64 * mm, "Рис. 1. Сборка, правая стопа. Смещение головки 8 мм, наклон 12° (канал спицы 102°).")
    c.drawString(14 * mm, 59 * mm, "Кость — схема Ø14. Красным — спицы 1,6 мм. Клипса надета на свободные концы.")

    text = (
        "<b>Что в этой модели не повторяет направитель 2023 года</b><br/>"
        "Исходный инструмент (Олейник и соавт., Травматология и ортопедия России, 2023; "
        "doi 10.17816/2311-2905-8427) задаёт одну спицу под 102° к оси кости и выход из "
        "латеральной коры на 10 мм проксимальнее остеотомии. Смещение головки кнаружи "
        "авторы прямо назвали нерегулируемым. Вторая канюлированная спица ставится от руки.<br/><br/>"
        "1. Смещение 0–12 мм, шаг шкалы 1 мм, упоры на обоих концах.<br/>"
        "2. Наклон запирается на 6 / 12 / 18°, то есть угол канала 96 / 102 / 108°. "
        "Номинал 12° сохраняет 102° и выход на 10 мм.<br/>"
        "3. Два параллельных канала с шагом 10 мм. Вторая спица идёт по каналу, а не от руки.<br/>"
        "4. Клипса надевается на уже стоящую первую спицу со свободного конца.<br/>"
        "5. Язык с пазом, открытым проксимально: снимается дистально, не задевая спицу. "
        "Три ширины, S / M / L, на одну рамку.<br/>"
        "6. Вилка сверху и снизу — грубая отметка высоты под кость Ø14, не жёсткий зажим."
    )
    para(c, text, 254 * mm, 58 * mm, 154 * mm, 200 * mm, BODY)

    c.setFillColorRGB(0.98, 0.94, 0.86)
    c.setStrokeColorRGB(0.72, 0.52, 0.22)
    c.roundRect(12 * mm, 26 * mm, 396 * mm, 28 * mm, 2 * mm, stroke=1, fill=1)
    para(
        c,
        "<b>Оговорка.</b> Это инженерный прототип для проверки формы, посадки и 3D-печати. "
        "Он не является медицинским изделием, не стерилен и не предназначен для операций. "
        "Бытовая смола не имплантационный материал. Оценка угла по формуле arctan(T / 55 мм) "
        "на листе 3 — геометрия, а не назначение. DMAA, пронация и остеотомия Akin этой моделью не задаются. "
        "Чертежи патента с размерами в открытом доступе не найдены; модель собрана по опубликованному "
        "описанию направителя, а не по патентным фигурам.",
        16 * mm, 28 * mm, 388 * mm, 24 * mm, WARN,
    )


def sheet_views(c):
    header(c, 2, "Проекции и управляемые размеры")
    title_block(c, 2, "Вид сверху и вид с латеральной стороны")
    c.drawImage(os.path.join(STILLS, "still_dorsal.png"), 12 * mm, 168 * mm,
                width=250 * mm, height=100 * mm, preserveAspectRatio=True, anchor="c")
    c.drawImage(os.path.join(STILLS, "still_lateral.png"), 12 * mm, 40 * mm,
                width=250 * mm, height=118 * mm, preserveAspectRatio=True, anchor="c")
    c.setFillColorRGB(*HAIR)
    c.setFont("DejaVu", 7)
    c.drawString(14 * mm, 160 * mm, "Рис. 2. Вид сверху. Дистальный конец справа, медиальная сторона вверху.")
    c.drawString(14 * mm, 36 * mm, "Рис. 3. Вид с латеральной стороны. Спицы в пазу языка, лопатка у головки.")

    rows = [
        ("Угол канала к оси кости, номинал", "102°"),
        ("Наклон дистального фрагмента", "12°  (также 6° и 18°)"),
        ("Углы канала на фиксаторе", "96° / 102° / 108°"),
        ("Выход спицы 1, номинал", "10 мм проксимальнее распила"),
        ("Тот же выход при 6°", "12,3 мм проксимальнее"),
        ("Тот же выход при 18°", "7,6 мм проксимальнее"),
        ("Шаг двух спиц вдоль кости", "10 мм, параллельно"),
        ("Спица / канал в печати / развёртка", "1,6 / Ø1,80 / Ø1,70–1,75"),
        ("Смещение головки", "0–12 мм, на сборке 8 мм"),
        ("Шаг шкалы / зазор упора", "1 мм / 0,25 мм"),
        ("Расчётная кость", "Ø14, латеральная кора y = −7"),
        ("Лицо лопатки при T", "Y = 7 − T"),
        ("Язык S / M / L, полутолщина", "1,00 / 1,20 / 1,45 мм"),
        ("Паз языка, полуширина по Z", "1,50 / 1,75 / 1,75 мм"),
        ("Конец паза / конец языка", "x = −8 / x = −5,2"),
        ("Портал прототипа", "около 5–6 мм"),
    ]
    x, y = 268 * mm, 248 * mm
    c.setFont("DejaVuBold", 8)
    c.setFillColorRGB(*INK)
    c.drawString(x, y, "Управляемые размеры")
    y -= 6 * mm
    for label, value in rows:
        c.setFillColorRGB(0.96, 0.96, 0.95)
        c.rect(x, y - 1.2 * mm, 138 * mm, 6.2 * mm, stroke=0, fill=1)
        c.setFillColorRGB(*INK)
        c.setFont("DejaVu", 6.6)
        c.drawString(x + 1.5 * mm, y, label)
        c.setFont("DejaVuBold", 6.6)
        c.drawRightString(x + 136 * mm, y, value)
        y -= 6.4 * mm
    c.setFillColorRGB(*HAIR)
    c.setFont("DejaVu", 6.4)
    note = (
        "При 6° и 18° спица поворачивается вокруг шарнира, который лежит на номинальной оси. "
        "Канал остаётся на спице, а выход по латеральной коре сдвигается на несколько миллиметров — "
        "это указано в таблице, а не спрятано."
    )
    para(c, note, x, 40 * mm, 138 * mm, 28 * mm, SMALL)


def sheet_detail(c):
    header(c, 3, "Узел остеотомии, печать, крепёж")
    title_block(c, 3, "Контрольная схема М 3:1 и данные для прототипа")
    # schematic origin: model (0, 0) placed so x=-42..18 and y=-20..18 fit
    schematic(c, 140 * mm, 104 * mm, 3.0)

    c.setFillColorRGB(*INK)
    c.setFont("DejaVuBold", 8)
    c.drawString(250 * mm, 262 * mm, "Печать, слой 0,05 мм")
    c.setFont("DejaVu", 6.5)
    y = 254 * mm
    c.drawString(250 * mm, y, "Деталь")
    c.drawString(300 * mm, y, "Ориентация")
    c.drawRightString(402 * mm, y, "Габарит на столе, мм")
    y -= 2 * mm
    c.setStrokeColorRGB(*RULE)
    c.line(250 * mm, y, 404 * mm, y)
    y -= 5 * mm
    names = {
        "frame": "рамка", "blade": "лопатка", "turret": "турель", "clip": "клипса",
        "tongue_S": "язык S", "tongue_M": "язык M", "tongue_L": "язык L",
    }
    orient = {"Yup": "ось скольжения вверх", "bore": "каналы вертикально"}
    for item in VAL["print_files"]:
        size = " × ".join(f"{v:.1f}" for v in item["size_mm"])
        c.setFillColorRGB(*INK)
        c.setFont("DejaVu", 6.5)
        c.drawString(250 * mm, y, names.get(item["part"], item["part"]))
        c.drawString(300 * mm, y, orient[item["bed_orientation"]])
        c.drawRightString(402 * mm, y, size)
        y -= 5 * mm
    c.setFillColorRGB(*HAIR)
    c.setFont("DejaVu", 6.3)
    para(
        c,
        "Левая стопа — файлы *_LEFT, зеркало относительно плоскости XZ. "
        "Канал печатается Ø1,80 и разворачивается до 1,70–1,75 под спицу 1,6: "
        "усадку смолы в номинал не закладывать. Оправка Ø14 с пазом под язык M — "
        "только для стенда, в комплект для стопы не входит.",
        250 * mm, y - 28 * mm, 154 * mm, 26 * mm, SMALL,
    )

    c.setFillColorRGB(*INK)
    c.setFont("DejaVuBold", 8)
    c.drawString(250 * mm, 168 * mm, "Крепёж, не печатается")
    hardware_ru = [
        "M3×25 — винт смещения, 1 шт.",
        "Гайка M3 смещения, 1 — в дорсальное окно лопатки",
        "M3×10 — фиксатор языка, 1 шт.",
        "Гайка M3 языка, 1 — в плантарное окно полки",
        "M3×12 — фиксатор угла, 1 (отверстие 96, 102 или 108)",
        "Гайка M3 угла, 1 шт.",
        "M3×8 — ось шарнира, 1, только сверху",
    ]
    yy = 160 * mm
    for line in hardware_ru:
        c.setFont("DejaVu", 6.4)
        c.setFillColorRGB(*INK)
        c.drawString(250 * mm, yy, "·  " + line)
        yy -= 5.2 * mm

    c.setFont("DejaVuBold", 8)
    c.drawString(250 * mm, 112 * mm, "Геометрическая оценка, не назначение")
    para(
        c,
        "Грубый перевод смещения в угол: Δ ≈ arctan(T / 55 мм). "
        "T = 6 → 6,2°;  8 → 8,3°;  10 → 10,3°;  12 → 12,3°. "
        "55 мм — принятая длина плеча для оценки, не измерение конкретной кости. "
        "Решение о величине смещения модель не принимает.",
        250 * mm, 78 * mm, 154 * mm, 32 * mm, SMALL,
    )
    para(
        c,
        "<b>Портал.</b> Шейка языка и лопатка стоят рядом, около 4 мм вдоль кости. "
        "Поэтому прототип рассчитан на разрез около 5–6 мм, а не на 3–4 мм исходной методики. "
        "Это обмен: в тот же доступ входят и язык, и регулируемая лопатка.",
        250 * mm, 48 * mm, 154 * mm, 28 * mm, SMALL,
    )


def main():
    os.makedirs(OUT, exist_ok=True)
    pdf_path = os.path.join(OUT, "HALIA-1_drawing.pdf")
    c = pdfcanvas.Canvas(pdf_path, pagesize=PAGE)
    c.setTitle("HALIA-1 — чертёж прототипа")
    c.setAuthor("HALIA-1 prototype")
    for drawer in (sheet_general, sheet_views, sheet_detail):
        drawer(c)
        c.showPage()
    c.save()
    dxf_path = os.path.join(OUT, "HALIA-1_schematic.dxf")
    dxf_schematic(dxf_path)
    print(pdf_path)
    print(dxf_path)


if __name__ == "__main__":
    main()
