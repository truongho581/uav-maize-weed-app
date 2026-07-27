# Phase 9 - QGroundControl và MAVSDK integration contract

## QGroundControl

`QGroundControlPlanReader` nhận JSON có `fileType = Plan`, mission object và ít nhất một
item. Reader giữ:

- Planned home, firmware type, vehicle type và plan/mission version.
- `SimpleItem`: command, frame, tọa độ, độ cao và auto-continue.
- Survey `ComplexItem`: polygon, visual transect points, HoverAndCapture và overlap camera.

QGC Plan dùng cặp `[latitude, longitude]`. Dữ liệu được đọc để kiểm tra/tích hợp, không tự
động upload sang drone. Cấu trúc bám theo [QGroundControl Plan File Format](https://docs.qgroundcontrol.com/master/en/qgc-dev-guide/file_formats/plan.html).

`QGroundControlLogReader` hỗ trợ:

- CSV UTF-8/UTF-8 BOM có timestamp, system ID, latitude, longitude, relative altitude;
  chấp nhận alias cột QGC/MAVLink thường gặp.
- `.tlog` thông qua optional dependency `pymavlink` (`pip install .[drone]`).
- Mapping bắt buộc `system_id -> drone_id`; system chưa map bị từ chối.
- Bỏ mẫu lặp và mẫu đến sai thứ tự theo từng system, đồng thời trả bộ đếm.

## MAVSDK read-only

`MavsdkReadOnlyAdapter` chỉ có:

- `stream_positions`: connect, chờ connection state, đọc position và reconnect có giới hạn.
- `download_mission`: tải raw mission để quan sát.

Adapter không có `arm`, `takeoff`, `land`, `upload_mission`, `start_mission` hoặc API gửi
command. `commands_enabled` luôn là `False`. Cách connect/telemetry async theo
[MAVSDK-Python](https://mavsdk.mavlink.io/main/en/python/) và mission raw được chọn vì
MAVSDK lưu ý mission QGC có thể vượt tập command của Mission API chuẩn trong
[MAVSDK Missions](https://mavsdk.mavlink.io/main/en/cpp/guide/missions.html).

Mỗi endpoint cấu hình rõ `system_id`, `drone_id`, `system_address`. `TelemetryStreamGuard`:

- Từ chối trùng system ID hoặc một drone map sang nhiều system.
- Từ chối frame có system/drone không khớp mapping.
- Bỏ duplicate, timestamp/sequence sai thứ tự.
- Chuyển frame hợp lệ thành domain `TelemetrySample` có mission ID.

## Demo ba drone

`simulate_three_drone_streams` tạo ba system, ba drone và dữ liệu interleave xác định. Demo
kiểm tra contract host khi chưa có SITL/phần cứng. Nó không chứng minh độ trễ realtime,
độ ổn định radio, chất lượng GPS hoặc safety ngoài thực địa.

## Safety gate

Phase 9 chỉ đọc. Bất kỳ chức năng gửi lệnh nào sau này phải là adapter riêng, feature flag
mặc định tắt, có authentication, state machine, geofence, mất-link behavior, SITL test và
review an toàn trước khi nối thiết bị thật.
