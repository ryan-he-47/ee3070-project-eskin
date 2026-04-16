from __future__ import annotations

import argparse
import math
import struct
import sys
import wave
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.dataloader import MaestroPianoRollDataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render one dataloader window to WAV for auditory inspection."
    )
    parser.add_argument(
        "--dataset-root",
        type=str,
        default=str(PROJECT_ROOT / "dataset" / "maestro-v3.0.0"),
    )
    parser.add_argument("--split", type=str, default="train", choices=["train", "validation", "test"])
    parser.add_argument("--sample-index", type=int, default=0)
    parser.add_argument("--seq-len", type=int, default=128)
    parser.add_argument("--stride", type=int, default=64)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--note-dim", type=int, default=127)
    parser.add_argument("--max-files", type=int, default=1)
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument("--sample-rate", type=int, default=22050)
    parser.add_argument(
        "--output",
        type=str,
        default=str(PROJECT_ROOT / "runs" / "frame_audition" / "frame_window.wav"),
    )
    return parser.parse_args()


def midi_to_hz(midi_note: int) -> float:
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def render_roll_to_wave(
    roll: np.ndarray,
    fps: int,
    sample_rate: int,
    threshold: float,
) -> np.ndarray:
    frame_samples = max(1, int(round(sample_rate / float(fps))))
    total_samples = roll.shape[0] * frame_samples
    audio = np.zeros(total_samples, dtype=np.float32)

    # Keep oscillator phase continuous across frames to reduce click artifacts.
    phases = np.zeros(roll.shape[1], dtype=np.float64)

    for frame_idx in range(roll.shape[0]):
        start = frame_idx * frame_samples
        end = start + frame_samples
        t = np.arange(frame_samples, dtype=np.float64) / float(sample_rate)

        frame = roll[frame_idx]
        active_indices = np.where(frame > threshold)[0]
        if active_indices.size == 0:
            continue

        block = np.zeros(frame_samples, dtype=np.float64)
        for pitch in active_indices:
            freq = midi_to_hz(int(pitch))
            amp = float(frame[pitch])
            phase0 = phases[pitch]
            phase_curve = phase0 + (2.0 * math.pi * freq * t)
            block += amp * np.sin(phase_curve)
            phases[pitch] = (phase_curve[-1] + (2.0 * math.pi * freq / sample_rate)) % (2.0 * math.pi)

        # Normalize per-frame by active note count to keep dynamics in range.
        block /= max(1.0, float(active_indices.size))
        audio[start:end] = block.astype(np.float32)

    peak = float(np.max(np.abs(audio)))
    if peak > 1e-6:
        audio = 0.95 * (audio / peak)
    return audio


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(audio, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(struct.pack("<" + "h" * len(pcm16), *pcm16.tolist()))


def main() -> None:
    args = parse_args()

    dataset = MaestroPianoRollDataset(
        dataset_root=args.dataset_root,
        split=args.split,
        seq_len=args.seq_len,
        stride=args.stride,
        fps=args.fps,
        note_dim=args.note_dim,
        max_files=args.max_files,
    )

    if args.sample_index < 0 or args.sample_index >= len(dataset):
        raise IndexError(
            f"sample-index {args.sample_index} out of range [0, {len(dataset) - 1}]"
        )

    x, y = dataset[args.sample_index]
    # Rebuild the original window as seq_len + 1 frames.
    roll = np.concatenate([x.numpy(), y[-1:].numpy()], axis=0)

    audio = render_roll_to_wave(
        roll=roll,
        fps=args.fps,
        sample_rate=args.sample_rate,
        threshold=args.threshold,
    )

    output_path = Path(args.output)
    write_wav(output_path, audio, args.sample_rate)

    duration_sec = len(audio) / float(args.sample_rate)
    print(f"[done] wrote wav: {output_path}")
    print(f"[info] split={args.split} sample_index={args.sample_index} seq_len={args.seq_len}")
    print(f"[info] fps={args.fps} sample_rate={args.sample_rate} duration={duration_sec:.2f}s")


if __name__ == "__main__":
    main()
