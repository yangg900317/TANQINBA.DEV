from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.audio import AudioOutput
from app.chords import RHYTHM_LABELS, lookup_chord
from app.diagram import paint_diagram
from app.engine import Engine
from app.fretboard import Fretboard
from app.library import default_score, write_default
from app.model import DEFAULT_SCORE_PATH, SCORES_DIR, Score, ScoreError, load_score, transpose_key
from app.score_canvas import ScoreCanvas
from PySide6.QtCore import QRectF


class ChordCard(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(188)
        self.name = ""

    def set_chord(self, name: str) -> None:
        if name != self.name:
            self.name = name
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fffdf8"))
        painter.setPen(QColor("#eadfcd"))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
        shape = lookup_chord(self.name) if self.name else None
        paint_diagram(painter, self.name or "—", shape, QRectF(self.rect().adjusted(16, 8, -16, -8)), False)
        painter.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("吉他谱播放器")
        self.resize(1280, 820)
        self.setMinimumSize(1020, 680)
        self.engine = Engine(self._startup_score())
        self.audio = AudioOutput(self.engine)
        self.audio.start()
        self._scrubbing = False
        self._view_key = None
        self._build()
        self._bind()
        self._show_score()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)
        self.setAcceptDrops(True)

    def _startup_score(self) -> Score:
        try:
            if not DEFAULT_SCORE_PATH.exists():
                write_default()
            return load_score(DEFAULT_SCORE_PATH)
        except ScoreError:
            return default_score()

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(54)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(16, 8, 16, 8)
        title = QLabel("吉他谱播放器")
        title.setObjectName("appTitle")
        self.header_song = QLabel()
        self.header_song.setObjectName("songTitle")
        self.open_button = QPushButton("打开乐谱")
        self.open_button.setObjectName("openButton")
        zoom_label = QLabel("缩放")
        zoom_label.setObjectName("headerLabel")
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(80, 150)
        self.zoom.setValue(100)
        self.zoom.setFixedWidth(120)
        header_row.addWidget(title)
        header_row.addSpacing(16)
        header_row.addWidget(self.header_song, 1)
        header_row.addWidget(zoom_label)
        header_row.addWidget(self.zoom)
        header_row.addSpacing(8)
        header_row.addWidget(self.open_button)
        outer.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.canvas = ScoreCanvas()
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().installEventFilter(self)
        body.addWidget(self.scroll, 1)

        side_scroll = QScrollArea()
        side_scroll.setObjectName("sideScroll")
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side_scroll.setFixedWidth(280)
        side = QWidget()
        side.setObjectName("side")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(14, 14, 14, 14)
        side_layout.setSpacing(8)
        side_layout.addWidget(self._caption("曲谱信息"))
        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setObjectName("info")
        side_layout.addWidget(self.info_label)
        self.where_label = QLabel("第 1 小节")
        self.where_label.setObjectName("where")
        self.where_label.setFixedHeight(28)
        side_layout.addWidget(self.where_label)
        side_layout.addWidget(self._caption("当前和弦"))
        self.chord_card = ChordCard()
        self.chord_card.setFixedHeight(156)
        side_layout.addWidget(self.chord_card)
        side_layout.addWidget(self._caption("反复"))
        loop_row = QHBoxLayout()
        self.loop_a = QPushButton("设 A")
        self.loop_b = QPushButton("设 B")
        self.loop_clear = QPushButton("清除")
        loop_row.addWidget(self.loop_a)
        loop_row.addWidget(self.loop_b)
        loop_row.addWidget(self.loop_clear)
        side_layout.addLayout(loop_row)
        self.loop_label = QLabel("未设置")
        self.loop_label.setObjectName("muted")
        side_layout.addWidget(self.loop_label)
        side_layout.addStretch(1)
        side_scroll.setWidget(side)
        body.addWidget(side_scroll)
        outer.addLayout(body, 1)

        self.fretboard = Fretboard()
        outer.addWidget(self.fretboard)

        options = QFrame()
        options.setObjectName("transport")
        option_row = QHBoxLayout(options)
        option_row.setContentsMargins(12, 4, 12, 4)
        self.melody = QCheckBox("旋律")
        self.melody.setChecked(True)
        self.metronome = QCheckBox("节拍器")
        self.count_in = QCheckBox("预备拍")
        self.follow = QCheckBox("跟谱滚动")
        self.follow.setChecked(True)
        for box in (self.melody, self.metronome, self.count_in, self.follow):
            option_row.addWidget(box)
        option_row.addSpacing(12)
        option_row.addWidget(QLabel("伴奏"))
        self.rhythm = QComboBox()
        self.rhythm.setFixedWidth(110)
        for label, value in RHYTHM_LABELS:
            self.rhythm.addItem(label, value)
        option_row.addWidget(self.rhythm)
        option_row.addStretch(1)
        outer.addWidget(options)

        transport = QFrame()
        transport.setObjectName("transport")
        row = QHBoxLayout(transport)
        row.setContentsMargins(12, 8, 12, 8)
        self.play_button = QPushButton("播放")
        self.play_button.setObjectName("play")
        self.stop_button = QPushButton("停止")
        self.progress = QSlider(Qt.Orientation.Horizontal)
        self.progress.setRange(0, 10000)
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setMinimumWidth(92)
        row.addWidget(self.play_button)
        row.addWidget(self.stop_button)
        row.addWidget(self.progress, 1)
        row.addWidget(self.time_label)
        row.addSpacing(10)
        row.addWidget(QLabel("速度"))
        self.tempo = QSlider(Qt.Orientation.Horizontal)
        self.tempo.setRange(40, 200)
        self.tempo.setFixedWidth(110)
        self.tempo_label = QLabel("72")
        self.tempo_label.setMinimumWidth(28)
        row.addWidget(self.tempo)
        row.addWidget(self.tempo_label)
        row.addSpacing(8)
        row.addWidget(QLabel("变调"))
        self.transpose = QSpinBox()
        self.transpose.setRange(-6, 6)
        self.transpose.setFixedWidth(58)
        row.addWidget(self.transpose)
        row.addSpacing(8)
        row.addWidget(QLabel("音量"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(85)
        self.volume.setFixedWidth(80)
        row.addWidget(self.volume)
        outer.addWidget(transport)

        self.hint = QLabel("空格 播放/暂停    单击乐谱定位    Shift+单击 设 A    Ctrl+单击 设 B    Ctrl+滚轮 缩放    本地播放，不联网")
        self.hint.setObjectName("hint")
        outer.addWidget(self.hint)
        self.setStyleSheet(STYLES)
        self.setFont(QFont("Microsoft YaHei UI", 9))
        self._icon()

    def _caption(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("caption")
        return label

    def _icon(self) -> None:
        image = QImage(64, 64, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#d0121a"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 60, 60)
        painter.setPen(QPenWhite())
        painter.setBrush(QColor("white"))
        painter.drawEllipse(24, 36, 16, 12)
        painter.drawLine(38, 18, 38, 42)
        painter.end()
        from PySide6.QtGui import QIcon, QPixmap
        self.setWindowIcon(QIcon(QPixmap.fromImage(image)))

    def _bind(self) -> None:
        self.open_button.clicked.connect(self._open)
        self.play_button.clicked.connect(self.engine.toggle)
        self.stop_button.clicked.connect(self.engine.stop)
        self.canvas.seekRequested.connect(self._seek)
        self.zoom.valueChanged.connect(lambda value: self.canvas.set_zoom(value / 100))
        self.tempo.valueChanged.connect(self._tempo_changed)
        self.transpose.valueChanged.connect(self.engine.set_transpose)
        self.volume.valueChanged.connect(lambda value: self.engine.set_volume(value / 100))
        self.progress.sliderPressed.connect(self._begin_scrub)
        self.progress.sliderReleased.connect(self._end_scrub)
        self.melody.toggled.connect(lambda checked: self.engine.set_options(melody=checked))
        self.metronome.toggled.connect(lambda checked: self.engine.set_options(metronome=checked))
        self.count_in.toggled.connect(lambda checked: self.engine.set_options(count_in=checked))
        self.rhythm.currentIndexChanged.connect(self._rhythm_changed)
        self.loop_a.clicked.connect(lambda: self._mark_loop(True))
        self.loop_b.clicked.connect(lambda: self._mark_loop(False))
        self.loop_clear.clicked.connect(self.engine.clear_loop)
        for key, slot in (
            (Qt.Key.Key_Space, self.engine.toggle),
            (Qt.Key.Key_Home, self._restart),
            (Qt.Key.Key_Escape, self.engine.clear_loop),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(slot)
        for button in (self.play_button, self.stop_button, self.loop_a, self.loop_b, self.loop_clear, self.open_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _show_score(self) -> None:
        score = self.engine.score
        self.canvas.set_score(score)
        self.header_song.setText(f"{score.title}  ·  {score.subtitle}" if score.subtitle else score.title)
        self.setWindowTitle(f"{score.title} - 吉他谱播放器")
        self.tempo.blockSignals(True)
        self.tempo.setValue(score.tempo)
        self.tempo.blockSignals(False)
        self.tempo_label.setText(str(score.tempo))
        self.transpose.blockSignals(True)
        self.transpose.setValue(self.engine.transpose)
        self.transpose.blockSignals(False)
        sounded = score.key if self.engine.transpose == 0 else transpose_key(score.key, self.engine.transpose)
        self.info_label.setText(
            f"曲名：{score.title}\n"
            f"副标题：{score.subtitle or '—'}\n"
            f"演唱：{score.artist or '—'}\n"
            f"调号：1 = {score.key}\n"
            f"拍号：{score.beats_per_measure}/{score.beat_unit}\n"
            f"小节：{len(score.measures)}\n"
            f"试听调：{sounded}"
        )
        self._view_key = None

    def _tick(self) -> None:
        if not self.audio.ok:
            self.engine.render(1323)
        state = self.engine.snapshot()
        score = self.engine.score
        view_key = (round(state.beat, 3), state.playing, state.tempo, state.transpose, state.loop_a, state.loop_b)
        if view_key != self._view_key:
            self.canvas.set_view(state.beat, state.tempo, state.transpose, state.loop_a, state.loop_b)
            self._view_key = view_key
        self.play_button.setText("暂停" if state.playing else "播放")
        self.tempo_label.setText(str(state.tempo))
        total = score.total_beats
        if not self._scrubbing and total > 0:
            shown = 0 if state.beat < 0 else min(total, state.beat)
            self.progress.setValue(int(shown / total * 10000))
        self.time_label.setText(f"{self._clock(state.beat, state.tempo)} / {self._clock(total, state.tempo)}")
        beats = score.beats_per_measure
        if state.beat < 0:
            where = "预备拍"
        else:
            measure = min(len(score.measures), int(state.beat // beats) + 1)
            beat = int(state.beat % beats) + 1
            where = f"第 {measure} 小节 · 第 {beat} 拍"
        if state.chord:
            where += f"  ·  {state.chord}"
        self.where_label.setText(where)
        self.chord_card.set_chord(state.chord)
        if state.loop_a is None:
            self.loop_label.setText("未设置")
        else:
            end = state.loop_b if state.loop_b is not None else len(score.measures) - 1
            lo, hi = sorted((state.loop_a, end))
            self.loop_label.setText(f"第 {lo + 1}–{hi + 1} 小节循环")
        self.fretboard.set_state(score.tuning, lookup_chord(state.chord) if state.chord else None, [(note.string, note.fret, note.role) for note in state.active])
        if self.follow.isChecked() and state.playing and not self.scroll.verticalScrollBar().isSliderDown():
            anchor = self.canvas.cursor_anchor()
            self.scroll.ensureVisible(int(anchor.x()), int(anchor.y()), 70, 110)
        if self.audio.error and not state.playing:
            self.hint.setText(self.audio.error + "    光标仍会跟着走")

    def _tempo_changed(self, value: int) -> None:
        self.engine.set_tempo(value)
        self.tempo_label.setText(str(value))

    def _rhythm_changed(self) -> None:
        self.engine.set_options(rhythm=self.rhythm.currentData())

    def _begin_scrub(self) -> None:
        self._scrubbing = True

    def _end_scrub(self) -> None:
        total = self.engine.score.total_beats
        self.engine.seek(self.progress.value() / 10000 * total)
        self._scrubbing = False

    def _seek(self, beat: float, measure: int, mods: int) -> None:
        shift = int(Qt.KeyboardModifier.ShiftModifier.value)
        control = int(Qt.KeyboardModifier.ControlModifier.value)
        if mods & shift:
            self.engine.set_loop(measure, self.engine.snapshot().loop_b)
        elif mods & control:
            start = self.engine.snapshot().loop_a
            self.engine.set_loop(measure if start is None else start, measure)
        else:
            self.engine.seek(beat)

    def _mark_loop(self, is_a: bool) -> None:
        state = self.engine.snapshot()
        beats = self.engine.score.beats_per_measure
        measure = 0 if state.beat < 0 else min(len(self.engine.score.measures) - 1, int(state.beat // beats))
        if is_a:
            self.engine.set_loop(measure, state.loop_b)
        else:
            self.engine.set_loop(measure if state.loop_a is None else state.loop_a, measure)

    def _restart(self) -> None:
        playing = self.engine.snapshot().playing
        self.engine.seek(0)
        if playing:
            self.engine.play()

    def _open(self) -> None:
        SCORES_DIR.mkdir(parents=True, exist_ok=True)
        path, _selected = QFileDialog.getOpenFileName(self, "打开乐谱", str(SCORES_DIR), "吉他谱 (*.json)")
        if path:
            self._load_path(path)

    def _load_path(self, path: str) -> None:
        try:
            score = load_score(path)
        except ScoreError as exc:
            QMessageBox.warning(self, "无法打开", str(exc))
            return
        self.engine.set_score(score)
        self.engine.set_transpose(0)
        self._show_score()

    def _clock(self, beat: float, tempo: int) -> str:
        seconds = max(0.0, beat) * 60.0 / max(1, tempo)
        return f"{int(seconds // 60)}:{int(seconds % 60):02d}"

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Wheel and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            step = 10 if event.angleDelta().y() > 0 else -10
            self.zoom.setValue(self.zoom.value() + step)
            return True
        return super().eventFilter(watched, event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls:
            self._load_path(urls[0].toLocalFile())

    def closeEvent(self, event) -> None:
        self.audio.stop()
        super().closeEvent(event)


def QPenWhite():
    from PySide6.QtGui import QPen
    return QPen(QColor("white"), 3)


STYLES = """
QWidget#root { background: #e4dece; color: #1c1c1c; }
QFrame#header { background: #1b1b1b; }
QLabel#appTitle { color: #f4efe6; font-size: 16px; font-weight: 700; }
QLabel#songTitle, QLabel#headerLabel { color: #d9d0c3; }
QScrollArea#sideScroll, QWidget#side { background: #f7f4ee; border: none; border-left: 1px solid #e3d8c4; }
QFrame#transport { background: #f7f4ee; border-top: 1px solid #e3d8c4; }
QLabel#caption { color: #8a8174; font-size: 12px; font-weight: 700; }
QLabel#info { color: #2a2a2a; line-height: 140%; }
QLabel#where { color: #d0121a; font-weight: 700; }
QLabel#muted, QLabel#hint { color: #6f695e; padding: 4px 12px 6px 12px; background: #f7f4ee; }
QPushButton {
    background: white; border: 1px solid #ddd4c6; border-radius: 6px; padding: 6px 10px;
}
QPushButton:hover { border-color: #d0121a; }
QPushButton#play {
    background: #d0121a; color: white; border: none; padding: 7px 16px; font-weight: 700;
}
QPushButton#play:hover { background: #b10e16; }
QPushButton#openButton { background: #d0121a; color: white; border: none; font-weight: 700; }
QComboBox, QSpinBox { background: white; border: 1px solid #ddd4c6; border-radius: 4px; padding: 3px 6px; }
QSlider::groove:horizontal { height: 4px; background: #ddd4c6; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -6px 0; border-radius: 7px; background: #d0121a; }
QScrollArea { background: #e4dece; }
"""
