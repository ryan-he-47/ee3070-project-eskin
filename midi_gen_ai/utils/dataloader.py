from __future__ import annotations

import csv
import math
import random
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset, Sampler

try:
	import pretty_midi
except ImportError as exc:  # pragma: no cover - import error is user environment specific
	raise ImportError(
		"pretty_midi is required for MAESTRO loading. Install with: pip install pretty_midi"
	) from exc


@dataclass(frozen=True)
class _FileMeta:
	path: Path
	duration: float


@dataclass(frozen=True)
class _SampleMeta:
	file_idx: int
	start_frame: int


class GroupedWindowBatchSampler(Sampler[List[int]]):
	"""Yield batches that stay mostly within the same MIDI file."""

	def __init__(
		self,
		sample_groups: Sequence[Sequence[int]],
		batch_size: int,
		shuffle: bool,
		drop_last: bool,
		seed: int = 42,
	) -> None:
		if batch_size <= 0:
			raise ValueError("batch_size must be > 0")

		self.sample_groups = [list(group) for group in sample_groups if group]
		self.batch_size = batch_size
		self.shuffle = shuffle
		self.drop_last = drop_last
		self.seed = seed
		self._epoch = 0

	def __iter__(self) -> Iterator[List[int]]:
		rng = random.Random(self.seed + self._epoch)
		self._epoch += 1

		file_groups = [list(group) for group in self.sample_groups]
		if self.shuffle:
			rng.shuffle(file_groups)
			for group in file_groups:
				rng.shuffle(group)

		ordered_indices: List[int] = []
		for group in file_groups:
			ordered_indices.extend(group)

		for start in range(0, len(ordered_indices), self.batch_size):
			batch = ordered_indices[start : start + self.batch_size]
			if len(batch) < self.batch_size and self.drop_last:
				break
			yield batch

	def __len__(self) -> int:
		total = sum(len(group) for group in self.sample_groups)
		if self.drop_last:
			return total // self.batch_size
		return (total + self.batch_size - 1) // self.batch_size


class MaestroPianoRollDataset(Dataset):
	"""MAESTRO dataset -> fixed-length piano-roll windows for autoregressive training.

	Each sample returns:
	- x: [seq_len, note_dim]
	- y: [seq_len, note_dim], where y[t] is x[t+1] in the original sequence
	"""

	def __init__(
		self,
		dataset_root: str | Path,
		split: str = "train",
		seq_len: int = 128,
		stride: int = 64,
		fps: int = 50,
		note_dim: int = 127,
		velocity_scale: float = 127.0,
		max_files: Optional[int] = None,
		cache_size: int = 8,
	) -> None:
		self.dataset_root = Path(dataset_root)
		self.csv_path = self.dataset_root / "maestro-v3.0.0.csv"
		self.split = split
		self.seq_len = seq_len
		self.stride = stride
		self.fps = fps
		self.note_dim = note_dim
		self.velocity_scale = velocity_scale
		self.cache_size = max(1, cache_size)

		if self.note_dim <= 0 or self.note_dim > 128:
			raise ValueError("note_dim must be in [1, 128]")
		if self.seq_len <= 0:
			raise ValueError("seq_len must be > 0")
		if self.stride <= 0:
			raise ValueError("stride must be > 0")
		if self.fps <= 0:
			raise ValueError("fps must be > 0")

		self._files = self._collect_files(max_files=max_files)
		self._samples, self._sample_groups = self._build_sample_index()
		self._roll_cache: "OrderedDict[int, np.ndarray]" = OrderedDict()

	def _collect_files(self, max_files: Optional[int]) -> List[_FileMeta]:
		if not self.csv_path.exists():
			raise FileNotFoundError(f"MAESTRO split file not found: {self.csv_path}")

		files: List[_FileMeta] = []
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
			raise ValueError(
				f"No MIDI files found for split='{self.split}' in {self.dataset_root}"
			)
		return files

	def _build_sample_index(self) -> Tuple[List[_SampleMeta], List[List[int]]]:
		samples: List[_SampleMeta] = []
		sample_groups: List[List[int]] = [[] for _ in self._files]
		needed = self.seq_len + 1

		for file_idx, meta in enumerate(self._files):
			approx_frames = int(math.ceil(meta.duration * self.fps))
			if approx_frames < needed:
				continue
			max_start = approx_frames - needed
			for start in range(0, max_start + 1, self.stride):
				index = len(samples)
				samples.append(_SampleMeta(file_idx=file_idx, start_frame=start))
				sample_groups[file_idx].append(index)

		if not samples:
			raise ValueError(
				"No valid training windows were generated. "
				"Try reducing seq_len or check dataset integrity."
			)
		return samples, sample_groups

	def _load_roll(self, file_idx: int) -> np.ndarray:
		if file_idx in self._roll_cache:
			roll = self._roll_cache.pop(file_idx)
			self._roll_cache[file_idx] = roll
			return roll

		midi_path = self._files[file_idx].path
		pm = pretty_midi.PrettyMIDI(str(midi_path))

		# pretty_midi returns [pitch, frame], keep first note_dim and convert to [frame, note_dim]
		roll = pm.get_piano_roll(fs=self.fps)[: self.note_dim, :].T.astype(np.float32)

		if self.velocity_scale > 0:
			roll /= self.velocity_scale
		np.clip(roll, 0.0, 1.0, out=roll)

		self._roll_cache[file_idx] = roll
		if len(self._roll_cache) > self.cache_size:
			self._roll_cache.popitem(last=False)

		return roll

	def __len__(self) -> int:
		return len(self._samples)

	def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
		sample = self._samples[idx]
		roll = self._load_roll(sample.file_idx)

		start = sample.start_frame
		end = start + self.seq_len + 1
		window = roll[start:end]

		if window.shape[0] < self.seq_len + 1:
			pad_rows = self.seq_len + 1 - window.shape[0]
			pad = np.zeros((pad_rows, self.note_dim), dtype=np.float32)
			window = np.concatenate([window, pad], axis=0)

		x = torch.from_numpy(window[:-1]).float()
		y = torch.from_numpy(window[1:]).float()
		return x, y

	@property
	def num_files(self) -> int:
		return len(self._files)

	@property
	def num_samples(self) -> int:
		return len(self._samples)

	@property
	def sample_groups(self) -> List[List[int]]:
		return self._sample_groups


def create_maestro_dataloader(
	dataset_root: str | Path,
	split: str,
	batch_size: int,
	seq_len: int = 128,
	stride: int = 64,
	fps: int = 50,
	note_dim: int = 127,
	shuffle: Optional[bool] = None,
	num_workers: int = 0,
	pin_memory: bool = True,
	drop_last: bool = True,
	max_files: Optional[int] = None,
	cache_size: int = 8,
	group_windows_by_file: bool = True,
	seed: int = 42,
) -> DataLoader:
	dataset = MaestroPianoRollDataset(
		dataset_root=dataset_root,
		split=split,
		seq_len=seq_len,
		stride=stride,
		fps=fps,
		note_dim=note_dim,
		max_files=max_files,
		cache_size=cache_size,
	)

	if shuffle is None:
		shuffle = split == "train"

	if group_windows_by_file:
		batch_sampler = GroupedWindowBatchSampler(
			sample_groups=dataset.sample_groups,
			batch_size=batch_size,
			shuffle=shuffle,
			drop_last=drop_last,
			seed=seed,
		)
		loader_kwargs = {
			"batch_sampler": batch_sampler,
			"num_workers": num_workers,
			"pin_memory": pin_memory,
		}
		if num_workers > 0:
			loader_kwargs["persistent_workers"] = True
			loader_kwargs["prefetch_factor"] = 2
		return DataLoader(dataset, **loader_kwargs)

	return DataLoader(
		dataset,
		batch_size=batch_size,
		shuffle=shuffle,
		num_workers=num_workers,
		pin_memory=pin_memory,
		drop_last=drop_last,
		persistent_workers=num_workers > 0,
		prefetch_factor=2 if num_workers > 0 else None,
	)


def create_maestro_dataloaders(
	dataset_root: str | Path,
	batch_size: int,
	seq_len: int = 128,
	train_stride: int = 64,
	eval_stride: int = 128,
	fps: int = 50,
	note_dim: int = 127,
	num_workers: int = 0,
	pin_memory: bool = True,
	max_train_files: Optional[int] = None,
	max_validation_files: Optional[int] = None,
	max_test_files: Optional[int] = None,
	group_windows_by_file: bool = True,
	seed: int = 42,
) -> Dict[str, DataLoader]:
	train_loader = create_maestro_dataloader(
		dataset_root=dataset_root,
		split="train",
		batch_size=batch_size,
		seq_len=seq_len,
		stride=train_stride,
		fps=fps,
		note_dim=note_dim,
		shuffle=True,
		num_workers=num_workers,
		pin_memory=pin_memory,
		drop_last=True,
		max_files=max_train_files,
		group_windows_by_file=group_windows_by_file,
		seed=seed,
	)
	validation_loader = create_maestro_dataloader(
		dataset_root=dataset_root,
		split="validation",
		batch_size=batch_size,
		seq_len=seq_len,
		stride=eval_stride,
		fps=fps,
		note_dim=note_dim,
		shuffle=False,
		num_workers=num_workers,
		pin_memory=pin_memory,
		drop_last=False,
		max_files=max_validation_files,
		group_windows_by_file=group_windows_by_file,
		seed=seed,
	)
	test_loader = create_maestro_dataloader(
		dataset_root=dataset_root,
		split="test",
		batch_size=batch_size,
		seq_len=seq_len,
		stride=eval_stride,
		fps=fps,
		note_dim=note_dim,
		shuffle=False,
		num_workers=num_workers,
		pin_memory=pin_memory,
		drop_last=False,
		max_files=max_test_files,
		group_windows_by_file=group_windows_by_file,
		seed=seed,
	)

	return {
		"train": train_loader,
		"validation": validation_loader,
		"test": test_loader,
	}
