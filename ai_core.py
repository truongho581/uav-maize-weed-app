"""
ai_core.py -- Module AI loi dung chung
4 Class: maize_2, maize_4, maize_6, weed
Doc anh -> YOLOv8-seg -> ve contour polygon + label theo phong cach anh mau
"""

import cv2
import numpy as np
from pathlib import Path

try:
    from ultralytics import YOLO
    ULTRALYTICS_OK = True
except ImportError:
    ULTRALYTICS_OK = False

# ===================================================
# CAU HINH 4 CLASS
# Thu tu class phai khop voi data.yaml luc train:
#   0: maize_2   (Ngo 2 la)
#   1: maize_4   (Ngo 4 la)
#   2: maize_6   (Ngo 6 la)
#   3: weed      (Co Dai)
# ===================================================
IDX_MAIZE_2 = 0
IDX_MAIZE_4 = 1
IDX_MAIZE_6 = 2
IDX_WEED    = 3

# Alias backward-compat
IDX_SOIL       = IDX_MAIZE_2
IDX_CROP       = IDX_MAIZE_4
IDX_BACKGROUND = IDX_MAIZE_2

# Cac class thuoc nhom "Cay trong" (crop)
CROP_CLASS_IDS = {IDX_MAIZE_2, IDX_MAIZE_4, IDX_MAIZE_6}

# Ten hien thi ngan (giong anh mau)
CLASS_LABELS = {
    IDX_MAIZE_2: "crop_2",
    IDX_MAIZE_4: "crop_4",
    IDX_MAIZE_6: "crop_6",
    IDX_WEED:    "weed",
}

# Mau BGR cho tung class. OpenCV dùng thứ tự BGR, không phải RGB.
CLASS_COLORS_BGR = {
    IDX_MAIZE_2: (0, 255, 255),   # vang
    IDX_MAIZE_4: (0, 255, 0),     # xanh la
    IDX_MAIZE_6: (255, 120, 0),   # xanh duong
    IDX_WEED:    (0, 50, 220),    # do cho co dai
}

CLASS_NAMES_VI = {
    IDX_MAIZE_2: "Ngo 2 La",
    IDX_MAIZE_4: "Ngo 4 La",
    IDX_MAIZE_6: "Ngo 6 La",
    IDX_WEED:    "Co Dai",
}


class CropAICore:
    """Module AI loi: load YOLOv8-seg va chay inference, ho tro 4 class."""

    def __init__(self, model_path: str, device: str = "cpu",
                 conf: float = 0.25, iou: float = 0.45):
        if not ULTRALYTICS_OK:
            raise ImportError("Cai ultralytics: pip install ultralytics")
        if not Path(model_path).exists():
            raise FileNotFoundError(f"Khong tim thay model: {model_path}")

        self.device = device
        self.conf   = conf
        self.iou    = iou
        self.model  = YOLO(model_path)
        self.class_names = self.model.names

    # ------------------------------------------------------------------
    def predict_image_with_boxes(self, image_bgr: np.ndarray) -> dict:
        """
        Chay inference + ve contour polygon + label theo phong cach anh mau.

        Returns dict:
            detection_overlay : uint8 (H,W,3) BGR -- anh da ve contour + label
            crop_mask         : bool (H,W)
            weed_mask         : bool (H,W)
            per_stage_masks   : {cls_id: bool (H,W)}
            stage_counts      : {cls_id: int}
            n_crop_instances  : int
            Cỏ dại được xử lý như mask vùng, không đếm instance.
            instances         : list of dict {cls_id, label, conf, bbox, mask}
        """
        H, W = image_bgr.shape[:2]
        crop_mask = np.zeros((H, W), dtype=bool)
        weed_mask = np.zeros((H, W), dtype=bool)
        per_stage = {
            IDX_MAIZE_2: np.zeros((H, W), dtype=bool),
            IDX_MAIZE_4: np.zeros((H, W), dtype=bool),
            IDX_MAIZE_6: np.zeros((H, W), dtype=bool),
        }
        stage_counts = {IDX_MAIZE_2: 0, IDX_MAIZE_4: 0, IDX_MAIZE_6: 0}
        n_crop = 0
        instances = []

        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        results = self.model(image_rgb, conf=self.conf, iou=self.iou,
                             verbose=False, device=self.device)[0]

        if results.masks is not None:
            for m, box in zip(results.masks.data.cpu().numpy(), results.boxes):
                cls_id = int(box.cls.item())
                conf_v = float(box.conf.item())
                xyxy   = box.xyxy[0].cpu().numpy().astype(int)
                m_bin  = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR) > 0.5

                instances.append({
                    "cls_id": cls_id,
                    "label":  CLASS_LABELS.get(cls_id, str(cls_id)),
                    "conf":   conf_v,
                    "bbox":   xyxy,   # [x1,y1,x2,y2]
                    "mask":   m_bin,
                })

                if cls_id in CROP_CLASS_IDS:
                    crop_mask |= m_bin
                    if cls_id in per_stage:
                        per_stage[cls_id] |= m_bin
                        stage_counts[cls_id] += 1
                    n_crop += 1
                elif cls_id == IDX_WEED:
                    weed_mask |= m_bin

        overlay = self._draw_contour_style(image_bgr, instances)

        return {
            "detection_overlay": overlay,
            "crop_mask":         crop_mask,
            "weed_mask":         weed_mask,
            "per_stage_masks":   per_stage,
            "stage_counts":      stage_counts,
            "n_crop_instances":  n_crop,
            "instances":         instances,
        }

    # ------------------------------------------------------------------
    def _draw_contour_style(self, image_bgr: np.ndarray,
                             instances: list,
                             font_scale: float = 0.38,
                             line_thickness: int = 1) -> np.ndarray:
        """
        Ve ket qua theo phong cach anh mau:
          - Chi ve contour polygon cua mask (khong to nen)
          - Label nho "crop_2 0.93" dat ngay tren diem dau cua contour
          - Khong ve bounding box day du, chi contour la
        """
        canvas = image_bgr.copy()
        H, W   = canvas.shape[:2]

        for inst in instances:
            color = CLASS_COLORS_BGR.get(inst["cls_id"], (0, 255, 0))
            mask_u8 = inst["mask"].astype(np.uint8) * 255

            # Tim contour
            contours, _ = cv2.findContours(
                mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if not contours:
                continue

            # Ve contour
            cv2.drawContours(canvas, contours, -1, color, line_thickness)

            # Vi tri dat label: goc tren-trai cua bounding rect cua contour lon nhat
            largest = max(contours, key=cv2.contourArea)
            rx, ry, rw, rh = cv2.boundingRect(largest)

            label = f"{inst['label']} {inst['conf']:.2f}"

            # Ve label text truc tiep (khong co nen) giong anh mau
            lx = rx
            ly = max(ry - 3, 10)

            # Shadow nho de de doc
            cv2.putText(canvas, label,
                        (lx + 1, ly + 1),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                        (0, 0, 0), 2, cv2.LINE_AA)
            # Text chinh mau xanh la
            cv2.putText(canvas, label,
                        (lx, ly),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                        color, 1, cv2.LINE_AA)

        return canvas

    # ------------------------------------------------------------------
    # Giu lai de tuong thich code cu
    # ------------------------------------------------------------------
    def predict_image(self, image_bgr: np.ndarray) -> dict:
        """Goi predict_image_with_boxes va map lai key cu."""
        r = self.predict_image_with_boxes(image_bgr)
        r["colored_overlay"] = r["detection_overlay"]
        return r

    def _build_overlay(self, image_bgr, per_stage, weed_mask, alpha=0.5):
        colored  = np.zeros_like(image_bgr)
        mask_any = weed_mask.copy()
        for cls_id, sm in per_stage.items():
            colored[sm] = CLASS_COLORS_BGR[cls_id]
            mask_any |= sm
        colored[weed_mask] = CLASS_COLORS_BGR[IDX_WEED]
        overlay = image_bgr.copy()
        if mask_any.any():
            blended = cv2.addWeighted(image_bgr, 1 - alpha, colored, alpha, 0)
            overlay[mask_any] = blended[mask_any]
        return overlay

    def build_overlay_custom(self, image_bgr, per_stage, weed_mask,
                             show_crop=True, show_weed=True, alpha=0.5):
        overlay  = image_bgr.copy()
        colored  = np.zeros_like(image_bgr)
        mask_any = np.zeros(image_bgr.shape[:2], dtype=bool)
        if show_crop:
            for cls_id, sm in per_stage.items():
                colored[sm] = CLASS_COLORS_BGR[cls_id]
                mask_any |= sm
        if show_weed:
            colored[weed_mask] = CLASS_COLORS_BGR[IDX_WEED]
            mask_any |= weed_mask
        if mask_any.any():
            blended = cv2.addWeighted(image_bgr, 1 - alpha, colored, alpha, 0)
            overlay[mask_any] = blended[mask_any]
        return overlay
