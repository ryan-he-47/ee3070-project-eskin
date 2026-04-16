from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.dataloader import create_maestro_dataloaders


def main() -> None:
    dataset_root = PROJECT_ROOT / "dataset" / "maestro-v3.0.0"

    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset path not found: {dataset_root}")

    loaders = create_maestro_dataloaders(
        dataset_root=dataset_root,
        batch_size=2,
        seq_len=64,
        train_stride=64,
        eval_stride=128,
        fps=50,
        note_dim=127,
        num_workers=0,
        pin_memory=False,
        max_train_files=2,
        max_validation_files=1,
        max_test_files=1,
    )

    for split, loader in loaders.items():
        dataset = loader.dataset
        x, y = next(iter(loader))
        print(f"[{split}] files={dataset.num_files} samples={dataset.num_samples}")
        print(f"[{split}] x shape={tuple(x.shape)} y shape={tuple(y.shape)}")
        print(
            f"[{split}] x range=({float(x.min()):.4f}, {float(x.max()):.4f}) "
            f"y range=({float(y.min()):.4f}, {float(y.max()):.4f})"
        )


if __name__ == "__main__":
    main()
