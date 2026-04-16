from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from generate import generate_tokens, load_prompt_tokens
from src.dataset import MaestroEventDataset, create_event_dataloaders
from src.metrics import summarize_midi, token_entropy, token_repeat_rate, token_unique_ratio
from src.model import EventLSTMLM
from src.tokenizer import EventTokenizer


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate an event-LM checkpoint.")
    parser.add_argument("--checkpoint", type=str, required=True)
    parser.add_argument(
        "--dataset-root",
        type=str,
        default=str(PROJECT_ROOT.parent / "midi_gen_ai" / "dataset" / "maestro-v3.0.0"),
    )
    parser.add_argument("--split", type=str, default="validation", choices=["train", "validation", "test"])
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--prompt-midi", type=str, default=None)
    parser.add_argument("--prompt-split", type=str, default="train", choices=["train", "validation", "test"])
    parser.add_argument("--prompt-index", type=int, default=0)
    parser.add_argument("--prompt-window-len", type=int, default=1024)
    parser.add_argument("--max-new-tokens", type=int, default=512)
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
    parser.add_argument("--rebuild-cache", action="store_true", help="Force regeneration of cached token files.")
    parser.add_argument("--output-json", type=str, default=None)
    return parser


@torch.no_grad()
def compute_loss(model: nn.Module, loader, criterion: nn.Module, device: torch.device, vocab_size: int) -> float:
    model.eval()
    total_loss = 0.0
    total_batches = 0
    for x, y in loader:
        x = x.to(device, non_blocking=True)
        y = y.to(device, non_blocking=True)
        logits = model(x)
        loss = criterion(logits.reshape(-1, vocab_size), y.reshape(-1))
        total_loss += float(loss.item())
        total_batches += 1
    return total_loss / max(1, total_batches)


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

    loaders = create_event_dataloaders(
        dataset_root=args.dataset_root,
        tokenizer=tokenizer,
        batch_size=args.batch_size,
        seq_len=int(checkpoint["config"]["train_config"]["seq_len"]),
        stride=int(checkpoint["config"]["train_config"]["stride"]),
        num_workers=args.num_workers,
        pin_memory=torch.cuda.is_available(),
        max_train_files=args.max_files if args.split == "train" else None,
        max_validation_files=args.max_files if args.split == "validation" else None,
        max_test_files=args.max_files if args.split == "test" else None,
        cache_dir=args.cache_dir,
        rebuild_cache=args.rebuild_cache,
    )

    criterion = nn.CrossEntropyLoss(ignore_index=tokenizer.pad_id)
    split_loss = compute_loss(model, loaders[args.split], criterion, device, tokenizer.vocab_size)
    split_ppl = float(np.exp(split_loss))

    report = {
        "checkpoint": str(checkpoint_path),
        "split": args.split,
        "loss": split_loss,
        "perplexity": split_ppl,
        "tokenizer_vocab": tokenizer.vocab_size,
    }

    if args.prompt_midi or args.prompt_index is not None:
        prompt_tokens = load_prompt_tokens(args, tokenizer)
        generated_tokens = generate_tokens(
            model=model,
            prompt_tokens=prompt_tokens,
            max_new_tokens=args.max_new_tokens,
            context_len=args.context_len,
            temperature=args.temperature,
            top_k=args.top_k,
            top_p=args.top_p,
            device=device,
        )
        midi = tokenizer.decode_tokens(generated_tokens)
        report["generation"] = {
            "prompt_length": len(prompt_tokens),
            "generated_length": len(generated_tokens),
            "token_repeat_rate_4": token_repeat_rate(generated_tokens, n=4),
            "token_unique_ratio": token_unique_ratio(generated_tokens),
            "token_entropy": token_entropy(generated_tokens),
            "midi": summarize_midi(midi),
        }

    output_json = Path(args.output_json) if args.output_json else checkpoint_path.with_suffix(".eval.json")
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[info] wrote report: {output_json}")


if __name__ == "__main__":
    main()
