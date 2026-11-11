from __future__ import annotations

import bisect
import math
import threading
from dataclasses import dataclass, field

import numpy as np

from app.chords import lookup_chord, pattern_hits, pick_strings
from app.model import Score
from app.synth import SAMPLE_RATE, Voice, mix


@dataclass
class Event:
    beat: float
    string: int
    fret: int
    duration: float
    velocity: float
    delay: float
    role: str


@dataclass
class ActiveNote:
    string: int
    fret: int
    until: float
    role: str


@dataclass
class ViewState:
    beat: float
    playing: bool
    tempo: int
    transpose: int
    loop_a: int | None
    loop_b: int | None
    active: list[ActiveNote] = field(default_factory=list)
    chord: str = ""


class Engine:
    def __init__(self, score: Score):
        self.score = score
        self.tempo = score.tempo
        self.transpose = 0
        self.volume = 0.85
        self.metronome = False
        self.count_in = False
        self.melody = True
        self.rhythm = "none"
        self.loop_a: int | None = None
        self.loop_b: int | None = None
        self.beat = 0.0
        self.playing = False
        self.events: list[Event] = []
        self.voices: list[Voice] = []
        self.active: list[ActiveNote] = []
        self._index = 0
        self._arm_click = False
        self._lock = threading.Lock()
        self._error = ""
        self.rebuild()

    def rebuild(self) -> None:
        with self._lock:
            self.events = self._build_events()
            self._index = bisect.bisect_left([event.beat for event in self.events], self.beat - 1e-6)

    def set_score(self, score: Score) -> None:
        with self._lock:
            self.score = score
            self.tempo = score.tempo
            self.beat = 0.0
            self.playing = False
            self.loop_a = None
            self.loop_b = None
            self.voices.clear()
            self.active.clear()
            self.events = self._build_events()
            self._index = 0

    def set_tempo(self, tempo: int) -> None:
        with self._lock:
            self.tempo = int(max(40, min(200, tempo)))

    def set_transpose(self, semitones: int) -> None:
        with self._lock:
            self.transpose = int(max(-6, min(6, semitones)))

    def set_volume(self, volume: float) -> None:
        with self._lock:
            self.volume = float(max(0.0, min(1.0, volume)))

    def set_options(self, **options) -> None:
        rebuild = False
        with self._lock:
            for key, value in options.items():
                setattr(self, key, value)
                if key in ("melody", "rhythm"):
                    rebuild = True
            if rebuild:
                self.events = self._build_events()
                self._index = bisect.bisect_left([event.beat for event in self.events], self.beat - 1e-6)
                self.voices.clear()

    def set_loop(self, start: int | None, end: int | None = None) -> None:
        with self._lock:
            count = len(self.score.measures)
            self.loop_a = None if start is None else max(0, min(count - 1, start))
            if end is None:
                self.loop_b = self.loop_b if start is not None else None
            else:
                self.loop_b = max(0, min(count - 1, end))
            if self.loop_a is None:
                self.loop_b = None

    def clear_loop(self) -> None:
        self.set_loop(None, None)

    def seek(self, beat: float) -> None:
        with self._lock:
            self.beat = float(max(0.0, min(self.score.total_beats, beat)))
            self._index = bisect.bisect_left([event.beat for event in self.events], self.beat - 1e-6)
            self.voices.clear()
            self.active.clear()
            self._arm_click = False

    def play(self) -> None:
        with self._lock:
            total = self.score.total_beats
            if self.beat >= total - 0.01:
                self.beat = 0.0
            if self.beat <= 0 and self.count_in:
                self.beat = -float(self.score.beats_per_measure)
            self.playing = True
            self._index = bisect.bisect_left([event.beat for event in self.events], self.beat - 1e-6)
            self._arm_click = self.metronome or self.beat < 0

    def pause(self) -> None:
        with self._lock:
            self.playing = False
            self.voices.clear()

    def stop(self) -> None:
        with self._lock:
            self.playing = False
            self.beat = 0.0
            self._index = 0
            self.voices.clear()
            self.active.clear()

    def toggle(self) -> None:
        if self.playing:
            self.pause()
        else:
            self.play()

    def render(self, frames: int) -> np.ndarray:
        try:
            with self._lock:
                return self._render_locked(frames)
        except Exception as exc:
            if not self._error:
                self._error = str(exc)
            return np.zeros(frames, dtype=np.float32)

    def snapshot(self) -> ViewState:
        with self._lock:
            lag = (0.06 * self.tempo / 60.0) if self.playing else 0.0
            heard = self.beat - lag
            if self.beat >= 0:
                heard = max(0.0, heard)
            return ViewState(
                beat=heard,
                playing=self.playing,
                tempo=self.tempo,
                transpose=self.transpose,
                loop_a=self.loop_a,
                loop_b=self.loop_b,
                active=list(self.active),
                chord=self._chord_at(max(0.0, heard)),
            )

    def _render_locked(self, frames: int) -> np.ndarray:
        if not self.playing:
            return np.zeros(frames, dtype=np.float32)
        bpm = self.score.beats_per_measure
        delta = frames / SAMPLE_RATE * self.tempo / 60.0
        start = self.beat
        end = start + delta
        bounds = self._loop_bounds()
        wrapped = False
        if bounds and start >= 0 and end >= bounds[1]:
            end = bounds[0]
            wrapped = True
            self.voices.clear()
            self.active.clear()
            self._index = bisect.bisect_left([event.beat for event in self.events], end - 1e-6)
        total = self.score.total_beats
        if bounds is None and end >= total:
            self.beat = total
            self.playing = False
            self.voices.clear()
            self.active.clear()
            return np.zeros(frames, dtype=np.float32)

        if self._arm_click and self._near_integer(start):
            self._add_click(int(round(start)), bpm)
        self._arm_click = False
        click = math.floor(start) + 1
        while click <= end + 1e-9:
            if self._want_click(click, start):
                self._add_click(click, bpm)
            click += 1

        while self._index < len(self.events) and self.events[self._index].beat <= end + 1e-9:
            event = self.events[self._index]
            if wrapped or event.beat >= start - 1e-6:
                self._trigger(event)
            self._index += 1

        self.beat = end
        audio = mix(self.voices, frames, self.volume)
        self.voices = [voice for voice in self.voices if not voice.finished]
        self.active = [note for note in self.active if note.until > self.beat]
        return audio

    def _build_events(self) -> list[Event]:
        events: list[Event] = []
        bpm = self.score.beats_per_measure
        for measure_index, measure in enumerate(self.score.measures):
            origin = measure_index * bpm
            if self.melody:
                for note in measure.notes:
                    events.append(Event(origin + note.beat, note.string, note.fret, note.duration, 0.92, 0.0, "melody"))
            if self.rhythm != "none":
                for hit_beat, kind, velocity in pattern_hits(self.rhythm, bpm):
                    shape = lookup_chord(self._chord_at(origin + hit_beat))
                    if shape is None:
                        continue
                    chosen = pick_strings(shape, kind)
                    for order, (string, fret) in enumerate(chosen):
                        events.append(Event(
                            origin + hit_beat, string, fret, 0.45, velocity * 0.72,
                            order * 0.012, "rhythm",
                        ))
        events.sort(key=lambda event: (event.beat, event.delay, event.string))
        return events

    def _trigger(self, event: Event) -> None:
        midi = self.score.tuning[event.string - 1] + event.fret + self.transpose
        midi = max(0, min(127, midi))
        seconds = max(0.05, event.duration * 60.0 / max(1, self.tempo))
        voice = Voice(midi, event.velocity, seconds, "rhythm" if event.role == "rhythm" else "melody")
        voice.delay = int(event.delay * SAMPLE_RATE)
        self.voices.append(voice)
        if len(self.voices) > 32:
            self.voices = self.voices[-32:]
        self.active.append(ActiveNote(event.string, event.fret, event.beat + event.duration, event.role))

    def _add_click(self, beat: int, bpm: int) -> None:
        accent = beat % bpm == 0
        voice = Voice(0, 0.72 if accent else 0.38, 0.12, "tick", freq=1760.0 if accent else 1320.0)
        self.voices.append(voice)

    def _want_click(self, beat: int, start: float) -> bool:
        if self.metronome:
            return True
        return beat < 0 or (beat == 0 and start < 0)

    def _loop_bounds(self) -> tuple[float, float] | None:
        if self.loop_a is None:
            return None
        bpm = self.score.beats_per_measure
        start = self.loop_a
        end = self.loop_b if self.loop_b is not None else len(self.score.measures) - 1
        if end < start:
            start, end = end, start
        return start * bpm, (end + 1) * bpm

    def _chord_at(self, beat: float) -> str:
        found = ""
        origin = 0.0
        bpm = self.score.beats_per_measure
        for measure in self.score.measures:
            for chord in measure.chords:
                if origin + chord.beat <= beat + 1e-6:
                    found = chord.name
            origin += bpm
            if origin > beat + bpm:
                break
        return found

    @staticmethod
    def _near_integer(beat: float) -> bool:
        return abs(beat - round(beat)) < 1e-4
