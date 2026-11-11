from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.chords import ChordShape
from app.model import note_name
from app.theme import AMBER, MUTED, RED


class Fretboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(118)
        self.tuning = [64, 59, 55, 50, 45, 40]
        self.chord: ChordShape | None = None
        self.active: list[tuple[int, int, str]] = []
        self.frets = 12

    def set_state(self, tuning: list[int], chord: ChordShape | None, active: list[tuple[int, int, str]]) -> None:
        self.tuning = list(tuning)
        self.chord = chord
        self.active = list(active)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f3efe4"))
        nut = 62.0
        right = self.width() - 14
        top = 18.0
        bottom = self.height() - 22.0
        span = max(40.0, right - nut)
        scale = span / (1 - 2 ** (-self.frets / 12))

        def fret_line(fret: int) -> float:
            if fret <= 0:
                return nut
            return nut + scale * (1 - 2 ** (-fret / 12))

        painter.setPen(QPen(QColor("#c9b89a"), 8))
        painter.drawLine(int(nut), int(top), int(right), int(top))
        painter.drawLine(int(nut), int(bottom), int(right), int(bottom))
        painter.setPen(QPen(QColor("#d7c7a6"), 1))
        for index in range(1, 6):
            y = top + (bottom - top) * index / 5
            painter.drawLine(int(nut), int(y), int(right), int(y))

        for string in range(6):
            y = top + (bottom - top) * string / 5
            painter.setPen(QPen(QColor("#8d8070"), 1.1 + string * 0.35))
            painter.drawLine(int(nut), int(y), int(right), int(y))
            font = QFont("Microsoft YaHei UI")
            font.setPixelSize(10)
            painter.setFont(font)
            painter.setPen(QColor(MUTED))
            painter.drawText(QRectF(0, y - 8, 30, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, note_name(self.tuning[string]))

        painter.setPen(QPen(QColor("#f7f1e4"), 5))
        painter.drawLine(int(nut), int(top - 2), int(nut), int(bottom + 2))
        painter.setPen(QPen(QColor("#8a7b66"), 1))
        for fret in range(1, self.frets + 1):
            x = fret_line(fret)
            painter.drawLine(int(x), int(top), int(x), int(bottom))
        font = QFont("Times New Roman")
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(QColor(MUTED))
        for fret in (1, 3, 5, 7, 9, 12):
            x = (fret_line(fret - 1) + fret_line(fret)) / 2
            painter.drawText(QRectF(x - 8, bottom + 2, 16, 14), Qt.AlignmentFlag.AlignCenter, str(fret))
            if fret in (3, 5, 7, 9, 12):
                painter.setBrush(QColor(210, 190, 160, 150))
                painter.setPen(Qt.PenStyle.NoPen)
                y = (top + bottom) / 2
                painter.drawEllipse(QRectF(x - 3.5, y - 3.5, 7, 7))

        def dot(string: int, fret: int, color: QColor, radius: float) -> None:
            y = top + (bottom - top) * (string - 1) / 5
            if fret <= 0:
                x = nut - 16
            elif fret > self.frets:
                return
            else:
                x = (fret_line(fret - 1) + fret_line(fret)) / 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(x - radius, y - radius, radius * 2, radius * 2))

        if self.chord is not None:
            for index, fret in enumerate(self.chord.frets):
                if fret >= 0:
                    dot(6 - index, fret, QColor(AMBER), 6.5)
        for string, fret, role in self.active:
            color = QColor(RED) if role == "melody" else QColor("#e07a2f")
            dot(string, fret, color, 7.5 if role == "melody" else 6)
        painter.setPen(QColor(MUTED))
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(10)
        painter.setFont(font)
        painter.drawText(self.width() - 168, 13, "红点是旋律，黄点是和弦")
        painter.end()
