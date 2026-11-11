from __future__ import annotations

from pathlib import Path

from app.model import DEFAULT_SCORE_PATH, Score, dump_score, score_from_dict


def _note(beat: float, string: int, fret: int, duration: float = 0.5, lyric: str = "") -> dict:
    payload = {"beat": beat, "string": string, "fret": fret, "duration": duration}
    if lyric:
        payload["lyric"] = lyric
    return payload


def _eighths(pairs: list[tuple[int, int]]) -> list[dict]:
    return [_note(index * 0.5, string, fret) for index, (string, fret) in enumerate(pairs)]


def _quarters(items: list[tuple[int, int, str]]) -> list[dict]:
    return [_note(index, string, fret, 1, lyric) for index, (string, fret, lyric) in enumerate(items)]


def _measure(chord: str, notes: list[dict], label: str = "") -> dict:
    payload = {"chords": [{"beat": 0, "name": chord}], "notes": notes}
    if label:
        payload["label"] = label
    return payload


DEFAULT_DICT = {
    "title": "练习曲一",
    "subtitle": "G调吉他弹唱谱",
    "artist": "原创",
    "key": "G",
    "beatsPerMeasure": 4,
    "beatUnit": 4,
    "tempo": 72,
    "tuningMidi": [64, 59, 55, 50, 45, 40],
    "measures": [
        _measure("G", _eighths([(2, 0), (1, 3), (2, 0), (1, 3), (2, 3), (1, 3), (2, 0), (1, 0)]), "前奏"),
        _measure("Em", _eighths([(3, 0), (2, 0), (1, 0), (2, 0), (3, 0), (1, 0), (2, 0), (1, 3)])),
        _measure("C", _eighths([(3, 0), (2, 1), (1, 0), (2, 1), (3, 0), (1, 3), (2, 1), (1, 0)])),
        _measure("D", _eighths([(3, 2), (2, 3), (1, 2), (2, 3), (3, 2), (1, 2), (2, 3), (1, 5)])),
        _measure("G", _quarters([(2, 3, "把"), (1, 0, "弦"), (1, 3, "调"), (1, 5, "准")]), "主歌"),
        _measure("Em", _quarters([(1, 3, "再"), (1, 0, "轻"), (2, 3, "轻"), (2, 0, "弹")])),
        _measure("C", _quarters([(1, 0, "从"), (1, 3, "这"), (1, 5, "一"), (1, 3, "格")])),
        _measure("D", _quarters([(1, 2, "慢"), (2, 3, "慢"), (2, 0, "走"), (1, 2, "过")])),
        _measure(
            "G",
            [
                _note(0, 1, 3, 1.5, "一"),
                _note(1.5, 2, 0, 0.5, "格"),
                _note(2, 1, 0, 1, "一"),
                _note(3, 2, 3, 1, "音"),
            ],
            "副歌",
        ),
        _measure("Em", _quarters([(2, 0, "慢"), (3, 0, "慢"), (2, 0, "就"), (1, 0, "会")])),
        _measure("C", _quarters([(1, 0, "听"), (1, 3, "见"), (2, 1, "旋"), (1, 0, "律")])),
        _measure("G", _quarters([(1, 0, "落"), (2, 3, "在"), (1, 3, "弦"), (1, 3, "上")])),
    ],
}


def default_score() -> Score:
    return score_from_dict(DEFAULT_DICT)


def write_default(path: Path = DEFAULT_SCORE_PATH) -> Path:
    dump_score(default_score(), path)
    return path
