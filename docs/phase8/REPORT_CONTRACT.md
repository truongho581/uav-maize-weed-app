# Phase 8 - Mission report contract

## Phiên bản

- `schema_version = 1`: cấu trúc dữ liệu JSON/manifest.
- `template_version = 1.0`: bố cục HTML hiện tại.
- Thay đổi thêm field tương thích có thể giữ schema 1; xóa/đổi nghĩa field bắt buộc tăng
  `schema_version`.

`MissionReport` không phụ thuộc Qt, SQLite hay exporter. Desktop, CLI và API Phase 9 có
thể dùng cùng read model.

## Nguồn dữ liệu

- Mission, 1-3 lane, camera, ảnh và telemetry lấy từ `MissionDataRepository`.
- Job, model ID, threshold và summary lấy từ `AnalysisJobRepository`.
- Model version lấy từ model registry; không suy ra từ tên checkpoint.
- Orthomosaic/heatmap, CRS và source job lấy từ `SpatialProductRepository`.
- Với một ảnh có nhiều job hoàn thành, report lấy job có `updated_at` mới nhất.

Report không đọc lại mask để tính số khác với artifact đã công bố.

## Gói xuất

Mỗi lần xuất tạo một thư mục mới:

```text
<mission-id>-report-<timestamp>/
  report.json
  images.csv
  report.html
  manifest.json
```

- `report.json`: toàn bộ contract versioned, UTF-8.
- `images.csv`: UTF-8 BOM, một dòng cho mỗi ảnh để Excel và công cụ độc lập đọc Unicode.
- `report.html`: UTF-8, CSS và heatmap được nhúng nội tuyến; không cần mạng hoặc asset ngoài.
- `manifest.json`: schema/template version và SHA-256 của ba artifact trên.

Exporter ghi vào staging directory rồi rename atomically. Export trùng timestamp được thêm
hậu tố thay vì ghi đè report cũ.

## CSV chi tiết ảnh

Các cột bắt buộc gồm:

- Định danh: `mission_id`, `drone_id`, `lane_index`, `image_id`, `sequence_index`.
- Nguồn: `captured_at`, `source_path`, `latitude`, `longitude`, `relative_altitude_m`,
  `camera_profile_id`.
- Chất lượng: `quality_status` (`valid`, `warning`, `error`) và `issue_codes`.
- AI: `analysis_job_id`, `model_id`, `model_version`, `weed_coverage_percent`.
- Đơn vị ước tính: `estimated_gsd_cm_px`, `estimated_weed_area_m2`.
- Maize contract: trạng thái và các cột instance/density/canopy. Các ô metric để trống cho
  tới khi checkpoint instance được đăng ký; không thay bằng contour trên semantic mask.

## GSD và diện tích

Khi camera có horizontal FOV và chiều rộng ảnh:

```text
ground_width_m = 2 * altitude_m * tan(horizontal_fov_deg / 2)
estimated_gsd_cm_px = ground_width_m / image_width_px * 100
```

Ưu tiên độ cao tương đối của ảnh; nếu thiếu mới dùng độ cao kế hoạch. Đây là ước tính từ
camera model, không phải GSD đo bằng control point. `estimated_weed_area_m2` chỉ được tạo
khi cả GSD và weed coverage đều có.

## Quy tắc nghiệp vụ

- Weed là semantic coverage; không có số instance weed.
- Maize là instance; report không tạo số liệu maize khi checkpoint/worker chưa sẵn sàng.
- Ảnh thiếu nguồn/GPS/độ cao là `error`; telemetry skew là `warning` nếu không có lỗi nặng hơn.
- Preview không georeferenced vẫn được liệt kê nhưng không được trình bày như bản đồ địa lý.
- HTML và JSON luôn có phần giới hạn kết quả, kể cả khi toàn bộ dữ liệu đầy đủ.
