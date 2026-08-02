# Phase 2 - Hợp đồng nhập dữ liệu mission

## Không phụ thuộc cấu trúc thư mục

Lõi nhập dữ liệu không tự suy đoán thư mục nào thuộc drone nào. Mỗi nguồn được
khai báo bằng `DroneImportSource` gồm:

- `drone_id` đã được gán vào một lane của mission.
- `image_dir` chứa ảnh của riêng drone đó.
- `telemetry_file` tùy chọn.
- `telemetry_mapping` ánh xạ tên cột và định dạng timestamp.
- `camera_profile` tùy chọn.

Khi có cấu trúc dữ liệu thực tế, chỉ cần thêm adapter chuyển cấu trúc đó thành 1-3
`DroneImportSource`. SQLite schema và import service không phải thay đổi.

## Mission manifest

Schema canonical là `mission.json` version 1. Xem
[`mission.example.json`](./mission.example.json).

Manifest lưu:

- Mission ID, tên, thời điểm tạo có timezone.
- Độ cao, góc gimbal, forward/side overlap và capture mode.
- Từ một đến ba drone, lane liên tục `0..n-1`, đường dẫn ảnh và telemetry.
- Mapping cột telemetry và camera profile.
- Ngưỡng lệch timestamp tối đa, mặc định 2 giây.

Đường dẫn nằm cùng cây thư mục với manifest được ghi tương đối để mission có thể
di chuyển giữa Windows, Linux và macOS.

## Telemetry CSV

Mapping mặc định:

| Ý nghĩa | Tên cột mặc định |
| --- | --- |
| Thời gian | `timestamp` |
| Vĩ độ | `latitude` |
| Kinh độ | `longitude` |
| Độ cao tương đối | `relative_altitude_m` |

Timestamp hỗ trợ ISO 8601 và Unix seconds/milliseconds/microseconds/nanoseconds.
CSV reader phát hiện thiếu cột, dòng sai, GPS ngoài miền, timestamp trùng và thứ
tự telemetry không tăng.

## Đồng bộ ảnh và telemetry

1. Ảnh được liệt kê theo tên file và đọc `DateTimeOriginal` từ EXIF.
2. Ảnh được băm SHA-256 để phát hiện trùng trong toàn mission.
3. Mỗi ảnh tìm telemetry gần nhất của cùng `drone_id` bằng timestamp.
4. Chỉ dùng telemetry nếu độ lệch không vượt `max_telemetry_skew_seconds`.
5. GPS hoặc độ cao tương đối thiếu sau đồng bộ là lỗi.
6. Độ cao tương đối ngoài 10-20 m là warning và vẫn được giữ để review.

`GPSAltitude` trong EXIF được lưu là `absolute_altitude_m`; không được diễn giải
thành độ cao tương đối để tính GSD. `relative_altitude_m` phải đến từ flight log
hoặc adapter thiết bị biết rõ hệ quy chiếu.

## Import report

`ImportReport` trả về:

- Số ảnh hợp lệ theo từng drone.
- Danh sách image asset và telemetry sample.
- Coverage timestamp, GPS và độ cao tương đối.
- Issue có `code`, `severity`, `drone_id`, `source` và `row_number` khi có.
- Trạng thái `persisted`.

Nếu có ít nhất một issue mức `error`, bundle không được ghi vào database. Warning
không chặn import.

## SQLite schema v1

- `schema_migrations`
- `missions`
- `drone_assignments`
- `camera_profiles`
- `image_assets`
- `telemetry_samples`

Mission bundle được ghi trong một transaction. Re-import thay dữ liệu con của
mission theo kiểu atomic; nếu khóa ngoại hoặc insert lỗi, dữ liệu trước đó được
rollback nguyên vẹn.
