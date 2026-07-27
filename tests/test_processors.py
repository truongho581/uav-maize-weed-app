import numpy as np

from uav_crop_analysis.application import summarize_maize_instances, summarize_weed_mask
from uav_crop_analysis.inference import (
    InstanceBatchPrediction,
    InstancePrediction,
    PredictionProvenance,
)


def _two_plant_mask() -> np.ndarray:
    mask = np.zeros((100, 100), dtype=bool)
    mask[10:20, 10:20] = True
    mask[50:60, 50:60] = True
    return mask


def _provenance() -> PredictionProvenance:
    return PredictionProvenance("model", "1", "best", "0" * 64, "test", "cpu", "pre")


def test_maize_metrics_use_instances_and_image_footprint_for_density() -> None:
    masks = (_two_plant_mask(), np.flip(_two_plant_mask(), axis=1).copy())
    prediction = InstanceBatchPrediction(
        image_size_hw=(100, 100),
        instances=tuple(
            InstancePrediction(index, stage, 0.9, (0, 0, 99, 99), mask)
            for index, (stage, mask) in enumerate(zip(("maize2", "maize4"), masks))
        ),
        provenance=_provenance(),
        latency_ms=1.0,
    )

    result = summarize_maize_instances(prediction, gsd_cm_per_px=1.0)

    assert result.instance_count == 2
    assert result.footprint_area_m2 == 1.0
    assert result.density_per_m2 == 2.0
    assert result.stage_counts == {"maize2": 1, "maize4": 1}


def test_weed_metrics_treat_weed_as_semantic_grid_regions() -> None:
    weed_mask = np.zeros((100, 100), dtype=bool)
    weed_mask[0:20, 0:20] = True
    result = summarize_weed_mask(
        weed_mask,
        gsd_cm_per_px=1.0,
        grid_shape=(2, 2),
        high_risk_threshold=0.1,
    )

    assert result.coverage_percent == 4.0
    assert result.area_m2 == 0.04
    assert sum(cell.high_risk for cell in result.cells) == 1
