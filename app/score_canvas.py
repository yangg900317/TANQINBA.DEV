from __future__ import annotations

import traceback
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from app.chords import lookup_chord
from app.diagram import paint_diagram
from app.model import Score, key_alters, note_name, spell, transpose_key
from app.theme import DESK, INK, LINE, MUTED, PAPER, RED

SHARP_STEPS = [10, 7, 11, 8, 5, 9, 6]
FLAT_STEPS = [6, 9, 5, 8, 4, 7, 3]


def rhythmic_value(duration: float) -> float:
    for base in (0.25, 0.5, 1.0, 2.0, 4.0):
        if abs(duration - base) < 1e-3 or abs(duration - base * 1.5) < 1e-3:
            return base
    return duration


def is_dotted(duration: float) -> bool:
    value = rhythmic_value(duration)
    return abs(duration - value * 1.5) < 1e-3


@dataclass
class Pitch:
    step: int
    accidental: str
    y: float
    string: int
    fret: int


@dataclass
class Onset:
    beat: float
    duration: float
    x: float
    lyric: str
    pitches: list[Pitch] = field(default_factory=list)


@dataclass
class LaidChord:
    beat: float
    name: str
    x: float


@dataclass
class LaidMeasure:
    index: int
    x: float
    y: float
    w: float
    h: float
    content_left: float
    content_width: float
    staff_top: float
    tab_top: float
    lyric_y: float
    first: bool
    show_time: bool
    label: str
    onsets: list[Onset] = field(default_factory=list)
    chords: list[LaidChord] = field(default_factory=list)


class ScoreCanvas(QWidget):
    seekRequested = Signal(float, int, int)

    def __init__(self):
        super().__init__()
        self.score: Score | None = None
        self.zoom = 1.0
        self.beat = 0.0
        self.tempo = 72
        self.transpose = 0
        self.loop_a: int | None = None
        self.loop_b: int | None = None
        self.laid: list[LaidMeasure] = []
        self._content_bottom = 400
        self.space = 9.0
        self.tab_space = 11.0
        self.beat_w = 56.0
        self._layout_width = -1
        self.setMouseTracking(True)

    def set_score(self, score: Score) -> None:
        self.score = score
        self.tempo = score.tempo
        self.beat = 0.0
        self._layout_width = -1
        self._relayout()
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self.zoom = max(0.8, min(1.5, zoom))
        self._layout_width = -1
        self._relayout()
        self.update()

    def set_view(self, beat: float, tempo: int, transpose: int, loop_a: int | None, loop_b: int | None) -> None:
        self.beat = beat
        self.tempo = tempo
        self.transpose = transpose
        self.loop_a = loop_a
        self.loop_b = loop_b
        self.update()

    def cursor_anchor(self) -> QPointF:
        if not self.laid or self.score is None:
            return QPointF(0, 0)
        measure, x = self._cursor_x()
        return QPointF(x, measure.staff_top + measure.h * 0.35)

    def _metrics(self) -> None:
        self.space = 9.0 * self.zoom
        self.tab_space = 11.0 * self.zoom
        self.beat_w = 58.0 * self.zoom

    def _prelude(self, first: bool, show_time: bool) -> float:
        if not first or self.score is None:
            return 14 * self.zoom
        alters = len(key_alters(self.score.key))
        width = self.space * 5.1 + alters * self.space * 1.15 + self.space * 0.8
        if show_time:
            width += self.space * 2.5
        return width

    def _relayout(self) -> None:
        if self.score is None or self.width() < 80:
            return
        self._metrics()
        self._layout_width = self.width()
        score = self.score
        beats = score.beats_per_measure
        label_h = 16 * self.zoom
        chord_h = 54 * self.zoom
        gap = 16 * self.zoom
        lyric_h = 18 * self.zoom
        system_h = label_h + chord_h + 4 * self.space + gap + 5 * self.tab_space + lyric_h + 14 * self.zoom
        page_left = 16
        x_start = page_left + 48
        right_limit = self.width() - 22
        y = 188
        index = 0
        laid: list[LaidMeasure] = []
        system_index = 0
        while index < len(score.measures):
            used = 0.0
            row: list[tuple[int, float, bool, bool]] = []
            first = True
            while index < len(score.measures):
                show_time = system_index == 0 and first
                width = self._prelude(first, show_time) + beats * self.beat_w
                if row and used + width > right_limit - x_start:
                    break
                row.append((index, width, first, show_time))
                used += width
                index += 1
                first = False
            x = x_start
            for measure_index, width, is_first, show_time in row:
                laid.append(self._place(measure_index, x, y, width, system_h, is_first, show_time, label_h, chord_h, gap))
                x += width
            y += system_h + 18 * self.zoom
            system_index += 1
        self.laid = laid
        self._content_bottom = y + 8
        desired = int(self._content_bottom + 12)
        if self.minimumHeight() != desired:
            self.setMinimumHeight(desired)

    def _place(self, index: int, x: float, y: float, width: float, height: float, first: bool, show_time: bool, label_h: float, chord_h: float, gap: float) -> LaidMeasure:
        score = self.score
        assert score is not None
        measure = score.measures[index]
        beats = score.beats_per_measure
        staff_top = y + label_h + chord_h
        tab_top = staff_top + 4 * self.space + gap
        prelude = self._prelude(first, show_time)
        content_left = x + prelude
        content_width = beats * self.beat_w
        buckets: dict[float, list] = {}
        for note in measure.notes:
            buckets.setdefault(round(note.beat, 4), []).append(note)
        onsets: list[Onset] = []
        for local in sorted(buckets):
            notes = buckets[local]
            pitches: list[Pitch] = []
            lyric = ""
            for note in notes:
                midi = score.tuning[note.string - 1] + note.fret
                written = spell(midi, score.key)
                pitches.append(Pitch(
                    written.step,
                    written.accidental,
                    self._staff_y(staff_top, written.step),
                    note.string,
                    note.fret,
                ))
                if note.lyric:
                    lyric = note.lyric
            onsets.append(Onset(index * beats + local, notes[0].duration, content_left + (local / beats) * content_width, lyric, pitches))
        chords = [
            LaidChord(index * beats + chord.beat, chord.name, content_left + (chord.beat / beats) * content_width)
            for chord in measure.chords
        ]
        return LaidMeasure(
            index, x, y, width, height, content_left, content_width, staff_top, tab_top,
            tab_top + 5 * self.tab_space + 14 * self.zoom, first, show_time, measure.label, onsets, chords,
        )

    def _staff_y(self, staff_top: float, step: int) -> float:
        bottom = staff_top + 4 * self.space
        return bottom - (step - 2) * (self.space / 2)

    def resizeEvent(self, event) -> None:
        self._relayout()
        super().resizeEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            if self._layout_width != self.width():
                self._relayout()
            self._paint(painter)
        except Exception:
            traceback.print_exc()
            painter.setPen(QColor(RED))
            painter.drawText(20, 30, "乐谱绘制出错，请查看终端输出")
        painter.end()

    def _paint(self, painter: QPainter) -> None:
        painter.fillRect(self.rect(), QColor(DESK))
        if self.score is None:
            return
        page = QRectF(10, 10, self.width() - 20, max(self.height() - 20, self._content_bottom - 4))
        painter.fillRect(page.translated(3, 3), QColor(0, 0, 0, 22))
        painter.fillRect(page, QColor(PAPER))
        painter.setPen(QPen(QColor("#e3d9c4"), 1))
        painter.drawRect(page)
        self._paint_header(painter, page)
        for measure in self.laid:
            self._paint_measure(painter, measure)
        self._paint_cursor(painter)

    def _paint_header(self, painter: QPainter, page: QRectF) -> None:
        score = self.score
        assert score is not None
        title_font = QFont("Microsoft YaHei UI")
        title_font.setPixelSize(22)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(INK))
        painter.drawText(QRectF(page.left() + 150, page.top() + 12, page.width() - 300, 30), Qt.AlignmentFlag.AlignCenter, score.title)
        sub_font = QFont("Microsoft YaHei UI")
        sub_font.setPixelSize(12)
        painter.setFont(sub_font)
        painter.setPen(QColor(MUTED))
        painter.drawText(QRectF(page.left() + 150, page.top() + 40, page.width() - 300, 18), Qt.AlignmentFlag.AlignCenter, score.subtitle)

        info = QFont("Microsoft YaHei UI")
        info.setPixelSize(11)
        painter.setFont(info)
        painter.setPen(QColor(INK))
        left = page.left() + 22
        top = page.top() + 64
        painter.drawText(QRectF(left, top, 180, 16), f"1 = {score.key}    {score.beats_per_measure}/{score.beat_unit}")
        self._tempo_mark(painter, left, top + 20)
        names = [note_name(midi) for midi in score.tuning]
        marks = "①②③④⑤⑥"
        for row, (low, high) in enumerate(((0, 3), (1, 4), (2, 5))):
            painter.drawText(
                QRectF(left, top + 40 + row * 15, 190, 15),
                f"{marks[low]} = {names[low]}     {marks[high]} = {names[high]}",
            )
        if score.artist:
            painter.drawText(QRectF(page.right() - 180, top + 8, 156, 18), Qt.AlignmentFlag.AlignRight, f"演唱：{score.artist}")
        if self.transpose:
            sounded = transpose_key(score.key, self.transpose)
            sign = f"+{self.transpose}" if self.transpose > 0 else str(self.transpose)
            painter.setPen(QColor(RED))
            painter.drawText(QRectF(page.right() - 230, top + 30, 206, 18), Qt.AlignmentFlag.AlignRight, f"试听 {sounded}（变调 {sign}）")

    def _tempo_mark(self, painter: QPainter, x: float, y: float) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(INK))
        painter.drawEllipse(QRectF(x, y + 6, 7, 5))
        painter.setPen(QPen(QColor(INK), 1.2))
        painter.drawLine(QPointF(x + 7, y + 8), QPointF(x + 7, y - 6))
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(11)
        painter.setFont(font)
        painter.drawText(QRectF(x + 12, y - 4, 70, 18), f"= {self.tempo}")

    def _paint_measure(self, painter: QPainter, measure: LaidMeasure) -> None:
        score = self.score
        assert score is not None
        beats = score.beats_per_measure
        start = measure.index * beats
        current = start <= self.beat < start + beats
        loop = self._in_loop(measure.index)
        if loop:
            painter.fillRect(QRectF(measure.x, measure.y, measure.w, measure.h), QColor(208, 18, 26, 24))
        elif current and self.beat >= 0:
            painter.fillRect(QRectF(measure.x, measure.y, measure.w, measure.h), QColor(255, 236, 196, 90))

        painter.setPen(QPen(QColor(LINE), 1))
        for line in range(5):
            y = measure.staff_top + line * self.space
            painter.drawLine(QPointF(measure.x, y), QPointF(measure.x + measure.w, y))
        for line in range(6):
            y = measure.tab_top + line * self.tab_space
            painter.drawLine(QPointF(measure.x, y), QPointF(measure.x + measure.w, y))
        self._barline(painter, measure, beats)
        if measure.first:
            self._system_marks(painter, measure)
        self._label(painter, measure)
        self._notes(painter, measure)
        active_beat = self._active_chord_beat()
        for chord in measure.chords:
            rect = QRectF(chord.x - 18, measure.y + 16 * self.zoom, 36 * self.zoom, 50 * self.zoom)
            paint_diagram(painter, chord.name, lookup_chord(chord.name), rect, abs(chord.beat - active_beat) < 1e-3 if active_beat is not None else False)

    def _in_loop(self, index: int) -> bool:
        if self.loop_a is None or self.score is None:
            return False
        end = self.loop_b if self.loop_b is not None else len(self.score.measures) - 1
        lo, hi = sorted((self.loop_a, end))
        return lo <= index <= hi

    def _active_chord_beat(self) -> float | None:
        found = None
        for measure in self.laid:
            for chord in measure.chords:
                if chord.beat <= self.beat + 1e-6:
                    found = chord.beat
        return found

    def _barline(self, painter: QPainter, measure: LaidMeasure, beats: int) -> None:
        painter.setPen(QPen(QColor(INK), 1))
        if not measure.first:
            self._line(painter, measure.x, measure)
        last = self.score is not None and measure.index == len(self.score.measures) - 1
        right = measure.x + measure.w
        if last:
            self._line(painter, right - 6, measure)
            painter.setPen(QPen(QColor(INK), 3))
            self._line(painter, right - 2, measure)
        else:
            self._line(painter, right, measure)

    def _line(self, painter: QPainter, x: float, measure: LaidMeasure) -> None:
        painter.drawLine(QPointF(x, measure.staff_top), QPointF(x, measure.staff_top + 4 * self.space))
        painter.drawLine(QPointF(x, measure.tab_top), QPointF(x, measure.tab_top + 5 * self.tab_space))

    def _system_marks(self, painter: QPainter, measure: LaidMeasure) -> None:
        self._brace(painter, measure.x - 24, measure.staff_top, measure.tab_top + 5 * self.tab_space)
        font = QFont("Times New Roman")
        font.setBold(True)
        font.setPixelSize(max(8, int(self.tab_space * 0.78)))
        painter.setFont(font)
        painter.setPen(QColor(INK))
        for index, letter in enumerate("TAB"):
            painter.drawText(
                QRectF(measure.x - 16, measure.tab_top + index * self.tab_space - 1, 14, self.tab_space),
                Qt.AlignmentFlag.AlignCenter,
                letter,
            )
        self._clef(painter, measure.x + 2, measure.staff_top)
        self._signature(painter, measure)

    def _brace(self, painter: QPainter, x: float, y1: float, y2: float) -> None:
        mid = (y1 + y2) / 2
        path = QPainterPath()
        path.moveTo(x + 9, y1)
        path.cubicTo(x, y1 + 8, x - 4, mid - 18, x + 3, mid)
        path.cubicTo(x - 4, mid + 18, x, y2 - 8, x + 9, y2)
        painter.setPen(QPen(QColor(INK), 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def _clef(self, painter: QPainter, x: float, staff_top: float) -> None:
        font = QFont("Segoe UI Symbol")
        font.setPixelSize(int(self.space * 4.15))
        if QFontMetrics(font).inFontUcs4(0x1D11E):
            painter.setFont(font)
            painter.setPen(QColor(INK))
            painter.drawText(QRectF(x - 4, staff_top - self.space * 0.7, self.space * 4.4, self.space * 5.2), "𝄞")
            return
        self._clef_path(painter, x + self.space * 0.7, staff_top + self.space * 3)

    def _clef_path(self, painter: QPainter, x: float, gy: float) -> None:
        space = self.space
        path = QPainterPath()
        path.moveTo(x, gy - space * 1.6)
        path.cubicTo(x - space * 0.2, gy - space * 2.7, x + space * 1.3, gy - space * 2.8, x + space * 1.1, gy - space * 1.5)
        path.cubicTo(x + space * 0.8, gy - space * 0.2, x - space * 0.15, gy + space * 0.5, x + space * 0.35, gy + space * 1.15)
        path.cubicTo(x + space * 0.9, gy + space * 1.8, x + space * 1.5, gy + space * 0.9, x + space * 0.85, gy + space * 0.15)
        path.cubicTo(x + space * 0.2, gy - space * 0.7, x + space * 0.15, gy - space * 1.2, x + space * 0.7, gy - space * 1.7)
        painter.setPen(QPen(QColor(INK), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        tail = QPainterPath()
        tail.moveTo(x + space * 1.05, gy - space * 1.45)
        tail.cubicTo(x + space * 1.35, gy + space * 0.4, x + space * 0.7, gy + space * 2.3, x - space * 0.15, gy + space * 2.8)
        painter.drawPath(tail)

    def _signature(self, painter: QPainter, measure: LaidMeasure) -> None:
        score = self.score
        assert score is not None
        alters = key_alters(score.key)
        steps = SHARP_STEPS if any(value > 0 for value in alters.values()) else FLAT_STEPS
        glyph = "#" if any(value > 0 for value in alters.values()) else "b"
        x = measure.x + self.space * 4.7
        for index in range(len(alters)):
            y = self._staff_y(measure.staff_top, steps[index])
            if glyph == "#":
                self._sharp(painter, x, y, self.space * 0.95)
            else:
                self._flat(painter, x, y, self.space * 0.95)
            x += self.space * 0.9
        if measure.show_time:
            font = QFont("Times New Roman")
            font.setBold(True)
            font.setPixelSize(int(self.space * 2.15))
            painter.setFont(font)
            painter.setPen(QColor(INK))
            painter.drawText(QRectF(x + 2, measure.staff_top - 1, self.space * 1.8, self.space * 2.1), Qt.AlignmentFlag.AlignCenter, str(score.beats_per_measure))
            painter.drawText(QRectF(x + 2, measure.staff_top + self.space * 1.9, self.space * 1.8, self.space * 2.1), Qt.AlignmentFlag.AlignCenter, str(score.beat_unit))

    def _label(self, painter: QPainter, measure: LaidMeasure) -> None:
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(max(9, int(10 * self.zoom)))
        painter.setFont(font)
        painter.setPen(QColor(MUTED))
        painter.drawText(QRectF(measure.x + 2, measure.y, 24, 14 * self.zoom), str(measure.index + 1))
        if not measure.label:
            return
        box_font = QFont("Microsoft YaHei UI")
        box_font.setPixelSize(max(10, int(11 * self.zoom)))
        painter.setFont(box_font)
        width = max(36, 14 * len(measure.label) + 12)
        rect = QRectF(measure.x + 18, measure.y, width, 15 * self.zoom)
        painter.setPen(QPen(QColor(INK), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 2, 2)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, measure.label)

    def _notes(self, painter: QPainter, measure: LaidMeasure) -> None:
        groups = self._beam_groups(measure)
        beamed: set[int] = set()
        directions: dict[int, bool] = {}
        for group in groups:
            up = self._group_up(group)
            for onset in group:
                beamed.add(id(onset))
                directions[id(onset)] = up
            self._beam(painter, group, up)
        for onset in measure.onsets:
            up = directions.get(id(onset), self._group_up([onset]))
            self._onset(painter, measure, onset, up, id(onset) in beamed)

    def _beam_groups(self, measure: LaidMeasure) -> list[list[Onset]]:
        score = self.score
        assert score is not None
        origin = measure.index * score.beats_per_measure
        middle = origin + score.beats_per_measure / 2
        groups: list[list[Onset]] = []
        current: list[Onset] = []
        for onset in measure.onsets:
            value = rhythmic_value(onset.duration)
            if value > 0.5 + 1e-6:
                if len(current) >= 2:
                    groups.append(current)
                current = []
                continue
            if current:
                previous = current[-1]
                crosses = previous.beat < middle <= onset.beat
                contiguous = abs((previous.beat + previous.duration) - onset.beat) < 1e-3
                if crosses or not contiguous:
                    if len(current) >= 2:
                        groups.append(current)
                    current = [onset]
                else:
                    current.append(onset)
            else:
                current = [onset]
        if len(current) >= 2:
            groups.append(current)
        return groups

    def _group_up(self, group: list[Onset]) -> bool:
        steps = [pitch.step for onset in group for pitch in onset.pitches]
        if not steps:
            return True
        return sum(steps) / len(steps) < 6

    def _beam(self, painter: QPainter, group: list[Onset], up: bool) -> None:
        tips = [self._stem_tip(onset, up) for onset in group]
        y1, y2 = tips[0][1], tips[-1][1]
        x1, x2 = group[0].x, group[-1].x
        painter.setPen(QPen(QColor(INK), max(2.2, self.space * 0.42), Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        painter.drawLine(QPointF(tips[0][0], y1), QPointF(tips[-1][0], y2))
        if all(rhythmic_value(onset.duration) <= 0.25 for onset in group):
            offset = 4.5 if up else -4.5
            painter.drawLine(QPointF(tips[0][0], y1 + offset), QPointF(tips[-1][0], y2 + offset))
        for onset, (sx, _tip) in zip(group, tips):
            span = (onset.x - x1) / (x2 - x1) if abs(x2 - x1) > 0.1 else 0
            beam_y = y1 + (y2 - y1) * span
            attach = self._attach_y(onset, up)
            painter.setPen(QPen(QColor(INK), 1.15))
            painter.drawLine(QPointF(sx, attach), QPointF(sx, beam_y))

    def _stem_tip(self, onset: Onset, up: bool) -> tuple[float, float]:
        length = self.space * 3.3
        attach = self._attach_y(onset, up)
        sx = self._stem_x(onset, up)
        return sx, attach - length if up else attach + length

    def _attach_y(self, onset: Onset, up: bool) -> float:
        ys = [pitch.y for pitch in onset.pitches]
        return (min(ys) if up else max(ys))

    def _stem_x(self, onset: Onset, up: bool) -> float:
        rx = self.space * 0.58
        return onset.x + rx - 0.8 if up else onset.x - rx + 0.8

    def _onset(self, painter: QPainter, measure: LaidMeasure, onset: Onset, up: bool, beamed: bool) -> None:
        sounding = onset.beat <= self.beat < onset.beat + onset.duration and self.beat >= 0
        color = QColor(RED if sounding else INK)
        shifts = self._second_shifts(onset.pitches, up)
        for pitch, shift in zip(onset.pitches, shifts):
            self._ledgers(painter, measure, onset.x + shift, pitch.step)
            if pitch.accidental:
                self._accidental(painter, onset.x + shift - self.space * 1.35, pitch.y, pitch.accidental)
            self._head(painter, onset.x + shift, pitch.y, rhythmic_value(onset.duration) < 2, color)
            self._tab_number(painter, measure, pitch, onset.x, color)
        if is_dotted(onset.duration) and onset.pitches:
            self._dot(painter, onset, color)
        value = rhythmic_value(onset.duration)
        if value < 4 and not beamed:
            sx, tip = self._stem_tip(onset, up)
            painter.setPen(QPen(color, 1.15))
            painter.drawLine(QPointF(sx, self._attach_y(onset, up)), QPointF(sx, tip))
            if value <= 0.5:
                self._flag(painter, sx, tip, up, color)
        if onset.lyric:
            font = QFont("Microsoft YaHei UI")
            font.setPixelSize(max(10, int(12 * self.zoom)))
            painter.setFont(font)
            painter.setPen(color)
            painter.drawText(QRectF(onset.x - 18, measure.lyric_y, 36, 16), Qt.AlignmentFlag.AlignCenter, onset.lyric)

    def _second_shifts(self, pitches: list[Pitch], up: bool) -> list[float]:
        order = sorted(range(len(pitches)), key=lambda index: pitches[index].step)
        shifts = [0.0] * len(pitches)
        for previous, current in zip(order, order[1:]):
            if pitches[current].step - pitches[previous].step <= 1:
                target = current if up else previous
                shifts[target] = self.space * 1.15
        return shifts

    def _ledgers(self, painter: QPainter, measure: LaidMeasure, x: float, step: int) -> None:
        lines: list[int] = []
        if step <= 0:
            line = 0
            while line >= step:
                lines.append(line)
                line -= 2
        if step >= 12:
            line = 12
            while line <= step:
                lines.append(line)
                line += 2
        painter.setPen(QPen(QColor(INK), 1))
        for line in lines:
            y = self._staff_y(measure.staff_top, line)
            painter.drawLine(QPointF(x - self.space * 0.95, y), QPointF(x + self.space * 0.95, y))

    def _head(self, painter: QPainter, x: float, y: float, filled: bool, color: QColor) -> None:
        painter.save()
        painter.translate(x, y)
        painter.rotate(-18)
        painter.setPen(QPen(color, 1.25))
        painter.setBrush(color if filled else QColor(PAPER))
        rx = self.space * 0.62
        ry = self.space * 0.46
        painter.drawEllipse(QRectF(-rx, -ry, rx * 2, ry * 2))
        painter.restore()

    def _tab_number(self, painter: QPainter, measure: LaidMeasure, pitch: Pitch, x: float, color: QColor) -> None:
        y = measure.tab_top + (pitch.string - 1) * self.tab_space
        text = str(pitch.fret)
        width = 12 if pitch.fret < 10 else 16
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PAPER))
        painter.drawRoundedRect(QRectF(x - width / 2, y - 6.5, width, 13), 2, 2)
        font = QFont("Arial")
        font.setBold(True)
        font.setPixelSize(max(9, int(10 * self.zoom)))
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(QRectF(x - 10, y - 8, 20, 16), Qt.AlignmentFlag.AlignCenter, text)

    def _dot(self, painter: QPainter, onset: Onset, color: QColor) -> None:
        pitch = max(onset.pitches, key=lambda item: item.y)
        y = pitch.y - self.space / 2 if pitch.step % 2 == 0 else pitch.y
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF(onset.x + self.space * 0.85, y - 1.8, 3.6, 3.6))

    def _flag(self, painter: QPainter, x: float, y: float, up: bool, color: QColor) -> None:
        path = QPainterPath()
        path.moveTo(x, y)
        if up:
            path.cubicTo(x + 11, y + 7, x + 13, y + 18, x + 3, y + 26)
            path.cubicTo(x + 11, y + 16, x + 8, y + 10, x, y + 13)
        else:
            path.cubicTo(x + 11, y - 7, x + 13, y - 18, x + 3, y - 26)
            path.cubicTo(x + 11, y - 16, x + 8, y - 10, x, y - 13)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)

    def _accidental(self, painter: QPainter, x: float, y: float, kind: str) -> None:
        size = self.space
        if kind == "#":
            self._sharp(painter, x, y, size)
        elif kind == "b":
            self._flat(painter, x, y, size)
        else:
            self._natural(painter, x, y, size)

    def _sharp(self, painter: QPainter, x: float, y: float, size: float) -> None:
        painter.setPen(QPen(QColor(INK), max(1.0, size * 0.11)))
        painter.drawLine(QPointF(x, y - size * 0.55), QPointF(x, y + size * 0.55))
        painter.drawLine(QPointF(x + size * 0.36, y - size * 0.55), QPointF(x + size * 0.36, y + size * 0.55))
        painter.drawLine(QPointF(x - size * 0.12, y - size * 0.08), QPointF(x + size * 0.5, y - size * 0.24))
        painter.drawLine(QPointF(x - size * 0.12, y + size * 0.24), QPointF(x + size * 0.5, y + size * 0.08))

    def _flat(self, painter: QPainter, x: float, y: float, size: float) -> None:
        painter.setPen(QPen(QColor(INK), max(1.1, size * 0.12)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(x, y + size * 0.42), QPointF(x, y - size * 1.05))
        path = QPainterPath()
        path.moveTo(x, y + size * 0.4)
        path.cubicTo(x + size * 0.62, y, x + size * 0.55, y - size * 0.42, x, y - size * 0.02)
        painter.drawPath(path)

    def _natural(self, painter: QPainter, x: float, y: float, size: float) -> None:
        painter.setPen(QPen(QColor(INK), max(1.0, size * 0.11)))
        painter.drawLine(QPointF(x, y - size * 0.55), QPointF(x, y + size * 0.25))
        painter.drawLine(QPointF(x + size * 0.34, y - size * 0.25), QPointF(x + size * 0.34, y + size * 0.55))
        painter.drawLine(QPointF(x, y - size * 0.08), QPointF(x + size * 0.34, y - size * 0.28))
        painter.drawLine(QPointF(x, y + size * 0.25), QPointF(x + size * 0.34, y + size * 0.05))

    def _cursor_x(self) -> tuple[LaidMeasure, float]:
        score = self.score
        assert score is not None and self.laid
        beats = score.beats_per_measure
        if self.beat < 0:
            measure = self.laid[0]
            return measure, measure.content_left
        position = min(self.beat, score.total_beats)
        index = min(len(self.laid) - 1, int(position // beats))
        if position >= score.total_beats:
            measure = self.laid[-1]
            return measure, measure.x + measure.w - 2
        measure = self.laid[index]
        local = position - index * beats
        return measure, measure.content_left + (local / beats) * measure.content_width

    def _paint_cursor(self, painter: QPainter) -> None:
        if not self.laid:
            return
        measure, x = self._cursor_x()
        top = measure.staff_top - 8
        bottom = measure.lyric_y + 12
        painter.setPen(QPen(QColor(RED), 1.6))
        painter.drawLine(QPointF(x, top + 6), QPointF(x, bottom))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(RED))
        path = QPainterPath()
        path.moveTo(x - 5, top)
        path.lineTo(x + 5, top)
        path.lineTo(x, top + 8)
        painter.drawPath(path)
        if self.beat < 0:
            font = QFont("Microsoft YaHei UI")
            font.setPixelSize(11)
            painter.setFont(font)
            painter.setPen(QColor(RED))
            painter.drawText(QRectF(x + 6, top - 2, 48, 16), "预备")

    def mousePressEvent(self, event) -> None:
        if self.score is None:
            return
        point = event.position()
        beats = self.score.beats_per_measure
        for measure in self.laid:
            if QRectF(measure.x, measure.y, measure.w, measure.h).contains(point):
                local = (point.x() - measure.content_left) / max(1.0, measure.content_width)
                local = min(max(local, 0.0), 0.999) * beats
                local = round(local * 2) / 2
                mods = event.modifiers()
                value = int(getattr(mods, "value", mods))
                self.seekRequested.emit(measure.index * beats + local, measure.index, value)
                return
