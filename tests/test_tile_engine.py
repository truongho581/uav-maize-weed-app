import numpy as np

from uav_crop_analysis.jobs.pipeline import blend_weight_kernel, tile_windows


def test_split_image_covers_edges_without_padding_the_original() -> None:
    windows = tile_windows(900, 1000, tile_size=640, overlap=64)

    assert len(windows) == 4
    assert windows == (
        (0, 0, 640, 640),
        (360, 0, 1000, 640),
        (0, 260, 640, 900),
        (360, 260, 1000, 900),
    )


def test_blend_kernel_is_positive_and_prefers_tile_center() -> None:
    kernel = blend_weight_kernel(640)

    assert kernel.shape == (640, 640)
    assert kernel.dtype == np.float32
    assert kernel.min() > 0
    assert kernel[320, 320] > kernel[0, 0]
