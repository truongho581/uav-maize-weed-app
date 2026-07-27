#!/usr/bin/env python3
"""Export a registered PyTorch semantic checkpoint and validate it with ONNX Runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from uav_crop_analysis.errors import DependencyUnavailableError
from uav_crop_analysis.inference import ModelRegistry
from uav_crop_analysis.inference.registry import sha256_file
from uav_crop_analysis.inference.torch_semantic import (
    TorchSemanticSegmenter,
    logits_from_output,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_id")
    parser.add_argument("artifact_role")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--registry",
        type=Path,
        default=PROJECT_ROOT / "models/model_inventory.json",
    )
    parser.add_argument("--opset", type=int, default=17)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        import onnx
        import onnxruntime as ort
        import torch
    except ImportError as exc:
        raise DependencyUnavailableError(
            "ONNX export requires installation with the 'onnx' extra"
        ) from exc

    registry = ModelRegistry.from_file(args.registry)
    resolved = registry.resolve(args.model_id, args.artifact_role)
    segmenter = TorchSemanticSegmenter.load(resolved, device="cpu")
    height, width = resolved.manifest.input_size_hw

    class ExportWrapper(torch.nn.Module):
        def __init__(self, model: torch.nn.Module) -> None:
            super().__init__()
            self.model = model

        def forward(self, images: torch.Tensor) -> torch.Tensor:
            return logits_from_output(self.model(images), (height, width))

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    wrapper = ExportWrapper(segmenter.model).eval()
    dummy = torch.zeros((1, 3, height, width), dtype=torch.float32)
    torch.onnx.export(
        wrapper,
        (dummy,),
        output,
        input_names=["images"],
        output_names=["logits"],
        opset_version=args.opset,
        dynamo=False,
    )
    model = onnx.load(output)
    onnx.checker.check_model(model)
    session = ort.InferenceSession(str(output), providers=["CPUExecutionProvider"])
    result = session.run(None, {"images": np.zeros((1, 3, height, width), dtype=np.float32)})
    expected_shape = (1, len(resolved.manifest.class_names), height, width)
    if not result or result[0].shape != expected_shape:
        raise RuntimeError(f"unexpected ONNX output shape: {result[0].shape if result else None}")
    print(
        json.dumps(
            {
                "path": str(output),
                "sha256": sha256_file(output),
                "format": "onnx",
                "opset": args.opset,
                "input_shape": [1, 3, height, width],
                "output_shape": list(result[0].shape),
                "validated_with": "onnx.checker+onnxruntime",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
