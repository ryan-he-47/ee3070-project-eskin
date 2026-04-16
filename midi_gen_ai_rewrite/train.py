from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
from torch.optim import AdamW

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.dataset import create_event_dataloaders
from src.model import EventLSTMLM
from src.tokenizer import EventTokenizer


@dataclass
class TrainConfig:
    dataset_root: str
    run_dir: str
    seq_len: int
    stride: int
    batch_size: int
    epochs: int
    embed_dim: int
    hidden_dim: int
    num_layers: int
    dropout: float
    lr: float
    weight_decay: float
    grad_clip: float
    num_workers: int
    seed: int
    low_pitch: int
    high_pitch: int
    velocity_bins: int
    time_shift_bins: int
    time_shift_step: float
    max_train_files: Optional[int]
    max_validation_files: Optional[int]
    max_test_files: Optional[int]
    cache_dir: Optional[str]
    rebuild_cache: bool
    resume_from: Optional[str]


class RunLogger:
    def __init__(self, run_dir: Path, config: dict) -> None:
        self.started_at = datetime.now()
        timestamp = self.started_at.strftime("%Y%m%d_%H%M%S")
        self.session_name = f"train_{timestamp}"
        self.logs_dir = run_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.session_path = self.logs_dir / f"{self.session_name}.json"
        self.latest_path = self.logs_dir / "latest.json"
        self.state = {
            "session_name": self.session_name,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "status": "running",
            "config": config,
            "epochs": [],
        }
        self._flush()

    def log_epoch(self, epoch: int, train_loss: float, val_loss: float, best_val_loss: float, epoch_seconds: float) -> None:
        self.state["epochs"].append(
            {
                "epoch": int(epoch),
                "train_loss": float(train_loss),
                "val_loss": float(val_loss),
                "best_val_loss": float(best_val_loss),
                "epoch_seconds": float(epoch_seconds),
            }
        )
        self._flush()

    def finalize(self, test_loss: float, status: str = "completed") -> None:
        finished_at = datetime.now()
        self.state["status"] = status
        self.state["test_loss"] = float(test_loss)
        self.state["finished_at"] = finished_at.isoformat(timespec="seconds")
        self.state["total_seconds"] = float((finished_at - self.started_at).total_seconds())
        self._flush()

    def _flush(self) -> None:
        with self.session_path.open("w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
        with self.latest_path.open("w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train an event-sequence LSTM for symbolic music.")
    parser.add_argument(
        "--dataset-root",
        type=str,
        default=str(PROJECT_ROOT.parent / "midi_gen_ai" / "dataset" / "maestro-v3.0.0"),
    )
    parser.add_argument("--run-dir", type=str, default=str(PROJECT_ROOT / "runs" / "event_lm_v1"))
    parser.add_argument("--seq-len", type=int, default=1024)
    parser.add_argument("--stride", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--embed-dim", type=int, default=256)
    parser.add_argument("--hidden-dim", type=int, default=512)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--grad-clip", type=float, default=1.0)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--low-pitch", type=int, default=21)
    parser.add_argument("--high-pitch", type=int, default=108)
    parser.add_argument("--velocity-bins", type=int, default=32)
    parser.add_argument("--time-shift-bins", type=int, default=100)
    parser.add_argument("--time-shift-step", type=float, default=0.01)
    parser.add_argument("--max-train-files", type=int, default=None)
    parser.add_argument("--max-validation-files", type=int, default=None)
    parser.add_argument("--max-test-files", type=int, default=None)
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Directory used to persist tokenized MAESTRO files (defaults to dataset_root/.event_token_cache).",
    )
    parser.add_argument(
        "--rebuild-cache",
        action="store_true",
        help="Force regeneration of cached token files.",
    )
    parser.add_argument("--resume-from", type=str, default=None)
    return parser


def parse_args() -> TrainConfig:
    args = build_arg_parser().parse_args()
    return TrainConfig(
        dataset_root=args.dataset_root,
        run_dir=args.run_dir,
        seq_len=args.seq_len,
        stride=args.stride,
        batch_size=args.batch_size,
        epochs=args.epochs,
        embed_dim=args.embed_dim,
        hidden_dim=args.hidden_dim,
        num_layers=args.num_layers,
        dropout=args.dropout,
        lr=args.lr,
        weight_decay=args.weight_decay,
        grad_clip=args.grad_clip,
        num_workers=args.num_workers,
        seed=args.seed,
        low_pitch=args.low_pitch,
        high_pitch=args.high_pitch,
        velocity_bins=args.velocity_bins,
        time_shift_bins=args.time_shift_bins,
        time_shift_step=args.time_shift_step,
        max_train_files=args.max_train_files,
        max_validation_files=args.max_validation_files,
        max_test_files=args.max_test_files,
        cache_dir=args.cache_dir,
        rebuild_cache=args.rebuild_cache,
        resume_from=args.resume_from,
    )


def set_seed(seed: int) -> None:
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def count_parameters(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters())


def train_one_epoch(
    model: nn.Module,
    loader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    grad_clip: float,
    vocab_size: int,
    epoch_index: int,
    log_every: int = 20,
) -> float:
    model.train()
    total_loss = 0.0
    total_batches = 0
    epoch_start = time.perf_counter()

    for batch_index, (x, y) in enumerate(loader, start=1):
        batch_start = time.perf_counter()
        x = x.to(device, non_blocking=True)
        y = y.to(device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)
        logits = model(x)
        loss = criterion(logits.reshape(-1, vocab_size), y.reshape(-1))
        loss.backward()
        if grad_clip > 0:
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=grad_clip)
        optimizer.step()

        total_loss += float(loss.item())
        total_batches += 1

        if log_every > 0 and (batch_index == 1 or batch_index % log_every == 0):
            elapsed = time.perf_counter() - epoch_start
            step_time = time.perf_counter() - batch_start
            print(
                f"[epoch {epoch_index:03d}] batch {batch_index:05d}/{len(loader):05d} "
                f"loss={total_loss / total_batches:.6f} step={step_time:.2f}s elapsed={elapsed/60:.1f}m",
                flush=True,
            )

    return total_loss / max(1, total_batches)


@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader,
    criterion: nn.Module,
    device: torch.device,
    vocab_size: int,
    stage_name: str,
) -> float:
    model.eval()
    total_loss = 0.0
    total_batches = 0

    for batch_index, (x, y) in enumerate(loader, start=1):
        x = x.to(device, non_blocking=True)
        y = y.to(device, non_blocking=True)
        logits = model(x)
        loss = criterion(logits.reshape(-1, vocab_size), y.reshape(-1))
        total_loss += float(loss.item())
        total_batches += 1

        if batch_index == 1 or batch_index % 25 == 0:
            print(f"[{stage_name}] batch {batch_index:05d}/{len(loader):05d} loss={total_loss / total_batches:.6f}", flush=True)

    return total_loss / max(1, total_batches)


def save_checkpoint(path: Path, model: nn.Module, optimizer: torch.optim.Optimizer, epoch: int, train_loss: float, val_loss: float, config: dict) -> None:
    torch.save(
        {
            "epoch": int(epoch),
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "train_loss": float(train_loss),
            "val_loss": float(val_loss),
            "config": config,
        },
        path,
    )


def main() -> None:
    cfg = parse_args()
    set_seed(cfg.seed)

    run_dir = Path(cfg.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "train_config.json").open("w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, ensure_ascii=False, indent=2)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[info] device: {device}")
    print("[info] using cached token files under dataset_root/.event_token_cache unless overridden")

    tokenizer = EventTokenizer(
        low_pitch=cfg.low_pitch,
        high_pitch=cfg.high_pitch,
        velocity_bins=cfg.velocity_bins,
        time_shift_bins=cfg.time_shift_bins,
        time_shift_step=cfg.time_shift_step,
    )

    print("[info] building dataloaders...")
    loaders = create_event_dataloaders(
        dataset_root=cfg.dataset_root,
        tokenizer=tokenizer,
        batch_size=cfg.batch_size,
        seq_len=cfg.seq_len,
        stride=cfg.stride,
        num_workers=cfg.num_workers,
        pin_memory=torch.cuda.is_available(),
        max_train_files=cfg.max_train_files,
        max_validation_files=cfg.max_validation_files,
        max_test_files=cfg.max_test_files,
        cache_dir=cfg.cache_dir,
        rebuild_cache=cfg.rebuild_cache,
    )

    train_loader = loaders["train"]
    val_loader = loaders["validation"]
    test_loader = loaders["test"]
    print("[info] dataloaders ready")

    print(f"[info] train samples: {train_loader.dataset.num_samples}")
    print(f"[info] val samples:   {val_loader.dataset.num_samples}")
    print(f"[info] test samples:  {test_loader.dataset.num_samples}")
    print(f"[info] tokenizer vocab: {tokenizer.vocab_size}")

    model = EventLSTMLM(
        vocab_size=tokenizer.vocab_size,
        embed_dim=cfg.embed_dim,
        hidden_dim=cfg.hidden_dim,
        num_layers=cfg.num_layers,
        dropout=cfg.dropout,
    ).to(device)
    optimizer = AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    criterion = nn.CrossEntropyLoss(ignore_index=tokenizer.pad_id)
    logger = RunLogger(run_dir, config=asdict(cfg))

    best_val = float("inf")
    start_epoch = 1
    best_path = run_dir / "best.pth"
    last_path = run_dir / "last.pth"

    if cfg.resume_from:
        resume_path = Path(cfg.resume_from)
        if not resume_path.exists():
            raise FileNotFoundError(f"Resume checkpoint not found: {resume_path}")
        checkpoint = torch.load(resume_path, map_location=device)
        model.load_state_dict(checkpoint["model_state_dict"])
        if "optimizer_state_dict" in checkpoint:
            optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        start_epoch = int(checkpoint.get("epoch", 0)) + 1
        best_val = float(checkpoint.get("val_loss", float("inf")))
        print(f"[info] resumed from {resume_path} next_epoch={start_epoch} best_val={best_val:.6f}")

    print(f"[info] model params: {count_parameters(model):,}")

    try:
        for epoch in range(start_epoch, cfg.epochs + 1):
            epoch_start = time.perf_counter()
            train_loss = train_one_epoch(
                model=model,
                loader=train_loader,
                criterion=criterion,
                optimizer=optimizer,
                device=device,
                grad_clip=cfg.grad_clip,
                vocab_size=tokenizer.vocab_size,
                epoch_index=epoch,
            )
            val_loss = evaluate(
                model=model,
                loader=val_loader,
                criterion=criterion,
                device=device,
                vocab_size=tokenizer.vocab_size,
                stage_name="val",
            )
            epoch_seconds = time.perf_counter() - epoch_start

            print(f"[epoch {epoch:03d}] train={train_loss:.6f} val={val_loss:.6f}")

            checkpoint_config = {
                "train_config": asdict(cfg),
                "tokenizer_config": tokenizer.to_config(),
                "model_config": model.to_config(),
            }
            save_checkpoint(last_path, model, optimizer, epoch, train_loss, val_loss, checkpoint_config)
            if val_loss < best_val:
                best_val = val_loss
                save_checkpoint(best_path, model, optimizer, epoch, train_loss, val_loss, checkpoint_config)
                print(f"[info] new best checkpoint: {best_path}")

            logger.log_epoch(epoch, train_loss, val_loss, best_val, epoch_seconds)

        test_loss = evaluate(
            model=model,
            loader=test_loader,
            criterion=criterion,
            device=device,
            vocab_size=tokenizer.vocab_size,
            stage_name="test",
        )
        print(f"[done] test_loss={test_loss:.6f}")
        logger.finalize(test_loss=test_loss, status="completed")
    except KeyboardInterrupt:
        print("[warn] interrupted by user")
        logger.finalize(test_loss=float("nan"), status="interrupted")
        raise
    except Exception:
        logger.finalize(test_loss=float("nan"), status="failed")
        raise


if __name__ == "__main__":
    main()
