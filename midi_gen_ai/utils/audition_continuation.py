from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import List

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.audition_frames import render_roll_to_wave, write_wav
from utils.dataloader import MaestroPianoRollDataset
from utils.train import TinyLSTM


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch render continuation WAVs: prompt audio + model continuation."
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=str(PROJECT_ROOT / "runs" / "lstm_demo" / "best.pth"),
        help="Path to trained checkpoint (.pth).",
    )
    parser.add_argument(
        "--dataset-root",
        type=str,
        default=str(PROJECT_ROOT / "dataset" / "maestro-v3.0.0"),
    )
    parser.add_argument("--split", type=str, default="train", choices=["train", "validation", "test"])
    parser.add_argument("--sample-indices", type=str, default="0,40,80")
    parser.add_argument("--num-samples", type=int, default=3)
    parser.add_argument("--random-samples", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--prompt-seconds", type=float, default=10.0)
    parser.add_argument("--continue-seconds", type=float, default=30.0)
    parser.add_argument("--fps", type=int, default=None, help="Override checkpoint/default fps.")
    parser.add_argument("--note-dim", type=int, default=127)
    parser.add_argument("--threshold", type=float, default=0.10)
    parser.add_argument(
        "--decode-mode",
        type=str,
        default="hybrid",
        choices=["threshold", "topk", "hybrid", "sample"],
        help="Frame decode strategy from probabilities.",
    )
    parser.add_argument("--top-k", type=int, default=4, help="Top-k notes used in topk/hybrid fallback.")
    parser.add_argument(
        "--min-active",
        type=int,
        default=1,
        help="Ensure at least this many notes remain active in hybrid mode.",
    )
    parser.add_argument(
        "--max-active",
        type=int,
        default=0,
        help="Cap active notes per frame (0 means no cap).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Logit temperature before sigmoid; >1.0 makes outputs less peaky.",
    )
    parser.add_argument(
        "--sustain",
        type=float,
        default=0.0,
        help="Carry over previous frame with this decay factor to reduce dead-air.",
    )
    parser.add_argument(
        "--stuck-window",
        type=int,
        default=24,
        help="If active-note count stays unchanged this many frames, inject jitter.",
    )
    parser.add_argument(
        "--stuck-jitter",
        type=float,
        default=0.08,
        help="Random probability perturbation used when stuck-window is triggered.",
    )
    parser.add_argument(
        "--frame-hold",
        type=int,
        default=1,
        help="Keep each decoded frame for N model steps (N>1 slows perceived harmonic motion).",
    )
    parser.add_argument(
        "--voice-lead-weight",
        type=float,
        default=0.0,
        help="Blend decoded probabilities with a prior built from the previous frame's pitches.",
    )
    parser.add_argument(
        "--voice-lead-sigma",
        type=float,
        default=4.0,
        help="Pitch-distance sigma (in semitone bins) for the previous-frame continuity prior.",
    )
    parser.add_argument(
        "--voice-lead-hold-bonus",
        type=float,
        default=1.5,
        help="Extra weight for pitches that were already active in the previous frame.",
    )
    parser.add_argument(
        "--voice-lead-neighbor-bonus",
        type=float,
        default=1.0,
        help="Extra weight for nearby pitches around previous active notes.",
    )
    parser.add_argument(
        "--centroid-lock-weight",
        type=float,
        default=0.0,
        help="Blend decoded probabilities with a Gaussian prior around the previous pitch centroid.",
    )
    parser.add_argument(
        "--centroid-lock-sigma",
        type=float,
        default=9.0,
        help="Pitch-distance sigma for the centroid-lock prior.",
    )
    parser.add_argument(
        "--binary-active",
        action="store_true",
        help="Set all active notes to 1.0 amplitude after decoding for clearer audition.",
    )
    parser.add_argument("--sample-rate", type=int, default=22050)
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(PROJECT_ROOT / "runs" / "continuation_audition"),
    )
    return parser.parse_args()


def parse_indices(raw: str) -> List[int]:
    cleaned = [part.strip() for part in raw.split(",") if part.strip()]
    return [int(part) for part in cleaned]


def resolve_fps(args: argparse.Namespace, checkpoint: dict) -> int:
    if args.fps is not None:
        return int(args.fps)

    cfg = checkpoint.get("config", {})
    ckpt_fps = cfg.get("fps")
    if isinstance(ckpt_fps, int) and ckpt_fps > 0:
        return ckpt_fps

    # Backward-compatible fallback for older checkpoints without fps metadata.
    return 24


def build_model_from_checkpoint(checkpoint: dict, note_dim: int, device: torch.device) -> TinyLSTM:
    cfg = checkpoint.get("config", {})
    hidden_size = int(cfg.get("hidden_size", 96))
    num_layers = int(cfg.get("num_layers", 1))
    dropout = float(cfg.get("dropout", 0.0))

    model = TinyLSTM(
        note_dim=note_dim,
        hidden_size=hidden_size,
        num_layers=num_layers,
        dropout=dropout,
    ).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model


def decode_next_frame(
    probs: np.ndarray,
    threshold: float,
    decode_mode: str,
    top_k: int,
    min_active: int,
    max_active: int,
    prev_frame: np.ndarray | None,
    sustain: float,
    binary_active: bool,
) -> np.ndarray:
    frame = np.zeros_like(probs, dtype=np.float32)

    if decode_mode == "threshold":
        frame = np.where(probs >= threshold, probs, 0.0).astype(np.float32)
    elif decode_mode == "topk":
        k = max(1, min(int(top_k), probs.shape[0]))
        indices = np.argpartition(probs, -k)[-k:]
        frame[indices] = probs[indices].astype(np.float32)
    elif decode_mode == "sample":
        sampled = (np.random.rand(*probs.shape) < probs).astype(np.float32)
        frame = sampled
        active = int(np.count_nonzero(frame > 0.0))
        if active < int(min_active):
            k = max(int(min_active), min(int(top_k), probs.shape[0]))
            indices = np.argpartition(probs, -k)[-k:]
            frame[indices] = 1.0
    else:
        frame = np.where(probs >= threshold, probs, 0.0).astype(np.float32)
        active = int(np.count_nonzero(frame > 0.0))
        required = max(0, int(min_active) - active)
        if required > 0:
            k = max(required, min(int(top_k), probs.shape[0]))
            indices = np.argpartition(probs, -k)[-k:]
            frame[indices] = np.maximum(frame[indices], probs[indices].astype(np.float32))

    if prev_frame is not None and sustain > 0.0:
        frame = np.maximum(frame, (prev_frame * float(sustain)).astype(np.float32))

    # Cap polyphony to avoid dense random clusters sounding like keyboard smash.
    if int(max_active) > 0:
        active_idx = np.where(frame > 0.0)[0]
        if active_idx.size > int(max_active):
            keep = active_idx[np.argsort(frame[active_idx])[-int(max_active):]]
            trimmed = np.zeros_like(frame, dtype=np.float32)
            trimmed[keep] = frame[keep]
            frame = trimmed

    if binary_active:
        frame = np.where(frame > 0.0, 1.0, 0.0).astype(np.float32)

    return frame.astype(np.float32)


def build_voice_lead_prior(
    prev_frame: np.ndarray,
    note_dim: int,
    sigma: float,
    hold_bonus: float,
    neighbor_bonus: float,
) -> np.ndarray:
    prior = np.zeros(note_dim, dtype=np.float32)
    active = np.where(prev_frame > 0.0)[0]
    if active.size == 0:
        return prior

    sigma = max(1e-3, float(sigma))
    two_sigma_sq = 2.0 * sigma * sigma
    pitch_ids = np.arange(note_dim, dtype=np.float32)

    for idx in active:
        amp = float(max(prev_frame[idx], 0.0))
        dist = np.abs(pitch_ids - float(idx))
        neighbor = np.exp(-(dist * dist) / two_sigma_sq).astype(np.float32)
        prior += neighbor_bonus * amp * neighbor
        prior[idx] += hold_bonus * amp

    peak = float(np.max(prior))
    if peak > 1e-6:
        prior /= peak
    return np.clip(prior, 0.0, 1.0).astype(np.float32)


def blend_with_voice_lead_prior(
    probs: np.ndarray,
    prev_frame: np.ndarray | None,
    voice_lead_weight: float,
    voice_lead_sigma: float,
    voice_lead_hold_bonus: float,
    voice_lead_neighbor_bonus: float,
) -> np.ndarray:
    if prev_frame is None or voice_lead_weight <= 0.0:
        return probs

    prior = build_voice_lead_prior(
        prev_frame=prev_frame,
        note_dim=probs.shape[0],
        sigma=voice_lead_sigma,
        hold_bonus=voice_lead_hold_bonus,
        neighbor_bonus=voice_lead_neighbor_bonus,
    )
    if not np.any(prior > 0.0):
        return probs

    weight = float(np.clip(voice_lead_weight, 0.0, 1.0))
    blended = (1.0 - weight) * probs + weight * prior
    return np.clip(blended, 0.0, 1.0).astype(np.float32)


def blend_with_centroid_lock_prior(
    probs: np.ndarray,
    prev_frame: np.ndarray | None,
    centroid_lock_weight: float,
    centroid_lock_sigma: float,
) -> np.ndarray:
    if prev_frame is None or centroid_lock_weight <= 0.0:
        return probs

    active = np.where(prev_frame > 0.0)[0]
    if active.size == 0:
        return probs

    weights = np.maximum(prev_frame[active], 0.0).astype(np.float32)
    weight_sum = float(weights.sum())
    if weight_sum <= 1e-6:
        return probs

    centroid = float(np.dot(active.astype(np.float32), weights) / weight_sum)
    sigma = max(1e-3, float(centroid_lock_sigma))
    pitch_ids = np.arange(probs.shape[0], dtype=np.float32)
    prior = np.exp(-((pitch_ids - centroid) ** 2) / (2.0 * sigma * sigma)).astype(np.float32)
    peak = float(np.max(prior))
    if peak > 1e-6:
        prior /= peak

    weight = float(np.clip(centroid_lock_weight, 0.0, 1.0))
    blended = (1.0 - weight) * probs + weight * prior
    return np.clip(blended, 0.0, 1.0).astype(np.float32)


def compute_roll_metrics(roll: np.ndarray, fps: int, threshold: float = 0.05) -> dict:
    if roll.size == 0:
        return {
            "frames": 0,
            "seconds": 0.0,
            "mean_active": 0.0,
            "std_active": 0.0,
            "change_ratio": 0.0,
            "onsets_per_sec": 0.0,
            "pitch_centroid_mean": 0.0,
            "pitch_centroid_std": 0.0,
            "centroid_step_mean": 0.0,
            "centroid_step_std": 0.0,
            "frame_overlap_mean": 0.0,
            "unique_frame_ratio": 0.0,
        }

    active = roll > threshold
    active_count = active.sum(axis=1).astype(np.float32)

    if active.shape[0] > 1:
        changed = np.any(active[1:] != active[:-1], axis=1)
        change_ratio = float(changed.mean())
    else:
        change_ratio = 0.0

    prev = np.zeros_like(active, dtype=bool)
    prev[1:] = active[:-1]
    onsets = np.logical_and(active, np.logical_not(prev)).sum()
    seconds = float(active.shape[0] / max(1, fps))
    onsets_per_sec = float(onsets / max(seconds, 1e-6))

    pitch_ids = np.arange(roll.shape[1], dtype=np.float32)
    weights = np.where(active, np.maximum(roll, 0.0), 0.0).astype(np.float32)
    weight_sum = weights.sum(axis=1)
    centroid = np.zeros(roll.shape[0], dtype=np.float32)
    nonzero = weight_sum > 1e-6
    centroid[nonzero] = (weights[nonzero] * pitch_ids[None, :]).sum(axis=1) / weight_sum[nonzero]

    if centroid.shape[0] > 1:
        centroid_step = np.abs(np.diff(centroid))
        centroid_step_mean = float(centroid_step.mean())
        centroid_step_std = float(centroid_step.std())
    else:
        centroid_step_mean = 0.0
        centroid_step_std = 0.0

    if active.shape[0] > 1:
        prev_active = active[:-1]
        next_active = active[1:]
        union = np.logical_or(prev_active, next_active).sum(axis=1).astype(np.float32)
        inter = np.logical_and(prev_active, next_active).sum(axis=1).astype(np.float32)
        overlap = np.divide(inter, np.maximum(union, 1.0), out=np.zeros_like(inter), where=union > 0.0)
        frame_overlap_mean = float(overlap.mean())
    else:
        frame_overlap_mean = 0.0

    packed = np.packbits(active.astype(np.uint8), axis=1)
    unique_rows = np.unique(packed, axis=0).shape[0]
    unique_frame_ratio = float(unique_rows / max(1, active.shape[0]))

    return {
        "frames": int(active.shape[0]),
        "seconds": seconds,
        "mean_active": float(active_count.mean()),
        "std_active": float(active_count.std()),
        "change_ratio": change_ratio,
        "onsets_per_sec": onsets_per_sec,
        "pitch_centroid_mean": float(centroid.mean()),
        "pitch_centroid_std": float(centroid.std()),
        "centroid_step_mean": centroid_step_mean,
        "centroid_step_std": centroid_step_std,
        "frame_overlap_mean": frame_overlap_mean,
        "unique_frame_ratio": unique_frame_ratio,
    }


@torch.no_grad()
def generate_continuation(
    model: TinyLSTM,
    prompt_roll: np.ndarray,
    continuation_frames: int,
    threshold: float,
    decode_mode: str,
    top_k: int,
    min_active: int,
    max_active: int,
    temperature: float,
    sustain: float,
    binary_active: bool,
    stuck_window: int,
    stuck_jitter: float,
    frame_hold: int,
    voice_lead_weight: float,
    voice_lead_sigma: float,
    voice_lead_hold_bonus: float,
    voice_lead_neighbor_bonus: float,
    centroid_lock_weight: float,
    centroid_lock_sigma: float,
    device: torch.device,
) -> np.ndarray:
    hidden = None

    # Warm up hidden state with real prompt frames.
    for frame in prompt_roll:
        step = torch.from_numpy(frame.astype(np.float32)).view(1, 1, -1).to(device)
        seq_in = step.transpose(0, 1)  # [1, 1, note_dim]
        output, hidden = model.lstm(seq_in, hidden)

    generated = []
    prev_out = output
    prev_frame = prompt_roll[-1].astype(np.float32) if len(prompt_roll) > 0 else None

    temp = max(1e-4, float(temperature))
    frame_hold = max(1, int(frame_hold))
    stuck_window = max(1, int(stuck_window))
    stuck_jitter = max(0.0, float(stuck_jitter))
    same_active_count = 0
    last_active_count: int | None = None
    hold_counter = 0

    for _ in range(continuation_frames):
        if hold_counter <= 0 or prev_frame is None:
            logits = model.proj(prev_out).transpose(0, 1)  # [1, 1, note_dim]
            probs = torch.sigmoid(logits / temp)[0, 0].detach().cpu().numpy().astype(np.float32)
            probs = blend_with_voice_lead_prior(
                probs=probs,
                prev_frame=prev_frame,
                voice_lead_weight=voice_lead_weight,
                voice_lead_sigma=voice_lead_sigma,
                voice_lead_hold_bonus=voice_lead_hold_bonus,
                voice_lead_neighbor_bonus=voice_lead_neighbor_bonus,
            )
            probs = blend_with_centroid_lock_prior(
                probs=probs,
                prev_frame=prev_frame,
                centroid_lock_weight=centroid_lock_weight,
                centroid_lock_sigma=centroid_lock_sigma,
            )

            # Break deterministic limit cycles by nudging probabilities when activity pattern stalls.
            current_active = int(np.count_nonzero(probs >= threshold))
            if last_active_count is not None and current_active == last_active_count:
                same_active_count += 1
            else:
                same_active_count = 0
            last_active_count = current_active

            if same_active_count >= stuck_window and stuck_jitter > 0.0:
                noise = np.random.uniform(-stuck_jitter, stuck_jitter, size=probs.shape).astype(np.float32)
                probs = np.clip(probs + noise, 0.0, 1.0)
                same_active_count = 0

            next_frame = decode_next_frame(
                probs=probs,
                threshold=threshold,
                decode_mode=decode_mode,
                top_k=top_k,
                min_active=min_active,
                max_active=max_active,
                prev_frame=prev_frame,
                sustain=sustain,
                binary_active=binary_active,
            )
            hold_counter = frame_hold - 1
        else:
            next_frame = prev_frame.copy()
            hold_counter -= 1
        generated.append(next_frame)
        prev_frame = next_frame

        step = torch.from_numpy(next_frame).view(1, 1, -1).to(device)
        seq_in = step.transpose(0, 1)
        prev_out, hidden = model.lstm(seq_in, hidden)

    if not generated:
        return np.zeros((0, prompt_roll.shape[1]), dtype=np.float32)
    return np.stack(generated, axis=0)


def main() -> None:
    args = parse_args()

    ckpt_path = Path(args.checkpoint)
    if not ckpt_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {ckpt_path}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(ckpt_path, map_location=device)

    fps = resolve_fps(args, checkpoint)
    prompt_frames = max(1, int(round(args.prompt_seconds * fps)))
    continuation_frames = max(1, int(round(args.continue_seconds * fps)))

    dataset = MaestroPianoRollDataset(
        dataset_root=args.dataset_root,
        split=args.split,
        seq_len=prompt_frames,
        stride=max(1, prompt_frames // 2),
        fps=fps,
        note_dim=args.note_dim,
        max_files=None,
    )

    model = build_model_from_checkpoint(
        checkpoint=checkpoint,
        note_dim=args.note_dim,
        device=device,
    )

    if args.random_samples:
        rng = random.Random(args.seed)
        sample_indices = rng.sample(range(len(dataset)), k=min(args.num_samples, len(dataset)))
    else:
        sample_indices = parse_indices(args.sample_indices)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "checkpoint": str(ckpt_path),
        "epoch": int(checkpoint.get("epoch", -1)),
        "fps": fps,
        "prompt_seconds": args.prompt_seconds,
        "continue_seconds": args.continue_seconds,
        "threshold": args.threshold,
        "decode_mode": args.decode_mode,
        "top_k": args.top_k,
        "min_active": args.min_active,
        "max_active": args.max_active,
        "temperature": args.temperature,
        "sustain": args.sustain,
        "binary_active": bool(args.binary_active),
        "stuck_window": args.stuck_window,
        "stuck_jitter": args.stuck_jitter,
        "frame_hold": args.frame_hold,
        "voice_lead_weight": args.voice_lead_weight,
        "voice_lead_sigma": args.voice_lead_sigma,
        "voice_lead_hold_bonus": args.voice_lead_hold_bonus,
        "voice_lead_neighbor_bonus": args.voice_lead_neighbor_bonus,
        "centroid_lock_weight": args.centroid_lock_weight,
        "centroid_lock_sigma": args.centroid_lock_sigma,
        "sample_indices": sample_indices,
        "files": [],
        "metrics": {
            "samples": [],
            "aggregate": {},
        },
    }

    for sample_idx in sample_indices:
        if sample_idx < 0 or sample_idx >= len(dataset):
            print(f"[warn] skip sample_index={sample_idx}, out of range [0, {len(dataset)-1}]")
            continue

        x, _ = dataset[sample_idx]
        prompt_roll = x.numpy().astype(np.float32)
        generated_roll = generate_continuation(
            model=model,
            prompt_roll=prompt_roll,
            continuation_frames=continuation_frames,
            threshold=args.threshold,
            decode_mode=args.decode_mode,
            top_k=args.top_k,
            min_active=args.min_active,
            max_active=args.max_active,
            temperature=args.temperature,
            sustain=args.sustain,
            binary_active=bool(args.binary_active),
            stuck_window=args.stuck_window,
            stuck_jitter=args.stuck_jitter,
            frame_hold=args.frame_hold,
            voice_lead_weight=args.voice_lead_weight,
            voice_lead_sigma=args.voice_lead_sigma,
            voice_lead_hold_bonus=args.voice_lead_hold_bonus,
            voice_lead_neighbor_bonus=args.voice_lead_neighbor_bonus,
            centroid_lock_weight=args.centroid_lock_weight,
            centroid_lock_sigma=args.centroid_lock_sigma,
            device=device,
        )

        combined_roll = np.concatenate([prompt_roll, generated_roll], axis=0)
        audio = render_roll_to_wave(
            roll=combined_roll,
            fps=fps,
            sample_rate=args.sample_rate,
            threshold=0.01,
        )

        output_path = output_dir / f"sample_{sample_idx}_p{prompt_frames}_c{continuation_frames}_fps{fps}.wav"
        write_wav(output_path, audio, args.sample_rate)

        prompt_sec = prompt_roll.shape[0] / float(fps)
        generated_sec = generated_roll.shape[0] / float(fps)
        total_sec = combined_roll.shape[0] / float(fps)
        print(
            f"[done] {output_path.name} prompt={prompt_sec:.2f}s continue={generated_sec:.2f}s total={total_sec:.2f}s"
        )
        summary["files"].append(
            {
                "sample_index": sample_idx,
                "wav": str(output_path),
                "prompt_frames": int(prompt_roll.shape[0]),
                "continue_frames": int(generated_roll.shape[0]),
                "total_frames": int(combined_roll.shape[0]),
            }
        )

        prompt_metrics = compute_roll_metrics(prompt_roll, fps=fps, threshold=0.05)
        cont_metrics = compute_roll_metrics(generated_roll, fps=fps, threshold=0.05)
        summary["metrics"]["samples"].append(
            {
                "sample_index": int(sample_idx),
                "prompt": prompt_metrics,
                "continuation": cont_metrics,
            }
        )

    if summary["metrics"]["samples"]:
        keys = [
            "mean_active",
            "std_active",
            "change_ratio",
            "onsets_per_sec",
            "pitch_centroid_mean",
            "pitch_centroid_std",
            "centroid_step_mean",
            "centroid_step_std",
            "frame_overlap_mean",
            "unique_frame_ratio",
        ]
        aggregate = {}
        for scope in ["prompt", "continuation"]:
            aggregate[scope] = {}
            for key in keys:
                values = [item[scope][key] for item in summary["metrics"]["samples"]]
                aggregate[scope][key] = float(np.mean(values))
        summary["metrics"]["aggregate"] = aggregate

    summary_path = output_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[info] summary: {summary_path}")


if __name__ == "__main__":
    main()
