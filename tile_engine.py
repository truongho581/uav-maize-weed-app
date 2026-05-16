"""
tile_engine.py — Cắt ảnh lớn thành tile 640×640 và ghép kết quả lại
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

import cv2
import numpy as np


@dataclass
class Tile:
    """Đại diện cho 1 tile đã cắt từ ảnh gốc."""
    image_bgr: np.ndarray          # Dữ liệu ảnh tile (H_tile × W_tile × 3)
    row: int                        # Vị trí hàng trong grid tile
    col: int                        # Vị trí cột trong grid tile
    x_start: int                    # Toạ độ x trong ảnh gốc
    y_start: int                    # Toạ độ y trong ảnh gốc
    x_end: int
    y_end: int
    # Kết quả AI sẽ gán sau
    crop_mask: Optional[np.ndarray] = field(default=None)
    weed_mask: Optional[np.ndarray] = field(default=None)
    per_stage_masks: Optional[Dict[int, np.ndarray]] = field(default=None)


class TileEngine:
    """
    Cắt ảnh lớn thành nhiều tile nhỏ 640×640 và ghép mask lại sau khi chạy AI.

    Args:
        tile_size: Kích thước mỗi tile (mặc định 640)
        overlap:   Số pixel overlap giữa các tile (để tránh mất thông tin ở biên)
    """

    def __init__(self, tile_size: int = 640, overlap: int = 64):
        self.tile_size = tile_size
        self.overlap = overlap
        self.stride = tile_size - overlap

    # ------------------------------------------------------------------
    def split_image(self, image_bgr: np.ndarray) -> List[Tile]:
        """
        Cắt ảnh thành danh sách các Tile.

        Args:
            image_bgr: Ảnh gốc (H × W × 3)

        Returns:
            Danh sách Tile objects
        """
        H, W = image_bgr.shape[:2]

        def _starts(length: int) -> List[int]:
            if length <= self.tile_size:
                return [0]
            starts = list(range(0, max(length - self.tile_size, 0) + 1, self.stride))
            last = length - self.tile_size
            if starts[-1] != last:
                starts.append(last)
            return starts

        tiles = []
        for row, y_start in enumerate(_starts(H)):
            y_end = min(y_start + self.tile_size, H)
            for col, x_start in enumerate(_starts(W)):
                x_end = min(x_start + self.tile_size, W)
                tile_img = image_bgr[y_start:y_end, x_start:x_end]

                if tile_img.shape[:2] != (self.tile_size, self.tile_size):
                    padded = np.zeros((self.tile_size, self.tile_size, 3), dtype=image_bgr.dtype)
                    h, w = tile_img.shape[:2]
                    padded[:h, :w] = tile_img
                    tile_img = padded

                tiles.append(Tile(
                    image_bgr=tile_img,
                    row=row, col=col,
                    x_start=x_start, y_start=y_start,
                    x_end=x_end, y_end=y_end,
                ))

        return tiles

    # ------------------------------------------------------------------
    def stitch_masks(
        self,
        tiles: List[Tile],
        original_shape: Tuple[int, int],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Ghép các mask từ tile thành mask kích thước ảnh gốc.
        Dùng blending với weight matrix để xử lý vùng overlap.

        Args:
            tiles:          Danh sách Tile (đã có crop_mask, weed_mask)
            original_shape: (H, W) của ảnh gốc

        Returns:
            (crop_mask_full, weed_mask_full): cả hai dtype bool
        """
        H, W = original_shape
        crop_acc = np.zeros((H, W), dtype=np.float32)
        weed_acc = np.zeros((H, W), dtype=np.float32)
        weight_acc = np.zeros((H, W), dtype=np.float32)

        # Weight: gaussian-like (cao ở giữa, thấp ở biên) để blend overlap mượt
        weight_kernel = self._make_weight_kernel(self.tile_size)

        for tile in tiles:
            if tile.crop_mask is None or tile.weed_mask is None:
                continue

            ys, ye = tile.y_start, tile.y_end
            xs, xe = tile.x_start, tile.x_end

            rh, rw = ye - ys, xe - xs
            if rh <= 0 or rw <= 0:
                continue

            # Tile mask phải đúng kích thước tile_size × tile_size
            crop_m = tile.crop_mask.astype(np.float32)
            weed_m = tile.weed_mask.astype(np.float32)

            if crop_m.shape != (self.tile_size, self.tile_size):
                crop_m = cv2.resize(crop_m, (self.tile_size, self.tile_size))
            if weed_m.shape != (self.tile_size, self.tile_size):
                weed_m = cv2.resize(weed_m, (self.tile_size, self.tile_size))

            crop_acc[ys:ye, xs:xe] += crop_m[:rh, :rw] * weight_kernel[:rh, :rw]
            weed_acc[ys:ye, xs:xe] += weed_m[:rh, :rw] * weight_kernel[:rh, :rw]
            weight_acc[ys:ye, xs:xe] += weight_kernel[:rh, :rw]

        # Normalize
        eps = 1e-6
        weight_safe = np.where(weight_acc < eps, 1.0, weight_acc)
        crop_norm = crop_acc / weight_safe
        weed_norm = weed_acc / weight_safe

        return (crop_norm > 0.5), (weed_norm > 0.5)

    # ------------------------------------------------------------------
    @staticmethod
    def _make_weight_kernel(size: int) -> np.ndarray:
        """Tạo ma trận weight dạng pyramid: cao ở giữa, thấp ở biên."""
        k = np.ones((size, size), dtype=np.float32)
        margin = size // 8
        # Nhân margin: biên thấp hơn
        k[:margin, :]  *= 0.5
        k[-margin:, :] *= 0.5
        k[:, :margin]  *= 0.5
        k[:, -margin:] *= 0.5
        return k

    # ------------------------------------------------------------------
    def stitch_colored_overlay(
        self,
        original_bgr: np.ndarray,
        full_crop_mask: np.ndarray,
        full_weed_mask: np.ndarray,
        alpha: float = 0.5,
    ) -> np.ndarray:
        """Tạo ảnh overlay màu từ mask đã ghép."""
        from ai_core import CLASS_COLORS_BGR, IDX_CROP, IDX_WEED

        overlay = original_bgr.copy()
        colored = np.zeros_like(original_bgr)
        colored[full_crop_mask] = CLASS_COLORS_BGR[IDX_CROP]
        colored[full_weed_mask] = CLASS_COLORS_BGR[IDX_WEED]

        mask_any = full_crop_mask | full_weed_mask
        if mask_any.any():
            blended = cv2.addWeighted(original_bgr, 1 - alpha, colored, alpha, 0)
            overlay[mask_any] = blended[mask_any]

        return overlay

    # ------------------------------------------------------------------
    def count_tiles(self, image_bgr: np.ndarray) -> int:
        """Ước tính số tile mà không cắt thực sự (dùng cho progress bar)."""
        H, W = image_bgr.shape[:2]
        rows = 1 if H <= self.tile_size else int(np.ceil((H - self.tile_size) / self.stride)) + 1
        cols = 1 if W <= self.tile_size else int(np.ceil((W - self.tile_size) / self.stride)) + 1
        return rows * cols
