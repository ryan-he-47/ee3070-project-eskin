from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Sequence

import numpy as np
import pretty_midi


@dataclass(frozen=True)
class TokenizerConfig:
    low_pitch: int = 21
    high_pitch: int = 108
    velocity_bins: int = 32
    time_shift_bins: int = 100
    time_shift_step: float = 0.01


class EventTokenizer:
    def __init__(
        self,
        low_pitch: int = 21,
        high_pitch: int = 108,
        velocity_bins: int = 32,
        time_shift_bins: int = 100,
        time_shift_step: float = 0.01,
    ) -> None:
        if low_pitch >= high_pitch:
            raise ValueError("low_pitch must be < high_pitch")
        if velocity_bins <= 0:
            raise ValueError("velocity_bins must be > 0")
        if time_shift_bins <= 0:
            raise ValueError("time_shift_bins must be > 0")
        if time_shift_step <= 0:
            raise ValueError("time_shift_step must be > 0")

        self.low_pitch = int(low_pitch)
        self.high_pitch = int(high_pitch)
        self.velocity_bins = int(velocity_bins)
        self.time_shift_bins = int(time_shift_bins)
        self.time_shift_step = float(time_shift_step)
        self.pitch_count = self.high_pitch - self.low_pitch + 1

        self.pad_id = 0
        self.bos_id = 1
        self.eos_id = 2
        self.velocity_offset = 3
        self.note_on_offset = self.velocity_offset + self.velocity_bins
        self.note_off_offset = self.note_on_offset + self.pitch_count
        self.time_shift_offset = self.note_off_offset + self.pitch_count
        self.vocab_size = self.time_shift_offset + self.time_shift_bins

    @classmethod
    def from_config(cls, config: dict) -> "EventTokenizer":
        return cls(
            low_pitch=int(config.get("low_pitch", 21)),
            high_pitch=int(config.get("high_pitch", 108)),
            velocity_bins=int(config.get("velocity_bins", 32)),
            time_shift_bins=int(config.get("time_shift_bins", 100)),
            time_shift_step=float(config.get("time_shift_step", 0.01)),
        )

    def to_config(self) -> dict:
        return asdict(
            TokenizerConfig(
                low_pitch=self.low_pitch,
                high_pitch=self.high_pitch,
                velocity_bins=self.velocity_bins,
                time_shift_bins=self.time_shift_bins,
                time_shift_step=self.time_shift_step,
            )
        )

    def pitch_to_token_id(self, pitch: int) -> int:
        if pitch < self.low_pitch or pitch > self.high_pitch:
            raise ValueError(f"pitch {pitch} out of range [{self.low_pitch}, {self.high_pitch}]")
        return self.note_on_offset + (pitch - self.low_pitch)

    def pitch_off_token_id(self, pitch: int) -> int:
        if pitch < self.low_pitch or pitch > self.high_pitch:
            raise ValueError(f"pitch {pitch} out of range [{self.low_pitch}, {self.high_pitch}]")
        return self.note_off_offset + (pitch - self.low_pitch)

    def token_id_to_pitch(self, token_id: int) -> int:
        if self.note_on_offset <= token_id < self.note_on_offset + self.pitch_count:
            return self.low_pitch + (token_id - self.note_on_offset)
        if self.note_off_offset <= token_id < self.note_off_offset + self.pitch_count:
            return self.low_pitch + (token_id - self.note_off_offset)
        raise ValueError(f"token_id {token_id} is not a pitch token")

    def velocity_to_token_id(self, velocity: int) -> int:
        velocity = int(np.clip(velocity, 1, 127))
        bin_index = int((velocity - 1) * self.velocity_bins / 127.0)
        bin_index = min(self.velocity_bins - 1, max(0, bin_index))
        return self.velocity_offset + bin_index

    def token_id_to_velocity(self, token_id: int) -> int:
        if not self.is_velocity(token_id):
            raise ValueError(f"token_id {token_id} is not a velocity token")
        bin_index = token_id - self.velocity_offset
        center = (bin_index + 0.5) * 127.0 / self.velocity_bins
        return int(np.clip(round(center), 1, 127))

    def time_to_token_ids(self, delta_seconds: float) -> list[int]:
        if delta_seconds <= 0.0:
            return []

        remaining = float(delta_seconds)
        tokens: list[int] = []
        while remaining > self.time_shift_step * 0.5:
            steps = int(round(remaining / self.time_shift_step))
            steps = min(self.time_shift_bins, max(1, steps))
            tokens.append(self.time_shift_offset + (steps - 1))
            remaining = max(0.0, remaining - steps * self.time_shift_step)
        return tokens

    def token_id_to_time_shift(self, token_id: int) -> float:
        if not self.is_time_shift(token_id):
            raise ValueError(f"token_id {token_id} is not a time shift token")
        steps = (token_id - self.time_shift_offset) + 1
        return steps * self.time_shift_step

    def is_velocity(self, token_id: int) -> bool:
        return self.velocity_offset <= token_id < self.note_on_offset

    def is_note_on(self, token_id: int) -> bool:
        return self.note_on_offset <= token_id < self.note_off_offset

    def is_note_off(self, token_id: int) -> bool:
        return self.note_off_offset <= token_id < self.time_shift_offset

    def is_time_shift(self, token_id: int) -> bool:
        return self.time_shift_offset <= token_id < self.vocab_size

    def encode_path(self, midi_path: str | Path, add_bos: bool = True, add_eos: bool = True) -> list[int]:
        midi = pretty_midi.PrettyMIDI(str(midi_path))
        return self.encode_midi(midi, add_bos=add_bos, add_eos=add_eos)

    def encode_midi(
        self,
        midi: pretty_midi.PrettyMIDI,
        add_bos: bool = True,
        add_eos: bool = True,
    ) -> list[int]:
        events: list[tuple[float, int, str, int, int]] = []
        for instrument in midi.instruments:
            if instrument.is_drum:
                continue
            for note in instrument.notes:
                if note.end <= note.start:
                    continue
                if note.pitch < self.low_pitch or note.pitch > self.high_pitch:
                    continue
                velocity = int(np.clip(note.velocity, 1, 127))
                events.append((float(note.start), 1, "velocity", velocity, int(note.pitch)))
                events.append((float(note.start), 2, "note_on", velocity, int(note.pitch)))
                events.append((float(note.end), 0, "note_off", velocity, int(note.pitch)))

        # Order events by time first, then by type so velocity and note-on are emitted before note-off at the same timestamp.
        events.sort(key=lambda item: (item[0], item[1], item[4]))

        tokens: list[int] = []
        if add_bos:
            tokens.append(self.bos_id)

        current_time = 0.0
        for event_time, _, kind, velocity, pitch in events:
            delta = max(0.0, event_time - current_time)
            tokens.extend(self.time_to_token_ids(delta))
            current_time = event_time

            if kind == "note_off":
                tokens.append(self.pitch_off_token_id(pitch))
            elif kind == "velocity":
                tokens.append(self.velocity_to_token_id(velocity))
            elif kind == "note_on":
                tokens.append(self.pitch_to_token_id(pitch))

        if add_eos:
            tokens.append(self.eos_id)
        return tokens

    def decode_tokens(self, token_ids: Sequence[int]) -> pretty_midi.PrettyMIDI:
        midi = pretty_midi.PrettyMIDI()
        instrument = pretty_midi.Instrument(program=0, is_drum=False, name="Piano")

        current_time = 0.0
        current_velocity = 64
        # Keep a FIFO list per pitch so overlapping note-on / note-off pairs can be reconstructed safely.
        active_notes: dict[int, list[tuple[float, int]]] = {}

        for token_id in token_ids:
            token_id = int(token_id)
            if token_id in {self.pad_id, self.bos_id}:
                continue
            if token_id == self.eos_id:
                break
            if self.is_time_shift(token_id):
                current_time += self.token_id_to_time_shift(token_id)
                continue
            if self.is_velocity(token_id):
                current_velocity = self.token_id_to_velocity(token_id)
                continue
            if self.is_note_on(token_id):
                pitch = self.token_id_to_pitch(token_id)
                active_notes.setdefault(pitch, []).append((current_time, current_velocity))
                continue
            if self.is_note_off(token_id):
                pitch = self.token_id_to_pitch(token_id)
                starts = active_notes.get(pitch)
                if starts:
                    start_time, velocity = starts.pop(0)
                    end_time = max(current_time, start_time + self.time_shift_step)
                    instrument.notes.append(
                        pretty_midi.Note(
                            velocity=int(velocity),
                            pitch=int(pitch),
                            start=float(start_time),
                            end=float(end_time),
                        )
                    )

        final_time = current_time + max(self.time_shift_step, 0.05)
        for pitch, starts in active_notes.items():
            for start_time, velocity in starts:
                end_time = max(final_time, start_time + self.time_shift_step)
                instrument.notes.append(
                    pretty_midi.Note(
                        velocity=int(velocity),
                        pitch=int(pitch),
                        start=float(start_time),
                        end=float(end_time),
                    )
                )

        instrument.notes.sort(key=lambda note: (note.start, note.pitch, note.end))
        midi.instruments.append(instrument)
        return midi
