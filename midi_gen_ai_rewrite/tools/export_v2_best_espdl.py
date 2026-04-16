from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from esp_ppq.core import QuantizationPolicy, QuantizationProperty

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PROJECT_ROOT = PROJECT_ROOT.parent / "sample_project"


@dataclass(frozen=True)
class ExportPaths:
    checkpoint: Path
    onnx_path: Path
    espdl_path: Path


class OneHotEventLSTMLM(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        embed_dim: int,
        hidden_dim: int,
        num_layers: int,
        dropout: float,
    ) -> None:
        super().__init__()
        self.vocab_size = int(vocab_size)
        self.embed_dim = int(embed_dim)
        self.hidden_dim = int(hidden_dim)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)

        self.embedding = nn.Linear(self.vocab_size, self.embed_dim, bias=False)
        self.lstm = nn.LSTM(
            input_size=self.embed_dim,
            hidden_size=self.hidden_dim,
            num_layers=self.num_layers,
            dropout=self.dropout if self.num_layers > 1 else 0.0,
            batch_first=True,
        )
        self.norm = nn.LayerNorm(self.hidden_dim)
        self.head = nn.Linear(self.hidden_dim, self.vocab_size)

    def forward(self, one_hot_tokens: torch.Tensor) -> torch.Tensor:
        embedded = self.embedding(one_hot_tokens)
        output, _ = self.lstm(embedded)
        output = self.norm(output)
        return self.head(output)


class EquivalentOneHotEventLSTMLM(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        embed_dim: int,
        hidden_dim: int,
        num_layers: int,
        dropout: float,
    ) -> None:
        super().__init__()
        self.vocab_size = int(vocab_size)
        self.embed_dim = int(embed_dim)
        self.hidden_dim = int(hidden_dim)
        self.num_layers = int(num_layers)
        self.dropout = float(dropout)

        self.embedding = nn.Linear(self.vocab_size, self.embed_dim, bias=False)
        self.head = nn.Linear(self.hidden_dim, self.vocab_size)

        self.weight_ih = nn.ParameterList()
        self.weight_hh = nn.ParameterList()
        self.bias_ih = nn.ParameterList()
        self.bias_hh = nn.ParameterList()

        for layer_idx in range(self.num_layers):
            input_dim = self.embed_dim if layer_idx == 0 else self.hidden_dim
            self.weight_ih.append(nn.Parameter(torch.empty(4 * self.hidden_dim, input_dim)))
            self.weight_hh.append(nn.Parameter(torch.empty(4 * self.hidden_dim, self.hidden_dim)))
            self.bias_ih.append(nn.Parameter(torch.empty(4 * self.hidden_dim)))
            self.bias_hh.append(nn.Parameter(torch.empty(4 * self.hidden_dim)))

        self.reset_parameters()

    def reset_parameters(self) -> None:
        nn.init.xavier_uniform_(self.embedding.weight)
        nn.init.xavier_uniform_(self.head.weight)
        nn.init.zeros_(self.head.bias)

        for layer_idx in range(self.num_layers):
            nn.init.xavier_uniform_(self.weight_ih[layer_idx])
            nn.init.orthogonal_(self.weight_hh[layer_idx])
            nn.init.zeros_(self.bias_ih[layer_idx])
            nn.init.zeros_(self.bias_hh[layer_idx])

    def forward(self, one_hot_tokens: torch.Tensor) -> torch.Tensor:
        x = self.embedding(one_hot_tokens)
        batch_size = x.shape[0]
        seq_len = x.shape[1]

        h_states = []
        c_states = []
        for _ in range(self.num_layers):
            h_states.append(x.new_zeros((batch_size, self.hidden_dim)))
            c_states.append(x.new_zeros((batch_size, self.hidden_dim)))

        outputs = []
        for t in range(seq_len):
            layer_input = x[:, t, :]
            for layer_idx in range(self.num_layers):
                gates = (
                    F.linear(layer_input, self.weight_ih[layer_idx], self.bias_ih[layer_idx])
                    + F.linear(h_states[layer_idx], self.weight_hh[layer_idx], self.bias_hh[layer_idx])
                )
                gate_i, gate_f, gate_g, gate_o = gates.chunk(4, dim=-1)
                input_gate = torch.sigmoid(gate_i)
                forget_gate = torch.sigmoid(gate_f)
                candidate = torch.tanh(gate_g)
                output_gate = torch.sigmoid(gate_o)

                c_states[layer_idx] = forget_gate * c_states[layer_idx] + input_gate * candidate
                h_states[layer_idx] = output_gate * torch.tanh(c_states[layer_idx])
                layer_input = h_states[layer_idx]

            outputs.append(layer_input.unsqueeze(1))

        output = torch.cat(outputs, dim=1)
        return self.head(output)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export midi_gen_ai_rewrite v2_best as ESP-DL compatible espdl.")
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=str(PROJECT_ROOT / "runs" / "event_lm_v2" / "best.pth"),
        help="Path to the trained PyTorch checkpoint.",
    )
    parser.add_argument(
        "--onnx-path",
        type=str,
        default=str(SAMPLE_PROJECT_ROOT / "main" / "models" / "p4" / "v2_best.onnx"),
        help="Where to write the intermediate ONNX model.",
    )
    parser.add_argument(
        "--espdl-path",
        type=str,
        default=str(SAMPLE_PROJECT_ROOT / "main" / "models" / "p4" / "v2_best.espdl"),
        help="Where to write the exported ESP-DL model.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--calib-samples", type=int, default=64)
    parser.add_argument("--calib-batch-size", type=int, default=1)
    parser.add_argument("--opset", type=int, default=13)
    parser.add_argument(
        "--equivalent-random-weights",
        action="store_true",
        help="Build a structurally equivalent model with random weights for speed benchmarking.",
    )
    parser.add_argument(
        "--equivalent-unrolled-lstm",
        action="store_true",
        help="Use an equivalent unrolled-LSTM graph (without ONNX LSTM op) for better esp-dl compatibility.",
    )
    return parser


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_checkpoint(checkpoint_path: Path) -> dict:
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
    return torch.load(checkpoint_path, map_location="cpu")


def infer_vocab_size(tokenizer_config: dict) -> int:
    low_pitch = int(tokenizer_config["low_pitch"])
    high_pitch = int(tokenizer_config["high_pitch"])
    velocity_bins = int(tokenizer_config["velocity_bins"])
    time_shift_bins = int(tokenizer_config["time_shift_bins"])
    pitch_count = high_pitch - low_pitch + 1
    return 3 + velocity_bins + pitch_count * 2 + time_shift_bins


def build_model_from_checkpoint(
    checkpoint: dict,
    equivalent_unrolled_lstm: bool,
    equivalent_random_weights: bool,
) -> nn.Module:
    model_config = checkpoint["config"]["model_config"]
    tokenizer_config = checkpoint["config"]["tokenizer_config"]
    vocab_size = infer_vocab_size(tokenizer_config)

    model_kwargs = dict(
        vocab_size=vocab_size,
        embed_dim=int(model_config["embed_dim"]),
        hidden_dim=int(model_config["hidden_dim"]),
        num_layers=int(model_config["num_layers"]),
        dropout=float(model_config["dropout"]),
    )

    if equivalent_unrolled_lstm:
        model = EquivalentOneHotEventLSTMLM(**model_kwargs)
    else:
        model = OneHotEventLSTMLM(**model_kwargs)

    if equivalent_random_weights:
        model.eval()
        return model

    state_dict = checkpoint["model_state_dict"]
    # Training model stores embedding as [vocab_size, embed_dim] (nn.Embedding),
    # while one-hot Linear expects [embed_dim, vocab_size].
    embedding_weight = state_dict["embedding.weight"]
    if tuple(embedding_weight.shape) == tuple(model.embedding.weight.shape):
        model.embedding.weight.data.copy_(embedding_weight)
    elif tuple(embedding_weight.t().shape) == tuple(model.embedding.weight.shape):
        model.embedding.weight.data.copy_(embedding_weight.t())
    else:
        raise RuntimeError(
            "Unexpected embedding weight shape: "
            f"checkpoint={tuple(embedding_weight.shape)} vs export_model={tuple(model.embedding.weight.shape)}"
        )
    if equivalent_unrolled_lstm:
        for layer_idx in range(model.num_layers):
            model.weight_ih[layer_idx].data.copy_(state_dict[f"lstm.weight_ih_l{layer_idx}"])
            model.weight_hh[layer_idx].data.copy_(state_dict[f"lstm.weight_hh_l{layer_idx}"])
            model.bias_ih[layer_idx].data.copy_(state_dict[f"lstm.bias_ih_l{layer_idx}"])
            model.bias_hh[layer_idx].data.copy_(state_dict[f"lstm.bias_hh_l{layer_idx}"])
    else:
        model.lstm.load_state_dict({key.replace("lstm.", ""): value for key, value in state_dict.items() if key.startswith("lstm.")})
    model.norm.load_state_dict({key.replace("norm.", ""): value for key, value in state_dict.items() if key.startswith("norm.")})
    model.head.load_state_dict({key.replace("head.", ""): value for key, value in state_dict.items() if key.startswith("head.")})

    model.eval()
    return model


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
        dynamo=False,
    )

    import onnx

    exported = onnx.load(str(onnx_path))
    onnx.save(onnx.shape_inference.infer_shapes(exported), str(onnx_path))


def build_calibration_samples(vocab_size: int, sample_count: int) -> list[torch.Tensor]:
    samples: list[torch.Tensor] = []
    for _ in range(sample_count):
        token_id = torch.randint(low=0, high=vocab_size, size=(1, 1), dtype=torch.long)
        one_hot = F.one_hot(token_id, num_classes=vocab_size).to(torch.float32)
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
    from esp_ppq.parser.espdl import layout_patterns
    from esp_ppq.quantization.quantizer.EspdlQuantizer import BaseEspdlQuantizer
    from esp_ppq.quantization.optim.refine import QuantAlignmentPass
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

    original_align_to_first_output = QuantAlignmentPass.align_to_first_output

    def _align_to_first_output_safe(self, op):
        if len(op.config.output_quantization_config) < 2 or len(op.config.input_quantization_config) <= 5:
            return op.config.output_quantization_config[0]
        return original_align_to_first_output(self, op)

    QuantAlignmentPass.align_to_first_output = _align_to_first_output_safe

    original_axis_export = layout_patterns.AxisTransformPattern.export

    def _axis_export_with_keepdims_default(self, op, graph, **kwargs):
        if op.type in layout_patterns.REDUCE_OP_SET and "keepdims" not in op.attributes:
            op.attributes["keepdims"] = 1
        return original_axis_export(self, op, graph, **kwargs)

    layout_patterns.AxisTransformPattern.export = _axis_export_with_keepdims_default

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
    set_seed(args.seed)

    checkpoint_path = Path(args.checkpoint)
    onnx_path = Path(args.onnx_path)
    espdl_path = Path(args.espdl_path)

    checkpoint = load_checkpoint(checkpoint_path)
    model = build_model_from_checkpoint(
        checkpoint,
        equivalent_unrolled_lstm=args.equivalent_unrolled_lstm,
        equivalent_random_weights=args.equivalent_random_weights,
    )
    vocab_size = model.vocab_size

    export_onnx(model, onnx_path, vocab_size=vocab_size, opset=args.opset)
    export_espdl(
        onnx_path=onnx_path,
        espdl_path=espdl_path,
        vocab_size=vocab_size,
        calib_samples=args.calib_samples,
        calib_batch_size=args.calib_batch_size,
    )

    summary_path = espdl_path.with_suffix(".json")
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "checkpoint": str(checkpoint_path),
                "onnx_path": str(onnx_path),
                "espdl_path": str(espdl_path),
                "vocab_size": vocab_size,
                "embed_dim": model.embed_dim,
                "hidden_dim": model.hidden_dim,
                "num_layers": model.num_layers,
                "dropout": model.dropout,
                "equivalent_unrolled_lstm": bool(args.equivalent_unrolled_lstm),
                "equivalent_random_weights": bool(args.equivalent_random_weights),
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