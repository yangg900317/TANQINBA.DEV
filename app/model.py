from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
SCORES_DIR = APP_ROOT / "scores"
DEFAULT_SCORE_PATH = SCORES_DIR / "练习曲一.json"

PC_NAME = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
SHARP_KEYS = ["C", "G", "D", "A", "E", "B", "F#", "C#"]
FLAT_KEYS = ["C", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"]
SHARP_LETTERS = ["F", "C", "G", "D", "A", "E", "B"]
FLAT_LETTERS = ["B", "E", "A", "D", "G", "C", "F"]
LETTER_INDEX = {letter: index for index, letter in enumerate("CDEFGAB")}

SHARP_SPELLING = [
    ("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0),
    ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0),
]
FLAT_SPELLING = [
    ("C", 0), ("D", -1), ("D", 0), ("E", -1), ("E", 0), ("F", 0),
    ("G", -1), ("G", 0), ("A", -1), ("A", 0), ("B", -1), ("B", 0),
]


class ScoreError(ValueError):
    pass


@dataclass
class Note:
    beat: float
    string: int
    fret: int
    duration: float
    lyric: str = ""


@dataclass
class ChordSymbol:
    beat: float
    name: str


@dataclass
class Measure:
    notes: list[Note] = field(default_factory=list)
    chords: list[ChordSymbol] = field(default_factory=list)
    label: str = ""


@dataclass
class Score:
    title: str
    subtitle: str
    artist: str
    key: str
    beats_per_measure: int
    beat_unit: int
    tempo: int
    tuning: list[int]
    measures: list[Measure]

    @property
    def total_beats(self) -> float:
        return len(self.measures) * self.beats_per_measure


@dataclass(frozen=True)
class Spelling:
    letter: str
    octave: int
    step: int
    accidental: str


def normalize_key(value: str) -> str:
    key = value.strip().replace("调", "").replace(" ", "")
    aliases = {"Gb": "F#", "Db": "C#"}
    if key in SHARP_KEYS or key in FLAT_KEYS:
        return key
    if key in aliases and aliases[key] in SHARP_KEYS:
        return aliases[key]
    raise ScoreError(f"不认识的调号：{value}")


def key_alters(key: str) -> dict[str, int]:
    if key in SHARP_KEYS:
        count = SHARP_KEYS.index(key)
        return {SHARP_LETTERS[index]: 1 for index in range(count)}
    if key in FLAT_KEYS:
        count = FLAT_KEYS.index(key)
        return {FLAT_LETTERS[index]: -1 for index in range(count)}
    return {}


def spell(midi: int, key: str) -> Spelling:
    pitch = midi % 12
    use_flats = key in FLAT_KEYS and key != "C"
    letter, alter = (FLAT_SPELLING if use_flats else SHARP_SPELLING)[pitch]
    octave = (midi - alter) // 12 - 1
    step = (octave - 4) * 7 + LETTER_INDEX[letter]
    expected = key_alters(key).get(letter, 0)
    if alter == expected:
        accidental = ""
    elif alter == 0:
        accidental = "n"
    elif alter > 0:
        accidental = "#"
    else:
        accidental = "b"
    return Spelling(letter, octave, step, accidental)


def transpose_key(key: str, semitones: int) -> str:
    names = FLAT_KEYS if key in FLAT_KEYS and key != "C" else SHARP_KEYS
    spelling = FLAT_SPELLING if names is FLAT_KEYS else SHARP_SPELLING
    tonic = next(index for index, (letter, alter) in enumerate(spelling) if letter == key[0] and (alter == 1) == ("#" in key) and (alter == -1) == ("b" in key))
    moved = (tonic + semitones) % 12
    letter, alter = spelling[moved]
    if alter == 1:
        return letter + "#"
    if alter == -1:
        return letter + "b"
    return letter


def note_name(midi: int) -> str:
    return PC_NAME[midi % 12]


def load_score(path: str | Path) -> Score:
    import json

    file_path = Path(path)
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScoreError(f"找不到乐谱：{file_path}") from exc
    except json.JSONDecodeError as exc:
        raise ScoreError(f"乐谱不是合法的 JSON：{exc}") from exc
    return score_from_dict(payload)


def score_from_dict(payload: dict) -> Score:
    try:
        title = str(payload.get("title") or "未命名")
        subtitle = str(payload.get("subtitle") or "")
        artist = str(payload.get("artist") or "")
        key = normalize_key(str(payload.get("key") or "C"))
        beats = int(payload.get("beatsPerMeasure") or 4)
        unit = int(payload.get("beatUnit") or 4)
        tempo = int(payload.get("tempo") or 72)
        tuning = list(payload.get("tuningMidi") or [64, 59, 55, 50, 45, 40])
        raw_measures = payload["measures"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ScoreError(f"乐谱字段不完整：{exc}") from exc

    if beats <= 0 or unit not in (1, 2, 4, 8, 16):
        raise ScoreError("拍号不正确")
    if not 20 <= tempo <= 280:
        raise ScoreError("速度需要在 20 到 280 之间")
    if len(tuning) != 6 or any(not isinstance(item, int) for item in tuning):
        raise ScoreError("tuningMidi 需要 6 个音高，从 1 弦到 6 弦")
    if not raw_measures:
        raise ScoreError("乐谱至少要有一个小节")

    measures: list[Measure] = []
    for index, raw in enumerate(raw_measures, start=1):
        notes: list[Note] = []
        for item in raw.get("notes") or []:
            try:
                note = Note(
                    beat=float(item["beat"]),
                    string=int(item["string"]),
                    fret=int(item["fret"]),
                    duration=float(item.get("duration") or 1),
                    lyric=str(item.get("lyric") or ""),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ScoreError(f"第 {index} 小节有无法识别的音符") from exc
            if not 1 <= note.string <= 6 or not 0 <= note.fret <= 24:
                raise ScoreError(f"第 {index} 小节的弦号或品位超出范围")
            if note.duration <= 0 or note.beat < 0 or note.beat >= beats:
                raise ScoreError(f"第 {index} 小节的拍位或时值不正确")
            notes.append(note)
        chords: list[ChordSymbol] = []
        for item in raw.get("chords") or []:
            try:
                chord = ChordSymbol(beat=float(item.get("beat") or 0), name=str(item["name"]).strip())
            except (KeyError, TypeError, ValueError) as exc:
                raise ScoreError(f"第 {index} 小节有无法识别的和弦") from exc
            if not chord.name or chord.beat < 0 or chord.beat >= beats:
                raise ScoreError(f"第 {index} 小节的和弦位置不正确")
            chords.append(chord)
        notes.sort(key=lambda note: (note.beat, note.string))
        chords.sort(key=lambda chord: chord.beat)
        measures.append(Measure(notes=notes, chords=chords, label=str(raw.get("label") or "")))
    return Score(title, subtitle, artist, key, beats, unit, tempo, [int(item) for item in tuning], measures)


def dump_score(score: Score, path: str | Path) -> None:
    import json

    payload = {
        "title": score.title,
        "subtitle": score.subtitle,
        "artist": score.artist,
        "key": score.key,
        "beatsPerMeasure": score.beats_per_measure,
        "beatUnit": score.beat_unit,
        "tempo": score.tempo,
        "tuningMidi": score.tuning,
        "measures": [
            {
                "label": measure.label,
                "chords": [{"beat": chord.beat, "name": chord.name} for chord in measure.chords],
                "notes": [
                    {
                        "beat": note.beat,
                        "string": note.string,
                        "fret": note.fret,
                        "duration": note.duration,
                        "lyric": note.lyric,
                    }
                    for note in measure.notes
                ],
            }
            for measure in score.measures
        ],
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
