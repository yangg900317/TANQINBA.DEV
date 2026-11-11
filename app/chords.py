from __future__ import annotations

from dataclasses import dataclass

OPEN_SHAPES: dict[str, tuple[int, ...]] = {
    "C": (-1, 3, 2, 0, 1, 0),
    "Cm": (-1, 3, 5, 5, 4, 3),
    "C7": (-1, 3, 2, 3, 1, 0),
    "Cmaj7": (-1, 3, 2, 0, 0, 0),
    "D": (-1, -1, 0, 2, 3, 2),
    "Dm": (-1, -1, 0, 2, 3, 1),
    "D7": (-1, -1, 0, 2, 1, 2),
    "Dsus4": (-1, -1, 0, 2, 3, 3),
    "E": (0, 2, 2, 1, 0, 0),
    "Em": (0, 2, 2, 0, 0, 0),
    "E7": (0, 2, 0, 1, 0, 0),
    "Em7": (0, 2, 0, 0, 0, 0),
    "Esus4": (0, 2, 2, 2, 0, 0),
    "F": (1, 3, 3, 2, 1, 1),
    "G": (3, 2, 0, 0, 0, 3),
    "G7": (3, 2, 0, 0, 0, 1),
    "A": (-1, 0, 2, 2, 2, 0),
    "Am": (-1, 0, 2, 2, 1, 0),
    "A7": (-1, 0, 2, 0, 2, 0),
    "Am7": (-1, 0, 2, 0, 1, 0),
    "Asus4": (-1, 0, 2, 2, 3, 0),
    "B7": (-1, 2, 1, 2, 0, 2),
    "Dm7": (-1, -1, 0, 2, 1, 1),
}

QUALITY_NAMES = {
    "": "maj",
    "M": "maj",
    "maj": "maj",
    "m": "min",
    "min": "min",
    "-": "min",
    "7": "7",
    "m7": "m7",
    "min7": "m7",
    "maj7": "maj7",
    "M7": "maj7",
    "sus4": "sus4",
    "sus2": "sus2",
    "dim": "dim",
    "aug": "aug",
}

ROOTS = ["C#", "Db", "D#", "Eb", "F#", "Gb", "G#", "Ab", "A#", "Bb", "C", "D", "E", "F", "G", "A", "B"]
ROOT_PC = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


@dataclass(frozen=True)
class ChordShape:
    name: str
    frets: tuple[int, ...]
    base: int
    show_nut: bool

    @property
    def barre(self) -> int | None:
        sounding = [fret for fret in self.frets if fret > 0]
        if not sounding:
            return None
        lowest = min(sounding)
        indexes = [index for index, fret in enumerate(self.frets) if fret == lowest]
        if len(indexes) >= 2 and indexes[-1] - indexes[0] >= 3:
            return lowest
        return None


def _shape(name: str, frets: tuple[int, ...]) -> ChordShape:
    sounding = [fret for fret in frets if fret > 0]
    if not sounding or max(sounding) <= 4:
        return ChordShape(name, frets, 1, True)
    base = min(sounding)
    return ChordShape(name, frets, base, False)


def split_chord(name: str) -> tuple[str, str] | None:
    text = name.strip()
    if "/" in text:
        text = text.split("/", 1)[0]
    for root in ROOTS:
        if text.startswith(root):
            return root, text[len(root):]
    return None


def _e_shape(fret: int, quality: str) -> tuple[int, ...] | None:
    if fret == 0:
        return {"maj": (0, 2, 2, 1, 0, 0), "min": (0, 2, 2, 0, 0, 0), "7": (0, 2, 0, 1, 0, 0)}.get(quality)
    shapes = {
        "maj": (fret, fret + 2, fret + 2, fret + 1, fret, fret),
        "min": (fret, fret + 2, fret + 2, fret, fret, fret),
        "7": (fret, fret + 2, fret, fret + 1, fret, fret),
        "m7": (fret, fret + 2, fret, fret, fret, fret),
    }
    return shapes.get(quality)


def _a_shape(fret: int, quality: str) -> tuple[int, ...] | None:
    if fret == 0:
        return {"maj": (-1, 0, 2, 2, 2, 0), "min": (-1, 0, 2, 2, 1, 0), "7": (-1, 0, 2, 0, 2, 0)}.get(quality)
    shapes = {
        "maj": (-1, fret, fret + 2, fret + 2, fret + 2, fret),
        "min": (-1, fret, fret + 2, fret + 2, fret + 1, fret),
        "7": (-1, fret, fret + 2, fret, fret + 2, fret),
        "m7": (-1, fret, fret + 2, fret, fret + 1, fret),
    }
    return shapes.get(quality)


def lookup_chord(name: str) -> ChordShape | None:
    cleaned = name.strip()
    if cleaned in OPEN_SHAPES:
        return _shape(cleaned, OPEN_SHAPES[cleaned])
    parsed = split_chord(cleaned)
    if parsed is None:
        return None
    root, suffix = parsed
    quality = QUALITY_NAMES.get(suffix)
    if quality is None:
        return None
    pitch = ROOT_PC[root]
    e_fret = (pitch - 4) % 12
    a_fret = (pitch - 9) % 12
    frets = _e_shape(e_fret, quality) if e_fret <= a_fret else _a_shape(a_fret, quality)
    if frets is None:
        frets = _a_shape(a_fret, quality) if e_fret <= a_fret else _e_shape(e_fret, quality)
    if frets is None:
        return None
    return _shape(cleaned, frets)


def sounding(shape: ChordShape) -> list[tuple[int, int]]:
    notes = []
    for index, fret in enumerate(shape.frets):
        if fret >= 0:
            notes.append((6 - index, fret))
    return notes


def pick_strings(shape: ChordShape, kind: str) -> list[tuple[int, int]]:
    notes = sounding(shape)
    if not notes:
        return []
    high_to_low = sorted(notes, key=lambda item: item[0])
    low_to_high = list(reversed(high_to_low))
    if kind == "bass":
        return [low_to_high[0]]
    if kind == "high1":
        return [high_to_low[0]]
    if kind == "high2":
        return [high_to_low[1] if len(high_to_low) > 1 else high_to_low[0]]
    if kind == "high3":
        return [high_to_low[2] if len(high_to_low) > 2 else high_to_low[-1]]
    if kind == "up":
        upper = high_to_low[:-1] if len(high_to_low) >= 4 else high_to_low
        return upper
    return low_to_high


PATTERNS: dict[str, list[tuple[float, str, float]]] = {
    "finger": [
        (0.0, "bass", 0.82), (0.5, "high3", 0.46), (1.0, "high2", 0.52), (1.5, "high1", 0.58),
        (2.0, "high2", 0.5), (2.5, "high3", 0.46), (3.0, "high2", 0.52), (3.5, "high1", 0.56),
    ],
    "ballad": [
        (0.0, "bass", 0.86), (1.0, "down", 0.7), (1.5, "up", 0.5),
        (2.0, "bass", 0.76), (2.5, "up", 0.5), (3.0, "down", 0.72), (3.5, "up", 0.48),
    ],
    "rock": [
        (0.0, "down", 0.9), (1.0, "down", 0.62), (1.5, "up", 0.48),
        (2.0, "down", 0.86), (2.5, "up", 0.5), (3.0, "down", 0.7), (3.5, "up", 0.48),
    ],
    "waltz": [
        (0.0, "bass", 0.86), (1.0, "down", 0.62), (2.0, "up", 0.56),
    ],
}

RHYTHM_LABELS = [
    ("无", "none"),
    ("分解", "finger"),
    ("民谣", "ballad"),
    ("摇滚", "rock"),
    ("华尔兹", "waltz"),
]


def pattern_hits(name: str, beats: int) -> list[tuple[float, str, float]]:
    if name == "none":
        return []
    hits = [hit for hit in PATTERNS.get(name, []) if hit[0] < beats]
    if name == "waltz" and beats >= 4:
        hits.append((3.0, "down", 0.5))
    if hits:
        return hits
    return [(float(beat), "down", 0.7) for beat in range(beats)]
