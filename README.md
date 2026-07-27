# UAV Crop Analysis

Ứng dụng desktop và module Python để quản lý dữ liệu khảo sát nông nghiệp từ tổ hợp ba
drone, chạy phân tích AI và xuất sản phẩm không gian.

## Phạm vi hiện tại

- Mission đúng ba drone, ba làn song song, gimbal nadir và đứng yên chụp.
- Import ảnh/EXIF/telemetry, kiểm tra GPS, độ cao, timestamp và thứ tự.
- Weed semantic bằng Attention U-Net, DeepLabV3+ hoặc SegFormer đã đăng ký.
- Maize instance có contract riêng; checkpoint YOLOv8/Mask R-CNN được bổ sung sau.
- Preview ba làn không georeference; orthomosaic GeoTIFF qua import hoặc NodeODM.
- Weed heatmap GeoTIFF/GeoJSON/PNG có CRS, transform và provenance.
- Dashboard báo cáo ba drone; xuất JSON/CSV/HTML tự chứa kèm checksum manifest.
- SDK Python, CLI và REST `/api/v1` cho phần mềm điều khiển bên ngoài.
- Đọc QGroundControl plan/log và MAVSDK telemetry/mission ở chế độ read-only.

## Chạy ứng dụng

```bash
python -m pip install -e .
uav-crop-analysis
```

NodeODM là dịch vụ tùy chọn bên ngoài:

```bash
UAV_CROP_NODEODM_URL=http://localhost:3000 uav-crop-analysis
```

## SDK, CLI và API

```bash
uav-crop capabilities
uav-crop mission list
uav-crop serve --host 127.0.0.1 --port 8765
```

```python
from uav_crop_analysis.sdk import UavCropAnalysis

with UavCropAnalysis.open() as sdk:
    missions = sdk.list_missions()
```

MAVSDK và binary QGC `.tlog` là optional:

```bash
python -m pip install -e '.[drone]'
```

## Tài liệu

- [Yêu cầu phần mềm](docs/requirements/YEU_CAU_PHAN_MEM.md)
- [Kế hoạch tái cấu trúc](docs/roadmap/KE_HOACH_TAI_CAU_TRUC.md)
- [Phân tích hiện trạng](docs/analysis/Phan_tich_UAV_CropAnalysis.txt)
- [Quy ước tổ chức repository](docs/ROOT_LAYOUT.md)
- [Geospatial contract](docs/phase7/GEOSPATIAL_CONTRACT.md)
- [SDK/API contract](docs/phase9/SDK_API_CONTRACT.md)

## Cấu trúc thư mục

- `src/`: mã nguồn package; `tests/`: kiểm thử; `tools/`: công cụ phát triển.
- `docs/`: yêu cầu, kế hoạch, phân tích và tài liệu theo phase.
- `models/`: model registry và checkpoint cục bộ (checkpoint bị Git ignore).
- `main.py`, `pyproject.toml`, `uv.lock`, `uav_analysis.spec`: các điểm vào và cấu hình build.
- `Báo cáo nghiệm thu CN2025/`: tài liệu nghiệm thu gốc, được giữ nguyên làm nguồn tham chiếu.

Các thư mục `build/`, `dist/`, cache, virtual environment và metadata package là đầu ra cục bộ,
đã được Git ignore. `dist/` hiện giữ các artifact kiểm chứng ở Phase 9.
