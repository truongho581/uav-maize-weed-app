#!/usr/bin/env python3
"""Run one real image through the persisted Phase 4 worker pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from uav_crop_analysis.adapters import SQLiteAnalysisJobRepository
from uav_crop_analysis.jobs import (
    AnalysisInput,
    AnalysisJobConfig,
    AnalysisJobService,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--model-id", default="segformer-b0-v72-loso")
    parser.add_argument("--artifact-role", default="best_test_D1_seed_42")
    parser.add_argument(
        "--registry",
        type=Path,
        default=PROJECT_ROOT / "models/model_inventory.json",
    )
    parser.add_argument("--database", type=Path)
    parser.add_argument("--device", default="cpu")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = args.output_root.expanduser().resolve()
    database = args.database or output_root / "phase4-smoke.db"
    config = AnalysisJobConfig(
        mission_id="phase4-smoke",
        model_id=args.model_id,
        artifact_role=args.artifact_role,
        registry_path=args.registry,
        inputs=(AnalysisInput("smoke-image", args.image),),
        output_root=output_root,
        device=args.device,
        tile_size=640,
        overlap=64,
    )
    repository = SQLiteAnalysisJobRepository(database)
    service = AnalysisJobService(repository)
    job = service.submit(config)
    started = perf_counter()
    service.start(job.job_id)
    completed = service.wait(job.job_id, timeout=180)
    elapsed_ms = (perf_counter() - started) * 1000.0
    print(
        json.dumps(
            {
                "job_id": completed.job_id,
                "status": completed.status.value,
                "attempt": completed.attempt,
                "elapsed_ms": round(elapsed_ms, 3),
                "event_count": len(repository.list_events(completed.job_id)),
                "artifact_dir": (
                    str(completed.result.artifact_dir) if completed.result else None
                ),
                "manifest_sha256": (
                    completed.result.manifest_sha256 if completed.result else None
                ),
                "error": completed.error.code if completed.error else None,
            },
            indent=2,
        )
    )
    return 0 if completed.result is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
