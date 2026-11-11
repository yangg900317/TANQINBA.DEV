from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from app.chords import ChordShape
from app.theme import INK, RED


def paint_diagram(painter: QPainter, name: str, shape: ChordShape | None, rect: QRectF, active: bool = False) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    name_height = min(18.0, rect.height() * 0.24) if name else 0.0
    if name:
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(max(9, int(name_height * 0.85)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(RED if active else INK))
        painter.drawText(QRectF(rect.left(), rect.top(), rect.width(), name_height), Qt.AlignmentFlag.AlignCenter, name)
    grid = QRectF(rect.left() + 2, rect.top() + name_height, rect.width() - 4, rect.height() - name_height)
    if shape is None or grid.height() < 16 or grid.width() < 16:
        painter.restore()
        return

    marker_h = max(7.0, grid.height() * 0.16)
    left = grid.left() + (8 if not shape.show_nut else 2)
    top = grid.top() + marker_h
    width = grid.width() - (10 if not shape.show_nut else 4)
    rows = 4
    used = [fret - shape.base + 1 for fret in shape.frets if fret > 0]
    if used:
        rows = max(4, max(used))
    height = grid.height() - marker_h - 2
    string_gap = width / 5
    fret_gap = height / rows

    painter.setPen(QPen(QColor(INK), 1))
    for index in range(6):
        x = left + index * string_gap
        painter.drawLine(int(x), int(top), int(x), int(top + height))
    for row in range(rows + 1):
        y = top + row * fret_gap
        thickness = 2.4 if row == 0 and shape.show_nut else 1
        painter.setPen(QPen(QColor(INK), thickness))
        painter.drawLine(int(left), int(y), int(left + width), int(y))

    if not shape.show_nut:
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(max(8, int(fret_gap * 0.55)))
        painter.setFont(font)
        painter.setPen(QColor(INK))
        painter.drawText(QRectF(grid.left() - 2, top, 12, fret_gap), Qt.AlignmentFlag.AlignVCenter, str(shape.base))

    font = QFont("Microsoft YaHei UI")
    font.setPixelSize(max(7, int(marker_h * 0.8)))
    painter.setFont(font)
    for index, fret in enumerate(shape.frets):
        x = left + index * string_gap
        if fret == 0 and shape.show_nut:
            painter.setPen(QColor(INK))
            painter.drawText(QRectF(x - 6, grid.top(), 12, marker_h), Qt.AlignmentFlag.AlignCenter, "○")
        elif fret < 0:
            painter.setPen(QColor(INK))
            painter.drawText(QRectF(x - 6, grid.top(), 12, marker_h), Qt.AlignmentFlag.AlignCenter, "×")

    barre = shape.barre
    radius = min(string_gap, fret_gap) * 0.34
    if barre is not None:
        indexes = [index for index, fret in enumerate(shape.frets) if fret == barre]
        y = top + (barre - shape.base + 0.5) * fret_gap
        x1 = left + indexes[0] * string_gap
        x2 = left + indexes[-1] * string_gap
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(RED if active else INK))
        painter.drawRoundedRect(QRectF(x1 - radius, y - radius, x2 - x1 + radius * 2, radius * 2), radius, radius)

    for index, fret in enumerate(shape.frets):
        if fret <= 0 or fret == barre:
            continue
        x = left + index * string_gap
        y = top + (fret - shape.base + 0.5) * fret_gap
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(RED if active else INK))
        painter.drawEllipse(QRectF(x - radius, y - radius, radius * 2, radius * 2))
    painter.restore()
