from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from torch.utils.data import DataLoader

from utils.dataloader import MaestroPianoRollDataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quantize ONNX model to .espdl for ESP-DL")
    parser.add_argument("--onnx", type=str, required=True, help="Path to ONNX model")
    parser.add_argument("--output", type=str, required=True, help="Output .espdl path")
    parser.add_argument(
        "--dataset-root",
        type=str,
        default=str(PROJECT_ROOT / "dataset" / "maestro-v3.0.0"),
    )
    parser.add_argument("--seq-len", type=int, default=64)
    parser.add_argument("--calib-steps", type=int, default=64)
    parser.add_argument("--target", type=str, default="esp32p4", choices=["esp32", "esp32s3", "esp32p4", "c"])
    parser.add_argument("--bits", type=int, default=8, choices=[8, 16])
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--export-test-values", action="store_true")
    parser.add_argument("--max-train-files", type=int, default=8)
    return parser.parse_args()


def build_calib_loader(dataset_root: str, seq_len: int, max_train_files: int) -> DataLoader:
    dataset = MaestroPianoRollDataset(
        dataset_root=dataset_root,
        split="train",
        seq_len=seq_len,
        stride=seq_len,
        fps=50,
        note_dim=127,
        max_files=max_train_files,
        cache_size=4,
    )

    # ESP-DL deployment is batch=1, use batch_size=1 for calibration consistency.
    return DataLoader(dataset, batch_size=1, shuffle=False, num_workers=0, drop_last=False)


def main() -> None:
    args = parse_args()

    try:
        from esp_ppq.api import espdl_quantize_onnx
    except Exception as exc:
        raise ImportError(
            "esp-ppq is required. Install with: pip install esp-ppq"
        ) from exc

    calib_loader = build_calib_loader(
        dataset_root=args.dataset_root,
        seq_len=args.seq_len,
        max_train_files=args.max_train_files,
    )

    def collate_fn(batch):
        # batch item: (x, y), quantization only needs model input x
        x, _ = batch
        if isinstance(x, (list, tuple)):
            x = x[0]
        return x.float()

    onnx_path = Path(args.onnx)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    graph = espdl_quantize_onnx(
        onnx_import_file=str(onnx_path),
        espdl_export_file=str(output_path),
        calib_dataloader=calib_loader,
        calib_steps=args.calib_steps,
        input_shape=[1, args.seq_len, 127],
        target=args.target,
        num_of_bits=args.bits,
        collate_fn=collate_fn,
        device=args.device,
        error_report=True,
        skip_export=False,
        export_test_values=args.export_test_values,
        verbose=0,
        inputs=None,
    )

    if graph is None:
        raise RuntimeError("espdl_quantize_onnx returned None")

    print(f"[done] espdl exported: {output_path}")


if __name__ == "__main__":
    main()
