from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

from src.tokenizer import EventTokenizer


@dataclass(frozen=True)
class _FileMeta:
    path: Path
    duration: float


class MaestroEventDataset(Dataset):
    def __init__(
        self,
        dataset_root: str | Path,
        split: str,
        tokenizer: EventTokenizer,
        seq_len: int = 1024,
        stride: int = 512,
        max_files: Optional[int] = None,
        cache_dir: str | Path | None = None,
        rebuild_cache: bool = False,
    ) -> None:
        self.dataset_root = Path(dataset_root)
        self.csv_path = self.dataset_root / "maestro-v3.0.0.csv"
        self.split = split
        self.tokenizer = tokenizer
        self.seq_len = int(seq_len)
        self.stride = int(stride)
        self.rebuild_cache = bool(rebuild_cache)
        self.cache_root = (
            Path(cache_dir)
            if cache_dir is not None
            else (self.dataset_root / ".event_token_cache")
        )
        self.tokenizer_cache_key = self._tokenizer_cache_key()

        if self.seq_len <= 0:
            raise ValueError("seq_len must be > 0")
        if self.stride <= 0:
            raise ValueError("stride must be > 0")

        self._files = self._collect_files(max_files=max_files)
        self._sequences: list[np.ndarray] = []
        self._samples: list[tuple[int, int]] = []
        self._build_index()

    def _tokenizer_cache_key(self) -> str:
        payload = repr(self.tokenizer.to_config()).encode("utf-8")
        return hashlib.sha1(payload).hexdigest()[:12]

    def _cache_path_for(self, meta: _FileMeta) -> Path:
        stat = meta.path.stat()
        rel_path = meta.path.relative_to(self.dataset_root).as_posix()
        digest_source = f"{rel_path}|{stat.st_size}|{stat.st_mtime_ns}|{self.tokenizer_cache_key}"
        digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()
        return self.cache_root / self.tokenizer_cache_key / self.split / f"{digest}.npy"

    def _load_or_build_tokens(self, meta: _FileMeta) -> np.ndarray:
        cache_path = self._cache_path_for(meta)
        # Persist tokenized MIDI on disk and reopen it with mmap so repeated runs avoid re-tokenizing the same file.
        if cache_path.exists() and not self.rebuild_cache:
            return np.load(cache_path, mmap_mode="r")

        print(
            f"[info] tokenizing {self.split} file: {meta.path.name}",
            flush=True,
        )
        tokens = np.asarray(self.tokenizer.encode_path(meta.path), dtype=np.int64)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(cache_path, tokens)
        return np.load(cache_path, mmap_mode="r")

    def _collect_files(self, max_files: Optional[int]) -> list[_FileMeta]:
        if not self.csv_path.exists():
            raise FileNotFoundError(f"MAESTRO split file not found: {self.csv_path}")

        files: list[_FileMeta] = []
        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("split") != self.split:
                    continue
                rel_path = row.get("midi_filename")
                if not rel_path:
                    continue
                midi_path = self.dataset_root / rel_path
                if not midi_path.exists():
                    continue
                duration = float(row.get("duration", 0.0))
                files.append(_FileMeta(path=midi_path, duration=duration))
                if max_files is not None and len(files) >= max_files:
                    break

        if not files:
            raise ValueError(f"No MIDI files found for split='{self.split}' in {self.dataset_root}")
        return files

    def _build_index(self) -> None:
        needed = self.seq_len + 1
        # Build fixed-length next-token windows from each cached token file.
        for file_idx, meta in enumerate(self._files):
            print(
                f"[info] loading {self.split} file {file_idx + 1}/{len(self._files)}: {meta.path.name}",
                flush=True,
            )
            tokens = self._load_or_build_tokens(meta)
            self._sequences.append(tokens)

            if len(tokens) <= needed:
                self._samples.append((file_idx, 0))
                continue

            last_start = len(tokens) - needed
            starts = list(range(0, last_start + 1, self.stride))
            if starts[-1] != last_start:
                starts.append(last_start)
            for start in starts:
                self._samples.append((file_idx, start))

        if not self._samples:
            raise ValueError("No valid training windows were generated.")

    def __len__(self) -> int:
        return len(self._samples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        file_idx, start = self._samples[idx]
        seq = self._sequences[file_idx]
        window = seq[start : start + self.seq_len + 1]
        if len(window) < self.seq_len + 1:
            pad = np.full((self.seq_len + 1 - len(window),), self.tokenizer.pad_id, dtype=np.int64)
            window = np.concatenate([window, pad], axis=0)

        x = torch.from_numpy(window[:-1].copy()).long()
        y = torch.from_numpy(window[1:].copy()).long()
        return x, y

    @property
    def num_files(self) -> int:
        return len(self._files)

    @property
    def num_samples(self) -> int:
        return len(self._samples)


def create_event_dataloaders(
    dataset_root: str | Path,
    tokenizer: EventTokenizer,
    batch_size: int,
    seq_len: int = 1024,
    stride: int = 512,
    num_workers: int = 0,
    pin_memory: bool = True,
    max_train_files: Optional[int] = None,
    max_validation_files: Optional[int] = None,
    max_test_files: Optional[int] = None,
    cache_dir: str | Path | None = None,
    rebuild_cache: bool = False,
) -> dict[str, DataLoader]:
    train_dataset = MaestroEventDataset(
        dataset_root=dataset_root,
        split="train",
        tokenizer=tokenizer,
        seq_len=seq_len,
        stride=stride,
        max_files=max_train_files,
        cache_dir=cache_dir,
        rebuild_cache=rebuild_cache,
    )
    validation_dataset = MaestroEventDataset(
        dataset_root=dataset_root,
        split="validation",
        tokenizer=tokenizer,
        seq_len=seq_len,
        stride=stride,
        max_files=max_validation_files,
        cache_dir=cache_dir,
        rebuild_cache=rebuild_cache,
    )
    test_dataset = MaestroEventDataset(
        dataset_root=dataset_root,
        split="test",
        tokenizer=tokenizer,
        seq_len=seq_len,
        stride=stride,
        max_files=max_test_files,
        cache_dir=cache_dir,
        rebuild_cache=rebuild_cache,
    )

    loader_kwargs = dict(
        batch_size=batch_size,
        num_workers=num_workers,
        pin_memory=pin_memory,
    )
    if num_workers > 0:
        loader_kwargs["persistent_workers"] = True
        loader_kwargs["prefetch_factor"] = 2

    return {
        "train": DataLoader(train_dataset, shuffle=True, drop_last=True, **loader_kwargs),
        "validation": DataLoader(validation_dataset, shuffle=False, drop_last=False, **loader_kwargs),
        "test": DataLoader(test_dataset, shuffle=False, drop_last=False, **loader_kwargs),
    }
