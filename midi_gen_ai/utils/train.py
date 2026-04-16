from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
from torch.optim import AdamW


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from utils.dataloader import create_maestro_dataloaders


MODEL_PRESETS = {
	"tiny": {"hidden_size": 96, "num_layers": 1, "dropout": 0.0},
	"p4-balanced": {"hidden_size": 192, "num_layers": 2, "dropout": 0.1},
	"p4-large": {"hidden_size": 256, "num_layers": 2, "dropout": 0.1},
	"p4-xl": {"hidden_size": 320, "num_layers": 2, "dropout": 0.1},
}


class TinyLSTM(nn.Module):
	"""Small autoregressive LSTM for piano-roll next-frame prediction."""

	def __init__(
		self,
		note_dim: int = 127,
		hidden_size: int = 96,
		num_layers: int = 1,
		dropout: float = 0.0,
	) -> None:
		super().__init__()
		self.note_dim = note_dim
		self.hidden_size = hidden_size
		self.num_layers = num_layers

		# Keep batch_first=False to make exported ONNX graph closer to vanilla ONNX LSTM layout.
		self.lstm = nn.LSTM(
			input_size=note_dim,
			hidden_size=hidden_size,
			num_layers=num_layers,
			dropout=dropout if num_layers > 1 else 0.0,
			batch_first=False,
		)
		self.proj = nn.Linear(hidden_size, note_dim)

	def forward(self, x: torch.Tensor) -> torch.Tensor:
		# Input x: [batch, seq, note_dim]
		x = x.transpose(0, 1)  # [seq, batch, note_dim]
		h, _ = self.lstm(x)
		logits = self.proj(h)  # [seq, batch, note_dim]
		return logits.transpose(0, 1)  # [batch, seq, note_dim]


class SessionLogger:
	"""Write per-run loss curves to timestamped files under run_dir/logs."""

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


@dataclass
class TrainConfig:
	dataset_root: str
	run_dir: str
	model_preset: str
	fps: int
	seq_len: int
	hidden_size: int
	num_layers: int
	dropout: float
	epochs: int
	batch_size: int
	lr: float
	weight_decay: float
	grad_clip: float
	train_stride: int
	eval_stride: int
	num_workers: int
	max_train_files: Optional[int]
	max_validation_files: Optional[int]
	max_test_files: Optional[int]
	pin_memory: bool
	seed: int
	export_onnx: bool
	onnx_path: Optional[str]
	resume_from: Optional[str]


def count_parameters(model: nn.Module) -> int:
	return sum(parameter.numel() for parameter in model.parameters())


def estimate_model_size_mb(param_count: int) -> dict[str, float]:
	bytes_fp32 = param_count * 4
	bytes_fp16 = param_count * 2
	bytes_int8 = param_count
	mb = 1024 * 1024
	return {
		"fp32": bytes_fp32 / mb,
		"fp16": bytes_fp16 / mb,
		"int8": bytes_int8 / mb,
	}


def set_seed(seed: int) -> None:
	torch.manual_seed(seed)
	if torch.cuda.is_available():
		torch.cuda.manual_seed_all(seed)


def train_one_epoch(
	model: nn.Module,
	loader,
	criterion: nn.Module,
	optimizer: torch.optim.Optimizer,
	device: torch.device,
	grad_clip: float,
	epoch_index: int,
	log_every: int = 10,
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
		loss = criterion(logits, y)
		loss.backward()

		if grad_clip > 0:
			nn.utils.clip_grad_norm_(model.parameters(), max_norm=grad_clip)

		optimizer.step()
		total_loss += float(loss.item())
		total_batches += 1
		batch_elapsed = time.perf_counter() - batch_start

		if log_every > 0 and (batch_index == 1 or batch_index % log_every == 0):
			average_loss = total_loss / total_batches
			epoch_elapsed = time.perf_counter() - epoch_start
			print(
				f"[epoch {epoch_index:03d}] batch {batch_index:05d}/{len(loader):05d} "
				f"loss={average_loss:.6f} step={batch_elapsed:.2f}s elapsed={epoch_elapsed/60:.1f}m",
				flush=True,
			)

	return total_loss / max(total_batches, 1)


@torch.no_grad()
def evaluate(
	model: nn.Module,
	loader,
	criterion: nn.Module,
	device: torch.device,
	stage_name: str = "eval",
) -> float:
	model.eval()
	total_loss = 0.0
	total_batches = 0

	for batch_index, (x, y) in enumerate(loader, start=1):
		x = x.to(device, non_blocking=True)
		y = y.to(device, non_blocking=True)
		logits = model(x)
		loss = criterion(logits, y)
		total_loss += float(loss.item())
		total_batches += 1

		if batch_index == 1 or batch_index % 50 == 0:
			print(
				f"[{stage_name}] batch {batch_index:05d}/{len(loader):05d} "
				f"loss={total_loss / total_batches:.6f}",
				flush=True,
			)

	return total_loss / max(total_batches, 1)


def export_to_onnx(model: nn.Module, seq_len: int, output_path: Path) -> None:
	model_cpu = model.to("cpu").eval()
	dummy = torch.zeros(1, seq_len, 127, dtype=torch.float32)
	output_path.parent.mkdir(parents=True, exist_ok=True)

	# Static batch=1 and static sequence length are friendlier to ESP-DL deployment constraints.
	try:
		torch.onnx.export(
			model_cpu,
			dummy,
			str(output_path),
			input_names=["x"],
			output_names=["logits"],
			opset_version=18,
			do_constant_folding=False,
			dynamic_axes=None,
		)
	except ModuleNotFoundError as exc:
		missing = getattr(exc, "name", "")
		if missing in {"onnxscript", "onnx"}:
			raise RuntimeError(
				"ONNX export requires onnx and onnxscript. "
				"Install with: pip install onnx onnxscript"
			) from exc
		raise


def parse_args() -> TrainConfig:
	parser = argparse.ArgumentParser(description="Train a tiny LSTM for MIDI frame autoregression")
	parser.add_argument(
		"--dataset-root",
		type=str,
		default=str(PROJECT_ROOT / "dataset" / "maestro-v3.0.0"),
	)
	parser.add_argument("--run-dir", type=str, default=str(PROJECT_ROOT / "runs" / "lstm_demo"))
	parser.add_argument(
		"--model-preset",
		type=str,
		choices=sorted(MODEL_PRESETS.keys()),
		default="p4-large",
		help="Model size preset. LSTM in esp-dl currently requires batch=1 at inference.",
	)
	parser.add_argument("--seq-len", type=int, default=64)
	parser.add_argument("--fps", type=int, default=24)
	parser.add_argument("--hidden-size", type=int, default=None)
	parser.add_argument("--num-layers", type=int, default=None)
	parser.add_argument("--dropout", type=float, default=None)
	parser.add_argument("--epochs", type=int, default=20)
	parser.add_argument("--batch-size", type=int, default=64)
	parser.add_argument("--lr", type=float, default=1e-3)
	parser.add_argument("--weight-decay", type=float, default=1e-4)
	parser.add_argument("--grad-clip", type=float, default=1.0)
	parser.add_argument("--train-stride", type=int, default=64)
	parser.add_argument("--eval-stride", type=int, default=128)
	parser.add_argument("--num-workers", type=int, default=None)
	parser.add_argument("--max-train-files", type=int, default=None)
	parser.add_argument("--max-validation-files", type=int, default=None)
	parser.add_argument("--max-test-files", type=int, default=None)
	parser.add_argument("--pin-memory", action="store_true")
	parser.add_argument("--seed", type=int, default=42)
	# Kept for backward-compatible CLI scripts. This flag no longer has effect.
	parser.add_argument("--no-live-plot", action="store_true")
	parser.add_argument("--export-onnx", action="store_true")
	parser.add_argument("--onnx-path", type=str, default=None)
	parser.add_argument(
		"--resume-from",
		type=str,
		default=None,
		help="Checkpoint path to resume training from (best.pth or last.pth).",
	)

	args = parser.parse_args()
	preset = MODEL_PRESETS[args.model_preset]
	hidden_size = args.hidden_size if args.hidden_size is not None else preset["hidden_size"]
	num_layers = args.num_layers if args.num_layers is not None else preset["num_layers"]
	dropout = args.dropout if args.dropout is not None else preset["dropout"]
	default_num_workers = 4 if torch.cuda.is_available() else 0
	num_workers = args.num_workers if args.num_workers is not None else default_num_workers
	return TrainConfig(
		dataset_root=args.dataset_root,
		run_dir=args.run_dir,
		model_preset=args.model_preset,
		fps=args.fps,
		seq_len=args.seq_len,
		hidden_size=hidden_size,
		num_layers=num_layers,
		dropout=dropout,
		epochs=args.epochs,
		batch_size=args.batch_size,
		lr=args.lr,
		weight_decay=args.weight_decay,
		grad_clip=args.grad_clip,
		train_stride=args.train_stride,
		eval_stride=args.eval_stride,
		num_workers=num_workers,
		max_train_files=args.max_train_files,
		max_validation_files=args.max_validation_files,
		max_test_files=args.max_test_files,
		pin_memory=args.pin_memory or torch.cuda.is_available(),
		seed=args.seed,
		export_onnx=args.export_onnx,
		onnx_path=args.onnx_path,
		resume_from=args.resume_from,
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

	loaders = create_maestro_dataloaders(
		dataset_root=cfg.dataset_root,
		batch_size=cfg.batch_size,
		seq_len=cfg.seq_len,
		train_stride=cfg.train_stride,
		eval_stride=cfg.eval_stride,
		fps=cfg.fps,
		note_dim=127,
		num_workers=cfg.num_workers,
		pin_memory=cfg.pin_memory,
		max_train_files=cfg.max_train_files,
		max_validation_files=cfg.max_validation_files,
		max_test_files=cfg.max_test_files,
	)

	train_loader = loaders["train"]
	val_loader = loaders["validation"]
	test_loader = loaders["test"]

	print(f"[info] train samples: {train_loader.dataset.num_samples}")
	print(f"[info] val samples:   {val_loader.dataset.num_samples}")
	print(f"[info] test samples:  {test_loader.dataset.num_samples}")
	print(
		f"[info] dataloader: num_workers={cfg.num_workers} pin_memory={cfg.pin_memory} grouped_windows=True"
	)
	print(f"[info] piano-roll fps={cfg.fps}")

	model = TinyLSTM(
		note_dim=127,
		hidden_size=cfg.hidden_size,
		num_layers=cfg.num_layers,
		dropout=cfg.dropout,
	).to(device)
	param_count = count_parameters(model)
	size_mb = estimate_model_size_mb(param_count)
	print(
		f"[info] model: preset={cfg.model_preset} hidden={cfg.hidden_size} layers={cfg.num_layers} "
		f"dropout={cfg.dropout}"
	)
	print(
		f"[info] params={param_count:,} size(fp32/fp16/int8)="
		f"{size_mb['fp32']:.2f}/{size_mb['fp16']:.2f}/{size_mb['int8']:.2f} MB"
	)
	criterion = nn.BCEWithLogitsLoss()
	optimizer = AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
	session_logger = SessionLogger(run_dir=run_dir, config=asdict(cfg))
	print(f"[info] metrics log: {session_logger.session_path}")

	best_val = float("inf")
	best_path = run_dir / "best.pth"
	last_path = run_dir / "last.pth"
	start_epoch = 1

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
		print(
			f"[info] resumed from: {resume_path} (next_epoch={start_epoch}, best_val={best_val:.6f})"
		)
		if start_epoch > cfg.epochs:
			print(
				f"[warn] checkpoint epoch already >= target epochs ({cfg.epochs}); skip training loop."
			)

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
				epoch_index=epoch,
				log_every=10,
			)
			val_loss = evaluate(model=model, loader=val_loader, criterion=criterion, device=device, stage_name="val")
			epoch_seconds = time.perf_counter() - epoch_start

			print(f"[epoch {epoch:03d}] train={train_loss:.6f} val={val_loss:.6f}")

			ckpt = {
				"epoch": epoch,
				"model_state_dict": model.state_dict(),
				"optimizer_state_dict": optimizer.state_dict(),
				"train_loss": train_loss,
				"val_loss": val_loss,
				"config": asdict(cfg),
			}
			torch.save(ckpt, last_path)

			if val_loss < best_val:
				best_val = val_loss
				torch.save(ckpt, best_path)
				print(f"[info] new best checkpoint: {best_path}")

			session_logger.log_epoch(
				epoch=epoch,
				train_loss=train_loss,
				val_loss=val_loss,
				best_val_loss=best_val,
				epoch_seconds=epoch_seconds,
			)

		test_loss = evaluate(model=model, loader=test_loader, criterion=criterion, device=device, stage_name="test")
		print(f"[done] test_loss={test_loss:.6f}")
		session_logger.finalize(test_loss=test_loss, status="completed")
	except KeyboardInterrupt:
		print("[warn] training interrupted by user")
		session_logger.finalize(test_loss=float("nan"), status="interrupted")
		raise
	except Exception:
		session_logger.finalize(test_loss=float("nan"), status="failed")
		raise

	if cfg.export_onnx:
		onnx_path = Path(cfg.onnx_path) if cfg.onnx_path else (run_dir / "tiny_lstm.onnx")
		export_to_onnx(model=model, seq_len=cfg.seq_len, output_path=onnx_path)
		print(f"[done] exported onnx: {onnx_path}")


if __name__ == "__main__":
	main()
