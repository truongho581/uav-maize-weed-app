import sys
import os
import csv
from pathlib import Path
import cv2
import numpy as np
from PyQt5 import uic
from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QFileDialog,
    QMessageBox, QTableWidgetItem, QWidget,
    QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QSizePolicy,
    QGroupBox, QGridLayout, QComboBox, QDoubleSpinBox, QSpinBox,
    QScrollArea, QTableWidget, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QPalette, QColor

try:
    from ai_core import (
        CropAICore,
        IDX_MAIZE_2, IDX_MAIZE_4, IDX_MAIZE_6, IDX_WEED,
        CLASS_COLORS_BGR, build_overlay_custom,
    )
    AI_OK = True
    _AI_ERR = ""
except Exception as _e:
    try:
        from ai_core import (
            CropAICore,
            IDX_MAIZE_2, IDX_MAIZE_4, IDX_MAIZE_6, IDX_WEED,
        )
        AI_OK = True
        _AI_ERR = ""
    except Exception as _e2:
        AI_OK = False
        _AI_ERR = str(_e2)

try:
    from crop_processor import CropProcessor
    CROP_PROC_OK = True
except Exception:
    CROP_PROC_OK = False

try:
    from weed_processor import WeedProcessor
    WEED_PROC_OK = True
except Exception:
    WEED_PROC_OK = False

try:
    from tile_engine import TileEngine
    TILE_ENGINE_OK = True
except Exception:
    TILE_ENGINE_OK = False

BASE_DIR      = Path(__file__).resolve().parent
UI_FILE       = BASE_DIR / "phan_tich_ui.ui"
DEFAULT_MODEL = BASE_DIR / "models" / "best.pt"

# DJI Mini 4 Pro hardcoded GSD (cm/px)
GSD_5M      = 0.148
GSD_10M     = 0.296
GSD_DEFAULT = GSD_5M

IMG_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

COLOR_CROP = (0, 200, 50)    # xanh la
COLOR_WEED = (0, 50, 220)    # do

# =============================================================================
TILE_DIR = "_tiles640"   # subfolder where cut tiles are saved

# =============================================================================
class AnalysisWorker(QThread):
    progress    = pyqtSignal(int, str)
    image_done  = pyqtSignal(int, dict)
    tiles_ready = pyqtSignal(list)   # list[str] of valid source image paths
    batch_done  = pyqtSignal(list)   # final display results, stitched if overlap exists
    finished    = pyqtSignal()
    error       = pyqtSignal(str)

    def __init__(
        self,
        image_paths,
        model_path,
        conf=0.25,
        iou=0.45,
        gsd_cm_per_px=GSD_DEFAULT,
        weed_grid=4,
        weed_threshold=0.35,
        parent=None,
    ):
        super().__init__(parent)
        self.image_paths = [str(p) for p in image_paths]
        self.model_path  = model_path
        self.conf        = conf
        self.iou         = iou
        self.gsd_cm_per_px = gsd_cm_per_px
        self.weed_grid   = weed_grid
        self.weed_threshold = weed_threshold

    def run(self):
        try:
            if not TILE_ENGINE_OK:
                raise RuntimeError("Không nạp được TileEngine.")

            self.progress.emit(2, "Đang kiểm tra ảnh đầu vào...")
            valid_paths = []
            invalid_paths = []
            for img_path in self.image_paths:
                img_bgr = cv2.imread(img_path)
                if img_bgr is None:
                    invalid_paths.append(img_path)
                else:
                    valid_paths.append(img_path)

            if invalid_paths:
                names = ", ".join(Path(p).name for p in invalid_paths[:3])
                more = "..." if len(invalid_paths) > 3 else ""
                self.progress.emit(3, "Bỏ qua ảnh lỗi: {}{}".format(names, more))

            if not valid_paths:
                raise RuntimeError("Không đọc được ảnh hợp lệ trong đầu vào.")

            self.tiles_ready.emit(valid_paths)

            self.progress.emit(8, "Đang nạp model AI...")
            ai = CropAICore(str(self.model_path), conf=self.conf, iou=self.iou)

            crop_proc = CropProcessor() if CROP_PROC_OK else None
            weed_proc = WeedProcessor(
                zone_grid=self.weed_grid,
                high_density_threshold=self.weed_threshold,
            ) if WEED_PROC_OK else None
            tile_engine = TileEngine(tile_size=640, overlap=64)

            image_results = []
            n = len(valid_paths)
            for i, img_path in enumerate(valid_paths):
                pct = int(10 + 85 * i / max(n, 1))
                self.progress.emit(pct, "Đang phân tích ảnh {}/{}: {}".format(
                    i + 1, n, Path(img_path).name))

                img_bgr = cv2.imread(img_path)
                if img_bgr is None:
                    continue

                result = self._analyze_one_image(
                    img_bgr, img_path, ai, crop_proc, weed_proc, tile_engine)
                image_results.append(result)
                self.image_done.emit(len(image_results) - 1, result)

            final_results = image_results
            if len(image_results) > 1:
                stitched = self._try_stitch_overlapping_results(image_results)
                if stitched is not None:
                    final_results = [stitched]
                    self.progress.emit(98, "Đã phát hiện ảnh overlap và ghép thành 1 kết quả.")

            self.batch_done.emit(final_results)

            self.progress.emit(100, "Hoàn thành!")
            self.finished.emit()

        except Exception as exc:
            self.error.emit(str(exc))

    def _analyze_one_image(self, img_bgr, img_path, ai, crop_proc, weed_proc, tile_engine):
        tiles = tile_engine.split_image(img_bgr)
        stage_counts = {IDX_MAIZE_2: 0, IDX_MAIZE_4: 0, IDX_MAIZE_6: 0}
        n_crop = 0

        for tile in tiles:
            pred = ai.predict_image_with_boxes(tile.image_bgr)
            tile.crop_mask = pred.get("crop_mask", np.zeros((640, 640), dtype=bool))
            tile.weed_mask = pred.get("weed_mask", np.zeros((640, 640), dtype=bool))
            tile.per_stage_masks = pred.get("per_stage_masks", {})
            n_crop += pred.get("n_crop_instances", 0)
            for k, v in pred.get("stage_counts", {}).items():
                stage_counts[k] = stage_counts.get(k, 0) + v

        crop_m, weed_m = tile_engine.stitch_masks(tiles, img_bgr.shape[:2])
        per_stage_m = self._stitch_per_stage_masks(tiles, img_bgr.shape[:2], tile_engine)
        overlay = self._build_overlay_image(img_bgr, crop_m, weed_m, 0.45, per_stage_m)

        crop_stats = {}
        if crop_proc is not None:
            try:
                crop_stats = crop_proc.analyze(
                    crop_m.astype(bool), original_bgr=None,
                    gsd_cm_per_px=self.gsd_cm_per_px)
            except Exception as ce:
                crop_stats = {"error": str(ce)}

        weed_stats = {}
        if weed_proc is not None:
            try:
                weed_stats = weed_proc.analyze(
                    weed_m.astype(bool), crop_mask=crop_m.astype(bool),
                    gsd_cm_per_px=self.gsd_cm_per_px)
            except Exception as we:
                weed_stats = {"error": str(we)}

        heatmap_img = self._build_weed_view(img_bgr, weed_proc, weed_stats, "heatmap")
        zone_img = self._build_weed_view(img_bgr, weed_proc, weed_stats, "zones")

        return {
            "result_type": "image",
            "image_name": Path(img_path).name,
            "original_path": img_path,
            "crop_mask": crop_m,
            "weed_mask": weed_m,
            "per_stage_masks": per_stage_m,
            "stage_counts": stage_counts,
            "n_crop_instances": n_crop,
            "crop_stats": crop_stats,
            "weed_stats": weed_stats,
            "display_images": {
                "original": img_bgr,
                "crop_mask": self._stage_masks_to_bgr(per_stage_m, crop_m),
                "weed_mask": self._mask_to_bgr(weed_m, COLOR_WEED),
                "overlay": overlay,
                "weed_heatmap": heatmap_img,
                "weed_zones": zone_img,
            },
        }

    @staticmethod
    def _stitch_per_stage_masks(tiles, original_shape, tile_engine):
        H, W = original_shape
        weight_kernel = tile_engine._make_weight_kernel(tile_engine.tile_size)
        out = {}
        for cls_id in (IDX_MAIZE_2, IDX_MAIZE_4, IDX_MAIZE_6):
            acc = np.zeros((H, W), dtype=np.float32)
            weight_acc = np.zeros((H, W), dtype=np.float32)
            for tile in tiles:
                stage_masks = tile.per_stage_masks or {}
                stage_mask = stage_masks.get(cls_id)
                if stage_mask is None:
                    continue

                ys, ye = tile.y_start, tile.y_end
                xs, xe = tile.x_start, tile.x_end
                rh, rw = ye - ys, xe - xs
                if rh <= 0 or rw <= 0:
                    continue

                stage_m = stage_mask.astype(np.float32)
                if stage_m.shape != (tile_engine.tile_size, tile_engine.tile_size):
                    stage_m = cv2.resize(
                        stage_m, (tile_engine.tile_size, tile_engine.tile_size))

                acc[ys:ye, xs:xe] += stage_m[:rh, :rw] * weight_kernel[:rh, :rw]
                weight_acc[ys:ye, xs:xe] += weight_kernel[:rh, :rw]

            weight_safe = np.where(weight_acc < 1e-6, 1.0, weight_acc)
            out[cls_id] = (acc / weight_safe) > 0.5
        return out

    @staticmethod
    def _mask_to_bgr(mask, color):
        out = np.zeros((mask.shape[0], mask.shape[1], 3), dtype=np.uint8)
        out[mask.astype(bool)] = color
        return out

    @staticmethod
    def _stage_masks_to_bgr(per_stage_masks, fallback_crop_mask=None):
        if per_stage_masks:
            shape = next(iter(per_stage_masks.values())).shape
        elif fallback_crop_mask is not None:
            shape = fallback_crop_mask.shape
        else:
            return None

        out = np.zeros((shape[0], shape[1], 3), dtype=np.uint8)
        has_stage = False
        for cls_id in (IDX_MAIZE_2, IDX_MAIZE_4, IDX_MAIZE_6):
            mask = (per_stage_masks or {}).get(cls_id)
            if mask is None:
                continue
            out[mask.astype(bool)] = CLASS_COLORS_BGR.get(cls_id, COLOR_CROP)
            has_stage = has_stage or bool(mask.any())
        if not has_stage and fallback_crop_mask is not None:
            out[fallback_crop_mask.astype(bool)] = COLOR_CROP
        return out

    @staticmethod
    def _build_overlay_image(img_bgr, crop_m, weed_m, alpha, per_stage_masks=None):
        colored = np.zeros_like(img_bgr)
        any_m = crop_m.astype(bool) | weed_m.astype(bool)
        if per_stage_masks:
            for cls_id in (IDX_MAIZE_2, IDX_MAIZE_4, IDX_MAIZE_6):
                mask = per_stage_masks.get(cls_id)
                if mask is not None:
                    colored[mask.astype(bool)] = CLASS_COLORS_BGR.get(cls_id, COLOR_CROP)
        else:
            colored[crop_m.astype(bool)] = COLOR_CROP
        colored[weed_m.astype(bool)] = COLOR_WEED
        overlay = img_bgr.copy()
        if any_m.any():
            blended = cv2.addWeighted(img_bgr, 1 - alpha, colored, alpha, 0)
            overlay[any_m] = blended[any_m]
        return overlay

    @staticmethod
    def _build_weed_view(img_bgr, weed_proc, weed_stats, mode):
        if weed_proc is None or not weed_stats or "error" in weed_stats:
            return img_bgr.copy()
        if mode == "heatmap":
            return weed_proc.draw_analysis(
                img_bgr, weed_stats,
                show_contours=False, show_danger_zones=False, show_heatmap=True)
        return weed_proc.draw_analysis(
            img_bgr, weed_stats,
            show_contours=False, show_danger_zones=True, show_heatmap=False)

    def _try_stitch_overlapping_results(self, results):
        stitched_images = self._stitch_display_images(results)
        if stitched_images is None:
            return None

        agg = self._aggregate_result_dicts(results)
        agg["result_type"] = "stitched"
        agg["image_name"] = "Ảnh_ghep_overlap"
        agg["original_path"] = ""
        agg["display_images"] = stitched_images
        agg["crop_mask"] = None
        agg["weed_mask"] = None
        return agg

    def _stitch_display_images(self, results):
        view_keys = ["original", "crop_mask", "weed_mask", "overlay", "weed_heatmap", "weed_zones"]
        mosaics = {k: results[0]["display_images"][k].copy() for k in view_keys}
        feature_canvas = mosaics["original"].copy()

        for result in results[1:]:
            next_img = result["display_images"]["original"]
            H = self._find_homography(next_img, feature_canvas)
            if H is None:
                return None

            h0, w0 = feature_canvas.shape[:2]
            h1, w1 = next_img.shape[:2]
            corners0 = np.float32([[0, 0], [w0, 0], [w0, h0], [0, h0]]).reshape(-1, 1, 2)
            corners1 = np.float32([[0, 0], [w1, 0], [w1, h1], [0, h1]]).reshape(-1, 1, 2)
            warped1 = cv2.perspectiveTransform(corners1, H)
            all_corners = np.vstack((corners0, warped1))
            xmin, ymin = np.floor(all_corners.min(axis=0).ravel()).astype(int)
            xmax, ymax = np.ceil(all_corners.max(axis=0).ravel()).astype(int)
            if xmax <= xmin or ymax <= ymin:
                return None

            trans = np.array([[1, 0, -xmin], [0, 1, -ymin], [0, 0, 1]], dtype=np.float64)
            size = (int(xmax - xmin), int(ymax - ymin))

            for key in view_keys:
                base = cv2.warpPerspective(mosaics[key], trans, size)
                nxt = cv2.warpPerspective(result["display_images"][key], trans @ H, size)
                mask = cv2.cvtColor(nxt, cv2.COLOR_BGR2GRAY) > 0
                if key == "original":
                    overlap = mask & (cv2.cvtColor(base, cv2.COLOR_BGR2GRAY) > 0)
                    base[mask & ~overlap] = nxt[mask & ~overlap]
                    if overlap.any():
                        base[overlap] = cv2.addWeighted(base, 0.5, nxt, 0.5, 0)[overlap]
                else:
                    base[mask] = nxt[mask]
                mosaics[key] = base

            feature_canvas = mosaics["original"]

        return mosaics

    @staticmethod
    def _find_homography(src_bgr, dst_bgr):
        gray_src = cv2.cvtColor(src_bgr, cv2.COLOR_BGR2GRAY)
        gray_dst = cv2.cvtColor(dst_bgr, cv2.COLOR_BGR2GRAY)
        orb = cv2.ORB_create(4000)
        kp1, des1 = orb.detectAndCompute(gray_src, None)
        kp2, des2 = orb.detectAndCompute(gray_dst, None)
        if des1 is None or des2 is None or len(kp1) < 20 or len(kp2) < 20:
            return None
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = matcher.knnMatch(des1, des2, k=2)
        good = []
        for pair in matches:
            if len(pair) != 2:
                continue
            m, n = pair
            if m.distance < 0.75 * n.distance:
                good.append(m)
        if len(good) < 16:
            return None
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        H, inliers = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if H is None or inliers is None or int(inliers.sum()) < 12:
            return None
        return H

    @staticmethod
    def _aggregate_result_dicts(results):
        out = dict(results[0])
        out["n_crop_instances"] = sum(r.get("n_crop_instances", 0) for r in results)
        stage = {}
        for r in results:
            for k, v in r.get("stage_counts", {}).items():
                stage[k] = stage.get(k, 0) + v
        out["stage_counts"] = stage

        cs = {}
        for key in ("so_cay_uoc_tinh", "dien_tich_tan_m2", "so_cay_kem_pt"):
            vals = [r.get("crop_stats", {}).get(key) for r in results
                    if r.get("crop_stats", {}).get(key) is not None]
            cs[key] = sum(vals) if vals else None
        cov_vals = [r.get("crop_stats", {}).get("do_phu_phan_tram") for r in results
                    if r.get("crop_stats", {}).get("do_phu_phan_tram") is not None]
        cs["do_phu_phan_tram"] = sum(cov_vals) / len(cov_vals) if cov_vals else None
        out["crop_stats"] = cs

        ws = {}
        for key in ("so_vung_co", "dien_tich_co_m2", "cay_bi_bao_vay"):
            vals = [r.get("weed_stats", {}).get(key) for r in results
                    if r.get("weed_stats", {}).get(key) is not None]
            ws[key] = sum(vals) if vals else None
        for key in ("do_phu_co_phan_tram", "ty_le_co_tren_cay"):
            vals = [r.get("weed_stats", {}).get(key) for r in results
                    if r.get("weed_stats", {}).get(key) is not None]
            ws[key] = sum(vals) / len(vals) if vals else None
        zones = []
        for r in results:
            zones.extend(r.get("weed_stats", {}).get("vung_nguy_hiem", []) or [])
        ws["vung_nguy_hiem"] = zones
        if results[0].get("weed_stats", {}).get("muc_do_canh_tranh"):
            ws["muc_do_canh_tranh"] = results[0]["weed_stats"]["muc_do_canh_tranh"]
        out["weed_stats"] = ws
        return out

# =============================================================================
# Phần MainWindow giữ nguyên như cũ, không cần thay đổi nhiều
# vì dữ liệu tile vẫn được đưa vào self.results_data và hiển thị như ảnh bình thường.
# =============================================================================


# =============================================================================
class MainWindow(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(str(UI_FILE), self)

        self._theme       = "dark"
        self._kpi_labels  = {}
        self.folder_path  = None
        self.model_path   = DEFAULT_MODEL
        self.results_data = []
        self._img_paths   = []
        self._source_count = 0
        self._tile_count   = 0
        self.current_idx  = 0
        self._worker      = None

        self._build_dashboard_shell()
        self._apply_style()
        self._update_kpis()
        self._connect_signals()
        self._set_nav_enabled(False)
        self.btnBatDau.setEnabled(False)

        if not AI_OK:
            self.lblTrangThai.setText("AI chưa khả dụng: " + _AI_ERR[:60])
        elif self.model_path.exists():
            self.lblTrangThai.setText("Model sẵn sàng: " + self.model_path.name)
            self.lblModel.setText("Model: " + self.model_path.name)
        else:
            self.lblTrangThai.setText("Thiếu model: models/best.pt")
            self.lblModel.setText("Thiếu model: best.pt")

    # -------------------------------------------------------------------------
    def _connect_signals(self):
        self.btnChonAnh.clicked.connect(self._chon_anh)
        self.btnChonThuMuc.clicked.connect(self._chon_thu_muc)
        self.btnChonModel.clicked.connect(self._chon_model)
        self.btnBatDau.clicked.connect(self._bat_dau)
        self.btnTruoc.clicked.connect(self._anh_truoc)
        self.btnSau.clicked.connect(self._anh_sau)
        self.btnXuatCSV.clicked.connect(self._xuat_csv)
        self.btnLuuAnh.clicked.connect(self._luu_anh)
        self.btnTheme.clicked.connect(self._toggle_theme)
        self.actionChonThuMuc.triggered.connect(self._chon_thu_muc)
        self.actionXuatCSV.triggered.connect(self._xuat_csv)
        self.actionThoat.triggered.connect(self.close)
        self.cmbViewMode.currentIndexChanged.connect(self._refresh_display)
        self.rbAnhGoc.toggled.connect(self._refresh_display)
        self.rbOverlay.toggled.connect(self._refresh_display)
        # Checkboxes chi xem cay / co
        try:
            self.chkChiXemCay.stateChanged.connect(self._refresh_display)
            self.chkChiXemCo.stateChanged.connect(self._refresh_display)
        except AttributeError:
            pass
        self.sliderAlpha.valueChanged.connect(self._on_slider)

    # -------------------------------------------------------------------------
    def _chon_anh(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Chọn ảnh UAV", str(Path.home()),
            "Image (*.jpg *.jpeg *.png *.tif *.tiff *.bmp)")
        if not f:
            return
        self.folder_path = None
        self._img_paths = [Path(f)]
        self.results_data = [None]
        self._source_count = 1
        self._tile_count = 0
        self.current_idx = 0
        self.lblThuMuc.setText(Path(f).name)
        self.lblTrangThai.setText("Đã chọn 1 ảnh.")
        self.btnBatDau.setEnabled(True)
        self._set_nav_enabled(False)
        self._update_kpis()

    def _chon_thu_muc(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục ảnh UAV", str(Path.home()))
        if not folder:
            return
        self.folder_path = Path(folder)
        imgs = sorted([p for p in self.folder_path.iterdir()
                       if p.suffix.lower() in IMG_EXTS])
        if not imgs:
            QMessageBox.warning(self, "Không có ảnh",
                "Thư mục không chứa ảnh jpg/png/tif")
            return
        self._img_paths   = imgs
        self.results_data = [None] * len(imgs)  # reset; tiles_ready se cap nhat
        self._source_count = len(imgs)
        self._tile_count   = 0
        self.current_idx  = 0
        self.lblThuMuc.setText("{} ({} anh)".format(
            self.folder_path.name, len(imgs)))
        self.btnBatDau.setEnabled(True)
        self.lblTrangThai.setText("Đã chọn {} ảnh.".format(len(imgs)))
        self._update_kpis()

    def _chon_model(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Chọn model .pt", str(self.model_path.parent),
            "Model (*.pt *.onnx)")
        if f:
            self.model_path = Path(f)
            self.lblModel.setText("Model: " + self.model_path.name)
            self._update_kpis()

    # -------------------------------------------------------------------------
    def _bat_dau(self):
        if not self._img_paths:
            QMessageBox.information(self, "Chưa chọn ảnh",
                "Hãy chọn ảnh hoặc thư mục ảnh trước.")
            return
        if not AI_OK:
            QMessageBox.critical(self, "Lỗi AI", _AI_ERR)
            return
        if not self.model_path.exists():
            QMessageBox.critical(self, "Không có model",
                str(self.model_path))
            return

        self.btnBatDau.setEnabled(False)
        self.btnChonThuMuc.setEnabled(False)
        self._set_nav_enabled(False)
        self.progressBar.setValue(0)
        self._update_kpis()

        self._worker = AnalysisWorker(
            self._img_paths,
            self.model_path,
            conf=self.spinConf.value(),
            iou=self.spinIou.value(),
            gsd_cm_per_px=self.spinGSD.value(),
            weed_grid=self.spinGrid.value(),
            weed_threshold=self.spinWeedThreshold.value(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.tiles_ready.connect(self._on_tiles_ready)
        self._worker.image_done.connect(self._on_image_done)
        self._worker.batch_done.connect(self._on_batch_done)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, pct, msg):
        self.progressBar.setValue(pct)
        self.lblTrangThai.setText(msg)

    def _on_tiles_ready(self, tile_paths):
        """Cập nhật danh sách ảnh hợp lệ sẽ được phân tích."""
        self._img_paths   = [Path(p) for p in tile_paths]
        self.results_data = [None] * len(tile_paths)
        self.current_idx  = 0
        n_orig = len(tile_paths)
        self._source_count = n_orig
        self._tile_count   = 0
        self.lblThuMuc.setText(
            "{} ảnh hợp lệ đang được phân tích".format(n_orig))
        self.lblTrangThai.setText(
            "Đã kiểm tra đầu vào. Đang chạy AI...")
        self._update_kpis()

    def _on_image_done(self, idx, result):
        if idx < len(self.results_data):
            self.results_data[idx] = result
        if idx == self.current_idx:
            self._refresh_display()
            self._fill_table(result)
        self._update_kpis()

    def _on_batch_done(self, final_results):
        if not final_results:
            return
        self.results_data = final_results
        self._img_paths = [Path(r.get("image_name", "kết_quả")) for r in final_results]
        self._tile_count = len(final_results)
        self.current_idx = 0
        if len(final_results) == 1 and final_results[0].get("result_type") == "stitched":
            self.lblThuMuc.setText("Đã ghép ảnh overlap thành 1 kết quả")
        self._refresh_display()
        self._fill_table(final_results[0])
        self._update_kpis()

    def _on_finished(self):
        self.btnBatDau.setEnabled(True)
        self.btnChonThuMuc.setEnabled(True)
        self._set_nav_enabled(True)
        self.lblTrangThai.setText(
            "Hoàn thành! {} ảnh/kết quả.".format(len(self._img_paths)))
        r = self.results_data[self.current_idx] \
            if self.results_data and self.current_idx < len(self.results_data) \
            else None
        if r:
            self._refresh_display()
            self._fill_table(r)
        self._update_kpis()

    def _on_error(self, msg):
        self.btnBatDau.setEnabled(True)
        self.btnChonThuMuc.setEnabled(True)
        QMessageBox.critical(self, "Lỗi AI", msg)
        self.lblTrangThai.setText("Lỗi: " + msg[:80])
        self._update_kpis()

    # -------------------------------------------------------------------------
    def _build_dashboard_shell(self):
        self.setMinimumSize(1080, 720)
        self.resize(1080, 720)
        self.layoutRoot.setContentsMargins(12, 12, 12, 12)
        self.layoutRoot.setSpacing(12)

        left_outer_layout = self.layoutLeft
        left_outer_layout.setContentsMargins(0, 0, 0, 0)
        left_outer_layout.setSpacing(0)
        self.sidebarContent = QWidget()
        self.sidebarContent.setObjectName("sidebarContent")
        self.sidebarLayout = QVBoxLayout(self.sidebarContent)
        self.sidebarLayout.setContentsMargins(0, 0, 0, 0)
        self.sidebarLayout.setSpacing(8)
        while left_outer_layout.count():
            item = left_outer_layout.takeAt(0)
            widget = item.widget()
            nested_layout = item.layout()
            if widget is not None:
                widget.setParent(self.sidebarContent)
                self.sidebarLayout.addWidget(widget)
            elif nested_layout is not None:
                self.sidebarLayout.addLayout(nested_layout)
            else:
                self.sidebarLayout.addItem(item)
        self.sidebarScroll = QScrollArea()
        self.sidebarScroll.setObjectName("sidebarScroll")
        self.sidebarScroll.setWidgetResizable(True)
        self.sidebarScroll.setFrameShape(0)
        self.sidebarScroll.setWidget(self.sidebarContent)
        left_outer_layout.addWidget(self.sidebarScroll)
        self.layoutLeft = self.sidebarLayout

        self.layoutRight.setContentsMargins(0, 0, 0, 0)
        self.layoutRight.setSpacing(10)
        self.panelLeft.setMinimumWidth(280)
        self.panelLeft.setMaximumWidth(310)
        self.panelRight.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lblAnh.setMinimumHeight(250)
        self.grpBang.setMinimumHeight(150)
        self.grpInput.setMinimumHeight(145)
        self.grpHienThi.setMinimumHeight(100)
        self.grpDieuHuong.setMinimumHeight(76)
        self.grpBang.setTitle("Chỉ số Crop / Weed")
        self.grpBang.setMinimumHeight(210)
        self.bangChiSo.setMinimumHeight(150)
        self.menubar.setNativeMenuBar(False)

        self.layoutInput.setContentsMargins(14, 16, 14, 10)
        self.layoutInput.setSpacing(4)
        self.layoutHienThi.setContentsMargins(14, 16, 14, 10)
        self.layoutHienThi.setSpacing(4)
        self.layoutDieuHuong.setContentsMargins(14, 16, 14, 10)
        self.layoutDieuHuong.setSpacing(8)
        self.layoutBang.setContentsMargins(12, 18, 12, 12)
        self.layoutBang.setSpacing(8)
        self._build_metrics_tables()

        for button in (
            self.btnChonThuMuc, self.btnChonModel, self.btnTruoc,
            self.btnSau, self.btnXuatCSV, self.btnLuuAnh,
        ):
            button.setMinimumHeight(30)
        self.btnBatDau.setMinimumHeight(38)
        self.progressBar.setMinimumHeight(16)
        for label in (self.lblThuMuc, self.lblModel, self.lblDoDam):
            label.setMinimumHeight(17)
        self.lblThuMuc.setVisible(False)
        self.lblModel.setVisible(False)
        for option in (
            self.rbAnhGoc, self.rbOverlay,
            self.chkChiXemCay, self.chkChiXemCo,
        ):
            option.setMinimumHeight(20)
        self.sliderAlpha.setMinimumHeight(20)

        self.btnChonAnh = QPushButton("Chọn 1 ảnh...")
        self.btnChonAnh.setObjectName("btnChonAnh")
        self.btnChonAnh.setToolTip("Chọn một ảnh UAV để phân tích")
        self.btnChonAnh.setMinimumHeight(30)
        self.layoutInput.insertWidget(0, self.btnChonAnh)

        for old_widget in (
            self.rbAnhGoc, self.rbOverlay,
            self.chkChiXemCay, self.chkChiXemCo,
        ):
            old_widget.setVisible(False)

        self.cmbViewMode = QComboBox()
        self.cmbViewMode.setObjectName("cmbViewMode")
        self.cmbViewMode.addItem("Ảnh gốc", "original")
        self.cmbViewMode.addItem("Mask cây", "crop_mask")
        self.cmbViewMode.addItem("Mask cỏ", "weed_mask")
        self.cmbViewMode.addItem("Overlay", "overlay")
        self.cmbViewMode.addItem("Heatmap cỏ", "weed_heatmap")
        self.cmbViewMode.addItem("Vùng cảnh báo", "weed_zones")
        self.cmbViewMode.setCurrentIndex(3)
        self.layoutHienThi.insertWidget(0, self.cmbViewMode)

        self.grpConfig = QGroupBox("Cấu hình phân tích")
        self.grpConfig.setObjectName("grpConfig")
        self.grpConfig.setMinimumHeight(130)
        cfg = QGridLayout(self.grpConfig)
        cfg.setContentsMargins(14, 16, 14, 10)
        cfg.setHorizontalSpacing(8)
        cfg.setVerticalSpacing(2)

        self.spinGSD = QDoubleSpinBox()
        self.spinGSD.setRange(0.01, 20.0)
        self.spinGSD.setDecimals(3)
        self.spinGSD.setSingleStep(0.01)
        self.spinGSD.setValue(GSD_DEFAULT)
        self.spinGSD.setSuffix(" cm/px")

        self.spinConf = QDoubleSpinBox()
        self.spinConf.setRange(0.01, 0.99)
        self.spinConf.setDecimals(2)
        self.spinConf.setSingleStep(0.05)
        self.spinConf.setValue(0.25)

        self.spinIou = QDoubleSpinBox()
        self.spinIou.setRange(0.01, 0.99)
        self.spinIou.setDecimals(2)
        self.spinIou.setSingleStep(0.05)
        self.spinIou.setValue(0.45)

        self.spinWeedThreshold = QDoubleSpinBox()
        self.spinWeedThreshold.setRange(0.01, 0.95)
        self.spinWeedThreshold.setDecimals(2)
        self.spinWeedThreshold.setSingleStep(0.05)
        self.spinWeedThreshold.setValue(0.35)

        self.spinGrid = QSpinBox()
        self.spinGrid.setRange(2, 12)
        self.spinGrid.setValue(4)

        cfg.addWidget(QLabel("GSD"), 0, 0)
        cfg.addWidget(self.spinGSD, 0, 1)
        cfg.addWidget(QLabel("Conf"), 1, 0)
        cfg.addWidget(self.spinConf, 1, 1)
        cfg.addWidget(QLabel("IoU"), 2, 0)
        cfg.addWidget(self.spinIou, 2, 1)
        cfg.addWidget(QLabel("Ngưỡng cỏ"), 3, 0)
        cfg.addWidget(self.spinWeedThreshold, 3, 1)
        cfg.addWidget(QLabel("Lưới"), 4, 0)
        cfg.addWidget(self.spinGrid, 4, 1)
        self.layoutLeft.insertWidget(2, self.grpConfig)

        brand = QWidget()
        brand.setObjectName("sidebarBrand")
        brand.setMinimumHeight(58)
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(16, 10, 16, 10)
        brand_layout.setSpacing(2)
        self.lblBrandTitle = QLabel("UAV Crop Analytics")
        self.lblBrandTitle.setObjectName("brandTitle")
        self.lblBrandSubtitle = QLabel("Phân tích cây trồng từ ảnh UAV")
        self.lblBrandSubtitle.setObjectName("brandSubtitle")
        self.lblBrandSubtitle.setWordWrap(True)
        brand_layout.addWidget(self.lblBrandTitle)
        brand_layout.addWidget(self.lblBrandSubtitle)
        self.layoutLeft.insertWidget(0, brand)

        header = QWidget()
        header.setObjectName("panelHeader")
        header.setMinimumHeight(58)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 10, 20, 10)
        header_layout.setSpacing(12)

        title_box = QWidget()
        title_box.setObjectName("headerTitleBox")
        title_layout = QVBoxLayout(title_box)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)
        self.lblHeaderTitle = QLabel("Dashboard phân tích sinh trưởng")
        self.lblHeaderTitle.setObjectName("headerTitle")
        self.lblHeaderMeta = QLabel("")
        self.lblHeaderMeta.setObjectName("headerMeta")
        self.lblHeaderMeta.setWordWrap(True)
        title_layout.addWidget(self.lblHeaderTitle)
        title_layout.addWidget(self.lblHeaderMeta)

        self.btnTheme = QPushButton("Chế độ sáng")
        self.btnTheme.setObjectName("btnTheme")
        self.btnTheme.setMinimumHeight(32)
        self.btnTheme.setToolTip("Chuyển đổi giao diện sáng/tối")

        header_layout.addWidget(title_box, 1)
        header_layout.addWidget(self.btnTheme, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.layoutRight.insertWidget(0, header)

        kpi_row = QWidget()
        kpi_row.setObjectName("kpiRow")
        kpi_row.setMaximumHeight(78)
        kpi_layout = QHBoxLayout(kpi_row)
        kpi_layout.setContentsMargins(0, 0, 0, 0)
        kpi_layout.setSpacing(12)
        kpi_layout.addWidget(self._make_kpi_card("Ảnh gốc", "0", "images"))
        kpi_layout.addWidget(self._make_kpi_card("Kết quả", "0", "tiles"))
        kpi_layout.addWidget(self._make_kpi_card("Cây ngô", "0", "crop"))
        kpi_layout.addWidget(self._make_kpi_card("Phủ cỏ", "0.0%", "weed"))
        self.layoutRight.insertWidget(1, kpi_row)

        self.splitterRight.setStretchFactor(0, 5)
        self.splitterRight.setStretchFactor(1, 2)

    def _build_metrics_tables(self):
        while self.layoutBang.count():
            item = self.layoutBang.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        self.tblCrop = self.bangChiSo
        self.tblCrop.setObjectName("tblCropMetrics")
        self.tblWeed = QTableWidget()
        self.tblWeed.setObjectName("tblWeedMetrics")

        metrics_layout = QHBoxLayout()
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(12)

        crop_panel = self._make_metric_panel("Crop", self.tblCrop)
        weed_panel = self._make_metric_panel("Weed", self.tblWeed)
        metrics_layout.addWidget(crop_panel, 1)
        metrics_layout.addWidget(weed_panel, 1)
        self.layoutBang.addLayout(metrics_layout)

    def _make_metric_panel(self, title, table):
        panel = QWidget()
        panel.setObjectName("metricPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(title)
        label.setObjectName("metricTitle")
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Chỉ số", "Giá trị"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.setMinimumHeight(150)
        table.setMaximumHeight(16777215)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)

        layout.addWidget(label)
        layout.addWidget(table, 1)
        return panel

    def _make_kpi_card(self, title, value, key):
        card = QWidget()
        card.setObjectName("kpiCard")
        card.setMinimumHeight(72)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(2)
        label = QLabel(title)
        label.setObjectName("kpiLabel")
        number = QLabel(value)
        number.setObjectName("kpiValue")
        number.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(label)
        layout.addWidget(number)
        self._kpi_labels[key] = number
        return card

    def _fmt_int(self, value):
        try:
            return "{:,}".format(int(value)).replace(",", ".")
        except Exception:
            return str(value)

    def _update_kpis(self):
        if not self._kpi_labels:
            return
        done = [r for r in self.results_data if isinstance(r, dict)]
        n_done = len(done)
        n_tiles = self._tile_count or 0
        n_sources = self._source_count

        crop_total = sum(r.get("n_crop_instances", 0) for r in done)
        weed_cover_vals = [
            r.get("weed_stats", {}).get("do_phu_co_phan_tram")
            for r in done
            if r.get("weed_stats", {}).get("do_phu_co_phan_tram") is not None
        ]
        weed_cover = sum(weed_cover_vals) / len(weed_cover_vals) if weed_cover_vals else 0.0

        tile_text = "{} / {}".format(self._fmt_int(n_done), self._fmt_int(n_tiles)) \
            if n_tiles else self._fmt_int(n_done)
        self._kpi_labels["images"].setText(self._fmt_int(n_sources))
        self._kpi_labels["tiles"].setText(tile_text)
        self._kpi_labels["crop"].setText(self._fmt_int(crop_total))
        self._kpi_labels["weed"].setText("{:.1f}%".format(weed_cover))

        folder = self.folder_path.name if self.folder_path else "Chưa chọn thư mục ảnh"
        model = self.model_path.name if self.model_path else "Chưa chọn model"
        self.lblHeaderMeta.setText("{} | Model: {}".format(folder, model))

    def _toggle_theme(self):
        self._theme = "light" if self._theme == "dark" else "dark"
        self._apply_style()

    # -------------------------------------------------------------------------
    def _agg(self, tiles):
        """Tong hop (aggregate) danh sach tile-results cua 1 anh goc."""
        if not tiles:
            return {}
        if len(tiles) == 1:
            return tiles[0]
        out = dict(tiles[0])
        out["n_crop_instances"] = sum(t.get("n_crop_instances", 0) for t in tiles)
        sc = {}
        for t in tiles:
            for k, v in t.get("stage_counts", {}).items():
                sc[k] = sc.get(k, 0) + v
        out["stage_counts"] = sc
        def _sum(key):
            vals = [t["crop_stats"][key] for t in tiles
                    if t.get("crop_stats", {}).get(key) is not None]
            return sum(vals) if vals else None
        cs = {}
        for k in ("so_cay_uoc_tinh", "dien_tich_tan_m2", "so_cay_kem_pt", "mat_do_m2"):
            v = _sum(k); cs[k] = v if v is not None else None
        out["crop_stats"] = cs
        def _wsum(key):
            vals = [t["weed_stats"][key] for t in tiles
                    if t.get("weed_stats", {}).get(key) is not None]
            return sum(vals) if vals else None
        ws = {}
        for k in ("so_vung_co", "dien_tich_co_m2", "cay_bi_bao_vay"):
            ws[k] = _wsum(k)
        def _wavg(key):
            vals = [t["weed_stats"][key] for t in tiles
                    if t.get("weed_stats", {}).get(key) is not None]
            return sum(vals)/len(vals) if vals else None
        ws["ty_le_co_tren_cay"] = _wavg("ty_le_co_tren_cay")
        if tiles[0].get("weed_stats", {}).get("muc_do_canh_tranh"):
            ws["muc_do_canh_tranh"] = tiles[0]["weed_stats"]["muc_do_canh_tranh"]
        out["weed_stats"] = ws
        return out

    def _build_composite(self, tiles, show_crop, show_weed, alpha):
        """Ghep overlay cua tat ca tile len anh goc."""
        if not tiles:
            return None
        orig_path = tiles[0].get("original_path", "")
        img = cv2.imread(orig_path) if orig_path else None
        if img is None:
            # fallback: hien tile dau
            return tiles[0].get("mask_overlay")
        for t in tiles:
            tx, ty = t.get("tile_origin", (0, 0))
            crop_m = t.get("crop_mask")
            weed_m = t.get("weed_mask")
            H_img, W_img = img.shape[:2]
            x1 = min(tx + 640, W_img)
            y1 = min(ty + 640, H_img)
            rw, rh = x1 - tx, y1 - ty
            if rw <= 0 or rh <= 0:
                continue
            region  = img[ty:y1, tx:x1]
            colored = np.zeros_like(region)
            any_m   = np.zeros((rh, rw), dtype=bool)
            if show_crop and crop_m is not None:
                m = crop_m[:rh, :rw]; colored[m] = COLOR_CROP; any_m |= m
            if show_weed and weed_m is not None:
                m = weed_m[:rh, :rw]; colored[m] = COLOR_WEED; any_m |= m
            if any_m.any():
                blended = cv2.addWeighted(region, 1-alpha, colored, alpha, 0)
                region[any_m] = blended[any_m]
                img[ty:y1, tx:x1] = region
        return img

    # -------------------------------------------------------------------------
    def _refresh_display(self):
        if not self.results_data or self.current_idx >= len(self.results_data):
            return
        result = self.results_data[self.current_idx]
        if result is None:
            return

        mode = self.cmbViewMode.currentData() if hasattr(self, "cmbViewMode") else "overlay"
        display_images = result.get("display_images", {})
        img = display_images.get(mode)

        if mode == "overlay":
            crop_m = result.get("crop_mask")
            weed_m = result.get("weed_mask")
            per_stage_m = result.get("per_stage_masks")
            base = display_images.get("original")
            if base is not None and crop_m is not None and weed_m is not None:
                img = AnalysisWorker._build_overlay_image(
                    base, crop_m, weed_m,
                    self.sliderAlpha.value() / 100.0,
                    per_stage_m)

        if img is None:
            img = display_images.get("original")

        if img is None:
            return
        self._show_image(img)
        total_items = len(self._img_paths) if self._img_paths else len(self.results_data)
        self.lblSoAnh.setText("{} / {}".format(
            self.current_idx + 1, total_items))

    def _show_image(self, img_bgr):
        rgb  = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pix  = QPixmap.fromImage(qimg)
        pix  = pix.scaled(self.lblAnh.size(),
                          Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lblAnh.setPixmap(pix)

    def _on_slider(self, val):
        self.lblDoDam.setText("Độ đậm mask: {}%".format(val))
        self._refresh_display()

    # -------------------------------------------------------------------------
    def _anh_truoc(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self._refresh_display()
            r = self.results_data[self.current_idx]
            if r:
                self._fill_table(r)

    def _anh_sau(self):
        if self.current_idx < len(self._img_paths) - 1:
            self.current_idx += 1
            self._refresh_display()
            r = self.results_data[self.current_idx]
            if r:
                self._fill_table(r)

    def _set_nav_enabled(self, en):
        self.btnTruoc.setEnabled(en)
        self.btnSau.setEnabled(en)

    # -------------------------------------------------------------------------
    def _fill_table(self, result):
        self._fill_metric_table(self.tblCrop, self._build_crop_rows(result))
        self._fill_metric_table(self.tblWeed, self._build_weed_rows(result))

    def _fill_metric_table(self, tbl, rows):
        tbl.setRowCount(len(rows))
        tbl.setColumnCount(2)
        tbl.setHorizontalHeaderLabels(["Chỉ số", "Giá trị"])
        for r, (k, v) in enumerate(rows):
            tbl.setItem(r, 0, QTableWidgetItem(str(k)))
            tbl.setItem(r, 1, QTableWidgetItem(str(v)))
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.resizeColumnsToContents()

    def _build_crop_rows(self, result):
        rows = []
        n_crop = result.get("n_crop_instances", 0)
        stage = result.get("stage_counts", {})
        crop_m = result.get("crop_mask")
        cs = result.get("crop_stats", {})

        rows += [
            ("Tổng cây ngô", str(n_crop)),
            ("Ngô 2 lá", str(stage.get(IDX_MAIZE_2, 0))),
            ("Ngô 4 lá", str(stage.get(IDX_MAIZE_4, 0))),
            ("Ngô 6 lá", str(stage.get(IDX_MAIZE_6, 0))),
        ]
        if cs.get("do_phu_phan_tram") is not None:
            rows.append(("Phủ tán cây (%)", "{:.1f}".format(cs["do_phu_phan_tram"])))
        elif crop_m is not None:
            rows.append(("Phủ tán cây (%)", "{:.1f}".format(
                float(crop_m.sum()) / max(crop_m.size, 1) * 100)))

        if cs and "error" not in cs:
            if cs.get("so_cay_uoc_tinh") is not None:
                rows.append(("Số cây ước tính",
                             str(cs["so_cay_uoc_tinh"])))
            if cs.get("dien_tich_tan_m2") is not None:
                rows.append(("Diện tích tán (m2)",
                             "{:.2f}".format(cs["dien_tich_tan_m2"])))
            if cs.get("mat_do_m2") is not None:
                rows.append(("Mật độ (cây/m2)",
                             "{:.2f}".format(cs["mat_do_m2"])))
            if cs.get("so_cay_kem_pt") is not None:
                rows.append(("Cây kém phát triển",
                             str(cs["so_cay_kem_pt"])))

        return rows

    def _build_weed_rows(self, result):
        rows = []
        weed_m = result.get("weed_mask")
        ws = result.get("weed_stats", {})

        if ws.get("do_phu_co_phan_tram") is not None:
            rows.append(("Phủ tán cỏ (%)", "{:.1f}".format(ws["do_phu_co_phan_tram"])))
        elif weed_m is not None:
            rows.append(("Phủ tán cỏ (%)", "{:.1f}".format(
                float(weed_m.sum()) / max(weed_m.size, 1) * 100)))

        if ws and "error" not in ws:
            if ws.get("so_vung_co") is not None:
                rows.append(("Số vùng cỏ",
                             str(ws["so_vung_co"])))
            if ws.get("ty_le_co_tren_cay") is not None:
                rows.append(("Tỉ lệ cỏ/cây",
                             "{:.3f}".format(ws["ty_le_co_tren_cay"])))
            if ws.get("muc_do_canh_tranh"):
                rows.append(("Mức độ cạnh tranh",
                             self._competition_label(ws["muc_do_canh_tranh"])))
            if ws.get("dien_tich_co_m2") is not None:
                rows.append(("Diện tích cỏ (m2)",
                             "{:.2f}".format(ws["dien_tich_co_m2"])))
            if ws.get("cay_bi_bao_vay") is not None:
                rows.append(("Cây bị bao vây",
                             str(ws["cay_bi_bao_vay"])))
            if ws.get("vung_nguy_hiem") is not None:
                rows.append(("Vùng cảnh báo",
                             str(len(ws.get("vung_nguy_hiem") or []))))

        return rows

    @staticmethod
    def _competition_label(value):
        labels = {
            "thap": "Thấp",
            "trung_binh": "Trung bình",
            "cao": "Cao",
            "rat_cao": "Rất cao",
        }
        return labels.get(value, value)

    # -------------------------------------------------------------------------
    def _xuat_csv(self):
        if not any(self.results_data):
            QMessageBox.information(self, "Chưa có dữ liệu",
                "Chưa có kết quả phân tích.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu CSV", str(Path.home()/"uav_results.csv"),
            "CSV (*.csv)")
        if not path:
            return
        headers = [
            "File","Loai_KetQua","GSD",
            "N_Crop","N_Maize2","N_Maize4","N_Maize6",
            "DoPhuCay_pct","SoCay_UocTinh","DienTich_m2","MatDo_m2","CayKemPT",
            "DoPhuCo_pct","SoVungCo","TiLeCo","MucDoCanhTranh",
            "DienTichCo_m2","CayBiBaoVay","SoVungCanhBao",
        ]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for result in self.results_data:
                if not result:
                    continue
                orig_name = result.get("image_name") or Path(result.get("original_path","")).name
                st = result.get("stage_counts", {})
                cs = result.get("crop_stats", {})
                ws = result.get("weed_stats", {})
                w.writerow([
                    orig_name, result.get("result_type", "image"),
                    "{:.3f}".format(self.spinGSD.value()),
                    result.get("n_crop_instances", 0),
                    st.get(IDX_MAIZE_2,0), st.get(IDX_MAIZE_4,0),
                    st.get(IDX_MAIZE_6,0),
                    cs.get("do_phu_phan_tram",""),
                    cs.get("so_cay_uoc_tinh",""), cs.get("dien_tich_tan_m2",""),
                    cs.get("mat_do_m2",""), cs.get("so_cay_kem_pt",""),
                    ws.get("do_phu_co_phan_tram",""),
                    ws.get("so_vung_co",""), ws.get("ty_le_co_tren_cay",""),
                    ws.get("muc_do_canh_tranh",""), ws.get("dien_tich_co_m2",""),
                    ws.get("cay_bi_bao_vay",""),
                    len(ws.get("vung_nguy_hiem") or []),
                ])
        QMessageBox.information(self, "OK", "Đã lưu: " + path)

    def _luu_anh(self):
        """Lưu ảnh kết quả đang xem."""
        if not self.results_data or self.current_idx >= len(self.results_data):
            return
        cur = self.results_data[self.current_idx]
        if cur is None:
            return
        mode = self.cmbViewMode.currentData() if hasattr(self, "cmbViewMode") else "overlay"
        img = cur.get("display_images", {}).get(mode)
        if mode == "overlay" and cur.get("crop_mask") is not None and cur.get("weed_mask") is not None:
            img = AnalysisWorker._build_overlay_image(
                cur["display_images"]["original"], cur["crop_mask"], cur["weed_mask"],
                self.sliderAlpha.value() / 100.0,
                cur.get("per_stage_masks"))
        if img is None:
            return
        stem = Path(cur.get("image_name", "ket_qua")).stem
        name = "{}_{}.png".format(stem, mode)
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu ảnh", str(Path.home()/name),
            "Image (*.png *.jpg)")
        if path:
            cv2.imwrite(path, img)
            self.lblTrangThai.setText("Đã lưu: " + Path(path).name)

    # -------------------------------------------------------------------------
    def _apply_style(self):
        palettes = {
            "dark": {
                "bg": "#111513",
                "panel": "#1b211e",
                "panel2": "#222a26",
                "text": "#eef4ef",
                "muted": "#aab7ae",
                "border": "#354139",
                "accent": "#2fbf71",
                "accent_hover": "#43d685",
                "primary": "#70a5ff",
                "image_bg": "#0d1110",
                "hover_bg": "#28342e",
                "table_alt": "#202822",
                "menu": "#171c19",
                "disabled_bg": "#2a302d",
                "disabled_text": "#68746c",
            },
            "light": {
                "bg": "#eef3f0",
                "panel": "#ffffff",
                "panel2": "#f7faf8",
                "text": "#162018",
                "muted": "#66756b",
                "border": "#d8e2dc",
                "accent": "#248f5c",
                "accent_hover": "#1f7a51",
                "primary": "#2563eb",
                "image_bg": "#e7ede9",
                "hover_bg": "#e7ede9",
                "table_alt": "#f5f8f6",
                "menu": "#ffffff",
                "disabled_bg": "#edf2ef",
                "disabled_text": "#9aa6a0",
            },
        }
        c = palettes[self._theme]

        app = QApplication.instance()
        if app is not None:
            pal = QPalette()
            pal.setColor(QPalette.Window, QColor(c["bg"]))
            pal.setColor(QPalette.WindowText, QColor(c["text"]))
            pal.setColor(QPalette.Base, QColor(c["panel"]))
            pal.setColor(QPalette.AlternateBase, QColor(c["table_alt"]))
            pal.setColor(QPalette.Button, QColor(c["panel2"]))
            pal.setColor(QPalette.ButtonText, QColor(c["text"]))
            pal.setColor(QPalette.Text, QColor(c["text"]))
            pal.setColor(QPalette.Highlight, QColor(c["accent"]))
            pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
            pal.setColor(QPalette.Disabled, QPalette.Text, QColor(c["disabled_text"]))
            pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c["disabled_text"]))
            app.setPalette(pal)

        self.btnTheme.setText("Chế độ tối" if self._theme == "light" else "Chế độ sáng")
        self.setStyleSheet("""
            QMainWindow, QWidget#centralwidget {{
                background-color: {bg};
                color: {text};
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 13px;
            }}
            QWidget#panelLeft, QWidget#panelRight, QWidget#kpiRow,
            QWidget#headerTitleBox, QWidget#sidebarContent {{
                background: transparent;
                border: none;
            }}
            QScrollArea#sidebarScroll {{
                background: transparent;
                border: none;
            }}
            QWidget#sidebarBrand, QWidget#panelHeader, QWidget#kpiCard {{
                background-color: {panel};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            QLabel {{
                background: transparent;
                color: {text};
            }}
            QLabel#brandTitle {{
                color: {text};
                font-size: 16px;
                font-weight: 700;
            }}
            QLabel#brandSubtitle, QLabel#headerMeta, QLabel#kpiLabel {{
                color: {muted};
                font-size: 11px;
            }}
            QLabel#headerTitle {{
                color: {text};
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#kpiValue {{
                color: {text};
                font-size: 24px;
                font-weight: 700;
            }}
            QLabel#metricTitle {{
                color: {primary};
                font-size: 16px;
                font-weight: 800;
            }}
            QGroupBox {{
                background-color: {panel};
                border: 1px solid {border};
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 8px;
                color: {text};
                font-weight: 700;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 8px;
                color: {primary};
                background-color: {bg};
            }}
            QPushButton {{
                background-color: {panel2};
                color: {text};
                border: 1px solid {border};
                border-radius: 7px;
                padding: 5px 10px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {accent};
                background-color: {hover_bg};
            }}
            QPushButton:pressed {{
                background-color: {border};
            }}
            QPushButton:disabled {{
                background-color: {disabled_bg};
                color: {disabled_text};
                border-color: {border};
            }}
            QPushButton#btnBatDau {{
                background-color: {accent};
                border-color: {accent};
                color: #ffffff;
                font-size: 13px;
                font-weight: 700;
            }}
            QPushButton#btnBatDau:hover {{
                background-color: {accent_hover};
                border-color: {accent_hover};
            }}
            QPushButton#btnTheme {{
                color: {primary};
                padding-left: 16px;
                padding-right: 16px;
            }}
            QComboBox, QDoubleSpinBox, QSpinBox {{
                background-color: {panel2};
                color: {text};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 4px 8px;
                min-height: 22px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 22px;
            }}
            QLabel#lblTrangThai {{
                color: {primary};
                font-weight: 600;
            }}
            QLabel#lblSoAnh {{
                color: {text};
                font-weight: 700;
                min-width: 54px;
            }}
            QLabel#lblAnh {{
                background-color: {image_bg};
                border: 1px solid {border};
                border-radius: 10px;
                color: {muted};
                font-size: 14px;
            }}
            QProgressBar {{
                background-color: {panel2};
                border: 1px solid {border};
                border-radius: 8px;
                color: {text};
                text-align: center;
                font-weight: 600;
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 7px;
            }}
            QTableWidget {{
                background-color: {panel};
                alternate-background-color: {table_alt};
                color: {text};
                gridline-color: {border};
                border: 1px solid {border};
                border-radius: 10px;
                selection-background-color: {accent};
                selection-color: #ffffff;
                font-size: 15px;
            }}
            QTableWidget::item {{
                padding: 7px;
            }}
            QHeaderView::section {{
                background-color: {panel2};
                color: {primary};
                border: none;
                border-bottom: 1px solid {border};
                padding: 8px;
                font-weight: 700;
                font-size: 14px;
            }}
            QRadioButton, QCheckBox {{
                color: {text};
                spacing: 8px;
                background: transparent;
            }}
            QRadioButton::indicator, QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid {border};
                background-color: {panel2};
            }}
            QRadioButton::indicator {{
                border-radius: 8px;
            }}
            QRadioButton::indicator:checked, QCheckBox::indicator:checked {{
                background-color: {accent};
                border-color: {accent};
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: {panel2};
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {accent};
                border: 2px solid {panel};
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
            QMenuBar {{
                background-color: {menu};
                color: {text};
                border-bottom: 1px solid {border};
            }}
            QMenuBar::item:selected {{
                background-color: {panel2};
            }}
            QMenu {{
                background-color: {menu};
                color: {text};
                border: 1px solid {border};
            }}
            QMenu::item:selected {{
                background-color: {accent};
                color: #ffffff;
            }}
            QStatusBar {{
                background-color: {bg};
                color: {muted};
                border-top: 1px solid {border};
            }}
            QSplitter::handle {{
                background-color: {border};
                border-radius: 2px;
            }}
        """.format(**c))
