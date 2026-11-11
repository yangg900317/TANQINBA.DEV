"""Render the score to PNG files so the layout can be checked without a speaker."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from app.chords import lookup_chord
from app.diagram import paint_diagram
from app.fretboard import Fretboard
from app.library import default_score
from app.score_canvas import ScoreCanvas


def render_widget(widget, path: str) -> None:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("white"))
    widget.render(image)
    image.save(path)


def main() -> None:
    os.makedirs("_preview", exist_ok=True)
    app = QApplication(sys.argv)
    score = default_score()
    canvas = ScoreCanvas()
    canvas.resize(1180, 400)
    canvas.set_score(score)
    canvas.resize(1180, max(canvas.minimumHeight(), 400))
    canvas.set_view(0, score.tempo, 0, None, None)
    render_widget(canvas, "_preview/score.png")

    canvas.set_view(5.25, 72, 0, 4, 7)
    render_widget(canvas, "_preview/score_play.png")

    board = Fretboard()
    board.resize(1180, 118)
    board.set_state(score.tuning, lookup_chord("G"), [(1, 3, "melody"), (2, 0, "rhythm")])
    render_widget(board, "_preview/fretboard.png")

    card = QImage(180, 210, QImage.Format.Format_ARGB32_Premultiplied)
    card.fill(QColor("#fffdf8"))
    painter = QPainter(card)
    paint_diagram(painter, "G", lookup_chord("G"), QRectF(10, 6, 160, 196), False)
    painter.end()
    card.save("_preview/chord.png")
    print("wrote _preview")


if __name__ == "__main__":
    main()
