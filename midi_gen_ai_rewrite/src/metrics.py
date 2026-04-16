from __future__ import annotations

from typing import Sequence

import numpy as np
import pretty_midi


def token_repeat_rate(tokens: Sequence[int], n: int = 4) -> float:
    tokens = list(tokens)
    if n <= 0 or len(tokens) <= n:
        return 0.0
    ngrams = [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]
    if not ngrams:
        return 0.0
    return float(1.0 - (len(set(ngrams)) / len(ngrams)))


def token_unique_ratio(tokens: Sequence[int]) -> float:
    tokens = list(tokens)
    if not tokens:
        return 0.0
    return float(len(set(tokens)) / len(tokens))


def token_entropy(tokens: Sequence[int]) -> float:
    tokens = np.asarray(list(tokens), dtype=np.int64)
    if tokens.size == 0:
        return 0.0
    counts = np.bincount(tokens)
    counts = counts[counts > 0]
    probs = counts / counts.sum()
    return float(-(probs * np.log2(probs)).sum())


def summarize_midi(midi: pretty_midi.PrettyMIDI, grid_size: int = 200) -> dict:
    notes = [note for inst in midi.instruments if not inst.is_drum for note in inst.notes]
    if not notes:
        return {
            "note_count": 0,
            "duration_seconds": 0.0,
            "note_rate_per_sec": 0.0,
            "mean_pitch": 0.0,
            "pitch_std": 0.0,
            "pitch_range": 0,
            "mean_duration": 0.0,
            "polyphony_mean": 0.0,
            "polyphony_std": 0.0,
            "polyphony_max": 0,
        }

    pitches = np.asarray([note.pitch for note in notes], dtype=np.float32)
    durations = np.asarray([max(0.0, note.end - note.start) for note in notes], dtype=np.float32)
    starts = np.asarray([note.start for note in notes], dtype=np.float32)
    ends = np.asarray([note.end for note in notes], dtype=np.float32)
    duration_seconds = float(max(midi.get_end_time(), float(ends.max(initial=0.0))))
    duration_seconds = max(duration_seconds, 1e-6)
    note_count = len(notes)

    grid_count = int(np.clip(grid_size, 20, 500))
    grid = np.linspace(0.0, duration_seconds, grid_count, dtype=np.float32)
    active = (starts[:, None] <= grid[None, :]) & (ends[:, None] > grid[None, :])
    polyphony = active.sum(axis=0).astype(np.float32)

    return {
        "note_count": int(note_count),
        "duration_seconds": duration_seconds,
        "note_rate_per_sec": float(note_count / duration_seconds),
        "mean_pitch": float(pitches.mean()),
        "pitch_std": float(pitches.std()),
        "pitch_range": int(pitches.max() - pitches.min()),
        "mean_duration": float(durations.mean()),
        "polyphony_mean": float(polyphony.mean()),
        "polyphony_std": float(polyphony.std()),
        "polyphony_max": int(polyphony.max()),
    }
