from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import pretty_midi
import torch

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.dataset import MaestroEventDataset
from src.model import EventLSTMLM
from src.tokenizer import EventTokenizer


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate symbolic music continuations from an event-LM checkpoint.")
    parser.add_argument("--checkpoint", type=str, required=True)
    parser.add_argument(
        "--dataset-root",
        type=str,
        default=str(PROJECT_ROOT.parent / "midi_gen_ai" / "dataset" / "maestro-v3.0.0"),
    )
    parser.add_argument("--output-midi", type=str, default=str(PROJECT_ROOT / "runs" / "generated.mid"))
    parser.add_argument("--prompt-midi", type=str, default=None)
    parser.add_argument("--prompt-split", type=str, default="train", choices=["train", "validation", "test"])
    parser.add_argument("--prompt-index", type=int, default=0)
    parser.add_argument("--prompt-window-len", type=int, default=1024)
    parser.add_argument("--min-new-tokens", type=int, default=0)
    parser.add_argument("--min-new-seconds", type=float, default=0.0)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--context-len", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Directory used to persist tokenized MAESTRO files.",
    )
    parser.add_argument("--seed", type=int, default=42)
    return parser


def sample_from_logits(logits: torch.Tensor, temperature: float, top_k: int, top_p: float) -> int:
    temperature = max(1e-4, float(temperature))
    probs = torch.softmax(logits / temperature, dim=-1)

    if top_k > 0 and top_k < probs.numel():
        top_values, top_indices = torch.topk(probs, top_k)
        filtered = torch.zeros_like(probs)
        filtered[top_indices] = top_values
        probs = filtered

    if 0.0 < top_p < 1.0:
        sorted_probs, sorted_indices = torch.sort(probs, descending=True)
        cumulative = torch.cumsum(sorted_probs, dim=-1)
        keep = cumulative <= top_p
        keep[0] = True
        filtered = torch.zeros_like(probs)
        filtered[sorted_indices[keep]] = probs[sorted_indices[keep]]
        probs = filtered

    total = probs.sum()
    if float(total) <= 0.0:
        probs = torch.softmax(logits, dim=-1)
    else:
        probs = probs / total

    next_token = torch.multinomial(probs, num_samples=1).item()
    return int(next_token)


@torch.no_grad()
def generate_tokens(
    model: EventLSTMLM,
    tokenizer: EventTokenizer,
    prompt_tokens: list[int],
    min_new_tokens: int,
    min_new_seconds: float,
    max_new_tokens: int,
    context_len: int,
    temperature: float,
    top_k: int,
    top_p: float,
    device: torch.device,
) -> list[int]:
    tokens = list(prompt_tokens)
    context_len = max(1, int(context_len))
    min_new_tokens = max(0, int(min_new_tokens))
    min_new_seconds = max(0.0, float(min_new_seconds))
    generated_seconds = 0.0

    # Generation is autoregressive: each new token is sampled from the last context window.
    for step in range(max(1, int(max_new_tokens))):
        input_ids = torch.tensor(tokens[-context_len:], dtype=torch.long, device=device).unsqueeze(0)
        logits = model(input_ids)[0, -1]

        # Block EOS early so the model cannot terminate before the prompt has enough continuation.
        if step < min_new_tokens and logits.numel() > 2:
            logits = logits.clone()
            logits[2] = -1e9

        next_token = sample_from_logits(logits, temperature=temperature, top_k=top_k, top_p=top_p)

        if next_token == 2 and (step < min_new_tokens or generated_seconds < min_new_seconds):
            continue

        tokens.append(next_token)
        if tokenizer.is_time_shift(next_token):
            generated_seconds += float(tokenizer.token_id_to_time_shift(next_token))

        if next_token == 2 and step >= min_new_tokens and generated_seconds >= min_new_seconds:
            break
    return tokens


def load_prompt_tokens(args: argparse.Namespace, tokenizer: EventTokenizer) -> list[int]:
    if args.prompt_midi:
        midi = pretty_midi.PrettyMIDI(str(args.prompt_midi))
        return tokenizer.encode_midi(midi, add_bos=True, add_eos=False)

    prompt_dataset = MaestroEventDataset(
        dataset_root=args.dataset_root,
        split=args.prompt_split,
        tokenizer=tokenizer,
        seq_len=args.prompt_window_len,
        stride=args.prompt_window_len,
        max_files=None,
        cache_dir=args.cache_dir,
    )
    if args.prompt_index < 0 or args.prompt_index >= len(prompt_dataset):
        raise IndexError(f"prompt-index {args.prompt_index} out of range [0, {len(prompt_dataset)-1}]")
    x, _ = prompt_dataset[args.prompt_index]
    return x.tolist()


def main() -> None:
    args = build_arg_parser().parse_args()
    checkpoint_path = Path(args.checkpoint)
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(checkpoint_path, map_location=device)
    tokenizer = EventTokenizer.from_config(checkpoint["config"]["tokenizer_config"])
    model = EventLSTMLM.from_config(checkpoint["config"]["model_config"]).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    prompt_tokens = load_prompt_tokens(args, tokenizer)
    generated_tokens = generate_tokens(
        model=model,
        tokenizer=tokenizer,
        prompt_tokens=prompt_tokens,
        min_new_tokens=args.min_new_tokens,
        min_new_seconds=args.min_new_seconds,
        max_new_tokens=args.max_new_tokens,
        context_len=args.context_len,
        temperature=args.temperature,
        top_k=args.top_k,
        top_p=args.top_p,
        device=device,
    )

    midi = tokenizer.decode_tokens(generated_tokens)
    output_path = Path(args.output_midi)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    midi.write(str(output_path))

    summary = {
        "checkpoint": str(checkpoint_path),
        "prompt_length": len(prompt_tokens),
        "generated_length": len(generated_tokens),
        "min_new_tokens": args.min_new_tokens,
        "min_new_seconds": args.min_new_seconds,
        "temperature": args.temperature,
        "top_k": args.top_k,
        "top_p": args.top_p,
        "context_len": args.context_len,
        "output_midi": str(output_path),
    }
    summary_path = output_path.with_suffix(".json")
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"[done] wrote midi: {output_path}")
    print(f"[info] summary: {summary_path}")


if __name__ == "__main__":
    main()
