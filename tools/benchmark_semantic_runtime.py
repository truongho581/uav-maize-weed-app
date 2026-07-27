#!/usr/bin/env python3
"""Benchmark one registered semantic checkpoint in an isolated process."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
from time import perf_counter

import numpy as np
from PIL import Image

from uav_crop_analysis.inference import ImageInput, ModelRegistry
from uav_crop_analysis.inference.torch_semantic import TorchSemanticSegmenter


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_id")
    parser.add_argument("artifact_role")
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "--registry",
        type=Path,
        default=PROJECT_ROOT / "models/model_inventory.json",
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--repeat", type=int, default=1)
    return parser.parse_args()


def max_rss_mb() -> float:
    try:
        import resource
    except ImportError:
        try:
            import psutil
        except ImportError:
            return 0.0
        return float(psutil.Process().memory_info().rss) / (1024.0 * 1024.0)
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    divisor = 1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0
    return value / divisor


def main() -> int:
    args = parse_args()
    if args.repeat < 1:
        raise ValueError("repeat must be positive")
    registry = ModelRegistry.from_file(args.registry)
    resolved = registry.resolve(args.model_id, args.artifact_role)
    image = ImageInput(np.asarray(Image.open(args.image).convert("RGB"), dtype=np.uint8))
    baseline_rss = max_rss_mb()
    started = perf_counter()
    segmenter = TorchSemanticSegmenter.load(resolved, device=args.device)
    load_ms = (perf_counter() - started) * 1000.0
    latencies = [segmenter.predict(image).latency_ms for _ in range(args.repeat)]
    peak_rss = max_rss_mb()
    print(
        json.dumps(
            {
                "model_id": args.model_id,
                "artifact_role": args.artifact_role,
                "device": str(segmenter.device),
                "image_size_hw": image.size_hw,
                "load_ms": round(load_ms, 3),
                "prediction_median_ms": round(statistics.median(latencies), 3),
                "prediction_samples_ms": [round(value, 3) for value in latencies],
                "process_peak_rss_mb": round(peak_rss, 3),
                "process_peak_delta_mb": round(max(0.0, peak_rss - baseline_rss), 3),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
