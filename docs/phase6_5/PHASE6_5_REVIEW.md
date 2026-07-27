# Review Phase 6.5 - Legacy retirement

Ngày review: 2026-07-27.

## Mục tiêu

Loại bỏ desktop PyQt5 và các module phẳng ở project root sau khi hành vi cần giữ đã
được chuyển sang package `uav_crop_analysis`.

## Migration

- `tile_engine.py` được thay bởi `jobs.pipeline.tile_windows`, probability blending và
  atomic artifact pipeline.
- Contract class không còn lấy từ constant của YOLO legacy; model registry bắt buộc
  weed semantic và maize instance tách biệt.
- `CropProcessor`/`WeedProcessor` được thay bằng metric API framework-neutral:
  `summarize_maize_instances()` và `summarize_weed_mask()`.
- Maize density dùng toàn bộ footprint ảnh theo GSD, không chia số cây cho riêng diện
  tích tán như implementation cũ.
- Chỉ số dinh dưỡng suy diễn từ RGB và contour-count trên semantic mask không được
  chuyển tiếp vì không phù hợp contract nghiệm thu hiện tại.

## Đã xóa

- `ai_core.py`, `crop_processor.py`, `weed_processor.py`, `tile_engine.py`.
- `phan_tich_ui.py`, Qt Designer resource cũ và optional dependency PyQt5.
- Legacy adapter, legacy console entry point và test compatibility tương ứng.
- `build_exe.py`; PyInstaller spec là build contract duy nhất.

`main.py` được giữ như bootstrap mỏng cho source/PyInstaller. Các file `.py` trong
`src/uav_crop_analysis` là source code có cấu trúc của sản phẩm, không phải legacy.

## Kiểm tra

- Test hồi quy được chuyển sang application/job/model contracts hiện tại.
- Wheel sạch không chứa module legacy hoặc PyQt5.
- PyInstaller bundle khởi động từ `HOME` sạch và tạo database/log đúng app path.
- `requirements.txt` trỏ về `pyproject.toml`; `requirements-dev.lock` và `uv.lock`
  là hai lockfile được sinh lại từ metadata chuẩn.
