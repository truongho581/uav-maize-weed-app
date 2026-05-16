"""
weed_processor.py — Xử lý hậu kỳ: Phân tích cỏ dại
Nhận weed_mask & crop_mask từ AI → trả về các chỉ số về cỏ dại
"""

import cv2
import numpy as np
from typing import Optional, List, Dict, Any, Tuple


# Ngưỡng đánh giá mức độ cạnh tranh
COMPETITION_THRESHOLDS = {
    "thap":       (0.0,  0.20),   # ratio cỏ/cây < 0.2 → Thấp (an toàn)
    "trung_binh": (0.20, 0.50),   # 0.2 - 0.5 → Trung bình (cần theo dõi)
    "cao":        (0.50, 1.00),   # 0.5 - 1.0 → Cao (cần can thiệp)
    "rat_cao":    (1.00, 9999.),  # > 1.0 → Rất cao (khẩn cấp)
}

ZONE_GRID_N = 4  # Chia ảnh thành lưới N×N để tìm vùng nguy hiểm


class WeedProcessor:
    """
    Phân tích cỏ dại từ binary mask.

    Các chỉ số tính được:
    - Độ phủ cỏ (%)
    - Tỷ lệ cỏ / cây (chỉ số cạnh tranh)
    - Vùng có mật độ cỏ cao (heatmap)
    - Phân loại mức độ nguy hiểm
    """

    def __init__(
        self,
        min_weed_area_px: int = 100,   # Diện tích tối thiểu 1 vùng cỏ
        zone_grid: int = ZONE_GRID_N,  # Lưới phân tích vùng nguy hiểm
        high_density_threshold: float = 0.35,  # % cỏ/ô > này → vùng nguy hiểm
    ):
        self.min_weed_area_px = min_weed_area_px
        self.zone_grid = zone_grid
        self.high_density_threshold = high_density_threshold

    # ------------------------------------------------------------------
    def analyze(
        self,
        weed_mask: np.ndarray,
        crop_mask: Optional[np.ndarray] = None,
        gsd_cm_per_px: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Phân tích đầy đủ cỏ dại.

        Args:
            weed_mask:      Binary mask cỏ dại (H, W) bool
            crop_mask:      Binary mask cây trồng (optional, để tính tỷ lệ)
            gsd_cm_per_px:  GSD để tính m² (optional)

        Returns:
            dict:
            {
                'do_phu_co_phan_tram':     float  — % pixel cỏ / tổng ảnh
                'ty_le_co_tren_cay':       float  — ratio cỏ/cây pixel
                'muc_do_canh_tranh':       str    — 'thap'/'trung_binh'/'cao'/'rat_cao'
                'so_vung_co':              int    — số vùng cỏ tách rời
                'dien_tich_co_m2':         float  — diện tích cỏ m² (None nếu ko GSD)
                'vung_nguy_hiem':          list   — list {row, col, density, bbox}
                'heatmap':                 np.ndarray — heatmap mật độ cỏ (H,W) float
                'weed_contours':           list   — contours cỏ
                'cay_bi_bao_vay':          int    — số cây bị cỏ bao xung quanh
            }
        """
        H, W = weed_mask.shape[:2]
        total_pixels = H * W

        # --- 1. Độ phủ cỏ ---
        weed_pixels = int(weed_mask.sum())
        do_phu_co = 100.0 * weed_pixels / total_pixels if total_pixels > 0 else 0.0

        # --- 2. Tỷ lệ cỏ/cây ---
        ty_le_co_cay = 0.0
        if crop_mask is not None:
            crop_pixels = int(crop_mask.sum())
            if crop_pixels > 0:
                ty_le_co_cay = weed_pixels / crop_pixels

        # --- 3. Mức độ cạnh tranh ---
        muc_do = self._classify_competition(ty_le_co_cay)

        # --- 4. Contours cỏ ---
        weed_contours, weed_areas = self._find_weed_contours(weed_mask)
        so_vung_co = len(weed_contours)

        # --- 5. Tính m² ---
        dien_tich_co_m2 = None
        if gsd_cm_per_px is not None and gsd_cm_per_px > 0:
            px2_per_m2 = (100.0 / gsd_cm_per_px) ** 2
            dien_tich_co_m2 = weed_pixels / px2_per_m2

        # --- 6. Phân tích vùng nguy hiểm (grid analysis) ---
        vung_nguy_hiem, heatmap = self._analyze_danger_zones(weed_mask)

        # --- 7. Cây bị bao vây (overlap với cỏ xung quanh) ---
        cay_bi_bao_vay = 0
        if crop_mask is not None:
            cay_bi_bao_vay = self._count_surrounded_plants(crop_mask, weed_mask)

        return {
            "do_phu_co_phan_tram": round(do_phu_co, 2),
            "ty_le_co_tren_cay": round(ty_le_co_cay, 3),
            "muc_do_canh_tranh": muc_do,
            "so_vung_co": so_vung_co,
            "dien_tich_co_m2": round(dien_tich_co_m2, 2) if dien_tich_co_m2 else None,
            "vung_nguy_hiem": vung_nguy_hiem,
            "heatmap": heatmap,
            "weed_contours": weed_contours,
            "cay_bi_bao_vay": cay_bi_bao_vay,
        }

    # ------------------------------------------------------------------
    def draw_analysis(
        self,
        canvas: np.ndarray,
        analysis: Dict[str, Any],
        show_contours: bool = True,
        show_danger_zones: bool = True,
        show_heatmap: bool = False,
        heatmap_alpha: float = 0.55,
    ) -> np.ndarray:
        """Vẽ kết quả phân tích cỏ lên canvas BGR."""
        out = canvas.copy()

        if show_contours and analysis["weed_contours"]:
            cv2.drawContours(out, analysis["weed_contours"], -1, (0, 0, 255), 2)

        if show_danger_zones:
            H, W = out.shape[:2]
            gh = H // self.zone_grid
            gw = W // self.zone_grid
            for zone in analysis["vung_nguy_hiem"]:
                r, c = zone["row"], zone["col"]
                x1 = c * gw
                y1 = r * gh
                x2 = min(x1 + gw, W)
                y2 = min(y1 + gh, H)
                density = zone["density"]
                # Màu theo mức độ: vàng → đỏ
                intensity = min(int(density * 500), 255)
                color = (0, 255 - intensity, 255)
                cv2.rectangle(out, (x1, y1), (x2, y2), color, 3)
                cv2.putText(
                    out, f"Co: {density*100:.0f}%",
                    (x1 + 5, y1 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
                )

        if show_heatmap and analysis["heatmap"] is not None:
            hm = analysis["heatmap"].astype(np.float32)
            hm_resized = cv2.resize(
                hm, (out.shape[1], out.shape[0]), interpolation=cv2.INTER_NEAREST)
            scale = max(float(self.high_density_threshold), 1e-6)
            hm_norm = (np.clip(hm_resized / scale, 0.0, 1.0) * 255).astype(np.uint8)
            hm_color = cv2.applyColorMap(hm_norm, cv2.COLORMAP_TURBO)

            active = hm_resized > 0.001
            if active.any():
                alpha = (0.18 + 0.37 * (hm_norm.astype(np.float32) / 255.0))
                alpha = np.minimum(alpha, heatmap_alpha)
                alpha = (alpha * active.astype(np.float32))[..., None]
                hm_color = np.maximum(hm_color, out)
                out = (out.astype(np.float32) * (1.0 - alpha)
                       + hm_color.astype(np.float32) * alpha).astype(np.uint8)

        return out

    # ------------------------------------------------------------------
    def _classify_competition(self, ratio: float) -> str:
        for label, (lo, hi) in COMPETITION_THRESHOLDS.items():
            if lo <= ratio < hi:
                return label
        return "rat_cao"

    def _find_weed_contours(self, weed_mask: np.ndarray):
        mask_u8 = weed_mask.astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        cleaned = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, kernel, iterations=1)
        contours_raw, _ = cv2.findContours(
            cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        contours, areas = [], []
        for cnt in contours_raw:
            area = cv2.contourArea(cnt)
            if area >= self.min_weed_area_px:
                contours.append(cnt)
                areas.append(area)
        return contours, areas

    def _analyze_danger_zones(
        self, weed_mask: np.ndarray
    ) -> Tuple[List[Dict], np.ndarray]:
        """Chia ảnh thành grid và tính mật độ cỏ trong mỗi ô."""
        H, W = weed_mask.shape
        gh = max(1, H // self.zone_grid)
        gw = max(1, W // self.zone_grid)
        heatmap = np.zeros((self.zone_grid, self.zone_grid), dtype=np.float32)
        danger_zones = []

        for r in range(self.zone_grid):
            for c in range(self.zone_grid):
                y1 = r * gh
                y2 = min(y1 + gh, H)
                x1 = c * gw
                x2 = min(x1 + gw, W)
                cell = weed_mask[y1:y2, x1:x2]
                density = float(cell.sum()) / max(cell.size, 1)
                heatmap[r, c] = density
                if density >= self.high_density_threshold:
                    danger_zones.append({
                        "row": r, "col": c,
                        "density": round(density, 3),
                        "bbox": (x1, y1, x2 - x1, y2 - y1),
                    })

        return danger_zones, heatmap

    def _count_surrounded_plants(
        self, crop_mask: np.ndarray, weed_mask: np.ndarray, dilation_px: int = 20
    ) -> int:
        """Đếm số cây bị cỏ bao xung quanh (weed dilated overlap with crop)."""
        kernel = np.ones((dilation_px, dilation_px), np.uint8)
        weed_dilated = cv2.dilate(weed_mask.astype(np.uint8), kernel, iterations=1) > 0
        # Tìm contours cây
        crop_u8 = crop_mask.astype(np.uint8) * 255
        contours, _ = cv2.findContours(crop_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        count = 0
        for cnt in contours:
            M = cv2.moments(cnt)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                # Tạo mask nhỏ quanh cây để kiểm tra overlap
                x, y, w, h = cv2.boundingRect(cnt)
                pad = dilation_px
                ys = max(0, y - pad)
                ye = min(crop_mask.shape[0], y + h + pad)
                xs = max(0, x - pad)
                xe = min(crop_mask.shape[1], x + w + pad)
                region_crop = crop_mask[ys:ye, xs:xe]
                region_weed_d = weed_dilated[ys:ye, xs:xe]
                # Nếu vùng xung quanh cây có > 30% là cỏ → bị bao vây
                if region_crop.sum() > 0:
                    surround = region_weed_d & ~region_crop
                    surround_ratio = surround.sum() / max(region_crop.sum(), 1)
                    if surround_ratio > 0.3:
                        count += 1
        return count
