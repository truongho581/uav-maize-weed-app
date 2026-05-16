"""
crop_processor.py — Xử lý hậu kỳ: Phân tích cây trồng (Maize)
Nhận crop_mask từ AI → trả về các chỉ số hình học/diện tích về cây trồng.

Các chỉ số màu RGB và chỉ số cần camera đa phổ không còn được dùng trong
pipeline chính để tránh diễn giải quá mức từ ảnh RGB thông thường.
"""

import cv2
import numpy as np
from typing import Optional, List, Dict, Any, Tuple


# ──────────────────────────────────────────────────────────────────
# Ngưỡng phân loại dinh dưỡng (có thể chỉnh)
# ──────────────────────────────────────────────────────────────────
GLI_HEALTHY_MIN   = 0.10   # GLI >= ngưỡng này → cây khỏe (xanh đậm)
GLI_WARNING_MIN   = 0.04   # 0.04 <= GLI < 0.10 → nghi thiếu dinh dưỡng
# GLI < 0.04 → stress nặng / vàng lá

VARI_STRESS_MAX   = 0.10   # VARI < ngưỡng → có khả năng stress nước/nhiệt

EXG_STRESS_MIN    = 0.05   # ExG < ngưỡng → stress (đã có từ trước)


class CropProcessor:
    """
    Phân tích cây trồng từ binary mask.

    Các chỉ số tính được:
    - Độ phủ tán cây (%)
    - Số cây ước tính (findContours)
    - Mật độ cây (cây/m²) — cần GSD
    - Danh sách cây kém phát triển
    - Diện tích tán cây (m²) — cần GSD
    - Phân tích từng cây riêng lẻ vẫn được giữ như hàm phụ, không dùng trong UI chính
    """

    def __init__(
        self,
        min_plant_area_px: int = 200,        # Diện tích tối thiểu 1 cây (pixel²)
        underdeveloped_ratio: float = 0.40,   # Cây nhỏ hơn ratio*mean → kém phát triển
        morph_kernel_size: int = 5,           # Kernel morphological operations
    ):
        self.min_plant_area_px    = min_plant_area_px
        self.underdeveloped_ratio = underdeveloped_ratio
        self.morph_kernel_size    = morph_kernel_size

    # ──────────────────────────────────────────────────────────────
    def analyze(
        self,
        crop_mask: np.ndarray,
        original_bgr: Optional[np.ndarray] = None,
        gsd_cm_per_px: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Phân tích đầy đủ cây trồng.

        Args:
            crop_mask:      Binary mask cây ngô (H, W) bool
            original_bgr:   Ảnh gốc (H, W, 3) BGR — dùng tính chỉ số màu, optional
            gsd_cm_per_px:  Ground Sample Distance cm/pixel — để tính m², optional

        Returns:
            dict với các chỉ số:
            {
                'do_phu_phan_tram'   : float  — % pixel cây / tổng ảnh
                'so_cay_uoc_tinh'   : int    — số cây ước tính
                'dien_tich_tan_px2' : int    — tổng diện tích pixel
                'dien_tich_tan_m2'  : float  — tổng diện tích m² (None nếu ko có GSD)
                'mat_do_m2'         : float  — cây/m² (None nếu ko có GSD)
                'so_cay_kem_pt'     : int    — số cây kém phát triển (diện tích nhỏ)
                'cay_kem_pt_bboxes' : list   — bbox [x,y,w,h] của cây kém PT
                'contours'          : list   — contour objects (dùng vẽ)
                'contour_areas'     : list   — diện tích từng cây (px²)
                'mean_plant_area_px': float  — diện tích trung bình 1 cây
                'exg_mean'          : float  — ExG trung bình vùng cây
                'gli_mean'          : float  — GLI trung bình vùng cây
                'vari_mean'         : float  — VARI trung bình vùng cây
                'rg_ratio_mean'     : float  — R/G ratio trung bình
                'stress_detected'   : bool   — phát hiện stress (ExG thấp)
                'nutrition_status'  : str    — "Khỏe mạnh" / "Nghi thiếu DD" / "Stress nặng"
            }
        """
        H, W = crop_mask.shape[:2]
        total_pixels = H * W

        # --- 1. Độ phủ tán ---
        crop_pixels = int(crop_mask.sum())
        do_phu_phan_tram = 100.0 * crop_pixels / total_pixels if total_pixels > 0 else 0.0

        # --- 2. Morphological để tách cây dính ---
        cleaned_mask = self._morphological_separation(crop_mask)

        # --- 3. findContours để đếm cây ---
        contours, areas, bboxes = self._find_plant_contours(cleaned_mask)

        so_cay    = len(contours)
        mean_area = float(np.mean(areas)) if areas else 0.0

        # --- 4. Cây kém phát triển (diện tích < ratio * mean) ---
        kem_pt_bboxes = []
        kem_pt_count  = 0
        for area, bbox in zip(areas, bboxes):
            if mean_area > 0 and area < self.underdeveloped_ratio * mean_area:
                kem_pt_bboxes.append(bbox)
                kem_pt_count += 1

        # --- 5. Tính m² nếu có GSD ---
        dien_tich_m2 = None
        mat_do_m2    = None
        if gsd_cm_per_px is not None and gsd_cm_per_px > 0:
            px2_per_m2 = (100.0 / gsd_cm_per_px) ** 2
            dien_tich_m2 = crop_pixels / px2_per_m2
            if dien_tich_m2 > 0:
                mat_do_m2 = so_cay / dien_tich_m2

        return {
            "do_phu_phan_tram":    round(do_phu_phan_tram, 2),
            "so_cay_uoc_tinh":     so_cay,
            "dien_tich_tan_px2":   crop_pixels,
            "dien_tich_tan_m2":    round(dien_tich_m2, 2) if dien_tich_m2 else None,
            "mat_do_m2":           round(mat_do_m2, 2) if mat_do_m2 else None,
            "so_cay_kem_pt":       kem_pt_count,
            "cay_kem_pt_bboxes":   kem_pt_bboxes,
            "contours":            contours,
            "contour_areas":       areas,
            "mean_plant_area_px":  round(mean_area, 1),
        }

    # ──────────────────────────────────────────────────────────────
    def analyze_nutrition_per_plant(
        self,
        crop_mask: np.ndarray,
        original_bgr: np.ndarray,
    ) -> List[Dict[str, Any]]:
        """
        Phân tích dinh dưỡng từng cây riêng lẻ.
        Trả về danh sách, mỗi phần tử là một cây với:
            {
                'plant_id'         : int
                'bbox'             : [x, y, w, h]
                'area_px'          : int
                'centroid'         : (cx, cy)
                'gli'              : float
                'exg'              : float
                'vari'             : float
                'hsv_hue_mean'     : float   — Hue TB (0-180 OpenCV)
                'hsv_sat_mean'     : float   — Saturation TB
                'trang_thai'       : str     — "Khỏe mạnh" / "Nghi thiếu DD" / "Stress nặng"
                'contour'          : ndarray
            }
        """
        cleaned_mask = self._morphological_separation(crop_mask)
        contours, areas, bboxes = self._find_plant_contours(cleaned_mask)

        H, W = original_bgr.shape[:2]
        img_f = original_bgr.astype(np.float32) / 255.0
        B_ch  = img_f[:, :, 0]
        G_ch  = img_f[:, :, 1]
        R_ch  = img_f[:, :, 2]
        img_hsv = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)

        results = []
        for pid, (cnt, area, bbox) in enumerate(zip(contours, areas, bboxes)):
            # Tạo mask riêng cho từng cây
            plant_mask = np.zeros((H, W), dtype=np.uint8)
            cv2.drawContours(plant_mask, [cnt], -1, 255, -1)
            pm = plant_mask > 0

            if pm.sum() == 0:
                continue

            # Tính các chỉ số màu
            g = G_ch[pm]; r = R_ch[pm]; b = B_ch[pm]

            exg_vals  = 2.0 * g - r - b
            gli_denom = 2.0 * g + r + b
            gli_vals  = np.where(gli_denom > 1e-6, (2.0 * g - r - b) / gli_denom, 0.0)
            vari_denom = g + r - b
            vari_vals  = np.where(np.abs(vari_denom) > 1e-6, (g - r) / vari_denom, 0.0)

            exg_mean  = float(np.mean(exg_vals))
            gli_mean  = float(np.mean(gli_vals))
            vari_mean = float(np.mean(vari_vals))
            hue_mean  = float(np.mean(img_hsv[:, :, 0][pm]))
            sat_mean  = float(np.mean(img_hsv[:, :, 1][pm]))

            trang_thai = self._classify_nutrition(gli_mean, exg_mean)

            # Centroid
            M = cv2.moments(cnt)
            cx = int(M["m10"] / M["m00"]) if M["m00"] > 0 else bbox[0] + bbox[2] // 2
            cy = int(M["m01"] / M["m00"]) if M["m00"] > 0 else bbox[1] + bbox[3] // 2

            results.append({
                "plant_id":     pid + 1,
                "bbox":         bbox,
                "area_px":      int(area),
                "centroid":     (cx, cy),
                "gli":          round(gli_mean, 3),
                "exg":          round(exg_mean, 3),
                "vari":         round(vari_mean, 3),
                "hsv_hue_mean": round(hue_mean, 1),
                "hsv_sat_mean": round(sat_mean, 1),
                "trang_thai":   trang_thai,
                "contour":      cnt,
            })

        return results

    # ──────────────────────────────────────────────────────────────
    def draw_nutrition_heatmap(
        self,
        canvas: np.ndarray,
        per_plant_results: List[Dict[str, Any]],
        index: str = "gli",
        alpha: float = 0.55,
    ) -> np.ndarray:
        """
        Vẽ heatmap dinh dưỡng lên ảnh dựa trên chỉ số đã chọn.

        Args:
            canvas:             Ảnh BGR gốc
            per_plant_results:  Kết quả từ analyze_nutrition_per_plant()
            index:              'gli' | 'exg' | 'vari' (chỉ số dùng làm nhiệt)
            alpha:              Độ trong suốt overlay

        Returns:
            Ảnh BGR với heatmap màu nhiệt
        """
        out     = canvas.copy()
        H, W    = canvas.shape[:2]
        heat_map = np.zeros((H, W), dtype=np.float32)
        count_map = np.zeros((H, W), dtype=np.float32)

        if not per_plant_results:
            return out

        # Lấy min/max để normalize
        vals = [p[index] for p in per_plant_results if index in p]
        if not vals:
            return out
        v_min, v_max = min(vals), max(vals)
        v_range = v_max - v_min if v_max != v_min else 1.0

        for p in per_plant_results:
            val = p.get(index, 0.0)
            norm_val = (val - v_min) / v_range   # 0.0 → 1.0
            cnt = p["contour"]
            mask_single = np.zeros((H, W), dtype=np.uint8)
            cv2.drawContours(mask_single, [cnt], -1, 1, -1)
            heat_map  += mask_single * norm_val
            count_map += mask_single

        # Tránh chia 0
        valid = count_map > 0
        heat_map[valid] /= count_map[valid]

        # Chuyển sang colormap (COLORMAP_RdYlGn: đỏ=thấp, xanh=cao)
        heat_u8  = (heat_map * 255).astype(np.uint8)
        heat_color = cv2.applyColorMap(heat_u8, cv2.COLORMAP_RdYlGn)

        # Chỉ áp lên vùng cây
        mask_any = count_map > 0
        blended  = cv2.addWeighted(canvas, 1 - alpha, heat_color, alpha, 0)
        out[mask_any] = blended[mask_any]

        return out

    # ──────────────────────────────────────────────────────────────
    def draw_analysis(
        self,
        canvas: np.ndarray,
        analysis: Dict[str, Any],
        show_contours: bool = True,
        show_kem_pt: bool = True,
        show_count_label: bool = True,
    ) -> np.ndarray:
        """
        Vẽ kết quả phân tích lên canvas BGR.

        Args:
            canvas:           Ảnh BGR để vẽ lên
            analysis:         Kết quả từ analyze()
            show_contours:    Vẽ viền từng cây
            show_kem_pt:      Đánh dấu cây kém phát triển
            show_count_label: Hiển thị số thứ tự cây
        """
        out = canvas.copy()

        if show_contours and analysis["contours"]:
            cv2.drawContours(out, analysis["contours"], -1, (0, 255, 0), 2)

        if show_kem_pt:
            for bbox in analysis["cay_kem_pt_bboxes"]:
                x, y, w, h = bbox
                cv2.rectangle(out, (x, y), (x + w, y + h), (0, 80, 255), 3)
                cv2.putText(out, "Kem PT", (x, y - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 80, 255), 1)

        if show_count_label and analysis["contours"]:
            for i, cnt in enumerate(analysis["contours"]):
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    cv2.putText(out, str(i + 1), (cx - 5, cy + 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

        return out

    # ──────────────────────────────────────────────────────────────
    def draw_per_plant_nutrition(
        self,
        canvas: np.ndarray,
        per_plant_results: List[Dict[str, Any]],
        show_label: bool = True,
    ) -> np.ndarray:
        """
        Vẽ viền màu từng cây theo tình trạng dinh dưỡng:
          - Xanh lá   → Khỏe mạnh
          - Vàng      → Nghi thiếu dinh dưỡng
          - Đỏ        → Stress nặng
        """
        COLOR_MAP = {
            "Khỏe mạnh":       (0, 210, 50),
            "Nghi thiếu DD":   (0, 200, 255),
            "Stress nặng":     (0, 50, 230),
        }
        out = canvas.copy()
        for p in per_plant_results:
            color = COLOR_MAP.get(p["trang_thai"], (200, 200, 200))
            cv2.drawContours(out, [p["contour"]], -1, color, 2)
            if show_label:
                cx, cy = p["centroid"]
                label  = f"#{p['plant_id']} GLI:{p['gli']:.2f}"
                cv2.putText(out, label, (cx - 20, cy - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)
        return out

    # ──────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────
    def _morphological_separation(self, mask: np.ndarray) -> np.ndarray:
        """
        Morphological opening → closing:
        Tách cây dính nhau và loại nhiễu nhỏ.
        """
        mask_u8 = mask.astype(np.uint8) * 255
        kernel  = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (self.morph_kernel_size, self.morph_kernel_size),
        )
        opened = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN,  kernel, iterations=2)
        closed = cv2.morphologyEx(opened,  cv2.MORPH_CLOSE, kernel, iterations=1)
        return closed > 0

    def _find_plant_contours(
        self,
        mask: np.ndarray,
    ) -> Tuple[list, list, list]:
        """
        Tìm contour và lọc theo diện tích tối thiểu.
        Returns: (contours, areas, bboxes)
        """
        mask_u8 = mask.astype(np.uint8) * 255
        contours_raw, _ = cv2.findContours(
            mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        contours, areas, bboxes = [], [], []
        for cnt in contours_raw:
            area = cv2.contourArea(cnt)
            if area >= self.min_plant_area_px:
                contours.append(cnt)
                areas.append(area)
                bboxes.append(list(cv2.boundingRect(cnt)))
        return contours, areas, bboxes

    def _calc_color_indices(
        self,
        image_bgr: np.ndarray,
        crop_mask: np.ndarray,
    ) -> Tuple[float, float, float, float, bool, str]:
        """
        Tính ExG, GLI, VARI, R/G ratio trên toàn vùng cây.

        Returns:
            (exg_mean, gli_mean, vari_mean, rg_ratio_mean, stress_detected, nutrition_status)
        """
        img_f = image_bgr.astype(np.float32) / 255.0
        B_ch  = img_f[:, :, 0]
        G_ch  = img_f[:, :, 1]
        R_ch  = img_f[:, :, 2]

        pm = crop_mask.astype(bool)
        if pm.sum() == 0:
            return 0.0, 0.0, 0.0, 1.0, False, "Không có dữ liệu"

        g = G_ch[pm]; r = R_ch[pm]; b = B_ch[pm]

        # ExG
        exg_vals = 2.0 * g - r - b
        exg_mean = float(np.mean(exg_vals))

        # GLI = (2G - R - B) / (2G + R + B)
        gli_denom = 2.0 * g + r + b
        gli_vals  = np.where(gli_denom > 1e-6, (2.0 * g - r - b) / gli_denom, 0.0)
        gli_mean  = float(np.mean(gli_vals))

        # VARI = (G - R) / (G + R - B)
        vari_denom = g + r - b
        vari_vals  = np.where(np.abs(vari_denom) > 1e-6, (g - r) / vari_denom, 0.0)
        # Clip outlier
        vari_vals  = np.clip(vari_vals, -1.0, 1.0)
        vari_mean  = float(np.mean(vari_vals))

        # R/G ratio
        rg_ratio_vals = np.where(g > 1e-6, r / g, 1.0)
        rg_ratio_mean = float(np.mean(rg_ratio_vals))

        # Phân loại
        stress_detected  = exg_mean < EXG_STRESS_MIN
        nutrition_status = self._classify_nutrition(gli_mean, exg_mean)

        return exg_mean, gli_mean, vari_mean, rg_ratio_mean, stress_detected, nutrition_status

    @staticmethod
    def _classify_nutrition(gli: float, exg: float) -> str:
        """
        Phân loại tình trạng dinh dưỡng dựa vào GLI + ExG.

        GLI >= 0.10 và ExG >= 0.05  → Khỏe mạnh
        GLI >= 0.04                  → Nghi thiếu DD
        còn lại                      → Stress nặng
        """
        if gli >= GLI_HEALTHY_MIN and exg >= EXG_STRESS_MIN:
            return "Khỏe mạnh"
        elif gli >= GLI_WARNING_MIN:
            return "Nghi thiếu DD"
        else:
            return "Stress nặng"
