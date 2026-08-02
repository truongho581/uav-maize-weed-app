# GreenEye

GreenEye là ứng dụng desktop và module Python để quản lý dữ liệu khảo sát nông nghiệp từ
một đến ba drone, chạy phân tích AI và xuất sản phẩm không gian.

## Phạm vi hiện tại

- Mission hỗ trợ từ một đến ba drone; kịch bản nghiệm thu chính dùng ba làn song song,
  gimbal nadir và đứng yên chụp.
- Import ảnh/EXIF/telemetry, kiểm tra GPS, độ cao, timestamp và thứ tự.
- Semantic mặc định dùng SegFormer-B0 `v7.2-maizemask-weedsgalore-seed42`, phân vùng đồng thời ngô và cỏ dại; cỏ dại vẫn là mục tiêu nghiệp vụ chính.
- Maize instance dùng YOLOv8-seg `v7.2-fixed-seed42`, xuất mask, khung bao và số cây theo `maize2/maize4/maize6` để đếm cây và nhận biết cây còi nhỏ.
- Kiểm tra nhanh checkpoint bằng ảnh đơn hoặc tối đa 12 khung đại diện từ video, không cần tạo mission.
- Preview ba làn không georeference; orthomosaic GeoTIFF qua import hoặc NodeODM cục bộ.
- Weed heatmap GeoTIFF/GeoJSON/PNG có CRS, transform và provenance.
- Dashboard báo cáo theo số drone thực tế; xuất JSON/CSV/HTML, ảnh ghép và heatmap
  GeoTIFF kèm checksum manifest.
- SDK Python, CLI và REST `/api/v1` cho phần mềm điều khiển bên ngoài.
- Đọc QGroundControl plan/log và MAVSDK telemetry/mission ở chế độ read-only.

## Chạy ứng dụng

```bash
python -m pip install -e .
uav-crop-analysis
```

Để tự tạo orthomosaic, người dùng chỉ cần cài Docker Desktop. Ứng dụng tự kiểm tra và
mở Docker Desktop khi cần, tải image chính thức ở lần đầu, khởi động NodeODM và gửi ảnh bằng PyODM.
Không cần clone source, build image, chạy container hay nhập URL thủ công.

```bash
uav-crop-analysis
```

Tại `Không gian`, nút `Chạy NodeODM` quản lý container `uav-crop-nodeodm` trên
`127.0.0.1:3000`, hiển thị tiến trình upload/xử lý/download và tự mở orthophoto
GeoTIFF trong viewer. Lần đầu cần mạng để Docker tải `opendronemap/nodeodm`; các lần
sau có thể chạy offline khi image đã có trên máy.

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

- [Mục lục tài liệu](docs/README.md)
- [Hướng dẫn sử dụng](docs/HUONG_DAN_SU_DUNG.md)
- [Yêu cầu phần mềm](docs/requirements/YEU_CAU_PHAN_MEM.md)
- [Contract xuất nhiệm vụ](docs/phase9_5/GREENEYE_MISSION_EXPORT_CONTRACT.md)

## Cấu trúc thư mục

- `src/`: mã nguồn package; `tests/`: kiểm thử; `tools/`: công cụ phát triển.
- `docs/`: yêu cầu, kế hoạch, phân tích và tài liệu theo phase.
- `models/`: model registry và checkpoint cục bộ (checkpoint bị Git ignore).
- `main.py`, `pyproject.toml`, `uv.lock`, `uav_analysis.spec`: các điểm vào và cấu hình build.
- `Báo cáo nghiệm thu CN2025/`: tài liệu nghiệm thu gốc, được giữ nguyên làm nguồn tham chiếu.

Các thư mục `build/`, `dist/`, cache, virtual environment và metadata package là đầu ra cục bộ,
đã được Git ignore. `dist/` hiện giữ các artifact kiểm chứng ở Phase 9.
