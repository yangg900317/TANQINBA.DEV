from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from app.chords import lookup_chord, pick_strings
from app.engine import Engine
from app.library import default_score
from app.model import dump_score, load_score, spell, transpose_key
from app.synth import midi_to_freq


class PlayerTests(unittest.TestCase):
    def test_score_shape(self) -> None:
        score = default_score()
        self.assertEqual(len(score.measures), 12)
        self.assertEqual(score.total_beats, 48)
        self.assertEqual(score.measures[0].label, "前奏")
        self.assertEqual(score.measures[4].notes[0].lyric, "把")
        self.assertEqual(score.tuning[0], 64)

    def test_spelling_respects_key_signature(self) -> None:
        self.assertEqual(spell(66, "G").accidental, "")
        self.assertEqual(spell(66, "G").step, 3)
        self.assertEqual(spell(65, "G").accidental, "n")
        self.assertEqual(spell(69, "G").accidental, "")
        self.assertEqual(spell(68, "G").accidental, "#")
        self.assertEqual(transpose_key("G", 2), "A")
        self.assertEqual(transpose_key("G", -1), "F#")

    def test_open_g_and_bass(self) -> None:
        shape = lookup_chord("G")
        self.assertIsNotNone(shape)
        assert shape is not None
        self.assertEqual(shape.frets, (3, 2, 0, 0, 0, 3))
        self.assertEqual(pick_strings(shape, "bass"), [(6, 3)])
        self.assertIsNotNone(lookup_chord("F#m"))

    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "song.json"
            dump_score(default_score(), path)
            loaded = load_score(path)
        self.assertEqual(loaded.title, "练习曲一")
        self.assertEqual(len(loaded.measures[8].notes), 4)

    def test_playback_pitch_and_clock(self) -> None:
        engine = Engine(default_score())
        engine.set_options(metronome=False, melody=True, rhythm="none", count_in=False)
        engine.play()
        chunks = [engine.render(1024) for _ in range(8)]
        audio = np.concatenate(chunks)
        self.assertGreater(float(np.max(np.abs(audio))), 0.05)
        window = audio * np.hanning(len(audio))
        spectrum = np.abs(np.fft.rfft(window))
        freqs = np.fft.rfftfreq(len(audio), 1 / 44100)
        peak = float(freqs[int(np.argmax(spectrum[1:]) + 1)])
        ratio = peak / midi_to_freq(59)
        self.assertLess(abs(ratio - round(ratio)), 0.045)
        self.assertGreater(engine.snapshot().beat, 0.05)

    def test_transpose_changes_frequency(self) -> None:
        engine = Engine(default_score())
        engine.set_options(metronome=False, rhythm="none", count_in=False)
        engine.set_transpose(2)
        engine.play()
        engine.render(2048)
        self.assertTrue(engine.voices)
        self.assertAlmostEqual(engine.voices[0].freq, midi_to_freq(61), delta=0.05)

    def test_loop_wraps(self) -> None:
        engine = Engine(default_score())
        engine.set_options(metronome=False, count_in=False)
        engine.seek(3.95)
        engine.set_loop(0, 0)
        engine.play()
        engine.render(5000)
        self.assertLess(engine.beat, 0.5)

    def test_rhythm_events(self) -> None:
        engine = Engine(default_score())
        engine.set_options(melody=False, rhythm="ballad", metronome=False)
        beats = [event.beat for event in engine.events if event.beat < 4]
        self.assertGreaterEqual(len(beats), 4)
        engine.play()
        audio = engine.render(4096)
        self.assertGreater(float(np.max(np.abs(audio))), 0.02)


if __name__ == "__main__":
    unittest.main()
