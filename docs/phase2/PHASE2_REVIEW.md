# Review Phase 2 - Mission store và import dữ liệu ba drone

Ngày review: 2026-07-27.

## Kết luận gate

**Đạt điều kiện bắt đầu Phase 3 về kiến trúc và model registry.** Một mission hợp
lệ có thể được nhập, đóng database, mở lại và khôi phục đủ mission, ba drone,
camera profile, image metadata và telemetry.

Adapter cấu trúc thư mục thực tế được để mở theo yêu cầu; contract hiện tại không
gắn với cách đặt thư mục hoặc tên file cụ thể.

## Đã hoàn thành

- Domain `CameraProfile`, `GeoPoint`, `ImageAsset`, `TelemetrySample`.
- `MissionDataRepository` port và SQLite implementation.
- Migration v1, khóa ngoại, unique checksum và index timestamp.
- Transaction atomic cho create/re-import mission bundle.
- `mission.json` schema version 1 và file ví dụ.
- Pillow EXIF reader và mapped CSV telemetry reader.
- Timestamp mapping ISO 8601 và Unix s/ms/us/ns.
- Đồng bộ nearest telemetry theo drone và timestamp.
- Validation thiếu drone, GPS lỗi, độ cao, timestamp skew, thứ tự và ảnh trùng.
- Import report với count theo drone và metadata coverage.
- Phân biệt cao độ tuyệt đối EXIF với độ cao tương đối flight controller.

## Kết quả kiểm tra

| Kiểm tra | Kết quả |
| --- | --- |
| `python -m pytest` | 44/44 passed |
| Coverage package | 88% |
| Mission đủ ba drone | Persist và reopen đủ metadata |
| Thiếu một drone | Báo `missing_drone_source`, không persist |
| GPS sai | Báo `invalid_telemetry_row` và `missing_gps` |
| Timestamp lệch | Báo `telemetry_time_skew`, không persist |
| Ảnh trùng | Báo `duplicate_image`, không persist |
| Thứ tự ảnh sai | Warning `non_monotonic_image_sequence`, vẫn persist |
| Migration create/reopen | Schema v1 ổn định |
| Transaction lỗi | Rollback giữ nguyên bundle cũ |
| Build và cài wheel ngoài source | Import package, tạo SQLite schema v1 thành công |
| `uv lock --check` | Passed |
| Kiểm tra model inventory | 9 semantic hợp lệ, 2 instance chờ đường dẫn |
| `python -m ruff check .` | Passed |
| `python -m mypy` | Passed |

## Rủi ro và phần để mở

1. Chưa có flight log thật nên mapping tên cột, timezone và đơn vị cần xác nhận sau.
2. Chưa có cấu trúc thư mục thật; adapter discovery sẽ được thêm khi nhận mẫu.
3. Pillow đọc EXIF chuẩn nhưng chưa đọc DJI XMP hoặc DNG chuyên biệt.
4. Đồng bộ hiện là nearest timestamp; chưa nội suy GPS giữa hai telemetry sample.
5. Database lưu đường dẫn nguồn. Chiến lược copy/link ảnh vào app data sẽ được quyết định khi biết dung lượng mission thực tế.
6. Golden AI vẫn chờ checkpoint instance v7.2 chính thức và thuộc Phase 3.

## Public extension points

- Thêm `TelemetryReader` mới cho flight controller cụ thể.
- Thêm `ImageMetadataReader` mới cho DNG/XMP hoặc sidecar metadata.
- Thêm adapter nhận cấu trúc thư mục thật và sinh `MissionImportRequest`.
- UI hoặc phần mềm điều khiển drone có thể gọi trực tiếp `ImportMissionData.execute()`.
