# Review Phase 8 - Dashboard và report export

Ngày review: 2026-07-27.

## Đã hoàn thành

- Thêm `MissionReport` schema 1/template 1.0 độc lập framework.
- Tổng hợp toàn mission và đúng ba drone: ảnh, ảnh hợp lệ/lỗi, GPS, độ cao, telemetry,
  số ảnh đã AI và weed coverage trung bình.
- Chi tiết từng ảnh chứa định danh, thời gian, vị trí, camera, GSD, quality status,
  model/version, weed metrics và trạng thái maize.
- Liệt kê job/provenance và spatial product/CRS/source job.
- Export atomic JSON, CSV UTF-8 BOM, HTML tự chứa và checksum manifest.
- HTML nhúng heatmap bằng data URI, không phụ thuộc mạng hoặc file ngoài.
- Workspace `Báo cáo` có dashboard, bảng ba drone, tab ảnh/job, heatmap, camera/GSD,
  giới hạn kết quả và export chạy nền.
- Overview và sidebar đều mở được workspace report; HTML có thể mở bằng ứng dụng mặc định.

## Kiểm tra

- Contract test aggregate 6 ảnh từ ba drone, job semantic, camera và heatmap.
- Snapshot key set cho schema JSON; kiểm tra schema/template version.
- CSV được đọc lại bằng `csv.DictReader`; giữ đúng tiếng Việt, khoảng trắng và đường dẫn
  kiểu Windows `C:\\Dữ liệu UAV\\ảnh 01.jpg`.
- Kiểm tra SHA-256 của từng artifact theo manifest.
- HTML được kiểm tra UTF-8, data URI, không có URL mạng.
- pytest-qt kiểm tra KPI, bảng, heatmap, export/open signal và controller thread.
- Screenshot dashboard 18 ảnh tại 1366x768, 1440x900 và 1920x1080.

## Kết quả chốt phase

- Ruff: đạt, không có lỗi.
- MyPy: đạt trên 122 file nguồn.
- Pytest: 101 test đạt.
- Visual regression: đạt cho ba ảnh Phase 7 và ba ảnh Phase 8.
- `uv lock --check`: lockfile hợp lệ với 109 package được resolve.
- Wheel `uav_crop_analysis-0.1.0-py3-none-any.whl`: 88 entry, có reporting/export/UI
  Phase 8 và không chứa module legacy ở thư mục gốc.
- PyInstaller macOS arm64: build thành công; bundle khoảng 727 MB do chứa Qt và runtime AI.
- Frozen smoke test: ứng dụng khởi động từ user home sạch, tạo database schema v3 và đầy đủ
  bảng mission, telemetry, analysis, camera, spatial product; không có traceback khi khởi động.

## Quyết định phạm vi

- Phase 8 chọn CSV + HTML thay cho Excel/PDF. HTML tự chứa có thể in thành PDF bằng trình
  duyệt mà không thêm dependency render native; CSV phục vụ Excel/GIS/data processing.
- GeoTIFF/GeoJSON tiếp tục do Phase 7 xuất và được report liên kết, không sao chép raster lớn
  vào thư mục report.
- Metric maize để trống có trạng thái rõ vì checkpoint instance chưa được cung cấp.
- GSD và weed area được ghi là `estimated`; không dùng chúng như số đo control-point.
