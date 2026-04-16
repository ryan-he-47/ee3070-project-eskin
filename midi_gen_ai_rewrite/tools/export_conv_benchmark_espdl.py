from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import torch.nn as nn
from esp_ppq.core import QuantizationPolicy, QuantizationProperty

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PROJECT_ROOT = PROJECT_ROOT.parent / "sample_project"


class ConvBenchmarkModel(nn.Module):
    def __init__(self, in_ch: int = 1, base_ch: int = 32) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_ch, base_ch, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.Conv2d(base_ch, base_ch, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.Conv2d(base_ch, base_ch // 2, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.Conv2d(base_ch // 2, base_ch // 2, kernel_size=1, stride=1, padding=0),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export conv benchmark model as ESP-DL model.")
    parser.add_argument("--input-h", type=int, default=32)
    parser.add_argument("--input-w", type=int, default=32)
    parser.add_argument("--base-ch", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--calib-samples", type=int, default=64)
    parser.add_argument("--calib-batch-size", type=int, default=1)
    parser.add_argument("--opset", type=int, default=13)
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
    return parser


def export_onnx(model: nn.Module, onnx_path: Path, input_h: int, input_w: int, opset: int) -> None:
    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    dummy_input = torch.zeros((1, 1, input_h, input_w), dtype=torch.float32)
    dummy_input[0, 0, 0, 0] = 1.0

    torch.onnx.export(
        model,
        dummy_input,
        str(onnx_path),
        opset_version=opset,
        input_names=["input"],
        output_names=["output"],
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


def build_calibration_samples(input_h: int, input_w: int, sample_count: int) -> list[torch.Tensor]:
    samples: list[torch.Tensor] = []
    for _ in range(sample_count):
        samples.append(torch.rand((1, 1, input_h, input_w), dtype=torch.float32))
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


def export_espdl(onnx_path: Path, espdl_path: Path, input_h: int, input_w: int, calib_samples: int, calib_batch_size: int) -> None:
    from esp_ppq import QuantizationSettingFactory
    from esp_ppq.api import espdl_quantize_onnx
    from esp_ppq.quantization.quantizer.EspdlQuantizer import BaseEspdlQuantizer
    from torch.utils.data import DataLoader

    per_tensor_policy = QuantizationPolicy(
        QuantizationProperty.SYMMETRICAL | QuantizationProperty.LINEAR | QuantizationProperty.PER_TENSOR
    )

    original_create_espdl_quant_config = BaseEspdlQuantizer.create_espdl_quant_config

    def _create_espdl_quant_config_per_tensor(self, operation, num_of_bits, quant_min, quant_max, bias_bits):
        config = original_create_espdl_quant_config(
            self,
            operation,
            num_of_bits,
            quant_min,
            quant_max,
            bias_bits,
        )

        for tqc_list in (config.input_quantization_config, config.output_quantization_config):
            for tqc in tqc_list:
                if tqc.policy.has_property(QuantizationProperty.PER_CHANNEL):
                    tqc._policy = per_tensor_policy
                    tqc._channel_axis = None

        return config

    BaseEspdlQuantizer.create_espdl_quant_config = _create_espdl_quant_config_per_tensor

    quant_setting = QuantizationSettingFactory.espdl_setting()
    calibration_dataset = CalibrationDataset(build_calibration_samples(input_h, input_w, calib_samples))
    dataloader = DataLoader(calibration_dataset, batch_size=calib_batch_size, shuffle=False, collate_fn=collate_fn)

    espdl_path.parent.mkdir(parents=True, exist_ok=True)
    espdl_quantize_onnx(
        onnx_import_file=str(onnx_path),
        espdl_export_file=str(espdl_path),
        calib_dataloader=dataloader,
        calib_steps=min(32, max(1, len(dataloader))),
        input_shape=[1, 1, input_h, input_w],
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

    model = ConvBenchmarkModel(in_ch=1, base_ch=args.base_ch)
    model.eval()

    export_onnx(model, onnx_path, input_h=args.input_h, input_w=args.input_w, opset=args.opset)
    export_espdl(
        onnx_path=onnx_path,
        espdl_path=espdl_path,
        input_h=args.input_h,
        input_w=args.input_w,
        calib_samples=args.calib_samples,
        calib_batch_size=args.calib_batch_size,
    )

    summary_path = espdl_path.with_suffix(".json")
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "kind": "conv_benchmark_model",
                "onnx_path": str(onnx_path),
                "espdl_path": str(espdl_path),
                "input_shape": [1, 1, args.input_h, args.input_w],
                "base_ch": args.base_ch,
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
