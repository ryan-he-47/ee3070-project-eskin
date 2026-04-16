from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import torch.nn as nn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PROJECT_ROOT = PROJECT_ROOT.parent / "sample_project"


class RandomBenchmarkModel(nn.Module):
    def __init__(self, vocab_size: int, hidden_dim: int) -> None:
        super().__init__()
        self.vocab_size = int(vocab_size)
        self.hidden_dim = int(hidden_dim)
        self.net = nn.Sequential(
            nn.Flatten(start_dim=1),
            nn.Linear(self.vocab_size, self.hidden_dim),
            nn.ReLU(),
            nn.Linear(self.hidden_dim, self.vocab_size),
        )

    def forward(self, one_hot_tokens: torch.Tensor) -> torch.Tensor:
        # Input: [B, 1, vocab], Output: [B, 1, vocab]
        y = self.net(one_hot_tokens)
        return y.unsqueeze(1)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export random benchmark model as ESP-DL model.")
    parser.add_argument("--vocab-size", type=int, default=311)
    parser.add_argument("--hidden-dim", type=int, default=384)
    parser.add_argument(
        "--onnx-path",
        type=str,
        default=str(SAMPLE_PROJECT_ROOT / "main" / "models" / "p4" / "v2_best.onnx"),
    )
    parser.add_argument(
        "--espdl-path",
        type=str,
        default=str(SAMPLE_PROJECT_ROOT / "main" / "models" / "p4" / "v2_best.espdl"),
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--calib-samples", type=int, default=64)
    parser.add_argument("--calib-batch-size", type=int, default=1)
    parser.add_argument("--opset", type=int, default=13)
    return parser


def export_onnx(model: nn.Module, onnx_path: Path, vocab_size: int, opset: int) -> None:
    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    dummy_input = torch.zeros((1, 1, vocab_size), dtype=torch.float32)
    dummy_input[0, 0, 0] = 1.0

    torch.onnx.export(
        model,
        dummy_input,
        str(onnx_path),
        opset_version=opset,
        input_names=["one_hot_tokens"],
        output_names=["logits"],
        do_constant_folding=True,
        dynamic_axes=None,
    )

    import onnx
    import onnxsim

    exported = onnx.load(str(onnx_path))
    simplified, check = onnxsim.simplify(exported)
    if not check:
        raise RuntimeError("ONNX simplification failed validation")
    onnx.save(onnx.shape_inference.infer_shapes(simplified), str(onnx_path))


def build_calibration_samples(vocab_size: int, sample_count: int) -> list[torch.Tensor]:
    samples: list[torch.Tensor] = []
    for _ in range(sample_count):
        token_id = torch.randint(low=0, high=vocab_size, size=(1, 1), dtype=torch.long)
        one_hot = torch.nn.functional.one_hot(token_id, num_classes=vocab_size).to(torch.float32)
        samples.append(one_hot)
    return samples


class CalibrationDataset(torch.utils.data.Dataset):
    def __init__(self, samples: list[torch.Tensor]) -> None:
        self.samples = samples

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> torch.Tensor:
        return self.samples[index]


def collate_fn(batch: list[torch.Tensor]) -> torch.Tensor:
    return batch[0]


def export_espdl(onnx_path: Path, espdl_path: Path, vocab_size: int, calib_samples: int, calib_batch_size: int) -> None:
    from esp_ppq import QuantizationSettingFactory
    from esp_ppq.api import espdl_quantize_onnx
    from torch.utils.data import DataLoader

    quant_setting = QuantizationSettingFactory.espdl_setting()
    calibration_dataset = CalibrationDataset(build_calibration_samples(vocab_size, calib_samples))
    dataloader = DataLoader(calibration_dataset, batch_size=calib_batch_size, shuffle=False, collate_fn=collate_fn)

    espdl_path.parent.mkdir(parents=True, exist_ok=True)
    espdl_quantize_onnx(
        onnx_import_file=str(onnx_path),
        espdl_export_file=str(espdl_path),
        calib_dataloader=dataloader,
        calib_steps=min(32, max(1, len(dataloader))),
        input_shape=[1, 1, vocab_size],
        target="esp32p4",
        num_of_bits=8,
        collate_fn=lambda batch: batch,
        setting=quant_setting,
        device="cpu",
        error_report=True,
        skip_export=False,
        export_test_values=True,
        verbose=1,
        inputs=None,
    )


def main() -> None:
    args = build_arg_parser().parse_args()
    torch.manual_seed(args.seed)

    onnx_path = Path(args.onnx_path)
    espdl_path = Path(args.espdl_path)

    model = RandomBenchmarkModel(vocab_size=args.vocab_size, hidden_dim=args.hidden_dim)
    model.eval()

    export_onnx(model, onnx_path, vocab_size=args.vocab_size, opset=args.opset)
    export_espdl(
        onnx_path=onnx_path,
        espdl_path=espdl_path,
        vocab_size=args.vocab_size,
        calib_samples=args.calib_samples,
        calib_batch_size=args.calib_batch_size,
    )

    summary_path = espdl_path.with_suffix(".json")
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "kind": "random_benchmark_model",
                "onnx_path": str(onnx_path),
                "espdl_path": str(espdl_path),
                "vocab_size": args.vocab_size,
                "hidden_dim": args.hidden_dim,
                "seed": args.seed,
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    print(f"[done] ONNX:  {onnx_path}")
    print(f"[done] ESPDL: {espdl_path}")
    print(f"[done] meta:  {summary_path}")


if __name__ == "__main__":
    main()
