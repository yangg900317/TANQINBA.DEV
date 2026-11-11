from __future__ import annotations

import numpy as np

SAMPLE_RATE = 44100


def midi_to_freq(midi: float) -> float:
    return 440.0 * (2.0 ** ((float(midi) - 69.0) / 12.0))


class Voice:
    def __init__(self, midi: int, velocity: float, duration: float, kind: str = "melody", freq: float | None = None):
        self.midi = midi
        self.vel = float(velocity)
        self.duration = duration
        self.kind = kind
        self.freq = float(freq if freq is not None else midi_to_freq(midi))
        self.sr = SAMPLE_RATE
        self.age = 0
        self.delay = 0
        seed = int(self.freq * 10) + (0 if kind == "melody" else 19)
        rng = np.random.RandomState(seed)
        self.phase = rng.uniform(0, 2 * np.pi, 6).astype(np.float32)
        self.noise = rng.uniform(-1, 1, 700).astype(np.float32)
        amps = np.array([1.0, 0.48, 0.26, 0.14, 0.08, 0.045], dtype=np.float32)
        if midi < 52:
            amps[3:] *= 0.35
        self.amps = amps

    def render(self, frames: int) -> np.ndarray:
        out = np.zeros(frames, dtype=np.float32)
        if self.delay >= frames:
            self.delay -= frames
            return out
        lead = self.delay
        self.delay = 0
        body = self._body(frames - lead)
        out[lead:] = body
        return out

    def _body(self, frames: int) -> np.ndarray:
        if frames <= 0:
            return np.zeros(0, dtype=np.float32)
        start = self.age
        t = (np.arange(frames, dtype=np.float32) + start) / self.sr
        self.age += frames
        if self.kind == "tick":
            envelope = np.exp(-t * 48.0)
            return (np.sin(2 * np.pi * self.freq * t) * envelope * self.vel).astype(np.float32)
        signal = np.zeros(frames, dtype=np.float32)
        decay_scale = 1.55 if self.kind == "rhythm" else 1.0
        for harmonic in range(1, 7):
            stretched = harmonic * np.sqrt(1.0 + 0.00018 * harmonic * harmonic)
            decay = (1.8 + harmonic * 1.05) * decay_scale
            signal += self.amps[harmonic - 1] * np.sin(
                2 * np.pi * self.freq * stretched * t + self.phase[harmonic - 1]
            ) * np.exp(-t * decay)
        if start < self.noise.size:
            take = min(frames, self.noise.size - start)
            attack = np.exp(-t[:take] * 52.0)
            signal[:take] += self.noise[start:start + take] * attack * 0.28
        return (signal * self.vel * 0.42).astype(np.float32)

    @property
    def finished(self) -> bool:
        limit = 0.18 if self.kind == "tick" else self.duration + 1.15
        return self.age > limit * self.sr and self.delay <= 0


def mix(voices: list[Voice], frames: int, volume: float) -> np.ndarray:
    mixed = np.zeros(frames, dtype=np.float32)
    for voice in voices:
        mixed += voice.render(frames)
    if volume <= 0 or not voices:
        return np.zeros(frames, dtype=np.float32)
    return (np.tanh(mixed * 1.25) * float(volume)).astype(np.float32)
